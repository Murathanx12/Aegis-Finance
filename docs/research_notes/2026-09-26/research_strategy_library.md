# Research — seeding the strategy library and backtest factory (2026-09-26)

For `backend/services/strategy_library.py` and `scripts/night_backtest_factory.py`
(spec: `docs/research_notes/2026-09-26/spec_chunk3b_strategy_library_and_backtest_factory.md`).
Murat: *"do a search on strategies, what other people said, what the backtests
... 100 backtests, list the top 10."*

**Evidence-strength tag on every row**: `[V]` = fetched the primary paper's
abstract/tables this session (link given). `[B]` = background knowledge of a
well-known, widely-taught result, not re-fetched this session — treat as
lower confidence until the builder spot-checks the number against JKP/Quantpedia.
`[FWD]` = no historical data exists for Aegis; only testable forward, per the
Lookahead-Propensity rule.

WebSearch was already at its per-session budget (200/200) when this task
started, so all live lookups below used `exa` (`web_search_exa` /
`web_fetch_exa`), not the WebSearch tool.

---

## 0. The one honest sentence up front

Every strategy below is ONE line over `backend/services/xs_ranker.py::FEATURES`
(`mom_21, mom_63, mom_126, mom_252_21, rev_1, rev_5, vol_21, vol_63, vol_ratio,
dollar_vol_log, turnover_surge, trade_surge, px_vs_52w_high, px_vs_52w_low,
px_vs_ma50, px_vs_ma200, amihud, gap_share, vwap_pressure, resid_mom_63,
beta_63, up_days_21, max_drawdown_63, skew_63`), the quarterly SEC fundamentals
panel (`rev_qoq`, `gross_margin`, `margin_chg`), dated analyst revisions,
insider transactions, the catalyst calendar, or forward-only LLM outputs. A
handful of textbook rules (industry momentum, index-rebalance, FDA catalysts)
do **not** map onto the current panel — they are catalogued anyway (Murat asked
for the literature search) and flagged `NOT REACHABLE ON CURRENT PANEL` so the
builder doesn't spend a night trying to wire them.

---

## 1. Catalogue — 113 candidate strategies

### Momentum (12)

| id | rule (signal, sort, k/quantile, hold) | source | reported number (sample/universe) | decay/replication | survival note on our 2016-2026 panel |
|---|---|---|---|---|---|
| MOM-01 | `mom_252_21` (12-1) top decile, long-only or L/S, monthly hold | Jegadeesh & Titman 1993, *JF* [B] | ~1%/mo raw (1965-1989, NYSE/AMEX) | McLean-Pontiff: predictors built from price/volume alone decay *more* than accounting ones [V, JoF 2016 abstract] | Momentum is already 12-1 of the incumbent composite (99.5% coverage per `docs/ROADMAP...HUMAN_HEURISTICS...`) — a duplicate seed, useful only as the calibration control every other row is judged against |
| MOM-02 | `mom_126` (6-1) top decile | Jegadeesh & Titman 1993 [B] | weaker than 12-1, still positive | same family decay | shorter formation = more turnover = more cost; a cheaper survival test than MOM-01 |
| MOM-03 | `mom_63` (3-1) top decile | textbook variant [B] | weakest classic momentum window | — | closest to reversal boundary; expect it to straddle MOM/REV |
| MOM-04 | `px_vs_52w_high` top decile ("nearness to 52-week high") | George & Hwang 2004, *JF* [B] | comparable magnitude to 12-1 momentum, distinct driver (anchoring, not past return per se) | JKP clusters this in the "momentum" theme; 82.4% global replication rate for the theme as a whole [V] | worth a subsumption test against MOM-01 (canon: "is this new number or repackaged momentum") |
| MOM-05 | `resid_mom_63` (momentum orthogonalized to `beta_63`) — "residual momentum" | Blitz, Huij & Martens 2011 [B] | lower turnover, similar Sharpe to raw momentum in their sample | — | the panel already computes this feature; cheapest test of whether momentum survives after removing the market-beta component |
| MOM-06 | industry/sector momentum (buy the best-performing GICS sector, hold names in it) | Moskowitz & Grinblatt 1999, *JF* [B] | industry component drives much of individual-stock momentum in-sample | — | **NOT REACHABLE ON CURRENT PANEL** — no sector/industry field in `FEATURES`; would need a GICS join |
| MOM-07 | `mom_252_21` sign only, monthly hold, applied at the *index* level (SPY vs cash) | Moskowitz, Ooi & Pedersen 2012 (TSMOM), *JFE* [B] | Sharpe ~1.0 pooled across 58 futures, 1985-2009 | Hurst/Ooi/Pedersen follow-ups show TSMOM decayed post-2013 in equities specifically | this is a market-timing rule, not a cross-sectional one — reframe as a single-name overlay (scale exposure by `mom_252_21` sign) rather than a k-selection row |
| MOM-08 | Novy-Marx 12-7 "intermediate" momentum (`mom_252_21` computed with a 2-month skip instead of 1) | Novy-Marx 2012, *JFE* "Is momentum really momentum?" [B] | intermediate-horizon momentum (months t-12..t-7) outperforms recent momentum (t-6..t-2) in-sample | — | needs a feature variant (`mom` with a longer skip); flag for `xs_ranker` feature-request if not already latent in `mom_252_21`'s exact window |
| MOM-09 | `dollar_vol_log`-weighted momentum (momentum sorted only within top liquidity tercile) | practitioner overlay, no single paper [B] | — | McLean-Pontiff: post-publication decay concentrated in illiquid names [V] | directly testable: does MOM-01 survive when the universe is liquidity-screened first (same test the panel already ran for price/volume ranking, §59) |
| MOM-10 | beta-neutral momentum (`mom_252_21` top decile within `beta_63` terciles, dollar-neutral across terciles) | Asness, Frazzini, Israel & Moskowitz 2014, "Fact, Fiction and Momentum Investing" [B] | argues raw momentum's apparent "crashes" are largely beta-timing, not the factor itself | — | cheap to build with existing features; addresses the 2009 momentum-crash critique directly |
| MOM-11 | `up_days_21` (frequency of up days) as a "frog-in-the-pan" gradual-information proxy, top decile | Da, Gurun & Warachka 2014, *RFS*, "Frog in the Pan" [B] | gradual-information momentum outperforms momentum built from discrete jumps | — | `up_days_21` is a reasonable proxy for their "information discreteness" measure; worth registering as a distinct row from MOM-01 rather than folding in |
| MOM-12 | short-term reversal-adjusted momentum: `mom_252_21` minus `rev_5`-implied reversal component | practitioner composite, no single paper [B] | — | — | a combination row, listed here for completeness; true home is the Combinations section (COMB) |

### Short-term reversal (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| REV-01 | `rev_1` (prior-day return) bottom decile long, top decile short, daily/weekly rebalance | Jegadeesh 1990; Lehmann 1990, *JF*/*QJE* [B] | strong short-horizon reversal, pre-2000 US | McLean-Pontiff: price/volume-only predictors decay hardest, and reversal needs the highest turnover of any family here [V] | almost certainly dies to cost: implied turnover is daily-to-weekly against `COST_BPS_BY_BAND` of 18-35bps for mid/small; this is my #2 "expect dead" pick below |
| REV-02 | `rev_5` (prior-week return) bottom decile, weekly hold | Lo & MacKinlay 1990 [B] | contrarian profits, but partly a bid-ask bounce artifact per their own paper | Jegadeesh & Titman 1995 attribute much of it to microstructure, not economics | same cost problem as REV-01, one notch cheaper |
| REV-03 | reversal conditional on high `gap_share` (overnight-gap-driven names revert intraday/next-day) | Lou, Polk & Skouras 2019 "A Tug of War" (overnight/intraday reversal), *JFE* [B] | documents a persistent overnight-return vs intraday-return spread | still an active-research area, decay less studied | plausible edge concentrated in the mechanism our `gap_share` feature already targets; worth a dedicated test |
| REV-04 | reversal only within high-`amihud` (illiquid) names | mechanical extension of REV-01/02 | — | McLean-Pontiff: post-publication returns *higher* in illiquid, high-idio-risk names — implying pre-cost edge survives longest there, but that is exactly where our cost bands (35bps small) bite hardest | net effect ambiguous without running the numbers; a good candidate for the "print gross AND net" receipt |
| REV-05 | reversal combined with `skew_63` (short recent big-up-move names with negative skew — crash-prone) | practitioner combination [B] | — | — | combination row; low confidence, cheap to test |
| REV-06 | monthly reversal (`mom_21` bottom decile at month-end, held one month) — the classic "loser" leg of decile sorts | Fama & French 1996 replicate as part of their factor zoo [B] | small but positive at monthly horizon in original samples | JKP: reversal-family factors are among the weaker replicators globally [V, JKP theme clusters] | lowest turnover of the reversal family — the only one worth a real forward book |

### Low volatility / betting-against-beta (8)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| LV-01 | `vol_21` bottom decile (lowest realized vol), monthly hold | Ang, Hodrick, Xing & Zhang 2006, *JF*, "The Cross-Section of Volatility and Expected Returns" [B] | low-idiosyncratic-vol stocks earn *higher* average returns — the "idio-vol puzzle" | Ang et al. 2009 (*JFE*) confirm internationally; puzzle debated but replicates | one of my "expect to survive" picks — see §4 |
| LV-02 | `vol_63` bottom decile, quarterly hold (lower turnover version of LV-01) | same literature [B] | — | — | cheaper turnover than LV-01, worth testing both |
| LV-03 | `beta_63` bottom decile, monthly hold, dollar-neutral vs top decile — Betting-Against-Beta | Frazzini & Pedersen 2014, *JFE* [V] | US BAB Sharpe **0.78**, 1926-Mar 2012; FF3 alpha 0.73%/mo (t=7.39), Carhart alpha 0.55%/mo (t=5.59) [V, direct quote] | positive in 18/19 MSCI-developed countries; the BAB dataset (AQR, updated through recent years) is one of the most-replicated factors in finance | **needs leverage to be beta-neutral in the original construction** — Aegis's PROBE/EXPLOIT books are unlevered per canon, so a long-only "low-beta top decile" is a *weaker* implementation than the paper's factor; print that caveat on the receipt |
| LV-04 | `vol_ratio` (short-vol/long-vol) bottom decile — "vol compression" | practitioner overlay, no single paper [B] | — | — | speculative; cheap to test, low prior |
| LV-05 | `max_drawdown_63` shallowest-decile (steadiest recent equity curve) | practitioner "quality of the path" overlay [B] | — | — | overlaps heavily with LV-01/02; likely redundant, keep for the multiplicity count but expect high correlation with LV-01 |
| LV-06 | `skew_63` least-negative-decile (avoid crash-prone names) | Harvey & Siddique 2000, *JF* (co-skewness priced) [B] | co-skewness carries a premium in-sample | — | thin literature on univariate skew as a stock-picking signal outside of options-market applications; low prior |
| LV-07 | low-vol + quality combination (LV-01 ∩ QUAL-01 top decile each) | Asness, Frazzini & Pedersen 2019, QMJ combined with defensive factors, *RFS* [B] | "quality minus junk" composite Sharpe comparable to value/momentum in AQR's public factor data | — | belongs to Combinations too; listed here because low-vol is the dominant leg |
| LV-08 | BAB restricted to mega/large liquidity band only (`COST_BPS_BY_BAND` mega=6bps, large=10bps) | derived from LV-03 + our own cost table | — | — | this is the version of BAB actually worth forward-papering — low-vol names cluster in mega/large anyway, so it is the family least penalized by the cost curve |

### Quality (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| QUAL-01 | `gross_margin` top decile (Novy-Marx gross profitability, gross profit / assets) | Novy-Marx 2013, *JFE* [V] | profitable-minus-unprofitable spread **0.31%/mo (t=2.49)**; FF3-adjusted **0.52%/mo (t=4.49)**; mixed profitability+value strategy Sharpe **0.85** (2.5x the market's 0.34), July 1963-Dec 2010, NYSE/AMEX/COMPUSTAT ex-financials [V, direct quote] | one of the best-replicating anomalies in JKP's 13-theme Bayesian model; low turnover (paper notes annual profitability rebalance, ~4-year holding period even in the "low frequency" version) | **my #3 "expect to survive" pick** — see §4; the low required turnover is exactly what our cost bands reward |
| QUAL-02 | `margin_chg` (gross-margin change, QoQ) top decile — margin *expansion* rather than level | derivative of Novy-Marx + earnings-quality literature [B] | — | — | distinct from QUAL-01 (level vs change); pairs naturally with `rev_qoq` in INFL rows below |
| QUAL-03 | accruals bottom decile (low accruals = higher earnings quality) | Sloan 1996, *Accounting Review*, "Do Stock Prices Fully Reflect Information in Accruals..." [B] | accrual anomaly documented pre-2000, ~10%/yr spread in original sample (per Quantpedia screener #0038: 7.50% return / 10.26% vol OOS [V, fetched screener]) | McLean-Pontiff explicitly test accruals as one of their 97 predictors — among the "explained by publication" group | Aegis's `fundamentals_sec` panel does not currently carry a standardized accruals field (cash-flow-vs-earnings gap); this row needs a feature-build step before it can run — flag as a dependency, not a free seed |
| QUAL-04 | ROA/ROE top decile (if present in `fundamentals_sec`) | Fama & French 2006, 2015 (profitability factor RMW) [B] | RMW is one leg of the FF5 model | JKP replication rate 82.4% globally for the profitability theme [V] | check `fundamentals_sec` schema before registering; may collapse into QUAL-01 if only gross margin is available |
| QUAL-05 | composite quality score (rank-average of QUAL-01 + margin stability (`vol_63` of margin) + low accruals) | Asness, Frazzini & Pedersen 2019 QMJ, *RFS* [B] | AQR QMJ factor, published live since ~2013, positive but modest live Sharpe (~0.3-0.4 net, per AQR's own factor-performance disclosures) — **not independently re-verified this session** | — | a genuine multi-leg composite; register it distinctly from QUAL-01 so the receipt can show whether combining legs helps or just adds noise (canon: "the composite chose no feature on any training fold" §63 lesson applies here too) |
| QUAL-06 | earnings-quality inflection: `margin_chg` positive AND `rev_qoq` positive in the *same* quarter | derived, matches Deliverable-1's "inflection" family explicitly | — | — | this is literally the `rev_qoq × margin_chg` row the spec names; see INFL-01 below (duplicate id kept for cross-reference) |

### Value (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| VAL-01 | book-to-market top decile (cheap) | Fama & French 1992/1993, *JF*/*JFE* [B] | HML premium ~0.4-0.5%/mo in original 1963-1990 US sample | McLean-Pontiff: value-type predictors decay less than pure price/volume ones, but HML itself has had a well-documented "decade of drawdown" 2010-2020 [B, widely reported] | needs `fundamentals_sec` book value field, PIT-lagged; check availability before seeding as a free row |
| VAL-02 | earnings-to-price top decile | Basu 1977, *JF* [B] | one of the oldest documented anomalies | absorbed into JKP's value theme, replicates globally at theme level [V] | same PIT-fundamentals dependency as VAL-01 |
| VAL-03 | EV/EBIT top decile (cheap) | Greenblatt "Magic Formula" popularization; academically closest to Basu/Fama-French value [B] | Greenblat's own claimed backtest ~30%/yr 1988-2004 (his book) — **retail/popularization claim, not a peer-reviewed number**, keep separate from VAL-01/02 | independent replications (e.g. AQR, various practitioner write-ups) find far smaller, sometimes insignificant excess return once the Magic Formula's own small-cap tilt and survivorship-prone sample are corrected | list under RETAIL below too; the EV/EBIT leg alone is a legitimate value variant, the "Magic Formula" combination (value + quality-ish ROC screen) is the retail-favorite version |
| VAL-04 | composite value (rank-average of VAL-01, VAL-02, VAL-03) | standard practitioner construction, e.g. AQR value composite [B] | — | — | combination row; register both the single-leg and composite versions so multiplicity accounting is honest about which is "the same idea" three times |
| VAL-05 | value restricted to profitable firms only (VAL-01 ∩ QUAL-01) | Novy-Marx 2013 itself argues this combination hedges value's drawdowns [V — see QUAL-01 quote above] | joint profitability+value strategy Sharpe 0.85 vs 0.34 market, never had a losing 5-year window July 1963-Dec 2010 [V] | — | genuinely well-evidenced combination; a strong Combinations-family candidate |
| VAL-06 | deep-value / net-current-asset-value ("Graham net-nets") | Graham 1949 *The Intelligent Investor*; modern test in Quantpedia screener #0037: 31.19% OOS return [V, fetched] | huge headline number but on a tiny, illiquid, largely-delisted-candidate universe | Oppenheimer 1986 and others replicate historically; modern US equity universe has very few true net-nets outside micro/nano-cap | **NOT REACHABLE cleanly on current panel** without a dedicated tiny-cap/near-delisting universe filter; flag as a low-priority build |

### Investment / asset growth (3)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| INV-01 | total asset growth bottom decile (low-growth firms outperform) | Cooper, Gulen & Schill 2008, *JF*, "Asset Growth and the Cross-Section of Stock Returns" [B] | asset-growth spread documented as one of the largest anomalies pre-2008; Quantpedia screener #0052 "Asset Growth Effect": 20.84% return / 14.07% vol OOS [V, fetched screener] | JKP "investment" theme is one of the 13 clusters and replicates at the theme level, but Cooper-Gulen-Schill's own effect concentrates in small caps | **my #4 "expect dead" pick** — concentration in small/micro is exactly the survivorship/illiquidity trap the panel's §59 finding already exposed; see §4 |
| INV-02 | net stock issuance bottom decile (buybacks > issuance) | Fama & French 2008; Pontiff & Woodgate 2008, *JF* [B] | net-issuance anomaly among the more robust "financing" predictors in McLean-Pontiff's 97 | McLean-Pontiff test net issuance explicitly; moderate decay | overlaps with buyback-insider-divergence work already in the repo (`first_books/replay/buyback_insider_divergence_v0`) — check for duplication before registering |
| INV-03 | investment×momentum combination (INV-01 ∩ MOM-01) | Titman, Wei & Xie 2004 and later q-factor-model literature (Hou, Xue & Zhang 2015 "q-factor model") [B] | investment factor is one of four legs of the q-factor model, which JKP treat as a benchmark comparator | — | combination row |

### Size × liquidity (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| SIZ-01 | `amihud` top decile (most illiquid) long, monthly hold — the illiquidity premium | Amihud 2002, *J. Financial Markets*, "Illiquidity and Stock Returns" [B] | illiquidity premium documented pre-2002; Quantpedia and JKP both carry liquidity-theme factors that replicate at similar magnitude globally [V, JKP theme table] | already directly investigated on this exact panel: §59 (2026-09-22) found price/volume ranking at 21d nets **+0.28% gross vs a 35bps toll**, and **"liquid-only collapses to -0.18% — the edge IS the illiquidity"** [from project memory, this session's context] | this is not a hypothesis for Aegis, it is a **closed finding**: the family already knows illiquidity is where the raw edge lives and where costs kill it net. Register it in the library mainly so the nightly factory reproduces the known number, not as a fresh bet |
| SIZ-02 | small-cap decile alone (lowest `dollar_vol_log` quintile, no other signal) | Banz 1981, *JFE*, size effect | classic size premium | Documented to be flat-to-negative in the US large-cap-dominated era since the 1980s-2000s (widely reported, e.g. Dimson/Marsh/Staunton *Credit Suisse Global Investment Returns Yearbook* series) [B] | expect near-zero to negative net of costs on 2016-2026 US large/mega-heavy market cap growth; a good "known-dead" calibration row |
| SIZ-03 | `dollar_vol_log` bottom decile ∩ `mom_252_21` top decile — "small + momentum" | practitioner combination, echoes Fama-French size/momentum double sorts [B] | — | — | the small-cap version of MOM-01; expect it to inherit SIZ-01's illiquidity-driven gross/net gap |
| SIZ-04 | liquidity-adjusted momentum: MOM-01 signal, but weight by `1/amihud` at the portfolio-construction step | practitioner risk-parity-style construction [B] | — | — | a construction variant, not a new signal; test whether it changes net Sharpe materially vs equal-weight MOM-01 |
| SIZ-05 | size decile bottom EXCLUDING bottom-decile `dollar_vol_log` (i.e., "small but not illiquid") | derived directly from the §59 lesson | — | — | this is the natural fix implied by the family's own finding — worth registering explicitly as the "designed to survive costs" version of SIZ-01/02 |
| SIZ-06 | mega-cap-only momentum (top `dollar_vol_log` quintile ∩ MOM-01) | derived from canon: "the mega-cap is a SENSOR, not the trade" (`AEGIS_STRATEGIC_INVARIANTS.md`) | — | — | expected to have the *lowest* cost drag (mega band = 6bps) but per the invariant, also the smallest true edge — a deliberate low-Sharpe, high-capacity control row |

### Analyst revisions (10)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| AREV-01 | net EPS-estimate raises (raises − cuts) top decile, monthly hold | Womack 1996, *JF*, "Do Brokerage Analysts' Recommendations Have Investment Value?" [B] | analyst upgrades/downgrades carry significant post-event drift, esp. on the sell side | — | Aegis has dated revisions since 2011 — this is a first-class, already-available panel, unlike VAL/QUAL which need a fundamentals build step |
| AREV-02 | breadth of raises (`n_firms` raising, normalized by coverage) top decile | Gleason & Lee 2003, *The Accounting Review*, "Analyst Forecast Revisions and Market Price Discovery" [B] | breadth/consensus-shift measures add information beyond the level of estimates | — | directly matches the spec's "n_firms" field |
| AREV-03 | median target-price change top decile | practitioner target-price-revision literature, e.g. Brav & Lehavy 2003, *JF* [B] | target-price revisions predict returns incrementally over EPS revisions | — | matches spec's "median target change" field |
| AREV-04 | revision momentum: 3-month change in AREV-01's score, top decile ("revisions of revisions") | Jegadeesh & Kim 2006, *J. Financial Markets*, "Value of Analyst Recommendations" (international evidence) [B] | recommendation-revision effect present in most of the G7 markets they test, weaker in some | JKP-style: revision-based signals decay faster than price-momentum because they are cheap to compute and widely followed by sell-side desks themselves [B] | worth testing decay explicitly with by-year table (canon §64 lesson: "skill is at h=1, gone by h=5" for a related forward-forecast panel) |
| AREV-05 | StarMine-style "Analyst Revision Model" composite (weight recent, high-accuracy analysts more; approximate with recency-weighted `net raises`) | Refinitiv/StarMine ARM & SmartEstimate methodology (proprietary, described in vendor white papers, not a single peer-reviewed paper) [B] | vendor-claimed strong predictive power; independent academic tests are sparser because the weighting scheme is proprietary | no independent JKP-style replication exists because the exact accuracy-weighting is not public | Aegis cannot reproduce SmartEstimate's proprietary analyst-accuracy weights; this row is an *approximation* using count/breadth only — mark expected number as unverifiable against the vendor's own claim |
| AREV-06 | revisions + price momentum combination (rank-average AREV-01 + MOM-01) | Chan, Jegadeesh & Lakonishok 1996 already combine earnings and price momentum, *JF* [B] | combined signal outperforms either alone in their sample | — | canonical "combination" row within this family |
| AREV-07 | downgrade-avoidance: exclude bottom decile of net cuts from an otherwise unconditional universe (long-only overlay) | practitioner risk-overlay, no single paper [B] | — | — | cheap defensive variant, easy to test as a modifier on any long-only book |
| AREV-08 | target-price upside (median target / current price − 1) top decile | practitioner "implied upside" screens, related to Brav & Lehavy 2003 [B] | target-implied-return has modest but positive predictive power net of optimism bias | analysts are systematically over-optimistic on targets (well documented, e.g. Bradshaw 2004) — the *level* of upside is much noisier than the *change* in upside | expect AREV-03 (the change) to outperform AREV-08 (the level) net of cost — a clean within-family bake-off |
| AREV-09 | revision acceleration (2nd derivative: change in the rate of net raises) | derived, matches "inflection" logic applied to the revisions panel | — | — | pairs with INFL rows; test whether acceleration beats level (AREV-01) |
| AREV-10 | revision dispersion bottom decile (low disagreement among analysts = higher-conviction signal) | Diether, Malloy & Scherbina 2002, *JF*, "Differences of Opinion and the Cross Section of Stock Returns" [B] | high dispersion predicts *lower* future returns (over-optimism/short-sale-constraint story) | widely replicated as one of the more robust behavioral anomalies | good short leg for a combined long-raises/short-high-dispersion book |

### Earnings momentum / PEAD / SUE (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| PEAD-01 | standardized unexpected earnings (SUE) top decile, held ~60 trading days post-announcement | Bernard & Thomas 1989/1990, *J. Accounting Research*/*JAE*, the original PEAD papers [B] | drift persists 60+ days post-earnings in-sample, one of the most robust anomalies in accounting research | Chordia & Shivakumar 2006 tie PEAD partly to macro risk; some decay documented but PEAD remains among JKP's better-replicating themes [B] | Aegis's `rev_qoq` + a earnings-surprise construction from `fundamentals_sec` could proxy SUE; check whether the panel carries a true "consensus estimate at announcement" field, else this needs the analyst-revisions panel as the estimate source |
| PEAD-02 | price reaction magnitude on the earnings-announcement date itself (top decile, hold to next announcement) | "earnings announcement premium," Quantpedia screener #0080: 18.36% / 16.12% vol OOS [V, fetched] | positive announcement-window drift documented | — | needs a catalyst-calendar join for the announcement date itself, which Aegis has |
| PEAD-03 | earnings momentum combined with price momentum (Chan-Jegadeesh-Lakonishok 1996) | same as AREV-06 but built from realized SUE instead of analyst revisions [B] | combining the two "momentum" families outperforms either alone in-sample | — | duplicate-flag against AREV-06; keep both but note the shared ancestry for the multiplicity count |
| PEAD-04 | reversal of the PEAD drift beyond ~6 months (buy the losers of a stale SUE signal) | Quantpedia screener #0238 "Reversal in Post-Earnings Announcement Drift": 40.32% OOS return [V, fetched] | large headline OOS number on a strategy few retail sources discuss | single-source (Quantpedia); no independent academic replication found this session | mark evidence strength LOW — one number from one non-peer-reviewed database; treat as speculative until Aegis's own by-year table runs |
| PEAD-05 | earnings-announcement combined with buybacks (repurchase announced around earnings) | Quantpedia screener #0271: 25.20% / 11.11% vol OOS [V, fetched] | — | — | needs the catalyst calendar (buyback announcements) joined to earnings dates; check catalyst YAML coverage before registering |
| PEAD-06 | guidance-date drift (management forecast revisions, if present in the catalyst calendar) | Anilowski, Feng & Skinner 2007, *JAE* on guidance and analyst forecasts [B] | guidance revisions carry information similar to formal earnings surprises | — | depends on whether the catalyst YAML distinguishes guidance events from earnings events; flag as a schema check |

### Insider trading (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| INS-01 | opportunistic-insider net buying (Cohen-Malloy-Pomorski classification), top decile, monthly hold | Cohen, Malloy & Pomorski 2012, *JF*, "Decoding Inside Information" [V] | opportunistic long-short: **VW 82bps/mo (9.8%/yr, t=2.15); EW 180bps/mo (21.6%/yr, t=6.07)**, five-factor alpha, Jan 1986-Dec 2007, Thomson Reuters insider filings [V, direct quote]. Routine-trader portfolio: essentially zero (VW -20bps t=-0.57) | classification requires ≥3 years of an insider's trading history to label routine vs opportunistic — a real implementation cost, but the *effect itself* has held up in later practitioner replications (AQR wrote it up as a Journal-Article feature, no public refutation found) | **my #2 "expect to survive" pick** — see §4; note the paper's sample ends 2007, so post-2012 decay has not been independently re-tested in the academic literature this session found — the family's own forward book is the first fresh OOS test |
| INS-02 | opportunistic-insider net selling (short leg of INS-01) | same paper [V] | opportunistic sells are the *stronger* half: "over half the improvement... comes from the superior performance of opportunistic sells relative to routine sells" [V, direct quote] | — | Aegis's mandate/book construction may restrict shorting; if long-only, INS-02 becomes an *exclusion* filter (avoid names with opportunistic insider selling) rather than a short leg |
| INS-03 | insider cluster buys (≥3 distinct insiders buying within 30 days), no routine/opportunistic split | Lakonishok & Lee 2001, *Review of Financial Studies*, "Are Insider Trades Informative?" [B] | insider purchases (not sales) predict returns, concentrated in smaller firms; large-firm insider trading has weak predictive power | — | the size-concentration is the same trap as INV-01/SIZ-01 — expect INS-03 (unfiltered) to show the illiquidity pattern, while INS-01 (opportunistic-filtered) should be cleaner |
| INS-04 | insider cluster buys restricted to small/mid-cap band (deliberate opposite of SIZ-05) | derived from Lakonishok-Lee's own finding [B] | — | — | a designed-to-test-the-mechanism row: if the edge really is insider information (not illiquidity beta), INS-04 should beat SIZ-01's known illiquidity-only result net of the same cost band |
| INS-05 | insider + analyst-revision combination (INS-01 ∩ AREV-01) | no single paper combines these two exactly; natural extension | — | — | Combinations-family candidate; two independent information sources (corporate insiders, sell-side analysts) — good multiplicity-control test case since the sources are genuinely distinct |
| INS-06 | insider selling as a *market-wide* timing signal (aggregate opportunistic-sell/buy ratio), not stock selection | Seyhun 1988, *JFE*, aggregate insider trading and market timing [B] | aggregate insider sentiment has some market-timing power in-sample | — | this is a market-timing overlay, not a k-selection row — same caveat as MOM-07 |

### Catalyst / event (6)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| CAT-01 | post-8-K filing drift (top decile by a simple filing-tone/keyword proxy, if available) | Lee, Peress, Zhang et al. line of 8-K text literature (no single canonical paper) [B] | 8-K events carry measurable short-window abnormal returns in the literature | — | needs the catalyst YAML to carry 8-K item codes; check schema |
| CAT-02 | post-FDA-decision drift (biotech) | well-documented in event-study literature (e.g. Guedj & Scharfstein-style biotech event studies) [B] | large event-window returns around FDA decisions, biotech-specific | — | **NOT REACHABLE ON CURRENT PANEL** unless the catalyst calendar carries FDA PDUFA dates; flag as a data-acquisition dependency, not a free seed |
| CAT-03 | index-addition drift (S&P 500 inclusion effect) | Harris & Gurel 1986; Shleifer 1986, *JF*; more recent Petajisto 2011 finds the effect has shrunk | Petajisto 2011, *Financial Analysts Journal*, documents the S&P inclusion premium falling over the 2000s as index funds anticipate additions | explicit, well-documented decay: this is a textbook case of a published anomaly being arbitraged toward zero | **NOT REACHABLE ON CURRENT PANEL** (no index-membership-change calendar); also a good "expect dead" citation even if built, since Petajisto's own paper documents the decay |
| CAT-04 | earnings-date proximity (own a name in the N days before its next scheduled earnings) | practitioner "pre-earnings drift" overlays, related to PEAD literature [B] | mixed evidence; some pre-announcement drift documented, but also elevated event risk | — | needs the catalyst calendar's earnings-date field, which Aegis likely has via the fundamentals/analyst pipeline |
| CAT-05 | thesis-card verdict agreement (own names where the forward-only LLM thesis card says BUY) | Aegis-internal, forward-only [FWD] | n/a — generated 2026-09-25, no history | n/a | **forward-only per the Lookahead-Propensity rule** — cannot be backfilled; treat as a fresh forward-paper book from day one |
| CAT-06 | investigator-p agreement (own names where the forward "investigator" process forecast is high-confidence) | Aegis-internal, per memory §64 "`investigator` (a PROCESS) +8.97% held out vs nine thematic personas -27.98%" [this session's context, not re-verified] | Aegis's own §64 finding, not an external paper | the finding itself already distinguishes a *process* forecaster from *persona* forecasters — reuse that distinction rather than re-deriving it | this is the single most directly relevant prior result the library should seed from, since it is already a positive forward OOS result on Aegis's own ledger |

### Seasonality (8, with the honest evidence noted per row)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| SEAS-01 | turn-of-month (own broad market/names only in the last day + first 3-4 days of the month) | Ariel 1987, *JF*; Lakonishok & Smidt 1988 [B] | turn-of-month effect historically explained a large share of total monthly stock returns | Quantpedia screener #0041 "Turn of the Month in Equity Indexes": 7.20% / 6.90% vol OOS [V, fetched] — still shows up in an OOS-tracked database, i.e., not fully arbitraged away | testable directly as a calendar overlay on the existing panel; cheap and mechanical |
| SEAS-02 | January effect (small-cap outperformance concentrated in January) | Keim 1983, *JFE*; Reinganum 1983 [B] | strong in 1970s-80s small-cap samples | widely reported to have weakened sharply since the effect became well-known and since small-cap indices became easily tradable via ETFs (post-1990s); Quantpedia lists it (#0114) but with a much smaller "current" claimed edge than the historical one | **my #2 "expect dead" pick** — see §4; also a poor statistical case regardless of truth, since a 10-year window gives only ~10 non-overlapping January observations |
| SEAS-03 | "Sell in May and go away" (long equities Nov-Apr, flat/short May-Oct) | Bouman & Jacobsen 2002, *American Economic Review*, "The Halloween Indicator" [B] | documented across 36 of 37 countries studied, pre-2002 | Post-publication (McLean-Pontiff logic applies directly): numerous practitioner write-ups (e.g. by the original authors themselves in follow-up work, and by CXO Advisory-style trackers) report the effect weakening/reversing in parts of the post-2013 sample | **my #3 "expect dead" pick** — see §4; also not naturally a k-selection row (it's a market-timing calendar rule), so it belongs as an exposure-scaling overlay, not a strategy_library row with a `k` |
| SEAS-04 | Santa Claus rally (last 5 trading days of Dec + first 2 of Jan) | Yale Hirsch, *Stock Trader's Almanac* (popularization, not peer-reviewed) [B] | small but historically frequent positive window | genuinely thin/mostly-anecdotal evidence base outside the Almanac's own tracking | RETAIL-favorite; low confidence, cheap to test |
| SEAS-05 | pre-holiday effect (day before a market holiday) | Ariel 1990, *JFE*; Quantpedia screener #0083: 6.39% OOS [V, fetched] | documented pre-holiday abnormal returns | Quantpedia still tracks it OOS with a modest but positive number [V] | mechanical calendar overlay, cheap to test |
| SEAS-06 | day-of-week (Monday) effect | French 1980, *JFE*, "Stock Returns and the Weekend Effect" [B] | historically negative Monday returns | widely reported to have weakened/disappeared post-1987 in most US-equity studies (well-known "the weekend effect went away" finding, e.g. discussed in later replications) | good "textbook dead" calibration row — expect ~zero on 2016-2026 data |
| SEAS-07 | quarter-end window dressing (own recent winners in the last week of a quarter) | Lakonishok, Shleifer, Thaler & Vishny 1991, "Window Dressing by Pension Fund Managers," *AER* [B] | documented institutional rebalancing pattern | — | mechanical overlay, cheap; likely small/noisy on a diversified equity panel |
| SEAS-08 | 12-month cyclicality in the cross-section of stock returns (own names that historically outperform in the current calendar month) | Heston & Sadka 2008, *JFE*, "Seasonality in the Cross-Section of Stock Returns"; Quantpedia screener #0125: 8.60% / 12.20% vol OOS [V, fetched] | a genuinely distinct, less-publicized seasonality result (return seasonality at the *individual stock* level, not the calendar-wide level) | less arbitraged than SEAS-02/03/04/06 precisely because it is less well-known | worth taking seriously as a "less crowded seasonality" test, distinct from the famous-and-likely-dead calendar rules above |

### Fundamental inflection (4)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| INFL-01 | `rev_qoq` acceleration × `margin_chg` positive, top decile ("the spec's named row") | Aegis-internal per the spec's Deliverable 1 text; conceptually related to Piotroski 2000, *J. Accounting Research*, F-Score (multi-signal fundamental-inflection composite) [B] | Piotroski's F-score: value stocks with improving fundamentals significantly outperform value stocks with deteriorating fundamentals, 1976-1996 US sample | F-Score itself is one of the better-replicating composite scores in follow-up literature | already flagged in the family's own §54/§59 work as **fundamentals = GO (39bps/month, stable across k)** [this session's context] — a strong, already-partially-validated candidate |
| INFL-02 | revenue-growth acceleration alone (`rev_qoq` 2nd derivative, top decile) | derived, single-leg version of INFL-01 | — | — | bake-off leg vs INFL-01 to see whether margin adds information over revenue alone |
| INFL-03 | margin-expansion alone (`margin_chg` top decile, no revenue condition) — duplicate of QUAL-02, kept here for the family cross-reference | — | — | — | see QUAL-02 |
| INFL-04 | triple inflection: `rev_qoq` accel + `margin_chg` positive + `AREV-01` (analyst catching up to the inflection) | derived combination | — | — | tests whether sell-side analysts lag the inflection (a "does the market know yet" combination, directly answering the family's Rule #3 — "human intuition generates hypotheses, data adjudicates them") |

### Attention / social (4, forward-only for Aegis)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| ATT-01 | abnormal Google-search-volume top decile | Da, Engelberg & Gao 2011, *JF*, "In Search of Attention" [B] | SVI-based attention predicts short-horizon returns and IPO first-day pops in-sample, 2004-2008 sample | later work finds the effect weaker/noisier post-2012 as search-based trading became common (widely discussed in follow-on attention literature) [B] | **[FWD]** — Aegis has no historical Google Trends panel; would need a live pull, and even then it is only testable forward |
| ATT-02 | crowd-wisdom aggregation of retail-analyst articles (SeekingAlpha-style) | Chen, De, Hu & Hwang 2014, *Review of Financial Studies*, "Wisdom of Crowds: Crowdsourced Earnings Predictions" [B] | crowd sentiment from SeekingAlpha predicts earnings surprises and returns incrementally over Wall Street consensus, in-sample | — | **[FWD]** — no historical scrape exists in Aegis; forward-only |
| ATT-03 | LLM-generated sentiment score on the whole-market news feed (Aegis's own thesis-card / forecast pipeline) | Aegis-internal, forward-only [FWD] | n/a | n/a | **[FWD]**, and per canon a Lookahead-Propensity test is owed on every pre-cutoff LLM read (project memory) before this can even be treated as forward-clean |
| ATT-04 | social-media mention-spike top decile (Reddit/Twitter mention surge) | practitioner literature (e.g. WallStreetBets-era academic studies, 2021+, no single canonical paper) [B] | documented short-lived, high-variance return spikes associated with retail mention surges (GameStop-era literature) | explicitly a crowded, well-known, largely reflexive/short-lived effect by the time it is public | **[FWD]** and low prior — the mechanism (retail herding) is close to self-negating once documented |

### Combinations (8)

| id | rule | source | reported number | decay/replication | survival note |
|---|---|---|---|---|---|
| COMB-01 | "Value and Momentum Everywhere" — rank-average of VAL-04 and MOM-01 | Asness, Moskowitz & Pedersen 2013, *JF* [B] | value and momentum are negatively correlated across 8 markets/asset classes; combining them roughly doubles the Sharpe of either alone in their global sample | one of the best-known and most-replicated combination results (AQR's public factor data continues to track this) | strong Combinations candidate — the negative correlation is the whole point, and Aegis can test it directly since both legs exist on the panel (pending VAL's fundamentals dependency) |
| COMB-02 | quality + momentum (QUAL-01 ∩ MOM-01, rank-average) | derived; consistent with Novy-Marx's own four-factor model treating value, momentum and profitability as near-orthogonal legs [V, from QUAL-01 paper] | — | — | — |
| COMB-03 | low-vol + value (LV-01 ∩ VAL-04) | "Defensive value" practitioner framing, no single canonical paper [B] | — | — | — |
| COMB-04 | momentum + analyst revisions (MOM-01 ∩ AREV-01) — duplicate of AREV-06, cross-referenced | Chan, Jegadeesh & Lakonishok 1996 [B] | — | — | see AREV-06/PEAD-03 |
| COMB-05 | insider + momentum (INS-01 ∩ MOM-01) | derived | — | — | tests whether informed-insider buying and price momentum are additive or redundant |
| COMB-06 | small + quality + momentum triple sort | derived, in the spirit of Fama-French-style triple sorts | — | — | multiplicity-heavy row — three legs means three chances to overfit; flag for extra DSR scrutiny |
| COMB-07 | rank-average of the library's own top-3 DSR-surviving singles each night (a dynamically-defined "meta" row) | Aegis-internal design, not literature | n/a | n/a | this is explicitly the thing `docs/ROADMAP...` warns against doing prematurely ("a learned router comes after several independent selectors exist, not before") — register it but do NOT let it dominate the leaderboard on night one |
| COMB-08 | fundamentals inflection + insider agreement (INFL-01 ∩ INS-01) | derived | — | — | two independently-sourced signals (accounting data, Form-4 filings) — good multiplicity-control case, same logic as INS-05 |

### Retail / quant-blog favourites (14)

| id | rule | source (claimed number) | independent replication finding | evidence strength |
|---|---|---|---|---|
| RET-01 | Golden Cross / Death Cross (`px_vs_ma50` crosses `px_vs_ma200`) | r/algotrading and technical-analysis canon; no formal academic backing as a stock-picking (vs index-timing) rule [B] | Academic tests of moving-average crossover rules on individual equities generally find the edge concentrated (if anywhere) at the *index* level and largely explained by trend/momentum exposure, not a distinct signal (Brock, Lakonishok & LeBaron 1992, *JF*, is the closest formal test, on the Dow index) | LOW as a stock-selection rule; the panel already has `px_vs_ma50`/`px_vs_ma200` so it is a free, cheap-to-discredit-or-confirm row |
| RET-02 | RSI mean-reversion (buy oversold, `rev_5`/`rev_1` proxy for RSI) | ubiquitous retail technical-analysis rule [B] | same literature as REV-01/02 above — largely a reversal-microstructure effect, heavily arbitraged | LOW-MODERATE; effectively a re-labeling of REV-01/02 |
| RET-03 | "Buy the dip" (own names after a large `max_drawdown_63`) | retail canon, no formal paper | overlaps with REV-04/LV-05; academic reversal literature says short-horizon dips revert (REV family) but says nothing distinct for this specific framing | LOW; likely fully redundant with REV/LV rows already listed |
| RET-04 | Turtle-style trend following (Donchian channel breakout, approximate with `px_vs_52w_high`) | Richard Dennis's "Turtle Traders" (1980s, popularized by Curtis Faith's book, not peer-reviewed) [B] | closest academic analog is TSMOM (Moskowitz-Ooi-Pedersen, MOM-07); documented decay in trend-following CTA returns since ~2010s is widely reported in industry (e.g. SG CTA/Trend Index underperformance discussions) | LOW-MODERATE; largely redundant with MOM-04/MOM-07 |
| RET-05 | Alpha Architect "QVM" (quantitative value + momentum) screen | Alpha Architect blog/books (Gray & Carlisle, *Quantitative Value*, *Quantitative Momentum*) [B] | their own books cite the same academic literature as VAL/MOM above; Alpha Architect's live ETFs (QVAL, QMOM, etc.) have public track records that can be checked directly (not fetched this session) | MODERATE — has a live, checkable ETF track record, unlike most retail claims; worth an exa fetch of QVAL/QMOM's actual live returns before the builder trusts the "backtest" number |
| RET-06 | Composer "symphonies" (rules-based tactical allocation, e.g. leveraged sector rotation) | Composer.trade platform, user-published, not peer-reviewed | Composer's own symphonies are mostly index/ETF-timing rules (not single-stock cross-sectional selection) and frequently use leverage; independent scrutiny (e.g. Bogleheads-forum-style critiques) commonly flags backtest overfitting on short/curated windows | LOW; largely **NOT REACHABLE** as a single-stock `strategy_library` row — it is an asset-allocation-overlay category, not a cross-sectional stock ranker |
| RET-07 | Short-interest effect (long low-short-interest, short high-short-interest names) | Quantpedia screener #0045/#0046: L/S 19.70%/17.14% vol; long-only 26.80% OOS [V, fetched]; academically, Asquith, Pathak & Ritter 2005, *JFE* | one of the better-evidenced "retail-adjacent" anomalies — has real academic backing (not just a blog claim) | MODERATE-HIGH; needs a short-interest data feed Aegis does not currently list among its panels — flag as a data dependency |
| RET-08 | 52-week-high anchoring, duplicate of MOM-04, but framed as the popular "buy stocks near new highs" retail heuristic | George & Hwang 2004 [B] (same as MOM-04) | — | already covered under MOM-04; listed here only because it is independently a top retail/Quantpedia favorite (screener #0088: 11.75%/11.00% vol OOS [V, fetched]) |
| RET-09 | Options-market-implied volatility-risk-premium overlay | Quantpedia screener #0018 "Volatility Risk Premium Effect": 26.00%/19.00% vol OOS [V, fetched] | large academically-documented premium (selling variance swaps/options) — but this is an *options* strategy, not a cash-equity cross-sectional ranker | **NOT REACHABLE** on the current equity-only panel without an options chain; flag as out of scope for `strategy_library` v1 |
| RET-10 | "13F cloning" (mimic disclosed hedge-fund holdings) | Quantpedia screener #0042 "Alpha Cloning - Following 13F Filings": 20.21% OOS [V, fetched] | academically related to Cohen, Frazzini & Malloy's work on portfolio manager networks, but naive 13F-cloning is well known to lag by up to 45 days (disclosure delay) and to have decayed as it became popular practitioner knowledge | MODERATE-LOW; needs a 13F feed Aegis doesn't currently list — flag as a data dependency, and expect meaningful decay from the reporting lag alone |
| RET-11 | Pairs trading / statistical arbitrage (sector-neutral mean reversion between correlated names) | Quantpedia screener #0012: 11.16%/5.85% vol OOS [V, fetched]; academic root Gatev, Goetzmann & Rouwenhorst 2006, *RFS* | Gatev et al. themselves document declining profitability of classic distance-method pairs trading through their sample (ending 2002); widely reported to have decayed further since as it became a retail/prop-desk staple | LOW-MODERATE as a *simple* distance-method pairs strategy; **structurally different** from the rest of this catalogue (it's a relative-value pair rule, not a k-of-N cross-sectional rank) — would need its own construction inside `strategy_library`, not a one-line rule over `FEATURES` |
| RET-12 | FOMC-meeting-day effect (own the market around scheduled Fed meetings) | Quantpedia screener #0075: 6.19% OOS [V, fetched]; academic root Lucca & Moench 2015, *JF*, "The Pre-FOMC Announcement Drift" | Lucca-Moench's own effect has been reported (in later practitioner and some academic commentary) to have weakened in the post-2015 sample as it became widely known | LOW-MODERATE; market-timing overlay, not single-stock selection — same structural note as SEAS-03 |
| RET-13 | Option-expiration-week effect | Quantpedia screener #0102: 9.30%/8.70% vol OOS [V, fetched] | thinly documented outside Quantpedia's own tracking; no major peer-reviewed paper found this session | LOW; single-source evidence, mark for Aegis's own by-year table to adjudicate |
| RET-14 | "January Barometer" (as the S&P 500 goes in January, so goes the year) | Quantpedia screener #0113: 10.38%/16.80% vol OOS [V, fetched]; popularized by Yale Hirsch | a market-timing calendar rule with an obvious small-sample problem (only ~1 observation per year — with a 2016-2026 window that is **10 independent observations total**, nowhere near enough for any claim) | LOW, and a clean teaching example for the "block count" section below — 10 years = 10 blocks, full stop |

**Row count: 12+6+8+6+6+3+6+10+6+6+6+8+4+4+8+14 = 113**, inside the spec's
100-140 target. Several rows are explicitly flagged `NOT REACHABLE ON CURRENT
PANEL` or `[FWD]` — the builder should decide whether those count toward the
"≥100 seeded" floor or whether only the panel-reachable ~95 do; I'd count only
the reachable ones toward the floor and keep the rest as a documented backlog,
per the family's own rule that a module needs a caller or a classification,
never silent absence.

---

## 2. Open-source backtests and libraries

| library | license | data / PIT & survivorship handling | overlap with our 113 rows | verdict |
|---|---|---|---|---|
| **JKP Global Factor Data** (`jkpfactors.com`, code at `github.com/bkelly-lab/jkp-data` and the legacy `bkelly-lab/ReplicationCrisis`) [V] | Free data download + open Python/R code; cite the paper. Underlying WRDS/Compustat/CRSP access still needed to *regenerate* from scratch, but pre-built factor and characteristic files are free | Standard Compustat/CRSP academic PIT convention (accounting-lag by 4-6 months, no restatement look-ahead); the global 93-country sample specifically targets survivorship by including delisted names via standard CRSP delisting-return conventions | 406 characteristics, 153 published factors — directly overlaps VAL, QUAL, INV, MOM, LV families (roughly 35-45 of our rows have a near-exact JKP characteristic to cross-check against, e.g. `at_gr1` for INV-01, `gp_at` for QUAL-01, `beta_60m` for LV-03) | **best cross-check target for the fundamentals/price-based families.** Does not cover AREV, PEAD (US-specific IBES-style estimate data), INS, CAT, ATT, or any forward-only row — those are Aegis's own edge over a purely academic replication |
| **Quantpedia Screener + Premium** (`quantpedia.com`) [V] | Commercial (Screener free tier ~70 strategies; Premium 900+ paywalled); do not copy their QuantConnect code, only cross-check the *numbers* per the spec's own instruction | ~800 of the Premium strategies carry monthly-updated out-of-sample QuantConnect backtests with equity curves; PIT/survivorship handling is per-strategy and not independently audited by Aegis | Free-tier screener alone gave usable numbers for RET-07/08/09/10/11/12/13/14, SEAS-01/05/08, INV-01, VAL-06, QUAL-03, PEAD-02/04/05 — i.e., a large fraction of the RETAIL and SEAS families' "claimed numbers" in the table above came directly from this fetch | good, fast source for a first cross-check number; treat every Quantpedia figure in this doc as **single-source** until Aegis's own receipt confirms or refutes it |
| **`vectorbt`** (`github.com/polakowo/vectorbt`, ~8.9k★) [V] | "Fair-code" — Apache-2.0 + Commons Clause (free to use internally, cannot resell as a product) | No built-in survivorship/PIT handling — entirely the user's responsibility, same posture Aegis already takes with `xs_ranker` | Implements none of our 113 rules out of the box; it is a *speed* library (vectorized NumPy/Numba), not a factor-definition library | **the right engine, not the right factor set.** Its "test thousands of configurations, packed into arrays" design is exactly what a 900-cell nightly sweep needs — worth benchmarking `night_backtest_factory.py`'s vectorization against vectorbt's approach even if Aegis keeps its own code |
| **`zipline-reloaded`** (`github.com/stefan-jansen/zipline-reloaded`, ~1.9k★) [V] | Apache-2.0 | Bundle-based data ingestion; PIT is whatever the user's bundle encodes — no first-class point-in-time guarantee | Its Pipeline API is a reference architecture for factor-ranking pipelines, but implements none of our specific 113 rules | reference for API design only; independent benchmarking (fetched this session) shows it is the slowest of the three general engines (2.9s for a single 5yr/500-name run vs vectorbt's 0.7s) — not the right engine for a 90-minute, 900-cell nightly budget |
| **`alphalens-reloaded`** (`github.com/stefan-jansen/alphalens-reloaded`) [V] | same family/license as zipline-reloaded | Consumes whatever panel it's given; no independent survivorship handling | Its IC/quantile-return/turnover diagnostics are functionally what `xs_ranker.top_k_backtest`'s by-year/LOO/breadth outputs already do | good for a sanity cross-check of `xs_ranker`'s own diagnostic shapes, not needed as a dependency |
| **`bt`** (pmorissette, portfolio-allocation backtester) | BSD-ish (not independently re-verified this session) | Portfolio-allocation-level, not single-name cross-sectional-ranking oriented | Low overlap — designed for asset-allocation backtests (rebalancing between funds/ETFs), not stock-picking | LOW priority per third-party ranking found this session (autotradelab: "niche tool, not a trading system," 5.5/10) [V] |
| **Qlib (Microsoft)** [B, not fetched this session — background knowledge only, flag for the builder to verify independently] | MIT, ~37k★ per a third-party framework comparison fetched this session [V, indirect mention] | Qlib's stated design goal is first-class point-in-time data and survivorship-aware instrument-universe configs (e.g., historical CSI300 membership) — closer in spirit to `xs_ranker`'s own survivorship-free panel discipline than any other tool on this list, **but this specific PIT claim was not independently re-verified this session** and should be checked against Qlib's own docs before being relied on | Alpha158/Alpha360 factor libraries overlap heavily with the price/volume half of `FEATURES` (momentum, volatility, volume-pressure operators analogous to `resid_mom_63`, `vwap_pressure`, `gap_share`) | **worth a dedicated follow-up session**: running Alpha158 against the same 2016-2026 panel would be the single best independent cross-check for the MOM/REV/LV families, since it is the one open tool built with the same PIT discipline Aegis already insists on |
| **OpenBB** | mixed (core AGPL/MIT depending on module) [B, not fetched this session] | Aggregates free/paid data sources (FMP, Polygon, EDGAR) with a screener layer; not itself a PIT-safe backtest engine | Could be a *data source* for AREV/INS/PEAD (EDGAR-based Form 4, 8-K, analyst estimates) rather than a backtester | flag as a data-sourcing option, not a backtest cross-check tool; not independently verified this session — treat as a lead, not a citation |
| **WRDS-free replications since 2024 (GitHub search)** | not surveyed individually this session | — | — | **not done** — a dedicated GitHub search for "post-2024 WRDS-free factor replication" repos was not completed under this session's effort budget; flag as an open follow-up for whoever picks up Deliverable 2's build |

---

## 3. The honest arithmetic

**Trial count.** ~95-113 seeded strategies × 3 k-values (10/20/50, per the
spec's own `xs_ranker` convention) × 3 holds (21/63/126 sessions) ≈ **855-1,017
cells**, matching the spec's own "~900 cells" estimate. Several rows are
themselves near-duplicates by construction (MOM-01/02/03, LV-01/02/05, three
value legs plus a composite, three momentum-analyst-revision combinations
counted three separate times across MOM-12/AREV-06/PEAD-03/COMB-04) — the
**effective** number of independent hypotheses is materially smaller than 900,
which matters for both the multiple-testing correction and for reading the DSR
honestly (see below).

**Multiple-testing bar.** Harvey, Liu & Zhu 2016, *RFS*, "…and the
Cross-Section of Expected Returns" [V]: given the historical rate of factor
production in the finance literature (≈313 papers by their count), a *newly
discovered* factor needs **t ≥ 3.0**, not the traditional 2.0, and their own
20-year forward projection pushes the hurdle higher still as more factors get
tried. That hurdle was calibrated to the *entire published literature's*
factor-production rate, not to one night's internal sweep — using it verbatim
for a single 900-cell night is conservative in one direction (900 tonight vs.
~313 papers over decades) and generous in another (this library is testing
mostly-known, mostly-correlated variants of a dozen or so true underlying
ideas, not 900 independent new hypotheses). **The receipt should print t ≥ 3.0
as the headline bar, exactly as the spec says, but also print the *effective*
number of independent factor families (cluster the 113 rows the way JKP
clusters 153 factors into 13 themes) so a reader can see whether the true
multiplicity is closer to 900 or closer to 15.**

**Deflated Sharpe Ratio (DSR).** Bailey & López de Prado 2014, *Journal of
Portfolio Management*, "The Deflated Sharpe Ratio: Correcting for Selection
Bias, Backtest Overfitting and Non-Normality" [B — not re-fetched this
session, well-known formula]:

```
DSR = Φ( (SR_hat - SR_0*) * sqrt(n-1) / sqrt(1 - γ3·SR_hat + ((γ4-1)/4)·SR_hat²) )
```

where `SR_0*` is the *expected maximum* Sharpe ratio achievable by pure noise
given `N` independent trials, `n` is the number of return observations behind
`SR_hat`, and `γ3`/`γ4` are the skewness/kurtosis of the strategy's returns
(non-normality correction — directly relevant here since insider/PEAD/
short-interest strategies are exactly the fat-tailed, positively-skewed-then-
crash-prone kind DSR was built to catch). `SR_0*` itself comes from
extreme-value theory:

```
E[max SR] ≈ sqrt(V[SR]) · [(1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e))]
```

(`γ` = Euler-Mascheroni ≈ 0.5772). With monthly rebalancing over the 2020-2026
window (72 months) and `V[SR] ≈ 1/T`, at `N = 900` the noise ceiling on the
*maximum* observed Sharpe is roughly `sqrt(1/72) · Φ⁻¹(1 - 1/900) ≈
0.118 × 3.09 ≈ 0.36` — meaning **a top-of-900 Sharpe below roughly 0.4-0.5 over
this window is indistinguishable from the best of 900 noise draws**, and the
"1,000% vs 200%" style headline the family wants to eventually print needs a
Sharpe well north of that, deflated by the *actual* (not nominal) trial count,
before it is anything more than the winner of a lottery. `top_k_backtest`
should carry `dsr` next to `sharpe` on every leaderboard row exactly as the
spec already requires, computed at both `n=900` (nominal) and `n=`(effective
cluster count) so the reader sees the range.

**Block count on 2020-2026 at monthly rebalance.** 72 calendar months. This is
where the family's own §64 lesson (`docs/CLAUDE.md` item 11 / the
`n_effective`-counts-date-blocks canon rule) bites hardest, and it bites
*differently by hold length*, which is exactly the "a t whose bias depends on
the swept parameter" lesson already in memory:

| hold (sessions) | non-overlapping independent blocks in 72 months | what a "top 10 since 2020" table can honestly claim |
|---|---|---|
| 21 (≈1 month) | ~72 | enough blocks for a real by-year table (6 years × ~12); still needs LOO-worst-year read before any headline, per the §64 "print by year" rule already in memory |
| 63 (≈3 months) | ~24 | marginal — 24 independent quarterly observations is thin for a t-statistic that claims more than "directionally positive"; DSR should be computed with `n=24`, not `n=72`, for these cells |
| 126 (≈6 months) | ~12 | **not enough for any standalone claim** — 12 independent half-year draws cannot support a t ≥ 3.0 hurdle no matter how large the point estimate; a 126-session-hold row's number is a PRODUCT_EXPERIMENT observation at best, never a RESEARCH_CLAIM, on this window alone |

The practical instruction for `night_backtest_factory.py`: **re-derive `n` for
the t-statistic and the DSR from the hold length being swept, not from the
72-month calendar count uniformly** — this is the exact defect the family
already found and fixed once (the horizon-sweep t-stat bug, `docs/CLAUDE.md`
item 11) and the same bug is latent here if `k`/`hold` sweeps share one `n`.

---

## 4. Five bets to survive, five expected dead

### Expect to survive

1. **QUAL-01 — Novy-Marx gross profitability.** 82.4% JKP global replication
   rate for the theme [V], and critically, the *original* construction rebalances
   annually / turns over roughly once every four years in its low-frequency
   form [V, direct quote] — i.e. it is the one family in this catalogue with
   turnover low enough to survive even the 35bps small-cap cost band without
   the edge being mostly cost. **Settling observation**: print realized
   turnover in the receipt; if it stays under ~4x/year net of the rebalance
   rule, the net-of-cost Sharpe should stay close to the gross one.
2. **INS-01 — opportunistic insider buying.** 82bps/mo VW, 180bps/mo EW
   five-factor alpha [V, direct quote], and the mechanism (three years of an
   insider's trading history needed to classify them) is a genuine
   implementation moat — most retail and even many practitioner insider-signal
   products use the raw Form-4 filing without the routine/opportunistic split,
   so it hasn't been arbitraged as hard as its raw-insider-trading cousins.
   **Settling observation**: net-of-cost-by-band Sharpe stays positive when
   restricted to non-mega names (INS-04) — i.e. the edge is insider information,
   not the SIZ-01 illiquidity beta wearing an insider costume.
3. **LV-08 — betting-against-beta, mega/large band only.** BAB Sharpe 0.78 over
   1926-2012, positive in 18/19 developed markets [V], and low-vol names
   cluster in the mega/large liquidity bands where Aegis's own cost table
   charges only 6-10bps. **Settling observation**: the mega/large-restricted
   version should show materially less net-vs-gross erosion than any small/mid
   version of the same signal.
4. **AREV-01/02 — analyst revision breadth and net raises.** Aegis already has
   dated revisions since 2011 as a first-class panel (unlike VAL/QUAL, which
   need a fundamentals-schema build step), and per §54 fundamentals-adjacent
   work is already flagged **GO (39bps/month, stable across k)** [this
   session's context]. **Settling observation**: leave-one-year-out worst year
   stays positive, per the §64 lesson that a positive headline must survive
   `groupby(year).mean()` before it is believed.
5. **INFL-01 — revenue acceleration × margin expansion.** Directly descended
   from the family's own already-partially-validated fundamentals-inflection
   work, and structurally similar to Piotroski's F-Score, one of the
   better-replicating composite scores in the follow-up literature.
   **Settling observation**: INFL-01 should beat both single-leg versions
   (INFL-02 revenue-only, INFL-03 margin-only) — if it doesn't, the "inflection"
   framing is adding complexity without adding signal (same trap as the §63
   composite-chose-nothing lesson).

### Expect dead after costs

1. **REV-01/02 — 1-day/5-day short-term reversal.** Needs daily-to-weekly
   turnover against an 18-35bps mid/small cost band; McLean-Pontiff show
   price/volume-only predictors decay hardest of all [V], and the family's own
   related finding ("all 11 exit rules lose to holding," fleet-replay memory,
   this session's context) already shows fast trading rules die to cost on
   this exact panel. **Settling observation**: implied round-trip count per
   name per year; if it's in the double digits, the gross edge (already modest
   in the literature) cannot clear the cost line.
2. **SEAS-02 — the January effect.** Both a decayed-effect story (widely
   reported weakening since the 1980s-90s small-cap-premium era) and a
   statistically starved one — a 2016-2026 window gives only ~10 independent
   January observations, nowhere near enough for any claim regardless of the
   true effect size. **Settling observation**: the by-year table for a
   January-only book shows no more than noise-level dispersion across the ~10
   years available.
3. **SEAS-03 — "Sell in May."** Bouman & Jacobsen's own 36-of-37-country result
   [B] is a market-timing calendar rule, not a cross-sectional one, and
   post-2013 practitioner tracking widely reports the seasonal spread
   weakening/reversing. **Settling observation**: compare Nov-Apr vs May-Oct
   SPY legs 2016-2026 net of nothing; expect an inconsistent sign across years
   (this doubles as a demonstration that a calendar-timing rule doesn't even fit
   the `strategy_library`'s per-name `k`/`hold` schema cleanly).
4. **INV-01 — asset growth, unfiltered.** Concentrates in exactly the small/
   illiquid names the family's own §59 finding already showed drive the
   panel's survivorship and illiquidity bias — "the edge IS the illiquidity."
   **Settling observation**: run the same liquid-only-subsample test the panel
   already ran for price/volume ranking; expect the same collapse-toward-zero
   pattern (from +2084bps-style Quantpedia headline down to near nothing net
   of realistic costs on liquid names).
5. **ATT-01/02/03/04 — attention/social factors.** Genuinely `[FWD]` for
   Aegis (no historical data at all), and even in their own literature the
   documented edge is short-horizon and has been reported to fade as
   search/social-based trading became common post-2012. **Settling
   observation**: the spec's own adopt/reject rule already settles this one —
   ≥63 sessions of forward paper trading beating both SPY and the random-
   same-band twin, or it's REJECTED. No backtest can settle it either way, which
   is itself the finding worth printing on the receipt.

---

## 5. Sources (every non-`[FWD]`/non-derived row above links back to one of these)

- McLean & Pontiff 2016, *Journal of Finance* 71(1):5-32, "Does Academic
  Research Destroy Stock Return Predictability?" — https://doi.org/10.1111/jofi.12365
  (SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623)
- Jensen, Kelly & Pedersen 2023, *Journal of Finance* 78(5):2465-2518, "Is
  There a Replication Crisis in Finance?" — https://doi.org/10.1111/jofi.13249 ;
  data/code at https://jkpfactors.com and https://github.com/bkelly-lab/jkp-data
- Harvey, Liu & Zhu 2016, *Review of Financial Studies* 29(1):5-68, "…and the
  Cross-Section of Expected Returns" — https://doi.org/10.1093/rfs/hhv059
  (SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2249314)
- Novy-Marx 2013, *Journal of Financial Economics* 108(1):1-28, "The Other
  Side of Value: The Gross Profitability Premium" — https://doi.org/10.1016/j.jfineco.2013.01.003
- Frazzini & Pedersen 2014, *Journal of Financial Economics* 111(1):1-25,
  "Betting Against Beta" — https://doi.org/10.1016/j.jfineco.2013.10.005
- Cohen, Malloy & Pomorski 2012, *Journal of Finance* 67(3):1009-1043,
  "Decoding Inside Information" — https://doi.org/10.1111/j.1540-6261.2012.01740.x
- Quantpedia Screener (free tier) — https://quantpedia.com/screener and
  https://quantpedia.com/pricing/ (strategy counts and OOS return/vol figures
  quoted above pulled directly from the live screener page)
- `stefan-jansen/zipline-reloaded` — https://github.com/stefan-jansen/zipline-reloaded
- `stefan-jansen/alphalens-reloaded` — https://github.com/stefan-jansen/alphalens-reloaded
- `polakowo/vectorbt` — https://github.com/polakowo/vectorbt
- Framework comparisons (independent, third-party, fetched this session):
  autotradelab "20+ Algo Trading Frameworks Reviewed" —
  https://autotradelab.com/blog/nautilus-vs-vectorbt-vs-freqtrade-20-python-quant-trading-frameworks-compared ;
  pickuma "Backtrader vs VectorBT vs Zipline-Reloaded, Benchmarked" —
  https://pickuma.com/for-dev/python-backtesting-frameworks-backtrader-vectorbt-zipline-2026/
- All `[B]`-tagged rows (Jegadeesh-Titman 1993, George-Hwang 2004, Sloan 1996,
  Fama-French 1992/1993/2006/2015, Amihud 2002, Banz 1981, Cooper-Gulen-Schill
  2008, Ang-Hodrick-Xing-Zhang 2006, Asness-Moskowitz-Pedersen 2013,
  Asness-Frazzini-Pedersen 2019, Womack 1996, Gleason-Lee 2003, Jegadeesh-Kim
  2006, Chan-Jegadeesh-Lakonishok 1996, Diether-Malloy-Scherbina 2002,
  Bernard-Thomas 1989, Lakonishok-Lee 2001, Seyhun 1988, Da-Engelberg-Gao 2011,
  Chen-De-Hu-Hwang 2014, Bouman-Jacobsen 2002, Ariel 1987/1990,
  Keim 1983/Reinganum 1983, French 1980, Lakonishok-Shleifer-Thaler-Vishny 1991,
  Heston-Sadka 2008, Piotroski 2000, Bailey-López de Prado 2014, Moskowitz-
  Ooi-Pedersen 2012, Petajisto 2011, Gatev-Goetzmann-Rouwenhorst 2006, Lucca-
  Moench 2015, Asquith-Pathak-Ritter 2005) are well-known results not
  individually re-fetched this session under the effort budget — the builder
  should spot-check any row before it drives a real capital decision, per the
  three-licences rule: this catalogue is sufficient to license
  `PRODUCT_EXPERIMENT` exploration on all of them, but none of these `[B]` rows
  clears `RESEARCH_CLAIM` on citation strength alone.
