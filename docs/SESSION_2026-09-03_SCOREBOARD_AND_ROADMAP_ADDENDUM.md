# SESSION 36 (2026-09-03) — SCOREBOARD AND ROADMAP ADDENDUM

Addendum to the active TIER 1 `ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`.
Eight Opus agents on non-overlapping surfaces, one coordinator. Every number
below names its receipt; nothing here is quotable without opening the receipt.

## RESULTS SCOREBOARD (the handoff convention, first paragraph, no burying)

- Best historical net OOS result: learner v2 `encoder_clf__residual`, 1m,
  net 10bps/side, 18.28x vs market 4.86x, paired **t 2.64**, clears all 64
  model-null draws (p ~= 0.015) (`tracker_backtest/learner_v2_20260903.json`).
- Best forward paper day: hack4 +1.20% / hack3 +1.19% / hack6 +0.76% (09-02).
- New actionable findings: 7 (below). REFUTED claims corrected: 2 (S35's
  "12-month object" headline; the "model liked nothing" shadow-book read).
- LLM spend: ~$0.004 priced (scenario bridge) + $0 everywhere else.
- RESULT IMPROVEMENT: a calibrated probability head (first in the program),
  a mis-specified null bar found and replaced, NAV freshness restored live.

## WHAT CHANGED IN THE WORLD MODEL (each with its receipt)

1. **BAND_PRIOR is an exclusion rule, and 21 sessions is its best clock.**
   The 12m t 34.5 was overlap flattery (block-t flat ~13.6; per-month info
   decays sub-sqrt(h)). Only `toxic_ge_5` survives BH-FDR; Holm exports
   nothing for 3-5; the 3-5 band is +2.3%/yr t 0.12 in 2022-2024, the era
   the live books trade. Not beta (matched control: +1.0%/yr t 0.23).
   `tracker_backtest/band_horizon_20260903.json`.
2. **Horizon policy (AEGIS-HORIZON-1, recommended):** horizon is a property
   of the admitting signal — 12m for a level admission (costs, not alpha),
   6m for a revision admission (the only net-market-beating arm at every
   cost tier), and NO capital on price-shape signals at daily frequency
   (1-day-reversal breakeven 0.26bps/side at 435x turnover; 12m beats it
   7,021x in TW at 25bps, paired t +13.4). A stop parks proceeds in the
   benchmark, never cash. `tracker_backtest/holding_period_policy_20260903.json`.
   This is Murat's "day trading reading graphs loses" instinct, measured.
3. **The learner's own edge sits on a 3-6 month plateau** (t 2.64 -> 3.42 ->
   3.70 -> 2.65 across 1/3/6/12m) — not "longer is better", and the 12m head
   has n_eff 8 (do not build on it). `learner_v2_20260903.json`.
4. **The null bar was wrong repo-wide.** A model fitted on shuffled targets
   holds one smooth tilt for 107 months; its naive IC-t ranges -9.2..+12.0
   across legitimate seeds. Retire `|null t| < 2` as a bar; the replacement
   is a many-draw model-null percentile. Random-ranking nulls CANNOT catch
   this (max t 1.72 over 200 draws). `learner_v2_20260903.json`.
5. **P(beat)=0.494 was ABOVE the base rate** (0.458): v1 is a ranking score
   with a decimal point (level +2.2pp bias, ordering excellent); v2's
   residual encoder head is the program's first LITERAL probability at
   1m/3m. Sizing may consume v2 probabilities, not v1's. Same receipt.
6. **Four OOS market states exist and matter**: the "broken lottery ticket"
   state (19%: worst mean, fattest tail, HIGHEST big-upside frequency —
   the lost-winners address); half the panel is a state where every model
   but lgbm_clf dies. A MoE gate is now buildable on state + reliability.
   `tracker_backtest/unsupervised_states_20260903.json`.
7. **Holder/analyst identity features subtract** (16/16 ablation cells
   negative; the 13F-popularity corpse rediscovered as collinearity).
   Keeper: the adverse stake effect is a TAIL (top-decile fraction t -8.2
   at 12m), opposite-signed from the linear mean.
   `tracker_backtest/feature_ablation_20260903.json`.

## OPERATIONAL (terminal fleet + website)

- Tournament graded FROM THE VENUE: Alpaca paper does not fill tif=opg
  (13/15 expired untouched) — auction entries cannot be expressed on paper,
  same class as tif=cls. R3/R4 churn measured in dollars (TNXP -3.5% stop
  then re-buy 90min later).
  `aegis-alpha-terminal/state/tournament/2026-09-02_graded.json`.
- Authority solo seal PROVEN (09-03 sha 4fdc008f, tgt=ok x3129; runners
  hash-verified + installed). fleet_health now derives the solo seal.
- Website DEGRADED root-caused: "15 past due" = clock false-positive
  (fixed); NAV staleness = yfinance exclusive-end bug (fixed, freshness
  RESTORED live); WHY-MOVED dict-as-list crash (fixed); mirror/arena
  Alpaca keys REVOKED at Alpaca (attended: mint new); arena scan parquet
  was never deployable (`*.parquet` gitignored; ship plan written).
  Three of five faults were green receipts over broken work.
  `docs/FORENSICS_2026-09-03_HEALTH_EPISODE.md`.
- SIC 9999 mislabeled "Public Administration" on 22.5% of panel rows —
  every sector grouping in the repo must give it an UNCLASSIFIED bucket.

## SCENARIO -> HISTORY BRIDGE (new organ)

20 DeepSeek causal scenarios, graded on real 2013-2024 outcomes for $0.004.
47% of scenario fields map to NOTHING we own — the acquisition queue is
now named: EDGAR 8-K item codes (cheapest win), CCM fundq link, supply-chain
edges, GICS. Cross-model agreement on retrieval fields is 0.225 (narrative
0.53): the analogue set depends on which model you ask.
`tracker_backtest/scenario_bridge_20260903.json`.

## QUEUE (ordered)

1. WEDNESDAY 09-04: books liquidate 10:45 ET, judging 11:00 ET. R1 pinned;
   verify "EXPIRY DAY: entries refused" in runner logs, no re-buys.
2. Post-judging deploy train (finance): forensics fixes are committed
   locally — the trigger-MTM-before-deploy ordering caveat is ALREADY
   satisfied (freshness restored on old code); deploy, then run
   verify-prod-after-deploy.
3. Post-judging fleet train (terminal): R4 re-entry guard (now measured in
   dollars), R3 stop-width, R8 clamp units, R10 execution_authority caller,
   mixed-currency market cap, coverage-scale read, disarm the opg tournament
   arms (the venue cannot express them), SAFEST@2x sealed contract.
4. Mint new Alpaca paper keys for finance mirror+arena (REVOKED); Railway env.
5. Ship the crsp_pit parquet to the volume (arena discovery is blind
   outside the watchlist until then).
6. Adopt AEGIS-HORIZON-1 into a sealed PRODUCT_EXPERIMENT book post-judging:
   the 6m revision-admission book is the strongest candidate (only net winner).
7. Replace `|null t| < 2` with a model-null percentile wherever it gates.
8. MoE gate experiment on states x reliability (states receipt is the input).
9. Scenario-bridge acquisition queue: EDGAR 8-K item codes first.
10. Alpaca INDEX OPTIONS (SPX/SPXW/VIX/VIXW/DJX/XSP) went live on the
    Trading API (2026-09-03 email): cash-settled, no early assignment —
    the S18 "core was never priced" family and any hedged-book design can
    now be expressed without share-delivery paths. Post-judging evaluation,
    paper first if paper supports it.

## STANDING (unchanged)

Ledger hash chain broken since 25 Aug — never silently repair. No reseal of
a live day. Arena graded-never-traded. DeepSeek is the only backend LLM.
