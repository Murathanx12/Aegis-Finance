# Research v3 — crowd reads, StockTwits over the public API + verified X handles (2026-09-27 23:35 HKT)

**Licence: PRODUCT_EXPERIMENT.** Companion to `research_v3_crowd_reads.md`, which is untouched. Nothing here is a claim or an order.

**Why this file exists.** The browser crawl's results file was truncated to zero bytes at 19:12 HKT when C: filled. The `muratclaw` browser profile is now absent and `openclaw_client.health()` says DO NOT BROWSE, so the browser route was left alone. StockTwits answers its public JSON endpoint (`api.stocktwits.com/api/2/streams/symbol/<T>.json`) over plain HTTP: 68 of 68 OK. Reddit answers plain HTTP with 403, so Reddit beyond the first 15 names is still unread.

**How to read the columns.** The API returns the latest 30 messages. `7d` and `24h` count how many of those 30 fall in the window, so `7d = 30` means *at least* 30 (capped). `span_d` is the age in days of the 30th message: small = busy. Bull/Bear are self-tagged by posters; most messages carry no tag. Watchers is a stock, not a flow.

| Ticker | Tier | Watchers | msgs 24h | msgs 7d | span_d of 30 | Bull | Bear | Authors |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| AAPL | T2 | 995,144 | 29 | 29 | 0.62 | 6 | 4 | 25 |
| AMZN | T2 | 704,556 | 20 | 29 | 1.59 | 7 | 6 | 22 |
| NVDA | T2 | 668,630 | 30 | 30+ | 0.36 | 12 | 2 | 29 |
| META | T2 | 611,599 | 30 | 30+ | 0.6 | 8 | 1 | 27 |
| GOOG | T2 | 312,100 | 9 | 30+ | 1.83 | 14 | 4 | 28 |
| GOOGL | T2 | 231,489 | 20 | 28 | 1.5 | 9 | 2 | 21 |
| MU | T2 | 217,071 | 30 | 30+ | 0.11 | 17 | 1 | 23 |
| BA | T2 | 197,435 | 30 | 30+ | 0.8 | 12 | 0 | 21 |
| DKNG | T2 | 120,381 | 7 | 30+ | 1.79 | 9 | 0 | 26 |
| HOOD | T2 | 101,113 | 19 | 30+ | 1.56 | 13 | 5 | 22 |
| AVGO | T2 | 74,937 | 15 | 28 | 1.71 | 12 | 1 | 20 |
| CRM | T2 | 71,383 | 1 | 30+ | 3.95 | 4 | 0 | 25 |
| TSM | T2 | 69,808 | 3 | 29 | 2.96 | 7 | 0 | 24 |
| IONQ | T1 | 60,824 | 13 | 30+ | 1.51 | 10 | 3 | 22 |
| SNOW | T2 | 58,744 | 1 | 30+ | 4.01 | 14 | 7 | 19 |
| NOW | T2 | 44,405 | 5 | 30+ | 1.97 | 8 | 1 | 24 |
| VKTX | T1 | 39,793 | 30 | 30+ | 0.6 | 14 | 1 | 21 |
| BE | T2 | 36,466 | 28 | 30+ | 1.08 | 9 | 3 | 26 |
| MP | T1 | 36,197 | 7 | 30+ | 2.1 | 12 | 1 | 21 |
| QUBT | T1 | 33,549 | 3 | 30+ | 2.06 | 22 | 0 | 12 |
| NVO | T2 | 32,149 | 7 | 30+ | 1.9 | 9 | 0 | 26 |
| TEM | T2 | 21,770 | 3 | 30+ | 2.04 | 18 | 2 | 23 |
| AVPT | T1 | 21,320 | 1 | 5 | 51.79 | 17 | 0 | 12 |
| VRT | T2 | 20,337 | 0 | 30+ | 5.04 | 12 | 0 | 24 |
| CCJ | T1 | 17,492 | 1 | 17 | 8.91 | 8 | 1 | 24 |
| NTLA | T1 | 15,252 | 1 | 30+ | 3.89 | 10 | 3 | 21 |
| WDAY | T2 | 15,197 | 1 | 10 | 13.48 | 7 | 0 | 19 |
| AMGN | T2 | 15,000 | 1 | 30+ | 5.1 | 9 | 2 | 21 |
| VRTX | T1 | 12,839 | 0 | 25 | 10.98 | 13 | 3 | 20 |
| GEV | T2 | 10,655 | 1 | 30+ | 5.62 | 15 | 0 | 16 |
| SLDP | T1 | 10,449 | 1 | 24 | 10.02 | 17 | 0 | 21 |
| LEU | T1 | 8,796 | 1 | 23 | 9.04 | 12 | 1 | 22 |
| LNG | T2 | 7,950 | 1 | 7 | 17.7 | 9 | 1 | 20 |
| CLS | T2 | 7,647 | 0 | 30+ | 3.07 | 10 | 1 | 19 |
| HUBS | T1 | 6,874 | 0 | 21 | 10.11 | 9 | 1 | 15 |
| ACI | T1 | 5,962 | 0 | 7 | 36.99 | 15 | 1 | 17 |
| INCY | T2 | 5,634 | 0 | 8 | 51.63 | 9 | 0 | 17 |
| IRDM | T1 | 5,481 | 1 | 30+ | 5.8 | 19 | 0 | 19 |
| BBIO | T1 | 5,416 | 0 | 9 | 29.91 | 15 | 2 | 20 |
| AMSC | T1 | 4,886 | 3 | 21 | 13.1 | 4 | 0 | 10 |
| VG | T2 | 4,725 | 8 | 30+ | 1.85 | 15 | 0 | 17 |
| JAZZ | T2 | 4,225 | 0 | 6 | 37.01 | 7 | 0 | 25 |
| ABSI | T1 | 3,499 | 0 | 27 | 9.68 | 18 | 0 | 20 |
| BHVN | T1 | 3,447 | 0 | 30+ | 6.03 | 7 | 0 | 6 |
| COGT | T1 | 3,308 | 0 | 5 | 80.1 | 8 | 0 | 18 |
| PSNL | T2 | 2,910 | 1 | 12 | 18.72 | 5 | 0 | 12 |
| AGIO | T1 | 2,892 | 0 | 7 | 59.07 | 1 | 0 | 8 |
| HWM | T2 | 2,659 | 1 | 12 | 18.65 | 11 | 4 | 20 |
| PRCH | T1 | 2,656 | 0 | 4 | 54.13 | 17 | 2 | 14 |
| BN | T2 | 2,402 | 0 | 8 | 13.02 | 10 | 0 | 18 |
| SOC | T1 | 2,335 | 5 | 30+ | 1.97 | 7 | 2 | 19 |
| PRAX | T1 | 1,781 | 0 | 12 | 27.12 | 11 | 0 | 16 |
| PEGA | T1 | 1,768 | 0 | 0 | 66.11 | 12 | 1 | 23 |
| RGEN | T1 | 1,573 | 0 | 3 | 92.75 | 8 | 0 | 19 |
| NVT | T2 | 1,496 | 0 | 4 | 58.16 | 7 | 2 | 18 |
| KYTX | T1 | 1,490 | 4 | 30+ | 2.48 | 10 | 0 | 11 |
| HELE | T1 | 1,458 | 0 | 2 | 81.05 | 9 | 3 | 20 |
| SMPL | T1 | 1,221 | 0 | 3 | 79.32 | 19 | 0 | 13 |
| PRGS | T1 | 1,143 | 0 | 1 | 88.67 | 3 | 0 | 20 |
| WST | T1 | 898 | 0 | 0 | 199.91 | 3 | 0 | 19 |
| NVEC | T1 | 865 | 0 | 3 | 62.74 | 18 | 0 | 17 |
| NOVT | T1 | 805 | 0 | 2 | 117.6 | 7 | 0 | 23 |
| BSP | T2 | 588 | 0 | 6 | 40.92 | 8 | 7 | 20 |
| RHI | T1 | 577 | 0 | 1 | 81.22 | 3 | 0 | 19 |
| MAN | T1 | 564 | 0 | 1 | 68.83 | 3 | 2 | 10 |
| AGYS | T1 | 552 | 0 | 0 | 123.14 | 8 | 0 | 22 |
| SNDR | T2 | 437 | 0 | 1 | 240.06 | 0 | 6 | 18 |
| AARD | T1 | 144 | 0 | 0 | 77.53 | 8 | 5 | 20 |

**Near-silent on StockTwits (3 or fewer messages in 7 days), 13 names:** PEGA, RGEN, HELE, SMPL, PRGS, WST, NVEC, NOVT, RHI, MAN, AGYS, SNDR, AARD.

## Official X handles for the 20 names

| Ticker | Handle | Source | Note |
|---|---|---|---|
| PRAX | @praxismedicines | own_site | a LinkedIn aggregator says praxismedicine (no s); homepage wins |
| BBIO | @BridgeBioPharma | own_site |  |
| LEU | @centrus_energy | own_site |  |
| MP | @MPMaterials | own_site | the earlier guess MPMaterialsCo was a 404 |
| COGT | @CogentBio | own_site |  |
| AMSC | @powerresiliency | own_site | brand handle, not the company name |
| ABSI | @abscibio | own_site | also named in press-release footers |
| PRGS | @progresssw | own_site |  |
| QUBT | @QciQuantum | own_site |  |
| KYTX | @Kyverna_Tx | own_site |  |
| IONQ | @IonQ_Inc | own_site |  |
| NVEC | @NveCorporation | own_site |  |
| NTLA | @intelliatx | own_site |  |
| AGIO | @agiospharma | own_site |  |
| WST | @WestPharma | own_site |  |
| VKTX | @Viking_VKTX | secondary | no X link on vikingtherapeutics.com |
| DKNG | @DraftKings | secondary | draftkings.com answered 403; @DKSports is the sportsbook content account |
| SLDP | @solidpowerinc | secondary | solidpowerbattery.com answered 403 |
| AGYS | NOT FOUND | not_found | an account exists (AltIndex counts ~3.2K followers) but no source named the handle; no link on agilysys.com |
| NOVT | NOT FOUND | not_found | no link on novanta.com; no source found |

`own_site` = the link is on the company's own homepage. `secondary` = third-party mirrors only; treat as unconfirmed until the profile is opened. No X timeline was read: that needs the browser.

Receipts: `scratchpad/stocktwits_http.json`, `scratchpad/handles_verified.json` (session 2d30ddaf).
