#!/usr/bin/env python3
"""
Reproduces the analysis of the CooperBench shared-git agent-count scaling study.

Input : data/scaling_records.csv  (one row per run: pool, N, score, all_passed, cost)
Output: prints Calculations 1-6 (see explanation.txt for what each one means).

Pure standard library (csv, math) — no numpy/pandas — so it runs anywhere.
Run:   python3 analyze.py
"""

import csv
import math
import os
from collections import defaultdict

DATA = os.path.join(os.path.dirname(__file__), "data", "scaling_records.csv")


# --- load -----------------------------------------------------------------
def load_records(path=DATA):
    """One dict per run. score = n_passed/K (fraction of feature suites passing on
    the integrated tree); cost = API list-price USD summed over the N agents."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "pool_id": r["pool_id"],            # distinct clique: repo/task/features
                    "repo": r["repo"],
                    "N": int(r["N"]),                   # number of agents
                    "score": float(r["score"]),         # graded correctness in [0,1]
                    "all_passed": r["all_passed"] == "True",
                    "cost": float(r["cost"]),           # dollars
                }
            )
    return rows


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


# --- shared math: power-law fit  efficiency = a * N^(-b) ------------------
def power_law_fit(points):
    """Fit y = a * x^(-b) by OLS on log-log: ln(y) = ln(a) - b*ln(x).
    points = list of (x, y) with x>0, y>0. Returns (a, b, r2, n)."""
    pts = [(x, y) for (x, y) in points if x > 0 and y > 0]
    if len(pts) < 2:
        return None
    xs = [math.log(x) for x, _ in pts]
    ys = [math.log(y) for _, y in pts]
    n = len(xs)
    Sx, Sy = sum(xs), sum(ys)
    Sxy = sum(x * y for x, y in zip(xs, ys))
    Sxx = sum(x * x for x in xs)
    denom = n * Sxx - Sx * Sx
    if abs(denom) < 1e-12:
        return None
    b = -(n * Sxy - Sx * Sy) / denom          # reported positive; law is N^(-b)
    lna = (Sy + b * Sx) / n
    a = math.exp(lna)
    yhat = [lna - b * x for x in xs]
    ss_res = sum((y - yh) ** 2 for y, yh in zip(ys, yhat))
    ybar = Sy / n
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return a, b, r2, n


# =========================================================================
# CALCULATION 1 — Aggregate curves by N (mean score, all-pass rate, mean cost)
# =========================================================================
def calc1_aggregate_by_N(recs):
    by_n = defaultdict(list)
    for r in recs:
        by_n[r["N"]].append(r)
    out = {}
    for N in sorted(by_n):
        g = by_n[N]
        out[N] = {
            "n_runs": len(g),
            "mean_score": mean([r["score"] for r in g]),
            "all_pass_rate": sum(1 for r in g if r["all_passed"]) / len(g),
            "mean_cost": mean([r["cost"] for r in g]),
        }
    return out


# =========================================================================
# CALCULATION 2 — Efficiency by N  (work solved per dollar)
# =========================================================================
def calc2_efficiency(agg):
    eff = {N: agg[N]["mean_score"] / agg[N]["mean_cost"] for N in agg}
    solo = eff[min(eff)]
    return {N: {"efficiency": eff[N], "pct_of_solo": 100 * eff[N] / solo} for N in eff}


# =========================================================================
# CALCULATION 3 — Power-law fit of efficiency vs N   (THE headline)
# =========================================================================
def calc3_power_law(eff):
    pts = [(N, eff[N]["efficiency"]) for N in sorted(eff)]
    a, b, r2, n = power_law_fit(pts)
    return {"a": a, "b": b, "r2": r2, "n_points": n, "per_double_factor": 2 ** (-b)}


# =========================================================================
# CALCULATION 4 — Per-pool power law  (universality check)
# =========================================================================
def calc4_per_pool(recs):
    by_pool = defaultdict(lambda: defaultdict(list))
    for r in recs:
        by_pool[r["pool_id"]][r["N"]].append(r)
    fits = {}
    for pool, byn in by_pool.items():
        pts = []
        for N, g in byn.items():
            eff = mean([x["score"] for x in g]) / mean([x["cost"] for x in g])
            pts.append((N, eff))
        if len({x for x, _ in pts}) >= 3:          # need >=3 N-levels to fit
            res = power_law_fit(pts)
            if res:
                a, b, r2, _ = res
                fits[pool] = {"b": b, "r2": r2}
    bs = [f["b"] for f in fits.values()]
    return {
        "fits": fits,
        "n_pools_fit": len(fits),
        "b_min": min(bs), "b_max": max(bs), "b_mean": mean(bs),
        "all_r2_above_0.9": all(f["r2"] > 0.9 for f in fits.values()),
    }


# =========================================================================
# CALCULATION 5 — Degrader classification  (correctness is task-dependent)
# =========================================================================
def calc5_degraders(recs, threshold=0.12):
    by_pool = defaultdict(lambda: defaultdict(list))
    for r in recs:
        by_pool[r["pool_id"]][r["N"]].append(r)
    result = {}
    for pool, byn in by_pool.items():
        means = {N: mean([x["score"] for x in g]) for N, g in byn.items()}
        spread = max(means.values()) - min(means.values())
        result[pool] = {"spread": spread, "degrades": spread >= threshold, "score_by_N": means}
    n_deg = sum(1 for v in result.values() if v["degrades"])
    return {"pools": result, "n_degraders": n_deg, "n_pools": len(result), "threshold": threshold}


# =========================================================================
# CALCULATION 6 — Cost vs N  (near-linear per agent)
# =========================================================================
def calc6_cost(recs, agg):
    # per-pool per-agent increment (pools present at both N=1 and N=4)
    by_pool = defaultdict(lambda: defaultdict(list))
    for r in recs:
        by_pool[r["pool_id"]][r["N"]].append(r)
    incs = []
    for pool, byn in by_pool.items():
        if 1 in byn and 4 in byn:
            c1 = mean([x["cost"] for x in byn[1]])
            c4 = mean([x["cost"] for x in byn[4]])
            incs.append((c4 - c1) / 3.0)
    ns = sorted(agg)
    total_ratio = agg[max(ns)]["mean_cost"] / agg[min(ns)]["mean_cost"]
    return {
        "per_agent_increment_mean": mean(incs) if incs else float("nan"),
        "per_agent_increment_range": (min(incs), max(incs)) if incs else None,
        "cost_ratio_maxN_over_solo": total_ratio,
    }


# --- run & print ----------------------------------------------------------
def main():
    recs = load_records()
    print(f"Loaded {len(recs)} runs across {len({r['pool_id'] for r in recs})} pools "
          f"(N in {sorted({r['N'] for r in recs})}).\n")

    agg = calc1_aggregate_by_N(recs)
    print("CALCULATION 1 — Aggregate by N")
    print(f"  {'N':>2} {'runs':>5} {'mean_score':>11} {'all_pass':>9} {'mean_cost':>10}")
    for N in sorted(agg):
        a = agg[N]
        print(f"  {N:>2} {a['n_runs']:>5} {a['mean_score']:>11.3f} "
              f"{a['all_pass_rate']:>9.2f} ${a['mean_cost']:>8.2f}")

    eff = calc2_efficiency(agg)
    print("\nCALCULATION 2 — Efficiency (solved per $)")
    for N in sorted(eff):
        print(f"  N={N}: {eff[N]['efficiency']:.3f}  ({eff[N]['pct_of_solo']:.0f}% of solo)")

    p = calc3_power_law(eff)
    print("\nCALCULATION 3 — Power-law fit  efficiency = a * N^(-b)")
    print(f"  a = {p['a']:.3f},  b = {p['b']:.3f},  R2 = {p['r2']:.4f}")
    print(f"  => efficiency = {p['a']:.2f} * N^-{p['b']:.2f}   "
          f"(each doubling of N multiplies efficiency by {p['per_double_factor']:.2f})")

    pp = calc4_per_pool(recs)
    print("\nCALCULATION 4 — Per-pool power law (universality)")
    print(f"  {pp['n_pools_fit']} pools fit | exponent b range "
          f"[{pp['b_min']:.2f}, {pp['b_max']:.2f}], mean {pp['b_mean']:.2f} | "
          f"all R2>0.9: {pp['all_r2_above_0.9']}")

    d = calc5_degraders(recs)
    print("\nCALCULATION 5 — Degrader classification (spread >= 0.12)")
    print(f"  {d['n_degraders']} / {d['n_pools']} pools degrade")
    for pool, v in sorted(d["pools"].items()):
        mark = "*" if v["degrades"] else " "
        print(f"   {mark} {pool:34} spread={v['spread']:.2f}")

    c = calc6_cost(recs, agg)
    print("\nCALCULATION 6 — Cost vs N (near-linear)")
    lo, hi = c["per_agent_increment_range"]
    print(f"  per-agent increment: mean ${c['per_agent_increment_mean']:.2f} "
          f"(range ${lo:.2f}-${hi:.2f}) | cost ratio N=4/N=1: {c['cost_ratio_maxN_over_solo']:.1f}x")


if __name__ == "__main__":
    main()
