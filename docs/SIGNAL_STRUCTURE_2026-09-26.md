# Signal structure of the strategy library — 2026-09-26

> **HINDSIGHT.** Every rule was written on 2026-09-26, after every month scored here. Licence
> `PRODUCT_EXPERIMENT`, $0, no LLM. Run `2026-09-26T150811Z` (the last VALID factory run; `T153843Z`
> is INVALID and was not read). Reviewer D+E idea #1 (`docs/reviews/REVIEW_2026-09-26_CHUNKS_D_E.md`).
>
> Receipt `backend/data/optimus/signal_structure/signal_structure_2026-09-26T150811Z.json` ·
> series `monthly_returns_2026-09-26T150811Z.parquet` (115 months x 880 cells, monthly NET) ·
> ETF cache `etf_monthly.parquet` (+ `etf_monthly.json` stamp, fetched 2026-09-26T16:00Z) · every table
> in `tables_2026-09-26T150811Z.md` · code `backend/services/signal_structure.py`,
> `python -m scripts.signal_structure`.

**RESULT IMPROVEMENT: NONE (a denominator and a diagnosis, not a new edge).**

## How the series were obtained

The committed factory checkpoint (`git show HEAD:.../checkpoint_2026-09-26.json`) carries every
cell's `active_returns` (net − SPY, one per month, no gaps). Its panel fingerprint is
`97412eb7aeecf327`, which equals the run receipt's. The working-tree checkpoint was rewritten by the
INVALID run, and the script refuses it by fingerprint.

Net = active + SPY. SPY is rebuilt with the factory's own `spy_leg` construction: yfinance adjusted
close, compounded over (month-end, next month-end]. **Check:** compounded by-year net matches the
checkpoint's own `by_year` to **1.4e-5** at worst, over 8,752 rule-years. No holdings were re-run,
because the receipt already carried the series.

Coverage: 880 cells have series (849 trial cells + 31 control cells). 5 were refused: 3 FORWARD_ONLY
rules and 2 control cells with no month of k = 50 names.

## 1. The number of distinct bets

Clustering is average linkage on 1 − ρ of monthly ACTIVE returns, cut at ρ = 0.8. A pair needs at
least 24 overlapping months in the window.

| scope | dev (83 months) | 2024-26 (32 months) | full (115 months) |
|---|---|---|---|
| 849 trial cells (rule x k) | **264** | **312** | **292** |
| 282 rules (primary k) | **178** | **181** | **187** |

**282 rules are about 180 bets. 849 cells are about 265-310.**

The biggest cluster is momentum: 17 rules spread across **ten nominal families**, with mean inner ρ
0.85. The families are momentum, sector_relative, weighted, revision_flow, analyst_rating, insider,
earnings_event, filing_event, flow_momentum and analyst_dispersion. So the board's "32 families"
overstates how diverse its winners are.

In 2024-26, low-vol collapses the same way: 13 low-vol rules (9 from the low_risk family) are one bet, and 12 quality/low-vol
combinations are another.

### Multiplicity: DSR at n = clusters beside n = cells

| window | best cluster representative | months | DSR @ n = 849 cells | DSR @ n = clusters |
|---|---|---|---|---|
| full | `eap_mom@k10` | 115 | 0.441 | **0.577** (n = 292) |
| dev | `mom_no_downgrades_small@k10` | 83 | 0.348 | **0.492** (n = 264) |
| 2024-26 | `eap_mom@k10` | 32 | 0.263 | **0.367** (n = 312) |

Take the board's best primary row, `mom_12_1_q@k20`. Its DSR is 0.200 at n = 849, which reproduces
the leaderboard exactly. At n = 292 it is 0.310, and at n = 187 it is 0.366.

**The honest denominator raises every DSR, and still none reaches 0.95.** The library's null result
is not an artefact of over-counting trials.

### Rule-level clusters, full window (members ≥ 3)

| # | n | mean ρ | representative (highest dev DSR) | rep dev vs SPY | rep 2024-26 vs SPY | rep beat SPY both | families | members |
|---|---|---|---|---|---|---|---|---|
| 122 | 17 | 0.85 | `mom_no_downgrades` | +28.6% | +0.4% | yes | momentum 5, sector_relative 3, weighted 2, revision_flow, analyst_rating, insider, earnings_event, filing_event, flow_momentum, analyst_dispersion | disp_short_avoid, eap_avoid_mom, mom_12_1, mom_12_1_ivw, mom_12_1_q, mom_12_1_secrel, mom_12_7, mom_12m, mom_in_raised, mom_in_top_sectors, mom_no_downgrades, mom_no_exec_change, mom_no_insider_selling, mom_no_rating_downgrade, +3 |
| 96 | 10 | 0.89 | `net_raises` | +9.7% | +5.9% | yes | revision_flow 5, analyst_skill 2, flow_momentum, weighted, ibes_skill_weighted | flow_in_winners, flow_rule, flow_rule_large, flow_rule_q, ibes_skill_net_raises, net_raises, net_raises_ivw, net_raises_large, skill_raises, skill_raises_large |
| 107 | 7 | 0.87 | `gh11_skip_month_composite_q` | +8.4% | −18.6% | no | momentum 4, trend 3 | gh11_skip_month_composite_q, mom_6_1, mom_6_1_large, mom_6m, px_vs_ma200, px_vs_ma200_large, trend_ma50_200 |
| 105 | 7 | 0.87 | `mom_gp` | +14.9% | −4.0% | no | combination 3, regime_gated 2, quality, sector_relative | gp_at_large, mom_gp, mom_gp_large, qc536_secneutral_multimom_large, qc597_secneutral_multimom_calm, qc629_multimom_above_trend_gated, trend_quality_large |
| 27 | 5 | 0.88 | `lowvol_63_q` | −29.9% | −13.9% | no | low_risk 5 | low_idio_63, low_max, lowvol_21, lowvol_63, lowvol_63_q |
| 10 | 4 | 0.87 | `gp_lowvol_large` | +0.3% | −13.0% | no | combination 3, diversified_combo | div_agree_quality_lowvol, gp_lowvol, gp_lowvol_large, mom_gp_lowvol |
| 131 | 4 | 0.87 | `mom_flow_ivw` | +7.4% | +23.0% | yes | combination, analyst_skill, sector_relative, weighted | mom_flow, mom_flow_ivw, mom_flow_secrel, skill_mom |
| 119 | 4 | 0.92 | `qc395_sharpe252_above_trend_large` | +13.6% | +35.2% | yes | momentum 3, revision_flow | mom_12_1_large, mom_no_downgrades_large, qc395_sharpe252_above_trend_large, resid_mom_12_1_large |
| 165 | 4 | 0.86 | `rev_1m` | +9.0% | −0.8% | no | reversal 3, filing_event | distress_free_reversal, rev_1m, rev_1m_small, rev_in_winners |
| 88 | 3 | 0.86 | `big_dv` | +6.0% | +13.5% | yes | momentum, size_liquidity, trend | big_dv, mom_12_1_mega, qc768_golden_cross_mega |
| 55 | 3 | 0.93 | `gp_at_q` | +4.0% | −9.6% | no | quality 2, weighted | gp_at, gp_at_ivw, gp_at_q |
| 104 | 3 | 0.86 | `gp_low_ag` | +16.4% | +2.2% | yes | investment, combination, insider | gp_low_ag, insider_buyers_large, low_asset_growth_large |
| 142 | 3 | 0.86 | `inflection_large` | −1.6% | +3.8% | no | inflection 3 | inflection, inflection_large, inflection_mid_plus |
| 70 | 3 | 0.84 | `insider_before_print` | +2.2% | −12.5% | no | insider 2, earnings_event | insider_before_print, insider_buyers, insider_unconfirmed |
| 106 | 3 | 0.85 | `insider_mom` | +35.2% | −3.6% | no | combination, insider, diversified_combo | div_mom_insider_flow, insider_mom, mom_low_ag |
| 50 | 3 | 0.91 | `lead_raises_large` | +2.6% | −6.3% | no | lead_chase 3 | lead_minus_chase, lead_raises, lead_raises_large |
| 143 | 3 | 0.83 | `margin_expansion` | −6.2% | +4.5% | no | fund_inflection 2, quality | margin_expansion, margin_turn, rev_accel_margin |
| 77 | 3 | 0.95 | `mom_12_1_q_trend` | +10.4% | +20.8% | yes | regime_gated 3 | mom_12_1_q_trend, mom_12_1_trend, mom_no_downgrades_trend |
| 21 | 3 | 0.84 | `recovery_anchoring` | −24.2% | +0.7% | no | momentum, sector_relative, disposition | hi52, hi52_secrel, recovery_anchoring |

Beyond this table, the full window has 22 two-member clusters and 146 singletons. The tables file
also covers the dev and 2024-26 windows and the cell-level clusters. The receipt holds the same data
under `clusters.rules_dev`, `clusters.rules_sealed` and `clusters.cells_*`.

## 2. Decomposition on ETF spreads (SMH, IWM, MTUM, USMV, QUAL, VLUE, each minus SPY)

Mean monthly spreads in 2024-26 were:

- **SMH − SPY: +2.47%/month** (dev: +1.14%)
- MTUM − SPY: +0.63%
- VLUE − SPY: +0.86%
- IWM − SPY: −0.24%

In 2024-26, SMH − SPY correlates **0.69** with MTUM − SPY and **−0.69** with USMV − SPY. So the
regression fits seven parameters on 32 collinear blocks, and single betas are unstable. Read the alpha
t and R², not any one beta. The column `t a (SMH,MTUM only)` is the reviewer's two-regressor version.

How to read the table:

- The alpha `a` is monthly.
- `SMH+MTUM share` = (β_SMH × mean(SMH−SPY) + β_MTUM × mean(MTUM−SPY)) / mean active, over 2024-26.
  It is printed only when the rule beat SPY by at least 20 bps/month.
- Tags: [S] = 2024-26 top-30, [D] = dev top-30.

**2024-26 top-10** (the full 2024-26 top-30 and dev top-30 are in the tables file):

| rule | 2024-26 vs SPY | a 24-26 | t | b SMH | b IWM | b MTUM | b USMV | b QUAL | b VLUE | R2 | SMH+MTUM share | t a (SMH,MTUM only) | a dev | t dev | R2 dev | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `mom_12_1_liqw` [S] | +68.4% | +1.61% | +0.60 | +1.08 | +1.33 | +0.81 | -1.07 | -1.12 | +0.60 | +0.59 | +53% | +0.55 | -0.36% | -0.29 | +0.40 | MOSTLY SMH/MTUM BETA |
| `qc372_oversold_snapback_mega` [S] | +59.4% | +1.87% | +1.12 | -0.06 | -0.45 | +0.49 | -1.23 | -0.51 | +1.08 | +0.39 | +4% | +1.41 | -0.08% | -0.12 | +0.32 |  |
| `rev_5d` [S] | +48.4% | +2.13% | +1.71 | +0.47 | +1.26 | -0.15 | +0.20 | -2.39 | -0.09 | +0.47 | +33% | +1.43 | +0.27% | +0.23 | +0.41 |  |
| `qc623_mom63_liquidity_weighted` [S] | +46.3% | +0.78% | +0.34 | +0.98 | +1.79 | +0.04 | -1.19 | -0.46 | +0.80 | +0.61 | +56% | +0.20 | -0.23% | -0.23 | +0.15 | MOSTLY SMH/MTUM BETA |
| `mom_12_1_q` [SD] | +37.9% | +2.11% | +1.13 | +0.95 | +1.27 | -0.09 | +1.21 | -1.65 | -0.89 | +0.24 | +79% | +0.94 | +2.11% | +2.49 | +0.48 |  |
| `skill_mom` [S] | +37.0% | +1.42% | +1.20 | +0.35 | +0.77 | +0.55 | -0.76 | +0.56 | -0.10 | +0.57 | +44% | +0.87 | +0.32% | +0.67 | +0.48 |  |
| `margin_mom` [S] | +36.9% | +1.82% | +1.09 | +0.19 | +1.51 | +0.79 | -0.41 | -1.74 | -0.16 | +0.45 | +33% | +0.82 | +0.52% | +0.88 | +0.52 |  |
| `qc395_sharpe252_above_trend_large` [SD] | +35.2% | +0.43% | +0.21 | +0.39 | +0.25 | +0.88 | -0.92 | -1.02 | +0.53 | +0.47 | +47% | +0.30 | +1.08% | +1.31 | +0.27 | alpha t<1 after ETFs |
| `illiquid` [S] | +34.9% | +0.68% | +0.46 | -0.52 | +0.69 | +1.10 | -2.28 | -1.42 | +1.35 | +0.65 | -21% | +0.49 | -0.20% | -0.28 | +0.56 | alpha t<1 after ETFs |
| `qc470_mom252_quarterly_riskparity` [S] | +31.1% | +1.26% | +0.83 | +0.89 | +0.95 | +0.27 | +0.82 | -1.62 | -0.92 | +0.37 | +97% | +0.61 | +1.64% | +2.01 | +0.49 | MOSTLY SMH/MTUM BETA |

### Findings across the 2024-26 top-30

- **21 of 30 have alpha t < 1 once the six ETF spreads are in.** The median R² is 0.44.
- **17 of 30 are MOSTLY SMH/MTUM BETA.** Each one:
  - beat SPY by at least 20 bps/month;
  - has alpha t < 1 after the ETF spreads;
  - owes at least half of its mean active return to the SMH and MTUM legs.

  The 17 are `mom_12_1_liqw`, `qc623_mom63_liquidity_weighted`, `qc470_mom252_quarterly_riskparity`,
  `disp_short_avoid`, `resid_mom_12_1_large`, `mom_12_1_secrel`, `mom_12_1_ivw`, `frog_large`,
  `mom_flow_ivw`, `mom_flow`, `mom_12_1_large`, `mom_12_1_q_trend`, `ear_drift`,
  `px_vs_ma200_large`, `chase_raises`, `mom_6_1_large` and `eap_mom`.
- **The loading nobody named is IWM.** The median IWM − SPY beta is **+1.03**, against a median SMH
  beta of +0.43. The books are small-cap tilted, and in 2024-26 small caps lagged. So part of each
  printed alpha makes up for a size headwind; it is not skill.
- **`mom_12_1_q`, the board's best-DSR row.** 79% of its 2024-26 excess is SMH + MTUM. Its alpha t is
  1.13 in 2024-26, against 2.49 in dev.

**Survivors (alpha t ≥ 2 in BOTH windows): NONE.**

- One rule clears 2 in 2024-26 only: `co03_reversal_in_high_margin`, t 2.37 (dev t 0.43).
- Fifteen rules clear 2 in dev only. Momentum had real ETF-adjusted alpha before 2024: `mom_12_1`,
  `mom_no_downgrades`, `mom_12_1_small`, `mom_no_downgrades_small`, `insider_mom` and `small_gp_mom`
  show t 2.0-3.4 in dev. In 2024-26 all of it sits at t ≤ 1.2.
- So the 2024-26 "momentum win" is SMH/MTUM beta. The pre-2024 momentum alpha did not carry into it.

The t-statistics use plain OLS standard errors. Quarterly (hold > 1) books have serially dependent
months, so their t is optimistic, which only strengthens "no survivors".

## 3. Lead-lag across families (HYPOTHESIS, never finding)

**Setup.** Each of the 187 rule-level cluster representatives (full window) was cross-correlated
with two series:

- (a) the library's own `mom_12_1@k20` active return;
- (b) SMH − SPY.

Lags were +1 and +2 months, in both directions: **1,496 tests**, n ≈ 113. Under the null,
P(|ρ| ≥ 0.3) = 0.0017, so about **2.5 false hits** are expected.

**Two hits were observed, which is the noise rate:**

| representative | leader | lag | ρ | n | ρ dev / 2024-26 | partial t (own lags + MTUM lag) | **ρ without 2020** |
|---|---|---|---|---|---|---|---|
| `gp_low_ag@k20` | mom_12_1 active | +2 | +0.37 | 113 | 0.40 / 0.36 | 3.85 | **+0.05** (n 101) |
| `mom_gp@k20` | mom_12_1 active | +2 | +0.34 | 113 | 0.39 / 0.15 | 4.97 | **−0.08** (n 101) |

- **H1: "momentum's active return leads quality/low-investment by two months."**
  - *Observation that would separate it from beta:* the lag-2 coefficient survives dropping 2020.
  - **It does not** (ρ 0.37 → 0.05). The hit is the COVID crash-and-rebound sequence counted twice.
    The partial t of 3.85 comes from the same months.
  - What would revive it: a positive lag-2 ρ in the forward months from 2026-10 on, net of each
    series' own lags.
- **H2: "momentum leads `mom_gp`."**
  - It cannot be momentum's own persistence: `mom_12_1`'s lag-2 autocorrelation is −0.01.
  - It dies the same way without 2020 (ρ −0.08).
- **SMH − SPY led nothing** at |ρ| ≥ 0.3, at +1 or +2 months, in either direction.
- **(c) News flow: SKIPPED.**
  - `news_corpus/alpaca_benzinga_news` stamps `first_seen_utc` at PULL time: all 36,720 rows fall in
    2026-09.
  - Its `published_utc` covers only 2015-01 to 2015-02.
  - So no monthly news-flow count exists for 2017-2026. It needs a corpus whose native publish stamps
    span the window: GDELT, or the Benzinga backfill extended past Feb 2015.

## 4. What this changes

### Frozen forward books that are the same bet

Grouping is by full-window cluster; the ρ values are pairwise monthly-active correlations.

- **One bet:** `lib_mom_12_1_2026-09-26`, `lib_mom_12_1_q_2026-09-26`,
  `lib_mom_no_downgrades_2026-09-26` and `lib_mom_12_1_secrel_sealed_2026-09-26`. Pairwise ρ is
  0.83-0.97 over the full window and 0.80-0.98 inside each window.
- **One bet:** `lib_mom_flow_2026-09-26` and `lib_skill_mom_sealed_2026-09-26`. ρ is 0.92 full, 0.95
  dev and 0.88 in 2024-26. In the backtest, `skill_mom` is `mom_flow` under another name, which
  matters for the analyst-skill branch.
- **One cluster in 2024-26 only:** `lib_mom_12_1_liqw_sealed_2026-09-26__ew`,
  `lib_skill_mom_sealed_2026-09-26` and `lib_resid_mom_12_1_large_sealed_2026-09-26`.
- **Net:** the 19 frozen books with a backtest row are **15 distinct bets** on the full window and
  **14** on 2024-26.

The books stay frozen, because frozen books are never mutated. What changes is how they are read:

- The forward bridge should grade each cluster as **one** observation.
- It should report every momentum book against **SMH and MTUM before SPY**, as the reviewer proposed.
  That is buildable now from `etf_monthly.parquet`.
- `bridge_2026-09-26.json`'s `semis_umd_regression` recorded `SMH_NOT_IN_PANEL`. This decomposition
  supplies that missing input.

### Duplicates to retire from the current search: 61 rules, `DEPRIORITIZED` (never `STOP`)

A rule is retired as a duplicate when both of these hold:

- it sits in the same full-window cluster as its representative;
- its ρ with that representative is ≥ 0.8 in dev **and**, separately, in 2024-26.

The representative is the member with the highest dev DSR. The full list with ρ values is in the
tables file and in the receipt under `deprioritized_duplicates`. The largest groups:

- **14 duplicates of `mom_no_downgrades`:** `mom_12_1`, `mom_12_1_q`, `mom_12_1_secrel`,
  `mom_12_1_ivw`, `mom_12m`, `mom_no_rating_downgrade`, `mom_resid_to_sector`, `resid_mom_12_1`,
  `disp_short_avoid`, `eap_avoid_mom`, `mom_in_raised`, `mom_in_top_sectors`, `mom_no_exec_change`,
  `qc470_mom252_quarterly_riskparity`.
- **8 duplicates of `net_raises`:** `flow_rule`, `flow_rule_large`, `flow_in_winners`,
  `net_raises_large`, `net_raises_ivw`, `ibes_skill_net_raises`, `skill_raises`,
  `skill_raises_large`.
- **3 duplicates of `qc395_sharpe252_above_trend_large`:** `mom_12_1_large`,
  `mom_no_downgrades_large`, `resid_mom_12_1_large`.
- **3 duplicates of `lowvol_63_q`:** `low_idio_63`, `lowvol_21`, `lowvol_63`.
- **2 duplicates of `mom_flow_ivw`:** `mom_flow`, `skill_mom`.

What follows for new work:

- A new rule that lands in one of these clusters is a copy of an existing bet, not a new trial. The
  factory should print a rule's cluster before its rank.
- `mom_12_1` stays in use as the literature anchor for controls, even though it ranks as a duplicate
  here. Retirement takes it out of the search, not out of use as a reference.

### BRIDGE.md

`docs/BRIDGE.md` was **not** appended. `scripts/bridge_report.py` renders it, so the next render would
wipe a hand-written section. The tables live here and in the receipt.

## Not done, and why

- **(c) news-flow lead-lag:** no point-in-time monthly news count exists for 2017-2026 (see §3).
- **No holdings re-run through `replicate_vectorbt`:** the checkpoint already carried the series, and
  the by-year check agrees to 1.4e-5. The factory was also not run, because the fundamentals
  extraction is still running.
- **HAC / Newey-West standard errors for hold > 1 books:** not done. Their t is optimistic, and the
  "no survivors" conclusion does not depend on them.
