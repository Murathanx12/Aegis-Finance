# FINDING — 2026-08-24: the borrow confound was a training artefact, and the refusal was mine

**Amendment** `EVENT-RESPONSE-2/AMENDMENT-1` · hash `e9e7622bd537999a`
**Parent** `EVENT-RESPONSE-2`, spec_hash `534124d8bd63f4f4` (unchanged)
**Receipts** `event_response_v2_amendment1_receipt.json` (+`_drift5`)
**Declared and committed BEFORE any of its numbers existed** (commit `b1956ce`)

## Verdict: **BORROW_ATTRIBUTION_NOT_ESTABLISHED** at both horizons.

The precondition that downgraded v2 from BUILD does not fire when it is
executed as an attribution test. I ran the original slice, and I got it wrong.

---

## 1. What the original slice actually did

v2 reported that excluding the top borrow quintile took `drift1` from +0.0315
(t 3.19) to **+0.0151 (t 1.42)** — a halving — and concluded the predictability
lived in hard-to-borrow names. The receipt argued this was not a POWER artefact,
and that argument was sound: the point estimate halved while MDE₈₀ moved only
0.0276 → 0.0297.

But "not a power artefact" does not establish "therefore borrow". The script
that produced it no longer exists, so it was re-derived from scratch. Four
variants, one walk-forward fit each, identical pipeline:

| variant | IC | t |
|---|---|---|
| **A** baseline, all events | 0.03147 | 3.19 |
| **B** exclude high-borrow from **evaluation only** | **0.02980** | **3.35** |
| **C** exclude from **training AND evaluation** | **0.01505** | **1.42** |
| **D** exclude from **training only**, evaluate on all | 0.00700 | 0.68 |

**C reproduces the original to the digit** — 0.01505, t 1.42. The original
excluded high-borrow events from the TRAINING SET as well as the evaluation
cross-section.

That answers a different question. "Can a model trained only on cheap-to-borrow
names predict cheap-to-borrow names?" is not "does this signal predict among
cheap-to-borrow names?" — the first confounds the population with a 20% smaller
and differently-composed training set.

**D is the diagnostic that settles it.** Excluding high-borrow names from
training while evaluating on *everything* gives 0.0070 (t 0.68) — worse than C.
The damage is entirely on the training side. The model needs those names to
LEARN the relationship; it does not need them to PREDICT.

That makes sense mechanically: hard-to-borrow names have the widest IV spreads
and largest moves, so they are where `gap_vs_implied` varies most. Strip them
from training and the fit loses its range.

## 2. The attribution test, run properly

Model fixed, evaluation population varied — the only thing that isolates where
the predictability lives.

| slice | drift1 IC | t | drift5 IC | t |
|---|---|---|---|---|
| all events | 0.03147 | 3.19 | 0.02883 | 2.61 |
| **exclude HIGH borrow** | **0.03286** | **3.56** | **0.02826** | 2.43 |
| exclude LOW borrow | 0.02708 | 2.32 | 0.02999 | 2.52 |

Excluding hard-to-borrow names does not reduce the effect. At `drift1` it
slightly *raises* it. Paired difference high-vs-low: **+0.0058 ± 0.0088
(t 0.66, p 0.51)** — no difference at all. At `drift5` the paired
difference is **-0.0017 +/- 0.0084 (t -0.21, p 0.84)**, i.e. the high-borrow
exclusion is if anything the *milder* of the two.

Controls, as declared:

* **Random 20% exclusions** (20 draws): mean IC 0.03195, p20 0.02823, min
  0.02467. The borrow exclusion sits *above* the random mean.
* **Placebo top-quintile exclusions**: `pre_event_price_runup` 0.04188 ·
  `disclosure_delay_days` 0.03479 · `expectation_dispersion` 0.02534 ·
  `iv_term_slope` 0.02879. Trimming a tail moves the IC around by ±0.01 in
  either direction; the borrow cut is unremarkable within that spread.

## 3. What this changes, and what it does not

**Restored:** v2's declared decision rule produced BUILD, and the precondition
that overrode it does not fire. `lightgbm@1d[with_options]` — IC +0.0315,
t 3.19, surviving BH-FDR, MDE₈₀ 0.0276 — stands as the only adequately-powered
result this programme has produced.

**Not restored:** any claim of alpha. BUILD licenses a PRODUCT_EXPERIMENT paper
book, nothing more. And the deployment question is genuinely open — trading
concentrates in the names where the signal is strongest, which still overlaps
expensive-to-short names. The finding is that the signal is not *confined*
there, not that borrow costs are irrelevant to a live book.

**Also corrected:** v2's receipt reported `n_effective: 168`, taken from the
frame's month count. Every arm walks forward from 2012 and is built from **96**
months; the earlier months are training, and training months are not evidence.
That overstated the evidence base by 75% under CANON §58. Fixed in the script;
both numbers now carry their roles.

## 4. The lesson, and it is not the one I expected

The previous session's write-up said the borrow precondition was promoted from
follow-up to precondition, and that **the ordering was what turned a
retraction into a refusal**. That was true, and it was the right instinct.

It just wasn't sufficient. A precondition declared in the right order can still
be *implemented* wrongly, and a wrong implementation produces a confident number
with a plausible story attached. The refusal felt more rigorous than the BUILD,
which is exactly why it went unchallenged: **a result that argues against your
own interest reads as evidence of care, so it gets audited less.**

What caught it was not suspicion. It was noticing that "not a power artefact"
and "therefore borrow" are different claims, and that only one had been tested.

Two operational consequences:

1. **A slice that changes a verdict must say which side of the fit it changes.**
   Training population and evaluation population are different experiments and
   the receipt must name which one ran.
2. **The ad-hoc script that produced the original slice was never committed**,
   so the verdict rested on numbers nobody could re-derive. This amendment
   lives in `scripts/event_response_v2.py --amendment-1`. A number that decides
   a verdict belongs in a runnable file, not a terminal.
