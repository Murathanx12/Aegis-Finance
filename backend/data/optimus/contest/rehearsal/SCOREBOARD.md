# Contest rehearsal scoreboard (derived view; the receipts are grades/grade_*.json and strategies/<book>/grades/grade_*.json)

Graded 20261008T063007Z UTC; price source: yfinance; benchmark ACWI opens (WLS proxy). Every book is frozen at the same time by the same task and graded here by the same code.

## Books side by side

| book | closed / open | realised P&L $ (0 bps) | unrealised $ (mark) | relative 0 / 10 / 25 bps | hit rate vs bench | TAIL: top name share | relative without top name | worst case (latest sheet) |
|---|---|---|---|---|---|---|---|---|
| ROT5_TRAIL | 10 / 1 | +12,782 | -446 | +0.08% / -0.30% / -0.88% | 30% (40% abs) | ACN US Equity (2026-09-30) 323% of net; best 68% of gains | -4.05% | 2026-10-07: 5x$200,000; 5% stop $50,000, 10% stop $100,000; 2σ63 $101,557 |
| ROT5_DIR | 0 / 0 | +0 | +0 | n/a / n/a / n/a | n/a (n/a abs) | n/a n/a of net; best n/a of gains | n/a | 2026-10-07: 5x$200,000; 5% stop $50,000, 10% stop $100,000; 2σ63 $101,557 |
| MAXTAIL_BH | 0 / 5 | +0 | +14,615 | n/a / n/a / n/a | n/a (n/a abs) | n/a n/a of net; best n/a of gains | n/a | 2026-10-07: 5x$200,000; 5% stop $50,000, 10% stop $100,000; 2σ63 $190,560 |
| MAXTAIL_EVT | 0 / 5 | +0 | +8,523 | n/a / n/a / n/a | n/a (n/a abs) | n/a n/a of net; best n/a of gains | n/a | 2026-10-07: 5x$200,000; 5% stop $50,000, 10% stop $100,000; 2σ63 $190,560 |
| ROT5_TRAIL on ROT5_DIR's sheets (from 2026-10-07) | 0 / 0 | +0 | +0 | n/a / n/a / n/a | n/a (n/a abs) | n/a n/a of net; best n/a of gains | n/a | n/a |
| ROT5_TRAIL on MAXTAIL_BH's sheets (from 2026-10-07) | 0 / 0 | +0 | +0 | n/a / n/a / n/a | n/a (n/a abs) | n/a n/a of net; best n/a of gains | n/a | n/a |
| ROT5_TRAIL on MAXTAIL_EVT's sheets (from 2026-10-07) | 0 / 0 | +0 | +0 | n/a / n/a / n/a | n/a (n/a abs) | n/a n/a of net; best n/a of gains | n/a | n/a |

Read the same-sheets line, not the full ROT5_TRAIL line, when comparing: the shadow books start later. A handful of positions decides nothing; the TAIL column says how much one name carries.

## ROT5_TRAIL

- positions: 16 ({'CLOSED': 10, 'PENDING_ENTRY': 5, 'OPEN': 1})
- book P&L at 0 bps: $12,782; NAV $1,012,782
- relative vs ACWI: 0 bps 0.00084, 10 bps -0.003, 25 bps -0.008758 over ['2026-09-30', '2026-10-06']

| sheet | ticker | qty | entry | exit | state | ret (local) | P&L USD | bench | note |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-30 | PRGS US Equity | 4,833 | 2026-09-30 39.439998626708984 | 2026-10-01 40.52000045776367 | CLOSED | +2.74% | +5,220 | -0.64% |  |
| 2026-09-30 | MU US Equity | 180 | 2026-09-30 1076.760009765625 | 2026-10-01 1054.0799560546875 | CLOSED | -2.11% | -4,082 | -0.64% |  |
| 2026-09-30 | AYI US Equity | 622 | 2026-09-30 309.9700012207031 | 2026-10-01 306.44000244140625 | CLOSED | -1.14% | -2,196 | -0.64% |  |
| 2026-09-30 | ACN US Equity | 1,091 | 2026-09-30 178.10000610351562 | 2026-10-01 215.97999572753906 | CLOSED | +21.27% | +41,327 | -0.64% |  |
| 2026-09-30 | 4088 JT Equity | 10,600 | 2026-10-01 2882.0 | 2026-10-05 2865.0 | CLOSED | -0.59% | -1,359 | +0.75% |  |
| 2026-10-01 | NKE US Equity | 5,380 | 2026-10-01 35.45000076293945 | 2026-10-02 32.54999923706055 | CLOSED | -8.18% | -15,602 | +0.77% |  |
| 2026-10-04 | 3186 JT Equity | 10,600 | 2026-10-05 2838.0 | 2026-10-06 2556.0 | CLOSED | -9.94% | -19,200 | +1.09% |  |
| 2026-10-05 | AEHR US Equity | 1,776 | 2026-10-05 107.31999969482422 | 2026-10-06 107.62999725341797 | CLOSED | +0.29% | +551 | +1.09% |  |
| 2026-10-05 | LW US Equity | 4,368 | 2026-10-05 43.900001525878906 | 2026-10-06 47.029998779296875 | CLOSED | +7.13% | +13,672 | +1.09% |  |
| 2026-10-05 | RPM US Equity | 1,920 | 2026-10-05 99.13999938964844 | 2026-10-06 96.25 | CLOSED | -2.92% | -5,549 | +1.09% |  |
| 2026-10-06 | 3391 JT Equity | 14,100 | 2026-10-07 2144.5 |   | OPEN |  |  |  | mark 2026-10-08 -446 |
| 2026-10-07 | 6323 JT Equity | 6,600 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 9983 JT Equity | 300 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 2809 JT Equity | 6,900 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 7649 JT Equity | 24,500 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 3382 JT Equity | 15,200 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |

## ROT5_DIR

- positions: 5 ({'PENDING_ENTRY': 5})
- book P&L at 0 bps: $0; NAV $1,000,000
- relative vs ACWI: 0 bps n/a, 10 bps n/a, 25 bps n/a over n/a

| sheet | ticker | qty | entry | exit | state | ret (local) | P&L USD | bench | note |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-07 | 6323 JT Equity | 6,600 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 9983 JT Equity | 300 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 2809 JT Equity | 6,900 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 7649 JT Equity | 24,500 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |
| 2026-10-07 | 3382 JT Equity | 15,200 | 2026-10-08  |   | PENDING_ENTRY |  |  |  |  |

## MAXTAIL_BH

- positions: 5 ({'OPEN': 5})
- book P&L at 0 bps: $0; NAV $1,000,000
- relative vs ACWI: 0 bps n/a, 10 bps n/a, 25 bps n/a over n/a

| sheet | ticker | qty | entry | exit | state | ret (local) | P&L USD | bench | note |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-07 | AXTI US Equity | 2,266 | 2026-10-07 79.77999877929688 |   | OPEN |  |  |  | mark 2026-10-07 +23 |
| 2026-10-07 | AVBP US Equity | 12,626 | 2026-10-07 15.244999885559082 |   | OPEN |  |  |  | mark 2026-10-07 +20,770 |
| 2026-10-07 | AEHR US Equity | 2,067 | 2026-10-07 90.36000061035156 |   | OPEN |  |  |  | mark 2026-10-07 -2,046 |
| 2026-10-07 | RXT US Equity | 47,382 | 2026-10-07 3.940000057220459 |   | OPEN |  |  |  | mark 2026-10-07 -4,264 |
| 2026-10-07 | UTZ US Equity | 13,351 | 2026-10-07 14.279999732971191 |   | OPEN |  |  |  | mark 2026-10-07 +134 |

## MAXTAIL_EVT

- positions: 5 ({'OPEN': 5})
- book P&L at 0 bps: $0; NAV $1,000,000
- relative vs ACWI: 0 bps n/a, 10 bps n/a, 25 bps n/a over n/a

| sheet | ticker | qty | entry | exit | state | ret (local) | P&L USD | bench | note |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-07 | AXTI US Equity | 2,266 | 2026-10-07 79.77999877929688 |   | OPEN |  |  |  | mark 2026-10-07 +23 |
| 2026-10-07 | AVBP US Equity | 12,626 | 2026-10-07 15.244999885559082 |   | OPEN |  |  |  | mark 2026-10-07 +20,770 |
| 2026-10-07 | RXT US Equity | 47,382 | 2026-10-07 3.940000057220459 |   | OPEN |  |  |  | mark 2026-10-07 -4,264 |
| 2026-10-07 | UTZ US Equity | 13,351 | 2026-10-07 14.279999732971191 |   | OPEN |  |  |  | mark 2026-10-07 +134 |
| 2026-10-07 | QMCO US Equity | 5,691 | 2026-10-07 32.5 |   | OPEN |  |  |  | mark 2026-10-07 -8,138 |

