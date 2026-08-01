"""Reproduces the headline calculations of the final report, one function per
Appendix B section. Run from this directory:

    uv run --with pandas --with scipy python calculations.py

Data: all_runs.csv (copied from results_csv/), one row per run.
"""

from pathlib import Path

import pandas as pd
from scipy.stats import wilcoxon

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
    diffs = solo_rates - msg_rates
    stat, p = wilcoxon(solo_rates.to_numpy(), msg_rates.to_numpy())
    print(f"\nWilcoxon signed-rank on per-pair rates:")
    print(f"  zero differences discarded: {(diffs == 0).sum()}   informative pairs: {(diffs != 0).sum()}")
    print(f"  solo better: {(diffs > 0).sum()}   messaging better: {(diffs < 0).sum()}")
    print(f"  W = {stat}, p = {p:.3e}")

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


if __name__ == "__main__":
    calculation_1()
