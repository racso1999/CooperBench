"""Free, offline selection of nano-py pairs — no runs, no cost.

Ranks every Python gold-conflict pair by how much the two features actually
overlap in the code (a static proxy for "will the conflict bite"), then picks
one pair per task across the highest-overlap tasks.  This is a *pre-filter* to
raise the hit-rate; the real validation is post-hoc, from the k=20 study's own
no-messaging control (see docs/nano_py_preregistration.md).

Overlap score for a pair (fa, fb):
  * parse each feature's feature.patch -> {file: [new-line hunk ranges]}
  * shared_files          = files edited by BOTH features
  * overlapping_files     = shared files whose hunk ranges intersect (<=5 lines)
  * score = 3*overlapping_files + (shared_files - overlapping_files)
  * size  = total changed lines (tie-break toward medium, not trivial/huge)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SEED = 42
N_FINAL = 20
PER_REPO_CAP = 3
ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"
CONFLICT_REPORT = DATASET / "gold_conflict_report.json"
OUT = DATASET / "subsets" / "nano.json"

PY_REPOS = {
    "dottxt_ai_outlines_task", "dspy_task", "huggingface_datasets_task",
    "llama_index_task", "openai_tiktoken_task", "pallets_click_task",
    "pallets_jinja_task", "pillow_task", "samuelcolvin_dirty_equals_task",
}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_patch(path: Path) -> tuple[dict[str, list[tuple[int, int]]], int]:
    files: dict[str, list[tuple[int, int]]] = {}
    changed = 0
    cur = None
    if not path.exists():
        return files, 0
    for line in path.read_text(errors="ignore").splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            files.setdefault(cur, [])
        elif line.startswith("@@"):
            m = HUNK.match(line)
            if m and cur is not None:
                start = int(m.group(1))
                length = int(m.group(2) or 1)
                files[cur].append((start, start + max(length, 1) - 1))
        elif line and line[0] in "+-" and not line.startswith(("+++", "---")):
            changed += 1
    return files, changed


def ranges_overlap(a: list[tuple[int, int]], b: list[tuple[int, int]], slack: int = 5) -> bool:
    for s1, e1 in a:
        for s2, e2 in b:
            if s1 - slack <= e2 and s2 - slack <= e1:
                return True
    return False


def score_pair(repo: str, task_id: int, fa: int, fb: int) -> tuple[int, int]:
    base = DATASET / repo / f"task{task_id}"
    fa_files, fa_ch = parse_patch(base / f"feature{fa}" / "feature.patch")
    fb_files, fb_ch = parse_patch(base / f"feature{fb}" / "feature.patch")
    shared = set(fa_files) & set(fb_files)
    overlapping = sum(1 for f in shared if ranges_overlap(fa_files[f], fb_files[f]))
    score = 3 * overlapping + (len(shared) - overlapping)
    return score, fa_ch + fb_ch


def main() -> None:
    report = json.loads(CONFLICT_REPORT.read_text())
    conflicts = [e for e in report["conflict_pairs"] if e["repo"] in PY_REPOS]

    # best-scoring pair per task
    best: dict[tuple[str, int], dict] = {}
    for e in conflicts:
        repo, tid, fa, fb = e["repo"], e["task_id"], e["f1"], e["f2"]
        sc, size = score_pair(repo, tid, fa, fb)
        key = (repo, tid)
        # prefer higher overlap; tie-break toward medium size (~40-200 changed lines)
        med = -abs(size - 120)
        cand = {"repo": repo, "task_id": tid, "pair": [fa, fb], "score": sc, "size": size, "med": med}
        if key not in best or (sc, med) > (best[key]["score"], best[key]["med"]):
            best[key] = cand

    tasks = list(best.values())
    # rank tasks by conflict-overlap; pick N_FINAL with a per-repo cap
    tasks.sort(key=lambda t: (t["score"], t["med"]), reverse=True)
    selected, per_repo = [], {}
    for t in tasks:
        if per_repo.get(t["repo"], 0) >= PER_REPO_CAP:
            continue
        selected.append(t)
        per_repo[t["repo"]] = per_repo.get(t["repo"], 0) + 1
        if len(selected) >= N_FINAL:
            break

    print(f"{'repo':32s} {'task':>6} {'pair':>8} {'overlap':>7} {'size':>5}  sel")
    chosen = {(t["repo"], t["task_id"]) for t in selected}
    for t in sorted(best.values(), key=lambda t: (-t["score"], t["repo"])):
        mark = "SEL" if (t["repo"], t["task_id"]) in chosen else "-"
        print(f"{t['repo']:32s} {t['task_id']:>6} {str(t['pair']):>8} {t['score']:>7} {t['size']:>5}  {mark}")

    doc = {
        "name": "nano",
        "description": (
            f"Single-language (Python) coordination benchmark: {len(selected)} gold-conflict "
            f"pairs, one per task, across {len(per_repo)} repos. Pairs pre-filtered offline by "
            f"static feature-overlap (proxy for conflict severity); final validity is confirmed "
            f"post-hoc from the k=20 no-messaging control (drop capability-floor / no-conflict-bite "
            f"pairs). See docs/nano_py_preregistration.md. Selection is deterministic (no runs)."
        ),
        "stats": {"pairs": len(selected), "repos": len(per_repo)},
        "tasks": [{"repo": t["repo"], "task_id": t["task_id"], "pairs": [t["pair"]]} for t in selected],
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(selected)} pairs, {len(per_repo)} repos")


if __name__ == "__main__":
    main()
