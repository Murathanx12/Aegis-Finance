# TRIAL-DRAFT-D — the abstention book (`abstention-book-v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-12, before any read. Not in
`rule_experiments`; `cumulative_trials` unchanged.

**Family:** `NIGHT_JOB_BOOKS_2026_09` (four primary tests, one budget; Holm at
export). **Licence:** `PRODUCT_EXPERIMENT`. Zero capital.

## 0. Corpse check — the receipt this book must BEAT, reproduced in full

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`.

- **`NEGATIVE_RESULTS.md` §1 is the bar, not the background.** The existing
  timing strategy **lost to buy-and-hold on both axes**: total return
  **+28.3% vs +114.8%**, Sharpe **0.432 vs 0.837**, 2020-01 to 2025-06, 66
  monthly signals, 32 bps round trip. Those four numbers are reproduced here so
  that a later reader cannot quietly forget the bar. **Abstention is timing
  with a stricter trigger and must beat that receipt directly, printed on the
  same axes, not merely exist as a different construction.**
- **Resurrects: §1's mechanism, deliberately, with a named change of
  instrument.** The closed strategy switched on a market-level timing signal.
  This one switches per NAME on a cross-sectional confidence threshold and its
  default is the index rather than cash, so the cost of being wrong about the
  regime is zero rather than the whole equity premium. Whether that is enough
  is the question; the corpse is named because it is the same family.
- **Supporting prior, not a corpse:** Barber & Odean — high-turnover retail
  households earned 11.4%/yr net against 18.5%/yr for low-turnover, **with no
  difference in gross returns**. The entire value proposition is converting
  "nothing works most of the time" — this programme's own most robust finding —
  into a policy at zero mean cost. It is not a claim to add alpha.

## 1. Hypothesis

> A selector that holds its declared fallback (SPY) unless a name's confidence
> clears a frozen threshold — `Construction(rule="threshold_coverage")` with
> `engine_params["abstain"]` — reaches **higher terminal wealth at equal or
> better realised maximum drawdown** than the identical selector with the gate
> disabled (coverage forced to 100%), over ≥ 24 monthly blocks, **and** its
> risk-coverage curve is monotone.

**Honest prior.** Selective prediction / learning-with-a-reject-option
(Chalkidis & Savani) reports the covered region beating the always-in twin on
risk-adjusted terms at coverage as low as 17-55%, with the advantage **growing
with slippage** because abstention's cost is exactly zero. Transplanted to
portfolio form this is untested. The honest prior is that the confidence signal
carries little information and the book becomes an index-drag machine — which
is precisely the falsifier in §5.

**The confidence, v1, and why not v0.** Spec §D.2 names two triggers and says
not to block on L2. **v0** is R2's own digest `CONFIDENCE`; it covers a handful
of names a month and an abstention book needs a number for every name it might
hold. **v1** — the arena composite's cross-sectional extremity — is what is
wired and frozen. `COMPOSITE_WEIGHTS` is 99.5% 12-1 momentum for one-factor
names (CLAUDE.md THE BOTTLENECK), so the cross-sectional **z of `mom_12_1`** IS
the composite's extremity for almost every name, and this draft says that out
loud instead of pretending a six-weight blend is being computed. The z is
**signed**, not absolute: an abstention book deviating into a name because its
momentum was extremely negative would be buying the worst names in the market
with high confidence.

## 2. Coverage is the decision

`threshold_coverage` holds `engine_params["abstain"] = {"min_signal": 1.5,
"min_names": 3, "fallback": "SPY"}`. In any period where fewer than
`min_names` names clear `min_signal`, the book is the fallback and its turnover
that period is whatever moving to SPY costs. Coverage is **reported every
period** and is a first-class output, not a by-product: the literature's band
is 17-55% and a book outside it by a wide margin is mis-calibrated (§5).

## 3. Primary metric — the ONE deciding number

`terminal_wealth_at_equal_drawdown_vs_always_invested_twin`: terminal wealth of
the abstention book against the always-invested twin **at equal realised
maximum drawdown**, under the declared objective
`terminal_wealth_at_drawdown_budget` (`drawdown_budget = −0.20`,
`periods_per_year = 12`). The PRODUCT ruler is the right one here because the
pitch is cost and drawdown avoidance, not a return edge, and a ranked
comparison names the objective it was computed under.

**The sharpest single falsifier, reported alongside and checked FIRST:**
bucket months by confidence decile and compute realised excess-vs-twin per
decile. **The idea is wrong if that risk-coverage curve is flat or inverted** —
if the top-confidence decile's excess is not above the bottom decile's over
≥ 24 monthly blocks. This is the idea's own stated kill condition and it is
checked before the headline number is trusted.

**Reported, never deciding:** realised coverage per period; the SPY, random and
beta-matched twins; turnover; total return and Sharpe on §1's exact axes.

## 4. Power — §64, computed BEFORE the confirmation, and it constrains the read

Receipt: `backend/data/optimus/first_books/mde_receipt.json`.

| quantity | value |
|---|---|
| median cross-sectional monthly return sd, 2011-2024 | **0.162806** |
| k | 5 |
| implied book monthly sd | 0.072809 |
| book-minus-twin monthly sd | **0.102968** |
| blocks (the design's own floor, not the tape's) | **24** |
| **MDE at 80% power, α 0.05, two-sided** | **5.885%/month** |

> **A 24-block read cannot confirm a monthly mean edge smaller than 5.9%/month
> on a k=5 book.** No plausible version of this mechanism produces that. The
> monthly-mean test is therefore **reported as underpowered** and is not the
> deciding number — which is why the deciding number is terminal wealth at
> equal drawdown plus the monotone risk-coverage curve, both of which are
> comparisons of paths rather than tests of a small mean.

The 24-block floor is the design's own (angle4 §1) and is NOT a computed-MDE
substitute. It exists so the book cannot be read early even if it looks good at
month 6, and §8 forbids reading the curve before it.

declared_effect_size: 6.0% per month -- the top-minus-bottom confidence-decile monthly excess over the always-invested twin, one notch above the computed 5.885% MDE. It is stated as a number so the design can be powered at all, but it is NOT the deciding metric: the deciding metric is terminal wealth at equal realised drawdown plus a monotone risk-coverage curve, because a 24-block read on a k=5 book cannot resolve a small monthly mean and saying otherwise would be a power claim this design cannot support
event_frequency_per_year: 12 (a monthly decision; the design's own floor is 24 monthly blocks and the curve may not be read before them)
outcome_dispersion: 0.1030 (the book-minus-twin monthly sd implied by a measured median cross-sectional monthly return sd of 0.162806 at k=5)
outcome_horizon_days: 21 (one trading month)
dependence_unit: ONE CALENDAR MONTH -- the book holds at most five names or the index, and in an abstained month it holds exactly one series, so a name-month count would overstate the sample by the coverage fraction alone
cross_sectional_k: 5
cross_sectional_rho: 0.2345 (MEASURED: mean pairwise correlation of monthly name returns over 2011-2024, 250 names, 31,125 pairs, seed 20260912)
slice_purpose: CONFIRM -- forward only. The 24 monthly blocks are accrued AFTER seeding and none of them exists at registration, which is the one property that makes the read worth anything
selection_window_note: none exists. The book has no history at registration: its first NAV row is written by the first cadence pass after seeding, and the confidence threshold (min_signal 1.5) is frozen here before any coverage figure has been observed
slice_securities: the local daily bar universe above a $3M median dollar-volume floor and a $5 price minimum (3,060 symbols on the 2025-26 panel), plus the SPY fallback the book holds when coverage is empty
slice_period: 2026-10-01 .. 2028-09-30
information_cutoff: each monthly decision uses only bars up to that close; the book has no history at registration and every block in the slice is in the future
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the selective-prediction literature (Chalkidis & Savani) and from Barber & Odean. NEGATIVE_RESULTS §1 is the BAR this book must clear, quoted so it cannot be forgotten; its outcome is not what made the question exist

## 5. Decision rule

Earliest decision date: **24 monthly blocks after seeding.** Not before, for
any reason.

- **`PRODUCT_PROMISING`** — terminal wealth beats the always-invested twin at
  equal or better realised drawdown, **AND** the risk-coverage curve is
  monotone (Spearman > 0 with its own significance checked), **AND** the book's
  total return and Sharpe beat **+28.3% / 0.432** on `NEGATIVE_RESULTS.md` §1's
  own axes. Beating the twin is necessary and not sufficient; beating the closed
  receipt is the additional explicit bar.
- **`FAILED_VARIANT`** — the risk-coverage curve is flat or inverted (the
  confidence carries no information), **OR** terminal wealth is below the
  twin's at equal drawdown.
- **`CONDITIONAL`** — beats the twin but the curve is not clearly monotone, or
  realised coverage sits far outside the literature's 17-55% band (which
  suggests mis-calibration rather than a verdict).
- **Crash override** and contamination clause as in TRIAL-DRAFT-A §5.

## 6. Frozen parameters

The `Strategy` object `abstention_book_v0` as `scripts/seed_first_books.py`
constructs it, hashed at the registration commit. Also frozen: the **v1**
confidence trigger (signed cross-sectional z of `mom_12_1`) — a later swap to
v0 or to L2 is a **new registration, not an amendment**; `min_signal = 1.5`;
`min_names = 3`; `fallback = "SPY"`; k = 5; `max_single_name = 0.30`;
`drawdown_budget = −0.20`; the 24-block minimum.

## 7. Corpse-check result

Run 2026-09-12 against **358 prior experiments**:

```
PASS   (n_required 23, n_available 1115, smallest resolvable effect 0.86pp)
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
```

`PASS` means UNMATCHED, not novel: the linter compares wording against the
graveyard, the registry and the prereg corpus, and knows nothing about the
literature. The nearest neighbours it found are named in §0 and are quoted
there as corpses to respect, not as results that motivated this one.

`CALENDAR_DISJOINT_BY_CONSTRUCTION` is a **claim on the record**: it says no
prior fit was declared, so there is no selection window to overlap. If any
threshold, bucket boundary or universe in §6 was in fact chosen after looking
at this corpus, that declaration is false and the result is not a confirmation.

## 8. What this rule may NOT do

- **No reading the risk-coverage curve before 24 blocks.**
- No declaring victory on terminal wealth alone if the curve is flat.
- No comparing against a strategy weaker than `NEGATIVE_RESULTS.md` §1's own
  timing receipt.
- No tuning `min_signal` after the first read. A threshold tuned on the
  realised coverage is a coverage chosen to look like the literature's.
- No swapping the confidence trigger inside this registration.
- No quoting a coverage figure without the period count it was averaged over.

## 9. Registry

`rule_experiments` row `abstention-book-v0`, **not yet written**.
