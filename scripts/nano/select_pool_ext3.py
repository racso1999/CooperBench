"""Third screen — exhaust the not-yet-solvable tasks to chase 20 distinct.

Targets every Python task that still has no solo-solvable pair, with fresh
untested gold-conflict pairs (up to N per task), ranked by SMALL patch size
(simpler pairs are likelier to be solved solo). Run solo; any task that cracks
becomes a new independent cluster for the 20-task study set.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from select_pairs import PY_REPOS, score_pair

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"
LOGS = ROOT / "logs"
OUT = DATASET / "subsets" / "nano_pool_ext3.json"

PER_TASK = 4
SOLO_RUNS = ["nano_solo_1", "nano_pool_solo_1", "nano_pool2_solo_1"]
SCREENED_SUBSETS = ["nano", "nano_pool_ext", "nano_pool_ext2"]


def main() -> None:
    report = json.loads((DATASET / "gold_conflict_report.json").read_text())
    conflicts = [e for e in report["conflict_pairs"] if e["repo"] in PY_REPOS]

    screened = set()
    for name in SCREENED_SUBSETS:
        for t in json.loads((DATASET / "subsets" / f"{name}.json").read_text())["tasks"]:
            for p in t["pairs"]:
                screened.add((t["repo"], t["task_id"], frozenset(p)))

    solvable = set()
    all_tasks = set()
    for run in SOLO_RUNS:
        for f in glob.glob(str(LOGS / run / "**" / "eval.json"), recursive=True):
            e = json.loads(Path(f).read_text())
            if e.get("both_passed"):
                solvable.add((e["repo"], e["task_id"]))
    for e in conflicts:
        all_tasks.add((e["repo"], e["task_id"]))
    unsolved = all_tasks - solvable

    # fresh untested pairs from unsolved tasks, smallest-first (solvability heuristic)
    cand = []
    for e in conflicts:
        key = (e["repo"], e["task_id"])
        if key in solvable:
            continue
        if (e["repo"], e["task_id"], frozenset((e["f1"], e["f2"]))) in screened:
            continue
        _, size = score_pair(e["repo"], e["task_id"], e["f1"], e["f2"])
        cand.append({"repo": e["repo"], "task_id": e["task_id"], "pair": [e["f1"], e["f2"]], "size": size})

    cand.sort(key=lambda r: r["size"])  # smaller = simpler = likelier solvable
    per_task, grouped, order = {}, {}, []
    for r in cand:
        key = (r["repo"], r["task_id"])
        if per_task.get(key, 0) >= PER_TASK:
            continue
        per_task[key] = per_task.get(key, 0) + 1
        grouped.setdefault(key, []).append(r["pair"])
        if key not in order:
            order.append(key)

    doc = {
        "name": "nano_pool_ext3",
        "description": (
            f"Exhaustive screen of the {len(unsolved)} not-yet-solvable Python tasks: "
            f"fresh untested gold-conflict pairs (<= {PER_TASK}/task, smallest-first). "
            f"Run solo to find new solvable tasks toward 20 distinct clusters."
        ),
        "stats": {"pairs": sum(len(v) for v in grouped.values()), "tasks": len(grouped)},
        "tasks": [{"repo": r, "task_id": t, "pairs": grouped[(r, t)]} for r, t in order],
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"unsolved tasks: {len(unsolved)}  -> screening {len(grouped)} of them")
    print(f"wrote {OUT.relative_to(ROOT)}: {doc['stats']['pairs']} pairs\n")
    for r, t in order:
        print(f"  {r.replace('_task',''):26s} task{t:<7} pairs={grouped[(r, t)]}")
    uncovered = unsolved - set(order)
    if uncovered:
        print(f"\n  NOTE: no fresh pairs left to try for: {sorted(uncovered)}")


if __name__ == "__main__":
    main()
