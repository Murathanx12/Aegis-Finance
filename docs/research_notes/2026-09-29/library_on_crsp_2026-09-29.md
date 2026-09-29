# The strategy library on CRSP, 1991-2024: what survives the survivor-free panel (2026-09-29)

Licence `PRODUCT_EXPERIMENT`. $0.00, no LLM, no network, no broker call. No frozen book, ledger row,
bar file, leaderboard or past receipt was changed; one new shadow book and its twin were APPENDED to
`llm_portfolio/books.jsonl`. Every number below is in a receipt under
`backend/data/optimus/crsp_rebuild/` (run id `LIB_2026-09-29T0802Z`, board `2026-09-29T081355Z`).

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: A FORWARD CANDIDATE, NOT A CLAIM.** Of 133 library rules runnable on CRSP (plus 7
controls), 12 beat their matched twin at t >= 2 over 1991-2024 and **49 are positive in all three
windows** (1991-2024, the 1991-2016 holdout the library never saw, and 2017-2024). **No single rule
clears the deflated Sharpe bar** (best DSR 0.31 at n = 1,296 cells ever looked at). A post-hoc blend of
the best rule from four nearly uncorrelated clusters reads **+0.64%/mo over its twin, t 5.3, DSR 0.962
at n = 1,298**. That blend was chosen after looking, so it is frozen forward as `CRSP_BLEND_v0`, not
claimed.

| item | value |
|---|---|
| best historical net strategy vs the market | `qc629_multimom_above_trend_gated` (k10): CRSP net CAGR **19.3%** vs the market's 10.6% (1994-2024). Among k20 rules, `px_vs_ma200_large` **17.8% vs 10.5%**. Both are HINDSIGHT. |
| rules run on CRSP / in the library | **140 of 312** (133 tested + 7 controls). 172 not run: their inputs do not exist in the CRSP era on disk (named below). |
| rules surviving on CRSP | **49 of 133** positive vs twin in all three windows. **33** also pass the candidate filter (majority of years, trimmed mean > 0, LOO-worst > 0). **12** at nominal t >= 2 (about 3 expected by chance from 133 at one-sided 2.3%; they are correlated). **0** at DSR >= 0.95. |
| what the vendor panel inflated | mean rule - twin across the 133 rules: vendor **+0.19%/mo** vs CRSP **+0.07%/mo** on the same 2017-2024 window. 92 rules were positive on the vendor panel; **26** of them are negative on CRSP 1991-2024 and **33** negative on the holdout. Rank agreement vendor vs CRSP: Spearman 0.44 (full), 0.53 (same 2017-2024 window), 0.28 (vs the holdout). |
| the old vendor top 10 on CRSP | `mom_12_1_q` +1.87 -> **+0.10**; `rev_5d` +0.99 -> **-0.05**; `qc372_oversold_snapback_mega` +1.06 -> +0.15; `qc623` +1.12 -> **+1.00 (t 2.5)**; `co03` +1.05 -> **+0.70 (t 2.9)**. Three of the ten need inputs CRSP lacks (`rd_intensity`, `margin_mom`, `skill_mom`). |
| controls | `random_1/2/3`, `random_large`: -0.16 to +0.02%/mo, all |t| < 1.1. The twin is unbiased on CRSP. |
| independent selector count | among the 33 candidates: **7 bets at \|rho\| 0.3**, 18 at 0.5, 25 at 0.7 (single linkage on rule - twin series). |
| farm candidates tested / promoted | 133 rules + 286 two/three-rule blends read; **1 shadow book frozen** (`CRSP_BLEND_v0`, book `b0a33a92c56fddb1`, twin `b35d287bdcbf00bb`, entry at the 2026-09-29 US open). 0 promoted to capital. |
| best forward paper strategy | unchanged; nothing matures before 2026-10-26. |
| new actionable finding | **Large-cap trend/momentum survives the survivor-free panel; small/illiquid momentum does not.** `mom_12_1_large` +0.75%/mo (t 2.8; holdout +0.80, t 2.5) while `mom_12_1` (all) is +0.04 and `mom_12_1_small` +0.03. The vendor bias sat where the old board looked; the edge, if any, sits where it did not. |
| external execution drag | not measured |
| LLM spend | $0.00 |

## 1. What was run

`scripts/library_on_crsp.py`, four parts, each writing a receipt with a run id:

1. `--part panel`: the momentum_on_crsp CRSP bridge, **unchanged**, but keeping every column
   `build_panel` computes (46). Receipt `library_panel_2026-09-29T075640Z.json`. It has **2,033,164 rows**,
   the same count as the momentum panel, as it should.
2. `--part fundamentals`: WRDS Financial Ratios (`wrdsapps__firm_ratio`) merged point in time on
   `public_date <= decision date` by permno, 70-day tolerance. These are **PROXIES** for the library's
   SEC-facts columns: `gp_at` = gprof, `book_to_market` = bm, `debt_at` = debt_at, `gross_margin` = gpm,
   `ni_be` = roe. It also carries a point-in-time GICS `gsector`, which the vendor panel does not have
   (the vendor uses today's sector for every past month). Coverage of eligible rows: 75% in 1991, over
   90% from 2001. 38 of the 133 rules read a proxy and are marked `[proxy]`.
3. `--part run`: every library rule whose `requires` exist, through `calendar_offset_triplet.run_one`,
   the library's own path. That means costs on, the rule's own k, and the 21-draw matched twin (size
   band x vol_63 x 12-1 tercile, two seed sets). The 11 rules with a 3-month hold also run the three
   quarterly offsets, and they are read calendar-neutral. Stats are keyed on the **hold** month: 3-month
   block t with the MDE beside it, by year, LOO-worst, share of total by date, the top-5% share and the
   5% trimmed mean. The run also computes a Fama-French 3 + UMD read of the net book. The jsonl is
   appended rule by rule, so a cut-off loses nothing. It took 737 s.
4. `--part board`: the vendor side-by-side and the DSR. The vendor numbers are the same cell's rule -
   twin21 from `signal_structure/matched_twins_monthly_2026-09-27T082553Z.parquet`. That is one
   calendar, 2017-2026. The DSR is computed at n = 877 vendor cells + 133 CRSP cells + 286 blends
   = 1,296, with a CRSP-only DSR beside it. The board also writes the candidate filter, blends, the
   correlation matrix and the verdicts.

Consistency check: `mom_12_1_q` reproduces the momentum note exactly (+0.10%/mo, t 0.33, MDE 0.83).

### Verdicts (the rule was written in code before the run)

The headline rule is FAILED_VARIANT when rule - twin <= 0; CALENDAR_ARTEFACT from the v2 calendar
rule; ALPHA_DETECTED at twin t >= 2 when the holdout is positive and the FF3+UMD net read is not
BETA_EXPLAINS; BETA_EXPLAINS when the twin t >= 2 but the net book is BETA_EXPLAINS; otherwise
CANNOT_DISTINGUISH. The counts:

| headline | rules |
|---|---:|
| FAILED_VARIANT | 51 |
| CANNOT_DISTINGUISH | 70 |
| ALPHA_DETECTED (nominal t, **not** deflated) | 12 |
| BETA_EXPLAINS | 0 |
| CALENDAR_ARTEFACT / ROBUST_TO_CALENDAR | 0 / 0 (all 11 quarterly rules read CANNOT_DISTINGUISH) |

"ALPHA_DETECTED" here means a nominal t. With DSR at most 0.31, none is a claim.

## 2. The table: top and bottom

All figures are rule - matched twin21 in %/month, net of costs, as t on 3-month blocks with the MDE
beside it. "Vendor" is the 2026-09-27 matched-twin run (2017-2026).

| rule | k | vendor | CRSP 1991-2024 | holdout 1991-2016 | 2017-2024 | +yrs | trim5 | LOO-worst | DSR | headline |
|---|---|---|---|---|---|---|---|---|---|---|
| `qc629_multimom_above_trend_gated` | 10 | +2.36 (t 1.38, MDE 4.79) | **+1.27 (t 2.32, MDE 1.53)** | +0.91 (t 2.67) | +2.30 (t 1.12) | 22/31 | +0.63 | +0.77 | 0.02 | ALPHA_DETECTED |
| `qc623_mom63_liquidity_weighted` | 10 | +1.12 (t 1.24) | **+1.00 (t 2.51, MDE 1.11)** | +1.02 (t 2.28) | +0.94 (t 1.19) | 19/31 | +0.68 | +0.64 | 0.19 | ALPHA_DETECTED |
| `px_vs_ma200_large` | 20 | +1.93 (t 2.12) | **+0.93 (t 2.54, MDE 1.02)** | +0.58 (t 1.98) | +1.85 (t 1.96) | **25/30** | +0.69 | +0.71 | 0.17 | ALPHA_DETECTED |
| `mom_12_1_liqw` | 20 | +1.58 (t 1.28) | +0.86 (t 1.78, MDE 1.36) | +0.74 (t 1.53) | +1.27 (t 1.06) | 19/34 | +0.38 | +0.64 | 0.05 | CANNOT_DISTINGUISH |
| `mom_12_1_large` | 20 | +0.25 (t 0.47) | **+0.75 (t 2.77, MDE 0.76)** | +0.80 (t 2.50) | +0.62 (t 1.06) | 20/30 | +0.60 | +0.60 | 0.22 | ALPHA_DETECTED |
| `co03_reversal_in_high_margin` [proxy] | 20 | +1.05 (t 2.25) | **+0.70 (t 2.93, MDE 0.67)** | +0.91 (t 3.18) | +0.02 (t 0.04) | 24/34 | +0.47 | +0.55 | 0.31 | ALPHA_DETECTED |
| `mom_6_1_large` | 20 | +1.94 (t 1.82) | +0.70 (t 1.76, MDE 1.11) | +0.37 (t 1.33) | +1.58 (t 1.44) | 22/30 | +0.46 | +0.46 | 0.03 | CANNOT_DISTINGUISH |
| `resid_mom_12_1_large` | 20 | +0.50 (t 0.91) | +0.63 (t 1.93, MDE 0.91) | +0.62 (t 1.55) | +0.64 (t 1.08) | 18/30 | +0.47 | +0.46 | 0.09 | CANNOT_DISTINGUISH |
| `trend_quality_trend` [proxy] | 20 | +0.54 (t 1.89) | **+0.52 (t 2.66, MDE 0.54)** | +0.45 (t 2.10) | +0.72 (t 1.80) | 22/34 | +0.46 | +0.42 | 0.25 | ALPHA_DETECTED |
| `frog_in_pan` | 20 | +0.94 (t 2.34) | +0.46 (t 2.14, MDE 0.60) | +0.39 (t 1.60) | +0.67 (t 1.60) | 21/34 | +0.41 | +0.36 | 0.14 | ALPHA_DETECTED |
| `vol_compression` | 20 | **-2.02 (t -3.54, MDE 1.60)** | +0.38 (t 2.03, MDE 0.52) | +0.45 (t 2.22) | +0.15 (t 0.28) | 22/34 | +0.40 | +0.31 | 0.07 | ALPHA_DETECTED |
| ... | | | | | | | | | | |
| `recovery_anchoring` | 20 | -1.07 (t -2.98) | -0.44 (t -3.04, MDE 0.41) | -0.42 (t -2.74) | -0.50 | 6/34 | -0.38 | -0.51 | 0 | FAILED_VARIANT |
| `turnover_surge` | 20 | -0.58 | -0.45 (t -2.18) | -0.57 (t -2.61) | -0.08 | 8/34 | | | 0 | FAILED_VARIANT |
| `hi52_secrel` [proxy] | 20 | -1.00 (t -3.08) | -0.49 (t -2.33) | -0.68 (t -2.89) | -0.05 | 9/26 | | | 0 | FAILED_VARIANT |
| `shallow_dd` | 20 | -0.72 | **-0.62 (t -4.20, MDE 0.42)** | -0.65 (t -4.29) | -0.52 | 7/34 | | | 0 | FAILED_VARIANT |
| `illiquid` | 20 | +0.21 | **-0.69 (t -2.64)** | -0.58 | -1.08 | 9/34 | | | 0 | FAILED_VARIANT |
| `mom_in_laggard_sectors` [proxy] | 20 | -1.15 | -0.83 (t -2.44) | -0.77 | -0.96 | 9/26 | | | 0 | FAILED_VARIANT |
| `overnight_mom` | 20 | +0.59 | **-1.30 (t -3.68, MDE 0.99)** | -1.49 (t -4.43) | -0.68 | 10/34 | | | 0 | FAILED_VARIANT |

The full table has 140 rows, with the FF3+UMD read and the calendar verdict for every rule:
`crsp_rebuild/library_board_LIB_2026-09-29T0802Z__2026-09-29T081355Z.md`.

**Is it just UMD?** The candidates' rule - twin gaps were regressed on the four factors.

- **The large-cap momentum rules are partly UMD.** `mom_12_1_large` has a gap alpha of +0.44 (t 1.62)
  with a UMD beta of 0.42. `resid_mom_12_1_large` has +0.30 (t 1.00). Both read CANNOT_DISTINGUISH.
- **These keep a four-factor alpha on the gap:**
  - `px_vs_ma200_large`: +0.81 (t 2.30, MDE 0.99), UMD beta 0.37;
  - `qc623`: +0.84 (t 2.16);
  - `co03`: +0.78 (t 2.88), UMD beta -0.12;
  - `trend_quality_trend`: +0.54 (t 2.76);
  - `vol_compression`: +0.85 (t 4.88).

## 3. What DOES work (post-hoc; findings to test forward, never priors)

**The candidate filter.** The filter declared first needed "top 5% of months carry < 75% of the
total". **It could not go green.** A +0.5%/mo edge with a 3-4%/mo sd puts 70-110% of a 34-year total in
its best 5% of months by arithmetic alone. It passed 0 of 132 rules, including every rule with
t > 2. After the first 132 rules were read it was replaced by a symmetric test: the mean after dropping
the best **and** worst 5% of months must stay above 0. This change was made after looking, and it is
recorded in the board as `candidate_rule_amendment`. Both filters are on the receipt.

**The candidates: 33.** They cluster into about **7 independent bets at |rho| 0.3** on rule - twin:

1. Large-cap trend and momentum: `px_vs_ma200_large`, `qc629`, `qc623`, `mom_12_1_large`,
   `mom_6_1_large`, `qc395`. The rho between `px_vs_ma200_large` and `qc629` is 0.79.
2. Trend + quality: `trend_quality`, `trend_quality_trend` (rho 0.86 with each other).
3. Short-horizon reversal in quality or large names: `co03`, `rev_5d_large` (rho 0.43).
4. Volatility compression: `vol_compression`.
5. Profitable low-vol: `gp_lowvol_large`, `mom_gp_lowvol`.
6. Frog-in-the-pan: `frog_in_pan` and its variants.
7. Low-weight fundamentals: `roe`, `gp_at_large`, and the annual large-cap ROE rule.

**The blend.** The best-by-mean rule of four of these clusters were blended at 25% each:
`px_vs_ma200_large`, `trend_quality_trend`, `co03_reversal_in_high_margin` and `vol_compression`.
Their pairwise rho is between -0.14 and +0.18.

| blend rule - twin | mean %/mo | t (3-mo blocks) | MDE |
|---|---:|---:|---:|
| 1995-2024 (common span) | **+0.64** | **5.32** | 0.34 |
| holdout, 1995-2016 | +0.63 | 4.57 | 0.38 |
| library window, 2017-2024 | +0.68 | 2.89 | 0.66 |

It also shows:

- 26 of 30 hold years positive;
- a 5%-trimmed mean of +0.62;
- a LOO-worst of +0.57;
- **a DSR of 0.962 at n = 1,298** (every cell ever looked at, plus the two blends read).

**How much to trust it.** It is the only object on either board over the DSR bar, but the count
understates the search. Four rules were picked from 33 candidates, and the candidates themselves were
screened on the same 34 years. The 1995-2016 half was never seen by the library's *development*. Every
mechanism in it except `co03` was published before 2016, though, so the holdout is honest for these
implementations, not for the ideas.

Two of the four read proxy fundamentals (WRDS ratios), and the frozen book reads the vendor's SEC facts.
That is the same concept, not the same bytes.

## 4. The shadow book (frozen before the 2026-09-29 US open, 13:30 UTC)

`CRSP_BLEND_v0`: book **`b0a33a92c56fddb1`**, matched twin21 **`b35d287bdcbf00bb`**, registered
2026-09-29T08:22:59Z, entry at the open of 2026-09-29.

**How the book was built:**

- **Four sleeves at 25% each.** Each is its rule's `latest_selection` on the current vendor panel, built
  by `bridge_report.build_library_panel`. That uses the stitch cut, the bar-defect screen, SEC
  fundamentals and the market bars to 2026-09-28.
- **The screen:** 77 names, 0 of 77 slots on flagged bars.
- **The gate:** the `mkt_trend_up` gate is ON.
- **The twin:** each name gets 21 draws of the same band x vol tercile x 12-1 tercile. That makes
  920 twin names.

**Pre-declared reads and kill rule:**

- **Kill rule** (in the registration): if book minus twin is below -1.645 x its noise sd at 126
  sessions, the verdict is FAILED_VARIANT.
- **The expected read is CANNOT_DISTINGUISH.** A 0.64%/mo edge against a ~2.5%/mo tracking sd gives a
  6-month t of about 0.6. This book can kill the blend. It cannot confirm it in 2026.
- **Roadmap conflict.** This is a new book inside ROADMAP_2026-09-28's "no new book to 2026-10-26"
  window. It was frozen on this brief's instruction and can be voided before entry with
  `llm_portfolio.void`.

Files:

- `shadow_bayes/REGISTRATION_CRSP_BLEND_v0_2026-09-28_20260929T082258Z.json`
- `shadow_bayes/crsp_blend_v0_2026-09-28_20260929T082258Z.json` (the rule receipt; `..._081956Z` is
  the dry run that preceded it, identical selection, kept)

## 5. What could not be run, and why

172 rules were not run. The inputs they need are absent from the CRSP era on disk, or have no
point-in-time bridge built today. The most common missing inputs, with the number of rules each blocks:

- `net_raises` and the other analyst-revision flow columns (36, from the yfinance revision parquet,
  2016+ only);
- `ins_buyers_90` and the other insider columns (22, SEC Form 4 pulls);
- `ear_last` and the other earnings-event columns (12+);
- `gm_chg`, `inflection`, `rev_gr`, `rev_accel`, `ope_be`, `roa_chg`, `cash_at`, `ebit_ev`, `rd_intensity`
  and `org_capital` (SEC-facts derivations with no WRDS proxy mapped yet);
- `dtc`, `si_chg_3m` and `short_vol_ratio_21` (short interest and FINRA short volume);
- `skill_net_raises_90` and `analyst_skill_weight` (the analyst-skill book);
- `target_cv_180` (IBES, 1999+; `disp_short_avoid` was run there in the momentum note);
- `attention_z` and `news_tone_z` (news);
- `d2d_chg`;
- `inst_breadth_chg` (13F);
- `n701_90` and `n8k_90` (8-K filings).

IBES (`recdet`, `ptgdet`, `detu`), Compustat quarterly and TR 13F are on disk. They could proxy
several of these; that is the next build, not done here.

## 6. Files

| role | path |
|---|---|
| the runner (panel / fundamentals / run / board) | `scripts/library_on_crsp.py` |
| the blend book (dry run / `--freeze`) | `scripts/crsp_blend_book.py` |
| tests (offline, synthetic; 12 + 3) | `backend/tests/test_library_on_crsp.py`, `backend/tests/test_crsp_blend_book.py` |
| wide panel receipt (parquet local, gitignored) | `crsp_rebuild/library_panel_2026-09-29T075640Z.json` |
| PIT fundamentals receipt | `crsp_rebuild/library_fund_2026-09-29T041550Z.json` |
| per-rule results (append-only) | `crsp_rebuild/library_rules_LIB_2026-09-29T0802Z.jsonl` |
| per-rule monthly series | `crsp_rebuild/library_series_LIB_2026-09-29T0802Z/<rule>.parquet` |
| the new leaderboard (json + md) | `crsp_rebuild/library_board_LIB_2026-09-29T0802Z__2026-09-29T081355Z.{json,md}` |
| old vendor leaderboard (untouched) | `strategy_library/LEADERBOARD.md`, `leaderboard_2026-09-28T141504Z.json` |

`crsp_rebuild` already has a caller: `scripts/momentum_on_crsp.py`, and now `scripts/library_on_crsp.py`.
`signal_reachability` counts it as `tooling_only` through the scripts closure, so no classification
edit was needed.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS.**

- **Large-cap trend and momentum** ($100M+ a day median dollar volume). It is positive in both halves
  on a survivor-free panel. `px_vs_ma200_large` was positive in 25 of 30 years, with a four-factor gap
  alpha of +0.81 (t 2.3).
- **Short-horizon reversal inside high-margin names** (`co03`): +0.91 on the holdout (t 3.2). It is
  flat in 2017-2024.
- **Volatility compression**: +0.38 (t 2.0), with a four-factor gap alpha of t 4.9. The vendor panel
  had this rule at -2.02%/mo (t -3.5). CRSP turns it positive: the survivor bias runs in both directions.
- **Trend + quality**: +0.52 (t 2.7).
- **Diversifying across those four**: +0.64%/mo, t 5.3, DSR 0.96. This is the best call on the
  evidence, and it is frozen forward.
- **The bridge**: 140 rules in 12 minutes. Any new price rule can be read on 34 survivor-free years
  before it gets a book.

**WHAT DOES NOT.**

- **Momentum over the whole or the small-cap universe**: `mom_12_1` +0.04, `mom_12_1_small` +0.03,
  `mom_12_1_q` +0.10.
- **Illiquidity**: `illiquid` -0.69, t -2.6.
- **Overnight momentum**: -1.30, t -3.7.
- **Shallow drawdown, recovery anchoring, turnover surge**: all t below -2 on CRSP.
- **The old board's `rev_5d`** (+0.99 on the vendor panel, -0.05 on CRSP).
- **Any single-rule claim**: no rule reaches DSR 0.95.
- **The vendor panel as a ranking device**: vendor-to-holdout rank correlation is 0.28.

**HIGHEST-EV EXPERIMENT.** Build the IBES, Compustat and 13F point-in-time bridge for the 172 rules not
run, starting with analyst revisions (36 rules) from IBES `detu`/`recdet`, then re-run the board.

- **Cost:** about 2-3 hours, $0.
- **Why it ranks first:** the `analyst_skill` family is one of the two families the vendor board read as
  ALPHA_DETECTED vs twin, and the vendor panel's revision data starts in 2016. Only CRSP-era IBES can give it a holdout.
  P(changes the roadmap) is high either way.
- **Second, cheaper:** read `CRSP_BLEND_v0` against its twin at 21 sessions. It is a sanity check
  only; do not tune.

## CONTINUE FROM HERE

Everything is computed and in receipts. The two parquet panels are local (gitignored). Nothing is
committed (brief). Reproduce:

```bash
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_library_on_crsp.py backend/tests/test_crsp_blend_book.py -q
python -m scripts.library_on_crsp --part panel                                  # ~5 min
python -m scripts.library_on_crsp --part fundamentals --panel-run <panel id>    # ~10 s
python -m scripts.library_on_crsp --part run --panel-run 2026-09-29T075640Z --fund-run 2026-09-29T041550Z --run-id <id>   # ~12 min, resumable
python -m scripts.library_on_crsp --part board --run-id LIB_2026-09-29T0802Z    # new board id each time
python -m scripts.crsp_blend_book --asof <last bar date>                        # dry run only; v0 is frozen
```

Owed, in order:

1. **Commit before any read of `CRSP_BLEND_v0`.** The files to commit are the two scripts, the two
   tests, this note, the jsonl, the board json/md, the panel/fund receipts, the shadow_bayes receipts,
   and the books.jsonl rows.
2. **The IBES/Compustat/13F bridge** for the 172 rules not run (above).
3. **Put the four-factor gap read on the board itself.** It is computed ad hoc in section 2 and not
   yet in `part_board`.
4. **A combination search with the full count.** Enumerate every 4-cluster blend, not only the one
   read, and deflate at that count, before calling the blend anything but a forward candidate.


---

## 2026-09-29 (afternoon): the two follow-ups the CRSP_BLEND review named

Licence `PRODUCT_EXPERIMENT`, $0, no LLM, no network. No book, ledger or earlier receipt was touched.
Engine unchanged: `run_one`, the 21-draw matched twin, set B alongside. Receipts:

- `crsp_rebuild/followups_daily_FU_2026-09-29T0855Z.{parquet,json}` hold the skip ratios and spreads
  per name and month.
- `crsp_rebuild/followups_FU_2026-09-29T0900Z.json` holds every statistic quoted below.
- `followups_series_FU_2026-09-29T0900Z__<tag>.parquet` holds the monthly series.

The code is `scripts/crsp_blend_followups.py` and `scripts/crsp_blend_followups_run.py`, with tests in
`backend/tests/test_crsp_blend_followups.py`. The baseline reproduces the board: `co03` rule minus twin
is +0.70%/mo, t 2.93, over 406 months.

### RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.**

- `co03`'s gap over its twin survives a one-day skip, a four-month fundamentals lag and per-name
  spreads: +0.56%/mo in 2001-2024, but at t 1.91.
- It is about zero after 2016.
- As a book it loses to the market once real spreads are charged.
- "Large-cap trend survives" does not survive a rank floor after 2000, except in one band width that is
  carried by 2021.

### A. `co03_reversal_in_high_margin`: skip a day, charge real spreads, lag the fundamentals

**Decision line, written into the script before the run:** rule minus twin21 with all three changes,
over 2001-2024.

- At least +0.40%/mo with t >= 2: it remains a candidate.
- At or below +0.10%/mo: FAILED_VARIANT.
- Anything else: CANNOT_DISTINGUISH.

**What changed:**

1. **Entry one session later.** The book enters at the open of t+2, or the close of t+1 when there is
   no open, and exits one session later too. 1991 has no CRSP opens; half of 1992 has them; after that,
   87-99% do.
2. **Per-name, per-month cost from the Corwin-Schultz (2012) high-low spread estimator.**
   - It uses CRSP `askhi`/`bidlo` with the overnight adjustment and averages the 20 two-day estimates
     that end at the decision date. Negative two-day estimates are set to 0, and the estimate is capped
     at 20%.
   - It is charged as a full round trip every month to every name held by the book and by the twin
     alike.
   - The median for eligible names is 64-82 bp, against a flat median of 35 bp.
   - **Known biases, all of which make it an upper bound for these names:**
     - volatility leaks into the high-low range;
     - flooring negatives at 0 biases the average up, most for low-spread names;
     - CRSP high/low on no-trade days are ask/bid;
     - charging a full round trip overcharges the book slightly, because its turnover is 92%, not 100%.
   - The engine's flat band schedule is charged to the twin at the rule's own rate, so it cancels in the
     rule-minus-twin gap. That is why "on top of flat" and "instead of flat" give identical gaps and
     differ only against the market.
3. **Fundamentals lag.** A WRDS ratio row is usable only from max(`public_date`, fiscal period end +
   122 days).

**Rule minus twin21, %/mo (t on 3-month blocks, MDE at 80% power):**

| variant | 1991-2024 | 2001-2024 | 2017-2024 | 2020-24 | LOO-worst 2001-24 (year dropped) |
|---|---|---|---|---|---|
| as run (board) | +0.70 (2.93, MDE 0.67) | +0.59 (2.12, 0.78) | +0.02 (0.04) | -0.27 (-0.45) | +0.37 (2001) |
| skip 1 day | +0.60 (2.55) | +0.60 (1.99) | -0.02 (-0.05) | -0.31 (-0.61) | +0.31 (2001) |
| 4-month fundamentals lag | +0.73 (2.97) | +0.64 (2.24) | +0.14 (0.30) | +0.01 (0.02) | +0.43 (2001) |
| CS spreads, on top of flat | +0.64 (2.71) | +0.54 (1.95) | -0.02 (-0.04) | -0.31 (-0.52) | +0.33 (2001) |
| **all three** | **+0.54 (2.28, MDE 0.66)** | **+0.56 (1.91, MDE 0.82)** | **-0.01 (-0.03, MDE 1.12)** | **-0.20 (-0.38, MDE 1.50)** | **+0.30 (2001)** |

**Rule minus market, all three changes, %/mo:**

| cost | 1991-2024 | 2001-2024 | 2017-2024 | 2020-24 | book CAGR (market 11.2%) |
|---|---|---|---|---|---|
| CS on top of flat | -0.88 (t -2.51) | -0.81 (-1.52) | -1.63 (-1.98) | -1.91 (-1.63) | **-5.9%** |
| CS instead of flat | -0.63 (-1.79) | -0.57 (-1.06) | -1.40 (-1.70) | -1.68 (-1.43) | **-3.0%** |
| as run (flat only) | +0.44 (1.25) | +0.31 (0.63) | -0.29 (-0.35) | -0.40 (-0.33) | 10.9% |

**Rule minus twin by hold year, all three changes (sum, %):**

| 1991 | 1992 | 1993 | 1994 | 1995 | 1996 | 1997 | 1998 | 1999 | 2000 | 2001 | 2002 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| +8 | -2 | -8 | +5 | +8 | -20 | -4 | +42 | +25 | +4 | **+79** | +15 |

| 2003 | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| +16 | +16 | +21 | +11 | +7 | -19 | +14 | +2 | +2 | -12 | -16 | +3 |

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| +20 | +5 | +9 | +2 | 0 | +25 | -4 | +1 | -19 | -14 |

**Turnover and capacity (all three changes):**

- Turnover is 92% a month.
- The median pick trades $8M/day in the 1990s, $14M in the 2000s, $17M in the 2010s and $21M in the
  2020s. The 10th-percentile pick trades $4-5M/day.
- A $10M book puts $0.5M in each name: 3.7% of the median pick's daily volume, and 11.6% of the
  10th-percentile pick's.
- A $100M book puts 37% and 116% respectively, so it is not implementable. Capacity is in the single-digit
  millions.

**What it says:**

- **The bid-ask-bounce hypothesis is mostly refuted for the gap.** The skip moves 1991-2024 by -0.10 and
  2001-2024 by 0.00. Per-name spreads move the gap only -0.06, because the twin's names are just as
  illiquid.
- **The gap is between two losing portfolios once real spreads are charged.** The book pays about
  1.2%/mo in spread, against 0.25%/mo on the flat schedule. The twin compounds at -9.6% a year and the
  book at -5.9%.
- **The whole 2001-2024 number predates 2017.** 2017-2024 is -0.01 and the 2020s are -0.20.
- **2001 alone is +79 of a 2001-2024 total of +161.** Dropping it leaves +0.30%/mo.

**Verdict: the gap over the twin is CANNOT_DISTINGUISH.** +0.56 is above the +0.40 bar, but t 1.91 is
below 2, and the result sits in the pre-stated middle band.

- As a stand-alone book at realistic spreads, `co03` loses to the market in every window. It is
  **DEPRIORITIZED**, and it is not a capital idea at any size.
- The reviewer's two branches were "keeps +0.4 at t 2: re-register" and "about zero: void". Neither
  fired.

### B. "Large-cap trend survives" with a RANK floor

The eligible set on each date is cut to the top 300 or top 500 names by trailing 63-session median
dollar volume. `px_vs_ma200` and `mom_12_1` then run with no further band filter, and the twin draws
from the same cut. The nominal-$100M board versions are shown beside them. Their series starts
1995-07.

**Rule minus twin21, %/mo (t):**

| cell | 1991-2024 | 2001-2024 | 2017-2024 | 2020-24 | 2009 (sum) | 1995-99 share of total | LOO-worst 2001-24 |
|---|---|---|---|---|---|---|---|
| px_vs_ma200, top 300 | +0.63 (2.21, MDE 0.80) | +0.32 (1.29, 0.70) | +0.76 (1.73) | +1.18 (1.84) | -37 | 56% | +0.19 (2024) |
| px_vs_ma200, top 500 | +0.96 (2.68, 1.00) | **+0.84 (2.05, 1.15)** | +1.93 (1.83) | +2.55 (1.54) | -24 | 38% | +0.56 (2021) |
| px_vs_ma200_large ($100M, board) | +0.93 (2.54) | +0.77 (2.02) | +1.85 (1.96) | +2.62 (1.75) | -41 | 32% | +0.50 (2021) |
| mom_12_1, top 300 | +0.84 (2.80, 0.84) | +0.41 (1.54, 0.74) | +1.06 (1.72) | +1.74 (1.91) | -12 | 47% | +0.21 (2024) |
| mom_12_1, top 500 | +0.58 (1.90, 0.86) | +0.11 (0.42, 0.73) | +0.91 (1.72) | +0.93 (1.14) | -24 | 74% | -0.02 (2024) |
| mom_12_1_large ($100M, board) | +0.75 (2.77) | +0.38 (1.46) | +0.62 (1.06) | +0.94 (1.08) | -18 | 44% | +0.25 (2024) |

**Rule minus market, %/mo (t):**

| cell | 1991-2024 | 2001-2024 | 2017-2024 | 2020-24 | 2009 (sum) | CAGR (market 11.2%) |
|---|---|---|---|---|---|---|
| px_vs_ma200, top 300 | +0.80 (2.16) | +0.25 (0.78) | +0.86 (1.60) | +1.63 (2.11) | -24 | 17.5% |
| px_vs_ma200, top 500 | +1.12 (2.42) | +0.81 (1.73) | +2.02 (1.80) | +3.05 (1.76) | -16 | 20.1% |
| mom_12_1, top 300 | +0.94 (2.28) | +0.36 (1.05) | +1.13 (1.57) | +2.05 (2.00) | -8 | 18.0% |
| mom_12_1, top 500 | +0.94 (2.11) | +0.34 (0.90) | +1.35 (1.79) | +1.88 (1.67) | -23 | 17.0% |

**Turnover and capacity:**

- px_vs_ma200 turns over 42-46% a month and mom_12_1 32-33%.
- In the top 300, the median pick trades $23-26M/day in the 1990s and $370-430M/day in the 2020s.
- A $100M book is 3-6% of the median pick's daily volume. Capacity is not the constraint.

**What it says:**

- **Over 1991-2024, a rank floor keeps a t above 2 in three of four cells.** That is the part the review
  suspected: the full-sample number is not only the nominal floor's 17-to-113-name mega-cap book.
- **1995-1999 still carries 38-74% of every total.**
- **After 2000 the picture changes:**
  - `mom_12_1` is +0.11 to +0.41%/mo, t 0.4-1.5;
  - px_vs_ma200 in the top 300 is +0.32, t 1.3;
  - only px_vs_ma200 in the top 500 reaches t 2.05, and its worst leave-one-year-out drops 2021, a
    single +88% year.
- **The result flips with band width.** Top 300 vs top 500 is +0.32 vs +0.84 for trend, and +0.41 vs
  +0.11 for momentum, in opposite directions. A mechanism should not do that.
- **2009 is a -12% to -37% year against the twin in every cell.**

**Verdict:**

- **`px_vs_ma200` in a rank band: CANNOT_DISTINGUISH over 2001-2024.** One of two band widths clears
  t 2, and that one leans on 2021.
- **`mom_12_1` in a rank band: CANNOT_DISTINGUISH**, about zero at the top 500.
- **"Large-cap trend survives, small momentum does not" is DEPRIORITIZED as a finding.** It is not
  purely the nominal-floor artefact the review suspected, because the full-sample t survives a rank
  floor. But its post-2000 evidence is one band width and one year.

### For the owner: `CRSP_BLEND_v0` before entry (recommendation only)

**Neither pre-stated trigger fired:**

- **Void trigger:** `co03` about zero. It did not fire: the gap is +0.56 in 2001-2024.
- **Re-register trigger:** at least +0.4 at t >= 2, plus a rank-based trend sleeve. It did not fire:
  t 1.91, and the rank-based trend is unstable across band widths.

**Recommendation: do not void. Keep it as a free shadow labelled CANNOT_DISTINGUISH / DEPRIORITIZED.**

- Do not re-register it or upgrade it.
- Quote nothing from it as evidence.
- Fix its kill line (review section 6) before any read.

**What argues against keeping it, and why it does not change the recommendation:**

- Both sleeves that carry the blend read about zero or negative since 2017: `co03` is -0.01 in 2017-2024
  and -0.20 in the 2020s.
- The sleeves the forward window will actually test are therefore the ones with the weakest recent
  evidence.

Voiding would save only attention. The shadow costs nothing and cannot adjudicate anything before
2027 either way.

**Owed:** the same skip, spread and lag treatment for `vol_compression`, the blend's other small-name
sleeve. It was not run here.
