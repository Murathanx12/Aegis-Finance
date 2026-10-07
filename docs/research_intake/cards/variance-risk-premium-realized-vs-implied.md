# CARD: variance-risk-premium-realized-vs-implied

## Index fields
- topic: Volatility, variance risk premium (realised versus implied)
- mechanism_class: risk_premium, limits_to_arbitrage, estimation_error
- dataset_status: NOT_FOUND

## Citation
Tim Bollerslev, George Tauchen and Hao Zhou (2009), "Expected Stock Returns and Variance Risk
Premia," Review of Financial Studies, 22(11): 4463-4492. DOI 10.1093/rfs/hhp008. Verified by fetching
`https://ideas.repec.org/a/oup/rfinst/v22y2009i11p4463-4492.html` and
`https://api.crossref.org/works/10.1093/rfs/hhp008` on 2026-10-07 (title, authors, volume, issue,
pages, DOI, abstract agree). The Federal Reserve Board working-paper version (FEDS 2007-11, December
2006 draft, listed there under Bollerslev and Zhou) was fetched at
`https://www.federalreserve.gov/econres/feds/expected-stock-returns-and-variance-risk-premia.htm` and
`https://www.federalreserve.gov/Pubs/Feds/2007/200711/200711pap.pdf` (text extracted); every number
below labelled "working paper" is from that draft, not from the journal version.

Peter Carr and Liuren Wu (2009), "Variance Risk Premiums," Review of Financial Studies, 22(3):
1311-1341. DOI 10.1093/rfs/hhn038. Verified by fetching
`https://ideas.repec.org/a/oup/rfinst/v22y2009i3p1311-1341.html` and
`https://api.crossref.org/works/10.1093/rfs/hhn038` on 2026-10-07 (Crossref dates the online record
2008; RePEc gives 2009 for volume 22, issue 3). The May 2004 working-paper version
`https://econwpa.ub.uni-muenchen.de/econ-wp/fin/papers/0409/0409015.pdf` was fetched and its text
extracted for the index-versus-single-stock comparison; its sample (January 1996 to February 2003) and
numbers are that draft's and may differ from the published version.

Turan G. Bali and Armen Hovakimian (2009), "Volatility Spreads and Expected Stock Returns,"
Management Science, 55(11): 1797-1812. DOI 10.1287/mnsc.1090.1063. Verified by fetching
`https://ideas.repec.org/a/inm/ormnsc/v55y2009i11p1797-1812.html` and
`https://api.crossref.org/works/10.1287/mnsc.1090.1063` on 2026-10-07 (abstract only; no numbers
were extracted).

Amit Goyal and Alessio Saretto (2009), "Cross-section of option returns and volatility," Journal of
Financial Economics, 94(2): 310-326. DOI 10.1016/j.jfineco.2009.01.001. Verified by fetching
`https://ideas.repec.org/a/eee/jfinec/v94y2009i2p310-326.html` (RePEc printed no DOI) and
`https://api.crossref.org/works/10.1016/j.jfineco.2009.01.001` (Crossref supplied it) on 2026-10-07
(abstract only; no numbers were extracted).

Ian Dew-Becker and Stefano Giglio (2025), "The Decline of the Variance Risk Premium: Evidence from
Traded and Synthetic Options," Federal Reserve Bank of Chicago Working Paper 2025-17, RePEc handle
RePEc:fip:fedhwp:101806. Verified by fetching `https://ideas.repec.org/p/fip/fedhwp/101806.html` on
2026-10-07 (title, authors, series, abstract). No DOI is listed there; a search also returned an SSRN
abstract page (5525882) that was not fetched.

## The claim, in one sentence
The difference between market-implied variance and recently realised variance of the aggregate stock
market, both observable at time t, predicts the next quarter's market excess return with a positive
sign (a high premium forecasts a high return), most strongly at the quarterly horizon (Bollerslev,
Tauchen and Zhou 2009).

## Mechanism: why the inefficiency could exist, and who is on the other side
- **A priced risk, not a mispricing.** Carr and Wu's working paper finds average variance risk
  premia strongly negative for the S&P 500, S&P 100 and Dow, and reads the sign as "variance buyers
  are willing to suffer a negative average excess return to hedge away upward movements in the index
  return variance" (their wording). The counterparty paying the premium is the hedger buying
  variance; the party earning it is the one selling variance, with option intermediaries in the
  middle (Dew-Becker and Giglio use an intermediary-based model to explain both the premium and its
  recent decline).
- **Why the gap would predict equity returns.** The Bollerslev-Tauchen-Zhou working paper offers the
  intuition that "when the market anticipates high (low) volatility going forward, there is a
  discount (premium) built into prices, in turn resulting in high (low) future returns" (their
  wording), within a general-equilibrium framework of time-varying economic uncertainty and risk
  aversion. On this reading it is compensation for bearing risk rather than a mispricing, so it need
  not self-correct by arbitrage; the open question is whether it is stable.
- **Why it probably does not live in single stocks.** Carr and Wu's working paper reports that the
  mean variance risk premia "are insignificant for all but three of the 35 individual stocks" (1996 to
  2003 sample) and conjectures "the market does not price all return variance variation in each single
  stock, but only prices the variance risk in the stock market portfolio" (their wording; a
  conjecture in the text, not a tested result). The stock-level translations
  have a different mechanism: Bali and Hovakimian read the realised-minus-implied spread as a
  volatility-risk proxy with a negative link to expected returns and the call-put spread as a
  jump-risk proxy with a positive link, and report information flow from individual equity options to
  the stocks, which they read as informed trading. Goyal and Saretto's result is a return to trading
  options (a zero-cost strategy sorted on historical minus at-the-money implied volatility), which a
  stock book cannot hold.

## Assumptions
- Implied variance is model-free (VIX-type), not a Black-Scholes at-the-money number; the
  Bollerslev-Tauchen-Zhou abstract says the results depend crucially on model-free implied
  volatilities and on realised variation built from high-frequency intraday data rather than daily
  data.
- The trailing realised variance is an acceptable stand-in for expected future realised variance. The
  working paper defines the premium as implied minus the realised variance of the previous interval so
  that both legs are known at t, and notes that other studies instead use the ex-post spread (implied
  minus the next interval's realised variance), which is not point-in-time.
- The relation is estimated on a post-1990 sample because the VIX series starts there (the working
  paper says so).
- The premium has not decayed away. Dew-Becker and Giglio's abstract says traded index-option alphas
  have been indistinguishable from zero for about 15 years; that is a statement about the return to
  selling variance, and whether the predictive link for equity returns decayed too is a separate
  question the abstract does not answer.
- No closer substitute for exposure timing: trend and volatility-target controllers are the
  incumbents (`docs/GRAND_ARENA_EXPOSURE.md`).

## Measurable variables: the precursor observable BEFORE the move
The source's variable, from the working-paper text: VRP at t equals IV at t minus RV at t, where IV at
t is the risk-neutral expectation of variation over the next interval (the VIX, a model-free 30-day
measure) and RV at t is the realised variation over the interval that just ended (a sum of five-minute
squared returns within the month). The text states that both are "directly observable at time t".
Their regressions are quarterly, using the last observation in each quarter.

Point-in-time status, stated per leg:
- Implied leg: known at the close of t. The repo's own options surface is an end-of-day object that its
  receipt says to treat as known at t+1 open (`backend/data/optimus/learner/features_options_receipt.json`,
  `pit_note`: "END-OF-DAY object ... known at t+1 open"), so any decision rule built on it must act no
  earlier than the next session.
- Realised leg: must be trailing. The ex-post spread (implied at t minus realised over t to t+1) is
  not an observable at t and is the version many cross-sectional studies use.
- Data source for the index implied leg: the free series is FRED `VIXCLS`
  (`https://fred.stlouisfed.org/series/VIXCLS`, fetched 2026-10-07: CBOE VIX, daily close). The page
  states the data is copyrighted by the CBOE and must be cited, which matters for the public-tool
  deliverable.
- The stock-level cousin that is on disk is `iv_minus_rv_21d`, defined in
  `backend/data/optimus/learner/features_options_receipt.json` as the 30-day at-the-money implied
  volatility minus the annualised trailing 21-session realised volatility of the underlying from CRSP
  daily returns, in volatility units. `learner/features_options.py` calls it "the variance risk
  premium proxy". It is Black-Scholes-type and daily-return based, so by the source's own condition it
  is not the object that was published.

## Sample period and markets
- Bollerslev, Tauchen and Zhou (working paper): the S&P 500 composite index, January 1990 to January
  2005, monthly VIX and five-minute realised variance, quarterly forecast regressions; the published
  abstract says only "post-1990" and the journal sample end was not extracted.
- Carr and Wu (working paper): five stock indexes and 35 individual stocks, OptionMetrics, January
  1996 to February 2003.
- Bali and Hovakimian; Goyal and Saretto: US stocks and options; periods not extracted.
- Dew-Becker and Giglio: equity index options over roughly the past 15 years against longer history,
  plus synthetic options over 100 years (abstract).
- Scope note: vol-of-vol, named in the QUEUE row, is covered by none of the sources fetched and is
  outside this card.

## Effect size as published
- Bollerslev, Tauchen and Zhou (working paper, 1990 to 2005): the variance risk premium alone
  explains 15.14 percent of the variation in quarterly S&P 500 excess returns (adjusted R-squared);
  implied variance alone 6.32 percent; realised variance alone -1.05 percent; the premium plus P/E
  "more than twenty-five percent" (abstract). The coefficient on the premium is positive. These are
  in-sample explained-variation figures on about 60 quarterly observations (arithmetic from the stated
  sample), not out-of-sample forecasts.
- Carr and Wu (working paper): over -50 percent per month for the two S&P 500 indexes and the Dow on
  their log variance risk premium (the log excess return of a long variance-swap position); for single
  stocks the mean log premium is significantly negative for 21 of 35 but the mean premium is
  insignificant for all but three.
- Bali and Hovakimian, Goyal and Saretto, Dew-Becker and Giglio: direction only in the abstracts.

## Known failure modes and post-publication decay
The standing decay and multiplicity references, McLean and Pontiff (2016) and Harvey, Liu and Zhu
(2016), are carried (authors, year, venue, volume and pages, and the McLean and Pontiff DOI) in cards
`post-earnings-announcement-drift` and `markowitz-1952-portfolio-selection`; both were re-checked
against Crossref on 2026-10-07 and are not re-derived here. Neither is specific to this mechanism.

Specific to this mechanism:
- A short sample and in-sample R-squared: about 60 quarterly points from a single 15-year stretch of
  VIX history.
- The result is stated by its authors to depend on model-free implied variance and intraday realised
  variance. A VIX-based version has the first ingredient and lacks the second; the on-disk stock-level
  surface (at-the-money implied volatility, daily-return realised volatility) has neither, so neither
  may reproduce the published result.
- Decay of the premium itself (Dew-Becker and Giglio).
- Single-name premia are small (Carr and Wu), which is the mechanism-level reason the stock-level
  translation has little to harvest.
- This repo's own measured failures of the stock-level translations are in the corpse section.
- For any exposure rule, the binding control is matched-average exposure: in
  `docs/GRAND_ARENA_EXPOSURE.md`, 42 of 45 real controller configurations on the primary bed did not
  clear their own MDE against it, and the document says they "discovered de-risking", not timing.

## What AEGIS has on disk to test it
The published claim needs two legs, and only one is documented here.
- **Stock-level options surface (documented, bytes not tracked).** `docs/DATA_MANIFEST.md` (line 139)
  lists 29 files `optionm_surface30d_*.parquet`, 71,132,384 rows, 1996-01-04 to 2024-12-31, pulled
  2026-08-19 by `scripts/wrds_training_pull.py`. `docs/DATA_CATALOG.md` (line 85) lists
  `backend/data/optimus/learner/features_options.parquet` at 384.1 MB, 16,055,957 rows, 1998-01-02 to
  2024-12-31, status "ignored" (gitignored), provenance UNKNOWN_PROVENANCE. The tracked receipt
  `backend/data/optimus/learner/features_options_receipt.json` repeats rows 16,055,957 and 8,114
  permnos, gives `iv_minus_rv_21d` a non-null rate of 0.9975 and a median of +0.056 (p05 -0.267, p95
  +0.437, volatility units), and names the builder `learner/features_options.py`. Presence on any
  machine and row counts cannot be confirmed from a git-tracked file; the figures above are the
  documents' own.
- **The QUEUE's lead is narrower than the real holding.**
  `backend/data/optimus/wrds/bulk/optionm_all__stdopd1996.parquet` is a single-year file
  (`docs/DATA_CATALOG.md` lines 88-89: 6,726,186 rows, 1996-01-04 to 1996-12-31); the
  multi-year material is the surface files above and, per `docs/DATA_MANIFEST.md` (line 140),
  `stdopd_events` (21,102,886 rows, 2006-01-03 to 2019-12-31).
- **ETF option quotes.** `docs/DATA_MANIFEST.md` (line 144): `optionm_etf_quotes`, 11,859,415 rows,
  1999-03-10 to 2025-08-29 (the 27 tracked meta files, for example
  `backend/data/optimus/wrds/optionm_etf_quotes/quotes_2013.meta.json`, sum to the same figure; SPY, QQQ,
  IWM, SMH; 14 to 45 days to expiry, moneyness 0.55 to 1.45). These could support an approximate SPY
  model-free implied variance; they are not the CBOE VIX.
- **Realised leg.** `backend/data/optimus/wrds/ff_factors_daily.parquet` (`docs/DATA_MANIFEST.md`
  line 197: 26,274 rows, 1926-07-01 to 2026-06-30; the meta file is tracked, the bytes are not).
- **Implied leg for the index: not found.** No VIX or index implied-variance series appears in
  `docs/DATA_CATALOG.md` or `docs/DATA_MANIFEST.md`. The code pulls it at run time: `VIXCLS` from FRED
  with a key in `backend/services/market_sensor.py` (which refuses by name when offline) and `^VIX`
  through yfinance in `backend/services/backtest.py` and `backend/services/signal_optimizer.py`. Those
  are runtime pulls, not stored datasets.
- **The `vol_compression` family is not this.** `backend/services/strategy_library.py` (line 1141)
  defines the rule as "lowest vol_21 / vol_63" and `scripts/hyp_lab.py` (line 228) as "Volatility
  compression breakout with frictions": a ratio of two realised volatilities, no implied volatility.
  `backend/data/optimus/hyp_lab/LEDGER.md` shows zero verdicts for it. So the QUEUE's "check what the
  family already tested" resolves to: nothing on implied versus realised.

## The falsifiable question and the declared primary metric, with costs
*On the CRSP value-weighted market from the VIX era onward, does an exposure rule that scales equity
exposure with the point-in-time variance-premium proxy (VIX squared, as a variance, minus trailing
realised variance, both at the close of t, acting from t+1) beat the constant exposure with the same
average exposure?* Primary metric: D_matched, the net CAGR difference in percentage points per year
against matched-average exposure, judged against its own 80-percent-power MDE and by-decade-block
signs, exactly the ruler of `docs/GRAND_ARENA_EXPOSURE.md`. Cost model: that document's declared
5.0 bps one-way index-leg cost on the market bed at 0x, 1x and 2x. A time-series replication of the
quarterly regression is secondary and printed by sub-period. Draft for a future pre-registration only.
The sample will be roughly a third of the 1927-2024 bed, so its MDE will be larger than the 1.05 to
2.33 pp per year rulers that document reports for the long bed; that has to be stated before the run.

## Whether a corpse already exists here
Optimus (`brain_query`, `aegis_postmortems`) and Exa were not available in this session; the check
rests on the file searches below.
- **Stock-level translation, closed twice at the sizes those tests could see.** The weekend-lab feature
  screen `backend/data/optimus/weekend_lab_2026-09-06/W5_options_iv_run00_v0.json` (1999-2024, 309
  months, median 2,192 names a month, target `excess_vw_1m` as named in the receipt, PRODUCT_EXPERIMENT):
  `iv_minus_rv_21d` had a raw rank-IC t of -3.54 and a Fama-MacBeth coefficient with momentum, size and
  volatility in the same regression of +0.001493 with t 0.87; by era the monthly means are -0.02%,
  +0.41% and +0.09% (t -0.08, 1.56, 0.26); the receipt says the smallest annual excess it could have
  shown at t 2 is 4.13% per year, and lists the feature among those "killed by the controls". The book
  built on the two features that did survive that screen (the call-put spread and the skew, not the
  premium proxy), `backend/data/optimus/weekend_lab_2026-09-06/W5b_options_book_run03_v0.json`, was
  NOISE (best of 24 cells -0.019% per month), which is context for how little the surface added, not a
  second test of the premium. `NEGATIVE_RESULTS.md` section 27 (TRIAL-OPT-COHORT,
  2026-08-02): the realised-implied spread arm `riv_spread` among seven option-implied arms, all
  REJECTED on the explore window with the confirm window unread (net -47.4 bps per month, t -2.75,
  large/mid at flat 25 bps; -55.2, t -2.88, small), and the family closes.
- **Variance selling as a trade.** `docs/research/AI_PANEL_2026-07-30.md` (section 2, item 1) closed
  options-income at the prior check on Dew-Becker and Giglio's evidence, unregistered.
  `scripts/optionmetrics_core_replay.py` and `scripts/vrp_state_gate.py` document a replay that refuted
  the short put spread "GLOBALLY" (the gate script's wording) and a conditional gate built after it;
  the finding itself lives in the execution repo (`docs/INDEX.md` line 188 flags the pointer as
  broken), and this pass found no tracked receipt for the conditional gate.
- **Options as a volatility forecast, not an alpha.** `docs/TRIALS/PREREG_OPTIONS_RUNG_CONFIRM_1.md`:
  OPTIONS_RUNG_CONFIRMED, volatility IC 0.762 to 0.791, with the caveat that implied volatility "is a
  market vol forecast".
- **The market-level claim as an exposure state: no corpse found.** `docs/GRAND_ARENA_EXPOSURE.md` has
  no VIX or implied-variance controller (a search for vix, implied and vrp returns nothing) and
  `docs/REGIME_ARENA_1.md` conditions on price and macro states only. In the vocabulary of
  `.claude/skills/pre-register-trial/SKILL.md`: the stock-level translation is BLOCKED at the effect
  sizes the two closures could resolve (W5's own MDE is 4.13% per year, and section 27's confirm window
  was never read) and a POWER-type RESURRECTION below that; the market-level exposure translation
  would be a PASS, which means unmatched, not novel.

## hyp_lab family
`risk_timing` - the market-level premium is a state variable for timing equity risk, which is what that family's one cell (H-e1b7ce3a8e, volatility-managed market exposure, FAILED_VARIANT) and its queued successor (H-1270b5a351, NEEDS_CELL) cover; `vol_compression` is realised-volatility-only and does not fit, and the stock-level translation has no family of its own.

## Verdict
**NEEDS_DATA.** The published claim is market-level and needs an index implied-variance series that neither the catalogue nor the manifest holds (free source: FRED VIXCLS, CBOE-copyrighted; no pull was performed), while its stock-level translation, the only version the on-disk surface can test, is already closed twice at the effect sizes those tests could resolve.

The prior is low and the cost near zero: observable-state exposure controllers have a poor record on the matched-exposure ruler (42 of 45 inside their own MDE), a VIX-plus-daily-returns proxy lacks the intraday realised variance the authors call crucial, and a 1990-onward sample is short. It is still the one version of this topic that nothing in the repo has asked.

## needs_evidence
- Does a variance-premium proxy built only from point-in-time inputs (the model-free VIX and trailing realised variance from daily returns, not the intraday measure) reproduce any of the Bollerslev-Tauchen-Zhou predictability out of sample, given the authors' own statement that the result depends on model-free implied variance and high-frequency realised variance?
- Does a premium-keyed exposure rule beat matched-average exposure rather than merely de-risk, on a sample whose MDE will be wider than the 1.05 to 2.33 pp per year rulers of the long bed?
- Did the predictive link for equity returns decay after the published sample, given that Dew-Becker and Giglio document the decay for traded index options only?
