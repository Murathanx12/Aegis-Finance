# Data Sources (≤$50/mo) + Firm Baselines — verified 2026-07-16

Inline web verification (the agent fan-out was cut off by the Claude monthly
spend limit; these were checked directly). CRSP is out per Murat
(eligibility + academic-only license).

## Survivorship-free US equity data within $50/month

| Source | Price | Delisted coverage | Verdict |
|---|---|---|---|
| **EODHD "All World"** | **€19.99/mo (~$22)** | Delisted tickers in ANY package: 26,000+ US delisted tickers, mostly from Jan 2000; 42,000+ non-US ([pricing](https://eodhd.com/pricing) via [G2 2026](https://www.g2.com/products/eodhd-financial-data-apis/pricing); [delisted FAQ](https://eodhd.com/financial-academy/financial-faq/historical-stock-prices-for-delisted-companies)) | **BUY FIRST** — with the acceptance test below |
| **Sharadar SEP** (Nasdaq Data Link) | not public (login/quote) | "SEP covers both active and delisted stocks" per Nasdaq's own help center ([source](https://help.data.nasdaq.com/article/508-do-you-cover-delisted-stocks)); prices since 1998 ([QuantRocket](https://www.quantrocket.com/sharadar/)) | Fallback — request quote if EODHD fails the audit |
| **Norgate Platinum** | $433.13/6mo ≈ **$72/mo** ([prices](https://norgatedata.com/prices.php)) | Delisted + historical index constituents to 1950 | OVER BUDGET; also Windows-app-centric |
| Tiingo | ~$10-30/mo | Includes delisted per docs/forum reports, but ticker-rename handling is reported messy ([AmiBroker forum](https://forum.amibroker.com/t/tiingo-and-delisted-stocks/26140)) | Weak third option |
| yfinance | $0 | 1/20 delisted names usable (our own audit, T7) | Rejected (proven) |

**Recommendation:** subscribe to **EODHD All World (€19.99/mo)** — inside
budget with headroom — but treat the first month as a trial gated by OUR OWN
acceptance test: rerun `engine/research/survivorship_audit.py` (the exact
20-delisted-name list that failed yfinance at 1/20) against the EODHD API.
- **Pass bar (pre-committed): ≥16/20 delisted names return usable price
  history with a sane final print.** If it fails, cancel and get a Sharadar
  SEP quote instead.
- Caveats found: EODHD documents NO delisting-return methodology or
  corporate-action guarantees for delisted names (their claims are
  marketing-verified only — the audit is the truth); the €19.99 tier is a
  personal-use license (fine for offline VALIDATION, the CRSP role; public
  redistribution of raw data would need their commercial tier — we display
  derived analytics only, and validation results stay in docs).
- Bulk download: pull the audited universe once into `engine/data/bulk/`
  (check retention terms before relying on retain-after-cancel).

## Firm baselines for the model-vs-firm comparison

Published capital market assumptions, US large-cap, **nominal annualized**:

| Firm | Horizon | US large-cap E[r] | As of | Source |
|---|---|---|---|---|
| J.P. Morgan LTCMA 2026 | 10-15y | **6.7%** (60/40: 6.4%) | Oct 2025 | [JPM AM press release](https://am.jpmorgan.com/us/en/asset-management/institutional/about-us/media/press-releases/jp-morgan-releases-2026-long-term-capital-market-assumptions/), [full report PDF](https://am.jpmorgan.com/content/dam/jpm-am-aem/americas/us/en/institutional/insights/portfolio-insights/ltcma-full-report.pdf) |
| Vanguard VEMO 2026 | 5-10y | **4.0%-5.0%** (AI-bull scenario 8-10% @p10; AI-bear −2-2% @p30) | Dec 2025 | [2026 outlook PDF](https://corporate.vanguard.com/content/dam/corp/research/pdf/isg_vemo_2026.pdf) (Oct VCMM interim read was 3.5-5.5%) |
| BlackRock CMA | 10y | **8.5%** | Mar 31, 2026 | BlackRock CMA data file (primary, agent-verified) |
| Schwab | 2026-2035 | **5.9%** | 2025 | Schwab CMA page (primary, agent-verified) |
| Invesco CMA | 10y | **5.0%** | 2025 | Invesco CMA PDF (primary, agent-verified) |
| AQR | 5-10y | **3.9% real ≈ 6.3% nominal** | 2025 | AQR CMA PDF (primary, agent-verified) |
| Goldman Sachs | 10y | **6.5%** (updated from the famous Oct-2024 ~3% call) | Nov 2025 | secondary sources — primary paywalled; verify before UI display |
| Fidelity / Morningstar / Research Affiliates | 20y/10y/10y | 5.8% / 5.3% / 3.1% | 2025-26 | secondhand via Morningstar's CMA roundup — flagged, verify before display |

Firm dispersion: **3.1% (Research Affiliates) … 8.5% (BlackRock)** — a 5.4pp
spread among the world's largest institutions for the SAME asset class. That
spread IS the margin-of-error message for users.

Our MC 5Y annualized band (+2% to +8%, median ~5.9% per CLAUDE.md healthy
ranges) sits INSIDE the firm dispersion — the honest
display is "our median vs the firm range," not a point-vs-point beauty
contest. These constants live in `config.py::firm_baselines` for the future
comparison card; each carries its as_of date and must be refreshed on the
firms' annual cycle (next: ~Oct-Dec 2026).

## Street 12-month price-target error (for the Wall Street View caveat + TRIAL-FORECAST-LEDGER prior)

- ~100,000 targets 1997-2002: price reached/exceeded the 12m target in only
  **~25%** of cases by month 12; touched at ANY point during the year <50%
  ([Columbia paper](https://business.columbia.edu/sites/default/files-efs/imce-uploads/FRANK%20ZHANG%20PAPER%20PSZ_20190913.pdf)).
- 2023 large-cap study: fewer than half of 12m targets reached in the window
  ([Anachart 18-year study](https://anachart.com/how-accurate-are-analyst-price-targets/)).
- Structural optimism: S&P 500 ratings Dec 2025 = 57.5% Buy / 37.7% Hold /
  **4.8% Sell** (FactSet count, via the same survey).

This is the pre-registered prior of TRIAL-FORECAST-LEDGER made concrete: the
street's forecasts carry a large, documented optimistic bias; our ledger
measures whether the MC forecast's bias is smaller on the same stocks, same
dates. UI copy may cite these numbers WITH sources; our own numbers wait for
the ledger to mature (2027-07).
