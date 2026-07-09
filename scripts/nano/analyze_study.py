"""Full multi-arm analysis of the nano no-git messaging-protocol study.

Reads eval.json across all six no-git coop arms, applies the pre-registered
post-hoc exclusions (judged on the CONTROL arm only), and reports, on the
validated pair set:

  * per-arm funnel: applied -> merge-clean -> both_passed
  * PRIMARY endpoint  = merge-clean rate (coordination-specific), pooled with a
    Cochran-Mantel-Haenszel test stratified by pair (respects clustering), MH
    common odds ratio + Holm-corrected p, vs control and in head-to-heads
  * SECONDARY endpoint = both_passed, same treatment
  * merge_outcome failure taxonomy (pass / solo_rescue / functional_fail /
    textual_conflict / missing_patch) — the mechanism
  * pre-merge capability (feature{1,2}_independent) as context

Design fixed in docs/nano_py_preregistration.md. One pair per task => stratify
-by-pair == stratify-by-task. No third-party deps.

merge-clean is operationalised as merge status in {clean, identical} — the eval
pipeline's own MERGE_OK. `identical` (both agents produced byte-identical merged
code) is a conflict-free merge; excluding it would perversely penalise a protocol
for succeeding by convergence. clean-only and identical are also reported split.

Usage:  python scripts/nano/analyze_study.py            # markdown to stdout
        python scripts/nano/analyze_study.py --json OUT  # + machine-readable dump
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

# reuse the vetted primitives from the 2-arm tool
from analyze import cmh, wilson  # type: ignore  # noqa: E402  (same dir on sys.path)

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"

MERGE_OK = {"clean", "identical"}
CEILING_BOTH = 0.60     # drop pair if control both_passed > this (conflict doesn't bite)
FLOOR_CAP = 0.10        # drop pair if neither feature passes independently in > this of control runs

# (prefix, short label). control MUST be first.
ARMS = [
    ("nano_control", "no-msg (control)"),
    ("nano_msg", "free-text"),
    ("nano_struct", "semi_structured"),
    ("nano_handshake", "plan_handshake"),
    ("nano_dc", "designated_coder"),
    ("nano_coauthor", "coauthor_overlap"),
]
BUCKETS = ["pass", "solo_rescue", "functional_fail", "textual_conflict", "missing_patch", "unknown"]


def pair_outcome(apply_this, apply_partner, merge_status, both) -> str:
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


def collect(prefix: str) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    # match "<prefix>_<n>/" and "<prefix>/" but NOT "<prefix>_b2..." style siblings:
    # the study arms are plain "<prefix>_<int>". guard with a digit check.
    for f in glob.glob(str(LOGS / f"{prefix}_*" / "**" / "eval.json"), recursive=True):
        rel = Path(f).relative_to(LOGS)
        top = rel.parts[0]
        suffix = top[len(prefix) + 1:]
        if not suffix.isdigit():
            continue
        try:
            e = json.loads(Path(f).read_text())
        except Exception:
            continue
        key = (e["repo"], e["task_id"], tuple(e.get("features", [])))
        out.setdefault(key, []).append(e)
    return out


def agg(evals: list[dict]) -> dict:
    a = {k: 0 for k in ("n", "infra", "applied", "clean", "identical", "mergeok",
                        "both", "cap_any", "cap_n")}
    buckets: Counter = Counter()
    for e in evals:
        if e.get("error"):
            a["infra"] += 1
            continue
        a["n"] += 1
        ms = (e.get("merge") or {}).get("status")
        ap = e.get("apply_status") or {}
        a1, a2 = ap.get("agent1"), ap.get("agent2")
        if a1 == "applied" and a2 == "applied":
            a["applied"] += 1
        if ms == "clean":
            a["clean"] += 1
        if ms == "identical":
            a["identical"] += 1
        if ms in MERGE_OK:
            a["mergeok"] += 1
        both = bool(e.get("both_passed"))
        if both:
            a["both"] += 1
        buckets[pair_outcome(a1, a2, ms, both)] += 1
        # pre-merge capability from feature{1,2}_independent (uncorrupted by merge)
        i1 = (e.get("feature1_independent") or {}).get("passed")
        i2 = (e.get("feature2_independent") or {}).get("passed")
        if i1 is not None or i2 is not None:
            a["cap_n"] += 1
            if i1 or i2:
                a["cap_any"] += 1
    a["buckets"] = dict(buckets)
    return a


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj: dict[str, float] = {}
    running = 0.0
    for i, (k, p) in enumerate(items):
        val = min(1.0, (m - i) * p)
        running = max(running, val)
        adj[k] = running
    return adj


def rate(d: dict, key: str) -> float:
    return d[key] / d["n"] if d["n"] else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="also dump computed numbers here")
    args = ap.parse_args()

    data = {prefix: {k: agg(v) for k, v in collect(prefix).items()} for prefix, _ in ARMS}
    ctrl = data["nano_control"]
    all_pairs = sorted(set().union(*[set(d) for d in data.values()]))

    # ---- pre-registered post-hoc exclusion, judged on control -------------
    kept, dropped = [], []
    for k in all_pairs:
        c = ctrl.get(k)
        if not c or c["n"] == 0:
            dropped.append((k, "no control data"))
            continue
        cap = c["cap_any"] / c["cap_n"] if c["cap_n"] else None
        if cap is not None and cap <= FLOOR_CAP:
            dropped.append((k, f"floor (control indep-cap {cap:.0%} <= {FLOOR_CAP:.0%})"))
            continue
        if c["both"] / c["n"] > CEILING_BOTH:
            dropped.append((k, f"ceiling (control both {c['both']/c['n']:.0%} > {CEILING_BOTH:.0%})"))
            continue
        kept.append(k)

    def lbl(k):
        return f"{k[0].replace('_task','')}/{k[1]}/{','.join(map(str, k[2]))}"

    out = ["# nano protocol study — computed results", ""]
    out.append(f"Pairs total: {len(all_pairs)}  |  kept (validated): {len(kept)}  |  dropped: {len(dropped)}")
    out.append("")
    out.append("## Pre-registered exclusions (judged on control arm)")
    if dropped:
        for k, why in dropped:
            out.append(f"- DROP {lbl(k)} — {why}")
    else:
        out.append("- (none)")
    out.append("")

    # ---- per-arm funnel on kept set ---------------------------------------
    out.append("## Funnel + endpoints on validated set (pooled over kept pairs)")
    out.append("")
    out.append("| arm | k-range | runs | applied | merge-clean (primary) | both_passed (secondary) |")
    out.append("|---|---|---|---|---|---|")
    perarm = {}
    for prefix, label in ARMS:
        d = data[prefix]
        n = sum(d[k]["n"] for k in kept if k in d)
        appl = sum(d[k]["applied"] for k in kept if k in d)
        mok = sum(d[k]["mergeok"] for k in kept if k in d)
        both = sum(d[k]["both"] for k in kept if k in d)
        # k per pair (runs / pairs)
        npairs = sum(1 for k in kept if k in d and d[k]["n"] > 0)
        krange = f"~{round(n / npairs)}" if npairs else "0"
        lo, hi = wilson(mok, n)
        blo, bhi = wilson(both, n)
        perarm[prefix] = dict(n=n, applied=appl, mergeok=mok, both=both,
                              mok_ci=(lo, hi), both_ci=(blo, bhi))
        out.append(f"| {label} | {krange} | {n} | {appl/n:.0%} | "
                   f"**{mok/n:.0%}** [{lo:.0%},{hi:.0%}] | {both/n:.0%} [{blo:.0%},{bhi:.0%}] |")
    out.append("")
    out.append("*merge-clean = merge status in {clean, identical}. Wilson 95% CIs are "
               "descriptive (not cluster-adjusted); CMH below is the inferential test.*")
    out.append("")

    # ---- CMH contrasts, primary + secondary -------------------------------
    def contrasts(key: str, title: str):
        out.append(f"## {title}")
        out.append("")
        fam = {}
        # every protocol vs control + two head-to-heads
        pv = {}
        rows = []
        for prefix, label in ARMS[1:]:
            strata = [(data[prefix][k][key], data[prefix][k]["n"] - data[prefix][k][key],
                       ctrl[k][key], ctrl[k]["n"] - ctrl[k][key])
                      for k in kept if k in data[prefix]]
            orr, p = cmh(strata)
            pv[f"{label} vs control"] = p
            cs = sum(ctrl[k][key] for k in kept)
            csz = sum(ctrl[k]["n"] for k in kept)
            ps = sum(data[prefix][k][key] for k in kept if k in data[prefix])
            psz = sum(data[prefix][k]["n"] for k in kept if k in data[prefix])
            rows.append([f"{label} vs control", cs/csz, ps/psz, orr, p])
        # head to heads (base = second arm)
        for a, b in [("nano_coauthor", "nano_handshake"), ("nano_coauthor", "nano_dc"),
                     ("nano_dc", "nano_handshake")]:
            la = dict(ARMS)[a]
            lb = dict(ARMS)[b]
            strata = [(data[a][k][key], data[a][k]["n"] - data[a][k][key],
                       data[b][k][key], data[b][k]["n"] - data[b][k][key])
                      for k in kept if k in data[a] and k in data[b]]
            orr, p = cmh(strata)
            pv[f"{la} vs {lb}"] = p
            asz = sum(data[a][k]["n"] for k in kept if k in data[a])
            asum = sum(data[a][k][key] for k in kept if k in data[a])
            bsz = sum(data[b][k]["n"] for k in kept if k in data[b])
            bsum = sum(data[b][k][key] for k in kept if k in data[b])
            rows.append([f"{la} vs {lb}", bsum/bsz, asum/asz, orr, p])
        adj = holm(pv)
        fam["holm"] = adj
        out.append("| contrast | base | arm | CMH OR | p (raw) | p (Holm) | sig |")
        out.append("|---|---|---|---|---|---|---|")
        for name, base, armr, orr, p in rows:
            pa = adj[name]
            orstr = "inf" if orr == float("inf") else f"{orr:.2f}"
            out.append(f"| {name} | {base:.0%} | {armr:.0%} | {orstr} | {p:.4f} | {pa:.4f} | "
                       f"{'**' + chr(0x2713) + '**' if pa < 0.05 else 'ns'} |")
        out.append("")
        return fam

    prim = contrasts("mergeok", "PRIMARY endpoint — merge-clean (CMH stratified by pair, Holm-corrected)")
    seco = contrasts("both", "SECONDARY endpoint — both_passed (CMH stratified by pair, Holm-corrected)")

    # ---- failure taxonomy --------------------------------------------------
    out.append("## Failure taxonomy — merge_outcome per pair-run (validated set, %)")
    out.append("")
    out.append("| arm | pass | solo_rescue | functional_fail | textual_conflict | missing_patch |")
    out.append("|---|---|---|---|---|---|")
    tax = {}
    for prefix, label in ARMS:
        d = data[prefix]
        c = Counter()
        for k in kept:
            if k in d:
                for b, v in d[k]["buckets"].items():
                    c[b] += v
        tot = sum(c.values())
        tax[prefix] = {b: c[b] for b in BUCKETS}
        cells = " | ".join(f"{c[b]/tot:.0%}" if tot else "-" for b in BUCKETS[:5])
        out.append(f"| {label} | {cells} |")
    out.append("")

    # ---- clean vs identical split (transparency) --------------------------
    out.append("## merge status split (validated set, per pair-run)")
    out.append("")
    out.append("| arm | identical | clean | conflicts/other |")
    out.append("|---|---|---|---|")
    for prefix, label in ARMS:
        d = data[prefix]
        n = sum(d[k]["n"] for k in kept if k in d)
        ident = sum(d[k]["identical"] for k in kept if k in d)
        cln = sum(d[k]["clean"] for k in kept if k in d)
        other = n - ident - cln
        out.append(f"| {label} | {ident} ({ident/n:.0%}) | {cln} ({cln/n:.0%}) | {other} ({other/n:.0%}) |")
    out.append("")

    # ---- capability context -----------------------------------------------
    out.append("## Pre-merge capability (feature-independent, validated set)")
    out.append("")
    out.append("| arm | pair-runs w/ ≥1 feature passing independently |")
    out.append("|---|---|")
    for prefix, label in ARMS:
        d = data[prefix]
        cn = sum(d[k]["cap_n"] for k in kept if k in d)
        ca = sum(d[k]["cap_any"] for k in kept if k in d)
        out.append(f"| {label} | {ca/cn:.0%} (n={cn}) |" if cn else f"| {label} | n/a |")
    out.append("")

    # ---- per-pair primary appendix ----------------------------------------
    out.append("## Appendix — per-pair merge-clean rate (validated set)")
    out.append("")
    hdr = "| pair | " + " | ".join(lb for _, lb in ARMS) + " |"
    out.append(hdr)
    out.append("|" + "---|" * (len(ARMS) + 1))
    for k in kept:
        cells = []
        for prefix, _ in ARMS:
            d = data[prefix]
            if k in d and d[k]["n"]:
                cells.append(f"{d[k]['mergeok']/d[k]['n']:.0%}")
            else:
                cells.append("-")
        out.append(f"| {lbl(k)} | " + " | ".join(cells) + " |")
    out.append("")

    report = "\n".join(out)
    print(report)

    if args.json:
        dump = {
            "kept": [lbl(k) for k in kept],
            "dropped": [[lbl(k), why] for k, why in dropped],
            "perarm": {p: perarm[p] for p, _ in ARMS},
            "taxonomy": tax,
            "primary_holm": prim["holm"],
            "secondary_holm": seco["holm"],
        }
        Path(args.json).write_text(json.dumps(dump, indent=2, default=str))
        print(f"\n[wrote {args.json}]")


if __name__ == "__main__":
    main()
