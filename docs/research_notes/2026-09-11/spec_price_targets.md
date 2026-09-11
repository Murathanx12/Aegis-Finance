# Price Target Spec — Research Scratchpad

Status: STARTING. Building incrementally.

## Owner complaint (verbatim intent)
"our price targets for stocks are bad. We can't run a 5-year Monte Carlo and
then just divide it by 5. Do it like the analysts: they make 52-week (1-year)
price targets. Learn how they do it and build the same system. My stocks have
been down a lot."

## Plan
1. Read repo: stock_analyzer.py (130-360), monte_carlo.py::simulate_paths,
   analyst_intelligence.py::_price_target_block, estimate_revisions.py,
   relative_valuation.py::_compute_implied_fair_value, analyst_target_grades.json,
   docs/INDEX.md ibes__ptgsumu notes.
2. Web research: sell-side target-setting methodology + academic citations.
3. Write BUILD SPEC for backend/services/price_target.py.
4. Explain why a better target doesn't answer "my stocks are down."

## MID-TASK ADDITION FROM MURAT (09-11)
"There seems to be a cap at 30%. See how our price targets compare to
analysts' and learn why they differ too much and how ours is wrong. We need
the analysts' target % upside to choose stocks in the screener, and the
engine itself should be able to use it. Test on backtests — the Monte Carlo
sims are so off. The engine should run and learn to correct itself: not caps
or limits, but corrections on every mistake."

Additions required:
1. DIAGNOSTIC — scripts/price_target_audit.py spec: per screener/tracker
   name, print our 1y figure vs consensus upside vs difference, and WHICH
   clamp step produced the gap (shrinkage / tier cap / consensus clip /
   300% ceiling / mean-vs-median). Plus IBES 2010-2024 backtest of our
   method-as-implemented vs consensus vs drift-only, per era, abs error +
   hit rate.
2. NO CAPS, CALIBRATION INSTEAD — replace clips with a learned, monthly-
   refit isotonic/quantile calibration of raw upside -> realized 12m return,
   by sector x vol x cap-bucket, on IBES PIT history. Re-fit loop = self-
   correction. Screener ranks on (calibrated upside, interval width, hit
   rate). Tracker books' "sealed upside x consensus" field consumes the
   calibrated figure.
3. Keep MC for path/drawdown only; specify how to test its 1y quantiles are
   calibrated (p05-p95 coverage on realized 1y outcomes, per era).

## REPO FINDINGS — THE EXACT BUG CHAIN (verified by direct reads)

### File: backend/services/stock_analyzer.py

**STOCK_CAGR_CAPS (lines 29-36)** — per market-cap tier, `(min_cagr, max_cagr)`,
loaded from `backend/config.py` `stocks.cagr_caps` (lines 868-873):
```
mega:  (0.04, 0.30)   # >$200B  <- THE 30% CAP MURAT NOTICED
large: (0.05, 0.35)   # $10-200B
mid:   (0.06, 0.40)   # $2-10B
small: (0.08, 0.45)   # <$2B
```
Comment says these were "widened for growth mega-caps" from an even lower
0.15/0.20/0.25/0.30 — i.e. the cap has already been raised once and is still
binding.

**Historical-drift path (lines ~160-178):** trailing-5y log return -> arithmetic
-> Bayesian-shrunk toward a flat 7% equity-premium prior
(`drift_shrinkage.prior_equity_premium=0.07`, shrinkage weight 25%-60%
depending on years of data) -> `capped_arithmetic = clip(shrunk, min_cagr,
max_cagr)`. This produces `capped_drift`.

**Consensus-blend path (line ~181, exact):**
```python
if analyst_target is not None and analyst_target > 0:
    analyst_1y_return = (analyst_target / current_price) - 1
    analyst_annual = np.clip(analyst_1y_return, -0.30, max_cagr)
    blended_arithmetic = 0.60 * capped_arithmetic + 0.40 * analyst_annual
```
**THIS IS THE BUG.** The raw Yahoo/S&P consensus 1-year target upside
(`analyst_1y_return`, e.g. +60% for a name Wall Street loves) is clipped to
`[-30%, max_cagr]` — i.e. to the SAME 30% (mega) / 35% / 40% / 45% ceiling as
the historical-drift leg — BEFORE the 60/40 blend. So no matter how bullish
the consensus is, the blended annual return can never exceed `max_cagr`. A
consensus of +60% and a consensus of +31% collapse to the identical clipped
input. The cap is not "our model disagreeing with analysts" — it is the
analysts' own number being truncated before it is used.

`final_arithmetic = clip(blended_arithmetic, min_cagr*0.5, max_cagr)` re-clips
again after the blend, so even a below-min_cagr*0.5 floor also compresses.

**Then this annual return is fed into a 5-YEAR Monte Carlo** (`forecast_days:
int = 1260` = 252*5, line ~100) via Ito-corrected log drift `final_mu`, run
through `simulate_paths` for 1260 trading days. `final_prices = paths[-1]`
(the 5-year terminal distribution) is capped again at
`current_price * (1 + max_5y_return)` where **`max_5y_return = 3.0` (300%
ceiling on the 5-year *cumulative* price, config.py line 654)** — a separate,
independent cap on top of the annual cap already baked into the drift.
`expected_return`/`median_return` (lines ~289-291) are the mean/median of
this 5-YEAR terminal distribution, reported as raw percentages with NO
horizon-appropriate framing in the API payload itself.

**Where the "divide five-year by 5" actually happens:**
`frontend/src/app/outlook/page.tsx:148-151`:
```ts
const model5yMedian = stock.median_return;
const model5yMean = stock.expected_return;
const modelAnnualized = (Math.pow(1 + model5yMean / 100, 1 / 5) - 1) * 100;
const medianAnnualized = (Math.pow(1 + model5yMedian / 100, 1 / 5) - 1) * 100;
```
This is a geometric 5th root (CAGR-ization), not a literal `/5`, but it is
exactly the move Murat is rejecting: back a "52-week" figure out of a 5-year
terminal MC distribution by assuming smooth annual compounding. It inherits
every upstream cap, throws away the terminal distribution's actual shape
(skew, fat tails, the jump-diffusion crash events land anywhere in 5 years
not necessarily year 1), and is NOT what analysts do (they don't run 5-year
paths at all for a 12-month target).

Elsewhere `stockData.expected_return` is shown directly on the stock page
(`frontend/src/app/stock/[ticker]/page.tsx:604`) labeled "Expected Return
(5Y)" — correctly labeled there — but the SAME field feeds the screener's
sort/summary (`frontend/src/app/screener/page.tsx:106,270,344,437-438`)
labeled just "Expected Return" with a 5Y number sorted/averaged as if it were
comparable across horizons, and portfolio/outlook pages reuse it as an
annual number via the CAGR-ization above.

### File: backend/services/analyst_intelligence.py
`_price_target_block` — DISPLAY ONLY, explicitly documented: "This is
DISPLAY intelligence, not a signal source — nothing here feeds the paper
lanes or the signal engine write-paths." Pulls `stock.analyst_price_targets`
(current/low/mean/median/high) from yfinance (S&P Global Market Intelligence
via Yahoo), computes `upside_pct = (mean/current - 1)*100` with NO
calibration, NO bias correction, NO clipping — this is the raw consensus,
shown to the user but never touching the engine. This is the field Murat
wants the engine and screener to actually consume (calibrated, not raw).

### File: backend/services/estimate_revisions.py
Pulls yfinance `.recommendations` (upgrade/downgrade actions) +
`.analyst_price_targets`, computes net revision counts (7d/30d/90d) and a
bullish/bearish consensus label. Also display/signal-adjacent, not a target
model. Cites Novy-Marx 2013, Jegadeesh & Livnat 2006, Barber & Odean for
revision-as-signal rationale (revisions, not target LEVELS).

### File: backend/services/relative_valuation.py :: _compute_implied_fair_value (lines 317-358)
Comps-based, NOT a 12-month target: peer-MEDIAN multiple (forward P/E,
trailing P/E, P/S — needs >=3 peers with positive metric) x the target's own
per-share figure (forward EPS, trailing EPS, revenue/share), then MEAN of
the available estimates. Explicitly documented: "what the stock would trade
at if priced like its sector median; not a forecast." This is exactly the
"multiple x NTM estimate" justified-multiple convention analysts use, BUT
the multiple is peer-median-of-the-moment (no time-series/PIT discipline,
no growth-conditioning, no shrinkage toward own history or market) — closest
existing building block to leg 1 of the new price_target.py spec, needs
generalizing (sector x growth-bucket median over trailing 5y, PIT, shrunk
toward market) and needs a fair-value -> 12-month-horizon interpretation
(today's comps fair value is a "now" fair value, not a forecast of where
comps trade in 12 months).

### IBES analyst-grading receipt: backend/data/optimus/tracker_backtest/analyst_target_grades.json
`licence: PRODUCT_EXPERIMENT`. Window 2005-2023 (anndats years), min 20
targets/analyst, implied-return cap 4.0 (400%, a data-cleaning cap not a
modeling cap). generated_utc 2026-09-01.
- **pooled**: n=1,333,683 individual 12-month targets graded, 9,158 analysts
  total (5,365 gradeable). **mean IMPLIED upside = 22.76%**, **mean REALIZED
  12m return = 12.98%**, **mean bias = +9.78pp** (median bias +6.92pp) —
  consensus targets are systematically optimistic by ~+7-10pp on average,
  consistent with Dechow-You 2020 / Bradshaw et al. **pooled IC (implied vs
  realized) = 0.0289** — the raw target LEVEL has almost no cross-sectional
  information about which names will actually do best (consistent with
  Brav-Lehavy: information is in the revision, not the level).
- **persistence_bias**: Spearman(bias in first half, bias in second half)
  across analysts = **0.376** — an analyst's optimism/pessimism IS a stable,
  learnable trait. Decile means run from d1 -2.76% to d10 +80.3% —
  monotonic and strongly separated. **This licenses bias-correction by
  analyst/firm cohort.**
- **persistence_accuracy**: Spearman = **0.087** — near zero. An analyst who
  was accurate in the first half is barely more accurate in the second half.
  **This is why "weight the historically-accurate analysts more" does NOT
  work** — it would be fitting to what the receipt's own `read_me_first`
  calls noise. Only bias-correction is defensible from this receipt, not
  skill-weighting.
- Row-level parquet is LOCAL-ONLY (not committed) — read `read_me_first`
  before quoting further detail; this JSON summary is the citable receipt.

### docs/INDEX.md
Line 91: "tape now reads `ibes__ptgsumu` over the raw close (PIT share
basis)" — the existing tape/panel infrastructure already reads IBES price
targets (`ptgsum`/`ptgdet` per the task brief) on a point-in-time,
split-adjusted basis. Line 178 cites the analyst_target_grades.json receipt
above verbatim.

### learner/beta.py
Offline WRDS-panel rolling-OLS beta builder (`_rolling_ols_beta`,
`build_market_daily`, `build`) producing `beta_panel.parquet` from CRSP
returns — this is the historical-panel-scale beta engine (for backtesting
IBES history PIT). For the LIVE price_target.py service, the practical beta
source is either yfinance `info["beta"]` (already used in stock_analyzer.py,
Yahoo's 5y-monthly regression beta) or the already-computed
`_get_factor_exposure`/`factor_model.decompose_stock` Fama-French loadings
(stock_analyzer.py line 595+, returns alpha_annual + per-factor loadings) —
reuse rather than re-fit. The offline learner/beta.py panel is the right
tool for BACKTESTING the DCF-lite leg over IBES 2010-2024 (PIT beta per
name-month), not for the live per-request call.

## MEASURED, LIVE (coordinator, 09-11) — TWO DEFECTS, NOT ONE

Six names run through the live `analyze_stock` (default `forecast_days=1260`
= 5y; `config.py:612 forecast_years: 5`). Columns: price / consensus 1-y
upside (Yahoo `targetMeanPrice`) / OUR `expected_return` / OUR `median_return`:

| Ticker | Price | Consensus 1y upside | OUR expected (5y) | OUR median (5y) |
|---|---|---|---|---|
| NVDA | 218 | +49.8% | +114.6% | +88.7% |
| ADBE | 249 | +12.5% | +25.1% | -3.2% |
| ADSK | 212 | +49.0% | +81.5% | +55.5% |
| MU | 977 | +54.8% | +96.4% | +60.1% |
| TSM | 428 | +28.8% | +151.3% | +143.2% |
| GPRO | 1.40 | -64.3% | -45.1% | -79.6% |

**DEFECT #1 (put first, above the clip chain): HORIZON MISMATCH.** The
number the page calls "expected return" is the MEAN of the 5-YEAR terminal
Monte Carlo distribution, shown/sorted/compared directly beside a 12-MONTH
consensus figure, with no per-year figure honestly computed either way. The
5y arithmetic mean is right-skewed vs the 5y median (NVDA +114.6% mean vs
+88.7% median; ADBE +25.1% mean vs -3.2% median — mean and median don't even
agree on SIGN) because jump-diffusion + GARCH fat tails compound positive
skew over 5 years of geometric compounding. Comparing a 5y mean to a 12m
consensus number is not apples-to-apples on ANY dimension: horizon, or
statistic (mean vs point estimate). This is the dominant, more embarrassing
defect and must be fixed before the clip chain even matters.

**DEFECT #2: the blend/clip chain (detailed above).** NVDA's own +49.8%
consensus enters the blend as +30% (mega-cap `max_cagr`) before the 60/40
mix — visible in the gap between what the consensus says and what a
correctly-annualized version of our number would say.

Both defects must be listed at the top of the diagnostic section (deliverable
1 below), and the spec's FIRST deliverable is a 12-MONTH figure computed on
the SAME horizon as the consensus (not backed out of a 5-year path via any
root/division), carrying its own interval — before any other piece of the
spec.

## STATUS: repo reads + live measurement done. Proceeding to web literature research next.

## LITERATURE — KEY FACTS AND NUMBERS (citations, for deliverable 1)

- **Bradshaw 2002**, "The Use of Target Prices to Justify Sell-Side Analysts'
  Stock Recommendations," Accounting Horizons 16(1):27-41. 103 reports:
  analysts disclose target-price justification in >2/3 of reports; most
  favorable recs/targets justified by P/E and growth (i.e., PEG-style
  heuristics); analysts largely compute targets via price-multiple heuristics
  ("PEG"), not full DCF.
- **Demirakos, Strong & Walker 2004**, "What Valuation Models Do Analysts
  Use?" (Accounting Horizons) and **2009** "Does Valuation Model Choice
  Affect Target Price Accuracy?" — catalogs multiples (P/E dominant), DCF,
  RIM usage by sector; multiple choice varies by industry maturity.
- **Asquith, Mikhail & Au 2005**, "Information content of equity analyst
  reports," JFE 75(2):245-282. Catalog of 1997-99 All-American analyst
  reports: **most analysts use a simple earnings-multiple valuation model;
  only a minority use NPV/DCF.** No correlation between valuation
  methodology and either market reaction or target accuracy. **~54% of
  targets achieved/exceeded within 12 months; the other 46% reach an average
  84% of target.** Optimism (bigger implied move) inversely related to hit
  probability: targets implying 0-10% moves hit 74.4% of the time; targets
  implying >=70% moves hit <25% of the time. Price-target CHANGES carry
  independent information beyond earnings-forecast and recommendation
  revisions (this is the "information is in the revision" finding).
- **Brav & Lehavy 2003**, "An Empirical Analysis of Analysts' Target Prices,"
  JFE/Journal of Finance 58(5):1933-1967. 1997-99: significant market
  reaction to target REVISIONS (announcement-day spread of ~7pp between
  positive/negative revisions); cointegration analysis finds the long-run
  equilibrium 1-year-ahead target is **~22-28% above current price** on
  average (i.e., consensus targets imply +20-30% upside as a matter of
  course, largely independent of the specific stock) and that subsequent
  correction toward that equilibrium is done by analysts revising targets,
  not by the market alone.
- **Bradshaw, Brown & Huang 2013**, "Do sell-side analysts exhibit
  differential target price forecasting ability?" Review of Accounting
  Studies 18(4). 2000-2009: **implied target-based returns exceed actual
  returns by ~15% on average; absolute forecast errors average ~45%; only
  ~38% of targets are met at the 12-month horizon, but 64% are met at SOME
  point during the 12 months.** Statistically significant but economically
  weak persistence in analyst-level forecasting ability (contrast with
  strong, persistent EARNINGS-forecast skill) — market discounts optimistic
  targets appropriately and does not reward/punish based on analysts' past
  target-accuracy track record. **Directly consistent with our own IBES
  receipt's persistence_accuracy Spearman 0.087 (near-zero).**
- **Kerl 2011**, "Target Price Accuracy," Business Research 4:74-96 (German
  market). Accuracy (price comes within range) 73.64% at 12mo; buy recs
  75.69% vs sell recs 59.43%. Only **56.53%** of targets are exactly reached
  within 12 months (median 72 days to reach, when reached). Accuracy
  negatively related to analyst optimism and stock volatility/P-B; positively
  related to report detail, company size, bank reputation. Not related to
  conflicts of interest.
- **Bilinski, Lyssimachou & Walker 2013**, "Target Price Accuracy:
  International Evidence," The Accounting Review 88(3):825-851. 16 countries:
  cross-country accuracy variation explained by disclosure quality, legal
  origin, culture, IFRS adoption. Analysts DO show differential and
  PERSISTENT target-forecasting ability in this broader international
  sample (contrast with Bradshaw/Brown/Huang's narrower US finding) —
  literature is not fully settled on accuracy persistence, but bias
  persistence is uncontested across studies.
- **Dechow & You 2020**, "Understanding the Determinants of Analyst Target
  Price Implied Returns," The Accounting Review 95(6):125-149. Four factor
  families explain ~25% of cross-sectional variance in target-implied
  returns: (1) future realized returns (some genuine information), (2)
  errors in forecasting fundamentals, (3) errors in forecasting the
  risk-adjusted expected return (biggest contributor), (4) incentive-driven
  bias. Investors do NOT fully back out the predictable optimism bias —
  i.e., **the bias is knowable in advance and still not priced out**, which
  is exactly the opening for a calibration layer.
- **Zhang (Yale, working paper, Management Science forthcoming)** — 537,519
  firm-months: pooled Spearman(PRET, realized 12m return) = **-0.047**
  (target LEVEL is if anything slightly NEGATIVELY associated with what
  happens next, unconditionally); but conditioning on DISPERSION flips it:
  in the lowest-dispersion decile, high implied-return names beat low ones
  by +2.96%/yr (t=2.54); in the highest-dispersion decile the same trade
  LOSES -11.44%/yr (t=-5.34). **Consensus disagreement (dispersion) is a
  necessary conditioning variable, not just the upside number itself** —
  ties directly to the spec's "interval width" / "n_analysts" dimension.
- **Almeida & Gaspar (2004-2019, European 50 mega-caps)**: Bloomberg
  12-month consensus targets have **no predictive power over future prices**
  (R^2 ~0); targets are not more informative than a naive current-price
  capitalization forecast; targets found to be positively biased.
- **India 2016-2020 (Kadam & Sethi 2024)**: 63% hit rate during the 12mo
  window, 38% at exactly 12mo (close to Bradshaw/Brown/Huang's 64%/38%);
  multiples-based + SOTP hybrid MORE effective than DCF for hitting targets;
  optimism reduces hit rate; higher beta -> bigger errors.
- **ML / LLM vs analysts (recency for deliverable 1's "any 2020-2025 ML/LLM
  paper" ask):**
  - Cao, Jiang, Wang & Yang (SSRN 2024), "Can AI Replace Stock Analysts?" —
    a model-free deep-learning net on raw financial-statement data
    OUTPERFORMS human analysts on 12-month-ahead target price forecasts by
    a large margin, at a cost of "$1,450 equipment, 15 hours, $2.50
    electricity" over a 14-year sample. AI/analyst agreement is higher for
    financially healthier, more liquid, higher-institutional-ownership
    names.
  - SSRN 2023/2024 "The Promise and Peril of Generative AI: Evidence from
    GPT-4 as Sell-Side Analysts" — GPT-4 EARNINGS forecasts are
    SIGNIFICANTLY LESS accurate than analysts'; accuracy degrades beyond
    the model's knowledge cutoff (a caution directly relevant to our
    DeepSeek-only setup and any LLM-in-the-loop leg).
  - Li, Feng, Yang & Huang 2023, "Can ChatGPT reduce human financial
    analysts' optimistic biases?" — ChatGPT forecasts for CSI300 firms show
    materially SMALLER upward bias than human analysts across most
    performance measures, though its own accuracy does not persist as well
    at longer horizons. Directionally: an LLM cross-check is a
    bias-correction tool, not a superior point forecaster.
  - "Deep FinResearch Bench" (2026, arXiv) — benchmarks OpenAI DR, Gemini,
    Perplexity, Grok deep-research agents vs two professional firms on
    3m/6m target hit rate, MAE, mean bias. Best AI hit rates ~57% at 6mo
    (Gemini) vs professional Firm A ~40% at 6mo but with much lower bias
    (+3.6% vs +8-33% for the AI agents) — professionals show better
    CALIBRATION (lower bias) even when hit rate is lower; AI agents are
    NOISIER. Useful evidence for why raw LLM output should feed a
    calibration layer, not be trusted as a point estimate.
  - van Binsbergen, Han & Lopez-Lira 2023 (RFS/Rev.Fin.Studies), "Man versus
    Machine Learning" — a real-time ML benchmark shows analyst earnings
    expectations are upward-biased, increasing in horizon; the bias
    predicts negative cross-sectional returns (the short legs of many
    anomalies are stuffed with over-optimistic-forecast names). Directly
    supports "de-bias the consensus, don't just average it in."

- **Justified multiple mechanics (CFA-curriculum level, for the DCF-lite /
  multiple-leg formulas):**
  - Justified forward P/E = (1-b)/(r-g); justified trailing P/E =
    (1-b)(1+g)/(r-g); b = retention ratio, g = b*ROE (sustainable growth),
    r = cost of equity (CAPM).
  - Justified P/B = (ROE-g)/(r-g).
  - Justified P/S = (E0/S0)(1-b)(1+g)/(r-g).
  - PEG = (P/E) / (expected growth in percentage points).
  - Terminal value in a multi-stage DCF = terminal-year metric x EXIT
    multiple, where the exit multiple should be a mature-company multiple,
    not the subject's own current (often growth-inflated) multiple —
    directly relevant to the DCF-lite leg's terminal-value treatment.

## HEADLINE NUMBERS TO CARRY INTO THE SPEC (owner-facing)
- Consensus targets, pooled across decades of US studies: imply **+20-30%**
  upside on average (Brav-Lehavy ~22-28%; our own IBES receipt 22.76%).
- Hit rate at exactly 12 months: **~24-45%** across studies (Bradshaw et al.
  2005 sample 24%; Bradshaw/Brown/Huang 2013 38%; Kerl 2011 56.5%/73.6%
  "accuracy"-band metric; India 2024 38%). ANY-TIME-during-the-year hit rate
  is much higher: 45-64%.
- Mean optimism bias: **+9-15pp** on implied vs realized return across
  studies (Bradshaw/Brown/Huang +15pp; our IBES receipt +9.78pp mean /
  +6.92pp median).
- Bias is PERSISTENT per analyst (our receipt: Spearman 0.376); accuracy is
  NOT persistent (our receipt: Spearman 0.087; confirmed by
  Bradshaw/Brown/Huang's "weak" persistence finding) — the load-bearing
  asymmetry for deliverable 2's calibration design.
- Information content lives in the REVISION, not the level (Brav-Lehavy;
  Asquith-Mikhail-Au; our own estimate_revisions.py already cites this
  literature for a different purpose) — target LEVEL cross-sectional IC is
  near zero to slightly negative (Zhang: -0.047 pooled Spearman; our IBES
  receipt: 0.0289 pooled IC) UNLESS conditioned on dispersion/agreement.

## STATUS: literature done. Writing the build spec next.

## CRITICAL REPO CONSTRAINT FOUND — MUST GATE DELIVERABLE 2

`backend/services/recommendation.py` (header, verified): the registry
(`backend/services/signal_registry.py`) already ran this exact experiment.
`implied_upside -> expected_return.mu -> certainty_equivalent -> sort` used
the analyst target's cross-sectional ORDER to rank the BUY list. Graded:
**`analyst_target_upside_xs`: PERVERSE/CLOSED, measured at -8 to -18%/yr
GROSS over 21 years of PIT IBES (trial ANALYST-IBES-1, 2026-08-11).**
`PERVERSE` and `REJECTED` are both in `NEVER_PICKS` — a PERVERSE signal is
barred from ever leading a ranking again under its own name.

The registry's own fix, already live: analyst target LEVEL may be used as a
**RISK_INPUT** (`analyst_target_level_haircut` — a per-name haircut/cap/size
discount) but its cross-sectional order may **never** be what sorts the BUY
list — `rank_invariance()` requires Spearman rho == 1.0 when a signal's
values are permuted across names, i.e. a RISK_INPUT/CLOSED signal must be
provably unable to reorder anything.

**This directly constrains Murat's ask** ("we need the analysts' target %
upside to choose stocks in the screener, and the engine itself should be
able to use it"). Two things are true at once:
1. The RAW consensus upside, used to RANK, is a closed, perverse signal —
   re-opening it without new evidence repeats the exact mistake the registry
   exists to prevent (CLAUDE.md: "a null owes two tests," "if it isn't
   pre-registered it didn't happen").
2. A **calibrated** upside (deliverable 2 below) is a different artifact —
   de-biased, PIT, sector/vol/cap-bucket-conditioned, PLUS an interval and a
   hit-rate receipt — and is NOT the same signal ANALYST-IBES-1 tested. It
   is allowed to be TESTED FRESH (a `PRODUCT_EXPERIMENT` licence needs no
   significance gate to enter paper trading — see CLAUDE.md "Three
   Licences"), but it must clear `rank_invariance()`/`audit_leadership()`
   before it is allowed to lead the screener's sort, and until it does, the
   calibrated figure ships as a **RISK_INPUT and a display column** (upside,
   interval, hit-rate-of-this-bucket) — sortable/filterable by the user, but
   not silently driving `ranking_score`. The spec below makes this
   explicit and pre-registers the re-test as its own trial
   (`docs/TRIALS/` via the `pre-register-trial` skill) named e.g.
   `CALIBRATED-TARGET-UPSIDE-1`, scoped explicitly as testing the
   CALIBRATED signal, with ANALYST-IBES-1's parent (the raw ranked upside)
   barred per the Mission's rule 2 ("every mechanism carries an executable
   precursor that is tested on foreign slices with its parent barred").

## ============================================================
## DELIVERABLE 1 — LITERATURE SUMMARY (condensed; full detail above)
## ============================================================
See "LITERATURE — KEY FACTS AND NUMBERS" and "HEADLINE NUMBERS" sections
above. Bottom line for the build:
- Dominant method: forward-P/E x forward-EPS ("justified multiple" heuristic,
  PEG-flavored) — Bradshaw 2002, Asquith-Mikhail-Au 2005. DCF/NPV used by a
  minority. EV/EBITDA, EV/Sales for growth/negative-earnings names, P/B for
  financials, SOTP for conglomerates.
- No correlation between which valuation model an analyst discloses and
  either market reaction or target accuracy (Asquith-Mikhail-Au) — so the
  spec's "three legs" below are a REASONABLE STRUCTURE to combine
  transparently, not a claim that any one method is provably superior.
- Consensus targets imply +20-30% upside on average, hit ~24-45% of the time
  at exactly 12mo, ~45-64% at some point during the 12mo. Mean optimism bias
  +9-15pp. Bias persists per-analyst; accuracy barely does — confirmed by
  our own 1.33M-target IBES receipt.
- Information is in the REVISION, not the level; the level's raw
  cross-sectional IC is near zero to negative unless conditioned on
  dispersion — and, in THIS repo specifically, ranking on the raw level's
  cross-sectional order is an already-CLOSED, PERVERSE signal.
- 2023-2026 ML/LLM evidence is mixed and horizon-sensitive: model-free deep
  learning on financials can beat analysts on 12mo targets (Cao et al.
  2024); generic GPT-4 earnings forecasts are WORSE than analysts and decay
  past the knowledge cutoff; LLMs reduce optimism bias more than they add
  accuracy. Implication for Aegis (DeepSeek-only): an LLM leg belongs in the
  bias-correction/qualitative-adjustment role, not as an unsupervised point
  forecaster, and must be tested for knowledge-cutoff decay like any other
  DeepSeek call per existing house rules.

## ============================================================
## DELIVERABLE 2 — BUILD SPEC: backend/services/price_target.py
## ============================================================

### 0. Scope and licence
`PRODUCT_EXPERIMENT` (per CLAUDE.md Three Licences) for the initial build and
paper-trade integration — no significance gate, no 24-month floor, but a
frozen strategy contract (policy hash, timestamp, inputs, costs, objective)
before the first decision the ENGINE (not just the display) makes with it.
Promotion of the calibrated-upside signal to `PICKER`/rank-bearing status in
`signal_registry.py` requires clearing `rank_invariance()`/
`audit_leadership()` and a pre-registered trial (`CALIBRATED-TARGET-UPSIDE-1`)
per the constraint above — that is a SEPARATE gate from shipping the display
+ RISK_INPUT feature.

### 1. FIRST deliverable, ahead of everything else: a true 12-month figure
Before any new leg is built, fix the horizon bug: add (or reuse
`analyze_stock` with) a `forecast_days=252` (~1 trading year) call path and
report `expected_return_12m` / `median_return_12m` / `p10_12m` / `p90_12m`
computed on THAT terminal distribution — never derived by any root/power/
division from the 5-year run. Keep the existing 5-year fields for path/
drawdown use (renamed for clarity: `expected_return_5y`, `median_return_5y`,
labeled "(5Y)" wherever shown, per the existing correct label on
`stock/[ticker]/page.tsx:604` — the screener and outlook pages must adopt
the SAME labeling discipline). This alone fixes DEFECT #1 (the NVDA
+114.6%-mean-vs-consensus-+49.8% type of gap, driven by mean-of-5y-terminal
skew, not by any economic disagreement).

### 2. Inputs (all free / already-available in this repo)
- yfinance `info`: `forwardEps`, `trailingEps`, `sector`, `industry`,
  `targetMeanPrice`/`targetMedianPrice`/`targetLowPrice`/`targetHighPrice`,
  `numberOfAnalystOpinions`, `recommendationMean`, `marketCap`,
  `dividendRate`/`payoutRatio`, `returnOnEquity`, `beta` — already fetched in
  `stock_analyzer.py` / `analyst_intelligence.py`.
- `backend/services/factor_model.py::decompose_stock` — Fama-French alpha +
  factor loadings, already computed per ticker (reuse for beta/discount rate
  instead of re-fitting).
- FRED risk-free rate (`config["risk_free_rate"]`, already read in
  `stock_analyzer.py`) for CAPM cost of equity.
- Own IBES history (WRDS `ptgsum`/`ptgdet`, PIT via `ibes__ptgsumu`) for
  BOTH (a) the sector x growth-bucket median justified-multiple
  time series (leg 1's calibration target) and (b) the calibration/backtest
  in deliverable (e)/(f).
- `backend/data/optimus/tracker_backtest/analyst_target_grades.json` — the
  per-analyst/per-cohort bias table (bias IS persistent, Spearman 0.376) —
  this is the direct input to leg 3's de-bias step; DO NOT build a skill-
  weighting scheme off `persistence_accuracy` (Spearman 0.087, noise).

### 3. Three legs

**Leg A — Multiple-based ("justified forward P/E" convention).**
```
target_A = forward_eps * justified_multiple
justified_multiple = shrink(
    sector_growth_bucket_median_multiple_trailing5y,   # PIT, from own IBES/CRSP panel
    toward = market_median_multiple,
    weight = f(n_peers_in_bucket, own data_years)       # same shrinkage pattern as
)                                                         # stock_analyzer.py's drift_shrinkage
```
`sector_growth_bucket` = sector x tercile of consensus long-term EPS growth
(or trailing 3y realized EPS CAGR when LT growth is unavailable) x cap tier
— generalizes `relative_valuation.py::_compute_implied_fair_value`'s
peer-median-of-the-moment into a PIT, growth-conditioned, shrunk multiple.
For negative/near-zero EPS names, fall back to `forward_revenue_per_share *
justified_EV/Sales` (same shrinkage machinery) rather than emitting a
degenerate P/E; for financials, fall back to `book_value_per_share *
justified_P/B` using the CFA-standard `(ROE-g)/(r-g)` formula, `r` from
CAPM below.

**Leg B — DCF-lite (3-stage).**
- Stage 1 (yrs 1-3): consensus/forward EPS growth path, fading linearly to
  Stage 2's rate.
- Stage 2 (yrs 4-10): fades toward a GDP-plus-inflation terminal growth cap
  (`config["stocks"]["terminal_growth_cap"]`, e.g. 3-4%, never above the
  risk-free rate — a standard DCF sanity bound).
- Stage 3 (terminal): Gordon-growth OR exit-multiple terminal value, take
  the MIN of the two (never let terminal value run on the subject's own
  current, possibly growth-inflated, multiple — use the SAME PIT
  sector-median mature multiple as leg A, per the CFA/analyst-prep
  convention "the exit multiple should be a mature-company multiple, not
  the subject's own").
- Discount rate: CAPM `r = risk_free_rate + beta * equity_risk_premium`,
  beta from `factor_model.decompose_stock` (market-factor loading) with a
  fallback to yfinance `info["beta"]`; equity_risk_premium from
  `config["stocks"]["drift_shrinkage"]["prior_equity_premium"]` (reuse the
  existing 7% constant already in config.py — do not invent a second one).
- **Report and log the terminal-value SHARE of total value explicitly**
  (typically 60-80% for a 10y-horizon DCF — this is the reason DCF is the
  most assumption-sensitive of the three legs and the literature's weakest
  performer at hitting 12-month targets specifically: Kadam & Sethi 2024
  found DCF LESS effective than SOTP/multiples for target accuracy).
- Discount the resulting fair value back to a 12-MONTH figure by rolling
  the valuation date forward one year within the same model (re-run stage 1
  starting from year 2) rather than dividing the multi-year fair value by
  its horizon — same anti-"/5" discipline as deliverable 1.

**Leg C — Consensus, bias-corrected.**
```
raw_upside = targetMeanPrice / current_price - 1
cohort = bucket_of(sector, cap_tier, n_analysts_bucket)   # matches the
                                                            # analyst_target_grades.json granularity
debias = historical_mean_bias[cohort]                      # from the IBES receipt,
                                                             # refreshed monthly (see calibration loop)
target_C_return = raw_upside - debias
```
No clip, no cap — the correction is additive and learned, not a truncation.
Where per-analyst identity is available (own-collected IBES rows carry
`amaskcd`), prefer analyst-level bias correction over cohort-level (higher
resolution; the receipt shows bias deciles separating -2.8pp to +80.3pp) —
fall back to cohort-level when the analyst isn't in the graded set.

### 4. Combination rule
Inverse-error weights, fit PIT on IBES history, refit monthly:
```
w_leg = (1 / historical_MAE_leg_in_this_cohort^2) / sum_over_legs(1/MAE^2)
target_12m = sum_leg(w_leg * target_leg)
```
`historical_MAE_leg_in_this_cohort` comes from the backtest in (e) below,
computed per sector x cap-tier x era cohort (never pooled globally — a
single global weight hides regime dependence the way the arena's
12-1-momentum composite already burned five months on, per CLAUDE.md's
"THE BOTTLENECK"). Cold-start (a cohort with <20 backtest observations)
falls back to equal weights (1/3 each) with `weight_basis: "COLD_START"`
disclosed in the output.

### 5. Interval, not a point — and a probability of exceeding
The empirical 12-month error distribution of `target_12m - realized_12m`,
binned by sector x realized-volatility-tercile x cap-tier (same bucket
scheme as the Monte Carlo's cap tiers, for consistency), read off the
backtest in (e):
```
p10 = current_price * (1 + target_12m_return + bucket_error_p10)
p50 = current_price * (1 + target_12m_return)
p90 = current_price * (1 + target_12m_return + bucket_error_p90)
prob_exceeds_target_12m = bucket's empirical P(realized_12m_return > target_12m_return)
```
This is an EMPIRICAL calibration interval (conformal-prediction-style: use
the bucket's actual historical error quantiles, not a parametric normal
assumption — target errors are fat-tailed and skewed per every cited study).

### 6. Backtest protocol — IBES 2010-2024, monthly, PIT
For each month t and each name with a live IBES consensus target at t:
- **Arm 1 (ours):** `target_12m` from the combination rule above, using
  ONLY information available as of t (multiples/bias tables refit on data
  strictly before t — walk-forward, matching this repo's existing
  walk-forward discipline).
- **Arm 2 (consensus):** raw `targetMeanPrice` at t, unmodified.
- **Arm 3 (naive control):** `current_price * (1 + trailing_market_drift)`
  — a "current price x (1+drift)" control, exactly as Murat specified.
- Score: absolute % error vs realized 12m return, AND hit rate (realized
  price >= target at any point / at exactly 12mo, both — matching the
  literature's own two conventions so results are comparable to published
  numbers).
- **Per era** (pre-2013 / 2013-2016 / 2016-2020 / 2020-2024, matching this
  repo's existing era convention in `learner/evaluate.py` — do not invent a
  new era scheme) and **per sector x cap-tier cohort** — a global-only
  number is exactly the defect CLAUDE.md's "sample the window before
  believing the t" and "check whether the noise is shared" feedback items
  warn about.
- Multiplicity: BH-FDR at the screening stage (per-cohort comparisons),
  Holm at the export/headline stage — CLAUDE.md §63.
- `n_effective` counts DATE BLOCKS, not name-months (CLAUDE.md §58) — 12-
  month-overlapping targets are not independent observations.
- Cost: none needed for a pure forecast-accuracy backtest (no trades), but
  state explicitly `zero_cost_diagnostic=True`-equivalent framing so nobody
  mistakes this for a tradable-strategy backtest — that is a SEPARATE
  question (whether trading on the calibrated upside earns money net of
  costs), gated as described in the CRITICAL REPO CONSTRAINT section above.

### 7. scripts/price_target_audit.py (the diagnostic Murat asked for)
For every name in the screener universe + tracker universe, print one row:
```
ticker | price | consensus_1y_upside | our_5y_expected(existing, buggy) |
our_5y_annualized(existing CAGR-ized) | our_new_12m_target | 
gap_vs_consensus | attributed_to: [SHRINKAGE | TIER_CAP | CONSENSUS_CLIP |
FIVE_YEAR_CEILING | MEAN_VS_MEDIAN_SKEW | HORIZON_MISMATCH]
```
Attribution logic: recompute each intermediate value from
`stock_analyzer.analyze_stock`'s own locals (shrinkage_weight,
capped_arithmetic, analyst_annual pre/post clip, final_arithmetic,
max_5y_return cap hit y/n) and report which clamp step, if reversed alone,
would close the largest fraction of the gap — a decomposition, not a guess.
Second section of the script: run the deliverable-6 backtest and print the
same per-era, per-cohort abs-error/hit-rate table as a receipt file under
`backend/data/optimus/tracker_backtest/price_target_backtest_<date>.json`
(same convention as `analyst_target_grades.json`), with a `read_me_first`
field, per CLAUDE.md's "a headline number belongs in a receipt."

### 8. The self-correcting loop (Murat: "not caps or limits, but corrections
on every mistake")
Monthly, as new IBES targets resolve to realized 12-month outcomes:
1. Append the new (predicted, realized) pairs to the backtest panel.
2. Refit: (a) the isotonic/quantile calibration map raw-upside ->
   realized-return per sector x vol x cap bucket (leg C's `debias` table
   AND the interval's error quantiles), (b) the inverse-error leg weights.
3. Diff the new calibration curve against last month's — this diff IS the
   "correction," logged as a receipt
   (`price_target_calibration_drift_<date>.json`: per-bucket delta in
   debias magnitude, delta in MAE, delta in leg weights) — the board Murat
   asked for.
4. No hard caps anywhere in this loop. The only bound is the empirical
   support of the training data itself (a bucket with too few observations
   uses the COLD_START equal-weight fallback and a WIDER interval, not a
   clipped point estimate) — this is what makes it "correction, not a
   limit": a genuinely unprecedented +60% consensus move is not truncated
   to 30%, it is mapped through whatever the sector/vol bucket's OWN
   history says +60%-type moves have actually delivered, with a wide
   interval if that bucket has few precedents.
5. Guard: `test_new_gate_against_first_real_case`-style test (per this
   repo's own feedback item) — before shipping calibration v(n+1), replay
   it against the most recent closed month and confirm it does not silently
   degenerate (e.g., collapse to a constant, or produce p10>p90) — a gate
   that cannot go green is a broken gate (CLAUDE.md rule).

### 9. Output schema (JSON)
```json
{
  "ticker": "NVDA",
  "as_of": "2026-09-11",
  "target_12m": {
    "point": 268.10,
    "p10": 195.40,
    "p50": 268.10,
    "p90": 355.20,
    "prob_exceeds": 0.41,
    "return_pct": 22.9
  },
  "legs": {
    "multiple_based": {"value": 251.0, "weight": 0.29, "justified_multiple": 34.2, "peer_median_multiple": 31.5, "shrinkage_weight": 0.35},
    "dcf_lite": {"value": 244.0, "weight": 0.21, "wacc": 0.104, "terminal_growth": 0.035, "terminal_value_share_pct": 71.2},
    "consensus_debiased": {"value": 292.0, "weight": 0.50, "raw_consensus_upside_pct": 49.8, "debias_applied_pp": -12.4, "cohort": "tech_mega_highcoverage"}
  },
  "combination_basis": "inverse_error_pit_2010_2024",
  "calibration": {"bucket": "tech|mega|vol_high", "n_backtest_obs": 812, "mae_pct": 18.3, "hit_rate_12m_pct": 41.2, "hit_rate_anytime_pct": 62.0, "last_refit": "2026-09-01"},
  "consensus_reference": {"mean": 325.0, "median": 320.0, "n_analysts": 58, "raw_upside_pct": 49.8},
  "vs_our_old_method": {"expected_return_5y_pct": 114.6, "median_return_5y_pct": 88.7, "annualized_5y_pct": 16.5, "note": "shown for transition/debug only — do not compare to target_12m, different horizon and statistic"},
  "engine_usage": {"rank_bearing": false, "registry_role": "RISK_INPUT", "reason": "raw upside ranking closed PERVERSE, trial ANALYST-IBES-1; calibrated figure pending CALIBRATED-TARGET-UPSIDE-1"}
}
```

### 10. Stock page / screener surfacing
- Stock page: a "12-Month Target" card beside (not replacing) the existing
  "Analyst Target" — point + p10-p90 band drawn as a horizontal range, our
  hit-rate-on-this-sector/vol-bucket printed directly under it ("this
  method has hit its target 41% of the time on tech mega-caps since 2010"),
  and the 5-year MC fields relabeled and moved to a separate "5-Year Path
  Risk" card (drawdown/prob-loss/tail metrics only — see deliverable 3).
- Screener: replace the `expected_return` sort key's silent 5y-vs-12m
  ambiguity with an explicit `target_12m.return_pct` column, sortable, with
  the interval width and hit-rate shown as secondary columns per Murat's
  "(calibrated upside, interval width, hit rate)" ranking request — but
  the DEFAULT sort stays on whatever `ranking_score` in
  `recommendation.py` already computes (which does NOT currently include
  this signal as rank-bearing, per the registry gate above) until
  CALIBRATED-TARGET-UPSIDE-1 clears `rank_invariance()`.
- Enroll `price_target.py` in `backend/services/signal_reachability.py`
  immediately (a new module with no caller/classification fails the suite
  per CLAUDE.md's DO list) — reachable via the stock router + screener
  serializer, classified `RISK_INPUT` pending promotion.

### 11. Test cases with known answers
- **Multiple-based leg, hand check:** a hypothetical firm, forward EPS
  $5.00, sector-median forward P/E 20x (no shrinkage, i.e. `n_peers` at max
  confidence) -> `target_A = 100.00` exactly; assert to the cent.
- **DCF-lite leg, Gordon-growth closed form:** stage-3-only firm (flat 0%
  near-term growth so stages 1-2 collapse to stage 3), FCF $10/share,
  r=10%, g=4% -> `terminal_value = 10*(1.04)/(0.10-0.04) = 173.33`; assert
  DCF leg reproduces the textbook Gordon-growth number to 2 decimals when
  fed degenerate (flat) growth inputs — this is the DCF unit test's whole
  point: catch a drift-vs-log-return or terminal-year-off-by-one bug the
  way `stock_analyzer.py`'s own Ito-correction comments show this codebase
  has hit before.
- **Consensus-debias leg:** raw upside +50%, cohort historical mean bias
  +9.78pp (the pooled IBES number, usable as a literal fixture) ->
  `target_C_return = 40.22%`; assert no clipping occurs even for a +200%
  raw upside (regression test against the exact defect being removed:
  `np.clip(analyst_1y_return, -0.30, max_cagr)` must not appear anywhere
  in the new module — grep-assert it, matching this repo's own
  grep-guard convention, but per CLAUDE.md rule 10 read the AST/skip
  docstrings so the guard cannot be fooled by a comment describing the old
  bug).
- **Interval coverage:** synthetic backtest fixture with a KNOWN generating
  distribution (e.g., simulate realized returns ~ N(target, sigma) for a
  fake bucket) -> assert empirical p10-p90 band covers ~80% of simulated
  realized outcomes to within Monte-Carlo sampling error — this IS the
  calibration test for deliverable (f) below, run first on synthetic data
  where the truth is known before trusting it on real IBES data.
- **No-look-ahead:** for a given (ticker, month) pair, assert every input
  the combination rule touches (multiples, bias table, leg weights) has an
  `as_of` date strictly before the target's issue date — a PIT violation
  test, matching this repo's existing PIT-discipline test pattern.
- **Horizon regression test:** assert `target_12m.return_pct` is NEVER
  computed via `(1+x)**(1/n) - 1` or `x/n` from any multi-year figure
  anywhere in the module — the literal defect this whole spec exists to
  remove; grep-assert (AST-based) as above.

## ============================================================
## DELIVERABLE — WHAT THE MONTE CARLO SHOULD BE USED FOR INSTEAD
## ============================================================
Keep `monte_carlo.py::simulate_paths` and `stock_analyzer.py`'s jump-
diffusion + GARCH + options-calibrated machinery exactly as-is for what it
is actually good at and was built for: **the PATH, not the level** —
- max drawdown / time-to-recovery distributions,
- probability of a >X% loss within Y months (position sizing, stop
  placement, the CLAUDE.md-mandated "worst case in dollars" print before
  any sizing change),
- tail risk metrics (`tail_risk.py`'s Sortino/Omega/Calmar) for portfolio
  construction,
- scenario/stress inputs to `portfolio_optimizer.py` / `mpc_optimizer.py`.
It should NOT be used, at any horizon, as the source of a headline "expected
return" or "price target" number shown next to a 12-month consensus figure.
**Calibration test for the MC itself** (deliverable 3's explicit ask): for
each sector x vol-bucket cohort, over the same 2010-2024 IBES-anchored
backtest panel, compute the MC's OWN p05-p95 (or p10-p90) band on a
252-trading-day horizon run from each historical starting point, and measure
**coverage**: what fraction of realized 12-month outcomes actually fell
inside the band, per era. A well-calibrated p10-p90 band should contain
~80% of outcomes; report the actual number per era exactly the way
`prediction_confidence.py` already scores confidence, and treat persistent
under-coverage (band too narrow, realized outcomes escaping it too often —
likely given GARCH persistence + jump clustering) or over-coverage (band
too wide, MC uninformative) as its own logged, monthly-refreshed receipt,
symmetric to the price-target calibration drift file in deliverable (part
8) above — same self-correcting-loop discipline, applied to the risk model
instead of the point forecast.

## ============================================================
## DELIVERABLE 3 — WHY A BETTER TARGET DOESN'T ANSWER "MY STOCKS ARE DOWN"
## ============================================================
(drafted; final paragraph goes in the report to the user, not just here)
Brav-Lehavy 2003 and Asquith-Mikhail-Au 2005 both locate the analyst
target's genuine information content in its REVISION — the market reacts
significantly to a target CHANGE and barely differently based on which
valuation model produced it — not in its static 12-month LEVEL, which
across every cited study (Bradshaw/Brown/Huang 2013: 38% at exactly 12mo;
Kerl 2011: 56.5%; Almeida-Gaspar: ~0 predictive R^2 for European mega-caps;
our own IBES receipt: pooled IC 0.029) is hit less than half the time and
carries almost no cross-sectional information about which name does best.
A 12-month target — however carefully built, de-biased, and calibrated — is
a CENTRAL ESTIMATE with a wide, fat-tailed, sector-and-volatility-dependent
error band; it was never going to be a promise, and the literature's own
consensus number (implying +20-30% upside on the AVERAGE stock, every year,
in every study, across three decades) means an accurate target for a stock
that is down a lot will very often still show a big implied upside now,
precisely BECAUSE it is down — that upside number is not new information
about a rebound, it is centered on the base rate. The one deliverable that
actually engages "my stocks have been down a lot" is not a bigger number on
the target card, it is deliverable 2's INTERVAL and hit-rate columns: read
`p10` (what the bucket's worst-quartile outcomes have actually looked like)
beside the point, and read `hit_rate_12m_pct` for names that share this
stock's sector/vol/cap bucket, before deciding anything is "supposed to"
recover on any particular clock.

## STATUS: FULL SPEC WRITTEN. Ready to report to coordinator.

