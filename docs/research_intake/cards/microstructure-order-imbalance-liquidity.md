# CARD: microstructure-order-imbalance-liquidity

## Index fields
- topic: Microstructure: signed order-flow imbalance, spread estimators and illiquidity as a predictor
- mechanism_class: structural_friction, information_asymmetry, risk_premium
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Tarun Chordia, Avanidhar Subrahmanyam (2004), "Order imbalance and individual stock returns: Theory and evidence," Journal of Financial Economics, 72(3): 485-518. DOI 10.1016/S0304-405X(03)00175-2.
Verified by fetching https://ideas.repec.org/a/eee/jfinec/v72y2004i3p485-518.html on 2026-10-07 (authors, title, journal, volume, issue, pages read; RePEc prints no abstract or DOI), https://api.crossref.org/works?query.bibliographic=Order+imbalance+and+individual+stock+returns+Theory+and+evidence+Chordia+Subrahmanyam+2004&filter=type:journal-article&rows=3 (first record: JFE 72(3), pages 485-518, 2004, with the DOI above) and the author manuscript dated 7 October 2002 hosted by eScholarship, https://escholarship.org/content/qt34k8f3pv/qt34k8f3pv.pdf, read as text for the abstract, sample and results. The published journal text is paywalled and was not read, so figures below are the manuscript's.

Tarun Chordia, Richard Roll, Avanidhar Subrahmanyam (2008), "Liquidity and market efficiency," Journal of Financial Economics, 87(2): 249-268. DOI 10.1016/j.jfineco.2007.03.005.
Verified by fetching https://ideas.repec.org/a/eee/jfinec/v87y2008i2p249-268.html on 2026-10-07 (authors, title, journal, volume, issue, pages read; no abstract printed) and https://api.crossref.org/works?query.bibliographic=Liquidity+and+market+efficiency+Chordia+Roll+Subrahmanyam+Journal+of+Financial+Economics+2008&filter=type:journal-article&rows=3 (first record gives the DOI above). The abstract text itself was NOT fetched (the Deakin repository returned 403, SSRN 403 and a mirror 503); the claim attributed to this paper below rests on its abstract as summarised in web-search results and is flagged as snippet-level.

Charles M. C. Lee, Mark J. Ready (1991), "Inferring Trade Direction from Intraday Data," Journal of Finance, 46(2): 733-746. DOI 10.1111/j.1540-6261.1991.tb02683.x.
Verified by fetching https://ideas.repec.org/a/bla/jfinan/v46y1991i2p733-46.html on 2026-10-07 (authors, title, journal, volume, issue, pages and abstract read) and https://api.crossref.org/works/10.1111/j.1540-6261.1991.tb02683.x (agrees). The Wiley landing page returned 403.

Shane A. Corwin, Paul Schultz (2012), "A Simple Way to Estimate Bid-Ask Spreads from Daily High and Low Prices," Journal of Finance, 67(2): 719-760. DOI 10.1111/j.1540-6261.2012.01729.x.
Verified by fetching https://ideas.repec.org/a/bla/jfinan/v67y2012i2p719-760.html on 2026-10-07 (bibliographic fields; no abstract printed), https://api.crossref.org/works/10.1111/j.1540-6261.2012.01729.x (agrees) and the authors' NBER conference manuscript, https://conference.nber.org/confer/2009/mms09/Corwin_Schultz.pdf, read as text for the abstract and the TAQ validation figures.

Yakov Amihud (2002), "Illiquidity and stock returns: cross-section and time-series effects," Journal of Financial Markets, 5(1): 31-56. DOI 10.1016/S1386-4181(01)00024-6.
Verified by fetching https://ideas.repec.org/a/eee/finmar/v5y2002i1p31-56.html on 2026-10-07 (bibliographic fields; no abstract printed), https://api.crossref.org/works/10.1016/S1386-4181(01)00024-6 (agrees) and the published article PDF hosted at https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf, read as text (running head "Journal of Financial Markets 5 (2002) 31-56", abstract, data and method). The NYU Stern working-paper record https://archive.nyu.edu/handle/2451/27420 (fetched) holds the earlier version.

## The claim, in one sentence
Daily signed order imbalance (buyer-initiated minus seller-initiated trades) is positively autocorrelated, and one session's imbalance positively predicts the next session's open-to-close return in individual stocks, because inventory-bearing market makers accommodate split orders at a price concession that reverses only slowly (Chordia and Subrahmanyam 2004).

## Mechanism: why the inefficiency could exist, and who is on the other side
Source says (order imbalance). Large traders split their orders, so imbalances are autocorrelated;
market makers with inventory costs accommodate them by moving price, and the resulting price pressure
produces a positive relation between lagged imbalance and return that reverses sign once the current
imbalance is controlled for (Chordia and Subrahmanyam, abstract, manuscript read). The pressure unwinds
slowly: in their multi-lag regressions four of the sixth through tenth lags are negative and
significant, though much smaller than the first lag. The counterparty to a continuation trade is the
inventory-bearing liquidity provider, who sets prices that drift with the imbalance while holding the
opposite inventory, and ultimately the order-splitting trader who pays the concession. The authors
note the strategies are not inconsistent with market efficiency, because inventory models predict that
market makers offer favourable terms for a period in order to offload inventory.

Source says (illiquidity). Amihud (2002) proposes that expected stock return rises with expected
illiquidity, measured as the average daily ratio of absolute return to dollar volume. Over time,
expected market illiquidity raises ex ante excess return while unexpected illiquidity lowers
contemporaneous return, and the effect is stronger for small firms. The counterparty is the investor
who must trade quickly and pays the premium through price impact. Corwin and Schultz (2012) is not a
return mechanism at all: daily highs are almost always buys and lows almost always sells, so the
high-to-low ratio contains both variance and the bid-ask spread, and comparing one-day with two-day
ranges separates them. In this programme it is a cost ruler (`backend/services/matched_twins.py`).
Lee and Ready (1991) is the measurement step that order imbalance rests on: classifying each trade as
a market buy or sell from trade and quote data.

Why predictor rather than cost. The quantity that prices a trade (spread, impact, imbalance pressure)
may also carry expected-return information, because liquidity provision is paid for. The house has
measured that for the LEVEL of illiquidity and found the payment handed back in spread; the signed-flow
version is the part not yet measured. No source in this card claims that the effective-to-quoted spread
ratio predicts returns; that ratio is a cost-model object (it says how much of the quoted spread a
marketable order pays) and the house routes it into the cost function.

## Assumptions
- Trades can be signed correctly. Lee and Ready's own abstract names two problems with quote-based
  classification (quotes recorded ahead of the trades that triggered them, and trades inside the spread
  that are not readily classifiable). Modern market structure adds off-exchange reporting latency and
  many midpoint prints (see the house venue probe below).
- Market makers' inventory costs still bind. Chordia, Roll and Subrahmanyam (2008, snippet-level) report
  the predictability diminishing when spreads are narrower and declining over time with the tick size,
  and the 2013-2024 window is entirely a post-decimal, narrow-spread regime.
- The effect must exist in names liquid enough to trade at the house floor ($10M median dollar volume).
  Chordia and Subrahmanyam's own gradient says it is concentrated in the smallest names.
- Decision timing: the aggregates are final only after the close, so the decision is at the next open.
- No closer substitute. A Lee-Ready imbalance is mechanically correlated with the same session's
  return, so it can be mistaken for one-day reversal or momentum unless it is residualised.

## Measurable variables: the precursor observable BEFORE the move
Source variables (Chordia and Subrahmanyam manuscript): OIBNUM, the daily number of buyer-initiated
minus seller-initiated trades scaled by total trades, and OIBVOL, the same on dollar volume scaled by
total dollar volume, with trades signed by the Lee and Ready procedure (a trade above the quote
midpoint is a buy, below a sell, and at the midpoint the tick test decides; a quote less than five
seconds old is ignored). The move they predict is the next day's open-to-close return.

House analogue, PIT-observable: the TAQ Intraday Indicators carry `total_trade`, `total_vol`,
`total_dv_lr`, `buyvol_lr`, `sellvol_lr`, `buynumtrades_lr`, `sellnumtrades_lr`, `cprc` and `oprc`
per symbol and day (`backend/data/optimus/wrds/taq_iid_2020.meta.json`; the `_lr` suffix is read here as
Lee-Ready classification, which WRDS's own documentation was not fetched to confirm). From these,
OIBNUM is (`buynumtrades_lr` minus `sellnumtrades_lr`) over `total_trade` and OIBVOL is (`buyvol_lr`
minus `sellvol_lr`) over `total_vol`. The tracked meta states the `date` column is the knowledge date
because the intraday aggregates are final after the close, so the observable at the t+1 open is the
session-t imbalance, and the move is the t+1 `oprc` to `cprc` return from the same file. To separate
the signal from beta or noise it must be residualised on the same session's return and the prior
session's return, and read within liquidity bands.

Other house-measurable precursors: the Corwin-Schultz spread from CRSP `askhi` and `bidlo` (rank and
change; the source's own validation reports a pooled stock-month correlation with TAQ effective spreads
of 0.873 for levels and an average monthly cross-sectional correlation of 0.447 for spread CHANGES,
which are different statistics and not directly comparable), and Amihud from CRSP `ret`, `prc` and
`vol`. Point-in-time cautions: CRSP substitutes closing bid and ask for high and
low on a no-trade day (Corwin and Schultz section 2.2); symbols are reused over time, so the IID join
needs the dated link and `sym_suffix IS NULL`.

## Sample period and markets
- Chordia and Subrahmanyam (manuscript): NYSE-Amex stocks, January 1988 to December 1998 (132 months),
  2,378 unique stocks, with ISSM data for 1988-1992 and TAQ for 1993-1998, stocks required on both CRSP
  and the transaction databases. A pre-decimal sample (tick sizes of one-eighth and one-sixteenth).
- Corwin and Schultz (manuscript): validated against TAQ effective spreads for 1993-2005 on CRSP common
  stocks (share codes 10 and 11), sub-periods 1993-1996, 1997-2000 and 2001-2005; applied to all NYSE
  stocks from 1926 to 2005.
- Amihud (published text): NYSE stocks 1963-1997, monthly Fama-MacBeth cross-sections for 1964-1997 (408
  months), returns adjusted for delistings following Shumway (1997).
- Chordia, Roll and Subrahmanyam (2008): sample not read (abstract not fetched).
- AEGIS window available: 2013-2024 for signed flow (12 years of daily TAQ Intraday Indicators), a
  different market-structure regime from every source sample.

## Effect size as published
- Chordia and Subrahmanyam (manuscript, results section 5): about 77% of first-lag OIBNUM coefficients in
  the daily regressions are positive and more than a quarter are positive and significant; the average
  first-lag coefficient is statistically significant only for the three smallest size groups. A strategy
  that buys at the opening ask and sells at the closing bid after a positive prior-day imbalance (and
  reverses after a negative one) earned a statistically significant 0.09% a day over the whole sample,
  falling monotonically from about 0.23% a day in the smallest size quartile to about 0.03% in the
  largest; extreme imbalances (more than two standard deviations) in small firms earned 0.55%. The
  authors state that $10 to $20 online commissions would virtually nullify the profit on a one-lot trade.
- Corwin and Schultz (manuscript): across all stock-months the correlation between TAQ effective spreads
  and the high-low estimate is 0.873 (Roll covariance estimator 0.694, effective tick estimator 0.720),
  with a mean absolute difference of 0.97% (1.75% for Roll). Weekly correlation 0.755.
- Amihud (published abstract and text): ILLIQ has a positive and highly significant effect on expected
  return across NYSE stocks, 1964-1997; the abstract reports no single premium number and none was
  extracted here.
- Lee and Ready: a method paper; its abstract reports no effect size.

## Known failure modes and post-publication decay
The standing references, McLean & Pontiff (2016) and Harvey, Liu & Zhu (2016), are carried with their
numbers in the card `post-earnings-announcement-drift` and are not re-derived here. Mechanism-specific
evidence:
- Capacity and decay of order imbalance. The effect is concentrated in small stocks inside the source's
  own sample (0.23% against 0.03% a day), and Chordia, Roll and Subrahmanyam (2008, snippet-level) say
  predictability falls as spreads narrow. The house's own 2026-09-11 note
  (`docs/research_notes/2026-09-11/ideas_round2/angle3_evidence.md`, item h1) carries a low-tier
  secondary source on post-1998 decline, which is not relied on here, and concludes a strong prior of
  near-total decay in liquid names. No post-2015 after-cost replication was retrieved by that note, and
  one web search in this pass for post-2010 US replications surfaced only non-US or unfetched studies,
  none of which was read.
- Signing quality in the modern market. The house's one name-day venue probe
  (`backend/data/optimus/taq_effective_spreads_v1.meta.json`, AAPL 2026-08-14) found off-exchange prints
  matched to wider prevailing quotes than on-exchange prints (0.98 against 0.66 bps), read by the house as
  the signature of reporting latency, and about 20% of prints at the exact midpoint on both venues.
- The Corwin-Schultz estimator has documented limits: negative estimates (set to zero), unreliable high
  and low for infrequently traded stocks, and sensitivity to overnight returns (the manuscript's
  sections 2.1 to 2.3). The house cross-check in NEGATIVE_RESULTS.md section 25 found Corwin-Schultz one-way
  medians 3.4 to 9.1 times Kyle-Obizhaeva medians (large/mid 25.8-32.2 bps against 3.4-4.2; small
  41.7-49.2 against 11.6-13.1) with a pooled rank correlation of 0.660 (n = 735,523): the
  estimators agree on WHICH names are expensive and disagree on HOW expensive, and the ledger records
  Corwin-Schultz as documented to be biased upward in illiquid names, the names a spread predictor
  would concentrate on.
- Rank information from volatility and liquidity features is a known false-positive channel
  (NEGATIVE_RESULTS.md sections 32 and 34); see the corpse section.
- Survivorship. CLAUDE.md records that `prices_2025_26/bars.parquet` is survivor-selected and
  concentrated in small, illiquid, distressed names, so any illiquidity-premium read there is suspect
  until delisted names are in. The two corpse readings below avoid that panel (CRSP PIT with delisting
  returns charged; the section 59 panel with 32.8% of symbols delisting early). The TAQ IID panel needs
  its own check (needs_evidence 1).

## What AEGIS has on disk to test it
Tracked in git (bytes you can open in this checkout):
- `backend/data/optimus/taq_effective_spreads_v1.jsonl` with `taq_effective_spreads_v1.meta.json`: 4,224
  rows, 184 names and 23 days (15 July to 14 August 2026) of effective and quoted spreads from WRDS
  computed trades. The meta marks it v1, unfiltered for trade condition, odd lot or venue, with verdict status
  DEFERRED; median effective one-way spread 1.076 bps and median effective-to-quoted ratio 0.369. A
  cost-calibration panel with no signing, far too small and short to test a predictor.
- `backend/data/optimus/taq_quoted_spreads_calibration.csv`,
  `backend/data/optimus/cost_curve/taq_spread_regression_v1.json` (log half-spread on log dollar volume,
  log price and volatility; 177 names; R-squared 0.482, leave-one-out 0.402) and
  `backend/data/optimus/wrds/taq_spread_by_liquidity_band.json`.
- Code: `backend/services/spread_estimators.py` (Corwin-Schultz and an AGK edge estimator, with a
  one-way versus round-trip convention audit), `backend/services/matched_twins.py` (`round_trip_spread`:
  the larger of Corwin-Schultz capped at 20% and the 6/10/18/35 bps flat band), and
  `backend/services/liquidity_risk.py` (descriptive Amihud, Roll and Kyle's lambda; the lambda estimator
  regresses absolute return on the square root of UNSIGNED volume although its docstring says signed).
- Tracked meta files for the yearly TAQ Intraday Indicators, `backend/data/optimus/wrds/taq_iid_2013.meta.json`
  through `taq_iid_2024.meta.json`: columns as listed above; rows per year 911,069 (2013), 937,356,
  920,382, 850,700, 782,178, 732,092, 687,482, 646,093, 624,460, 597,959, 566,581 and 546,755 (2024),
  8,803,107 in total (sum of the twelve files' `rows`); pulled 2026-08-19; universe the 6,894-PERMNO
  screened superset. `backend/data/optimus/wrds/TRAINING_SUBSTRATE_V1.json` lists the twelve parquet
  files with byte sizes and hash prefixes (for example 32,380,960 bytes for 2013).
- Corpse receipts: `backend/data/optimus/crsp_rebuild/library_board_LIB_2026-09-29T0802Z__2026-09-29T081355Z.md`,
  `backend/data/optimus/xs_ranker/bakeoff_survivorship_free.json` and
  `backend/data/optimus/wrds/liquidity_migration.json`.

Documented but not tracked (the bytes are gitignored, `.gitignore` line 74 for parquet, so presence and
contents cannot be confirmed from this checkout):
- `backend/data/optimus/wrds/taq_iid_2013.parquet` through `taq_iid_2024.parquet`: the only signed-flow
  data. Raw TAQ trades and quotes are NOT on disk: `scripts/wrds_pull_everything.py` excludes the
  intraday firehoses (`taqm_`, `taqmsec`, `issm`) by design and keeps the server-side `taq_iid`
  aggregates, so the QUEUE row's and `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`'s statement that
  TAQ is on disk means these aggregates and the small panel above, not ticks. A different signing
  convention would need a new server-side WRDS query.
- `backend/data/optimus/wrds/crsp_dsf_1990.parquet` through `crsp_dsf_2024.parquet` (35 files; the
  tracked meta files list `askhi`, `bidlo`, `openprc`, `vol` and `shrout`, for example 1,420,353 rows for
  2002 and 945,529 for 2013): what Corwin-Schultz and Amihud are built from.
- `backend/data/optimus/prices_deep/bars.parquet` and `bars_delisted.parquet`, the survivorship-free
  panel behind NEGATIVE_RESULTS.md section 59 (its receipt is tracked).

Not found: a consumer of the signed columns. The one script that opens the IID files,
`scripts/cross_source_structure_1.py` (function `_liquidity`), reads four numeric columns into a list
and then returns None on both branches, so `buyvol_lr` and `sellvol_lr` have never been used anywhere in
the repository. Also not found in tracked files: the symbol-to-PERMNO link for 2015-2024, since
`backend/data/optimus/wrds/link_taq_crsp.meta.json` reports a window ending 2014-12-31.

## The falsifiable question and the declared primary metric, with costs
Among common stocks above the $10M median-dollar-volume floor in 2013-2024, does the previous session's
volume imbalance (OIBVOL from `buyvol_lr` and `sellvol_lr`, residualised on the same and prior session's
return) rank-predict the next session's open-to-close return, as a long-only top-decile book that beats
a matched random-universe twin (same session, same liquidity band, same one-way turnover) net of the
house cost bracket, with its sign unchanged when any one calendar year is dropped? The deciding metric is
the net mean next-session open-to-close return of the top-decile book in excess of its twin, in basis
points per session, with the t-statistic blocked by calendar month (CANON section 58) and `by_year` and
`leave_one_year_out` printed beside it (CLAUDE.md protocol 11); the top-minus-bottom spread and the
bottom-decile mirror are reported and never deciding, so the construction class is stated
(NEGATIVE_RESULTS.md section 28). Costs: one full round trip per session (buy at the open, sell at the
close), charged to rule and twin by the same function (`matched_twins.trade_cost` with
`round_trip_spread`, the larger of capped Corwin-Schultz and the 6/10/18/35 bps band), with the TAQ
effective half-spread (1.08 bps median in the unfiltered 184-name panel) and Kyle-Obizhaeva as brackets,
because a single cost ruler is never quoted without an interval (NEGATIVE_RESULTS.md section 25). The
minimum detectable effect is to be computed from the realised book-minus-twin series before the cell is
declared, as `scripts/first_books_mde.py` did for Book A. If it graduates it arrives as its own
`PRODUCT_EXPERIMENT` book, never as a weight in `arena_composite` (CLAUDE.md). This is a draft for a
future pre-registration, not a registration.

Separate from the cell, the same panel supports using the prior session's imbalance as a CONTROL
variable in any cross-sectional regression the house runs (the 2026-09-11 note's recommended use), to
ask of any candidate signal whether it merely bought names under buying pressure. That is a diagnostic,
not a hypothesis, and it is not what the verdict below is about.

## Whether a corpse already exists here
Closed, do not re-run (checked in the README's order: NEGATIVE_RESULTS.md at the repo root,
`docs/TRIALS/`, dated research notes, `docs/reviews/`, the FINDING documents; the Optimus brain was not
reachable in this session, so the check rests on the files named):
- **Illiquidity LEVEL (Amihud), long side, CRSP 1991-2024.** Library board
  `backend/data/optimus/crsp_rebuild/library_board_LIB_2026-09-29T0802Z__2026-09-29T081355Z.md`
  (rule minus matched twin, net of costs, %/month, t on 3-month blocks): `illiquid` (highest Amihud,
  20 names) -0.69 (t -2.64, MDE 0.74), holdout 1991-2016 -0.58 (t -2.15), 2017-2024 -1.08 (t -1.38),
  positive in 9 of 34 years; `illiquid_mid_plus` -0.33 (t -1.17); `quiet_volume` -0.36; `turnover_surge`
  -0.45; `small_dv` -0.08, all FAILED_VARIANT; `small_not_illiquid` +0.08 and `big_dv` +0.17
  CANNOT_DISTINGUISH. The CRSP PIT panel is delisting-inclusive with delisting returns charged
  (NEGATIVE_RESULTS.md front matter: 1,463 delistings in 1990-2012), so the survivorship caveat does not
  apply to this reading.
- **The same question on the survivorship-free price panel**, NEGATIVE_RESULTS.md section 59 (receipt
  `backend/data/optimus/xs_ranker/bakeoff_survivorship_free.json`: 5,481,309 rows, 3,578 symbols,
  2016-07-01 to 2026-08-19; 1,573 of 4,793 symbols, 32.8%, stop trading early). The zero-fitted composite
  of dollar volume, Amihud, 63-day skew and 5-day reversal grosses +0.20% to +0.28% per 21 sessions at
  every book size from 10 to 500 (the section's wording) and is net negative at every size against a
  roughly 35 bps small-cap round trip; at a $50M floor its gross falls to -0.18%, so "the edge IS the
  illiquidity". Section 61 (2026-09-24) showed the
  126-session version is gross-positive only because of 2025: +0.12% per hold with 2025 dropped.
- **Rank information alone is not evidence.** NEGATIVE_RESULTS.md sections 32 and 34 measured that
  volatility and liquidity features (named: `vol_12m_low`, `amihud_3m`, `price_level`, `max_ret_low`)
  show mean rank-IC up to 0.05 on panels with zero extractable alpha, and a probability of about 70% of
  an IC t of at least 1.5 on certified null panels, so any cell on these features must read the money
  leg, not the IC.
- **Liquidity-band CHANGE.** `docs/FINDING_2026-08-31_LIQUIDITY_MIGRATION_IS_DISPERSION_NOT_DIRECTION.md`
  (receipt `backend/data/optimus/wrds/liquidity_migration.json`, CRSP 2013-2024, 368,558 usable
  name-months): climbing two or more dollar-volume bands has a lower median 12-month return than flat
  names (-15.31% against +5.45%) and a fatter tail in both directions; a dispersion signal and not a
  directional one, gross of costs and not risk-adjusted.

Not found this pass, so the cells remain open:
- Signed order imbalance as a predictor: no corpse in any of the places above. The 2026-09-11 note (item
  h1) pre-assessed it from the literature (decay since 1998, concentrated in small names, "a
  market-maker's edge", effectively zero capacity as a standalone strategy) and recommended building the
  panel as a control variable instead. That is a literature-based deprioritisation, not a measurement on
  the 2013-2024 data.
- Corwin-Schultz as a predictor (it is used only as a cost) and the effective-to-quoted ratio as a state
  variable: no cell found. The first is expected to inherit the illiquidity-level result, because
  Corwin and Schultz's own footnote says low-frequency liquidity measures such as Amihud's are highly
  correlated with low-frequency spread estimates.

In the `pre-register-trial` vocabulary (read by hand; the linter was not run): re-submitting an Amihud,
dollar-volume or illiquid-book cell would be BLOCKED (adequately powered and refuted on two panels); the
signed-imbalance cell would be PASS, which means unmatched, not novel.

## hyp_lab family
`family_unmapped` - the nearest label by name, `investable_spread`, is a false friend: its only ledger row (H-fe59c56bfe) is long-short RETURN spreads made investable (hedged, short-twin, size-hedged), not bid-ask spreads, so it must not be used here; for an aggregate-illiquidity timing branch the nearest family is `risk_timing`.

## Verdict
**READY_TO_CELL.** Only for the signed-order-imbalance cell, which is powered at a daily horizon, independent of the momentum composite and never run, with a prior of near-zero net edge at the $10M floor so it is a cheap measurement of decay plus a covariate for other cells; the illiquidity-level and Corwin-Schultz-level cells are ALREADY_CLOSED or inherit that closure, and the verdict becomes NEEDS_DATA if the documented TAQ Intraday Indicator files are absent on the machine that runs the cell.

## needs_evidence
- Are `taq_iid_2013.parquet` through `taq_iid_2024.parquet` present on the machine that will run the cell, and is the 2015-2024 universe thinned by a symbol list drawn from a link table whose tracked meta ends 2014-12-31 (rows per year fall from 911,069 in 2013 to 546,755 in 2024, which would make post-2014 listings absent and the out-of-sample years a survivor universe), what share of `total_vol` is left unclassified by `buyvol_lr` plus `sellvol_lr` each year, what does the `_lr` suffix mean in WRDS's documentation, and what maps `sym_root` to PERMNO after 2014; if the files are absent the verdict becomes NEEDS_DATA (one scripted query, `scripts/wrds_training_pull.py`)?
- Is there any gross next-session edge left at the $10M floor after 2013, meaning does the top-decile imbalance book's gross open-to-close excess in the two most liquid size quintiles exceed the cost bracket (TAQ effective half-spread 1.08 bps median in the unfiltered panel plus open and close slippage), given that the source's own largest-quartile edge, already net of buying at the opening ask and selling at the closing bid, was about 3 bps a day in the pre-decimal 1988-1998 sample and Chordia, Roll and Subrahmanyam (2008) report predictability falling as spreads narrow?
- Does Lee-Ready signing hold up on 2013-2024 prints and does the imbalance survive residualisation on the same session's return, given the house venue probe (off-exchange prints matched to wider, possibly stale quotes, about 20% of prints at the midpoint), and does the result read on the money leg and not the rank-IC alone, since NEGATIVE_RESULTS.md sections 32 and 34 measured a false-positive channel for volatility and liquidity features?
