# DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER (ROT5_TRAIL 2026-10-07; built 20261006T182456Z UTC; nothing is frozen)

**DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER.** This file is a preview. It is not frozen, not hashed, not gated (rehearsal: no gate), and `verify` will not accept it. The order sheet is the frozen `order_sheet.md` written by the scheduled task.

REHEARSAL (paper; nothing is entered anywhere). Book **ROT5_TRAIL**. Desk sheet window Wed 07 Oct 14:00 to Thu 08 Oct 14:00 HKT.
Calendar: calendar_2026-10-06.parquet (near-dated, rehearsal folder). Membership: PROXY, UNCONFIRMED (no WLS export).
Licence: PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill. Zero direction skill is assumed.
**WORST CASE (ROT5_TRAIL)** largest admissible book 5 x $200,000 = $1,000,000, sum|notional|/equity 0.98: loss at 5% stop $50,000; 10% stop $100,000; at a 2-sigma63 move $103,382 (the largest sigma63 among this sheet's book names).
This sheet's book after its tickets: 5 name(s), $992,709 gross = 0.97 of equity; loss at 5% stop $49,635; 10% stop $99,271; at 2-sigma63 $48,894; at 2x the trailing |earnings move| $58,600. No book here carries a stop (ROT5 exits at the open after the print; MAXTAIL holds) and a gap fills through any stop: the stop rows are reference arithmetic, not a bound.
DRIFT: the 20% cap is enforced AT ENTRY. Whether it also applies at all times is NOT settled by the public rules (OWNER-ONLY item 4); if it does, sell the trim below at the next open. No position is held through this sheet.
**PRICE SOURCE STALE**: CN: last bar 2026-09-30 (7 days) STALE; KR: last bar 2026-10-02 (5 days) STALE. Check every price on the Terminal before entering (a move beyond 30% of the sheet's reference: see the split/gap rule).

NAV used for sizing: $1,023,073. Position budget: $200,000 (20% of notional; the other reading allows $204,615). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (1)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **3391 JT Equity** | SELL | **14,100** | MARKET AT OPEN |  | JPY | 0 | Thu 08 Oct 08:00 / Wed 20:00 | UT | LIVE; DRY - DO NOT ENTER; report has happened by this open |

## BUY (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | **6323 JT Equity** | BUY | **6,600** | LIMIT | 4,720.0 | JPY | 197,497 | Thu 08 Oct 08:00 / Wed 20:00 | U6 | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 3 | **9983 JT Equity** | BUY | **400** | LIMIT | 78,424.0 | JPY | 198,877 | Thu 08 Oct 08:00 / Wed 20:00 | N3 | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 4 | **2809 JT Equity** | BUY | **6,900** | LIMIT | 4,521.0 | JPY | 197,769 | Thu 08 Oct 08:00 / Wed 20:00 | 99 | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 5 | **7649 JT Equity** | BUY | **24,100** | LIMIT | 1,306.0 | JPY | 199,542 | Thu 08 Oct 08:00 / Wed 20:00 | XF | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 6 | **3382 JT Equity** | BUY | **15,100** | LIMIT | 2,079.0 | JPY | 199,024 | Thu 08 Oct 08:00 / Wed 20:00 | HM | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |

## CONTROL (check on the blotter after entering)

- lines: **6** (1 SELL, 5 BUY)
- total SELL shares: **14,100**; total BUY shares: **53,100**
- total BUY notional at the limits: **$992,709** (never above $1,000,000)
- SHEET CODE: **2D2355E3**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-07 --entered <file>`: it must print the same code.

