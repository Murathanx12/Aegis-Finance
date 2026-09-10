# HANDOFF 2026-09-10 (session close) — the app, the replay, and eleven defects

**From:** the Opus builder session of 2026-09-10.
**Read order:** this file → `HANDOFF_2026-09-10_THE_REPLAY_AND_THE_EXE.md` (the
research half, in detail) → `ROADMAP_2026-09-10_MODEL_NEWS_AND_THE_EVENT_NET.md`
(the model, the news loop, the event net, the memory-chunking plan) → `CLAUDE.md`.

---

## 0. SCOREBOARD

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE.** No strategy moved. |
| best historical net strategy vs market | none surviving its own control above the tradability floor |
| best forward paper strategy | none — six books −4.43% aggregate in week one vs SPY −0.12% |
| only live lane | **R2** (local 7B on an anonymised monthly digest), +16.19%/yr over its shuffled-digest control, t 3.92, 112 blocks. Now **pre-registered**; net is CANNOT DETERMINE, difference bounded **[+10.19, +22.19]%/yr** |
| independent selectors with evidence | **one** — unchanged; still the reason no router is permitted |
| new actionable finding | **the night search was replaying itself**: 541/541 genome overlap between consecutive G3 runs |
| LLM spend | **$0.00** — every job local |
| tests | fast suite **7,966 passed / 20 skipped / 0 failed** (7,845 at session start) |
| CI | **green on `96f1204`**, the final commit. It went RED once, on `e50f46d`, from a test I wrote that reloaded `backend.config` — see defect #12 |
| what shipped | **Aegis Desktop**: one-click app, local-only, model server the OS cannot let outlive it |

---

## 1. WHAT WAS BUILT

### The night factory can accumulate
- `scripts/night_checkpoint.py` — `Checkpoint` (atomic, per generation; a resume
  under a changed config is REFUSED with the drifted key named) and
  `SearchState` (elites carried across nights; every bank seed drawn from
  outside the union of every seed any night selected on, rejection count in the
  receipt). **Proven:** killed by PID at generation 3, resumed, reproduced the
  uninterrupted trajectory bit-for-bit.
- `night_factory.resolve_run` resumes a crashed run under its own number.
- G3 rebuilt: representative by best-MEASURED member, `banks_met` a hard gate, a
  per-generation confirmation pass, nulls through the drawdown refusal.

### Aegis Desktop
- `desktop/aegis_desktop.py` (shell), `AegisDesktop.spec` (onedir, 1.1 GB),
  `build_icon.py`, `make_shortcut.py`. Shortcut at
  `C:\Users\mrthn\OneDrive\Desktop\Aegis.lnk`.
- FastAPI serves the Next.js static export — **one process, no Node**.
- `backend/services/llama_server.py` — model server owned by PID, never by
  image name, with a Windows **job object** so the OS kills it when the app
  dies however it dies.
- `backend/services/quiet_subprocess.py` — no console windows.
- `GET /api/control/fleet` refuses an estimate without its uncertainty.
- `POST /api/control/ask` — local model, $0, a READER of receipts.
- Paper data from the deployment is **opt-in**: one GET per click, cached.

### Research
- N3 (frozen encoder + learned head) — **FAILED_VARIANT**, details in the other
  handoff. Registered as a night job anyway: the panel grows and the head refits
  in minutes, so it is the cheapest standing check that text ever starts paying.
- P7 PIT universe (partial: liquidity fixed, survival not).
- `scripts/night_queue_plan.py` — derives tomorrow's queue, refuses to invent.
- C2 cost model corrected; R2 pre-registered and widened (PENDING_MODEL).

---

## 2. TWELVE DEFECTS, AND NOT ONE WAS CAUGHT BY A TEST THAT WAS ALREADY FAILING

| # | defect | how it was found |
|---|---|---|
| 1 | the night search **replayed itself** — 541/541 overlap, zero discovery | reading the evaluations log against the receipt |
| 2 | the archive discarded its **best-measured** genomes (248/251 lineages represented by a one-bank draw) | same log |
| 3 | null genomes **bypassed** the drawdown gate (69.3% of arms refused, 0% of nulls) | reading the code against its own comment |
| 4 | `admissible` the list **shadowed** `admissible` the function | reading |
| 5 | `dollar_vol` in the E1 panel is a **look-ahead** (entry session's own close × volume) | N3, as a by-product |
| 6 | **C2's universe** screens on that same column | grepping for other readers of #5 |
| 7 | job receipts **silently overwrote** each other (~15.6 ms clock, 200 stamps identical) | taking one "flaky" failure seriously |
| 8 | the packaged app read an **empty database inside its own bundle** | first packaged run's log |
| 9 | the vendored schema was **dropped** from the bundle | smoke test, failed loudly with the path |
| 10 | the **ownership note** was written inside the bundle → the model server outlived the app | **Murat closed the app**; diagnosed from the process table |
| 11 | `AEGIS_DATA_DIR` one level too deep → `optimus/optimus/` | a stray untracked directory at session close |
| 12 | **mine, introduced today**: a test that reloaded `backend.config` rebound `LLM_PRICE_PER_MTOK`, breaking a later test's IDENTITY assertion | CI, on the commit that claimed the session was closed |

**The pattern.** Five of these (#8, #9, #10, #11, and the frozen `-m` spawn) are
one defect wearing different clothes: **a path that resolves somewhere
believable and wrong inside the frozen build**. I fixed the first and did not
generalise, so Murat found the third. It is now a category to check, and the app
writes `backend/data/optimus/aegis_desktop.log` so the next one is a ten-second
read rather than a forensic dig.

**Defect #12 is the one to read twice.** It is the only one I introduced, and I
had flagged the risk to myself while writing it -- "reloading config mid-suite
could corrupt state for other tests" -- then took the short path anyway. It is
order-dependent, so it passed locally and failed on CI. That is the same
signature as #7 (the receipt overwrite): a failure visible only under one
interleaving, and easy to re-run and call flaky. Fixed by checking the invariant
in a subprocess, which touches no in-process module state.

**Two more worth carrying.** #10 also needed a *second* fix: with ownership
repaired, a hard kill still leaked, because every shutdown hook runs user code
and `TerminateProcess` runs none. And my first kill test of the job-object fix
said **FAIL** and was wrong — it matched the parent by command line and found
the wrong PID. Believing it would have deleted a working guarantee.

---

## 3. WHAT MURAT REPORTED, AND WHAT WAS DONE

| report | cause | state |
|---|---|---|
| "hard to close the llama server" | `llama-stop.cmd` uses `taskkill /IM` and needs a terminal | Stop button + auto-close; kernel-enforced |
| "API fetch error … shouldn't use railway" | `NEXT_PUBLIC_API_URL` inlined at build time; `/desktop` used a different client, so the half I tested was the half that worked | zero Railway in the bundle, verified |
| "random cmds popup and close" | `console=False` + console subprocesses; three on a 3-second poll | all 11 sites suppressed |
| "guide … dont show again" | — | built, `aegis.guide.dismissed.v1`, "? Guide" reopens |
| "the exe didnt open timed out" | `load_url` fired into a window whose GUI loop did not exist; splash never swapped | `webview.start(when_ready)`; **verified in the packaged build** |
| "pull paper data from railway, don't add expense" | — | opt-in, one GET per click, cached |
| "qwen 3.8 27b uncensored" | it is **Qwen3-30B-A3B** | downloaded and measured |
| "semi encoder/decoder NN from news" | two prior corpses constrain it | built as N3; **it does not fire** |
| "chunk the memory" | `evidence_memory.jsonl` 62 MB | plan in roadmap §3b |

**Verified end to end, from Murat's own use** (`aegis_desktop.log`):
```
17:23:44  backend on 63326; lifetime_bound: true
17:23:46  health_ok=True after 1.03s
17:23:46  loaded http://127.0.0.1:63326/desktop
17:33:11  shutdown(window-closing): stopped pid 2436, vram 316 MiB
```

---

## 4. WHAT IS LEFT TO DO

**Blocking-ish, has a clock on it**
1. **Chunk `evidence_memory.jsonl`.** 62.14 MB; GitHub warns at 50, **rejects at
   100**, and it grows nightly. Plan and options in roadmap §3b. Recommendation:
   monthly rotation, live chunk untracked. **Compaction is refused** — a log
   that summarises itself is not an evidence log. Split by each row's OWN stamp,
   never by file mtime.

**Research**
2. **Re-measure Qwen3-30B-A3B on an idle machine.** Today's numbers (1,854 MiB
   VRAM, 19.8 tok/s) were taken while PyInstaller saturated 20 cores, so they
   are a lower bound. **Prompt eval came in at 5.6 tok/s under that load — if it
   stays there when idle it cannot read a digest at all**, which decides the
   whole question. Sweep `--n-cpu-moe` down from 48. A swap is a **new arm**;
   R2's prereg freezes the model sha256 for that reason. Test the plain Instruct
   build's refusal rate before assuming "uncensored" is wanted.
3. **Run the night queue FROM THE APP** and watch G3 survive a deliberate
   stop/resume at full scale. Only done at smoke scale.
4. **Give every night receipt a `next_test` field.** The queue planner is built
   and starved — tonight's derived queue is one row because only three amendment
   files declare what comes next.
5. **Re-run C2 on `pit_dv_21`** to settle whether the universe look-ahead moved
   its levels (the ranking is argued to survive; that argument is written down
   in `C2_universe_lookahead_note.json` so it can be disagreed with).
6. **R2 widened panel B** is `PENDING_MODEL` — one command once llama-server is
   up. Re-run the AMNESIA canary on the widened set; a widened result without it
   is not a result.
7. Audit anything else that read `dollar_vol` off the E1 panel.

**Product**
8. **Open the app and use it properly.** The window is now verified to load, but
   only the four `/desktop` pages have been exercised; the rest of the app now
   talks to the local backend for the first time and some endpoints will want
   network data on first call.
9. The `/dev` page links to a Vercel-hosted brain (an `<a href>`, not a fetch) —
   harmless, but it is the last remote reference in the desktop build.
10. `dist/` is 1.1 GB and rebuilt often; it is gitignored. A rebuild while the
    app is open now REFUSES with a readable message.

**Do not**
- Do not add a learned router. One independent selector with evidence.
- Do not quote N3 as evidence against R2 — different horizon, different reader.
- Do not quote any absolute C2 number without its look-ahead note.

---

## 5. MUST NOT REGRESS (cumulative)

1. No order path in the app; the AST test stays green.
2. Kill by PID from the registry, after the STOP file. Never by image name.
3. Every displayed number from a receipt; amendments shown.
4. A control beside its arm, per era; a control's LEVEL moves with the corner.
5. Uncertainty travels with the estimate.
6. A long job checkpoints; the queue resumes.
7. "Net" means costs on realised turnover, with turnover printed.
8. Never move `.env`; never `taskkill /IM`.
9. A model swap opens a **new arm**; it never updates an existing lane's number.
10. The representation is frozen or the text experiment is unfalsifiable.
11. Three controls or no claim for a text lane: TF-IDF, shuffled, no-text.
12. A search that does not advance its seed across nights is replaying itself.
13. `listening` is not `ready`. Probe the health route; carry both states.
14. **A path that resolves differently in the frozen build is a defect family,
    not a coincidence.** Check the database, the data dir, every ownership or
    state file, and anything opened BY PATH rather than imported.
15. **A grep-shaped guard that cannot tell an explanation from an instance is
    broken.** Read the AST and skip docstrings.
16. **A promise kept only on the tidy path is not the promise.** If it must hold
    through a crash, the OS has to enforce it.
