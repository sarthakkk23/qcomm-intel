# qcomm-intel

Free, public competitive intelligence dashboard for Indian quick commerce: Blinkit, Zepto, Swiggy Instamart and Flipkart Minutes.

_Work in progress._

## Limitations

<!-- Record every data gap here as it is discovered: which source, which brand, why, and the fallback. -->

- **GDELT rate limits (news).** The DOC 2.0 API returns HTTP 429 more aggressively than its stated "one request every 5 seconds"; on 2026-10-11 the Blinkit tone call failed 5 times over ~5 minutes. The collector spaces calls 30s apart, retries with exponential backoff, and logs any brand/metric it could not fetch as a gap instead of failing the run. Because every run re-fetches the last 30 days, a missed day is backfilled by the next successful run.
- **GDELT volume is low for these brands.** Over 30 days to 2026-10-10: Blinkit ~65 articles, Swiggy Instamart 36, Flipkart Minutes 16 (single digits per day). Daily average tone on 1–2 articles is noisy, so tone-based insights require a minimum article count.
- **GDELT has missing days of its own.** For the 30 days to 2026-10-10 the API returned the same 17 dates for every brand (with explicit 0s for days without matches) and nothing for the other 13 (e.g. 14–19 Sep, 3–5 Oct). Those are gaps in GDELT's processing, not zero coverage, so they are stored as missing (NULL), never filled with 0.
- **GDELT throttling is severe from some networks.** On the first full run, 5 of 8 calls failed after 3 retries each, even after a 40-minute cooldown. Likely cause: carrier-grade NAT, where many broadband customers share one public IPv4 address. Reliability from GitHub Actions runners is tracked in RUNLOG. If it stays poor, the fallback is Google News RSS search for daily article counts (no tone).
- **No Wikipedia page for Swiggy Instamart or Flipkart Minutes.** Only their parent companies (Swiggy, Flipkart) have English Wikipedia articles, and parent pageviews are not comparable to a single quick-commerce brand. Wikipedia pageviews are collected for Blinkit (`Blinkit`) and Zepto (`Zepto_(company)`, since plain `Zepto` redirects to "Metric prefix") only, and Wikipedia share-of-signal compares those two.
- **Play Store tracks standalone quick-commerce apps only.** Instamart (`in.swiggy.android.instamart`, launched Jan 2025) and Flipkart Minutes (`com.flipkart.minutes.android`, launched 11 Sep 2026 as a limited beta) also live inside their parent apps (Swiggy, Flipkart), whose ratings mix in food delivery and general e-commerce. Standalone totals are therefore not market-size measures; insights use day-on-day change in rating and review counts, not totals. Minutes' standalone app is a month old (≈5.9k ratings at first snapshot), so most Minutes usage is not captured.
- **Play Store data is a daily snapshot with no history.** Unlike GDELT and Wikipedia, a failed Play Store fetch cannot be backfilled later; a missed day stays missing. `google-play-scraper` has no network timeout, so the collector sets a 30s socket timeout to avoid hanging the daily run.
