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

---

## Corrected 2026-09-27

Review: `docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md` (items 2-5 and 8-10
accepted). Every number below comes from the stored monthly series, not a factory rerun:

- `backend/data/optimus/signal_structure/signal_structure_2026-09-26T150811Z.json` (this document's
  run, re-derived; `stored_series_check` shows the parquet kept at a gap of 0.0);
- the hold-keyed sidecars `backend/data/optimus/signal_structure/leaderboard_<run>.rekeyed.json`
  for `T150811Z`, `T164302Z` (the receipt of record) and `T182110Z`.

### The overclaim, plainly

§2 said *"the 2024-26 momentum win is SMH/MTUM beta; the pre-2024 momentum alpha did not carry into
it"*, and it labelled 17 of the top 30 **MOSTLY SMH/MTUM BETA**. That read **no power** as **no
alpha**.

- With 32 monthly blocks and 7 parameters, the median SE of a 2024-26 alpha is **0.88%/month**. The
  median MDE at 80% power (2.8 × SE) is **2.46%/month**, about 29%/yr. A rule would need that much
  alpha to show t ≥ 2 four times in five.
- `mom_12_1_q`'s 2024-26 alpha point estimate is **+2.11%/month, the same as dev**. Only the SE
  changed. Its 2024-26 MDE is 5.2%/month.
- The "SMH+MTUM share" was a ratio of in-sample contributions on regressors correlated at 0.69. It
  printed +97% and −21%, and it could not tell beta from no power.

**The label and the share column are deleted** from `scripts/signal_structure.py`. Every alpha
now carries its SE and MDE beside t.

The replacement is **the alpha left after an ex-ante hedge**: the 2024-26 active return minus the
**dev (pre-2024) betas** × the 2024-26 spreads. It has an SE, and it gets a verdict:

| verdict | rule |
|---|---|
| `ALPHA_DETECTED` | abs(t) ≥ 2 (sign printed) |
| `BETA_EXPLAINS` | abs(t) < 1 **and** MDE < the observed mean excess |
| `CANNOT_DISTINGUISH` | everything else |

### The sentence that replaces §2's conclusion

> In 2024-26 the momentum cluster's return (17 members, mean +0.85%/month vs SPY) is fully
> accounted for by the ETF spreads: in-window alpha −0.04%/month, t −0.02. After the ex-ante hedge,
> its point estimate is **−1.83%/month** (t −1.02, SE 1.79%, MDE 5.0%/month). Thirty-two blocks
> cannot distinguish "the pre-2024 alpha died" from "it is intact at 2%/month". Verdict:
> **CANNOT_DISTINGUISH**. It is not "is beta".

### The numbers, over all 282 primary cells

§2 decomposed only the 52 cells of the two top-30s. Over all 282:

| | this document said | corrected |
|---|---|---|
| alpha t ≥ 2 in dev | 15 | **25** |
| alpha t ≥ 2 in 2024-26 | 1 | **3** |
| alpha t ≥ 2 on the full 115 months | — | **19** |
| alpha t ≥ 2 in both windows | NONE | **1** (see below) |

- **The one both-window survivor is `quality_composite_large`:** t 2.19 in dev and 2.07 in 2024-26.
  After the ex-ante hedge it is +0.08%/month (t 0.20), and it lost to SPY in 2024-26 by 4.1 pp/yr.
  It was never in the top-30s, so the old search could not see it.
- **Verdicts, all primary:** `ALPHA_DETECTED` 14, of which **12 are negative**. The two positive
  ones are `small_dv` (+1.67%/month, t 2.49) and `insider_cluster_small` (+1.39%/month, t 2.12).
  `CANNOT_DISTINGUISH` 268; `BETA_EXPLAINS` **0**.
- **Verdicts, 2024-26 top-30: CANNOT_DISTINGUISH 30 of 30.** The same holds for the dev top-30.
  Round 2 (`T182110Z`) is also 30 of 30.
- **Beta stability.** The correlation across cells of each rule's dev beta with its 2024-26 beta is:

  | spread | dev vs 2024-26 correlation |
  |---|---|
  | IWM | 0.62 |
  | SMH | 0.40 |
  | MTUM | 0.31 |
  | USMV | 0.33 |
  | QUAL | 0.16 |
  | VLUE | −0.20 |

  The momentum loadings are a regime, not a style: momentum bought semis because semis were
  trending.

### IWM β ≈ 1 is the panel's tilt, not the rules'

§2 said *"the loading nobody named is IWM (median +1.03)"*. That median was the 2024-26 top-30.

The random controls load **0.65-0.92** on IWM − SPY (1-factor, full window). The survivorship-free
panel is small-cap before any rule acts, so "vs SPY" charges every rule the panel's own tilt.

**The benchmark statement:** the survivorship-free panel itself tilts small (random controls' IWM β
0.65-0.92), so "vs SPY" understates every rule by the panel's own tilt.

Every receipt row now carries `vs_iwm` and `vs_random_panel` beside `vs_spy`. The random panel is
the mean net series of `random_1/2/3` at k = 50.

Rules beating the benchmark in **both** windows:

| run | vs SPY | vs IWM | vs random panel |
|---|---|---|---|
| `T150811Z` (282 rules) | 65 | 112 | 135 |
| `T164302Z`, of record (284) | 68 | 117 | 137 |
| `T182110Z`, round 2 (288) | 69 | 119 | 140 |

The reviewer's 66 for `T150811Z` is 65 on the board's own `dev_selected_sealed_evaluated`, and 65
here.

### "282 rules ≈ 180 bets" becomes a curve

Clusters over the 282 primary cells, full window, from `bet_count_curve`:

| series clustered | ρ 0.5 | ρ 0.6 | ρ 0.7 | ρ 0.8 | ρ 0.9 |
|---|---|---|---|---|---|
| raw net | 8 | 15 | 31 | 83 | 197 |
| active (the old count) | 35 | 79 | 131 | **187** | 238 |
| residual after SMH/IWM/MTUM | 93 | 135 | 171 | 212 | 249 |
| residual after all 6 ETFs | 99 | 147 | 183 | **216** | 250 |

- **Residual clustering RAISES the count.** The shared factor had merged bets.
- **For ALPHA multiplicity, the denominator is the residual count, ~216.** At n = 216:

  | cell | DSR at n = 216 | DSR at n = 849 cells |
  |---|---|---|
  | `mom_12_1_q@k20` | 0.347 | 0.200 |
  | the board-best `eap_mom@k10` | 0.617 | 0.441 |

  Neither reaches 0.95.
- **For RISK** (what loses together), the active or raw counts are the right ones.

### A factory-wide defect: by-year was keyed on the decision date

`strategy_library.evaluate` keyed these on the **decision** date, one month early:

- `by_year`;
- `by_year_signs`;
- `positive_excess_years_2020_2025`;
- `leave_one_year_out_mean_active`;
- `loo_worst_*`.

The window split was already entry-keyed. Every statistic is now keyed on the month the money was
**held**.

For one release, `by_year_decision` and its companions ride along, marked `DEPRECATED`, and
`top5_months_hold` names the best months.

**The distance-to-default example** (`T182110Z` sidecar), compounded excess vs SPY:

| year | decision-keyed | hold-keyed |
|---|---|---|
| 2020 | +61.0% | **−3.2%** |
| 2021 | −7.3% | **+75.5%** |

Its best hold month is **2021-01**, the squeeze.

**What changes in the receipt of record** (`leaderboard_2026-09-26T164302Z.rekeyed.json`, 284 rules
+ 11 controls):

- **29 rules change their LOO-worst > 0 verdict.**
  - 28 fail under the decision key and pass under the hold key: `agreements_mom`, `cash_rich`,
    `deleveraging`, `eap_avoid_mom`, `ear_flow`, `ear_mom`, `gp_at_large`, `gp_at_q`, `gp_at_small`,
    `insider_buy_dip`, `mom_12_1_mid`, `mom_12_1_trend`, `mom_6_1_q`, `mom_6m`, `mom_flow_secrel`,
    `mom_gp_large`, `mom_no_downgrades_trend`, `mom_no_insider_selling`, `overnight_mom`,
    `px_vs_ma200`, `qc629_multimom_above_trend_gated`, `resid_mom_63`, `rev_1m`, `rev_1m_small`,
    `rev_5d_large`, `rev_in_winners`, `roe`, `trend_ma50_200`.
  - 1 passes under the decision key and fails under the hold key: `lowvol_252_mega`.
  - None is in the 2024-26 top-10.
- **78 rules change their LOO-worst dropped year** (the "drop 2025" family), and 145 change their
  2020-2025 positive-year count.
- **0 top-5 verdicts change, by construction.** The share is a sum over the five best months, so
  the key cannot move it. Which months it names is now printed.

### Construction inside a cluster (the bridge's Level 2)

The cluster mean hid the within-cluster spread:

- **Momentum cluster 122:** members span **−18.6% to +37.9%** vs SPY in 2024-26, and member rank
  persistence from dev to 2024-26 is **0.06**.
- **Clusters 107 and 105:** rank persistence is **0.86** and **0.82**. They hold universe and k
  variants of one signal (the `_large` pairs).
- **Pair by pair:** the dev ordering held in 2024-26 for:
  - **83% of 12 universe-only pairs**;
  - **67% of all 30 construction-only pairs**;
  - **55% of 257 signal/filter pairs**.

  A coin is 50%.

`docs/BRIDGE.md` now carries both levels: the cluster mean vs its twins, and each member minus the
cluster mean, tagged by axis.

### Not done (owed)

- **The factory's row builder does not copy the new fields to leaderboard rows.**
  `night_backtest_factory._row` copies `by_year` (now hold-keyed), `loo_worst_*` and the top-5
  share. It does not copy:
  - `by_year_decision`;
  - `top5_months_hold`;
  - `vs_iwm` / `vs_random_panel`.

  The panel-relative columns need the random controls' series, so they are computed after the
  factory. A one-line hook is owed in `night_backtest_factory.py`: call `SL.panel_benchmarks` per
  cell once the controls are done, then copy the columns in `_row`. Until then the sidecar carries
  them.
- **HAC / Newey-West SEs for hold > 1 books:** still not done. Their MDE is optimistic.

## 2026-09-27 (later): hold-period keying in xs_ranker, HAC for multi-month holds, matched twins

Every number below is HINDSIGHT. Run of record: `T164302Z`. Its series come from
`checkpoint_2026-09-27.T173143Z.bak.json`, now also stored as
`monthly_returns_2026-09-26T164302Z.parquet`. That file is gitignored and is rebuilt by `--hac`. No factory
run and no LLM spend.

### 1. `xs_ranker.top_k_backtest` is hold-keyed

The per-year fields now use the year of the forward return's END session: decision date +
`horizon` business days on the US federal holiday calendar. This covers `by_year`,
`leave_one_year_out`, `loo_worst_*` and `share_of_total_by_year`. `share_of_total_top1pct_hold_ends`
names the dates by their hold end.

The decision-keyed values are kept for one release as `*_decision`, marked DEPRECATED. The
`share_of_total_by_date` fractions do not depend on the key and are unchanged.
`night_horizon_sweep` reads the same field names, so it now reads hold-keyed values. Test: a
21-session hold entered on 2023-12-29 lands in 2024 (`test_xs_ranker_hold_keying.py`).

### 2. HAC standard errors for rules held longer than one month

`signal_structure.ols` and `exante_hedge` now print both the plain SE and a Newey-West SE (Bartlett,
lag = hold_months − 1). For hold > 1, the verdict reads the HAC t, **floored at the plain SE**:
the HAC correction may widen the SE but never narrows it. `python -m scripts.signal_structure --hac`
writes `hac_readout_2026-09-26T164302Z.json`.

The floor is not optional here:

- 284 primary cells: 269 hold 1 month, 11 hold 3 months, 4 hold 12 months.
- For 8 of the 15 multi-month rules, the raw Newey-West SE came out *below* the plain SE.
- Unfloored, one verdict flipped. `rd_intensity` (12-month hold) went from CANNOT_DISTINGUISH to
  ALPHA_DETECTED: hedged t +1.57 → +2.85. That estimate is lag 11 on 32 months, which is noise.
- **Floored, no verdict changes:** 14 ALPHA_DETECTED and 270 CANNOT_DISTINGUISH, the same under
  both SEs.

### 3. Characteristic-matched random twins, 2024-26 top-10

Command: `python -m scripts.signal_structure --matched-twins`; receipt:
`matched_twins_2026-09-26T164302Z.json`; module: `backend/services/matched_twins.py`.

How the twin is built:

- For every held name, draw one name from the same size band × vol_63 tercile × 12-1 tercile at
  the same rebalance.
- Draw from the same survivorship-free panel. The rule's own names are excluded.
- Seed from the rule id. 20 extra draws give the twin's sampling SD.
- Twin net = twin gross − the rule's own cost that month.
- Reconstruction check: the rule's own gross, rebuilt from its holdings on this panel, matches the
  stored series within 1e-7 for all 10 rules.

All figures are CAGR differences. "Removed" = (rule − random_1) − (rule − twin).

| rule | dev: rule−twin | dev: rule−random_1 | 24-26: rule−twin (draw SD) | 24-26: rule−random_1 | share removed 24-26 |
|---|---|---|---|---|---|
| mom_12_1_liqw | −4.9% | −4.4% | +71.2% (23.5%) | +79.0% | 10% |
| qc372_oversold_snapback_mega | +1.9% | +0.8% | +71.1% (14.9%) | +70.0% | −2% |
| rd_intensity | +5.0% | +5.7% | +40.2% (11.9%) | +66.1% | 39% |
| rev_5d | −2.9% | −8.6% | +34.6% (13.8%) | +59.0% | 41% |
| qc623_mom63_liquidity_weighted | +2.5% | +0.8% | +44.1% (20.6%) | +56.9% | 22% |
| mom_12_1_q | +16.4% | +22.8% | +24.9% (14.1%) | +48.4% | 49% |
| margin_mom | +2.6% | +2.1% | +41.1% (9.5%) | +48.4% | 15% |
| skill_mom | +4.8% | +6.5% | +26.3% (9.4%) | +47.5% | 45% |
| qc395_sharpe252_above_trend_large | +21.2% | +15.4% | +13.4% (10.8%) | +45.8% | 71% |
| co03_reversal_in_high_margin | +6.0% | +1.1% | +26.5% (10.3%) | +45.5% | 42% |

What the table says:

- **In 2024-26, matching removes a median 20.1 pp of the 52.6 pp excess over random_1** (median
  share about 40%). The largest shares are the large-cap trend rule (71%) and quarterly momentum
  (49%).
- **All 10 rules still beat their matched twin in 2024-26.** Two cautions apply:
  - these 10 were *selected* on 2024-26;
  - the twin draw SD is 9–24%/yr.
- **In dev, matching removes nothing** (median −0.8 pp), and 8 of 10 rules beat their twins by a
  median of only +3.7%.
- **Conclusion:** the 2024-26 excess is part style (size, vol, past return) and part window
  selection. Neither is established as a mechanism.

### Still owed

- The factory's own `night_backtest_factory` does not apply the HAC floor. Its t is
  `t_active_horizon_blocks` on horizon-wide blocks, which is a different estimator.
- Matched twins cover only the 10 rules the replication file carries holdings for. Rolling them
  out to every board row needs the factory to store holdings for every cell. (Done 2026-09-27
  evening, next section.)

## 2026-09-27 (evening): pooled family tests and matched twins for every cell

Every number below is HINDSIGHT. Every rule was registered 2026-09-26, after every month scored.
Licence `PRODUCT_EXPERIMENT`, $0, no LLM. This is reviewer ideas 2 and 3
(`docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md` §8), which the adjudication
deferred to the next factory night.

**RESULT IMPROVEMENT: NONE.** This adds a stronger test and a denominator. It does not add an edge.

- **Run of record:** `2026-09-27T082553Z`, from `python -m scripts.night_backtest_factory --no-freeze`.
  It ran 306 rules and 904 OK cells in 251 s. Panel fingerprint `3a8c19576fafb9a4`, as in `T080946Z`.
  The earlier run's checkpoint is kept as `checkpoint_2026-09-27.T080946Z.bak.json`.
- **Readouts:** `python -m scripts.signal_structure --run-id 2026-09-27T082553Z --rekey --hac --matched-twins`,
  then `--family-pool`.
- **Receipts:** `signal_structure/family_pool_2026-09-27T082553Z.{json,md}`,
  `matched_twins_2026-09-27T082553Z.json`, `hac_readout_…`, `leaderboard_….rekeyed.json`, and
  `strategy_library/holdings_2026-09-27T082553Z.manifest.json`.
- **Code:** `backend/services/family_pool.py`, `matched_twins.py` (`cell_records`, `check_months`,
  `CellIndex`), and `night_backtest_factory.write_holdings`.

### 1. Holdings for every cell

The factory now writes the held symbols and weights at every rebalance for all 904 cells: 2,499,348
rows, 4.6 MB. It also writes each cell's monthly gross, cost and net (103,184 rows) and its own
twin panel (372,754 rows). All three are parquet, so they are gitignored. The manifest, which is
committed, carries each file's sha256, and the readers refuse any file that does not match it.

- **Check: 904 of 904** OK cells have holdings and exactly `n_months` monthly rows.
- **Crash safety:** a part is flushed before every checkpoint, so `--resume` keeps the holdings.
- **Twin reconstruction:** the matched-twin module rebuilds each rule's gross from those holdings
  to within 1.7e-8. Net agrees with the series of record to within 1.1e-6.
- **Refusal:** a cell whose monthly series has a hole inside its span refuses by name. No cell
  refused on this run.

### 2. Matched twins for all 288 primary cells

The twin is drawn from the same size band × vol_63 tercile × 12-1 tercile at every rebalance.
Draw 0 is seeded from the cell id, and 20 more draws give the twin's spread. 99% of twin names came
from the full cell (596,207 cell draws; 3,507 fell back to "any").

| window | median rule − twin | median rule − random_1 | removed by matching (share) | beats twin | t(rule − twin21) ≥ 2 / ≤ −2 |
|---|---|---|---|---|---|
| dev | +3.0% | +2.1% | −1.4 pp (17%) | 193 / 288 | 36 / 23 |
| 2024-26 | **−0.2%** | +7.1% | **+8.2 pp (51%)** | 140 / 288 | 9 / 8 |

The top-10 table above said all ten rules beat their twin in 2024-26. Over the whole library that
was selection. The median primary rule's 2024-26 excess over random_1 (+7.1%) is **entirely
style** (size, volatility and past return), and the median rule loses to its matched twin by 0.2%.
In 2024-26, 9 cells beat their twin at t ≥ 2 and 8 lose at t ≤ −2, which is what 288 draws of
noise produce.

Two cells clear t ≥ 2 against the 21-draw twin in both windows:

- `mom_12_1_q_trend@k20`: dev +1.77%/mo (t 2.34), 2024-26 +2.63%/mo (t 2.14);
- `disp_short_avoid@k20`: +1.67%/mo (t 2.07), then +2.17%/mo (t 2.02).

Chance alone predicts about 0.8 such cells: 36 dev hits × P(t ≥ 2 | null) ≈ 0.023 in 2024-26. These two are
leads for the forward book, not findings.

### 3. Pooled family tests (25 families with ≥ 3 primary rules)

Each family is scored as one series: the equal-weight mean of its members' monthly active returns.

- **SE:** plain SE, and Newey-West at lag max(hold) − 1. The used SE is the larger of the two.
- **MDE:** 2.8 × SE.
- **n_eff** = n / (1 + (n − 1) ρ̄), printed for each window.
- **Verdict:** the single-rule rules, applied to the 2024-26 pooled series hedged with its dev ETF
  betas.
- **Rule − twin:** reads the mean of the 21 twin draws.

Ten families have fewer than 3 rules and were not pooled. The full table (25 rows) is in
`signal_structure/family_pool_2026-09-27T082553Z.md`. The rows that matter:

| family | n | n_eff 24-26 (ρ̄) | vs panel dev: mean (t) | vs panel 24-26: mean (t) | MDE 24-26 | ETF α vs SPY dev (t) | 24-26 (t) | verdict | rule − twin dev (t) | rule − twin 24-26 (t) |
|---|---|---|---|---|---|---|---|---|---|---|
| quality | 12 | 8.9 (0.03) | +0.69% (3.03) | +0.23% (0.81) | 0.79% | +0.55% (2.36) | +0.17% (0.54) | CANNOT_DISTINGUISH | +0.47% (2.72) | −0.33% (−0.99) |
| analyst_dispersion | 4 | 2.9 (0.13) | +0.82% (3.20) | +0.45% (0.85) | 1.48% | +0.75% (2.78) | +0.12% (0.24) | CANNOT_DISTINGUISH | +0.50% (2.36) | +0.36% (0.90) |
| revision_flow | 15 | 2.2 (0.41) | +0.98% (2.82) | +0.69% (0.88) | 2.22% | +0.53% (1.90) | −0.38% (−0.61) | CANNOT_DISTINGUISH | +0.56% (2.50) | +0.14% (0.41) |
| insider | 16 | 5.7 (0.12) | +0.75% (2.51) | +0.44% (1.15) | 1.08% | +0.75% (2.39) | +0.24% (0.56) | CANNOT_DISTINGUISH | +0.50% (2.24) | +0.04% (0.13) |
| value | 3 | 3.0 (−0.01) | +0.95% (2.35) | +0.67% (1.28) | 1.46% | +1.07% (3.28) | +0.64% (0.99) | CANNOT_DISTINGUISH | +0.54% (1.60) | +0.24% (0.50) |
| weighted | 7 | 3.7 (0.15) | +1.13% (2.59) | +2.02% (1.99) | 2.85% | +0.74% (1.86) | +0.72% (0.83) | CANNOT_DISTINGUISH | +0.69% (2.01) | **+1.31% (2.25)** |
| momentum | 26 | 2.1 (0.45) | +1.06% (1.77) | +1.22% (0.97) | 3.51% | +0.72% (1.32) | −0.23% (−0.20) | CANNOT_DISTINGUISH | +0.55% (1.39) | +0.40% (0.54) |
| combination | 37 | 5.5 (0.16) | +0.50% (1.63) | +0.70% (1.74) | 1.12% | +0.35% (1.42) | +0.51% (1.37) | CANNOT_DISTINGUISH | +0.16% (1.13) | +0.26% (1.11) |
| diversified_combo | 11 | 4.9 (0.12) | +0.72% (2.80) | −0.00% (−0.00) | 1.15% | +0.57% (2.52) | −0.23% (−0.59) | ALPHA_DETECTED, **negative** (hedged −0.98%/mo, t −2.06) | +0.39% (2.90) | −0.50% (−1.81) |
| low_risk | 17 | 2.3 (0.40) | −1.31% (−2.80) | −0.22% (−0.45) | 1.34% | −1.40% (−5.27) | −0.11% (−0.39) | CANNOT_DISTINGUISH | −1.45% (−3.93) | −0.22% (−0.87) |

**Power.** Pooling bought less than the hoped-for halving of the MDE, because family members are
correlated:

- Median n_eff is about 2-4, not n.
- MDE of the mean vs the panel: single rule 1.51%/mo (dev) and 2.74%/mo (2024-26); pooled family
  median 1.03% and 2.15%. That is about 0.7-0.8× a single rule.
- The ETF-alpha SE in 2024-26 is 0.89% single versus 0.65% pooled. The MDE falls from 2.48% to
  1.82%/mo, which is still 22%/yr.
- The 2024-26 window cannot resolve a family alpha under ~1%/mo even at best: `quality`, with
  n_eff 8.9, has an MDE of 0.79%.

**The answers:**

- **Alpha in BOTH windows against the panel benchmark: none of the 25 families.** Pooled mean
  t ≥ 2 in dev and 2024-26: none vs the random panel, none vs SPY. ETF-alpha t ≥ 2 in both: none.
- **Families dev-strong vs the panel:** `quality`, `analyst_dispersion`, `revision_flow`,
  `diversified_combo`, `weighted`, `insider`, `value`, `sector_relative`. All of them are t < 2 in
  2024-26. `weighted` is the closest, at 1.99.
- **Verdicts vs SPY:** 24 CANNOT_DISTINGUISH and 1 ALPHA_DETECTED, which is **negative**
  (`diversified_combo`). Against the panel, all 25 are CANNOT_DISTINGUISH.
- **Rule − matched twin, pooled t ≥ 2 in both windows: one family, `weighted`.** It scores +0.69%/mo
  (t 2.01) in dev and +1.31%/mo (t 2.25) in 2024-26, with n_eff 5.4 on the twin series and DSR
  0.83 at n = 25 families.
  - Its members are the inverse-vol, liquidity-weighted and risk-parity versions of momentum,
    quality, gross profitability and net-raises.
  - What survives the twin is plausibly the WEIGHTING itself (a volatility tilt inside each cell),
    not any one signal's selection.
  - One family of 25 clearing t ≥ 2 twice is within what this much looking allows. It is a lead, and
    it is not a claim.
- **Multiplicity over families.** Best DSR at n = 25 families:
  - vs the panel: `quality` 0.891;
  - vs SPY: `weighted` 0.529;
  - rule − twin: `regime_gated` 0.872.
  - None reaches 0.95.
- **Consistent reads.** `low_risk` is significantly NEGATIVE in dev on every benchmark. The rekeyed
  board gives 69 / 119 / 139 of 288 primary rules beating SPY / IWM / the panel in both windows,
  consistent with the review's 66 / 112 / 135.

### What changes in the README's honest sentence (Fable re-renders)

> Pooled into 25 families and tested against the panel's own random portfolio, no family of rules
> shows a statistically detectable alpha in both the pre-2024 and the 2024-26 windows. Against
> characteristic-matched random twins, the median rule's 2024-26 excess is zero, because what it
> beat SPY by was its size, volatility and momentum style. Pooling lowers the detectable effect
> only to about 1-2%/month, because a family's rules are largely the same bet. One family
> (volatility- and liquidity-weighted books) beats its twins at t ≈ 2 in both windows, which is a
> lead for forward paper, not a claim.

### Still owed

- The **fundamentals-family minus price/volume-family** hedged contrast from idea 3 was not run.
  This readout groups by the library's `family` label, not by input source.
- A month-block bootstrap of the family mean was not done. The SE is plain or Newey-West as for
  single rules.
- `weighted`, `mom_12_1_q_trend@k20` and `disp_short_avoid@k20` should be graded forward against
  their matched twins. That is the only test that is not hindsight.
