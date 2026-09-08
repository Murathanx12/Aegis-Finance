# HANDOFF — 2026-09-07 — Fable 5.1 → Opus 5 builder sessions — TWO MODES, ONE SYSTEM

**Mandate:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` (read it whole; §2
has the blocks, §3 the order). Why: `REVIEW_2026-09-07_FABLE51_ON_GPT_AND_MURAT.md`.
Evidence: the four `EXTERNAL_/VALIDATION_/GROUNDING_2026-09-07_*.md` files.
Canon: `docs/INDEX.md` TIER 0, CLAUDE.md rules 1-8. If the Optimus MCP is
down (it was this session), read `docs/INDEX.md` and proceed; note it in the
build doc.

**Murat runs these sessions step by step and will have each session spawn its
own agents. Spawn agents on Opus 5 (`model: opus`), not Fable: Fable sessions
hit the account's rate limit on 2026-09-07 and killed three agents mid-task.
The reviewer (Fable) reads the build doc afterwards.**

## 0. Session contract (every session, every agent)

1. Start: `python -m scripts.ci_watch --n 1`. **Red CI on HEAD is the first
   task.** Then `git status` in both repos; if a tree is dirty from a previous
   agent, commit or stash it before anything else. **No two writers on one
   tree:** one agent per repo per lane, or worktrees.
2. Never: push, seal, order, deploy, change a Railway variable, move `.env`,
   print a key value, repair the ledger chain, edit a sealed receipt (sidecars
   only), call any Anthropic/OpenAI API, or kill a process by image name
   (`taskkill /F /IM`, `pkill python`). Kill by a PID you wrote down.
3. LLM: DeepSeek only, under a per-job dollar cap declared in the receipt and
   measured as the delta of the ledger; report spend to the cent and the
   provider balance before/after. Caps in the tables below.
4. Every receipt: `receipt_provenance.attach` (argv, resolved config, SHA-256
   of every input opened), β first on every book, family size + family-max p
   + DSR + MDE + three-era table on every edge claim; a check that did not
   run is not a check that passed; a refusal is a finding.
5. Tests: finance `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300`;
   terminal ONLY `python run_tests.py`. Both suites at the end of every
   session; counts in the build doc. **`cmd | tail` eats the exit code.**
6. Memory: 6 GB free-memory guard before any heavy job; lab runner or one
   standalone job, never both.
7. Commit locally per item with the item id in the message; Murat or Fable
   pushes. Nothing here is a claim; every edge is PRODUCT_EXPERIMENT unless
   the receipt says otherwise.
8. Build doc `docs/BUILD_TWO_MODES_<session>_2026-09-XX.md`, ≤ 2 pages,
   **RESULTS SCOREBOARD first** (best historical net vs market · best forward
   · selector count · cells tested/promoted · new actionable finding ·
   external drag · LLM spend), then lane by lane, then **claims for Fable to
   attack** (5-10), then test counts, then what did NOT work and why.
   Update roadmap §6 in place, session memory, `MEMORY.md` (one line).

## 1. SESSION ONE — hygiene and foundations (parallel agents, two repos)

| agent | repo | lane | deliverable | test / gate | cap |
|---|---|---|---|---|---|
| **Xf** | finance | X2, X5-X9 | stale-NAV re-mark at the official close with STALE stamp; `verdict_from` SEPARATED_NOT_SURVIVING; ERAS callers; one price table; `STATE_SEMANTICS` text; the nine stale doc numbers corrected in place (list in roadmap X9) | Dimson lag test; battery B1 planted edge no longer NOISE; a test that fails on two rate tables; CI green | $0 |
| **Xt** | terminal | X1, X3, X4, X10 | clock-skew guard (venue `/v2/clock` vs local, > 5 min ⇒ `CLOCK_SKEW` refusal, exits unaffected); Sunday fixtures (venue-open fixture, `considered=0` becomes a typed refusal); `VENUE_REJECTED`; fleet.py citation; runbook rows 352-361 and the D3 audit re-run | `tests_smoke_labor_faults` case 6 flips; the four Sunday suites pass on a closed-venue fixture; D3 receipt shows hack2 manage-only | $0 |
| **Xh** | both | X11 | `taskkill`/`pkill` PreToolUse hook from Vibe-Trading `_shell_safety.py` (MIT) in both `.claude/settings.json` | a hook test with the four forbidden forms; CLAUDE.md rule 6 cites the hook | $0 |
| **E1** | terminal | E1, E2 | resumable news puller: per-month cursor, log file, PID file, per-month coverage receipt, `--start/--end`, `--universe tradable` (CRSP-common proxy exported from finance as a symbol list, batched 20 per Alpaca call); then finish the Alpaca 2025-01 → 2026-09 gap and start the Finnhub leg detached with its PID written down | a kill-and-resume test on a two-month window; coverage-by-year receipt; the finance `n4_event_table --build` re-join | $0 (no LLM) |
| **I1** | finance | I1 | SEC Insider Transactions bulk loader (2006 Q1 →, quarterly ZIPs), PIT on filing acceptance, permno link via CIK→ticker→CRSP, routine-vs-opportunistic classifier, coverage-by-year receipt, joined into the event table as `insider_*` families | PIT test that fails on a lookahead join; a known-answer on a synthetic routine insider; guard test that no Form 4 row is fabricated stays green | $0 |
| **S1** | finance | S1, S2 | `backend/strategy/`: the `Strategy` contract and `run_one(strategy, universe, window, objective) → receipt`; the composite book and the growth champion expressed through it and reproducing their sealed receipts byte-for-byte; the multiple-testing library ported from Vibe-Trading `agent/src/quantlib/multipletesting.py` (MIT, header kept) with its gotchas as tests | byte-identical reproduction of two sealed receipts; DSR/PBO from the library equal the receipts' values to 1e-9 | $0 |
| **H1** | finance | H1 | `/api/candidates/*` (scorecards, tracker, band vs estimate, allocator artefacts) served from local files, and the page; runs under `docker compose up` with no Railway; the nightly potential-universe job re-run so the vintage is today's | endpoint tests; `npx next build`; a screenshot in the build doc | $0 |

**Session-one gate:** CI green on both repos; both suites green (report the
counts); E1's puller running detached with a PID; S1 reproduces two sealed
receipts; H1 renders today's vintage. What did not finish is a row in the
build doc, not silently dropped.

## 2. SESSION TWO — the human loop and the grounding ports

| agent | repo | lane | deliverable | gate | cap |
|---|---|---|---|---|---|
| **H2** | both | H2 | conviction decision → `Thesis` row → prediction-book seal under brain `human:murat`; new row fields `horizon_sessions`, `min_normal_hold_sessions`, `loss_budget_ref`; a `late_entry` row is graded from its true time | a thesis after its own catalyst is refused; seal verifies | $0 |
| **T2/H4** | finance | T2, H4 | `decision_log.py` (pending → resolved at the row's own horizon against CRSP/Alpaca closes, `as_of` gate, 2-4 sentence DeepSeek reflection) and the four-counterfactual regret grader (held-to-horizon, held-to-review, engine pick, SPY) for human and machine rows; endpoint + page beside recall | grader known-answer on synthetic rows; reflection cost per row logged | $1 |
| **H5** | both | H5 | read-only sync of terminal `state/` (seals, fills, refusals, autopsies, learning reports) into a directory the backend serves | a test that the sync never writes back | $0 |
| **T1/T4** | finance | T1, T4 | typed decision rows with REVIEW sentinel; verified-snapshot grounding clause in `_call_llm`; PIT date-window helper + the six ported tests; stale-data refusal sentinel; identity anchoring from CRSP `comnam`/SIC | the language pin and refusal counters still fire; a fabricated-price probe is caught | $0.50 |
| **I2** | finance | I2, I3 | 13F bulk (2013 Q2 →) best-ideas book through N1 constructions, 45-day lag; 13D/13G via EDGAR full-text + index with a cover-page parser; both joined to the event table | coverage receipts; β printed first on the best-ideas book | $0 |
| **U1** | finance | U1-U3 | archetype clusters with the nemotron embedder (probe first; batch 50; ≤ $2 for cluster labels), typed-hypothesis emitter, route through `research_gym/scope.py::corpse_check` into B8 genomes, planted-archetype known-answer | U3 passes; ten emitted hypotheses graded with family = 10 | $2 |
| **D** (added 09-08) | finance → terminal | F hack2 | **The constantly-active book.** (1) The faithful event-clocked backtest of the earnings-REACTION signal (R4 §12.1): enter session +1 after each announcement, long the top reaction decile above the `$3m/day` floor (add a dollar-volume column to `R4_earnings_events.parquet`), hold 21, 25 bps a side, β first, three eras, the +40-session placebo re-run on the SAME book; join a free announcement timestamp so `e1/e2` collapses to a number. (2) If the book's β-matched line is positive in ≥ 2 eras, draft hack2's v2 contract exactly as `DECISIONS_2026-09-08_…ACTIVE_BOOK.md` §4.2 (21 / 5 / σ-stop / 8 × 6% / loss budget 40:24) with the worst case printed, plus a zero-capital intraday shadow arm (opening-range or first-hour reaction) under the same discipline. Nothing armed; Murat flips | the placebo flips sign on the book; worst case in dollars on the seal | $0 |
| **E0** (added 09-08) | finance | E0 | the joined text-and-return panel: permno link for news rows via CRSP `dsenames` by date; 2025-2026 daily price panel from Alpaca bars; the E3 gate reworded per R4 §14; coverage-by-year receipt with BOTH readings | a PIT test on the link; a year with both prices and ≥ 40% news coverage exists | $0 |

## 3. SESSION THREE — Murat's replay, the debate A/B, the fleet (attended)

| agent | repo | lane | deliverable | gate | cap |
|---|---|---|---|---|---|
| **R** | finance | R1-R5 | era replay v2 at cadences {1m, 3m, 6m} × three eras × arms; ChronoBERT/ChronoGPT yearly checkpoint (Hugging Face `manelalab/`) as the memory-free decider arm (embedder + linear head if the GPU cannot hold a decider); Gao-Jiang-Yan pre/post-cutoff test as a gate; hold answer per era | canary held; per-era tables; nothing pooled | **$10, only after Murat tops up the balance** ($9.28 on 09-06) |
| **T3** | finance | T3 | bull/bear + research manager as hypothesis stress-test on the screen's top five, debate-off vs debate-on on matched days | if the five are identical with and without, close at cost | $3 |
| **E3** | finance | E3 | PEAD / revision-on-event / surprise × reaction / 8-K item families over the tradable universe through N1 constructions, three eras where the tape allows | ≥ 90% coverage per year first; family-max p over every cell | $0 |
| **S3-S8** | both | S | leak detectors (spec-reimplemented), `do_predict` manifold flag, `breakeven_fee_bps`, exit ladder in `alpha/contract.py`, protections as data, Numerai habits (per-era scoring, neutralisation, era-boosting, MMC) | each with a known-answer; the composite reproduces through `run_one` after every port | $0 |
| **F** | terminal | F | contract drafts for the six roles in roadmap §2 F, each with hold fields, loss budget, `n × notional% × stop%` and `Σ|notional|/equity` printed; a dry run per book; **nothing deployed** | Murat flips per the runbook; hack4 at 1× under the extreme budget or declined is his call | $0 |

## 4. Review-back protocol

Fable reads, in this order: the scoreboard; the claims-to-attack list; the
receipts named in the build doc (not the doc's numbers: **the receipt wins**;
this session found eight places where our own docs disagreed with their
receipts); the test counts; the "what did not work" section. A number in
prose with no receipt is struck. A gate reported green is re-derived from its
receipt before it is believed.

## 5. Things a builder will be tempted to do and must not

- Fold a surviving family into `arena_composite` as a weight. It arrives as
  its own PRODUCT_EXPERIMENT book or not at all.
- Quote 29.27× beside 3.66×. They are at different cost rates.
- Treat "the pull is resumable" as a cursor. There is none until E1 lands.
- Read `learner/evaluate.ERAS` as the era grid. Call `long_eras()`.
- Believe a shadow book's β from a stale mark.
- Let any LLM output reach a size, a stop or an order. It reaches a row.
- Report a red suite as "pre-existing". Four terminal suites have failed on
  Sundays since 09-06; X3 owns them.
