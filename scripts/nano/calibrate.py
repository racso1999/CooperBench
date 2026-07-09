"""Data-driven calibration screen that turns candidates into the final nano-py.

Pre-registered rule (fixed BEFORE looking at any result):

  For each candidate task we estimate two rates over k replicate runs on the
  target model:

    solo_rate   = P(both features pass | ONE agent, full context, no coordination)
                  -> capability.  If this is low the task is CAPABILITY-limited
                     (the model just can't write the features); a communication
                     protocol cannot help, so we EXCLUDE it.

    nomsg_rate  = P(both features pass | two agents, --no-messaging)
                  -> what the naive, un-coordinated merge achieves.  If this is
                     high the conflict does not actually bite (nothing to
                     coordinate); we EXCLUDE it (ceiling).

  KEEP a task iff  solo_rate >= SOLO_MIN  AND  nomsg_rate <= NOMSG_MAX.
  Kept tasks are ranked by headroom = solo_rate - nomsg_rate (the room a
  protocol has to work in) and capped per repo to keep clusters independent.
  We never look at any *with-messaging* protocol outcome here -- selecting on
  the dependent variable would be circular.

Usage:
  # 1. see the plan + cost/time envelope, run nothing
  python scripts/nano/calibrate.py plan --k 6

  # 2. execute the screen (long, costs money) -- runs on the target model
  python scripts/nano/calibrate.py run --k 6 --model claude-sonnet-5

  # 3. read the logs and emit dataset/subsets/nano_py.json + a report
  python scripts/nano/calibrate.py select --k 6

`run` and `select` are separate so a crashed/partial run can be re-read, and so
you can eyeball the report before the final subset is written.  `--limit N` and
`--k` let you smoke-test the plumbing cheaply before committing to the full k.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = "nano_py_candidates"  # subset name under dataset/subsets/
OUT_SUBSET = ROOT / "dataset" / "subsets" / "nano_py.json"
REPORT = ROOT / "scripts" / "nano" / "calibration_report.json"

# Pre-registered thresholds.
SOLO_MIN = 0.60     # must be solo-solvable at least this often (capability)
NOMSG_MAX = 0.50    # naive no-messaging merge must fail at least half the time
FINAL_TARGET = 15   # aim for ~12-15 final pairs
PER_REPO_CAP = 2    # keep clusters independent; no repo dominates

CONDITIONS = {
    "solo": ["--setting", "solo"],
    "nomsg": ["--setting", "coop", "--no-messaging"],
}


def _candidate_tasks() -> list[dict]:
    data = json.loads((ROOT / "dataset" / "subsets" / f"{CANDIDATES}.json").read_text())
    return data["tasks"]


def _run_name(cond: str, i: int) -> str:
    return f"calib_{cond}_k{i}"


def cmd_plan(args) -> None:
    tasks = _candidate_tasks()[: args.limit] if args.limit else _candidate_tasks()
    n = len(tasks)
    invocations = 2 * args.k
    solo_agent_runs = args.k * n            # 1 agent per solo pair
    nomsg_agent_runs = args.k * n * 2       # 2 agents per coop pair
    total_agent_runs = solo_agent_runs + nomsg_agent_runs
    # rough per-agent cost band observed for sonnet-tier claude_code coop work
    lo, hi = 0.15, 0.90
    print(f"candidates:            {n} tasks")
    print(f"replicates (k):        {args.k}")
    print(f"cooperbench runs:      {invocations}  ({args.k} solo + {args.k} nomsg, each over {n} tasks)")
    print(f"agent-runs total:      {total_agent_runs}  (solo {solo_agent_runs} + nomsg {nomsg_agent_runs})")
    print(f"est. cost band:        ${total_agent_runs*lo:,.0f} - ${total_agent_runs*hi:,.0f}  (sonnet-5, very rough)")
    print(f"concurrency:           {args.concurrency}  ->  ~{invocations} sequential invocations")
    print()
    print("thresholds (pre-registered):")
    print(f"  keep iff solo_rate >= {SOLO_MIN} and nomsg_rate <= {NOMSG_MAX}")
    print(f"  final target ~{FINAL_TARGET} pairs, <= {PER_REPO_CAP} per repo, ranked by headroom")


def cmd_run(args) -> None:
    tasks = _candidate_tasks()
    limit = args.limit or len(tasks)
    for cond, flags in CONDITIONS.items():
        for i in range(args.k):
            name = _run_name(cond, i)
            cmd = [
                "uv", "run", "cooperbench", "run",
                "-n", name,
                "--subset", CANDIDATES,
                "-a", "claude_code",
                "-m", args.model,
                "-c", str(args.concurrency),
                "--force",
                *flags,
            ]
            # --limit is a smoke-test convenience: restrict to the first N repos
            # by filtering with -r when N==1; otherwise rely on the full subset.
            if limit == 1:
                cmd += ["-r", tasks[0]["repo"], "-t", str(tasks[0]["task_id"])]
            print(">>", " ".join(cmd), flush=True)
            if args.dry_run:
                continue
            rc = subprocess.run(cmd, cwd=ROOT).returncode
            if rc != 0:
                print(f"!! run {name} exited {rc}", file=sys.stderr)


def _rate(cond: str, k: int, repo: str, task_id: int) -> tuple[float, float, int]:
    """Return (both_pass_rate, merge_conflict_rate, n_seen) over k replicate runs."""
    passes = conflicts = seen = 0
    for i in range(k):
        pat = str(ROOT / "logs" / _run_name(cond, i) / "**" / f"{repo}" / str(task_id) / "**" / "eval.json")
        for f in glob.glob(pat, recursive=True):
            try:
                e = json.loads(Path(f).read_text())
            except Exception:
                continue
            seen += 1
            if e.get("both_passed"):
                passes += 1
            if (e.get("merge") or {}).get("status") == "conflict":
                conflicts += 1
    if seen == 0:
        return (float("nan"), float("nan"), 0)
    return (passes / seen, conflicts / seen, seen)


def cmd_select(args) -> None:
    tasks = _candidate_tasks()
    rows = []
    for t in tasks:
        repo, tid = t["repo"], t["task_id"]
        solo_rate, _, solo_n = _rate("solo", args.k, repo, tid)
        nomsg_rate, conflict_rate, nomsg_n = _rate("nomsg", args.k, repo, tid)
        keep = (
            solo_n > 0 and nomsg_n > 0
            and solo_rate >= SOLO_MIN
            and nomsg_rate <= NOMSG_MAX
        )
        rows.append({
            "repo": repo, "task_id": tid, "pair": t["pairs"][0],
            "solo_rate": solo_rate, "solo_n": solo_n,
            "nomsg_rate": nomsg_rate, "nomsg_n": nomsg_n,
            "merge_conflict_rate": conflict_rate,
            "headroom": (solo_rate - nomsg_rate) if solo_n and nomsg_n else float("nan"),
            "eligible": keep,
        })

    eligible = [r for r in rows if r["eligible"]]
    eligible.sort(key=lambda r: r["headroom"], reverse=True)
    selected, per_repo = [], {}
    for r in eligible:
        if per_repo.get(r["repo"], 0) >= PER_REPO_CAP:
            continue
        selected.append(r)
        per_repo[r["repo"]] = per_repo.get(r["repo"], 0) + 1
        if len(selected) >= FINAL_TARGET:
            break

    REPORT.write_text(json.dumps({"k": args.k, "thresholds": {"solo_min": SOLO_MIN, "nomsg_max": NOMSG_MAX},
                                  "rows": rows, "selected": [(r["repo"], r["task_id"]) for r in selected]},
                                 indent=2) + "\n")

    print(f"{'repo':32s} {'task':>6} {'pair':>8} {'solo':>6} {'nomsg':>6} {'head':>6} keep")
    for r in sorted(rows, key=lambda r: (r["repo"], r["task_id"])):
        mark = "SEL" if r in selected else ("ok" if r["eligible"] else "-")
        sr = "  n/a" if r["solo_n"] == 0 else f"{r['solo_rate']:5.0%}"
        nr = "  n/a" if r["nomsg_n"] == 0 else f"{r['nomsg_rate']:5.0%}"
        hd = "  n/a" if r["solo_n"] == 0 or r["nomsg_n"] == 0 else f"{r['headroom']:5.0%}"
        print(f"{r['repo']:32s} {r['task_id']:>6} {str(r['pair']):>8} {sr} {nr} {hd}  {mark}")
    print(f"\nselected {len(selected)} pairs")

    if not selected:
        print("no eligible pairs yet (have you run the screen?) -- not writing nano_py.json")
        return

    doc = {
        "name": "nano_py",
        "description": (
            f"Data-selected single-language (Python) coordination benchmark. "
            f"{len(selected)} gold-conflict pairs, one per task, chosen by the "
            f"pre-registered screen: solo_rate>={SOLO_MIN} (capability present) and "
            f"nomsg_rate<={NOMSG_MAX} (naive merge fails), ranked by headroom, "
            f"<= {PER_REPO_CAP}/repo. Calibrated on {args.model if hasattr(args,'model') else 'target model'} "
            f"at k={args.k}. See scripts/nano/calibration_report.json."
        ),
        "stats": {"pairs": len(selected), "repos": len({r["repo"] for r in selected})},
        "tasks": [{"repo": r["repo"], "task_id": r["task_id"], "pairs": [r["pair"]]} for r in selected],
    }
    OUT_SUBSET.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {OUT_SUBSET.relative_to(ROOT)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="phase", required=True)
    for phase in ("plan", "run", "select"):
        sp = sub.add_parser(phase)
        sp.add_argument("--k", type=int, default=6, help="replicate runs per condition (default 6)")
        sp.add_argument("--model", default="claude-sonnet-5")
        sp.add_argument("--concurrency", type=int, default=4)
        sp.add_argument("--limit", type=int, default=0, help="smoke-test: restrict to first N candidate tasks")
        sp.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    {"plan": cmd_plan, "run": cmd_run, "select": cmd_select}[args.phase](args)


if __name__ == "__main__":
    main()
