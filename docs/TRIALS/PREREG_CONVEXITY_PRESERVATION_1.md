# PREREG — CONVEXITY-PRESERVATION-1

SIGNED-BY: (unsigned)

**Status: DRAFT awaiting Murat's signature. The runner
(`scripts/convexity_trial_run.py`) refuses the registered basis until the
SIGNED-BY line names a human — same gate as the NET tournament, same code
(`net_tournament.assert_signed` with this path).**

Registered basis: `backend/data/optimus/convexity/episodes_v2.parquet`
(23,011 episodes × 143 crossing-month date blocks expected — v2 adds the
capture-metric outcome family per P-grind-2026-08-19e, approved 2026-08-19
BEFORE any verdict existed; v1 remains on disk as the pre-amendment
construction). Daemon submission: `CONVEXITY-PRESERVATION-1` in the first
queue, priors declared 2026-08-18 before any outcome was read.

## The question

Do trim/stop rules destroy right-tail terminal wealth versus holding, on
+20/+40/+75/+100 threshold-crossing winners — and if so, which crossings?
This is Murat's own management question ("am I selling my best stocks too
early?") asked at the only place it can be answered honestly: episodes
anchored at crossings, with matched non-winners, costs charged both ways.

## The corpse, confronted by name (canon)

**CANON §15 — the trailing-stop trap.** S15's kill was a stop EVALUATED on
paths selected for having survived the stop — conditioning on the path
being evaluated. Here the stop is an ARM scored on episodes anchored at
threshold crossings detected WITHOUT reference to any arm's behavior; the
selection is the crossing, not the rule. What this asks that §15's corpse
did not: per-dollar terminal wealth of a fixed rule-set applied from the
crossing forward, against hold, on the same paths, with the matched
non-winner control (§16) carried per episode.

## Hypothesis (prior: MODERATE, direction declared)

H1: `hold` beats each trim/stop arm on mean per-episode terminal wealth at
the +40 threshold and above — the right tail pays for the drawdowns.
H0 owes both tests: MDE and equivalence at the economic margin.

## Primary metric — the ONE deciding number

Cell: **`trail_stop_20` vs `hold` at threshold +40**, the classic
protect-your-gains rule at a meaningful winner threshold.
Deciding number: the **paired per-episode terminal-wealth difference**
`tw_trail_stop_20 − tw_hold`, negative = the stop destroys wealth, with
date-block bootstrap over CROSSING MONTHS (§58; the v1 audit measured 143
blocks and a per-block SE of 0.0016 on the trim25 contrast — the executor
receipt of 2026-08-19 is the §64 power check, run before this
registration's signature).

Decision rule, committed before any number exists:
- **STOP_DESTROYS** iff mean < 0 AND |mean| ≥ its bootstrap MDE(80%) AND
  Holm at FWER 0.05 across the m = 5 declared non-hold arms.
- **STOP_NONINFERIOR** iff run-time MDE ≤ the economic margin AND the 90%
  CI is bounded inside ±margin.
- **NOT_ESTABLISHED** otherwise. An underpowered miss licenses nothing.

**Economic margin: 0.005 terminal-wealth fraction over the 60-day window**
(≈3%/yr drag — the smallest management effect worth acting on given the
+3%/yr execution standard). The v1 audit's measured MDE ≈ 0.0045 < 0.005,
so this cell is ANSWERABLE at the declared margin — recorded at
registration, per §64.

## Reported, never deciding (SCREEN, BH-FDR 0.10, m = tests run)

- The full arm × threshold grid of paired terminal-wealth differences.
- The capture family: `mfe_captured_<arm>` distributions, peak giveback,
  days underwater, near-peak-at-end rates per arm.
- The §16 leg: episode `tw_hold` vs `control_tw_hold` per threshold —
  do crossers outrun their matched non-winners at all?
- Right-tail truncation: arm-vs-hold differences within the top decile of
  `tw_hold` (the cell where trimming should hurt most if H1 is real).
- Continuation covariates (pit_* features) interacted with the primary
  difference — hypothesis-generating only.

## Costs

Per-name measured TAQ one-way where retired (`taq_cost_calibration.json`),
the declared band otherwise; v2's builder default (flat 3bp) is superseded
by the lookup at run time and the receipt says which basis each name used.
Conventions caveat: the 2026-08-19 probe showed the effective-inside-quoted
discount is liquid-name-only; costs here use QUOTED-basis numbers, which
is the conservative side for a trial about NOT trading.

## What this trial may NOT do

- Change arm definitions, thresholds, the primary cell, or fold structure
  after any score exists.
- Promote a non-declared cell that happens to clear (§37).
- Quote headline counts as market base rates (large-cap universe
  under-samples +75/+100 by construction — the CRSP extension re-asks).
- Feed any output into a lane or user-facing surface. §61 cap:
  ADAPTIVE_HISTORICAL_VALIDATION.
- Run before the SIGNED-BY line names a human.

## Descendants (registered as designs, not smuggled in later)

- `REENTRY-OPTION-VALUE-1`: exit + systematic re-entry arms. Distinct
  registration naming this document as parent.
- CRSP-universe re-run under UNIVERSE-SURVIVAL-STRESS-1's panel.

— drafted 2026-08-19 day session; the daemon's declared priors predate it
