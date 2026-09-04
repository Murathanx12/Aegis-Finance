# HANDOFF — S37 → Fable 5.1 (2026-09-04): REVIEW MANDATE, not a build queue

You are being handed the program to REVIEW, VALIDATE, and RE-PLAN — not to
extend. Murat's instruction verbatim: *"review everything, validate our work
and approach, find better alternatives perhaps and methods, to make a better
roadmap and services we can do."* Your deliverables are at the bottom. Your
default posture is adversarial: we pay you to find what's wrong, the way S36
killed S35's best finding and S37 found the repo's null bar was broken.

## READ FIRST, IN THIS ORDER

1. `docs/AEGIS_STRATEGIC_INVARIANTS.md` (TIER 0 — 16 points, changes ~2x/yr)
2. `docs/HANDOFF_2026-09-03_S36_REVIEW_AND_BUILD.md` (S36 results + incident)
3. `docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md` (external
   review verdicts on the 7 questions + allocator design)
4. Terminal repo `docs/FINDING_2026-09-04_THE_INVISIBLE_40PCT_CEILING.md`
5. Session memory: `project_session_37_2026_09_04_night_watch_the_invisible_ceiling.md`
6. Then receipts on demand (every claim below names its file under
   `backend/data/optimus/tracker_backtest/`).

## STATE SNAPSHOT (as of 2026-09-04 ~07:00 HKT)

- **Judging is TODAY 11:00 ET (23:00 HKT).** Until it completes: NO pushes to
  either repo, NO fleet/seal/order actions, NO Railway config changes. The
  expiry-day guard liquidates the books at 10:45 ET; peer session
  aegis-finance-51 has that watch.
- Finance repo: 13 local commits ahead of origin (`e8d91fa` is origin tip).
  Full fast suite on the merged tree: **6,269 passed / 0 failed / 17 skipped**.
- Terminal repo: 3+ local commits ahead, deliberately unpushed (a push
  redeploys seal-authority). Terminal suite ALL PASS (72 suites / 3,287).
- Website deploy verified live at `e8d91fa0`, nav fresh, zero degraded.
- Fleet: six paper accounts, unattended artery proven; scoreboard in
  `state/benchmark_regret_20260903.json` (terminal). hack4 ≈ benchmark and
  the only positive-realized book; hack3/5/6 carry the 08-28 kickoff losses.
- `claude` CLI updated to 2.1.260 for this handoff.

## THE CLAIMS TO ATTACK (each with its receipt; do not re-derive, re-JUDGE)

| # | Claim | Receipt | What would kill it |
|---|---|---|---|
| 1 | The `\|shuffled-null t\|<2` bar was mis-specified; replacement = >=64-draw model-null percentile, per-pipeline (nulls are architecture-dependent: lgbm sd 0.89 vs encoder sd 2-3), family max-stat for selected arms | `learner_v1_model_null_64_20260904.json`, `feature_ablation_model_null_64_20260904.json`, `learner/nullbar.py` | a flaw in the permutation scheme (within-month shuffle preserves what?); is 64 draws enough for p floors at 0.0154; is add-one the right convention |
| 2 | Learner v2 champion (`encoder_clf residual 1m`, net t 2.64) deserves frozen forward accrual | `learner_v2_20260903.json` | multiplicity accounting across the ~48 arm-horizon cells; the champion was picked post-hoc before freezing |
| 3 | BAND_PRIOR = exclusion only (toxic_ge_5 survives FDR); 3-5 band dead 2022-24 | `band_horizon_20260903.json` | block-t methodology; the beta-matched control's construction |
| 4 | Toxic-band SHORT: beta-hedged liq-floored 1m = +76.6%/yr gross t 7.24, breakeven borrow 57%/yr, best era 2022-24 | `toxic_band_short_20260904.json` | borrow-fee/squeeze correlation (the receipt itself flags it); PIT of the ratio; short-side delisting treatment |
| 5 | Revision-6M: overlapping cohorts remove a 2.9x phase lottery; edge is PRE-2022 (2022-24 adverse −4.3pp/yr) | `revision_6m_cohorts_20260904.json`, `docs/CONTRACT_DRAFT_2026-09-04_REVISION_6M.md` | is a pre-2022-only edge worth a book at all; IBES-coverage filter as hidden selection |
| 6 | The fleet's idle capital = UNCLASSIFIED driver bucket capping every tracker book at 40% gross | terminal `docs/FINDING_2026-09-04_THE_INVISIBLE_40PCT_CEILING.md` + dry-run log | reproduce it yourself; then judge the FIX (sector drivers at seal time) — is sector the right correlation proxy or do we need measured cluster drivers |
| 7 | Capital Allocator v0 design: cash requires a thesis, benchmark is the parking orbit, U_i = E − λ·CVaR − λ·Costs − λ·Uncertainty | `learner/allocator.py`, artifacts in `backend/data/optimus/decision_artifacts/` | the λs are PRIOR_ONLY; is a linear utility the right v1 or should it be Kelly-fraction/drawdown-constrained; 8 named PRIOR_ONLY inputs |
| 8 | PotentialUniverse v1 schema is the right substrate for the allocator | `learner/potential_universe.py`, vintage `potential_universe/2026-09-02.jsonl` | the tracker file IS the observability ceiling (OBSERVE_ONLY names never enter); v2 champion REFUSES on shadow schema — is the schema or the champion wrong |
| 9 | Unsupervised states: 4 OOS states; first consumer = SIZING (GPT) vs stop-width (handoff) — unresolved tension | `unsupervised_states_20260903.json` | the new persistence-preserving null (`learner/states.py::persistent_shuffled_null`) has NOT been run over the sealed states result — running it is fair game and could kill the states |
| 10 | AEGIS-HORIZON-1 policy: 12m level / 6m revision / no daily chart lane | `holding_period_policy_20260903.json` | cost-tier assumptions; is a knowingly-non-alpha level book worth anything (GPT says retire levels) |

## KNOWN WEAKNESSES (start here, we already distrust these)

- **Demonstrated edge is still ~0% forward.** Everything above is backtest or
  one-day-old shadow. The farm's verdict stands: sqrt(T) is exhausted on
  historical data; only forward evidence and mechanism-specific books move it.
- The 08-28 kickoff loss (−9% on three books in 40 minutes) was a leverage ×
  stop cascade — fixed, but the risk-guard fix train (R3/R8/R10/R4) is still
  QUEUED, not shipped. Four risk guards measured as unable to fire (S35).
- Two sub-systems are dead and reported honestly: the counterfactual marker
  (since 08-28 → refusal regret CANNOT DETERMINE) and the campaign ledger's
  path persistence (writes to a non-volume path on Railway).
- The ledger hash chain is torn since 25 Aug — evidence, never repaired.
- Concurrent-session write contention on one repo tree is a live operational
  risk (two sessions + agents committed to the same branch this week).

## OPEN / ATTENDED DECISIONS (Murat's, not yours — but advise)

1. Post-judging fleet remap (six mechanism-specific books; review doc PART B).
2. AEGIS-HORIZON-1 adoption.
3. Mint mirror/arena Alpaca keys (revoked; still not done).
4. seal-authority public GET-only domain — keep or delete.
5. Data buys: real borrow fees (gates claim #4), historical CRSP-CIK link
   (gates EDGAR panel joins), OptionMetrics re-join for the options books.

## YOUR DELIVERABLES

1. **Validation verdicts** on claims 1–10: CONFIRMED / REFUTED /
   CANNOT_DETERMINE-with-what-would-determine, each with what you actually
   re-ran or re-read. Running the persistence null over the sealed states
   (claim 9) and re-deriving one or two of the cheapest receipts end-to-end
   is strongly encouraged; heavy re-runs are authorized.
2. **Better methods**, where you have them: the null scheme, the allocator
   objective, the driver taxonomy fix, the multiplicity regime, scenario
   generation. Name the method, the cost, and what it changes — not a survey.
3. **A new TIER 1 roadmap draft** (`docs/ROADMAP_2026-09-04_*.md`): what the
   next 10 sessions should build, gates-not-dates, with the post-judging fix
   train (starved seal P0, driver taxonomy, risk guards, stop-to-benchmark,
   DecisionArtifact→Railway) explicitly sequenced against the research lanes.
4. **A services proposal**: given what now exists (PotentialUniverse,
   allocator artifacts, daily learning report, receipts discipline, the
   public repo), what can Aegis OFFER — to Murat's own capital, to the
   open-source public tool's users, to the HKU paper — and what is the
   minimum honest version of each. "Services" includes internal services
   (the daily report, the allocator) and external ones (the public tool run
   at someone else's utility function; a published dataset/tape; the paper).
5. Every verdict lands as receipt + doc; anything you change lands as
   commit + test, same boundaries as every session.

## BOUNDARIES (unchanged, not optional)

- Nothing pushes, deploys, seals, or orders before judging completes today.
- Never move `.env`; finance tests via `AEGIS_IGNORE_DOTENV=1 python -m
  pytest backend/tests/ -m "not slow"`; terminal via `python run_tests.py`.
- DeepSeek is the only LLM provider. No LLM authority over capital.
- Sealed receipts are immutable; addenda live in new files.
- The ledger tear is evidence; repairing it is the tampering.
- Coordinate with any live peer session via SendMessage before touching
  shared surfaces (`ListAgents` shows them).
