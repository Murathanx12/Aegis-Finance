# Research note 2026-09-11 — whole-market news coverage (Sonnet agent, web only)

Feeds roadmap `ROADMAP_2026-09-11_ROOT_FIRST_...md` §2.1 and lane N.

## 1. The two GitHub inspirations Murat named

**World Monitor** = `github.com/koala73/worldmonitor` — 86,006 stars, **AGPL-3.0-only** (commercial
licence sold separately), created Jan 2026, active. Real-time geopolitical/finance/infra dashboard:
500+ attributed upstream feeds catalogued by provider/tier/licence/collection-method (RSS + APIs + some
scraping), dual map engine, Tauri desktop app, AI briefs via Ollama/Groq/OpenRouter. Ships
`sdk/python/` (`worldmonitor-sdk` on PyPI). Reusable for Aegis: the **source-catalogue schema** and the
SDK; NOT the backend (AGPL binds a public tool to stay open or buy a licence).

**God's Eye** = `github.com/bilawalsidhu/gods-eye-view` — 24,752 stars, MIT (code only), open-sourced
2026-08-24. A **geospatial sensor** dashboard, not a news aggregator: flights (OpenSky, adsb.lol),
vessels (AISStream), satellites (CelesTrak/SGP4), earthquakes (USGS), fires (NASA FIRMS), traffic,
CCTV, radio, launches — vanilla JS/CesiumJS, no Python backend. Reusable part: the `DATA_SOURCES.md`
pattern of one thin fetcher per public API.

## 2. Free or cheap programmatic sources (global + Asia)

| source | key | free tier | PIT stamp | tickers | note |
|---|---|---|---|---|---|
| GDELT DOC 2.0 API | none | free, 65 languages, rolling 3-month window, GKG themes + tone | source stamp (mixed tz) | no (entities) | undocumented rate limit in spikes; fallback Web NGrams 3.0 bulk; client `github.com/alex9smith/gdelt-doc-api` |
| Google News RSS | none | unlimited-ish, per `hl/gl/ceid` (`zh-CN`, `ja`/`JP:ja`, `ko`, …) | `pubDate`, **index state not first-seen**, dedupes | no | breadth only; never a label source |
| yfinance `Ticker.news` / `Search(...).news` | none | unofficial, scrapes Yahoo | timestamp | related tickers | fragile |
| Alpaca News API (Benzinga) | Alpaca account | 200 req/min free (10k on unlimited), history to 2015, ~130 articles/day | native `created_at` | **yes** | already in the stack; the PIT-grade feed |
| Finnhub | free key | 60 calls/min; company news + sentiment; recommendation trends | yes | yes | **recommendation history kept 4 months only** — snapshot daily |
| Marketaux / NewsAPI / EODHD / Polygon | keys | 100/day · 1,000/day non-commercial · 2-4/day · paid | edited/backfilled silently | partial | thin or unsafe for PIT |
| SEC EDGAR full-text + `output=atom` RSS | none | 10 req/s | filing stamp | CIK | primary source |
| HKEXnews | none/paid | official RSS; paid Issuer Information Feed; Apify scrapers | yes | HK codes | |
| TDnet (Japan) | paid | ¥70k+ API; MCP/Apify scrapers; <15-min mandatory disclosure | yes | JP codes | defer |
| KIND (Korea) | none | `kind.krx.co.kr`, scrapeable | yes | KR codes | defer |
| SGX | none | REST delayed prices; SGXNet announcements page; no free news RSS found | | | defer |
| Chinese sources | none | **AKShare** (`github.com/akfamily/akshare`) aggregates Eastmoney/Sina/Tonghuashun/Tencent/Xueqiu; raw `hq.sinajs.cn` | source stamp CST | CN codes | the one library to take |
| Nikkei Asia RSS | none | `asia.nikkei.com/rss/feed/nar` | pubDate | no | |

## 3. Open-source aggregation + local-LLM projects (ingestion separable from LLM?)
- AI4Finance FinGPT / FinRobot (FinNLP pipeline) — yes, separable.
- virattt/ai-hedge-fund (61.8k★) — news via Financial Datasets API + Tavily; pluggable agent, separable.
- TauricResearch/TradingAgents — News Analyst + Sentiment Analyst pull headlines/StockTwits/Reddit; separable.
- OpenBB Platform — pluggable news providers (Tiingo/Polygon/yfinance free-tier); the abstraction to copy.
- news-please / newscatcher / FinNews (`scaratozzolo/FinNews`) — crawler/RSS layers with no LLM coupling.

## 4. Hiring / job postings as alternative data
Free, legal: public ATS JSON — `boards.greenhouse.io/{company}`, `jobs.lever.co/{company}`,
`jobs.ashbyhq.com/{company}` (no key, no login); Workday needs per-tenant career-site scraping.
LinkedIn scraping violates its ToS — excluded. Revelio Labs (paid / WRDS academic) is the reference dataset.

Evidence:
1. Kothari & O'Doherty (2023), *Job postings and aggregate stock returns*, J. Financial Markets —
   postings/employment ratio predicts the equity premium; 1 sd → **+6.60% next-month annualised excess**.
   doi:10.1016/j.finmar.2023.100804
2. Kuehn, Simutin & Wang (2017), *A Labor Capital Asset Pricing Model*, J. Finance 72(5) — **6%/yr**
   decile spread (t≈3.66) on labour-market-tightness loadings. doi:10.1111/jofi.12504
3. Belo, Lin & Bazdresch (2014), *Labor Hiring, Investment, and Stock Return Predictability in the Cross
   Section*, JPE 122(1) — hiring rate is a cross-sectional predictor.
4. Wolfe Research × RavenPack, *Alpha Insights from Global Job Postings Data* (industry, not peer-reviewed).

## 5. Free analyst coverage
yfinance `Ticker.recommendations`, `.analyst_price_targets` (unofficial); Finnhub `/stock/recommendation`
(4 months retained → snapshot daily); TipRanks-style scraping is ToS-prohibited.

## Ranked recommendation (coverage per dollar for a laptop-run nightly pull)
1. GDELT DOC 2.0 — the backbone crawler. 2. Google News RSS region/language sweep — Asia breadth
(coverage counts only). 3. Alpaca/Benzinga — the PIT-grade, ticker-tagged feed; finish the backfill.
4. AKShare for China before any bespoke HKEX/TDnet/KIND scraper. 5. SEC EDGAR + Finnhub snapshots as
structured complements. 6. Greenhouse/Lever/Ashby hiring scrape as a differentiated, legal, uncrowded
signal. 7. Borrow World Monitor's source-catalogue schema as our registry format. 8. Defer paid Asian
exchange APIs until (1)-(4)'s coverage gaps are measured.

**Two PIT pitfalls:** (a) timezone — GDELT/EDGAR/Google stamp in different conventions; normalise to UTC
at ingest and write our own `first_seen_utc`. (b) backfilled/edited articles — Google News RSS is index
state; NewsAPI/Marketaux/EODHD edit after publish; only a feed with a native first-publish stamp
(Alpaca `created_at`) or our own first-seen stamp is safe for a frozen panel.
