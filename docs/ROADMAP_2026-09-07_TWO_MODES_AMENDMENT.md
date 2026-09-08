# ROADMAP AMENDMENT — 2026-09-07 — TWO MODES, ONE SYSTEM

**Status:** ACTIVE amendment to `ROADMAP_2026-09-04_PROFIT_ENGINE.md` (which
stays the TIER 1 roadmap; its §6 is still the live status table and gains the
rows in §6 below). Read with `ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md`
(the second ruler) and `REVIEW_2026-09-07_FABLE51_ON_GPT_AND_MURAT.md` (why).
Gates outrank dates. Nothing here is blocked by a calendar; everything is
blocked by its dependency and its evidence.

## 0. The reset, in one paragraph

Five months were spent on stage one of a four-stage chain, and stage one is
not where the money died. Information leaves a book at four places:
**prediction → selection → construction → holding/exit**, and the last two
were measured to destroy most of what the first one had (transfer coefficient
0.13 → 0.49 by construction alone; turnover 0.90 → 0.53 by holding alone).
Meanwhile the product has two customers who are the same person: Murat
deciding with the machine beside him (Mode A), and the machine deciding with
Murat auditing it (Mode B). These are one system at two authority levels, and
Mode A is how Mode B gets its labels. So the order is: hygiene → the decision
surface and the human book → the data nobody else has (Murat's decisions,
free SEC investor data, the event table finished) → Murat's era replay with a
memory-free control → the unsupervised-to-hypothesis route → the strategy
interface that makes a new mechanism a file instead of a session.

## 1. Amendments to the invariants (proposed for `AEGIS_STRATEGIC_INVARIANTS.md`; binding here now)

17. **Four stages, every receipt.** A book receipt reports where information
    died: IC, effective breadth, transfer coefficient, hold statistics, and
    exit attribution by typed reason. A book with TC < 0.5 is a construction
    defect and its signal verdict is unreadable from it.
18. **Two authority levels, one ledger.** Mode A (human decides) and Mode B
    (machine decides) write the same typed decision row and are graded by the
    same four counterfactuals: held to declared horizon, held to next
    scheduled review, the engine's own pick, SPY. Neither mode is a product
    without the other.
19. **A loss budget is declared before the first position.** Every
    PRODUCT_EXPERIMENT book states how many positions it is judged at and how
    many it expects to lose. An idea is retired by its book's scoreboard,
    never by its own first loss.
20. **Confidence is coverage-normalised.** It shrinks toward the base rate by
    evidence quality and never grows with news volume. The ranking objective
    is expected utility at the declared drawdown budget, so a 20%-probability
    5:1 idea may outrank a 60% 1:1 idea.
21. **An LLM's memory is measured, not instructed away.** Any historical text
    scored by an LLM carries a real-anon control arm and a leak canary, or it
    is not admissible. (AMNESIA-1: the instruction did nothing, 15.8% vs 15.8%.)

## 2. THE NEW BLOCKS (lettered; B1-B10, G, L, N, W rows in the main roadmap stand)

### X — HYGIENE WITH OWNERS AND TESTS (first; a red line beside real checks teaches skimming)

| # | item | repo | test that proves it |
|---|---|---|---|
| X1 | **Clock skew guard**: every ET gate compares local time with the venue clock (`GET /v2/clock`) once per pass; skew > 5 min ⇒ REFUSE entries with class `CLOCK_SKEW`, exits unaffected | terminal | `tests_smoke_labor_faults.py` case 6 flips from "no guard exists" to "guard refuses at +20/−20 min" |
| X2 | **Stale NAV**: lane NAVs re-marked at the official close; a mark older than the session is stamped STALE on the row and excluded from β | finance `backend/services` | the G7 Dimson lead/lag test: `conviction`'s lagged loading falls below its contemporaneous one |
| X3 | **Sunday fixtures**: `run_pass` end-to-end suites derive a weekday session clock AND a venue-open fixture; `considered=0` on a closed venue is a REFUSAL with a reason, not a silent zero | terminal | the four suites pass on a Sunday |
| X4 | **`VENUE_REJECTED`** refusal class | terminal | `refusal_classes` test; C1 row updated |
| X5 | **`verdict_from`** gains SEPARATED_NOT_SURVIVING (t clears MDE, Holm does not); the planted edge at Holm 0.0154 must not read NOISE | finance | B1 battery re-run |
| X6 | **`evaluate.ERAS` callers** pass `eras=` or call `long_eras()`; no caller refuses on a long panel | finance | the two named call sites |
| X7 | **One price table**: `llm_research.PRICE_PER_MTOK` imports `config.LLM_PRICE_PER_MTOK`; a test fails if two rate tables exist | finance | `test_llm_provider_declaration` sibling |
| X8 | **`STATE_SEMANTICS`** text says CANNOT_DETERMINE and informational-only; vintage headers stop quoting null 1 as validation | finance | potential-universe header test |
| X9 | **Stale doc numbers** corrected in place, receipts win: event table 2015-2026 / 789,277 rows in 2015-2024; compression 137,190 → 105,494; NVIDIA embedder REACHABLE; conviction 0.6072 / 1.399; long-short β up to 0.4254; round-2 canary END 0/8, FRONT 1/8; the construction-tax table shown at equal cost (3.66 → 18.14 at 25 bps; 8.96 → 29.27 at 10 bps) | finance docs + roadmap §6 | `test_benchmark_canonical`-style pin on the four headline numbers |
| X10 | Terminal: `fleet.py:113` citation fixed to this repo's path; runbook rows 352-361 and `D3_tuesday_rearm_audit.json` re-run so hack2 reads manage-only | terminal | D3 audit re-run receipt |
| X11 | **`taskkill` hook**: the Vibe-Trading `_shell_safety.py` pattern (MIT) as a PreToolUse hook in both repos' `.claude/settings.json`; CLAUDE.md rule 6 becomes code | both | a hook test with the four forbidden forms |

**Gate:** CI green on both repos after X; every X row either fixed with its test or CANNOT DETERMINE with a reason.

### H — HUMAN MODE (Mode A): the decision surface and the human book

| # | item | notes |
|---|---|---|
| H1 | **Candidate-list API + page** (read-only): the 3,056 potential-universe scorecards, the tracker watchlist and its status histogram, analyst-target band vs our estimate, the allocator's decision artefacts, sorted and filterable; served from local files by the Docker backend | `learner/potential_universe.py` writes JSONL today; no surface exists. The nightly job must run (both vintages stale at 2026-09-02) |
| H2 | **Journal → thesis bridge**: a conviction decision (`POST /api/pi/conviction/decision`) creates a `Thesis` row (`alpha/human.py`, falsifier ≥ 15 chars, refuses a thesis after its own catalyst) and is sealed into the pre-open prediction book under brain `human:murat` | reuse the existing schema verbatim; add `horizon_sessions`, `min_normal_hold_sessions`, `loss_budget_ref` |
| H3 | **The HUMAN BOOK**: one Alpaca paper account executes Murat's journal rows under a frozen contract (hold fields from the row, typed exits, worst case in dollars printed at seal) | attended flip; see F |
| H4 | **Four-counterfactual regret, nightly**: for every journal row and every machine decision, P&L vs held-to-horizon, held-to-next-review, the engine's pick on the same day, and SPY; exposed as an endpoint and a page beside recall (`NOT_OBSERVED / GENERATED_NOT_RANKED / RANKED_NOT_BOUGHT / BOUGHT_SOLD_EARLY`) | this is B3 §2 with the human as a brain; merges with T2's decision log |
| H5 | **Terminal-state reader**: a read-only sync of the terminal repo's `state/` (seals, fills, refusals, autopsies, learning reports) into a directory the Docker backend serves; no HTTP layer is added to the terminal repo | the website cannot see `aegis-alpha-terminal/state/` today |
| H6 | **Loss budget + drawdown budget** declared per book on the page, with the scoreboard (positions judged, losers so far, budget left) | invariant 19 made visible |

**Gate:** 20 graded journal rows with four counterfactuals each and the recall page live. Process metrics only; no P&L claim under 20 rows ("a receipt, not a result").

### F — FLEET REMAP BY HORIZON AND AUTHORITY (attended; Murat flips)

Six accounts is Alpaca's limit on *accounts*, not on *books*: anything beyond six runs as an internal shadow book with the same contract and zero capital.

| account | role | contract (horizon / min hold / exit family) | loss budget | note |
|---|---|---|---|---|
| `market` (7th account) | **SPY benchmark**, contract `PASSIVE_BETA_v1` (one purchase, exit never, no stop), seeded 2026-08-27 | n/a | n/a | corrected 2026-09-08: the benchmark is NOT hack1; its keys go into `.env` (names only in docs) so `fleet --check-all` and `crossbook` can read it |
| hack1 | survival layer (−35% SPY drawdown emergency rule) | 126 / 21; manage-only | n/a | not the SPY control; holding SPY here would duplicate `market` and trip `crossbook` |
| hack2 | **EARNINGS-REACTION book — the one constantly-active book** (Murat 09-08: "day trading or one system that is constantly active, to test and learn") | v2 contract: 21 / 5 / `THESIS_INVALIDATED` (reversal of the announcement move beyond the name's σ) + `DEADLINE`; stop at 1.3 daily σ of the name; 8 × 6%, gross ≤ 48%; entry at session +1 after each announcement, long the top reaction decile above the `$3m/day` floor | judged at 40 events, 24 expected to lose | R4 §9: the announcement REACTION held in all three eras (t 6.13 / 2.97 / 3.67 at 21 sessions), placebo +40 sessions flips sign (t −2.04), breakeven 39-45 bps; PEAD on the SURPRISE decayed (t 1.47 in 2016-24). Gated on lane D's faithful event-clocked backtest (R4 §12.1); an intraday arm, if wanted, runs as a zero-capital shadow beside it. `DECISIONS_2026-09-08_FABLE_ON_THE_REARM_AND_THE_ACTIVE_BOOK.md` §4 |
| hack3 | **3-MONTH HOLD book** | 63 / 21 / `THESIS_INVALIDATED`, scheduled monthly review | judged at 20, 8 expected to lose | revision family, broad rank-weighted, hysteresis (hold until rank > 2k), institutional-floor names only (the $100k floor loses 9.63%/yr on measured spreads) |
| hack4 | **6-MONTH HOLD book** | 126 / 42 / `THESIS_INVALIDATED`, quarterly review | judged at 15, 6 expected to lose | quality-momentum + drawdown control (the growth champion) at **1×** on the EXTREME personality's 50% drawdown budget (contract row maxDD −46.88%, P(lose half) 0.232; the proxy MC says 0.442). It does not fit the aggressive 35% budget. **Run at 1× under the extreme budget, or decline: Murat's call, with those three numbers in front of him.** 2026-09-08: the current hack4 contract gates its $99k to zero on `requires_catalyst: true`, a clause `murat_rule` lists as not measured — a gate that cannot go green; a **v2 contract without it** (catalyst carried as `UNVALIDATED_INDICATOR`, v1 retired in the supersession log, worst case 5 × 8% × 15% = −6.00%) is frozen and Murat flips |
| hack5 | **HUMAN BOOK** (H3) | per journal row | per journal | replaces the convex options book, which is gated on a states resolution that came back CANNOT_DETERMINE |
| hack6 | **ENSEMBLE broad book** | 42 / 21 / `THESIS_INVALIDATED`, monthly refit | judged at 100 names, half expected to lag | `ensemble_ew|k=100|ew|hold=200|10bps`, the best historical net line (β 1.195, +5.65%/yr t 2.42, era-concentrated); PRODUCT_EXPERIMENT, β printed first |

**Gate:** every contract frozen with `n × notional% × stop%` and `Σ|notional| / equity` printed; hack1 and hack2 stay manage-only until their contracts are frozen; nothing deploys from an agent session.

### I — INVESTOR DATA (free, historical, nobody's WRDS)

| # | item | source | book |
|---|---|---|---|
| I1 | **SEC Insider Transactions bulk sets** 2006 Q1 → (Forms 3/4/5, quarterly ZIPs of tab-delimited tables); PIT on filing date; the **routine-vs-opportunistic** split (same calendar month three years running = routine) | sec.gov/data-research/sec-markets-data/insider-transactions-data-sets | opportunistic-buy book via N1 constructions; 82 bp/month VW in Cohen-Malloy-Pomorski (1989-2007) is the prior, not the claim |
| I2 | **SEC Form 13F bulk sets** 2013 Q2 → ; **best ideas** = each manager's max-tilt position vs its benchmark weight; 45-day lag honoured | sec.gov/dera/data/form-13f | best-ideas book; expect small-cap momentum β and print it |
| I3 | **13D/13G** via EDGAR full-text search (2001 →) and full-index files (1993 →); own cover-page parser (percent of class, item 4 purpose); structured XML only from 2024-12 | efts.sec.gov; Archives/edgar/full-index | replaces the seven-days-in-2026 slice in the event table |
| I4 | Join I1-I3 into the event table with `observed_at = filing acceptance` | N4 | ownership-change and insider-accumulation families |
| I5 | **Murat's own decisions** (H2/H4) as the sixth investor: graded with the same machinery, never trained on under 100 rows | H | the calibration curve of one human |

**Gate:** each source has a coverage-by-year receipt and a PIT test that fails on a lookahead join.

### E — FINISH THE EVENT PIPELINE (the pull died at 83.6%)

| # | item | notes |
|---|---|---|
| E0 | **THE JOINED PANEL, first** (added 2026-09-08): only 21,841 of 993,005 event rows carry both a headline and a permno (9,457 labelled cells, 135 names); 2015-2024 has prices and ~1% news, 2025-2026 has 44-46% news and no CRSP prices — no year has both. (a) permno link for the news rows through CRSP `dsenames` by date; (b) a 2025-2026 daily price panel from Alpaca bars so the news years can be graded; (c) the E3 gate reworded per R4 §14 to name its reading — the earnings family (95-98% coverage every year 1999-2024) is not blocked by the news family's number | R3 + R7 found it independently; a from-scratch encoder on 528k headlines loses to TF-IDF for this reason. Outranks any new mechanism |
| E1 | **Resumable puller**: per-month cursor file, log to disk, PID file, coverage receipt written per month not only at the end, `--universe tradable` (the CRSP-common proxy, thousands of names, batched 20 symbols per Alpaca call), `--start/--end` instead of months-from-today | terminal `scripts/news_backfill.py`; today: no cursor, no log, `fleet` ≈ 156 names, `window_universe.json` absent |
| E2 | Finish the Alpaca leg (2025-01 → 2026-09 gap) and run the Finnhub leg (~6.4 h at 1.1 s/call for 156 names; the tradable universe needs the batched Alpaca leg first) | network job, runs beside compute |
| E3 | **Run the event books**: PEAD, revision-on-event, surprise × reaction, 8-K item families, over the tradable universe through N1's constructions; three-era table where the tape allows; family-max p over every cell | gated on E2 ≥ 90% coverage per year |
| E4 | **GDELT** as the whole-market, Asia-first layer (events + GKG, 15-minute, 100+ languages): the denominator for coverage normalisation and the top-down theme → sector → name pass | VISION §4.1; DeepSeek reads the Chinese/Japanese/Korean items |
| E5 | **Transcripts** (free 2020 →): Q&A scripting (prepared-remarks similarity), evasiveness lexicon, tone; each a typed hypothesis with the paper's direction | Lee 2016; "Straight Talkers"; Loughran-McDonald; Murat's "presentation" hypothesis in testable form |

**Gate:** E3 reports per family: IC, TC, breadth, β, three eras, family size, Holm; a family that survives goes to a PRODUCT_EXPERIMENT book, not a weight.

### R — ERA REPLAY v2 AS MURAT DESIGNED IT (B7, made concrete)

1. **Cadences {1m, 3m, 6m}** × **three eras** (2010-13 EDGAR-only, 2016-19 Alpaca/Benzinga, 2025-26 corpus) × arms {fantasy, real-anon, diary on/off}; weights ≤ 1; cost at every rebalance; the three code-side nulls; the year/company canary on every decision.
2. **Second decider family with no memory of the era**: a ChronoBERT/ChronoGPT yearly checkpoint (free, Hugging Face `manelalab/`) as embedder-plus-linear-head where a decider is too heavy for the GPU; DeepSeek stays the causal-reasoning arm. The gap between them IS the memory measurement.
3. **Leak gate**: the Gao-Jiang-Yan pre/post-cutoff accuracy test on every DeepSeek-scored feature; a feature whose accuracy drops at the model's cutoff is memory and is refused.
4. **Made-up news** is admissible only when a separate call cannot name company or year (canary held 768/768 in v2's blind); dates shifted, sector-unique facts masked, real-anon arm always run beside it.
5. **The hold answer per era**: terminal wealth and rank IC by cadence, reported per era, never pooled. Budget: 10,000 windows ≈ $6.40 at 1,500/300 tokens (`config.LLM_PRICE_PER_MTOK`); cap **$10**; balance $9.28 on 09-06 means Murat tops up first or the run is 5,000 windows.

**Gate:** a cadence result that holds in all three eras is a finding; one era is a regime; both are reported.

### U — THE UNSUPERVISED → HYPOTHESIS → GENOME ROUTE

| # | item |
|---|---|
| U1 | **Event archetype clusters** over the canonical events with the NVIDIA `nemotron-3-embed-1b` embedder (REACHABLE: probe OK, dim 2048); each cluster is labelled once by DeepSeek (≤ $2) and emitted as a **typed hypothesis**: precursor, direction, horizon, family, the archetype's members |
| U2 | Hypotheses enter B8 as genomes through **`research_gym/scope.py::corpse_check`** (the mechanistic comparator), not the five-word `assert_distinct_from_corpses`; code computes every return |
| U3 | **Known-answer**: a planted archetype (a synthetic event family with a planted drift) must be clustered, emitted and recovered by the book path, and a null archetype must read NOISE |
| U4 | The 8-seed self-supervised arm stays inside the ensemble; states stay informational; novelty stays WITHIN_MODEL_NULL until the full corpus is testable |

**Gate:** U3 passes; the first ten emitted hypotheses are graded under the alpha ruler with family = 10.

### T — THE TRADINGAGENTS PORT (decision scaffold; Apache-2.0; nothing touches sizing)

| # | item | source → target |
|---|---|---|
| T1 | **Typed decision rows** (`PortfolioDecision`, `TraderProposal`, `SentimentReport` shapes) with a REVIEW sentinel instead of a silent Hold; **verified-snapshot grounding** clause in the central prompt assembly | `agents/schemas.py`, `dataflows/market_data_validator.py` → `backend/services/llm_analyzer.py` |
| T2 | **Decision log with deferred resolution**: pending tag at decision time, resolved at the row's OWN horizon against CRSP/Alpaca closes, `as_of` gate on lessons, 2-4 sentence reflection | `agents/utils/memory.py`, `graph/reflection.py` → `backend/services/decision_log.py`; serves H4 |
| T3 | **Debate as hypothesis stress-test, A/B**: bull/bear + research manager on the ≤ 5 names the deterministic screen already chose; debate-off vs debate-on on matched candidates; cap $3; PRODUCT_EXPERIMENT | `agents/researchers/*`, `managers/research_manager.py` → `backend/services/thesis_debate.py` |
| T4 | PIT date-window helper + its six regression tests; stale-data refusal sentinel; instrument-identity anchoring from CRSP `comnam`/SIC; message clearing between roles; the DeepSeek capability table | `dataflows/date_window.py`, `stockstats_utils.py`, `agent_utils.py`, `llm_clients/capabilities.py` |

**Not ported:** the three risk personas, free-text sizing, the indicator menu, the fixed 5-day horizon, yfinance fundamentals, the live-clock Polymarket tool, LangGraph, the results table.

**Gate:** T3 answers "does the debate change the five?" If the top five are identical with and without it, T3 closes at $3.

### S — THE STRATEGY INTERFACE (what all five repos have and we do not)

| # | item | source |
|---|---|---|
| S1 | **`Strategy` contract** (universe, signal, construction, hold/exit ladder, sizing, cost model, benchmark, objective, loss budget, licence) and **`run_one(strategy, universe, window, objective) → receipt`**: one command from idea to graded, cost-aware, receipted result; every existing book, farm preset and genome expressed through it | new `backend/strategy/` |
| S2 | **Multiple-testing library** (DSR, PSR, expected max Sharpe, BH-FDR, PBO via CSCV) as one tested module every verdict calls | Vibe-Trading `quantlib/multipletesting.py` (MIT, copy) |
| S3 | **Two model-free leak detectors**: lookahead-analysis (cut the frame before each signal, diff the columns) and recursive-analysis (warm-up drift) | freqtrade design, reimplemented from a written spec (GPL) |
| S4 | **`do_predict` manifold flag** beside every score (dissimilarity index, one-class SVM, DBSCAN; each rejection subtracts one); books gate on `== 1` | freqtrade design, reimplemented |
| S5 | **`breakeven_fee_bps`** on every result row; ADV participation cap with the shortfall carried forward | Vibe-Trading (MIT, copy) |
| S6 | **Exit ladder**: time-decayed `minimal_roi` curve and a ranked exit order (signal → stop → ROI → trailing) in `alpha/contract.py`; **the exit rule as its own tested model** (meta-label the sell) | freqtrade design; Akepanidtaworn et al. 2023 |
| S7 | **Protections as data**: gross `Σ|notional|/equity`, `n × notional% × stop%`, daily loss, cooldown, evaluated in `run_pass` before entries; a guard list that is never empty by default | freqtrade/OpenAlice designs, reimplemented |
| S8 | **Numerai habits in the learner**: per-era scoring, feature neutralisation, era-boosting, and **MMC-style marginal contribution** of every new book against the ensemble ("are its errors different errors?" as a number) | docs.numer.ai |

**Gate:** a new mechanism is one file implementing `Strategy` plus one `run_one` call; the composite book and the growth champion both reproduce their sealed receipts byte-for-byte through it.

## 3. ORDER (gates, not dates)

```
X (hygiene, both repos, CI green)
 ├─ H1 candidate page ── H2 journal→thesis ── H4/T2 regret+decision log ── H5 reader ── H3 human book ── F (attended)
 ├─ E1 resumable puller ── E2 finish ── E3 event books ── E4 GDELT ── E5 transcripts
 ├─ I1 insider ── I2 13F ── I3 13D/G ── I4 join ── books via N1
 ├─ S1 interface + S2 stats lib ── S3-S8 ports ── every book re-expressed
 ├─ T1/T4 grounding ── T3 debate A/B
 ├─ R era replay (after Murat tops up DeepSeek; cap $10)
 └─ U1 archetypes ── U2 corpse_check route ── U3 known-answer ── B8
```

Parallelisable: everything on different branches of the tree. Not
parallelisable: time-dependent forward evidence (H gate, F) and statistics
that do not exist yet (E3 before E2 finishes).

## 4. WHAT DOES NOT CHANGE

PIT discipline · frozen information states · costs never omitted · immutable
policy versions · outcome provenance · no training on future information ·
**no LLM authority over real capital** · no backfilled forward evidence · no
mutation of seeded histories · the alpha ruler for claims and the product
ruler for the aggressive personality · β printed first · the ledger chain is
not repaired silently · sealed receipts are immutable (sidecars) · DeepSeek is
the only API provider; Claude/Opus sessions never call an LLM API · never
kill by image name · `.env` is never moved.

## 5. SERVICES (minimum version of each, unchanged in spirit)

The public tool is Mode A: a candidate list with reasons and a journal that
grades the user against four counterfactuals. The paper's candidate result is
the construction tax (era-stable mechanism, not alpha) and, if E3 or I1
produce one, an event family under family correction. Murat's capital sees
nothing until a CAPITAL_CANDIDATE gate is met, attended.

## 6. STATUS ROWS (append to `ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6; update in place)

| block | status | receipts / notes |
|---|---|---|
| **X hygiene** | **CLOSED 2026-09-08** — X1/X3/X4/X10 (terminal) and X2/X5-X9 (finance) done; X2 is PARTIAL and says so (a uniformly one-session-old mark is not repairable from a `(date, level)` series and is stamped `beta_admissible_as_exposure=False`) | `BUILD_2026-09-07b_Xt_TERMINAL_HYGIENE.md`, `BUILD_2026-09-07b_Xf_HYGIENE.md`. **Two of this roadmap's own X5/X9 glosses were WRONG and the receipts won:** Holm p 0.01543 CLEARS 0.05 — what fails is the DSR deflation bar, so the verdict is *separated after Holm, short of the export bar*; and the long-short β 0.00-0.05 claim is false for SIX cells, not four (momentum -0.0601/-0.0605 as well as ridge 0.205 and encoder 0.425) |
| **F fleet remap** | **DONE and DEPLOYED 2026-09-08** — five books ARMED, hack1 manage-only by declaration | `BUILD_2026-09-08_FLEET_REARM_AND_PREMARKET_OFF.md`, `RECEIPT_2026-09-07_STOP_WIDTH_VS_HOLD.json`. The books were empty for FOUR reasons, three of them invisible from this repo: all six deployed loops carried `--manage-only`, `AAT_LOOP_EXPIRY` was the dead 2026-09-04 date, `AAT_MANDATE_END_UTC` was unset (so a 10:45 ET liquidation every session), and `run_pass` died with `UnboundLocalError: os` on every `--role`-less call. Separately the stop sat INSIDE the noise (hack6 3% = 0.98 daily sd, 56.3% stopped out before session 10), so the minimum hold could never bind. `contract.HORIZON_REMAP` now declares horizon/hold/stop per book, no book has a zero hold, and `worst_case(book, seal=...)` derives `n x notional x stop` from the seal. Worst cases: hack3 -9.96%, hack6 -9.00%, hack4 -6.00%, hack5 -9.00% (true bound -18%), hack2 -3.84% |
| **premarket OFF** | **DONE 2026-09-08** (Murat's instruction) | `agent_loop.PREMARKET_PASSES_ENABLED=False` gates BOTH the digest (the loop's largest DeepSeek consumer) and the opening auction; `--premarket` re-enables; skips are logged. hack4/hack6 degrade to entering at the ordinary pass — `topup_headroom` only gates names already held, so a flat book takes its full sealed weight |
| **H human mode** | OPEN — nothing exists beyond the conviction journal and `Thesis`; candidate list has no surface | `GROUNDING_2026-09-07_WEBSITE_AND_IDEAS.md` A.4-A.5 |
| **F fleet remap** | PROPOSED — attended; hack4 at 1× under the extreme budget or decline is Murat's call | numbers in §2 F |
| **I investor data** | OPEN — sources confirmed free and historical | `EXTERNAL_2026-09-07_LANDSCAPE_WHAT_WE_MISSED.md` D4 |
| **E event pipeline** | BLOCKED on E1 — the pull DIED 2026-09-07 03:18 at 112/134 Alpaca months, Finnhub leg never started, no log, no cursor | grounding report Part 2 (in the validation notes) |
| **R era replay v2 (Murat's design)** | READY — v2 code exists ($0.0025/window); needs balance top-up and the ChronoBERT arm | `FINDING_2026-09-06_ERA_REPLAY_V2.md` |
| **U unsupervised route** | OPEN — embedder REACHABLE (roadmap §6 N5 row was wrong) | `N5_event_compression.json::nemotron_probe` |
| **T TradingAgents port** | OPEN — clone at `C:\Users\mrthn\reference\TradingAgents` (v0.4.1, Apache-2.0) | `EXTERNAL_2026-09-07_FIVE_REPOS.md` §2 |
| **S strategy interface** | OPEN — the highest-leverage item on the external list | `EXTERNAL_2026-09-07_FIVE_REPOS.md` §6-§7 |

## 7. STATUS AFTER THE 2026-09-08 SESSION (nine lanes, Opus 5)

Every row's evidence is a `BUILD_2026-09-0*` doc plus its receipts. Nothing below
is a claim: three lanes are nulls with stated MDEs, and no book was promoted.

| block | status | the one thing to know |
|---|---|---|
| **X hygiene** | **CLOSED** | Two of this roadmap's own glosses were wrong; the receipts won. |
| **F fleet remap** | **DONE + DEPLOYED** | Five books ARMED on `382a6c4`; verified by dry run at 10/10 and 15/15, zero refusals. |
| **premarket OFF** | **DONE** | Both pre-open passes behind one gate, skips logged. |
| **H human mode** | **H1, H2, H4/T2, H5 DONE; H3 NOT** (attended) | The grader is known-answer 29/29 and **zero rows were seeded on purpose** — fabricating decisions would poison the only labelled dataset nobody else has. Gate stands at `have 0 / need 20`. |
| **I investor data** | **I1 DONE; I2/I3 NOT** | 11,522,229 Form 4 transactions, free, 2006-2026. And the first result on it is a **negative**: the CMP spread is illiquidity, not edge (matched +2.7 bp t 0.15; above the $3m/day floor −18.8 bp). |
| **E event pipeline** | **E1/E2 DONE; E3 as a declared SLICE** | The ≥90% gate is met only on reading D (IBES EPS, 95.1-98.2%); the news leg is REFUSED because CRSP ends 2024-12 and dense coverage starts 2025. **Entry convention carried 92.5% of the PEAD headline.** |
| **S strategy interface** | **S1-S8 DONE** | The growth champion reproduces its sealed receipt byte-for-byte. **MMC is the useful number** — see below. |
| **R era replay v2** | **NOT STARTED** | No longer blocked on a DeepSeek top-up: free local inference exists. |
| **U unsupervised** | in flight | — |
| **T TradingAgents port** | **NOT STARTED** | — |
| **new: predictability router** | **MEASURED — one Holm-clean positive, one null** | Predictability IS forecastable (rank IC 0.046→0.142, t 7.03, all four engines). Routing on it does NOT beat always-trade (−1.64%/yr, MDE 5.70%/yr, 0/36 Holm). An oracle buys +26.5%/yr, so the mechanism is real and **our forecast of it dies at the truncation**. |
| **new: news representation** | **NULL, with the structural reason** | A from-scratch self-supervised encoder on 528,223 headlines **loses to TF-IDF in every era**. Labelled overlap is 9,457 cells / 135 names, because the years with coverage have no prices. The year canary leaks loudly (29.75% vs 10%, p<1e-8). |

### The MMC result, and why it is the most useful number here

`COMPOSITE_WEIGHTS` names six signals and coverage is `{"1": 206, "6": 1}` —
99.5% of names carry 12-1 momentum alone. That is THE BOTTLENECK this roadmap
opens with, and until now "are its errors different errors?" had no number.

On 1,456,439 name-months over **312 monthly eras** (n_effective = eras, canon
§58), against a meta-model of `ret_12_1` (the composite as it actually is):

| book | corr | MMC | t |
|---|---|---|---|
| `ret_12_1` (itself) | +0.0313 | **0.00000** | — |
| `ivol_capm_252d` | +0.0313 | **+0.0238** | 3.49 |
| `qmj` | +0.0257 | **+0.0190** | 4.27 |
| `ope_be` | +0.0276 | **+0.0188** | 3.62 |
| `be_me` | +0.0083 | **+0.0172** | 4.74 |
| `at_gr1` | +0.0091 | **+0.0133** | 4.28 |

**`be_me` and `at_gr1` have MMC LARGER than their own correlation** — they hedge
momentum, so neutralising against the ensemble improves them. On this evidence
they are the best candidates for the second independent selector the bottleneck
section asks for. Caveats that bind: correlation space, gross, one panel, and
this is NOT a portfolio result. It earns a pre-registered lane, not a book.

### Two traps this session paid for

1. **`seal-authority` has no Railway volume.** Redeploying it DESTROYS the
   published seal and forces a ~100-minute rebuild. The loops had already synced
   theirs so nothing operational was lost. Redeploy it after an open, never before.
2. **`sync_once` short-circuits on a valid local seal**, so a corrected seal
   reaches the fleet TOMORROW, never today. The only lever that reaches an
   already-sealed book is `STOP_FRACTION_BY_PROFILE`, because a sealed contract
   carries `stop_frac: null` and defers its width to that table.

### U — CLOSED 2026-09-08, and the tape is the binding constraint

`BUILD_2026-09-08_R3_ARCHETYPES.md`. **U3 passed only after failing once, and the
failure is the more useful half.** With the real `nemotron-3-embed-1b` embedder
the planted gate FAILED on run 01 (receipt kept, named
`..._RARE_TOKEN_PLANT_FAILED.json`): the embedder put BOTH planted families into
one cluster of exactly 800 at purity 0.50, because **it separates REGISTER — "is
this a financial headline" — not two rare-token vocabularies.** The plant had to
match the embedder's notion of similarity before the gate meant anything. A
discovery pipeline validated with the wrong plant is validated against nothing.

- **U1**: k=20 by silhouette (0.111). Reseed+resample **ARI 0.540** — partial
  stability. Vocabulary-distinct clusters (options flow, semis supply chain,
  takeover chatter) are stable; "general market movement" boundaries are not. So
  it is **not an archetype set**, and is not reported as one.
- **U2**: 20 typed hypotheses, precursor `(in archetype X) AND (days_since_public
  <= 1)`, entry at the close of the first trading day STRICTLY after
  `observed_at_utc` — **none buys the reaction it predicts**, which is the trap
  that carried 92.5% of the PEAD headline in lane R4. 20/20 ALLOWED_WITH_PARENT_CONTROL
  through `corpse_check`.
- **Grades (family 10, beta first, date blocks)**: exactly one Holm survivor —
  A18 takeover chatter, −0.809 pp/5d, t −3.02, Holm 0.0484. **And it is not an
  archetype effect.** The corpus-level event-minus-control is −0.848 pp, t −3.03
  — the same number, which every archetype inherits. Not a beta artefact
  (β 1.272 vs 1.278). The post-hoc test that actually isolates the archetype
  (event vs OTHER events) gives **0/10 Holm, 0/10 BH, none powered**.

**THE BINDING CONSTRAINT, and it governs every text lane.** Of 993,005 event-table
rows only **21,841 carry BOTH a headline and a CRSP permno** — 91 mega-cap tech
names, 2015-2018, 38 date blocks. IBES rows have no text; 8-K rows have only item
codes and 8% permno linkage. This is the same wall lane R7 hit from the other
side (9,457 labelled cells, 135 names, because dense news is 2025-26 and CRSP
ends 2024-12). **Two independent lanes measured the same gap: we do not have a
joined text-and-return panel, and no amount of modelling substitutes for one.**
That is the highest-value data item on this roadmap, ahead of any new mechanism.

**Open, pre-registered**: does the corpus-level −0.85 pp survive a control
matched on PRE-EVENT VOLATILITY and DOLLAR VOLUME, not just name and month? News
clusters on days already moving, and this design does not remove that confound.
