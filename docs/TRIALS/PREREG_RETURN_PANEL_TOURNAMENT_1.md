# PREREG — RETURN-PANEL-TOURNAMENT-1: does information beyond price buy a
# return-ranking signal at scale?

SIGNED-BY: Murat Abdullaev — recorded order 2026-08-22 ("we should run
backtests, randomized backtests, supervised and unsupervised training with
and without the help of LLM to build the engine and the brain and the NN.
find out what methodology and the methods are the best and continue with
the build"), recorded by the working session under the RISK-HEAD-AT-SCALE-1
signature precedent. Frozen before any model saw AEGIS-PANEL-1.

**Family:** supervised cross-sectional return screen on the canonical panel.
**Grade:** SCREEN. A surviving primary licenses a PORTFOLIO-STAGE
registration (costs, turnover, capacity, terminal wealth) and nothing else.
**ACCRUES ZERO ARMS. Never a lane, never a book, no buy/sell language.**

## 0. Corpse check — the predecessors are named and this is not them

`python scripts/lint_prereg.py TRIALS/PREREG_RETURN_PANEL_TOURNAMENT_1.md`

- **AEGIS-NET-TOURNAMENT-1** (2026-08-19, REGISTERED): on 182 contemporary
  names × 7 price features, NO arm established a return-ranking edge over
  ridge. Untouched here — this trial changes BOTH the universe (~4,300 PIT
  names, delistings included) and the information set.
- **UNIVERSE-SURVIVAL-STRESS-1** (SCREEN): price-only return ICs ≈ 0 for
  every arm, 2017–2024 at scale. That is the FLOOR this trial prices
  against — the floor arm is those features, verbatim.
- **RISK-HEAD-AT-SCALE-1** (CLOSED, LGBM_WINS on vol): its SCREEN found
  price-only return ICs positive in 1994–2012 and ~0 in 2017–2024, and
  declared the return question a NEW registration. Resurrects: the
  return-head question — **new instrument: 412 JKP characteristics in 12
  declared families (VALUE/QUALITY/GROWTH/ACCRUALS/ISSUANCE/…), none of
  which any prior arm ever saw.**
- **H3/13F-popularity corpse & 206-predictor NET median −0.12%/yr:** the
  stated prior is WEAK-OR-NULL. A null here is a finding about the panel's
  families at this scale, reported at its MDE, never softened.
- **CONSTRUCTION-CUT-1** (construction is not the bottleneck) is not
  contradicted: this trial asks about SELECTION information, not
  construction.

## 1. Substrates (all on disk before registration; hashes in the receipt)

- `aegis_panel/aegis_panel_v1.parquet` — 230,640 rows × 419 features,
  131 formation months 2014-01..2024-11, 4,354 permnos, PIT spine with
  delisting returns compounded (`crsp_pit_monthly_v1` filters frozen).
- JKP PIT spot-audit receipt `aegis_panel/jkp_pit_audit_2026-08-22.json`
  = **PASS** (2,479 change events: 621 annual at the 4-month rule, 1,836
  quarterly at announcement month, 19 unattributable, 3 late-filer edge
  cases under JKP's own uniform 4-month rule, 0 genuine lookahead). The
  registered run REFUSES if this receipt is absent or non-PASS.
- Primary label `ret_1m_fwd`: next CALENDAR month `ret_incl_delist` from
  the spine; month gaps yield NaN, never "next observed month".

## 2. Arms (frozen; hyperparameters are part of this registration)

| arm | features | model |
|---|---|---|
| `floor_lgbm` | 7 price-floor features (stress-1 verbatim) | LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.05, random_state=20260819) |
| `full_lgbm` | 419 (floor + 412 JKP) | same LGBM, verbatim |
| `full_ridge` | 419 | SimpleImputer(median) → StandardScaler → Ridge(alpha=1.0) |
| `full_mlp` | 419 | SimpleImputer(median) → StandardScaler → MLPRegressor((64,64), max_iter=200, random_state=20260819) |
| `full_lgbm_rank` | 419 | LGBMRanker(lambdarank, same complexity params); label = within-date decile of ret_1m_fwd; group = formation date |

No tuning, no additional arms, no feature engineering beyond the panel as
built. NaN goes to LGBM natively; sklearn paths use median imputation
(house rule).

## 3. Folds (frozen)

Expanding walk-forward: test year y ∈ 2016..2024, one fold per year.
Train = formation months whose LABEL month is strictly before Jan y (a
one-month embargo by construction — the December y−1 formation, whose
label is Jan y, is excluded from train). min_train = 20,000 rows or the
fold is refused and reported.

## 4. Primary (ONE deciding cell) and decision rule

- **Primary:** paired per-formation-date Spearman rank-IC difference
  **full_lgbm − floor_lgbm** on `ret_1m_fwd`, pooled over all test dates
  (~108). Date-block bootstrap per §58 (block from
  `bootstrap_block_dates`, labels are non-overlapping monthly).
- **§64 masked audit is written BEFORE any verdict is computed** (n_dates,
  block, SE, MDE at 80% power, both limbs' answerability), mean masked.
- **Declared direction:** POSITIVE. **Economic bar:** 0.01 IC (the
  tournament's registered bar).
- **Three-way verdict** (the tournament machinery, verbatim):
  `INFORMATION_ADDS` / `FLOOR_NONINFERIOR` (one-sided: the full arm's edge
  bounded below the bar) / `NOT_ESTABLISHED`. A null owes two tests: the
  equivalence read prints beside the significance read.
- **ADOPT-grade gate (declared now):** any claim that licenses a
  portfolio-stage registration requires, IN ADDITION to
  `INFORMATION_ADDS`, the full_lgbm arm's own pooled IC ≥ 0.01 with its
  90% CI excluding zero. A dIC win over a zero floor with an absolute IC
  of 0.005 is a finding about the panel, not a licence.

## 5. Null world (runs FIRST, same pipeline, planted answer = nothing)

Before the registered run: `ret_1m_fwd` permuted WITHIN each formation
date (`default_rng(20260822)`), full pipeline on the primary contrast.
Required outcome: no win verdict — the contrast must NOT come back
`INFORMATION_ADDS`, and |dIC| must sit inside its MDE. Receipt stamped
`NULL_WORLD`. The registered run REFUSES to start without a null receipt
for the same panel hash satisfying this. A null-world "pass" (signal
found in noise) halts everything and is itself the session's headline
finding.

**ERRATUM 2026-08-22, pre-run (recorded before the registered panel was
opened):** this section originally demanded the verdict literal
`NOT_ESTABLISHED` in the null world. That was a mis-specification of this
protocol's own three-way machinery: `NOT_ESTABLISHED` means an
UNDERPOWERED miss, while a POWERED pipeline shown pure noise correctly
returns the bounded-null verdict (`FLOOR_NONINFERIOR`) — which is the
machine working, not a signal. The null world ran first, produced
exactly that (dIC +0.0009 against MDE 0.0082), and the runner's literal
check halted as written. The acceptance condition is corrected to the
sentence above (no win verdict + inside MDE); the primary metric,
decision rule, arms, folds and bar are untouched. A test pinned to a
literal that the machinery is designed to move past cannot be the gate —
the gate is the absence of a WIN on noise.

## 6. SCREEN (BH-FDR 0.10, m = cells actually run; reported, never deciding)

Model ordering (full_ridge / full_mlp / full_lgbm_rank vs full_lgbm,
paired dICs); single-family LGBM ICs (each of the 12 families alone vs
floor — where does the information live); per-year IC paths (era
stability); `fwd_vol_21d` cross-check head (risk restates
RISK-HEAD-AT-SCALE-1 or the panel join is suspect — a diagnostic, not a
new risk claim).

## 7. Scope and §-notes

- §58: n_effective counts DATE BLOCKS (~108 months, block from measured
  spacing). §60/§61: the slice is 2014–2024 US common stocks above
  $5/$100M-dollar-vol — verdicts are scoped to that slice and era; the
  1990–2012 era has NO JKP families and any early-era claim is a successor
  registration on the families that exist there. §62: tradability is by
  construction of the universe filters; capacity is NOT addressed here.
- An IC is not money. Costs, turnover, capacity and terminal wealth are
  the portfolio stage's questions, behind their own registration and the
  standing execution standard (net excess CAGR ≥ +3%/yr AND ≥4/6 regime
  blocks AND holdout).
- LLM/TEXT factorial: TEXT is a DECLARED ABSENT family in v1; nothing in
  this trial speaks to LLM value (ABLATION-1 owns that question).

slice_purpose: EXPLORE — a SCREEN over declared families and frozen arms on the modern-era panel; no confirm authority; any survivor's confirmation is a successor registration on a slice this run never touched
parent_trial: RISK-HEAD-AT-SCALE-1
selection_period: 2016-01-01 .. 2026-08-19 (the floor features, arms and hyperparameters were selected by the predecessor tournament and stress receipts, all closed before this registration)
selection_window: 2016-01-01 .. 2024-12-31 (walk-forward test years; expanding train from 2014)
slice_securities: US common stocks, CRSP shrcd 10/11, exchcd 1-3, price ≥ $5, monthly dollar volume ≥ $100M (crsp_pit_monthly_v1 frozen filters), delisting returns included
information_cutoff: each row's formation month-end; JKP characteristics are formation-stamped per the PASS spot-audit; the label begins strictly after formation
slice_period: 2016-01-01 .. 2024-12-31 (test folds; CRSP vintage ends 2024-12-31)
hypothesis_source_period: 1993-01-01 .. 2026-08-19 (Gu-Kelly-Xiu 2020 and the JKP factor literature; our own receipts through 2026-08-19 — all strictly before this registration; no forward data is involved anywhere)
declared_effect_size: 0.01 paired per-date rank-IC difference (full_lgbm − floor_lgbm), the tournament's registered economic bar
event_frequency_per_year: 12 (formation months; ~108 paired test dates across the nine folds)
outcome_dispersion: 0.03 (sd of the PAIRED per-date dIC; prior paired contrasts at scale ran 0.02-0.04, giving SE ≈ 0.003 and MDE ≈ 0.008 at 108 dates — both limbs expected answerable; the §64 audit in the runner is the authority)
dependence_unit: ONE independent observation is one FORMATION MONTH's paired dIC — the ~1,900-name cross-section is collapsed to a single per-date Spearman IC BEFORE any inference, so cross-sectional dependence cannot inflate n by construction; serial dependence across months is handled by the §58 date-block bootstrap, whose block derives from measured spacing (labels are non-overlapping monthly, so adjacent months share no label window)
cross_sectional_n: 1 (genuinely 1 BY CONSTRUCTION: the ~1,900 names per date are collapsed into a single per-date Spearman IC before any inference — no cross-sectional row is ever pooled as an independent observation, so the observation's cross-sectional width is 1, not 1,900)
cluster_size: 1 (one formation month per observation; any residual month-to-month clustering is absorbed by the block bootstrap, not assumed away)

## 8. May NOT

Tune anything · add or drop arms or families after this line · feed any
lane, book, or surface · pool cells with any predecessor's · read the
registered panel before the null-world receipt exists · claim alpha or use
buy/sell language (an IC is not money) · treat the 3 late-filer JKP edge
cases as retired (they are recorded, bounded, and carried in the receipt).

— frozen 2026-08-22, before any model saw the panel

---

## RESULTS (registered run 2026-08-22, appended post-run)

Receipts: `aegis_panel/tournament_null_world.json`,
`tournament_primary_audit.json` (§64, mean masked, written first),
`tournament_primary.json`, `tournament_screen.json`. Panel hash
`34f7cb98ad147785`, 106 paired test dates 2016–2024.

**NULL WORLD (ran first):** dIC +0.0009 inside MDE 0.0082, no win on
noise — and it caught this prereg's own §5 verdict-literal
mis-specification before the registered panel was opened (erratum above).

**PRIMARY: NOT_ESTABLISHED.** Paired dIC (full_lgbm − floor_lgbm) =
**−0.0025**, SE 0.0075, **MDE 0.0210** against the 0.01 bar — the
noninferiority limb was NOT answerable (realized per-date dIC dispersion
~0.077 vs the declared 0.03; the §64 audit said so before the verdict).
Full-arm pooled IC **−0.0007**. At this instrument's resolution, 412
characteristics did not buy a return-ranking signal over the price floor
on 2016–2024. adopt_grade=False. No portfolio-stage registration is
licensed.

**SCREEN (BH-FDR discipline; every cell inside its MDE — leads, not
results):**

- Model ordering: ridge ≈ LGBM (dIC +0.0005); MLP +0.0107 vs LGBM (MDE
  0.0175 — inside noise, but MLP's own pooled IC +0.0100 was the only
  arm that touched the bar); **LambdaRank −0.0405 — the ranking
  objective actively hurt**, with per-year swings (−0.16..+0.09) that
  look like decile-label overfit.
- Family ablation (each family alone + floor, vs floor): **RISK_PRICE
  (+0.0157 own IC, dIC +0.0140) is the ONLY family with a
  positive-looking lead** — the return-flavored shadow of the standing
  "risk is stationary" result. Every fundamental family (VALUE −0.0066,
  QUALITY −0.0061, GROWTH −0.0035, ACCRUALS −0.0019, LIQUIDITY −0.0099
  vs floor) is flat-to-negative in this era. And the FULL panel
  (−0.0007) is WORSE than RISK_PRICE alone — 400 flat columns dilute
  the one family with a pulse.
- Vol cross-check: floor 0.744 → full 0.779 forward-vol IC — the panel
  join restates RISK-HEAD-AT-SCALE-1 (a diagnostic pass; the risk claim
  belongs to that trial, not this one).

**ANNOTATION 2026-08-22 (instrument calibration — documents an engine
property, changes no frozen parameter):** the sensitivity worlds
(`tournament_planted_linear.json`, `tournament_planted_linear_dense.json`,
SENSITIVITY_WORLD, run after the registered result) measured what this
instrument can DETECT: a planted linear factor of IC 0.03 — sparse
(one column) or dense (82-column family carrier) — is recovered at only
dIC +0.001..+0.003, far inside the MDE. A per-date z-scored training
label changes nothing in these worlds — including the heteroskedastic
world built for exactly that question
(`tournament_planted_linear_hetero.json`: signal AND noise scaled by each
month's REAL cross-sectional dispersion; raw-label LGBM recovers +0.0021,
z-label +0.0001). The objective-mismatch hypothesis is refuted at this
scale; the binding constraint is sample size, full stop. The
arithmetic: planted R² ~0.001 against 419 features on ~10^5 training
rows leaves even the optimal estimator with a fraction of the signal,
and the MDE sits at that recovered scale. **Therefore this trial's
NOT_ESTABLISHED bounds only signals well above realistic single-name
IC scale; it is close to uninformative for effects ≤0.03.** The panels
where supervised return prediction demonstrably resolves (GKX-class)
are ~100× larger (all caps, 60 years). The successor instrument is
scale — a full-history all-cap panel — and any TOURNAMENT-2 must show
planted-world detectability at its declared effect size BEFORE its
registered run is interpreted.

**What follows (successor registrations, not this trial's authority):**
a RISK_PRICE-family-only return screen with its own §64 (the lead's MDE
here was 0.0229 — a confirmatory design needs more dates or a paired
construction with tighter dispersion), and the portfolio-stage question
stays unlicensed. The 4mo-late-filer JKP edge and the era scope (§7)
carry into any successor.
