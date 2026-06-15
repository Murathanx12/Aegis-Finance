# TRIAL-EXIT — ATR trailing stops + vol-target sizing (pre-registered)

> Drafted 2026-06-15 (Priority 4). This is the **pre-registration**; it predates
> any forward data. The trial is **NOT yet live** — it requires (a) wiring the
> `exit_engine` overlay into the reference rebalance path, (b) a new lane config,
> and (c) attended seeding (new inception). This file is the commitment that the
> decision rule was fixed before the data.

## Why a NEW lane, not a retrofit (load-bearing guardrail)

The exit-discipline win from the 2026-06-15 backtest (maxDD −30.6% vs SPY
−33.7%; consistent across runs) is real and worth measuring forward. But the
canon is explicit: **never change the strategy of an in-flight tracked lane.**
Arming ATR exits on the existing `conservative` lane would alter a live
TRIAL-class record mid-stream (same defect class as arming the crash overlay on
TRIAL-001 lanes — see `postmortems/2026-06-14-crash-overlay-dark.md`).

Therefore the trial runs as a **new lane `conservative-atr`** with a mandate
**identical** to `conservative` (same target equity %, universe, cadence, cost
model) plus the exit overlay. The existing `conservative` lane is the **frozen
control**. This is exactly the "managed vs unmanaged" comparison Murat asked for,
done without corrupting either record.

## Hypothesis

Adding an ATR Chandelier trailing stop (k·ATR, ratchets up never down) + a
volatility-target position cap to the conservative mandate **improves
risk-adjusted return** vs the unmanaged control, primarily by reducing drawdown,
without materially hurting net Sharpe.

*Honest prior (from the backtest):* the exit overlay's measured effect is
**drawdown reduction at a small return cost** — NOT a Sharpe increase. So the
realistic expectation is *better Calmar / shallower maxDD, ~flat-to-slightly-
lower Sharpe.* Adoption must reflect that the mechanism is downside control.

## Decision rule

- **Primary metric (deciding):** full-window **net Sharpe** (after tx costs)
  from daily `paper_nav` returns of `conservative-atr` vs `conservative`, from a
  shared new inception.
- **Co-primary (deciding, because the mechanism is drawdown):** full-window
  **max drawdown**. Adoption requires the managed lane's maxDD be **shallower**
  (the overlay must do what it claims).
- **Adopt-confirmed** iff, at month ≥12: net Sharpe non-inferior (within −0.10)
  **AND** maxDD shallower by ≥ 3 absolute points. **Reject** iff net Sharpe
  trails by ≥ 0.20 **or** maxDD is not shallower (the overlay isn't earning its
  turnover).
- **Minimum window:** 12 months; evaluated quarterly thereafter. No decision
  before month 12.
- **Secondary (reported, never deciding):** Calmar, annualized vol, turnover,
  total transaction cost, tracking error vs control, number of stop-outs.
- **Multiple-testing:** recorded in the registry; DSR/PBO deflated against the
  cumulative trial count (will be ≥5 after book-lane seeding). The exit params
  (`atr_stop_multiple`, `vol_target_annual`) are **frozen at config defaults**
  for this trial — no per-lane tuning (tuning = the overfitting the backtest
  already flagged at PBO 0.66).
- **Contamination / crash override:** same clauses as TRIAL-001 (a ≥20% SPY
  drawdown defers decisions until ≥6 months past the trough; data defects extend
  the window).

## What this rule may NOT do

No metric substitution after the fact; no window cherry-picking; no tuning the
ATR multiple to the forward data; no early adoption on a calm-market Sharpe bump.

## Implementation checklist (before this goes live — attended)

1. Wire `exit_engine` into `reference_engine` daily check for lanes flagged
   `exit_overlay: atr` (apply trailing-stop sells + vol-target cap). Tested.
2. Add `conservative-atr` to a config path that does **not** perturb
   `paper_portfolios.yaml`'s hash (mirror the book-lane separation pattern) so
   TRIAL-001's segment stays clean.
3. Attended seed (new inception) + register TRIAL-EXIT in `rule_experiments`.
4. Confirm `/api/health/full` shows both lanes fresh.
