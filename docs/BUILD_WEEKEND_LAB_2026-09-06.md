# WEEKEND LAB — 2026-09-06/07 — did nineteen years say what seven could not?

*Written continuously by the lab, not at the end. Numbers are re-checked against
their receipts before each update; a line with no receipt is not in this file.*

---

> ## CORRECTIONS — read these before anything below
>
> Two adversarial review lanes were run against this document's own claims. They
> found a leak, a guard that could not fail, and a circular flag. **Three things
> in this file changed as a result, and the earlier versions were wrong.**
>
> **1. FINDING 3's headline archetype was a LEAK.** W7's control pool excluded
> future *losers* as well as winners, which made "being a control" a statement
> about the future. Any feature predicting outcome **dispersion** then differs
> from winners by construction — and the published #1 archetype,
> `log_dollar_vol_20d` ("thinly traded for its size", Holm p 0.000178), is
> exactly a dispersion proxy. **Fixed** — each side now excludes only its own
> tail. `log_dollar_vol_20d` falls to t −2.76, Holm **0.158**: it does not
> survive. The analyst-revision cluster survives and gets *stronger*
> (`net_rev_4w` Holm 0.063 → **0.0047**). **The corrected archetype is "being
> upgraded", not "unloved and illiquid."**
>
> **2. The early-era share-basis gate could not go red.** The reviewer injected
> the exact 2026-09-04 defect and the gate still returned PASS. The corruption
> travels through `cfacpr(t)` (forward) while the treatment arm is
> `split_prior_year` (backward), so 84% of corrupted rows land in the *control*
> and a difference test cancels it. **Fixed** — the gate now tests the level and
> **proves its own sensitivity on every run** by injecting the defect into a copy
> (real 0.9783 vs injected 0.8545, floor 0.95 separates them). The panel was
> always fine; the *evidence* that it was fine is only now real.
>
> **3. `powered` was the t-test written longer.** `years_needed ≤ years_observed`
> reduces algebraically to `t ≥ 2`, so `CANNOT DETERMINE (underpowered)` fired
> for every arm with 0 < t < 2 and **NOISE was unreachable** — across 19
> receipts. **Fixed** — power is now measured against a pre-specified 3%/yr
> effect at the arm's own volatility, and the receipt reports the **Minimum
> Detectable Effect**. The honest number is sobering: a top-50 book over 21 years
> at realistic volatility has an **MDE of ~7.4%/yr**.
>
> Also fixed: 25 of 92 verdicts said `NOVEL` while bypassing the bar this repo
> defines (screens now have their own vocabulary and can never reach NOVEL); the
> evidence memory stamped a *fabricated* DSR on screen rows and then sorted on
> it; and W7 stamped the wrong months onto any feature with incomplete coverage.
>
> **And one number below is not what it looked like:** the neural arm's terminal
> wealth of **561×** is ~94% microcap. At the repo's own `TRADABLE_DOLLAR_VOL`
> floor of $3m/day it is 92.8×, and with a $5 price floor as well it is **36.3×
> at t 1.98**. Its median holding without a floor closes at **$6.61** and trades
> **$1.03m/day**; 18% are under $2.
>
> The full reports are `docs/REVIEW_2026-09-06_ATTACK_ON_THE_WEEKEND.md` and
> `docs/REVIEW_2026-09-06_CODE.md`.

---

## RESULTS SCOREBOARD (the house rule: this block comes before any code count)

| | |
|---|---|
| **Best historical net strategy vs the market** | **none clears any bar.** The 26-year learner grid's best cell is +11.45%/yr at **t 1.43**, DSR **0.293** against a 0.95 bar. The one book that reached t > 2 unfloored falls to **t 1.68** once restricted to names anyone could buy, and 54% of it is five months. Every options-book cell loses *gross*. |
| **Best forward paper strategy** | unchanged; the lab placed no orders and touched no book |
| **Independent selector count** | unchanged — nothing was promoted |
| **New actionable finding** | **YES — six, below** |
| **External execution drag** | not measured this weekend (no orders) |
| **LLM spend** | **$0.00** — no LLM call was made |

**The verdict census across all 83 current receipts:**

| verdict | count |
|---|---|
| CANNOT DETERMINE (underpowered) | 29 |
| NOISE | 23 |
| INVENTORY | 18 |
| SCREEN_SURVIVOR | 6 |
| DEFERRED | 5 |
| AUTOPSY | 1 |
| DECAYED (worked, then stopped) | 0 *(the one that said so is retracted in §0: graded on the tradable book it is CANNOT DETERMINE, DSR 0.127)* |
| **NOVEL** | **0** |

**Nothing this weekend reached NOVEL.** An earlier count of 21 did, and every one
of them was a feature screen wearing a word defined for a book — see
`_superseded_old_verdict_vocabulary/`.

**RESULT IMPROVEMENT: NONE in return terms.** No strategy was promoted and none
was killed. What moved is the *instrument*, one dated fact, and what we know
about the *method*:

1. the panel is **2.2× longer in months** (143 → 310), which is the quantity that was actually scarce;
2. **the one result that looked powered did not survive being made tradable** (§0) — it is a tail-driven, early-era effect: 54% of its excess is five months, and without them it is +3.13%/yr at t 0.84;
3. **five published features died under their own controls** — the 52-week high, single-day attention, ATM implied vol, IV-minus-realised-vol, and a VWAP gap that was a split artefact;
4. **a Fama-MacBeth t of +4.15 produced a book that loses gross**, and the decile table says exactly why. That one applies to every feature screen in this repo.

---

## 0. THE HEADLINE, AND ITS RETRACTION

> **RETRACTED IN ITS ORIGINAL FORM.** What follows below was written against the
> **unfloored** book on the **pre-fix** panel. Both were wrong, in opposite
> directions, and the corrected version is much weaker. The section is kept
> because the reasoning is still the reasoning; the numbers it was built on are
> superseded by this box.
>
> Two things changed after it was written. `dataset.build`'s target-revision legs
> were a ratio of two different share bases and were fixed (4,359 rows rebased at
> 1m), and the repo's own `TRADABLE_DOLLAR_VOL` floor was applied, which no book
> job had been doing.
>
> | | unfloored | **tradable ($3m/day, close ≥ $5)** |
> |---|---|---|
> | terminal wealth, 308 months | 85.32 vs market 13.03 | **36.44 vs 13.03** |
> | annualised excess | 10.95% | **6.73%** |
> | **t** | 2.407 | **1.682** |
> | share of excess in the 5 best months | 43.4% | **54.3%** |
> | **excluding those 5 months** | +6.30%/yr, t 1.57 | **+3.13%/yr, t 0.844** |
> | era t's (99-07 / 08-15 / 16-24) | 2.77 / 1.78 / 0.09 | **2.23 / 0.71 / 0.04** |
>
> The five months are **2020-01, 1999-11, 2000-05, 1999-12, 2020-11** — dot-com
> and COVID. Remove them and there is nothing left.
>
> **So "worked for 17 years and stopped in 2016" is not what the tradable book
> says.** It says **1999-2007 only** (t 2.23), already weak by 2008-2015
> (t 0.71), gone after. And half of even that is five months.
>
> The correct verdict is not `DECAYED`. Graded on the tradable book, `W9` now
> returns **CANNOT DETERMINE (underpowered; MDE 8.0%/yr)** with a **DSR of
> 0.127** over the weekend's full 288-trial search. Nothing here is a candidate
> for anything.
>
> `W9` is now graded on the tradable series by construction — the verdict, the
> era table and the power block all come from it, and `tail_concentration` is on
> every receipt. The unfloored numbers remain in the receipt, labelled, because
> the gap between them is the finding.
>
> *Two corrections pushed in opposite directions and that is the interesting
> part: the share-basis fix made the unfloored number BETTER (t 2.055 → 2.407),
> and the execution floor then took more than all of it back (→ 1.682). The fix
> improved the signal on split-heavy names, and split-heavy names are thin.*

## 0.old — the original headline, superseded by the box above

`W9_survivor_books` takes **every feature any screen marked as a survivor this
weekend** and books all of them in ONE family — which is also the multiplicity
fix, because five jobs each reporting "my best cell" is a five-fold search whose
deflation nobody was computing. Twelve survivors, 24 cells.

The best cell is `target_rev_1m__xs` (within-month rank of the 1-month change in
the mean analyst target price), long the top 50, value-weighted, 10 bps:

| | book | market |
|---|---|---|
| terminal wealth, 308 months | **56.66** | 13.03 |
| CAGR | **17.03%** | 10.52% |
| annualised excess | **+9.64%** | — |
| paired t vs market | **2.055** | — |
| turnover | 0.958/month | — |

**`powered: true`.** t = 2 needs 24.3 years at this Sharpe; the panel has 25.67.
**This is the first cell in the entire weekend with enough tape to answer its own
question** — which is the single thing the long panel was built to buy.

**And unlike the neural arm, it is buyable.** Under this repo's own execution
floor:

| filter | TW net | excess | t |
|---|---|---|---|
| no floor | 56.66 | 9.64%/yr | 2.055 |
| $3m/day (house floor) | 53.92 | 7.73%/yr | **2.08** |
| $3m/day **and** close ≥ $5 | 52.29 | 7.74%/yr | **2.022** |

**Only 7.85% of it is unbuyable**, against **93.7%** for the neural arm's 561×.
The t is essentially unchanged. Its median holding closes at $12.87 on $3.1m/day
— real names. Whatever else is wrong with this finding, it is not a microcap
artefact.

**And then the era table:**

| era | mean/month | t |
|---|---|---|
| 1999-2007 | **+1.51%** | **2.35** |
| 2008-2015 | **+0.95%** | 1.81 |
| **2016-2024** | **−0.02%** | **−0.03** |

It stopped. Not "was never there" — *stopped*, around 2016. Costs matter too:
at 25 bps the excess falls from +9.6%/yr to +6.2%/yr and t from 2.06 to 1.32, so
roughly half the edge lives between 10 and 25 bps on ~0.96 monthly turnover.

**And two things make the headline weaker than it first looked, both found by
interrogating it rather than by defending it:**

**(a) The DSR was computed over the wrong family.** `n_trials = 24 book cells`
counts the *books* and not the *screening that chose which features to book*.
Derived from the receipts, the real search is **253 distinct
(feature, job, variant) rows examined**, so `n_trials = 277`:

| | DSR |
|---|---|
| counting only the 24 book cells | 0.529 |
| **counting the whole search (277)** | **0.202** |

0.202 is almost exactly the **0.197** the night lab got on the 12-year panel —
the search is producing selection noise at the same rate, and the corrected
number says a zero-edge search would produce a Sharpe this good about 80% of the
time.

**(b) The headline signal is the *least* robust of the archetypes.** Across four
genuinely different W7 variants (top-100×3, top-25×8, top-50×5 at 12m, top-50×5
at 6m):

| feature | survives in | block-t range |
|---|---|---|
| `log_dollar_vol_20d` | **4 of 4** | −5.69 … −3.18 |
| `consensus__xs` | **4 of 4** | −3.48 … −2.52 |
| `net_rev_4w`, `net_rev_1m`, `consensus_rev_1m__xs` | 3 of 4 | ≈ +3 |
| **`target_rev_1m__xs`** | **1 of 4** | +3.81 |

`target_rev_1m__xs` entered the survivor list from a **single** variant. The book
result on 308 months stands on its own — it was measured independently — but the
*selection* of that feature came from a thin path.

**So it does not clear the NOVEL bar and it is not claimed to.** What survives
scrutiny is not the Sharpe; it is the **era pattern**, which is driven by the
sign table and the `powered` flag rather than by the DSR, and which no 12-year
panel could have shown.

**Why this is the weekend's most valuable output.** On the 2013-2024 panel this
appears as a weak positive and gets filed as noise. On 1999-2024 it is a strong
effect with a visible end date. *A decayed anomaly and an absent one are
different findings and imply different next moves* — the first says find out what
changed, the second says look elsewhere. So `verdict_from` gained a fourth word,
`DECAYED (worked, then stopped)`, which only a long panel can ever reach.

This is consistent with the published post-publication decay literature
(McLean–Pontiff) and with revision-based anomalies being among the most heavily
arbitraged. **It is not a trade. It is a dated fact.**

### 0.1 The autopsy — *what* changed, with the negatives reported

"It stopped working" is where research usually stops. `W10_decay_autopsy` tests
five candidate mechanisms and reports all of them, **including the ones that did
not move — because a mechanism that did not change is what rules an explanation
out.**

| era | VW book gross | market | excess | t | EW t | signal sd | mean analysts | 3m decile-spread t |
|---|---|---|---|---|---|---|---|---|
| 1999-2007 | 4.51 | 1.10 | +18.1% | **2.35** | **3.14** | 0.136 | 7.9 | **4.72** |
| 2008-2015 | 6.10 | 2.43 | +11.4% | 1.81 | 0.31 | 0.198 | 9.0 | 2.30 |
| **2016-2024** | **3.69** | **4.86** | −0.3% | −0.03 | −1.48 | **0.547** | 8.9 | **3.48** |

- **Arbitraged, not out-costed.** The **gross** book loses in 2016-2024 (3.69 vs 4.86). Costs explain net-vs-gross; they cannot explain this.
- **Not a size migration.** Equal-weighted is *worse* (t −1.48), so it did not move to names a VW book underweights.
- **Not an information-supply story.** Within-month dispersion of the signal **quadrupled** (0.136 → 0.547). There is *more* to sort on, not less. Coverage is flat (7.9 → 8.9 analysts).
- **But the 3-month decile spread is still alive at t 3.48** — stronger than in 2008-2015.

**So the lead was: it slowed rather than died.** Tested directly, by refreshing
the signal only every *n* months and carrying it in between (the portfolio a
quarterly rebalance produces, at ~1/3 the turnover):

| hold | era | tw net | market | excess | t | turnover |
|---|---|---|---|---|---|---|
| 1m | 2016-2024 | 3.03 | 4.86 | −0.3% | −0.03 | 0.945 |
| 3m | 2016-2024 | 4.51 | 4.86 | +2.2% | 0.27 | 0.378 |
| 6m | 2016-2024 | **7.96** | 4.86 | **+9.0%** | **1.02** | 0.235 |

**The lead does not survive.** No cell reaches t ≥ 2 in the last era.

And the tempting cell is named in the receipt on purpose — `hold6m|2016-2024`
shows terminal wealth **7.96 against a market of 4.86**, which is exactly the
number someone finds later and wants. It is not promoted because **t = 1.02 on
one era of an 18-cell search, and the identical rule returns 0.74 against a
market of 1.14 in 1999-2007.** A rule that only works in the era it was found in
is a description of that era.

**Third appearance of one lesson:** the 3-month *decile spread* is alive (t 3.48)
and the 3-month *book* is not (4.51 vs 4.86). A spread is top-minus-bottom,
equal-weighted inside each decile; a book is the top 50 only, value-weighted.
Same gap as W5b and W7b.

---

## 0.0 THE ANSWER TO THE QUESTION THE WEEKEND WAS ASKED

> *"Whether nineteen years say something seven could not."*

**They do — but not the thing we were asking.** Nineteen years say the learner's
edge was never an edge. It is six market-bottom rebound months.

### The finding that supersedes the DSR argument

On the corrected panel the champion is `lgbm|residual|6m|10bps`: terminal wealth
**25.84 against a market at 12.89**, +11.38%/yr, t 1.448 over 246 months. Then
ask where it came from.

| | share of excess in the **5 best months** | excess **without** them |
|---|---|---|
| no floor | **96.2%** | +0.44%/yr, **t 0.07** |
| $3m/day | 90.5% | +0.95%/yr, t 0.19 |
| $3m/day and ≥ $5 | 88.8% | +0.88%/yr, t 0.18 |

The runner-up `lgbm|raw|6m` is **108.8%** — *negative* without its five best
months. And the months name themselves:

```
2009-02  +74.9%     2016-02  +46.9%     2020-05  +37.2%
2019-01  +34.2%     2009-03  +31.3%     2020-03  +25.5%     2009-04  +25.5%
```

GFC bottom · the February 2016 bottom · the COVID crash and its rebound · the
rebound from the December 2018 selloff. **Every one is a market-bottom rebound.**
The book wins **48.8% of months** — a coin flip — and takes 96% of its total from
six of them.

**The control settles it.** The market's own five best months are **21.9%** of
its own total; this book's are **96.2%**. The concentration is not a property of
monthly returns. It is specific to this book.

**So the learner is not selecting stocks.** It holds small, cheap, volatile names
— the champion's median holding closes at **$4.19** and trades **$533k/day**,
with 58% of the book under $5 — and those rebound violently off bottoms against a
cap-weighted index. That is a **beta-timing artefact**, not selection skill, and
more tape does not fix it; it just supplies more bottoms.

This supersedes the deflation argument below. The DSR was never the binding
constraint: **there was no persistent monthly edge to deflate.**

### The deflation argument, which is still true and no longer the point `W2_learner_long`, the full 32-cell learner grid, walk-forward
2004-2023, 240 months common to every cell:

| | 12-year panel (night lab, 09-05) | **26-year panel** |
|---|---|---|
| best cell | lgbm\|raw\|3m\|10bps | **lgbm\|raw\|6m\|10bps** |
| paired excess | +1.553%/month | +1.096%/month |
| **DSR** | 0.197 | **0.293** |
| SPA p | 0.291 | 0.277 |
| PBO | 0.286 | 0.171 |
| out-of-sample months | 84 | **240** |
| years needed for t = 2 | 16.1 (had 7.0) | **30.7 (has 20.0)** |

More tape moved the Deflated Sharpe from **0.197 to 0.293** on the pre-fix panel,
and to **0.263** on the corrected one (the champion moves to `lgbm|residual|6m`,
SPA p 0.361, PBO 0.157, t 1.536, MDE **16.0%/yr**). The bar is 0.95.
Tripling the out-of-sample months bought about ten points of DSR and left the
verdict where it was: **CANNOT DETERMINE — underpowered.** The best cell shows
+11.45%/yr of excess at **t 1.43**, and its Minimum Detectable Effect is
**16.3%/yr** — the instrument could not have resolved what it appears to have
found.

Best cell by terminal wealth is `lgbm|raw|3m|10bps` at **TW 31.69 against a
market at 13.71** (+11.17%/yr, t 1.59) — and it still does not clear.

**One clean structural result, though, and it is the same in every cell:**

| | 10 bps | 25 bps |
|---|---|---|
| **every `lgbm` cell** (16 of 16) | positive excess | positive excess |
| **every `ridge` cell** (16 of 16) | **negative** excess | **negative** excess |

Ridge is not merely worse — it *loses*, by 1.2 to 9.3 %/yr, in all sixteen cells.
The relationship between these features and forward excess return is not linear,
and a linear model on them is an active liability rather than a weak baseline.
That is a finding about the feature space that holds across 26 years, four
horizons, two target shapes and two cost levels, and it does not depend on any
of the corrections above.

### 0.0.1 And feeding the weekend's new features into the learner does not help

The roadmap's instruction was that W4/W5/W6's features "feed into W2/W3's next
pass". They now do — `W2` variant 5, both grids fitted on the **same rows over
the same months** so the difference is the features and not the window, because
a feature that is real and *redundant* looks identical to a real and useful one
until the model is fitted both ways.

21 features added to the panel's 49:

| cell | paired lift (augmented − panel-only) | t | eras |
|---|---|---|---|
| lgbm\|raw\|1m\|10bps | +0.016%/mo | 0.03 | 2+/1− |
| lgbm\|raw\|1m\|25bps | +0.004%/mo | 0.01 | 2+/1− |
| lgbm\|raw\|3m\|10bps | **−0.555%/mo** | −1.17 | 1+/2− |
| lgbm\|raw\|3m\|25bps | **−0.558%/mo** | −1.17 | 1+/2− |

Terminal wealth at 3 months: **30.05 panel-only against 10.06 augmented.** Adding
the features cut it by two thirds.

They are real in isolation — W5 and W6 measured controlled Fama-MacBeth t's of 2
to 5 for several of them. They are **redundant given what the panel already
carries**, and eight of the 21 are the graph columns, which match **2.8%** of
panel rows: a ~97%-missing feature adds variance without information, even though
LightGBM consumes NaN natively.

**Conclusion: do not carry these into the learner.** The options surface still
earns its keep elsewhere — it is the source of the short-side signal in FINDING
9 — but as learner inputs the whole set is a no-op at best.

---

## 1. The one thing the weekend was for

Friday's night lab left a single number in the way: the best learner cell on
2013-2024 was **+14.4%/yr ahead of the market and NOISE by every honest test**
(DSR 0.197 against a 0.2305 noise bar, SPA p 0.29, PBO 0.29), and at that Sharpe
**t = 2 needed 16.1 years of out-of-sample months against the 7.0 on hand.**

That is a statistical ceiling, not a modelling one. So the weekend bought tape,
not model size.

### W1 — the long panel exists, and its early years are not thin

`learner/long_panel.py` → `train_table_long.parquet`, schema
`learner-train-table-3`.

| | incumbent | long panel |
|---|---|---|
| window | 2013-2024 | **1999-2024** |
| name-months | 605,410 | **925,757** |
| months | 143 | **310** |
| IBES loader pin | 605,410 | 1,228,757 name-months |
| CRSP daily rows read | ~13M | **31,051,486** |

**The roadmap's worry did not survive contact with the data.** It hedged that
"IBES coverage is thinner pre-2004 — print it; do not fake it." Printed:

| year | name-months | names | hygiene pass |
|---|---|---|---|
| 1999 (from March) | 19,733 | 2,895 | 0.804 |
| 2000 | 34,261 | 3,461 | 0.771 |
| 2004 | 35,283 | 3,316 | 0.788 |
| 2013 | 33,861 | 3,101 | 0.874 |
| 2024 | 38,124 | 3,420 | 0.773 |

The early era runs at roughly **85-90% of the late era's density**, not a
fraction of it. **Months, not rows, are what buy a t-statistic**, and months
went from 143 to 310.

### The share-basis fix holds in 1999, and the first gate that said so was broken

The 2026-09-04 share-basis correction (read the UNADJUSTED `ibes__ptgsumu`, never
rescale the adjusted file) had only ever been pinned on AAPL 2013-06. It needed a
test in the era it was never tested on.

**The first version of that gate could not pass.** It asked for `ratio` on rows
where `split_prior_year` is true — and `dataset.hygiene` defines
`target_readable = ... & ~split_prior_year`, so `build` NULLS `ratio` on exactly
those rows by construction. The gate saw zero rows, produced `nan`, and printed
FAIL. That is the failure CLAUDE.md already names: *a gate that cannot go green
is a broken gate, not a strict one.* Fixed by reading `ratio_unhygienic` — the
audit column that holds the raw ratio on precisely the suppressed rows — and by
matching the control on everything hygiene asks for **except** the split flag, so
the only difference between the two sides is the share-basis change itself.

**Result, 1999-2004:** 1,453 permnos with a share-basis change, 19,619 rows.

| | in-band rate | median ratio |
|---|---|---|
| names with a share-basis change | **0.9807** | 1.2149 |
| matched control, no change | 0.9780 | 1.2439 |

Gap **−0.0027**. A split-adjusted numerator over a raw denominator would move a
2:1 name's ratio by a factor of two and open a gap of tens of points. **PASS.**

---

## 2. Three findings, in order of how much they change what we do

### FINDING 1 — a t of −12 was a split artefact, and no test caught it

The behavioural feature `vwap_60d_gap` (price relative to its 60-session
volume-weighted average) first measured at **controlled t −12.06**, negative in
all three eras — by a distance the strongest controlled result in its table.

It was an artefact. The first construction took `Σ(prc·vol)/Σvol` — a **raw**
share-basis average over 60 sessions — and divided by **today's** `cfacpr`. For
any name that split inside the window the numerator mixes pre- and post-split
prices, the denominator mixes pre- and post-split share counts, and rescaling by
one day's factor corrects neither. Split-heavy names have distinctive forward
returns, so the feature was substantially measuring *did this name split
recently*.

The fix needs no extra data. Adjusted share volume is already derivable:

```
dollar_vol / adj_prc  =  (prc·vol) / (prc/cfacpr)  =  vol·cfacpr
```

so `Σdollar_vol / Σ(dollar_vol/adj_prc)` is a dollar-weighted average of
`adj_prc` itself — split-consistent by construction, one basis on both legs, no
rescaling at all.

**After the fix: controlled t −1.14. Nothing.**

This is `reference_farm_split_adjustment` arriving from a new direction, and the
uncomfortable part is the last clause: **no test caught it.** It was caught by
fixing the basis on principle before reading the result. Had the first run been
reported, the weekend's headline would have been an artefact.

*Related, same class:* `attention_z` is built on **dollar** volume rather than
share volume, deliberately — dollar volume is split-invariant, so the problem is
removed rather than corrected for. A share-count z-score reads a 2:1 split as a
6-sigma attention event.

### FINDING 2 — the 52-week-high effect is momentum on this universe

`W6_behavioural`, 925,757 rows, 309 months, 1999-2024. Each feature is reported
twice: its plain cross-sectional rank IC, and its coefficient in a **monthly
Fama-MacBeth regression that also holds momentum, size and vol** — because the
control belongs in the regression, not in a sentence after it.

| feature | rank IC | t (raw) | **t (controlled)** | eras +/− | verdict |
|---|---|---|---|---|---|
| `prox_52w_high` | +0.0556 | 5.39 | **−1.33** | 0/3 | **killed by controls** |
| `attention_z` | +0.0181 | 4.12 | **0.88** | 1/2 | **killed by controls** |
| `vwap_60d_gap` | +0.0143 | 2.10 | −1.14 | 0/3 | nothing |
| `prox_52w_low` | −0.0038 | −0.61 | −1.77 | 1/2 | nothing |
| `ret_5d` | −0.0120 | −2.10 | **−4.27** | 0/3 | **survives** |
| `attention_z_5d` | +0.0185 | 4.55 | **+2.71** | 2/1 | **survives** |
| `amihud_21d` | −0.0500 | −7.55 | **−2.37** | 0/3 | **survives** |

George–Hwang 52-week-high proximity looks like a strong effect at raw IC t 5.39
and **adds nothing** once the thing it correlates with is held in the same
regression. Same for single-day attention; only its 5-day average survives.

What does survive, on 26 years and with controls:
- **short-run reversal** (`ret_5d`, t −4.27, same sign in 3 of 3 eras) — classic, and it replicates;
- **5-day attention** (t +2.71, 2 of 3 eras);
- **Amihud illiquidity, with the sign INVERTED from the textbook** (t −2.37, 3 of 3 eras). More illiquid → *worse* forward excess. Plausibly because the analyst-covered universe with a $2 floor has already screened out the compensated end of illiquidity, so what is left is the uncompensated end. Flagged as a claim for Fable to attack, not as a result.

### FINDING 3 — the winner/matched-loser factory found an archetype that survives Holm

`W7_matched_loser`, **297 formation months (1999-04 → 2023-12)**, 50 residual
winners × 5 matched controls each.

The design, because it is the whole result: the 12-month forward excess is
**residualised within each month on size, momentum and vol ranks**, and each
winner is matched to five names in the **same sector** with the nearest (size,
momentum, vol) ranks that are neither winners nor losers. Every feature is dated
at the **formation month**; the outcome is twelve months later. So a difference
that survives is a difference that was **observable beforehand** — the Micron
test — not a story told afterwards.

**The loser side is what makes it a test.** Look at the largest t's:

| feature | winner − control | loser − control | reading |
|---|---|---|---|
| `vol_60d__xs` | +0.0257, block-t **19.0** | +0.0316, block-t **~30** | same direction both tails |
| `log_market_cap__xs` | −0.0225, block-t **−10.7** | −0.0263, block-t **−24** | same direction both tails |
| `dispersion__xs` | +0.0602, block-t **11.8** | +0.0747, block-t **~25** | same direction both tails |

Small, cheap, volatile, high-dispersion names are over-represented in **both**
tails. That is a statement about being **extreme**, not about being **right**,
and every one of them is correctly excluded.

What survives the matched control, a non-overlapping |t| ≥ 2.5, a consistent sign
in ≥ 2 of 3 eras, **and** a loser side that moves differently:

**AFTER THE LEAK FIX** (the pre-fix column is kept so the size of the correction
is visible, not asserted):

| feature | **block t (fixed)** | **Holm p (fixed)** | *block t (leaked)* | *Holm p (leaked)* | eras |
|---|---|---|---|---|---|
| `net_rev_4w` | **3.83** | **0.0047** ✓ | *3.05* | *0.063* | 2+/1− |
| `net_rev_1m` | **3.68** | **0.0082** ✓ | *2.98* | *0.079* | 3+/0− |
| `consensus_rev_1m__xs` | **3.52** | **0.0146** ✓ | *3.73* | *0.0062* | 3+/0− |
| `net_rev_4w__xs` | **3.35** | **0.027** ✓ | *2.50* | *0.259* | 2+/1− |
| `consensus_rev_1m` | 3.06 | 0.068 | *2.70* | *0.152* | 3+/0− |
| `coverage` | 2.93 | 0.099 | *—* | *—* | |
| `consensus` | −2.91 | 0.102 | *—* | *—* | |
| **`log_dollar_vol_20d`** | **−2.76** | **0.158** ✗ | *−4.57* | *0.00018* | 0+/3− |
| `consensus__xs` | −2.74 | 0.162 | *−2.72* | *0.152* | 0+/3− |
| `log_dollar_vol_20d__xs` | *dropped* | — | *−3.91* | *0.0031* | |

Eleven candidates over **four distinct ideas** — `net_rev_*` / `consensus_rev_*`
and their `__xs` ranks are several views of one idea, and counting them
separately would inflate the finding by construction. **Four survive Holm 5%**
(CANON §63: screen = BH, export = Holm).

**The corrected archetype, in words.** Against a name matched on sector, size,
momentum and vol, a future 12-month residual winner was, at formation, **being
upgraded** — analyst ratings and target counts revising up (`net_rev_4w` Holm
0.0047, `net_rev_1m` Holm 0.0082, `consensus_rev_1m__xs` Holm 0.0146), with a
secondary and weaker tendency to have been **rated lower to begin with**
(`consensus` −2.91, `consensus__xs` −2.74, both outside Holm).

**What is NOT in the archetype any more:** "thinly traded for its size." It was
the leak. Excluding future losers from the control pool made any predictor of
outcome *dispersion* differ from winners by construction, and thinness is
precisely that. It is worth noting that this leg was the one the earlier draft
found most striking — the largest t, the smallest p, and the first thing quoted.

**The honest counterweight — the recall baseline.** Share of each month's residual
top-50 already in the top decile of each precursor at formation, against the 0.10
a chance precursor gets:

| precursor | recall | lift |
|---|---|---|
| analyst upside | **0.195** | 2.0× |
| net revisions | 0.140 | 1.4× |
| 12-1 momentum | 0.135 | 1.4× |

So this is a real precursor with a **2× lift, not a discovery machine**. A mean
difference alone could not have told those apart, which is why both are printed.

### FINDING 4 — supply-chain momentum: CANNOT DETERMINE, and the reason is scope

`learner/features_graph.py`, built this weekend from `MARKET-GRAPH-1`.

The roadmap said the edges exist "2015-2024 only". **Measured, they do not.**
`filing_date` runs **2014-04-24 → 2024-06-26**; the source's own `date` column is
a quarterly research cut running 1–428 days *after* the filing (median 154) and
is never used as `valid_from`. Real coverage: **2014-05 → 2024-12, 129 months,
11 panel years of 26.**

Nothing reaches |t| = 2 in any of three variants. The best-directed arm is
customer momentum, equal-weight, **FM t 1.45** — the right sign for the
Cohen–Frazzini diffusion story, and **needing 18.6 years of tape against the 9.75
the graph has.** The controls killed nothing, because the raw ICs were already
~0.01 at |t| < 1.5; there was never a raw signal to strip.

Three scope facts that bound any future claim:

- **The median "customer average" is an average of ONE name** (median neighbours: customer 1, supplier 1, competitor 2). This is not a supply-chain graph; it is a handful of named counterparties per filer.
- The resolver placed **30.6% of raw mentions**; 69.2% of the residue is *not in CRSP* — Samsung, TSMC, Foxconn, Sanofi. **The graph is structurally missing most of the actual supply chain because most of it is not US-listed.**
- Every monthly cross-section is the graph universe (89–219 names), i.e. large widely-covered filers — not the panel.

The join matches **2.08% of panel rows**, against a ceiling of 4.4% (386 of 8,981
names × 11 of 26 years). `attach` prints all three numbers so nobody "fixes" it by
widening the tolerance.

**`MECHANISM_REJECTED` would be wrong.** This closes *this graph at this size*:
`FAILED_VARIANT` / `DEPRIORITIZED`, pending a wider edge set.

### FINDING 5 — **a Fama-MacBeth t of 4.15 lost money GROSS.** This is the weekend's most useful result.

This is a three-step chain, and the last step is the one that generalises.

**Step 1 — W5: two options features survive on 26 years, with controls.**
`learner/features_options.py`, built from `optionm_surface30d_*.parquet`
(**29 files, 1996-2024, 71,132,384 raw rows**, measured — not the month-end
decoy in the sibling repo, which is 12 dates a year and has already been
misread as "the surface is monthly" twice). `secid → permno` reuses the existing
`link_optionm_crsp` with interval validity; 99.96% linked — *and the receipt says
that rate is not evidence*, because the surface was pulled with a WHERE clause
bounded by that same link.

| feature | rank IC t | **FM t (controlled)** | eras | reading |
|---|---|---|---|---|
| `cp_iv_spread_30d` | 3.68 | **+4.15** | +/+/+ | Cremers-Weinbaum, literature's sign |
| `skew_25d_30d` | −0.38 | **−5.37** | −/−/− | Xing-Zhang-Zhao, literature's sign |
| `atm_iv_30d` | **−3.86** | −0.27 | mixed | **killed by controls** |
| `iv_minus_rv_21d` | **−3.54** | +0.87 | mixed | **killed by controls** |
| `atm_iv_chg_1m` | −0.17 | 1.55 | mixed | nothing |

Two more published features that are realised volatility wearing a
forward-looking label. That is now **three independent instances today** — with
`prox_52w_high` and `attention_z` — of a named effect dying under its own
controls. It is the weekend's most repeated finding.

**Step 2 — W5b: build the actual book. All 24 cells lose, and they lose GROSS.**

| | best cell | market |
|---|---|---|
| terminal wealth NET, 309 months | 6.65 | **13.18** |
| terminal wealth GROSS | **11.58** | 13.18 |
| turnover | 0.90/month | — |

Scored against **both** the full CRSP market and the value-weighted return of the
option-covered universe itself, because only 72.9% of panel rows carry a surface
and the missing 27% are systematically the small and illiquid — a book measured
only against the full market is partly measuring *having listed options*. It
loses against both. And since it loses **gross**, the spread is not the
explanation.

**Step 3 — the shape says why, and it is not a subtle reason.**

```
cp_iv_spread_30d — mean realised excess (%/month) by signal decile
d1     d2     d3     d4     d5     d6     d7     d8     d9     d10
-0.619 -0.047 +0.179 +0.089 +0.171 +0.182 +0.104 +0.089 +0.061 -0.032
```

Top-minus-bottom is +0.587%/month — **that is the entire FM t.** Deciles 3-10
span 0.2 percentage points and **d10 is worse than d3-d9.** The same shape holds
for skew (d1 −0.516, everything above it +0.01 to +0.14) and for the combination
(d1 −0.600, rest flat).

**These are short-side signals.** They identify names that will do badly and say
almost nothing about which will do well. A long-only top-50 value-weighted book
lives entirely in d10 — the one region where the signal is worthless.

**Why it generalises.** A Fama-MacBeth beta is the average slope over the whole
cross-section with every name weighted equally inside the month. A top-50
value-weighted book is the extreme tail with the weight on the largest names.
Those are different objects, and a signal that is monotone through the middle and
flat at the top scores brilliantly on the first and loses on the second. Every
feature result in this weekend — W6's three survivors, W4's arms, and any future
screen — is an FM beta. **This is the demonstration that t = 4 in that framework
can be worth less than zero as a book.** It is `feedback_ask_the_cross_section_first`
("the quantile SHAPE decides the construction") arriving with a price tag.

**Step 4 — W5c: the instrument a bottom-decile signal actually has.** A signal
that only marks losers needs no short book and no borrow: *don't hold them*.
Removing the bottom decile of `cp_iv_spread_30d` (ranked **within** each month,
never a full-sample cut) from an ordinary long book, against **a random decile
exclusion of the same size drawn from the same screenable rows in the same
months** — because removing 10% of any universe shifts the size mix, the sector
mix, and the number of names competing for 50 slots:

| base | bps | screen lift | random lift | **screen − random** | t | yrs → t2 |
|---|---|---|---|---|---|---|
| `mom_12_1` | 25 | +0.137%/mo | −0.035%/mo | **+0.171%/mo** | 1.27 | **64.1** |
| `mom_12_1` | 10 | +0.141%/mo | −0.021%/mo | +0.162%/mo | 1.21 | 60.1 |
| `net_rev_4w` | 25 | +0.007%/mo | −0.062%/mo | +0.069%/mo | 1.15 | 9,186 |
| `ratio` | 25 | −0.189%/mo | −0.224%/mo | +0.035%/mo | 0.14 | — |

**Verdict: CANNOT DETERMINE (underpowered), not NOISE.** ~+2%/yr in the right
direction against the control, needing 64 years of tape against 25.8 on hand.
Note the sign split: the IV screen helps a momentum book and *hurts* an
analyst-upside book, which is consistent with the two selecting different names.

*(My first version of this job returned `"NOVEL" if real else "NOISE"` and
printed NOISE for that row — the exact error the whole weekend exists to stop.
It now routes through the power block.)*

### FINDING 6 — the archetype does not make money, and the reason is the same shape lesson

`W7b_archetype_book` turns W7's three legs into an actual book. It does not work:
best cell **+0.91%/yr excess, t 0.27, DSR 0.052, 1,380 years needed**; the
size-neutral version is **−0.72%/yr**. Every one of 20 cells is at or below the
market.

The leg-by-leg shape says why, and it is the mirror image of the options result:

```
_leg_thin_for_size — mean realised excess (%/month) by decile
d1     d2     d3     d4     d5     d6     d7     d8     d9     d10
-0.019 +0.131 +0.193 +0.128 +0.210 +0.200 +0.123 +0.028 -0.090 -0.106
```

An **inverted U**. Moderately thin is +0.20%/month; *extremely* thin is −0.11%.
Top-minus-bottom is **negative**, so a long top-decile book buys the worst part —
and that leg alone returns **−7.2%/yr, t −2.21**. `_leg_rated_low` is similar
(−5.8%/yr). Only `_leg_being_upgraded` has its best decile at the top
(top-bottom +0.466, d10 +0.319), and it still makes no money as a VW top-50.

**The general form, and it is W5b's lesson from the other side:**

> A matched-control mean difference is a **LOCAL gradient** — how a winner
> differed from its nearest twin. A top-decile book is a **GLOBAL extreme**. For
> a non-monotone feature those two point in opposite directions, and *both
> readings are correct*.

Nothing about W7 is retracted. Its finding is a statement about the neighbourhood
of a matched control; W7b is a statement about the tail. The panel simply says
those are different places.

### FINDING 7 — S28's liquidity band does NOT replicate as a band. It replicates as a FLOOR.

W7b's inverted U is S28's liquidity band (+6.98%, t 2.22 in $100k–$10m/day,
found 2026-08-30 on 2013-2024) re-derived from a completely different direction.
That makes it a **replication target**: the edges are quoted, not chosen, and
1999-2012 is fourteen years the original claim never saw.

**The first version of this test was wrong, and the control row is what caught
it.** Measured against the value-weighted market, the band showed +7.64%/yr at
**t 2.25** out of sample — a near-perfect match to S28. But so did *every* band,
including `above_the_band` at t 2.06. The reason: `excess_vw_1m` is a name's
return minus the **value-weighted** market, and averaging it **equal-weighted**
over any broad set of names in 1999-2012 is positive, because EW beat VW
enormously in that decade. `learner/dataset.py` states the rule this broke — *an
EW benchmark is a size artefact, a small-cap portfolio wearing a market's name* —
and the test had built the artefact into its own benchmark.

Re-measured against the **equal-weighted rest of the universe** (same weighting
on both legs, so the regime cancels):

| band | vs VW market | t | **vs EW rest** | **t** | OOS t | eras + | yrs → t2 |
|---|---|---|---|---|---|---|---|
| below $100k/day | −0.59%/yr | −0.17 | **−2.58%/yr** | −0.93 | −0.77 | **0 of 3** | — |
| S28's $100k–$10m | +1.92%/yr | 0.68 | +0.85%/yr | 0.50 | 1.67 | 2 of 3 | 407 |
| wider $50k–$50m | +1.98%/yr | 0.82 | +1.79%/yr | 1.02 | **2.04** | 2 of 3 | 98 |
| narrower $500k–$5m | +1.86%/yr | 0.64 | +0.34%/yr | 0.23 | 1.23 | 1 of 3 | 1,887 |
| **above $10m/day (control)** | +1.34%/yr | 0.95 | **−0.06%/yr** | **−0.03** | −1.28 | 1 of 3 | — |

The control goes to **t −0.031** — dead flat — which is exactly what a control
should do once the artefact is removed, and is the evidence that it *was*
removed.

**Verdict: the band does not replicate as a band.** What survives is its lower
edge. Sub-$100k/day names lose 2.58%/yr against the equal-weighted rest and are
negative in **3 of 3 eras**; above that, liquidity stops mattering (the
$10m+ control is zero). That is a **FLOOR**, not a band — and the repo already
carries `evaluate.TRADABLE_DOLLAR_VOL = $3,000,000`, which is well above where
the damage actually is. Underpowered as an *edge*; clear as an *exclusion*.

### FINDING 8 — my own survivor filter had a sign bug that hid three of four features

The first version of the era test asked `holds_in_2_of_3` — how many eras had a
**positive** mean. That is right for a **strategy's excess return**, where the
book is long and a negative era is a failure. It is wrong for a **feature's
coefficient**: a reliably negative feature is a signal, traded the other way
round. The filter was dropping `ret_5d`, `amihud_21d` and (at the time)
`vwap_60d_gap` for the crime of being consistently negative.

Both are now reported — `holds_in_2_of_3` and `same_sign_in_2_of_3` — and every
caller names which one it means.

---

## 3. Infrastructure built (all of it running, none of it theoretical)

| what | where | why it exists |
|---|---|---|
| CUDA torch | 2.11.0+cu128, RTX 5060 Laptop, sm_120 | verified with a real matmul: 20 GPU matmuls in 0.433 s vs 3 CPU matmuls in 0.791 s (~36× per op). Blackwell has no kernels before cu128. |
| the long panel | `learner/long_panel.py` | 1999-2024, era column, coverage-by-year, the early-era share-basis gate, and `--regate` so a wrong gate costs no rebuild |
| `power_note` | `learner/inference.py` | `t = SR·√T` inverted: `years_needed_for_t2` beside every Sharpe, so NOISE and UNDERPOWERED stop being written in the same word |
| turnover hysteresis | `learner/evaluate.py` `book(hold_k=)` | buy at rank ≤ k, hold until rank > hold_k. On pure noise it cuts turnover 0.751 → 0.503 and moves net toward gross — it saves cost, it cannot create edge. REFUSES when `hold_k ≤ k`. |
| a real quantile head | `learner/models.py` `fit_predict(quantile=)` | pinball objective. q0.9 vs q0.1 correlate **−0.885**, and q0.9 vs the mean head only **−0.25** — ranking by the right tail is a genuinely different book. REFUSES rather than returning the mean head under a q-labelled name. |
| behavioural features | `learner/features_price.py` | 31,051,486 rows, 1998-2024, 94-100% coverage per column |
| the weekend runner | `scripts/weekend_lab.py` | variant cycling (twenty passes = twenty questions, not one question twenty times), two-strike skip, and a BEST SO FAR block rewritten at the top of the leaderboard each pass |
| evidence memory | `learner/evidence_memory.py` | **a single pass can neither promote nor kill**; REFUTED additionally needs three passes that each HAD THE POWER to detect the effect |

---

## 4. The honest part: three unreachable gates in one session

Three times today a gate was written against a key or column that could not
exist, and each would have printed a clean, false result:

1. the early-era share-basis gate read `ratio`, which hygiene NULLS on exactly the rows it was inspecting → permanent FAIL;
2. W7's archetype bar read `t_hac`/`t_block`, but `evaluate.overlap_corrected` returns `t_newey_west`/`block_t_block` → every corrected t came back `None`, and the job printed **"0 archetype candidates"** as though that were a finding;
3. W8's null bar read `p_value`, but `states.shuffled_null` returns `p_value_one_sided`.

All three now **REFUSE** on a missing key instead of defaulting to `None`. The
pattern is worth naming because it is not a typo class — it is that *a missing
input and a negative result look identical downstream*, and the default value is
what makes them indistinguishable.

---

### FINDING 9 — the shapes were pointing at real money, and the frictions are worst exactly where it lives

Five of twelve survivors have their whole effect in decile 1. W5b, W7b and W10
each concluded independently that a long top-50 book cannot reach an effect that
lives in the bottom decile. `W12_short_side` measures the book that can: long
top-50, short bottom-50, value-weighted inside each leg, **dollar-neutral,
benchmarked against CASH** (a neutral book carries no market exposure to beat),
with costs charged on **both** legs' measured turnover and **borrow charged
monthly on the short notional**.

`cp_iv_spread_30d`, at 10 bps and general-collateral borrow: **+4.91%/yr,
t 2.398**, SPA p **0.036**, PBO 0.157. The decomposition says where it comes
from:

| leg | annualised |
|---|---|
| long top-50 | **+13.71%** — ≈ the market itself, i.e. no alpha |
| short bottom-50 | **−0.78%** — ≈ 14.5 points below the long leg |
| transaction cost @ 10 bps | −2.08% |
| borrow @ 50 bps/yr | −0.25% |

**Essentially all of the spread is the short leg.** The decile-1 story, confirmed
in money.

**And then the frictions.**

| cell | ann. net | t vs cash |
|---|---|---|
| 10 bps, 50 bps borrow | +4.91% | **2.40** |
| 10 bps, 200 bps borrow | +4.16% | **2.03** |
| 10 bps, **500 bps borrow** | +2.66% | 1.30 |
| **25 bps**, 50 bps borrow | +1.79% | 0.87 |
| 25 bps, 500 bps borrow | −0.46% | −0.23 |

At 25 bps the cost drag is 5.21%/yr and it eats the whole thing. At 500 bps
borrow it dies too. **And the short leg's median dollar volume is $2,245,045/day**
— small, thin names, which is precisely where borrow is *not* general collateral.
**The realistic friction scenario is the one that kills it.** Zero of 30 cells
survive a 500 bps borrow at t ≥ 2, and DSR over the 30-cell family is 0.629.

`skew_25d_30d` behaves the same way one notch weaker (+3.68%/yr, t 1.70 at
10/50). `attention_z_5d` inverts entirely as a long-short (−1.23%/yr, t −0.53) —
its Fama-MacBeth coefficient does not translate at all.

**This is `COST_KILLED`, not `REFUTED`** — and the evidence memory has a separate
word for it on purpose, because "it does not work" and "it works and the
frictions eat it" call for completely different next moves. The honest reading:
the informed-trading signal in the options surface is real and it is on the short
side, and the instrument that could harvest it is the one this book cannot
afford. **The affordable version is an exclusion screen** — which is exactly what
`W5c` tested, and found at +0.17%/month over a random exclusion, t 1.27, needing
64 years.

**This is research, not a proposal.** `Mandate.allow_short` gates naked shorts on
the live books; this job placed no order, changed no mandate and proposed no seal.

### FINDING 10 — the GPU neural arm, and how 561× became 36×

`learner/neural_long.py` on the long panel, CUDA verified (`sm_120`, 8 seeds,
21 walk-forward years). Its best cell reported **terminal wealth 561.06 against a
market at 14.38** over 251 months — a ~35%/yr top-50 book, DSR 0.9835, SPA p
0.016, PBO 0.086. Every family test it was given, it passed.

In this repo a number that size has been an artefact before — the split
adjustment bug once produced a "42% CAGR equal-weighted market" and an 831×
basket — so it was checked the way `feedback_ask_what_it_bought` says to check:
**by printing the holdings.**

| | neural book | whole panel |
|---|---|---|
| median close | **$6.61** | $20.68 |
| share under $5 | **41.3%** | — |
| share under $2 | **17.9%** | — |
| median $ volume/day | **$1.03m** | $6.22m |
| share under $1m/day | **49.3%** | — |
| median market cap | **$202m** | $883m |

It is a microcap book. And `evaluate.TRADABLE_DOLLAR_VOL` — **$3m/day, this
repo's own execution floor** — was not being applied by the neural module, nor
by any of this weekend's book jobs.

| filter | TW net | excess | t |
|---|---|---|---|
| no floor | **561.06** | 23.97%/yr | 3.542 |
| $1m/day | 112.04 | 14.23%/yr | 2.917 |
| $3m/day (house floor) | 92.81 | 12.70%/yr | 2.756 |
| **$3m/day and close ≥ $5** | **36.31** | 7.04%/yr | **1.981** |

**93.7% of the headline is unbuyable**, and the t falls under 2 once a price
floor joins the volume floor. The neural arm's own verdict was already *"clears
the market bar, does NOT beat lgbm"* — the advantage over LightGBM does not
survive the family — so nothing here was going to be promoted anyway. But the
561× was going to be *quoted*.

So the floor check is computed in the **W3 wrapper and attached to every neural
receipt**, not written up in a document. A 561× sitting in a JSON file will be
quoted by somebody, and the correction has to travel with the number rather than
live somewhere they might not read.

**The neural lane found the same thing independently, and went three steps
further.** Its `robustness()` block is now permanent and in every receipt:

- **The champion is the top of an 8-draw distribution.** Across seeds the annualised excess runs min 4.4% / median 12.2% / **max 24.0%** (sd 6.1pp) and terminal wealth **9.26 → 49.31 → 561.06**. Only **6 of 8** seeds beat LightGBM. The published champion's t is five times the worst draw's.
- **The floor reverses the comparison.** Under $3m/day the champion falls 561 → 92.8 — and **LightGBM RISES, 16.75 → 59.85.** A 33× lead becomes 1.55×, and the seed-mean ensemble (89.3 → 42.8) ends up *behind* lgbm. A floor that helps the incumbent and hurts the challenger is not a detail.
- **Two more variants are refuted outright.** The **q90 pinball head loses money** — ensemble −3.5%/yr, terminal wealth **0.098**, a 90% loss, with 3 of 8 seeds positive. *"The right tail is more predictable"* is refuted on this panel, which retires W2's own quantile hypothesis. And **4× width does nothing** (median 11.5% vs 12.2%): capacity is not the constraint, which is the tape-not-model diagnosis arriving from a third direction.
- **The one thing that helped is the honest one.** Self-supervised masked-feature pre-training tightens the seed spread from sd 6.09 to **3.47pp**, lifts the worst seed from +4.4%/yr to **+14.2%/yr**, makes **all 8** seeds beat lgbm, and its ensemble survives the floor (83.6 vs lgbm 59.8) where the baseline's does not. Still NOISE by the family — but it is the direction worth another pass.
- **And the "mild look-ahead" buys nothing.** Pre-training on all 1999-2024 *features* is **worse** than the strictly causal version on every statistic. That removes a whole class of future temptation.

**One number from that lane lands on this document's own centrepiece:**
**99.6% of LightGBM's entire 251-month excess comes from five months** (43% for
the neural champion). At 25 bps lgbm goes 16.75 → **8.55, below the market's
14.38.** That is `feedback_check_the_tail_before_the_mean` pointed directly at
§0.0, and it is checked there.

### FINDING 11 — the last untried instrument, and why the decile-1 alpha cannot be harvested

Every book this weekend was the same shape: top 50 by a signal, value-weighted,
rebuilt monthly. The evidence kept saying that is the wrong shape — six survivors
carry their whole effect in **decile 1** and a long top-k book lives in decile 10;
the long-short that *can* reach decile 1 dies at 25 bps or a 500 bps borrow.

A signal that only marks losers, on names that are expensive to short, has one
remaining instrument: **do not hold them.** No borrow, no short book, no
concentration. `W13_composite_exclusion` builds it — on the **tradable universe
by construction** (≥$3m/day, ≥$5; 1,793 names/month, 309 months), dropping the
worst 10% by a composite of the five bottom-decile signals.

| arm | annualised | t | eras + | MDE |
|---|---|---|---|---|
| screened − unfiltered | +0.142% | **2.43** | **3 of 3** | 0.12%/yr |
| **random** decile − unfiltered *(control)* | −0.122% | −0.90 | 0 of 3 | 0.27%/yr |
| **screened − random** *(the only real column)* | **+0.264%** | 1.78 | **3 of 3** | 0.30%/yr |
| tradable universe − CRSP VW market *(sanity)* | +0.006% | 0.03 | — | 0.33%/yr |

Everything behaves. The control *hurts* (removing random names from a
value-weighted universe adds noise, −0.12%/yr, negative in all three eras); the
universe restriction is neutral (+0.006%/yr, t 0.03), so the floor is not doing
the work; and the signal-based exclusion beats a random one **in all three eras**.
This arm is also, for once, **well powered** — its MDE is 0.30%/yr, not 8%.

**And it is worth +0.26%/yr.** An order of magnitude below anything tradeable.

**The reason closes the arc.** A value-weighted universe barely notices its worst
decile, because those names are *small* — dropping 10% of 1,793 names by count
removes a tiny fraction by weight. The decile-1 alpha is real, and:

- a **long top-k** book cannot reach it (it lives in decile 10);
- a **long-short** can reach it and cannot afford it (borrow, on a $2.2m/day short leg);
- an **exclusion** can afford it and cannot feel it (value weighting dilutes it away).

That is every instrument, and the answer is the same each time. The alpha in
these signals is concentrated exactly where capital cannot go.

---

## 5. What the evidence memory says, taken together

`learner/evidence_memory.py` is what makes a looping lab cumulative rather than
repetitive: **a single distinct observation can neither promote nor kill**, and
`REFUTED` additionally needs three observations that each *had the power* to
detect the effect.

It also caught a flaw in itself, which is worth reading as a warning about every
looping system:

> `SUPPORTED  attention_z_5d  (cleared the full bar on 24 of 24 passes)`

Twenty-four of twenty-four passes is not twenty-four pieces of evidence — the
runner had executed a **deterministic** job twenty-four times against the same
panel. A rule written to stop one lucky pass being quoted had licensed the exact
opposite error: **a deterministic job promoting itself by being run again.**
`evidence_key` now collapses observations that asked the same question of the
same data and got the same answer. State counts before → after: SUPPORTED 12 → 7,
REFUTED 2 → 0, IDEA 91 → 114.

What replicates is a different **variant**, not a second execution:

| cell | state | on |
|---|---|---|
| `cp_iv_spread_30d`, `skew_25d_30d` | SUPPORTED | 2 of 2 distinct observations (8 passes) |
| `log_dollar_vol_20d` (+`__xs`) | SUPPORTED | 4 of 4, and 4 of 4 W7 variants |
| `consensus_rev_1m__xs`, `net_rev_4w`, `consensus__xs` | SUPPORTED | 2-3 distinct |
| `net_rev_1m` | CONDITIONAL | cleared once, not twice |
| `attention_z_5d`, `amihud_21d`, `ret_5d` | **IDEA** | 9 passes collapse to **1** observation |
| **`target_rev_1m__xs`** (the headline) | **IDEA** | **1 observation, however good** |

---

## 6. For Murat, on check-in

**Nothing was pushed, sealed, ordered, deployed, or changed on Railway.** The
lab's own rule. One command publishes the work:

```
git push -u origin lab/weekend-2026-09-06
```

Branch `lab/weekend-2026-09-06`, ~8 commits. Fast suite **6,545 passed, 17
skipped, 0 failed** on the last full run.

**Nothing here is ready to trade.** The Monday runbook
(`aegis-alpha-terminal/docs/RUNBOOK_2026-09-08_REARM.md`) is unaffected by this
weekend and should be run as written.

**The five things worth your attention, in order:**

1. **Nineteen years do not say what seven could not.** The 32-cell learner grid on 26 years moves the DSR from 0.197 to **0.293** against a bar of 0.95. Tripling the out-of-sample months bought ten points and changed no verdict. That is the answer to the question the weekend was set.
2. **Three of this session's own findings were wrong, and two review lanes found them** — a leak in the matched-control design, a guard that could not go red, and a power flag that was the t-test restated. All fixed, all with the correction attached to the number rather than filed in a document. **The reviews were the highest-value hours of the weekend.**
3. **The headline retracted itself.** Analyst target-price revisions looked like a powered +9.6%/yr result that decayed in 2016. Corrected for share basis and restricted to names over $3m/day above $5, it is **t 1.68, 54% of it five months, and confined to 1999-2007**. The retraction is the finding: it took a share-basis fix and one line of `tradable_floor` to move it, and neither was in place when it was written.
4. **A regression coefficient is not a book.** Five features died crossing that gap. Every book job now prints its decile shape before its verdict, and `W9_survivor_books` books every survivor in one family so multiplicity is counted over the whole search (288 trials, not 24). Related and cheap: **apply `TRADABLE_DOLLAR_VOL` in every book** — it was in none of them, and it is what turned a 561× into 36×.
5. **The liquidity FLOOR, not band.** Sub-$100k/day names lose 2.58%/yr against the equal-weighted rest, negative in 3 of 3 eras; above that liquidity stops mattering. The current $3m floor is safe but was not evidence-shaped until now.

**The single most useful number to carry forward:** a top-50 book over 21 years at
realistic volatility has a **Minimum Detectable Effect of ~7.4%/yr**, and the
26-year learner grid's best cell has an MDE of **16.3%/yr**. Most of what this
programme wants to measure is smaller than what its instruments can see. That is
not a reason to stop; it is the reason evidence has to accumulate across
independent tests rather than arrive from one — which is what
`learner/evidence_memory.py` now exists to do.

**Housekeeping I could not do from this repo:** the weekend roadmap asks for a
`W weekend lab` row in the roadmap §6 and a B10 status line. Those B-lanes live
in `aegis-alpha-terminal`, and per the four-repo rule this session did not reach
across. One row, yours to place.

### FINDING 12 — the lab ran out of memory and left no receipt at all

Late in the session the OS killed the runner, a standalone `W2_learner_long` and
two waiters **together**. None was individually large: every job that loads the
long panel peaks around **3-4 GB** (418 MB of parquet expanded into 142 float64
columns over 925,757 rows, plus model matrices), and three were holding one at
once — because a standalone job had been started *beside* the loop. Mine.

The runner serialises its **own** jobs correctly. What it could not see was a
second runner or a hand-started job, so it could not know it was one of three.

**The interesting part is not the OOM. It is that four processes vanished and the
only evidence was their absence** — which is precisely the failure this runner
was built to prevent: *a process that produces no artefact reads exactly like a
process that was never run.* The runner had that invariant for crashes, for
timeouts and for jobs that find nothing, and not for being killed from outside.

Fixed: `_free_gb()` reads available physical memory and `_other_lab_jobs()`
enumerates competing `weekend_lab_jobs` processes. Below **6 GB free** a job is
skipped with a receipt naming the free memory and the competing PIDs.
`_free_gb()` returns `None` rather than guessing where it cannot measure, and the
guard then *proceeds* with that recorded — a guard that silently blocks a weekend
is worse than no guard, and a guard that silently passes is the one it replaces.

The operating rule this leaves behind: **either the loop runs, or a standalone
job runs. Never both.**

---

## 7. Still running when this was written

- **W2** — the 32-cell learner grid on 26 years. Ridge on the late folds (700k rows × 5 alphas) is far slower than a 2010 probe suggested, so the grid is resumable: completed cells are cached tag-keyed and a killed pass resumes rather than repeats.
- **W3** — the GPU encoder, four variants × 8 seeds × 21 walk-forward years.
- The loop itself, cycling variants until a `STOP` file appears at
  `backend/data/optimus/weekend_lab_2026-09-06/STOP`.

*Claims for Fable to attack are marked as such above; two review lanes were also
run against them and their reports are in `docs/REVIEW_2026-09-06_*.md`.*
