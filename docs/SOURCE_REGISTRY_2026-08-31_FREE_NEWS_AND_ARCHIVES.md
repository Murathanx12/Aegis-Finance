# SOURCE REGISTRY — 2026-08-31 — FREE NEWS, ARCHIVES, GLOBAL SENSORS, AND CRAWLER STACK

**Purpose:** replace the failed assumption that one paid news vendor must supply AEGIS's history. RavenPack is not entitled under the current HKU WRDS package. This registry is the acquisition plan for the world-sensor/EventCluster layer.

**Rule:** access is not the same as reuse rights. Every adapter records source, acquisition time, publication/effective time, terms/use class, content-vs-metadata rights, and whether raw text may be retained or used for model training. AEGIS can always retain its own derived facts/features where permitted, but it must not silently assume a public webpage grants redistribution/training rights.

---

## 0. The architecture

Do not run one expensive LLM per ticker. Run this funnel:

`SOURCE FEEDS / ARCHIVES -> URL + RAW RECEIPT -> EXTRACT -> NORMALIZE -> DUPLICATE/NEAR-DUPLICATE CLUSTER -> ENTITY LINK -> EventCluster -> causal reasoning -> CompanyState`

Store three layers separately:

1. **raw receipt** — URL/source, timestamps, hashes, acquisition metadata, permitted cached content;
2. **canonical event** — one economic fact/event even when 1,000 outlets repeat it;
3. **derived features** — novelty, surprise, causal exposure, evidence density, dissemination speed, etc.

This avoids the NVDA problem: 1,000 syndicated stories become one event with high corroboration, not 1,000 bullish votes.

---

# A. HIGHEST PRIORITY FREE HISTORICAL TEXT

## A1. FNSPID — financial news + prices, 1999–2023

**Repository:** `zGeneral/fnspid` / `Zdong104/FNSPID_Financial_News_Dataset`; mirrors on Hugging Face.

**Claimed scale by authors:** ~15.7M financial-news records + 29.7M prices, 4,775 companies, 1999–2023, four financial-news websites.

**Why AEGIS wants it:** this is immediately useful for the era replay, event-compression tests, analyst/context features, and long-horizon text-vs-price studies. It is the closest free public object to the historical financial-news lake Murat asked for.

**Important rights caveat:** repository text published 24 Jul 2025 says commercial/research rights were released, while the principal Hugging Face dataset card still displays CC BY-NC-4.0 / no commercial use. Treat that as a rights inconsistency. Fine for our research experiments; verify provenance/license before any commercial redistribution or production model training.

**PIT caveat:** publication timestamps and article-source history need auditing before any result is called point-in-time. Corporate actions/ticker mapping must use CRSP/Compustat history, not today's ticker.

**Action:** download a small shard first; measure timestamp completeness, duplicates, ticker survivorship, article-source mix and exact disk size after parquet compression. Do not ingest 30GB blindly.

## A2. SC454k — unusually valuable small-cap text dataset

**Dataset:** Hugging Face `nbettencourt/SC454k`.

~454k news articles/press releases about small-cap stocks, scraped from Nasdaq.com and paired with WRDS TAQ/MSEC market data. It contains article text, title, timestamp, symbol, sector/industry, related stocks, publication and multiple pre/post-event price observations.

**Why this may be more important than FNSPID for our hypothesis:** it directly attacks AEGIS's coverage asymmetry. Our live Benzinga corpus is famous-name heavy; SC454k is explicitly small-cap text and therefore a much better sandbox for `evidence density != opportunity`, event novelty and under-covered discovery.

**Action:** inspect date span, symbol survivorship, publisher mix and license/usage terms; build a PIT sample and run the same T13/T20 encoder on it before another mega-cap-heavy corpus test.

## A3. Common Crawl CC-NEWS — daily worldwide news archive, 2016→present

**Official dataset:** `crawl-data/CC-NEWS/`.

Common Crawl says CC-NEWS contains news from sites around the world, released in daily WARC files and organized by year/month from 2016 to date.

**Why:** free raw historical news breadth, no API subscription, excellent for historical backfill of domains/keywords/events that company APIs missed.

**Do NOT download everything.** Query/filter by domain/date/entity/theme and stream/process WARC subsets.

**Tools:** `fhamborg/news-please`, `commoncrawl/cdx_toolkit`, new official `commoncrawl/cc-downloader`.

## A4. Common Crawl MAIN — open web history, regularly available back through the 2010s/2008-era crawls

Use when CC-NEWS or a primary source lacks the page. Main crawl is broad web, not a clean newswire. Query the URL/CDX index before fetching bytes.

**Use cases:** old issuer IR pages, supplier/customer announcements, industry blogs, trade publications, local media, deleted/changed pages.

**PIT warning:** crawl timestamp != publication timestamp. Keep both and refuse a historical decision if publication/effective timing cannot be established.

## A5. Internet Archive / Wayback — targeted historical pages

Use through `commoncrawl/cdx_toolkit` for specific domains/URLs/dates, not as an excuse to bulk-copy the internet. Best for reconstructing old investor-relations pages, company press releases, supplier pages and local publications.

**PIT rule:** capture time bounds when the page was observable in the archive; it is not automatically its original publication time.

## A6. Media Cloud Online News Archive

Open-source media-research project; current API client is `mediacloud/api-client`. Media Cloud documents 200M+ searchable stories and collections across 100+ countries/languages. It also exposes Wayback-backed search for its media collections.

**Action:** register/test API key and measure actual historical depth and full-text availability for our target domains. Use as a discovery/index layer even if only metadata/snippets are retrievable.

## A7. FinSen

**Repo:** `EagleAdelaide/FinSen_Dataset`.

Research dataset described as 160k financial/economic news records over 2007–2023, with a 197-country collection project. Public repo currently says the freely supplied data is US-focused and asks researchers to contact the authors for the wider country set.

**Use:** small external benchmark for causal/sentiment calibration; not a replacement for the world lake.

---

# B. OPEN-SOURCE ACQUISITION / EXTRACTION REPOS

## B1. `fhamborg/news-please` — PRIORITY

Apache-licensed integrated news crawler/extractor. It can follow internal links, ingest RSS, fetch current or archived articles, process raw HTML/WARC, and includes a Common Crawl CC-NEWS workflow with publisher/date filters.

**Adopt:** use as the first historical-news extraction adapter rather than writing our own crawler from zero.

## B2. `commoncrawl/cdx_toolkit` — PRIORITY

Apache-licensed toolkit over Common Crawl and Internet Archive CDX indexes. It hides API differences, supports date/domain filters and can extract archived pages into WARC.

**Adopt:** targeted historical URL discovery and archive retrieval.

## B3. `commoncrawl/cc-downloader` — PRIORITY for large CC jobs

Official Common Crawl downloader. First stable release Aug 2026 includes Rust library + Python bindings, concurrent downloading and polite exponential-backoff/jitter.

**Adopt:** once a filtered WARC/WET path list exists. Do not use it to fetch entire crawls into Railway.

## B4. `ArchiveBox/ArchiveBox` — BUILD OUR OWN ARCHIVE FROM NOW FORWARD

Open-source self-hosted archiver. Can schedule RSS/URLs and stores HTML, article text, JSON, PDF, WARC, screenshots and metadata.

**AEGIS use:** every high-value URL that enters EventCluster gets archived (when rights/robots permit). In one year we should not be asking a vendor what AEGIS read on 31 Aug 2026; we should own the receipt.

Run archive storage outside the latency-sensitive trading loop; low-cost object storage is appropriate.

## B5. `trafilatura`

Fast article/main-text + metadata extraction to JSON/Markdown/XML/TXT. Good deterministic first extractor before spending LLM tokens.

## B6. `newspaper4k`

Maintained Newspaper fork; useful fallback extractor when Trafilatura/news-please fails. Respect robots/terms.

## B7. `webrecorder/pywb`

Lower-level WARC record/replay stack. Useful if AEGIS eventually needs its own replayable web archive service rather than only ArchiveBox files.

## B8. OpenBB

`OpenBB-finance/OpenBB` is valuable as a connector/reference layer, not as a magical source. Current providers include no-cost SEC/yfinance and optional connectors such as Biztoc, Finviz, Seeking Alpha and WSJ. A connector existing does **not** mean historical content is freely licensed; probe each source separately.

## B9. AI4Finance FinNLP / FinGPT

`AI4Finance-Foundation/FinNLP` is specifically an internet-scale financial-data connector reference. It contains/adapts Yahoo/Finnhub-style US news, Sina/Eastmoney/CCTV China news and social-source pipelines. FinGPT has news/fundamental retrieval examples.

**AEGIS use:** borrow adapters/source lists and tests, especially China/Asia. Do not assume every old scraper still works or is allowed under current source terms.

---

# C. LIVE + HISTORICAL GLOBAL WORLD SENSORS

## C1. GDELT — PRIORITY

World-scale event/news/GKG data, multilingual machine translation, 15-minute updates. Use for geopolitical events, policy, protests, conflict, supply-chain disruptions, company/entity mentions, location and narrative diffusion.

**AEGIS role:** global discovery sensor and Asia-before-US-open lead detector. Do not treat GDELT tone or event counts as ready-made alpha; cluster/verify events first.

## C2. EDGAR / SEC — PRIORITY, whole US market

Official APIs require no API key for submissions/XBRL; full-text search covers >20 years and EDGAR has real-time latest filings/RSS.

**Ingest first:** 8-K + exhibits, 10-Q, 10-K, 6-K/20-F, Form 4, SC 13D/G, tender/M&A forms, registration/prospectus changes.

This is the most important cure for `no media coverage = no company information`.

## C3. Federal Register / GovInfo bulk data

Official US policy/regulatory text. Use bulk XML/structured data rather than news articles when the market-moving fact is a rule, sanction, tariff, export restriction, agency notice or procurement regime change.

## C4. USAspending

Official API; endpoints currently require no authorization. Government contracts/grants/obligations can become company/industry demand signals.

Build award-recipient/entity mapping and `award_value / company_revenue` rather than raw award count.

## C5. FDA / openFDA

Public APIs/downloads for Drugs@FDA, shortages, labels, adverse events, recalls, devices, approvals/clearances. Some datasets reach back to 2002/2004; bulk JSON downloads exist.

For biotech/medtech this is a first-class event source, not a news annotation.

## C6. ClinicalTrials.gov API v2

Trials, status, endpoints, sponsors, phase and changes. Use to create dated clinical-catalyst/state transitions and link sponsor/asset/company.

## C7. FRED + ALFRED

ALFRED preserves real-time vintages of macro releases and later revisions. This is critical: backtests should see the unemployment/CPI/GDP value actually known then, not today's revised history.

## C8. US Census International Trade API

Monthly detailed trade from Jan 2010→present. Useful for supply-chain demand, country/product flows, tariff substitution and physical bottlenecks.

## C9. World Bank Indicators

No authentication; nearly 16k time series across 45+ databases, many >50 years. Useful slow macro/country-state features, not intraday signals.

---

# D. ASIA-FIRST SOURCES

## D1. HKEX RSS — PRIORITY for HK/China-linked information

Official feeds for regulatory announcements, news releases, market communications and rule/listing updates.

## D2. Korea OpenDART

Official Korean disclosure API. Original disclosure documents can be downloaded as XML; major disclosures and financial information are structured. Requires a free authentication key.

## D3. Japan EDINET API v2

Official FSA filing API; API v2 docs updated Jun 2026 and EDINET code list updated Aug 2026. Requires an issued API key. Use for Japanese issuer filings and text, not as a general Japanese news feed.

## D4. China — AKShare + primary endpoints

`akfamily/akshare` has adapters for Eastmoney stock news and many Chinese market/macroeconomic sources; `stock_news_em` returns recent company news with title/content/time/source/link. FinNLP also contains Sina/Eastmoney/CCTV connectors.

Use these as **adapter references** and keep upstream URL/source provenance. Some public-page adapters are brittle and source terms can change.

Priority primary/official Chinese sources to map: CNINFO disclosures, exchange announcements, ministries/NDRC/MIIT/MOFCOM/customs, company IR, plus GDELT/local-language news.

## D5. Cross-country lead feature

Every event gets `information_region` and `first_seen_utc`. A US stock can receive a feature from Korean/Japanese/Chinese information before US media covers it. This is one of AEGIS's explicit T21 experiments.

---

# E. SOCIAL / COMMUNITY SIGNALS

Social data is a sensor for **attention, disagreement, narrative diffusion and retail positioning**, not a fact source.

## E1. Bluesky / AT Protocol — PRIORITY FOR FORWARD COLLECTION

AT Protocol firehose is publicly connectable without authentication; public AppView endpoints are also available. This is a clean way to start an append-only social-attention dataset now.

Store derived ticker/theme counts, velocity, unique-author counts, link-domain diversity, disagreement and bot/spam indicators. Retain raw content only under a documented policy.

## E2. Hacker News official API

Public near-real-time API; documentation currently states no rate limit. Particularly useful for developer/AI/software/security/semiconductor narrative emergence rather than broad retail sentiment.

## E3. StockNet historical Twitter benchmark

Public GitHub dataset has tweets + Yahoo prices for 88 stocks in 2014–2016. Small, but useful as a reproducible historical social-text benchmark for the fantasy/context pipeline.

## E4. X / Twitter

Official full-archive search reaches back to Mar 2006 but is pay-per-use/Enterprise, not free. Recent search is available to developers. Do **not** make unofficial Twitter scrapers a foundational dependency; they are fragile and may violate access rules.

Possible cheap experiment: use historical **counts** rather than raw posts for selected tickers/themes if API pricing is tolerable; then buy raw full-archive retrieval only if the count/disagreement signal merits it.

## E5. Reddit

Current Reddit Data API/Developer terms do not grant blanket rights to use user content to train AI/ML; explicit permission is required. Do not build the future NN by scraping Reddit raw text. If approved access is obtained, use permitted aggregate/derived attention features with deletion/compliance handling.

## E6. Stocktwits

Official developer site currently says new application registrations are paused, and current terms prohibit unauthorized scraping. Do not build a scraper workaround. Revisit if approved API access becomes available.

---

# F. FREE / FREEMIUM API PROBES — USE AS SUPPLEMENTS, NOT THE FOUNDATION

## F1. Finnhub

Current docs list company-news free tier as one year of history for North American companies. We already use it; its outage/coverage behavior means it must remain one sensor, not the sole tracker truth.

## F2. Alpha Vantage NEWS_SENTIMENT

Supports historical `time_from/time_to`, ticker/topic filters and up to 1,000 results per response, with a free API key. Probe the actual free-tier historical depth/rate before depending on it.

## F3. Media Cloud

Free/research-oriented API key; broad source collections and 200M+ story archive. Probe actual current full-text/history coverage.

## F4. Event Registry

Offers trial/free access and historical search but historical queries consume tokens. Useful for evaluation/coverage comparison, not assumed free bulk history.

## F5. FinancialNewsAPI / NewsFilter

Open-source Python client advertises >50M searchable articles, real-time stream, historical search and sources including mainstream financial news plus SEC/FDA/contracts/patents. It offers a free API key; quotas/licensing/pricing must be measured before any claim that the archive is free.

This is a good **coverage benchmark** against our free stack: query 100 random tracker names and compare unique events/source families.

## F6. NewsAPI / NewsData / Mediastack / Currents

Useful free-tier probes for current/recent breadth, but historical access is heavily limited or paid. Do not spend engineering time treating them as the 2000→present solution.

---

# G. DATASETS / REPOS TO TEST, NOT IMMEDIATELY TRUST

- `Brianferrell787/financial-news-multisource` on Hugging Face: aggregates FNSPID plus multiple historical headline datasets. Useful index/benchmark; provenance/license must be checked per subset.
- NIFTY financial-headline datasets: useful LLM benchmark/dedup examples, not whole-market history.
- FinGPT Dow30/news datasets: useful pipeline/reference, too narrow for discovery.
- Any GitHub repo that republishes Reuters/WSJ/Bloomberg full text: **do not ingest merely because it is public on GitHub**. Repository availability does not create content rights.

---

# H. THE COLLECTION STACK TO BUILD

## H1. `source_registry.json`

One row per adapter:

`source_id, family, regions, languages, first_date, typical_lag, update_frequency, content_type, full_text_available, auth, rate_limit, expected_cost, use_rights_class, PIT_quality, entity_coverage, adapter, health, last_success_at`.

## H2. `raw_observation`

`source_id, source_item_id, url, discovered_at, fetched_at, published_at, effective_at, raw_hash, content_hash, language, title, permitted_body_pointer, extraction_method, extraction_confidence`.

## H3. Dedup before LLM

Exact: URL normalization + content hash.

Near-duplicate: title/body MinHash/SimHash/embedding; time/entity constrained.

Event-level: semantic cluster over facts/entities/time. Keep `source_count` and `independent_source_count` separately.

## H4. Entity linking

Map company aliases, former tickers, products, executives, suppliers, customers, geographies, government agencies and assets to stable IDs. Never join old text on today's ticker only.

## H5. LLM numerical compiler

Only after deterministic reduction. For each EventCluster produce the active roadmap's fields: surprise, demand/supply delta, causal driver/hop, magnitude, evidence density, already-priced proxy, confidence, and horizons.

Use provider disagreement as a feature: if DeepSeek and NVIDIA disagree strongly on direction/causal path, confidence falls; the disagreement itself becomes T25 data.

---

# I. DOWNLOAD / BUILD ORDER

### Today / competition week

1. Finish current tracker/night chain and portfolio seals first; do not interrupt it for scraping installs.
2. SC454k sample + FNSPID sample: validate PIT/provenance and run encoder coverage.
3. `news-please` + CC-NEWS proof: one month, selected financial/local-news domains, stream into `raw_observation`.
4. GDELT live + EDGAR live adapters into EventCluster v0.
5. ArchiveBox forward preservation for URLs AEGIS actually used.
6. HKEX/OpenDART/EDINET source stubs + one live receipt each.
7. Bluesky firehose-derived attention counters (no trading authority).

### This week after the first proof

8. Expand CC-NEWS 2016→present by domain/theme in chunks.
9. Use `cdx_toolkit` for targeted 2008–2016/older IR and trade-publication recovery.
10. Federal Register/USAspending/FDA/ClinicalTrials/Census/ALFRED structured event lanes.
11. Media Cloud / Alpha Vantage / FinancialNewsAPI coverage bake-off against the free source mesh.
12. Only then decide whether any paid archive closes a measured residual gap worth its cost.

---

# J. SUCCESS METRICS

Do not report “we scraped 5 million articles.” Report:

- unique canonical events/day and historical month;
- % tracker names with at least one non-price observation;
- coverage by analyst-count bucket, market cap, sector and dollar-volume bucket;
- independent-source count distribution;
- duplicate compression ratio;
- publication/effective timestamp completeness;
- entity-link precision sample;
- event-type coverage;
- Asia/local-language events first seen before US sources;
- opportunity recall on later winners;
- incremental rank/calibration/P&L vs existing corpus;
- dollars and compute per useful canonical event.

The goal is not the largest archive. It is the highest-value, point-in-time world state AEGIS can transform into repeatable decisions.