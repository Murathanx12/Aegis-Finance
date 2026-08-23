# HANDOFF — 2026-08-23 (evening): the profit-first turn, implemented

Supersedes `docs/HANDOFF_2026-08-23_OPUS_BUILDER.md` for ordering. That document's
research state is unchanged and still correct; this one records what shipped
after Murat's ruling and what the next session should do first.

**Read with:** `docs/ROADMAP_2026-08-23_PROFIT_FIRST.md` (the licences and the
reordered queue) and `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`.

---

## 1. The correction, in one line

> Research rigour determines what Aegis may **CLAIM**. It must not determine
> what Aegis may **TEST** in paper.

Three licences now exist — `PRODUCT_EXPERIMENT` / `CAPITAL_CANDIDATE` /
`RESEARCH_CLAIM` — in `CLAUDE.md` and the roadmap. The 24-month floor and
CANON §6 are amended **in scope**, not repealed: they govern claims. A paper
book needs a frozen strategy contract, not a preregistration.

---

## 2. LIVE vs BUILT vs ACCRUING

### LIVE (deployed and verified)
- Population-aware forecast health (`/api/health/full` → `forecast_populations`).
- Router policy identity: flipping `CLUSTER_ADJUST_DEFAULT` is now self-refusing.
- Paper-broker targets: an arena book **can** be mirrored; default unchanged.
- Paper-broker liquidation guards.
- Event store, with the arena as its producer.

### BUILT, not yet exercised
- **Arena → Alpaca paper execution.** The adapter accepts
  `AEGIS_PAPER_BROKER_TARGET=arena:<BOOK_ID>` but nothing has been seeded
  against an arena book. Activation is one attended env change plus the
  existing `AEGIS_SEED_ALPACA_MIRROR=1` boot. **Do not point it at
  `lane:mirror`'s account without deciding what happens to that lane's
  third-party history first** — the two cannot share one account.
- **Event store history.** Real, but one day deep. Novelty correctly reports
  `UNKNOWN` until a baseline exists.

### ACCRUING
- Arena: 10 books, NAV from 2026-08-21, 151 experiences, 25 beliefs. Daily at
  17:45 ET, trading days only.
- `arena_forward` ledger — now visible to health for the first time.

### NOT accruing, and now diagnosed
- `live_forward` — see §4.

---

## 3. The alarm was about the wrong subsystem

`/api/health/full` read DEGRADED on **"no new forecast in 11 days"**, and an
external review read that as the continuously-learning engine having stopped.

**Measured: it had not.** The arena wrote 25 beliefs and 151 experiences on
2026-08-21 — the last trading session before the check. Two populations, two
files, one alarm that named neither. The arena's ledger had **never appeared on
any health surface**.

Structurally identical to the WRDS finding one day earlier: *a check that reads
the record of what happened cannot see what was never asked for.* Both are now
fixed the same way — enumerate the **plan**, not the record.
`forecast_populations.py` declares every population with producer, consumers,
purpose and its own quiet clock (arena = 5 days, so a Sunday read of a Friday
write no longer cries wolf), computes health **per population**, refuses
pooling, and **fails the suite when a `predictions.jsonl` appears that no
population claims.**

---

## 4. `live_forward`: diagnosed, and it should self-resolve Monday

This was going to be an attended decision ("repair the producer or supersede
it"). It is not — the producer exists and is already fixed.

- `live_forward`'s producer is **`why_moved`**, which mints predictions through
  `belief_state.make_prediction` and appends to the default ledger path
  (= the volume, in prod).
- It ran as `pi_why_moved` and **crashed every night since shipping** on a
  no-arg call `TypeError`. Fixed 2026-08-22.
- It has **not run since the fix**: it is weekdays-only and its next fire is
  **Mon 2026-08-24 17:15 ET**.

**Falsifiable prediction for the next session:** after Monday evening,
`forecast_populations.populations.live_forward.last_written` should be
`2026-08-24` and `days_quiet` should reset. **If it is still 2026-08-12 on
Tuesday, the fix did not take and that is the P0.** Do not backfill either way.

---

## 5. The incident — read this before touching the paper broker

While smoke-testing the generalised adapter I called `sync_alpaca_mirror()` on
the dev machine. It **placed 12 live sell orders against the Alpaca paper
account.** They were accepted-not-filled (Sunday, market closed) and I
cancelled all 12 before the open. Account verified restored: 12 positions
intact, 0 open orders, equity 109,156.98 unchanged.

**Nothing was lost — by luck of the clock, not by any check.** Had it been a
weekday, the mirror lane's entire replicated book would have liquidated.

The root cause predates this session and is a genuine design bug: **`sync`
reads positions from a LOCAL source but executes against a SHARED remote
account**, and it resolved an empty local read as *"the lane liquidated
everything"*. An unreadable source and a genuinely flat source are
indistinguishable, and the code picked the destructive reading. Any dev
machine, fresh container or wiped volume would have done the same on contact.

Now guarded, with tests that drive a fake transport:
- empty internal source + non-empty account → **refuse**, log ERROR, record
  equity only;
- a pass that would close **>50%** of the book → **refuse** (a rebalance is
  incremental; "close almost everything" is what a broken source looks like);
- `AEGIS_ALPACA_ALLOW_FULL_LIQUIDATION=1` re-permits a genuine liquidation, so
  a book that really went to cash can still say so.

**Standing warning:** the local `.env` carries prod Alpaca keys, and they load
lazily via `backend.db`/`backend.config` import — so `alpaca_available()` reads
False until something triggers dotenv, then True. Never call `sync`/`seed`
interactively to "see what it returns".

---

## 6. Overnight/intraday: `ANOMALY_CONFIRMED / STRATEGY_REJECTED`

Murat's lead, tested properly. Full write-up in the finding doc; the short of
it:

- **Window declared:** pre-2013 CRSP years on disk carry no `openprc`, so
  "since 1990" is **untestable here**. 2013–2024, 11.3M stock-days, reconciles
  to CRSP `retx` on all but 173 rows (0.0015%).
- **Real:** overnight +10.7 bps/day (t=8.71). MU +3,306% overnight vs −62.7%
  intraday — the viral direction replicates.
- **Not a penny-stock artifact:** strongest in the *most* traded quintile
  (8.25 bps, t=5.94), weakest in the least (0.43, t=0.51). Bid-ask bounce
  predicts the opposite, so it is rejected.
- **Still dominated:** buy-and-hold beats overnight-only **at zero cost**
  (41.6%/yr Sharpe 1.86 vs 22.2%/yr Sharpe 1.69), because in liquid names the
  intraday leg is *also* positive — the leg the strategy sits out. The viral
  version generalises from the one name where intraday is negative.
- **The headline number is volatility drag:** MU's intraday mean is t=−0.21,
  and −52.5% of the −62.7% is `exp(−σ²T/2)` alone.

**No book launched.** Registering one would have been the easy, wrong move.
**Deployable at zero cost:** an execution rule for existing lanes — *reduce
exposure during the session, not overnight* (overnight carries the premium at
~4× lower vol).

Cheap follow-up worth doing: overnight **conditioned on an earnings release in
the gap** is the version the mechanism story actually predicts, and it needs
the earnings calendar the event store already touches.

---

## 7. The event store — and why the news engine did not need building

The roadmap said "build the news engine". **Measured first, and it already
works:** `get_ticker_events("NVDA")` → 10 events, three feeds `ok`; in prod all
10 of `LLM_EVENTS_v1`'s beliefs carry `event_coverage: FETCHED` with events
shown, while the numeric-only books correctly show `NOT_REQUESTED`.

`event_intel.events_extracted: 0` in health looks like a dead feed and is a
per-process counter on a healthy subsystem. *(Own fix, small: make it
cumulative or label it "since boot". A metric that reads 0 on a working
component is how a session rebuilds something that already runs.)*

What was missing was **yesterday**. `event_store.py` is append-only and
separates **source time** from **acceptance time** — acceptance is stamped from
the wall clock and never taken from the payload, because a feed handing over a
three-day-old stamp would backdate information into a decision that never had
it. `available_to_decision()` filters on the acceptance clock alone and is
strict at the boundary. Novelty returns **UNKNOWN** on an empty store rather
than NEW.

---

## 8. The lab: do NOT run it — recommend retirement

Murat asked for the lab to be run. I did not, and this is why:

- `lab/` has a large **uncommitted v5 rewrite** in the working tree that
  **removes 23 of 27 collectors** (adds 4). It would blind the lab to most of
  the engine.
- It breaks **14 tests** — not stale tests: it deleted
  `_compute_market_signal_for_lab`, which they cover.
- `rd_loop.py` launches autonomous Claude sessions that **auto-commit**.
  Running that from unreviewed, half-finished code unattended is not a call I
  should make.
- `rd_loop`'s last real run was **2026-04-17** — four months ago.

**Recommendation: retire the lab.** The arena has superseded it. The arena is
the continuously-learning loop, it runs daily in production, it grades itself,
and it has a licence. `rd_loop` is a second, dormant, less disciplined version
of the same idea. Retiring it also unblocks the "lab/ retirement" queue item.
The v5 rewrite is left uncommitted and untouched.

---

## 9. Queue for the next session

1. **Verify Monday's `why_moved` run** broke `live_forward`'s quiet clock (§4).
2. **Verify the deploy** carried `forecast_populations` and `event_store` into
   `/api/health/full`, and that `arena_forward` reads `ok` after Monday's
   17:45 pass.
3. **Attended, unblocked:** flip `CLUSTER_ADJUST_DEFAULT` → True and launch
   `PROFIT_ALLOCATOR_v2`. v1's history stays what it was; the flip is now
   self-refusing rather than silent.
4. **Attended:** decide the Alpaca account question (§2) and seed one arena
   book to external paper.
5. Earnings-conditioned overnight slice (§6) — cheap, and the one version of
   the lead that is not yet answered.
6. Actor intelligence: extend `RELIABILITY_ROUTER_v1`'s shrinkage to
   `actor × domain × claim_type × horizon × regime`. `INVERSE` is **earned** by
   holdout, never assumed — the Inverse-Cramer ETF was itself liquidated.
7. Research, in parallel and non-blocking: linear arm · `signals_raw_plus`
   replication · risk-price forward registration · T2 prereg.

---

## 10. Suite and deploy

- Fast suite: **5,398 passed / 15 failed** before this session's fixes. 14 of
  the 15 are the uncommitted `lab/` v5 rewrite (§8, not staged). The 15th was
  guard enrolment for the new guards — now enrolled, 55 contract tests pass.
- New tests: 18 population · 9 router identity · 19 paper broker · 22 event
  store = **68**.
- Commits: `a363e2f` (licences, populations, router identity, paper broker,
  overnight study) and `a2a38a6` (event store).
