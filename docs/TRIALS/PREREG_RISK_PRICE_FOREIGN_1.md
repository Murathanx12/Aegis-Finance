# PREREG — RISK-PRICE-FOREIGN-1: does the modern-era risk-price return
# signal exist outside the United States? (a FOREIGN screen — an
# era-bound claim is only ever CONFIRMABLE FORWARD)

SIGNED-BY: Murat Abdullaev — recorded orders 2026-08-22/23 ("run
backtests... find out what methodology and the methods are the best";
"continue pull" resuming the pull whose meta names this trial as its
consumer), recorded by the working session under the RISK-HEAD-AT-SCALE-1
signature precedent. Frozen before any model IC was computed on any
foreign row.

**Family:** cross-sectional return screen over thirteen foreign markets
in the SAME era as the US lead.
**Grade: FOREIGN — no confirm authority, by the calendar rule (R13e/N9):
securities-disjoint is not calendar-disjoint when markets co-move; a
rule selected on 2016–2024 US states and scored on other tickers through
the same states is being asked whether it fits the states it came from.
And deeper: the claim under test is ERA-BOUND, so no historical slice
anywhere can confirm it — only FORWARD accrual can. What this screen can
do is KILL the lead cheaply (a foreign zero closes it as US-local or
noise) or justify spending a forward instrument on it.**
**ACCRUES ZERO ARMS. Never a lane, never a book, no buy/sell language.**

## 0. Corpse check and lineage

`python scripts/lint_prereg.py TRIALS/PREREG_RISK_PRICE_FOREIGN_1.md`

**Not the parent re-run:** RISK-PRICE-EARLY-1 asked WHEN (does the US
lead exist in another era — no); this asks WHERE (does it exist in other
markets in its own era). Different axis, different substrate, same
frozen family.

Resurrects: RISK-PRICE-EARLY-1 — new instrument: thirteen foreign-market
cross-sections (2,384,261 stock-months, AUS..TWN, verified 2026-08-23)
that share NO securities with any slice the parent or grandparent read;
the parent's instrument was the US 1990–2012 daily store and could not
see any non-US market by construction.

- **RISK-PRICE-EARLY-1 (parent):** the US risk-price family is a TIGHT
  ZERO in 1994–2012 (dIC −0.0005 ± 0.0051) and +0.0299 (MDE 0.0248) on
  2016–2024 — an era-bound lead. Its RESULTS section licensed exactly
  this trial: same era, foreign cross-sections, never another US
  backtest.
- **RETURN-PANEL-TOURNAMENT-1 (grandparent):** RISK_PRICE was the only
  family with a pulse (+0.0140 over floor, inside MDE) among 11.
- **New instrument:** thirteen developed-market cross-sections
  (2,384,261 stock-months verified, 144 months each, no cap fills —
  `wrds/jkp_full/foreign_verify_2026-08-23.json`) that NO Aegis model
  has ever touched, sharing essentially no securities with the US slices
  that generated the hypothesis.
- The 206-predictor NET-median corpse stands; a null here closes the
  lead as a US-local (or noise) artifact and is a fully publishable
  outcome.

## 1. Substrate

`wrds/jkp_full/jkp_risk_{ctry}_2013_2024.parquet`, 13 countries
(AUS CAN CHE DEU ESP FRA GBR ITA JPN KOR NLD SWE TWN), JKP
`contrib_global_factor` construction, `eom` formation stamping (US
spot-audit PASS 2026-08-22; the construction is identical by vendor).
Label: `ret_exc_lead1m` (JKP delisting-aware lead; corr 0.99987 vs our
own construction on the US overlap).

**Universe within each country-month (frozen):** `common=1, obs_main=1,
primary_sec=1` (measured: already true on every pulled row) AND market
equity `me` at or above the country-month MEDIAN — the larger half of
each market, mirroring in spirit the US trials' liquidity screen without
importing a dollar-volume threshold that means different things across
markets. Rows lacking the label or any floor feature drop and are
counted.

## 2. Arms (frozen; tournament LGBM hyperparameters verbatim)

| arm | features |
|---|---|
| `floor_jkp` | ret_1_0, ret_12_1, ret_12_7, rvol_21d, rvol_252d — the closest JKP-native mirror of the US price floor (named approximation: no dd_252 / mom_63 / mom_126 equivalents were pulled) |
| `riskprice_jkp` | floor + {beta_21d, beta_252d, beta_60m, beta_dimson_21d, betabab_1260d, betadown_252d, corr_1260d, ivol_capm_21d, ivol_capm_60m, ivol_capm_252d, ivol_ff3_21d, ivol_hxz4_21d, iskew_capm_21d, iskew_ff3_21d, iskew_hxz4_21d, coskew_21d, rskew_21d, rmax1_21d, rmax5_21d, rmax5_rvol_21d, mispricing_perf, mispricing_mgmt} — the parent family's JKP columns, verbatim |

LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.05,
random_state=20260819). One pooled model across countries per arm per
fold (country is not a feature; the cross-section is ranked WITHIN
country-month, see §3). No tuning, no other arms.

## 3. Folds and the deciding statistic

Walk-forward: test year y ∈ 2016..2024; train = rows whose label month
precedes Jan y (one-month embargo by construction); min_train 100,000
rows. Per (country, month): Spearman rank IC of predictions vs
`ret_exc_lead1m` WITHIN that country-month (a country-month with <50
scored names is refused and counted). Per month: the unweighted mean of
the available country ICs. **Primary: the paired per-month difference
(riskprice_jkp − floor_jkp) of that cross-country mean, pooled over the
~108 test months, §58 date-block bootstrap.**

- **§64 masked audit BEFORE any verdict** — and it must additionally
  report the measured cross-country IC correlation (the effective number
  of independent markets), because the power arithmetic below assumes it.
- Declared direction: POSITIVE. Economic bar: 0.01. Three-way verdict:
  `NOT_US_ONLY` (screen-grade — licenses a FORWARD registration, nothing
  else) / `US_LOCAL` (one-sided: the foreign edge bounded below the
  bar — closes the lead) / `NOT_ESTABLISHED`.

## 4. SCREEN (BH-FDR m=run; reported, never deciding)

Per-country paired dICs (13 cells — where does it transfer) · per-year
paths · pooled IC levels per arm · a size-split cell (above-median vs
the excluded half is NOT run — the excluded half is out of scope by
declaration, not a hidden robustness knob).

slice_purpose: FOREIGN — the hypothesis was generated entirely on US slices; the deciding slice is thirteen NON-US cross-sections sharing essentially no securities with any hypothesis-source slice; the calendar OVERLAPS the source era by construction because the claim is era-bound, therefore this trial carries NO confirm authority and its positive branch licenses only a forward registration
parent_trial: RISK-PRICE-EARLY-1
hypothesis_source: RISK-PRICE-EARLY-1 — its modern consistency cell (+0.0299, MDE 0.0248, SCREEN) and the grandparent tournament's family-ablation cell are the OUTCOMES that generated this hypothesis; both read only US data; per R13e the calendar overlap means this trial may NEVER be written up as confirmation of any kind — it is a foreign-market screen whose positive branch licenses a forward registration and whose negative branch kills the lead
selection_period: 2016-01-01 .. 2026-08-22 (the family and effect size were selected on US receipts closed 2026-08-22)
selection_window: 2016-01-01 .. 2024-12-31 (foreign walk-forward test years)
slice_securities: non-US common stocks of 13 developed markets (AUS CAN CHE DEU ESP FRA GBR ITA JPN KOR NLD SWE TWN), JKP common/obs_main/primary_sec, market equity at or above country-month median; explicitly disjoint from every US slice that produced the hypothesis
information_cutoff: each row's eom formation stamp; every feature is JKP formation-stamped; the label begins strictly after formation
slice_period: 2016-01-01 .. 2024-12-31
hypothesis_source_period: 2013-01-01 .. 2026-08-22 (US-only data and receipts)
declared_effect_size: 0.014 paired per-month cross-country dIC — the US modern lead's magnitude, named as selection-biased; the equivalence limb bound is the 0.01 bar
event_frequency_per_year: 12 (months; ~108 deciding months over nine folds)
outcome_dispersion: 0.042 (per-month sd of the CROSS-COUNTRY MEAN paired dIC: the US single-market paired sd measured 0.084; averaging 13 markets with an assumed effective independence of ~4 gives 0.084/√4 = 0.042 — the ASSUMPTION IS DECLARED and the §64 audit measures the real cross-country correlation before any verdict; if the measured effective independence is lower the audit will say so and the win limb may not be answerable)
dependence_unit: ONE independent observation is one CALENDAR MONTH's cross-country mean paired dIC — within-market cross-sections collapse to one IC per country-month, and the thirteen same-month country ICs collapse to ONE number because global markets co-move; serial dependence across months is the §58 block bootstrap's job
cross_sectional_n: 1 (genuinely 1 by construction: both collapse steps happen BEFORE inference; nothing cross-sectional is ever pooled as independent)
cluster_size: 1 (one calendar month per observation)

## 5. May NOT

Tune anything · add or drop countries, features, or the size screen
after this line · pool any US cell into the deciding statistic · feed
any lane, book, or surface · claim alpha or CONFIRMATION of any kind (an
IC is not money, and a same-era slice confirms nothing — a `NOT_US_ONLY`
verdict licenses one FORWARD registration and nothing else) · read the
excluded small-cap half as a robustness check · treat
`NOT_ESTABLISHED` as `US_LOCAL` (the equivalence read prints beside the
significance read, per the standing two-test rule).

— frozen 2026-08-23, before any model IC on any foreign row
