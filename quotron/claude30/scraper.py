"""
Claude-30 Index data scraper — uses Shoal for browser orchestration.

Three data tiers, three scraping strategies:

1. QUOTES (Yahoo Finance API) — lightweight JSON, tls-client minnow
2. NEWS (Google News) — HTML scraping, Lightpanda or minnow
3. SOCIAL (Reddit) — JSON API, tls-client minnow

Usage:
    # Start Shoal cluster first
    make run-cf  # from shoal/ directory

    # Run scraper
    python quotron/claude30/scraper.py [--quotes] [--news] [--social] [--all]
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

# Add shoal client to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shoal", "clients", "python"))
from shoal import Shoal, ShoalError

from index import CLAUDE_30, TICKERS, SECTORS, by_sector


SHOAL_URL = os.environ.get("SHOAL_URL", "http://localhost:8180")


# --- Data Types ---

@dataclass
class Quote:
    ticker: str
    price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    market_cap: float = 0.0
    timestamp: str = ""

@dataclass
class Headline:
    ticker: str
    title: str = ""
    source: str = ""
    url: str = ""
    timestamp: str = ""

@dataclass
class SocialPost:
    ticker: str
    title: str = ""
    score: int = 0
    comments: int = 0
    subreddit: str = ""
    url: str = ""


# --- Quote Scraper (Yahoo Finance API — minnow tier) ---

def scrape_quotes(s: Shoal, tickers: list[str]) -> list[Quote]:
    """
    Fetch quotes from Yahoo Finance v8 chart API (public, no auth).
    One request per ticker — lightweight JSON, perfect for minnows.
    """
    quotes = []

    def fetch_quote(ticker: str) -> Quote | None:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        try:
            resp = s.fetch(url, consumer="claude30-quotes", agent_class="light")
            data = resp.json()
            result = data["chart"]["result"][0]
            meta = result["meta"]

            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("previousClose", price)
            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            volume = meta.get("regularMarketVolume", 0)

            return Quote(
                ticker=ticker,
                price=price,
                change=change,
                change_pct=change_pct,
                volume=volume,
                market_cap=0,  # not in chart API
                timestamp=datetime.now().isoformat(),
            )
        except (ShoalError, json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"  quote error ({ticker}): {e}")
            return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_quote, t): t for t in tickers}
        for f in as_completed(futures):
            q = f.result()
            if q:
                quotes.append(q)

    return quotes


# --- News Scraper (Google News RSS — minnow tier) ---

def scrape_news(s: Shoal, tickers: list[str], max_per_ticker: int = 3) -> list[Headline]:
    """
    Fetch news from Google News RSS feeds.
    RSS is XML/HTML — lightweight enough for minnows.
    """
    headlines = []

    def fetch_ticker_news(ticker):
        company = CLAUDE_30[ticker]["name"]
        query = f"{company} stock"
        url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"

        try:
            resp = s.fetch(url, consumer="claude30-news", agent_class="light")
            # Parse RSS XML
            items = []
            html = resp.html
            while "<item>" in html and len(items) < max_per_ticker:
                start = html.find("<item>")
                end = html.find("</item>", start) + len("</item>")
                item_xml = html[start:end]
                html = html[end:]

                title = extract_xml_tag(item_xml, "title")
                source = extract_xml_tag(item_xml, "source")
                link = extract_xml_tag(item_xml, "link")
                pub_date = extract_xml_tag(item_xml, "pubDate")

                if title:
                    items.append(Headline(
                        ticker=ticker,
                        title=title,
                        source=source,
                        url=link,
                        timestamp=pub_date,
                    ))
            return items
        except ShoalError as e:
            print(f"  news error ({ticker}): {e}")
            return []

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_ticker_news, t): t for t in tickers}
        for f in as_completed(futures):
            headlines.extend(f.result())

    return headlines


# --- Social Scraper (Reddit JSON API — minnow tier) ---

def scrape_social(s: Shoal, tickers: list[str], max_per_ticker: int = 3) -> list[SocialPost]:
    """
    Fetch social posts from Reddit's public JSON API.
    Reddit's .json endpoints are lightweight — minnow tier.
    Some subreddits may rate-limit, but the API is generally open.
    """
    posts = []
    subreddits = ["wallstreetbets", "stocks", "investing"]

    def fetch_ticker_social(ticker):
        results = []
        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/search.json?q=${ticker}&sort=new&limit={max_per_ticker}&restrict_sr=on"

            try:
                resp = s.fetch(url, consumer="claude30-social", agent_class="light")
                data = resp.json()

                for post in data.get("data", {}).get("children", []):
                    d = post.get("data", {})
                    results.append(SocialPost(
                        ticker=ticker,
                        title=d.get("title", ""),
                        score=d.get("score", 0),
                        comments=d.get("num_comments", 0),
                        subreddit=sub,
                        url=f"https://reddit.com{d.get('permalink', '')}",
                    ))
            except (ShoalError, json.JSONDecodeError) as e:
                pass  # Reddit rate limits are noisy, skip silently

        return results[:max_per_ticker]

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch_ticker_social, t): t for t in tickers}
        for f in as_completed(futures):
            posts.extend(f.result())

    return posts


# --- Helpers ---

def extract_xml_tag(xml: str, tag: str) -> str:
    start = xml.find(f"<{tag}>")
    if start == -1:
        start = xml.find(f"<{tag} ")
    if start == -1:
        return ""
    start = xml.find(">", start) + 1
    end = xml.find(f"</{tag}>", start)
    if end == -1:
        return ""
    value = xml[start:end]
    # Strip CDATA
    if value.startswith("<![CDATA["):
        value = value[9:-3]
    return value.strip()


def print_quotes(quotes: list[Quote]):
    if not quotes:
        print("  no quotes")
        return
    for q in sorted(quotes, key=lambda x: CLAUDE_30.get(x.ticker, {}).get("weight", 0), reverse=True):
        direction = "+" if q.change >= 0 else ""
        mcap = f"${q.market_cap/1e9:.0f}B" if q.market_cap > 1e9 else f"${q.market_cap/1e6:.0f}M"
        vol = f"{q.volume/1e6:.1f}M" if q.volume > 1e6 else f"{q.volume/1e3:.0f}K"
        print(f"  {q.ticker:5s} ${q.price:>8.2f} {direction}{q.change_pct:>6.2f}% vol={vol:>7s} mcap={mcap:>7s}")


def print_news(headlines: list[Headline]):
    if not headlines:
        print("  no headlines")
        return
    for h in headlines[:15]:
        print(f"  {h.ticker:5s} [{h.source}] {h.title[:80]}")


def print_social(posts: list[SocialPost]):
    if not posts:
        print("  no posts")
        return
    for p in sorted(posts, key=lambda x: x.score, reverse=True)[:10]:
        print(f"  {p.ticker:5s} r/{p.subreddit:20s} score={p.score:>5d} comments={p.comments:>4d} | {p.title[:60]}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Claude-30 Index Scraper")
    parser.add_argument("--quotes", action="store_true", help="scrape stock quotes")
    parser.add_argument("--news", action="store_true", help="scrape news headlines")
    parser.add_argument("--social", action="store_true", help="scrape reddit social posts")
    parser.add_argument("--all", action="store_true", help="scrape everything")
    parser.add_argument("--shoal", default=SHOAL_URL, help="Shoal controller URL")
    args = parser.parse_args()

    if not any([args.quotes, args.news, args.social, args.all]):
        args.all = True

    print("=" * 60)
    print("  CLAUDE-30 INDEX SCRAPER")
    print("=" * 60)
    print(f"  shoal: {args.shoal}")
    print(f"  constituents: {len(TICKERS)} stocks across {len(SECTORS)} sectors")
    print()

    s = Shoal(args.shoal)

    try:
        pool = s.status()
        print(f"  pool: {pool.total} agents, {pool.available} available")
    except Exception as e:
        print(f"  ERROR: can't reach Shoal at {args.shoal}: {e}")
        print(f"  start with: cd shoal && make run-cf")
        return

    # --- Quotes ---
    if args.quotes or args.all:
        print(f"\n--- Quotes (Yahoo Finance API → minnow) ---\n")
        t0 = time.perf_counter()
        quotes = scrape_quotes(s, TICKERS)
        dt = time.perf_counter() - t0
        print_quotes(quotes)
        print(f"\n  {len(quotes)}/{len(TICKERS)} quotes in {dt:.1f}s")

    # --- News ---
    if args.news or args.all:
        print(f"\n--- News (Google News RSS → minnow) ---\n")
        t0 = time.perf_counter()
        # Just do top 10 by weight to keep it fast
        top_tickers = sorted(TICKERS, key=lambda t: CLAUDE_30[t]["weight"], reverse=True)[:10]
        headlines = scrape_news(s, top_tickers)
        dt = time.perf_counter() - t0
        print_news(headlines)
        print(f"\n  {len(headlines)} headlines for {len(top_tickers)} tickers in {dt:.1f}s")

    # --- Social ---
    if args.social or args.all:
        print(f"\n--- Social (Reddit JSON → minnow) ---\n")
        t0 = time.perf_counter()
        top_tickers = sorted(TICKERS, key=lambda t: CLAUDE_30[t]["weight"], reverse=True)[:10]
        posts = scrape_social(s, top_tickers)
        dt = time.perf_counter() - t0
        print_social(posts)
        print(f"\n  {len(posts)} posts for {len(top_tickers)} tickers in {dt:.1f}s")

    print(f"\n{'='*60}")
    print(f"  done")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
