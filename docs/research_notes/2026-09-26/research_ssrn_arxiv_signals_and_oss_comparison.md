# Research — SSRN/arXiv signal literature and OSS comparison (2026-09-26)

Scope handed to this session: find replicable academic signals (SSRN FEN /
arXiv q-fin / Semantic Scholar, 2019-2026) not already in the library, rank
the data sources their papers need that Aegis lacks, compare Aegis against the
"big name" OSS quant/trading-bot projects (deliberately excluded from
`docs/research_notes/2026-09-25/research_repos.md`, which covers small/
undiscovered repos instead), and produce a tonight-registrable shortlist.

**Licence: `PRODUCT_EXPERIMENT` exploration.** Nothing here is a
`RESEARCH_CLAIM`. Every claimed number below is the SOURCE's own figure,
never Aegis-measured, per `strategy_library.ClaimIsNotEvidence`.

**Method and its limits, stated plainly:** SSRN (`ssrn.com`) returns HTTP 403
to a plain `curl`/non-browser fetch — confirmed this session, not assumed —
so no SSRN abstract page was live-fetched. The arXiv API
(`export.arxiv.org/api/query`) and GitHub's REST API worked directly over
plain HTTP and every arXiv id/date/abstract-excerpt below **was fetched this
session** (marked `[V-ARXIV]`). Semantic Scholar's public API returned
`429 Too Many Requests` on the one call attempted and was not retried
(session-budget discipline, not a wall worth spending OpenClaw browser calls
on). Every pre-2020 finance-journal paper below (JF/JFE/JAR/RFS/JFQA) is cited
from established literature knowledge, not a live fetch this session — marked
`[LIT]` — consistent with how `strategy_library.py`'s own `SEED` catalogue
already cites Moskowitz-Ooi-Pedersen, Asness-Frazzini-Pedersen etc. without a
live URL fetch. No OpenClaw agent call was made (browser verbs were not
needed either); the $0.50 budget is untouched — plain HTTP covered every
source that mattered. All repo star/license/push data below is a live GitHub
API read timestamped 2026-09-26, not from memory.

Read first, so nothing below repeats it: `backend/services/strategy_library.py`
(203-rule catalogue + 34-family taxonomy + `NOT_REACHABLE`/
`BECAME_REACHABLE_2026_09_26_PM` dicts), `backend/services/strategy_library_ext.py`
(chunk C's six `pit_features` rules + 23 `EXT-*` discovery rules + 26
`EXT_NOT_REACHABLE` rows), `backend/services/pit_features.py` (the six-column
feature set + its `MIN_SUPPORT`), `LEADERBOARD.md` (112 rules run, no DSR
≥0.95, `low_risk` structurally dead), and the three 2026-09-26 research notes
(`research_library_expansion_and_lean.md` — 91 more proposed rules + the
LEAN/vectorbt/zipline engine cross-check; `research_openclaw_strategy_discovery.md`
— 47 QC-leaderboard/Reddit/GitHub/Quantpedia/Composer candidates, source of
the `EXT-*` rows already registered; `research_differentiation_and_interdisciplinary.md`).
Checked live this session: `backend/data/optimus/fundamentals_sec/sec_facts_history.parquet`
carries exactly **9** curated facts (`assets, cash, cogs, debt, equity,
net_income, operating_income, revenue, shares`) — **no R&D, no SG&A tag
extracted**, which matters for §1 below.

---

## 1. Papers with replicable rules (18 candidates)

Every row states whether the mechanism is **NEW** to the library (not one of
the 203 already registered/proposed rows) or **CORROBORATES** an existing
family (kept because the task asked for the category and because a second
citation with a different reported number is itself useful evidence
context). `reg_spec` is written in the `S(id, family, description, signal, ...)`
/ `D(did, rid, family, ...)` shape the codebase already uses, so it can be
pasted into `_rules()`/`_discovery_rules()` directly.

### A. Post-earnings-announcement drift

| # | citation | formula | universe/rebalance | reported effect | PIT columns: have / missing |
|---|---|---|---|---|---|
| 1 | DellaVigna & Pollet (2009), *JF*, "Investor Inattention and Friday Earnings Announcements" `[LIT]` | earnings-response coefficient to a Friday-filed announcement is materially weaker than to a same-surprise weekday announcement; the unpriced reaction resolves over the following weeks as drift | US equities, event-driven | Friday announcers show an immediate response ~15% smaller than weekday announcers of the same surprise, with a correspondingly larger subsequent drift (paper's own numbers, not independently re-derived here) | **HAVE** — `ear_last` (3-day announcement return) and `earn_next`/`earn_following` are already built from EDGAR 8-K item-2.02 dates (`strategy_library.py` `_EARN_CAVEAT`); day-of-week of that same filed date is a one-line derivation, no new data |
| 2 | Livnat & Mendenhall (2006), *JAR*, "Comparing the Post-Earnings-Announcement Drift for Surprises Calculated from Analyst and Time Series Forecasts" `[LIT]` | SUE = (actual EPS − analyst consensus EPS) / price, vs. the time-series-forecast SUE the original PEAD literature used | US equities, monthly, decile | analyst-consensus SUE produces a **larger and more persistent** drift than time-series SUE | **MISSING** — needs `sue`, i.e. a consensus EPS estimate *as of the announcement date*; this is `PEAD-01` in the existing catalogue, refused for exactly this reason since the first 02:00 board, and refused again by `PEAD-04` (needs PEAD-01) — a third confirmation that this single missing input blocks three catalogue rows, not one |
| 3 | Gleason & Lee (2003), *The Accounting Review*, "Analyst Forecast Revisions and Market Price Discovery" `[LIT]` | price discovery completes FASTER for the FIRST analyst to revise in a cluster than for later revisers; late revisions are largely already priced | US equities, event-driven | first-mover revisions carry significantly more of the eventual price move than revisions 2nd/3rd/... into the same cluster | **HAVE** — `revision_flow.py` already carries `firm`/`n_firms_acting`; `MISC-08`/`SEQ`-family "days-since-first-raise" was proposed in `research_library_expansion_and_lean.md` §L but never registered — this paper is the citation that MISC-08 was missing |

### B. Analyst-revision momentum

| # | citation | formula | universe/rebalance | reported effect | PIT columns |
|---|---|---|---|---|---|
| 4 | Diether, Malloy & Scherbina (2002), *JF*, "Differences of Opinion and the Cross Section of Stock Returns" `[LIT]` | HIGH analyst forecast dispersion predicts LOWER future returns (short-sale-constraint / optimist-sets-the-price story) — the sign the existing `DISP-*` family in `research_library_expansion_and_lean.md` §G assumed but never pinned to a citation | US equities, monthly | high-dispersion quintile underperforms low-dispersion by a statistically significant margin in the original sample | **FORWARD_ONLY, confirmed** — target-dispersion snapshots start 2026-09-24 (`forecast_dispersion_v1` already registered `FORWARD_ONLY`); this paper fixes the SIGN the `DISP-01..06` proposals need (short/avoid high dispersion, not buy it) |
| 5 | Jegadeesh, Kim, Krische & Lee (2004), *JF*, "Analyzing the Analysts: When Do Recommendation Changes Have Value?" `[LIT]` | recommendation-change PROFITABILITY is concentrated where it CONFIRMS an existing earnings-momentum or revision signal, not where it stands alone | US equities, monthly | combined signal materially outperforms either alone | **CORROBORATES** — this is the citation underneath the already-registered `skilled_leader`/`skill_mom` combination rules; no new build |

### C. Short interest / utilisation

| # | citation | formula | universe/rebalance | reported effect | PIT columns |
|---|---|---|---|---|---|
| 6 | Asquith, Pathak & Ritter (2005), *JFE*, "Short Interest, Institutional Ownership, and Stock Returns" `[LIT]` | days-to-cover (short interest / average daily volume), high-DTC + low-institutional-ownership underperforms most | US equities, monthly | economically large underperformance in the high-DTC/low-inst-own bucket | **CORROBORATES** — already `RET-07` → `low_days_to_cover`/`low_days_to_cover_large`/`short_covering`/`low_dtc_mom`/`short_squeeze`/`low_dtc_gp`/`covering_flow` (7 rules registered); `LEADERBOARD.md` shows `low_dtc_gp` at **−21.9%** vs SPY in the 2024-26 window — i.e. already tested and currently losing |
| 7 | Boehmer, Jones & Zhang (2008), *JF*, "Which Shorts Are Informed?" `[LIT]` | DAILY short-SALE volume (execution-based, from exchange audit-trail data) predicts next-day/next-week returns more strongly and faster than the bi-monthly reported short-INTEREST position the library already uses | US equities, daily | daily-short-volume-based signal predicts returns at a materially shorter horizon than the classic bi-monthly short-interest literature | **NEW mechanism, MISSING data** — `dtc` is sourced from Compustat's `shortintadj` (`_SI_CAVEAT`: settlement-date + 26 calendar days, **bi-monthly**); FINRA's free daily short-sale-volume files are a different, higher-frequency source — see §2 |
| 8 | Engelberg, Reed & Ringgenberg (2018), *JFE*, "Short-Selling Risk" `[LIT]` | securities-lending FEE and fee VOLATILITY (the cost/risk of maintaining a short) price beyond the short-interest LEVEL the library already has | US equities, monthly | fee and fee-volatility carry incremental return predictability over short interest alone | **MISSING** — needs a lending-fee feed (IHS Markit/FIS); paid, ranked low priority in §2 given #7's free substitute covers similar ground |

### D. Insider clusters

| # | citation | formula | universe/rebalance | reported effect | PIT columns |
|---|---|---|---|---|---|
| 9 | Cohen, Malloy & Pomorski (2012), *JF*, "Decoding Inside Information" `[LIT]` | ROUTINE insider trades (same calendar quarter, 3+ consecutive years) carry no signal; OPPORTUNISTIC trades do | US equities, monthly | opportunistic-trade portfolio significantly outperforms; routine-trade portfolio does not | **CORROBORATES** — already the exact split behind `insider_opportunistic`/`insider_officer` (`INS-01`, `BECAME_REACHABLE_2026_09_26_PM`); no new build |
| 10 | Jeng, Metrick & Zeckhauser (2003), *Review of Economics and Statistics*, "Estimating the Returns to Insider Trading: A Performance-Evaluation Perspective" `[LIT]` | insider BUY portfolios show abnormal returns of a similar magnitude to the best mutual-fund managers; insider SELLS show little to no abnormal signal (asymmetric, buys informative, sells mostly liquidity-driven) | US equities, calendar-time | buy-portfolio alpha materially larger than sell-portfolio alpha | **CORROBORATES** — matches the existing long-only-mandate design choice already documented in `INT-08`'s caveat (sells used only as an exclusion overlay, never a short) |

### E. News-tone momentum (distinct from the library's existing COUNT-based attention family)

| # | citation | formula | universe/rebalance | reported effect | PIT columns |
|---|---|---|---|---|---|
| 11 | Tetlock (2007), *JF*, "Giving Content to Investor Sentiment: The Role of Media in the Stock Market" `[LIT]` | a media-pessimism SCORE (Harvard-IV/GI dictionary applied to a general-news column) predicts a next-day price DECLINE, followed by a REVERSAL within the week — a fundamentally different temporal shape (overreaction+reversal) than the drift-momentum families the library already carries | US market-level, daily | high pessimism → lower next-day return → partial reversal within ~1 week | **NEW mechanism, buildable now, not free of compute cost** — Aegis already runs FinBERT in-house (`backend/services/sentiment_analyzer.py`, primary path, keyword fallback) over per-ticker headlines; the news corpus (`news_corpus`, `first_seen_utc`) exists but its history is short (`night_e1_news_return_panel.py` defaults to `years=("2025","2026")`, ~20 months, same caveat `MISC-03` in `research_library_expansion_and_lean.md` already carries) |
| 12 | Loughran & McDonald (2011), *JF*, "When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks" `[LIT]` | a finance-specific negative-word dictionary applied to **10-K/10-Q narrative text** outperforms the general Harvard-IV dictionary for predicting returns/volatility around filings | US equities, event-driven | LM dictionary materially reduces false-positive "negative" classifications vs. Harvard-IV on financial text, translating into a cleaner return/volatility relationship | **MISSING** — needs the filing's NARRATIVE TEXT; `sec_facts_history.parquet` carries only 9 numeric XBRL facts (`assets, cash, cogs, debt, equity, net_income, operating_income, revenue, shares` — confirmed live this session), no filing prose at all |
| 13 | "Sentiment trading with large language models" (2024) `[V-ARXIV 2412.19245, published 2024-12-26]` | compares LLM sentiment scorers on 965,375 US financial-news articles (2010-01-01→2023-06-30): OPT 74.4%, BERT 72.5%, **FinBERT 72.2%** sentiment-direction accuracy vs. the Loughran-McDonald dictionary's 50.1%; documents a "significant association between LLM scores and subsequent daily stock returns" | US equities, daily, news-level | FinBERT/OPT/BERT all clear ~72-74% vs. LM's ~50% on the paper's own accuracy metric (not Sharpe/CAGR) | **de-risks #11 directly**: Aegis's existing FinBERT install is the SAME model class this paper finds informative, not merely "a dictionary" — the missing piece for #11 is corpus HISTORY LENGTH, not model choice |
| 14 | "Fine-Tuning Large Language Models for Stock Return Prediction Using Newsflow" (2024) `[V-ARXIV 2407.18103, published 2024-07-25]` | fine-tunes encoder- and decoder-only LLMs on newsflow-derived token representations for direct return forecasting; finds AGGREGATED token-level representations (not naive mean-pooling) improve forecast quality | US/global equities, daily, news-level | fine-tuned representations outperform naive sentiment-polarity baselines in the paper's own held-out evaluation | **NOT tonight** — a genuine fine-tuning/labelled-target ML build, not a one-line rule; logged as a "this month" R&D item, not a `strategy_library` row |

### F. Intangibles / R&D

| # | citation | formula | universe/rebalance | reported effect | PIT columns |
|---|---|---|---|---|---|
| 15 | Chan, Lakonishok & Sougiannis (2001), *JF*, "The Stock Market Valuation of Research and Development Expenditure" `[LIT]` | R&D expense / market value (or / assets); the market under-values R&D because GAAP expenses it immediately rather than capitalising it | US equities, annual | high-R&D-intensity firms subsequently outperform, esp. among firms with low market-to-book | **MISSING, but CHEAPLY FIXABLE** — confirmed live this session: `sec_facts_history.parquet` extracts only 9 hand-picked XBRL tags and `ResearchAndDevelopmentExpense`/`SellingGeneralAndAdministrativeExpense` are **not among them**. This is not a new data SOURCE (the raw SEC XBRL company-facts the pipeline already pulls from almost certainly carries `us-gaap:ResearchAndDevelopmentExpense` for R&D-reporting firms) — it is a missing line in whatever extraction config builds this parquet. Flagged as the single cheapest genuinely-new fundamentals column in this whole note. |
| 16 | Eisfeldt & Papanikolaou (2013), *JF*, "Organization Capital and the Cross-Section of Expected Returns" `[LIT]` | capitalise SG&A into an "organization capital" stock (perpetual-inventory method); high organization-capital-to-physical-capital firms earn a return premium, concentrated where key talent is scarce | US equities, annual | organization-capital-sorted portfolios earn a significant premium over the sample period | **MISSING, same fix as #15** — needs `SellingGeneralAndAdministrativeExpense`, also absent from the 9-tag extraction; both #15 and #16 are one extraction-config change away, not a new vendor relationship |

### G. Low-vol/quality combinations, seasonality, industry momentum — CORROBORATION only (no new build; logged because the task asked for the category)

| # | citation | why it's already covered |
|---|---|---|
| 17 | Heston & Sadka (2008), *JFE*, "Seasonality in the Cross-Section of Stock Returns" `[LIT]` | same-calendar-month return persistence; already registered as `seas_mom` and the tail-of-file `book_f_seasonality_11_20_v0` — this paper is the citation, no new column needed |
| 18 | Asness, Frazzini, Israel & Moskowitz (2014/2020 "Fact, Fiction, and Momentum Investing" and related), *JPM* `[LIT]` | momentum's crash risk concentrates in high-volatility, post-crash "up market" states; **directly the mechanism behind `INT-06`/`REG-01`/`REG-02`/`REG-08`** proposed in `research_library_expansion_and_lean.md` §A/B but **not yet registered in `strategy_library.py`'s live `_rules()`** — this is the citation those proposals were missing; it is the single highest-value "quality/low-vol × momentum" row to register tonight (see §4) |

### One important negative result carried over honestly

Row 6 (`low_dtc_gp`, the short-interest+profitability combination) already RAN
on `LEADERBOARD.md` and sits at **−21.9% vs SPY** in the 2024-26 selection
window — the paper's own claim (Asquith-Pathak-Ritter) is not being presented
here as untested; it has already been tested and is currently losing on this
panel. Cited for completeness of the requested category, not as a new
candidate to chase.

---

## 2. Data sources named above that Aegis lacks, ranked by cost and PIT-cleanliness

| rank | source | cost | PIT-cleanliness | unlocks | free path? |
|---|---|---|---|---|---|
| 1 | **Two more XBRL tags on the existing SEC-facts pipeline**: `us-gaap:ResearchAndDevelopmentExpense`, `us-gaap:SellingGeneralAndAdministrativeExpense` | **$0** — same ingestion pipeline that already produces `sec_facts_history.parquet`'s 9 tags; likely an extraction-config change, not a new pull | as clean as the existing 9 facts (`filed`+2d join, `_FUND_CAVEAT` already governs it) | candidates #15 (Chan-Lakonishok-Sougiannis R&D) and #16 (Eisfeldt-Papanikolaou org capital) | yes — verify the raw XBRL source already has the tag before assuming a new SEC pull is needed |
| 2 | **SEC EDGAR full-text search** (`efts.sec.gov/LATEST/search-index`) | free, no key required | filed-date exact, genuinely PIT-clean | unlocks the entire "filing NARRATIVE TEXT" gap: Loughran-McDonald dictionary scoring (#12), Cohen-Malloy-Nguyen "Lazy Prices" MD&A-change-detection (not tabled above, same family as #12), and — per arXiv 2604.19476's 10-K-embedding approach — a cheap substitute for Compustat customer-supplier segment data | yes |
| 3 | **FINRA daily short-sale-volume files** (`finra.org/finra-data`, the "Regulation SHO" daily files) | free, T+1 | genuinely PIT-clean (published daily) | candidate #7 (Boehmer-Jones-Zhang daily short-sale signal, distinct FREQUENCY from the existing bi-monthly `dtc`) | yes |
| 4 | **BEA Input-Output Use Tables** (`bea.gov`, annual) | free | published with a stated, dateable lag | Menzly-Ozbas industry-pair lead-lag (a free substitute for firm-level customer-supplier data) — logged in `research_library_expansion_and_lean.md` §I as needing a sector map join, which now exists; this is the next-cheapest genuinely new mechanism after items 1-3 | yes |
| 5 | **13F structured filings** | **already have it** — `backend/data/optimus/wrds/tr13f_s34_*.parquet` back to 1996, per `research_library_expansion_and_lean.md` §0. Listed here only to correct the record: `NOT_REACHABLE["RET-10"]` in `strategy_library.py` says "no 13F feed," which is now stale — the file exists, just unregistered as a rule (`SEQ-04`/`SEQ-06` in the other note) | $0 | institutional-ownership-breadth rows | already free — a registration gap, not a data gap |
| 6 | **IHS Markit / FIS securities-lending fee data** | paid, institutional-tier pricing | reasonably PIT-clean once licensed | candidate #8 (Engelberg-Reed-Ringgenberg short-selling-risk) | no |
| 7 | **Full sell-side analyst REPORT TEXT** (Refinitiv/Visible Alpha/FactSet narrative feed, or a scrape of uncertain legality) | paid and/or legally uncertain | timing/redistribution rights unclear — the WEAKEST PIT-cleanliness case in this table | candidates behind arXiv 2502.20489 / 2411.13813 | no clean free path found this session |
| 8 | **Compustat Segment-Customer file** (Item 101 major-customer disclosures) | paid (WRDS/Compustat) | reasonable PIT (filed-date joins) | literal Cohen-Frazzini (2008) firm-level customer-supplier links | no — but item 4 (BEA) and the EDGAR-text route (item 2, following arXiv 2604.19476's method) both approximate the same economics for free |
| 9 | **Consensus EPS estimate AT ANNOUNCEMENT** (I/B/E/S detail history, WRDS) | paid | good PIT if licensed at the detail-history level | closes `PEAD-01`/`PEAD-04` and candidate #2 (Livnat-Mendenhall SUE) — the single most-requested-and-refused input in the ENTIRE existing catalogue (three separate rows die on its absence) | no free path found; flagged as the highest-value PAID acquisition if Aegis ever budgets for one |

---

## 3. OSS trading-bot / quant-framework comparison

Deliberately the "big name" list `research_repos.md` excluded on instruction
(it covers small/undiscovered repos instead). Stars/license/last-push are a
live GitHub API read, 2026-09-26. LEAN, vectorbt and zipline-reloaded were
already researched in depth in `research_library_expansion_and_lean.md` §2 —
summarized here for the comparison table, not re-derived.

| repo | stars / license / last push | what it does better than Aegis (concretely) | what Aegis does that it doesn't | ONE thing to copy |
|---|---|---|---|---|
| **microsoft/qlib** | 48,868 / MIT / 2026-09-22 (active) | A proper point-in-time data server with a declarative feature-expression DSL (`Alpha158`/`Alpha360`: `"Ref($close,-1)/$close-1"`, lazily evaluated with dependency tracking) and an auto-generated IC/RankIC-by-horizon report per experiment | Cross-experiment multiplicity accounting (DSR at n=834 cells, the 31-family effective count) — qlib's IC report is per-model, not corrected across a whole library the way `LEADERBOARD.md`'s "Multiplicity" section is; no analogue to the licence ladder or the by-year/LOO-worst honesty fields | `qlib/contrib/report/analysis_model/analysis_model_performance.py`'s standardized IC-decay-by-horizon chart — copy the CHART SHAPE (not the code) into `LEADERBOARD.md`'s generator as a visual complement to the existing `by_year_signs` string |
| **QuantConnect/Lean** | 21,787 / Apache-2.0 / 2026-09-25 (active) | An architecturally independent (.NET/C#, event-driven bar-by-bar) execution/fill/brokerage model with realistic partial fills and corporate-action handling — genuinely different failure modes than Aegis's own vectorized pandas engine, which is the whole point of a second-engine cross-check | The sealed/dev split discipline and per-rule fingerprint/signature dedup; LEAN's own backtest report has no equivalent to "which years were dropped and what happens to the number" | Already scoped in full: `research_library_expansion_and_lean.md` §2.5's exact adapter design (`top10_for_replication_<date>.json` → `PythonData` custom-data class) — build that, don't re-derive it |
| **freqtrade/freqtrade** | 54,810 / GPL-3.0 / 2026-09-26 (active) | A single code path for `dry_run` (paper) and live trading (`IStrategy.populate_indicators/entry_trend/exit_trend`, one execution loop) plus a `--freqaimodel` plugin seam for swapping in an ML model without touching order routing | The three-licence ladder and a reputation ledger spanning MULTIPLE independently-run paper accounts with a shared execution lease (`pc_broker.py`); freqtrade has no cross-strategy-family governance layer, only per-bot config | freqtrade's single-entry-point pattern: Aegis currently has TWO separate code paths for a decision (`night_backtest_factory`'s vectorized `run_strategy` vs. `pc_broker.submit()`'s live path, per the 2026-09-25 finding that `u_plan` is the ONLY caller of `pc_broker.submit()`) — copy the PATTERN (not the code) so a forward-paper decision and a backtest replay call the identical scoring function, closing the exact gap S56's research note already named |
| **stefan-jansen/zipline-reloaded** | 1,948 / Apache-2.0 / 2026-01-06 | An established Pipeline API (`DataSet`/`Column`/`DataFrameLoader`) that much of the factor-research Python ecosystem (`alphalens-reloaded`) still targets | Already covered: benchmarked SLOWER than vectorbt in-repo (2.9s vs 0.7s) and documented custom-bundle footguns (`research_library_expansion_and_lean.md` §2.3) — the recommendation there (skip for the second-engine check, vectorbt+LEAN instead) stands; not revisited here |
| **polakowo/vectorbt** | 9,193 / "custom, source-available" (Apache-2.0-with-Commons-Clause per its own terms page) / 2026-09-26 (active) | Already covered in depth (§2.2 of the LEAN note) — Numba-vectorized `Portfolio.from_orders`, ~4-6hr adapter estimate, chosen as the Phase-1 cross-check | The whole `strategy_library.Strategy` frozen-dataclass contract (signature/fingerprint dedup so a ThresholdVariant can't sneak in as a "new" rule) — vectorbt has no concept of a rule catalogue, only a backtesting engine | Not revisited — build proceeds per the existing Phase-1 plan |
| **mementum/backtrader** | 23,329 / GPL-3.0 / **last push 2024-08-19 — confirmed dormant over 2 years, live-checked this session** | Nothing current to copy; listed only to correct a common assumption — it is NOT actively maintained despite its star count, unlike every other entry in this table | — | skip; do not build against it |
| **AI4Finance-Foundation/FinRL** | 16,403 / MIT / 2026-09-26 (active) | A standardized Gym-style RL environment abstraction (`env_stock_trading`) letting a strategy be swapped for PPO/A2C/DDPG etc. against the same state/reward interface, plus a documented FinRL-Meta market-simulation layer for pretraining | PIT discipline end-to-end and the DSR/multiplicity machinery — FinRL's published benchmarks are widely criticized (including within its own later papers) for survivorship/lookahead issues the RL environment does not itself guard against | The Gym-environment ABSTRACTION as a pattern: if Aegis ever tests a learned router (`COMB-07`, deliberately deferred per the roadmap), standardizing its state/action/reward interface the way FinRL does would make it swappable against the FIXED selectors, not a rebuild of the ranker |
| **OpenBB-finance/OpenBB** | 73,477 / "custom, source-available" per its own licensing page / 2026-09-26 (active) | A very broad, actively-maintained set of FREE data-provider adapters (SEC, FRED, several fundamentals/estimates vendors) behind one consistent interface — a genuinely useful DATA ADAPTER LAYER, not a strategy engine | Everything downstream of data: the ranker, the rule catalogue, the licence ladder, the forward paper books | Its provider-adapter pattern (one thin class per data vendor, normalized to a common schema) as a template for closing §2's XBRL-tag and EDGAR-full-text gaps consistently, rather than one-off scripts per new column |
| **TauricResearch/TradingAgents** | 108,724 / Apache-2.0 / 2026-09-25 (active — by far the most-starred repo in this table) | A clean multi-agent DEBATE architecture (bull/bear analyst agents argue, a risk-manager agent adjudicates, a trader agent decides) with a documented, swappable LLM backend | The debate/verdict framing is close to Aegis's own thesis-card `bull/bear/falsifier/verdict/confidence` structure — but Aegis's card is explicitly "evidence and a falsifier, never an order" (per its own docstring) while TradingAgents' trader agent DOES place the order; Aegis's `pc_broker`/mandate-limit/execution-lease machinery has no analogue here | The explicit bull-agent/bear-agent/risk-manager AGENT SEPARATION (three distinct prompts arguing, not one prompt asked to see both sides) — worth comparing against Aegis's current single-pass thesis-card generation as a structural upgrade, independent of whether Aegis ever lets an LLM place an order |
| **AI4Finance-Foundation/FinGPT** | 21,297 / MIT / 2026-09-23 (active) | A documented, reproducible pipeline for fine-tuning open LLMs specifically on financial sentiment/forecasting tasks (LoRA-based, low compute cost), with published benchmark comparisons against FinBERT | The DEPLOYED forward-paper infrastructure — FinGPT is a research/fine-tuning toolkit, not a live trading system | Its LoRA fine-tuning recipe as the concrete "how" for candidate #14 above (Fine-Tuning LLMs for Stock Return Prediction Using Newsflow) if that R&D item is ever picked up |
| **virattt/ai-hedge-fund** | 63,754 / MIT / 2026-09-26 (active) | A roster of named "persona" agents (Buffett-style, Burry-style, technical, fundamentals, sentiment) each producing an independent signal that a portfolio-manager agent combines — an accessible, widely-copied reference architecture for "several independent selectors, combined later," which is literally Aegis's own stated bottleneck fix (`docs/AEGIS_STRATEGIC_INVARIANTS.md`: "a new mechanism arrives as its own book, never as a weight in `arena_composite`") | The persona-vs-process distinction from §64 (`docs/…`/MEMORY.md: "investigator (a PROCESS) +8.97% held out vs nine thematic personas −27.98% at optimal weight ZERO — a process forecasts; a persona does not") is exactly the finding this repo's whole architecture is blind to; ai-hedge-fund has no mechanism to detect that a named-persona agent is anti-signal | Nothing to copy code-wise — its VALUE here is as a calibration/comparison point: it is the popular reference implementation of the pattern Aegis's own §64 finding already falsified for one specific case (personas), worth citing precisely because it is the mainstream version of the idea Aegis's own data argued against |
| **HKUDS/Vibe-Trading** *(new, 2025-26)* | 34,065 / MIT / 2026-09-25 (active) | A one-command FastAPI+React personal trading-agent stack aimed at giving ANY coding agent (not just a fixed pipeline) tool access to trading capabilities — broad tool coverage, fast to stand up | Everything specific to Aegis's PIT discipline, cost model, and multi-book forward-paper ledger — this repo is a capability SURFACE, not a research programme | Its "one command, full tool surface for an agent" packaging philosophy — worth a look if Aegis ever wants Claude/DeepSeek-in-the-loop tool access packaged more cleanly than the current bespoke `investigator_tools.py` |
| **ginlix-ai/LangAlpha** *(new, 2025-26)* | 1,779 / Apache-2.0 / 2026-09-26 (active) | A "vibe investing agent harness" that dispatches parallel LLM subagents to screen the market and returns interactive long/short PAIR-TRADE ideas with a calibrated confidence display, built on LangChain | Aegis's long-only mandate discipline (per the three-licences note, Aegis explicitly does not run a short leg) — LangAlpha's pair-trade framing assumes short capability throughout | The parallel-subagent market-screening pattern (dispatch N subagents over disjoint universe slices, merge results) as a cheaper alternative to a single long-running OpenClaw quest when screening a large universe |
| **hsliuping/TradingAgents-CN** *(new, 2025-26)* | 31,988 / Apache-2.0 / 2026-09-22 (active) | A localization/enhancement fork of TradingAgents adding Chinese-market data adapters (A-share-specific fundamentals, regulatory-filing sources) | Nothing new beyond TradingAgents itself for a US-equity-only book; logged for completeness of the ">1k stars, 2025-26" ask, not as an actionable source | none beyond the base TradingAgents entry above |

---

## 4. Ranked "learn from their paper" list — 5 tonight-registrable, by `P(changes roadmap) × value − cost`

Every row below uses ONLY columns already on the panel — no new data pull, no
XBRL extraction change, no OpenClaw quest. Ranked highest expected value
first; every row states its falsifier and its control, per the pre-registration
discipline this note's licence does not require but the roadmap's own culture
rewards doing anyway.

| rank | rule (paper) | one-line `register()` spec | falsifier | control |
|---|---|---|---|---|
| 1 | **`friday_ear_drift`** (DellaVigna & Pollet 2009 — candidate #1) | `S("friday_ear_drift", "earnings_event", "announcement drift among names whose earnings 8-K was FILED on a Friday", gated(col("ear_last"), "ear_filed_dow", lo=5.0, hi=5.0), source="literature:SSA-01 DellaVigna & Pollet 2009, JF", economic_reason="investors are less attentive on Fridays; the unpriced reaction becomes drift")` — needs one new derived column, `ear_filed_dow`, a one-line `.dt.dayofweek` on the EXISTING 8-K filed date already used to build `ear_last` | if `friday_ear_drift`'s net return is statistically indistinguishable from `ear_drift`'s (the unconditional version already on the board), the day-of-week conditioning adds nothing and the row is `DEPRIORITIZED`, not the whole `earnings_event` family | `ear_drift` unconditional (already registered) as the k+1 twin; a `monday_ear_drift`/`wed_ear_drift` sibling (same construction, different day) as the random-same-band control — DellaVigna-Pollet's own claim is specifically about Friday, so any OTHER single weekday showing the same effect falsifies the DAY-SPECIFIC mechanism even if the row itself is profitable |
| 2 | **`quality_momentum_gate`** (Asness-Frazzini-Israel-Moskowitz momentum-crash literature — candidate #18, formalizing `INT-05`/`REG-08` which were proposed in the prior note but never registered) | `S("quality_momentum_gate", "combination", "12-1 momentum, scored only in the top tercile of gross_margin", gated(col("mom_252_21"), "gross_margin", lo=<p66 threshold>), source="literature:SSA-18 Asness, Frazzini, Israel & Moskowitz; " + <existing quality/momentum NM cite>, economic_reason="momentum survives in profitable/quality names; the crash risk concentrates in the unprofitable tail")` | if the row's net return is not meaningfully better than plain `mom_252_21` unconditional AND its worst-cell/LOO-worst is not meaningfully less negative, the crash-risk-concentration story is falsified for this panel | plain `mom_252_21` (registered) as the unconditional twin; `mom_low_ag`/`mom_gp` (already registered combination rows) as k+1 siblings from the same family — this row's DISTINCTIVE claim is specifically about the CRASH TAIL (LOO-worst month, max drawdown), not the mean, so the control comparison must read those fields, not just CAGR |
| 3 | **`cascade_entry_timing`** (Gleason & Lee 2003 — candidate #3, MISC-08 from the prior note, now with its citation) | `S("cascade_entry_timing", "revision_flow", "rank by DAYS-SINCE-FIRST-RAISE within an active revision cluster (early entrants score highest)", <needs a days-since-first-raise column derived from existing firm/date fields in revision_flow.py — buildable from data already on disk>, source="literature:SSA-03 Gleason & Lee 2003, TAR", economic_reason="the first mover into a revision cluster carries the most unpriced information; later revisers are chasing")` | if early-cluster-entry rank shows no return advantage over `net_raises`/`first_mover_raises` (both registered), the cascade-position claim adds nothing beyond the existing first-mover rule and is `DEPRIORITIZED` | `first_mover_raises`/`first_mover_large` (already registered, a related but distinct construction — "was first" vs "how early relative to the cluster's own length") as the direct sibling comparison |
| 4 | **`disp_short_avoid`** (Diether-Malloy-Scherbina 2002 — candidate #4, sign-fixing the `DISP-*` proposals) | `D("SSA-04", "disp_short_avoid", "analyst_dispersion", "avoid/exclude names in the top decile of target dispersion", col("target_dispersion", -1), url="[LIT] Diether, Malloy & Scherbina 2002, JF", claimed="high-dispersion quintile underperforms low-dispersion significantly (original sample)", reason="with short-sale constraints, optimists set the price when opinions differ widely", forward_only=True)` — `FORWARD_ONLY`, same as every other `target_snapshots`-based row (history starts 2026-09-24) | once enough forward months accrue: if the exclusion screen applied to `mom_12_1_q` shows no improvement in either mean return or LOO-worst month vs. `mom_12_1_q` unmodified, the dispersion-as-risk-filter claim is falsified for this panel | `mom_12_1_q` unmodified (the board's current #1 rule) as the base to compare the SCREENED version against — this is a construction-only row, evaluated by its effect on an existing rule, not as a standalone signal |
| 5 | **`monday_ear_drift`** — the DELIBERATE CONTROL for rank-1, registered alongside it rather than after | `S("monday_ear_drift", "earnings_event", "announcement drift among names whose earnings 8-K was filed on a Monday", gated(col("ear_last"), "ear_filed_dow", lo=0.0, hi=0.0), source="ours (control for SSA-01)", economic_reason="the deliberate non-Friday control; DellaVigna-Pollet's mechanism is specifically about Friday inattention", control=True)` — marked `control=True` so it is printed but never ranked or counted as a trial, exactly like `random_1..3`/`skill_mom_ranks_21_40` | this row is EXPECTED to show a smaller/no effect; if it shows an EQUAL OR LARGER drift than `friday_ear_drift`, that is the finding that kills rank-1's day-specific story, and it must be read before crediting rank-1 with anything | is itself the control for rank-1 — registering it in the SAME commit as rank-1, not after seeing rank-1's number, is the point (a control chosen after looking at the result is not a control) |

Total marginal build cost for all five: one new derived column
(`ear_filed_dow`, a `.dt.dayofweek` on data already joined for `ear_last`),
one derived column for cascade position (`revision_flow.py` already carries
the `firm`/date fields it is computed from), and the `target_dispersion`
column already exists as `FORWARD_ONLY` infrastructure. No new collector, no
new vendor, no OpenClaw quest, no XBRL extraction change — every other
candidate in §1 that needed one of those (R&D/SGA tags, FINRA short-volume,
EDGAR full-text) is correctly excluded from this list and left in §2 as
backlog, priced there instead of smuggled in here as "tonight."
