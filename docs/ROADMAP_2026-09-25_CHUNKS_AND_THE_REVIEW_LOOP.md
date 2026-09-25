# ROADMAP 2026-09-25 (evening) — the chunks, and the review loop that attacks each one

**Status: ACTIVE TIER 1 amendment to `ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md`.**
Murat, 2026-09-25 evening (condensed): *divide the roadmap into chunks; Sonnet
researches, Opus builds, and after every chunk ANOTHER Opus reviews the work
as an investor and profit maximiser — "you are wrong, I would have done
this"; the reviewer proposes new ideas and Sonnet researches them and other
projects; make local paper accounts we review and learn from; first test the
engine in the Bloomberg competition, then maybe real money; use the
accumulated data for backtests — "a dot in a timeline": at one date combine
every numerical signal, social cue, news item and analyst forecast, look six
months later, learn the connections; focus on CEOs, politics and pivots (the
future, not the history); social cues (X login pending).*

The external review he forwarded (GPT, same evening; kept in
`research_notes/2026-09-25/external_review_v1_book.md`) names the same
bottleneck the audit found: **the best new intelligence sits beside the
ranker instead of inside the expected-return decision.** Its verdict on the
v1 book — "the theme selection is stronger than the individual stock
selection; too many interesting stories" — became v2 (§4).

---

## 1. THE LOOP (how every chunk runs from now on)

```
Sonnet research (reads, repos, papers, the market)  ─┐
                                                      ├─► Opus BUILD (tests, receipts, commit)
prior chunk's reviewer ideas ────────────────────────┘          │
                                                                ▼
                       Opus REVIEW — as an investor and profit maximiser:
                       "you are wrong; I would have done this; here is how"
                       + three new ideas + one thing to delete
                                                                │
                       Fable adjudicates: accept / reject each point, with a
                       receipt; accepted points become the next chunk's spec;
                       ideas go to Sonnet research; the review is a doc
                       (`docs/reviews/REVIEW_<date>_<chunk>.md`)
```

Rules of the loop:
- The reviewer never edits code. It reads the chunk's diff, its receipts, the
  live data, and the money question: *did this move expected terminal wealth
  or the ability to grade a decision?* A chunk that did neither is a failed
  chunk however green its tests.
- Every decision the machine makes is written so it can be graded later
  (forecast row, decision-ledger row, frozen book) — the reviewer checks
  this first.
- Guardrails are judged by what they cost: a guard that blocked no bad
  decision this month and blocked a good one is removed, with a receipt.

## 2. THE CHUNKS, in order (one Opus build at a time; reviewer after each)

| # | chunk | build | research (Sonnet) | done when |
|---|---|---|---|---|
| **1** | **PROBE path** — the committee shortlist reaches `u_plan` at probe size; every PROBE row lands in the decision ledger | in flight (Builder C3) | — | the next sim cycle places probe-sized paper orders on PC-PAPER and the ledger has PROBE rows |
| **2** | **THE EXPECTED-RETURN LAYER** — `expected_return.py`: per name and date, `E[r_h] = w_m·ranker + w_a·revision_flow + w_i·(calibrated investigator p→return) + w_t·thesis_verdict + w_c·catalyst_state + w_s·source_reliability + w_r·regime(market_sensor)`; every component is a separate column with its own forward grade; the weights come from `forecast_reputation` machinery (shrink, floor 0, refit each `u_grade`), never hand-set; `u_plan` sizes on `E[r]` under the five states | Opus | how others fuse heterogeneous signals forward (stacking with time-decay, Bayesian model averaging, GJP weighting); what to do when a component has n<30 | the plan receipt shows each name's E[r] decomposed by component, and the decision ledger carries the decomposition so the autopsy can say which component was wrong |
| **3** | **THE DOT ON THE TIMELINE** — `world_state_panel`: for (ticker, date) join the 23 price features, revision flow, news counts + typed events, social (LunarCrush/Reddit when present), forecasts, thesis-card verdicts, catalyst distance, insider/13F/Congress rows → outcomes at 5/21/63/126d; a harness that prints IC by year, LOO, worst cell, and **pairwise signal correlations** (is the news signal just momentum?); the survivor-selection audit on every column | Opus | event-study / signal-fusion panels in the open (Sonnet: repos + papers; the 94-query cue) | the first receipt of "which signals carried information about six-month outcomes, and which were the same signal twice" |
| **4** | **FUTURE-FACING QUESTS** — OpenClaw quest templates on *what is changing*: CEO/founder track record and promises vs delivery, pivots (the GoPro-style business-model switch), political/regulatory exposure, supplier/customer shifts; triggered on change (shortlist entry, revision cluster, 8-K, >2σ move); each quest ends in a forecast row; DeepSeek paired with the local model on a **short** prompt (the 45k-token factory prompt never fit the 8k context) | Opus | management-language-delta and promise-tracking literature; earnings-call Q&A evasiveness | `investigator:pivot_v1` rows accrue nightly and are graded |
| **5** | **THE COMPETITION ENGINE** — `competition_book.validate`, WLS check (Murat's Terminal export), five books frozen Oct 9 under `grand_prize` (Murat: 10%/name, +50% target), the tournament policy (BASE median / ATTACK EV), daily grade vs the WLS proxy; **this is the test of the engine Murat wants before any real money** | Opus | how the top-1% teams concentrated (the 2024/2025 write-ups), catalyst density inside Oct 12–Nov 13 | five books + twins on the leaderboard by Oct 9 |
| **6** | **SOCIAL CUES** — X once Murat has an account; LunarCrush and Reddit into the panel with `first_seen_utc`; attention *acceleration normalised by the name's own baseline*, graded, never a raw mention count | Opus | retail-attention and forward-return literature (Barber–Odean; WSB papers) | a social column in chunk 3's panel with its own IC line |
| **7** | **REVIEWER'S IDEAS** — whatever the chunk-1..6 reviewers proposed and Sonnet found evidence for | — | — | a spec per accepted idea |

Standing: every chunk's build starts by printing the worst case in dollars
for the largest admissible book, and ends with the reviewer's doc.

## 3. WHAT MURAT DOES
1. Register for the challenge by Oct 5; the WLS constituent export.
2. An X account for OpenClaw (chunk 6).
3. Read the reviewer docs; overrule with a sentence when he disagrees.
4. Real money is a separate decision after chunk 5's leaderboard exists —
   nothing here arms it.

## 4. THE v2 BOOK (from the review he forwarded; frozen beside v1, v1 keeps running)
Accepted from the review: core VRT/GEV/MU/TSM/HOOD/NVT/MP/VRTX/WST/COGT;
NOVT 6→3, ENS out (BE takes the power slot), LEU 4→2, RGEN 2→1, PRAX 4→1,
IONQ 1 (RGTI out — "don't own both"); QUBT, CAPR, SLI, ALB removed; COGT 1→3,
VKTX 2→3, AGIO 3→2; AVGO, CLS, BE added. **Rejected:** AMZN — a mega-cap is a
sensor, not the six-month asymmetry this book is for (`AEGIS_STRATEGIC_INVARIANTS` 4),
and it would be the fourth AI-infrastructure large cap in the book. GILD
dropped to make room (the review called it a stabiliser; this book is not
for stabilisers). Draft: `research_notes/2026-09-25/book_human_ai_thematic_v2.draft.json`.
