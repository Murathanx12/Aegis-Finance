# Contest sheet 2026-10-05 (sessions opening Mon 05 Oct 14:00 to Tue 06 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-10-05.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-30 (5 days) STALE; EU: last bar 2026-10-02 (3 days); HK: last bar 2026-10-02 (3 days); ID: last bar 2026-10-01 (4 days); IN: last bar 2026-10-01 (4 days); JP: last bar 2026-10-02 (3 days); KR: last bar 2026-10-02 (3 days); TW: last bar 2026-10-02 (3 days); US: last bar 2026-10-02 (3 days)

## 1. SELL (names whose report has happened)

- SELL **3186 JT Equity** (3186.T) at its next session (2026-10-06)

## 2. BUY: 3 name(s) at 20% each, in Hong Kong opening order

| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status | why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) | WLS membership | implied move |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AEHR US Equity | Aehr Test Systems, Inc. | US | Mon 21:30 | Mon 05 Oct 16:05 local, AMC | NOT CONFIRMED (VENDOR_ANNOUNCED) | 21.2% over 8 | 8.4% | 6.5% | $208M OK | UNCONFIRMED_MEMBERSHIP | 10.9% |
| 2 | LW US Equity | Lamb Weston Holdings, Inc. | US | Mon 21:30 | Tue 06 Oct 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 11.1% over 8 | 2.0% | 3.6% | $70M OK | UNCONFIRMED_MEMBERSHIP | 10.1% |
| 3 | RPM US Equity | RPM International Inc. | US | Mon 21:30 | Tue 06 Oct 07:00 local, BMO | NOT CONFIRMED (VENDOR_ANNOUNCED) | 5.7% over 8 | 1.9% | 2.2% | $101M OK | UNCONFIRMED_MEMBERSHIP | 6.4% |

## 3. If a name is not in the index or not tradable: take the next in rank

- no reserve name in this window

Refused by name:

- 1066.HK: REFUSED_ILLIQUID (median $vol < $10M)
- 1070.HK: REFUSED_HISTORY (< 3 past reactions)
- 1377.T: REFUSED_ILLIQUID (median $vol < $10M)
- 1866.HK: REFUSED_ILLIQUID (median $vol < $10M)
- 2659.T: REFUSED_ILLIQUID (median $vol < $10M)
- 2726.T: REFUSED_ILLIQUID (median $vol < $10M)
- 2918.T: REFUSED_ILLIQUID (median $vol < $10M)
- 7337.T: REFUSED_ILLIQUID (median $vol < $10M)
- APOG: REFUSED_ILLIQUID (median $vol < $10M)
- BZU.MI: REFUSED_HISTORY (< 3 past reactions)
- EMG.L: REFUSED_HISTORY (< 3 past reactions)
- GFC.PA: REFUSED_HISTORY (< 3 past reactions)
- VLGEA: REFUSED_ILLIQUID (median $vol < $10M)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).

## 5. Experimental columns (UNTESTED; they did not affect the ranking)

| ticker | revision30_EXPERIMENTAL | nn_prob_EXPERIMENTAL | drift20_EXPERIMENTAL |
|---|---|---|---|
| AEHR | n/a | 0.435 | 0.054 |
| LW | n/a | 0.506 | -0.188 |
| RPM | n/a | 0.505 | -0.087 |

Note: NN size-of-move column: size_2026-09-28.parquet (US names only; size of a 5-session excess move, not direction; display only).
