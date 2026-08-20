# FINDINGS — what was missed or done wrong (session of 2026-08-20, post-ORDER-25)

Written on instruction: *"It seems like there is a lot of things we missed or
did wrong I want you to also find and flag them while you are working."*

Every item below was verified against the repository or the live system, not
inferred from a handoff. Severity is about **what it would have cost if it had
gone unnoticed**, not about how hard it was to fix. `FIXED` means fixed in this
session with a test that fails without the fix.

**The pattern that connects most of them:** a component runs, returns a
plausible object, and nobody checks whether the object means what its name
says. Green and empty. It is the house failure mode and it recurred in six
separate places this week.

---

## A. THE BIG ONE — the WRDS pull reported itself finished having skipped 79%

**Severity: CRITICAL. Status: FIXED (catch-up pull built and running).**

`pull_everything_manifest.json` carries `completed_at: 2026-08-20T13:24:53Z`
and `disk_used_gb: 0.514`. Underneath that stamp:

| | |
|---|---|
| planned | 1,327 tables |
| **pulled** | **281** |
| **failed** | **1,127** |

The session handoff recorded *"finished ~2026-08-20 late evening (~1,327
joinable tables planned into `backend/data/optimus/wrds/bulk/`)"* — the **plan
count reported as the result**. `docs/HANDOFF_2026-08-20_ORDER25_TO_OPUS.md`
§0.5 then asked the next session merely to "verify the process ended and
record final counts". It ended. It ended having done a fifth of the job.

P3 of the brain queue ("supervised learning on the historical substrate — WRDS
is in") was scheduled on top of a substrate that is 21% present.

### A1. The 90-second timeout was self-inflicted, and the server allows 2 days

727 of the 1,127 failures are `canceling statement due to statement timeout`.
The cause is `wrds_pull_everything.PER_TABLE_TIMEOUT_S = 90`, defended in a
comment as protecting a scarce connection. Measured on the live server this
session:

```
SHOW statement_timeout  ->  2d
```

Nothing upstream asked for 90 seconds. Re-pulled by hand with the cap lifted:

| table | shape | time | verdict under the old cap |
|---|---|---|---|
| `crsp.contact_info` | 329,280 × 11 | **18.1s** | failed |
| `optionm.distrd` | 743,101 × 15 | 30.3s | failed |
| `comp.aco_indsta` | 59,293 × **886** | 91.3s | failed **by 1.3s** |
| `ibes.act_epsint` | 3,457,713 × 14 | 162.5s | failed |

A 329k-row table that takes 18 seconds on its own did not need 90 — it lost
them to five workers competing for one link. **The cap did not protect
throughput; it converted slow tables into absent ones.**

### A2. A DNS outage was booked as 235 individual table failures

235 failures are `could not translate host name
"wrds-pgdata.wharton.upenn.edu"`. The laptop lost name resolution for a
stretch and the puller recorded one permanent failure per table instead of
pausing. A transient network outage became a permanent hole in the substrate,
and then the hole was reported as a completed pull.

### A3. Entitlement facts were mixed into the failure count

125 `permission denied` + 28 `relation does not exist` are **not** pull
failures — they are facts about what this account may read, and the canon rule
is already written down: *the catalogue is not entitlement*. Buried inside a
1,127-line failure list they read as breakage.

### The fix — `scripts/wrds_pull_catchup.py`

* classifies every failure TERMINAL (never retried: `NOT_ENTITLED`,
  `ABSENT_FROM_SERVER`) vs RETRYABLE (`TIMEOUT`, `NETWORK_DNS`, `CONNECTION`,
  `REPLICA_RECOVERY`), and an **unrecognised error defaults to RETRYABLE and
  is named** — silently calling an unknown error terminal is how a transport
  bug becomes a permanent hole;
* timeout `--timeout-s` default **900s**, set once per connection;
* **3–4 workers, not 5** — contention was the real limit;
* dropped connections reconnect and retry with backoff;
* TERMINAL tables are written to `pull_terminal_failures.json` as an
  entitlement addendum;
* **refuses to write `completed_at` while any retryable table is
  outstanding** — it writes `partial_at` plus `incomplete_reason` instead.
  That is the exact sentence the first run got wrong.

First dry run of the catch-up: **134 terminal, 939 retryable.**

---

## B. The arena decided, recorded, and never learned

### B1. Minted LLM predictions were never resolved — `FIXED`
`perception.perceive` wrote gradeable `PredictionRecord`s to the arena ledger
and **nothing ever called `resolve_all` on that path**. A forecasting ledger
that only grows is a diary. `engine.run_daily` now grades it every pass.
*(This one the previous session did flag, in P1(c). It was still the first
thing to fix.)*

### B2. Forecast truth and executable P&L were the same number — `FIXED`
Outcomes were graded close(d0) → close(d0+h), but the books fill at the **next
session's open**. An overnight gap the book never traded through was being
attributed to the decision that preceded it. Rows now carry both legs
separately at `schema_version: 2`, and a row is written only when *both*
windows close — one session of latency in exchange for an immutable row, which
matters because these files are append-only.

### B3. The LLM invented its own prior in the call that used it — `FIXED`
`perception.perceive` asked for `prior` **and** `posterior` in one call. A
model asked "what did you think before, and what do you think now" writes both
halves so the second looks reasoned. `belief_change = posterior − prior` is
the quantity the belief-change contract rests on *and* the quantity the engine
turns into a weight tilt — it was a free parameter the forecaster set itself.
`beliefs.py` reads the prior from the ledger; a first look opens at a declared
`OPENING_PRIOR`, is stamped `INITIATION`, and never tilts anything.

### B4. The "daily" LLM ran roughly one session in twenty — `FIXED`
Perception fired only inside `_decide`, i.e. initial build and monthly
rebalance. Daily substitution never ran it. The model's only look at a name
was the call that traded it. The review now runs every session over a
deterministic population (holdings, then challengers, then names whose score
moved), and does not trade.

### B5. Segment identity did not cover the estimator — `FIXED`
The YAML SHA-256 was identity for the books, but the composite they select on
lives in `discovery.py`. **Editing the composite changed every book's policy
while every config hash stayed byte-identical and every seed still verified.**
This is precisely the silent-drift shape the lane machinery exists to refuse,
reproduced one directory over. Identity is now
`sha256(config_hash | COMPOSITE_VERSION)`, stored in the seed and enforced on
every run.

### B6. A partial price fetch would have been traded as if it were the universe — `FIXED`
Every score in the day state is a z-score over the names that got priced. A
fetch returning 20 of 180 names still yields 12 chosen, so
`insufficient_breadth` (floor: 6) never fires. The books would have traded a
ranking computed over a different universe — and **snapshots are write-once**,
so that day's wrong world would be permanent. `_decide` now refuses below
`min_priced_fraction` (0.80).

### B7. Six YAML keys look like controls and change nothing — `FIXED`
`rebalance`, `execution`, `secondary_benchmark`, `vol_lookback_days`, per-book
`selection`, `substitution.max_swaps_per_day`. Editing any of them did
nothing, silently. `load_specs` now refuses a key that is neither consumed nor
listed as descriptive *with the code location that actually implements it*.

### B8. The counting brain answered a question nobody had recorded — `FIXED`
Found by the house guard-enrolment harness catching my *own* new module:
`reliability.decision_cells` validated its grouping keys inside the row loop,
so an **empty** ledger sliced by a state nobody stores returned a clean, green,
empty report. "No data yet" and "that dimension was never recorded" read
identically. Keys are now declared and checked before any row is touched.
*(Worth noting the machinery worked: I did not catch this, the contract test
did.)*

---

## C. FEATURE-COVERAGE-AUDIT-1 — the premise of ORDER 25 holds for 12 names of 180

**Severity: HIGH (scoping). Status: aggregation FIXED; the real finding is open.**
Full detail: `docs/FEATURE_COVERAGE_AUDIT_1.md`.

The composite took the weighted mean of whatever factors a name had. Averaging
shrinks, so well-measured names were pushed to the middle: enriched names
appeared in a top-12 selection **0.43** times against the **0.80** that
coverage-blindness would give — under-represented in the only tail selection
reads.

But the audit contradicted the prior it was built to confirm, and that is the
useful part:

| change | value (latent-skill units) | share of oracle gap |
|---|---|---|
| fix the aggregation | +0.012 | 1.6% |
| **widen coverage 12 → 180 names** | **+0.239** | **31%** |

**ORDER 25's premise — that the arena is "the caller the 16 collectors never
had" — is true for 12 names out of 180. For the other 168 the arena is a 12-1
momentum ranker, and no aggregation rule changes that.** The +0.239 experiment
is arena-local, universe-wide features, and it requires no registered
cross-section to be widened.

---

### C1. Measured live, not modelled: 206 names on one factor, one name on six

A full end-to-end pass against live prices that evening froze this into the
day state:

```
coverage_histogram: {"1": 206, "6": 1}
```

The audit above modelled 12 enriched names of 180. Reality is **one of 207**.
`arena_composite` is 12-1 momentum for 99.5% of the cross-section. Everything
else in the same pass worked — 28 names nominated from outside the watchlist,
`priced_fraction` 0.9944 over core, 7 books decided, 105 experiences written —
which is what makes the histogram the finding rather than a symptom.

---

## C2. `event_intel` — the seventeenth collector with no caller

**Severity: HIGH. Status: FIXED (wired into the arena).**

`backend/services/event_intel.py` builds a typed event feed over yfinance
news, EDGAR 8-Ks and earnings, with per-feed degradation already disclosed.
Its only caller is `daily_brief.py`, which nothing schedules. Live prod:

```
"event_intel": {"events_extracted": 0, "by_tier": {}, "last_extraction_at": null}
```

Built, tested, never run. Meanwhile the arena's LLM was being asked to revise
a belief about a company while being shown nothing about the company. Now
wired through `arena/events.py`, frozen into the decision's input snapshot
(the feed is fetched live and would otherwise be unreplayable), with
`LLM_EVENTS_v1` as the ablation twin.

---

## A4. THE WORST ONE — 23 parquets held an arbitrary 4–80% of their table

**Severity: CRITICAL. Status: FIXED (refused going forward, 23 quarantined).**

`SELECT * FROM t LIMIT 8000000` with **no `ORDER BY`** returns an unspecified
8,000,000 rows. Not a prefix. Not a sample with a definition. Not the same set
on a re-run.

`wrds_pull_everything` has always had this and it **never fired**, because
every table big enough to hit the cap died on the 90-second timeout first.
Fixing the timeout (§A1) made the big tables succeed for the first time — and
the latent defect landed 23 files that look like complete tables:

| table | true rows | kept | share |
|---|---|---|---|
| `crsp.daily_nav_ret` | 186,442,964 | 8,000,000 | **4.3%** |
| `comp.aco_transq` | 75,590,661 | 8,000,000 | 10.6% |
| `comp.aco_transa` | 47,158,539 | 8,000,000 | 17.0% |
| `optionm.hvold2016` | 14,466,338 | 8,000,000 | 55.3% |
| `crsp.monthly_tna` | 10,011,987 | 8,000,000 | 79.9% |

**23 at the cap, 0 genuinely complete.** A file named
`crsp__daily_nav_ret.parquet` holding 4.3% of the table joins cleanly and
silently drops 96% of the data — worse than an absent file, and the house
failure mode with a parquet extension. It would have poisoned P3/Q4
(supervised learning on the substrate) invisibly.

**Fixed three ways:** the catch-up now refuses any table whose *measured*
count exceeds the cap and records `true_rows` (the plan's existing
`est_rows > cap` rule never fired because `est_rows` is 0 for anything
un-ANALYZEd); `scripts/wrds_quarantine_truncated.py` moved all 23 out with
their true sizes; and the cap is now a **declared decision** to revisit —
raise it, partition, or do without — rather than a hole.

### A5. Three corrupt parquets, from my own killed runs
Found by the quarantine sweep: `optionm__hvold2021/2022/2023.parquet` were
unreadable ("magic bytes not found in footer") — half-written when I killed a
run. The streaming writer deletes on **exception**, and SIGKILL is not an
exception, so the file survives and resumability (which keys off existence)
reads it as a completed table forever. Deleted, not quarantined: there is
nothing in them to keep.

### A6. A killed run lost all of its manifest bookkeeping
The catch-up wrote the manifest only at the end, so killing it left the
parquets on disk with **no record** of what they were, their row counts or
their date ranges. `wrds_pull_everything` carries a comment about learning
this exact lesson; this file had to learn it too. Now flushed every 5
completions, idempotently by name.

---

## C3. Two memory defects in my own catch-up puller, found by running it

Recorded because "I wrote it this session" is not a reason to leave it out.

1. **`pd.read_sql` buffers everything.** Its `chunksize` argument does not
   bound memory on psycopg2 — the default cursor is client-side, so the whole
   result arrives before the first chunk. Four workers on wide Compustat
   tables took the process to **4 GB and climbing** with `MAX_ROWS` at 8
   million. Fixed with a server-side named cursor.
2. **A server-side cursor was not enough.** The cursor bounds what the
   *server* sends per round trip, not what pandas/Arrow *materialise* per
   chunk. A 200,000-row chunk is 2.2 MB of an 11-column table and ~1.4 GB of
   an 886-column one, and Compustat is full of the latter — the process
   reached **10 GB**. Chunks are now sized in CELLS (`CHUNK_CELLS / n_cols`),
   and the buffered-vs-stream routing tests both axes rather than rows alone.
   Measured after: **470 MB**.

Both would have OOM'd overnight, and a killed pull leaves partial parquets
that resumability reads forever as completed tables. That third hazard is
also fixed: a failed attempt deletes its partial file before retrying.

---

## D. Process findings

### D1. The attended queue was carried forward without being checked
Three of the six items in `HANDOFF_2026-08-20_ORDER25_TO_OPUS.md` §5.5 were
already done:

| carried item | actual state |
|---|---|
| "amended NET prereg" | **SIGNED 2026-08-19** (`PREREG_AEGIS_NET_TOURNAMENT_1.md`) |
| "Brier-bar signature" | **SIGNED 2026-08-19** (`DECLARATION_IIF1_MINIMUM_MEANINGFUL_BRIER.md`) |
| "merge review of `lab/autonomous-rd`" | **0 ahead, 94 behind `main`** — nothing to merge |

A queue that is copied rather than verified stops being a queue. *(The
external review flagged this independently; it checks out.)*

### D2. The unseeded window was an asset, and it was nearly spent by accident
Every schema and policy change above is free while the arena is unseeded and
expensive the moment it is not. Had `AEGIS_SEED_ARENA=1` been flipped before
this session, the books would have locked in the broken composite (C), the
same-call prior (B3), the single-leg outcome schema (B2) and a segment
identity that could not see any of it (B5). **Nothing about the seeding
instruction said "seed last".** It should have.

### D3. Two live prod conditions, both pre-existing and both still open
* `prediction_ledger` DEGRADED: no new forecast in 8 days; 25 overdue, all
  quarantined by design (attended disposition).
* A boot warning states the image at `/app/backend/data/optimus/predictions.jsonl`
  holds **21,731 records absent from the persisted ledger** at
  `/data/optimus/predictions.jsonl` (which has 112). Deliberate — the
  persisted ledger is authoritative once non-empty — but a 21,731 vs 112 gap
  that logs once at boot deserves a decision, not a warning that scrolls.

---

## E. What I did NOT fix, and why

* **The coverage hole (C)** — the +0.239 item. It is the trackers /
  universe-wide feature work, which is a build, not a patch. It is the top of
  the queue.
* **Regret's named alternative** — `chosen_alternative` is written as the *top*
  pick for every reject, so `regret_vs_named` currently answers "vs the best
  thing we did instead", not "vs the name it displaced". Both readings are
  computed; `regret_vs_basket` is the one to use. Changing what gets stored is
  a schema change and should happen before seeding, not after.
* **Horizon mismatch** — decisions mature at 1/5/21/63/126 sessions, LLM
  forecasts at the `belief_state` grid 1/2/5/20/60/120/252. "A month" is 21 in
  one and 20 in the other. Not reconciled; **stated** in every
  `/api/arena/reliability` payload as `horizon_alignment.warning` so the two
  blocks are not joined on it.
* **The sell-side cost rounding in `_fill_pending`** — when a sell is capped by
  the position size, the cost is still charged on the requested notional.
  Real, tiny, and worth a line rather than a patch mid-session.
