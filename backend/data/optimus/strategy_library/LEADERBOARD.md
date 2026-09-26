# Strategy library leaderboard — 2026-09-26

> HINDSIGHT BACKTEST. Every rule was registered 2026-09-26, after every month in these tables; 'since 2020' is what the rule WOULD have done, not what Aegis did. The quotable record starts at registration and accrues in the lib_ forward books. Read by_year_signs, LOO-worst and the worst breadth cell BEFORE the CAGR column; read DSR before Sharpe.

## Multiplicity (read before any row)

- cells looked at: **834** (277 rules x breadth k=10/20/50 + own k); DSR computed at n=834 and, beside it, at the 31 families (n=31).
- expected best monthly active Sharpe of pure noise at n=834: 0.300 monthly (x3.46 annualised) on the analytic null; 0.491 if the null sd is the dispersion across these cells (printed as `dsr_null_from_library`, never ranked on: structurally negative rules inflate it).
- Harvey-Liu-Zhu bar: t >= 3.0 on horizon-wide blocks before a row is anything but a PRODUCT_EXPERIMENT observation.
- refused rules: 3; catalogue rows not reachable on this panel: 50 (named in `strategy_library.NOT_REACHABLE`).
- controls (never ranked, never trials): random_1, random_2, random_3, random_large

## The objective: sealed net return vs SPY (split declared in code)

- dev: entry <= 2023-12-31; SEALED: entry >= 2024-01-01 (32 monthly blocks); recent: last 6 completed monthly periods (~126 sessions). a period belongs to the window its ENTRY session (decision + 1 business day) is in.
- The sealed window is 32 monthly blocks (the brief assumed 21). 'Sealed' means the split was declared in code before this run, NOT that nobody has seen 2024-2026: every rule was written in 2026, and the 02:00 board printed full-sample numbers including it. Ranking 834 cells on 32 months selects luck as readily as skill -- read sealed_dsr (at n=834) and the dev column beside every sealed number.
- noise ceiling at n=834: best monthly active Sharpe of pure noise 0.300 over the full window, 0.575 over the sealed window (= 1.99 annual IR).
- expected pure-noise cells with an annual IR > 0.5: 51.4 on the full window, 175.8 on the sealed window.
- rules from strategy_library_ext: backend.services.strategy_library_ext (26 entries)

## Top 10 by SEALED net return vs SPY (the objective)

| id | family | k | sealed vs SPY | sealed CAGR (months) | SPY sealed | sealed DSR | dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_liqw | weighted | 20 | **+68.4%** | +89.4% (32) | +21.0% | 0.071 | +7.0% | -6.2% | 0.034 (834) | +0.67% | 0.91 | 5.8x | 73 | -70.6% | +85.6% (+12.4%) | `+--+---+++` |
| qc372_oversold_snapback_mega | reversal | 5 | **+59.4%** | +80.4% (32) | +21.0% | 0.172 | +12.2% | -1.0% | 0.072 (834) | +0.96% | 0.52 | 9.4x | 56 | -68.7% | +92.7% (+12.4%) | `+-++--++++` |
| rev_5d | reversal | 20 | **+48.4%** | +69.4% (32) | +21.0% | 0.156 | +2.8% | -10.3% | 0.005 (834) | +0.10% | 1.08 | 11.6x | 286 | -66.5% | +50.7% (+12.4%) | `-+-+---+++` |
| qc623_mom63_liquidity_weighted | momentum | 10 | **+46.3%** | +67.3% (32) | +21.0% | 0.035 | +12.2% | -1.0% | 0.026 (834) | +0.92% | 0.74 | 8.3x | 72 | -58.9% | +53.3% (+12.4%) | `---+---+++` |
| mom_12_1_q | momentum | 20 | **+37.9%** | +58.9% (32) | +21.0% | 0.057 | +34.2% | +21.1% | 0.202 (834) | +1.52% | 0.44 | 2.4x | 56 | -35.9% | +9.9% (+12.4%) | `-+++-+++++` |
| skill_mom | analyst_skill | 20 | **+37.0%** | +58.0% (32) | +21.0% | 0.102 | +17.9% | +4.7% | 0.101 (834) | +0.69% | 0.40 | 5.2x | 76 | -27.3% | +9.9% (+12.4%) | `-+++-+-+++` |
| margin_mom | combination | 20 | **+36.9%** | +57.9% (32) | +21.0% | 0.059 | +14.0% | +0.8% | 0.037 (834) | +0.33% | 0.58 | 5.1x | 111 | -51.0% | +16.0% (+12.4%) | `--++-+-+++` |
| qc395_sharpe252_above_trend_large | momentum | 10 | **+35.2%** | +56.2% (32) | +21.0% | 0.036 | +26.8% | +13.6% | 0.116 (834) | +1.10% | 0.48 | 5.0x | 47 | -32.6% | +13.1% (+12.4%) | `++-+-+-+++` |
| illiquid | size_liquidity | 20 | **+34.9%** | +55.9% (32) | +21.0% | 0.011 | -2.0% | -15.2% | 0.002 (834) | -0.25% | 1.44 | 8.0x | 277 | -80.7% | +59.0% (+12.4%) | `++-+---+++` |
| qc470_mom252_quarterly_riskparity | weighted | 20 | **+31.1%** | +52.1% (32) | +21.0% | 0.051 | +25.9% | +12.7% | 0.090 (834) | +1.03% | 0.51 | 2.7x | 62 | -47.7% | +6.6% (+12.4%) | `-+++--++++` |

## Bottom 10 by sealed net return vs SPY

| id | family | k | sealed vs SPY | sealed CAGR (months) | SPY sealed | sealed DSR | dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_in_laggard_sectors | sector_relative | 20 | **-29.3%** | -8.3% (32) | +21.0% | 0.000 | +2.0% | -11.2% | 0.000 (834) | -1.24% | n/a | 9.4x | 216 | -59.4% | -30.8% (+12.4%) | `---+------` |
| mom_6_1 | momentum | 20 | **-28.1%** | -7.1% (32) | +21.0% | 0.000 | +23.7% | +10.5% | 0.002 (834) | -1.11% | 1.29 | 5.9x | 145 | -66.1% | -8.5% (+12.4%) | `---+-+--+-` |
| raises_in_losers | flow_momentum | 20 | **-24.9%** | -3.9% (32) | +21.0% | 0.000 | +18.6% | +5.4% | 0.000 (834) | -0.43% | 0.75 | 9.5x | 121 | -24.7% | +4.0% (+12.4%) | `-+++--+---` |
| revenue_turn | fund_inflection | 20 | **-23.9%** | -2.9% (32) | +21.0% | 0.000 | +14.4% | +1.2% | 0.000 (834) | -0.75% | 1.08 | 2.3x | 54 | -40.5% | -1.8% (+12.4%) | `--++-+--+-` |
| raise_price_gap | lead_chase | 20 | **-23.3%** | -2.3% (32) | +21.0% | 0.000 | +18.0% | +4.9% | 0.001 (834) | -0.36% | 1.00 | 11.2x | 177 | -43.0% | +4.0% (+12.4%) | `++++-+----` |
| mom_in_calm_markets | regime_gated | 20 | **-22.8%** | -1.8% (32) | +21.0% | 0.000 | -0.9% | -14.0% | 0.000 (834) | -1.59% | n/a | 1.7x | 39 | -38.0% | -1.0% (+12.4%) | `-----+--+-` |
| mom_6m | momentum | 20 | **-22.8%** | -1.8% (32) | +21.0% | 0.000 | +23.9% | +10.7% | 0.003 (834) | -0.85% | 1.17 | 5.6x | 140 | -60.0% | -10.5% (+12.4%) | `---+-+--+-` |
| mom_rev | combination | 20 | **-22.0%** | -1.0% (32) | +21.0% | 0.000 | +18.9% | +5.7% | 0.002 (834) | -0.71% | 1.16 | 10.8x | 257 | -43.4% | -9.3% (+12.4%) | `+--+-+----` |
| low_dtc_gp | short_interest | 20 | **-21.9%** | -0.9% (32) | +21.0% | 0.000 | +21.1% | +8.0% | 0.001 (834) | -0.26% | 0.56 | 4.6x | 85 | -28.3% | +8.7% (+12.4%) | `+++++-----` |
| lead_raises_in_losers | lead_chase | 20 | **-21.5%** | -0.5% (32) | +21.0% | 0.000 | +14.5% | +1.3% | 0.000 (834) | -0.44% | 0.85 | 8.2x | 108 | -27.6% | +13.6% (+12.4%) | `++++------` |

## Controls on the sealed window (random k: the luck bar)

| id | family | k | sealed vs SPY | sealed CAGR (months) | SPY sealed | sealed DSR | dev CAGR | dev vs SPY | DSR full (n) | LOO-worst (mo) | top-5-mo share | turnover/yr | cost bps/yr | max DD | recent-126 (SPY) | by-year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random_1 | control | 20 | **-10.6%** | +10.4% (32) | +21.0% | 0.000 | +13.9% | +0.8% | 0.000 (834) | -0.36% | 0.69 | 11.9x | 274 | -29.9% | +25.4% (+12.4%) | `-+-+++---+` |
| random_2 | control | 20 | **-10.5%** | +10.5% (32) | +21.0% | 0.000 | +5.4% | -7.8% | 0.000 (834) | -0.70% | 1.01 | 11.9x | 269 | -38.1% | +4.7% (+12.4%) | `++-+-+----` |
| random_3 | control | 20 | **-2.1%** | +18.9% (32) | +21.0% | 0.001 | +5.9% | -7.3% | 0.000 (834) | -0.50% | 0.88 | 11.9x | 271 | -36.6% | +15.1% (+12.4%) | `---+-+--+-` |
| random_large | control | 20 | **-1.8%** | +19.2% (32) | +21.0% | 0.001 | +12.3% | -0.8% | 0.001 (834) | -0.19% | 0.53 | 11.6x | 112 | -27.4% | +20.6% (+12.4%) | `-+-+++--+-` |

## SPY

SPY since 2020-01-01: CAGR +15.7%, cumulative +162%, max DD -23.9% (79 months). Source `spy_tr_yf_adjclose` via learner.benchmark.

## Top 10 by deflated Sharpe

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_q | momentum | 20 | `-+++-+++++` | +1.52% (drop 2020) | 50: +32.8% | 0.44 / +22.0% (+15.3%) | 2.21 (39) | 1.04 (115) | 0.202 (834) | +49.7% | +15.7% | +1323% |
| mom_no_downgrades | revision_flow | 20 | `++++-++-++` | +1.02% (drop 2020) | 50: +27.0% | 0.51 / +17.1% (+15.3%) | 2.08 (115) | 0.92 (115) | 0.118 (834) | +35.8% | +15.7% | +648% |
| qc395_sharpe252_above_trend_large | momentum | 10 | `++-+-+-+++` | +1.10% (drop 2020) | 50: +26.2% | 0.48 / +17.4% (+15.3%) | 2.04 (115) | 0.94 (115) | 0.116 (834) | +44.2% | +15.7% | +1012% |
| net_raises | revision_flow | 20 | `++++--+-++` | +0.43% (drop 2020) | 50: +18.9% | 0.37 / +15.2% (+15.3%) | 2.00 (115) | 1.07 (115) | 0.113 (834) | +23.5% | +15.7% | +301% |
| skill_mom | analyst_skill | 20 | `-+++-+-+++` | +0.69% (drop 2020) | 50: +24.8% | 0.40 / +16.8% (+15.3%) | 1.90 (115) | 0.97 (115) | 0.101 (834) | +32.6% | +15.7% | +542% |
| mom_flow_ivw | weighted | 20 | `++-+-+-+++` | +0.53% (drop 2020) | 50: +19.6% | 0.38 / +16.6% (+15.3%) | 1.86 (115) | 0.99 (115) | 0.094 (834) | +30.1% | +15.7% | +464% |
| qc470_mom252_quarterly_riskparity | weighted | 20 | `-+++--++++` | +1.03% (drop 2020) | 50: +30.8% | 0.51 / +15.6% (+15.3%) | 1.74 (39) | 0.91 (115) | 0.090 (834) | +37.6% | +15.7% | +719% |
| mom_no_downgrades_small | revision_flow | 20 | `++++-++-++` | +0.65% (drop 2020) | 50: +21.8% | 0.43 / +16.6% (+15.3%) | 1.85 (115) | 0.93 (115) | 0.088 (834) | +29.6% | +15.7% | +451% |
| big_dv | size_liquidity | 20 | `+-++--++++` | +0.48% (drop 2020) | 50: +15.3% | 0.42 / +13.5% (+15.3%) | 1.87 (115) | 0.95 (115) | 0.087 (834) | +23.4% | +15.7% | +299% |
| eap_mom | earnings_event | 20 | `++-+-+++++` | +0.90% (drop 2020) | 50: +22.8% | 0.49 / +14.8% (+15.3%) | 1.84 (115) | 0.89 (115) | 0.085 (834) | +34.8% | +15.7% | +614% |

## Top 10 by hindsight CAGR since 2020

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mom_12_1_q | momentum | 20 | `-+++-+++++` | +1.52% (drop 2020) | 50: +32.8% | 0.44 / +22.0% (+15.3%) | 2.21 (39) | 1.04 (115) | 0.202 (834) | +49.7% | +15.7% | +1323% |
| px_vs_ma200_large | trend | 20 | `--++-+-++-` | +0.74% (drop 2020) | 50: +34.4% | 0.58 / +14.7% (+15.3%) | 1.80 (115) | 0.85 (115) | 0.031 (834) | +49.1% | +15.7% | +1290% |
| mom_6_1_large | momentum | 20 | `+--+-++++-` | +0.64% (drop 2020) | 50: +26.8% | 0.60 / +14.1% (+15.3%) | 1.80 (115) | 0.82 (115) | 0.032 (834) | +48.3% | +15.7% | +1240% |
| qc536_secneutral_multimom_large | sector_relative | 10 | `--++-+-++-` | +0.33% (drop 2020) | 50: +27.3% | 0.78 / +6.8% (+15.3%) | 1.25 (115) | 0.62 (115) | 0.001 (834) | +46.4% | +15.7% | +1128% |
| mom_low_ag | combination | 20 | `-+-+-+++++` | +0.81% (drop 2020) | 50: +30.0% | 0.64 / +10.9% (+15.3%) | 1.59 (115) | 0.82 (115) | 0.013 (834) | +45.8% | +15.7% | +1095% |
| qc395_sharpe252_above_trend_large | momentum | 10 | `++-+-+-+++` | +1.10% (drop 2020) | 50: +26.2% | 0.48 / +17.4% (+15.3%) | 2.04 (115) | 0.94 (115) | 0.116 (834) | +44.2% | +15.7% | +1012% |
| qc597_secneutral_multimom_calm | regime_gated | 10 | `--++-+-++-` | +0.43% (drop 2020) | 50: +20.2% | 0.81 / +5.5% (+15.3%) | 1.11 (115) | 0.60 (115) | 0.000 (834) | +43.9% | +15.7% | +996% |
| mom_12_1_liqw | weighted | 20 | `+--+---+++` | +0.67% (drop 2020) | 10: +28.6% | 0.91 / +2.2% (+15.3%) | 1.44 (115) | 0.66 (115) | 0.034 (834) | +42.6% | +15.7% | +936% |
| insider_mom | insider | 20 | `++++-++-+-` | +0.97% (drop 2020) | 50: +27.7% | 0.46 / +20.4% (+15.3%) | 2.16 (115) | 1.00 (115) | 0.051 (834) | +39.6% | +15.7% | +799% |
| qc629_multimom_above_trend_gated | regime_gated | 10 | `---+-+-++-` | -0.55% (drop 2020) | 50: +20.6% | 1.25 / -5.1% (+15.3%) | 0.89 (115) | 0.50 (115) | 0.001 (834) | +38.2% | +15.7% | +741% |

## Bottom 10

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lowvol_21 | low_risk | 20 | `----------` | -3.80% (drop 2024) | 10: -35.9% | n/a / -26.3% (+15.3%) | -7.37 (115) | -1.93 (115) | 0.000 (834) | -24.1% | +15.7% | -84% |
| low_max | low_risk | 20 | `----------` | -3.50% (drop 2017) | 10: -33.3% | n/a / -24.3% (+15.3%) | -7.40 (115) | -1.70 (115) | 0.000 (834) | -22.3% | +15.7% | -81% |
| lowvol_63 | low_risk | 20 | `----------` | -2.91% (drop 2018) | 10: -26.6% | n/a / -17.8% (+15.3%) | -6.20 (115) | -1.39 (115) | 0.000 (834) | -16.7% | +15.7% | -70% |
| lowvol_in_stress | regime_gated | 20 | `----------` | -2.80% (drop 2018) | 10: -24.6% | n/a / -16.8% (+15.3%) | -5.79 (115) | -1.46 (115) | 0.000 (834) | -16.6% | +15.7% | -70% |
| lowvol_63_q | low_risk | 20 | `----------` | -2.42% (drop 2018) | 10: -20.6% | n/a / -13.0% (+15.3%) | -6.38 (39) | -1.00 (115) | 0.000 (834) | -12.3% | +15.7% | -58% |
| vol_compression | low_risk | 20 | `+-------+-` | -2.70% (drop 2025) | 10: -24.6% | n/a / -18.3% (+15.3%) | -4.56 (115) | -0.44 (115) | 0.000 (834) | -12.2% | +15.7% | -57% |
| skew_high | low_risk | 20 | `+---------` | -2.01% (drop 2017) | 10: -24.4% | n/a / -14.5% (+15.3%) | -3.88 (115) | -0.27 (115) | 0.000 (834) | -11.5% | +15.7% | -55% |
| lowmax_mom | combination | 20 | `----------` | -2.49% (drop 2023) | 10: -18.3% | n/a / -17.1% (+15.3%) | -5.94 (115) | -0.67 (115) | 0.000 (834) | -11.1% | +15.7% | -54% |
| low_idio_63 | low_risk | 20 | `----------` | -2.37% (drop 2018) | 10: -23.6% | n/a / -13.3% (+15.3%) | -5.64 (115) | -0.81 (115) | 0.000 (834) | -10.2% | +15.7% | -51% |
| residmom_lowidio | combination | 20 | `-------++-` | -1.80% (drop 2025) | 10: -16.9% | n/a / -8.8% (+15.3%) | -4.59 (115) | -0.24 (115) | 0.000 (834) | -5.4% | +15.7% | -31% |

## Controls (random k — the bar a rule must clear by more than luck)

| id | family | k | by-year vs SPY | LOO-worst (mo, active) | worst cell (k: CAGR) | best-5-mo share / CAGR without them (SPY full) | t blocks | Sharpe (blocks) | DSR (n) | CAGR since 2020 | SPY CAGR | cum since 2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random_1 | control | 20 | `-+-+++---+` | -0.36% (drop 2020) | 50: +12.2% | 0.69 / +4.0% (+15.3%) | -0.17 (115) | 0.65 (115) | 0.000 (834) | +15.2% | +15.7% | +155% |
| random_2 | control | 20 | `++-+-+----` | -0.70% (drop 2020) | 10: +3.3% | 1.01 / -0.1% (+15.3%) | -1.81 (115) | 0.42 (115) | 0.000 (834) | +5.7% | +15.7% | +44% |
| random_3 | control | 20 | `---+-+--+-` | -0.50% (drop 2020) | 50: +8.1% | 0.88 / +1.1% (+15.3%) | -0.80 (115) | 0.50 (115) | 0.000 (834) | +12.1% | +15.7% | +113% |
| random_large | control | 20 | `-+-+++--+-` | -0.19% (drop 2025) | 50: +13.5% | 0.53 / +6.8% (+15.3%) | -0.04 (115) | 0.76 (115) | 0.001 (834) | +15.0% | +15.7% | +151% |

## Refused

- `attention_shock_fade`: FORWARD_ONLY: its input has no history on this panel; it accrues forward
- `fomo_reversal_21d`: FORWARD_ONLY: its input has no history on this panel; it accrues forward
- `fomo_reversal_5d`: FORWARD_ONLY: its input has no history on this panel; it accrues forward
