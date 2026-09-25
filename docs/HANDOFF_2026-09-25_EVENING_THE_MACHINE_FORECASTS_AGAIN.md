# Handoff — 2026-09-25 evening — the machine forecasts again, and 20 books are on the clock

Continuation file. Read `ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md` first,
then this. Written by Fable 5.1 while Murat was away (his order: *"review
everything that has been done and validate them ... make paper accounts
locally and check them up every day, make sure the engine makes decisions
that we can then later judge, use openclaw and deepseek"*).

---

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none.** New today: the revision-flow month-end rule (top-20 by `net_raises × n_firms`, ≥3 firms, 21d hold) beats SPY by **+0.32%/hold, +0.02% with its worst year left out, t 0.94 on 121 holds** — a positive sign, not a result (`analyst/revision_flow_sweep_2026-09-25.json`) |
| best forward paper strategy | PC-PAPER **$1,000,000, connected (verified by one `GET /v2/account`), idle**; fleet unchanged |
| forecasts | **accrual restarted**: `u_forecast` wrote its first rows today (`investigator:evidence_v3`, h=1 and h=5, $0.03 for 14 names at the time of writing); nine personas RETIRED_WEIGHT_ZERO on the day receipt |
| books on the clock | **human_ai_thematic_v1** `a20a2b972988eec6` + 4 twins; `revision_flow_v0` + random twin; **6 factory books** (3 personal, 3 competition) + twins; 14 more regenerating after the rescale fix. Entry = Monday 09-28 open; first grade Monday night |
| thesis cards | **81 of 81** written ($3.07 for the day, ~$0.05/quest; 3 refused during the lid close and retried clean), `validate` 0 drift. Supports: 000660.KS, 010120.KS, 012450.KS, 2330.TW, 6857.T, 8035.T, ARGX, ENR.DE, ENS, GEV, HOOD, LDO.MI, LLY, MP, MU, NOVT, NVT, RGTI, TSM, VRT. **Against: AARD, BHVN, SLDP, QUBT (all held by Murat), CAPR, SRAD.** DKNG neutral |
| reputation | investigator arms weight 0.03–0.42, **every persona 0.0**; calibration overconfident above p≈0.15; k_prior unidentified (equal n) |
| LLM spend today | seed cards $0.65 · main cards ≈ $3.5 (68 × ~$0.05) · factory $0.09 + reruns · forecasts ≤ $2 cap · smoke calls $0.11 |
| suite | 10,794 passed, **3 failed, all local-data gates** (below); CI expected green |

**RESULT IMPROVEMENT: the machine now produces gradeable decisions every day
(forecast rows, review labels, frozen books). Nothing has been graded yet.**

---

## 1. What was built (five Opus builders, one Fable patch) — all committed, not pushed at time of writing

| commit | what | run it with |
|---|---|---|
| `017c7b1b` | **Reputation layer** (`forecast_reputation.py`): held-out per-arm skill, shrink→floor 0→γ→log-odds→κ, calibration curve, restricted-sample check; scoreboard prints `new_rows_since_last_run` | `python -m backend.services.forecast_reputation` |
| `9f588c17` | **Thesis cards** (`thesis_card.py`, `scripts/thesis_cards.py`): engine side + one OpenClaw quest + one DeepSeek synthesis per name, FLAT schema, resumable, capped | `python -m scripts.thesis_cards run --max-quests 40 --cap-usd 5 --parallel 2` |
| `fe7af5df` | **Revision flow** (`revision_flow.py`), the with/without sweep, the month-end rule backtest, `decision_autopsy.py`; two books frozen | `python -m scripts.revision_flow_sweep`, `python -m scripts.decision_autopsy` |
| `3f646b17` + `b89cdb0e` | **Book factory + daily grade** (`llm_portfolio.py` kind/constraints/twins/leaderboard, `global_prices.py`, `book_factory.py`, catalyst YAML with 31 primary-tagged rows) and **O1's sim units** (`accrual_canary.py`, `daily_review.py`, `u_forecast`, `u_review`, OpenClaw telemetry, session row at START) — the two commits are mislabelled because the builders shared one git index | `python -m scripts.llm_portfolio grade` (daily) · `python -m scripts.book_factory generate --kind personal --n 10 --notes …` |
| `369e031f` | Factory rescales an arithmetic slip inside a band and STAMPS it; `--only` | — |
| `c8275f17` | the roadmap, plans, book docs, seven research notes | — |

### Sim units now in every cycle
`reconcile → funnel → analyst → rank → forecast → plan → grade → learn`, and
`review` after 08:00 ET on weekdays plus on a >2σ intraday move.
- `u_forecast`: once per UTC day; universe = shortlist ∪ `murat_book.yaml` ∪
  every frozen book's names ∪ top revision activity; h=1 and h=5; caps
  `FORECAST_MAX_NAMES_PER_DAY=60`, `FORECAST_DAILY_CAP_USD=2.0` read from the
  same ledger the writer writes (refuses if the ledger does not move after the
  first call); a day with 0 rows is DEGRADED. Receipt `forecasts/day_<date>.json`.
- `u_review`: every held name (Murat's book, PC-PAPER, every frozen book) gets
  last close, 1d/5d move **in sigma**, the latest forecast, the next dated
  catalyst, and a label via `agency.decide_label` wrapped by the **patience
  rule**: a >2σ day is `WATCH`, never `sell`; the next session decides.
  Labels are `review:v0` forecast rows at h=5 so they get graded. Receipts
  `review/review_<date>.json` + `review/morning_<date>.md`.

### Health rows that can go red now
`forecast_accrual` (3 quiet days → DEGRADED; undateable → UNKNOWN), OpenClaw
`EMPTY_LOG`, collector liveness, `n_considered` stuck detector beside the
funnel's `n_candidates`, session rows written at START (a crash is visible).

---

## 2. Tonight's session
`f85bfe5cd999`, pid 61916, mode `paper_profit`, 8 h from 15:22 HKT (07:22Z)
→ 23:22 HKT. It forecasts today, reviews after 20:00 HKT (08:00 ET), and
will refuse to trade on the measured-negative ranker exactly as before — the
PROBE path into `u_plan` (chunk C3) is **not built**, so PC-PAPER stays idle.
The thesis-card run is pid 118060 (log under `thesis_cards/2026-09-25/logs/`).

---

## 3. Numbers that came out today

**Revision-flow sweep** (2,993 names, OOS 2021-2026, k=20, mean net relative return per hold):

| H | arm | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | worst k cell |
|---|---|---|---|---|---|---|---|---|
| 21 | base | −5.81 | −3.61 | +0.24 | −0.26 | +1.93 | +1.34 | −1.10% |
| 21 | flow | −4.64 | −1.92 | +0.47 | −0.42 | +0.55 | +2.72 | −0.67% |
| 63 | base | −8.41 | −8.93 | +0.99 | +3.24 | +2.94 | −2.20 | −2.09% |
| 63 | flow | −6.24 | −7.65 | +1.49 | +2.90 | +0.82 | −0.26 | −1.65% |

Flow improves every worst cell except H=5 and **both arms lose net at 21 and
63 days**; small caps −0.16% (flow) vs −0.53% (base). The month-end rule by
year vs SPY: 2016 −0.61, 2017 +0.15, 2018 +0.24, 2019 +0.51, 2020 +3.01,
2021 −1.25, 2022 −0.89, 2023 +0.53, 2024 +0.57, 2025 −0.23, 2026 +1.54.
Only 64 of 1,784 dead names have revision history — both arms are survivor-
selected on that axis. **Q-10: RUNNING as a book, not a result.**

**Decision autopsy** (225 rows, 6 days, 1-day horizon only): BUY n=4 −0.74%
vs SPY (both losers CVLG); PROBE n=114 −0.36%, 42% up; REFUSED n=41 −0.54%,
39% up; 16 refused names rose (META +8.0%, ANIP +3.5%). 51 forecasts since
09-11, none graded at their own horizon yet.

**Reputation** (held out by date): investigator D_all +6.0% (w 0.42),
A_snapshot +5.0% (0.25), C_tools_only +5.0% (0.24), B_tools +3.1% (0.06),
B_anon +2.5% (0.03); macro_rates −20.7% … biotech_pharma −70.0%, all 0.0.
γ=3, κ=1.0; k_prior unidentified. h=1 calibration: stated 0.58 → realised
0.48; stated 0.29 → 0.20. Restricted-sample check binds on 0 rows (every
graded row postdates 08-11) — the Profit-Mirage question is still open.

**Book factory**: DeepSeek could not add — 14 of 20 books came back at
1.02–1.54 total after a re-ask. Fixed by rescale-and-stamp (band 0.90–1.15,
or 0.85–1.60 when the model stated its cash). The local llama-server never
saw a prompt: its context is 8,192 tokens and the prompt is ~45k — restart it
with a larger context or write a shorter local prompt.

---

## 4. The three red tests are local-data gates, not code (verified)
- `test_e2_embedding_horizon::…vintage_gap…` and `…reconstructs…`: a stored
  panel vs today's bars at 1e-9; bars were re-pulled (median diff 5.7e-6).
- `test_the_two_night_clocks::…BY_CANCELLATION`: pins 205.5 min from
  `derive_calls_per_cell()`, which reads local night receipts; the untracked
  09-24 night raised the max to 7.14 → 207.1. **Passes on a clean worktree of
  daa6c062** (no untracked receipts) — so CI is green and the local tree red.
- `test_x_lane_receipt_completeness`: an untracked `X2_elasticity_run01.json`
  from 09-21 lacks its protocol block.
All three are protocol-item-5/7 family (a fixture pinned to a growing local
dataset). Fix in a later session: skip-with-reason when the local data
postdates the fixture, or freeze the receipt set the test reads.

---

## 5. Murat, when back
1. **Register for the challenge by Oct 5** and read the export rule.
2. The v1 book is frozen; your line edits become **v2** (a new book, the v1
   clock keeps running). Reply in sentences; I write them.
3. QUBT: the card says **against / high** (gross margin −21%, acquired lines
   shrinking, goodwill litigation). It stays at 1% only because you hold it.
4. Restart llama-server with `-c 16384` or larger if you want the local model
   in the factory pairing.
5. Read `review/morning_2026-09-25.md` tomorrow morning: the first labels.

## 6. Must not regress (added tonight)
- Builders sharing one git index commit each other's staged files. One builder
  per index, or `git commit <paths>` only after `git status` shows no foreign
  staged paths.
- A factory that refuses an LLM's arithmetic loses the book; rescale inside a
  band and stamp, refuse outside it.
- `predictions.jsonl` moved today (u_forecast rows). Never reset.

---

## 7. Evening 2 (18:30 HKT) — the review loop ran once, PROBE is live, v2 is frozen

- **Chunk 1 landed** (`7311dae2`): `u_plan` now takes the committee shortlist
  under PROBE (10 names × 2%, gross cap 20%, `paper_profit` only, orders only
  while the venue is open, never a second order on a symbol with one open;
  every PROBE name writes decision rows at 5/21/63/126 sessions to
  `decisions/pc_plan/<date>.json`). The sim was restarted on it (session
  `f85bfe5cd999`, pid 97412): cycle 17 planned NVDA, INCY, AAPL, SNDR, META,
  AVPT, AMZN, GOOGL, GOOG, ALLE at 2% each, `send_block: venue closed`. **The
  first PC-PAPER orders in the account's life go out at the 21:30 HKT open.**
  Worst case: `10 × 2.00% × 8.23% (3σ of 2.74%/day) = −$16,452; gross 0.20;
  no stop, ceiling −$200,000`.
- **The first adversarial review** (`docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md`)
  and its adjudication (`ADJUDICATION_2026-09-25_CHUNK0.md`): 13 of 14 points
  accepted. The line that matters most: the investigator's 0.42 reputation
  weight is MAGNITUDE skill; on direction at h=5 its most bullish bin rose
  35.5%. Chunk 2 keeps direction and magnitude apart (spec committed).
- **Books frozen tonight:** `human_ai_thematic_v2` `5d137b013692a737` (from the
  review Murat forwarded; AMZN rejected), `reviewer_opus_2026-09-25`
  `919892d54f6e3190`, `cards_supports_2026-09-25` `89761b53e2cd82ba` (the 20
  supports names, no human hand). v1 keeps running as the un-reviewed control.
- **Cards:** 84 (AVGO supports, CLS and BE neutral). Forecast rows per card:
  builder in flight. Forecast universe: standalone random twin excluded, cap
  160 (`98b3cd8d`). Test gates: E2 skips on a different bar vintage, the
  night-clocks test reads its own fixture, a factory kill payload is refused
  as a kill (`40111a01`, `aa279c53`).
- **Next:** chunk 2 (the expected-return layer) is building; chunk 3 (the
  timeline panel) has its research; chunk 5 needs the FX leg before any
  competition book is graded fairly; Murat's X account for chunk 6.
