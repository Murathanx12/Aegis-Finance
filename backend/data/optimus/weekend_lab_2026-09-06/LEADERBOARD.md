# WEEKEND LAB 2026-09-06 -- leaderboard

One line per job per pass. `family max p` is the multiplicity-corrected
p-value where a family exists; a job with no family says so rather than
quoting a single-cell number as if it were one. `yrs->t2` is the years of
tape a t = 2 would need at the arm's own Sharpe -- the number that decides
whether a null verdict means NOISE or means NOT ENOUGH TAPE.

<!-- BEST SO FAR -->
**BEST SO FAR (ranked by DEFLATED Sharpe, not by return)** -- rewritten 2026-09-05T05:05:19+00:00

- **W3_neural_long pass 9 variant 0** -- [cuda] best of 20 cells is nn_s20260912|10bps at +1.998%/month vs market over 251 months (TW net 561.0604 vs market 14.3778); DSR 0.9835, SPA p 0.016, PBO 0.0857, t2 needs 6.7y vs 20.92y on hand. vs LGBM (TW 16.752 @10bps): best neural arm is 16.617%/yr (t 2.533), DSR 0.7467 -- the neural arm's advantage over lgbm does NOT survive the family
- DSR **0.9835** | SPA p 0.016 | PBO 0.0857 | verdict **NOISE (clears the market bar, does NOT beat lgbm)**
- 251 out-of-sample months (20.92 years); t = 2 would need **6.7** years at this Sharpe
- three-era sign table: {'1999-2007': {'months': 48, 'mean_pct': 0.4318, 't': 0.61, 'sign': 1}, '2008-2015': {'months': 96, 'mean_pct': 1.9587, 't': 2.825, 'sign': 1}, '2016-2024': {'months': 107, 'mean_pct': 2.7352, 't': 2.438, 'sign': 1}, 'eras_with_a_positive_mean': 3, 'eras_with_a_negative_mean': 0, 'eras_measured': 3, 'holds_in_2_of_3': True, 'same_sign_in_2_of_3': True, 'dominant_sign': 1}
<!-- /BEST SO FAR -->

| job | pass | v | headline | DSR | SPA p | PBO | n_oos_m | yrs->t2 | verdict |
|---|---|---|---|---|---|---|---|---|---|
| W1_long_panel_inventory | 1 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 1 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 2 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 2 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W5_options_iv | 2 | 1 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 2 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W4_graph_momentum | 2 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 2 | 1 | 297 formation months, 100 winners x 3 matched controls each; 5 candidates over 3 DISTINCT ideas (['a | -- | -- | -- | -- | -- | NOVEL |
| W8_states_three_nulls | 2 | 0 | k=4 market states over 286 months; market circular-shift p 0.578 (observed spread 0.008268 vs null p | -- | -- | -- | -- | -- | NOISE |
| W3_neural_long | 2 | 1 | not built yet: GPU encoder pass pending | -- | -- | -- | -- | -- | DEFERRED |
| W11_evidence_writeback | 2 | 0 | 12 receipts -> 67 cell observations; 55 cells tracked; states {'IDEA': 47, 'REGIME_SPECIFIC': 2, 'SU | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 3 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 3 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W5_options_iv | 3 | 0 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 3 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W4_graph_momentum | 3 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 3 | 2 | 303 formation months, 50 winners x 5 matched controls each; 6 candidates over 3 DISTINCT ideas (['an | -- | -- | -- | -- | -- | NOVEL |
| W8_states_three_nulls | 3 | 0 | k=4 market states over 286 months; market circular-shift p 0.578 (observed spread 0.008268 vs null p | -- | -- | -- | -- | -- | NOISE |
| W3_neural_long | 3 | 2 | not built yet: GPU encoder pass pending | -- | -- | -- | -- | -- | DEFERRED |
| W11_evidence_writeback | 3 | 0 | 21 receipts -> 120 cell observations; 56 cells tracked; states {'IDEA': 41, 'REGIME_SPECIFIC': 2, 'S | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 4 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 4 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W5_options_iv | 4 | 1 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 4 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W4_graph_momentum | 4 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 4 | 3 | 297 formation months, 25 winners x 8 matched controls each; 8 candidates over 3 DISTINCT ideas (['an | -- | -- | -- | -- | -- | NOVEL |
| W8_states_three_nulls | 4 | 0 | k=4 market states over 286 months; market circular-shift p 0.578 (observed spread 0.008268 vs null p | -- | -- | -- | -- | -- | NOISE |
| W3_neural_long | 4 | 3 | not built yet: GPU encoder pass pending | -- | -- | -- | -- | -- | DEFERRED |
| W11_evidence_writeback | 4 | 0 | 30 receipts -> 175 cell observations; 57 cells tracked; states {'IDEA': 42, 'REGIME_SPECIFIC': 2, 'S | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 5 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 5 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W5_options_iv | 5 | 0 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 5 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W4_graph_momentum | 5 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W1_long_panel_inventory | 6 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 6 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W6b_liquidity_band | 6 | 0 | S28 band vs the EW REST of the universe on 26 years: 0.851%/yr t 0.503; out-of-sample 1999-2012 t 1. | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W5_options_iv | 6 | 1 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 6 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W5c_options_exclusion | 6 | 0 | 6 base x cost cells; best screen-minus-random is 0.1714%/month (t 1.272) on mom_12_1@25bps; 0 of 6 c | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W4_graph_momentum | 6 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 6 | 1 | 297 formation months, 100 winners x 3 matched controls each; 5 candidates over 3 DISTINCT ideas (['a | -- | -- | -- | -- | -- | NOVEL |
| W7b_archetype_book | 6 | 0 | best of 20 archetype cells is arch_raw|10bps|rebuild at +0.076%/month over 308 months (size-neutral  | 0.0515 | 0.7465 | 0.2 | 308 | 1380.1 | CANNOT DETERMINE (underpowered) |
| W8_states_three_nulls | 6 | 2 | k=6 market states over 286 months; market circular-shift p 0.062 (observed spread 0.020108 vs null p | -- | -- | -- | -- | -- | NOISE |
| W3_neural_long | 6 | 1 | not built yet: GPU encoder pass pending | -- | -- | -- | -- | -- | DEFERRED |
| W11_evidence_writeback | 6 | 0 | 47 receipts -> 311 cell observations; 97 cells tracked; states {'IDEA': 81, 'REGIME_SPECIFIC': 2, 'S | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 7 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 7 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W6b_liquidity_band | 7 | 0 | S28 band vs the EW REST of the universe on 26 years: 0.851%/yr t 0.503; out-of-sample 1999-2012 t 1. | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W5_options_iv | 7 | 0 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 7 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W5c_options_exclusion | 7 | 0 | 6 base x cost cells; best screen-minus-random is 0.1714%/month (t 1.272) on mom_12_1@25bps; 0 of 6 c | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W4_graph_momentum | 7 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W1_long_panel_inventory | 8 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 8 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W6b_liquidity_band | 8 | 0 | S28 band vs the EW REST of the universe on 26 years: 0.851%/yr t 0.503; out-of-sample 1999-2012 t 1. | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W5_options_iv | 8 | 1 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 8 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W5c_options_exclusion | 8 | 0 | 6 base x cost cells; best screen-minus-random is 0.1714%/month (t 1.272) on mom_12_1@25bps; 0 of 6 c | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W4_graph_momentum | 8 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 8 | 3 | 297 formation months, 25 winners x 8 matched controls each; 8 candidates over 3 DISTINCT ideas (['an | -- | -- | -- | -- | -- | NOVEL |
| W7b_archetype_book | 8 | 0 | best of 20 archetype cells is arch_raw|10bps|rebuild at +0.076%/month over 308 months (size-neutral  | 0.0515 | 0.7465 | 0.2 | 308 | 1380.1 | CANNOT DETERMINE (underpowered) |
| W8_states_three_nulls | 8 | 1 | k=5 market states over 286 months; market circular-shift p 0.112 (observed spread 0.017384 vs null p | -- | -- | -- | -- | -- | NOISE |
| W9_survivor_books | 8 | 0 | 12 weekend survivors booked (24 cells): 5 beat the market NET, 10 beat it GROSS; 5 of them have thei | 0.5293 | 0.1078 | 0.2286 | 308 | 24.3 | DECAYED (worked, then stopped) |
| W3_neural_long | 8 | 3 | not built yet: GPU encoder pass pending | -- | -- | -- | -- | -- | DEFERRED |
| W11_evidence_writeback | 8 | 0 | 68 receipts -> 499 cell observations; 122 cells tracked; states {'IDEA': 86, 'REGIME_SPECIFIC': 2, ' | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 9 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 9 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W6b_liquidity_band | 9 | 0 | S28 band vs the EW REST of the universe on 26 years: 0.851%/yr t 0.503; out-of-sample 1999-2012 t 1. | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W5_options_iv | 9 | 0 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 9 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W5c_options_exclusion | 9 | 0 | 6 base x cost cells; best screen-minus-random is 0.1714%/month (t 1.272) on mom_12_1@25bps; 0 of 6 c | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W4_graph_momentum | 9 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 9 | 0 | 297 formation months, 50 winners x 5 matched controls each; 8 candidates over 3 DISTINCT ideas (['an | -- | -- | -- | -- | -- | NOVEL |
| W7b_archetype_book | 9 | 0 | best of 20 archetype cells is arch_raw|10bps|rebuild at +0.076%/month over 308 months (size-neutral  | 0.0515 | 0.7465 | 0.2 | 308 | 1380.1 | CANNOT DETERMINE (underpowered) |
| W8_states_three_nulls | 9 | 2 | k=6 market states over 286 months; market circular-shift p 0.062 (observed spread 0.020108 vs null p | -- | -- | -- | -- | -- | NOISE |
| W9_survivor_books | 9 | 0 | 12 weekend survivors booked (24 cells): 5 beat the market NET, 10 beat it GROSS; 5 of them have thei | 0.5293 | 0.1078 | 0.2286 | 308 | 24.3 | DECAYED (worked, then stopped) |
| W3_neural_long | 9 | 0 | [cuda] best of 20 cells is nn_s20260912|10bps at +1.998%/month vs market over 251 months (TW net 561 | 0.9835 | 0.016 | 0.0857 | 251 | 6.7 | NOISE (clears the market bar, does NOT beat lgbm) |
| W11_evidence_writeback | 9 | 0 | 81 receipts -> 637 cell observations; 142 cells tracked; states {'IDEA': 134, 'SUPPORTED': 7, 'CONDI | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 10 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 10 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | NOVEL |
| W6b_liquidity_band | 10 | 0 | S28 band vs the EW REST of the universe on 26 years: 0.851%/yr t 0.503; out-of-sample 1999-2012 t 1. | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W5_options_iv | 10 | 1 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 10 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | NOISE |
| W5c_options_exclusion | 10 | 0 | 6 base x cost cells; best screen-minus-random is 0.1714%/month (t 1.272) on mom_12_1@25bps; 0 of 6 c | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W4_graph_momentum | 10 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W7_matched_loser | 10 | 1 | 297 formation months, 100 winners x 3 matched controls each; 5 candidates over 3 DISTINCT ideas (['a | -- | -- | -- | -- | -- | NOVEL |
| W7b_archetype_book | 10 | 0 | best of 20 archetype cells is arch_raw|10bps|rebuild at +0.076%/month over 308 months (size-neutral  | 0.0515 | 0.7465 | 0.2 | 308 | 1380.1 | CANNOT DETERMINE (underpowered) |
| W8_states_three_nulls | 10 | 0 | k=4 market states over 286 months; market circular-shift p 0.578 (observed spread 0.008268 vs null p | -- | -- | -- | -- | -- | NOISE |
| W9_survivor_books | 10 | 0 | 12 weekend survivors booked (24 cells): 5 beat the market NET, 10 beat it GROSS; 5 of them have thei | 0.2022 | 0.1078 | 0.2286 | 308 | 24.3 | DECAYED (worked, then stopped) |
| W3_neural_long | 10 | 1 | [cuda] best of 38 cells is nn_pre_causal_s20260906|10bps at +1.987%/month vs market over 251 months  | 0.9081 | 0.02 | 0.4571 | 251 | 8.3 | NOISE |
| W11_evidence_writeback | 10 | 0 | 93 receipts -> 815 cell observations; 256 cells tracked; states {'IDEA': 244, 'SUPPORTED': 11, 'COND | -- | -- | -- | -- | -- | INVENTORY |
| W1_long_panel_inventory | 11 | 0 | 925,757 name-months over 310 months (1999-2024); early-era share-basis gate PASS; incumbent panel ha | -- | -- | -- | -- | -- | INVENTORY |
| W6_behavioural | 11 | 0 | 7 behavioural features on 925,757 rows; 3 clear |t| >= 2 WITH controls and keep one sign in 2 of 3 e | -- | -- | -- | -- | -- | SCREEN_SURVIVOR (3 of 7, controlled |t| >= 2 AND one sign in 2 of 3 eras; no formal multiplicity correction on 7 features) |
| W6b_liquidity_band | 11 | 0 | S28 band vs the EW REST of the universe on 26 years: 0.851%/yr t 0.503; out-of-sample 1999-2012 t 1. | -- | -- | -- | -- | -- | CANNOT DETERMINE (underpowered) |
| W5_options_iv | 11 | 0 | 5 option-surface features on 925,757 panel rows (worst column matches 71.5% of them); 2 clear |t| >= | -- | -- | -- | -- | -- | NOVEL |
| W5b_options_book | 11 | 0 | best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month ov | 0.0207 | 1.0 | 0.2429 | 309 | -- | CANNOT DETERMINE (underpowered; this arm could only have shown an effect of 7.1%/yr or larger) |
| W5c_options_exclusion | 11 | 0 | 6 base x cost cells; best screen-minus-random is 0.1714%/month (t 1.272) on mom_12_1@25bps; 0 of 6 c | -- | -- | -- | -- | -- | NOISE |
| W4_graph_momentum | 11 | 0 | 9 graph features on 12 of 26 panel years (2014-05-01..2025-01-01), 386 of 8,981 panel names; 0 clear | -- | -- | -- | -- | -- | NOISE |
| W7_matched_loser | 11 | 2 | 303 formation months, 50 winners x 5 matched controls each; 7 candidates over 3 DISTINCT ideas (['an | -- | -- | -- | -- | -- | SCREEN_SURVIVOR (5 of 49, Holm <= 0.05 on the non-overlapping t, 5 of 7 candidates) |
| W7b_archetype_book | 11 | 0 | best of 20 archetype cells is arch_raw|10bps|rebuild at +0.076%/month over 308 months (size-neutral  | 0.0515 | 0.7465 | 0.2 | 308 | 1380.1 | CANNOT DETERMINE (underpowered; this arm could only have shown an effect of 6.6%/yr or larger) |
| W8_states_three_nulls | 11 | 1 | k=5 market states over 286 months; market circular-shift p 0.112 (observed spread 0.017384 vs null p | -- | -- | -- | -- | -- | NOISE |
| W9_survivor_books | 11 | 0 | 14 weekend survivors booked (28 cells): 8 beat the market NET, 18 beat it GROSS; 6 of them have thei | 0.1993 | 0.1257 | 0.1429 | 308 | 24.3 | DECAYED (worked, then stopped) |
