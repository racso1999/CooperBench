"""Reproduces the headline calculations of the final report, one function per
Appendix B section. Run from this directory:

    uv run --with pandas --with scipy python calculations.py

Data files, all one row per run, all committed alongside this script:

* ``all_runs.csv``       — replication + protocol studies (Sections 3-4).
* ``leader_records.csv`` — the three topology arms of the scaling and
  supervision studies (Sections 5-6): ``flat`` (N peers), ``leader``
  (Opus supervisor, workers merged each other) and ``leader_central``
  (Sonnet supervisor as sole integrator).  Derived from
  ``results_topo/runs.csv`` by mapping condition -> arm and, for the
  supervised arms, reporting ``agents = workers + 1``.
* ``cost_accounts.csv``  — the four dollar-denominated token accounts per run.

Message-direction and allocation figures are recomputed from the raw agent
logs under ``logs/`` (also committed), so no number in the report rests on an
intermediate file that this script cannot rebuild.
"""

from collections import Counter
from pathlib import Path

import pandas as pd
from scipy.stats import rankdata, wilcoxon

HERE = Path(__file__).parent
DATA = HERE / "all_runs.csv"
LEADER = HERE / "leader_records.csv"
ACCOUNTS = HERE / "cost_accounts.csv"
LOGS = HERE.parent / "logs"


def calculation_1() -> None:
    """Appendix B.1 — the replication gap.

    44.2% (solo) vs 12.3% (messaging) over 46 matched pairs,
    Wilcoxon W = 3, p < .001.
    """
    df = pd.read_csv(DATA)

    # The replication arms, minus typst_task/6554 (intermittent eval-container
    # failures left too few scored runs per pair for a reliable estimate).
    excluded = (df["repo"] == "typst_task") & (df["task_id"] == 6554)
    solo = df[(df["arm"] == "flash_solo") & ~excluded]
    msg = df[(df["arm"] == "flash_msg") & ~excluded]

    # Step 1 — per-pair pass rate: mean of both_passed over each pair's
    # 3 repeats, so every pair scores 0, 1/3, 2/3 or 1.
    solo_rates = solo.groupby(["task_id", "pair"])["both_passed"].mean().astype(float)
    msg_rates = msg.groupby(["task_id", "pair"])["both_passed"].mean().astype(float)

    print("=== Calculation 1: the replication gap ===\n")
    print(f"matched pairs: {len(solo_rates)}   runs per condition: {len(solo)}")
    for name, runs, rates in [("solo", solo, solo_rates), ("messaging", msg, msg_rates)]:
        tally = rates.round(3).value_counts().sort_index(ascending=False)
        tally_str = ", ".join(f"{n} pairs at {v:g}" for v, n in tally.items())
        print(f"\n{name}: {tally_str}")
        print(f"  sum of per-pair rates = {rates.sum():.4f}  ->  mean = {rates.mean():.4f} ({rates.mean() * 100:.1f}%)")
        print(f"  balanced-design check: {int(runs['both_passed'].sum())}/{len(runs)} runs = {runs['both_passed'].mean():.4f}")

    # Step 3 — paired Wilcoxon signed-rank test on the 46 per-pair rates.
    #
    # Counted in passes-out-of-3 (whole numbers), not in thirds-as-decimals:
    # 1 - 2/3 is 0.33333333333333337 in binary, a hair above 1/3, which splits
    # rank ties that are genuinely tied. Whole numbers keep the ties exact.
    solo_passes = solo.groupby(["task_id", "pair"])["both_passed"].sum()
    msg_passes = msg.groupby(["task_id", "pair"])["both_passed"].sum()
    diffs = (solo_passes - msg_passes).astype(float)
    informative = diffs[diffs != 0]
    ranks = pd.Series(rankdata(informative.abs()), index=informative.index)

    w_plus = ranks[informative > 0].sum()
    w_minus = ranks[informative < 0].sum()
    n = len(informative)
    stat, p = wilcoxon(diffs.to_numpy())
    print("\nWilcoxon signed-rank on per-pair rates (differences in units of 1/3):")
    print(f"  zero differences discarded: {(diffs == 0).sum()}   informative pairs: {n}")
    print(f"  solo better: {(informative > 0).sum()}   messaging better: {(informative < 0).sum()}")
    for size, grp in sorted(informative.abs().groupby(informative.abs())):
        print(f"  |d| = {size:.0f}/3: {len(grp)} pairs, shared rank {ranks[grp.index].iloc[0]:.1f}")
    print(f"  W+ = {w_plus:.1f}, W- = {w_minus:.1f}, sum = {w_plus + w_minus:.0f} = n(n+1)/2")
    print(f"  W = {stat:.1f}, p = {p:.3e}")
    # First 10 pairs in data order — the worked table reproduced in Appendix B.1.
    print("\n  pair          solo   msg      d    |d|   rank")
    for key in list(diffs.index)[:10]:
        d = diffs[key]
        cells = [f"{key[0]}/{key[1]}", f"{solo_passes[key]:.0f}/3", f"{msg_passes[key]:.0f}/3"]
        cells += ["0", "-", "-"] if d == 0 else [f"{d:+.0f}/3", f"{abs(d):.0f}/3", f"{ranks[key]:.1f}"]
        print("  {:<12}{:>6}{:>6}{:>7}{:>7}{:>7}".format(*cells))

def calculation_1_5() -> None:
    """Appendix B.1.5 — capability vs integration.

    Pooled over the same 46 pairs x 3 repeats: both paired agents pass
    their own suite pre-merge in 62/138 runs vs the solo condition's
    61/138; only 17 of the 62 survive the merge, and all 45 losses are
    textual merge conflicts.
    """
    df = pd.read_csv(DATA)
    excluded = (df["repo"] == "typst_task") & (df["task_id"] == 6554)
    solo = df[(df["arm"] == "flash_solo") & ~excluded]
    msg = df[(df["arm"] == "flash_msg") & ~excluded].copy()

    # Capability: in the coop condition, each agent's patch tested against its
    # OWN suite in isolation, pre-merge (our --eval extension); in the solo
    # condition, the single agent's patch against both suites.
    msg["both_indep"] = msg["a_indep_passed"].astype(bool) & msg["b_indep_passed"].astype(bool)

    print("=== Calculation 1.5: capability vs integration ===\n")
    coop_cap = int(msg["both_indep"].sum())
    solo_cap = int(solo["both_passed"].sum())
    print(f"coop runs where BOTH agents' independent work passed own suite: {coop_cap}/138 ({coop_cap / 138 * 100:.1f}%)")
    print(f"solo runs where the single agent solved the whole pair:         {solo_cap}/138 ({solo_cap / 138 * 100:.1f}%)")

    # Integration funnel: what happened to the capability-complete coop runs.
    cap = msg[msg["both_indep"]]
    won = cap[cap["both_passed"]]
    lost = cap[~cap["both_passed"].astype(bool)]
    print(f"\nof the {len(cap)} capability-complete coop runs:")
    print(f"  survived the merge (both_passed): {len(won)} ({len(won) / len(cap) * 100:.0f}%)")
    print(f"  merge status of the {len(lost)} losses: {lost['merge_status'].value_counts().to_dict()}")
    print(f"  successes not capability-complete: {int((msg['both_passed'] & ~msg['both_indep']).sum())}")
    print(f"  merge strategy of the successes: {won['merge_strategy'].value_counts().to_dict()}")


def calculation_2() -> None:
    """Appendix B — the cost gap.

    Solo 0.675 vs messaging 0.107 passes per dollar: a 6.3x gap, versus
    3.6x in raw pass rate, because messaging runs also cost 1.75x more.
    """
    df = pd.read_csv(DATA)
    excluded = (df["repo"] == "typst_task") & (df["task_id"] == 6554)
    solo = df[(df["arm"] == "flash_solo") & ~excluded]
    msg = df[(df["arm"] == "flash_msg") & ~excluded]

    print("=== Calculation 2: the cost gap ===\n")
    solo_p, solo_c = int(solo["both_passed"].sum()), solo["total_cost"].sum()
    msg_p, msg_c = int(msg["both_passed"].sum()), msg["total_cost"].sum()
    solo_ppd, msg_ppd = solo_p / solo_c, msg_p / msg_c
    print(f"solo:      {solo_p} passes / ${solo_c:.2f} = {solo_ppd:.3f} passes per dollar")
    print(f"messaging: {msg_p} passes / ${msg_c:.2f} = {msg_ppd:.3f} passes per dollar")
    print(f"gap: {solo_ppd / msg_ppd:.2f}x  (raw pass rate alone: {solo_p / msg_p:.2f}x)")
    # The widening is exactly the extra spend: ppd ratio = pass ratio x cost ratio.
    print(f"decomposition: {solo_p / msg_p:.3f} (pass ratio) x {msg_c / solo_c:.3f} (cost ratio) = {(solo_p / msg_p) * (msg_c / solo_c):.3f}")
    print(f"mean cost per run: solo ${solo['total_cost'].mean():.3f}, messaging ${msg['total_cost'].mean():.3f}")


def calculation_2_5() -> None:
    """Appendix B — Wilcoxon on per-pair cost efficiency.

    W = 2.0, p = 2.4e-05. Unlike calculation 1, the 24 informative
    differences are distinct reals, so there are no rank ties.
    """
    df = pd.read_csv(DATA)
    excluded = (df["repo"] == "typst_task") & (df["task_id"] == 6554)
    solo = df[(df["arm"] == "flash_solo") & ~excluded]
    msg = df[(df["arm"] == "flash_msg") & ~excluded]

    # Per-pair efficiency: passes summed over the 3 repeats / dollars summed.
    solo_eff = solo.groupby(["task_id", "pair"]).agg(p=("both_passed", "sum"), c=("total_cost", "sum"))
    msg_eff = msg.groupby(["task_id", "pair"]).agg(p=("both_passed", "sum"), c=("total_cost", "sum"))
    diffs = (solo_eff["p"] / solo_eff["c"] - msg_eff["p"] / msg_eff["c"]).astype(float)

    informative = diffs[diffs != 0]
    ranks = pd.Series(rankdata(informative.abs()), index=informative.index)
    n = len(informative)
    w_plus = ranks[informative > 0].sum()
    w_minus = ranks[informative < 0].sum()

    print("=== Calculation 2.5: Wilcoxon on per-pair cost efficiency ===\n")
    print(f"zero differences discarded: {(diffs == 0).sum()} (pairs with 0 passes in both arms)")
    print(f"informative pairs: {n}   tied |d| values: {n - informative.abs().nunique()}")
    print(f"solo better: {(informative > 0).sum()}   messaging better: {(informative < 0).sum()}")
    for pair in informative[informative < 0].index:
        print(f"  messaging's win: {pair[0]}/{pair[1]}, d = {informative[pair]:.4f}, rank {ranks[pair]:.0f}")
    print(f"W+ = {w_plus:.0f}, W- = {w_minus:.0f}, sum = {w_plus + w_minus:.0f} = n(n+1)/2")
    stat, p = wilcoxon(diffs.to_numpy())
    print(f"W = {stat:.1f}, p = {p:.3e}")


# ----------------------------------------------------------------------------
# Section 6 — the supervised (centrally-integrated) topology.
# ----------------------------------------------------------------------------


def _power_law(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Least squares of log y = log a - b log N.  Returns (a, b, R^2)."""
    import math

    xs = [math.log(n) for n, _ in points]
    ys = [math.log(y) for _, y in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return math.exp(intercept), -slope, 1 - ss_res / ss_tot


def calculation_3() -> None:
    """Appendix B.3 — the supervised arm by team size.

    Cell means over all pools for each (arm, total agent count): graded score,
    strict all-pass rate, cost, wall-clock, and efficiency = score / cost.
    """
    df = pd.read_csv(LEADER)
    print("B.3  Topology arms by total agent count")
    print(f"  runs: {dict(Counter(df['arm']))}")
    print(f"  spend by arm: {df.groupby('arm')['cost'].sum().round(2).to_dict()}")
    print(f"\n  {'arm':16}{'agents':>7}{'runs':>6}{'score':>8}{'all-pass':>10}{'cost':>9}{'wall/min':>10}{'eff':>8}")
    for arm in ("flat", "leader", "leader_central"):
        for n, g in df[df["arm"] == arm].groupby("agents"):
            score, cost = g["score"].mean(), g["cost"].mean()
            print(
                f"  {arm:16}{n:>7}{len(g):>6}{score:>8.3f}"
                f"{g['all_passed'].astype(str).str.lower().eq('true').mean():>10.3f}"
                f"{cost:>9.2f}{g['wall_seconds'].mean() / 60:>10.1f}{score / cost:>8.3f}"
            )


def calculation_3_5() -> None:
    """Appendix B.4 — efficiency power laws and the crossover.

    Fit efficiency(N) = a * N^-b to the per-N cell means of each arm, then
    solve a1 N^-b1 = a2 N^-b2 for the crossover.
    """
    import math

    df = pd.read_csv(LEADER)
    fits = {}
    for arm in ("flat", "leader", "leader_central"):
        g = df[df["arm"] == arm].groupby("agents")
        pts = [(n, s["score"].mean() / s["cost"].mean()) for n, s in g]
        a, b, r2 = _power_law(pts)
        fits[arm] = (a, b)
        pretty = "  ".join(f"N={n}:{e:.3f}" for n, e in pts)
        print(f"B.4  {arm:16} eff = {a:.3f} * N^-{b:.3f}   R2 = {r2:.3f}   [{pretty}]")
    (a1, b1), (a2, b2) = fits["flat"], fits["leader_central"]
    print(f"     crossover flat vs leader_central: N = {math.exp(math.log(a2 / a1) / (b2 - b1)):.2f} agents")
    (a3, b3) = fits["leader"]
    print(f"     crossover flat vs leader (opus):  N = {math.exp(math.log(a3 / a1) / (b3 - b1)):.2f} agents")


def calculation_4() -> None:
    """Appendix B.5 — pool-matched comparison, supervised vs flat.

    Each arm is first averaged within a pool, then compared only on pools both
    arms cover, so an uneven pool mix cannot drive the ratio.
    """
    df = pd.read_csv(LEADER)
    cell = df.groupby(["arm", "agents", "pool_id"])[["cost", "score", "wall_seconds"]].mean()
    print("B.5  Pool-matched: leader_central vs flat, equal total agent count")
    for n in sorted(df[df["arm"] == "leader_central"]["agents"].unique()):
        try:
            sup, flat = cell.loc[("leader_central", n)], cell.loc[("flat", n)]
        except KeyError:
            continue
        common = sorted(set(sup.index) & set(flat.index))
        if not common:
            continue
        s, f = sup.loc[common], flat.loc[common]
        eff = (s["score"].mean() / s["cost"].mean()) / (f["score"].mean() / f["cost"].mean())
        print(
            f"  {n} agents ({len(common)} pools): sup ${s['cost'].mean():.2f}/{s['score'].mean():.3f}"
            f"  flat ${f['cost'].mean():.2f}/{f['score'].mean():.3f}"
            f"  cost x{s['cost'].mean() / f['cost'].mean():.2f}  eff x{eff:.2f}"
            f"  cheaper on {(s['cost'] < f['cost']).sum()}/{len(common)}"
        )


def calculation_4_5() -> None:
    """Appendix B.6 — what centralising integration changed.

    leader_central vs leader on the pools both cover, at equal worker count.
    The two arms differ in who merges AND in leader model (Sonnet vs Opus).
    """
    df = pd.read_csv(LEADER)
    cell = df.groupby(["arm", "workers", "pool_id"])[["cost", "score"]].mean()
    print("B.6  leader_central vs leader (Opus), equal worker count")
    for w in sorted(df[df["arm"] == "leader_central"]["workers"].unique()):
        try:
            c, o = cell.loc[("leader_central", w)], cell.loc[("leader", w)]
        except KeyError:
            continue
        common = sorted(set(c.index) & set(o.index))
        if not common:
            continue
        cc, oo = c.loc[common], o.loc[common]
        print(
            f"  {w} workers ({len(common)} pools): central ${cc['cost'].mean():.2f}/{cc['score'].mean():.3f}"
            f"  opus ${oo['cost'].mean():.2f}/{oo['score'].mean():.3f}"
            f"  cost x{cc['cost'].mean() / oo['cost'].mean():.2f}"
        )


def calculation_5() -> None:
    """Appendix B.7 — outcome mix and the cost accounts by topology.

    'Partial' = a run scoring strictly between 0 and 1 (some features pass).
    Account shares are comm+rework as a fraction of the run's four accounts.
    """
    df = pd.read_csv(LEADER)
    print("B.7  Outcome mix (share of runs)")
    for arm in ("flat", "leader_central"):
        for n, g in df[df["arm"] == arm].groupby("agents"):
            s = g["score"]
            print(
                f"  {arm:16} N={n}  zero {(s == 0).mean():.3f}  partial {((s > 0) & (s < 1)).mean():.3f}"
                f"  full {(s == 1).mean():.3f}   (n={len(g)})"
            )
    acc = pd.read_csv(ACCOUNTS)
    acc["total"] = acc[["context_usd", "task_usd", "comm_usd", "rework_usd"]].sum(axis=1)
    acc["msg_share"] = (acc["comm_usd"] + acc["rework_usd"]) / acc["total"]
    print("\n     comm+rework share of run cost")
    for arm in ("flat", "leader_central"):
        for n, g in acc[acc["arm"] == arm].groupby("agents"):
            print(f"  {arm:16} N={n}  {g['msg_share'].mean():.3f}  (n={len(g)})")


def calculation_6() -> None:
    """Appendix B.8 — message directions and integration behaviour.

    Recomputed from the committed agent logs.  'agent1' is the supervisor in
    the supervised arms.  A worker is counted as having merged a peer if its
    stream contains a `git merge team/<other worker>` invocation.
    """
    import json
    import re

    for arm, glob in (("leader_central", "scaling_*_leader_central"), ("leader", "scaling_*_leader")):
        dirs = [d for d in LOGS.glob(f"{glob}/scaling/*/*/*/*") if d.is_dir()]
        if arm == "leader":  # the _leader_central tree also matches scaling_*_leader
            dirs = [d for d in dirs if "_leader_central" not in str(d)]
        pairs, merged, workers_seen = Counter(), 0, 0
        for d in dirs:
            for f in sorted(d.glob("agent*_sent.jsonl")):
                sender = f.name.split("_sent")[0]
                for line in f.read_text(errors="ignore").splitlines():
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    role = lambda a: "leader" if a == "agent1" else "worker"  # noqa: E731
                    pairs[f"{role(sender)}->{role(rec.get('to', '?'))}"] += 1
            streams = sorted(d.glob("agent*_stream.jsonl"))
            if len(streams) < 3:  # need >=2 workers for "merged a peer" to mean anything
                continue
            for s in streams:
                aid = s.name.split("_stream")[0]
                if aid == "agent1":
                    continue
                workers_seen += 1
                tgts = set(re.findall(r"git\s+merge\s+(?:--no-edit\s+)?team/(agent\d+)", s.read_text(errors="ignore")))
                if tgts - {aid, "agent1"}:
                    merged += 1
        total = sum(pairs.values())
        print(f"B.8  {arm}: {len(dirs)} run dirs, {total} messages")
        for k, v in pairs.most_common():
            print(f"       {k:18} {v:5d}  ({v / total:.1%})" if total else f"       {k}: {v}")
        if workers_seen:
            print(f"       workers merging a peer: {merged}/{workers_seen} ({merged / workers_seen:.1%})")


def calculation_7() -> None:
    """Appendix B.9 — wall-clock time and realised speedup by topology.

    Speedup is paired within a pool: the flat solo (1-agent) mean time for that
    pool divided by the arm's mean time for that pool at team size N, then
    averaged over pools.  Ideal perfect parallelism would give N.
    """
    df = pd.read_csv(LEADER)
    df["wall_min"] = df["wall_seconds"] / 60
    solo = df[(df["arm"] == "flat") & (df["agents"] == 1)].groupby("pool_id")["wall_min"].mean()
    print(f"B.9  flat solo baseline: {solo.mean():.1f} min over {len(solo)} pools")
    for arm in ("flat", "leader_central"):
        for n, g in df[(df["arm"] == arm) & (df["agents"] > 1)].groupby("agents"):
            m = g.groupby("pool_id")["wall_min"].mean()
            common = m.index.intersection(solo.index)
            sp = (solo[common] / m[common]).mean()
            print(f"  {arm:16} N={n}  {g['wall_min'].mean():5.1f} min   speedup {sp:.2f}x   (n={len(g)})")


if __name__ == "__main__":
    calculation_1()
    print()
    calculation_1_5()
    print()
    calculation_2()
    print()
    calculation_2_5()
    for f in (calculation_3, calculation_3_5, calculation_4, calculation_4_5, calculation_5, calculation_6, calculation_7):
        print()
        f()
