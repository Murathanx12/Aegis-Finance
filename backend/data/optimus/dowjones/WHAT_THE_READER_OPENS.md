# What the reader opens

Generated from the configuration the reader runs with, at 2026-10-07T03:52:24+00:00 UTC (`python -m backend.services.reader_report --what-opens`). Never edited by hand.

The reader's browser window is the dedicated Chrome profile `muratclaw`. It may open ONLY the hosts below, at most 4,000 page loads a day in total. Anything else on that window's screen is either one of these hosts' own frames (ads, video players, a publisher's subscription offer inside an article) or a fault to report. A subscription offer frame (for example `buy.tinypass.com`) is never navigated to: the page carrying it is classed PAYWALL_STUB and the frame is logged as PAYWALL_CHECKOUT_FRAME in `page_log.jsonl`; a pop-up page on a refused address is closed.


Subscription offers seen INSIDE allowed pages in the last 24 h (frames the site itself loads; never navigated to, never typed into; the site then reads its fronts only for 6 h): asia.nikkei.com (314: buy-ap.piano.io, js.stripe.com); cnbc.com (27: buy.tinypass.com); scmp.com (10: buy.tinypass.com)

## 1. Hosts the browser window may open

### Paid news (subscription or metered)
_Dow Jones on the owner's subscription; FT, Nikkei and SCMP fronts and free pieces only (a paywall is recorded, never worked around)_

- wsj.com (120/hour)
- barrons.com (120/hour)
- marketwatch.com (120/hour)
- ft.com (30/hour, 300/day)
- asia.nikkei.com (30/hour, 300/day)
- scmp.com (30/hour, 300/day)

### Free news
_public pages; a robots.txt refusal is recorded and the page is never opened_

- reuters.com (30/hour, 300/day)
- apnews.com (30/hour, 300/day)
- cnbc.com (30/hour, 300/day)
- finance.yahoo.com (30/hour, 300/day)
- bbc.com (30/hour, 300/day)

### Official releases
_US statistics, SEC and Treasury press pages_

- bls.gov (30/hour, 300/day)
- sec.gov (30/hour, 300/day)
- treasury.gov (30/hour, 300/day)

### Central banks (public releases)
_official public sites, not commercial banks_

- none in the browser (read by feed / API only; see section 2)

### Social (read only)
_no posting, no messages, no sign-in; per-host caps unchanged_

- x.com (40/hour, 150/day)
- reddit.com (40/hour, 150/day)
- stocktwits.com (40/hour, 150/day)

## 2. Read by feed or API only (never in a browser window)

### Central banks (public releases)
- www.federalreserve.gov: fed_rss (Federal Reserve RSS: all press releases, speeches, testimony; plus each item's full text by plain HTTP (policy_texts). Since 2026-09-30 the Fed is never opened in the visible browser; at most 160 requests/day)
- www.ecb.europa.eu: ecb_rss (ECB press RSS; at most 40 requests/day)
- www.boj.or.jp: boj_rss (Bank of Japan what's-new RSS; at most 40 requests/day)
- www.bankofengland.co.uk: boe_rss (Bank of England news RSS; at most 40 requests/day)
- api.hkma.gov.hk: hkma_api (HKMA open API: press releases (retried with backoff); when the API is down, HKMA's own RSS (press releases, speeches) on www.hkma.gov.hk; at most 40 requests/day)

### Official data (feed / API)
- disclosures-clerk.house.gov: house_ptr (House Clerk annual FD index (zip) + each PTR PDF's text; at most 150 requests/day)
- publicreporting.cftc.gov: cftc_cot (CFTC Public Reporting API: TFF futures + disaggregated futures; at most 40 requests/day)
- api.finra.org: finra_si (FINRA Query API consolidatedShortInterest (by settlement date); at most 80 requests/day)
- cdn.finra.org: finra_sv (FINRA Reg SHO daily short-sale volume files (existing store); at most 20 requests/day)
- www.federalregister.gov: fedreg (Federal Register API: documents published + public inspection; at most 60 requests/day)
- www.whitehouse.gov: whitehouse_rss (White House RSS: presidential actions, news; at most 40 requests/day)

### Official releases
- www.sec.gov: sec_form4 (EDGAR latest-filings Atom + filing index page + ownership XML; at most 14000 requests/day)
- www.sec.gov: sec_8k (EDGAR latest-filings Atom (8-K items from each entry); at most 300 requests/day)
- www.sec.gov: sec_13dg (EDGAR latest-filings Atom (SCHEDULE 13D / 13G and SC 13D/G); at most 200 requests/day)
- www.sec.gov: sec_13f (EDGAR latest-filings Atom (13F-HR filed; holdings not parsed); at most 100 requests/day)
- www.sec.gov: sec_tickers (SEC company_tickers.json (CIK -> ticker); at most 4 requests/day)
- home.treasury.gov: treasury_rss (US Treasury RSS; at most 40 requests/day)

## 3. Refused on every path (browser, links, digest asks, feeds)

- **money_hosts (banks, brokers, payment, crypto)**: airstarbank.com, alipay.com, alpaca.markets, americanexpress.com, bankofamerica.com, barclays.co.uk, binance.com, bochk.com, bybit.com, capitalone.com, chase.com, citi.com, citibank.com, citibank.com.hk, coinbase.com, dbs.com, dbs.com.hk, etrade.com, fidelity.com, firstrade.com, fusionbank.com, futuhk.com, futuholdings.com, futunn.com, hangseng.com, hkbea.com, hsbc.co.uk, hsbc.com, hsbc.com.hk, ibkr.com, icbcasia.com, interactivebrokers.com, interactivebrokers.com.hk, itigerup.com, kraken.com, livibank.com, lloydsbank.com, moomoo.com, mox.com, okx.com, payme.hsbc, paypal.com, paypal.me, revolut.com, robinhood.com, sc.com, schwab.com, standardchartered.com, standardchartered.com.hk, stripe.com, tastytrade.com, tdameritrade.com, tigerbrokers.com, transferwise.com, usbank.com, vanguard.com, venmo.com, webull.com, wechatpay.com, welab.bank, wellsfargo.com, wise.com, za.group
- **checkout_hosts (subscription checkout providers)**: chargebee.com, checkout.stripe.com, js.stripe.com, paddle.com, pay.google.com, piano.io, recurly.com, tinypass.com, zuora.com
- **mail_and_message_hosts**: chat.reddit.com, discord.com, gmail.com, mail.google.com, mail.yahoo.com, messenger.com, outlook.live.com, outlook.office.com, proton.me, protonmail.com, web.telegram.org, web.whatsapp.com
- **other_never_hosts**: app.alpaca.markets, railway.app, railway.com

Address rules (any host):
- checkout / payment path (any host): `(^|/)(checkout[^/]*|subscribe|subscription|subscriptions|payment|payments|billing|cart)(/|$)|/offer/show`
- store / billing path segment (any host): `(^|/)(checkout|billing|payment|payments|pay|purchase|subscribe|subscription|subscriptions|upgrade|order|orders|cart|buy|add-card|addcard|wallet|premium|pricing|donate)(/|$)`
- host labels refused: `billing, buy, cart, checkout, commerce, customercenter, pay, payments, premium, shop, store, subscribe`
- mail / message path: `(^|/)(messages|message|compose|inbox|chat|dm|i/chat)(/|$)`
- social write path: `(^|/)(intent|submit|compose|share|settings)(/|$)`

Actions: no forms, typing, sign-in, posting, messages or payments; a reader clicks links only; buttons and text boxes are never touched.

Sources looked at and NOT read:
- senate_efd: BOT_CHECK_OR_FORM: 403 Access Denied to a plain request, and the search sits behind an agreement form; not submitted, not worked around
- senate_hearings: ACCESS_DENIED: 403 on the XML and on robots.txt
- pboc: ROBOTS_DISALLOWED: pbc.gov.cn robots.txt disallows the English news path
- nasdaq_earnings: ROBOTS_DISALLOWED: api.nasdaq.com robots.txt disallows it
- house_hearings: JS_RENDERED: the calendar is built by script in the page; no machine-readable feed was found. A candidate for the browser lane
- etf_flows: NO_OFFICIAL_FREE_SOURCE: issuer pages publish shares outstanding per fund, but no official free flow feed across funds was found
