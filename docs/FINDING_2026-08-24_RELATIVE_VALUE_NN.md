# FINDING — 2026-08-24: the neural question closes, and the first answer was a leak

**Trial** `RELATIVE-VALUE-NN-1` · **licence** PRODUCT_EXPERIMENT (SCREEN)
**spec_hash** `294b0203bf75c9a7`
**Receipt** `backend/data/optimus/relative_value/relative_value_nn_receipt.json`
**71,647 pairs · n_effective = 145 DATE BLOCKS** (CANON §58 — never 71,647)

## Verdict: **STOP.** No selector licensed, and the NN question is closed.

---

## 1. What was asked

Roadmap P1.2. Every other selector here asks "is this stock good". The decision a
portfolio actually makes is *"is this stock better than the one whose capital it
would take, after paying to switch"* — which `relative_value_labels` already
labelled: ordered pairs, both one-way costs charged at each name's measured TAQ
rate, cost-model-sensitive pairs excluded and counted.

Two questions, and the second is the one the roadmap wanted settled:

1. Is pairwise capital substitution predictable out of block **at all**?
2. Does a **neural** model add anything a tree or a line does not?

---

## 2. The result

Out-of-block rank IC within each test date, expanding split by date, 105 test
dates:

| model | IC | SE | t | p | MDE₈₀ | BH-FDR |
|---|---|---|---|---|---|---|
| ridge | +0.0233 | 0.0221 | 1.05 | 0.29 | 0.062 | ✗ |
| lightgbm | +0.0117 | 0.0119 | 0.98 | 0.33 | 0.033 | ✗ |
| mlp | +0.0034 | 0.0114 | 0.30 | 0.77 | 0.032 | ✗ |

| paired | diff | SE | t |
|---|---|---|---|
| mlp − lightgbm | **−0.0083** | 0.0112 | −0.74 |
| mlp − ridge | **−0.0199** | 0.0205 | −0.97 |
| lightgbm − ridge | −0.0116 | 0.0178 | −0.65 |

**Q1: no.** Nothing survives BH-FDR. **Q2: no** — and the MLP is not merely
non-superior, it is the **worst of the three**, behind both the tree and the
line.

### The neural question is closed, per the rule declared before the run

> *"If the MLP cannot beat LightGBM out of block, NEURAL-RELATIVE-VALUE closes
> as a v1 question WITH A RECEIPT and is not retried with a bigger network — an
> MLP that cannot beat a tree on tabular features is not going to be rescued by
> depth."*

It did not, so it closes. **The multi-head torch model the roadmap describes is
not built.** It was only ever worth building if the single-head version was
competitive, and this is what decides that.

---

## 3. The null owes its second test

MDE₈₀ is **0.033 for the tree and MLP, 0.062 for ridge** (whose date-to-date
variance is far higher). Against observed ICs of 0.003–0.023, this run had low
power throughout.

**What can be said:** no pairwise predictability of size ≥ ~0.03 IC exists in
these seven state features, out of block, on 145 date blocks.
**What cannot:** that the pairs are unpredictable. A 0.02 effect would have been
missed most of the time — and ridge's +0.023 is exactly the size that this
design cannot resolve.

---

## 4. THE FIRST RUN OF THIS SCREEN WAS A LEAK, AND IT IS THE MORE USEFUL RESULT

The same script, an hour earlier, returned:

| model | IC | t |
|---|---|---|
| ridge | +0.9688 | **+1070** |
| lightgbm | +0.9913 | **+2184** |
| mlp | +0.9835 | **+876** |

and its own decision rule reported **the pairwise signal as licensed**. No
financial prediction looks like that; it was not written up.

**The cause**, measured within date:

| feature | mean rank IC vs `forward_return` |
|---|---|
| **`cs_rank`** | **+1.0000** |
| **`cs_decile`** | **+0.9950** |
| `vol_63` | +0.0271 |
| `mom_252` | +0.0115 |

`cs_rank` is the cross-sectional rank **of the forward return**. The answer, in
the feature list.

The script's own docstring, two lines above the list, already said *"everything
else in the panel is a FORWARD quantity and would be the answer, not a
feature"*. The column was included anyway, because its **name** reads like a
state variable. **A property of the data was asserted from its column name
rather than measured** — this programme's named house failure mode, and the
third instance in one session:

| | what was trusted | what was true |
|---|---|---|
| `stdopd` skew | the catalogue's "standardized options" | ATM-only; no wings, no 25Δ |
| event-response target | that a daily return excludes the gap | CRSP is close-to-close; it includes it |
| `cs_rank` | the column name | the rank of the outcome |

Two of the three were caught by reading before running. **This one was caught
only because the number was absurd, which is not a method** — a leak that
produced IC 0.15 instead of 0.99 would have shipped.

### So the guard is now structural

`backend/services/feature_leakage_guard.py`. Every feature's **within-block**
rank IC against the target, refused at **0.5** — a bar nothing honest in this
repository approaches (strongest measured here: 0.032). It runs **before any
model is fitted**, so a leak becomes a refusal nobody had to believe rather than
a result someone has to retract, and it refuses outright when it cannot see
enough blocks to certify anything.

Verified against the real leak: it names `cs_rank` and `cs_decile` with their
ICs, passes the seven honest features, and refuses on a starved sample.

**0.99 → 0.023 is the entire value of the guard, in one number.**

---

## 5. What this changes

* **No relative-value selector is licensed.** The corpus is sound; these seven
  momentum/volatility state features do not rank capital substitution.
* **`NEURAL-RELATIVE-VALUE` closes as a v1 question.** Not "pending a better
  network" — closed, with this receipt.
* **The corpus is not discredited**, and Order 20 §4's G5 note still stands for
  whoever revisits it: the distinct claim is pairwise *substitution*, and richer
  features (event state, options, actor) were never tried here.
* **`feature_leakage_guard` should be called by every future screen** before it
  fits anything. It is cheap and it is the difference between a retraction and a
  refusal.
