# REVIEW 2026-10-06 — C2: PC-PAPER mandate on broker equity + the sim owner

Adversarial review, written as an investor and a risk officer. The build is in
WIP commit `f4dbd0c0` on `wip/2026-10-06-v1-beta`. I changed no code, moved no
limit, and started or stopped nothing. Evidence is from read-only Python over
the receipts and bars, the targeted suite, and the live session's own files.

## VERDICT: MERGE WITH FIXES

The plumbing works. The capital is derived from the broker, the owner fires
and writes one row per firing, the scaled views are honest about whole shares,
and the targeted tests pass (90 of 90). **The risk gate that decides whether
the account may trade passes for the wrong reason, though.** It prices the
book at a stale median-of-everything sigma. The names the EXPLOIT sleeve would
actually buy today carry about twice that sigma, and on those names the same
gate says **REFUSE (14.0% vs 10%)**. The other blocker is the word
"reconciled": what the build reconciles is the capital against itself. The
contract and the account still disagree about where the dollars are, and
nothing checks that.

Fixes required before merge: F1, F2, F3, F4. F5–F9 can follow.

RESULT IMPROVEMENT: NONE. The account held 10 names at 2% each and 80% cash
before this chunk, and it does the same after it.

---

## Findings

### F1 — HIGH. The worst-case gate passes on a sigma that the sleeve it protects does not have

- The gate is `gross × k × PROBE_REF_DAILY_SIGMA`, which is 1.00 × 3 × 2.16% =
  6.48%, compared with `PC_WORST_CASE_MAX_FRAC_OF_EQUITY` = 10%. The constant
  2.16% is the median name from the 2026-09-24 note. It is not recomputed.
- Recomputed by me on `prices_2025_26/bars.parquet`, last 90 calendar days to
  2026-10-05, with 40 or more returns per name, 3,058 names:
  - Universe daily sigma percentiles: p50 **2.51%**, p75 3.66%, p90 **4.90%**,
    p95 5.76%. Even the median is above the constant. At the median the gate
    gives 7.54%, which passes. At p90 it gives **14.69%, which is REFUSE**.
  - The bottom 40% of names by dollar volume: p90 5.10%, giving 15.3%.
  - The gate's own break-even, `daily_sigma_at_limit`, is 3.33%. **30.9% of
    the universe is above it.**
- What matters is **which names the sleeve buys**. EXPLOIT draws from
  `xs_ranker`, which ranks 2,884 eligible names, not from the low-vol funnel.
  Today's `ranking.json` top 25 have median sigma **4.51%** and p90 6.81%. The
  top eight are LITE 5.95, CDNL 7.54, ASPN 5.53, BRUN 7.82, NBTX 4.66, MSFT
  2.38, AMD 3.98 and OSS 4.51 (%). The largest admissible book built from those
  eight at 10% each, plus PROBE at 20% on the median sigma, has a one-day
  3-sigma loss of **14.0% of equity, which is REFUSE.**
- The funnel's 25 names are calm (p90 2.58%, giving 7.7%) because the funnel
  applies a low-volatility filter. That is the PROBE pool, not the EXPLOIT pool.
  The gate measures the calm sleeve and approves the volatile one.
- Today EXPLOIT is refused on MEASURED_NEGATIVE (`top20_net_rel_21d` −0.93%),
  so no money is at risk yet. **The day the ranker turns positive, the owner
  starts `paper_profit` on a PASS that would have been a REFUSE.** CLAUDE.md
  protocol 4 says "the LARGEST admissible book". On these names, that book
  fails.
- The 10% bound is a declared constant (good). It covers one day and the whole
  book, not a single position. It is checked **once, when the owner starts a
  session**: not each cycle, not on a manual start, and not in the order path
  (see F3).
- The ρ = 1 assumption (gross × kσ) is conservative across names. It does not
  capture single-name gap risk, though. A 12% name (broker cap) gapping −50% on
  a biotech readout costs −6% by itself. The sim's equal-weight fallback
  (`w_ex = room / len(ex_syms)`, used when no E[r] is priced) is **not** capped
  at `ER_EXPLOIT_MAX_WEIGHT`. Only the broker's 12% stops it.

**Fix:** compute sigma per name from the same panel the fleet manager uses
(`fleet_manager.sigma_stop_frac` already does this). Price the gate on the
names each sleeve would buy, with the ranker's top-N for EXPLOIT, and use the
max of (that book, the p90 of the eligible universe). Print both numbers.

### F2 — HIGH. "Reconciled" is a tautology; the real disagreement is not checked

- `_capital_from_broker()` sets capital to the broker equity. Then
  `account_mandate` compares capital with the broker equity. On the normal path
  `CAPITAL_BASES_DISAGREE` **cannot fire**. The receipt's move from
  "$40,000 UNRECONCILED" to "$1,003,532 OK" came from redefining the capital,
  not from reconciling anything. The only test with any bite is the age check.
- The disagreements that actually remain are not checked:
  - Today's contract (`decisions/2026-10-06.json`) still has **three agency
    BUY rows sized at $40,000**, taken from the IPS `Strategy.sizing.notional_usd`,
    beside a capital of $1,003,532. `capital_resolution` calls them
    "ALTERNATIVE whole books at this same capital", which is false. The literal
    `40000` is gone from the code (the AST test is right about that). It moved
    into data, which is the two-incomparable-dollar-columns problem that the
    deleted `_capital_from` docstring warned about.
  - `capital_resolution` says **99.75% benchmark core ($1,001,023)**. The
    broker holds **80% cash** and 20.2% in ten names. The contract describes a
    portfolio the account does not hold, and no line compares the two.

**Fix:** rename what exists (`CAPITAL_SOURCE: broker`) and add the real
reconciliation: contract-resolved weights vs broker positions, by name and by
sleeve, with cash as its own line. That check goes red on today's data. Size
the agency rows at the contract's capital, or label them at the IPS capital
explicitly and keep them out of any "same capital" sentence.

### F3 — HIGH. The mandate guards the owner's front door, not the order path

- `MANDATE_GATES_ORDERS` is still False. `sim_owner_mode` picks the mode
  **once**, at start. After that, a 6–8 h `paper_profit` session trades without
  rechecking the mandate. Equity can go stale, the worst case can flip, or
  `OWNER_STOP` can appear (the owner's pause only stops *new* starts; it does
  not stop a running session). A manual start (button, or Telegram
  `/sim start`) in `paper_profit` skips the mandate and the worst-case gate
  entirely.
- The builder's report says "trades only when mandate OK and worst case
  passes". That holds only for sessions the owner starts.

**Fix:** move the check into `u_plan`: re-evaluate the mandate and the gate
each cycle, and treat a REFUSE as `send_block`. Have a manual `paper_profit`
start go through the same `sim_owner_mode`. Make `OWNER_STOP` also call
`request_stop` on a running session, or document that it does not.

### F4 — MEDIUM-HIGH. The cited receipts are not in the commit

`git status` shows the evidence the report cites as **untracked or dirty**:
`backend/data/optimus/pc_mandate/` (the reconcile receipt), `sim/owner.jsonl`,
`backend/data/funnel_history/funnel_2026-10-06.json`, and the refreshed
`backend/data/funnel_night10.json` (modified, not committed). "Committed in
f4dbd0c0" is true of the code and false of the receipts. The reconcile receipt
and today's contract also carry absolute local paths (`contract_path`,
`broker_equity_source`), although the code now writes ledger-relative paths. A
live call today returns `paper_accounts/pc_snapshot/state_latest.json`, so the
on-disk receipts came from an earlier code state.

### F5 — MEDIUM. Stale-equity semantics: a failed live read can still trade

- Before each start the owner makes a **live** read (`pc_broker.snapshot`) and
  persists it. If that read fails (`broker_read.ok == False`), the mandate
  falls back to the newest file read. That read is up to 4.0 days old and
  still counts as OK. The owner then starts `paper_profit` on equity it just
  failed to confirm. Four days covers Friday-close to Tuesday-open over a
  holiday Monday (about 3.7 d), so the window is real.
- `pc_paper_equity` never checks `account_number`. All files today carry the
  same paper account, but if the PC keys are rotated to another account, the old
  account's $1M read is accepted for up to 4 days. Every snapshot already stores
  `account_number`, so the fix is cheap.
- Who writes the read: `pc_broker.snapshot` writes it on every owner firing
  (tag `sim_owner`), on every sim plan cycle (day folder, tag `plan`), and on
  the daily pass (`paper_accounts/pc_snapshot`). The newest read wins by its
  own `t`, which is correct (protocol 7).

**Fix:** `broker_read.ok == False` should force `observe`. Pin the expected
account number and refuse a read from any other account.

### F6 — MEDIUM. Health is ALIVE while the account cannot trade

`p_sim_session` returns ALIVE for any RUNNING session. If the owner started it
in `observe` (trading refused), the reason is only appended to the detail. If
it runs in `paper_profit` with EXPLOIT refused and PROBE unchanged, it is still
ALIVE. History: session 2026-09-28 ran 103 cycles and sent 3 orders. Session
2026-09-29 ran 91 cycles and sent 0. The current session `b7b5981048e5` was
still in **cycle 1 after 107 minutes** of US hours, with no `intended_book.json`
yet; the heartbeat was fresh and the verdict was ALIVE. This is the "scoreboard
over a dead ledger is green forever" pattern. ALIVE should require that a plan
was written in the last N minutes, and should state the orders sent today.

### F7 — MEDIUM. Two sessions can start, and the broker lease is not taken

- `sim_session.start` is check-then-write. It writes `state: RUNNING, pid: None`
  before spawning, and `status()` reads RUNNING with a dead or None pid as
  **UNCLEAN**. A second `start()` (owner vs Telegram/button) that lands in that
  window proceeds. Task Scheduler's `MultipleInstances IgnoreNew` protects only
  owner vs owner.
- `start()`'s own refusal text says "One session owns the GPU and the **broker
  lease**". `scripts/sim_run.py` never calls `pc_broker.open_lease`. Only
  `live_market_loop` does. Two order writers on PC-PAPER are therefore not
  excluded by anything.
- `AegisIIF1NightLauncher` does not start sims (confirmed). No race there.

**Fix:** use an O_EXCL lock file around start, and have `sim_run` take the
lease when `mode == paper_profit`.

### F8 — LOW. ET and calendar

The ET conversion uses `zoneinfo("America/New_York")`, which is correct across
2026-11-01 (a Sunday; Monday 09:00 ET is 22:00 HKT). The Windows trigger is
every 30 min, so DST cannot misfire it. However: (a) **no test crosses the DST
boundary**, and one fixed EST date would pin it; (b) early-close days (the day
after Thanksgiving, Dec 24) keep the 15:30 last start and a 17:00 target
derived from a 16:00 close, so a start after 13:00 ET trades nothing;
(c) `is_session_day` falls back to "weekdays" when `exchange_calendars` is
absent, which would start sessions on holidays; (d) after a crash (UNCLEAN) the
owner starts a **new** session and does not resume the checkpoint.

### F9 — LOW. Scaled views: honest, but read by no one

At $10,000, 3 of 10 held names can be bought in whole shares. **AAPL, AMZN,
GOOGL, JAZZ, META, NVDA and TSM cannot**, and this is printed by name with the
arithmetic. Executable gross is 5.31% vs 20.22% target, a tracking gap of
14.90%. At $40,000 all 10 are executable (gross 17.92% vs 20.22%). Contract
funded rows: IMKTA cannot be bought at $10k. **No executor path reads
`scaled_views`.** A repo-wide grep finds only `decision_contract.py`,
`sim_run.py` and the test, and the order path uses `targets`/`plans`. So the
scaled views cannot cause an order. Nothing displays them either, so the owner
sees the $40k view only by opening JSON.

### F10 — Tests (informational, plus two smells)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest
  backend/tests/test_pc_mandate_and_sim_owner.py
  backend/tests/test_contract_mandate_and_candidates.py
  backend/tests/test_u_plan_probe.py backend/tests/test_night_launcher.py -q
90 passed in 14.63s
```

- `test_the_worst_case_table_is_on_the_contract_in_dollars_and_sigma` asserts
  `verdict == "PASS"` **on the shipped config**. This test encodes "the stale
  sigma passes". Whoever fixes F1 turns it red and is pushed toward keeping the
  stale constant. Derive the expectation from the config, or assert the
  arithmetic only.
- `test_the_contract_capital_is_the_broker_equity` asserts
  `broker_equity_source == "fixture"`, which only checks that the mock passed
  through. Every owner test injects `status`, `start`, `mandate` and
  `broker_read`. No test covers a failed live read plus a 3-day-old file (F5),
  a different account number (F5), or a concurrent start (F7).
- The literal `40000` is gone from the sizing code. It remains only in
  docstrings (`decision_contract.py` 563, 1109, 2238), and the AST test
  correctly ignores those. It survives **in data**, via the IPS (F2).

### Funnel refresh (axis 4): mostly fine

- `generated_at` moved from 2026-09-24T02:48 to 2026-10-06T15:51. The archive
  copy exists as `funnel_history/funnel_2026-10-06.json` but is untracked
  (F4). It is date-named, so a second refresh the same day overwrites it
  (memory: "a date-named receipt a second run can overwrite"). This predates
  C2 and is worth a run-id suffix.
- The `u_funnel` gate is still age-based (`IC.funnel_staleness`), at most once
  per day folder. Correct.
- The contract's candidate line now reads "25 → 25 scored → **2 eligible** for
  the ROI ranking (= n_considered); excluded: 19 ranking score ≤ 0, 4
  NO_EVIDENCE", at 0.0 d old. It no longer suggests a stale file, and the
  bottleneck is now visible as eligibility rather than age. Good.

---

## Axis 7 — the investor's question: what will this account do this week?

Almost nothing. That is not what "manage a million dollars" means.

- **EXPLOIT:** refused every cycle while the ranker's top-20 net relative
  return is negative (−0.93% today).
- **PROBE:** the same ten names at 2% each (NVDA, INCY, AAPL, SNDR, META, AVPT,
  AMZN, GOOGL, JAZZ, TSM), unchanged since 2026-09-28. Five of them are
  mega-caps, which the strategic invariants call *sensors, not the trade*.
- **Contract:** 2 of 25 candidates eligible, and one funded row (IMKTA,
  0.25%).
- **Cash:** ~80%, earning nothing on a paper account.

So the week's P&L is ~20% × (ten-name basket) and ~0 on $800k. Against SPY
that is a guaranteed tracking deficit in any up week, which is the "beta
without alpha" result already seen on 09-22, only smaller. The owner asked for
a $1M book that is *managed*. What exists is a $200k probe with $800k parked.

**The next lever is not another gate. It is the benchmark core.** The contract
already claims 99.75% benchmark core. Make the account match it: hold
`1 − active` in SPY (or the declared benchmark) on PC-PAPER, and grade every
active sleeve as **excess over that core**. This does three things at once:
the account stops losing to the market by construction, F2's contract-vs-broker
disagreement closes, and the worst case becomes *honest*. SPY's ~1.2% daily
sigma on the 80% core, plus real per-name sigma on the active 20%, gives a
3-sigma loss near 6–7%, a real PASS rather than a stale-constant PASS. After
that, the lever is to widen eligibility (2 of 25) rather than to loosen any
cap.

---

## Three things I would have done instead

1. **Price the worst case from the names, not a constant.** Use per-name
   60-session sigma for the EXPLOIT ranker's top-N and the PROBE book, report
   max(that book, universe p90 sigma × gross), and re-check every cycle inside
   `u_plan` as an order block. The fleet manager already has the sigma
   machinery and GTC k-sigma stops with a never-loosen rule. The PC path has
   none, and "no stop order exists" is not acceptable for a $1M mandate
   whose largest admissible sleeve is small-cap.
2. **Reconcile positions, not capital.** Compare the contract's resolved book
   with the broker's positions and cash, by sleeve, every day. Capital
   = broker equity is a definition, and it deserves one line. The book
   disagreement deserves the red.
3. **Build the benchmark core first.** Before scheduling an owner that starts
   sessions which then place zero orders, build the leg that makes the $800k
   do what the contract already says it does. The owner then has something to
   run that changes the result line.

## Score: 61 / 100

| | |
|---|---|
| Capital derived from the broker, stamp-ordered, age-gated | +, but self-referential (F2) |
| Owner: idempotent, one row per firing, pause honoured, operator stop respected | + |
| Worst-case gate | declared and printed, but **wrong sigma** (F1); entry-only (F3) |
| Scaled views | correct arithmetic, non-executable names named, cannot reach an order (F9) |
| Tests | 90/90; one test pins the stale PASS; mocks pass through (F10) |
| Receipts | not committed; absolute paths (F4) |
| Result | none: the account does what it did before this chunk |
