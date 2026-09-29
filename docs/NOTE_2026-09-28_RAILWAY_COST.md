# Note 2026-09-28 -- Railway cost, what was changed tonight

Owner's request (2026-09-28): make Railway cheaper without deleting anything, because the PC now
runs the nightly work, while keeping every service restorable for a future real-money run.

**Where the record is.** Service ids, usage figures, account states, the state backup and the exact
rollback commands are in `backend/data/optimus/local_pc/railway/RAILWAY_CHANGES_2026-09-28.md`
(gitignored, this machine only). This note says only what changed, in general terms.

## Changed (both reversible; nothing deleted)

1. **One execution-repo paper loop was stopped** (its latest deployment removed; the service, its
   volume, its variables and its deploy history remain). It was chosen because its paper account was
   flat with no open orders, read-only, twice. Its volume state was copied to this machine first and
   the copy verified by size and SHA-256 against the container. The four loops whose accounts hold
   positions were **not** stopped: a stopped loop cannot manage exits.
2. **The website backend's start command** no longer launches the temporary
   `scripts/arena_paper_repair_once.py` hook. The file was not in the image (every boot logged
   `can't open file`), and if it ever came back it would have run a paper decision pass and submitted
   paper intent on every wake. The deploy was from `main` HEAD with CI green; the health route, the
   track-record route and the boot log were read from outside afterwards.

## Found, not changed (owner's decisions)

- The website's in-process close jobs have not run since 2026-09-18 (`scheduler.nav.all_fresh`
  false, forecast accrual stopped). The timing matches the warm loop being switched off: with no
  outbound traffic the app really sleeps, and APScheduler only catches up a missed slot if the app is
  awake within its one-hour grace. Keep it awake, or wake it in the grace windows from a free cron.
- Most of the remaining bill is the four position-holding paper loops. They can be stopped one by one
  as their accounts go flat, or made cheap in place by the two fixes in
  `docs/REVIEW_2026-09-26_RAILWAY_COST.md`.
- The plan tier, and the retired loop's volume, are the owner's call.

## Monthly check

`python -m scripts.railway_cost_check` reads the plan, billing period, usage so far and a 7-day
per-service run-rate from Railway's usage API, writes a receipt with a run id under the local folder
above, and prints one line (`--line-only`) suitable for the Telegram `report` reply.
