#!/usr/bin/env python3
"""Leader-topology (supervised) scaling analysis.

Mirrors analyze.py's calculations for the second scaling study, in which the K
features are handed to a *supervisor* that allocates them across N workers,
instead of being dealt round-robin to N peers.  Both arms are held in
data/leader_records.csv (arm = flat|leader) so every calculation below is a
paired flat-vs-leader comparison on the same 14 pools.

Team size convention: the leader is a real agent, so a leader run with N workers
is reported at N+1 agents.  This is what makes the arms comparable — 4 agents is
4 peers in the flat arm and 1 supervisor + 3 workers in the leader arm.
"""

import csv
import math
import os
from collections import defaultdict

DATA = os.path.join(os.path.dirname(__file__), "data", "leader_records.csv")
ACCOUNTS = os.path.join(os.path.dirname(__file__), "data", "cost_accounts.csv")


def load_records(path=DATA):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "pool_id": r["pool_id"],
                    "repo": r["repo"],
                    "K": int(r["K"]),
                    "arm": r["arm"],                       # flat | leader
                    "agents": int(r["agents"]),            # total agents (leader counts the supervisor)
                    "score": float(r["score"]),            # fraction of K suites passing
                    "all_passed": r["all_passed"] in ("True", "true", True),
                    "cost": float(r["cost"]),              # list-price USD, whole run
                    "leader_cost": float(r["leader_cost"]) if r["leader_cost"] else 0.0,
                    "wall_seconds": float(r["wall_seconds"]) if r["wall_seconds"] else None,
                    "agent_seconds": float(r["agent_seconds"]) if r["agent_seconds"] else None,
                }
            )
    return rows


def load_accounts(path=ACCOUNTS):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"pool_id": r["pool_id"], "arm": r["arm"], "agents": int(r["agents"]),
                         **{k: float(r[k]) for k in ("context_usd", "task_usd", "comm_usd", "rework_usd")}})
    return rows


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def power_law_fit(points):
    """y = a * x^(-b) by OLS on log-log. Returns (a, b, r2, n) or None."""
    pts = [(x, y) for x, y in points if x > 0 and y > 0]
    if len({x for x, _ in pts}) < 2:
        return None
    xs = [math.log(x) for x, _ in pts]
    ys = [math.log(y) for _, y in pts]
    n = len(xs)
    Sx, Sy = sum(xs), sum(ys)
    Sxy = sum(x * y for x, y in zip(xs, ys))
    Sxx = sum(x * x for x in xs)
    den = n * Sxx - Sx * Sx
    if abs(den) < 1e-12:
        return None
    slope = (n * Sxy - Sx * Sy) / den
    inter = (Sy - slope * Sx) / n
    yhat = [inter + slope * x for x in xs]
    ybar = Sy / n
    sst = sum((y - ybar) ** 2 for y in ys)
    r2 = 1 - sum((y - h) ** 2 for y, h in zip(ys, yhat)) / sst if sst > 0 else float("nan")
    return math.exp(inter), -slope, r2, n


# L1 — aggregate by arm x team size
def calc1_aggregate(recs):
    by = defaultdict(list)
    for r in recs:
        by[(r["arm"], r["agents"])].append(r)
    out = {}
    for k, g in sorted(by.items()):
        walls = [r["wall_seconds"] for r in g if r["wall_seconds"]]
        out[k] = {
            "n_runs": len(g),
            "mean_score": mean([r["score"] for r in g]),
            "all_pass_rate": sum(1 for r in g if r["all_passed"]) / len(g),
            "mean_cost": mean([r["cost"] for r in g]),
            "mean_wall_s": mean(walls) if walls else None,
            "mean_leader_cost": mean([r["leader_cost"] for r in g]),
        }
    return out


# L2/L3 — efficiency and its power law, per arm
def calc2_efficiency(agg):
    return {k: v["mean_score"] / v["mean_cost"] for k, v in agg.items()}


def calc3_power_law(eff, arm):
    pts = [(n, e) for (a, n), e in sorted(eff.items()) if a == arm]
    res = power_law_fit(pts)
    if not res:
        return None
    a, b, r2, n = res
    return {"a": a, "b": b, "r2": r2, "n_points": n, "points": pts}


# L4 — outcome distribution: zero / partial / perfect
def calc4_outcome_mix(recs):
    by = defaultdict(list)
    for r in recs:
        by[(r["arm"], r["agents"])].append(r["score"])
    out = {}
    for k, sc in sorted(by.items()):
        z = sum(1 for s in sc if s == 0)
        p = sum(1 for s in sc if s == 1.0)
        out[k] = {"n": len(sc), "zero": z / len(sc), "partial": (len(sc) - z - p) / len(sc), "perfect": p / len(sc)}
    return out


# L5 — paired per-pool comparison at matched team size
def calc5_paired(recs):
    cell = defaultdict(list)
    for r in recs:
        cell[(r["pool_id"], r["arm"], r["agents"])].append(r)
    pools = sorted({p for p, _, _ in cell})
    out = {}
    for n in (2, 3, 4, 5):
        ps = [p for p in pools if (p, "leader", n) in cell and (p, "flat", n) in cell]
        if not ps:
            continue
        def m(arm, field):
            return [mean([r[field] for r in cell[(p, arm, n)] if r[field] is not None]) for p in ps]
        out[n] = {
            "n_pools": len(ps),
            "score_flat": mean(m("flat", "score")), "score_leader": mean(m("leader", "score")),
            "cost_flat": mean(m("flat", "cost")), "cost_leader": mean(m("leader", "cost")),
            "wall_flat": mean(m("flat", "wall_seconds")), "wall_leader": mean(m("leader", "wall_seconds")),
        }
    return out


# L6 — cost accounts (context / task / comm / rework)
def calc6_accounts(accts):
    by = defaultdict(list)
    for r in accts:
        by[(r["arm"], r["agents"])].append(r)
    out = {}
    for k, g in sorted(by.items()):
        acc = {f: mean([r[f + "_usd"] for r in g]) for f in ("context", "task", "comm", "rework")}
        tot = sum(acc.values())
        out[k] = {**acc, "total": tot, "n": len(g),
                  "comm_share": acc["comm"] / tot if tot else 0,
                  "comm_rework_share": (acc["comm"] + acc["rework"]) / tot if tot else 0}
    return out


# L7 — wall-clock and parallel speedup vs the flat solo baseline
def calc7_time(recs):
    solo = defaultdict(list)
    for r in recs:
        if r["arm"] == "flat" and r["agents"] == 1 and r["wall_seconds"]:
            solo[r["pool_id"]].append(r["wall_seconds"])
    base = {k: mean(v) for k, v in solo.items()}
    by = defaultdict(list)
    for r in recs:
        if r["wall_seconds"]:
            by[(r["arm"], r["agents"])].append(r)
    out = {}
    for k, g in sorted(by.items()):
        sp = [base[r["pool_id"]] / r["wall_seconds"] for r in g if r["pool_id"] in base and r["wall_seconds"] > 0]
        out[k] = {"mean_wall_s": mean([r["wall_seconds"] for r in g]),
                  "mean_agent_s": mean([r["agent_seconds"] for r in g if r["agent_seconds"]]),
                  "speedup": mean(sp) if sp else None,
                  "efficiency": (mean(sp) / k[1]) if sp else None, "n": len(g)}
    return out


def main():
    recs = load_records()
    pools = {r["pool_id"] for r in recs}
    print(f"Loaded {len(recs)} runs across {len(pools)} pools "
          f"(flat={sum(1 for r in recs if r['arm']=='flat')}, leader={sum(1 for r in recs if r['arm']=='leader')}).\n")

    agg = calc1_aggregate(recs)
    print("L1 — AGGREGATE BY ARM x TEAM SIZE")
    print(f"  {'arm':7}{'agents':>7}{'runs':>6}{'score':>8}{'all_pass':>10}{'cost':>9}{'wall(min)':>11}{'lead$':>8}")
    for (arm, n), a in agg.items():
        w = f"{a['mean_wall_s']/60:.1f}" if a["mean_wall_s"] else "-"
        print(f"  {arm:7}{n:>7}{a['n_runs']:>6}{a['mean_score']:>8.3f}{a['all_pass_rate']:>10.0%}"
              f"${a['mean_cost']:>8.2f}{w:>11}${a['mean_leader_cost']:>7.2f}")

    eff = calc2_efficiency(agg)
    print("\nL2/L3 — EFFICIENCY (score per $) AND POWER LAW")
    for arm in ("flat", "leader"):
        pl = calc3_power_law(eff, arm)
        if not pl:
            continue
        pts = "  ".join(f"N={n}:{e:.3f}" for n, e in pl["points"])
        print(f"  {arm:7} {pts}")
        print(f"          efficiency = {pl['a']:.2f} * N^-{pl['b']:.2f}   (R2={pl['r2']:.3f})")

    mix = calc4_outcome_mix(recs)
    print("\nL4 — OUTCOME MIX (zero / partial / perfect)")
    for (arm, n), v in mix.items():
        print(f"  {arm:7} agents={n} n={v['n']:>3}: zero={v['zero']:>5.0%} partial={v['partial']:>5.0%} perfect={v['perfect']:>5.0%}")

    pair = calc5_paired(recs)
    print("\nL5 — PAIRED BY POOL, MATCHED TEAM SIZE (flat -> leader)")
    for n, v in pair.items():
        print(f"  {n} agents ({v['n_pools']} pools): score {v['score_flat']:.2f}->{v['score_leader']:.2f} "
              f"({v['score_leader']-v['score_flat']:+.2f})  cost ${v['cost_flat']:.2f}->${v['cost_leader']:.2f} "
              f"({(v['cost_leader']/v['cost_flat']-1)*100:+.0f}%)  wall {v['wall_flat']/60:.1f}->{v['wall_leader']/60:.1f}min")

    acc = calc6_accounts(load_accounts())
    print("\nL6 — COST ACCOUNTS ($; context/task/comm/rework)")
    print(f"  {'arm':7}{'agents':>7}{'context':>9}{'task':>8}{'comm':>8}{'rework':>8}{'total':>8}{'comm%':>7}{'c+r%':>7}")
    for (arm, n), a in acc.items():
        print(f"  {arm:7}{n:>7}{a['context']:>9.2f}{a['task']:>8.2f}{a['comm']:>8.2f}{a['rework']:>8.2f}"
              f"{a['total']:>8.2f}{a['comm_share']*100:>6.0f}%{a['comm_rework_share']*100:>6.0f}%")

    t = calc7_time(recs)
    print("\nL7 — WALL-CLOCK AND PARALLEL SPEEDUP (vs flat solo)")
    print(f"  {'arm':7}{'agents':>7}{'wall(min)':>11}{'agent(min)':>12}{'speedup':>9}{'par.eff':>9}")
    for (arm, n), v in t.items():
        sp = f"{v['speedup']:.2f}x" if v["speedup"] else "-"
        ef = f"{v['efficiency']:.2f}" if v["efficiency"] else "-"
        print(f"  {arm:7}{n:>7}{v['mean_wall_s']/60:>11.1f}{v['mean_agent_s']/60:>12.1f}{sp:>9}{ef:>9}")


if __name__ == "__main__":
    main()
