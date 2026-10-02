# The reading budget, free official sources, typed rows, and the digest's new sections (2026-09-30)

**Status: PAUSED by the owner at about 22:40 local, 2026-09-29.** The reader, the pool, the official-sources lane and the digest were all stopped. `SUPERVISOR_STOP` and `READER_POOL_STOP` are in place, and the Form 4 backfill was stopped by PID. Everything below was built and ran live before the pause. The payment-frame and bank-host refusals were finished after the pause, as code and offline tests only.

Licence: PRODUCT_EXPERIMENT. Paper and shadow only. No order path, size, cap or live book was changed.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE**. New frozen rows exist; none is graded yet |
| Browser page loads per day | **4,000, unchanged.** Dow Jones and social per-host caps are also unchanged. The loads are now spent by lane and by hour, not first-come |
| Reader during the US session, before the pause | about 205 OK of 212 loads in the 2 h to 14:40 UTC. The hourly allowance at US hours is 208 |
| New free sources, read by API or feed (no browser) | SEC Form 4, 8-K, 13D/G, 13F (EDGAR); House PTRs (Clerk index and PDFs); CFTC COT (TFF and disaggregated); FINRA short interest and short-sale volume; Federal Register (published and public inspection); Fed, ECB, BoJ, BoE, HKMA, White House and Treasury feeds |
| Rows landed | insider_tx **712** · filing_events **403** · politician_filings **403** · politician_trades **855** · positioning_cot **15,208** · short_interest **45,164** · policy_events **560** |
| Official API requests (24 h) | sec_form4 3,396 (includes the stopped 7-day backfill) · house_ptr 150 (it hit its own cap of 150) · all others 1-11 each |
| Digest run (real), `world_digest_20260929T141930Z` | $0.077 of the $0.90 cap. 60 frozen rows in total; 38 from the new sections: insiders 7, congress 4, policy 9, positioning 18 |
| Tests | 338 passed across the touched reader, digest and new test files. New files: `test_reader_budget.py`, `test_official_sources.py`, `test_digest_sections.py`, `test_reader_money_hosts.py` |
| LLM spend | $0.077 (DeepSeek, priced per call) |

## 1. The reading budget (`reader_scheduler.budget_*`, `reader_pool.Pool._budget_filter`)

**Lanes and their declared shares of the 4,000 daily loads:**

| lane | share |
|---|---|
| book_names | 0.24 |
| universe_names | 0.12 |
| markets_news | 0.20 |
| macro_world | 0.12 |
| politics_policy | 0.08 |
| official_releases | 0.04 |
| social | 0.11 (inside its unchanged per-host caps) |
| digest_asks | 0.06 |
| overhead (robots.txt reads) | 0.03 |

**Hourly allowance.** The allowance follows the UTC hour. It sums to the daily total and never falls below 60 an hour.

| UTC hours | window | loads per hour |
|---|---|---|
| 00-07 | Asia session | 182 |
| 08-10 | Europe | 104 |
| 11-12 | US pre-open | 169 |
| 13-19 | US session | 208 |
| 20-22 | US evening | 91 |
| 23 | Asia pre-open | 156 |

**How a load is granted:**
- The allowance binds on a rolling hour and on a rolling 10 minutes (the 10-minute limit is the hourly allowance ÷ 6 × 1.25).
- A lane under its hourly share is served.
- A lane over its share may borrow only when no other lane with something servable is under its own share.
- A lane that has spent 1.6 × its daily share borrows nothing while another lane is waiting.

**States and the daily cap:**
- When the budget or the day cap is spent, the pool **waits** and reports WAITING_FOR_CAP. That state is healthy and never counts as a stall. The pool no longer exits.
- **Bug fixed in the supervisor.** After a day-cap stop, the supervisor printed "retry at 19:14" at 21:25 and never relaunched. It had recomputed an already-past time from a stale log tail. The wait is now read from the throttle window itself (`caps_wait_s`).

**Health reporting:**
- Every load writes one row to `dowjones/budget_lanes.jsonl`.
- `reader_pool_status.json` → `budget.lanes` shows, per lane: loads and OK pages in the last 60 min and 24 h, pending, and the verdict.
- `reader_status.json` → `by_lane` shows lanes, OK pages by host and the official sources.
- `python -m backend.services.reader_report --lanes-hours N` prints pages by lane, host and UTC hour.

## 2. Sources, and how each is read (`backend/services/official_sources.py`, CLI `scripts/official_sources.py`)

All requests go through one fetcher. For every request it applies:
- a per-source daily cap;
- a gap per host;
- the host's robots.txt, read once a day;
- a bot check (403/429 with a block marker), which cools the source for 24 h and is never retried;
- the browser's money / checkout / mail URL rule;
- one log line in `official/requests.jsonl`.

SEC requests use the shared EDGAR rate limiter and the existing declared User-Agent.

| source | read by | public_utc rule |
|---|---|---|
| SEC Form 4 | Atom feed + filing index page + ownership XML | EDGAR acceptance; accepted after the filing window → 06:00 ET on the filing date |
| SEC 8-K / 13D-G / 13F | Atom feed (8-K items from the entry) | Atom `updated` = acceptance |
| House PTRs | Clerk annual zip index + PTR PDF text (pypdf); scanned PDFs have no text | disclosure date 23:59 ET; `tradable_from_utc` = next session open |
| CFTC COT | Public Reporting API (Socrata), 170 weeks | Friday 15:30 ET after the Tuesday report |
| FINRA short interest | Query API (POST, settlement date) | settlement + 8 business days, 23:00 UTC |
| FINRA short-sale volume | existing `finra_short_volume` store | a day's file is used only from the next session |
| Federal Register | API: documents + public inspection | issue day 06:00 ET; public inspection `filed_at` |
| Fed, ECB, BoJ, BoE, White House, Treasury | RSS | pubDate (a future-dated item is stamped when first seen) |
| HKMA | open API | date 23:59 HKT (the endpoint returned 502 / timeouts tonight) |

**Refused and recorded (`REFUSED_SOURCES`), nothing worked around:**
- Senate eFD: 403, and an agreement form in front of the data.
- Senate hearings XML: 403.
- PBoC: robots.txt disallows the path.
- Nasdaq earnings API: robots.txt disallows it.
- House hearings calendar: the page is built by script; no feed found.
- ETF flows: no official free source.

**Earnings calendar.** It stays on the MarketWatch earnings-calendar front (browser) and the existing providers. 8-K item 2.02 rows give realised earnings events.

**Finding for the owner of `ownership_forms.py` (not fixed there).** `_is_10b5_1` looks for `rule10b5-1Checked`. Live EDGAR XML uses `<aff10b5One>` (checked on 3 filings), so that parser returns "unknown" for almost every current Form 4. My rows fall back to the filing box and name the basis in `rule_10b5_1_basis`.

## 3. Tables: paths and join keys (all under `backend/data/optimus/official/tables/`)

All tables are append-only JSONL. They are deduplicated by `row_id`, and every row carries `source`, `public_utc`, `public_ts_basis` and `first_seen_utc`. Join by `ticker` (or `symbol`) and the date of `public_utc`, never by the trade, period or report date. The full field lists are in `official_sources.SCHEMAS`; `python -m scripts.official_sources --schema` prints them.

- `insider_tx.jsonl`: accession, ticker, issuer, owner, role (CEO/CFO/officer/director/10pct/other), code, side (buy/sell), shares, price, value_usd, rule_10b5_1 and its basis, transaction_date (not tradable), accepted_utc.
- `filing_events.jsonl`: form_type, accession, cik, company, role, ticker, items, event_types.
- `politician_filings.jsonl`: chamber, member, state_district, doc_id, disclosure_date, pdf_url.
- `politician_trades.jsonl`: member, owner, asset, ticker, asset_type, tx_type, trade_date, notification_date, disclosure_date, lag_days, amount_lo, amount_hi, tradable_from_utc.
- `positioning_cot.jsonl`: report, code, market, report_date, open_interest, groups (long/short/net/net_pct_oi/chg_net), headline_pctile_3y, headline_chg_z.
- `short_interest.jsonl`: symbol, settlement_date, short_qty, prev_short_qty, change_pct, avg_daily_volume, days_to_cover.
- `policy_events.jsonl`: source, title, url, agency, doc_type, significant, relevant, summary.

## 4. The digest's new sections (`backend/services/digest_sections.py`)

**Where the rows go.** Rows are written under `news_digest:insider_v0`, `congress_v0`, `policy_v0` and `positioning_v0`, through `world_digest.implication_records`. Deduplication is now per sub-tag. The existing `world_digest.grade` reads every `news_digest:` prefix. Section implications also enter the shadow signal; trust is 0, so nothing changed.

**Rule priors are declared, not measured:**
- Direction rows are shrunk into [0.45, 0.55].
- Size rows are written only for crowded shorts.

**Most interesting items from the real run:**
- **Insiders.** In 699 lines, 62 open-market buys and 140 lines under a 10b5-1 plan (skipped).
  - Cluster buys: ATCH (5 insiders, $163k).
  - Large officer buys: INBX CEO $329k, INR CFO $296k.
  - A discretionary CEO sale at BEKE of $84.6M.
  - 10% holders (Malone at LLYVK and LILA, GoldenTree at QVCG) are listed but not counted as insiders.
  - After the run, clusters were tightened to officers and directors with at least $50k in total. FNWD's $3.7k "cluster" would no longer qualify.
- **Policy**, from the DeepSeek synthesis of 57 official releases:
  - Fed and Treasury GENIUS-Act stablecoin rules → COIN up, JPM.
  - OFAC general licences → XOM.
  - FAA airworthiness directives on the 787 and 777 → BA down.
  - A $15B Iowa steel mill → NUE.
- **Congress.** 423 trades by 26 members were disclosed in 30 days, with a median lag of **23 days**. Two members bought MSFT (≥ $780k); four sold MSFT, four sold AAPL.
- **Positioning:**
  - COT: Russell E-mini leveraged funds at a 3-year low (→ IWM up, contrarian); UST bond and 5-year at a 3-year high (→ TLT); WTI and gasoline managed money at a 3-year high (→ USO).
  - Crowded shorts: SVRA at 36 days to cover.
  - Short-volume spikes: TRP, MDT, MMM and CVX at z ≥ 3.5.

## 5. Payments and banks (the owner's report "openclaw opens banks")

**What the history showed.** The dedicated Chrome visited no bank, broker or payment host. The coordinator found three loads of `buy.tinypass.com/checkout/offer/show`: the Piano subscription checkout that SCMP embeds in a frame on metered articles. The reader never navigates there: the `buy.` host label was already refused.

**What was added (`browser_policy.money_url_refusal`, applied through `url_refusal` on every navigation, open and click):**
- `MONEY_HOSTS`: HSBC, Hang Seng, BOCHK, Standard Chartered, ZA, Mox, Futu/moomoo, IBKR, Alpaca, PayPal, Wise, Revolut, Stripe, US and UK banks, crypto exchanges. Matched as a host suffix, so central banks are not caught.
- `CHECKOUT_HOSTS`: tinypass.com, piano.io, Stripe checkout and others.
- `CHECKOUT_PATH`: /checkout*, /subscribe, /payment(s), /billing, /cart, /offer/show.

**Where the rule now applies:**
- `web_reader.NEVER_HOSTS` and `host_ok`. This covers read_next asks and site searches.
- The official-sources fetcher.
- After every read, the pool lists the dedicated Chrome's targets:
  - a checkout **frame** makes that page PAYWALL_STUB, and its host reads only its fronts for 6 h (the metered articles are left alone);
  - a money or checkout **pop-up page** is closed after the instance proof.
- The supervisor sweeps pages the same way every tick.

**Mail** hosts stay in the message class (REFUSED_MESSAGE_URL).

**Central banks.** When a central bank page is open in the browser, `reader_status.json` labels it "central bank (public releases)".

**Hosts containing "bank" that my lanes would open:**

| host | how it is read |
|---|---|
| www.bankofengland.co.uk | RSS, API lane, no browser |
| www.ecb.europa.eu, www.boj.or.jp, api.hkma.gov.hk | feed / API only |
| www.federalreserve.gov | RSS, plus two browser fronts that existed before tonight |
| pbc.gov.cn | never opened (robots.txt) |

No commercial bank is opened on any path.

## 6. Unfinished

- **Not verified overnight** because of the pause: that the reader read through the whole US session, and that the supervisor survived the night.
- The Form 4 7-day backfill was stopped part-way. insider_tx covers about 30 h of live filings plus a partial backfill.
- House PTR PDFs: 105 of 403 read, capped by `house_ptr`'s 150 requests a day.
- HKMA returned 502 and timeouts.
- COT extremes include illiquid swap contracts with open interest above 100k. The contrarian prior is untested.
- TEVA shows +11,467% in FINRA short interest: that is the figure as reported, not checked.
- The shared test `test_guard_missing_input_contract.py` still fails on `fleet_manager` (another agent's module). I enrolled `official_sources`.

## CONTINUE FROM HERE (only when the owner says continue)

```
del backend\data\optimus\dowjones\SUPERVISOR_STOP backend\data\optimus\dowjones\READER_POOL_STOP
cmd /c backend\data\optimus\dowjones\supervisor_run.cmd       # supervisor --until 12:00; it launches the budgeted pool and `official_sources --due` every 15 min
python -m scripts.official_sources --backfill-form4 7         # resume the Form 4 history (unlocked; dedups by row id)
python -m scripts.official_sources --status                   # rows per table, requests per source
python -m scripts.world_digest --hours 24                     # the digest with the new sections ($0.90 cap)
python -m backend.services.reader_report --lanes-hours 8      # pages by lane / host / hour
```

## WHAT WORKS

- The reader spends its 4,000 loads by lane and by session-weighted hour. It waits at a cap instead of exiting, and its status shows per-lane pages for the last hour and day.
- Official data arrives by API, not by browser. Seven typed point-in-time tables were built in about an hour, with acceptance or disclosure times, and every refusal is recorded.
- The digest now has insider, policy, congress and positioning sections that write gradeable frozen rows for $0.08 a run.
- Bank, broker, payment, checkout and mail addresses are refused on every path, and checkout frames or pop-ups are handled. Pinned by 95 offline tests.

## WHAT DOES NOT

- No section's rows are graded yet, and the rule priors are declared, not measured.
- The official shared parser misreads the 10b5-1 flag (§2).
- The Senate, hearings, PBoC, Nasdaq and ETF-flow sources are not available.
- The overnight health verification did not happen (paused).

## HIGHEST-EV EXPERIMENT

Grade `news_digest:insider_v0` against a matched control **once it has 20 decision dates**:
- Cluster-buy names (officers and directors, at least $50k, not under 10b5-1) vs same-size, same-sector names with no insider buying.
- Dated by the EDGAR acceptance time, entering at the next open.
- Read by decision date and by year.

This costs $0 in reads (Form 4 is free and now lands every 15 minutes). It is the one section with literature behind it and a clean point-in-time timestamp.

---

## NIGHT CONTINUATION, 2026-09-30 00:00-08:30 local (interim; the final figures are in the section below it)

Resumed at 23:52 local. Interim state at 00:35 local: pool relaunched at 00:09 with the new code (Fed out of the browser, frame sweep deduplicated), Form 4 backfill relaunched with a 3,000-request reserve for the live feed, the 00:30 digest ran with the theme merge and the "what changed" header. Final section follows.
