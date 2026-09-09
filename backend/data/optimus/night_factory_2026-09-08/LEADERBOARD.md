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
| D4_ls_robustness_and_decay | 1 | CONTROL_ALSO_FIRES: 48/4 | 48/48 construction corners keep the long-short at |t|>2 (placebo: 8/48); at D3's own corner 15.919%/yr t 3.864; decay 21.19%/yr t 2.74 | -- | 2026-09-08T15:03:16+00:00 |
| N1_train_reaction_learner | 1 | FAILED_VARIANT | primary H21|all|s0: pooled Spearman IC 0.04707; long-short beta-matched 3.603%/yr t 0.604, TW 0.9831, DD -86.481%; placebo learner LS t -0.636 | None | 2026-09-08T15:30:21+00:00 |
| N1_train_reaction_learner | 2 | FAILED_VARIANT | primary H21|all|s0: pooled Spearman IC 0.04707; long-short beta-matched 3.603%/yr t 0.604, TW 0.9831, DD -86.481%; placebo learner LS t -0.636 | None | 2026-09-08T17:21:54+00:00 |
| G1_evolve | 1 | DEV ARCHIVE | 40680 genomes evaluated on DEV; best fitness 6.21341 (TW 547.9409 vs mkt 2.7103, beta 1.1232, bm t 4.727, DD -0.3776) | None | 2026-09-08T21:00:09+00:00 |
| G2_holdout_once | 1 | see archive_on_holdout:  | 35 archive genomes read on the holdout once against 0 random genomes | None | 2026-09-09T00:24:23+00:00 |
| G2_holdout_once | 2 | see archive_on_holdout:  | 35 archive genomes read on the holdout once against 200 random genomes | None | 2026-09-09T00:26:34+00:00 |
| RW1_random_windows | 1 | DESCRIPTIVE | 240 random windows x 6 strategies x 2 constructions; best excess beta-matched win rate over the null: G1_best_dev_genome_ALREADY_READ_ON_HOLDOUT|arena_k50_vw +0 | -- | 2026-09-09T02:18:38+00:00 |
