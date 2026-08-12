# Calculations

The replication study's results, worked through by hand from `all_runs.csv`, as a companion to the
code in `calculations.py` (named function in each heading). The topology results are not hand-worked
here — see Appendix A.3–A.10 of the report and the corresponding functions.

## A.1 — the replication gap (`a1_replication_gap`)

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

## Section 3.5 — capability vs integration (`capability_vs_integration`)

**Claim.** Pairing costs nothing in individual capability; the loss happens at merge. Same data as Calculation 1 (46 pairs × 3 repeats, pooled at run level, n = 138 per condition).

**Capability.** A run is *capability-complete* when all the pair's code was individually written correctly:

- cooperative: both agents' patches pass their **own** suite pre-merge (`a_indep_passed ∧ b_indep_passed`, from our `--eval` extension) → **62/138 = 44.9%**
- solo: the single agent passes **both** suites (`both_passed`) → **61/138 = 44.2%**

62 ≈ 61: splitting the work does not reduce the amount of working code written.

**Integration funnel.** Of the 62 capability-complete cooperative runs:

| outcome | runs |
|---|---|
| survived the merge (`both_passed`) | **17** (27%) |
| lost — `merge_status = conflicts` | **45** (100% of losses) |
| lost — clean merge, tests fail | 0 |

All 17 survivors are genuine clean naive merges (no solo-rescues), and every cooperative success was capability-complete (17 = Calculation 1's messaging total). So the entire solo→messaging drop beyond capability noise, 44.9% → 12.3%, is textual merge conflict — zero functional incompatibilities.

**Checks.** No error rows, no missing independent results; 4 runs with `no_patch` and 12 with zero tests executed all count as failures (none as passes); no pass was recorded with zero tests run.

## A.1 — the cost gap (`a1_cost_gap`)

**Claim.** Solo achieves 0.675 passes per dollar vs 0.107 under messaging — a 6.3× gap, versus 3.6× in raw pass rate.

**Data.** Same 46 pairs × 3 repeats. Cost of a run = `total_cost` (the CLI's `total_cost_usd`, summed over the run's agents; see Appendix A.2 for the price table).

**Aggregate passes per dollar** = total passes ÷ total dollars:

|  | passes | cost | passes/$ |
|---|---|---|---|
| solo | 61 | $90.33 | 61/90.33 = **0.675** |
| messaging | 17 | $158.28 | 17/158.28 = **0.107** |

Gap = 0.675/0.107 = **6.29×**.

**Why it widens from 3.6× to 6.3×.** The ratio factorises exactly:

$$\frac{0.675}{0.107} = \underbrace{\frac{61}{17}}_{3.59\times \text{ fewer passes}} \times \underbrace{\frac{158.28}{90.33}}_{1.75\times \text{ more spent}} = 6.29$$

Messaging fails more often *and* each run costs more (mean $1.147 vs $0.655 per run — two agents, plus message traffic). The cost-normalised gap is the product of the two penalties.

## A.1 — Wilcoxon on per-pair cost efficiency (`a1_cost_efficiency_wilcoxon`)

**Claim.** The efficiency gap is significant: W = 2.0, p < .001.

**Per-pair efficiency** = passes over the pair's 3 repeats ÷ dollars over the same 3 repeats. Test the 46 paired differences d = eff(solo) − eff(msg):

1. **Drop the zeros.** 22 pairs have d = 0 — exactly the pairs with 0 passes in both arms (0/cost = 0 on both sides) → n = 24. Note this n exceeds Calculation 1's 20: the 4 pairs that pass 3/3 in both arms tie on pass rate but *not* on efficiency, because their costs differ.
2. **Rank |d| ascending.** The 24 differences are distinct real numbers — **no ties** (unlike Calculation 1, no shared ranks and no tie correction; the float-tie hazard cannot arise).
3. **Total ranks by sign.** Solo wins 23 of 24. Messaging's one win is again pair 1559/f4_f8 (d = −0.185, rank 2) → W⁻ = **2**, W⁺ = **298**. Check: 300 = n(n+1)/2.
4. **W = min = 2.0.** Normal approximation: μ = n(n+1)/4 = 150, σ = √(n(n+1)(2n+1)/24) = 35.0, z = (2 − 150)/35 = −4.23 → two-sided **p = 2.4×10⁻⁵** (scipy agrees exactly).
