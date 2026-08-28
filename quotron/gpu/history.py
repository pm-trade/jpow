"""
Rolling GPU price history.

Appends one point per scrape to docs/gpu-history.json. GPU prices move on
hours-to-days, not seconds, so the window is long: 180 days at hourly
cadence. Each point keeps the three numbers that matter per model —
on-demand rent, auction bid floor, retail — and nothing else, so the file
stays small enough to commit on every run.
"""

import json
import os
from datetime import datetime

from catalog import GPUS

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "gpu-history.json")
MAX_POINTS = 4320  # 180 days at hourly cadence


def load_history() -> dict:
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH) as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"points": []}


def save_history(history: dict):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, separators=(",", ":"))


def record(snapshot: dict) -> int:
    """Append one point. `snapshot` is model -> merged price record."""
    history = load_history()

    models = {}
    for model, rec in snapshot.items():
        slim = {}
        for key in ("rent", "bid", "retail"):
            if rec.get(key) is not None:
                slim[key] = rec[key]
        if slim:
            models[model] = slim

    if not models:
        return len(history["points"])

    history["points"].append({"t": datetime.now().isoformat(timespec="seconds"), "models": models})
    if len(history["points"]) > MAX_POINTS:
        history["points"] = history["points"][-MAX_POINTS:]

    save_history(history)
    return len(history["points"])


def get_summary() -> dict:
    """Per-model move since the first recorded point, for the dashboard."""
    points = load_history().get("points", [])
    if not points:
        return {"points": 0, "models": {}}

    out = {}
    for model in GPUS:
        series = [(p["t"], p["models"][model]) for p in points if model in p.get("models", {})]
        if not series:
            continue
        first, last = series[0][1], series[-1][1]
        entry = {}
        for key in ("rent", "bid", "retail"):
            now, then = last.get(key), first.get(key)
            if now is None:
                continue
            entry[key] = now
            if then:
                entry[f"{key}_change_pct"] = round((now - then) / then * 100, 2)
            vals = [s[1][key] for s in series if s[1].get(key)]
            if vals:
                entry[f"{key}_low"] = min(vals)
                entry[f"{key}_high"] = max(vals)
        entry["observations"] = len(series)
        out[model] = entry

    return {"points": len(points), "since": points[0]["t"], "models": out}
