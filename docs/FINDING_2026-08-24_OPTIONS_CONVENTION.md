# FINDING — 2026-08-24: the options train/serve gap is a SOLVER gap, and it is 80% closed

**Measurement** `OPTIONS-CONVENTION-1` (round 1) · `OPTIONS-CONVENTION-2` (rounds 2–3), both declared before their numbers
**Receipt** `backend/data/optimus/options_pit/convention_receipt.json`
**Quotes** `backend/data/optimus/options_pit/convention_quotes.json` — every arm and the rate sweep are pure functions of this cache
**Module** `backend/services/option_implier.py` · 22 tests
**Script** `scripts/options_convention_measure.py` — the declaration and the code are the same file

## Verdict

**The mechanism is identified and settled. The blocker is 80% smaller. It is not
gone, and no arm that is a correct model clears the declared bar.**

`EVENT_RESPONSE_v1` remains `NEEDS_CALIBRATION` on `iv_put_minus_call_30d` —
but for a residue of 0.0053 instead of 0.0262, and the residue is now a
*quantified* question rather than an unexplained offset.

---

## 1. What was actually wrong

**yfinance's `impliedVolatility` column discounts nothing.**

| arm | median | gap vs stdopd | % positive |
|---|---|---|---|
| **R0** vendor IV *(control)* | **−0.02428** | −0.02622 | 23.1% |
| **R3** our inversion, **r = 0, q = 0** | **−0.02335** | −0.02529 | 17.9% |

R3 reproduces R0 to **0.0009**. Setting the rate and the dividend to zero in
our own solver recovers Yahoo's number. That is the whole 0.026 gap, and it was
never a difference in what the two datasets *measure*.

This is also why the two spent routes failed. The matched-strike fix corrected
*which strikes* were compared; the cross-sectional rank corrected *the scale*.
Both kept reading the disputed column, which is the quantity that was wrong.

**And it had to be this feature.** Put-call parity ties a call and a put at the
same strike, so a same-strike IV residual is close to a pure statement about
the pricer's `r` and `q`: it is a *difference*, so the volatility level cancels
and the convention error does not. The other three option features are levels
or same-side slopes, where a shared bias mostly cancels. Three transferred and
one did not, and that pattern was the fingerprint of a solver gap all along.

## 2. Inverting the prices ourselves closes 80% of it

| arm | model | median | gap | % positive | transfers |
|---|---|---|---|---|---|
| R0 | vendor IV | −0.02428 | −0.02622 | 23.1% | no |
| **R1** | **BSM, declared r and q, on the MID** | **−0.00338** | **−0.00532** | 43.6% | **no, by 0.0003** |
| R2 | same, q = 0 | +0.00250 | +0.00056 | 56.4% | *yes* |
| R3 | same, r = 0, q = 0 | −0.02335 | −0.02529 | 17.9% | no |
| R4 | R1 on the LAST TRADE | +0.00272 | +0.00078 | 51.3% | *yes* |
| R5 | r solved from cross-strike parity | +0.02307 | +0.02113 | 63.6% (n=22) | no |
| R6 | R1 with American exercise | −0.00408 | −0.00602 | 43.6% | no |

R1 is the candidate and it **misses the declared 0.005 bar by 0.0003**.

**R2 and R4 clear the bar and must not be shipped on that basis.** R2 sets the
dividend to zero, which is not OptionMetrics' convention; R4 inverts the last
trade, which is not either. Both land by cancellation, and adopting a model
because its errors happened to offset is the failure this measurement exists to
avoid. They are reported because a receipt that hid two passing arms would be
choosing quietly.

## 3. The two candidate explanations for the residue, both tested

R5 and R6 were **declared together**, before either ran, because they test the
two available stories for the same 0.005 — a wrong rate, or early exercise —
and running them one at a time would let the second be chosen after seeing the
first.

**Early exercise is ruled out.** R6 prices American options
(Bjerksund-Stensland, closed form) and moves the residual by **−0.0007** —
an order below the residue, and in the *wrong direction*. The premium is real
and correctly signed (an American put is worth more, so its European-implied
vol is too high, so pricing it properly *lowers* the residual). It is simply
tiny at 30 days near the money.

**Solving the rate from the market overshoots.** R5 takes the discount factor
from the cross-strike slope of `C − P`, which is model-free and vendor-free in
theory. It returned **+0.02307 on 22 of 39 names** — an implied rate near 7%,
which is not a rate. The diagnosis is in the failure itself: the slope in `K`
is contaminated by a *strike-dependent* term, and the American put's
early-exercise premium grows with strike, steepening `C − P` exactly that way.
R5 is unusable here, and it is unusable for a reason R6 measured.

## 4. What the residue is worth, in units anybody can check

The residual is very nearly linear in the net carry:

**median ≈ −0.0234 + 0.709 × (r − q)**, i.e. **≈ +0.0070 per percentage point**

Both halves are measured, not fitted: the intercept is R3 (r = q = 0) directly,
and the slope is 0.0071 from the R2−R3 contrast and 0.0069 as a finite
difference across the sweep. The two disagree in the third decimal because the
median runs over names with different dividend yields, so the relation is very
nearly linear rather than exactly so. Checked at three points:

| r | formula | measured |
|---|---|---|
| 0.0000 | −0.0291 | −0.02902 |
| 0.0400 | −0.0007 | −0.00082 |
| 0.0500 | +0.0064 | +0.00606 |

So:

| r | median | transfers |
|---|---|---|
| 0.0000 | −0.02902 | no |
| 0.0300 | −0.00776 | no |
| **0.0363** *(FRED fed funds, the declared source)* | **−0.00338** | **no** |
| 0.0400 | −0.00082 | yes |
| 0.0425 | +0.00090 | yes |
| 0.0500 | +0.00606 | yes |

**The verdict is decided by about seven tenths of a percentage point of rate.**
Round 1's first pass ran at 4.25% and reported TRANSFERS — because
`risk_free()` called `.get("value")` on a pandas Series, raised inside
`float()`, and silently fell back to a declared constant *while printing a rate
that decided the verdict*. That defect is fixed; it is recorded here because it
is the house failure mode wearing a new hat.

Matching stdopd's median exactly would need a rate of **4.37%** against a fed
funds effective of 3.63%. **The missing 0.74pp is the size of general equity
borrow**, which is precisely what `iv_put_minus_call_30d` is supposed to
measure — the codebase already calls it "the classic borrow/hard-to-borrow
proxy". So the residue may not be an error at all.

**That is a hypothesis and it is not asserted.** It has a cheap test, named in
§6.

## 5. A defect in the transfer test itself

The comparison is a **one-day live cross-sectional median** against a **median
over OptionMetrics' whole panel**. The residual is a direct function of the
prevailing rate — 0.0071 per point, measured — and the panel spans rate regimes
from zero to five percent. Those two medians have no reason to coincide even
when the feature is measuring the identical quantity.

This is not a reason to dismiss the gap; the 0.026 part was real and is now
explained. It is a reason the remaining 0.005 cannot be adjudicated by this
comparison as constructed.

## 6. What ships, and what is next

**Ships now**

* `option_implier.py` — inversion under a declared convention: continuous `r`
  and `q`, bid/ask midpoint with the price basis recorded per point, European
  BSM and Bjerksund-Stensland American, refusal (not a clamp) on an unpriceable
  quote, and `_phi` evaluated in log space because `kappa = 2b/sigma^2` reaches
  ~2265 for an American put at a 0.5% vol and the textbook form forms an
  overflow times a zero. That crashed on the first live name.
* The standing instruction that follows from §1: **never read a vendor's
  implied-volatility column again.** Read prices, declare the convention.

**Next, and cheap — the test that settles §4 and §5 together**

Recompute the stdopd reference median **restricted to periods whose short rate
is near today's**, and compare R1 against *that*. The panel is already pulled.
If the restricted median lands near −0.003, the feature transfers and the
residue was a regime comparison. If it stays near +0.002, the 0.74pp is
something real about the live universe and the borrow hypothesis is testable
directly against hard-to-borrow indicators.

**Meanwhile the review's fallback stands and is now much cheaper.** Shipping
the drop-feature arm as a labelled `PRODUCT_EXPERIMENT` costs a feature whose
train/serve error is 0.005, not 0.026 — an entirely different decision from the
one taken this morning.

## 7. The lesson

Three features transferred and one did not, and the one that did not was the
only *difference* among them. That pattern was visible before any of this ran:
a difference cancels the level and keeps the bias, so it is the most sensitive
probe of a convention you did not choose — and the most misleading thing to
read as a signal disagreement.

**A number computed by somebody else's model is not data. It is their model.**
