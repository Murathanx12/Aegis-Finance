# BUILD — CONTINUATION 2026-09-06 (Opus 5 as builder, six parallel agents)

Mandate: `docs/CONTINUATION_2026-09-06_OPUS_PROMPT.md`. Nothing pushed, sealed,
ordered, deployed or changed on Railway. Every number below has a receipt path.

---

## RESULTS SCOREBOARD

*(filled at the end of the session — see the sections below for the receipts)*

| KPI | This session |
|---|---|
| Best historical net strategy vs the market | — |
| Best forward paper strategy | — |
| Independent selector count | — |
| Farm candidates tested / promoted | — |
| New actionable finding | — |
| External execution drag | — |
| LLM spend / cost per gradeable output | — |

---

## 0. THE CUDA QUESTION — ANSWERED: a different interpreter, not a downgrade

`W3_neural_long_run13` recorded `torch 2.11.0+cu128`, `cuda_available: true`,
RTX 5060, `sm_120`, while `.venv/Scripts/python` reports `2.11.0+cpu`. The
review offered two hypotheses. It was the first, and the filesystem settles it:

| evidence | value |
|---|---|
| `.venv/.../torch-2.11.0.dist-info/RECORD` mtime | 2026-03-31 11:22 |
| `.venv/Lib/site-packages/` directory mtime | 2026-08-27 17:35 |
| entries in that directory newer than 2026-09-01 | **0** |
| system Python 3.12 `torch-2.11.0+cu128.dist-info/RECORD` mtime | **2026-09-05 11:49** |
| first CUDA-stamped W3 receipt | 2026-09-05 13:30 |

A directory's mtime moves when an entry is added or removed. `site-packages`
has not moved since 27 Aug, so nothing was installed into or removed from the
venv on 5 Sep: **the venv's torch has been the CPU build continuously since
31 March and was never downgraded.** The CUDA wheel went into
`C:\Users\mrthn\AppData\Local\Programs\Python\Python312`, one hour and
forty-one minutes before W3 ran. `resolve_device()` was honest at the time
(`git show da82992`), so **the GPU numbers are real**.

**The real defect was that the device block named the torch build and never the
interpreter**, so the receipt could not answer the question it existed to
answer. Three fixes, committed:

1. `learner/neural_long.py` — every device block now carries
   `python_executable`, `python_version`, `torch_file`.
2. `requirements-gpu.txt` — pins `torch==2.11.0+cu128` with its `--index-url`,
   names the designated interpreter and the `AEGIS_GPU_PYTHON` override, and
   carries the filesystem receipt in its header.
3. `backend/tests/test_gpu_environment_pin.py` — 4 tests. **FAILS** on a host
   with an NVIDIA GPU whose designated interpreter stops reporting CUDA;
   **SKIPS** on a GPU-less host, because a GPU assertion on a GPU-less runner
   is a broken gate, not a strict one.

**The caveat that must travel with every W3 number:** it ran on system Python
3.12 (numpy 2.4.6, sklearn 1.9.0), an environment the fast suite has never
exercised.

Receipt: `backend/data/optimus/continuation_2026-09-06/S0_cuda_drift_run01.json`

---

## S1 / S2 — TWO OF THE REVIEW'S THREE SETTLEMENT ITEMS WERE ALREADY DONE; I PUBLISHED THE THIRD

`REVIEW_2026-09-06_ATTACK_ON_THE_WEEKEND.md` was written against `f6b96e3`
(13:07 +0800). Three things were named as settling CLAIM 1 and CLAIM 6.

**(a) Null `target_rev_1m` on `cfacpr` moves — ALREADY DONE, and as a REBASE.**
`35915db` (13:23) rebases the prior target by `cfacpr(t)/cfacpr(t-h)`
(`dataset.py:799-809`), which cancels every factor after `t` and keeps the
observation rather than throwing it away; the panel was rebuilt at 13:51.
Measured on the panel every job in this session reads:

| | review at f6b96e3 | panel on disk |
|---|---|---|
| rows with a `cfacpr` move | 4,303 | 4,359 |
| mean `target_rev_1m` on them | **+3.12** | **+0.0675** |
| max | +359 | +31.5 |

A 46x reduction in the mean. Still open: 2.04% of those rows report a >100%
one-month consensus move and the panel-wide max is +141.5 — a rebase cannot
repair two IBES vintages that disagree about the share basis, and nothing
bounds those rows.

**(b) The share-basis gate that could not go red — ALREADY FIXED** in the same
commit: `learner/long_panel.py` now tests the LEVEL against a 0.95 floor and
carries an `_injection_self_test` that re-runs it against the injected
2026-09-04 defect (0.978 real vs 0.853 injected).

**(c) Re-run W9 with `n_trials` populated — ALREADY DONE.** I got this wrong
first: I read `run09`, the receipt the review quoted, and called it open. There
are 31 W9 receipts and `run40` (09:00Z, after the review's tree at 05:07Z)
carries `n_trials_used_for_the_DSR` **307** and returns **DSR 0.1239,
WITHIN_SELECTION_NOISE**; SPA p 0.0679; PBO 0.1429; MDE 8.0%/yr; t=2 needs
36.3 years against 25.67 observed. The review estimated 0.2022 at 277 trials —
same direction, further. *Absence of a fix in the receipt you were handed is
not evidence of absence.*

**(d) The size-matched control table — GENUINELY OPEN, so I built it.**
`scripts/size_matched_control.py`. The reviewer computed it in a scratch
session and quoted it in prose; every headline number belongs in a receipt.
`target_rev_1m__xs`, top-50 VW, 10 bps, 308 months, on the panel on disk:

```
book net TW 85.324 | VW market 13.031 | EW market 57.183 | cap-matched 11.127

vs VALUE-weighted market   +11.52%/yr  t 2.407   eras 2.774 / 1.784 / 0.094
vs EQUAL-weighted market   + 4.01%/yr  t 0.859   eras 0.823 / 0.629 / 0.167
vs CAP-DECILE-MATCHED draw +11.55%/yr  t 2.496   eras 2.525 / 2.160 / 0.272
```

**The claim survives the right control and dies against an equal-weighted
market.** The decay is real relative to cap-matched peers and absent relative
to EW, because against EW there was never anything to decay. And it still
reaches no verdict: **DSR of book-minus-control is 0.3326** over the weekend's
own 307 trials — WITHIN_SELECTION_NOISE. The control pays the BOOK's cost
series so the comparison isolates selection.

Note for anyone comparing with the review: it quoted TW 56.655 / t 2.055 at
`f6b96e3`; `evaluate.book` on the rebuilt panel returns 85.324 / 2.407, and so
does W9 `run40`. Both are correct for their own tape. **Cleaning the share
basis made the arm stronger**, which is why contamination explains nothing.

Receipts: `.../continuation_2026-09-06/S1_panel_split_contamination_recheck_run01.json`,
`.../S2_size_matched_control_run01.json`

---

## THE REVIEW'S SIX RANKED NEXT MOVES — where they stand

| # | move | state |
|---|---|---|
| 1 | re-run W9 on the code on disk, publish `n_trials_used_for_the_DSR` | **DONE before this session** — `W9_survivor_books_run40_v0.json`, 307 trials, DSR 0.1239 |
| 2 | replace the share-basis gate's gap test with a level test, prove it by injection | **DONE before this session** — `long_panel.py` `LEVEL_FLOOR = 0.95` + `_injection_self_test` |
| 3 | null `target_rev_1m`/`target_rev_3m` across a `cfacpr` move; re-issue | **DONE before this session, as a REBASE** — mean on split rows 3.12 -> 0.0675 |
| 4 | add the EW-market and cap-matched-control rows | **DONE THIS SESSION** — `S2_size_matched_control_run01.json` |
| 5 | re-run W10 through the runner so it has a durable receipt | **STILL OPEN.** Not attempted: the house rule is one lab job at a time and the GPU pass held the slot |
| 6 | downgrade "clear as an exclusion" (claim 4) or re-issue at the $2 floor | **STILL OPEN** |

Three corrections to the continuation prompt itself, each verified against a
receipt rather than argued:

- *"W4 was CANNOT DETERMINE"* — the module's word is
  `CANNOT DETERMINE (underpowered)`, but the **receipt's** verdict, after the
  runner re-derives it through the screen bar, is **NOISE**
  (`W4_graph_momentum_run40_v0.json`). A feature screen cannot reach NOVEL and
  this one did not clear anything: 0 of 9 features reach |t| >= 2 with controls
  and one sign in 2 of 3 eras.
- *"MARKET-GRAPH-1 edges cover 12 of 26 panel years"* — true, and the window is
  **2014-2024**, not an early one. The panel-row match rate for the graph
  features is **1.1-2.8%**. So the 1999-2013 extraction §2a asks for is exactly
  the complementary window, and the honest bar for it is a match rate, not an
  edge count.
- *"Friday's L10 built the scaffolding"* — **false**, and independently
  confirmed by the agent that needed it: `BUILD_NIGHT_LAB_2026-09-05.md` lists
  L10 among the jobs NOT run and `night_lab_2026-09-05/` holds no L10 receipt.
  The scaffolding was built this session.

---
