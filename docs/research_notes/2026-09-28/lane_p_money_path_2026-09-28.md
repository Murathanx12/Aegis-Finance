# Lane P: the paper money path, verified then built (2026-09-28)

## 0. FIRST: the forecaster was dead and health said it was alive

**The daily forecaster wrote 0 rows on 2026-09-27, and the health page printed `u_forecast ALIVE`.** That
unit (`investigator:evidence_v3`) is the only input the expected-return layer is waiting on. This lane's
first version saw `REFUSED_CAP, n_rows_written 0` and filed it as a sub-bullet. The review
(`docs/reviews/REVIEW_2026-09-28_LANE_P_MONEY_PATH.md` F1) was right to put it first, so it goes first here.

What I verified from the ledger and receipts (every figure below is re-read, not copied from the review):

| check | finding |
|---|---|
| `predictions.jsonl`, `investigator:evidence_v3` rows by `made_at` | 09-25 **118**, 09-26 **270**, 09-27 **0**. For 09-28 there is no day receipt yet. The sim ended 2026-09-27T23:58Z, and at 06:45Z no process is running. So 09-28 is **not run yet, not lost**: the review counted it before the day's run was due. |
| `forecasts/day_2026-09-27.json` | `REFUSED_CAP`, 0 rows, `spent_usd 0.0`, first-flush `ledger_delta_usd 0.0`, 55 s long |
| the one call that day (`llm_calls_2026-09.jsonl`, `310e3938c3ddf247`, 07:51:32Z) | `RC_NONZERO`, rc 1, 0 tokens, error *"Gateway agent call connection closed ... (1006 ...)"*. **The call failed. The cap was not involved.** |
| cap vs spend | `FORECAST_DAILY_CAP_USD` is $2.00. Spend was $0.1456 on 09-25 (59 OK calls; OpenClaw's own figure $0.149) and $0.3159 on 09-26 (135 OK; $0.3284). The reader and the writer agree within 2–4%, and spend was 7–16% of the cap. **The cap never came close to binding.** |
| health `health_20260927T235132Z.json` | `u_forecast ALIVE ... 167 made today`. Those 167 rows were `thesis_card` (134) and `source` (33). |
| the earlier outage (same shape, different cause) | rows by day: 08-25 600, 08-26 585, 08-27 600, then 11 on 09-11 and 40 on 09-24, and nothing on any other day, while the health page stayed green |

**Root cause (three defects in a row):**
1. `daily_forecast` ran its first-flush check (`if delta <= 0: REFUSED_CAP`) on the first call that carried a
   `call_id`, whether or not the call succeeded. A failed call costs $0, so an outage looked like a cap that
   cannot bind.
2. `REFUSED_CAP` was a terminal state in both `daily_forecast` and `sim_run.u_forecast`, so no later cycle retried.
3. `system_health.p_u_forecast` read `max(made_at)` over every specialist, so any other writer kept it green.

**Fixed (smallest change first):**
- **a. Every refusal names its true cause.** There are now three states:
  - `REFUSED_CAP`: the ledger is readable and complete, and spend is at or over the cap.
  - `REFUSED_CAP_READER_DISAGREES`: a *successful* call left the ledger unmoved, or the ledger is unreadable,
    or its total is only a lower bound.
  - `REFUSED_DEPENDENCY_DOWN` (new): the call failed with `TIMEOUT` or `RC_NONZERO`, or the CLI could not start.

  The first-flush check now runs only on a call whose status is `OK`. A model that answered with nothing
  (`EMPTY_LOG`) is still a refusal for that one name, not for the gateway.
- **b. A dependency failure no longer ends the day.** Per name, the unit makes up to
  `FORECAST_DEP_RETRY_MAX_ATTEMPTS` = 4 calls, sleeping `FORECAST_DEP_RETRY_BACKOFF_S` = 30/120/300 s between
  them. The worst run is 4 × 420 s + 450 s = 2,130 s, which fits inside `FORECAST_UNIT_TIMEOUT_S` (7,200 s).
  - `REFUSED_DEPENDENCY_DOWN` is not terminal. `resume_gate` is shared by the worker and `sim_run.u_forecast`,
    so the two cannot disagree. It lets a later cycle resume after `FORECAST_DEP_RETRY_MIN_GAP_S` = 3,600 s,
    for at most `FORECAST_DEP_MAX_RUNS_PER_DAY` = 8 runs.
  - The receipt's `dependency` block counts calls, failed calls, retries, runs and runs that ended down, and
    keeps the last 20 failures.
  - **There is no fallback to degrade to.** The evidence packet is already built from disk only (no browsing),
    and the OpenClaw call *is* the forecaster. So the unit refuses under the true name. It never restarts the
    gateway.
- **c. The health probe now counts each writer separately.** `config.FORECAST_WRITERS` registers the writers.
  - `u_forecast` is scheduled every UTC day. It is DEGRADED by name if it wrote 0 rows since 00:00Z of the
    previous UTC day, or if today's day receipt is `REFUSED*` or `DEGRADED`.
  - `thesis_card`, `source`, `review` and `promise` are reported but never graded, so they can no longer turn
    the probe green.
  - Read against the real ledger just now, the probe says:
    `DEGRADED: u_forecast | u_forecast DEGRADED (investigator:evidence_v3): 0 rows since 2026-09-27T00:00Z; newest 2026-09-26T00:30:25+00:00; thesis_card 134 (unscheduled, reported only); source_claims 33 ...`
- **d. The gap is recorded, not backfilled.** See `backend/data/optimus/incidents/u_forecast_dead_2026-09-27.json`.
  09-27 lost about 270–320 rows: 160 names × 2 horizons is the ceiling, and 09-26 wrote 270.
- **e. The unit was not run.** Another builder owns the gateway repair. Once that is done, run it with
  `.venv/Scripts/python.exe -m scripts.night_investigator_forecast --daily` (idempotent per UTC day, spends at
  most $2.00). A healthy first flush looks like this:
  - the console prints `first flush: ledger delta $0.002x, openclaw's own estimate $0.002x`: both positive and
    within a few percent (09-26 averaged $0.00234 per call);
  - the receipt `forecasts/day_<today>.json` shows `first_flush_check.call_status: OK`,
    `dependency.n_failed_calls: 0` and `state: RUNNING`, then `DONE`, with about 2 rows per priced name
    (≤ 320) and about $0.3–0.4 spent;
  - health then shows `u_forecast <n> since <yesterday>`.

  If the console instead prints `dependency failure 1/4 (RC_NONZERO)`, the gateway is still flapping. Stop and
  hand back.

Tests: `backend/tests/test_u_forecast_dependency.py` (11 tests). They use a fake transport that drops the
connection the way 09-27 did, a fake clock, a fake sleep and a fake LLM. Two assertions in
`backend/tests/test_u_forecast.py` were re-labelled to `REFUSED_CAP_READER_DISAGREES`. A true over-cap
refusal is still `REFUSED_CAP` (pinned).

## Results scoreboard

**RESULT IMPROVEMENT: NONE.** This lane fixes a reporting defect, a dead-ledger blind spot and an
issuer-concentration hole. It adds no new signal, spends nothing on the LLM, calls no broker, places no
order and runs no sim. No cap, stop or sizing value changed. Licence: PRODUCT_EXPERIMENT (PC-PAPER, paper
money only).

## Review must-fix list (Lane P's files): what was done

| # | review item | done | how |
|---|---|---|---|
| 1 | VERSION (F5) | **yes** | `sim_run.PROBE_POLICY_VERSIONS`: c3-v0 (from 2026-09-25) is kept unchanged, and **c3-v1 starts 2026-09-28** (share-class collapse). The boundary is checked: no `pc_plan` receipt through 09-27 carries `share_class_dropped`. The c3-v0 entry says on the record that it also covered three changes that were never versioned (the drift band, the bars age gate and the policy_state read). **Journal:** `policy_state.record_version_change` writes one `kind: code_version` row, idempotently, to `pc_book/policy_journal.jsonl`, on the first real (non-sandbox) `u_plan` run under c3-v1. No preference moves. I did not write that row by hand: the first real decision under the new version writes it. **Exit reason:** a held line that the collapse drops is sold with the reason `POLICY CHANGE (share-class collapse), sim_run.u_plan.probe c3-v0->c3-v1 from 2026-09-28: GOOG is a second line of Alphabet Inc. (CIK 1652044); GOOGL kept (...). Not a change of view.` It is listed in `policy_change_exits` on the receipt. The receipt also prints `policy_version`, `policy_version_from_asof` and the version history. |
| 2 | NAME (F2) | **yes** | The mandate status `REFUSED` is renamed **`UNRECONCILED`** and `decision_contract.normalise_mandate_status` maps the old word. `mandate_view` reads receipts that carry the old word (the 09-27 and 09-28 contracts): it prints `UNRECONCILED`, keeps `status_as_written: "REFUSED"`, rewrites the line prefix and says so in `source`. `refusals` is kept as a legacy key beside the new `disagreements`. The line now ends *"gates no order; turns OK when the owner confirms ONE capital base and ONE cap set"*. **GROSS_CAPS_DISAGREE:** I verified that `IC_TOTAL_TILT_BUDGET` is read only by `investment_committee`'s tilt rows, `roi_rank` and the contract's virtual rows, never by `sim_run.u_plan` or `pc_broker`. So I dropped it. The same was true of PROBE 0.20 and EXPLOIT room 0.80 taken alone: they are sleeves of one account that sum to its gross. So the compared gross caps are now the account-level ones only (the broker's `MAX_INVESTED_FRAC` and the sum of the sleeves). The three sleeve caps are printed in `sleeve_caps_seen` and compared to nothing. Today's status is still UNRECONCILED, on two disagreements that are real (capital bases $40,000 / $1,000,000 / $999,054, and per-name caps 2% / 3% / 10% / 12%). |
| 3 | MAP (F4, F6) | **yes** | Issuer identity is now **derived from SEC CIK** (`investment_committee.issuer_map`), using `backend/data/optimus/edgar_8k/company_tickers.json`. That file was already on disk and is tracked; nothing was downloaded. Only common lines are grouped (no NASDAQ fifth-letter preferred, note, warrant, unit or right; a dashed suffix must be one class letter), and only lines one class letter apart (so MSTR and STRC are not grouped, and neither are VIXM and VIXY in one ETF trust). **It reproduces all 22 in-universe groups** the review counted (the hand map had 14) plus the third classes BATRB, FWONB and LILAB. All 26 hand pairs that SEC lists come out identical. `config.ISSUER_SHARE_CLASSES` is cut down to the **override** for what SEC's file lacks: CWEN/CWEN-A and CCL/CUK. If the SEC file is missing, the collapse falls back to the override alone and the receipt says `OVERRIDE ONLY (DEGRADED)` (`issuer_identity` on every plan receipt). The test that passed on an empty map is replaced by four: a synthetic CIK file and universe where every group must collapse to one line and preferreds, notes and ETF-trust siblings must survive; override joining; the missing-file case; and the 22 review groups against the tracked SEC file. |
| 4 | the lane note leads with F1 | **yes** | §0 above |

## The four rulings (the first build, unchanged)

| # | reviewer's claim | ruling | one-line reason |
|---|---|---|---|
| P1 | "Every contract says mandate REFUSED, `u_plan` never reads it, PROBE orders go out anyway" | **BY DESIGN, reporting defect (b)** | The mandate encodes no limit, so there is nothing to bypass. It reconciles bases and caps (review 09-26 R4, "changes no limit"), and PROBE acting is the 09-25 C3 design. The defect: the contract printed REFUSED while the plan receipt printed no mandate at all. "Every contract" is also wrong: only 09-27 and 09-28 carry the block. |
| P2 | "The shortlist holds both GOOG and GOOGL" | **TRUE** | Funnel ranks 8 and 9 have the identical score 0.8564. Both were bought on 09-25 at 2% each, so Alphabet was 4% (2 × `PROBE_MAX_WEIGHT`). 14 other share-class groups exist in the 5,339-name universe; none is in today's candidate set. |
| P3 | "E[r] has 0 graded dates on all six inputs, so the policy_state read changes nothing" | **TRUE, and stronger** | `refit_2026-09-28.json`: 0 dates on 6 components × {h5, h21, h63}. And at **h5**, the only horizon `probe_order` reads, every component is ASLEEP on every name. A graded h21 component still could not reorder PROBE. |
| P4 | "Worst case on the largest book the code allows: ~−$65k to −$82k on a 3σ day; no stop, so the ceiling is the whole $999k" | **TRUE (arithmetic reproduces)** | −$64,739 / −$82,181 / −$999,054 from the constants. Today that book is unreachable: EXPLOIT is refused (MEASURED_NEGATIVE), and the reachable book is 21.84% invested, −$17,948 at 3σ. No path exceeds 1.00× on the plan's targets, but the gross check reads targets, not broker positions (see §3). |

## 1. The trace: input file → `pc_broker.submit()`

`scripts/sim_run.py::u_plan` (line numbers are from the working tree before this lane's edits):

1. `ranking.json` → `bars_gate` (the age gate refuses both states on stale bars) → EXPLOIT verdict `MEASURED_NEGATIVE` when `top20_net_rel_21d <= 0` → `may_trade=False`. EXPLOIT also needs `_blend_grade` (≥ 21 graded sessions).
2. `investment_committee.shortlist(asof)` reads `backend/data/funnel_night10.json` (generated 2026-09-24T02:48Z, 25 candidates, `ranked_by: profitability_small`). It refuses on stale, undateable or future files.
3. `_contract_view(decisions/<asof>.json)`: rows REFUSED as negative-EV are removed from PROBE (ALLE on 09-26 and 09-27, `contract_refused_excluded: 2`). **Before this lane, `_contract_view` read only `rows`; the `mandate` block was never loaded.**
4. E[r] view → `policy_state.plan_view` → `probe_order` (h5) → `probe_weights(max_weight=config.PROBE_MAX_WEIGHT, gross_cap=config.PROBE_GROSS_CAP)`.
5. `_probe_grade` → `UNMEASURED_TRADE_SMALL`, `may_trade=True` until 21 graded sessions exist; `probe_acting = mode == "paper_profit" and ...`.
6. `PB.plan_orders(targets, equity, held, prices)` clips each name to `MAX_NAME_FRAC` 0.12, clips Σ target weight to `MAX_INVESTED_FRAC` 1.00, caps each order at `MAX_ADV_PARTICIPATION` 0.02, and applies the drift band and the minimum order size.
7. `_may_send`: PROBE and PROBE_EXIT go only while `probe_acting`; EXPLOIT and EXIT only while `exploit_acting`. Then `PB.clock().is_open`, then an open-order skip, then **`PB.submit(p)`** (`pc_broker.py:501`, a market day order).

### The P1 design record

- **PROBE acting while EXPLOIT is refused.** `docs/HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md`, "Chunk C3": *"`acting` for PROBE is **not** gated on `top20_net_rel_21d` ... gated on the shortlist's own forward grade once ≥ 21 days exist, until then it is `UNMEASURED_TRADE_SMALL`."* It descends from 09-21's contract-level PROBE (23a, a $0 virtual row, `PROBE_REFUSAL_CLASSES`) and Murat's 09-25 instruction *"make sure the engine makes decisions that we can then later judge"* (`u_plan` docstring).
- **The mandate is not a gate.** `decision_contract.account_mandate` docstring: *"It REFUSES ... instead of picking one silently ... it stays red until Murat confirms ONE mandate. No limit is changed here."* `RUNBOOK_2026-09-26_SYSTEMS_FIXES.md` row 4 lists it as owner decision 1.
- **Receipts (last five days).**

| day | contract `mandate` | plan `probe_acting` | plan mandate field | submitted |
|---|---|---|---|---|
| 09-24 | *(no block)* | observe mode | none | 0 |
| 09-25 | *(no block)* | true | none | 22 (10 entries + 12 one-share rebalances) |
| 09-26 | *(no block)* | true | none | 1 (JAZZ) |
| 09-27 | REFUSED (3 disagreements) | true | none | 0 (venue closed; 1 queued: the ALLE exit) |
| 09-28 | REFUSED (3 disagreements) | no plan yet | n/a | n/a |

  Sources: `decisions/<d>.json`, `pc_book/<d>/decisions.jsonl`, `decisions/pc_plan/<d>.json`.
- **Is any limit bypassed?** No. Every PROBE order was ≤ 2% of equity and Σ ≤ 20% (0.2 `probe_gross` on each receipt). The mandate's three refusals are disagreements *between* limits: capital $40,000 / $1,000,000 / $999,054; per-name 2% / 3% / 10% / 12%; gross "reachable 1.00× vs tightest 0.10". The 0.10 is `IC_TOTAL_TILT_BUDGET`, the committee page's tilt garnish, which is not a `u_plan` limit. The one real breach of a cap's *intent* was issuer-level: Alphabet at 4%. That is P2.
- **Side finding.** The 09-25 one-share churn (GOOGL sold 13:37, bought back 13:47, and more) was already fixed the same day by `pc_broker.REBALANCE_DRIFT_FRAC` (0.10; the comment cites GOOGL).

### P3 detail: what goes live first, and when

`probe_order` uses `reputation_er(cell_h5)`. A component contributes only when (i) its `x` is non-null at h5 **and** (ii) the E[r] layer's own `weights_reputation[c] > 0`, which needs `n_dates >= ER_MIN_GRADED = 30` graded DATE blocks and held-out IC > 0 (floor 0). `investigator_dir` also needs its family to have weight > 0 in `policy_state.reputation_weights`; it does (investigator arms sum to 1.0).

- **The h5 asleep reasons** (`er_2026-09-27.json`, every name): ranker "calibrated at 21 sessions only"; revision_flow "no measured rule table at h=5"; investigator_dir "no graded calibration at h=5" (NVDA, AAPL, GOOGL, AMZN, which carry evidence_v3 rows) or "no investigator beats_benchmark row at h=5" (INCY, JAZZ, ...); thesis_card "no row at h=5"; catalyst "no dated PDUFA inside 5 sessions"; source_reliability follows revision_flow.
- **First to go live: `investigator_dir` at h5.** `predictions.jsonl` holds 194 open `investigator:evidence_v3 / beats_benchmark / h5` rows on 155 tickers, made 2026-09-25 and 09-26 (**2 date blocks**). The earliest `resolves_after` is 2026-10-05. After that grade, `x` wakes up (calibration exists), but `rep_weight` stays 0 until 30 blocks.
  - If the forecast unit writes evidence_v3 h5 rows on **every** XNYS session from 09-28, the 30th made day is **2026-11-04** (`DC.sessions_expiry(09-25, 28)`), graded **2026-11-11**. That is the earliest date the policy_state read can change a PROBE order, and only if held-out IC > 0.
  - Today the forecast unit reports `REFUSED_CAP, n_rows_written 0`, so the date slips one session for every session it stays refused.
  - The evidence_v2 h1 rows (40 graded) never count: h=1 is not in `ER_HORIZON_ALIASES`.
- **Decision-ledger path** (ranker, revision_flow, source_reliability). Only h21 and h63 rows carry `er_by_component`: 38 DECIDED rows on 3 asofs (09-25, 09-26, 09-27; the last is a Sunday), 0 SCORED. The first h21 score is 2026-10-26. Thirty blocks at h21, deciding every session: decision day 2026-11-05, graded **2026-12-07**. This path moves EXPLOIT's E[r], never the h5 PROBE order.

Nothing was built to force either date.

## 2. Worst case in dollars (protocol item 4)

Equity **$999,054.41** (PC-PAPER `PA37CSAUFCQR`, `pc_book/2026-09-27/nav.jsonl`). Two sigma bases: `PROBE_REF_DAILY_SIGMA` = 2.16%/day, and the funnel's highest `vol_annual` (AVPT, 43.5%/yr) = 2.742%/day. k = `PROBE_WORST_CASE_SIGMA` = 3. **No stop is declared anywhere**, so the 3σ column is a session move, not a stop, and the ceiling is the full gross.

| book (by construction) | n × notional% × move | Σ\|notional\|/equity | 3σ day @2.16% | 3σ day @2.742% | no-stop ceiling |
|---|---|---|---|---|---|
| PROBE largest admissible | 10 × 2% × 6.48% / 8.23% | 0.20 | −$12,948 | −$16,436 | −$199,811 |
| EXPLOIT, PROBE full (room = 1 − 0.20) | 18 × ≤10% (Σ ≤ 0.80) | 0.80 | −$51,791 | −$65,745 | −$799,244 |
| EXPLOIT alone (shortlist empty: room = 1 − probe_gross = 1.00) | 18 × ≤10% (Σ ≤ 1.00) | 1.00 | −$64,739 | −$82,181 | −$999,054 |
| PROBE + EXPLOIT | 10 × 2% + 18 × ≤10% | 1.00 | −$64,739 | −$82,181 | −$999,054 |
| reachable today (EXPLOIT refused) | 10 PROBE + ALLE exit pending | 0.2184 | −$14,139 | −$17,948 | −$218,197 |

Single name to zero:

| position | loss |
|---|---|
| EXPLOIT name at 10% | −$99,905 |
| broker `MAX_NAME_FRAC` 12% | −$119,887 |
| PROBE name at 2% | −$19,981 |
| Alphabet before P2 (4%) | **−$39,962** |
| Alphabet after P2 (2%) | −$19,981 |

- **By construction, is the PROBE book separate?** No. `room = 1 − probe_gross` uses the *planned* PROBE gross, not `PROBE_GROSS_CAP`. With an empty or refused shortlist, EXPLOIT alone can reach 1.00×.
- **Can any path exceed the gross cap?** Not on the plan's own targets. `plan_orders` clips Σ target weight to `MAX_INVESTED_FRAC` 1.00 (asserted ≤ 1.0 at import), EXPLOIT sizes inside `room`, and `probe_weights` refuses a breach.
- **The check reads a different ledger than the book.** Like 2026-09-21, the gross check reads the **plan's targets**, never **broker positions**. A holding that is not a target is an EXIT, and it is sold only while `exploit_acting`. While EXPLOIT is refused it sits outside the arithmetic (today: ALLE is a PROBE_EXIT and *is* sendable).
  - Under the current code such holdings come only from earlier books that were themselves ≤ 1.00×. So the realised gross stays ≤ ~1.00× plus price drift, and a transient cash dip is possible when buys fill before sells (sells are sent first).
  - The account shows **$3,734,382 buying power** (a margin account), so the venue would not refuse leverage. The only guard is the target arithmetic.
  - A broker-truth check is **owed**: Σ(post-order market value) ≤ `MAX_INVESTED_FRAC` × equity, computed from positions and refusing on disagreement. It was not built, because P4 is report-only.

## 3. What changed and why

Worst case **before → after** on the order path:

| measure | before | after |
|---|---|---|
| Largest admissible PROBE, 3σ | −$16,436 | −$16,436 (unchanged: n, weight, gross cap and σ-max name AVPT all unchanged) |
| Planned PROBE book, 3σ | −$16,436 | −$16,436 (GOOG σ 1.97%/day out, TSM 2.54%/day in, max still AVPT) |
| Largest single-issuer exposure | 4% (Alphabet), −$39,962 at zero | 2%, −$19,981 |
| Σ\|notional\|/equity | 0.20 | 0.20 |

**Nothing rises.**

1. **P1 (b): one mandate status on both surfaces** (`backend/services/decision_contract.py`, `scripts/sim_run.py`)
   - `decision_contract.mandate_view(contract_mandate, contract_status, contract_path)` returns the contract's `mandate` block **verbatim** (status, line, refusals). It never recomputes: the contract's capital comes from that day's agency options, and a second computation on another capital is how two statuses appear.
   - No contract, an unreadable one, or one without the block → `CANNOT DETERMINE`, by name.
   - `account_mandate` output (so every future contract) and `mandate_view` both carry:
     - `gates_orders: False`
     - `gates_orders_note`: "RECONCILIATION ONLY ... PROBE acting while EXPLOIT is refused is the 2026-09-25 C3 design, not a bypass"
     - `what_makes_it_green`: the owner confirms ONE capital base and ONE per-name/gross cap set.
   - `_contract_view` now carries `mandate_block`. `u_plan`'s receipt gets `mandate` and `mandate_line`; its return value gets `mandate_status`, `mandate_line` and `mandate_gates_orders`.
   - **No order behaviour changed.**
2. **P2: one issuer, one line** (`backend/config.py`, `backend/services/investment_committee.py`, `scripts/sim_run.py`)
   - `config.ISSUER_SHARE_CLASSES` is appended only: 28 issuers, 57 lines. 14 groups were found in the 2026-09-24 universe; the rest are dotted lines the universe filter drops today. **Superseded after review:** identity is now derived from SEC CIK, and the hand map holds only the 2 overrides SEC lacks (see must-fix #3).
   - `investment_committee.collapse_share_classes(rows)` runs inside `shortlist()`. It keeps the line with the larger funnel `median_dollar_vol` (the 60-session median of close × volume from the funnel's bars); when one is missing it keeps the best-scored line and says so.
   - Each dropped line is written as `share_class_dropped` {ticker, issuer, kept, basis} on the kept row, and on the `u_plan` receipt and return value.
   - On today's file: **GOOG is dropped** (GOOGL $8,805m vs GOOG $5,832m), and **TSM becomes PROBE name 10**.
3. **Tests** (`backend/tests/test_lane_p_money_path.py`, 13 tests)
   - Synthetic funnels, contracts and ledgers in `tmp_path`, dates from today, no network.
   - The fake broker records every call; its `forbid_submit` mode fails the test if `submit` is reached (observe mode under a REFUSED mandate).
   - No subprocess is spawned; no new exception class.

## 4. Consequence the owner should know before the next `paper_profit` session

At the next open, PROBE will **sell 58 GOOG (~$19.8k, PROBE_EXIT because it is a prior PROBE holding) and buy ~$20k of TSM**. ALLE's queued exit also goes then. This is the direct result of the P2 fix; no order was placed by this lane.

## 5. OWED LATER: a specification, not built (it changes sizing, so the owner confirms a capital base first)

No cap, stop or sizing value was changed by this lane. The items below change what can be bought, so they
wait for owner decision 1 (one capital base, one cap set). Worst cases use equity **$999,054.41**
(`pc_book/2026-09-27/nav.jsonl`, long MV $218,196.64, buying power $3,734,381.67 on margin), k =
`PROBE_WORST_CASE_SIGMA` 3, σ = `PROBE_REF_DAILY_SIGMA` 2.16%/day or AVPT's 2.742%/day, and **no stop
declared anywhere**. My recomputation from config matches the reviewer's to within $2 on every row. That $2
is rounding: the reachable row uses 0.2184 × equity, where the review used the exact long MV.

| book | Σ\|notional\|/equity | 3σ @2.16% | 3σ @2.742% | no-stop ceiling |
|---|---|---|---|---|
| PROBE largest admissible, 10 × 2% | 0.20 | −$12,948 | −$16,436 | −$199,811 |
| EXPLOIT alone (shortlist empty, room 1.00) | 1.00 | −$64,739 | −$82,182 | −$999,054 |
| **holdings path:** EXPLOIT acted at 1.00×, next day MEASURED_NEGATIVE, its names are unsendable EXITs, PROBE buys 0.20 | **1.20** | **−$77,686** | **−$98,619** | **−$1,198,865** (more than equity; margin) |
| R2 same-asof path: 10 PROBE bought, all refused on re-plan, 10 new bought | 0.40 | −$25,895 | −$32,873 | −$399,622 |
| reachable today (EXPLOIT refused) | 0.2184 | −$14,139 | −$17,949 | −$218,193 |
| EXPLOIT pool with two lines of one issuer at `ER_EXPLOIT_MAX_WEIGHT` 10% each | 0.20 in one issuer | −$12,948 | −$16,436 | −$199,811 on one issuer |
| cross-book: GOOGL PROBE 2% + GOOG EXPLOIT 10% | 0.12 in one issuer | −$7,769 | −$9,862 | −$119,887 |

**S1: broker-truth gross check (F3; the 09-26 review R2, deferred twice).**
- **Where:** `pc_broker.plan_orders`.
- **Inputs:** `held × price` from the broker's positions, not the plan's targets.
- **Rule:** post-order Σ market value ≤ `MAX_INVESTED_FRAC × equity`. On a breach, buys are **refused**
  (largest first) and sells still go.
- **Receipt:** `invested_frac_before` / `invested_frac_after` on the plan receipt, where the `u_plan` health
  probe already looks for them.
- **Same change:** fix `_prior_probe_holdings`' `p.stem >= asof`, so a name bought under the *current* asof
  exits as `PROBE_EXIT`.
- **Effect:** the 1.20× and 0.40× rows become unreachable, and the ceiling returns to −$999,054.
- **Owner questions:** (i) is the account's gross cap 1.00× of broker equity? (ii) is a refused buy
  acceptable over selling an EXPLOIT name while EXPLOIT is refused?

**S2: issuer caps across books (F4).**
- Run `collapse_share_classes` over the EXPLOIT pool (`ranking.json` top) and over the PROBE ∪ EXPLOIT union
  (today the `exploit_syms` exclusion matches exact tickers only). Apply `MAX_NAME_FRAC` per **issuer**.
- When both lines qualify, prefer the line already held, so a refresh of the dollar-volume ranking cannot
  churn Z/ZG.
- **Effect:** the 0.20-in-one-issuer and 0.12-in-one-issuer rows fall to 0.10 and 0.10.
- **Also needed:** an ADR/local map (TSM / 2330.TW), which CIK cannot see.

**S3: contract rows.** Collapse `decision_contract.compose_book` and the virtual PROBE/tilt rows by issuer, so
that one issuer is graded once. Grading changes; no order does.

**S4: frozen books.** Report the double Alphabet exposure on 8 books and the TSM + 2330.TW exposure on 6 books
on their grade. **Never repair them.**

**S5: stop.** The owner declares a stop, or accepts on the record that the ceiling is the gross.

Other items owed from this round:
- `system_health` has no `mandate` row. It would read the plan's `mandate_status` beside the contract's.
  That probe is not mine this round.
- `test_guard_missing_input_contract::test_every_guard_is_enrolled` is red on `muratclaw_instance`, another
  builder's new module. It is not enrolled by me. This lane added no exception class (it reuses
  `policy_state.PolicyRefused`).
