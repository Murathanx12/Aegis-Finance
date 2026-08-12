# NIGHT-14 DISCHARGE — 2026-08-12

What was asked, what shipped, what refused, what is still owed. Contract:
`NIGHT14_BRIEFING.md`. Source material: `NIGHT14_EXTERNAL_REVIEW.md`.

---

## §1 — The one sentence

**The bottleneck was never call volume. It was grading latency.**

`HORIZONS` started at 5 trading days, so every specialist forecast was
unfalsifiable for a month and the ledger's first grade fell on **2026-09-12**.
Adding calls to a system that cannot grade them faster buys more unlabelled data
at higher cost — the failure the external review warns about in its §8 while
proposing more calls in its §1.

**Measured result: earliest resolution moved 2026-09-12 → 2026-08-16.** The
explanation layer's grading latency went from 31 days to **under a minute**,
because cross-asset corroboration is a claim about a day whose prices are
already known.

---

## §2 — The answers Murat is owed (briefing §8)

### 1. Why it could not learn before, mechanically

Two dead wires, both green. NIGHT-13 found the first: `resolve_all` had no
caller. Tonight found the second: **`LEDGER_DIR` resolved inside the container
image while the persistent volume is `AEGIS_DATA_DIR`**, so every record the
nightly specialists wrote was destroyed by the next deploy. The forward
calibration clock starts at the first written record and cannot be backfilled,
so it was silently restarting at zero, repeatedly. *A ledger that lost its
history looks exactly like a ledger that was always young.*

Both are fixed and **verified in production**: the migration logged
`copied 112 record(s)` + `copied 37 record(s)` to `/data/optimus/`, and
`prediction_ledger.persistence` reads `under_data_dir: true, status: ok`.

### 2. What actually happened to his book

Deterministic, no LLM, and **independently re-verified by me against a second
price fetch**:

| | |
|---|---|
| Day of record | **2026-08-10** (08-11 refused: Yahoo had SPY's close but not 11 of 12 book names) |
| Book | $40,625.50 → $40,392.60 |
| **P&L** | **−$232.90 (−0.573%)** |
| SPY | −0.03%, book beta **2.19** |
| Market leg | −$26 |
| Sector leg | **+$461** |
| Idiosyncratic | **−$667** |

Worst: AARD −4.30% (−$340), AMSC −5.43%, PRCH −2.65%, QUBT −2.72%.
Best: **SOC +7.16% (+$238)**, HUBS +2.59%, ABSI +0.90%.
Contributions sum to −232.90 exactly. Confirmed independently: SOC +7.16%,
AARD −4.30%, XLE +4.66%, CL=F +5.05%.

**His "lost 1k yesterday" does not reproduce on the reconstructed book.** Recent
days: 08-06 −$320, **08-07 +$1,890 (+4.88%)**, 08-10 −$233. The week 08-05→08-10
was **+$1,337 (+3.4%)**. So *"it increased a lot this week"* is **corroborated**;
the $1,000 loss is **not**, on this reconstruction. Either the real book differs
(cash, share counts, positions we do not hold) or he means another day. **Second
night running that the broker CSV is the binding constraint.**

### 3. Whether any specialist's story was actually true

21 hypotheses, 6 lenses, **4 rejected as ungradeable**, 25 forecasts minted.

**The first headline was circular and I caught it.** Scoring said 89% (40/45) —
but the prompt hands each lens the book's own returns, the benchmark's, and each
held sector's, so "XLE up" from a lens just told *Energy +4.66%* is the input
read back.

| class | record |
|---|---|
| book tickers (return given) | 4/4 = 100% — tautological |
| sector ETFs + SPY (returns given) | 20/22 = 91% — largely derivable |
| **strictly external** | **16/19 = 84.2%** ← the only quotable number |

The split is computed from the prompt payload itself, so adding a prompt field
moves it automatically instead of rotting. The artifact was **re-scored, not
re-run** — repairing arithmetic with fresh model calls would have written a
second batch of correlated forecasts about the same day.

**84.2% is a COHERENCE score on n=19 from one day. It is not skill and must
never sit beside a Brier score as if it were the same currency.**

### 4. Selection versus sizing (`WINNER-GENOME-1`)

**Verdict: DISPERSION_ONLY.** 220 windows × 2,600 teams, prereg committed
before compute, search denominator 72.

- **Not one of five families shifts the median above its own MDE** (deltas
  +0.079/−0.023/−0.033/−0.010/−0.080pp vs MDEs 0.402/0.033/0.392/0.116/0.314pp).
- But **max over 2,600 draws = 185–208%**, p5 = −10 to −17%. The leaderboard
  reports a tail; the +195% winner has an uninterviewed cousin at −59%.
- P(produces the winner): volatility **32.5%**, speculative underdogs 25.9%,
  **random-at-matched-volatility 14.2%**, sector-concentrated 12.5%,
  momentum+volume 7.5%, quality-momentum 3.2%. **Equal-weight and large-cap:
  0.000 across 44,000 simulated fields.**
- **Sizing dominates and it transfers.** Inverse-vol beats the tournament's 20%
  cap on *both* return and drawdown in *every* family (e.g. F4 CAGR 9.82→10.61%
  with drawdown −55.5→−50.5). **The family most likely to win the contest has
  the worst career CAGR (4.3%) and worst drawdown (−75%).**

Run for twenty years instead of five weeks, the tournament budget carries a
**24–37% chance of losing half the account**. The tournament objective and the
wealth objective are close to opposed — now measured, not asserted.

**Fourth independent confirmation of the standing bet: the edge is in selection,
the losses are in management and sizing.**

### 5. Fable vs Opus — bounded

**14/14 vs 14/14 across both tiers. Saturated ⇒ the benchmark cannot rank
them.** Tier 1 (8 real shipped defects): all four arms 8/8 at near-identical
tokens (~50k) and 84–97s. Tier 2 (6 harder, including a trap with no defect):
both 6/6, neither fooled. Opus verified numerically (Monte Carlo,
leakage simulation); Fable reached identical conclusions analytically with fewer
calls.

**My own answer key was wrong twice and both models beat it** — the H3 drawdown
direction (corrected before grading) and an H4 "most likely overturner" that was
opinion graded as fact. Recorded in `NIGHT14_MODEL_BENCH.md`.

Rules out one thing only: a large per-task quality gap in either direction.
**The overnight-autonomy question stays open**, and NIGHT-13-vs-an-Opus-night is
not a comparison because the tasks differed. Also observed: **Fable ran out of
usage credits mid-benchmark.**

### 6. Still owed

See §5 below.

---

## §3 — Defects found tonight

| # | Defect | Status |
|---|---|---|
| F7 | Ledger inside the image ⇒ destroyed every deploy, calibration clock silently restarting | **fixed + verified in prod** (112+37 records migrated) |
| D1 | `call_id` collisions deduped 4 of every 5 telemetry rows ⇒ **spend read as 1/5 of truth** | fixed (salt = pid + in-process counter; Windows clock granularity ~15ms is coarser than the call rate) |
| D2 | `schema_valid` would rubber-stamp any HTTP 200 | fixed — takes the caller's contract as a predicate |
| D3 | **Corroboration hit rate circular** — prompt supplies the answers | fixed; external-only is now the headline |
| D4 | `macro_rates` ×3 rejections for recommendation language — one lens, systematic tic | counted; rejections now retain `matched_terms` + excerpt (they previously kept no trace, making the count unauditable) |
| D5 | Lens JSON truncated by a 2,400-token ceiling ⇒ wasted call | ceiling raised to 4,000; re-run produced 4 clean hypotheses |
| D6 | `why_moved` was the one uninstrumented LLM path | wired + 3 tests |
| D7 | `pytest-timeout` declared in requirements but **not installed locally** ⇒ CLAUDE.md's "un-hangable" guarantee was inert on this box | installed |
| D8 | Scheduler job-set canary absent (NIGHT-13's rolling-deploy deletion) | added; live block shows expected/actual/missing/unexpected |

**Known weakness, not a defect, stated plainly:** 23 of the first 25 forward
claims were 1-day `return_sign` at **p=0.50**. That accrues records fast and says
nothing — *a coin flip you called a coin flip is not a forecast.* The prompt now
demands horizon and observable variety; **that change is unvalidated live** and
is the first thing to check on the next run.

---

## §4 — Live verification (verify-prod-after-deploy)

Deployed `3344fc7`. CI green → commit flipped → surfaces exercised for
**content**:

- `status: ok`, `degraded_reasons: []`
- `scheduler.jobs`: expected == actual, `missing: []`, all 5 jobs
- `prediction_ledger.persistence`: `/data/optimus/predictions.jsonl`,
  `under_data_dir: true`
- `prediction_ledger`: **112 records**, 6 void, **0 overdue**, last_written
  2026-08-12, 12 distinct specialists
- `/api/why-moved/lenses` — real lens prompts
- `/api/why-moved/attribution?as_of=2026-08-10` — **−$232.90, beta 2.19, 12
  positions**, matching local exactly
- migration WARNINGs present in `recent_warnings`, as designed
- pre-existing Google Trends 429 unrelated to this change and correctly
  disclosed as unavailable

Local: **3491 passed, 3 skipped, 0 failed** (19:00).

### The loop is armed (final state, `2a3b78c`)

`pi_why_moved` was added AFTER the first verification, which is the exact
NIGHT-13 hazard — a new scheduler job whose target the old replica cannot
deserialize from the shared jobstore. **This time the canary was there to check
it, and the job survived**: 6 of 6 live, `missing: []`, `unexpected: []`.

| job | next run |
|---|---|
| `pi_congress_collect` | 07:30 ET |
| `pi_hourly_mtm` / `pi_daily_check` / `pi_ledger_resolve` | 16:30 ET |
| **`pi_why_moved`** | **17:15 ET** |
| `pi_weekly_aggressive` | Mon 09:00 ET |

Ledger: 112 records on `/data/optimus/predictions.jsonl`, 0 overdue, status ok.
**First resolution 2026-08-16.** From tonight it runs without anyone asking it
to.

### One CI failure worth recording

The `pi_why_moved` commit failed CI on `assert len(jobs) == 5` in
`test_scheduler.py` — a hardcoded count sitting beside five membership checks.
The irony is the point: that is the same shape as the `/health/scheduler` gate
which could not see NIGHT-13's vanished job. **A number is a weak proxy for a
set and fails in both directions** — it breaks on a correct addition and stays
silent when two jobs swap. Replaced with set equality against
`EXPECTED_JOB_IDS`, so a correctly-added job now needs no edit to that test at
all. Same class as NIGHT-13's hardcoded QUBT pins: local runs passed because I
ran the canary file, not that one.

---

## §5 — Refusals and what is still owed

**`THEME-CASCADE-1` — BLOCKED, and the refusal is the finding.** The external
review's most exciting original idea (second-wave beneficiaries; the SK Hynix /
SanDisk / WDC / Kioxia / Vicor pattern) **already has a well-powered corpse in
our own registry**: `TRIAL-THEME-SUPPLY` with noise check PASSED, micro arm
−80.8 bps/mo at t=−4.27, decisive **B−A spread t=0.10**, DSR 0.043 → REJECT;
plus `cust_mom` REJECT at monthly cadence. Both ends of the clock closed.
`lint_prereg.py` agrees independently: **BLOCKED vs 317 prior experiments**.
**No registry row created** — a draft stopped at the gate must not inflate the
denominator future promotions are deflated against. A legitimate resurrection
needs all four of: a different link source (an LLM graph is a different object
from disclosed `seg_customer` links, and its error rate must be *measured*), a
different claim (crowding/re-rating differential, not momentum diffusion), a
daily event-conditioned clock, and selections frozen before inspection.

**Deferred, with reasons** (unchanged from briefing §2): shadow-book seeding
(attended — inventing a seed path risks a fake inception); MCP context-health
fields; Portfolio Gym and EXIT-RL (behind synthetic known-answer worlds — prove
the learner recovers a *planted* rule before believing one it finds); the
contextual-bandit router (blocked until the reliability tensor has usable n —
a router built now would route on noise and then justify its own allocation);
intermediate non-price observables (they add a vendor whose definition can drift
to the resolution path); the three-risk-budget product surface.

**Carried into NIGHT-15:** verify the ledger survives a *second* real deploy
(tonight proved the migration, not the steady state); check whether the
forward-claim variety fix took; `/health/scheduler` still gates on `n_jobs >= 3`
(left alone because changing its 503 changes an UptimeRobot canary — the prod
monitor is already covered because it gates on top-level status); no frontend
page for WHY-MOVED.

**From Murat: the broker CSV, Aug-2025 → Aug-2026.** Two nights running it has
been the binding constraint, and tonight it became concrete — the engine can now
compute his P&L to the cent but cannot reconcile it to what he remembers.
