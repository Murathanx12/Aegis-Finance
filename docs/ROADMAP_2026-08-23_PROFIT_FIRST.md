# ROADMAP — 2026-08-23: profit-first, three licenses

**Status: ADOPTED.** Supersedes the ordering (not the content) of
`docs/ROADMAP_POSITION_2026-08-21.md`. Murat's ruling of 2026-08-23 is the
attended decision this encodes.

---

## 0. The correction

The mission has said since 2026-08-15 that the objective is **terminal wealth
under a declared utility**, that the paper is the *third* deliverable, and that
**the methodology is the guardrail, not the mission**. The operating queue had
drifted back into treating the guardrails as the mission: five months in, every
gate that could block work was blocking work, and the demonstrated market edge
is 0%.

The correction is one sentence, and it is not "abandon the discipline":

> **Research rigour determines what Aegis is allowed to CLAIM. It must not
> determine what Aegis is allowed to TEST in paper.**

A hypothesis may enter paper trading tomorrow because it is interesting. It may
not become "validated alpha" tomorrow. Those are different permissions, and
conflating them is what stalled the programme.

---

## 1. Three licences

One evidence standard was accidentally governing everything. From now on there
are three, and every artefact names which one it holds.

| Licence | What it permits | Required before it starts |
|---|---|---|
| **`PRODUCT_EXPERIMENT`** | internal simulation and **external PAPER brokerage** | a frozen strategy contract *before the first decision*: policy hash, timestamp, declared inputs, costs, fill convention, objective. **No statistical-significance gate. No 24-month floor. No preregistration.** |
| **`CAPITAL_CANDIDATE`** | candidacy for real money | matured forward evidence, realistic costs, calibration, utility improvement under the declared personality, drawdown/ruin bounds, robustness. Promotion stays **attended**. |
| **`RESEARCH_CLAIM`** | "this is alpha" — a paper, a public skill claim | full preregistration, MDE, multiplicity control, matched controls, foreign/holdout validation. Every standing evidence rule remains binding. |

`PRODUCT_EXPERIMENT` already exists in the code as the arena's
`validation_status` — this promotes it from a label to a licence with declared
powers.

### What does NOT relax

PIT discipline · frozen information states · realistic execution and costs ·
immutable policy versions · outcome provenance · no training on future
information · **no LLM authority over real capital** · no backfilled forward
evidence · no mutation of seeded book histories.

### Rules explicitly amended

Per the standing requirement that a conflicting rule be *quoted and amended*,
never silently ignored:

1. **24-month skill floor** (inception 2026-06-08, "no skill claims before
   24mo"). **Unchanged for claims.** It never governed launching a paper
   challenger, and is hereby stated not to.
2. **`pre-register-trial` skill — "if it isn't pre-registered, it didn't
   happen" (CANON §6).** **Amended in scope:** preregistration is required
   before a `RESEARCH_CLAIM` accrues. A `PRODUCT_EXPERIMENT` requires a frozen
   strategy contract instead — strictly weaker, and still tamper-evident.
   §6 continues to bind anything that will be *claimed*.
3. **CLAUDE.md — "not a trading bot / no position sizing / no live orders /
   not real-time".** **Factually stale**; scoped in §5 below.

---

## 2. What was measured this session (not asserted)

### 2.1 The learning loop was never dead

`/api/health/full` reported the deploy DEGRADED on `no new forecast in 11
days`, and that was read — by an external reviewer, and very nearly by this
session — as the continuously-learning engine having stopped.

**It had not.** Measured live:

| | records | last written | status |
|---|---|---|---|
| `live_forward` | 112 (all campaign copies) | 2026-08-12 | genuinely quiet — a real G7 problem |
| `arena_forward` | 25 beliefs, 151 experiences | **2026-08-21** (last trading session) | **healthy** |

Two populations, two files, one alarm that named neither. The arena ledger had
**never appeared on any health surface** — not refused, simply never
enumerated. This is structurally the same bug as the WRDS pull reporting
complete with seven tables never attempted: *a check that reads the record of
what happened cannot see what was never asked for.*

Fixed by `backend/services/forecast_populations.py`: every population declared
with producer, consumers, purpose and its own quiet clock; health computed
**per population**; pooling refused; and a suite test that **fails when a
`predictions.jsonl` appears that no population claims**.

Consequence for the roadmap: **G7 is not blocked by a dead scheduler.** It is
blocked by `live_forward` having no producer writing to it. That is a
different, smaller problem than the one the alarm implied.

### 2.2 The overnight claim — tested, and it does not survive as a strategy

Murat's lead (buy at close, sell at open) tested on the CRSP daily panel,
2013–2024, 11.3M stock-days, 3,019 sessions, common stock on NYSE/AMEX/Nasdaq.
Decomposition reconciles to CRSP's own `retx` on **all but 173 of 11,297,614
rows (0.0015%)**.

**Window limit, declared:** the claim is stated "since 1990". The pre-2013 CRSP
years on disk were pulled without `openprc`, so they carry no open price and
this decomposition is *undefined* on them. Everything below is scoped to
2013–2024. That is absence of evidence, not evidence of absence.

**The phenomenon is real.**

| slice | overnight | intraday |
|---|---|---|
| MU (the viral name) | **+3,306%** cumulative, 13.2 bps/day, t=4.15 | −62.7% cumulative, −0.8 bps/day, **t=−0.21** |
| all common stock | +10.7 bps/day, t=8.71 | +0.06 bps/day, t=0.01 |
| price ≥ $5 | +4.5 bps/day, t=3.57 | −0.08 bps/day, t=−0.05 |

**It is not a penny-stock artifact.** The obvious microstructure explanation —
bid-ask bounce between the closing and opening trade — predicts the effect
concentrating in illiquid names. The data says the opposite:

| dollar-volume quintile | overnight | intraday |
|---|---|---|
| q1 (least traded) | 0.4 bps, t=0.51 | −6.4 bps |
| q5 (most traded) | **8.3 bps, t=5.94** | **+6.3 bps** |

**And the strategy is still dominated.** On the only slice where execution is
arguable (q5), across a cost grid:

| one-way cost | overnight-only | buy-and-hold |
|---|---|---|
| 0 bps | 22.2%/yr, Sharpe 1.69 | **41.6%/yr, Sharpe 1.86** |
| 2 bps | 10.5%/yr, Sharpe 0.87 | 41.6%/yr, Sharpe 1.86 |
| 5 bps | **−5.0%/yr** | 41.6%/yr, Sharpe 1.86 |

Buy-and-hold wins **at zero cost**, before a single basis point is paid,
because in liquid names the intraday leg is *also* positive — the very leg the
strategy sits out. The viral version generalises from MU, where intraday
happens to be negative, to a universe where it is not.

**The most dramatic number in the claim is volatility drag, not an edge.** MU's
intraday "you'd be down 99.2%" decomposes as:

- realised cumulative: **−62.7%**
- pure vol drag at a mean of exactly zero: **−52.5%**
- contribution of the (statistically insignificant, t=−0.21) mean: −21.4%

A zero-mean series with 222 bps daily vol loses ~52% over 3,019 sessions by
compounding alone. The claim mistakes that for a negative intraday edge.

**What IS deployable, at zero cost, today:** overnight carries the equity
premium at ~4× lower volatility than intraday (69 vs 293 bps daily, universe
EW). The actionable read is an *execution* rule for books that already exist,
not a new book — **when reducing exposure, reduce it during the session, not
overnight.** No new capital, no new lane, no new evidence clock.

**Verdict: `ANOMALY_CONFIRMED / STRATEGY_REJECTED`.** No paper book is
launched from this. Registering one would have been the easy, wrong move.

---

## 3. Queue, reordered

Research work no longer blocks product learning. It continues in parallel where
it is cheap.

### P0 — the learning loop earns its name
1. ~~Population-aware forecast health~~ — **DONE this session.**
2. ~~Version-safe cluster-adjust path~~ — **DONE this session** (§4).
3. **`live_forward` has no producer.** Decide: repair the nightly specialist
   that fed it, or explicitly supersede it with `arena_forward` as G7's
   declared population. **Do not backfill.** *Attended: which population G7
   counts.*
4. **Generalise the Alpaca paper adapter** beyond the legacy `mirror` lane so a
   declared arena book can be mirrored to the external paper account.
   PAPER-only host refusal, next-open fills, immutable book id, cost
   accounting, idempotent orders, loud partial-fill receipts. New paper
   identity — never redirect `mirror`.

### P1 — perception
5. **Persistent event store** built on the existing `event_intel.py` /
   `arena/events.py` / `LLM_EVENTS_v1`, not a second stack. Append-only, with
   acceptance vs source timestamps, content hash, provenance, and
   was-this-available-to-a-decision.
   **Measured 2026-08-23, and the feed is NOT the problem.** `/api/health/full`
   reports `event_intel.events_extracted: 0`, which looks like a dead feed and
   is not one — it is a per-process counter reset at boot, and the arena had
   not run since the restart. Checked directly instead of inferred:

   - `get_ticker_events("NVDA")` returns **10 events, all three feeds `ok`**
     (yfinance news, EDGAR 8-K, earnings);
   - in prod, all 10 of `LLM_EVENTS_v1`'s beliefs carry
     `event_coverage: FETCHED` with `n_events_shown > 0`, while
     `LLM_PERCEPTION_v1` and `CURRENT_BEST_v1` correctly show `NOT_REQUESTED`.

   So the event arm is **live end-to-end**. What is missing is *persistence*:
   events are fetched fresh into each day's frozen snapshot and never
   accumulate, so nothing can learn across days which sources, event types or
   horizons paid. That — not ingestion — is what the store must add.

   *Secondary fix worth doing: make `events_extracted` a cumulative counter or
   label it "since boot". A metric that reads 0 on a working subsystem is how
   a session ends up rebuilding something that already works.*
6. **Earnings as a first-class state**: session of release, pre/post-market,
   surprise, guidance delta, opening gap, opening liquidity.
7. **Actor intelligence** — generalise `RELIABILITY_ROUTER_v1`'s hierarchical
   shrinkage over `actor × domain × claim_type × horizon × regime`. An
   `INVERSE` mapping is *earned* by holdout evidence, never assumed. Do not
   hard-code any pundit.

### P2 — research, in parallel, non-blocking
8. Memory-feasible linear arm · `signals_raw_plus` replication (a second
   vendor's characteristics panel, zero pulls) · risk-price forward
   registration · T2 prereg.
9. `optionm.opprcd` (4.31B rows) stays deferred until a named consumer exists.

---

## 4. The router decision, resolved without waiting

The G1 battery measures `CLUSTER_ADJUST_DEFAULT=False` at a **38.7% null-world
recommendation rate** against ORDER 27's ≤5% bar. OFF is measurably broken; ON
is the fix.

It was *not* simply flipped, because the router's verdict is in a live causal
path — `engine.py` sizes `ce_kelly` books at `abstain_kelly_factor` unless the
verdict is `RECOMMENDED` — and `PROFIT_ALLOCATOR_v1` was seeded under OFF.
Flipping in place would leave one live NAV series describing two policies.

**Implemented instead:** the setting is now part of the **policy identity** of
the books that consume it (`spec.policy_fingerprint(..., sizing=...)`). Scoped
on two axes so it is safe both ways:

- only `ce_kelly` books carry it — the other nine are untouched by a router
  change they never read;
- **OFF hashes to the legacy payload**, so every existing seed keeps verifying
  byte-for-byte. A guard that broke the live book it protects, at install time,
  would not be a guard.

Flipping the flag now makes `PROFIT_ALLOCATOR_v1` raise `ConfigDrift` under its
old seed and demand relaunch as a new immutable version. The correction ships
without rewriting history.

**Attended, and now unblocked:** flip the flag and launch
`PROFIT_ALLOCATOR_v2`. The old v1 history remains exactly what it was.

---

## 5. Governing text corrected

`CLAUDE.md` described a system that no longer exists. Scoped, not deleted:

- **Public Aegis** does not autonomously control any user's real brokerage
  capital, gives no financial advice, and keeps every disclaimer.
- **The internal engine** performs position sizing (Kelly, inverse-vol,
  CE-Kelly), makes daily simulated decisions, runs ten paper books with NAV
  series, and integrates a paper broker.
- **Event perception** may run intraday; ordinary portfolio decisions remain
  event-driven rather than high-frequency.

---

## 6. Scorecard

"Did it beat SPY over this interval?" stops being a universal kill rule. SPY
remains a required benchmark. Every book also reports: geometric return and
terminal wealth · CAGR · Sortino · expected shortfall · max drawdown ·
probability of ruin · upside/convexity capture · turnover and execution drag ·
regret vs rejected alternatives · calibration.

Each is read under the declared personality utility (preservation / balanced /
aggressive / extreme growth). These stay **declared preferences, never tuned
against history**. Murat's own book may be extreme-growth; the public product
must not inherit that as a default.
