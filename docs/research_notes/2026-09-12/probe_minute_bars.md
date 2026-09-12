# Probe 2026-09-12 — Alpaca IEX minute bars for lane D (Sonnet, market data only, no orders)

Credential: the terminal repo's `.env` `AAT_HACK3_KEY_ID`/`SECRET_KEY` via the P6 helper (names only).

## What one call does
`GET https://data.alpaca.markets/v2/stocks/bars?symbols=<20>&timeframe=1Min&feed=iex&limit=10000` over
the full UTC day of 2026-09-11 returned **9,373 bars in one page** (20 names stay under the 10k cap),
latency 2.6 s, rate-limit headers `X-Ratelimit-Limit: 200` per minute. Rows per symbol 363-433 (the
window spans pre- and post-market). Fields `t,o,h,l,c,v,n,vw`; `t` is ISO-8601 **UTC**. History: five
names pulled clean for 2026-01-02 (389-404 rows); **7-year depth not re-tested**.

## The store
- **No multi-symbol cap found**: 50 → 3,056 symbols in one GET all returned 200 (URL ~20,000 chars);
  `n_symbols_returned < n_requested` only because IEX has no trade in many symbol-minutes (a coverage
  ceiling, not a batching one). Pagination on `next_page_token` alone suffices.
- Measured: 500 names, full session → 8 pages, 70,393 rows, 19.4 s, 22.97 bytes/row (parquet).
  Extrapolated for 3,060 names: **~430k rows/day, ~49 pages, ~2 min wall, ~10 MB/day.**
- Layout: `minute_bars/<YYYY-MM-DD>/bars.parquet`, columns
  `symbol, ts_utc, open, high, low, close, volume, trades, vwap, feed`. Daily pull at 05:00 HKT, one
  paginated stream; resume by persisting the last `next_page_token` per date.

## The first-hour slice (plumbing only, no claim)
09:30-10:30 ET = 13:30-14:30 UTC. The IEX-anchored open matches the daily bar's open within a few bp on
liquid names (AAPL 327.45 both; SPY 764.52 vs 764.72). Examples on 2026-09-11: DELL first hour +8.67%,
rest of day +0.35%; ORCL −6.14% / −2.50%; SPY +0.16% / −0.19%. **Caveat:** the IEX "open" is a trade
proxy that can trail the primary exchange's auction print by minutes on some names.

## Real time, for Monday nights
The free websocket (`wss://stream.data.alpaca.markets/v2/iex`) is capped at **30 symbols** (pricing
table). A 30-minute cadence pass needs only the last completed 30-minute bar per name — REST
`timeframe=30Min` covers 3,060 names in a handful of calls; **no websocket needed**. Paper fills per the
docs: marketable only; 10% random partial fills; nothing documented about `opg` reliability
(consistent with the repo's 13/15-expired finding).

## Recommendation for D2/D5
REST-only 30-minute bars for the cadence pass; a nightly one-minute pull for the first-hour experiment
(~49 calls, ~10 MB, ~2 min); persist the page token; store by date. Unverified: minute-history depth
beyond 2026-01 and the true auction open. Probe scripts and samples under the session scratchpad
`minute_bars/`.
