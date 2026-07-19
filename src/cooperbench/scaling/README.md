# Scaling experiment (`cooperbench scaling`)

Measures how coordination **cost** scales as the number of agents *N* grows while
the **workload** (a fixed set of *K* interdependent features) is held constant.
The headline question: does cost grow *superlinearly* in *N* — faster than the
linear floor of "*N* agents each load their own context"?

Everything is gated behind the `scaling` subcommand. With it not invoked, the base
benchmark (`run` / `eval`) behaves exactly as before — this package is never
imported on the base path.

## The design

- **Independent variable:** N ∈ {1,2,3,4}.
- **Constant:** K features from one *pool*, split across N agents.
  - N=1: one agent implements all K.
  - N≥2: the K features are partitioned across the agents.
- **Pool** = `(repo, task_id, {f₁…f_K})` — a K-feature subset of a single task whose
  features are **mutually interdependent**: all C(K,2) pairs gold-conflict (a
  *clique* in the precomputed pairwise conflict graph, `dataset/gold_conflict_report.json`).
  This guarantees every partition boundary is a real conflict site, so the measured
  tax is coordination, not luck. A `connected` relaxation is available (`--require connected`).
  There is **no new dataset** — pools are derived from existing data; the target is
  the union of the K features' held-out `tests.patch` suites (no joint gold patch).
- **Partition** (`--partition round-robin`): deterministic. Features are sorted by id
  and dealt round-robin to agents. Same at every N (only the bucket count changes).
- **Conditions:** every N is run in both `comm` and `no-comm`. Empirical
  `tax(N) = cost_comm(N) − cost_nocomm(N)`.
- **Trials:** `r` runs per (pool, K, N, condition) cell (default 8).

## Instrumentation (token buckets)

Per agent per run (aggregated to a run total), derived post-hoc from the saved
Claude Code streams (`<agent>_stream.jsonl` / `_sent.jsonl`). **These are documented
proxies, not ground truth** — see the honesty note in `buckets.py` and INTEGRATION_MAP §6:

| bucket | meaning | how it's computed |
|---|---|---|
| `context` | shared repo/spec/tool-schema ingestion (linear floor) | resident context at turn 0 |
| `task` | reasoning/editing own features | residual generation |
| `comm` | messages sent + received + **re-ingestion** | send-log + `coop-recv` payloads × persistence (per-step cache-read deltas, compaction-bounded) |
| `rework` | redo of an already-edited file after an inbound message | **heuristic**; raw feeder signals also emitted |

Because `claude_code` is the only adapter that persists the per-agent raw stream,
the buckets are recoverable only for it; `buckets_recoverable=False` marks runs where
they are missing (never silently zero). Raw signals (`message_reads`, `conflict_events`,
`rework_turns`) ship alongside so the bucket formulas are auditable/recomputable.

**Dollar-denominated buckets (`*_usd`).** The raw buckets are token counts of *mixed
types* (`context` is cache-read side, `task`/`rework` are output side, `comm` mixes
both), so summing raw tokens across buckets is not meaningful — and per the project's
own conclusion, price is the only fair denominator across differing compositions.
`pricing.py` therefore weights each bucket by its token-type list price and
**apportions the run's real `total_cost_usd` across the buckets by that weight**, so
`context_usd + task_usd + comm_usd + rework_usd == dollar_cost` (additive in $).
Caveat: the buckets are proxies and don't enumerate every token the run paid for
(e.g. per-step carried context beyond turn 0), so apportioning the true cost folds
that residual in proportionally; raw token buckets and true `dollar_cost` are always
kept alongside. `*_usd` is blank for unpriced models.

## Failure taxonomy (one label per run)

`capability_fail` (an agent's own feature fails its suite pre-merge — dominates) →
`merge_conflict` → `merged_but_tests_fail` → `success`.

## N-way merge

N branches off the base commit, folded **sequentially in ascending agent-id order**
(`agent1` base, then merge `agent2`…`agentN`); a conflict at any step marks the run
`conflicts` (no lead-alone fallback — it would confound the clean-merge endpoint).
Test-run and test-file-stripping semantics are inherited unchanged from the core
sandbox. The fold order is recorded in `eval.json`.

## Usage

Screen candidate pools (solo N=1 must reliably complete all K), writing a manifest:

```bash
cooperbench scaling --screen-pools --subset flash --features 4 \
  --r-screen 3 --screen-threshold 2 --out results_scaling
# → results_scaling/pools.json
```

Sweep the qualified pools across N and both conditions:

```bash
cooperbench scaling --manifest results_scaling/pools.json \
  --agents 1,2,3,4 --comm --no-comm --trials 8 \
  -a claude_code -m claude-sonnet-5 --backend docker --out results_scaling
# → results_scaling/rows.jsonl, runs.csv, analysis.json
```

Re-run just the analysis over existing rows:

```bash
cooperbench scaling --analyze-only --out results_scaling
```

Single pool / smaller sweep:

```bash
cooperbench scaling --pool "openai_tiktoken_task/task0/f2_f3_f6_f8" --agents 1,2 --trials 1
```

## Analysis outputs (`analysis.json` + `runs.csv`)

- `runs.csv` — one row per run (token buckets, `*_usd` buckets, cost, pass/fail,
  failure bucket, drivers).
- **Three quadratic fits** `y(N) = α·N + β·N²` (`β>0`, CI strictly above 0 ⇒ superlinear):
  - `cost_fit_comm` — total dollar cost. **Weak by construction**: the ~linear
    per-agent context floor (~fixed tokens *per agent*, so cost has a large `α·N`
    term) dominates total cost, so total-cost `β` under-detects coordination curvature.
  - `comm_fit` — **comm-bucket dollars**. Where the coordination tax concentrates;
    the sharper headline `β`.
  - `tax_fit` — `tax(N) = cost_comm(N) − cost_nocomm(N)` per pool. The paired
    difference cancels the shared floor, isolating communication cost directly.
- **`cost_curve`** — mean ± sd of cost and comm dollars per (N, condition) (error bars).
- **`per_pool_cost_fits`** — the cost fit per pool with `β` aggregated (mean/sd/se)
  across pools, so pool heterogeneity isn't conflated with the N-effect.
- **Failure-mix vs N**, and a **driver regression** of excess `(comm+rework)` on
  `{message_reads, conflict_events, rework_turns}` (standardized), overall and per N.
- CIs use an exact Student-t table for small dof (scipy if present, else z only for
  large dof), so small-sample CIs aren't understated.

## Resume / idempotency

Cells are keyed by a stable run-name; a re-invocation **skips** completed runs and
**reuses cached `eval.json` / `buckets.json`** (the N-way merge runs in Docker, so
re-deriving it on resume is expensive) unless `--force`. So a crashed sweep can be
re-run cheaply — only missing cells execute.

## Shared-git integration mode (`--git`)

The default eval merges isolated per-agent patches with a naive `git merge`, which
conflates genuine coordination failure with incidental line-overlap. `--git` runs
the **fairer apparatus** instead:

- Agents work against a **shared bare git server** (`create_git_server`); each
  fetches its peers, `git merge`s their branches, resolves conflicts, and rebuilds
  its `patch.txt` from the *integrated* tree — **the agents own the integration.**
- Eval does **not** merge. `eval_git.score_team` scores the single integrated tree
  each agent produced against **all K** feature suites (graded), and reports the
  designated integrator's (`agent1`) result as the team deliverable, with
  `best_score` / per-agent scores logged so divergence is visible.
- **Validated at N=2/3/4**: every agent fetches + merges every peer and converges
  on one integrated tree; N=1/3/4 scored a perfect 4/4 on tiktoken through the real
  pipeline. (Integration is expensive — coordination cost rises steeply with N.)

`--git` and the default merge mode use **separate log-dir trees** (`_git` suffix)
so they never reuse each other's cached cells. N=1 always runs as the solo baseline.
Use trials > 1: individual agent runs occasionally error out (empty patch), which a
single trial would score as a spurious 0.

Headline output for this mode: `performance_curve` — graded `score` (and strict
all-pass rate) and mean cost per N — the solo→2→3→4→5 curve.

## Determinism & seeds

The partition is structural (seed-independent). Claude Code exposes no sampling seed,
so `--seed` fixes pool/feature *selection* only and is recorded for provenance;
trials (`r`) capture model stochasticity. This caveat is in every row's `seed` column.

## Notes / constraints

- Local Docker: keep effective concurrency low (this repo's memory notes `-c 2`).
- `claude_code` + `claude-sonnet-5` is the intended configuration (per-step buckets).
- Cost is Claude Code's `total_cost_usd` (API list-price-equivalent), summed over agents.
