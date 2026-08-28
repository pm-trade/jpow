"""
The tracked GPU universe — what we price on both sides of the market.

Two questions drive the catalog:
  buy  — what does this card cost right now, new, at retail?
  rent — what does an hour of it cost on the spot/auction market?

Consumer cards answer both, which is the whole point: a card you can buy
is also a card someone else is renting out, so retail / $-per-hour gives
a breakeven in hours. Datacenter parts are rent-only — you aren't buying
an H100 at retail, but its hourly rate is the AI-compute price signal.

Source keys map our name onto each provider's own spelling:
  vast    — gpu_name in the vast.ai offer search (exact match)
  runpod  — id in the RunPod gpuTypes GraphQL query (exact match)
  newegg  — search phrase; None means rent-only, skip retail

Newegg search is fuzzy — asking for a scarce card happily returns a
different one — so `match` lists tokens a title MUST contain and
`exclude` lists tokens that disqualify it. Without these the cheapest
"RTX 3090" on the page is an RTX 5060.
"""

# --- Catalog ---

GPUS = {
    # Consumer — buyable and rentable, so breakeven is meaningful
    "RTX 5090": {
        "label": "GeForce RTX 5090", "tier": "consumer", "vram": 32, "msrp": 1999,
        "vast": "RTX 5090", "runpod": "NVIDIA GeForce RTX 5090",
        "newegg": "rtx 5090", "match": ["5090"],
    },
    "RTX 5080": {
        "label": "GeForce RTX 5080", "tier": "consumer", "vram": 16, "msrp": 999,
        "vast": "RTX 5080", "runpod": "NVIDIA GeForce RTX 5080",
        "newegg": "rtx 5080", "match": ["5080"],
    },
    "RTX 4090": {
        "label": "GeForce RTX 4090", "tier": "consumer", "vram": 24, "msrp": 1599,
        "vast": "RTX 4090", "runpod": "NVIDIA GeForce RTX 4090",
        "newegg": "rtx 4090", "match": ["4090"],
    },
    "RTX 3090": {
        "label": "GeForce RTX 3090", "tier": "consumer", "vram": 24, "msrp": 1499,
        "vast": "RTX 3090", "runpod": "NVIDIA GeForce RTX 3090",
        "newegg": "rtx 3090", "match": ["3090"], "exclude": ["3090 ti"],
    },

    # Workstation — sold at retail, but priced like datacenter silicon
    "RTX 6000 Ada": {
        "label": "RTX 6000 Ada", "tier": "workstation", "vram": 48, "msrp": 6800,
        "vast": "RTX 6000Ada", "runpod": "NVIDIA RTX 6000 Ada Generation",
        "newegg": "rtx 6000 ada", "match": ["6000", "ada"],
    },
    "L40S": {
        "label": "L40S", "tier": "workstation", "vram": 48, "msrp": 9000,
        "vast": "L40S", "runpod": "NVIDIA L40S",
        "newegg": "nvidia l40s", "match": ["l40s"],
    },

    # Datacenter — rent-only; these are the AI compute price signal
    "H100 SXM": {
        "label": "H100 SXM 80GB", "tier": "datacenter", "vram": 80, "msrp": None,
        "vast": "H100 SXM", "runpod": "NVIDIA H100 80GB HBM3", "newegg": None,
    },
    "H100 NVL": {
        "label": "H100 NVL 94GB", "tier": "datacenter", "vram": 94, "msrp": None,
        "vast": "H100 NVL", "runpod": "NVIDIA H100 NVL", "newegg": None,
    },
    "H200": {
        "label": "H200 141GB", "tier": "datacenter", "vram": 141, "msrp": None,
        "vast": "H200", "runpod": "NVIDIA H200", "newegg": None,
    },
    "B200": {
        "label": "B200 180GB", "tier": "datacenter", "vram": 180, "msrp": None,
        "vast": "B200", "runpod": "NVIDIA B200", "newegg": None,
    },
    "A100 SXM": {
        "label": "A100 SXM4 80GB", "tier": "datacenter", "vram": 80, "msrp": None,
        "vast": "A100 SXM4", "runpod": "NVIDIA A100-SXM4-80GB", "newegg": None,
    },
    "A100 PCIe": {
        "label": "A100 PCIe 80GB", "tier": "datacenter", "vram": 80, "msrp": None,
        "vast": "A100 PCIE", "runpod": "NVIDIA A100 80GB PCIe", "newegg": None,
    },
}

MODELS = list(GPUS.keys())

TIERS = {
    "consumer":    "Consumer (buy or rent)",
    "workstation": "Workstation",
    "datacenter":  "Datacenter (rent only)",
}


def by_tier():
    """Group model keys by tier."""
    groups = {}
    for model, info in GPUS.items():
        groups.setdefault(info["tier"], []).append(model)
    return groups


def buyable():
    """Models we track a retail price for."""
    return [m for m, i in GPUS.items() if i.get("newegg")]
