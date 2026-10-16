"""Deterministic insight rules over the built tables. No LLM: every sentence comes
from a rule with an explicit threshold and carries the numbers it was computed from.

Reads  docs/data/*.parquet
Writes docs/data/insights.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"

WINDOW_DAYS = 7  # compare the latest 7 days with the 7 days before them
MIN_DAYS = 5     # each window needs at least this many days of data, or the rule stays silent
SHARE_SHIFT_PTS = {"google_trends": 2.0, "wikipedia": 3.0}  # same-day refetch noise was ~0.2 pts
RATING_SHIFT_STARS = 0.03  # weekly mean; a young app's daily rating moves about this much
TONE_MIN_ARTICLES = 5   # per week; tone from fewer articles is one journalist's mood
TONE_FLIP_SWING = 1.0   # the sign change must also be a real move, not -0.05 to +0.05
VELOCITY_SHIFT_PCT = 50    # weekly mean of new ratings per day
SOURCE_LABEL = {"google_trends": "Google search", "wikipedia": "Wikipedia pageview", "gdelt": "news"}


def load(name):
    df = pd.read_parquet(DATA / name)
    df["date"] = pd.to_datetime(df["date"])
    return df


def two_windows(df):
    """Split rows into the latest WINDOW_DAYS days and the WINDOW_DAYS days before them."""
    end = df["date"].max()
    recent_start = end - pd.Timedelta(days=WINDOW_DAYS - 1)
    prior_start = recent_start - pd.Timedelta(days=WINDOW_DAYS)
    recent = df[df["date"] >= recent_start]
    prior = df[(df["date"] >= prior_start) & (df["date"] < recent_start)]
    return recent, prior


def week_on_week(df, col):
    """Yield (brand, prior mean, recent mean, window) for brands with enough days in both weeks."""
    if df.empty:
        return
    recent, prior = two_windows(df)
    window = [recent["date"].min().date().isoformat(), recent["date"].max().date().isoformat()]
    for brand in sorted(df["brand"].unique()):
        r = recent.loc[recent["brand"] == brand, col]
        p = prior.loc[prior["brand"] == brand, col]
        if len(r) >= MIN_DAYS and len(p) >= MIN_DAYS:
            yield brand, p.mean(), r.mean(), window


def insight(rule, brand, source, text, value, threshold, window):
    return {
        "rule": rule, "brand": brand, "source": source, "text": text,
        "value": round(float(value), 3), "threshold": threshold,
        "strength": round(abs(float(value)) / threshold, 2), "window": window,
    }


def share_shift(share):
    """Rule 1: a brand's average share of signal moved by at least the threshold, week on week."""
    out = []
    for source, threshold in SHARE_SHIFT_PTS.items():
        rows = share[share["source"] == source]
        two_brands = rows["brand"].nunique() == 2  # one brand's gain is the other's loss: report once
        for brand, before, after, window in week_on_week(rows, "share"):
            change = after - before
            if abs(change) < threshold or (two_brands and change < 0):
                continue
            direction = "rose" if change > 0 else "fell"
            text = (f"{brand}'s {SOURCE_LABEL[source]} share {direction} {abs(change):.1f} pts "
                    f"week on week, from {before:.1f}% to {after:.1f}%.")
            out.append(insight("share_shift", brand, source, text, change, threshold, window))
    return out


def rating_shift(signals):
    """Rule 2: a brand's average Play Store rating moved by at least RATING_SHIFT_STARS, week on week."""
    out = []
    rows = signals[signals["metric"] == "play_rating"]
    for brand, before, after, window in week_on_week(rows, "value"):
        change = after - before
        if abs(change) < RATING_SHIFT_STARS:
            continue
        direction = "rose" if change > 0 else "fell"
        text = f"{brand}'s Play Store rating {direction} from {before:.3f} to {after:.3f} week on week."
        out.append(insight("rating_shift", brand, "play_store", text, change, RATING_SHIFT_STARS, window))
    return out


def velocity_shift(signals):
    """Rule 3: new Play Store ratings per day changed by at least VELOCITY_SHIFT_PCT, week on week."""
    out = []
    rows = signals[signals["metric"] == "play_ratings_per_day"]
    for brand, before, after, window in week_on_week(rows, "value"):
        if before <= 0:
            continue
        pct = 100 * (after / before - 1)
        if abs(pct) < VELOCITY_SHIFT_PCT:
            continue
        direction = "up" if pct > 0 else "down"
        text = (f"{brand} added {after:,.0f} new Play Store ratings a day, {direction} {abs(pct):.0f}% "
                f"on the week before ({before:,.0f}/day).")
        out.append(insight("velocity_shift", brand, "play_store", text, pct, VELOCITY_SHIFT_PCT, window))
    return out

def tone_flip(signals):
    """Rule 4: a brand's article-weighted news tone changed sign week on week, by a real margin."""
    out = []
    news = signals[signals["source"] == "gdelt"].pivot_table(
        index=["date", "brand"], columns="metric", values="value").reset_index()
    if not {"article_count", "avg_tone"} <= set(news.columns):
        return out
    news = news.dropna(subset=["article_count", "avg_tone"])
    if news.empty:
        return out
    recent, prior = two_windows(news)
    window = [recent["date"].min().date().isoformat(), recent["date"].max().date().isoformat()]
    for brand in sorted(news["brand"].unique()):
        tones = []
        for week in (prior, recent):
            w = week[week["brand"] == brand]
            n = w["article_count"].sum()
            tones.append((w["avg_tone"] * w["article_count"]).sum() / n if n >= TONE_MIN_ARTICLES else None)
        before, after = tones
        if before is None or after is None or (before > 0) == (after > 0):
            continue
        if abs(after - before) < TONE_FLIP_SWING:
            continue
        direction = "turned positive" if after > 0 else "turned negative"
        text = f"News tone on {brand} {direction} week on week: {before:+.2f} to {after:+.2f} (GDELT, article-weighted)."
        out.append(insight("tone_flip", brand, "gdelt", text, after - before, TONE_FLIP_SWING, window))
    return out


def main():
    share = load("share_of_signal.parquet")
    signals = load("signals.parquet")

    rules = [
        (share_shift, share, f"Share of signal moves at least {SHARE_SHIFT_PTS['google_trends']} pts "
                             f"(Google search) or {SHARE_SHIFT_PTS['wikipedia']} pts (Wikipedia), week on week"),
        (rating_shift, signals, f"Average Play Store rating moves at least {RATING_SHIFT_STARS} stars, week on week"),
        (velocity_shift, signals, f"New Play Store ratings per day change by at least {VELOCITY_SHIFT_PCT}%, week on week"),
        (tone_flip, signals, f"Article-weighted news tone changes sign, swinging at least {TONE_FLIP_SWING}, "
                             f"with at least {TONE_MIN_ARTICLES} articles in each week"),
    ]

    insights, errors = [], []
    for rule, table, _ in rules:
        try:
            insights += rule(table)
        except Exception as exc:  # one broken rule must not silence the others
            errors.append(f"{rule.__name__}: {exc!r}")
            print(f"insights: rule {rule.__name__} failed: {exc!r}", file=sys.stderr)

    insights.sort(key=lambda i: i["strength"], reverse=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules": [{"id": rule.__name__, "description": desc} for rule, _, desc in rules],
        "insights": insights,
        "errors": errors,
    }
    (DATA / "insights.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"insights: {len(insights)} insights from {len(rules)} rules -> docs/data/insights.json")
    for i in insights:
        print(" -", i["text"])
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()