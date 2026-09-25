# Strategy library leaderboard — 2026-09-26

> HINDSIGHT BACKTEST. Every rule was registered 2026-09-26, after every month in these tables; 'since 2020' is what the rule WOULD have done, not what Aegis did. The quotable record starts at registration and accrues in the lib_ forward books. Read by_year_signs, LOO-worst and the worst breadth cell BEFORE the CAGR column; read DSR before Sharpe.

## Multiplicity (read before any row)

- cells looked at: **336** (112 rules x breadth k=10/20/50 + own k); DSR computed at n=336 and, beside it, at the 11 families (n=11).
- expected best monthly active Sharpe of pure noise at n=336: 0.275 monthly (x3.46 annualised) on the analytic null; 0.571 if the null sd is the dispersion across these cells (printed as `dsr_null_from_library`, never ranked on: structurally negative rules inflate it).
- Harvey-Liu-Zhu bar: t >= 3.0 on horizon-wide blocks before a row is anything but a PRODUCT_EXPERIMENT observation.
- refused rules: 0; catalogue rows not reachable on this panel: 67 (named in `strategy_library.NOT_REACHABLE`).
- controls (never ranked, never trials): random_1, random_2, random_3, random_large

## SPY

SPY since 2020-01-01: CAGR +15.7%, cumulative +162%, max DD -23.9% (79 months). Source `spy_tr_yf_adjclose` via learner.benchmark.

## Top 10 by deflated Sharpe

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_q | momentum | 20 | `-+++-+++++` | +1.52% (drop 2020) | 50: +32.8% | 0.44 / +22.0% (+15.3%) | 2.21 (39) | 1.04 (115) | 0.293 (336) | +49.7% | +15.7% | +1323% |
| mom_no_downgrades | revision_flow | 20 | `++++-++-++` | +1.02% (drop 2020) | 50: +27.0% | 0.51 / +17.1% (+15.3%) | 2.08 (115) | 0.92 (115) | 0.184 (336) | +35.8% | +15.7% | +648% |
| net_raises | revision_flow | 20 | `++++--+--+` | +0.38% (drop 2020) | 50: +18.5% | 0.38 / +14.5% (+15.3%) | 1.86 (115) | 1.05 (115) | 0.142 (336) | +22.1% | +15.7% | +273% |
| big_dv | size_liquidity | 20 | `+-++--++++` | +0.48% (drop 2020) | 50: +15.3% | 0.42 / +13.5% (+15.3%) | 1.87 (115) | 0.95 (115) | 0.140 (336) | +23.4% | +15.7% | +299% |
| mom_12_1 | momentum | 20 | `++++-+--++` | +0.88% (drop 2020) | 50: +29.8% | 0.54 / +14.6% (+15.3%) | 1.88 (115) | 0.87 (115) | 0.130 (336) | +36.9% | +15.7% | +692% |
| mom_12_1_small | momentum | 20 | `++++-++-++` | +0.63% (drop 2020) | 50: +22.0% | 0.45 / +15.9% (+15.3%) | 1.81 (115) | 0.92 (115) | 0.130 (336) | +28.3% | +15.7% | +417% |
| mom_flow | combination | 20 | `++-+-+-+++` | +0.48% (drop 2020) | 50: +21.6% | 0.41 / +15.5% (+15.3%) | 1.74 (115) | 0.94 (115) | 0.119 (336) | +29.3% | +15.7% | +441% |
| trend_quality | combination | 20 | `++-+-+-+-+` | +0.27% (drop 2020) | 50: +22.4% | 0.40 / +14.5% (+15.3%) | 1.79 (115) | 1.05 (115) | 0.116 (336) | +24.2% | +15.7% | +318% |
| frog_in_pan | momentum | 20 | `++-+-+++++` | +0.77% (drop 2023) | 50: +20.1% | 0.44 / +14.8% (+15.3%) | 1.72 (115) | 0.95 (115) | 0.107 (336) | +32.0% | +15.7% | +523% |
| inflection_flow | combination | 20 | `-+++-+--+-` | +0.28% (drop 2020) | 50: +18.8% | 0.40 / +14.1% (+15.3%) | 1.60 (115) | 1.01 (115) | 0.092 (336) | +25.1% | +15.7% | +337% |

## Top 10 by hindsight CAGR since 2020

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_q | momentum | 20 | `-+++-+++++` | +1.52% (drop 2020) | 50: +32.8% | 0.44 / +22.0% (+15.3%) | 2.21 (39) | 1.04 (115) | 0.293 (336) | +49.7% | +15.7% | +1323% |
| px_vs_ma200_large | trend | 20 | `--++-+-++-` | +0.74% (drop 2020) | 50: +34.4% | 0.58 / +14.7% (+15.3%) | 1.80 (115) | 0.85 (115) | 0.065 (336) | +49.1% | +15.7% | +1290% |
| mom_6_1_large | momentum | 20 | `+--+-++++-` | +0.64% (drop 2020) | 50: +26.8% | 0.60 / +14.1% (+15.3%) | 1.80 (115) | 0.82 (115) | 0.068 (336) | +48.3% | +15.7% | +1240% |
| mom_low_ag | combination | 20 | `-+-+-+++++` | +0.81% (drop 2020) | 50: +30.0% | 0.64 / +10.9% (+15.3%) | 1.59 (115) | 0.82 (115) | 0.032 (336) | +45.8% | +15.7% | +1095% |
| mom_12_1 | momentum | 20 | `++++-+--++` | +0.88% (drop 2020) | 50: +29.8% | 0.54 / +14.6% (+15.3%) | 1.88 (115) | 0.87 (115) | 0.130 (336) | +36.9% | +15.7% | +692% |
| mom_no_downgrades | revision_flow | 20 | `++++-++-++` | +1.02% (drop 2020) | 50: +27.0% | 0.51 / +17.1% (+15.3%) | 2.08 (115) | 0.92 (115) | 0.184 (336) | +35.8% | +15.7% | +648% |
| low_asset_growth_large | investment | 20 | `-+-+++--++` | +0.26% (drop 2020) | 50: +24.1% | 0.60 / +10.7% (+15.3%) | 1.39 (115) | 0.80 (115) | 0.004 (336) | +34.0% | +15.7% | +586% |
| low_asset_growth | investment | 20 | `---+-+-+++` | +0.62% (drop 2025) | 10: +27.4% | 0.58 / +10.0% (+15.3%) | 1.41 (115) | 0.82 (115) | 0.054 (336) | +33.5% | +15.7% | +570% |
| resid_mom_12_1_large | momentum | 20 | `---+-+-++-` | +0.33% (drop 2020) | 20: +33.4% | 0.70 / +7.2% (+15.3%) | 1.36 (115) | 0.72 (115) | 0.055 (336) | +33.4% | +15.7% | +568% |
| gp_low_ag | combination | 20 | `++-+-+++-+` | +0.19% (drop 2020) | 50: +24.0% | 0.63 / +9.9% (+15.3%) | 1.42 (115) | 0.79 (115) | 0.012 (336) | +33.0% | +15.7% | +553% |

## Bottom 10

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lowvol_21 | low_risk | 20 | `----------` | -3.80% (drop 2024) | 10: -35.9% | n/a / -26.3% (+15.3%) | -7.37 (115) | -1.93 (115) | 0.000 (336) | -24.1% | +15.7% | -84% |
| low_max | low_risk | 20 | `----------` | -3.50% (drop 2017) | 10: -33.3% | n/a / -24.3% (+15.3%) | -7.40 (115) | -1.70 (115) | 0.000 (336) | -22.3% | +15.7% | -81% |
| lowvol_63 | low_risk | 20 | `----------` | -2.91% (drop 2018) | 10: -26.6% | n/a / -17.8% (+15.3%) | -6.20 (115) | -1.39 (115) | 0.000 (336) | -16.7% | +15.7% | -70% |
| lowvol_63_q | low_risk | 20 | `----------` | -2.42% (drop 2018) | 10: -20.6% | n/a / -13.0% (+15.3%) | -6.38 (39) | -1.00 (115) | 0.000 (336) | -12.3% | +15.7% | -58% |
| vol_compression | low_risk | 20 | `+-------+-` | -2.70% (drop 2025) | 10: -24.6% | n/a / -18.3% (+15.3%) | -4.56 (115) | -0.44 (115) | 0.000 (336) | -12.2% | +15.7% | -57% |
| skew_high | low_risk | 20 | `+---------` | -2.01% (drop 2017) | 10: -24.4% | n/a / -14.5% (+15.3%) | -3.88 (115) | -0.27 (115) | 0.000 (336) | -11.5% | +15.7% | -55% |
| lowmax_mom | combination | 20 | `----------` | -2.49% (drop 2023) | 10: -18.3% | n/a / -17.1% (+15.3%) | -5.94 (115) | -0.67 (115) | 0.000 (336) | -11.1% | +15.7% | -54% |
| low_idio_63 | low_risk | 20 | `----------` | -2.37% (drop 2018) | 10: -23.6% | n/a / -13.3% (+15.3%) | -5.64 (115) | -0.81 (115) | 0.000 (336) | -10.2% | +15.7% | -51% |
| residmom_lowidio | combination | 20 | `-------++-` | -1.80% (drop 2025) | 10: -16.9% | n/a / -8.8% (+15.3%) | -4.59 (115) | -0.24 (115) | 0.000 (336) | -5.4% | +15.7% | -31% |
| hi52 | momentum | 20 | `--------+-` | -1.78% (drop 2025) | 10: -13.5% | n/a / -8.6% (+15.3%) | -3.97 (115) | -0.24 (115) | 0.000 (336) | -5.3% | +15.7% | -30% |

## Controls (random k — the bar a rule must clear by more than luck)

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random_1 | control | 20 | `-+-+++---+` | -0.36% (drop 2020) | 50: +12.2% | 0.69 / +4.0% (+15.3%) | -0.17 (115) | 0.65 (115) | 0.001 (336) | +15.2% | +15.7% | +155% |
| random_2 | control | 20 | `++-+-+----` | -0.70% (drop 2020) | 10: +3.3% | 1.01 / -0.1% (+15.3%) | -1.81 (115) | 0.42 (115) | 0.000 (336) | +5.7% | +15.7% | +44% |
| random_3 | control | 20 | `---+-+--+-` | -0.50% (drop 2020) | 50: +8.1% | 0.88 / +1.1% (+15.3%) | -0.80 (115) | 0.50 (115) | 0.000 (336) | +12.1% | +15.7% | +113% |
| random_large | control | 20 | `-+-+++--+-` | -0.19% (drop 2025) | 50: +13.5% | 0.53 / +6.8% (+15.3%) | -0.04 (115) | 0.76 (115) | 0.002 (336) | +15.0% | +15.7% | +151% |

## Forward books frozen tonight

- `mom_12_1_q`: ALREADY_HAS_A_FORWARD_BOOK 
- `mom_no_downgrades`: ALREADY_HAS_A_FORWARD_BOOK 
- `net_raises`: ALREADY_HAS_A_FORWARD_BOOK 
- `big_dv`: ALREADY_HAS_A_FORWARD_BOOK 
- `mom_12_1`: ALREADY_HAS_A_FORWARD_BOOK 
- `mom_12_1_small`: ALREADY_HAS_A_FORWARD_BOOK 
- `mom_flow`: ALREADY_HAS_A_FORWARD_BOOK 
- `trend_quality`: ALREADY_HAS_A_FORWARD_BOOK 
- `frog_in_pan`: ALREADY_HAS_A_FORWARD_BOOK 
- `inflection_flow`: ALREADY_HAS_A_FORWARD_BOOK 
- `forecast_dispersion_v1`: ALREADY_HAS_A_FORWARD_BOOK 
- `book_f_seasonality_11_20_v0`: ALREADY_HAS_A_FORWARD_BOOK 

## Backtest vs forward

- lib_mom_12_1_q_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+2.23% (hindsight); forward sessions=None
- lib_mom_no_downgrades_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+2.00% (hindsight); forward sessions=None
- lib_net_raises_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+0.67% (hindsight); forward sessions=None
- lib_big_dv_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+0.73% (hindsight); forward sessions=None
- lib_mom_12_1_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+1.82% (hindsight); forward sessions=None
- lib_mom_12_1_small_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+1.36% (hindsight); forward sessions=None
- lib_mom_flow_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+1.03% (hindsight); forward sessions=None
- lib_trend_quality_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+0.73% (hindsight); forward sessions=None
- lib_frog_in_pan_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+1.08% (hindsight); forward sessions=None
- lib_inflection_flow_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=+0.69% (hindsight); forward sessions=None
- lib_forecast_dispersion_v1_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=n/a (hindsight); forward sessions=None
- lib_book_f_seasonality_11_20_v0_2026-09-26: forward_21d_vs_spy=PENDING (no session has opened since it was frozen); backtest_mean_21d_vs_spy=n/a (hindsight); forward sessions=None
