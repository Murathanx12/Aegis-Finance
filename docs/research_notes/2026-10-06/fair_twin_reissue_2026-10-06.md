# Fair twin re-issue, 2026-10-06 (CHUNK C1)

## RESULTS

- **Rules that beat their fair twin at t >= 2 AND beat the market net in validation (2009-2016) at t >= 2: 1 of 301 on the fair-twin column alone (`qc761_ebit_ev_ebit_ic_large_annual`). 0 of 301 once pure selection (gross vs gross) is also required.**
- qc761 does not beat its twin on selection: pure selection is t 1.51 over the full sample and t 1.50 in validation. Its market line in validation is +0.46%/mo at t 2.34. Its leave-one-year-out worst on the full-sample market line is +0.16%/mo, from dropping 2009. It is the same single row the 09-30 note flagged, and that read was undeclared.
- **The two 09-30 "SURVIVES" verdicts (`quality_composite`, `cash_lowvol`) are now CANNOT_DISTINGUISH.** Both fail on DSR at the full search count. Their market line in validation is t 0.34 and t 0.15.
- **Bridges board, 85 rules:** SURVIVES 2 → 0. CANNOT_DISTINGUISH 68 → 46. FAILED_VARIANT 9 → 33. NOT_DECIDABLE 6 → 6. Registration candidates: 0 → 0.
- **Library board, 140 rules:** ALPHA_DETECTED 12 → 13. CANNOT_DISTINGUISH 74 → 61. FAILED_VARIANT 54 → 66. Every one of the 13 has a market line in validation below t 2. The highest is t 1.16.
- RESULT IMPROVEMENT: NONE. This changes what "beats its twin" may mean. It does not change any verdict against the market.

## What changed in code

There is now one convention: `matched_twins.TWIN_COST_CONVENTION = "OWN_TURNOVER_SAME_COST_MODEL"`. Its full statement is in the docstring of `twin_cost_convention()`.

- The twin pays the rule's per-trade model (`matched_twins.trade_cost`): half of each name's round trip on every traded weight. The round trip is max(Corwin-Schultz, flat band).
- It pays that on its OWN measured turnover.
- `turnover_cost` refuses a missing turnover. The old bridges board defaulted it to 1.0, which is a full round trip.
- `turnover_scaled_net` is the one function applied to both the rule and the twin.
- Every row prints `FOUR_COLUMNS`:
  - `pure_selection`
  - `fair_twin_net`
  - `net_minus_market`
  - `twin_full_round_trip_UPPER_BOUND`. This is the old charge. It is kept for comparison, and no verdict reads it.
- `hyp_investable.trade_cost` and `conditionals_on_crsp.trade_cost` were copies. They are now imports.

## The caveat the numbers force

The fair twin's measured turnover is still high: about **0.39-0.43 a month** for the quality rules, against the rules' own 0.11-0.17. The twin basket is rebuilt every month from the selection's cell mix. The vol and momentum terciles are re-cut each month, so the basket churns even while the rule holds its names.

So `fair_twin_net` still flatters low-turnover rules, though much less than the old charge did:

| | rules at t >= 2 (full sample, of 301) |
|---|---:|
| upper bound (old charge) | 178 |
| fair twin | 35 |
| pure selection | 29 |

- `quality_composite`: pure selection t 1.91 → fair t 3.54 → upper bound t 6.32 (1991-2016).
- Of the library's 13 ALPHA_DETECTED rows, 7 are new. In those 7, pure selection is below t 2, so the label comes from the twin's residual turnover. Examples: `roe` is pure selection t 0.94 against fair t 2.41; `qp0025_small_annual` is 0.65 against 2.27.
- Rules where fair twin AND pure selection are both at t >= 2: **19** (listed in the summary receipt). None of them clears the market line in validation.

**Read a twin verdict only where pure selection agrees with it.** A sticky twin, one that redraws a partner only when the rule replaces a name, would have exactly the rule's turnover. That is the obvious next construction. It needs the twin draws changed in `matched_twins.twin_series` and the CRSP library runs re-run, so it was not done here.

## Receipts

- Fair-twin board, 301 rules (all OK, 0 refused):
  - `backend/data/optimus/hyp_lab/twin_board_FT_2026-10-06_1.jsonl`
  - `backend/data/optimus/hyp_lab/twin_board_SUMMARY_FT_2026-10-06_1.json`
  - series in `backend/data/optimus/hyp_lab/fair_twin_series_FT_2026-10-06_1/`
- Bridges board re-issued: `backend/data/optimus/crsp_rebuild/bridges_board_BR_FLAT_2026-09-29T1535Z__FT_2026-10-06_1__2026-10-06T162730Z.json`
- Library board re-issued: `backend/data/optimus/crsp_rebuild/library_fair_board_LIB_2026-09-29T0802Z__FT_2026-10-06_1__2026-10-06T162735Z.json`
- Superseded for twin reads:
  - `hyp_lab/twin_board_SUMMARY_TB_2026-09-30_1.json`
  - `crsp_rebuild/bridges_board_BR_FLAT_2026-09-29T1535Z__2026-09-29T140355Z.json`

Every fair-twin row carries the year checks for the fair-twin and market columns: by hold year, and leave-one-year-out worst.

## Reproduce

```
python -m scripts.hyp_twin_board --run-id <NEW>
python -m scripts.bridges_on_crsp --part board --declaration BD_2026-09-29T1530Z --flat-run BR_FLAT_2026-09-29T1535Z --cs-run BR_CS_2026-09-29T1545Z --turnover-run BT_2026-09-29T1555Z --fair-run <NEW>
python -m scripts.library_on_crsp --part fair_board --run-id LIB_2026-09-29T0802Z --fair-run <NEW>
```

## Verdict diff: every rule whose headline changed

For the bridges board, the "old t" is rule minus twin on the 09-29 declared variant (full-CS twin), over 1991-2016. For the library board, it is rule minus twin21 at flat costs over the full sample.

### Bridges board (declared line)

| rule | old verdict | new verdict | old t (rule - twin, 1991-2016) | new t (fair twin, 1991-2016) | net - market t in VALIDATE |
|---|---|---|---:|---:|---:|
| `quality_composite` | SURVIVES | CANNOT_DISTINGUISH | +6.32 | +3.54 | +0.34 |
| `cash_lowvol` | SURVIVES | CANNOT_DISTINGUISH | +6.02 | +3.38 | +0.15 |
| `div_insider_earn_shorts` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.54 | -0.02 | -0.54 |
| `div_six_sources` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.52 | -0.14 | -1.65 |
| `low_dtc_mom` | CANNOT_DISTINGUISH | FAILED_VARIANT | +2.27 | -0.15 | -1.59 |
| `covering_flow` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.86 | -0.15 | -4.71 |
| `skill_mom_ranks_21_40` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.44 | -0.25 | -2.13 |
| `div_skill_mom_quality` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.42 | -0.39 | -1.42 |
| `qc241_value_composite_small_annual` | CANNOT_DISTINGUISH | FAILED_VARIANT | +2.38 | -0.44 | -0.19 |
| `margin_expansion` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.64 | -0.44 | -1.28 |
| `cash_rich` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.14 | -0.57 | -0.87 |
| `revenue_turn` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.79 | -0.60 | -1.85 |
| `rd01_roic_growth_mom_insider` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.90 | -0.60 | -1.23 |
| `rev_accel_large` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.46 | -0.61 | -1.60 |
| `margin_turn` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.93 | -0.85 | -1.19 |
| `op_margin_expansion` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.97 | -1.05 | -1.77 |
| `org_capital` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.11 | -1.22 | +0.64 |
| `mom_low_ag` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.38 | -1.34 | -1.28 |
| `rev_accel_mom` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.04 | -1.37 | -2.42 |
| `inflection` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.72 | -1.43 | -2.04 |
| `first_mover_leadership` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.22 | -1.51 | -2.82 |
| `deleveraging` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.38 | -1.55 | -0.41 |
| `rev_accel_margin` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.64 | -1.62 | -2.09 |
| `margin_mom` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.57 | -1.76 | -3.02 |
| `lottery_max_net_vol` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.22 | -1.76 | -2.05 |
| `pricing_power_unwatched` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.24 | -2.45 | -2.41 |

changed: 26 of 85; old counts {'CANNOT_DISTINGUISH': 68, 'FAILED_VARIANT': 9, 'NOT_DECIDABLE': 6, 'SURVIVES': 2}; new {'CANNOT_DISTINGUISH': 46, 'FAILED_VARIANT': 33, 'NOT_DECIDABLE': 6}

### Library board (headline rule)

| rule | old headline | new headline | old t (rule - twin21, full) | new t (fair twin, full) | net - market t in VALIDATE |
|---|---|---|---:|---:|---:|
| `gross_margin` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +1.80 | +3.03 | +0.72 |
| `mom_gp_lowvol` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +1.54 | +2.49 | +0.04 |
| `roe` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +1.03 | +2.41 | +0.43 |
| `blog01_roe_adv_annual_large` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +0.77 | +2.34 | +1.16 |
| `qp0025_small_annual` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +0.02 | +2.27 | +1.07 |
| `quality_momentum_gate` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +1.38 | +2.07 | -0.05 |
| `trend_quality` | CANNOT_DISTINGUISH | ALPHA_DETECTED | +1.56 | +2.07 | -0.82 |
| `frog_in_pan` | ALPHA_DETECTED | CANNOT_DISTINGUISH | +2.14 | +1.87 | -2.16 |
| `frog_secrel` | ALPHA_DETECTED | CANNOT_DISTINGUISH | +2.25 | +1.76 | -1.51 |
| `gh02_five_price_factors_ivw` | ALPHA_DETECTED | CANNOT_DISTINGUISH | +2.48 | +1.73 | -1.34 |
| `gp_at` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.10 | +1.42 | +0.24 |
| `vol_compression` | ALPHA_DETECTED | CANNOT_DISTINGUISH | +2.03 | +1.34 | -1.10 |
| `lowvol_63_large` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.16 | +1.30 | -0.63 |
| `co03_reversal_in_high_margin` | ALPHA_DETECTED | CANNOT_DISTINGUISH | +2.93 | +1.21 | -1.39 |
| `mom_in_calm` | ALPHA_DETECTED | CANNOT_DISTINGUISH | +2.34 | +1.07 | -0.29 |
| `lowvol_252_large` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.17 | +0.84 | -0.72 |
| `lowbeta_gp` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.45 | +0.70 | -1.07 |
| `lowbeta_large` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.21 | +0.56 | -1.11 |
| `lowvol_252` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.54 | +0.53 | -0.26 |
| `mom_6_1_q` | FAILED_VARIANT | CANNOT_DISTINGUISH | -0.02 | +0.07 | -0.51 |
| `hi52_q` | FAILED_VARIANT | CANNOT_DISTINGUISH | -1.64 | +0.03 | -1.80 |
| `mom_12_1` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.13 | -0.01 | -2.21 |
| `mom_12_1_ivw` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.74 | -0.01 | -2.21 |
| `mom_12_1_liqw` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.78 | -0.01 | -2.21 |
| `rev5_lowvol_large` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.06 | -0.09 | -1.44 |
| `gh11_skip_month_composite_q` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.75 | -0.17 | -2.27 |
| `px_vs_ma200` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.38 | -0.22 | -1.45 |
| `mom_12_1_trend` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.04 | -0.25 | -2.15 |
| `mom_12_1_small` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.10 | -0.27 | -2.07 |
| `rev_5d_large` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.25 | -0.31 | -1.59 |
| `gh04_rps_20_60_120` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.31 | -0.44 | -1.97 |
| `seasonality_hs_large` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.94 | -0.53 | -1.88 |
| `qc768_golden_cross_mega` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.01 | -0.63 | n/a |
| `industry_mom` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.15 | -0.84 | -2.76 |
| `resid_mom_63` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.46 | -1.03 | -1.52 |
| `mom_12_1_q_mjsd` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.36 | -1.09 | -2.29 |
| `gap_reversal` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.81 | -1.16 | -1.96 |
| `low_debt` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.23 | -1.18 | -2.27 |
| `small_not_illiquid_trend` | CANNOT_DISTINGUISH | FAILED_VARIANT | +1.10 | -1.22 | -2.01 |
| `small_not_illiquid` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.71 | -2.07 | -1.10 |
| `random_2` | CANNOT_DISTINGUISH | FAILED_VARIANT | +0.15 | -2.97 | -3.19 |

changed: 41 of 140; old {'CANNOT_DISTINGUISH': 74, 'FAILED_VARIANT': 54, 'ALPHA_DETECTED': 12}; new {'FAILED_VARIANT': 66, 'CANNOT_DISTINGUISH': 61, 'ALPHA_DETECTED': 13}

