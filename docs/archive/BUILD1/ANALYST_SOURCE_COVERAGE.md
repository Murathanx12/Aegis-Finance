# B1 — Analyst source coverage matrix

Probed **2026-08-10** against ticker `DKNG` with the keys in `.env`.
Raw output: `analyst_source_probe_DKNG.json`. Reproduce with:

```bash
python scripts/probe_analyst_sources.py --ticker DKNG --json docs/BUILD1/analyst_source_probe_DKNG.json
```

Every row below carries the HTTP status that was actually returned. No row says
"unavailable" without one — that is the standing rule and this is the first time
it has been applied to the analyst layer.

---

## The matrix

| vendor | endpoint | status | analyst id | firm | target | timestamp | history | verdict |
|---|---|---|---|---|---|---|---|---|
| **finnhub** | `/stock/price-target` | **403** | – | – | – | – | – | not entitled on the free tier |
| **finnhub** | `/stock/recommendation` | **200** | no | no | no | **yes** | **yes** (4 monthly rows) | rating-count history **with real dates** |
| **finnhub** | `/stock/upgrade-downgrade` | **403** | – | – | – | – | – | not entitled |
| **finnhub** | `/calendar/earnings` | **200** | – | – | – | yes | – | **earnings dates + EPS/revenue estimates** |
| **finnhub** | `/stock/earnings` | **200** | – | – | – | yes | yes (4 quarters) | surprise history |
| **fmp** | `stable/price-target-consensus` | **402** | – | – | – | – | – | premium |
| **fmp** | `stable/price-target-news` | **402** | – | – | – | – | – | premium — *this is the endpoint we wanted* |
| **fmp** | `stable/grades-historical` | **402** | – | – | – | – | – | premium |
| **fmp** | `v4/price-target` | **403** | – | – | – | – | – | legacy path retired |
| **fmp** | `v4/price-target-consensus` | **403** | – | – | – | – | – | legacy path retired |
| **fmp** | `v4/upgrades-downgrades` | **403** | – | – | – | – | – | legacy path retired |
| **fmp** | `v3/analyst-estimates` | **403** | – | – | – | – | – | legacy path retired |
| **alpha_vantage** | `OVERVIEW` | **200** | – | – | **yes** (`AnalystTargetPrice`) | no | no | **a second, independent consensus target** |
| **eodhd** | `fundamentals?filter=AnalystRatings` | **403** | – | – | – | – | – | free token does not cover fundamentals |
| **eodhd** | `fundamentals?filter=Earnings::Trend` | **403** | – | – | – | – | – | not entitled |
| **polygon** | `/v2/last/nbbo` | **403** | – | – | – | – | – | quotes are a paid entitlement |
| **polygon** | `/v3/reference/tickers` | **200** | – | – | – | – | – | listing status, share class |
| **yahoo** (`yfinance`) | `analyst_price_targets` | 200 | no | no | yes (low/mean/median/high) | **no** | **no** | the current source |
| **yahoo** (`yfinance`) | `recommendations` | 200 | no | no | no | period label only | 4 rows, no dates | the current `rating_drift_3m` input |
| **yahoo** (`yfinance`) | `upgrades_downgrades` | 200 | no | **yes** | no | **yes** | yes | firm-attributed rating actions |

FMP was probed on **both** the legacy `v3/v4` paths and the current `stable`
paths, because a 403 that says *"Legacy Endpoint"* is a migration notice and
recording it as an entitlement answer would have been wrong. On the current API
the answer is a clean **402: premium**.

---

## What this settles

**1. Per-analyst target history is not purchasable on any tier we currently
hold.** FMP `price-target-news` (per-analyst target changes with dates and firm
names) is the right product and it is 402. Finnhub's target endpoints are 403.
EODHD is 403. Yahoo returns a target with **no timestamp at all**.

⇒ `ΔTarget over 7 / 30 / 90 days` cannot be obtained from a vendor today, and
must not be approximated by rating counts and called a revision. It is produced
by **our own point-in-time ledger** (`backend/services/analyst_ledger.py`),
which accrues one observation per ticker per day from first use, and reports
`MISSING` with a reason until two observations actually span the window.
Starting it costs nothing and it is the only path to the signal the mandate
names as most important.

**2. There is a second consensus target available today, free.** Alpha Vantage
`OVERVIEW` returns `AnalystTargetPrice` (34.78 for DKNG) plus
StrongBuy/Buy/Hold/Sell/StrongSell counts. It is **not wired in**, for one
reason: the free tier is **25 requests/day**, and the book plus watchlist is 45
names. It is viable as an attended cross-check on the 11 holdings, not as the
routine source, and wiring it silently would exhaust the quota and then fail
quietly — the house failure mode. Recorded here as available, deliberately not
adopted. `model_status.analyst_sources` continues to say `yahoo (yfinance)`
because that is what `enrich` actually calls.

**3. The catalyst layer is buildable today, for earnings only.** Finnhub's
`/calendar/earnings` and `/stock/earnings` are both 200 on the free tier. That
is now `backend/services/pm_catalysts.py` (B5 v0). FDA/PDUFA dates, clinical
readout windows, offerings, 13D/G, lockups and investor days have **no entitled
source**, so they are hand-entered under `catalysts:` in the book file, and the
calendar reports its own blindness on every call rather than letting an empty
list read as "nothing is coming". For a book holding APLT, NTLA and BHVN that
distinction is the difference between a tool and a hazard.

**4. A real quoted spread is not available.** Polygon NBBO is 403. The PM
therefore reports `spread: unavailable` and charges a labelled conservative
assumption instead — and the median intraday `(high − low) / close`, which v1
displayed beside the liquidity fields, has been renamed `intraday_range_pct`
with a note that it is a **range, not a spread and not a cost**.

---

## What would change the picture

| want | cheapest route | cost |
|---|---|---|
| per-analyst target history | FMP paid tier (`price-target-news`, `grades-historical`) | paid |
| target history without paying | our own ledger, one row/ticker/day | free, accrues from 2026-08-10 |
| real bid/ask | Polygon paid, or a broker API (Alpaca keys are already in `.env`) | paid / free-with-account |
| PDUFA + clinical calendar | no free structured source found; FDA calendars are scraped or licensed | – |
| second target opinion today | Alpha Vantage `OVERVIEW`, 25 req/day | free, quota-bound |

The ledger is the item that compounds: every day the engine runs, the thing the
vendors will not sell us gets one day longer.
