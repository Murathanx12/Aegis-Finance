# Lane N data-acquisition — REPORT (2026-09-11)

Read-only on the repo; all writes under scratchpad/lane_n/. No repo files
edited, no test suite run, no servers started. All probes <=200 rows/source.

## Per-source: probed, rows/day, PIT grade, schema, cursor, recommendation

### Alpaca/Benzinga news (`alpaca_benzinga_news`)
NOT PROBED — `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` (names from
`backend/services/portfolio_intelligence/alpaca_mirror.py`'s docstring; no
`ALPACA_*` constant lives in `backend/config.py`) both absent from this
environment; `.env` off limits. Est. ~130 articles/day historically (per
research_news.md). PIT: **native_stamp** (`created_at`, UTC). Cursor:
`created_at`, incremental. **Recommendation: build FIRST once keys exist —
this is the only ticker-tagged, body-bearing, native-stamp source in the
set; N-A already orders it first.**

### GDELT DOC 2.0 (`gdelt_doc_v2`)
PROBED (2 of 5 queries succeeded per run; region/theme rotate which ones
429). Est. rows/day: hundreds to low thousands per region at `maxrecords=250`
with a wide query, but **the real ceiling is the rate limit, not content
volume** — see finding below. PIT: **first_seen_only** (`seendate` is a
crawl/index timestamp, not a publisher's own stamp; write `first_seen_utc`
at ingest). Schema: `url, url_mobile, title, seendate, socialimage, domain,
language, sourcecountry`. No body, no tickers. Cursor: none native — page by
`seendate` descending and de-dupe by `url`. **Recommendation: the backbone
crawler for breadth, but the corpus writer needs backoff far more
conservative than the docs claim (below) or it will spend most of its budget
on 429s.**

### Google News RSS, 10 combos (`google_news_rss_*`)
PROBED, all 10/10 succeeded, 26-38 items each, 1.0-2.1s latency, no rate
limiting observed at this volume. Est. rows/day: ~30-40 items per combo per
pull, likely overlapping/rotating on repeat pulls within a day (this is a
live "top stories" feed, not an archive) — a daily pull under-samples;
several pulls/day would be needed to avoid missing stories that rotate off
before the next pull. PIT: **index_state** — never a label source (both the
research note and this probe agree; Google can re-rank/backfill). Schema:
`title, link, pubDate (RFC 822), source`. Cursor: none native; de-dupe by
`link`. **Recommendation: build FIRST alongside Alpaca — it is free, fast,
zero-setup, and gives immediate Asia-first breadth (HK/SG/IN/CN/TW/JP/KR all
confirmed live) while Alpaca/GDELT PIT-grade infrastructure is built.**

### AKShare — CN news (`akshare_stock_news_em`, `akshare_stock_news_main_cx`)
NOT PROBED — package not installed (`pip show akshare` confirms absent);
installing into the checkout's venv was out of scope per task instructions.
Function names and behavior read directly from GitHub source
(`akfamily/akshare`, main, 2026-09-11):
- `stock_news_em(symbol)` — per-symbol Eastmoney-search scrape, up to 100
  items/call. PIT: **index_state** (title/date/source/content/url; `curl_cffi`
  scrape of a search endpoint with a cookie baked into source — fragile,
  bound to break on Eastmoney's next markup change).
- `stock_news_main_cx()` — whole-market Caixin feed, 100 items/call, but the
  function code itself drops every timestamp column before returning
  (`temp_df[["tag","summary","url"]]`) — **index_state with no native stamp
  at all**, not just an editable one.
- No dedicated HK news function exists in AKShare's 24-function `stock_hk_*`
  surface (verified by grepping the full `__init__.py` export list).
**Recommendation: defer AKShare until the venv question is settled; it is the
right library for CN A-share PRICE data (per research_patents_data.md) but its
news functions are both index_state and one is confirmed fragile
(hardcoded cookie/UA). Google News RSS zh-CN + GDELT sourcecountry:CH cover
more CN breadth for less engineering risk in the meantime.**

### SEC EDGAR 8-K current feed (`sec_edgar_8k_current_atom`)
PROBED — **the roadmap's endpoint description needs a correction**:
`action=getcompany` with no company/CIK returns an empty feed (0 entries,
confirmed). The actual current-filings feed is `action=getcurrent`
(40 entries, 200, 1.35s once retried at a 30s timeout — one attempt at 15s
timed out with no other symptom). Est. rows/day: SEC files roughly
100-300+ 8-Ks on an average US trading day system-wide (this pull only
returns the newest `count` at request time, so a same-day poller must page
via `start=`). PIT: **native_stamp** (`updated`, US/Eastern, filing
acceptance time). Schema: `title` (form + company + CIK), `updated`, `link`,
`summary` (Filed date, AccNo, Size, Item numbers — Item 2.02 = earnings). No
ticker, CIK only. Cursor: `updated` desc + `start=` paging; join CIK->ticker
via SEC's free `company_tickers.json` (not probed here). **Recommendation:
build SECOND — free, native-stamped, zero auth, and Item 2.02 rows are a
clean earnings-announcement PIT signal with no vendor dependency at all.**

### Nikkei Asia RSS (`nikkei_asia_rss`)
PROBED — **format correction**: this is RSS 1.0/RDF, not RSS 2.0; a
namespace-naive parser returns 0 items (this probe's own first, wrong,
result). Fixed: 50/50 items, 0.77s, genuinely pan-Asia coverage (China, HK,
Vietnam, Japan all appeared). PIT: **index_state** (no confirmed stamp field
survives cleanly — `date` element present but timezone unverified). Schema:
`title, link, date`. Cursor: none native; de-dupe by `link`.
**Recommendation: cheap breadth add, third or fourth priority — smaller
payoff than Google News RSS's 10-region sweep since it's one feed, but it is
the one source in this set with an editorial (not aggregator) Asia focus.**

### HKEXnews RSS (`hkexnews_rss`)
NOT PROBED — no confirmed public RSS URL found in this pass (research_news.md
itself says "official RSS; paid Issuer Information Feed; Apify scrapers" but
did not hand this session a working feed URL, and finding one was out of the
<=200-row-probe scope). **Recommendation: defer, as research_news.md itself
recommends — Google News RSS en-HK + GDELT sourcecountry:HK substitute for
now.**

### Finnhub — company news + recommendation trends (`finnhub_*`)
NOT PROBED — `FINNHUB_API_KEY` absent. Free tier facts from
research_patents_data.md: 60 calls/min, `company-news` PIT via `datetime`
(native_stamp), `recommendation` trend keeps only 4 months server-side (must
snapshot daily from day 1 to build history). **Recommendation: build once a
free key exists — cheap, native-stamped, and the natural source for N-E's
daily analyst snapshot alongside yfinance.**

### yfinance `Ticker.news` (`yfinance_ticker_news`)
PROBED — 4/4 tickers OK (NVDA, BABA, TSM, 9988.HK), 10 items each,
0.47-2.87s. Est. rows/day: 10 items/call is likely a fixed page size, not a
full day's volume — repeat pulls needed to avoid missing turnover. PIT:
**first_seen_only** (`content.pubDate`, ISO 8601 UTC — Yahoo's own, but
unofficial/unverified against backfill risk, hence not native_stamp).
Schema: nested `content.{title, description, summary, pubDate, provider,
canonicalUrl, ...}`; body is a ~130-140-char blurb, not full text. Already
used exactly this way in `backend/services/news_intelligence.py:
fetch_stock_news`. Cursor: none native; de-dupe by `content.canonicalUrl` or
`id`. **Recommendation: keep as the low-effort per-ticker supplement it
already is; do not expand it into a primary source — no rate-limit
guarantee, unofficial API, thin bodies.**

### yfinance recommendations/targets (`yfinance_recommendations`)
Not separately network-probed this pass (news probe only pulled `.news`);
schema/PIT grade taken from `research_news.md` + the existing
`news_intelligence.py` pattern. PIT: **index_state** — current-snapshot only,
snapshot daily to build a PIT series (N-E's stated design). **Recommendation:
pair with Finnhub's `recommendation` trend as N-E's two free legs.**

### Wikipedia pageviews (`wikipedia_pageviews`)
PROBED — 200, 10 daily rows for NVDA (en.wikipedia), 0.63s. **Explicitly a
coverage sensor, never a news/label source**, per task instructions. Official
Wikimedia REST API, generous rate limits, daily granularity to 2015.
**Recommendation: cheap to add once the corpus writer exists; low priority —
not one of the "build first" three.**

### Greenhouse/Lever/Ashby ATS (N-G's data source)
Not network-probed (N-G is a separate pre-registered trial with a
token-discovery bottleneck, not a rate-limit question); documented in the
registry for completeness only, out of scope for N-B's whole-market news
registry proper.

## The three sources to build FIRST

1. **Google News RSS, 10-region sweep** — zero setup, zero auth, all 10
   region/language combos verified live today, immediate Asia-first breadth
   (this alone answers "is Asia first a number on the board" for HK/SG/IN
   partially). `index_state` — feeds the coverage card, never a label.
2. **SEC EDGAR `getcurrent` current-events Atom feed** — free, zero auth,
   `native_stamp`, and the roadmap's own endpoint description was wrong
   (`getcompany` vs `getcurrent`) — building this first also fixes that
   defect before N-A inherits it. Item 2.02 rows are a clean, free
   earnings-PIT signal with no vendor dependency.
3. **Alpaca/Benzinga news** — once the two env keys exist. It is the only
   source in this whole registry that is simultaneously native-stamp,
   ticker-tagged, AND body-bearing; N-A already orders it first and this
   probe found nothing to contradict that. Until the keys land, GDELT +
   Google News RSS + SEC EDGAR cover the gap at `first_seen_only`/
   `index_state` grade.

## Daily schedule in HKT (laptop-run, under every free limit)

| HKT time | job | sources | approx calls | limit headroom |
|---|---|---|---|---|
| 05:00 | US EOD sweep | SEC EDGAR `getcurrent` (page via `start=`, ~5-10 calls to cover overnight filings), Alpaca news incremental (once keyed) | ~15 | EDGAR 10 req/s cap — nowhere close |
| 06:00 | Asia EOD + delistings | Google News RSS (10 combos, ~10 calls), GDELT `sourcecountry:HK/CH/JA/KS` **one call every >=20s, not back-to-back** (~4 calls, ~80s wall time) | ~14 | GDELT: this probe's own finding says budget >=15-20s between calls, not the documented 5s |
| 08:00 | EDGAR diff + earnings calendar | SEC EDGAR `getcurrent` diff pass, Finnhub earnings calendar (once keyed) | ~10 | well under 60/min Finnhub cap |
| 22:00 | options snapshot + theme sweep | GDELT theme queries (5 themes from `theme_baskets.yaml`, paced >=20s apart, ~100s wall time), yfinance chain snapshot for liquid names | ~5 GDELT + N yfinance | GDELT paced; yfinance has no documented cap but keep to liquid-name subset per research_patents_data.md |

Everything above stays well inside every free tier's documented limit
**except GDELT, whose documented limit (5s) this probe found to be
optimistic in practice** — the schedule above already budgets the wider,
empirically-observed cadence rather than the documented one.

## Corrections filed against the roadmap/research notes (so the Opus
corpus-writer build in chunk 4 doesn't inherit them)

1. **SEC EDGAR endpoint**: roadmap says "SEC EDGAR Atom (8-K current feed)"
   without the action parameter — `action=getcompany` (the obvious guess)
   returns nothing; `action=getcurrent` is the real one. See `news_sources.yaml`.
2. **GDELT rate limit**: the documented "1 request/5s" under-estimates the
   real constraint by roughly 3-4x in this probe's sample (5 queries, 2
   full runs, only 2/5 succeeded each time even with 6s+12-15s-latency
   spacing).
3. **Nikkei Asia RSS format**: RSS 1.0/RDF, not RSS 2.0 — a generic RSS
   parser that doesn't handle namespaces silently returns zero items, which
   looks exactly like "source returns 0 twice is red" (N-A's own invariant)
   but is actually a parser bug, not a dead source. Worth a comment in the
   corpus writer so it isn't misdiagnosed as a dead feed.
4. **AKShare has no HK news function** — the roadmap's phrase "AKShare (CN/HK
   at zero marginal cost)" (§11b) is right for HK PRICE data (24 `stock_hk_*`
   functions exist) but wrong for HK NEWS specifically; there is none.

## Deliverables in this directory

- `news_sources.yaml` — 24-source registry (World Monitor shape).
- `probes/*.jsonl` + `probes/SUMMARY.md` — raw probe rows and narrative
  summary per source, including the GDELT/EDGAR/Nikkei corrections above.
- `name_table/issuers.csv` — 3,056-row skeleton (symbol, primary_name,
  aliases, country, is_adr) for the full universe; 200 rows carry a
  yfinance-sourced `primary_name` (alphabetically-first 200 symbols, a
  reproducible deterministic sample — not random), the remaining 2,856 carry
  `primary_name=""` and `aliases=<ticker only>` so the gap is visible rather
  than silently filled. yfinance `.info` throughput measured at 1.38s/name
  (200 names in 276.5s) — pulling all 3,056 names would take ~70 minutes at
  this rate and was out of the <=200-row-per-source probe budget.
- `name_table/asia_adrs.csv` — 31 candidate US/Asia dual-listing pairs, each
  US leg checked against yfinance `.info`/`.history` for a live
  `shortName`+`exchange`. Four errors caught and fixed, two before writing
  and two after seeing the probe output: (1) MUFG/Mizuho's Tokyo codes were
  initially swapped (correct: MUFG=8306.T, Mizuho/MFG=8411.T); (2) ticker
  `LPL` was initially mis-mapped to LG Corp — `LPL` is actually LG Display's
  NYSE ADR ticker (local code 034220.KS), not LG Corp's; (3) `MRAAY` was
  guessed as Mitsubishi Corp's ADR — yfinance's returned `shortName` says
  **Murata Manufacturing**, not Mitsubishi Corp (Mitsubishi Corp's real ADR
  ticker is `MSBHY`; Murata's TSE code is 6981, not the 8058 originally
  entered, which is actually Mitsubishi Corp's TSE code — that mix-up is
  probably how the wrong company ended up in the candidate list to begin
  with); (4) `CAJ` (Canon's NYSE ADR) came back `EMPTY_INFO` on `.info` and
  `"possibly delisted; no price data found"` on a `.history()` pull — Canon's
  NYSE ADR appears to be genuinely delisted, consistent with the broader
  trend of Japanese issuers dropping NYSE ADRs for OTC/Pink Sheets to cut
  Sarbanes-Oxley compliance cost; marked `DELISTED` rather than `YES`. Local-
  exchange company names in native script were NOT fetched (would have
  needed a second yfinance pass on the `.HK`/`.T`/`.KS` legs, out of budget
  already spent on the 200-name US sample) — `local_symbol` and
  `local_exchange` columns are filled from public knowledge, not
  independently re-verified beyond the US leg.
