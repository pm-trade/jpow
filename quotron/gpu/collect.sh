#!/bin/bash
# GPU price collection. Hourly by default — retail and rental move on
# hours-to-days, so scraping faster just commits noise.
#
# Usage:
#   ./collect.sh          # loop forever at INTERVAL
#   ./collect.sh once     # single run
#   INTERVAL=1800 ./collect.sh

set -euo pipefail
cd "$(dirname "$0")/../.."

INTERVAL="${INTERVAL:-3600}"

scrape_once() {
    timeout 180 python3 quotron/gpu/scraper.py --all --export docs/gpu.json 2>&1 \
        | grep -E "(models priced|history:|error|exported)" || true

    # Stage first: git diff can't see a file that isn't tracked yet, so the
    # very first run would otherwise look unchanged and never commit.
    git add docs/gpu.json docs/gpu-history.json 2>/dev/null || true
    if ! git diff --cached --quiet docs/gpu.json docs/gpu-history.json 2>/dev/null; then
        git commit -q -m "gpu $(date +%H:%M) | $(python3 -c "
import json
d = json.load(open('docs/gpu.json'))
g = d['gpus']
h100 = g.get('H100 SXM', {}).get('bid')
c5090 = g.get('RTX 5090', {}).get('retail')
parts = []
if h100: parts.append(f'h100bid=\${h100:.3f}')
if c5090: parts.append(f'5090=\${c5090:,.0f}')
print(' '.join(parts) or 'no prices')
")"
        git push -q 2>/dev/null || echo "[$(date +%H:%M)] push failed"
        echo "[$(date +%H:%M)] pushed"
    else
        echo "[$(date +%H:%M)] no changes"
    fi
}

if [ "${1:-}" = "once" ]; then
    scrape_once
    exit 0
fi

echo "[$(date +%H:%M)] gpu collector starting (every ${INTERVAL}s)"
while true; do
    scrape_once
    sleep "$INTERVAL"
done
