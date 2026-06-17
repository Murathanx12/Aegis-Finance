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

1. ✅ **DONE 2026-06-17.** Exit-overlay decision core built + tested:
   `services/portfolio_intelligence/exit_overlay.py` — `evaluate_exit_overlay`
   (per-position ATR Chandelier hold/exit, reusing `exit_engine.simulate_trailing_exit`)
   + `vol_capped_weights` (vol-target sizing cap, renormalised). Pure, arms
   nothing. Tests: `test_exit_overlay.py` (6 — monotonic winner held, rollover
   stopped near peak, entry-date alignment, vol cap trims the violent name).
2. ✅ **DONE 2026-06-17.** `backend/data/conservative_atr_lanes.yaml` — single
   `conservative-atr` lane with its OWN hash (`db.get_conservative_atr_config_hash`,
   verified distinct from the reference AND book hashes), mandate **byte-identical
   to `conservative`** (target_equity_pct 0.40 — the prior "60" in this doc was a
   typo; the actual conservative mandate is 40/50/10) + `exit_overlay: atr`. Exit
   params deliberately NOT duplicated — frozen at `config["exit_engine"]` defaults
   so there is no per-lane knob to tune. `paper_portfolios.yaml` untouched.
3. ✅ **DONE 2026-06-17.** `services/portfolio_intelligence/exit_lane.py`:
   `seed_conservative_atr_lane` (mandate weights, ATR-hash stamp, registry-on-seed,
   idempotent, fail-loud) + `run_exit_overlay_check` wired into `_daily_check`
   (NO-OP `not_seeded` until the flag seeds it, mirroring Plan 3): recompute the
   mandate target → `evaluate_exit_overlay` rotates stopped names to cash →
   `vol_capped_weights` on the equity sleeve → rebalance on cadence/drift OR
   immediately on a stop. Also wired: hourly MTM (`mark_all_conservative_atr_lanes`),
   `nav_freshness`, `/api/pi/track-record`, and the registry N_eff enumeration —
   each skips the lane until seeded. `main.py` env-gated seed hook reads
   `AEGIS_SEED_CONSERVATIVE_ATR=1`. Tests: `test_exit_lane.py` (9) — hash
   isolation, no-op-until-seeded, idempotent seed, registry-on-seed with the ATR
   hash, frozen `conservative` control never created/touched, and the exit overlay
   firing end-to-end (a rolled-over name is stopped → rotated to cash).
4. ⬜ **Attended (Murat).** Set `AEGIS_SEED_CONSERVATIVE_ATR=1` → deploy → confirm
   `/api/pi/registry` shows TRIAL-EXIT registered + the lane appears, and
   `/api/health/full` + `/api/pi/track-record` show it fresh → unset the flag →
   deploy. (The earlier 2026-06-17 seed attempt was a no-op because items 2–3 above
   were not yet built — the flag had nothing to trigger; now it does.)
