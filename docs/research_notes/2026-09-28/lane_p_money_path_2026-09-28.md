# Lane P: the paper money path, verified then built (2026-09-28)

**RESULT IMPROVEMENT: NONE.** This lane fixes a reporting defect and closes one issuer-concentration hole. No new signal, no LLM spend, no broker call, no order, no sim run. No cap, stop or sizing value changed. Licence: PRODUCT_EXPERIMENT (PC-PAPER, paper money only).

## The four rulings

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
   - `config.ISSUER_SHARE_CLASSES` is appended only: 28 issuers, 57 lines. 14 groups were found in the 2026-09-24 universe; the rest are dotted lines the universe filter drops today.
   - `investment_committee.collapse_share_classes(rows)` runs inside `shortlist()`. It keeps the line with the larger funnel `median_dollar_vol` (the 60-session median of close × volume from the funnel's bars); when one is missing it keeps the best-scored line and says so.
   - Each dropped line is written as `share_class_dropped` {ticker, issuer, kept, basis} on the kept row, and on the `u_plan` receipt and return value.
   - On today's file: **GOOG is dropped** (GOOGL $8,805m vs GOOG $5,832m), and **TSM becomes PROBE name 10**.
3. **Tests** (`backend/tests/test_lane_p_money_path.py`, 13 tests)
   - Synthetic funnels, contracts and ledgers in `tmp_path`, dates from today, no network.
   - The fake broker records every call; its `forbid_submit` mode fails the test if `submit` is reached (observe mode under a REFUSED mandate).
   - No subprocess is spawned; no new exception class.

## 4. Consequence the owner should know before the next `paper_profit` session

At the next open, PROBE will **sell 58 GOOG (~$19.8k, PROBE_EXIT because it is a prior PROBE holding) and buy ~$20k of TSM**. ALLE's queued exit also goes then. This is the direct result of the P2 fix; no order was placed by this lane.

## 5. Owed (not done here)

- **Owner decision:** confirm ONE capital base and ONE cap set for PC-PAPER. This is the only thing that turns the mandate OK.
- **Owner decision:** declare a stop, or accept that the ceiling is the gross.
- **Broker-truth gross check** in `pc_broker.plan_orders` (§2).
- `decision_contract` virtual PROBE rows still come from the uncollapsed funnel, so GOOG and GOOGL are graded as two names. The EXPLOIT ranking pool is not collapsed either; it had no pair on 09-25.
- `system_health` probe (not my file): a `mandate` row that reads the plan's `mandate_status` beside the contract's.
- `test_guard_missing_input_contract::test_every_guard_is_enrolled` is red on `alerts` and `calendar_offsets`, other builders' new modules. Not this lane's.
