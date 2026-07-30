# leader_analysis — reproducible analysis of the supervised (leader) scaling study

Self-contained. No numpy/pandas for the analysis (`figures.py` needs matplotlib +
numpy). Mirrors `../scaling_analysis/` file-for-file.

The companion study to the flat one next door. Same 14 pools, same N levels, same
trial counts, same eval — the **only** change is the coordination topology:

- **flat** (`../scaling_analysis`): the K features are dealt round-robin to N
  peers up front; the peers negotiate integration among themselves.
- **leader** (here): a **supervisor** is the only agent that sees all K specs. It
  decides the division of labour, assigns work through the shared task list,
  and owns the integration. Workers start with no spec and implement what they
  are assigned.

Both arms are in `data/leader_records.csv` (column `arm`) so every calculation is a
paired flat-vs-leader comparison on identical pools.

- `data/leader_records.csv` — one row per run (296 runs: 148 flat + 148 leader, 14
  pools): pool, arm, agents, trial, score (=n_passed/K), all_passed, cost ($),
  leader_cost ($), wall_seconds, agent_seconds, steps.
- `data/cost_accounts.csv` — 286 of those runs (10 leader runs had unparseable
  agent streams, so their accounts are missing rather than zero and are
  excluded), each run's cost split into four accounts (context / task / comm /
  rework) that sum exactly to that run's total.
- `data/pools.json` — the 14-pool manifest both arms were run on.
- `analyze.py` — computes Calculations L1-L7. Run: `python3 analyze.py`
- `figures.py` — writes `figures/fig3a..3d.png`. Run: `python3 figures.py`
- `explanation.txt` — what each of L1-L7 does and why.

**Team-size convention.** The leader is a real agent that costs real money and
real time, so a leader run with N workers is reported at **N+1 agents**. This is
what makes the arms comparable: "4 agents" is 4 peers in the flat arm and
1 supervisor + 3 workers in the leader arm. `agents` in the CSV is already the
total; `workers` is kept alongside for the leader rows.

Headline it reproduces: supervision does not make small teams cheaper — it
**changes the scaling exponent**. Work-per-dollar still decays as a power law,
but at `0.65 * N^-1.09` (R^2 = 0.982) against the flat arm's `1.28 * N^-1.61`
(R^2 = 0.996). Since b = 1 is the floor (cost strictly proportional to
head-count, zero coordination waste), the supervisor removes almost all the
super-proportional penalty. The curves cross at ~3.7 agents: below it the
supervisor's fixed overhead dominates, above it the flat arm's superlinear
coordination cost does.

Caveat carried by every number at 5 agents: only the 6 K=4 pools reach it
(16 runs), and those are the pools a single agent could already solve, so that
column is the thinnest and most favourably-composed evidence in the study.
