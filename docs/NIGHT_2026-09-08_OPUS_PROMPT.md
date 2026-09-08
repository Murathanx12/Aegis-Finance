# NIGHT 2026-09-08 — OPUS SESSION PROMPT (paste this whole file)

You are the Opus 5 builder for Aegis Finance. Read, in this order, before any code:
`CLAUDE.md` → `docs/AEGIS_STRATEGIC_INVARIANTS.md` →
**`docs/ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md`** (the plan you are executing) →
`docs/DECISIONS_2026-09-08_FABLE_ON_THE_REARM_AND_THE_ACTIVE_BOOK.md` (its §4 is
corrected by the roadmap's §3) → `docs/HANDOFF_2026-09-07_FABLE51_TO_OPUS5_TWO_MODES.md`
(session contract and agent conventions).

## The contract for this session

- **$0 of LLM.** No Anthropic, no OpenAI, no DeepSeek calls from any agent or job.
  Local inference only: `backend/services/free_inference.py` backend `local_gguf`
  (llama-server on 127.0.0.1:8080, started with `C:\Users\mrthn\llama\llama-start.cmd`).
- **Spawn every agent with `model: "opus"`.** Fable agents exhausted the session
  limit on 09-07. Agents write their reports incrementally, never only at the end.
- **Never `taskkill /F /IM python.exe`.** Kill by PID only. Tonight's PIDs: 166169
  (the CPU night queue), 166212 (the C1 GPU curriculum). Do not kill either unless
  the roadmap's STOP file is the wrong tool; the STOP file
  `backend/data/optimus/night_factory_2026-09-08/STOP` ends both between units of work.
- **Never move or edit `.env`.** Reproduce CI with `AEGIS_IGNORE_DOTENV=1`.
- **The holdout (months > 2015-12) is read ONCE, by `G2_holdout_once`, after G1
  ends.** No agent evaluates a searched object on it. D2's marked column is the
  model of how a holdout number is printed when it must be.
- **Nothing is ordered, sealed, pushed or deployed by an agent.** Fable or Murat
  push. Deploys are attended. Murat's flips are named in the roadmap §5.
- **Receipts before prose.** A job's JSON lands before its BUILD doc; the night
  leaderboard (`night_factory_2026-09-08/LEADERBOARD.md`) gets one typed row per
  job (`PRODUCT_PROMISING / CONDITIONAL / BETA_ONLY / CONSTRUCTION_SENSITIVE /
  REGIME_SPECIFIC / FAILED_VARIANT`). "Noise" is not a status.
- Terminal-repo tests only via `python run_tests.py`. Finance fast suite:
  `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`.
  After any push by Fable/Murat: `python -m scripts.ci_watch --wait`.

## Session one (tonight → morning): the lanes

Run the first three as independent agents now; the rest in session two.

| agent | lane | deliverable | done when |
|---|---|---|---|
| **A-M2** | D3 losers (roadmap §5) | `scripts/night_factory_jobs.py::D3_bottom_decile` + `D3_bottom_decile_run01.json` + `docs/BUILD_2026-09-08_D3_LOSERS.md` | bottom reaction decile graded by size tercile / liquidity / VW, β first, three eras; a borrow-aware short line and a put-proxy line; the AVOID/EXIT counterfactual on hack3/hack6's sealed names since 08-31 (terminal `state/` seals + `alpha/contract.py` exit types); an exit-clause DRAFT (not frozen) |
| **A-M3** | D4 cost floor | `D4_cost_curve.json` + doc | the long reaction leg at 25/10/5 bps × floors $3m/$20m/$50m per day × hold 21/42; the breakeven curve; statement of whether ANY long reaction book exists |
| **A-E0** | joined panel | `E0_joined_panel.parquet`, `E0_coverage.json`, doc | ticker→permno **by date** via `wrds/bulk/crsp__stocknames.parquet`; 2020-24 docs with bodies joined to CRSP daily; 2025-26 left as a named gap until Alpaca daily bars are pulled (attended network pull, Murat's key); all four coverage readings named (R4 §1) |
| **A-M1** (after ~21:00Z) | G2 read-once | `G2_holdout_once_run01.json`, leaderboard rows | `python -m scripts.night_factory_jobs G2_holdout_once` run exactly once; every archive genome gets its holdout t and its percentile against the 200 random genomes; the verdict sentence per genome |
| **A-N1** (session two) | NN with extended features | `learner_v3_*.json` | features added per roadmap §5 N1; `learner_v2_run` machinery reused, CPU torch; both rulers; paired vs v2 |
| **A-I2** (session two) | Form 4 features | `features_insider.parquet` | per name-month aggregates, PIT by filing date, red-test on a planted future row |
| **A-G3** (session two) | evolve v2 | `G3_*` | event/exit/routing genes; PBO-CSCV across DEV folds using the Vibe-Trading `multipletesting.py` port; Qwen-on-stagnation only |
| **A-X** | carry-over | — | taskkill hook in `.claude/settings.local.json`; the 4th Sunday suite fixture |

## How to verify before you report

1. `python -m scripts.night_factory --list`; read `QUEUE.log`, `G1_evolve_run01.log`,
   `C1.log`; `wc -l G1_evaluations.jsonl C1_counterfactual_news.jsonl`.
2. Fleet: from `aegis-alpha-terminal`, `python -m scripts.fleet --check-all`; read
   `railway logs --service aat-loop-<role>` for `refusals by class` and `SENTINEL`
   lines. The 09-08 deploy receipt is `state/deploy_receipts/2026-09-08_hack3_sentinel_fix.json`.
3. DeepSeek balance: `python -m scripts.llm_cost_audit --snapshot` — must still read $9.11.

## What the morning report must open with

The RESULTS SCOREBOARD (best historical net line vs market; best forward paper
line with β; independent selector count; night jobs run / promoted; the new
actionable finding; LLM spend = $0.00 with the DeepSeek balance read), then the
G2 reading in one table, then the fleet table, then what Murat must flip.
