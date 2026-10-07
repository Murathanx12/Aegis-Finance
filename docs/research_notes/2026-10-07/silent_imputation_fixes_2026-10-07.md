# Q15 — making three silent FRED imputations loud, with tests (2026-10-07)

Builder session following Q14 (`fred_production_2026-10-07.md`: production's
FRED key is unregistered; `fred_macro_inputs` now pages on it). This session
does not touch Railway, `.env`, or the key — it is the second, disclosure-side
half of that diagnosis: what the three consumers Q14 named do WITHOUT FRED
data, made loud instead of silent, with tests pinning the new behaviour.

## 1. `backend/services/fixed_income.py`

**Before:** `get_fixed_income_dashboard()` opened its own raw
`fredapi.Fred(os.getenv("FRED_API_KEY", ""))` client — a second, unaccounted
FRED path invisible to `fred_health`, `observability.source_health()`, and the
`fred_macro_inputs` probe. `compute_credit_spread_analysis()` fell through to
`stress.level = "normal"` whenever `spreads` had no `hy_oas`/`ig_oas` entry
(FRED empty) — absence of a credit read reported as a calm credit market.

**After:**
- `get_fixed_income_dashboard()` now fetches every yield-curve/credit series
  through `backend.services.providers.registry.get_macro_series()` (the same
  FRED abstraction `fx_curves.py` already used) and calls
  `fred_health.record_success()` / `record_miss()` explicitly per series
  (keyed by the raw FRED series id, e.g. `"DGS10"`, `"BAMLH0A0HYM2"` — these
  are NOT in `config["data"]["fred_series"]`'s 23 friendly names or
  `CRITICAL_FRED_SERIES`, so this registration is additive and does not
  perturb the existing `fred_macro_inputs` probe or `degraded_reasons()`,
  which stay scoped to the 23-series pass `DataFetcher.fetch_fred_data()`
  already owns). A failure here is now visible in
  `fred_health.series_status(names=[...])`.
- The dashboard return now carries `"degraded": bool` and
  `"missing_series": [...]` (friendly names, e.g. `"hy_oas"`) at the top
  level, so a caller does not have to infer health from the shape of
  `yield_curve`/`credit`.
- `compute_credit_spread_analysis()`: when neither `hy_oas` nor `ig_oas` is in
  `spreads`, returns `stress: {"level": "UNKNOWN", "signals": [],
  "missing_because": "..."}` instead of `"normal"`.
- `backend/routers/analytics.py` `GET /api/analytics/fixed-income`: a
  `degraded` response is no longer written to the 30-minute cache (a
  transient FRED miss must not be force-served to every caller for the next
  half hour); the response body still carries `degraded` either way — a 200
  is not a claim of health.

**Tests:** `backend/tests/test_fixed_income.py`
(`TestCreditSpreadAnalysis::test_empty_spreads_is_unknown_not_normal`,
`test_partial_spreads_without_credit_series_is_unknown`,
`TestGetFixedIncomeDashboard` — all-unavailable / all-available / partial
cases, asserting `degraded`, `missing_series`, and `fred_health` registration)
and the new `backend/tests/test_fixed_income_router.py` (router surfaces
`degraded`; a degraded read is not cached; a healthy read is).

## 2. `backend/services/fx_curves.py`

**Before:** `fetch_short_rate()` returned a bare `float | None` and silently
substituted `DEFAULT_USD_RATE = 0.04` for USD on ANY failure (unkeyed FRED,
empty series, exception), while `forward_curve()`'s `method` field still
claimed `"Covered interest parity (act/360) using FRED short rates"` even
when the rate used was the hardcoded constant.

**After:** `fetch_short_rate()` now returns
`{"rate": float | None, "source": "FRED" | "DEFAULT_CONSTANT" | "UNAVAILABLE",
"missing_because": str | None}`. `forward_curve()` reads `.rate` for the CIP
math, sets `degraded = True` whenever either leg's source is not `"FRED"`,
carries `rates.base_rate_source` / `rates.quote_rate_source` +
`missing_because`, and only prints the "using FRED short rates" `method`
string when BOTH legs actually came from FRED — the degraded case says so
explicitly ("...NOT a FRED read; see rates.*_rate_source"). `fx_dashboard()`
propagates a per-row `"degraded"` flag.

**Downstream consumers, checked:** grepped every caller of
`fetch_short_rate` / `forward_curve` / `fx_dashboard` repo-wide. Only
`backend/routers/markets.py` (`GET /api/markets/fx`, `GET /api/markets/fx/
{pair}`) calls them, and it returns the service dict unmodified — the
`degraded` flag reaches its response automatically. `backend/services/
portfolio_currency.py` (the one other FX consumer) uses `fetch_spot` only,
never `fetch_short_rate`, so it is unaffected and carries no pricing/sizing
dependency on the rate leg today. No consumer silently ignores the flag;
none needed a receipt change beyond what the service now returns.

**Tests:** `backend/tests/test_fx_curves.py` — updated all five existing
monkeypatches from a bare-float `fetch_short_rate` stub to the new dict
contract, and added `test_forward_curve_default_constant_is_disclosed` and
`test_fx_dashboard_rows_disclose_degraded_rate`.

## 3. `backend/services/data_fetcher.py` — `get_recession_probability`

**Before:** returned a bare `0.15` ("`# Default base rate`") with no marker
that it was a fallback when no FRED signal was present at all.

**Confirmed dead code** (re-verified this session, same as Q14's finding):
grepped repo-wide for `.get_recession_probability(` — zero matches outside
its own definition. Not in `backend/services/signal_reachability.py`'s
classification registry either. **Deleted** rather than instrumented: dead
code carrying a silent-imputation trap is worse than no code, because the
next caller to wire it up would inherit the exact failure mode with no test
or health row in the way. A comment at the deletion site records the
decision and the shape a revival should use (`{"probability": ...,
"signals_used": [...], "missing_because": ...}`).

**Test:** `backend/tests/test_fred_health.py::
test_get_recession_probability_was_removed_as_dead_code` pins the removal
(`not hasattr(DataFetcher, "get_recession_probability")`).

### Its sibling, `get_macro_features` — same shape, NOT touched

Also dead (no live caller; re-confirmed by grep this session). Left alone
deliberately: it *skips* an absent key rather than fabricating a value — a
materially smaller failure mode (same family as the already-documented
22/23-reads-as-fine incident in `fred_health.py`'s own docstring), and it is
dormant, so the risk is not active. Pinned by
`test_get_macro_features_still_has_no_live_caller` (an AST-free text grep for
a real call site, `\.get_macro_features\s*\(`, excluding doc/comment
mentions) so a future caller re-opens this decision instead of it silently
staying unreviewed.

## 4. Grep sweep for the same shape elsewhere in FRED consumers

Grepped every file importing `fredapi`, `FRED_API_KEY`, `get_macro_series`,
or `fetch_fred_data` (20 files) for `except Exception: return <constant>` and
`fillna(0)` on macro series. No `fillna(0)` hits anywhere in this set.
Per-file verdict:

**Already clean / disclosed (no fix needed):**
- `backend/services/market_sensor.py` — raises `SensorRefused` (per Q14).
- `backend/services/net_liquidity.py` — `_default_response(error=...)`,
  `signal: "UNKNOWN"` (per Q14).
- `backend/services/macro_calendar.py` `_fred_get()` — raises `MacroRefused`
  on every failure path (no key, network error, non-200, bad JSON); never
  returns `{}`.
- `backend/services/bond_analytics.py` (Treasury ladder yields via
  `registry.get_macro_series`) — returns `{"error": "no Treasury data
  available (FRED unkeyed?)"}` when nothing loaded; never a fabricated curve.
- `backend/services/valuation.py` (ERP real-yield leg) — `real_yield` stays
  `None` on any FRED exception; `erp` is only computed when both legs are
  present, so a FRED miss removes the field rather than injecting a value.
- `backend/services/portfolio_intelligence/fragility.py` (fragility
  composite's `sos`/`hy_oas`/`ig_oas` components) — every component is
  `_add(key, None)` on failure, `available` is tracked explicitly, and the
  composite is the mean of only the `available` components (`status:
  "no_inputs"` when none are); the Sahm/SOS reader
  (`backend/services/macro_indicators.py::_sahm_from_fred`) returns
  `{"status": "no_data", "value": None, "triggered": None}` rather than a
  fabricated flag.
- `backend/services/portfolio_intelligence/fragility_candidates.py`
  (`_fred_stress_percentile`) — raises `ValueError("FRED_API_KEY not set")`;
  no silent fallback.
- `backend/services/options_pit_store.py::risk_free_simple()` — already the
  house-style good example: returns `(value, source_string)` and the
  `source_string` is literally `"declared fallback"` vs
  `"FRED:fed_funds=..."` — this is the same disclosure shape items 1-2 above
  now also implement, pre-existing and correct.

**Owed, NOT fixed this session (flagged, scope reasons given):**
- **`backend/services/portfolio_intelligence/nav.py::get_rf_daily()`** —
  same shape as `fx_curves.DEFAULT_USD_RATE` before today's fix: on ANY FRED
  failure it silently substitutes `annual_fallback` (default `0.04`),
  disclosed only via a `logger.info`/`logger.warning` line, **not** in the
  return value (`-> float`), and the result is cached forever in a
  process-global `_RF_CACHE` dict with no TTL — one cold-start failure locks
  in the fallback for the process's lifetime. Live caller:
  `backend/routers/portfolio_intelligence.py:855`
  (`ReplayEngine().run(..., rf_daily=get_rf_daily())`). **Not fixed here**
  because `nav.py` is NAV-adjacent (CANON §5 / the `lane-integrity-check`
  skill requires a before-and-after run for any change near NAV/positions
  tables), which is outside this session's authorized scope of three named
  items plus a read-only grep sweep. Flagged for a session that runs
  `lane-integrity-check` deliberately.
- **`backend/services/economic_surprise.py::compute_surprise_index()`** —
  returns `None` cleanly when ALL configured indicators fail to fetch (good),
  but on PARTIAL failure it silently renormalizes the composite over
  whichever subset loaded — same "22/23 reads as fine" shape
  `fred_health.py`'s own docstring is about. Disclosed only via an
  `indicators_tracked` count a reader must think to compare against the
  configured total; no `missing_because`/`degraded` field at the top level.
  Lower severity (no fabricated reading, just a silently-reweighted one) and
  not a trivial ≤20-line fix (needs a configured-total constant threaded
  through plus a degraded/missing_because field and a test pinning the
  partial-coverage case) — left for a dedicated pass.

## Pytest summary

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest \
  backend/tests/test_fixed_income.py backend/tests/test_fixed_income_router.py \
  backend/tests/test_fx_curves.py backend/tests/test_fred_health.py \
  backend/tests/test_fred_health_survives_restart.py \
  backend/tests/test_signal_reachability.py \
  backend/tests/test_guard_missing_input_contract.py -q
=> 193 passed, 1 warning (StarletteDeprecationWarning, pre-existing/unrelated)
```

Additionally ran `test_market_dashboard.py` + `test_cross_asset_monitor.py`
(both consume `fixed_income.compute_*` through `market_dashboard.py`): 59
passed, offline, no regressions from the `compute_credit_spread_analysis`
contract change (their fixtures always include `hy_oas`/`ig_oas` series).

## Files changed

- `backend/services/fixed_income.py`
- `backend/services/fx_curves.py`
- `backend/services/data_fetcher.py`
- `backend/routers/analytics.py`
- `backend/tests/test_fixed_income.py`
- `backend/tests/test_fixed_income_router.py` (new)
- `backend/tests/test_fx_curves.py`
- `backend/tests/test_fred_health.py`
