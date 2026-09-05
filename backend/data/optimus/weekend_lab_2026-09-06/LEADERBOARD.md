# WEEKEND LAB 2026-09-06 -- leaderboard

One line per job per pass. `family max p` is the multiplicity-corrected
p-value where a family exists; a job with no family says so rather than
quoting a single-cell number as if it were one. `yrs->t2` is the years of
tape a t = 2 would need at the arm's own Sharpe -- the number that decides
whether a null verdict means NOISE or means NOT ENOUGH TAPE.

<!-- BEST SO FAR -->
**BEST SO FAR (ranked by DEFLATED Sharpe, not by return)** -- rewritten 2026-09-05T04:31:36+00:00

- **W5b_options_book pass 2 variant 0** -- best of 24 options-book cells is sig_cp_iv_spread_30d|10bps|rebuild|covered_univ at -0.019%/month over 309 months; DSR 0.0207, SPA p 1.0, PBO 0.2429, t2 needs Noney vs 25.75y
- DSR **0.0207** | SPA p 1.0 | PBO 0.2429 | verdict **NOISE**
- 309 out-of-sample months (25.75 years); t = 2 would need **None** years at this Sharpe
- three-era sign table: {'1999-2007': {'months': 106, 'mean_pct': 0.1095, 't': 0.181, 'sign': 1}, '2008-2015': {'months': 96, 'mean_pct': 0.3759, 't': 0.801, 'sign': 1}, '2016-2024': {'months': 107, 'mean_pct': -0.5002, 't': -1.129, 'sign': -1}, 'eras_with_a_positive_mean': 2, 'eras_with_a_negative_mean': 1, 'eras_measured': 3, 'holds_in_2_of_3': True, 'same_sign_in_2_of_3': True, 'dominant_sign': 1}
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
