"""Collect daily attention signals per brand.

- Wikipedia pageviews (Wikimedia REST API): last 30 days, for brands with an article.
- Play Store rating and rating/review counts (google-play-scraper): today's snapshot.

Writes data/raw/attention/<fetch_date>.csv in the shared raw schema:
fetch_date, date, brand, source, metric, value
"""
import signal
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from google_play_scraper import app


socket.setdefaulttimeout(30)  # google-play-scraper has no timeout of its own and can hang forever

PLAY_DEADLINE_SECONDS = 60  # hard cap per app: covers IPv6 stalls and multi-address retry loops


def _deadline_hit(signum, frame):
    raise TimeoutError(f"no answer within {PLAY_DEADLINE_SECONDS}s")


signal.signal(signal.SIGALRM, _deadline_hit)

HEADERS = {"User-Agent": "qcomm-intel/0.1 (+https://github.com/sarthakkk23/qcomm-intel)"}
WIKI_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{article}/daily/{start}/{end}"
)

# Brand -> English Wikipedia article. Instamart and Flipkart Minutes have none (see README).
WIKI_ARTICLES = {
    "Blinkit": "Blinkit",
    "Zepto": "Zepto_(company)",
}

# Brand -> standalone Play Store package name.
PLAY_APPS = {
    "Blinkit": "com.grofers.customerapp",
    "Zepto": "com.zeptoconsumerapp",
    "Swiggy Instamart": "in.swiggy.android.instamart",
    "Flipkart Minutes": "com.flipkart.minutes.android",
}

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "attention"


def fetch_wiki(article, today):
    """Return [(date, views), ...] for the 30 days before today, or None on failure."""
    start = (today - timedelta(days=30)).strftime("%Y%m%d")
    end = (today - timedelta(days=1)).strftime("%Y%m%d")
    url = WIKI_URL.format(article=article, start=start, end=end)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        items = resp.json()["items"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"  wiki {article} failed: {exc!r}", file=sys.stderr)
        return None
    return [
        (datetime.strptime(i["timestamp"], "%Y%m%d%H").date().isoformat(), i["views"])
        for i in items
    ]


def fetch_play(package):
    """Return today's {metric: value} snapshot for one app, or None on failure."""
    signal.alarm(PLAY_DEADLINE_SECONDS)
    try:
        a = app(package, lang="en", country="in")
    except Exception as exc:  # library errors, timeouts and parse failures all mean "no data today"
        print(f"  play {package} failed: {exc!r}", file=sys.stderr)
        return None
    finally:
        signal.alarm(0)
    return {
        "play_rating": a["score"],
        "play_ratings_count": a["ratings"],
        "play_reviews_count": a["reviews"],
    }


def main():
    today = datetime.now(timezone.utc).date()
    fetch_date = today.isoformat()
    rows, gaps = [], []

    for brand, article in WIKI_ARTICLES.items():
        points = fetch_wiki(article, today)
        if points is None:
            gaps.append(f"{brand}/wiki_pageviews")
            continue
        for day, views in points:
            rows.append({"fetch_date": fetch_date, "date": day, "brand": brand,
                         "source": "wikipedia", "metric": "wiki_pageviews", "value": views})

    for brand, package in PLAY_APPS.items():
        snapshot = fetch_play(package)
        if snapshot is None:
            gaps.append(f"{brand}/play_store")
            continue
        for metric, value in snapshot.items():
            rows.append({"fetch_date": fetch_date, "date": fetch_date, "brand": brand,
                         "source": "play_store", "metric": metric, "value": value})

    if rows:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{fetch_date}.csv"
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"attention: wrote {len(rows)} rows to {out}")
    if gaps:
        print(f"attention: GAPS for {', '.join(gaps)}", file=sys.stderr)
    sys.exit(0 if rows else 1)


if __name__ == "__main__":
    main()