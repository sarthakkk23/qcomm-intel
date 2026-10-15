"""Collect Google Trends search interest for the four brands in India.

One request compares all four brands, so their values share one 0-100 scale:
- daily interest, last 30 days -> data/raw/trends/<fetch_date>.csv (shared raw schema)
- 30-day share of search by state -> data/raw/trends_states/<fetch_date>.csv
"""
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pytrends.request import TrendReq

# Brand -> search term. A term matches any query containing it,
# so "Instamart" also counts searches for "swiggy instamart".
TERMS = {
    "Blinkit": "Blinkit",
    "Zepto": "Zepto",
    "Swiggy Instamart": "Instamart",
    "Flipkart Minutes": "Flipkart Minutes",
}

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 60    # Google Trends 429s need long waits
DEADLINE_SECONDS = 120  # hard cap per attempt: covers IPv6 stalls and slow responses
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def _deadline_hit(signum, frame):
    raise TimeoutError(f"no answer within {DEADLINE_SECONDS}s")


signal.signal(signal.SIGALRM, _deadline_hit)


def fetch_trends():
    """Return (daily, states) DataFrames from one comparison request, or None on failure."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        signal.alarm(DEADLINE_SECONDS)
        try:
            # Never pass retries= to TrendReq: pytrends' retry code breaks on urllib3 2.x.
            client = TrendReq(hl="en-US", tz=-330, timeout=(10, 30))
            client.build_payload(list(TERMS.values()), geo="IN", timeframe="today 1-m")
            daily = client.interest_over_time()
            states = client.interest_by_region()
            return daily, states
        except Exception as exc:
            print(f"  trends attempt {attempt} failed: {exc!r}", file=sys.stderr)
        finally:
            signal.alarm(0)
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)
    return None


def write(df, folder, fetch_date):
    out_dir = RAW_DIR / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{fetch_date}.csv"
    df.to_csv(out, index=False)
    print(f"trends: wrote {len(df)} rows to {out}")


def main():
    fetch_date = datetime.now(timezone.utc).date().isoformat()
    result = fetch_trends()
    if result is None or result[0].empty:
        print("trends: GAP, no data today", file=sys.stderr)
        sys.exit(1)
    daily, states = result
    brand_of = {term: brand for brand, term in TERMS.items()}

    daily = daily[~daily["isPartial"]].drop(columns="isPartial")
    daily = daily.reset_index().melt(id_vars="date", var_name="term", value_name="value")
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    daily["brand"] = daily["term"].map(brand_of)
    daily = daily.assign(fetch_date=fetch_date, source="google_trends", metric="search_interest")
    write(daily[["fetch_date", "date", "brand", "source", "metric", "value"]], "trends", fetch_date)

    states = states.reset_index().melt(id_vars="geoName", var_name="term", value_name="value")
    states = states.rename(columns={"geoName": "state"})
    states["brand"] = states["term"].map(brand_of)
    states = states.assign(fetch_date=fetch_date, metric="search_share_30d")
    write(states[["fetch_date", "state", "brand", "metric", "value"]], "trends_states", fetch_date)


if __name__ == "__main__":
    main()