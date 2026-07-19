"""Partition-aware run launcher for the scaling experiment.

The core coop runner (``runner.coop.execute_coop``) hardwires one feature per
agent.  The scaling experiment needs N agents to split a fixed set of K features
(K >= N), so each agent may own a *subset*.  This launcher mirrors
``execute_coop``'s threading / messaging / result-assembly but:

* builds each agent's prompt by concatenating its assigned features' specs
  (same shape as ``runner.solo``), and
* records a per-agent ``features`` list + the full ``assignment`` in ``result.json``.

It is only invoked by the ``scaling`` subcommand.  Base runs never reach here.
N=1 (single agent owns all K, messaging off) and N>=2 (peer agents, Redis
messaging when the comm condition is on) go through the same path.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from cooperbench.agents import get_runner
from cooperbench.runner.coop import _count_by_kind, _extract_conversation, _message_timestamp_key
from cooperbench.runner.tasks import DEFAULT_DATASET_DIR, DEFAULT_LOGS_DIR
from cooperbench.utils import console, get_image_name


def _cell_leaf(features: list[int], n_agents: int, condition: str, trial: int) -> str:
    """Relative log path distinguishing cells that share a pool within one run."""
    feature_str = "_".join(f"f{f}" for f in sorted(features))
    return f"{feature_str}/N{n_agents}_{condition}_r{trial}"


def _build_agent_prompt(task_dir: Path, features: list[int]) -> str:
    """Concatenate the assigned features' specs into one prompt (solo-style)."""
    parts = []
    for fid in sorted(features):
        feature_file = task_dir / f"feature{fid}" / "feature.md"
        if not feature_file.exists():
            raise FileNotFoundError(f"Feature file not found: {feature_file}")
        parts.append(f"## Feature {fid}\n\n{feature_file.read_text()}")
    return "\n\n---\n\n".join(parts)


def execute_partitioned(
    repo_name: str,
    task_id: int,
    assignment: dict[str, list[int]],
    run_name: str,
    *,
    condition: str,
    trial: int,
    seed: int,
    pool_id: str,
    agent_name: str = "claude_code",
    model_name: str = "claude-sonnet-5",
    redis_url: str = "redis://localhost:6379",
    messaging_enabled: bool = True,
    message_schema: dict | None = None,
    git_enabled: bool = False,
    force: bool = False,
    quiet: bool = True,
    backend: str = "docker",
    agent_config: str | None = None,
    dataset_dir: str | Path | None = None,
    logs_dir: str | Path | None = None,
) -> dict | None:
    """Run one scaling cell (fixed pool, fixed N, one condition, one trial).

    ``assignment`` maps ``agent1..agentN`` -> the feature ids that agent owns
    (from :func:`cooperbench.scaling.partition.partition_features`).  ``condition``
    is ``"comm"`` or ``"nocomm"``.  Returns a result dict (or a ``skipped`` marker
    if the cell already completed and ``force`` is false).
    """
    agent_ids = sorted(assignment)
    n_agents = len(agent_ids)
    all_features = sorted(f for a in agent_ids for f in assignment[a])
    # comm only makes sense with >= 2 agents; N=1 is inherently no-comm.
    comm_on = messaging_enabled and condition == "comm" and n_agents > 1
    # shared-git integration ("agents own the merge"); N=1 has nothing to integrate.
    git_on = git_enabled and n_agents > 1
    # the agents list is needed whenever peers exist (messaging OR git remote wiring).
    peers_on = comm_on or git_on

    root = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
    task_dir = Path(root) / repo_name / f"task{task_id}"
    logs_root = Path(logs_dir) if logs_dir is not None else DEFAULT_LOGS_DIR
    log_dir = (
        logs_root
        / run_name
        / "scaling"
        / repo_name
        / str(task_id)
        / _cell_leaf(all_features, n_agents, condition, trial)
    )
    result_file = log_dir / "result.json"

    if result_file.exists() and not force:
        prev = json.loads(result_file.read_text())
        had_error = any(a.get("status") == "Error" for a in prev.get("agents", {}).values())
        if not had_error:
            return {"skipped": True, **prev}

    run_id = uuid.uuid4().hex[:8]
    namespaced_redis = f"{redis_url}#run:{run_id}"
    start_time = datetime.now()

    # Load agent config once (shared across the cell's agents).
    base_config = {"backend": backend}
    if agent_config:
        cfg_path = Path(agent_config)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Agent config file not found: {agent_config}")
        loaded = yaml.safe_load(cfg_path.read_text())
        if loaded:
            base_config.update(loaded)

    # Shared git server for the cell (one per cell, shared by its N agents).  Only
    # for git_on; mirrors execute_coop's lifecycle.  openhands manages its own.
    git_server = None
    git_server_url: str | None = None
    git_network: str | None = None
    if git_on and agent_name != "openhands_sdk":
        from cooperbench.agents.mini_swe_agent_v2.connectors import create_git_server

        git_server = create_git_server(backend=backend, run_id=run_id, app=None)
        git_server_url = git_server.url
        git_network = getattr(git_server, "network_name", None)

    results: dict[str, dict] = {}
    threads: list[threading.Thread] = []

    def run_thread(agent_id: str, features: list[int]) -> None:
        try:
            prompt = _build_agent_prompt(task_dir, features)
            config = dict(base_config)
            config["run_id"] = run_id if comm_on else None
            if git_network:
                config["git_network"] = git_network
            runner = get_runner(agent_name)
            result = runner.run(
                task=prompt,
                image=get_image_name(repo_name, task_id),
                agent_id=agent_id,
                model_name=model_name,
                agents=agent_ids if peers_on else None,
                comm_url=namespaced_redis if comm_on else None,
                git_server_url=git_server_url if git_on else None,
                git_enabled=git_on,
                messaging_enabled=comm_on,
                message_schema=message_schema if comm_on else None,
                config=config,
                agent_config=agent_config,
                log_dir=str(log_dir),
            )
            results[agent_id] = {
                "agent_id": agent_id,
                "features": sorted(features),
                "status": result.status,
                "patch": result.patch,
                "cost": result.cost,
                "steps": result.steps,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cache_read_tokens": result.cache_read_tokens,
                "cache_write_tokens": result.cache_write_tokens,
                "messages": result.messages,
                "sent_messages": result.sent_messages,
                "error": result.error,
            }
        except Exception as e:  # noqa: BLE001 — record, don't crash the cell
            results[agent_id] = {
                "agent_id": agent_id,
                "features": sorted(features),
                "status": "Error",
                "patch": "",
                "cost": 0,
                "steps": 0,
                "messages": [],
                "sent_messages": [],
                "error": str(e),
            }

    if comm_on:
        from cooperbench.infra.redis import ensure_redis

        ensure_redis(redis_url)

    if not quiet:
        console.print(f"  [dim]scaling[/dim] {pool_id} N={n_agents} {condition} r{trial}")

    try:
        for agent_id in agent_ids:
            t = threading.Thread(target=run_thread, args=(agent_id, assignment[agent_id]))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    finally:
        if git_server is not None:
            git_server.cleanup()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    total_cost = sum(r.get("cost", 0) for r in results.values())
    total_steps = sum(r.get("steps", 0) for r in results.values())

    log_dir.mkdir(parents=True, exist_ok=True)

    # Inter-agent conversation (sent-only, timestamp-sorted) — reuses coop helpers.
    conversation = _extract_conversation(
        # _extract_conversation expects each result to carry feature_id; fold the
        # agent's first feature in so the helper's per-message tagging works.
        {a: {**r, "feature_id": (r["features"][0] if r["features"] else None)} for a, r in results.items()},
        agent_ids,
    )
    sent_msgs = [m for m in conversation if not m.get("received")]
    sent_msgs.sort(key=_message_timestamp_key)
    (log_dir / "conversation.json").write_text(json.dumps(sent_msgs, indent=2, default=str))

    for agent_id in agent_ids:
        (log_dir / f"{agent_id}.patch").write_text(results[agent_id].get("patch", ""))

    result_data = {
        "repo": repo_name,
        "task_id": task_id,
        "features": all_features,
        "setting": "scaling",
        "n_agents": n_agents,
        "condition": condition,
        "git_integrated": git_on,
        "pool_id": pool_id,
        "trial": trial,
        "seed": seed,
        "run_id": run_id,
        "run_name": run_name,
        "agent_framework": agent_name,
        "model": model_name,
        "started_at": start_time.isoformat(),
        "ended_at": end_time.isoformat(),
        "duration_seconds": duration,
        "assignment": {a: sorted(assignment[a]) for a in agent_ids},
        "agents": {
            a: {
                "features": sorted(assignment[a]),
                "status": r.get("status"),
                "cost": r.get("cost", 0),
                "steps": r.get("steps", 0),
                "input_tokens": r.get("input_tokens", 0),
                "output_tokens": r.get("output_tokens", 0),
                "cache_read_tokens": r.get("cache_read_tokens", 0),
                "cache_write_tokens": r.get("cache_write_tokens", 0),
                "patch_lines": len(r.get("patch", "").splitlines()),
                "error": r.get("error"),
            }
            for a, r in results.items()
        },
        "total_cost": total_cost,
        "total_steps": total_steps,
        "messages_sent": len(sent_msgs),
        "message_schema": message_schema.get("name") if message_schema else None,
        "messages_by_kind": _count_by_kind(sent_msgs),
        "log_dir": str(log_dir),
    }
    result_file.write_text(json.dumps(result_data, indent=2))

    return {
        "results": results,
        "result_data": result_data,
        "total_cost": total_cost,
        "total_steps": total_steps,
        "duration": duration,
        "run_id": run_id,
        "log_dir": str(log_dir),
    }
