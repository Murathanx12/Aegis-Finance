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
| B3 loop | blocked on B2 §5 | — |
| B4 inference | **§1 DONE 2026-09-05** (library); the >=256-seed model null deferred with its cost stated | `learner/inference.py` + 16 tests on a PLANTED world and a NULL world: Deflated Sharpe (N = cells looked at, null SR sd from draws), Hansen SPA with a stationary bootstrap (mean block 4 periods, consistent/lower/upper), CSCV/PBO, CPCV splits with purge+embargo, and per-draw persistence (`DrawStore`) so a family-max p can be recomputed over a DIFFERENT cell set without re-running the nulls. Finance `11be9a4` |
| B5 graph | blocked on B1 (panel) | — |
| B6 autopsy | blocked on B1, B4 | — |
| B7 era replay v2 | blocked on B4 (grading) — data prep may start | — |
| B8 evolution | blocked on B1, B4, B6 | — |
| B9 allocator | blocked on B2, B4 | — |
| B10 learner v3 | blocked on B1, B4, B5 | — |
| M / P / D lanes | open | — |
