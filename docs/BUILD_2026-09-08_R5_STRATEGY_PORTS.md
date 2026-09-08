# BUILD 2026-09-08 — R5: S3-S8, THE STRATEGY PORTS

**Lane:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 block **S**, rows S3-S8.
**Licence:** PRODUCT_EXPERIMENT. **LLM spend: $0.00, 0 calls.** No orders, no
deploys, no seals opened, no pushes, no git state changed, no `.env` touched.

## RESULTS SCOREBOARD

| | |
|---|---|
| **Result improvement** | **NONE from the ports themselves** — six detectors and one statistic, no book's returns changed. But one **new actionable finding** below is a real number about existing books. |
| Best historical net strategy vs the market | unchanged (`ensemble_ew\|k=100\|ew\|hold=200\|10bps`, β 1.195, +5.65%/yr t 2.42, era-concentrated) |
| Best forward paper strategy | unchanged |
| Independent selector count | still **1** — and S8 now says so as a NUMBER rather than as a coverage count (below) |
| **New actionable finding** | **all five non-momentum published predictors tested on our own panel have MMC t > 3.4 over 312 monthly eras** — i.e. their errors ARE different errors. `be_me`'s MMC (**+0.0172**) is *larger* than its own corr (+0.0083), because it is anti-correlated with momentum (ρ −0.363): neutralising against the ensemble makes value *better*, not worse. Every one of these is a candidate independent selector the arena does not have. |
| Cost-rate enforcement | **`breakeven_fee_bps` is now on every receipt**, per side, beside the declared rate. Validated against the event lane's PEAD measurement (1.2–14.6 bps a side vs the 10 / 25 grid), which also caught a factor-of-two units bug in my first version — §3b |
| External execution drag | not touched |
| LLM spend / cost per gradeable output | $0.00 / n.a. |

---

## 1. THE ROW-PER-ITEM TABLE

| # | item | status | known-answer test (the planted fault, and what must come back) | licence provenance |
|---|---|---|---|---|
| **S3a** | lookahead analysis (cut the frame before each signal, diff the columns) | **DONE** | `_build_with_lookahead` plants `tomorrow_ret = close.shift(-1)` and `z_vs_full_mean = (close − close.mean())/close.std()` beside three honest columns. The detector must return **exactly** `{"tomorrow_ret", "z_vs_full_mean"}` and mark `sma3`, `ret1`, `dollar_vol` CLEAN. `test_lookahead_detector_names_EXACTLY_the_two_planted_columns` | freqtrade GPL-3.0 — **reimplemented from a written spec** (§2 below, written before the code). No upstream line read into the file. |
| **S3b** | recursive analysis (warm-up drift) | **DONE** | `ewm(alpha=0.005)` has a ~200-bar memory and cannot be converged at 20 bars; `rolling(3)` is exact at 20. Detector must return `("ewm_slow",)` and only that. Second planted case: `expanding().mean()` — literally "a growing window vs a fixed one" — must be caught and `rolling(5)` must not. | same |
| **S4** | `do_predict` manifold flag (DI + one-class SVM + DBSCAN; each rejection −1; books gate on `== 1`) | **DONE** | train on a 300×3 Gaussian blob; score `(0,0,0)` → **1**; score `(50,50,50)` → **every** enabled detector objects and the flag is `1 − 3 = −2`. Monotone ladder 0 → 3 → 12 → 60 sd never increases trust. Gated score is **NULL**, not 0. | freqtrade GPL-3.0 — **reimplemented**; the three estimators are stock scikit-learn (BSD-3) that this module *calls*. |
| **S5** | `breakeven_fee_bps` on every result row + ADV cap with the shortfall carried forward | **DONE** | `ln(1.10)/(2·10·1)·10⁴ = 47.65509 bps a side`, asserted to 1e-6 by hand. **The PEAD validation case** (§3b): 1.2–14.6 bps a side against the 10 / 25 grid → DEAD, DEAD, SURVIVES, DEAD. Capacity: capital 1e6, ADV 1e6, cap 10% ⇒ a 0.35 target fills **0.10, 0.20, 0.30, 0.35** over four periods, unfilled **0.25, 0.15, 0.05, 0.00** — carried, never dropped, never filled. | Vibe-Trading **MIT** — **copied VERBATIM** with the LICENSE prepended; three tests byte-compare all three files against the clone. |
| **S6** | the exit ladder as its own tested model (time-decayed `minimal_roi`, ranked exit order, stop-vs-vol as an explicit input, meta-labelled sell) | **DONE** | **the ranking test**: on one bar where a stop and a signal both fire, the winner is `THESIS_INVALIDATED`; with the contract's `exit_priority` *reversed* and **nothing else changed**, the winner is `STOP`. That is what makes the order data. Stop-vs-vol: 3% stop / 3.06% sd ⇒ 0.98 sd ⇒ `min_hold_can_bind = False`. | freqtrade GPL-3.0 design — **reimplemented**; typed reasons are Aegis's own (`contract.DEFAULT_EXIT_PRIORITY`, mirroring the terminal repo's `alpha/contract.EXIT_REASONS`). Meta-labelling framing: Akepanidtaworn et al. 2023. |
| **S7** | protections as data, evaluated before entries; never empty; refuses rather than assumes | **DONE** | the 2026-08-28 incident reproduced: 12 names × 25% = **3.00× gross**, × 3% stop = **−9.00%** (−$9,000 on $100k); the "fix" that widened the stop to 8% gives **−24.00%** and locks. Five live profile bounds derived from gross×stop: 1.80 / 10.00 / 9.00 / 12.00 / 8.00 %. | freqtrade GPL-3.0 + OpenAlice AGPL-3.0 contract *shape* — **reimplemented from a written spec**. Nothing copied from either. |
| **S8** | per-era scoring, feature neutralisation, era boosting, **MMC** | **DONE** | MMC's two identities, both exact by construction: a book against **itself** has MMC **0.0** (and a monotone re-expression `3x+7` also has MMC 0.0, because ranks are gaussianised first); a book against an **uncorrelated** meta-model has MMC **== corr**. Partial overlap must land strictly between. | docs.numer.ai — public documentation of a method, **reimplemented**. No code copied. |

**Gate result:** `python -m scripts.run_one --reproduce` after every item →
`arena identity reproduced: True; growth development cells reproduced
BYTE-FOR-BYTE: True (2 cost cells); growth sealed era: REFUSED_BY_DESIGN`.
`git diff` on `S1_reproduction.json` is **empty** — the receipt is unchanged.

---

## 2. THE WRITTEN SPECS (written BEFORE the code; the GPL items are built from
these, not from upstream source)

### S3a — lookahead analysis

1. Baseline `full = compute(frame)`.
2. For each checkpoint `t`: `cut = compute(frame[:t])` — rows after `t` **deleted**,
   not masked (masking leaves the future in the object and a builder that reads
   `.values` still sees it).
3. For every shared column compare `full[:t]` against `cut[:t]`, NaN-aware, to
   `atol=1e-12 / rtol=1e-9`.
4. A column that differs is reading the future: report **by name**, with the
   first checkpoint at which it moved and the largest |delta|.
5. **The disambiguation upstream does not make:** a column all-NaN on the cut
   over the compared span has not leaked, it has not WARMED UP →
   `INSUFFICIENT_WARMUP`, a `CANNOT DETERMINE`, not a pass and not a fail. And
   *nothing was compared* is not agreement: a column all-NaN on **both** sides
   still counts as untested at that checkpoint.
6. Refusals: empty frame · no checkpoint in the index · builder returns nothing ·
   builder raises on a prefix. Each is a named refusal, never a clean bill.

### S3b — recursive analysis

For each warm-up `n` in `(20, 40, 80, 100, 150, 300, 999)`, compute on the last
`n` rows and read the final row. Reference = the **longest rung the frame can
actually supply**. Report relative deviation per column per rung; flag
`WARMUP_DRIFT` when the deviation at the *declared* warm-up exceeds 1%.
A rung longer than the frame is **refused by name, never clamped** — a clamped
rung agrees with the reference by construction and reads as convergence. A zero
reference reports the absolute deviation with `relative: null` rather than
dividing.

### S4 — `do_predict`

Pipeline `VarianceThreshold(0) → MinMaxScaler(−1,1) → three detectors`, the
scaler fitted on **train only**. (a) dissimilarity index: nearest-training-row
distance over the training set's mean pairwise distance, reject above
`di_threshold`. (b) one-class SVM, reject below the `nu` quantile of the
training decision function. (c) DBSCAN, reject beyond `eps` from every training
**core** sample, `eps` derived from the training median nearest-neighbour
distance. Each rejection subtracts 1 from a base of 1. `outlier_protection_percentage`
(30): a detector that would reject more than 30% of its **own** training set is
**disabled with a reason**, not applied to a decimated set. If **no** detector
fits, `score()` **raises** — returning 1 would tell every downstream book the
row was checked. `expired_flags()` returns `do_predict = 2` and NULL predictions.

### S6 — the exit ladder

`minimal_roi` = `{periods_held: min_profit}`, resolved by the largest key ≤ held;
an unmatured rung is `None` ("the ladder has not started"), **never 0.0** ("take
any profit"). Every reason is evaluated on every bar and a list is returned; the
winner is the first entry of the contract's `exit_priority`. `min_hold_periods`
suppresses the NORMAL exits (ROI, deadline, rebalance) and **never** the
emergency ones (stop, thesis invalidated, trailing) — a minimum hold that could
hold through a stop is a calendar overriding a risk limit.
Fill conventions, written down so they can be attacked: one price per bar, no
intrabar path, so a bar touching both the stop and an ROI rung resolves by the
**ranking**; a stop fills AT its level (optimistic, and named so); an ROI rung
fills at the bar's price, so a 6% rung can exit at 9%.

### S7 — protections

`Protection.evaluate(state) → ProtectionReturn(locked, reason, scope, measured,
determinable)`. Locks **entries only**. Four rules in code, not prose:
(1) the guard list is never empty — an empty `ProtectionStack` raises unless
`deliberately_unprotected="<why>"` is given in words; (2) an unmeasurable input
**LOCKS** with `CANNOT DETERMINE` — never "assume flat"; (3) the gross line and
the stop line are printed together; (4) no fleet **profile** is levered
(`gross_cap ≤ 1.0`, asserted for all five).

---

## 3. THE MMC NUMBERS — the required "MMC for at least one existing book"

Receipt: `backend/data/optimus/strategy_ports/S8_mmc.json`
Command: `python -m scripts.strategy_ports --mmc`

**Panel:** `backend/data/optimus/aegis_panel/aegis_panel_v2.parquet`, `excntry ==
USA`, `eom` 1999-01…2024-12, `dolvol >= TRADABLE_DOLLAR_VOL` (\$3m/day, the
execution floor applied *before* believing anything) → **1,456,439 name-months
over 312 monthly eras**. Target `ret_exc_lead1m`.

**Meta-model = `ret_12_1`**, i.e. **the composite arena book as it actually is.**
`COMPOSITE_WEIGHTS` names six signals; coverage is `{"1": 206, "6": 1}`, so 99.5%
of names carry 12-1 momentum only. The ensemble a new book would join *is*
momentum, and that is what it is neutralised against.

The composite's own score, for scale: **mean per-era corr +0.03126, t 4.80 on
312 eras.**

| candidate | sign | corr | **MMC** | t(MMC) on 312 eras | ρ with the ensemble | verdict |
|---|---|---|---|---|---|---|
| `ret_12_1` (the ensemble itself) | + | +0.03126 | **+0.00000** | — | +1.000 | **RE-EXPRESSION** — the known answer, and it comes back exact |
| `ivol_capm_252d` (low vol) | − | +0.03130 | **+0.02379** | 3.49 | +0.227 | DIFFERENT ERRORS |
| `qmj` (quality) | + | +0.02574 | **+0.01899** | 4.27 | +0.253 | DIFFERENT ERRORS |
| `ope_be` (profitability) | + | +0.02757 | **+0.01877** | 3.62 | +0.226 | DIFFERENT ERRORS |
| `be_me` (value) | + | +0.00825 | **+0.01721** | 4.74 | **−0.363** | DIFFERENT ERRORS |
| `at_gr1` (low asset growth) | − | +0.00913 | **+0.01330** | 4.28 | −0.129 | DIFFERENT ERRORS |

Two things in that table are worth stating plainly.

1. **`ret_12_1` against itself is exactly 0.** That is the known-answer check
   running on the real panel, not on a fixture. The number is readable *because*
   the definition forces it.
2. **`be_me` and `at_gr1` have MMC LARGER than their own corr.** That is not a
   bug: they are negatively correlated with momentum (ρ −0.363 and −0.129), so
   removing the ensemble's exposure *adds* signal. `corr − MMC` is negative for
   them — the ensemble was not helping, it was dragging. This is the
   value-as-a-momentum-hedge result, arrived at from our own panel, and it is
   the strongest argument in this document for a **separate value book** rather
   than a value weight inside `arena_composite`.

**What is NOT claimed.** Correlation space, gross, one panel, one meta-model.
Not a portfolio result, not net of costs, not evidence that a positive-MMC book
makes money. A book still has to beat its benchmark after costs, at a beta, on
its own receipt. `mmc()` prints that sentence in its own output.

---

## 3b. S5's UNITS BUG, AND THE PEAD CASE THAT CAUGHT IT

`breakeven_fee_bps = ln(1+gross) / (2 · trades · size) · 10⁴`. **The `2` in the
denominator is the two legs**, so the rate the identity solves for is the one
charged on EACH leg — it is **bps PER SIDE**, the same units as
`learner.evaluate.COST_BPS_PER_SIDE` and as the 10 / 25 bps grid every Aegis
receipt is computed on.

This module was first written comparing that number against
`CostModel.round_trip_bps`, which is twice the per-side rate. That is a factor
of two, always in the book's favour. It was corrected when the event-family lane
reported **PEAD's breakeven at 1.2–14.6 bps a side against the 10 / 25 bps
grid** — the effect is inside the spread. Run through the corrected code:

| PEAD cell | cost grid | verdict |
|---|---|---|
| 1.2 bps a side | 10 bps a side | **DEAD AT ITS OWN COST RATE** |
| 1.2 bps a side | 25 bps a side | **DEAD** |
| 14.6 bps a side | 10 bps a side | SURVIVES |
| 14.6 bps a side | 25 bps a side | **DEAD** |

Against a *round trip* the 14.6 cell would have read as a survivor at 25 bps
too, i.e. the bug would have promoted a dead cell. `test_THE_PEAD_VALIDATION_CASE`
is parametrised over exactly those four cells, solving the identity backwards
for the gross return that produces each breakeven, and
`test_THE_UNITS_ARE_PER_SIDE_and_the_row_says_so` pins the units on the row.
The round trip is still **printed** beside the per-side number — it is just not
what the comparison uses.

This is the second time in this lane that a live number from another lane broke
a port that its own fixtures were happy with (the first was `gamma="scale"`,
§5). Both are arguments for the same thing: a detector is not a detector until
it has been pointed at a real measurement.

---

## 4. WHAT WAS WIRED, AND WHY (the reachability question)

The coordinator flagged `test_signal_reachability::test_every_orphan_is_classified`
red on `backend.strategy.leak`. It was **wired, not classified**: all six modules
are now called from `run_one` itself, so **every receipt carries all six blocks**
— either the number, or a NAMED `CANNOT DETERMINE` saying which input was
missing.

| receipt key | filled when | otherwise |
|---|---|---|
| `execution` | always (breakeven from terminal wealth + turnover; ADV path when `adv_value` + `target_weights` given) | `capacity` says *"unmeasured — that is not the same as uncapped"* |
| `exit_ladder` | always — the stop is compared against the **book's own** period-return sd when the caller supplies none | `CANNOT DETERMINE` when neither exists |
| `protections` | always — the default stack is never empty; every guard that needs a live book state and gets none **LOCKS** | `state_note` names it |
| `leak_analysis` | when `feature_builder` + `raw_frame` given | *"a book whose features were never differenced is not a book shown to be leak-free"* |
| `manifold` | when `manifold_train` or `manifold_gate` given | *"every score on this receipt is ungated"* |
| `marginal_contribution` | when `mmc_panel` + the four column names given | *"a healthy IC and a zero MMC is a re-expression, not a mechanism"* |

A block that vanished when its input did would let a reader mistake *"not
measured"* for *"not a problem"*, which is the failure every one of these ports
exists to stop. `backend.strategy.*` (17 modules) is now `tooling_only` in the
reachability audit via `scripts/run_one.py` **and** has a real caller in
`run.py`. `test_strategy_ports_on_receipt.py` (15 tests) pins the wiring,
including that **`beta` is still literally the first key** after the ports.

---

## 5. THREE MEASURED DEVIATIONS FROM THE SOURCE DESIGNS

Recorded so nobody re-discovers them, and because in each case the upstream
choice **fails the known-answer test**.

1. **The one-class SVM is RBF, not `SGDOneClassSVM`.** freqtrade uses the linear
   SGD version. A linear one-class SVM cannot bound a blob: its decision
   function is `w·x − ρ`, so a point arbitrarily far out along `+w` scores
   arbitrarily *high* and is called an inlier. Fitted on the 3-d Gaussian blob it
   **accepted (50, 50, 50)** — precisely the row the flag exists to refuse.
2. **The SVM threshold is the `nu` quantile of the training decision function,
   not `predict() == -1`.** At `nu = 0.01`, `predict()` rejected **6.7%** of its
   own training set and placed the blob's **centre 7e-4 below its boundary** —
   the most inlying point available was called an outlier. Thresholding on the
   training quantile makes the self-rejection rate exactly `nu`, which is what
   `nu` is supposed to mean and what makes the 30% outlier-protection guard
   comparable across the three detectors.
3. **The RBF bandwidth is the median heuristic, not `gamma="scale"`.**
   `"scale"` is `1/(n_features · var(X))` and is calibrated for *standardised*
   data; on the MinMax(−1,1) data this pipeline produces it came out ≈ 3.0, far
   too narrow, and the decision function **anti-correlated with distance from the
   centre**: `corr(df, −radius) = −0.16`, centre at the **0th** percentile. At
   `gamma = 1/(2·median pairwise distance²)` the same fit gives
   `corr(df, −radius) = +0.94` and puts the centre at the **96th** percentile.

A fourth, smaller one: `verdict.pbo`'s default `n_splits` stays **8** (S2's
choice), and this lane changed nothing in the vendored statistics library.

---

## 6. LICENCE PROVENANCE, FILE BY FILE

| file | lines | origin | licence handling |
|---|---|---|---|
| `backend/strategy/leak.py` | 415 | freqtrade **design** | GPL-3.0 → **reimplemented from §2's spec**. Header states this. Nothing copied. |
| `backend/strategy/manifold.py` | 408 | freqtrade **design** + scikit-learn estimators | GPL-3.0 → **reimplemented**; sklearn is BSD-3 and is *called*, not vendored. |
| `backend/strategy/ladder.py` | 369 | freqtrade **design** + Akepanidtaworn et al. 2023 | GPL-3.0 → **reimplemented**. Typed reasons are Aegis's own. |
| `backend/strategy/protections.py` | 435 | freqtrade + OpenAlice **contract shape** | GPL-3.0 / AGPL-3.0 → **reimplemented**. Live bounds mirrored from the terminal repo *with the source path quoted*, and `worst_case_pct` is **derived** from gross×stop, never typed. |
| `backend/strategy/numerai.py` | 350 | docs.numer.ai | public method description → **reimplemented**; the normalisation is Aegis's own and the deviation from numer.ai's `0.29²` constant is documented in the module head. |
| `backend/strategy/vendor/impact.py` | 317 (36 header + **281 verbatim**) | Vibe-Trading `agent/src/quantlib/impact.py` | **MIT — copied verbatim**, LICENSE prepended, byte-compared to the clone by test. |
| `backend/strategy/vendor/factor_costs.py` | 452 (36 + **416 verbatim**) | Vibe-Trading `agent/backtest/factor_costs.py` | same |
| `backend/strategy/vendor/breakeven.py` | 72 (38 + **31 verbatim**) | Vibe-Trading `agent/src/strategy_discovery/models.py::breakeven_fee_bps` | **MIT — one function copied verbatim** out of a 453-line module; only `import math` added (the original inherited it from the module head), and the header says so. |
| `backend/strategy/vendor/__init__.py` | 82 | Aegis | the import shim, below |
| `backend/strategy/execution.py` | 247 | Aegis | wraps the vendored MIT code; no upstream body edited |
| `scripts/strategy_ports.py` | 173 | Aegis | `--mmc / --bounds / --self-test` |

**The import shim, stated plainly.** `factor_costs.py` opens with
`from src.quantlib.impact import …`, upstream's own layout. Rewriting that one
line would make the file no longer byte-identical, and *"byte-identical except
for the bits we changed"* is not a property worth having — so
`backend/strategy/vendor/__init__.py` registers the vendored module under the
name it expects. The shim **refuses** if some other `src.quantlib.impact` is
already imported, rather than resolving the vendored import against a stranger's
module.

---

## 7. TEST COUNTS

Command: `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300`

| | baseline (my own run) | final (measured after every port) |
|---|---|---|
| passed | 7409 | **7811** |
| failed | 1 | **10** |
| skipped | 20 | 20 |
| deselected | 124 | 124 |
| wall | 778 s | 617 s |

**Baseline note.** My baseline run began before `leak.py` existed, and its
single failure was `test_signal_reachability` catching *my own* half-created
module mid-run. The coordinator's clean number for the same tree was **7410
passed / 0 failed**, and 7409 + that 1 = 7410, so the true baseline is 7410 / 0.
The tree gained several other lanes' work between the two runs, which is most
of the +402.

**New tests: 153**, all passing:

| file | tests |
|---|---|
| `test_strategy_leak.py` | 17 |
| `test_strategy_manifold.py` | 14 |
| `test_strategy_execution.py` | 27 |
| `test_strategy_ladder.py` | 23 |
| `test_strategy_protections.py` | 35 |
| `test_strategy_numerai.py` | 22 |
| `test_strategy_ports_on_receipt.py` | 15 |

The whole S block (S1–S8: mine plus the S1/S2 lane's 66) runs green together —
**219 passed in 19.45 s**.

**NONE OF THE 10 FAILURES IS MINE, and none is in `backend/strategy/`.** All ten
are in two files created by other lanes this session, both still untracked:

| failure | count | lane |
|---|---|---|
| `test_r7_news_representation.py` | 9 | R7, news representation |
| `test_u_archetypes_receipt.py::test_the_chosen_k_in_the_doc_is_the_receipts` | 1 | U, archetypes |

The two failures I *did* pass through mid-run — `test_signal_reachability::test_every_orphan_is_classified`
and `test_guard_missing_input_contract::test_every_guard_is_enrolled`, both
naming another lane's `backend/services/human_thesis.py` — were fixed by their
owner and now pass:

```
backend/tests/test_signal_reachability.py backend/tests/test_guard_missing_input_contract.py
81 passed in 12.60s
```

`signal_reachability.assert_no_unclassified_orphans()` returns clean, and **no
`backend.strategy.*` module appears as an orphan**: all 17 are `tooling_only`
via `scripts/run_one.py`, and all six new ones additionally have a real caller
inside `run.py` (§4).

---

## 8. WHAT DID NOT WORK / WHAT IS NOT DONE

1. **`gamma="scale"` and `SGDOneClassSVM` both failed the planted-fault test**
   (§5). Two of the three S4 detectors had to be re-derived before the known
   answer came back. Anyone copying freqtrade's FreqAI pipeline verbatim into a
   MinMax-scaled feature space inherits an in-manifold check that is worse than
   none, because it reads as having been performed.
2. **The MMC numbers are correlation-space and gross.** No portfolio was built
   from `be_me` or `qmj` in this lane, and none should be quoted as a return.
   The obvious next step is one `PRODUCT_EXPERIMENT` book per positive-MMC
   candidate through `run_one` — a separate book, never a weight in
   `arena_composite`, which is exactly what the MMC number is arguing for.
3. **The exit ladder is not yet fed by a real book.** `simulate()` and the
   ranking are tested on constructed paths; `meta_label_exits` is tested on
   hand-built records. Neither has been run over the fleet's actual exit
   history, which lives in the *terminal* repo and is out of this lane. Until it
   is, `meta_labelled_exits` is `CANNOT DETERMINE` on every receipt — printed,
   not hidden.
4. **The ADV cap is not wired into `portfolio_farm`.** `run_one` will use it
   when handed `adv_value` + `target_weights`, but no existing farm preset
   supplies them, so every current receipt says the capacity is *unmeasured*.
   Wiring it means editing `scripts/portfolio_farm*`, which is another lane's
   file.
5. **`GrossExposureCap` initially refused the growth champion**, which declares
   `sizing.gross_cap = 2.0`. That was the guard being right about the wrong
   scope: no *fleet profile* is levered, but a research book graded on terminal
   wealth at a drawdown budget is compared to **levered SPY**, so leverage is
   its claim. The cap now accepts a levered value only with a
   `leverage_reason` in words, which `run_one` fills from the contract and which
   lands on the receipt. A silent numeric override would have been the wrong fix.
6. **`per_era_scores` and `era_boost_weights` are not called by the learner.**
   They are exported, tested and reachable, but `learner.evaluate.grade_by_era`
   remains what the sealed receipts were written with and was **not** modified —
   changing it would invalidate every sealed receipt that quotes it. Era
   boosting therefore ships as a weight generator, not as a fitted model.
7. **`ruff` is still not installed here** (`No module named ruff`), so the lint
   ratchet was checked by hand: `py_compile` clean on every new file, no line
   over 100 chars outside the vendored bodies, no unused imports.
8. **S5 shipped with the wrong units and a real number caught it** (§3b). The
   breakeven fee is per side; it was being compared against a round trip, which
   is a factor of two in every book's favour. The fixtures could not catch it —
   they asserted the identity, which was right, and the comparison, which was
   wrong in a way no synthetic case distinguishes. The PEAD measurement did.
   `breakeven_row` now takes `declared_cost_bps_per_side` and prints the round
   trip beside it rather than comparing against it.
9. **`backend/data/optimus/strategy_interface/S1_reproduction.json` was
   regenerated** by re-running the acceptance gate after every port. Its diff
   is **six lines, all of them clocks**: `wall_seconds`, two `generated_utc`,
   two `opened_utc` and `git_commit`. Every substantive field — the two
   byte-for-byte growth cost cells, the four arena identity hashes, the
   selection, the weights — is unchanged. No sealed artefact was opened; the
   growth book's sealed era stayed `REFUSED_BY_DESIGN` throughout.

---

## 9. HOW A NEW MECHANISM ARRIVES NOW (updated from S1 section 7)

```python
receipt = run_one(
    strategy, window=Window("2006-01", "2015-12"),
    data={
        "book": book, "benchmark": bench, "rf": rf,
        # S3 -- prove the features do not read the future
        "feature_builder": build_features, "raw_frame": raw, "declared_warmup": 250,
        # S4 -- refuse to score a name outside the training manifold
        "manifold_train": X_train, "manifold_score_rows": X_infer,
        # S5 -- what the tape could actually supply
        "adv_value": adv, "target_weights": targets, "capital": 1e6,
        # S6 -- the stop against the holding-period noise, and the sell's own score
        "per_period_sd": 0.021, "exit_records": exits,
        # S7 -- the guards, before entries
        "risk_profile": "aggressive", "book_state": state,
        # S8 -- are its errors DIFFERENT errors?
        "mmc_panel": panel, "mmc_pred_col": "my_score",
        "mmc_meta_col": "ret_12_1", "mmc_target_col": "ret_exc_lead1m",
        "mmc_era_col": "era",
    })
```

Beta first; costs never zero; six new blocks that are either a number or a
named refusal; a breakeven fee **per side**, in the same units as the 10 / 25
bps grid; and one statistic -- MMC -- whose expected null is zero and whose
being non-zero is the whole reason to build the book.

**And the rule the MMC table sharpens:** never fold a surviving family into
`arena_composite` as a weight. `be_me` at rho -0.363 to momentum is the clearest
case yet -- as a weight inside the composite it would be averaged against the
thing it hedges; as its own `Strategy` with its own `strategy_id` it keeps the
independence the number measured.
