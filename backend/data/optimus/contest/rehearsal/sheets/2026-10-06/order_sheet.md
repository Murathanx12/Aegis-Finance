# ORDER SHEET 2026-10-06  (frozen 2026-10-06T07:04:06 UTC)

REHEARSAL (paper; nothing is entered anywhere). Desk sheet window Tue 06 Oct 14:00 to Wed 07 Oct 14:00 HKT.
Calendar: calendar_2026-10-06.parquet (near-dated, rehearsal folder). Membership: PROXY, UNCONFIRMED (no WLS export yet).
Licence: PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill. Zero direction skill is assumed.
**PRICE SOURCE STALE**: CN: last bar 2026-09-30 (6 days) STALE. Check every price on the Terminal before entering (a move beyond 30% of the sheet's reference: see the split/gap rule).
Note: 1 of 5 slots filled: 80% of the book stays in cash by rule (fewer names report in this window).

NAV used for sizing: $1,023,073. Position budget: $200,000 (20% of notional; the other reading allows $204,615). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (3)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **AEHR US Equity** | SELL | **1,776** | MARKET AT OPEN |  | USD | 0 | Tue 06 Oct 21:30 / Tue 09:30 | CR | LIVE; report has happened by this open |
| 2 | **LW US Equity** | SELL | **4,368** | MARKET AT OPEN |  | USD | 0 | Tue 06 Oct 21:30 / Tue 09:30 | D3 | LIVE; report has happened by this open |
| 3 | **RPM US Equity** | SELL | **1,920** | MARKET AT OPEN |  | USD | 0 | Tue 06 Oct 21:30 / Tue 09:30 | XM | LIVE; report has happened by this open |

## BUY (1)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | **3391 JT Equity** | BUY | **14,100** | LIMIT | 2,235.0 | JPY | 199,789 | Wed 07 Oct 08:00 / Tue 20:00 | HE | LIVE; report 2026-10-07 AMC, sell at the 2026-10-08 open; CONFIRMED; lot 100 (UNVERIFIED) |

## CONTROL (check on the blotter after entering)

- lines: **4** (3 SELL, 1 BUY)
- total SELL shares: **8,064**; total BUY shares: **14,100**
- total BUY notional at the limits: **$199,789** (never above $200,000)
- SHEET CODE: **B1543860**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-06 --entered <file>`: it must print the same code.

