# From Failure Modes to Protocols: the Complete Chain

**The claim this document supports:** system-prompt-level intervention alone is
sufficient to produce substantial coordination improvement in two-agent coding.
Every protocol below is implemented purely as a system prompt plus message-field
validation — same model, same scaffold, same tasks — and the best of them lifts
the pre-registered primary endpoint ~6× over control.

The chain has three links: (1) failure modes identified on the flash free-messaging
run, (2) each protocol arm read as a targeted intervention against a specific mode,
(3) the pre-registered nano RCT showing which interventions worked. The punchline is
that the flash failure analysis *predicts* the nano results.

---

## 1. Failure modes found in flash_msg_1 (free messaging, n = 47 evaluable)

Decomposition: 21/47 pairs capability-clean (both agents passed their own feature
independently) → 6 passed → **15 coordination failures**. Mechanical classification
of those 15 (from archived patches, merge diffs, gold patches, and transcripts):

| # | Finding | Count | Evidence |
|---|---|---|---|
| F1 | **Failure is spatial, not semantic.** Every coordination failure is a textual merge conflict; zero capability-clean pairs died of incompatible semantics after a clean merge | 15/15 | `eval.json` merge status |
| F2 | **The overlap is task-inherent.** The gold reference patches for the two features also collide (±3 lines, same file) in every failing pair — by construction: benchmark pairs are selected for gold-patch conflict | 15/15 | gold `feature.patch` hunk comparison |
| F3 | **Information exchange is not the deficit.** The eventually-conflicting file was named in the conversation in every failure; every agent declared the overlap files it touched | 15/15 | `conversation.json` vs patch files |
| F4 | **Agreement without resolution.** Agents identify the collision precisely, agree a plan ("let's each add our own param"), and still emit textually colliding edits | dominant pattern | transcripts (e.g. click 2068 f6_f7) |
| F5 | **Wrong merge model.** Agents reason as if in a shared workspace ("your changes aren't present in my copy… you hadn't touched the files yet — go ahead"); nothing in the free-msg prompt describes the naive-merge evaluation | recurring | transcripts (dspy 8394, jinja 1465) |

What the 6 passes did differently: negotiated **sub-file placement** (method/line
granularity), placed new code in disjoint regions, confirmed disjointness — i.e.
they *resolved* the overlap rather than talking about it. File-level overlap did not
predict failure (45/47 pairs overlapped on files; 14 of those merged clean).

**Reading against the original CooperBench taxonomy:** our failures are concentrated
in their *expectation failures* (information shared but not integrated into action)
with clear instances of the *trust paradox* (F5). Their *communication failures*
(vague/unanswered messages) are nearly absent here, and — on these conflict-selected
Python pairs — their claim that agents are "decent at spatial coordination" inverts:
spatial failure is the whole story.

---

## 2. Each protocol arm as a targeted intervention

All arms: same model (claude-sonnet-5), same 20-pair nano set (capability-screened),
no git, intervention = system prompt + message schema only.

| Arm | Protocol mechanism | Failure mode it targets | Prediction from §1 |
|---|---|---|---|
| `nano_control` | no messaging | — (floor) | conflicts dominate |
| `nano_msg` | free-text messages | F3 (exchange information) | **no effect** — F3 shows information already flows |
| `nano_struct` | every message must carry `type` (CLAIM/INTENT/…) + `files` + `summary` | F3 (declare more clearly) | **no effect** — declarations were already made and accurate |
| `nano_handshake` | 2-phase PROPOSE/ACCEPT of a **disjoint file split** before editing | F1 at file granularity | **no effect** — F2 says overlap is *within* files; a file split cannot exist |
| `nano_dc` (designated_coder) | for each shared file, one agent owns and writes the union; the other defers + sends a spec | F4 (eliminate dual authorship) | should work **if** the deferring agent actually defers |
| `nano_coauthor` (coauthor_overlap) | for each overlapping construct, both agents co-author and emit **byte-identical merged code** | F4 + F5 directly (git merges identical hunks cleanly) | **should work** — resolves the collision itself |

---

## 3. Did the improvements happen? (pre-registered nano RCT, 18 validated pairs)

Primary endpoint = merge-clean rate; CMH stratified by pair, Holm-corrected.
(Numbers from the pre-registered analysis, `scripts/nano/analyze_study.py`;
full writeup recoverable at git `9b6bbc6c:docs/nano_protocol_study_results.md`.)

| Arm | runs | merge-clean | vs control (CMH OR) | Holm p | verdict |
|---|---|---|---|---|---|
| control (no msg) | 270 | 13% | — | — | floor |
| free-text | 270 | 21% | 1.79 | 0.105 | ns — **as predicted** |
| semi_structured | 270 | 16% | 1.24 | 1.000 | ns — **as predicted** |
| plan_handshake | 270 | 20% | 1.63 | 0.159 | ns — **as predicted** |
| designated_coder | 88 | 18% | 1.43 | 1.000 | ns — see below |
| **coauthor_overlap** | 89 | **78%** | **27.7** | **<0.0001** | **✓ — as predicted** |

Failure-taxonomy shift (the mechanism, visible directly):

| Arm | textual_conflict | honest pass | identical merges |
|---|---|---|---|
| control | 87% | 2% | 0% |
| free-text / struct / handshake | 79–84% | 3–10% | 0% |
| **coauthor_overlap** | **17%** | **62%** | **29%** |

- **coauthor_overlap collapses the conflict rate from ~87% to 17%** and is the only
  arm producing `identical` merges (29%) — the direct fingerprint of the protocol:
  both agents emitting the same merged construct. This is the fix for F4/F5.
- **designated_coder fails for a diagnosable reason:** the negotiation succeeds
  (CLAIM/DEFER/spec exchanged correctly), but the deferring agent **edits the shared
  file anyway** — so 39% still hard-conflict and its high `both_passed` (58%) is a
  `solo_rescue` evaluation artifact, not a real merge. This is a textbook instance of
  the original paper's *commitment failure*, reproduced under a protocol designed to
  exploit commitment.
- **Talk-only and plan-only protocols sit at the floor** (13–21%), exactly as the
  flash failure analysis predicts: they add clarity to an information channel that
  was never the bottleneck, and plan at a (file) granularity the task structure makes
  useless.

---

## 4. The integrated conclusion

1. On conflict-selected pairs, two-agent failure is **overwhelmingly spatial**: two
   working patches colliding on the same lines (F1–F2), despite complete and accurate
   information exchange (F3), because agents agree about overlap without resolving it
   (F4) under a wrong model of how their work combines (F5).
2. Protocols that add **structure to communication** (semi_structured) or **plan
   around** the overlap (plan_handshake) do not survive multiple-comparison
   correction — the failure mode they target is not the operative one.
3. The one protocol that **resolves the overlap itself** — co-authoring byte-identical
   text for shared constructs — lifts merge-clean from 13% to 78% (OR 27.7,
   p < 0.0001) and uniquely produces identical merges.
4. **Everything in (3) is achieved through the system prompt alone.** No model change,
   no fine-tuning, no scaffold change, no shared workspace: the intervention is
   instructions plus message-field validation. This is direct evidence for the thesis
   claim that prompt-level protocol design is sufficient for substantial coordination
   improvement.
5. The residual: coauthor still fails 17% textually and 10% functionally — the
   functional residue is where semantic coordination (the original paper's dominant
   mode) finally becomes visible once the spatial problem is solved.

---

### Provenance

- Flash failure modes: `results_csv/flash_msg_1.csv`, `logs/flash_msg_1/` (patches,
  `eval.json` merge diffs, `conversation.json`), gold patches under `dataset/`.
  Per-pair classification table: Track A script output (15/15/15 counts above).
- Arm protocol definitions: `logs/nano_<arm>_1/config.json` (`message_schema`),
  prompt templates in `src/cooperbench/agents/_coop/prompt.py`.
- RCT numbers: pre-registered analysis (`docs/nano_py_preregistration.md`,
  `scripts/nano/analyze_study.py`); full tables at git `9b6bbc6c:docs/nano_protocol_study_results.md`.
