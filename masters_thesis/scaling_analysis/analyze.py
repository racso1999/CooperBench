#!/usr/bin/env python3

import csv
import math
import os
from collections import defaultdict 

DATA = os.path.join(os.path.dirname(__file__), "data", "scaling_records.csv") #load data
ACCOUNTS = os.path.join(os.path.dirname(__file__), "data", "cost_accounts.csv")  # per-run $ decomposition


#comnvert csv to dict <- 1 dict per run
def load_records(path=DATA):

    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "pool_id": r["pool_id"],            # distinct clique: repo/task/features
                    "repo": r["repo"],
                    "N": int(r["N"]),                   # number of agents
                    "score": float(r["score"]),         # number of features that pass test suite
                    "all_passed": r["all_passed"] == "True",
                    "cost": float(r["cost"]),           # cost in dollars
                    # wall-clock seconds for the cell (agents run in parallel, so
                    # this tracks the slowest agent; eval time excluded)
                    "wall_seconds": float(r["wall_seconds"]) if r.get("wall_seconds") else None,
                }
            )
    return rows


# One dict per run holding the four dollar accounts. Each run's cost is apportioned
# across context / task / comm / rework so the four sum back to the run's total cost
# (they are a partition of it), which is what makes their per-N shares meaningful.
def load_accounts(path=ACCOUNTS):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "pool_id": r["pool_id"],
                    "N": int(r["N"]),
                    "context_usd": float(r["context_usd"]),   # each agent re-loads the shared repo
                    "task_usd": float(r["task_usd"]),          # implementing assigned features
                    "comm_usd": float(r["comm_usd"]),          # messages sent/received/re-ingested
                    "rework_usd": float(r["rework_usd"]),      # re-editing files after an inbound message
                }
            )
    return rows


#Helper functin to fix zero division errors

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



# CALCULATION 1 — Aggregate curves by N (mean score, all-pass rate, mean cost)
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



# CALCULATION 2 — Efficiency by N  (work solved per dollar)

def calc2_efficiency(agg):
    eff = {N: agg[N]["mean_score"] / agg[N]["mean_cost"] for N in agg}
    solo = eff[min(eff)]
    return {N: {"efficiency": eff[N], "pct_of_solo": 100 * eff[N] / solo} for N in eff}



# CALCULATION 3 — Power-law fit of efficiency vs N   (THE headline)

def calc3_power_law(eff):
    pts = [(N, eff[N]["efficiency"]) for N in sorted(eff)]
    a, b, r2, n = power_law_fit(pts)
    return {"a": a, "b": b, "r2": r2, "n_points": n, "per_double_factor": 2 ** (-b)}



# CALCULATION 4 — Per-pool power law  (universality check)

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



# CALCULATION 5 — Degrader classification  (correctness is task-dependent)

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



# CALCULATION 6 — Cost vs N  (near-linear per agent)

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


# CALCULATION 7 — Cost-account decomposition  (where the tax is paid)
#
# For each N, mean the four dollar accounts across runs and report two shares of
# the total run cost:
#   comm_share        = comm / total                 (messaging channel alone)
#   comm_rework_share = (comm + rework) / total       (messaging + the rework it triggers)
# The gap between the two is the message-triggered rework. Both are reported because
# the paper distinguishes messaging strictly (~a quarter) from all messaging-related
# cost (~a third).
def calc7_cost_accounts(accts):
    by_n = defaultdict(list)
    for r in accts:
        by_n[r["N"]].append(r)
    out = {}
    for N in sorted(by_n):
        g = by_n[N]
        ctx = mean([r["context_usd"] for r in g])
        task = mean([r["task_usd"] for r in g])
        comm = mean([r["comm_usd"] for r in g])
        rework = mean([r["rework_usd"] for r in g])
        total = ctx + task + comm + rework
        out[N] = {
            "n_runs": len(g),
            "context": ctx, "task": task, "comm": comm, "rework": rework, "total": total,
            "comm_share": comm / total if total else float("nan"),
            "comm_rework_share": (comm + rework) / total if total else float("nan"),
        }
    return out


# run all calculations and print results
# CALCULATION 8 — Wall-clock time & parallel speedup (does sharing work finish faster?)

def calc8_time(recs):
    """Per-N mean wall-clock, plus per-pool paired speedup vs the solo baseline:
    speedup(N) = mean wall(N=1) / mean wall(N); efficiency = speedup / N (1.0 =
    perfect work-sharing, ideal wall time T1/N). Pairing within a pool removes
    pool-difficulty heterogeneity."""
    timed = [r for r in recs if r["wall_seconds"] is not None]
    by_n = defaultdict(list)
    by_pool_n = defaultdict(lambda: defaultdict(list))
    for r in timed:
        by_n[r["N"]].append(r["wall_seconds"])
        by_pool_n[r["pool_id"]][r["N"]].append(r["wall_seconds"])
    out = {N: {"n_runs": len(v), "mean_wall_s": mean(v)} for N, v in sorted(by_n.items())}
    for N in out:
        if N == 1:
            continue
        sps = [mean(p[1]) / mean(p[N]) for p in by_pool_n.values() if 1 in p and N in p and mean(p[N]) > 0]
        if sps:
            out[N]["speedup_mean"] = mean(sps)
            out[N]["efficiency"] = mean(sps) / N
            out[N]["n_pools"] = len(sps)
    return out


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

    ca = calc7_cost_accounts(load_accounts())
    print("\nCALCULATION 7 — Cost-account decomposition (context / task / comm / rework)")
    print(f"  {'N':>2} {'context':>8} {'task':>8} {'comm':>8} {'rework':>8} {'total':>8}"
          f" {'comm%':>7} {'comm+rwk%':>10}")
    for N in sorted(ca):
        a = ca[N]
        print(f"  {N:>2} ${a['context']:>7.2f} ${a['task']:>7.2f} ${a['comm']:>7.3f} "
              f"${a['rework']:>7.3f} ${a['total']:>7.2f} {a['comm_share']*100:>6.1f}% "
              f"{a['comm_rework_share']*100:>9.1f}%")
    multi = [ca[N] for N in ca if N > 1]
    if multi:
        print(f"  across N>=2: comm alone {min(a['comm_share'] for a in multi)*100:.0f}-"
              f"{max(a['comm_share'] for a in multi)*100:.0f}% of cost; "
              f"comm+rework {min(a['comm_rework_share'] for a in multi)*100:.0f}-"
              f"{max(a['comm_rework_share'] for a in multi)*100:.0f}%")

    t = calc8_time(recs)
    print("\nCALCULATION 8 — Wall-clock time & parallel speedup")
    print(f"  {'N':>2} {'runs':>5} {'wall(min)':>10} {'speedup':>8} {'ideal':>6} {'par.eff':>8}")
    for N in sorted(t):
        a = t[N]
        sp = f"{a['speedup_mean']:.2f}x" if "speedup_mean" in a else "—"
        ef = f"{a['efficiency']:.2f}" if "efficiency" in a else "—"
        ideal = f"{N:.1f}x" if N > 1 else "—"
        print(f"  {N:>2} {a['n_runs']:>5} {a['mean_wall_s']/60:>10.1f} {sp:>8} {ideal:>6} {ef:>8}")


if __name__ == "__main__":
    main()
