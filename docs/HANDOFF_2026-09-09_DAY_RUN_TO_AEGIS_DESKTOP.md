# HANDOFF 2026-09-09 — the day run → AEGIS DESKTOP (the `.exe`)

**From:** the Opus day-run session (2026-09-09, 10:50–16:15 local).
**To:** the next session, whose whole job is the desktop app.
**Read order:** this file → `ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md` **§10.7**
(the spec) and **§11** (what today produced) → `CLAUDE.md` → `docs/AEGIS_STRATEGIC_INVARIANTS.md`.

---

## 0. RESULTS SCOREBOARD (the rule: this comes before code)

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE.** Four lanes closed, one opened as CONDITIONAL. No book changed, no seal, no order. |
| best historical net strategy vs market | still none that survives its own control above the tradability floor |
| best forward paper strategy | none — the six books are **−4.43%** in aggregate over their first week |
| independent selector count | unchanged |
| new actionable finding | **R2**: a local 7B model reading an anonymised monthly news digest calls next month's market-adjusted direction at **+16.19%/yr over its own shuffled-digest control, t 3.92 on 112 monthly blocks**. CONDITIONAL, gross of costs, 135 names. |
| LLM spend | **$0.0000.** 4,238 calls today, all `local_gguf`, verified in `llm_calls.jsonl`. DeepSeek balance $9.11 → **$9.07** (the Railway loops, not this session). |
| tests | fast suite **7,845 passed / 0 failed** |

**Closed today:** TRIAL-H5 (REJECTED), the earnings-reaction lane in *every*
form, the data-net's event features, and the random-window rule's single-draw
reading.

---

## 1. THE FLEET, AS OF 12:10 LOCAL — read this before touching the app

Live venue state (`python -m scripts.fleet --check-all` from the terminal repo,
read-only), and the paired six-session regret from `P6_bars_and_regret_run04.json`:

| book | equity | positions | vs $100k | book % | SPY % | regret | beta (s.e.) |
|---|---|---|---|---|---|---|---|
| hack1 | 98,859 | 0 | −1.14% | −1.14 | −0.12 | −1.02 pp | 0.023 (±0.062) |
| hack2 | 98,821 | 0 | −1.18% | −1.18 | −0.12 | −1.06 pp | 0.075 (±0.117) |
| **hack3** | **89,976** | 8 | **−10.02%** | −9.50 | −0.12 | **−9.38 pp** | 0.413 (±0.762) |
| hack4 | 99,476 | 0 | −0.52% | −0.52 | −0.12 | −0.41 pp | 0.203 (±0.899) |
| hack5 | 95,735 | 1 | −4.27% | −3.54 | −0.12 | −3.43 pp | 0.182 (±2.205) |
| **hack6** | **90,530** | 12 | **−9.47%** | −8.53 | −0.12 | −8.41 pp | 0.244 (±0.253) |

**Beta is NOT estimable on four paired sessions** — every standard error is
comparable to or larger than its estimate. Do not let the app render these as
measurements. What IS supported: SPY was flat, so the losses did not come from
market direction. `state: LEGACY` on all six just means "has traded"; it is not
an alarm.

---

## 2. WHAT EXISTS FOR THE APP TO DRIVE (all built and tested today)

### 2.1 The control router — phase A0 is DONE

`backend/routers/control.py`, wired in `backend/main.py`, pinned by
`backend/tests/test_control_router_authority.py` (9 tests, green).

```
GET  /api/control/services        # backend pid, llama-server health, STOP file, every run + pid + log mtime
GET  /api/control/jobs            # the whitelist, DERIVED from scripts.night_factory.QUEUE
GET  /api/control/leaderboard     # LEADERBOARD.md + the receipt list
GET  /api/control/balances        # the provider's own DeepSeek balance line
GET  /api/control/runs/{pid}/log  # tail a running job
POST /api/control/run/{job}       # spawn ONE whitelisted job, register its pid
POST /api/control/night           # one click: the whole queue in order
POST /api/control/stop/{pid}      # STOP file first, then signal that ONE registered pid
POST /api/control/stop-file/clear
```

**Three properties are enforced, not intended — do not weaken them:**

1. **No broker is importable.** An AST test fails if `alpaca`/`broker`/`order`
   ever appears in this module's imports. The app runs services and paper books;
   it never places a real order.
2. **A whitelist, never a command string.** `shell=False`, argv is a list, and
   the job id must be in the queue's derived whitelist. Adding a job to `QUEUE`
   adds a button — you should not need to touch the router.
3. **Kill by PID from the router's own registry, after the STOP file.** Never by
   image name. This is the 2026-09-06 lesson (`taskkill /F /IM python.exe` killed
   two other agents' jobs, a test suite and 1,676 billed extractions).

**Every mutating route returns 403 unless `AEGIS_CONTROL_ENABLED=1`.** That is
why the router is safe on the Railway website deployment. The desktop shell sets
the flag when it starts the backend on localhost; nothing else should.

### 2.2 What the pages can read, today, with no new backend work

| page | source | state |
|---|---|---|
| **Services** | `GET /api/control/services` | ready |
| **Night runs** | `GET /api/control/leaderboard` + `POST /api/control/night` + `runs/{pid}/log` | ready |
| **Fleet vs SPY** | `P6_bars_and_regret_run04.json` (`regret_vs_spy_over_the_same_sessions`) | ready, **render the standard errors** |
| **Networks** | per-head receipts: `N2_learner_v3_run01.json`, `N1_train_reaction_learner_run02.json`, `G3_evolve_run01.json` (`best_curve`) | ready — G3's `best_curve` is a real learning curve |
| **News** | `r7_news_representation/panel.parquet`, `C1_counterfactual_news.jsonl` | ready |
| **Picks** | the 3,056-name tracker screen + `/api/journal/thesis` | ready |
| **Regret** | `decision_log` in the terminal repo | needs a read path |

### 2.3 The night queue the app drives

`python -m scripts.night_factory --list` — twelve jobs. Seven were added today:
`RW1_random_windows`, `RW2_event_windows`, `G3_evolve_v2`, `N2_learner_v3`,
`P6_bars_and_regret`, plus `scripts/night_r2_monthly_llm.py`,
`scripts/night_h5_prereg_read.py`, `scripts/night_rw1_pooled.py` and
`scripts/night_leaderboard_sync.py`.

`night_leaderboard_sync` matters for the app: it puts receipts on the board even
when a job was run directly, and `--rebuild` regenerates the board from the
receipts. **It also files verdict AMENDMENTS as run 99**, so a retracted stamp
never outlives its correction on a page a human reads. Three amendments exist:
D3, R2 and G3.

---

## 3. THE DESKTOP LANE — where to start

§10.7 phases. A0 is done; **A1 is the next session's job.**

- **A1 — the shell.** `pywebview` wrapping the existing Next.js build served by
  `backend.main:app` on localhost, packaged with PyInstaller into
  `AegisDesktop.exe` plus a desktop shortcut. The website IS the app; do not
  start a new web stack. If the Next.js bundle fights PyInstaller, the fallback
  is a Tauri shell over the same backend.
- **A2** — Networks / News / Regret pages.
- **A3** — the forward-news view (R2's forecasts, graded each morning).

**Practical notes for A1:**

- The shell must set `AEGIS_CONTROL_ENABLED=1` for its own backend process and
  nothing else. Do not put it in `.env`.
- **Never move or edit `.env`** — use `AEGIS_IGNORE_DOTENV=1` to reproduce CI.
- The backend imports heavy scientific packages; a PyInstaller build will be
  large and slow to start. Measure cold start before optimising it.
- `llama-server` is a **separate process** the app should report on, not own.
  It has been up since 2026-09-07 18:32 and holds ~8 GB of mmap; restarting it
  mid-job destroys any in-flight inference and splits a receipt across two model
  instances.
- The box runs tight on memory (~2.5 GB free of 31.4 GB). Idle background
  watchers get reaped. **A killed watcher looks exactly like an unfinished job** —
  the app should read a run's log mtime and pid liveness, never the absence of a
  notification.

---

## 4. WHAT MUST NOT REGRESS

1. **No order path in the app.** Ever. Paper books only, and the AST test that
   proves it stays green.
2. **Kill by PID, never by image name.**
3. **Every displayed number comes from a receipt**, and a number that has been
   amended shows the amendment. `test_x9_day_run_numbers.py` pins §11's numbers
   to their receipts; keep that pattern for anything the UI asserts.
4. **A control is displayed beside its arm, per era.** The single biggest lesson
   of 2026-09-09 (§5 below) is that a control's own LEVEL moves with the
   construction corner. A UI that shows an arm's return without its control will
   re-teach the exact error the receipts spent the day unlearning.
5. **Uncertainty travels with the estimate.** The fleet betas are the live case:
   0.18 ± 2.21 is not a beta.

---

## 5. THE FIVE THINGS LEARNED TODAY (they belong in the app's copy, not just the docs)

1. **A control that shares the construction can WIN.** RW2: the reaction
   long-short's dateless placebo beats it in 2016-2024 above the $10m floor
   (+8.02 vs −3.67 %/yr, arm wins 24% of windows). N2: eight *dateless* columns
   add +2.780%/yr to the data-net against the real earnings print's +2.267%/yr.
2. **A control's level moves with the corner.** TRIAL-H5: the placebo-trained
   twin earns +3.27%/yr at the $3m floor and **+17.64%/yr** at $10m. The
   original "+44.5%/yr, control t −0.45" was a $3m-floor, zero-borrow number.
3. **A budget the benchmark cannot meet is a broken gate.** A flat 0.35 drawdown
   refusal killed 188 of 207 genomes because the market itself drew −47.2% over
   1999-2015. Derive the limit from the window.
4. **One draw cannot adjudicate a rule its own noise is the size of.** RW1's
   draw-to-draw dispersion is 0.099 mean / 0.150 max against a +0.15 threshold.
   Pooled over three draws and 720 windows: **0 of 12 cells pass.**
5. **A pre-hoc power estimate is a design quantity, not the truth.** R2's MDE was
   1.61× too conservative and stamped a t 3.9 result "underpowered".

---

## 6. STATE OF THE TREE — nothing is committed

`git status` is clean of artefacts and holds exactly the day's work:

- **new scripts (8):** `night_g3_evolve_v2`, `night_rw2_event_windows`,
  `night_n2_learner_v3`, `night_p6_bars_and_regret`, `night_r2_monthly_llm`,
  `night_h5_prereg_read`, `night_rw1_pooled`, `night_leaderboard_sync`
- **new tests (3):** `test_control_router_authority`, `test_n2_event_features_are_pit`,
  `test_x9_day_run_numbers`
- **new router:** `backend/routers/control.py` (+ the `main.py` wiring)
- **modified:** `scripts/night_factory{,_jobs}.py`, `.gitignore`,
  `NEGATIVE_RESULTS.md`, the roadmap, `LEADERBOARD.md`
- **receipts:** RW1 runs 2-3, `RW1_pooled`, RW2, G3, N2, P6 runs 1-4, R2 (2022
  and 2015-2024), `N1H5_prereg_read`, and three `*_verdict_amendment.json`

**The commit rule from the peer session:** `backend/routers/control.py`,
`backend/tests/test_control_router_authority.py` and `backend/main.py` go in
**one commit together** — a previous commit swept the import in without the
router and turned CI red. Then `python -m scripts.ci_watch --wait`.

`.gitignore` was corrected today: the old rule named `G1_evaluations.jsonl`
specifically, so **G3's evaluation log and all eight `*_smoke.json` receipts were
not ignored**. Now generalised to `*_evaluations.jsonl` and `*_smoke.json`.
A rule that names one job is a rule that will be wrong at the next job.

---

## 7. ATTENDED — Murat only

Unchanged and still his: hack2's evidence-gate threshold; hack4 v3 if a
sector-rotation book is wanted; the desktop packaging decision when A1 lands.
TRIAL-H5 is closed and needs nothing. No successor was registered.
