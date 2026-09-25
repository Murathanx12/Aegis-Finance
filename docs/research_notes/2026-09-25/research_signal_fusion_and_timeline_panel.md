# Signal fusion (chunk 2) and the timeline panel (chunk 3) — literature + schema (2026-09-25)

Scope: `docs/ROADMAP_2026-09-25_CHUNKS_AND_THE_REVIEW_LOOP.md` §2 rows 2-3. Row 2 spec (verbatim):
`E[r_h] = w_m·ranker + w_a·revision_flow + w_i·(calibrated investigator p→return) + w_t·thesis_verdict +
w_c·catalyst_state + w_s·source_reliability + w_r·regime(market_sensor)`, weights from
`forecast_reputation` (shrink, floor 0, refit each `u_grade`), done when the plan receipt decomposes
E[r] by component and the decision ledger carries that decomposition. Row 3 spec: `world_state_panel`
joining price features + revision flow + news + social + forecasts + thesis verdicts + catalyst
distance + insider/13F/Congress at (ticker, date), graded at 5/21/63/126d, done when the first receipt
says which signals carried information and which are duplicates.

`docs/research_notes/2026-09-25/research_llm_engine.md` §Q3 already specifies the GJP-style pooling
this repo has implemented in `backend/services/forecast_reputation.py` (track-record weight, n/(n+k)
shrinkage, floor+gamma power, logit pooling, kappa extremizing) — that is NOT re-derived below. This
note covers what §Q3 does not: combining components that are not all probabilities (a regression
score, a flow count, a categorical verdict, a calendar distance), and the panel/leakage/redundancy
methodology for chunk 3. Evidence tags: **[STRONG]**/**[MODERATE]**/**[WEAK]**/**[CONTESTED]** as in
the companion note.

Repo grounding used throughout (read this session, not re-derived): `xs_ranker.py` FEATURES (23 cols:
mom_21/63/126/252_21, rev_1/5, vol_21/63, vol_ratio, dollar_vol_log, turnover_surge, trade_surge,
px_vs_52w_high/low, px_vs_ma50/200, amihud, gap_share, vwap_pressure, resid_mom_63, beta_63,
up_days_21, max_drawdown_63, skew_63), `survivorship_audit()`, `top_k_backtest()` with `by_year` /
`leave_one_year_out` / `loo_worst_mean_net`; bars panel = 3,060 live symbols + 1,784 delisted, 2,694
trading dates 2016-01-04→2026-09-21 (`backend/data/optimus/prices_deep/bars.parquet` +
`bars_delisted.parquet`); `analyst/target_revisions.parquet` (393,369 rows, cols ticker/pulled_at/
event_date/firm/from_grade/to_grade/action/target_action/prior_target/current_target/target_change/
pit_safe); `news_corpus/<source>/<date>.jsonl` (fields source, first_seen_utc, published_utc,
tz_source, url, title, body, lang, tickers, entity_tags, raw_id, pit_grade); `web_events.py`
(observed_at / evidence_date / source_url / source_type / event_type / claim / retrieved_by /
confidence_source, by explicit design never a direction+return); `thesis_cards/<date>/<ticker>.json`
(engine_* fields, analyst_actions, consensus_*, upcoming_dates, asof); `pm_catalysts/catalysts_2026-
Q4.yaml`; `aegis_pi.db.pit_observations` (id, key, as_of, observed_at, value, payload, source,
revision — already the PIT contract the rest of the panel should converge on); `predictions.jsonl`
(24,997 rows: prediction_id, ticker, specialist, observable, horizon_days, probability, threshold,
made_at, resolves_after, model, outcome, brier); `decision_ledger.py` (append-only JSONL, states
DECIDED→…→SCORED, keyed on `decision_id`).

---

## PART A — the expected-return layer (chunk 2)

### A1. Timmermann, "Forecast Combinations" (Handbook of Economic Forecasting, 2006)
https://ideas.repec.org/h/eee/ecofch/1-04.html
Core result: simple/equal-weighted combinations frequently beat estimated-optimal-weight combinations
in empirical work, driven by correlation between forecast errors, relative error variances, model
misspecification, non-stationarity, and — the dominant factor when N is large relative to sample
size — **estimation error in the weights themselves**. Companion applied paper (Aiolfi, Capistrán,
Timmermann): across 14 macro variables × 4 horizons × 17 years, equal-weighted survey combos beat the
best individual time-series model ~two-thirds of the time, and equal weights beat estimated
combination weights in 38/56 cases. **[STRONG]** (canonical handbook chapter, replicated applied
result).

### A2. The forecast-combination puzzle — mechanism
Smith & Wallis 2009 (https://onlinelibrary.wiley.com/doi/full/10.1111/j.1468-0084.2008.00541.x) and
Claeskens, Magnus, Vasnev & Wang 2016, "The forecast combination puzzle: A simple theoretical
explanation" (https://janmagnus.nl/papers/forecast%20comb%20puzzle.pdf): when combination weights are
*estimated* rather than known, the combined forecast becomes biased even if the inputs are unbiased,
and its variance is strictly larger than the fixed-weight case (their Proposition 3.1 gives the exact
bias/variance decomposition). Equal-weight variance is just `1'Σ_yy 1 / N²`; estimated-weight variance
carries extra terms from the weight-estimation covariance. **There is no guarantee the "optimal"
estimated combination beats equal weights, or even beats the original forecasts, in finite samples.**
Elliott (https://econweb.ucsd.edu/~grelliott/AveragingOptimal.pdf) bounds the *maximum possible* gain
from optimal weights over averaging at 11% (N=3) / 25% (N=4) of MSFE under empirically realistic
positive-correlation structures — small enough that ordinary estimation noise erases it.
**[STRONG]**. **Direct implication for `expected_return.py`: this system combines ~7 components with,
at least early on, a few dozen to a few hundred graded cycles per component. This is exactly the
regime (few "forecasters", short history) where the puzzle literature says GJP-style estimated weights
can underperform equal weights.** The receipt should carry the equal-weight blend as a standing
comparison and only trust the reputation-weighted blend once it beats equal-weight OOS (§A-formula
below).

### A3. Bayesian Model Averaging (BMA)
Standard formula: posterior model probability `P(M_i | D) ∝ P(D | M_i) P(M_i)`; the BMA forecast is
`Σ_i P(M_i|D) · forecast_i`. Hoeting, Madigan, Raftery & Volinsky, "Bayesian Model Averaging: A
Tutorial" (Statistical Science, 1999) is the standard reference; Diebold & Pauly's shrinkage-toward-
equal-weight scheme (`w_it = λŵ_it + (1-λ)/N`, surfaced in the Stock & Watson handbook chapter found
in A1's search) is explicitly a *partial implementation of BMA* — shrinking toward the equal-weight
prior is BMA with a diffuse-ish prior over models plus a data term. **[STRONG]** as classical
methodology; **[MODERATE]** as a return-forecasting-specific citation (no return-prediction-specific
BMA paper was pulled this session — the tutorial + the handbook mention are the load-bearing sources).
Practically: BMA and the shrink-to-equal-weight recipe are the same move already implemented in
`forecast_reputation.py`'s `k_prior` shrinkage; this is confirmation, not new work.

### A4. Online learning / Hedge (exponentially weighted average forecaster)
Freund & Schapire 1997 (multiplicative weights) / Littlestone & Warmuth 1994 / Vovk 1998; canonical
treatment: Cesa-Bianchi & Lugosi, *Prediction, Learning, and Games* (2006),
https://cesa-bianchi.di.unimi.it/predbook/. Update rule: `p_t(i) ∝ exp(-η · L_{t-1}(i))` where
`L_{t-1}(i) = Σ_{s<t} ℓ_s(i)` is expert i's cumulative loss. Regret bound:
`R_T ≤ ln(N)/η + ηT`, optimized at `η = √(ln N / T)` giving `R_T = O(√(T ln N))` — regret grows only
logarithmically in the number of components N, which matters little here (N≈7) but the *adaptive*
variants matter more: a **"small-loss" bound** `R_T ≤ 3√((L_T(i*)+1) ln N) + 9 ln N` (Haipeng Luo's
lecture notes, https://haipeng-luo.net/courses/CSCI699/lecture4.pdf) means a component that has been
genuinely good pays almost no regret penalty, which is the right property for a system where one
factor (momentum) has historically dominated and others are newly added. **Missing components**
(investigator LLM view absent for most ticker-days, thesis card only monthly): the standard fix in
this literature is the **sleeping experts / specialists** framework (Freund, Schapire, Singer &
Warmuth, "Using and Combining Predictors That Specialize", STOC 1997) — renormalize the softmax over
only the "awake" (available) experts on a given date/name, so an absent component neither gains nor
loses weight that day. **[STRONG]** for Hedge/regret bounds (textbook, widely replicated);
**[MODERATE]** for the sleeping-experts citation (not re-fetched this session, but this is
well-established terminology in the online-learning canon, consistent with the Cesa-Bianchi & Lugosi
table of contents' "simulatable experts" section). Hedge is a genuine alternative/complement to the
GJP recipe already in `forecast_reputation.py`: GJP is essentially a *batch* skill-weighted scheme
re-fit each `u_grade`; Hedge is the *online* version with a regret guarantee that holds even if the
best component changes over time (non-stationarity — exactly the "arm discovering/losing its edge"
concern already logged for the momentum-vs-composite bottleneck in this repo's memory).

### A5. Numerai's meta-model / signal fusion
https://docs.numer.ai/numerai-tournament/scoring/definitions,
https://docs.numer.ai/numerai-tournament/staking, https://blog.numer.ai/achieving-meta-model-supremacy-at-numerai/.
Numerai combines hundreds of submitted models into a **Stake-Weighted Meta Model (SWMM)** — a
stake-weighted average of predictions, where stake is a skin-in-the-game signal a modeler chooses
(not purely a historical-skill statistic) and burns/pays out based on subsequent score, continuously
updating effective weight. Two features transfer directly: (1) **Meta Model Contribution (MMC)** —
gaussianize + rank + orthogonalize a component's prediction against the current meta-model, then take
covariance with the realized target: `mmc_i = cov(orthogonalize(rank(pred_i), rank(meta_model)),
target)`. This is *exactly* the "incremental IC after controlling for existing signals" metric needed
for Part B's redundancy question (§B5) and is a ready template for `expected_return.py`'s component
attribution. (2) Numerai filters to the subset of models that "work well together" by dropping highly
correlated ones before averaging — the same redundancy-pruning idea as §B5's pairwise correlation
check, applied to the fusion step itself, not just the panel audit. **[STRONG]** (production system,
public docs, large live track record).

### A6. "Alpha Illusion" — not found; nearest verified relatives
No paper literally titled "Alpha Illusion" was found this session. The two closest, verified
candidates: (a) **Kelly, Malamud & Zhou, "The Virtue of Complexity in Return Prediction"** (J. Finance
2024, https://doi.org/10.1111/jofi.13298) — proves, contrary to naive intuition, that *more* parameters
(even more than observations) can improve OOS return-prediction Sharpe under the right shrinkage,
because the true "virtue" comes from shrinkage absorbing variance while complexity captures a richer
approximating function — the opposite conclusion from a naive "more signals = more overfitting"
worry, and directly relevant to justifying keeping all 7 components rather than pre-pruning.
**[STRONG]** (top journal, theory + large empirical section). (b) The standard "many signals inflate
false discovery" caution is Harvey, Liu & Zhu, "...and the Cross-Section of Expected Returns" (Review
of Financial Studies, 2016) — proposes a multiple-testing-adjusted significance bar (t>3.0, not 2.0)
for any newly claimed factor; this is well-established common knowledge in the field, flagged here as
**not independently re-verified via fetch this session** (session budget), but it is the correct
citation for the "twenty variants, no multiplicity control" caution CLAUDE.md's `EXPLORE DIRTY, PROMOTE
CLEAN` section already accepts for `PRODUCT_EXPERIMENT` licence work — i.e. the repo has already made
the deliberate choice A6(b) would otherwise urge against, and does so explicitly and by design (the
three-licence system), so this is not a new finding, just confirmation the choice has a name.

### A7. Converting a calibrated probability into an expected return
The naive `EV = p·payoff_up - (1-p)·payoff_down` (binary-outcome expected value, seen in prediction-
market agent literature, e.g. https://agentbets.ai/guides/expected-value-prediction-markets/) is
**insufficient alone** because it needs `payoff_up`/`payoff_down`, i.e. the conditional return
distribution, not just p. Two concrete, implementable routes: (1) **Empirical conditional-distribution
lookup**: bucket historical (arm, horizon) rows by predicted p (deciles), and for each bucket compute
the empirical mean and distribution of realized returns — exactly the pattern `forecast_reputation.py`
already implements as `calibration_curve` (bin of p → realized rate/return, by year). Extending this
from realized *rate* to realized *return* is the direct answer: `E[r | p] = mean_return_in_p_bucket`,
refit each `u_grade`, with the same n<30 shrinkage as elsewhere. (2) **Slope/scaling approach**
(Carver, "Do non binary forecasts work?", https://qoppac.blogspot.com/2020/07/do-non-binary-forecasts-work.html
— **[WEAK]**, practitioner blog not peer-reviewed, but the underlying finding — normalized forecast
strength scales roughly linearly with subsequent risk-adjusted return except at extremes, where it
flattens/reverts — is a useful, cheap-to-validate check before trusting any p→r mapping): fit
`E[r|p] = a + b·(p - 0.5)` on held-out history per arm/horizon, cap at the empirical flattening point.
Route (1) is preferred here since `forecast_reputation.py` already has the machinery; route (2) is a
useful sanity check/fallback when a component has too few resolved rows for a full decile curve
(collapses to two free parameters instead of ~10 bucket means). **[MODERATE]** overall — no single
peer-reviewed paper gives this exact recipe for equity return conversion, but each ingredient
(empirical calibration curves per Primo/Ferro/Jolliffe/Stephenson 2008, https://doi.org/10.1175/2008mwr2579.1,
**[STRONG]** in the meteorological-forecasting literature this technique is borrowed from; isotonic/
Platt calibration is **[STRONG]** standard ML practice) is well supported.

### A8. Shapley decomposition of a linear blend — exact and cheap
Confirmed: Lundberg & Lee, "A Unified Approach to Interpreting Model Predictions" (NeurIPS 2017,
https://arxiv.org/abs/1705.07874), Corollary 1 ("Linear SHAP"): for a linear model
`f(x) = Σ_j w_j x_j + b` under the feature-independence assumption, the Shapley attribution is exactly
`φ_0 = b`, `φ_i = w_i·(x_i - E[x_i])` — no sampling, no kernel approximation needed, because the
`2^|F|` subset-retraining sum that defines Shapley values collapses algebraically for an additive
linear function. This traces to Štrumbelj & Kononenko's earlier observation and Shapley (1953)'s
original result. **[STRONG]** (peer-reviewed, foundational, exact — not an approximation for this
specific case). Direct implication: since `expected_return.py`'s blend is by construction linear
(`E[r] = Σ_c w_c · x_c`), **no SHAP library is needed** — the per-component attribution for any given
name/date is just `w_c · x_c` (raw contribution) or `w_c·(x_c - E[x_c])` (baseline-relative, better for
"which component moved this name away from its typical E[r]"). This is the exact mechanism the roadmap
asks for ("the decision ledger carries the decomposition so the autopsy can say which component was
wrong").

### Concrete formula set for `expected_return.py`

```
# Per component c ∈ {ranker, revision_flow, investigator_p, thesis, catalyst, source_reliability, regime}
# and per (ticker, date, horizon h):

# 1. Convert each raw component score to a return-unit value x_c using its own calibration curve,
#    refit each u_grade cycle, bucketed by (arm/component, horizon h), shrunk when sparse:
x_c        = calib_curve[c][h].lookup(raw_score_c)            # empirical E[r | bucket], §A7
n_c        = calib_curve[c][h].n_obs_in_bucket
x_c_shrunk = (n_c / (n_c + k_prior)) * x_c + (k_prior / (n_c + k_prior)) * population_mean_r[h]

# 2. Component skill weight (reuses forecast_reputation.py's exact recipe, generalized from
#    Brier-skill to IC/return-skill — same functions, different skill metric):
skill_shrunk_c = (n_c / (n_c + k_prior)) * skill_c            # skill_c = held-out IC or return-skill
raw_weight_c   = clip(skill_shrunk_c, floor=0.0, 1.0)         # floor: a worse-than-noise component
                                                               # (persona-arm precedent, §64) gets 0
amp_weight_c   = raw_weight_c ** gamma
w_c            = amp_weight_c / sum_j(amp_weight_j)           # over AWAKE components only (§A4
                                                               # sleeping-experts renormalization) —
                                                               # if 3 of 7 components fire today,
                                                               # normalize over those 3

# 3. Blend (linear — this is what makes step 5 exact):
E_r_h = sum_c( w_c * x_c_shrunk )

# 4. STANDING COMPARISON (§A1-A2, the forecast-combination puzzle): always also compute and store
E_r_h_equal = mean_c( x_c_shrunk )   over awake components
# The reputation-weighted blend is trusted for sizing (u_plan) ONLY once its OOS advantage over
# E_r_h_equal is itself positive and stable across the by-year / LOO check (§58 convention) —
# otherwise fall back to equal-weight. This gate is itself a receipt field (see below), not an
# assumption.

# 5. Attribution (§A8, exact because step 3 is linear):
phi_c = w_c * (x_c_shrunk - population_mean_r[h])    # baseline-relative Shapley value per component
# sum_c(phi_c) + population_mean_r[h] == E_r_h  (sanity check every receipt should assert)
```

### Decision-ledger / plan-receipt fields this implies

Extend the `DECIDED` contract row (`decision_ledger.py`) and `investment_committee`'s plan receipt
with, per (ticker, decision_id, horizon):

- `er_total`, `er_equal_weight` (the standing comparison, §A2)
- `er_by_component`: `{component: {x_raw, x_shrunk, n_obs, skill, weight, phi}}` — the full Shapley
  decomposition so `decision_autopsy.py` can join realized return against `phi_c` per component later
- `weight_source`: `"reputation_v<refit_date>"` vs `"equal_fallback"` — which regime step 4 was in
- `components_awake`: list — which components actually fired for this name/date (sleeping-experts
  bookkeeping; absence is informative, not a zero)
- `calibration_vintage`: id/date of the calibration curves used, so a later recalibration cannot
  silently make an old row unexplainable
- `regime_state_at_decision`: whatever `regime(market_sensor)` returned, verbatim
- `oos_advantage_reputation_vs_equal`: the by-year/LOO-checked number that licenses using the
  reputation weights at all (this is the receipt field a reviewer will ask for first)

---

## PART B — the dot on the timeline (chunk 3)

### B1-B3. Open panels, factor zoos, multimodal datasets

- **alphalens / alphalens-reloaded** (https://github.com/stefan-jansen/alphalens-reloaded, community
  fork of Quantopian's original https://github.com/quantopian/alphalens) — computes exactly the three
  things the roadmap asks the harness to print: **Returns Analysis** (quantile returns, long/short
  spread), **Information Coefficient Analysis** (IC time series, IC by month heatmap, IC histogram/QQ),
  **Turnover Analysis** (quantile turnover, factor rank autocorrelation). `stefan-jansen/alphalens-
  reloaded` is the actively-maintained fork (forks exist with 2025 pushes, e.g.
  `dollmi/alphalens-reloaded` pushed 2025-07-31); the original `quantopian/alphalens` is archived/dead.
  **Not a panel or dataset** — a tear-sheet library that expects a MultiIndex
  (date, asset) → factor value + forward returns frame, i.e. exactly the shape `world_state_panel`
  should be built to. **[STRONG]** as a proven, widely-used methodology; adopt its IC/quantile/turnover
  functions as the reference implementation rather than re-deriving them, but note it does **no PIT or
  survivorship checking** — that stays this repo's job.
- **JKP Global Factor Data** (Jensen, Kelly & Pedersen, "Is There a Replication Crisis in Finance?",
  J. Finance 2023, https://doi.org/10.1111/jofi.13249; data at https://jkpfactors.com/, code at
  https://github.com/bkelly-lab/jkp-data) — 153 factors (406 characteristics in the full download)
  clustered into 13 themes, across 93 countries, built with uniform PIT-respecting construction
  methodology (documented per-characteristic in their PDF documentation). Their central finding
  directly bears on Part B5's "same signal twice" question: the 153+ factors are NOT 153 independent
  ideas — they cluster into 13 themes by construction, and only ~10 of 13 themes survive jointly in a
  tangency-portfolio test controlling for all others. **This is the reference precedent for "cluster
  first, then ask which cluster survives jointly" rather than treating every named signal as
  independent evidence.** **[STRONG]** (top journal, large public dataset, extensively cited).
- **FNSPID** (Dong, Fan & Peng, arXiv:2402.06698, https://arxiv.org/abs/2402.06698; HF dataset
  https://huggingface.co/datasets/Zihan1004/FNSPID) — 29.7M prices + 15.7M time-aligned news records,
  4,775 S&P 500 names, 1999-2023, is the closest match found to a "2025-2026 multimodal financial
  panel" (published 2024, still the most-cited entrant in this space as of this session; no newer
  2025-2026 successor with comparable scale was found via HF hub search — searches for "financial
  multimodal dataset", "stock news price panel", "finance event dataset 2025" returned no results
  distinct from FNSPID). **Explicit finding, itself informative**: FNSPID's own paper states only ~20%
  of price-timestamp rows have a time-aligned news match, and the dataset card carries **no PIT
  caveat** — it uses `published_utc`-style timestamps from news sites, not a documented
  "first observed by us" stamp, which is exactly the look-ahead trap this repo's own `news_corpus`
  ingestion already guards against via `first_seen_utc` (§B4 below). **[MODERATE]** as a usable
  external panel — good for methodology/scale comparison, not safe to ingest directly without adding a
  first-seen discipline on top. No HF search this session surfaced a JKP-style *fundamentals+news+
  social* combined panel with documented PIT columns; that gap is itself the finding — building
  `world_state_panel` with an explicit PIT rule per column (§ schema below) is ahead of, not behind,
  the public state of the art here.

### B4. Leakage traps and the correct handling

- **Look-ahead in news timestamps.** The trap: using `published_utc` (or worse, an article's dateline)
  as the join date when the row was actually first ingested much later — this repo's own
  `news_corpus/alpaca_benzinga_news/2026-09-11.jsonl` contains rows with `published_utc:
  "2015-01-01T13:21:10+00:00"` and `first_seen_utc: "2026-09-11T12:06:30+00:00"` (a Benzinga
  historical-archive backfill), i.e. an 11-year gap between "happened" and "we saw it" in the same
  file — the exact failure mode. **Fix: join `world_state_panel` news columns on `first_seen_utc`,
  never `published_utc`**, consistent with `pit_grade` already present in the schema. General
  principle (López de Prado, *Advances in Financial Machine Learning*, Wiley 2018, ch. 2-3): every
  financial data point needs two timestamps — event time and knowledge time — and only knowledge time
  is admissible for a feature's "as of" date.
- **Survivorship.** Standard trap: building the panel only from names alive at construction time. This
  repo's own `survivorship_audit()` in `xs_ranker.py` and the `bars_delisted.parquet` merge already
  address this for price features (3,060 live + 1,784 delisted); `world_state_panel` must inherit the
  same merged universe for every OTHER column too (news, revisions, thesis cards) — a panel that is
  survivorship-free on price but survivorship-selected on news (e.g. thesis cards only exist for
  currently-covered names) silently reintroduces the bias on the non-price half.
- **Restatement look-ahead.** Using as-reported-today fundamentals for a historical date instead of
  what was actually filed at that date (the Compustat/IBES "point-in-time" vs. "most-recent-vintage"
  distinction — standard in the accounting/finance data literature, not independently re-verified this
  session but uncontested background knowledge). This repo's `target_revisions.parquet` already
  separates `event_date` (what the analyst dated the action) from `pulled_at` (when we captured it) —
  **use `pulled_at`, not `event_date`, as the panel join date**, mirroring the news fix above.
- **Label overlap and the block/embargo unit.** For a 126-session label, any two labels whose windows
  overlap in calendar time are not independent draws — shuffling them into different CV folds leaks
  the test answer into training. Standard fix: **Purged K-Fold CV with embargo**, López de Prado, AFML
  ch. 7 (mechanism confirmed via https://en.wikipedia.org/wiki/Purged_cross-validation and a faithful
  open reimplementation, https://github.com/eslazarev/purged-cross-validation): *purging* removes any
  training row whose label-formation window overlaps the test window; *embargoing* additionally drops
  a fixed post-test buffer (a percentage of the sample, e.g. 5% → 50 rows out of 1,000) to catch
  serial-correlation leakage that isn't strict overlap. The companion statistics that separate real
  skill from selection bias across many such folds are the Probabilistic and Deflated Sharpe Ratio
  (Bailey & López de Prado, 2012/2014) and the Probability of Backtest Overfitting (Bailey, Borwein,
  López de Prado & Zhu). **[STRONG]** — this is exactly the family of techniques this repo's own
  `xs_ranker.top_k_backtest` `by_year`/`leave_one_year_out` fields already approximate at the annual
  granularity; for a 126-day label specifically, the correct non-overlapping block width is **the
  horizon itself** (126 trading sessions ≈ 6 months), not a calendar year — see §B-schema arithmetic
  below, this is the same defect family CLAUDE.md's item 11 already found and fixed for the horizon
  sweep ("re-derive the blocking from the swept parameter in the same commit").

### B5. Detecting "the same signal twice"

- **Pairwise rank correlation of cross-sectional scores.** At each date, rank every name by each
  signal's score; compute Spearman correlation between every pair of signal-rank-vectors; average
  across dates. This is the standard quant-desk diagnostic for redundant alphas (Grinold & Kahn,
  *Active Portfolio Management* — canon reference for IC/signal-correlation methodology, not
  independently re-fetched this session but uncontested standard reference). A pair with average
  |ρ| above some threshold (e.g. 0.6-0.7) is flagged as "possibly the same signal" — the exact
  question the roadmap poses about news vs. momentum.
- **Orthogonalization against known factors.** Cross-sectionally regress each candidate signal's score
  on momentum (mom_21/63/126) and size/liquidity (dollar_vol_log) at each date; the residual is the
  signal's *unique* content. This is standard practice; Numerai's **MMC** (§A5 above) is a live,
  documented, production implementation of exactly this idea generalized to "orthogonalize against the
  current best blend, not just named factors" — `orthogonalize(rank(pred_i), rank(meta_model))` then
  `cov(residual, target)`. Recommend implementing both: orthogonalize against `{mom_21, mom_63,
  mom_126, dollar_vol_log}` (the "is it just momentum/size" check the roadmap names explicitly) AND
  against the current `expected_return.py` blend (the Numerai MMC pattern, for "is it just what we
  already believe").
- **Incremental / marginal IC.** Compute IC of the *full* blend with and without component c; the drop
  when c is removed is c's incremental IC — cheap to compute since the blend is linear (§A8), and
  directly reusable as `skill_c` in the fusion-weight formula above, closing the loop between chunk 2
  and chunk 3's diagnostics.

### B-schema. `world_state_panel`

| column group | example columns | join / PIT rule | source (this repo) |
|---|---|---|---|
| key | `ticker`, `date` | — | — |
| price/technical | 23 `xs_ranker.FEATURES` (mom_21/63/126/252_21, rev_1/5, vol_21/63, vol_ratio, dollar_vol_log, turnover_surge, trade_surge, px_vs_52w_high/low, px_vs_ma50/200, amihud, gap_share, vwap_pressure, resid_mom_63, beta_63, up_days_21, max_drawdown_63, skew_63) | trailing rolling windows ending at `date` inclusive — safe by construction; MUST use the survivorship-merged panel (live + delisted) | `backend/services/xs_ranker.py`, `backend/data/optimus/prices_deep/{bars,bars_delisted}.parquet` |
| analyst revisions | `firm`, `from_grade`, `to_grade`, `action`, `target_action`, `target_change`, aggregated to `net_revisions_90d`, `median_target_change_90d` | join on **`pulled_at`** (when we captured it), never `event_date`; drop rows with `pit_safe == False` | `backend/data/optimus/analyst/target_revisions.parquet` |
| news | per-source counts/sentiment aggregates, e.g. `news_count_5d`, `news_count_30d` | join on **`first_seen_utc`**, never `published_utc`; carry `pit_grade` through | `backend/data/optimus/news_corpus/<source>/<date>.jsonl` |
| web events / OpenClaw quests | `event_type`, `claim`, `confidence_source` aggregated per name | join on **`observed_at`** (module's own explicit design — `evidence_date` is metadata, not the join key) | `backend/services/web_events.py`, `backend/data/optimus/web_events/` |
| LLM forecasts | reputation-weighted `p` at h=1/5 per arm, converted to `x_investigator` per §A7 | join on **`made_at`**; unresolved-at-grading-time rows are `PENDING`, never zero (per `decision_autopsy.py` convention) | `backend/data/optimus/predictions.jsonl`, `backend/services/forecast_reputation.py` |
| thesis verdict | `engine_*` fields, `analyst_actions`, `consensus_*`, `upcoming_dates` | join on the card's own **`asof`**; use the most-recent card **as of** `date`, never a card generated after `date` | `backend/data/optimus/thesis_cards/<date>/<ticker>.json`, `scripts/thesis_cards.py` |
| catalyst distance | `days_to_next_catalyst`, `catalyst_type` | date the calendar entry by **the commit that added/edited it** (`git log --diff-filter=A`), per CLAUDE.md's own receipt-dating rule — never the YAML file's mtime | `backend/data/optimus/pm_catalysts/catalysts_2026-Q4.yaml`, `backend/services/pm_catalysts.py` |
| generic PIT store | `key`, `value`, `revision` | join on **`observed_at`**; this table already IS the target PIT contract — treat it as the schema every other source above should eventually normalize into | `backend/data/aegis_pi.db` / `backend/data/optimus/aegis_pi.db`, table `pit_observations` |
| outcomes | forward return at 5/21/63/126 sessions, cost-adjusted per `xs_ranker.COST_BPS_BY_BAND` | computed strictly from bars dated **after** `date` | `xs_ranker.py`, bars panel |

### B-tables. The first three tables the harness should print

1. **Coverage & survivorship receipt** — per column group: date range, `n_tickers` covered, `%` of
   rows non-null, and (mandatory) how many covered tickers subsequently delisted — a panel where a
   non-price column shows zero delistings among its covered names is selected, per the repo's own
   `survivorship_audit()` convention, even if the price columns already passed.
2. **IC-by-year / LOO / worst-cell, per signal × horizon** — directly extending
   `xs_ranker.top_k_backtest`'s existing `by_year`, `leave_one_year_out`, `loo_worst_mean_net` fields
   to every panel column (not just the price ranker), at all four horizons (5/21/63/126), with
   `n_effective` = number of independent date blocks at that horizon (§ arithmetic below) printed
   beside every IC so a reader cannot mistake row-count for evidence.
3. **Pairwise signal-correlation / redundancy matrix** — average cross-date Spearman correlation
   between every pair of signal scores, plus each signal's incremental IC after orthogonalizing
   against `{mom_21, mom_63, mom_126, dollar_vol_log}` and against the current blend (Numerai-MMC
   style, §B5) — this is the literal receipt the roadmap asks for: "which signals carried information
   about six-month outcomes, and which were the same signal twice."

### Sample-size arithmetic (repo's own §58 convention: count date blocks, not rows)

Panel: 3,060 live + 1,784 delisted names, 2,694 trading dates, 2016-01-04 → 2026-09-21 (~10.7 years,
~252 sessions/year). For a horizon-h label, non-overlapping date blocks ≈ `2,694 / h`:

| horizon h | n_effective (independent date blocks) | order-of-magnitude minimum detectable IC* |
|---|---|---|
| 5d | ≈ 539 | ≈ 0.009 (t≈2) |
| 21d | ≈ 128 | ≈ 0.018 |
| 63d | ≈ 43 | ≈ 0.030 |
| 126d | ≈ 21 | ≈ 0.044 |

\*Illustrative arithmetic, not a fitted number: `SE(mean IC) ≈ sd_block_IC / √n_effective`, using a
placeholder `sd_block_IC ≈ 0.20` (typical order of magnitude for cross-sectional equity IC dispersion);
minimum detectable IC at roughly t≈2 is `2·SE`. **The number of names (3,060) does not enter
`n_effective`** — same-day cross-sectional observations share market-wide noise and are not additional
independent draws, which is precisely why the repo's own convention counts date blocks, not
name-dates, and why CLAUDE.md's item 11 (the t-statistic that grew with horizon partly *because* the
estimator understated its own SE) is the exact failure this table is built to prevent: **the 126-day
row has only ~21 independent blocks over the entire 10.7-year history — any claimed edge at that
horizon needs to survive `leave_one_year_out` at that severity, not just a full-sample t-stat.**

---

## PART C — five external reads on CEO/founder track records, pivots, and political exposure

**1. Larcker & Zakolyukina, "Detecting Deceptive Discussions in Conference Calls"** (J. Accounting
Research 2012, https://doi.org/10.1111/j.1475-679x.2012.00450.x). Linguistic classifiers on earnings-
call Q&A (word categories tied to psychological deception research) predict subsequent restatements;
out-of-sample accuracy 6-16% better than random, comparable to accrual-based models; a portfolio long
low-deception / short high-deception CFO narratives earned an annualized alpha of −4% to −11% for the
high-deception leg. **[STRONG]** (peer-reviewed, still the reference paper; no comparably strong 2023-
2026 LLM-based successor was found this session — searches surfaced only tangential business-model
and rebranding event studies, not a direct successor scoring call evasiveness with an LLM). **Verdict:
TESTABLE now** — this repo already has DeepSeek for text scoring and could score `investigator`-style
evidence packets' underlying earnings-call transcripts (if a transcript source is added) for
deception-linguistic markers, graded against the same `predictions.jsonl` ledger already in place.

**2. Business-model-extension / pivot event studies** — no single canonical "corporate pivot" paper
was found; the closest verified cluster: a 2026 conference paper measuring **business-model-extending
joint-venture announcements** via event study on S&P 500 JVs 1998-2019, finding significant positive
CARs for BME-JVs specifically (not JVs generally), amplified under uncertainty
(https://papers.academic-conferences.org/index.php/ecmlg/article/download/2928/2798/11313); and Zhao,
Calantone & Voorhees, "Identity change vs. strategy change: the effects of rebranding announcements on
stock returns" (J. Academy of Marketing Science 2018, https://ideas.repec.org/a/spr/joamsc/v46y2018i5d10.1007_s11747-018-0579-4.html),
215 rebranding announcements, average positive CAR in a (−5,+5) window, moderated by fit/credibility.
**[MODERATE]** (single-study findings, not a consolidated literature the way CEO turnover is).
**Verdict: PARTIALLY TESTABLE** — the *event detection* half (an 8-K, a name change, a new-segment
disclosure) is buildable from EDGAR + the existing `web_events` typed-event schema; the *return-study*
half needs a hand-labeled or LLM-labeled corpus of "pivot" events this repo does not yet have, so this
is a build-a-labeling-pass item before it is gradeable, not a "run it on data we already hold" item.

**3. Faccio, "Politically Connected Firms"** (AER 2006, https://www.aeaweb.org/articles?id=10.1257%2F000282806776157704,
replication data https://www.openicpsr.org/openicpsr/project/116085/version/V1/view) — 541 politically
connected firms across 47 countries; announcement of a new political connection raises firm value, but
connected firms show *lower* accounting ROE/market-to-book than peers (poor performers seek
connections, or connections are a costly hedge). Companion: Cooper, Gulen & Ovtchinnikov, "Corporate
Political Contributions and Stock Returns" (J. Finance) and a portfolio study finding the
**highest-lobbying-intensity quintile earns ~5.5-6.7%/yr excess return** in years following formation,
consistent with the market underpricing lobbying activity (https://www.zora.uzh.ch/server/api/core/bitstreams/07ed9946-b255-491a-b59a-325efaf6d650/content).
A commercial lobbying-disclosure dataset (FinBrain, https://finbrain.tech/datasets/corporate-lobbying/)
packages the underlying U.S. Senate LDA filings by ticker. **[STRONG]** (peer-reviewed, AER + JF,
replicated across follow-ups). **Verdict: PARTIALLY TESTABLE** — Senate LDA lobbying disclosures are
public/free (same government-filing category as EDGAR), so the raw event data is gettable without a
new paid source, but nothing in this repo currently collects it; once collected it slots directly into
`web_events`'s typed-event schema (`event_type: LOBBYING_DISCLOSURE`) and can be graded like any other
column in `world_state_panel`. Congress-trading-disclosure literature specifically (STOCK Act filings)
was in-scope for the search but yielded no additional academic paper beyond what informs the
lobbying/political-connection literature above — the "does Congress trade on inside information"
question is adjacent but distinct from firm-level political connection, and the roadmap already lists
Congress/13F as an OpenClaw quest target (chunk 4), not a chunk-3 panel column yet.

**4. Forced CEO turnover and forward performance** — a genuinely **[CONTESTED]** literature, which is
itself the finding worth reporting: Denis & Denis (1995) / Huson, Parrino & Starks find *positive*
announcement-period abnormal returns for forced CEO turnover in the US and improved 3-year operating
performance; McColgan (UK sample, https://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2006-Madrid/papers/368955_full.pdf)
and a 2021 MDPI study (https://www.mdpi.com/2227-7072/9/3/34, S&P 1500, 2003-2012) find the *opposite*
sign on average, but a consistent finding across both: **firing an outperforming CEO gets a
significantly worse market reaction than firing an underperforming one** (the 2021 study: ~4.3
percentage-point CAR gap between the two), and **stating a clear (performance-related) reason for
departure produces a positive reaction while giving no reason produces a negative one** — a
transparency effect independent of the turnover's direction. **[MODERATE-STRONG]** (multiple peer-
reviewed event studies, but sign of the average effect is genuinely disputed across samples/eras —
report this as a conditional, not a directional, signal). **Verdict: TESTABLE now** — CEO/CFO turnover
8-Ks are on EDGAR (Item 5.02 filings), the "stated reason" text is exactly the kind of short passage
DeepSeek can classify (performance-stated vs. no-reason-given, outperformer vs. underperformer via
prior 3-year CAR from the existing bars panel), and grading against 5/21/63/126-day forward returns is
a direct `world_state_panel` column with no new data source required.

**5. Founder-CEO premium** — Fahlenbrach, "Founder-CEOs, Investment Decisions, and Stock Market
Performance" (JFQA 2009, https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/founderceos-investment-decisions-and-stock-market-performance/99BFE8A8C1A42F8CC7E32430FD627783)
— an equal-weighted founder-CEO portfolio 1993-2002 earned +8.3%/yr benchmark-adjusted, +4.4%/yr after
controlling for firm/CEO/industry characteristics; Adams, Almeida & Ferreira and Bain & Company's 2016
and Feb-2026 updates (https://www.bain.com/insights/the-magic-of-founder-led-companies-snap-chart/)
corroborate a persistent premium (2.1x TSR since 2015, 2.6x in tech) using more recent data, though
**"The Founder Premium Revisited"** (SSRN, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3977112)
finds the IPO-time valuation premium **decays quickly on the secondary market**, especially for
founder-*CEOs* specifically (vs. founders in a non-CEO board role, where the premium persists longer)
— a genuine boundary condition, not a flat contradiction. **[STRONG]** (multiple peer-reviewed studies
spanning 2003-2026, directionally consistent with one documented decay boundary). **Verdict: TESTABLE
now** — "founder is CEO" is a static, cheaply-labelable fact (proxy statements / company websites, or
even an LLM-read of a company's own "About" page), directly joinable to this repo's existing bars
panel and `xs_ranker` cross-section as a categorical column, gradeable at all four horizons with no new
infrastructure beyond a one-time labeling pass over the current ~3,000-name universe.
