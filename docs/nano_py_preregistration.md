# nano-py — pre-registration

Fixed **before** looking at any result. Purpose: a sensitive, unconfounded,
low-cost instrument for measuring whether a multi-agent **communication
protocol** improves conflict resolution — for developing the method, not for
cross-language generalization.

## Design

- **Single language: Python.** Removes the language×repo×difficulty confound; the
  only language with enough repos/tasks to scale independent clusters. (Cross-
  language generalization is a later phase, run only on a winning protocol.)
- **Unit of analysis:** the *task* (a repo at one base commit). One conflicting
  pair per task → independent clusters, domain-diverse across the 9 Python repos.
- **Set:** 20 pairs, one per task, ≤3 per repo (`dataset/subsets/nano_py.json`).

## Selection (free, offline — no runs)

From the 415 Python gold-conflict pairs, each pair is scored by **static feature
overlap** (shared files + intersecting hunk ranges in the two `feature.patch`es)
— a proxy for conflict severity. The highest-overlap pair per task is taken; the
20 highest-overlap tasks are kept (≤3/repo). Deterministic, reproducible
(`scripts/nano/select_pairs.py`). This is a **pre-filter to raise hit-rate**, not
the validity check.

## Validity check (free, post-hoc — from the control arm)

No separate calibration phase. Validity is judged from the study's own
no-messaging control at k=20. **Pre-registered exclusion** (`analyze.py`):
- **Capability floor:** drop a pair if neither feature passes in >10% of control
  runs (the model can't build the features → not a coordination problem).
- **No conflict bite:** drop a pair if the control's `both_passed` rate >60%
  (the naive merge already works → nothing to coordinate).
Survivors (~15–18 expected) are the validated set. We **never** select or exclude
on a with-messaging protocol outcome (that is the dependent variable).

## Measurement plan

- **k = 20** replicate runs per pair per condition (turns each pair's pass/fail
  into a rate out of 20; ±~11pp per pair). "Run the dataset 20 times" = 20 pairs
  × 20 = 400 pair-runs per condition.
- **Conditions:** a **no-messaging control** (run once, reused across protocols)
  and each **protocol** arm. Capability is read from per-feature `passed` in the
  control — no separate `solo` runs.
- **Primary endpoint:** merge-clean rate (coordination-specific).
  **Secondary:** `both_passed`.
- **Analysis (fixed):** per-pair rates + Wilson 95% CIs → pooled
  **Cochran–Mantel–Haenszel** stratified by pair (respects clustering; no
  pseudoreplication). Report the funnel: submitted → applied → merge-clean →
  both. **No flat test treating N runs as independent.**
- **Inference scope:** conditional on these Python pairs. No per-repo/per-domain
  claims (one pair per task).

## Reproducibility

Model pinned per run, seed=42 for selection, subset + scripts committed. Infra
failures (patch-apply errors, container crashes; `error` set in `eval.json`) are
flagged and excluded from rate denominators, not counted as task failures.

## Pipeline

1. `scripts/nano/select_pairs.py` → `dataset/subsets/nano_py.json` (offline).
2. Run control + protocol arms at k=20 (20 invocations each, distinct `-n` names).
3. `scripts/nano/analyze.py --control <prefix> --protocol <prefix>` → exclusion +
   per-pair CIs + CMH + funnel.
