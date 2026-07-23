# masters_thesis

Reproducible analysis packages and frozen data for the thesis. Each subfolder is
self-contained: a stdlib-only `analyze.py` that computes the numbers, a
matplotlib `figures.py` that reads the frozen data (so plots can't drift from the
tables), a `data/` artifact, and the rendered `figures/`.

## `scaling_analysis/` — the agent-count scaling study

How coordination cost scales as a fixed workload is split across N ∈ {1,2,3,4}
agents. Headline: efficiency collapses as a power law, ≈ 1.28·N^−1.61.

- `analyze.py` — reads `data/scaling_records.csv` (148 runs, 14 pools), prints Calculations 1–6.
- `figures.py` → `figures/fig2a_correctness.png`, `fig2b_cost.png`, `fig2c_efficiency.png`.
- Paper: `../paper.md` (scaling-study sections).

```bash
uv run python masters_thesis/scaling_analysis/analyze.py
uv run --with matplotlib --with numpy python masters_thesis/scaling_analysis/figures.py
```

## `protocol_analysis/` — the messaging-protocol study

Six coordination protocols compared at team size two on the capability-screened
nano subset. Headline: only resolving the shared construct works — coauthor_overlap
lifts the merge-clean rate from 13% to 78%.

- `analyze.py` — reads the six arms' `eval.json` from the repo's `logs/`, applies the
  pre-registered exclusions, prints the tables, and writes `data/nano_study.json`.
- `figures.py` → `figures/fig1_endpoints.png`, `fig2_failure_taxonomy.png`.
- Paper: `../protocol_paper.md`.

```bash
uv run python masters_thesis/protocol_analysis/analyze.py          # refreshes data/nano_study.json
uv run --with matplotlib python masters_thesis/protocol_analysis/figures.py
```
