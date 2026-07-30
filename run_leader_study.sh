#!/usr/bin/env bash
# Leader-topology scaling study driver (overnight, autonomous).
#
# Runs the supervised arm over the same 14 pools / N levels / trial counts as
# the original flat study (results_topo/plan.json), into results_topo/.
#
# BREADTH-FIRST BY TRIAL: sweeps every pool at trial 1, then every pool at
# trial 2, and so on.  The completed dataset is identical to running each pool
# to full depth, but a *partial* run then covers all 14 pools at shallow depth
# rather than a few pools deeply — far more useful if the study is stopped
# early (the N-curve can be computed across the whole pool set).
#
# Runs are resumable: completed cells are skipped cheaply on re-scan, so this
# script is safe to kill and restart at any point.
#
# Usage:  tmux new-session -d -s overnight ./run_leader_study.sh
set -uo pipefail
cd /home/oscar/CooperBench

# The study images live in the upstream namespace, not the default racso1999.
export COOPERBENCH_REGISTRY=akhatua

# Long-lived Claude Code token (from `claude setup-token`), if present.  Agents
# get only an access token and cannot re-authenticate, so the short-lived
# ~/.claude/.credentials.json token makes every run 401 the moment it expires.
# Kept in a 0600 file so it never has to be pasted into a transcript.
if [ -f /home/oscar/CooperBench/.study_token ]; then
    # shellcheck disable=SC1091
    set -a; . /home/oscar/CooperBench/.study_token; set +a
    echo "using long-lived CLAUDE_CODE_OAUTH_TOKEN (${#CLAUDE_CODE_OAUTH_TOKEN} chars)"
fi

OUT=results_topo
LOGDIR=logs/leader_study
STATUS=$LOGDIR/status.txt
mkdir -p "$LOGDIR"

MAXTRIALS=$(uv run python -c "
import json; print(max(v['trials'] for v in json.load(open('$OUT/plan.json')).values()))")

# pool|K|trials, cheapest first (K=3 before K=4) so problems surface early.
POOLS=$(uv run python -c "
import json
plan=json.load(open('$OUT/plan.json'))
for pid,v in sorted(plan.items(), key=lambda kv:(kv[1]['K'], kv[0])):
    print(f\"{pid}|{v['K']}|{v['trials']}\")
")

echo "=== STUDY START $(date -Is)  max_trials=$MAXTRIALS" | tee -a "$STATUS"

for t in $(seq 1 "$MAXTRIALS"); do
    echo "=== TRIAL SWEEP $t/$MAXTRIALS  $(date -Is)" | tee -a "$STATUS"
    i=0
    while IFS='|' read -r pid k trials; do
        [ -z "$pid" ] && continue
        i=$((i+1))
        # Skip pools whose planned depth is shallower than this trial.
        [ "$t" -gt "$trials" ] && continue
        slug=$(echo "$pid" | tr '/' '_')
        agents=$(seq -s, 1 "$k")
        echo "--- [t$t pool $i] $pid K=$k agents=$agents  $(date -Is)" | tee -a "$STATUS"
        uv run cooperbench scaling --leader \
            --manifest "$OUT/pools.json" \
            --pool "$pid" \
            --agents "$agents" \
            --trials "$t" \
            --out "$OUT" \
            >> "$LOGDIR/$slug.log" 2>&1
        rc=$?
        n=$(grep -c '"condition": "leader"' "$OUT/rows.jsonl" 2>/dev/null || echo 0)
        echo "--- [t$t pool $i] $pid rc=$rc leader_rows=$n  $(date -Is)" | tee -a "$STATUS"
        # Reap anything a crashed cell left behind before the next pool.
        docker ps -q --filter "name=minisweagent" | xargs -r docker kill >/dev/null 2>&1
        docker volume ls -q --filter "name=cb-team" | xargs -r docker volume rm >/dev/null 2>&1
    done <<< "$POOLS"
done

echo "=== STUDY COMPLETE $(date -Is)" | tee -a "$STATUS"
