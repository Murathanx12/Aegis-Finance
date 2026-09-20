# AEGIS — THE CONTEXT DOSSIER (2026-09-19)

*Give this file to any Claude session (or any model) that has to reason about Aegis. It is the
one-file answer to "what is this, what is known, what is dead, what is live, what is next, and how
do we work". Everything here is backed by a file in the repo; the path is beside each claim. It
supersedes nothing — the TIER 0 files still outrank it — it only collects.*

## 0. What Aegis is, in one paragraph

A self-improving investment-intelligence system owned by Murathan Abdullaev (HKU), built across
four repos: **Aegis-Finance** (research, the farm, the night factory, the always-on lab, the
website and desktop app), **aegis-alpha-terminal** (execution: six Alpaca paper accounts on
Railway, sealed books, an allocator), **Optimus** (the memory: an MCP brain over both repos'
docs) and the **Aegis module** (the 2026-07/08 hypothesis lab with its calibration ledger). The
objective is terminal wealth under a declared utility (`docs/OPTIMUS_OBJECTIVE.md` §0). Three
licences govern what may be claimed vs tested (`CLAUDE.md`: PRODUCT_EXPERIMENT /
CAPITAL_CANDIDATE / RESEARCH_CLAIM). The LLM narrates and types; the deterministic engine
computes; nothing LLM-derived allocates. The sole cloud LLM is DeepSeek; a local llama-server
(7B; Qwen3-30B-A3B measured) runs the unattended reads.

## 1. The value proposition (settled 2026-09-19)

For Murat's own use: **every morning, from registered evidence only, the system states what it
would buy or short today, at what size, why, and what would make it wrong — and grades
yesterday's statement against what happened.** That sentence is the product. The fleet, the
lab, the ledger and the night factory exist to produce and grade it. The public build is the
same sentence with the disclaimers back on (`AEGIS_PERSONAL_MODE`, roadmap §14.2).

## 2. How we work (the loop)

Roadmap §14.2, verbatim in short: a question enters with its corpse check and a verdict class
(ALREADY_TESTED / OPEN_AND_CHEAP / OPEN_BUT_NEEDS_DATA / NOT_A_HYPOTHESIS) → **Sonnet** researches
and writes a note with a build spec → **Fable** writes the roadmap chunk and an UNSIGNED
pre-registration → **Opus** builds with tests, commits locally, never pushes → **Fable** validates
(diff vs spec, suite under the memory recipe, push the verified SHA, watch CI, read the first
receipt) → the night factory / the lab runs it unattended → paper capital moves by rule
(allocator) and the Decision Contract records decided / delivered / seen / refused / filled /
scored. One Opus at a time. Gates outrank dates.

Two steps of the daily pass close that loop and were added on 2026-09-20 (chunk 18b, §14.4c),
because both halves of it existed in code and neither had ever run:

- **`decision_contract` now runs SECOND**, immediately after `news_pull` instead of fifth behind
  the analyst sweep — it needs nothing the sweep writes, it takes twelve seconds, and standing
  behind two and a half hours of network is why it had never executed once and why the decision
  ledger did not exist.
- **`grade_forecasts` runs after `book_cadence`** and resolves every forecast whose window has
  closed against the LOCAL bars through `ledger_resolver.resolve_due`, with a named reason per
  record that did not grade — the first run resolved 14,703 of a ledger that was 100% ungraded.

The last link of that loop — *"paper capital moves by rule"* — grew its rule on 2026-09-20
(chunk 18c, §14.4d). `backend/services/roi_rank.py` ranks the candidates that already cleared
the hard gates by `expected_return_net / downside` at the declared horizon, takes the top K and
sizes by fractional Kelly (`arena.policies.size_ce_kelly` reused, so `w = f · mu/sigma²` exactly,
with the four personalities as the `f` and the 3%/10% caps still binding — today's worst case is
unchanged). It scores a name **only** when both numbers are measured: the leading signal's net
forward return, copied off a receipt in `config.SIGNAL_MEASURED_RETURN` whose path a test proves
is on disk, and the name's own volatility — and only when that signal's own measured **t** clears
`ROI_MIN_T`. Three of the eight adapter signals have such a read (`profitability_small`
+0.241%/mo net with no t on the *return*, `insider_opportunistic` t 1.40,
`fusion_insider_profitability` NW t 1.66), none clears 2.0, so today's 43-row contract scores
**zero** and every row now names the field it is missing instead of carrying one flat
`NOT CALIBRATED` string. The BUY set and every weight are unchanged — the loop's shape changed,
not its output, and the rule fires without a code change the day a signal earns a t ≥ 2 read.
Beside it, `decision_ledger` gained `REVISED` at rank 3.5 and `decision_contract.revise`, which
re-runs the same ranking over the affected capital level and writes a child row with
`parent_decision_id` only when direction or rank-cut moves; it takes candidate FIELDS and refuses
text, so a typed event can revise a decision and a sentence cannot.

**And then the same evening, the authority split (chunk 21, §15.2), because a rule that scores
zero while a heuristic still buys four is two rules.** Murat's review: *"that is internally
inconsistent with 'if it can't be sure, don't make the bad decision' ... do not require t ≥ 2
before AEGIS is allowed to learn. Uncertain must mean INVESTIGATE, never freeze."* Every
candidate that clears the hard gates now carries exactly ONE authority
(`backend/services/decision_authority.py`): **EXPLOIT** — the leading signal's measured t clears
`ROI_MIN_T`, sized by the Kelly above, **empty today and printed empty**, which is what chunk 22's
rank→return calibration exists to change; **EXPLORE** — measured but unproven (positive monthly
net, t below the floor or no t at all), funded out of a fixed paper-risk budget
(`EXPLORE_BUDGET_PCT` 2% of equity at `EXPLORE_PER_NAME_PCT` 0.25%) allocated by **Thompson
sampling** over Normal(measured net, se), se = |net|/t and 3·|net| when the receipt states no t —
an unmeasured t is the *widest* posterior, never a zero — ranked by
`draw − cost − risk_penalty(vol) + uncertainty_bonus(se)` with every draw seeded from the as-of
date and the name, so a rebuilt day reproduces exactly; **REFUSED** — everything else, each with
its own sentence, and a name with *no* measured read is refused rather than explored, because
exploration is for measured-but-unproven and never for nothing. `IC_LEGACY_HEURISTIC_SIZING`
(False) retires `cap × verdict × confidence`, and a test asserts no row can carry a position
budget without an active authority. Today's rebuilt contract: **0 EXPLOIT, 2 EXPLORE (CVLG and
INDV at 0.25% = $100 each of the declared $40,000), 38 REFUSED**, worst cases printed side by
side — tilt sleeve 10 × 3% held to 10%, explore 0.50% of equity under a 2% ceiling, additive.

Two things follow that a reader of the loop needs. **Every dollar now resolves daily** (item 11):
the contract receipt carries `capital_resolution` — 99.50% benchmark core / 0.00% active exploit /
0.50% active explore / 0.00% cash, summing to 1.0, with the line "'no active trade' is an allowed
outcome; 'nothing happened' is not". And **the economics is printed first** (item 12):
**And on 2026-09-21 the loop's last open link closed: the engine can now say how much, per
company** (chunk 22, roadmap §15.2). Until Sunday, `roi_rank`'s expected return came from the
leading signal FAMILY's average — one number per signal, the same for every name it led — and the
downside came from the ticker's volatility, so among names sharing a family the rule preferred
whichever happened to be quietest. `scripts/calibrate_signal_return.py` (`C7_signal_calibration`,
stage `features`, 60-minute box, resumable per signal) now builds, for every signal the registry
permits to LEAD, an OUT-OF-SAMPLE map from score decile to abnormal return and downside at
5/21/63/126 sessions — cut points refit yearly on the expanding past, months as the dependence
unit, a block bootstrap on every cell, costs charged at 25 bps/side on the decile's own turnover,
two nulls and Holm over the whole (signal × horizon) family. `backend/services/signal_calibration.py`
is the only reader; `roi_rank` takes the candidate's OWN decile's net mean as `μ_i` and that
decile's measured 20th percentile as the downside, printing which of the two sources produced
each number and the receipt path it came off. **`decision_authority` now admits to EXPLOIT only a
name whose leading signal carries a CALIBRATED map**, so the set that has been empty since the
split was built can become non-empty only through measurement, never through a config row.

The first real run says the honest thing: all three leadable signals are **WEAK** over 2006-2024
(191 month blocks). `profitability_small` has the one map that looks like a map — monotone at
Spearman 0.964, D1 −0.417% → D10 +0.358% net, D10−D1 +0.6445% at 21 sessions (t 1.588, Holm p
1.000; at 126 sessions +5.11%, t 2.78, Holm p 0.065, the only cell near the bar).
`insider_opportunistic`'s gross edge (+0.125%/month) is smaller than its own turnover cost
(0.171%/month) and its score is 0.0 for 79.8% of name-months, so four of ten deciles are ever
populated and the receipt says so rather than printing ten buckets that are really two. The
measurement moved capital the same day: INDV's $100 of paper EXPLORE was withdrawn, because its
own decile reads −0.073%/month net where the family row had said +0.17%.

`backend/services/morning_scoreboard.py` composes NAV vs SPY, exploit P&L, explore P&L, decisions,
forecasts matured and graded, calibration against the base-rate Brier, strongest new positive,
strongest killed and one sentence on whether anything learned changed capital — as the first block
of the daily-pass receipt and the first paragraph of the desktop Ask. It computes nothing of its
own, and any field it cannot derive prints `CANNOT DETERMINE: <why>` and never a zero; six of ten
are in that state today (no local NAV, nothing SCORED yet, 0 resolved in the calibration window),
which is a fact about the programme rather than a defect in the reader.

Operating rules that cost the most to learn (full list: `docs/AEGIS_STRATEGIC_INVARIANTS.md`,
`CLAUDE.md` session protocol, roadmap §6/§13/§14.6): never kill by image name; never move
`.env`; gate a push on the suite's `exit=0` line and push the SHA, not the branch; a receipt is
dated by its own stamp; a gate that cannot go green is broken; the registered construction is
a test input; a check that did not run is not a check that passed; a refusal is a finding.

## 3. The state of the world (2026-09-19 12:00 HKT)

| | |
|---|---|
| fleet (paper, live read) | $440,907 of $500,000 across hack1/3/4/5/6; never deployed on the new engines; hack2 retired to lane D |
| best registered read | Book F calendar seasonality, +0.43%/mo net vs its twin at the $10M floor, t 3.12 (`night_factory_2026-09-13/B_books_efg_replay_run01.json`) — CONDITIONAL, untraded |
| filters/features standing | Book G price-scaled dispersion (+1.19%/mo t 6.07 at $10M, UNSIGNED, a screen not a book); belief elasticity (X2) as a feature |
| closed this month | A, B, H, I FAILED_VARIANT; C CONDITIONAL at $3M only; E dead at floor; R2 REJECTED on panel B; typed events closed at 5 and 1 sessions (143k headlines NOT typed by decision); X4 routing worse in sample |
| uptime | the lab runs from the Startup folder and now starts the model server itself (chunk 16a); both Windows scheduled tasks failed today (0x80070520) — chunk 17 moves the clock into the lab |
| money | ~$1,000 sunk (Railway ×2, DeepSeek, EODHD once); DeepSeek balance $56.98; lab spend $0/day (local model); Railway usage is dashboard-only |
| tests | 9,853 fast tests green; CI green at `48fcf4b5` |

## 4. What is DEAD, what is RULER-DEAD, what is OPEN (the failure thesis, condensed)

Source: `docs/research_notes/2026-09-19/research_failure_thesis.md` (57 rows, one per
`NEGATIVE_RESULTS.md` section).

- **Genuinely dead on modern, cost-honest data (stay closed, ~14):** market-timing signal
  engines vs buy-and-hold (§1), crash prediction at every horizon (§2, §6, §7, §33), LPPLS (§3),
  FDA approval drift at monthly and daily resolution (§11, §16), regime rotation (§15),
  conditional vol targeting (§21), residual momentum (§23), analyst price targets (§17), the
  option-implied cross-section incl. flow (§27), abnormal institutional ownership as a long
  signal (§26), LLM/agent trading alpha (§19, three external receipts to rebut before any
  LLM-signal registration).
- **The ruler's fault, not the pool's (six):** §32, §34, §36, §38, §40, §41 — gates with ~0%
  measured power, n where n_effective was owed, a regret denominator that manufactured
  refutations. §35's replay under fixed gates turned 0-for-179 into 10 adoptions.
- **Construction-dead, cheap to re-test:** momentum's drawdown (§9/§10: vol-scaled version
  untested), the supplier thesis at annual cadence (§12: reopen as event-conditioned daily
  links), the small-cap shelf's cost premise (§22), the 13D family "unmeasurable" only because
  both designs entered at month-end (§29-31).
- **Read as closed but never tested:** the short-leg rank information (IC t up to 11) as an
  EXCLUSION SCREEN on long-only books (§26/§27/§28 flag it, nobody ran it).
- **Positive and clean:** second moments are predictable and one trailing realised-vol number
  matches a 14-feature model (§52) — build the risk head; 13D activist disclosure CAR +152 bps
  t 2.37 placebo-controlled (§29).
- **Five re-tests adopted in order (roadmap §14.4 chunks 19-22):** exclusion screens · the 13D
  event-window book · the LLM-autopsy precursor library (85% of exceptional moves unwarned,
  ~$0.001 each) · the $10M re-audit of §35/§22 · TAQ costs on the §22 graduates.

## 5. Murat's ideas, adjudicated (`research_murat_ideas_adjudicated.md`)

| idea | verdict |
|---|---|
| CXMT vs Micron | not a trade (MU −5.2% on 09-14 was a sector day); **a missing event class** → `foreign_entrant_capacity` id + TRIAL-FOREIGN-ENTRANT-IC |
| earnings calls → suppliers early | §12 closed at annual cadence; reopen as event-conditioned daily links keyed to `growth_constraint_cited` |
| CEO open-market buys | TRIAL-INSIDER-IC / CMP-INSIDER-IC accruing forward (decision 2027-07-21); §46: no pre-disclosure accrual — do not re-register |
| politicians / hedge funds | TRIAL-CONGRESS-IC, TRIAL-ARK-IC accruing; generic 13F closed (§26) |
| options flow gap | §27 closed on OptionMetrics incl. flow; retail UOA needs $99-199/mo data — not now |
| ICT session-sweep FVG ritual | discretionary as stated; a frozen mechanical rule is testable on Alpaca 1-min in lane D; low prior |
| buy close / sell open | `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`: anomaly real, strategy rejected; survivor = reduce exposure intraday, never overnight (allocator rule) |
| social mentions, comment debate | open, needs data → `spec_social_video_pipeline.md` |
| construction ("five equal-weight names") | fractional Kelly exists and is correct (`arena/policies.py::size_ce_kelly`) but runs in 1 of 10 books; second arena book Kelly-sized vs EW twin; DeMiguel-Garlappi-Uppal is the honest prior |

## 6. Why the engine "makes no decisions" (`spec_decision_contract_and_path_audit.md`)

The engine sizes positions (`investment_committee.compose_book`, kill conditions per name), the
agency proposes costed options, the fleet places paper orders daily and refuses with a 43-class
taxonomy (`alpha/refusal_classes.py`) — and **none of it reaches the two surfaces Murat talks
to**: the copilot has ten tools and none returns a ranked buy list; the desktop Ask's system
prompt forbids sizing. "Agent X" is the Internet Investigator (IIF-1), forbidden from buy
verdicts by design (it forecasts calibration). The fix is wiring: a Decision Contract JSON per
day composed from the existing numbers, a lifecycle ledger, one copilot tool, one Ask route,
one card (chunk 18). No new model.

## 7. Data and tools we hold

WRDS (HKU): CRSP PIT 1990-2024, Compustat segments, IBES, OptionMetrics 23 years, TAQ (effective
spreads on the 182-name panel), 13F, Form 4 bulk; JKP factor panel on disk; our own corpus:
`news_pull` 18 sources with `first_seen_utc`, the 43-id typed-event vocabulary
(`backend/services/event_vocabulary.py`), the text-return panel, the hiring collector (192
boards), the catalyst calendar, decision-vs-reality grading, the nightly NN lab (12 heads), the
night factory (checkpoint/resume, twins, DSR/PBO stopping rules), the portfolio farm, the arena
(ten books, `ce_kelly` and HRP sizing coded), Alpaca 1-min bars, FRED, Finnhub free tier.
Attach next: **Scrapling** (BSD) now; NautilusTrader (LGPL) and Kronos (MIT) later
(`research_external_repos_round4.md`). Not lawful/not worth it: Instagram, X at scale, Osiris.

## 8. The roadmap from here

`docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md` §14.4: chunk 17
(the lab owns its clock; personal mode) → 18 (Decision Contract) → 19 (exclusion screens,
autopsy library, the Kelly book, the foreign-entrant id) → 20 (social phase 1) → 21 (13D
event-window book) → 22 (re-tests 4-5, Kronos, Nautilus). Terminal repo: the deploy (Murat),
delete `aat-loop-staging`, the overnight execution rule, the seal-authority 404 client.

## 9. What only Murat can do

Run the deploy lines · delete `aat-loop-staging` and read Railway usage · rotate the historical
FRED key · create the YouTube and Reddit keys · send the Xfield URL · decide the export
disclaimers · Book G Amendment 1.

## 10. Where the receipts live

`NEGATIVE_RESULTS.md` (57 sections) · `docs/TRIALS/` · `backend/data/optimus/night_factory_<date>/`
· `docs/research_notes/<date>/` · the handoffs `docs/HANDOFF_2026-09-11_*` · memory in
`~/.claude/projects/.../memory/` · Optimus MCP (`session_briefing`, `aegis_verified_state`,
`brain_query`, `aegis_postmortems`).
