#!/usr/bin/env bash
# quotron price collection — one tick over every jpow data source.
# Scrapes GPU retail/rental (and Claude-30 when Shoal is up), commits the
# outputs once and pushes. History is the whole point of a tracker, so this
# running on a schedule is what makes the docs/*.json series worth anything.
set -uo pipefail
export PATH="/home/hunter/.local/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO="$HOME/Desktop/code/jpow"

cd "$REPO" || { echo "no jpow repo at $REPO"; exit 1; }

# Land on top of whatever was pushed elsewhere; a diverged branch would only
# fail at push time and strand the tick's commit.
git pull -q --rebase --autostash 2>/dev/null || echo "pull failed, collecting anyway"

exec ./quotron/collect.sh
