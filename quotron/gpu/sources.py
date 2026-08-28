"""
Price sources. Plain stdlib HTTP, no third-party deps.

Three sources survive bare requests:
  vast.ai  — per-offer marketplace; carries min_bid, the interruptible
             auction floor. The cheapest honest number in GPU compute.
  RunPod   — one GraphQL call prices every GPU type at three tiers.
  Newegg   — embeds its whole product list as JSON in window.__initialState__,
             so retail needs no HTML scraping.

eBay (used-market comps) is deliberately absent: it 403s bare curl on TLS
fingerprint alone. It needs a TLS-impersonating client or an API key, and it
the one source worth adding when either exists.
"""

import json
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

VAST_URL = "https://console.vast.ai/api/v0/search/asks/"
RUNPOD_URL = "https://api.runpod.io/graphql"
NEWEGG_URL = "https://www.newegg.com/p/pl?d="

TIMEOUT = 30


class SourceError(Exception):
    pass


# --- HTTP ---

def _request(url, data=None, method=None, headers=None):
    hdrs = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        raise SourceError(f"{url}: {e}") from e


def _get_json(url, data=None, method=None):
    raw = _request(url, data=data, method=method)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SourceError(f"{url}: bad JSON ({e})") from e


# --- vast.ai (marketplace: on-demand asks + interruptible bid floor) ---

def vast_offers(gpu_name: str) -> dict:
    """
    Price one GPU model across the vast.ai marketplace.

    Rates are normalized per-GPU: a listing is often an 8-GPU box, and
    dph_total prices the whole box. Dividing by num_gpus is what makes
    an 8x H100 node comparable to a single 5090.
    """
    q = {"q": {"gpu_name": {"eq": gpu_name}, "rentable": {"eq": True}, "limit": 500}}
    offers = _get_json(VAST_URL, data=q, method="PUT").get("offers", [])
    if not offers:
        return {}

    ondemand, bids, locations = [], [], []
    for o in offers:
        n = max(o.get("num_gpus") or 1, 1)
        dph = o.get("dph_total")
        if dph:
            ondemand.append(dph / n)
            locations.append(o.get("geolocation") or "?")
        bid = o.get("min_bid")
        if bid:
            bids.append(bid / n)

    if not ondemand:
        return {}

    cheapest = min(range(len(ondemand)), key=lambda i: ondemand[i])
    return {
        "offers": len(offers),
        "ondemand_min": round(min(ondemand), 4),
        "ondemand_median": round(statistics.median(ondemand), 4),
        "bid_min": round(min(bids), 4) if bids else None,
        "bid_median": round(statistics.median(bids), 4) if bids else None,
        "cheapest_location": locations[cheapest],
        "total_gpus": sum(max(o.get("num_gpus") or 1, 1) for o in offers),
    }


# --- RunPod (one call prices every type) ---

RUNPOD_QUERY = """{
  gpuTypes {
    id displayName memoryInGb securePrice communityPrice
    lowestPrice(input: {gpuCount: 1}) { minimumBidPrice uninterruptablePrice }
  }
}"""


def runpod_prices() -> dict:
    """Map RunPod gpuType id -> its three price tiers."""
    data = _get_json(RUNPOD_URL, data={"query": RUNPOD_QUERY})
    if "errors" in data:
        raise SourceError(f"runpod: {data['errors'][0].get('message')}")

    out = {}
    for g in data.get("data", {}).get("gpuTypes", []):
        lp = g.get("lowestPrice") or {}
        # RunPod reports 0 for "tier unavailable"; None is the honest value.
        secure = g.get("securePrice") or None
        community = g.get("communityPrice") or None
        out[g["id"]] = {
            "secure": secure,
            "community": community,
            "bid": lp.get("minimumBidPrice"),
            "vram": g.get("memoryInGb"),
        }
    return out


# --- Newegg (retail, from the embedded state blob) ---

# Parts that carry a GPU's name but are not the GPU: waterblocks, brackets,
# and whole prebuilt systems whose price is the machine, not the card.
_NOT_A_CARD = re.compile(
    r"\b(cable|bracket|riser|stand|holder|adapter|water ?block|backplate|"
    r"cooler|shroud|sticker|screw|mount|extender|barebone|heatsink|"
    r"thermal pad|anti-?sag|alphacool|ekwb|bykski|hydro x|"
    r"gaming pc|gaming desktop|gaming computer|desktop pc|prebuilt|"
    r"laptop|notebook)\b", re.I)


def _is_card(title: str, match: list | None, exclude: list | None) -> bool:
    """A title is the card only if it names it and isn't an accessory or system."""
    low = title.lower()
    if _NOT_A_CARD.search(low):
        return False
    if match and not all(tok.lower() in low for tok in match):
        return False
    if exclude and any(tok.lower() in low for tok in exclude):
        return False
    return True


def newegg_listings(query: str, match: list | None = None,
                    exclude: list | None = None, limit: int = 60) -> list[dict]:
    """
    Retail listings for a search phrase.

    Newegg ships the result set as JSON in window.__initialState__, so we
    brace-match that object instead of parsing markup that changes monthly.
    """
    html = _request(NEWEGG_URL + urllib.parse.quote_plus(query))

    anchor = html.find('"Products":[')
    if anchor == -1:
        raise SourceError(f"newegg({query}): no product payload")

    # Walk back to the enclosing object, then let the JSON decoder find its end.
    depth, start = 0, None
    for i in range(anchor, 0, -1):
        if html[i] == "}":
            depth += 1
        elif html[i] == "{":
            if depth == 0:
                start = i
                break
            depth -= 1
    if start is None:
        raise SourceError(f"newegg({query}): unbalanced payload")

    try:
        obj, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError as e:
        raise SourceError(f"newegg({query}): {e}") from e

    listings = []
    for p in obj.get("Products", [])[:limit]:
        cell = p.get("ItemCell") or {}
        price = cell.get("FinalPrice") or cell.get("UnitCost")
        title = (cell.get("Description") or {}).get("Title") or ""
        if not price or not title or not _is_card(title, match, exclude):
            continue
        seller = cell.get("Seller") or {}
        listings.append({
            "title": title.strip(),
            "price": round(float(price), 2),
            "in_stock": bool(cell.get("Instock")),
            "sku": cell.get("Item"),
            "seller": seller.get("SellerName") if isinstance(seller, dict) else None,
            "low_30d": cell.get("LowestPrice30Days") or None,
        })
    return listings


def newegg_summary(query: str, match: list | None = None, exclude: list | None = None,
                   msrp: float | None = None) -> dict:
    """
    Collapse listings into the numbers a buyer actually reads.

    The MSRP floor is a last backstop: anything under a quarter of sticker
    is an accessory that slipped the title filter, not a bargain.
    """
    listings = newegg_listings(query, match, exclude)
    if msrp:
        listings = [l for l in listings if l["price"] >= msrp * 0.25]
    live = [l for l in listings if l["in_stock"]]
    pool = live or listings
    if not pool:
        return {}

    prices = sorted(l["price"] for l in pool)
    cheapest = min(pool, key=lambda l: l["price"])
    return {
        "listings": len(listings),
        "in_stock": len(live),
        "retail_min": prices[0],
        "retail_median": round(statistics.median(prices), 2),
        "cheapest_title": cheapest["title"][:80],
        "cheapest_sku": cheapest["sku"],
    }
