# GROWTH BOOK LAB — 2026-09-07 — beat SPY's terminal wealth at a declared drawdown budget (Opus 5 prompt)

**Mandate:** `ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` — read it first,
whole. Then `BUILD_LABOR_DAY_LAB_2026-09-07.md` (the session before yours),
`BUILD_CONTINUATION_2026-09-06b.md` (the incumbents are a loading), and
`ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6.

## Rules
As `CONTINUATION_2026-09-06_OPUS_PROMPT.md` §1. **LLM cap $3** (mutation
proposals only, DeepSeek, naming the closest corpse via `lint_prereg`; every
return computed by code). No Anthropic/Claude API. Never kill by image name.
Runner or standalone job, never both; 6 GB free-memory guard on. Nothing
pushed, sealed, ordered, deployed or changed on Railway. Commit locally on
`main` per item. Both suites at the end.

**Declare before you run.** The objective, constraints, benchmark set,
development/test split (1999-2015 / **sealed 2016-2024**), and the
generation-0 genome list are written to
`backend/data/optimus/growth_book/DECLARATION.json` and hashed **before the
first evaluation**. The sealed era is evaluated **once per frozen
champion**, and the receipt records how many times it has ever been opened.

## Items

G1. **The ruler.** `learner/growth.py`: `evaluate_growth(book_returns,
spy_tr, rf, *, cost_bps, financing_bps=100, gross_cap=2.0)` returning TW
net, CAGR, maxDD, CVaR₅, worst month, β and intercept (HAC t), realized vol,
**leverage-neutral TW** (book scaled to SPY's realized vol, financing
charged), P(ruin) by block bootstrap for the largest admissible book, and
the drawdown-budget check. Unit tests on planted worlds (a pure-beta book
must show intercept ≈ 0 and win only on raw TW; a book with a planted
intercept must win leverage-neutral).

G2. **Generation 0 on the development era** (1999-2015, floored long
panel + SPY TR from `learner/benchmark.py`): every genome family in the
amendment §3, at 10 and 25 bps, with and without the drawdown-control
overlay and the trend gate; levered variants to the drawdown budget. CPCV
+ PBO for the ranking; family-max p and DSR across everything looked at.
Leaderboard ranked by **leverage-neutral TW at the drawdown budget**, with
raw TW, β, maxDD beside it. Receipt per genome; one summary receipt.

G3. **Mutation round** (≤ $3): LLM proposes ≤ 20 mutations of the top-5
development genomes (parameters, gates, combinations), each naming the
closest corpse; code evaluates on development only; lineage recorded on the
genome (`parent_ids`, `mutation_history`). Family grows; DSR recomputed.

G4. **Freeze and open the sealed era once.** Champion = best development
leverage-neutral TW that also passes the constraints and PBO < 0.5. Evaluate
on 2016-2024 exactly once; receipt states `sealed_era_openings: 1`. Compare
to SPY TR and levered-SPY at the same drawdown budget, after 25 bps. Either
outcome is a result; write it plainly with β first.

G5. **The NN's job.** `learner/growth_sizer.py`: a walk-forward sequence
model on market/regime features forecasting next-month q05/q50/q95 of the
champion book's return; fractional-Kelly exposure capped by the budget;
graded against Moreira-Muir trailing-vol targeting on the **development
era only** (the sealed era stays closed for the sizer until a later
session). CUDA if available (`requirements-gpu.txt`); 8 seeds; the seed-mean
ensemble is the object judged. Report: does NN sizing beat trailing-vol
sizing on after-cost TW at equal maxDD? DSR over the sizer family.

G6. **Forward contract draft** for hack4: `docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md`
— the frozen champion, B2 hold fields (horizon 21 for monthly books, min
hold 10), leverage ladder 1× → 1.5× → 2× with the 20-session rung rule,
attribution fields (β × market / intercept / sizing / costs / cash drag),
worst case in dollars at each rung for a $100k book. Murat freezes or
declines; nothing is enabled.

G7. **Forward lanes re-read under the product ruler.** For the ten
website lanes and the six hack accounts, from whatever NAV/equity is
readable (Railway API read-only or local receipts): β to SPY over the
available window, raw excess, leverage-neutral excess, maxDD. One table.
This answers "why do conservative-ATR and aggressive beat SPY" with a
number instead of an argument.

## Deliverable
`docs/BUILD_GROWTH_BOOK_2026-09-07.md`, ≤ 2 pages, RESULTS SCOREBOARD first
(the sealed-era line with β first; the leverage-neutral leaderboard top-10;
the NN-vs-trailing-vol sizing result; the forward-lane β table), the
declaration hash, claims for Fable to attack (5-10), test counts, LLM spend
to the cent. Update roadmap §6 (a `G growth book` row), session memory,
`MEMORY.md` (one line), `refresh_aegis.py` if reachable.

*The success criterion is a sentence Murat can read: "On 2016-2024, unseen
in development, book X returned N× vs SPY M× and levered-SPY L× at the same
drawdown, after 25 bps, β = b, intercept t = t." Or the honest negative.*
