# CONTINUATION — 2026-09-06 (Sat evening HK) — the next Opus session, written by Fable after validating the weekend lab

**Read first:** `BUILD_WEEKEND_LAB_2026-09-06.md` (your predecessor's report,
including its own retractions), `REVIEW_2026-09-06_ATTACK_ON_THE_WEEKEND.md`,
`REVIEW_2026-09-06_CODE.md`, `ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6,
`DECISIONS_2026-09-05_PLAIN_LANGUAGE.md`. Then `session_briefing()` and
`aegis_verified_state(section="summary")`.

## 0. Fable's validation of the weekend (so you do not redo it)

Checked against receipts, not prose: evidence memory state counts
(SUPPORTED 12, IDEA 313, 101 observations superseded by one reasoned rule);
W9 tail concentration (54.3% of the revision book's excess in five months,
t 0.84 without them); W3 neural arm 698× unfloored → 64.9× under the $3m
floor, "does NOT beat lgbm"; W13 composite exclusion NOISE. All match the
build doc. **The weekend's cumulative verdict stands: nothing reached NOVEL;
the one idea with repeated screen support is analyst revisions, and it does
not survive becoming a tradable book. The 26-year learner champion is six
market-bottom rebound months.** Fast suite on the tree is being re-run by
Fable; 33 local commits will be pushed by Fable after it passes.

One inconsistency you must resolve first: `W3_neural_long_run13` records
`torch 2.11.0+cu128`, `device_actually_used: cuda`, RTX 5060 sm_120 — but
`.venv/Scripts/python -c "import torch"` now reports `2.11.0+cpu`. Either a
different interpreter ran W3 or torch was downgraded afterwards (a
`pip install -r requirements.txt` would do it; torch is not pinned). Find
which, pin the CUDA build where it cannot be undone silently (a
`requirements-gpu.txt` + a documented install line + a smoke test that FAILS
on this laptop when CUDA is unavailable and SKIPS on CI), and record the
answer in your build doc.

## 1. Rules (unchanged, plus the OOM rule)

- Clean long panel only; every market number from `learner/benchmark.py`;
  `TRADABLE_DOLLAR_VOL` + $5 floor inside every book AND inside training
  universes, not only at grading.
- Receipts always; family size + family-max p + DSR + MDE + three-era table
  on every edge claim; verdict vocabulary as the repo defines it (screens
  cannot reach NOVEL).
- **Either the loop runs or a standalone job runs, never both**; bounded
  foreground passes; the runner's 6 GB free-memory guard stays on.
- No Claude API. LLM cap **$15 total** for this session through the spend
  gate: ≤ $10 for §2a, ≤ $5 for §2b, $0 elsewhere. Every call names the
  decision it can change.
- Nothing pushed, sealed, ordered, deployed or changed on Railway. Commit
  locally on `main` per job with a receipt path in the message. Fast suite
  green at the end (`AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`);
  terminal `python run_tests.py` if you touch it.

## 2. The work, in priority order

The tape is at its statistical ceiling for the features it already has
(MDE ~7.4%/yr for a top-50 book over 21 years). Spend this session buying
**information the tape lacks** and making **Monday's books learn**, not
re-running the same grid.

### 2a. Buy supply-chain information (the one place LLM dollars buy evidence) — ≤ $10
W4 was CANNOT DETERMINE because MARKET-GRAPH-1 edges cover 12 of 26 panel
years and 386 of 8,981 names. The extractor exists in the third repo
(`../Aegis module/scripts/mg1_*.py`: 10-K Item 1 → competitor / customer /
supplier edges, name→permno resolver, $2.66 for 10,923 edge instances). Run
it forward in the finance repo (copy, do not import across repos) over
**1999-2013 10-K filings** for the panel's largest 1,500 names by coverage,
DeepSeek `deepseek-chat`, PIT by `filing_date`, into
`backend/data/optimus/graph/companyworld_v1.parquet` (`graph_layer=FACT`,
`valid_from/valid_to`, `source`, `confidence`). Then re-run W4 on the long
panel with the customer-momentum, competitor-momentum and shared-technology
features, with inference. Receipt names edge counts by year and the cost to
the cent. If the extractor cannot be made to run in 90 minutes, stop, write
the receipt saying why, and move on.

### 2b. The LLM reading test — era replay v2, decide step — ≤ $5
Friday's L10 built the scaffolding; run the **decide** step on ≤ 200 windows
of the 2016-19 era: gpt-5-nano rewriter (`reasoning_effort="minimal"`,
~$0.03/1k), DeepSeek decider, fantasy arm vs real-anon arm, **with and
without the diary**, nulls 1-3, year/company canary, **rank graded only**
(code prices). Terminal wealth vs the same-era equal-weight basket. This is
a different information source from the tape and the only "LLM in the
backtest" Murat asked for that we have not yet measured beyond 11 dates.

### 2c. The neural arm, honestly scoped
Re-run W3 with the tradable floor applied to the **training universe** (not
only at grading), 8 seeds × 2 variants, GPU. Report vs `lgbm_clf` under the
same floor with DSR and the era table. If it does not beat lgbm under the
floor, write "B10 not earned" in the roadmap §6 row and stop the neural
loop; if it does, freeze one champion and start shadow accrual.

### 2d. Monday must learn — B3 in the terminal repo
1. `daily_learning_report`: every CANNOT DETERMINE section caused by our own
   plumbing gets its input (live-equity fallback, counterfactual marker
   revived, shadow path env, tracker path); one SPY close source.
2. Revive `daily_autopsy` on the after-close schedule with a receipt every
   night even when empty; its second question (biggest idiosyncratic
   winners/losers across the whole market, did AEGIS generate the name)
   becomes the opportunity-recall ledger with typed misses.
3. **Dry-run Monday**: seal today's tracker vintage locally under
   hygiene-only band (decision B.1 §4a — Murat's "guides not rules" is the
   approval; implement 4a on the research side now, prepare the live
   `alpha/tracker.py` change as a commit Murat can enable), run hack3/4/6's
   10:01 pass in dry mode, and print: names admitted, the binding constraint
   per book, the contract fields on every holding, min hold 10, armed/
   disarmed state. Attach the printout to `RUNBOOK_2026-09-08_REARM.md` so
   Monday has no surprises.

### 2e. Evidence memory → registry (B6 §4, small)
A test that a superseded family cannot vote; a `--to-registry` export that
writes `(family, era, state) → {n, sharpe, dsr, spa_p, pbo, verdict}` rows
into `backend/data/signal_registry.yaml`'s new `conditional_evidence` block
(read-only for the PM until B9). The registry must see what the memory knows.

### 2f. Draft, do not freeze: the revision book contract for hack2 (B9 remap)
`docs/CONTRACT_DRAFT_2026-09-06_REVISION_BOOK.md`: top-50 by `net_rev_4w`
over the tradable universe (≥ $3m/day, ≥ $5), six overlapping monthly
cohorts, horizon 126 sessions, min hold 42, typed exits, 10 bps assumed,
benchmark SPY TR; the honest power line (the tape says it needs ~36 years
for t=2 at its own Sharpe; forward paper cannot adjudicate the alpha claim;
the book exists to test **holding discipline and regret**, not alpha).
Murat freezes or declines.

## 3. Deliverable

`docs/BUILD_CONTINUATION_2026-09-06.md`, ≤ 2 pages, scoreboard first: the
CUDA answer; edge counts bought and W4's new verdict; the era-replay table
(fantasy / real-anon × diary on/off, rank metrics, canary rate, cost); the
neural arm under the floor vs lgbm; Monday dry-run printout; registry rows
written; claims for Fable to attack (5-10, with receipts); LLM spend to the
cent. Update roadmap §6 (B3, B5, B7, B10 rows), session memory, `MEMORY.md`
(one line), and run `python tools/refresh_aegis.py` in the Optimus repo.
