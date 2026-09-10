# NIGHT FACTORY 2026-09-08 -- leaderboard

Two rulers, two lists (ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md section 1).
A row is never deleted for failing the first ruler; it moves to the second with a
typed status: PRODUCT_PROMISING / CONDITIONAL / BETA_ONLY / FAILED_VARIANT.
`family max p` is Holm over the job's own family, or `--` where the job has none.

## RESEARCH_PROVEN (alpha ruler: Holm, three eras, placebo)

(nothing yet -- a row lands here only from a pre-registered lane)

## PRODUCT_PROMISING (product ruler: beta first, terminal wealth at a drawdown budget)

| job | run | status | headline | family max p | utc |
|---|---|---|---|---|---|
| D1_reaction_book | 1 | FAILED_VARIANT | top-decile reaction, hold 21, 25bps: beta 1.4047, beta-matched -4.138%/yr t -1.089, TW 3.7635 vs market 8.2595, DD -55.459%; placebo t -2.672 | 0.27599417 | 2026-09-08T13:59:28+00:00 |
| D2_reaction_mutations | 1 | SCREEN | best DEV variant z_scored_reaction_top_decile: t 2.13 (Holm 0.3315282) | 1.0 | 2026-09-08T14:00:07+00:00 |
| D3_matched_control_grid | 1 | PRODUCT_PROMISING | long-short reaction decile, hold 21, 25bps both legs: beta -0.2192, beta-matched 15.919%/yr t 3.864, TW 20.1684, DD -54.726%; placebo LS t 0.02; bottom-vs-its-o | 0.0321692 | 2026-09-08T14:55:45+00:00 |
| D4_ls_robustness_and_decay | 1 | CONTROL_ALSO_FIRES | 48/48 construction corners keep the long-short at \|t\|>2 (placebo: 8/48); at D3's own corner 15.919%/yr t 3.864; decay 21.19%/yr t 2.74 | -- | 2026-09-08T15:03:16+00:00 |
| N1_train_reaction_learner | 1 | FAILED_VARIANT | primary H21\|all\|s0: pooled Spearman IC 0.04707; long-short beta-matched 3.603%/yr t 0.604, TW 0.9831, DD -86.481%; placebo learner LS t -0.636 | -- | 2026-09-08T15:30:21+00:00 |
| N1_train_reaction_learner | 2 | FAILED_VARIANT | primary H21\|all\|s0: pooled Spearman IC 0.04707; long-short beta-matched 3.603%/yr t 0.604, TW 0.9831, DD -86.481%; placebo learner LS t -0.636 | -- | 2026-09-08T17:21:54+00:00 |
| G1_evolve | 1 | DEV ARCHIVE | 40680 genomes evaluated on DEV; best fitness 6.21341 (TW 547.9409 vs mkt 2.7103, beta 1.1232, bm t 4.727, DD -0.3776) | -- | 2026-09-08T21:00:09+00:00 |
| G2_holdout_once | 1 | see archive_on_holdout: | 35 archive genomes read on the holdout once against 0 random genomes | -- | 2026-09-09T00:24:23+00:00 |
| G2_holdout_once | 2 | see archive_on_holdout: | 35 archive genomes read on the holdout once against 200 random genomes | -- | 2026-09-09T00:26:34+00:00 |
| RW1_random_windows | 1 | DESCRIPTIVE | 240 random windows x 6 strategies x 2 constructions; best excess beta-matched win rate over the null: G1_best_dev_genome_ALREADY_READ_ON_HOLDOUT\|arena_k50_vw + | -- | 2026-09-09T02:18:38+00:00 |
| RW1_random_windows | 2 | DESCRIPTIVE | 240 random windows x 6 strategies x 2 constructions; best excess beta-matched win rate over the null: G1_best_dev_genome_ALREADY_READ_ON_HOLDOUT\|arena_k50_vw + | -- | 2026-09-09T03:04:16+00:00 |
| RW2_event_windows | 1 | DESCRIPTIVE | 240 random windows; at the tradable corner ($10m floor, 200 bps borrow) the reaction long-short beats its own control in 0.713 of windows (median 8.57%/yr) and  | -- | 2026-09-09T03:11:59+00:00 |
| P6_bars_and_regret | 1 | PANEL BUILT | 1,248,370 daily bars for 3060 symbols over 421 sessions, 2025-01-01..2026-09-08 \| benchmarks 2025-01..today: best mechanical book EW_universe at 58.859% vs SPY | -- | 2026-09-09T03:18:40+00:00 |
| P6_bars_and_regret | 2 | DESCRIPTIVE | benchmarks 2025-01..today: best mechanical book REV_1M at 81.055% vs SPY 33.264%; worst live book vs SPY on its own sessions: hack3 -9.38 pp over 6 sessions | -- | 2026-09-09T03:26:07+00:00 |
| P6_bars_and_regret | 3 | DESCRIPTIVE | benchmarks 2025-01..today (survivorship-free rows only): best INDEX_QQQ at 41.839% vs SPY 33.264%; worst live book vs SPY on its own sessions: hack3 -9.38 pp ov | -- | 2026-09-09T03:26:38+00:00 |
| N2_learner_v3 | 1 | FAILED_VARIANT | v3 (panel + event) vs v2 (panel only), paired over 251 months: 2.267%/yr t 1.047; the DATELESS control adds 2.78%/yr t 1.888; incremental -0.513%/yr | -- | 2026-09-09T03:39:31+00:00 |
| R2_monthly_llm_2022 | 1 | UNDERPOWERED | 2022: 1054 cells over 12 month blocks; masked read 8.252%/yr vs shuffled control 3.347%/yr -> 4.904%/yr t 1.155; AMNESIA gap -0.0132; MDE 51.25%/yr | -- | 2026-09-09T03:46:30+00:00 |
| RW1_random_windows | 3 | DESCRIPTIVE | 240 random windows x 6 strategies x 2 constructions; best excess beta-matched win rate over the null: ensemble_3\|arena_k50_vw +0.42 (win 0.575, null 0.155, med | -- | 2026-09-09T03:53:27+00:00 |
| N1H5_prereg_read | 1 | REJECTED | TRIAL-H5 single registered read: learner minus control at the $10m floor with 100 bps borrow, seed-median over 13 seeds = 20.786%/yr t 1.142 on 156 monthly bloc | -- | 2026-09-09T03:54:07+00:00 |
| RW1_pooled | 1 | NO CELL clears the thres | 3 draws, 720 windows; 0 of 12 cells clear 'excess - dispersion >= 0.15 in every era'; best by excess-minus-dispersion: G1_best_dev_genome_ALREADY_READ_ON_HOLDOU | -- | 2026-09-09T03:54:36+00:00 |
| P6_bars_and_regret | 4 | DESCRIPTIVE | benchmarks 2025-01..today (survivorship-free rows only): best INDEX_QQQ at 41.839% vs SPY 33.264%; worst live book vs SPY on its own sessions: hack3 -9.38 pp ov | -- | 2026-09-09T04:11:02+00:00 |
| R2_monthly_llm_2015_2024 | 1 | UNDERPOWERED | 2015-2024: 7417 cells over 112 month blocks; masked read 21.845%/yr vs shuffled control 5.656%/yr -> 16.189%/yr t 3.922; AMNESIA gap -0.0041; MDE 18.56%/yr | -- | 2026-09-09T05:25:02+00:00 |
| G3_evolve | 1 | DEV ARCHIVE | 2373 evaluations over 437 generations, 595 distinct genomes in 251 lineages; best out-of-bank median excess over the random-genome null 20.2612%/yr (selection b | -- | 2026-09-09T07:18:01+00:00 |
| D3_matched_control_grid | 99 | ERA_DECAYED | AMENDMENT to D3_matched_control_grid_run01.json: The receipt's own verdict string was stamped by a rule that counted era SIGNS. All three eras are positive in s | -- | 2026-09-08T14:57:36+00:00 |
| G3_evolve | 99 | CONDITIONAL | AMENDMENT to G3_evolve_run01.json: the run stamped PRODUCT_PROMISING on a DEV-only archive whose null bar was not held to the same drawdown refusal as the arm,  | -- | 2026-09-09T08:15:00+00:00 |
| R2_monthly_llm_2015_2024 | 99 | CONDITIONAL | AMENDMENT to R2_monthly_llm_2015_2024_run01.json: the run stamped itself UNDERPOWERED against a PRE-HOC MDE whose standard error was 1.61x too large; the realis | -- | 2026-09-09T05:45:00+00:00 |
