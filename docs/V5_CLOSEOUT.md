# V5 CLOSEOUT — "Honest History" (2026-07-18/19)

V5's theme was buying and building honest history. It closed in two days.

## Shipped and verified

| What | Verdict / state | Evidence |
|---|---|---|
| EODHD two-phase acceptance gate | Phase 1 "pass" exposed as inflated; **Phase 2 FAIL 14/20** → don't renew | NEGATIVE_RESULTS §8, F-021 |
| EODHD paid-month harvest | **50,462 histories archived** (32,334 delisted + 18,128 active), 0 failures | `engine/data/eodhd/` (local) |
| Panel-quality gate | **PASS** (12/14 delisted spot-check; 10/10 active vs yfinance ≤0.009% dev) | `engine/research/panel_gate_2026-07-18.json` |
| TRIAL-MOM-BACKTEST #13 (pre-registered) | **FAIL**: CAGR 17.9% beat SPY 15.3% & RSP 11.8%, but Sharpe 0.63 vs 0.87, maxDD −54.7%; cloud robustly below SPY | NEGATIVE_RESULTS §9, F-026 |
| TRIAL-MOM-TREND #14 (pre-registered successor) | **FAIL harder**: 4.8%/yr, −61.3% DD — V-shaped-regime whipsaw, filter hand-verified correct. **Momentum-lane inquiry CLOSED** | NEGATIVE_RESULTS §10, F-027 |
| Mandate replay 2015→today (local, ETF sleeves) | Matches pre-commitment: all lanes trail SPY with smaller DD; balanced edges 60/40 CAGR | `QUANTCONNECT_REPLAY_2026-07-18.md` |
| Alpaca paper mirror | **SEEDED** (DKNG 1,897 + SLDP 22,500; fill Mon 07-20 open); double-seed bug found live, duplicate canceled by hand, idempotency guard fixed + regression test | `64024c6` |
| Beat-SPY evidence base | F-022 (TAA graveyard), F-023 (live factor-ETF scoreboard 1W/2T/6L), F-024 (QC library unauditable; Alpha Streams postmortem), F-025 (adopt list: parameter-cloud, universe-hash, fractional Kelly, ML-as-gate) | `BEAT_SPY_EVIDENCE_2026-07-18.md` |
| Investor Brain plan | 3-speed validation architecture (direction-checks / forward-IC / 24mo claims); suppliers-vs-appliers PIT study design; event-ledger; GKX NN blueprint | `INVESTOR_BRAIN_PLAN_2026-07-18.md` |
| Factor Lens (F-018) | Shipped: contributions (loading × realized premium), t-stats, rolling 1y loadings; new stock-page card | `c4c6ea4` |
| Builder absorbs (F-017) | Shipped: contradiction warnings (SEC IM 2017-02), glide-path disclosure, plain-English fan bands, prob-of-target + three levers | `c4c6ea4` |
| Silent-fragility fix | Portfolio /analyze factor exposures read nonexistent keys → alpha/R²/β were None for months; fixed + regression test | `c4c6ea4` |
| Registry | 14 cumulative trials (13/#14 added this arc), DSR/PBO deflate against all | `/api/pi/registry` |
| Fast suite | 2,949 passed, 0 failed | 2026-07-19 run |

## Gaps (adversarial)
1. **QC third-party URLs still missing** — Murat has not completed the 3
   lane backtests on QuantConnect; the historical replay currently rests on
   our self-run numbers (spec-identical, but not third-party-hosted).
2. **Alpaca first fill + divergence metric unverified** until Monday's open;
   the seeded state has never marked a real position.
3. **Congress-IC has still never collected real data in prod** (quota
   failures then weekend); Monday 07:30 ET behind the budget ledger is the
   first genuine attempt. Watch it.
4. The **factor lens** shows realized premiums as "earned" — correct and
   labeled, but a skeptic could misread contribution as persistent expected
   return. Wording reviewed once; deserves a user-eyes pass.
5. The **EODHD archive** is a local, single-machine asset (gitignored).
   No backup. If the laptop dies, $20 of history dies with it.
6. **Suppliers-vs-appliers** and the **event ledger** exist only as designs.
7. Frontend surfaces (lens card, warnings, bands) are build-green and
   deploy-verified at the API level but **not human-eyeballed**.

## Murat's checklist
1. Run the 3 QC backtests with OUR `aegis_lane_mandates.py`, share URLs.
2. Cancel EODHD auto-renew (keep access until period end).
3. Monday: glance at the Alpaca dashboard after the open (positions + equity).
4. Click through: a stock page (new Factor Lens card), portfolio builder
   with 1y + aggressive (warning banner), projection with a target amount.
5. Chase the HKU WRDS approval — it unlocks the NN at paper grade.
6. Back up `engine/data/eodhd/` (~a few GB) to an external drive or cloud.

## Next arc: THE INVESTOR BRAIN (Murat's chosen focus)
Plan of record: `docs/INVESTOR_BRAIN_PLAN_2026-07-18.md`. Build order:
1. **Suppliers-vs-appliers study** — PIT theme baskets from thematic-ETF
   launch holdings; Study A (themes vs SPY, prior: lose) + Study B (the
   novel one: suppliers vs appliers within themes). Pre-register both.
2. **Event ledger v1** — LLM extracts forward events (FDA/PDUFA, launches),
   logs falsifiable pre-event expectations, scores after. Extends #11.
3. **Chen-Zimmermann shortlist** — 3-5 predictors as forward-IC trials
   (attended registration).
4. **NN (GKX blueprint)** — after WRDS lands or on the EODHD 2017+ panel;
   must beat the dead momentum baseline to exist.
Constraints unchanged: pre-register before data, one run per hypothesis,
DSR/PBO vs cumulative count (14), nothing into paper_nav, LLM off trade
paths, negatives published.
