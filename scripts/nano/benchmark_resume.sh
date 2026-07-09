#!/usr/bin/env bash
# RESUME after the 2026-07-08 host reboot killed benchmark_5555.sh mid-batch-2.
# Batch 1 (nano_dc, designated_coder, 5 reps, 98 evals, both_passed 62%) is COMPLETE
# on disk and is NOT re-run. This resumes from batch 2 onward:
#   batch 2  nano_coauthor      coauthor_overlap  reps 1-5  -> balanced n=5 head-to-head here
#   batch 3  nano_dc_b2         designated_coder  reps 6-10
#   batch 4  nano_coauthor_b2   coauthor_overlap  reps 6-10 -> n=10 each
#
# The 4-pair partial nano_coauthor_1 from the interrupted run is removed first so the
# fresh coauthor batch's _1 dir starts clean.
#
# no-git, -c 2, eval-concurrency 2. Run in tmux session `benchmark`.
set -uo pipefail
cd /home/oscar/CooperBench
export PYTHONUNBUFFERED=1
export COOPERBENCH_REGISTRY=akhatua
LOG=/home/oscar/CooperBench/logs/benchmark_5555.log
COMMON="--setting coop -a claude_code -m claude-sonnet-5 --subset nano -c 2 --eval-concurrency 2 --repeats 5"

rm -rf /home/oscar/CooperBench/logs/nano_coauthor_1   # drop the interrupted partial

run() {  # $1 = schema file, $2 = run name
  echo "=== BATCH START name=$2 schema=$1 $(date) ===" | tee -a "$LOG"
  uv run cooperbench run $COMMON --structured-messaging "$1" -n "$2" 2>&1 | tee -a "$LOG"
  echo "=== BATCH DONE name=$2 rc=${PIPESTATUS[0]} $(date) ===" | tee -a "$LOG"
}

echo "############ BENCHMARK RESUME (from batch 2) START $(date) ############" | tee -a "$LOG"
run schemas/coauthor_overlap.toml  nano_coauthor       # batch 2: ca reps 1-5  -> balanced n=5
run schemas/designated_coder.toml  nano_dc_b2          # batch 3: dc reps 6-10
run schemas/coauthor_overlap.toml  nano_coauthor_b2    # batch 4: ca reps 6-10 -> n=10 each
echo "############ BENCHMARK RESUME ALL DONE $(date) ############" | tee -a "$LOG"
