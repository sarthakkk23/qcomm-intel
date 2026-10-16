"""Turn raw collector CSVs into clean Parquet tables for the dashboard.

Reads  data/raw/{news,attention,trends}/*.csv (shared schema) and data/raw/trends_states/*.csv
Writes docs/data/signals.parquet, share_of_signal.parquet, states.parquet and meta.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data"
KEY = ["date", "brand", "source", "metric"]

# (source, metric) -> brands that must all be present on a day before shares are computed.
# Absolute counts can be mixed across fetches; a relative index only within a single fetch.
ABSOLUTE_SHARES = {("gdelt", "article_count"): 4, ("wikipedia", "wiki_pageviews"): 2}
RELATIVE_SHARES = {("google_trends", "search_interest"): 4}


def load(folders):
    """Stack every CSV in the given raw folders into one DataFrame."""
    files = sorted(f for folder in folders for f in (RAW / folder).glob("*.csv"))
    return pd.concat(
        (pd.read_csv(f, parse_dates=["fetch_date", "date"]) for f in files), ignore_index=True
    )


def latest_fetch(df, key):
    """Keep one row per key: the one from the most recent fetch."""
    return df.sort_values("fetch_date").drop_duplicates(subset=key, keep="last")


def shares(df, by, inputs):
    """Each brand's % of its group's total, for groups where every expected brand is present."""
    parts = []
    for (source, metric), n_brands in inputs.items():
        part = df[(df["source"] == source) & (df["metric"] == metric)]
        part = part[part.groupby(by)["brand"].transform("nunique") == n_brands]
        total = part.groupby(by)["value"].transform("sum")
        parts.append(part.assign(share=100 * part["value"] / total))
    return pd.concat(parts, ignore_index=True).dropna(subset=["share"])


def play_velocity(signals):
    """Average new ratings/reviews per day between consecutive Play Store snapshots."""
    counts = signals[signals["metric"].isin(["play_ratings_count", "play_reviews_count"])]
    counts = counts.sort_values(["brand", "metric", "date"])
    g = counts.groupby(["brand", "metric"])
    per_day = g["value"].diff() / g["date"].diff().dt.days
    velocity = counts.assign(value=per_day, metric=counts["metric"].str.replace("_count", "_per_day"))
    return velocity.dropna(subset=["value"])


def write(df, name):
    """Write a table as Parquet with true DATE columns, so SQL date maths works in DuckDB."""
    df = df.copy()
    for col in ("date", "fetch_date"):
        if col in df:
            df[col] = df[col].dt.date
    df.to_parquet(OUT / name, index=False)
    print(f"build: wrote {len(df)} rows to docs/data/{name}")

def build_states():
    """Latest 30-day share of search by state; states with no measurable search are dropped."""
    files = sorted((RAW / "trends_states").glob("*.csv"))
    states = pd.concat((pd.read_csv(f, parse_dates=["fetch_date"]) for f in files), ignore_index=True)
    states = states[states["fetch_date"] == states["fetch_date"].max()]
    return states[states.groupby("state")["value"].transform("sum") > 0]

def main():
    raw = load(["news", "attention", "trends", "reviews"])
    n_raw = len(raw)
    # A day's numbers are final only once it is over. Play Store rows are point-in-time snapshots.
    partial = (raw["date"] >= raw["fetch_date"]) & ~raw["source"].isin(["play_store", "play_reviews"])
    raw = raw[~partial]

    signals = latest_fetch(raw, KEY).drop(columns="fetch_date")
    signals = pd.concat([signals, play_velocity(signals)], ignore_index=True)

    share = pd.concat([
        shares(signals, ["date"], ABSOLUTE_SHARES),
        latest_fetch(shares(raw, ["fetch_date", "date"], RELATIVE_SHARES), KEY).drop(columns="fetch_date"),
    ], ignore_index=True)

    OUT.mkdir(parents=True, exist_ok=True)
    write(signals.sort_values(KEY), "signals.parquet")
    write(share[KEY + ["share"]].sort_values(KEY), "share_of_signal.parquet")

    states = build_states()
    write(states, "states.parquet")

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_date": {s: d.date().isoformat() for s, d in signals.groupby("source")["date"].max().items()},
        "rows": {"raw": n_raw, "signals": len(signals), "share_of_signal": len(share), "states": len(states)},
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"build: wrote meta.json, built_at {meta['built_at']}")

if __name__ == "__main__":
    main()