| provider | status | latency | entitlement | failure class |
|---|---|---|---|---|
| FRED | ok | 477 ms | granted: series/VIXCLS,series/observations/DGS10 | - |
| Finnhub | ok | 534 ms | granted: company-news (free),quote (free),stock/insider-transactions,stock/profile2 (free),stock/recommendatio | - |
| FMP | ok | 1162 ms | granted: stable/profile,stable/quote / NOT entitled(403): v3/quote (LEGACY),v3/ratios-ttm (LEGACY) | - |
| Polygon | ok | 916 ms | granted: v2/aggs prev close,v3/reference/tickers / NOT entitled(403): v2/last/trade (PAID tier) | - |
| AlphaVantage | ok | 658 ms | free tier | - |
| EODHD | ok | 825 ms | granted: user (plan + quota) / 401 on: eod/AAPL.US | - |
| DeepSeek | ok | 314 ms | pay-as-you-go | - |
| NVIDIA NIM | CANNOT_DETERMINE | 30239 ms | unknown | cannot_determine |
| HF router | ok | 799 ms | 138 models visible; GLM-5.3-Flash served | - |
| OpenAI | ok | 2412 ms | 125 models visible; gpt-5-nano served | - |
| Featherless | FAIL | - | unknown | absent |
| WRDS | FAIL | - | NOT MEASURED TODAY. Last recorded 2026-08-31: READ=crsp-daily,ibes,ibes-detail,taq-ms,taq-liquidity,patents,bo | network |
| GDELT | FAIL | 11897 ms | unknown | quota |
| EDGAR | ok | 583 ms | public; declared UA present (47 chars) | - |
| Kalshi | ok | 801 ms | public read, no key | - |
| Polymarket | ok | 235 ms | public read, no key | - |
| CBOE | ok | 1179 ms | public CDN, no key; NO CALLER IN THIS REPO | - |
| website /api/health/full | ok | 27379 ms | ours | - |
| seal-authority (public GET) | ok | 564 ms | ours, public read | - |
| Alpaca (finance mirror/arena) | FAIL | - | revoked | auth |
| Railway (loving-elegance) | ok | 2273 ms | ours | - |

16 ok · 4 FAIL · 1 CANNOT DETERMINE of 21
