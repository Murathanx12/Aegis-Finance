# NIGHT LAB — 2026-09-07 (Sun night HK → Mon, Labor Day) — construction, events, unsupervised, simulations

**Read first:** `BRAINSTORM_2026-09-06_WHY_NO_PROFIT_AND_WHAT_OTHERS_DO.md` §3
(the list this night executes), `ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md`,
`BUILD_GROWTH_BOOK_2026-09-07.md`, `BUILD_LABOR_DAY_LAB_2026-09-07.md`,
`ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6. If the Optimus MCP is down, read
`docs/INDEX.md` TIER 0 and proceed.

**The night's one question:** *does the IC we already have turn into money
once the construction stops destroying it?* Everything else is in service of
that, plus the unsupervised and simulation lanes Murat asked for.

## Rules
As `CONTINUATION_2026-09-06_OPUS_PROMPT.md` §1 and CLAUDE.md rules 6-8.
**LLM cap $8** ($3 fantasy exams round 2, $3 event-compression labels if the
local embedder is unusable, $2 mutation proposals). No Anthropic/Claude API.
Never kill by image name. Runner or standalone job, never both (6 GB guard;
Chrome/Discord/VS Code hold ~17 GB — check `_free_gb()` before every heavy
job). Nothing pushed, sealed, ordered, deployed or changed on Railway; commit
locally on `main` per item; **run `python -m scripts.ci_watch --n 1` at the
start** and if CI is red on HEAD, fix that FIRST (a red CI is the session's
first task). Both suites at the end. Receipts under
`backend/data/optimus/night_lab_2026-09-07/`, provenance-stamped, β first on
every book receipt, family size + family-max p + DSR + MDE + three-era table
on every edge claim. A `STOP` file halts the loop.

## Lane N1 — construction: does the IC become money? (the priority)
1. **Fundamental-law receipt** (`learner/fundamental_law.py`): for any book,
   IC, effective breadth (Σw)²/Σw², transfer coefficient (corr of realised
   weights with the unconstrained signal weights), β, and the implied IR vs
   the realised IR. Unit-tested on planted worlds. Attach to every book
   receipt from tonight on.
2. **Broad hysteresis books** for `lgbm_clf`, `nn_pre_causal`, ridge, the
   revision family, momentum, quality-momentum, and the N2 ensemble: top-100
   and top-300 of the tradable universe, equal- and rank-weighted, **Qlib
   TopkDropout hysteresis** (hold until rank > 2k), monthly refit, at 10/25
   bps; graded **beta-matched** (primary) and raw (secondary), 1999-2024
   walk-forward, three-era table, family-max over every cell. Compare each
   to its old top-50 VW construction on the same months: the difference IS
   the transfer-coefficient cost.
3. **Monetise the bottom decile**: (a) index-hedged long-short (long top
   decile EW, short SPY to β≈0) and (b) exclusion books (tradable universe
   minus bottom decile, EW) for every selector; report against EW-universe
   and SPY TR.
4. **Retraining cadence** as the default: monthly refit inside every book
   above (A2's +5.75pp).

## Lane N2 — the ensemble (selection-free)
Stack every trained arm's out-of-sample rank (lgbm_clf, lgbm_raw, ridge,
encoder, nn_pre_causal, revisions, momentum, quality, options, behavioural)
into one rank-average weighted by each arm's **rolling 36-month beta-matched
reliability from the evidence memory** (Numerai's meta-model on our tape).
No champion selection → report the ensemble's DSR with family = 1 plus the
honest note that its inputs were searched. Feed it into N1's constructions.

## Lane N3 — size-aware floors
`execution_authority` floors as a function of book size and participation:
for a $100k book at 1% ADV, the floor is ~$500k/day, not $3m. Populate
OBSERVE_ONLY (`build(scope="observe")`). Re-grade the cells that died at $3m
(the small-cap 5-session reversal, the unfloored neural arm, S28's
$100k-$1m band) with **measured TAQ spreads** (we own `taq_iid_*`) instead
of flat bps. Receipt: edge vs floor curve, by book size $100k/$1m/$10m.

## Lane N4 — the event-time table (2015→; network job, runs while others compute)
`scripts/news_backfill.py --months 130 --universe tradable` (Alpaca/Benzinga
back to 2015, free on our entitlement; throttle-aware, resumable), joined
with IBES actuals (`ibes__actu_epsus` on disk) for surprises, the 8-K tape,
13D/G and Form 4 → `backend/data/optimus/events/event_table_v1.parquet`
(PIT: observed_at = availability). Then PEAD, revision-on-event, and
surprise×reaction books across the whole tradable universe with N1's
construction. Manifest row; receipt with coverage by year.

## Lane N5 — unsupervised, where it can win
1. **Event compression**: cluster the corpus + backfill into canonical
   events (dedupe syndication) with the NVIDIA `nemotron-3-embed-1b`
   embedder if reachable (341 calls exist; batch 50) or TF-IDF locally;
   features: `independent_source_count`, `novelty_vs_company_history`,
   `dissemination_speed`. Test the novelty feature on the event table.
2. **Self-supervised pre-training** (`nn_pre_causal` recipe) on the long
   panel + N4/N5 features, CUDA via the designated interpreter
   (`requirements-gpu.txt`), 8 seeds, seed-mean judged, then INTO the N2
   ensemble — never as a lone champion.
3. **States, third null**: the name-path-controlled permutation; final
   verdict on the four states; if CANNOT DETERMINE, demote them everywhere.

## Lane N6 — simulations
1. **Known-answer battery v2**: planted linear / regime / graph / event
   edges must be recovered through the **N1 broad-book path** and the N2
   ensemble, and the null world must read NOISE; any miss is a machine
   defect. Test-pinned.
2. **Fantasy stress exams round 2** (≤ $3): 40 new pairs on *event*
   archetypes (earnings surprise up/down, guidance cut/raise, activist stake
   in/out, index add/drop, financing/dilution); monotonicity share, canary.
3. **Path Monte Carlo for the hack4 contract at 1×** (block bootstrap of the
   champion's monthly returns 1999-2024): drawdown distribution, P(lose
   half) at 1×/1.3×, time-under-water; feeds the contract's worst-case table.

## Lane N7 — memory, registry, loop
Every receipt → evidence memory → registry `conditional_evidence`; the
leaderboard's "best so far" block by **beta-matched, family-corrected**
result; after N1-N6 the runner loops N1/N2 with the next variant list until
STOP.

## Morning deliverable
`docs/BUILD_NIGHT_LAB_2026-09-07.md`, ≤ 2 pages, RESULTS SCOREBOARD first:
the N1 answer in one sentence (IC → money, yes/no, with the transfer
coefficient before and after); the ensemble line; the floor curve; event
table coverage; the unsupervised verdicts; battery + exams; claims for Fable
to attack (5-10); test counts; LLM spend to the cent. Update roadmap §6,
session memory, `MEMORY.md` (one line), `refresh_aegis.py` if reachable.

*Tuesday 09-08 pre-open is attended (runbook in the terminal repo). This lab
touches nothing live.*
