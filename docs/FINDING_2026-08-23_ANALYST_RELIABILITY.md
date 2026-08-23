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
Analysts with ≥50 train and ≥30 holdout calls, n = 50:

> **corr(train edge, holdout edge) = 0.516, 95% CI [0.277, 0.694]**

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
  The persistence estimate rests on **n = 50 analysts**, and the CI is wide.
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
