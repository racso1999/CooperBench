"""Second extension pool — target tasks that don't yet have a solo-solvable pair.

Goal: maximise the number of distinct solo-solvable TASKS (independent clusters).
Reads what we've already screened (nano + nano_pool_ext) and which tasks are
already solvable (from the solo eval logs), then picks fresh, untested pairs
from the not-yet-solvable tasks (including any never screened), ranked by
feature-overlap. Run solo to see which of those tasks become solvable.
"""

from __future__ import annotations

import json
from pathlib import Path

from select_pairs import PY_REPOS, score_pair

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"
LOGS = ROOT / "logs"
OUT = DATASET / "subsets" / "nano_pool_ext2.json"

N = 30
PER_TASK_CAP = 3
SOLO_RUNS = ["nano_solo_1", "nano_pool_solo_1"]
SCREENED_SUBSETS = ["nano", "nano_pool_ext"]


def _screened_pairs() -> set:
    used = set()
    for name in SCREENED_SUBSETS:
        d = json.loads((DATASET / "subsets" / f"{name}.json").read_text())
        for t in d["tasks"]:
            for p in t["pairs"]:
                used.add((t["repo"], t["task_id"], frozenset(p)))
    return used


def _solvable_tasks() -> set:
    import glob
    solvable = set()
    for run in SOLO_RUNS:
        for f in glob.glob(str(LOGS / run / "**" / "eval.json"), recursive=True):
            e = json.loads(Path(f).read_text())
            if e.get("both_passed"):
                solvable.add((e["repo"], e["task_id"]))
    return solvable


def main() -> None:
    report = json.loads((DATASET / "gold_conflict_report.json").read_text())
    conflicts = [e for e in report["conflict_pairs"] if e["repo"] in PY_REPOS]
    screened = _screened_pairs()
    solvable = _solvable_tasks()

    # candidate = untested conflict pair whose TASK is not yet solvable
    scored = []
    for e in conflicts:
        repo, tid, fa, fb = e["repo"], e["task_id"], e["f1"], e["f2"]
        if (repo, tid) in solvable:
            continue  # task already has a solvable pair — don't need more here
        if (repo, tid, frozenset((fa, fb))) in screened:
            continue
        sc, size = score_pair(repo, tid, fa, fb)
        scored.append({"repo": repo, "task_id": tid, "pair": [fa, fb],
                       "score": sc, "med": -abs(size - 120)})

    scored.sort(key=lambda r: (r["score"], r["med"]), reverse=True)
    picked, per_task = [], {}
    for r in scored:
        key = (r["repo"], r["task_id"])
        if per_task.get(key, 0) >= PER_TASK_CAP:
            continue
        picked.append(r)
        per_task[key] = per_task.get(key, 0) + 1
        if len(picked) >= N:
            break

    grouped, order = {}, []
    for r in picked:
        key = (r["repo"], r["task_id"])
        if key not in grouped:
            grouped[key] = []; order.append(key)
        grouped[key].append(r["pair"])

    doc = {
        "name": "nano_pool_ext2",
        "description": (
            f"{len(picked)}-pair pool targeting not-yet-solvable tasks, to grow the "
            f"count of distinct solo-solvable tasks. Fresh untested gold-conflict pairs "
            f"(<= {PER_TASK_CAP}/task), ranked by feature-overlap. Run solo."
        ),
        "stats": {"pairs": len(picked), "tasks": len(grouped),
                  "repos": len({k[0] for k in grouped})},
        "tasks": [{"repo": r, "task_id": t, "pairs": grouped[(r, t)]} for r, t in order],
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"already-solvable tasks: {len(solvable)}  |  targeting {len(grouped)} not-yet-solvable tasks")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(picked)} pairs across {len(grouped)} tasks\n")
    for r, t in order:
        print(f"  {r.replace('_task',''):26s} task{t:<6} pairs={grouped[(r, t)]}")


if __name__ == "__main__":
    main()
