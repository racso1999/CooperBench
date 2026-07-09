#!/usr/bin/env bash
# Phase 1: coordination-gap baseline on the flash subset (50 pairs).
#   solo  = 1 agent does both features
#   coop  = 2 agents, one feature each, messaging ON (default), no --git
# Same model/agent/dataset; only --setting differs. Sequential to avoid
# oversubscribing RAM (coop spawns 2 containers/task).
set -uo pipefail
cd /home/oscar/CooperBench
LOG=scripts/local_images/logs
M="-a claude_code -m claude-sonnet-4-6 -s flash -c 8"

echo "######## $(date) SOLO ########"
uv run cooperbench run -n flash-solo $M --setting solo --force > "$LOG/phase1_solo.log" 2>&1
echo "solo exit=$? at $(date)"

echo "######## $(date) COOP (messaging on) ########"
uv run cooperbench run -n flash-coop $M --setting coop --force > "$LOG/phase1_coop.log" 2>&1
echo "coop exit=$? at $(date)"

echo "######## DONE $(date) ########"
