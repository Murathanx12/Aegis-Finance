# PREREG — GENERATION-2 LANES (launch window 2026-09-08) — DRAFT

**Status: DRAFT for Murat's signature before the window. Lanes ship per
`seed-a-lane` (own YAML, own hash, own inception, env-gated, Murat
flips). §64 basis: `lane_factory/g2_sweep_2026-08-19.json` (SIMULATION,
SCREEN — quoted for power, never as a verdict).**

## Pair A — risk-sized (transports the NET tournament risk result)

- `g2_equal_weight_control`: mom_12_1 top-50 of the PIT-eligible
  universe, equal weight, monthly rebalance, 3bp declared cost basis.
- `g2_inverse_vol`: identical except weights ∝ 1/vol_63. (The frozen
  ridge risk head is the v2 upgrade; v1 uses realized vol so the lane
  rule is fully deterministic and auditable.)
- **Primary (deciding, readable):** realized-vol difference at the
  6-month read — §59's fast clock. Sim basis: 0.309 vs 0.284 ann vol
  (trim books) and maxDD −0.636 vs −0.478. Bar: the inverse-vol lane's
  realized vol must be lower with the 90% CI excluding zero.
- **Secondary (slow clock, declared now):** net return difference. Sim
  screen says +5.2%/yr with monthly MDE 0.0046 at n=125 months — a
  2-lane forward pair reaches that only on a MULTI-YEAR clock; no
  return claim before its §64 says answerable.

## Pair B — winner-hold (transports CONVEXITY-PRESERVATION-1, honestly)

- `g2_rebalance_control`: as Pair A control.
- `g2_winner_exempt`: identical except a position up ≥40% since entry
  is exempt from rebalance SELLS for 60 trading days after crossing
  (renewable exemption, reference = original entry — v1 semantics as
  simulated; amending the reference rule is a pre-launch decision, not
  a post-launch drift).
- **DECLARED UP FRONT: the forward pair CANNOT decide the return
  question.** Sim screen: +0.8%/yr @equal, −0.9%/yr @inverse-vol, both
  far inside MDE even at 125 simulated months. Book-level rebalance
  trims are gentle; the trial's effect was measured on 25/50/100%
  exits (§60 scope — the dilution is itself a finding, recorded).
- **Primary (deciding, readable):** behavior + risk receipts — the
  exemption must FIRE (sim: 283 crossings), and the exempt book's
  realized vol / maxDD must not be worse than control beyond the
  declared band (sim says they IMPROVE: vol 0.284 vs 0.309, DD −0.587
  vs −0.636 at equal weight). Purpose: operational validation of the
  rule the simulator will keep testing at scale.

## Read discipline

90-day generation reviews per `DECISION_QUARTERLY_LANE_GENERATIONS.md`:
risk/behavior first, return differences printed WITH their MDE.
Bootstrap block for any read derives from the measured autocorrelation
of the paired diff series (formation overlap is 12 months; the monthly
block used in the sim screen is a lower bound — re-derive before the
first deciding read; recorded as an open §58 item).

## May NOT

Backdate anything; edit a running lane; pool sim months with live
months in any deciding statistic (SIMULATION ≠ track record); claim
skill on any public surface (24-month rule per lane).

— drafted 2026-08-19 night from the first factory sweep; awaiting
signature in the 09-08 window
