# SHADOW SHEET MAXTAIL_EVT 2026-10-07  (frozen 2026-10-07T06:32:45 UTC)

SHADOW BOOK **MAXTAIL_EVT** (REHEARSAL; paper; never entered; graded beside ROT5_TRAIL by the same grader). Contract 5cfe5e7293a63b33 (PRODUCT_EXPERIMENT). Window Wed 07 Oct 14:00 to Thu 08 Oct 14:00 HKT.
**WORST CASE (MAXTAIL_EVT)** largest admissible book 5 x $200,000 = $1,000,000, sum|notional|/equity 1.00: loss at 5% stop $50,000; 10% stop $100,000; at a 2-sigma63 move $190,560 (the largest sigma63 among this sheet's book names).
This sheet's book after its tickets: 5 name(s), $999,972 gross = 1.00 of equity; loss at 5% stop $49,999; 10% stop $99,997; at 2-sigma63 $169,471; at 2x the trailing |earnings move| n/a. No book here carries a stop (ROT5 exits at the open after the print; MAXTAIL holds) and a gap fills through any stop: the stop rows are reference arithmetic, not a bound.
DRIFT: the 20% cap is enforced AT ENTRY. Whether it also applies at all times is NOT settled by the public rules (OWNER-ONLY item 4); if it does, sell the trim below at the next open. No position is held through this sheet.
MAXTAIL_EVT: rank: raw sigma63; 6 series refused as x2 one-day jumps (CTVA, CAPR, MRNA, KOD, LQDA, ALMS); event filter: 2807 US names with a vendor-announced print 2026-10-13..2026-11-12 in calendar_2026-09-29.parquet.
Refused: CTVA -- REFUSED_JUMP_X2 (one-day move x6.2 inside 63 sessions: split / spin / stitch / bad print)
Refused: CAPR -- REFUSED_JUMP_X2 (one-day move x2.8 inside 63 sessions: split / spin / stitch / bad print)
Refused: MRNA -- REFUSED_JUMP_X2 (one-day move x2.8 inside 63 sessions: split / spin / stitch / bad print)
Refused: KOD -- REFUSED_JUMP_X2 (one-day move x2.8 inside 63 sessions: split / spin / stitch / bad print)
Refused: LQDA -- REFUSED_JUMP_X2 (one-day move x2.3 inside 63 sessions: split / spin / stitch / bad print)
Refused: ALMS -- REFUSED_JUMP_X2 (one-day move x2.3 inside 63 sessions: split / spin / stitch / bad print)
Reserves: RARE US Equity, CIFR US Equity, AAOI US Equity, MXL US Equity, IOVA US Equity, CDNL US Equity, UMAC US Equity, AMLX US Equity

NAV used for sizing: $1,000,000. Position budget: $200,000 (20% of notional; the other reading allows $200,000). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (0)

- none

## BUY (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **AXTI US Equity** | BUY | **2,266** | LIMIT | 88.26 | USD | 199,997 | Wed 07 Oct 21:30 / Wed 09:30 | W9 | LIVE; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 2 | **AVBP US Equity** | BUY | **12,626** | LIMIT | 15.84 | USD | 199,996 | Wed 07 Oct 21:30 / Wed 09:30 | H4 | LIVE; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 3 | **RXT US Equity** | BUY | **47,382** | LIMIT | 4.221 | USD | 199,999 | Wed 07 Oct 21:30 / Wed 09:30 | FC | LIVE; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 4 | **UTZ US Equity** | BUY | **13,351** | LIMIT | 14.98 | USD | 199,998 | Wed 07 Oct 21:30 / Wed 09:30 | 4E | LIVE; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |
| 5 | **QMCO US Equity** | BUY | **5,691** | LIMIT | 35.14 | USD | 199,982 | Wed 07 Oct 21:30 / Wed 09:30 | VC | LIVE; report n/a BUY_AND_HOLD, sell at the 2026-10-12 open; CONFIRMED; lot 1 |

## CONTROL (check on the blotter after entering)

- lines: **5** (0 SELL, 5 BUY)
- total SELL shares: **0**; total BUY shares: **81,316**
- total BUY notional at the limits: **$999,972** (never above $1,000,000)
- SHEET CODE: **0340E65E**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-07 --entered <file>`: it must print the same code.

