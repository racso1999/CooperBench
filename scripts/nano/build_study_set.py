"""Build the final nano study set from the solo-screening results.

The set is the coordination-limited Python pairs discovered by screening:
  * every task with a solo-both-solvable pair -> one pair each (prefer a pair we
    already have no-messaging control data for), and
  * two per-feature-viable additions (dottxt/1655 [8,10], hf/3997 [1,5]) — tasks
    solo can't do *both* features at once, but whose features are each doable
    individually, so coordination could plausibly succeed.

Writes dataset/subsets/nano.json — 20 pairs across 20 distinct tasks.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
OUT = ROOT / "dataset" / "subsets" / "nano.json"

SOLO_RUNS = ["nano_solo_1", "nano_pool_solo_1", "nano_pool2_solo_1", "nano_pool3_solo_1"]
CONTROL_RUN = "nano_nomsg_1"
# per-feature-viable additions (task solo-unsolvable but each feature doable)
ADDITIONS = [("dottxt_ai_outlines_task", 1655, [8, 10]),
             ("huggingface_datasets_task", 3997, [1, 5])]


def _pairs_from(run: str, both_only: bool) -> set:
    out = set()
    for f in glob.glob(str(LOGS / run / "**" / "eval.json"), recursive=True):
        e = json.loads(Path(f).read_text())
        if not both_only or e.get("both_passed"):
            out.add((e["repo"], e["task_id"], tuple(e["features"])))
    return out


def main() -> None:
    have_control = {(r, t, tuple(p)) for r, t, p in _pairs_from(CONTROL_RUN, both_only=False)}

    solvable_by_task: dict[tuple[str, int], list[tuple]] = {}
    for run in SOLO_RUNS:
        for r, t, feats in _pairs_from(run, both_only=True):
            solvable_by_task.setdefault((r, t), []).append(feats)

    tasks = []
    for (repo, tid), pairs in sorted(solvable_by_task.items()):
        pick = next((p for p in pairs if (repo, tid, p) in have_control), sorted(pairs)[0])
        tasks.append({"repo": repo, "task_id": tid, "pairs": [list(pick)]})
    for repo, tid, pair in ADDITIONS:
        tasks.append({"repo": repo, "task_id": tid, "pairs": [pair]})

    tasks.sort(key=lambda t: (t["repo"], t["task_id"]))
    doc = {
        "name": "nano",
        "description": (
            f"Single-language (Python) coordination benchmark: {len(tasks)} pairs across "
            f"{len(tasks)} distinct tasks ({len({t['repo'] for t in tasks})} repos), one pair per task. "
            "Every pair is coordination-limited: gold merge-conflict, and each feature is "
            "individually implementable by sonnet-5 (from solo screening) so a communication "
            "protocol can plausibly help. Capability-floored tasks (no feature solvable solo) "
            "were excluded. See docs/nano_py_preregistration.md."
        ),
        "stats": {"pairs": len(tasks), "tasks": len(tasks),
                  "repos": len({t["repo"] for t in tasks})},
        "tasks": tasks,
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(tasks)} pairs, {doc['stats']['repos']} repos")
    for t in tasks:
        print(f"  {t['repo'].replace('_task',''):26s} task{t['task_id']:<7} {t['pairs'][0]}")


if __name__ == "__main__":
    main()
