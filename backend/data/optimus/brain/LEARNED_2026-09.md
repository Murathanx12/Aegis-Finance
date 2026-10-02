# LEARNED_2026-09.md -- rules distilled from 2026-09's graded ledger

Last ledger distillation: 2026-09-30 -- **LEARNED** (24 rules written; answered by deepseek/deepseek-chat; local REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>; DeepSeek $0.002125)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-28 (ledger_distill): no new graded rows since 2026-09-26 (17484 graded, resolved through 2026-09-24)
- LEARN_DEGRADED 2026-09-29 (ledger_distill): no new graded rows since 2026-09-29 (17524 graded, resolved through 2026-09-28)

## MEASURED -- graded-ledger rules (n=24 current, 68 rows written this month)

### LRULE-2026-09-30-c4d40185 (class:investigator|abs_move_exceeds|h1)
- Rule (SKILL): "Investigator magnitude abs_move_exceeds at h=1 is SKILL: may be used at its measured weight, held-out skill +10.69%, discrimination +19.0pp."
- Numbers: n=1760 (held-out 880), Brier 0.11101 vs climatology 0.1243, skill 0.1069 (all rows 0.1287), disc 0.19, 9 date blocks
- Made from: 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-09-25; resolved through 2026-09-29; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.1069; hash 40ed40c959f55727fa56

### LRULE-2026-09-30-92c6fc64 (class:investigator|return_sign|h5)
- Rule (NO_DISCRIMINATION): "Investigator direction return_sign at h=5 is NO_DISCRIMINATION: weight 0, held-out skill -8.72%, discrimination +0.5pp."
- Numbers: n=1560 (held-out 780), Brier 0.25919 vs climatology 0.2384, skill -0.0872 (all rows -0.0794), disc 0.0055, 8 date blocks
- Made from: 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 95a748a2809f5049cf2c

### LRULE-2026-09-30-b9fdabce (class:investigator|abs_move_exceeds|h5)
- Rule (SKILL): "Investigator magnitude abs_move_exceeds at h=5 is SKILL: may be used at its measured weight, held-out skill +2.61%, discrimination +17.1pp."
- Numbers: n=1560 (held-out 780), Brier 0.16459 vs climatology 0.16899, skill 0.0261 (all rows -0.0064), disc 0.1708, 8 date blocks
- Made from: 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0261; hash e544d4c26bf25c6c43d8

### LRULE-2026-09-30-bfed17fb (class:investigator|beats_benchmark|h1)
- Rule (NO_DISCRIMINATION): "Investigator direction beats_benchmark at h=1 is NO_DISCRIMINATION: weight 0, held-out skill -1.42%, discrimination +0.0pp."
- Numbers: n=99 (held-out 50), Brier 0.24991 vs climatology 0.2464, skill -0.0142 (all rows -0.0868), disc 0.0004, 2 date blocks
- Made from: 2026-09-24, 2026-09-25; resolved through 2026-09-29; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 4a74ac9f31884d0eb1ab

### LRULE-2026-09-30-1b949a47 (class:personas|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "Personas pooled on abs_move_exceeds magnitude at h=20: NO_DISCRIMINATION, discrimination +1.2pp, held-out skill -74.08%; weight 0, do not use."
- Numbers: n=3165 (held-out 1583), Brier 0.34291 vs climatology 0.19698, skill -0.7408 (all rows -0.7559), disc 0.0122, 2 date blocks
- Made from: 2026-08-11, 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash e615ddfa14db3c0db06c

### LRULE-2026-09-30-06897a54 (class:personas|abs_move_exceeds|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled on abs_move_exceeds magnitude at h=5: NO_DISCRIMINATION, discrimination +1.7pp, held-out skill -71.04%; weight 0, do not use."
- Numbers: n=2346 (held-out 1173), Brier 0.33049 vs climatology 0.19322, skill -0.7104 (all rows -0.725), disc 0.0168, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 2d446037952d6d46ff6d

### LRULE-2026-09-30-477503a4 (class:personas|abs_move_exceeds|h2)
- Rule (NO_DISCRIMINATION): "Personas magnitude abs_move_exceeds at h=2 is NO_DISCRIMINATION: weight 0, held-out skill -133.49%, discrimination -0.6pp."
- Numbers: n=60 (held-out 30), Brier 0.37358 vs climatology 0.16, skill -1.3349 (all rows -1.5583), disc -0.0063, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 59484d0ed24bc5921388

### LRULE-2026-09-30-60cbbeea (class:personas|return_sign|h20)
- Rule (NO_DISCRIMINATION): "Personas pooled, return_sign h=20: NO_DISCRIMINATION, weight 0; held-out skill -19.58%, discrimination -0.6pp."
- Numbers: n=2479 (held-out 1240), Brier 0.28052 vs climatology 0.23458, skill -0.1958 (all rows -0.1964), disc -0.0062, 2 date blocks
- Made from: 2026-08-11, 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash df37bdd4a7ed88a47164

### LRULE-2026-09-30-078177a2 (class:personas|drawdown_exceeds|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled on drawdown_exceeds magnitude at h=5: NO_DISCRIMINATION, discrimination +0.4pp, held-out skill -52.14%; weight 0, do not use."
- Numbers: n=53 (held-out 27), Brier 0.31722 vs climatology 0.2085, skill -0.5214 (all rows -0.406), disc 0.0039, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 359c26622d70902f5bee

### LRULE-2026-09-30-a829cc0f (class:personas|abs_move_exceeds|h1)
- Rule (NO_SKILL): "Personas magnitude abs_move_exceeds at h=1 is NO_SKILL: weight 0, held-out skill -58.02%, discrimination +9.1pp."
- Numbers: n=42 (held-out 21), Brier 0.28667 vs climatology 0.18141, skill -0.5802 (all rows -1.1659), disc 0.0906, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash e9c922292f15b3fe30d4

### LRULE-2026-09-30-ccdf12b1 (class:personas|beats_benchmark|h20)
- Rule (NO_DISCRIMINATION): "Personas pooled on beats_benchmark direction at h=20: NO_DISCRIMINATION, discrimination +0.9pp, held-out skill -5.81%; weight 0, do not use."
- Numbers: n=2098 (held-out 1049), Brier 0.26027 vs climatology 0.24598, skill -0.0581 (all rows -0.0626), disc 0.0089, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash d9bf79a2318de547e1a1

### LRULE-2026-09-30-3b98301a (class:personas|return_sign|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled, return_sign h=5: NO_DISCRIMINATION, weight 0; held-out skill -4.01%, discrimination +0.0pp."
- Numbers: n=1986 (held-out 993), Brier 0.25962 vs climatology 0.24961, skill -0.0401 (all rows -0.045), disc 0.0003, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash fa82154b98d4a19a8606

### LRULE-2026-09-30-6335caae (class:personas|beats_benchmark|h5)
- Rule (NO_SKILL): "Personas pooled on beats_benchmark direction at h=5: NO_SKILL, held-out skill -13.82%, discrimination +2.7pp; weight 0, do not use."
- Numbers: n=135 (held-out 68), Brier 0.25994 vs climatology 0.22837, skill -0.1382 (all rows -0.1457), disc 0.0269, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 6e9b6b55ecb4cc8b0a02

### LRULE-2026-09-30-ff70c9f0 (class:personas|return_sign|h2)
- Rule (NO_SKILL): "Personas pooled, return_sign h=2: NO_SKILL, weight 0; held-out skill -15.31%, discrimination +2.7pp."
- Numbers: n=31 (held-out 16), Brier 0.21621 vs climatology 0.1875, skill -0.1531 (all rows -0.0542), disc 0.0267, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 5a1577496790e1347470

### LRULE-2026-09-30-8267cb05 (class:personas|return_sign|h1)
- Rule (NO_DISCRIMINATION): "Personas pooled, return_sign h=1: NO_DISCRIMINATION, weight 0; held-out skill -8.62%, discrimination +1.0pp."
- Numbers: n=43 (held-out 22), Brier 0.23563 vs climatology 0.21694, skill -0.0862 (all rows -0.0981), disc 0.01, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 6611a78d621db9617938

### LRULE-2026-09-30-c8821901 (class:personas|drawdown_exceeds|h20)
- Rule (NO_SKILL): "Personas pooled on drawdown_exceeds magnitude at h=20: NO_SKILL, held-out skill -1.66%, discrimination +2.4pp; weight 0, do not use."
- Numbers: n=343 (held-out 172), Brier 0.24642 vs climatology 0.24239, skill -0.0166 (all rows -0.0087), disc 0.0242, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash f7579ec9571328914da9

### LRULE-2026-09-30-0b13f8a6 (decision:PROBE-REFUSED|excess_vs_universe_median|h1)
- Rule (NOT_A_RESULT): "PROBE-REFUSED, h=1: NOT_A_RESULT, weight 0; mean gap -0.68% per day vs universe median."
- Numbers: n=155, mean gap -0.00679/day, t -0.831, 3 date blocks; Brier n/a (not a probability forecast)
- Made from: 2026-09-21, 2026-09-22, 2026-09-23; resolved through 2026-09-25; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash fd98b9a5036f6a410cf9

### LRULE-2026-09-30-eecb1221 (family:biotech_pharma|abs_move_exceeds|h20)
- Rule (NO_SKILL): "biotech_pharma, abs_move_exceeds h=20: NO_SKILL, weight 0; held-out skill -250.23%, discrimination +4.4pp."
- Numbers: n=80 (held-out 40), Brier 0.38306 vs climatology 0.10938, skill -2.5023 (all rows -1.6117), disc 0.0443, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash d393129e3a58700d9c2e

### LRULE-2026-09-30-696e5861 (family:options_volatility|abs_move_exceeds|h5)
- Rule (NO_DISCRIMINATION): "options_volatility abs_move_exceeds h=5: NO_DISCRIMINATION, weight 0; held-out skill -140.37%, discrimination +0.2pp."
- Numbers: n=230 (held-out 115), Brier 0.35878 vs climatology 0.14926, skill -1.4037 (all rows -1.2712), disc 0.0025, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 4201bdb4ee3632152b23

### LRULE-2026-09-30-3fff9ab3 (family:event_news|abs_move_exceeds|h5)
- Rule (NO_SKILL): "event_news abs_move_exceeds h=5: NO_SKILL, weight 0; held-out skill -92.59%, discrimination +3.0pp."
- Numbers: n=299 (held-out 150), Brier 0.33048 vs climatology 0.1716, skill -0.9259 (all rows -0.8709), disc 0.0298, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash fad0994b111f9be513da

### LRULE-2026-09-30-b2bfeb1e (family:options_volatility|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "options_volatility abs_move_exceeds h=20: NO_DISCRIMINATION, weight 0; held-out skill -95.27%, discrimination -1.5pp."
- Numbers: n=269 (held-out 135), Brier 0.36793 vs climatology 0.18842, skill -0.9527 (all rows -1.0412), disc -0.0154, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 9d7081aa1b0dc1cfc427

### LRULE-2026-09-30-b31550ed (family:execution_momentum|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "execution_momentum abs_move_exceeds h=20: NO_DISCRIMINATION, weight 0; held-out skill -82.90%, discrimination +0.8pp."
- Numbers: n=347 (held-out 174), Brier 0.3557 vs climatology 0.19448, skill -0.829 (all rows -0.8966), disc 0.0082, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 770b69ea36066e10547b

### LRULE-2026-09-30-1f73a2fe (family:event_news|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "event_news abs_move_exceeds h=20: NO_DISCRIMINATION, weight 0; held-out skill -109.84%, discrimination -0.3pp."
- Numbers: n=191 (held-out 96), Brier 0.35862 vs climatology 0.1709, skill -1.0984 (all rows -0.8745), disc -0.0026, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 3a6f0dc98ee0d888eb30

### LRULE-2026-09-30-cb08c7a4 (family:behavioral_narrative|abs_move_exceeds|h20)
- Rule (NO_SKILL): "behavioral_narrative abs_move_exceeds h=20: NO_SKILL, weight 0; held-out skill -87.71%, discrimination +2.5pp."
- Numbers: n=291 (held-out 146), Brier 0.34872 vs climatology 0.18578, skill -0.8771 (all rows -0.6894), disc 0.0254, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-09-30
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash fda6f86c1d70f459ab50

---

# M2 -- winner vs matched-loser pairs

Noise floor (shuffled-pair distillation, seed None): Brier None (climatology None)
Pairs: None real of None possible, 0 shuffled, 0 dropped as degenerate
Distillation model: the M2 pair path has not run this month, prompt contract None

## GENERALISED (n=0)

(none this month)

## NOT_GENERALISED (n=0)

(none this month)

## NOT_BETTER_THAN_NOISE (n=0)

(none this month)

## CANDIDATE (n=0)

(none this month)

## STALE (n=0)

(none this month)


