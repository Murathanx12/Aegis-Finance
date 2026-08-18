# 2026-08-18 — the launcher, the grader, and two numbers that were being quoted wrong

Order 15 §1 and §2 (both P0) are built. Two findings came out of building them,
and both are of the house type: a number that was right about one quantity being
read as if it were about another.

---

## 1. FINDING — 17:39 is not a launch time. Tonight's launch boundary is 17:02.

The derived stop everyone has been quoting is `next_open − duration_bound`
(13:30 UTC − 230.7 min = 09:39 UTC = **17:39 local**). That is the latest safe
**start of the run**.

`assert_night_fits_before_open` is called from inside `run_night()` — which
happens **after** `iif1_run` has assembled and frozen the snapshot. Assembly is
not free: Night 1's receipt records `decision_lag_minutes = 18.22`, because
assembly walks the whole universe through yfinance and EDGAR.

So a launcher that fires at 17:39 starts assembling at 17:39, reaches the guard
at ~17:57, and **is refused by it**. The launch boundary is the run boundary
minus an assembly allowance:

```
assembly_allowance = min(MAX_DECISION_LAG_MINUTES,            # 45, the cap the
                                                              # staleness guard
                                                              # itself enforces
                         worst measured assembly x DECLARED_DURATION_SAFETY_FACTOR)
                   = min(45, 18.22 x 2.0) = 36.4 min

latest safe LAUNCH = 17:39 − 36.4 = 17:02 local
```

**The standing 17:00 start therefore clears by 2.9 minutes, not 39.** It passes.
It passes by an order of magnitude less than the headline number suggests, and a
reader who remembered "17:39" would have launched half an hour into a window
that no longer existed.

The cap is the load-bearing half of that formula: `assert_decision_time_fresh`
refuses any snapshot older than 45 minutes, so an assembly longer than that
cannot produce a paid run at all — which makes 45 the true worst case and
anything derived above it fiction. With zero completed nights the cap governs,
which is the conservative direction.

This is the two-clocks finding's third consequence. The first two were named on
08-17; nobody had drawn this one, because `decision_lag_minutes` was written to
every receipt and **read back by nothing**.

## 2. FINDING — the campaign's power is dominated by a correlation nobody had measured

§64 says a power check that consumes no outcome is free and therefore
obligatory. For IIF-1 it needs exactly two inputs, both available today: the
arms' forecast **disagreement** (in the ledger since the night it was minted)
and a **base rate from history**. Neither is an outcome.

Measured on the Night-1 universe (40 names, 3y daily):

| registered cell | base rate | RMS \|f_B − f_A\| | ρ measured | design effect | **MDE @ 40 nights** |
|---|---|---|---|---|---|
| `abs_move_exceeds` h=1 thr=0.03 | 0.0972 | 0.127 | 0.074 | 3.88 | **0.0104** |
| `abs_move_exceeds` h=5 thr=0.05 | 0.1963 | 0.148 | 0.061 | 3.39 | **0.0153** |

Three things follow.

**The arms do disagree.** RMS forecast difference is 0.13–0.15, so the paired
contrast is not structurally undetectable. Forty nights is not buying nothing —
which was a live possibility and is now checked rather than assumed.

**ρ is the dominant term, and it was an assumption.** The MDE at ρ = 0 is
0.0054 / 0.0084; at the *measured* ρ it is **1.8–1.9× larger**. With ~40 names
per night, even a ρ of 0.06 produces a design effect near 3.5. The ρ = 0 figure
is an optimistic floor and is labelled as one in the code
(`OPTIMISTIC_FLOOR_INDEPENDENT_OUTCOMES`); the number to plan with is the
measured one.

**The two thresholds cannot share an MDE.** Their base rates differ two-fold
(0.097 vs 0.196), so power is reported per registered cell and never pooled
across them. The refusal that enforces this caught a real error while it was
being written: a climatology had been measured for `(h=5, thr=0.03)`, which is
not one of the three registered cells. The actual cells are
`(abs_move_exceeds, 5, 0.05)`, `(abs_move_exceeds, 1, 0.03)` and
`(return_sign, 5, None)` — so the **08-21 resolutions are the frozen loss
observable**, not `return_sign` as the horizon counts alone suggest.

**What is still owed:** the number this MDE has to be compared against — the
smallest paired Brier difference that would matter — is not declared anywhere.
§64 says it is recorded at *reservation* time. It should be declared before
2026-08-21, not after seeing a result.

## 3. Gap found: Night 1's receipt carries no `implementation_version`

`run_night` stamps `implementation_version` and `arm_implementation_fingerprint`
onto the result — but that line postdates Night 1, so the **only completed night
in the campaign has no version stamp**. The within-version contrast Order 15 §2
requires therefore has a hole exactly at the boundary the field exists to mark.

The grader reports that night as `UNSTAMPED` rather than coercing it to `1`.
Filling the hole with the version we *believe* it ran turns an inference into a
record, and the whole reason a declared version sits beside a derived
fingerprint is that the two can disagree. Night 2 onward will be stamped.

---

## 4. Built — the night launcher (Order 15 §1)

`backend/services/night_launcher.py` · `scripts/run_night_launcher.py` ·
25 tests in `backend/tests/test_night_launcher.py`.

- **Fires 17:00 local on XNYS trading days.** The calendar is read, never a
  weekday rule; the `WEEKLY /D MON-FRI` in the registration is a coarse
  pre-filter that only avoids waking the machine on Saturdays.
- **Readiness recomputed AT LAUNCH.** Calendar, calls/cell, duration bound,
  assembly allowance, frozen pre-registration — all re-derived at the moment of
  the decision. The launcher never carries a verdict from earlier in the day.
- **Refusal codes, each a derived check:** `NOT_A_SESSION`,
  `NOT_PREOPEN_WINDOW`, `PAST_LATEST_SAFE_LAUNCH`, `ALREADY_ATTEMPTED`,
  `ACCRUAL_COMPLETE`, `PREREG_UNREADABLE`, `SESSION_DATE_DISAGREEMENT`.
- **`SESSION_DATE_DISAGREEMENT` is new and it fires today.** The night stamps
  its snapshot by the New York date; the guard forecasts the next XNYS open. On
  a pre-open run those must be the same day. Before NY midnight they are not,
  and a receipt would be filed against a session it did not forecast.
- **Every outcome writes a receipt** — `LAUNCHED`, `REFUSED(code)`,
  `REHEARSAL`. The receipt is written **before** the night starts, so a night
  that dies mid-run still proves the launcher decided to run it.
- **If the receipt cannot be written, the launcher refuses to launch.** A
  refusing launcher and a dead task produce identical silence; an unattended
  run whose evidence may not exist is worse than a night not run.
- **One attempt per night, no retry.** A void night counts as an attempt (it
  named a population); a torn receipt counts as an attempt (the filename is the
  session date). Compensating for a refusal with an unregistered second attempt
  is how a campaign buys nights nobody reserved.
- **Acceptance = receipts on 3 consecutive XNYS sessions**, computed from the
  receipt files. Never `scheduler.running` — prod has already demonstrated all
  seven jobs registered and running while every tick refused.

### The acceptance criterion had a hole, and it is closed

As first built, a hand-run rehearsal receipt was indistinguishable from a
scheduled firing — so acceptance was satisfiable by three afternoons at a
keyboard, which is the honour system the launcher exists to remove re-entering
through its own acceptance test.

Now only receipts declaring `invocation_mode = scheduled` count, and the
declaration is recorded beside a derived observation (`sys.stdin.isatty()`) that
can contradict it — the same declared-vs-derived pattern as
`implementation_version` beside `arm_implementation_fingerprint`. Its limits are
stated in the code rather than implied: it catches a human in a terminal copying
the registered command line; it does not catch a deliberately detached console.
Excluded receipts are printed, never silently subtracted.

**Arming is env-gated and attended.** `AEGIS_IIF1_LAUNCHER_ARMED=1`. Unarmed,
every firing writes a `REFUSED / NOT_ARMED` receipt — which is exactly how the
three acceptance receipts can accrue at zero cost before anything is armed.

## 5. Built — the grader and pairing harness (Order 15 §2)

`backend/services/iif1_grader.py` · `scripts/iif1_grade.py` ·
30 tests in `backend/tests/test_iif1_grader.py`.

- **Two access modes, enforced by deletion.** `MODE_POWER` strips `outcome`,
  `brier`, `resolved_at`, `resolution_detail` at load, so the power path cannot
  read an outcome because it does not have one. A comment saying "this does not
  look at outcomes" is the honour system; deleting the field is not.
- **The read gate is handed a DERIVED count.** `check_read` still takes
  `n_graded_nights` as an input — the last outstanding item on the canon's
  honour-system list, and it lives in the sibling repo. Nothing in this repo
  supplies that number from anywhere but a count of receipts on disk. If the
  sibling cannot be imported the read is **refused**, not reimplemented: a
  second copy of a read schedule is a second thing that can drift.
- **Every Brier carries its base rate**, structurally — they are the same dict.
  Plus the Brier skill score against a PIT climatology (never against the
  scored sample's own outcomes) and Murphy's
  reliability/resolution/uncertainty. A degenerate base rate (0 or 1) is
  refused: `p(1−p)` is zero, no skill score is defined, and the score computed
  anyway is a fact about the sample read as one about the forecaster.
- **The unit is the NIGHT.** 585 paired records is n = 1, not n = 585. Each
  night contributes one mean paired difference; SE is `max(IID, HAC)` across
  nights. With one night the t-stat is `None` — a standard error over one date
  block is undefined, not small.
- **Night attribution is a derived interval join** from measured
  `arm_started_at`/`arm_finished_at`, not a date-string match (which would look
  right for every pre-open night and mis-file every post-close one). A record
  matching zero or ≥2 nights is refused, never nearest-matched — that would
  cross the version boundary silently.
- **Within-version AND pooled**, per Order 15 §2.
- **Pairing drop accounting names the arm.** A failure mode available only to
  the tool arms is a bias with a direction, toward the null.
- **The synthetic path refuses any record declaring
  `evidence_population=campaign_forward`.** The one path with no read licence
  must not be usable to read the real thing early; a test flag is not a licence.
- Verified end to end: an injected `+0.15` edge on `B_tools` is recovered as a
  negative mean paired difference with higher resolution, on synthetic outcomes
  only, with the campaign untouched.

## 6. Fixed — the GitHub notification flood

Two defects, neither about prod being broken. On 2026-08-17 the monitor sent
~14 notifications and failed three of its own runs.

1. **The alerter's own lookup could kill the alert.** `gh issue list --search`
   goes through the search API, which is separately rate-limited and
   transiently 5xx's; GitHub Actions runs `run:` blocks under `bash -e`, so a
   failing command substitution aborted the step **before** the alert was
   written. Runs 131/136/137 all failed at that exact step with the health
   check itself reported success. The failure mode was: prod degrades, the
   lookup flakes, no alert is written, and the only signal is a red workflow —
   an alerter that goes quiet precisely when it is needed. Now: plain REST list
   filtered client-side, three retries, and a lookup that still fails fails
   loud.
2. **One condition, nine emails.** A single continuous DEGRADED state produced
   one comment per tick for five hours, none carrying new information. Now the
   condition carries a signature (`status|ledger|fresh|why`); a **changed**
   signature comments, an **unchanged** one silently edits the issue body with
   a tick counter. Editing sends no notification, so the state stays visible
   and the inbox stays readable.

Also: `concurrency` group added (two overlapping runs could both create an
issue), the reasons are now in the alert instead of just the verdict, and the
`jq`+`sed` parse was replaced with `python3` — not style, but because `jq` is
absent from the dev machine, so a jq-based body could only be tested by pushing
it and watching the inbox, which is how this got into the state it was in. All
seven branches were exercised locally against a fake `gh`.

**What the flood was actually reporting:** `prediction_ledger` read DEGRADED
because 25 forecasts were past due while QUARANTINED — the resolver refusing
them on purpose. That is the actionable-vs-deliberate split, and it was fixed in
the app (`4545d48`/`18506c8`), not here. The monitor was right to be loud once
and wrong to be loud nine times. Prod is `ok` now, `all_fresh` true.

---

## 7. What is attended, and what tonight looks like

**Night 2 should run attended tonight**, per the Night-1 procedure. The launcher
is built, tested and rehearsed, but arming it is Murat's decision and acceptance
(three scheduled receipts) is three sessions away by construction.

The path that costs nothing and gets there fastest: register the task now,
**unarmed**. It fires at 17:00 on each trading day, recomputes readiness, and
writes a `REFUSED / NOT_ARMED` receipt. Three of those and the launcher is
ACCEPTED, at zero dollars and with no night at risk.

```
python -m scripts.run_night_launcher --schtasks     # prints it; runs nothing
python -m scripts.run_night_launcher --acceptance   # where the streak stands
```

Arming, later and separately: `set AEGIS_IIF1_LAUNCHER_ARMED=1`.

Still attended and unchanged: the LOSS amendment draft, the Track E
pre-registration draft, the 2026-08-21 resolve run, and
`iif1_read_gate.check_read`'s enrolment in the sibling repo.

**One number to carry into tonight:** the launch boundary is **17:02 local**,
recomputed at every firing and printed by `--dry-run`. Do not quote it from
here tomorrow — it moves with measurement.
