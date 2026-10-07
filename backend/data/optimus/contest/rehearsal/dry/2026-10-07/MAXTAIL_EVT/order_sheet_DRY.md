# DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER (MAXTAIL_EVT 2026-10-07; built 20261006T182457Z UTC; nothing is frozen)

**DRY PREVIEW - NOT AN ORDER SHEET - DO NOT ENTER.** This file is a preview. It is not frozen, not hashed, not gated (rehearsal shadow book), and `verify` will not accept it. The order sheet is the frozen `order_sheet.md` written by the scheduled task.

SHADOW BOOK **MAXTAIL_EVT** (REHEARSAL; paper; never entered; graded beside ROT5_TRAIL by the same grader). Contract 5cfe5e7293a63b33 (PRODUCT_EXPERIMENT). Window Wed 07 Oct 14:00 to Thu 08 Oct 14:00 HKT.
**WORST CASE (MAXTAIL_EVT)** largest admissible book 5 x $200,000 = $1,000,000, sum|notional|/equity 1.00: loss at 5% stop $50,000; 10% stop $100,000; at a 2-sigma63 move $190,465 (the largest sigma63 among this sheet's book names).
This sheet's book after its tickets: 5 name(s), $999,954 gross = 1.00 of equity; loss at 5% stop $49,998; 10% stop $99,995; at 2-sigma63 $166,372; at 2x the trailing |earnings move| n/a. No book here carries a stop (ROT5 exits at the open after the print; MAXTAIL holds) and a gap fills through any stop: the stop rows are reference arithmetic, not a bound.
DRIFT: the 20% cap is enforced AT ENTRY. Whether it also applies at all times is NOT settled by the public rules (OWNER-ONLY item 4); if it does, sell the trim below at the next open. No position is held through this sheet.
MAXTAIL_EVT: rank: raw sigma63; 6 series refused as x2 one-day jumps (CTVA, CAPR, MRNA, KOD, LQDA, ALMS); event filter: 2807 US names with a vendor-announced print 2026-10-13..2026-11-12 in calendar_2026-09-29.parquet.
Refused: CTVA -- REFUSED_JUMP_X2 (one-day move x6.2 inside 63 sessions: split / spin / stitch / bad print)
Refused: CAPR -- REFUSED_JUMP_X2 (one-day move x2.8 inside 63 sessions: split / spin / stitch / bad print)
Refused: MRNA -- REFUSED_JUMP_X2 (one-day move x2.8 inside 63 sessions: split / spin / stitch / bad print)
Refused: KOD -- REFUSED_JUMP_X2 (one-day move x2.8 inside 63 sessions: split / spin / stitch / bad print)
Refused: LQDA -- REFUSED_JUMP_X2 (one-day move x2.3 inside 63 sessions: split / spin / stitch / bad print)
Refused: ALMS -- REFUSED_JUMP_X2 (one-day move x2.3 inside 63 sessions: split / spin / stitch / bad print)
Reserves: CIFR US Equity, AAOI US Equity, MXL US Equity, CDNL US Equity, IOVA US Equity, UMAC US Equity, AMLX US Equity, SNDK US Equity

NAV used for sizing: $1,000,000. Position budget: $200,000 (20% of notional; the other reading allows $200,000). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (0)

- none

## BUY (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **AXTI US Equity** | BUY | **2,198** | LIMIT | 90.99 | USD | 199,996 | Wed 07 Oct 21:30 / Wed 09:30 | 4D | LIVE; DRY - DO NOT ENTER; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 2 | **RXT US Equity** | BUY | **48,840** | LIMIT | 4.095 | USD | 200,000 | Wed 07 Oct 21:30 / Wed 09:30 | YV | LIVE; DRY - DO NOT ENTER; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 3 | **UTZ US Equity** | BUY | **13,342** | LIMIT | 14.99 | USD | 199,997 | Wed 07 Oct 21:30 / Wed 09:30 | J6 | LIVE; DRY - DO NOT ENTER; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 4 | **QMCO US Equity** | BUY | **5,600** | LIMIT | 35.71 | USD | 199,976 | Wed 07 Oct 21:30 / Wed 09:30 | 9N | LIVE; DRY - DO NOT ENTER; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 5 | **RARE US Equity** | BUY | **13,131** | LIMIT | 15.23 | USD | 199,985 | Wed 07 Oct 21:30 / Wed 09:30 | 7C | LIVE; DRY - DO NOT ENTER; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |

## CONTROL (check on the blotter after entering)

- lines: **5** (0 SELL, 5 BUY)
- total SELL shares: **0**; total BUY shares: **83,111**
- total BUY notional at the limits: **$999,954** (never above $1,000,000)
- SHEET CODE: **D9E3B113**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-07 --entered <file>`: it must print the same code.

