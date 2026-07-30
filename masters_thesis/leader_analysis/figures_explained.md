# figures_explained

Reference for an AI (or human) using the figures in `figures/` without re-reading
the analysis. Each entry gives what is plotted, the values on it, the one claim it
licenses, and what it does **not** show. Numbers are current as of the complete
296-run dataset; regenerate with `python3 figures.py` after any data change.

## Conventions that apply to every figure

- **"Agent count N" is TOTAL agents.** In the supervised arm the leader is a real
  agent, so a run with N workers is plotted at N+1. "4 agents" = 4 flat peers, or
  1 supervisor + 3 workers. Never compare a supervised point to a flat point at
  the same *worker* count — the axis is already aligned for you.
- **Arm colours are fixed**: flat peers `#1b7ba0` (sea blue), supervised
  `#b01e28` (deep red). Purple `#ac18f2`-family appears only in fig3e, where a
  single series is tinted within one hue.
- **Coverage differs by arm.** Flat spans 1–4 agents, supervised spans 2–5. Only
  2–4 agents have both. There is no supervised solo point (a leader with zero
  workers is not a team) and no 5-agent flat point.
- **The 5-agent supervised column and the 4-agent flat column come from the six
  K=4 pools only** (16 runs each). Those pools are, by construction, the ones a
  single agent could already solve. Treat the end of each curve as the thinnest
  and most favourably-composed evidence in the study.
- Error bars, where present, are 95% CIs of the mean **clustered by pool** (t over
  the 14 per-pool means), except all-pass rates which use Wilson binomial
  intervals. The replication unit is the pool, not the run.

---

## fig3a_efficiency_topology.png — both arms, log–log

**Plots** work solved per dollar (mean graded score ÷ mean cost) against team
size, both arms, with each arm's fitted power law dashed through it.
**Axes are logarithmic on both scales**, so a power law is a straight line and its
exponent is the slope. A dotted vertical marks the crossover.

Values: flat 1.24, 0.43, 0.23, 0.13 at 1–4 agents; supervised 0.29, 0.21, 0.15,
0.11 at 2–5. Fits: flat `1.28·N^-1.61` (R²=0.996), supervised `0.65·N^-1.09`
(R²=0.982). Crossover at **N=3.7**.

**Supports:** supervision changes the *scaling exponent*, not the level. b=1 is
the floor (cost strictly proportional to head-count, zero coordination waste), so
flat's 1.61 is super-proportional waste and supervised's 1.09 sits essentially at
the floor. The lines cross, so flat is more efficient below ~3.7 agents and
supervised above it.

**Does not show:** the "collapse off a cliff" shape — log axes straighten it by
construction. Use fig3e (or the flat study's fig2c) if the visual claim is about
the steepness of the fall. Anything beyond 5 agents is extrapolation the data
cannot support; the crossover itself is interpolation and is safe.

## fig3b_correctness_topology.png — both arms, linear

**Plots** the strict all-pass rate (fraction of runs where *every* one of the K
feature suites passes on the integrated tree) against team size, with Wilson 95%
intervals.

Values: flat 89%, 82%, 77%, 69% at 1–4 agents; supervised 77%, 80%, 84%, 88% at
2–5. The curves cross between two and three agents.

**Supports:** the two topologies move in opposite directions as the team grows —
flat degrades monotonically, supervision improves — and at four agents, the
largest size both reach, the ordering has reversed (84% vs 69%).

**Does not show:** graded score, which is a different and flatter measure (flat
0.96→0.92, supervised 0.88→0.97). All-pass is the strict "did the team ship
something fully correct" rate. The intervals are wide at the ends (16 runs); the
crossing is a trend across the range, not a significant difference at any single
team size.

## fig3c_accounts_topology.png — both arms, paired stacked bars

**Plots** each run's dollar cost split into four accounts that sum to the run
total — context (each agent re-loading the shared repo), task (implementing),
comm (messages sent/received/re-ingested), rework (re-editing after an inbound
message). Flat is the left bar of each pair (solid), supervised the right (fine
cross-hatch). The label on the warm cap is (comm+rework) as a share of the run.

Values: flat totals $0.78 / $2.10 / $3.82 / $7.21 at 1–4 agents with tax shares
0/31/32/36%; supervised $2.81 / $4.04 / $5.58 / $9.16 at 2–5 with 21/21/25/31%.

**Supports:** the mechanism behind the exponent difference. The messaging-related
tax is consistently a smaller share under supervision, because workers coordinate
with one supervisor rather than with every peer, while the context floor grows
similarly in both arms — supervision reduces the part that *scales*, not the
message-independent floor.

**Does not show, and this is the important caveat:** these are apportioned dollars
priced at a single model's list rates, but supervised runs are mixed-model (Opus
leader + Sonnet workers). **Read the shares, not the absolute dollars, for the
supervised arm.** Also, 10 of 148 supervised runs had unparseable agent streams
and are excluded here (286 of 296 runs plotted), so a supervised bar total is the
mean over runs *with* bucket data and will not exactly equal that cell's mean
`dollar_cost` in fig3a. Exact costs live in `data/leader_records.csv`.

## fig3d_wallclock_topology.png — both arms, linear

**Plots** mean wall-clock minutes to completion against team size, with the dashed
`T₁/N` curve showing what perfect work-sharing would give, anchored at the flat
solo mean. A run's clock stops when its *last* agent finishes; evaluation time is
excluded.

Values: flat 4.0, 5.6, 6.5, 8.3 min at 1–4 agents; supervised 9.5, 11.0, 12.3,
14.8 at 2–5. Both rise where the ideal falls.

**Supports:** neither topology buys time, and supervision costs more of it at
every size, with the gap widening. Speedups against the solo baseline are 0.67×
→0.56× (flat) and 0.38×→0.32× (supervised) — all below 1, i.e. slower than one
agent working sequentially.

**Does not show:** that the parallelism is fake. Summed per-agent time grows
roughly linearly with team size while wall-clock grows far more slowly, so agents
genuinely do work concurrently; the gain is swamped by coordination on the
critical path (the leader plans for ~3.5 min before the first claim, and
integrates serially at the end). `agent_seconds` is recorded for the supervised
arm only — the flat runs predate that instrumentation.

## fig3e_efficiency_supervised.png — supervised arm alone, linear

**Plots** the same efficiency measure as fig3a but for the supervised arm only,
on **linear** axes, with the fitted `0.65·N^-1.1` dashed through it. Markers are
purple, tinted within one hue so brightness tracks the value while the series
reads as one colour. This is the direct counterpart of the flat study's
`../scaling_analysis/figures/fig2c_efficiency.png`, which is identical in
construction but green.

Values: 0.29, 0.21, 0.15, 0.11 at 2–5 agents.

**Supports:** the supervised arm's efficiency collapses as a power law, shown as
the curve it is. Use this when the claim is about the *shape* of the decay, or
when placing the supervised study beside the flat one as a matching pair.

**Does not show:** any comparison — there is no flat series on it, and its
linear y-axis is not shared with fig2c, so the two cannot be compared by eye
across figures. For anything comparative, use fig3a.

---

## Choosing a figure

| claim | figure |
|---|---|
| supervision changes the exponent / the arms cross | fig3a |
| efficiency collapses (shape of the decay) | fig3e, or fig2c for the flat arm |
| correctness trends run in opposite directions | fig3b |
| where the money goes / why the exponent differs | fig3c |
| teams are slower, and supervision slowest | fig3d |

Every number above is reproducible with `python3 analyze.py`; the figures are
generated from the same calc functions, so they cannot drift from the tables.
