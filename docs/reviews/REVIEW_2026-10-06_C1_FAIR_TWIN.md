# REVIEW 2026-10-06: CHUNK C1, the fair twin in shared code

Adversarial review by a second Opus, written as a quant who thinks the build is wrong. Licence of everything reviewed: `PRODUCT_EXPERIMENT`. Read-only: no board was re-run. Every number below comes from the C1 receipts, recomputed with read-only Python over the stored series.

## VERDICT: MERGE WITH FIXES

The shared-code half is right, and it is overdue. There is now one `trade_cost`, the missing turnover refuses instead of defaulting to a full round trip, and the AST guards do fail on the pre-C1 code. The measurement half is not yet symmetric. The fair-twin board has **one** structural asymmetry, which the builder disclosed: the twin churns 0.3-0.6 a month and the rule does not. The bridges board has **two more**, which were not disclosed: the rule's turnover there is measured in different units from the twin's, and the twin it scales is not the twin whose turnover it measured. The library re-issue also loosened its headline rule, so 7 rules are now labelled ALPHA_DETECTED with pure selection below t 2. None of this changes the bottom line against the market. It does change what "beats its twin" may be used for.

Fixes required before the re-issued verdicts are cited anywhere:

1. **F1 (bridges):** take the rule's turnover from the same instrument as the twin's (the fair board's `turnover`, which is one-way traded weight per month), not from `book_profile`. `book_profile` measures name replacement per **rebalance**. Re-issue the 6 hold-3 and hold-12 rows.
2. **F2 (bridges):** either scale `twin21` by `twin21`'s own measured turnover, or read the fair column from the basket twin the turnover came from. Today a basket's turnover scales a different object.
3. **F3 (library):** a fair-twin ALPHA label requires pure selection t >= 2 as well. Otherwise call it `NET_EDGE_FROM_TURNOVER`, not ALPHA_DETECTED. Fix the printed `headline_rule` text, which still says "rule - twin21".
4. **F4 (fair board):** `run_book` / `carried_picks` drop the rule's weights. 9 inverse-vol, liquidity-weighted and risk-parity rules were scored as their equal-weight parent. Pass `h["weights"]` through, or refuse non-EW rules by name.
5. **F5 (receipt hygiene):** state on the library receipt that the cost step (pure -> fair) mixes the Corwin-Schultz model and the twin's turnover. Also state that the calendar and FF3+UMD verdicts were carried over from a different book.

## Findings

### 1. [HIGH] Bridges board: rule turnover and twin turnover are in different units

`scripts/bridges_on_crsp_run.py` `part_board` takes the rule's `turnover_per_month` from `bridges_turnover_<run>.json`. That file is written by `scripts/crsp_blend_followups_run.py` `book_profile`, lines 69-73: `1 - |S_t ∩ S_{t-1}| / |S_t|`, averaged over **rebalances**. That is name replacement per rebalance, ignoring weights. The twin's turnover comes from the fair board's `run_book`: one-way traded weight per **month**, including drift re-weighting. The same rule, on the two instruments:

| hold_months | n rules | bridges `turnover_per_month` (median) | fair-board rule turnover (median) | ratio |
|---|---:|---:|---:|---:|
| 1 | 79 | 0.415 | 0.435 | 0.94 |
| 3 | 2 | 0.932 | 0.355 | 2.63 |
| 12 | 4 | 0.586 | 0.095 | 6.17 |

`qc761_ebit_ev_ebit_ic_large_annual` is charged 0.47 a month on the bridges board and has 0.07 on the fair board. Its twin is charged 0.31. On the bridges board the asymmetry therefore runs **against** the rule: fair t (1991-2016) is 0.79 on the bridges board against 2.90 (full) on the fair board, for the same rule under the "same" convention. The rows affected are `qc761`, `rd_intensity`, `qc241_value_composite_small_annual`, `org_capital`, `inst_breadth_up` and `inst_breadth_up_21_40`. Two of them, `qc241` and `org_capital`, flipped CANNOT_DISTINGUISH -> FAILED_VARIANT in the verdict diff, and part of each flip is this unit error. This is the 09-30 lesson again, "two engines that disagree are a warning". The C1 receipts contain both engines' turnover for the same rule, and nothing compares them.

### 2. [HIGH] Bridges board: a basket's turnover scales a different twin

`board_columns` (`scripts/bridges_on_crsp_run.py` ~272-288) applies `turnover_scaled_net(fl["twin21_net"], cs["twin21_net"], twin_tov)`. Here `twin_tov` is the fair board's measured turnover of the **infinite-draw cell basket** (`hyp_investable.twin_basket`, re-matched every month). `twin21` is a different object: 21 random partners drawn at the rule's rebalances by `matched_twins.twin_series`, and held constant between them. Its turnover is about 1.0 per rebalance per draw, which is roughly `1/hold_months` a month for a holding rule. The docstring says "each on its OWN turnover", and for the twin that is not true.

There is also a cost-model detail. In the bridges series the twin's flat-band cost is the **rule's** flat cost (`calendar_offsets.twin21`: twin net = twin gross - the rule's cost). Corwin-Schultz is then added on top, scaled by turnover (`load_merged(cs=True)` subtracts CS from every `fwd_ret`). The fair board instead charges `max(CS, flat)` once on each book's own traded weight. "Same cost model" holds within each board. It does not hold between the two boards that print the same column name.

### 3. [HIGH] The fair twin still mostly measures the turnover gap, and the builder's diagnosis is correct

Over all 301 rows of `hyp_lab/twin_board_FT_2026-10-06_1.jsonl`:

- corr(twin turnover - rule turnover, fair - pure selection in bps/month) = **0.91**.
- Rules with turnover < 0.2 (n = 28): the twin's median turnover is 0.40, and fair - selection is **+21 bps/month**. Rules at 0.2 or above: -5 bps.
- 16 rules reach fair t >= 2 with pure selection < 2. All are low-turnover quality/value/annual rules.
- The random controls go the other way, which shows the column is doing cost accounting rather than selection. `random_1/2/3/large` have turnover 0.89-0.99 against their twins' 0.48-0.58. Pure selection is t -0.17 to -0.71. **Fair t is -2.6 to -3.4.** A random rule "loses to its twin at t 3" purely on turnover.

The per-name spread is **not** the asymmetry. The traded-weight spread (cost / turnover) is a median **6 bps higher for the rule** than for its twin (71% of rules), so on spreads the rule is if anything charged more. The construction is the problem: `run_book` re-cuts `cell_table` every month, so the twin basket follows tercile migration (12-1 momentum terciles move every month), while the rule holds its names. The rule and the twin pay the same price per trade. The twin simply makes 3-5 times as many trades.

### 4. [HIGH] The library headline was loosened, and ALPHA_DETECTED now has two meanings

The old library headline read rule - twin21 at **flat** costs. There the twin pays the rule's cost, so it was a pure-selection read. `fair_headline_row` feeds `headline()` the **fair-twin net** column instead, so a cost differential can now earn ALPHA_DETECTED. From the receipt (`crsp_rebuild/library_fair_board_LIB_2026-09-29T0802Z__FT_2026-10-06_1__2026-10-06T162735Z.json`):

| rule | pure selection t (full) | fair t | old t | rule / twin turnover |
|---|---:|---:|---:|---|
| `qp0025_small_annual` | **0.65** | 2.27 | 0.02 | 0.12 / 0.33 |
| `roe` | **0.94** | 2.41 | 1.03 | 0.20 / 0.46 |
| `blog01_roe_adv_annual_large` | **0.98** | 2.34 | 0.77 | 0.07 / 0.37 |
| `quality_momentum_gate` | 1.45 | 2.07 | 1.38 | 0.25 / 0.43 |
| `mom_gp_lowvol` | 1.60 | 2.49 | 1.54 | 0.31 / 0.46 |
| `gross_margin` | 1.73 | 3.03 | 1.80 | 0.14 / 0.45 |
| `trend_quality` | 1.74 | 2.07 | 1.56 | 0.37 / 0.46 |

This is a defect in the headline rule that C1 should have fixed, not a declared read to be amended later. The builder's own note says "read a twin verdict only where pure selection agrees with it", but the code does not apply that rule. A label a reader acts on should not depend on reading a caveat. What these 7 rows show is that **a low-turnover book nets more than a high-turnover style replica**. That is a real and useful fact about implementation cost. It is not selection alpha.

Proposed labels: `ALPHA_DETECTED` only when pure selection t >= 2 **and** fair t >= 2 (with the existing holdout, calendar and FF3 conditions). Fair t >= 2 with selection < 2 becomes `NET_EDGE_FROM_TURNOVER`. On pure selection the board would read ALPHA_DETECTED 11, not 13, and all 11 have a **negative** validation market line (t -0.29 to -2.16; two of them, `gh02_five_price_factors_ivw` and `qc623_mom63_liquidity_weighted`, are also mis-weighted per finding 5).

On the orchestrator's requirement: **yes**, every one of the 140 library rows prints `t_pure_selection_full` beside the label (0 missing), and every row carries `by_hold_year` and `loo_worst` on the fair and market columns (0 missing). The printed `headline_rule` field still describes the old read ("rule - twin21"). The `reissue_note` corrects it, but the field itself is wrong.

### 5. [MEDIUM] Weighted rules were scored as their equal-weight parent

`scripts/hyp_twin_board.py` `carried_picks` keeps `h["symbols"]` and discards `h["weights"]`, and `scripts/hyp_investable.py` `run_book` sets `w = 1/len(sel)`. On the fair board, 9 non-EW rules (`mom_12_1_ivw`, `gp_at_ivw`, `net_raises_ivw`, `quality_composite_ivw`, `mom_flow_ivw`, `mom_12_1_liqw`, `qc623_mom63_liquidity_weighted`, `qc470_mom252_quarterly_riskparity`, `gh02_five_price_factors_ivw`) were scored without their weights. Five pairs produce rows **identical** to their EW parent. `mom_12_1`, `mom_12_1_ivw` and `mom_12_1_liqw` all show fair t -0.015 and validation market t -2.21. Under the old headline the three were +0.13, +0.74 and +1.78. Three of the 41 "changed" library headlines (`gh02_five_price_factors_ivw`, `mom_12_1_ivw`, `mom_12_1_liqw`) were therefore re-issued on the wrong book. `mom_12_1_q_jajo` also matches `mom_12_1_q` exactly. That may be a coincidence of start month, but it should be checked.

### 6. [MEDIUM] Separating the effects: partly possible, and the claim needs a footnote

The library re-issue changed the engine (monthly EW re-weighting with charged drift, and weights dropped), the twin (21 draws -> cell basket), the cost model (flat band -> max(CS, flat)) and the twin's turnover, all in one run. The receipt can split the 41 changes in two, because it prints the old t, pure selection and fair side by side. I re-applied `library_on_crsp.headline()` to the pure-selection column:

- **7 of 41** changes happen at old -> pure selection, which is the engine/twin construction step.
- **34 of 41** happen at pure selection -> fair, which is the cost step.

The cost step cannot be split further from the receipt. Corwin-Schultz versus flat band and the twin's turnover gap enter as a product (fair - selection ≈ twin turnover × twin spread - rule turnover × rule spread). With traded spreads of 75-110 bps, the CS floor multiplies the turnover-gap effect several-fold compared with the 6-35 bps flat band. "41 headlines changed because of the fair twin" is therefore not attributable as stated. It should read: 7 from the change of twin and engine, 34 from the cost step, where the cost model and the twin's churn cannot be separated.

### 7. [LOW] The guards are real but narrow

Tests: `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_fair_twin_cost.py backend/tests/test_matched_twins.py backend/tests/test_library_on_crsp.py backend/tests/test_bridges_and_conditionals.py -q` gives **54 passed** (28 + 6 + 12 + 8). The builder reported 77, so the count differs. Either the builder's run included other files or the files changed afterwards. The sticky-twin work, C1b, is being edited in the same files right now.

Against the pre-C1 code (commit `46d6efa4`), loaded through the test module's own helpers:

- `bridges_on_crsp_run.part_board` trips the full-CS-twin guard (2 hits) and the `else 1.0` turnover-default guard.
- `scripts/conditionals_on_crsp.py` and `backend/services/hyp_investable.py` trip the retyped-`trade_cost` guard.
- None of the three boards reads the convention constant.

So the guards would have failed on the old code. Their gaps:

- `_is_cs_twin` matches only the frame names `{cs, cs_, C_CS, full, full_cs}`, so a rename defeats it.
- The default guard catches `x if ... is not None else 1.0`, but not `or 1.0`, `.get(k, 1.0)` or `fillna(1.0)`.
- No test catches findings 1, 2 or 5. A unit-level test that asserts the rule's and the twin's turnover come from the same function on the same book would have caught 1 and 2.

### 8. [INFO] Forward reads do not depend on this convention

The forward graders do not use `TWIN_COST_CONVENTION`, and they do not need it:

- **TRIAL-LIB-FWD-TWIN-1** (early kill on 2026-10-26 at z_21 <= -2, pooled D_21 <= -9.57%) is read by `backend/services/lib_forward_trial.py` `pooled_z` over frozen book - frozen twin returns.
- **CRSP_BLEND_v0** is read by `scripts/shadow_grade.py` `grade_book` (NAV gap vs twin).
- Both draw returns from `backend/services/llm_portfolio.py`. There, each frozen book (parent **and** twin) pays its own half round trip at entry, at its own names' band cost (around lines 1100 and 1152), and nothing trades afterwards. That is symmetric by construction.
- CRSP_BLEND_v0's kill line sd comes from `scripts/crsp_blend_v0_kill_amendment.py` lines 49-50: flat-run `rule_net - twin21_net`, where the twin pays the rule's cost, which is pure selection. C1 does not move it.

Nothing downstream needs re-grading. The risk runs the other way: any **historical** "twin beat" now quoted next to those forward reads must be the pure-selection column, because that is what the forward statistic is.

## The one survivor, qc761

It is the same row the 09-30 note flagged as an undeclared near-miss (`docs/research_notes/2026-09-30/hypothesis_lab_2026-09-30.md` §2: validation net - market +0.46%/mo, t 2.34, "not registered"). Recomputed from `hyp_lab/fair_twin_series_FT_2026-10-06_1/qc761_ebit_ev_ebit_ic_large_annual.parquet` (328 invested months, 1997-07 -> 2024-10, by hold year):

| column | mean %/mo | LOO worst (year dropped) | years > 0 |
|---|---:|---:|---:|
| pure selection | +0.197 | +0.144 (1998) | 18/28 |
| fair twin | +0.385 | +0.328 (1998) | 20/28 |
| net - market | +0.217 | +0.159 (2009) | 19/28 |
| upper bound (old twin) | +0.889 | +0.823 (2001) | 25/28 |

By window, net - market: 1991-2008 +0.134 (LOO worst +0.021, dropping 1998). Validation 2009-2016 +0.455 (LOO worst +0.273, dropping 2009; 2009 alone is **+20.8%**). 2017-2024 **+0.096** (LOO worst -0.033).

- The fair - selection gap is a constant ~+0.19%/mo, which equals (0.31 - 0.07) × ~79 bps. Half of the "fair" edge is the twin's churn.
- It is a **2009 artefact in its validation window**: the large-cap EBIT/EV junk rebound. Without 2009 the validation market line is 40% smaller (+0.455 -> +0.273), and the latest eight years are flat. The selection t of 1.5 does not separate it from its style cell.
- **Forward shadow: nothing.** A free shadow would cost $0, but it has no decision attached. The rule is annual, so a forward read would need years. It was chosen after looking (it is the one survivor of 301). The 2017-2024 line is already the out-of-sample read the shadow would give, and it is +0.10%/mo. If anything, keep it as a named negative example in the library: "the survivor of 301 is a 2009 rebound".

## The sticky twin

The diagnosis is correct. `matched_twins.twin_series` redraws **every** partner at every rule rebalance. The fair board's basket goes further and re-cuts the terciles every **month** (`run_book` -> `cell_table(g)` per date), so its twin turnover is 0.31-0.71 against 0.07-0.40 for holding rules. A sticky twin is a **new construction**, not the registered one. The registered twin, frozen into LIB-FWD-TWIN-1 and CRSP_BLEND_v0, is 21 seeded draws re-matched at each rebalance on size band × vol tercile × 12-1 tercile. The sticky twin must carry its own dated declaration before its first read, and the registered forward statistics must stay on `twin_series`. Spec:

1. When the rule enters name s on date d, draw one partner per draw j from s's (band, vol, mom) cell at d, among eligible names not held by the rule and not already used as partners. Seed = sha(rule_id, j). Use the registered fallbacks (cell -> band_vol -> band -> any) and count them.
2. Hold the partner exactly as long as the rule holds s, at **s's weight** (ivw/liqw included), with the rule's drift and re-weight convention.
3. Redraw only when the rule exits s (the partner is sold), when the partner dies or stops returning (redraw at the next decision date), or when the partner collides with a new rule entry. Count each reason.
4. Charge both legs `trade_cost` from the same per-name spread lookup. Refuse the row if |twin turnover - rule turnover| exceeds a declared tolerance after excluding death-redraws.
5. Average 21 draws, name the construction `TWIN_STICKY_v1` in a dated declaration, and print it beside, never instead of, the registered twin21.

(C1b's in-progress `twin_series_sticky` / `STICKY_REASONS` / `sticky_turnover_check` follows this shape. It should also carry weights, per finding 5.)

## The investor's sentence for the scoreboard

> On CRSP 1991-2024, none of 301 library and bridge rules beats both its matched twin on pure selection (gross vs gross, t >= 2) and the market net of costs in the 2009-2016 validation window. The single rule that beats the market in validation (`qc761`) shows no selection skill (t 1.5), leans on 2009 and earns +0.10%/mo since 2017. **Historical alpha on CRSP is not demonstrated.**

## What I would have done instead

1. **Fix the control before re-issuing a single verdict.** Build the sticky twin first. It is about a day of code, and a few hours of one board run of the kind that was run anyway. Re-issuing 85 + 140 verdicts on a twin already known to churn three times faster than the rule produced a third set of labels (old, fair, and soon sticky) for readers to reconcile, and 7 ALPHA labels that will be withdrawn.
2. **One engine, one turnover function, one row per rule.** Drop the bridges board's flat-run/CS-run interpolation (`turnover_scaled_net` over two runs of the library engine) and read every board from the fair board's `run_book` series. One `trade_cost`, one turnover definition, one twin object. Then the bridges board is a declaration filter over the same rows, and the qc761 0.79 vs 2.90 disagreement cannot occur. Add a test asserting that the rule's and the twin's turnover in a row come from the same function on the same book.
3. **Headline on pure selection; print cost as a separate implementation line.** Selection is the research claim. "Net of a style replica's trading" is an implementation claim, and it belongs to `CAPITAL_CANDIDATE`. Keep them as two labels so that a cost asymmetry can never produce an alpha word.

## Score: 58 / 100

- +: shared `trade_cost`, refusal of a missing turnover, the upper bound kept and labelled, four columns plus by-year and LOO on every row, AST guards that fail on the old code, an honest caveat, and RESULT IMPROVEMENT: NONE stated.
- -: two undisclosed asymmetries on the bridges board (units, object), a headline rule loosened rather than tightened, weights dropped for 9 rules, and the effects mixed in one run without a footnote.
