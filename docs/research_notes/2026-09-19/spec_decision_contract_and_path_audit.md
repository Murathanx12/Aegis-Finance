# The decision path, traced end to end, and a spec to close the gap

**2026-09-19. Read-only audit.** Murat's complaint, verbatim: *"We are not
making any decisions... it shows the stock forecast, the analyst results, but
it doesn't make any decisions on what it should buy... When I was talking to
the local model, what does the agent think is a good buy? It did not say."*

This traces both repos with file:line citations, classifies every "no trade"
this audit could find, and specs the smallest change — a **Decision Contract**
— that closes the seam between the numeric engines and the two LLM surfaces.

---

## 0. One-paragraph answer

The system computes rankings and runs paper books, and it separately runs two
LLM surfaces — but **no LLM surface is ever handed the ranked BUY list**, and
**the one place that does compose an actual position (`investment_committee.
compose_book`) is never called by either LLM surface's tool catalogue.** The
copilot (`backend/services/copilot.py`) has ten tools and none of them is "give
me today's ranked buys." The desktop Ask assistant
(`backend/routers/control_ask.py`) is explicitly forbidden from sizing
anything — that is in its own system prompt. So when Murat asks the local
model "what's a good buy," the model has no tool that returns one, and its own
instructions say it has no authority to decide one even if it could compute it.
Meanwhile the execution repo *does* place paper orders daily across six books,
completely out of the LLM's sight, and reports why not in a well-built refusal
taxonomy the two research surfaces never read either. The gap is not that
nothing decides — it's that the two things that decide (the ranking/IC engine,
and the paper fleet) never hand their output to the two things Murat talks to
(the copilot, the desktop Ask).

---

## 1. Research repo: where forecasts/rankings are produced, and where the LLM stops short

### 1.1 The engine side actually decides sizes — it just isn't shown to the LLM

`backend/services/investment_committee.py` is the one place in the research
repo that composes an actual position list at a capital level:

- `compose_book()` (`investment_committee.py:295-430`) takes ranked
  recommendations, applies `_tilt_size()` (`:288-292`, verdict × confidence ×
  cap from `config.IC_SINGLE_NAME_TILT_CAP`), checks capacity
  (`CF.capacity_for`, `:343-350`), and returns **weights, dollars, and share
  counts** (`:404-417`) — "evidence-led" tilts on a benchmark core, with a
  `reason` string and a `kill_condition` per name (`_kill_condition`,
  `:60-83`).
- `committee()` (`:482-556`) is the full page: it explicitly refuses to
  print an expected return ("NOT CALIBRATED for any tilt name" — `:537-542`)
  but it DOES print position weights, dollar amounts, and share counts. This
  is the closest thing in the research repo to "what would you buy, at what
  size" — and it deliberately never resolves the "why"/"what would make you
  wrong" fields into one contract object; `kill_condition` and `reason` are
  separate strings on separate objects (`opportunities` vs `books`).
- Router: `backend/routers/investment_committee.py:18-21`,
  `prefix="/api/ic"`.
- Frontend: `frontend/src/app/investment-committee/page.tsx` renders this.

**So the IC page is a decision, in the research repo's own terms — it is just
never read by anything that talks to Murat in natural language.**

### 1.2 The "agent X" document is the Internet Investigator (IIF-1), and it is forbidden from buying by design

`docs/IIF1_PRE_NIGHT_1_CHECKLIST.md` is INTERNET-INVESTIGATOR-FWD-1, the
autonomous-investigation forecast trial. It matches Murat's description
exactly — "shows the stock forecast... but doesn't make any decisions":

- Line 82-88: `CLAIM_LANGUAGE` (frozen in
  `Aegis module/scripts/iif1_read_gate.py`) **refuses a verdict line
  containing "alpha, Sharpe, outperform, tradable, profitable, skill, stock
  picking."** The trial "forecasts no return and holds no position, so no
  such claim is available to it at any n."
- The permitted claim (line 84-85) is only: *"autonomous investigation
  improves magnitude/volatility forecast calibration relative to an engineered
  numerical snapshot."*
- `backend/services/investigator_night.py` and
  `backend/services/iif1_features.py` produce the forecasts;
  `Aegis module/scripts/iif1_read_gate.py` is the gate that stops any of it
  from becoming a buy verdict before n=40/80/120 reads.

This is a **deliberate design choice, not a bug**: IIF-1 is a
calibration trial under `RESEARCH_CLAIM`-adjacent discipline, and it is
*supposed* to stop short of a decision. The gap is that nothing downstream of
it (or of the IC page) ever gets handed to the surface Murat actually talks
to.

### 1.3 The two LLM surfaces, and their system prompts, verbatim

**A. The web copilot — `backend/services/copilot.py`**

- `TOOLS` catalogue (`:148-235`): `get_market_status`, `analyze_stock`,
  `get_style_box`, `get_factor_grades`, `get_short_interest`,
  `get_revisions_trend`, `get_crash_prediction`, `get_sector_rotation`,
  `backtest_allocation`, `compare_allocations`, `get_market_treemap`. **No
  tool calls `investment_committee.committee()`, `compose_book()`, or
  `REC.score_candidates()`.** The LLM can describe a stock's factor grades but
  cannot retrieve the engine's own ranked BUY/WATCH list or a sized position.
- System prompt (`:238-247`), quoted in full because the forbidding clause is
  the last sentence:

  > "You are Aegis Copilot, a quantitative finance assistant... Always call
  > tools before committing to numeric claims... Cite numbers you received
  > from tools and label them as 'Aegis data'. Never invent tickers... **This
  > tool is educational; always end with a one-line reminder that Aegis is
  > not financial advice.**"

  Nothing here forbids a buy recommendation in principle — but there is no
  tool that could produce one, so the instruction is moot in practice.

**B. The desktop "Ask" assistant (talks to the local model) —
`backend/routers/control_ask.py`**

This is very likely the "local model" Murat means — it is the desktop app's
offline assistant over `llama_server`.

- System prompt (`ASK_SYSTEM`, `control_ask.py:43-49`), quoted in full:

  > "You are the Aegis desktop assistant. You READ receipts and explain them.
  > **You have no authority: you cannot run jobs, seal books, arm lanes, size
  > positions or place orders, and you must never imply otherwise.** Every
  > number you state must appear in the context you were given; if a number
  > is not there, say you do not have it rather than estimating..."

  This is an explicit, structural prohibition on sizing anything — not a
  suggestion the model might ignore, a hard design rule (the module docstring
  at `control_ask.py:5-15` says the file exists specifically so this property
  can be proven by AST-walking `test_ask_authority.py` — no `open(...,"w")`,
  no subprocess, no broker symbol, no outbound POST).
- The router is deterministic (`backend/services/ask_tools.py:130-174`,
  `route()`): it maps a question to exactly one of `file`, `receipt`, `fleet`,
  `night_plan`, `universe`, `morning`, or `default` (canon + newest handoff).
  **None of these routes reads `investment_committee`.** A question like
  "what's a good buy" contains none of `_MORNING_WORDS`, `_FLEET_WORDS`,
  `_PLAN_WORDS`, or `_UNIVERSE_WORDS` (`ask_tools.py:94-97`), so it falls to
  `tool_default()` (`:375-396`) — canon TIER 0 names, the newest handoff head,
  and today's receipts. That is why Murat got silence: the router sent his
  question to the *canon*, not to the engine.
- Even the `morning` route (`tool_morning()`, `:274-294`) only surfaces the
  `forecasts` step from `backend/services/morning.py:step_forecasts`
  (`:427-503`), which writes **lane-vs-benchmark win-probability forecasts**
  ("does lane X beat lane Y tomorrow"), not per-ticker buy recommendations.

### 1.4 A genuinely new decision surface exists, uncommitted, not yet wired to either LLM

`backend/services/agency.py` (2,664 lines, untracked directory
`backend/data/optimus/agency/` in git status — this is chunk-16a-era, very
recent, 2026-09-18) is the closest thing in the research repo to the Decision
Contract this audit was asked to spec:

- `DECISIONS: tuple[str, ...] = ("hold", "sell", "buy_more", "trim")`
  (`agency.py:1588`).
- `propose()` (`:1313-1360`) builds **three costed `Strategy` `Option`s** per
  personality neighbour, each with `worst_case` (via
  `alpha.contract.worst_case`... actually
  `backend.strategy.contract.loss_budget_worst_case`), `expected_drawdown`,
  `hold_rule`, and twins — i.e., almost exactly "what to buy, at what size,
  and what would make you wrong."
- `hold()` (`:1398+`) requires an explicit human `sentence` ≥ 12 chars
  (`MIN_SENTENCE_CHARS`, `:1395`) before a chosen option becomes a book —
  **attended by construction**, which is correct given CANON's "no LLM
  authority over real capital," but it means this surface never runs
  automatically each morning; it waits for Murat to open
  `frontend/src/app/desktop/agency/page.tsx` and answer a questionnaire.
- `step_agency_review()` (`backend/services/morning.py:506-560`) is a
  DIFFERENT half of the same module — it reviews EXISTING `origin="human_text"`
  books daily with the same `hold/sell/buy_more/trim` vocabulary
  (`decide_label()`, `:1622-1647`) and writes graded calls to the prediction
  ledger. This runs automatically in the morning pass, but only for books a
  human already holds — it does not originate a new buy from the ranked
  universe.
- Router: `backend/routers/control.py:1234-1468` (`/agency/questionnaire`,
  `/agency/intake`, `/agency/propose`, `/agency/hold`, `/agency/protect-first`,
  `/agency/unflip`, `/agency/review`).
- **Neither `copilot.py`'s tool catalogue nor `control_ask.py`'s router calls
  any `/agency/*` endpoint or `agency.py` function.** A human has to visit the
  desktop Agency page directly; the two chat surfaces cannot even tell Murat
  it exists.

### 1.5 Summary of the stops-short-of-a-decision list, part 1

| surface | produces | stops at |
|---|---|---|
| IIF-1 / Internet Investigator ("agent X") | magnitude/volatility forecast calibration | forbidden by design from any buy/tradable claim (`CLAIM_LANGUAGE`) |
| Investment Committee (`investment_committee.py`) | sized weights/dollars/shares, per capital level | never read by either LLM surface's tool catalogue |
| Agency (`agency.py`) | 3 costed strategy options, hold/sell/trim calls on existing books | attended-only for new picks; automatic only for reviewing books already held; invisible to both chat surfaces |
| Copilot (`copilot.py`) | narrated factor grades, crash prob, backtests | no tool reaches a ranked buy list; ends every answer "not financial advice" |
| Desktop Ask (`control_ask.py`) | receipt/file summaries | explicit system-prompt ban on sizing/deciding anything; router never reaches the engine's rankings |

---

## 2. Execution repo: how a book becomes orders, and the "no trade" taxonomy

### 2.1 The mandate → order path

- `alpha/fleet.py:1-25` — six paper accounts (`hack1`...`hack6`), each a
  **declared `Mandate`** (data, not prose): which brains may spend, universe,
  sizing envelope, ranking objective, structure kinds. "The Railway service
  for a role is the same image with `AAT_ACCOUNT_ROLE` set and nothing else
  decided by hand at 11:00 ET."
- `alpha/brains/*` — one brain per mechanism (`vol_gap`, `event_move`,
  `options_attention`, `narrative_dispersion`, `seasonality_f`,
  `tracker_portfolio`, `theme_basket`, `post_event_drift`, `murat_rule`,
  `council_vector`, ...). Per `aegis-alpha-terminal/docs/HANDOFF.md`
  ("Runner: several brains, one position per symbol, nothing averaged"):
  every brain's enumeration is recorded under its own decision id; the
  champion is the largest approved risk among EXECUTABLE brains; losers are
  written `action=shadow` naming the winner.
- `alpha/allocator.py:1-40` — kills on RISK mechanically (peak-drawdown
  `-5%`/`-7.5%` cuts gross), promotes on RETURN slowly (Thompson posterior,
  capped 35% share, capital freed by a cut becomes `cash_weight`, never
  redistributed same-day). `gross_budget_scale` "can only ever REDUCE."
- `scripts/seal_authority.py:1-60` — the fail-closed service (Railway,
  `loving-elegance` project) that: (1) seals the prediction-book snapshot
  daily, (2) computes and serves the allocator's daily `gross-scale` record,
  (3) serves the Book F seasonality engine file
  (`docs/seed/engines/F_seasonality_<YYYY-MM>.json`) hash-verified. **It
  submits no orders and has no account mandate** — read-only authority, by
  design, over what every loop is permitted to see.
- `docs/DEPLOY_PLAN_2026-09-14.md:1-3,§1-2` — the live mandate table
  (as of the 2026-09-14 deploy): hack3 switched engine to `seasonality_f`
  (Book F); every role's worst case printed in dollars against real account
  equity (§2, e.g. hack3 −$10,001 of $83,342.42).

### 2.2 What is deployed vs not

Per `docs/DEPLOY_PLAN_2026-09-14.md` and `docs/HANDOFF.md`:

- **Deployed and live:** hack1, hack3, hack4, hack5, hack6 on Railway
  (`aat-loop-<role>`), reading the sealed book + allocator record + engine
  file over HTTP from `seal-authority`.
- **Not deployed:** hack2 — "loop DOWN, reassigned to lane D on Murat's
  2026-09-13 12:05 HKT decision" (`DEPLOY_PLAN_2026-09-14.md §0`). hack4 does
  NOT get the G3 lineage rule — the probe found 6 of 14 required features have
  **no source in this repo** ("NOT EXECUTABLE," §1).
- Per user memory (S53, 09-18): the fleet as a whole was reported **never
  deployed** for a stretch this week ($448,555 sitting idle) while the lab ran
  model-less — this is a stronger claim than the deploy plan alone shows and
  should be re-verified live (`railway logs --service aat-loop-hack3`, etc.)
  before treating either statement as current; this audit did not run
  Railway commands per its own read-only constraint.

### 2.3 The "no trade" decomposition — already built, in `alpha/refusal_classes.py`

This file (383 lines) is exactly the deep-research report's "decomposing no
trade," already implemented:

- `classify(reason)` (`:150-157`) maps 43 distinct refusal sentences to a
  closed set of classes via ordered, longest-match-first regex
  (`PATTERNS`, `:22-101`).
- `kind_of(cls)` (`:184-193`) buckets every class into exactly one of four
  questions:

| bucket (`kind_of`) | classes | this audit's label |
|---|---|---|
| `"book state"` (`BOOK_STATE_CLASSES`, `:113-119`) | `GROSS_NOTIONAL`, `DRIVER_CONCENTRATION`, `CROSS_BOOK`, `BOOK_LIMIT`, `PER_NAME_CONCENTRATION`, `TOMORROWS_OPTIONALITY`, `THETA_BURN`, `DELTA_STRESS`, `DAILY_LOSS_LATCH`, `AGGREGATE_RISK`, `CAPITAL_ROUNDS_TO_ZERO`, `ALREADY_HELD`, `BOOK_UNBOUNDED`, `EVENT_NODE_CAP`, `DRAWDOWN_UNKNOWN`, `PAST_LIQUIDATION_DEADLINE`, `CLOCK_SKEW`, `SESSION_CLOSED` | **risk refusal** |
| `"merit"` (`MERIT_CLASSES`, `:135-139`) | `REFUTED_ROUTE`, `MDE`, `EDGE_BELOW_BAR`, `CLAIM_MISMATCH`, `NO_STRUCTURE_CLEARED`, `OPENING_RANGE`, `CONVEX_RULE`, `CHAIN_UNUSABLE`, `CLAIM_MISMATCH_PAIR` | **deliberate abstention** (the idea itself did not clear a bar) |
| `"tournament"` (`TOURNAMENT_CLASSES`, `:130-133`) | `OUTRANKED_BY_SIBLING`, `CASH_BEATS_IT`, `SPREAD_EATS_THE_EDGE` | **deliberate abstention** (a sibling structure won instead — not a lost idea, a redundant one) |
| `"venue"` (`VENUE_CLASSES`, `:127`) | `VENUE_REJECTED` | **broker failure** |
| — (not in this file; found separately in this audit) | hack2 loop down, hack4 feature-not-executable | **not deployed / missing data** |
| — (not in this file) | `UNCLASSIFIED` (`:143`) — "a row that matches nothing," counted in every report | **stale file / unclassified** (a bucket that is itself a finding if it grows) |

`sub_classify()` (`:161-173`) additionally attributes a whole-forecast refusal
("N structures enumerated, none cleared the gates") to the specific gate that
stopped the *best* structure, so a forecast-level refusal is not
double-counted against its own candidate structures.

**This taxonomy is a genuinely strong asset** — reuse it rather than inventing
a second one for the Decision Contract's `falsifier`/refusal fields (§4 below).

---

## 3. The LLM ↔ engine seam, itemized

Every place an LLM output is consumed by numeric code, and every place numeric
output is shown to an LLM, found in this audit:

**LLM → numeric (consumed by code):**

1. `iif1_features.py` / `investigator_night.py` — the LLM's typed forecast
   rows are graded against realized magnitude/volatility (IIF-1). Consumed by
   the read-gate statistics (`iif1_read_gate.classify`), never by a trade.
2. `backend/services/agency.py` `explain_option`/`draft_prose`
   (`:986-1062`, `:2596+`) — the LLM (or a template) turns a computed Option
   into plain words for the Agency page. One-way: numbers → prose, nothing
   flows back.
3. `always_on_lab.py` "decision_vs_reality" job (`:89`,
   `backend/data/optimus/night_factory_2026-09-18/decision_vs_reality_2026-09-18.json`
   per git status) — grades "what we said vs what happened, across every
   mechanism." This is a scoring pass over records that already exist; it does
   not feed a new decision back into either LLM surface's tools.
4. `alpha_terminal`'s `narrative_dispersion` and `event_move` brains
   (`aegis-alpha-terminal/docs/HANDOFF.md` §"Three new brains") — an LLM
   (DeepSeek) reads news and emits `truth/belief/impact/already-priced` axes
   that widen a structure's sigma. **This is the one place in either repo
   where an LLM output changes a sizing number** — and by the handoff's own
   rule, "shadow-only... the LLM emits axes, never a trade" until it beats
   `brain_scoreboard`.
5. E1 typed-event head (`backend/data/optimus/night_factory_2026-09-18/
   L2_typed_events_run01_inputs.json` per git status; the 43-id enum system
   referenced in `feedback_a_prompt_that_refers_to_a_schema_it_never_sends.md`)
   — LLM-typed events feed a tabular forecast head (E1). This is a *research*
   arm (calibration test), not a live book's sizing input.

**Numeric → LLM (shown to a model):**

6. `copilot.py` `TOOLS` (`:148-235`) — market status, single-stock factor
   analysis, crash probability, sector rotation, allocation backtests. The
   LLM narrates these; **the IC's ranked/sized output is not among them.**
7. `control_ask.py` routed context (`ask_tools.route`) — repo files, job
   receipts, fleet state, tonight's queue, the universe header, canon TIER 0.
   **Also excludes the IC's ranked/sized output**, and the system prompt
   forbids the model from turning what it does see into a size or an order.

**Where the loop is broken, stated plainly:**

- The numeric engines that *do* decide (IC's `compose_book`, the execution
  fleet's brains + allocator) never hand their output to either LLM surface's
  context or tool catalogue.
- The one numeric artifact both LLM surfaces *can* reach — `tool_morning()`'s
  `forecasts` step — is a lane-vs-benchmark coin flip, not a per-ticker call,
  so even a perfectly cooperative model has nothing tradable to describe.
- The live paper book (execution repo) and the research repo's two LLM
  surfaces are in **different repos, different deploys** (Railway
  `loving-elegance` vs `selfless-courage`), and nothing in this audit found a
  live HTTP path from either LLM surface to `seal-authority` or to a fleet
  loop's current positions.

---

## 4. Spec: the Decision Contract

### 4.1 What already exists under other names (extend, do not duplicate)

| Decision Contract concept | existing analogue | file |
|---|---|---|
| a frozen, hash-identified decision object | the sealed prediction book | `aegis-alpha-terminal/scripts/seal_authority.py` (content-hash verified, served over `/allocator/`, `/engines/`) |
| position sizing + worst case | `alpha.strategy.contract.loss_budget_worst_case`; `investment_committee.compose_book` | `aegis-alpha-terminal/alpha/contract.py`; `backend/services/investment_committee.py:295-430` |
| `falsifier` / kill condition | `_kill_condition()` | `backend/services/investment_committee.py:60-83` |
| lifecycle: proposed → chosen → reviewed → graded | `agency.propose` → `agency.hold` → `morning.step_agency_review` → prediction ledger `resolve_due` | `backend/services/agency.py:1313-1475`; `morning.py:506-560` |
| kill/promote on realized performance | `alpha/allocator.py` | whole file |
| "why did this NOT happen" taxonomy | `alpha/refusal_classes.py` | whole file (§2.3 above) |
| decision-vs-outcome scoring | `decision_vs_reality` job | `scripts/always_on_lab.py:89` |

**The builder's job is to make one JSON object (the Decision Contract) that
sits ON TOP of these — composed from `investment_committee.compose_book()`
+ `agency.propose()` + the execution repo's `alpha/contract.py` worst-case
arithmetic + `refusal_classes.classify()` for anything that didn't clear —
and to add exactly one new pipe: that object reaches both LLM surfaces'
context.**

### 4.2 New/changed files

1. **`backend/services/decision_contract.py`** (new). One function,
   `build_daily_contracts(asof) -> list[dict]`, called by the morning pass.
   For every ticker that clears `investment_committee`'s tilt gate
   (`compose_book`'s `eligible` list, `investment_committee.py:319-330`) OR
   every `agency.propose()` option surfaced today, emit one row with the
   fields below. For every candidate that does NOT clear, emit a `REFUSED`
   row using `refusal_classes.classify()`'s vocabulary imported from the
   execution repo (vendor the module or re-derive the same closed enum
   locally — see §4.4 on the two-repo seam) so "why no trade" uses one
   vocabulary everywhere, not two.

   Fields (per the task's spec, resolved against what already exists):

   | field | source |
   |---|---|
   | `decision_id` | new: `sha256(policy_id + policy_version + ticker + asof)[:16]` |
   | `policy_id` | the book/personality name, e.g. `OPTIMUS_BALANCED`, or the agency `ips_id` |
   | `policy_version` | `investment_committee`'s funnel `generated_at`, or `agency.IPS.ips_hash` |
   | `information_cutoff_utc` | the funnel/features snapshot timestamp already on every IC/IIF-1 payload |
   | `licence` | one of the three existing licences (CLAUDE.md "THREE LICENCES") — this contract is `PRODUCT_EXPERIMENT` by construction, never `CAPITAL_CANDIDATE` |
   | `universe_hash` | already computed for the funnel gate (`REC.assert_registry_discipline`) |
   | `signal` | `r.leader().signal_id` (already on every `Recommendation`, used by `_kill_condition`) |
   | `direction` | `BUY`/`WATCH`/`SELL` from `r.recommendation` |
   | `horizon` | `config.IC_WEALTH_HORIZON_MONTHS` or the agency `Strategy`'s horizon |
   | `expected_payoff` | **do not fabricate one** — reuse the IC's existing refusal: "NOT CALIBRATED," carried as a field, not omitted (CLAUDE.md "a headline number belongs in a receipt") |
   | `estimated_probability` | from `agency.decide_label`'s `probability` where an Option exists; `null` + reason otherwise |
   | `maximum_loss` | `alpha.contract.loss_budget_worst_case` (execution repo) or `investment_committee`'s `worst_case` (agency) — already computed, just needs to land on this object |
   | `position_budget` | `compose_book`'s `weight`/`dollars`/`shares` |
   | `cost_model` | whichever cost model priced the book (`Policy` in `portfolio_farm`, or the execution repo's fill model) — cite it, do not silently assume zero cost (CLAUDE.md "EXPLORE DIRTY" rule 3) |
   | `falsifier` | `_kill_condition()`'s existing string |
   | `expiry_utc` | the review cadence (`agency`'s `hold_rule`) or the kill condition's own horizon |
   | `artifact_sha256` | hash of this row, computed the same way `seal_authority.py` hashes the book |

2. **`backend/services/decision_ledger.py`** (new, small). The lifecycle
   states requested: `DECIDED → DELIVERED → SEEN_BY_EXECUTOR →
   REFUSED|ORDER_SUBMITTED → FILLED → SCORED`. This is new — nothing in
   either repo currently tracks "did the LLM/human SEE this before the window
   closed." Model it as an append-only JSONL beside
   `backend/data/optimus/predictions.jsonl` (same durability pattern,
   same "campaign vs live" population field the two-ledger ruling already
   established — reuse that pattern rather than inventing a third ledger
   shape). `SEEN_BY_EXECUTOR` is written when `control_ask.py` or
   `copilot.py` actually retrieves the row (§4.3); `ORDER_SUBMITTED`/`FILLED`
   are written from the execution repo's fill/order path
   (`alpha/fills.py`) — this is the one place the spec requires a
   **cross-repo write**, and it should go through the same artery
   `seal_authority.py` already uses (HTTP, hash-verified, no shared
   filesystem) rather than a new mechanism.

3. **`backend/services/copilot.py`** — add one tool:
   `get_todays_decisions()` → reads today's `decision_contract.py` output.
   This is the single smallest change that answers "what would you buy
   today": give the copilot a tool that returns the contract rows, and
   update `SYSTEM_PROMPT` (`copilot.py:238-247`) to say the model MAY state
   the engine's own ranked list and size when this tool was called, still
   appending the existing "not financial advice" line — the two are not in
   tension; describing a computed position is not the model inventing advice.

4. **`backend/services/ask_tools.py`** — add a `decisions` route:
   extend `_MORNING_WORDS`-style matching (`ask_tools.py:94-97`) with a
   `_DECISION_WORDS = ("what should i buy", "good buy", "what would you buy",
   "what to buy")` tuple, and a `tool_decisions()` following the exact shape
   of `tool_morning()` (`ask_tools.py:274-294`) that reads
   `decision_contract.py`'s output instead of the `forecasts` step. Route it
   BEFORE the `_MORNING_WORDS` check in `route()` (`ask_tools.py:164-166`) so
   "what's a good buy today" does not fall through to `_MORNING_WORDS` and
   answer with the lane-vs-benchmark coin flip. **`control_ask.ASK_SYSTEM`
   (`control_ask.py:43-49`) does not need to change** — it already permits
   reading and explaining a receipt; a Decision Contract IS a receipt. The
   "you cannot size positions" clause stays exactly as strict, because the
   contract is pre-computed by the engine, not sized by the model in the
   chat turn.

5. **Frontend**: one new card or a "decisions" tab on
   `frontend/src/app/investment-committee/page.tsx` (already exists, already
   renders `compose_book`'s output) that also renders `falsifier` and
   `expiry_utc` beside each position — most of the data this needs is already
   in the `committee()` payload (`investment_committee.py:519-556`); the
   contract's job is to name and freeze the existing fields, not add new
   computation to the frontend.

### 4.3 What this buys, concretely

Tomorrow morning: `morning.py`'s step order gains one step,
`step_decision_contract`, after `step_forecasts` and `step_agency_review`
(same position `step_grade` currently holds, i.e., after the numbers exist,
before anything is graded). It writes the day's contract rows. When Murat
opens the desktop app and asks the local model "what's a good buy," the
question matches `_DECISION_WORDS`, `control_ask.py` routes to
`tool_decisions()`, and the model reads BUY-ranked rows with size, kill
condition, and expiry already computed by the engine — and says so, because
its system prompt already permits explaining a receipt. When Murat asks the
web copilot the same question, `get_todays_decisions()` is a tool the model
can call, same answer, same source of truth, same row.

### 4.4 One thing this spec deliberately does NOT do

It does not build a new ranking engine, a new sizing model, or a new LLM
call. Every number in a Decision Contract row already exists somewhere in
`investment_committee.py`, `agency.py`, or the execution repo's `alpha/
contract.py` / `refusal_classes.py`. The gap Murat is describing is a wiring
gap — computed decisions that never reach the surfaces he talks to — not a
missing-intelligence gap, and the smallest fix is exactly that: one contract
object, two new tool/route entries, no new model, no new capital risk.

---

## 5. Personal-mode disclaimer flag

### 5.1 Every "educational / not financial advice" string found

| file | line | string |
|---|---|---|
| `frontend/src/components/disclaimer-banner.tsx` | 10 | "Educational tool only. Not financial advice. All predictions are probabilistic estimates with significant uncertainty." |
| `frontend/src/components/methodology-banner.tsx` | 19 | "...Educational tool, not financial advice." |
| `frontend/src/components/dashboard/model-vs-firms-card.tsx` | 82 | "...Educational, not advice." |
| `frontend/src/components/stock/factor-lens-card.tsx` | 186 | "Data: Kenneth French Data Library. Educational, not advice." |
| `frontend/src/components/stock/two-sided-card.tsx` | 60 | "...never come from the AI. Educational, not financial advice." |
| `frontend/src/app/screener/page.tsx`, `risk/page.tsx`, `portfolio/page.tsx`, `news/page.tsx`, `investment-committee/page.tsx`, `copilot/page.tsx`, `crash/page.tsx`, `retirement/page.tsx`, `about/page.tsx` | (imports/renders `<DisclaimerBanner/>` or equivalent) | via the shared components above |
| `backend/routers/market.py` | 567 | "...Educational comparison, not advice." |
| `backend/services/copilot.py` | 245-246 | "This tool is educational; always end with a one-line reminder that Aegis is not financial advice." (SYSTEM_PROMPT clause — affects generated text, not a static string) |
| `backend/services/daily_brief.py` | 47 | "Educational context from public data — not financial advice." |
| `backend/services/portfolio_intelligence/tearsheet.py` | 261 | "Educational, not financial advice.</div>" |
| `backend/services/portfolio_guidance.py` | 196 | "...levels — not financial advice, not orders. No..." |

### 5.2 The proposed flag

**Backend:** `backend/config.py` — one new setting, following the existing
boolean-env pattern (`RESEARCH_LLM_ENABLED`, `config.py:2204`):

```python
PERSONAL_MODE = os.getenv("AEGIS_PERSONAL_MODE", "0") in ("1", "true", "yes")
```

Use it at the two backend string sites (`market.py:567`,
`copilot.py:245-246`) by branching the string, and expose it on
`/api/health/full` (or wherever `is_available()`-style flags already surface,
e.g. `copilot.py:483-484`) so the frontend can read it without hardcoding.

**Frontend:** one new env var, `NEXT_PUBLIC_AEGIS_PERSONAL_MODE`, read once
in `disclaimer-banner.tsx` and `methodology-banner.tsx` (both currently render
unconditionally) and in the three inline-string components
(`model-vs-firms-card.tsx:82`, `factor-lens-card.tsx:186`,
`two-sided-card.tsx:60`) — gate each render with
`process.env.NEXT_PUBLIC_AEGIS_PERSONAL_MODE !== "1"`.

**Files to touch (7):**
`backend/config.py` (new flag) ·
`backend/routers/market.py:567` ·
`backend/services/copilot.py:245-246` ·
`frontend/src/components/disclaimer-banner.tsx` ·
`frontend/src/components/methodology-banner.tsx` ·
`frontend/src/components/dashboard/model-vs-firms-card.tsx:82` ·
`frontend/src/components/stock/factor-lens-card.tsx:186` ·
`frontend/src/components/stock/two-sided-card.tsx:60`

Leave `daily_brief.py:47`, `tearsheet.py:261`, and `portfolio_guidance.py:196`
alone for now — those are export/brief artifacts that may leave Murat's
machine (a saved tearsheet, a shared brief) and should probably keep the
disclaimer regardless of build target; that is a judgment call for Murat, not
this audit, and is called out rather than silently decided.

---

## Notes on scope and what this audit did not do

- No git commits, no edits outside this directory, no `.env` reads, no
  Railway/fleet-deploy commands were run, per this task's own constraint.
  Section 2.2's "never deployed" claim from user memory was NOT independently
  re-verified against live Railway state and should be checked with
  `railway logs --service aat-loop-<role>` before it is repeated as current.
- This spec composes existing computation; it does not evaluate whether
  Book F seasonality, Book G price-scaled dispersion (`docs/TRIALS/
  TRIAL-DRAFT-G-forecast-dispersion-v0.md` — still `UNSIGNED DRAFT` as of
  2026-09-13), or belief elasticity (`docs/research_notes/2026-09-12/
  spec_lane_x.md` — `PRODUCT_PROMISING`, not yet an arm in a live head) are
  themselves good ideas. The Decision Contract's job is to surface whatever
  the engine already decided, honestly, including "NOT CALIBRATED" and
  "REFUSED" rows — it is not a claim that today's rankings are alpha.
