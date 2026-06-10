# Session Post-Mortem — 2026-06-10 (evening) — /api/health/full + status tooling

## Deploy verification recorded (closes the P0 observability arc)

Murat verified externally on prod: `nav.all_fresh: true`, balanced lane
shows real NAV **100,000 → 100,618.85** with `config_version` per point.
**P0 #1 (history→paper_nav), #3 (freshness canary), #4 (curve
reconciliation/labels) are DONE in production.** The transcript's open
question — "are paper_nav rows actually landing?" — is answered: yes,
since inception 2026-06-08. Also: `main` now auto-deploys and is the ship
target; Railway CLI linked to project `selfless-courage` during this
session (`railway status` verified working).

## What shipped

1. **`GET /api/health/full`** — one-call session status aggregating:
   deploy identity (`RAILWAY_GIT_COMMIT_SHA`, version, uptime), full
   scheduler block (incl. per-lane NAV freshness), track record (per-lane
   latest NAV + since-inception %, age in days), data-source health
   (yfinance batch success rate; FRED series loaded/failed **by name**),
   and a ring buffer of the last ≤50 WARNING+ log records. Read-only; zero
   write-path changes.
2. **`backend/observability.py`** — RingBufferHandler on the root logger
   (installed at import in main.py, idempotent) + thread-safe data-source
   counters; hooks in `data_fetcher` (`_fetch_batch_yahoo`,
   `fetch_fred_data`) that never raise. Documented as the second sanctioned
   exception (with cache.py) to services-are-stateless.
3. **go.md Phase 0 rewritten** — one `GET /api/health/full` instead of
   multiple endpoints; Railway CLI (`railway status`/`railway logs`) for
   deploy-level detail; **one-screen status report format** (DEPLOY / TRACK
   RECORD / SCHEDULER / DATA SOURCES / WARNINGS / GIT / REGISTRY / OPEN
   RISKS) so Murat reads a block, not JSON. grind.md prod-read rail updated
   to match.
4. **GPRH bug fixed by removal.** Tested against FRED live: GPRH, GPRD,
   GPR all "series does not exist" — the Caldara-Iacoviello GPR index is
   not FRED-hosted, so there is no correct ID to substitute. Since the
   fetch failed on every run since the entry was added, no feature ever
   existed → removal is provably behavior-identical (verified both
   consumers: `news_intelligence.compute_event_score` defaults to neutral
   0.3 when `fred_gpr is None`; `features.py` gpr interaction is gated on a
   column that never existed). FRED-hosted *uncertainty* proxies exist
   (USEPUINDXD daily, GEPUCURRENT monthly) — adding one would be a NEW
   feature → parked as an evolution-loop candidate, note in config.py.

## Decisions

- **Remove, don't substitute, GPRH.** A proxy swap would silently add a
  feature to the live matrix (frozen V1). The honest fix is deletion +
  documented candidate.
- **Ring buffer truncates messages at 300 chars** and never raises from
  `emit` — observability must not be able to take the app down.
- Source counters update only on real fetches (both fetchers are
  `@cached`); `last_fetch_at` makes staleness visible rather than faking
  per-request freshness.
- Shipped by **merging `lab/autonomous-rd` → `main`** (main auto-deploys;
  main was already at the lab tip `83086bb`, so this is a fast-forward).

## Surprises

- "Now-linked Railway CLI" wasn't — `railway status` said no linked
  project. Murat linked it interactively mid-session; verified working
  after. go.md written to degrade gracefully if the link is ever lost.
- `railway status` exits 255 even on success (output is fine) — don't
  gate scripts on its exit code.

## Rejected approaches

- Exposing the deployed commit by shelling out to `git rev-parse` at
  runtime — the image may not contain `.git`; `RAILWAY_GIT_COMMIT_SHA` is
  the supported source, with "unknown" fallback locally.
- A persistent (SQLite) warning log — the no-database rule covers it;
  reset-on-deploy is acceptable for a session-start signal.

## State for next session

- `/go` Phase 0 is now: read docs → one curl → one-screen report.
- Topmost open V2 items: P0 #2 (live equity-curve UI — unblocked now that
  history serves real NAV), then Step #2 leakage-safe optimization.
- PROPOSALS.md (5 entries) still awaiting verdicts; V2_GOALS.md still
  missing.
