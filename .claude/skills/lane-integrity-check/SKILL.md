---
name: lane-integrity-check
description: Run before AND after any change that goes near the paper lanes, lane YAMLs, the scheduler's lane path, rebalance logic, or NAV/positions tables. Verifies the track record's integrity invariants — config hashes byte-stable, no spurious segments, registry untouched, positions consistent with NAV. The paper_nav write-path is sacred (CANON §5).
---

# Lane Integrity Check

The forward track record is the project's one uncopyable asset. Any change in
the same postal district as the lanes gets this check on both sides.

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

## Invariants to verify

1. **Lane YAMLs byte-stable:** `git diff --stat -- data/*.yaml` shows NOTHING
   unless this change is an explicit, attended new-lane/new-version ship.
   `paper_portfolios.yaml`, `book_lanes.yaml`, `conservative_atr_lanes.yaml`
   each keep their existing content hash (hashes are printed in registry rows
   and `/api/pi/track-record` segments).
2. **No strategy change to an in-flight tracked lane — ever.** Changes ship as
   NEW pre-registered lanes with their own hash and inception (see seed-a-lane).
   Arming/retrofitting an overlay onto a live lane is forbidden (TRIAL-001
   annotation).
3. **Registry untouched:** `GET /api/pi/registry` — `cumulative_trials` count
   and existing trial rows identical before/after. New rows only via the
   pre-register-trial procedure.
4. **NAV continuity:** every lane on `/api/pi/track-record` keeps its history —
   no gaps, no re-dated rows, no spurious `config_version` segment boundary you
   didn't intend. `nav.all_fresh` true on `/api/health/full`.
5. **Positions ⇄ NAV consistency:** if the change touches rebalance/positions,
   confirm `paper_positions` was rewritten alongside the recorded weights
   (the 2026-06-11 class) — the recorded post-weights must reprice to the NAV.
6. **Surface visibility:** anything marked-to-market must appear on
   `/api/pi/track-record` (the hardcoded-lane-list class). DB-true but
   API-invisible fails this check.

## How

- Offline: run the lane/PI suites —
  `python -m pytest backend/tests/portfolio_intelligence/ -q -m "not slow"`
  (hash-isolation and frozen-control tests live there and must stay green).
- Live: `aegis_verified_state` (Optimus) or `/api/health/full` +
  `/api/pi/track-record` before/after, and diff the lane set + segment
  boundaries + latest NAV dates.
- If ANY invariant fails: stop, do not commit/push; the fix is attended.
