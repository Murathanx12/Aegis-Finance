# ORDER SHEET 2026-10-04  (frozen 2026-10-04T06:33:39 UTC)

REHEARSAL (paper; nothing is entered anywhere). Desk sheet window Sun 04 Oct 14:00 to Mon 05 Oct 14:00 HKT.
Calendar: calendar_2026-10-04.parquet (near-dated, rehearsal folder). Membership: PROXY, UNCONFIRMED (no WLS export yet).
Licence: PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill. Zero direction skill is assumed.
Note: 1 of 5 slots filled: 80% of the book stays in cash by rule (fewer names report in this window).

NAV used for sizing: $1,024,667. Position budget: $200,000 (20% of notional; the other reading allows $204,933). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (1)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **4088 JT Equity** | SELL | **10,600** | MARKET AT OPEN |  | JPY | 0 | Mon 05 Oct 08:00 / Sun 20:00 | EU | LIVE; report has happened by this open |

## BUY (1)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | **3186 JT Equity** | BUY | **10,600** | LIMIT | 2,960.0 | JPY | 198,674 | Mon 05 Oct 08:00 / Sun 20:00 | HK | LIVE; report 2026-10-05 AMC, sell at the 2026-10-06 open; CONFIRMED; lot 100 (UNVERIFIED) |

## CONTROL (check on the blotter after entering)

- lines: **2** (1 SELL, 1 BUY)
- total SELL shares: **10,600**; total BUY shares: **10,600**
- total BUY notional at the limits: **$198,674** (never above $200,000)
- SHEET CODE: **BE79BA12**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-04 --entered <file>`: it must print the same code.

