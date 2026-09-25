# Small/undiscovered OSS repos & datasets for Aegis Finance
Compiled 2026-09-25. Method: 4 parallel search agents, `gh search repos` (GitHub API,
gh CLI 2.97.0) + WebSearch (unavailable for 2 of 4 agents — session budget exhausted
before they reached it; see note) + WebFetch of READMEs for verification + Hugging Face
hub search for datasets. 60+ distinct query strings run across the team (listed in full
in RESEARCH CUE below). Excluded per instructions: TradingAgents, ai-hedge-fund, FinRL,
FinGPT, qlib, FinMem, DMulajkar/Quantgress, LSEG RevisionsMomentum sample,
luweihai/CARAG, kamendula/AlphaAgent, effective-p/FinAgent, xt2201/finmem, StockBench,
Sunny-1991/13F-Tracker, kylemcdonald/ews, hiring-lab/job_postings_tracker.

Scoring convention used below: stars, last-push date, license, PIT-safety verdict
(YES / NO / UNCLEAR — verified by reading README/code where possible, not assumed),
quality signal, and Aegis takeaway + best-guess module.

NOTE ON CONFIDENCE: none of this was cloned locally or run; every "PIT-safe" or
"has tests" verdict is a README/code-skim by a subagent, not a verified receipt.
Before taking code or a claimed result, re-verify per Aegis's own standing rule
("a check that did not run is not a check that passed").

---

## 1. Congress / insider / 13F / SEC filings (module: congress_trades, investigator_agent, event_extraction)

### austin-starks/sec-ownership-disclosures — STRONGEST FIND OF THE RUN
https://github.com/austin-starks/sec-ownership-disclosures
- 1 star, pushed 2026-09-24, MIT, TypeScript/Node, npm package, CI green.
- Builds a local SEC ownership lake from EDGAR: Form 3/4/5 insider transactions
  (10,045,180 legs, 2006Q1-2026Q2) + 13F institutional holdings (124,012,468
  legs, 2013Q2-present).
- Data source: SEC EDGAR. PIT-safety: YES by design — explicitly stores "when
  each filing could first have been known" as a first-class column (most
  datasets omit this). Has a receipts/resume mechanism and an audit pass that
  re-parses archives rather than trusting its own counters.
- Quality: real scale, CI green, transparent about a real gotcha — raw "insider
  buying" mixes open-market purchases (894K) with grants/exercises (4.4M) and
  the repo flags the distinction explicitly.
- Aegis takeaway: take the PIT-column design and the grant-vs-open-market split
  directly into investigator_agent / insider_opportunistic calibration.

### austin-starks/congressional-disclosures
https://github.com/austin-starks/congressional-disclosures
- 5 stars, pushed 2026-09-25 (today), MIT, TypeScript/Node, CI green, npm
  package. Same author as above.
- Resumable, sharded pipeline for House Clerk + Senate eFD periodic transaction
  reports: downloads originals, decrypts House PDFs, OCRs scans, cross-checks
  with independent model reads, reconciles disagreements, writes to SQLite.
- PIT-safe: YES, disclosure-date aware by design. Production-grade rigor
  (receipts, audits, resumability) — backs the author's live NexusTrade product.
- Aegis takeaway: more robust ingestion pattern than most congress-trade
  scrapers found; overlaps event_extraction / new congress-trade collector.
- Companion HF dataset: austin-starks/congressional-stock-trades — 100K-1M rows,
  parquet, explicitly tagged "point-in-time", updated 2026-09-25 (today). Best
  PIT-labeled dataset found in this whole search.

### Builder106/capitol-alpha
https://github.com/Builder106/capitol-alpha
- 3 stars, pushed 2026-09-23, MIT, Python/Jupyter, CI badge, live findings site
  (capitolalpha.vercel.app).
- College (Wesleyan) semester project: Playwright-scrapes House+Senate
  disclosures, normalizes 16,203 trades (2020-2024), computes Jensen's alpha
  over 30/90/180-day holds vs SPY. Headline finding: politician purchases beat
  SPY by +2.58% over 90 days (p<0.05) — a testable, citable prior, not a
  proprietary claim.
- PIT-safety: UNCLEAR whether it separates transaction-date vs disclosure-date
  in the return calc — verify before reusing the finding.
- Aegis takeaway: replicate this matched-control comparison on Aegis's own
  PIT-correct congressional feed as a sanity check (investigator_agent).

### crnicholson/capitol-api
https://github.com/crnicholson/capitol-api
- 9 stars, pushed 2026-07-05, license unclear.
- Free, self-hostable API for congressional stock trades (House PTRs
  2018-2026), incremental parsing from House Clerk filings +
  unitedstates.github.io legislator DB + Yahoo Finance prices; resumable,
  queryable while streaming. No tests found.
- Aegis takeaway: lightweight alternative/complement; small enough to read
  end-to-end in an hour. Overlaps web_events / analyst_intelligence.

### timothycarambat/senate-stock-watcher-data
https://github.com/timothycarambat/senate-stock-watcher-data
- 100 stars, originally 2021 but data updated 2026-09-10 (still refreshing), no
  explicit license.
- Plain JSON mirror of Senate STOCK Act disclosures (efdsearch.senate.gov), same
  data behind senatestockwatcher.com. Data-only, no code/tests.
- Aegis takeaway: free, currently-live alternative feed for congress_trades.

### kovagent/congresskit (+ sibling kovagent/fundskit)
https://github.com/kovagent/congresskit
- 0 stars, pushed 2026-09-24 (freshest-updated repo in the whole search),
  Apache-2.0, Rust.
- STOCK Act periodic transaction reports bundled as Parquet, nightly refresh, no
  API key needed. Sibling fundskit does the same for 13F holdings.
- Rust, not directly reusable in Aegis's Python stack, but the
  vendored-parquet + nightly-refresh + zero-API-key design is worth stealing
  conceptually for Aegis's own stale-funnel problem (echoes the
  FUNNEL_STALE_DAYS fix already in CLAUDE.md).

### alexislowys/insider-tracker
https://github.com/alexislowys/insider-tracker
- 0 stars, pushed 2026-09-19 (days old), MIT, Next.js + Postgres, Vercel Cron.
- Ingests SEC EDGAR daily index -> parses Form 4 XML within ~1 min of filing,
  idempotent reingestion window, detects cluster-buys (2+ insiders, 14-day
  window), scores each buy's market-adjusted return vs SPY over the holding
  period. Has CI badge + test scripts (test-parser.ts, stats.ts).
- PIT-safety: not explicit, but pipeline is index-date driven.
- Aegis takeaway: the SPY-relative excess-return scoring of insider clusters is
  exactly the "winner vs matched loser" pattern the mission wants — take the
  metric design (investigator_agent).

### Pdong19/edgar-scanner
https://github.com/Pdong19/edgar-scanner
- 0 stars, pushed 2026-09-19, MIT.
- Autonomous small-cap scanner: extracts "monopoly language" from 10-Ks, 12-dim
  explicit/auditable threshold scoring (not ML), cross-validates claims against
  USAspending.gov federal contracts, tracks Form 4 insider buys via SEC atom
  feed, yfinance for market data.
- Quality: 285 tests, GitHub Actions CI on 3.10/3.11/3.12, Ruff lint — one of
  the best-tested repos found in the whole search.
- PIT-safety: UNCLEAR — pulls "latest 10-K", no explicit filed-date discipline
  mentioned.
- Aegis takeaway: the multi-source cross-validation idea (10-K claim vs
  USAspending record) is directly reusable in investigator_agent /
  event_extraction.

### jaablon/buried-events-parser
https://github.com/jaablon/buried-events-parser
- 1 star, pushed 2026-06-19 (updated 2026-07-29), MIT.
- Pure-Python regex classifier flagging 8-Ks where filers mis-bucket a material
  event under generic Item 8.01 instead of a specific code (e.g. "ransomware"
  text under 8.01 -> suspected undisclosed 1.05 cyber incident). Takes a
  filed_at timestamp param. No tests found.
- Aegis takeaway: cheap, no-LLM idea worth stealing outright — a
  keyword-to-item-code mismatch detector as a pre-filter before spending LLM
  budget on 8-Ks (event_extraction).

### ryansmccoy/py-sec-edgar
https://github.com/ryansmccoy/py-sec-edgar
- 128 stars (under the 300 cutoff but the largest kept), pushed 2026-09-22,
  license "Other".
- Downloads/parses 10-K/10-Q/13-D/S-1/8-K etc. from EDGAR into
  structured/unstructured form. Established, actively maintained infra rather
  than a hidden gem, but small and directly useful as an EDGAR-fetch backbone
  (event_extraction infra).

### stefanoamorelli/sec-edgar-toolkit
https://github.com/stefanoamorelli/sec-edgar-toolkit
- 38 stars, pushed 2026-08-18, AGPL-3.0 (viral license — flag before vendoring
  code), Python+TS, CI both langs, Codecov, Docker.
- XBRL company-facts/segment extraction, "amendment-aware filing lookups," date
  range filtering framed as enabling point-in-time analysis.
- Aegis takeaway: most PIT-conscious XBRL/amendment handling design found —
  read for ideas, don't vendor the code given AGPL (event_extraction).

### Honorable mention (design reference only, archived)
gBlaku/edgar-ai-pivot-monitor — EDGAR full-text-search -> Claude-scored 8-K
alert pipeline (excerpt-before-LLM, confidence 1-10, Discord/Slack/ntfy). Good
architecture idea; repo is archived/unmaintained, so reference only.

---

## 2. Prediction markets / event resolution (module: prediction_markets, event_extraction)

### JDSource/clearmarket
https://github.com/JDSource/clearmarket
- 3 stars, pushed 2026-09-25 (today), MIT.
- "Structured intelligence for prediction markets": normalizes Polymarket +
  Kalshi, assigns Resolution Clarity Grades, cross-platform claim mapping,
  daily signal wire. Has a tests/ dir. Catalyst coverage is macro/Fed/
  geopolitical, not biotech-specific.
- Aegis takeaway: the Resolution Clarity Grade concept (how authoritative/
  ambiguous a claimed catalyst outcome is) is transferable to scoring PDUFA/8-K
  "did it actually happen" events even though the code isn't biotech-focused.
  New module candidate: event_resolution_grading.

---

## 3. Biotech / clinical-trial catalysts (module: new — biotech_catalysts)

### cyanheads/clinicaltrialsgov-mcp-server
https://github.com/cyanheads/clinicaltrialsgov-mcp-server
- 95 stars, pushed 2026-09-22, Apache-2.0.
- MCP server wrapping the ClinicalTrials.gov API v2 for trial search,
  study-detail retrieval, patient-trial matching. General-purpose, not
  stock-specific, but well-built and current.
- Aegis takeaway: good infra to sit underneath a PDUFA/trial-outcome catalyst
  tracker instead of hand-rolling the CT.gov client.

### HF dataset: GooseWithStories/clinical-trial-outcomes-2020plus
https://huggingface.co/datasets/GooseWithStories/clinical-trial-outcomes-2020plus
- CC0-1.0, updated 2026-09-11. 124,790 normalized endpoints across 14,170
  studies (2020+) with posted results, snapshotted from CT.gov API v2 on
  2026-09-08. Rich schema: endpoint canonicalization, direction, timeframe/
  horizon days, phase, sponsor class, enrollment, dates.
- Built with an MIT-licensed "ctgov" normalizer the author says is re-runnable
  against the live registry (find/reuse that normalizer if it surfaces on
  GitHub/PyPI).
- Aegis takeaway: close to a ready-made PIT-able panel of trial outcomes; still
  needs linkage to tickers/PDUFA dates.

### HF dataset: 3rdSon/clinical-trial-outcomes-predictions
https://huggingface.co/datasets/3rdSon/clinical-trial-outcomes-predictions
- Apache-2.0, updated 2026-02-19. 1,366 binary forecasting questions on
  2023-2024 trials ("will X meet endpoints / get FDA approval") with verified
  outcomes, built via Lightning Rod Labs' "Future-as-Label" auto-labeling.
- Small, LLM-generated question framing — treat as a forecast-calibration toy
  set, not ground truth.
- Aegis takeaway: usable as an out-of-sample forecast-calibration benchmark for
  a catalyst-prediction model.

### ebachUTSA/DeceptionClassifier
https://github.com/ebachUTSA/DeceptionClassifier
- 6 stars, pushed 2025-09-19, academic/non-commercial license (ASL,
  LIWC-gated) — real constraint, blocks direct reuse in a for-profit/public
  tool.
- Classifier (sklearn + PyTorch variants) detecting deceptive CEO language in
  earnings-call transcripts using LIWC-2015 linguistic features, built for an
  academic study on cognitive-load-induced deception. Not stock-return-tested.
- Aegis takeaway: closest thing found to "earnings call QA evasiveness" —
  useful as a feature-engineering idea (LIWC deception cues) even if the
  trained model can't be redistributed. New module candidate:
  management_deception.

---

## 4. Multi-source financial data infra (module: analyst_intelligence / event_extraction / web_events)

### daniel3303/Equibles
https://github.com/daniel3303/Equibles
- 231 stars, pushed 2026-09-25 (today), AGPL-3.0.
- Self-hosted MCP financial-data server: SEC filings/XBRL, 13F holdings,
  insider + congressional trades, FINRA short interest, FRED, CFTC/CBOE, daily
  prices — 62 tools. Cloud tier (paid) adds earnings-call transcripts,
  guidance, options chains. Sources: SEC EDGAR/XBRL, FINRA, FRED, CFTC, CBOE,
  Yahoo Finance, USAspending.gov, FDA.gov.
- PIT-safety: not documented — treat as unverified.
- Quality: CI (CodeQL, codecov badges), pre-commit config, test directory,
  4,505 commits — real, active infra, largest/most complete find of the run
  (also the only one near the 300-star soft cap, at 231).
- Aegis takeaway: reference for which free sources exist and how to normalize
  them; check its insider/congressional-trade and FDA.gov collectors before
  rebuilding from scratch. AGPL — read for ideas / API surface, be careful
  about vendoring code directly.

### jasonpalmer1/wafergraph-mcp
https://github.com/jasonpalmer1/wafergraph-mcp
- 0 stars, pushed 2026-08-31, license "Other".
- Remote MCP server (Cloudflare Workers, no auth) over wafergraph.com's
  dataset: 565 semiconductor/AI-supply-chain companies, supplier/customer
  graph, 74-deal M&A corpus, sourced from SEC/Wikidata/Wikipedia/GLEIF with
  per-field attribution. No per-edge relationship dates (a real gap for PIT
  use).
- Aegis takeaway: small, genuinely novel dataset-as-a-service. New module
  candidate: supply_chain_graph — pull the raw data/schema rather than the
  code.

---

## 5. Point-in-time fundamentals / survivorship-bias-free / risk models (module: new — alt_data_research, adjacent to xs_ranker)

### juanmicl/quant-market-data-forensics
https://github.com/juanmicl/quant-market-data-forensics
- 6 stars, pushed 2026-08-23, MIT.
- 91-module (~32k LOC) PIT research platform on Sharadar (SEP/SFP/SF1/SF2/SF3)
  + FRED vintages, TimescaleDB, purged walk-forward XGBoost/CVXPY.
- PIT-safe: YES by design (filing dates, release dates, revision-aware macro;
  runtime guards reject lookahead). Has CI-grade validators (exit codes) and a
  lookahead-leakage feature-lag test.
- Quality signal that matters most here: it found and killed its own strategy
  — a unit-scale bug had inflated alpha 9-556x, and log-return convexity was
  overstated by ~half sigma squared. This is exactly the "study losers as hard
  as winners" / self-audit ethos already in CLAUDE.md.
- Aegis takeaway: take the bias-detection instrumentation and PIT-guard
  pattern directly. New module candidate: alt_data_research_forensics.

### tigersunmj/sharadar-risk-model
https://github.com/tigersunmj/sharadar-risk-model
- 21 stars, pushed 2026-08-12, no license file.
- Barra-style US equity risk model (19 style + 48 industry factors, daily
  cross-sectional regression) on Sharadar SEP/SF1/DAILY/TICKERS.
- PIT-safe: YES — merges fundamentals on SEC filing date, not report period,
  explicitly to avoid a ~2-month leak. Bias-tested across 846 days; no CI
  pipeline, manual testing only. Requires a paid Sharadar subscription.
- Aegis takeaway: risk-model methodology/code structure, adjacent to
  xs_ranker.

### samratsaini275-cyber/Point-in-time-fundamentals-
https://github.com/samratsaini275-cyber/Point-in-time-fundamentals-
- 2 stars, pushed 2026-08-28, license unclear.
- Survivorship-bias-free, bitemporal SEC EDGAR XBRL store ("never returns a
  number that wasn't publicly known as of a given date"), Streamlit GUI per
  filer. No stated tests/CI.
- Aegis takeaway: check its bitemporal schema design against Aegis's own
  derive_q4 XBRL-recovery work (59,296 rows) — possible cross-validation of
  gap logic.

### younghwan91/portfolio-research
https://github.com/younghwan91/portfolio-research
- 2 stars, pushed 2026-09-21, MIT.
- Korean-language US-equity factor engine: PIT + survivorship-corrected data,
  walk-forward gated on Deflated Sharpe Ratio + Probability of Backtest
  Overfitting (PBO), and publishes rejected variants alongside adopted ones.
- Aegis takeaway: take the DSR/PBO gating code as a second opinion on Aegis's
  own promotion gate (farm gating logic).

### alphaville76/sharadar_db_bundle
https://github.com/alphaville76/sharadar_db_bundle
- 19 stars, pushed 2026-09-19, license unclear.
- Zipline data bundle for Sharadar (SEP/SFP/SF1) via Nasdaq Data Link API,
  SQL-backed for incremental updates instead of bcolz.
- PIT-safety: NOT documented — makes no lookahead-protection claims.
- Aegis takeaway: incremental-ingestion pattern only; don't trust any PIT
  claim since it makes none.

### Dropped after inspection (do not pursue)
- BlackFalconData-org/delisted-stocks-list — looked strong (36k delisted
  stocks, SEC EDGAR daily) but is README-only, no code/data/license — a
  lead-gen page for a paid Apify actor.
- bsommerfeld/wsbg-terminal (22 stars) — WSB-community dashboard app, more
  entertainment than research tooling.
- KayhanB21/sports_betting_handle_prediction — no usable description/README.

---

## 6. Alternative data — hiring / social attention (module: web_events, new — alt_data_hiring / alt_data_reddit_attention)

### groundtruthtools/ats-jobs-mcp
https://github.com/groundtruthtools/ats-jobs-mcp
- 0 stars, pushed 2026-09-13, MIT, has tests/test_core_parity.py.
- MCP server reading current job postings directly from company ATS APIs
  (Greenhouse 4,168 boards, Ashby 3,311, partial Lever) — no scraping, no
  keys, 7,479 company boards mapped and verified against vendor APIs. Salary
  parsing, PII stripping.
- Caveat: current-only, not historical — you'd need to snapshot it yourself
  for a time series.
- Aegis takeaway: directly matches the VISION file's "hiring signal via
  Greenhouse/Lever/Ashby" build item. Take the board-mapping list + parsing
  code, wire into a daily snapshot job.

### RezaSoleymanifar/ape-tape
https://github.com/RezaSoleymanifar/ape-tape
- 0 stars, pushed 2026-08-07, MIT.
- Archives ApeWisdom (Reddit ticker-mention/sentiment aggregator) hourly
  across 9 finance subreddits via GitHub Actions cron; stores raw gzipped
  snapshots + derived monthly stats (delta_24h, rank_change, churn).
- PIT-safety: genuinely point-in-time (append-only live capture, not
  backfilled). No test framework; author is transparent about missed
  collection hours.
- Aegis takeaway: collector pattern for a Reddit-attention time series Aegis
  doesn't currently have.

---

## 7. LLM-agent / forecasting benchmarks (module: llm_portfolio, investigator_agent)

### QF-Bench/QuantitativeFinance-Bench
https://github.com/QF-Bench/QuantitativeFinance-Bench
- 60 stars, license NOASSERTION (none explicit), pushed 2026-09-04, 89 open
  issues (active).
- Benchmark built on Harbor (sandboxed Docker agent-eval framework): evaluates
  LLM agents doing real quant tasks — stateful environments, dirty data,
  runtime debugging, verifiable numeric outputs — inside an air-gapped
  sandbox. Ships an "oracle" agent (no LLM) to verify tasks are correctly
  authored.
- Aegis takeaway: template for grading Aegis's own LLM-driven investigator/
  analyst calls against verifiable numeric ground truth instead of vibes.

### hclaile/ProFinAgent
https://github.com/hclaile/ProFinAgent
- 0 stars, no license file, pushed 2026-05-28, Python.
- Official implementation for an ICML'2026 paper, "Towards Professional-Grade
  Financial Agents: Benchmarking, Tooling, Structured Reasoning." Two agent
  backends (local/API), inline MCP-style tool server, configurable
  tool-selection rules. Companion HF dataset: huangchenglaile/ProFinR.
- Quality: paper-backed but thin community validation (0 stars, no license —
  check terms before reuse).
- Aegis takeaway: the tool-registry + tool-selection-rules design pattern is
  the useful part even if the benchmark data isn't adopted wholesale.

### zhangsensen/openclaw-finance
https://github.com/zhangsensen/openclaw-finance
- 3 stars, pushed 2026-09-08, MIT, mostly shell/config over OpenClaw agents.
- 4-7 specialized agents (PM/analyst/programmer/skeptic) collaborating on
  financial research via OpenClaw, with a dedicated "skeptic" agent that
  challenges assumptions, heartbeat-based self-healing, full decision
  logging. Bilingual (EN/Chinese), used in a live Telegram workflow for US +
  A-share research. README itself cautions "verify current runtime status
  before relying on it operationally."
- Aegis takeaway: relevant precedent for a multi-persona / skeptic-role
  pattern (echoes "study losers as hard as winners" / matched-control
  instincts already in CLAUDE.md), and directly relevant since Murat runs
  OpenClaw locally.

### TheFutureEdge/ipulse-ai-options-alpha-agent
https://github.com/TheFutureEdge/ipulse-ai-options-alpha-agent
- 0 stars, MIT, pushed 2026-09-04, Python, 0 open issues.
- Inspectable, autonomous options-research + Alpaca paper-trading agent,
  framed explicitly PRODUCT_EXPERIMENT-shaped (paper only, inspectable
  decision trail) rather than a black-box bot — one of the few Alpaca-hackathon
  repos found that isn't a 10-minute vibe-coded clone.
- Aegis takeaway: audit-trail/inspectability pattern on options specifically,
  an area Aegis hasn't built out (llm_portfolio).

---

## 8. Other Hugging Face datasets found (not otherwise listed above)

| Dataset | License | Notes |
|---|---|---|
| emperor-mew/sec-filings | CC0 | Indexes every SEC filing by CIK/form/date incl. Form 4 and 13F; size unclear, worth a look given license. |
| kapilrao/SEC_filings_1994_2024 | none explicit | 10M-100M rows, EDGAR master-index metadata. |
| zorynthiq/zoryntiq-sec-filings | Apache-2.0 | Small (5,179 chunks), focused on recently-IPO'd/pre-IPO companies. |
| Rogersurf/earnings-call-transcripts | "other" (scraped, terms unclear) | 9.1K transcripts, 440MB parquet, ticker/quarter/year columns; verify redistribution terms before use beyond personal research. |

No usable HF results for: FDA approval calendar as a dataset, analyst price
targets, or "form 4 insider trading" as a direct HF query (Form 4 data was
only found via GitHub/austin-starks instead).

---

## Coverage gaps / dead ends worth knowing about

- Patent-to-stock-signal and government-contracts-to-ticker mapping are
  genuinely thin on GitHub. Multiple rephrasings (uspto patent assignee
  ticker, patent trading signal, federal register api companies, tariff
  impact stocks tracker) returned nothing usable. Pdong19/edgar-scanner's
  USAspending cross-check is the only real hit touching this space.
- App-downloads / app-store-ranking alt-data, sports-betting-handle data, and
  gambling-stock trackers: zero usable GitHub hits across many rephrasings.
  This is very likely a "the good stuff isn't open-sourced" gap (paid
  vendors: Sensor Tower, Apptopia) rather than a search-technique failure —
  worth trying arXiv/blog search instead of GitHub next time.
- IBES / StarMine / analyst-estimate-revisions as open source: nothing
  found — this data is proprietary (Refinitiv/LSEG) and nobody has
  open-sourced a usable substitute; the closest adjacent things are TipRanks
  wrappers (dropped for staleness, see below) and Equibles' cloud tier (paid).
- Bloomberg BQL/blpapi example repos: nothing small/useful found; these
  require a Bloomberg Terminal license so the OSS ecosystem around them is
  thin by construction.
- Humanoid-robot-supply-chain and quantum-computing-stock trackers: zero
  GitHub hits under any rephrasing tried. Likely exist as blog posts/gists/
  investor newsletters rather than indexed repos — try WebSearch, not
  gh search repos, next time.
- WebSearch tool was unavailable for 2 of the 4 research agents (session
  budget exhausted before they reached it) — all their discovery ran through
  gh search repos + Hugging Face hub search + WebFetch-verified READMEs
  only. This means GitHub/HF-indexed-only bias is real for those two
  branches (biotech/analyst and LLM-forecasting/misc); a rerun with working
  WebSearch would likely surface additional non-GitHub sources (blogs,
  gists, papers).
- Dropped for failing the 2025/2026 freshness bar (real last-commit dates
  found via `gh api`, despite promising descriptions): janlukasschroeder/
  tipranks-api-v2 (TipRanks price-target/sentiment wrapper, 100 stars, last
  commit 2022), rajdeep345/ECTSum (EMNLP 2022 transcript-summarization
  benchmark, 35 stars, 2024), cdubiel08/Earnings-Calls-NLP (76 stars, 2023).
  Worth revisiting as reference code if the freshness constraint is relaxed.

---

# RESEARCH CUE — reusable query list + rubric for a future session

## Scoring rubric (apply to every candidate before spending more than 5 minutes on it)
1. Stars < 300 (soft; note anything 300-1000 as "known, verify novelty"; drop
   >1000 outright — that's an NVDA-shaped source, not a hidden one).
2. Last commit/push < 12 months old — verify with
   `gh api repos/{owner}/{repo} --jq .pushed_at`, NOT the README date or
   stars-sort default (staleness traps: TipRanks/ECTSum/Earnings-Calls-NLP
   above all looked live until checked).
3. License compatible with the intended use (MIT/Apache/BSD/CC0 = safe to
   vendor; AGPL = read-for-ideas only, don't vendor; "no license"/NOASSERTION
   = treat as all-rights-reserved, ask before using; academic/non-commercial
   = ideas only).
4. PIT-safe — does it date data by filing/disclosure/knowledge date, or by
   report/event period? Read the code, don't trust a README claim. A repo
   that makes NO PIT claim at all is more honest than one that claims
   PIT-safety without showing the join key.
5. Has tests or a receipt-generating pipeline — CI badge, test directory, or
   at minimum an audit/validation script that produces a printed number. A
   repo with none of these is a prototype, not infra — still useful for the
   idea, never for the code unqualified.
6. Score = keep only if it clears 1+2+3; note 4+5 as quality tier (A =
   PIT-safe + tested, B = one of the two, C = neither — idea-only).

## Query list (60+, grouped)
Run via: `gh search repos "<query>" --sort=updated --limit 20 --json
fullName,description,stargazersCount,updatedAt,url,licenseInfo` — use
UNQUOTED multi-word queries when passing to gh (quoting the whole phrase
causes GitHub exact-phrase matching and false-empty results); verify real
pushed_at via `gh api repos/{owner}/{repo}` before trusting any staleness
claim.

Biotech / FDA / clinical catalysts:
1. pdufa calendar
2. fda approval calendar
3. clinicaltrials.gov api
4. ctgov python
5. biotech catalyst tracker
6. drug approval stock screener
7. fda advisory committee calendar

Analyst estimates / revisions / IBES:
8. analyst upgrades downgrades dataset
9. price target revisions point-in-time
10. earnings estimate revisions
11. IBES open source
12. StarMine (mostly noise — verify each hit manually)
13. analyst rating scraper language:python
14. consensus estimate history dataset

Earnings calls / guidance / management language:
15. earnings call transcript diff delta
16. earnings call transcripts dataset
17. management guidance tracking earnings
18. earnings call sentiment language:python
19. earnings call qa evasiveness
20. CEO deception detection earnings
21. 8-K guidance extraction

Congress / insider / institutional:
22. congress trades api
23. senate stock watcher
24. capitol trades scraper
25. house stock watcher
26. 13F parser xml
27. 13f institutional holdings python
28. form 4 insider realtime
29. form4 sec alert python
30. insider cluster buying tracker
31. congressional stock trades point-in-time

SEC filings infra:
32. 8-K parser sec
33. sec edgar full text search python
34. sec edgar xbrl point in time
35. edgar amendment aware filing

Supply chain / patents / gov contracts:
36. supply chain graph companies
37. customer supplier relationships dataset
38. sec 10-k customers extraction
39. patent company signal stock
40. uspto ticker mapping
41. uspto patent assignee ticker
42. government contracts usaspending ticker
43. usaspending python client
44. federal register api companies
45. federal register python client
46. tariff impact stocks tracker

Prediction markets:
47. kalshi api python
48. polymarket data python
49. prediction market arbitrage stocks
50. prediction market resolution grading

Alt-data (social / hiring / trends):
51. google trends stock prediction
52. wikipedia pageviews stock
53. reddit wallstreetbets scraper (unquoted "wallstreetbets" alone was more
    productive than the full phrase)
54. app downloads alternative data stock (dead end on GitHub — try
    arXiv/blogs)
55. job postings greenhouse company
56. ats jobs api ticker
57. sports betting handle data (dead end on GitHub — try arXiv/blogs)
58. gambling stocks tracker

Point-in-time / survivorship / risk:
59. point in time fundamentals (very productive — many near-duplicate repos,
    triage by stars+freshness)
60. survivorship bias free stocks
61. delisted stocks data
62. sharadar (very productive — most PIT-fundamentals hits trace back to
    Sharadar wrappers)
63. barra style risk model python
64. deflated sharpe ratio pbo python

LLM forecasting / agent benchmarks:
65. llm stock forecasting 2026 (bump year each session)
66. llm earnings call benchmark
67. financial agent benchmark 2026
68. brier score stock forecast
69. forecast ledger calibration trading
70. quantitative finance agent benchmark harbor
71. financial agent tool use benchmark

Bloomberg / niche terminals:
72. bloomberg trading challenge
73. bql python
74. blpapi examples

Thematic stock trackers:
75. humanoid robot supply chain stocks (dead end on GitHub — try
    blogs/newsletters)
76. quantum computing stocks tracker (dead end on GitHub — try
    blogs/newsletters)

Alpaca / OpenClaw:
77. alpaca paper trading agent 2026 (filter hard for freshness — most are
    hackathon one-shots)
78. openclaw finance

Hugging Face hub searches (repo_type=dataset unless noted):
79. earnings call transcripts
80. analyst price targets
81. FDA approval calendar
82. clinical trial outcomes
83. SEC filings
84. insider trading form 4
85. congressional stock trades
86. financial forecasting benchmark
87. point-in-time fundamentals
88. IBES analyst estimates
89. (repo_type=model) finance tool-use agent

arXiv (not yet run this session — do next):
90. "point-in-time" financial machine learning dataset
91. LLM earnings call analysis 2026
92. financial forecasting calibration LLM
93. congressional trading alpha
94. insider trading cluster detection machine learning
</content>
