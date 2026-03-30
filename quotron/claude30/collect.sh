#!/bin/bash
# Claude-30 automated data collection — runs independently of Claude.
# Scrapes all sources, updates dashboard, pushes to GitHub.
#
# Usage:
#   ./collect.sh              # single run
#   watch -n 600 ./collect.sh # every 10 minutes

set -euo pipefail
cd "$(dirname "$0")/../.."

# Check Shoal is up
if ! curl -s localhost:8180/health > /dev/null 2>&1; then
    echo "[$(date +%H:%M)] shoal not running, starting school-minnow..."
    cd ../shoal && make school-minnow COUNT=5 > /dev/null 2>&1
    cd ../jpow
    sleep 3
fi

# Scrape
python3 quotron/claude30/scraper.py --all --export docs/data.json 2>&1 | \
    grep -E "(quotes in|index:|headlines|posts for|trending|error)" || true

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
