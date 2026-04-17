# Aegis Finance SDK

Python client for the [Aegis Finance](https://github.com/Murathan/aegis-finance)
REST API. Drop into a Jupyter notebook, a research script, or a trading
bot — every endpoint becomes a one-liner.

## Install

```bash
pip install -e sdk/
# or, once published:
# pip install aegis-finance-sdk
```

## Quick start

Spin up the backend:

```bash
uvicorn backend.main:app --port 8000
```

Then in Python / Jupyter:

```python
import aegis

# Live snapshot
snap = aegis.equity.snapshot("AAPL")
print(snap["price"], "via", snap.get("source"))

# Institutional ownership
owners = aegis.equity.ownership("AAPL")
print(owners["crowding"]["level"])

# ETF look-through
print(aegis.equity.etf_lookthrough("SPY")["top_holdings"][:3])

# Portfolio analytics
result = aegis.portfolio.analyze([
    {"ticker": "AAPL", "shares": 10, "current_price": 230.0},
    {"ticker": "MSFT", "shares": 5,  "current_price": 420.0},
])
print("Risk number:", result["risk_number"]["risk_number"])

# Convex optimizer with transaction costs and tracking error
opt = aegis.portfolio.optimize_mpc(
    ["AAPL", "MSFT", "GOOGL", "NVDA"],
    benchmark_weights={"AAPL": 0.25, "MSFT": 0.25, "GOOGL": 0.25, "NVDA": 0.25},
    tracking_error_limit=0.05,
    transaction_cost_bps=5,
    horizon=4,
    return_decay=0.25,
)
print(opt["final_weights"])

# Save an Excel tearsheet
blob = aegis.portfolio.tearsheet_xlsx(result["holdings"], title="Q2 Review")
with open("tearsheet.xlsx", "wb") as f:
    f.write(blob)

# Market + macro
print(aegis.macro.status()["regime"])
print(aegis.macro.fixed_income()["yield_curve"]["shape"])

# Economic calendar + earnings
print(aegis.calendar.economic(days_ahead=7)["count"])
print(aegis.calendar.earnings("AAPL", days_ahead=60))

# Provider health
for p in aegis.world.providers()["providers"]:
    print(p["name"], "✓" if p["available"] else "✗")
```

## Configuration

By default the SDK talks to `http://localhost:8000`. Point it at a
different backend via env var or `configure()`:

```bash
export AEGIS_API_URL=https://api.my-aegis.com
```

```python
aegis.configure(base_url="https://api.my-aegis.com", timeout=120)
```

## Namespaces

| Namespace            | Covers                                                  |
|----------------------|---------------------------------------------------------|
| `aegis.equity`       | per-ticker data: snapshot / analysis / fundamentals / ownership / factors |
| `aegis.portfolio`    | analyze / optimize / optimize_mpc / attribution / tearsheets |
| `aegis.risk`         | crash probability / tail risk / conformal intervals     |
| `aegis.macro`        | market-status / regime / yield curve / net liquidity    |
| `aegis.calendar`     | earnings + economic-release calendars                   |
| `aegis.world`        | WEI-style market tile + provider inventory              |

## Errors

Any non-2xx raises `aegis.AegisError`, with the parsed payload on
`.payload` and the status code on `.status_code`. Transient 5xx failures
are retried twice with exponential backoff before giving up.
