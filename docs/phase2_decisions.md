# Phase 2 — Design Decisions

## Sector mapping: double-source lookup

`real_analyzer._get_sector_map()` builds a ticker-to-sector mapping from three sources,
checked in priority order:

1. **`config.py` stock_universe.sector_stocks`** — the existing ~200-ticker screener universe.
   Covers all large/mid-cap names already in Aegis.

2. **`paper_portfolios.yaml` universe.individual_stocks`** — the PI reference universe (~76 tickers).
   Category keys (e.g., `healthcare_biotech`, `emerging_tech`) are mapped to standard
   sector labels via `_PI_SECTOR_LABELS`.

3. **`_FIXTURE_SECTORS` hardcoded dict** — five small-cap biotech tickers from Murat's
   personal portfolio (TVTX, ALMS, APLT, NTLA, APMX) that are too small for either
   reference universe but need correct sector classification for concentration flags.

### Phase 5.5 concern: user-added personal tickers

When the Personal Conviction lane (Phase 5.5) allows users to log decisions for tickers
not in any of the three sources above, `_get_sector_map()` will return "Other" for those
tickers. This means:

- Sector concentration flags won't fire correctly for unknown sectors
- The sector_exposure breakdown in MetricPack will bucket them as "Other"

**Resolution path (Phase 5.5):** When `ingest_decision()` processes a new ticker not in
the sector map, it should:
1. Look up the ticker's sector via yfinance (`yf.Ticker(t).info.get("sector")`)
2. Cache the result in a `ticker_metadata` table (new, lightweight)
3. Map the yfinance sector string to our standard labels

This is a ~20-line addition to the personal lane ingest path, not a redesign. The
hardcoded `_FIXTURE_SECTORS` dict should be removed at that point since the metadata
table will handle it.

## Catalyst calendar and did-you-know panel (SPEC section 3, items 4-5)

Both are **deferred to Phase 5 (frontend)**, not dropped.

- **Catalyst calendar**: the data already exists via `/api/earnings/{ticker}` and
  `/api/stock/{ticker}` endpoints. The frontend page will fetch these per-holding.
  No new backend service needed.

- **Did-you-know panel**: requires reference lane MetricPacks (Phase 3/4) to compare
  against. The raw data (sector_exposure, factor_exposure in MetricPack) is already
  computed by the Phase 2 analyzer. The narrative generation ("Your biotech weight is
  4.2x higher than the Aggressive reference") is Phase 5 frontend logic that compares
  the real portfolio's MetricPack against each reference lane's MetricPack.

## Max drawdown computation

Drawdown is computed inline from cumulative returns rather than delegating to
`drawdown_analyzer.analyze_drawdowns()`. Reason: the drawdown analyzer expects an
absolute price series and returns drawdown percentages in a format that required
conversion. Computing `(cum / peak - 1).min()` directly is 4 lines, no conversion
needed, and produces values in [-1, 0] which MetricPack expects. The drawdown analyzer
is still available for the detailed drawdown-by-drawdown breakdown in Phase 5 frontend.
