# Running CooperBench

This page explains how to run agents on the benchmark, what every `run` / `eval`
flag does, and gives copy-paste examples for the common cases (including **solo
over the full dataset with the Claude Code wrapper**).

> All commands below assume you're in the repo root. In a dev checkout, prefix
> with `uv run` (e.g. `uv run cooperbench run ...`); an installed package exposes
> the bare `cooperbench` command.

---

## 1. Prerequisites

1. **Execution backend** — pick one:
   - **`docker`** (default) — runs each task in a local container. Simplest; what
     this guide assumes.
   - **`modal`** — cloud sandboxes (`modal setup`).
   - **`gcp`** — Google Cloud VMs (`cooperbench config gcp`).
2. **Task images** — the Docker backend pulls `akhatua/cooperbench-*` images per
   task. On **amd64** hosts, 14 of the 30 tasks are arm64-only on Docker Hub and
   must be rebuilt locally first — see
   [`scripts/local_images/PLAN.md`](../scripts/local_images/PLAN.md) and run
   `scripts/local_images/sync_local_dataset.sh`. Once built/pulled locally, the
   backend uses the local image automatically.
3. **Dataset** — `cooperbench prepare` downloads it into `./dataset` (already
   present in a repo checkout).
4. **Model credentials** — set in `.env` or the environment:
   - Default agent uses a hosted model → needs `GEMINI_API_KEY` / `OPENAI_API_KEY`
     / `ANTHROPIC_API_KEY` depending on `-m`.
   - **`claude_code` agent** can run on a **Claude Max/Pro subscription** with no
     key at all — it auto-reads your `~/.claude/.credentials.json` OAuth token
     (or `CLAUDE_CODE_OAUTH_TOKEN`, or `ANTHROPIC_API_KEY`, in that order).
5. **Redis** — only for `--setting coop` / `team` (inter-agent messaging):
   `docker run -p 6379:6379 redis:7`. Not needed for `solo`.

---

## 2. Quick start

```bash
# Solo agent on one task, local Docker, Claude via your Max subscription
cooperbench run -n my-first-run -r pillow_task -t 25 -f 1,2 \
  -a claude_code -m claude-sonnet-4-6 --setting solo

# Results are evaluated automatically. To re-evaluate later:
cooperbench eval -n my-first-run
```

---

## 3. The three settings (`--setting`)

| Setting | Agents | Needs Redis | What happens |
|---|---|---|---|
| **`solo`** | 1 | no | One agent implements **every feature** of the task, alone in one container. |
| **`coop`** *(default)* | N peers | yes | N agents, one feature each, talking over Redis (`coop-send`/`coop-recv`). Add `--git` for a shared remote so they can merge each other's branches. |
| **`team`** | 1 lead + N−1 members | yes | Shared Redis task list (atomic claims), a shared `/workspace/shared` scratchpad volume, and lead/member role prompts. `result.json` gains a coordination `metrics` block. |

All three are scored identically by `eval`: per-feature tests against each agent's
patch.

---

## 4. `cooperbench run` — every flag

### Selection (which tasks/pairs to run)
| Flag | Default | Meaning |
|---|---|---|
| `-n, --name` | auto | Experiment name; becomes the `logs/<name>/` directory. |
| `-s, --subset` | — | Run a predefined subset from `dataset/subsets/` (`lite`, `flash`, `core`). |
| `-r, --repo` | all | Filter to one repository, by **dir name** (e.g. `pillow_task`, `llama_index_task`). |
| `-t, --task` | all | Filter to one task **id** (integer, e.g. `25`). |
| `-f, --features` | all pairs | Run a single feature pair, comma-separated (e.g. `1,2`). Omit to run every pair. |

### Agent & model
| Flag | Default | Meaning |
|---|---|---|
| `-a, --agent` | `mini_swe_agent_v2` | Agent framework. One of: `mini_swe_agent_v2`, `claude_code`, `codex`, `openhands_sdk`, `swe_agent`. |
| `-m, --model` | `vertex_ai/gemini-3-flash-preview` | Model id passed to the agent. For `claude_code`: a bare Claude id like `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-haiku-4-5-20251001` (provider prefix is stripped). |
| `--agent-config` | — | Path to an agent-specific config file (format depends on the agent). |

### Custom / self-hosted model endpoint
| Flag | Default | Meaning |
|---|---|---|
| `--base-url` | — | Anthropic-compatible base URL, forwarded as `ANTHROPIC_BASE_URL`. Point straight at a vLLM ≥0.17.1 `/v1/messages` server, no proxy. |
| `--auth-token` | — | Token paired with `--base-url`, forwarded as `ANTHROPIC_AUTH_TOKEN` (use any placeholder for unauthenticated endpoints). |

### Setting & coordination
| Flag | Default | Meaning |
|---|---|---|
| `--setting` | `coop` | `solo` / `coop` / `team` (see §3). |
| `--git` | off | (coop) Enable a shared `team` git remote so peers can fetch/merge each other's branches. |
| `--no-messaging` | off | Disable the `send_message` command between agents. |
| `--redis` | `redis://localhost:6379` | Redis URL for coop/team messaging. |
| `--team-no-task-list` | off | (team) Disable the shared Redis task list + pre-seeding + metrics. |
| `--team-no-scratchpad` | off | (team) Disable the `/workspace/shared` volume. |
| `--team-no-mcp` | off | (team) Skip MCP `wait_for_message` registration. |
| `--team-no-auto-refresh` | off | (team) Drop the in-loop task-list summary injection. |
| `--team-no-protocol` | off | (team) Drop the typed `coop-request`/`coop-respond`/`coop-pending` verbs. |

### Execution & evaluation
| Flag | Default | Meaning |
|---|---|---|
| `--backend` | `docker` | `docker` (local) / `modal` (cloud) / `gcp` (VM). |
| `-c, --concurrency` | `30` | Number of tasks run in parallel. |
| `--no-auto-eval` | off | Skip the automatic eval pass after the run (run only). |
| `--eval-concurrency` | `10` | Parallelism for the auto-eval pass. |
| `--force` | off | Re-run even if results already exist for these tasks. |
| `--dataset-dir` | `./dataset` | Root of the dataset tree. |
| `--log-dir` | `./logs` | Root to write run logs under. |

---

## 5. `cooperbench eval` — score existing runs

Evaluation runs automatically after `run` unless you pass `--no-auto-eval`. Run it
manually to (re)score a prior experiment:

```bash
cooperbench eval -n my-first-run
```

| Flag | Default | Meaning |
|---|---|---|
| `-n, --name` | *(required)* | Experiment name to evaluate (the `logs/<name>/` dir). |
| `-s, --subset` | — | Restrict to a subset. |
| `-r, --repo` / `-t, --task` / `-f, --features` | all | Same selection filters as `run`. |
| `-c, --concurrency` | `10` | Parallel evaluations. |
| `--force` | off | Re-evaluate even if `eval.json` exists. |
| `--backend` | `docker` | Where to run the test containers. |
| `--dataset-dir` / `--log-dir` | `./dataset` / `./logs` | Tree roots. |

---

## 6. Output layout

Each run writes under `logs/<name>/`:

```
logs/<name>/
├── config.json                 # the run configuration
├── summary.json                # aggregate results
└── <setting>/<repo>/<task>/f<a>_f<b>/
    ├── result.json             # status, cost, steps, tokens, patch_lines
    ├── eval.json               # pass/fail per feature
    ├── <setting>.patch         # the agent's produced patch
    ├── <setting>_session.jsonl # full message log
    ├── <setting>_traj.json     # trajectory
    └── <setting>_stream.jsonl  # raw model stream
```

---

## 7. Common example runs

**Solo over the FULL dataset, Claude Code wrapper (Max subscription):**
```bash
cooperbench run -n solo-claude-full \
  -a claude_code -m claude-sonnet-4-6 \
  --setting solo --backend docker
# no -r/-t/-f  -> every task, every feature pair. Uses your Max OAuth token; no key needed.
```

**Quick smoke test — one task, one feature pair, solo:**
```bash
cooperbench run -n smoke -r pillow_task -t 25 -f 1,2 \
  -a claude_code -m claude-sonnet-4-6 --setting solo
```

**A fast subset instead of the whole dataset:**
```bash
cooperbench run -n lite-claude -s lite \
  -a claude_code -m claude-opus-4-8 --setting solo
```

**Cooperative peers (needs Redis), with shared git remote:**
```bash
docker run -d -p 6379:6379 redis:7
cooperbench run -n coop-claude -r llama_index_task -t 17070 \
  -a claude_code -m claude-sonnet-4-6 --setting coop --git
```

**Team mode (lead + members):**
```bash
docker run -d -p 6379:6379 redis:7
cooperbench run -n team-claude -r dspy_task -t 8563 \
  -a claude_code -m claude-sonnet-4-6 --setting team
```

**Default agent on a hosted model (needs the matching API key in `.env`):**
```bash
cooperbench run -n gemini-coop -r pillow_task -t 25 \
  -a mini_swe_agent_v2 -m vertex_ai/gemini-3-flash-preview --setting coop
```

**Run only, evaluate later:**
```bash
cooperbench run -n later -r pillow_task -t 25 --setting solo --no-auto-eval
cooperbench eval -n later
```

**Self-hosted vLLM endpoint:**
```bash
cooperbench run -n vllm-run -r pillow_task -t 25 --setting solo \
  -a claude_code -m my-model \
  --base-url https://your-vllm-host.example.com --auth-token placeholder
```

---

## 8. Notes & gotchas

- **amd64 hosts:** ensure the local images exist first
  (`scripts/local_images/sync_local_dataset.sh`); otherwise arm64-only tasks fail
  with `no matching manifest for linux/amd64`.
- **`solo` runs every feature pair** of a task (e.g. 5 features → C(5,2)=10
  containers). Scope with `-f a,b` for a single pair while testing.
- **`claude_code` cost** shown in the summary is the token-usage equivalent; on a
  subscription it's billed against your plan, not as API dollars.
- **`coop`/`team` require Redis** at `--redis` (default `redis://localhost:6379`).
- Use `--force` to overwrite prior results for the same task/experiment.
- Lower `-c/--concurrency` if you hit memory/CPU limits running many heavy
  containers at once.
