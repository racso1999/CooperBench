# Six messaging protocols on the nano_py conflict set — results

*Results dump, no interpretation. This records what was run and what came out, for the six no-git cooperation protocols on the capability-screened Python conflict subset. It sits alongside the replication study (which localised the two-agent gap to patch integration) and the scaling study (agent-count cost). All numbers here are computed by `masters_thesis/protocol_analysis/analyze.py` over the run logs; the frozen output is `masters_thesis/protocol_analysis/data/nano_study.json`. Reproducibility commands are at the end.*

## Setup

**What varies.** Six arms. Each arm differs from the others *only* in the cooperation-protocol block appended to the agent system prompt, plus the message-field validation the container enforces. Same model (Claude Sonnet 5, Claude Code scaffold), same tasks, same evaluation, same integration model (each agent edits its own private checkout; the evaluator combines the two independent patches with a naive two-branch `git merge`; no shared workspace, no post-hoc conflict resolution). In the structured arms the messaging CLI hard-rejects any message that omits a required field or violates an enum; field *values* stay free text, only the coordination metadata is enforced.

**Subset.** A capability-screened 20-pair Python subset ("nano"), one conflicting pair per task, pre-filtered by static gold-patch overlap (shared files and intersecting hunk ranges). 18 pairs survive pre-registered screening (`docs/nano_py_preregistration.md`); the 2 drops are ceiling cases (control both-passed ≥ 73% > 60%).

**Endpoints.**
- **Primary — merge-clean rate:** fraction of pair-runs whose two independent patches merge with status in {`clean`, `identical`}. `identical` = both agents emitted byte-for-byte identical merged code (git reports "identical", not a conflict).
- **Secondary — both-passed:** both features' held-out suites pass on the merged tree.

**Runs and inference.** k ≈ 15 replicates/pair for the four full-set arms (≈ 270 pair-runs each); k ≈ 5 for the two overlap-resolution arms (88 and 89 runs — three runs produced no eval record). Rates are over all runs (n), so non-applied runs count in the denominator. Per-arm rates carry Wilson 95% CIs (descriptive). Inferential test: Cochran–Mantel–Haenszel stratified by pair, Holm-corrected across the family of 8 contrasts. No run in this dataset carried an infrastructure-failure flag.

## The six arms and their prompts

Ordered control → talk-only → plan-only → authorship-changing. Each block is verbatim as rendered to `agent1` (working alongside `agent2`); `<...>` are the CLI's own argument hints.

### 1. control — no messaging

No cooperation block at all; the agent is never told it has a partner.

> *(no cooperation block)*

### 2. free-text — unconstrained messaging

Redis-backed inbox, free-text send/broadcast/recv, recommended-but-unenforced workflow.

````
## Cooperation protocol

You are **agent1**, working alongside: **agent2**.
Each agent has been assigned a separate feature from the same codebase;
your features may overlap (touch the same files), so coordinate to avoid
clobbering each other's changes.

Available shell commands for cross-agent messaging (Redis-backed inbox,
one inbox per agent):

```bash
coop-send <recipient> "message text here"   # send to a specific peer
coop-broadcast "message text here"          # send to every other peer
coop-recv                                    # drain your inbox (prints JSON list)
coop-peek                                    # number of unread messages
coop-agents                                  # list every agent id
```

Recommended workflow:

1. At the start, `coop-broadcast` a short summary of your feature and
   which files you intend to touch.
2. Periodically `coop-recv` to read what your peers have sent — at
   minimum after major edits and before submitting.
3. If two agents need to modify the same file, coordinate explicitly
   (split the file, agree on one owner, or merge changes).
4. Keep messages short and focused: file names, function names, and
   one-sentence intents are usually enough.

Messages are not magic — your peers only know what you tell them.
````

### 3. semi_structured — typed, field-validated messages

Every message must carry `type` (CLAIM / INTENT / QUESTION / ANSWER / STATUS), `files`, and a one-sentence `summary`; malformed messages are rejected.

````
## Cooperation protocol (structured messaging)

You are **agent1**, working alongside: **agent2**.
Each agent has been assigned a separate feature from the same codebase;
your features may overlap (touch the same files), so coordinate to avoid
clobbering each other's changes.

Cross-agent messages are **structured** (schema `semi_structured_v1`). Every
`coop-send` / `coop-broadcast` MUST supply these fields as flags:

- `--type` (required) — one of: CLAIM, INTENT, QUESTION, ANSWER, STATUS: the kind of message
- `--files` (required): comma-separated files/regions you will touch (declare early to avoid clobbering peers)
- `--summary` (required): one-sentence intent
- `--blocked_on` (optional): anything you need from a peer before you can proceed

**Messages that omit a required field or use an out-of-enum value are
REJECTED — they exit non-zero and are NOT delivered to your peer.** Field
values are free text; only these coordination fields are enforced.

```bash
coop-send agent2 --type "CLAIM" --files "<files>" --summary "<summary>"                       # send to a specific peer
coop-broadcast --type "CLAIM" --files "<files>" --summary "<summary>"   # send to every other peer
coop-recv                                    # drain your inbox now (prints JSON list)
coop-await                                   # BLOCK until a peer replies, then drain
coop-peek                                    # number of unread messages
coop-agents                                  # list every agent id
```

Recommended workflow:

1. At the START, broadcast which files you intend to touch, before you begin editing.
2. `coop-recv` (or `coop-await`) to read your peers' messages — at minimum after
   major edits and before submitting — and if two agents want the same file,
   coordinate explicitly (split it, agree on one owner, or merge changes).
3. Keep each field short and specific.

Messages are not magic — your peers only know what you tell them.
````

### 4. plan_handshake — agree a disjoint file split before editing

Phase 1: exchange PROPOSE / ACCEPT / REVISE (blocking on `coop-await`) until a disjoint file partition is mutually agreed. Only then may agents edit.

````
## Cooperation protocol (structured messaging)

You are **agent1**, working alongside: **agent2**.
Each agent has been assigned a separate feature from the same codebase;
your features may overlap (touch the same files), so coordinate to avoid
clobbering each other's changes.

Cross-agent messages are **structured** (schema `plan_handshake_v1`). Every
`coop-send` / `coop-broadcast` MUST supply these fields as flags:

- `--type` (required) — one of: PROPOSE, ACCEPT, REVISE, DONE: handshake message type
- `--my_files` (required): comma-separated files YOU will own and edit
- `--your_files` (optional): comma-separated files you propose your PARTNER owns
- `--note` (optional): optional short rationale

**Messages that omit a required field or use an out-of-enum value are
REJECTED — they exit non-zero and are NOT delivered to your peer.** Field
values are free text; only these coordination fields are enforced.

```bash
coop-send agent2 --type "PROPOSE" --my_files "<my_files>"                       # send to a specific peer
coop-broadcast --type "PROPOSE" --my_files "<my_files>"   # send to every other peer
coop-recv                                    # drain your inbox now (prints JSON list)
coop-await                                   # BLOCK until a peer replies, then drain
coop-peek                                    # number of unread messages
coop-agents                                  # list every agent id
```

Coordinate in TWO STRICT PHASES. Do NOT edit any file until Phase 1 is complete.

PHASE 1 — PLAN & HANDSHAKE (messages only, NO editing yet):
1. Immediately send a PROPOSE: `my_files` = the files YOU will own (from your
   feature), `your_files` = the files you think your PARTNER should own. Keep the
   two sets DISJOINT.
2. Run `coop-await` — it BLOCKS until your partner replies — to read their messages.
3. If their split gives you a disjoint set you can implement your feature with,
   reply ACCEPT (echo the agreed `my_files`). Otherwise reply REVISE with a better
   split and `coop-await` again. Repeat until you have RECEIVED an ACCEPT from your
   partner AND sent your own ACCEPT.
4. Only after you have received your partner's ACCEPT may you begin editing.

PHASE 2 — IMPLEMENT:
5. Edit ONLY the files in your agreed `my_files`. If you discover you genuinely must
   touch a file your partner owns, send a REVISE and re-agree BEFORE touching it.
6. Send DONE when your implementation is finished.

The whole point: agree a disjoint file split up front so your patches never collide
at merge time.

Messages are not magic — your peers only know what you tell them.
````

### 5. designated_coder — one owner per shared file, the other sends a spec

For any file both features need, one owner is assigned; the non-owner DEFERs, sends a SPEC of what it needs, and leaves the file untouched. The owner implements both features there.

````
## Cooperation protocol (structured messaging)

You are **agent1**, working alongside: **agent2**.
Each agent has been assigned a separate feature from the same codebase;
your features may overlap (touch the same files), so coordinate to avoid
clobbering each other's changes.

Cross-agent messages are **structured** (schema `designated_coder_v1`). Every
`coop-send` / `coop-broadcast` MUST supply these fields as flags:

- `--type` (required) — one of: SURVEY, CLAIM, DEFER, SPEC, DONE: coordination message type
- `--files` (required): comma-separated files this message is about (all files you touch, for SURVEY; the owned/deferred file, for CLAIM/DEFER/SPEC)
- `--spec` (optional): when DEFERring, a precise self-contained description of what your feature needs done in that file, for the owner to implement
- `--note` (optional): optional short rationale or the function name(s) involved

**Messages that omit a required field or use an out-of-enum value are
REJECTED — they exit non-zero and are NOT delivered to your peer.** Field
values are free text; only these coordination fields are enforced.

```bash
coop-send agent2 --type "SURVEY" --files "<files>"                       # send to a specific peer
coop-broadcast --type "SURVEY" --files "<files>"   # send to every other peer
coop-recv                                    # drain your inbox now (prints JSON list)
coop-await                                   # BLOCK until a peer replies, then drain
coop-peek                                    # number of unread messages
coop-agents                                  # list every agent id
```

Coordinate in THREE STRICT PHASES. Do NOT edit any file until Phase 2 is agreed.

PHASE 1 — DISCOVER SHARED FILES (messages only, NO editing yet):
1. Immediately send a SURVEY: `files` = every file (and, in `note`, the specific
   function(s)) YOUR feature must edit. Be exhaustive and precise.
2. Run `coop-await` — it BLOCKS until your partner replies — to read their SURVEY.
3. Intersect the two file lists. The intersection is your SHARED files; everything
   else is yours alone.

PHASE 2 — ASSIGN A SINGLE OWNER PER SHARED FILE (still NO editing):
4. For EACH shared file, agree exactly ONE owner. Send CLAIM (`files` = the shared
   file(s) you will OWN and write) or DEFER (`files` = the shared file(s) you hand
   to your partner). Every shared file must end up with exactly one owner.
5. If you DEFER a file, you MUST send a SPEC for it: `files` = that file, `spec` =
   a precise, self-contained description of exactly what YOUR feature needs done in
   it (signatures, parameters, behaviour, return values, edge cases) — enough for
   the owner to implement your feature correctly without seeing your tests.
6. `coop-await` and repeat until every shared file has one owner AND every deferred
   file has a delivered SPEC that its owner has ACKNOWLEDGED (reply CLAIM echoing it).

PHASE 3 — IMPLEMENT:
7. Edit ONLY: your own (non-shared) files, plus the shared files you OWN. In each
   file you own that is shared, implement BOTH your feature AND your partner's SPEC.
8. Do NOT touch any shared file you deferred — leave it entirely to its owner.
9. Send DONE when finished.

The whole point: every shared file is written by exactly one agent, so independent
patches never collide there; the deferring agent's needs travel as a SPEC instead
of as conflicting edits.

Messages are not magic — your peers only know what you tell them.
````

### 6. coauthor_overlap — both agents write byte-identical merged code

Where two features overlap in one construct, the pair jointly authors the full merged version of it and both agents write that agreed text byte-for-byte identically.

````
## Cooperation protocol (structured messaging)

You are **agent1**, working alongside: **agent2**.
Each agent has been assigned a separate feature from the same codebase;
your features may overlap (touch the same files), so coordinate to avoid
clobbering each other's changes.

Cross-agent messages are **structured** (schema `coauthor_overlap_v1`). Every
`coop-send` / `coop-broadcast` MUST supply these fields as flags:

- `--type` (required) — one of: SURVEY, DRAFT, AGREE, DONE: coordination message type
- `--files` (required): comma-separated files this message is about
- `--region` (optional): which overlapping construct this DRAFT/AGREE is about (e.g. 'encode() method')
- `--code` (optional): the complete verbatim source of the merged construct — must be byte-identical to your partner's
- `--note` (optional): optional short rationale or the construct name(s) involved

**Messages that omit a required field or use an out-of-enum value are
REJECTED — they exit non-zero and are NOT delivered to your peer.** Field
values are free text; only these coordination fields are enforced.

```bash
coop-send agent2 --type "SURVEY" --files "<files>"                       # send to a specific peer
coop-broadcast --type "SURVEY" --files "<files>"   # send to every other peer
coop-recv                                    # drain your inbox now (prints JSON list)
coop-await                                   # BLOCK until a peer replies, then drain
coop-peek                                    # number of unread messages
coop-agents                                  # list every agent id
```

Coordinate in THREE STRICT PHASES. Do NOT edit any file until Phase 2 is agreed.

PHASE 1 — DISCOVER OVERLAPPING CONSTRUCTS (messages only, NO editing yet):
1. Immediately send a SURVEY: `files` = every file YOUR feature must edit, and in
   `note` name the specific construct(s) — function/class/import block — you must
   change (e.g. "the `encode()` method").
2. Run `coop-await` — it BLOCKS until your partner replies — to read their SURVEY.
3. Identify OVERLAPPING constructs: any function/class/block you BOTH must edit.

PHASE 2 — CO-AUTHOR THE OVERLAP (still NO editing):
4. For EACH overlapping construct, jointly write the FULL merged version of it — one
   implementation that carries BOTH features' behaviour at once (e.g. the whole
   `encode()` method with BOTH new parameters AND both new code paths). Send a DRAFT:
   `region` = which construct, `code` = the complete verbatim source of the merged
   construct.
5. `coop-await`, compare against your partner's DRAFT character-for-character. If they
   differ in ANY way (order, whitespace, types, trailing commas), send a new DRAFT
   until you converge. Then send AGREE echoing the exact `code`. You must BOTH end
   Phase 2 holding the identical agreed text for every overlapping construct.

PHASE 3 — IMPLEMENT:
6. For every overlapping construct, write the agreed `code` VERBATIM — copy it
   exactly, do not paraphrase, retype, or reformat it. Both of you write the same text.
7. For any construct only YOU touch (not overlapping), implement it normally — but it
   must not overlap your partner's non-shared constructs.
8. Send DONE when finished.

The whole point: for every construct you both edit, your patch and your partner's
patch contain the IDENTICAL merged code, so git merges them as identical rather than
conflicting — and each patch already satisfies both features there.

Messages are not magic — your peers only know what you tell them.
````

## Results

### Endpoints (validated 18-pair set)

| arm | runs | applied | merge-clean (primary) | both-passed (secondary) |
|---|---|---|---|---|
| control (no messaging) | 270 | 89% | 13% [10–18] | 2% [1–4] |
| free-text | 270 | 83% | 21% [17–26] | 3% [2–6] |
| semi_structured | 270 | 89% | 16% [12–21] | 3% [2–6] |
| plan_handshake | 270 | 93% | 20% [16–25] | 10% [7–15] |
| designated_coder | 88 | 86% | 18% [12–28] | 58% [48–68] |
| coauthor_overlap | 89 | 94% | 78% [68–85] | 69% [58–77] |

*merge-clean = merge status in {clean, identical}. Brackets are Wilson 95% CIs (descriptive). Rates are over all runs; "applied" is the share of runs where the patch applied.*

- Merge-clean: five arms fall in a 13–21% band; coauthor_overlap is 78%.
- both-passed: designated_coder 58% and coauthor_overlap 69% are the two high values; plan_handshake 10%; the rest ≤ 3%.

![Endpoints by arm: merge-clean vs both-passed](masters_thesis/protocol_analysis/figures/fig1_endpoints.png)

### Inference — primary endpoint (merge-clean, CMH stratified by pair, Holm-corrected)

| contrast | base | arm | CMH OR | *p* (Holm) |
|---|---|---|---|---|
| free-text vs control | 13% | 21% | 1.79 | 0.105 |
| semi_structured vs control | 13% | 16% | 1.24 | 1.000 |
| plan_handshake vs control | 13% | 20% | 1.63 | 0.159 |
| designated_coder vs control | 13% | 18% | 1.43 | 1.000 |
| coauthor_overlap vs control | 13% | 78% | 27.7 | 3.1e-29 |
| coauthor_overlap vs plan_handshake | 20% | 78% | 10.4 | 9.1e-24 |
| coauthor_overlap vs designated_coder | 18% | 78% | 16.0 | 1.4e-13 |
| designated_coder vs plan_handshake | 20% | 18% | 0.91 | 1.000 |

- After Holm correction, coauthor_overlap is the only arm that separates from control on merge-clean (and from the next-best arms in head-to-heads). The other four arm-vs-control contrasts are non-significant.

### Inference — secondary endpoint (both-passed, CMH stratified by pair, Holm-corrected)

| contrast | *p* (Holm) | CMH OR |
|---|---|---|
| coauthor_overlap vs control | 3.7e-43 | 90.2 |
| designated_coder vs control | 1.1e-35 | 75.6 |
| coauthor_overlap vs plan_handshake | 2.4e-29 | — |
| designated_coder vs plan_handshake | 3.9e-23 | — |
| plan_handshake vs control | 8.1e-05 | 5.9 |
| coauthor_overlap vs designated_coder | 0.476 | — |
| free-text vs control | 1.000 | — |
| semi_structured vs control | 1.000 | — |

- On both-passed, plan_handshake, designated_coder, and coauthor_overlap all beat control after correction. coauthor_overlap and designated_coder are not distinguishable from each other on this endpoint (*p* = 0.48), despite their merge-clean rates being 78% vs 18%.

### Failure taxonomy (each pair-run in exactly one bucket, over n)

Buckets: `pass` = clean/identical merge AND both features pass; `solo_rescue` = both features pass but the merge was not clean (one patch carried the pair); `functional_fail` = clean merge, code fails; `textual_conflict` = patches collided; `missing_patch` = a patch did not apply.

| arm | pass | solo_rescue | functional_fail | textual_conflict | missing_patch |
|---|---|---|---|---|---|
| control | 2% | 0% | 1% | 87% | 11% |
| free-text | 3% | 0% | 1% | 79% | 17% |
| semi_structured | 3% | 0% | 2% | 84% | 11% |
| plan_handshake | 10% | 0% | 3% | 80% | 7% |
| designated_coder | 5% | 43% | 0% | 39% | 14% |
| coauthor_overlap | 62% | 6% | 10% | 17% | 6% |

- Textual-conflict share: 79–87% for control / free-text / semi_structured / plan_handshake; 39% for designated_coder; 17% for coauthor_overlap.
- designated_coder's both-passed comes almost entirely through `solo_rescue` (43% of its runs — both features pass on a non-clean merge), not through `pass` (5%).
- Note the taxonomy `pass`+`solo_rescue` (dc 48%, coauthor 68%) does not equal the both-passed endpoint (dc 58%, coauthor 69%): the both-passed endpoint also credits runs where a patch did not apply but both suites still pass on the merged tree; the taxonomy routes those to `missing_patch`.

![Failure taxonomy by arm](masters_thesis/protocol_analysis/figures/fig2_failure_taxonomy.png)

### Merge status split (validated set)

| arm | identical | clean | conflicts/other |
|---|---|---|---|
| control | 0 (0%) | 36 (13%) | 234 (87%) |
| free-text | 0 (0%) | 57 (21%) | 213 (79%) |
| semi_structured | 0 (0%) | 43 (16%) | 227 (84%) |
| plan_handshake | 0 (0%) | 54 (20%) | 216 (80%) |
| designated_coder | 1 (1%) | 15 (17%) | 72 (82%) |
| coauthor_overlap | 26 (29%) | 43 (48%) | 20 (22%) |

- `identical` merges (both agents emitting byte-for-byte identical merged code): 26 of coauthor_overlap's 89 runs (29%); exactly 1 across all 1,168 runs of the other five arms combined (a single designated_coder run).

### Pre-merge capability (feature-independent, validated set)

| arm | pair-runs with ≥1 feature passing independently |
|---|---|
| control | not recorded |
| free-text | not recorded |
| semi_structured | 86% (n=270) |
| plan_handshake | 97% (n=270) |
| designated_coder | 94% (n=88) |
| coauthor_overlap | 90% (n=89) |

- Where recorded, at least one feature passed independently (before merge) in 86–97% of pair-runs. control and free-text evals do not record per-feature independent results.

### designated_coder message compliance (from transcripts)

- SURVEY, CLAIM, and DEFER are exchanged in 100% of its validated runs.
- The SPEC message, which the protocol makes mandatory whenever a file is deferred, is sent in only 39% of runs.
- 39% of its runs still end in a textual conflict — i.e. both branches touched the same region despite one agent having deferred the file.

## Concerns / caveats

- **Two arms are low-k.** designated_coder and coauthor_overlap ran at k ≈ 5 (88 and 89 runs) versus ≈ 270 for the other four. Their Wilson intervals are correspondingly wider. coauthor_overlap's primary-endpoint effect survives correction by many orders of magnitude regardless; the low-k caution bites hardest on designated_coder.
- **The designated_coder primary null is an interval, not an identity.** At 88 runs, "18%, indistinguishable from the 13% floor" means a small real benefit could still sit inside the CI [12–28]. It is not established that designated_coder equals the floor, only that it is not distinguishable from it here.
- **The capability-floor screen never fired.** The pre-registration specified dropping pairs where neither feature builds solo (>10% control), but control evals do not record per-feature independent results, so that criterion was undefined for every pair; screening reduced in practice to the ceiling rule alone. Net effect: no pair was removed for being beyond the model, so the retained set is, if anything, harder than intended.
- **both-passed vs taxonomy mismatch.** As noted above, the secondary endpoint and the taxonomy count different things when a patch fails to apply; compare like-for-like when reading the two tables together.
- **Three missing eval records.** The two overlap-resolution arms fall short of 18 × 5 = 90 (88, 89) because three runs produced no eval record. They are dropped from denominators, not scored as failures.
- **Residual failure in the winning arm.** coauthor_overlap still leaves 17% textual conflict and 10% functional_fail; the byte-identical requirement is not always met, and clean merges still fail functionally at a nonzero rate.
- **Scope.** One model (Claude Sonnet 5), one scaffold, conflict-selected Python pairs (one per task, chosen because their gold patches collide), and one fixed integration model (isolated checkouts, naive two-branch merge, no post-hoc conflict resolution). No per-repository or per-language estimates. Results are conditional on all of the above; a different integration model (e.g. a shared workspace with live conflict resolution) is a harness change, not tested here.
- **Denominator convention.** Rates are over all runs n, so the varying "applied" rates (83–94%) fold non-applied runs into the failure mass. Reading rates over `applied` instead would shift every arm upward and by different amounts.

---

### Reproducibility

- **Numbers.** Computed by `masters_thesis/protocol_analysis/analyze.py` over the six no-git arms in `logs/`. Frozen output: `masters_thesis/protocol_analysis/data/nano_study.json`. Regenerate with `uv run python masters_thesis/protocol_analysis/analyze.py` (also prints the merge-status split, pre-merge capability, and a per-pair merge-clean appendix not reproduced above).
- **Figures.** `masters_thesis/protocol_analysis/figures.py` reads that JSON and writes `figures/fig1_endpoints.png` and `fig2_failure_taxonomy.png`. Run `uv run --with matplotlib python masters_thesis/protocol_analysis/figures.py`.
- **Protocol prompts.** The blocks above are the verbatim cooperation-protocol sections rendered by `cooperbench.agents._coop.prompt.build_instruction`; the structured schemas live in `src/cooperbench/agents/_coop/message_schema.toml` (semi_structured) and `schemas/{plan_handshake,designated_coder,coauthor_overlap}.toml`. Each arm is selected at run time by `--structured-messaging <schema>` (or `--no-messaging` for control) on `cooperbench run --setting coop`.
