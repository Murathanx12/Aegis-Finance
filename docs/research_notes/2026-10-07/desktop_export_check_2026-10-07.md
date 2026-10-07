# Desktop export check — 2026-10-07 (C24)

Verifier session. Task: prove the new pages (`/opportunities`, `/brain`, `/arena`,
`/forecast-lab`, `/theory-lab`) work in the desktop export, offline, with no keys.
**Half done**: the frontend build receipt is green and the static code path was
read end to end and found correct. **The live launch + probe table was BLOCKED
by the session's own RAM gate** and is owed to the next session — see "Owed"
below for the exact command to finish it.

## 1. `python -m scripts.frontend_check` — GREEN, exit 0/0/0

Ran once (`AEGIS_IGNORE_DOTENV=1 python -m scripts.frontend_check`), receipt at
`backend/data/optimus/frontend_check.json`:

| step | cmd | exit | seconds |
|---|---|---|---|
| tsc | `npx tsc --noEmit` | **0** | 6.77s |
| site | `npx next build` | **0** | 22.79s |
| desktop | `AEGIS_DESKTOP_BUILD=1 npx next build` | **0** | 13.09s |

`verdict: GREEN`, `headline: "3 build(s) green in 43s"`. The site build's route
list includes `/opportunities`, `/forecast-lab`, `/theory-lab` as static routes;
the desktop export list is the same minus the API-route-only pages (expected —
a static export has no server routes). No code was changed, so this single run
stands for the `npx tsc --noEmit` the task also asks for at the end; see
"Tests run" below.

## 2. Desktop launch + probe table — NOT RUN (RAM gate)

Free RAM was checked repeatedly across the session (PowerShell
`(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB`):

| when | free GB |
|---|---|
| session start | 6.09, then 6.04 |
| immediately after `frontend_check` finished | 5.88 |
| +5s | 5.83 |
| +20s (one recovery blip) | 6.06 |
| +~10s, right before the planned launch | 4.16 |
| +20s | 4.96 |
| +30s | 4.73 |
| right before the closing `tsc` re-check | **3.60** |

`Get-Process | Sort-Object WS -Descending` at the low point showed another
`python` (≈1.37 GB working set), a `node` (≈1.08 GB), and two other `claude`
processes (≈709 MB and ≈498 MB) — i.e. this machine had other sessions actively
building/running at the same time, not a leak from this session's own build.
`backend/data/optimus/local_pc/CLOUD_SESSION_LOCK.json` does not exist, so no
session had declared a `heavy_job` lock, but the standing instruction is to
**refuse below 6 GB regardless**, and 5 of 8 readings were below that floor with
no stable recovery. Per the standing rule against killing by image name (and
because these looked like other sessions' legitimate work, not orphans), nothing
was terminated.

So neither the desktop launch (`AegisDesktop.exe` under `dist/AegisDesktop/`, or
`python -m desktop.launcher` from source) nor its probe table was attempted this
session. This is the task's actual acceptance line
(`docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` §5a row C24: "desktop
export exit 0; **a receipt from a launch via Start-Process**") and it is not yet
satisfied — only the "export exit 0" half is.

## 3. What was verified by reading code (no launch needed for this part)

Because the live launch couldn't run, the offline/no-keys behaviour was checked
statically instead, end to end:

- **API base in desktop mode.** `frontend/src/lib/api.ts:35-56`
  (`resolveApiBase`) returns `""` whenever the desktop flag is true, so every
  `fetchAPI`/`fetchOnce` call (`frontend/src/lib/api.ts:104`) resolves to a
  same-origin relative path. `frontend/next.config.ts` sets
  `NEXT_PUBLIC_AEGIS_DESKTOP_BUILD: "1"` and **blanks**
  `NEXT_PUBLIC_API_URL: ""` only when `AEGIS_DESKTOP_BUILD=1` (the desktop
  export path), so a stale Railway URL cannot be inlined into the desktop
  bundle. This is the exact fix CLAUDE.md's "a windowless process has no
  stdout" sibling bug (the 2026-09-10 "fetch error" report) already put in
  place; it was not touched, only re-read and confirmed intact.
- **The five new pages' data calls.** Grepped
  `frontend/src/app/{arena,brain,forecast-lab,opportunities,theory-lab}/*.tsx`
  for `fetch(`, `API_BASE`, `https://`, `NEXT_PUBLIC`: the only hit is
  `frontend/src/app/brain/page.tsx:46`,
  `BRAIN_MAP_URL = "https://optimus-brain-alpha.vercel.app"` — an explicit
  `<a target="_blank">` link out to a **different, older showcase repo**
  (labelled as such in its own `title=` attribute), not a data fetch the page
  depends on. Everything else goes through `getArenaLatest`, `getArenaStories`,
  `getOpportunitiesLatest`, etc. in `lib/api.ts`, which all use the
  same-origin `API_BASE` above. No absolute production URL feeds any of the
  five pages' own data.
- **Sidebar.** `frontend/src/components/sidebar.tsx` already lists all five
  routes (`/opportunities` OPP, `/arena` ARENA, `/forecast-lab` FLAB,
  `/theory-lab` TLAB, `/brain` BRAIN) — nothing missing, nothing to add.
- **Static export mount.** `backend/main.py:644` `mount_desktop_frontend`
  mounts `frontend/out` via `StaticFiles(html=True)` at `/`, gated on
  `AEGIS_DESKTOP=1`, mounted **last** so it never shadows `/api/*`. It reads
  `frontend/out` via `AEGIS_DESKTOP_FRONTEND` env or
  `Path(__file__).resolve().parent.parent / "frontend" / "out"` — i.e. relative
  to `backend/main.py`'s own location, which is correct both running from
  source and under the launcher's spawned child (which is never frozen; see
  next point).
- **Frozen-path family, specifically for this launcher.** Only
  `desktop/launcher.py` (+ `desktop/_interp.py` + pywebview) is what PyInstaller
  freezes (`dist/AegisDesktop/AegisDesktop.exe` exists, built already). The
  launcher never imports `backend` or `desktop.aegis_desktop` — it finds the
  checkout (`find_checkout`, markers `backend`/`scripts`/`desktop`/`.git`),
  resolves the checkout's own interpreter (`desktop/_interp.py`: checked
  `.venv/Scripts/python.exe` exists at repo root — it does), and spawns
  `[<that interpreter>, "-m", "desktop.aegis_desktop", ...]` as a **child
  process under a real, unfrozen Python**. `desktop/aegis_desktop.py::repo_root()`
  then takes the `not getattr(sys, "frozen", False)` branch and returns its own
  parent directory, i.e. the real checkout — the exact mechanism that is
  supposed to make "a path that resolves differently when frozen" impossible
  for this app, by construction (`desktop/launcher.py`'s module docstring,
  lines 1-21, states this was the point of the 2026-09-11 rewrite). Before
  importing `backend.main`, `start_backend()` (`desktop/aegis_desktop.py:276-330`)
  explicitly sets `AEGIS_REPO_ROOT` and `AEGIS_DATA_DIR=<root>/backend/data` on
  the child's own environment — matching the non-desktop default exactly, so
  `backend/config.py`'s `PUBLIC_RECEIPTS_DIR` (fixed to the image path,
  independent of `AEGIS_DATA_DIR`, per today's earlier prod fix — see
  `docs/research_notes/2026-10-07/prod_receipts_in_image_2026-10-07.md`) and
  `OPTIMUS_LEDGER_DIR` both resolve inside the real checkout in desktop mode
  too, not inside the frozen bundle. This is a code-reading confirmation, not a
  live one — see "Owed".

**No fix was made.** Everything this layer is responsible for (the API base,
the five pages' fetches, the sidebar links, the static-export mount, the
frozen/unfrozen boundary) was already correct on inspection; nothing needed a
path-constant change or an absolute-URL fix.

## 4. Owed to the next session

1. **The actual launch-and-probe**, blocked today by sustained free RAM < 6 GB
   (see table above) while other sessions were active. Exact command for next
   time, run only when free RAM is stably ≥ 6 GB and no `heavy_job` lock is
   held:

   ```powershell
   $env:AEGIS_IGNORE_DOTENV = "1"
   Start-Process -FilePath "C:\Users\mrthn\aegis-finance\dist\AegisDesktop\AegisDesktop.exe" `
     -ArgumentList "--no-update","--serve","--no-llama" -PassThru |
     Tee-Object -Variable launchProc
   # then poll backend/data/optimus/aegis_desktop_report.json for "port",
   # record its "pid" and the launcher's own PID from
   # backend/data/optimus/launch_receipt.json ("steps" -> step "shell" -> "pid"),
   # probe http://127.0.0.1:<port>/{,"opportunities","brain","arena",
   #   "forecast-lab","theory-lab","health"} and the six API endpoints
   #   (/api/arena/v1/latest, /api/legibility/v1/{forecast-lab,theory-lab,
   #    system-health,brain}, /api/opportunities/latest), expecting 200 and
   #   served_from naming the published copy, then stop ONLY the recorded
   #   shell PID (Stop-Process -Id <pid>), never the launcher's own or by
   #   image name.
   ```

   `--no-update` is deliberate: this session already produced a green
   `frontend_check` receipt and the branch has many modified data files
   unrelated to code (would make `git status --porcelain` dirty anyway and
   skip the pull regardless) — no need to redo the build.
2. **A live confirmation** that `PUBLIC_RECEIPTS_DIR`/`AEGIS_DATA_DIR`
   actually resolve as described in §3 inside the spawned shell (today's check
   was code-reading only, consistent with CLAUDE.md's own warning that
   "absence of a local object is not evidence of absence" cuts both ways —
   code reading is not the same as a receipt from a real launch).
3. Confirm `/api/health` payload names a `served_from` for the six
   `public_receipts`-backed endpoints the same way prod does now, from inside
   the desktop shell specifically (not just from `uvicorn` run directly, which
   was the prod fix's own repro and is not the same code path as the frozen
   launcher's spawned child).

## Tests run

- `python -m scripts.frontend_check` (covers `npx tsc --noEmit` already, exit 0;
  see §1). No code was changed, so a second standalone `cd frontend && npx tsc
  --noEmit` was not re-run — free RAM was 3.60 GB at that point in the session
  (see §2 table), below the 6 GB floor, and tsc is also a Node build step this
  rule applies to. Owed alongside item 1 above once RAM recovers, though the
  frontend_check result already covers it for the current, unchanged tree.
- No backend/frontend code was edited this session, so there is nothing new to
  add a test for.
