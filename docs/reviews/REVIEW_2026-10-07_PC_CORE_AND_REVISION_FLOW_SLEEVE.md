# REVIEW 2026-10-07 — PC-PAPER off cash: SPY core (D14/D22), D21, revision_flow sleeve

Reviewer: adversarial investor (read-only on code). Reviewed: `d8283f29` (60% version) and
`f98bf0ea` (second bound, sleeve 50%), which landed during the review. Verdict applies to **f98bf0ea**.

## VERDICT: SHIP WITH FIXES

Tonight's first cycle (80% cash → 50% sleeve + 20% PROBE + 29% SPY) stays inside the hard
mandate on every path I traced. Gross is 0.986 after fills in the replay. No non-SPY name goes
above 12%. Nothing is sold short. The flags-OFF golden reproduces on the PARENT commit's code.

The sizing does not meet the coordinator's own rule. Bound 2 ("gross x the basket's worst
historical 21-session return <= 10%") was computed on a **21-month panel** (2025-01..2026-10).
That window contains neither 2020 nor 2022. On the 10-year panel in the same repo, the same
rule gives **25–30%, not 50%**. Fix 1 is that number, or an explicit owner acceptance of the
2025-26 window. The other fixes are not live on night 1, but each becomes live within days.

### Fix before the 21:30 HKT open (one line)

1. **`backend/config.py:5963` `PC_SLEEVE_REVISION_FLOW_GROSS = 0.50` → `0.30` (or `0.25`).**
   Failing scenario: a 2022-type month. On `prices_deep/bars.parquet` the same 20 names,
   equal-weight and daily-rebalanced, lost **−32.03% over 21 sessions to 2022-05-18 (all 20
   priced)** and **−34.18% to 2020-03-16 (15 priced)**. 0.50 × 0.3203 = **16.0% of equity** against
   a 10% limit. Rule outcome: 30% passes (9.61%) and 35% fails (11.2%) on 2022; 25% passes (8.55%) on 2020.
   `pc_sleeves.basket_history` (`pc_sleeves.py:114`) and the receipt's new "21-SESSION BOUND"
   line read `prices_2025_26` (`PR._bars_path()`), so every receipt will print PASS against
   −19.05% indefinitely. The bound must name its panel and use the longest one.
   (Same failure as CLAUDE.md protocol 11: *which part of the sample is it*.)

### Fix within 48 h (not live on night 1, live soon after)

2. **Gross > 100% via the drift band. The core is sized from TARGET weights, not post-trade
   holdings.** `sim_run.py:1138` `core_plan(acting, ...)` uses `1 − Σtarget − resid − 1%`.
   `pc_broker.plan_orders` refuses a sleeve rebalance below the 10% drift band, so sleeve names
   can sit up to ~10% ABOVE target while SPY is bought up to its target. Reproduced with the real
   `plan_orders` + `core_plan` (50% RF / 20% PROBE / 29% SPY held, 1% cash): sleeves +9%, SPY −6%
   → SPY buy 65 sh → **gross 1.020**. Grid maximum **1.057** (sleeves +18%, SPY −17%). Paper buying
   power (~$3.77M) accepts it, so this is margin. Fix: size the core from post-plan quantities
   (held qty for refused or unsent plans, target qty for sendable ones), or clip the SPY buy
   so that `cash + sells − buys >= buffer × equity`.
3. **Buys can be submitted before the sell that funds them.** At `sim_run.py:1838`,
   `plans = plans + core_plans` appends the SPY plan AFTER the sleeves' list, which is already
   sorted sells-first (`pc_broker.py:497`). A cycle that rebuys sleeve names by selling SPY sends
   the buys first. That is transient margin, and persistent margin until the next cycle if the
   SPY sell is rejected. Fix: re-sort the combined list sells-first. Night 1 is unaffected
   (80% cash).
4. **A sleeve refusal orphans 50% of the book, or dumps it.** When `load_revision_flow` refuses
   (`sim_run.py:1075`: book voided, hack2_v2.json re-pointed to a new book_id, transient read
   error on books.jsonl, flag turned OFF), held sleeve names fall to state `EXIT`
   (`sim_run.py:1871`). An EXIT is sent only when `exploit_acting` (`:1876`):
   - ranker negative (today): 50% of equity is held with no owner, no exit, no stop.
     `_held_residual` shrinks the core around it, so it is not a mandate breach. It is an
     unmanaged position.
   - ranker positive (a future night): one failed file read SELLS the whole sleeve, labelled
     "not in the ranked book: exit". That is ~$500k turnover, the ranker gets credit for the
     decision, and the next cycle rebuys.

   Fix: held names of a refused sleeve get state `REVISION_FLOW_HOLD` (never EXIT). Exits come
   only from an explicit rule (fix 5).
5. **It is not a mirror: no horizon and no stop.** The book of record and `hack2_v2.json` both
   declare `horizon_sessions: 21` from 2026-09-25 (expires ~2026-10-23/24) and a 3-sigma GTC stop
   clipped to 4–12%. The sleeve buys tonight, 8 sessions into that life, on a 2026-09-25
   information set, and has no expiry and no stop. The receipt says so itself: "no stop is
   declared, so the ceiling is −$992,241". Fix: carry `expiry = book horizon`. Past it, the
   sleeve REFUSES new buys and exits with state `REVISION_FLOW_EXPIRY`. Re-arming means freezing
   a new book and an owner flip of `PC_SLEEVE_REVISION_FLOW_BOOK_ID`.
6. **Attribution hole: tonight's result is readable only by hand.** Sleeve orders carry
   `state: REVISION_FLOW` on `sent[]` and the receipt. They write **no decision rows and no
   DECIDED ledger rows**, and nothing in `backend/services` or `scripts` consumes
   `excess_over_core` (grep: the only hit is the declaration in `benchmark_core.py:84`). Worse,
   the C11 decision story now **always reports replay MISMATCH**. `actual_weights` = `pre_gate_w`
   (`sim_run.py:1451`) includes the 20 sleeve names, and `decision_story.replan` does not
   model the sleeve. Verified in the replay: `replay_matches_actual: False`, 20 diffs, "every
   leave-one-out NOT_SEPARABLE". The C11 LOO attribution is dark for PROBE/EXPLOIT on every cycle
   while the sleeve is on. Fix: exclude `rf_w` (and CORE) from `actual_weights`, or teach
   `replan` the sleeve. Write one row per sleeve name per day (entry px, SPY px) so the nightly
   grade prints `0.5×(r_RF − r_SPY)` separately from PROBE. Note: one night of this sleeve is
   noise (basket daily sd 2.10% → ~±1.05% of equity at 50%). The evidence for it, +5.7% excess
   in 7 sessions, is about 1 sigma.

### Lower / informational

7. **Golden self-writes** (`test_pc_plan_replay_owner_d14.py:120`):
   `if not GOLDEN.exists(): GOLDEN.write_text(...)`. A deleted fixture turns the byte-identical
   pin into a pass. Make it `pytest.fail`. (The committed golden IS pre-change: I exported
   `b3f23c55` without data, added the committed test and fixtures, and the flags-OFF test passed
   on the parent's `sim_run.py`, verified by `__file__`.)
8. **Fill race, pre-existing, now bigger.** `held` is read at `sim_run.py:1732`; open orders
   are read seconds later (`:1977`). An order from an earlier cycle that fills in between is
   neither held nor open, so it is re-sent: a double buy (SPY 29% → gross ~1.29), or a double
   sell (short). It needs an order that stays open across a cycle, so it is unlikely with
   market orders. Fix: read open orders first and add their signed qty to `held`.
9. **conftest pins the four flags OFF globally.** With them at shipped values, 9 older tests
   fail. All 9 are intended behaviour changes: a stale funnel, an empty shortlist or a
   measured-negative PROBE **no longer means "no orders"**, because the sleeve and core still
   trade. In a sandbox, `load_revision_flow` reads this machine's real books.jsonl. None of the
   9 hides a mandate breach, but the semantic change belongs on the receipt's `why_not`.
10. **D21** counts every non-ETF broker holding as `plan_sleeves_pct` beside the contract's
    EXPLORE/EXPLOIT rows. A contract row on a held name is counted twice. That is
    non-blocking (POSITIONS_DISAGREE is not in `ORDER_BLOCKING_DISAGREEMENTS`).
11. **Q6 cross-check:** it refuses correctly on a ticker-set difference and on a book_id
    mismatch (tested). A re-freeze does NOT silently move the sleeve to a new basket, because
    the config pins the id. The danger is the opposite one (fix 4/5): it silently keeps a
    stale basket forever.
12. **Q7:** `pc_sleeves` is enrolled in `test_guard_missing_input_contract.CASES`.
    `test_signal_reachability` passes. Test dates derive from `TODAY` (`test_u_plan_probe.ASOF`).
    The string asserts are on receipt lines, not grep guards.

## Mandate trace (Q1), night 1 vs later

| Path | Night 1 | Later |
|---|---|---|
| gross > 100% | no (0.986 after fills) | yes, up to ~1.02–1.06 via drift band (fix 2); transient via order sequence (fix 3) |
| non-SPY name > 12% | no (2.5% each; `min(gross/n, MAX_NAME_FRAC)`; one symbol one sleeve) | 5% on a double fill (fix 8) |
| short | no (long-only targets) | only via the fill race (fix 8) |
| SPY order rejected, sleeves fill | under-invested, safe | same |
| second cycle / restart | idempotent (open-orders skip, drift band); lease refuses a second owner | — |
| stale bars | whole plan REFUSED_BARS_STALE before any broker call | — |
| sleeve refusal | core takes the room, no sleeve buys | orphan or dump (fix 4) |

## Worst-case block, recomputed by the reviewer

Equity $1,002,264. 20 names: OKTA SNOW CRWD PANW CRM ABNB AFRM GTLB AMD ESTC AMGN TGT NET
DDOG MDB ZS WDAY S XYZ DELL (book cb8d492bb8bf9ade, frozen 2026-09-25, equal 5%).

One day, rho = 1 (the builder's rule, reproduced):

- avg 63-session name sigma **3.666%** (to 2026-10-06), matching the builder's 3.67%. The
  sum is w_i × 3 × sigma_i. The realised basket sd is 2.10% (implied avg rho 0.29), so rho = 1
  is conservative on a normal day.
- sleeve 50% × 3 × 3.67% = **−$55,122 (5.50%)**. Planned whole book: RF −$55,122 + PROBE
  −$13,356 + SPY 29% × 3 × 0.70% −$6,075 = **−$74,553 (7.44%) PASS**. Largest admissible 7.91%.
  The rule DOES use the whole book: the order-path gate prices PROBE + EXPLOIT + sleeve, and
  the core is shrunk to the remaining room including held-not-traded names.

History (the same 20 names, equal-weight, daily-rebalanced):

| panel | worst day | worst 5 | worst 21 | worst 63 | max DD |
|---|---|---|---|---|---|
| prices_2025_26 (2025-01-02..2026-10-06) | −8.24% (2025-04-03) | −14.09% | **−19.05%** (2025-03-13) | −24.85% | −32.0% |
| prices_deep (2016..2026-10-06) | −12.68% (2020-03-16, 15 names) | −26.14% (2022-05-11, 20 names) | **−34.18%** (2020-03-16) / **−32.03%** (2022-05-18, 20 names) | −39.55% | **−60.9%** (to 2022-11-09) |

Worst 21 sessions by year (deep): 2016 −20.0, 2018 −20.0, 2020 −34.2, 2021 −20.2,
**2022 −32.0**, 2024 −15.6, 2025 −19.1, 2026 −19.0.

Survivorship: the names are fixed and alive, so survivor selection does not bias this
look-back. The look-back is still optimistic, because the basket was picked in 2026 and
young listings (SNOW, ABNB, AFRM, S, GTLB) have no 2018 or 2020 history. Split check:
the only |daily move| > 40% values are AMD 2016-04-22 and AFRM 2021-08-30, both real.

Whole book as shipped (50 RF / 20 PROBE as currently held / 29 SPY), deep panel:
worst day **−11.48%** (2020-03-16; RF −12.68, PROBE −10.06, SPY −10.78), so the one-day
3-sigma line (10%) was exceeded by history. Worst 21 sessions **−30.0%** (2020) and **−22.4%**
(2022). Max DD **−44.8%** (2022).
In dollars at $1,002,264: worst day −$115k; worst 21 sessions −$301k; with 50% in the
sleeve alone at the deep 21-session worst, −$171k (2020) / −$161k (2022).

## Tests run

- `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 python -m pytest -q -p no:cacheprovider
  test_pc_plan_replay_owner_d14.py test_pc_broker_drift_band.py test_benchmark_core.py
  test_decision_contract.py test_u_plan_probe.py test_guard_missing_input_contract.py
  test_signal_reachability.py` on f98bf0ea: **215 passed** (60 s). On d8283f29 plus the then
  uncommitted work, without reachability: 206 passed.
- Parent-code golden check (`b3f23c55` exported to scratch, committed test and fixtures):
  `test_flags_off_plan_is_the_pre_change_plan` **1 passed**.
- Flags left at shipped values (scratch copy, conftest pin disabled): u_plan_probe,
  benchmark_core, drift_band, decision_contract → **9 failed**, all intended behaviour
  changes (item 9).
- Replay with flags ON (scratch probe): gross after fills 0.9857, SPY 0.2894, 22 orders
  (CORE, REVISION_FLOW, PROBE), decision story `replay_matches_actual: False` (item 6).
- Drift-band simulations with the real `pc_broker.plan_orders` and `benchmark_core.core_plan`
  (item 2).
