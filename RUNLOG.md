# RUNLOG

Build log for qcomm-intel. One entry per stage; times in IST.

| # | Stage | Finished | Notes |
|---|---|---|---|
| 1 | Environment setup | 2026-10-11 19:52 | Python 3.12.15 (Homebrew), venv, pandas 3.0.6, pyarrow 26.0.0, gh CLI linked, git identity set to GitHub noreply |
| 2 | news.py (GDELT) | 2026-10-11 22:50 | 4 brands × volume + tone, 30-day window. First full local run: 85 rows, 5/8 calls lost to HTTP 429 (likely CGNAT shared IP). GDELT itself returned only 17 of 30 days. |
| 3 | attention.py (Wikipedia + Play) | 2026-10-11 21:35 | 72 rows, 0 gaps. Debugged an 8-minute hang: home network's IPv6 to Google is broken (`curl -6` timed out, `-4` answered in 0.19s); fixed with a 60s `signal.alarm` deadline per Play Store call. |
| 4 | trends.py (Google Trends) | 2026-10-15 21:14 | One 4-brand request, geo=IN, last 30 days. 120 daily rows + 144 state rows. Succeeded on attempt 3 after two HTTP 429s. 30-day avg share of search: Blinkit 55.0%, Zepto 28.5%, Instamart 11.7%, Minutes 4.8%. |
| 5 | GitHub repo + daily Actions workflow | 2026-10-16 03:41 | Public repo sarthakkk23/qcomm-intel. First automated run (#38763964289): success in 28m44s, of which GDELT took 27m15s (5/8 calls 429 from Actions too); Play Store 2s, 0 gaps; Trends 63s after one 429. Hardened: collectors reordered (attention → trends → news), news.py 20-min run budget, news step 25-min timeout, job timeout 45 min. Same-day Trends re-fetch moved Blinkit's raw index 89→91 but 30-day share only 55.0→54.8%, confirming share-of-search as the stable measure. |
| 6 | build.py | 2026-10-16 03:50 | 413 raw rows → 365 signals (incl. 8 Play velocity rows), 188 share-of-signal rows, 140 state rows; ~15 KB of Parquet in docs/data. Dedupe = latest fetch per (date, brand, source, metric); same-day partials dropped; shares only when every expected brand is present (GDELT: 0 complete days so far); Trends shares computed within each fetch. Daily shares verified to sum to 100. |
| 7 | insights.py (rule engine) | 2026-10-16 15:33 | 5 deterministic rules (share shift, rating shift, velocity shift, tone flip, new ad themes), thresholds as named constants set from observed noise. Shared week-on-week helper; ≥5 days per week or the rule stays silent. First output: 1 insight (Blinkit Wikipedia share +4.7 pts, strength 1.55). Rules 4–5 verified on synthetic data. Corrected an earlier over-read: Minutes' rating "slip" reversed the next day, and day-to-day Play velocity is distorted by cron delays, so Play rules use weekly means. |
