# ORDER SHEET 2026-10-01  (frozen 2026-10-01T06:33:28 UTC)

REHEARSAL (paper; nothing is entered anywhere). Desk sheet window Thu 01 Oct 14:00 to Fri 02 Oct 14:00 HKT.
Calendar: calendar_2026-10-01.parquet (near-dated, rehearsal folder). Membership: PROXY, UNCONFIRMED (no WLS export yet).
Licence: PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill. Zero direction skill is assumed.
**PRICE SOURCE STALE**: KR: last bar 2026-09-23 (8 days) STALE. Check every price on the Terminal before entering (a move beyond 30% of the sheet's reference: see the split/gap rule).
Note: 1 of 5 slots filled: 80% of the book stays in cash by rule (fewer names report in this window).

NAV used for sizing: $1,000,000. Position budget: $200,000 (20% of notional; the other reading allows $200,000). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (4)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **PRGS US Equity** | SELL | **4,833** | MARKET AT OPEN |  | USD | 0 | Thu 01 Oct 21:30 / Thu 09:30 | JM | LIVE; report has happened by this open |
| 2 | **MU US Equity** | SELL | **180** | MARKET AT OPEN |  | USD | 0 | Thu 01 Oct 21:30 / Thu 09:30 | R7 | LIVE; report has happened by this open |
| 3 | **AYI US Equity** | SELL | **622** | MARKET AT OPEN |  | USD | 0 | Thu 01 Oct 21:30 / Thu 09:30 | Y3 | LIVE; report has happened by this open |
| 4 | **ACN US Equity** | SELL | **1,091** | MARKET AT OPEN |  | USD | 0 | Thu 01 Oct 21:30 / Thu 09:30 | EP | LIVE; report has happened by this open |

## BUY (1)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | **NKE US Equity** | BUY | **5,380** | LIMIT | 37.17 | USD | 199,975 | Thu 01 Oct 21:30 / Thu 09:30 | 7F | LIVE; report 2026-10-01 AMC, sell at the 2026-10-02 open; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |

## CONTROL (check on the blotter after entering)

- lines: **5** (4 SELL, 1 BUY)
- total SELL shares: **6,726**; total BUY shares: **5,380**
- total BUY notional at the limits: **$199,975** (never above $200,000)
- SHEET CODE: **1772ED78**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-01 --entered <file>`: it must print the same code.

