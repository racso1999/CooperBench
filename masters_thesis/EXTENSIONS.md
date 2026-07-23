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

## 3. Scaling-study infrastructure

**What it does.** Holds a fixed workload — K mutually-conflicting features from one task
(a "pool") — constant and splits it across N agents to measure how coordination cost
scales. Pipeline: build pools from the gold conflict graph → **screen** (keep pools a solo
agent can complete) → **partition** features round-robin across N agents → **sweep**
N ∈ {1..4} running each agent on its share (with Redis messaging + a shared git server) →
stream one row per run to `rows.jsonl` → aggregate to `runs.csv` with a power-law fit.
Headline: work-per-dollar collapses as `efficiency ≈ 1.28·N^-1.61`.

**How to use it.** A `scaling` subcommand on the main CLI. Three modes:

```bash
# 1. Screen candidate pools → writes <out>/pools.json
uv run cooperbench scaling --screen-pools --features 4 --r-screen 3 --screen-threshold 2 --out results_scaling

# 2. Sweep the screened pools across agent counts
uv run cooperbench scaling --manifest results_scaling/pools.json --agents 1,2,3,4 \
    --comm --trials 2 --git --backend docker -m claude-sonnet-5 --out results_scaling

# 3. Re-run the analysis on existing rows
uv run cooperbench scaling --analyze-only --out results_scaling
```

Key flags:

- `--agents 1,2,3,4` — agent counts to sweep (comma list; N=1 is the solo baseline).
- `--features K` — features per pool (default 4); `--require clique|connected` — interdependence.
- `--comm` / `--no-comm` — messaging on/off; `--trials N`; `--seed`/`--seeds`.
- `--screen-pools` / `--analyze-only` — mode selectors (default mode is the sweep).
- `--r-screen`, `--screen-threshold` — screening repeats and pass bar.
- `--git` — shared-git evaluation (agents merge peers into one integrated tree).
- `--manifest` — reuse a screened `pools.json`; `--subset`/`--repos`/`--pool`/`--pools` — pool selection.
- `-a/--agent`, `-m/--model`, `--backend modal|docker|gcp`, `--timeout`, `--out` (output dir).

Note: the output flag is `--out` (not `--out-dir`), and agent count is `--agents` (no `-N`).

**Analysis** (self-contained, reads the frozen `data/scaling_records.csv`):

```bash
uv run python masters_thesis/scaling_analysis/analyze.py    # Calculations 1–6 + power-law fit
uv run --with matplotlib --with numpy python masters_thesis/scaling_analysis/figures.py
```
