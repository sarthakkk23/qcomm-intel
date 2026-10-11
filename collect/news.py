"""Collect daily news volume and tone per brand from the GDELT DOC 2.0 API.

Writes data/raw/news/<fetch_date>.csv in the shared raw schema:
fetch_date, date, brand, source, metric, value
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
HEADERS = {"User-Agent": "qcomm-intel/0.1 (+https://github.com/sarthakkk23/qcomm-intel)"}

# Display name -> GDELT query. Multi-word names need quotes to match as a phrase.
BRANDS = {
    "Blinkit": "Blinkit",
    "Zepto": "Zepto",
    "Swiggy Instamart": '"Swiggy Instamart"',
    "Flipkart Minutes": '"Flipkart Minutes"',
}

PAUSE_SECONDS = 30  # GDELT's limiter is stricter than its stated 5s; space calls widely
MAX_ATTEMPTS = 3    # gaps self-heal: tomorrow's 30-day fetch re-covers today's dates
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "news"


def fetch_timeline(query, mode):
    """Return GDELT's timeline data points, or None if every attempt fails."""
    params = {"query": query, "mode": mode, "format": "json", "timespan": "30d"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            if resp.status_code == 200 and resp.text.lstrip().startswith("{"):
                timeline = resp.json().get("timeline", [])
                return timeline[0]["data"] if timeline else []
            reason = f"HTTP {resp.status_code}: {resp.text[:80]!r}"
        except requests.RequestException as exc:
            reason = repr(exc)
        wait = PAUSE_SECONDS * 2 ** (attempt - 1)
        print(f"  {mode} attempt {attempt} failed ({reason}); waiting {wait}s", file=sys.stderr)
        time.sleep(wait)
    return None


def to_rows(points, brand, metric, fetch_date):
    """Convert GDELT points to rows in the shared raw schema."""
    rows = []
    for p in points:
        day = datetime.strptime(p["date"], "%Y%m%dT%H%M%SZ").date().isoformat()
        base = {"fetch_date": fetch_date, "date": day, "brand": brand, "source": "gdelt"}
        rows.append({**base, "metric": metric, "value": p["value"]})
        if "norm" in p:  # volume mode also reports GDELT's total articles that day
            rows.append({**base, "metric": "gdelt_total_articles", "value": p["norm"]})
    return rows


def main():
    fetch_date = datetime.now(timezone.utc).date().isoformat()
    only = sys.argv[1:]  # optional brand names, e.g. python collect/news.py Blinkit
    calls = [("timelinevolraw", "article_count"), ("timelinetone", "avg_tone")]
    rows, gaps = [], []

    for brand, query in BRANDS.items():
        if only and brand not in only:
            continue
        for mode, metric in calls:
            points = fetch_timeline(query, mode)
            if points is None:
                gaps.append(f"{brand}/{metric}")
            else:
                rows += to_rows(points, brand, metric, fetch_date)
            time.sleep(PAUSE_SECONDS)

    if rows:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{fetch_date}.csv"
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"news: wrote {len(rows)} rows to {out}")
    if gaps:
        print(f"news: GAPS for {', '.join(gaps)}", file=sys.stderr)
    sys.exit(0 if rows else 1)


if __name__ == "__main__":
    main()