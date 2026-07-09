#!/usr/bin/env bash
# Make the full CooperBench task-image set available locally as linux/amd64.
#
# Reads manifest.tsv and, per task:
#   action=pull  -> docker pull --platform linux/amd64 <tag>     (amd64 exists on Docker Hub)
#   action=build -> docker build --platform linux/amd64 -t <tag> dataset/<repo>/<task>/
#                   (Docker Hub copy is arm64-only; rebuild natively from the local Dockerfile)
#
# Every image is tagged with the exact name the Docker backend resolves
# (akhatua/cooperbench-<slug>:task<id>), so `cooperbench run --backend docker`
# uses the local amd64 image and never re-pulls the arm64 one.
#
# Usage:
#   ./sync_local_dataset.sh                 # all 30, 6-way parallel
#   ./sync_local_dataset.sh -j 8            # set parallelism
#   ./sync_local_dataset.sh --only build    # only the 14 rebuilds
#   ./sync_local_dataset.sh --only pull     # only the 16 pulls
#   ./sync_local_dataset.sh --save          # also `docker save` each to ./images/
#   ./sync_local_dataset.sh --dry-run       # print actions only
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
MANIFEST="$HERE/manifest.tsv"
LOGDIR="$HERE/logs"; IMGDIR="$HERE/images"; STATDIR="$LOGDIR/status"
ONLY="all"; SAVE=0; DRY=0; JOBS=6
while [[ $# -gt 0 ]]; do
  case "$1" in
    -j|--jobs) JOBS="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --save) SAVE=1; shift;;
    --dry-run) DRY=1; shift;;
    *) echo "unknown arg: $1"; exit 2;;
  esac
done

command -v docker >/dev/null || { echo "docker not found"; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker daemon not reachable as $(whoami)"; exit 1; }
[[ "$(uname -m)" == "x86_64" ]] || echo "WARN: host is $(uname -m), expected x86_64"
mkdir -p "$LOGDIR" "$STATDIR"; [[ $SAVE -eq 1 ]] && mkdir -p "$IMGDIR"
rm -f "$STATDIR"/*.status 2>/dev/null

process_one() {
  local reltask="$1" tag="$2" action="$3"
  local safe; safe="$(echo "$tag" | tr '/:' '__')"
  local lf="$LOGDIR/$safe.log" sf="$STATDIR/$safe.status"
  {
    echo ">> [$action] $tag"
    local ok=1
    if [[ "$action" == pull ]]; then
      docker pull --platform linux/amd64 "$tag" || ok=0
    else
      local ctx="$REPO_ROOT/dataset/$reltask"
      if [[ ! -f "$ctx/Dockerfile" ]]; then echo "no Dockerfile at $ctx"; echo "ERR $tag (no-dockerfile)" > "$sf"; return; fi
      docker build --platform linux/amd64 -t "$tag" "$ctx" || ok=0
    fi
    local arch; arch="$(docker image inspect "$tag" --format '{{.Os}}/{{.Architecture}}' 2>/dev/null)"
    if [[ $ok -eq 1 && "$arch" == "linux/amd64" ]]; then
      [[ $SAVE -eq 1 ]] && docker save -o "$IMGDIR/$safe.tar" "$tag"
      echo "OK $tag" > "$sf"
    else
      echo "ERR $tag (ok=$ok arch=$arch)" > "$sf"
    fi
  } > "$lf" 2>&1
}
export -f process_one
export REPO_ROOT LOGDIR IMGDIR STATDIR SAVE

# Build the work list (TSV: reltask \t tag \t action), heavy builds last.
mapfile -t LINES < <(
  awk -F'\t' -v only="$ONLY" '
    $0 ~ /^#/ || NF<6 {next}
    only!="all" && $5!=only {next}
    {print $1"\t"$3"\t"$5}' "$MANIFEST")

echo ">> ${#LINES[@]} task(s), ${ONLY} action, ${JOBS}-way parallel"
if [[ $DRY -eq 1 ]]; then printf '%s\n' "${LINES[@]}"; exit 0; fi

# Concurrency gate.
running=0
for line in "${LINES[@]}"; do
  IFS=$'\t' read -r reltask tag action <<< "$line"
  echo "   launch [$action] $tag"
  process_one "$reltask" "$tag" "$action" &
  running=$((running+1))
  if [[ $running -ge $JOBS ]]; then wait -n 2>/dev/null || wait; running=$((running-1)); fi
done
wait

echo; echo "==================== SUMMARY ===================="
ok=$(grep -lh '^OK ' "$STATDIR"/*.status 2>/dev/null | wc -l)
err=$(grep -Lh '^OK ' "$STATDIR"/*.status 2>/dev/null | wc -l)
echo "succeeded: $ok"; grep -h '^OK '  "$STATDIR"/*.status 2>/dev/null | sed 's/^OK /   OK  /'
echo "failed:    $err"; grep -h '^ERR ' "$STATDIR"/*.status 2>/dev/null | sed 's/^ERR /   ERR /'
echo; echo "Local image inventory:"
docker image ls 'akhatua/cooperbench-*' --format '   {{.Repository}}:{{.Tag}}  {{.Size}}' 2>/dev/null | sort
[[ "$err" -gt 0 ]] && exit 1 || exit 0
