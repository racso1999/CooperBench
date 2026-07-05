#!/usr/bin/env python3
"""eval2 -- per-feature measurement pipeline for coop runs.

Layout: one row PER FEATURE PER RUN (each repeat independently), followed by an
AGGREGATE row per feature (rates for pass/fail, means for the numeric columns).
Each agent in coop owns exactly one feature (runner/coop.py:
zip(agents, sorted_features)), so "per feature" == "per agent's own work".

Columns per feature-run:
  * INDEPENDENT (pre-merge): does this agent's OWN patch pass its OWN feature's
    tests, in isolation?  Must be RUN in containers -- see --compute.
  * MERGE / POST-MERGE (pair context, from eval.json): apply status, textual
    merge status, whether this feature passes on the merged tree, both_passed,
    and a convenience merge_outcome bucket.
  * EFFORT / TOKENS (from result.json): steps, cost, input/output/cache tokens,
    patch size, duration.
  * MESSAGING (from agent*_sent.jsonl): messages sent, message chars, and
    messaging_output_share = message tokens (approx chars/4) / output_tokens --
    an approximate proxy for "what fraction of generated text was messaging".

No inferential statistics here (do those downstream); the aggregate row is just
rates + means for convenience.

Modes:
    python scripts/eval2.py NAME --compute [-c 4]   # run pre-merge tests, cache
    python scripts/eval2.py NAME                     # emit the table

Output: logs/<name>/eval2_rows.csv (+ .json).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

INDEP_CACHE = "independent.json"
MERGE_OK = {"clean", "identical"}
CHARS_PER_TOKEN = 4  # rough token estimate for messaging share

FIELDS = [
    "run",
    "repeat",
    "row_type",
    "n",
    "repo",
    "task_id",
    "pair",
    "feature_id",
    "partner_feature",
    # independent (pre-merge)
    "indep_passed",
    "indep_tests_passed",
    "indep_tests_failed",
    "indep_reason",
    # merge / post-merge (pair context)
    "merged_passed",
    "merge_status",
    "both_passed",
    "merge_outcome",
    "apply",
    # effort / tokens
    "status",
    "steps",
    "cost",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "patch_lines",
    "duration_s",
    # messaging
    "messages_sent",
    "message_chars",
    "message_tokens_est",
    "messaging_output_share",
]

BOOL_COLS = ("indep_passed", "merged_passed", "both_passed")
MEAN_COLS = (
    "indep_tests_passed",
    "indep_tests_failed",
    "steps",
    "cost",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "patch_lines",
    "duration_s",
    "messages_sent",
    "message_chars",
    "message_tokens_est",
    "messaging_output_share",
)


def run_dirs(name: str, logs: Path) -> list[Path]:
    out: list[Path] = []
    if (logs / name).is_dir():
        out.append(logs / name)
    pat = re.compile(rf"^{re.escape(name)}_\d+$")
    if logs.is_dir():
        out.extend(d for d in logs.iterdir() if d.is_dir() and pat.match(d.name))
    return sorted(set(out))


def leaf_dirs(name: str, logs: Path) -> list[Path]:
    leaves: list[Path] = []
    for d in run_dirs(name, logs):
        leaves.extend(p.parent for p in d.rglob("result.json"))
    if not leaves:
        raise SystemExit(f"no run leaves found for '{name}' under {logs}/ (looked for {name} and {name}_<n>)")
    return sorted(set(leaves))


def coop_features(leaf: Path) -> tuple[int, int] | None:
    try:
        r = json.loads((leaf / "result.json").read_text())
    except Exception:
        return None
    feats = sorted(r.get("features", []))
    if r.get("setting") != "coop" or len(feats) != 2:
        return None
    return (feats[0], feats[1])


# ---------------------------------------------------------------- compute mode


def compute_independent(leaf: Path, backend: str, timeout: int, force: bool) -> dict | None:
    from cooperbench.eval.sandbox import run_patch_test  # lazy: only compute needs docker

    feats = coop_features(leaf)
    if feats is None:
        return None
    cache = leaf / INDEP_CACHE
    if cache.exists() and not force:
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    r = json.loads((leaf / "result.json").read_text())
    repo, task = r["repo"], r["task_id"]
    out: dict[str, dict] = {}
    for fid in feats:
        patch = leaf / f"agent{fid}.patch"
        if not patch.exists() or not patch.read_text().strip():
            out[f"feature{fid}"] = {"passed": False, "reason": "no_patch"}
            continue
        res = run_patch_test(repo, task, fid, agent_patch=patch, timeout=timeout, backend=backend)
        out[f"feature{fid}"] = {
            "passed": bool(res.get("passed")),
            "tests_passed": res.get("tests_passed"),
            "tests_failed": res.get("tests_failed"),
            "reason": res.get("error"),
        }
    cache.write_text(json.dumps(out, indent=2))
    return out


def do_compute(name: str, logs: Path, backend: str, concurrency: int, timeout: int, force: bool) -> None:
    leaves = [ln for ln in leaf_dirs(name, logs) if coop_features(ln) is not None]
    todo = [ln for ln in leaves if force or not (ln / INDEP_CACHE).exists()]
    print(
        f"compute: {len(leaves)} coop leaves, {len(todo)} to run "
        f"({len(leaves) - len(todo)} cached), concurrency={concurrency}"
    )
    done = 0
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(compute_independent, ln, backend, timeout, force): ln for ln in todo}
        for fut in as_completed(futs):
            ln = futs[fut]
            done += 1
            try:
                fut.result()
                mark = "ok"
            except Exception as e:  # noqa: BLE001 -- surface and keep going
                mark = f"ERR {e}"
            print(f"  [{done}/{len(todo)}] {ln.relative_to(logs)}  {mark}")
    print("compute done.\n")


# ----------------------------------------------------------------- helpers


def merge_outcome(apply_this: str | None, apply_partner: str | None, merge_status: str | None, both: bool) -> str:
    if apply_this != "applied" or apply_partner != "applied":
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


def msg_stats(leaf: Path) -> dict[str, dict[str, int]]:
    """Per agent-id: number of messages sent and total content chars."""
    out: dict[str, dict[str, int]] = {}
    for p in leaf.glob("agent*_sent.jsonl"):
        aid = p.name.split("_sent")[0]  # 'agent1'
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
        out[aid] = {"msgs": msgs, "chars": chars}
    return out


def _b(v: object) -> object:
    return "" if v is None else v


def build_feature_rows(leaf: Path, logs: Path) -> list[dict]:
    feats = coop_features(leaf)
    if feats is None:
        return []
    f1, f2 = feats
    r = json.loads((leaf / "result.json").read_text())
    repeat = leaf.relative_to(logs).parts[0]
    run = repeat.rsplit("_", 1)[0] if re.search(r"_\d+$", repeat) else repeat

    agent_of_feat = {a.get("feature_id"): aid for aid, a in r.get("agents", {}).items()}
    by_feat = {a.get("feature_id"): a for a in r.get("agents", {}).values()}
    msgs = msg_stats(leaf)

    ev = None
    try:
        ev = json.loads((leaf / "eval.json").read_text())
    except Exception:
        pass

    # independent (pre-merge) result per feature id: prefer eval.json (the
    # integrated pipeline writes feature{1,2}_independent), else fall back to the
    # legacy independent.json cache produced by --compute.
    indep_by_fid: dict[int, dict] = {}
    if ev is not None:
        if ev.get("feature1_independent") is not None:
            indep_by_fid[f1] = ev["feature1_independent"]
        if ev.get("feature2_independent") is not None:
            indep_by_fid[f2] = ev["feature2_independent"]
    if (leaf / INDEP_CACHE).exists():
        try:
            cache = json.loads((leaf / INDEP_CACHE).read_text())
            for fid in (f1, f2):
                if fid not in indep_by_fid and f"feature{fid}" in cache:
                    indep_by_fid[fid] = cache[f"feature{fid}"]
        except Exception:
            pass

    rows = []
    for fid, partner in ((f1, f2), (f2, f1)):
        a = by_feat.get(fid, {})
        aid = agent_of_feat.get(fid)
        row = {k: "" for k in FIELDS}
        row.update(
            run=run,
            repeat=repeat,
            row_type="run",
            n="",
            repo=r.get("repo"),
            task_id=r.get("task_id"),
            pair=f"{f1},{f2}",
            feature_id=fid,
            partner_feature=partner,
            status=_b(a.get("status")),
            steps=_b(a.get("steps")),
            cost=_b(a.get("cost")),
            input_tokens=_b(a.get("input_tokens")),
            output_tokens=_b(a.get("output_tokens")),
            cache_read_tokens=_b(a.get("cache_read_tokens")),
            cache_write_tokens=_b(a.get("cache_write_tokens")),
            patch_lines=_b(a.get("patch_lines")),
            duration_s=_b(r.get("duration_seconds")),
        )
        it, ot = a.get("input_tokens"), a.get("output_tokens")
        row["total_tokens"] = (it or 0) + (ot or 0) if (it is not None or ot is not None) else ""

        # messaging
        ms = msgs.get(aid, {"msgs": 0, "chars": 0}) if aid else {"msgs": 0, "chars": 0}
        row["messages_sent"] = ms["msgs"]
        row["message_chars"] = ms["chars"]
        mtok = ms["chars"] / CHARS_PER_TOKEN
        row["message_tokens_est"] = round(mtok, 1)
        row["messaging_output_share"] = round(mtok / ot, 4) if ot else ""

        # merge / post-merge
        if ev is not None:
            apply = ev.get("apply_status") or {}
            apply_this = apply.get(agent_of_feat.get(fid))
            apply_partner = apply.get(agent_of_feat.get(partner))
            merge_status = (ev.get("merge") or {}).get("status")
            both = bool(ev.get("both_passed"))
            merged_key = "feature1" if fid == f1 else "feature2"
            row.update(
                apply=_b(apply_this),
                merge_status=_b(merge_status),
                both_passed=both,
                merged_passed=_b((ev.get(merged_key) or {}).get("passed")),
                merge_outcome=merge_outcome(apply_this, apply_partner, merge_status, both),
            )

        # independent (pre-merge)
        fr = indep_by_fid.get(fid)
        if fr is not None:
            row.update(
                indep_passed=_b(fr.get("passed")),
                indep_tests_passed=_b(fr.get("tests_passed")),
                indep_tests_failed=_b(fr.get("tests_failed")),
                indep_reason=_b(fr.get("reason")),
            )
        rows.append(row)
    return rows


def aggregate_row(runs: list[dict]) -> dict:
    agg = {k: "" for k in FIELDS}
    first = runs[0]
    for k in ("run", "repo", "task_id", "pair", "feature_id", "partner_feature"):
        agg[k] = first[k]
    agg.update(row_type="aggregate", repeat="", n=len(runs))

    def rate(col: str) -> object:
        vals = [r[col] for r in runs if isinstance(r[col], bool)]
        return round(sum(1 for v in vals if v) / len(vals), 4) if vals else ""

    def mean(col: str) -> object:
        vals = [r[col] for r in runs if isinstance(r[col], (int, float)) and not isinstance(r[col], bool)]
        return round(sum(vals) / len(vals), 4) if vals else ""

    for col in BOOL_COLS:
        agg[col] = rate(col)
    for col in MEAN_COLS:
        agg[col] = mean(col)
    return agg


def emit(name: str, logs: Path, out_stem: Path) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for leaf in leaf_dirs(name, logs):
        for row in build_feature_rows(leaf, logs):
            groups[(row["repo"], row["task_id"], row["feature_id"])].append(row)

    out_rows: list[dict] = []
    for key in sorted(groups, key=lambda k: (str(k[0]), str(k[1]), k[2])):
        runs = sorted(groups[key], key=lambda r: r["repeat"])
        out_rows.extend(runs)
        out_rows.append(aggregate_row(runs))

    out_stem.parent.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = out_stem.with_suffix(".csv"), out_stem.with_suffix(".json")
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)
    json_path.write_text(json.dumps(out_rows, indent=2))

    n_run = sum(1 for r in out_rows if r["row_type"] == "run")
    n_feat = sum(1 for r in out_rows if r["row_type"] == "aggregate")
    ncomp = sum(1 for r in out_rows if r["row_type"] == "run" and r["indep_passed"] != "")
    print(f"wrote {len(out_rows)} rows -> {csv_path}  (and {json_path.name})")
    print(
        f"  {n_feat} features x ~{n_run // max(n_feat, 1)} runs each = {n_run} feature-run rows + {n_feat} aggregate rows"
    )
    print(
        f"  independent (pre-merge) computed for {ncomp}/{n_run} feature-runs"
        + ("" if ncomp == n_run else f"  -- run:  python scripts/eval2.py {name} --compute")
    )
    return out_rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="run name; covers NAME and repeats NAME_1, NAME_2, ...")
    ap.add_argument(
        "--compute",
        action="store_true",
        help="backfill: run the pre-merge independent tests (containers) and cache to "
        "independent.json. Only needed for runs evaluated BEFORE the integrated eval "
        "pipeline; new runs already carry feature{1,2}_independent in eval.json.",
    )
    ap.add_argument("-c", "--concurrency", type=int, default=4, help="parallel sandboxes for --compute (default 4)")
    ap.add_argument("--backend", default="docker", choices=["docker", "modal", "gcp"])
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--force", action="store_true", help="recompute even if independent.json exists")
    ap.add_argument("--log-dir", default="logs")
    ap.add_argument("--out", default=None, help="output stem (default logs/<name>/eval2_rows)")
    args = ap.parse_args()

    logs = Path(args.log_dir)
    if args.compute:
        do_compute(args.name, logs, args.backend, args.concurrency, args.timeout, args.force)
    out_stem = Path(args.out) if args.out else logs / args.name / "eval2_rows"
    emit(args.name, logs, out_stem)


if __name__ == "__main__":
    main()
