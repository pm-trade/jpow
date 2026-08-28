# gpu

Tracks GPU prices on both sides of the market: what a card costs to **buy**,
and what an hour of one costs to **rent**.

The number this exists to produce is the join between them — breakeven hours,
`retail / $-per-hour`. Buying only wins if you'd keep the card busy longer
than that. At the time of writing an RTX 5090 is ~$4,900 retail and rents for
$0.32/hr on demand or $0.20/hr on the interruptible auction, so buying pays
back after roughly 15,000 hours of continuous use — about 1.7 years.

## Sources

| source | side | auth | notes |
|---|---|---|---|
| vast.ai | rent | none | per-offer marketplace; `min_bid` is the interruptible auction floor |
| RunPod | rent | none | one GraphQL call prices every type at secure / community / bid |
| Newegg | buy | none | ships its result set as JSON in `window.__initialState__` |

No pip installs — stdlib `urllib` only.

eBay used-market comps are deliberately missing: eBay 403s bare requests on
TLS fingerprint alone. It needs a TLS-impersonating client or an API key, and
it's the first source worth adding when either exists.

## Files

- `catalog.py` — the tracked models, with each provider's spelling of them
- `sources.py` — one adapter per source, all returning plain dicts
- `scraper.py` — collect, merge, derive breakeven, export `docs/gpu.json`
- `history.py` — append to `docs/gpu-history.json` (180 days, hourly)

Collection and committing live in `quotron/collect.sh`, which runs every
source and commits once. See `quotron/README.md` for scheduling.

## Usage

```sh
python3 quotron/gpu/scraper.py --all --export docs/gpu.json
python3 quotron/gpu/scraper.py --cloud        # rental only
python3 quotron/gpu/scraper.py --retail       # retail only

./quotron/collect.sh                          # all sources, one commit
```

## Gotchas

Newegg's search is fuzzy — asking for a scarce card returns a different one.
`catalog.py` carries `match`/`exclude` token lists per model, and without them
the cheapest "RTX 3090" on the page is an RTX 5060. Anything under 25% of MSRP
is dropped as an accessory. If you add a model, give it `match` tokens and
eyeball the first run.

vast.ai prices whole boxes: an 8×H100 node's `dph_total` is for all eight.
Rates are divided by `num_gpus` so a node is comparable to a single card.
