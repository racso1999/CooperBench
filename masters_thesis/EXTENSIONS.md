# Extensions to CooperBench

This thesis contributes three additions to CooperBench: the **nano dataset**, a
family of **cooperation protocols**, and the **scaling-study infrastructure**.
Each is described below with a concise summary and the flags needed to use it.

All commands assume the repo root and `uv` (`uv run cooperbench ...`).

---

## 1. The nano dataset

**What it does.** A small, Python-only subset (`dataset/subsets/nano.json`): 20 gold
merge-conflict pairs across 20 tasks in 9 repos. Every pair is *coordination-limited* —
each feature is solvable by a single agent alone (screened with sonnet-5), so any lift
must come from cooperation. Being single-language removes the language×repo confound and
lets the 20 pairs act as independent clusters for statistical power. It is the instrument
the protocol study (below) runs on.

**How to use it.** Select any subset with `-s`/`--subset` (the filename stem under
`dataset/subsets/`):

```bash
uv run cooperbench run -n my_run --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2
```

- `-s, --subset nano` — use the nano manifest.
- `--setting coop` — cooperative (two-agent) setting.
- `-c` — concurrency; `--repeats N` — run N replicates (names get an `_i` suffix).

There is no `--nano`/`--dataset` flag; `nano` is just the subset name. The dataset
directory is set separately with `--dataset-dir`.

**Regenerating the manifest** (optional — the committed `nano.json` is frozen):

```bash
python scripts/nano/enumerate_candidates.py   # sampling frame → nano_py_candidates.json
python scripts/nano/calibrate.py run --k 6 --model claude-sonnet-5   # solo screening
python scripts/nano/build_study_set.py        # → dataset/subsets/nano.json (20 pairs)
```

---

## 2. Cooperation protocols

**What they do.** Six coordination arms for the two-agent `coop` setting, compared in
`../protocol_paper.md`. Each is a system-prompt block plus (for the structured arms) a
validated message schema:

| Protocol | What it does |
|---|---|
| **control** | No partner disclosed, no channel — the coordination floor. |
| **free-text** | Unconstrained `coop-send`/`coop-recv` inbox; talk freely. |
| **semi-structured** | Every message must carry a validated `type`/`files`/`summary`; malformed messages are rejected. |
| **plan-handshake** | Agents PROPOSE/ACCEPT a disjoint file partition before editing. |
| **designated-coder** | One owner per shared file; the other DEFERs and sends a spec. |
| **coauthor-overlap** | Both agents write the overlapping region byte-identically so git merges it clean (the winning arm: 13% → 78% merge-clean). |

**How to select one.** Within `--setting coop`, the messaging arm is a mutually-exclusive
choice:

```bash
# control (no messaging)
uv run cooperbench run -n nano_control --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2 --no-messaging

# free-text (plain messaging — the default, no flag)
uv run cooperbench run -n nano_freetext --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2

# semi-structured (bundled default schema)
uv run cooperbench run -n nano_semi --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2 --structured-messaging

# plan-handshake
uv run cooperbench run -n nano_plan --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2 --structured-messaging schemas/plan_handshake.toml

# designated-coder
uv run cooperbench run -n nano_desig --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2 --structured-messaging schemas/designated_coder.toml

# coauthor-overlap
uv run cooperbench run -n nano_coauthor --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2 --structured-messaging schemas/coauthor_overlap.toml
```

- `--no-messaging` → control.
- (no flag) → free-text.
- `--structured-messaging [SCHEMA]` → a structured arm; omit the path for the bundled
  semi-structured default (`src/cooperbench/agents/_coop/message_schema.toml`), or pass a
  `schemas/*.toml` file for the others.

(`--team-no-protocol` is unrelated — it toggles the separate `team` setting's typed
request/response transport, not these arms.)

### Writing your own schema

A schema is a TOML file that defines **the message structure agents must use** when
they talk in `coop` mode, plus an optional **workflow prompt**. The container-side
messaging CLI hard-rejects any message that omits a required field or breaks an enum,
so "structure was actually followed" is guaranteed, not assumed. Point
`--structured-messaging` at your file — no code change needed. The four bundled arms
live in `schemas/`; copy one and edit it.

A schema has three parts:

```toml
# 1. name — stamped into the auto run-name as struct-<name> and into logs/<run>/
#    config.json + each pair's result.json. CHANGE IT whenever you change the schema,
#    or A/B arms collide in logs/.
name = "my_protocol_v1"

# 2. instructions (optional) — a top-level string rendered into each agent's prompt
#    IN PLACE OF the generic cooperation workflow. This is how you specify a
#    multi-phase protocol (e.g. a PROPOSE/ACCEPT handshake) with no code change.
#    Agents can call `coop-await` (blocking receive) to synchronise on a handshake.
instructions = """
PHASE 1 — announce the files you will touch (type=CLAIM), then coop-await your partner.
PHASE 2 — once claims are disjoint, implement your own features and send type=DONE.
"""

# 3. [[field]] blocks — each is one slot the agent fills via
#    `coop-send --<name> <value>`. Repeat the block per field.
[[field]]
name = "type"            # required; becomes the --type flag. Match [A-Za-z][A-Za-z0-9_]*. Avoid `help`.
required = true          # default false; a message omitting a required field is rejected.
enum = ["CLAIM", "DONE"] # optional; the value must be one of these strings.
description = "message type"  # shown to the agent in its prompt.

[[field]]
name = "files"
required = true
description = "comma-separated files this message is about"
```

**What each part does:** `[[field]]` entries define and *enforce* the wire format
(the machine-checkable half); `instructions` defines the *workflow* the agents are
told to follow (the prose half). A schema can use either or both — fields only for a
pure structure test, or fields + instructions for a full multi-phase protocol like
`plan_handshake.toml` / `coauthor_overlap.toml`. Run it exactly like the bundled arms:

```bash
uv run cooperbench run -n nano_mine --subset nano --setting coop -a claude_code -m claude-sonnet-5 -c 2 --structured-messaging schemas/my_protocol.toml
```

Every run is self-documenting: the full field set is saved to `logs/<run>/config.json`
(`message_schema`) and each pair's `result.json` records the schema `name` and
`messages_by_kind`. See `schemas/README.md` for the full field reference.

**Analysis** (reproduces the paper's tables/figures):

```bash
uv run python masters_thesis/protocol_analysis/analyze.py          # refreshes data/nano_study.json
uv run --with matplotlib python masters_thesis/protocol_analysis/figures.py
```

---

## 3. Scaling-study infrastructure (the "pool" experiment)

New to this part? Read this whole section top-to-bottom once — it takes you from zero to
a running sweep. It assumes you have already run ordinary CooperBench tasks.

### What it is

The question: **when you split one fixed workload across more agents, what does
coordination cost you?** The workload is a **pool** — K features from a *single task* that
are mutually interdependent (their gold patches conflict, so they cannot be done in
isolation without stepping on each other). You hold that K-feature pool constant and run it
at N = 1, 2, 3, 4 agents. N = 1 (one agent does all K alone) is the baseline; higher N
splits the same K features across the agents. The output is a cost/quality curve vs N.

Everything runs through one subcommand: **`cooperbench scaling`**.

### Prerequisites

Same as a normal `coop` run — nothing pool-specific to install:

- A working `--backend` (default `docker`) with the task images you already use for
  CooperBench. Pools only reference tasks that exist in your dataset.
- The conflict graph `dataset/gold_conflict_report.json` — ships with the dataset; pools
  are computed from it, you do not create it.
- **Redis** is used for inter-agent messaging in the `comm` condition; you do **not** need
  to start it — `cooperbench` auto-launches a `redis:alpine` container via Docker on first
  use.

### The workflow: screen → sweep → analyse

There are three modes. The normal path is **screen once, then sweep** (the sweep prints the
analysis automatically; `--analyze-only` is only for re-running analysis later).

**Step 1 — screen** the candidate pools for *your model*. This runs a single agent alone on
each candidate and keeps only the ones it can fully solve, writing the survivors to
`<out>/pools.json` (details + why in the callout below):

```bash
uv run cooperbench scaling --screen-pools \
    --features 4 --r-screen 3 --screen-threshold 2 \
    -m claude-sonnet-5 --backend docker \
    --out results_scaling_sonnet5
```

**Step 2 — sweep** the screened pools across agent counts. Point `--manifest` at the
`pools.json` from step 1. Each `(pool, N, condition, trial)` cell runs, streams a row to
`<out>/rows.jsonl`, and the analysis (`runs.csv` + the power-law fit) prints at the end:

```bash
uv run cooperbench scaling \
    --manifest results_scaling_sonnet5/pools.json \
    --agents 1,2,3,4 --comm --trials 2 --git \
    -m claude-sonnet-5 --backend docker \
    --out results_scaling_sonnet5
```

**Step 3 (optional) — re-analyse** existing rows without re-running any agents:

```bash
uv run cooperbench scaling --analyze-only --out results_scaling_sonnet5
```

> **Start small and cheap.** Both steps launch real agents, and cost ≈ (pools) × (trials) ×
> (agent counts). For a first run, scope to one or two pools (see below) with `--trials 1`
> before committing to a full sweep.

### Choosing which pools to run

The sweep needs a set of pools. It resolves them (in priority order) from:

- `--manifest pools.json` — the screened set from step 1 (**recommended**).
- `--pool <pool_id>` or `--pools <id1,id2>` — specific pools by id (ids look like
  `dspy_task/8394/f1_f2_f4`; you can copy them from a `pools.json` or any `rows.jsonl`).
- `--subset <name>` / `--repos <repo1,repo2>` — restrict the tasks pools are drawn from.
- nothing — fresh selection of one pool per eligible task straight from the conflict graph.

⚠️ Only `--manifest` (or re-screening) gives you a **screened** set. Selecting with
`--pool`/`--subset`/nothing skips screening, so those pools have no capability floor — fine
for a quick smoke test, not for a real result.

**Key constraint:** `K ≥ max(--agents)` — every agent must own at least one feature. With
`--features 4` you can sweep up to `--agents 1,2,3,4`; ask for `--agents ...,5` and it errors
(`--agents max 5 exceeds smallest pool K 4`).

### Flags you'll actually use

- `--features K` — pool size (default 4); `--require clique|connected` — how tightly the K
  features must interconnect (default `clique` = all pairs conflict).
- `--agents 1,2,3,4` — the N values to sweep (N=1 is the solo baseline, always run once).
- `--comm` / `--no-comm` — messaging condition; omit both to run *both* conditions.
- `--trials N` — repeats per cell (captures model stochasticity; default 8).
- `--git` — shared-git evaluation: agents integrate peers into one tree and it's scored
  graded. This is the mode the thesis uses; recommend keeping it on.
- `--screen-pools` / `--analyze-only` — pick a non-default mode (default is the sweep).
- `--r-screen`, `--screen-threshold` — screening trials and the pass bar (default 3 / 2).
- `-m/--model`, `-a/--agent`, `--backend modal|docker|gcp`, `--timeout`, `--out` (output dir).

Gotchas: the output flag is `--out` (not `--out-dir`), and agent count is `--agents` (no `-N`).

### Outputs (all under `--out`)

- `pools.json` — the screened pool manifest (from `--screen-pools`).
- `rows.jsonl` — one row per `(pool, N, condition, trial)` cell, streamed live (crash-safe).
- `runs.csv` + `analysis.json` — the aggregated table and the power-law fits.

Note: the default `--out` (`results_scaling*`) is git-ignored, so treat it as scratch — the
`pools.json` there is **not** persisted across a clean checkout.

### What `--screen-pools` does (and why it is model-specific)

Screening runs a *single* agent alone on each candidate pool — handed all K features at
once — for `--r-screen` trials, and keeps only pools that agent solves completely (all K
test-suites pass) in at least `--screen-threshold` trials. The survivors, with their pass
counts, are written to `<out>/pools.json`, which the sweep consumes via `--manifest`. This
is what makes the scaling result interpretable: it guarantees the workload is
*solo-solvable*, so any failure at N ≥ 2 is a **coordination** failure, not an impossible
task.

> **Important — re-screen for every model.** The capability floor is model-specific: a pool
> solo-solvable by one model may be unsolvable by another. A `pools.json` is therefore only
> valid for the model (`-m`) that screened it. **When you change `-m`/`-a`, re-run
> `--screen-pools` to produce a fresh manifest for that model** — do not reuse another
> model's pool set, or its N ≥ 2 failures will be misread as coordination failures when they
> are really task-impossibility. (The manifest does not record which model screened it, so
> nothing warns you of a mismatch — track it yourself, e.g. `--out results_scaling_<model>`.)

### Offline analysis of the thesis data

Self-contained, stdlib-only, reads the frozen `data/scaling_records.csv` (no agents, no
cost) — the quickest way to see the shape of the output:

```bash
uv run python masters_thesis/scaling_analysis/analyze.py    # Calculations 1–6 + power-law fit
uv run --with matplotlib --with numpy python masters_thesis/scaling_analysis/figures.py
```
