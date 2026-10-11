# RUNLOG

Build log for qcomm-intel. One entry per stage; times in IST.

| # | Stage | Finished | Notes |
|---|---|---|---|
| 1 | Environment setup | 2026-10-11 19:52 | Python 3.12.15 (Homebrew), venv, pandas 3.0.6, pyarrow 26.0.0, gh CLI linked, git identity set to GitHub noreply |
| 2 | news.py (GDELT) | 2026-10-11 22:50 | 4 brands × volume + tone, 30-day window. First full local run: 85 rows, 5/8 calls lost to HTTP 429 (likely CGNAT shared IP). GDELT itself returned only 17 of 30 days. |
| 3 | attention.py (Wikipedia + Play) | 2026-10-11 21:35 | 72 rows, 0 gaps. Debugged an 8-minute hang: home network's IPv6 to Google is broken (`curl -6` timed out, `-4` answered in 0.19s); fixed with a 60s `signal.alarm` deadline per Play Store call. |
