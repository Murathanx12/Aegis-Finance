# CARD: regime-conditioned-signal-trust

## Index fields
- topic: Regime changes and regime-conditioned signal trust
- mechanism_class: risk_premium, behavioural_bias, estimation_error
- dataset_status: TRACKED_IN_GIT

## Citation
Kent Daniel and Tobias J. Moskowitz (2016), "Momentum crashes," Journal of Financial Economics,
122(2): 221-247. DOI 10.1016/j.jfineco.2015.12.002. Verified by fetching
`https://ideas.repec.org/a/eee/jfinec/v122y2016i2p221-247.html` and
`https://api.crossref.org/works/10.1016/j.jfineco.2015.12.002` on 2026-10-07 (title, authors, volume,
issue, pages, DOI, abstract agree). The NBER working-paper PDF
`https://www.nber.org/system/files/working_papers/w20439/w20439.pdf` was also fetched and its text
extracted; the sample, definitions and numbers attributed to the working paper below come from it and
may differ from the journal version.

Michael J. Cooper, Roberto C. Gutierrez Jr. and Allaudeen Hameed (2004), "Market States and
Momentum," Journal of Finance, 59(3): 1345-1365. DOI 10.1111/j.1540-6261.2004.00665.x.
Verified by fetching `https://api.crossref.org/works/10.1111/j.1540-6261.2004.00665.x` on 2026-10-07
(title, authors, volume, issue, pages, DOI) and
`https://api.openalex.org/works/doi:10.1111/j.1540-6261.2004.00665.x` (abstract reconstructed from its
inverted index). The Wiley landing page returned 403, and the RePEc handle I tried returned 404, so
neither is counted.

James D. Hamilton (1989), "A New Approach to the Economic Analysis of Nonstationary Time Series and
the Business Cycle," Econometrica, 57(2): 357-384. DOI 10.2307/1912559. Verified by fetching
`https://ideas.repec.org/a/ecm/emetrp/v57y1989i2p357-84.html` (RePEc printed no DOI) and
`https://api.crossref.org/works/10.2307/1912559` (Crossref supplied it) on 2026-10-07.

Andrew Ang and Geert Bekaert (2002), "International Asset Allocation With Regime Shifts," Review of
Financial Studies, 15(4): 1137-1187. DOI 10.1093/rfs/15.4.1137. Verified by fetching
`https://ideas.repec.org/a/oup/rfinst/v15y2002i4p1137-1187.html` (RePEc printed no DOI) and
`https://api.crossref.org/works/10.1093/rfs/15.4.1137` (Crossref supplied it) on 2026-10-07.

Andrew Ang and Allan Timmermann (2012), "Regime Changes and Financial Markets," Annual Review of
Financial Economics, 4: 313-337. DOI 10.1146/annurev-financial-110311-101808. Verified by fetching
`https://ideas.repec.org/a/anr/refeco/v4y2012p313-337.html` and
`https://api.crossref.org/works/10.1146/annurev-financial-110311-101808` on 2026-10-07. The NBER
Working Paper 17182 (June 2011), `https://www.nber.org/papers/w17182.pdf`, was fetched and its text
extracted; passages quoted below are from that working paper.

## The claim, in one sentence
Momentum profits depend on a state of the market that is observable beforehand: positive after market
gains and negative after market losses (Cooper, Gutierrez and Hameed 2004), and crashing in "panic"
states, after market declines when volatility is high, in a way that is partly forecastable ex ante
(Daniel and Moskowitz 2016), so how much a signal is trusted should be conditioned on a real-time
market state.

## Mechanism: why the inefficiency could exist, and who is on the other side
- **Overreaction that is state-dependent (Cooper, Gutierrez and Hameed).** The abstract frames the
  paper as a test of overreaction theories of short-run momentum and long-run reversal, finds
  momentum profits depend on the market state "as predicted", and finds that the up-market momentum
  reverses in the long run, the signature those theories predict. The abstract does not name the
  counterparty; my reading of the overreaction story is the investor who over-extrapolates after
  market gains.
- **An option-like premium on past losers (Daniel and Moskowitz).** The abstract attributes the low
  ex-ante expected return of momentum in panic states to "a conditionally high premium attached to
  the option like payoffs of past losers". The working-paper text locates the crash on the short
  side: in July and August 1932 the market rose 82% and the winner decile 32% but the loser decile
  232%; from March to May 2009 the market rose 26% and the loser decile 163%; the losers are
  "crashing up". On that evidence the party who loses is whoever is short the losers (the momentum
  investor) and the party paid is whoever holds the past losers' convex upside (my reading of the
  text, not a sentence in it).
- **Regimes as latent states that are learned, not observed.** Hamilton's regime-switching model
  treats shifts in growth as unobserved and estimates them; Ang and Timmermann describe the filtering
  problem of learning about a regime in real time. Ang and Bekaert report (abstract, as returned by the
  fetch tool) that the cost of ignoring regimes is modest for stock-only portfolios and larger once a
  risk-free asset is added. That pattern, little value in regime knowledge when everything held is an
  equity and more when exposure can move to a risk-free asset, resembles what this repo measured for
  cross-sectional choices versus exposure (corpse section), although Ang and Bekaert's setting is
  international equity allocation, not stock selection.

## Assumptions
- The state variable is built only from information at t. Daniel and Moskowitz's bear-market
  indicator, from the working-paper text, equals 1 if the cumulative CRSP value-weighted market
  return over the past 24 months is negative; the market-variance forecast uses the trailing daily
  returns.
- The conditional mean and variance relations are stable enough that estimates from past data still
  hold. The working paper's dynamic strategy does not establish this recursively: its scale is chosen
  so that the in-sample annualised volatility is 19%, and its normalisation uses the full-sample mean of
  market variance in bear states (the abstract calls the strategy implementable; its state variables
  are ex ante, and as far as I found its parameters are full-sample). A search of the extracted text for
  in-sample, out-of-sample and expanding found the in-sample scaling above, and "out of sample" used
  only for other equity markets and asset classes; the search is not a full read, so this is a
  statement about what I found, not a proof of absence.
- Labels are filtered, not smoothed (next section).
- The book can hold the object the paper tested. The crash is a short-leg event of a long-short
  portfolio; the repo's arena books are long-only, so their exposure to the same states is a market-beta
  statement.

## Measurable variables: the precursor observable BEFORE the move
Market-state variables, all point-in-time at the close of t and acting from t+1: the sign of the
trailing 24-month market return (Daniel and Moskowitz's bear indicator), the sign of the lagged market
return (Cooper, Gutierrez and Hameed's up and down market), and trailing realised market variance from
daily returns.

Regime labels from a model are point-in-time only if they are filtered, and the sources are explicit
about the gap. Ang and Timmermann's working paper notes that Hamilton's regimes "were closely tied to
the notion of recession indicators as identified ex post by the NBER business cycle dating committee";
its Figure 4 plots "the smoothed regime probabilities ... conditioning on the whole sample", which
classify, for example, 1997 to 2003 as a high-volatility regime; and its learning illustration
says the filtered probabilities "track the underlying regime quite accurately, but at times miss an
important regime change ... and at other times issue false alarms". A smoothed probability or an
NBER-style date is a hindsight label; only the filtered probability (information through t) can
condition a real-time decision. This repo already learned the failure mode once: REGIME-ARENA-1's
inherited change-point state read a full-sample variance, so corrupting the future changed past
labels, and only a decision-level perturbation proof caught it.

The AEGIS-specific regime rows (`backend/services/world_state.py`, spec in
`docs/research_notes/2026-10-07/world_state_and_regime_rows_2026-10-07.md`): fixed graded events
(growth: SPY up; rates: TLT up; liquidity: HYG beats IEF; risk appetite: IWM beats SPY; commodities:
USO up; realised stress; plus 13 sector ETFs beating SPY), each stated as a probability by an LLM
reading the news digest at horizons of 1 and 5 sessions, stamped with a made-at time, an entry session
and a resolution date, and graded against base-rate and persistence nulls (plus an EWMA-volatility
null for the realised-stress event). That is a forecast of regime-like events, not a label history. What separates a regime effect from
estimation noise or beta, the question the README requires, is a permuted-label placebo and a
matched-beta twin (below).

## Sample period and markets
- Cooper, Gutierrez and Hameed: US stocks, 1929 to 1995 (abstract).
- Daniel and Moskowitz (working paper): US equities, July 1927 to March 2013 for the dynamic strategy and
  January 1927 to March 2013 for the bear-market regressions; the abstract adds international equity
  markets and other asset classes. The journal sample bounds were not separately extracted.
- Hamilton: US output growth (the abstract refers to GNP); period not extracted.
- Ang and Bekaert: international equity markets (abstract); period not extracted.
- Ang and Timmermann: a survey; no sample of its own.

## Effect size as published
- Cooper, Gutierrez and Hameed (abstract): from 1929 to 1995 the mean monthly momentum profit following
  positive market returns is +0.93%, against -0.37% after negative market returns (the reconstructed
  abstract reads "whereas mean negative -0.37%", so "after negative market returns" is my reading of
  a garbled clause); the up-market momentum reverses in the long run.
- Daniel and Moskowitz (working-paper text): the static winner-minus-loser portfolio has a Sharpe ratio
  of 0.71 against 0.40 for the market, a market beta of -0.58 and an unconditional CAPM alpha of 22.3%
  per year (t 8.5); the abstract says the implementable dynamic strategy "approximately doubles the
  alpha and Sharpe ratio" of the static one. These are long-short figures and the dynamic one uses the
  full-sample parameters described above.
- Ang and Bekaert, Hamilton: descriptive in their abstracts; no headline effect size was extracted.

## Known failure modes and post-publication decay
The standing decay and multiplicity references, McLean and Pontiff (2016) and Harvey, Liu and Zhu
(2016), are carried (authors, year, venue, volume and pages, and the McLean and Pontiff DOI) in cards
`post-earnings-announcement-drift` and `markowitz-1952-portfolio-selection`; both were re-checked
against Crossref on 2026-10-07 and are not re-derived here. Neither is specific to this mechanism.

Specific to regime conditioning:
- Hindsight labels and full-sample parameters, as above.
- Real-time regime tracking misses changes and gives false alarms (Ang and Timmermann).
- The published crash is a long-short, short-leg event; this repo's books are long-only.
- Conditioning has a mechanical cost that has nothing to do with information: `docs/REGIME_ARENA_1.md`
  measured that splitting the trailing estimation window at random, with labels carrying no
  information, cost the selection family 7.024 pp per year (t -3.21, 7 of 7 blocks, 0 of 20 seeds
  positive). Any regime-conditioned rule without a permuted-label placebo will mistake that for a
  finding.
- A trend filter on momentum has already failed here for the standard reason, whipsaw through V-shaped
  rebounds (corpse section).

## What AEGIS has on disk to test it
- **The regime rows themselves: tracked.** The ledger `backend/data/optimus/predictions.jsonl` is
  tracked. Counting its rows whose `model_version` is `regime_v1` at this checkout gives 76, made on two
  UTC dates (2026-10-06 and 2026-10-07), 19 per horizon per date across 18 tickers and 3 observables,
  and none has an outcome or a resolved-at stamp. (The 14 `regime_v0` rows are excluded by rule.) The
  first one-session rows resolve after 2026-10-10 and the first five-session rows after 2026-10-16
  (`docs/research_notes/2026-10-07/world_state_build_2026-10-07.md`). The belief table and scenarios are
  tracked at `backend/data/optimus/world_state/beliefs.json` and
  `backend/data/optimus/world_state/scenarios.json`; the code is `backend/services/world_state.py`.
- **How much history that is.** The same note puts the requirement at about 352 independent entry
  sessions per field to detect a 0.005 Brier improvement at the prior per-date standard deviation of
  0.0335 (about 1.4 trading years, longer for the five-session rows) and about 505 dates for the
  direction arm's trust gate; the C17 review says trust cannot honestly leave zero before about 2028
  unless the effect is large (`docs/reviews/REVIEW_2026-10-07_C17_WORLD_STATE_REGIME.md`, F5). The
  build note records the model answering "within about 0.02 of its baselines on almost every row", so
  any skill will be a small departure from the nulls.
- **Price and macro states for the closed tests: documented, bytes not tracked.**
  `docs/DATA_CATALOG.md` (line 59) lists `backend/data/optimus/aegis_panel/aegis_panel_v2.parquet`,
  4,157,680 rows, 1926-01-30 to 2024-12-31, status ignored; `docs/DATA_MANIFEST.md` (line 197) lists
  `backend/data/optimus/wrds/ff_factors_daily.parquet`. The regime receipts of 2026-08-20 are tracked
  under `backend/data/optimus/regime/`.
- **Rule-based classifier.** `backend/services/regime_detector.py` and
  `backend/services/regime_validator.py` (VIX, VIX term-structure and drawdown thresholds, plus a
  hidden-Markov fit used by the Monte Carlo engine).
- The QUEUE's description of the rows as "freshest, least-tested infrastructure" is accurate, and it is
  also the limitation: for the conditioning question they hold two dates of unresolved forecasts, so the
  usable state history has to come from price and macro series.

## The falsifiable question and the declared primary metric, with costs
*Does conditioning which of the repo's existing selectors is trusted on the news-derived `regime_v1`
state (an information class that differs from the price and macro states already closed) beat making
the same decision unconditionally, against both its own 80-percent-power MDE and a permuted-label
placebo, once at least N_needed independent graded entry sessions exist?* Primary metric: D_cond, the
paired monthly difference in percentage points per year between the conditioned arm and its own
unconditional twin (the identical machinery with the state label deleted), as frozen in
`docs/REGIME_ARENA_1.md`, with the 20-seed permuted-label placebo, a matched-beta twin and a by-year
and leave-one-year-out print (CLAUDE.md protocol 11). Cost model: that document's G7, a Corwin-Schultz
half-spread (median 24.2 bps), 5 bps slippage and 1 bp commission on the one-way traded fraction, at
0x, 1x and 2x. The gate is time, not design: on the C17 review's numbers the question cannot be asked
before roughly 350 independent sessions exist. Draft for a future pre-registration only.

## Whether a corpse already exists here
Yes, many. Optimus (`brain_query`, `aegis_postmortems`) and Exa were not available in this session;
the check rests on the file searches below.
- `docs/REGIME_ARENA_1.md` (GRAND-ARENA-1 chunk 5; 408 simulations, 84 scored arms, 227 evaluation
  months from 2006-01-31 to 2024-11-29 on one CRSP bed; pre-registered in the module repo, whose
  receipts are not in this checkout): conditioning a selection, a signal weighting or a risk model on an
  observable state is "NOT DETECTABLE AGAINST MAKING THE SAME DECISION UNCONDITIONALLY"; 35 of 36 real
  primary arms sit inside their own ruler, the one that does not (`D2|S_BREADTH3`, -7.364 pp per year
  against an MDE of 5.952) is negative and falls to -3.130 against an MDE of 3.951 once beta is matched;
  the cross-sectional oracle is worth 0.64, 1.02 and 1.74 times its own MDE against 10.4 times for
  exposure; most MDEs are 3 to 20 pp per year, so a 2 pp effect could not have been seen; and its
  section 12 says the remaining chunks "should not spend compute conditioning cross-sectional choices on
  a market state".
- `docs/GRAND_ARENA_EXPOSURE.md` (chunk 6): 42 of 45 real exposure controllers on the primary bed did
  not clear their own MDE against matched-average exposure; the exposure oracle is worth +21.563 pp per
  year at 10.4 times its MDE and the best observable controller captured 7.4% of it ("the failure is
  observability, not availability"). The document's daily geopolitical-risk conditioner, a published
  index series in a 2026-07 vintage (so not point-in-time), was detectably harmful on the real-book bed
  (-6.865 pp per year against an MDE of 2.040, 7 of 7 blocks). That is an external index series, not an
  LLM-read belief state, and it was not point-in-time, so it does not close the LLM-news class; it is a
  reason to hold a low prior.
- `backend/data/optimus/regime/` (2026-08-20, tracked): REGIME-ORACLE-CEILING-1 verdict
  `CEILING_STATISTICALLY_PRESENT_BUT_ECONOMICALLY_NEGLIGIBLE` (per the
  `scripts/regime_risk_conditioning_1.py` docstring, perfect foresight of the volatility regime nets
  +0.24% per year and clears a matched-transition null by +1.00% per year against a 3% per year bar);
  REGIME-RISK-CONDITIONING-1 `CEILING_IS_IN_THE_LEVEL_ONLY`; STATE-OBSERVABLE-1
  `OBSERVABLE_DOES_NOT_REACH_IT`; MARKET-SCALING-1 `MARKET_SCALING_DOES_NOT_HELP`.
- `NEGATIVE_RESULTS.md` section 10 (TRIAL-MOM-TREND, 2017-01 to 2026-06): momentum plus an SPY
  10-month trend cash filter returned 4.8% CAGR, Sharpe 0.307 and max drawdown -61.3%, against 17.9%,
  0.629 and -54.7% unfiltered and 15.3%, 0.871 and -33.7% for SPY, in a window with five V-shaped
  recoveries and no long grinding bear. Section 15 (statistical jump-model rotation: passed explore,
  rejected at confirm, 2022 cost -21.6%) and section 18 (the inflation-gate repair made 2022 worse,
  -23.9%), which adds that "successors need a different information class and inherit both". Section 21
  (TRIAL-COND-VT): conditional volatility targeting's confirm-window drawdown was identical to SPY's
  and 2020 returned +3.28% against +18.33%.
- `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md` cells C06 to C09: the
  revision signal conditioned on market trend and on volatility state, all FAILED_VARIANT against the
  market; the note says "The state dependence is real against the twin, and it is not an edge against
  the market". `docs/research_notes/2026-10-06/fair_twin_reissue_2026-10-06.md`: `mom_12_1_trend` is
  FAILED_VARIANT on the fair twin (t -0.25 full sample; -2.15 net of market in validation).
- `backend/data/optimus/hyp_lab/LEDGER.md`: the `risk_timing` family has one negative cell (H-e1b7ce3a8e,
  volatility-managed market exposure) and a queued successor (H-1270b5a351); `engine/research/vol_managed_momentum.py`
  (TRIAL-VMM) printed a false PASS that `NEGATIVE_RESULTS.md` attributes to survivorship.

Scope, so the closure is not over-read: these close observable price and macro states on one bed for
cross-sectional decisions, regime-to-exposure controllers on replicable beds, and single-trigger
rotation. They do not close a news-derived state, which has no history. In the vocabulary of
`.claude/skills/pre-register-trial/SKILL.md`, price and macro conditioning is BLOCKED where the MDE
allowed a verdict and a POWER-type RESURRECTION where it did not; a news-state cell would be a PASS,
which means unmatched, not novel.

## hyp_lab family
`family_unmapped` - nearest is `risk_timing` (volatility-managed market exposure), but that family times exposure whereas this card routes trust among selectors, a meta-allocation method rather than a return-predicting signal, the same structural gap the Markowitz card records for construction methods.

## Verdict
**ALREADY_CLOSED.** Conditioning selection, weighting or risk model on observable price or macro states is recorded as not detectable (REGIME-ARENA-1: 35 of 36 real arms inside their own ruler, the exception negative and dissolving under beta matching), regime-to-exposure controllers did not beat matched-average exposure on any replicable bed (EXPOSURE-ARENA-1), and single-trigger rotation died at confirm (NEGATIVE_RESULTS sections 15, 18 and 21).

The one open thread is a news-derived state: it is a different information class, but it has 76 unresolved rows over two dates and needs on the order of 350 independent graded sessions before any conditioning cell can be asked, so it is gated by time, not by research.

## needs_evidence
- How many independent graded entry sessions of `regime_v1` exist, and does any field beat its base-rate, persistence and EWMA-volatility nulls, before any conditioning cell is designed (76 unresolved rows over two dates at 2026-10-07, against about 352 sessions needed)?
- Does any state, price, macro or news-derived, beat its permuted-label placebo and its unconditional twin on a second bed with an MDE small enough to see 2 pp per year (REGIME-ARENA-1's MDEs of 3 to 20 pp per year could not)?
- Is a long-short momentum-crash conditional (the published object, a short-leg phenomenon) worth testing at all for a long-only programme, or does its long-only analogue reduce to the de-risking that EXPOSURE-ARENA-1 already measured as DE_RISKING_ONLY?
