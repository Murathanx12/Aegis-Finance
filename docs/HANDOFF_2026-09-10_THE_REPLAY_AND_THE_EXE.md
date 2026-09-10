# HANDOFF 2026-09-10 — the replay, the exe, and the model that fits

**From:** the Opus builder session of 2026-09-10.
**Read order:** this file → `docs/ROADMAP_2026-09-10_MODEL_NEWS_AND_THE_EVENT_NET.md`
→ `CLAUDE.md` → `docs/AEGIS_STRATEGIC_INVARIANTS.md`.

---

## 0. RESULTS SCOREBOARD

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE.** No strategy moved. |
| best historical net strategy vs market | none that survives its own control above the tradability floor |
| best forward paper strategy | none — the six books were −4.43% aggregate in their first week against SPY −0.12% |
| only live lane | **R2** (local 7B on an anonymised monthly digest): +16.19%/yr over its shuffled-digest control, t 3.92, 112 blocks. **Now pre-registered.** Its NET is CANNOT DETERMINE; the difference is bounded **[+10.19, +22.19]%/yr** |
| independent selectors with evidence | **one** — unchanged, and the reason no router is permitted yet |
| new actionable finding | **the night search was replaying itself.** 541/541 genome overlap between two consecutive G3 runs |
| LLM spend | **$0.00** (every job local) |
| tests | fast suite **7,924 passed / 20 skipped / 0 failed** (7,845 on 09-09). CI green on `452214f` |

---

## 1. THE FINDING — the night factory was not accumulating, and the crash hid it

The 09-09 `G3_evolve_v2` job died with the PC (`exit 1073807364` =
`DBG_TERMINATE_PROCESS`) after 3.1 hours at generation 340, leaving only
night_factory's stub receipt. The handoff called it three hours of lost work.

The evaluations log says otherwise. Both the 09-08 and the 09-09 runs used
declared seed `20260909` and `bank_seed = seed + 1000 * gen`, so both drew the
same window banks, initialised the same population from the same rng, and walked
the same tree. **Of the 541 distinct genomes the crashed run evaluated, 541 were
already in the earlier run's log** — overlap 1.000, discovery zero — and it died
93 generations *behind* where the programme already stood (343 against 436).

The crash cost nothing. A checkpoint alone would have made a pointless replay
resumable. Receipt: `night_factory_2026-09-09/G3_evolve_v2_run99.json`
(`RECONSTRUCTED_FROM_EVALUATIONS`).

### Three more defects in that file, each found by reading its own log

1. **The archive threw away its best-measured genomes.** `finalist_basis` in the
   09-08 receipt reads *"ALL lineages (only 3 met two banks)"*. The log shows
   **161 of 595 genomes met two or more.** The lineage representative was chosen
   by median fitness, and a one-bank median is a single draw sitting at the noisy
   top of that ordering — so **248 of 251 lineages** were represented by a
   one-bank genome and the `banks_met >= 2` clause could never bind. That is
   selection on the outcome, in the file whose own comment says it is avoiding
   exactly that. Fixed: the representative is the best-MEASURED member
   (`banks_met`, then fitness), the gate is a HARD eligibility condition, and a
   per-generation confirmation pass gives the leaders a second bank so the gate
   can go green. Smoke run: 11/27 genomes eligible, 3/3 lineages qualifying.
2. **Null genomes bypassed the drawdown refusal** — 69.3% of arms refused, 0% of
   nulls, so the fitness was "an admissible genome minus a *typical* genome", a
   bar drawn from a population the arm was not allowed to join. Nulls now pass
   through `admissible()`, and a window whose nulls all fail is **dropped**, not
   graded against zero (which was D1's error).
3. `admissible` the list **shadowed** `admissible` the function in the same
   scope, and the archive bank was the constant `seed ^ 0xA5C1` — the same
   "unseen" bank every night, never checked against the selection seeds.

Also: G3 hard-coded `RUN_DATE` while `night_factory` honours `NIGHT_RUN_DATE`,
so the 09-09 night wrote its receipt to one directory and its evaluations to
another, and two nights' rows ended up in one file separable only by a timestamp
gap.

### What now exists

`scripts/night_checkpoint.py` — `Checkpoint` (atomic tmp+replace, per
generation; a resume whose config moved is REFUSED with the drifted key named)
and `SearchState` (elites carried across nights; every bank seed drawn from
outside the union of every seed any night selected on, with the rejection count
in the receipt). `night_factory.resolve_run` resumes a crashed run under its own
number instead of bumping to n+1 and orphaning its checkpoint.

**Proven, not asserted:** a smoke run was killed by PID at generation 3 and
resumed; it reproduced the uninterrupted run's trajectory bit-for-bit (gen 5
−3.424, gen 10 +2.199) and finished against the *remaining* time box.

---

## 2. AEGIS DESKTOP — built, and the model server is stoppable

- `desktop/aegis_desktop.py`: pywebview window, uvicorn in-process on a port the
  OS hands out, splash until `/api/health` answers. **Cold start 0.75 s to
  health, 4.87 s total.** `AEGIS_DESKTOP`/`AEGIS_CONTROL_ENABLED` are set on the
  process's own environment — never `.env`.
- FastAPI serves the frontend: `AEGIS_DESKTOP_BUILD=1` switches Next to
  `output: "export"`, `mount_desktop_frontend` mounts `out/` at `/` when
  `AEGIS_DESKTOP=1`. **One process, no Node.** Verified: `/api/health`,
  `/api/control/{services,llama,fleet}` and all four of
  `/desktop{,/night,/fleet,/ask}` return 200.
- `backend/services/llama_server.py`: the model server owned **by PID**.
  `~/llama/llama-stop.cmd` still ends in `taskkill /IM llama-server.exe /F` —
  kill by image name, banned since 2026-09-06 — which is exactly why it was hard
  to close. The new path resolves the owning PID from the socket table and
  **refuses** rather than falling back to a name match. Measured: start → ready →
  stop, VRAM 5,861 → 1,091 MiB. Closing the app stops a server Aegis started and
  **leaves a foreign one alone** (the UI asks, with the detail, before it will).
- `GET /api/control/fleet` will not return an estimate without its uncertainty:
  every lane carries `se_daily_excess_pct`, `n_days` and an `estimable` flag that
  is False below a 20-session floor with a reason string. Its benchmark is a
  control **lane**, not SPY, and the payload says so.
- `POST /api/control/ask` — the built-in assistant on the local model, $0, a
  READER of receipts. No broker importable; the AST test still holds.
- `desktop/AegisDesktop.spec` — `--onedir` (onefile unpacks on every launch and
  is what antivirus flags hardest), icon from `frontend/public/logo.png` on a
  dark tile, and the spec **refuses to package without `frontend/out`** because
  that build's only symptom is an empty window.

**The trap the frozen build would have hit:** the control router spawns
`[sys.executable, "-m", "scripts.night_factory", ...]`. Inside PyInstaller
`sys.executable` is `AegisDesktop.exe`, which has no `-m` — every job launched
from the packaged app would have died on an argparse error, leaving an empty log
and a "job started" that never ran. `control.child_argv` rewrites it to
`--run-module`, which the shell dispatches **before argparse**, and three tests
pin it.

---

## 3. THE MODEL — Qwen3-30B-A3B, measured on this laptop

"qwen 3.8 27b uncensored-fps" is **Qwen3-30B-A3B**: 30B total, ~3.3B active per
token (MoE). Q4_K_M is **17.28 GB** and does not fit 8 GB of VRAM.

| | Qwen2.5-7B Q4_K_M (current) | Qwen3-30B-A3B Q4_K_M |
|---|---|---|
| file | 4.36 GB | 17.28 GB |
| VRAM | 5,861 MiB (all on GPU) | **1,854 MiB** (`--n-cpu-moe 48`, experts in RAM) |
| load | 9.6 s | 5.3 s |
| generation | **41.4 tok/s** | 19.8 tok/s (8.75 end-to-end on a short chat) |

Both ran simultaneously in 6,866 of 8,151 MiB.

**Caveats, and they matter.** These were measured while PyInstaller saturated
all 20 cores, and the MoE model is CPU-bound, so its numbers are a **lower
bound**. Prompt eval came in at 5.6 tok/s under that contention — if that holds
when the machine is idle it rules the model out for long digests, so re-measure
idle and try fewer MoE layers on the CPU before deciding anything. On one
qualitative prompt Qwen3's answer was tighter and better reasoned; one prompt is
not evidence.

**Two rules this session adds:**

- **A model swap is a NEW ARM, not an upgrade.** R2's pre-registration freezes
  the model file's sha256 for precisely this reason. Running R2 on Qwen3 opens
  R2-Qwen3 beside R2; it does not update R2's number.
- **"Uncensored" is probably wrong for this job.** Abliteration costs benchmark
  performance to remove refusals we do not hit. Measure the refusal rate of the
  plain Instruct build on R2's own prompts first; take the abliterated one only
  if it actually refuses.

---

## 4. FROM THE PARALLEL WORKERS

- **C2's −237%/yr net was a cost artefact** — a flat 100 bps per date, i.e. full
  daily turnover on both legs. On realised turnover: **−134.1 / −149.2 / −150.7**
  with turnover 0.81–0.86 per rebalance. The verdict (curriculum not earned) is
  unchanged because the cost was a constant, and the honest reading is harsher
  than the curriculum question: **a daily-rebalanced decile long-short cannot pay
  25 bps a side at that turnover, whatever it is trading on.** An audit table of
  every `cost_bps` site in `scripts/night_*.py` is in the amendment.
- **R2 is pre-registered** before it is widened. Prompt, system prompt, digest
  spec and model sha256 all frozen; `verify_frozen` refuses on any edit. Panel B
  built (18,501 cells, 19 blocks, 912 names/month, MDE 14.05%/yr) and filed
  `PENDING_MODEL`. Every answer is now appended as it arrives, so a re-grade at a
  different cost is free forever.
- **P7 gives 2025-26 a point-in-time universe** — and says out loud that it is a
  PARTIAL fix. The liquidity look-ahead is repaired (ARKO: $4.16m in 2025-03 IN,
  $1.74m in 2026-01 OUT, $5.48m in 2026-09 IN). The survival look-ahead is not:
  **3 of 3,056 symbols ever stop trading**, because the bars were pulled from a
  2026-09-01 screen and the source is itself survivor-screened.
- **`scripts/night_queue_plan.py`** derives tomorrow's queue from the receipts
  and refuses to invent a successor. Tonight: `NIGHT_QUEUE="G3_evolve_v2:300"`,
  one row, 19 refusals. **The finding is that no job receipt carries a
  `next_test` field** — only the amendments do, which is why the plan is one row.
  Give receipts a declared next test and the planner gets useful.

---

## 4b. N3 — THE EVENT NET IS A NEGATIVE RESULT, AND A CLEAN ONE

`scripts/night_n3_frozen_embedding_head.py`, receipt
`night_factory_2026-09-10/N3_frozen_embedding_head_run01.json` (+ `_daily.csv`).

The design that survives both prior corpses — a **frozen**
`BAAI/bge-small-en-v1.5` (33.4M params, 384-dim, revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, CLS + L2 norm, 192 tokens) with only
a ridge head learned on the return label — against all three controls on
identical splits. **162,548 distinct texts embedded in 130 s (1,253 texts/s) on
the 5060, $0.00**; 130,090 `(symbol, entry_date)` cells over 3,019 symbols,
2025-02-05..2026-09-08; expanding walk-forward by month, 5-session embargo, 15
folds. Mean daily cross-sectional Spearman IC ×100, t over date blocks:

| era | blocks | EMBED | TFIDF | SHUFFLE | NOTEXT | EMBED−TFIDF | EMBED−SHUFFLE |
|---|---|---|---|---|---|---|---|
| ALL | 277 | −0.35 (t −0.74) | −0.07 (t −0.14) | +0.41 | +0.39 | −0.28 t −0.56 p 0.57 | −0.76 t −1.25 p 0.21 |
| 2025Q3 | 42 | +0.17 | +0.79 | +1.19 | −1.06 | −0.62 | −1.02 |
| 2025Q4 | 64 | +0.70 | −0.35 | −0.70 | +1.13 | +1.05 | +1.39 |
| 2026Q1 | 61 | −0.75 | +0.39 | +0.49 | +1.00 | −1.14 | −1.25 |
| 2026Q2 | 62 | −1.43 | +1.00 | +1.57 | −0.74 | −2.43 t −2.25 | −3.00 t −2.11 |
| 2026Q3 | 48 | −0.28 | −2.39 | −0.41 | +1.36 | +2.11 | +0.14 |

Holm-adjusted `family_max_p = 1.0`. **No arm is distinguishable from zero.**
EMBED beats TF-IDF in 2 of 5 eras and loses the pooled comparison, and — the
clause that settles it — **does not beat the shuffled-text control**, so
whatever any arm earns is the panel's calendar and universe, not the text. On
top of that, every arm turns over ~1.8/day, so 25 bps on realised turnover costs
**~110%/yr**: the day-hold decile long-short on this panel is not a book in any
arm. **Verdict: FAILED_VARIANT.**

**Two by-products worth more than the arm.**

1. **The E1 panel's `dollar_vol` column is a look-ahead** — it is the ENTRY
   session's own close × volume, i.e. information from the session being traded
   (written at `night_e1_news_return_panel.py:192`). N3 ignores it and
   recomputes `pit_dv_21` from bars, with a test pinning that.

   **It has one other reader, and it is C2.** `night_c2_curriculum_transfer.py:138`
   screens the panel with `dollar_vol >= 3,000,000`, so C2's UNIVERSE is
   look-ahead-contaminated. Filed as
   `night_factory_2026-09-09/C2_universe_lookahead_note.json`. The screen is
   applied once, before the split, so all three arms trade the identical
   universe and a term common to every arm does not move a difference — the
   09-09 RANKING (BASELINE > CONTROL > TRANSFER) stands on the same argument
   that let the flat-cost verdict stand. **The LEVELS are contaminated and must
   not be quoted alone.** Settling it means re-running C2 on `pit_dv_21`; that
   has NOT been done.
2. PIT re-verified on all 339,657 rows: **0 violations**, minimum lag under two
   seconds, median 17.6 hours from publication to the entry open.

**What this closes and what it does not.** It closes the daily-horizon,
next-open route for both representations on this panel. It does **not** touch
R2, which is a different horizon (a monthly digest, not a per-headline next-open
label) and a different reader (a 7B doing inference, not a linear head on a
fixed vector). Do not quote N3 as evidence against R2; they answer different
questions. What N3 does say is that the cheap version of "a net that learns from
events" has now been tried in its most defensible form and did not fire.

**What this closes and what it does not.** It closes the daily-horizon,
next-open route for both representations on this panel. It does **not** touch
R2, which is a different horizon (monthly digest, not per-headline next-open)
and a different reader (a 7B doing inference, not a linear head on a fixed
vector). Do not quote N3 as evidence against R2; they answer different
questions. What N3 does say is that the cheap version of "a net that learns from
events" has now been tried in its most defensible form and did not fire.

## 4c. TWO LESSONS FROM PACKAGING, BOTH CHEAP TO REPEAT

- **The first spec produced a 27 GB dist directory.** `collect_data_files` on
  `backend`/`scripts`/`learner` swept every parquet — the 1.25M-row bar table,
  the 339,657-row news panel, `train_table_long` — into the bundle, and
  `collect_submodules("scripts")` imported every night job at analysis time and
  dragged in torch with CUDA. The corrected build is **1.1 GB**. The app was
  never portable (it reads `backend/data/optimus/**` at runtime), so a copy
  inside the .exe is duplication that goes stale the moment a night job writes.
  Night jobs now run under a real interpreter via `control.job_python()`.
- **Then the opposite error, caught by the smoke test.** Dropping the blanket
  sweep also dropped `backend/vendor/aat/**` — a schema mirror the code opens by
  PATH, not by import. The .exe started and died with
  `SchemaUnavailable: the vendored thesis schema is missing at <path>`. It named
  the path, which is why it took one run to find. The spec now walks
  `backend/` for non-`.py` files, skipping `data/` and `tests/` **by name** and
  REFUSING any single file over 8 MB — the skip is the safety property and the
  ceiling is the second line of defence.

## 5. WHAT THE NEXT SESSION SHOULD DO

1. **Re-measure Qwen3 on an idle machine**, and sweep `--n-cpu-moe` from 48 down
   until VRAM is near full. The prompt-eval rate is the number that decides
   whether it can read a digest at all.
2. **Run the night queue FROM THE APP** and watch G3 survive a deliberate
   stop/resume. That is the acceptance test of both halves of today's work and it
   has been done only at smoke scale.
3. **Give every night receipt a `next_test` field.** The planner is built and
   starved.
4. **N3** (frozen-encoder + learned head, three controls) — check its receipt.
   If the frozen embedding does not beat TF-IDF, that is the result; S45 put the
   prior there.
5. **Do not add a router.** One independent selector with evidence.
6. **Chunk the evidence memory before it blocks a push.** Murat, 2026-09-10:
   *"maybe separate the memory into chunks... or find a much better method of
   compacting. we can put it in a different repo or somewhere else too?"*
   `evidence_memory.jsonl` is **62.14 MB** and GitHub warned on the push of
   `6485b73`; the hard reject is 100 MB and the file grows every night, so this
   is a deadline. Options weighed in
   `ROADMAP_2026-09-10_MODEL_NEWS_AND_THE_EVENT_NET.md` section 3b. The
   recommendation is **monthly rotation with the live chunk untracked** --
   sealed months are written once, which is the shape git is good at and the
   shape an evidence record should have. **Compaction is refused**: a log that
   summarises itself is not an evidence log, and dropping a row nobody thought
   mattered is the receipt-overwrite bug with better manners. Split by each
   row's OWN stamp, never by file mtime.

---

## 6. MUST NOT REGRESS (added to the 09-09 and 09-10 lists)

9. **A model swap opens a new arm; it never updates an existing lane's number.**
10. **The representation is frozen or the text experiment is unfalsifiable** — C2
    is the receipt.
11. **Three controls or no claim** for any text lane: TF-IDF, shuffled text,
    no-text.
12. **A search that does not advance its seed across nights is replaying itself.**
    Check the overlap against the previous run's log before crediting discovery.
13. **`listening` is not `ready`.** Probe the health route; carry both states.
14. **Kill by PID or refuse.** Never fall back to an image name, not even when
    the PID cannot be resolved.
