# FINDING — 2026-08-24: the options train/serve gap was two wrong conventions, and it is CLOSED

**Measurements** `OPTIONS-CONVENTION-1` · `OPTIONS-CONVENTION-2` · `OPTIONS-RATE-REGIME-1` · `OPTIONS-DIVIDEND-WINDOW-1` — each declared, in a committed file, before its numbers existed
**Receipts** `convention_receipt.json` · `rate_regime_receipt.json` · `dividend_window_receipt.json`, all under `backend/data/optimus/options_pit/`
**Quotes** `backend/data/optimus/options_pit/convention_quotes.json` — every arm and the rate sweep are pure functions of this cache
**Module** `backend/services/option_implier.py` · 22 tests
**Script** `scripts/options_convention_measure.py` — the declaration and the code are the same file

## Verdict — AMENDED, and the amendment is the result

**The feature TRANSFERS.** Not by calibration, not by a fitted map: by getting
two conventions right that were wrong. Read §§1–4 for how the 0.026 became
0.005, then §5 and §5.5, which are where the last 0.005 went and where the
explanation I preferred was refuted by my own measurement.

| arm | median | gap vs stdopd +0.00194 | % positive | transfers |
|---|---|---|---|---|
| vendor IV *(where this started)* | −0.02428 | −0.02622 | 23.1% | no |
| ours, declared r, **trailing** q | −0.00338 | −0.00532 | 43.6% | no |
| **ours, declared r, q over the option's own WINDOW** | **−0.00179** | **−0.00373** | **46.2%** | **yes** |

`EVENT_RESPONSE_v1` may serve the full model on this column under the
servability rule declared before any of this ran. That is one live cross-section
of 39 names against a 168-month panel median, and §7 says what it is not.

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

## 5. I thought the transfer test was defective. It is not. — `OPTIONS-RATE-REGIME-1`

**The claim this section used to make, now withdrawn:** that the comparison is a
one-day live cross-sectional median against a median over OptionMetrics' whole
panel, on a quantity that moves 0.0070 per point of rate across a panel spanning
zero to six percent — so the two medians need not coincide even when the feature
is identical.

It sounded right and it is wrong. Measured over **168 months**, the panel's own
residual regressed on FEDFUNDS:

| | |
|---|---|
| slope | **+0.00001 per percentage point** |
| t | **0.04** |
| R² | **0.000** |

**Flat.** A precisely measured zero, not an underpowered one.

The reason is the finding. **OptionMetrics discounts correctly, so the rate is
already absorbed and what remains does not move with it.** Ours moves at
0.0070/pp precisely because `r` and `q` are *our inputs* and we can get them
wrong. That asymmetry is diagnostic: a residual that tracks the policy rate is
a residual computed under the wrong carry.

So the full-panel median **+0.00194** is a legitimate reference, and the
remaining 0.005 was ours to explain.

*Reproduction check passed on the way:* the panel's full median recomputes to
+0.00194 at 54.8% positive — exactly the standing reference in
`train_serve_skew_receipt.json`, from an independent path.

**And the regime half of that test is underpowered by construction; its verdict
must not be read.** Only **one** month of 2006–2019 has FEDFUNDS within 0.5pp
of today's 3.63%. My declared rule had no minimum-months guard on the subset —
the third instrument defect this session found by running the instrument, after
round 1's `n_eff` gate and the single-null-draw comparison in the graph work.

## 5.5 It was `q`, and specifically the tenor — `OPTIONS-DIVIDEND-WINDOW-1`

Declared with a **point prediction before running**, which is what separates a
test from a search.

We used **trailing 12-month dividends / spot**. For a 30-day option the
economically correct `q` is the dividend expected *inside the option's life*,
and a quarterly payer has an ex-date in a given 30-day window only about a third
of the time. For the rest the correct `q` is **zero** — so the trailing yield
systematically over-states the carry deduction.

Measured: **11 of 39 names (28%)** carry a projected ex-date inside 30 days, and
the median `q` over the window is **0.00000** against a trailing median of
0.00767. Switching to it moves the residual to **−0.00179**, which clears both
declared bars.

**The point prediction was wrong in magnitude and right in mechanism, and both
halves belong here.** I predicted +0.0025 — the sensitivity 0.709 times the
median trailing `q` of 0.0083. The actual move was +0.00159, not +0.0059,
because the median of a heterogeneous shift is not the shift at the median: the
non-payers move not at all, the 28% with an in-window ex-date move partly, and
only the rest move fully. The arithmetic was against the wrong world, which is
the house failure mode, and it left the direction and the mechanism intact.

**Why R7 ships and R2 does not, even though both clear the bar.** R2 sets `q`
to zero for *every* name, which is wrong for the 28% that do pay inside the
window; it lands by a compensating error. R7 is a correct model: `q` measured
over the window each expiry actually spans, with future ex-dates projected from
the median historical cadence — an estimate, using **only past ex-dates**, so
no look-ahead, and exactly the information a live collector holds at decision
time.

That distinction was written down in §2 *before* R7 existed, which is what makes
it a selection rule rather than a rationalisation. Eight arms were run; the one
that ships is the one that is a correct model **and** was declared with a
prediction, not the one with the smallest gap (R2's is smaller).

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

* `options_pit_store` schema **1.2.0**: `q_used` is now the window yield,
  `q_trailing` is kept beside it (the standing receipts were computed under it,
  so dropping it would make them unreproducible), and both travel with every
  row. Shipped before the collector's first run rather than after, because
  `pi_options_pit` first fires Monday 15:30 ET and a chain has no history to go
  back for.

**The review's fallback is no longer needed.** Shipping the drop-feature arm
would now cost a feature that clears its transfer bar. That is a different
decision from the one on the table this morning, and it is the one
`EVENT_RESPONSE_v1` should be built against.

**What is still open, and it is not small**

* **One day, 39 names.** The transfer is measured on a single live
  cross-section. The collector accrues daily from Monday; the honest version of
  this number is the same comparison over a month of snapshots.
* **The 0.74pp of unexplained carry did not vanish, it shrank.** R7's median
  still sits 0.0037 below the panel's. Implied financing above OIS and general
  borrow both live in that gap and neither has been measured.
* **`pct_positive` is 46.2% against the panel's 54.8%** — inside the declared
  0.10 bar, and the largest remaining distributional difference. A tree splits
  on thresholds, so the sign balance around zero matters more than the tail
  shape.
* The projected-ex-date approximation is untested against a name that changes
  its dividend schedule inside the window.

## 7. What this is not

It is not evidence of alpha, and nothing here touched a forward return. It is a
servability result: the live feature now has the same distribution as the one
the model was fit on, to within bars declared before the first measurement.

`EVENT_RESPONSE_v1`'s own numbers are unchanged — IC +0.0315, t 3.19 at one
day, and its `MDE₈₀` of 0.0276 still sits just under its own IC. This work
removes a reason it could not be *served*. It adds nothing to the case that it
*works*.

## 8. The lesson

Three features transferred and one did not, and the one that did not was the
only *difference* among them. That pattern was visible before any of this ran:
a difference cancels the level and keeps the bias, so it is the most sensitive
probe of a convention you did not choose — and the most misleading thing to
read as a signal disagreement.

**A number computed by somebody else's model is not data. It is their model.**
And when your own number moves with something theirs does not, the thing it
moves with is your bug.

Three instruments in this session were defective and all three were caught by
running them: an `n_eff` gate that re-asked the density question, a null
comparison with one draw and no dispersion, and a regime subset of one month
with no minimum. **The measurement that checks a measurement is the cheapest
thing here and it keeps being the thing that was skipped.**
