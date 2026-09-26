# Research — CHUNK D: toward 200 strategies, a second-engine cross-check, and a sealed-return leaderboard (2026-09-26)

For `backend/services/strategy_library.py`, `scripts/night_backtest_factory.py` and
`backend/data/optimus/strategy_library/LEADERBOARD.md`. Read alongside
`docs/research_notes/2026-09-26/research_strategy_library.md` (the 113-row
catalogue, "[V]"/"[B]"/"[FWD]" tags carried over unchanged here) and
`external_session_brief_2026-09-26.md` §D. Tools used this session: `exa`
(`web_search_exa`/`web_fetch_exa`) — `WebSearch` reported the session-wide
200/200 budget already spent before this task started, same as the prior
strategy-library research session; every `[V]` citation below was fetched via
exa, not WebSearch.

## 0. Where the library actually stands tonight

- `LEADERBOARD.md`: **112 rules, 336 cells** (112 × k∈{10,20,50}), first night,
  **no row clears DSR ≥ 0.95** at either n=336 (analytic null) or the 11-family
  effective count. Top-by-DSR is `mom_12_1_q` at DSR **0.293**; every `low_risk`
  row is **structurally negative** (t as low as −7.40 on 115 blocks) — the
  single cleanest finding already on the board is that naive low-volatility
  selection on this cost-and-survivorship-free panel currently *loses*, not
  that nothing works.
- `strategy_library.Strategy` is a frozen dataclass: `id, family, description,
  signal, universe_rule, k, hold_months, source, literature_reported, control,
  cost_scale`. Every rule is **one function over the panel** built from
  `col(name, sign)`, `rank_of`, `combo(*legs)` (rank-average), `gated(base,
  gate_col, lo, hi)` (filter, not rank) and `within_top(base, rank_col, frac,
  sign)`. `check_costs` refuses a zero-cost run unless `zero_cost_diagnostic`
  is declared, inherited from `portfolio_farm.Policy` — the same one place
  decides whether a frictionless run is legal, for every rule. `run_strategy`
  is the ONLY execution path (equal-weight top-k, monthly-or-longer rebalance,
  half the band round trip charged per side, drift between rebalances untraded
  and uncharged) — a new mechanism plugs into this, it does not get its own
  backtester.
- Columns already on the panel that Part 1 below writes against: `FEATURES`
  (`mom_21/63/126/252_21, rev_1, rev_5, vol_21, vol_63, vol_ratio,
  dollar_vol_log, turnover_surge, trade_surge, px_vs_52w_high/low,
  px_vs_ma50/200, amihud, gap_share, vwap_pressure, resid_mom_63, beta_63,
  up_days_21, max_drawdown_63, skew_63`), PIT fundamentals (`rev_qoq,
  gross_margin, margin_chg`, subject to `_FUND_CAVEAT`: SEC facts joined on
  `filed`+2d, annual flows only, NaN past 460 days), dated analyst revisions
  with `firm`/`n_firms`/`target_action` (`revision_flow.py`,
  `analyst_intelligence.py`, `expected_return.py` — firm-level identity
  tracking already exists, it is not a new build), price-target snapshots
  since **2026-09-24 only** (`forecast_dispersion_v1` is already registered as
  `FORWARD_ONLY` for exactly this reason), insider/13F/congress
  `pit_observations` (13F parquet back to 1996 via
  `backend/data/optimus/wrds/tr13f_s34_*.parquet`; congress data has at least
  one prior test, `night_factory_2026-09-20/congress_leadership_split_backtest.json`,
  TRIAL-CONGRESS-IC — check that trial before re-registering a congress row as
  novel), the catalyst calendar (currently richest in the LLM-portfolio
  factory outputs, `llm_portfolio/factory/2026-09-25*/*_catalyst_calendar.*`),
  the news corpus keyed on `first_seen_utc` (`scripts/news_pull.py`,
  `night_e1_news_return_panel.py` — **history is short**, `E1` builds from
  `years=("2025","2026")` by default, so a news-derived signal has at most
  ~20 months, not the panel's full 2016–2026 span), and forward-only
  thesis-card verdicts (`thesis_card.py`, `bull/bear/falsifier/verdict/
  confidence` — a verdict is evidence and a falsifier, per its own docstring,
  never an order).
- Two dependencies Part 1 leans on that exist **elsewhere in the repo but not
  on the ranker panel**: a sector/GICS map (`attribution._build_sector_map()`,
  ticker→sector, used for attribution reporting, never joined onto
  `xs_ranker`'s panel) and VIX/VIX-term-structure data (`regime_detector.py`
  consumes a `VIX`/`VIX3M` column on a market-level frame, not on the
  per-name panel `strategy_library` signals read). Every row below that needs
  either is flagged `NEEDS COLUMN`.

---

## Part 1 — Toward 200: 91 additional strategies, distinct in mechanism

Murat's instruction: no trivial threshold variants. Every row below is either
an **interaction** (two signals combined by gating/sequencing, not just
rank-averaging — `combo()` already covers rank-averaging and produced the
existing `mom_flow`/`trend_quality`/`inflection_flow`/`lowmax_mom`/
`residmom_lowidio`/`gp_low_ag` rows), a **regime condition**, a **construction
change** (sector-neutral, one-per-sector), a **timing/sequencing** rule
(leads-vs-chases, before/after a catalyst), or a **genuinely different
data source** (13F, congress, news-count, thesis-card, target dispersion)
from anything already registered. Ids are proposals for
`night_backtest_factory.py`/`strategy_library._rules()`, family names extend
the 11 already on the board. **91 rows**, inside the 90–110 ask; combined with
the 112 already registered that gives **203**, clearing the ≥200 floor with
the panel-reachable ones alone (a further ~20 below need a column that does
not exist yet and should be counted as backlog, per the same rule the first
catalogue used for its 67 `NOT REACHABLE` rows).

### A. Interactions (8) — gated/sequenced, not rank-averaged

| id | family | rule | source / why distinct mechanism | expected survival after cost | fwd-only? |
|---|---|---|---|---|---|
| INT-01 | revision_flow_gated | `mom_252_21`, scored only where `net_raises` (AREV-01 score) is in the top tercile; zero elsewhere (`gated`, not `combo`) | tests whether revisions are a **filter** (removes the momentum names sell-side doesn't believe in) rather than an additive rank leg, which is a different claim than `mom_flow`'s rank-average | plausible — a filter concentrates the book more than an average, should show lower breadth but a cleaner sign pattern than `mom_flow` | no |
| INT-02 | inflection_liquidity | INFL-01 (`rev_qoq` accel × `margin_chg`>0), gated to `mid_plus`/`large` band only | tests whether the fundamentals-inflection edge (already flagged GO at 39bps/mo) survives when the illiquidity contribution (SIZ-01's known mechanism) is removed — directly answers "is INFL-01 secretly SIZ-01" | if it survives at a similar magnitude in `large`, that's the strongest single receipt line this batch can produce | no |
| INT-03 | insider_momentum_gate | `mom_252_21`, scored only among names with a `pit_observations` opportunistic insider buy in the trailing 90d | interaction, not COMB-05's rank-average: asks whether insider buying **selects which momentum names are informed** rather than adding independent information | expect fewer names, higher per-name conviction; the informative test is whether it beats plain MOM-01 on the SAME reduced universe, not on the full one | no |
| INT-04 | raises_no_price_yet | net-raises top decile, gated to `mom_21` (1-month price return) in the bottom half — "the analysts moved, the tape hasn't" | distinct from AREV-04 (revision momentum) and AREV-06 (rank-average with price momentum): this is explicitly the **unpriced-information** cut, the opposite condition from momentum-confirmation | this is the row Part 1's "raises LEAD price" section (D) formalizes further — see D-family, kept here as the base interaction | no |
| INT-05 | quality_momentum_gate | `mom_252_21`, scored only in `gross_margin` top tercile (QUAL-01 as a gate) | different from COMB-02's rank-average: a gate concentrates on Novy-Marx's own "profitable value/momentum survives, unprofitable does not" claim structurally rather than diluting it into an average | strong prior given QUAL-01 is one of the two "expect to survive" picks | no |
| INT-06 | lowvol_momentum | `mom_252_21` top decile, gated to `vol_21` bottom half | tests the Asness-Frazzini-Israel-Moskowitz (MOM-10) claim that momentum's own "crashes" are a high-volatility-state artifact, by construction rather than by ex-post beta-neutralization | a genuine bet AGAINST the board's own bottom-10 (`low_risk` family died outright) — the finding either shows low-vol conditioning rescues momentum's tail or shows the family's low-vol dead-end infects any book it touches | no |
| INT-07 | dispersion_momentum | `mom_252_21` top decile, gated to lowest-tercile target dispersion (once `target_snapshots` has enough history) | "high-conviction momentum": momentum where sell-side actually agrees on the price target, distinct from AREV-10's standalone dispersion row | `[FWD]` until `target_snapshots` (2026-09-24 start) accrues enough dates for a backtest | **yes — dispersion history starts 09-24** |
| INT-08 | insider_sell_killswitch | `mom_252_21` top decile, EXCLUDING any name with an opportunistic insider **sell** in the trailing 60d | a defensive overlay, not a new rank: tests INS-02's "opportunistic sells are the stronger half" finding as a subtraction from an existing book rather than a fresh short leg (Aegis mandates are long-only per the three-licences note) | expect a small, hard-to-see-through-noise improvement; worth the receipt precisely because it is cheap and mechanical | no |

### B. Regime-gated versions of the top families (10) — SPY 200d / VIX terciles

**NEEDS COLUMN for every row in this section**: a market-level regime flag
(SPY's own `px_vs_ma200` sign, and a VIX tercile) is not currently joined onto
the per-name panel `Strategy.signal(p)` reads. `attribution`/`regime_detector`
already source VIX and SPY moving averages elsewhere; the join itself is a
half-day build (broadcast one regime value per `date` across all `symbol`
rows), not a new data pull.

| id | family | rule | source / why distinct mechanism | expected survival after cost | fwd-only? |
|---|---|---|---|---|---|
| REG-01 | momentum_regime | `mom_252_21` top decile, ACTIVE only when SPY close > SPY 200dma | Moskowitz-Ooi-Pedersen (MOM-07) reframed as a per-name overlay instead of an index-timing rule; tests whether momentum's edge is conditional on the trend regime it's usually measured in | expect this to beat unconditional MOM-01 on a risk-adjusted basis even if raw CAGR is similar — fewer, cleaner months | no |
| REG-02 | momentum_bear_control | same signal, ACTIVE only when SPY < 200dma | the deliberate control for REG-01 — Daniel & Moskowitz's momentum-crash literature predicts this is where momentum dies; **expected dead**, and its deadness is the finding that validates REG-01 | expect negative or near-zero; a clean "textbook dead" calibration row like SEAS-02/06 | no |
| REG-03 | quality_high_vix | QUAL-01 (`gross_margin` top decile), ACTIVE only in the top VIX tercile | "flight to quality" — quality's premium is often argued to concentrate in stress regimes; distinct claim from QUAL-01's unconditional version | plausible; quality's already-favorable turnover profile makes this cheap to test even if the regime split halves the sample | no |
| REG-04 | lowvol_high_vix | LV-01 (`vol_21` bottom decile), ACTIVE only in the top VIX tercile | the low-vol family died UNCONDITIONALLY on this board (t −7.4); this asks whether it dies **everywhere** or only in the calm-market months where its defensive property is never called on | if this also dies, it strengthens the board's low-vol finding into "wrong in the regime it's supposed to matter most," which is a stronger and more citable negative than the unconditional one | no |
| REG-05 | revision_flow_bull | `net_raises`, ACTIVE only when SPY > 200dma | tests whether the already-GO'd fundamentals/revision family (§54, 39bps/mo) is itself a beta-in-disguise that only shows up in risk-on regimes | if it survives roughly unconditionally, that's evidence the mechanism is NOT sector-beta timing; if it collapses out of bull regimes, that is the "which part of the sample" question from CLAUDE.md protocol 11 applied one level up | no |
| REG-06 | insider_calm_vix | INS-01-style opportunistic buying, ACTIVE only in the BOTTOM VIX tercile | calm markets should carry a cleaner idiosyncratic-information signal (less macro noise swamping the Form-4 signal) — opposite conditioning from REG-03/04 on purpose, to see which families are regime-loving vs regime-agnostic | speculative; cheap given INS-01 is already a top pick | no |
| REG-07 | reversal_stress_vix | REV-02 (`rev_5` bottom decile), ACTIVE only in the top VIX tercile | short-term reversal's academic home is exactly liquidity-provision after panic-selling (Lehmann/Jegadeesh microstructure story) — testing it ONLY in stress regimes changes the turnover profile from "always trading" to "trading rarely, when the mechanism is live," which changes the cost arithmetic that killed REV-01/02 unconditionally | this is the row most likely to rescue a reversal family the first catalogue already expects dead — worth the receipt specifically because it might flip an "expect dead" | no |
| REG-08 | momentum_calm_vix | `mom_252_21` top decile, ACTIVE only in the BOTTOM VIX tercile | the complementary cut to REG-01/02 along the volatility axis instead of the trend axis — classic momentum literature (Daniel-Moskowitz) locates the crash risk specifically in high-vol/rebound states, not merely bear markets | expect this to show the cleanest Sharpe of the whole regime batch if the crash-risk story is right | no |
| REG-09 | small_bull_only | SIZ-05 (small, liquid-screened) ACTIVE only when SPY > 200dma | small caps are widely reported to be a levered bet on risk appetite; this tests whether SIZ-05's already-designed-to-survive-costs version needs the bull-regime condition to actually clear costs, or does so regardless | plausible partial improvement; cheap given SIZ-05 already exists | no |
| REG-10 | regime_switch_meta | a router: use `mom_252_21` when SPY>200dma, switch to QUAL-01 when SPY<200dma, re-evaluated monthly | **multiplicity-heavy — flag for extra DSR scrutiny**, and directly the thing `docs/ROADMAP...` warns against ("a learned router comes after several independent selectors exist, not before"); register it to have the receipt, do not let it anchor the board | unknown by design; the point is to have ONE meta-router row on file rather than none, not to promote it | no |

### C. Sector-neutral versions (8) — NEEDS COLUMN (sector map join)

Every row needs `attribution._build_sector_map()`'s ticker→sector joined onto
the panel as a `sector` column, then reranks WITHIN each date×sector group
instead of within the whole date's cross-section. This directly answers the
canon line "does the mega-cap sensor generalize, or is the composite just
buying one sector twice."

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| SECN-01 | sector_neutral_momentum | `mom_252_21`, ranked within-sector, top decile per sector | removes the possibility that MOM-01's edge is "own more tech," which is a sector bet wearing a momentum costume | if MOM-01's Sharpe survives sector-neutralization near-intact, that is strong evidence against a pure sector-beta explanation | no |
| SECN-02 | sector_neutral_quality | QUAL-01, ranked within-sector | same logic for the "expect to survive" quality pick — quality is known to concentrate by sector (software vs energy gross margins are not comparable in absolute terms) | quality is exactly the family MOST likely to change materially sector-neutral, since raw `gross_margin` levels are sector-driven | no |
| SECN-03 | sector_neutral_revision | `net_raises`, ranked within-sector | tests whether analyst-revision breadth is itself sector-clustered (a whole sector gets upgraded together on a macro read, e.g. all semis) | plausible partial decay — a genuinely informative bake-off against the unconditional AREV-01/02 rows | no |
| SECN-04 | sector_neutral_lowvol | LV-01, ranked within-sector | tests whether the board's dead low-vol family is dead PARTLY because it concentrates in one or two low-beta sectors (utilities/staples) that themselves underperformed 2016–2026, vs a genuine within-sector defensive failure | if sector-neutral low-vol is LESS dead than LV-01, the family's failure was partly a sector bet, not the low-vol premise itself | no |
| SECN-05 | sector_neutral_insider | INS-01-style opportunistic buying, ranked within-sector | insider buying is known to cluster by sector during sector-wide re-ratings (all the biotech CEOs buying ahead of a conference); within-sector ranking isolates the idiosyncratic signal | speculative, cheap | no |
| SECN-06 | sector_relative_52w_high | distance to the SECTOR's own 52-week high (not the stock's), top decile | genuinely different from MOM-04: anchoring to a sector benchmark rather than the stock's own price history, closer to a relative-strength-vs-peers framing | untested mechanism, moderate prior given MOM-04's own strength | NEEDS COLUMN (sector-level rolling high) |
| SECN-07 | sector_rotation_pick | own the single best-momentum name in each of the top-3 momentum sectors (one pick per sector, `k`=3×names-per-sector) | distinct from MOM-06 (industry momentum) and SECN-01: a portfolio-CONSTRUCTION rule (diversify across leading sectors) rather than a pure signal, testing whether concentration risk (not signal quality) explains part of unconditional momentum's tail | construction-only row; primarily useful for the multiplicity-vs-construction distinction in the receipt | no |
| SECN-08 | sector_cap_one | MOM-01's signal, but construction caps the book at 1 name per sector regardless of rank order below the cap | isolates how much of MOM-01's return is sector concentration by comparing identical signal, different construction, against the unconditional book | same purpose as SECN-07 from the opposite direction (relaxed cap vs hard cap) | no |

### D. "Raises LEAD price, not chase it" (6) — the reviewer's idea

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| LEAD-01 | revision_leads | net-raises top decile AND `mom_21` (trailing 1-month price) in the BOTTOM half — analysts moved, price hasn't yet | the base case of INT-04, formalized as its own family: this is the row that actually tests "does the market catch up to the analyst," the opposite direction from every existing AREV row which either measures the level or combines with confirmed momentum | if this beats AREV-01 unconditional, it is direct evidence analysts have a genuine lead time over price, not merely correlation with existing momentum | no |
| LEAD-02 | revision_chases | net-raises top decile AND `mom_21` in the TOP half — price already ran, then the raise arrives | the deliberate control for LEAD-01: this is the "confirmation"/chase case, expected to show LOWER incremental information (McLean-Pontiff logic: crowd-followed, already-priced signals decay fastest) | expected weaker than LEAD-01 — the bake-off between the two IS the finding, more informative than either number alone | no |
| LEAD-03 | lead_magnitude | rank by (raise-decile score) MINUS (contemporaneous `mom_21` rank) — the raw "gap" between what analysts say and what price has done | a continuous version of LEAD-01/02's binary split, closer to a genuine "surprise relative to price" measure | untested; moderate prior given LEAD-01's expected direction | no |
| LEAD-04 | first_mover_analyst | net-raises top decile restricted to raises from a SINGLE firm acting alone (not yet joined by other firms in the cluster) — uses `firm`/`n_firms` to isolate the first raise in a window | genuinely different from AREV-05's approximation: this identifies the FIRST informed mover using data Aegis already has (`revision_flow.py`'s `n_firms`), rather than a proprietary accuracy weighting | Womack 1996's first-mover literature gives a real prior; worth building since the `firm` field already exists | no |
| LEAD-05 | divergence_tape | net-raises top decile with `rev_1` (yesterday's return) NEGATIVE — analysts say buy while yesterday's tape said sell | a sharper, single-day version of LEAD-01 aimed at the shortest-horizon "does the market know yet" question | speculative, cheap; likely thin sample per day so needs the `k`=50 breadth cell to have enough names | no |
| LEAD-06 | cluster_unconfirmed | breadth-of-raises (AREV-02) top decile AND `mom_21` in the bottom tercile — a whole cluster of analysts moved and price STILL hasn't | the strongest form of "lead": not one analyst but several, with zero price confirmation yet | this is the single highest-conviction row in the LEAD family if the "analysts lead" hypothesis is true at all | no |

### E. Catalyst run-up / exit-before rules (8)

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| CATR-01 | own_into_catalyst | own names with a scheduled catalyst-calendar event within the next 10 sessions, exit 1 session before it | tests the pre-event drift literature (PEAD-06/CAT-04's cousin) as an explicit ENTRY/EXIT timing rule rather than a static conditioning filter | plausible, thinly-evidenced; needs the catalyst calendar's date field, which the LLM-portfolio factory outputs already carry | check catalyst calendar coverage/history depth before registering |
| CATR-02 | buyback_authorization_hold | own names with a newly announced buyback authorization in the catalyst calendar, hold through the announcement | distinct mechanism from INV-02 (net issuance level): this is an EVENT, not a stock, and tests the announcement-drift literature (PEAD-05's Quantpedia number) directly | check for duplication against `first_books/replay/buyback_insider_divergence_v0` before registering — that file already exists and may cover this ground | no |
| CATR-03 | preearnings_runup | own names showing the pre-earnings-drift pattern (positive `mom_21` AND an earnings catalyst within 5 sessions), EXIT the session before the print | practitioner overlay (CAT-04's cousin) turned into an explicit exit-before-event risk rule, distinct from holding through the print | speculative; event-risk avoidance is the point, not necessarily higher raw return | no |
| CATR-04 | postcatalyst_fade | EXIT a held position the session after ANY catalyst-calendar event if the underlying signal score has decayed below its entry percentile | a decay/exit rule layered on any existing book (e.g. applied to MOM-01), not a new selection signal — tests whether catalyst-triggered exits reduce drawdown without giving up much CAGR | construction-only; test against MOM-01 unmodified as the control | no |
| CATR-05 | catalyst_plus_raises | own names with an approaching catalyst AND positive net-raises in the trailing 30d — confirmation that sell-side is positioning ahead of the event too | genuinely different from CAT-05/06 (thesis-card agreement): this combines a structured calendar event with a structured revisions signal, no LLM in the loop | moderate; two independent structured sources | no |
| CATR-06 | catalyst_insider_preposition | own names with an approaching catalyst AND an insider buy in the trailing 30d — informed pre-positioning ahead of a known event | distinct from INS-01 unconditional: this specifically targets insiders who may have non-public knowledge of an upcoming catalyst's likely outcome | speculative, and the single row in this family closest to a genuine information-timing story rather than a drift story | no |
| CATR-07 | exit_before_earnings_overlay | MOM-01's signal, with a mechanical "close the position 1 session before its next scheduled earnings, re-enter after" overlay | a risk-reduction CONSTRUCTION variant of the board's own top rule, not a new signal — tests whether MOM-01's Sharpe improves once earnings-day gap risk is removed | plausible small Sharpe improvement, likely small CAGR cost; the receipt should show both | no |
| CATR-08 | catalyst_density | own names with the MOST distinct catalyst-calendar events clustering in the next 21 sessions ("attention magnets") | a genuinely different mechanism from any single-event row: tests whether catalyst DENSITY itself, independent of catalyst type, predicts an attention-driven move (adjacent to the ATT family but built from structured calendar data, not search/social) | speculative, low prior, cheap | no |

### F. Earnings-proximity conditioning (6)

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| EARN-01 | momentum_far_from_earnings | MOM-01 restricted to names >10 sessions from their next scheduled print | a pure risk-avoidance conditioning of the board's own top row — removes event-risk sessions from the momentum book entirely, distinct from CATR-07's exit-and-reenter overlay (this never enters at all) | expect similar CAGR, lower tail risk (fewer catalyst-driven drawdown sessions) | no |
| EARN-02 | revisions_near_earnings | net-raises restricted to the 10 sessions immediately BEFORE a scheduled print — sell-side is most active and informative right before a release | distinct from AREV-01 unconditional: tests whether the revision signal's information content concentrates near the event it anticipates | plausible improvement in signal-to-noise even with fewer eligible names per day | no |
| EARN-03 | insider_near_earnings | opportunistic insider buying restricted to the 20 sessions before a scheduled print | the single highest-conviction cut of the insider family if insiders sometimes know how the quarter is going before it's reported — Form-4 filings inside a blackout-adjacent window are the ones regulators scrutinize hardest, so a genuine signal here is a strong claim | speculative but high-value if it holds; needs a careful look at insider-trading-window/blackout-period compliance data before over-trusting any positive number | no |
| EARN-04 | inflection_just_after_earnings | INFL-01 restricted to the 10 sessions immediately AFTER a print (freshest possible fundamental read) | distinct from INFL-01 unconditional: tests whether the fundamentals-inflection edge is front-loaded right after the data becomes public, decaying as the quarter ages | plausible, and directly tests the fundamentals family's own decay shape (§64's "skill at h=1, gone by h=5" lesson, applied to fundamentals instead of forecasts) | no |
| EARN-05 | dispersion_near_earnings | target dispersion (AREV-10/G-family) restricted to the window right after a print, when targets get freshly updated | `[FWD]` for the same reason as every dispersion row — no history before 2026-09-24 | yes |
| EARN-06 | insider_avoid_earnings_overlay | INS-01's book with a mechanical exclusion of the earnings-week itself (opposite conditioning from EARN-03, applied as a risk overlay rather than a signal restriction) | construction row, paired deliberately with EARN-03 as the "avoid the event" control | no |

### G. Dispersion-of-targets rules (6) — `[FWD]`, target snapshots start 2026-09-24

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| DISP-01 | dispersion_trend | CHANGE in target dispersion over the trailing available snapshots (narrowing = convergence), top decile | distinct from AREV-10/`forecast_dispersion_v1` (the LEVEL): this is a trend/second-derivative measure, the same "level vs change" distinction the first catalogue already drew for AREV-03 vs AREV-08 | `[FWD]`, and needs MORE snapshot history than the level version before it is even measurable | yes |
| DISP-02 | dispersion_widening_weak_price | dispersion WIDENING (analysts diverging) combined with `mom_21` negative — disagreement rising alongside price weakness, a candidate AVOID/exclusion signal rather than a buy | genuinely different framing from DISP-01: a risk-off combination, not a conviction one | yes |
| DISP-03 | risk_adjusted_upside | median target upside (AREV-08) DIVIDED BY dispersion, top decile — "conviction-adjusted" implied return | distinct from AREV-08 alone: penalizes upside claims that come with wide disagreement | yes |
| DISP-04 | dispersion_momentum_confirm | low dispersion AND `mom_252_21` top decile (INT-07's twin, kept here for the family cross-reference) | see INT-07 | yes |
| DISP-05 | dispersion_by_band | dispersion signal restricted to `mega`/`large` band only — dispersion likely MEANS something different for a 3-analyst small-cap than a 40-analyst mega-cap | tests whether the dispersion signal needs a liquidity-band condition the way BAB (LV-08) did | yes |
| DISP-06 | dispersion_cluster_confirm | low dispersion AND a recent insider buy — two independently-sourced "conviction" signals (sell-side agreement, insider action) | genuinely distinct information sources, good multiplicity-control case like INS-05/COMB-08 | yes |

### H. Insider-cluster × revision confirmation, sequenced (6)

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| SEQ-01 | insider_then_revision_confirm | insider cluster buy (≥3 insiders, INS-03) in month t, followed by net analyst raises in month t+1 | SEQUENCED, not simultaneous like INS-05: tests "insiders lead analysts" as a timed hypothesis rather than a same-month rank-average | genuinely novel test of a specific causal-ordering claim | no |
| SEQ-02 | insider_unconfirmed | insider cluster buy with NO analyst raise yet in the following month — the pure "insiders know first, market hasn't caught up" leg | the leading-edge complement to SEQ-01; if this decays FASTER once revisions arrive (SEQ-01), that is direct evidence for the sequencing story | no |
| SEQ-03 | insider_then_downgrade | insider selling (INS-02) followed by an analyst cut within 30 days — a bearish confirmation sequence, used as an EXCLUSION filter (long-only mandate) | distinct from AREV-07 (downgrade-avoidance alone): adds the insider-selling precondition | no |
| SEQ-04 | inst13f_insider_confirm | 13F quarterly net institutional accumulation (breadth of funds adding, not just aggregate $) INTERSECTED with insider buying in the same quarter | two independently-sourced OWNERSHIP signals (institutional 13F filings, corporate Form-4) — genuinely different data provenance from any revision-based row; 13F history goes back to 1996, no `[FWD]` tag needed | no |
| SEQ-05 | congress_insider_confirm | congressional trading net buying (per `pit_observations`, cross-check against the existing TRIAL-CONGRESS-IC before treating as novel) intersected with insider buying | two distinct "informed party" sources; register only after confirming this isn't already covered by the 2026-09-20 congress trial | check TRIAL-CONGRESS-IC for overlap first |
| SEQ-06 | inst13f_breadth_alone | 13F breadth-of-funds-adding alone (not intersected with anything), top decile | a standalone institutional-ownership-change signal, distinct from any insider/analyst row — the base case SEQ-04 builds on, worth having on its own line for the bake-off | no |

### I. Industry-relative momentum via the sector ETF map (6) — NEEDS COLUMN

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| SECI-01 | resid_to_sector | stock `mom_252_21` MINUS its sector ETF's own trailing 12-1 momentum, top decile | genuinely different residualization from `resid_mom_63` (which is residual to `beta_63`/the MARKET, not the stock's own sector) — this is Moskowitz-Grinblatt's actual mechanism (MOM-06), finally reachable now that a sector map exists elsewhere in the repo | plausible; the whole reason MOM-06 was flagged NOT REACHABLE before was the missing sector field | needs sector map join |
| SECI-02 | sector_etf_gate | trade only within the top-3 momentum sector ETFs' constituent names, ranked by stock-level `mom_252_21` inside that gate | a two-stage construction (pick the sector, then pick the stock), distinct from SECI-01's residual and from SECN-07's diversified one-per-sector pick | needs sector map join |
| SECI-03 | sector_pick_diversified | one best-momentum name per sector among the top-3 momentum sectors only (SECN-07 restricted further to the leading sectors, not all sectors) | narrower version of SECN-07, testing whether restricting to leading sectors changes the diversification-vs-concentration tradeoff | needs sector map join |
| SECI-04 | sector_laggard_reversion | buy the sector ETF that most underperformed the leading sector last month, rank its constituent stocks by momentum — a sector-level mean-reversion feeding a stock-level pick | genuinely distinct mechanism: sector ROTATION timing (reversion at the sector level) combined with stock selection (continuation at the name level) | needs sector map join |
| SECI-05 | sector_relative_revisions | net-raises ranked WITHIN sector rather than across the whole universe (SECN-03's twin, kept here for the family cross-reference) | see SECN-03 | needs sector map join |
| SECI-06 | sector_concentration_test | MOM-01's exact signal, construction capped at 1 name per sector (SECN-08's twin, kept here for cross-reference) | see SECN-08 | needs sector map join |

### J. FOMO / reversal family (7) — from Chunk C

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| FOMO-01 | chase_then_fade | `gap_share` top decile AND `trade_surge`/`turnover_surge` top decile in the SAME session ("FOMO entry"), SHORT/avoid the next 1–5 sessions | distinct from REV-03 (gap-driven reversal alone): requires the VOLUME surge co-occurring with the gap, isolating retail-chase behavior specifically, not just any gap | REV-01/02's cost problem applies here even harder (very short hold); expect dead net of cost unless the gross effect is large | no |
| FOMO-02 | attention_spike_reversion | `trade_surge` top decile alone (no return-direction condition), next-session mean reversion | distinct from every REV row: gated on ATTENTION (volume), not on price direction — a name can spike on volume without a big price move yet, testing pure attention-driven overreaction | speculative, high turnover, likely a cost casualty like REV-01/02 | no |
| FOMO-03 | gapup_volume_fade | `gap_share` top decile (up-gaps) AND high relative volume, SHORT the next session's open-to-close ("retail chase, professional fade") | the base retail-chase pattern from the technical-analysis literature, made testable with existing panel columns instead of tick-level order flow | expect dead net of cost, same family as REV-01 | no |
| FOMO-04 | parabolic_exhaustion | `up_days_21` at its maximum (long up-day streak) combined with DECELERATING `turnover_surge` (volume fading even as price keeps rising) — an exhaustion signal | distinct from MOM-11 (frog-in-the-pan, which REWARDS gradualism): this specifically targets the OPPOSITE state, a streak losing its volume support, as a reversal candidate | speculative, low prior, worth the receipt as a contrast to MOM-11 | no |
| FOMO-05 | fomo_with_catalyst | an attention spike (FOMO-02's condition) that COINCIDES with a genuine catalyst-calendar event, vs one with no identifiable catalyst | tests whether attention spikes with a real fundamental trigger persist while catalyst-free spikes revert — a genuinely different claim from either alone | speculative; the bake-off between the two conditions is the finding | check catalyst calendar coverage |
| FOMO-06 | marginal_winner_fade | within the momentum top decile, the BOTTOM half of that decile (marginal qualifiers) vs the top half (strongest qualifiers) — tests whether the weakest momentum names in the winning bucket are more FOMO-driven and decay faster | a within-decile bake-off, not a new signal on the full universe — cheap, and directly informative about whether MOM-01's edge is uniform across its own decile | no |
| FOMO-07 | recovery_anchoring | names within 5% of their 52-week high AFTER having been down >30% from that same high within the trailing year — anchoring-driven selling pressure "getting back to even" (disposition effect) | distinct mechanism from MOM-04 (nearness to high, unconditional): requires the PRIOR drawdown, testing Grinblatt-Han-style disposition-effect resistance at the old high | plausible, evidenced disposition-effect literature; a genuinely different construction from any MOM row | no |

### K. Lottery-preference family (6) — from Chunk C

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| LOT-01 | max_effect_short | Kumar (2009)-style "MAX effect": highest single-day return in the trailing month (approximate via extreme `rev_1` combined with elevated `vol_21`), BOTTOM decile long / AVOID short | the academically cleanest lottery-preference row: high-MAX stocks are well-documented to UNDERPERFORM going forward — this is a "buy the opposite of the lottery ticket" row, not a lottery-chasing one | plausible survival as an avoidance/exclusion signal even if not tradable as a standalone short | no |
| LOT-02 | lottery_bucket_exclude | `skew_63` positive-and-high AND `vol_21` high AND `dollar_vol_log` low, jointly — an EXCLUSION screen (never a buy list) applied to other books, e.g. MOM-01 | genuinely different use of the same underlying literature (Kumar's lottery-demand definition) as a portfolio-construction FILTER rather than a signal, testing whether removing the lottery bucket improves MOM-01's tail without hurting its mean | construction-only; test against MOM-01 unmodified as control | no |
| LOT-03 | post_spike_reversion | the SESSION immediately after a `trade_surge`+`skew_63`-high joint spike, short/avoid — the disposition/anchoring unwind rather than the spike day itself | distinct from FOMO-01/03 by TIMING (day after, not the spike day itself) and by requiring the skew condition, not just volume+gap | expect dead net of cost (single-session hold); worth registering as the cheapest possible test of the mechanism | no |
| LOT-04 | skew_chase_crowding | `trade_surge` top decile AND `skew_63` top decile jointly — retail crowding into positively-skewed, already-hyped names | distinct from LV-06 (level of skew alone, no surge condition): the SURGE+skew interaction targets active crowding, not passive skew exposure | speculative, low prior | no |
| LOT-05 | low_priced_lottery_screen | `dollar_vol_log` bottom tercile AND `vol_21` top tercile, jointly, as an exclusion-only screen (a "penny-stock-like" bucket, distinct from SIZ-02's size-alone cut) | a genuinely distinct 2-D screen from any single-feature SIZ row, aimed at isolating the specific lottery-demand bucket rather than small caps broadly | construction-only | no |
| LOT-06 | idio_vol_lottery_overlay | MOM-01 with the LOT-02 exclusion screen ADDED to the existing REG/INT overlays — tests whether stacking a lottery-exclusion on top of a regime-gated momentum book (REG-01) compounds or cancels the improvement | explicitly a "does stacking help" multiplicity-scrutiny row, flagged for extra DSR care given three conditions compound here | no |

### L. Remaining distinct mechanisms (14) — rounding out the 91

| id | family | rule | why distinct mechanism | expected survival | fwd-only? |
|---|---|---|---|---|---|
| MISC-01 | inst13f_multi_fund_breadth | number of DISTINCT 13F filers adding a name (not aggregate dollar accumulation), top decile | distinct from SEQ-06 by counting FUNDS not dollars — a breadth measure analogous to AREV-02's analyst-breadth logic applied to institutional ownership | no |
| MISC-02 | congress_sector_neutral | congressional net buying, ranked within-sector (cross-check TRIAL-CONGRESS-IC for overlap first) | genuinely new construction (sector-neutral) on an existing-but-thin data source | needs sector map join; check TRIAL-CONGRESS-IC first |
| MISC-03 | news_count_acceleration | z-scored acceleration in daily `first_seen_utc` article counts per name, top decile | an Aegis-OWN-corpus attention signal, distinct from ATT-01/04 (third-party Google Trends/social, `[FWD]` for Aegis) — this one has SOME history (2025–2026) so it is backtestable, just on a much shorter window than the full panel | thin-sample, not full `[FWD]` — flag "short history (~20mo), not full-panel testable" |
| MISC-04 | news_thesis_agree | news-count acceleration (MISC-03) AND a forward thesis-card BUY verdict agreeing, same name/week | two Aegis-internal sources, one backtestable-thin (news), one strictly forward (thesis card) — the combination is necessarily forward-only even though one leg has partial history | yes (thesis-card leg forces it) |
| MISC-05 | silence_before_catalyst | names with a catalyst due within 10 sessions and ZERO news-corpus mentions in the trailing 10 sessions — "the market hasn't started paying attention yet" | a genuinely different framing from MISC-03 (looks for absence of coverage, not presence), directly testing an "information not yet priced" hypothesis via silence rather than activity | speculative, low prior, cheap once the news corpus is joined | check catalyst calendar + news corpus join |
| MISC-06 | analyst_identity_accuracy | net-raises restricted to firms in the top quartile of the FIRM'S OWN historical hit rate (computed from `firm`+realized returns already in `revision_flow`/`expected_return`), current-quarter raises only | genuinely different from AREV-05's crude count/breadth approximation of StarMine: this is an ACTUAL identity-weighted accuracy measure, buildable because `firm`-level history already exists in the repo (`expected_return.py`'s per-ticker firm groupby) | this is the row most likely to beat AREV-01 on a like-for-like basis if analyst skill is persistent (Jegadeesh-Kim's own finding) — worth prioritizing over AREV-05 | no |
| MISC-07 | first_mover_accurate | firms that were BOTH first (LEAD-04) AND historically accurate (MISC-06), current call only | the intersection of two genuinely distinct analyst-level claims (timing, accuracy) — the single most information-dense row in the whole revisions family if both hold independently | no |
| MISC-08 | cascade_entry_timing | rank by DAYS-SINCE-FIRST-RAISE within an active revision cluster — entering early in a cascade vs late | distinct from AREV-04 (revision momentum, a level-of-change measure): this is explicitly a TIMING-WITHIN-CASCADE measure, testing whether early entrants to a revision cascade capture more of the eventual drift than late ones | no |
| MISC-09 | promise_vs_delivery | guidance-implied growth from N quarters ago (if the catalyst calendar distinguishes guidance events) vs REALIZED `rev_qoq` now — delivery-beats-promise top decile | Chunk C's "promise-vs-delivery" concept made concrete: a genuinely new mechanism (management credibility, not price or analyst behavior) | check catalyst calendar guidance-event coverage first |
| MISC-10 | verdict_flip_momentum | thesis-card verdict CHANGED to BUY this week vs HOLD/SELL last week, same name — "qualitative view momentum" | forward-only by construction (LLM-generated verdicts); distinct from CAT-05 (static agreement) by requiring a CHANGE, not a level | yes |
| MISC-11 | capacity_pricing_power | `gross_margin` expansion AND `rev_qoq` acceleration AND LOW `dollar_vol_log`, jointly — pricing power showing up in a name nobody's watching yet | a genuine triple interaction distinct from INFL-04 (which pairs fundamentals with analyst attention, not liquidity/attention scarcity) — tests Chunk C's "pricing power"/"capacity constraint" concepts directly against an inattention proxy | no |
| MISC-12 | pmf_inflection_discrete | `margin_chg` FLIPPING from negative to positive for the first time in ≥2 quarters (a discrete regime-change flag), vs INFL-02's continuous second derivative | a discrete-event framing of the same underlying data, testing whether Chunk C's "PMF inflection" concept is better captured as a step-change than a continuous acceleration | no |
| MISC-13 | turnaround_pivot | `rev_qoq` sign flip (negative to positive) after ≥2 consecutive negative quarters — a "pivot" distinct from an ongoing-acceleration framing (MISC-12 is margin, this is revenue) | Chunk C's "pivots" concept, kept as its own row since revenue and margin turnarounds are not guaranteed to co-occur | no |
| MISC-14 | china_capacity_entry_proxy | sector-relative margin compression (`margin_chg` bottom decile WITHIN a materials/industrials/tech-hardware sector cut) as a proxy for new-capacity-driven price competition | Chunk C's "China capacity entry" concept approximated with existing columns — genuinely speculative and the row most likely to need a real data build (an actual capacity/import-volume series) before it clears even PRODUCT_EXPERIMENT confidence | needs sector map join; flag LOW confidence, proxy-only |

**Count: 8+10+8+6+8+6+6+6+6+7+6+14 = 91.** Combined with the 112 already on
`LEADERBOARD.md`, that is **203 rows**, of which roughly 20 (every `NEEDS
COLUMN` row in sections B/C/I plus a handful in L) cannot run until the
sector map and market-regime series are joined onto the ranker panel — count
only the ~183 panel-reachable rows toward the ≥200 floor tonight, and carry
the rest as a named backlog exactly as the first catalogue's 67
`NOT REACHABLE` rows were carried, never silently dropped.

---

## Part 2 — The second-engine cross-check: LEAN investigated first, vectorbt recommended for the build

### 2.1 QuantConnect LEAN CLI — what was verified this session [V]

- **Docker is required** to run LEAN locally via the CLI (`lean backtest`);
  the first run pulls a multi-gigabyte engine image (a QuantConnect forum
  thread from 2024 reports "more than 9 GB") [V,
  https://www.quantconnect.com/forum/discussion/18129/lean-cli-local-development-what-data-to-subscribe/].
  Docker Desktop on Windows (WSL2 backend) is the standard path; nothing found
  this session suggests Windows is unsupported, only that Docker itself is the
  dependency, same as any other Docker workload on this machine.
- **Custom local data is a first-class, documented path, and does NOT require
  a paid QuantConnect data subscription** — QuantConnect's own "Custom Data"
  page for the LEAN CLI gives the exact recipe: subclass `PythonData`
  (Python) or `BaseData` (C#), override `get_source`/`GetSource` to point at
  `os.path.join(Globals.data_folder, "your_file.csv")` with
  `SubscriptionTransportMedium.LOCAL_FILE` instead of a remote URL, and
  override `reader`/`Reader` to parse each line [V,
  https://www.quantconnect.com/docs/v2/lean-cli/datasets/custom-data]. This is
  exactly the "feed our own parquet" path the brief asked about, confirmed
  directly from QuantConnect's docs, not inferred.
- **The "paid tier" wall is specifically the built-in Dataset Market
  downloader** (`lean data download`), which needs an organization on a paid
  tier and/or QCC credits to pull QuantConnect's own curated datasets (equities,
  security master, etc.) [V,
  https://www.quantconnect.com/docs/v2/lean-cli/datasets/quantconnect/key-concepts].
  That wall does **not** block `lean init`/`lean backtest` against your own
  local files via the custom-data path above — a 2024 QuantConnect forum
  answer says the same thing explicitly: "Local Development without Data
  Subscription: While a data subscription is required for full access to
  historical data, you can still run backtesting scripts using sample data or
  custom data sources... implement custom data types in your algorithm to
  simulate data feeds" [V,
  https://www.quantconnect.com/forum/discussion/18129/lean-cli-local-development-what-data-to-subscribe/].
- **Engineering cost of feeding OUR panel through this path**: one
  `PythonData` subclass (reusable across all symbols via `config.Symbol` in
  `get_source`, not one class per ticker), one CSV-per-symbol export job from
  `prices_2025_26/bars.parquet` (or the wider panel), one algorithm.py that
  does the monthly top-k selection and applies a per-band cost model via
  LEAN's fee/slippage model override hooks. This is a genuinely different
  execution runtime (a .NET/C# engine running inside Docker, event-driven,
  bar-by-bar) from Aegis's own vectorized pandas pipeline — which is exactly
  the property "independent replication, not replacement" is asking for: a
  bug in `xs_ranker`'s or `strategy_library`'s pandas/numpy assumptions would
  not be reproduced by a differently-implemented engine in a different
  language.
- **Estimated cost**: Docker install/pull (30–60 min, one-time, $0), the
  `PythonData` class + CSV export job (1–2 hrs), the algorithm implementing
  monthly top-k + cost model (3–4 hrs), the parquet→per-symbol-CSV export and
  validation (2–3 hrs), debug/run (2–4 hrs). **~10–14 engineering hours,
  effectively $0 licensing cost** for a LOCAL, non-Dataset-Market backtest —
  the "paid tier" requirement genuinely does not apply to this use case.

### 2.2 `vectorbt` (community/open-source edition) [V]

- **License**: Apache 2.0 with the Commons Clause — "everyone (individuals and
  organizations) may use it for free... you may not sell products or services
  that are primarily this software" [V, https://vectorbt.dev/terms/license/,
  https://github.com/polakowo/vectorbt]. Aegis using it internally for
  research/backtesting is squarely inside the free-use grant; nothing here is
  being resold as vectorbt-the-product.
- **`vectorbtpro` is a separate, actively-developed, paid/membership product**
  (private repo, crowdfunded monthly membership, "Private Use / Non-Commercial
  Use" license terms) [V, https://vectorbt.pro/terms/software-license/,
  https://vectorbt.dev/getting-started/upgrade/] — not needed here; the free
  community edition already does everything a monthly top-k rank-and-hold
  backtest needs.
- The open-source repo is still active by GitHub's own numbers at fetch time
  (8,937 stars, 138 open issues, actively watched) [V,
  https://github.com/polakowo/vectorbt] — not abandoned.
- **Offline feasibility with our parquet**: trivial — it is a NumPy/Numba
  vectorization layer over pandas DataFrames the caller supplies directly; no
  bundled data, no ingestion step, no network call. The existing research note
  already benchmarked it in-repo at **0.7s for a 5yr/500-name run** vs
  zipline-reloaded's **2.9s** for the same test [V, cited already in
  `research_strategy_library.md` §2 from autotradelab/pickuma framework
  comparisons].
- **Faithfulness to "top-k by rank at month-end, held 21d, net of band costs"**:
  high. `vectorbt`'s `Portfolio.from_orders`/`from_signals` accept an explicit
  per-date target-weight or order-size schedule, which is exactly what a
  monthly top-k rank produces; per-band transaction costs map directly onto
  its `fees`/`slippage` arguments (which can be arrays, matching our
  band-by-symbol convention).
- **Estimated cost**: pip install (minutes, $0), adapter (build the same
  monthly top-k weight schedule `run_strategy` already produces, feed it to
  `vectorbt.Portfolio.from_orders` with the band-cost array) — **~4–6
  engineering hours**, because it reuses the SAME Python/pandas panel Aegis
  already has in memory; no export/ingestion step at all.

### 2.3 `zipline-reloaded` [V]

- Actively maintained by Stefan Jansen for the *Machine Learning for Algorithmic
  Trading* book community; CI badges (tests, PyPI build, codecov) are present
  and green-looking on the current README, Apache-2.0 licensed [V,
  https://github.com/stefan-jansen/zipline-reloaded,
  https://raw.githubusercontent.com/stefan-jansen/zipline-reloaded/main/README.md].
- **Custom local data is possible without any paid subscription**: the
  `csvdir_equities` bundle reads a directory of CSVs directly
  (`register('custom1', csvdir_equities(['daily'], '/path/to/csvs'), ...)` in
  `~/.zipline/extension.py`, then `zipline ingest -b custom1`) [V,
  https://github.com/stefan-jansen/zipline-reloaded/issues/162]. Its
  Pipeline API (`DataSet`, `Column`, `DataFrameLoader`) is the reference
  architecture that `alphalens-reloaded` and much of the factor-research
  Python ecosystem still cites.
- **Real friction found this session, not merely theoretical**: bundle
  registration must live in `extension.py`, not a notebook cell — a Jupyter
  cell defining and registering a bundle silently fails with "no bundle
  registered" until the code is moved into the extension file, per multiple
  open/closed GitHub issues on exactly this point [V,
  https://github.com/stefan-jansen/zipline-reloaded/issues/162,
  https://github.com/stefan-jansen/zipline-reloaded/issues/188]; a separate
  issue shows a custom-bundle + Pipeline combination silently producing all-NaN
  pipeline columns that then crash downstream `sklearn` calls [V,
  https://github.com/stefan-jansen/zipline-reloaded/issues/268]. None of this
  is disqualifying, but it is real engineering friction beyond what LEAN's
  documented local-file `PythonData` recipe or vectorbt's plain-DataFrame
  input require.
- Already benchmarked in-repo as the **slowest of the three general
  engines** for our kind of workload (2.9s vs vectorbt's 0.7s for the same
  test) — a real cost for a nightly, many-cell factory even though it is not
  the replication target here (only the top 10 need to run through the
  second engine, not 200+ rows).
- **Estimated cost**: bundle registration + CSV export (2–3 hrs, complicated
  by the `extension.py`-only registration gotcha above), Pipeline/DataSet
  definitions for the top-10 rules (2–3 hrs), algorithm + cost model (2 hrs).
  **~6–8 engineering hours**, plus a real chance of losing an hour to the
  bundle-registration/NaN-pipeline sharp edges the GitHub issues document.

### 2.4 Recommendation: two-phase — vectorbt now, LEAN as the true independent check

Pick vectorbt for an immediate, cheap first cross-check, and LEAN for the
genuinely independent second opinion, rather than picking only one:

1. **Phase 1 (now, ~4–6 hrs, $0): vectorbt.** Fastest to build because it
   needs no export step and no new runtime — it catches gross implementation
   bugs in `run_strategy`'s cost/turnover arithmetic almost immediately. It is
   the weaker form of "independence" (same Python/pandas/NumPy stack as
   `xs_ranker` itself — a shared pandas semantics bug would fool both), which
   is exactly why it should not be the ONLY check.
2. **Phase 2 (this week, ~10–14 hrs, $0 licensing): LEAN CLI via Docker.**
   Higher setup cost but the only one of the three that is architecturally
   independent — a different language runtime (.NET/C# inside Docker),
   different execution model (event-driven bar-by-bar vs vectorized), and no
   dependency on Aegis's own pandas code at all. This is what "independent
   replication, not replacement" should mean in practice, and the "paid tier"
   wall Murat may have expected to block this does **not** apply to a
   local-file custom-data backtest per QuantConnect's own docs [V, above] — it
   only blocks pulling QuantConnect's OWN datasets, which this design never
   needs.
3. **`zipline-reloaded`: skip for now.** It offers a similar (event-driven,
   pure-Python-this-time) independence profile to LEAN at a nominally lower
   engineering-hour estimate, but (a) it is already benchmarked in-repo as the
   slowest of the three, (b) this session found concrete, documented
   footguns in exactly the custom-bundle path this task needs (extension.py
   registration, silent all-NaN pipeline columns), and (c) it does not add
   independence beyond what LEAN already provides once LEAN is built — it
   shares Python/pandas idioms with Aegis's own stack in a way LEAN's C#
   runtime does not. Revisit only if the LEAN Docker build turns out to be
   infeasible on this machine.

### 2.5 The exact adapter design

**Input** — `backend/data/optimus/strategy_library/top10_for_replication_<date>.json`,
written by `strategy_library.py`/`night_backtest_factory.py` once the top-10
by DSR are known:

```json
{
  "generated_utc": "...",
  "source": "backend/services/strategy_library.py + LEADERBOARD.md <date>",
  "cost_model": {
    "bands_bps_round_trip": {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0},
    "convention": "half the band round trip charged per side, at each rebalance; drift between rebalances untraded and uncharged",
    "band_boundary_var": "median_dollar_vol (trailing)"
  },
  "rows": [
    {
      "id": "mom_12_1_q",
      "family": "momentum",
      "rule_one_line": "12-1 momentum (mom_252_21), top 20, quarterly rebalance",
      "universe_rule": "all | eligible & median_dollar_vol>=X",
      "k": 20,
      "hold_months": 3,
      "rebalance_dates": ["2016-XX-XX", "..."],
      "held_symbols_by_date": {"2016-XX-XX": ["AAA", "BBB", "..."]},
      "monthly_return_series": [
        {"date": "2016-XX-XX", "gross": 0.0, "cost": 0.0, "net": 0.0,
         "n_held": 20, "n_delisted": 0, "rebalanced": true}
      ],
      "fingerprint": "<Strategy.fingerprint()>"
    }
  ]
}
```

This is `run_strategy`'s own output frame plus the held-symbols-by-date
lookup, serialized — no new schema, just a snapshot of what already exists in
memory for the top 10.

**Output** — the engine (vectorbt Phase 1, LEAN Phase 2) writes
`.../vectorbt_replication_<date>.json` / `.../lean_replication_<date>.json`
with the SAME `monthly_return_series` shape recomputed independently from the
SAME `held_symbols_by_date` and cost model (never re-deriving the selection —
the point is to test EXECUTION/accounting agreement, not re-run the ranker),
plus a per-row comparison block:

```json
{"id": "mom_12_1_q",
 "n_months_compared": 115,
 "corr_net_monthly": 0.994,
 "mean_abs_diff_net_monthly": 0.0009,
 "max_abs_diff_net_monthly": 0.0041,
 "max_abs_diff_date": "2020-XX-XX",
 "verdict": "AGREE"}
```

**Tolerance**: `AGREE` requires `corr_net_monthly >= 0.98` AND
`mean_abs_diff_net_monthly <= 0.0015` (15 bps/month) across the comparable
window; anything looser is `DISAGREEMENT`, printed, never averaged away.

**What a disagreement means, and what to print** — classify every
`DISAGREEMENT` into exactly one of five buckets before touching either
engine's code, the same discipline as item E's `REGIME_SHIFT/CROWDING/...`
taxonomy:

| bucket | what it looks like | what to print |
|---|---|---|
| `REBALANCE_TIMING` | diffs cluster right at rebalance dates only | the exact entry convention each engine used (month-end close vs "next session's open," which `run_strategy`'s own docstring already declares) |
| `COST_MODEL_MISMATCH` | diffs scale with turnover | each engine's realized round-trip bps per name that month, side by side |
| `UNIVERSE_MISMATCH` | one engine holds a symbol the other doesn't on a given date | the exact `held_symbols_by_date` set difference for that date |
| `DATA_MISALIGNMENT` | diffs appear on delisting-heavy months | each engine's fill convention for a delisted name that period |
| `IMPLEMENTATION_BUG` | none of the above explain it | which engine, which line, reproduced with a 2-name/2-date minimal case before either number is trusted |

A disagreement is a finding, investigated exactly like a forward-paper
failure in item E — never silently patched by averaging the two engines'
numbers together.

---

## Part 3 — What the leaderboard must print for MAXIMISE SEALED NET RETURN

### 3.1 The dev/sealed split does not exist as a first-class field yet — and the columns that WOULD build it already exist

`strategy_library.evaluate()` already computes, per cell: `by_year` (a dict
keyed by year string, each with `net`/`spy`/`excess`/`n_months`),
`by_year_signs` (the exact string printed on `LEADERBOARD.md`),
`leave_one_year_out_mean_active`/`loo_worst_mean_active`/
`loo_worst_dropped_year`, `hindsight_since_2020` (cum/CAGR/max-DD for net vs
SPY from a `since` date), and `quotable_since_registration` (months strictly
after the rule's `first_registered_utc` — the only truly non-hindsight
number). **None of these currently draws the line at 2023-12-31/2024-01-01**
specifically — `since` defaults to `"2020-01-01"`, which BLENDS four dev
years (2020-2023) with the sealed years (2024-2026) into one CAGR. That
blending is precisely the failure mode Murat is naming: a single "CAGR since
2020" column cannot show a strategy that was beautiful in 2020-2023 and dead
in 2024-2026, because the four good years dominate the average.

**The fix is one new field, reusing the exact machinery already in the
function** — add to `evaluate()`:

```python
DEV_END = _pd.Timestamp("2023-12-31")
dev = m[m.index <= DEV_END]
sealed = m[m.index > DEV_END]
sp_dev = sp.reindex(dev.index).dropna()
sp_sealed = sp.reindex(sealed.index).dropna()
out["dev_sealed_split"] = {
    "dev_end": "2023-12-31",
    "dev": {"n_months": int(len(dev)), "cum_net": ..., "cagr_net": _cagr(dev["net"]),
            "cagr_spy": _cagr(sp_dev), "max_dd_net": _max_dd(dev["net"])},
    "sealed": {"n_months": int(len(sealed)), "cum_net": ..., "cagr_net": _cagr(sealed["net"]),
               "cagr_spy": _cagr(sp_sealed), "max_dd_net": _max_dd(sealed["net"]),
               "n_blocks_honesty": "sealed n_months monthly blocks; read loo_worst_mean_active "
                                   "and dsr computed at THIS n before trusting the sealed CAGR alone"}}
# a THIRD, even-tighter cut: trailing ~126 sessions (~6 calendar months)
recent = m[m.index >= (m.index.max() - _pd.DateOffset(months=6))]
out["recent_126_sessions"] = {"n_months": int(len(recent)),
                              "cum_net": ..., "cagr_net": _cagr(recent["net"]),
                              "cagr_spy": _cagr(sp.reindex(recent.index).dropna())}
```

This is additive — every existing field stays, `LEADERBOARD.md`'s render
step gains three new columns (`dev CAGR`, `sealed CAGR`, `recent-126 return`)
placed, per the file's own house rule ("read DSR before Sharpe"), **before**
the existing "CAGR since 2020" column, not after — a beautiful dev number
sitting next to a dead sealed number should be the first thing the eye hits,
not something the reader has to compute by subtracting two blended figures.

### 3.2 The sample-size honesty the sealed number needs, worked through with real numbers on the board tonight

2024-01-01 through 2026-09-26 is **~33 calendar months** — the builder should
print the ACTUAL count from `evaluate()['dev_sealed_split']['sealed']
['n_months']` once this ships, not a number asserted here without running the
real panel. If the effective sealed sample is closer to the brief's own
**~21 monthly blocks**, that gap between 33 calendar months and ~21 usable
blocks is itself worth printing and explaining (a likely cause: some rules'
inputs — the fundamentals panel's 460-day-NaN cutoff, the revisions panel's
survivor-selected coverage, or a rule's own `hold_months` — thin out how many
of those 33 months actually produced a rebalance with ≥`k` selectable names;
`run_strategy`'s own loop already skips a month when `len(cand) < k`). Either
way, **the sealed count is smaller than the dev count by construction** (dev
is 2016 or 2017 through 2023, roughly 84-96 months; sealed is at most ~33),
and every DSR/`t_active_horizon_blocks` computed on the sealed slice alone
must use `n` = the sealed block count, not the full-history `n`, for exactly
the reason CLAUDE.md item 11 already fixed once for the horizon sweep: **the
`n` behind a statistic must be re-derived from the SLICE being read, not
inherited from the full-panel calculation.** A DSR computed on ~21-33 sealed
blocks will be forgiving (few blocks → the analytic noise ceiling is itself
higher, per §3.3's arithmetic below) — print it, but print the block count
right next to it so nobody reads "DSR 0.6 sealed" as equivalent evidentiary
weight to "DSR 0.6 full-history."

Illustration from real numbers already on `LEADERBOARD.md` (not invented):
`mom_12_1_q`'s printed `by_year_signs` is `-+++-+++++`, ten characters — one
per year in its full monthly history — with `by-year vs SPY` reading
predominantly positive except two down years, and its own `LOO-worst (mo,
active)` row already shows dropping 2020 changes the worst-year read
(`+1.52% (drop 2020)`). That LOO-worst figure is itself proof the board
already knows single-year composition matters — the dev/sealed split above
is the same discipline applied to a fixed, forward-meaningful boundary (when
capital could actually have been committed under this exact frozen rule)
rather than to whichever year the leave-one-out happens to flag as worst.
**The builder should pull the ACTUAL `by_year` dict for `mom_12_1_q` (and the
other 9 top-DSR rows) and report the real 2024/2025/2026-partial figures next
to the real pre-2024 figures** — this document proposes the mechanism and the
placement, not a fabricated sealed number, because asserting one without
running `evaluate()` on the real panel would be exactly the kind of
unverified headline number CLAUDE.md's rules exist to prevent ("a headline
number belongs in a receipt").

### 3.3 DSR at ~600 cells (≈200 rules × 3 k-breadths) barely moves the bar, and that is the point to print

Reusing the exact extreme-value approximation `research_strategy_library.md`
§3 already used and that reproduces `LEADERBOARD.md`'s own printed 0.275
figure at `n=336` (`sqrt(1/(T-1)) · Φ⁻¹(1-1/N)` with `T≈115` monthly blocks,
`0.0937 · 2.75 ≈ 0.258`, in the same ballpark as the board's printed 0.275
once the fuller Euler-Mascheroni correction terms are included):

| n (cells) | Φ⁻¹(1-1/n) | noise ceiling (monthly, T=115) | reading |
|---|---|---|---|
| 336 (tonight, 112 rules × 3 k) | ≈2.75 | ≈0.26–0.275 (board's own printed figure) | today's bar |
| 600 (≈200 rules × 3 k) | ≈2.94 | ≈0.275–0.29 | barely higher |

**The noise ceiling moves by only ~5–10% going from 336 to 600 cells** — the
extreme-value quantile grows with `log(n)`, not `n`, so tripling the trial
count from tonight's 112 rules to ~200 does NOT make the bar meaningfully
harder to clear. What DOES change is the **false-discovery arithmetic at any
fixed bar**: with ~600 genuinely-looked-at cells instead of 336, the expected
NUMBER of noise draws that clear a fixed threshold (say DSR ≥ 0.5) roughly
scales with `n`, even though the single best-of-n ceiling barely moves. Print
both: the ceiling (barely changes) and the expected-false-positive-count at
whatever threshold the board reports as "clears" (scales with n) — reporting
only the ceiling would understate how much more skeptically a 600-cell board
must be read than a 336-cell one, and reporting only the count without the
ceiling would let two-versus-three-hundred additional close-miss cells be
mistaken for meaningfully-more-noise rather than the same noise measured more
times.

**And, restated from the existing `LEADERBOARD.md` note**: the effective
family count also grows with Part 1's ~91 new rows — 11 families become
roughly 25-30 once Part 1's `revision_flow`/`regime`/`sector_neutral`/`lead`/
`catalyst`/`earnings_proximity`/`dispersion`/`sequenced`/`sector_industry`/
`fomo`/`lottery`/`misc` groups are added. `deflate()` already supports
`effective_trials` as a second, side-by-side DSR — print `dsr` at n≈600
(nominal) AND `dsr_effective` at n≈25-30 (family-clustered) on every new row
exactly as it already does for the current 11, so the reader sees both ends
of the multiplicity range rather than one number presented as settled.

### 3.4 The ordering rule for the new columns

Per the leaderboard's own house rule ("read `by_year_signs`, LOO-worst and
the worst breadth cell BEFORE the CAGR column; read DSR before Sharpe"),
extend it explicitly: **read sealed CAGR before dev CAGR, and read the sealed
block count before either.** A row where dev CAGR is spectacular and sealed
CAGR is negative should be UNMISSABLE in the render — not something a reader
derives by mentally subtracting the existing "CAGR since 2020" from a
by-year table. Concretely, `LEADERBOARD.md`'s render step should place
`n_blocks_sealed | sealed CAGR | sealed vs SPY | dev CAGR | dev vs SPY | DSR
(sealed) | DSR (dev) | ...` ahead of every column currently there, and the
`Top 10 by hindsight CAGR since 2020` table should be relabeled or dropped in
favor of a `Top 10 by sealed net return` table — ranking on the blended
"since 2020" number is exactly the objective mismatch item D is asking to
fix, since MAXIMISE SEALED NET RETURN and MAXIMISE BLENDED-SINCE-2020 RETURN
are two different rankings whenever a rule's dev and sealed performance
diverge, which the family's own §64 lesson ("check whether the noise is
shared," "print by year before the CAGR") already predicts some will.

---

## Sources

- QuantConnect LEAN CLI custom-data docs —
  https://www.quantconnect.com/docs/v2/lean-cli/datasets/custom-data
- QuantConnect LEAN CLI dataset-market key concepts (the actual paid-tier
  wall) — https://www.quantconnect.com/docs/v2/lean-cli/datasets/quantconnect/key-concepts
- QuantConnect forum, "Lean-cli local development, what data to subscribe?"
  (2024-10-03), confirming local custom-data backtests need no subscription —
  https://www.quantconnect.com/forum/discussion/18129/lean-cli-local-development-what-data-to-subscribe/
- QuantConnect/Lean wiki, implementing `BaseData`/`PythonData` —
  https://github.com/QuantConnect/Lean/wiki/Data%5CImplementing-BaseData
- `vectorbt` license and terms — https://vectorbt.dev/terms/license/ ,
  https://vectorbt.dev/terms/ , https://github.com/polakowo/vectorbt
- `vectorbtpro` license/upgrade page — https://vectorbt.pro/terms/software-license/ ,
  https://vectorbt.dev/getting-started/upgrade/
- `zipline-reloaded` — https://github.com/stefan-jansen/zipline-reloaded ,
  README — https://raw.githubusercontent.com/stefan-jansen/zipline-reloaded/main/README.md
- `zipline-reloaded` custom-bundle friction (issues fetched this session) —
  https://github.com/stefan-jansen/zipline-reloaded/issues/162 ,
  https://github.com/stefan-jansen/zipline-reloaded/issues/188 ,
  https://github.com/stefan-jansen/zipline-reloaded/issues/268 ,
  https://github.com/stefan-jansen/zipline-reloaded/issues/72
- All Part 1 literature ids (MOM-xx, AREV-xx, INS-xx, LV-xx, QUAL-xx, etc.)
  carry forward unchanged from `docs/research_notes/2026-09-26/
  research_strategy_library.md` §1/§5 — not re-cited here.
- In-repo sources cited by file path: `backend/services/strategy_library.py`,
  `backend/services/xs_ranker.py`, `backend/services/attribution.py`
  (`_build_sector_map`), `backend/services/regime_detector.py` (VIX/VIX3M),
  `backend/services/revision_flow.py` / `analyst_intelligence.py` /
  `expected_return.py` (`firm`-level identity), `backend/services/
  thesis_card.py`, `scripts/news_pull.py` / `night_e1_news_return_panel.py`
  (`first_seen_utc`), `backend/data/optimus/wrds/tr13f_s34_*.parquet` (13F
  1996–2024), `backend/data/optimus/night_factory_2026-09-20/
  congress_leadership_split_backtest.json` (TRIAL-CONGRESS-IC),
  `backend/data/optimus/first_books/replay/buyback_insider_divergence_v0_*.json`,
  `backend/data/optimus/strategy_library/LEADERBOARD.md`.
