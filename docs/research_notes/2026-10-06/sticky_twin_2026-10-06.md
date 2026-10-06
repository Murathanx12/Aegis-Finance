# Sticky twin and the C1 review fixes, 2026-10-07 (CHUNK C1b)

## RESULTS

- **Sticky twin (`STK_2026-10-07_2`, 301 rules, 277 OK, 24 refused): 44 rules at fair-twin t >= 2. 40 of them also have pure selection t >= 2 on the sticky twin. 1 of those 40 also has net-minus-market t >= 2 in validation (2009-2016): `qc761_ebit_ev_ebit_ic_large_annual`.**
- qc761 does not survive as a claim:
  - Its sticky pure-selection t is 2.24 over the full sample but **1.16 in validation**, and 1.51 against the basket twin.
  - Its validation market line is +0.455%/mo at t 2.34. 2009 alone is +20.8%. The 2017-2024 market line is +0.096%/mo (t 0.36).
  - The bridges board reads it on its declared line against the sticky twin. There it is CANNOT_DISTINGUISH: rule-twin t 1.83 over 1991-2016, DSR 0.008.
  - It was found by looking: it was flagged on 09-30 and is 1 of 301.
- A stricter read: sticky fair-twin t >= 2 AND pure selection t >= 2 on **both** twins gives 25 rules. **0** of them beat the market in validation.
- Fixed fair board (`FT_2026-10-07_1`, 301 OK) and the re-issued boards:
  - Library: ALPHA_DETECTED 6, NET_EDGE_FROM_TURNOVER 7. All 6 ALPHA rows have a **negative** validation market line (t -0.61 to -1.61).
  - Bridges: CANNOT_DISTINGUISH 41, FAILED_VARIANT 38, NOT_DECIDABLE 6. 0 registration candidates.
- RESULT IMPROVEMENT: NONE. The control is fairer now. Nothing beats the market.

## What was built

1. **`matched_twins.twin_series_sticky`** sits beside the registered `twin_series`, which is unchanged: a test pins it byte-identical with a hash taken before the edit.
   - It is declared as `TWIN_STICKY_v1` in `docs/research_notes/2026-10-06/DECLARATION_TWIN_STICKY_v1.json`. The body sha256 is `7333553e17ea6471...` and the code sha256 is `a4b29e5136c49510...`.
   - A sticky run refuses if the declaration is missing, or if the code no longer hashes to the declared value.
2. **How the sticky twin draws partners.** When the rule enters a name, it draws one partner per draw from that name's size × vol × 12-1 cell as of the entry date, and holds it until the rule exits the name.
   - It redraws when the partner dies or stops returning, and when the rule buys the partner (a collision). Every redraw is counted.
   - Each partner carries its matched name's weight.
   - There are 21 draws, seeded `seed_for(rule, j)`.
   - Both legs pay `trade_cost`.
3. **The receipt check.** The median over invested months of |twin turnover − rule turnover| must be ≤ `config.STICKY_TWIN_TURNOVER_TOLERANCE` (0.03), or the row is refused with the gap.
   - Months with a death or collision redraw are excluded from that median, following the review's spec.
4. **Review fixes (`docs/reviews/REVIEW_2026-10-06_C1_FAIR_TWIN.md`):**
   - **F1/F2.** The bridges board now reads its four columns from the fair board's per-rule series: one engine, one `trade_cost`, and one unit (one-way traded weight per month) for the rule and the twin.
     - The two-run `turnover_scaled_net` interpolation is gone.
     - `book_profile`'s names-replaced-per-rebalance is printed only as a diagnostic.
     - qc761's rule turnover there is now 0.071, not 0.47. Its fair t over 1991-2016 is now 2.78, not 0.79.
   - **One cost composition.** `matched_twins.round_trip_spread` / `TWIN_COST_COMPOSITION` (max(CS capped at 20%, flat band)) is called by `hyp_investable.spreads_of` and `conditionals_on_crsp`.
   - **F3.** On the library fair board, ALPHA_DETECTED now needs pure selection t >= 2 as well as fair t >= 2. Otherwise the label is `NET_EDGE_FROM_TURNOVER`. The board prints `FAIR_HEADLINE_RULE` as `headline_rule`.
   - **F4.** Rule weights are carried: `carried_picks` → `run_book` → the sticky twin.
     - The board also adds each weight rule's column: `vol_63` for `inv_vol`, `amihud` for `inv_amihud`.
     - **Found on the way:** `amihud` is not in `rule.requires`. So `mom_12_1_liqw` and `qc623_mom63_liquidity_weighted` were still EW in `FT_2026-10-07_1` and `STK_2026-10-07_2`, because `strategy_library._weights` fills a missing column silently.
     - Both were re-scored in the supplements `FT_2026-10-07_2` and `STK_2026-10-07_3`, which supersede those two rows.
     - Basket: fair t 2.18 and 2.13. Sticky: 1.88 and 2.18. Validation market t: -1.13 and -1.04. No count above changes except one: liqw drops out of the sticky ≥ 2 list, where it never was.
   - **F5.** The library receipt states in `caveats` that the cost model and the twin's turnover cannot be separated, and that the calendar and FF3+UMD verdicts are carried over from a different book.
   - **Item 7, tests:**
     - The rule's and the twin's turnover are bound from `trade_cost` in both `run_book` and `twin_series_sticky`.
     - A real book measured both ways gives the same turnover and cost.
     - The AST guard now also catches `x or 1.0`, `.get(k, 1.0)` and `.fillna(1.0)` on turnover names.

## Verdict diff: basket fair twin (FT_2026-10-07_1) vs sticky twin (STK_2026-10-07_2)

**Turnover is closed.** Over the 277 OK rules, the median of (twin − rule) mean turnover is **0.002 on the sticky twin**, against 0.027 on the basket. On the basket it was about +0.25 for the low-turnover rules.

**The random controls are now sane:**

| control | basket fair t | sticky fair t |
|---|---:|---:|
| `random_1` | -2.76 | -0.26 |
| `random_2` | -2.97 | -0.37 |
| `random_3` | -3.40 | -0.53 |

On the basket, a random rule "lost to its twin at t 3" on turnover alone.

Counts at t >= 2, full sample:

| | basket | sticky |
|---|---:|---:|
| fair twin | 35 | 44 |
| pure selection | 28 | 45 |

**Two effects move in opposite directions.**

- **Low-turnover quality and value rules lose their twin-cost tailwind.** Fair-twin net moves −21 bps/mo (median, rules with turnover < 0.2), while pure selection barely moves (−1 bps):

  | rule | basket fair t | sticky fair t |
  |---|---:|---:|
  | `quality_composite` | 3.40 | 1.47 |
  | `ope_be` | 3.81 | 1.97 |
  | `gross_margin` | 3.03 | 1.72 |
  | `roe` | 2.41 | 1.16 |
  | `qp0025_small_annual` | 2.27 | -0.28 |
  | `blog01_roe_adv_annual_large` | 2.34 | 0.52 |
  | `qc241_value_composite_small_annual` | 3.01 | 1.78 |

  This is exactly the reviewer's finding: the basket fair t was the twin's churn.

- **Momentum-type rules gain on pure selection against the sticky twin.** The momentum family is up a median +10 bps/mo and the trend family +15. Examples:

  | rule | basket fair t | sticky fair t |
  |---|---:|---:|
  | `cascade_entry_timing` | 1.24 | 3.43 |
  | `co03_reversal_in_high_margin` | 1.21 | 2.81 |
  | `mom_in_calm` | 1.07 | 2.46 |
  | `flow_acceleration` | 0.74 | 2.35 |

  The mechanism is a staleness bias, and it is a caveat on the sticky twin, not on the rules:
  - A monthly momentum rule keeps a name only while it is still a winner.
  - Its partner was matched on momentum at entry and is held regardless.
  - So the partner's momentum decays while the rule's does not.
  - The sticky twin is a weaker STYLE control for any rule whose holding is conditional on a fast-moving characteristic.

**Refused rows (24).** All are high-turnover short-horizon or large/mega-band rules: `rev_1m*`, `rev_5d_large`, `qc372_oversold_snapback_mega`, `illiquid*`, `eap_*`, `random_large`. The median gap is 0.0305-0.0777 against a tolerance of 0.03.

- Their residual gap is EW re-weighting of drifted books with large monthly moves, plus redraws in thin mega cells.
- They are refused, not read.

**A weakness in the declared check.** Because a month is excluded when ANY of the 21 draws redrew, the median rule has **83% of its months excluded** from the median-gap test. The check still passes on the overall means (e.g. qc761: twin 0.077 vs rule 0.071 per month), but it is weaker than it reads. A v2 should exclude per draw, not per month. That was not changed after the run.

## Which twin the boards should read by default

**Read the sticky twin for the cost-fair column (`fair_twin_net`), and require pure selection t >= 2 on BOTH twins before a twin verdict is cited.**

- The sticky twin is the fair cost control for a holding rule. It trades when the rule trades, and as much: a median gap of 0.002 a month. With it the random controls fall back to about zero, and the basket's cost artefact disappears from the quality and annual rules.
- It is not a better style control. For a monthly momentum or trend rule it lets the partner's characteristic decay, while the rule's book re-selects on that characteristic. Its pure-selection column flatters those rules by about 10-15 bps/mo.
- The monthly re-matched basket is the stronger style control and the worse cost control. So a "beats its twin" claim needs both:
  - sticky `fair_twin_net` t >= 2;
  - pure selection t >= 2 on the sticky twin AND on the basket.
- Under that conjunction, 25 rules qualify and none beats the market in validation.
- The registered monthly 21-draw twin (`matched_twins.twin_series`) stays the construction of record for TRIAL-LIB-FWD-TWIN-1 and CRSP_BLEND_v0 until their reads. Nothing about either trial was touched.

## Forward graders (TRIAL-LIB-FWD-TWIN-1, CRSP_BLEND_v0)

- **Who reads them:**
  - TRIAL-LIB-FWD-TWIN-1 is read by `backend/services/lib_forward_trial.py`: `pooled_z` over frozen book − frozen twin returns, with twin type `matched_random`, else `random_same_band`.
  - CRSP_BLEND_v0 is read by `scripts/shadow_grade.py` `grade_book`: the NAV gap against `matched_twin21`, at sleeve scale, with the amended kill line.
- **Where the returns come from.** Both take their returns from `llm_portfolio.grade_books`.
  - Each frozen book, parent and twin alike, pays half its names' band round trip (`xs_ranker.round_trip_bps`) **once at entry**, and nothing trades afterwards.
  - Neither reads `TWIN_COST_CONVENTION` or `TWIN_COST_COMPOSITION`.
- **Which twin was frozen.** The CRSP_BLEND_v0 twin was drawn ONCE at freeze, 21 draws, on band × vol × 12-1 cells (`scripts/crsp_blend_book.matched_twin`, `scripts/shadow_bayes_rule.matched_twin21`).
- **The forward twin is already sticky.** A frozen buy-and-hold twin holds one partner per holding until the book's horizon, so its turnover equals the parent's (entry only) by construction.
- **No shadow column was added.** A `shadow_sticky_twin` series would be identical to the registered twin over the forward window, so it would add nothing.
- **One real dependency.** The backtest sigmas these trials froze come from the monthly-redrawn twin series:
  - LIB-FWD-TWIN-1 uses `matched_twins_monthly_2026-09-27T082553Z`.
  - CRSP_BLEND_v0's kill-line sd uses flat-run `rule_net − twin21_net`, which is pure selection.

  Those are registered inputs. They are reported here and not changed.

## Receipts

- **Declaration:** `docs/research_notes/2026-10-06/DECLARATION_TWIN_STICKY_v1.json`
- **Fixed basket fair board** (rule weights carried, one cost composition):
  - `backend/data/optimus/hyp_lab/twin_board_FT_2026-10-07_1.jsonl`
  - `backend/data/optimus/hyp_lab/twin_board_SUMMARY_FT_2026-10-07_1.json`
  - series: `hyp_lab/fair_twin_series_FT_2026-10-07_1/`
- **Weight supplement** (supersedes the two `inv_amihud` rows): `hyp_lab/twin_board_FT_2026-10-07_2.jsonl` and `twin_board_SUMMARY_FT_2026-10-07_2.json`
- **Sticky board:**
  - `backend/data/optimus/hyp_lab/twin_board_STK_2026-10-07_2.jsonl`
  - `backend/data/optimus/hyp_lab/twin_board_SUMMARY_STK_2026-10-07_2.json` (status PARTIAL: the 24 refusals are named)
  - series: `hyp_lab/fair_twin_series_STK_2026-10-07_2/`
  - supplement: `hyp_lab/twin_board_STK_2026-10-07_3.jsonl`
- **Re-issued boards on the fixed basket:**
  - `backend/data/optimus/crsp_rebuild/bridges_board_BR_FLAT_2026-09-29T1535Z__FT_2026-10-07_1__2026-10-06T182820Z.json`
  - `backend/data/optimus/crsp_rebuild/library_fair_board_LIB_2026-09-29T0802Z__FT_2026-10-07_1__2026-10-06T182826Z.json`
- **The same boards on the sticky twin (read beside):**
  - `crsp_rebuild/bridges_board_BR_FLAT_2026-09-29T1535Z__STK_2026-10-07_2__2026-10-06T190836Z.json` (85 OK: CANNOT_DISTINGUISH 44 / FAILED_VARIANT 35 / NOT_DECIDABLE 6)
  - `crsp_rebuild/library_fair_board_LIB_2026-09-29T0802Z__STK_2026-10-07_2__2026-10-06T190841Z.json` (123 of 140; 17 refused by the sticky check)
- **Superseded:**
  - `FT_2026-10-06_1` (weights dropped; the bridges board's mixed units)
  - its two re-issued boards
- **VOID:** the smoke runs `STK_SMOKE_2026-10-07_1` and `FT_SMOKE_2026-10-07_1`.
  - Also VOID: the pre-declaration sticky run `STK_2026-10-07_1`. It was killed for low memory at 254/301, it ran on the EW-dropping engine, and its check did not exclude death/collision months. It is not read.
- Board timestamps in the file names are UTC.

## Reproduce

```
python -m scripts.hyp_twin_board --run-id <FT> --twin basket
python -m scripts.hyp_twin_board --run-id <STK> --twin sticky          # >= 4 GB free; ~38 min
python -m scripts.bridges_on_crsp --part board --declaration BD_2026-09-29T1530Z --flat-run BR_FLAT_2026-09-29T1535Z --cs-run BR_CS_2026-09-29T1545Z --turnover-run BT_2026-09-29T1555Z --fair-run <FT|STK>
python -m scripts.library_on_crsp --part fair_board --run-id LIB_2026-09-29T0802Z --fair-run <FT|STK>
```
