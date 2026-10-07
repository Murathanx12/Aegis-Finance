# REVIEW 2026-10-07: C26, the fleet's named gates and end-of-day audit

Reviewer: Opus 5.5, adversarial (risk officer + the operator who reads tonight's 22:45 HKT open-pass receipt).
Scope: `backend/services/fleet_manager.py` (named gates, `Venue.stop_fills_since`), `scripts/fleet_manager_run.py`,
`backend/services/fleet_eod_audit.py`, `scripts/fleet_eod_audit.py`, `backend/services/task_receipts.py`,
`backend/config.py` C26 block, the sibling `aegis-alpha-terminal/scripts/fleet_daily_check.py` (uncommitted there).
Mode: read-only. No broker call, no fleet pass, nothing edited or committed. Receipts read:
`fleet_manager/runs/run_20261006T144500Z-604e5b.json` (open), `run_20261006T193006Z-b38268.json` (preclose),
`state/*.json`, `grades.jsonl`, `modes.json`.

## VERDICT: MERGE WITH FIXES (already on main at 92f147f6)

Nothing in C26 makes tonight's 22:45 HKT open pass unsafe. I replayed the 10-06 open plan through the new gate list on
the 10-06 open context, and **every order comes out at the same quantity with the same LIVE/REFUSED outcome** (F1).
The two new gates are in shadow, and the worst case reproduces to the cent (F7).

Two one-line changes are worth making **before 22:45 HKT**. Neither is a safety block.

1. **The stop-history read catches only `FleetRefusal`** (F4). This read has never run against a real account. A
   timeout or a malformed 200 raises something else, and that turns the whole account into `ERROR`, including its
   protective-stop maintenance. Widen it to `except Exception` and set `stopped_out = None`.
2. **Print the C26 delta** (F12). In shadow, `gate_summary` counts every shadow verdict as `PASS`, and `print_role`
   prints no gate information at all. Tonight's receipt therefore cannot tell the owner whether C26 changed anything.
   The research note tells the operator to "look first at cooldown / sector_concentration in `gate_summary`", and in
   shadow those cells always read PASS.

Everything else can be fixed after tonight.

## Results scoreboard

RESULT IMPROVEMENT: NONE. C26 adds governance and observability. It does not move a forecast, a selector or a fill.
The largest execution defect in the fleet this week is not in C26's scope, and C26's audit does not see it either
(F7): **49 of 75 LIVE buys since 10-01 were rejected by the broker with HTTP 403 "potential wash trade detected"**.

## Tests (item 7)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_fleet_gates.py \
  backend/tests/test_fleet_eod_audit.py backend/tests/test_fleet_manager*.py -q
........................................................................ [100%]
72 passed in 2.10s
```
(The builder quoted "388 then 64/101". On the four files named, it is 72 passed.)

**Mocks used:**
- Everywhere: `FM.Venue(transport=<fake>)`.
- In `test_run_role_puts_a_named_gate_trace_on_every_action`:
  - `_VenueFake`, monkeypatched over `FM._urllib_transport`;
  - `FM.root` -> tmp_path;
  - `RUN.panel_sigma_and_screen` and `RUN.stop_counterfactual_step`, both stubbed.
- In the EOD tests:
  - `FleetFake` transports;
  - `EOD.run_audit`, monkeypatched to raise for the refusal test.
- `stop_fills_since` is tested against one hand-written Alpaca shape: a JSON list for FILL activities, plus one GET
  for the old GTC order.

**No replay test exists.** No test runs the full gate list on a real-shaped 10-06 run receipt and asserts that the
same orders come out. I ran that replay by hand (F1), and it should become a fixture test. The 400-case
never-enlarge property test runs in the default (shadow) mode, so the two new gates' SHRINK paths are never
exercised under it. It also never generates a stop order, so `stop_never_loosened` is outside the property.

## Findings

### F1 (INFO, the good news). The new gate list is behaviour-neutral on the last real plan
I rebuilt `GateCtx` from the 10-06 open receipt (positions' market value, equity, cash, the real v2 contract, and the
sector map) and walked every one of the 66 proposed actions across hack1/2/4/5/6 through `run_gates`. Every action's
executed quantity and LIVE/REFUSED outcome is identical to what the old `check_limits` path produced. The only new
output is three `shadow_verdict`s on hack2 (F5). The script is about 60 lines (reviewer scratchpad `c26/replay.py`)
and should become the replay test.

### F2 (MEDIUM). Behaviour changes on live paper that were not owner decisions (item 1)
Per-order, each gate can only shrink. **At the system level, though, C26 executes more than the old code did in every
case where the old code refused.** An old refusal sent 0 shares; a shrink now sends `to > 0`. Classified:

| change | what it does | classification | shadow it? |
|---|---|---|---|
| oversized sell -> cut to shares held (was KILL) | arises when `held + pending` makes the delta exceed the long. The exit goes through instead of being refused | **correction** of an obvious bug: the intent was "exit", and the old refusal left the name held | no |
| cash / gross / name cap -> SHRINK to fit (was KILL) | hack1 cash $3,185 and hack2 $4,624 at the 10-06 preclose, so cash can bind tonight. Old: the largest buy over cash was refused and smaller buys still went. New: the largest buy is shrunk to all remaining cash, and every later buy dies at "< min order". **Which names get bought changes** | sizing-policy change inside unchanged caps. The gross, name and cash bounds still hold, so it is **risk-neutral** but **changes composition** | no, but record the old verdict ("instead" #1) |
| turnover -> SHRINK (was KILL), and full exits no longer spend the budget | more buy notional per session than v2 executed before. `daily_turnover_frac` is a FROZEN contract term (`caps_block`), and its implemented meaning at freeze counted full-exit sells | **loosening** of a frozen term's interpretation, bounded by 0.5 x equity of entries | yes, or record an owner line in `modes.json` `_history` |
| exits exempt from `max_orders_per_run` | the circuit breaker no longer bounds cancels, stops or exits. A planner bug that churns cancel/re-stop pairs is now unbounded | **loosening of a circuit breaker**. The cap exists for runaway loops, not for risk | restore it: count everything, and give exits a separate, higher cap (e.g. 2x) |

None of these would have changed 10-06 (F1). The cash shrink is the one most likely to bind tonight, because hack1
and hack2 run near zero cash. The owner should hear about it as a sentence, not find it as a SHRINK count.

### F3 (MEDIUM, latent). A shrunk or killed TRIM leaves shares without a stop until the preclose pass
The sell expansion in `fleet_manager_run.py` ("a sell must first release shares its resting stops hold") emits this
sequence **before the gates run**: cancel every resting stop on the name -> the trim sell of `q` -> a `stop_new` for
`rem = held - q`. The cancel is protective, so every risk gate passes it. The trim is not an exit, so it pays turnover
and the order count:
- if `turnover_budget` SHRINKS the trim to `q' < q`, then `q - q'` shares have no stop;
- if `turnover_budget` or `order_count` KILLS the trim, `q` shares have no stop.

In both cases the gap lasts about 4h45m, until the preclose maintenance re-covers it. The KILL variant predates C26.
The SHRINK variant is new with C26. Fix: size the re-protect stop from the post-gate quantity (run the gates on the
sell before building its stop), or gate the cancel/sell/stop triple as one unit.

### F4 (MEDIUM, fix before 22:45). Cooldown's fill read: never run live, and the wrong except (item 3)
- **Has it ever read real fills? No.** Both 10-06 passes predate the commit: the receipts carry no
  `stopped_out_recent`, `stop_history_error`, `gate_summary` or `gates` keys, and `eod_audit/` does not exist yet.
  Tonight's 22:45 open pass is the first time these calls hit the real accounts:
  `GET /v2/account/activities/FILL` (with `after`, `page_token` and `direction=desc`), the closed-orders list, and
  one GET per old order.
- `run_role` catches `FM.FleetRefusal` only. `Venue.get` raises `FleetRefusal` on non-200, but `_urllib_transport`
  lets `URLError` and socket timeouts through. A 200 whose body is a dict (an error envelope) is iterated by
  `out.extend(page)` as keys, and then `f.get` raises `AttributeError`. **Either failure aborts the whole account,
  including its protective-stop maintenance.** The read sits after planning and before any order. One line:
  `except Exception as exc: stopped_out = None`.
- **Fail-closed is right in principle, but nothing would see it.** In `enforce`, `stopped_out is None` kills every buy
  on the account. Tonight in shadow it only adds `SHADOW_WOULD_KILL` to every buy. Either way, the account's `status`
  stays `"ok"`. `task_receipts._fleet_pass` reads only `accounts[*].status` and the EOD rows, and `print_role` does
  not print `stop_history_error`. **That is a silent book freeze that health would read as green.** Before any flip
  to enforce, `stop_history_error` must make the account `DEGRADED`.
- `fills()` stops at 10 pages x 100 rows without saying so. That is harmless for a 21-day window on these accounts,
  but the truncation is not named.

### F5 (MEDIUM, owner input before enforce). The sector map is the wrong granularity (item 4)
- **Source:** `potential_universe/2026-09-02.jsonl identity.sector`, 3,052 symbols, **35 days old**. Nothing checks
  its age; the receipt prints only the file name.
- **The map has 46 labels at mixed levels:**
  - `Technology` (228 names) is the catch-all for software and hardware. It sits beside `Semiconductors` (96),
    `Electrical Equipment` and `Machinery`.
  - `Banking` sits beside `Financial Services`.
  - `Health Care` sits beside `Biotechnology` and `Pharmaceuticals`.
  - A literal `N/A` label (16 symbols) is a separate bucket from `UNKNOWN`.
  - NVDA/AVGO/MU/TSM are `Semiconductors`, while MDB/NET/SNOW/CRM/AAPL/MSFT/DELL/ZS are `Technology`.

  **A 40% cap on these labels measures the taxonomy, not concentration.** hack2's software book is 68% `Technology`
  and binds. hack1's AI-capex book passes every check, although it is about 70% one theme: Electrical Equipment
  27.5% + Machinery 27.0% + Semiconductors 15.5%.
- **UNKNOWN as one bucket:** ETFs (SPY, QQQ) and unmapped names share it. hack5's SPY is exempt through
  `name_cap_overrides`; hack6's QQQ is not. If the map is unreadable, every name is UNKNOWN, at about 85-95% of the
  denominator. In enforce, **every buy on every account is killed**, while the account still reads `"ok"` (the same
  silence as F4). Tonight, in shadow, that would only add noise.
- **hack2 tonight, computed from the 10-06 open context:** gross $99,112, equity $102,866, Technology $67.4k = 68.0%
  of max(gross, equity).
  - Room under 40% is negative, so **any Technology buy logs
    `SHADOW_WOULD_KILL: sector Technology <= 40% of gross: room $0 leaves less than the $250 minimum order`**.
  - Replaying the 10-06 plan, that means MDB, NET and SNOW.
  - AMGN (Biotechnology) and TGT (Retail) pass. CRM, WDAY and ABNB are killed by the planner's min-order rule first.
  - **All three shadow-killed names were also rejected by the broker (403 wash trade) on 10-06.** On that day the
    gate would have changed nothing that executed.
  - Other accounts: hack4 `Technology` is at 35.8%, close to the line. hack1 and hack6 are under 30% in every label.

### F6 (LOW). Never-enlarge holds; the stop path is the only subtle one (item 2)
**Quantity paths, traced gate by gate:**
- `_shrink` floors (`int(math.floor(cap/px + 1e-9))`) and returns PASS when `q >= qty`.
- `long_only` floors the held quantity.
- No gate touches `limit_price`.
- `run_gates` kills any `SHRINK` with `to > q_in`, and any non-stop `SHRINK` with `to == q_in`.
- No board-lot rounding exists anywhere, so there is no rounding-up path.

**The stop path:**
- `stop_never_loosened` is the only mutation that is not a quantity. It RAISES `stop_price` to the replaced stop, so
  the stop distance tightens.
- `Action.notional` for a stop rises with it. Nothing downstream sizes on a stop's notional, because exits pass every
  risk gate.
- Both planners already take `max(old, new)`, and the renewal path refuses a stop at or above price.
- `stop_price_for` -> `round_price` runs before the `max`, so the resting price `old` is never rounded down.

**No enlarging path found.**

**Two inaccuracies:**
- The builder's summary says "an exit is refused only by the four lease gates". That is false as written:
  `instrument`, `order_shape` and `long_only` can refuse an exit too. The research note admits this; the summary
  does not.
- The cross-run turnover sum `used` still counts full-exit sells from earlier passes, while the in-run gate exempts
  them. The two accountings disagree.

### F7 (MEDIUM). The EOD audit (item 5)
**401 handling: CREDENTIAL_INVALID, no crash.**
- `venue.call` returns `(401, ...)`, the row is written, and the loop continues.
- hack3 is excused through `PAPER_ACCOUNTS_RETIRED_UNREADABLE`.
- Any other exception becomes that account's `ERROR` row. Correct.

**What counts as a mismatch:**
- state: `FM.reconcile(state.positions + FILL activities since state.t, broker, orders since)`, giving position
  mismatches plus orders without our coid prefix;
- grades: the newest grade row's `equity` against the broker's `last_equity` at 0.5% tolerance, or a grade older than
  `prev_weekday(today)`.

**Weaknesses in the reconciliation:**
- At trigger `preclose_pass` the state check is close to a tautology. The same pass wrote `state/<role>.json` seconds
  earlier (`t2`), so "fills since" is empty and broker equals record. The informative run is the 06:45 HKT daily
  check, which catches anything after 15:30 ET, including stop fills in the last half hour.
- `prev_weekday` ignores exchange holidays, so the day after Thanksgiving (2026-11-27) will report a false
  `GRADES_MISMATCH`.

**Blind spot: broker rejections.** `orders_today` counts ours vs foreign and never counts REJECTED.
- Since 10-01 the broker rejected these LIVE buys with `403 potential wash trade` on the four open passes: 10/17,
  11/20, 13/19 and 15/19 (49 of 75).
- They are top-ups of names that hold a resting GTC sell stop.
- The executed books have drifted from their frozen v2 targets by this mechanism, more than anything C26 changes.
- An audit built to catch "an account nobody was watching" reports these accounts `OK`.
- Fix: add `orders_today.rejected` and a `REJECTED_ORDERS` flag.

**Which stop the worst case uses:** the **resting GTC stop price**, not the contract's stop %. It takes the minimum
`stop_price` across the name's stops when they cover the full quantity, and the whole position otherwise. That is
the right choice: hack1's resting (partly legacy v1) stops give $10,880, against $8,947 at the v2 contract stop %.

**Recomputed from `state/hack1.json`:** 24 names, quantities identical to the broker, times 10-06 preclose prices,
at the resting stops.

| account | worst case |
|---|---|
| hack1 | **$10,879.73 (11.71% of $92,926.62), an exact match** |
| hack2 | $10,983.36 |
| hack4 | $4,631.63 |
| hack5 | $10,898.55 |
| hack6 | $6,679.81 |
| fleet | **$44,072.98 = 9.74% of $452,595** (the builder's $44,074 is rounding) |

Gap risk through the stop is not in the number. The receipt says so, and the audit row should say so too.

### F8 (LOW-MEDIUM). Sibling-repo coupling (item 6)
**The setup works today.**
- The scheduled task `AegisFleetDailyCheck` runs aegis-finance's `.venv` python, with cwd in the terminal repo.
- The child process gets `sys.executable` (the same venv) and `cwd=aegis-finance`.
- `import scripts.fleet_eod_audit` succeeds under that venv (verified).

**If it ever fails:**
- **loud in the log:** rc != 0 -> `FLAG EOD_AUDIT_NOT_OK`, with `stderr_tail` in the receipt;
- **quiet on the health surface:** `task_receipts.r_fleet_daily` derives status from `accounts[*].status` only and
  shows `n_flags` as detail text. An import error and a DEGRADED account produce the same flag text, and neither
  turns the reading red.

The sibling change is also **uncommitted**, so a reset in that repo deletes it.

### F9 (INFO). The gates hash makes a flip visible
`gates_config()["hash"]` includes `new_gates_mode`, so a flip to enforce changes the hash on every decision row, as
claimed.

### F10 (LOW). The operator note is stale on shadow
`fleet_gates_and_eod_audit_2026-10-07.md` §"tonight" has two statements that are wrong while the mode is shadow:
- It says `stopped_out_recent: null` means "every buy was killed". In shadow, no buy was killed.
- It says to read cooldown/sector in `gate_summary`. In shadow those cells only ever read `PASS` (F12).

### F11 (LOW). Every decision row now carries 16 gate rows
`decisions.jsonl` is already 617 KB. With about 20-60 actions x 16 gate rows per pass, the file now grows several
times faster. Nothing breaks, but the fixed-window tail reads in `task_receipts` need watching (`audit.jsonl` uses
256 KiB).

### F12 (MEDIUM, fix before 22:45). The operator's one line (item 8)
The owner's question is whether C26 changed anything tonight. The answer should be one line per account:

`C26 delta: shrunk n (old path would REFUSE m, +$X executed) | shadow would-kill k / would-shrink j | stop history OK|ERR`

**The receipt does not print it.**
- `gate_summary` records shadow verdicts as `PASS`.
- `print_role` prints no gate information.
- No field compares against the old `check_limits` verdict, which is kept verbatim in the module and could simply be
  called beside `run_gates`.

The minimum before 22:45 is to count `shadow_verdict`s and SHRINKs per account into `res["c26_delta"]` and print it.
The proper version is "instead" #1.

## Three things I would have done instead

1. **Run the old hard gate beside the new one for a week.** Call `check_limits` (kept verbatim) and the old
   turnover/order-count accounting on every action, store `old_verdict` on the trace, and print the disagreement
   count as the receipt's first line. That turns every semantic change in F2 into evidence, instead of a
   classification in a review.
2. **Ship the replay test first.** Take the 10-06 open receipt as a fixture, rebuild `GateCtx` from it, and assert
   the identical executed set. Then each behaviour change arrives as a diff to that fixture's expected output, with
   the owner's name on it.
3. **Use the right taxonomy, and put rejections in the audit.**
   - Map to GICS sector (11 buckets) from the same identity source, or skip the sector gate for books whose declared
     selection is a single theme.
   - Make ETFs look-through, or put them in a named `ETF` bucket rather than `UNKNOWN`.
   - Spend the audit's first column on `REJECTED` broker orders. That is where the fleet actually diverges from its
     contracts today (49 of 75 live buys).

## Score: 74 / 100

**What C26 gets right:**
- An ordered gate list with classes, a per-order story id and trace, and a gates hash on every row.
- The invariants are pinned by tests and hold under my trace.
- The new gates are shadowed by default, and the shadow mode is hashed.
- The audit transport refuses every write verb by construction.
- The 401 is named, not skipped.
- The worst case is exact and reproducible.

**What costs points:**
- System-level loosenings shipped without an owner line or a counterfactual: turnover, the exit exemption, and the
  order-count circuit breaker.
- The first live run of a new network read catches the wrong exception.
- Shadow results are invisible in the summary the operator is told to read.
- The sector gate runs on a mixed-granularity taxonomy.
- The audit is blind to the fleet's dominant execution failure.
- There is no replay test.
