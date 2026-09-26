# Strategy library leaderboard — 2026-09-26

> HINDSIGHT BACKTEST. Every rule was registered 2026-09-26, after every month in these tables; 'since 2020' is what the rule WOULD have done, not what Aegis did. The quotable record starts at registration and accrues in the lib_ forward books. Read by_year_signs, LOO-worst and the worst breadth cell BEFORE the CAGR column; read DSR before Sharpe.

## Multiplicity (read before any row)

- cells looked at: **762** (254 rules x breadth k=10/20/50 + own k); DSR computed at n=762 and, beside it, at the 26 families (n=26).
- expected best monthly active Sharpe of pure noise at n=762: 0.298 monthly (x3.46 annualised) on the analytic null; 0.492 if the null sd is the dispersion across these cells (printed as `dsr_null_from_library`, never ranked on: structurally negative rules inflate it).
- Harvey-Liu-Zhu bar: t >= 3.0 on horizon-wide blocks before a row is anything but a PRODUCT_EXPERIMENT observation.
- refused rules: 0; catalogue rows not reachable on this panel: 50 (named in `strategy_library.NOT_REACHABLE`).
- controls (never ranked, never trials): random_1, random_2, random_3, random_large

## The objective: sealed net return vs SPY (split declared in code)

- dev: entry <= 2023-12-31; SEALED: entry >= 2024-01-01 (32 monthly blocks); recent: last 6 completed monthly periods (~126 sessions). a period belongs to the window its ENTRY session (decision + 1 business day) is in.
- The sealed window is 32 monthly blocks (the brief assumed 21). 'Sealed' means the split was declared in code before this run, NOT that nobody has seen 2024-2026: every rule was written in 2026, and the 02:00 board printed full-sample numbers including it. Ranking 762 cells on 32 months selects luck as readily as skill -- read sealed_dsr (at n=762) and the dev column beside every sealed number.
- noise ceiling at n=762: best monthly active Sharpe of pure noise 0.298 over the full window, 0.571 over the sealed window (= 1.98 annual IR).
- expected pure-noise cells with an annual IR > 0.5: 47.0 on the full window, 160.6 on the sealed window.
- rules from strategy_library_ext: absent (backend/services/strategy_library_ext.py does not exist)

## Top 10 by SEALED net return vs SPY (the objective)

| id | family | k | sealed vs SPY | sealed CAGR (months) | SPY sealed | sealed DSR | dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_liqw | weighted | 20 | **+68.4%** | +89.4% (32) | +21.0% | 0.075 | +7.0% | -6.2% | 0.036 (762) | +0.67% | 0.91 | 5.8x | 73 | -70.6% | +85.6% (+12.4%) | `+--+---+++` |
| rev_5d | reversal | 20 | **+48.4%** | +69.4% (32) | +21.0% | 0.163 | +2.8% | -10.3% | 0.006 (762) | +0.10% | 1.08 | 11.6x | 286 | -66.5% | +50.7% (+12.4%) | `-+-+---+++` |
| mom_12_1_q | momentum | 20 | **+37.9%** | +58.9% (32) | +21.0% | 0.060 | +34.2% | +21.1% | 0.209 (762) | +1.52% | 0.44 | 2.4x | 56 | -35.9% | +9.9% (+12.4%) | `-+++-+++++` |
| skill_mom | analyst_skill | 20 | **+37.0%** | +58.0% (32) | +21.0% | 0.106 | +17.9% | +4.7% | 0.105 (762) | +0.69% | 0.40 | 5.2x | 76 | -27.3% | +9.9% (+12.4%) | `-+++-+-+++` |
| margin_mom | combination | 20 | **+36.9%** | +57.9% (32) | +21.0% | 0.062 | +14.0% | +0.8% | 0.039 (762) | +0.33% | 0.58 | 5.1x | 111 | -51.0% | +16.0% (+12.4%) | `--++-+-+++` |
| illiquid | size_liquidity | 20 | **+34.9%** | +55.9% (32) | +21.0% | 0.012 | -2.0% | -15.2% | 0.002 (762) | -0.25% | 1.44 | 8.0x | 277 | -80.7% | +59.0% (+12.4%) | `++-+---+++` |
| low_dtc_mom | short_interest | 20 | **+26.2%** | +47.2% (32) | +21.0% | 0.070 | +6.0% | -7.2% | 0.004 (762) | -0.04% | 0.59 | 6.3x | 148 | -38.4% | -6.6% (+12.4%) | `---+-++++-` |
| low_asset_growth | investment | 20 | **+26.0%** | +47.0% (32) | +21.0% | 0.021 | +16.7% | +3.5% | 0.031 (762) | +0.62% | 0.58 | 2.6x | 67 | -34.4% | +14.2% (+12.4%) | `---+-+-+++` |
| resid_mom_12_1_large | momentum | 20 | **+24.5%** | +45.5% (32) | +21.0% | 0.019 | +17.3% | +4.1% | 0.032 (762) | +0.33% | 0.70 | 3.7x | 35 | -45.3% | +3.7% (+12.4%) | `---+-+-++-` |
| mom_12_1_secrel | sector_relative | 20 | **+24.1%** | +45.1% (32) | +21.0% | 0.023 | +17.1% | +4.0% | 0.025 (762) | +0.32% | 0.64 | 4.9x | 117 | -48.1% | +11.5% (+12.4%) | `-+++---+++` |

## Bottom 10 by sealed net return vs SPY

| id | family | k | sealed vs SPY | sealed CAGR (months) | SPY sealed | sealed DSR | dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_in_laggard_sectors | sector_relative | 20 | **-29.3%** | -8.3% (32) | +21.0% | 0.000 | +2.0% | -11.2% | 0.000 (762) | -1.24% | n/a | 9.4x | 216 | -59.4% | -30.8% (+12.4%) | `---+------` |
| mom_6_1 | momentum | 20 | **-28.1%** | -7.1% (32) | +21.0% | 0.000 | +23.7% | +10.5% | 0.002 (762) | -1.11% | 1.29 | 5.9x | 145 | -66.1% | -8.5% (+12.4%) | `---+-+--+-` |
| raises_in_losers | flow_momentum | 20 | **-24.9%** | -3.9% (32) | +21.0% | 0.000 | +18.6% | +5.4% | 0.000 (762) | -0.43% | 0.75 | 9.5x | 121 | -24.7% | +4.0% (+12.4%) | `-+++--+---` |
| revenue_turn | fund_inflection | 20 | **-23.9%** | -2.9% (32) | +21.0% | 0.000 | +14.4% | +1.2% | 0.000 (762) | -0.75% | 1.08 | 2.3x | 54 | -40.5% | -1.8% (+12.4%) | `--++-+--+-` |
| raise_price_gap | lead_chase | 20 | **-23.3%** | -2.3% (32) | +21.0% | 0.000 | +18.0% | +4.9% | 0.001 (762) | -0.36% | 1.00 | 11.2x | 177 | -43.0% | +4.0% (+12.4%) | `++++-+----` |
| mom_in_calm_markets | regime_gated | 20 | **-22.8%** | -1.8% (32) | +21.0% | 0.000 | -0.9% | -14.0% | 0.000 (762) | -1.59% | n/a | 1.7x | 39 | -38.0% | -1.0% (+12.4%) | `-----+--+-` |
| mom_6m | momentum | 20 | **-22.8%** | -1.8% (32) | +21.0% | 0.000 | +23.9% | +10.7% | 0.003 (762) | -0.85% | 1.17 | 5.6x | 140 | -60.0% | -10.5% (+12.4%) | `---+-+--+-` |
| mom_rev | combination | 20 | **-22.0%** | -1.0% (32) | +21.0% | 0.000 | +18.9% | +5.7% | 0.002 (762) | -0.71% | 1.16 | 10.8x | 257 | -43.4% | -9.3% (+12.4%) | `+--+-+----` |
| low_dtc_gp | short_interest | 20 | **-21.9%** | -0.9% (32) | +21.0% | 0.000 | +21.1% | +8.0% | 0.001 (762) | -0.26% | 0.56 | 4.6x | 85 | -28.3% | +8.7% (+12.4%) | `+++++-----` |
| lead_raises_in_losers | lead_chase | 20 | **-21.5%** | -0.5% (32) | +21.0% | 0.000 | +14.5% | +1.3% | 0.000 (762) | -0.44% | 0.85 | 8.2x | 108 | -27.6% | +13.6% (+12.4%) | `++++------` |

## Controls on the sealed window (random k: the luck bar)

| id | family | k | sealed vs SPY | sealed CAGR (months) | SPY sealed | sealed DSR | dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random_1 | control | 20 | **-10.6%** | +10.4% (32) | +21.0% | 0.000 | +13.9% | +0.8% | 0.000 (762) | -0.36% | 0.69 | 11.9x | 274 | -29.9% | +25.4% (+12.4%) | `-+-+++---+` |
| random_2 | control | 20 | **-10.5%** | +10.5% (32) | +21.0% | 0.000 | +5.4% | -7.8% | 0.000 (762) | -0.70% | 1.01 | 11.9x | 269 | -38.1% | +4.7% (+12.4%) | `++-+-+----` |
| random_3 | control | 20 | **-2.1%** | +18.9% (32) | +21.0% | 0.001 | +5.9% | -7.3% | 0.000 (762) | -0.50% | 0.88 | 11.9x | 271 | -36.6% | +15.1% (+12.4%) | `---+-+--+-` |
| random_large | control | 20 | **-1.8%** | +19.2% (32) | +21.0% | 0.001 | +12.3% | -0.8% | 0.001 (762) | -0.19% | 0.53 | 11.6x | 112 | -27.4% | +20.6% (+12.4%) | `-+-+++--+-` |

## SPY

SPY since 2020-01-01: CAGR +15.7%, cumulative +162%, max DD -23.9% (79 months). Source `spy_tr_yf_adjclose` via learner.benchmark.

## Top 10 by deflated Sharpe

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_q | momentum | 20 | `-+++-+++++` | +1.52% (drop 2020) | 50: +32.8% | 0.44 / +22.0% (+15.3%) | 2.21 (39) | 1.04 (115) | 0.209 (762) | +49.7% | +15.7% | +1323% |
| mom_no_downgrades | revision_flow | 20 | `++++-++-++` | +1.02% (drop 2020) | 50: +27.0% | 0.51 / +17.1% (+15.3%) | 2.08 (115) | 0.92 (115) | 0.123 (762) | +35.8% | +15.7% | +648% |
| net_raises | revision_flow | 20 | `++++--+-++` | +0.43% (drop 2020) | 50: +18.9% | 0.37 / +15.2% (+15.3%) | 2.00 (115) | 1.07 (115) | 0.118 (762) | +23.5% | +15.7% | +301% |
| skill_mom | analyst_skill | 20 | `-+++-+-+++` | +0.69% (drop 2020) | 50: +24.8% | 0.40 / +16.8% (+15.3%) | 1.90 (115) | 0.97 (115) | 0.105 (762) | +32.6% | +15.7% | +542% |
| mom_flow_ivw | weighted | 20 | `++-+-+-+++` | +0.53% (drop 2020) | 50: +19.6% | 0.38 / +16.6% (+15.3%) | 1.86 (115) | 0.99 (115) | 0.099 (762) | +30.1% | +15.7% | +464% |
| mom_no_downgrades_small | revision_flow | 20 | `++++-++-++` | +0.65% (drop 2020) | 50: +21.8% | 0.43 / +16.6% (+15.3%) | 1.85 (115) | 0.93 (115) | 0.092 (762) | +29.6% | +15.7% | +451% |
| big_dv | size_liquidity | 20 | `+-++--++++` | +0.48% (drop 2020) | 50: +15.3% | 0.42 / +13.5% (+15.3%) | 1.87 (115) | 0.95 (115) | 0.092 (762) | +23.4% | +15.7% | +299% |
| eap_mom | earnings_event | 20 | `++-+-+++++` | +0.90% (drop 2020) | 50: +22.8% | 0.49 / +14.8% (+15.3%) | 1.84 (115) | 0.89 (115) | 0.089 (762) | +34.8% | +15.7% | +614% |
| mom_12_1_ivw | weighted | 20 | `-+-+--++++` | +0.85% (drop 2020) | 50: +30.6% | 0.51 / +15.6% (+15.3%) | 1.90 (115) | 0.90 (115) | 0.086 (762) | +38.1% | +15.7% | +736% |
| mom_12_1_small | momentum | 20 | `++++-++-++` | +0.63% (drop 2020) | 50: +22.0% | 0.45 / +15.9% (+15.3%) | 1.81 (115) | 0.92 (115) | 0.085 (762) | +28.3% | +15.7% | +417% |

## Top 10 by hindsight CAGR since 2020

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_q | momentum | 20 | `-+++-+++++` | +1.52% (drop 2020) | 50: +32.8% | 0.44 / +22.0% (+15.3%) | 2.21 (39) | 1.04 (115) | 0.209 (762) | +49.7% | +15.7% | +1323% |
| px_vs_ma200_large | trend | 20 | `--++-+-++-` | +0.74% (drop 2020) | 50: +34.4% | 0.58 / +14.7% (+15.3%) | 1.80 (115) | 0.85 (115) | 0.033 (762) | +49.1% | +15.7% | +1290% |
| mom_6_1_large | momentum | 20 | `+--+-++++-` | +0.64% (drop 2020) | 50: +26.8% | 0.60 / +14.1% (+15.3%) | 1.80 (115) | 0.82 (115) | 0.035 (762) | +48.3% | +15.7% | +1240% |
| mom_low_ag | combination | 20 | `-+-+-+++++` | +0.81% (drop 2020) | 50: +30.0% | 0.64 / +10.9% (+15.3%) | 1.59 (115) | 0.82 (115) | 0.014 (762) | +45.8% | +15.7% | +1095% |
| mom_12_1_liqw | weighted | 20 | `+--+---+++` | +0.67% (drop 2020) | 10: +28.6% | 0.91 / +2.2% (+15.3%) | 1.44 (115) | 0.66 (115) | 0.036 (762) | +42.6% | +15.7% | +936% |
| insider_mom | insider | 20 | `++++-++-+-` | +0.97% (drop 2020) | 50: +27.7% | 0.46 / +20.4% (+15.3%) | 2.16 (115) | 1.00 (115) | 0.055 (762) | +39.6% | +15.7% | +799% |
| mom_12_1_ivw | weighted | 20 | `-+-+--++++` | +0.85% (drop 2020) | 50: +30.6% | 0.51 / +15.6% (+15.3%) | 1.90 (115) | 0.90 (115) | 0.086 (762) | +38.1% | +15.7% | +736% |
| mom_12_1 | momentum | 20 | `++++-+--++` | +0.88% (drop 2020) | 50: +29.6% | 0.54 / +14.6% (+15.3%) | 1.88 (115) | 0.87 (115) | 0.083 (762) | +36.9% | +15.7% | +692% |
| mom_no_downgrades | revision_flow | 20 | `++++-++-++` | +1.02% (drop 2020) | 50: +27.0% | 0.51 / +17.1% (+15.3%) | 2.08 (115) | 0.92 (115) | 0.123 (762) | +35.8% | +15.7% | +648% |
| mom_12_1_q_trend | regime_gated | 20 | `-+-+-+++++` | +0.59% (drop 2020) | 50: +22.8% | 0.61 / +10.8% (+15.3%) | 1.30 (39) | 0.86 (115) | 0.030 (762) | +35.8% | +15.7% | +648% |

## Bottom 10

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lowvol_21 | low_risk | 20 | `----------` | -3.80% (drop 2024) | 10: -35.9% | n/a / -26.3% (+15.3%) | -7.37 (115) | -1.93 (115) | 0.000 (762) | -24.1% | +15.7% | -84% |
| low_max | low_risk | 20 | `----------` | -3.50% (drop 2017) | 10: -33.3% | n/a / -24.3% (+15.3%) | -7.40 (115) | -1.70 (115) | 0.000 (762) | -22.3% | +15.7% | -81% |
| lowvol_63 | low_risk | 20 | `----------` | -2.91% (drop 2018) | 10: -26.6% | n/a / -17.8% (+15.3%) | -6.20 (115) | -1.39 (115) | 0.000 (762) | -16.7% | +15.7% | -70% |
| lowvol_in_stress | regime_gated | 20 | `----------` | -2.80% (drop 2018) | 10: -24.6% | n/a / -16.8% (+15.3%) | -5.79 (115) | -1.46 (115) | 0.000 (762) | -16.6% | +15.7% | -70% |
| lowvol_63_q | low_risk | 20 | `----------` | -2.42% (drop 2018) | 10: -20.6% | n/a / -13.0% (+15.3%) | -6.38 (39) | -1.00 (115) | 0.000 (762) | -12.3% | +15.7% | -58% |
| vol_compression | low_risk | 20 | `+-------+-` | -2.70% (drop 2025) | 10: -24.6% | n/a / -18.3% (+15.3%) | -4.56 (115) | -0.44 (115) | 0.000 (762) | -12.2% | +15.7% | -57% |
| skew_high | low_risk | 20 | `+---------` | -2.01% (drop 2017) | 10: -24.4% | n/a / -14.5% (+15.3%) | -3.88 (115) | -0.27 (115) | 0.000 (762) | -11.5% | +15.7% | -55% |
| lowmax_mom | combination | 20 | `----------` | -2.49% (drop 2023) | 10: -18.3% | n/a / -17.1% (+15.3%) | -5.94 (115) | -0.67 (115) | 0.000 (762) | -11.1% | +15.7% | -54% |
| low_idio_63 | low_risk | 20 | `----------` | -2.37% (drop 2018) | 10: -23.6% | n/a / -13.3% (+15.3%) | -5.64 (115) | -0.81 (115) | 0.000 (762) | -10.2% | +15.7% | -51% |
| residmom_lowidio | combination | 20 | `-------++-` | -1.80% (drop 2025) | 10: -16.9% | n/a / -8.8% (+15.3%) | -4.59 (115) | -0.24 (115) | 0.000 (762) | -5.4% | +15.7% | -31% |

## Controls (random k — the bar a rule must clear by more than luck)

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random_1 | control | 20 | `-+-+++---+` | -0.36% (drop 2020) | 50: +12.2% | 0.69 / +4.0% (+15.3%) | -0.17 (115) | 0.65 (115) | 0.000 (762) | +15.2% | +15.7% | +155% |
| random_2 | control | 20 | `++-+-+----` | -0.70% (drop 2020) | 10: +3.3% | 1.01 / -0.1% (+15.3%) | -1.81 (115) | 0.42 (115) | 0.000 (762) | +5.7% | +15.7% | +44% |
| random_3 | control | 20 | `---+-+--+-` | -0.50% (drop 2020) | 50: +8.1% | 0.88 / +1.1% (+15.3%) | -0.80 (115) | 0.50 (115) | 0.000 (762) | +12.1% | +15.7% | +113% |
| random_large | control | 20 | `-+-+++--+-` | -0.19% (drop 2025) | 50: +13.5% | 0.53 / +6.8% (+15.3%) | -0.04 (115) | 0.76 (115) | 0.001 (762) | +15.0% | +15.7% | +151% |
