# Review: forecasts and frozen/shadow books, 2026-09-29 -> 2026-10-02

Read-only review. Every number below is traced to a file path. "Today" for this
review is 2026-10-02; the newest priced session in almost every local pipeline
is **2026-09-28** (see Finding 0) — that gap is the finding, not a data-entry error.

## RESULTS SCOREBOARD

| item | value |
|---|---|
| best historical net strategy vs the market | unchanged this window (library leaderboard has not been regenerated since 2026-09-30 00:12 — see Finding 0) |
| best forward paper strategy | contest rehearsal desk, 09-30 sheet: **+4.66% relative to its benchmark proxy over 2 sessions, 0bps** (+4.28% at 25bps), but 93% of the gain is one name's post-earnings pop (ACN +21.3%); licensed `PRODUCT_EXPERIMENT`, "never evidence of skill" |
| independent selector count | no change (13 of ~32 library books currently pass the freeze gate; unchanged since 09-30) |
| farm candidates tested / promoted | 0 / 0 this window |
| new actionable finding | **the shared daily bars panel (`prices_2025_26/bars.parquet`, 3,060 symbols) stopped advancing after 2026-09-28 and has not moved in 3 straight scheduled refresh attempts** (09-29, 09-30, 10-02 — all refused on `HTTPError: HTTP Error 400: Bad Request`; 10-01's scheduled run is missing from the index entirely). This freezes the forecast grader, the strategy-library leaderboard, and the sim's ranker simultaneously |
| RESULT IMPROVEMENT | **NONE measurable.** The forecast ledger has graded zero new outcomes since 2026-09-29 (frozen at 17,783 resolved) while the ledger grew from 31,491 to 32,910 rows and the backlog of forecasts "past due and unresolved" grew from 0 to 172 (health status DEGRADED since 10-01). The owner's question — is the engine measurably better on pre-registered forecasts — **cannot currently be answered**, because almost nothing new has been graded in the window asked about |
| external execution drag | not newly measured this window (straddle forward log is still pre-entry) |
| LLM spend / cost per gradeable output | sim session `ad32603783de`: $1.12 forecast spend over 8h, zero new orders, zero net new gradeable rows beyond what the ledger already had queued |

---

## 0. The root cause that explains most of what follows

`backend/data/optimus/prices_2025_26/bars_refresh_index.jsonl` (last 4 entries):

| run | status | newest bar | sessions old | reason |
|---|---|---|---|---|
| 2026-09-28T22:30 | ok | 2026-09-28 | 0 | — |
| 2026-09-29T22:30 | **refused** | 2026-09-28 | 1 | `HTTPError: HTTP Error 400: Bad Request` |
| 2026-09-30T22:30 | **refused** | 2026-09-28 | 2 | same |
| *(no run logged 2026-10-01)* | — | — | — | — |
| 2026-10-02T03:58 | **refused** | 2026-09-28 | 3 | same |

The refresher correctly **refused to overwrite the panel with a failed pull** rather
than corrupting it (`backend/data/optimus/prices_2025_26/bars_refresh/20261002T035834Z.json`),
but the effect is identical to the "static file" failure mode already in house
memory: every downstream consumer of this panel has been reading 2026-09-28 data
for three sessions running. Confirmed directly from the parquet file itself
(`prices_2025_26/bars.parquet`, mtime 2026-09-29 06:31, max `date` column =
2026-09-28).

Consumers affected:
- `backend/services/forecast_grader` (Finding 3) — graded count frozen at 17,783.
- `backend/data/optimus/strategy_library/leaderboard_2026-09-29T160819Z.json` — last
  written 2026-09-30 00:12; the SAME file is cited as the input by
  `bridge_2026-09-30.json`, `bridge_2026-10-01.json`, and `bridge_2026-10-02.json`
  (`backend/data/optimus/bridge/bridge_2026-10-0{1,2}.json` field `leaderboard`).
- The sim's `rank` unit, every cycle: `"skipped": "bars unchanged since the last
  rank"` (`backend/data/optimus/sim/session.json`).

Not affected: the **contest rehearsal desk**, which fetches its own live
`yfinance` quotes independently (`price_source: "yfinance"` in every
`backend/data/optimus/contest/rehearsal/grades/grade_*.json`) — which is why it
is the only part of the system below showing genuinely fresh, moving prices.

## 1. Frozen library books vs. matched twins (3-4 sessions claimed, 1 real)

The bridge's `rows` array (the per-book library forward record) is **byte-identical
across all four days** — same `forward_return`, same `sessions_since_entry: 1`,
same `forward_relative`, in `bridge_2026-09-29.json` through `bridge_2026-10-02.json`.
This is Finding 0 again: nothing new has been priced in since the 2026-09-28->29
entry session.

Distribution across the 31 graded library books, one session (`bridge_2026-10-02.json`
field `rows`, `forward_relative`):
mean **+0.33%**, median **+0.37%**, 23 of 31 positive, range -3.52% to +2.15%.

Of those, only the 13 that pass the full freeze gate (selection + construction +
timing, `backend/data/optimus/bridge/freeze_gate_2026-10-02.json`, unchanged
13/32-33 pass since 09-30) are a candidate set at all: mean **+0.62%**, median
**+0.46%**, 11 of 13 positive.

**No pooled cluster z is printed anywhere in the bridge file** (checked all keys
of `bridge_2026-10-02.json`; the closest fields are `distinct_bets` — 18 distinct
bets behind the 32 sealed books, cluster-level `forward_relative_one_observation`
— and `level2_pairs`, a within-cluster decomposition, neither of which is a
pooled z). `docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md`'s own
honest prior: on the backtest only 2 of 288 cells cleared t>=2 against the twin
in both windows, against ~0.8 expected by chance — a null is the pre-registered
expectation.

**One session of real data, re-served four times, decides nothing.** The
13/31-positive counts above are descriptive, not evidence.

## 2. Shadow books vs. twin and vs. SPY since entry

(`backend/data/optimus/llm_portfolio/leaderboard_2026-10-02.json`, `grades`,
`to_date`, bars through 2026-10-01, 3 forward sessions since the 09-28 entry)

| book | book_id | net to-date | vs SPY to-date | twin net | twin vs SPY |
|---|---|---:|---:|---:|---:|
| CRSP_BLEND_v0 | `b0a33a92c56fddb1` | **+1.13%** | **+1.50%** | -0.30% | +0.07% |
| SHADOW_BAYES_v1 (live-size) | `0f038859b2ebea62` | -0.40% | -0.03% | -0.41% | -0.04% |
| SHADOW_BAYES_v0 (sleeve) | `439fd84f869744e0` | +0.56% | +0.93% | — | — |
| human_ai_thematic_v1 | `a20a2b972988eec6` | -0.94% (4 sessions) | -0.37% | — | — |

- **CRSP_BLEND_v0 is ahead of its twin and SPY**, but it is 3 of its 21-session
  first-read horizon — `backend/data/optimus/shadow_bayes/AMENDMENT_CRSP_BLEND_v0_KILL_RULE_2026-09-29.json`
  fixes the first reading at **21 sessions after the 09-29 entry**, not now.
  **Kill-rule status**: the amendment found the registered kill line's noise-sd was
  never actually computed for this book; the only implementation (idiosyncratic-only)
  gives a kill line near -4.7% with a **~21% false-kill rate**, not the intended 5%.
  Decision: **keep the book, do not void it, treat the forward record itself as
  the evidence** (`owner_decision` field). The backtest-level review
  (`docs/reviews/REVIEW_2026-09-29_CRSP_BLEND.md`) separately flagged the
  selection procedure as chosen after looking at 40,920 candidate blends and
  failing forward on fixed splits — verdict on the procedure: **CANNOT_DISTINGUISH,
  DEPRIORITIZED as a lead**, kept only as a free shadow.
- **SHADOW_BAYES_v1 is statistically indistinguishable from its own twin**
  (-0.40% vs -0.41%) — the live-size rule is not yet separating itself from a
  matched null.
- **human_ai_thematic_v1** is the one book clearly behind both SPY and zero
  across its first week; one of its Asia names (`2330.TW` etc.) sat in cash
  several sessions on `NO_BAR_ON_ENTRY_SESSION` (`leaderboard_2026-10-02.json`,
  `deferred_entry`).
- **SHADOW_NEWS_v0** (`backend/data/optimus/news_digest/shadow/decisions.jsonl`,
  16 rows, one per digest cycle 09-29 -> 10-02): `trust_dir` and `trust_size`
  are **0.0 in every single decision row**, and `shadow` weights equal `base`
  weights to 4 decimal places throughout. The news-tilt has not yet been allowed
  to move any weight in this window — it is still in a pure observation/burn-in
  state, not a result.

## 3. The forecast ledger

`backend/data/optimus/predictions.jsonl`: 32,957 total rows as of 2026-10-02
18:31 (grew from 31,491 on 09-29 to 32,910 by the 10-02 grading run).

Rows written by writer prefix (`specialist` field), by day:

| writer | 09-29 | 09-30 | 10-01 | 10-02 |
|---|---:|---:|---:|---:|
| investigator | 810 | **0** | 600 | 0 |
| review | 1,165 | 0 | 0 | 0 |
| thesis_card | 2 | 0 | 0 | 0 |
| news_digest | 339 | 240 | 224 | 194 |
| source | 219 | 18 | 0 | 0 |
| nn_lab | 0 | 0 | 0 | 0 |

**Forecast accrual went to zero for `investigator`, `review` and `thesis_card`
on 2026-09-30**, resumed partially for `investigator` on 10-01 (no `review`,
no `thesis_card` since 09-29), and was zero again for everything but
`news_digest` on 10-02. `nn_lab` wrote nothing to this ledger in the whole
window (0 rows found anywhere in the file).

**Grading itself has been stuck since 09-29**, independent of writer activity
(`backend/data/optimus/night_factory_2026-10-0{1,2}/grade_forecasts_*.json`):

| grading run (date) | n_records in ledger | graded (cumulative) | newly resolved | past-due & waiting on a bar | health |
|---|---:|---:|---:|---:|---|
| 09-29 | 31,491 | 17,783 | 0 | 0 | ok |
| 09-30 | 31,675 | 17,783 | 0 | 159 | ok |
| 10-01 | 31,939 | 17,783 | 0 | 172 | **DEGRADED** |
| 10-02 | 32,910 | 17,783 | 0 | 676 | **DEGRADED** |

This is Finding 0's direct consequence: the grader reads the same
`prices_2025_26/bars.parquet` that stopped advancing at 2026-09-28, so nothing
with a resolution date after that has been able to resolve, regardless of how
many new predictions are written.

The sim session separately hit an explicit **`REFUSED_DEPENDENCY_DOWN`** state
on its `forecast` unit in **every one of its 91 logged cycles** on 2026-09-29
(`sim/session.json`): "the OpenClaw call failed 4 time(s) in a row on AMZN...
Run 1 ended down (1 of 8 allowed today)." This is a second, independent cause
of degraded forecast accrual (an LLM-dependency outage), separate from the
stale-bars cause above.

**The only skill-by-writer numbers that exist anywhere in this window** are
from the single `learning_reports/report_2026-09-29.md` (no report has been
produced for 09-30, 10-01 or 10-02 — consistent with nothing new having been
graded to report on):
- `abs_move_exceeds` h=1: the free sigma_63 volatility prior beats the live LLM
  arms' posterior, +14.13% vs +10.62% (n=875 held out); only `investigator:B_anon`
  individually beats the prior on its own rows.
- `abs_move_exceeds` h=5: prior +5.92% vs posterior +2.62% (n=775); only
  `investigator:D_all` beats the prior on its own rows.
- `return_sign` (direction) h=5: the live LLM arms score **-7.91%** held out
  (n=780) — worse than the base rate, i.e. negative skill; worst single cell
  `investigator:C_tools_only` at -11.73%.

**News_digest 5-session grades**: confirmed **none have matured** — the first
digest is dated 2026-09-29, so 5-session maturity is not due until ~2026-10-06
at the earliest for the first ones (the task's 2026-10-09 figure refers to a
specific later cohort); in any case the grading pipeline is not currently
resolving anything new regardless of due date (see table above).

## 4. Sim session `ad32603783de`

`backend/data/optimus/sim/session.json`: mode `paper_profit`, started
2026-09-29T15:52:47Z, ended 2026-09-29T23:56:19Z (~8h01m, requested 8h00m),
state **COMPLETED** cleanly (no UNCLEAN end), 90 logged cycles plus one
`resumed_from` cycle (91 total).

- **First cycle lost ~83 minutes again**: the `resumed_from` cycle's `analyst`
  unit took **4,967s (82.8 min)**, flagged by the session's own `slow` note
  ("4967s exceeds SLOW_UNIT_S 1800s; reported, not killed"). This reproduces
  the pattern house memory already names ("whether its first cycle lost 80
  minutes again") — yes, again.
- **Forecast**: `REFUSED_DEPENDENCY_DOWN` in all 91 cycles (see §3); total
  forecast spend across the session $1.12 (`sum of spent_usd` field).
- **Orders**: **zero**. Every one of the 90 logged cycles had
  `plan.verdict == "MEASURED_NEGATIVE"` and `plan.mandate_gates_orders == False`
  — the mandate reconciliation gate (two disagreeing capital bases, $40,000 vs
  $1,000,000, with correspondingly different caps) blocked every order the
  whole 8 hours. Equity moved only from mark-to-market of the 10 pre-existing
  positions: $999,596.58 -> $999,278.15 (-0.03%).
- **What it learned**: the `learn` unit mostly reported `idle` ("rota rest
  slot; the market loop owns the session") or ran diagnostics unrelated to new
  trading experience — `survivorship_audit` (42.4% of 5,586 symbols stop
  trading before the panel ends — delistings are represented, a health check,
  not a policy update) and `breadth_check`. No `policy_state.json` change
  attributable to new trading was logged this session, because no new trades
  occurred.

## 5. Contest rehearsal desk

Sheets generated every day 09-29 through 10-02
(`backend/data/optimus/contest/rehearsal/sheets/<date>/desk_sheet.md` +
`orders.json`) — **the daily task ran each day without a gap**. However, the
grading pipeline (`.../grades/grade_*.json`) only starts tracking positions
from the **09-30** sheet onward: the 09-29 sheet's five picks (CNXC, AIR, FDS,
JBL, CALM) were frozen and ordered but **never appear in any grade file** —
effectively dropped from the graded record, not carried forward or voided
explicitly.

From the 09-30 sheet (5 names, 20% each, entered at the 09-30 open; priced
live via `yfinance`, independent of the stale local panel — see Finding 0),
closed at the 10-01 session (`grade_20261002T063006Z.json`):

| symbol | entry px | exit px | return (local) | P&L (USD) |
|---|---:|---:|---:|---:|
| PRGS | 39.44 | 40.52 | +2.74% | +$5,220 |
| MU | 1076.76 | 1054.08 | -2.11% | -$4,082 |
| AYI | 309.97 | 306.44 | -1.14% | -$2,196 |
| ACN | 178.10 | 215.98 | **+21.27%** | **+$41,327** |
| 4088.T (Japan) | entered 10-01 (delayed one session) | still open | — | — |

Book return (0bps) over the 2 closed sessions: **+4.03%**; at 25bps round-trip
cost: **+3.64%**. Benchmark (ACWI proxy, WLS stand-in) over the same window:
**-0.64%**. Relative: **+4.66%** (0bps) / **+4.28%** (25bps). **93% of the
dollar P&L is the single ACN earnings surprise** — the sheet's own framing
states "zero directional skill is assumed... sells variance for rank," and
this result is consistent with that: one concentrated binary event dominating
a 5-name, 20%-each book.

10-01 sheet: bought 1 name (NKE, entry 35.45, still open at the 10-02 grade).
10-02 sheet: 0 buys (none eligible that day), sold NKE. No cumulative P&L
figure yet beyond the 09-30 cohort above.

## 6. World digests

16 digest files ran over the window (`backend/data/optimus/digest/world_digest_*`),
roughly every 4-7 hours, spanning 2026-09-29 02:58Z to 2026-10-02 10:30Z.
Recorded spend is **$0.00 in every one of the 16 files** (field `spend.usd`) —
flagged as worth independent confirmation rather than taken as a true zero,
since a reader that is always zero is a known failure shape elsewhere in this
system.

Themes that persisted across the full 4-day window (appearing, under slightly
varying headlines, in all or nearly all 16 digests): **global bond rout /
Treasury yields to multi-decade highs**, **AI chip and data-center capex
boom**, **US-Iran tensions / oil above $100**, and **China property easing**.
Later entrants: Apple product-launch coverage (from 10-01), a Flydubai
cockpit-attack/terrorism story (from 10-01), a US military leadership shakeup
(10-02).

**Early informal read only, not a verdict**: the per-ticker `already_moved`
sigma fields attached to themes are themselves computed off the same frozen
bars panel — every digest from 09-29 evening through 10-02 10:30 reports
`last_bar: "2026-09-28"` inside `already_moved`, so this check has been blind
to any price action since the panel froze. On the one digest where the sigma
check still reflected a live same-day bar (09-29 02:58Z), none of the "AI
infrastructure boom" theme's lead tickers had moved beyond 1 sigma in the
bullish direction that day (NVDA the largest at +0.69 sigma); no clean
directional read is possible for the theme's remaining three days.

## Trials

- **TRIAL-PT-REVERSAL-1**: registered 2026-09-29, read exactly once the same
  day (`backend/data/optimus/ft_lab/receipts/pt_reversal_read.json`). Gross
  fade mean **-0.14%** (t -0.91, 723 cells, 206 dates, 52 weekly blocks) —
  the decision rule's "refuted at this power" branch fires (mean <= 0) ->
  **FAILED_VARIANT**; the lead is `RETIRED_FROM_CURRENT_SEARCH` for this
  implementation (not price-target information generally).
- **TRIAL-CONTEST-MAG-1**: pre-registered 09-29; its evaluation window does
  not open until 2026-10-12 — **no data to read yet**, as designed.
- **TRIAL-STRADDLE-FWD-1**: contract frozen 09-29; first scheduled entry
  2026-10-16 — **no data to read yet**, as designed. Its one concrete finding
  so far is cost-related: at 09-28 closing quotes, only 164 of the 400 most
  liquid optionable names passed quote filters, with median straddle spread
  11.5% of mid (21.2% across all quoted names) — real execution drag looks
  larger than the lab's assumed 10%.
- **TRIAL-LIB-FWD-TWIN-1** governs §1's comparison; its own honest prior
  (weak, ~0.8 false positives expected by chance at the backtest's own hit
  rate) is the correct lens for reading the one-session numbers above.

---

## WHAT WORKS

- The bars refresher correctly **refuses rather than corrupts** on a failed
  vendor pull (3 refusals in a row, 0 rows silently dropped or overwritten).
- The forecast grader's own health flag correctly flipped to **DEGRADED** once
  forecasts started piling up past due (10-01 onward) — the earlier "zero that
  stays zero forever" failure mode did not recur here; it just hasn't been
  *acted on* yet.
- The contest rehearsal desk ran every single day, end to end, on its own
  live price feed, independent of the frozen local panel, and produced the
  only genuinely fresh forward numbers in this review.
- CRSP_BLEND_v0's kill-rule review is a model instance of the house discipline:
  the false-kill rate was checked (found wrong, ~21% not 5%), the book was
  kept rather than killed on a broken rule, and the first real read was
  explicitly deferred to 21 sessions rather than read early.

## WHAT DOES NOT

- **The forecast ledger has produced zero newly graded outcomes since
  2026-09-29**, which is the one thing the owner's question depends on. The
  learning report, skill-by-writer numbers, and "what currently works" section
  have not updated since that date for the same reason.
- **`investigator`, `review`, and `thesis_card` forecast writers went dark on
  09-30** and have not fully resumed (no `review` or `thesis_card` rows at all
  since 09-29); `nn_lab` wrote nothing to the ledger in this window at all.
- **The strategy-library leaderboard has not been regenerated since
  2026-09-30 00:12**, so the "library books vs twins" comparison in every
  bridge file from 09-30 onward is the identical single session served three
  times, not three to four sessions of evidence.
- **The sim's 8-hour 09-29 session placed zero orders** (mandate capital-base
  disagreement) and its forecast unit was refused for the entire run (OpenClaw
  dependency down) — an 8-hour, $1.12 session that generated no new trading
  experience and no policy update.
- **The contest rehearsal's day-1 picks (09-29) were silently dropped** from
  the graded record rather than carried forward or explicitly voided.

## HIGHEST-EV EXPERIMENT

**Fix or route around the bars-vendor HTTP 400 before anything else.** It is
the single point of failure gating every other forward-evidence question in
this report: the forecast grader, the library leaderboard, the sim's ranker,
and (for its stale sigma checks) the digest pipeline all read the same frozen
panel. Until a session gets a clean refresh (or a documented reason the vendor
pull keeps failing and a fallback path), no amount of new signal work can be
measured, and the owner's actual question — is the engine getting measurably
better on pre-registered forecasts — stays unanswerable by construction, not
because the engine is bad.
