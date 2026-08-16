# PREREG — N4B: can the six-rule library's coverage lift be RULED OUT below the level at which it would pay?

**Registered:** 2026-08-16, before the equivalence statistic exists. The
descriptive lift point estimates from N4 (`a6ff2ff`) are already public and are
*not* re-estimated here as if they were new; what is new is the **margin**, the
**standard error** and the **decision rule**, none of which existed before this
document.

**Resurrects:** N4 — new instrument: a one-sided non-inferiority test against an
economically derived margin, replacing a below-MDE null that was reported as an
absence.

## Why this exists

N4 measured pooled coverage lift of 0.82–1.15 against MDEs of 0.25–0.62 and the
script printed `NO COVERAGE`. That is the project's own named failure mode:
failure to separate an estimate from 1.0 is a statement about the instrument.
The correct negative — if there is one — has the form *"we can rule out the
lifts that would have mattered"*, and it needs a margin chosen from economics
before the interval is looked at.

## The margin, derived from economics and NOT from available power

The library's only action is: **when any precursor fires, cut equity exposure
by δ for H days.** So its value is decided by three measured quantities and one
cost assumption, none of which involve the lift.

With `q = P(bottom-decile move) = 0.10` by construction and `p = P(any
precursor fires)` measured, Bayes gives the precision directly:

```
P(tail | fire) = P(fire | tail) · q / p = L · q
```

— a lift of L means the warning is right `10·L`% of the time. De-risking pays
when the tail loss avoided exceeds the upside forgone plus the round-trip cost:

```
L · q · |μ_tail|  >  (1 − L · q) · μ_rest  +  c
```

which solves to the **minimum economically meaningful lift**:

```
L_min = (μ_rest + c) / ( q · (|μ_tail| + μ_rest) )
```

where `μ_tail` is the mean H-day return in the bottom decile, `μ_rest` the mean
H-day return outside it, and `c` the round-trip cost of the exposure change.

**Declared before running:** `c = 0.10%` per round trip (liquid ETF, paper-lane
realistic). `μ_tail` and `μ_rest` are properties of the unconditional return
distribution of each security — they are measured from the same price history,
they do not depend on the precursor library in any way, and they cannot be
tuned by anything the test discovers. `L_min` is computed per (security,
horizon) and pooled the same way the lift is.

This is deliberately the *opposite* procedure to the one order 3 warned about.
The margin is not 1.25 because 1.25 happens to be reachable, and it is not 10pp
because 25 episodes can see 10pp. It is whatever the return distribution says it
must be, and if that number turns out to be unreachable then the honest verdict
is that this design cannot certify the library — which is itself the finding.

## Hypothesis

**H0 (the thing we try to rule out):** the library's true coverage lift is at
least `L_min` — i.e. firing carries enough information about the tail for
de-risking on it to be worth the forgone upside.

**H1:** true lift is below `L_min`.

## Primary statistic

One-sided 95% upper confidence bound on pooled lift, per (horizon, tail),
against `L_min` for that cell:

```
RULED_OUT  iff  lift_hat + 1.645 · se(lift_hat)  <  L_min
```

`se` comes from a **moving-block bootstrap over episodes**, block length = the
horizon, resampled within each security and pooled across securities — because
six co-moving ETFs are not six independent measurements (§41: pooling them
previously manufactured confidence without moving the estimate).

## Decision rule (pre-committed)

| outcome | verdict |
|---|---|
| upper bound < `L_min` at **both** horizons on the **bottom** tail | `REFUTED_IN_SCOPE` — the library is refuted **as a de-risking trigger**, its declared purpose. It is not refuted as anything else. |
| upper bound < `L_min` in some cells only | `REFUTED_IN_SCOPE` in those cells, reported cell by cell, nothing pooled to a headline |
| upper bound ≥ `L_min` anywhere | `NOT_DEMONSTRATED` in that cell — neither coverage nor its absence established |
| `L_min` inside the bootstrap spread of the lift estimate itself | `UNPOWERED_IN_SCOPE` — this design cannot certify the library either way, and says so |

**Sensitivity, reported always, not only when convenient:** the whole table
recomputed at `c = 0` and at `c = 0.25%`, and at block lengths of H/2, H and 2H.
If the verdict is not stable across that range, the reported verdict is the
weakest one in it (review §14: report the robust decision, do not pretend the
dependence structure is known).

## What this cannot conclude

* Nothing about mechanisms **individually**. This is a property of the library
  as a whole, at its own base firing rate.
* Nothing about **other actions**. A lift too small to justify de-risking may
  still be worth something to a policy with different economics (sizing rather
  than exit, for instance). The verdict names the action.
* Nothing about **coverage that could exist**. Refuting the six rules says
  nothing about the 85% of moves they never marked, which is N9's territory and
  is a generation problem, not an adjudication one.

## R13 — resolvability, declared before compute

Expressed in coverage percentage points, since lift is a ratio: at base rate
15.3%, a lift of `L` is a coverage difference of `15.3·(L−1)` pp. The margin
`L_min ≈ 2` therefore corresponds to a declared effect of ~15pp of coverage, and
the observed cell-to-cell dispersion of coverage is ~2.3pp.

- event_frequency_per_year: 2
- declared_effect_size: 15pp
- outcome_dispersion: 2.3pp
- corpus_years: 27

## Run spec (frozen)

`python -m scripts.n4b_coverage_equivalence` — universe SPY QQQ IWM XLF XLE XLK,
1999-01-01 to 2026-08-15, tail quantile 0.10, horizons 20 and 60, precursors
compiled from the same autopsy file N4 used, 2000 bootstrap resamples, seed
frozen in the script. ONE run. The result is final for this trial.

## Result (filled in AFTER the run — never edited afterwards)

Run 2026-08-16. 6,591 shared trading days, 2000-05-31 → 2026-08-14, six
securities, 2,000 bootstrap resamples per block length, seed 20260816.

| H | tail | lift | precision | se | upper 95% bound | `L_min` | verdict |
|---|---|---|---|---|---|---|---|
| 20d | bottom | 0.954 | 9.5% | 0.184 | **1.257** | **1.69** | `RULED_OUT` |
| 60d | bottom | 0.808 | 8.1% | 0.259 | **1.234** | **2.11** | `RULED_OUT` |
| 20d | top | 1.179 | 11.8% | 0.235 | 1.565 | (0.09) | descriptive only |
| 60d | top | 1.117 | 11.2% | 0.319 | 1.642 | (0.33) | descriptive only |

**Verdict: `REFUTED_IN_SCOPE` — the six-rule library is refuted AS A DE-RISKING
TRIGGER**, at both horizons, on the tail it was built from. Stable across all
nine sensitivity combinations (cost 0 / 10bp / 25bp × block H/2, H, 2H), so the
robust verdict and the headline verdict are the same one.

In plain terms: when a precursor fires, a bottom-decile move follows **9.5%**
of the time at twenty days. Break-even for cutting exposure is **16.9%**. The
signal is not weak — it is on the wrong side of the line, and the upper bound of
its interval does not reach the line either.

**Self-correction made during the run, before reading the bottom tail.** The
first run adjudicated all four cells and returned `AT_LEAST_MARGIN` on both top
tails. That was an artefact: `L_min` is derived from de-risking economics, the
top tail's `mu_rest` is ≈0 or negative, so the margin collapses to 0.09–0.33 and
any lift clears it. Two of the four cells would have been reported as the
library *working*. The top tail has a different action and therefore a different
margin; it is now marked `margin_applicable: false` and reported descriptively,
as N4 reported it. **§37 — a new instrument's first POSITIVE is the one that
looks like it working.**

- Receipt: `backend/data/optimus/research_gym/n4b_coverage_equivalence.json`
- Script: `scripts/n4b_coverage_equivalence.py`

**What this does NOT close.** Nothing about individual mechanisms; nothing about
other actions (sizing rather than exit has different economics and is untested);
and nothing about the 85% of exceptional moves the library never marked, which
is a generation problem (N9), not an adjudication one.
