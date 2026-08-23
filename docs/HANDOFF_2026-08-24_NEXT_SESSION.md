# HANDOFF — for the next session (written 2026-08-24)

Rewritten in place; the version this replaces is in git at `264b1c2`. Its three
Monday verification events survive here in §4. Read this first, then
`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.

---

## 1. Where we are, in one paragraph

An external review was adjudicated rather than imported
(`ADJUDICATION_2026-08-24_EXTERNAL_REVIEW.md`). Four of its five claimed defects
were real and are fixed; the fifth was real in mechanism, inert in fact, and a
different defect underneath it was live. A sixth, which the review could not
have seen, was found while fixing the first. Its central *architectural* claim —
that the arena's ten books share one alpha source and differ only in portfolio
treatment — was verified against the YAML and the composite weights, and is now
the organising diagnosis of the roadmap. Demonstrated edge is still **0%**, and
only matured decisions move that.

---

## 2. What changed this session

### Fixed, with tests

1. **The arena's external paper execution was two sessions late.** It mirrored
   *settled* positions from the 16:30 job, which runs before the 17:45 pass that
   decides. It now mirrors queued **order intent** and submits inside the pass
   that produced it. `paper_broker_targets.intent()` · `_submit_arena_broker_intent`.
2. **Credentials and state could come from different Alpaca accounts.**
   `_request` resolved keys from the ENV target regardless of the caller's
   target, so `sync_alpaca_mirror(target=arena_book)` with the env unset read
   the arena and traded the **mirror lane's account** — walking around the
   refusal built to prevent exactly that. The target is threaded through now.
3. **The event taxonomy was dropped between producer and model.**
   `event_intel` emits `event_type`; the arena adapter read `category`, which no
   producer emits. The LLM saw `category: null` on every event since event
   context shipped. Fixed, with a three-hop contract test.
4. **Event identity hashed the URL**, so five syndications of one story were
   five events — while the docstring promised the opposite. Split into
   `canonical_hash` (the event) and `observation_hash` (the sighting). Done now
   because the store is empty everywhere; later would have meant a 30-day window
   of everything reporting NEW.
5. **Acceptance time was caller-controlled** and the arena passed the frozen
   snapshot's simulated clock into it. Schema 1.1.0 has three clocks —
   `source_timestamp` / `ingested_at` / `decision_asof` — availability computes
   on `ingested_at` alone, a supplied stamp is marked `ingest_clock: supplied`,
   and a future one is refused.
6. **IBES exact-midnight announcement times were read as pre-market.** 3,168
   rows; 1,234 claims moved by one session. Same fix in
   `g4_collect_earnings.py` (807 rows).

### Built

7. **`signal_reachability.py`** — enumerate the PLAN for code. Three tiers
   (reachable 250 / tooling-only 60 / orphan 20), every orphan classified with a
   typed reason, derived from the import graph rather than a hand-maintained
   list. **On its first run it found that `detectability_gate` — TOURNAMENT-2's
   declared precondition — was imported by nothing**; that is now wired and the
   gap is closed. Four gaps remain named.

### Measured

8. **The actor result survives the PIT fix.** Corpus rebuilt, same seven
   analysts licensed for INVERSE, same holdout deficits to three decimals.
9. **The persistence headline was a filtered subset.** `0.516, n = 50` was 50 of
   **222**, selected by a rule nobody had written down (≥30 holdout claims).
   Unrestricted it is **0.25**. Every rung of the ladder excludes zero, so the
   premise holds; the magnitude depended on a threshold. The whole ladder is in
   `score_receipt.json` now, and the finding doc is amended.

---

## 3. Waiting on a human — and it is smaller than it was

* ~~A second Alpaca PAPER account~~ — **DONE.** The keys are in `.env` as
  `ALPACA_ARENA_API_KEY_ID` / `ALPACA_ARENA_API_SECRET_KEY`, they resolve, and
  the shared-account guard passes (the arena key differs from the lane key).
  **Two things remain, and both are deliberately attended:**
  1. set the same two variables **on Railway** — `.env` is local only;
  2. **DONE on Railway 2026-08-24**: `AEGIS_ARENA_BROKER_TARGET=CURRENT_BEST_v1`.
     Note the variable — declaring an arena book no longer un-mirrors the lane
     (§8). Still outstanding: **the seed boot**, which cannot happen until the
     book holds positions. See §8.
  **Rotate the arena secret when convenient** — it was pasted in plain text into
  a chat session before being written to `.env`.
* Which population G7 counts (`live_forward` vs `arena_forward`).
* The standing attended queue in `MEMORY.md` is otherwise unchanged.

---

## 4. Monday's verification events — unchanged, plus one

The three from the previous handoff still apply to **Monday 2026-08-24 17:45 ET**:

1. ten seed migrations to per-book identity appear in the logs;
2. nine books run (not ten — `PROFIT_ALLOCATOR_v1` retired);
3. `event_store` moves off `ABSENT`.

**And now a fourth, from this session's change:** the arena pass should log a
`Paper broker submit:` line. With no arena target declared it must log
**nothing** (lane targets are the 16:30 job's) — so *silence is the expected
result until someone sets `AEGIS_PAPER_BROKER_TARGET`*, and a line appearing
before that is the finding.

Also still falsifiable: **`why_moved` runs 17:15 ET Monday.** If `live_forward`
is still quiet on Tuesday, that is a P0, not a puzzle.

If a book raises `ConfigDrift` saying "refusing to migrate", the YAML changed
before the stamp took: restore it, let it migrate, then re-edit.

---

## 5. Do these next, in order

Full reasoning in `ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.

1. **`ANALYST_COCOVERAGE_GRAPH_v1`** — one groupby over IBES, already on disk.
   Which companies share analysts, with edges weighted by those analysts'
   *measured* reliability (which is what §6 of the finding just built, and what
   no published version of this can do). It is the "simple graph features before
   a GNN" test: if reliability-weighted co-coverage carries nothing, the graph
   programme stops for a groupby's worth of cost.
2. **`EVENT_RESPONSE_v1`** — continuation vs overshoot after an event, from the
   `g4/earnings_v1` corpus and TAQ. Not the event store: it has no history yet.
3. **`RELATIVE_VALUE_NN_v1`** — the corpus exists. **The effective n is 145 date
   blocks, not 72,495 pairs** (CANON §58); split by date block or the result is
   about within-month interpolation. Decision rule declared in advance: if an
   MLP does not beat LightGBM out of block, there is no neural challenger and
   the line closes with a receipt.

Each is a separate `PRODUCT_EXPERIMENT` book. **None of them goes into
`arena_composite`** — folding them in would hide the only thing being tested,
which is whether their errors are different errors.

---

## 6. Traps

* **A new custom exception under `services/` fails the suite** until it is
  enrolled in `backend/tests/test_guard_missing_input_contract.py` (`CASES`) or
  exempted with a reason. Cost 6 minutes this session; it is working as
  designed.
* **`.env` had raw dashboard text pasted into it** (`SECOND ALPACA`, `Key`,
  `Secret` as bare lines). `python-dotenv` logs "could not parse statement at
  line N" and carries on, so the keys were simply absent with no error anywhere.
  If credentials appear to be unset, read the file before reading the code.
* **Fixture datetimes must be in the past.** `event_store.make_record` now
  refuses a future ingestion stamp, and several tests used "today at 17:00",
  which is a coin flip on the hour the suite runs.
* `backend/routers/portfolio.py` carries a **BOM**. Python's importer strips it;
  `ast.parse` does not. Read source with `utf-8-sig` in any tooling.

---

## 7. The standard

The machinery got materially better again and the edge did not move, because
only decision days move it. What is different after this session is that the
next thing to build is finally the thing that could: **mechanisms whose errors
are different errors, competing where the outcome is recorded.**

---

## 8. The arena paper account: what is done, and the ONE step left

Set on Railway 2026-08-24 (production, service `Aegis-Finance`):

```
ALPACA_ARENA_API_KEY_ID       = PKLL…2LN4      (second paper account)
ALPACA_ARENA_API_SECRET_KEY   = ****
AEGIS_ARENA_BROKER_TARGET     = CURRENT_BEST_v1
AEGIS_SEED_ALPACA_MIRROR      = 0              (unchanged — deliberately)
AEGIS_PAPER_BROKER_TARGET     — still unset, so lane:mirror keeps its account,
                                its 16:30 sync and its verified curve
```

**Why `CURRENT_BEST_v1`.** One arena account, one equity curve, so it is one
book. It is the only book combining every rule the programme currently believes
in — inverse-trailing-vol sizing, LLM perception, substitution — which makes it
the one whose curve would ever be worth third-party verification. Substitution
also means it trades *between* monthly rebalances, so it accrues execution
observations fastest, and execution divergence is the thing the account exists
to measure. `ANTI_SIGNAL_v1` is the inverse control and `AGGRESSIVE_TOP5_v1`
would show larger slippage, but neither is a book anyone would promote.

### The step that is left, and why it could not be done now

**Every arena book holds `positions: 0`.** The arena has run exactly once
(Fri 2026-08-21); it decided 12 ENTERs for `CURRENT_BEST_v1` and queued them,
and nothing has filled yet because the next pass is Monday. `seed_alpaca_mirror`
replicates *settled positions*, so seeding today returns
`no_internal_positions` and does nothing.

Sequence, therefore:

| When | What happens | Expected |
|---|---|---|
| Mon 17:45 | arena fills Friday's 12 orders at Monday's open, decides, then submits | `Paper broker submit: target=arena:CURRENT_BEST_v1 status=not_seeded` — **no trades**, the Alpaca account is empty and `sync` will not open the first position |
| **Then, attended** | `railway variables --set AEGIS_SEED_ALPACA_MIRROR=1` → wait for the redeploy → **set it back to `0`** | boot seeds the account to the book's ~12 settled positions |
| Tue 17:45 | first real intent submit | trades, `basis=intent`, `decided_for=<Tue>` |

**The boot seeder now visits BOTH targets.** It used to call
`seed_alpaca_mirror()` with no argument, which resolves to the LANE — seeded
since inception — so with an arena book declared it would have returned
`already_seeded`, logged that as a success, and left the arena account empty
forever while every later sync reported `not_seeded` with no explanation
anywhere. Caught before the flag was ever flipped; one log line per target now,
so the lane's `already_seeded` cannot be read as the arena being done.

**Do not leave the seed flag armed.** It only fires at boot, Railway boots are
unpredictable, and an armed seed flag is what produced the duplicate DKNG order
on 2026-07-18. The `already_seeded` guard (open orders count as seeded) now
catches that case, but the doctrine stands: arm it, watch it fire, disarm it.

**If the seed reports `no_internal_positions` on Tuesday**, Monday's pass did
not fill — that is the finding, and the arena is the thing to look at, not the
broker.
