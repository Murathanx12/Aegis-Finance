# ORDER — brain → builder (order 15) — the daytime is not waiting, and the nights stop needing a human

Binding. Tree clean at `18506c8`, prod verified on `4545d48`. Murat's directive:
*"it is not valid to wait for 5pm — there is a lot to build, backtests to run,
novel things to find, and the nights must be automated."* He is right about the
waiting and the order below is the schedule that removes it. One clarification
first, so the directive is not misread:

**The 17:00 start is not the thing being waited for — it is the treatment.**
Fresh inputs are the tool arms' entire mechanism, and Order 14 §3 already ruled
that the judgement half of the programme cannot be moved into the day at any
price. What CAN fill the day is everything mechanical: the grader, the replays,
the library, the cost model, the product. That work is specified here, and none
of it touches an outcome that is not yet licensed.

---

## 1. P0 — the night launcher: no human at 17:00, ever again

Night 1 ran unattended once *launched*; the launch itself is still a person at a
keyboard at 17:00, which is exactly the honour-system input the house rule
forbids, applied to the calendar. Build the launcher today:

- **Fires at 17:00 local on XNYS trading days only** (the planner already derives
  the calendar; the launcher consumes it, never a weekday rule).
- **Readiness is recomputed AT LAUNCH, inside the launcher** — the derived
  latest-safe-start, the spend bound, `verify_or_refuse()`, the go/no-go criteria
  of `b4c64e2`. A refusal aborts the night and *says so loudly*. The launcher
  never carries a precomputed verdict from earlier in the day.
- **A refusing launcher and a dead scheduled task produce identical silence** —
  the canon's mirror rule, so both outcomes emit a receipt: `LAUNCHED`,
  `REFUSED(reason)`, or nothing-at-which-point-the-absence-is-the-alarm. The
  morning check reads the receipt, not the task's `running` flag.
- **Acceptance test: receipts on three consecutive trading dates.** Not
  `scheduler.running`, not a dry-run flag. Until three receipts exist the
  launcher is unproven and the attended fallback stays live.
- **Tonight (2026-08-18):** if the launcher has a clean rehearsal (sandbox night
  or refused-launch receipt) before 16:30 local, Night 2 is its first real
  firing. If not, Night 2 launches attended per the Night-1 procedure at 17:00
  and the launcher takes Night 3. **Night 2 is approved either way** — the
  standing 17:00 decision plus launch-time readiness is the whole authorization;
  nothing else is waited on.
- **The stop is derived, never remembered** — 17:39 was this morning's number,
  not a constant. The launcher reads it fresh.

## 2. P0 — the grader and pairing harness (Order 13 §7): everything else is unscored until this exists

First resolutions arrive **2026-08-21** (195 records at h=1) and **08-27** (390
at h=5). The attended `resolve_campaign_ledger.py` grades the ledger; **no IIF-1
grader module exists** to turn graded records into the campaign's paired
contrast. Build it now, against Night 1's receipt plus *synthetic* outcomes, so
that on 08-21 the attended run flows straight through:

- Pairing per Order 13 §7 (paired cells, per-arm, within-`implementation_version`
  and pooled — the version-2 boundary is already stamped).
- The loss is the frozen one: Brier on `abs_move_exceeds`. **Every Brier read
  prints the base rate beside it** — Opus's own trap note from `18506c8`, now a
  requirement, because rare events shrink `base·(1−base)` and a Brier without
  its base rate is a number without its power.
- The read gate stays closed: the grader must be runnable on synthetic outcomes
  end-to-end while **refusing** to touch `campaign_forward` records before
  `check_read` licenses a look. That refusal ships with the missing-input test
  the canon requires.
- MDE at the 40-night look, computed forward (§64) from the base rate and n —
  printed now, before any outcome exists, so the first licensed read arrives
  with its detectability already on record.

## 3. P1 — the backtests that are valid to run today

All screen-grade (§63: BH-FDR, m = tests run), all mechanical (Order 14 §3:
rules replay cleanly, judgement does not), all with `k_eff` counted in date
blocks and printed beside every result, all with tradable fraction and arrival
time attached (§62). Pre-register each batch before it accrues.

1. **Insider / Form-4 disclosure-delay replay** — buy at *disclosure
   publication*, never at trade date. The live trials (`TRIAL-INSIDER-IC` etc.)
   keep accruing untouched; this is the historical breadth-of-condition half.
2. **Politician disclosure-delay replay** — same rule, and it doubles as Track
   E's groundwork: the replay's delay distribution IS the tradable-fraction
   question for TEACHER-LIBRARY-1.
3. **The cost model, corrected before it flips more verdicts:** implement
   Corwin–Schultz effective-spread estimation from daily OHLC (computable from
   data we already hold), replace the flat-bp assumption, and re-price the
   206-predictor panel and the N25 tercile verdicts. This is an **instrument
   correction, not a new hypothesis** — it spends no calendar. A survivor count
   quotes its cost rate or is not quoted.
4. **The rare-event library** (Order 14 §6.3) — coverage is the binding limit
   (~86% of exceptional moves had no precursor); the library attacks coverage
   directly. Winner vs **matched loser** from the first row; tradable fraction
   and arrival attached from the first row.

## 4. P1 — the novel direction, stated as a budget fact

The research line closed for *return* claims because §58/§59 price them at ~95
years. The same arithmetic prices two other claim types cheaply, and their
intersection is where novelty is affordable:

> **Relative claims are cheap (§58: the cross-section still adds). Risk
> outcomes are ~30× closer (§59). The affordable frontier is therefore
> CROSS-SECTIONAL RISK RANKING — and it is exactly what the /risk product
> (M6) needs as an engine.**

Authorized screens on that frontier, in order:

- **Does options-implied information improve next-month per-name risk ranking?**
  (IV skew / term structure vs realized vol and drawdown rank.) IV-ORACLE-GAP-1
  survives the errata; this is its risk-outcome descendant. Rank-correlation
  primary, §64 power check at reservation, screen grade.
- **Does the denoised covariance improve realized portfolio-risk forecasts vs
  sample covariance, cross-sectionally?** Forecast-evaluation only — Graph-
  Covariance-1 closed the *min-variance-solve* route, not risk forecasting, and
  scope-aware verdicts say a closed route does not close the conditional
  question never asked. Cite the corpse in the registration.
- **Sizing on RISK (§59, roadmap):** does the risk layer's exposure scaling
  reduce realized drawdown on the reserved-window-respecting slice, stated as a
  bound (`UCB(drag) < break_even(λ)`, λ declared)?

These feed M6 directly: the product's honest claim is *"risk reduced /
risk ranked; return effect not established"*, and every screen above either
strengthens or bounds that sentence.

## 5. Attended items — queued for Murat, nothing operational blocked

- **The LOSS registration gap** (`18506c8`): draft the amendment declaring
  Brier-on-`abs_move_exceeds` + base-rate-reporting as the registered loss,
  for Murat to approve before the 40-night read. Drafting is a session's work;
  registering is his.
- **Track E (TEACHER-LIBRARY-1) pre-registration draft** — precondition met
  (Night 1 clean). Draft per `pre-register-trial`: STOCK-Act mean-politician
  null as prior, 13F-popularity corpse as H3 control, §64 forward power at the
  intended n. Registration attended.
- **`iif1_read_gate.check_read` enrolment** — lives in the Aegis module
  sibling; cannot be done from this repo. Standing prerequisite before night
  40; next Aegis-module session takes it.
- **2026-08-21: first attended resolve run** — calendar item, his keyboard.

## 6. Standing

- **A launch is an action; an unattended campaign with an attended launch is
  attended.** Automate the launch or the campaign's cadence is a person's
  calendar wearing a cron costume.
- **Grade-readiness precedes accrual-readiness.** Records due in three days
  with no grader is Order 13's open loop; the harness is P0 over every new
  accrual.
- **An instrument correction spends no calendar** — re-pricing existing results
  under a measured cost model is maintenance of the ruler, not a new test. New
  *hypotheses* still register.
- **The affordable frontier is relative × risk.** Return claims cost ~95 years;
  spend novelty where the arithmetic says it can resolve.

— brain, 2026-08-18
