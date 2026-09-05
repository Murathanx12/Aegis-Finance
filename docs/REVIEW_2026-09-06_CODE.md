# CODE REVIEW — weekend lab, 2026-09-06

**There is a leak, and it is live in the weekend's headline result:** `W7_matched_loser` builds
its matched control group by removing names whose **12-month forward outcome** was in either
tail, so "being a control" is a statement about the future, and every winner-minus-control
difference for a dispersion-correlated feature is biased by construction. Eight archetype
candidates and the `NOVEL` verdict on six committed W7 receipts rest on it.

**Scope.** `scripts/weekend_lab.py`, `scripts/weekend_lab_jobs.py`, `learner/long_panel.py`,
`learner/features_price.py`, `learner/evidence_memory.py`, and today's diffs to
`learner/inference.py` (`power_note`), `learner/evaluate.py` (`book(hold_k=)`),
`learner/models.py` (quantile head).

**State reviewed.** Branch `lab/weekend-2026-09-06` at `27d7561`, **working tree dirty**
(`scripts/weekend_lab.py`, `scripts/weekend_lab_jobs.py` modified; `W12_short_side` added
mid-review). Two commits landed while the review ran. Line numbers are the working tree as read.

**Shape of the damage.** Apart from C1, the panel and feature code are point-in-time clean —
every `merge_asof` is backward, every cross-sectional rank is `groupby("month")`,
`walk_forward_splits` embargoes on the target's maturity date, and W10's carry-forward provably
never reads a later month. The rest of the damage is in the **verdict layer**: a leak detector
that cannot detect its own bug, five gates that compare against constants they themselves wrote,
and a verdict vocabulary whose two words are algebraically one word.

---

# CRITICAL

## C1. `W7_matched_loser` — control membership is conditioned on the outcome
`scripts/weekend_lab_jobs.py:1102`

```python
pool = g.drop(index=list(win.index) + list(los.index))
```

`win` and `los` are defined by `_resid`, the **12-month-forward** residual excess return.
Excluding the winners is necessary. Excluding the *losers* means a control is, by definition, a
name whose 12-month outcome was **neither** top-50 nor bottom-50 — selection on the dependent
variable.

**Failure scenario.** Any formation feature that predicts outcome *dispersion* rather than
outcome *direction* — volatility, thinness, analyst disagreement — will differ between winners
and this pool by construction, because winners are drawn from a tail and controls are drawn from
names guaranteed not to be in either tail. The top published archetype candidate is
`log_dollar_vol_20d` (Holm p 0.000178, `mean_diff` −0.1308) — a liquidity/thinness measure, i.e.
exactly a dispersion proxy. Its "winners are thinner than their matched controls" reading is
partly a restatement of "tail outcomes happen to thin names, and controls were chosen to have no
tail outcome".

The design's own guard is the loser-side sign check (`:1208-1215`) — but `cl` is drawn from the
**same** outcome-excluded pool, so the guard inherits the bias it is meant to detect, and it only
fires at `|t_loser| >= 2.0`.

**Fix.** Draw controls from all non-winner names (`pool = g.drop(index=list(win.index))`). Keep
winner-vs-loser as a separate, explicitly labelled contrast rather than folding the loser
exclusion into the control definition. Re-run the eight archetype candidates and expect
`log_dollar_vol_20d` and `log_dollar_vol_20d__xs` to move most.

## C2. The early-era share-basis gate returns PASS on a panel carrying the exact bug it exists to catch
`learner/long_panel.py:183-264`

This is the only check between the never-before-tested 1999-2004 window and the share-basis
defect that voided the band constants on 2026-09-04. Reproduced against the shipped panel with
the defect injected (numerator = `meanptg_adj` over raw close, computable as
`ratio_adj_check / cfacpr`):

| panel | split arm | control arm | gap | verdict (bar 0.10) |
|---|---|---|---|---|
| TRUE (unadjusted numerator) | 0.9807 | 0.9780 | −0.0027 | PASS |
| **BUGGED (adjusted numerator)** | 0.8529 | 0.8657 | **+0.0129** | **PASS** |

Two independent causes, both measured:

1. **The treatment group is the wrong group — the bug is common-mode.** `_split` (`:219`) is
   `split_prior_year`, which `dataset.py:531-532` defines *backward*
   (`cfacpr(t) != cfacpr(t−252)`). The bug scales by `cfacpr(t)`, the cumulative factor to the
   **end of sample**, driven by every split *after* t. Of the 68,250 early-window rows the bug
   actually distorts, **57,373 (84.1%) land in the CONTROL arm.** Both arms degrade together
   (0.9807→0.8529 and 0.9780→0.8657) and a gate that measures only a *difference* sees nothing.
2. **Even correctly grouped, the band is too wide for the modal split.** Median `cfacpr` on
   flagged rows is 1.0, p75 is 2.0. Dividing a ratio distribution centred at 1.2149 by 2 gives
   ~0.61 — comfortably inside the `(0.3, 4.0)` band; the in-band rate actually *rises* to 0.9906.
   Sweep: the gate first fires at k≈3 and k≈4. It is blind at 1.5× and 2×, which is most splits.

The docstring's `what_would_fail` claim (`:255-258`) — "would push the post-change rows out of the
band by roughly the split factor" — is false for the modal split factor. `W1`'s
`share_basis_gate_early_era: PASS` is printed on every pass and is currently worth nothing.

**Fix.** Define treatment as `cfacpr(t) != 1` (the population the restatement actually touches).
Replace the in-band-rate-vs-wide-band test with a **paired** per-row comparison of `ratio` against
`ratio_adj_check * cfacpr` — a paired test on the same rows has no common-mode blind spot. **The
gate has no test of its own**; add one that injects the bug and asserts FAIL.

## C3. `W7_matched_loser` matches on two different rank scales, biasing the match on the dimension being neutralised
`scripts/weekend_lab_jobs.py:1106-1107`

```python
pr = {c: pool[c].rank(pct=True) for c in on}   # ranks within POOL (g minus the 100 extremes)
gr = {c: g[c].rank(pct=True)    for c in on}   # ranks within the FULL month
...
d2 = sum((pr[c].loc[cand.index] - gr[c].at[i]) ** 2 for c in on)
```

The winner's coordinate is a percentile of the full cross-section; the candidates' coordinates are
percentiles of a distribution with 100 names removed. These are not the same axis, so the squared
distance is between incommensurable numbers.

**Failure scenario.** ~1000 names in a month, 100 removed. Residual winners and losers skew
small-cap, so the surviving small names' percentile ranks shift upward by up to ~10 points. A
winner at `gr = 0.05` on `log_market_cap` is matched to the pool name at `pr ≈ 0.05` — which after
the shift is a materially **smaller** name. Every winner-minus-control difference for a
size-correlated feature inherits that bias, and the top archetype candidate
(`log_dollar_vol_20d`) is size-correlated.

**Fix.** Rank once on the full month and index both sides into the same series:
`gr = {c: g[c].rank(pct=True)}`, then `d2 = sum((gr[c].loc[cand.index] - gr[c].at[i])**2 ...)`.

---

# REQUIRED

## R1. `W7` stamps the wrong months onto any feature with incomplete coverage — live in the committed receipts
`scripts/weekend_lab_jobs.py:1167`

```python
s = pd.Series(vals, index=pd.Index(months_used[:len(vals)], name="month"))
```

`months_used` gains one entry per formation month that produced a matched set (`:1147`), but
`diffs_w[c].append(...)` (`:1130-1133`) is **conditional** on both sides having ≥10 non-null. So
for any feature with non-universal coverage, `len(vals) < len(months_used)`, and values from a
*scattered subset* of months are labelled with the **first** `len(vals)` months. Reproduced:

```
values belong to ['1999-03','1999-04','1999-05'] but are labelled ['1999-01','1999-02','1999-03']
```

**Live in `W7_matched_loser_run09_v0.json`**: `formation_months = 297`, but `ratio`, `log_ratio`,
`ratio__xs` carry `months = 292` (winner side); `ratio`, `log_ratio`, `ratio__xs`, `upside` carry
289; `target_rev_1m__xs` carries 296. Their era tables read `105 / 96 / 91` — the missing
observations were silently absorbed by truncating the **last** era, and every observation is
shifted earlier by up to five months. That mislabelled series feeds `era_sign_table` (`:1183`),
whose `same_sign_in_2_of_3` is a **hard gate on the archetype bar** (`:1210`), and
`power_note` (`:1184`). `ratio` (IBES upside) is thinnest in the early era — the misdating is
systematically toward the era boundary that matters.

Blast radius today is bounded (all 8 published candidates have `months == 297`), but the shape is
unbounded: a feature missing its first 60 formation months would have 237 values labelled
1999-2018 and an era table that is fiction.

**Fix.** Append `(month, value)` pairs, or carry a parallel `months_w[c]` appended in the same
branch. Never index a conditionally-appended list against an unconditionally-appended one.

## R2. `W8._era_consistent` is always True — the `REGIME_SPECIFIC` verdict is unreachable
`scripts/weekend_lab_jobs.py:1799`

```python
era_consistent = bool(len(era_spreads) >= 2 and min(era_spreads) > 0)
```

`era_spreads` are `states.spread_statistic` values, and that is `per.max() - per.min()`
(`learner/states.py:757`) — a **range, non-negative by construction**. So `min(...) > 0` is true
for any real input. Whenever `pm <= 0.05` the verdict is `NOVEL`; the
`elif pm <= 0.05: "REGIME_SPECIFIC"` branch at `:1804` can never execute. Verified across all 7
committed W8 receipts — every era spread is strictly positive (0.0117 … 0.0849).

**Live near-miss.** `W8_states_three_nulls_run09_v2.json` (k=6) has era spreads
`0.0221 / 0.0849 / 0.0245` — the middle era is ~4× the others, textbook regime-specific — and
`era_consistent` calls that consistent. It escaped publication as `NOVEL` only because
`p = 0.062 > 0.05`.

**Fix.** A range has no sign, so non-degeneracy is not consistency. Require `min >= 0.5 * max`, or
better — and what the docstring actually describes — that the **ordering of the states** persists
across eras (rank-correlate the per-state mean vectors era to era).

## R3. `power_note`'s `powered` flag is algebraically `t_observed >= t_target`
`learner/inference.py:594-598`, consumed at `scripts/weekend_lab_jobs.py:148-150`

`needed_years <= years_obs` ⟺ `(t_target/SR)² <= T` ⟺ `t_target <= SR·√T = t_observed`. Verified:

```
t_observed  powered  years_needed  years_observed
   -0.486    False       None           25.7
    0.748    False      183.3           25.7
    1.306    False       60.2           25.7
    1.542    False       43.2           25.7
    5.446    True         3.5           25.7
```

So `verdict_from` returns **`CANNOT DETERMINE (underpowered)` for every arm with `0 < t < 2`**,
and `NOISE` only for arms with a non-positive mean or `t >= 2` that fail DSR/SPA/PBO. A truly null
arm with a hair of positive sample mean is filed as "we could not tell" — reporting absence of
evidence as inability to determine, the inverse of the error the docstring says it prevents.
**19 committed receipts carry this label.** No number is wrong; the word on 19 receipts is.

The useful content (`years_needed_for_t2` at the observed Sharpe) should stay. The flag is not a
power calculation — power needs a **declared** effect size (an MDE), not the observed one.

**Fix.** Take `sr_of_interest` (or an annualised MDE) as an argument and compute `powered` against
that. Keep the observed-SR `years_needed` as a separate, differently named field. Then
`CANNOT DETERMINE` means "25 years cannot detect the SR we said we cared about" and `NOISE` means
"it could have, and did not".

## R4. `power_note` has no overlap correction, and W7 feeds it a 12-month-overlapping series
`learner/inference.py:506` (no `n_effective` parameter); consumed at `weekend_lab_jobs.py:1184, 1191, 1463, 1483`

W7's rows carry `n_effective: 25` and an `overlap_note` saying "the naive t divides by
sqrt(months) when the independent draws number about months/12". The `power` block on the **same
row** says `n_periods: 297`, `years_observed: 24.75`, and its `t_observed` **is** the naive t the
row itself corrects away. From `W7_matched_loser_run00_v0.json`:

| feature | t_naive | t_block_non_overlapping | published `years_needed_for_t2` | honest (n_eff = 25) |
|---|---|---|---|---|
| `vol_60d__xs` | 39.4 | 19.0 | **0.1** | ~0.28 |
| `net_rev_1m` | 3.648 | 2.976 | **7.4** | ~11.3 |

No verdict flips today — I checked every W7 row and found **0** where `|t_naive| >= 2` and
`|t_block| < 2` — so this is wrong numbers rather than a wrong conclusion. But the numbers are
published, and `powered` on those rows is decided by a t the receipt disowns two fields earlier.

**Fix.** Give `power_note` an `n_effective` (or `overlap_periods`) argument; when supplied, compute
SR per independent draw and scale `years_observed`. Callers with an overlapping target must pass
it. Refuse rather than default when the caller has already computed `n_effective`.

## R5. `W7b.where_the_effect_lives` is backwards for 2 of the 5 published legs — it tells the reader to go long a negative decile
`scripts/weekend_lab_jobs.py:1629`

The test compares **magnitudes only**: it ignores sign, ignores whether the top decile is actually
the best decile, and ignores the correctly computed `top_decile_turns_over` two lines above.
Live in `W7b_archetype_book_run09_v0.json`:

| leg | d1 | d10 | top−bottom | `turns_over` | published reading |
|---|---|---|---|---|---|
| `_leg_thin_for_size` | −0.019 | **−0.106** | **−0.087** | True | "the TOP decile — a long book is the right instrument" |
| `_leg_rated_low` | +0.022 | **−0.025** | **−0.047** | True | "the TOP decile — a long book is the right instrument" |

For both, the top decile is negative *and worse than the bottom*. This is the exact W5b error the
field was added to prevent — and `W5b_options_book:797` gets it right by using `turn`, so W7b is a
regression against its own sibling.

**Fix.** Drive the reading off sign and ordering: `tbl[-1] > tbl[0] and not turn` → "top decile /
long book"; `tbl[0] < 0 and abs(tbl[0]) > abs(tbl[-1])` → "bottom decile / exclusion"; otherwise
"no clean side".

## R6. `evidence_memory._record_features` fabricates the DSR and the SPA p, so the DSR/SPA/PBO bars are dead code on every promoted cell
`learner/evidence_memory.py:397-398`; gate at `:146-152`

`dsr = 0.99 if cleared else 0.10` and `spa_p = 0.01 if cleared else 0.90`, where `cleared` is just
`abs(t) >= 2 and same_sign_in_2_of_3` (`:389`). `_clears` then tests `dsr < 0.95` / `spa_p > 0.10`
against those very constants — so **`_clears(feature_row)` is algebraically identical to
`cleared`** and the multiplicity correction never runs. Proof from the live store: all 7
`SUPPORTED` cells in `evidence_memory_state.json` have `best_dsr` **exactly 0.99**.
`snapshot():322-323` then sorts `by_cell` by `best_dsr` — a sort on a two-valued constant.

This is not discarding an available number: W4/W5/W6 publish no corrected p at all. So the fix is
to stop laundering a t-stat through a fake DSR.

**Fix.** Record `t_controlled` and the era table as their own fields; give `_clears` a feature
branch that reads them; leave `dsr`/`spa_p` `None` for feature cells. As written, the module's own
table ("SUPPORTED = clears DSR + SPA + PBO") describes a check that has never run.

## R7. `NOVEL` is published on a bare t-threshold in W5c and W7, bypassing the four-part bar the module defines
`scripts/weekend_lab_jobs.py:1044` and `:1319`

The module docstring (`:11-15`) states `NOVEL` requires DSR > 0.95 **and** SPA p < 0.10 **and**
PBO < 0.5 **and** the era sign, enforced centrally by `verdict_from` (`:135`). W2, W5b, W7b and W9
call it. W5c and W7 do not:

- `W5c:1044` — `"NOVEL" if real else ...`, where `real` is `t >= 2.0` over 6 cells with no DSR, no
  SPA, no PBO and no multiplicity control at all.
- `W7:1319` — `"NOVEL" if arche else "NOISE"`, where `arche` is `|t| >= 2.5` plus the era sign.
  BH and Holm **are** computed (`:1240-1245`) and **are** reported, but neither gates the word.
  `W7_matched_loser_run09_v0.json` publishes `verdict: NOVEL` with 8 candidates of which only 3
  survive Holm 5%.

W6 (`:676`) has the same shape: `"NOVEL" if survivors else "NOISE"` on `|t| >= 2` over 7 features,
with `multiplicity_note` *asserting* that "the era requirement is doing the work a Holm correction
would". That is an assertion, not a correction, and CANON §63 says SCREEN = BH-FDR / EXPORT = Holm.
**25 of the 92 committed receipt verdicts are `NOVEL`, and none of them cleared the bar the module
docstring defines.**

**Fix.** Route all of them through `verdict_from`; where a feature-level job legitimately needs a
different bar, give it a distinct word (`SCREEN_SURVIVOR`) so one job's `NOVEL` cannot be read as
another's.

## R8. `W7`'s loser-side control silently never runs for some features, and the receipt records that as "measured, and it does not"
`scripts/weekend_lab_jobs.py:1213`

```python
other = lt.get(r["feature"])
same_sign = bool(other and isinstance(ot, (int, float)) and abs(ot) >= 2.0 and ...)
```

`lt` comes from `_summarise(diffs_l, ...)`, which **skips any feature with fewer than 24
loser-side months** (`:1162`). For such a feature `lt.get(...)` → `None` → `same_sign = False` →
the feature is admitted as an archetype candidate **with the control never evaluated**. The row
records `loser_side_moves_the_same_way: False`, indistinguishable from "measured, and it does
not", and the headline (`:1300`) asserts "a loser side that does NOT move the same way".

Loser-side coverage genuinely is shorter than winner-side in the receipts (`ratio`: 292 winner
months vs 289 loser months). The case could not be ruled in or out from the receipt because only
`l[:25]` is published (`:1290`) — which is itself the defect.

**Fix.** Make the three states explicit — `loser_side: "moves_same_way" | "moves_differently" |
"NOT MEASURED (n months < 24)"` — and refuse a candidate whose loser side was not measured. A
check that did not run is not a check that passed.

## R9. `W7`'s controls are de-duplicated, so this is not a matched design
`scripts/weekend_lab_jobs.py:1119`

```python
picks.extend(d2.nsmallest(N_MATCH).index.tolist())
return pool.loc[list(dict.fromkeys(picks))]
```

`dict.fromkeys` collapses duplicates, so a name that is the nearest neighbour of 30 different
winners enters `cw` **once**. `diffs_w[c]` (`:1132`) is then `win[c].mean() - cw[c].mean()` — an
unweighted mean over *distinct* neighbours, not the mean of within-pair differences. Variant 0 is
50 winners × 5 matches = 250 picks; if winners cluster in one size/sector cell, `cw` can collapse
to well under 250 rows and the matching weights become silently non-uniform. The published
`design.controls_per_name: 5` then overstates what was used.

**Fix.** Keep duplicates (`pool.loc[picks]`), or compute per-pair differences and average those.
Either way record `len(cw)` in the receipt so the collapse is visible.

## R10. `W5c` computes its era-consistency gate on one series and applies it to another
`scripts/weekend_lab_jobs.py:987`

`r["era_sign_table"]` is built from `d_screen` (`:975`) — the screen lift versus the *unscreened*
book. The statistic being gated is `screen_minus_random_t`, computed on `d_screen - d_rand`. These
are different series with different signs and different era behaviour. `d_screen` is dominated by
the mechanical effect of removing 10% of any universe (plausibly the same sign in all three eras),
while `d_screen - d_rand` — the only column that is about implied volatility — could flip sign era
to era and still be admitted. The job's own `control_note` says `screen_minus_random` is the only
meaningful column, then gates it on the other one's era table.

Not currently live (`real` is empty; best `screen_minus_random_t` = 1.27), but it is the gate that
decides `NOVEL` at `:1044`.

**Fix.** `era_sign_table((d_screen - d_rand).dropna())` for the gate; keep the `d_screen` table as
a reported diagnostic.

## R11. The evidence memory's clear rates are computed on RAW rows — "pass count is not evidence count" survives one level above today's fix
`learner/evidence_memory.py:301-303`

`distinct_evidence` is applied inside `state_of` but **not** to the rates. Measured on the
committed store: 537 rows → 144 distinct; `global_clear_rate` RAW **0.1304** (what `snapshot()`
writes) vs DIST **0.1528**. W5b contributes 192 of 537 rows because the queue reached it 8 times;
W9 contributes 24 because it ran once. **Re-running W9 seven more times with byte-identical output
would move the prior that feeds `backoff_estimate` for every cell** (`state_of:230`).

Compounding: `_clears` returns False when `dsr` is `None`, and `_record_cells:458-460` sets
`dsr=None` on every non-best cell **by construction** — so W5b's family rate is capped at
8/192 = 0.042 regardless of the book. Same shape as today's `ratio`-is-NULL-by-construction bug.

**Fix.** Compute both rates over `distinct_evidence`, and exclude rows carrying no inference from
the denominator rather than counting them as failures.

## R12. `W5c`'s 72 observations are permanently inert, and the one job that published per-cell power has it discarded
`learner/evidence_memory.py:441-442`

`W5c_options_exclusion` receipts carry `cells` but no `best_cell` and no `inference` — it publishes
`power_of_the_best_cell` instead. `_record_cells` reads `payload["best_cell"]` (→ `None`) and
`payload["inference"]["power"]` (→ `{}`), so `is_best` is False for all 18 cells and every row gets
`dsr=None, spa_p=None, powered=None`. **18 cells × 4 passes = 72 of 537 observations (13%) that can
never be anything but IDEA.** Exactly the `payload["cells"]` bug from the other side.

**Fix.** Fall back to `power_of_the_best_cell`; derive `best_cell` from
`max(cells, key=mean_monthly_excess)` when absent.

## R13. Promotion is gated on the runner's variant count, not on the evidence
`learner/evidence_memory.py:190, :242`; `scripts/weekend_lab.py:78`

`evidence_key` includes `variant` plus the rounded result. A deterministic job with `n_variants=1`
returns an identical row every pass, so all its cells collapse to **one** distinct observation
forever and freeze at IDEA:

```
IDEA | W6-behavioural::feature::attention_z_5d | cleared 1 of 1 distinct (raw 9)
IDEA | W6-behavioural::feature::amihud_21d     | cleared 1 of 1 distinct (raw 9)
IDEA | W6-behavioural::feature::ret_5d         | cleared 1 of 1 distinct (raw 9)
```

Three W6 features clear the full bar on every pass and can never leave IDEA, while a W5 feature
reaches SUPPORTED because the QUEUE happens to give W5 two variants. **9 of the 13 families in the
store are structurally incapable of ever reaching SUPPORTED or REFUTED.** The collapse rule is
right; making it the only promotion currency makes the state a function of the runner's config.

**Fix.** A single observation that clears should be `CONDITIONAL`, not `IDEA`; SUPPORTED/REFUTED
should require distinct **variants** explicitly rather than inheriting it by accident.

## R14. `_clears` accepts `same_sign_in_2_of_3` on book rows, where it is the wrong question
`learner/evidence_memory.py:154`

`holds_in_2_of_3 OR same_sign_in_2_of_3` — and the producers set `same_sign: true` for an
**all-negative** era table (W6 `prox_52w_high`: `eras_with_a_positive_mean: 0`,
`holds_in_2_of_3: false`, `same_sign: true`). Counterfactual on the live store:

```
CURRENT (holds OR same_sign): 7 SUPPORTED
STRICT  (holds only):         3 SUPPORTED
```

`skew_25d_30d`, `log_dollar_vol_20d`, `log_dollar_vol_20d__xs`, `consensus__xs` are SUPPORTED only
via the sign-blind disjunct. For *features* that is defensible (`_record_features` uses `abs(t)`;
a signed predictor is tradable either way). For *books* it is not: `_record_cells` records a
realised **signed** excess. A W9 survivor cell with dsr 0.96 / spa 0.05 / pbo 0.3 and eras
(−1.5%, −0.8%, +0.2%) gets `same_sign: true` → clears → SUPPORTED, for a book that **lost money in
two of three eras**.

**Fix.** Pass the sign convention into `_clears`; require `holds_in_2_of_3` on grid/book rows.

## R15. `run_job` resurrects a stale receipt when a restarted pass crashes before writing
`scripts/weekend_lab.py:232-240`

`out_path.exists()` is checked *after* the subprocess returns, and `_receipt_path` is keyed on
`(job, run, variant)` — which repeats when the operator restarts with `--start-pass`. Scenario: a
syntax error is introduced into `weekend_lab_jobs.py`; the operator restarts with
`--start-pass 9`. Every job's `run09` receipt already exists. The subprocess dies at import having
written nothing → the **old** payload is loaded, `payload.setdefault("verdict", "FAILED")` at
`:237` does **not** overwrite the existing `"NOVEL"`, and the receipt is rewritten with last
pass's headline plus `exit_code: 1`. `append_leaderboard` posts last pass's result as this
pass's, `update_best` can re-promote it, and `failures[key]` is never incremented (`:301` counts
only `FAILED`/`TIMEOUT`) — so a file that cannot import loops forever reporting NOVEL. The receipt
set on disk shows restarts did happen (`run00`, gaps at `run05`/`run07`).

**Fix.** `out_path.unlink(missing_ok=True)` before launching the subprocess.

## R16. `W6_behavioural` mis-dates its own monthly series whenever a month is skipped
`scripts/weekend_lab_jobs.py:632-634`

```python
ic = pd.Series(ics, index=sorted(d["month"].unique())[:len(ics)])
be = pd.Series(betas, index=ic.index[:len(betas)])
```

`ics` skips months with `< 30` names (`:614`); `betas` additionally skips `LinAlgError` months
(`:625`). The index taken is the **first** `len(ics)` months in sorted order — so if 8 early months
are skipped (thin 1999-2001 cross-sections), every coefficient is stamped ~8 months early and the
last 8 months are dropped. That feeds `era_sign_table(be)`, a **gate for the NOVEL verdict** in W6
and for the survivor harvest in W9 (`:1892-1896`). Same shape as R1, different job.

Verified **not live today**: on the current panel all 7 features have 309 months with **0** skipped.
Latent — it fires the first time a thinner feature is added or the panel is sub-sampled.

**Fix.** Collect `(month, value)` pairs inside the loop and build the Series from them.

## R17. `W6`'s Fama-MacBeth t has no HAC correction while its sibling job's does
`scripts/weekend_lab_jobs.py:630-631`

`t_be = be.mean() / (be.std(ddof=1)/sqrt(n))` — the plain FM t. W5 (`features_options`) publishes
`newey_west_lags` on the same kind of series. Monthly coefficient series on persistent features are
positively autocorrelated, so the uncorrected t overstates. W6's three published survivors are
`attention_z_5d 2.705`, `amihud_21d −2.371`, `ret_5d −4.273` — the first two are close enough to
the bar that a lag-3 NW correction could move them off it.

**Fix.** Use the same NW estimator as `features_options`, and report both the naive and the
corrected t per the house rule.

## R18. `_market_circular_shift_null`'s p-value omits the +1 correction and can report an impossible 0.0
`scripts/weekend_lab_jobs.py:1375`

```python
"p_value_one_sided": round(float((a >= obs).mean()), 4) if len(a) else None,
```

The observation is not counted among the draws, so with 500 shuffles the reported minimum is
`0.0000`, which is not a probability. The correct estimator is `(1 + Σ[a ≥ obs]) / (1 + n)`, floor
1/501 ≈ 0.002. Latent (smallest committed p is 0.062) but sitting directly under a publication
threshold: `W8:1802` gates `NOVEL` on `pm <= 0.05`.

Secondary: `off = rng.integers(1, n)` draws **with replacement** from only `n−1` distinct circular
shifts, so 500 draws oversample ~299 distinct null values. Not a bias, but `null_draws: 500`
overstates the resolution.

**Fix.** `(1 + (a >= obs).sum()) / (1 + len(a))`; report the distinct-shift ceiling beside
`null_draws`.

## R19. `W7`'s BH/Holm use a normal approximation on a t with ~24 degrees of freedom
`scripts/weekend_lab_jobs.py:1224`

```python
def _two_sided_p(t):
    return float(erfc(abs(float(t)) / _sqrt(2.0)))
```

The statistic converted is `t_block_non_overlapping`, whose companion `n_effective` is **25** in
every published row. The normal approximation understates the p-value by 1.6×–2.4× over the
observed range:

```
t=2.502  normal 0.01235  t24 0.01957  (1.58x)
t=2.703  normal 0.00687  t24 0.01242  (1.81x)
t=3.054  normal 0.00226  t24 0.00546  (2.42x)
```

Consequence checked rather than assumed: with m = 49, correcting to `t.sf(·, n_effective−1)` leaves
both published survivor sets unchanged (BH 10% keeps all 8; Holm 5% keeps the same 3). Real defect,
did not move this receipt — but the margin on `net_rev_4w__xs` (BH q 0.021 → ~0.04) is the kind
that moves on the next run.

**Fix.** `2 * scipy.stats.t.sf(abs(t), df=n_effective - 1)`. The df is already on the row.

## R20. The `_cells/` prediction cache is keyed on RangeIndex row positions with no panel fingerprint
`scripts/weekend_lab_jobs.py:220-223, 248-256, 305-311`

The panel index is a plain `RangeIndex(0..925756)`. The cache blob stores
`{index, values, tag, kind, target, horizon, written_utc}` — **no row count, no
`schema_version`, no panel hash** — and it is committed to git (~136 MB). If the panel is rebuilt
with any change in row count or ordering (adding a year, a data fix — exactly what W1 exists to
detect), every cached label still resolves and the cached out-of-sample predictions attach to
**different name-months**. `df.loc[s.index, col] = s.values` raises `KeyError` only when a label is
*missing*; a same-length-different-meaning panel passes silently.

Currently consistent (panel built 11:51, cells written 12:26+), so latent, not live.

**Fix.** Write the panel's `schema_version` + row count (or a hash of `permno`/`month`) into the
blob and refuse on mismatch. Better: key the series on `(permno, month)` rather than row position.

## R21. `W10` and `W9` publish hardcoded numbers inside receipt fields
`scripts/weekend_lab_jobs.py:2244-2250`, `:1996-2003`

`W10`'s returned dict contains the constant string *"the 3-month DECILE SPREAD is alive in the last
era at t 3.479, and the 3-month BOOK is not (tw_net 4.511 vs a market of 4.864)"* — beside
`row["decile_spread"]["3m"]["t"]`, which the same function computes. Every future W10 run publishes
3.479 / 4.511 / 4.864 whatever it actually computed. `W9`'s `why_the_bigger_family` has the same
shape ("survived in ONE of W7's four variants"). This is worse than a number in prose: it is a
stale number **in the receipt**, where it looks derived. Note `W10_decay_autopsy` has produced no
committed receipt in nine passes, so these numbers currently have no run behind them at all.

**Fix.** Interpolate from the computed values, or drop the numbers and keep the lesson.

## R22. `W9`'s DSR depends on how many receipt files happen to be on disk
`scripts/weekend_lab_jobs.py:1967-1970`

`n_trials = len(examined) + len(cells)`, where `examined` is harvested from
`WL.OUT.glob("W*_run*_v*.json")`. Deriving breadth from receipts is the right instinct, and the
`(feature, job, variant, key)` dedup correctly prevents repeated passes from inflating it — but the
count still grows as **new variants** land, so the same job on the same data yields a different DSR
on pass 3 and pass 9. Commit `78c37fc` ("DSR 0.529 → 0.202") is that in action. The receipt records
`search_breadth_feature_job_variant_rows` (a count) but not **which** trials were counted, so the
number is not reproducible from panel + code.

**Fix.** Store the sorted `examined` list (or its hash) in the receipt, and state in the headline
that the DSR is conditional on the search enumerated there.

## R23. `W5b`'s covered-universe benchmark is built from one signal's coverage, and its cross-check twin can be itself
`scripts/weekend_lab_jobs.py:750, :826`

- `:750` — `cov = df[df[list(have)[0]].notna() & ...]` defines the "option-covered universe"
  benchmark from the coverage of the **first signal only** (`cp_iv_spread_30d`). The
  `sig_combined` book requires *both* signals and therefore trades a strictly smaller universe than
  the benchmark it is scored against — so the `covered_univ` leg is not the combined cell's own
  universe, which is the one thing that leg exists to be.
- `:826` — `twin = best.replace("covered_univ", "full_mkt")`. `pool = covered or fam` (`:821`)
  falls back to `fam` if no covered cell produced a series; `best` then ends in `full_mkt`, the
  `replace` is a no-op, and `best_vs_full_market_twin` reports the best cell as its own twin at an
  identical number. Silent, and it reads as a passed cross-check.

**Fix.** Build the covered universe from the intersection of every signal the cell uses; and
refuse (or label `NOT AVAILABLE`) when `twin == best`.

---

# OPTIONAL

- **`scripts/weekend_lab.py:301`** — `DEFERRED` is not counted as a failure, so `W4`'s docstring
  claim (`weekend_lab_jobs.py:552-554`, "the runner's two-strike skip is preserved") is false.
  `W3_neural_long` produced 5 receipts reading `"verdict": "DEFERRED"`, `elapsed_s: 0.7`, consuming
  a queue slot every pass. Add `"DEFERRED"` to the failure tuple.
- **`learner/evidence_memory.py:348-349`** — `if not fam: return 0` drops 14 of 82 receipts
  (`W1` ×9, `W3` ×5, which carry no `family_id`) with no error, and W11's `errors` list stays
  empty. Fall back to `family_id = payload["job"]`.
- **`learner/evidence_memory.py:287-289`** — `median_n_months` indexes `[len(rows)//2]` into a list
  already filtered to integer `n_months`. Reproduced: two observations where one lacks `n_months`
  raises `IndexError` → `state_of` raises → `snapshot()` raises → W11 dies and the memory silently
  stops updating. Index into the filtered list's own length.
- **`learner/long_panel.py:274`** (same shape at `:317`) — `split_era_share_basis_gate` guards the
  missing column and returns `CANNOT DETERMINE`; `hand_checked_split_rows` dereferences
  `split_prior_year` unguarded. `--regate` against an older panel raises `KeyError` **before**
  `LONG_RECEIPT.write_text`, leaving the previous gate verdict on disk describing a different
  panel. `if "split_prior_year" not in df.columns: return []`.
- **`scripts/weekend_lab.py:288`** — `QUEUE` is iterated in fixed order every pass with no rotation
  and no "already have this `(job, variant)`" check. 8 of 9 `W1` receipts and 7 of 9 `W6` receipts
  are byte-identical modulo timestamp, while `W10_decay_autopsy` has zero. The variant mechanism
  fixes this for the 5 multi-variant jobs; the other 11 do what the docstring calls wrong.
- **`_w2_grid:294-297`** — a per-year fit failure writes `cells[f"{kind}|{target}|{h}m|fit"]` and
  continues. Every failing year **overwrites the same key**, so 20 failed years read as 1, and the
  surviving `{...}|{bps}bps` cell looks complete while fitted on a partial set of test years. Key
  the error by year and record `n_years_fitted` on the cell.
- **`_w2_report:353-357` / `W9:1962`** — `pd.concat(series, axis=1).dropna()` truncates every cell
  to the common window for the inference, while `cells[key]` carries each cell's own-window
  terminal wealth and t. A reader comparing `best_cell_book.t_stat_paired_vs_market` against
  `inference` is comparing two windows.
- **`weekend_lab_jobs.py:2334-2345`** — `main()` catches, writes a `FAILED` receipt, and returns 0,
  so `r.returncode` is always 0 and `weekend_lab.py:236-238` (the `stderr_tail` capture) is
  unreachable. Cosmetic, but the stderr a reader wants on a failure is never captured.
- **`learner/features_price.py:256`** — `attach` leaves a stray `date` column on the panel. Nothing
  reads it today, but `W9:1914-1918` runs `FP.attach` then `FO.attach`, so the price-bar date
  occupies the name `date` for every subsequent join. Add `"date"` to the drop list.
- **`learner/models.py:220-221`** — the lgbm meta now always carries `objective` /
  `quantile_alpha`, changing the default key set on the lgbm path — the exact schema-stability
  concern `evaluate.book` was careful about (`evaluate.py:327-334`). Harmless today; inconsistent.
- **`W9:1885-1890`** — `survivors.setdefault` means the first receipt in **filename order** sets a
  feature's booked direction. No feature disagrees across today's receipts (verified: 12 survivors,
  0 with two directions), so latent — but if two variants ever disagree on the sign, the direction
  is an alphabetical accident, not the screen the docstring credits.
- **`learner/long_panel.py:25-27`** — docstring says "~19 out-of-sample years";
  `FIRST_TEST_YEAR = 1999 + 5 = 2004` gives 21. The constant is consumed; the prose is wrong.

---

# WHAT IS CORRECT — verified, not assumed

- **No point-in-time leak in the panel or feature code.** `walk_forward_splits:1043-1050` embargoes
  on `mat_date_{h}m < cutoff`, not on the feature date — a Nov-2015 row with a 12m target is
  correctly excluded from a 2016 test year. Every `__xs` rank is `groupby("month")`
  (`dataset.py:881`); W6's IC and FM regression rank **within** the month group (`:617-621`);
  `_residualise:677-694` and `W7b._resid_on_size:1595-1600` are within-month and index-aligned.
  `evaluate.decile_table:120` cuts within month via `groupby(month).transform(qcut)`, so every
  `cross_section_shape` block in W5b, W7b and W9 is PIT-correct. **`W7:1136`'s
  `cut = g[col].quantile(0.9)` is fine** — `g` is the per-month group, so that is a within-month
  decile, and the self-inclusion of the 50 winners in a ~1000-name month is what makes the stated
  0.10 chance-recall baseline exactly right.
- **`features_price` PIT is clean throughout, and its tests are decisive.** `attention_z` shifts
  **before** the rolling window so t's own observation is excluded; every `shift`/`rolling` is
  grouped by permno; no `center=True`, no `bfill`, no full-sample quantile or standardization.
  27/27 pass, and the tests compute the *wrong* window and refute it rather than only asserting the
  right one. The `cfacpr`-is-a-future-quantity worry does not apply: every price feature is a ratio
  of `adj_prc` values within one name over a trailing window, so a later split cancels.
- **Both `merge_asof` directions are right.** `features_price.attach` is backward, 7-day tolerance;
  `allow_exact_matches=True` is correct here because `entry_date` is a real session whose close the
  panel already uses. `features_options.attach:568` refuses same-day, which is also correct — an IV
  surface dated t is not knowable at t's close.
- **W10's carry-forward is a carry, not a peek** (`:2168-2176`).
  `keep[months[i]] = months[(i // hold) * hold]`, and `(i // hold) * hold <= i` for all `i`, so the
  anchor month is never later than the row's own month. `_slow1` is the identity and reproduces the
  raw signal — a built-in control.
- **`book(hold_k=)` hysteresis is correct.** `fill` can never reach past rank `k` (the count of
  non-kept names inside the top `k` is `k − |keep ∩ top-k| >= k − |keep|`, always enough), so the
  buy rule is honoured; no permno can be double-counted (`fill` excludes `keep` by permno); the
  book size stays exactly `k`. Measured on a synthetic 200×60 panel:

  ```
  hold_k None  names/mo 50.0  turnover 0.764
  hold_k 100   names/mo 50.0  turnover 0.517
  hold_k 150   names/mo 50.0  turnover 0.263
  ```

  The `hold_k <= k` refusal (`evaluate.py:246-250`) and the conditional key set (`:327-336`) are
  both right.
- **`models._fit_lgbm(quantile=)` refuses correctly.** The post-fit check reads the *fitted
  booster's* objective (`models.py:207-217`), not the constructor kwarg — the pre-fit guard alone
  would have been the bug it was written to prevent. `fit_predict`'s argument validation runs
  before any data is touched (`:318-324`). `arm_reconstruct` is the identity for `arm="raw"`, so
  the quantile variant's omission of it (`weekend_lab_jobs.py:487`) is harmless.
- **No mutation hazard.** `long_panel.load_long()` re-reads the parquet on every call (no module
  cache) and `dataset.feature_columns()` is a fixed list, so the `pred_*` / `book_*` / `_slow*` /
  `sig_*` / `arch_*` columns that jobs write onto `df` can never become model features; jobs also
  run as separate subprocesses. **Keep `load_long` uncached** — adding an `lru_cache` to it would
  turn every one of those assignments into a live cross-job leak.
- **W7's overlap discipline (apart from R4) is right.** `:1155-1160` derives `t_newey_west` and the
  block t from `EV.overlap_corrected` and **`raise SystemExit` if absent**, then gates the archetype
  bar on the *non-overlapping* t (`:1206`). `n_effective = 25` for 297 monthly draws of a 12-month
  outcome. All three t's are reported, per the house rule.
- **W8's `_p` (`:1782-1791`)** applies the same derive-or-refuse discipline on `p_value_one_sided`;
  nulls 1 and 2 are skipped with a written reason when the state is market-level, and
  `market_level` is **measured** (`:1738`) rather than assumed. The circular-shift construction is
  sound — each row gets its own month's shifted state, offsets exclude 0, and the state marginal,
  run lengths and calendar are all preserved. Only the p-value estimator (R18) is off.
- **W6b's statistics are right.** Every t is on a **monthly** series (`groupby("month").mean()`),
  n = months not name-months, and both `months` and `name_months` are reported. The NaN-contamination
  risk in `rest = df[~m & ...]` is immaterial (`miss__log_dollar_vol_20d = 0.0001`). The verdict
  correctly rests on the same-weighting leg rather than the vs-VW-market leg.
- **`evaluate.book`'s `tradable_floor` derives-or-refuses** (`:218-236`) — the fix for the earlier
  silent-pass bug is real — and the tie-break is seeded rather than permno-ascending.
- **Key names in the grid path all match their producers**: `deflated_sharpe.dsr`,
  `spa.p_spa_consistent`, `pbo.pbo`, `power.{powered,years_needed_for_t2,years_observed,n_periods}`,
  `terminal_wealth_{net,gross,market_same_months}`, `holm_p`, `bh_fdr_q`. Checked one by one against
  the committed receipts. **No new instance of today's four wrong-key bugs in these paths.**
- **`_w2_grid`'s cell cache is variant-tagged**, so an ablation cell can never be served to the
  baseline, and a corrupt entry is deleted and refitted rather than half-used. The only gap is the
  panel fingerprint (R20).
- **`evidence_memory`'s append-only JSONL store, `_era_count`, `read_all`'s tolerance of a truncated
  final line, `distinct_evidence` itself, the STOP-file check, and the per-`(job, variant)` failure
  keying** are all sound. `_record_cells`'s refusal to paste family inference onto non-best cells
  (`:458-460`) is right in intent; see R11 for its unintended consequence.
- **`test_weekend_long_panel.py` is non-vacuous** (explicit `assert bad.any()` anti-vacuity checks).
  Its gap is coverage, not correctness: it never touches `split_era_share_basis_gate` — the function
  in C2.

---

# VERIFICATION STORY

- **Tests reviewed:** yes. `test_weekend_features_price.py` 27/27 pass and are unusually good — they
  compute the wrong window and refute it rather than only confirming the right one.
  `test_weekend_long_panel.py` is non-vacuous but has **no test at all** for
  `split_era_share_basis_gate`, the function in C2. No test covers `_w2_grid`'s cache round-trip
  (R20), `verdict_from`'s branch structure (R3), or W7's series construction (R1).
- **Run, to verify rather than assume:** the share-basis gate with the defect injected (C2);
  `power_note` on five synthetic arms (R3 tautology); `book(hold_k=)` on a synthetic 200×60 panel
  (hysteresis correctness and turnover); the W7 month-labelling bug reproduced on a fixture (R1);
  `EM.state_of` on a two-row mixed-`n_months` cell (IndexError); `_clears` counterfactual over the
  live store (R14, 7→3 SUPPORTED); raw-vs-distinct clear rates over the live store (R11);
  month-skip counts per W6 feature (R16 latency); `t_naive` vs `t_block` across every W7 row (R4);
  normal-vs-t p-values with the survivor sets recomputed (R19); direction stability and `holm_p`
  presence across all committed W7 receipts; era spreads across all 7 W8 receipts (R2).
- **Security:** not applicable — offline research code, no network, no credentials, no user input.
- **A note on the reviewed state:** two commits landed and the working tree changed during the
  review. `W12_short_side` was added after the scope was set and is **not** reviewed beyond a read
  of `_long_short` (its borrow charge, both-legs cost and cash benchmark look right; the `0.5`
  scaling is consistent with a 50/50 dollar-neutral book).
