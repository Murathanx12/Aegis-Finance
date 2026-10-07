# Fleet named gates and the end-of-day audit (C26, 2026-10-07)

**RESULT IMPROVEMENT: NONE.** This is risk plumbing. It changes no alpha source, no
contract, and no stop distance. It can only shrink or refuse what the frozen
contracts already propose. It also gives every account a daily row that names
a dead credential (hack3) and any held name missing its stop.

Licence: `PRODUCT_EXPERIMENT` (unchanged). The gates are not part of any frozen
contract, so their own hash (`gates_config()["hash"]`) is written on every
decision row next to the contract's policy hash.

Source of the pattern: `docs/OUTSIDE_TOOLS_2026-10-07.md` and
`docs/research_notes/2026-10-06/borrow_from_outside_2026-10-06.md` §Alpaca. Two
hackathon winners used it: Killswitch, with fifteen deterministic gates that
only shrink or kill, and Autobelay, with an end-of-day critique per account.
We take the deterministic half of each. **No LLM is involved, and none has
authority over an order.**

## 1. The gates, in order

Code: `backend/services/fleet_manager.py` → `GATES`, `run_gates`, `GateCtx`.
Config: `config.FLEET_GATE_ORDER`. A test fails if the two orders differ.

Each order proposal walks the list. Each gate returns `PASS`, `SHRINK(to)` or
`KILL`, with a reason. The walk stops at the first KILL. A proposal the planner
already refused (no price, below the minimum order) shows a single `planner`
row and is not walked.

| # | gate | class | what it does |
|---|---|---|---|
| 1 | `kill_switch` | lease | `fleet_manager/STOP` present → KILL everything |
| 2 | `credential` | lease | the account's own key was not accepted → KILL |
| 3 | `reconciliation` | lease | broker ≠ last record + fills, or a foreign executor → KILL everything (this is the single-writer lease) |
| 4 | `venue_window` | lease | a LIVE order while the venue is closed or within 5 min of the close → KILL (a DRY order passes) |
| 5 | `instrument` | shape | not a plain equity ticker → KILL |
| 6 | `order_shape` | shape | qty ≤ 0; not limit/stop; a buy without a limit; a non-protective stop → KILL |
| 7 | `long_only` | shape | a sell larger than the long position → SHRINK to the long quantity; nothing held → KILL (no shorts). **Change:** this used to KILL |
| 8 | `stop_never_loosened` | shape | a stop that replaces a resting stop below the old price is RAISED to the old price (recorded as SHRINK, quantity unchanged). The planners already take `max(old, new)`, so in practice this is an assertion |
| 9 | `min_order` | risk | an entry or trim below `min_order_usd` ($250) → KILL |
| 10 | `cooldown` | risk | **NEW.** No buy of a name a sell-stop filled on within N sessions. Unreadable stop history → KILL buys |
| 11 | `turnover_budget` | risk | an entry or trim beyond the day's turnover budget → SHRINK to what is left (KILL below the minimum). **Change:** this used to KILL |
| 12 | `cash` | risk | a buy beyond cash → SHRINK (no leverage) |
| 13 | `gross_cap` | risk | a buy beyond `max_gross_frac` × equity → SHRINK |
| 14 | `name_cap` | risk | a buy beyond the name cap → SHRINK. The cap is the contract's `max_name_frac`: **10%** on every hack contract today, with SPY at 95% on hack5 v2. The brief's "12%" is the v2 contracts' maximum stop distance, not a name cap |
| 15 | `sector_concentration` | risk | **NEW.** A buy that would take its sector above X of the account's gross → SHRINK (KILL if no room). A contract's declared name-cap override (the SPY control) is exempt |
| 16 | `order_count` | risk | an entry or trim beyond the per-run order cap (60) → KILL |

**What is pinned by tests** (`backend/tests/test_fleet_gates.py`):

- **Never enlarge.** `run_gates` refuses a gate that returns `SHRINK` to a
  larger quantity, a non-stop `SHRINK` to the same quantity, or an unknown
  verdict. Each of these is a `GATE_DEFECT` that kills the order. A gate that
  raises an exception is a `GATE_ERROR` and kills the order too. A test runs
  400 random proposals and checks that no row has `qty_out > qty_in`.
- **Exits are never blocked outside the lease class.** An exit is any of:
  `exit`, `cancel`, `stop_new`, `stop_renew`, anything protective, or a sell of
  the whole long position. In the test, an exit passes every risk gate with
  negative cash, gross at 5× equity, the turnover budget at 0, the order cap
  used up, unreadable stop history, a 1% sector cap and a 99-session cooldown.
  Only the four lease gates can refuse it.
- **Two shape gates can also refuse an exit**, and this is deliberate. An
  option or a malformed order is never built, and a sell with nothing held has
  nothing to exit.
- **Old refusals that are now passes.** Exits no longer spend the turnover
  budget and are not counted against the order cap. A full exit that the old
  path refused for budget or count now goes through. A trim (a partial sell)
  still pays the budget.

## 2. Config constants (`backend/config.py`, after `FLEET_MANAGER_CONTROL_STOP_FRAC`)

| constant | value | meaning |
|---|---|---|
| `FLEET_GATE_ORDER` | the 16 names above | must equal `[g[0] for g in GATES]` |
| `FLEET_GATE_COOLDOWN_SESSIONS` | 5 | weekday sessions (`sessions_between`). Blocked at N−1, allowed at N |
| `FLEET_GATE_COOLDOWN_LOOKBACK_DAYS` | 21 | calendar days of FILL activity read for stop fills |
| `FLEET_GATE_SECTOR_MAX_FRAC` | 0.40 | sector ≤ 40% × max(gross after the order, equity) |
| `FLEET_NEW_GATES_MODE` | `"shadow"` (added same day, after the decision below) | governs `cooldown` + `sector_concentration` only: "shadow" = evaluate and log `shadow_verdict` on the trace row, but `run_gates` always returns PASS (no KILL/SHRINK reaches the order); "enforce" = bind like every other gate. Hashed onto `gates_config()["hash"]` |
| `FLEET_EOD_AUDIT_GRADE_TOL_FRAC` | 0.005 | grade-ledger equity vs the broker's `last_equity` |
| `FLEET_EOD_AUDIT_SINCE_UTC` | `2026-10-07T12:00:00Z` | Preclose receipts started earlier come from code that had no audit, so the health reader excuses them |

**Where the sector comes from.** `book_dna.load_sector_map()` reads the newest
`potential_universe/*.jsonl` `identity.sector` (2026-09-02, 3,052 symbols). The
sector-map source is printed on the run receipt. A name with no sector joins
one bucket named `UNKNOWN`. If the map fails to load, everything lands in
UNKNOWN. That can only shrink more, and the failure is named on the receipt.

**How cooldown finds a stop fill.** It reads FILL activities (sell side) from
the last 21 days. It does not use the order list, because Alpaca's `after`
filter applies to the submission time, and the stops that fill are GTC orders
submitted weeks earlier. The order type comes from the closed orders submitted
in the window, or else from one `GET /v2/orders/{id}`. If any of these reads
fails, every buy on that account is killed with "stop history unreadable", and
`stop_history_error` is printed on the account block.

## 3. The end-of-day audit

- Code: `backend/services/fleet_eod_audit.py`.
- CLI: `python -m scripts.fleet_eod_audit [--trigger daily_check]`.
- Rows go to `backend/data/optimus/paper_accounts/fleet_manager/eod_audit/audit.jsonl`.

**Who runs it:**

- **The Preclose pass**, as its last step (`eod_audit_step`, trigger
  `preclose_pass`, same `run_id` as the run receipt). It audits every
  `FLEET_MANAGER_ROLES` account, including hack3, which the pass itself skips.
- **The 06:45 HKT daily check.**
  `aegis-alpha-terminal/scripts/fleet_daily_check.py` now runs the CLI as a
  subprocess with trigger `daily_check`, and adds a flag when the CLI exits
  non-zero. **That file is in the other repo and its change is not
  committed.**

**It can never place or cancel anything.** Its `Venue` is wrapped in
`readonly_transport`, which raises `EodAuditRefusal` on any verb other than GET.
`Venue.submit` and `Venue.cancel` refusing is pinned by a test.

**Row schema `fleet_eod_audit/1`:**

```
schema, run_id, trigger, t, role, places_orders: false
status          OK | DEGRADED | CREDENTIAL_INVALID | NO_CREDENTIAL | UNREADABLE | ERROR
credential      OK | INVALID_HTTP_401 | INVALID_HTTP_403 | MISSING | UNKNOWN
why             the flags joined, or the credential sentence
session_day_et, equity, cash, last_equity, n_positions, n_open_orders
orders_today    {n, ours (aegisfm prefix), foreign}
stops           {n_held_long, n_protected, missing: [sym], partial: [{symbol, qty, covered}]}
reconciliation  {state:  {status, since, n_fills_since, n_mismatch, examples},
                 grades: {status, newest_session, grade_equity, broker_last_equity, rel_diff, n_mismatch, examples}}
n_mismatches, mismatch_examples (<= 5)
worst_case      {usd_at_stops, pct_equity, gross_usd, gross_over_equity,
                 formula_bound: {n, notional_frac (largest), stop_frac (widest; 1.0 if any name is unstopped),
                                 worst_frac, worst_usd, gross_over_equity}}
flags           MISSING_STOP [...], STATE_MISMATCH (k), GRADES_MISMATCH (k), NEGATIVE_CASH, SHORT_SHARES
```

**When a row is DEGRADED:**

- a held long equity name lacks a stop for its full quantity;
- the broker ≠ `state/<role>.json` plus the fills since it was written, or an
  order without our prefix was submitted since then;
- the newest grade is older than the previous session, or its equity differs
  from `last_equity` by more than 0.5%;
- cash is negative;
- the account holds short shares.

**Health.** `task_receipts._fleet_pass("preclose")` now reads the audit rows
that carry the receipt's `run_id`:

- no row → **DEGRADED**, with the reason "no end-of-day audit row for preclose
  run_…";
- rows present → the same per-account rule as the passes. Any non-retired
  account that is not OK makes it DEGRADED. hack3 is excused by
  `PAPER_ACCOUNTS_RETIRED_UNREADABLE` but still appears in the detail.

The Open pass's health is unchanged.

## 4. Worst case for the five readable accounts (read-only, from files)

Positions come from `state/hack*.json` (all written 2026-10-06 19:30–19:31 UTC).
Prices and resting stops come from the same pass's receipt,
`runs/run_20261006T193006Z-b38268.json`. For every account the state matches
the broker read in that receipt. **No broker call was made for this table.**

| account | equity | n | Σ\|notional\|/equity | worst at resting stops | % equity | bound n × max notional × widest stop | top sector (share of max(gross, equity)) |
|---|---|---|---|---|---|---|---|
| hack1 | $92,927 | 24 | 0.966 | $10,880 | 11.7% | 24 × 0.272 × 0.184 = $111,235 | Electrical Equipment 27.5% |
| hack2 | $102,235 | 20 | 0.955 | $10,983 | 10.7% | 20 × 0.051 × 0.173 = $18,088 | **Technology 67.3%** |
| hack4 | $79,591 | 11 | 0.810 | $4,632 | 5.8% | 11 × 0.235 × 0.154 = $31,657 | Technology 35.0% |
| hack5 | $96,327 | 1 | 0.947 | $10,899 | 11.3% | 1 × 0.947 × 0.120 = $10,899 | UNKNOWN (SPY) 94.7%, exempt |
| hack6 | $81,517 | 38 | 0.809 | $6,680 | 8.2% | 38 × 0.079 × 1.0 = $243,142 | Biotechnology 20.1% |
| **fleet** | $452,597 | 94 | | **$44,074** | 9.7% | | |
| hack3 | unreadable (401 since 2026-09-22) | | | | | | |

**Reading the table:**

- The bound is deliberately loose. On hack1 and hack4, one legacy position
  drives it: about 27% and 23% of equity in a single name, held under v1
  terms.
- hack6's bound uses a widest stop of 1.0 because PPLI read as unstopped
  *before* that same pass placed its `stop_new` (LIVE, 19 shares at 38.23).
  The first audit row tonight will show whether that stop is resting.
- **Each account's worst case is about 5.8–11.7% of equity**, if every resting
  stop fills at its price. A gap can fill worse.

**What the new gates will do tomorrow:**

- **hack2: Technology is already 67% of the account, above the 40% cap.**
  Without a decision, the sector gate would KILL every Technology buy
  (top-ups in the analyst-revision book), drifting hack2's executed book from
  its frozen book and twin before the owner had chosen to allow that.
  **Decided 2026-10-07, same session: `config.FLEET_NEW_GATES_MODE = "shadow"`
  (the default).** `cooldown` and `sector_concentration` both still evaluate
  against the real order and book tonight, but `fleet_manager.run_gates`
  overrides a KILL or SHRINK from either one back to PASS before it reaches
  the order -- hack2's Technology buys execute at full size tonight, exactly
  as the frozen book and twin expect, and the gate drag this paragraph
  described does **not** happen yet. **Decisions for Murat (still open,
  unblocked by tonight's run):** keep the sector cap at 40%, raise it, or
  exempt a single-alpha-source book such as hack2 -- then flip
  `FLEET_NEW_GATES_MODE` to `"enforce"` once one of those is chosen.
  **The first live trace will show, for every hack2 Technology buy tonight:**
  `gates[]` carries a `cooldown`/`sector_concentration` row with
  `"verdict": "PASS"` and a `"shadow_verdict"` field reading
  `SHADOW_WOULD_KILL: ...` (cooldown, if the name was recently stopped out) or
  `SHADOW_WOULD_SHRINK(to=<q>): sector Technology <= 40% of gross: ...`
  (sector_concentration) -- i.e. the order is NOT refused or resized
  (`refused` is `null`, `qty_out == qty_in` on that row), while the shadow
  field names exactly what would have bound under `"enforce"`.
  `gate_summary.sector_concentration` / `.cooldown` will show `PASS` counts,
  not `KILL`/`SHRINK`, for as long as the mode stays `"shadow"`.
- **hack4** has room: Technology is at 35% against the 40% cap.
- **hack1** has room: Electrical Equipment is at 27.5%.
- **hack5:** SPY is exempt.

## 5. Reading tomorrow morning's first gate trace

The next scheduled Open pass runs this code. Then:

1. Open the newest `fleet_manager/runs/run_*.json` with `"pass": "open"`.
   - The top-level `gates` block has the order, the config and the hash.
   - `sector_map` names the source file. If it starts with `REFUSED`, every
     name was in UNKNOWN.
2. For each account:
   - `gate_summary` gives `{gate: {PASS, SHRINK, KILL}}` counts. Look first at
     `cooldown`, `sector_concentration` and `turnover_budget`.
   - `stopped_out_recent` gives `{symbol: date}`. `null` means the stop history
     was unreadable, and `stop_history_error` says why. In that case every buy
     was killed.
   - `sector_gross` gives the sector notional before the run.
3. Each entry in `actions[]` has a `story_id` (`fs-…`) and `gates[]`: one row
   per gate evaluated, `{gate, class, verdict, reason, qty_in, qty_out}`.
   - The story is order → gates → outcome.
   - `refused` reads `"<gate>: <reason>"`.
   - A SHRINK shows `qty_in > qty_out`, and the action's `qty` is the shrunk
     size that was sent.
4. The same trace is on each `decisions.jsonl` decision row (`gates`,
   `gates_hash`, `story_id`). Use those rows to join outcomes later.
5. After tonight's Preclose pass:
   - the receipt carries `eod_audit: {status, rows_written, accounts}`;
   - `eod_audit/audit.jsonl` holds one row per role with that `run_id`.
   - Expect hack3 `CREDENTIAL_INVALID` (excused). Every other account should
     be OK. A DEGRADED row's `why` names the missing stop or the mismatch.

**What to check first:**

- **hack2's Technology `shadow_verdict: SHADOW_WOULD_KILL`/`SHADOW_WOULD_SHRINK`
  entries on the `cooldown`/`sector_concentration` rows, with `verdict: PASS`
  and `refused: null` on those same actions** (expected, while
  `FLEET_NEW_GATES_MODE == "shadow"`; a real KILL there would mean the mode
  was flipped to `"enforce"` without the decision above being made).
- **Any `GATE_DEFECT` or `GATE_ERROR`** (there should be none).
- **Whether any exit shows a KILL from a non-lease gate.** That would be a bug:
  the invariant test says it cannot happen.

## Files

**Added:**

- `backend/services/fleet_eod_audit.py`
- `scripts/fleet_eod_audit.py`
- `backend/tests/test_fleet_gates.py`
- `backend/tests/test_fleet_eod_audit.py`
- this note

**Changed:**

- `backend/services/fleet_manager.py`: the gates; `Venue.stop_fills_since`; a
  renewal records `replaces_stop`.
- `scripts/fleet_manager_run.py`: gates walk replaces the hard-gate block;
  entry protection walks the gates; trace and story id on rows; `eod_audit_step`
  on Preclose; sector map and gates on the receipt.
- `backend/config.py`: the constants above.
- `backend/services/task_receipts.py`: the Preclose reader requires the audit.
- `backend/tests/test_guard_missing_input_contract.py`: `fleet_eod_audit`
  enrolled.
- `aegis-alpha-terminal/scripts/fleet_daily_check.py` (**other repo, not
  committed**).

**Not touched:**

- `modes.json`, the v1/v2/v3 contracts, `.env`.
- No live pass was run. No order was placed.
