# Q14 — FRED macro inputs never load in production (2026-10-07)

**Diagnoser: Sonnet, read-only on prod, no deploy made.** Live prod was read
once via the public health endpoint (GET only, no state changed); local
reproduction mutated only this machine's dev `.cache/` (one diskcache key,
`DataFetcher._fetch_fred_payload:()[]`) and `os.environ` inside throwaway
subprocesses. `.env` was read for presence/length only — its value is never
printed below.

## 1. The finding, confirmed live

`curl https://aegis-finance-production.up.railway.app/api/health/full`
(2026-10-07, deploy `46d6efa4`, up since 2026-10-02T14:52:35Z, uptime
~398,211 s ≈ 4.6 days):

```
status: DEGRADED
degraded_reasons: ["critical FRED series never loaded: initial_claims (ICSA) ...",
                   "... initial_claims_4wk (IC4WSA) ...", "... nfci (NFCI) ...",
                   "... yield_spread (T10Y3M) ...", "... hy_oas (BAMLH0A0HYM2) ..."]
data_sources.fred: {fetches: 5, series_loaded: [], series_failed: [23 names], n_loaded: 0, n_failed: 23}
fred_health.by_status.UNAVAILABLE: [all 23 configured series]
```

`recent_warnings` on the same response carries the actual exception text from
every one of the 23 per-series fetches, word for word:

> `Failed to fetch unemployment (UNRATE): Bad Request.  The value for variable
> api_key is not registered.  Read https://fred.stlouisfed.org/docs/api/api_key.html
> for more information.`

(23 near-identical lines, one per series, same wording, same timestamp batch;
plus `net_liquidity` logging the same "api_key is not registered" message
separately.)

## 2. Reproduction table (local, three isolated subprocess runs)

Each case clears the one relevant disk-cache key first (`DataFetcher.
_fetch_fred_payload:()[]` in `.cache/`, a diskcache/SQLite store that survives
process restarts — the dev machine had a warm 24h-cached payload from a prior
real fetch, which silently masked the "no key" case on the first attempt and
is itself worth remembering: **a local repro that doesn't clear the disk
cache is testing the cache, not the code**).

| case | env | `data_sources.fred` | `fred_health.status` | matches prod? |
|---|---|---|---|---|
| **no key** | `AEGIS_IGNORE_DOTENV=1`, `FRED_API_KEY=` (unset/empty) | `fetches=0, n_loaded=0, n_failed=0, series_failed=[]` | `DEGRADED`, `last_no_fetch_reason="FRED_API_KEY not set"` | **No.** `fetches` never increments — `_fetch_fred_payload` returns before the `ThreadPoolExecutor` ever runs. Prod's `fetches=5` rules this out. |
| **wrong key** (syntactically-plausible-but-invalid, 31 chars) | real env, key = dummy string | `fetches=1, n_loaded=0, n_failed=23, series_failed=[23 names]` | `DEGRADED`, same 5 `degraded_reasons` lines, byte-identical wording | **Yes — exact shape match** (`fetches>0`, `n_loaded=0`, `n_failed=23`, all 23 names). Local exception text: *"api_key is not a 32 character alpha-numeric lower-case string"* (my dummy key fails FRED's syntax check) vs prod's *"api_key is not registered"* (prod's key passes FRED's syntax check — it's a real 32-char lowercase token — but FRED does not recognize it as issued/active). |
| **real key** (this repo's own `.env` `FRED_API_KEY`, 32 chars, no placeholder marker) | normal (dotenv loaded) | `fetches=1, n_loaded=23, n_failed=0, series_failed=[]` | `ok`, `degraded_reasons=[]` | This machine's key works today. |

**Cause, confirmed, not inferred:** the `FRED_API_KEY` Railway variable is
**present** (it passes `api_keys.has()` — non-empty, no `"placeholder"`
substring — and reaches `fredapi`'s `Fred(api_key=...)` client, which is why
`data_sources.fred.fetches` increments and the `ThreadPoolExecutor` actually
runs 23 real HTTP calls) but **FRED itself rejects it as unregistered** on
every single call, every one of the 5 daily passes since the container
started on 10-02. This is consistent with any of: a revoked/deactivated key, a
key copied with a typo, a key belonging to a different service, or a key that
was never activated by FRED's confirmation step — the code cannot and does not
need to distinguish which; FRED's own 400 response is unambiguous ("is not
registered").

Ruled out: no key configured (would show `fetches=0`); fredapi not installed
(would also show `fetches=0`, with `last_no_fetch_reason="fredapi not
installed"`); an egress/network block (would produce a network-layer
exception, e.g. timeout/connection-refused text, not an HTTP 400 body parsed
from FRED's own API — `fredapi` got a response, just a rejecting one); a
fetch-budget cap (there is no budget cap in this path — `fetches` is a plain
counter of cold-cache passes bounded only by the 24h TTL, and nothing in
`_fetch_fred_payload` / `fred_provider.py` refuses after N attempts).

## 3. Owner action (not done by this session — Railway variables are a secret)

Variable name, from `backend/config.py` `APIKeys.from_env()`:

```python
fred=os.getenv("FRED_API_KEY", ""),
```

Owner sets a **currently-registered** FRED API key (free, from
https://fred.stlouisfed.org/docs/api/api_key.html — the same place the error
message points to) on the `selfless-courage` / `Aegis-Finance` / `production`
service:

```bash
railway link --project selfless-courage --service Aegis-Finance --environment production
railway variables --set FRED_API_KEY=<REDACTED-new-key> --service Aegis-Finance
```

**Verification** (do this after the owner sets it — this session does not):

1. Railway redeploys on the variable change (same commit `46d6efa4`, new
   `deploy.started_at`/`uptime_seconds` resets near 0).
2. Poll `GET /api/health/full` (per `verify-prod-after-deploy`): the FRED
   fetch is cache-TTL'd at 86,400 s but runs cold on the first miss after
   restart, so the next natural pass or scheduled job should populate it
   within the first poll after redeploy — check `data_sources.fred.n_loaded`
   (want 23, not 0) and `fred_health.status` (want `"ok"`, not `DEGRADED`).
3. `degraded_reasons` should no longer contain any `"critical FRED series
   never loaded"` line.
4. The new `fred_macro_inputs` health row (below) should flip from
   `DEAD`/`STALE` to `ALIVE` — that is the one-line canary to watch instead of
   re-reading the whole JSON by hand.

## 4. The health-surface fix shipped this session

`degraded_reasons` already *named* every missing critical series — but it is
a **list of strings**, not a row with a verdict that can go red on its own,
and it had said the same thing for 5 days with nothing forcing a second look
(the exact C8 pattern CLAUDE.md names for `funnel_staleness`). Added:

**`backend/services/system_health.p_fred_macro_inputs`** (new probe,
registered in `PROBES`, picked up automatically by `scripts/health_probe.py`
and `scripts/daily_pass.py` since both run the full `system_health.PROBES`
registry) — `GET /api/health/full`, reads `fred_health.by_status` against
`config.CRITICAL_FRED_SERIES` and `deploy.uptime_seconds`:

- **DEAD** — zero of the critical series have ever loaded AND the deploy has
  been up more than 24h (one real day is enough passes to rule out "just
  hasn't tried yet"). Detail names the likely cause: `fred_health.
  last_no_fetch_reason` when the process never even attempted a fetch (no key
  / fredapi missing), else the first FRED-related `api_key` warning pulled
  from `recent_warnings` (today, verified against prod, that line is *"api_key
  is not registered"*).
- **STALE** — zero loaded but uptime is still under 24h (give it a day before
  calling it dead), or some-but-not-all critical series loaded.
- **ALIVE** — all critical series loaded.
- **UNKNOWN** — no fetch pass has run yet, or the health body itself lacks the
  fields this probe reads (an honest "cannot determine," never a false "ok").

Test: `backend/tests/test_system_health.py` — 5 new cases (`DEAD` with the
real prod `api_key is not registered` message surfacing in `detail`; `STALE`
under 24h uptime; `UNKNOWN` on zero passes; `ALIVE` on 5/5; `STALE` on a
partial 2/5) plus the existing repo-wide
`test_every_probe_with_its_evidence_absent_is_not_alive` parametrized test,
extended to exempt `fred_macro_inputs` the same way as `railway_backend` (an
unanswering health endpoint is `DEAD`, not `UNKNOWN` — there genuinely is no
evidence to even classify). All pass; see the diagnoser's report for the
pytest summary.

**Right now, against today's live body, this probe reads `DEAD`**: 0/5
critical series loaded, 5 passes, uptime > 4 days, cause `"api_key is not
registered"` — which is exactly the standing-for-5-days condition this fix
exists to stop being invisible.

## 5. What the consumers do WITHOUT these inputs today — second finding

Traced every reader of FRED-derived data for silent imputation vs disclosed
refusal:

- **`backend/services/market_sensor.py` (`vix_history`/`vix_level`/
  `regime`) — REFUSES loudly.** Raises `SensorRefused` naming the cause
  ("the FRED fetch failed...the VIX leg of the sensor is unobserved and no
  last-known value is substituted"). This is the pattern the rest of the repo
  should match.
- **`backend/services/net_liquidity.py` — discloses, does not impute.**
  Catches the FRED exception and returns `_default_response(error=str(e))`:
  `signal: "UNKNOWN"`, every numeric field `None`, and the real exception
  text in an `error` field. A caller reading this cannot mistake it for a real
  zero-liquidity reading.
- **`backend/services/data_fetcher.DataFetcher.get_recession_probability()`
  — silently imputes, AND IS DEAD CODE.** When no FRED signal is available at
  all it `return`s a bare `0.15` float (`# Default base rate`) with zero
  marker that it is a fallback rather than a model output. Grepped for
  callers repo-wide (outside its own module, `config.py`'s comment, and
  `fred_health.py`'s docstring): **none exist.** Same for its sibling
  `get_macro_features()`. Neither is reachable from any live code path today,
  so the silent-imputation risk is currently dormant, not active — but either
  one becoming a crash/regime model input later would ship this exact failure
  mode with no test or health row in its way.
- **`backend/services/fixed_income.get_fixed_income_dashboard()` — a second,
  live, *unaccounted* FRED path, and it silently imputes "normal."** This
  function does its own raw `fredapi` fetch keyed on `os.getenv("FRED_API_KEY",
  "")` directly — it does **not** go through `DataFetcher.fetch_fred_data()`,
  so none of its failures are visible to `fred_health`, `observability.
  source_health()`, or the new `fred_macro_inputs` probe; today's key failure
  would be completely invisible from this path alone. Per-series fetch
  failures are swallowed at `logger.debug` (not even a warning). When FRED is
  entirely unavailable, `compute_yield_curve_analysis` does disclose
  (`{"error": "No yield curve data available", "yields": {}}`), but
  `compute_credit_spread_analysis` does **not**: with `spreads == {}` the
  function still returns `"stress": {"level": "normal", "signals": []}` —
  a complete absence of the `hy_oas`/`ig_oas` reads is reported as a calm
  credit market, not as "unknown." This feeds `hy_spread` in
  `market_dashboard.py`. Logged here as a finding, not fixed in this session
  (out of today's ≤30-line scope); it belongs in `silent-fragility-audit`'s
  next pass over `fixed_income.py`.
- **`backend/services/fx_curves.fetch_short_rate()` — silently imputes a
  hardcoded rate.** `DEFAULT_USD_RATE = 0.04` is substituted for USD on *any*
  failure (unkeyed, empty series, or exception), and the resulting
  `forward_curve()` output's `method` field still claims `"Covered interest
  parity (act/360) using FRED short rates"` even when the rate used was the
  hardcoded default, not a FRED read. Also logged as a finding, not fixed
  here (FX forwards are outside the crash/regime-model scope this task was
  about, and it's a second, independent piece of silent-fragility work).

**Net for the crash/regime models specifically:** the two inputs they
actually reach through — `market_sensor`'s VIX leg and `net_liquidity` — both
refuse or disclose honestly today; they do not silently impute. The silent-
imputation failure mode exists in this codebase (`get_recession_probability`,
`fixed_income.compute_credit_spread_analysis`, `fx_curves.
fetch_short_rate`), but on paths the crash/regime models are not currently
wired to. The risk is real for the next integration, not for today's degraded
reading.
