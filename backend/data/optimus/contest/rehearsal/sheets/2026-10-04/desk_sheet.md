# Contest sheet 2026-10-04 (sessions opening Sun 04 Oct 14:00 to Mon 05 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-10-04.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-30 (4 days); EU: last bar 2026-10-02 (2 days); HK: last bar 2026-10-02 (2 days); ID: last bar 2026-10-01 (3 days); IN: last bar 2026-10-01 (3 days); JP: last bar 2026-10-02 (2 days); KR: last bar 2026-10-02 (2 days); TW: last bar 2026-10-02 (2 days); US: last bar 2026-10-02 (2 days)

## 1. SELL (names whose report has happened)

- nothing held from the previous sheet (or first day)

## 2. BUY: 1 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3186 JT Equity | NEXTAGE Co., Ltd. | JP | Mon 08:00 | Mon 05 Oct 15:35 local, AMC | CONFIRMED | 5.7% over 8 | 2.5% | n/a | $11M OK | UNCONFIRMED_MEMBERSHIP | n/a |

## 3. If a name is not in the index or not tradable: take the next in rank

- no reserve name in this window

Refused by name:

- 2734.T: REFUSED_ILLIQUID (median $vol < $10M)
- 5243.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7630.T: REFUSED_ILLIQUID (median $vol < $10M)
- 9793.T: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| 3186.T | n/a | n/a | -0.193 |

Note: NN size-of-move column: size_2026-09-28.parquet (US names only; size of a 5-session excess move, not direction; display only).
