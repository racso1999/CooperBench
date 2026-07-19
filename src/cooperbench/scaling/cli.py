"""``cooperbench scaling`` subcommand — the whole scaling experiment gate.

The subcommand *is* the ``--scaling-experiment`` flag: nothing here runs unless
``scaling`` is invoked, so the base ``run`` / ``eval`` paths are untouched.

Modes:
* ``--screen-pools``  : screen candidate pools with solo N=1, write a manifest.
* ``--analyze-only``  : (re)build runs.csv + fits from an existing rows.jsonl.
* default             : sweep every (pool, N, condition, trial) cell, then analyse.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cooperbench.scaling import analysis, experiment, pools
from cooperbench.utils import console


def add_scaling_parser(subparsers) -> None:
    """Register the ``scaling`` subcommand on the top-level argparse tree."""
    p = subparsers.add_parser(
        "scaling",
        help="Agent-count scaling experiment (opt-in, flag-gated)",
        description="Measure how coordination cost scales with the number of agents "
        "while the K-feature workload is held constant.",
    )
    p.add_argument(
        "--agents", default="1,2,3,4", help="Agent counts to sweep, e.g. '1,2,3,4' or '3' (default: 1,2,3,4)"
    )
    p.add_argument(
        "--features",
        type=int,
        default=4,
        help="K: fixed workload size (features per pool). Needs K >= max(--agents). Default 4.",
    )
    p.add_argument(
        "--partition",
        default="round-robin",
        choices=["round-robin"],
        help="Partition policy (only round-robin for now)",
    )
    p.add_argument("--comm", action="store_true", help="Run the comm condition")
    p.add_argument("--no-comm", dest="no_comm", action="store_true", help="Run the no-comm condition")
    p.add_argument("--trials", type=int, default=8, help="Trials per (pool,N,condition) cell (default 8)")
    p.add_argument("--seed", type=int, default=0, help="Selection/partition seed (provenance; default 0)")
    p.add_argument("--seeds", default=None, help="Comma list of seeds (overrides --seed; loops each)")
    p.add_argument(
        "--require",
        default=pools.REQUIRE_CLIQUE,
        choices=[pools.REQUIRE_CLIQUE, pools.REQUIRE_CONNECTED],
        help="Interdependence strength for pool selection (default clique)",
    )
    # candidate-set / pool selection
    p.add_argument("--subset", default=None, help="Restrict candidate tasks to this subset (e.g. flash)")
    p.add_argument("--repos", default=None, help="Comma list of repos to restrict candidate tasks")
    p.add_argument("--pool", default=None, help="Run a single pool by its pool_id")
    p.add_argument("--pools", default=None, help="Comma list of pool_ids to run")
    p.add_argument("--manifest", default=None, help="Path to a pools manifest (from --screen-pools)")
    # modes
    p.add_argument(
        "--screen-pools",
        dest="screen_pools",
        action="store_true",
        help="Screen candidate pools with solo N=1 and write a manifest; do not sweep",
    )
    p.add_argument("--r-screen", dest="r_screen", type=int, default=3, help="Screening trials (default 3)")
    p.add_argument(
        "--screen-threshold",
        dest="screen_threshold",
        type=int,
        default=2,
        help="Passes-out-of-r_screen to qualify (default 2)",
    )
    p.add_argument(
        "--analyze-only",
        dest="analyze_only",
        action="store_true",
        help="Only (re)build runs.csv + fits from <out>/rows.jsonl",
    )
    # execution
    p.add_argument("-a", "--agent", default="claude_code", help="Agent framework (default claude_code)")
    p.add_argument("-m", "--model", default="claude-sonnet-5", help="Model (default claude-sonnet-5)")
    p.add_argument("--backend", choices=["modal", "docker", "gcp"], default="docker")
    p.add_argument(
        "--git",
        action="store_true",
        help="Shared-git integration: agents merge peers on a shared repo and eval "
        "scores the single integrated tree (graded), instead of eval merging isolated patches.",
    )
    p.add_argument("--redis", default="redis://localhost:6379")
    p.add_argument("--agent-config", default=None)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument(
        "--no-independent",
        dest="no_independent",
        action="store_true",
        help="Skip the pre-merge per-feature capability check",
    )
    p.add_argument("--dataset-dir", default=None)
    p.add_argument("--log-dir", default=None)
    p.add_argument("--out", default="results_scaling", help="Output dir for rows/csv/analysis + manifest")


def _candidate_tasks(args) -> set[tuple[str, int]] | None:
    """Resolve the (repo, task_id) candidate set from --subset / --repos (or all)."""
    tasks: set[tuple[str, int]] | None = None
    if args.subset:
        from cooperbench.runner.tasks import load_subset

        data = load_subset(args.subset, dataset_dir=args.dataset_dir)
        tasks = set(data["tasks"])
    if args.repos:
        repos = {r.strip() for r in args.repos.split(",")}
        if tasks is None:
            # need the full graph to enumerate repo tasks
            graph = pools.load_conflict_graph(dataset_dir=args.dataset_dir)
            tasks = {k for k in graph if k[0] in repos}
        else:
            tasks = {k for k in tasks if k[0] in repos}
    return tasks


def _resolve_pools(args) -> list[pools.Pool]:
    """Pool list for a sweep: manifest, explicit ids, or fresh selection."""
    if args.manifest:
        pool_list = pools.load_manifest(args.manifest)
    else:
        tasks = _candidate_tasks(args)
        pool_list = pools.find_candidate_pools(
            args.features, tasks=tasks, require=args.require, dataset_dir=args.dataset_dir
        )
    ids = None
    if args.pool:
        ids = {args.pool}
    elif args.pools:
        ids = {x.strip() for x in args.pools.split(",")}
    if ids is not None:
        pool_list = [p for p in pool_list if p.pool_id in ids]
    return pool_list


def _conditions(args) -> tuple[str, ...]:
    if args.comm and not args.no_comm:
        return ("comm",)
    if args.no_comm and not args.comm:
        return ("nocomm",)
    return experiment.DEFAULT_CONDITIONS


def scaling_command(args) -> None:
    """Dispatch the ``scaling`` subcommand."""
    out = Path(args.out)

    if args.analyze_only:
        rows_path = out / "rows.jsonl"
        if not rows_path.exists():
            print(f"error: {rows_path} not found (nothing to analyze)", file=sys.stderr)
            sys.exit(1)
        result = analysis.run_analysis(rows_path, out)
        console.print(f"[green]analysis[/green] {result['n_runs']} runs → {out / 'runs.csv'}")
        _print_headline(result)
        return

    agents = [int(x) for x in str(args.agents).split(",") if x.strip()]

    if args.screen_pools:
        tasks = _candidate_tasks(args)
        candidates = pools.find_candidate_pools(
            args.features, tasks=tasks, require=args.require, dataset_dir=args.dataset_dir
        )
        console.print(f"[dim]screening[/dim] {len(candidates)} candidate pools (K={args.features})")
        qualified = experiment.screen_pools(
            candidates,
            r_screen=args.r_screen,
            threshold=args.screen_threshold,
            agent_name=args.agent,
            model_name=args.model,
            backend=args.backend,
            agent_config=args.agent_config,
            dataset_dir=args.dataset_dir,
            logs_dir=args.log_dir,
            timeout=args.timeout,
        )
        manifest_path = out / "pools.json"
        pools.write_manifest(
            manifest_path,
            qualified,
            meta={
                "features": args.features,
                "require": args.require,
                "r_screen": args.r_screen,
                "threshold": args.screen_threshold,
            },
        )
        console.print(f"[green]qualified[/green] {len(qualified)}/{len(candidates)} → {manifest_path}")
        return

    pool_list = _resolve_pools(args)
    if not pool_list:
        print("error: no pools resolved (check --features / --subset / --manifest / --pool)", file=sys.stderr)
        sys.exit(1)
    if max(agents) > min(p.k for p in pool_list):
        print(
            f"error: --agents max {max(agents)} exceeds smallest pool K {min(p.k for p in pool_list)}",
            file=sys.stderr,
        )
        sys.exit(1)

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else [args.seed]
    conditions = _conditions(args)
    console.print(
        f"[bold]scaling[/bold] pools={len(pool_list)} agents={agents} conditions={conditions} "
        f"trials={args.trials} seeds={seeds}"
    )

    all_rows: list[dict] = []
    for seed in seeds:
        rows = experiment.run_experiment(
            pool_list,
            agents=agents,
            conditions=conditions,
            trials=args.trials,
            seed=seed,
            partition_policy=args.partition,
            agent_name=args.agent,
            model_name=args.model,
            redis_url=args.redis,
            backend=args.backend,
            agent_config=args.agent_config,
            dataset_dir=args.dataset_dir,
            logs_dir=args.log_dir,
            out_dir=out,
            timeout=args.timeout,
            run_independent=not args.no_independent,
            git_enabled=args.git,
        )
        all_rows.extend(rows)

    result = analysis.run_analysis(all_rows, out)
    console.print(f"[green]done[/green] {len(all_rows)} runs → {out / 'runs.csv'}")
    _print_headline(result)


def _print_headline(result: dict) -> None:
    # Graded performance vs N — the headline for the shared-git experiment.
    curve = result.get("performance_curve") or {}
    if curve:
        console.print("[dim]performance vs N (mean score / all-pass rate / mean $):[/dim]")
        for n in sorted(curve, key=int):
            c = curve[n]
            ms = f"{c['mean_score']:.2f}" if c.get("mean_score") is not None else "n/a"
            ap = f"{c['all_passed_rate']:.2f}" if c.get("all_passed_rate") is not None else "n/a"
            mc = f"${c['mean_cost']:.2f}" if c.get("mean_cost") is not None else "n/a"
            console.print(f"  N={n}: score={ms} all_pass={ap} cost={mc} (n={c['n_runs']})")
    # comm_fit + tax_fit are the sharper superlinearity signals (the total-cost
    # fit is diluted by the linear context floor); print all three.
    for key, label in (
        ("comm_fit", "comm$(N)"),
        ("tax_fit", "tax(N)"),
        ("cost_fit_comm", "cost(N) comm"),
    ):
        fit = result.get(key, {})
        if "beta" in fit:
            ci = [round(x, 4) if x == x else "nan" for x in fit["beta_ci95"]]
            console.print(
                f"[dim]{label}=aN+bN^2:[/dim] a={fit['alpha']:.4f} b={fit['beta']:.4f} "
                f"CI95={ci} R2={fit['r2']:.3f} superlinear={fit['beta_superlinear']} "
                f"(n={fit['n']},dof={fit['dof']},{fit['crit_method']})"
            )
        else:
            console.print(f"[dim]{label}:[/dim] {fit.get('error', 'n/a')}")
