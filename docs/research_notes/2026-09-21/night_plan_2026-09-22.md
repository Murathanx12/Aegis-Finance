# The night of 2026-09-21 → 22: plan, and Fable's assessment of the self-improving loop

Murat, 21:40 HKT: "make everything ready for the night and run it, make it stop
at 7.30 am. during that while don't spend tokens, use the local things to run
tests and simulations to constantly learn and improve. you can also use
deepseek, we still have 50 usd there. make a test environment and with every
iteration and step it should get better. self improving system, do your own
assessment on how to improve that too." He attached GPT's night brief (closed
loop: predict → observe → error → hypothesis → challenger → replay → keep or
reject; seven missions; hard stop 07:30; DeepSeek ≤ $5; a morning report with
five questions where Q1 may be NO).

## What runs tonight, in order (all local unless marked)

`python -m scripts.night_run_until --date 2026-09-22 --stop-at 07:30 --lab --paid`
is the clock (new tonight; `scripts/night_run_until.py`). It loads the keys
into the environment once so every child has them (last night X4 and P6 ran
without theirs), starts the model server and writes its PID down, snapshots the
DeepSeek balance, then:

| phase | job | box | why it is here |
|---|---|---|---|
| 1 | `P6_bars_and_regret` | 60 | **reality first**: the local bar panel ended 2026-09-11; 2,911 forecasts wait on a bar. P6 extends it to today. |
| grading | `forecast_grader.grade_due` + `decision_ledger.score_due` | — | every forecast and decision whose window has closed, graded on the fresh bars BEFORE anything trains. |
| 2 | `J1_error_dataset` (new) | 20 | the ERROR DATASET: one row per graded prediction, clustered (wrong direction / magnitude / horizon / costs / overconfident / REFUSED-then-performed …) with a curriculum block naming the experiments the clusters justify. |
| 2 | `C7_signal_calibration` | 60 | rank→return maps re-fit on the extended panel; a WEAK cell moving is a `BELIEF_CHANGED`. |
| 2 | `J2_missed_opportunity` (new, **DeepSeek ≤ $4.50, soft stop $4.00**) | 45 | the largest 21-session moves AEGIS did not hold; deterministic PIT precursor check (Form 4 clusters, revisions, news volume, typed events, search interest); the SAME masked cases read by the local 7B and by DeepSeek; graded against the precursors the data actually shows. This is the one paid question of the night, and its first flush is the proof that chunk 22c's cap now binds. |
| 2 | `E4_adwin_gated_refit`, `E1_event_head`, `E3_adaptive_conformal`, `E5_stopping_rules` | 60 each | the model lab: drift-gated refit vs monthly refit on identical dates (champion/challenger on one head); the typed-event head vs its capacity-matched shuffled control; adaptive intervals; stopping rules on the lineage archive. |
| 2 | `X4_regime_route`, `X2_elasticity` | 60, 120 | last night X4 refused (no FRED key reached it) and X2 timed out at 60; both re-run with the key in the env and a wider box. |
| 2 | `L2_typed_events`, `L2_retype_v3`, `S1_social_features` | 120, 60, 30 | the typing backlog that feeds E1 (coverage 9%); the social variables. |
| 2 | `B_first_books_replay`, `D4_ls_robustness_and_decay` | 60, 120 | replay-family jobs, if the clock allows. |
| lab | `scripts.always_on_lab` | until STOP | news and social pulls into the corpus, typing when the model is idle, decision-vs-reality hourly, the 06:30 daily pass (contract with PROBE rows, grader, scoreboard). |
| 07:00 | STOP file | | no new job starts (both the factory and the lab read it). |
| 07:25 / 07:27 | kill by PID | | the running job tree, then the lab if still up. |
| 07:30 | model server stopped by its PID; `scripts.night_morning_report` → `MORNING_REPORT_2026-09-22.md`; `NIGHT_STOPPED.json` with the process census and the GPU line. |

Not run tonight, and why: `S2_scenario_gym` — its default seed is a constant,
so a second run would be a bit-identical replay of last night's 300 cells
(the 2026-09-10 lesson); gym v2 (chunk 23g) is the next gym. `N9` — 11,386
candidates measured this morning, 0 survivors; no more candidates are bought.
No world-model sidecar exists yet (chunk 25), so mission 7 is not attempted;
bandit off-policy evaluation is CANNOT DETERMINE until ~200 scored PROBE/EXPLORE
rows exist (first PROBE grade 2026-09-28).

## Fable's assessment: what "self-improving" is and is not, here

**What already closes the loop on disk.** Predictions and decisions are
timestamped before reality (the ledger, PROBE rows at $0), graded at their own
expiry by the same grader (progressive validation, exactly), calibration is
re-fit walk-forward (C7), a drift detector gates a refit against a fixed-cadence
control on identical dates (E4), every head is measured against a
capacity-matched shuffled control (E1), and a chunk cannot close without one of
CAPITAL / WEIGHT / HYPOTHESIS_KILLED / BELIEF_CHANGED. That IS champion versus
challenger with promotion left to the validated pipeline; nothing overnight
rewrites production logic.

**What is missing, in the order it matters.**

1. **The error dataset did not exist.** Grading produced totals (Brier 0.2625
   vs climatology 0.2244) and no rows a learner or a reader could act on. J1 is
   the first night whose output is *the errors themselves, clustered*, and its
   curriculum block is how tomorrow's experiments get chosen by yesterday's
   failures instead of by whoever is awake. The rule I would adopt: **≥ 70% of
   a night's queue must trace to a J1 cluster or a J2 missed name**, and the
   receipt says which.
2. **Reality was stale.** The bar panel was ten days old; every "graded"
   number this week was graded against bars that stopped on the 11th. P6 now
   runs first every night. The scoreboard should print `last_bar` beside every
   NAV/SPY line so a stale panel cannot pass as a fresh grade.
3. **The paid model has never been made to earn its cost on a paired case.**
   J2 is the first job where the local 7B and DeepSeek answer the same masked
   cases under the same schema and are graded by data, not by each other. If
   DeepSeek does not beat the local reader on precursor hit rate, the $ goes
   elsewhere; if it does, the delta is the price of the information.
4. **Horizon is still a default.** Chunk 22 measures 5/21/63/126 and the
   authority reads 21. profitability_small at 126 (net +5.11%, t 2.78) is the
   worked example; chunk 23d makes the cell the unit.
5. **No specialist error-correlation matrix.** Until scored PROBE rows carry
   `source`, unanimity is counted as evidence. The rows now carry
   `hypothesis_id`, `signal`, `selection_probability`, `action_set_sha256`;
   the matrix (23f) and the router (28) can be computed once ~200 exist.
6. **The morning report was a person.** J3 writes it from receipts by rule,
   with Q1 = NO unless a receipt carries a measured before→after. That removes
   the incentive to narrate progress.

**What I would not build.** A nightly NN that retrains on "more data": E1's
head has lost to its own shuffled control three nights running at 9% event
coverage; the limiting factor is typed coverage and a target with signal, not
optimizer steps. And a world-model swarm before the sidecar boundary and its
four controls exist — its consequence chains should enter as PROBE rows, never
as returns.

**The honest expectation for tonight.** Q1 will most likely be NO: the night
can grade ~2,900 more forecasts, produce the first error dataset and the first
paired local-vs-DeepSeek read, re-fit calibration on ten more sessions, and
re-run the drift and head jobs. None of that changes capital before the first
PROBE grade lands on 09-28. A NO with three new measurements is the right
answer; a YES without a before→after would be the wrong one.
