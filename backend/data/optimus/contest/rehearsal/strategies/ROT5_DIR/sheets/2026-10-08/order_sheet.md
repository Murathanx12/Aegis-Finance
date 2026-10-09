# SHADOW SHEET ROT5_DIR 2026-10-08  (frozen 2026-10-08T06:33:15 UTC)

SHADOW BOOK **ROT5_DIR** (REHEARSAL; paper; never entered; graded beside ROT5_TRAIL by the same grader). Contract 298ee42706e4a2a6 (PRODUCT_EXPERIMENT). Window Thu 08 Oct 14:00 to Fri 09 Oct 14:00 HKT.
**WORST CASE (ROT5_DIR)** largest admissible book 5 x $200,000 = $1,000,000, sum|notional|/equity 1.00: loss at 5% stop $50,000; 10% stop $100,000; at a 2-sigma63 move $76,884 (the largest sigma63 among this sheet's book names).
This sheet's book after its tickets: 5 name(s), $991,511 gross = 0.99 of equity; loss at 5% stop $49,576; 10% stop $99,151; at 2-sigma63 $63,440; at 2x the trailing |earnings move| $153,966. No book here carries a stop (ROT5 exits at the open after the print; MAXTAIL holds) and a gap fills through any stop: the stop rows are reference arithmetic, not a bound.
DRIFT: the 20% cap is enforced AT ENTRY. Whether it also applies at all times is NOT settled by the public rules (OWNER-ONLY item 4); if it does, sell the trim below at the next open. No position is held through this sheet.
Direction source: target_revisions.parquet sha256 6acad2a20a43a53a (395326 rows; first-seen basis: first_seen_utc (min over pulls; pulled_at where missing)); last pull 2026-10-07 14:18:32+00:00 (0.68 days old); 0 rows first seen after the freeze excluded; of 5 ROT5_TRAIL names: 0 admitted, 5 unrated (admitted, no evidence), 0 dropped.

NAV used for sizing: $1,000,000. Position budget: $200,000 (20% of notional; the other reading allows $200,000). Buy limits are 5% above the last close so the notional AT THE LIMIT stays under the cap.

Type EXACTLY what is in the TICKER, SIDE and SHARES columns. If the Terminal's notional on a BUY ticket is above $200,000, the quantity is wrong: stop and re-read the line.

## SELL (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **6323 JT Equity** | SELL | **6,600** | MARKET AT OPEN |  | JPY | 0 | Fri 09 Oct 08:00 / Thu 20:00 | DF | LIVE; report has happened by this open |
| 2 | **9983 JT Equity** | SELL | **300** | MARKET AT OPEN |  | JPY | 0 | Fri 09 Oct 08:00 / Thu 20:00 | UK | LIVE; report has happened by this open |
| 3 | **2809 JT Equity** | SELL | **6,900** | MARKET AT OPEN |  | JPY | 0 | Fri 09 Oct 08:00 / Thu 20:00 | P9 | LIVE; report has happened by this open |
| 4 | **7649 JT Equity** | SELL | **24,500** | MARKET AT OPEN |  | JPY | 0 | Fri 09 Oct 08:00 / Thu 20:00 | FT | LIVE; report has happened by this open |
| 5 | **3382 JT Equity** | SELL | **15,200** | MARKET AT OPEN |  | JPY | 0 | Fri 09 Oct 08:00 / Thu 20:00 | FN | LIVE; report has happened by this open |

## BUY (5)

| # | TICKER (type this) | SIDE | SHARES | type | limit | ccy | notional USD | session (HKT / New York) | code | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 6 | **3046 JT Equity** | BUY | **5,300** | LIMIT | 5,954.0 | JPY | 199,349 | Fri 09 Oct 08:00 / Thu 20:00 | 7F | LIVE; report 2026-10-09 AMC, sell at the 2026-10-13 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 7 | **6814 JT Equity** | BUY | **3,500** | LIMIT | 8,852.0 | JPY | 195,722 | Fri 09 Oct 08:00 / Thu 20:00 | AV | LIVE; report 2026-10-09 AMC, sell at the 2026-10-13 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 8 | **6506 JT Equity** | BUY | **6,000** | LIMIT | 5,193.0 | JPY | 196,834 | Fri 09 Oct 08:00 / Thu 20:00 | WC | LIVE; report 2026-10-09 AMC, sell at the 2026-10-13 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 10 | **4443 JT Equity** | BUY | **14,100** | LIMIT | 2,241.0 | JPY | 199,614 | Fri 09 Oct 08:00 / Thu 20:00 | ER | LIVE; report 2026-10-09 AMC, sell at the 2026-10-13 open; CONFIRMED; lot 100 (UNVERIFIED) |
| 9 | **DMART IN Equity** | BUY | **5,048** | LIMIT | 3,818.0 | INR | 199,992 | Fri 09 Oct 11:45 / Thu 23:45 | 7F | LIVE; report 2026-10-10 AMC, sell at the 2026-10-12 open; NOT CONFIRMED (VENDOR_ANNOUNCED); lot 1 |

## CONTROL (check on the blotter after entering)

- lines: **10** (5 SELL, 5 BUY)
- total SELL shares: **53,500**; total BUY shares: **33,948**
- total BUY notional at the limits: **$991,511** (never above $1,000,000)
- SHEET CODE: **2F4F9FD1**. Paste the blotter into `python -m scripts.contest_rehearsal verify --date 2026-10-08 --entered <file>`: it must print the same code.

