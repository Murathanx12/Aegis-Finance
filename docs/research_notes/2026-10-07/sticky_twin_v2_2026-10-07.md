# Sticky twin, turnover check v2 (per draw), 2026-10-07 (Q9a item 1)

Licence `PRODUCT_EXPERIMENT`. $0 LLM. A check version, not a new twin.

## RESULTS

- **Sticky twin with the per-draw check v2 (`STK_2026-10-07_v2_1`, 301 rules): 284 OK, 17 refused (v1: 277 OK, 24 refused).**
  - 44 rules at fair-twin t >= 2.
  - 40 of those also have pure selection t >= 2.
  - **1** of those 40 also has net-minus-market t >= 2 in validation: `qc761_ebit_ev_ebit_ic_large_annual`, the same rule as under v1.
  - Stricter read (selection t >= 2 on both the sticky and the basket twin): **25 rules, 0 of which beat the market in validation.**
- The headline counts are identical to v1 (44 / 40 / 1 / 25 / 0). The verdict changes are all in rules far from t 2.
- **Scoreboard sentence:** *Sticky twin, per-draw check v2 (STK_2026-10-07_v2_1, 301 rules): 284 OK, 17 refused (v1: 277 OK); 44 at fair-twin t >= 2, 40 of them with pure selection t >= 2, 1 of those with net-minus-market t >= 2 in validation (qc761_ebit_ev_ebit_ic_large_annual); selection t >= 2 on both twins: 25, of which 0 beat the market in validation. RESULT IMPROVEMENT: NONE.*

## What v2 changes

- **v1** (`sticky_turnover_check`) excludes a **month** if any of the 21 draws redrew a partner (a death or a collision).
  - Measured on this run, the median rule had **82.8%** of its invested months excluded.
- **v2** (`matched_twins.sticky_turnover_check_per_draw`) excludes the month only for the draw that redrew.
  - The gap is the median of |draw j's twin turnover − rule turnover| over all retained (draw, month) pairs.
  - The median rule has **14.6%** of its pairs excluded.
  - The tolerance stays **0.03**. The refusal rule is unchanged.
- **v2 is the stricter test in one sense.** v1 compared the rule with the *mean* turnover over 21 draws, where draw-to-draw noise cancels. v2 compares it with each draw.
  - The median gap rose only from 0.0087 to 0.0099.
  - The median per-rule change (v2 − v1) is +0.0017.
- **The construction did not change:**
  - Draw j is re-run alone under `_draw_id(rule, j)`, whose draw-0 seed is v1's `seed_for(rule, j)`.
  - For all 276 rules OK on both boards, every twin column of the v2 series matches the v1 series to **≤ 5.6e-16**.
  - Fair-twin and selection t match exactly (0 mismatches).
  - The three v1-hashed functions are byte-identical: the code hash is still `a4b29e51…`.

## Verdict changes, rule by rule (full table: `per_rule` in the receipt)

| rule | change | v1 gap | v2 gap | v2 fair t | v2 sel t | v2 mkt-validate t |
|---|---|---:|---:|---:|---:|---:|
| gh11_skip_month_composite_q | OK → REFUSED | 0.000 | 0.0367 | (v1: +0.64) | (v1: +1.02) | (v1: −2.27) |
| cluster_unconfirmed | REFUSED → OK | 0.0353 | 0.0268 | −0.90 | −0.70 | −0.62 |
| eap_avoid_mom | REFUSED → OK | 0.0401 | 0.0278 | −0.61 | +0.02 | −3.13 |
| eap_lowvol | REFUSED → OK | 0.0326 | 0.0070 | +0.43 | −0.11 | −1.72 |
| flow_accel_mom | REFUSED → OK | 0.0324 | 0.0217 | +0.61 | +0.91 | −2.25 |
| illiquid | REFUSED → OK | 0.0326 | 0.0242 | −3.90 | −2.63 | −1.44 |
| mom_in_laggard_sectors | REFUSED → OK | 0.0357 | 0.0192 | −2.81 | −2.37 | −1.22 |
| qc372_oversold_snapback_mega | REFUSED → OK | 0.0777 | 0.0239 | +1.08 | +1.17 | −0.14 |
| runup_exit_before_large | REFUSED → OK | 0.0325 | 0.0000 | +0.28 | +0.36 | −1.70 |

- **gh11_skip_month_composite_q** is the case v1 could not see. Its v1 gap was 0.000 because:
  - 79% of its (draw, month) pairs carry a redraw, so v1 dropped nearly every month;
  - in the months that remained, the over- and under-trading draws averaged to zero.
  - Per draw, the median gap is 0.037 (per-draw medians 0.027-0.046), so it is now refused.
- **The 16 rules refused under both checks** are the same family as before: short-horizon reversal (`rev_1m*`, `rev_5d_large`, `rev5_lowvol_large`, `mom_rev`, `rev_in_winners`, `buy_the_dip`, `attention_reversal`) and large or mega-band rules (`hi52_large`, `low_max_large`, `seasonality_hs_large`, `random_large`), plus `illiquid_mid_plus`, `seas_mom` and `eap_mom`. Their v2 gaps run from 0.032 to 0.080.
- Every rule that changed verdict sits at |fair t| < 2, except `illiquid` (−3.90) and `mom_in_laggard_sectors` (−2.81). Both of those are significantly **negative**. No count above moves.

## The one positive, printed in full (`positives_detail` in the receipt)

`qc761_ebit_ev_ebit_ic_large_annual`. Its series is identical to v1, so the C1b reading stands:

| column | full | design | validate | late | 1991-2016 |
|---|---|---|---|---|---|
| fair twin net, %/mo (t) | +0.30 (2.33) | +0.35 (1.38) | +0.22 (1.20) | +0.30 (1.34) | +0.30 (1.83) |
| pure selection, %/mo (t) | +0.29 (2.24) | +0.33 (1.31) | +0.22 (1.16) | +0.29 (1.31) | +0.28 (1.75) |
| net minus market, %/mo (t) | +0.22 (1.74) | +0.13 (0.65) | **+0.45 (2.34)** | +0.10 (0.36) | +0.27 (1.83) |

- **By year.** The fair-twin line is negative in 8 of 28 hold years. The market line's largest year is **2009, +20.8%**.
- **Leave one year out.**
  - Fair twin: worst full-sample mean +0.25%/mo, without 2000.
  - Market line: worst full-sample mean +0.16%/mo, without 2009.
- **Why it is not a claim:**
  - The validation market t of 2.34 sits on a window that holds 2009.
  - Within validation, its sticky selection t is 1.16.
  - It is 1 of 301 rules, and it was flagged by looking (09-30).
  - Nothing here changes C1b's verdict: **CANNOT_DISTINGUISH**.

## Receipts

- Declaration (written and hashed **before** the run; it pins the v1 construction hash, the v2 code hash and the 0.03 tolerance): `docs/research_notes/2026-10-07/DECLARATION_TWIN_STICKY_v2.json`.
  - body sha256 `e09fcaaae7f22600…`
  - code sha256 `67a6c2fe9f6495fa…`
- Board: `backend/data/optimus/hyp_lab/twin_board_STK_2026-10-07_v2_1.jsonl`, `twin_board_SUMMARY_STK_2026-10-07_v2_1.json`, and the series in `fair_twin_series_STK_2026-10-07_v2_1/`.
  - Every row carries **both** checks: `sticky_turnover_check` (v2) and `sticky_turnover_check_v1`.
- v1 vs v2 comparison: `backend/data/optimus/hyp_lab/sticky_v2_compare_STK_2026-10-07_v2_1.json` (`python -m scripts.sticky_v2_compare --v2-run STK_2026-10-07_v2_1`).
- **Run incident, recorded.** At 13:07 HKT another session ran `git stash -u` in this working tree (`stash@{0}`, "epitaxy: pre-switch").
  - It removed the board's jsonl (63 rows) and this work's uncommitted code from disk, while the board process kept running on the code it had already loaded.
  - The files were restored byte for byte from the stash by read-only `git show`. The stash was neither popped nor dropped.
  - The board process (stopped by its own PID) was resumed under the same run id from the merged rows. A resume skips scored rules, and rows are deterministic.
  - The series parquets were never removed.

## Reproduce

```
python -m scripts.hyp_twin_board --run-id <new id> --twin sticky --sticky-check v2   # >= 4 GB free; ~1.8 h (21 single-draw passes)
python -m scripts.sticky_v2_compare --v2-run <new id>
```
