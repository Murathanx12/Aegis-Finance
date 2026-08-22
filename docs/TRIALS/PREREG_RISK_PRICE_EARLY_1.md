# PREREG — RISK-PRICE-EARLY-1: does the one family with a pulse transfer
# to an era no JKP-based arm ever touched?

SIGNED-BY: Murat Abdullaev — recorded order 2026-08-22 ("continue with
whats left, make sure to validate whats we built so far too", following
"run backtests... find out what methodology and the methods are the
best"), recorded by the working session under the RISK-HEAD-AT-SCALE-1
signature precedent. Frozen before any model IC existed on the early era
with these features.

**Family:** cross-sectional return screen, TRANSFER of a modern-era lead.
**Grade:** SCREEN. A surviving pattern licenses exactly one thing: the
foreign-country JKP pull (named consumer) as the CONFIRM instrument.
**ACCRUES ZERO ARMS. Never a lane, never a book, no buy/sell language.**

## 0. Corpse check — the lead, its predecessors, and the new instrument

`python scripts/lint_prereg.py TRIALS/PREREG_RISK_PRICE_EARLY_1.md`

- **Parent lead (named, selection-biased, inside its MDE):**
  RETURN-PANEL-TOURNAMENT-1's screen (2026-08-22) found RISK_PRICE the
  ONLY family with positive return-rank information on 2016–2024
  (+0.0157 own IC, +0.0140 over the price floor, MDE 0.0229 — a lead,
  never a result). The full 412-column panel diluted it to zero.
- **RISK-HEAD-AT-SCALE-1 SCREEN:** early-era price-only RETURN ICs were
  positive (+0.012..+0.017) vs ~0 modern — era-dependence is the known
  hazard, which is why this trial runs the family in BOTH eras under ONE
  construction.
- **Resurrects:** the early-era return question — **new instrument: the
  RISK_PRICE family rebuilt from raw CRSP daily data with definitions
  identical in both eras** (11 features from prc/ret/vol + FF mktrf;
  `backend/services/risk_price_features.py`; turnover excluded because
  shrout is absent from the early daily pull — declared, not dropped
  silently). No JKP column is used anywhere, so a cross-era difference
  cannot be a construction difference.
- The 206-predictor NET-median corpse stands: prior is weak; a null here
  is reported at its MDE in the standing two-test form.

## 1. Substrates

- Early: `crsp_dsf_1990..2012` + `crsp_pit_monthly_early.parquet` (same
  frozen filters, delist returns compounded) + `ff_factors_daily`.
- Modern consistency cell: AEGIS-PANEL-1's spine/floor/labels (panel hash
  in receipt) with the SAME own-construction features.
- Label: next calendar month `ret_incl_delist` from the era's spine,
  month-gap-safe (the AEGIS-PANEL-1 convention, verbatim).

## 2. Arms (frozen; tournament hyperparameters verbatim)

| arm | features |
|---|---|
| `floor_lgbm` | the 7 price-floor features |
| `riskprice_lgbm` | floor + the 11 own-construction RISK_PRICE features |

LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.05,
random_state=20260819). No other arms, no tuning.

## 3. Folds

Early (deciding): expanding walk-forward, test year y ∈ 1994..2012, train
= formation months whose label month precedes Jan y (1-month embargo by
construction), min_train 20,000 rows. Modern consistency cell (SCREEN):
same design, test years 2016..2024.

## 4. Primary (ONE deciding cell)

Paired per-formation-date rank-IC difference **riskprice_lgbm −
floor_lgbm** on the early era (~228 dates), §58 date-block bootstrap.
**§64 masked audit written BEFORE any verdict.** Declared direction:
POSITIVE. Economic bar: 0.01 IC. Three-way verdict:
`RISKPRICE_ADDS` / `FLOOR_NONINFERIOR` / `NOT_ESTABLISHED`.

Honest power statement, declared now: at the modern screen's measured
paired-dIC dispersion (0.084/date), 228 dates give MDE ≈ 0.016 — the win
limb is answerable only if the true effect is at least ~0.016, and the
noninferiority limb at bar 0.01 is likely NOT answerable. This is a
SCREEN and says so; the confirm instrument (foreign JKP, ~15 countries)
is powered by construction and is what a surviving pattern licenses.

## 5. SCREEN (BH-FDR m=run; reported, never deciding)

Modern consistency cell — do the OWN-construction features reproduce the
JKP-based lead's direction on 2016–2024? (validates the lead AND the
construction against each other) · per-year IC paths both eras ·
riskprice-alone pooled IC · per-feature single-column dICs (where does
the family's information live).

slice_purpose: TRANSFER — the hypothesis (RISK_PRICE family carries return-rank information) was generated on the modern era by the parent screen; the deciding slice is 1994–2012, which no JKP-based arm and no risk-price return screen has ever touched
parent_trial: RETURN-PANEL-TOURNAMENT-1
hypothesis_source: RETURN-PANEL-TOURNAMENT-1 — its 2026-08-22 family-ablation SCREEN cell (RISK_PRICE +0.0140 over floor, inside MDE) is the OUTCOME that generated this hypothesis; the data that motivated the question was read, so this trial is TRANSFER and may never be written up as independent confirmation
selection_period: 2016-01-01 .. 2026-08-22 (the family was selected as the lead by the parent screen, closed 2026-08-22, entirely on modern-era data)
selection_window: 1994-01-01 .. 2012-12-31 (the deciding early-era walk-forward test years)
slice_securities: US common stocks, CRSP shrcd 10/11, exchcd 1-3, the early-era PIT screen's frozen filters, delisting returns included
information_cutoff: each row's formation month-end; every feature window ends at formation; the label begins strictly after formation
slice_period: 1994-01-01 .. 2012-12-31
hypothesis_source_period: 2013-01-01 .. 2026-08-22 (the parent screen's modern panel and receipts — strictly disjoint from the deciding slice)
declared_effect_size: 0.014 paired per-date rank-IC difference — the parent lead's UNSHRUNK point estimate, named as selection-biased; a true effect at the shrunk value (~0.010) is expected to land NOT_ESTABLISHED and that outcome is informative, not a failure
event_frequency_per_year: 12 (formation months; ~228 deciding dates)
outcome_dispersion: 0.084 (the parent screen's MEASURED per-date paired-dIC standard deviation on the same contrast shape — measured, not assumed)
dependence_unit: ONE independent observation is one FORMATION MONTH's paired dIC — the cross-section is collapsed to a single per-date statistic before inference; serial dependence handled by the §58 date-block bootstrap
cross_sectional_n: 1 (genuinely 1 by construction — no cross-sectional row is ever pooled as an independent observation)
cluster_size: 1 (one formation month per observation; residual clustering absorbed by the block bootstrap)

## 6. May NOT

Tune anything · add features or arms after this line · pool the modern
consistency cell into the deciding statistic (the hypothesis was SELECTED
there) · feed any lane, book, or surface · claim alpha (an IC is not
money) · treat a NOT_ESTABLISHED as evidence of absence (it owes the
equivalence read, which the §64 audit already predicts unanswerable at
this n — say so, don't bury it).

— frozen 2026-08-22, before any early-era model IC on these features

---

## RESULTS (registered run 2026-08-22, appended post-run)

Receipts: `aegis_panel/risk_price_early_audit.json` (§64, mean masked,
written first), `risk_price_early_trial.json`,
`risk_price_modern_cell.json`.

**PRIMARY (deciding, 1994–2012): NOT_ESTABLISHED — and the point
estimate is ZERO, not merely underpowered.** Paired dIC (riskprice −
floor) = **−0.0005**, SE 0.0051, MDE 0.0142, 215 dates. The modern lead
did not transfer: the early-era CI is roughly ±0.010 around zero, so
while the noninferiority limb at the 0.01 bar is formally unanswerable
at 80% power, nothing resembling the declared 0.014 is there.

**SCREEN modern consistency cell (2016–2024, never deciding): dIC
+0.0299 (MDE 0.0248)** — the own-construction 11-feature family
REPRODUCES and STRENGTHENS the JKP-based parent lead (+0.0140) on the
modern era. Own-construction vs JKP is not the difference; the ERA is.

**Reading, scope-aware:** the risk-price return signal, if real, is a
2016–2024-era phenomenon (consistent with the post-2015 defensive-factor
regime), not a stable law — the early era rejects transfer with a tight
zero. What this licenses is exactly what §0 declared: the
foreign-country JKP pull (same 2013–2024 era, ~13 developed markets) as
the cross-sectional confirm of a SAME-ERA effect. A modern-only signal
confirmed across countries is a regime fact worth registering forward;
a US-only, modern-only cell is one draw.
