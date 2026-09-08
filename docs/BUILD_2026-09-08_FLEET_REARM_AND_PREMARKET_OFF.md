# BUILD — 2026-09-07/08 — the fleet re-arm, the premarket switch, and why the books were empty

**Lead session (Opus 5).** Seven builder agents ran in parallel on their own
lanes; this document covers only the lead's lane. Their build docs are the
`BUILD_2026-09-07b_*.md` files.

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs market | UNCHANGED — nothing in this lane touched a selector |
| best forward paper strategy | **none: all six paper books held ZERO positions, and had since 2026-09-04** |
| independent selector count | UNCHANGED |
| farm candidates tested / promoted | 0 / 0 |
| **new actionable finding** | **the fleet was disarmed four different ways at once, and the stop width made every declared minimum hold unreachable** |
| external execution drag | not re-measured |
| LLM spend | **$0.00.** DeepSeek balance untouched at ~$9.28 |

**RESULT IMPROVEMENT: NONE.** No edge was found, tested or promoted. What this
lane did was make the books capable of expressing an idea at all.

## 1. WHY SIX ACCOUNTS WERE EMPTY

Not one cause. Four, each independently sufficient, and the first three were
invisible from the repository because they lived in the deployed environment.

1. **Every one of the six deployed loops carried `--manage-only`.**
   `alpha/fleet.py` declares it for hack1 and hack2 only; the live
   `AAT_LOOP_ARGS` on all six services had it. A book with that flag may not
   open a position. The mandate table and the running fleet had drifted
   completely apart, and `loop_args()` only reconciles them **at deploy time**.
2. **`AAT_LOOP_EXPIRY = 2026-09-04` on all six** — the hackathon date, days past.
3. **`AAT_MANDATE_END_UTC` was unset on all six**, so the code fell back to the
   2026-09-04 contest deadline. That fires `deadline_liquidation_due` at 10:45 ET
   every session and makes the entry pass refuse outright. The venue's own order
   history shows exactly this: hack3, hack4 and hack6 were liquidated in a burst
   at 14:46-14:47 UTC on 2026-09-04, and nothing has entered on any account since.
4. **`scripts/run_pass.py` crashed on every invocation that did not pass
   `--role`** — which is how `scripts/agent_loop.py` calls it. A function-local
   `import os` inside `main()` (added 2026-08-26, f741211, closing audit defect 6)
   made `os` a local for the whole function body while only ASSIGNING it behind
   `if args.role:`. Every role-less run died with
   `UnboundLocalError: cannot access local variable 'os'`. Fixed, with the
   reason written at the site so it is not re-added.

The deployed build commits were `cabdb06+dirty` and `9be7f71+dirty`, both older
than HEAD, so none of the 2026-09-05 contract work was running either.

## 2. THE STOP WAS INSIDE THE NOISE, SO THE MINIMUM HOLD COULD NEVER BIND

`exits.evaluate` has honoured `min_normal_hold_sessions` since 2026-09-05 and the
books still churned, because `HARD_RISK_LIMIT` is always legal and is checked
**above** the hold. The widths were profile constants with no relationship to the
volatility of the names being bought.

Measured on the 2026-09-07 seal's own holdings, over every entry point since
2024-01 (`docs/RECEIPT_2026-09-07_STOP_WIDTH_VS_HOLD.json`):

| book | stop | stop / 1-day sd | P(stopped before its own hold) | P(survives horizon) |
|---|---|---|---|---|
| hack6 | 3% | **0.98** | **56.3%** | 30.2% |
| hack3 | 8% | 2.35 | 31.0% | 53.8% |

hack6's stop sat at one daily standard deviation of the names it had just bought.
A 21-session thesis whose exit rule terminates 56% of positions before session 10
is a one-week strategy wearing a contract. `alpha/engine/equity.py` already says
"a stop inside the noise is a fee, not a stop" in its own comment, and then kept
3% for the aggressive profile.

## 3. WHAT CHANGED

`contract.HORIZON_REMAP` gives every book declared terms that outrank both the
profile width and the generic tracker/event shapes:

| book | horizon / min hold | stop | n x notional | gross | worst case |
|---|---|---|---|---|---|
| hack1 | 126 / 21 | 35%* | 1 x 95% | 95% | -33.25%* |
| hack2 | 5 / **2** | 8% | 8 x 6% | 48% | -3.84% |
| hack3 | 63 / 21 | 12% | 10 x 8.3% | 83% | -9.96% |
| hack4 | 126 / 42 | 15% | 5 x 8% | 40% | -6.00% |
| hack5 | 21 / **2** | 50% | 6 x 3% | 18% | -9.00% (true bound -18%) |
| hack6 | 42 / 21 | 10% | 15 x 6% | 90% | -9.00% |

\* hack1's "stop" is a -35% SPY drawdown: an emergency, not a trading rule. A
control that stops out is no longer a control.

**No book still has a zero minimum hold** — that is what "buy and sold" means —
and no book is levered: every gross is under 100% of its own equity.

**What it costs, said plainly.** hack6's worst case rises from -2.70% to -9.00%
and hack3's from -6.64% to -9.96%. My first draft cut the notionals to hold both
near their old bounds, and that draft was wrong twice over: the seal sizes these
books (not `alpha/contract.py`), so the smaller numbers described an intention
nothing would execute; and a book that can hold but has stopped using its money
is not what was asked for. `worst_case(book, seal=...)` now DERIVES the numbers
from the morning's sealed book and stamps `sizing_source`, so the declared figure
and the executed one cannot drift apart the way they did on 2026-08-28 (prose
-9%, configuration -24%).

Also: **a book's declared floor now outranks a brain's forecast.** For books
outside `TRACKER_BOOKS`, `runner.contract_for` overrides the horizon with the
forecast's `horizon_days`; a one-session forecast would have produced hold 2 >
horizon 1, which `validate` refuses outright. The horizon is lifted to the floor
rather than the floor being quietly cut to fit.

**hack2 un-manage-only'd**, by the condition its own caveat set: it was to stay
manage-only "until its own contract is frozen", and every clause of the stated
objection (zero hold, +2.5% target, 3% stop) is now answered. A gate whose
condition has been met and which stays shut is not caution, it is an unread gate.

## 4. PREMARKET PASSES ARE OFF

Murat: *"we dont run premarket runs anymore, the more project improves the more
things we lose and gets missed."*

`agent_loop.PREMARKET_PASSES_ENABLED = False` gates **both** pre-open passes
through one decision — `scripts.premarket_digest` (the loop's largest DeepSeek
consumer, roughly 6 calls per role per day) and `scripts.open_auction` (the
entry-timing tournament's pre-open arm). `--premarket` re-enables it for one run,
and each skip is **logged**, because an absence that says nothing reads exactly
like a pass that broke.

A constant and a flag, not an env var: `AAT_MANAGE_ONLY=1` sat in the runbook for
days meaning nothing because no code read it. `tests_smoke_premarket_off.py`
asserts the scheduler's behaviour, counts the gated call sites, and fails if a
third pre-open pass is ever added without the gate.

Turning the auction off does not stop hack4/hack6 trading — the ordinary
in-session pass still fills them. It stops them entering BEFORE the open, which
is the window nothing here can verify because the venue is shut.

## 5. TESTS

`python run_tests.py`: **84 suites, 3868 checks, ALL PASS** (from 83 / 3813).
New: `tests_smoke_premarket_off.py` (8 checks), `tests_smoke_horizon_remap.py`
(45 checks). Updated pins, each moved to a declared value rather than merely
made to pass: `tests_smoke_contract.py` 44 -> 55, `tests_smoke_band_mode.py`
61 -> 63, `tests_smoke_labor_exits_adversary.py` -> 19.

That last suite's C2-0 section had DOCUMENTED the hack2 defect; it now asserts
the fix. Its assertion B was measuring `equity.stop_fraction(profile)` while
`exits.evaluate` charges the contract's width, so it was reporting its own
arithmetic as a violation — it now reads the width the exit rule actually uses.

## 6. CLAIMS FOR THE REVIEWER TO ATTACK

1. The four causes in section 1 are each independently sufficient. Attack: were
   all six services really `--manage-only`, or did I misread a variable dump?
2. hack6's stop was 0.98 daily sd. Attack: that sd is a trailing 120-day pstdev
   on closes; a different window or an intraday measure moves it.
3. P(stop before hold) is a **lower** bound — closes only, no intraday touch.
4. The 2024-01 to now sample is one regime and bounds nothing about a crisis.
5. hack4's row is DECLARED, not measured: its sealed book was empty
   (`requires_catalyst=true`, `rank_distinct_values=0`).
6. The `os` shadowing broke every role-less run — but the loops have been up for
   days, so either the entry pass never ran during market hours since 08-26, or
   something else passed `--role`. I did not find that something, and the
   Railway logs I read did not settle it.
7. Nothing here demonstrates an edge. It demonstrates a book that can hold.

## 7. WHAT DID NOT WORK / IS NOT DONE

- **The books are still empty as of writing.** The re-arm requires redeploying
  all six Railway services; a deploy tars the working directory and seven agents
  were mid-edit, so it is gated on their completion and one more green suite.
- **hack1 / SPY.** I asked Murat whether hack1 should hold SPY as the control and
  he chose yes — but I had the premise wrong. The SPY benchmark is a SEPARATE
  seventh account (`market`, `PA3I7VTCC0BM`, contract `PASSIVE_BETA_v1`: "one
  purchase at the next regular open, exit never, no stop"), and the local ledger
  shows it seeded with SPY on 2026-08-27. Its keys are not in this `.env`, so I
  could not read the account to confirm — **CANNOT DETERMINE from here.** Putting
  SPY into hack1 as well would duplicate the benchmark and create exactly the
  cross-book overlap `alpha/crossbook.py` exists to flag, so I have NOT done it
  pending his call.
- The `market` account's keys should be added to `.env` so the benchmark is
  readable by `scripts.fleet --check-all` and by `crossbook`.
- The `market` arm is a seventh account beyond the six in `alpha/fleet.py`. The
  roadmap's F table treats hack1 as the SPY control; the code does not. Those two
  should be reconciled in the roadmap, not in a session's head.

---

# ADDENDUM — 2026-09-08, after the re-arm

## 8. A FIFTH CAUSE, FOUND BY RUNNING THE REAL ENTRY PASS

The four causes in §1 were necessary and not sufficient. A DRY `run_pass` against
the 2026-09-08 seal — real sizer, real admission gates, real risk guards —
submitted **four of hack3's ten** names and refused six:

```
ADMISSION refused TNXP long_shares x572: DRIVER: after this order the book
would carry 41% of equity in notional on the single driver 'UNCLASSIFIED'
```

`drivers.declared_map()` reads a human-stated theme seed written 2026-08-28
holding **70 symbols** (uranium, quantum, fuel-cell, solar). The tracker books
have since moved to a **~774-name screened universe** sharing almost nothing with
it: 10 of hack3's 10 and 14 of hack6's 15 resolved to `UNCLASSIFIED`, which by
design is ONE shared bucket, so the 40%-of-gross cap bound after ~4 names on
every tracker book, permanently.

The conservative default is right — *not knowing whether four names are
independent is not evidence that they are* — but the sealed book already had the
answer: `prediction_book` stamps a `sector` on every holding and enforces
`max_names_per_sector = 3` and `max_sector_share = 0.30` at selection. The sealed
sector is now a **third declared source**, after the theme seed and before
UNCLASSIFIED, obeying this module's own rule that declared is the floor and
measurement may only MERGE. A name nothing names is still UNCLASSIFIED.

**Measured after: hack3 10/10 and hack6 15/15 admitted, zero refusals**, largest
driver 3 names. Per-name risk 0.30–0.78% of equity.

## 9. THE PROFILE TABLE WAS THE ONLY LEVER THAT REACHED AN ALREADY-SEALED BOOK

A sealed contract carries `stop_frac: null` and a `profile`, so it takes its width
from `equity.STOP_FRACTION_BY_PROFILE`. That is why the per-book widths in §3
alone would NOT have reached today's positions. The table also failed its own
written standard ("~1.3 daily sigma"): `aggressive` was 0.03 on names whose mean
daily sd is 3.05%. So aggressive 0.03→0.10, basket 0.08→0.12, maximum 0.06→0.15.

**And `tests_smoke_monday` immediately caught the trap.** `maximum` had a gross
cap of **1.50 — leverage** — so a 15% stop put **22.50%** of equity structurally
at risk: the 2026-08-28 −9%→−24% mistake to two significant figures. Cap cut to
0.60, restoring the 9.00% bound exactly and costing hack4 nothing (its sealed
target is 50% gross). The suite now checks `gross_cap × stop` for **every**
profile against a 12.5% ceiling that binds, rather than checking basket alone.
**No profile is levered.**

## 10. TWO MEASUREMENTS TAKEN BECAUSE THEY WERE CHEAP AND NOBODY HAD

- **`RECEIPT_2026-09-08_LIVE_TRANSFER.json`** — sealed weight → submitted weight
  on hack3/hack6 is ratio **1.00, sd 0.00** (gross 83.0→82.9%, 90.0→89.7%). The
  sizer loses nothing, so the four-stage leak for these books is in SELECTION or
  EXIT, not construction. Consistent with §2.
- **`RECEIPT_2026-09-08_FLEET_INDEPENDENCE.json`** — hack3 and hack6 share only
  **3 of 22** names (Jaccard 0.14) yet their EW returns correlate at **ρ 0.719**
  (52% shared variance), and both load MORE on **IWM** (0.752, 0.766) than on SPY
  (0.605, 0.675) over 380 sessions. The k=10 vs k=15 breadth test carries far less
  independent information than "two accounts" suggests, and excess on these books
  must be measured against IWM. Six equity curves are fewer than six pieces of
  evidence.

## 11. WHAT I GOT WRONG TODAY

**I destroyed the published 2026-09-08 seal.** `seal-authority` has **no Railway
volume**, so redeploying it wiped its state and forced a ~100-minute rebuild of
3,110 names. No operational damage: both tracker loops had already synced the
seal (sha `f20929777f77fa55`) into their own volumes, and `sync_once`
short-circuits on a valid local copy, so they never lost it. The byte-identical
pre-redeploy copy is committed as `state/predictions/2026-09-08.pre_redeploy_0507.json`.
The seal republished at 06:35 UTC. **Do not redeploy that service casually.**

## 12. OPEN, AND FOR THE NEXT SESSION

- **The loops hold the OLD seal and will not re-fetch.** `sync_once` returns early
  on a valid local file, so today's books run horizon 21 / hold 10 with the
  corrected profile widths (12% / 10%). The republished seal carries the better
  terms (hack3 63/21 `stop_frac` 0.12, hack6 42/21 `stop_frac` 0.10) and reaches
  the fleet **tomorrow**. A seal fix is never same-day.
- **The authority is one commit behind (9519bfd, not 382a6c4)**, so the seal's
  informational `stop_fraction` (0.08 / 0.03) disagrees with its operative
  `stop_frac` (0.12 / 0.10), and the seal's `risk_budget_usd` is computed from the
  stale one. `risk_budget_usd` is validated but never ENFORCED at trade time, so
  this is a reporting defect, not a risk-control defect. **Redeploy the authority
  AFTER an open, never in the last hours before one.**
- hack1 still holds no SPY — see §7; the premise of that question was mine and
  wrong, and the benchmark is a seventh account.
- hack4's seal is still EMPTY (`requires_catalyst=true`, `rank_distinct_values=0`).

## 13. VERIFYING THE FILL (run this after 09:30 ET)

```
cd ~/aegis-alpha-terminal
python -m scripts.accounts                       # positions per book
railway logs --service aat-loop-hack3 | tail -40 # the entry pass
python -m scripts.fleet --overlap                # cross-book concentration
```
Expect hack3 ≈ 10 names and hack6 ≈ 15. hack2 and hack5 depend on their own
brains finding something; hack4 will be empty until its catalyst filter is
revisited. **hack1 is manage-only by declaration and should stay flat.**
