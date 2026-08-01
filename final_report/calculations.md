# Calculations

Each section reproduces one headline result, by hand, from `all_runs.csv`. Code: `calculations.py`.

## Calculation 1 — the replication gap

**Claim.** Over 46 matched pairs, pass rate falls from 44.2% (solo) to 12.3% (messaging); Wilcoxon W = 3, p < .001.

**Data.** Arms `flash_solo` and `flash_msg`, excluding `typst_task/6554`: 46 pairs × 3 repeats = 138 runs per condition, each scored by the binary `both_passed`.

**Step 1 — per-pair rate.** A pair passing s of its 3 repeats scores s/3 ∈ {0, ⅓, ⅔, 1}.

**Step 2 — condition mean** = average of the 46 per-pair rates.

| | pairs at 1 | at ⅔ | at ⅓ | at 0 | sum of rates | mean |
|---|---|---|---|---|---|---|
| solo | 17 | 4 | 2 | 23 | 17 + 8/3 + 2/3 = 61/3 | (61/3)/46 = **44.2%** |
| messaging | 4 | 1 | 3 | 38 | 4 + 2/3 + 1 = 17/3 | (17/3)/46 = **12.3%** |

Balanced design (3 repeats per pair) ⇒ equal to the raw run counts: 61/138 and 17/138. Ratio 44.2/12.3 = the 3.6× gap.

**Step 3 — Wilcoxon signed-rank** on the 46 paired differences d = solo − msg. The test throws away the size of the rates and keeps only the *order* of the gaps, so it asks: if the two conditions were equivalent, how unlikely is a split this lopsided?

Count in thirds throughout — d ∈ {0, ±⅓, ±⅔, ±1} exactly. First 10 of the 46 pairs:

| pair | solo | msg | d | \|d\| | rank | goes to |
|---|---|---|---|---|---|---|
| 0/f2_f9 | 0/3 | 0/3 | 0 | — | — | tie, dropped |
| 0/f3_f6 | 3/3 | 0/3 | +1 | 1 | 15 | solo |
| 0/f6_f8 | 3/3 | 0/3 | +1 | 1 | 15 | solo |
| 25/f1_f5 | 0/3 | 0/3 | 0 | — | — | tie, dropped |
| 25/f2_f3 | 3/3 | 1/3 | +⅔ | ⅔ | 7.5 | solo |
| 26/f1_f2 | 0/3 | 0/3 | 0 | — | — | tie, dropped |
| 43/f2_f3 | 1/3 | 0/3 | +⅓ | ⅓ | 3 | solo |
| 43/f3_f7 | 0/3 | 0/3 | 0 | — | — | tie, dropped |
| 56/f1_f5 | 0/3 | 0/3 | 0 | — | — | tie, dropped |
| 68/f1_f5 | 0/3 | 0/3 | 0 | — | — | tie, dropped |

1. **Drop the ties.** 26 pairs have d = 0 (22 failed 0–0 in both arms, 4 passed 3/3 in both) → n = 20 ranked pairs.
2. **Rank |d| ascending; tied values share their average rank.** Five |d| = ⅓ occupy places 1–5 → each ranks **3**; four |d| = ⅔ occupy 6–9 → each **7.5**; eleven |d| = 1 occupy 10–20 → each **15**.
3. **Total the ranks by sign.** Solo wins 19 pairs — four of the five ⅓s, all four ⅔s, all eleven 1s → W⁺ = 4(3) + 4(7.5) + 11(15) = 12 + 30 + 165 = **207**. Messaging wins 1, the fifth ⅓ (pair 1559/f4_f8) → W⁻ = **3**. Check: W⁺ + W⁻ = 210 = n(n+1)/2.
4. **W = min(W⁺, W⁻) = 3** — of 210 available rank points, messaging earned 3 against 105 expected under the null. Normal approximation: μ = n(n+1)/4 = 105; σ² = n(n+1)(2n+1)/24 − Σ(t³−t)/48 = 717.5 − 31.25 = 686.25 (tie groups t = 5, 4, 11), so σ = 26.20; z = (3 − 105)/26.20 = −3.89 → two-sided **p = 9.9×10⁻⁵**.

**Cost-normalised companion.** Per pair: passes summed over 3 repeats ÷ dollars summed over 3 repeats. Aggregate: solo 61 passes / $90.33 = **0.675 per $**; messaging 17 / $158.28 = **0.107 per $** — a 6.3× gap. Same Wilcoxon procedure on the 46 per-pair efficiencies: **W = 2.0, p = 2.4×10⁻⁵**.
