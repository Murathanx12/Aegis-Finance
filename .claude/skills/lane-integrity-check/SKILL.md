---
name: lane-integrity-check
description: Run before AND after any change that goes near the paper lanes or books, lane YAMLs, strategy contracts, the scheduler's lane path, rebalance logic, or the NAV/positions tables (aegis_pi.db). Verifies the forward record's integrity invariants — config and contract hashes byte-stable, no spurious segments, registry untouched, positions consistent with NAV. The paper_nav write-path is sacred (CANON §5). The website lanes cannot be read while the hosted backend is off (since 2026-11); this skill says what can still be checked.
---

# Lane Integrity Check

The forward track record is the project's one uncopyable asset. Any change in
the same postal district as the lanes gets this check on both sides.

## What exists where (2026-11-19)

- **Website lanes** (conservative / balanced / aggressive, conservative-atr, mirror,
  conviction and the other hosted lanes): their `paper_nav` history is in the hosted
  backend's database on Railway. Hosting is off by owner decision, so
  `/api/pi/track-record`, `/api/pi/registry` and `/api/health/full` answer 404. **Their
  NAV continuity cannot be verified from this machine, and whether the hosted database
  is preserved is unknown.** Say exactly that; never report these lanes as intact or as
  broken on the strength of a local file.
- **The PC's database** `C:\Users\mrthn\aegis-finance\backend\data\aegis_pi.db` (every
  release clone reaches it through `AEGIS_PI_DB_PATH`, exported by
  `scripts/runtime_task.py`; it is never copied or linked). It holds `paper_nav` rows
  for `book:` portfolios only, plus `rule_experiments`. It is live data: open it
  read-only (`sqlite3.connect("file:<path>?mode=ro", uri=True)`), never copy it into a
  worktree, never write to it from a builder.
- **PC paper books** with no database row: each writes its own ledger under
  `backend/data/optimus/` and is governed by a frozen contract in `docs/TRIALS/`.
- **Broker paper accounts:** the execution repo and the PC fleet managers own them;
  their check is broker reconciliation plus advancing receipts
  (`docs/VERIFICATION_2026-10-09.md`), not this skill.

## Why this exists (paid-for lessons)

- **2026-06-11 (THE big find):** rebalance events recorded weights/trades but
  never rewrote `paper_positions` — recorded weights would have silently
  diverged from the NAV book at the first monthly rebalance.
- **Config hash = segment identity:** reverting a lane YAML in place reproduces
  an old hash and corrupts segment contiguity. Rule changes roll FORWARD as a
  new config version, never revert bytes.
- **2026-06-16:** seeded book lanes were marked-to-market but INVISIBLE on the
  track-record endpoint (hardcoded lane list) — an integrity property can hold
  in the DB and still lie on the surface.
- **2026-11-15:** a release clone grew its own `backend\data\aegis_pi.db` beside the
  junctioned data; the wrapper refused every task pointed at it (exit 90, "split
  brain"). Two databases is the failure; the refusal is the guard working.

## Invariants to verify

1. **Lane YAMLs and contracts byte-stable:** in YOUR worktree,
   `git diff --stat origin/main -- backend/data/*.yaml backend/data/copy_lab backend/data/arena docs/TRIALS`
   shows NOTHING unless this change is an explicit, attended new-lane / new-version
   ship. `paper_portfolios.yaml`, `book_lanes.yaml`, `conservative_atr_lanes.yaml` each
   keep their existing content hash; a contract file already in force is write-once
   (a change is a new `v<N+1>` file).
2. **No strategy change to an in-flight tracked lane or book — ever.** Changes ship as
   NEW entries with their own hash and inception (see seed-a-lane).
   Arming/retrofitting an overlay onto a live lane is forbidden (TRIAL-001
   annotation).
3. **Registry untouched:** the `rule_experiments` row count and existing rows are
   identical before/after (PC: a read-only count on the live database; hosted, when it
   is back: `GET /api/pi/registry` → `cumulative_trials`). New rows only via the
   pre-register-trial procedure.
4. **NAV continuity:** every portfolio keeps its history — no gaps you introduced, no
   re-dated rows, no spurious `config_version` boundary. PC: per `portfolio_id`,
   `count(*)`, `min(date)`, `max(date)` and the distinct `config_version`s from
   `paper_nav`, read-only, before and after; every "before" row must still be there
   with the same values. Hosted: cannot be checked today (see above).
5. **Positions ⇄ NAV consistency:** if the change touches rebalance/positions,
   confirm `paper_positions` was rewritten alongside the recorded weights
   (the 2026-06-11 class) — the recorded post-weights must reprice to the NAV.
6. **Surface visibility:** anything marked-to-market must appear on the surface that
   reports it — on the PC, the status page row and the book's own report; on the hosted
   site, `/api/pi/track-record` (the hardcoded-lane-list class). DB-true but
   surface-invisible fails this check.
7. **One database.** No `backend\data\aegis_pi.db` inside a release clone or a worktree
   that a task could open; the wrapper's run log
   (`backend\data\optimus\runtime_switch\runtime_task_runs.jsonl`) shows no new
   `"event": "refused"` row naming a split brain.

## How

- Offline, in your worktree: the lane/PI suites —
  `python -m pytest backend/tests/portfolio_intelligence/ -q -m "not slow" -p no:cacheprovider`
  (hash-isolation and frozen-control tests live there and must stay green). It is a
  targeted directory, not the full suite; check free RAM first.
- PC live state: the read-only queries of invariants 3 and 4 against the live database,
  and `backend\data\optimus\system_status\status.json` (the `decisions` section) for the
  books' rows. `aegis_verified_state` (Optimus) returns HTTP 404 while hosting is off.
- Hosted live state (dormant): `/api/health/full` + `/api/pi/track-record` before/after,
  diffing the lane set, segment boundaries and latest NAV dates; `nav.all_fresh` true.
- If ANY invariant fails: stop, do not commit/push; the fix is attended.
- Run git from YOUR worktree (`git -C <worktree> ...`). Never run a
  state-changing git command in the runtime checkout `C:/Users/mrthn/aegis-finance`:
  scheduled tasks run from it, and on 2026-11-11 a `sparse-checkout` there hid
  ~6,800 tracked files for four minutes.
- State in the report which of the three record kinds you checked and which you could
  not. "Website lanes: not verifiable, hosting off" is a complete and honest line.
