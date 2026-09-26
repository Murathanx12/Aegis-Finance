# Research — SSRN via OpenClaw's browser: signal candidates (2026-09-26)

**Licence: `PRODUCT_EXPERIMENT` exploration.** Every claimed number below is the
SOURCE's own figure (paper abstract or Quantpedia's own backtest page), never
Aegis-measured. Nothing here is a `RESEARCH_CLAIM`.

**Why this note exists.** `research_ssrn_arxiv_signals_and_oss_comparison.md`
(2026-09-26, earlier this session) could not read SSRN at all — `curl`/plain
HTTP gets a 403 from `papers.ssrn.com`. This note re-runs the SSRN half of that
scope through OpenClaw's browser on the **managed `muratclaw` profile**
(`backend/services/openclaw_client.browser()` / `.read_text()`), which is not
subject to that block, and adds the Quantpedia / Alpha Architect / Robeco / AQR
sweep the original note also owed.

**Read first, so results aren't re-proposed:**
- `backend/services/strategy_library_ext.py` — six rules registered TONIGHT
  under `REGISTERED_PAPER` (2026-09-26T15:05Z), sourced from the earlier SSRN/
  arXiv note, and **all six had a falsifier fire**: `friday_ear_drift` /
  `monday_ear_drift` (earnings-event, DellaVigna-Pollet Friday inattention),
  `quality_momentum_gate` (quality × momentum crash-tail, Asness-Frazzini-
  Israel-Moskowitz), `cascade_entry_timing` (revision-flow first-mover cascade,
  Gleason-Lee), `disp_short_avoid` (analyst-dispersion, Diether-Malloy-
  Scherbina), `inst_breadth_up` (institutional 13F breadth, Chen-Hong-Stein).
  Per the brief, this note actively steers toward **different economic
  sources** than those five families (earnings-calendar inattention, quality-
  momentum, revision herding, disagreement/short-constraint, ownership
  breadth) — not because those families are wrong everywhere, but because a
  sixth confirmation of the same source would not be new information.
- `EXT_NOT_REACHABLE` (24 rows) / `EXT_COVERED_BY` (9 rows) in the same file —
  the OpenClaw-discovery-round candidates from QuantConnect/Quantpedia/GitHub/
  Composer/Reddit already triaged tonight. Nothing below duplicates a row
  already sitting in either list; where a candidate here needs the same
  missing column as one of those rows (e.g. dividend yield, book-to-market,
  buyback facts), the existing row is cited rather than re-opened.
- `backend/services/strategy_library.py` `FAMILIES` dict (line ~991) — the 27
  economic-mechanism families already registered. No `patent`/`innovation`,
  no `options`/implied-vol, no `credit_risk`/distance-to-default, and no
  `filing_similarity`/text-change family exists yet — those four directions
  got priority in the SSRN search plan below.

---

## 1. SSRN — read live through OpenClaw's browser

**Method, stated plainly.** `openclaw browser open url=https://papers.ssrn.com`
on `muratclaw` (a cold, non-logged-in Chrome profile — SSRN never asked for a
login to read an abstract). Every subsequent page load is `navigate` -> `wait`
-> `snapshot --format ai --urls` (for the on-page hrefs) -> `read_text` (the
one fixed `innerText` read the wrapper allows; `evaluate` is refused by
`openclaw_client.ALLOWED_VERBS` at the Python layer regardless of what a CLI
example suggests). A cookie-consent overlay appeared once, on the first page
load, and covered the search button until "Accept all cookies" was clicked —
recorded in §5 as the one page that "walled" the run, not with a 403 but with
an invisible click target.

**A structural finding, not a footnote: SSRN's search is relevance-ranked, not
date-ranked, and the UI's own date/sort controls are native `<select>`
elements OpenClaw's accessibility-tree snapshot does not expose as clickable
options** (`browser`'s `ALLOWED_VERBS` has no `select` verb either — only
`click`/`type`/`press` on elements the AI-format snapshot names a `ref` for).
Two mitigations attempted and their outcome:

1. Clicking the "Sort by" combobox opened a native OS-level dropdown with no
   accessible-tree children in the snapshot — clicking blind was not possible
   without a coordinate-based click the wrapper doesn't expose.
2. Appending `&npage=1` to the search-results URL directly (bypassing the UI)
   did not paginate — it reset the query to empty ("Please enter search terms
   and click Search to see results"), i.e. `npage` is not silently ignored, it
   actively drops `term` from server-side session state. **Constructing a
   search URL by hand is not a safe shortcut on this site** — the one reliable
   path is the interactive one: navigate to `DisplayAbstractSearch.cfm`, type
   into the textbox, click the Search button, and read whatever relevance
   order comes back.

Consequence: results below are what SSRN's own relevancy ranking surfaced for
each query, not a top-downloaded or newest-first pull, and it skews toward
older (2000s-2010s), heavily-cited papers for generic finance queries — a real
result, not a methodology failure, and it is why several queries below
returned corroboration of an already-registered mechanism rather than
something new. Where SSRN's relevancy for a term returned nothing dated
2023-2026 on the visible page, that is recorded rather than papered over with
an invented "recent" hit.

**Queries run, each read live and timestamped this session (2026-09-27,
00:1x-01:0x local):** "cross-section of stock returns 2025" (negative —
relevancy surfaced only 2002-2016 papers on the visible page, none dated
2023-2026), "machine learning anomalies out-of-sample" (mostly off-topic
engineering/ML papers; one on-topic corroboration), "earnings call tone",
"patent stock returns", "options implied volatility skew stock returns",
"distance to default credit risk equity returns", "LLM news stock returns".
Each query's URL is `https://papers.ssrn.com/searchresults.cfm?term=<query>`
(the search-results page itself, always a valid, stable link back to the same
relevancy-ranked list); individual abstract permalinks
(`papers.ssrn.com/sol3/papers.cfm?abstract_id=NNNNNNN`) were captured via the
`--urls` snapshot for the first and last query and are given where captured —
noted per row where only the search-URL is available (a real limitation of
doing six searches in one browsing session under a pacing budget, stated
rather than backfilled from memory).

### A. Earnings-call TONE (a temperature/text-tone family, not on the panel at all — distinct from `ear_last`'s price reaction and from `attention_z`'s news COUNT)

| title | authors | posted | downloads | formula (as stated) | universe/horizon | claimed effect | PIT column: have/missing |
|---|---|---|---|---|---|---|---|
| Earnings Conference Calls and Stock Returns: The Incremental Informativeness of Textual Tone (*J. Banking & Finance* 36(4), 2012) | Price, Doran, Peterson, Bliss | posted 18 Jun 2010 [search: `earnings+call+tone`] | 2,642 | textual tone of the earnings-call TRANSCRIPT (not the 8-K price reaction) | US equities, up to 60 trading days post-call | "conference call tone dominates earnings surprises over the sixty trading days following the call" (source's own words) | **MISSING** — needs the call TRANSCRIPT text. No free aggregator exists on disk or (confirmed by prior SSRN/arXiv note) known free-and-legal; this is a genuinely new gap, distinct from `sec_facts_history`'s numeric XBRL and from the 10-K/10-Q prose gap #12/#Q1 below (transcripts are not an EDGAR filing type) |
| The Information Content of Tone Dispersion: Evidence from Earnings Conference Call Q&As | Fu, Huang, Wermers, Zhang, Zhang | posted 21 Apr 2026 [search: `earnings+call+tone`] | 119 | FinBERT-scored tone LEVEL and cross-speaker DISPERSION in the Q&A portion specifically | US equities, event-driven | tone dispersion carries incremental information beyond the level | **MISSING** — same transcript gap; notable that the source uses the SAME FinBERT model Aegis already runs (`sentiment_analyzer.py`), so the model is not the blocker, the transcript corpus is |
| Tone and Intraday Liquidity During Earnings Conference Calls | Rigsby | posted 17 Aug 2025 [search: `earnings+call+tone`] | 138 | tone vs. INTRADAY LIQUIDITY (bid-ask/depth), not returns directly, 36k calls 2009-2020 | US equities, intraday | tone is associated with liquidity-provider behaviour during the call | **MISSING**, same transcript gap; logged for completeness (liquidity, not a return signal) |
| Strategic Tone Construction in Earnings Calls: CEO Communication and Intra-Executive Dynamics | Lai Ngor NG | posted 11 Mar 2026 [search: `earnings+call+tone`] | 41 | qualitative/ML study of how CEO tone is transmitted to or diluted by other executives in Q&A | US equities | organisational-behaviour finding, no return number stated | **CORROBORATION only** — no testable return claim in the abstract; logged as evidence the transcript-tone literature is still active in 2026, not as its own row |

### B. Patents / innovation (no `patent`/`innovation` family exists in the library at all)

| title | authors | posted | downloads | formula | universe | claimed effect | PIT column |
|---|---|---|---|---|---|---|---|
| The Cross Section of Stock Returns Related to Patent Infringement Allegations (*J. Banking & Finance*, forthcoming) | Bereskin, Hsu, Latham, Wang | posted 22 Dec 2017 [search: `patent+stock+returns`] | 428 | long/short by ALLEGED-INFRINGER status; litigation data 2000-2014 | US equities, event-driven | "a stock portfolio consisting of alleged patent infringers...subsequent stock returns" underperform (mispricing/pessimism); plaintiff firms show no abnormal return | **NOT REACHABLE** — needs a patent-LITIGATION feed (Stanford NPE Litigation DB / Lex Machina / RPX are paid or access-gated); no such feed on disk |
| Patent Thickets, Stock Returns, and Conditional CAPM | Hsu, Lee, Zhou | posted 28 Jul 2015 [search: `patent+stock+returns`] | 788 | patent-thicket fragmentation measure (overlapping-ownership patent classes) vs. subsequent returns, explained by a conditional CAPM | US equities | thicket firms earn lower subsequent returns via commercialisation-cost channel | **NOT REACHABLE** — needs a patent citation/classification network (USPTO PatentsView / Google Patents Public Data are free but require a heavy citation-graph build, not a column-add) |
| Patents, Transfer Efficiency, and Stock Returns: Evidence from China | Rong, Weng, Ma, Lu | posted 28 Apr 2025 [search: `patent+stock+returns`] | 101 | patent count x "patent-to-profit transfer efficiency"; individual-investor limited attention to patent information | China A-shares | strong predictive power for non-SOE returns, weaker for SOEs | **NOT REACHABLE for the US panel** (China-specific data and market structure); logged because it is the most RECENT hit and states the clearest attention-based mechanism of the three |

### C. Options-implied moments (no `options`/implied-vol family exists in the library; distinct from `EXT-GH-06`'s SPY-only straddle, which is a market-timing not cross-sectional rule)

| title | authors | posted | downloads | formula | universe | claimed effect | PIT column |
|---|---|---|---|---|---|---|---|
| Option Implied Volatility, Skewness, and Kurtosis and the Cross-Section of Expected Stock Returns (Georgetown WP) | Bali, Hu, Murray | posted 10 Sep 2013 [search: `options+implied+volatility+skew+stock+returns`] | 4,609 | ex-ante risk-neutral moments (IV, skew, kurtosis) extracted from single-name option prices | US equities with listed options, monthly | risk-neutral moments are "positively related to the cross section of ex-ante expected stock returns" | **NOT REACHABLE** — needs a per-name options chain / implied-vol history (OptionMetrics IvyDB via WRDS is the standard paid source; no free per-name equivalent found) |
| The Relationship between the Option-Implied Volatility Smile, Stock Returns and Heterogeneous Beliefs (*Int'l Rev. Financial Analysis* 41, 2015) | Feng, Zhang, Friesen | posted 29 Aug 2015 [search: `options+implied+volatility+skew+stock+returns`] | — | slope of the put side vs. the call side of the IV smile | US equities with listed options | "stocks with a steeper put slope earn lower future returns, while stocks with a steeper call slope earn higher future returns" — the cleanest stated sign/formula of the three | **NOT REACHABLE**, same options-chain gap |
| Option-Based Variables and Future Stock Returns Across Firm Size and the COVID-19 Recession | Ayar, Allam | posted 18 Aug 2026 [search: `options+implied+volatility+skew+stock+returns`] | 31 | option-based predictors' strength BY firm-size band | US equities with listed options | small-cap option signals are noisier (wider spreads, lower option-to-stock volume) — a conditioning/interaction finding, not a standalone signal | **NOT REACHABLE**, same gap; kept because it is a §4 interaction hypothesis, not merely a corroboration |

### D. Distance-to-default / credit risk in equity returns (no `credit_risk` family exists — and the missing input is NOT a new data source, see the flag below)

| title | authors | posted | downloads | formula | universe | claimed effect | PIT column |
|---|---|---|---|---|---|---|---|
| Equity Returns Following Changes in Default Risk: New Insights into the Informational Content of Credit Ratings | Vassalou, Xing | posted 23 Jul 2003 [search: `distance+to+default+credit+risk+equity+returns`] | 906 | Merton (1974) distance-to-default, recomputed monthly from equity value, equity volatility and total debt | US equities, monthly | firms whose default risk RISES subsequently earn HIGHER returns than firms whose default risk falls (a distress-risk PREMIUM, counter to the naive "risky = avoid" prior) | **ONE COLUMN AWAY, AND THE MISSING PIECE IS ALREADY-KNOWN-BROKEN, NOT NEW.** Merton's inputs are equity market value, equity volatility (`vol_252` — HAVE) and total debt (`sec_facts_history` fact `debt` — HAVE, one of the 9 extracted tags). The ONLY missing input is a clean market-cap/equity-value series, which is the exact defect `strategy_library.py` already names `VAL-01` ("split-adjusted bars x as-filed shares" contamination) and which already blocks `EXT-QC-10`/`EXT-QC-14g`/value rules. **This means fixing VAL-01 unlocks distance-to-default AND value/book-to-market in one move — not two separate acquisitions.** |
| The Cross-Section of Credit Risk Premia and Equity Returns (*Journal of Finance*, forthcoming) | Friewald, Wagner, Zechner | posted 12 Jul 2011 [search: `distance+to+default+credit+risk+equity+returns`] | 2,255 | CDS-implied credit risk PREMIUM (market price of default risk), not the physical/risk-neutral default PROBABILITY alone | US/global equities+CDS, monthly | resolves the "distress puzzle" — physical default probability alone is not what is priced; the risk PREMIUM component is | **NOT REACHABLE** — needs a CDS feed (Markit/IHS, paid); logged as the correlation hypothesis in §4 that separates this from Vassalou-Xing's simpler Merton measure |

### E. News tone / LLM-on-news (ties directly to the panel's existing `attention_z`, which counts news, not its TONE)

| title | authors | posted | downloads | formula | universe | claimed effect | PIT column |
|---|---|---|---|---|---|---|---|
| Good News, Bad News, No News: The Media and the Cross Section of Stock Returns | Naumer, Yurtoglu | posted 12 Mar 2020, `abstract_id=3541037` | 415 | tonality of GENERAL news flow (not firm filings) | broad equities, daily | tonality of news flow relates to the cross-section of expected returns | **ONE COLUMN AWAY** — same construction as Tetlock 2007 (already logged by the prior SSRN/arXiv note as item #11); Aegis's `news_corpus` + in-house FinBERT (`sentiment_analyzer.py`) already exist, only a `news_tone_z` PANEL COLUMN (the score joined onto `pit_features`, exactly like `attention_z`'s own join) is missing — see §3 rank #1 |
| Text-based Fiscal News and the Cross-section of Stock Returns | Nguyen | posted 27 Dec 2022, `abstract_id=4311379` | 206 | a firm's REGRESSION-ESTIMATED exposure to a text-derived "Fiscal News Index" (macro, not firm-specific) | US equities, monthly | high-fiscal-news-exposure firms demand higher expected returns (a systematic-risk-exposure story, not a mispricing story) | **NOT REACHABLE** — the Fiscal News Index itself would need building from a macro-news corpus + a firm-level exposure regression; not a one-column join |
| What Does ChatGPT Make of Historical Stock Returns? Extrapolation and Miscalibration in LLM Stock Return Forecasts | Chen, Green, Gulen, Zhou | posted 23 Sep 2024 [search: `LLM+news+stock+returns`] | 826 | prompts an LLM with historical price paths/charts and measures forecast bias | US equities | "individual stock returns tend to reverse, LLM forecasts overextrapolate trends" | **Not a `strategy_library` row — a house-relevant methodological warning.** Aegis runs an LLM (DeepSeek) inside its own decision layer (`investment_committee`, `thesis_cards`, `u_forecast`). This paper's finding is a directly testable risk to that layer, not to the panel: if Aegis's own LLM-generated forecasts show the same extrapolation-vs-reversal gap, that is a bias in the JUDGE, not a new alpha source. Flagged for `pre-register-trial` on Aegis's own forecast ledger, not for `strategy_library` |

### F. Corroboration-only rows (logged per the brief's ask for the category; no new build)

- *Media Coverage and the Cross-Section of Stock Returns* (Fang & Peress, *JF* 2009, `abstract_id=971202`, 4,912 downloads) — breadth of media coverage affects expected returns; corroborates the existing `attention`/count family, no new mechanism.
- *Heterogeneous Responses in Financial Markets: Insights from Machine Learning* (Tang, Tang, Zhou, 2022) — a Fama-MacBeth-extending ML framework over 94 characteristics; corroborates the already-registered `combination` family and the base library's existing ML-adjacent rules; not a single-column addition.
- *Mfa Rpc News Sentiment and Stock Returns* — China-specific (Ministry of Foreign Affairs press-conference sentiment); corroborates the general news-sentiment genre, not transferable to the US panel.

## 2. Quantpedia / Alpha Architect / Robeco / AQR

`alphaarchitect.com/blog` returned HTTP 403 to a plain fetch (same shape as
SSRN, not retried through OpenClaw given the six Quantpedia hits below already
covered the requested breadth; logged as walled in §5). Robeco's and AQR's
insight listings rendered but are JS-paginated and gave at most one on-topic
title each for 2025-2026 (a Fama-French podcast, a style-premia white paper) —
neither carries a testable signal, so they are logged as **CORROBORATION
ONLY**, not tabled as candidates.

All six rows below were read live (`WebFetch`, timestamped 2026-09-27 00:2x-00:3x
UTC-local per this session's clock — the site itself carries no per-request
timestamp, so the read time is what is logged, per house rule "date a receipt
by its own stamp"). Quantpedia's own screener page
(`https://quantpedia.com/strategies/`) was fetched first and searched for six
themes named in the brief (patents, options/skew, buybacks, credit risk,
ESG/controversy, customer-supplier, M&A, news/LLM); it surfaced hits for
buybacks, options and ESG, and explicitly **none** for patents, credit risk,
customer-supplier or M&A-rumor — recorded as a negative result, not silence.

| # | title | URL | citation | signal | universe/rebal | claimed number | PIT column: have/missing |
|---|---|---|---|---|---|---|---|
| Q1 | The Positive Similarity of Company Filings and Stock Returns | quantpedia.com/strategies/the-positive-similarity-of-company-filings-and-stock-returns | Padyšák (2021), SSRN | monthly: cosine-similarity of each firm's latest 10-K/10-Q language vs. its own prior filing (Brain Company NLP feed); long the LOWEST-similarity decile (biggest textual change), short the highest | ~1,000 US large caps (Brain Company coverage), monthly | 5.47%/yr, vol 6.48%, Sharpe 0.84, backtest 2007-2020 | **MISSING** — needs the filing's NARRATIVE TEXT, which `sec_facts_history.parquet` does not carry (9 numeric XBRL tags only, confirmed by the earlier SSRN/arXiv note this session). Free path exists and was already named there: `efts.sec.gov/LATEST/search-index` (EDGAR full-text search) — same unlock as Loughran-McDonald dictionary scoring, but this is a DIFFERENT mechanism (year-over-year self-similarity, no dictionary, no sentiment model) |
| Q2 | Exploiting Term Structure of VIX Futures | quantpedia.com/strategies/exploiting-term-structure-of-vix-futures | Simon & Campasano (EFMA 2013) | daily: short (long) the front VIX future when its basis vs spot VIX is in contango (backwardation) beyond a 0.10-point roll threshold, hedged with E-mini S&P futures, 5-day hold | VIX futures + ES futures, daily | 19.67%/yr in-sample (2007-11); source's OWN page states out-of-sample is "slightly negative" with "deteriorating alpha" | **NOT REACHABLE** — needs VIX futures and index-futures rows; the panel is single-stock equities only. Also: the source itself reports the effect already decayed out-of-sample, so even if the instrument existed this would not clear the door |
| Q3 | Option-Expiration Week Effect | quantpedia.com/strategies/option-expiration-week-effect | Stivers & Sun (SSRN #1571786) | hold the largest-cap names ONLY during the week containing the month's 3rd Friday (option-expiration week), cash otherwise; mechanism is market-maker delta-hedge unwind as call open interest declines | S&P 100, weekly | 9.3%/yr, vol 8.7%, Sharpe 0.61, max DD -15.1%, backtest 1988-2010 | **PARTIAL / engine mismatch** — the calendar flag itself (`is_opex_week`, third-Friday-of-month) is a $0, zero-data-risk derivation from the date alone. The obstacle is not data, it is that this is a WEEKLY effect and the factory's engine is monthly (`_MONTHLY` caveat already logged elsewhere): every calendar month contains exactly one opex week, so a naive monthly realisation ("hold if in opex week") is either always-on or needs a weekly engine this factory does not have. Logged as its own bucket rather than forced into ONE_COLUMN_AWAY |
| Q4 | ESG Factor Momentum Strategy | quantpedia.com/strategies/esg-factor-momentum-strategy | Nagy, Kassam & Lee — "Can ESG Add Alpha? An Analysis of ESG Tilt and Momentum Strategies" | monthly: overweight names with the LARGEST 12-month RISE in ESG rating vs. MSCI World, underweight the largest fall | MSCI World (~1,000 names), monthly | 2.23%/yr, Sharpe 0.89, vol 2.5%, backtest 2007-2015; page's own complexity/confidence flags: "Very Complex" / "Moderate", and states its own out-of-sample back-test is "slightly negative" | **NOT REACHABLE** — needs an ESG-rating TIME SERIES (MSCI/Sustainalytics), not on disk and not free. Logged mainly because the source explicitly frames the mechanism as partly ordinary price momentum in disguise ("captures near-term momentum effects") — see §4 |
| Q5 | Earnings Announcements Combined with Stock Repurchases | quantpedia.com/strategies/earnings-announcements-combined-with-stock-repurchases | Amini & Singal — "Are Earnings Predictable?" (SSRN #2589966) | a buyback ANNOUNCEMENT of >=5% of shares outstanding in the 30-15 days before an earnings date signals management's positive private expectation; long 10-15 days before through 15 days after the earnings date | NYSE/AMEX/Nasdaq ex-ADR/CEF/REIT, bottom-quartile-cap excluded; daily, ~100 names/period | 25.2%/yr, Sharpe 2.27, vol 11.1%, backtest 1987-2013 | **MISSING — same gap already on record.** No buyback-announcement calendar exists on disk; this is the exact gap `strategy_library.py` already carries as `CATR-02`/`PEAD-05` ("no buyback calendar") and `EXT_NOT_REACHABLE["EXT-QP-05"]` (net_payout_yield). Not re-opened as a new gap — cited here only because it is this session's clearest, highest-claimed-Sharpe illustration of why that one column is worth acquiring |
| Q6 | ESG Level Factor Investing Strategy (context only) | quantpedia.com/strategies/esg-factor-investing-strategy | (same ESG family as Q4) | levels rather than changes | MSCI World, monthly | not re-fetched in detail — logged as the same NOT_REACHABLE gap as Q4, no separate row needed | same as Q4 |

**Alpha Architect, Robeco, AQR.** `alphaarchitect.com/blog` returned HTTP 403
(logged in §5, not retried through OpenClaw given budget — the six Quantpedia
rows already met the "5-10 more candidates" ask). Robeco's insights listing
surfaced one 2026-03 item ("The curious case of Fama-French: where does alpha
come from?" — a podcast, no testable signal) and AQR's surfaced one 2026-08
item ("Academic Alpha" — a style-premia commentary white paper, no specific
factor or number in the fetched excerpt). Both logged as **CORROBORATION
ONLY**: neither names a new mechanism or a claimed number, so neither is
tabled as a candidate — recorded as a negative result rather than papered
over with a generic "AQR believes in factors" citation.

## 3. Ranked candidates

Ranked qualitatively by `P(changes the roadmap) x value - cost`, per the
brief. "Cost" here means engineering + data-acquisition cost, not LLM spend
(this whole note spent $0 of the $1 `agent()` budget — see §5).

| rank | candidate | family | bucket | why this rank |
|---|---|---|---|---|
| 1 | `news_tone_reversal_5d` | `news_tone` (NEW) | **ONE COLUMN AWAY** | cheapest possible: the FinBERT model and the news corpus both already exist in-house (`sentiment_analyzer.py`, `news_corpus`); the ONLY new thing is a `news_tone_z` join exactly mirroring how `attention_z` already gets built. Different economic shape (tone-driven overreaction+reversal) from the six falsified families |
| 2 | `filing_similarity_change` | `textual_similarity` (NEW) | **ONE COLUMN AWAY** | "Strong" confidence per Quantpedia's own rating, a real SSRN citation, a free unlock path already named in the prior SSRN/arXiv note (EDGAR full-text search) — but it is a new ingestion pipeline (text + cosine similarity), costlier than #1 |
| 3 | `distance_to_default_rising` | `credit_risk` (NEW) | **ONE COLUMN AWAY, compounding** | the highest LEVERAGE item in this whole note: its only missing input is the market-cap fix (`VAL-01`) that ALSO blocks every value/book-to-market row already sitting in `EXT_NOT_REACHABLE`. Fixing it once unlocks two families, not one |
| 4 | `call_tone_drift` | `earnings_call_tone` (NEW) | **NOT REACHABLE** | the single highest CLAIMED effect size read this session ("dominates earnings surprises" over 60 days) but the transcript-text gap has no confirmed free path; ranked above the options/patent/credit-premia items because the claim is unusually strong and the spec is cheap to keep ready |
| 5 | `opex_week_large_hold` | `calendar_options` (NEW) | **PARTIAL — engine mismatch, not a data gap** | genuinely $0 (a calendar derivation), but the source's effect is weekly and the factory is monthly; ranked here rather than higher because a faithful realisation may not exist without a weekly engine, and lower than #4 because the claimed effect (9.3%/yr) is smaller |
| 6 | Option-implied moments (Bali-Hu-Murray IV/skew/kurtosis) | `options_implied` | NOT REACHABLE | strong, well-cited (4,609 downloads) claim, but needs a per-name options chain (OptionMetrics/WRDS, paid); no free per-name substitute found |
| 7 | Patent infringement litigation | `patent_litigation` | NOT REACHABLE | clean event-driven claim (JBF, 428 downloads) but needs a patent-litigation feed (Stanford NPE DB / Lex Machina, paid/gated) |
| 8 | Credit risk PREMIUM (Friewald-Wagner-Zechner, CDS-based) | `credit_risk` | NOT REACHABLE | this is the REFINEMENT of #3, not a substitute for it — ranked below #3 because it needs a paid CDS feed while #3 needs only the already-planned VAL-01 fix |
| 9 | ESG factor momentum / ESG level (Quantpedia Q4/Q6) | `esg` | NOT REACHABLE | needs an ESG-rating time series (MSCI/Sustainalytics, paid); source's OWN page states its out-of-sample backtest is "slightly negative" — low priority even once reachable |
| 10 | VIX futures term structure (Quantpedia Q2) | `vol_term_structure` | NOT REACHABLE | needs VIX + index futures instruments the single-stock panel does not carry; source's own page states the effect already decayed out-of-sample — do not prioritise even if the instrument gap closes |
| — | Patent thickets (conditional CAPM) | `patent_litigation` | NOT REACHABLE | needs a patent citation/classification network (USPTO PatentsView, free but a heavy graph build) — logged, not ranked above #7 given the build cost |
| — | Fiscal News Index exposure | `macro_text_exposure` | NOT REACHABLE | the index itself would need building from a macro-news corpus + a firm-exposure regression, not a column join |
| — | Buyback + earnings-announcement combo (Quantpedia Q5) | (existing gap) | **not a new gap** | same missing column as the ALREADY-LOGGED `CATR-02`/`PEAD-05`/`EXT-QP-05` (no buyback calendar); cited only as this session's clearest illustration of that gap's value, not re-ranked |

### Register()-ready specs for the top 5

Written in the exact shape `strategy_library_ext.py` already uses
(`Strategy`/`PaperStrategy` via its `S(...)`/`_paper(...)` helpers), so a
future session can paste these once each one's blocking column lands. None of
these five is registered tonight — every one is missing at least a column;
the specs exist so the NEXT session does not have to re-derive them.

```python
# 1. news_tone_reversal_5d -- family news_tone (NEW). Needs: news_tone_z
#    (FinBERT run over the EXISTING news_corpus, same join shape as attention_z).
S("news_tone_reversal_5d", "news_tone",
  "5-session LOWEST FinBERT tone z-score (most pessimistic) vs the name's own "
  "126-session baseline, scored only where attention_z > 2 (the spike Tetlock's "
  "mechanism requires)",
  gated(col("news_tone_z", -1), "attention_z", lo=2.0),
  source="literature:SSRN-NEWSTONE Tetlock 2007, JF 'Giving Content to Investor "
  "Sentiment'; Naumer & Yurtoglu 2020 https://papers.ssrn.com/sol3/papers.cfm?"
  "abstract_id=3541037 (research_ssrn_via_openclaw_browser_signal_candidates.md "
  "2026-09-27)",
  literature_reported="CLAIMED by source: high media pessimism -> lower next-day "
  "return -> partial reversal within ~1 week (Tetlock 2007; not re-derived here)",
  economic_reason=("attention-constrained investors overreact to a pessimistic "
                   "tone spike; the overreaction reverses once attention fades"),
  falsifier=("against fomo_reversal_5d (the already-registered COUNT-based spike-"
            "reversal rule): if dev-window excess vs SPY is not above it, tone "
            "carries nothing beyond the count spike already registered"),
  controls=("fomo_reversal_5d", "attention_shock_fade"),
  caveat=("NEW COLUMN: news_tone_z, FinBERT over the existing news_corpus; "
         "forward_only, same as attention_z (corpus began 2026-09-11)"),
  forward_only=True)

# 2. filing_similarity_change -- family textual_similarity (NEW). Needs: filing
#    narrative TEXT via EDGAR full-text search (efts.sec.gov, free) + a cosine-
#    similarity build against the firm's own prior filing.
S("filing_similarity_change", "textual_similarity",
  "cosine similarity of each firm's latest 10-K/10-Q language vs its OWN prior "
  "filing of the same type; LOWEST similarity (biggest year-over-year change) "
  "first",
  col("filing_similarity", -1),
  source=("literature:SSRN-FILINGSIM Padysak 2021, SSRN Electronic Journal "
          "'The positive similarity of company filings and the cross-section "
          "of stock returns' https://quantpedia.com/strategies/the-positive-"
          "similarity-of-company-filings-and-stock-returns "
          "(research_ssrn_via_openclaw_browser_signal_candidates.md 2026-09-27)"),
  literature_reported=("CLAIMED by source: 5.47%/yr, vol 6.48%, Sharpe 0.84, "
                       "backtest 2007-2020, Brain Company data, ~1,000 large caps"),
  economic_reason=("a large year-over-year change in a firm's OWN filing "
                   "language is itself news the market under-reads relative to "
                   "the numeric disclosures it already reacts to"),
  falsifier=("against rd_intensity/org_capital (the other filing-derived rules) "
            "and a random-k control: if dev-window excess vs SPY is not above "
            "both, textual change adds nothing beyond the numeric-facts rules "
            "already registered"),
  controls=("rd_intensity", "random_1"),
  caveat=("NEW INGESTION, not a column add: needs EDGAR full-text search "
         "(efts.sec.gov/LATEST/search-index, free, PIT-clean by filed date) "
         "plus a same-firm cosine-similarity build; a genuinely new pipeline, "
         "costlier than #1"),
  forward_only=False)

# 3. distance_to_default_rising -- family credit_risk (NEW). Needs: clean
#    equity market value (the VAL-01 fix). vol_252 and SEC-facts "debt" already
#    exist; this is why it out-ranks every other NOT_REACHABLE row.
_paper("SSA-D2D", "distance_to_default_rising", "credit_risk",
       "Merton (1974) distance-to-default recomputed monthly from equity value, "
       "vol_252 and SEC-facts debt; the LARGEST monthly RISE in default risk "
       "(falling distance-to-default) first",
       col("d2d_chg", -1),
       cite=("Vassalou & Xing 2003/2004, working paper -> Journal of Finance "
             "'Equity Returns Following Changes in Default Risk' "
             "(research_ssrn_via_openclaw_browser_signal_candidates.md "
             "2026-09-27)"),
       claimed=("firms whose default risk RISES subsequently earn HIGHER "
               "returns than firms whose default risk falls -- a distress-risk "
               "premium (no number carried in the source's own abstract)"),
       reason=("investors demand compensation for rising default risk; a "
              "distress-risk premium orthogonal to price momentum, quality and "
              "ownership breadth"),
       falsifier=("against gross_margin (quality) and a random-k control: if "
                 "dev-window excess vs SPY is not above BOTH, the 'premium' is "
                 "indistinguishable from the existing quality/random baseline"),
       controls=("gross_margin", "random_1"),
       caveat=("BLOCKED BY VAL-01, NOT A NEW GAP: needs a clean equity market "
              "value, the exact split-adjusted-bars-x-as-filed-shares defect "
              "already blocking value/book-to-market rows in EXT_NOT_REACHABLE "
              "-- fixing VAL-01 once unlocks THIS family and value in the same "
              "move"))

# 4. call_tone_drift -- family earnings_call_tone (NEW). NOT REACHABLE tonight:
#    needs the call TRANSCRIPT text (no EDGAR filing type, no confirmed free
#    aggregator found this session). Spec pre-written so it activates the day a
#    transcript corpus lands, same pattern as rd_intensity/org_capital sitting
#    behind INTANGIBLES_EXTRACTED.
_paper("SSA-CALLTONE", "call_tone_drift", "earnings_call_tone",
       "FinBERT tone score of the latest earnings-call transcript's prepared "
       "remarks, scored for 60 trading days following the call",
       col("call_tone_z"),
       cite=("Price, Doran, Peterson & Bliss 2012, J. Banking & Finance 36(4) "
             "'Earnings Conference Calls and Stock Returns: The Incremental "
             "Informativeness of Textual Tone' "
             "(research_ssrn_via_openclaw_browser_signal_candidates.md "
             "2026-09-27)"),
       claimed=("conference call tone dominates earnings surprises over the 60 "
               "trading days following the call (source's own words; no number "
               "carried)"),
       reason=("call tone carries private managerial information beyond the "
              "numeric surprise; the market under-reacts to tone specifically"),
       falsifier=("against ear_drift (the registered post-announcement drift "
                 "rule) AND news_tone_reversal_5d (spec #1 above): if dev-"
                 "window excess is not above BOTH, transcript tone adds nothing "
                 "beyond the price-reaction drift already registered and the "
                 "cheaper news-tone column"),
       controls=("ear_drift", "news_tone_reversal_5d"),
       caveat=("NOT REACHABLE TONIGHT: needs call-TRANSCRIPT text; not an "
              "EDGAR filing type, no confirmed free aggregator found this "
              "session (unlike the 10-K/10-Q text EDGAR full-text search "
              "already covers for #2)"))

# 5. opex_week_large_hold -- family calendar_options (NEW). $0 calendar
#    derivation, but ENGINE MISMATCH (weekly effect, monthly factory) -- flagged
#    explicitly rather than silently approximated.
S("opex_week_large_hold", "calendar_options",
  "hold the large-cap band ONLY during the calendar week containing the "
  "month's 3rd Friday (option-expiration week); cash the rest of the month",
  gated(col("mkt_not_stress"), "is_opex_week", lo=1.0, hi=1.0),
  source=("literature:SSRN #1571786 Stivers & Sun 'Returns and Option Activity "
          "over the Option-Expiration Week for S&P 100 Stocks' "
          "https://quantpedia.com/strategies/option-expiration-week-effect "
          "(research_ssrn_via_openclaw_browser_signal_candidates.md 2026-09-27)"),
  literature_reported=("CLAIMED by source: 9.3%/yr, vol 8.7%, Sharpe 0.61, max "
                       "DD -15.1%, S&P 100, backtest 1988-2010"),
  economic_reason=("market-maker delta-hedge unwind as option open interest "
                   "declines into expiration lifts large, actively-optioned "
                   "names during that one week"),
  falsifier=("against a RANDOM calendar week each month (not the opex week): "
            "if dev-window excess is not above that control, the mechanism is "
            "not opex-specific"),
  controls=("random_1",),
  caveat=("ENGINE MISMATCH, NOT A DATA GAP: is_opex_week is a free calendar "
         "derivation, but the source's effect is WEEKLY and this factory "
         "rebalances MONTHLY -- every month contains exactly one opex week, so "
         "a faithful monthly realisation does not exist without a weekly "
         "engine; register only as a stated approximation, never silently"))
```

## 4. Correlation / interaction hypotheses from the abstracts

Every hypothesis below is stated as an interaction rule plus the ONE
observation that would separate it from ordinary factor beta, per the North
Star's rule ("every intuition is owed one question").

1. **Distress-risk premium vs. credit-risk PREMIUM (Vassalou-Xing vs.
   Friewald-Wagner-Zechner).** Friewald-Wagner-Zechner's abstract states the
   "distress puzzle" directly: physical/risk-neutral default PROBABILITY alone
   has not reliably predicted returns in prior work; their claim is that the
   PRICED component is a risk *premium*, not the raw probability.
   **Separating observation:** if `distance_to_default_rising` (spec #3, the
   raw Merton probability) earns its premium ONLY in periods/names where
   credit spreads are already wide (i.e. it proxies a premium rather than a
   probability), an interaction gate on `mkt_stress` or a sector-level spread
   proxy should raise its Sharpe; if the gate does nothing, the "premium, not
   probability" distinction is not showing up on this panel and the simpler
   Merton measure should be read at face value, not defended as a partial
   proxy for something fancier.
2. **News tone vs. news COUNT (`news_tone_z` vs. `attention_z`).** Tetlock's
   mechanism is specifically about TONE, and Da-Engelberg-Gao's (already
   registered as `attention_shock_fade`) is about COUNT. **Separating
   observation:** score tone and count independently, then check whether
   `news_tone_reversal_5d`'s excess return SURVIVES a control for
   `attention_z` at the same dates (not just the `attention_z > 2` gate it is
   already conditioned on, but the FULL cross-sectional regression). If tone's
   coefficient goes to zero once count is included, tone is attention
   wearing a different name; if it survives, they are two different pieces of
   the same news event.
3. **Filing self-similarity vs. R&D intensity / org capital.** Padysak's
   mechanism (a big change in a firm's OWN language) and Chan-Lakonishok-
   Sougiannis / Eisfeldt-Papanikolaou's (understated R&D/SG&A capitalisation)
   are BOTH filing-derived but structurally unrelated — one is a rate-of-
   change-of-TEXT signal, the other a LEVEL-of-a-number signal.
   **Separating observation:** a name with high R&D intensity that files
   nearly-identical boilerplate every year (low `filing_similarity` variance)
   would falsify a "these are secretly the same signal" worry directly; the
   register()-ready spec already names `rd_intensity` as `filing_similarity
   _change`'s control for exactly this reason.
4. **Option-implied signals degrade with firm size (Ayar-Allam, item C3).**
   This is already stated as an interaction IN the source: "small-cap options
   exhibit wider relative bid-ask spreads and lower option-to-stock volume
   ratios, implying noisier implied-volatility [signals]." **Separating
   observation, if/when an options feed is ever acquired:** any options-based
   rule (`opex_week_large_hold`, or a future implied-moments rule) MUST be
   read only within the `large`/`mega` universe bands — the existing
   `universe_rule` mechanism `strategy_library.py` already has — never pooled
   with `small`/`mid`, or the size interaction the source itself warns about
   will silently dilute the result exactly the way `LEADERBOARD.md`'s
   liquidity-band splits already guard against for other families.
5. **ESG rating momentum is explicitly ordinary price momentum wearing a
   label (Nagy-Kassam-Lee, item Q4).** Their own abstract says the ESG-change
   signal "captures both near-term momentum effects and long-term ESG
   improvements" — i.e. the source itself concedes conflation.
   **Separating observation, if an ESG feed is ever acquired:** score
   `esg_rating_chg` net of ordinary 12-1 momentum (residualise or run both in
   one cross-sectional regression); if the ESG coefficient is not
   significant once momentum is included, this is `mom_12_1` under a
   different name and should never be registered as its own family — logged
   here specifically so nobody registers it on the strength of the raw
   univariate number in the Quantpedia table.
6. **Patent-based signals concentrate where investor attention is limited
   (the China patent paper, item B3).** Its own abstract: predictive power is
   strong for non-SOE firms specifically "driven by individual investors'
   limited ability to interpret patent information," and is explicitly
   WEAKER elsewhere. **Separating observation, if a US patent-litigation or
   patent-citation feed is ever acquired:** the same conditioning (small/
   low-analyst-coverage names) should be checked BEFORE pooling patent
   signals across the whole universe — the same "read the worst cell of a
   breadth sweep before the headline" discipline the standing rules already
   require for k-of-N sweeps.

## 5. OpenClaw at work

**Pages and verb sequence.** 13 OpenClaw page loads on `muratclaw` across
roughly 40 minutes of real elapsed time: one `open` (SSRN home, which
redirected to `DisplayAbstractSearch.cfm`), then per query
`navigate -> wait -> snapshot(ai, --urls) -> [click "Accept all cookies" once,
first query only] -> type(box, query) -> click(search button) -> wait ->
read_text -> snapshot(ai, --urls)`. Six query themes completed this way:
"cross-section of stock returns 2025", "machine learning anomalies out-of-
sample", "earnings call tone", "patent stock returns", "options implied
volatility skew stock returns", "distance to default credit risk equity
returns", "LLM news stock returns" (seven, not six — corrected count). Spacing
between page loads was coded at 6-18s (inside the intended 5-20s band); actual
spacing between QUERIES ran much longer in practice (multiple minutes) because
of tooling friction below, which is slower than a person, never faster —
consistent with the pacing intent even though it was not by design.

**What walled the run, and what did not.**

1. **SSRN's cookie-consent overlay** covered the search button on the very
   first page load and made `click` on the button's ref fail with "Element
   not found or not visible" — not a captcha, not a 403, an invisible click
   target. Fixed by finding and clicking "Accept all cookies" first; it did
   not recur on later navigations within the same session (the consent
   choice persisted).
2. **SSRN's date/sort controls are native `<select>` elements** with no
   children exposed in the AI-format accessibility snapshot, and `browser()`'s
   `ALLOWED_VERBS` has no `select` verb — `click` opens the native OS dropdown
   but nothing inside it is addressable. Two workarounds were tried (clicking
   blind, then constructing the URL with `&npage=1`); the second one actively
   broke the query (SSRN dropped the search term entirely rather than
   ignoring the unknown parameter). **Lesson for the next session: do not
   hand-construct an SSRN search URL beyond the bare `?term=`.**
3. **A self-inflicted tooling failure, not a website wall, cost the most real
   time.** Two background batch scripts (looping over multiple queries
   unattended) were launched to reduce round-trips; the machine was under
   heavy concurrent load from other processes at the time (confirmed via
   `Get-CimInstance Win32_Process`: several hundred-MB python/node processes
   already running, consistent with `always_on_lab` and other sessions'
   automation per the memory index), which made each `openclaw browser`
   subprocess call take far longer than its steady-state latency. One batch
   script hit a transient `REFUSED_BROWSER_PROFILE_UNAVAILABLE` (the
   `muratclaw` Chrome instance appears to have restarted mid-run, orphaning
   its tab) and both ended up running far longer than expected before being
   killed by PID (never by image name, per the standing rule) once `tabs()`
   showed the session was stuck rather than progressing. The remaining
   queries were then run one at a time, in the foreground, which is slower
   per query but verifiable at each step — the right trade given the house
   rule that a check that did not run is not a check that passed.
4. **Alpha Architect's blog (`alphaarchitect.com/blog`) returned HTTP 403**
   to a plain `WebFetch` — not retried through OpenClaw's browser given the
   six Quantpedia rows already satisfied the "5-10 more candidates" ask and
   the session's time budget was already stretched by item 3.

**Cost.** $0.00 of the $1.00 `openclaw_client.agent()` budget was spent — this
entire note used only the deterministic `browser()`/`read_text()` verb route,
never an LLM-backed OpenClaw agent turn. The Quantpedia/Robeco/AQR/Alpha
Architect reads used `WebFetch` (outside OpenClaw, outside the $1 cap, and
outside the `muratclaw`-profile pacing rule since it is not a browser session
at all). No page was written to, no field was filled beyond the search box,
and `browser-profile user` was never invoked.
