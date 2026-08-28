#!/bin/bash
# quotron collector — runs every source, commits once.
#
# Per-source collect.sh scripts each did their own add/commit/push, which
# races the index and fights over the remote when two run at once. This is
# the scheduled entry point: scrape everything, stage the outputs, one commit.
#
# A source that fails is reported and skipped, never fatal — a dead upstream
# shouldn't cost us the sources that did work.
#
# Usage:
#   ./collect.sh          # one pass
#   ./collect.sh --loop   # forever, every INTERVAL seconds

set -uo pipefail
cd "$(dirname "$0")/.."

INTERVAL="${INTERVAL:-3600}"

# source | output | scraper args
SOURCES=(
    "gpu|docs/gpu.json|--all"
)

log() { echo "[$(date +%H:%M)] $*"; }

scrape_all() {
    local ok=() failed=()

    for entry in "${SOURCES[@]}"; do
        IFS='|' read -r name out args <<< "$entry"

        if timeout 300 python3 "quotron/$name/scraper.py" $args --export "$out" >/dev/null 2>&1; then
            ok+=("$name")
        else
            failed+=("$name")
        fi
    done

    log "scraped: ${ok[*]:-none}${failed:+ | failed: ${failed[*]}}"
    [ ${#ok[@]} -gt 0 ]
}

commit_all() {
    # Stage only our outputs — never -A, the working tree isn't ours to sweep.
    git add docs/*.json 2>/dev/null

    if git diff --cached --quiet 2>/dev/null; then
        log "no price changes"
        git reset -q 2>/dev/null
        return 0
    fi

    git commit -q -m "quotron $(date +%H:%M) | $(python3 - <<'PY'
import json, os
bits = []
try:
    g = json.load(open("docs/gpu.json"))["gpus"]
    if g.get("H100 SXM", {}).get("bid"):
        bits.append(f"h100bid=${g['H100 SXM']['bid']:.3f}")
    if g.get("RTX 5090", {}).get("retail"):
        bits.append(f"5090=${g['RTX 5090']['retail']:,.0f}")
except Exception:
    pass
try:
    d = json.load(open("docs/data.json"))
    idx = d.get("index_summary", {}).get("value")
    if idx:
        bits.append(f"idx={idx:.1f}")
except Exception:
    pass
print(" ".join(bits) or "data")
PY
)"
    # A failed push just means the next tick carries both commits.
    if git push -q 2>/dev/null; then
        log "pushed"
    else
        log "commit held (push failed)"
    fi
}

run_once() {
    scrape_all
    commit_all
}

if [ "${1:-}" = "--loop" ]; then
    log "quotron collector starting (every ${INTERVAL}s)"
    while true; do
        run_once
        sleep "$INTERVAL"
    done
else
    run_once
fi
