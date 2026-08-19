# PREREG — CONVEXITY-PRESERVATION-1

SIGNED-BY: Murat

**Status: SIGNED 2026-08-19 (Murat, in-session). Amendment 1 applied
2026-08-19 under the same in-session approval, BEFORE any aggregate
outcome of the registered basis was read — see §Amendment 1 below for
what changed and why. The runner (`scripts/convexity_trial_run.py`)
refuses the registered basis until the SIGNED-BY line names a human —
same gate as the NET tournament, same code
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
date-block bootstrap whose blocks SPAN THE 60-TRADING-DAY OUTCOME OVERLAP
(§58; Amendment 1 — block length derived from the panel's own
crossing-date spacing via `bootstrap_block_dates(dates, OUTCOME_DAYS)`,
measured 84 calendar days ⇒ **n_effective = 22 blocks**, superseding the
crossing-month unit).

**Execution semantics, frozen (Amendment 1):** `trail_stop_20` is a
**daily-CLOSE trailing rule** (alias `close_trail_20`): trailing peak =
max of adjusted closes through day i−1; the position exits AT the close
of the first day i whose close ≤ peak × 0.80, charged one one-way cost.
It is NOT an intraday high/low broker stop. Any verdict sentence must
say "20% trailing exits evaluated on daily closes", never "20% trailing
stops" unqualified.

Decision rule, committed before any number exists:
- **STOP_DESTROYS** iff mean < 0 AND |mean| ≥ its bootstrap MDE(80%) AND
  Holm at FWER 0.05 across the m = 5 declared non-hold arms.
- **STOP_NONINFERIOR** iff run-time MDE ≤ the economic margin AND the
  **one-sided** bound holds: lower edge of the 90% CI of (stop − hold)
  > −margin (Amendment 1: the management question is "does the stop COST
  more than the margin", so a stop that beats hold passes; the previous
  two-sided "CI inside ±margin" wording contradicted the runner and is
  superseded).
- **NOT_ESTABLISHED** otherwise. An underpowered miss licenses nothing.

**Economic margin: 0.005 terminal-wealth fraction over the 60-day window**
(≈3%/yr drag — the smallest management effect worth acting on given the
+3%/yr execution standard). **The margin is never shrunk.**

**§64 power check (Amendment 1, superseding the v1 figure):** the draft's
"MDE ≈ 0.0045 < 0.005, ANSWERABLE" was measured on the WRONG ARM
(trim_25) under the WRONG DEPENDENCE UNIT (month blocks). The
mean-masked audit of the exact primary cell under 84-day blocks
(`scripts/convexity_primary_power_audit.py`, receipt
`primary_power_audit_2026-08-19.json`, run before any aggregate read)
measures **MDE = 0.0071 > 0.005**. Therefore, declared PROSPECTIVELY:
**STOP_NONINFERIOR is NOT_ANSWERABLE_AT_N on this panel** — the trial
can still establish STOP_DESTROYS (a destruction ≥ its run-time MDE) or
return NOT_ESTABLISHED, and the noninferiority question is reserved for
the CRSP-PIT extension where n grows. A NOT_ESTABLISHED here is a
power statement, not evidence of safety.

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
the declared band otherwise. **Amendment 1 wording fix:** the per-name
costs are **baked into `episodes_v2.parquet` at materialization**
(`scripts/convexity_episodes_materialize.py --taq-costs`), not looked up
at run time; the v2 metadata records which basis each name used
(verified: AAPL one-way 0.59 bp).
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

## Amendment 1 (2026-08-19, applied pre-run, before any aggregate read)

Adjudicated from the external GPT audit of 2026-08-19 (4/4 confirmed on
this document) under Murat's recorded in-session approval. No score of
the registered basis existed when these were applied; the only prior
computation on real episodes was the mean-masked power audit above.

1. **Dependence unit repaired:** bootstrap blocks now span the 60-day
   outcome overlap (84 calendar days derived from panel spacing), not a
   hardcoded 21-day month. n_effective: 22 blocks, not 143.
2. **Power re-measured on the exact primary cell**, mean-masked. Result:
   MDE 0.0071 > margin 0.005 ⇒ STOP_NONINFERIOR declared
   NOT_ANSWERABLE_AT_N prospectively. The margin was NOT shrunk.
3. **Noninferiority criterion made one-sided** (matches the runner; the
   drafted two-sided equivalence wording is superseded).
4. **Execution semantics frozen:** daily-close trailing rule
   (`close_trail_20` alias), never described as a broker intraday stop.
5. **Cost wording corrected:** TAQ costs baked at materialization.

Rehearsal gate (run before the registered command): all four declared
worlds — destruction / null / stop_superior / near_margin — through the
final runner; STOP_DESTROYS must fire only in `destruction`, and
`stop_superior` must never yield STOP_DESTROYS.

— drafted 2026-08-19 day session; the daemon's declared priors predate it

---

## RESULTS (registered run 2026-08-19T070720Z, appended post-run)

Receipt: `backend/data/optimus/convexity/trial_2026-08-19T070720Z.json`.
First run (070510Z) refused itself with NaN means — 1 of 6198 primary
pairs had a missing leg (ENPH 2026-05-14); pair-integrity repair (drop
WITH count, refuse if >1%) applied before any finite aggregate existed.

Paired tw diff (arm − hold), +40 threshold, 22 effective 84-day blocks,
Holm FWER 0.05 across the 5 declared arms:

| arm | mean tw diff | MDE(80%) | verdict |
|---|---|---|---|
| `trail_stop_20` (DECIDING) | −0.0055 | 0.0071 | **NOT_ESTABLISHED** |
| `stop_vol_1_5` | −0.0080 | 0.0092 | NOT_ESTABLISHED |
| `trim_25` | −0.0129 | 0.0073 | **STOP_DESTROYS** |
| `trim_50` | −0.0258 | 0.0146 | **STOP_DESTROYS** |
| `exit_full` | −0.0516 | 0.0292 | **STOP_DESTROYS** |

**Verdict sentences (scope-aware, §60):** On 2019–2026 US large caps
(182-name contemporary panel, TAQ-measured costs), immediately trimming
25%/50% or fully exiting a +40% winner destroyed 60-day terminal wealth
— per-dollar drags of 1.3%/2.6%/5.2%, each clearing its MDE under Holm.
The **daily-close 20% trailing exit** shows the same sign (−0.55%) but
below its 0.71% MDE: NOT_ESTABLISHED, and noninferiority was
prospectively NOT_ANSWERABLE_AT_N. H1's direction (the right tail pays)
is confirmed for mechanical de-risking arms; the trailing-stop question
is reserved for CONVEXITY-CRSP-REPLICATION-1 (design frozen BEFORE this
table was read). §61 cap: ADAPTIVE_HISTORICAL_VALIDATION — this is
evidence about Murat's management question on historical episodes, not
production policy and not a skill claim.
