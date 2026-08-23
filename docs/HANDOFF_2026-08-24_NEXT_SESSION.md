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

## 4. Monday's verification events — unchanged, plus one

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

Full reasoning in `ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.

~~1. `ANALYST_COCOVERAGE_GRAPH_v1`~~ — **DONE**, verdict CONTINUE. It licensed
   `GRAPH_PROPAGATION_v1` (plain equal-weighted peer return, nothing fancier
   earned its place) and it un-licensed the GNN. Build the selector when a
   book slot is free; it is no longer the *blocking* item.

1. **`EVENT_RESPONSE_v1`** — continuation vs overshoot after an event, from the
   `g4/earnings_v1` corpus and TAQ. Not the event store: it has no history yet.
2. **`RELATIVE_VALUE_NN_v1`** — the corpus exists. **The effective n is 145 date
   blocks, not 72,495 pairs** (CANON §58); split by date block or the result is
   about within-month interpolation. Decision rule declared in advance: if an
   MLP does not beat LightGBM out of block, there is no neural challenger and
   the line closes with a receipt.

Each is a separate `PRODUCT_EXPERIMENT` book. **None of them goes into
`arena_composite`** — folding them in would hide the only thing being tested,
which is whether their errors are different errors.

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
| Tue 17:45 | first real intent submit | trades, `basis=intent`, `decided_for=<Tue>`, and an `execution ledger: N submission(s) recorded` line |
| Wed 17:45 | first reconciliation | `Execution reconcile: … filled=N mean_slippage_bps=…` — the first time this project has ever compared an assumed fill to a real one |

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
