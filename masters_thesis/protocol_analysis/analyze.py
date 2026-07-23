"""Analysis for the six-arm nano messaging-protocol study.

This is the script every number in the protocol paper comes from. It reads the
per-run eval.json files for all six no-git coop arms out of the repo's logs/,
applies the pre-registered exclusions (decided on the control arm only), and
prints:

  * a funnel per arm: how many runs applied, merged clean, and passed both features
  * the PRIMARY endpoint  = merge-clean rate (the coordination-specific measure)
  * the SECONDARY endpoint = both_passed, with the same statistics
  * a failure taxonomy showing where each run actually died at merge time
  * pre-merge capability, as context (could each agent build its own feature?)

The primary/secondary rates are tested with a Cochran-Mantel-Haenszel test
stratified by pair, then Holm-corrected across the whole family of contrasts.
Stratifying by pair matters: the k replicate runs of one pair are not independent,
so we can't pool them as if they were. The design is fixed in
docs/nano_py_preregistration.md. One pair per task, so "by pair" == "by task".

A "merge-clean" run is one whose merge status is either "clean" or "identical".
Identical means both agents produced byte-for-byte identical merged code, which git
accepts without a conflict — that is a success, not a fluke, so we count it. The
clean-vs-identical split is reported separately for transparency.

This script is self-contained (pure standard library) and lives alongside the
figures it feeds: figures.py reads the JSON this writes, so the plotted numbers
can never drift from the tables here.

Usage:  python analyze.py            # markdown to stdout + refresh data/nano_study.json
        python analyze.py --json OUT  # write the raw numbers somewhere else
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]      # repo root (masters_thesis/protocol_analysis/ -> up two) — logs/ lives here
LOGS = ROOT / "logs"
DEFAULT_JSON = HERE / "data" / "nano_study.json"

# A merge is a success if it came back clean OR if both agents wrote identical code.
MERGE_OK = {"clean", "identical"}

# Pre-registered exclusion thresholds, both judged on the control arm only.
CEILING_BOTH = 0.60     # drop a pair if the naive merge already passes this often (no conflict to fix)
FLOOR_CAP = 0.10        # drop a pair if neither feature passes solo in more than this (model can't build it)

# The six arms, control first. The prefix is how each arm's run directories are
# named in logs/; the label is what we print. Control has to be first so the
# per-pair exclusions and every "vs control" contrast can find it.
ARMS = [
    ("nano_control", "no-msg (control)"),
    ("nano_msg", "free-text"),
    ("nano_struct", "semi_structured"),
    ("nano_handshake", "plan_handshake"),
    ("nano_dc", "designated_coder"),
    ("nano_coauthor", "coauthor_overlap"),
]

# The mutually-exclusive outcomes a single pair-run can end in.
BUCKETS = ["pass", "solo_rescue", "functional_fail", "textual_conflict", "missing_patch", "unknown"]


# --- statistics helpers ---------------------------------------------------
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion k out of n.

    These are the error bars on each rate. The Wilson interval behaves sensibly
    near 0% and 100% and for small n, where the textbook +/- 1.96*sqrt(p(1-p)/n)
    interval breaks down. z=1.96 gives the 95% level.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    # d is the denominator, c the recentred midpoint, h the half-width.
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def cmh(strata: list[tuple[int, int, int, int]]) -> tuple[float, float]:
    """Cochran-Mantel-Haenszel test across strata (here, one stratum per pair).

    Each stratum is a 2x2 table (a,b,c,d): a=proto_pass, b=proto_fail,
    c=ctrl_pass, d=ctrl_fail. The test pools the effect across strata while
    keeping them separate, so the repeated runs of one pair don't count as
    independent observations. Returns (common odds-ratio, two-sided p-value).
    """
    # num/den accumulate the Mantel-Haenszel chi-square; R/S accumulate the
    # common odds-ratio numerator and denominator.
    num = den = R = S = 0.0
    for a, b, c, d in strata:
        T = a + b + c + d
        if T <= 1:  # a stratum with 0 or 1 observation carries no information
            continue
        # Row and column totals for this table.
        n1, n0, m1 = a + b, c + d, a + c
        # Observed minus expected count in the top-left cell, and its variance.
        num += a - n1 * m1 / T
        den += (n1 * n0 * m1 * (b + d)) / (T * T * (T - 1))
        R += a * d / T
        S += b * c / T
    if den == 0:
        return (float("nan"), 1.0)
    # Continuity-corrected chi-square (1 df); erfc turns it into a two-sided p.
    chi = (abs(num) - 0.5) ** 2 / den
    p = math.erfc(math.sqrt(chi / 2))
    orr = (R / S) if S > 0 else float("inf")
    return (orr, p)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm step-down correction for the family of p-values.

    Sort the p-values ascending, multiply the i-th smallest by (remaining count),
    and keep the running maximum so the adjusted values never decrease. This
    controls the family-wise error rate without assuming the tests are independent.
    """
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj: dict[str, float] = {}
    running = 0.0
    for i, (k, p) in enumerate(items):
        val = min(1.0, (m - i) * p)
        running = max(running, val)
        adj[k] = running
    return adj


# --- loading & tallying ---------------------------------------------------
def pair_outcome(apply_this, apply_partner, merge_status, both) -> str:
    """Classify one pair-run into exactly one outcome bucket.

    This is the failure taxonomy: given whether each agent's patch applied, how the
    merge went, and whether both features passed, decide what actually happened.
    """
    # If either agent never produced an applicable patch, nothing could have merged.
    if apply_this != "applied" or apply_partner != "applied":
        return "missing_patch"
    # Clean merge and both features green: the run we want.
    if both and merge_status in MERGE_OK:
        return "pass"
    # Both features pass but the merge wasn't clean -> one agent's patch carried the
    # pair alone (the "solo rescue" case), not a real joint merge.
    if both:
        return "solo_rescue"
    # Merge was fine but the code doesn't work: a genuine functional failure.
    if merge_status in MERGE_OK:
        return "functional_fail"
    # The patches collided textually — the failure mode this whole study is about.
    if merge_status in ("conflicts", "missing_input"):
        return "textual_conflict"
    return "unknown"


def collect(prefix: str) -> dict[tuple, list[dict]]:
    """Load every eval.json for one arm, grouped by pair.

    An arm is spread across run directories named "<prefix>_<replicate>", so we
    gather all of them and key each eval by its pair (repo, task, feature set).
    """
    out: dict[tuple, list[dict]] = {}
    for f in glob.glob(str(LOGS / f"{prefix}_*" / "**" / "eval.json"), recursive=True):
        # Only accept "<prefix>_<integer>" directories. A sibling like
        # "nano_dc_b2" is a different batch, and its suffix isn't a number, so
        # this digit check keeps it out.
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
    """Tally one pair's replicate runs into counts we can turn into rates."""
    a = {k: 0 for k in ("n", "infra", "applied", "clean", "identical", "mergeok",
                        "both", "cap_any", "cap_n")}
    buckets: Counter = Counter()
    for e in evals:
        # Infrastructure failures (container crashes, apply errors) don't count as
        # task failures — drop them from the denominator entirely.
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
        # Pre-merge capability: did each agent's own feature pass in isolation? We
        # read this from the per-feature independent tests, which run before the
        # merge, so a later conflict can't corrupt the signal.
        i1 = (e.get("feature1_independent") or {}).get("passed")
        i2 = (e.get("feature2_independent") or {}).get("passed")
        if i1 is not None or i2 is not None:
            a["cap_n"] += 1
            if i1 or i2:
                a["cap_any"] += 1
    a["buckets"] = dict(buckets)
    return a


def rate(d: dict, key: str) -> float:
    return d[key] / d["n"] if d["n"] else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(DEFAULT_JSON),
                    help="where to dump the raw numbers (default: data/nano_study.json)")
    args = ap.parse_args()

    # Load and aggregate every arm, keyed by pair.
    data = {prefix: {k: agg(v) for k, v in collect(prefix).items()} for prefix, _ in ARMS}
    ctrl = data["nano_control"]
    all_pairs = sorted(set().union(*[set(d) for d in data.values()]))

    # Pre-registered exclusions, decided from the control arm alone. We never look
    # at a protocol arm to decide what to keep — that would bias the very thing
    # we're testing.
    kept, dropped = [], []
    for k in all_pairs:
        c = ctrl.get(k)
        if not c or c["n"] == 0:
            dropped.append((k, "no control data"))
            continue
        # Capability floor: if neither feature can be built solo, a failure here is
        # a modelling problem, not a coordination problem — drop it.
        cap = c["cap_any"] / c["cap_n"] if c["cap_n"] else None
        if cap is not None and cap <= FLOOR_CAP:
            dropped.append((k, f"floor (control indep-cap {cap:.0%} <= {FLOOR_CAP:.0%})"))
            continue
        # Ceiling: if the naive merge already works most of the time, there's no
        # conflict for a protocol to resolve — drop it too.
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

    # Per-arm funnel and endpoints, pooled over the validated pairs.
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
        # Rough replicates-per-pair, just for the table (total runs / pairs present).
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

    # The contrasts: every protocol vs control, plus a few head-to-heads. Called
    # once for the primary endpoint and once for the secondary.
    def contrasts(key: str, title: str):
        out.append(f"## {title}")
        out.append("")
        fam = {}
        pv = {}
        rows = []
        for prefix, label in ARMS[1:]:
            # One 2x2 table per pair (the CMH stratum): protocol pass/fail vs
            # control pass/fail. cmh pools these while respecting the pairing.
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
        # A few head-to-head contrasts between protocols (base = the second arm).
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
        # Correct the whole family together, then print.
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

    # Failure taxonomy: the share of each arm's runs that landed in each bucket.
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

    # Split the merge-clean successes into "identical" vs "clean" so the reader can
    # see how much of coauthor's win comes from byte-identical merges specifically.
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

    # Context: were the agents even capable of their own feature before merging?
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

    # Per-pair primary-endpoint appendix, so every pair's contribution is visible.
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

    # Write the machine-readable dump — this is what figures.py reads, so the
    # plotted numbers can't drift from the tables above.
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
