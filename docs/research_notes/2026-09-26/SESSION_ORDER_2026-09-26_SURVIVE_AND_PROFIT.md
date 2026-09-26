# Session order — 2026-09-26 (afternoon) — improve the pipeline, not the roadmap

Murat's brief is the order (chunks A–I, verbatim in this folder's
`external_session_brief_2026-09-26.md`). The roadmap is
`docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md`. This file only assigns
ownership, file boundaries, and the rules each chunk must print.

## Roles
- **Sonnet**: discovery and literature (chunks C, D-research, H-research).
- **OpenClaw**: live web + the authenticated X account (chunks A, B, F). Read-only; never an order.
- **DeepSeek / NVIDIA (`integrate.api.nvidia.com`)**: named comparison/adjudication models only (chunk G registers NVIDIA as a provider; never "primary").
- **Opus builders**: one per chunk, disjoint files, commit only their own paths, never push, never reset. Full suite only when free memory ≥ 8 GB and no sim learn unit is running; otherwise the touched test files and a line saying the suite was skipped.
- **Opus reviewers**: after A, after D+E, after B+F, after G+H, after I — "you are wrong; I would have done this"; Fable adjudicates; the reviewer's ideas feed the next chunk.

## Waves and ownership (disjoint files)
| wave | chunk | owner | owns (create/modify) | reads |
|---|---|---|---|---|
| 1 | **A fast-mover forensics** | Opus | `backend/services/fast_mover_forensics.py`, `scripts/fast_mover_forensics.py`, `backend/data/optimus/forensics/`, tests | every ledger, books, bars, news corpus (PIT by `first_seen_utc`), cards, revisions, OpenClaw for pre-entry X reads (dated) |
| 1 | **D library → 200 + sealed columns** | Opus | `strategy_library.py`, `night_backtest_factory.py`, tests | `research_strategy_library.md` + the wave-1 Sonnet expansion note |
| 1 | **G model routing** | Opus | `backend/services/llama_server.py` (on-demand + idle shutdown), OpenClaw localService config, the Telegram command router (find it under `backend/services/telegram*` / `scripts/telegram*`), `llm_analyzer.py` (NVIDIA as a NAMED provider + `/compare` packet), tests | `docs/OPERATOR_SURFACE_2026-09-22_*`, `docs/OPENCLAW_2026-09-22_SETUP.md` |
| 1 | **I daily learning report** | Opus | `scripts/daily_learning_report.py`, one hook at session end in `scripts/sim_run.py` (`run()` exit only), `backend/data/optimus/learning_reports/`, tests | every receipt of the day |
| 1 | C research | Sonnet | `research_notes/2026-09-26/research_families_to_pit_features.md` | — |
| 1 | D research | Sonnet | `research_notes/2026-09-26/research_library_expansion_and_lean.md` | — |
| 2 | **B source/actor graph** | Opus | `backend/services/source_registry.py`, `scripts/source_reads.py`, `backend/data/optimus/sources/`, tests | OpenClaw + X; `forecast_reputation` keyed by `source_id` |
| 2 | **E backtest→forward bridge** | Opus | `scripts/bridge_report.py`, `llm_portfolio.grade` (one added table), tests | `strategy_library/leaderboard_*.json`, `llm_portfolio/leaderboard_*.json` |
| 2 | **F OpenClaw quests** | Opus | `backend/services/thesis_card.py` (the question set + evidence→forecast→grade), `scripts/thesis_cards.py`, tests | — |
| 2 | **H Railway cost review** | Sonnet + Opus (report only) | `docs/REVIEW_2026-09-26_RAILWAY_COST.md` | `../aegis-alpha-terminal`, `railway status/logs` read-only; **no production mutation** |

## Rules that bind every chunk
1. **Sealed before pretty.** Every library leaderboard row prints: dev return, SPY, **sealed/OOS return** (a date split declared before the run: development ≤ 2023-12-31, sealed 2024-01-01 → today, and a second sealed window = the last 126 sessions), DSR at the cells looked at, LOO-worst, top-5-month share, turnover, cost, max DD, recent-period return. The objective is **maximise sealed net return**.
2. **No later evidence explains an earlier forecast** (chunk A): the state at entry is rebuilt from rows with `first_seen_utc`/`made_at`/`filed` ≤ entry; the ex-post catalyst is a separate column.
3. **Social is an attention layer, not a truth layer** (chunk B): a source's claims become forecast rows and earn a reliability weight; X and Reddit never generate orders; a source may be kept as a reversal indicator.
4. **Every concept becomes a PIT column** (chunk C): a family that cannot name its observable, its PIT rule and its source file is not registered.
5. **A forward failure is investigated, not deleted** (chunk E): REGIME_SHIFT / CROWDING / FACTOR_DECAY / DATA_LEAK / IMPLEMENTATION / COST / UNIVERSE_CHANGE / RANDOMNESS / UNKNOWN.
6. **Every OpenClaw result = structured evidence + timestamp + forecast + future grade** (chunk F).
7. **Cost per provider is measured** (chunk G): the same packet to local / DeepSeek / NVIDIA, all frozen, graded later.
8. **Production is not mutated by a review** (chunk H).
9. The day ends with chunk I's three sentences, not a roadmap.
