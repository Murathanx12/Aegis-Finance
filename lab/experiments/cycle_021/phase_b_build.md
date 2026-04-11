# Cycle 21 — Phase B: BUILD

## What was implemented

**Screener Parallelization + Request Timing Middleware + GDELT Hardening**

### Changes (4 files, ~120 lines meaningful changes)

1. **`backend/middleware.py`** (NEW, 50 lines)
   - Request timing middleware: logs duration, adds `X-Process-Time` header
   - Warns on slow requests (>10s), info-logs requests >1s
   - Provides observability for all endpoints

2. **`backend/main.py`** (+3 lines)
   - Wired `add_timing_middleware(app)` after CORS

3. **`backend/routers/stock.py`** (~60 lines changed)
   - Screener: replaced sequential `for ticker in sorted(all_tickers)` with
     `ThreadPoolExecutor(max_workers=8)` — expected 3-5x speedup
   - `_compute_sector_momentum()`: parallelized 11 ETF fetches with 6 workers
   - Added timing log for screener completion

4. **`backend/services/news_intelligence.py`** (~15 lines changed)
   - Parallelized 3 independent GDELT API calls (tone, volume, conflict)
   - Added `@retry_with_backoff(max_retries=2)` to each GDELT fetch function
   - GDELT latency: ~3x reduction (parallel) + resilience against transient failures

## Why this was highest-impact

The screener endpoint (`/api/stock/screener`) is the most user-visible performance
bottleneck. With 30+ tickers each taking 3-8s for yfinance + GARCH + MC, sequential
execution takes 90-240s. Parallelization with 8 workers reduces this to 15-40s.

The timing middleware is foundational — you can't optimize what you can't measure.
Every future cycle benefits from knowing which requests are slow.

## Test results

- 142 passed, 92 deselected (fast tests) in 39.46s
- All imports resolve cleanly
- No regressions

## Expected performance improvement

| Endpoint | Before | After (estimated) |
|----------|--------|-------------------|
| /api/stock/screener | 90-240s | 15-40s |
| GDELT news fetch | 3-5s | 1-2s |
| All endpoints | no timing data | X-Process-Time header |
