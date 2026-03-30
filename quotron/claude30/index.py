"""
The Claude-30 Index — 30 stocks representing the AI infrastructure stack.

Selection criteria:
- Companies whose revenue or strategic direction is materially tied to AI
- Balanced across the AI value chain: chips → memory → cloud → software → infra
- Mix of mega-cap anchors and high-growth mid-caps
- Weighted by AI revenue exposure, not just market cap

The index tracks the companies building, powering, and deploying AI.

Rebalance history:
- v1 (2026-03-29): Initial composition
- v2 (2026-03-30): Added MU (HBM memory), CRWV (GPU cloud), ALAB (interconnect).
  Removed BBAI, RGTI, SOUN (speculative, not core infra). Trimmed ORCL, INTC.
"""

# --- Index Constituents ---

CLAUDE_30 = {
    # GPU & Silicon (the bedrock)
    "NVDA":  {"name": "NVIDIA",           "sector": "silicon",    "weight": 12.0},
    "AMD":   {"name": "AMD",              "sector": "silicon",    "weight": 4.0},
    "AVGO":  {"name": "Broadcom",         "sector": "silicon",    "weight": 5.0},
    "MRVL":  {"name": "Marvell",          "sector": "silicon",    "weight": 2.0},
    "MU":    {"name": "Micron",           "sector": "silicon",    "weight": 2.0},
    "INTC":  {"name": "Intel",            "sector": "silicon",    "weight": 1.0},

    # Cloud & Compute (the ocean)
    "AMZN":  {"name": "Amazon",           "sector": "cloud",      "weight": 8.0},
    "MSFT":  {"name": "Microsoft",        "sector": "cloud",      "weight": 8.0},
    "GOOG":  {"name": "Alphabet",         "sector": "cloud",      "weight": 7.0},
    "META":  {"name": "Meta",             "sector": "cloud",      "weight": 5.0},
    "ORCL":  {"name": "Oracle",           "sector": "cloud",      "weight": 2.0},
    "CRWV":  {"name": "CoreWeave",        "sector": "cloud",      "weight": 1.5},

    # AI Software & Data (the current)
    "CRM":   {"name": "Salesforce",       "sector": "software",   "weight": 3.0},
    "PLTR":  {"name": "Palantir",         "sector": "software",   "weight": 3.0},
    "SNOW":  {"name": "Snowflake",        "sector": "software",   "weight": 2.0},
    "MDB":   {"name": "MongoDB",          "sector": "software",   "weight": 1.5},
    "DDOG":  {"name": "Datadog",          "sector": "software",   "weight": 1.5},

    # Infrastructure & Interconnect (the hull)
    "NET":   {"name": "Cloudflare",       "sector": "infra",      "weight": 2.5},
    "ANET":  {"name": "Arista Networks",  "sector": "infra",      "weight": 2.5},
    "CRWD":  {"name": "CrowdStrike",      "sector": "infra",      "weight": 2.5},
    "SMCI":  {"name": "Super Micro",      "sector": "infra",      "weight": 2.0},
    "ALAB":  {"name": "Astera Labs",      "sector": "infra",      "weight": 1.5},
    "FTNT":  {"name": "Fortinet",         "sector": "infra",      "weight": 1.0},

    # Hardware & Systems (the dock)
    "TSLA":  {"name": "Tesla",            "sector": "hardware",   "weight": 4.0},
    "DELL":  {"name": "Dell",             "sector": "hardware",   "weight": 2.0},
    "ISRG":  {"name": "Intuitive Surgical","sector": "hardware",  "weight": 2.0},
    "HPE":   {"name": "HPE",              "sector": "hardware",   "weight": 1.0},

    # Emerging AI (the fry)
    "PATH":  {"name": "UiPath",           "sector": "emerging",   "weight": 1.5},
    "RKLB":  {"name": "Rocket Lab",       "sector": "emerging",   "weight": 1.5},
    "IONQ":  {"name": "IonQ",             "sector": "emerging",   "weight": 1.0},
}

TICKERS = list(CLAUDE_30.keys())

SECTORS = {
    "silicon":  "GPU, Silicon & Memory",
    "cloud":    "Cloud & Compute",
    "software": "AI Software & Data",
    "infra":    "Infrastructure & Interconnect",
    "hardware": "Hardware & Systems",
    "emerging": "Emerging AI",
}

def by_sector():
    """Group tickers by sector."""
    groups = {}
    for ticker, info in CLAUDE_30.items():
        sector = info["sector"]
        if sector not in groups:
            groups[sector] = []
        groups[sector].append(ticker)
    return groups
