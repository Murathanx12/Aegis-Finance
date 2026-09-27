# FINRA Reg SHO daily short-sale volume: PIT column + three rules (2026-09-27, Lane D)

**RESULT IMPROVEMENT: NONE.** None of the three rules beats SPY or the random panel. Two of them
underperform SPY significantly, and the SPY + (IWM-SPY) exposure accounts for that. The low-shorting
gate also makes 12-1 momentum worse, not better.

Receipt: `backend/data/optimus/strategy_library/finra/finra_short_volume_rules_2026-09-27T142546Z.json`
(run id `2026-09-27T142546Z`, panel fingerprint in the receipt, network none, LLM $0).
Runner: `python -m scripts.finra_short_volume_rules`. Licence: PRODUCT_EXPERIMENT. Rules registered
`2026-09-27T13:10:00Z` (`strategy_library_ext.REGISTERED_FINRA`) before the first score. Every
number before today is hindsight.

## Data
- Source: `https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt`, the consolidated
  off-exchange (FINRA-reported) files. This is short SALE volume, not short interest.
- Pulled: **19,645,674 rows, 2,049 trade dates, 2018-08-01 -> 2026-09-25**. 79 weekdays returned
  no file (403), which matches the exchange holidays. Manifest `finra_short_volume/manifest.json`
  records rows and sha256 per year and is tracked. The parquets are gitignored.
- PIT rule: a day's file is published after that day's close (~17:20 ET). A decision on day D reads
  only files dated strictly before D. The factory scores the month-end t close and enters at the
  t+1 open, so it asks for D = t+1 day and t's own file is the last one it may use. Pinned by
  `test_a_decision_on_day_d_does_not_see_day_ds_file` and
  `test_features_are_invariant_to_files_on_or_after_the_decision_date`.
- Coverage on eligible month-end rows (`short_vol_ratio_21`): 212,747 of 224,118 rows non-null,
  **3,550 names, 98 month-ends (2018-08-31 -> 2026-09-25), median 2,095 names per date.** The
  FINRA-to-panel join is by raw ticker, so class-share symbols like `BRK/B` do not match.

## Results (k=20, monthly, net of band costs 6/10/18/35 bps round trip, 95-96 months 2018-08 -> 2026-07)
SE = sd/sqrt(n); MDE = 2.8 x SE. The alpha is the intercept of net-SPY on [SPY, IWM-SPY].

| rule | net/mo | active vs SPY (SE, MDE, t) | vs random panel (t) | alpha (t) | IWM-SPY beta | LOO worst | verdict |
|---|---|---|---|---|---|---|---|
| low_short_vol_ratio | +0.43% | **-0.84%** (0.34, 0.96, -2.43) | -0.38% (-1.13) | -0.20% (-0.83) | 0.52 | -1.00% (drop 2022) | BETA_EXPLAINS |
| short_vol_ratio_falling | +0.28% | **-0.98%** (0.36, 1.00, -2.75) | -0.54% (-1.72) | -0.60% (-1.94) | 0.58 | -1.20% (drop 2024) | BETA_EXPLAINS |
| mom_low_short_vol | +1.28% | +0.01% (0.84, 2.35, 0.01) | +0.47% (0.61) | +0.30% (0.45) | 1.23 | -0.30% (drop 2022) | CANNOT_DISTINGUISH |
| controls: low_..._21_40 | +0.87% | -0.39% (t -1.14) | +0.06% | (-0.75) | 0.44 | | CANNOT_DISTINGUISH |
| short_vol_..._falling_21_40 | +0.79% | -0.48% (t -1.18) | -0.03% | (-0.01) | 0.88 | | CANNOT_DISTINGUISH |
| mom_low_..._21_40 | +1.94% | +0.67% (t 0.97) | +1.13% (1.78) | (1.72) | 1.08 | | CANNOT_DISTINGUISH |
| ref: mom_12_1 (same months) | +3.02% | +1.75% (t 1.62) | +2.21% (2.23) | +2.0% (2.10) | 1.62 | +1.08% (drop 2020) | (reference) |
| ref: short_covering | +0.45% | -0.82% (t -2.40) | -0.36% | (-1.98) | 0.51 | | (reference) |
| ref: random_1 | +1.22% | -0.05% (t -0.13) | +0.40% | (0.72) | 0.81 | | (reference) |

By year (active vs SPY, hold-month keyed) is in the receipt for every row. low_short_vol_ratio is
negative in 7 of 9 years, and short_vol_ratio_falling in 8 of 9.

## Reading, against the registered falsifiers
- **SSA-07a low_short_vol_ratio:** falsifier (b) fires. The book is low-SPY-beta (-0.31, t -5.4)
  and small-tilted (IWM-SPY 0.52, t 5.9). Once those exposures are removed, the -0.84%/mo is
  -0.20% (t -0.83). Falsifier (c) also fires: ranks 21-40 earn more than the top 20, so the
  ordering inside the decile carries nothing. The Boehmer-Jones-Zhang direction (low shorting
  beats high shorting) does not show on these off-exchange files.
- **SSA-07b short_vol_ratio_falling:** the residual is -0.60%/mo (t -1.94), the OPPOSITE of the
  claim, and under the MDE. The verdict rule calls it BETA_EXPLAINS, because |alpha t| < 2. Its
  (d) comparison is short_covering: that rule also lost (-0.82%), so daily frequency adds nothing
  it can show.
- **SSA-07c mom_low_short_vol:** falsifier (b) fires. The gated momentum book earns +1.28%/mo net
  against ungated mom_12_1's +3.02% over the same months, so the gate removes momentum return
  rather than adding it. Its own ranks 21-40 beat it, so (d) fires too.
- The mom_12_1 reference row meets the ALPHA_DETECTED conditions on this window (alpha t 2.10).
  It is not part of this lane, carries IWM-SPY beta 1.6, and has 2020 as its largest year. Nothing
  here changes what is already known about momentum.

## Not done / owed
- The matched random twin per rule (same band, same count, `signal_structure --matched-twins`)
  was not built. The all-universe random panel (3 controls, k=50) stands in for it.
- A health probe for FINRA staleness (the manifest's `last` against today) is owed in
  `system_health.py`. It was not added because that file is another builder's this session.
- The rules sit in `strategy_library.RULES`, so the nightly factory scores them from its next
  run, and `attach()` puts the columns on its panel. Nothing re-pulls FINRA on a schedule:
  `python -m scripts.pull_finra_short_volume` has to be run by hand, and it is idempotent and
  resumes where it stopped.
- No forward book was frozen. With these results none is warranted.
