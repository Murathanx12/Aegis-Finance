# Session Post-Mortem — 2026-06-10 — V2 P0 #1 + #3 (observability)

First `/go` session. Track record age at session start: 2 days (inception 2026-06-08, config `82be14cb6039bfae`).

## What shipped

1. **P0 #1 — `/api/pi/reference/{lane}/history` wired to `paper_nav`.**
   The Phase-6 stub seeded `inception_value` at each rebalance date — a synthetic
   flat line indistinguishable from real data. Now the equity curve is the real
   MTM NAV series, each point stamped with its `config_version` (segment
   boundaries for versioned rule changes), plus `has_nav_data` so an empty state
   is structurally distinct from a flat line. Response gains `inception_date` /
   `inception_value`.

2. **P0 #3 — canary upgraded from liveness to freshness.**
   - `last_mtm` is no longer stamped when every lane fails to mark (was:
     stamped unconditionally after `mark_all_lanes`, i.e. green canary over
     zero rows was possible).
   - `/health/scheduler` now includes a `nav` block: per-lane
     `MAX(date) FROM paper_nav` vs the expected last trading day
     (pre/post-close aware, weekend/holiday aware via `US_MARKET_HOLIDAYS`
     in config — extends through 2027), plus `all_fresh`.
   - `_get_current_prices` survives per-ticker fetch failures (one bad ticker
     no longer aborts the loop).
   - **New guard:** total price failure (zero live prices) skips the NAV
     persist entirely instead of writing an all-cost-basis row — a flat fake
     row would have poisoned the very curve P0 #1 just exposed.

## Decisions

- **Freshness is close-of-day granularity.** Expected NAV date = today only
  after 17:00 ET, else prior trading day. Intraday MTM gaps (job dies at 11:00,
  10:30 row exists) are not caught — accepted: pages within one cycle (next
  day), no false alarms, matches the go.md done-when.
- **Static NYSE holiday list in config** (2026–2027) instead of a market-
  calendar dependency. Expiry failure mode is a loud false "stale" on a future
  holiday, not a silent pass.
- **Partial price failure → cost-basis fallback persists; total failure → no
  row.** The line between "degrade gracefully" and "fabricate data" is ≥1 live
  price.
- Post-mortem convention established: `docs/postmortems/`, one file per
  session, for future Optimus ingestion.

## Surprises

- `docs/V2_GOALS.md` referenced by go.md Phase 0 **does not exist** (transcript
  open item: Murat to write "Murat's additions"). Worked from V2_ROADMAP.md +
  go.md's embedded goal stack instead.
- Live deploy healthy and fresh at session start: `last_mtm` 2026-06-09T20:30
  (Tuesday close) — but whether `paper_nav` rows actually landed is still
  **unverified** until this session's endpoint deploys. That verification is
  the first action of the next session.
- Two dirty files in the worktree were a real latent bug: `%,.0f` is an
  invalid printf-style logging format (raises inside logging on every lane
  init / replay start). Committed with this session.

## Rejected approaches

- **`pandas_market_calendars` dependency** for the trading calendar — overkill
  for a freshness canary; static list is auditable and dependency-free.
- **Stamping `last_mtm` if *all* lanes succeed (vs ≥1):** rejected — one lane
  failing while two succeed should not mark the whole canary stale;
  the per-lane `nav` block now carries the granular signal.
- **Verifying Railway `paper_nav` rows via local DB inspection** — local
  `aegis_pi.db` is stale dev state (1 lane, 0 NAV rows, inception 2026-05-02);
  production state lives on the Railway volume and is only observable through
  the API. (This is why P0 #1 had to come first.)

## State for next session

- Tests: 337 PI tests green (14 new: 11 canary freshness, 3 history wiring).
- **Next:** deploy this commit → hit `/api/pi/reference/*/history` and
  `/health/scheduler` → confirm real NAV rows + `all_fresh: true`. That
  closes the transcript's open item ("are rows landing?") with a measured
  answer. Then P0 #2 (equity-curve UI) is unblocked, then P0 #4 (reconcile
  the three curves).
- Registry: 0 trials adopted, 0 rejected (loop not built — Step #3 pending).
