# qcomm-intel

Free, public competitive intelligence dashboard for Indian quick commerce: Blinkit, Zepto, Swiggy Instamart and Flipkart Minutes.

_Work in progress._

## Limitations

<!-- Record every data gap here as it is discovered: which source, which brand, why, and the fallback. -->

- **GDELT rate limits (news).** The DOC 2.0 API returns HTTP 429 more aggressively than its stated "one request every 5 seconds"; on 2026-10-11 the Blinkit tone call failed 5 times over ~5 minutes. The collector spaces calls 30s apart, retries with exponential backoff, and logs any brand/metric it could not fetch as a gap instead of failing the run. Because every run re-fetches the last 30 days, a missed day is backfilled by the next successful run.
- **GDELT volume is low for these brands.** Blinkit averaged ~2 matching articles/day over 30 days, and days with no matches are omitted by the API (treated as 0). Daily average tone on 1–2 articles is noisy, so tone-based insights require a minimum article count.
- **No Wikipedia page for Swiggy Instamart or Flipkart Minutes.** Only their parent companies (Swiggy, Flipkart) have English Wikipedia articles, and parent pageviews are not comparable to a single quick-commerce brand. Wikipedia pageviews are collected for Blinkit (`Blinkit`) and Zepto (`Zepto_(company)`, since plain `Zepto` redirects to "Metric prefix") only, and Wikipedia share-of-signal compares those two.
