# FINDING — 2026-08-24: the options feature works, and the edge it produces is borrow fees

**Trial** `EVENT-RESPONSE-2` · **licence** PRODUCT_EXPERIMENT (SCREEN)
**spec_hash** `534124d8bd63f4f4` — frozen before the first number
**Receipt** `backend/data/optimus/event_response/event_response_v2_receipt.json`
**49,357 events · n_effective = 96 EVENT MONTHS** (CANON §58 — the
**168** originally printed here was the frame's month count; every arm
walks forward from 2012 and is built from 96 evaluated months, so the
original overstated the evidence base by 75%.)

> ## SUPERSEDED IN ITS VERDICT — 2026-08-24
>
> **The borrow slice below was implemented wrongly and its conclusion does not
> hold.** It excluded high-borrow events from the TRAINING SET as well as the
> evaluation cross-section, which measures "can a model trained only on
> cheap-to-borrow names predict them" rather than "does this signal predict
> among cheap-to-borrow names".
>
> Run as an attribution test — model fixed, evaluation population varied — the
> effect does **not** move: drift1 goes 0.0315 -> **0.0329 (t 3.56)** when
> hard-to-borrow names are excluded. `AMENDMENT-1` reproduces the original's
> 0.01505/t1.42 exactly as the train-and-eval variant.
>
> **`docs/FINDING_2026-08-24_EVENT_RESPONSE_V2_AMENDMENT1.md` supersedes
> sections 2-4 below.** The verdict returns to **BUILD** (a PRODUCT_EXPERIMENT
> paper licence, not a claim). Section 1 stands unchanged.


## Verdict: **NOT LICENSED — borrow-confounded.** Downgraded from BUILD by a test declared in advance.

---

## 1. v1's diagnosis was right

`EVENT-RESPONSE-1` returned STOP and named its own reason:
`options_implied_move` was `None` throughout the corpus, so "surprise" was
measured against analyst consensus when the tradable quantity is
`surprise − what was already priced`.

21.1M rows of `stdopd` later, that hypothesis tests **positive**:

| arm | base | with options | BH-FDR |
|---|---|---|---|
| `lightgbm@1d` | +0.0105 (t 1.04) | **+0.0315 (t 3.19)** | ✓ |
| `lightgbm@2d` | +0.0164 (t 1.45) | +0.0220 (t 2.07) | ✗ |
| `lightgbm@5d` | +0.0158 (t 1.74) | **+0.0288 (t 2.61)** | ✓ |
| `ridge@1d` | +0.0061 (t 0.65) | +0.0094 (t 0.91) | ✗ |

Paired, on the same months: **options help the tree by +0.0210 ± 0.0093
(t 2.27)** at one session.

Ridge gains nothing, so the relationship is **non-linear** — which is what a
"did it move more than priced" feature should be: it matters conditionally, not
as a slope. `surprise_only` is bit-identical across the two feature sets, which
is the sanity check it should be.

**And unusually for this repository, it was adequately powered**: MDE₈₀ 0.0276
against an observed 0.0315. Every other screen this session sat below its own
MDE.

---

## 2. And then the precondition killed it

The roadmap promoted `OPTIONS_BORROW_CONFOUND_v1` to a **precondition** of this
work rather than a follow-up, on a 2025 JFE result: much of the apparent
stock-return predictability in option-implied measures is explained by **stock
borrow fees**, and excluding expensive-to-short names removes most of it.

The proxy is free here. By put-call parity ATM call and put implied vols should
agree; the residual `iv_put_minus_call_30d` is the classic hard-to-borrow
signal. Top quintile = high borrow (cut +0.0192, 9,872 of 49,357 events).

| | all events | excluding high-borrow | only high-borrow |
|---|---|---|---|
| **`drift1`** | +0.0315 (t **3.19**, p 0.002) | +0.0151 (t **1.42**, p 0.16) | +0.0088 (t 0.46) |
| **`drift5`** | +0.0288 (t **2.61**, p 0.011) | +0.0113 (t **0.96**, p 0.34) | +0.0233 (t 1.23) |

**Removing 20% of events removes 52% of the effect at one session and 61% at
five, and all of the significance.**

This is not a power artefact. The **point estimate halved**; MDE₈₀ moved only
0.0276 → 0.0297. Dropping a fifth of the sample cannot do that to an estimate
unless the dropped fifth was carrying it.

The `only high-borrow` column is itself insignificant, but it is 69 months with
MDE₈₀ 0.054 — badly underpowered, and it cannot carry a positive claim either.
So the honest statement is **"removing them removes the effect"**, not "the
effect is entirely in them".

---

## 3. What is true, stated carefully

1. **The implied move genuinely adds predictive information.** The paired
   comparison is on identical months and identical events, and it is +2.27 SE.
   v1's diagnosis was a real hypothesis and it tested positive.
2. **The predictability it produces is concentrated in hard-to-borrow names.**
3. **Therefore it is not a selector.** You cannot trade it where it works
   without paying the cost that most plausibly explains it, and a cheaper
   mechanism that explains the same number wins.

What this does **not** say: that the option feature is useless. It says that
*this* edge, on *these* names, at *this* horizon, is not separable from borrow.
A version that conditions on borrow explicitly — trading only where the effect
survives, or modelling the fee as a cost — is a different experiment and needs
its own declaration.

---

## 4. Why this was found before a selector existed and not after

Because it was declared as a **precondition**, not a follow-up.

Had the borrow slice been left for later, this session would have shipped a
`BUILD` verdict on IC 0.0315 with t 3.19 surviving BH-FDR — a genuinely strong
number — and retracted it afterwards. The receipt records both verdicts
(`verdict_before_borrow_slice: BUILD`) so the downgrade is visible rather than a
result that quietly never existed.

That is the second time in one session that the order of operations decided
whether something became a retraction or a refusal. The other was
`feature_leakage_guard`, built after an IC of 0.99 was caught by luck.

---

## 5. Method notes

* **PIT.** Option state is the last observation **strictly before** the event's
  tradable date (`merge_asof`, `allow_exact_matches=False`, 7-day tolerance).
  96.9% of events matched.
* **Target unchanged from v1**, so the two runs are comparable: `sign(gap) ×
  cumulative excess return over the k sessions strictly AFTER the event
  session`, entry at the event day's close.
* **Leakage guard ran before any model was fitted.** Strongest feature-target
  agreement 0.041 (`overnight_gap`), far under the 0.5 bar.
* **Both feature sets on the same events**, so "options helped" is a paired
  difference on one sample rather than two runs on two populations.
* **`stdopd` is ATM-only** — no skew, no 25Δ, no risk reversal. Nothing here
  computes them.
