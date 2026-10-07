# Session budget receipt — 2026-10-07-day (Q10)

Built: `backend/services/session_budget.py` + `python -m scripts.session_budget`
(open / log / close / status). See that module's docstring for the full design
rationale. One line of context for anyone reading this cold:

> Claude Code's own Opus/Sonnet/Fable usage has no API this repo can read, and
> the session transcripts that would show it live outside the repo entirely.
> So this receipt is **DECLARED** by the orchestrator, one row per task, worker
> + priority (§5b's 1-7 order) + a one-line EV — never measured, never
> defaulted, never guessed. The **one number that IS measured** is paid-API
> spend (DeepSeek + OpenClaw), pulled from `llm_telemetry.summary()` against
> `backend/data/optimus/llm_calls*.jsonl`, and it is labelled `MEASURED`
> everywhere the declared rows are labelled `DECLARED`.

## Seeded today's session

`backend/data/optimus/session_budget/2026-10-07-day.json`, one row per
chunk/review/research task from `docs/HANDOFF_2026-10-07_V1_BETA_NIGHT_ONE.md`
§0b and `docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` §5/§5a/§5b —
night one's C1-C14 builds *and* their adversarial Opus reviews as separate
rows (so the Opus-heavy night shows up as Opus-heavy rows, not folded into one
row per chunk), R1-R11 research notes, the morning wave C15-C26, and the third
queue Q1-Q10. `tokens`/`usd` were left blank throughout — nobody declared a
token count for this session, and a blank is the honest answer, not a zero.

### `status --session 2026-10-07-day` (captured after close; real CLI output)

```
session 2026-10-07-day (2026-10-07) -- opened 2026-10-07T04:46:12+00:00, CLOSED 2026-10-07T04:47:27+00:00
task                                      worker        pri tokens   usd      ev
C1 fair twin in shared code               opus          2   -        -        measurement correctness: one shared convention stops every board quoting a different round-trip
C1 fair twin review                       opus          2   -        -        adversarial second-Opus review of C1's convention before it reissues every board
C2 PC-PAPER $1M mandate + sim owner       opus          1   -        -        capital/execution correctness: worst case must print in dollars before a mandate binds
C2 PC-PAPER review                        opus          1   -        -        adversarial review of the sim owner and worst-case arithmetic
C3 winner/loser DNA nightly receipt       opus          4   -        -        research: clusters of winners/losers from R4, beta/cash/selection split per lane
C3 winner/loser DNA review                opus          4   -        -        adversarial review of C3's clustering and evidence labels
C4 Opportunity Explorer page + API        opus          6   -        -        core product/UI: owner-ordered columns, direction vs magnitude, company names
C4 Opportunity Explorer review            opus          6   -        -        adversarial review of C4 before it ships to /opportunities
C5 nn_lab membership freeze + nightly ru  opus          2   -        -        data/measurement correctness: a frozen membership stops silent universe drift
C5 nn_lab review                          opus          2   -        -        adversarial review of the freeze and the ridge/LightGBM/NN baseline comparison
C6 Telegram cockpit intent router         opus          6   -        -        core product/UI: deterministic utterances, bounded LLM fallback, no new authority
C6 Telegram cockpit review                opus          6   -        -        adversarial review of the router's refusal-on-out-of-enum behaviour
C7 OpenClaw open web query planner        opus          4   -        -        research instrument: pages to claims to forecast rows, yield printed, read-only
C7 OpenClaw review                        opus          4   -        -        adversarial review of the yield receipt and the read-only boundary
C8 progress-aware health                  opus          3   -        -        bug blocking the live loop: UNKNOWN by omission had become ALIVE by omission
C8 health review                          opus          3   -        -        adversarial review that every REFUSED/ERROR/STOPPED path still never reads ALIVE
C9 contest desk direction-aware rehearsa  opus          5   -        -        forward-paper improvement: a second rehearsal sheet graded beside ROT5_TRAIL
C9 contest desk review                    opus          5   -        -        adversarial review of the magnitude x direction sign construction
C10 data catalog + ledger archival        opus          2   -        -        data/measurement correctness: one receipt answers do-we-have-X; 178MB out of git
C10 data catalog review                   opus          2   -        -        adversarial review of the Parquet rotation and manifest
C11 Decision Story + regret ledger        opus          5   -        -        forward-paper improvement: lineage ids event to decision to outcome, regret by type
C11 Decision Story review                 opus          5   -        -        adversarial review of the leave-one-source-out and BUY-counterfactual construction
C12 theory cells at $0 from R5            opus          4   -        -        research: price-location features, fiscal-year spending, snowball prereg
C12 theory cells review                   opus          4   -        -        adversarial review of the EV-shrink for thin families
C13 two suite failures fixed              opus          3   -        -        bug blocking the live loop: two failing tests found during night one's merge gate
C14 gateway process leak fixed            opus          3   -        -        bug blocking the live loop: an MCP process leak surfaced by the ten-builder wave
R1 outside tools research (Alpaca/RD-Age  sonnet        4   -        -        research: borrow_from_outside note, $0
R2 funding + contest facts research       sonnet        4   -        -        research: funding_and_contest_status note, $0
R3 OpenClaw model audit + open-web feasi  sonnet        4   -        -        research: 7-day yield estimate feeding C7's gate, $0
R4 winner/loser DNA analysis              sonnet        4   -        -        research: feeds C3's clustering, $0
R5 snowball prereg draft + theory object  sonnet        4   -        -        research: feeds C12's cells, $0
C15 review follow-ups (sticky-twin v2, b  sonnet        3   -        -        bug/plumbing: items owed by C1/C3/C9/C4/C5/C7's reviews
C16 public-flow sensors (USAspending, LD  sonnet        4   -        -        research/data: sensors with provenance and latency, no trade signal alone
R6 public-flow sensors research note      sonnet        4   -        -        research note gating C16
C17 world state + regime rows             sonnet        5   -        -        forward-paper improvement: belief table, regime-classification forecast row, graded from 10-09
R7 world state research note              sonnet        4   -        -        research note gating C17
C18 analyst reputation weighting          sonnet        2   -        -        data/measurement correctness: reputation-weighted consensus replaces n>=5; labelled NOT_PERSISTENT_OOS
R8 analyst reputation research note       sonnet        4   -        -        research note gating C18
C19 Arena/Forecast-lab/Theory-lab/Health  sonnet        6   -        -        core product/UI: evidence ladder on every page, frontend_check 0/0/0
C20 six-role fleet v3 contracts (prepare  sonnet        1   -        -        capital/execution-adjacent: contracts hashed, benchmark core flag OFF pending D21/D22
C23 funding + documentation pack          sonnet        7   -        -        nice-to-have (docs): evidence pack, V1 Beta doc, honest README
R9 funding/contest docs research note     sonnet        4   -        -        research note gating C23
C25 health gate root-cause fixes          sonnet        3   -        -        bug blocking the live loop: three gate failures fixed at the root, not papered over
R10 design reference library research no  sonnet        7   -        -        research note gating Q3/Q5 (p5.js, motion for data, GitHub identity)
R11 social-media theory objects research  sonnet        4   -        -        research note gating Q4
C26 fleet gates + EOD audit (new, unrevi  opus          1   -        -        capital/execution correctness: two new gates touch live paper orders; default SHADOW
Q1 restore README generated bridge block  sonnet        3   -        -        bug/plumbing: mechanical, test-pinned fix
Q2 final frozen-tree suite -> merge -> p  deterministic 1   -        -        the merge gate itself: capital/execution-adjacent, no model judgement needed
Q3 design reference library docs          sonnet        7   -        -        nice-to-have: research/docs for the brain page redesign
Q4 four social-media ideas as theory obj  sonnet        4   -        -        research: mechanism/assumptions/data-gaps template
Q5 brain page v2 state-driven layout      sonnet        6   -        -        core product/UI: low-risk frontend, deterministic tests review
Q6 finance-research intake routine for T  sonnet        4   -        -        research: mechanism/assumptions/variables/failure-modes template
Q7 review of C26 fleet gates              opus          1   -        -        capital/execution correctness: adversarial review of live-order-adjacent gates
Q8 external AI research instruments audi  sonnet        4   -        -        research: Perplexity/Consensus/Semantic Scholar/arXiv coverage vs our stack
Q9 heavy deferred measurement items       opus          2   -        -        data/measurement correctness: sticky-twin v2, ROT5_DIR replay, contest horizon worst case
Q10 session budget receipt (this task)    sonnet        7   -        -        nice-to-have plumbing: a DECLARED manager view of the Opus/Sonnet mix
-- 56 row(s); opus share of rows: 0.5179 (DECLARED)
```

(`task` truncates at 40 chars in the terminal table — the full names are in
the JSON at the path above; e.g. "C5 nn_lab membership freeze + nightly ru"
is "C5 nn_lab membership freeze + nightly runs".)

### `close --session 2026-10-07-day` summary (real CLI output)

```json
{
  "n_rows": 56,
  "by_worker": {
    "opus": 29,
    "sonnet": 26,
    "deterministic": 1
  },
  "by_worker_label": "DECLARED",
  "by_priority": {
    "2": 8,
    "1": 6,
    "4": 20,
    "6": 6,
    "3": 7,
    "5": 5,
    "7": 4
  },
  "by_priority_label": "DECLARED",
  "opus_share_of_rows": 0.5179,
  "opus_share_label": "DECLARED",
  "paid_api_spend": {
    "label": "MEASURED",
    "available": true,
    "ledger": "backend/data/optimus/llm_calls*.jsonl (llm_telemetry.summary)",
    "since": "2026-10-07",
    "total_cost_usd": 0.25619,
    "total_is_lower_bound": true,
    "cost_is_estimate": true,
    "n_calls": 353,
    "n_unpriced_calls": 0
  }
}
```

`total_is_lower_bound: true` because `llm_telemetry` found unreadable ledger
lines and unpriced models (`gpt-5-nano` has no row in
`config.LLM_PRICE_PER_MTOK`) in the window — both are printed by
`llm_telemetry` itself, not swallowed by this module.

### Handoff block (pasteable)

```
### Session budget -- 2026-10-07-day (2026-10-07) [worker mix is DECLARED; paid-API spend is MEASURED]

- rows: 56 | opus share of rows: 0.5179 (DECLARED)
- by worker (DECLARED): deterministic=1, opus=29, sonnet=26
- by priority (DECLARED): p1=6, p2=8, p3=7, p4=20, p5=5, p6=6, p7=4
- paid-API spend since 2026-10-07 (MEASURED, backend/data/optimus/llm_calls*.jsonl (llm_telemetry.summary)): $0.25619 (lower bound) over 353 call(s)
```

## Reading

- **Opus share 0.5179** over the 56 rows logged — night one (C1-C14, build +
  review, all Opus) is the majority of the Opus mass; the morning wave and the
  third queue (C15-C26, R6-R11, Q1-Q10) are mostly Sonnet, matching §5b's
  10:20 operating-model reset ("Fable orchestrates ... Sonnet for research,
  reading, specs, docs ... Opus 5.5 only for financial decision architecture,
  measurement/backtest correctness, execution logic, concurrency/data-integrity
  bugs, major architecture, and adversarial review").
- **Priority mix**: 6 rows at priority 1 (capital/execution correctness: C2,
  C20, C26, Q2, Q7, plus C2's review), 8 at priority 2 (data/measurement),
  7 at priority 3 (bugs blocking the live loop), 20 at priority 4 (high-value
  research — the largest bucket, mostly the R-series notes), 5 at priority 5
  (forward-paper), 6 at priority 6 (product/UI), 4 at priority 7
  (nice-to-have, including this very Q10 task).
- **The only measured number**: $0.25619 (lower bound) in DeepSeek/OpenClaw
  spend recorded in `llm_calls*.jsonl` since 2026-10-07 — cheap relative to the
  56 declared rows above it, which is the point `llm_telemetry`'s own
  docstring makes: the paid-API side is not where this week's cost sits: the
  weekly strong-model (Opus) allowance is.

## Files

- `backend/services/session_budget.py` — the library (open/log/close/status,
  `opus_share`, `build_handoff_block`, `_paid_api_spend`)
- `scripts/session_budget.py` — thin CLI wrapper (`python -m scripts.session_budget`)
- `backend/tests/test_session_budget.py` — 27 tests: open/log/close round trip,
  idempotent close, every refusal path (missing priority, out-of-range
  priority, unknown worker, blank task/EV, logging after close or before
  open), `opus_share` arithmetic at the empty/half/all/none edges, the
  `MEASURED`/`DECLARED` labels on `_paid_api_spend` and the handoff block
  (including the "report unavailable, never a fabricated zero" path), `status`
  finding the open session, and two CLI-level refusals (argparse exits 2 on a
  missing or out-of-range `--priority`, writing nothing)
- `backend/data/optimus/session_budget/2026-10-07-day.json` — today's seeded
  receipt (56 rows, closed)
