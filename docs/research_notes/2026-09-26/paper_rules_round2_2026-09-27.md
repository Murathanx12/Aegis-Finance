# Paper rules round 2 — SSRN via OpenClaw (2026-09-27)

**Licence: `PRODUCT_EXPERIMENT`.** Every "claimed" number is the source's own;
every measured number is from the receipt named in §3. No LLM spend.

Source note: `research_ssrn_via_openclaw_browser_signal_candidates.md` (§3 specs,
§4 interaction hypotheses). Code: `backend/services/strategy_library_ext.py`
(round-2 block, `attach_round2_columns`), `backend/services/pit_features.py`
(`news_tone_features`, `tone_frame`, `score_corpus_tone`). Registered
`REGISTERED_ROUND2 = 2026-09-26T18:15:00Z`, before any score.

## 1. Where each of the five landed

| rule | family | column | status | named controls (registered) | claimed by source |
|---|---|---|---|---|---|
| `distance_to_default_rising` | credit_risk | `d2d_chg` (naive Merton DD from `mkt_value`, `vol_252`, `mom_252`, SEC `debt`) | **SCORES** | `gross_margin`, `random_1`, twin `distance_to_default_rising_21_40`, §4-H1 `distance_to_default_rising_in_stress` | rising default risk → higher returns (no number) — Vassalou & Xing 2004 |
| `news_tone_reversal_5d` | news_tone | `news_tone_z` (new, archive rows excluded) | **REGISTERED, FORWARD-ONLY** — 0 non-NaN values | `fomo_reversal_5d`, `attention_shock_fade`, twin `news_tone_reversal_5d_21_40` | pessimism → lower next-day return → partial reversal in ~1 week — Tetlock 2007 |
| `filing_similarity_change` | textual_similarity | `filing_similarity` | **EXT_NOT_REACHABLE** — needs 10-K/10-Q narrative text; FREE: EDGAR `Archives/edgar/data/<CIK>/<accession>.txt` + `data.sec.gov/submissions` | (declared) `rd_intensity`, `random_1`, twin | 5.47%/yr, Sharpe 0.84, 2007-2020 — Padysak 2021 |
| `call_tone_drift` | earnings_call_tone | `call_tone_z` | **EXT_NOT_REACHABLE** — needs call transcripts; no free source confirmed (8-K EX-99 bodies on disk are press releases) | (declared) `ear_drift`, `news_tone_reversal_5d`, twin | tone dominates surprises over 60 days (no number) — Price et al. 2012 |
| `opex_week_large_hold` | calendar_options | `is_opex_week` (built, free) | **EXT_NOT_REACHABLE — engine, not data**: measured 0 of every month-end decision row falls in an opex week, so the rule selects nothing | (declared) `random_1` | 9.3%/yr, Sharpe 0.61, 1988-2010 — Stivers & Sun |

Every DOI cited on the rules was resolved via api.crossref.org on 2026-09-27.

## 2. The two enablers

### (b) VAL-01 — it WAS a join bug, and it is fixed

The refused construction was *adjusted close × as-filed SEC shares*: the bars
are split- and dividend-adjusted, so every future split rescales the past
price while the share count stays as filed. The fix joins on one basis:
Compustat `cshoq × prccq` is a **raw** market value at the quarter's
`datadate`, available at `rdq + 2d`, rolled to the decision date by
`adj_close(t) / adj_close(datadate)` — the future split factor is in both
closes and cancels. Residuals: dividends between datadate and t (≤ ~2%) and
issuance after datadate (ignored, as in any quarterly cap join).

Validation against CRSP `|prc| × shrout` (random ~400 CRSP names per date,
matched by ticker):

| date | fixed: median \|log err\| | fixed: within 10% | refused construction: median \|log err\| | refused: within 10% | refused: off ≥2× |
|---|---|---|---|---|---|
| 2019-06-28 | 0.54% | 90.5% | 13.5% | 40.3% | 10.4% |
| 2020-08-31 | 0.23% | 91.2% | 10.9% | 47.1% | 8.2% |
| 2022-06-30 | 0.65% | 89.5% | 5.4% | 64.2% | 9.3% |
| 2024-06-28 | 0.84% | 83.5% | 3.2% | 78.2% | 8.0% |

The refused construction's error shrinks toward 2024 — fewer future splits left
to contaminate it — which is the look-ahead signature VAL-01 described.

**The one data gap left:** Compustat fundq on disk ends at datadate
2024-12-31, so with the 460-day staleness rule every market-value column is NaN
from **2026-04-06**. A Compustat pull for 2025Q1+ closes it.

Rules that leave `EXT_NOT_REACHABLE` because of this enabler: **3**
(`EXT-QC-14g` → `qc409_book_to_market`, `EXT-QC-10` →
`qc241_value_composite_small_annual`, `EXT-QC-13` →
`qc761_ebit_ev_ebit_ic_large_annual`), plus `distance_to_default_rising`,
which was never filed there. Base `NOT_REACHABLE` VAL-01..05 strings are
updated; `EXT-QP-05` (buybacks) and `INV-02` (issuance) stay blocked.

### (a) `news_tone_z` — the tone pipeline the note assumed does not exist

`sentiment_analyzer` scores FinBERT on demand for the website. **Nothing stored
a per-row tone over `news_corpus`.** So the enabler is two pieces:
`score_corpus_tone` (FinBERT over non-archive, ticker-tagged titles → cache
`news_corpus/_tone/finbert_tone.jsonl`, REFUSES instead of falling back to
keywords) and `news_tone_features` (5 vs 126 covered sessions by
`first_seen_utc`, archive rows excluded from both items and coverage). The
scorer was **not run tonight** (memory), and it would not matter yet: the
corpus began 2026-09-11 and the column needs 60 covered baseline sessions, the
same wall `attention_z` hits (0 non-NaN on the pit_features receipt).

Rules that leave `EXT_NOT_REACHABLE` because of this enabler: **0 scoring**; 1
registered forward-only (`news_tone_reversal_5d` + twin). `call_tone_drift` is
not unblocked by tone — its gap is transcripts.

A finding on the way: `attention_z` (chunk C) does **not** exclude archive rows —
`news_frame` reads every row's `first_seen_utc`, so the 36,720 archived
Benzinga headlines all bucket onto 2026-09-11. It is invisible today (the
column is all-NaN) and will be a spike the first day the baseline fills.
Not fixed here (chunk C's column, flagged).

## 3. The factory run

**Run `2026-09-26T182110Z`** (`python -m scripts.night_backtest_factory --no-freeze`,
started 02:21 local with 4.75 GB free, PID 130876, 349 s): 306 rules, 868 cells
looked at, 5 refusals (all `FORWARD_ONLY`: the three attention rules and the two
tone rules). Panel fingerprint `3a8c19576fafb9a4`, 372,754 rows, 117 dates.
Receipts: `strategy_library/leaderboard_2026-09-26T182110Z.json`,
`run_2026-09-26T182110Z.json`, `round2_readout_2026-09-26T182110Z.json` (every
new rule beside its named controls + ETF decomposition),
`signal_structure/signal_structure_2026-09-26T182110Z.json`
(`python -m scripts.signal_structure --run-id 2026-09-26T182110Z`: it decomposes
only the top-30 cells, so the new rules' betas were fitted from its
`monthly_returns_*.parquet` with the same `SS.ols` / `factor_spreads` and are on
the round-2 readout). The receipt of record `T164302Z` is not changed.

Column support on the run: `mkt_value` 215,945 rows (≈22-24k per year
2017-2025, 5,783 in 2026 — the Compustat gap), `book_to_market` 180,972,
`earnings_yield` 173,863, `ebit_ev` 93,083, `ebit_ic` 118,248, `d2d_chg`
113,621; `is_opex_week` = 1 on **0 of 372,754** decision rows.

"Dev" = pre-2024 excess CAGR vs SPY; "2024-26" = the declared 2024-26 window
(seen data, not a holdout); DSR at the 868 cells looked at.

| rule (k) | dev vs SPY | 2024-26 vs SPY | DSR | LOO-worst mean active /mo | top-5-month share | max DD | years + of 10 | dev α t (IWM β, t) | 2024-26 α t (IWM β, t) | SMH β / MTUM β (dev) |
|---|---|---|---|---|---|---|---|---|---|---|
| `distance_to_default_rising` (20) | +1.9% | −4.8% | 0.0009 | −0.32% | 0.80 | −29.4% | 3 | 1.08 (0.90, 3.1) | 0.56 (0.71, 2.5) | 0.23 / 0.49 |
| ctl `distance_to_default_rising_21_40` | −3.1% | −3.9% | 0.0002 | −0.36% | 0.59 | −34.7% | 3 | 0.53 (0.71, 5.2) | 0.98 (0.71, 2.2) | 0.01 / 0.23 |
| ctl `distance_to_default_rising_in_stress` | −8.5% | −15.6% | 0.0 | −0.97% | 1.50 | −27.9% | 3 | −0.47 (0.68, 4.4) | −2.02 (0.03, 0.2) | 0.10 / −0.13 |
| `qc409_book_to_market` (20) | +2.5% | +14.5% | 0.0162 | +0.32% | 0.69 | −62.7% | 6 | 2.02 (0.98, 3.6) | 1.59 (1.34, 3.7) | −0.50 / −0.28 |
| `qc241_value_composite_small_annual` (25) | +7.7% | −4.0% | 0.0107 | +0.21% | 0.67 | −49.7% | 6 | 3.00 (0.95, 4.5) | 1.10 (1.58, 8.5) | 0.08 / 0.06 |
| `qc761_ebit_ev_ebit_ic_large_annual` (50) | +2.9% | −7.0% | 0.0017 | −0.03% | 0.44 | −29.3% | 6 | 2.78 (0.15, 2.0) | −0.21 (0.16, 1.6) | −0.05 / −0.07 |
| ctl `random_1` (20) | +0.8% | −10.6% | 0.0004 | — | — | — | 5 | — | — | — |
| ctl `gross_margin` (20) | −2.0% | −17.9% | 0.0 | — | — | — | 4 | — | — | — |
| `news_tone_reversal_5d` (+ twin) | refused FORWARD_ONLY | | | | | | | | | |

`distance_to_default_rising` by year (excess vs SPY): 2017 −3.2%, 2018 −11.8%,
2019 −2.6%, **2020 +61.0%**, 2021 −7.3%, 2022 +13.7%, 2023 −26.4%, 2024 +0.8%,
2025 −6.3%, 2026 −2.0%. Without its best 5 months it compounds 3.0%/yr vs SPY
15.0%.

**Falsifiers.**

- `distance_to_default_rising` (a) *not fired on the letter* — dev +1.9% is above
  `gross_margin` (−2.0%) and `random_1` (+0.8%); (b) *not fired* — the 21-40 twin
  earns −3.1%, so the ordering is not flat; (c) **fired in substance** — the dev
  number is 2020 alone (top-5-month share 0.80, LOO-worst negative, 3 of 10 years
  positive), its IWM-SPY beta is 0.90 (t 3.1) and the alpha after the ETF spreads
  is t 1.08 dev / 0.56 in 2024-26, and it trails SPY in 2024-26. Status:
  **DEPRIORITIZED** (this construction; the credit_risk family is not rejected —
  one naive-DD build with long-term debt only).
- §4-H1 `distance_to_default_rising_in_stress` — **fired**: Sharpe 0.35 vs the
  ungated 0.63, and worse in both windows. The premium-not-probability
  distinction does not show on this panel (with market vol as the stress proxy;
  no credit spread on disk).
- Value unlocks (`if dev excess is not above random_1's`) — **none fired**: all
  three beat `random_1` in dev. Every one is a small-cap book first: IWM-SPY
  β 0.95-1.58 (t up to 8.5) except `qc761` (0.15). Alpha survives the ETF
  spreads in dev (`qc241` t 3.00, `qc761` t 2.78, `qc409` t 2.02) and does not
  clear t 2 in 2024-26 for any of them (`qc409` 1.59, `qc241` 1.10, `qc761`
  −0.21). `qc409_book_to_market` is the only one above SPY in both windows, with
  a −62.7% max DD and DSR 0.016.
- `news_tone_reversal_5d` — not evaluable (no history).

The dev-selected sentence on this run is unchanged from `T164302Z` (+8.8 pp/yr,
median +2.6 pp, 6 of 10); no round-2 rule enters the top-10 by DSR.

## 4. The §4 interaction hypotheses

| # | hypothesis | status |
|---|---|---|
| 1 | D2D premium lives only where credit is stressed (Friewald-Wagner-Zechner) | **registered control** `distance_to_default_rising_in_stress` (regime gate `mkt_stress`; market vol, not a credit spread — none on disk) |
| 2 | tone survives a control for news COUNT | **not yet** — both columns are forward-only; needs the cross-sectional regression once `news_tone_z` has values |
| 3 | filing self-similarity ≠ R&D intensity | **declared** — `rd_intensity` is the named control on the waiting spec; runs when `filing_similarity` exists |
| 4 | option signals degrade with firm size | **not yet** — no options rule is reachable; the waiting opex spec is already `universe_rule="large"` |
| 5 | ESG momentum is price momentum in a label | **not yet** — no ESG feed |
| 6 | patent signals concentrate in low-attention names | **not yet** — no patent feed registered (note: `wrds/bulk/wrdsapps_patents__uspatents_gvkey_linking.parquet` is on disk; the link, not the patents) |
