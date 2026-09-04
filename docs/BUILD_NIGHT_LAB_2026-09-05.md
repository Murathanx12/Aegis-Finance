# NIGHT LAB — 2026-09-05 — what ran, what it found, what it could not do

**For Murat, Saturday morning. Two pages. Scoreboard first.**
Everything is local and committed; nothing was pushed, deployed, sealed or
ordered. LLM spend: **$0.00** (no model was called — every job is arithmetic on
data we already own).

---

## RESULTS SCOREBOARD

| | |
|---|---|
| **Best historical net strategy vs the market** | unchanged: still none. B1's re-issued receipts stand (+28.3% vs +114.8% market). |
| **Best forward paper strategy** | none live — the fleet is flat by design until Monday. |
| **Independent selector count** | unchanged (1). |
| **New actionable finding** | **the daily reversal is dead at every size, and the LULU shape specifically is nothing.** One positive cell survives only below 25 bps. |
| **Best learner arm on the clean panel** | 4.91x vs market 3.34x over 90 months (+14.4%/yr) — and **DSR 0.197, SPA p 0.29, PBO 0.29**. Below the Sharpe a zero-edge search over 32 cells is expected to produce. **16.1 years needed for t = 2; we have 7.0.** |
| **Result improvement** | **NONE in P&L.** The improvement is in what we can now measure: `learner/inference.py`, and books that can hold a thesis. |
| **LLM spend** | $0.00. Cost per gradeable output: $0.00. |

---

## 1. THE MONDAY DELIVERABLE — B2 §1–6 SHIPPED

Terminal repo, branch `lab/night-2026-09-05`, commit `1cea12d`.
**Suite: 74 suites, 3,368 checks, ALL PASS.**
Runbook: **`docs/RUNBOOK_2026-09-08_REARM.md`** (terminal repo) — seven steps,
fifteen minutes, one decision.

What changed, in the order it matters:

1. **A strategy contract on every book and every sealed holding** — expected
   horizon, minimum normal hold, thesis expiry, hard falsifiers, risk budget in
   dollars, and the typed list of reasons that may close early. Inside
   `content_sha256`. **The seal now REFUSES a book without one.**
2. **`exits.py` obeys it.** Before the minimum hold (10 sessions on the tracker
   books) a close needs a typed reason: `DEADLINE`, `EXECUTION_CORRECTION`,
   `HARD_RISK_LIMIT`, `DATA_ERROR`, `THESIS_INVALIDATED`,
   `EXPLICIT_EVENT_STRATEGY_EXIT`. "The price moved 3%" is not one. The flat 3%
   stop becomes the **profile width** (the number the venue stop already used,
   and the one PANW's 0.52σ barrier came from); the +2.5% target is now
   per-contract and the tracker books declare **none**.
3. **The curfew is keyed to its own date.** `deadline_liquidation_due` returned
   True at 10:45 ET *every day* once the deadline had passed — with entries
   re-armed that is a fleet flattened each morning, for ever. The mandate end
   moved to 2027-12-31 (`AAT_MANDATE_END_UTC`), and `window_universe` follows it
   or every earnings print would be `TOO_LATE` and the event books would starve
   in silence.
4. **The re-entry guard sees every exit**, not only the venue's filled stops —
   one of four exit routes was covered.
5. **From the mega-11 finding:** `Mandate.allow_short` is now *read* (no book
   may open a naked short; the hedged pair is untouched); a close that fails
   after its stop was cancelled **re-places the stop** instead of leaving the
   position naked for 76 minutes; and the claimed move in dollars is compared
   with the stop in dollars on **every** admission.
6. **The horizon comes from the book, not from `--expiry`.** A 21-session thesis
   was being forecast at 4 sessions on a Monday and 1 on a Thursday.
7. **It is visible the next morning.** `scripts/utilization` prints
   ARMED/DISARMED and the binding constraint per role; the daily learning report
   gains **(c2) HOLDING DISCIPLINE** — the exit-reason census and the
   same-session round-trip percentage that would have caught the churn in a day
   instead of a month.

### One thing I changed from the instruction, and why

You approved "refuse when `expected_edge_usd < 3 × stop_loss_usd`". Implemented
literally and applied to every book, **that gate refuses one hundred percent of
what the tracker books select** — their own sealed `exp_return` is 1–3% against
a 6–8% profile stop, which is 0.2–0.4∶1. It would have emptied the accounts
this whole build exists to fill, on Monday morning, quietly.

So: the ratio is **computed and recorded on every admission** (it is a census
you can act on), and it **binds at 3∶1 on naked shorts**, which is the exact
population the finding indicts — a short share has no ceiling on its loss, so
the stop *is* the risk. All five PANW shorts fail it at 0.13–0.24∶1.
**Binding it further is your call, and now it comes with the numbers.**

---

## 2. THE LAB — `learner/inference.py` (L0), then the jobs

`nullbar.py` answers *"is this better than the same pipeline fitted on noise?"*.
L0 adds the three questions after it, and per-draw persistence so a null
distribution can be re-used instead of re-run:

- **Deflated Sharpe** — how many cells did the search open? At 60 cells, a
  zero-edge search is *expected* to produce a t above 2.
- **Hansen SPA** — is the best arm better than the best *alternative*, under a
  stationary bootstrap that keeps the serial dependence a persistent tilt makes.
- **CSCV / PBO** — would the ranking have survived a different split?

16 tests, on a **planted** world and a **null** world. A statistics module that
is only ever run on real data cannot be caught being wrong.

---

## 3. THE FINDINGS, one number and one null each

### L4 — your LULU question, measured. **The daily bounce is dead.**

1.8m mover-days, 2013–2024, entry at the **next session's open** (a fill a
person could take; a close-to-close "reversal" on a name that just fell 15% is
mostly bid-ask bounce), $5 price floor, costs charged per side.

| after a bottom-decile one-day drop | 10 bps | 25 bps | 50 bps |
|---|---|---|---|
| next session, every size quintile | −0.06% | **−0.36%** | −0.86% |

**For a large-cap name that dropped on an earnings print — LULU's actual shape
— five sessions later is −0.05% (t −0.34). Nothing.**

The one positive cell: **smallest quintile, no earnings event, five sessions**
— +0.579% at 10 bps (HAC t 5.70, non-overlapping t 4.16), +0.279% at 25 bps
(t 2.75), **−0.221% at 50 bps (t −2.18)**. It lives entirely inside the cost
assumption, on an 85-name equal-weighted basket of the smallest names we admit.
At the costs an 85-name small-cap basket actually pays, it is negative.

Two corrections I made mid-job, both of which changed the answer:
- the first cut printed **t −65** by counting *name-days* as periods. Every name
  that moved on the same session shares that session's market (CANON §58). One
  equal-weighted portfolio return per **session** is the honest unit.
- the 5-session series is **overlapping**: naive t 10.0 → HAC t 5.7 →
  non-overlapping t 4.2.

Event coverage was raised from 7,370 to **67,098** item-2.02 filings by mapping
tickers through CRSP `stocknames` *inside their validity window* — an 8%-mapped
event split puts 92% of real earnings days in the "no event" bucket and then
reports the difference between the buckets.

**Verdict: REFUTED** for the tradable daily reversal. The small-cap 5-session
cell is **CANNOT DETERMINE**, pending a version that models impact rather than
a flat bps.

### L12 — the mirror lane's −16%. **It is real performance, not a setup error.**

| lane | positions | equity at last close | authoritative NAV | gap |
|---|---|---|---|---|
| mirror | 12 | $82,772 | $83,441 | −0.8% (cash), **within tolerance** |
| conviction | 12 | $95,857 | $96,734 | −0.9% (cash), **within tolerance** |

The positions table and the NAV book agree. Read-only GETs; nothing written —
repairing a track record is attended by rule.

### L11 — Polymarket/Kalshi. **Three days.**

397 events, 14,669 rows, and the longest history on any single event is
**3 days**. Zero events reach 60 observations. Nothing here can be tested yet;
the receipt carries the test design and its earliest decision date instead of a
number. (This is the honest version of "we already collect Polymarket".)

### L8 — the sealed books. **Not matured, and that is the finding.**

10 books, 6,550 prediction rows, 104 holdings. **0 of 5 book-days have reached
21 sessions.** Grading a 21-session thesis on five sessions grades the noise and
sets the precedent of reading a book early whenever the number looks good. The
grading date is scheduled in the receipt.

### L13 — corpus → Railway. **332,065 rows, 218 MiB, laptop-only.**

Design written (`night_lab_2026-09-05/DESIGN_corpus_to_railway.md`): one cron
service on the authority's volume, collector keys only (no broker keys), and a
`fleet_health` check that asserts on **rows that arrived**, never on the job's
exit code. Not applied — the Railway change is yours.

### L1 — the learner on the clean panel. **The best book is 25% ahead of the market and it is still noise.**

32 cells: {ridge, lgbm} x {raw, residual} x {1, 3, 6, 12 months} x {10, 25 bps},
walk-forward 2017–2024, top-50 value-weighted, on the B1 clean panel.

| cell | months | TW net | TW market | ann. excess | paired t | turnover |
|---|---|---|---|---|---|---|
| `lgbm|residual|6m|10bps` | 90 | **4.906** | 3.337 | **+14.4%** | 1.10 | 0.77 |
| `lgbm|raw|6m|10bps` | 90 | 5.169 | 3.337 | +12.4% | 1.12 | 0.77 |
| `lgbm|raw|3m|10bps` | 93 | 4.430 | 3.549 | +11.8% | 0.91 | 0.83 |
| `ridge|residual|12m|25bps` | 84 | 0.659 | 2.814 | −17.4% | −1.98 | 0.40 |

Every one of the six best cells is LightGBM; every one of the three worst is
ridge. **12 of 32 cells beat the market at all** — barely more than a coin flip.
**No arm reaches t 1.2.**

Now the three tests L0 was built for, on the 84 months every arm shares:

- **Deflated Sharpe 0.197.** After 32 cells, the monthly Sharpe a *zero-edge*
  search is expected to produce is **0.2305**. The best arm's is **0.1439** —
  *below* what selection noise alone delivers.
- **Hansen SPA p = 0.291.** The best arm is not distinguishable from the best of
  the family under a stationary bootstrap.
- **PBO 0.286 — SELECTION_IS_FRAGILE.** In 29% of partitions the in-sample
  champion finished below the out-of-sample median.

**The honest sentence:** the best learner arm ends **4.91× against the market's
3.34×** over seven and a half years, and at a monthly Sharpe of 0.144 you would
need **193 months — 16.1 years — to reach t = 2.** We have 84. This is the same
shape as S39's "ranking skill is not money", now measured with the multiplicity
admitted. Note also that the best cell at **25 bps** is +8.8%/yr (t 0.68), not
+11.8%: a third of the headline is the cost assumption.

**Verdict: NOISE** by every test, with a large point estimate that the data
cannot resolve. Not "nothing is there" — "seven years cannot tell".

The `>=256-seed model null` is deferred: at ~8 walk-forward folds per cell it is
days of CPU for LightGBM, and the family-level tests above are what one night
buys. Two earlier runs of this job failed and wrote their tracebacks as their
receipts (a wrong arm name, then a pandas truth-value error) — the runner
working as designed. A third correction was silent and mattered more: the family
was being aligned by POSITION, so a 12-month arm's 2021 was being compared with
a 1-month arm's 2019. It is aligned on the intersection of months now (84 of
93–95), and the window is in the receipt.

---

## 4. CLAIMS FOR FABLE TO ATTACK

1. **The daily reversal is not tradable at any size** (L4 receipt, 1.8m
   mover-days, next-open entry). Attack: is next-open-to-close the right fill
   for a name that gapped, or does it already contain the bounce?
2. **The small-cap 5-session cell dies between 25 and 50 bps** — so the whole
   result is a claim about costs, not about returns. Attack: measure impact for
   an 85-name basket rather than assuming a flat rate.
3. **The 3∶1 edge-vs-stop floor is unsatisfiable for every long book we run.**
   Attack: is `|centre| / stop_fraction` the right ratio, or should the
   comparison be edge against `P(touch) × stop`?
4. **60% of round trips closing in-session was an exit-rule artefact, not a
   strategy** — and the contract fix is untested against a live tape until
   Monday. Attack: what does a 10-session minimum hold cost when the thesis
   really is broken on day 2?
5. **The mirror lane's −16% is performance.** Attack: the reconcile compares
   positions to NAV, not to the *seed*; a lane that silently changed holdings
   would still reconcile.
6. **The belief series has 3 days of history**, so every plan that leans on
   prediction markets is at least two months from a first test.
7. **The learner's +14.4%/yr is below the selection benchmark.** Attack: is
   `n_trials = 32` right when the panel, the features and the horizons were all
   chosen by earlier sessions that also looked at cells? The honest N may be far
   larger than 32, which makes DSR 0.197 an upper bound.

---

## 5. WHAT THE LAB COULD NOT DO, AND WHY

Honest list, not a schedule slip:

- **L2 (states), L3 (winner/matched-loser factory), L5 (customer momentum from
  MARKET-GRAPH-1), L6 (options → stock), L7 (psychology proxies), L9 (band prior
  on the live object), L10 (era replay v2)** — not run. The night went into B2
  (the Monday deliverable, which was the point) and into L0, whose absence would
  have made every later job un-gradeable.
- **The ≥256-seed model null for L1** — at ~8 walk-forward folds per cell that is
  days of CPU for LightGBM. The family-level tests (DSR / SPA / PBO) are what one
  night buys. The cost is stated rather than skipped in silence.
- **L1's feature ablations and quantile heads** — the variant loop in the brief.
  The base grid used the night; ablations are the next run of the same job.
- **L8's actual grades** — the data has not matured. Not a capability gap.

---

## 6. WHAT I WOULD DO NEXT, IN ORDER

1. **Monday: run the runbook.** Everything else is worth less than one week of a
   book that actually holds a thesis.
2. **L3, the winner/matched-loser factory.** It is the only queued job that
   attacks the *mechanism* question rather than re-measuring a known one.
3. **Decide the edge-vs-stop floor** with the census in hand — it is a mandate
   choice, not a measurement.
4. **Impact, not bps.** Two of tonight's results turn entirely on the cost model,
   and we are still asserting a flat rate.
