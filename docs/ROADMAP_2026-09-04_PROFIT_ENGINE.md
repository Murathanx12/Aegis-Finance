# ROADMAP — THE PROFIT ENGINE (adopted 2026-09-04, Fable 5.1 as brain, Opus 5 as builder)

**Status: ACTIVE TIER 1.** Supersedes `ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`
(kept as the receipt for competition week) and the S36 addendum.
**Strategic authority (unchanged):** `AEGIS_STRATEGIC_INVARIANTS.md`,
`AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`,
`AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md`, `OPTIMUS_OBJECTIVE.md` §0.
**Evidence base:** `REVIEW_2026-09-04_FABLE51_VERDICTS.md` — read it first; every
block below exists because of a finding there.

**Gates, not dates.** Blocks are ordered by dependency and evidence. A block
opens when its predecessor's gate is green, not on a calendar. Several Opus
agents can finish a block in one session; two things cannot be parallelised —
forward time, and statistical information that does not exist yet.

---

## 0. The reset, in one paragraph

Murat's instruction: *forget the hackathon; treat AEGIS as a product that
maximises an individual user's benchmark-relative compound wealth at their
declared risk; backtest with the LLM and the NN until we honestly beat the
S&P; learn from every backtest; do not kill ideas on one instance; go to the
roots of companies like WBUY, GPRO, MRVL, MU, XOM, SOC, ALMS, XHLD, MSTR,
NVDA, AMD and their sectors, competitors and dependencies.* The external
review's frame — research is a subordinate service of a profit product — is
adopted. The order is changed by what the review of 2026-09-04 found: the
ruler was wrong (+740% was triple-compounded), the tape was wrong (adjusted
targets over raw prices), the champion was unadjusted for search, the books
sold on a 3-day drift rule, and the learning loop was silent. **So: fix the
ruler, fix the tape, fix the hold, make the loop speak — then search
aggressively, with honest inference, on clean data.** Nothing in the search
phase is allowed to run on the old panel.

The artery is unchanged:
`WORLD SENSORS → EVIDENCE → COMPANYWORLD GRAPH → EXPECTATIONS → DIVERGENCE → EXPRESSION → ADMISSION → REALITY → LEARNING`.
What changes is that every block below names the **entry point that consumes
it** in the same commit, or it is a print.

---

## 1. Top-line KPIs (replace hit rate; every block reports the ones it moves)

| KPI | Definition | Owner block |
|---|---|---|
| Terminal wealth vs SPY TR, after cost | per book, per era, per sealed test | B1, B8, B9 |
| Family-adjusted evidence | max-stat p over every cell looked at; DSR; PBO | B4 |
| Opportunity recall | of the next-12-month top-50 idiosyncratic winners in the PIT universe, the share each generator surfaced *before* the move; misses typed NOT_OBSERVED / GENERATED_NOT_RANKED / RANKED_NOT_BOUGHT / BOUGHT_SOLD_EARLY | B3, B6 |
| Winner capture ratio | realised / (held-to-thesis-horizon) on every closed position | B2 |
| Premature-exit, stop, re-entry and refusal regret | dollars per day, decomposed | B2, B3 |
| Capital utilisation and the BINDING constraint | actual / intent / ceiling, which guard bound | B2 |
| Turnover, cost drag, capacity | per book at $100k / $1m / $10m | B1, B9 |
| Calibration | Brier + reliability table per head, per LLM arm | B4, B7 |
| Max drawdown, CVaR₅, P(ruin) at the largest admissible book | printed in dollars before any sizing change | B9 |
| Performance by era / state | never pooled across eras | all |

---

## 2. THE BLOCKS

### B1 — TRUTH: the ruler and the tape  ← **OPEN NOW**

*Why first:* every downstream number is measured with these two instruments.

1. **Canonical benchmark module** `learner/benchmark.py`: SPY total return
   (pinned CRSP VW market from `backend/data/ff_daily_pinned.csv.gz` for
   history; yfinance adjusted SPY for live), QQQ, equal-weight of the same
   PIT universe, cash/T-bill (`RF`), beta-matched, and a strategy-specific
   matched benchmark. One function signature; every receipt writer imports
   it; a test fails if a receipt under `tracker_backtest/` carries a
   `market` field not produced by it. Retire `^GSPC`-as-benchmark
   (`backend/services/backtest.py:95`) and the dead `tickers=["SPY"]` default.
2. **Regenerate `backend/BACKTEST_RESULTS.md`** from the current
   non-overlapping code against the module; README/NEGATIVE_RESULTS §1/CANON
   quote the new numbers with the receipt path.
3. **Rebuild the panel** (`learner/dataset.py`, `scripts/tracker_ibes_backtest.py`):
   - read `ibes__ptgsumu` (unadjusted); keep `meanptg × cfacpr / prc` as a
     cross-check column and print the disagreement rate;
   - merge `crsp__dsedelist.dlret` on `dlstdt`; Shumway fill (−30% NYSE/AMEX,
     −55% NASDAQ) for performance codes with missing `dlret`; stop describing
     `dsf.ret` as delisting-inclusive;
   - verify the dsf pull covers all shrcd 10/11, exchcd 1-3 permnos (or
     re-pull); `ratio ≥ 50` and split-year hygiene move into the dataset;
     SIC 9999 → `UNCLASSIFIED` everywhere;
   - `backend/tests/test_ibes_target_share_basis.py`: remove the xfail
     marker — it must pass green.
4. **Re-issue the four tape receipts** on the clean panel with calendar-time
   overlapping cohorts + Newey-West(h−1) (the engine in
   `scripts/holding_period_policy.py` already does this) and the B4 inference
   stub where available: band_horizon, toxic short (report `−resid` with
   Reg-T capital, never "hedged gross"), revision (over the full PIT hygiene
   universe, both `target_rev_1m` and `net_rev_1m`), holding-period. Each new
   receipt carries `supersedes:`; each old one gets `SUPERSEDED_BY` appended
   in a sidecar, never edited.
5. **Re-derive BAND_PRIOR** from the clean panel. If no band's premium
   survives family-adjusted inference, BAND_PRIOR becomes hygiene only
   (price floor, coverage floor, unreadable-across-split) in
   `learner/prior.py` **and** the live thresholds in
   `aegis-alpha-terminal/alpha/tracker.py` are re-derived from the live
   object (Finnhub unadjusted targets) or set to hygiene-only. Attended.
6. **Manifest the 59 GB**: every ignored WRDS parquet family gets a
   `DATA_MANIFEST.md` row.

**Gate B1 → B2/B4:** benchmark module with tests; share-basis test green;
`dlret` merged with a receipt of the delisting count; four receipts
re-issued; INDEX updated; a one-page `FINDING_*_THE_TAPE_REBUILT.md` with the
before/after table.

### B2 — HOLD: decision and holding integrity (terminal repo)  ← **OPEN NOW, parallel to B1**

*Why:* 84% of round trips close within a session; the thesis is never tested.

1. **Strategy contract fields** on every sealed holding and every
   `state/contracts/*.json`: `expected_horizon_sessions`,
   `min_normal_hold_sessions`, `thesis_expiry`, `hard_falsifiers`,
   `risk_budget_usd`, `emergency_exit_reasons`. The seal refuses a book
   without them.
2. **Exit pass reads the contract** (`alpha/exits.py`): before
   `min_normal_hold` a close is legal only with a typed reason ∈
   {THESIS_INVALIDATED, DATA_ERROR, HARD_RISK_LIMIT, EXECUTION_CORRECTION,
   DEADLINE, EXPLICIT_EVENT_STRATEGY_EXIT}; the −3% stop uses the profile
   width (R3) and counts as HARD_RISK_LIMIT; the +2.5% PEAD target is removed
   from tracker books (it stays on `post_event_drift` where it was measured);
   the drift-window horizon comes from the book, never from `--expiry`.
3. **Re-entry guard sees every exit**: union `protect.stopped_today` with
   today's `brain=="exit" and action=="closed"` ledger rows for the role
   (`alpha/runner.py:1134-1150`). This one change removes the same-day
   re-buy without touching any limit.
4. **Exit reason enum** written to the ledger; `refusal_classes.py` gains
   exit classes.
5. **Regret, nightly** (in `daily_learning_report`): for every closed
   position, actual vs held-to-horizon vs held-to-next-review vs SPY, MAE and
   MFE → PREMATURE_EXIT_REGRET, STOP_REGRET, REENTRY_REGRET; REFUSAL_REGRET
   from a revived counterfactual marker.
6. **Driver taxonomy at seal time**: sector/SIC from the panel (EDGAR
   per-CIK SIC), so the 40% driver cap binds per sector; `UNCLASSIFIED` stays
   for the truly unknown; `utilization.py` and the learning report print the
   BINDING constraint per book.
7. **Data gaps are not decisions**: a clause UNREADABLE for the whole
   universe marks the book DEGRADED — holdings carry forward with a staleness
   flag; unallocated capital defaults to the benchmark, never cash.
8. Fix train already queued: BUR stop-id day salt; R8 clamp units; R10
   `execution_authority` caller; disarm opg arms; mixed-currency market cap;
   mint mirror/arena keys (attended).
9. **Feed the authority**: either ship the corpus generator + sources to
   the Railway image/volume, or (preferred) move catalyst/corpus features to
   the finance-side PotentialUniverse and let the authority seal from a
   DecisionArtifact (B9 finishes this). Until then `requires_catalyst` books
   are DEGRADED, not empty.

**Gate B2 → B9:** five forward sessions with (a) zero same-session closes
without a typed reason, (b) median hold ≥ `min_normal_hold`, (c) regret
decomposition printed nightly with a receipt even when zero, (d) binding
constraint visible per book, (e) fleet deployment ≥ 80% of intent or an
explicit thesis for the remainder.

### B3 — THE LOOP SPEAKS: learning report, autopsy, recall

1. `daily_learning_report`: every CANNOT DETERMINE section gets its input
   (live-equity fallback for the scoreboard, counterfactual marker revived,
   shadow path via env, tracker path); **one** SPY close source (the
   benchmark module); the report is the Personal CIO object's skeleton.
2. **Revive `daily_autopsy` and `investigator_night` on a schedule that emits
   a receipt every night even when empty** (invariant 15). The autopsy's
   second question — the day's biggest idiosyncratic winners/losers across
   the whole market and whether AEGIS generated the name — becomes the
   **opportunity-recall ledger**; misses are typed and queued.
3. `decision_outcomes` write-back readable from the laptop (a GET on the
   authority or a nightly pull from the volume).
4. **Personal CIO daily object v0** = learning report + allocator artifact
   + autopsy, one JSON + one rendered page: portfolio diagnosis; what changed
   overnight; best new opportunities; buy/add/hold/trim/exit with weight,
   horizon, expected return, P(beat), downside, thesis, catalysts,
   falsifiers, disagreements; capital left in benchmark/cash and why;
   yesterday's attribution; what the system learned. Answers "why do I own
   this", "what would make us sell", "where should another $10k go", "what
   did we miss yesterday".

**Gate:** ten consecutive nightly reports with zero CANNOT DETERMINE
sections caused by our own plumbing (a venue lag is allowed and named).

### B4 — INFERENCE: honest statistics for an aggressive search

1. `learner/inference.py` — the one library every receipt calls:
   per-draw persistence; **family max-stat across every (arm, head,
   horizon) cell per seed**; ≥256 independent seeds for anything
   capital-facing (≥64 dev); **Deflated Sharpe Ratio** (N = cells looked at,
   null SR variance from the draws); **Hansen SPA** with a stationary
   bootstrap (3-6 month blocks) on the paired-excess series; **CPCV** with
   purge = horizon, embargo = 1 month, and **PBO** for arm rankings. Every
   family carries a persistent budget charged per cell looked at
   (invariant 16); family IDs are enumerated.
2. Install CUDA torch (`cu128` wheels for the RTX 5060) so null draws are
   cheap; pin `torch.cuda.is_available()` in a smoke test that *skips* on
   CI and *fails* on the laptop.
3. Re-adjudicate learner v2's champion with (1) on the B1 panel; re-issue.
4. **States**: issue the CANNOT DETERMINE receipt from the persistent null;
   design one null that controls the name-path confound (e.g. permute
   feature vectors across names within month while holding each name's label
   sequence fixed, or evaluate on a held-out *time* split against a
   return-matched null). If it cannot be resolved, states are demoted to
   UNVALIDATED in `potential_universe.py` and the allocator plan.
5. Retire `|null t| < 2` everywhere it still gates (grep `shuffled_null`).

**Gate:** no receipt after this block quotes an edge without family-max p,
DSR and PBO; the v2 champion has a re-issued verdict.

### B5 — COMPANYWORLD v1 (reuse first)

1. **Import MARKET-GRAPH-1** (`Aegis module/runs/MARKET-GRAPH-1/edge_instances.parquet`)
   into `backend/data/optimus/graph/companyworld_v1.parquet`: nodes
   company/security (permno), edges competitor/customer/supplier/
   shared_technology/regulatory_exposure/shared_end_market with
   `valid_from` = filing date, `valid_to` = next filing that omits the edge,
   `source`, `evidence_id`, `confidence`, `graph_layer ∈ {FACT, HYPOTHESIS, LEARNED}`.
   An LLM hypothesis is never promoted to FACT without a filing or a
   measured relationship.
2. **Historical permno↔CIK link** from `crsp.ccmxpf_lnkhist` +
   `comp.company.cik` (both on disk) — unblocks the 8-K tape (55.4% → full
   panel) and every EDGAR join.
3. **One 8-K event schema** reconciling `edgar_events.py` (disclosure type +
   materiality), `scenario_bridge.EIGHTK_ITEM_EVENT_TYPE` (mechanism) and the
   tape: keep both fields, one table, availability = acceptance datetime.
4. **Seed exposures for the case companies** as FACT rows with sources:
   XOM→Brent/WTI, Permian, Guyana; MU→DRAM/HBM contract pricing, NVDA
   qualification; MRVL→hyperscaler custom silicon; MSTR→BTC, mNAV, issuance
   capacity; NVDA/AMD→AI capex; SOC→offshore/regulatory; plus commodity and
   crypto nodes. Node types beyond company remain empty until a source
   feeds them — declared, not faked.
5. **First consumers, same commit**: (a) the driver taxonomy at seal time
   (sector + graph cluster) — the B2 fix becomes a graph consumer; (b) a
   **customer-momentum feature** (Cohen-Frazzini 2008: lagged customer
   return → supplier) as a PRODUCT_EXPERIMENT feature on the B1 panel with
   B4 inference; (c) `scenario_bridge.company_role`.
6. Tombstone the 514 placeholder rows in
   `aegis-alpha-terminal/state/causal_graph.jsonl` (append VOID markers;
   never delete) and make the writer refuse the schema example.

**Gate:** graph coverage stat (share of panel permnos with ≥1 FACT edge by
year); customer-momentum receipt with family-adjusted p; driver cap binding
per cluster on the fleet.

### B6 — AUTOPSY FACTORY + MATCHED LOSERS

1. **`WINNER_MATCHED_LOSER_FACTORY_V1`** (named "the largest gap" in five
   handoffs; never built): for each year 2013-2024 on the B1 panel, the top
   and bottom 50 twelve-month idiosyncratic movers (residual to beta×size×
   sector), K = 5 matched controls on (month, sector, size, liquidity,
   coverage, 12-1 momentum, 60d drawdown), and PIT feature deltas at 1/5/21/
   63/126/252 sessions before the move — including graph neighbours' moves,
   8-K events, 13D/G, Form 4, revisions, options where OptionMetrics covers.
   Output: archetype candidates = features whose winner−matched-loser
   difference clears B4 inference in ≥ 2 eras.
2. **Seed cases through the typed autopsy schema**
   (`backend/services/research_gym/autopsy.py`): WBUY, GPRO, MRVL, MU, XOM,
   SOC, ALMS, XHLD, MSTR, NVDA, AMD. XHLD has nothing anywhere — start there.
   Each case: what was observable at 1d/1w/1m/3m/6m, what AEGIS observed,
   missed, rejected; did it buy; why did it sell; held-to-horizon
   counterfactual; matched losers; the archetype that survives.
3. **Opportunity-recall baseline over history**: of each year's top-50
   winners, what share did each existing generator (analyst dislocation,
   tracker, PotentialUniverse, arena) surface beforehand.
4. Evidence Memory write-back: every archetype and every conditional result
   lands in the signal registry as `(strategy, state, era) → posterior`,
   using `arena/trust_router.py`'s estimator re-keyed to strategy; states
   {IDEA, CONDITIONAL, SUPPORTED, SHADOW, FORWARD_SUPPORTED, CAPITAL_ELIGIBLE,
   REGIME_SPECIFIC, DORMANT, COST_KILLED, CAPACITY_LIMITED, DECAYED, REFUTED};
   a single episode can neither promote nor kill.

**Gate:** archetype receipts; recall baseline table; registry rows with
posteriors; the eleven case files.

### B7 — HISTORICAL LLM PORTFOLIO MANAGER (ERA REPLAY v2)

1. T13 → three eras (2025-26 corpus; 2016-19 via Alpaca/Benzinga backfill
   + 8-K ex-99.1; 2010-13 EDGAR-only), cadences {1m, 3m, 6m}, **diary arm**
   (previous diary + previous weights; run with and without), weights
   summing ≤ 1, cost charged at every rebalance, nulls 2 (shuffled dates)
   and 3 (same-day paired), the year/company canary, a second decider family
   (NVIDIA kimi-k3 or HF GLM). Rewriter gpt-5-nano at `reasoning_effort=
   "minimal"` (~$0.03/1k items); one run ≈ $1-5.
2. Grade **rank** (code prices; T13's calibration was negative in every arm)
   and terminal wealth vs the same-era equal-weight basket, per era, never
   pooled. Fantasy arm is the claim; real-anon arm is the memory control.
3. Fantasy **stress exams** (Data Designer pattern): vary one causal fact at
   a time — FDA rejection, sanction, funding withdrawal, supply shock — and
   require the forecast to move the economically correct way.
4. The same encoder runs on today's corpus pre-open (the live bridge),
   feeding PotentialUniverse fields.

**Gate:** a cadence/diary result that holds in all three eras is a finding;
one era is a regime; both are reported.

### B8 — STRATEGY EVOLUTION LAB

1. Extend `PortfolioGenome` (Aegis module) with `parent_ids`, `thesis`,
   `causal_path`, `universe`, `entry`, `exit`, `expected_horizon`,
   `min_normal_hold`, `sizing`, `gross`, `benchmark`, `cost_model`,
   `regime_conditions`, `instrument`, `mutation_history`, `experiments_seen`.
2. LLM agents propose and mutate (naming the closest corpse via
   `lint_prereg`); **code computes every return**; every genome tried is
   recorded. Families: revision, post-event drift, lgbm cross-section,
   customer/supplier momentum, sector-relative revisions, commodity-shock
   propagation, ownership anomalies, event-driven, pairs/stat-arb,
   physical-vs-implied options, combinations.
3. **Development era 2013-2019 with CPCV/PBO; champion frozen; sealed test
   era 2020-2024 opened once per champion; SPA over the whole family.** The
   search may run until it beats SPY TR after cost in development; the
   sealed era is never tuned on.
4. A champion that wins the sealed era starts forward paper under a frozen
   contract with B2's hold fields.

**Gate:** either a champion with family-adjusted p < 0.05 on the sealed era
and forward accrual started, or the honest result "no champion" with the
family size and the best DSR recorded.

### B9 — CAPITAL ALLOCATOR v1 + fleet remap (attended)

1. Objective: expected **log-wealth** with CVaR from quantile heads (B10 or
   bootstrap), sleeve covariance, benchmark uncertainty > 0, cost and
   uncertainty terms, per-personality λ in config; cash requires a thesis;
   benchmark is the parking orbit; leverage only as a ladder 1× → 1.5× → 2×
   on a frozen contract, each rung graded on compound wealth after drawdown.
2. Nightly regret attribution: selection α / β / sizing / timing / cash drag
   / premature exits / stops / refusals / slippage / leverage.
3. **DecisionArtifact → authority seal** (the finance→Railway artery);
   PotentialUniverse `build(scope="observe")` run so OBSERVE_ONLY names
   exist.
4. Fleet remap (six mechanism-specific books, each a frozen contract with
   hold fields): hack1 SPY control + survival layer; hack2 the best
   B1-surviving admission family (revision only if it survives, else
   customer-momentum or a B6 archetype); hack3 learner-v2 re-adjudicated
   shadow → live only after B4; hack4 profit-max ensemble; hack5
   vol/convexity with defined-risk options (index options now available on
   Alpaca) only after B4's states resolution; hack6 market-neutral.

**Gate:** 20 forward sessions with regret decomposition; allocator vs SPY
reported; worst case in dollars printed for the largest admissible book.

### B10 — LEARNER v3 (last, and only on B1 + B4 + B5)

Cross-sectional ranking, expected return + calibrated P(beat), tail /
magnitude via quantile heads (q05/q50/q95) with split-conformal intervals,
graph features from B5; CUDA; `lgbm_clf` mandatory baseline; CPCV; raw and
residual targets (with the prior refit per split); 1/3/6/12 months; keep
only complexity that improves after-cost OOS wealth with DSR.

---

## 3. STANDING LANES (any session may pick up; no gate)

- **M — Optimus memory.** Done 2026-09-04: domain registration + registry
  test, `aegis_verified_state(section=)`, staleness banner, health regex.
  Next, in order: `brain_remember(text, kind)` write tool with a whitelisted
  directory + `brain_reindex()`; git `post-commit` hook in both repos and a
  Claude Code `SessionEnd` hook that runs `refresh_aegis.py`; incremental
  ingest (content-hash skip, loud size-cap skips, source mtime recorded);
  chunk pages at `##` to ≤1,500 tokens and score chunks; SQLite FTS5
  prefilter; re-probe `FLOOR_SCORE` on the 1,015-page corpus; local
  embedding hybrid last.
- **P — Providers.** Add Featherless to `fleet.SECRETS`; delete dead finance
  keys or give them a caller; NVIDIA embeddings for the live funnel; the
  DeepSeek daily cap becomes a per-purpose budget.
- **D — Data buys / pulls (attended):** real borrow fees (only if the B1
  short study revives); OptionMetrics re-join for B9's options books; Alpaca
  news backfill to 2015 for B7.

---

## 4. SERVICES — what AEGIS can honestly offer, minimum version of each

| Audience | Service | Minimum honest version now | Becomes |
|---|---|---|---|
| Murat's capital | the Personal CIO daily object at the aggressive personality | attribution + regret + "why do I own this / what would make us sell" on the paper fleet; benchmark parking; no alpha claim | live capital after B9's gate and a CAPITAL_CANDIDATE review |
| Public open-source users | the same object run at *their* utility on free data (yfinance, EDGAR, Finnhub free) | v0 = explain and attribute: holdings diagnosis, benchmark-relative attribution, catalysts, falsifiers, exposure map from CompanyWorld FACT edges | recommendations once a sealed-era champion exists |
| HKU paper | a methods paper | (i) the fantasy-transposition blind test for LLM reading vs memorisation (T13, B7) — novel and defensible; (ii) the share-basis defect as a cautionary result on analyst-target research; (iii) the matched-loser factory | (iv) an exclusion/selection result only if it survives the clean panel |
| Researchers | published tapes | the EDGAR 8-K item tape (PIT on acceptance clock) + the sealed prediction ledger + the CompanyWorld FACT layer | — |

---

## 5. WHAT DOES NOT CHANGE

PIT discipline · frozen information states · realistic costs · immutable
policy versions · outcome provenance · no training on future information ·
**no LLM authority over real capital** · no backfilled forward evidence · no
mutation of seeded book histories · sealed receipts immutable, addenda in new
files · the ledger tear is evidence · three licences · EXPLORE DIRTY, PROMOTE
CLEAN · a global negative does not answer a conditional question.

---

## 6. BLOCK STATUS (update in place; this table is the roadmap's state)

| Block | Status | Gate evidence |
|---|---|---|
| B0 review | DONE 2026-09-04 | `REVIEW_2026-09-04_FABLE51_VERDICTS.md` |
| B0v verification | DONE 2026-09-04 | `VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md` — 14 numbers re-derived (11 exact), 6 claims overstated, 3 mis-attributions corrected, 1 conclusion withdrawn (§4: the corrected toxic band is a sub-$5 cell that flips sign at a $5 floor). Roadmap adopted unchanged; B1 narrowed in three places |
| B1 truth | **DONE 2026-09-05 — gate PASS** (§5 attended) | `BUILD_B1_2026-09-05.md` (scoreboard + gate checklist + 8 attackable claims). §1 `learner/benchmark.py` + 21 tests, `^GSPC` retired. §2 BACKTEST_RESULTS **+28.3% net vs +114.8%** (was +250.9/+740.0); void pair corrected at the point of use in all 9 docs. §3 panel on `ibes__ptgsumu` + `dlret`, schema `learner-train-table-2`, **`toxic_ge_5` 26,199 -> 2,123**, `xfail` now a plain pass. §4 four receipts re-issued with sidecars: **BH-FDR survivors 8 -> 0**, toxic short **+76.63 -> -29.25%/yr** on Reg-T, revision champion **TW 3.743 -> 1.284**, **no holding-period arm positive at 25bps** (max t in a 268-cell family +1.533). §5 ATTENDED. §6 **58.52 GiB / 84 families manifested; 14.25 GiB duplicate**. Suite 6377+7 green. `FINDING_2026-09-04_THE_TAPE_REBUILT.md` |
| B2 hold | **DONE 2026-09-05 (§1-6) — awaiting Murat's Monday push + deploy** | Terminal `lab/night-2026-09-05` `1cea12d`, **74 suites / 3,368 checks ALL PASS**; runbook `docs/RUNBOOK_2026-09-08_REARM.md` (terminal repo). §1 `alpha/contract.py`: six fields per book (horizon 21 / min hold 10 on the tracker books), sealed inside `content_sha256` on the block AND every holding; `prediction_book.seal` REFUSES a book without one. §2 `exits.py` obeys it — before the minimum hold only a typed reason closes (DEADLINE / EXECUTION_CORRECTION / HARD_RISK_LIMIT / DATA_ERROR / THESIS_INVALIDATED / EXPLICIT_EVENT_STRATEGY_EXIT); the flat 3% stop becomes the PROFILE width; the +2.5% target is per-contract and the tracker books declare NONE; the horizon comes from the contract, never from `--expiry`. §3 the re-entry guard is unioned with today's ledger exits (it saw one of four exit routes). §4 `deadline_liquidation_due` fires only ON the deadline's ET date and the mandate end moved to 2027-12-31 (`AAT_MANDATE_END_UTC`); `window_universe` follows it or every print is TOO_LATE. §5 `Mandate.allow_short` is READ (no naked shorts; the hedged pair untouched); a close that fails after its stop was cancelled RE-PLACES the stop; the claimed move in dollars is compared with the stop in dollars on every admission. **The 3:1 floor is RECORDED everywhere and BINDS on naked shorts only** — applied to every book it refuses 100% of what the tracker books select (their `exp_return` is 1-3% against a 6-8% stop = 0.2-0.4:1), which would empty the accounts this block exists to fill; the census is now on every admission and binding it further is attended. §6 `scripts/utilization` prints ARMED/DISARMED + the binding constraint per role; the daily learning report gains (c2) HOLDING DISCIPLINE (exit-reason census + same-session round-trip %) and (c3) ENTRY AUTHORITY |
| B3 loop | **§1-§3 DONE 2026-09-06 (terminal repo, local) — and the dry run found the thing that would have gone wrong on Monday** | `BUILD_CONTINUATION_2026-09-06_DETAIL.md` §2d. Terminal `5e27070`, `c253ede`, `c01043d`, `d28742b`. **§1** every refusal on the daily learning report now carries `cause`: PLUMBING vs NO_DATA_YET, header prints `REFUSALS: n OUR PLUMBING | m no data yet`; wired live-equity fallback (only when the account's session day IS the report day — today's equity can never be stamped on an earlier day, pinned), counterfactual marker, `AEGIS_SHADOW_DIR` + 2 fallbacks, tracker path, and ONE SPY source (`alpha/spy.py`). **Measured: the counterfactual marker last wrote 2026-08-28 — EIGHT DAYS DEAD**, reported until now as 'either nothing was refused or the marker did not run'. Also found: the test suite was writing into TWO PRODUCTION LEDGERS. **§2** `daily_autopsy` writes `state/autopsy/<day>.json` on EVERY exit path incl. empty and refused, day derived from `alpha.exits.session_day()`; new `alpha/recall.py` types every miss NOT_OBSERVED / GENERATED_NOT_RANKED / RANKED_NOT_BOUGHT / BOUGHT_SOLD_EARLY and reports winner_recall BESIDE loser_avoidance. **The venue screener called SEVEN names 'the whole market'** (missing NX +22.2%, GWRE −19.9%, LULU −17.4%, FICO −16.7%, PATH −16.6%); the union gives 23, of which **16 were NOT_GENERATED — not one of the day's sixteen biggest movers was on the candidate list either way**. Recall status CANNOT DETERMINE because judging day had no seal — the guard refusing to blame a stage. **§3 MONDAY DRY RUN** (vintage 2026-09-02, both band modes, nothing sealed/ordered/published): RETURNS mode hack3 **10** @83% gross (worst case −6.64%), hack4 **5** @50% (−3.00%), hack6 **15** @90% (−2.70%); **HYGIENE_ONLY mode hack3 10→5 with an ENTIRELY DIFFERENT FIVE, hack4 5→5, hack6 15→0**. **`exp_return` is computed FROM the band's return constants, so retiring them (decision B.1 §4a) makes `exp_return` non-positive for 799 of 810 candidates — hygiene-only is not a loosening, it is the TIGHTEST rule in the stack, and implementing 4a literally on Monday arms three books and fills one and a half.** ATTENDED. Binding constraint reported as `only` (fails NOTHING ELSE), not first-fired — they diverge by an order of magnitude. Entry authority: hack1 DISARMED, **hack2/3/4/5/6 ARMED**; two of four disarms are RAILWAY VARIABLES and invisible locally, and the block refuses to guess. **hack2 is ARMED and is NOT a tracker book** — `contract.defaults_for` branches on `TRACKER_BOOKS=(hack3,hack4,hack6)` so hack2 gets EVENT defaults: horizon 3, min hold 0, profit target 2.5% — the exact churn the min-hold build exists to stop. Found independently by the §2f agent. NOT FIXED: Murat's call. Printout attached to terminal `docs/RUNBOOK_2026-09-08_REARM.md`; receipts `B3_1_*`, `B3_1b_*`, `B3_2_*`, `B3_3_*` |
| B4 inference | **§1 DONE 2026-09-05** (library); the >=256-seed model null deferred with its cost stated | `learner/inference.py` + 16 tests on a PLANTED world and a NULL world: Deflated Sharpe (N = cells looked at, null SR sd from draws), Hansen SPA with a stationary bootstrap (mean block 4 periods, consistent/lower/upper), CSCV/PBO, CPCV splits with purge+embargo, and per-draw persistence (`DrawStore`) so a family-max p can be recomputed over a DIFFERENT cell set without re-running the nulls. Finance `11be9a4` |
| B5 graph | **§1 PARTIAL 2026-09-06 — edges bought, and the scope excuse is answered NEGATIVELY** | `BUILD_CONTINUATION_2026-09-06_DETAIL.md` §2a. `backend/data/optimus/graph/companyworld_v1.parquet`: **2,020 edges, 945 permnos, 1999-2011**, 93.9% quote-verified, resolution 31.1% (the residue is real — 4,138 of 6,753 mentions are NOT IN CRSP at the date; the supply chain is mostly not US-listed). Panel coverage **945 of 8,981** names against MARKET-GRAPH-1's 386. W4 re-run on the long panel with the floors on the **training** universe (925,757 → 530,447 rows): all three arms **CANNOT DETERMINE (underpowered)**, and the direction is the finding — customer momentum falls from FM t **1.447** on MARKET-GRAPH-1's own 2014-24 tape to **t 0.297** on the never-seen 1999-2013 tape (pooled 0.989); family size 9, Sidak family-max p 0.96/0.74/0.97, PBO 0.957 OVERFIT / 0.343 FRAGILE / 0.514 OVERFIT. **More tape made it weaker.** §2 (permno↔CIK link) done as a by-product: 30,638 of 51,001 filings linked, 60.1%. §3-§5 not started. Cost **$2.12** of a $10 cap. Receipts `W4b_*.json`, `S3_graph_receipt_provenance_run01.json` |
| B6 autopsy | **§4 DONE 2026-09-06 (evidence memory → registry); the autopsy proper is B3's** | `BUILD_CONTINUATION_2026-09-06_DETAIL.md` §2e. `backend/data/signal_registry.yaml` gains `conditional_evidence:` — **12 rows, 3 families, 4 cells × 4 eras**, `{n, sharpe, dsr, spa_p, pbo, verdict}`, idempotent (sha `3224a851…` on three runs), everything outside its two markers byte-identical, CRLF preserved. **Inert for the PM, proved not asserted**: `Registry.__dataclass_fields__` has five keys and the guard greps every `.py` while asserting >500 files were actually scanned. `weekend-W7-matched-loser` is EXCLUDED as SUPERSEDED and the count is named — **9 of the memory's 12 SUPPORTED cells are in it**, and all 9 survive the row-level rule because the boundary predates the corrected re-runs. Superseded-cannot-vote proved RED (5 of 11 tests fail on the reverted code; file restored byte-identical). Three further silent holes closed, incl. `before_utc: "2026-09-05"` excluding **nothing** on a lexicographic compare. Receipt `B6_evidence_to_registry_run01.json`; tests 11 + 32 |
| B7 era replay v2 | **§1-§2 DONE 2026-09-06 — the decide step ran and the verdict is NOISE** | `BUILD_CONTINUATION_2026-09-06_DETAIL.md` §2b, `docs/FINDING_2026-09-06_ERA_REPLAY_V2.md`, `scripts/era_replay_v2.py`. The prompt's claim that "Friday's L10 built the scaffolding" is FALSE — L10 was never run; v1 lives in the SIBLING repo (`alpha/transpose.py`) and v2's diary arm, nulls 2-3 and coded canary existed nowhere. **192 windows** of 2016-01..2019-12 (the whole era), 8 names/window, top-3 held, 10 bps on realised turnover, $3m/day + $5 floors applied when the window is BUILT, `n_effective` = **48 month blocks**, benchmark = the EW basket of the SAME eight names in the SAME month, **rank graded only**. IC / net-vs-EW %/mo / TW ratio: fantasy-nodiary −0.031 / −0.393 / 0.799 · fantasy-diary −0.026 / **−0.127** / 0.907 · realanon-nodiary −0.046 / −0.353 / 0.813 · realanon-diary −0.053 / −0.530 / 0.752. Family 4, **family-max p 0.729, nothing survives BH-FDR**; DSR **0.081**, SPA p **1.00**, PBO 0.386; **MDE 8.75%/yr**, so NOISE means *not detectable on four years*, not absent; three-era table CANNOT DETERMINE (one era ran). **A random ranking already loses ~−0.20%/mo** (a top-3-of-8 book pays turnover the basket does not), so null 1 is the real test: p 0.72 / 0.41 / 0.68 / 0.85 — three arms rank WORSE than chance. **The blind HELD: 0 of 768 decisions named the true year**; blinded, the model assumes it is NOW (190 of 243 guesses said 2023, 53 said 2024, none 2016-2019); **the diary SUPPRESSES the canary** (191/192 no-guess with it vs 93 and 50 without) ⇒ ask the canary in a SEPARATE call. **REFUSED loudly:** the EDGAR 8-K item tape — its manifest resolves the universe through `company_tickers.json` = CURRENT registrants, so 8-K presence in 2016-19 correlates with survival to 2026, a forward-looking leak into the prompt. Three silent defects caught: `deepseek-chat` abbreviates "Company A" to "A" (lost EVERY real-anon window while the table still printed); `gpt-5-nano` keys its JSON on the whole heading line (lost 11 of 20 bundles); and **the magnitude gate counted field names as data**, scoring a faithful rewrite 0% — retracted in-session, true preservation 97.9%/98.4%, arm gap 0.005. §3-§4 not started. Cost **$0.4817** of $5.00. Commit `65db6e9` |
| B8 evolution | blocked on B1, B4, B6 | — |
| B9 allocator | blocked on B2, B4 | — |
| B10 learner v3 | **NOT EARNED 2026-09-06 — the neural loop is stopped** | `BUILD_CONTINUATION_2026-09-06_DETAIL.md` §2c. Decision rule declared and hashed BEFORE the run (`W3b_neural_floored_run01_declaration.json`, sha `428a7148…`), judged on the **seed-mean ensemble** and never the best cell. Floor on the **TRAINING** universe (530,447 of 925,757 rows); proof it bound the fit — the grading floor then removed **0 of 454,708** gradeable rows and every graded book has a median holding at $17-29m/day and $27-41 a share. 251 months at 10 bps against market TW 14.378: `nn_pre_causal` ensemble **49.01** (+8.14%/yr, t 2.243), `nn` ensemble 24.13, **`lgbm` 36.24**, `lgbm_clf` 22.61. `nn_pre_causal` clears clauses (a), (c), (d) and **FAILS (b)**: DSR vs `lgbm_clf` **0.1726** against the 0.95 bar, SPA p 0.108, PBO 0.343, paired t 1.24, and only +0.83%/yr over `lgbm`. **No champion frozen, no shadow accrual, best cell (TW 105.0, DSR 0.862) explicitly NOT promoted** — it is 2× the median seed and not choosable in advance. **And the incumbent is five months too:** 83.6% of `lgbm_clf`'s 251-month excess is five months and without them it is BEHIND the market (7.78 vs 8.18). $0.00 LLM. Receipt `W3b_neural_floored_run01.json` |
| W weekend lab 2026-09-06 | **W0-W12 DONE 2026-09-06 — the answer is NO, and three of the lab's own findings were retracted by its own review** | `BUILD_WEEKEND_LAB_2026-09-06.md` + `REVIEW_2026-09-06_CODE.md` + `REVIEW_2026-09-06_ATTACK_ON_THE_WEEKEND.md`; branch `lab/weekend-2026-09-06` (**NOT PUSHED**). **W1** long panel `learner-train-table-3`, **925,757 name-months / 310 months** (vs 605,410 / 143); early-era share-basis gate now PROVES its own sensitivity every run by injecting the 09-04 defect (real 0.9783 vs injected 0.8545). **W2** the 32-cell grid on 26 years: **DSR 0.197 -> 0.293** against a 0.95 bar, best cell +11.45%/yr at **t 1.43**, MDE **16.3%/yr** — tripling the out-of-sample months changed no verdict. All 16 lgbm cells positive, **all 16 ridge cells NEGATIVE**. Adding W4/W5/W6's 21 features to the learner: **+0.016%/mo, t 0.03** (redundant; **-0.555%/mo at 3m**). **W5** two options coefficients survive controls (HAC t +4.15, -5.37) and **W5b's 24 book cells all lose GROSS** — the effect lives in decile 1. **W12** as a dollar-neutral long-short it is +4.91%/yr t 2.40 at 10bps/50bps borrow and dead at 25bps or 500bps borrow, on a short leg trading $2.2m/day. **W7** archetype corrected after a **LEAK** (the control pool excluded future losers): 'thin for its size' Holm 0.000178 -> **0.158**, the surviving idea is analyst REVISIONS. **W6b** S28's liquidity band replicates as a **FLOOR, not a band**. **W4** supply-chain momentum CANNOT DETERMINE (11 of 26 years, median 'customer average' = ONE name). **W8** market states NOISE under the only null defined for them. **W3** neural 561x is **93.7% unbuyable** ($3m/day + $5 floor -> 36.3x, t 1.98) and never beats lgbm after the family; pre-training is the only variant that helped, the q90 head loses money, 4x width does nothing. **Verdict census 83 receipts: 0 NOVEL.** LLM spend **$0.00**; no order, seal, deploy or Railway change. Suite 6,552 green |
| R review 2026-09-06 | DONE — `REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md`: claim 5 REFUTED as timing evidence (top-5 share ≥83.55% arises in 31-40% of pure-noise draws at that Sharpe), claim 4's consequence reversed (freeze `nn_pre_causal` as a zero-capital SHADOW; research loop stays stopped); next queue: beta-matched re-grade of both incumbents, DeepSeek price table from provider balance, era-replay HOLD arm + second era, counterparty-bias check, receipt provenance rule | receipts under `continuation_2026-09-06/` |
| **L labor day lab 2026-09-07** | **A1-A4 / B1-B3 / C1-C4 / D1-D3 DONE 2026-09-06 — RESULT IMPROVEMENT: NONE under the research ruler; the MACHINE moved** | `BUILD_LABOR_DAY_LAB_2026-09-07.md`; finance `7407a1d`,`011c29b`,`dd4b6d9`,`c1c5cfc`,`8d5e2b9`,`727ecbd`,`b523590`,`8c1495c`,`c6dd565`,`08fba68`; terminal `3a6a67c`,`0bcc4b6`,`1034c29`,`bf55c32`,`1f39189`. **A1** one grader, two selectors: nn_pre_causal − lgbm_clf beta-matched **+2.827%/yr t 0.748** over 251 months, holdings overlap **8.32 of 50**, excess corr **0.255** — different errors, and family 6 min p 0.1245, nothing survives Holm. Both nightly vintages absent (lgbm_clf REFUSED on schema `fd48dbc7` vs `7f01cbe4`). **A2** the cadence question, asked for the first time: monthly minus frozen-once **+5.751pp** beta-matched at 10 bps (+5.388pp at 25), TW 27.17 vs 6.77 — **the information is NOT static** — but family 8, min p 0.05703, best Holm 0.456. A reproduction gate ran FIRST: annual reproduces W3b's `lgbm_clf` over **454,708 rows at max dev 3e-08**. **A3** 32-cell grid pooled PBO 0.0143, **but at 1m — the horizon the books trade — PBO 0.5286 = AT THE COIN FLIP**; neural family: an **individual SEED wins 15 of 15 CPCV partitions**, never the seed-mean (PBO 0.514 at 10 bps = OVERFIT), and 18 of 40 cells are unreconstructible (stage parquets gone). **A4** hysteresis is the largest lever in lane A — **19 of 20 rungs beat the no-hysteresis monthly control**; best cell `nn_pre_causal hold_k=150 10bps` +8.139%/yr t 2.393 vs MDE 6.80 = SEPARATED FROM ZERO, family 40, family-max p 0.7794, **0 survive Holm**; lgbm_clf's +5.073pp at 25 bps is **turnover** (0.904→0.527, cost line 5.34→3.16%/yr). **B1** a synthetic known-answer battery for the WHOLE machine (dataset→learner→inference→evidence memory→allocator): recovers linear/regime/graph at Holm p 0.0000 with the right sign, returns **NOISE + REFUTED** on the null, allocator weight **0.0** on the null world, **ALL_PASS** — and caught two defects: `verdict_from` has **no word between NOVEL and NOISE** (a real planted edge at Holm 0.0154 is called NOISE) and **`learner/evaluate.ERAS` is hard-coded 2016-2024**, grading a 1999-2024 panel on nine years without a refusal. **B2** fantasy stress exams: **40 of 40 pairs monotone on all three fields, three independent draws**, mean |Δp_up| 0.370 — against a **canary rate of 0.125**, which is what the share has to be read against. **B3** bridge coverage: maps-to-nothing **40.0% → 26.7%** under the ownership standard, **40.0% UNCHANGED** under a panel-overlap standard (*companyworld_v1 gives the concept, not the dates*); grades identical by construction, and **18 of 20 scenarios moved because the PANEL was rebuilt** — a 09-04 receipt no longer reproduces. **C1** fault injection, 14 faults / 53 checks: **12 PASS, five defects fixed before the venue found them** (stop-id day salt for the BUR 422, seal `content_sha256` verified before trading, the sealed contract now READ by the runner, torn-ledger refusal of EXECUTION_CORRECTION, stop re-placed after a failed close); **1 FAIL reported — every ET gate reads the LOCAL clock** (+20 min disarms the opening range, −20 min manufactures a refusal, the curfew fires 20 min early), and `refusal_classes` has **no VENUE_REJECTED state**. **C2** 1,200 synthetic paths × 6 profiles: **0 violations** on all three assertions; hack2's contract IS the EVENT defaults field-for-field and the min-hold rule is **vacuous on hack1/2/5**. **C3** 19 fragility findings, 2 fixed — `spend()` returned a truthy dict of ZEROS for a ledger it never read (**re-authorising the whole LLM ceiling at the moment the accounting breaks**), and the provenance checker counted a file it could not find as one it opened. **C4** 0 unadjudicated key-shaped hits in 996 files since 09-01; seal-authority **GET/HEAD only, POST→501, books dir only**, verified with no network call; `.env.bak.*` safe in both repos. **D1** finance **16 ok / 4 FAIL / 1 CANNOT DETERMINE of 21**, terminal **16 ok of 16**, every failure carrying a CLASS (auth/quota/network/entitlement/absent/cannot_determine); `scripts/connection_check.py` in both repos, adoptable by `fleet_health`. **D2** 44 credentials, **0 dead weight**, 4 correctly refused (the revoked mirror/arena pair), 6 proved the SAME object across repos by fingerprint — after a **near-miss that called eleven live fleet keys DEAD** because `alpha/config.py` builds their names at runtime; fixed with a derived rule, not an exemption list. **D3** the Tuesday audit: the deploy arms hack2..hack6, **`AAT_MANAGE_ONLY=1` is read by NOTHING in the repo** (appendix B.2's hold-back is inert) and `AAT_MANDATE_END_UTC` is set on **no service at all**; runbook appendix C. **LLM $0.03** of a $6.00 cap (200 DeepSeek calls, all in B2). Finance suite **6,869 passed / 14 skipped / 122 deselected in 487.04s**; terminal **80 suites / 3,669 checks ALL PASS**. Nothing pushed, sealed, ordered, deployed or changed on Railway |
| **G growth book (amendment 2026-09-07)** | **G1-G7 DONE 2026-09-06 — the sealed era is open, the number is a LOADING, and the honest sentence has beta in front of it** | `BUILD_GROWTH_BOOK_2026-09-07.md`; finance `a2e0ea2`,`c906638`,`dd436b2`,`46c08d6`,`cf9b95e`,`0dcf72e`. Declaration sha **`0397b9bfae7d53c1…`**, written and hashed BEFORE the first evaluation (44 genomes x 2 cost rates = 88 cells). **G2** generation 0 on 2004-01..2015-12 (144 months): leader `lgbm_clf|dd` 10bps **beta 0.776, leverage-neutral TW 4.431** vs SPY 2.0935; family-min raw p 0.0146, **best Holm 1.0**, best BH-FDR 0.5098, best DSR 0.278, **PBO 0.6429 = SELECTION_IS_OVERFIT**. Every verdict names WHICH bar failed (B1's `verdict_from` gap). Found in its own loader: the W3b stage join was POSITIONAL where `_row` is the original panel LABEL — 57.3% of labels existed (exactly the floor's `share_kept`) so every prediction column looked populated **while sitting on the wrong rows**, and the only tell was a non-null `lgbm_clf` in 2002-2003, before the first test year of the fit that produced it. Joins by label now, and refuses on either symptom. **G3** 20 DeepSeek mutations at **$0.0132** of a $3 cap, each naming a REJECTED/PERVERSE corpse from the registry with a >=5-word distinct claim (`scripts/lint_prereg.py` is named in a docstring and **does not exist**; `research_daemon.assert_distinct_from_corpses` applied directly instead). Family 88 -> 128, best child `m06_lgbm_clf|dd` beta 0.663 LN-TW 4.789. **The proposer is NOT deterministic at temperature 0.0** — three calls, three proposal sets; round 1 was 20-of-20 REFUSED by an interface defect (parents named by CELL id, validator matches GENOME id) and round 2's HIGHER leader (5.4803) is recorded and **not claimed**, because choosing among draws by score is selection. `--replay` reproduces the recorded round at $0.00. **G4** champion `m12_quality_mom|dd` frozen (sha `39ab3224c1a12e14…`) BEFORE the open, chosen at 25 bps because the claim is made at 25 bps. **`sealed_era_openings: 1`**, read back from an append-only ledger; `open_sealed_window` logs ONE line for all four legs of the comparison, because an opening is the act of LOOKING and not a call to a slicing function. **The sentence: beta 0.6681 (intercept +4.907%/yr, HAC t 0.968): on 2016-2024, unseen in development, the book returned 3.6684x vs SPY TR 3.6707x after 25 bps, at maxDD -29.66% vs SPY's -30.99%; SIZED TO THE SAME DRAWDOWN BUDGET it runs 1.3027x for 4.6616x against levered SPY's 1.2471x for 4.4823x. Leverage-neutral TW 3.6044 — BELOW SPY.** Amendment 5 gate **NOT MET**: the wealth condition, the constraints and 2-of-3 development eras pass; **DSR 0.0046 over 128 cells** and **PBO 0.6429** fail. The gate itself was CORRECTED after the numbers were visible (it compared an unlevered book to a levered benchmark) — recorded on the receipt, verdict unchanged, sealed era NOT re-opened. **G5** `learner/growth_sizer.py`: walk-forward quantile GRU on 11 regime features, quarter-Kelly, 8 seeds, CUDA (RTX 5060 sm_120, cu128, base interpreter). At equal drawdown on 202 development months: flat 1x **TW 5.6264**, Moreira-Muir 3.7599, **NN seed-mean 1.0546**, NN DSR 0.0073. **NN sizing loses to the baseline and BOTH lose to doing nothing.** Seed spread 0.7275 / 1.5789 / 5.7383 — eightfold on identical data, seed-mean BELOW the median seed (A3's finding in a second family). `MATURED = False`; the baseline trades, the NN stays a shadow. **G6** `docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md` — frozen recipe, B2 hold fields (horizon 21, min hold 10), five-term nightly attribution, and the ladder in dollars on $100k: **1.0x -$46,882 (P(lose half) 0.232) · 1.5x -$65,435 (0.797) · 2.0x -$78,293 (0.985)**. **The 2x rung is REFUSED by the declaration** (worst month -59.6% past the -40% floor); the real ceiling is the 1.3027x admissible size. Recommendation: **rung 1x or decline**. NOTHING ENABLED. **G7** the forward lanes under the product ruler, 7 readable of 16: conservative-atr is the ONLY positive raw excess, **+0.144pp at beta 0.039** with maxDD -1.5% vs SPY -3.4% — it sat out a window in which SPY rose ~2%, it did not out-select it; `mirror` and `conviction` are the only lanes with real beta and both LOST (-22.1pp, -7.7pp) at -24.7% and -21.3% drawdowns. **And the beta column is biased toward zero: R2 vs SPY is 0.0015-0.05 on all seven and Dimson lead/lag says why — `conviction` loads **0.6072** on today's market and **1.3990** on YESTERDAY's (joint Dimson OLS; Dimson sum 1.9313, lagged univariate 1.4259, OLS beta 0.7163 - corrected 2026-09-07 from a rounded 0.66 / 1.50 that matched no field of the receipt). The lane NAV is marked on STALE PRICES, and a stale mark HIDES beta.** hack1-6 CANNOT DETERMINE at 4 observations — account AGE (genesis 2026-08-28), not readability; `state/learning_report` was NOT merged because its clock disagrees with the benchmark receipt's by a day and stitching them would manufacture a return out of a timezone bug. **Also fixed (queued from lane B1):** `evaluate.grade_by_era` DERIVES its era grid or REFUSES — a 1999-2024 panel put 65.38% of its rows in no bucket and said nothing; `long_eras()` derives the grid from `long_panel.ERAS`, the constant did not move, and the 2016-2024 numbers are proved byte-identical by a test carrying a verbatim copy of the pre-fix loop. **LLM $0.0132** of a $3 cap ($0.00066 per gradeable cell); zero other network calls (SPY pinned, RF pinned, predictions from stage parquets). **97 new tests**; finance suite **6,984 passed / 14 skipped / 122 deselected in 541.58s**. Nothing pushed, sealed, ordered, deployed or changed on Railway |
| **Cb §1 beta-matched re-grade** | **DONE 2026-09-05 — the answer is LOADING, and the comparison ladder is re-based** | `BUILD_CONTINUATION_2026-09-06b.md`; `C1_beta_matched_regrade_run01.json`. `lgbm_clf` beta **1.1782** (t(beta-1) 2.03 HAC): +3.393%/yr t 1.225 raw becomes **+1.126%/yr t 0.349** beta-matched at 10bps and **-2.074%/yr** at 25bps. `lgbm_raw` beta 1.3918: +2.33% / -0.80%. `nn_pre_causal` beta **1.3294** (t(beta-1) 4.24): the **t 2.243** W3b reported becomes **+3.952%/yr t 1.095**, and +1.053% t 0.292 at 25bps. **Three of six books lose to their own leverage on terminal wealth.** A reproduction gate ran BEFORE anything was computed — the stage parquets were gone, the fit was redone, universe fingerprint `616fa0a5` MATCHES, and all six cells reproduce every field of W3b's `cells` block exactly. `rf` is compounded over each book month's OWN holding window `(entry_date, mat_date_1m]`: the row labelled 2020-02 is the book entered 02-21 and held into the -33.3% March, and a calendar-month rf would have been the wrong leg while `benchmark.beta_matched` silently `fillna(0)`'d it. **Fable's claim 5 REPRODUCES**: 20,000 draws at each series' own moments put lgbm_clf's 0.8355 top-5 share inside **27.1% (normal) / 35.5% (t4)** of pure noise, 30.5%/39.7% conditional on a positive total. Under the beta-matched leg the top-5 share stops being a share for both LightGBM books (2.07, 1.82; both negative without their five best months); `nn_pre_causal` 0.457. Family **40** (W3b's `cells_looked_at`, where the selection happened), SPA family-max p 0.2794, DSR 0.0019-0.1497, Holm 0.821-1.00, MDE 5.38-8.22%/yr, three-era table on every cell. **`nn_pre_causal` is UNDERPOWERED, not NOISE**: t 1.095 against MDE 6.86%/yr, positive at both cost rates and in 3 of 3 eras. 251 months cannot separate it from zero |
| **Cb §2 shadow freeze** | **FROZEN 2026-09-05 — zero capital, accruing** | `C2_nn_pre_causal_shadow_freeze_run01.json`. Registry row `neural_pre_causal_ensemble_v1`, grade **SHADOW**, role PICKER, `allowed_in_pm false`, `first_grade_date 2026-09-05`, contract `nn_pre_causal_shadow_v1` sha `16e7d439…`, rule hash `428a7148…`. The frozen object is the **RECIPE, not a model file** — `run_neural` produces walk-forward OOS predictions over 21 folds, so there is no single object to persist and persisting the last fold would be a different experiment. `verify_contract()` compares `learner.neural_long`'s **live** constants against the frozen ones, so a module edit is DETECTED while the contract file stays byte-identical (a file-hash check alone cannot see it). Book **monthly**, receipt **nightly**: the tracker day file supplies `SHADOW_MAPPABLE`'s 14 features and this arm reads 50, so a night with no new month writes a heartbeat rather than a book from a median-imputed third of the inputs. The `SHADOW` grade carries three refusals **proved red** (no `first_grade_date`; no `contract_sha256`; `allowed_in_pm true`) and is deliberately NOT in `NEVER_PICKS` — a shadow is alive, and grouping it with the corpses makes the graduation queue and the graveyard the same list. **Incidental, not caused here: `lgbm_clf`'s daily shadow is REFUSED** on a schema hash mismatch (sealed `fd48dbc7`, current `7f01cbe4`); coverage is fine at 2947/3056, so the champion is stale. Retraining is attended and was not done |
| **Cb §3 DeepSeek price** | **CORRECTED FROM THE BALANCE 2026-09-05** | `C3_deepseek_price_derivation_run01.json`, `config.LLM_PRICE_DERIVATION`. `deepseek-v4-flash` (+ both aliases) `{in 0.14, out 0.28}` -> **`{in 0.169413, out 1.284835}`**; `LLM_PRICE_AS_OF 2026-09-05`. out/in is **7.58**, not the 2:1 the table assumed. **A scalar multiple is REFUTED**: W1 (08-24 -> 09-05, $10.63, 4,471 calls) needs **3.614x** the old table and W2 (the 25-minute extraction window, $3.98, 4,099 calls) needs **1.813x** — spread 1.99x, condition number 2.579, residual 1.8e-15. **S4's '1.79-1.81x' was W2 read alone.** The SHAPE was wrong, not the level: input 1.21x, output 4.59x. Table-wrong vs ledger-incomplete decided by proportionality — the gap tracks OUTPUT TOKENS (per-Mtok-out spread **1.24x**) and not calls (3.95x), total tokens (4.51x) or input tokens (9.11x); missing rows lose whole CALLS and would show a constant gap per call. Verdict `TABLE_IS_WRONG_OUTPUT_LEG`. `cached_in` and `deepseek-v4-pro` are **SCALED, NOT MEASURED** and say so (two windows cannot identify three legs; zero v4-pro rows in 70,664 ledger lines). Anthropic rows untouched. The dollar gate binds at real dollars with no further change (`require -> spend -> row_cost -> price_call` reads the live table, pinned). **History is NOT rewritten** — `llm_calls.jsonl` is byte-identical and every row keeps its `cost_usd` and `pricing_as_of`; `reprice()` is the audit helper. Open and recorded: repricing the whole ledger implies $97.61 lifetime against $27.41 at the old table, most of it before the first balance reading, and we hold no top-up history |
| **Cb §4 era-replay HOLD** | **VERDICT UNCHANGED (NOISE) — and the review's diagnosis was wrong** | `C4_era_replay_hold_run01.json`, `C4b_era2_window_build_dryrun.json`, declaration `C4_hold_rule_declaration.json` (sha `e5e176a3…`, written BEFORE the grade; `grade()` refuses without it). 768/768 cached decisions re-graded, **zero wire calls, $0.00**; the no-hold re-grade reproduces the sealed L10 receipt IDENTICALLY on all four arms across 12 headline keys. Three of four hold cells are **byte-identical** to their parents; the fourth moved by ONE held name across 192 windows. Family 8: family-min p 0.173, **family-max 0.859, nothing survives BH-FDR** (adjusted >= 0.432), SPA p 1.0, PBO 0.286, DSR 0.0024-0.0507, MDE 8.50-9.19%/yr on 48 month blocks. **Turnover 0.9965 was NEVER rank churn.** The WINDOW BUILD redraws the 8-name bundle from ~2,700 eligible permnos every month: **8 of 1,504 name-slots repeat across 188 transitions, a 0.53% repeat rate.** Hysteresis cannot hold a name that is not on next month's menu. Largest cost saving anywhere **0.34 bps/month**, and of the one cell that moved, 0.00034pp is cost and 0.0589pp is a different name held once. Three-era table **CANNOT DETERMINE BY CONSTRUCTION** (2016-19 only; the other eras' decisions do not exist). **2010-13 from EDGAR only: CANNOT BUILD** — `filing_date_min` is 2013-01-02, so 2010/2011/2012 have literally zero rows; EDGAR also prices nothing and only 7.94% of its rows carry a permno. The same build on the long panel gives 192 windows over 48/48 months, reported beside it and flagged as NOT EDGAR-only. Projected decide cost **$0.6733** at the corrected price. The decide step is locked in CODE: `assert_decidable()` refuses any wire call outside `FROZEN_DECIDE_ERA (2016, 2019)`, checked on the DATA, with a CLI refusal as belt |
| **Cb §5 counterparty bias** | **HYPOTHESIS REFUTED — in the other direction** | `C5_counterparty_resolution_bias_run01.json`. Within-month cap deciles (the panel is uniform 10% by construction): resolved counterparties sit at mean decile **8.16** against 5.50, with **47.6% in decile 10** (ratio 4.76x); chi2 2947.0 on 9 df, KS D 0.4295. On **distinct** counterparty permnos (n=578) — 2,020 edges are not 2,020 independent draws — mean 6.62, chi2 106.6. Median cap **$14.28bn resolved vs $1.92bn panel**; `customer` edges mean 8.51 / $20.27bn; the **filer/supplier side sits LOWER** at 6.47 / $2.86bn. That is the Cohen-Frazzini shape, not its inverse. **Customer momentum was tested on the LARGE half of the graph.** The 68.9% residue is foreign or private **by construction**: `crsp__stocknames` carries share codes 10/11/12/18 and **zero ADR codes** — Nortel, Alcatel, BP, SAP, Canon are simply not in the file. Of 4,656 unresolved mentions, 90% of keys are never in CRSP at all and only **52** should have resolved and did not. 50-name regex/alias sample (seed 20260906, no LLM): 6 matched / 42 foreign-private / 2 ambiguous => implied true resolution **39.3% [34.9, 47.5]** against the 31.05% headline — and the missed residue is itself mega-cap (mean decile 7.96, median $8.6bn), so repairing the resolver makes the graph MORE large, not less. Descriptive only, so no DSR/MDE/three-era block, and the receipt says so rather than omitting it. **Does not settle POWER**: `graph_cust_mom_1m_ew` matched **1.74%** of panel rows, a third explanation distinct from bias and absence. Incidental: the declared RENAMES table is **dead code** — 0 fires in 6,753 mentions, because 9 of its 17 entries are short single tokens caught by an earlier branch; IBM alone is 58 mentions |
| **Cb §6 receipt provenance** | **CLASS CLOSED 2026-09-05** | `C6_receipt_provenance_rule_run01.json`, `backend/services/receipt_provenance.py`. `InputTracker.opened()` streams a SHA-256 in 1 MiB chunks, caches per normalised path so a 50 MB panel opened five times is hashed once, and records `{"error": "MISSING"}` rather than raising. `provenance_block()` emits the fixed schema; `resolve_config()` tags every key `arg`/`env`/`default`; `check_receipt()` returns NAMED findings and never raises. **PROVED RED**: `test_the_w4b_bug_in_miniature_is_rejected` rebuilds the 2026-09-05 arm — the loader opens `companyworld_v1.parquet`, the receipt stamps `edge_instances.parquet` with `source_rows 2020` beside it — and gets `UNOPENED_PATH_STAMPED`; the same receipt with the ARGUMENT stamped returns `[]`, so a checker that always failed could not pass. The sweep also went red for real, twice, on artefacts lacking the block. AT_RISK survey with three AST detectors and a positive control (the pre-fix W4b line IS flagged, the fixed line is not): **1 AT_RISK — `scripts/investment_committee.py:41`, where `DEFAULT_OUT` is computed at module level from the DEFAULT input, so `--funnel elsewhere.json` with no `--out` writes beside the module default — 13 SAFE, 2 ALREADY_FIXED**. Wired into `scripts/weekend_lab_jobs.py` at ONE choke point (asserted to be exactly one by test, because the W4b bug happened where provenance was written by hand at N call sites), and it instruments the long-panel parquet: the input every weekend number rests on, which no receipt had ever named. No number any receipt reports changed |
| **Cb §7 Monday prep** | **READ-ONLY; two proposals, neither applied** | `C7_monday_prep_read_only_run01.json`, `C7_monday_dry_run_printout.txt`; terminal `85d117f`, `docs/RUNBOOK_2026-09-08_REARM.md` **APPENDIX B**. **(a) a third band mode `indicator`, OFF by default**: hygiene gates admission exactly as under `hygiene_only`, the ratio is an admission rule in NEITHER, and the band constant still populates `exp_return` — stamped **UNVALIDATED_INDICATOR** on the row, on every sealed holding, and inside `content_sha256` beside `band_mode`. Measured on the 2026-09-02 vintage: `returns -> hygiene_only` hack3 **10->5**, hack4 5->5, hack6 **15->0**; `returns -> indicator` hack3 **10->10**, hack4 5->5, hack6 **15->15**. **It costs nothing in admissions and buys the label.** It does NOT claim the constants are right — they sit below their own t 2 bar, which is why the label reads UNVALIDATED — and the identical admitted set is not evidence the gate is inert: hygiene fires on 33 names, visible in every book's `fails` column. **(b) hack2 manage-only**, written as a RUNBOOK instruction and not code: `contract.defaults_for` branches on `TRACKER_BOOKS`, so hack2 gets EVENT defaults (horizon 3, min hold 0, +2.5% target) on a 3% stop — the exact churn the min-hold build exists to stop. Which defaults hack2 gets is Murat's call. Bug avoided: gating the eligibility chain on `hygiene_only()` alone would have silently dropped the hygiene exclusion the moment a third mode appeared; `hygiene_gate_on()` asks the question the chain actually has. An unrecognised `AAT_BAND_MODE` resolves to `returns`, pinned. Terminal suite **76 suites / 3,503 checks ALL PASS** (from 3,483). Nothing sealed, ordered, deployed or changed on Railway |
| **N1 construction** | **DONE 2026-09-07 — the mechanism is real, the money is one family** | `BUILD_NIGHT_LAB_2026-09-07.md`; `N1_construction_books.json`, `N1d_monthly_refit_books.json`. `learner/fundamental_law.py` attaches IC / effective breadth / transfer coefficient / β / implied-vs-realised IR to every book. Broadening moves **TC 0.11-0.20 → 0.28-0.64** and effective names **7-19 → 50-300** with no prediction changed — and **only 15 of 100** broad-minus-control comparisons are positive, median **−2.853pp/yr**. The exception: `revisions` top-300 rank-weighted beats its own top-50 VW control by **+4.670pp/yr t 2.584** (TC 0.132 → 0.487), **positive in 3 of 3 eras**, Holm **0.4884**, nothing survives. Index-hedged long-short: hedge works on **14 of 20** cells (realised β spans **-0.0605 .. 0.4254**; `momentum` -0.060, `ridge` 0.205 and `encoder` 0.425 are NOT hedged, each at both cost rates - corrected 2026-09-07, the earlier "0.00-0.05" was false for six cells), **19 of 20 cells lose**. Exclusion books survive best: **+0.861pp/yr t 2.487** at 10 bps. Monthly refit beats annual in **12 of 12** constructions and the gain **falls 7× as TC rises** (+2.658pp at TC 0.16 → +0.363pp at TC 0.48) — A2's +5.751pp was the narrowest instrument against a baseline nobody proposes |
| **N2 ensemble** | **DONE 2026-09-07 — and the mandate's weighting LOST** | `N2_ensemble.json`. Eight arms, monthly percentile ranks, no arm chosen. **Reliability weighting −1.041pp/yr (t −0.907) vs equal weight**, so equal weight is the honest ensemble: β **1.1951**, β-matched **+5.651%/yr t 2.424**, TW **62.87 vs 13.18** over 309 months, DSR 0.9687, MDE 4.66%/yr. The caveat that decides it: the edge is **1999-2007 (t 2.988)**, when only THREE arms existed; on the 107 months when it is genuinely eight arms it is **+2.142%/yr t 0.697** |
| **N3 size-aware floors** | **DONE 2026-09-07 — the curve runs the WRONG way for the small-book thesis** | `N3_edge_vs_floor_curve.json`, terminal `alpha/universe.py`. Floor at 1% ADV: $100k book → $500k/day. Measured TAQ cost, β-matched: institutional +2.795%/yr t 1.019 · **$100k −9.629%/yr t −3.279** · $1m +3.397 t 1.369 · $10m +4.245 t 2.176. Family 12, family-max p 0.99948, 0 survive Holm. All three named dead cells stay dead (reversal −0.49%/5-session t −2.30 at the $100k floor; S28 band net **−17.67%/yr** against a 17.86%/yr measured cost line) |
| **N4 event table** | **BUILT 2026-09-07; the books are NOT run** | `event_table_v1.parquet` **993,005 rows spanning 2015-2026 (789,277 in 2015-2024), 81-86%** of the CRSP-common proxy — IBES surprises 618,419 · 8-K 276,978 · news 95,228 and growing · 13D/G 2,380 (**all from seven days in Aug 2026**; 2015-2024 effectively absent). **Form 4 absent everywhere**, with a guard test against fabricating one. The puller has no `tradable` universe; `fleet` (~156 names) used and flagged. PEAD / revision-on-event / surprise×reaction **NOT RUN** — the Alpaca leg is ~27% through |
| **N5 unsupervised** | **DONE 2026-09-07 — compression is infrastructure, novelty is not a signal** | `N5_event_compression.json`, `N5b_pretraining_status.json`, `N5_states_third_null.json`. 137,190 news rows → **105,494 canonical events, ratio 1.3005** (receipt at HEAD; the doc's 127,157 → 97,949 was a stale snapshot, corrected 2026-09-07) (TF-IDF; a LOWER bound. NVIDIA embedder REACHABLE (`nemotron_probe` OK, 3 embeddings, dim 2048; the earlier 'ABSENT' line contradicted its own receipt, corrected 2026-09-07)). Novelty on 18,071 matured events: IC 0.003663, model-null percentile 0.92, p 0.0846 → **WITHIN_MODEL_NULL**; the three-era table **cannot be filled** (only 2015-2018 is testable) and is not claimed. CUDA **True** (RTX 5060, torch 2.11.0+cu128) by probing the designated interpreter; the 8-seed self-supervised arm IS in the ensemble at 0.253 weight share and is never a lone champion; re-training on event features **DEFERRED**, blockers named |
| **N6 simulations** | **DONE 2026-09-07 — ALL_PASS, and the machine's floor is measured** | `N6_battery_v2.json`, `N6b_fantasy_exams_round2.json`, `N6b_path_monte_carlo.json`. Battery v2: **5 of 5 worlds ALL_PASS** through N1's two constructions and N2's ensemble (linear 9.914 · regime 7.479 · graph 10.473 · **event 33.006** · null t 1.577 NOISE). The new EVENT world is where the constructions disagree most — **control t 33.0 vs broad t 14.2**: *breadth is not free when the edge is concentrated*. Sensitivity ladder recovers **0.5×** B1's planted scale and loses 0.25×. Fantasy exams round 2: **40/40 monotone, canary 0/8**, and the new clause-position control gives END 0.305 vs FRONT 0.291 → **POSITION-INSENSITIVE** (attack #6 answered). Path MC, $100k at 1× (proxy genome): **P(lose half) 0.442**, median worst DD −48.2%, p95 −72.8%; 1.3× **0.765** |
| **N7 memory / board** | **DONE 2026-09-07** | `N7_memory_and_leaderboard.json`, `LEADERBOARD.md`, `best_so_far.json`. Every receipt walked into the evidence memory; the board's head is ranked on the **β-matched t** with the family correction beside it, pinned by a test in which a cell with 45× the terminal wealth and t 0.1 must not appear in the head |
| M / P / D lanes | open | — |
| **X hygiene (amendment 2026-09-07)** | **OPEN 2026-09-07 — 11 rows, none started** | `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 X; owners in `HANDOFF_2026-09-07_FABLE51_TO_OPUS5_TWO_MODES.md` §1. Clock skew, stale NAV, Sunday fixtures, `VENUE_REJECTED`, `verdict_from`, ERAS callers, one price table, `STATE_SEMANTICS`, stale doc numbers, terminal citations, the `taskkill` hook |
| **H human mode** | **OPEN — the candidate list has NO web surface; journal + `Thesis` + prediction book exist** | `GROUNDING_2026-09-07_WEBSITE_AND_IDEAS.md` A.4-A.5; both nightly vintages stale at 2026-09-02 |
| **F fleet remap by horizon/authority** | **PROPOSED, attended** — hack4 at 1x under the EXTREME budget (contract maxDD -46.88%, P(lose half) 0.232; proxy MC 0.442) or declined is Murat's call | amendment §2 F |
| **I investor data** | **OPEN — SEC insider bulk (2006 Q1->) and 13F bulk (2013 Q2->) are FREE and historical; the 'no Form 4 source' line in N4 was wrong** | `EXTERNAL_2026-09-07_LANDSCAPE_WHAT_WE_MISSED.md` D4 |
| **E event pipeline** | **BLOCKED on E1 — the news pull DIED 2026-09-07 03:18 at 112 of 134 Alpaca months (83.6%), Finnhub leg never started, no log, no cursor, no coverage receipt; '~27% through' had no computation behind it** | `REVIEW_2026-09-07_FABLE51_ON_GPT_AND_MURAT.md` §2 |
| **R era replay v2 (Murat's design)** | **READY — code exists at $0.0025/window; needs a balance top-up ($9.28 on 09-06) and the ChronoBERT memory-free arm** | `FINDING_2026-09-06_ERA_REPLAY_V2.md` |
| **U unsupervised -> hypothesis -> genome route** | **OPEN — embedder reachable; route through `research_gym/scope.py::corpse_check`, not the 5-word check** | `N5_event_compression.json::nemotron_probe` |
| **T TradingAgents port** | **OPEN — clone at `C:\Users\mrthn\reference\TradingAgents` v0.4.1 (Apache-2.0); port the scaffold, never the sizing or the results** | `EXTERNAL_2026-09-07_FIVE_REPOS.md` §2 |
| **S strategy interface** | **OPEN — the one object all five external repos have and we do not** | `EXTERNAL_2026-09-07_FIVE_REPOS.md` §6-§7 |
