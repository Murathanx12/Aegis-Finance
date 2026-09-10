# HANDOFF 2026-09-10 — BUILDER MAP FOR OPUS (the crash, the fixes, the .exe)

**From:** Fable 5.1 (survey only, ~10 tool calls; Murat's Fable budget is at 90%).
**To:** the Opus session that BUILDS today. Spawn agents on `model: "opus"`, never Fable.
**Read order:** this file → `HANDOFF_2026-09-09_DAY_RUN_TO_AEGIS_DESKTOP.md` (§2 control API,
§4 must-not-regress, §5 lessons) → `ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md` §10.7 (app spec)
and §11.10–11.11 (defect list) → `CLAUDE.md` → `docs/AEGIS_STRATEGIC_INVARIANTS.md`.
Run `session_briefing()` + `aegis_verified_state()` first (CLAUDE.md protocol step 1).

Murat's mandate for today, verbatim in intent:
1. see where we are and what we built;
2. **validate** what was built, **fix and improve the nightly sims** so they learn and
   improve autonomously (math AND methodology);
3. **create the EXE today** — one click runs sims and all services, with the local AI
   model we built in as the free built-in assistant;
4. improve the ideas where needed.

---

## 0. SCOREBOARD (unchanged since 09-09; nothing ran to completion overnight)

| | |
|---|---|
| RESULT IMPROVEMENT | **NONE.** The PC crashed mid-queue. |
| best historical net strategy vs market | none that survives its own control above the tradability floor |
| best forward paper strategy | none — six books −4.43% aggregate first week, SPY −0.12% |
| only live lane | **R2** (local 7B on anonymised monthly digest): +16.19%/yr over shuffled-digest control, t 3.92, 112 blocks. CONDITIONAL: gross, 135 names, prompt unregistered |
| LLM spend | $0.00 (all `local_gguf`) |
| tests | fast suite 7,845 / 0 on 09-09; **not re-run since** |
| processes | 0 running; `llama-server` state UNKNOWN after the reboot — check `127.0.0.1:8080` |

---

## 1. THE CRASH — what the disk says

`backend/data/optimus/night_factory_2026-09-09/`:

| job | run | state |
|---|---|---|
| E1_news_return_panel | 1 | OK, receipt. 339,657 cells / 3,031 symbols / 2025-01-02..2026-09-08. Parquet at `text_return_panel/news_returns_2025_26.parquet` |
| C2_curriculum_transfer | 1 | OK, receipt. Curriculum NOT earned (see §2.2 — its NET numbers are a cost-model artefact) |
| **G3_evolve_v2** | 1 | **FAILED: `exited 1073807364 with no receipt`** after 11,102 s, gen 340, 1,933 evals, 4,138 dd-refusals. `0x40010004` = `DBG_TERMINATE_PROCESS` — the OS killed it (the crash), not a Python error. Last logged best: +15.9%/yr median-excess, win 1.00, β 0.80. |

Nothing after G3 in that queue ran. The 09-08 directory is complete (D1–D4, G1–G3, N1/N2,
P6 ×4, R2 ×2, RW1 ×3 + pooled, RW2, H5 read, three amendments).

**Defect the crash exposed (fix first, it is the whole "autonomous" story):**
a 3–5 h evolutionary job holds its entire result in memory and writes ONE receipt at
the end. `G3_evaluations.jsonl` is appended per evaluation (`night_g3_evolve_v2.py:302`),
so the raw evaluations survived, but there is no elite/lineage checkpoint and no
`--resume`. Three hours of $0 compute and a real learning curve are gone from the
receipt. `night_factory.py` has no resume either: `_receipt_path` only bumps the run
number (`:222`); a job with a log but no receipt is re-run from zero.

---

## 2. VALIDATE + FIX THE NIGHT SIMS (math and methodology) — ordered

Every item below has a receipt or a line number behind it. Do them in this order; each
is small. Add a test per fix in the `test_x9_day_run_numbers.py` pattern (a number the
UI or a doc asserts is pinned to its receipt).

### 2.1 Crash-safety = the autonomy floor (G3, then every long job)
- Checkpoint per generation: population, elites, lineage table, rng state, bank ids →
  `G3_checkpoint.json` (atomic write: tmp + rename). `--resume` loads it.
- `night_factory`: if `{job}_run{n}.log` exists with no receipt → **resume** that run
  (pass `--resume`), never restart at run n+1 silently. Print "RESUMED from gen k".
- Rebuild the G3 09-09 receipt from `G3_evaluations.jsonl` (the archive bank scoring
  can be recomputed from the evaluations; mark it `RECONSTRUCTED_FROM_EVALUATIONS`).
- Rule: a receipt is written when a job has ANYTHING to say, and amended, not only at
  exit. `night_leaderboard_sync` already files amendments as run 99 — use that.

### 2.2 C2's cost model charges 100% turnover every day (methodology)
`C2_curriculum_transfer_run01.json` → `construction.cost_note`: "a flat 100 bps per
date, i.e. full daily turnover on both legs". Gross +30.6/+19.5/+15.0 %/yr becomes net
−221/−233/−237 %/yr. A −237%/yr net line is not a number a book can produce; it is
25 bps × 2 sides × 2 legs × 252. The ranking is unchanged (the cost is a constant) so
the VERDICT (curriculum not earned) stands, but the leaderboard headline prints the
net line. Fix: charge `Σ|Δw| × bps` on realised decile-membership turnover, print
turnover/day beside net. Same audit for every night job that says "net": grep
`cost_note` and `cost_bps` across `scripts/night_*.py`.

### 2.3 G3's two open one-liners (roadmap §11.10, still open)
- Null genomes bypass `admissible()` (`:214` vs `:318`) — the fitness is "admissible
  genome minus typical genome"; 69.3% of arms were refused, 0% of nulls. Apply
  `admissible()` to the null draws; log how many nulls it refuses.
- `banks_met >= 2` is a preference (`:409–411`: "ALL lineages (only 3 met two banks)").
  Make it an eligibility condition and re-score surviving elites on a fixed audit
  bank each generation so the count accumulates.

### 2.4 The survivor-screened 2025-26 universe (blocks the six-mandate replay)
P6 refused the replay; every 2025-26 benchmark is survivor-screened. Build a PIT
universe vintage per month (Alpaca bars exist: 1,248,370 bars, 3,060 symbols; the
tracker screen has 3,056 names; list membership by first/last bar date + dollar-vol
floor at that month, not today). One parquet, one receipt, one test.

### 2.5 R2 — the only live lane, protect it before widening it
- Pre-register the prompt + digest construction (`pre-register-trial` skill) BEFORE
  widening from 135 names to the E1 panel. Freeze the prompt hash in the receipt.
- Costs and turnover: print net beside gross. The primary is a difference of two
  identically-rebalanced books, so costs mostly cancel — measure it, don't argue it.
- Widen using `text_return_panel/news_returns_2025_26.parquet` (E1) — labels are
  `x_oc`/`x_oo` minus SPY, first open strictly after publication (PIT by design).
  The AMNESIA canary must be re-run on the widened set.

### 2.6 What "learns and improves autonomously" should mean here (keep it honest)
The loop is: queue → receipts → typed status → amendments → next queue. Two additions
make it autonomous without letting it promote itself:
- `night_schedule_plan.py` derives tomorrow's `NIGHT_QUEUE` from the leaderboard:
  CONDITIONAL rows get their declared next test; FAILED runs get a resume; closed
  lanes get nothing. It writes the plan as a receipt a human can veto.
- Promotion (PRODUCT_PROMISING → CAPITAL_CANDIDATE) stays ATTENDED. The machine
  proposes, files, and grades; it does not seal or arm a book. `learner/evidence_memory.jsonl`
  is the memory to append to.
- Do NOT add a "learned router" over selectors; there is still one independent
  selector with evidence (CLAUDE.md bottleneck section).

### 2.7 Then: fast suite green, then commit
`AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"` (verify
`python -c "import pytest_timeout"` first). Commit rule: `backend/routers/control.py` +
`backend/tests/test_control_router_authority.py` + `backend/main.py` in ONE commit
(a swept import without the router turned CI red on 09-09). Then
`python -m scripts.ci_watch --wait`. Receipts and night scripts can be a second commit.

---

## 3. THE EXE — phase A1 (do it today, after §2.1–2.3; §2.4–2.6 can be agents in parallel)

### 3.1 What exists
- **A0 done + tested:** `/api/control/*` (services, jobs, leaderboard, balances,
  runs/{pid}/log, run/{job}, night, stop/{pid}, stop-file/clear). Whitelist derived from
  `scripts.night_factory.QUEUE`; `shell=False`; kill by PID only; mutating routes 403
  unless `AEGIS_CONTROL_ENABLED=1`. 9 authority tests. **No broker importable (AST test).**
- **Local AI:** `backend/services/free_inference.py` — backend `local_gguf` talks to
  `llama-server` on `127.0.0.1:8080` (Qwen2.5-7B GGUF, ~43 tok/s, $0). `complete()`,
  `usage()`, `capability_declaration()` are the entry points. `local_review.py` is a
  caller. `llm_analyzer` routes to DeepSeek — that stays the paid path; the app's
  built-in assistant uses `local_gguf`.
- **Frontend:** Next.js, `next.config.ts` has `output: "standalone"` → it needs a Node
  runtime. `backend/main.py` does **not** mount the frontend (no `StaticFiles`).

### 3.2 Decisions Fable recommends (Murat said "improve my ideas if you need to")
1. **Serve the frontend from FastAPI, not from Node.** Switch the build to
   `output: "export"` (static) if every page is client-rendered or uses only client
   fetches to `/api/*` — check `frontend/src/app` for server components / dynamic
   routes first. Mount the `out/` dir with `StaticFiles(html=True)` at `/` in
   `backend/main.py`, guarded so Railway (which has its own frontend deploy) is
   untouched: mount only when `AEGIS_DESKTOP=1`. One process, one port, PyInstaller
   only has to bundle Python. Fallback if export is impossible: ship Node's standalone
   server as a second child process (the shell owns it), then Tauri as last resort.
2. **Shell:** `desktop/aegis_desktop.py` — pywebview window → starts uvicorn in-process
   thread on a free localhost port with `AEGIS_CONTROL_ENABLED=1`, `AEGIS_DESKTOP=1`
   set on ITS OWN environment only (never `.env`). Splash while `/api/health` is not
   yet 200 (measure cold start; the backend imports heavy scientific packages).
3. **llama-server:** the one-click launcher **starts it if 8080 is not listening and
   owns it only then**; if it is already up (it holds ~8 GB mmap and may be mid-job),
   report and do not touch. Record which case happened in
   `/api/control/services`. Model path + binary path in `backend/config.py`, not in
   the shell.
4. **Built-in AI chat page:** a small `POST /api/control/ask` → `free_inference.complete(backend="local_gguf")`
   with the session briefing + leaderboard as context. It is a READER of receipts,
   not an authority: it can explain a receipt, it cannot run, seal, or arm anything.
   That keeps the AST no-broker test and the "no LLM authority" invariant intact.
5. **One click = "Night":** `POST /api/control/night` already runs the queue in order.
   Add "Services" (backend + llama + optional Railway status read) and "Stop"
   (STOP file, then PIDs from the registry). No image-name kills, ever.
6. **PyInstaller:** `desktop/AegisDesktop.spec`, `--onedir` (not `--onefile`: cold start
   and antivirus), hidden imports for uvicorn/fastapi/pyarrow/lightgbm as they surface,
   `backend/data/` and `scripts/` as data dirs (the control router spawns
   `python -m scripts.<job>` — inside a frozen app that must become
   `sys.executable` + an entry that dispatches to the job module; add that dispatch
   and pin it with a test). Desktop shortcut via a `.lnk` created by a post-build script.
   Build with `python -m PyInstaller desktop/AegisDesktop.spec`; smoke-test the
   `dist/` exe from a directory that is NOT the repo.

### 3.3 Pages for A1 (the rest is A2/A3)
Services · Night runs (leaderboard + one-click + live log) · Fleet vs SPY (render the
standard errors; β 0.18 ± 2.21 is not a beta) · Ask Aegis (local model). Every
displayed number comes from a receipt, and an amended number shows its amendment.

---

## 4. MUST NOT REGRESS (from 09-09 §4, plus two from the crash)
1. No order path in the app; the AST test stays green.
2. Kill by PID from the router's registry, after the STOP file. Never by image name.
3. Every displayed number from a receipt; amendments shown.
4. A control beside its arm, per era. A control's LEVEL moves with the corner
   (H5: +3.27%/yr at $3m, +17.64%/yr at $10m).
5. Uncertainty travels with the estimate.
6. **A long job checkpoints; the queue resumes.** (new)
7. **"Net" means costs on realised turnover, with the turnover printed.** (new)
8. Never `.env` moves; `AEGIS_IGNORE_DOTENV=1` reproduces CI. Never `taskkill /IM`.

---

## 5. TREE STATE (uncommitted, 40 entries; artefact-free after the 09-09 .gitignore fix)
New scripts (8): `night_g3_evolve_v2`, `night_rw2_event_windows`, `night_n2_learner_v3`,
`night_p6_bars_and_regret`, `night_r2_monthly_llm`, `night_h5_prereg_read`,
`night_rw1_pooled`, `night_leaderboard_sync`. New tests (3): control authority, N2 PIT,
X9 numbers. New router + `main.py` wiring. Modified: `.gitignore`, `NEGATIVE_RESULTS.md`,
roadmap, leaderboards, telemetry jsonl. Untracked data: `night_factory_2026-09-09/`,
`text_return_panel/`, `iif1_launches/2026-09-09.json`. Handoff 09-09 untracked too.

---

## 6. SESSION ORDER FOR OPUS
1. Protocol: briefing, verified state, `brain_query` on "checkpoint resume night factory"
   and "desktop exe pywebview" (a corpse may exist). Check 8080, check 0 processes.
2. §2.1 checkpoint/resume + reconstruct G3 receipt → §2.2 cost model → §2.3 G3 one-liners.
   Fast suite. Commit 1 (router trio), commit 2 (scripts/tests/receipts). `ci_watch --wait`.
3. Agents (opus): (a) §2.4 PIT universe vintage; (b) §2.5 R2 prereg + net; (c) §2.6 plan
   job. Each writes its receipt incrementally and reports in ≤ 300 words.
4. §3 the EXE. Measure cold start. Smoke-test outside the repo. Shortcut on the desktop.
5. Re-launch the night queue FROM THE APP (that is the acceptance test of both halves):
   `G3_evolve_v2` resumes, then the rest. Watch it survive one deliberate stop/resume.
6. Handoff with a SCOREBOARD first; memory file; push; `ci_watch --wait`.
