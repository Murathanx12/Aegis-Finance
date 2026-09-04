# NIGHT LAB — 2026-09-05 — the prompt for Opus 5 (paste this whole file)

You are Opus 5, the builder. It is Friday night in Hong Kong; Murat sleeps
~8 hours and stops the lab by hand in the morning. Fable 5.1 is the brain and
reviews everything you produce. Read, in order: `session_briefing()`,
`aegis_verified_state(section="summary")`, `docs/DECISIONS_2026-09-05_PLAIN_LANGUAGE.md`
(Murat's answers are appended at the bottom by him — apply only what he
approved), `docs/ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6, your own
`docs/BUILD_B1_2026-09-05.md`, and `docs/MURAT_2026-09-05_INPUTS.md`.

## 0. Rules for tonight (no exceptions)

- **No Anthropic/Claude API calls. No LLM spend except DeepSeek or
  gpt-5-nano, hard-capped at $5 total** through `alpha/spend.py` /
  `llm_analyzer` budget; every call names the decision it can change.
  Everything else is heavy shells on local data.
- **The old panel is dead.** Every job reads the B1 clean panel
  (`ibes__ptgsumu`, `dlret` merged) via `learner/benchmark.py` for every
  market number. A receipt with a `market` not produced by the module fails
  the gate.
- **Nothing sealed, ordered, deployed or pushed by you.** Railway variables
  untouched. Murat pushes and deploys in the morning.
- **Every job writes a receipt even when it finds nothing** (invariant 15):
  `backend/data/optimus/night_lab_2026-09-05/<job>_<run>.json` with
  `licence: PRODUCT_EXPERIMENT`, `question`, `family_id`, `cells_looked_at`,
  the ≥64-draw model-null percentile, and `family_max_p` where the library
  exists. Loud refusals, never silent zeros.
- **A `STOP` file halts everything**: every loop checks
  `backend/data/optimus/night_lab_2026-09-05/STOP` between runs.
- Two agents per repo maximum on the same tree; each agent owns disjoint
  files; the coordinator commits per job on a branch `lab/night-2026-09-05`.
- Tests: finance `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`
  (**run the full fast suite FIRST tonight** — the last run was cut short —
  and again at the end); terminal `python run_tests.py`.

## 1. First hour — the build that gives the paper accounts holdings on Monday (B2 §1-3, terminal repo)

This is not a lab job; it is the deliverable Murat asked for all week.

1. Contract fields on every sealed holding and `state/contracts/*.json`:
   `expected_horizon_sessions`, `min_normal_hold_sessions`, `thesis_expiry`,
   `hard_falsifiers`, `risk_budget_usd`, `emergency_exit_reasons`. The seal
   refuses a book without them. Tracker books: horizon 21, min hold 10.
2. `alpha/exits.py` reads the contract: before `min_normal_hold` a close is
   legal only with a typed reason (THESIS_INVALIDATED, DATA_ERROR,
   HARD_RISK_LIMIT, EXECUTION_CORRECTION, DEADLINE,
   EXPLICIT_EVENT_STRATEGY_EXIT); the stop uses the profile width (R3) and
   is HARD_RISK_LIMIT; the +2.5% PEAD target is removed from tracker books;
   the drift-window horizon comes from the book, never from `--expiry`.
3. Re-entry guard sees every exit (`alpha/runner.py:1134-1150` ∪ today's
   ledger `brain=="exit" and action=="closed"` rows).
4. **`deadline_liquidation_due` fires only ON the deadline date**
   (`alpha/exits.py:114`: `current.date() != deadline.date()` → False), and
   `AAT_LOOP_EXPIRY` in `alpha/fleet.py` moves to `2027-12-31`. Without this
   the fleet liquidates every day at 10:45 ET once entries are re-armed.
5. From `FINDING_2026-09-05_THE_MEGA11_EXEMPTION.md`: refuse when
   `expected_edge_usd < 3 × stop_loss_usd`; make `Mandate.tier` binding on
   side (SAFE books cannot short shares); `exits.manage` re-places a stop it
   cancelled when the close fails.
6. Exit-reason enum written to the ledger; `utilization.py` and the
   learning report print the armed/disarmed state of every entry path per
   role and the BINDING constraint.
7. Tests for each; `python run_tests.py` green; commit on the branch; write
   `docs/RUNBOOK_2026-09-08_REARM.md`: the exact Monday steps for Murat
   (push → `fleet --deploy <role> --up` → remove `--manage-only` on
   hack3/4/6 → verify "entries armed" in logs → first seal under
   hygiene-only → 10:01 ET entries → hold ≥ 10 sessions).

## 2. The lab queue (finance repo; heavy shells; loop until STOP)

Build `scripts/night_lab.py`: a runner that takes the queue below, runs each
job as a subprocess with a per-job timeout, writes the receipt, appends a
line to `night_lab_2026-09-05/LEADERBOARD.md` (job, run, headline number,
family-max p, verdict), and when the queue is exhausted **starts over with
the next variant list** until STOP. Order is priority order; a job that
fails writes its traceback as its receipt and the loop continues.

**L0 — Inference library, minimal** (`learner/inference.py`; B4 §1). Before
any other job: per-draw persistence; `family_max_p` over all (arm, head,
horizon) cells per seed (the v2 driver never called it); Deflated Sharpe
(N = cells looked at, null SR variance from draws); Hansen SPA with a
stationary bootstrap (block 3-6 months) on paired-excess series; CPCV
(purge = horizon, embargo 1 month) + PBO for arm rankings. Unit-test on a
planted linear world and a null world. Every later job imports it.

**L1 — Learner on the clean panel, repeated.** `lgbm_clf` baseline +
`encoder_clf` (prior REFIT PER SPLIT via `prior.band_constants_from_frame`,
not the full-sample constants) + `ridge` at 1/3/6/12m, top-50 VW, 10 and
25 bps; ≥256 model-null seeds for the champion cell (lgbm is CPU; that is
fine); DSR, family-max p, PBO. **Variant loop:** feature families ablated
one at a time (analyst, price-shape, holder, sector, ratio-as-indicator,
customer-momentum if L5 lands); then quantile heads (q05/q50/q95, pinball
loss) for a tail estimate. Leaderboard by after-cost terminal wealth vs SPY
TR with DSR beside it. If CUDA torch can be installed in <15 minutes
(`pip install torch --index-url https://download.pytorch.org/whl/cu128`),
do it and record `torch.cuda.is_available()` in the receipt; otherwise CPU.

**L2 — States, honestly.** Re-run `learner/states.py` on the clean panel;
report the within-month null AND the persistent circular-shift null AND one
new null that permutes feature vectors across names within month while
holding each name's label sequence fixed. Verdict is whatever the three say
together; CANNOT DETERMINE is an allowed answer. Autoencoder variant once.

**L3 — Winner/matched-loser factory v1** (B6 §1). Per year 2013-2024: top
and bottom 50 twelve-month movers residual to beta×size×sector; 5 matched
controls each (month, sector, size, liquidity, coverage, 12-1 momentum, 60d
drawdown); PIT feature deltas at 1/5/21/63/126/252 sessions before the
move, including 8-K item counts (tape), revisions, `dlret` context, and
graph-neighbour moves if L5 lands. Output: archetype candidates whose
winner−matched-loser difference clears L0 inference in ≥ 2 eras. Also the
**opportunity-recall baseline**: of each year's top-50, what share did
(a) the analyst-upside screen, (b) 12-1 momentum, (c) revisions, (d) the
learner surface beforehand — typed misses.

**L4 — Reversal, by size and by event** (Murat's LULU question). On the
clean daily CRSP: after a top/bottom-decile one-day move, next-session and
5-session excess using **next-open-to-close** entry, by size quintile ×
{earnings-day (8-K 2.02 within ±1 day), no event}, at 10/25/50 bps. Family
of ~40 cells with L0 inference. Then the same for the 09-04 movers list if
prices are cached.

**L5 — Customer momentum from MARKET-GRAPH-1** (B5 §5b). Read
`../Aegis module/runs/MARKET-GRAPH-1/edge_instances.parquet`; build the
permno-level customer→supplier and competitor tables with `valid_from` =
filing date; feature = lagged one-month return of a firm's customers
(Cohen-Frazzini); test on the clean panel with L0 inference; also the
competitor-momentum and shared-technology variants. Write
`backend/data/optimus/graph/companyworld_v1.parquet` with `graph_layer=FACT`.

**L6 — Options → stock** (Murat's calls question). Join OptionMetrics
`vsurfd` (30-day surface) to the clean panel through `link_optionm_crsp`;
features: 1-month change in ATM implied vol, call-put implied-vol spread
(Cremers-Weinbaum), skew (Xing-Zhang-Zhao); cross-sectional IC and top-decile
VW books at 1/3m; L0 inference. Peer lead-lag: does a name's IV change lead
its MARKET-GRAPH-1 competitors' returns?

**L7 — Psychology proxies.** 52-week-high proximity (George-Hwang),
distance from a 60-day VWAP as a purchase-price anchor, attention spike
(volume z-score); test as features on the clean panel with size/momentum
controls; L0 inference. Design note for the LLM-disposition test in the era
replay diary arm.

**L8 — Analyst vs ours, expectation vs reality.** (a) Re-run
`analyst_target_grades` confirming the share basis of `ptgdetu`; bias
persistence across halves on the clean panel. (b) **Grade every sealed
prediction book** (`state/predictions/*.json`, 9 books, 5,740 rows) against
realised 21-session returns now that days have passed: hit rate, Brier,
calibration table, and the analyst consensus on the same names as the
comparator — "expectation vs reality with our assessments". (c) Grade
Murat's 2026-09-05 lists forward-only: register them as a human generator
with observed_at = today; no return is available yet, so the receipt says
so and schedules the grade.

**L9 — Band prior on its own live object.** Using the tracker day files
(`state/tracker/*.jsonl`, Finnhub unadjusted targets, 4 days) and the
2013-24 PIT tape, re-derive what an "analyst upside" screen earns with a
$5 floor and `dlret`; this is the research half of decision B.1 and it
must not touch the live rule.

**L10 — Era replay v2, data only ($0).** Build the 2016-19 era windows from
the corpus + EDGAR 8-K exhibit 99.1 press releases (tape on disk), the
frozen entity map, and the diary-arm scaffolding (`previous diary`,
`previous weights`, cost per rebalance, nulls 2 and 3). Do NOT run the
decide step tonight unless the $5 cap has room; if you run it, gpt-5-nano
rewriter + DeepSeek decider on ≤ 100 windows and grade rank only.

**L11 — Belief series inventory.** Polymarket/Kalshi rows collected so far
(`state/belief_series.jsonl`, 14,670 rows): coverage by market, dates,
whether any event has ≥ 60 observations; write the test design; do not
claim.

**L12 — Mirror lane reconcile** (Murat's −16%): `python -m
scripts.lane_positions_reconcile --from-prod` if the endpoint is reachable
read-only; print holdings vs seed and the NAV chain check; a report, no fix.

**L13 — Corpus-to-Railway design**: a one-page design for running the
corpus collectors as a scheduled job on the seal-authority service writing
to its volume, with cost; plus `fleet_health` check "corpus rows on the
authority ≥ N". Design only; Murat approves the Railway change.

## 3. Morning deliverable

`docs/BUILD_NIGHT_LAB_2026-09-05.md`, ≤ 2 pages, RESULTS SCOREBOARD first:
- the leaderboard (every job, every run, headline, family-max p, DSR,
  verdict NOVEL / NOISE / CANNOT DETERMINE / REFUTED);
- what B2 §1-3 shipped and the Monday runbook;
- claims for Fable to attack (5-10, with receipts);
- what the lab could not do and why;
- LLM spend to the cent.
Update roadmap §6, session memory (one file, one fact each), `MEMORY.md`
(one line), and run `python tools/refresh_aegis.py` in the Optimus repo.

Murat will judge in the morning whether each finding is novel and worth
carrying, or noise. Your job is to make that judgment easy: one number,
one null, one sentence per job.
