# ORDER SHEET 2026-09-30  (frozen 2026-09-29T13:48:41 UTC)

REHEARSAL (paper; nothing is entered anywhere). Desk sheet window Wed 30 Sep 14:00 to Thu 01 Oct 14:00 HKT.
Calendar: calendar_2026-09-30.parquet (near-dated, rehearsal folder). Membership: PROXY, UNCONFIRMED (no WLS export yet).
Licence: PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill. Zero direction skill is assumed.
**PRICE SOURCE STALE**: KR: last bar 2026-09-23 (7 days) STALE; TW: last bar 2026-09-24 (6 days) STALE. Check every price on the Terminal before entering (a move beyond 30% of the sheet's reference: see the split/gap rule).
Reserves (take the next when a name is not in WLS, its date moved, or it is not tradable): HUBG US Equity, MKC US Equity

NAV used for sizing: $1,000,000. Position budget: $200,000 (20% of notional; the other reading allows $200,000). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (0)

- none

## BUY (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **PRGS US Equity** | BUY | **4,833** | LIMIT | 41.38 | USD | 199,990 | Wed 30 Sep 21:30 / Wed 09:30 | 9W | LIVE; report 2026-10-01 AMC; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |
| 2 | **MU US Equity** | BUY | **180** | LIMIT | 1,107.0 | USD | 199,260 | Wed 30 Sep 21:30 / Wed 09:30 | HD | LIVE; report 2026-10-01 AMC; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |
| 3 | **AYI US Equity** | BUY | **622** | LIMIT | 321.21 | USD | 199,793 | Wed 30 Sep 21:30 / Wed 09:30 | AC | LIVE; report 2026-10-01 BMO; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |
| 4 | **ACN US Equity** | BUY | **1,091** | LIMIT | 183.19 | USD | 199,860 | Wed 30 Sep 21:30 / Wed 09:30 | AD | LIVE; report 2026-10-01 BMO; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |
| 5 | **4088 JT Equity** | BUY | **10,600** | LIMIT | 2,959.0 | JPY | 199,192 | Thu 01 Oct 08:00 / Wed 20:00 | Y6 | LIVE; report 2026-10-05 UNKNOWN; NOT CONFIRMED (VENDOR_ESTIMATE); lot 100 (UNVERIFIED) |

## CONTROL (check on the blotter after entering)

- lines: **5** (0 SELL, 5 BUY)
- total SELL shares: **0**; total BUY shares: **17,326**
- total BUY notional at the limits: **$998,095** (never above $1,000,000)
- SHEET CODE: **BE6D9938**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-09-30 --entered <file>`: it must print the same code.

