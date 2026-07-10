# TRIAL-PEAD-IC — post-earnings-announcement drift as a forward IC trial

> Pre-registered 2026-07-09, **before any forward data accrued** (the collector
> ships in the same commit as this doc; the first snapshot lands on the next
> deploy's daily check). The git timestamp is the tamper evidence. Changing the
> hypothesis, metric, or thresholds after data accrues invalidates the trial.

## Hypothesis

Cross-sectionally, a fresher/larger earnings surprise — measured two ways and
combined (analyst-forecast surprise % AND 3-day announcement-window return in
excess of SPY; strongest when aligned, per the two-way-sort literature) —
predicts higher forward returns over 21/63 trading days within the tracked
universe.

**Honest prior (stated before data):** weak-to-moderate. The verified research
(docs/research/ENGINE_GAPS_2026_07_09.md) says US PEAD has been *declining*
through the 2010s, is concentrated in small/high-cost names, and is disputed
net-of-cost in liquid large caps — which our universe tilts toward. A null
result is a publishable outcome. The claim that PEAD is independent of
momentum was REFUTED in verification — correlation with the momentum sleeve is
reported alongside the IC, not assumed away.

## Signal definition (frozen)

`backend/services/pead_signal.py::compute_pead_score` — mean of two clipped
components: surprise% / 10 and abnormal-3d-return / 0.10, each clipped to
[-1, 1]; zero with an explicit status when the last reported announcement is
older than 90 days or components are unavailable. Parameters
(MAX_AGE_DAYS=90, window=3td, scales 10%/10pts) are frozen at these defaults —
no tuning during the trial.

## Decision rule

- **Primary metric:** forward rank-IC (Spearman) of `pead_score:{ticker}` PIT
  snapshots vs realized forward returns at **21 and 63 trading days**, with
  bootstrap CI, via the existing `forward_ic` scorecard. All-zero snapshot
  periods (throttle/stale artifacts) are excluded, as with the other IC trials.
- **Secondary (reported, never deciding):** IC at 126td; rank correlation of
  the score with the momentum score (the subsumption check); IC conditional on
  `two_way_aligned`.
- **Adoption threshold:** IC > 0 with CI excluding 0 at BOTH primary horizons
  on a matured forward window — then, and only then, candidacy for any
  composite goes through `evaluate_candidate` (DSR/PBO deflated against the
  cumulative trial count).
- **Reject/park:** CI straddles 0 after ≥ 26 weeks of matured snapshots →
  parked as a measured negative result in NEGATIVE_RESULTS.md.
- **Hard constraints:** descriptive-only; never arms a lane; no buy/sell
  language anywhere it surfaces; NOT added to the in-flight TRIAL-MULTIFACTOR
  composite (that trial's definition is frozen — a v2 composite would be its
  own pre-registered trial).

## What this rule may NOT do

No metric substitution, no horizon cherry-picking after data accrues, no
re-scaling the components to improve the read, no retroactive universe
changes. Annotations documenting engine properties are permitted; rule changes
are not.
