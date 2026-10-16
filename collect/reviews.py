"""Collect a daily complaint radar from recent Play Store reviews.

For each standalone app, take the newest REVIEW_SAMPLE English reviews and measure what share of them
are 1-2 star complaints mentioning each theme. Only aggregate percentages are stored: no review text,
user names or review IDs ever leave this script.

Writes data/raw/reviews/<fetch_date>.csv in the shared raw schema:
fetch_date, date, brand, source, metric, value
"""
import re
import signal
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google_play_scraper import Sort, reviews

socket.setdefaulttimeout(30)  # google-play-scraper has no timeout of its own and can hang forever

DEADLINE_SECONDS = 120  # hard cap per app: a 400-review fetch is several requests


def _deadline_hit(signum, frame):
    raise TimeoutError(f"no answer within {DEADLINE_SECONDS}s")


signal.signal(signal.SIGALRM, _deadline_hit)

# Brand -> standalone Play Store package name (same apps as attention.py).
APPS = {
    "Blinkit": "com.grofers.customerapp",
    "Zepto": "com.zeptoconsumerapp",
    "Swiggy Instamart": "in.swiggy.android.instamart",
    "Flipkart Minutes": "com.flipkart.minutes.android",
}

REVIEW_SAMPLE = 400  # newest reviews per app per day; Blinkit gets this many in a few hours, Minutes in ~2 weeks
LOW_STARS = 2        # 1-2 star reviews count as complaints; this stops praise like "support is excellent" counting

# Theme -> keywords (case-insensitive regular expressions), English plus common Hinglish.
# Tested on 1,600 recent reviews on 2026-10-16; see README for coverage and limits.
THEMES = {
    "late_delivery": r"\blate\b|\bdelay|\bwait(?:ed|ing)?\b|took (?:too |so )?long|not (?:in|within) 10"
                     r"|\b(?:[2-9]\d|1\d\d)\s*(?:min|mins|minutes)\b|\bder se\b",
    "order_issues": r"\bmissing\b|wrong (?:item|product|order|thing)s?|\bdamaged?\b|\bbroken\b|\bexpir|\brotten\b"
                    r"|\bspoil|\bleak|\bstale\b|not (?:been )?delivered|\bundelivered\b|\bincomplete\b|\bgalat\b",
    "fees": r"\bfees?\b|delivery charges?|handling (?:fee|charge)|platform (?:fee|charge)|\bsurge\b|small cart"
            r"|unnecessary charges?|extra charges?",
    "refunds": r"\brefund|money back|pais[ae] wapas|amount (?:not|deducted)|\bdeducted\b",
    "support": r"customer (?:care|support|service)|\bsupport\b|\bchat\b|\bagent\b|\bexecutive\b|no response"
               r"|not respond|\bhelpline\b|\brude\b",
    "app_issues": r"\bcrash|\bbug|\bglitch|not working|\bloading\b|\botp\b|\blog ?in\b|payment (?:fail|issue|problem)"
                  r"|\berror\b|stuck on\b|screen (?:is )?stuck",
}
PATTERNS = {theme: re.compile(rx, re.IGNORECASE) for theme, rx in THEMES.items()}

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "reviews"


def fetch_reviews(package):
    """Return the newest REVIEW_SAMPLE reviews for one app, or None on failure."""
    signal.alarm(DEADLINE_SECONDS)
    try:
        batch, _ = reviews(package, lang="en", country="in", sort=Sort.NEWEST, count=REVIEW_SAMPLE)
    except Exception as exc:  # library errors, timeouts and parse failures all mean "no data today"
        print(f"  reviews {package} failed: {exc!r}", file=sys.stderr)
        return None
    finally:
        signal.alarm(0)
    return batch or None


def summarise(batch):
    """Turn one sample of reviews into percentages. Text is only read here, never stored."""
    n = len(batch)
    complaints = [r["content"] or "" for r in batch if r["score"] <= LOW_STARS]
    summary = {"reviews_sampled": n, "low_star_pct": 100 * len(complaints) / n}
    for theme, pattern in PATTERNS.items():
        summary[f"complaint_{theme}_pct"] = 100 * sum(1 for text in complaints if pattern.search(text)) / n
    unmatched = sum(1 for text in complaints if not any(p.search(text) for p in PATTERNS.values()))
    summary["complaint_unclassified_pct"] = 100 * unmatched / n
    return summary


def main():
    fetch_date = datetime.now(timezone.utc).date().isoformat()
    rows, gaps = [], []

    for brand, package in APPS.items():
        batch = fetch_reviews(package)
        if batch is None:
            gaps.append(brand)
            continue
        for metric, value in summarise(batch).items():
            rows.append({"fetch_date": fetch_date, "date": fetch_date, "brand": brand,
                         "source": "play_reviews", "metric": metric, "value": round(value, 3)})

    if rows:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{fetch_date}.csv"
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"reviews: wrote {len(rows)} rows to {out}")
    if gaps:
        print(f"reviews: GAPS for {', '.join(gaps)}", file=sys.stderr)
    sys.exit(0 if rows else 1)


if __name__ == "__main__":
    main()
