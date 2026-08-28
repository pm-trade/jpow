# quotron
your data, here

Services that collect, normalize and distribute public data.

## Sources

| source | collects | output | needs |
|---|---|---|---|
| `gpu` | GPU retail and rental prices, buy-vs-rent breakeven | `docs/gpu.json`, `docs/gpu-history.json` | nothing |

Each source is a directory with a `scraper.py` that takes `--export <path>`
and writes one JSON file. Sources own their catalog and their history; they
do not share code, and there is no framework to conform to — two of them is
not yet a pattern worth abstracting.

Git is the database. Every tick commits the outputs, so `docs/*.json` on
GitHub Pages is the distribution layer and the commit log is the archive.

## Collecting

`quotron/collect.sh` is the entry point. It runs every source, then makes a
single commit for all of them — per-source scripts each doing their own
add/commit/push raced the index and fought over the remote. A source that
fails is reported and skipped, never fatal, so a dead upstream doesn't cost
us the sources that did work.

```sh
./quotron/collect.sh            # one pass
./quotron/collect.sh --loop     # forever, INTERVAL=3600 by default
```

## Scheduling

Hourly via a systemd user timer. A tracker with no scheduler is just a
checker — the history series is the reason any of this exists.

```sh
cp bin/jpow-collect.sh ~/.local/bin/
cp systemd/jpow-collect.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jpow-collect.timer
```

`Persistent=true` — the box powers off nightly on purpose, so the timer
catches up on the next boot rather than leaving a hole in the series.

```sh
systemctl --user list-timers jpow-collect.timer
journalctl --user -u jpow-collect.service -n 20
```
