# HANDOFF — Session 36 (2026-09-03) — for GPT review and Opus build

One page of state, then results with receipts, then the ordered queue, then
open research questions. Written to be pasted into a reviewer (GPT) and a
builder (Opus) session. The builder's boundaries are at the bottom and are
not optional.

## TLDR

Eight Opus agents ran overnight on non-overlapping surfaces while the fleet
traded unattended. The session's three headline events:

1. **We corrected our own best-looking finding.** "BAND_PRIOR is a 12-month
   object" (S35) is REFUTED — the 12m t 34.5 was overlapping-window
   flattery. The band is an **exclusion rule** (only `toxic_ge_5` survives
   FDR), it is **dead in 2022-2024**, it is **not beta**, and 21 sessions is
   the best clock it has. Separately, the holding-period study showed longer
   holds still win **on costs**: 12m for level admissions, 6m for revision
   admissions (the only arm that beats the market net at every cost tier),
   and a measured "no" to daily chart trading (1-day-reversal breakeven
   0.26 bps/side at 435x turnover).
2. **The learner grew up.** v2's residual encoder is net-positive vs the
   market at 1m (paired t 2.64) and carries the program's FIRST literally
   calibrated probability head. En route we discovered the repo's
   `|shuffled-null t| < 2` bar is itself mis-specified (a model fitted on
   noise holds one tilt for 107 months; its naive t spans -9..+12) — every
   result must now be judged against >=64 model-null draws.
3. **The fleet is fully unattended and the website is repaired.** First
   solo seal proven end-to-end (sha 4fdc008f, tgt=ok x3129, all runners
   installed). Tournament graded from the venue: Alpaca paper does NOT fill
   opg auction orders (13/15 expired) — the entry-timing question cannot be
   answered on this venue. Website DEGRADED root-caused: NAV bug (yfinance
   exclusive `end`) fixed and freshness restored live; "15 past due" was a
   health-clock false positive, fixed; WHY-MOVED crash fixed; mirror/arena
   Alpaca keys found REVOKED (attended).

## ROADMAP POSITION (honest percentages)

- **Competition week (judging 2026-09-04 11:00 ET): ~95%.** Books trade
  unattended, stops rest broker-side, R1 expiry-day guard is pinned by
  test. Remaining 5% = tomorrow's live verification (checklist below).
- **TIER 1 world-model/learning roadmap: ~60%.** Done: historical
  experiment factory substrate (441k name-months PIT), supervised learners
  v1+v2 with calibration, unsupervised states v1, scenario->history bridge
  v1, horizon adjudication, feature-family ablations, hypothesis harvest +
  4 preregs. Not built: mixture-of-experts gate (its two inputs now exist),
  PotentialUniverse (the one-scorecard-per-observable-name object),
  DecisionArtifact laptop->Railway bridge, daily learning report,
  graph/sequence models, continuous (self-running) hypothesis factory.

## RESULTS (every number has a receipt; do not quote without opening it)

| Finding | Number | Receipt |
|---|---|---|
| Band prior horizon | block-t flat 14.6->13.6 across 1/3/6/12m; IC sub-sqrt(h); 3-5 band 2022-24: +2.3%/yr t 0.12; beta-matched control +1.0%/yr t 0.23; only toxic_ge_5 survives BH-FDR | `tracker_backtest/band_horizon_20260903.json` |
| RANK-VS-EXPRETURN-1 | resolved NO-DIFFERENCE; random ordering beat the sealed expectation field | same |
| Holding period | 12m level (1m behind before first commission, breakeven -2.08bps); 6m revision only net VW-beater; 1-day reversal breakeven 0.26bps at 435x turnover; 12m vs day trading TW ratio 7,021x, paired t +13.4; stop parks in benchmark not cash | `tracker_backtest/holding_period_policy_20260903.json` |
| Learner v2 | encoder_clf residual 1m net t 2.64 (18.28x vs 4.86x), clears 64 model-null draws p~.015; horizon plateau 3-6m (t 2.64/3.42/3.70/2.65); calibrated P(beat) at 1m/3m; v1's 0.494 was ABOVE base rate 0.458 | `tracker_backtest/learner_v2_20260903.json` |
| Null-bar defect | shuffled-MODEL null t spans -9.2..+12.0 across seeds; random-ranking max t 1.72/200 draws | same |
| Unsupervised states | 4 stable OOS states, p=0.000 vs 200 random partitions; state 0 "broken lottery ticket" (19%): mean -4.9%/3m t -3.4, worst-5% -75%, big-upside freq 21.7%; half the panel kills every model except lgbm_clf | `tracker_backtest/unsupervised_states_20260903.json` |
| Feature ablation | holder+analyst families subtract in 16/16 cells; adverse stake is a TAIL (top-decile fraction t -8.2 at 12m), linear mean opposite-signed (+2.27) | `tracker_backtest/feature_ablation_20260903.json` |
| Scenario bridge | 20 scenarios graded on real outcomes, $0.004; 47% of fields map to nothing owned; cross-model agreement on retrieval fields 0.225 | `tracker_backtest/scenario_bridge_20260903.json` |
| Tournament 09-02 | opg: 13/15 expired unfilled on paper; churn measured (TNXP stop -3.5% then re-buy +90min); day P&L hack3 +1.19 / hack4 +1.20 / hack6 +0.76 | terminal `state/tournament/2026-09-02_graded.json` |
| Health episode | 5 faults, 3 were "green receipts over broken work"; NAV freshness RESTORED live | `docs/FORENSICS_2026-09-03_HEALTH_EPISODE.md` + `tracker_backtest/health_forensics_20260903.json` |

## TESTS

- Finance fast suite: **6,171 passed / 0 failed / 14 skipped** on the merged
  tree (was 6,074 at session start; +97 new tests incl. red-then-green
  forensics pins, PIT/beta guards, states leakage guards both directions,
  scenario schema/retriever, calibration).
- Terminal suite: **71 suites / 3,235 checks ALL PASS** (venue socket
  blocked; run ONLY via `python run_tests.py`).
- New pinned invariants worth knowing exist: expiry-day refuses all entries
  through BOTH the 10:01 and the auction path; fleet_health derives the
  solo seal from the authority log; a beta fitted on the return it explains
  is caught by a slow twin; cross-block KMeans relabelling can no longer
  cancel a planted effect.

## DEPLOY / OPS STATE (as of writing)

- Finance `main` pushed to `019b5b5` (16 commits). GitHub page (README +
  3 new receipt-driven charts + INDEX ladder + DATA_MANIFEST) is live.
  Railway deploy of 019b5b5 was mid-build at handoff time — run
  `verify-prod-after-deploy` to completion: commit flip, canaries
  (`nav.all_fresh` already TRUE), then confirm the "15 past due" false
  positive is gone from `degraded_reasons` under the new predicate.
- Terminal repo has 2 local commits (eb7de9f receipt+gate, acc3544
  handoff) **deliberately NOT pushed**: a push redeploys seal-authority and
  could reseal a different sha mid-day. Push after 16:05 ET today, or
  first prove the authority's books survive a redeploy.
- Fleet: all six accounts healthy; today (09-03) runs one more ordinary
  tournament day; failure direction is the control.
- `.env.bak.2026-08-27` contained LIVE keys and was un-ignored; now
  ignored, verified never committed.

## INCIDENT FOUND AFTER THE FIRST PUSH (09-03 open) — READ BEFORE THE QUEUE

The authority's first solo seal was VALID and EMPTY: `portfolios[hack4]` =
0 names. Root cause: `days_to_catalyst` derives from the observation corpus
(`state/corpus/` — laptop-only, never on the authority's volume), so
`d_catalyst` was UNREADABLE on all 810 candidates and hack4
(`requires_catalyst=True`) sealed empty; hack6's coverage-calibration
refusal is the same class of suspect. The exit pass then treated "dropped
out of the book" as SELL — **a data gap became a sell decision** — and the
books drifted to ~15-30% deployed on competition eve (safe: fail-closed,
stops resting, remaining positions held; tomorrow's 10:45 liquidation
unaffected). Full write-up + fix direction: terminal `docs/HANDOFF.md` S36.

This adds a P0 to the build queue (post-judging): (a) whole-universe
UNREADABLE must carry holdings forward with a staleness flag or mark the
book DEGRADED — never trim; (b) ship the corpus/coverage inputs to the
authority so a solo seal has laptop-grade information; (c) fleet_health
alarms on an empty enabled book AT SEAL TIME.

Extra research question for GPT: **8.** When a sealed book is empty because
of a DATA GAP (not a market opinion), what is the correct standing policy —
hold yesterday's book with a declared staleness penalty, degrade to the
benchmark, or go to cash? Cash is what implicitly happened; argue for one.

## TODOS — ATTENDED (Murat, cannot be delegated)

1. **Mint new Alpaca paper keys** for the finance mirror + arena accounts
   (both REVOKED at the venue; hack1-6 keys are fine) and set them on
   Railway. Copying old keys cannot fix a revocation.
2. Decide adoption of **AEGIS-HORIZON-1** as policy (12m level / 6m
   revision / no daily chart lane) — it reshapes every future book.
3. Post-judging: approve the SAFEST@2x-intraday sealed contract if wanted.

## TODOS — BUILD QUEUE FOR OPUS (ordered; each names producer, artifact, consumer, grader)

1. **09-04 JUDGING-DAY VERIFICATION (first, before anything).** Verify in
   runner logs: "EXPIRY DAY: entries refused" on every book, 10:45 ET
   liquidation, zero re-buys after it. Nothing else ships until this is
   confirmed clean.
2. **Terminal push + fix train** (after 16:05 ET / after judging): push
   eb7de9f+acc3544; then R4 re-entry guard (measured in dollars now), R3
   stop-width (equity.stop_hit hardcodes 3% vs protect's 6-8%), R8 clamp
   units, R10 execution_authority caller, disarm the opg tournament arms
   (delete one env line each in alpha/fleet.py — the venue cannot express
   them), mixed-currency market_cap_usd, coverage-scale read.
3. **Finance deploy verification** of 019b5b5 (see ops state).
4. **Retire `|null t| < 2` repo-wide** — replace with >=64-draw model-null
   percentile wherever a shuffled null gates a claim. Producer: a shared
   helper in learner/; consumers: every evaluator; grader: the existing
   receipts re-checked.
5. **Mixture-of-experts gate v1** (both inputs now exist): gate features =
   unsupervised state + band + coverage + missingness + trailing matured
   OOS reliability; experts = BAND_PRIOR, lgbm_clf, encoder residual,
   ridge; compare equal-weight vs rolling-reliability vs learned gate;
   SHADOW ONLY. Key prior from states receipt: lgbm_clf is the only arm
   alive in all four states.
6. **PotentialUniverse v1**: one scorecard per observable company-vintage
   (engine prior, v1/v2 predictions, state/anomaly, disagreement,
   execution capacity, OBSERVE_ONLY flag, reasons+falsifiers). Persist
   daily beside the shadow books; graded like any book.
7. **6m revision-admission PRODUCT_EXPERIMENT book**: frozen strategy
   contract before the first decision (the only net-market-beating arm).
8. **Ship `crsp_pit_monthly_v1.parquet` to the Railway volume** (arena
   discovery is blind outside the watchlist until then; plan in forensics
   doc).
9. **Scenario-bridge acquisition #1: EDGAR 8-K item codes** (free, dated)
   -> event_type becomes mappable; re-run the 20 scenarios.
10. **Fix SIC 9999** ("Public Administration" on 22.5% of rows) with an
    honest UNCLASSIFIED bucket in tracker_ibes_backtest.SIC_DIVISIONS.
11. **Daily learning report** (the roadmap item nobody built): one page,
    auto-generated — yesterday's books vs seals, refusal regret, shadow
    books, watchlist events.
12. **Index options design study** (SPX/XSP/VIX live on Alpaca 09-03,
    cash-settled): can the S18 "core was never priced" family or a hedged
    book be expressed? Check paper support first.

## NEW IDEAS (this session's harvest, untested)

- **Trade the learner where the engine is silent, literally**: a shadow
  book restricted to `no_opinion` + state!=1 names ranked by the calibrated
  v2 head — the two conditioning facts we now have receipts for.
- **State-0 barbell**: the "broken lottery ticket" state has the panel's
  highest big-upside frequency AND worst mean — a tiny-weight, wide-stop,
  many-names lottery sleeve is the natural expression of Murat's lost
  winners; needs a prereg because the mean is negative.
- **The adverse-stake TAIL as a short/avoid overlay** (top-decile fraction,
  t -8.2 at 12m) — after borrow/cost modeling.
- **Stop-to-benchmark**: change every book's stop to park proceeds in SPY
  instead of cash (the holding-period study's single most valuable line).
- **Analyst REVISION velocity as the admission signal** (Brav-Lehavy: the
  revision pays, the level doesn't) — the 6m book above is its vehicle.

## RESEARCH QUESTIONS FOR GPT (review pass)

1. The null-bar finding: do you accept the diagnosis (serially-correlated
   single-tilt => inflated naive t) and the >=64-draw model-null percentile
   as the replacement bar? Is 64 enough draws, and should the percentile be
   computed per-metric (IC, paired-t, TW) or only on the primary?
2. Band verdict tension: band-horizon says the 3-5 band is statistically
   unestablished vs the market and dead 2022-24, yet the live books gate on
   it. Should the sealed books (a) keep the gate as pure exclusion
   (toxic>=5 + <1.5 only), (b) keep 3-5 as-is until the forward paper
   record matures, or (c) replace admission with the calibrated v2 head?
   What forward evidence would decide this fastest?
3. Learner v2's t 2.64 at 1m survives its model-null but is one champion
   over ~12 arms x 4 horizons — what multiplicity correction do you want
   before it feeds ANY shadow sizing? (Our proposal: pre-register ONE
   champion + one metric now, grade forward only.)
4. Horizon policy: 12m-level is a cost argument, not an alpha argument
   (nothing beats VW on the level signal). Is a book that knowingly holds a
   non-alpha signal at lower cost worth running at all, or should level
   admissions be retired in favor of revision admissions everywhere?
5. The MoE gate can only see trailing matured reliability, which at 6-12m
   horizons means the gate is years behind the regime. Is a monthly-horizon
   gate over monthly experts the only honest v1, with longer-horizon
   experts entering as fixed sleeves?
6. Scenario bridge: given retrieval-field agreement of 0.225 between
   models, should scenario generation move to committee-of-N with field
   voting before ANY scenario result is used, or is single-model +
   disagreement-logging enough at this stage?
7. States: no state is profitable (they rank loss/tail). What is the
   correct first CONSUMER — position sizing, stop width, or admission veto?
   We lean stop width (risk resolves ~30x faster than return, canon §59).

## BUILDER BOUNDARIES (Opus session, not optional)

- Read finance `docs/INDEX.md` TIER 0 + `ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`
  + `docs/SESSION_2026-09-03_SCOREBOARD_AND_ROADMAP_ADDENDUM.md` first.
- Before 09-04 11:00 ET: NO terminal-repo push, NO fleet deploys, NO order
  submission/cancellation, NO change to sealed books or account allocations.
- Never move `.env`; finance tests via `AEGIS_IGNORE_DOTENV=1 python -m
  pytest backend/tests/ -m "not slow"`; terminal tests ONLY via
  `python run_tests.py`.
- The ledger hash chain (broken since 25 Aug) is never silently repaired.
- No LLM authority over capital. DeepSeek is the only backend provider.
- Every result lands as receipt + doc + test; a capability without a
  consumer is not built (signal_reachability will fail the suite).
