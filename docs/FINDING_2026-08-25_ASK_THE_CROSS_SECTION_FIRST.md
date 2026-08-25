# The farm was asking the portfolio question before the signal question

**2026-08-25 · licence: `PRODUCT_EXPERIMENT` (exploration) · instrument change + first results**

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs market | unchanged this session (no new replay run) |
| best forward paper strategy | unchanged — **no new forward book launched yet** |
| **independent selector count** | **3 data sources joined** (`crsp.dsf` · `finratio` · **`ibes`**, new). Selectors clearing the cross-section check on 32 years, one per source: `profit_roe` (ic_t 4.18) · `rev_dispersion` (3.14) · `mom_12_1` (2.17), plus `sell_side_state` (2.64) and `rev_breadth` (2.03). **None is trading paper yet.** |
| farm candidates tested / promoted | **23 registered signals** (19 real + 4 explicit baselines) diagnosed on two windows / **0 promoted** |
| new actionable finding | **YES — three, below** |
| external execution drag | not measured this session |
| LLM spend | $0 (no LLM call made) |
| **RESULT IMPROVEMENT** | **NONE in realised P&L.** The change is that the farm can now tell a weak signal from a wrecked one. |

---

## 1. The defect: four questions entangled in one number

Every farm result to this date was produced by one chain —

```
characteristic -> rank -> top-k long-only book -> compare to a benchmark
```

— and then read as a statement about the **characteristic**. It is not one. That
chain entangles four things, and when the answer disappoints, nothing in the
output says which of them ate it:

1. **signal quality** — does forward return move with the score?
2. **portfolio construction** — does top-10-of-500 capture it, or destroy it?
3. **factor exposure** — is the book long size/age/sector by accident?
4. **benchmark choice** — better than *what*?

Point 4 was closed on 2026-08-25 by `portfolio_farm_paired_power`. Points 1–3
are `backend/services/portfolio_farm/diagnostics.py`, added here:
rank IC over **non-overlapping** dates, a quantile curve with a monotonicity
score, top-minus-bottom spread, turnover, and a holdings census whose age and
size percentiles are measured **against the eligible set on each date**.

Run it with `python -m scripts.portfolio_farm_diagnose`.

## 2. `equal` was never an equal-weight book

`equal_universe` scored every eligible name `0.0`. With every score tied,
`top_k` falls through to the stable sort's tie-break, which is **permno order**,
and CRSP assigns permnos roughly in listing order. The farm's "equal" control
was therefore **the k oldest surviving eligible listings**.

The docstring had said so since it was written. That was not enough, because
the *leaderboard* prints the name. So

> "nothing beats `equal`"

read as *nothing beats a dumb equal-weight portfolio* and actually meant

> **ROE and momentum cannot be distinguished from a particular listing-age
> exposure**

which is narrower, more useful, and the statement that turned `profit_roe`'s
31-year requirement into 126.

It is now `oldest_listing`, scored explicitly as `-permno`; `newest_listing` is
the opposite-tail control the canon requires. The rename is **holdings-identical**
— verified, not asserted — but only because `Panel.permnos` is ascending. Hand
the old version a differently-ordered panel and it silently selects something
else, with nothing in any receipt reading differently. That is the argument for
declaring a baseline's score rather than inheriting it:
`test_the_old_tie_break_was_only_the_oldest_BY_ACCIDENT`.

`Policy(signal="equal")` is now **refused** and names its replacement. Refused
rather than silently resolved: a `Policy` is a frozen hashed strategy record,
and rewriting its signal field would produce a policy whose hash no longer
matches the receipt it came from.

## 3. What the cross section actually says

`h=21`, `k=20`, 5 buckets, non-overlapping formation dates, next-open to
next-open total returns.

> All tables below were REGENERATED after two late corrections — `diagnostics`
> now builds its trailing-dollar-volume series with the same `min_obs=5` as
> `replay` (it had used 10, a stricter eligible set than the book trades), and
> the `rev_breadth` plausibility bound was widened (§4b). Numbers here are the
> post-fix run; receipts:
> `signal_diagnostics_1993_2024_2026-08-25T070533Z.json` and
> `..._2013_2024_..T070047Z.json`.

### 1993–2024 (32 years, `--reduce`, h=21, k=20)

| signal | ic_t | mono | t−b %/yr | names/slot | turn% | age% | size% |
|---|---|---|---|---|---|---|---|
| **profit_roe** | **4.18** | 0.90 | +5.05 | 25.1 | 16.7 | **51.1** | **52.8** |
| **rev_dispersion** | **3.14** | 0.60 | +3.86 | 29.1 | 41.4 | 47.1 | 54.0 |
| **sell_side_state** | **2.64** | **1.00** | +3.04 | 78.9 | 95.3 | 55.0 | 41.4 |
| **mom_12_1** | **2.17** | **1.00** | +8.54 | 73.1 | 40.2 | 61.9 | 25.9 |
| **rev_breadth** | **2.03** | **1.00** | +2.77 | 72.5 | 94.7 | 53.4 | 45.0 |
| illiquid | −2.64 | −0.30 | −2.95 | 130.0 | 75.9 | 62.0 | 6.0 |
| size_large | 2.30 | 0.10 | +1.41 | **3.6** | 5.1 | 31.2 | 97.9 |
| value_bm | −1.22 | **−0.90** | −2.28 | 26.0 | 25.1 | 45.6 | 45.1 |
| liquid | 0.12 | −0.70 | −0.98 | 13.8 | 18.9 | 40.0 | 90.7 |
| *random* | −0.08 | −0.30 | −1.03 | 83.7 | 96.5 | 50.2 | 50.5 |
| *random_persistent* | 0.06 | 0.40 | +1.80 | 11.1 | 15.4 | 58.1 | 39.3 |
| *oldest_listing* | 0.67 | 0.60 | +1.81 | 6.2 | 11.0 | **1.9** | 60.3 |
| *newest_listing* | −0.67 | −0.70 | −1.78 | 48.6 | 27.4 | **97.9** | 41.0 |

**Five signals clear the cross-section check**, and they sit on three different
data sources. The random family is at the noise floor (|ic_t| ≤ 0.08), which is
where it should be.

The baselines validate the instrument: `oldest_listing` reads age% 1.9 and
`newest_listing` 97.9, exactly as declared.

**Three findings.**

**(a) I HYPOTHESISED AN AGE CONFOUND AT `k=100` AND THE TEST REFUTED IT.**

The hypothesis was: `profit_roe` is age-neutral at `k=20` (age% 51.1), so the
126-year requirement against the age book must come from the `k=100` book
reaching deep into the large-old corner of a 500-name universe. I wrote down
the discriminating prediction before running it — *"if it stays near 50 at
k=100, then the 126-year result has some other cause and this explanation is
wrong"* — and ran it:

| k | `profit_roe` age% | `oldest_listing` age% |
|---|---|---|
| 20 | 51.1 | 1.9 |
| **100** | **49.5** | 9.9 |

**It stayed at 49.5. The explanation is wrong and is withdrawn.** At `k=100`
`profit_roe` holds names of almost exactly median age for its eligible set,
nowhere near the age book's 9.9. The two books hold genuinely different names.

**What the 126 years actually is.** It is power arithmetic on a small excess,
not evidence of a confound. `paired_power` measured `profit_roe` at `k=100`
clearing the age book by **+1.53%/yr** against a **6.11%** paired tracking
error, and `(2.8 × 6.11 / 1.53)² = 125`. The figure says *this sample cannot
resolve a difference that small*, which is a statement about the size of the
edge and the length of the record — not about what the book is made of.

**So the real tension is sharper, and it is the whole reason this module
exists:** `profit_roe` has the strongest cross-sectional evidence in the
project's history (`ic_t = 4.18`, monotone 0.90, 32 years of non-overlapping
dates) and a **weak book** (+1.53%/yr over a named alternative). A strong
signal and a weak long-only top-k implementation of it are entirely
compatible, and every previous farm result collapsed them into one number.
**The open question is construction, not confounding** — a long-only top-k
slice is capturing very little of a signal that demonstrably orders the whole
cross section.

*(Note: `ic_t`, `mono` and `t−b` are identical at k=20 and k=100 by
construction — they are cross-sectional and do not depend on `top_k`. Only the
census columns move with `k`. That is correct behaviour, not a null result.)*

**(b) `value_bm` fails monotonically in the WRONG DIRECTION** (−0.90). That is
not a weak signal — it is a consistent one pointing the other way.

A negative value effect over 32 years is exactly the kind of result that should
be suspected of being a broken join before it is believed, because HML is among
the most replicated anomalies there is. **So the characteristic was calibrated
against known facts rather than assumed**, and it passes:

| check | expected | measured |
|---|---|---|
| `bm` median | ~0.5 | **0.499** |
| market cap across bm quintiles | falls (value is smaller) | **monotone falling, q0 → q4** |
| highest-bm industries | banks, insurers, heavy industry | **MONEY, HLTH, OTHER, BUSEQ, MANUF** |
| lowest-bm industries | biotech, tech | **HLTH, BUSEQ, SHOPS** |

The join is sound and the sign is right. So the negative reading is a fact about
**this universe and this construction**, not a bug: the farm screens to the
top-500 by dollar volume, which is essentially large caps, and HML in large caps
since 1993 has been weak to negative — while extreme top-k within it selects
distressed financials. The implication is concrete: **the reversed signal is the
one with a monotone positive cross section here**, and this is the shape a
`FARM_CALIBRATION_BATTERY` should take for every characteristic before a novel
result from it is trusted.

**(c) `liquid` is dead outside its decade.** `ic_t` 0.09 and monotonicity −0.60
on 32 years, against the best t on the 2013–2024 grid. It was a description of
a mega-cap decade, and the census (`names/slot` 13.6, size% 90.8) says so
without any statistics at all.

Note also `size_large`: `ic_t = 2.35` on **3.6 distinct names per slot**. That
is a static mega-cap list, and the census is the only column that says so.

### The window disagrees with itself, again

On 2013–2024 `mom_12_1` reads `ic_t = 0.70` and non-monotone; on 32 years it is
`2.17` and **perfectly monotone**. The 12-year window has now reversed a farm
verdict three separate times (holding period, breadth, and now the cross
section). It should not be used to close anything.

## 4. The third data source is joined: analyst state

`backend/services/portfolio_farm/revisions.py`. `ibes_consensus_monthly` and
`ibes_consensus_monthly_early` were already on disk for **both eras** with
`permno` joined — 5.2M rows, no linkage step, no new pull. EPS, `fpi='1'` (FY1).

Registered as components **and** a composite, never composite-only — that is
the `arena_composite` lesson as code (six declared weights that turned out to
be 12-1 momentum for 99.5% of names, invisible because only the composite was
reported):

| | |
|---|---|
| `rev_breadth` | `(numup − numdown) / numest` — bounded, no denominator pathology |
| `rev_magnitude` | consensus change, floored at $0.10 to kill the rounding grid |
| `rev_dispersion` | `−stdev/|meanest|` — **negated so high = agreement**, sign declared before any result |
| `sell_side_state` | equal-weight cross-sectional z of the three |

**1993–2024, h=21, k=20** (2013–2024 in brackets, to show the window
disagreeing with itself a fourth time):

| signal | ic_t | mono | t−b %/yr | turn% | age% | size% |
|---|---|---|---|---|---|---|
| **rev_breadth** | **2.03** *(1.62)* | **1.00** *(0.90)* | +2.77 | 94.7 | 53.4 | 45.0 |
| rev_magnitude | 1.12 *(1.25)* | 0.40 *(0.70)* | +0.77 | 88.9 | 54.5 | 37.2 |
| **rev_dispersion** | **3.14** *(2.10)* | 0.60 *(**0.10**)* | **+3.86** | **41.4** | 47.1 | 54.0 |
| **sell_side_state** | **2.64** *(2.08)* | **1.00** *(0.90)* | +3.04 | 95.3 | 55.0 | 41.4 |

The composite and two of its three channels clear the cross-section check on
32 years, and all four are **neutral on both confound axes** — not age books,
not size books. That is what a genuinely independent selector should look like.

**The calibration fix in §4b moved these numbers, and it moved them UP**, which
is the confirmation that the 16,024 dropped rows were the informative ones:
`rev_breadth` went `ic_t` 1.90 → **2.03** (crossing the bar it had been failing)
and `sell_side_state`'s monotonicity went 0.70 → **1.00**. A filter on the
most-revised names was costing the signal exactly what it was built to capture.

**`rev_dispersion` is the strongest tradeable candidate on the board**, and it
is the one the 12-year window would have thrown away: `ic_t` 2.10 → **3.14**,
monotonicity **0.10 → 0.60**. On 2013–2024 it read as "high t, no ordering —
one bucket did everything", which is a correct description of that window and a
wrong description of the signal. Its turnover is **41%**, less than half the
other analyst channels', which is what makes it the candidate most likely to
survive costs.

`rev_magnitude` is the weakest, exactly where the module's own docstring said to
distrust it first (IBES restates per-share estimates for splits, so a month-on-
month consensus change can be a corporate action). Declaring that before the
measurement is why the number is now interpretable rather than puzzling.

**Two caveats, stated before the result is used, not after:**

- **turnover is ~95%/month for breadth and the composite.** Those
  top-minus-bottom figures are **gross**. At 6 bps plus slippage the composite's
  +2.74%/yr could plausibly be eaten entirely, and that must be measured in a
  replay before any claim. `rev_dispersion` at 41% is the exception and the
  reason it leads.
- IBES summary data restates for splits and rounds small estimates.
  `rev_breadth` is immune (it counts analysts); `rev_magnitude` is not. Both
  are documented in the module rather than repaired.

### The milestone, stated precisely

Three selectors clear the cross-section check on **three different data
sources**:

| selector | source | ic_t (32y) | mono | age% | size% | turn% |
|---|---|---|---|---|---|---|
| `profit_roe` | `finratio` (accounting) | 4.18 | 0.90 | 51.1 | 52.8 | 16.7 |
| `rev_dispersion` | `ibes` (analyst behaviour) | 3.14 | 0.60 | 47.1 | 54.0 | 41.4 |
| `mom_12_1` | `crsp.dsf` (price) | 2.17 | 1.00 | 61.9 | 25.9 | 40.2 |

That is the **precondition** for `ALPHA_STACK_EQUAL_RISK_v1`, not the delivery
of it. None of the three is trading paper money, and the cross-section check is
not a licence — it is evidence that the next hour is worth spending.

## 3b. WHY A STRONG SIGNAL MAKES A WEAK BOOK — the deciles answer it

Finding (a) left the question *why does `ic_t 4.18` produce +1.53%/yr?* The
quantile curve answers it directly. Annualised %/yr by decile, 1993–2024,
h=21:

| signal | d1 … d10 | shape |
|---|---|---|
| `profit_roe` | 9.5 8.2 9.3 9.3 **13.2 13.6 14.8 14.8 14.3 14.4** | **STEP** |
| `mom_12_1` | 6.7 8.3 10.0 9.6 12.1 12.6 14.0 14.3 14.1 **19.2** | **TAIL** |
| `rev_dispersion` | 10.2 10.9 12.0 14.1 11.5 12.3 11.1 10.4 10.6 **19.0** | **TAIL** |
| `sell_side_state` | 8.6 12.0 8.8 12.5 13.8 13.0 **14.7** 12.0 12.9 14.4 | noisy |
| `oldest_listing` *(baseline)* | 10.9 12.1 12.0 11.7 12.9 *(quintiles)* | flat |

**`profit_roe`'s information is a STEP, not a gradient.** Below the median it
earns ~9%/yr; above it, a **plateau at 14.3–14.8** that is flat from decile 7 to
decile 10. Deciles 7 and 8 (14.8) are *better* than decile 10 (14.4).

A top-k=20 book out of 500 is the **top 4%** — buried inside decile 10, on the
flattest part of the curve. **Concentrating buys tracking error and no
return.** That is the whole explanation for a 4.18 signal producing a +1.53%/yr
book, and it is a construction fact with a concrete fix: **build `profit_roe`
WIDE** — the top 30–40%, not the top 4%.

This also supplies the missing MECHANISM for the standing "breadth is the cheap
lever" finding. `MDE = z·te/√T`, te falls from 34% at k=10 to 16.4% at k=50, and
if return is *flat* across the top four deciles then widening `k` cuts the
denominator of the t-statistic **at no cost to the numerator**. Breadth was
argued from Grinold; here it is measured.

**Momentum is the control that makes this legible.** Its decile 10 jumps to
19.2 from 14.1 — its money *is* the extreme tail, so a narrow book is correct
for it, which is why it clears the age book by +9.23%/yr on a *weaker* `ic_t`
(2.17 vs 4.18). **Ranking signals by `ic_t` alone would have got this exactly
backwards.** Signal strength and correct construction are different axes.

### Two consequences I did not expect

**1. `sell_side_state` DILUTES the one channel that pays.** Top-decile lift over
the mean of the other nine:

| | top decile | other nine | **lift** |
|---|---|---|---|
| `mom_12_1` | 19.2 | 11.3 | **+7.9** |
| `rev_dispersion` | 19.0 | 11.4 | **+7.6** |
| `profit_roe` | 14.4 | 11.9 | +2.5 |
| **`sell_side_state`** | 14.4 | 12.0 | **+2.3** |

The equal-weight z-composite has **a third of `rev_dispersion`'s lift**.
Averaging a tail-concentrated signal against two gradient signals washes the
tail out. **Ship `rev_dispersion`, not the composite** — and treat this as a
direct warning for `ALPHA_STACK_EQUAL_RISK_v1`: equal-risk combination is not
free when the components have different SHAPES, and the fixed-weight stack has
to be checked against its own best component, not only against the market.

### The shape classifier across all 23 signals

Run over the whole registry at deciles (receipt
`signal_diagnostics_1993_2024_..T073954Z.json`), one structural pattern falls
out that no single-signal reading would have shown:

| family | shape | signals |
|---|---|---|
| **price momentum** | **TAIL**, every member | `mom_12_1` (+7.9) · `mom_12_0` (+6.2) · `trend_200` (+5.5) · `mom_6_1` (+4.4) |
| **fundamental / analyst level** | **STEP or GRADIENT** | `profit_roe` (step) · `rev_breadth` (gradient) · `sell_side_state` (gradient) |
| **analyst disagreement** | **TAIL** | `rev_dispersion` (+7.6) |
| reversed / absent | **flat** | `value_bm` · `illiquid` · `size_small` · `high_vol` · `liquid` · `size_large` |

**Price momentum pays in the extreme tail; fundamental level pays as a step.**
That is a construction rule for a whole family rather than one signal, and it
says the two kinds of selector should not be built the same way — which is
exactly what a fixed equal-risk stack would do to them.

**The instrument calibrates itself again: all four baselines read `flat`**
(`random`, `random_persistent`, `oldest_listing`, `newest_listing`). A shape
classifier that assigned a shape to a coin flip would be worthless, and this is
the cheapest possible check that it does not.

**SHAPE IS NOT STRENGTH.** `rev_magnitude` classifies `tail` on a lift of
**+0.94%/yr** — the curve's *form* is tail-like and there is almost nothing in
it. `shape` says how to build a book *if* the signal is worth building;
`ic_t` and `lift` say whether it is. Quoting shape alone would be the
`arena_composite` mistake in a new costume.

**2. My monotonicity criterion penalises tail signals, and that is my bug.**
`rev_dispersion` reads monotonicity **0.236** at ten buckets — which prints as
"no signal" — while carrying the second-largest lift on the board. Monotonicity
answers *does the score order the whole cross section*; it cannot see a payoff
that lives entirely in the last bucket. `diagnostics` now reports
`top_bucket_lift_annual_pct` and a `shape` (`tail` / `gradient` / `flat`)
beside it, the verdict no longer fails a tail signal for lacking monotonicity,
and `implied_construction` states narrow-vs-wide directly. Pinned by
`test_a_TAIL_signal_is_not_failed_for_lacking_monotonicity`.

## 4b. The calibration battery, and the second bug it found in my own work

`python -m scripts.portfolio_farm_calibrate` — reproduce known facts about
known factors before trusting a novel result. Not exact factor returns
(universes and conventions differ, and a battery demanding Fama-French's
numbers would fail for reasons that say nothing about this data), but the
coarse facts a correct join cannot violate.

**It failed on its first run, on `rev_breadth`, and the bug was mine.** I had
bounded breadth at |1| reasoning from the formula that `numup + numdown` cannot
exceed `numest`. The data disagreed:

    numest 7,  numup 12,  numdown 0   ->  breadth 1.71

`numup`/`numdown` are a **FLOW** — revisions filed during the period — and
`numest` is a **STOCK**, the estimates standing now. An analyst may revise
twice; revising analysts may since have dropped coverage. Measured over
1,051,457 rows: **1.52% exceed |1|, 0.025% exceed |2|, and nothing exceeds |5|.**

So the bound was silently discarding 16,024 rows — and not a random 1.52%, but
**precisely the names with the most revision activity, which are the most
informative observations the signal has.** The signal still "worked", its
leaderboard row looked entirely ordinary, and nothing else in the system could
have noticed. The bound is now (−5, 5), chosen because zero rows exceed it.

**A bound asserted from a formula rather than measured from the data is a
filter, and a filter on the informative tail is invisible.**

The value checks pass, which is what makes `value_bm`'s negative cross section
interpretable rather than suspect. Battery now 12/12.

## 5. One defect found in my own work, and it is the session's own shape

`signals.zscore` returned **zeros** for a row with nothing to standardise. Every
name then scores identically, `top_k` falls through to the permno tie-break, and
the composite **silently becomes `oldest_listing`** on exactly the dates where
the signal had no data — the hardest place to notice it, and a live path because
IBES coverage is thin at the window's edges.

That is the `equal` defect again, one level down, introduced by me while fixing
the first one. It now returns NaN — not selectable — and `sell_side_state`
additionally requires all three channels present per name. Pinned by
`test_an_all_nan_date_scores_NOTHING_rather_than_tying_every_name`.

## 6. What did NOT change

- No forward book was launched. **Demonstrated edge remains 0%.**
- No replay/terminal-wealth number was recomputed. Everything above is
  cross-sectional; the top-k books are unmeasured at `k=20` post-rename.
- The `PRODUCT_EXPERIMENT` verdict in `diagnostics._verdict` is **advisory and
  says so in its own payload**. It governs what may be CLAIMED and what
  deserves the next hour — never what may be tested in paper. A gate here would
  recreate the 24-month paralysis under a new name.

## 7. What follows

1. `QUALITY_RESIDUAL_v1` — the enabling re-pull
   (`scripts/wrds_repull_finratio_early.py`, keyed on **columns** not existence)
   widens the early era from 5 columns to the full ~100, which is what makes
   age/size/industry neutralisation testable before 2013 at all.
2. Re-run the holding-period and breadth grids at `k=20` with the renamed
   baselines.
3. Measure `sell_side_state` **net of costs** in a replay. Its turnover is the
   open question, not its IC.
4. Reverse `value_bm` and diagnose it; the −0.90 monotonicity is a result, not
   a null.
