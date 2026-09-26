# Research — OpenClaw-driven strategy discovery (2026-09-26)

Murat, away ~5h: *"work more on the backtest ... use OpenClaw to access the
website — in the beginning of the project we used a website to find backtest
strategies, then upload ours ... OpenClaw can do research on Reddit, on GitHub.
It can do everything. OpenClaw is supposed to be a great tool we are not
utilising."* The site was **QuantConnect** (`docs/V5_CLOSEOUT.md`,
`docs/research/QUANTCONNECT_REPLAY_2026-07-18.md`).

**Licence: `PRODUCT_EXPERIMENT` exploration.** Nothing here is a `RESEARCH_CLAIM`
— no significance gate, no MDE, no preregistration was required to gather it,
per the three-licences rule. Every row below is a candidate to look at, not a
result. Read `backend/data/optimus/strategy_library/LEADERBOARD.md` and
`docs/research_notes/2026-09-26/research_strategy_library.md` (the 113-row
catalogue already seeded 2026-09-26) before adding any of these — the whole
point of this note is to NOT re-find momentum/value/quality/insider/revision
rows that catalogue already has.

**What was done before this session, per V5_CLOSEOUT and the QC replay doc:**
QuantConnect was used once, in July 2026, for exactly one thing — a
third-party-hosted **direction-check replay** of the three reference lane
*mandates* (ETF sleeves, ~30 min of Murat's time, ids recorded in
`QUANTCONNECT_REPLAY_2026-07-18.md`). It was never used to *discover* new
strategies, and "upload ours" (running one of our own `strategy_library` rules
as a LEAN algorithm) was never attempted. This note does the discovery half and
writes the recipe for the upload half (§(b)).

## OpenClaw quest log

Health gate before any browsing: `OC.health()` → `verdict: READY`
(`gateway_probe_ok`, `profile_pinned` to `muratclaw`, `evaluate_allowed=false`,
`messaging_channels=0`). Every quest below ran through
`backend/services/openclaw_client.py::agent()`, model
`deepseek/deepseek-flash`, prompt written to a repo-local temp file (the
`/tmp` path Bash resolves is NOT visible to the native Windows `openclaw.ps1`
subprocess — first attempt failed with `Message file not found`; fixed by
writing prompts under `docs/research_notes/2026-09-26/openclaw_logs/tmp_prompts/`).

| # | quest | elapsed (wall) | status | cost (USD, from usage) | log |
|---|---|---|---|---|---|
| 1 | QuantConnect community Strategies leaderboard | 258.0s | OK, 20 items, no login wall | $0.0605 | `openclaw_logs/q1_quantconnect_strategies.json` |
| 2 | Reddit r/algotrading, 2026 "still works after costs" threads | 257.8s | OK, 11 threads | $0.0784 | `openclaw_logs/q2_reddit_algotrading.json` |
| 3 | Reddit r/quant, 2026 factor/decay/crowding threads | 279.8s | OK, 12 threads | $0.0674 | `openclaw_logs/q3_reddit_quant.json` |
| 4 | X search: "backtest" "Sharpe" "long-only" "factor" "2026" | 174.9s | **BLOCKED** — logged out | $0.0217 | `openclaw_logs/q4_x_quant_accounts.json` |
| 5 | X via search-engine indirection (site:x.com OR site:twitter.com) | 47.0s | **BLOCKED** — Bing served a Cloudflare CAPTCHA, zero results | $0.0033 | `openclaw_logs/q5_x_via_search_engine.json` |

5 of the allowed ≤12 quests were run; total OpenClaw spend **$0.2313** of
the ≤$1.50 budget. Budget was never the binding constraint — browser-profile
authentication state was (see §(c)). Quests 2, 3 and 7 (Quantpedia, GitHub, QC
docs, Composer) were served instead by `exa` (`web_search_exa`/`web_fetch_exa`)
because those pages are static/server-rendered and reading them does not need
a browser agent or Murat's signed-in profile — cheaper and faster, and it
saves the OpenClaw budget for the pages that actually need a live session
(QuantConnect's dynamic leaderboard, Reddit, X).

**Model-pricing caveat, per `docs/OPENCLAW_2026-09-22_SETUP.md`:** every dollar
figure above comes from `usage.input`/`usage.output` tokens priced through
`llm_telemetry`'s house table for `deepseek-flash`. The setup doc's own
warning — *"DeepSeek answered `usage.model=deepseek-flash` from 09-14, an
unpriced model id, which makes every dollar cap a lower bound of $0"* — did
NOT reproduce this session: every one of the 5 calls returned real, non-zero
`usage` and `openclaw_cost_usd` (OpenClaw's own estimate), and the two tracked
independently within ~15% of each other. Treat the $ column as real, not a
declared lower bound of $0, for this specific run — but re-verify on the next
one rather than assuming the caveat is retired.

## (a) Candidate table — NOT already in the library

47 candidates. `id` prefix: `EXT-QC-*` (QuantConnect community leaderboard,
via OpenClaw quest 1) · `EXT-QP-*` (Quantpedia free screener, via `exa`) ·
`EXT-GH-*` (GitHub, via `exa`) · `EXT-CO-*` (Composer symphonies, via `exa`) ·
`EXT-LIT-*` (an academic-literature family the 113-row catalogue missed) ·
`EXT-RD-*` (Reddit-sourced, via OpenClaw quests 2/3 — anecdotal, lowest
confidence) · `EXT-BLOG-*` (an independent practitioner write-up surfaced
while chasing quest 6, kept because it is concrete and dated).

**Read `worst cell (k: CAGR)` and `by_year` on every row of the 113-row
catalogue before trusting any single number here — none of these have been
run through `xs_ranker.top_k_backtest` yet. Every "claimed number" below is a
CLAIM field, never an Aegis-measured one**, per `strategy_library.py`'s own
`ClaimIsNotEvidence` discipline.

| id | source (link) | rule (one line) | claimed number + period | replicable on our panel? (columns) | leak/overfit risk | suggested family |
|---|---|---|---|---|---|---|
| EXT-QC-01 | [quantconnect.com/strategies/536](https://www.quantconnect.com/strategies/536) | 75% 4-model daily ETF regime rotation (RSI/MA-trend/vol-term-structure + QQQ crash guard, TQQQ/SOXL/UVXY/SQQQ) + 25% sector-neutral large-cap momentum top-10 monthly | 5Y CAGR 156.4%, 1Y Sharpe 1.33, 5Y DD 24.2% (leaderboard, 2026-09-26) | Partial — momentum sleeve maps to `mom_252_21`/`dollar_vol_log`; leveraged/inverse ETF regime sleeve is not on our panel | High — QC's own leaderboard scores on 1Y Sharpe with an OOS-length penalty, so it structurally surfaces the newest, highest-variance winners; survivorship of the leaderboard itself (losers get buried) | combination / leveraged-overlay (new family) |
| EXT-QC-02 | [strategies/629](https://www.quantconnect.com/strategies/629) | 3-sleeve long-only, no leverage: large-cap momentum + momentum-breadth w/ cash hedge + leveraged-ETF regime engine, ~1/3 each | 5Y CAGR 91.0%, 1Y Sharpe 1.01, 5Y DD 31.9% | Partial (momentum sleeves yes, regime sleeve no) | High, same leaderboard-selection risk as QC-01 | combination |
| EXT-QC-03 | [strategies/623](https://www.quantconnect.com/strategies/623) | Monthly, S&P 500 top-10 by 90-day TRIX cross-sectional momentum, cap-weighted | 5Y CAGR 58.3%, **1Y Sharpe 2.59**, 5Y DD 47.2% | Yes — TRIX ≈ smoothed `mom_63`/`mom_126` | Very high — 1Y Sharpe 2.59 on a 10-name book is a large outlier vs. the literature (~0.4–0.9); textbook leaderboard-selection artifact | momentum — cross-check only |
| EXT-QC-04 | [strategies/285](https://www.quantconnect.com/strategies/285) | Daily-rebuilt sector-neutral large-cap momentum (price>$5, cap>$5B), de-risks on broad deterioration | 5Y CAGR 53.3%, **1Y Sharpe 0.16**, 5Y DD 56.8% | Yes | Medium — the 5Y-CAGR/1Y-Sharpe gap is itself the finding: recent decay on a real, currently-listed strategy | momentum |
| EXT-QC-05 | [strategies/470](https://www.quantconnect.com/strategies/470) | Quarterly, top-20 by trailing-252d return, weighted by **hierarchical risk parity** (not equal-weight) | 5Y CAGR 20.3%, 1Y Sharpe 1.09, 5Y DD 15.8% | Yes for the rank; HRP weighting is NOT in our library (equal-weight only) | Low-medium | combination — **directly answers Aegis's own open TRIAL-001 (does HRP beat EW on the equity sleeve)**, worth a dedicated look independent of the momentum leg |
| EXT-QC-06 | [strategies/254](https://www.quantconnect.com/strategies/254) | Monthly, top 5% of 1000 liquid US stocks by standardized unexpected earnings (SUE) | 5Y CAGR 19.3%, 1Y Sharpe 0.72, 5Y DD 24.0% | Partial — needs a consensus-estimate-at-announcement field (same PEAD-01 dependency) | Medium — most literature-consistent number on the leaderboard | earnings_momentum — independent confirmation PEAD-01 is worth building |
| EXT-QC-07 | [strategies/410](https://www.quantconnect.com/strategies/410) | Monthly, allocate to SPY/IEF/GLD/UUP/DBC by best recent-90d return-distribution median, scaled to a fixed downside-risk budget | 5Y CAGR 18.7%, 1Y Sharpe 1.33, 5Y DD **8.3%** | No — 5-ETF asset-allocation overlay, not single-stock (same caveat as RET-06) | Low — smallest, most plausible-looking drawdown on the whole fetch | NOT REACHABLE cleanly — asset allocation |
| EXT-QC-08 | [strategies/372](https://www.quantconnect.com/strategies/372) | Daily, RSI(2)<20 + falling TSI mean reversion on 20 liquid ETFs/megacaps, ATR stop/target, 8d time stop | 5Y CAGR 14.1%, 1Y Sharpe 1.25, 5Y DD 15.9% | Yes — `rev_5`/`rev_1`-style | High overlap with existing REV-01/02/RET-02 (near-duplicate) | reversal — cross-check only |
| EXT-QC-09 | [strategies/211](https://www.quantconnect.com/strategies/211) | Annual, Dow 30 → top-10 dividend yield → concentrate in 5 lowest-priced ("Puppies"), equal weight | 5Y CAGR 13.9%, 1Y Sharpe 1.64, 5Y DD 22.9% | Partial — needs a dividend-yield field, not in `FEATURES` | Medium — 30-name universe, annual rebalance = thin sample; Dogs-of-the-Dow variant, no peer-reviewed backing found | value/income — **dividend yield is a genuinely new family**, not in the 113-row catalogue |
| EXT-QC-10 | [strategies/241](https://www.quantconnect.com/strategies/241) | Annual, $80M–$1B cap value (book/earnings/EV-EBIT composite) + size, top-25, convex weighting | 5Y CAGR 13.6%, **1Y Sharpe 0.11** | Partial — needs VAL fundamentals fields | High — concentrates in exactly the illiquid small-cap band our own §59 finding flagged; recent Sharpe near-zero | value/size — corroborates the INV-01/SIZ "expect dead" pattern with real numbers |
| EXT-QC-11 | [strategies/768](https://www.quantconnect.com/strategies/768/Dual-MA-Trend-Following-on-DJIA) | 100d SMA crosses above 200d SMA → buy the DJIA constituent, ~1.5x leverage, 20% stop | 5Y-window CAGR 10.3%/Sharpe 0.56; **full-backtest CAGR 10.27%/Sharpe 0.29** (same page, different window) | Yes — `px_vs_ma50`/`px_vs_ma200` (= RET-01 golden cross) | Medium — the strategy's own page shows the shorter window flattering the Sharpe by ~2x vs. the full backtest, a live example of window-selection inflation | trend — confirms RET-01's LOW confidence rating with real data |
| EXT-QC-12 | [strategies/310](https://www.quantconnect.com/strategies/310) | Monthly, 5 lowest trailing-252d-vol large caps, equal weight, fully invested | 5Y CAGR 9.8%, 1Y Sharpe 0.91, 5Y DD 16.4% | Yes — `vol_21`/`vol_63` (= LV-01/02) | Low-medium — only 5 names is a concentrated, high-idio-risk implementation of "low vol" | low_risk — independent cross-check for LV-01 |
| EXT-QC-13 | [strategies/761](https://www.quantconnect.com/strategies/761) | Annual, S&P 500 ex-Fin/RE, rank by EBIT/EV + EBIT/invested-capital, top-50, 5%/25% caps | 5Y CAGR 5.2%, **1Y Sharpe -0.16**, 5Y DD 20.6% | Partial — needs EV/EBIT + invested-capital fields | Medium — the worst-performing item on the whole leaderboard fetch; useful as a "value+quality currently out of favor" control | value+quality combination |
| EXT-QC-14 | [strategies/536,629,470,...](https://www.quantconnect.com/strategies/) plus 6 more on the leaderboard not tabulated | Equal-weight AI-compute basket, RSI vol-rotation, sector-neutral momentum variants — see full JSON | 5Y CAGR 38–46%, various | Partial | Medium-high, thematic/basket rows | see `openclaw_logs/q1_quantconnect_strategies.json` for the remaining 6 |
| EXT-QP-01 | [quantpedia.com/screener](https://quantpedia.com/screener), #0003 "Sector Momentum – Rotational System" | Monthly, rotate into best-performing equity sector | OOS 13.94% / vol 18.38% | Partial — no sector/GICS field on panel (same MOM-06 dependency) | Medium | sector momentum — corroborates MOM-06 with a real number |
| EXT-QP-02 | Quantpedia #0013 "Short Term Reversal Effect in Stocks" | Weekly stock-level reversal | OOS 16.25% / vol 14.94% | Yes — `rev_5` | High turnover/cost risk, REV-01/02 family | reversal — cross-check |
| EXT-QP-03 | Quantpedia #0014 "Momentum Factor Effect in Stocks" | Monthly stock momentum | OOS 8.30% / vol 16.60% | Yes — `mom_252_21` | Medium, textbook MOM-01 duplicate | momentum — cross-check |
| EXT-QP-04 | Quantpedia #0025 "Size Factor – Small Capitalization Stocks Premium" | Yearly small-cap tilt | OOS 6.10% / vol **25.60%** | Yes — `dollar_vol_log` bottom decile (SIZ-02) | High — matches "expect dead in a large-cap-dominated modern US market" with concrete low-return/high-vol numbers | size — corroborates SIZ-02 "expect dead" |
| EXT-QP-05 | Quantpedia #0036 "Net Payout Yield Effect" | Yearly, high (buybacks+dividends−issuance)/price | OOS 22.13% (no vol reported) | Partial — needs buyback+dividend+issuance fields; distinct construction from INV-02's net-issuance | Medium — no Sharpe, single-source | value/payout — genuinely new value variant |
| EXT-QP-06 | Quantpedia #0055 "Pairs Trading with Country ETFs" | Daily, cointegrated country-ETF pairs, mean reversion | OOS 20.60% / vol 10.00% | No — pairs construction, not a k-of-N ranker (same structural note as RET-11) | Medium | pairs/relative-value — needs its own construction |
| EXT-QP-07 | Quantpedia #0067 "Industry Momentum – Riding Industry Bubbles" | Monthly, buy the best-performing industry | OOS 18.00% | Partial — same MOM-06/sector dependency | Medium | sector momentum — second independent MOM-06 number |
| EXT-QP-08 | Quantpedia #0077 "Betting Against Beta Factor in Stocks" | Monthly, low-beta long (or long-only low-beta) | OOS **8.86%** / vol 11.50% | Yes — `beta_63` (LV-03/LV-08) | Low — notably SMALLER than Frazzini-Pedersen's academic Sharpe-0.78 claim; useful counterweight to LV-03's "expect to survive" optimism | low_risk — independent, more conservative BAB number |
| EXT-QP-09 | Quantpedia #0091 "Momentum Factor and Style Rotation Effect" | Monthly, rotate between momentum and other style factors on a regime signal | OOS 9.25% / vol 16.01% | Partial — needs a style-rotation regime signal not yet built | Medium | combination — a "meta-router" idea; COMB-07's caution against premature routers applies |
| EXT-QP-10 | Quantpedia #0096 "Crude Oil Predicts Equity Returns" | Monthly, oil-price signal predicts subsequent equity returns | OOS 11.90% / vol 9.80% | Partial — needs a WTI/Brent series joined to the panel; not currently wired but easy to source | Medium | cross-asset overlay — genuinely new family |
| EXT-QP-11 | Quantpedia #0108 "Soccer Clubs' Stocks Arbitrage" | Daily reversal/arbitrage on listed soccer-club stocks after match results | OOS 42.00% / vol **50.00%** | No — tiny, illiquid, non-US niche; not on our panel | High — huge vol on a name-count-small universe | novelty/niche — listed for completeness only |
| EXT-QP-12 | Quantpedia #0002 "Momentum Asset Allocation Strategy" | Monthly momentum rotation among equities/bonds/commodities/REITs | OOS 14.49% / vol 11.00% | No — asset-class rotation | Low, single-source | NOT REACHABLE — asset allocation |
| EXT-GH-01 | [github.com/You07abd/ApexQuant](https://github.com/You07abd/ApexQuant) | Dual-engine long-only swing (trend+mean-reversion) on SPY/QQQ/IWM/DIA/GLD/TLT + megacap satellite, decided once/day after close | OOS Sharpe ≈0.9–1.2, ann. return ≈4–7%, max DD −8%, ~45 trades/yr (June 2026) | Partial — ETF-sleeve rotation close to our own lane-mandate replay; megacap satellite maps to `mom_252_21` | Medium — README explicitly **rejects** the intraday and ML variants after costs and recommends paper-trade-only; unusually honest about what failed | combination/ETF rotation — good methodology reference |
| EXT-GH-02 | [github.com/yingwang/trade](https://github.com/yingwang/trade) | 5 price factors (momentum, 52w-high proximity, short reversal, trend persistence, vol contraction), 12 positions, 22% vol target, 3-week rebalance, Almgren-Chriss impact cost | 5Y (2021–2026) CAGR 16.1%/Sharpe 0.71 vs SPY +80.3% cum.; 1Y CAGR 39.5%/Sharpe 1.45; repo's own note: an earlier July-2026 headline (+193.6%/5Y) had ~half its excess return removed by a later bugfix to the rebalance/impact-cost chain | Yes — `mom_252_21`, `px_vs_52w_high`, `rev_5`, `resid_mom_63`-like persistence, `vol_21`/`vol_63` all map directly | Medium-low — rare self-correcting repo, dated commit-by-commit; good model for how our own receipts should read | momentum/combination — closest GitHub analogue to our own `mom_flow`/`trend_quality` rows |
| EXT-GH-03 | [github.com/ava-28/statistical-arbitrage-backtest](https://github.com/ava-28/statistical-arbitrage-backtest) | Engle-Granger cointegration pairs on 7 US names, selected 2020–2023, tested OOS 2024–2025 | OOS mean Sharpe 0.517, ann. return 0.4–5.5% vs SPY Sharpe 1.307/+49%; repo's own conclusion: "does not beat buying the index" | No — pairs construction | Low leak risk (explicitly OOS-honest) but a 7-name universe is not statistically meaningful | pairs/relative-value — citation for "clean OOS pairs still loses to SPY" |
| EXT-GH-04 | [github.com/Donvink/quant-trade](https://github.com/Donvink/quant-trade) | Relative Price Strength (RPS) rank across 20/60/120d + volume/fundamental filters, layered stop system | 2yr (2024–2026): CAGR 93.9%, Sharpe 1.97, max DD −34.2% vs SPY ~22%/0.9 | Yes — multi-horizon RPS ≈ our momentum family | **Very high** — single 2-year "simulated capital" run, no purged/walk-forward CV stated; classic retail-repo overstatement (contrast with GH-02's self-correction) | momentum — flagged HIGH overfit risk, calibration example not a source to trust |
| EXT-GH-05 | [github.com/brianbeals/sector-rotation-screener](https://github.com/brianbeals/sector-rotation-screener) | 11 SPDR sector ETFs scored on seasonality + economic-cycle-fit (FRED **point-in-time ALFRED vintages**) + relative strength vs SPY | 15-year backtest since 2011; net-of-cost banner not quoted in the fetched excerpt | Partial — sector rotation, not single-stock; the PIT-macro-vintage discipline (never use revised FRED values) is a genuinely useful ENGINEERING pattern | Low — author is explicit about the PIT discipline, matching Aegis's own canon | sector rotation — borrow the ENGINEERING, not necessarily the alpha |
| EXT-GH-06 | [github.com/Weculp/Trading-Strategies](https://github.com/Weculp/Trading-Strategies) (RGVH) | Always-short SPY ATM straddle, gated by IV regime + cross-asset stress + yield-curve inversion | **Sharpe 3.38 net, 12y OOS** (2013-07→2025-08) | No — options/short-vol, not reachable on a cash-equity panel (same as RET-09) | **Very high** — an enormous unverified claim from a 3-star, 1-watcher repo with no independent replication; short-vol is exactly the fat-tailed, blow-up-prone family DSR exists to catch | options/volatility — NOT REACHABLE, cautionary-tale headline number |
| EXT-GH-07 | [github.com/renee-jia/trading-bot](https://github.com/renee-jia/trading-bot) | Multi-agent (technical/trend/macro/sentiment/quant-alpha) 0–100 conviction score sizing a live Alpaca paper portfolio | Per-year 2023–2026 beats SPY/QQQ every year shown (e.g. 2025 +24.2% vs SPY +18.0%); repo's own "Honesty note": universe is "today's survivors held back through time," calls the raw alpha an "upper bound" | Partial — the multi-agent conviction-score idea is closer to Aegis's own investigator/persona distinction (§64) than a `FEATURES` row | Medium — survivorship bias self-disclosed (rare); the scoring core is marked 🔒 PRIVATE so the actual rule can't be inspected | combination/LLM-agent — methodological cousin of Aegis's own thesis-card work |
| EXT-GH-08 | [github.com/aengusmartindonaire/statistical-arbitrage-strat](https://github.com/aengusmartindonaire/statistical-arbitrage-strat) | 3 variants: unhedged reversal, SPY-hedged reversal, SPY-hedged residual momentum (12M-1M), Bloomberg-derived survivorship-free universe 2016–2025 | SPY-hedged resid. momentum: IC 0.0168, hit rate 56.7%, cum. +721.8%, Sharpe 0.48, DD −39.1%; **both reversal legs deeply negative** (Sharpe −1.01, −0.88, cum. ≈−98%) | Yes — `resid_mom_63` is exactly this construction (already MOM-05) | Medium — the catastrophic reversal legs corroborate REV-01/02 "expect dead"; the 721% momentum number over one 10-year run with no stated purged CV is a red flag despite the positive framing | momentum/reversal — MOM-05 cross-check + REV "expect dead" corroboration |
| EXT-GH-09 | [github.com/vzeman/trading-autoresearch](https://github.com/vzeman/trading-autoresearch) | LLM-driven autoresearch on a PatchTST transformer + Kelly policy, bootstrap-CI gated, hard −15% DD floor, walk-forward retrains on unseen calendar years | Best "deploy-shaped" 3-fold walk-forward: 2023 +24.1% vs SPY +23.7%, 2024 +25.6% vs SPY +25.2%, 2025 +23.0% vs SPY +17.2%, 28 trades, −9.8% worst DD; repo's own log shows MANY prior variants explicitly REJECTED for falling below SPY under added cost stress | No direct `FEATURES` mapping (proprietary transformer) | Low methodological risk — the most rigorous public repo found this session: multi-seed median Sharpe + bootstrap CI, walk-forward over unseen years, a public log of rejected variants | ML — best-practice reference for how `night_backtest_factory` receipts should read |
| EXT-GH-10 | [github.com/ChiefStarKid/roaring-trade-portfolio-rotation](https://github.com/ChiefStarKid/roaring-trade-portfolio-rotation) | Sector-ETF "M-Signal" rotation, tiered profit-target exits, interactive client-side dashboard | No single headline number quoted; **36,966 exit-day × allocation combinations** swept, user picks sliders after the fact | No — sector rotation, path-dependent exit mechanic | High — sweeping ~37,000 combinations and letting the reader pick post-hoc is an overfitting-surface demo, not a strategy | sector rotation/exit-mechanic — cautionary UI pattern |
| EXT-GH-11 | [github.com/husaam-atq/systematic-equity-factor-backtester](https://github.com/husaam-atq/systematic-equity-factor-backtester) | Monthly, 20% top-quantile momentum-weighted composite score, long-only, 5bps one-way costs | CAGR 32.4%, Sharpe 1.33, max DD −31.3% vs SPY 13.0%/0.78; **long-short much weaker after costs than long-only** (explicit finding) | Yes — momentum family, directly comparable construction | Medium — transparent quantile-sensitivity and cost-sensitivity tables shipped in the repo, above-average transparency for a solo repo | momentum — good comparison for `mom_12_1_q` |
| EXT-GH-12 | [github.com/Jeremy-Xiang/alpha-factor-pipeline](https://github.com/Jeremy-Xiang/alpha-factor-pipeline) | IC/IC-IR factor screen (drop `\|IC_IR\|<0.15`) → `HistGradientBoostingRegressor` on an expanding window, long top 30%/short bottom 30% | Long-short net Sharpe 0.93; **equal-weight benchmark Sharpe 4.27 beats it outright** — repo's own conclusion: "the benchmark's Sharpe is higher... that's the correct outcome to report" | Partial — the IC/IC-IR factor-screening step is a genuinely reusable pattern, independent of the specific ML model | Low — one of the most honest repos found this session; explicitly reports a losing comparison | ML/factor-screening — methodology reference, not an alpha source |
| EXT-GH-13 | [github.com/swaraaaa/FactorPortfolio](https://github.com/swaraaaa/FactorPortfolio) | Fama-French 3-factor long-short, weekly rebalance, 12-ETF universe, beta-constrained mean-variance vs. information-ratio optimization | Strategy II (IR-opt): cum. 828.8% vs SPY 535.6% (2007–2025), Sharpe 0.66 vs SPY 0.54; **Strategy I (low-beta) Sharpe only 0.06** | No — 12-ETF asset-class universe (equities/commodities/FX/fixed income), not single-stock | Medium — 18-year single-path backtest, two strategies presented side by side including the losing one | combination/asset-allocation — NOT REACHABLE on our single-stock panel, but the "report the losing variant too" discipline is worth citing |
| EXT-BLOG-01 | [quanta72.substack.com](https://quanta72.substack.com/p/the-factor-model-i-tested-8021-stocks) (2026-08-20, "Quanta 72") | Annual (Jan), S&P 500 top-10 by 12m ROE + top-10 by 63d avg-dollar-volume, equal-weight 20 slots, + a proprietary "BetaMap" defensive overlay | 2013–2024: ROE+ADV 21.1% ann. (SPY 13.2%), Sharpe 1.08→1.17 with the overlay, max DD 35.8%→26.2% | Partial — ROE needs a fundamentals field; ADV (`dollar_vol_log`) already on panel | High — **this is a promotional newsletter** ("Get the Factor Model" is a paid product); the BetaMap overlay is proprietary/unreproducible, ROE-alone was shown by the same post to decay 2015–2024 | combination — logged with an explicit promotional flag, ROE+ADV pairing is the only reusable idea |
| EXT-CO-01 | [composer.trade/trading-strategies](https://www.composer.trade/trading-strategies), "Midori-Congress Sells" | Thematic long-only, tracks **Congressional STOCK-Act trading disclosures**, tech+energy/utility tilt, daily rebalance | Since 2024-04-26: cum. 57.08%, Sharpe 0.98, max DD 20.66% | Partial — needs a Congressional-disclosure feed (Capitol Trades / Quiver Quantitative / House-Senate efdsearch); none of Aegis's current collectors carry this | Medium — short (~2.5yr) window, thematic sector tilt confounds the pure "follow Congress" signal | catalyst/insider-adjacent — **new mechanism family**, see EXT-LIT-01 for the decay evidence |
| EXT-LIT-01 | Ziobrowski et al. 2004 *JFQA* (Senate); Ziobrowski et al. 2011 *Business & Politics* (House); Belmont, Sacerdote, Sehgal & Van Hoek 2022 *J. Public Economics*; Ansolabehere et al. | Buy stocks recently purchased by members of Congress (STOCK-Act disclosures) | **Pre-2012**: Senate +85bps/mo buy-minus-market (1993–1998); House +55bps/mo ≈6%/yr (1985–2001). **Post-STOCK-Act (2012–2020)**: Belmont et al. find NO superior performance (House buys **underperform** −26bps/6mo); Ansolabehere: the abnormal-return effect "disappears after the STOCK Act was passed in 2012" | Partial — same disclosure-feed dependency as EXT-CO-01; the STOCK Act's mandatory 45-day disclosure lag is a real, quantifiable cost | Low-medium **as a deliberately DEAD mechanism** — a real historical edge a transparency law specifically closed, the cleanest "expect dead" bet in this whole batch, same shape as RET-10's 13F-cloning lag | catalyst/insider-adjacent — register as **expect dead post-2012**, a calibration control alongside SEAS-02/03 |
| EXT-CO-02 | Composer, "CQ_USA vs. Europe" | Momentum/relative-strength rotation, US vs. European equities, long-only | Since 2024-10-24: cum. 52.42%, Sharpe 1.51, max DD 14.25% | No — country-level allocation | Low-medium, ~1yr track record | NOT REACHABLE — asset allocation |
| EXT-CO-03 | Composer, "? Charged Pool: Filtered Tech+" | 3yr backtest, contrarian RSI mean-reversion + quality filter on concentrated semiconductor names | AR 26.1%, Sharpe 0.82, SD 36.1%, MD **37.9%** | Partial — `rev_5`/RSI + `gross_margin` quality filter both map to `FEATURES`, but sector-concentrated | Medium-high — single-sector concentration confounds the reversal+quality signal with a semiconductor-cycle bet | reversal+quality combination — cross-check only |
| EXT-RD-01 | r/quant, ["Feedback on a Ranking Model (ROIC, Earnings, Momentum, Flows)"](https://www.reddit.com/r/quant/comments/1s8g7l3/feedback_on_a_ranking_model_roic_earnings/) (2026-03-31) | Multi-factor rank: ROIC + earnings growth + momentum + insider activity + institutional flows | Claimed "~30% excess return vs QQQ" over "~4-year backtest" (single, unaudited Reddit post) | Partial — momentum/insider map; ROIC/flows need new fields (RET-10 dependency for flows) | **Very high** — top commenter directly flags "4 years is too short" and that the factors likely load on known premia; anecdotal | combination — logged for completeness only, very low confidence |
| EXT-RD-02 | r/quant, ["Tried to replicate the Attention Factors stat-arb paper (ICAIF 2025)"](https://www.reddit.com/r/quant/comments/1w8otws/tried_to_replicate_the_attention_factors_statarb/) (2026-09-06) | Neural attention-factor model, point-in-time top-500, 2016-06→2026-08 | Paper claimed Sharpe **+2.30**; independent replication got Sharpe **−0.64**; top comment: "I generally don't bother with papers that report miraculous SRs while not linking a repository" | No — out of scope as a `FEATURES` row | Very high, textbook irreproducibility | ML/attention-factor — NOT a candidate to adopt; logged as a decay/skepticism data point |
| EXT-RD-03 | r/algotrading, ["Found a simple mean reversion setup with 70% win rate"](https://www.reddit.com/r/algotrading/comments/1rjvxjy/found_a_simple_mean_reversion_setup_with_70_win/) (2026-03-03) | Daily SPY/QQQ: buy when close < (10d high − 2.5×(25d avg high − 25d avg low)) AND IBS<0.3; exit close>yesterday's high; 2011–2026 | 70% win rate quoted (**no CAGR/Sharpe given**); top comment: "signals are very delayed and you cannot get the stocks at the signaled prices" in real life | Yes — IBS/range-based `rev_1`/`vol_21` variant | High — win-rate-only framing without a Sharpe/CAGR is an incomplete-metric red flag; only 2 tickers tested | reversal — cross-check only, low confidence |

*Remaining 6 QuantConnect leaderboard items and the full text of every Reddit
thread's counter-arguments are in the raw quest logs
(`openclaw_logs/q1_quantconnect_strategies.json`,
`openclaw_logs/q2_reddit_algotrading.json`,
`openclaw_logs/q3_reddit_quant.json`) rather than duplicated here.*

## (b) QuantConnect replication recipe — running one of OUR rules on QC

This is the "upload ours" half of Murat's ask, never attempted before (per
V5_CLOSEOUT gap #1: only the ETF-sleeve mandate replay has ever run on QC).
Confirmed against QC's own docs (`quantconnect.com/docs/v2/...`, fetched this
session) and the LEAN GitHub reference algorithms.

**Free tier limits that bound this** (confirmed 2026-09-26): 1 free backtest
node + 1 free research node; project file size cap **32 KB** (Free tier); a
backtest/research session may download **≤25 remote files**, each ≤200 MB;
Object Store *storage* has no download restriction for writing but its
*download* action needs an Institution-tier "derived data agreement" — so a
CSV pushed into the Object Store can be READ by the algorithm forever, but
cannot be pulled back out through the API on the free tier. None of this
blocks a single custom-rank monthly top-k algorithm.

**Recipe: monthly top-k by one of our `strategy_library` ranks (e.g.
`mom_12_1_q`), run on QC's own survivorship-handled US equity data.**

1. **Export our own rank, not raw features.** Run our existing
   `night_backtest_factory`/`xs_ranker` pipeline offline to produce a CSV of
   `date,ticker,rank_score` at the rule's own rebalance cadence (monthly for
   the top rows in `LEADERBOARD.md`). This is the point of the exercise: QC
   supplies a different, third-party, survivorship-free price history, so
   only OUR ranking method is exported — not our returns.
2. **Host the CSV where LEAN can reach it.** Free-tier options, per QC docs:
   Dropbox (public link with `?dl=1`), a public GitHub raw URL, or a public
   Google Sheets CSV export link. (The Object Store is simpler once inside
   LEAN — `lean cloud object-store set` — but is a paid-CLI action; the
   in-browser IDE's Dropbox/GitHub route needs no CLI.)
3. **Custom-data class + scheduled monthly rebalance** (Python, LEAN v2 API):

```python
from AlgorithmImports import *

class AegisRankReplication(QCAlgorithm):
    """Runs ONE Aegis strategy_library rule (a monthly top-K custom rank)
    on QuantConnect's own US equity history. The rank values are OURS,
    exported offline; QC supplies price history and cost/fill modeling
    independent of our own panel -- an actual third-party replication,
    not a repeat of our own backtest.
    """

    RULE_ID = "mom_12_1_q"      # <- strategy_library id being replicated
    TOP_K = 20                  # <- matches the library row's own k
    RANK_CSV_URL = "https://raw.githubusercontent.com/<you>/<repo>/main/mom_12_1_q_ranks.csv"

    def initialize(self):
        self.set_start_date(2016, 1, 1)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
                                  AccountType.MARGIN)   # no leverage requested
        self.set_benchmark("SPY")
        self.universe_settings.resolution = Resolution.DAILY

        # Coarse+fine ONLY to get a tradable, has-fundamental-data US universe;
        # the actual RANK comes from our own CSV, not from QC's fundamentals.
        self.add_universe(self.coarse_selection_function, self.fine_selection_function)
        self._changes = None
        self._ranks_by_date = {}   # date -> {ticker: rank_score}, loaded once
        self._current_month = None

        self.schedule.on(self.date_rules.month_start(),
                          self.time_rules.after_market_open("SPY", 30),
                          self.rebalance)

    def coarse_selection_function(self, coarse):
        # Liquid, has-fundamental-data names only -- keeps the universe close
        # to what xs_ranker would have considered tradable.
        liquid = [c for c in coarse if c.has_fundamental_data and c.price > 5]
        return [c.symbol for c in sorted(liquid, key=lambda c: c.dollar_volume,
                                          reverse=True)[:1000]]

    def fine_selection_function(self, fine):
        return [f.symbol for f in fine]   # no further QC-side filtering

    def _load_ranks_once(self):
        if self._ranks_by_date:
            return
        raw = self.download(self.RANK_CSV_URL)   # bulk download, free tier: <=25 remote files/session
        for line in raw.splitlines()[1:]:
            date_s, ticker, score = line.split(",")
            self._ranks_by_date.setdefault(date_s, {})[ticker] = float(score)

    def rebalance(self):
        self._load_ranks_once()
        month_key = self.time.strftime("%Y-%m")
        if month_key == self._current_month:
            return
        self._current_month = month_key

        # Match this month's exported ranks to symbols currently in the universe.
        month_ranks = self._ranks_by_date.get(self.time.strftime("%Y-%m-01"), {})
        tradable = {s: month_ranks[s.value] for s in self.active_securities.keys()
                    if s.value in month_ranks}
        top = sorted(tradable.items(), key=lambda kv: kv[1], reverse=True)[:self.TOP_K]

        targets = [PortfolioTarget(sym, 1.0 / len(top)) for sym, _ in top]
        if targets:
            self.set_holdings(targets, liquidateExistingHoldings=True)

    def on_securities_changed(self, changes):
        self._changes = changes
        for security in changes.removed_securities:
            if security.invested:
                self.liquidate(security.symbol)
```

4. **Backtest, then Share for a public URL** (repeats the exact workflow that
   already worked for the lane-mandate replay in July — see
   `QUANTCONNECT_REPLAY_2026-07-18.md` "Murat's steps"). No login/account is
   needed beyond the free signup Murat already has.
5. **Read QC's Sharpe correctly.** Per the same doc's hard-won lesson: QC's
   Sharpe subtracts a live risk-free rate; our own convention uses rf=0. Quote
   both, exactly as the July replay's results table does, or a "low Sharpe"
   reads as a failed run when it's a denomination difference.
6. **What this replication is NOT**: it does not relax the three-licence
   ladder. A QC-hosted run of `mom_12_1_q` is still the SAME `PRODUCT_EXPERIMENT`
   observation, just on different (QC-licensed) price data — useful as an
   independent-data robustness check, not as a new pre-registration or a
   `RESEARCH_CLAIM`.

## (c) What OpenClaw could and could not do

**Could, cleanly, with no login and real dated data:**
- Browse QuantConnect's live community **Strategies** leaderboard
  (`/strategies/`) unauthenticated — a "You are not logged in" banner appears
  but does not block the data, and the underlying `/api/v2/strategies/...`
  routes were reachable too. This is a genuinely dynamic, dated surface (Sep
  2026 leaderboard/comments) — not marketing copy.
- Browse Reddit (r/algotrading, r/quant) and read full threads + comment
  trees through the rendered new-Reddit UI, with correctly-resolved dates
  from relative labels ("8d ago" → 2026-09-18). Both quests explicitly
  reported that **direct HTTP/JSON access to Reddit was refused** ("network
  policy" 403) — only the rendered browser path worked, which is exactly why
  this was an OpenClaw job and not an `exa`/`WebFetch` job.

**Could not:**
- **X/Twitter.** Quest 4 hit a fully logged-out onboarding wall on BOTH
  configured profiles (`muratclaw` AND `openclaw`) — contradicting this task's
  premise that "the authenticated X account is available." `OC.profiles()`
  shows two OTHER profiles (`user`, tag `existing-session`; `chrome`, tag
  `extension`) that might hold a real login, but `openclaw_client.py`
  deliberately refuses to fall back to any profile other than the pinned
  `muratclaw` — *"a fallback is how a run ends up in ... somebody else's
  signed-in Chrome"* — so this run did not try them, correctly. Quest 5 (an
  indirect route: search Bing for `site:x.com OR site:twitter.com` results
  instead of loading x.com directly) hit a **Cloudflare CAPTCHA interstitial**
  on the search page itself — zero results, zero X links to even attempt. A
  follow-up `exa` search for the same goal surfaced GitHub/Substack/LinkedIn
  results instead of real X posts. **Three independent paths to X content all
  failed this session** (direct browse, indirect search-engine browse, exa
  web search) — this is a genuine capability gap, not a quest-design mistake.
  **Action for the next session: sign into X inside the `muratclaw` profile by
  hand** (`openclaw browser open` then log in inside that window) — after
  that, quest 4's exact query should be re-run first, cheaply, before spending
  more quests on workarounds.
- Reddit's own JSON/API endpoints and direct `curl`/`web_fetch` to
  `reddit.com` — both refused with a network-policy block page. Only the
  rendered-page route through the browser agent worked.
- Quest 3 noted the shared `muratclaw` browser profile was **contended by
  other concurrent automations that repeatedly closed tabs mid-read** during
  this run — a real operational hazard for any future *parallel* OpenClaw
  session, worth a note for whoever schedules concurrent quests: OpenClaw
  quests should probably run serially against one profile, not fanned out.

**Didn't need OpenClaw, used `exa` instead (cheaper, no browser/profile
needed):** Quantpedia's free screener, GitHub repo search, QuantConnect's
static documentation pages (custom-data upload, free-tier limits, universe
selection API), and Composer's symphony database — all served their data to
a plain fetch without JS-gated interactivity or a login wall. **Rule of thumb
for the next run:** try `exa`/`WebFetch` first; reserve OpenClaw quests for
pages that are confirmed to need a live session (dynamic SPA data, a site
that blocks scripted HTTP, or anything genuinely behind Murat's login).

**Cost/quest efficiency:** 5 of ≤12 quests used, $0.2313 of the ≤$1.50 budget,
all model `deepseek/deepseek-flash` with real (non-zero) priced usage on every
call. Per-quest cost was NOT the constraint — 7 quests and ~$1.27 of budget
headroom went unused this run. Elapsed wall time (~1–4.5 min/quest, mostly the
agent reading/paginating a real page) was the practical limiter, and
browser-profile authentication state (for X) plus a Cloudflare challenge (for
Bing) were the actual blockers, not cost or the quest cap.

## Sources

Every non-derived claim above links inline to its source in the candidate
table. Academic sources for EXT-LIT-01: Ziobrowski, Cheng, Boyd & Ziobrowski
2004, *Journal of Financial and Quantitative Analysis* 39:661–676; Ziobrowski,
Boyd, Cheng & Ziobrowski 2011, *Business and Politics* 13:1–22; Belmont,
Sacerdote, Sehgal & Van Hoek 2022, *Journal of Public Economics*
("Do senators and house members beat the stock market? Evidence from the
STOCK Act"); Ansolabehere et al., "Trading on Private Information: Evidence
from Members of Congress," *Financial Review*. QuantConnect docs pages fetched
2026-09-26: `/docs/v2/writing-algorithms/importing-data/key-concepts`,
`/docs/v2/cloud-platform/organizations/tier-features`,
`/docs/v2/cloud-platform/projects/files`,
`/docs/v2/writing-algorithms/algorithm-framework/universe-selection/*`,
`/docs/v2/cloud-platform/community/strategies`. Quantpedia screener:
`quantpedia.com/screener/` (free tier, fetched 2026-09-26 — treat every figure
as single-source until Aegis's own receipt confirms or refutes it, same
caution as `research_strategy_library.md` §2 already states for this site).
