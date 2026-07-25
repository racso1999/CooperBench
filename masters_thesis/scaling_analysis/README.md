# scaling_analysis — reproducible analysis of the agent-count scaling study

Self-contained. No numpy/pandas.

- `data/scaling_records.csv` — one row per run (148 runs, 14 pools): pool, N,
  score (=n_passed/K), all_passed, cost ($).
- `data/cost_accounts.csv` — same 148 runs, each run's cost split into four
  accounts (context / task / comm / rework) that sum to the run total.
- `analyze.py` — computes Calculations 1-7 (7 = cost-account decomposition).
  Run: `python3 analyze.py`
- `figures.py` — writes `figures/fig2a..2d.png` (2d = stacked cost accounts vs N).
- `explanation.txt` — what each of Calculations 1-7 does and why (numbers match
  the script's CALCULATION blocks).

Headline it reproduces: work-per-dollar collapses as a power law,
efficiency = 1.28 * N^-1.61 (R^2 = 0.996), ~10% of solo at 4 agents.
