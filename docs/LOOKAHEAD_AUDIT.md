# LOOKAHEAD AUDIT — new V3 code (forward_ic, exposure_multiplier, cross_asset_rotation)

**Date:** 2026-06-20 · **Scope:** the three new numeric/data modules from Chunks 4–6.
**Question per path:** is every value point-in-time (PIT) at decision time? No full-series
statistic evaluated at a point, no restated fundamentals, no survivorship in the universe? And
does the `data_grade` stamp reach every backtest result with no un-stamped path?

Legend: ✅ clean · ⚠️ suspect (conditionally safe — note the condition) · ❌ leak.

---

## 1. `forward_ic.py`

| Path / input | Verdict | Reasoning |
|---|---|---|
| factor value (`build_signal_panel`) | ✅ clean | Read via `db.get_series_observable(key, as_of_ts)` which filters `observed_at <= cutoff` and takes the latest revision per `as_of` — the leak-free read contract. The factor is what was KNOWN. |
| forward return (`_forward_return`) | ✅ clean | Entry = last close `<= as_of` (`searchsorted(..., 'right')-1`); exit = entry + `horizon_days` (strictly future). The future leg is the realized LABEL, not an input — correct, not lookahead. |
| price source for the label | ⚠️ suspect→accepted | Prices come from yfinance → survivorship-biased + adjusted. This makes the label DIRECTIONAL, which is exactly why `score_forward_ic` stamps `data_grade` (directional). Acceptable: forward-IC of held signals is a directional read by design. |
| universe of tickers scored | ✅ clean (for intent) | Tickers come from the PIT store (T8/T9/T10 = the actual book names). It is the held universe, not a survivorship-free cross-section — correct for grading the signals we actually collect. |
| `score_forward_ic` NaN handling | ✅ clean (post-fix F2) | NaN factor/fwd rows dropped before the sufficiency gate; degenerate → `insufficient_history`. |

**Net:** no lookahead. The only caveat is the directional grade of the realized-return leg,
which is explicitly stamped.

## 2. `exposure_multiplier` (in `fragility.py`)

| Path / input | Verdict | Reasoning |
|---|---|---|
| `composite` scalar argument | ✅ clean (live use) | A single fragility reading; the function itself does no time-series math. Bounded + monotonic + NaN-safe (post-fix F1). |
| **origin of `composite`** = `compute_fragility_index` | ⚠️ suspect-IF-BACKTESTED | `_pct_rank(series, value)` ranks the current value against the **full series** (`(s <= value).mean()`). For the LIVE descriptive reading the "full series" is data up to now → no peek. But if the composite is ever computed at a PAST `as_of` with a full series that extends beyond `as_of`, the percentile would use future points = lookahead. compute_fragility_index is pre-existing and currently LIVE-ONLY (never in a backtest path), so clean today — but any future backtest of the composite MUST as-of-slice its inputs first. → IMPROVEMENT_BACKLOG B5. |
| use of the multiplier | ✅ clean | Descriptive only; no live lane consumes it (no decision path exists yet). |

**Net:** clean for its current live/descriptive use; the percentile-rank in the upstream
composite is a latent lookahead that bites only if the composite is backtested — flagged.

## 3. `cross_asset_rotation.py`

| Path / input | Verdict | Reasoning |
|---|---|---|
| `asset_returns` window | ⚠️ suspect→caller-responsibility | `inverse_vol_weights` takes `std` over whatever window the CALLER passes. Pure function; leak-safety depends on the caller passing an as-of-sliced window (exactly as `replay` slices via `MarketDataAtTimestamp`). There is NO caller yet (lane deferred), so no leak today; the contract must be enforced when a lane is built. Documented in the module docstring. |
| `fragility_composite` input | ⚠️ inherits §2 | Same percentile-rank caveat as the composite. |
| `data_grade` of any rotation backtest | ⚠️ see §4 | A future rotation lane backtest must carry the directional stamp (ReplayResult already does). |
| weight math | ✅ clean | No time-series statistic beyond the passed window; degenerate inputs → `{}` (no silent NaN). |

**Net:** pure and leak-free by itself; PIT-safety is a documented caller contract because no
consumer exists yet.

## 4. `data_grade` stamp coverage (no un-stamped backtest path?)

| Result object | Stamped? | Verdict |
|---|---|---|
| `ReplayResult` (replay.py) | ✅ yes | `data_grade=di.data_grade(DEFAULT_PRICE_SOURCE)` set on every result; default field value also "directional". |
| `forward_ic_scorecard` / `score_forward_ic` | ✅ yes | Every return carries `data_grade`. |
| `evaluate_candidate` / `rule_evolution` verdict | ❌ un-stamped | The DSR/PBO **verdict** dict (pre-existing modules) carries no `data_grade`, so a verdict from a directional backtest reads as gradeless. **Suspect path** → IMPROVEMENT_BACKLOG B2. Not a leak, but a stamp-coverage gap. |

---

## Summary
- **No actual lookahead leak** in the three new modules as currently used.
- Two **conditional** risks, both flagged to the backlog: (B5) the fragility composite's
  full-series percentile rank would leak if ever backtested without as-of slicing; (caller
  contract) the rotator's return window must be as-of-sliced by whatever lane consumes it.
- One **stamp-coverage gap** (B2): the candidate DSR/PBO verdict doesn't carry `data_grade`.
- The realized-return leg of forward-IC is directional by design and is explicitly stamped.
