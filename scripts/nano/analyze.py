"""Analyze a nano-py protocol comparison: control vs protocol at k=20.

Reads the eval.json files from two sets of runs (matched by run-name prefix),
aggregates per-pair pass-rates over the k replicates, applies the pre-registered
post-hoc exclusion (drop capability-floor and no-conflict-bite pairs, judged from
the CONTROL arm only), and reports:

  * the pipeline funnel (submitted -> applied -> merge-clean -> both-pass)
  * per-pair rates with Wilson 95% CIs, for control and protocol
  * pooled effect via Cochran-Mantel-Haenszel (stratified by pair) on the
    primary endpoint (merge-clean) and secondary (both_passed)

No third-party deps.  CMH respects the pair clustering (no pseudoreplication);
inference is conditional on these pairs (see docs/nano_py_preregistration.md).

Usage:
  python scripts/nano/analyze.py --control nano_py_control --protocol nano_py_msg
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"

# pre-registered post-hoc exclusion thresholds (judged on control arm)
CEILING_BOTH = 0.60        # drop if naive merge already passes often -> conflict doesn't bite


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


def collect(prefix: str) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for f in glob.glob(str(LOGS / f"{prefix}*" / "**" / "eval.json"), recursive=True):
        try:
            e = json.loads(Path(f).read_text())
        except Exception:
            continue
        key = (e["repo"], e["task_id"], tuple(e.get("features", [])))
        out.setdefault(key, []).append(e)
    return out


def agg(evals: list[dict]) -> dict:
    n = infra = both = clean = f1 = f2 = 0
    for e in evals:
        if e.get("error"):
            infra += 1
            continue
        n += 1
        if e.get("both_passed"):
            both += 1
        if (e.get("merge") or {}).get("status") == "clean":
            clean += 1
        if (e.get("feature1") or {}).get("passed"):
            f1 += 1
        if (e.get("feature2") or {}).get("passed"):
            f2 += 1
    return {"n": n, "infra": infra, "both": both, "clean": clean, "f1": f1, "f2": f2}


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--control", required=True, help="run-name prefix for the no-messaging control")
    ap.add_argument("--protocol", required=True, help="run-name prefix for the protocol arm")
    ap.add_argument("--solo", nargs="*", default=[],
                    help="run-name prefix(es) for solo runs — used to judge CAPABILITY. "
                    "Capability must come from solo (one agent, no merge); the control's "
                    "per-feature passes are unreliable because merge conflicts corrupt the "
                    "code. If omitted, the capability-floor check is skipped (the nano set is "
                    "already curated to be capability-viable).")
    args = ap.parse_args()

    ctrl = {k: agg(v) for k, v in collect(args.control).items()}
    prot = {k: agg(v) for k, v in collect(args.protocol).items()}
    # solo capability: a feature is "doable" if it ever passed in a solo run
    solo = {}
    for pref in args.solo:
        for k, v in collect(pref).items():
            a = agg(v)
            s = solo.setdefault(k, {"f1": 0, "f2": 0})
            s["f1"] += a["f1"]; s["f2"] += a["f2"]
    pairs = sorted(set(ctrl) & set(prot))
    if not pairs:
        print("no overlapping pairs found — check --control/--protocol prefixes and that runs completed")
        return

    # Post-hoc exclusion. CAPABILITY (floor) is judged on the SOLO arm, not the
    # control — in the no-messaging control a merge conflict fails both features'
    # tests regardless of whether each agent implemented correctly, so control
    # per-feature passes cannot distinguish "can't build it" from "merge clobbered
    # it". CONFLICT-BITE (ceiling) is judged on the control.
    kept, dropped = [], []
    for k in pairs:
        c = ctrl[k]
        if c["n"] == 0:
            dropped.append((k, "no control data")); continue
        if args.solo:  # capability floor, from solo
            s = solo.get(k)
            if not s or (s["f1"] == 0 and s["f2"] == 0):
                dropped.append((k, "floor (neither feature solvable solo)")); continue
        if c["both"] / c["n"] > CEILING_BOTH:
            dropped.append((k, f"ceiling (ctrl both {c['both'] / c['n']:.0%})"))
        else:
            kept.append(k)

    def rate(d, key):
        return d[key] / d["n"] if d["n"] else float("nan")

    print("="*92)
    print(f"per-pair both_passed rate (n runs) — control='{args.control}'  protocol='{args.protocol}'")
    print("="*92)
    print(f"{'repo/task/feat':40s} {'ctrl both':>16} {'proto both':>16} {'Δ':>6} keep")
    for k in pairs:
        c, p = ctrl[k], prot[k]
        cb, pb = rate(c, "both"), rate(p, "both")
        clo, chi = wilson(c["both"], c["n"]); plo, phi = wilson(p["both"], p["n"])
        tag = "keep" if k in kept else "DROP"
        lbl = f"{k[0].replace('_task','')}/{k[1]}/{','.join(map(str,k[2]))}"
        print(f"{lbl:40s} {cb:5.0%}[{clo:3.0%},{chi:3.0%}] {pb:5.0%}[{plo:3.0%},{phi:3.0%}] {pb-cb:+5.0%}  {tag}")

    for (k, why) in dropped:
        print(f"  excluded {k[0]}/{k[1]}/{k[2]}: {why}")

    if not kept:
        print("\nall pairs excluded post-hoc — nothing to test")
        return

    # funnel over kept pairs, protocol arm
    tot = {kk: sum(prot[k][kk] for k in kept) for kk in ("n", "clean", "both")}
    subm = sum(prot[k]["n"] for k in kept)  # eval exists => both agents produced output
    print("\nfunnel (protocol arm, kept pairs): "
          f"runs={tot['n']}  merge-clean={tot['clean']/tot['n']:.0%}  both-pass={tot['both']/tot['n']:.0%}")

    for endpoint, key in (("PRIMARY  merge-clean", "clean"), ("secondary both_passed", "both")):
        strata = [(prot[k][key], prot[k]["n"]-prot[k][key], ctrl[k][key], ctrl[k]["n"]-ctrl[k][key]) for k in kept]
        orr, p = cmh(strata)
        csum = sum(ctrl[k][key] for k in kept); csz = sum(ctrl[k]["n"] for k in kept)
        psum = sum(prot[k][key] for k in kept); psz = sum(prot[k]["n"] for k in kept)
        print(f"\n{endpoint}: control {csum/csz:.0%} -> protocol {psum/psz:.0%}  "
              f"(pooled over {len(kept)} pairs)  CMH OR={orr:.2f}  p={p:.4f}  {'*' if p<0.05 else ''}")


if __name__ == "__main__":
    main()
