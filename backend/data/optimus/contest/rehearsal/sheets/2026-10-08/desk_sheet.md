# Contest sheet 2026-10-08 (sessions opening Thu 08 Oct 14:00 to Fri 09 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-10-08.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-30 (8 days) STALE; EU: last bar 2026-10-07 (1 days); HK: last bar 2026-10-07 (1 days); ID: last bar 2026-10-07 (1 days); IN: last bar 2026-10-07 (1 days); JP: last bar 2026-10-07 (1 days); KR: last bar 2026-10-07 (1 days); TW: last bar 2026-10-07 (1 days); US: last bar 2026-10-07 (1 days)

## 1. SELL (names whose report has happened)

- SELL **6323 JT Equity** (6323.T) at its next session (2026-10-09)
- SELL **9983 JT Equity** (9983.T) at its next session (2026-10-09)
- SELL **2809 JT Equity** (2809.T) at its next session (2026-10-09)
- SELL **7649 JT Equity** (7649.T) at its next session (2026-10-09)
- SELL **3382 JT Equity** (3382.T) at its next session (2026-10-09)

## 2. BUY: 5 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3046 JT Equity | JINS HOLDINGS Inc. | JP | Fri 08:00 | Fri 09 Oct 15:35 local, AMC | CONFIRMED | 12.6% over 8 | 3.8% | n/a | $12M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 2 | 6814 JT Equity | Furuno Electric Co., Ltd. | JP | Fri 08:00 | Fri 09 Oct 15:35 local, AMC | CONFIRMED | 10.8% over 8 | 3.5% | n/a | $15M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 3 | 6506 JT Equity | YASKAWA Electric Corporation | JP | Fri 08:00 | Fri 09 Oct 15:35 local, AMC | CONFIRMED | 9.5% over 8 | 3.8% | n/a | $135M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 5 | 4443 JT Equity | Sansan, Inc. | JP | Fri 08:00 | Fri 09 Oct 15:35 local, AMC | CONFIRMED | 2.8% over 8 | 3.4% | n/a | $16M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 4 | DMART IN Equity | Avenue Supermarts Limited | IN | Fri 11:45 | Sat 10 Oct 15:35 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 3.2% over 8 | 1.5% | n/a | $16M OK | UNCONFIRMED_MEMBERSHIP | n/a |

## 3. If a name is not in the index or not tradable: take the next in rank

- no reserve name in this window

Refused by name:

- 002149.SZ: REFUSED_HISTORY (< 3 past reactions)
- 002167.SZ: REFUSED_HISTORY (< 3 past reactions)
- 002364.SZ: REFUSED_HISTORY (< 3 past reactions)
- 1171.HK: REFUSED_HISTORY (< 3 past reactions)
- 1308.HK: REFUSED_HISTORY (< 3 past reactions)
- 1419.T: REFUSED_ILLIQUID (median $vol < $10M)
- 2653.T: REFUSED_ILLIQUID (median $vol < $10M)
- 2791.T: REFUSED_ILLIQUID (median $vol < $10M)
- 300418.SZ: REFUSED_HISTORY (< 3 past reactions)
- 3048.T: REFUSED_ILLIQUID (median $vol < $10M)
- 3087.T: REFUSED_ILLIQUID (median $vol < $10M)
- 3222.T: REFUSED_ILLIQUID (median $vol < $10M)
- 4343.T: REFUSED_ILLIQUID (median $vol < $10M)
- 575A.T: REFUSED_ILLIQUID (median $vol < $10M)
- 5832.T: REFUSED_ILLIQUID (median $vol < $10M)
- 600096.SS: REFUSED_HISTORY (< 3 past reactions)
- 600160.SS: REFUSED_HISTORY (< 3 past reactions)
- 600360.SS: REFUSED_HISTORY (< 3 past reactions)
- 6136.T: REFUSED_ILLIQUID (median $vol < $10M)
- 6627.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7085.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7512.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7516.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8198.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8570.T: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| 3046.T | n/a | n/a | -0.077 |
| 6814.T | n/a | n/a | 0.098 |
| 6506.T | n/a | n/a | 0.005 |
| DMART.NS | n/a | n/a | -0.078 |
| 4443.T | n/a | n/a | 0.021 |

Note: NN size-of-move column: size_2026-10-06.parquet (US names only; size of a 5-session excess move, not direction; display only).
