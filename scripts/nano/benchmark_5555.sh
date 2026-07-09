#!/usr/bin/env bash
# 5/5/5/5 interleaved run of the two overlap-resolution protocols on full nano.
# Interleaved (dc5, ca5, dc5, ca5) so that after the FIRST two batches we already
# have a balanced n=5 comparison of both schemas — if it stops early we still have
# usable, symmetric data. Batches 3-4 top each arm up to n=10.
#
# no-git, -c 2, eval-concurrency 2. Runs in tmux session `benchmark`.
set -uo pipefail
cd /home/oscar/CooperBench
export PYTHONUNBUFFERED=1
export COOPERBENCH_REGISTRY=akhatua
LOG=/home/oscar/CooperBench/logs/benchmark_5555.log
COMMON="--setting coop -a claude_code -m claude-sonnet-5 --subset nano -c 2 --eval-concurrency 2 --repeats 5"

run() {  # $1 = schema file, $2 = run name
  echo "=== BATCH START name=$2 schema=$1 $(date) ===" | tee -a "$LOG"
  uv run cooperbench run $COMMON --structured-messaging "$1" -n "$2" 2>&1 | tee -a "$LOG"
  echo "=== BATCH DONE name=$2 rc=${PIPESTATUS[0]} $(date) ===" | tee -a "$LOG"
}

echo "############ BENCHMARK 5/5/5/5 START $(date) ############" | tee -a "$LOG"
run schemas/designated_coder.toml  nano_dc          # batch 1: dc  reps 1-5
run schemas/coauthor_overlap.toml  nano_coauthor    # batch 2: ca  reps 1-5   -> balanced n=5 here
run schemas/designated_coder.toml  nano_dc_b2       # batch 3: dc  reps 6-10
run schemas/coauthor_overlap.toml  nano_coauthor_b2 # batch 4: ca  reps 6-10  -> n=10 each
echo "############ BENCHMARK 5/5/5/5 ALL DONE $(date) ############" | tee -a "$LOG"
