# Opportunity Explorer, brain page and showcase fixes (C4, 2026-10-06)

Licence: PRODUCT_EXPERIMENT. Nothing on these pages is a claim of alpha or an order.

## What shipped

| Piece | Where |
|---|---|
| Receipt builder (offline, $0) | `scripts/opportunities_build.py` -> `backend/data/optimus/opportunities/opportunities_<asof>_<runid>.json` |
| Read side | `backend/services/opportunities.py` (newest receipt by the stamp in the NAME, never mtime) |
| API (read-only) | `backend/routers/opportunities.py`: `GET /api/opportunities/latest`, `GET /api/opportunities/{list_id}`; 404 when no receipt or unknown list, 422 on a malformed id |
| Page | `frontend/src/app/opportunities/page.tsx` (`/opportunities`, sidebar "Stocks > Opportunity Explorer") |
| Brain page | `frontend/src/app/brain/page.tsx` (`/brain`, sidebar "Tools > Optimus Brain") |
| Build hook | `scripts/stock_lists_v3_build.py` section 3 now also writes `<WORK>/roi_list_v3.json` (ranked + excluded rows); the next build's ranking is read from JSON instead of the rendered Markdown |
| Tests | `backend/tests/test_opportunities_router.py` (404, 422, shape, serve-time age, newest-by-name, unreadable skipped, foreign links, registration, CORS origin) |

Rebuild the receipt: `python -m scripts.opportunities_build` (about 10 s). A second run writes a new file; it never overwrites.

## Lists in the switcher

| list_id | Source | Rows | Label on the page |
|---|---|---|---|
| `roi_v3` | v3.2 Markdown section 3 table + its EXCLUDED table | 65 | HYPOTHESIS ranking; the excluded names (n < 5, research-note veto) are shown and marked, not hidden |
| `thesis_cards_v3` | v3 Markdown section 2 | 69 | a verdict is about evidence, not a price call |
| `analyst_upside_v3` | v3 Markdown 5a + 5b tables + the 5c paragraph | 700 | SCREEN, not a buy list (target-level upside measured perverse) |
| `human_ai_thematic_v2`, `_v1` | `llm_portfolio/books.jsonl` | 23, 28 | v1 = CONTROL |
| `reviewer_opus_2026-09-25` | books.jsonl | 10 | 60% non-USD |
| `cards_supports_2026-09-25`, `probe_equal_2026-09-26` | books.jsonl | 20, 11 | |
| `murat_core_satellite_2026-09-27` | books.jsonl | 11 | BENCHMARK_OVERLAY: 80% SPY core, never a flagship |
| `bloomberg_rehearsal_2026-09-27` | books.jsonl | 10 | MAGNITUDE RANKING: not a long list |

Declared CASH lines are not rows (they are the list's `cash_weight`). The v3 lists were built on 2026-09-27; the enrichment (price, targets, insiders, news) is as of the receipt run.

## Column map (owner's order -> field -> receipt source)

| # | Owner column | Field(s) | Source |
|---|---|---|---|
| 1 | Ticker | `ticker`, `company_name`, `exchange`, `currency`, `links` | name: newest thesis card, else SEC Form 4 issuer name, else yfinance 09-27 pull, else FINRA issue name. Exchange: ticker suffix for foreign listings (`services/opportunities.SUFFIX_EXCHANGE`), `potential_universe/2026-09-02.jsonl` identity for US. Links are built from the ticker (Yahoo, Yahoo analysts, MarketWatch, MarketWatch analysts, Benzinga, SEC EDGAR by CIK from `official/company_tickers.json`); US-only pages are null for foreign tickers |
| 2 | Weight | `weight` (books), `rank` + `list_score` (ranking), `list_score` (screen) | books.jsonl; v3 Markdown |
| 3 | Sector | `sector`, `sector_source`, `theme` | `config.WHY_MOVED_TICKER_SECTOR` (GICS) first, then the Alpaca industry label in the 09-02 potential universe; the book's theme is shown when neither exists |
| 4 | Price vs analyst low / median / high | `price`, `analyst`, `upside` | last close from `llm_portfolio/global_bars.parquet` (then `prices_2025_26/bars.parquet`); targets from `analyst/target_snapshots.parquet` latest row, else the MarketWatch analyst snapshot; analyst count from the 09-27 yfinance pull, else MarketWatch. Upside = target / last close - 1, basis printed |
| 5 | Why picked | `why_picked[]` (1-3, each with `service`) | book thesis (llm_portfolio), ROI formula (stock_lists_v3_build section 3), analyst screen, thesis card verdict + bull line, fundamentals proxy |
| 6 | Dates / news | `catalysts[]`, `news[]` | card `upcoming_dates` (future only, with URL), `straddle_forward/earnings_cache.json`, EDGAR 8-K 2.02 + 91d estimate (labelled ESTIMATE), MarketWatch next earnings; news from the card's dated items, `news_corpus/*/<day>.jsonl` (30 days), `dowjones/_claims`, `sources/claims.jsonl` |
| 7-8 | Insiders / holders / other | `insiders`, `short_interest`, `politicians`, `revision` | SEC Form 4 open-market P/S (`official/tables/insider_tx.jsonl`, 180 days), FINRA short interest, House PTRs, `services/revision_flow.compute` (90-day net raises, firms, median change) |
| - | MoveScore | `move_score` (label MAGNITUDE) | sigma of the last 63 daily log returns x sqrt(21) x sqrt(2/pi), from the same bars |
| - | Direction | `direction` (UP / DOWN / NEUTRAL / MIXED) | consensus rating sign + 90-day revision sign; never from sigma. MIXED = the two disagree; `single_source` when only one exists |
| - | Falsifier, horizon, evidence | `falsifier`, `horizon`, `evidence` | book position or card; list horizon; EARLY_EVIDENCE with sessions since the book's as-of (books), OBSERVED (lists) |
| - | Lane | `lane`, `risk_flags` | HIGH_RISK_INNOVATION when < 5 analysts or none, expected 21-session move >= 15%, an "against" card, or a PDUFA/FDA/trial date; shown as a badge in the same table |
| - | Freshness | `last_update_utc`, `last_update_age_days` | newest of price date, target observation, card run; the age is computed by the router at serve time |

The sigma63 / "2 sigma 126 sessions" vocabulary the owner did not want is gone from the page: the legend says, in two sentences, that MoveScore is how big a move may be and Direction is which way the analysts lean.

## What is null today, and why (receipt `opportunities_2026-10-06_20261006T161647Z.json`)

- **Insiders: null on most rows** (47 of 65 ROI rows, 594 of 700 screen rows). The official Form 4 table holds filings public since 2026-09-18 only, so "no open-market buy or sell in 180 days" really means "since 09-18". Foreign listings never have a Form 4.
- **Foreign listings** (reviewer book: 6 of 10; cards_supports: 8 of 20): no analyst targets, upside, direction, revisions, short interest or US news; the snapshot covers US tickers only. Name, exchange, currency, price and MoveScore are filled.
- **Revision flow: null for 7-124 rows per list.** No dated target revision in the 90 days before the run; absent, not zero.
- **Screen rows (`analyst_upside_v3`)**: no weight and no horizon by construction; 673 of 700 have no falsifier because no thesis card exists for them.
- **Sector**: null for foreign tickers and ETFs (no GICS/industry receipt on disk; the book theme is shown instead).
- **News**: 466 rows had at least one corpus item DROPPED because its title names neither the ticker nor the company (example: a 2026-10-02 MarketWatch robotics column tagged VKTX). The drop is recorded in `missing_because["news.dropped"]`.
- **Learning reports** (`learning_reports/report_<day>.json`) have no API endpoint; the brain page shows their health probe (`learn_rota`) and the daily digest (404 on this machine: none written yet).

## The showcase bugs: root causes and fixes

1. **The whole public website called a placeholder.** On 2026-10-06 the deployed site at aegis-finance-six.vercel.app requested `https://aegis-finance-six.vercel.app/[SENSITIVE]/api/...` for every call: 16 of 16 on the dashboard and 6 of 6 on /dev, all 404. The site's API-URL build variable held a redaction placeholder instead of a URL. Next inlined it, and `fetch("[SENSITIVE]/api/x")` resolved as a relative path on the site's own origin. Nothing failed at build time, and every card (the brain cards included) fell back to its empty state. **Fix:** `frontend/src/lib/api.ts` now has `resolveApiBase`. A value that is not an absolute http(s) URL is refused and reported once in the console, and the documented public API from README "Live" is used instead. `lib/control-api.ts` now reads the same resolver. **The Vercel variable still needs correcting. That is an attended change, and it is not made here.**
2. **The backend blocked the site's origin.** The Railway API echoed `Access-Control-Allow-Origin` for `http://localhost:3000` and for nothing else (measured with curl). So even a correct URL would have been blocked in the browser. **Fix:** `backend/main.py` always adds `https://aegis-finance-six.vercel.app` to the allowed origins. An `ALLOWED_ORIGINS` env list now adds origins and can no longer drop the site. This is pinned by `test_public_site_origin_is_always_allowed`. It takes effect on the next deploy.
3. **The brain map (optimus-brain-alpha.vercel.app, the "neuron" view).** It loads, and the only console error is a missing favicon. What is visibly wrong: the legend text overlaps the drag/zoom hint at the bottom of the canvas, bubbles are clipped at the canvas edges, and the data is the 2026-07-12 build (168 nodes, against about 395 pages after the 08-29 repair). That site is built by `showcase/build.py` in the **optimus** repo, which is a separate repo and a separate Vercel deploy. It is **not changed here**. The owed fix: rebuild with `python showcase/build.py`, clamp node positions inside the canvas, and move the legend below the canvas.
4. **NN showcase.** No page in this repo rendered nn_lab before today. The new `/brain` page has a "Neural-net lab" card, built from the `lab_loop:nn_lab` probe in `/api/health/full`. It currently reads **stopped by operator**, which is the true state. A dedicated nightly-IC chart needs an endpoint over `nn_lab_history.jsonl`, and none exists yet.

`/brain` uses existing endpoints only: `/api/health/full` (subsystem probes grouped as Memory / Neural-net lab / Learning / Decisions / Senses, with a verdict strip), `/api/ic/decisions` (today's contract, the ledger lifecycle as a timeline, and actionable rows first) and `/api/optimus/digest` (404 is shown as "none written yet", never as zeros).

## Review fixes (REVIEW_2026-10-06_C4_OPPORTUNITY_EXPLORER.md, F1-F8, F13)

Receipt after the fixes: `opportunities_2026-10-06_20261006T174255Z.json` (947 rows).

- **F1, the badge.** It is now three separate checks. COVERAGE fires when fewer than 3 firms made a dated target action in 180 days (`target_revisions.parquet`). BINARY EVENT fires on an FDA or trial word (BLA, NDA, sNDA, PDUFA, CRL, readout, topline, Phase 3, AdCom) within 63 weekdays. RUNWAY fires when XBRL cash and equivalents cover less than 4 quarters of the latest quarterly operating loss; this is a lower bound, because marketable securities are not in that XBRL tag. The badge needs 2 of the 3. The thresholds live in `config.OPPORTUNITIES_*`. ROI-list badges fell from 30 of 65 to 7 of 65: VKTX, IONQ, COGT, ABSI, AGIO, KYTX, SLDP. MAN and RHI now read CORE with no flags. Pinned in `backend/tests/test_opportunities_build.py` on 2026-10-06 numbers: KYTX (3 flags), SLDP (2) and SOC (2) carry the badge, and NOVT carries one flag.
  - **QUBT carries none of the three flags, and that is reported, not tuned away.** It has 4 firms with dated targets, 8.2 quarters of cash and no FDA event. Catching the owner's read of QUBT would need a fourth axis, such as price-to-sales or pre-revenue. That is the owner's decision.
  - **SOC on the live receipt.** `target_revisions.parquet` was re-pulled on 2026-10-06 and gained two SOC initiations: JP Morgan on 10-02 and William Blair on 10-05. SOC now has 4 dated firms, so on today's data it carries runway only, which is one flag and no badge.
- **F2, analyst stance.** The "Direction" column is now **Analyst stance**: positive, negative, neutral or mixed, in muted colours, and never green. When the stance is positive but the price is above the median target, the row prints "price is above the median target". There are 13 such rows.
- **F3, upside.** Upside has its own sortable column. It is green only at +5% or more AND with more than one target. Below +5% it is grey with a **LOW UPSIDE** tag (30 rows). It reads **single target** when low equals high or there is one analyst (32 rows); a single-target row draws no range strip. The analyst count is printed in the cell. The old Coverage column was removed.
- **F4, insider window.** The header reads "Insiders (since 09-18)". A row with no trades says "none since 09-18". The detail panel says "18 days covered (the table starts 2026-09-18)". The null reason says "this is NOT a 180-day answer".
- **F5, why picked.** "Why picked" only quotes a card dated on or before the list's freeze. A card from the freeze day itself is labelled "same day; order not provable", because cards record no run time. A later card appears in a dashed box, "Later commentary (post-freeze)", on 76 rows. The fundamentals-percentile filler is gone, with 0 rows left.
- **F6, freshness.** The builder takes the newest `stock_lists/<day>/` with a rendered `stock_lists_<day>_v*.md`; the date is no longer hard-coded. The router serves the newest receipt by the stamp in its name and returns its age from `generated_utc`. The page prints the age, and shows a red STALE (or UNKNOWN) banner past `config.OPPORTUNITIES_STALE_DAYS = 3`. The parsed receipt is cached by path and size (F12).
- **F7, dates.** Under every price strip: "targets 2026-09-29 (n from yfinance...) · close 2026-10-05".
- **F8, revision gap.** The list header prints "frozen <date> · analyst revisions through <date> · Form 4 data since <date>". The stance tooltip and the detail panel both name the date the revision data ends.
- **F9, magnitude sort.** Sorting a long list by MoveScore shows the amber "this is now a MAGNITUDE ranking" banner.
- **F10, API fallback.** `resolveApiBase` falls back to the production API only in a production build. A developer's malformed value goes to localhost.
- **F13, glossary.** CRL, PDUFA, BLA, NDA and sNDA are dotted-underline tooltips wherever they appear (falsifier, reasons, dates), with a glossary line under the legend. CRL reads "FDA Complete Response Letter: not approvable as filed".

**Deployment.** Production will 404 until a receipt is either committed or built by a scheduled job. Three options:
- Commit the newest receipt, `backend/data/optimus/opportunities/opportunities_<asof>_<runid>.json` (about 5.9 MB).
- Add `python -m scripts.opportunities_build` to the task_keeper daily list, after the bars, analyst and official pulls, as C10 did for the catalog. `daily_pass.py` was not edited.
- Have Railway build the receipt on deploy. For that the builder needs `global_bars.parquet`, `target_snapshots.parquet`, `target_revisions.parquet`, `sec_facts_history.parquet` and `official/tables/*.jsonl`, and none of these is in git.
