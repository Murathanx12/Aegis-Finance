# Contest sheet 2026-09-30 (sessions opening Wed 30 Sep 14:00 to Thu 01 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-09-30.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-28 (2 days); EU: last bar 2026-09-28 (2 days); HK: last bar 2026-09-28 (2 days); ID: last bar 2026-09-28 (2 days); IN: last bar 2026-09-28 (2 days); JP: last bar 2026-09-28 (2 days); KR: last bar 2026-09-23 (7 days) STALE; TW: last bar 2026-09-24 (6 days) STALE; US: last bar 2026-09-28 (2 days)

## 1. SELL (names whose report has happened)

- nothing held from the previous sheet (or first day)

## 2. BUY: 5 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | PRGS US Equity | Progress Software Corporatio | US | Wed 21:30 | Wed 30 Sep 16:05 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 9.7% over 8 | 3.2% | 4.8% | $19M OK | UNCONFIRMED_MEMBERSHIP | 12.0% |
| 2 | MU US Equity | Micron Technology, Inc. | US | Wed 21:30 | Wed 30 Sep 16:05 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 9.1% over 8 | 4.9% | 4.6% | $31,072M OK | UNCONFIRMED_MEMBERSHIP | 7.7% |
| 3 | AYI US Equity | Acuity Inc. | US | Wed 21:30 | Thu 01 Oct 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 8.1% over 8 | 2.0% | 3.3% | $92M OK | UNCONFIRMED_MEMBERSHIP | 9.5% |
| 4 | ACN US Equity | Accenture plc | US | Wed 21:30 | Thu 01 Oct 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 6.6% over 8 | 2.9% | 4.6% | $959M OK | UNCONFIRMED_MEMBERSHIP | 8.1% |
| 5 | 4088 JT Equity | Air Water Inc. | JP | Thu 08:00 | Fri 02 Oct 00:00 local, UNKNOWN | NOT CONFIRMED (VENDOR_ESTIMATE) | 5.6% over 3 | 2.1% | n/a | $15M OK | UNCONFIRMED_MEMBERSHIP | n/a |

## 3. If a name is not in the index or not tradable: take the next in rank

- #6 HUBG US Equity (US, avg move 5.0%, UNCONFIRMED_MEMBERSHIP)
- #7 FIZZ US Equity (US, avg move 3.9%, UNCONFIRMED_MEMBERSHIP)
- #8 MKC US Equity (US, avg move 3.7%, UNCONFIRMED_MEMBERSHIP)

Refused by name:

- 1ACN.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 1MKC.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 1MU.MI: REFUSED_HISTORY (< 3 past reactions)
- 2531.T: REFUSED_ILLIQUID (median $vol < $10M)
- 3549.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7611.T: REFUSED_ILLIQUID (median $vol < $10M)
- ANGO: REFUSED_ILLIQUID (median $vol < $10M)
- KOF.PA: REFUSED_ILLIQUID (median $vol < $10M)
- MTE.DE: REFUSED_HISTORY (< 3 past reactions)
- MU.SW: REFUSED_ILLIQUID (median $vol < $10M)
- SAGA.L: REFUSED_ILLIQUID (median $vol < $10M)
- SKIS-B.ST: REFUSED_ILLIQUID (median $vol < $10M)
- VFS: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| PRGS | n/a | 0.509 | -0.080 |
| MU | n/a | 0.512 | 0.042 |
| AYI | n/a | 0.511 | -0.151 |
| ACN | n/a | 0.500 | 0.026 |
| 4088.T | n/a | n/a | 0.118 |

Note: NN size-of-move column: size_2026-09-28.parquet (US names only; size of a 5-session excess move, not direction; display only).
