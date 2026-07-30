#!/usr/bin/env bash
# Overnight watchdog for the leader study — fully autonomous.
#
# An earlier version used `pgrep -f run_leader_study.sh`, which matches ANY process whose
# command line merely mentions the script (e.g. a status check).  That both
# masked real deaths and risked spurious restarts.  This version inspects /proc argv
# directly and requires argv[0]=bash, argv[1]=*run_leader_study.sh — an exact
# match that no shell one-liner can accidentally satisfy.
#
# Responsibilities:
#   1. keep the OAuth token fresh (agents cannot re-authenticate themselves)
#   2. keep disk from filling (eval sandboxes accumulate)
#   3. restart the driver whenever it dies, until the study reports COMPLETE
#   4. heartbeat so progress is auditable without interrogating the driver
set -uo pipefail
cd /home/oscar/CooperBench

LOG=logs/leader_study/watchdog.log
STATUS=logs/leader_study/status.txt
mkdir -p logs/leader_study
log() { echo "[watchdog $(date -Is)] $*" >> "$LOG"; }

driver_alive() {
    python3 - <<'PY'
import os, sys
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        argv = [a for a in open(f'/proc/{pid}/cmdline','rb').read().split(b'\0') if a]
    except OSError:
        continue
    if len(argv) >= 2 and os.path.basename(argv[0].decode(errors='replace')) in ('bash','sh') \
       and argv[1].decode(errors='replace').endswith('run_leader_study.sh'):
        sys.exit(0)
sys.exit(1)
PY
}

log "watchdog started"
cycle=0
while true; do
    cycle=$((cycle+1))

    # --- 1. token keepalive (long-lived token makes this a no-op) --------
    if [ ! -f .study_token ]; then
        exp=$(python3 -c "
import json
try: print(int(json.load(open('/home/oscar/.claude/.credentials.json'))['claudeAiOauth']['expiresAt']))
except Exception: print(0)" 2>/dev/null)
        now_ms=$(date +%s000)
        if [ "${exp:-0}" -gt 0 ] && [ $(( (exp - now_ms) / 60000 )) -lt 45 ]; then
            log "oauth expiring soon — forcing refresh"
            timeout 120 claude -p "ok" >/dev/null 2>&1
        fi
    fi

    # --- 2. disk guard ---------------------------------------------------
    free_g=$(df -BG --output=avail /home/oscar | tail -1 | tr -dc '0-9')
    if [ "${free_g:-999}" -lt 25 ]; then
        log "disk low (${free_g}G) — pruning stopped containers"
        docker container prune -f >> "$LOG" 2>&1
    fi

    # --- 3. finished? ----------------------------------------------------
    if grep -q "STUDY COMPLETE" "$STATUS" 2>/dev/null; then
        rows=$(grep -c '"condition": "leader"' results_topo/rows.jsonl 2>/dev/null || echo '?')
        log "STUDY COMPLETE (${rows} leader rows) — watchdog exiting"
        exit 0
    fi

    # --- 4. driver alive? ------------------------------------------------
    if ! driver_alive; then
        log "driver DOWN — reaping orphans and restarting"
        docker ps -q --filter "name=minisweagent" | xargs -r docker kill >/dev/null 2>&1
        docker volume ls -q --filter "name=cb-team" | xargs -r docker volume rm >/dev/null 2>&1
        setsid nohup ./run_leader_study.sh >> logs/leader_study/driver.log 2>&1 < /dev/null &
        sleep 10
        if driver_alive; then log "driver restarted OK"; else log "ERROR restart failed"; fi
    fi

    # --- 5. heartbeat every ~20 min --------------------------------------
    if [ $((cycle % 10)) -eq 0 ]; then
        rows=$(grep -c '"condition": "leader"' results_topo/rows.jsonl 2>/dev/null || echo '?')
        log "heartbeat: ${rows}/148 leader rows, $(df -BG --output=avail /home/oscar | tail -1 | tr -d ' ') free"
    fi

    sleep 120
done
