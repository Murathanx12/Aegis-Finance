# Spec — the strategy library and the nightly backtest factory (Murat, 2026-09-26 02:00 HKT)

Murat: *"I wanted to focus on maximizing backtests ... 100 backtests maybe, and
list the top 10, say that this made 1,000% when the S&P got 200-300 ... do a
search on strategies, what other people said ... that is your ultimate purpose
on this nightly simulation. And then see how the backtest is actually
performing on the current date ... with a forward paper account ... if it
works we adopt it ... and say: if Aegis had existed in 2020 to now, this is
what it would have done vs the S&P 500."*

## What exists and does not connect (read before building)
| machinery | what it does | tape | why it is not the library |
|---|---|---|---|
| `backend/services/portfolio_farm.py` + `scripts/portfolio_farm_run.py` | hundreds of policies over one replayed history (presets holding / breadth / signals), refuses zero costs | learner tape (CRSP, 2013-2024) | its results live in farm receipts nobody ranks nightly |
| `xs_ranker.top_k_backtest` | any feature ranking → net top-k, by_year, LOO, worst cell | survivorship-free 2016-2026 bars | one feature at a time |
| `scripts/revision_flow_sweep.py` | with/without flow + the month-end rule | same bars | one strategy |
| `scripts/night_first_books_replay.py` | books A-D replayed with random twins | CRSP | four books, on request |
| `night_factory` G3 evolve | genomes over banks | learner tape | discovery, not a library |
| `learner/benchmark.py` | THE market leg (SPY) every receipt must use | | keep |
| `llm_portfolio` books + twins + daily grade | forward paper books | live | the forward half |

Every one of them backtests; none produces the sentence Murat wants. The
library is the one place a strategy is DEFINED once, backtested nightly the
same way as every other, ranked honestly, and handed a forward book.

## Deliverable 1 — `backend/services/strategy_library.py`
A `Strategy` = `{id, family, description, universe_rule, signal(panel, asof) -> scores, k, hold_days, rebalance, weight_rule, source: "ours|literature:<ref>", registered_utc}`.
Seed **≥ 100 strategies** across families, each ONE line of code over the
existing feature panel (no new data): momentum (12-1, 6-1, 3-1, 52w-high,
residual), reversal (1m, 5d), low-vol / min-vol, quality (gross margin, ROA if
present), value (from `fundamentals_sec` where PIT), size × liquidity bands,
revision flow (net raises, n_firms, median change; the month-end rule and its
variants), inflection (rev_qoq × margin_chg), insider clusters (from
`pit_observations` where PIT), catalyst proximity (the YAML), thesis-card
verdicts (from 2026-09-25 forward only), investigator p (forward only),
combinations (2-3 signal ranks averaged), and the literature set Sonnet
returns (`research_notes/2026-09-26/research_strategy_library.md`): each with
its citation and the paper's reported number beside ours.
Every strategy carries `first_registered_utc`; a strategy's "since 2020"
number is only quotable for dates after its registration (no backfilled
hindsight — the invariant).

## Deliverable 2 — `scripts/night_backtest_factory.py` (a night unit, runs every night)
- Tape: the survivorship-free 2016-2026 bars ∪ delisted (`xs_ranker.survivorship_free_paths()`), monthly rebalance dates, net of `round_trip_bps` by band; SPY from `learner/benchmark.py`.
- Per strategy: cumulative net return 2020-01-01 → last session, CAGR, max DD, Sharpe (with `n_date_blocks`), **by-year**, **leave-one-year-out worst**, worst breadth cell (k 10/20/50), turnover, and the **honest t on horizon-wide blocks**.
- **Multiplicity:** the library is one family; the receipt prints the number of strategies LOOKED AT and the deflated Sharpe (DSR) at that count; the top-10 table carries `dsr` beside `sharpe`. "1,000% vs 200%" is printed with its DSR and its LOO-worst beside it, or not at all.
- Leaderboard `backend/data/optimus/strategy_library/leaderboard_<date>.json` + `LEADERBOARD.md`: top 10 by net CAGR since 2020, top 10 by DSR, bottom 10, and the SPY line. Idempotent per day; **resumable** (checkpoint every 10 strategies; a crash loses ≤10).
- **Forward twins:** every top-10 strategy (by DSR) that has no frozen forward book gets one via `llm_portfolio.freeze` (kind personal, name `lib_<id>_<date>`, positions = today's top-k, twins ew/sector_etf/random_same_band/spy). The daily `grade` then reports backtest-vs-forward side by side: `forward_21d_vs_backtest_mean_21d` — the sentence "the backtest says +X, the forward book says +Y".
- Adopt/reject rule (declared here, not tuned later): a library strategy is ADOPTED to EXPLOIT candidacy when its forward book has ≥ 63 sessions, beats SPY and its random twin net, and its by-year backtest has ≥ 4 positive years of 6; REJECTED when the forward book trails both for 63 sessions; otherwise RUNNING.

## Deliverable 3 — the era replay ("if Aegis had existed in 2020")
Phase 2, after Deliverable 2 runs three nights: replay the **whole decision
pipeline** month by month 2020→now with only data dated ≤ each month (ranker,
revision flow, fundamentals PIT; no LLM reads over history — the
Lookahead-Propensity rule) and print the NAV line vs SPY with the same
by-year/LOO/DSR. `time_machine_arena` and the era-replay receipts are VOID
until re-issued on the rebuilt panel (INDEX 09-04) — this is that re-issue.

## Tests first
1. A planted panel where one signal has a known net edge: the library ranks it first, prints by-year, LOO, DSR at n=100, and the random-twin freeze happens.
2. A strategy registered after 2024-06 has no quotable number before its registration.
3. Zero-cost refusal (Policy refuses zero costs) is inherited.
4. Checkpoint/resume: kill after 15 strategies, resume finishes 100 without recomputing the 15.
5. The leaderboard's SPY leg comes from `learner/benchmark.py` (`test_benchmark_canonical` passes).

## Cost and time
CPU only, no LLM. Budget ≤ 90 minutes per night at 100 strategies on the
2016-2026 bars (subsample rebalance dates to monthly; vectorise). Print the
worst case in dollars for any forward book it freezes (the PROBE line).
