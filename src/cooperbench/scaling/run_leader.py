"""Leader-topology launcher for the scaling experiment.

The flat scaling cell (``run_partitioned``) deals the K features round-robin to
N peer agents up front.  This launcher runs the *supervised* alternative: one
**leader** container plus N **worker** containers.  The leader — typically a
larger model — is the only agent that sees all K feature specs; it decides the
division of labour itself, materialises each spec into the shared scratchpad,
assigns work through the team task list (``coop-task-*``), monitors progress,
and owns the final integration over the shared git remote.  Workers start with
no feature spec at all: they claim what the leader assigns them.

Comparing this arm against the flat arm at the same worker count N asks whether
coordination scales better when it is centralised in a supervisor instead of
negotiated peer-to-peer.

Reuses the team_harness coordination surface (task list, scratchpad volume,
MCP, protocol — see ``cooperbench.team_harness``) but keeps the scaling cell
contract: ``condition="leader"`` cells, ``{agent_id}.patch`` artifacts,
per-agent durations, and a ``result.json`` that ``experiment._assemble_row``
can flatten.  ``N`` counts *workers*; the leader is container ``agent1``
(the team harness treats the first agent id as the lead) and its cost is
reported separately as ``leader_cost`` while still counting in ``total_cost``
— the supervisor is real overhead of the topology.

Shared-git integration is always on here: the leader's integrated tree is what
``eval_git.score_team`` scores (the leader sorts first, so it is the designated
integrator).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from cooperbench.agents import get_runner
from cooperbench.runner.coop import _count_by_kind, _extract_conversation, _message_timestamp_key
from cooperbench.runner.tasks import DEFAULT_DATASET_DIR, DEFAULT_LOGS_DIR
from cooperbench.scaling.run_partitioned import _cell_leaf
from cooperbench.team_harness import TeamHarnessConfig, TeamSession
from cooperbench.utils import console, get_image_name

DEFAULT_LEADER_MODEL = "claude-opus-5"


def _leader_task_text(specs: dict[int, str], workers: list[str]) -> str:
    """The leader's brief: all K specs + the allocation/integration mandate."""
    k = len(specs)
    worker_list = ", ".join(workers)
    header = (
        f"You lead a team of {len(workers)} implementation agent(s) ({worker_list}) "
        f"working in this repository. The workload is the {k} feature "
        f"specification(s) below. Your workers have NOT been given any spec — "
        f"deciding who implements what is your job.\n\n"
        f"1. Read every spec, decide the division of labour, and write it to "
        f"/workspace/shared/PLAN.md.\n"
        f"2. Write each spec verbatim to /workspace/shared/specs/feature<id>.md "
        f"so your workers can read their assignments.\n"
        f"3. Create one task per feature with "
        f'`coop-task-create --assign <worker> "Implement feature <id> '
        f'(spec: /workspace/shared/specs/feature<id>.md)"`, choosing the '
        f"allocation you judge best (group related features on one worker).\n"
        f"4. Monitor with `coop-task-list`; unblock workers by messaging them.\n"
        f"5. Integrate: fetch and merge every worker's branch on the shared git "
        f"remote, resolve conflicts, verify the merged tree, and submit the "
        f"integrated result. The benchmark scores YOUR integrated tree against "
        f"all {k} feature suites.\n\n"
        f"Implement a feature yourself only when a worker is stuck — your value "
        f"is allocation, review, and integration."
    )
    spec_blocks = [f"## Feature {fid}\n\n{specs[fid]}" for fid in sorted(specs)]
    return "\n\n---\n\n".join([header, *spec_blocks])


def _worker_task_text(agent_id: str, k: int, leader: str = "agent1") -> str:
    """A worker's brief: no spec — await the leader's allocation."""
    return (
        f"You are {agent_id}, an implementation agent on a team implementing {k} "
        f"feature(s) in this repository. Your team lead ({leader}) decides which "
        f"features are yours — you have not been given a spec directly.\n\n"
        f"1. Check `coop-task-list` (and /workspace/shared/tasks/) for tasks "
        f"assigned to you. If none exist yet, the lead is still planning: wait "
        f"briefly and re-check (see also /workspace/shared/PLAN.md).\n"
        f"2. Read each assigned feature's spec at "
        f"/workspace/shared/specs/feature<id>.md.\n"
        f"3. Claim the task (`coop-task-claim`), implement the feature, publish "
        f"your work on the shared git remote, and mark the task done "
        f"(`coop-task-update`).\n"
        f"Implement only what the lead assigns you."
    )


def execute_leader_cell(
    repo_name: str,
    task_id: int,
    features: list[int],
    n_workers: int,
    run_name: str,
    *,
    condition: str = "leader",
    trial: int,
    seed: int,
    pool_id: str,
    agent_name: str = "claude_code",
    leader_model: str = DEFAULT_LEADER_MODEL,
    worker_model: str = "claude-sonnet-5",
    redis_url: str = "redis://localhost:6379",
    force: bool = False,
    quiet: bool = True,
    backend: str = "docker",
    agent_config: str | None = None,
    dataset_dir: str | Path | None = None,
    logs_dir: str | Path | None = None,
) -> dict | None:
    """Run one leader-topology scaling cell (fixed pool, N workers, one trial).

    Launches ``agent1`` (leader, ``leader_model``) plus ``agent2..agentN+1``
    (workers, ``worker_model``) as one team over the shared git server, the
    team task list, and Redis messaging.  Returns the same result shape as
    :func:`cooperbench.scaling.run_partitioned.execute_partitioned` (or a
    ``skipped`` marker when the cell already completed and ``force`` is off).
    """
    leader = "agent1"
    workers = [f"agent{i}" for i in range(2, n_workers + 2)]
    agent_ids = [leader, *workers]  # leader first: the harness lead convention
    all_features = sorted(features)

    root = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
    task_dir = Path(root) / repo_name / f"task{task_id}"
    logs_root = Path(logs_dir) if logs_dir is not None else DEFAULT_LOGS_DIR
    log_dir = (
        logs_root
        / run_name
        / "scaling"
        / repo_name
        / str(task_id)
        / _cell_leaf(all_features, n_workers, condition, trial)
    )
    result_file = log_dir / "result.json"

    if result_file.exists() and not force:
        prev = json.loads(result_file.read_text())
        had_error = any(a.get("status") == "Error" for a in prev.get("agents", {}).values())
        if not had_error:
            return {"skipped": True, **prev}

    specs: dict[int, str] = {}
    for fid in all_features:
        feature_file = task_dir / f"feature{fid}" / "feature.md"
        if not feature_file.exists():
            raise FileNotFoundError(f"Feature file not found: {feature_file}")
        specs[fid] = feature_file.read_text()

    run_id = uuid.uuid4().hex[:8]
    namespaced_redis = f"{redis_url}#run:{run_id}"
    team_features = TeamHarnessConfig()  # full harness: task list, scratchpad, mcp, ...
    team_volume = f"cb-team-{run_id}"
    session = TeamSession(
        run_id=run_id,
        redis_url=namespaced_redis,
        agents=agent_ids,
        team_volume=team_volume,
        config=team_features,
    )
    start_time = datetime.now()

    base_config: dict = {"backend": backend, "team_volume": team_volume}
    if agent_config:
        cfg_path = Path(agent_config)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Agent config file not found: {agent_config}")
        loaded = yaml.safe_load(cfg_path.read_text())
        if loaded:
            base_config.update(loaded)

    from cooperbench.infra.redis import ensure_redis

    ensure_redis(redis_url)

    # Seed a single meta-task for the leader.  Unlike execute_team, feature
    # tasks are NOT pre-assigned — allocating them is the leader's job.
    import redis as redis_lib

    task_list = None
    try:
        bare_url = redis_url.split("#", 1)[0]
        client = redis_lib.from_url(bare_url)
        task_list = session.task_list_client(redis_client=client)
        if task_list is not None:
            task_list.create(
                title=f"Lead-only: allocate the {len(all_features)} features across your workers, then integrate",
                created_by="bench-runner",
                owner=leader,
                metadata={"lead_task": True, "features": all_features},
            )
    except (redis_lib.exceptions.RedisError, OSError) as e:
        if not quiet:
            console.print(f"  [yellow]task-list[/yellow] degraded: {e}")
        task_list = None

    # Shared git server — always on for the leader arm: the leader's merged
    # tree is the scored artifact.
    from cooperbench.agents.mini_swe_agent_v2.connectors import create_git_server

    git_server = create_git_server(backend=backend, run_id=run_id, app=None)
    git_server_url = git_server.url
    git_network = getattr(git_server, "network_name", None)

    results: dict[str, dict] = {}
    threads: list[threading.Thread] = []

    def run_thread(agent_id: str, role: str, model_name: str, task_text: str) -> None:
        agent_start = time.monotonic()
        try:
            config = dict(base_config)
            config["run_id"] = run_id
            if git_network:
                config["git_network"] = git_network
            runner = get_runner(agent_name)
            result = runner.run(
                task=task_text,
                image=get_image_name(repo_name, task_id),
                agent_id=agent_id,
                model_name=model_name,
                agents=agent_ids,
                comm_url=namespaced_redis,
                git_server_url=git_server_url,
                git_enabled=True,
                messaging_enabled=True,
                config=config,
                agent_config=agent_config,
                log_dir=str(log_dir),
                team_role=role,
                team_id=run_id,
                task_list_url=namespaced_redis,
                team_features=team_features,
            )
            results[agent_id] = {
                "agent_id": agent_id,
                "team_role": role,
                "model": model_name,
                "features": [],  # allocation is the leader's, not the bench's
                "status": result.status,
                "duration_seconds": time.monotonic() - agent_start,
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
                "team_role": role,
                "model": model_name,
                "features": [],
                "status": "Error",
                "duration_seconds": time.monotonic() - agent_start,
                "patch": "",
                "cost": 0,
                "steps": 0,
                "messages": [],
                "sent_messages": [],
                "error": str(e),
            }

    if not quiet:
        console.print(f"  [dim]scaling/leader[/dim] {pool_id} N={n_workers} r{trial}")

    try:
        t = threading.Thread(
            target=run_thread,
            args=(leader, "lead", leader_model, _leader_task_text(specs, workers)),
        )
        threads.append(t)
        t.start()
        for w in workers:
            t = threading.Thread(
                target=run_thread,
                args=(w, "member", worker_model, _worker_task_text(w, len(all_features), leader)),
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    finally:
        git_server.cleanup()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    total_cost = sum(r.get("cost", 0) for r in results.values())
    total_steps = sum(r.get("steps", 0) for r in results.values())

    log_dir.mkdir(parents=True, exist_ok=True)

    # Task-list audit trail → coordination metrics (how the leader allocated).
    metrics = None
    try:
        fresh = redis_lib.from_url(redis_url.split("#", 1)[0])
        fresh_list = session.task_list_client(redis_client=fresh)
        metrics, events, final_tasks = session.harvest_metrics(fresh_list)
        (log_dir / "task_log.json").write_text(json.dumps(events, indent=2, default=str))
        (log_dir / "tasks.json").write_text(json.dumps(final_tasks, indent=2, default=str))
    except (redis_lib.exceptions.RedisError, OSError):
        pass

    conversation = _extract_conversation(
        {a: {**r, "feature_id": None} for a, r in results.items()},
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
        "topology": "leader",
        "n_agents": n_workers,  # N counts workers; the leader is overhead on top
        "n_containers": n_workers + 1,
        "leader": leader,
        "leader_model": leader_model,
        "worker_model": worker_model,
        "condition": condition,
        "git_integrated": True,
        "pool_id": pool_id,
        "trial": trial,
        "seed": seed,
        "run_id": run_id,
        "run_name": run_name,
        "agent_framework": agent_name,
        "model": worker_model,
        "started_at": start_time.isoformat(),
        "ended_at": end_time.isoformat(),
        "duration_seconds": duration,
        "agents": {
            a: {
                "team_role": r.get("team_role"),
                "model": r.get("model"),
                "status": r.get("status"),
                "duration_seconds": r.get("duration_seconds"),
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
        "leader_cost": results.get(leader, {}).get("cost", 0),
        "total_steps": total_steps,
        "messages_sent": len(sent_msgs),
        "messages_by_kind": _count_by_kind(sent_msgs),
        "team_metrics": metrics,
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
