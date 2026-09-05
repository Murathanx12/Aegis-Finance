# ADVERSARIAL REVIEW — 2026-09-06 weekend lab

*Reviewer: a hostile reader with the panel, the receipts and the code. Every
criticism below carries a number or a code line; where an attack failed, it says
so and says what was tried. Written against `docs/BUILD_WEEKEND_LAB_2026-09-06.md`
at repo HEAD `f6b96e3`. **`scripts/weekend_lab_jobs.py` was being edited by a live
session while I read it** — `W9_survivor_books` moved from line 1837 to 1944 in the
span of this review — so line numbers are as of `f6b96e3` and should be re-grepped
before being quoted.*

**Claim 1 is not broken.** I reproduced its headline byte for byte and it survived
a point-in-time audit, a split-contamination audit, a random-book control and a
size-matched control. It is WOUNDED in one specific place — the multiplicity
correction — and that wound is large enough to change the verdict word.

---

## SCOREBOARD

| # | claim | verdict | the number that decides it |
|---|---|---|---|
| 1 | `target_rev_1m__xs` 56.66 vs 13.03, t 2.055, POWERED | **WOUNDED** | DSR falls **0.529 → 0.202** when the family is the one the repo's own code computes (277, not 24) |
| 6 | early-era share-basis gate PASS | **BROKEN** | I injected the exact 2026-09-04 bug and the gate still returns **PASS**, gap **+0.0129** against its 0.10 alarm |
| 2 | the effect DECAYED (2.35 / 1.81 / −0.03) | **WOUNDED** | against the **EW** market the three eras are t **0.46 / 0.64 / 0.04** — no era is alive. Against a size-**matched** control they are 2.30 / 1.70 / 0.12. Both are printed below; the doc printed neither. Also: **no W10 receipt exists** in the receipts directory |
| 3 | FM t +4.15 lost money gross; the effect lives in d1 | **WOUNDED** | "d1 is the effect" holds (**t −3.83**). "d10 is the worthless region" does **not** (**t −0.615**), and the doc's decile row is a *pooled name-month* mean whose d10 sign **flips** (−0.032 → +0.098) when one observation per month is used |
| 4 | S28's band replicates as a FLOOR | **SURVIVES** the tail attack | dropping the 5 largest-\|diff\| months makes it **stronger** (−2.58 → −4.40%/yr, t −1.74). But "clear as an exclusion" at **t −0.93** is not a supported word |
| 5 | five published features died under their own controls | **SURVIVES** | with `prox_52w_high` in the regression, momentum's own t goes **2.11 → +3.93**. Not over-control |

---

## CLAIM 1 — `target_rev_1m__xs`: **WOUNDED**

### What I reproduced exactly

Loading `train_table_long.parquet` and calling `evaluate.book(k=50, weight="vw",
cost_bps=10, ret_col="fwd_1m", mkt_col="mkt_vw_1m")` on `target_rev_1m__xs`
returns, to four decimals:

```
months=308  TWnet=56.655  TWmkt=13.031  mean=0.8032%/mo  t=2.055
eras: 1999-2007 (105, 1.5100, 2.349) | 2008-2015 (96, 0.9503, 1.807) | 2016-2024 (107, -0.0224, -0.028)
```

Every figure in §0 of the build doc reproduces. The market leg is the same 308
months as the book (`evaluate.book` returns
`terminal_wealth_market_same_months`, and the paired series is
`net.index.equals(mkt.index)`-gated at `weekend_lab_jobs.py:2027`). **The
terminal-wealth comparison is not misaligned.**

### PIT: the revision is clean

`learner/dataset.py:786` — `target_rev_1m = meanptg / meanptg.shift(1) - 1` where
both `meanptg` values are IBES `statpers` vintages at or before the row's
`vintage`, the row trades at `entry_date = statpers + lag_days`
(`dataset.py:707-711`, `merge_asof` forward with a 7-day tolerance), and the lag
is enforced on the merge, not asserted in prose. The prior-row lag is guarded by
`ok1 = (gap >= 20) & (gap <= 45)` so a name that left and returned cannot book a
"one-month" revision spanning a year. **No look-ahead found.** The numerator is
the UNADJUSTED `ibes__ptgsumu` — the post-2026-09-04 source.

### Delisting / survivorship: not the story

**123 of 15,400** top-50 selections (0.80%) carry a delisting-filled forward
return (`delisting_filled_1m`), and the fill convention is hold-to-last-observed-
then-cash (`dataset.py:590-596`), which is conservative. Rows that fail hygiene
are kept and NULLed, not deleted (`dataset.py:823`). Survivorship does not
produce this.

### A REAL BUG in the headline feature — which happens to work against it

`target_rev_1m` is a ratio of two **unadjusted** consensus targets one month
apart, and **nothing nulls it across a share-basis change**. `dataset.py:823`
nulls only `("ratio", "upside", "log_ratio")` on hygiene failure;
`target_rev_1m` is untouched. Measured:

- **4,839** rows in the long panel have a `cfacpr` move against the prior month;
  **4,303** of those carry a non-null `target_rev_1m`, with **mean +3.12 (312%)**
  and **max +359** — reverse splits reading as a 35,900% upgrade.
- **1,013 of 15,400 (6.58%)** of the book's top-50 selections over 308 months are
  such rows. Contamination by era: **1.1 / 2.1 / 6.6** names per month.

This is the same class as FINDING 1's `vwap_60d_gap` artefact, in the feature the
weekend made its headline, and no test caught it either. It should be fixed.

**But cleaning it makes the claim stronger, not weaker**, so it is not the
explanation:

| variant | TW net | t | 1999-2007 | 2008-2015 | 2016-2024 |
|---|---|---|---|---|---|
| as published | 56.66 | 2.055 | 2.349 | 1.807 | −0.028 |
| split rows dropped, re-ranked | **72.85** | **2.282** | 2.592 | 1.685 | +0.066 |
| split-clean **and** close ≥ $5 | **88.09** | **2.458** | 2.468 | 1.487 | +0.464 |

### The real wound: the DSR is computed over the wrong family, and the code knows it

`W9_survivor_books` at `f6b96e3` contains a 12-line comment block ending:

> "A DSR computed over 24 book cells prices the second search and ignores the
> first, which flatters exactly the thin-path survivor most."

and then `n_trials = len(examined) + len(cells)` (`weekend_lab_jobs.py:2078`).
**The receipt that produced the headline did not run that code.**
`W9_survivor_books_run09_v0.json` (written 04:58 UTC) carries
`n_trials_used_for_the_DSR: null`, `search_breadth_feature_job_variant_rows:
null`, `dsr_if_only_the_books_were_counted: null`, and
`deflated_sharpe.n_trials: **24**`. The repo code and the published number are
different runs.

Recomputing `examined` over the lab's own receipts with the code's own harvest
loop gives **253 (feature, job, variant, side) rows**, so `n_trials = 277`.
Re-running `inference.deflated_sharpe`'s analytic expression on the receipt's own
moments (`sr 0.1171, T 308, skew 0.588, kurtosis 10.564`):

| n_trials | SR0 (the noise bar) | z | **DSR** |
|---|---|---|---|
| 24 (published) | 0.1130 | +0.073 | **0.5293** |
| 49 | 0.1295 | −0.221 | 0.4126 |
| 100 | 0.1444 | −0.488 | 0.3129 |
| **277 (the code on disk)** | **0.1638** | **−0.834** | **0.2022** |

**0.2022 is below the 0.2305 noise bar Friday's night lab used to call the L1
learner arm NOISE.** The headline arm and the arm the lab already rejected are on
the same side of the same line once the search is priced consistently.

Even at the published N = 24 the receipt says the arm's Sharpe is **0.1171
against a zero-edge search's expected 0.1130** — the headline is **3.6%** above
its own noise bar. The doc's "**the first POWERED result of the run**" and
"`powered: true`" are a statement about *tape length*, not about evidence, and
the two sit in adjacent lines in §0 where a reader will fuse them.

### Thin-path provenance, quantified

`target_rev_1m__xs` entered the survivor family from `W7_matched_loser`. Across
the four W7 variants that ran:

| variant | design | Holm ≤ 0.05 survivors |
|---|---|---|
| v0 (×2 runs) | 50 winners × 5 controls | log_dollar_vol_20d, log_dollar_vol_20d__xs, consensus_rev_1m__xs |
| v1 (×2) | 100 × 3 | log_dollar_vol_20d, log_dollar_vol_20d__xs |
| v2 (×2) | 50 × 5 | log_dollar_vol_20d, consensus__xs, net_rev_4w, log_dollar_vol_20d__xs |
| **v3 (×2)** | **25 × 8** | **target_rev_1m__xs**, net_rev_4w, net_rev_1m, consensus__xs, log_dollar_vol_20d, consensus_rev_1m__xs |

**`target_rev_1m__xs` clears Holm in 1 of 4 variants**, and is **absent from
`winner_side` entirely in v0**. FINDING 3's table in the doc is v0's — so the
weekend's headline feature does not appear anywhere in the section that is
supposed to have discovered it. `log_dollar_vol_20d` survives 4 of 4 and lost
money as a book. That asymmetry is the definition of a thin-path survivor, and
it is the exact thing N = 24 fails to price.

### Attacks that FAILED (the claim survives these)

- **"It's a benchmark/universe artefact."** Five random 50-name VW books drawn
  from the identical monthly rows, same weighting, same 10 bps, give ALL-period
  t of −1.99, −1.15, +0.42, −1.11, −0.21 and 1999-2007 t of −0.82, −0.16, −0.26,
  −0.60, +0.62. The VW return of the whole *covered* universe is 0.9753%/mo
  against the market's 0.9747% — **"having analyst coverage" is worth
  0.06 bp/month.** The selection is doing the work.
- **"It's a size tilt."** Ambiguous, and both readings belong in the receipt.
  The book's weighted-average log cap sits **2.3 log points (≈10×) below** the
  cap-weighted universe, stably in all three eras, and it carries an
  **SMB beta of 0.562 (t 5.13)** on `mkt_ew_1m − mkt_vw_1m`. Regressing the
  paired excess on that crude SMB gives **alpha +0.475%/mo, t 1.25** (from
  2.055). But a *proper* size-matched control — each holding replaced by a random
  name from the **same within-month market-cap decile** at **identical weights**,
  averaged over 10 seeds — gives **+0.8167%/mo, t 2.10**, i.e. no attenuation at
  all. The reconciliation: within its own covered universe the book sits at cap
  percentile **0.72–0.76**, so it is *not* a small-cap book; the SMB proxy is
  driven by CRSP micro-caps the book never holds and the regression over-controls.
  **The size-matched control is the right one and the claim passes it** — but the
  SMB beta of 0.562 at t 5.13 is a real exposure and any factor-adjusted version
  of this claim has to price it.

### What would settle claim 1

1. Re-run `W9_survivor_books` on the code that is actually on disk and publish
   the receipt with `n_trials_used_for_the_DSR` populated. If it prints ~277 and
   DSR ~0.20, the verdict word must change from `DECAYED` to something that says
   *within selection noise once the screening search is priced*.
2. Null `target_rev_1m` / `target_rev_3m` on rows whose `cfacpr` moved, at
   `dataset.py:786`, and re-issue every number that reads them.
3. Publish the size-matched control table beside the raw excess. It is the
   difference between "beats the market" and "beats a cap-matched draw", and this
   claim survives both — which is worth saying.

---

## CLAIM 6 — the early-era share-basis gate: **BROKEN**

`learner/long_panel.py:183-264`. The gate compares the in-band rate of the PIT
ratio on `split_prior_year` rows against a matched control, and calls PASS when
`gap < 0.10` (`long_panel.py:263`). Its own docstring says what it is looking
for: *"a split-adjusted numerator over a raw denominator would push the
post-change rows out of the band by roughly the split factor, so the split-name
in-band rate would collapse relative to the matched control."*

**I injected exactly that bug and the gate passed.**

Reconstructing the 2026-09-04 corruption from the panel's own audit column
(`ratio_adj_check = meanptg_adj·cfacpr/close`, so the buggy ratio is
`ratio_adj_check / cfacpr`) and re-running `split_era_share_basis_gate`:

| | in-band rate, split names | in-band rate, matched control | **gap** | verdict |
|---|---|---|---|---|
| as built (correct panel) | 0.9807 | 0.9780 | −0.0027 | PASS |
| **with the bug injected** | **0.8529** | **0.8657** | **+0.0129** | **PASS** |

The gap moves by 1.6 points against a 10-point alarm. The bug is plainly visible
— **both** in-band rates collapse from 0.98 to ~0.86 — and the gate reads the
*difference*, which is exactly the statistic a common shift cancels out of.

The mechanism is that `split_prior_year` flags a split in the **prior year**,
while the corrupting quantity is `cfacpr`, the **cumulative factor to the end of
the sample**. In 1999-2004 almost every surviving name carries a large `cfacpr`
from splits that had not happened yet, so the control group is corrupted as badly
as the treatment group. A matched-difference design cannot detect a shift that
applies to both arms.

This is `reference_gate_that_cannot_go_green` in mirror image: **a gate that
cannot go red.** It is not a strict certification of the 1999 era; it is not a
certification at all. Note that the *panel itself is fine* — the build reads
`ibes__ptgsumu` and my injection was synthetic. What is void is the evidence that
it is fine in 1999-2004.

Secondary weakness, smaller: the eligibility filter drops **1,879 of 21,498**
early-era split-flagged rows, **1,872** of them for failing `has_opinion` and 7
for `ratio ≥ 50` — so the corrupted right tail (reverse splits, which push the
ratio above the readable ceiling) is partly screened out of the treatment arm
before the comparison. That is a second-order softening on top of a design that
has no power to begin with.

**What would settle it:** test the **level**, not the gap — the in-band rate on
split names against a fixed floor (e.g. ≥ 0.95), which moves 0.9807 → 0.8529
under the injected bug and would FAIL. Or compare `ratio` against
`ratio_adj_check` directly on split rows: the disagreement rate is already
computed in `dataset.build`'s receipt and is the statistic that actually carries
the signal. And whichever is chosen, **run it against the injected bug before
believing it** — this gate would have been caught in five minutes by that test.

---

## CLAIM 2 — "it decayed, around 2016": **WOUNDED**

### First: the receipt does not exist where the doc says receipts live

The build doc opens *"a line with no receipt is not in this file."* §0.1's entire
decay-autopsy table has **no receipt in
`backend/data/optimus/weekend_lab_2026-09-06/`**. `W10_decay_autopsy` is not in
the running queue (`scripts.weekend_lab --queue …` on PID 104436 lists 13 jobs,
W10 not among them) and appears nowhere in `LEADERBOARD.md`'s 60+ rows. The
numbers do exist — in
`…/scratchpad/w10_test{,2,3}.json`, written 12:50–12:52 — i.e. in a
session-scoped temp directory that is deleted with the session. The values match
the doc (`gross TW 3.6944 vs market 4.8636`, `EW t −1.478`, `sd 0.547195 vs
0.136163`, `3m spread t 3.479`). Not fabricated; **not durable**, and not where
the doc's own rule says it must be.

### The era split is NOT post-hoc — this attack failed

`ERAS` is a module constant at `learner/long_panel.py:96`, defined as three
near-equal thirds (9/8/9 years) *in the panel builder*, before any result
existed, and `add_era` keys on `entry_date` (the date the money moved), not on
`vintage`. Every job imports it rather than re-deriving it. I could not find a
tuned boundary.

### But the "decay" is benchmark-dependent, and the doc reports one benchmark

Same book, same months, scored against the **equal-weighted** CRSP market
instead of the value-weighted one:

| era | book | VW mkt | EW mkt | excess vs VW | t | **excess vs EW** | **t** |
|---|---|---|---|---|---|---|---|
| 1999-2007 | 1.7425%/mo | 0.2325 | **1.4416** | +1.510 | **2.349** | **+0.301** | **0.464** |
| 2008-2015 | 1.9931 | 1.0428 | 1.6586 | +0.950 | 1.807 | +0.334 | 0.644 |
| 2016-2024 | 1.6196 | 1.6420 | 1.5851 | −0.022 | −0.028 | +0.035 | 0.044 |

Against an EW market **there is no decay because there was never anything to
decay** — all three eras are flat and insignificant. The 1999-2007 t of 2.349 is
substantially the EW-beats-VW regime of that decade (EW 1.44%/mo vs VW 0.23%/mo,
a 1.21 pp/month gap that never recurs).

This is precisely the trap the same document catches itself in **one section
later**: FINDING 7 says *"`learner/dataset.py` states the rule this broke — an EW
benchmark is a size artefact… and the test had built the artefact into its own
benchmark"*, and fixes W6b by putting the same weighting on both legs. That fix
was never applied to the headline. The `above_the_band` control that caught it in
W6b has no counterpart in W9/W10.

**The counter-evidence, reported because it cuts the other way:** the
size-matched control (same weights, random name from the same within-month
cap decile, 10 seeds) gives era diffs of **+1.49%/mo t 2.30 / +0.88 t 1.70 /
+0.09 t 0.12**. So a *cap-matched* reading keeps the decay ordering and keeps E1
alive; an *EW-market* reading kills all three eras. The honest statement is that
**the decay is real relative to cap-matched peers and absent relative to an
equal-weighted market**, and the doc's flat assertion "it worked for 17 years and
has been dead for 9" is one of those two readings presented as the only one.

Note also that E3 (2016-2024) is the era with **6.6 split-contaminated holdings
per month against 1.1 in E1** (see claim 1). Cleaning the contamination lifts
E3's t from −0.028 to +0.066, and with a $5 floor to +0.464. The measured "death"
is partly a data-quality gradient running the *opposite* way to the effect.

### What would settle claim 2

Print the book's excess against **three** legs in the same table — VW market,
EW market, and a cap-matched random draw — and let the reader see that the answer
depends on which. Then re-run W10 through the runner so it has a receipt.

---

## CLAIM 3 — the FM t of +4.15 that lost money: **WOUNDED** (core right, detail wrong)

The general lesson — an FM beta is an equal-weighted whole-cross-section average
slope and a top-50 VW book is a cap-weighted extreme tail — is correct and worth
the weekend. Three specific things in Step 3 do not hold.

**(a) The decile row is a pooled name-month mean, and d10's sign flips without
it.** `evaluate.decile_table` (`learner/evaluate.py:109-133`) cuts bins per month
(correct) but then reports `chunk[y_col].mean()` over **all name-months in the
bin** with no per-month aggregation and no standard error. On 672,454
name-months / 309 months:

| decile | doc / pooled % | **one obs per month** % | t | | decile | pooled | per-month | t |
|---|---|---|---|---|---|---|---|---|
| d1 | −0.619 | **−0.456** | −1.71 | | d6 | +0.182 | +0.250 | +2.24 |
| d2 | −0.047 | +0.051 | +0.26 | | d7 | +0.105 | +0.158 | +1.29 |
| d3 | +0.179 | +0.267 | +1.69 | | d8 | +0.089 | +0.172 | +1.13 |
| d4 | +0.089 | +0.184 | +1.44 | | d9 | +0.061 | +0.159 | +0.84 |
| d5 | +0.171 | +0.231 | +1.99 | | **d10** | **−0.032** | **+0.098** | +0.37 |

The pooled column reproduces the doc exactly. **d10 changes sign** between the
two aggregations, and d10 is the decile the whole argument rests on. This is
`feedback_name_days_are_not_periods` in the receipt the doc uses to teach a
methodological lesson.

**(b) "d10 is the one region where the signal is worthless" is not measurable.**
Paired monthly differences:

```
d10 − d1            +0.5533%/mo   t +3.963
d1  − mean(d3..d9)  −0.6584%/mo   t −3.829   <- the claim that holds
d10 − d5            −0.1335%/mo   t −0.673
d10 − d3            −0.1695%/mo   t −1.015
d10 − mean(d3..d9)  −0.1051%/mo   t −0.615   <- the claim that does not
```

"The effect lives in decile 1" is supported at t −3.83. "d10 is worse than d3-d9"
is t **−0.615** and is being read off unstarred point estimates.

**(c) The decile shape is largely a size/liquidity U, and the doc's own W7b
language applies.** Median `log_dollar_vol_20d` by decile of
`cp_iv_spread_30d`: d1 **15.04**, rising to d5-d6 **≈17.44**, falling to d10
**14.85**; median log cap 20.01 → 22.18 → 19.95. **Both tails are the small,
illiquid corner.** FINDING 3 rejects features whose winner and loser sides move
the same way ("a statement about being extreme, not about being right"); the same
reading applies here and is not made. A long top-50 VW book does *not* "live
entirely in d10" in any meaningful economic sense — it lives in the large names
inside d10, which is a different set again.

On the fairness question asked in the brief: the decile table and the book **do**
use the same universe (both are `df` after `FO.attach`, dropna on the signal), so
that is not the discrepancy. The discrepancy is weighting and aggregation, which
is what the doc says — it just over-claims the shape's precision.

---

## CLAIM 4 — S28's band replicates as a FLOOR: **SURVIVES the tail attack**

The standing worry (35 rows of 46,361 carrying 81% of a result) does not apply.
Below-$100k/day bucket, 64,761 name-months, 309 months, median **197 names/month**
(min 15, max 475 — only **one** month has fewer than 20 names):

```
full                          -2.58%/yr   t -0.926   median monthly diff -0.239% (mean -0.215%)
drop 1  largest-|diff| month  -3.33%/yr   t -1.239
drop 3  largest-|diff| months -4.41%/yr   t -1.697
drop 5                        -4.40%/yr   t -1.737
drop 10                       -4.10%/yr   t -1.703
months with >=20 names        -2.93%/yr   t -1.059  (308 of 309)
```

Removing the extremes makes it **more** negative, the median tracks the mean, and
the sign is stable across eras (−2.49 / −2.55 / −2.70 %/yr). **Not a tail
artefact, not a thin-month artefact.** And it strengthens under the repo's own
price hygiene: with `close ≥ $2` (the `has_opinion` floor) it is **−6.23%/yr,
t −2.40**; at `close ≥ $5`, −4.37%/yr t −1.62. If anything the doc understated it.

**Where the doc over-writes:** "clear as an *exclusion*" describes a t of −0.93
whose per-era t's are **−0.588 / −0.463 / −0.561** — no era anywhere near 2, and
53.4% of months negative, which is a coin flip. And the actionable sentence
— *"the repo already carries `evaluate.TRADABLE_DOLLAR_VOL = $3,000,000`, which
is well above where the damage actually is"* — reads as an argument for lowering
a live safety floor on the strength of a t of −0.93. The $2-floor recomputation
above (t −2.40) is the version that could support that sentence, and it is not in
the doc.

---

## CLAIM 5 — five features died under their own controls: **SURVIVES**

The over-control objection is the right question and the answer is no, at least
for the headline case. Monthly FM on 880,417 rows / 309 months, all regressors as
within-month percentile ranks, y = `excess_vw_1m`:

```
X = [prox_52w_high, mom_12_1, log_market_cap, vol_60d]
  prox_52w_high    beta -0.006130   t -1.329     <- reproduces the doc's -1.33
  mom_12_1         beta +0.012230   t +3.934
  log_market_cap                    t -1.157
  vol_60d                           t -1.765

X = [mom_12_1, log_market_cap, vol_60d]        -> mom_12_1     t +2.113
X = [prox_52w_high, log_market_cap, vol_60d]   -> prox_52w_high t +0.479
```

Mean within-month rank correlation of the two is **0.607** — high, but the
regression is not degenerate, and the test that decides over-control is
symmetric: **momentum's t goes UP (2.11 → 3.93) when `prox_52w_high` joins**,
while `prox_52w_high`'s own t without momentum is only **+0.479**. Momentum
absorbs the 52-week high; the 52-week high does not absorb momentum. On this
universe the doc's reading is right and it is not an artefact of removing the
mechanism along with the confound.

### One latent code bug found while checking it

`scripts/weekend_lab_jobs.py:728-729`:

```python
ic = pd.Series(ics, index=sorted(d["month"].unique())[:len(ics)])
be = pd.Series(betas, index=ic.index[:len(betas)])
```

`ics` is appended only inside `if len(g) < 30: continue`, but the index is the
**first** `len(ics)` sorted months. Any skipped month silently shifts every
subsequent IC and beta onto the wrong month, and `era_sign_table(be)` then
assigns them to the wrong era. Likewise `betas` can be shorter than `ics` when
`lstsq` raises, and the truncation drops the **last** months rather than the
failing ones. **On this panel the bug is latent — I measured 0 months skipped**
(the thinnest year, 1999, still averages ~2,000 names/month). It becomes live the
first time this code meets a thin panel or a feature with sparse coverage, and it
would produce a clean, wrong era table. Report only; not fixed, per the file
ownership rule.

---

## THINGS THE DOC SAYS THAT THE RECEIPTS DO NOT

1. *"DSR over the 24-cell family is 0.529"* — the family is 24 in the **receipt**
   and 277 in the **code**, and the code's own comment explains why 24 is wrong.
2. *"a line with no receipt is not in this file"* — §0.1's whole table has no
   receipt under `backend/data/optimus/weekend_lab_2026-09-06/`.
3. FINDING 3's table (W7 v0) does not contain `target_rev_1m__xs`, the feature
   §0 is built on. The provenance of the headline feature is never stated.
4. §5 lists W7 as *"re-running with the corrected overlap t"* and W2 as *"first
   pass in flight"*; both are true, but §0's headline consumes W7 output, so the
   headline is downstream of a job the doc itself marks as still moving.

## THINGS THAT HELD UP UNDER ATTACK, EXPLICITLY

- Every headline figure in §0 and §1 that I recomputed reproduced to four
  decimals. The lab's arithmetic is not in question.
- PIT discipline on `target_rev_1m`: clean.
- Delisting/survivorship on the headline book: 0.80% of selections, conservative
  fill.
- The era boundaries: constants in the panel builder, not tuned.
- The `random control` design in W5c and the `above_the_band` control in W6b are
  both genuinely load-bearing and both caught real errors. The missing one is the
  same control on the headline.
- FINDING 1 (`vwap_60d_gap` split artefact) and FINDING 8 (`holds_in_2_of_3` sign
  bug) are both real self-catches and both correctly described.

## RANKED NEXT MOVES

1. Re-run W9 on the code on disk; publish `n_trials_used_for_the_DSR`. If DSR
   ≈ 0.20, retitle §0.
2. Replace `split_era_share_basis_gate`'s gap test with a level test, and prove
   it by injecting `ratio_adj_check / cfacpr` and requiring FAIL.
3. Null `target_rev_1m`/`target_rev_3m` across a `cfacpr` move; re-issue.
4. Add the EW-market and cap-matched-control rows to §0 and §0.1.
5. Re-run W10 through the runner so it has a durable receipt.
6. Downgrade "clear as an exclusion" (claim 4) or re-issue it at the $2 floor.
