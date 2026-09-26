# Fast movers -- 2026-09-26

Receipt: `fast_movers_2026-09-26.json`. Rules: `backend/services/fast_mover_forensics.py`. State at entry uses only rows stamped <= entry; the ex-post catalyst is a separate column. Credit requires beating the median of 3 matched controls by >= 1 sigma_h AND the mechanism visible at entry AND the reason it was held.

## What the counts can and cannot say

Cases were selected on the size of the move (|move| >= 5% or >= 2 sigma), so beating a 3-name control median by 1 sigma_h is close to guaranteed by that selection; the earlier count of favourable cases that 'beat their controls' is withdrawn as uninformative. No book is credited: the credit rule needs a selection reason mapped to a mechanism, which momentum/abstention books and twins do not record. What the receipt can say is narrower -- on 82 favourable cases (45 ticker-entries) at least one strategy-library rule held the name at its last rebalance before entry (SELECTABLE_BY_RULE): the machine could have had them, which is factor selection, not a stock call. The informative denominator is all 895 priced positions, and a book's move is read in its own ex-ante sigma (below) before any per-name story.

## Counts

```
{
 "n_cases": 318,
 "n_unique_ticker_entries": 203,
 "class_counts": {
  "OTHER": 135,
  "UNFORESEEABLE_NEWS": 36,
  "SELECTABLE_BY_RULE": 82,
  "SECTOR_BETA": 22,
  "ATTENTION_REFLEXIVITY": 25,
  "ANALYST_CASCADE": 12,
  "PRODUCT_DEMAND": 5,
  "RIGHT_STOCK_WRONG_REASON": 1
 },
 "credit_counts": {
  "none": 108,
  "n/a": 210
 },
 "favourable": 108,
 "adverse": 210,
 "favourable_selectable_by_rule": 82,
 "favourable_unique_ticker_entries_selectable": 45,
 "credited": 0,
 "n_positions_priced": 895,
 "news_pre_entry_archive_rows_excluded": 1008,
 "forecasts_expired_at_entry_excluded": 4687,
 "predicted": 53,
 "coverage_by_family": {
  "night_books_twin": {
   "positions": 336,
   "priced": 336,
   "unpriced": {},
   "cases": 129
  },
  "night_books": {
   "positions": 22,
   "priced": 22,
   "unpriced": {},
   "cases": 20
  },
  "website_lane_localdb": {
   "positions": 665,
   "priced": 439,
   "unpriced": {
    "symbol absent from the bars panel": 226
   },
   "cases": 111
  },
  "pc_paper": {
   "positions": 11,
   "priced": 0,
   "unpriced": {
    "no session after entry in the panel": 10,
    "entry outside the panel's sessions": 1
   },
   "cases": 0
  },
  "conviction_log": {
   "positions": 12,
   "priced": 11,
   "unpriced": {
    "symbol absent from the bars panel": 1
   },
   "cases": 9
  },
  "alpaca_fleet": {
   "positions": 89,
   "priced": 87,
   "unpriced": {
    "symbol absent from the bars panel": 1,
    "no session after entry in the panel": 1
   },
   "cases": 49
  }
 },
 "candidate_features": []
}
```

## Corpus archive quarantine (graded at read time)

Rule: pit_grade = 'archive' when first_seen_utc - published_utc > 30 days; graded at read time (backend.services.news_registry.grade_row), corpus files untouched. Receipt: `news_corpus/_receipts/archive_quarantine_2026-09-26.json`. Excluded from every state-at-entry and 'visible at entry' count; an expired forecast (resolves_after < entry) is never visible.

| source | rows | archive | share |
|---|---:|---:|---:|
| alpaca_benzinga_news | 36,720 | 36,720 | 100.0% |
| yfinance_ticker_news | 9,573 | 3,043 | 31.8% |
| reddit_securityanalysis_rss | 60 | 5 | 8.3% |

## Book moves in book-sigma (realised sigma_63 and correlation at entry)

Every 'N%' book move is printed beside the book's own sigma over the same sessions, from the names' 63-session sigmas and their realised pairwise correlation (not an assumed rho).

| book | title | twin | entry S | line |
|---|---|---|---|---|
| book:3b3e7049e693c3e4 * | Always invested — Book D's primary comparator (the gate disabled) |  | 2026-09-11 | h=1: -5.7% = -0.95 book-sigma (sigma_h 6.0%); h=5: +1.6% = +0.12 book-sigma (sigma_h 13.3%); h=6: +12.4% = +0.85 book-sigma (sigma_h 14.6%); h=to_date: +12.4% = +0.85 book-sigma (sigma_h 14.6%)  [sigma_1 5.96%, 5 names, realised mean pair corr 0.44 over 63 sessions] |
| book:8dbbb73b6159d61d * | 12-1 momentum, k=12, equal weight, monthly |  | 2026-09-11 | h=1: -2.2% = -0.58 book-sigma (sigma_h 3.9%); h=5: +2.5% = +0.29 book-sigma (sigma_h 8.6%); h=6: +4.9% = +0.52 book-sigma (sigma_h 9.5%); h=to_date: +4.9% = +0.52 book-sigma (sigma_h 9.5%)  [sigma_1 3.86%, 12 names, realised mean pair corr 0.36 over 63 sessions] |
| book:b109c8861c43e3c6 * | Cash/index by default; deviate only above a confidence threshold |  | 2026-09-11 | h=1: -5.7% = -0.95 book-sigma (sigma_h 6.0%); h=5: +1.6% = +0.12 book-sigma (sigma_h 13.3%); h=6: +12.4% = +0.85 book-sigma (sigma_h 14.6%); h=to_date: +12.4% = +0.85 book-sigma (sigma_h 14.6%)  [sigma_1 5.96%, 5 names, realised mean pair corr 0.44 over 63 sessions] |
| book:000b263cf7ec2286 | Good-news names in the top overhang tercile, long-only (Frazzini 2006 / Grinblatt-Han 2005) — random_universe twin | yes | 2026-09-11 | h=1: -0.6% = -0.58 book-sigma (sigma_h 1.0%); h=5: -2.4% = -1.11 book-sigma (sigma_h 2.2%); h=6: -2.4% = -1.01 book-sigma (sigma_h 2.4%); h=to_date: -2.4% = -1.01 book-sigma (sigma_h 2.4%)  [sigma_1 0.98%, 30 names, realised mean pair corr 0.10 over 63 sessions] |
| book:0b4039242299f2e0 | Always invested — Book D's primary comparator (the gate disabled) — random_universe twin | yes | 2026-09-11 | h=1: +0.2% = +0.06 book-sigma (sigma_h 2.6%); h=5: +2.3% = +0.40 book-sigma (sigma_h 5.9%); h=6: +8.7% = +1.34 book-sigma (sigma_h 6.5%); h=to_date: +8.7% = +1.34 book-sigma (sigma_h 6.5%)  [sigma_1 2.65%, 5 names, realised mean pair corr 0.17 over 63 sessions] |
| book:1dc244805b119552 | Insider cluster buys, 4-5 day clusters, long-only (Kang-Kim-Wang / Alldredge-Blank) — random_universe twin | yes | 2026-09-11 | h=1: -0.9% = -0.92 book-sigma (sigma_h 1.0%); h=5: -1.4% = -0.60 book-sigma (sigma_h 2.3%); h=6: -1.0% = -0.39 book-sigma (sigma_h 2.5%); h=to_date: -1.0% = -0.39 book-sigma (sigma_h 2.5%)  [sigma_1 1.01%, 40 names, realised mean pair corr 0.06 over 63 sessions] |
| book:1ece648f7410da8e | Always invested — Book D's primary comparator (the gate disabled) — beta_matched twin | yes | 2026-09-11 | h=1: -1.8% = -0.97 book-sigma (sigma_h 1.8%); h=5: +0.5% = +0.12 book-sigma (sigma_h 4.1%); h=6: +3.2% = +0.71 book-sigma (sigma_h 4.5%); h=to_date: +3.2% = +0.71 book-sigma (sigma_h 4.5%)  [sigma_1 1.84%, 5 names, realised mean pair corr 0.15 over 63 sessions] |
| book:2c0eb59f611b009c | Cash/index by default; deviate only above a confidence threshold — beta_matched twin | yes | 2026-09-11 | h=1: -0.4% = -0.58 book-sigma (sigma_h 0.8%); h=5: -0.1% = -0.05 book-sigma (sigma_h 1.7%); h=6: +1.5% = +0.77 book-sigma (sigma_h 1.9%); h=to_date: +1.5% = +0.77 book-sigma (sigma_h 1.9%)  [sigma_1 0.77%, 1 names, realised mean pair corr -- over 63 sessions] |
| book:32adc8a0ec8ca0fe | Insider SAME-DAY clusters — the falsifier arm for insider_cluster_length_v1 — random_universe twin | yes | 2026-09-11 | h=1: +0.1% = +0.15 book-sigma (sigma_h 0.8%); h=5: -0.9% = -0.47 book-sigma (sigma_h 1.9%); h=6: -0.6% = -0.30 book-sigma (sigma_h 2.1%); h=to_date: -0.6% = -0.30 book-sigma (sigma_h 2.1%)  [sigma_1 0.84%, 40 names, realised mean pair corr 0.07 over 63 sessions] |
| book:33418f0ea53a2f1a | Low short interest, high turnover, long-only (Boehmer-Huszar-Jordan 2010) — beta_matched twin | yes | 2026-09-11 | h=1: -0.7% = -0.65 book-sigma (sigma_h 1.1%); h=5: -0.8% = -0.35 book-sigma (sigma_h 2.4%); h=6: -0.5% = -0.19 book-sigma (sigma_h 2.6%); h=to_date: -0.5% = -0.19 book-sigma (sigma_h 2.6%)  [sigma_1 1.05%, 50 names, realised mean pair corr 0.07 over 63 sessions] |
| book:364486e140074b55 | Cash/index by default; deviate only above a confidence threshold — random_universe twin | yes | 2026-09-11 | h=1: -0.4% = -0.58 book-sigma (sigma_h 0.8%); h=5: -0.1% = -0.05 book-sigma (sigma_h 1.7%); h=6: +1.5% = +0.77 book-sigma (sigma_h 1.9%); h=to_date: +1.5% = +0.77 book-sigma (sigma_h 1.9%)  [sigma_1 0.77%, 1 names, realised mean pair corr -- over 63 sessions] |
| book:57c7af9fb85e59e8 | 12-1 momentum, k=12, equal weight, monthly — beta_matched twin | yes | 2026-09-11 | h=1: -1.2% = -0.76 book-sigma (sigma_h 1.5%); h=5: -0.3% = -0.09 book-sigma (sigma_h 3.4%); h=6: +0.4% = +0.11 book-sigma (sigma_h 3.8%); h=to_date: +0.4% = +0.11 book-sigma (sigma_h 3.8%)  [sigma_1 1.54%, 12 names, realised mean pair corr 0.06 over 63 sessions] |
| book:60c4658f92c49e48 | The UNCONDITIONED reaction book — Book C's primary comparator, run fresh — random_universe twin | yes | 2026-09-11 | h=1: -0.4% = -0.47 book-sigma (sigma_h 0.9%); h=5: -1.6% = -0.79 book-sigma (sigma_h 2.1%); h=6: -1.8% = -0.81 book-sigma (sigma_h 2.3%); h=to_date: -1.8% = -0.81 book-sigma (sigma_h 2.3%)  [sigma_1 0.92%, 30 names, realised mean pair corr 0.06 over 63 sessions] |
| book:6310ca122657f8b1 | Good-news names in the top overhang tercile, long-only (Frazzini 2006 / Grinblatt-Han 2005) — beta_matched twin | yes | 2026-09-11 | h=1: -1.2% = -0.94 book-sigma (sigma_h 1.3%); h=5: -0.4% = -0.13 book-sigma (sigma_h 2.8%); h=6: -0.3% = -0.11 book-sigma (sigma_h 3.1%); h=to_date: -0.3% = -0.11 book-sigma (sigma_h 3.1%)  [sigma_1 1.25%, 30 names, realised mean pair corr 0.07 over 63 sessions] |
| book:668a4e273abf21ff | The UNCONDITIONED reaction book — Book C's primary comparator, run fresh — beta_matched twin | yes | 2026-09-11 | h=1: -1.2% = -0.94 book-sigma (sigma_h 1.3%); h=5: -0.4% = -0.13 book-sigma (sigma_h 2.8%); h=6: -0.3% = -0.11 book-sigma (sigma_h 3.1%); h=to_date: -0.3% = -0.11 book-sigma (sigma_h 3.1%)  [sigma_1 1.25%, 30 names, realised mean pair corr 0.07 over 63 sessions] |
| book:9d62cc74239b435d | Low short interest, high turnover, long-only (Boehmer-Huszar-Jordan 2010) — random_universe twin | yes | 2026-09-11 | h=1: -1.3% = -1.24 book-sigma (sigma_h 1.0%); h=5: -1.8% = -0.78 book-sigma (sigma_h 2.3%); h=6: -1.5% = -0.61 book-sigma (sigma_h 2.5%); h=to_date: -1.5% = -0.61 book-sigma (sigma_h 2.5%)  [sigma_1 1.01%, 50 names, realised mean pair corr 0.08 over 63 sessions] |
| book:f46aaaa40b8c039a | 12-1 momentum, k=12, equal weight, monthly — random_universe twin | yes | 2026-09-11 | h=1: +0.1% = +0.13 book-sigma (sigma_h 0.9%); h=5: -1.5% = -0.76 book-sigma (sigma_h 2.0%); h=6: -1.1% = -0.48 book-sigma (sigma_h 2.2%); h=to_date: -1.1% = -0.48 book-sigma (sigma_h 2.2%)  [sigma_1 0.90%, 12 names, realised mean pair corr 0.03 over 63 sessions] |

## Which library rules held the +10% books' names at entry

Last rebalance on or before R, non-control rules; sealed rank = position on the leaderboard's primary sort (sealed vs SPY).

- **NUAI@2026-09-11** (R 2026-09-11): 19 rule(s) -- `mom_12_1_liqw` (sealed #1), `mom_12_1_q` (sealed #5), `qc470_mom252_quarterly_riskparity` (sealed #10), `mom_12_1_ivw` (sealed #16), `mom_12_1_q_trend` (sealed #23), `mom_12_1` (sealed #74), `mom_ex_lottery` (sealed #80), `mom_no_downgrades` (sealed #103), `mom_12m` (sealed #112), `seasonality_hs` (sealed #132), `seasonality_1y` (sealed #155), `mom_12_1_mid` (sealed #156), `mom_12_1_trend` (sealed #178), `resid_mom_12_1` (sealed #181), `mom_no_rating_downgrade` (sealed #187), `mom_12_7` (sealed #213), `seas_mom` (sealed #216), `mom_no_downgrades_trend` (sealed #223), `eap_avoid_mom` (sealed #261)
- **AXTI@2026-09-11** (R 2026-09-11): 31 rule(s) -- `mom_12_1_liqw` (sealed #1), `mom_12_1_q` (sealed #5), `qc395_sharpe252_above_trend_large` (sealed #8), `qc470_mom252_quarterly_riskparity` (sealed #10), `resid_mom_12_1_large` (sealed #14), `mom_12_1_secrel` (sealed #15), `mom_12_1_ivw` (sealed #16), `frog_large` (sealed #17), `mom_12_1_large` (sealed #22), `mom_12_1_q_trend` (sealed #23), `ear_drift` (sealed #24), `mom_no_downgrades_large` (sealed #31), `ear_drift_large` (sealed #70), `mom_12_1` (sealed #74), `agreements_mom` (sealed #82), `mom_no_downgrades` (sealed #103), `ear_fresh` (sealed #108), `mom_12m` (sealed #112), `mom_6_1_q` (sealed #125), `mom_in_top_sectors` (sealed #135), `mom_resid_to_sector` (sealed #143), `ear_mom` (sealed #144), `overnight_mom` (sealed #148), `div_insider_earn_shorts` (sealed #151), `qc285_secneutral_mom_large_trend` (sealed #157), `mom_12_1_trend` (sealed #178), `resid_mom_12_1` (sealed #181), `mom_no_rating_downgrade` (sealed #187), `mom_12_7` (sealed #213), `mom_no_downgrades_trend` (sealed #223), `eap_avoid_mom` (sealed #261)
- **TWST@2026-09-11** (R 2026-09-11): 14 rule(s) -- `qc623_mom63_liquidity_weighted` (sealed #4), `qc395_sharpe252_above_trend_large` (sealed #8), `px_vs_ma200_large` (sealed #25), `gh04_rps_20_60_120` (sealed #33), `qc597_secneutral_multimom_calm` (sealed #40), `qc536_secneutral_multimom_large` (sealed #46), `init_mom` (sealed #98), `mom_no_exec_change` (sealed #117), `resid_mom_63` (sealed #160), `qc629_multimom_above_trend_gated` (sealed #190), `trend_ma50_200` (sealed #218), `px_vs_ma200` (sealed #244), `gh11_skip_month_composite_q` (sealed #263), `mom_6m` (sealed #271)
- **MU@2026-09-11** (R 2026-09-11): 60 rule(s) -- `mom_12_1_liqw` (sealed #1), `mom_12_1_q` (sealed #5), `skill_mom` (sealed #6), `margin_mom` (sealed #7), `qc395_sharpe252_above_trend_large` (sealed #8), `qc470_mom252_quarterly_riskparity` (sealed #10), `low_dtc_mom` (sealed #12), `resid_mom_12_1_large` (sealed #14), `mom_12_1_secrel` (sealed #15), `mom_12_1_ivw` (sealed #16), `frog_large` (sealed #17), `mom_flow_ivw` (sealed #20), `mom_flow` (sealed #21), `mom_12_1_large` (sealed #22), `mom_12_1_q_trend` (sealed #23), `px_vs_ma200_large` (sealed #25), `mom_no_downgrades_large` (sealed #31), `skill_raises` (sealed #32), `low_days_to_cover_large` (sealed #35), `inflection_flow_large` (sealed #36), `skill_raises_large` (sealed #37), `big_dv` (sealed #42), `qc768_golden_cross_mega` (sealed #43), `mom_12_1_mega` (sealed #48), `n_firms_acting` (sealed #52), `mom_flow_trend` (sealed #57), `mom_flow_secrel` (sealed #59), `inflection_flow` (sealed #64), `net_raises` (sealed #65), `mom_in_raised` (sealed #69), `net_raises_large` (sealed #73), `mom_12_1` (sealed #74), `inflection_large` (sealed #79), `mom_ex_lottery` (sealed #80), `flow_rule` (sealed #81), `flow_in_winners` (sealed #84), `flow_rule_large` (sealed #85), `ibes_skill_net_raises` (sealed #86), `div_mom_insider_flow` (sealed #100), `net_raises_ivw` (sealed #101), `mom_no_downgrades` (sealed #103), `mom_12m` (sealed #112), `net_raises_180d` (sealed #121), `big_dv_trend` (sealed #130), `mom_in_top_sectors` (sealed #135), `flow_rule_q` (sealed #138), `mom_resid_to_sector` (sealed #143), `overnight_mom` (sealed #148), `qc285_secneutral_mom_large_trend` (sealed #157), `net_raises_trend` (sealed #158), `inflection_flow_trend` (sealed #162), `mom_12_1_trend` (sealed #178), `mom_no_rating_downgrade` (sealed #187), `runup_exit_before_large` (sealed #189), `div_lead_earn_mom` (sealed #195), `mom_no_downgrades_trend` (sealed #223), `runup_exit_before` (sealed #259), `eap_avoid_mom` (sealed #261), `mom_no_insider_selling` (sealed #262), `raises_in_losers` (sealed #275)
- **MU@2026-05-01** (R 2026-05-01): 40 rule(s) -- `skill_mom` (sealed #6), `margin_mom` (sealed #7), `qc395_sharpe252_above_trend_large` (sealed #8), `low_dtc_mom` (sealed #12), `frog_large` (sealed #17), `mom_flow_ivw` (sealed #20), `mom_flow` (sealed #21), `chase_raises` (sealed #26), `skill_raises` (sealed #32), `low_days_to_cover_large` (sealed #35), `inflection_flow_large` (sealed #36), `skill_raises_large` (sealed #37), `frog_in_pan` (sealed #39), `big_dv` (sealed #42), `qc768_golden_cross_mega` (sealed #43), `mom_12_1_mega` (sealed #48), `n_firms_acting` (sealed #52), `mom_flow_trend` (sealed #57), `inflection_flow` (sealed #64), `net_raises` (sealed #65), `net_raises_large` (sealed #73), `frog_in_pan_trend` (sealed #78), `inflection_large` (sealed #79), `flow_rule` (sealed #81), `flow_in_winners` (sealed #84), `flow_rule_large` (sealed #85), `ibes_skill_net_raises` (sealed #86), `init_mom` (sealed #98), `net_raises_ivw` (sealed #101), `mom_no_exec_change` (sealed #117), `net_raises_180d` (sealed #121), `net_raises_secrel` (sealed #127), `big_dv_trend` (sealed #130), `flow_rule_q` (sealed #138), `net_raises_trend` (sealed #158), `inflection_flow_trend` (sealed #162), `lead_raises_large` (sealed #167), `inflection_mid_plus` (sealed #186), `runup_exit_before_large` (sealed #189), `lead_raises` (sealed #210)
- **MU@2026-08-10** (R 2026-08-10): 63 rule(s) -- `mom_12_1_liqw` (sealed #1), `mom_12_1_q` (sealed #5), `skill_mom` (sealed #6), `margin_mom` (sealed #7), `qc395_sharpe252_above_trend_large` (sealed #8), `qc470_mom252_quarterly_riskparity` (sealed #10), `low_dtc_mom` (sealed #12), `resid_mom_12_1_large` (sealed #14), `mom_12_1_secrel` (sealed #15), `mom_12_1_ivw` (sealed #16), `frog_large` (sealed #17), `mom_flow_ivw` (sealed #20), `mom_flow` (sealed #21), `mom_12_1_large` (sealed #22), `mom_12_1_q_trend` (sealed #23), `px_vs_ma200_large` (sealed #25), `mom_no_downgrades_large` (sealed #31), `skill_raises` (sealed #32), `low_days_to_cover_large` (sealed #35), `inflection_flow_large` (sealed #36), `skill_raises_large` (sealed #37), `big_dv` (sealed #42), `qc768_golden_cross_mega` (sealed #43), `mom_12_1_mega` (sealed #48), `n_firms_acting` (sealed #52), `gh01_pullback_in_uptrend_mega` (sealed #54), `mom_flow_trend` (sealed #57), `mom_flow_secrel` (sealed #59), `inflection_flow` (sealed #64), `net_raises` (sealed #65), `mom_in_raised` (sealed #69), `net_raises_large` (sealed #73), `mom_12_1` (sealed #74), `inflection_large` (sealed #79), `flow_rule` (sealed #81), `flow_in_winners` (sealed #84), `flow_rule_large` (sealed #85), `ibes_skill_net_raises` (sealed #86), `net_raises_ivw` (sealed #101), `mom_no_downgrades` (sealed #103), `mom_12m` (sealed #112), `net_raises_180d` (sealed #121), `big_dv_trend` (sealed #130), `mom_in_top_sectors` (sealed #135), `flow_rule_q` (sealed #138), `mom_resid_to_sector` (sealed #143), `overnight_mom` (sealed #148), `qc285_secneutral_mom_large_trend` (sealed #157), `net_raises_trend` (sealed #158), `inflection_flow_trend` (sealed #162), `cluster_unconfirmed` (sealed #173), `mom_12_1_trend` (sealed #178), `inflection_mid_plus` (sealed #186), `mom_no_rating_downgrade` (sealed #187), `div_lead_earn_mom` (sealed #195), `trend_ma50_200` (sealed #218), `mom_no_downgrades_trend` (sealed #223), `skilled_leader` (sealed #233), `attention_reversal` (sealed #237), `eap_avoid_mom` (sealed #261), `gh11_skip_month_composite_q` (sealed #263), `raise_price_gap` (sealed #273), `mom_in_laggard_sectors` (sealed #277)
- **MU@2026-09-04** (R 2026-09-04): 60 rule(s) -- `mom_12_1_liqw` (sealed #1), `mom_12_1_q` (sealed #5), `skill_mom` (sealed #6), `margin_mom` (sealed #7), `qc395_sharpe252_above_trend_large` (sealed #8), `qc470_mom252_quarterly_riskparity` (sealed #10), `low_dtc_mom` (sealed #12), `resid_mom_12_1_large` (sealed #14), `mom_12_1_secrel` (sealed #15), `mom_12_1_ivw` (sealed #16), `frog_large` (sealed #17), `mom_flow_ivw` (sealed #20), `mom_flow` (sealed #21), `mom_12_1_large` (sealed #22), `mom_12_1_q_trend` (sealed #23), `px_vs_ma200_large` (sealed #25), `mom_no_downgrades_large` (sealed #31), `skill_raises` (sealed #32), `low_days_to_cover_large` (sealed #35), `inflection_flow_large` (sealed #36), `skill_raises_large` (sealed #37), `big_dv` (sealed #42), `qc768_golden_cross_mega` (sealed #43), `mom_12_1_mega` (sealed #48), `n_firms_acting` (sealed #52), `mom_flow_trend` (sealed #57), `mom_flow_secrel` (sealed #59), `inflection_flow` (sealed #64), `net_raises` (sealed #65), `mom_in_raised` (sealed #69), `net_raises_large` (sealed #73), `mom_12_1` (sealed #74), `inflection_large` (sealed #79), `mom_ex_lottery` (sealed #80), `flow_rule` (sealed #81), `flow_in_winners` (sealed #84), `flow_rule_large` (sealed #85), `ibes_skill_net_raises` (sealed #86), `div_mom_insider_flow` (sealed #100), `net_raises_ivw` (sealed #101), `mom_no_downgrades` (sealed #103), `mom_12m` (sealed #112), `net_raises_180d` (sealed #121), `big_dv_trend` (sealed #130), `mom_in_top_sectors` (sealed #135), `flow_rule_q` (sealed #138), `mom_resid_to_sector` (sealed #143), `overnight_mom` (sealed #148), `qc285_secneutral_mom_large_trend` (sealed #157), `net_raises_trend` (sealed #158), `inflection_flow_trend` (sealed #162), `mom_12_1_trend` (sealed #178), `mom_no_rating_downgrade` (sealed #187), `runup_exit_before_large` (sealed #189), `div_lead_earn_mom` (sealed #195), `mom_no_downgrades_trend` (sealed #223), `runup_exit_before` (sealed #259), `eap_avoid_mom` (sealed #261), `mom_no_insider_selling` (sealed #262), `raises_in_losers` (sealed #275)
- **MU@2026-09-10** (R 2026-09-10): 60 rule(s) -- `mom_12_1_liqw` (sealed #1), `mom_12_1_q` (sealed #5), `skill_mom` (sealed #6), `margin_mom` (sealed #7), `qc395_sharpe252_above_trend_large` (sealed #8), `qc470_mom252_quarterly_riskparity` (sealed #10), `low_dtc_mom` (sealed #12), `resid_mom_12_1_large` (sealed #14), `mom_12_1_secrel` (sealed #15), `mom_12_1_ivw` (sealed #16), `frog_large` (sealed #17), `mom_flow_ivw` (sealed #20), `mom_flow` (sealed #21), `mom_12_1_large` (sealed #22), `mom_12_1_q_trend` (sealed #23), `px_vs_ma200_large` (sealed #25), `mom_no_downgrades_large` (sealed #31), `skill_raises` (sealed #32), `low_days_to_cover_large` (sealed #35), `inflection_flow_large` (sealed #36), `skill_raises_large` (sealed #37), `big_dv` (sealed #42), `qc768_golden_cross_mega` (sealed #43), `mom_12_1_mega` (sealed #48), `n_firms_acting` (sealed #52), `mom_flow_trend` (sealed #57), `mom_flow_secrel` (sealed #59), `inflection_flow` (sealed #64), `net_raises` (sealed #65), `mom_in_raised` (sealed #69), `net_raises_large` (sealed #73), `mom_12_1` (sealed #74), `inflection_large` (sealed #79), `mom_ex_lottery` (sealed #80), `flow_rule` (sealed #81), `flow_in_winners` (sealed #84), `flow_rule_large` (sealed #85), `ibes_skill_net_raises` (sealed #86), `div_mom_insider_flow` (sealed #100), `net_raises_ivw` (sealed #101), `mom_no_downgrades` (sealed #103), `mom_12m` (sealed #112), `net_raises_180d` (sealed #121), `big_dv_trend` (sealed #130), `mom_in_top_sectors` (sealed #135), `flow_rule_q` (sealed #138), `mom_resid_to_sector` (sealed #143), `overnight_mom` (sealed #148), `qc285_secneutral_mom_large_trend` (sealed #157), `net_raises_trend` (sealed #158), `inflection_flow_trend` (sealed #162), `mom_12_1_trend` (sealed #178), `mom_no_rating_downgrade` (sealed #187), `runup_exit_before_large` (sealed #189), `div_lead_earn_mom` (sealed #195), `mom_no_downgrades_trend` (sealed #223), `runup_exit_before` (sealed #259), `eap_avoid_mom` (sealed #261), `mom_no_insider_selling` (sealed #262), `raises_in_losers` (sealed #275)

## Cases

| ticker | book | entry | h | move | move h1 / h5 | sigma_h | z | class | ex-post label | rules holding | credited | candidate feature |
|---|---|---|---:|---:|---|---:|---:|---|---|---:|---|---|
| TWST | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | +31.4% | +6.0% / +31.4% | 12.4% | +2.5 | SELECTABLE_BY_RULE | OTHER | 14 | none |  |
| AXTI | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -13.0% | -13.0% / +6.8% | 10.5% | -1.1 | OTHER | OTHER | 31 | n/a |  |
| AXTI | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -13.0% | -13.0% / +6.8% | 10.5% | -1.1 | OTHER | OTHER | 31 | n/a |  |
| AXTI | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -13.0% | -13.0% / +6.8% | 10.5% | -1.1 | OTHER | OTHER | 31 | n/a |  |
| PRAX | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | -11.7% | -2.4% / -11.7% | 8.7% | -1.2 | OTHER | OTHER | 18 | n/a |  |
| LITE | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -11.0% | -11.0% / -0.8% | 6.1% | -1.6 | OTHER | OTHER | 33 | n/a |  |
| WOLF | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -7.6% | -7.6% / -1.3% | 7.7% | -1.0 | OTHER | OTHER | 25 | n/a |  |
| WOLF | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -7.6% | -7.6% / -1.3% | 7.7% | -1.0 | OTHER | OTHER | 25 | n/a |  |
| WOLF | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -7.6% | -7.6% / -1.3% | 7.7% | -1.0 | OTHER | OTHER | 25 | n/a |  |
| ERAS | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | -7.5% | +1.2% / -7.5% | 9.5% | -0.7 | OTHER | OTHER | 22 | n/a |  |
| ERAS | book:b109c8861c43e3c6 * | 2026-09-11 | 5 | -7.5% | +1.2% / -7.5% | 9.5% | -0.7 | OTHER | OTHER | 22 | n/a |  |
| ERAS | book:3b3e7049e693c3e4 * | 2026-09-11 | 5 | -7.5% | +1.2% / -7.5% | 9.5% | -0.7 | OTHER | OTHER | 22 | n/a |  |
| NUAI | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -5.7% | -5.7% / -1.3% | 7.9% | -0.7 | OTHER | OTHER | 19 | n/a |  |
| NUAI | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -5.7% | -5.7% / -1.3% | 7.9% | -0.7 | OTHER | OTHER | 19 | n/a |  |
| MU | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 5.9% | -0.9 | SECTOR_BETA | SECTOR_BETA | 60 | n/a |  |
| ORKA | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | +5.5% | +5.5% / +4.4% | 4.1% | +0.9 | SELECTABLE_BY_RULE | OTHER | 17 | none |  |
| SNDK | book:8dbbb73b6159d61d * | 2026-09-11 | 1 | -5.5% | -5.5% / +9.1% | 8.5% | -0.6 | OTHER | OTHER | 60 | n/a |  |
| SNDK | book:b109c8861c43e3c6 * | 2026-09-11 | 1 | -5.5% | -5.5% / +9.1% | 8.5% | -0.6 | OTHER | OTHER | 60 | n/a |  |
| SNDK | book:3b3e7049e693c3e4 * | 2026-09-11 | 1 | -5.5% | -5.5% / +9.1% | 8.5% | -0.6 | OTHER | OTHER | 60 | n/a |  |
| RVMD | book:8dbbb73b6159d61d * | 2026-09-11 | 5 | -5.2% | +1.8% / -5.2% | 5.4% | -1.2 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 24 | n/a |  |
| RARE | hack6 | 2026-09-02 | 1 | -42.4% | -42.4% / -44.2% | 3.3% | -13.0 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 1 | n/a |  |
| RARE | hack6 | 2026-09-03 | 1 | -42.3% | -42.3% / -46.1% | 3.3% | -12.9 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 1 | n/a |  |
| MU | conservative | 2026-05-01 | 5 | +37.7% | +6.3% / +37.7% | 10.0% | +3.8 | SELECTABLE_BY_RULE | OTHER | 40 | none |  |
| RKLB | conservative | 2026-05-01 | 5 | +33.8% | +1.9% / +33.8% | 12.6% | +2.7 | SELECTABLE_BY_RULE | ATTENTION_REFLEXIVITY | 5 | none |  |
| SECZ | book:0b4039242299f2e0 | 2026-09-11 | 5 | +30.1% | -1.7% / +30.1% | 18.0% | +1.7 | SELECTABLE_BY_RULE | ATTENTION_REFLEXIVITY | 2 | none |  |
| AMD | conservative | 2026-05-01 | 5 | +26.3% | -5.3% / +26.3% | 9.9% | +2.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 8 | none |  |
| INTC | conservative | 2026-05-01 | 5 | +24.9% | -4.2% / +24.9% | 11.1% | +2.3 | SELECTABLE_BY_RULE | OTHER | 31 | none |  |
| ABSI | conviction | 2026-07-10 | 5 | -21.7% | -3.7% / -21.7% | 18.6% | -1.2 | OTHER | OTHER | 9 | n/a |  |
| NTLA | conviction | 2026-07-10 | 5 | -20.0% | -8.4% / -20.0% | 12.5% | -1.6 | OTHER | OTHER | 1 | n/a |  |
| MSTR | conservative | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | +1.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 6 | none |  |
| MSTR | balanced | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | +1.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 6 | none |  |
| MSTR | aggressive | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | +1.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 6 | none |  |
| MSTR | balanced-ew-control | 2026-09-11 | 5 | +19.7% | +6.5% / +19.7% | 12.5% | +1.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 6 | none |  |
| RZLV | hack4 | 2026-09-01 | 1 | -19.4% | -19.4% / -20.4% | 5.3% | -3.7 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ABSI | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +18.8% | -0.4% / +18.8% | 15.6% | +1.1 | SELECTABLE_BY_RULE | OTHER | 6 | none |  |
| ABSI | book:6310ca122657f8b1 | 2026-09-11 | 5 | +18.8% | -0.4% / +18.8% | 15.6% | +1.1 | SELECTABLE_BY_RULE | OTHER | 6 | none |  |
| ABSI | book:668a4e273abf21ff | 2026-09-11 | 5 | +18.8% | -0.4% / +18.8% | 15.6% | +1.1 | SELECTABLE_BY_RULE | OTHER | 6 | none |  |
| ADPT | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | +18.3% | +2.5% / +18.3% | 7.9% | +2.3 | OTHER | OTHER | 0 | none |  |
| FWDI | book:1dc244805b119552 | 2026-09-11 | 5 | +17.6% | +6.1% / +17.6% | 13.1% | +1.3 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 3 | none |  |
| OKLO | hack1 | 2026-09-09 | 5 | -16.6% | -6.6% / -16.6% | 11.5% | -1.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 1 | n/a |  |
| BE | hack6 | 2026-08-28 | 5 | +16.1% | -5.3% / +16.1% | 17.1% | +0.9 | SELECTABLE_BY_RULE | OTHER | 27 | none |  |
| ABCL | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | +1.0 | SELECTABLE_BY_RULE | OTHER | 3 | none |  |
| ABCL | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | +1.0 | SELECTABLE_BY_RULE | OTHER | 3 | none |  |
| ABCL | book:6310ca122657f8b1 | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | +1.0 | SELECTABLE_BY_RULE | OTHER | 3 | none |  |
| ABCL | book:668a4e273abf21ff | 2026-09-11 | 5 | +16.0% | +2.6% / +16.0% | 15.4% | +1.0 | SELECTABLE_BY_RULE | OTHER | 3 | none |  |
| INIO | book:9d62cc74239b435d | 2026-09-11 | 1 | -15.0% | -15.0% / +3.1% | 5.3% | -2.7 | OTHER | OTHER | 0 | n/a |  |
| ORCL | conservative | 2026-05-01 | 5 | +14.0% | +4.9% / +14.0% | 8.5% | +1.7 | SELECTABLE_BY_RULE | OTHER | 7 | none |  |
| ABG | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -13.9% | -1.7% / -13.9% | 5.1% | -2.4 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ABG | book:6310ca122657f8b1 | 2026-09-11 | 5 | -13.9% | -1.7% / -13.9% | 5.1% | -2.4 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ABG | book:668a4e273abf21ff | 2026-09-11 | 5 | -13.9% | -1.7% / -13.9% | 5.1% | -2.4 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ACHV | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +13.5% | +2.8% / +13.5% | 8.7% | +1.5 | SELECTABLE_BY_RULE | OTHER | 2 | none |  |
| NAMS | hack6 | 2026-09-02 | 5 | -13.4% | +2.5% / -13.4% | 6.6% | -1.9 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| SOC | conviction | 2026-07-10 | 1 | +13.0% | +13.0% / +11.0% | 10.3% | +1.3 | SELECTABLE_BY_RULE | ATTENTION_REFLEXIVITY | 6 | none |  |
| MNPR | book:0b4039242299f2e0 | 2026-09-11 | 5 | -13.0% | -2.3% / -13.0% | 9.7% | -1.3 | OTHER | OTHER | 6 | n/a |  |
| PANW | hack2 | 2026-09-04 | 5 | +12.8% | +1.7% / +12.8% | 8.2% | +1.5 | ANALYST_CASCADE | ANALYST_CASCADE | 23 | n/a |  |
| NAMS | hack6 | 2026-09-08 | 1 | -12.4% | -12.4% / -18.7% | 2.9% | -3.5 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| AVTX | hack6 | 2026-09-09 | 1 | -12.3% | -12.3% / -15.4% | 4.2% | -3.0 | OTHER | OTHER | 2 | n/a |  |
| PANW | hack1 | 2026-09-04 | 5 | +12.2% | +1.2% / +12.3% | 8.2% | +1.5 | ANALYST_CASCADE | ANALYST_CASCADE | 23 | n/a |  |
| ULS | hack6 | 2026-09-08 | 5 | -12.2% | -1.2% / -12.2% | 5.8% | -2.1 | OTHER | OTHER | 1 | n/a |  |
| NAMS | hack6 | 2026-09-03 | 5 | -12.1% | -2.1% / -12.1% | 6.6% | -1.6 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| COHR | book:9d62cc74239b435d | 2026-09-11 | 1 | -12.1% | -12.1% / +4.7% | 6.4% | -2.0 | OTHER | OTHER | 10 | n/a |  |
| COHR | book:1dc244805b119552 | 2026-09-11 | 1 | -12.1% | -12.1% / +4.7% | 6.4% | -2.0 | OTHER | OTHER | 10 | n/a |  |
| GPCR | hack6 | 2026-09-08 | 1 | -11.4% | -11.4% / -16.3% | 3.1% | -4.2 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 2 | n/a |  |
| BTU | book:1dc244805b119552 | 2026-09-11 | 5 | -11.2% | -3.7% / -11.2% | 6.8% | -1.5 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| AMD | conservative | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | +1.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 31 | none |  |
| AMD | balanced | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | +1.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 31 | none |  |
| AMD | aggressive | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | +1.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 31 | none |  |
| AMD | balanced-ew-control | 2026-09-11 | 5 | +11.2% | -2.0% / +11.2% | 10.2% | +1.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 31 | none |  |
| COIN | conservative | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | +2.5 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| COIN | balanced | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | +2.5 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| COIN | aggressive | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | +2.5 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| COIN | balanced-ew-control | 2026-09-11 | 1 | +11.1% | +11.1% / +12.8% | 4.5% | +2.5 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| LENZ | hack4 | 2026-09-09 | 1 | -11.1% | -11.1% / -22.0% | 4.2% | -2.7 | OTHER | OTHER | 0 | n/a |  |
| TXG | book:9d62cc74239b435d | 2026-09-11 | 5 | +11.0% | +1.6% / +11.0% | 10.8% | +1.1 | SELECTABLE_BY_RULE | OTHER | 26 | none |  |
| DKNG | conservative | 2026-05-01 | 5 | +11.0% | +2.5% / +11.0% | 7.3% | +1.5 | SELECTABLE_BY_RULE | OTHER | 4 | none |  |
| JACK | book:60c4658f92c49e48 | 2026-09-11 | 5 | -10.9% | +0.0% / -10.9% | 12.3% | -0.9 | OTHER | OTHER | 1 | n/a |  |
| HPE | book:000b263cf7ec2286 | 2026-09-11 | 1 | -10.8% | -10.8% / -1.9% | 4.0% | -2.7 | PRODUCT_DEMAND | PRODUCT_DEMAND | 11 | n/a |  |
| AEIS | book:9d62cc74239b435d | 2026-09-11 | 1 | -10.6% | -10.6% / -7.8% | 4.9% | -2.3 | OTHER | OTHER | 0 | n/a |  |
| MRAM | book:9d62cc74239b435d | 2026-09-11 | 1 | -10.5% | -10.5% / -7.2% | 6.2% | -1.5 | OTHER | OTHER | 2 | n/a |  |
| IMCR | hack6 | 2026-09-08 | 5 | -10.5% | -2.9% / -10.5% | 4.6% | -2.6 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| TEN | book:9d62cc74239b435d | 2026-09-11 | 5 | +10.4% | +5.2% / +10.4% | 5.5% | +1.6 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | none |  |
| AVGO | conservative | 2026-08-11 | 5 | -10.2% | -1.7% / -10.2% | 7.6% | -1.3 | OTHER | OTHER | 7 | n/a |  |
| ABVX | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | -0.9 | OTHER | OTHER | 1 | n/a |  |
| ABVX | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | -0.9 | OTHER | OTHER | 1 | n/a |  |
| ABVX | book:6310ca122657f8b1 | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | -0.9 | OTHER | OTHER | 1 | n/a |  |
| ABVX | book:668a4e273abf21ff | 2026-09-11 | 5 | -10.2% | -2.9% / -10.2% | 12.4% | -0.9 | OTHER | OTHER | 1 | n/a |  |
| SLDP | conservative | 2026-05-01 | 5 | -10.1% | +1.2% / -10.1% | 8.6% | -1.2 | OTHER | OTHER | 1 | n/a |  |
| TTAM | book:9d62cc74239b435d | 2026-09-11 | 5 | -10.1% | -3.9% / -10.1% | 5.1% | -1.7 | OTHER | OTHER | 0 | n/a |  |
| GPGI | book:1dc244805b119552 | 2026-09-11 | 5 | -9.9% | -2.4% / -9.9% | 9.0% | -1.1 | OTHER | OTHER | 1 | n/a |  |
| UEC | hack6 | 2026-08-28 | 1 | -9.8% | -9.8% / -15.0% | 5.3% | -1.9 | OTHER | OTHER | 2 | n/a |  |
| TRMD | book:1dc244805b119552 | 2026-09-11 | 5 | +9.8% | +1.5% / +9.8% | 5.3% | +1.7 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 1 | none |  |
| TRMD | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | +9.8% | +1.5% / +9.8% | 5.3% | +1.7 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 1 | none |  |
| AR | book:9d62cc74239b435d | 2026-09-11 | 5 | -9.8% | -1.4% / -9.8% | 4.4% | -2.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| PRCH | conviction | 2026-07-10 | 1 | -9.7% | -9.7% / -7.9% | 4.4% | -2.2 | OTHER | OTHER | 0 | n/a |  |
| GRAB | hack6 | 2026-09-08 | 1 | -9.5% | -9.5% / -13.4% | 2.3% | -4.8 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| AAOI | book:57c7af9fb85e59e8 | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | -1.1 | OTHER | OTHER | 7 | n/a |  |
| AAOI | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | -1.1 | OTHER | OTHER | 7 | n/a |  |
| AAOI | book:1dc244805b119552 | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | -1.1 | OTHER | OTHER | 7 | n/a |  |
| AAOI | book:6310ca122657f8b1 | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | -1.1 | OTHER | OTHER | 7 | n/a |  |
| AAOI | book:668a4e273abf21ff | 2026-09-11 | 1 | -9.3% | -9.3% / -0.4% | 8.2% | -1.1 | OTHER | OTHER | 7 | n/a |  |
| MU | balanced | 2026-09-04 | 5 | -9.1% | -1.6% / -9.1% | 13.9% | -0.7 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| MU | aggressive | 2026-09-04 | 5 | -9.1% | -1.6% / -9.1% | 13.9% | -0.7 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| MU | balanced-ew-control | 2026-09-04 | 5 | -9.1% | -1.6% / -9.1% | 13.9% | -0.7 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| ARDX | hack6 | 2026-09-08 | 5 | -9.1% | +1.6% / -9.1% | 7.1% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| INTC | balanced | 2026-09-04 | 1 | +9.0% | +9.1% / +1.5% | 5.0% | +1.8 | SELECTABLE_BY_RULE | OTHER | 19 | none |  |
| INTC | aggressive | 2026-09-04 | 1 | +9.0% | +9.1% / +1.5% | 5.0% | +1.8 | SELECTABLE_BY_RULE | OTHER | 19 | none |  |
| INTC | balanced-ew-control | 2026-09-04 | 1 | +9.0% | +9.1% / +1.5% | 5.0% | +1.8 | SELECTABLE_BY_RULE | OTHER | 19 | none |  |
| NGVC | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | +9.0% | +3.3% / +9.0% | 6.6% | +1.3 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | none |  |
| ABX | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -9.0% | -1.6% / -9.0% | 7.5% | -1.0 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ABX | book:6310ca122657f8b1 | 2026-09-11 | 5 | -9.0% | -1.6% / -9.0% | 7.5% | -1.0 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ABX | book:668a4e273abf21ff | 2026-09-11 | 5 | -9.0% | -1.6% / -9.0% | 7.5% | -1.0 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| USAR | hack6 | 2026-08-28 | 1 | -8.9% | -8.9% / -10.0% | 5.8% | -1.3 | OTHER | OTHER | 3 | n/a |  |
| ADNT | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -8.8% | -3.2% / -8.8% | 7.4% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| ORCL | balanced | 2026-09-04 | 5 | -8.8% | +2.4% / -8.8% | 8.1% | -1.1 | ANALYST_CASCADE | ANALYST_CASCADE | 5 | n/a |  |
| ORCL | aggressive | 2026-09-04 | 5 | -8.8% | +2.4% / -8.8% | 8.1% | -1.1 | ANALYST_CASCADE | ANALYST_CASCADE | 5 | n/a |  |
| ORCL | balanced-ew-control | 2026-09-04 | 5 | -8.8% | +2.4% / -8.8% | 8.1% | -1.1 | ANALYST_CASCADE | ANALYST_CASCADE | 5 | n/a |  |
| LXEO | hack4 | 2026-09-09 | 1 | -8.8% | -8.8% / -13.0% | 3.5% | -2.4 | OTHER | OTHER | 1 | n/a |  |
| META | conservative | 2026-08-11 | 5 | -8.7% | -2.8% / -8.7% | 6.5% | -1.3 | OTHER | OTHER | 3 | n/a |  |
| ACMR | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -8.6% | -8.6% / -6.4% | 6.4% | -1.1 | OTHER | OTHER | 0 | n/a |  |
| TEAM | book:9d62cc74239b435d | 2026-09-11 | 1 | +8.6% | +8.6% / +8.1% | 6.1% | +1.2 | SELECTABLE_BY_RULE | OTHER | 15 | none |  |
| AMSC | hack6 | 2026-09-08 | 5 | -8.6% | -3.2% / -8.6% | 9.5% | -0.7 | SECTOR_BETA | SECTOR_BETA | 2 | n/a |  |
| CTNM | book:9d62cc74239b435d | 2026-09-11 | 5 | -8.6% | +0.2% / -8.6% | 9.4% | -0.9 | ANALYST_CASCADE | ANALYST_CASCADE | 0 | n/a |  |
| NVDA | conservative | 2026-05-01 | 5 | +8.4% | +0.0% / +8.4% | 5.5% | +1.5 | SELECTABLE_BY_RULE | SECTOR_BETA | 18 | none |  |
| KYTX | conviction | 2026-07-10 | 1 | -8.4% | -8.4% / -12.2% | 5.1% | -1.7 | OTHER | OTHER | 0 | n/a |  |
| NVDA | balanced | 2026-09-04 | 5 | -8.4% | -2.1% / -8.4% | 5.7% | -1.4 | ANALYST_CASCADE | ANALYST_CASCADE | 13 | n/a |  |
| AA | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| AA | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| AA | book:6310ca122657f8b1 | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| AA | book:668a4e273abf21ff | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| AA | book:1ece648f7410da8e | 2026-09-11 | 5 | -8.4% | -3.2% / -8.4% | 7.0% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| NVDA | aggressive | 2026-09-04 | 5 | -8.3% | -2.0% / -8.3% | 5.7% | -1.4 | ANALYST_CASCADE | ANALYST_CASCADE | 13 | n/a |  |
| NVDA | balanced-ew-control | 2026-09-04 | 5 | -8.3% | -2.0% / -8.3% | 5.7% | -1.4 | ANALYST_CASCADE | ANALYST_CASCADE | 13 | n/a |  |
| DKNG | conservative | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| DKNG | balanced | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| DKNG | aggressive | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| DKNG | balanced-ew-control | 2026-09-11 | 5 | -8.3% | +4.8% / -8.3% | 7.6% | -1.1 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| INTC | balanced-ew-control | 2026-09-11 | 5 | +8.3% | -3.1% / +8.3% | 11.1% | +0.7 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 19 | none |  |
| RGTI | conservative | 2026-05-01 | 5 | +8.2% | +1.1% / +8.2% | 12.2% | +0.7 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| NB | hack4 | 2026-09-02 | 5 | -8.2% | -1.2% / -8.2% | 11.8% | -0.4 | OTHER | OTHER | 1 | n/a |  |
| AMSC | conviction | 2026-07-10 | 5 | -8.2% | -4.9% / -8.2% | 11.6% | -0.7 | OTHER | OTHER | 3 | n/a |  |
| HUBS | conviction | 2026-07-10 | 5 | +8.1% | +4.9% / +8.1% | 11.9% | +0.7 | SELECTABLE_BY_RULE | OTHER | 4 | none |  |
| GPOR | book:000b263cf7ec2286 | 2026-09-11 | 5 | -8.1% | -0.4% / -8.1% | 4.1% | -1.9 | OTHER | OTHER | 0 | n/a |  |
| HL | hack6 | 2026-08-28 | 1 | -8.0% | -8.0% / -4.3% | 4.3% | -1.7 | OTHER | OTHER | 0 | n/a |  |
| CHYM | book:1dc244805b119552 | 2026-09-11 | 5 | -8.0% | +3.0% / -8.0% | 9.4% | -0.9 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 4 | n/a |  |
| META | aggressive | 2026-09-04 | 5 | +7.9% | -0.5% / +7.9% | 6.4% | +1.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| META | balanced-ew-control | 2026-09-04 | 5 | +7.9% | -0.5% / +7.9% | 6.4% | +1.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| FTH | book:1dc244805b119552 | 2026-09-11 | 5 | -7.9% | +4.4% / -7.9% | 17.1% | -0.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 8 | n/a |  |
| META | balanced | 2026-09-04 | 5 | +7.8% | -0.6% / +7.8% | 6.4% | +1.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| PLUG | hack1 | 2026-09-09 | 5 | -7.8% | -3.7% / -7.8% | 8.3% | -1.3 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| ADEA | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -7.7% | -7.7% / -7.1% | 3.8% | -2.0 | OTHER | OTHER | 0 | n/a |  |
| MP | hack6 | 2026-08-28 | 1 | -7.7% | -7.7% / -8.1% | 4.4% | -1.6 | OTHER | OTHER | 2 | n/a |  |
| SVV | book:000b263cf7ec2286 | 2026-09-11 | 5 | -7.7% | +0.7% / -7.7% | 7.6% | -1.0 | OTHER | OTHER | 0 | n/a |  |
| SCZM | book:9d62cc74239b435d | 2026-09-11 | 1 | -7.7% | -7.7% / -1.9% | 4.7% | -1.5 | OTHER | OTHER | 0 | n/a |  |
| GS | conservative | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | -1.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 1 | n/a |  |
| GS | balanced | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | -1.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 1 | n/a |  |
| GS | aggressive | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | -1.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 1 | n/a |  |
| GS | balanced-ew-control | 2026-09-11 | 5 | -7.6% | -3.1% / -7.6% | 5.0% | -1.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 1 | n/a |  |
| QUBT | conviction | 2026-07-10 | 1 | -7.6% | -7.6% / -9.9% | 6.8% | -1.1 | OTHER | OTHER | 0 | n/a |  |
| MRVL | conservative | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | +0.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 28 | none |  |
| MRVL | balanced | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | +0.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 28 | none |  |
| MRVL | aggressive | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | +0.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 28 | none |  |
| MRVL | balanced-ew-control | 2026-09-11 | 5 | +7.6% | -3.6% / +7.6% | 13.1% | +0.6 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 28 | none |  |
| KRMN | hack6 | 2026-09-09 | 1 | -7.4% | -7.4% / -0.6% | 4.3% | -3.1 | OTHER | OTHER | 2 | n/a |  |
| ECG | book:32adc8a0ec8ca0fe | 2026-09-11 | 1 | -7.4% | -7.4% / -3.5% | 4.1% | -1.7 | OTHER | OTHER | 0 | n/a |  |
| ACDC | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -7.4% | -7.4% / -1.9% | 5.6% | -1.1 | OTHER | OTHER | 0 | n/a |  |
| ACDC | book:6310ca122657f8b1 | 2026-09-11 | 1 | -7.4% | -7.4% / -1.9% | 5.6% | -1.1 | OTHER | OTHER | 0 | n/a |  |
| ACDC | book:668a4e273abf21ff | 2026-09-11 | 1 | -7.4% | -7.4% / -1.9% | 5.6% | -1.1 | OTHER | OTHER | 0 | n/a |  |
| A | book:57c7af9fb85e59e8 | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | +1.6 | OTHER | OTHER | 0 | none |  |
| A | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | +1.6 | OTHER | OTHER | 0 | none |  |
| ACRS | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +7.3% | +7.3% / +4.7% | 3.4% | +1.8 | SELECTABLE_BY_RULE | ATTENTION_REFLEXIVITY | 2 | none |  |
| A | book:6310ca122657f8b1 | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | +1.6 | OTHER | OTHER | 0 | none |  |
| A | book:668a4e273abf21ff | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | +1.6 | OTHER | OTHER | 0 | none |  |
| A | book:1ece648f7410da8e | 2026-09-11 | 5 | +7.3% | +0.7% / +7.3% | 4.0% | +1.6 | OTHER | OTHER | 0 | none |  |
| WVE | hack4 | 2026-09-09 | 5 | -7.3% | -3.9% / -7.3% | 7.7% | -1.1 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| ACLS | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -7.2% | -7.2% / -3.6% | 5.0% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| JMIA | book:000b263cf7ec2286 | 2026-09-11 | 5 | -7.1% | -1.9% / -7.1% | 7.8% | -0.9 | OTHER | OTHER | 0 | n/a |  |
| PLTR | conservative | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | +0.6 | SELECTABLE_BY_RULE | OTHER | 9 | none |  |
| PLTR | balanced | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | +0.6 | SELECTABLE_BY_RULE | OTHER | 9 | none |  |
| PLTR | aggressive | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | +0.6 | SELECTABLE_BY_RULE | OTHER | 9 | none |  |
| PLTR | balanced-ew-control | 2026-09-11 | 5 | +7.1% | +4.5% / +7.1% | 11.4% | +0.6 | SELECTABLE_BY_RULE | OTHER | 9 | none |  |
| MAZE | hack6 | 2026-09-02 | 5 | -7.1% | -3.1% / -7.1% | 6.3% | -1.0 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| CAL | book:000b263cf7ec2286 | 2026-09-11 | 5 | -7.0% | -0.7% / -7.0% | 8.9% | -0.7 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| CAL | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -7.0% | -0.7% / -7.0% | 8.9% | -0.7 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| NTST | book:1dc244805b119552 | 2026-09-11 | 5 | -7.0% | -0.1% / -7.0% | 3.3% | -2.3 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| ACI | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +6.9% | +6.9% / +3.8% | 3.5% | +1.5 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| ABAT | hack4 | 2026-09-02 | 5 | -6.9% | -1.1% / -6.9% | 13.4% | -0.1 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| DNN | hack6 | 2026-08-28 | 1 | -6.9% | -6.9% / -6.0% | 4.0% | -1.9 | OTHER | OTHER | 0 | n/a |  |
| CDE | hack6 | 2026-08-28 | 1 | -6.9% | -6.9% / -4.8% | 4.7% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| ABAT | hack4 | 2026-08-31 | 5 | +6.8% | -1.5% / +6.8% | 13.6% | +0.7 | OTHER | OTHER | 0 | none |  |
| ADBE | conservative | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | +2.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 4 | none |  |
| ADBE | balanced | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | +2.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 4 | none |  |
| ADBE | aggressive | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | +2.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 4 | none |  |
| ADBE | balanced-ew-control | 2026-09-11 | 1 | +6.7% | +6.7% / +0.0% | 3.2% | +2.1 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 4 | none |  |
| OSS | book:1dc244805b119552 | 2026-09-11 | 1 | -6.7% | -6.7% / -3.2% | 5.1% | -1.0 | OTHER | OTHER | 4 | n/a |  |
| TTI | book:1dc244805b119552 | 2026-09-11 | 1 | -6.7% | -6.7% / -12.3% | 3.6% | -1.4 | OTHER | OTHER | 1 | n/a |  |
| AMZN | conservative | 2026-08-11 | 5 | -6.7% | -3.9% / -6.7% | 6.2% | -1.1 | OTHER | OTHER | 2 | n/a |  |
| UPBD | book:60c4658f92c49e48 | 2026-09-11 | 5 | -6.7% | -0.6% / -6.7% | 6.1% | -1.1 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| ADBE | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +6.6% | +6.6% / -0.1% | 3.1% | +1.7 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 4 | none |  |
| NKTR | hack6 | 2026-09-03 | 5 | -6.6% | -0.7% / -6.6% | 6.8% | -0.6 | OTHER | OTHER | 6 | n/a |  |
| DY | book:9d62cc74239b435d | 2026-09-11 | 1 | -6.6% | -6.6% / -5.0% | 3.6% | -1.8 | OTHER | OTHER | 4 | n/a |  |
| IONQ | conservative | 2026-05-01 | 5 | +6.6% | -1.0% / +6.6% | 14.6% | +0.4 | SELECTABLE_BY_RULE | SECTOR_BETA | 2 | none |  |
| CRM | conservative | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | +1.7 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 10 | none |  |
| CRM | balanced | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | +1.7 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 10 | none |  |
| CRM | aggressive | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | +1.7 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 10 | none |  |
| CRM | balanced-ew-control | 2026-09-11 | 1 | +6.6% | +6.6% / -2.1% | 3.9% | +1.7 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 10 | none |  |
| AD | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -6.6% | +0.5% / -6.6% | 3.2% | -2.1 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 1 | n/a |  |
| ABAT | hack4 | 2026-09-01 | 1 | +6.5% | +6.5% / +2.3% | 6.1% | +0.5 | OTHER | OTHER | 0 | none |  |
| AAON | book:57c7af9fb85e59e8 | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | -1.6 | OTHER | OTHER | 0 | n/a |  |
| AAON | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | -1.6 | OTHER | OTHER | 0 | n/a |  |
| AAON | book:6310ca122657f8b1 | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | -1.6 | OTHER | OTHER | 0 | n/a |  |
| AAON | book:668a4e273abf21ff | 2026-09-11 | 1 | -6.5% | -6.5% / -5.0% | 3.4% | -1.6 | OTHER | OTHER | 0 | n/a |  |
| ENPH | hack6 | 2026-08-28 | 1 | -6.5% | -6.5% / -6.6% | 5.0% | -1.4 | OTHER | OTHER | 4 | n/a |  |
| QS | hack6 | 2026-08-28 | 1 | -6.4% | -6.4% / -8.2% | 4.9% | -1.1 | OTHER | OTHER | 0 | n/a |  |
| UUUU | hack6 | 2026-08-28 | 1 | -6.3% | -6.3% / -8.1% | 4.9% | -1.3 | OTHER | OTHER | 1 | n/a |  |
| WGO | book:9d62cc74239b435d | 2026-09-11 | 5 | -6.3% | +0.5% / -6.3% | 6.5% | -1.0 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| PLGO | book:000b263cf7ec2286 | 2026-09-11 | 5 | -6.3% | -0.8% / -6.3% | 4.0% | -1.5 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| BUR | hack6 | 2026-09-08 | 5 | -6.3% | +0.4% / -6.3% | 5.5% | -0.7 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| HON | conservative | 2026-08-11 | 5 | -6.3% | -3.4% / -6.3% | 5.0% | -1.2 | ANALYST_CASCADE | ANALYST_CASCADE | 0 | n/a |  |
| IONQ | balanced-ew-control | 2026-09-11 | 5 | +6.2% | +1.8% / +6.2% | 11.3% | +0.5 | RIGHT_STOCK_WRONG_REASON | RIGHT_STOCK_WRONG_REASON | 0 | none |  |
| SGML | book:9d62cc74239b435d | 2026-09-11 | 1 | -6.2% | -6.2% / +4.9% | 4.5% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| NX | book:0b4039242299f2e0 | 2026-09-11 | 5 | -6.2% | -2.4% / -6.2% | 9.6% | -0.7 | OTHER | OTHER | 0 | n/a |  |
| CRVL | book:1dc244805b119552 | 2026-09-11 | 1 | +6.2% | +6.2% / +3.9% | 1.9% | +2.2 | OTHER | OTHER | 0 | none |  |
| MAZE | hack6 | 2026-09-03 | 5 | -6.1% | +0.0% / -6.1% | 6.3% | -1.3 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| COIN | conservative | 2026-05-01 | 1 | +6.1% | +6.1% / +5.2% | 5.5% | +1.1 | OTHER | OTHER | 0 | none |  |
| UEC | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -6.1% | -1.8% / -6.1% | 9.1% | -0.7 | SECTOR_BETA | SECTOR_BETA | 2 | n/a |  |
| CHKP | book:60c4658f92c49e48 | 2026-09-11 | 1 | +6.1% | +6.1% / +1.7% | 2.5% | +2.1 | OTHER | OTHER | 0 | none |  |
| CARR | book:60c4658f92c49e48 | 2026-09-11 | 5 | -6.1% | -0.2% / -6.1% | 4.8% | -1.3 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| QUBT | hack6 | 2026-08-28 | 5 | -6.1% | -3.5% / -6.1% | 11.7% | -0.6 | OTHER | OTHER | 0 | n/a |  |
| POWL | book:f46aaaa40b8c039a | 2026-09-11 | 1 | -6.1% | -6.1% / +1.2% | 4.0% | -1.6 | OTHER | OTHER | 4 | n/a |  |
| ACN | book:33418f0ea53a2f1a | 2026-09-11 | 1 | +6.0% | +6.0% / -1.4% | 3.7% | +1.6 | OTHER | OTHER | 0 | none |  |
| HOG | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -6.0% | -0.7% / -6.0% | 5.4% | -1.2 | SECTOR_BETA | SECTOR_BETA | 1 | n/a |  |
| BDC | book:1dc244805b119552 | 2026-09-11 | 1 | -5.9% | -5.9% / -7.9% | 3.2% | -2.3 | OTHER | OTHER | 0 | n/a |  |
| AMD | balanced | 2026-09-04 | 1 | +5.9% | +5.9% / +3.3% | 4.6% | +1.3 | SELECTABLE_BY_RULE | OTHER | 31 | none |  |
| AMD | aggressive | 2026-09-04 | 1 | +5.9% | +5.9% / +3.3% | 4.6% | +1.3 | SELECTABLE_BY_RULE | OTHER | 31 | none |  |
| AMD | balanced-ew-control | 2026-09-04 | 1 | +5.9% | +5.9% / +3.3% | 4.6% | +1.3 | SELECTABLE_BY_RULE | OTHER | 31 | none |  |
| MSTR | conservative | 2026-05-01 | 5 | +5.9% | +3.7% / +5.9% | 13.3% | +0.4 | SELECTABLE_BY_RULE | SECTOR_BETA | 3 | none |  |
| AVGO | book:1dc244805b119552 | 2026-09-11 | 1 | -5.9% | -5.9% / -2.4% | 2.7% | -1.8 | ANALYST_CASCADE | ANALYST_CASCADE | 5 | n/a |  |
| AVGO | book:32adc8a0ec8ca0fe | 2026-09-11 | 1 | -5.9% | -5.9% / -2.4% | 2.7% | -1.8 | ANALYST_CASCADE | ANALYST_CASCADE | 5 | n/a |  |
| HAL | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.9% | -2.0% / -5.9% | 4.8% | -1.3 | SECTOR_BETA | SECTOR_BETA | 4 | n/a |  |
| AADX | book:33418f0ea53a2f1a | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | +0.4 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | none |  |
| AADX | book:6310ca122657f8b1 | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | +0.4 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | none |  |
| AADX | book:668a4e273abf21ff | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | +0.4 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | none |  |
| AADX | book:1ece648f7410da8e | 2026-09-11 | 5 | +5.8% | -3.4% / +5.8% | 11.6% | +0.4 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | none |  |
| MU | conservative | 2026-08-11 | 1 | +5.8% | +5.8% / +9.3% | 7.0% | +0.8 | SELECTABLE_BY_RULE | OTHER | 63 | none |  |
| ALMU | hack4 | 2026-08-31 | 1 | -5.8% | -5.8% / +0.6% | 6.4% | -0.8 | OTHER | OTHER | 6 | n/a |  |
| GE | balanced | 2026-09-04 | 5 | -5.8% | -0.7% / -5.8% | 4.4% | -1.3 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| GE | aggressive | 2026-09-04 | 5 | -5.8% | -0.7% / -5.8% | 4.4% | -1.3 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| GE | balanced-ew-control | 2026-09-04 | 5 | -5.8% | -0.7% / -5.8% | 4.4% | -1.3 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| DKNG | conviction | 2026-07-10 | 5 | -5.8% | -0.1% / -5.8% | 7.6% | -0.8 | OTHER | OTHER | 0 | n/a |  |
| NKTR | hack6 | 2026-09-02 | 1 | +5.8% | +5.8% / -2.2% | 3.0% | +2.1 | SELECTABLE_BY_RULE | OTHER | 6 | none |  |
| NXE | book:9d62cc74239b435d | 2026-09-11 | 1 | -5.7% | -5.7% / -6.9% | 3.1% | -1.2 | OTHER | OTHER | 0 | n/a |  |
| BJ | book:60c4658f92c49e48 | 2026-09-11 | 1 | +5.7% | +5.7% / +2.1% | 1.9% | +2.2 | SELECTABLE_BY_RULE | OTHER | 2 | none |  |
| NEXN | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.7% | +1.4% / -5.7% | 5.4% | -0.9 | SECTOR_BETA | SECTOR_BETA | 2 | n/a |  |
| CVS | book:1dc244805b119552 | 2026-09-11 | 5 | -5.7% | +1.4% / -5.7% | 3.6% | -1.7 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 4 | n/a |  |
| CVS | book:60c4658f92c49e48 | 2026-09-11 | 5 | -5.7% | +1.4% / -5.7% | 3.6% | -1.7 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 4 | n/a |  |
| EGO | book:60c4658f92c49e48 | 2026-09-11 | 1 | -5.6% | -5.6% / -0.9% | 4.1% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| DHR | conservative | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | +1.0 | OTHER | OTHER | 0 | none |  |
| DHR | balanced | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | +1.0 | OTHER | OTHER | 0 | none |  |
| DHR | aggressive | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | +1.0 | OTHER | OTHER | 0 | none |  |
| DHR | balanced-ew-control | 2026-09-11 | 5 | +5.6% | +1.4% / +5.6% | 5.4% | +1.0 | OTHER | OTHER | 0 | none |  |
| QQQ | conservative | 2026-05-01 | 5 | +5.5% | -0.2% / +5.5% | 2.8% | +2.0 | OTHER | OTHER | 0 | none |  |
| ERIE | book:9d62cc74239b435d | 2026-09-11 | 1 | +5.5% | +5.5% / -0.7% | 3.1% | +1.2 | OTHER | OTHER | 0 | none |  |
| ACHR | book:33418f0ea53a2f1a | 2026-09-11 | 5 | -5.5% | -1.0% / -5.5% | 11.8% | -0.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| ACHR | book:6310ca122657f8b1 | 2026-09-11 | 5 | -5.5% | -1.0% / -5.5% | 11.8% | -0.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| ACHR | book:668a4e273abf21ff | 2026-09-11 | 5 | -5.5% | -1.0% / -5.5% | 11.8% | -0.5 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 0 | n/a |  |
| ORCL | conservative | 2026-08-11 | 5 | -5.5% | +1.5% / -5.5% | 9.3% | -0.6 | OTHER | OTHER | 10 | n/a |  |
| MU | conservative | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | -0.9 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| MU | balanced | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | -0.9 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| MU | aggressive | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | -0.9 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| MU | balanced-ew-control | 2026-09-11 | 1 | -5.5% | -5.5% / +3.9% | 6.1% | -0.9 | UNFORESEEABLE_NEWS | UNFORESEEABLE_NEWS | 60 | n/a |  |
| NBR | book:60c4658f92c49e48 | 2026-09-11 | 5 | -5.4% | -3.6% / -5.4% | 7.0% | -0.8 | OTHER | OTHER | 0 | n/a |  |
| FSLR | conservative | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | -0.8 | OTHER | OTHER | 5 | n/a |  |
| FSLR | balanced | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | -0.8 | OTHER | OTHER | 5 | n/a |  |
| FSLR | aggressive | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | -0.8 | OTHER | OTHER | 5 | n/a |  |
| FSLR | balanced-ew-control | 2026-09-11 | 5 | -5.4% | -0.1% / -5.4% | 6.9% | -0.8 | OTHER | OTHER | 5 | n/a |  |
| FUL | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.4% | -2.4% / -5.4% | 4.7% | -0.9 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| ALMU | hack4 | 2026-09-01 | 5 | +5.4% | +1.8% / +5.4% | 12.9% | +0.1 | SELECTABLE_BY_RULE | OTHER | 9 | none |  |
| XOM | conservative | 2026-05-01 | 5 | -5.4% | +0.6% / -5.4% | 4.2% | -1.3 | SECTOR_BETA | SECTOR_BETA | 9 | n/a |  |
| ORCL | conservative | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | -1.5 | PRODUCT_DEMAND | PRODUCT_DEMAND | 5 | n/a |  |
| ORCL | balanced | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | -1.5 | PRODUCT_DEMAND | PRODUCT_DEMAND | 5 | n/a |  |
| ORCL | aggressive | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | -1.5 | PRODUCT_DEMAND | PRODUCT_DEMAND | 5 | n/a |  |
| ORCL | balanced-ew-control | 2026-09-11 | 1 | -5.3% | -5.3% / -3.5% | 3.7% | -1.5 | PRODUCT_DEMAND | PRODUCT_DEMAND | 5 | n/a |  |
| TTWO | conservative | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | -1.0 | OTHER | OTHER | 8 | n/a |  |
| TTWO | balanced | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | -1.0 | OTHER | OTHER | 8 | n/a |  |
| TTWO | aggressive | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | -1.0 | OTHER | OTHER | 8 | n/a |  |
| TTWO | balanced-ew-control | 2026-09-11 | 5 | -5.3% | +2.7% / -5.3% | 5.1% | -1.0 | OTHER | OTHER | 8 | n/a |  |
| MAZE | hack6 | 2026-09-09 | 1 | -5.3% | -5.3% / -8.8% | 2.8% | -2.1 | OTHER | OTHER | 0 | n/a |  |
| NCLH | book:9d62cc74239b435d | 2026-09-11 | 5 | -5.3% | -1.2% / -5.3% | 6.6% | -0.7 | SECTOR_BETA | SECTOR_BETA | 3 | n/a |  |
| NCLH | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -5.3% | -1.2% / -5.3% | 6.6% | -0.7 | OTHER | OTHER | 3 | n/a |  |
| AAUC | book:33418f0ea53a2f1a | 2026-09-11 | 1 | -5.3% | -5.3% / +0.5% | 3.9% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| AAUC | book:6310ca122657f8b1 | 2026-09-11 | 1 | -5.3% | -5.3% / +0.5% | 3.9% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| AAUC | book:668a4e273abf21ff | 2026-09-11 | 1 | -5.3% | -5.3% / +0.5% | 3.9% | -1.4 | OTHER | OTHER | 0 | n/a |  |
| FSLR | conservative | 2026-08-11 | 1 | -5.2% | -5.2% / -8.1% | 3.9% | -1.3 | OTHER | OTHER | 2 | n/a |  |
| CALY | book:32adc8a0ec8ca0fe | 2026-09-11 | 5 | -5.2% | -1.5% / -5.2% | 5.0% | -1.0 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 3 | n/a |  |
| NVDA | hack4 | 2026-08-28 | 5 | +5.2% | +0.8% / +5.2% | 6.1% | +0.2 | SELECTABLE_BY_RULE | SECTOR_BETA | 22 | none |  |
| ADBE | conservative | 2026-08-11 | 1 | -5.2% | -5.2% / -3.6% | 3.2% | -1.6 | OTHER | OTHER | 3 | n/a |  |
| TDC | book:f46aaaa40b8c039a | 2026-09-11 | 1 | +5.2% | +5.2% / +3.5% | 4.1% | +1.3 | SELECTABLE_BY_RULE | OTHER | 1 | none |  |
| NOVT | book:9d62cc74239b435d | 2026-09-11 | 1 | -5.2% | -5.2% / -9.8% | 3.0% | -1.5 | OTHER | OTHER | 0 | n/a |  |
| PAYS | book:000b263cf7ec2286 | 2026-09-11 | 5 | -5.1% | -1.4% / -5.1% | 10.0% | -0.5 | OTHER | OTHER | 5 | n/a |  |
| NPO | book:9d62cc74239b435d | 2026-09-11 | 1 | -5.1% | -5.1% / -2.3% | 2.8% | -2.0 | OTHER | OTHER | 0 | n/a |  |
| SMR | hack6 | 2026-08-28 | 1 | -5.1% | -5.1% / -0.7% | 5.8% | -0.8 | OTHER | OTHER | 0 | n/a |  |
| IONQ | balanced | 2026-09-04 | 5 | -5.1% | +2.4% / -5.1% | 11.9% | -0.4 | OTHER | OTHER | 0 | n/a |  |
| IONQ | aggressive | 2026-09-04 | 5 | -5.1% | +2.4% / -5.1% | 11.9% | -0.4 | OTHER | OTHER | 0 | n/a |  |
| IONQ | balanced-ew-control | 2026-09-04 | 5 | -5.1% | +2.4% / -5.1% | 11.9% | -0.4 | OTHER | OTHER | 0 | n/a |  |
| DKNG | conservative | 2026-08-11 | 1 | +5.1% | +5.1% / -0.9% | 3.7% | +1.4 | OTHER | OTHER | 0 | none |  |
| ALM | book:f46aaaa40b8c039a | 2026-09-11 | 1 | -5.1% | -5.1% / -10.7% | 5.7% | -0.9 | OTHER | OTHER | 1 | n/a |  |
| HALO | book:60c4658f92c49e48 | 2026-09-11 | 5 | +5.1% | +0.9% / +5.1% | 6.8% | +0.7 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 2 | none |  |
| GOOGL | conservative | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | +2.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| GOOGL | balanced | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | +2.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| GOOGL | aggressive | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | +2.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| GOOGL | balanced-ew-control | 2026-09-11 | 1 | +5.0% | +5.0% / +5.1% | 2.3% | +2.2 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 3 | none |  |
| MSFT | conservative | 2026-08-11 | 5 | -5.0% | -2.9% / -5.0% | 6.5% | -0.7 | OTHER | OTHER | 4 | n/a |  |
| MLYS | hack6 | 2026-09-02 | 1 | +4.9% | +4.9% / +8.8% | 3.0% | +3.6 | SELECTABLE_BY_RULE | OTHER | 4 | none |  |
| MAZE | hack6 | 2026-09-17 | 1 | -4.6% | -4.6% / -- | 2.9% | -2.0 | ATTENTION_REFLEXIVITY | ATTENTION_REFLEXIVITY | 0 | n/a |  |
| ATR | hack6 | 2026-09-08 | 1 | -3.3% | -3.3% / -1.2% | 1.4% | -3.0 | SECTOR_BETA | SECTOR_BETA | 0 | n/a |  |
| BIP | book:60c4658f92c49e48 | 2026-09-11 | 1 | -3.1% | -3.1% / -1.9% | 1.6% | -2.1 | SECTOR_BETA | SECTOR_BETA | 1 | n/a |  |
| PFE | conservative | 2026-08-11 | 1 | -2.7% | -2.7% / +0.7% | 1.3% | -2.2 | OTHER | OTHER | 0 | n/a |  |
| NGG | book:9d62cc74239b435d | 2026-09-11 | 1 | -2.2% | -2.2% / +0.2% | 1.2% | -2.1 | OTHER | OTHER | 0 | n/a |  |

## Supplement: the ~10% books at h = 6 (2026-09-21)

Outside the declared window (h in 1, 5); printed because that session is where their gain came from.

| ticker | book | entry | h | move | move h1 / h5 | sigma_h | z | class | ex-post label | rules holding | credited | candidate feature |
|---|---|---|---:|---:|---|---:|---:|---|---|---:|---|---|
| TWST | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +30.5% | -- / -- | 13.6% | +2.2 | SELECTABLE_BY_RULE | OTHER | 14 | none |  |
| NUAI | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +28.8% | -- / -- | 19.4% | +1.5 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 19 | none |  |
| NUAI | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +28.8% | -- / -- | 19.4% | +1.5 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 19 | none |  |
| AXTI | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +21.9% | -- / -- | 25.6% | +0.9 | SELECTABLE_BY_RULE | ANALYST_CASCADE | 31 | none |  |
| AXTI | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +21.9% | -- / -- | 25.6% | +0.9 | SELECTABLE_BY_RULE | ANALYST_CASCADE | 31 | none |  |
| AXTI | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +21.9% | -- / -- | 25.6% | +0.9 | SELECTABLE_BY_RULE | ANALYST_CASCADE | 31 | none |  |
| PRAX | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | -11.7% | -- / -- | 9.5% | -1.1 | OTHER | OTHER | 18 | n/a |  |
| SNDK | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +7.6% | -- / -- | 20.7% | +0.4 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 60 | none |  |
| SNDK | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +7.6% | -- / -- | 20.7% | +0.4 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 60 | none |  |
| SNDK | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +7.6% | -- / -- | 20.7% | +0.4 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 60 | none |  |
| WOLF | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +6.9% | -- / -- | 18.9% | +0.4 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 25 | none |  |
| WOLF | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | +6.9% | -- / -- | 18.9% | +0.4 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 25 | none |  |
| WOLF | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | +6.9% | -- / -- | 18.9% | +0.4 | SELECTABLE_BY_RULE | UNFORESEEABLE_NEWS | 25 | none |  |
| MU | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | +6.7% | -- / -- | 14.5% | +0.5 | SELECTABLE_BY_RULE | RIGHT_STOCK_WRONG_REASON | 60 | none |  |
| ERAS | book:8dbbb73b6159d61d * | 2026-09-11 | 6 | -5.9% | -- / -- | 10.4% | -0.5 | OTHER | OTHER | 22 | n/a |  |
| ERAS | book:b109c8861c43e3c6 * | 2026-09-11 | 6 | -5.9% | -- / -- | 10.4% | -0.5 | OTHER | OTHER | 22 | n/a |  |
| ERAS | book:3b3e7049e693c3e4 * | 2026-09-11 | 6 | -5.9% | -- / -- | 10.4% | -0.5 | OTHER | OTHER | 22 | n/a |  |

`*` = one of the ~10% books Murat named (abstention, always-invested, 12-1 momentum).
