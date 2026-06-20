# Data Integrity — directional vs sizing grade

**Module:** `backend/services/data_integrity.py` · **Tests:** `backend/tests/test_data_integrity.py`
**Added:** 2026-06-20 (V3 Chunk 3, the gate before single-stock backtests)

## The contract

A backtest is only as honest as its data. Every data source is classified:

| Grade | Means | May be used to | Sources |
|---|---|---|---|
| **DIRECTIONAL** | survivorship-biased and/or restated (non-PIT) | **KILL** a candidate (falsification). Numbers are directional, never position-sizing grade. | yfinance, fmp, alpha_vantage, polygon, finnhub |
| **SIZING** | delisted-inclusive prices **AND** point-in-time (as-reported) fundamentals | size a real position | sharadar *(registered; adapter not yet wired)* |

Sizing-grade requires **both** guarantees. A source with only one stays directional.

### Why free data is directional-only
- **Survivorship bias** — yfinance carries only names that still trade. Every stock
  that went to zero (Lehman, Enron, WaMu, Bear Stearns, GGP) is silently absent, so a
  backtest "over the universe" is secretly a backtest over the *winners*.
- **Restated fundamentals** — yfinance serves *today's* restated financials, not what
  was knowable on the trade date. A model that sees a restatement early reads the future.

Both manufacture fake alpha. This matches the project's own **T7 audit** (yfinance could
build a survivorship-free universe for only 1/20 delisted names).

## How to use the gate

```python
from backend.services import data_integrity as di

# 1) Any backtest claiming sizing-grade results must pass this — fails LOUD on
#    a directional source so a single-stock number never silently sizes a position.
di.require_sizing_grade(price_source, context="single-stock momentum candidate")

# 2) Empirically prove the source can serve delisted names (network in the fetch fn):
report = di.survivorship_probe(fetch_history=my_price_fetch, source=price_source)
di.assert_survivorship_safe(report)   # raises if a SIZING-registered source is biased

# 3) Directional backtests run freely but must STAMP results with the grade:
result["data_grade"] = di.data_grade(price_source).value   # "directional"
```

**Rule:** no single-stock backtest result may omit its `data_grade` stamp. Chunk 4's
cross-sectional ranker calls `require_sizing_grade` (or stamps `directional`) before any
result can graduate toward a forward lane.

## Empirical check (run manually, needs network)
```bash
python -c "from dotenv import load_dotenv; load_dotenv(); \
import yfinance as yf, pandas as pd; \
from backend.services.data_integrity import survivorship_probe, KNOWN_DELISTED; \
f=lambda t: (yf.download(t, period='max', progress=False)['Close'] if True else None); \
print(survivorship_probe(lambda t: f(t).dropna() if f(t) is not None else None))"
```
Expect `survivorship_biased=True` for yfinance — that is the gate working.

## Upgrade path — Sharadar (drop-in)

Recommended sizing-grade source: **Sharadar SEP + SF1 via Nasdaq Data Link**
(delisted-inclusive prices + as-reported PIT fundamentals, ~$ low-hundreds/yr).
It is **already registered SIZING** in `SOURCE_GUARANTEES`. To activate:

1. Subscribe (Nasdaq Data Link / Sharadar) and put `NASDAQ_DATA_LINK_API_KEY` in `.env`.
2. Implement a `SharadarProvider(BaseProvider)` in `backend/services/providers/` that
   serves `get_equity_history` (SEP, delisted-inclusive) and `get_fundamentals` (SF1,
   filtered to `datekey <= as_of` for PIT) — mirroring the existing provider adapters.
3. Point the backtest price source at `"sharadar"`. The gate then passes sizing-grade and
   every single-stock backtest becomes sizing-grade with no other change.

Until then: **all single-stock backtests are directional-only (falsification).** Forward
paper lanes remain the only sizing-grade evidence (the 24-month rule).
