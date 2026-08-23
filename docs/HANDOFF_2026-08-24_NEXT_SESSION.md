# HANDOFF — for the next session (written 2026-08-24)

Rewritten in place; the version this replaces is in git at `264b1c2`. Its three
Monday verification events survive here in §4. Read this first, then
`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.

---

## 1. Where we are, in one paragraph

An external review was adjudicated rather than imported, six defects were fixed,
and then **four alpha mechanisms were attempted in one night and all four now
carry receipts**: the analyst co-coverage graph is licensed AND buildable, two
screens returned STOP, and one returned a genuinely strong number (+0.0315,
t 3.19, surviving BH-FDR) that was **refused** because a precondition test
showed the edge is borrow fees. Demonstrated edge is still **0%**. What changed
is that the remaining directions are the ones that survived being attacked, and
three expensive ones are closed on evidence rather than open on hope.

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

10. **Two Alpaca accounts, two books.** `AEGIS_PAPER_BROKER_TARGET` was a single
    GLOBAL choice — naming an arena book would have silently stopped mirroring
    `lane:mirror`, whose third-party-verified curve the code calls the only
    independent check on our NAV maths. Two credential namespaces means two
    accounts, so both mirror at once now: new `AEGIS_ARENA_BROKER_TARGET`.
11. **The boot seeder was a silent no-op.** It called `seed_alpaca_mirror()`
    with no argument, which resolves to the LANE — seeded since inception — so
    with an arena book declared it would have logged `already_seeded` as a
    success and left the arena account empty forever. `seed_all_paper_brokers`
    visits every declared target now.
12. **`execution_ledger.py`** — one row per intended order, written at
    submission and resolved later, so the broker's real fill sits beside the
    book's synthetic one. The first thing in this repository that checks the
    `cost_bps + slippage_bps` every arena book assumes. Records what leaves no
    fill behind: never-filled, partial, and broker-filled-with-no-internal-
    match. `/api/health/full` gains `execution_ledger` and `paper_broker` rows.

### Measured

8. **The actor result survives the PIT fix.** Corpus rebuilt, same seven
   analysts licensed for INVERSE, same holdout deficits to three decimals.
13. **`ANALYST-COCOVERAGE-GRAPH-1` ran — verdict CONTINUE**, and the three
    refinements we hoped for all measured zero. Full result:
    `docs/FINDING_2026-08-24_ANALYST_COCOVERAGE_GRAPH.md`. The effect
    replicates (+0.0228 IC) and survives own-momentum (+0.0156 paired) and
    industry momentum (+0.0090 paired); reliability-weighted edges are a
    precisely measured zero (−0.00008 ± 0.00052), direction shows no
    asymmetry, 52-week-high conditioning adds nothing. **The GNN stays
    unbuilt** — its gate was "simple graph features pay", and they do, but
    every kind of structure a GNN exists to exploit measured zero.
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
  **Set on Railway 2026-08-24** (`railway variables --skip-deploys`):
  `ALPACA_ARENA_API_KEY_ID`, `ALPACA_ARENA_API_SECRET_KEY`, and
  `AEGIS_ARENA_BROKER_TARGET=CURRENT_BEST_v1`. Note the variable name —
  declaring an arena book no longer un-mirrors the lane (§8).

  **ONE thing remains, and it is deliberately attended: the seed boot**, which
  cannot happen until the book holds positions. See §8.
  **Rotate the arena secret when convenient** — it was pasted in plain text into
  a chat session before being written to `.env`.
* Which population G7 counts (`live_forward` vs `arena_forward`).
* The standing attended queue in `MEMORY.md` is otherwise unchanged.

---

## 4. Monday's verification events — unchanged, plus two

**Read the clock carefully.** The scheduler runs on `US/Eastern` and the arena
job is `mon-fri`. A session working from a UTC+8 machine sees the local date
roll over to Monday roughly 12 hours before Eastern does, and the pass does NOT
run on the local Monday — it runs on the Eastern one. This was got wrong once
already in the session that wrote this section.

The three from the previous handoff still apply to **Monday 2026-08-24 17:45 ET**:

1. ten seed migrations to per-book identity appear in the logs;
2. nine books run (not ten — `PROFIT_ALLOCATOR_v1` retired);
3. `event_store` moves off `ABSENT`.

**And now two more, from this session's changes.** `AEGIS_ARENA_BROKER_TARGET
= CURRENT_BEST_v1` IS set on Railway, so the pass will speak — and exactly what
it should say is predictable:

4. `Execution reconcile: target=arena:CURRENT_BEST_v1 status=nothing_pending`
   — nothing has been submitted yet, so there is nothing to reconcile.
5. `Paper broker submit: target=arena:CURRENT_BEST_v1 status=not_seeded
   basis=... trades=0` — **zero trades is the CORRECT outcome.** The Alpaca
   account is empty and `sync` deliberately will not open the first position;
   only the attended seed does that (§8).

**A `trades=N` with N > 0 on Monday would be the finding**, not the success:
it would mean the account was seeded by something nobody authorised.

Also still falsifiable: **`why_moved` runs 17:15 ET Monday.** If `live_forward`
is still quiet on Tuesday, that is a P0, not a puzzle.

If a book raises `ConfigDrift` saying "refusing to migrate", the YAML changed
before the stamp took: restore it, let it migrate, then re-edit.

---

## 5. Do these next, in order

**Every roadmap item now carries a receipt.** Four alpha mechanisms were
attempted in one night; this is what they returned:

| trial | verdict | why it matters |
|---|---|---|
| `ANALYST-COCOVERAGE-GRAPH-1` | **CONTINUE + BUILDABLE** | the only positive. Survives own-momentum, industry momentum, firm granularity and actions-only — every reduction a live feed forces |
| `EVENT-RESPONSE-1` | STOP | PEAD real at 7bps; nothing ranked which events drift. Named its own successor |
| `RELATIVE-VALUE-NN-1` | STOP | MLP worst of three; the neural question is closed with a receipt |
| `EVENT-RESPONSE-2` | **NOT LICENSED** | hypothesis correct (+0.0315, t 3.19) and the edge is **borrow fees** |

### 1. `GRAPH_PROPAGATION_v1` — built, NOT registered, and the reason has a date

**The module exists** (`backend/services/graph_propagation.py`, 15 tests) with
its frozen contract (`contract_hash` `136240f859ca7e41`). What is missing is the
arena book, and that wait is a hard ordering constraint, not a to-do.

**THE VENDOR QUESTION IS ANSWERED — VIABLE.** Measured 2026-08-24 over the real
179-name universe, receipt in `backend/data/optimus/graph_propagation/`:

| | |
|---|---|
| depth | **not the constraint** — median 14.4 years of history |
| usable graph rows | **176/179 = 98.3%** |
| median covering firms in window | **17** (the IBES graph the screen validated on had 14) |
| median days since last action | 10 |

**And the probe found a defect worth more than the answer.** META, WELL and CAT
return an EMPTY trailing window and **no error** — their action history is
truncated in yfinance's data. This is not coverage ceasing: yfinance's own
`recommendations` summary reports **62 analysts rating META this month** while
`upgrades_downgrades` stops at 2024-09-30. A graph that trusts the empty window
drops a mega-cap out of the ranking in silence. Hence `STALE_FEED_DAYS = 120` is
a **refusal**, not a log line. It does no delicate work: genuine silence tops out
near 49 days in this universe and the truncated names sit at 675-689.

> #### DO NOT ADD THE BOOK TO `arena_books_v1.yaml` UNTIL THE ARENA HAS RUN
>
> The ten books seeded 2026-08-21 still carry only the **legacy whole-file**
> fingerprint. They migrate to per-book identity on their **next arena pass**,
> and `assert_config_current` migrates *only while the legacy hash still
> verifies*. Adding a book first changes that hash, so the migration branch
> refuses to run **and refuses to migrate** — all ten, permanently, with their
> NAV histories stranded.
>
> This is already pinned by
> `test_migration_REFUSES_when_the_config_already_changed`; it was checked
> against production before anything was edited, not reasoned about afterwards.
>
> **So Monday's pass is doing two jobs**, and the second one was invisible:
> it queues the arena's decisions *and* it migrates the seeds. Confirm the
> migration landed (`/api/arena/status`, books carrying `book-v1`) before
> registering anything.

Once registered, it is a **separate PRODUCT_EXPERIMENT book**, never a weight in
`arena_composite`, and seeding stays attended (§3, `seed-a-lane`).

Nothing fancier than plain equal-weighted peer return belongs in it: reliability
weighting, edge direction and 52-week-high conditioning each measured **zero**.

### 2. `EVENT-RESPONSE-3` — condition on borrow rather than ignore it

v2 established that the implied move genuinely adds information and that the
resulting edge is not separable from borrow. That is not "the feature is
useless"; it is "this version is untradeable". A version that models the borrow
fee as a COST, or trades only where the effect survives its exclusion, is a
different experiment and **owes its own declaration**.

Do not reuse v2's spec_hash for it.

### 3. P0.2 the information bus

The only original roadmap item never started, and it now has what it was waiting
for: `signal_reachability` has named the orphans.

### Standing rules for any of the above

* **`feature_leakage_guard.assert_no_target_leakage` before fitting anything.**
* **Declare confound tests as PRECONDITIONS, not follow-ups.** Twice in one
  session that ordering was the difference between a refusal and a retraction.
* **Every screen so far has been under-powered except v2.** State nulls as "no
  effect larger than X", never "no effect".

---

## 5.5. RAILWAY WILL NOT DEPLOY WHILE CI IS RED — and nothing said so

**Found 2026-08-24 the hard way.** Two pushes (`67c26ff`, `a7c4448`) were
reported as successful `git push`es and never reached production. The service
kept serving `1e2dda0` while the working tree was three commits ahead.

```
railway deployment list --json
  -> 'status': 'SKIPPED', 'skippedReason': 'CI check suite failed'
```

Railway is wired to the GitHub check suite and **skips the deploy entirely when
CI fails** — no build, no error, nothing in the service logs. `railway status`
still says the service is healthy, because the OLD deployment is healthy. That
setting is correct and should stay; what was missing is that anyone knew.

**So a green local suite is not evidence that anything shipped.** The deploy
verification for any push must read `deploy.commit` from
`/api/health/full` and compare it to the pushed SHA. It already did — which is
the only reason this was caught at all.

### How to read CI without the `gh` CLI (not installed on this machine)

GitHub's check-runs endpoint is readable **unauthenticated** for this repo:

```bash
curl -s -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/Murathanx12/Aegis-Finance/commits/<SHA>/check-runs" \
  | python -c "import json,sys; [print(r['name'], r['status'], r['conclusion'])
                for r in json.load(sys.stdin)['check_runs']]"
```

Job LOGS need auth; the pass/fail per job does not, and that is enough to know
which of the two jobs (`backend pytest` / `frontend next build`) broke.

### The CI-mimic recipe, because local and CI differ in one load-bearing way

`backend/config.py` calls `load_dotenv(PROJECT_ROOT / ".env")` **at import**, so
every local test run sees whatever secrets are on this machine. CI has no
`.env`. That is exactly how the 2026-08-24 failure happened: `execution_ledger.
reconcile` short-circuits to `not_configured` without credentials, so eleven
tests passed locally **because a secrets file existed** and failed in CI.

To reproduce CI before pushing:

```bash
( trap 'mv -f .env.hidden .env 2>/dev/null' EXIT
  mv .env .env.hidden
  AEGIS_IIF1_PREREG_ABSENT_OK=1 python -m pytest backend/tests/ -m "not slow" -q
  mv -f .env.hidden .env )
```

**Always inside a subshell with the trap.** A run that dies with `.env` moved
leaves the machine without its keys.

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
* **A column name is not a measurement.** THREE times in one session a
  property of data was asserted from its description and was wrong:
  `stdopd` "standardized options" (ATM-only, no wings, so no skew); a daily
  return "excluding" the overnight gap (CRSP is close-to-close, so it includes
  it); and `cs_rank` (the cross-sectional rank OF THE FORWARD RETURN, sitting in
  a feature list). Two were caught by reading. The third was caught only because
  the resulting IC was 0.99 — **which is not a method**, since the same leak at
  0.15 would have shipped. `backend/services/feature_leakage_guard.py` now
  refuses any feature whose within-block rank IC against the target exceeds 0.5,
  **before any model is fitted**. Call it from every screen.
* **Every screen so far has been under-powered by its own design.** All three
  report an MDE at 80% power ABOVE their own observed effect. That is not a
  reason to discount them — it is the reason each null is stated as "no effect
  larger than X", never "no effect".
* **A test can pass because of a file on your machine.** `backend/config.py`
  loads `.env` at import, so the suite sees local secrets CI never has. If a
  code path branches on "are credentials configured", its tests must stub that
  branch rather than inherit the answer from disk. See §5.5 for the recipe that
  reproduces CI locally.
* **`git push` succeeding does not mean anything deployed** (§5.5). Railway
  skips the deploy when the GitHub check suite fails, silently.
* **An autouse fixture calling `tmp_path_factory.mktemp` runs per TEST.** Added
  once here it took the fast suite from 8:46 to 14:37 — 5,570 directories.
  Session-scope the directory; only the monkeypatch needs to be per-test.
* **The suite writes into real ledger paths unless something stops it.** Found
  by reading `git status` after a run — twice now, by two different sessions.
  `test_paper_broker_targets` drives `sync_alpaca_mirror` against a fake
  broker, and the sync records submissions, so PENDING orders for AAPL/MSFT
  landed in the real execution ledger and would have aged into `NEVER_FILLED`.
  An autouse conftest fixture now redirects the root, matching
  `_sandbox_telemetry_to_tmp` directly above it. **Read `git status` after a
  suite run** whenever a service starts writing files.
* **An append-only ledger cannot count open work by row state.** A resolved
  order leaves a PENDING row *and* a resolution row, so counting rows-in-state
  counted every resolved order forever. Derive by identity.
* **CRSP schema drift**: `crsp_dsf_1990..2012` carry no `shrout`/`cfacpr`,
  2013+ do. Refuse those years rather than defaulting the split factor — an
  unadjusted price makes every split look like a crash against a 52-week high.
* **Fixture datetimes must be in the past.** `event_store.make_record` now
  refuses a future ingestion stamp, and several tests used "today at 17:00",
  which is a coin flip on the hour the suite runs.
* `backend/routers/portfolio.py` carries a **BOM**. Python's importer strips it;
  `ast.parse` does not. Read source with `utf-8-sig` in any tooling.

---

## 7. The standard

**Every roadmap item now carries a receipt.** Four alpha mechanisms attempted in
one night: one licensed and buildable, two STOP, one strong number correctly
refused.

**Demonstrated edge is still 0%**, and that is the honest reading. But the night
closed three expensive directions on evidence rather than leaving them open on
hope — including the GNN, closed by measuring that the structure it exists to
exploit is not there — and it refused a BUILD that would otherwise have shipped
at t 3.19.

### The two things worth carrying forward

**Order of operations, twice.** `feature_leakage_guard` exists because an IC of
0.99 was caught by luck rather than method. `EVENT-RESPONSE-2` was refused
rather than retracted because its confound test was a PRECONDITION. Both times
the difference was *when* the check ran, not whether it existed.

**A description is not a measurement.** Six times in one session a property of
data or code was asserted from its name or its docs and was wrong: `stdopd`
"standardized options" (ATM-only), a daily return "excluding" the gap (CRSP is
close-to-close), `cs_rank` (the rank of the outcome), a module global restored
after every fit, the ET/local clock, and the standing-vs-actions gap (87.1%
already actions). Five were caught by reading or measuring. One was caught by
luck.

The machinery keeps improving and the edge keeps not moving, because only
matured decisions move it. What changed is that the next thing to build is
finally something that survived being attacked.
