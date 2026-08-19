# PREREG — AEGIS-NET-TOURNAMENT-1

SIGNED-BY: Murat Abdullaev — verbal in-session approval 2026-08-19 ("I approve everything on my queue", given in response to the session summary that described AMENDMENT 1 including the changed primary metric); recorded by the working session

**Status: SIGNED 2026-08-19 (see SIGNED-BY above); registered run
complete, RESULTS appended below. [Hygiene pass 2026-08-19: this line
previously still read "DRAFT" after signature — status text only, no
protocol text touched.] The harness
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
the same way.

**Verdicts are THREE-WAY per arm (amendment 1 — an underpowered miss is not
evidence of linearity; canon: a null owes both its MDE and an equivalence
test):**

- `COMPLEX_WINS` — the arm clears the decision rule below.
- `LINEAR_NONINFERIOR` — the instrument could see the economic bar
  (run-time MDE ≤ ΔIC 0.01) AND the 90% CI's upper edge sits below it. Only
  this outcome licenses the finding *"the shape is linear on these features;
  spend the next dollar on scale, coverage and cost."*
- `NOT_ESTABLISHED` — everything else, including every underpowered cell.
  The next-dollar DECISION may still favour scale (prior + G5 receipts),
  but it is a decision under uncertainty, not a finding.

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
Deciding number (amendment 1 — one unit end to end): the **paired per-date
Spearman rank-IC difference** of each complex arm against `linear_ridge`
(ΔIC, positive = the arm beats linear), over all walk-forward test dates,
with date-block bootstrap (`block_bootstrap_paired`). The block size is
**derived from the panel's own date spacing** so one block spans the 20-day
outcome overlap — on this month-end panel that is ~1–2 panel dates, and the
§58 n_effective is ~145 monthly blocks, matching the power basis below.
(The original draft blocked 20 *panel dates* — 20 months — which silently
tripled the run-time MDE against the registered power basis; found and
fixed 2026-08-19, `net_tournament.bootstrap_block_dates`.)

Decision rule, committed before any number exists:
- An arm earns `COMPLEX_WINS` iff mean ΔIC > 0 AND |mean| ≥ its own
  bootstrap MDE(80%) AND it survives **Holm at FWER 0.05 across the m = 4
  declared complex arms**.
- `LINEAR_NONINFERIOR` requires run-time MDE ≤ ΔIC 0.01 AND 90% CI upper
  edge < 0.01. Anything else is `NOT_ESTABLISHED` (see Hypothesis).
- The paired per-row squared-loss difference is retained as a **diagnostic**
  (reported beside the primary, never deciding).
- Rank IC per arm, the other heads (magnitude, realised vol, drawdown,
  barriers), and all ablations are **reported, never deciding** (SCREEN,
  BH-FDR at 0.10, m = tests actually run, counted by the daemon).

## Power declaration (§64, run forwards — before any outcome is read)

At a declared per-month IC dispersion σ≈0.10 and 145 monthly blocks, the
80%-power MDE on the ΔIC primary is ≈ 2.8·σ/√145 ≈ **0.023**. The
economically meaningful bar declared here is **ΔIC 0.01** (what plausibly
survives measured TAQ costs at monthly turnover). 0.023 > 0.01, therefore:
**at the economic bar this panel's primary contrast is NOT_ANSWERABLE_AT_N
unless the measured dispersion comes in materially under the declared σ —
recorded NOW, at registration, not discovered after** (Order 19 §2: the bar
is never shrunk to rescue a cell). Amendment 1 makes this power basis and
the deciding statistic the SAME unit measured on the SAME dependence
structure (~monthly blocks); the run-time bootstrap MDE is the operative
number and the trial reports "which effects were resolvable" alongside
every verdict. If run-time MDE > 0.01, the honest ceiling is
`NOT_ESTABLISHED` for any arm that fails to win — never "linear".

## Frozen protocol parameters (amendment 1 — nothing deciding lives only in code)

- `first_test_year = 2016`; expanding-window annual refits
  (`world_model.walk_forward_folds`), 2H-day embargo at each boundary,
  `min_train = 1000`, `horizon_days = 20`.
- Seed `20260819` everywhere; LightGBM deterministic single-thread.
- Missingness: features median-imputed on TRAIN only; rows with a missing
  TARGET dropped and counted (a missing target imputed is a label invented).
- Bootstrap: `block_bootstrap_paired`, 2000 resamples, block size from
  `bootstrap_block_dates` (panel-spacing-derived; see Primary metric).
- Multiplicity: Holm FWER 0.05, m = 4 declared complex arms (primary);
  BH-FDR 0.10 for everything reported-not-deciding.
- Software versions are recorded in the run receipt at run time.

## The competing-risks barrier head (amendment 1 — now executable as declared)

Registered on `barrier_up20_down10` ONLY at this horizon. Protocol
(`net_tournament.run_barrier_head`): the SAME walk-forward folds as every
other head; per fold, cause-specific Cox (up- and down-hazard; the other
cause and `neither` censor) and a timing-blind multinomial logistic on
{up, down, neither} are fit on train and scored on the HELD-OUT test rows —
per-cause concordance of each model's risk score against the test
(duration, event) pairs. Sub-30-event causes refuse per fold and are
counted. The pooled paired difference (Cox − multinomial) has n = FOLDS and
is SCREEN-grade by construction. `fit_cause_specific`'s in-sample
concordance is a diagnostic and decides nothing.

## Cells recorded NOT_ANSWERABLE at registration

- `barrier_up75_down30` at h=20: 0.6% event rate (~150 events); the
  cause-specific fit refuses below its 30-event-per-fold floor.
- `barrier_up40_down20` at h=20: 2.7% — pooled fit only; per-fold thin.
- The competing-risk comparison (cause-specific Cox vs multinomial) is
  therefore registered on `barrier_up20_down10` ONLY at this horizon.

## Universe-selection limitation (amendment 1 — declared, and it caps claims)

The panel's universe is the 2026 TAQ-calibration 182 applied back to 2013 —
a **current-universe selection**, tilted toward names that survived to 2026
(EA, MMC→MRSH, SQ→XYZ and PXD are this week's proof identity is not
static). That is acceptable for a hermetic ARCHITECTURAL comparison on "the
features this machine actually has," and is exactly why every claim here is
§61-capped; it is NOT a basis for historical cross-sectional economics. The
companion registration `UNIVERSE-SURVIVAL-STRESS-1` (CRSP PIT universe via
permanent identifiers; same arms; primary output = does the arm RANKING
move) is the declared robustness check, and any material rank movement
there files an erratum against this trial's interpretation section.

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

## AMENDMENT 1 — 2026-08-19 day session, PRE-SIGNATURE (drafting, not tampering)

No score has ever been computed on the registered panel (the gate refuses
unsigned; verified again today). The draft was repaired before signature on
four defects raised by external review round 3 and verified against the
code, plus one found during the repair:

1. **Units:** the deciding statistic was squared loss while the economic
   bar and power basis were ΔIC. Primary is now the per-date rank-IC
   difference; squared loss demoted to diagnostic.
2. **Verdict:** "anything else adopts the linear verdict" conflated
   NOT_ESTABLISHED with noninferiority. Three-way verdicts now; an
   underpowered miss is never evidence of linearity.
3. **Executability:** the registered competing-risks comparison existed in
   code but was never called by the runner, and its concordance was
   in-sample. `run_barrier_head` now runs it walk-forward, held-out, with
   the multinomial comparator on identical rows/folds.
4. **Frozen params:** `first_test_year=2016`, folds, seed, imputation and
   bootstrap config were hard-coded in the runner but unregistered. Now in
   the Frozen-protocol section.
5. **(Found during repair)** the bootstrap blocked 20 *panel dates*
   (= 20 months) instead of the 20-trading-day overlap — the run-time MDE
   silently disagreed with the registered power basis by ~√20. Block size
   is now derived from panel spacing (`bootstrap_block_dates`).

Also added: the universe-selection limitation clause and the
`UNIVERSE-SURVIVAL-STRESS-1` companion. Synthetic known-answer worlds
(`--world linear|nonlinear|null|barrier`) are part of the harness
acceptance: nonlinear world → a nonlinear arm must win; null world → no
COMPLEX_WINS; barrier world → survival must beat timing-blind, held out.

## RESULTS — first registered run, 2026-08-19 (receipt `tournament_2026-08-19T040624Z.json`)

Recorded after the fact; nothing above this section changed post-run.

**Primary (cs_rank, deciding):** ridge IC +0.0004. ΔIC vs ridge: LightGBM
+0.0124 · MLP-1 +0.0112 · MLP-2 +0.0134 · MLP-3 +0.0064, each against a
run-time bootstrap MDE ≈ 0.051–0.055 (126 monthly test dates, block=1).
**Verdict, all four arms: NOT_ESTABLISHED.** The registered power warning
fired exactly as written: measured per-date IC dispersion (se·√126 ≈ 0.21)
is ~2× the declared σ≈0.10, so the economic bar (ΔIC 0.01) was not
resolvable at this n. Per amendment 1 this is NOT a linearity finding —
LINEAR_NONINFERIOR was unreachable (MDE > bar) and is recorded as such.
SCREEN-grade observation, reported not deciding: all four complex arms
carry the same positive sign, mean ΔIC ≈ +0.011 ≈ the economic bar.

**Reported heads (never deciding):** forward_realised_vol — ridge 0.652
beats every NN (0.540–0.627). forward_max_drawdown — ridge 0.415 beats
every NN (0.331–0.372). The §59 learnability ordering (risk ≫ return)
reproduces on this panel, and the G5 shape-negative extends to these risk
heads on numeric-price features: **the linear map wins the heads that are
learnable at all.**

**Competing-risks barrier (up20_down10):** held-out concordance, 11/11
folds scored, 0 refusals — Cox 0.849 vs multinomial 0.854 (up), 0.664 vs
0.663 (down). Up-barrier risk is strongly rankable; the timing information
adds nothing beyond incidence at this horizon (SCREEN, n = folds).

**What this licenses (§61 cap applies):** spend the next dollar on scale,
coverage and cost — as a DECISION under uncertainty, with the return-shape
question honestly unresolved at this n. The ablation ladder's next rungs
(+options, +expectations) run as amendments naming this document as parent
when their PIT stores materialize. UNIVERSE-SURVIVAL-STRESS-1 remains the
declared robustness check on the universe selection.
