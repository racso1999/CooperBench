"""Scaling-experiment orchestration.

Two entry points:

* :func:`screen_pools` — the ``--screen-pools`` pass.  Runs a solo (N=1) agent on
  each candidate pool for a few trials and keeps only pools the single agent
  *reliably* completes (all K feature suites pass in >= a threshold of trials).
  Downstream sweeps draw only from qualified pools.

* :func:`run_experiment` — the sweep.  For each ``(pool, N, condition, trial)``
  cell it partitions the K features across N agents, launches the run, evaluates
  the N-way merge, derives token buckets, and emits one flat row.  Rows are the
  input to ``analysis.py``.

Determinism: the partition is structural (seed-independent); ``seed`` is recorded
for provenance and fixes pool/feature *selection*, not LLM sampling (Claude Code
exposes no sampling seed — trials capture model stochasticity).
"""

from __future__ import annotations

import json
from pathlib import Path

from cooperbench.scaling.buckets import compute_run_buckets
from cooperbench.scaling.eval_git import score_team
from cooperbench.scaling.eval_nway import test_merged_nway
from cooperbench.scaling.partition import partition_features
from cooperbench.scaling.pools import Pool
from cooperbench.scaling.pricing import apportion_bucket_dollars
from cooperbench.scaling.run_partitioned import execute_partitioned
from cooperbench.utils import console

DEFAULT_CONDITIONS = ("comm", "nocomm")


def _run_and_eval_cell(
    pool: Pool,
    n_agents: int,
    condition: str,
    trial: int,
    *,
    seed: int,
    partition_policy: str,
    agent_name: str,
    model_name: str,
    redis_url: str,
    message_schema: dict | None,
    backend: str,
    agent_config: str | None,
    dataset_dir: str | Path | None,
    logs_dir: str | Path | None,
    force: bool,
    timeout: int,
    run_independent: bool,
    git_enabled: bool = False,
) -> dict:
    """Launch one cell, evaluate it, derive buckets → one flat row.

    ``git_enabled`` selects the eval model: **shared-git** (agents integrate their
    own work; score the single integrated tree, graded) vs the legacy **N-way
    merge** (eval merges isolated patches).
    """
    assignment = partition_features(pool.features, n_agents, policy=partition_policy)

    run = execute_partitioned(
        repo_name=pool.repo,
        task_id=pool.task_id,
        assignment=assignment,
        run_name=_cell_run_name(pool, git_enabled),
        condition=condition,
        trial=trial,
        seed=seed,
        pool_id=pool.pool_id,
        agent_name=agent_name,
        model_name=model_name,
        redis_url=redis_url,
        message_schema=message_schema,
        git_enabled=git_enabled,
        force=force,
        backend=backend,
        agent_config=agent_config,
        dataset_dir=dataset_dir,
        logs_dir=logs_dir,
    )
    result_data = run.get("result_data") or run  # skipped path returns result.json inline
    log_dir = Path(result_data["log_dir"])
    agent_ids = sorted(assignment)

    # Idempotent eval: runs in a Docker sandbox, so re-deriving on resume is
    # expensive.  Reuse a cached eval.json unless --force.
    eval_path = log_dir / "eval.json"
    if eval_path.exists() and not force:
        eval_result = json.loads(eval_path.read_text())
    elif git_enabled:
        # Shared-git: score the integrated tree(s) the agents produced — no merge.
        agent_patches = {a: (log_dir / f"{a}.patch") for a in agent_ids}
        eval_result = score_team(
            repo_name=pool.repo,
            task_id=pool.task_id,
            feature_ids=list(pool.features),
            agent_patches=agent_patches,
            timeout=timeout,
            backend=backend,
            dataset_dir=dataset_dir,
        )
        eval_path.write_text(json.dumps(eval_result, indent=2))
    else:
        # Legacy: eval merges the isolated per-agent patches.
        patches = {a: (log_dir / f"{a}.patch") for a in agent_ids}
        eval_result = test_merged_nway(
            repo_name=pool.repo,
            task_id=pool.task_id,
            assignment=assignment,
            patches=patches,
            timeout=timeout,
            backend=backend,
            dataset_dir=dataset_dir,
            run_independent=run_independent,
        )
        eval_path.write_text(json.dumps(eval_result, indent=2))

    # Idempotent buckets (pure stream parsing, but cache for consistency + speed).
    buckets_path = log_dir / "buckets.json"
    if buckets_path.exists() and not force:
        buckets = json.loads(buckets_path.read_text())
    else:
        buckets = compute_run_buckets(log_dir, agent_ids)
        buckets_path.write_text(json.dumps(buckets, indent=2))

    return _assemble_row(pool, n_agents, condition, trial, seed, model_name, result_data, eval_result, buckets)


def _assemble_row(
    pool: Pool,
    n_agents: int,
    condition: str,
    trial: int,
    seed: int,
    model_name: str,
    result_data: dict,
    eval_result: dict,
    buckets: dict,
) -> dict:
    """Flatten one cell into a runs.csv-ready row."""
    rt = buckets.get("run_total", {})
    recoverable = buckets.get("recoverable", False)
    total_tokens = (
        rt.get("total_output", 0)
        + rt.get("total_input", 0)
        + rt.get("total_cache_read", 0)
        + rt.get("total_cache_write", 0)
    )
    merge_status = eval_result.get("merge", {}).get("status")
    git_integrated = result_data.get("git_integrated", False)
    # Graded performance — works for both eval shapes.  Shared-git eval carries a
    # ready "score"; the legacy N-way eval carries a per-feature "features" list.
    if "score" in eval_result:  # shared-git integrated scoring
        score = eval_result.get("score", 0.0)
        n_passed = eval_result.get("n_passed", 0)
        best_score = eval_result.get("best_score", "")
        all_passed = eval_result.get("all_passed", False)
    else:  # legacy N-way merge eval
        feats = eval_result.get("features", [])
        n_passed = sum(1 for f in feats if f.get("passed"))
        all_passed = eval_result.get("all_passed", False)
        score = n_passed / pool.k if pool.k else 0.0
        best_score = ""
    dollar_cost = result_data.get("total_cost", 0)
    # Dollar-denominated buckets: apportion the run's real cost by price-weighted
    # token share (additive in $).  None when unrecoverable or model unpriced.
    bucket_usd = apportion_bucket_dollars(rt, dollar_cost, model_name) if recoverable else None
    return {
        # identity
        "pool_id": pool.pool_id,
        "repo": pool.repo,
        "task_id": pool.task_id,
        "features": "_".join(str(f) for f in pool.features),
        "K": pool.k,
        "N": n_agents,
        "condition": condition,
        "trial": trial,
        "seed": seed,
        # token buckets (proxies; None-as-blank when unrecoverable)
        "context_tokens": rt.get("context_tokens") if recoverable else "",
        "task_tokens": rt.get("task_tokens") if recoverable else "",
        "comm_tokens": rt.get("comm_tokens") if recoverable else "",
        "rework_tokens": rt.get("rework_tokens") if recoverable else "",
        "buckets_recoverable": recoverable,
        # dollar-denominated buckets (apportioned; sum to dollar_cost)
        "context_usd": bucket_usd["context_usd"] if bucket_usd else "",
        "task_usd": bucket_usd["task_usd"] if bucket_usd else "",
        "comm_usd": bucket_usd["comm_usd"] if bucket_usd else "",
        "rework_usd": bucket_usd["rework_usd"] if bucket_usd else "",
        # cost
        "total_tokens": total_tokens if recoverable else "",
        "dollar_cost": dollar_cost,
        "total_steps": result_data.get("total_steps", 0),
        # outcome — graded performance is the headline for the git experiment
        "score": score,
        "n_passed": n_passed,
        "best_score": best_score,
        "all_passed": all_passed,
        "pass": all_passed,
        "git_integrated": git_integrated,
        "failure_bucket": eval_result.get("failure_bucket"),
        "merge_status": merge_status,
        # driver signals
        "messages_sent": result_data.get("messages_sent", 0),
        "message_reads": rt.get("n_messages_read", 0),
        "conflict_events": 1 if merge_status in ("conflicts", "missing_input") else 0,
        "rework_turns": rt.get("n_reedits_after_recv", 0),
        # comm breakdown (for auditing comm_tokens)
        "comm_sent_tokens": rt.get("comm_sent_tokens", 0),
        "comm_recv_tokens": rt.get("comm_recv_tokens", 0),
        "comm_reingest_tokens": rt.get("comm_reingest_tokens", 0),
    }


def _cell_run_name(pool: Pool, git_enabled: bool = False) -> str:
    """A stable run-name so re-invocation resumes (skips) completed cells.

    The git vs merge eval model gets its own log-dir tree (``_git`` suffix), so a
    shared-git run never reuses an isolated-patch run's cached cells (they produce
    fundamentally different agent artifacts).
    """
    feats = "_".join(f"f{f}" for f in pool.features)
    suffix = "_git" if git_enabled else ""
    return f"scaling_{pool.repo}_task{pool.task_id}_{feats}{suffix}"


def screen_pools(
    candidates: list[Pool],
    *,
    r_screen: int = 3,
    threshold: int = 2,
    agent_name: str = "claude_code",
    model_name: str = "claude-sonnet-5",
    backend: str = "docker",
    agent_config: str | None = None,
    dataset_dir: str | Path | None = None,
    logs_dir: str | Path | None = None,
    timeout: int = 600,
    force: bool = False,
) -> list[Pool]:
    """Keep only pools a solo (N=1) agent reliably completes.

    A pool qualifies if a single agent passes **all K** feature suites in
    ``>= threshold`` of ``r_screen`` trials.  Screen metadata (passes / trials)
    is attached to each qualified pool.
    """
    qualified: list[Pool] = []
    for pool in candidates:
        passes = 0
        for trial in range(1, r_screen + 1):
            row = _run_and_eval_cell(
                pool,
                1,
                "nocomm",
                trial,
                seed=0,
                partition_policy="round-robin",
                agent_name=agent_name,
                model_name=model_name,
                redis_url="redis://localhost:6379",
                message_schema=None,
                backend=backend,
                agent_config=agent_config,
                dataset_dir=dataset_dir,
                logs_dir=logs_dir,
                force=force,
                timeout=timeout,
                run_independent=False,
            )
            if row["all_passed"]:
                passes += 1
        console.print(f"[dim]screen[/dim] {pool.pool_id} K={pool.k}: {passes}/{r_screen}")
        if passes >= threshold:
            qualified.append(
                Pool(
                    pool.repo, pool.task_id, pool.features, pool.require, screen={"passes": passes, "trials": r_screen}
                )
            )
    return qualified


def run_experiment(
    pools: list[Pool],
    *,
    agents: list[int],
    conditions: tuple[str, ...] = DEFAULT_CONDITIONS,
    trials: int = 8,
    seed: int = 0,
    partition_policy: str = "round-robin",
    agent_name: str = "claude_code",
    model_name: str = "claude-sonnet-5",
    redis_url: str = "redis://localhost:6379",
    message_schema: dict | None = None,
    backend: str = "docker",
    agent_config: str | None = None,
    dataset_dir: str | Path | None = None,
    logs_dir: str | Path | None = None,
    out_dir: str | Path = "results_scaling",
    timeout: int = 600,
    run_independent: bool = True,
    git_enabled: bool = False,
    force: bool = False,
) -> list[dict]:
    """Sweep every ``(pool, N, condition, trial)`` cell; return + persist rows.

    Rows are streamed to ``<out_dir>/rows.jsonl`` as they complete (so a long
    sweep is crash-resilient) and returned in full.  ``analysis.py`` turns them
    into ``runs.csv`` + the fits.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "rows.jsonl"
    rows: list[dict] = []

    with rows_path.open("w") as fh:
        for pool in pools:
            for n_agents in agents:
                if n_agents > pool.k:
                    console.print(f"[yellow]skip[/yellow] {pool.pool_id}: N={n_agents} > K={pool.k}")
                    continue
                # N=1 is the solo baseline the whole curve anchors on: it has no
                # peers, so it runs exactly once (labelled nocomm) regardless of the
                # requested conditions.  N>=2 runs each requested condition.
                cell_conditions = ("nocomm",) if n_agents == 1 else conditions
                for condition in cell_conditions:
                    for trial in range(1, trials + 1):
                        row = _run_and_eval_cell(
                            pool,
                            n_agents,
                            condition,
                            trial,
                            seed=seed,
                            partition_policy=partition_policy,
                            agent_name=agent_name,
                            model_name=model_name,
                            redis_url=redis_url,
                            message_schema=message_schema,
                            backend=backend,
                            agent_config=agent_config,
                            dataset_dir=dataset_dir,
                            logs_dir=logs_dir,
                            force=force,
                            timeout=timeout,
                            run_independent=run_independent,
                            git_enabled=git_enabled,
                        )
                        rows.append(row)
                        fh.write(json.dumps(row) + "\n")
                        fh.flush()
    return rows
