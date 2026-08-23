# FINDING — 2026-08-23: analyst reliability is measurable and persistent

**Verdict: `RELIABILITY_PERSISTS` — the precondition for actor intelligence
holds.**
**Licence: none requested.** Nothing is traded from this.

Reproduce:
```
python -m scripts.actor_corpus_ibes --build
python -m scripts.actor_corpus_ibes --score
```
Receipts: `backend/data/optimus/actor_corpus/{build_receipt,score_receipt}.json`

---

## 1. Why this exists

`actor_intelligence.py` shipped as an estimator with nothing to estimate from.
The whole "inverse Cramer" idea rests on an untested premise: **that an actor's
track record predicts their next call.** If reliability does not persist out of
sample, the entire actor layer is worthless no matter how good the statistics
are. This tests that premise on the only clean, timestamped, already-on-disk
actor corpus: IBES analyst recommendations.

Commentators — the actual inverse-Cramer case — come last, not first. There is
no clean public feed of timestamped calls, so that is an ingestion problem, not
a statistics one.

## 2. Corpus

`ibes__recddet`: 3,261,102 recommendations → **98,772 graded claims** from
**5,793 analysts**, 2013–2024.

- **Direction:** `ireccd` 1–2 → +1, 4–5 → −1. **`3` (hold) is dropped**, not
  bucketed as a weak buy — scoring it would build a record out of the times an
  analyst declined to make a call. 101,991 holds dropped and counted.
- **Timestamp:** a rec announced at or after the 16:00 close is not actionable
  at that close, so the position opens at the **next** session. `anndats`
  (public) and `actdats` (when IBES recorded it) are both carried; the gap is
  reported, never assumed zero.
- **Scope, declared:** US firms only (`usfirm == 1`). IBES covers international
  issuers and CRSP does not — measured, `usfirm=0` links at **0.1%** and
  `usfirm=1` at **74.0%**, and 80% of the window is non-US. An unfiltered merge
  silently drops four rows in five and reports a "14.6% link rate" that looks
  like a broken join and is a universe mismatch. The build now **refuses**
  below a 60% link rate within the US subset.

## 3. The benchmark was the whole result

First pass benchmarked against the equal-weighted CRSP market. It produced a
striking result, and the result was an artifact:

| | EW-market benchmark | **SIC2 sector benchmark** |
|---|---|---|
| buy calls, hit rate | 0.4657 | **0.5666** |
| buy calls, mean 63-day excess | **−3.67%** | **+1.43%** |
| sell calls, hit rate | — | 0.4472 |
| sell calls, mean excess | — | +0.77% |

Under the market benchmark *every* analyst buy call underperformed, and the
inverse gate licensed three analysts who turned out to be **37–56% concentrated
in a single SIC2** (mostly pharma/chemicals). That was never analyst skill: it
was sector and size exposure. Analysts cover larger, growthier names while an
equal-weighted CRSP market is dominated by small caps, so the comparison
answered a question nobody asked.

**This is the house failure mode — correct arithmetic against the wrong
world — caught in flight.** Grading each call against its own SIC2 division
over the same window flips the sign and makes the question the one a
recommendation actually asserts: *did this name beat its sector?*

Second correction, same shape: buy and sell claims resolve in their favour at
different base rates (0.567 vs 0.447), so each analyst is graded against **their
own direction mix**. A pure-buy analyst scored against a blended null is
credited with the buy/sell base-rate gap as if it were skill — and every
"inverse" licensed in the first pass was a pure-buy analyst, which is exactly
the shape that error produces.

## 4. The result: reliability persists

Split by **time**, not at random (2013–2020 train, 2021–2024 holdout — a random
split leaks, because one analyst's calls are correlated within a quarter).

**Amended 2026-08-24.** The first version of this section reported one number,
`0.516 over n = 50`, without naming the rule that selected 50 analysts out of
222: a minimum of **30 graded claims in the holdout**. Unrestricted, the same
split gives 0.25. Reporting only the filtered rung left a reader unable to tell
attenuation from selection, so the whole ladder is now in the receipt
(`score_receipt.json` → `persistence.by_min_holdout_claims`) and reproduced
here. (Numbers also shift in the fourth decimal from the announcement-time fix
described in §7.)

| min holdout claims | n analysts | corr(train, holdout) | 95% CI |
|---|---|---|---|
| 0 (all) | 222 | **0.253** | [0.125, 0.372] |
| 10 | 171 | 0.329 | [0.188, 0.457] |
| 20 | 105 | 0.400 | [0.226, 0.550] |
| 30 | 50 | **0.513** | [0.273, 0.692] |
| 40 | 20 | 0.453 | [0.014, 0.746] |
| 50 | 10 | 0.739 | [0.205, 0.934] |

**Every rung's interval excludes zero.** The premise survives at any threshold;
only its magnitude depends on one. The ladder is monotone in holdout evidence
up to the point where n collapses, which is the signature of **attenuation** —
an analyst whose holdout edge rests on six calls contributes a very noisy `y`,
and noise in `y` pulls `r` toward zero. It is not selection on the outcome: the
filter is on holdout *precision*, never on holdout *result*, so it cannot pick
analysts for having persisted.

Read conservatively, the honest headline is the **unrestricted 0.25**, with the
better-measured subsets suggesting the true figure is higher.

| train-edge quintile | train | → holdout |
|---|---|---|
| Q1 (worst) | −0.154 | **−0.093** |
| Q2 | −0.040 | +0.004 |
| Q3 | +0.000 | −0.010 |
| Q4 | +0.032 | +0.003 |
| Q5 (best) | +0.108 | **+0.032** |

Both tails persist, and **the negative tail persists more strongly**:

- train edge < −0.05 (n=15) → holdout **−0.065**
- train edge > +0.05 (n=9) → holdout **+0.041**

**An actor's track record predicts their next call.** That is the premise the
whole actor layer rests on, and it holds.

## 5. What the strict gate licensed

Applying all four `inverse_license` conditions — ≥5pp deficit, BH-FDR across
every actor considered (m = 254), ≥20 independent decision days, and a holdout
that repeats the deficit:

- **7 analysts licensed for INVERSE**, holdout deficits −0.08 to −0.20;
- **0 analysts licensed on the mirror-image "follow" side.**

That asymmetry is not because the raw distribution is skewed — it is symmetric
and correctly centred (mean edge −0.003, median −0.000; 67 analysts below
−0.05, 62 above). It is because **being reliably wrong persists harder than
being reliably right**, which §4 measures directly. A plausible reading is that
good analysts are competed away — promoted, poached, or their calls arbitraged
— while a systematic bias just keeps operating. That reading is a hypothesis,
not a result.

## 6. What this does NOT show

- **Not tradable.** Direction-only hit rate. It says nothing about magnitude,
  timing, position sizing, capacity, or transaction costs. A 6pp hit-rate edge
  on 63-day horizons is not a strategy.
- **One split, not walk-forward.** 2013–2020 → 2021–2024 is a single holdout.
  The persistence estimate is threshold-dependent (§4): 0.25 over all 222
  analysts, 0.51 over the 50 with ≥30 holdout claims. Every CI excludes zero;
  none of them is narrow.
- **Sector benchmark is coarse.** SIC2 divisions, equal-weighted. No size,
  value or momentum adjustment — a within-sector size tilt would still leak in.
- **Analyst identity is `amaskcd`.** It survives broker moves, which is what we
  want, but a shared or reassigned code would blur two people into one.
- **No claim about any named individual.** These are anonymised analyst codes,
  and nothing here should be read as a statement about a person.

## 7. What follows

The premise holds, so the actor layer is worth continuing. In order:

1. **Walk-forward** the persistence estimate — one split is not an evidence
   clock. This is cheap and it is the honest next step.
2. **Magnitude, not just direction.** Grade on excess return, not a hit-rate
   coin flip; a `RESEARCH_CLAIM` needs the economic size.
3. **Extend the corpus** — Form 4 insiders and 13F institutions via the
   existing collectors. `disclosure_lag_days` already exists on the record
   precisely because a 13F is public ~45 days after the trade, and grading from
   the trade date would credit foresight no follower could act on.
4. **Only then commentators**, and only if a timestamped feed can be ingested
   with provenance. The event store is the right home for that.

## 7. Amendment 2026-08-24 — the announcement-time rule

The corpus dated a recommendation to the next session whenever `anntims` was at
or after the 16:00 close. Two things were wrong with how "unknown" was handled:

* `.astype(str).fillna("00:00:00")` fills nothing — `astype(str)` has already
  turned a missing stamp into the string `"NaT"` — and the hour was then
  coerced to `0`, i.e. **pre-market**, i.e. tradable at that same session's
  open. Measured: **0 rows** in this window are actually unreadable, so this
  changed nothing here. It was a guard that did not guard.
* **Exactly `00:00:00` is a placeholder, not a time.** 3,168 US rows carry it,
  while the rest of hour 0 spreads across the minute field (00:16, 00:17,
  00:02 …) the way real stamps do, and the midnight share falls monotonically
  from 5.5% of 2013 to 0.1% of 2024 — a legacy default being retired. Read as
  a time it means pre-market, and an after-close release would have been graded
  from a price that preceded it.

Both now take the **next** session. 1,234 claims moved by one session.

**The result is unchanged.** The same seven analysts are licensed for INVERSE,
with the same holdout deficits to three decimals; edges move in the fourth. The
corpus row counts are identical — the rule changes which open a claim is graded
from, not whether it is graded. This is recorded because a PIT fix that turns
out to change nothing is still worth the receipt: the alternative is discovering
later that nobody knows whether it mattered.
