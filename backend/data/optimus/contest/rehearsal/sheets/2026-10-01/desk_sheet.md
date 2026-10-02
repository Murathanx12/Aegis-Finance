# Contest sheet 2026-10-01 (sessions opening Thu 01 Oct 14:00 to Fri 02 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-10-01.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-30 (1 days); EU: last bar 2026-09-30 (1 days); HK: last bar 2026-09-30 (1 days); ID: last bar 2026-09-30 (1 days); IN: last bar 2026-09-30 (1 days); JP: last bar 2026-09-30 (1 days); KR: last bar 2026-09-23 (8 days) STALE; TW: last bar 2026-09-30 (1 days); US: last bar 2026-09-30 (1 days)

## 1. SELL (names whose report has happened)

- SELL **PRGS US Equity** (PRGS) at its next session (2026-10-01)
- SELL **MU US Equity** (MU) at its next session (2026-10-01)
- SELL **AYI US Equity** (AYI) at its next session (2026-10-01)
- SELL **ACN US Equity** (ACN) at its next session (2026-10-01)
- SELL **4088 JT Equity** (4088.T) at its next session (2026-10-05)

## 2. BUY: 1 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | NKE US Equity | NIKE, Inc. | US | Thu 21:30 | Thu 01 Oct 16:05 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 7.4% over 8 | 1.8% | 3.5% | $953M OK | UNCONFIRMED_MEMBERSHIP | 8.7% |

## 3. If a name is not in the index or not tradable: take the next in rank

- no reserve name in this window

Refused by name:

- 0QZ6.L: REFUSED_ILLIQUID (median $vol < $10M)
- 1NKE.MI: REFUSED_ILLIQUID (median $vol < $10M)
- 3148.T: REFUSED_ILLIQUID (median $vol < $10M)
- 3612.T: REFUSED_ILLIQUID (median $vol < $10M)
- 6474.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7965.T: REFUSED_ILLIQUID (median $vol < $10M)
- 8923.T: REFUSED_ILLIQUID (median $vol < $10M)
- BC94.L: REFUSED_HISTORY (< 3 past reactions)
- NKE.DE: REFUSED_ILLIQUID (median $vol < $10M)
- TMQ: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| NKE | n/a | 0.508 | -0.129 |

Note: NN size-of-move column: size_2026-09-28.parquet (US names only; size of a 5-session excess move, not direction; display only).
