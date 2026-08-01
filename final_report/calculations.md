# Calculations

Each section reproduces one headline result, by hand, from `all_runs.csv`. Code: `calculations.py`.

## Calculation 1 — the replication gap

**Claim.** Over 46 matched pairs, pass rate falls from 44.2% (solo) to 12.3% (messaging); Wilcoxon W = 2.5, p < .001.

**Data.** Arms `flash_solo` and `flash_msg`, excluding `typst_task/6554`: 46 pairs × 3 repeats = 138 runs per condition, each scored by the binary `both_passed`.

**Step 1 — per-pair rate.** A pair passing s of its 3 repeats scores s/3 ∈ {0, ⅓, ⅔, 1}.

**Step 2 — condition mean** = average of the 46 per-pair rates.

| | pairs at 1 | at ⅔ | at ⅓ | at 0 | sum of rates | mean |
|---|---|---|---|---|---|---|
| solo | 17 | 4 | 2 | 23 | 17 + 8/3 + 2/3 = 61/3 | (61/3)/46 = **44.2%** |
| messaging | 4 | 1 | 3 | 38 | 4 + 2/3 + 1 = 17/3 | (17/3)/46 = **12.3%** |

Balanced design (3 repeats per pair) ⇒ equal to the raw run counts: 61/138 and 17/138. Ratio 44.2/12.3 = the 3.6× gap.

**Step 3 — Wilcoxon signed-rank** on the 46 paired differences d = solo − msg:

1. Discard the 26 pairs with d = 0 (22 failed 0–0 in both arms, 4 passed 3/3 in both) → n = 20.
2. Rank |d| ascending, ties share the average rank: five |d| = ⅓ → ranks 1–5; four |d| = ⅔ → ranks 6–9; eleven |d| = 1 → ranks 10–20 (each 15).
3. Sum ranks by sign: solo wins 19 pairs → W⁺ = 207.5; messaging wins 1 (a ⅓-difference) → W⁻ = 2.5. Check: W⁺ + W⁻ = 210 = n(n+1)/2.
4. W = min(W⁺, W⁻) = **2.5**. Normal approximation: μ = n(n+1)/4 = 105, σ² = n(n+1)(2n+1)/24 − tie correction ≈ 686.25, z = (2.5 − 105)/26.2 = −3.91 → two-sided **p = 9.3×10⁻⁵**.

**Cost-normalised companion.** Per pair: passes summed over 3 repeats ÷ dollars summed over 3 repeats. Aggregate: solo 61 passes / $90.33 = **0.675 per $**; messaging 17 / $158.28 = **0.107 per $** — a 6.3× gap. Same Wilcoxon procedure on the 46 per-pair efficiencies: **W = 2.0, p = 2.4×10⁻⁵**.
