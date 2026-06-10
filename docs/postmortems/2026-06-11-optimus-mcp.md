# Session Post-Mortem — 2026-06-11 — TRIAL-001 pre-registration + Optimus MCP (Goal 6)

## Task 1 — config v2 deploy verification ✓

First `628456e4`-stamped NAV rows landed on **all four lanes** (the three
switched lanes re-marked + the control's first row at $100,000.00); the
balanced series shows the 82be14cb→628456e4 transition between 06-09 and
06-10 — the exact condition that renders the chart's segment break;
`/api/health/full` 4/4 fresh, 0 warnings. Boundary-rebalance cost visible
as ~3bp NAV dips. Honest and expected.

## Task 2 — TRIAL-001 decision rule pre-registered ✓ (before data accrued)

- **Primary (only deciding) metric:** full-window net Sharpe from daily
  `paper_nav` returns, inception 2026-06-10.
- **Window:** ≥12 months (earliest decision 2027-06-10), quarterly
  evaluations thereafter; interim numbers reported, never acted on.
- **Revert:** HRP trails control by **≥0.30** → config v3 via the guarded
  loop (never an in-place YAML revert). Symmetric adopt-confirmation at
  +0.30.
- **Crash override:** SPY −20% in-window → no decision until ≥6 months past
  trough. **Contamination clause** for data defects.
- Tamper evidence: `docs/TRIALS/TRIAL-001-hrp-vs-ew.md` (git timestamp) +
  embedded in the live registry row's notes by an idempotent startup step
  that NEVER overwrites an existing rule (test-pinned — rule changes after
  data accrues are a registry event, not a deploy).
- New: `GET /api/pi/registry` — read-only registry view (cumulative count,
  verdicts, full rows). Deployed at `397e20a`, verified live.

## Task 3 — Optimus MCP server ✓ (Goal 6, the context-loss-tax fix)

Built `optimus/mcp/server.py` (FastMCP, stdio, in the Optimus repo's public
engine — brain stays gitignored). Five read-only tools:
`aegis_verified_state` (live /api/health/full), `aegis_registry`,
`aegis_canon` (V2_GOALS / TRACK_RECORD_POLICY / TRIAL docs / anti-goals),
`aegis_postmortems` (keyword search over this very log), `brain_query`
(Optimus corpus, `Store(read_only=True)` — SQLite mode=ro).

**Cold-start loop proven end-to-end** (`optimus/tests/smoke_mcp_server.py`,
real stdio client = exactly how Claude Code spawns it): all five tools
returned live data — deploy commit, 4 lanes fresh, TRIAL-001 rule read back
from the prod registry, anti-goals section, the Step #2 postmortem, and a
cited brain answer. Wired via `.mcp.json` in the Aegis repo root
(gitignored — machine-specific absolute paths); go.md Phase 0 now prefers
the Optimus tools and falls back to the manual path.

## Decisions / surprises / rejected

- **Boundary held:** Optimus reads Aegis over HTTP + local checkout; the
  registry endpoint was added on the AEGIS side precisely so Optimus never
  touches the Railway volume.
- **Surprise (footgun documented):** the Optimus repo's `mcp/` directory
  vs the installed `mcp` SDK package — safe ONLY while `mcp/` has no
  `__init__.py` (regular packages beat namespace dirs in resolution).
  Noted in the server header.
- Windows cp1252 console broke the smoke test PRINT (not the tools) on a
  `→` character — `sys.stdout.reconfigure(encoding="utf-8")`.
- Rejected: routing postmortem search through the Optimus brain corpus
  (ingest lag would serve stale sessions); direct file search of the Aegis
  repo is the dependable v1 — corpus search stays available via brain_query.
- Optimus repo had unrelated WIP (store.py, ui/) — committed ONLY the MCP
  files; WIP left untouched for Murat.

## Acceptance status (Goal 6 done-when)

"Fresh session Phase 0 pulls from Optimus instead of static docs" — wiring
+ tool loop proven this session; the literal fresh-session confirmation
happens at the next `/go` (the `optimus` server loads from `.mcp.json` on
session start). If the tools appear and Phase 0 runs through them, Goal 6
closes.

## Next session

1. Phase 0 via Optimus MCP (confirms Goal 6 end-to-end).
2. Topmost stack: P1 #6 lane framework (portfolio-mirror + conviction
   lanes) or the grind queue (UTC TTL, PI mypy, F841).
