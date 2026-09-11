# Lane N probes — notes (2026-09-11)

All probes network-only, read-only, capped at <=200 rows/source per task
instructions. Raw rows in sibling *.jsonl files, one row per JSON line.

## GDELT DOC 2.0 (gdelt.jsonl, gdelt_summary.json)

Query: sourcecountry:HK / sourcecountry:CH (China) / sourcecountry:JA
(Japan) / sourcecountry:KS (Korea), plus one theme query
(NVDA OR "semiconductor" OR "AI chip") for ai_compute. mode=artlist&
format=json&maxrecords=50.

| query | status | latency | rows |
|---|---|---|---|
| region:HK | 429 | 12.4s | 0 |
| region:CN | 429 | 12.4-14.2s | 0 |
| region:JP | 200 | 22.4s | 50 |
| region:KR | 200 | 15.9s | 50 |
| theme:ai_compute | 200/429 (mixed across 2 runs) | 12-15s | 0-50 |

Finding: the documented "one request every 5 seconds" is not sufficient in
practice. Two full runs, second spaced 6s apart (so ~18-20s wall-clock between
request STARTS given ~12-15s own latency), still hit 429 on 3 of 5 queries.
Only 2 of 5 (rotating which ones, not consistently the same query) succeeded
per run. backend/services/news_intelligence.py's existing 1.0s stagger
between its own 3 sequential calls is well under this - consistent with that
module's own 2026-07-16 postmortem note about a self-inflicted 429 storm.
Recommendation for the corpus writer: budget >=1 request per 15-20s per
region/theme query, with exponential backoff on 429, not a fixed 5s or 1s
stagger. Schema returned: url, url_mobile, title, seendate, socialimage,
domain, language, sourcecountry - no body, no tickers. seendate format
YYYYMMDDTHHMMSSZ (UTC).

## Google News RSS (google_news.jsonl, google_news_summary.json)

10 hl/gl/ceid combos, all 200, all fast (1.0-2.1s).

| combo | items |
|---|---|
| en-US/US | 38 |
| en-GB/GB | 38 |
| en-HK/HK | 38 |
| en-SG/SG | 38 |
| en-IN/IN | 38 |
| en-AU/AU | 38 |
| zh-CN/CN | 26 |
| zh-TW/TW | 34 |
| ja/JP | 30 |
| ko/KR | 34 |

zh-CN returns noticeably fewer items (26 vs 38 for the en-* editions) -
plausibly because google.com itself is blocked inside China and this feed is
served/crawled from outside. No rate limiting observed at this volume. Schema:
title, link, pubDate (RFC 822), source (element <source>). index_state
grade confirmed - no first-publish guarantee, breadth/coverage sensor only,
never a label source.

## SEC EDGAR 8-K current feed (edgar_nikkei_wiki.jsonl)

Correction to the roadmap's endpoint description: action=getcompany
(no CIK/company given) returns an EMPTY Atom feed (0 entries) - that action
needs a specific company. The actual whole-market "latest 8-K filings" feed is
action=getcurrent, e.g.:

https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include&count=40&output=atom

Probed: 200, 40 entries, 1.35s latency (one earlier attempt in the same
session timed out after 15s with no other symptom - bumped timeout to 30s and
it succeeded instantly on retry; treat 15s as too tight for this endpoint under
load, budget 30s). Schema per entry: title ("8-K - COMPANY NAME (CIK)
(Filer)"), updated (US/Eastern, e.g. 2026-09-11T07:00:21-04:00),
link[@href] (filing index page), summary (HTML: Filed date, AccNo, Size,
and Item numbers, e.g. "Item 8.01: Other Events" or "Item 2.02: Results of
Operations and Financial Condition" - the 2.02 rows are the earnings-
announcement PIT signal named in research_patents_data.md). No ticker in the
feed, CIK only - resolving to a symbol needs SEC's own
company_tickers.json (free, not probed here).

## Nikkei Asia RSS (edgar_nikkei_wiki.jsonl)

Correction: this is RSS 1.0 / RDF (<rdf:RDF><channel>...<item>, items
namespaced under http://purl.org/rss/1.0/), not RSS 2.0. A naive
root.findall(".//item") with no namespace handling returns ZERO matches -
that was this probe's first result (0 items, false negative) before the
parser was fixed to iterate all elements and strip namespaces. Fixed: 200, 50
items, 0.77s latency. Sample titles span China, Hong Kong, Vietnam, Japan -
genuinely pan-Asia, not JP-only, in this 50-item sample (e.g. "Chinese Nvidia
challenger Enflame jumps 179% in Shanghai market debut", "Hong Kong Tiananmen
vigil organizers sentenced..."). Schema: title, link, date - no timezone
marker observed on date in this sample; treat as unverified TZ, likely
UTC or JST.

## Wikipedia pageviews (edgar_nikkei_wiki.jsonl)

Official Wikimedia REST API, article=Nvidia, en.wikipedia, daily,
2026-09-01..2026-09-10. Probed: 200, 10 rows, 0.63s latency. Schema:
project, article, granularity, timestamp (YYYYMMDDHH), access, agent,
views. Coverage sensor only, per task instructions - never a news/label
source.

## yfinance Ticker.news (yfinance_news.jsonl, yfinance_news_summary.json)

4 tickers (NVDA, BABA, TSM, 9988.HK), 1s pacing. All 200, 10 items each,
0.47-2.87s latency (first call slower - cold Yahoo session). Schema:
item = {id, content: {id, contentType, title, description, summary, pubDate,
displayTime, isHosted, bypassModal, previewUrl, thumbnail, provider,
canonicalUrl, clickThroughUrl, metadata, finance, storyline}}. pubDate is
ISO 8601 UTC (2026-09-10T16:00:39Z). Body (summary/description) is a
short blurb, observed 129-143 chars on NVDA rows - NOT full article text. HK
dual-listed ticker 9988.HK returned 10 items same as BABA, but titles in
this small sample were all English/global-wire, not local HK press - whether
.HK-suffixed tickers surface Chinese-language coverage is unverified at this
sample size.

## AKShare - NOT network-probed

pip show akshare confirms NOT INSTALLED in this environment; per task
instructions, installing into the checkout's venv was not attempted. Instead,
read the library's source directly from GitHub (akfamily/akshare, main
branch, 2026-09-11) via gh api:

- stock_news_em(symbol="603777") - module akshare/news/news_stock.py.
  Scrapes Eastmoney's search API (search-api-web.eastmoney.com, via
  curl_cffi), returns up to 100 most-recent items PER STOCK CODE: columns
  keyword/title/content/date/source/url (Chinese column names in source:
  guanjianci/xinwenbiaoti/xinwenneirong/fabushijian/wenzhangalaiyuan/xinwenlianjie).
  No documented rate limit; it is an unofficial scrape against a search
  endpoint with a hardcoded browser User-Agent and stale cookie header baked
  into the source - fragile.
- stock_news_main_cx() - module akshare/stock/stock_news_cx.py. Whole-market
  Caixin feed, pageSize=100, but the function KEEPS ONLY tag/summary/url
  from the response - no timestamp column survives, so this is index_state
  by construction (no native stamp available at all, not just an editable
  one).
- No dedicated Hong Kong news function exists. Searched the full
  __init__.py export list (7,097 lines) for every stock_hk_* symbol: 24 HK
  functions are exported (spot prices, historical bars, valuation, dividends,
  hot-rank, comparison tables) and none is a news feed. stock_news_em
  (symbol=<HK code>) might incidentally return HK results via Eastmoney's
  search but this is unverified, not a confirmed HK source.

## Alpaca / Finnhub - not probed, keys absent

Checked (presence only, never printed) via PowerShell $env: lookups:
ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY (exact names from
backend/services/portfolio_intelligence/alpaca_mirror.py's docstring - no
ALPACA_* constant exists in backend/config.py itself), and
FINNHUB_API_KEY - all three ABSENT from this environment. Recorded as
"not probed: key absent" in news_sources.yaml, per task instructions.
