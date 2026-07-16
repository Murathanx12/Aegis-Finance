# Postmortem — screener/stock analysis 100% dead for ~2 days (2026-07-14 → 07-16)

## What happened

The 70d8ed6 shared-fetch refactor (rate-limit honesty work) replaced
`stock = yf.Ticker(ticker)` + `stock.history()/.info` in
`stock_analyzer.analyze_stock` with the new `fetch_ticker_history/info`
helpers — and deleted the `stock` variable. The enrichment block five screens
lower (`_get_analyst_targets(stock)`, `_get_recommendations(stock)`, holders,
news, earnings) still referenced it. Every call to `analyze_stock` raised
`NameError: name 'stock' is not defined` AFTER the Monte Carlo completed.

Blast radius: the 80-ticker screener returned empty (each ticker logged
`screener skip {T}: name 'stock' is not defined` — 50/50 of prod's recent
warnings), and per-ticker stock pages failed once their pre-deploy cache
expired. The engine looked alive: NAV lanes, canaries, health checks all
green, yfinance success rate 1.0 — the failure was post-fetch.

## Why it survived deploy verification

`verify-prod-after-deploy` was run — but it exercised the NEW surfaces
(resolver, 503 mapping, daily brief), not the CHANGED one. `stock_analyzer`
was edited, and no fresh `analyze_stock` was forced live (cached pre-deploy
responses masked it). The fast suite has no test that runs `analyze_stock`
end-to-end offline; every existing test mocked around it or needed network
(slow-marked).

## Fixes

1. One line: recreate the lazy `yf.Ticker` handle before the enrichment block
   (constructing it does no I/O).
2. Regression test pinning "analyze_stock completes offline with all
   enrichments failing" (`test_web_fixes_2026_07_14.py::TestAnalyzeStockCompletes`).
3. Sibling hardening: the five enrichment helpers caught only
   `(AttributeError, KeyError, TypeError, ValueError)` — any network-layer
   exception killed the whole analysis despite the "non-critical, per-field"
   contract. Broadened to `except Exception` + debug log (fields are optional
   and their absence is visible as None in the payload).

## Lessons

- **Verify the changed surface, not the changed feature.** The refactor's
  feature was rate-limit honesty; its blast radius was every consumer of
  `analyze_stock`. The live check must exercise the module you edited, with
  a cache-busting fresh request.
- A per-item `except Exception: log + skip` around a whole worker function
  converts a deterministic 100% failure into a warning stream — fine — but
  only if someone READS the warning stream. `aegis_verified_state`'s
  recent_warnings surfaced it immediately when finally read; the daily brief
  of prod warnings is the habit.
- Refactors that delete a variable need a grep for remaining references
  before commit (`\bstock\b` in the file would have caught it in seconds).
