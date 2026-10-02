# Contest sheet 2026-09-29 (sessions opening Tue 29 Sep 14:00 to Wed 30 Sep 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-09-29.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-28 (1 days); EU: last bar 2026-09-28 (1 days); HK: last bar 2026-09-28 (1 days); ID: last bar 2026-09-28 (1 days); IN: last bar 2026-09-28 (1 days); JP: last bar 2026-09-28 (1 days); KR: last bar 2026-09-23 (6 days) STALE; TW: last bar 2026-09-24 (5 days) STALE; US: last bar 2026-09-28 (1 days)

## 1. SELL (names whose report has happened)

- nothing held from the previous sheet (or first day)

## 2. BUY: 5 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CNXC US Equity | Concentrix Corporation | US | Tue 21:30 | Tue 29 Sep 16:05 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 14.7% over 8 | 4.9% | 5.8% | $34M OK | UNCONFIRMED_MEMBERSHIP | 20.9% |
| 2 | AIR US Equity | AAR Corp. | US | Tue 21:30 | Tue 29 Sep 16:05 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 8.6% over 8 | 3.1% | 4.8% | $47M OK | UNCONFIRMED_MEMBERSHIP | 12.8% |
| 3 | FDS US Equity | FactSet Research Systems Inc | US | Tue 21:30 | Wed 30 Sep 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 5.6% over 8 | 3.0% | 4.4% | $218M OK | UNCONFIRMED_MEMBERSHIP | 10.2% |
| 4 | JBL US Equity | Jabil Inc. | US | Tue 21:30 | Wed 30 Sep 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 5.1% over 8 | 3.2% | 4.2% | $325M OK | UNCONFIRMED_MEMBERSHIP | 9.6% |
| 5 | CALM US Equity | Cal-Maine Foods, Inc. | US | Tue 21:30 | Wed 30 Sep 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 3.5% over 8 | 2.1% | 3.0% | $67M OK | UNCONFIRMED_MEMBERSHIP | 8.8% |

## 3. If a name is not in the index or not tradable: take the next in rank

- #6 GIS US Equity (US, avg move 3.4%, UNCONFIRMED_MEMBERSHIP)
- #7 CAG US Equity (US, avg move 3.2%, UNCONFIRMED_MEMBERSHIP)

Refused by name:

- 000823.SZ: REFUSED_HISTORY (< 3 past reactions)
- 000960.SZ: REFUSED_HISTORY (< 3 past reactions)
- 0017.HK: REFUSED_ILLIQUID (median $vol < $10M)
- 002155.SZ: REFUSED_HISTORY (< 3 past reactions)
- 1CAG.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 1CALM.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 1FDS.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 1JBL.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 2685.T: REFUSED_ILLIQUID (median $vol < $10M)
- 600410.SS: REFUSED_HISTORY (< 3 past reactions)
- 600549.SS: REFUSED_HISTORY (< 3 past reactions)
- 7447.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7545.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7915.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8276.T: REFUSED_ILLIQUID (median $vol < $10M)
- ASY.PA: REFUSED_ILLIQUID (median $vol < $10M)
- BAG.L: REFUSED_ILLIQUID (median $vol < $10M)
- CARD.L: REFUSED_ILLIQUID (median $vol < $10M)
- CBG.L: REFUSED_ILLIQUID (median $vol < $10M)
- GNFT.PA: REFUSED_ILLIQUID (median $vol < $10M)
- HBH.DE: REFUSED_ILLIQUID (median $vol < $10M)
- HTT: REFUSED_ILLIQUID (median $vol < $10M)
- NIOX.L: REFUSED_ILLIQUID (median $vol < $10M)
- SA: REFUSED_HISTORY (< 3 past reactions)
- SPI.L: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| CNXC | n/a | 0.492 | 0.091 |
| AIR | n/a | 0.510 | -0.251 |
| FDS | n/a | 0.511 | -0.029 |
| JBL | n/a | 0.513 | -0.138 |
| CALM | n/a | 0.515 | -0.163 |

Note: NN size-of-move column: size_2026-09-28.parquet (US names only; size of a 5-session excess move, not direction; display only).
