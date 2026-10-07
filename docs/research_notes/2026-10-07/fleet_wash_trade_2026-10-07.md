# C27: making top-ups lawful under the broker's wash-trade rule (2026-10-07)

**RESULT IMPROVEMENT: NONE (execution correctness).** C27 changes no alpha source, contract, cap or
stop distance. It changes the order in which the frozen contracts' own orders reach the broker, so
that the orders the contracts already decided are no longer refused.

**What the 49 rejections cost.** Since 2026-10-01 the broker rejected 49 of 75 LIVE buys, and all
49 were `403 potential wash trade`. Measured on the first rejection per (account, symbol), they cost
the books **+$146.36 net** of missed gain on $18,740 of intended notional (+0.78%), up to the
2026-10-06 close. The amount is small. The larger effect is the drift: the executed books stopped
matching their frozen books and twins.

**Worst case after the fix.** It is no higher than what the old path would have added for the same
top-ups. The only exception is the buy limit's slippage over the reference price, which was at most
$0.24 on one name on 10-06. On the real 10-06 plan:

- hack4's sequences **lower** its worst case by $23.
- hack2 sat $83 **above** its contract line before any order, so the line rule refuses its five
  top-ups by name (§5).

Licence: `PRODUCT_EXPERIMENT`, unchanged. Policy: `gate_policy_version = "c27-wash-trade-sequence"`,
which keeps the c26-p2 frozen terms and adds the sequence.

**C27 is not a gate and not shadowed.** The sequence binds from the first pass that runs this code.
`FLEET_NEW_GATES_MODE` governs only `cooldown` and `sector_concentration`, and the sequence ignores it.

## 1. The broker's rule

Fetched 2026-10-07 from `https://docs.alpaca.markets/us/docs/user-protection` (raw page, quoted
verbatim):

> "If we detect a possible wash trade, we reject the order and send back an error message with the
> HTTP status code 403 (Forbidden)."
>
> "A wash trade occurs when a customer's two orders could potentially interact with each other."
>
> | Existing Order | New Order | Reject Condition |
> |---|---|---|
> | stop sell | limit buy | always rejected |
> | limit buy | stop sell | always rejected |
>
> "If a customer wants to set up a 'take profit' and a 'stop loss' situation, we recommend using a
> bracket or OCO (One Cancels the Other) order. These complex orders and trailing stop orders are
> exceptions to our wash trade protection."
>
> "Our wash trade protection also applies to your paper trading account."

The two table rows force the design:

- A top-up's limit buy cannot be placed while our GTC sell stop rests.
- The stop for the combined quantity cannot be placed while any part of that buy is still open.

The 403 body names the conflicting order (`existing_order_id`). In all 49 cases it was the resting
stop in that pass's stop table.

## 2. The audit (measure first)

**Receipt:** `backend/data/optimus/paper_accounts/fleet_manager/wash_trade_audit_20261007T051104Z-48104e.json`.

- **Script:** `python -m scripts.fleet_wash_trade_audit`. It is read-only and uses only the run
  receipts and the bars panel.
- **Panel:** the newest close is 2026-10-06; the 10-07 session had not traded yet.

| pass | LIVE buys sent | rejected (403 wash trade) | 422 | other |
|---|---|---|---|---|
| 2026-10-01 open | 17 | 10 | 0 | 0 |
| 2026-10-02 open | 20 | 11 | 0 | 0 |
| 2026-10-05 open | 19 | 13 | 0 | 0 |
| 2026-10-06 open | 19 | 15 | 0 | 0 |
| **total** | **75** | **49** | 0 | 0 |

All 49 rejections were top-ups of a name that held our resting GTC sell stop
(`every_rejection_is_a_topup_with_a_resting_stop: true`). Every buy of a name not yet held went
through.

**How the P&L was measured:**

- **Entry:** filled at the intended limit on the session of the attempt. That limit is ask × 1.001,
  so it is marketable.
- **Stop:** one stop at max(the resting stop, the contract's stop level).
- **Exit:** from the next session, at the open if the price gaps below the stop, else at the stop if
  the low reaches it, else marked at the 2026-10-06 close.
- **Costs:** 10 bps per side on both sides (`costs_block`).
- **Limit of the method:** the session of the attempt is not path-checked intraday.

Each rejected top-up was re-planned at the next open with the same shortfall. Summing all 49 would
count the same missing shares up to four times (**−$40.97**). The honest figure is the first
rejection per name:

| first rejected | account | symbol | qty | limit | resting stop (qty) | combined stop | outcome | net | $ net |
|---|---|---|---|---|---|---|---|---|---|
| 10-01 | hack4 | JAZZ | 8 | 232.15 | 218.47 (21) | 220.43 | mark 231.39 | −0.53% | −9.79 |
| 10-01 | hack4 | ALLE | 12 | 152.69 | 146.26 (32) | 146.26 | mark 155.20 | +1.44% | +26.46 |
| 10-01 | hack4 | INCY | 15 | 120.22 | 115.82 (39) | 115.82 | **stopped 10-02** | −3.86% | −69.61 |
| 10-01 | hack4 | SNDR | 56 | 31.71 | 29.91 (159) | 29.91 | mark 31.60 | −0.55% | −9.71 |
| 10-01 | hack4 | GOOG | 5 | 338.63 | 323.39 (13) | 323.39 | mark 344.59 | +1.56% | +26.41 |
| 10-01 | hack4 | AAPL | 5 | 331.21 | 313.24 (15) | 313.28 | mark 333.63 | +0.53% | +8.79 |
| 10-01 | hack4 | AMZN | 6 | 247.27 | 231.70 (15) | 231.70 | mark 256.29 | +3.45% | +51.15 |
| 10-01 | hack4 | META | 2 | 727.61 | 658.77 (4) | 658.77 | mark 738.88 | +1.35% | +19.63 |
| 10-01 | hack4 | NVDA | 6 | 230.77 | 213.45 (17) | 213.59 | mark 239.24 | +3.47% | +48.05 |
| 10-01 | hack4 | AVPT | 82 | 14.02 | 12.33 (288) | 12.90 | mark 14.59 | +3.87% | +44.44 |
| 10-02 | hack2 | AMGN | 1 | 404.37 | 395.68 (11) | 395.68 | mark 402.60 | −0.64% | −2.58 |
| 10-02 | hack2 | MDB | 1 | 357.56 | 315.59 (13) | 315.59 | mark 360.71 | +0.68% | +2.43 |
| 10-05 | hack2 | AMD | 1 | 632.56 | 562.50 (7) | 562.50 | mark 649.42 | +2.47% | +15.60 |
| 10-05 | hack2 | TGT | 2 | 151.04 | 149.69 (31) | 149.69 | mark 154.33 | +1.98% | +5.98 |
| 10-06 | hack1 | VRT | 1 | 251.80 | 219.03 (27) | 220.62 | mark 253.14 | +0.33% | +0.84 |
| 10-06 | hack2 | NET | 1 | 361.56 | 322.56 (13) | 322.56 | mark 355.01 | −2.01% | −7.27 |
| 10-06 | hack2 | SNOW | 1 | 339.73 | 313.30 (14) | 313.30 | mark 335.95 | −1.31% | −4.46 |
| **17 names** | | | | | | | 1 stopped | **+0.78%** | **+$146.36** |

By account (first rejection per name):

| account | names | notional | net P&L |
|---|---|---|---|
| hack4 | 10 | $16,091 | +$135.82 |
| hack2 | 6 | $2,398 | +$9.70 |
| hack1 | 1 | $252 | +$0.84 |

**Reading this:**

- The rejections cost the books $146 of gain over four to six sessions.
- On 17 names and less than a week, that number is noise. Neither sign is evidence about the
  strategy.
- The cost that matters is structural. hack4's executed book has been about $16k short of its
  frozen v2 book since 10-01, so its grade against its twin has been measuring a different book.
- INCY's held shares were stopped out on 10-02, and the top-up would have gone with them. A later
  buy of INCY was a re-entry, not a top-up.

**Names held without a full resting stop now:**

- Count: **0**, in the newest open and preclose receipts, net of stops the same pass placed.
- hack6's PPLI read as uncovered (19 shares) in the 10-06 preclose stop table, but that same pass
  placed its stop (`stop_new` LIVE, submitted).
- No cancel/replace race has left a name unprotected in the receipts read. The EOD audit, which
  starts tonight, will confirm this from the broker.

## 3. The sequence and its rollback

The sequence is in `backend/services/fleet_manager.py` under `C27: the wash-trade sequence`, and is
called from `scripts/fleet_manager_run.py`.

### Planning

Planning happens in `plan_topup_sequence`, after the buy has passed every gate.

- **Conflicts.** `wash_conflicts` applies the broker's table:
  - a resting sell `stop` always conflicts;
  - a sell `stop_limit` conflicts if buy limit ≥ its limit;
  - a resting sell `limit` or `market` order is an exit in flight. The top-up is
    `REFUSED_WASH_TRADE_RULE` by name, because the sequence never cancels an exit;
  - a `trailing_stop` and a complex-order leg are exempt, in the broker's own words.
- **The combined stop:**
  - quantity = held + top-up, re-read from the broker after the buy;
  - price = max(every replaced stop, the contract's stop level at the reference price);
  - `inputs.replaces_stop` carries the old price, so the `stop_never_loosened` gate re-checks it;
  - it is gated as the protective order it will become (it counts toward the per-run order cap).
- **If the combined stop is refused at the gates,** the buy is `REFUSED_WASH_TRADE_RULE` and the
  resting stop is left alone.
- **The worst-case line rule** is `topup_line_walk`, §5.
- **Decision rows.** Every member (the cancels, the buy, the combined stop) gets a decision row with
  its gate trace and a shared `wash_seq` id. All decision rows of the account are on disk before its
  first order.

### Execution

Execution is `execute_topup_sequence`. Every step is a timestamped event (UTC, ms).

1. **Re-read the open orders.** A stop renewed earlier in the same run carries an id the plan never
   saw, and it is released too.
   - The combined stop is raised to the highest stop actually resting.
   - A newly found exit in flight refuses the sequence before any step.
2. **Cancel each resting stop** and wait for the venue to confirm it `canceled`. The wait is
   `FLEET_WASH_SEQ_CANCEL_WAIT_S` = 6 s.
   - **Rollback:** if a cancel does not confirm, re-place every stop already cancelled and send no
     buy. The result is `REFUSED_WASH_TRADE_RULE`, or `ABORTED_STOP_FILLED` if the stop had filled.
3. **Send the buy** (`submit_once`, idempotent client id).
   - **Rollback:** if it is rejected, re-place the original stop(s) immediately, at the same price and
     the same quantity, capped at the shares held. The result is `BUY_REJECTED_ROLLED_BACK`.
4. **Wait for the buy to reach a terminal status.** The wait is `FLEET_WASH_SEQ_BUY_WAIT_S` = 8 s.
   If it is still open, cancel the remainder first ("limit buy | stop sell | always rejected").
5. **Read the position from the broker** and place one stop for exactly that quantity.
   - **Rollback:** if this stop is rejected, place a plain `stop` (market on trigger) at the same
     price under a new id (`…-p`). The sequence is marked **REFUSED** on the receipt.
   - If that is rejected too, re-place the original stop(s). The sequence is marked **UNPROTECTED**
     with the uncovered quantity.
6. **Measure the stop-less window:** from the first confirmed cancel to the first accepted stop
   (combined, protective or restored), as `stopless_window_s`.

**Circuit breaker.** If a sequence ends REFUSED or UNPROTECTED, or its window exceeds
`FLEET_WASH_SEQ_MAX_WINDOW_S` = 45 s, every later top-up on that account in the same run becomes
`REFUSED_WASH_TRADE_RULE`. The venue is not answering fast enough to open another window safely.
**Nothing is ever skipped silently.**

**Receipt and ledger.** Each sequence writes a `wash_sequence` row to `decisions.jsonl`. The account
block carries:

- `wash_sequences.summary`: `n`, `by_status`, `max_stopless_window_s`, `stopless_events`,
  `unprotected_qty`;
- `c27_worst_case`;
- `rejections`.

**The cost of the window.** It is bounded by the waits: about 6 + 8 + 6 s plus four round trips,
typically a few seconds when the limit is marketable. During the window a held name has no stop. A
gap through the old stop in those seconds is the residual risk, and the receipt measures it.

**What is not proven.**

- **The real paper venue's cancel-confirm latency.** The tests use a fake broker that enforces the
  table. The first live pass is the first measurement of `stopless_window_s`.
- **A bracket/OTO order instead of the sequence.** The broker exempts complex orders. An OTO buy with
  a stop leg might avoid the window entirely, but it is untested here and would change the order
  shape the contracts declared ("GTC sell stop for the full long quantity").

## 4. What the 10-06 replay shows

Test: `backend/tests/test_fleet_wash_trade_c27.py::test_the_10_06_open_plans_on_the_rule_broker_old_path_vs_c27`.
Fixtures: `fixtures/c26/replay_2026-10-06.json` (the plans) and `fixtures/c27/resting_2026-10-06_open.json`
(the resting stops and the broker's real answers).

- **Old path.** The fake broker that enforces the table rejects exactly the 15 buys the real broker
  rejected on 10-06, and accepts the other 4 (VKTX, VALE, PPLI, UPS).
- **C27 path.** All 19 buys reach the broker. The 15 top-ups go through cancel → buy → one combined
  stop, and each ends with one resting stop for held + top-up, never below the old stop. That
  includes hack2's MDB, NET and SNOW in shadow mode.
- **Enforce mode.** The sector gate still refuses MDB/NET/SNOW before any sequence, and a refused buy
  opens no stop-less window.

**Which 10-06 orders now reach the broker** (with the worst-case line rule, §5):

- **hack4 (9 top-ups):** ALLE, JAZZ, SNDR, GOOG, AAPL, AMZN, NVDA, AVPT, META. All go through the
  sequence.
- **hack1:** VRT goes through the sequence; VKTX goes as before.
- **hack6:** VALE, PPLI, UPS go as before (new names).
- **hack2:** AMGN, MDB, NET, SNOW, TGT are **refused by name, `REFUSED_WORST_CASE_LINE`**. hack2
  executes the same as on 10-06 (nothing), but now the reason is ours and named, not the broker's 403.

## 5. Worst case, before and after (CLAUDE.md protocol 4)

All figures are from the real 10-06 open receipt, in dollars at the stops (a gap can fill worse).

- **"now":** the resting stops before the pass.
- **"old path adds":** what the pre-C27 receipt printed for these top-ups (the added shares at the
  contract stop fraction).
- **"after C27":** now + the change from moving held + added shares onto one combined stop.
- **Line:** the active v2 contract's `worst_case_formula_v2`.

| account | equity | now | old path adds | after C27 (top-ups admitted) | contract line | top-ups |
|---|---|---|---|---|---|---|
| hack1 | $92,674 | $10,374.91 | +$30.22 | **$10,363.16** (−$11.75) | $10,676.07 | VRT: OK |
| hack2 | $102,866 | $12,427.23 | +$154.98 | $12,427.23 (all refused; would have been $12,525.61) | **$12,343.87** | 5 × REFUSED_WORST_CASE_LINE |
| hack4 | $80,564 | $5,604.36 | +$824.23 | **$5,581.51** (−$22.85) | $9,476.44 | 9 × OK |
| hack5 | $96,368 | $10,938.33 | 0 | $10,938.33 | $9,154.99 | none (SPY control) |
| hack6 | $81,219 | $6,227.65 | 0 | $6,227.65 | $812.19 (news sleeve) | none (new names only) |

**The rule** (`topup_line_walk`, in plan order): a sequence may not take an account's worst case
above its contract line, nor raise it further when the account already sits above. A sequence that
lowers the worst case always passes.

**Why the worst case can fall.** The combined stop re-bases the held shares at the contract level
from today's price. Examples on 10-06: NVDA 213.45 → 224.81 and AVPT 12.33 → 13.92. This tightening
pays for the added shares. It is the same `max(old, contract level)` rule the stop renewal already
applies.

**Owner decision (open).** hack2's resting stops sit more than 12% below prices that have risen
since the stops were placed. The account was $83 above its line before the pass, so its frozen book
can no longer be topped up under this rule. Two options:

- accept it (risk can only be reduced: the default);
- re-base hack2's stops to the contract level first. That tightens stops and lowers the worst case
  below the line. It would be its own attended change.

hack5 and hack6 are above their lines too, but they have no top-ups.

## 6. Counting rejections: receipt, audit, health

- **Run receipt.** Every account and the fleet carry `rejections`: `{n_live_buys_sent, n_rejected,
  by_reason {wash_trade_403, http_422, other}, rejected_frac, refused_before_broker, degraded, line}`.
  The rejected status of a buy that was submitted and then rejected asynchronously counts as `other`.
- **EOD audit** (`fleet_eod_audit.rejections_today`):
  - A 403 is refused at submission and never becomes a broker order, so the audit counts from
    **our** `decisions.jsonl` outcome rows for the session. It ignores idempotent re-runs.
  - Broker-side `rejected` buys from the order list are added under `other`.
  - The row gains `orders_today.rejected` and `rejections` (with the `wash_sequences` stop-less
    window events).
  - Flag `REJECTED_BUYS k/n (…)` above 20%, and `TOPUP_UNPROTECTED` when any sequence left shares
    without a stop. Either flag makes the row DEGRADED.
- **Health** (`task_receipts._fleet_rejections_status`, on the Open and the Preclose pass):
  - DEGRADED when more than `FLEET_REJECTED_BUY_DEGRADED_FRAC` = 20% of the pass's LIVE buys were
    rejected. The reason names the counts by reason and the accounts.
  - On the 10-06 open receipt it reads DEGRADED: "broker rejected 15 of 19 LIVE buys (79% > 20%):
    15 wash-trade 403, 0 422, 0 other [hack1 1/2, hack2 5/5, hack4 9/9]".

**The lines tonight's receipt prints for rejections.** Per account, under the header:

```
  C27 rejections: <k> of <n> LIVE buys rejected by the broker (<p>%) -- <a> wash-trade 403, <b> 422, <c> other; <r> refused before the broker (REFUSED_WASH_TRADE_RULE/REFUSED_WORST_CASE_LINE)
  C27 sequences: <n> {'OK': ..}; longest stop-less window <s>s; unprotected shares <u>
```

Before orders:

```
  [hackN] C27 WORST CASE: now $X; after <k> top-up sequence(s) $Y (combined stops; old path would have added $Z); contract line $L [ALREADY ABOVE THE LINE before this run]
```

At the end, for the fleet: `FLEET C27 rejections: ...`. If the 10-06 plan repeats tonight, the
expected values are:

- hack4 `0 of 9`;
- hack1 `0 of 2`;
- hack2 `0 of 0 ... 5 refused before the broker`;
- fleet `0 of 14`.

## Files

**Changed:**

- `backend/services/fleet_manager.py`:
  - added `classify_rejection`, `rejection_summary`, `wash_conflicts`, `plan_topup_sequence`,
    `topup_worst_case`, `topup_line_walk`, `execute_topup_sequence` and `wash_sequence_summary`;
  - `GATE_POLICY_VERSION = "c27-wash-trade-sequence"`;
  - added a `wash_trade_sequence` policy choice.
- `scripts/fleet_manager_run.py`:
  - plans the sequence after the gates;
  - runs the worst-case line walk and prints it;
  - writes every decision row before the first order;
  - runs each sequence as one unit with the circuit breaker;
  - prints the rejection and sequence lines;
  - puts `wash_trade_rule` and the fleet `rejections` on the receipt.
- `backend/services/fleet_eod_audit.py`: `rejections_today`; `orders_today.rejected`; the
  `REJECTED_BUYS` and `TOPUP_UNPROTECTED` flags.
- `backend/services/task_receipts.py`: `_fleet_rejections_status` on both fleet passes.
- `backend/config.py`:
  - `FLEET_WASH_SEQ_BUY_WAIT_S`, `FLEET_WASH_SEQ_CANCEL_WAIT_S`, `FLEET_WASH_SEQ_MAX_WINDOW_S`,
    `FLEET_REJECTED_BUY_DEGRADED_FRAC`;
  - the known-defect line now names C27.
- `backend/tests/test_fleet_gates_c26_review.py`: the pinned policy version is now c27, and the c26
  choices are asserted unchanged.
- `backend/tests/test_fleet_eod_audit.py`: `orders_today.rejected`.

**Added:**

- `scripts/fleet_wash_trade_audit.py`
- `backend/tests/test_fleet_wash_trade_c27.py` (25 tests)
- `backend/tests/fixtures/c27/resting_2026-10-06_open.json`
- this note

**Not touched:** contracts, `modes.json`, `.env`. No live pass was run and no order was placed.
