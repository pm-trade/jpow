#!/bin/bash
# Claude-30 automated data collection — tides-aware.
# Queries Shoal's /tides/status for the current interval,
# then loops at that cadence. Market hours = fast, overnight = slow.
#
# Usage:
#   ./collect.sh       # runs forever, adjusts interval via tides
#   ./collect.sh once   # single run

set -euo pipefail
cd "$(dirname "$0")/../.."

SHOAL_URL="${SHOAL_URL:-http://localhost:8180}"
DEFAULT_INTERVAL=600  # 10 minutes fallback

scrape_once() {
    # Check Shoal is up
    if ! curl -s "$SHOAL_URL/health" > /dev/null 2>&1; then
        echo "[$(date +%H:%M)] shoal down, starting school-minnow..."
        cd ../shoal && make school-minnow COUNT=5 > /dev/null 2>&1
        cd ../jpow
        sleep 3
    fi

    # Scrape quotes (fast, reliable) — full scrape on the hour
    minute=$(date +%M)
    if [ "$minute" = "00" ] || [ "$minute" = "30" ]; then
        timeout 60 python3 quotron/claude30/scraper.py --all --export docs/data.json 2>&1 | \
            grep -E "(quotes in|index:|headlines|trending|error)" || true
    else
        timeout 30 python3 quotron/claude30/scraper.py --quotes --export docs/data.json 2>&1 | \
            grep -E "(index:|error)" || true
    fi

    # Push if changed
    if ! git diff --quiet docs/data.json docs/history.json 2>/dev/null; then
        git add docs/data.json docs/history.json
        git commit -m "data $(date +%H:%M) | $(python3 -c "
import json
d=json.load(open('docs/data.json'))
idx=d.get('index_summary',{})
print(f'idx={idx.get(\"value\",1000):.1f} q={len(d[\"quotes\"])}/30')
")" > /dev/null
        git push > /dev/null 2>&1
        echo "[$(date +%H:%M)] pushed"
    else
        echo "[$(date +%H:%M)] no changes"
    fi
}

get_interval() {
    # Query tides for current scrape interval (in seconds)
    interval=$(curl -s "$SHOAL_URL/tides/status" 2>/dev/null | \
        python3 -c "import sys,json; print(int(json.load(sys.stdin).get('interval',0)/1e9))" 2>/dev/null)

    if [ -z "$interval" ] || [ "$interval" -lt 30 ] 2>/dev/null; then
        echo "$DEFAULT_INTERVAL"
    else
        echo "$interval"
    fi
}

# Single run mode
if [ "${1:-}" = "once" ]; then
    scrape_once
    exit 0
fi

# Continuous mode — interval adjusts with the tides
echo "[$(date +%H:%M)] collector starting (tides-aware)"
while true; do
    scrape_once
    interval=$(get_interval)
    echo "[$(date +%H:%M)] next in ${interval}s ($(curl -s "$SHOAL_URL/tides/status" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('phase','?'))" 2>/dev/null) tide)"
    sleep "$interval"
done
