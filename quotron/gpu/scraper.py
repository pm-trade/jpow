"""
GPU price scraper — both sides of the market in one pass.

Buy side  : Newegg retail, versus MSRP, so you can see the scalp premium.
Rent side : vast.ai and RunPod, on-demand and interruptible bid floors.

The join between them is the number this exists to compute: breakeven
hours = retail / cheapest hourly rate. Buying only wins if you'd keep the
card busy longer than that.

Usage:
    python quotron/gpu/scraper.py [--cloud] [--retail] [--all] [--export docs/gpu.json]
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from catalog import GPUS, MODELS, TIERS, by_tier
from history import record as record_history, get_summary
from sources import SourceError, newegg_summary, runpod_prices, vast_offers


# --- Collection ---

def collect_cloud() -> dict:
    """Rental prices per model, vast.ai offers plus RunPod tiers."""
    out = {m: {} for m in MODELS}

    try:
        runpod = runpod_prices()
    except SourceError as e:
        print(f"  runpod error: {e}")
        runpod = {}

    def fetch(model):
        try:
            return model, vast_offers(GPUS[model]["vast"])
        except SourceError as e:
            print(f"  vast error ({model}): {e}")
            return model, {}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, m) for m in MODELS]
        for f in as_completed(futures):
            model, vast = f.result()
            out[model]["vast"] = vast
            rp = runpod.get(GPUS[model]["runpod"] or "", {})
            out[model]["runpod"] = rp

    return out


def collect_retail() -> dict:
    """Retail listings per buyable model."""
    out = {}

    def fetch(model):
        try:
            info = GPUS[model]
            return model, newegg_summary(info["newegg"], info.get("match"),
                                         info.get("exclude"), info.get("msrp"))
        except SourceError as e:
            print(f"  newegg error ({model}): {e}")
            return model, {}

    targets = [m for m in MODELS if GPUS[m].get("newegg")]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch, m) for m in targets]
        for f in as_completed(futures):
            model, summary = f.result()
            if summary:
                out[model] = summary

    return out


# --- Merge & derive ---

def merge(cloud: dict, retail: dict) -> dict:
    """
    Fold every source into one record per model, then derive the
    buy-versus-rent numbers that the raw feeds don't carry.
    """
    merged = {}

    for model in MODELS:
        info = GPUS[model]
        vast = (cloud.get(model) or {}).get("vast") or {}
        rp = (cloud.get(model) or {}).get("runpod") or {}
        shop = retail.get(model) or {}

        # Cheapest honest rate at each tier, across providers.
        rents = [v for v in (vast.get("ondemand_min"), rp.get("community"), rp.get("secure")) if v]
        bids = [v for v in (vast.get("bid_min"), rp.get("bid")) if v]

        rec = {
            "model": model,
            "label": info["label"],
            "tier": info["tier"],
            "vram": info["vram"],
            "msrp": info["msrp"],
            "rent": min(rents) if rents else None,
            "bid": min(bids) if bids else None,
            "retail": shop.get("retail_min"),
            "retail_median": shop.get("retail_median"),
            "in_stock": shop.get("in_stock", 0),
            "cheapest_listing": shop.get("cheapest_title"),
            "vast": vast,
            "runpod": rp,
        }

        # Scalp premium: what retail asks over the sticker nobody honors.
        if rec["retail"] and info["msrp"]:
            rec["premium_pct"] = round((rec["retail"] - info["msrp"]) / info["msrp"] * 100, 1)

        # Breakeven: hours of use before buying beats renting. Bid rate is
        # the fair comparison for batch work you can checkpoint and resume.
        if rec["retail"]:
            if rec["rent"]:
                rec["breakeven_hours"] = round(rec["retail"] / rec["rent"])
                rec["breakeven_days"] = round(rec["retail"] / rec["rent"] / 24, 1)
            if rec["bid"]:
                rec["breakeven_hours_bid"] = round(rec["retail"] / rec["bid"])

        # Spread between on-demand and the auction floor — how much patience pays.
        if rec["rent"] and rec["bid"]:
            rec["bid_discount_pct"] = round((rec["rent"] - rec["bid"]) / rec["rent"] * 100, 1)

        merged[model] = rec

    return merged


# --- Display ---

def print_cloud(merged: dict):
    print(f"  {'model':16s} {'vram':>5s} {'on-dem':>9s} {'bid':>9s} {'disc':>6s} {'offers':>7s}  cheapest at")
    print(f"  {'-'*16} {'-'*5} {'-'*9} {'-'*9} {'-'*6} {'-'*7}  {'-'*20}")
    for tier, models in by_tier().items():
        for m in models:
            r = merged[m]
            if not r["rent"]:
                continue
            bid = f"${r['bid']:.3f}" if r["bid"] else "-"
            disc = f"{r['bid_discount_pct']:.0f}%" if r.get("bid_discount_pct") else "-"
            loc = (r["vast"].get("cheapest_location") or "-")[:20]
            n = r["vast"].get("offers", 0)
            print(f"  {r['label'][:16]:16s} {r['vram']:>4d}G ${r['rent']:>8.3f} {bid:>9s} {disc:>6s} {n:>7d}  {loc}")


def print_retail(merged: dict):
    print(f"  {'model':16s} {'msrp':>7s} {'cheapest':>10s} {'median':>10s} {'premium':>8s} {'stock':>6s}")
    print(f"  {'-'*16} {'-'*7} {'-'*10} {'-'*10} {'-'*8} {'-'*6}")
    for m in MODELS:
        r = merged[m]
        if not r["retail"]:
            continue
        msrp = f"${r['msrp']:,}" if r["msrp"] else "-"
        prem = f"{r['premium_pct']:+.0f}%" if r.get("premium_pct") is not None else "-"
        med = f"${r['retail_median']:,.0f}" if r.get("retail_median") else "-"
        print(f"  {r['label'][:16]:16s} {msrp:>7s} ${r['retail']:>9,.0f} {med:>10s} {prem:>8s} {r['in_stock']:>6d}")


def print_breakeven(merged: dict):
    """The buy-or-rent verdict, which is the point of tracking both."""
    rows = [r for r in merged.values() if r.get("breakeven_hours")]
    if not rows:
        print("  no overlap between retail and rental this run")
        return
    print(f"  {'model':16s} {'buy':>9s} {'rent/hr':>9s} {'breakeven':>12s} {'at bid rate':>13s}")
    print(f"  {'-'*16} {'-'*9} {'-'*9} {'-'*12} {'-'*13}")
    for r in sorted(rows, key=lambda x: x["breakeven_hours"]):
        beb = f"{r['breakeven_hours_bid']:,}h" if r.get("breakeven_hours_bid") else "-"
        print(f"  {r['label'][:16]:16s} ${r['retail']:>8,.0f} ${r['rent']:>8.3f} "
              f"{r['breakeven_hours']:>10,}h {beb:>13s}")
        print(f"  {'':16s} {'':>9s} {'':>9s} {r['breakeven_days']:>10,.0f}d")


# --- Export ---

def export_json(merged: dict, outpath: str):
    data = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "catalog": {m: GPUS[m] for m in MODELS},
        "tiers": TIERS,
        "gpus": merged,
        "history_summary": get_summary(),
    }
    os.makedirs(os.path.dirname(os.path.abspath(outpath)), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  exported to {outpath}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="GPU price tracker — buy and rent")
    parser.add_argument("--cloud", action="store_true", help="rental prices only")
    parser.add_argument("--retail", action="store_true", help="retail prices only")
    parser.add_argument("--all", action="store_true", help="both sides (default)")
    parser.add_argument("--export", default="", help="write JSON here for the dashboard")
    parser.add_argument("--no-history", action="store_true", help="skip appending to history")
    args = parser.parse_args()

    if not (args.cloud or args.retail):
        args.all = True

    print("=" * 74)
    print("  GPU PRICE TRACKER")
    print("=" * 74)
    print(f"  tracking {len(MODELS)} models across {len(TIERS)} tiers")

    cloud, retail = {}, {}

    if args.cloud or args.all:
        print(f"\n--- Rental (vast.ai marketplace + RunPod) ---\n")
        t0 = time.perf_counter()
        cloud = collect_cloud()
        merged_preview = merge(cloud, {})
        print_cloud(merged_preview)
        print(f"\n  {sum(1 for r in merged_preview.values() if r['rent'])}/{len(MODELS)} "
              f"models priced in {time.perf_counter() - t0:.1f}s")

    if args.retail or args.all:
        print(f"\n--- Retail (Newegg) ---\n")
        t0 = time.perf_counter()
        retail = collect_retail()
        print_retail(merge({}, retail))
        print(f"\n  {len(retail)} models priced in {time.perf_counter() - t0:.1f}s")

    merged = merge(cloud, retail)

    if args.all:
        print(f"\n--- Buy vs Rent ---\n")
        print_breakeven(merged)

    if not args.no_history:
        n = record_history(merged)
        print(f"\n  history: {n} points")

    if args.export:
        export_json(merged, args.export)

    print(f"\n{'=' * 74}")


if __name__ == "__main__":
    main()
