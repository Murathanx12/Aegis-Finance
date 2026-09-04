# PROPOSAL (ATTENDED) — retire BAND_PRIOR's return constants, keep its hygiene

**Status:** proposal only. **Nothing in this document has been applied.** It asks
Murat for one decision, in two places (research constants and live thresholds).
**Roadmap:** `ROADMAP_2026-09-04_PROFIT_ENGINE.md` B1 task 5, whose text is
*"If no band's premium survives family-adjusted inference, BAND_PRIOR becomes
hygiene only."* This document argues the condition is met.
**Evidence:** `VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md` §1 and §4;
`REVIEW_2026-09-04_FABLE51_VERDICTS.md` §2.

---

## 1. What BAND_PRIOR asserts today

`learner/prior.py` carries four constants — the engine's expected annualised
excess return as a function of `ratio = mean_target / close`:

| band | constant | t | name-months |
|---|---|---|---|
| `ratio < 1.5` | +2.41%/yr | 1.30 | 285,173 |
| `1.5 ≤ r < 3` | +5.74%/yr | 1.85 | 48,289 |
| `3 ≤ r < 5` | **+16.55%/yr** | 2.20 | 5,888 |
| `r ≥ 5` | **−37.77%/yr** | −7.75 | 24,358 |

They are load-bearing: the offset in the learner's residual arm, a feature in
its raw arm, the incumbent baseline every model must beat, and — through
`aegis-alpha-terminal/alpha/tracker.py` — thresholds on six live paper accounts.

## 2. Why all four constants are artefacts

`learner/dataset.py:228` loads `ibes__ptgsum`, IBES's **split-adjusted**
consensus — targets restated in *end-of-sample* share terms — and `:445` divides
it by the **raw** CRSP close. Hand-verified: AAPL 2013-06-20 carries `meanptg`
**19.323** adjusted against **541.04** unadjusted, a factor of exactly **28.0**
(7:1 in 2014 × 4:1 in 2020). So

    ratio_used  ≈  true_ratio / cfacpr(t)

and `cfacpr(t)` is a *future* quantity. A name that later **reverse**-splits gets
its ratio inflated and lands in `toxic_ge_5`; a name that later forward-splits is
pushed down into `lt_1_5`. Reverse splits are what collapsing companies do, so
`toxic_ge_5` was a **future-collapse detector**, not an opinion about price targets.

The magnitude, re-derived independently and reproducing to the second decimal:

- **74.35%** of original `toxic_ge_5` rows carry a future reverse split, against
  **0.09%** of `lt_1_5`.
- Splitting the original toxic band by whether a future split exists:
  `cfacpr == 1` → **−13.38%/yr, t −1.65**; `cfacpr < 1` → **−48.88%/yr,
  t −7.14**. The −37.77 constant is the second column leaking into the first.
- Of 26,199 original "toxic" rows, only **2,965** are still toxic under a
  point-in-time ratio: 11,072 are really 1.5-3, 3,339 are 3-5, and **8,823 are
  below 1.5** — the opposite end of the scale.

All four constants were fitted on that mismatch. There is no subset of them that
is safe to keep.

## 3. Why the CORRECTED numbers do not replace them

Under a proper point-in-time ratio (`ibes__ptgsumu` over the raw close) the bands
invert, and the natural reading — *"then the toxic band is a long"* — is wrong:

| | corrected |
|---|---|
| `toxic_ge_5` | **+37.44%/yr, t 1.94, 7 names/month** |
| `b_3_5` | **−7.01%/yr, t −0.67, 46 names/month** |

The `+37.44%` does not survive contact with five checks:

1. **It is a sub-$5 cell.** 84.1% of its 2,093 name-months trade under $5
   (median close **$3.08**). Impose a $5 price floor and the sign **flips**:
   **−31.6%/yr, t −1.41**, on 3.6 names/month. The result is earned where a
   10 bps round-trip is fiction — a realistic spread on a $3 microcap is
   50-200 bps.
2. **Seven names a month is not a portfolio.** 10 of 143 months are empty, 17
   hold ≤ 2 names, 50 hold ≤ 5.
3. **It is a right tail, not a location shift.** Median monthly excess
   **−0.86%** against a mean of +2.69%. Drop the single best month (2020-06,
   +76% on 7 names) → +28.7%/yr, t 1.66.
4. **No era clears t = 2**: +38.3 (t 1.56) / +113.3 (t 1.41) / **+0.7 (t 0.03)
   for 2022-24**.
5. **It still carries lookahead.** 27.6% of the corrected cell *still* has a
   future reverse split, and dropping those rows moves the estimate to +93.5%/yr
   — a **56pp** swing on a lookahead filter means the composition is not clean.
   And merging `dlret` will make it *worse*: the original toxic band had the
   lowest 1m delisting incidence of any band (0.26%) because its members were
   survivors; the corrected band has the **highest** (1.79%).

Add the multiplicity the original "8 FDR survivors" never carried — they were one
finding × 4 horizons × 2 universes — and nothing is left.

**Therefore: no band's premium survives family-adjusted inference.** B1 §5's
condition is met.

## 4. What is proposed

### 4a. Research side (`learner/prior.py`) — reversible, no capital at risk

1. **Retire the four return constants.** `horizon_prior()` returns **0.0** for
   every band, with `has_opinion` unchanged. A prior of zero is a *statement*:
   the engine has no calibrated expected excess as a function of the ratio.
2. **Keep the hygiene, which was never a band and never depended on the defect:**
   - `close ≥ $2` — below $2 the prior was measured UNINFORMATIVE (t 0.39, S30b)
     and the house rule is "no opinion", never "historically bad";
   - `coverage ≥ 2` analysts;
   - **unreadable-across-split** — a target quoted on a share basis the price is
     not on is not an opinion; this is the defect promoted to a hygiene rule;
   - `ratio ≥ 50` exclusion, and split-year hygiene.
3. **Add a price floor of $5 to any future band work**, recorded as the reason:
   every apparent band premium found so far lives below it.
4. Keep `band_code` as a *descriptive* label. Delete `prior_*` from the learner's
   feature set and from the residual target — the residual arm currently
   subtracts an in-sample, full-window, equal-weight-benchmarked prior from a
   value-weight excess, which is three problems even when the constants are
   right.

**Consequence to state plainly:** the learner's residual arm loses its offset and
its incumbent baseline. That is not a regression to be worked around — the
baseline was flattered (`prior.py` says so itself: *"the prior arm gets to know
the future that the ML arms are denied"*) and the champion already sits at the
maximum of its own noise distribution. The honest baselines are the ones in
`learner/baselines.py` plus the canonical benchmarks in `learner/benchmark.py`.

### 4b. Live side (`aegis-alpha-terminal/alpha/tracker.py`) — **needs Murat**

The live rule reads **Finnhub unadjusted** targets. That is a *different object*
from the tape, and its thresholds were imported from the corrupted tape. So the
live thresholds have never been tested on the data they actually consume —
independently of everything above.

Two options, and I recommend the first:

| option | what it does | why |
|---|---|---|
| **A — hygiene only (recommended)** | keep the price floor, the coverage floor and the unreadable-across-split refusal; drop every ratio-band admission and every band-derived expected return | The live object was never measured. Hygiene rules are the ones that do not require a measurement to justify. |
| B — re-derive on the live object | build a Finnhub-target panel and measure the bands on it before changing anything | Correct in principle, but it needs a PIT Finnhub history nobody has yet, and the accrual clock has not started |

Option A is not "turning the signal off" — it is declining to keep a threshold
whose only evidence was an arithmetic error. Whether it changes what the books
buy is an empirical question the seal will answer on the next pass, and the
answer belongs in the receipt.

## 5. What would reverse this

A band premium that survives, simultaneously: a point-in-time unadjusted ratio; a
$5 price floor; delisting returns merged; a family correction over every band ×
horizon × universe cell examined; and a 2022-24 sub-era that does not sit at
t ≈ 0. If such a cell exists, the constants come back with a receipt. Until then
the prior is zero, and zero is a measurement.

## 6. The decision requested

1. Apply 4a on the research side? (reversible, no capital)
2. Live thresholds: **A** (hygiene only) or **B** (re-derive first)?
3. If A: should the books re-seal on the next scheduled pass, or stay held until
   B2's hold integrity ships? Note that B2's exit machinery is unfixed and the
   entry pass currently has no deadline gate, so "re-seal now" means re-sealing
   into a loop that closes 60% of its round trips the same session.

Nothing proceeds on any of the three until you answer.
