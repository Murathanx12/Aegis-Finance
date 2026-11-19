---
name: verify-prod-after-deploy
description: Run after a merge to main is RELEASED to the PC (a new release clone, tasks repointed) and before reporting anything as live or running. "Prod" is the PC since 2026-11 — the hosted Railway site is off by owner decision. Verifies the release clone exists and passed preflight, the changed tasks run from it, each changed job's OWN RECEIPT is advancing, the wrapper refused nothing new, and the status page row is green. Green tests and rc 0 are not a live verification (the insider collector passed 12 tests while 403-ing on 100% of prod fetches; the learning loop was refused for 24 days at rc 0).
---

# Verify a release on the PC

A change is verified when the **changed job's own output** demonstrably advanced in
production — not when tests pass, not when the merge lands, not when the task shows rc 0.

**Where production is (2026-11-19).** The owner stopped paying for Railway on purpose.
The hosted backend (`aegis-finance-production.up.railway.app`) answers 404 and stays off
until the owner says otherwise. Everything that runs, runs on the PC: Windows scheduled
tasks started through `scripts/runtime_task.py` from a release clone
`C:\Users\mrthn\aegis-runtime-<tag>` (newest on this date: `20261115b`), plus tasks still
on the WIP checkout `C:\Users\mrthn\aegis-finance`. A push to main deploys **nothing** by
itself. The old Railway procedure is kept at the bottom, dormant.

## Why this exists (paid-for lessons)

- **T9 insider collector (2026-06-17):** 12 green offline tests, worked on dev,
  reported live — a prod check found 100% of its SEC fetches 403-ing. A collector
  that runs but fetches nothing reads as "covered" on every dashboard.
- **rc 0 for 24 days (2026-10-15 → 11-10):** `provider_budget` refused every DeepSeek
  call while the world digest, IIF-1, hyp_lab and the learner reported rc 0. The task
  result column was green the whole time; only the receipts had stopped.
- **Split brain (2026-11-15):** a release clone grew its own `backend\data\aegis_pi.db`
  and the wrapper refused every task pointed at it (exit 90). The refusal was correct
  and visible only in the wrapper's run log.
- **A release the shortcut does not use (2026-11-14):** tasks ran from the new clone
  while `Aegis.lnk` still opened the old one; the owner saw an empty reader page.

## Who does what

Cutting a release, repointing a task and anything in the runtime checkout are
**brain-only, attended** steps (`run-a-chunk` → "Only the brain, attended"). A builder
runs the read-only steps 2–6 and reports; it never creates a clone, never changes a
scheduled task, and never runs `--retire`.

## Steps

1. **CI first.** Nothing is released from a red main:
   `python -m scripts.ci_watch --wait` (public API, no token; it filters on YOUR full head
   sha and on the workflow named CI). A run that never starts may be the Actions-minute
   quota; read the run list, never assume green.
2. **The release clone exists and passed its own preflight.** The release is a pushed tag
   (`20261115b` style) whose commit is an ancestor of `origin/main`, cloned by
   `python -m scripts.runtime_release --tag <tag>` (brain). Check, read-only:
   - `C:\Users\mrthn\aegis-runtime-<tag>` exists and `git -C <clone> rev-parse HEAD`
     equals the tag's commit;
   - the newest `backend\data\optimus\runtime_switch\release_<tag>_*.json` in the LIVE
     data folder has `"verdict": "PASS"` and its `checkout` is that clone. Read `warned`
     too: a warning is noted, not ignored.
3. **The changed tasks are pointed at it.**
   `python -m scripts.runtime_release --repoint-plan <tag> --out <report dir>` reads the
   scheduler (read-only) and classifies every task: `ON_TARGET`, `REPOINT`, `ATTENDED`
   (can reach an order path: the owner's step, never scripted), `SKIP_RUNNING`,
   `REFUSED_MODULE_MISSING`, `REFUSED_CONFIG_DRIFT`. It writes `repoint_<tag>.ps1` and
   `rollback_<tag>.ps1` and runs neither. Exit 3 = a task was refused, 2 = the plan was.
   Every task your change touches must read `ON_TARGET` before you go on; a task that
   still names an older clone or the WIP checkout is running the OLD code.
4. **Each changed job's OWN RECEIPT advanced, after the repoint.** Find the file the job
   writes (its `--out`, its ledger, its `*_runs.jsonl`) and check its own stamp is newer
   than the repoint and its CONTENT is non-empty: rows fetched, rows graded, a decision
   written. Date the receipt by the stamp inside it, never by file mtime. A new collector
   is verified when it FETCHED (non-zero count or a PIT row), not when it ran. If the job
   has not had a scheduled run yet, say so and name the time of the next one (compute it
   in ET: the machine is UTC+8, the schedule is US/Eastern).
5. **No new wrapper refusal.** Read the tail of
   `backend\data\optimus\runtime_switch\runtime_task_runs.jsonl` (LIVE data folder) for
   rows with `"event": "refused"` (exit 90, with a `why`) or an `"event": "end"` whose
   `rc` is non-zero, for your `clone` and module, since the repoint. A refusal is a
   finding to report with its `why`, never something to route around.
6. **The status page row is green.** `backend\data\optimus\system_status\status.json`
   is rewritten every 15 minutes by the `AegisSystemStatus` task (to refresh by hand,
   from a release clone: `python -m scripts.system_status --html`; read-only, exit 3 when
   a required row could not be determined, 2 with `--strict` when any row is DOWN).
   Check `generated_utc` is recent, then the row for your task under `sections.tasks`
   and any row your change feeds (learning, universe, decisions, night, infrastructure):
   `OK` is green; `DEGRADED`, `DOWN` and `UNKNOWN` are not. The rows that were already
   red before your release are listed as pre-existing, not hidden. The same page is
   `status.html`, which the desktop app shows.
7. **The desktop app, when the change is in the app or the frontend.** A new clone has
   no `node_modules` and no frontend export; `runtime_release` prints the `npm ci`, the
   export and the `Aegis.lnk` repoint and runs none of them. Verify
   `<clone>\frontend\out\desktop\reader\index.html` exists and that the shortcut's target
   names the new clone, then open the page (playwright or by eye) and read its content.
8. **Watch for the silent-failure shape:** a subsystem that "ran" with zero output
   (0 fetched, all-zero snapshots, empty payloads) is a FAILURE until proven otherwise —
   see the `silent-fragility-audit` skill.
9. **Report honestly.** Three separate words: *merged* (on main), *released* (clone made,
   preflight PASS, task `ON_TARGET`), *running* (its own receipt advanced after the
   repoint, with the stamp quoted). State which tasks still run older code. Never report
   "live" on the strength of tests, a merge or rc 0.

## What this skill cannot tell you

- The Optimus tool `aegis_verified_state` calls the hosted backend and returns HTTP 404
  while hosting is off. Until Optimus is patched to fall back to the local status
  receipt, read `status.json` directly (step 6).
- The website lanes' NAV (`paper_nav` for conservative / balanced / aggressive and the
  other hosted lanes) lived on the Railway volume. Nothing on the PC marks them, and the
  local `backend\data\aegis_pi.db` holds only `book:` portfolios. Their state since the
  shutdown is **unknown from this machine** — do not report them fresh or stale.
- The frontend on Vercel: not checked by this skill. Its deploy state is unverified.

## Dormant: when hosting returns (Railway procedure, not runnable today)

Kept so it is not re-derived. Use it only after the owner turns hosting back on.

1. Railway deploys are gated on GitHub CI ("Waiting for CI"); a red CI silently blocks
   every deploy (2026-07-08).
2. Poll `GET /api/health/full` until `deploy.commit` equals the pushed sha (build ≈ 3–8
   min after CI); if it never flips, `railway status`.
3. On the same response: `scheduler.nav.all_fresh` true, no NEW `recent_warnings` tied to
   the change.
4. Hit the changed endpoint and read the body, not the status code; scheduler wiring is
   verified on the next scheduled run's line in `railway logs`.
5. If the public URL is unreachable, distinguish app-down from edge-down first
   (`railway logs` plus a second vantage). The app can be healthy internally while the
   public URL refuses all connections (2026-07-08).
