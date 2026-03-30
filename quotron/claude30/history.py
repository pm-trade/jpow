"""
Claude-30 Index historical tracking.

Maintains a rolling history of index values and per-stock prices.
Appends to docs/history.json on each scrape, capped at 7 days of
10-minute intervals (~1000 data points).

The index value is a weighted composite:
  index = sum(price_i / base_price_i * weight_i) * (1000 / total_weight)

Normalized to 1000 at inception (first data point = base prices).
"""

import json
import os
from datetime import datetime
from index import CLAUDE_30

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "history.json")
MAX_POINTS = 1008  # 7 days * 24 hours * 6 per hour (10-min intervals)


def load_history() -> dict:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return {"base_prices": {}, "points": []}


def save_history(history: dict):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f)


def record(quotes: list[dict]):
    """Append a data point from the latest scrape."""
    history = load_history()

    # Build price map from quotes
    prices = {}
    for q in quotes:
        if q.get("price", 0) > 0:
            prices[q["ticker"]] = q["price"]

    if not prices:
        return

    # Set base prices on first run
    if not history["base_prices"]:
        history["base_prices"] = dict(prices)

    # Calculate weighted index value
    total_weight = sum(info["weight"] for info in CLAUDE_30.values())
    index_value = 0
    contributors = 0

    for ticker, info in CLAUDE_30.items():
        price = prices.get(ticker)
        base = history["base_prices"].get(ticker)
        if price and base and base > 0:
            index_value += (price / base) * info["weight"]
            contributors += 1

    if contributors > 0:
        index_value = index_value * (1000 / total_weight)
    else:
        index_value = 1000

    # Build data point
    point = {
        "t": datetime.now().isoformat(),
        "index": round(index_value, 2),
        "prices": {t: round(p, 2) for t, p in prices.items()},
    }

    history["points"].append(point)

    # Cap history length
    if len(history["points"]) > MAX_POINTS:
        history["points"] = history["points"][-MAX_POINTS:]

    save_history(history)

    return index_value


def get_summary() -> dict:
    """Get current index stats for display."""
    history = load_history()
    points = history.get("points", [])

    if not points:
        return {"value": 1000, "change": 0, "change_pct": 0, "points": 0}

    current = points[-1]["index"]
    first = points[0]["index"]
    change = current - first
    change_pct = (change / first * 100) if first else 0

    # Find min/max
    values = [p["index"] for p in points]

    return {
        "value": current,
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "high": max(values),
        "low": min(values),
        "points": len(points),
        "since": points[0]["t"],
    }
