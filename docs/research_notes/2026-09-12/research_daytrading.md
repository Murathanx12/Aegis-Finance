# Day-trading lane research — 2026-09-12

## Repo grounding (read before web research)

### Roadmap Lane B (docs/ROADMAP_2026-09-11...md §3)
- Unit = frozen contract + cadence + control twin + forecast row, not "an account".
- B1: PaperBook = Strategy(contract.py, fingerprinted) + cadence in {30m, daily, weekly, quarterly} + created_utc + origin + origin_text + control_twin_id.
- B2: NL -> contract via local model; engine validates (unknown field refusal, zero-cost refusal by construction, universe >=5 names, licence=PRODUCT_EXPERIMENT); prints worst case in $ (n x notional% x stop%); human clicks Hold. No LLM order authority.
- B3: every book gets a twin at creation: same construction/cadence, random universe draw from same liquidity band (RW1 null), + beta-matched long-only twin. Never show a number without its twin.
- B4: cadence scheduler marks from local Alpaca bars (1.25M rows, 3,060 symbols) + yfinance; 30m book marks from minute bars during session; receipt per pass ("nothing to do" invariant 15).
- B5: forecast rows per book: PredictionRecord (belief_state.make_prediction), model = local model or engine, observable=beats_benchmark, benchmark=control_twin, horizon=cadence. pi_ledger_resolve runs in desktop backend -> graded on laptop.
- B6: Regret page - forecasts vs outcomes per book/model, calibration curve, worst miss w/ thesis+counter-thesis.

§11c idea round 2 relevant: #2 disposition-overhang as event conditioner on the (closed) reaction lane -- reaction lane closed but this is a scope-aware conditional question never asked. #7 abstention book vs NEGATIVE_RESULTS §1 (timing loses to buy-hold, +28.3% vs +114.8%).

### contract.py (backend/strategy/contract.py) — Strategy dataclass fields
Strategy(strategy_id, title, universe: Universe, signal: Signal, construction: Construction,
  hold: HoldRule, sizing: Sizing, costs: CostModel, benchmark: Benchmark, objective: Objective,
  loss_budget: LossBudget, licence=PRODUCT_EXPERIMENT, engine="series", engine_params, parents, note)
- Universe(name, source, floor_dollar_vol_usd, min_price_usd, max_names, fingerprint, note)
- Construction(rule="top_k", k=12, weighting="ew", max_single_name=0.20, hysteresis_rank, gross_cap=1.0)
- HoldRule(horizon_periods=21, min_hold_periods=0, roi_ladder={}, stop_loss, trailing_stop, exit_priority, scheduled_review_periods)
- Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10000, overlays=(), params)
- CostModel(transaction_cost_bps=5.0 one-way, slippage_bps=1.0, financing_bps_over_rf, borrow_bps, zero_cost_diagnostic=False) -- constructs portfolio_farm.Policy, refuses zero cost unless diagnostic flag.
- Benchmark(name="SPY", series_key="spy_tr", beta_matched=True, levered_at_budget, is_own_universe_average)
- Objective(name="alpha_intercept", periods_per_year=12, drawdown_budget, utility="risk_adjusted")
- LossBudget(positions_judged, expected_losers, note)
- Window(start, end, label, sealed, periods_per_year=12)
No native "cadence" field on Strategy itself -- cadence lives on PaperBook (B1) wrapping Strategy.
periods_per_year defaults to 12 (monthly) -- an intraday 30m book needs periods_per_year recalibrated (e.g., ~13 30-min bars/session x 252 = ~3,276/yr) for Objective/Window annualization to mean anything.

### NEGATIVE_RESULTS.md corpses directly relevant
- §1 Timing strategy loses to buy-and-hold (+28.3% vs +114.8%, Sharpe 0.432 vs 0.837), 2020-2025. Sell signals fire at VIX>25 which were the best buying windows. -> any "abstention"/market-timing-shaped intraday lane must beat this receipt.
- §46 (N1) insider return does NOT accrue pre-disclosure on 5 filing days -- BUY 0d n=15 n_eff 12.6 post-disclosure +2.30% (MDE 1.48) DETECTABLE; 1d +1.80% (MDE1.76) DETECTABLE; 2d not detectable. Caveat: corpus only 5 filing days deep (1,175/1,589 events filed same day 2026-08-13), so this is a licence to continue not an edge.
- Earnings-reaction lane closed daily (25bps kills long leg; placebo control wins post-2016) -- per task framing.
- PEAD dead in literature; a within-month rank was lookahead (per task framing).

### docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md — CRITICAL, directly bears on Experiment (a)
CRSP daily 2013-2024, decomposed r_overnight vs r_intraday (open-to-close), reconciled against retx (0.0015% failure rate).
- Phenomenon real: universe-wide overnight +10.73bps/day t=8.71; price>=$5 +4.47bps t=3.57; MU +13.24bps t=4.15.
- NOT a bid-ask-bounce artifact: effect STRONGEST in most-liquid quintile (overnight 8.25bps t=5.94, intraday ALSO positive 6.30bps t=3.88) -- weakest in illiquid names. Rejects microstructure story.
- Strategy still LOSES: liquid-quintile overnight-only EW, 3019 sessions: 0bps cost 22.17%/yr Sharpe 1.69 vs buy-hold 41.61%/yr Sharpe 1.86 (buy-hold wins AT ZERO COST). Breakeven one-way cost for overnight-only vs itself ~4.13bps but even winning that race still loses to holding, because intraday leg you'd be sitting out is ALSO positive (+6.30bps) in the liquid names you could actually trade.
- Vol drag: MU intraday "-99.2%" claim is compounding artifact of a zero-mean 222bps/day vol series (exp(-sigma^2 T/2) = -52.49% pure drag), NOT a real negative intraday edge (t=-0.21).
- Earnings-conditioned slice (7b): mechanism CONFIRMED (overnight gap 2.3x larger on earnings dates: +9.70bps t=3.15 vs +4.30bps no-earnings; intraday flips to -5.89bps t=-1.98 on earnings gaps) but Sharpe on the "bigger" earnings-gap overnight (0.94) ~= no-earnings Sharpe (0.96) -- conditioning finds a BIGGER bet not a BETTER one. Intraday short on earnings gaps (-5.89bps, t=-1.98, p~0.048) doesn't survive multiplicity (~20 slice comparisons run).
- Deployable-now conclusion (no new book needed): execution refinement for EXISTING books -- reduce exposure intraday not overnight (intraday carries ~0 mean at ~4x the overnight variance: 293 vs 69bps/day EW).
- Verdict stamped: ANOMALY_CONFIRMED / STRATEGY_REJECTED, no licence requested.
=> Means: Experiment (a) "overnight vs intraday split" is LARGELY ALREADY DONE at DAILY resolution on CRSP through 2024. The open, un-answered part for a Lane D 30-min-cadence book is (i) whether Alpaca's live minute bars/IEX fills reproduce this on paper with REAL execution frictions and opening-auction mechanics (not modeled in the CRSP study), and (ii) the earnings-day FIRST HOUR specifically (not open-to-close) as its own conditional slice, since 7b used full-session intraday, not first-hour.

### Alpaca opg/auction order finding (docs/HANDOFF_2026-09-03_S36_REVIEW_AND_BUILD.md, docs/SESSION_2026-09-03_SCOREBOARD...md, docs/research_notes/2026-09-11/survey_paper_books.md)
- Alpaca paper does NOT reliably fill tif=opg: 13/15 hack6 auction orders EXPIRED UNFILLED (2026-09-02 tournament). Entry-timing question at the open "cannot be [tested]" via opg orders on paper -- must use marketable/limit orders shortly after 09:30 instead, or accept the open-price fill is not achievable via the order type meant for it.
- Day P&L from that tournament: hack3 +1.19%, hack4 +1.20%, hack6 +0.76% (single day, not a rate).

## Web research (to fill in below)

## Web findings summary (with URLs)
- Barber/Lee/Liu/Odean (Taiwan day traders, "Do Day Traders Rationally Learn About Their Ability?"): <1% of day-trader population reliably earns positive abnormal returns net of fees; ~1.6% profitable in an average year; 80% quit within 2 years, 7% remain after 5 years. https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf
- Chague/De-Losso/Giovannetti 2020 "Day Trading for a Living?" (Brazil equity futures, 2013-2015 cohort): 97% of individuals persisting >300 days LOSE money; only 1.1% earn more than Brazilian minimum wage. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101 ; https://www.tradicted.com/research/chagu-day-2020/
- Jordan & Diltz 2003 (Financial Analysts Journal, 324 US day traders, 1998-99): ~2x as many lose as make money; ~20% "more than marginally profitable"; profitability tied to Nasdaq Composite moves (i.e., beta, not skill). https://www.tandfonline.com/doi/abs/10.2469/faj.v59.n6.2578
- Gao/Han/Li/Zhou 2018 "Market Intraday Momentum" (JFE 129(2):394-414, SPY 1993-2013): first half-hour return predicts last half-hour return, scaled slope 6.94, R^2=1.6%, stronger on high-vol/high-volume/recession/macro-news days; holds on 10 other liquid ETFs. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866
- Lou/Polk/Skouras 2019 "A Tug of War: Overnight vs Intraday Expected Returns" (JFE 134(1):192-213): overnight/intraday return components persist and reverse across each other for YEARS; institutional ownership tracks intraday returns more than overnight; retail-flow explanation. https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- Lopez-Lira & Tang "Can ChatGPT Forecast Stock Price Movements?" (2023-2025 versions): GPT-4 on post-cutoff headlines hits ~90% direction-of-initial-reaction on non-tradable same-instant reaction; ~88.8% on the signed sum of a day's headlines predicting intraday direction; drift continues, strongest in small stocks/negative news. https://arxiv.org/abs/2304.07619
- Glasserman & Lin 2023 "Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis": LLM backtests over training-period text conflate look-ahead bias and a "distraction effect" (general company knowledge swamping the text's actual sentiment); anonymized headlines outperform, i.e. distraction > lookahead as the bigger contaminant. https://arxiv.org/abs/2309.17322 (aligns with repo's own L3 Lookahead-Propensity test, lane L3)
- Opening range breakout: plain-vanilla ORB on SPY 2008-2025 "fails to generate meaningful net-of-fee returns" -- commissions/impact erode gross edge almost entirely; only volatility/volume/trend-filtered variants retain anything, and even those are practitioner (not peer-reviewed) claims. https://concretumgroup.substack.com/p/improving-the-opening-range-breakout
- VWAP reversion: no peer-reviewed after-cost study found; all sources are practitioner/blog claims (55-65% win rate WITH filters, ~45% without, "reversion fails badly on trend days") -- treat as UNVERIFIED, hypothesis-only.
- Option-expiry pinning: 2004 study found average 16.5bp price distortion at strikes on expiry (~$9B aggregate market-cap shift), but later academic/practitioner work is MIXED once vol/volume/news are controlled for -- "hypothesis generator, not a standalone signal."
- Month-end/rebalancing flow: turn-of-month effect well documented (infrequent-rebalancing + risk-deferral models); leveraged-ETF rebalancing flow found to move last-half-hour returns by ~430% of the average last-half-hour return per 1sd flow shock (i.e., real, large, mechanical, and largely already known/priced by sophisticated participants).

## Data/cost infra
- Alpaca IEX free feed: ~2.5% of US equity consolidated volume, up to 30 concurrent streamed symbols on free tier, but REST historical bars go back 7+ years (i.e., IEX-source minute history for backtesting is available free, though the IEX feed itself only reflects IEX's own trades so intraday price/volume is a biased sample of true consolidated tape). https://docs.alpaca.markets/us/docs/market-data-faq ; https://forum.alpaca.markets/t/iex-feed-historical-data/13681
- Alpaca SIP (full consolidated CTA+UTP, 100% volume) = $99/mo "Algo Trader Plus" (also adds OPRA options, 10,000 rpm). https://alpaca.markets/data
- Alpaca paper fill simulation: fills only once marketable vs NBBO-equivalent quote; partial fills 10% of the time at random size; ORDER SIZE NOT CHECKED AGAINST NBBO DEPTH (can fill arbitrarily large size at a quoted price -- unrealistic for anything beyond small size); community reports fill-delay complaints from seconds to minutes. https://docs.alpaca.markets/us/docs/paper-trading ; https://forum.alpaca.markets/t/paper-trading-fill-delays-of-50-260-seconds-limit-orders-filled-minutes-after-price-crossed/18223
- Databento US equities Standard plan $199/mo: unlimited 1s/1m OHLCV history (7 years), 12mo of L0/L1, 1mo of L2/L3. https://databento.com/pricing
- Polygon.io Stocks Starter $29/mo: unlimited calls, 5yr minute aggregates, 100% market coverage, but 15-MIN DELAYED (fine for backtest construction, not live paper decisions); Advanced $199/mo adds real-time + 20yr history. https://polygon.io/pricing

## Arithmetic (computed, not sourced)
1.01^252 - 1 = ~1,127% (252 trading days/yr); task's stated "~1,150%" is the same order (differs only in day-count/compounding convention assumed).
Round-trip cost per day at 1x/2x/4x daily turnover:
 - liquid TAQ 1.08bp one-way: 1x=2.16bp/day, 2x=4.32bp/day, 4x=8.64bp/day
 - retail 25bp one-way: 1x=50bp/day, 2x=100bp/day (=1%, the ENTIRE target), 4x=200bp/day (2%, exceeds target alone)
Gross daily edge needed for 1% net:
 - liquid-cost regime: 1.0216% / 1.0432% / 1.0864% at 1x/2x/4x turnover (cost is nearly irrelevant at institutional TAQ spreads)
 - retail-cost regime: 1.50% / 2.00% / 3.00% gross at 1x/2x/4x turnover
Sessions to power a t=2.8 test of mean=1%/day vs 0, by assumed diversified-book daily sd (n=(t*sd/mean)^2):
 sd=0.5%: n~2 ; sd=1.0%: n~8 ; sd=1.5%: n~18 ; sd=2.0%: n~31 ; sd=3.0% (repo's own EW-universe full-session intraday vol, 293bp/day): n~71 sessions (~3.5 months)
A k=12 EW book (contract.py Construction default) of ~2%/day single-name vol at ~0.3 avg correlation implies book sd ~1.2%/day -> n~11-12 sessions to reach t=2.8 IF the true mean really were 1%/day -- i.e. the statistical bar is not the hard part; finding a real, surviving 1%/day gross mechanism is the entire problem, and none of the cited retail-day-trading literature (Taiwan, Brazil, US 1998-99) documents a population-level edge within orders of magnitude of that.
