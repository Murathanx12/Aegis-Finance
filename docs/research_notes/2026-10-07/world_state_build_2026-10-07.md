# World state, regime rows, scenarios: the C17 build (2026-10-07, revised after review)

**RESULT IMPROVEMENT: NONE.** This is plumbing that starts measuring today. No regime number is a
finding before the first h5 grades (**2026-10-16**, derived from the rows' `resolves_after`) and
before at least 3 graded entry sessions exist.

- Spec: `docs/research_notes/2026-10-07/world_state_and_regime_rows_2026-10-07.md`.
- Review: `docs/reviews/REVIEW_2026-10-07_C17_WORLD_STATE_REGIME.md` (54/100). This note
  describes the build after the review's fixes.

**RESULTS:**
- 16 beliefs in `world_state/v2`.
- 38 `regime_v1` rows for entry session 2026-10-06 (6 fixed events and 13 sectors, each at h1
  and h5).
- 14 `regime_v0` rows are excluded by rule.
- 8 scenarios, all on declared priors.
- Cost per cycle: world state $0.0000 + regime about $0.0008. The validation call was $0.00076.

## What the review changed

| finding | fix |
|---|---|
| F1 label/event mismatch on 5 of 14 rows | `regime_v1`: one FIXED event per variable. The model sees the base rate and persistence for each event and states P(event). Sectors get 13 P(ETF beats SPY) numbers, shifted so their mean equals the mean of their base rates. The 14 v0 rows stay in the ledger and are excluded from every grade by `config.WORLD_STATE_REGIME_EXCLUDED_VERSIONS = {"regime_v0": "v0_incoherent"}`. The label is applied at read time; ledger rows are never rewritten. |
| F2 UTC-day keying | One row per (variable, h, **entry session**). The entry session is the session whose close the resolver anchors on, so writes on Saturday, Sunday and Monday before the open share Monday's. Duplicates are refused. Grades are blocked by entry session, and h5 grades use only non-overlapping windows. |
| F3 belief noise | Rows are collapsed into root events, so a syndicated story counts as one vote. Only root events not yet applied move a belief. One vote per (theme, topic), weighted by the share of the theme's root events that are new. Masses (up, down) decay by elapsed time at the topic's half-life. `belief_stability` is printed on every receipt and reads DEGRADED above 0.25. |
| F4 key 1 | Per arm, never max(). An arm needs n ≥ N_MDE dates, posterior − 1.64·sd > 0, and trust ≥ 0.05 (`config.NEWS_TILT_KEY1_*`). An arm whose key fails contributes trust 0. |
| F5/F7 | `regime_grade` prints absolute Briers, every null, MDE, N_needed and a verdict. A panel that lags the last closed session is REFUSED before any spend, which makes persistence lag-1. `realised_stress` (renamed) carries an EWMA(0.94) vol null. `vol_prior_p` is also stored, but it is the 252-session frequency, i.e. the base rate. |
| F8 scenarios | Priors live in config with value, version, author, date and hash. A changed prior is logged PRIOR_RESTATED. Probabilities move slowly: indicators are smoothed over 30 days and a probability moves at most 0.01 per day. The stored number sits under `probability_sealed` and is read only through `scenario_probability(s, "display")`. |
| F9 provenance | FACT needs a positive rule: reported actuals, an official host, a reported event type, or a data page. Anything else is UNCLASSIFIED. Analyst actions are INTERPRETATION. Each forward claim carries its own provenance. Provenance is observation-only and weights no evidence. |
| F10 | The tilt runs BEFORE the order-path gate. Key 2 reads the PC plan's own regret rows: `mdc_news_tilt_full` = utility(plan_plus_shadow_news_full) − utility(plan_full), net of round-trip cost. |
| F11/F12/F13 | Edges are renamed `co_mention_edges` and their signs are netted per cycle. First due dates are derived from the rows. The regime grade uses `raw_probability`. The ledger `brier` (on the shrunk number) is labelled `brier_ledger_shrunk_NOT_THE_GRADE`. |

## Provenance on the 19,659 cached rows (re-run)

| provenance | rows | share |
|---|---|---|
| UNCLASSIFIED | 7,557 | 38.4% |
| FACT | 5,556 | 28.3% |
| INTERPRETATION | 3,956 | 20.1% |
| FORECAST | 1,662 | 8.5% |
| COMPANY_CLAIM | 928 | 4.7% |

Before the fix, FACT was 67% because it was the default bucket. Official hosts are now matched on
the URL **host**: a substring match let Google-News links containing "sec" or "bea" through.

## Belief stability on the two digests 45 minutes apart (replayed under v2, $0)

| version | belief_stability | beliefs that flipped |
|---|---|---|
| v1 (review) | 4 of 16 flipped | `energy_security` up 0.28 → down 0.06, and three others |
| v2 | **0.125** (2 of 16) | `china_policy` none → mixed (conf 0.02); `semiconductor_capex` mixed → up (0.06) |

`energy_security` stays up 0.19. The second digest brought 85 new root events, against 791 in the
first.

Caveat: the replay rebuilt each theme's row membership from its URLs and top tickers, because the
digest JSON does not store theme row indices. Live cycles pass the exact indices.

## The live belief table (rebuilt from those two digests, `world_state/beliefs.json`)

| topic | direction | confidence |
|---|---|---|
| ai_demand | up | 0.41 |
| consumer_conditions | down | 0.29 |
| dollar | up | 0.28 |
| energy_security | up | 0.19 |
| commodity_shortages | down | 0.08 |
| grid_power_demand | up | 0.07 |
| semiconductor_capex | up | 0.06 |

The other nine topics are mixed or none, at 0.05 or below.

## The first regime_v1 rows (validation call, entry session 2026-10-06, written to the ledger)

The model's answer, as returned: *"probabilities stay near the base rates with only small tilts"*.

| event | p_model h1 / h5 | base rate h1 / h5 | persistence h1 / h5 |
|---|---|---|---|
| growth: SPY > 0 | 0.535 / 0.550 | 0.532 / 0.564 | 0.548 / 0.486 |
| rates_down: TLT > 0 | 0.460 / 0.440 | 0.476 / 0.433 | 0.430 / 0.450 |
| liquidity: HYG beats IEF | 0.530 / 0.615 | 0.536 / 0.615 | 0.515 / 0.619 |
| risk_appetite: IWM beats SPY | 0.485 / 0.465 | 0.480 / 0.476 | 0.492 / 0.431 |
| commodities: USO > 0 | 0.545 / 0.545 | 0.548 / 0.536 | 0.547 / 0.552 |
| realised_stress | 0.360 / 0.390 | 0.353 / 0.361 | 0.366 / 0.424 |
| SMH beats SPY | 0.610 / 0.615 | 0.599 / 0.623 | 0.647 / 0.597 |
| XLY beats SPY | 0.415 / 0.340 | 0.421 / 0.361 | 0.411 / 0.242 |

For realised_stress, the EWMA-vol null is 0.272 at both horizons. The other 11 sectors are in the
receipt.

Receipt: `backend/data/optimus/digest/regime_v1_validation_<stamp>.json`.

The model now sits within about 0.02 of its baselines on almost every row. That is coherent. It
also means the arm can only show skill through small departures from the nulls, which is exactly
what N_needed measures.

## The news wire, as it now prints

`news tilt: trust dir 0.0069 / size 0.0000 (usable 0.0000 / 0.0000), applied=False (flag NEWS_TILT_IN_PLAN=False); key 1: NOT MET (direction NOT MET (n 3 of ~505); size NOT MET (n 4 of ~78)); key 2: NOT MET (0/20 PC-plan regret sessions)`

## Scenarios

All 8 are back at their declared priors after the v2 rebuild:

| scenario | prior |
|---|---|
| ai_capex_supercycle_2027 | 0.40 |
| ai_capex_digestion_2027 | 0.25 |
| higher_for_longer_2027 | 0.30 |
| us_recession_2027 | 0.25 |
| taiwan_strait_crisis_2027 | 0.08 |
| energy_supply_shock_2027 | 0.15 |
| grid_electrification_2030 | 0.50 |
| biotech_regulatory_tailwind_2030 | 0.35 |

Under the slow rule they can move at most 0.01 per day. The newest prediction-market snapshot is
2026-08-21, 46 days old, so no market prior is used.

## What waits

- **Regime grades:**
  - The first h1 rows resolve 2026-10-10 and the first h5 rows 2026-10-16.
  - Trust stays exactly 0 below 3 graded entry sessions.
  - N_needed is about 352 independent entry sessions per field to detect δ = 0.005 Brier at the
    prior per-date sd of 0.0335. That is about 1.4 trading years, and longer for h5.
- **Key 1** needs about 505 dates on the direction arm and about 78 on the size arm, at today's
  measured sd.
- **Key 2** waits for `u_plan` and the regret ledger to accrue at least 20 PC-plan sessions.
- **Market-implied scenario priors** wait for a fresh prediction-market snapshot.
