# ORDER SHEET 2026-10-05  (frozen 2026-10-05T12:12:02 UTC)

REHEARSAL (paper; nothing is entered anywhere). Desk sheet window Mon 05 Oct 14:00 to Tue 06 Oct 14:00 HKT.
Calendar: calendar_2026-10-05.parquet (near-dated, rehearsal folder). Membership: PROXY, UNCONFIRMED (no WLS export yet).
Licence: PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill. Zero direction skill is assumed.
**PRICE SOURCE STALE**: CN: last bar 2026-09-30 (5 days) STALE. Check every price on the Terminal before entering (a move beyond 30% of the sheet's reference: see the split/gap rule).
Note: 3 of 5 slots filled: 40% of the book stays in cash by rule (fewer names report in this window).

NAV used for sizing: $1,024,667. Position budget: $200,000 (20% of notional; the other reading allows $204,933). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (1)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **3186 JT Equity** | SELL | **10,600** | MARKET AT OPEN |  | JPY | 0 | Tue 06 Oct 08:00 / Mon 20:00 | E6 | LIVE; report has happened by this open |

## BUY (3)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | **AEHR US Equity** | BUY | **1,776** | LIMIT | 112.57 | USD | 199,924 | Mon 05 Oct 21:30 / Mon 09:30 | UP | LIVE; report 2026-10-05 AMC, sell at the 2026-10-06 open; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |
| 3 | **LW US Equity** | BUY | **4,368** | LIMIT | 45.78 | USD | 199,967 | Mon 05 Oct 21:30 / Mon 09:30 | RE | LIVE; report 2026-10-06 BMO, sell at the 2026-10-06 open; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |
| 4 | **RPM US Equity** | BUY | **1,920** | LIMIT | 104.15 | USD | 199,968 | Mon 05 Oct 21:30 / Mon 09:30 | 64 | LIVE; report 2026-10-06 BMO, sell at the 2026-10-06 open; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |

## CONTROL (check on the blotter after entering)

- lines: **4** (1 SELL, 3 BUY)
- total SELL shares: **10,600**; total BUY shares: **8,064**
- total BUY notional at the limits: **$599,859** (never above $600,000)
- SHEET CODE: **E4310EE5**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-05 --entered <file>`: it must print the same code.

