"""Reproduces the headline calculations of the final report, one function per
Appendix B section. Run from this directory:

    uv run --with pandas --with scipy python calculations.py

Data: all_runs.csv (copied from results_csv/), one row per run.
"""

from pathlib import Path

import pandas as pd
from scipy.stats import rankdata, wilcoxon

DATA = Path(__file__).parent / "all_runs.csv"


def calculation_1() -> None:
    """Appendix B.1 — the replication gap.

    44.2% (solo) vs 12.3% (messaging) over 46 matched pairs,
    Wilcoxon W = 2.5, p < .001; cost-normalised 0.675 vs 0.107
    passes per dollar, W = 2.0, p < .001.
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

    # Cost-normalised companion: per-pair passes summed over the 3 repeats,
    # divided by summed dollar cost.
    solo_eff = solo.groupby(["task_id", "pair"]).agg(passed=("both_passed", "sum"), cost=("total_cost", "sum"))
    msg_eff = msg.groupby(["task_id", "pair"]).agg(passed=("both_passed", "sum"), cost=("total_cost", "sum"))
    solo_ppd = solo_eff["passed"].sum() / solo_eff["cost"].sum()
    msg_ppd = msg_eff["passed"].sum() / msg_eff["cost"].sum()
    stat2, p2 = wilcoxon(
        (solo_eff["passed"] / solo_eff["cost"]).astype(float).to_numpy(),
        (msg_eff["passed"] / msg_eff["cost"]).astype(float).to_numpy(),
    )
    print(f"\ncost-normalised (passes per dollar):")
    print(f"  solo: {solo_ppd:.3f}   messaging: {msg_ppd:.3f}   ratio: {solo_ppd / msg_ppd:.1f}x")
    print(f"  W = {stat2}, p = {p2:.3e}")


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


if __name__ == "__main__":
    calculation_1()
    print()
    calculation_1_5()
