"""Build a 30-pair *extension* candidate pool for solo capability screening.

Draws 30 gold-conflict Python pairs that are NOT already in nano.json, ranked by
static feature-overlap (same proxy as select_pairs.py), with a per-task cap so no
single task dominates. Output feeds a solo run: pairs whose solo pass-rate is
high enough join the study pool alongside the already-screened nano pairs.
"""

from __future__ import annotations

import json
from pathlib import Path

from select_pairs import PY_REPOS, score_pair  # reuse the same scoring

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"
OUT = DATASET / "subsets" / "nano_pool_ext.json"

N = 30
PER_TASK_CAP = 2  # allow up to 2 new pairs per task (24 tasks -> room for 30)


def main() -> None:
    report = json.loads((DATASET / "gold_conflict_report.json").read_text())
    conflicts = [e for e in report["conflict_pairs"] if e["repo"] in PY_REPOS]

    # exclude pairs already in nano.json
    nano = json.loads((DATASET / "subsets" / "nano.json").read_text())
    used = {(t["repo"], t["task_id"], frozenset(t["pairs"][0])) for t in nano["tasks"]}

    scored = []
    for e in conflicts:
        repo, tid, fa, fb = e["repo"], e["task_id"], e["f1"], e["f2"]
        if (repo, tid, frozenset((fa, fb))) in used:
            continue
        sc, size = score_pair(repo, tid, fa, fb)
        scored.append({"repo": repo, "task_id": tid, "pair": [fa, fb], "score": sc,
                       "med": -abs(size - 120), "size": size})

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

    # Group by task into a single entry each (the subset loader keys pairs by
    # (repo, task_id), so multiple same-task entries would overwrite).
    grouped: dict[tuple[str, int], list[list[int]]] = {}
    order: list[tuple[str, int]] = []
    for r in picked:
        key = (r["repo"], r["task_id"])
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(r["pair"])

    doc = {
        "name": "nano_pool_ext",
        "description": (
            f"{len(picked)}-pair extension pool for solo capability screening "
            f"(gold-conflict Python pairs not in nano, ranked by feature-overlap, "
            f"<= {PER_TASK_CAP}/task). Run solo to find individually-solvable candidates."
        ),
        "stats": {"pairs": len(picked), "repos": len({r["repo"] for r in picked}),
                  "tasks": len(grouped)},
        "tasks": [{"repo": repo, "task_id": tid, "pairs": grouped[(repo, tid)]} for repo, tid in order],
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(picked)} pairs, "
          f"{doc['stats']['tasks']} tasks, {doc['stats']['repos']} repos")
    for r in picked:
        print(f"  {r['repo'].replace('_task',''):26s} task{r['task_id']:<6} f{r['pair']}  overlap={r['score']} size={r['size']}")


if __name__ == "__main__":
    main()
