# Cycle 031 — Phase B: BUILD

## What Was Built
**Router-Level Test Suite** — 54 new tests covering the HTTP layer of 6 API routers.

## Why This, Not the Others
- Phase A Finding #1 (macro_risk zero weight) turned out to be a **false positive**: the config already has `macro_risk: 0.12` in `signal_weights`, and `signal_engine.py` loads from config, not the fallback dict.
- Finding #2 (stock null fields) appears to be a lab script artifact, not a service bug — `signal_quality` output shows all 16 stock signals working.
- Finding #3 (zero router tests) was the **genuine gap**: 9 routers, 0 tests. HTTP status codes, input validation, ticker sanitization, Pydantic model validation — all completely untested.

## Files Changed
| File | Action | Lines |
|------|--------|-------|
| `backend/tests/test_routers.py` | **Created** | ~310 lines |

## Test Coverage Added (54 tests across 10 classes)

| Class | Tests | Routers Covered |
|-------|-------|-----------------|
| TestRootAndHealth | 3 | main.py (root, health, 404) |
| TestCrashRouter | 6 | crash.py (horizon validation, ticker regex) |
| TestSimulationRouter | 5 | simulation.py (n_sims/years bounds) |
| TestNewsRouter | 3 | news.py (ticker validation) |
| TestSavingsRouter | 7 | savings.py (Pydantic model, all risk levels) |
| TestPortfolioRouter | 15 | portfolio.py (build/analyze/project/questionnaire validation) |
| TestSavingsResponseStructure | 1 | savings.py (response shape) |
| TestCrashRouterTickerPatterns | 11 | crash.py (parametrized valid + malicious tickers) |
| TestNewsRouterTickerPatterns | 3 | news.py (SQL injection, XSS, overflow) |

## What's Tested Now
- HTTP 422 for all invalid inputs (bad horizons, out-of-range params, malicious tickers)
- HTTP 404 for nonexistent routes
- Pydantic validation on all POST bodies (portfolio, savings)
- Input sanitization: SQL injection, XSS, path traversal patterns blocked
- Response structure validation (savings projections)
- All valid enum values accepted (risk levels, methods, goals)

## Metrics
- **Before:** 388 fast tests, 16 files, 403 functions
- **After:** 442 fast tests, 17 files, 457 functions
- **Delta:** +54 tests, +1 file
- **All passing:** 442/442, 0 failures
