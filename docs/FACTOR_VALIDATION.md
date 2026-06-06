# Factor Validation — Do the Grades Actually Predict?

Chunk 2 of the 2026-06 roadmap: *validate, don't build*. The five-factor
report card (`factor_grades.py`) grades Value / Growth / Profitability /
Momentum / Revisions A+→F. This document measures whether those grades carry
out-of-sample predictive skill — applying the same honest-measurement
discipline as the overfitting guards (`METHODOLOGY.md §1.5`).

Method: Information Coefficient analysis computed directly (no Alphalens
dependency) via `engine/validation/factor_ic.py` — per-date cross-sectional
Spearman rank correlation of factor vs forward return, summarized across
dates (mean IC, IC IR, t-stat, hit rate) plus a quantile forward-return
spread. Rule of thumb: a usable equity factor shows |mean IC| ≈ 0.02–0.05
with a t-stat ≥ 2; near-zero IC means the grade is descriptive, not predictive.

## What we could validate, and what we could not

| Factor | Source | Historically reconstructable without look-ahead? | Validated here |
|---|---|---|---|
| **Momentum** | price history | **Yes** — prices are point-in-time by nature | ✅ Yes |
| Value | fundamentals (P/E, P/B, …) | No — needs as-filed point-in-time fundamentals | ❌ Deferred |
| Growth | fundamentals (rev/EPS growth) | No | ❌ Deferred |
| Profitability | fundamentals (ROE, margins) | No | ❌ Deferred |
| Revisions | Piotroski + estimate trend | No | ❌ Deferred |

**Why the four fundamental factors are deferred (not skipped).** A rigorous IC
test needs a *panel* of factor values as they were known on each past date.
The only fundamentals history available to us is **restated** (yfinance) or
non-point-in-time / rate-limited (FMP) — using it would bake in look-ahead
bias, the exact error this project exists to avoid. A correct test requires a
point-in-time fundamentals panel (as-filed SEC EDGAR across the universe over
time). Building that is a data-engineering task, deliberately out of scope for
a "validate, don't build" chunk. **This is a prerequisite, logged here as a
known gap — not a passed test.**

## Momentum — results

Harness: `engine/validation/validate_momentum.py`
(`python -m engine.validation.validate_momentum`). Universe = the live
~178-name watchlist + sector lists. Window = trailing 6 years. Forward
horizon = 21 trading days, sampled on **non-overlapping** monthly rebalances
(59 periods, 10,532 observations). Two definitions compared:

- **`composite`** — the factor the grade uses today: a weighted blend of
  1M/3M/6M/12M trailing returns (weights 0.10/0.25/0.35/0.30).
- **`mom_12_1`** — textbook Jegadeesh-Titman momentum: the 12-month return
  that **skips the most recent month** (short-term returns mean-revert).

| Metric | `composite` (current grade) | `mom_12_1` (textbook) |
|---|---|---|
| mean IC | 0.0024 | 0.0147 |
| IC t-stat | 0.08 | 0.54 |
| p-value | 0.94 | 0.59 |
| IC hit rate | 54.2% | 59.3% |
| top−bottom quintile (monthly) | +0.20% | +0.81% |
| monotonic quintiles | no | no |
| verdict | **no measurable skill** | weak, not significant |

### Findings

1. **The current composite momentum grade has essentially no predictive
   skill** on this universe/window (IC 0.0024, t 0.08 — indistinguishable
   from noise).
2. **The 1-month component is dilutive.** Textbook 12-1 momentum has ~6× the
   IC and ~4× the quantile spread of the composite. Including the recent
   1-month return — which exhibits *reversal*, not continuation — drags the
   signal toward zero. This matches the literature (momentum is conventionally
   measured 12-1).
3. **Even 12-1 is not statistically significant here** (t 0.54). The IC is
   weakly positive and the top quintile does earn the most, but month-to-month
   IC is very noisy (IC std ≈ 0.21) on a ~178-name mega-cap set over a
   momentum-hostile 2020–2026 (COVID V-reversal, 2022 bear, sharp rotations).

### Caveats (why this is a floor, not a verdict on momentum-as-a-factor)

- **Universe**: a curated large/mega-cap watchlist, not a broad cross-section.
  Momentum is historically strongest in broad, smaller-cap universes; it is
  weak among mega-caps.
- **Window**: 6 years / 59 monthly periods is short, and this particular window
  is unusually unfriendly to momentum.
- **Survivorship**: the universe is *current* membership (look-ahead in
  composition) — see the survivorship diagnostic planned for Chunk 3.

## Recommendation

- **Reduce or remove the 1M weight** in `cross_sectional_momentum` (move the
  composite toward the 12-1 / skip-month definition). The evidence that the 1M
  component hurts is unambiguous; this is a strict improvement even though it
  does not, by itself, make momentum a validated predictor here. *(Proposed —
  changes live grade behavior, so applied only on approval.)*
- **Label the momentum grade as descriptive relative-strength, not a validated
  alpha signal** on the current universe, until tested on a broader cross-section.
- **Build the point-in-time fundamentals panel** before claiming predictive
  skill for Value/Growth/Profitability/Revisions. Until then the four
  fundamental grades are presented as peer-relative descriptors, not validated
  predictors.

The honest headline: of the five graded factors, only momentum is testable
today, and as currently defined it does not predict forward returns on this
universe. That is a credibility-building negative result — and it points to a
concrete, low-risk fix (drop the 1M reversal term).
