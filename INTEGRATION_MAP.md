# INTEGRATION_MAP.md — agent-count scaling harness

Discovery notes for the scaling-experiment build. **Every claim below was grepped
and read, not assumed.** File:line references are to the tree at time of writing.
The purpose is to record exactly what exists, what does **not** exist, and the
concrete hook points before any code is written.

**Bottom line up front:** roughly 60% of the design maps onto existing machinery
cleanly. The other 40% hits three hard realities the spec's vocabulary papers over —
(1) there is no "pool with a joint gold patch"; (2) the eval merge is *strictly*
two-patch, in both the coop and solo paths; (3) the four token buckets are **not**
recorded and are only *partially* recoverable, and only for the `claude_code` agent.
Details and proposed resolutions are in §6–§8. These need your sign-off before I code.

---

## 1. Feature pools & gold patches

### What exists
- **Subset files** live in `dataset/subsets/*.json` (e.g. `flash.json`, `nano.json`).
  Loaded by `load_subset()` at `src/cooperbench/runner/tasks.py:11-40`.
  Schema: top-level `name`, `description`, `stats`, `tasks[]`. Each task entry is
  `{repo: str, task_id: int, pairs: [[f1,f2], ...]}`. The loader reads only `repo`,
  `task_id`, and the 2-element `pairs` (`tasks.py:31-40`); `name`/`description`/`stats`
  are ignored.
- **Features on disk** (`dataset/README.md:33-40`, confirmed by `find`):
  ```
  dataset/<repo>_task/task<ID>/
    combined.patch                     # full PR patch — ALL features of the task
    Dockerfile, setup.sh, runner.sh, run_tests.sh
    feature<N>/
      feature.md      # human-readable spec (Markdown, not JSON)
      feature.patch   # that feature's gold implementation
      tests.patch     # that feature's held-out test suite
  ```
  A "feature" is a `feature<N>/` dir with those three files. `feature.md` fields:
  `**Title**`, `**Pull Request Details**`, `**Description**`, `**Technical
  Background**`, `**Files Modified**`. No per-feature JSON, no explicit PR-number field.
- **Feature discovery** in code: `discover_tasks` scans `task<ID>` dirs for
  `feature*` subdirs, extracting the int id (`tasks.py:89-93`); tasks with `< 2`
  features are skipped (`tasks.py:95-96`).
- **`dataset/gold_conflict_report.json`** — top-level keys `summary`, `per_task`,
  `conflict_pairs`, `all_results`. `conflict_pairs[]` = `{repo, task_id, f1, f2}`
  (only gold-conflicting pairs). **Precomputed data; not read by any code in `src/`**
  (grep confirms). The conflict selection is baked into each subset's `pairs` list.

### What does NOT exist (critical for the design)
- **There is no "pool of mutually-compatible features with a joint gold patch."**
  The entire model is *pairwise*. Features are combined strictly two at a time
  (`combinations(feature_ids, 2)`, `tasks.py:123`; `f1, f2 = pair`, `tasks.py:111`).
- Gold patches exist only at **per-feature** (`feature.patch`) and **per-whole-PR**
  (`combined.patch`) granularity — never per-arbitrary-feature-set. `combined.patch`
  covers *all* features of a task and is **not consumed by the runner or eval**
  (grep for `combined.patch` in `src/` → only an unrelated docstring).
- The word "pool" in the repo refers only to `ThreadPoolExecutor` / connection pools
  and to naming labels on nano extension batches — never a feature-pool abstraction.

### Resolution — pool = solo-screened conflict-clique K-subset of a task

The design's "pool + joint gold + test suites" bundles three separable roles; only
one needs an artifact, and it already exists. Verified load-bearing fact: the gold
`feature.patch` is used **only** as a fallback when no agent patch is supplied
(`sandbox.py:47-49`, a dataset-validation helper). Every agent-scoring `_run_tests`
call receives the **agent's** patch (`merged.patch`/`patch1.patch`/`solo.patch`,
`sandbox.py:224-225,275-276,290-292,399-402`) — never the gold. So agent work is
scored against **test suites run on the agent tree**, not against any gold patch.

A **pool** is `(repo, task_id, {f₁…f_K})` — a specific K-feature subset of one task —
qualified by two properties, both computable from data already on disk:

1. **Mutual interdependence (coordination must matter).** All `C(K,2)` pairs among
   the K features are gold-conflicting → the K features form a **clique** in the
   pairwise conflict graph. That graph is precomputed in
   `dataset/gold_conflict_report.json` (`conflict_pairs`); pool selection enumerates
   K-cliques from it — no new merges to select. *Rationale:* if features didn't
   conflict, splitting them across agents would cost nothing and `tax(N)` would be
   noise. The clique guarantees every partition boundary is a real conflict site.
   *Relaxation* if K-cliques are scarce at large K: require the conflict graph on the
   K features to be **connected** (each feature conflicts with ≥1 other) instead of
   complete. Default clique; fall back to connected only if needed, logging which.
2. **Solo-achievable (workload fair across N).** A solo Sonnet-5 run at N=1 completes
   all K within the step/budget cap — this is `--screen-pools`. Pools a single agent
   can't finish are disqualified, so N=1 never "fails" for capability reasons.

The **joint target = union of the K features' `tests.patch` suites**, run
independently on the N-way-merged agent tree. `pool_passes(N)` = **all K** suites
pass (generalizes existing `both_passed` → `all_passed`). **No joint-gold-patch file
is created or required.**

Optional (reporting only): a materialized joint gold = deterministic N-way merge of
the K `feature.patch`es in the pinned fold order (same machinery as agent-patch
merge); its clean/conflict status is a pool **covariate** ("gold has G conflicting
hunks"), never a scoring input.

**Feasibility on real data** (flash clique census): 875 valid K=3 cliques, 1419 K=4,
1775 K=5, max clique up to 12 features — a K=4 pool covering N∈{1,2,3,4} is plentiful.
**K ≥ N** is required to split into N agents, so the {1,2,3,4} sweep needs **K ≥ 4**.
When a task has several K-cliques, pick deterministically (lexicographically smallest
sorted feature-id tuple by default), logged with the run.

---

## 2. Run launch, settings, and agent frameworks

- **CLI entrypoint:** `src/cooperbench/cli.py:69` `main()` → `run` subparser
  (`cli.py:110-115`) → `_run_command` (`cli.py:389`) → loops `run(...)` over
  `--repeats` (`cli.py:462`). `run()` is `src/cooperbench/runner/core.py:38`; it
  dispatches by `setting` to `execute_solo` / `execute_team` / `execute_coop`
  (`core.py:140-175`).
- **Settings** (`--setting`, choices `coop`/`solo`/`team`, default `coop`):
  - `solo` = one agent on the whole feature list (`solo.py`), messaging hardwired off.
  - `coop` = N peer agents, one feature each, Redis messaging on by default.
  - `team` = N agents with shared task list / roles.
  `setting` is written into every `result.json`.
- **Agent count is data-driven:** `coop.py:81` `n_agents = len(features)`;
  `coop.py:82` `agents = [f"agent{i+1}" for i in range(n_agents)]`. Agents launch as
  one `threading.Thread` each (`coop.py:159-166`), **fully asynchronous** — no global
  lockstep barrier. Feature→agent assignment: `sorted_features = sorted(features)`
  (`coop.py:157`) zipped to agent ids (`coop.py:158`).
- **Solo runner already accepts arbitrary K:** `execute_solo(..., features: list[int], ...)`
  (`solo.py:15-18`), and its agent loops `for fid in features` (`solo.py:174`). So the
  N=1 arm needs no runner change — a solo run on K features already works.
- **Default agent framework is `mini_swe_agent_v2`** (`-a`, `cli.py`), but **your
  scaling experiment must use `claude_code`** (see §4/§8 — it is the only adapter that
  persists the per-agent raw stream needed for per-step buckets, and it is what the
  prior flash experiments used).

Relevant existing `run` flags: `-n/--name`, `-s/--subset`, `-r/--repo`, `-t/--task`,
`-f/--features` (comma list), `-m/--model`, `-a/--agent`, `-c/--concurrency`,
`--repeats`, `--setting`, `--redis`, `--no-messaging` | `--structured-messaging`,
`--no-auto-eval`, `--backend {modal,docker,gcp}`, `--dataset-dir`, `--log-dir`.

---

## 3. Token / cost recording

- **Authoritative source:** the Claude Code terminating event
  `{"type":"result", ...}` from `claude --output-format=stream-json`. Parsed in
  `src/cooperbench/agents/claude_code/parsers.py:46-72` (`parse_stream_json`), which
  **skips every non-`result` event** (`parsers.py:56-57`). Exact field reads:
  - `cost = float(event.get("total_cost_usd") or 0.0)` — `parsers.py:66`
  - `steps = int(event.get("num_turns") or 0)` — `parsers.py:67`
  - `input_tokens` ← `usage.input_tokens` — `parsers.py:68`
  - `output_tokens` ← `usage.output_tokens` — `parsers.py:69`
  - `cache_read_tokens` ← `usage.cache_read_input_tokens` — `parsers.py:70`
  - `cache_write_tokens` ← `usage.cache_creation_input_tokens` — `parsers.py:71`
- **`total_cost_usd` is the CLI's own dollar figure** (API list-price-equivalent).
  `src/cooperbench/agents/pricing.py` `compute_fallback_cost(...)` is used **only**
  when an agent returns `cost==0`; it is **not** on the `claude_code` path.
- **`result.json` shape:**
  - Coop: top-level `repo, task_id, features, setting, run_id, run_name,
    agent_framework, model, started_at, ended_at, duration_seconds, agents{...},
    total_cost, total_steps, messages_sent, message_schema, messages_by_kind, log_dir`.
    Per agent (`agents[agentK]`): `feature_id, status, cost, steps, input_tokens,
    output_tokens, cache_read_tokens, cache_write_tokens, patch_lines, error`.
  - Solo: same but singular `agent` (dict, **no `feature_id`**) and no messaging fields.
  - Totals: `total_cost = Σ agent.cost` (`coop.py:214`), `total_steps` (`coop.py:215`).

### Per-step recoverability (crucial for the four buckets)
- `result.json` carries **only terminating aggregates** — no per-step breakdown.
- **BUT** the full Claude Code stream is saved per agent, so per-step recovery is
  possible **for `claude_code` only**:
  - In-container: `claude --verbose --output-format=stream-json ... | tee
    /tmp/claude-stream.jsonl` (`adapter.py:238-243`; `CONTAINER_STREAM_LOG` at
    `adapter.py:76`).
  - Persisted to the host run dir (`adapter.py:573-582`):
    - `<log>/<agent_id>_stream.jsonl` — full stream-json, **per-assistant-event
      `usage` blocks** (this is where step-by-step input/cache-read growth lives)
    - `<log>/<agent_id>_session.jsonl` — session transcript
    - `<log>/<agent_id>_sent.jsonl` — coop send-log (coop only)
- **Constraint:** this raw-stream persistence exists **only in the `claude_code`
  adapter**. `mini_swe_agent_v2` and other frameworks expose only the aggregate
  `AgentResult`. → the scaling experiment is effectively `claude_code`-only.

---

## 4. Inter-agent messaging & the comm/no-comm distinction

- **Mechanism:** Redis list per agent as an inbox. Key
  `f"{prefix}{agent_id}:inbox"`; `rpush` to send, `lpop` to drain
  (`agents/mini_swe_agent_v2/connectors/messaging.py:30,52,81,90-94`). Run
  namespacing: `namespaced_redis = f"{redis_url}#run:{run_id}"` (`coop.py:86`).
- **Container-side CLI** the LLM drives via bash: `agents/_coop/coop_msg.py`
  (`coop-send`/`coop-broadcast`/`coop-recv`/`coop-await`/`coop-peek`/`coop-agents`).
  **`claude_code` uses exactly this path** (`claude_code/adapter.py:410-427`: sets
  `COOP_REDIS_URL`, `COOP_AGENT_ID`, `COOP_AGENTS`, `COOP_LOG_PATH`, installs
  `coop_msg.py`). There is **no auto-drain for `claude_code`** — the agent
  voluntarily runs `coop-recv`, and received messages arrive as **Bash tool-result
  output inside its session stream** (favorable: comm tokens are discrete, locatable
  events, not silent prompt injection).
  - (For `mini_swe_agent_v2` only, received messages are auto-injected as synthetic
    `role="user"` turns at the top of each step — `agents/.../agents/default.py:203-217`.
    Different mechanism; not our path.)
- **Message record shape:** free-form `{from, to, content, timestamp}`
  (`messaging.py:75-81`); structured adds `timestamp_iso`, `fields`, `kind`
  (`coop_msg.py:146-158`). Optional JSONL send-log at `COOP_LOG_PATH`.
- **Message kinds** (schema `semi_structured_v1`, `agents/_coop/message_schema.toml`):
  `CLAIM, INTENT, QUESTION, ANSWER, STATUS`. These populate `messages_by_kind`.
- **Logged to `result.json`:** `messages_sent = len(sent_msgs)` (`coop.py:243`),
  `messages_by_kind` (`coop.py:245`), `message_schema` name. **No `messages_received`
  field** — received msgs are dropped in aggregation (`coop.py:181`). Full sent-only
  conversation is separately written to `conversation.json` (`coop.py:184-186`).
- **Comm gating:** on ⇔ `messaging_enabled AND comm_url AND len(agents) > 1`
  (`coop.py:126`; `claude_code/adapter.py:375`). So:
  - **N=1 is inherently no-comm** (gate fails at `len(agents)>1`). Good.
  - **No-comm at N≥2:** `--no-messaging` (`cli.py:222-226` → `messaging_enabled=False`).
  - `--structured-messaging [SCHEMA]` selects structured mode + kinds.
- **"Step"** = one `query()` (one LLM call); per-agent count is `n_calls`, surfaced as
  `steps`. Coordination is eventual — an agent sees a peer's message only on its next
  `coop-recv`.

---

## 5. Evaluation pipeline: merge & tests

- **Entrypoint:** `eval` subcommand (`cli.py:290`) → `_eval_command` (`cli.py:467-491`)
  → `evaluate(...)` (`evaluate.py:17-149`) → per run `_evaluate_single`
  (`evaluate.py:318-406`) → `test_solo` (solo) or `test_merged` (coop). Writes
  `eval.json` per run.
- **`test_merged` is strictly two-patch** (`sandbox.py:93-104`): params
  `feature1_id, feature2_id, patch1, patch2`. Two literal branches `agent1`/`agent2`.
- **Branch/apply** (`_setup_branches`, `sandbox.py:476-514`): capture `BASE_SHA`;
  `git checkout -b agent1` off HEAD, `apply_patch 1`, commit `--allow-empty`;
  `git checkout $BASE_SHA`, `git checkout -b agent2`, `apply_patch 2`, commit. Patch
  apply = `git apply` then fallback `git apply --3way`; failure → `PATCH{n}_FAILED`.
- **Naive merge** (`_merge_naive`, `sandbox.py:543-560`), verbatim:
  ```bash
  git checkout agent2
  if git merge agent1 --no-commit --no-ff; then
      echo "MERGE_STATUS=clean"; git commit -m "Temp merge"
      git diff {base_sha} HEAD > /patches/naive_diff.patch
  else
      echo "MERGE_STATUS=conflicts"; git merge --abort
  fi
  ```
  No strategy flag (git default ort). Conflict detection = merge exit status →
  `conflict = "MERGE_STATUS=conflicts" in output` (`sandbox.py:564`). A `_merge_union`
  helper exists (`sandbox.py:575-610`) but is **dead code** in the docker/modal path
  (union explicitly removed, `sandbox.py:246-250`; the separate `gcp.py` batch path
  still uses union — different codepath).
- **Test-file stripping** (`_filter_test_files`, `sandbox.py:716-740`): drops all
  hunks of any file whose `diff --git` header contains `/test_`, `/tests/`,
  `_test.py`, `/test/`, or `tests.py`. Applied to each agent patch before merge.
- **Test run** (`_run_tests`, `sandbox.py:630-660`): hard-reset to base, then
  `bash /usr/local/bin/runner.sh {tests_patch} {feature_patch}` (per-repo runner
  applies feature+test patch and runs the suite). `passed = exit_code == 0 AND
  parsed["passed"] > 0` (`sandbox.py:654-660`). On a clean merge both suites run
  against `merged.patch` (`sandbox.py:271-276`); `both_passed = test1.passed AND
  test2.passed` (`sandbox.py:324`).
- **Solo fallback** (`sandbox.py:278-295`): on non-clean merge, test **agent1's patch
  alone** against **both** suites; if both pass, `winning_solo="agent1"`,
  `merge.strategy="solo-agent1"`. **Only agent1** (the "lead") — no agent2 fallback.
- **Recorded outcome fields** (in `eval.json`, nested — `sandbox.py:303-326`):
  `apply_status{agent1,agent2}` (`applied|skipped|failed|unknown`); `merge.status`
  (`clean|conflicts|missing_input|identical|error`); `merge.strategy`
  (`naive|solo-agent1|skip-merge-identical|None`); `merge.diff`;
  `feature1`/`feature2` (`feature_id,passed,exit_code,tests_passed,tests_failed,
  test_output`); `feature1_independent`/`feature2_independent`
  (pre-merge capability check, `sandbox.py:182-190`); `both_passed`; `error`.
  - **`test_solo` is ALSO two-feature-hardwired** (`sandbox.py:333-337`:
    `feature1_id, feature2_id`), and `_evaluate_single` does
    `f1, f2 = features[0], features[1]` unconditionally before branching
    (`evaluate.py:337`). So **both** eval paths assume exactly 2 features.
  - The CSV-only field names (`merge_clean`, `outcome`, `a_indep_passed`, …) do **not**
    exist in eval output — they are derived later by `scripts/nano/build_run_csvs.py`.

**Merge is strictly N=2 everywhere.** N-way requires new code in `_setup_branches`,
`_merge_naive`, `test_merged`, the fallback, `test_solo`, and the `evaluate.py`
dispatch. This is the single largest build item.

---

## 6. The four token buckets — feasibility (READ THIS)

The spec wants per-agent `context / task / comm / rework` tokens. **None of these are
recorded.** They must be derived from the saved `claude_code` streams (§3). Honest
assessment of what is recoverable vs. proxy vs. missing:

| Bucket   | Recoverability | Method against real logs |
|----------|----------------|--------------------------|
| **context** | **Proxy (good)** | The linear floor = tokens to ingest repo/spec/tool schemas. Best proxy: the input/cache-write of the **first assistant step** in `<agent>_stream.jsonl` (system prompt + tool schemas + initial repo reads), before any task edit or message. Clean at step 1; blurs as the agent reads more files mid-task. |
| **task** | **Residual** | total input+output − context − comm. Not independently measured; it is what's left. Defensible as "everything not floor and not coordination." |
| **comm** | **Recoverable (claude_code)** | SENT = tokens in `coop-send`/`coop-broadcast` tool-call args (locatable in the stream + cross-checked against `<agent>_sent.jsonl`). RECEIVED = tokens in `coop-recv` tool-**result** blocks. **Re-ingestion:** a received message's tool-result persists in context and is re-billed as cache-read each subsequent step until compaction — computed as (received-block token size) × (steps it remains resident), read off the per-step `usage.cache_read_input_tokens` deltas. Documented, not guessed. |
| **rework** | **Heuristic proxy (weakest)** | "Turns triggered by an inbound coordination signal that re-touch an already-edited file." Derivable by correlating a `coop-recv` event with a **subsequent `Edit`/`Write` tool_use on a file path already edited earlier** in the same session (both are in `<agent>_session.jsonl` with ordering). This is a heuristic — it will over/under-count when rework is triggered by reasoning rather than a message, or when a re-edit is coincidental. Flagged as the least trustworthy bucket. |

**What's genuinely missing / caveats to record in `runs.csv` provenance:**
- No token attribution exists natively; all four buckets are **post-hoc stream
  derivations**, valid only for `claude_code`.
- context vs task cannot be cleanly separated after step 1 (both are "input tokens for
  file reads"); the split is a documented proxy, not ground truth.
- rework is a correlation heuristic; I'll emit the raw signals feeding it
  (#message-reads, #re-edits-after-recv) alongside the bucket so the number is auditable.
- Compaction boundaries must be detected from the stream (cache-read resets) to bound
  the re-ingestion multiplier; where compaction can't be located, I'll cap persistence
  at the observed context window and note it.

Per the spec: where a clean split isn't recoverable I state so and record the closest
defensible proxy + what's missing, rather than silently approximating. The above is
that record. **If you'd rather I collapse to fewer, fully-defensible buckets (e.g.
`context-floor / comm / other`) than ship a weak `rework` proxy, say so.**

---

## 7. Proposed hook points (nothing modified when flags off)

New isolated module `src/cooperbench/scaling/` (flag-gated). It *calls into* existing
code; it does not alter base behavior. Anticipated touch points:

- **New CLI flags** parsed in `cli.py` under a `--scaling-experiment` guard; when
  absent, `run`/`eval` behave exactly as today. (The only in-tree edit outside
  `scaling/` — a guarded branch that hands off to `scaling.run_experiment(...)`.)
- **Partitioning** (`scaling/partition.py`): deterministic round-robin over
  `sorted(features)` → per-agent feature lists. Pure function; seed-independent
  (determinism is structural). Logged to the run dir.
- **Run orchestration** (`scaling/experiment.py`): for each (pool, K, N, condition,
  trial) cell, invoke the existing `run(...)` (`core.py:38`) with
  `setting="coop"|"solo"`, the partition-derived features, `--no-messaging` for the
  no-comm arm, `-a claude_code`. Reuses all existing launch/token plumbing.
- **N-way eval** (`scaling/eval_nway.py`): new `test_merged_nway(...)` generalizing
  `_setup_branches`/`_merge_naive` to N branches off `BASE_SHA` folded in a **fixed,
  documented, recorded order** (sequential `git merge` fold; order = agents sorted by
  id), reusing `_filter_test_files`, `_run_tests`, and per-feature `tests.patch`
  semantics unchanged. N=1 → no merge (reuse `test_solo` generalized to K suites);
  N=2 → may delegate to the existing `test_merged` for exact parity.
- **Instrumentation** (`scaling/buckets.py`): parse `<agent>_stream.jsonl` /
  `_session.jsonl` / `_sent.jsonl` into the four buckets per §6.
- **Analysis** (`scaling/analysis.py`): emit `runs.csv`; fit `cost(N)=αN+βN²`;
  failure-mix vs N; driver regression. Failure buckets map to eval fields:
  `merge_conflict` ⇐ `merge.status==conflicts`; `capability_fail` ⇐ a feature's
  `*_independent.passed==False`; `merged_but_tests_fail` ⇐ merge clean but
  `both_passed==False` (N-way: not all suites pass).
- **Screening** (`--screen-pools`): run N=1 (`test_solo` generalized) across candidate
  tasks, keep those where solo passes all K within the step/budget cap, and report the
  largest K each supports.

---

## 8. Decisions — resolved defaults (override any before I code)

1. **RESOLVED — pool = solo-screened conflict-clique K-subset of a task**, target =
   union of the K `tests.patch` suites, **no joint-gold-patch artifact**. Full
   rationale in §1. (`combined.patch` is not used; it covers the whole PR, not an
   arbitrary K-subset.)
2. **`claude_code` + `claude-sonnet-5` only.** The per-step buckets require the raw
   stream that only the `claude_code` adapter persists (§3), matching the prior flash
   runs. Other frameworks would degrade the four buckets to aggregate-only.
3. **Ship all four buckets, rework as an audited heuristic.** `context`(first-step
   proxy) / `task`(residual) / `comm`(recoverable) / `rework`(heuristic). The design
   explicitly asks for rework and it's a candidate headline driver, so I keep it but
   emit its **raw feeder signals** (#message-reads, #re-edits-after-`coop-recv`) as
   their own `runs.csv` columns, so the bucket is auditable and can be recomputed or
   discarded downstream without a re-run.
4. **Seeds fix selection + partition only.** Claude Code exposes no sampling seed, so
   a seed cannot make the LLM reproducible; it fixes pool/feature selection and the
   (already deterministic) partition. Trials (`r`) capture model stochasticity. Seeds
   are logged; this caveat is stated in the README and `runs.csv` provenance.
5. **N-way merge fold order = ascending agent id, recorded per run.** Base = agent1's
   branch off `BASE_SHA`, then `git merge agent2`, `agent3`, … `agentN` in order
   (mirrors the existing 2-agent `checkout agent2; merge agent1` shape, generalized
   and pinned). The order string is written into `eval.json` and `runs.csv`.
6. **Screening default: flash's 20 tasks, K=4, r_screen=3, qualify at ≥2/3.** A pool
   qualifies if solo N=1 passes **all K** suites in ≥2 of 3 screening runs, under the
   agent's default turn/budget limit (no artificial cap; `--max-turns` overridable via
   agent config). `--screen-pools` emits the qualified `(repo, task_id, feature-tuple)`
   set with the largest K each task supports.

**Next step:** implement `scaling/` (isolated, flag-gated; base runs byte-identical
when flags off), generalize the eval merge/test path to N (incl. `all_passed`), add the
bucket derivation from saved `claude_code` streams, the analysis (`runs.csv`, α/β fit,
failure-mix, driver regression), a README, and the smoke test (one pool, K=2, N∈{1,2},
r=1, both conditions). Pausing here for your go-ahead per Step 0.
