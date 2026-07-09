"""Enumerate the nano-py sampling frame and emit a seeded candidate shortlist.

Scientific intent (pre-registered): the final nano-py pairs must be selected on
*data* (the calibration screen), not by hand.  This script builds the frame
those data are collected over:

  * population   = every gold merge-conflict pair in a Python repo
  * cluster unit = a task (a repo frozen at one base commit)
  * candidate    = exactly ONE conflicting pair per task, chosen with a fixed
                   seed, so tasks stay independent clusters and no task is
                   over-represented.

The output (`nano_py_candidates.json`) is the input to `calibrate.py`, which
runs the solo + no-messaging screens and drops floor/ceiling tasks to produce
the final `nano_py.json`.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parents[2]
CONFLICT_REPORT = ROOT / "dataset" / "gold_conflict_report.json"
OUT = ROOT / "dataset" / "subsets" / "nano_py_candidates.json"

PY_REPOS = {
    "dottxt_ai_outlines_task",
    "dspy_task",
    "huggingface_datasets_task",
    "llama_index_task",
    "openai_tiktoken_task",
    "pallets_click_task",
    "pallets_jinja_task",
    "pillow_task",
    "samuelcolvin_dirty_equals_task",
}


def main() -> None:
    report = json.loads(CONFLICT_REPORT.read_text())
    conflicts = [e for e in report["conflict_pairs"] if e["repo"] in PY_REPOS]

    by_task: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for e in conflicts:
        key = (e["repo"], e["task_id"])
        by_task.setdefault(key, []).append((e["f1"], e["f2"]))

    rng = random.Random(SEED)
    tasks = []
    # Deterministic order, then one seeded pair per task.
    for repo, task_id in sorted(by_task):
        pairs = sorted(by_task[(repo, task_id)])
        f1, f2 = rng.choice(pairs)
        tasks.append({"repo": repo, "task_id": task_id, "pairs": [[f1, f2]]})

    doc = {
        "name": "nano_py_candidates",
        "description": (
            "Pre-calibration candidate frame for nano-py: one seeded gold-conflict "
            "pair per Python task (seed=42). NOT the final subset — feed to "
            "scripts/nano/calibrate.py, which drops floor/ceiling tasks via the "
            "solo + no-messaging screen and balances repos to produce nano_py.json."
        ),
        "seed": SEED,
        "selection": "one conflicting pair per task, uniform-random within task, seed=42",
        "stats": {
            "candidates": len(tasks),
            "repos": len({t["repo"] for t in tasks}),
        },
        "tasks": tasks,
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"candidates: {len(tasks)} tasks across {doc['stats']['repos']} repos")
    per_repo: dict[str, int] = {}
    for t in tasks:
        per_repo[t["repo"]] = per_repo.get(t["repo"], 0) + 1
    for repo in sorted(per_repo):
        print(f"  {repo:34s} {per_repo[repo]}")


if __name__ == "__main__":
    main()
