# Contest sheet 2026-10-02 (sessions opening Fri 02 Oct 14:00 to Sat 03 Oct 14:00 HKT)

*PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Never evidence of skill.* Zero directional skill is assumed: this rule sells variance for rank.
Every name here is as likely to fall as to rise; the rule picks names that MOVE.

Calendar: calendar_2026-10-02.parquet; universe membership: PROXY (unconfirmed).  Bars: CN: last bar 2026-09-30 (2 days); EU: last bar 2026-10-01 (1 days); HK: last bar 2026-09-30 (2 days); ID: last bar 2026-10-01 (1 days); IN: last bar 2026-10-01 (1 days); JP: last bar 2026-10-01 (1 days); KR: last bar 2026-09-23 (9 days) STALE; TW: last bar 2026-10-01 (1 days); US: last bar 2026-10-01 (1 days)

## 1. SELL (names whose report has happened)

- SELL **NKE US Equity** (NKE) at its next session (2026-10-02)

## 2. BUY: 0 name(s) at 20% each, in Hong Kong opening order

- none eligible. Leave cash, or buy the filler list in section 3.

## 3. If a name is not in the index or not tradable: take the next in rank

- no reserve name in this window

Refused by name:

- 2GB.DE: REFUSED_ILLIQUID (median $vol < $10M)
- AIV: REFUSED_ILLIQUID (median $vol < $10M)
- CHRN: REFUSED_ILLIQUID (median $vol < $10M)
- CURR: REFUSED_ILLIQUID (median $vol < $10M)
- GRFS: REFUSED_ILLIQUID (median $vol < $10M)
- JDW.L: REFUSED_ILLIQUID (median $vol < $10M)
- LONN.SW: REFUSED_HISTORY (< 3 past reactions)

## 4. Three checks on the Terminal before entering

1. `EVTS` / `ERN` on each name: the report date and time match the column above (a NOT CONFIRMED date that moved means skip it and take the next in rank).
2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.
3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).


Note: NN size-of-move column: size_2026-09-28.parquet (US names only; size of a 5-session excess move, not direction; display only).
