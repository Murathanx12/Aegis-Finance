# PREREG — N9B: is 1.271 the vocabulary's ceiling or the market's?

**Registered:** 2026-08-16, after N9's confirmation and before any wider-vocabulary
number exists.

**Resurrects:** N9 — new instrument: five features admitted to the grammar that
are not functions of the security's own price and VIX. N9 answered "can the
grammar mark these moves"; this asks "is the answer bounded by the grammar".

## Why

N9 confirmed that rules over the eight-feature transferable vocabulary mark
uncovered exceptional moves at lift **1.271** out of sample (p = 0.015), and
that 1.271 sits below the **1.69** at which acting on the warning would pay.

Every feature in that vocabulary is a function of **one security's own price
history plus VIX**. So the ceiling has two possible causes and they imply
opposite next moves:

* **the market's** — exceptional moves genuinely are not markable, and building a
  bigger episode factory will produce a thousand stories that compile into the
  same 1.27;
* **the vocabulary's** — the grammar cannot express the state that matters, and
  the factory has something to find as soon as it can say it.

This is the cheaper of the two diagnoses and it decides which to fund.

## The five features admitted, and why these five

All are **cross-sectional or liquidity** state — the information class the
current vocabulary structurally cannot express, since every existing term is
computed within one security's own series.

| feature | what it says | why it is not already there |
|---|---|---|
| `breadth_stress` | fraction of the 12-security universe whose `rv20` is in its own expanding-window top decile | "this security is volatile" and "everything is volatile" are different states and the grammar can only say the first |
| `xs_dispersion` | cross-sectional sd of 20-day returns across the universe | dispersion vs level: a market moving together and a market pulling apart look identical to `rv20` |
| `avg_pairwise_corr` | 60-day mean pairwise correlation across the universe | the co-movement term MARKET-GRAPH-1's one clean positive was about |
| `dollar_volume_z` | 20-day z-score of log dollar volume | participation, entirely absent from a price-only grammar |
| `amihud_20d` | mean of \|return\| / dollar volume over 20 days | illiquidity, ditto |

Every one is computed backward-looking and lagged one day, exactly as the
existing eight are. `breadth_stress` uses an **expanding** window so a rank never
sees its own future.

## Protocol — identical to N9, deliberately

Same target (bottom-decile moves the incumbent library missed), same train
(`SPY/XLF/XLE` pre-2016), same foreign (`QQQ/IWM/XLK` post-2016), same
confirmation (`DIA/XLV/XLI/XLP/XLU/XLB`), same bar (1.69 / 2.11 from N4B), same
block-shift placebo, same seed. **Only the feature set changes.** Anything else
would leave the comparison uninterpretable.

## Decision rule (pre-committed)

The quantity is the **difference between two confirmation medians** — wide
vocabulary minus narrow — because "1.42 is bigger than 1.271" is not a test
(§18). Both are medians of the same statistic on the same slice, so the
difference is taken over the same block-shift resamples and carries its own
interval.

| outcome | verdict |
|---|---|
| wide − narrow > 0 and above its own MDE, wide confirmation p < 0.05 | **`VOCABULARY_BOUND`** — the ceiling was the grammar. Fund the vocabulary before the factory. |
| wide − narrow not above its MDE | `NOT_DETECTABLE_IN_SCOPE` — this addition does not move it, which is **not** evidence that no addition would |
| wide confirmation p ≥ 0.05 | the wider search did not transfer at all; report it and prefer the narrow result |

**And the economic bar does not move.** If the wide vocabulary reaches, say,
1.45 and 1.45 is still below 1.69, the finding is scientific and the investment
answer is unchanged. Those stay separate rows.

## The multiple-comparison honesty

This is a **second look at the same target with the same splits**. The search
denominator grows (13 features rather than 8), and both denominators are printed.
More importantly: N9's confirmation slice has now been used **twice**, so it is
no longer virgin. Any third look at it is worth nothing and must use new
securities.

## R13 — resolvability, declared before compute

- event_frequency_per_year: 25
- declared_effect_size: 15pp
- outcome_dispersion: 2.3pp
- corpus_years: 27

## Run spec (frozen)

`python -m scripts.n9_mine_the_85 --confirm --wide-vocab`, seed 20260816.
ONE run.

## Result (filled in AFTER the run — never edited afterwards)

Run 2026-08-16. Search denominator **38,038** (286 single-clause, 37,752
two-clause) against the narrow run's 13,728.

| H | narrow confirmation | wide confirmation | difference | null sd | MDE | p(paired) |
|---|---|---|---|---|---|---|
| 20d | 1.271 (p = 0.015) | 1.354 (p = 0.010) | **+0.083** | 0.110 | 0.309 | 0.289 |
| 60d | 1.330 (p = 0.075) | 1.386 (p = 0.015) | **+0.056** | 0.211 | 0.591 | 0.279 |

**Verdict: `NOT_DETECTABLE_IN_SCOPE` at both horizons.** The five
cross-sectional/liquidity features did not detectably widen the grammar's reach.

**And the thing this test was built to stop.** Read as two point estimates, the
60-day row looks like a change in kind: the narrow vocabulary did not transfer
at 60 days on either slice (p = 0.428 foreign, 0.075 confirmation) and the wide
one transfers on both (0.030, 0.015). That is the §18 error — comparing two
p-values — and the paired difference refuses it flatly: **+0.056 against an MDE
of 0.591.** Without the difference statistic this would have been written up as
"the vocabulary was the ceiling, confirmed at 60 days."

**The equivalence version says more than the null does.** The difference that
would have mattered is exactly known — the gap from the narrow median to N4B's
break-even lift:

| H | needed | observed | upper 95% bound | |
|---|---|---|---|---|
| 20d | +0.419 | +0.083 | **+0.264** | **`RULED_OUT`** |
| 60d | +0.780 | +0.056 | **+0.403** | **`RULED_OUT`** |

**These five features are ruled out as a route to a tradeable rule.** Not
"we couldn't tell" — the amount that would have closed the economic gap was
large enough to see, and it is excluded. A powered negative.

### What this does and does not license

* It does **not** show the vocabulary is irrelevant. It shows that *these five*
  additions do not close the gap. Event, revision, fundamental and text features
  are untouched, and the same test would answer for them.
* It **weakens** the case for funding vocabulary width ahead of the episode
  factory, which is the opposite of what I expected when I registered it.
* The confirmation slice `DIA/XLV/XLI/XLP/XLU/XLB` has now been used **twice**.
  It is spent. Any third look needs new securities.

### The defect found while computing this

`_aggregate`'s confirmation result was computed, printed and **never written to
the artifact** — so the amendment's own result lived only in a terminal that had
scrolled away, and this experiment's declared statistic had nothing to read.
Found by trying to compute it. Both runs were re-executed after the fix and
reproduced their originals exactly, seeds being deterministic.

- Receipts: `n9b_wide_vocabulary.json`, `n9b_difference.json`
- Scripts: `scripts/n9_mine_the_85.py --wide-vocab`,
  `scripts/n9b_vocabulary_difference.py`
