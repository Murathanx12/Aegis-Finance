# DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER (ROT5_DIR 2026-10-07; built 20261006T182456Z UTC; nothing is frozen)

**DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER.** This file is a preview. It is not frozen, not hashed, not gated (rehearsal shadow book), and `verify` will not accept it. The order sheet is the frozen `order_sheet.md` written by the scheduled task.

SHADOW BOOK **ROT5_DIR** (REHEARSAL; paper; never entered; graded beside ROT5_TRAIL by the same grader). Contract 298ee42706e4a2a6 (PRODUCT_EXPERIMENT). Window Wed 07 Oct 14:00 to Thu 08 Oct 14:00 HKT.
**WORST CASE (ROT5_DIR)** largest admissible book 5 x $200,000 = $1,000,000, sum|notional|/equity 1.00: loss at 5% stop $50,000; 10% stop $100,000; at a 2-sigma63 move $103,382 (the largest sigma63 among this sheet's book names).
This sheet's book after its tickets: 5 name(s), $992,709 gross = 0.99 of equity; loss at 5% stop $49,635; 10% stop $99,271; at 2-sigma63 $48,894; at 2x the trailing |earnings move| $58,600. No book here carries a stop (ROT5 exits at the open after the print; MAXTAIL holds) and a gap fills through any stop: the stop rows are reference arithmetic, not a bound.
DRIFT: the 20% cap is enforced AT ENTRY. Whether it also applies at all times is NOT settled by the public rules (OWNER-ONLY item 4); if it does, sell the trim below at the next open. No position is held through this sheet.
Direction source: target_revisions.parquet sha256 de10c593106f4ccc (395127 rows; first-seen basis: pulled_at (no first_seen column yet: an upper bound on when each row was known)); last pull 2026-10-06 17:09:34+00:00 (0.05 days old); 0 rows first seen after the freeze excluded; of 5 ROT5_TRAIL names: 0 admitted, 5 unrated (admitted, no evidence), 0 dropped.

NAV used for sizing: $1,000,000. Position budget: $200,000 (20% of notional; the other reading allows $200,000). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (0)

- none

## BUY (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **6323 JT Equity** | BUY | **6,600** | LIMIT | 4,720.0 | JPY | 197,497 | Thu 08 Oct 08:00 / Wed 20:00 | U6 | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 2 | **9983 JT Equity** | BUY | **400** | LIMIT | 78,424.0 | JPY | 198,877 | Thu 08 Oct 08:00 / Wed 20:00 | N3 | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 3 | **2809 JT Equity** | BUY | **6,900** | LIMIT | 4,521.0 | JPY | 197,769 | Thu 08 Oct 08:00 / Wed 20:00 | 99 | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 4 | **7649 JT Equity** | BUY | **24,100** | LIMIT | 1,306.0 | JPY | 199,542 | Thu 08 Oct 08:00 / Wed 20:00 | XF | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 5 | **3382 JT Equity** | BUY | **15,100** | LIMIT | 2,079.0 | JPY | 199,024 | Thu 08 Oct 08:00 / Wed 20:00 | HM | LIVE; DRY - DO NOT ENTER; report 2026-10-08 AMC, sell at the 2026-10-09 open; CONFIRMED; lot 100 (UNVERIFIED) |

## CONTROL (check on the blotter after entering)

- lines: **5** (0 SELL, 5 BUY)
- total SELL shares: **0**; total BUY shares: **53,100**
- total BUY notional at the limits: **$992,709** (never above $1,000,000)
- SHEET CODE: **54E1AEAC**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-07 --entered <file>`: it must print the same code.

