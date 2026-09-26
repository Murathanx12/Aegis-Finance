# SOURCES -- the source/actor scoreboard (2026-09-26)

Every source is a forecaster that has not earned a weight yet. Social sources are an **attention layer, not a truth layer**; X and Reddit **never generate orders**. A source whose names pop then fade is kept and labelled `use_as: reversal`.

Receipt: `scoreboard_2026-09-26.json` -- 514 sources, 24 claims, 11 sources with at least one claim.

## By kind

| kind | sources | claims | unverified |
|---|---:|---:|---:|
| company | 23 | 13 | 11 |
| filing | 4 | 0 | 0 |
| fund_manager | 3 | 0 | 0 |
| industry_specialist | 5 | 8 | 1 |
| journalist | 6 | 3 | 1 |
| newswire | 14 | 0 | 0 |
| reddit_community | 2 | 0 | 0 |
| retail_influencer | 1 | 0 | 0 |
| sell_side | 456 | 0 | 0 |

## Sources with claims (or social, unverified or not)

| source | kind | verified | n | lead h (med) | corrob. | 1d | 5d | 21d signed | FP 21d | skill h1/h5/h20 | crowding | weight | use as |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| x:agiospharma | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:bloom_energy | company | True | 5 | -2.8900 | +0.6000 | -0.0249 | +0.0178 | - | - | -/-/- | - | prior | prior |
| x:bridgebio | company | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:broadcom | company | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:cameco | company | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:celestica | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:centrusenergy | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:cogentbio | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:draftkings | company | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:gevernova | company | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:ionq_inc | company | True | 1 | -38.5 | +1.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:microntech | company | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:mpmaterials | company | True | 2 | - | +0.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:novantainc | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:nventhq | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:praxisprecision | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:repligen | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:robinhoodapp | company | True | 1 | - | +0.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:tsmc | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:vertexpharma | company | True | 2 | - | +0.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:vertiv | company | True | 2 | -25.9 | +1.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:vikingtx | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:westpharma | company | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:citronresearch | fund_manager | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:fuzzypandashort | fund_manager | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:muddywatersre | fund_manager | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:dylan522p | industry_specialist | True | 4 | -43.4 | +1.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:jukanlosreve | industry_specialist | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:semianalysis_ | industry_specialist | True | 3 | -3.7100 | +0.6667 | - | - | - | - | -/-/- | - | prior | prior |
| x:trendforce | industry_specialist | True | 1 | -38.8 | +1.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:adamfeuerstein | journalist | True | 1 | - | +0.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:deitaone | journalist | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:endpointsnews | journalist | False | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:fiercebiotech | journalist | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:firstsquawk | journalist | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |
| x:matthewherper | journalist | True | 2 | - | +0.0000 | - | - | - | - | -/-/- | - | prior | prior |
| x:unusual_whales | retail_influencer | True | 0 | - | - | - | - | - | - | -/-/- | - | prior | prior |

477 further registered sources (newswires, filings, brokerages) have no claims in the claims ledger; they are in the JSON receipt. Brokerages are scored from the revisions parquet below (`brokers` in the receipt) when that section is present.

## Metrics

- `lead_h_median`: hours from claim to the earliest mainstream (newswire/filing) item on the same ticker within +/-48h; positive = source first
- `corroboration_rate`: share of claims with a mainstream item on the same ticker in that window (a proxy for fact accuracy until facts are matched)
- `rel_ret_Nd`: mean name-minus-SPY return over N sessions entering at the first close strictly after the claim date
- `signed_ret_Nd`: the same, times the claim's stated direction
- `false_positive_rate_21d`: share of directional claims whose signed 21-session relative return was negative
- `skill_hN`: forecast_reputation.arm_skill keyed (source_id, beats_benchmark, h), held out on the later half by date
- `crowding_signature`: mean signed 21d minus mean signed 5d; <= -0.01 with a positive 5d and n >= 10 = use_as reversal
- `weight`: 'prior' until 20 graded rows at a horizon; then max(0, best held-out skill)

## Brokerages -- scored from `target_revisions.parquet` (2026-09-26)

393,568 claims (320,809 directional) from 456 firms. Outcome = the name's return minus the universe-median return from the first close after the revision (survivorship-free panel). Base hit rate: 5d 0.501, 21d 0.502 (last 3y: 0.500). Held-out split 2025-05-06; persistence of firm skill (Spearman, in-sample vs held-out, 62 firms): -0.106. 71 firms earned a registry weight.

**Caveat:** claims on the same name and day are NOT independent (a print draws 10 firms at once); hit rates are descriptive and the month-blocked first-mover SE is the only inferential number here.

### Top 20 by 21d hit rate (n >= 50 resolved 21d claims since 2023-09-26)

| firm | n21 | hit 21d | hit 5d | 21d after raise | 21d after lower | held-out skill (n) | weight | by year (hit21, n) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Melius Research | 56 | 0.571 | 0.456 | +3.43% | +3.47% | 0.185 (27) | 0.022 | 2023: 0.667 (3), 2024: 0.474 (19), 2025: 0.607 (28), 2026: 0.667 (6) |
| Craig-Hallum | 404 | 0.564 | 0.557 | +3.14% | -0.51% | -0.139 (65) | 0.000 | 2023: 0.490 (157), 2024: 0.606 (292), 2025: 0.534 (58), 2026: 0.375 (32) |
| Wolfe Research | 463 | 0.549 | 0.554 | +2.00% | -0.76% | 0.075 (201) | 0.037 | 2023: 0.488 (207), 2024: 0.562 (169), 2025: 0.553 (152), 2026: 0.514 (105) |
| Seaport Global | 270 | 0.541 | 0.548 | -1.30% | -2.41% | 0.054 (110) | 0.019 | 2023: 0.611 (36), 2024: 0.545 (88), 2025: 0.536 (97), 2026: 0.500 (66) |
| Ladenburg Thalmann | 82 | 0.537 | 0.549 | +0.61% | +8.68% | 0.106 (47) | 0.020 | 2023: 0.417 (12), 2024: 0.560 (25), 2025: 0.524 (21), 2026: 0.500 (34) |
| Roth MKM | 474 | 0.534 | 0.525 | +2.23% | -0.69% | 0.333 (3) | prior | 2023: 0.429 (161), 2024: 0.548 (354), 2025: 0.515 (66), 2026: 0.000 (1) |
| Telsey Advisory Group | 568 | 0.533 | 0.527 | +1.13% | +1.24% | 0.028 (247) | 0.016 | 2023: 0.478 (186), 2024: 0.554 (213), 2025: 0.553 (199), 2026: 0.482 (110) |
| Redburn Atlantic | 77 | 0.532 | 0.468 | -1.10% | -0.94% | 0.455 (11) | prior | 2023: 0.556 (9), 2024: 0.542 (48), 2025: 0.522 (23) |
| Leerink Partners | 249 | 0.530 | 0.534 | +3.32% | +3.45% | 0.103 (156) | 0.045 | 2023: 0.000 (3), 2024: 0.424 (66), 2025: 0.636 (88), 2026: 0.522 (92) |
| Roth Capital | 305 | 0.525 | 0.497 | +3.26% | -0.34% | 0.049 (305) | 0.030 | 2023: 0.632 (19), 2025: 0.573 (171), 2026: 0.463 (134) |
| Deutsche Bank | 1092 | 0.520 | 0.495 | +1.31% | +0.58% | 0.003 (329) | 0.002 | 2023: 0.484 (640), 2024: 0.533 (634), 2025: 0.471 (204), 2026: 0.535 (185) |
| Compass Point | 150 | 0.520 | 0.450 | +0.87% | +2.37% | 0.212 (33) | 0.030 | 2023: 0.426 (54), 2024: 0.523 (86), 2025: 0.542 (48), 2026: 0.500 (10) |
| Goldman Sachs | 3882 | 0.517 | 0.499 | +1.65% | +1.22% | 0.075 (1589) | 0.067 | 2023: 0.492 (1380), 2024: 0.528 (1373), 2025: 0.534 (1385), 2026: 0.504 (785) |
| HSBC | 347 | 0.516 | 0.535 | +0.92% | -1.48% | -0.101 (138) | 0.000 | 2023: 0.453 (95), 2024: 0.561 (164), 2025: 0.556 (81), 2026: 0.427 (82) |
| BTIG | 1086 | 0.516 | 0.520 | +1.93% | +2.50% | 0.017 (771) | 0.013 | 2023: 0.500 (176), 2024: 0.549 (264), 2025: 0.469 (260), 2026: 0.523 (535) |
| Baird | 3038 | 0.514 | 0.504 | +0.42% | -0.14% | -0.008 (1194) | 0.000 | 2023: 0.526 (736), 2024: 0.551 (1306), 2025: 0.470 (1143), 2026: 0.528 (545) |
| Freedom Broker | 244 | 0.512 | 0.540 | +0.52% | +0.79% | 0.025 (244) | 0.014 | 2025: 0.558 (95), 2026: 0.483 (149) |
| Macquarie | 428 | 0.512 | 0.490 | +2.08% | +1.20% | -0.027 (224) | 0.000 | 2023: 0.600 (35), 2024: 0.548 (146), 2025: 0.538 (143), 2026: 0.444 (135) |
| UBS | 7336 | 0.511 | 0.499 | +0.51% | +0.25% | 0.015 (4462) | 0.014 | 2023: 0.514 (887), 2024: 0.543 (1640), 2025: 0.501 (3153), 2026: 0.505 (2312) |
| Citigroup | 6843 | 0.510 | 0.512 | +0.85% | +0.65% | 0.016 (3955) | 0.015 | 2023: 0.494 (1855), 2024: 0.531 (1713), 2025: 0.505 (2394), 2026: 0.505 (2414) |

### Bottom 20 by 21d hit rate (n >= 50 resolved 21d claims since 2023-09-26)

| firm | n21 | hit 21d | hit 5d | 21d after raise | 21d after lower | held-out skill (n) | weight | by year (hit21, n) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Jones Trading | 65 | 0.354 | 0.455 | +0.67% | +9.99% | -0.192 (47) | 0.000 | 2024: 0.200 (10), 2025: 0.360 (25), 2026: 0.400 (30) |
| William Blair | 159 | 0.428 | 0.481 | +1.52% | +4.05% | -0.167 (84) | 0.000 | 2023: 0.484 (31), 2024: 0.436 (39), 2025: 0.419 (62), 2026: 0.420 (50) |
| Exane BNP Paribas | 78 | 0.436 | 0.513 | -0.84% | +1.44% | -0.667 (6) | prior | 2023: 0.481 (77), 2024: 0.412 (51), 2025: 0.286 (7), 2026: 0.000 (1) |
| Chardan Capital | 123 | 0.439 | 0.544 | -2.96% | +2.37% | -0.250 (80) | 0.000 | 2023: 0.486 (35), 2024: 0.500 (30), 2025: 0.467 (60), 2026: 0.333 (33) |
| GLJ Research | 50 | 0.440 | 0.608 | -2.44% | +4.53% | -0.172 (29) | 0.000 | 2023: 0.444 (9), 2024: 0.333 (9), 2025: 0.545 (22), 2026: 0.333 (15) |
| BWS Financial | 52 | 0.442 | 0.519 | +0.27% | +1.47% | 0.037 (27) | 0.004 | 2023: 0.583 (12), 2024: 0.533 (15), 2025: 0.286 (21), 2026: 0.615 (13) |
| Barrington Research | 298 | 0.450 | 0.497 | -0.76% | +0.78% | -0.079 (126) | 0.000 | 2023: 0.373 (83), 2024: 0.482 (114), 2025: 0.466 (103), 2026: 0.462 (65) |
| Citizens | 437 | 0.465 | 0.503 | -0.04% | +0.57% | -0.071 (437) | 0.000 | 2025: 0.425 (80), 2026: 0.473 (357) |
| JMP Securities | 789 | 0.473 | 0.498 | +0.31% | +2.35% | -0.048 (229) | 0.000 | 2023: 0.492 (311), 2024: 0.510 (394), 2025: 0.435 (331) |
| Lake Street | 225 | 0.476 | 0.573 | +0.38% | +1.22% | 0.032 (126) | 0.012 | 2023: 0.519 (52), 2024: 0.467 (60), 2025: 0.451 (113), 2026: 0.529 (51) |
| Loop Capital | 594 | 0.478 | 0.492 | +0.44% | +1.15% | 0.006 (153) | 0.003 | 2023: 0.514 (220), 2024: 0.475 (299), 2025: 0.494 (259), 2026: 0.400 (25) |
| Keybanc | 2297 | 0.480 | 0.499 | -0.47% | +0.33% | -0.027 (1083) | 0.000 | 2023: 0.491 (749), 2024: 0.500 (720), 2025: 0.454 (840), 2026: 0.511 (562) |
| BMO Capital | 2499 | 0.483 | 0.499 | -0.00% | +0.19% | -0.036 (1006) | 0.000 | 2023: 0.492 (778), 2024: 0.490 (1026), 2025: 0.469 (735), 2026: 0.514 (554) |
| HC Wainwright & Co. | 1411 | 0.483 | 0.484 | +1.28% | +5.23% | 0.012 (812) | 0.010 | 2023: 0.465 (299), 2024: 0.450 (360), 2025: 0.501 (555), 2026: 0.482 (415) |
| Piper Sandler | 4950 | 0.484 | 0.490 | +0.06% | +1.24% | -0.043 (2224) | 0.000 | 2023: 0.473 (1299), 2024: 0.501 (1588), 2025: 0.486 (1711), 2026: 0.472 (1253) |
| Scotiabank | 1772 | 0.484 | 0.496 | -0.05% | +1.15% | -0.036 (882) | 0.000 | 2023: 0.500 (92), 2024: 0.522 (542), 2025: 0.480 (735), 2026: 0.446 (464) |
| Northland Capital Markets | 287 | 0.484 | 0.466 | +3.24% | -0.10% | 0.099 (71) | 0.026 | 2023: 0.481 (104), 2024: 0.554 (157), 2025: 0.371 (89), 2026: 0.556 (27) |
| Cantor Fitzgerald | 1203 | 0.485 | 0.508 | +0.44% | +2.18% | -0.037 (841) | 0.000 | 2023: 0.443 (131), 2024: 0.516 (213), 2025: 0.471 (378), 2026: 0.490 (572) |
| Argus Research | 487 | 0.485 | 0.510 | +0.24% | +0.51% | -0.035 (230) | 0.000 | 2023: 0.514 (181), 2024: 0.515 (206), 2025: 0.471 (119), 2026: 0.479 (140) |
| Benchmark | 1118 | 0.486 | 0.505 | +1.21% | +1.04% | -0.049 (597) | 0.000 | 2023: 0.523 (283), 2024: 0.530 (334), 2025: 0.463 (402), 2026: 0.468 (316) |

### All firms by year

| year | claims | directional | hit 5d | hit 21d | 21d after raise | 21d after lower |
|---|---:|---:|---:|---:|---:|---:|
| 2011 | 4 | 2 | - | - | - | - |
| 2012 | 10,558 | 9,133 | - | - | - | - |
| 2013 | 12,544 | 9,876 | - | - | - | - |
| 2014 | 12,504 | 10,112 | - | - | - | - |
| 2015 | 12,962 | 10,336 | 0.500 | 0.500 | -5.27% | -1.55% |
| 2016 | 13,793 | 10,820 | 0.494 | 0.474 | +0.48% | +1.51% |
| 2017 | 9,847 | 7,525 | 0.510 | 0.515 | +0.81% | +1.01% |
| 2018 | 16,083 | 13,572 | 0.494 | 0.511 | +0.66% | +0.83% |
| 2019 | 15,098 | 12,137 | 0.501 | 0.499 | +0.62% | +1.36% |
| 2020 | 28,055 | 24,923 | 0.506 | 0.501 | +1.83% | +3.64% |
| 2021 | 23,876 | 19,747 | 0.506 | 0.515 | +0.16% | +0.31% |
| 2022 | 33,498 | 29,483 | 0.499 | 0.502 | +0.48% | +0.41% |
| 2023 | 45,460 | 34,462 | 0.493 | 0.496 | +0.36% | +1.04% |
| 2024 | 54,643 | 41,759 | 0.511 | 0.525 | +1.08% | -0.01% |
| 2025 | 57,561 | 47,126 | 0.497 | 0.490 | +0.26% | +0.98% |
| 2026 | 47,082 | 39,796 | 0.500 | 0.493 | +0.70% | +0.73% |

### First mover vs follower, point-in-time (other firms moving the name the same way in the prior 10 days, knowable at t)

| horizon | first: mean signed (hit, n) | second | third+ | first - third+ (month-block SE, t, blocks) | LOYO worst |
|---|---|---|---|---|---:|
| 5d | -0.01% (0.501, 142,960) | -0.06% (0.502, 57,992) | -0.02% (0.501, 78,824) | +0.05% (+0.09%, t 0.59, 130) | -0.01% |
| 21d | +0.01% (0.503, 142,070) | -0.06% (0.501, 57,643) | +0.03% (0.502, 77,868) | -0.06% (+0.24%, t -0.26, 129) | -0.23% |

21d first - third+ by year: 2015: -12.17%, 2016: +0.97%, 2017: -1.58%, 2018: -0.28%, 2019: +1.55%, 2020: -0.34%, 2021: +0.25%, 2022: -0.20%, 2023: +0.07%, 2024: -0.14%, 2025: +0.43%, 2026: -0.57%

### First mover vs follower, clusters (>= 3 firms, same name and direction, within 10 days) -- LOOK-AHEAD, descriptive

A cluster is only known once its followers arrive, so 'the first firm of a cluster' is selected on the future. Read this as where in a cascade the return accrues, not as a signal.

- **5d**: 28,465 clusters; 0.268 have first and last entering on the same session. All: first +0.65% vs last -0.11%, diff +0.80% (month-block SE +0.10%, t 7.97, 129 blocks). Staggered only (20,851): first +0.85% vs last -0.10%, diff +1.02% (SE +0.12%, t 8.32); leave-one-year-out worst +0.92%.
  - by rank: #1: +0.65% (hit 0.535, n 26,105), #2: +0.12% (hit 0.510, n 26,095), #3: -0.07% (hit 0.499, n 26,089), #4: -0.05% (hit 0.498, n 14,532), #5+: +0.01% (hit 0.504, n 28,244)
  - staggered diff by year: 2016: +1.06% (412), 2017: +0.83% (266), 2018: +0.85% (680), 2019: +1.19% (556), 2020: +1.24% (1719), 2021: +1.19% (1166), 2022: +0.69% (2162), 2023: +0.94% (2638), 2024: +0.91% (3430), 2025: +0.97% (4159), 2026: +0.90% (3612)
- **21d**: 28,465 clusters; 0.268 have first and last entering on the same session. All: first +0.80% vs last -0.10%, diff +1.07% (month-block SE +0.13%, t 8.01, 128 blocks). Staggered only (20,851): first +1.00% vs last -0.14%, diff +1.34% (SE +0.15%, t 8.74); leave-one-year-out worst +1.10%.
  - by rank: #1: +0.80% (hit 0.528, n 25,933), #2: +0.15% (hit 0.508, n 25,922), #3: -0.03% (hit 0.504, n 25,910), #4: +0.05% (hit 0.503, n 14,406), #5+: +0.16% (hit 0.502, n 27,735)
  - staggered diff by year: 2016: +1.84% (412), 2017: +1.14% (266), 2018: +0.74% (680), 2019: +1.52% (556), 2020: +1.23% (1719), 2021: +1.10% (1166), 2022: +0.79% (2162), 2023: +0.98% (2638), 2024: +1.21% (3430), 2025: +1.25% (4159), 2026: +1.12% (3439)

#### Firms most often first (>= 30 cluster claims since 2023-09-26)

| firm | cluster claims | share first | mean rank pct | 21d signed when first | when follower |
|---|---:|---:|---:|---:|---:|
| Needham | 1386 | 0.455 | 0.224 | -0.19% | +0.27% |
| BTIG | 612 | 0.410 | 0.298 | -0.70% | -0.29% |
| HC Wainwright & Co. | 447 | 0.380 | 0.390 | -2.49% | +0.07% |
| Seaport Global | 77 | 0.351 | 0.426 | +4.62% | -0.12% |
| Baird | 1778 | 0.346 | 0.341 | +0.85% | +0.05% |
| Chardan Capital | 65 | 0.339 | 0.368 | -4.65% | +0.21% |
| William Blair | 90 | 0.322 | 0.357 | -1.42% | -4.15% |
| Compass Point | 57 | 0.281 | 0.566 | +4.35% | +0.91% |
| Wolfe Research | 150 | 0.280 | 0.492 | +0.81% | +2.87% |
| Telsey Advisory Group | 407 | 0.278 | 0.363 | +2.11% | +0.10% |
| Citizens | 262 | 0.267 | 0.391 | +0.40% | -1.07% |
| B of A Securities | 2120 | 0.264 | 0.423 | +0.67% | +0.44% |
| Keybanc | 1224 | 0.263 | 0.402 | +0.25% | -0.39% |
| Jefferies | 1195 | 0.253 | 0.478 | +0.35% | +0.51% |
| Leerink Partners | 137 | 0.248 | 0.462 | -0.89% | -0.41% |

Lead time vs the corpus's first mainstream item: 65 firms have at least one matched claim (the corpus starts 2026-09-11); the rest are null, not zero. Per-firm values are in the JSON receipt.

