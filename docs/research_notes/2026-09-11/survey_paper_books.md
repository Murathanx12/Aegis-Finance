# Survey: paper books / N-books-at-cadence feasibility (2026-09-11)

## A. TERMINAL REPO STATE (aegis-alpha-terminal)

- `git log --oneline -10` HEAD: `637e661` "The seal check reads a rotating log buffer..." down to `c413796` N3 execution_authority.
  Chain: 637e661, 5e27c9d (deploy receipt 09-09), 5705648 (fully invested 1x six books), c96d146 (hack4 v2 catalyst gate removed),
  94b292c (hack3 redeploy receipt), 329adb5 (sentinel fix), 1281486 (driver-sector suite guard), 382a6c4 (driver cap fix),
  9519bfd (re-arm fleet), c413796 (N3 execution_authority).
- `git status --short`: 2 modified files (state/labor_day_lab_2026-09-07/*), MANY untracked files under `state/` (predictions,
  autopsy, candidates, tournament, genesis_hack1..6.json, research/analyst_panel/*.jsonl, universe files, etc.) — i.e. a lot of
  state/ output is NOT committed (gitignored or just untracked). Branch: main.
- Most recent HANDOFF/SESSION doc by commit date (not mtime, per house rule): `docs/HANDOFF.md`, last touched by commit
  `2ff6a07` (2026-09-03 23:53:15 +0800), "Correction: the starvation was hack4-only...". The newest docs/ file of ANY kind is
  `docs/RUNBOOK_2026-09-08_REARM.md` (commit 2026-09-08 13:05), which is a runbook not a HANDOFF/SESSION doc. No SESSION_*/
  HANDOFF file postdates 09-03; work since then is tracked only in commit messages (637e661 .. c413796, 09-09/09-10/09-11).
  HANDOFF.md SESSION 36 scoreboard (first ~80 lines): first full tournament day graded from the venue: hack3 +1.19%, hack4
  +1.20%, hack6 +0.76%; Alpaca paper does NOT fill tif=opg (13/15 hack6 auction orders expired untouched); hack4 had nothing
  to submit; solo seal worked end-to-end (sha 4fdc008f12d3b769, 3,129 names, runners hash-verified). Also documents a real
  defect chain that day: hack4 empty (days_to_catalyst unreadable on authority's volume — laptop-only corpus artifact),
  hack3 sealed 10 names but entered NONE of them (forecast-universe reachability bug), hack6 BUR stop id collision (HTTP 422,
  duplicate client_order_id) left a position unprotected.

### The six Alpaca paper books (roles hack1..hack6)
Declared in `alpha/fleet.py` (dataclass `Mandate`, dict `FLEET`). Table also in `docs/FLEET_2026-08-28.md` (per HANDOFF skim
layer, though the fleet.py source is authoritative and newer — v2 dated 2026-09-09 in the caveat text).

| role  | tier  | label                                   | brains              | profile     | universe             | structure       | mandate/contract note |
|-------|-------|------------------------------------------|----------------------|-------------|-----------------------|------------------|------------------------|
| hack1 | RISKY | THEME BASKET (human-heuristic themes)   | theme_basket         | aggressive  | themes                | long_shares      | v2 2026-09-09 (Murat: "make sure paper accounts active/using buying power"); contract HORIZON_REMAP['hack1']: horizon 21, min hold 5, 10% stop, no target; 8x12.5%=100% gross, worst case -10% equity |
| hack2 | SAFE  | DRIFT (measured edge only)              | post_event_drift     | aggressive  | window                | (default)        | contract horizon 5, min hold 2, no target, 8% stop; un-manage-only 2026-09-07; worst case 8×6%×8% = -3.84% equity, gross 48% |
| hack3 | RISKY | TRACKER BALANCED (sealed upside x consensus, k=10) | tracker_portfolio | basket | themes_plus_rule | long_shares | approved 2026-08-31; worst case stop-based -6.64%, gap-to-modelled -23.3% |
| hack4 | RISKY | TRACKER PROFIT-MAX (k=5, sealed, opening-auction entry) | tracker_portfolio | maximum | window | long_shares | approved 2026-08-31 (docs/DECISION_2026-08-31_HACK4_TRACKER_APPROVED.md); catalyst gate removed in c96d146 ("a gate that cannot go green"); worst case stop -3.00%, gap ~-18.4% |
| hack5 | RISKY | CONVEXITY (options only, EV-ranked)     | theme_basket, post_event_drift | convex | themes_with_options | long_call, bull_call_spread | P(profit) ~33-51%/structure; "exists to measure the tail" |
| hack6 | RISKY | TRACKER DIVERSIFIED (k=15, staggered entry) | tracker_portfolio | aggressive | window_plus_themes | long_shares | approved 2026-08-31; worst case stop -2.70%, gap ~-13.0% |

- `COMMON_ENV["AAT_MANDATE_END_UTC"] = "2027-12-31T15:00:00Z"` — moved off the hackathon deadline (2026-09-04) deliberately
  because judging closed but books keep trading; `AAT_LOOP_EXPIRY = "2027-12-31"` fallback (options books derive their own
  next-monthly-expiry). So **mandate end for all six is effectively 2027-12-31**, not a real near-term expiry.
- Hard guards that do NOT change per mandate (module docstring): paper host only, genesis verified, no LLM order path,
  tif=day options, bounded worst case per structure.
- `may_short(role)`: unknown role -> NO. Six declared roles only; an unrecognized AAT_ACCOUNT_ROLE has no mandate.

### Deploy receipts
Live under `state/deploy_receipts/` (per Optimus table + memory index). Confirmed via commit `5e27c9d`: "Deploy receipt
2026-09-09: seal-authority, hack1 and hack4 redeployed for the fully-invested six-book fleet (variables redacted, worst
cases printed, the 2x flip priced and not taken)". (Directory listing pending — see follow-up.)

### Ledger / state (latest known positions/NAV)
- pending — check `state/ledger*`, `state/tracker/`, `state/predictions/*.json` dates.

## B. RESEARCH REPO PAPER-BOOK ABSTRACTION (aegis-finance)

TWO SEPARATE "paper" systems exist in this repo, and neither talks to a real broker:

1. **`backend/strategy/contract.py`** (478 lines) — a frozen, versioned, hashed strategy object, added
   2026-09-07 specifically because "a strategy was spread across an arena book YAML, a frozen contract in
   the terminal repo, a farm preset, a composite weight table and a selector function, with no interface a
   new mechanism had to implement" (docstring). Fields: `Universe, Signal, Construction, HoldRule, Sizing,
   CostModel, Benchmark, Objective, LossBudget, Licence` (PRODUCT_EXPERIMENT/CAPITAL_CANDIDATE/RESEARCH_CLAIM
   enum, `contract.py:61-66`), `engine`, `engine_params`, `parents`, `note`. `Strategy.__post_init__`
   (line 401) REFUSES a non-PRODUCT_EXPERIMENT licence with an empty `note`. `Strategy.fingerprint`
   (line 418) = SHA-256 over the whole dict, 16 hex — "a drifted parameter is a different strategy."
   `CostModel.__post_init__` constructs a `portfolio_farm.Policy` and lets `PolicyError` surface, so
   zero-cost is refused by construction, not a checked field. This satisfies exactly the "frozen strategy
   contract: policy hash, timestamp, inputs, costs, fill convention, objective" language in CLAUDE.md's
   THREE LICENCES table.
   `run_one(strategy, universe, window, objective) -> receipt` (`backend/strategy/run.py:96`) is the single
   entry point — but it dispatches to EXISTING BACKTEST/REPLAY machinery (`learner.growth_lab`,
   `backend.services.portfolio_farm`, `backend.services.arena.policies`); it does not open a live paper
   account or place any order. `Window.sealed=True` is refused without `sealed_authorisation`. This is a
   research/backtest contract, not a live-trading harness.

2. **The PI (portfolio-intelligence) system** — `backend/data/*.yaml` lane registries + a live scheduler +
   sqlite. Multiple lane files, none unifying: `arena_books_v1.yaml` (10 books: `ENGINE_BASELINE_v1,
   RISK_SIZED_v1, WINNER_EXEMPT_v1, ANTI_SIGNAL_v1, LLM_PERCEPTION_v1, LLM_EVENTS_v1, CURRENT_BEST_v1,
   AGGRESSIVE_TOP5_v1, DIVERSIFIED_TOP20_v1, PROFIT_ALLOCATOR_v1` — the "ten arena books, all
   composite_top_k over one signal" from CLAUDE.md's BOTTLENECK section), `paper_portfolios.yaml` (4
   reference lanes: `aggressive, balanced, balanced-ew-control, conservative` — confirmed as the only rows
   in the live local `paper_portfolios` sqlite table), `book_lanes.yaml` (Murat's real 12-name book, two
   lanes: `mirror` optimizer=hrp monthly rebalance, and `conviction` which only moves on logged
   `personal_decisions`), plus `shadow_portfolios.yaml`, `conservative_atr_lanes.yaml`,
   `smallmid_quality_lanes.yaml`, `tsmom_xa_lanes.yaml`, `theme_baskets.yaml`, and
   `copy_lab/{copy_lab_lanes_v1,teacher_copy_lanes}.yaml`. **Total across all files: on the order of
   dozens of lanes, not thousands** — this is the real ceiling on "how many lanes exist now."
   NAV marking: `backend/services/portfolio_intelligence/scheduler.py` (APScheduler,
   `SQLAlchemyJobStore` at `backend/data/apscheduler_jobs.db`) runs `_daily_check` (CronTrigger 16:30 ET,
   `pi_daily_check`) and `_hourly_mtm` (16:00-19:30 ET catch-up retries, `pi_hourly_mtm`) — i.e. the
   existing cadence is effectively ONE daily close mark plus retry windows, not arbitrary per-book cadences.
   Price source is whatever `nav_reconstruction.py`/the mark job pulls (yfinance-family, consistent with the
   rest of the repo). History: sqlite `backend/data/aegis_pi.db`, table `paper_nav` (`portfolio_id, date,
   nav, config_version, computed_at`, PK `(portfolio_id, date)`, `backend/db.py:191-200`), archived
   historically under `paper_nav_archive_20260726` when schema drifted. Related tables in the same db:
   `paper_portfolios` (4 rows locally), `paper_positions` (374 rows), `paper_trades` (0 rows locally),
   `personal_decisions` (1 row), `decision_outcomes` (0 rows), `rule_experiments` (16 rows),
   `pit_observations` (1,299 rows). NOTE: local `paper_nav` has 0 rows — this dev-machine sqlite copy is
   NOT the live Railway one; do not read "0 NAV marks" as "NAV marking is broken," only as "this local
   file is not the record of truth" (the CLAUDE.md caution about absence-of-a-local-object applies here
   directly).

### Does anything create a book from a natural-language request or LLM output?
Grepped `copilot`, `investment_committee`, `pm.py`, `llm` near `portfolio`. Found:
- `backend/routers/copilot.py` + `backend/services/copilot.py` (524 lines) — a Q&A function-calling copilot
  ("How does AAPL's style box compare to MSFT?", "Run a 60/40 backtest…"). Its tool catalogue
  (`_tool_market_status, _tool_stock_analysis, _tool_style_box, _tool_factor_grades, _tool_short_interest,
  _tool_revisions, _tool_crash_prediction, _tool_sector_rotation, _tool_allocation_backtest,
  _tool_compare_allocations, _tool_market_treemap`) has **no tool that creates or mutates a portfolio** —
  it is read-only/backtest-only, DeepSeek-or-Claude-agnostic wire format.
- `backend/routers/investment_committee.py` + `backend/services/investment_committee.py` (556 lines) —
  `build_page` / `funnel_state` / `compose_book`: composes a recommended "core + evidence-scaled tilts"
  page from the nightly signal funnel and `portfolio_factory.py`. This is a **report/recommendation page**,
  not a live paper book instantiation, and it is not driven by a free-text prompt ("very high-risk, cheap,
  industry-focused") — it works off pre-registered signal archetypes (`archetypes.py`) and capital tiers
  (`capital_frontier.py`), not natural language.
- `backend/routers/pm.py` (188 lines) — ALL GET endpoints (`/book, /book/validate, /revisions/{ticker},
  /daily, /name/{ticker}, /wealth, /catalysts, /journal`) plus `POST /journal/record` and `POST /snapshot`
  (both append to a decision journal / NAV snapshot, not create-a-book).
- **Conclusion: NOT FOUND.** No code path in this repo turns a natural-language ask ("build me a
  high-risk, cheap, industry-focused portfolio") into a new paper book/lane. Every lane above is declared
  as YAML/dataclass by a human/session, not synthesized from an LLM instruction at request time.

## C. THE "WHAT WE THOUGHT VS WHAT HAPPENED" LEDGER (aegis-finance)

`backend/services/belief_state.py` (977 lines) is exactly this ledger, and its docstring names the gap
directly: "Murat wants Optimus to work as a brain that talks back and forth with an agent about what to
buy... there has been no shared object to talk about... no forecast that can later be scored."

- **Files**: `backend/data/optimus/predictions.jsonl` (24,828 rows) and `backend/data/optimus/beliefs.jsonl`
  (37 rows), paths come from `LEDGER_DIR = config.OPTIMUS_LEDGER_DIR = DATA_DIR / "optimus"`
  (`belief_state.py:82-84`).
- **Schema** (`PredictionRecord`, `belief_state.py:217-266`): `prediction_id, ticker, specialist,
  observable (return_sign|beats_benchmark|abs_move_exceeds|drawdown_exceeds), horizon_days, probability,
  threshold, benchmark, made_at, resolves_after, thesis, counter_thesis, next_observable, model,
  model_version, prompt_hash, input_snapshot_hash, schema_version`, plus an optional belief-change triple
  (`prior, posterior, belief_change`), `arm` (experimental arm label), `session_as_of`,
  `evidence_population`, `ledger_id`, and fields filled ONLY at resolution: `resolved_at, void_reason,
  outcome, brier, resolution_detail`. `make_prediction()` builds one; `record_outcome()` (per docstring)
  returns `None` always — "no caller can branch on a write," i.e. the LLM cannot see or act on its own
  grade.
- **How a row gets written**: `make_prediction(...)` + `append(records, path)` (append-only jsonl).
  Sample rows are DeepSeek (`model: "deepseek-chat"` / `"deepseek-v4-flash"`) forecasts on individual
  tickers (NTLA, BHVN, WFC…) with explicit thesis/counter-thesis text — this is the LLM-hypothesis→typed
  claim pipeline the mission statement asks for ("instinct as a typed hypothesis").
  Local `predictions.jsonl` sample rows top out around 2026-08-27; **0 of 24,828 local rows have
  `outcome != null`** (6 are void) — either the local file is stale relative to the live Railway one, or
  grading has not run against this copy; do not read this as proof the grader is broken (same "absence of a
  local object" caution as above).
- **Grading job**: `pi_ledger_resolve` (`backend/services/portfolio_intelligence/scheduler.py`), added
  because "belief_state.py shipped resolve_one/resolve_all with NO caller — no job, no route, no script"
  (classic silent-fragility house bug). It's registered as a daily 16:30 ET job
  (`scheduler.py:181-195`), calls `backend.services.ledger_resolver.resolve_due()` →
  `belief_state.resolve_all(prices, ...)`.
- **What it grades against**: `resolve_one(rec, prices, today)` (`belief_state.py:609-686`) — real price
  series (`backend/data/conviction_prices.csv` frozen replay CSV first, else fresh yfinance adjusted
  closes per `ledger_resolver.py` docstring), windowed to `horizon_days + 1` bars from `made_at`. Grades:
  `return_sign` -> sign of realised return; `beats_benchmark` -> return vs named benchmark;
  `abs_move_exceeds` -> |return| > threshold; `drawdown_exceeds` -> max drawdown > threshold. Writes
  `outcome` (0/1) and `brier = (probability - outcome)^2`. A record whose ticker/benchmark never appears in
  the price frame is logged and left permanently unresolved rather than silently dropped. `calibration()`
  and `ledger_health()` (with a `max_quiet_days` staleness canary) exist on top of this.
- **`docs/TRIALS/`**: 54 pre-registered trial files (TRIAL-*.md), one per hypothesis (e.g.
  `TRIAL-H5-event-learner-five-session.md`, `TRIAL-R2-monthly-news-digest-read.md`,
  `TRIAL-FORECAST-LEDGER-model-vs-street.md`) — these are the CANON §6 pre-registration objects, a level up
  from individual prediction rows: hypothesis + primary metric + decision rule + earliest decision date.
- Separately, `learner/evidence_memory.py` + `backend/data/optimus/learner/evidence_memory.jsonl`
  (102,029 lines) is a DIFFERENT, larger, older ledger (Optimus's general evidence corpus, not
  belief_state's typed forecast ledger) — do not conflate the two; they have different schemas and
  purposes.

## D. SCALE QUESTION — cheapest path to "N paper books at declared cadences, each a frozen contract, each graded against its own control"

**Reusable today:**
- `backend/strategy/contract.py` `Strategy` dataclass — already IS "one frozen, hashed, versioned contract"
  with a licence field; extend `Universe`/`Signal` to accept an LLM-authored spec (e.g. "high-risk, cheap,
  industry-focused") translated into `Construction`/`Sizing`/`HoldRule` fields, not prose.
- `backend/strategy/run.py:run_one` — reuse for the backtest/replay leg of any new book before it goes live.
- `backend/services/belief_state.py` + `pi_ledger_resolve` — reuse WHOLESALE as the "what we thought vs
  what happened" instrument per book: each book's entry/hold/exit decision becomes a `PredictionRecord`
  with its own `resolves_after`, graded automatically by the existing daily job against real prices.
- `backend/db.py` `paper_nav` / `paper_portfolios` / `paper_positions` tables — the schema already supports
  an arbitrary number of `portfolio_id`s at daily granularity; this is the cheapest existing "NAV marked
  against real prices without touching a broker" surface, i.e. the pattern that scales to thousands, NOT
  the terminal repo's real-Alpaca-account pattern.
- `alpha/fleet.py` `Mandate` dataclass (terminal repo) — good REFERENCE for what fields a mandate needs
  (brains, universe, sizing envelope, structure kinds, worst-case printer via `loss_budget_worst_case`),
  but it is architecturally ONE-BOOK-PER-REAL-ALPACA-ACCOUNT (each role needs its own
  `AAT_HACKn_KEY_ID`/`AAT_HACKn_SECRET_KEY`, `alpha/fleet.py:224-225` SECRETS tuple) — this does NOT scale
  to thousands; six accounts already required six manual Alpaca account creations and six Railway services.
- `backend/services/portfolio_intelligence/scheduler.py` APScheduler + `SQLAlchemyJobStore` — reuse the
  scheduling machinery, but its current jobs are hardcoded cron entries (`pi_daily_check`,
  `pi_hourly_mtm`, etc.), not a data-driven "N books x cadence" table.

**Missing pieces:**
1. A data-driven cadence scheduler: today every PI job is a hand-added `CronTrigger` in one file; nothing
   reads "book X wants a check every 30 minutes, book Y every 3 months" from a table and fans out.
2. A programmatic Strategy-from-spec builder: nothing turns a short natural-language ask into a `Strategy`
   object (contract.py has no LLM-facing constructor); this is the actual missing link for "tell an AI
   agent to build me a portfolio."
3. A per-book matched control at construction time: `contract.py`/`run_one` support a `Benchmark`, but
   nothing here auto-generates a shuffled/random-genome NULL twin per book the way the terminal repo's
   RW1/RW2 null-genome or the farm's placebo constructions do (`docs/AEGIS_STRATEGIC_INVARIANTS.md`,
   memory: "a null owes TWO tests").
4. A "thousands of lightweight simulated books" NAV engine distinct from the six real-Alpaca-account
   books — needs to mark-to-market against real prices on its own cadence WITHOUT opening a broker
   account per book (extend `paper_nav`/PI machinery, do not extend `alpha/fleet.py`'s per-account model).
5. A single UI/API surface in the desktop dashboard that lets the user issue the natural-language request
   and see the resulting frozen contract before it starts accruing (mirrors `seed-a-lane` skill's "human
   flips the flag" discipline, but for a much higher volume of proposals).
6. Cost/zero-cost handling at whatever new fan-out point creates the Strategy — `CostModel` already refuses
   zero-cost by construction, so this is wiring, not new logic.
7. A backfill-safe identity/idempotency scheme so a "book" created twice from a similar prompt does not
   silently double-count discovery (cf. the 09-10 "replay" lesson in the terminal repo: same-seed reruns
   look like new discovery but are not).

**Invariants that constrain this directly (CLAUDE.md / AEGIS_STRATEGIC_INVARIANTS.md):**
- "**A new mechanism arrives as its own `PRODUCT_EXPERIMENT` book, never as a weight in `arena_composite`**"
  (CLAUDE.md, THE BOTTLENECK) — each LLM-specified portfolio must be its OWN `Strategy`/lane, never folded
  into an existing composite.
- **THREE LICENCES table** — a `PRODUCT_EXPERIMENT` book needs "a frozen strategy contract before the
  first decision: policy hash, timestamp, inputs, costs, fill convention, objective. No significance gate,
  no 24-month floor" — this is PERMISSIVE for exactly the "thousands of books, explore dirty" use case, as
  long as each book freezes its contract before trading and never mutates it afterward ("once a candidate
  enters forward paper, its version is frozen").
- **Four things that never relax even in PRODUCT_EXPERIMENT**: no information acted on before it was
  public; no target leakage; costs never omitted (`zero_cost_diagnostic` must be explicit and travels onto
  every result row); frozen version once in forward paper.
- **No LLM authority over real capital** (CLAUDE.md THREE LICENCES "Does NOT relax" list) and, in the
  terminal repo, "no LLM order path" is a HARD GUARD that does not change per mandate (`alpha/fleet.py`
  module docstring) — an LLM may PROPOSE a portfolio spec; a deterministic engine must be the one that
  turns it into sized orders/weights, exactly the "LLM proposes and forecasts; the engine computes and
  allocates" firewall already built into `belief_state.py`.
- **Session-start protocol rule 4** (CLAUDE.md): before any sizing/stop/cap change, print the worst case
  in dollars for the largest admissible book (`n names x notional% x stop%`, `Σ|notional| / equity`) — a
  thousand-book fan-out needs this printed in aggregate across the whole fleet, not per book, or the
  fleet-level worst case is invisible (exactly the "12 names x 25% = 300% gross" 28-Aug lesson).
- **A grep/mtime-shaped guard is a broken guard**; any new gate for admitting a book (e.g. "is this book's
  contract frozen?") must DERIVE the answer or say CANNOT DETERMINE, never silently report 0/N passing.
- **RESULTS SCOREBOARD discipline**: any handoff about this work should open with best historical net
  strategy vs market, best forward paper strategy, independent selector count, farm candidates
  tested/promoted, LLM spend and cost per gradeable output — scaling to "thousands of books" multiplies
  the LLM-spend line, which the mission's rule 5 ("maximise information per dollar, not minimise API
  calls," scored as `P(changes roadmap) x value - cost`) directly governs.
