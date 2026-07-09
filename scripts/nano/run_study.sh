#!/usr/bin/env bash
# Runner for the nano messaging-vs-no-messaging study.
#
# Runs, at the proven-safe concurrency 2, a range of replicate indices. For each
# index i it runs the no-messaging CONTROL then the MESSAGING arm, so if it's
# stopped early the two arms stay balanced. Repeats land in distinct log dirs
# (nano_control_<i> / nano_msg_<i>) that analyze.py picks up by prefix, so you
# can extend across several sessions toward k=20.
#
# Usage — run it DIRECTLY in your terminal to watch the live progress bars
# (exactly like a single `cooperbench run`); each of the 2*(END-START+1) runs
# renders in turn:
#
#   bash scripts/nano/run_study.sh 1 5      # ~9-10 h, k=5 each arm, live output
#   bash scripts/nano/run_study.sh 6 10     # next batch, toward k=20
#
# Ctrl-C stops it; closing the terminal stops it. To keep it running after you
# disconnect while still watching live, start it inside tmux/screen:
#   tmux new -s study 'bash scripts/nano/run_study.sh 1 5'   # detach: Ctrl-b d
#
# Full k=20 = repeats 1..20 (~37 h total across sessions).

set -u
START="${1:?usage: run_study.sh START END}"
END="${2:?usage: run_study.sh START END}"

MODEL="claude-sonnet-5"
AGENT="claude_code"
CONC=2            # proven safe: >=4 oversubscribes 12 cores during build/test bursts
SUBSET="nano"

cd "$(dirname "$0")/../.." || exit 1

run() {  # name  extra-flags...
  local name="$1"; shift
  echo "=== [$(date '+%F %T')] $name ==="
  uv run cooperbench run -n "$name" --subset "$SUBSET" --setting coop \
    -a "$AGENT" -m "$MODEL" -c "$CONC" "$@" \
    || echo "!! $name exited non-zero (continuing)"
}

echo "### nano study: repeats $START..$END at -c $CONC, model $MODEL"
for i in $(seq "$START" "$END"); do
  run "nano_control_${i}" --no-messaging   # baseline: no messaging
  run "nano_msg_${i}"                       # protocol: messaging on
  echo "--- [$(date '+%F %T')] repeat $i complete ---"
done
echo "### DONE repeats $START..$END"