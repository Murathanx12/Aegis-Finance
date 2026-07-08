---
name: verify-prod-after-deploy
description: Run after every push that deploys to Railway — verifies the deploy actually landed AND the changed surface actually works live. Use when a push to main completes, when a deploy is claimed done, or before reporting any shipped feature as live. Green tests are not a live verification (the insider collector passed 12 tests while 403-ing on 100% of prod fetches).
---

# Verify Prod After Deploy

A deploy is verified when the **changed surface** demonstrably works in prod — not
when tests pass, not when the push succeeds, not when health returns 200.

## Why this exists (paid-for lessons)

- **T9 insider collector (2026-06-17):** 12 green offline tests, worked on dev,
  reported live — a prod check found 100% of its SEC fetches 403-ing. A collector
  that runs but fetches nothing reads as "covered" on every dashboard.
- **CI gate (2026-07-08):** Railway deploys are gated on GitHub CI ("Waiting for
  CI"). A red CI silently blocks every deploy — the push "landing" means nothing.
- **Edge outage (2026-07-08):** the app can be healthy internally while the public
  URL refuses all connections. Health from inside ≠ reachable from outside.

## Steps

1. **CI first.** A push does not deploy until CI is green:
   `curl -s "https://api.github.com/repos/Murathanx12/Aegis-Finance/actions/runs?per_page=1"`
   → check `status`/`conclusion` for YOUR head sha. Red CI = no deploy, fix it.
2. **Confirm the commit flipped.** Poll `GET /api/health/full` until
   `deploy.commit` equals your pushed sha (Railway build ≈ 3-8 min after CI).
   If it never flips: `railway status` (look for "Waiting for CI" or a stuck
   deployment). Prefer `aegis_verified_state` (Optimus MCP) when available.
3. **Read the canaries on the same response:** `scheduler.nav.all_fresh` must be
   true; `recent_warnings` must not contain NEW warnings tied to your change
   (pre-existing ones are noted, not ignored).
4. **Exercise the changed surface directly.** Whatever this deploy changed, hit
   its live endpoint / trigger its live path and check the CONTENT, not the
   status code. New collector → confirm it FETCHES (log line with nonzero
   counts, or a PIT row), not merely that it ran. New endpoint → curl it and
   read the body. Scheduler wiring → check the next scheduled run's log line
   via `railway logs`.
5. **Watch for the silent-failure shape:** a subsystem that "ran" with zero
   output (0 fetched, all-zero snapshots, empty payloads) is a FAILURE until
   proven otherwise — see the silent-fragility-audit skill.
6. **Report honestly.** State what was verified live vs what awaits its first
   scheduled run (e.g. "collector wired; first collection lands at the 20:30 UTC
   daily check — verify its log line then"). Never report "live" on the strength
   of tests alone.

## If the public URL is unreachable

Distinguish app-down from edge-down before touching anything: `railway logs`
(app serving internal probes?) + a second vantage (WebFetch). App healthy +
edge dead = Railway networking; a redeploy may rebind; dashboard
delete/regenerate domain is the escalation. The track record is safe either
way — NAV marking is outbound.
