"""Flatten every run under logs/ into per-run CSVs (one row per pair).

For each run directory logs/<run_name>/ that contains at least one result.json
or eval.json leaf, writes results_csv/<run_name>.csv with one row per pair
(coop) or per feature (solo). Also writes:

  * results_csv/all_runs.csv   every row from every run, same columns
  * results_csv/runs.csv       one line per run (counts + run metadata)

Feature "a" is the lower feature id (eval.json's feature1), "b" the higher.
Pre-merge independent results come from eval.json's feature{1,2}_independent
when present, else the legacy independent.json cache written by eval2 --compute.
The outcome bucket mirrors scripts/eval2.py merge_outcome so numbers line up.

Run:  uv run python scripts/nano/build_run_csvs.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

MERGE_OK = {"clean", "identical"}

# pre-registered exclusions, judged on the control arm by analyze_study.py
# (ceiling: control both_passed > 60%, so merge conflict never bites there).
# rows for these pairs get in_validated_set=False; everything else True.
EXCLUDED_PAIRS = {
    ("llama_index_task", 18813, "f1_f3"),
    ("pallets_click_task", 2956, "f3_f6"),
}

PRIMARY_NOGIT = {"nano_control", "nano_msg", "nano_struct", "nano_handshake", "nano_dc", "nano_coauthor"}
GIT_ARMS = {"nano_nomsg_git", "nano_free_git", "nano_hs_git"}

AGENT_COLS = (
    "status",
    "steps",
    "cost",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "patch_lines",
)

BASE_FIELDS = [
    # run identity
    "run_name",
    "arm",
    "repeat",
    "arm_family",
    "model",
    "agent_framework",
    "setting",
    "messaging_mode",
    "message_schema",
    # pair identity
    "repo",
    "task_id",
    "pair",
    "feature_a",
    "feature_b",
    "in_validated_set",
    # merge (pair-level)
    "apply_a",
    "apply_b",
    "merge_status",
    "merge_strategy",
    "merge_clean",
    "both_passed",
    "outcome",
    # post-merge, per feature
    "a_merged_passed",
    "a_merged_tests_passed",
    "a_merged_tests_failed",
    "b_merged_passed",
    "b_merged_tests_passed",
    "b_merged_tests_failed",
    # pre-merge (independent), per feature
    "a_indep_passed",
    "a_indep_tests_passed",
    "a_indep_tests_failed",
    "a_indep_reason",
    "b_indep_passed",
    "b_indep_tests_passed",
    "b_indep_tests_failed",
    "b_indep_reason",
    # effort
    "duration_s",
    "total_cost",
    "total_steps",
    *[f"a_{c}" for c in AGENT_COLS],
    *[f"b_{c}" for c in AGENT_COLS],
    # messaging
    "messages_sent",
    "a_msgs_sent",
    "a_msg_chars",
    "b_msgs_sent",
    "b_msg_chars",
    # msgs_<KIND> columns are appended dynamically (union across all runs)
    # status / provenance
    "error",
    "evaluated_at",
    "pair_dir",
    "n_files",
    "files",
]

RUN_FIELDS = [
    "run_name",
    "arm",
    "repeat",
    "arm_family",
    "model",
    "setting",
    "messaging_mode",
    "message_schema",
    "n_rows",
    "n_evals",
    "n_both_passed",
    "n_merge_clean",
    "n_conflicts",
    "n_errors",
    "total_cost",
    "started_at",
    "completed_at",
    "csv",
]


def arm_of(run_name: str) -> tuple[str, str]:
    m = re.match(r"^(.*)_(\d+)$", run_name)
    return (m.group(1), m.group(2)) if m else (run_name, "")


def family_of(arm: str) -> str:
    if arm in PRIMARY_NOGIT:
        return "coop_nogit"
    if arm in GIT_ARMS:
        return "coop_git"
    if arm.startswith("flash_"):  # flash runs follow the same arm_repeat naming
        return "coop_git" if arm.endswith("_git") else "coop_nogit"
    if "solo" in arm:
        return "solo"
    if arm.startswith("smoke"):
        return "smoke"
    return "misc"


def merge_outcome(apply_a: object, apply_b: object, merge_status: object, both: bool) -> str:
    # mirrors scripts/eval2.py merge_outcome, pair-level (symmetric)
    if apply_a != "applied" or apply_b != "applied":
        return "missing_patch"
    if both and merge_status in MERGE_OK:
        return "pass"
    if both:
        return "solo_rescue"
    if merge_status in MERGE_OK:
        return "functional_fail"
    if merge_status in ("conflicts", "missing_input"):
        return "textual_conflict"
    return "unknown"


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def msg_stats(leaf: Path) -> dict[str, dict[str, int]]:
    """Per agent slot ('agent1'): messages sent and total content chars."""
    out: dict[str, dict[str, int]] = {}
    for p in leaf.glob("agent*_sent.jsonl"):
        slot = p.name.split("_sent")[0]
        msgs = chars = 0
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except Exception:
                continue
            msgs += 1
            chars += len(m.get("content", "") or "")
        out[slot] = {"msgs": msgs, "chars": chars}
    return out


def _b(v: object) -> object:
    return "" if v is None else v


def indep_by_fid(ev: dict | None, leaf: Path, fids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    if ev is not None:
        for i, fid in enumerate(fids[:2], start=1):
            blk = ev.get(f"feature{i}_independent")
            if blk is not None:
                out[fid] = blk
    cache = read_json(leaf / "independent.json")
    if cache:
        for fid in fids:
            if fid not in out and f"feature{fid}" in cache:
                out[fid] = cache[f"feature{fid}"]
    return out


def leaf_row(run_name: str, cfg: dict, leaf: Path, logs: Path) -> dict | None:
    res = read_json(leaf / "result.json")
    ev = read_json(leaf / "eval.json")
    if res is None and ev is None:
        return None
    src = res or ev or {}
    fids = sorted(src.get("features", []))
    fa = fids[0] if fids else None
    fb = fids[1] if len(fids) > 1 else None

    arm, repeat = arm_of(run_name)
    row: dict[str, object] = dict.fromkeys(BASE_FIELDS, "")
    row.update(
        run_name=run_name,
        arm=arm,
        repeat=repeat,
        arm_family=family_of(arm),
        model=_b(cfg.get("model") or src.get("model")),
        agent_framework=_b(cfg.get("agent_framework") or src.get("agent_framework")),
        setting=_b(src.get("setting") or cfg.get("setting")),
        messaging_mode=_b(cfg.get("messaging_mode")),
        message_schema=_b(cfg.get("message_schema") or (res or {}).get("message_schema")),
        repo=_b(src.get("repo")),
        task_id=_b(src.get("task_id")),
        pair=leaf.name,
        feature_a=_b(fa),
        feature_b=_b(fb),
        in_validated_set=(src.get("repo"), src.get("task_id"), leaf.name) not in EXCLUDED_PAIRS,
        pair_dir=str(leaf.relative_to(logs)),
    )

    # slot mapping: which agent slot owns which feature id
    slot_of: dict[int, str] = {}
    if res is not None:
        for slot, a in (res.get("agents") or {}).items():
            slot_of[a.get("feature_id")] = slot
        row.update(
            duration_s=_b(res.get("duration_seconds")),
            total_cost=_b(res.get("total_cost")),
            total_steps=_b(res.get("total_steps")),
            messages_sent=_b(res.get("messages_sent")),
        )
        for kind, n in (res.get("messages_by_kind") or {}).items():
            row[f"msgs_{kind}"] = n
        for side, fid in (("a", fa), ("b", fb)):
            agent = (res.get("agents") or {}).get(slot_of.get(fid, ""), {})
            for c in AGENT_COLS:
                row[f"{side}_{c}"] = _b(agent.get(c))

    if ev is not None:
        apply = ev.get("apply_status") or {}
        merge = ev.get("merge") or {}
        both = bool(ev.get("both_passed"))
        apply_a = apply.get(slot_of.get(fa, ""))
        apply_b = apply.get(slot_of.get(fb, ""))
        row.update(
            apply_a=_b(apply_a),
            apply_b=_b(apply_b),
            merge_status=_b(merge.get("status")),
            merge_strategy=_b(merge.get("strategy")),
            merge_clean=merge.get("status") in MERGE_OK if merge.get("status") else "",
            both_passed=both,
            error=_b(ev.get("error")),
            evaluated_at=_b(ev.get("evaluated_at")),
        )
        if fb is not None:  # coop: outcome bucket + per-feature post-merge
            row["outcome"] = merge_outcome(apply_a, apply_b, merge.get("status"), both)
        for i, side in ((1, "a"), (2, "b")):
            blk = ev.get(f"feature{i}") or {}
            row[f"{side}_merged_passed"] = _b(blk.get("passed"))
            row[f"{side}_merged_tests_passed"] = _b(blk.get("tests_passed"))
            row[f"{side}_merged_tests_failed"] = _b(blk.get("tests_failed"))
        for fid, side in ((fa, "a"), (fb, "b")):
            blk = indep_by_fid(ev, leaf, fids).get(fid) if fid is not None else None
            if blk:
                row[f"{side}_indep_passed"] = _b(blk.get("passed"))
                row[f"{side}_indep_tests_passed"] = _b(blk.get("tests_passed"))
                row[f"{side}_indep_tests_failed"] = _b(blk.get("tests_failed"))
                row[f"{side}_indep_reason"] = _b(blk.get("reason"))
    else:
        row["error"] = "no_eval"

    msgs = msg_stats(leaf)
    for side, fid in (("a", fa), ("b", fb)):
        ms = msgs.get(slot_of.get(fid, ""))
        if ms:
            row[f"{side}_msgs_sent"] = ms["msgs"]
            row[f"{side}_msg_chars"] = ms["chars"]

    names = sorted(p.name for p in leaf.iterdir() if p.is_file())
    row["n_files"] = len(names)
    row["files"] = ";".join(names)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log-dir", default="logs")
    ap.add_argument("--out-dir", default="results_csv")
    args = ap.parse_args()

    logs, out = Path(args.log_dir), Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    per_run: dict[str, list[dict]] = {}
    skipped: list[str] = []
    for run_dir in sorted(p for p in logs.iterdir() if p.is_dir()):
        leaves = sorted(
            {p.parent for p in run_dir.rglob("result.json")} | {p.parent for p in run_dir.rglob("eval.json")}
        )
        if not leaves:
            skipped.append(run_dir.name)
            continue
        cfg = read_json(run_dir / "config.json") or {}
        rows = [r for leaf in leaves if (r := leaf_row(run_dir.name, cfg, leaf, logs)) is not None]
        rows.sort(key=lambda r: (str(r["repo"]), str(r["task_id"]), str(r["pair"])))
        per_run[run_dir.name] = rows

    # stable columns everywhere: union of msgs_<KIND> across all rows
    kinds = sorted({k for rows in per_run.values() for r in rows for k in r if k.startswith("msgs_")})
    fields = BASE_FIELDS[: BASE_FIELDS.index("error")] + kinds + BASE_FIELDS[BASE_FIELDS.index("error") :]

    def write_csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, restval="")
            w.writeheader()
            w.writerows(rows)

    all_rows: list[dict] = []
    run_lines: list[dict] = []
    for run_name, rows in sorted(per_run.items()):
        write_csv(out / f"{run_name}.csv", rows)
        all_rows.extend(rows)
        summ = read_json(logs / run_name / "summary.json") or {}
        cfg = read_json(logs / run_name / "config.json") or {}
        arm, repeat = arm_of(run_name)
        run_lines.append(
            {
                "run_name": run_name,
                "arm": arm,
                "repeat": repeat,
                "arm_family": family_of(arm),
                "model": _b(cfg.get("model")),
                "setting": _b(cfg.get("setting")),
                "messaging_mode": _b(cfg.get("messaging_mode")),
                "message_schema": _b(cfg.get("message_schema")),
                "n_rows": len(rows),
                "n_evals": sum(1 for r in rows if r["evaluated_at"] != ""),
                "n_both_passed": sum(1 for r in rows if r["both_passed"] is True),
                "n_merge_clean": sum(1 for r in rows if r["merge_clean"] is True),
                "n_conflicts": sum(1 for r in rows if r["merge_status"] == "conflicts"),
                "n_errors": sum(1 for r in rows if r["error"] != ""),
                "total_cost": _b(summ.get("total_cost")),
                "started_at": _b(cfg.get("started_at")),
                "completed_at": _b(summ.get("completed_at")),
                "csv": f"{run_name}.csv",
            }
        )

    write_csv(out / "all_runs.csv", all_rows)
    with (out / "runs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RUN_FIELDS)
        w.writeheader()
        w.writerows(run_lines)

    print(f"{len(per_run)} runs -> {out}/  ({len(all_rows)} rows total; columns: {len(fields)})")
    print(f"  + all_runs.csv ({len(all_rows)} rows), runs.csv ({len(run_lines)} runs)")
    if skipped:
        print(f"  skipped (no result.json/eval.json): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
