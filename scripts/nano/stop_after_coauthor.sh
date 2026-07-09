#!/usr/bin/env bash
# Watcher: cap the study at 5 reps each. Let batch 2 (nano_coauthor --repeats 5)
# finish naturally, then stop the driver before it launches batch 3 (nano_dc_b2)
# or batch 4 (nano_coauthor_b2).
#
# Safe because: the driver prints "BATCH DONE name=nano_coauthor" only AFTER the
# batch-2 cooperbench process has already exited, so killing the driver at that
# point cannot cascade-SIGPIPE an in-flight run. As a belt-and-braces guard we
# also trip if a nano_dc_b2 process ever appears.
set -uo pipefail
LOG=/home/oscar/CooperBench/logs/benchmark_5555.log
DRIVER_RE='benchmark_resume.sh'

while true; do
  # Trip condition A: batch 2 reported done by the driver.
  if grep -q "BATCH DONE name=nano_coauthor " "$LOG" 2>/dev/null; then
    reason="batch2 (coauthor) DONE"; break
  fi
  # Trip condition B: batch 3 (dc_b2) somehow already spawned.
  if pgrep -f "cooperbench run .* -n nano_dc_b2" >/dev/null 2>&1; then
    reason="nano_dc_b2 spawned"; break
  fi
  sleep 3
done

# Kill any batch-3/4 cooperbench that may have just started, then the driver.
pkill -f "cooperbench run .* -n nano_dc_b2"       2>/dev/null || true
pkill -f "cooperbench run .* -n nano_coauthor_b2" 2>/dev/null || true
pkill -f "$DRIVER_RE"                             2>/dev/null || true
echo "############ CAPPED AT 5 REPS EACH ($reason) $(date) ############" >> "$LOG"
