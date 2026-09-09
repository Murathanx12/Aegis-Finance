# 2026-09-09 — OPUS DAY-RUN PROMPT (paste this whole file)

You are the Opus 5 builder for Aegis Finance, running the night factory for a
WHOLE DAY. Read in this order before any code: `CLAUDE.md` →
`docs/AEGIS_STRATEGIC_INVARIANTS.md` → `docs/ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md`
(**§10 is your mandate; §§8-9 are last night's receipts; §10.2 is the protocol**) →
`docs/REVIEW_2026-09-09_FABLE51_ON_THE_NIGHT_AND_THE_BACKTEST_METHOD.md` (what was
wrong, what changes) → `docs/NIGHT_2026-09-08_OPUS_PROMPT.md` (the session contract,
unchanged).

## The contract (unchanged, restated)

- **$0 of LLM.** Local `local_gguf` only (llama-server 127.0.0.1:8080, `C:\Users\mrthn\llama\llama-start.cmd`). No Anthropic, no OpenAI, no DeepSeek.
- **Every agent on `model: "opus"`**, writing its report incrementally.
- **Kill by PID only.** The STOP file `backend/data/optimus/night_factory_2026-09-08/STOP` ends the queue between jobs.
- **Never move or edit `.env`.** `AEGIS_IGNORE_DOTENV=1` reproduces CI.
- **No orders, seals, pushes, deploys, Railway changes by an agent.** Murat's flips are listed in §10.8.
- **Receipts before prose; a typed leaderboard row per job; "noise" is not a status.**
- **Every event cell carries `vs_control`** (its own matched control, subtracted), and every product stamp is read on random windows as an EXCESS over the random-genome null (§10.2). A holdout, if one is read, is read once by a named job with a `min_months` derived from the window.
- Tests: terminal repo ONLY via `python run_tests.py`; finance `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`; ruff must pass (CI runs it). After any push by Fable/Murat: `python -m scripts.ci_watch --wait`.

## The day queue (run `python -m scripts.night_factory --job <id>` per job, or the whole queue)

| order | job / lane | agent | deliverable | done when |
|---|---|---|---|---|
| 1 | **RW1 second draw** (`--seed 20260910`) | A-RW | `RW1_random_windows_run02.json` | two draws agree on the excess-over-null ordering; disagreement is itself reported |
| 2 | **RW2** random windows for the event-clock books (N1 `H5\|all` scores, the reaction long-short at the $10m floor) | A-RW | `RW2_event_windows_run01.json` | same window seeds as RW1; each cell has `vs_control`; borrow cost line at 0/50/200 bps/yr on the short leg |
| 3 | **G3 evolve v2** | A-G3 | `G3_evolve_run01.json` + `G3_evaluations.jsonl` | fitness = median β-matched excess over 40 random DEV windows (seeded per generation); DD budget is a hard refusal; archive de-duplicated by ancestry (parent hashes stored); NO holdout read |
| 4 | **N2 step one: data-net `learner_v3`** | A-N2 | `learner_v3_<date>.json` | event features (z-scored reaction decile, sessions since print), U state probabilities, I2 insider aggregates added to the long table; `learner_v2_run` machinery; graded alone under both rulers; paired vs v2 |
| 5 | **P6 bars + regret** (§10.4) | A-P6 | `prices_2025_26/bars.parquet` + receipt; `P6_regret_run01.json` | daily bars 2025-01→today for the tracker universe + SPY through the terminal repo's data credential (no order path imported); the six mandates replayed monthly from 2026-03; each vs what the account did vs SPY; opportunity capture |
| 6 | **R2 pilot** (§10.5, GPU after C1) | A-R2 | `R2_monthly_llm_2022.json` | AMNESIA canary FIRST (real vs anonymised names); monthly + six-monthly cells on 2022, β first, shuffled-digest control |
| 7 | **A0 control router** (§10.7) | A-A0 | `backend/routers/control.py` + tests | whitelist of job ids, PID file per run, STOP-then-kill-by-PID, no order path imported (AST test like `test_the_router_imports_no_broker`) |
| carry | X: taskkill hook, 4th Sunday suite; F2: hack2 evidence gate as a declared threshold (draft for Murat); F4: hack4 v3 sector-rotation draft | A-X/F | — | — |

## Verify before you report

`python -m scripts.night_factory --list`; the night dir's `*.log` and `LEADERBOARD.md`;
`python -m scripts.fleet --check-all` from the terminal repo (six books + orders working);
`python -m scripts.llm_cost_audit --snapshot` (DeepSeek balance must still read $9.11).

## The evening report opens with

The RESULTS SCOREBOARD (best historical net line vs market; best forward paper line
with β; RW1/RW2 excess-over-null table by era and length with what each winner
HELD; G3's DEV archive and the fact that no holdout was read; N2's data-net vs v2
paired; P6's regret table for the six books vs SPY; $0.00 with the balance read),
then the fleet table, then what Murat must flip.
