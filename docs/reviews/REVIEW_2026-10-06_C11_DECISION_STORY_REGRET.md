# REVIEW 2026-10-06 — C11 Decision Story + Regret Ledger (adversarial)

Reviewer stance: a quant/investor who says "you are wrong, I would have done this".
Scope: `backend/services/decision_story.py`, `backend/services/regret_ledger.py`,
`scripts/sim_run.py` (`_freeze_decision_story`, the u_plan hook), `xs_ranker.load_bars(symbols=)`,
`policy_state.regret_view()`, `scripts/task_keeper.py` `regret` job,
`backend/tests/test_decision_story_and_regret.py`. Read-only; probes ran on synthetic data in a
scratch folder. Nothing in the tree was edited.

## VERDICT

**PLUMBING SOUND, MEASUREMENT NOT YET HONEST — DO NOT READ THE FIRST REGRET RECEIPT AS A RESULT.**
The append-only story, the seals, the NOT_SEPARABLE refusals and the zero-cost refusal are good
engineering. But three of the six regret types are biased positive by construction (hindsight
`max` over alternatives, plus an infeasible "enter one session EARLIER" alternative). The
abstention headline is the raw return of a 102%-gross, 51-name book that could never have been
held, and it is not benchmark-relative. Weekend asofs are graded as three sessions entered at
Friday's close. And on 2026-10-13 nothing will be graded: there are zero live stories, and the
grader has no scheduled caller. RESULT IMPROVEMENT: NONE. That is also what the builder says.

Score: **56 / 100**.

## Test run (pasted)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest \
  backend/tests/test_decision_story_and_regret.py backend/tests/test_u_plan_probe.py \
  backend/tests/test_policy_state_is_read.py -q
.....................................................................    [100%]
69 passed in 23.95s
exit=0
```

Mocks and fakes in play:
- `test_u_plan_probe.FakeBroker(is_open=False)`, installed by monkeypatch. No venue, so `sent == []`
  on every u_plan test, and the `order_link` path is never exercised by a real send.
- Synthetic bars `_bars()`. These are **deterministic constant-drift series** with no noise
  (AAA +0.1%/day, BBB +0.3%/day). With no noise, every "right sign" assertion holds trivially.
  Under constant positive drift `buy_double` *must* win sizing.
- `task_keeper.run_regret(grade=lambda: ...)` and `grade=boom`, an injected grader.
- `test_policy_state_is_read` monkeypatches `PS.LEARNED_RULES / STATE_PATH / JOURNAL_PATH /
  LEADERBOARD_DIR` and `ER.build`.
- One weak assertion: `res["why_zero_orders"] is None or "abstentions frozen" in ...`. The
  `is None` branch makes the "appends the line" claim untested whenever orders exist.

## Findings

### F1 — HIGH — Sizing and timing regret are hindsight oracles, positive under the null
`sizing_regret = max(buy_half, buy_double_capped) − actual` and
`timing_regret = max(enter_next, enter_prev) − actual`. A `max` over alternatives chosen after
the outcome is positive whenever the return is non-zero. Probe: zero-drift random walk at the
book's median daily sigma (2.16%), w = 2%, 35 bps round trip, h = 5, 4,000 draws:

| quantity under H0 (no skill) | mean | share > 0 |
|---|---|---|
| sizing_regret | **+5.64 bps of equity** | **1.00** |
| timing_regret | **+3.39 bps** (sd 5.02) | 0.75 |

Every decision will show "should have sized differently". About three quarters will show "should
have timed differently", with no information in either. On top of that, `enter_prev_session`
enters at the close *before* the decision. It is not an action the plan could have taken, so it is
not an alternative. The h5 MDE of a timing edge is about 6.3 bps per decision at 5 sessions and
1.8 bps at 63. The selection bias (+3.4) is the same size as that MDE.
*Fix:* report each alternative's signed difference separately, and never the `max`. Report
"double − actual", which is symmetric and has mean zero under H0 apart from cost. Drop
`enter_prev_session`, or label it INFEASIBLE_DIAGNOSTIC and keep it out of any regret.

### F2 — HIGH — The abstention headline is beta on an inadmissible book
For a REFUSE, `abstention_regret = w_default·(r − rt)`, with w_default = 2%. All 51 dry-run
candidates are abstentions, so the summed "$X by acting" prices **51 × 2% = 102% gross**. That is
more than five times `PROBE_GROSS_CAP` (20%) and more than the account. Session protocol item 4
asks for the worst case in dollars for the largest admissible book, and this headline prices an
inadmissible one. `benchmark_return` is stored on every row and **subtracted nowhere**. Probe with
51 beta-1 names, 20 bps cost and SPY ±1% over h5: the line reads **"+$8,160 would have made"** or
**"−$12,240"**. That is pure market direction. The same sum also mixes three different questions:
PROBE names the plan selected but observe mode gated (their honest counterfactual is
`plan_full`, the plan's own target, not `buy_default`); NOT_SELECTED ranker-pool names (the
answer to "what if we bought everything"); and HELD names (where "abstention" means resizing
from 2.11% to 2.00%, as in the NVDA example).
*Fix:* grade abstention as `plan_full` for selected-but-gated names. Report every number as excess
over SPY and over the panel's random-portfolio control. Split by `state`, and scale the book to
the gross cap before converting to dollars.

### F3 — HIGH — Weekend and holiday asofs: triple counting and an infeasible entry
`asof = _asof_et()` is the ET calendar date, and u_plan runs every cycle, including weekends.
The bars gate counts closed sessions, so it passes on Saturday. Each asof mints new decision
ids. `hold_return` enters at "last bar ≤ asof". Probe (freeze Fri/Sat/Sun, then grade):

```
2026-05-15 entry 2026-05-15 exit 2026-05-22 abst $290
2026-05-16 entry 2026-05-15 exit 2026-05-22 abst $290
2026-05-17 entry 2026-05-15 exit 2026-05-22 abst $290
h5 n_sessions: 3        mdc_news h5 label: TRUST_AT_63 (3/63)
```

This causes three problems:
- One observation is counted three times, in the dollar sum and in `n_sessions`.
- `TRUST_AT_63` and `regret_view()["trusted"]` arrive about 40% early in calendar terms.
- The Saturday decision is priced at Friday's close. That close was already printed before the
  decision, and the decision may read forecasts made after it (Friday after-hours). That is a
  look-back entry.

The same thing happens on any decision built after 16:00 ET, whose entry is a close it already
saw.
*Fix:* key the story on the next tradable session (`DC.sessions_expiry(asof, 0)` or the XNYS
calendar). Refuse non-session asofs. Enter at the next session's open, or the decision-day close
only when `decision_at` < 16:00 ET.

### F4 — HIGH — The 10-13 "first grade" will not happen
- `backend/data/optimus/decision_story/` **does not exist**. The running session holds the old
  u_plan, so no live story has been written, and nothing dated 2026-10-06 can mature on 10-13.
- `task_keeper regret` exists but has **no scheduled caller**. It appears only as a
  `TODO(orchestrator)` comment, and `daily_pass.py` does not call it.
- `regret_view()` has no production caller either: no morning report, no policy_state reader.

The line `first grades at 2026-10-13` is printed from `first_grade_date(asof)` for whatever asof
ran, so the dry run printed a date that no live data supports. This is the house failure mode: a
staleness line without a scheduled remedy.
*Fix:* restart the session onto the new u_plan, then add the daily_pass step. Make the receipt
print `live stories on disk: N, oldest asof: D` beside the date.

### F5 — MEDIUM — Replay exactness is not float-fragile, but it is code-drift-fragile, and it has already drifted
- `replay_check` uses an absolute tolerance of 1e-9. A 1e-12 perturbation passes and 2e-9 fails
  (probed), so floating-point noise is not the risk.
- The risk is that `replan` re-implements u_plan by hand. While this review ran, a concurrent C2
  change added `_order_path_gate` (`sim_run.py`). It mutates **EXPLOIT target weights down by
  `scale_exploit`** before `_freeze_decision_story` receives `targets`, and `replan` does not model
  it. On any day EXPLOIT acts and the worst-case cap binds, the replay mismatches and **every LOSO
  row becomes NOT_SEPARABLE**. It is dormant today only because EXPLOIT is MEASURED_NEGATIVE.
- The mismatch is recorded on the story, but it is not on the receipt line, and nothing goes red.
  Nothing tests "u_plan and replan agree" except one sandbox fixture.
*Fix:* have u_plan *call* `replan` for its targets (one implementation), or pass the
pre-gate weights and the scale explicitly. Add a test that changes a u_plan sizing rule and
expects the replay test to fail. Print `replay_matches_actual` on the line.

### F6 — MEDIUM — PIT: the freeze is clean because it prices nothing; the grade has no reconciliation
- `freeze_plan` reads bars only for the held-weight fallback. Alternatives store weights and
  E[r], with no price, so "post-asof bars mutated → byte-identical" is true but close to
  tautological.
- The PIT test mutates only bars **after** asof, which cannot catch the nn_lab leak shape (a
  later adjustment that rewrites **past** bars). Attack: re-running the freeze over a panel
  back-adjusted for a later 2:1 split halves CCC's held weight (0.0103 → 0.0052). Live freezes run
  on the then-current panel, so this only bites a replay or backfill. The test claims more than
  it checks.
- The grader computes entry and exit from the grade-time panel alone, with no check against the
  decision-time price (`latency.prices.decision_at` is stored and never compared). Attack on BBB
  at h5, true return +1.51%:
  - a raw, unadjusted split in the hold window grades **−49.25%** (abstention −$9,861) with
    `status: OK`;
  - a two-basis splice grades **+103%** (+$20,592) with `status: OK`.
- Today's panel is `adjustment=all`. `pull_bars_refresh` re-pulls whole series on drift and
  refuses splices. The 51 symbols present in both deep and delisted files agree to under 0.5% on
  all 100,961 shared rows. So the leak is latent, not live, and the grader is trusting a guard it
  never checks.
*Fix:* freeze the decision-time reference close (the last bar ≤ asof, at freeze time) on the story.
At grade time, refuse a row whose entry close differs from it by more than the cumulative
adjustment factor allows. Flag any |r_h5| > 8σ for review.

### F7 — MEDIUM — The news arm is not connected to decisions; C11 confirms the gap and does not close it
u_plan has no `news` or `digest` read (grep over the function body). `expected_return.NOT_READ_BY_DESIGN`
lists `source:` and `news_digest:`. What connects and what does not:
- **Connects:**
  - world_digest → `SHADOW_NEWS_v0`, a shadow contract graded by `shadow_grade` / `daily_pass`.
    Trust stays 0 until `WORLD_DIGEST_TRUST_MIN_DATES` graded dates exist.
  - world_digest → `fleet_manager.news_targets`, a fixed 1%-unit news sleeve on a fleet paper
    account. It is *not* trust-weighted.
  - news rows → the C11 story's `chain.event_ids`, labelled `event_ids_read_by_plan: false`.
- **Does not connect:** news → E[r] → u_plan → the PC book. MDC_news ≡ 0 by construction. The C11
  receipt will print a news MDC every day that says nothing about news.

The owner's "news arm must be connected to decisions" is therefore still open on the PC book.
C11 could have measured the question without wiring anything: freeze one more alternative,
`plan_plus_shadow_news`, which applies `world_digest.shadow_decision(base=plan_full, trust_dir=1,
trust_size=1)`. That would make the MDC of news a real number from the first graded day, still
with no order.

### F8 — MEDIUM — Selection regret: one comparator, one session, no independence
- `next_ranked_not_taken` comes from the replay's `shortlist_order` (after `probe_order`, before
  the PROBE acting gate, and after the EXPLOIT exclusion when EXPLOIT acts). So it is defined
  pre-gate, which is correct.
- But **every** PROBE name in a session is compared with the **same** single next-ranked name. Ten
  selection regrets per day are therefore one observation (CANON §58: n_effective counts date
  blocks).
- The selection P&L charges the *taken* name's cost to the alternative name.
- In observe mode `eff_w = 0` for every non-held name, so sizing, timing and selection regret are
  computed **only for held names**. The 51-abstention dry run yields almost none of them, and the
  summary's `n` will mislead unless it is read beside `state`.

### F9 — LOW — The "double capped at 12%" alternative and the readers of alternatives
- The cap is `pc_broker.MAX_NAME_FRAC = 0.12`, the broker's per-name cap, which is correct.
- `grep` for `alternatives_` and `regret_ledger` / `regret_view` readers finds only
  `regret_ledger._load_frozen` and tests. No path treats an alternative as a target, and
  `places_orders: false` is on every row. This is clean.
- One semantic point: with `ref_w = 2%`, "double" is 4%, which is 2× `PROBE_MAX_WEIGHT`. The PROBE
  sleeve could not have held it, so its sizing number answers a question about a different
  mandate.

### F10 — LOW — The cost model
- An unknown volume is charged the 35 bps small band. That is correct for unknowns, but a held
  mega-cap that is not on the shortlist or in the pool (no `median_dollar_vol` on the row) is
  charged 35 bps instead of 6 bps. That biases exit and hold regret for exactly the names the
  book holds longest. Look the volume up from the panel instead.
- `_load_frozen` keeps the *last* decision per (asof, ticker) by `built_utc`, and BUY entries are
  priced at the close rather than the broker fill. The `order_link` and `fill_at` are not used by
  the grader, so the graded "actual" is not the account's actual.

## The table the owner should see when h5 grades land (and whether this code produces it)

One table per graded date block, net of cost, **excess over SPY and over the panel random-portfolio
control**:

| bucket (by `state`) | n names | book (scaled to the gross cap) | mean net excess h5 | vs random control | n date blocks | MDE |
|---|---|---|---|---|---|---|
| PROBE: selected, gated by observe mode (`plan_full`) | | | | | | |
| NOT_SELECTED: shortlist names not taken | | | | | | |
| NOT_SELECTED: ranker pool | | | | | | |
| HELD (hold vs exit_now) | | | | | | |

The question it answers: "did the plan's *own* picks beat the names it passed over, and SPY,
after costs?". That is the only abstention question observe mode can answer.

**Will this code produce it? No.**
- The receipt gives sums of the six regret types by horizon and ISO week, plus a raw-dollar
  abstention line.
- It has no excess over the benchmark (the column exists but is not used), no split by state,
  no gross scaling, no MDE, and an `n_sessions` that counts weekends.
- The rows carry `state`, `realised_return`, `benchmark_return` and `cost_round_trip_bps`, so the
  table is about 20 lines of post-processing.
- On 10-13 there will be no rows at all (F4).

## Three things I would have done instead

1. **Grade the selector, not the regret.** Use one alternative per decision that matters:
   `plan_full` (what the plan wanted) vs `no_trade`, at the next feasible entry, as excess return
   over SPY and over a random draw from the same funnel. Add sizing and timing only as signed,
   mean-zero diagnostics, never a `max`. Hindsight-best regrets are a dashboard for regret, not a
   learning signal.
2. **One session = one row, from the exchange calendar.** Key stories on the next XNYS session and
   enter at that session's open. Freeze the reference price, refuse weekend and post-close
   duplicates, and count n in date blocks with an MDE on the receipt (CANON §58, §64).
3. **Make news measurable this week instead of declaring it zero.** Freeze
   `plan_plus_shadow_news` (the SHADOW_NEWS_v0 tilt at full trust over `plan_full`) as an
   alternative. Also have u_plan call `replan` for its own targets, so the LOSO replay cannot
   drift from the live sizing, which a concurrent chunk already did.

## Score: 56 / 100
- +: append-only sealed rows, deterministic ids, honest NOT_SEPARABLE and IDENTICAL_NOT_READ
  with reasons, zero-cost refusal, never raises into the plan, no reader treats an alternative as
  a target, parquet symbol filter.
- −: biased-positive regret types (F1); abstention headline that is beta on a 102%-gross book
  (F2); weekend triple counting and look-back entry (F3); no live data and no scheduled grader,
  so the promised 10-13 grade cannot happen (F4); replay already broken by a concurrent change
  (F5); a grader that trusts the panel without reconciliation (F6).
