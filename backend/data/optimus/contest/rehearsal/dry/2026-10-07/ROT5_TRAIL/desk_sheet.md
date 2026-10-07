# Contest sheet 2026-10-07 (sessions opening Wed 07 Oct 14:00 to Thu 08 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-10-06.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-30 (7 days) STALE; EU: last bar 2026-10-05 (2 days); HK: last bar 2026-10-05 (2 days); ID: last bar 2026-10-05 (2 days); IN: last bar 2026-10-05 (2 days); JP: last bar 2026-10-05 (2 days); KR: last bar 2026-10-02 (5 days) STALE; TW: last bar 2026-10-05 (2 days); US: last bar 2026-10-05 (2 days)

## 1. SELL (names whose report has happened)

- SELL **3391 JT Equity** (3391.T) at its next session (2026-10-08)

## 2. BUY: 5 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 6323 JT Equity | Rorze Corporation | JP | Thu 08:00 | Thu 08 Oct 15:35 local, AMC | CONFIRMED | 4.2% over 8 | 5.2% | n/a | $46M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 2 | 9983 JT Equity | Fast Retailing Co., Ltd. | JP | Thu 08:00 | Thu 08 Oct 15:35 local, AMC | CONFIRMED | 3.4% over 8 | 1.9% | n/a | $512M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 3 | 2809 JT Equity | Kewpie Corporation | JP | Thu 08:00 | Thu 08 Oct 15:35 local, AMC | CONFIRMED | 2.8% over 8 | 1.6% | n/a | $10M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 4 | 7649 JT Equity | Sugi Holdings Co.,Ltd. | JP | Thu 08:00 | Thu 08 Oct 15:35 local, AMC | CONFIRMED | 2.3% over 8 | 2.1% | n/a | $18M OK | UNCONFIRMED_MEMBERSHIP | n/a |
| 5 | 3382 JT Equity | Seven & i Holdings Co., Ltd. | JP | Thu 08:00 | Thu 08 Oct 15:35 local, AMC | CONFIRMED | 2.1% over 8 | 1.6% | n/a | $104M OK | UNCONFIRMED_MEMBERSHIP | n/a |

## 3. If a name is not in the index or not tradable: take the next in rank

- no reserve name in this window

Refused by name:

- 002222.SZ: REFUSED_HISTORY (< 3 past reactions)
- 0QOS.L: REFUSED_ILLIQUID (median $vol < $10M)
- 2157.T: REFUSED_ILLIQUID (median $vol < $10M)
- 2698.T: REFUSED_ILLIQUID (median $vol < $10M)
- 3201.T: REFUSED_ILLIQUID (median $vol < $10M)
- 4187.T: REFUSED_ILLIQUID (median $vol < $10M)
- 4992.T: REFUSED_ILLIQUID (median $vol < $10M)
- 5982.T: REFUSED_ILLIQUID (median $vol < $10M)
- 600141.SS: REFUSED_HISTORY (< 3 past reactions)
- 6005.TW: REFUSED_ILLIQUID (median $vol < $10M)
- 600536.SS: REFUSED_HISTORY (< 3 past reactions)
- 6264.T: REFUSED_ILLIQUID (median $vol < $10M)
- 6289.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8200.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8244.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8278.T: REFUSED_ILLIQUID (median $vol < $10M)
- 9381.T: REFUSED_ILLIQUID (median $vol < $10M)
- 9861.T: REFUSED_HISTORY (< 3 past reactions)
- ANANDRATHI.NS: REFUSED_ILLIQUID (median $vol < $10M)
- INDIANB.BO: REFUSED_ILLIQUID (median $vol < $10M)
- INDIANB.NS: REFUSED_ILLIQUID (median $vol < $10M)
- TCS.BO: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| 6323.T | n/a | n/a | 0.146 |
| 9983.T | n/a | n/a | 0.033 |
| 2809.T | n/a | n/a | -0.089 |
| 7649.T | n/a | n/a | -0.085 |
| 3382.T | n/a | n/a | -0.025 |

Note: NN size-of-move column: size_2026-10-05.parquet (US names only; size of a 5-session excess move, not direction; display only).
