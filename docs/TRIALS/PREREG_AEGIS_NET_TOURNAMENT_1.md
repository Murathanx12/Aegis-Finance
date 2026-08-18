# PREREG — AEGIS-NET-TOURNAMENT-1

SIGNED-BY: (unsigned)

**Status: DRAFT awaiting Murat's signature. The harness
(`backend/services/net_tournament.py`) refuses to touch the registered panel
until the SIGNED-BY line names a human — the gate is in code, not here.**

Registered basis: `backend/data/optimus/net_panel/net_panel_v1.parquet`
(sha256 of source in `net_panel_v1.meta.json`; 24,911 rows × 145 monthly
date blocks × ≤179 names, h=20, universe = the TAQ calibration 182).

## Why this, and why it is a SCREEN and not an alpha claim

The question is architectural: does any nonlinear model family extract more
than a regularized linear map from the features this machine actually has?
The 2013–2026 calendar this panel spans has been read by many prior
experiments; under §61 nothing evaluated on it can be described as
independent confirmation. **Every claim this trial can produce is capped at
ADAPTIVE_HISTORICAL_VALIDATION** — it selects a shape and prices the next
dollar of effort (scale vs shape); forward confirmation belongs to accruing
data under its own future registration.

## The corpse, confronted by name (canon: or the thing is not built)

**G5 — three registered receipts: a learned conditional SHAPE adds nothing,
even given an oracle scale.** What this asks that G5's tests did not: every
G5 receipt was graded against a *directional* target, where this engine
measures AUC 0.497–0.509. The tournament's heads are cross-sectional rank,
magnitude, realised vol, drawdown and competing-risk barriers — none of
which reduces to sign. If nonlinearity adds nothing HERE either, that is a
fourth receipt and the linear verdict below is adopted, not argued with.

## Hypothesis (honest prior: LOW)

At least one of {LightGBM, MLP-1, MLP-2, MLP-3} beats `linear_ridge` on the
primary head by more than its own measured MDE. Prior is LOW: Gu–Kelly–Xiu
found shallow ≥ deep in this signal regime, and our own G5 receipts point
the same way. **The second declared outcome is a finding, verbatim: "the
shape is linear; spend the next dollar on scale, coverage and cost."**

## Arms — FROZEN (hyperparameters are part of this registration)

Exactly `net_tournament.build_arm`: ridge(α=1.0) · LightGBM(300 trees,
lr 0.05, 31 leaves, min_child 50, deterministic single-thread) ·
MLP(32) · MLP(32,16) · MLP(32,16,8), each behind median-impute + standardize,
seed 20260819. No arm may be added, tuned, or re-seeded after signature.

## Features — the declared ablation ladder and its measured floor

Family 1 `numeric_price` (7 columns, the only family with a PIT store on
this machine — `net_panel_v1_coverage.json` declares options, expectations,
event/LLM and semantic ABSENT). The full ladder
(numeric → +options → +expectations → +event/LLM → +semantic) is registered
as the *intended* sequence; rungs run only as their PIT stores materialize,
each as an amendment naming this document as parent. **A linear win on
family 1 alone does not license "nonlinearity is dead" — it licenses "not
detectable in numeric-price features," and the report must say which.**

## Primary metric — the ONE deciding number

Head: `cs_rank` (cross-sectional rank of 20-day forward return).
Deciding number: the **paired per-row squared-loss difference** of each
complex arm against `linear_ridge`, pooled over all walk-forward test
periods, with date-block bootstrap (block = 20 trading days,
`block_bootstrap_paired`; the §58 unit is the DATE BLOCK, n_effective ≈
145 monthly blocks / block overlap). Negative mean = the arm beats linear.

Decision rule, committed before any number exists:
- An arm WINS iff mean < 0 AND |mean| ≥ its own bootstrap MDE(80%) AND it
  survives **Holm at FWER 0.05 across the m = 4 declared complex arms**.
- Anything else — including "close" — adopts the linear verdict.
- Rank IC per arm, the other heads (magnitude, realised vol, drawdown,
  barriers), and all ablations are **reported, never deciding** (SCREEN,
  BH-FDR at 0.10, m = tests actually run, counted by the daemon).

## Power declaration (§64, run forwards — before any outcome is read)

At a declared per-month IC dispersion σ≈0.10 and 145 monthly blocks, the
80%-power MDE on a ΔIC-shaped contrast is ≈ 2.8·σ/√145 ≈ **0.023**. The
economically meaningful bar declared here is **ΔIC 0.01** (what plausibly
survives measured TAQ costs at monthly turnover). 0.023 > 0.01, therefore:
**at the economic bar this panel's primary contrast is NOT_ANSWERABLE_AT_N
unless the measured dispersion comes in materially under the declared σ —
recorded NOW, at registration, not discovered after** (Order 19 §2: the bar
is never shrunk to rescue a cell). The loss-contrast MDE is measured by its
own bootstrap at run time; the trial reports "which effects were resolvable"
alongside every verdict.

## Cells recorded NOT_ANSWERABLE at registration

- `barrier_up75_down30` at h=20: 0.6% event rate (~150 events); the
  cause-specific fit refuses below its 30-event-per-fold floor.
- `barrier_up40_down20` at h=20: 2.7% — pooled fit only; per-fold thin.
- The competing-risk comparison (cause-specific Cox vs multinomial) is
  therefore registered on `barrier_up20_down10` ONLY at this horizon.

## Costs

Any economically-flavoured sentence uses per-name **measured TAQ one-way
costs** (`taq_cost_calibration.json`, `retired: true` rows) with the
declared 1–5bp band for the 3 unretired names, charged on decile long-short
turnover at the monthly rebalance. Statistical verdicts are gross;
economic sentences are net; the report labels which is which.

## What this trial may NOT do

- Change objective, head, arm, or fold structure after any score exists.
- Promote a non-declared cell that happens to clear (§37 in equivalence
  clothing).
- Describe any result as validation, edge, or confirmation — the §61 cap
  is part of the registration.
- Feed any output into a lane, a signal, or user-facing surface.
- Run before the SIGNED-BY line names a human (enforced by
  `assert_signed`, tested).

## Contamination clause

The panel's prices were assembled by LEAKAGE-PROBE-1 and the calendar is
spent for confirmation purposes (§60/§61). If any head's outcome influences
which future data systems get built (it is designed to), those systems'
trials must name this document as `hypothesis_source`.

— drafted by grind session 2026-08-18 night, awaiting signature
