# LEARNED_2026-10.md -- rules distilled from 2026-10's graded ledger

Last ledger distillation: 2026-10-08 -- **LEARNED** (24 rules written; answered by deepseek/deepseek-chat; local REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>; DeepSeek $0.002112)
- LEARN_DEGRADED 2026-10-07 (ledger_distill): no new graded rows since 2026-10-07 (20095 graded, resolved through 2026-10-06)
- LEARN_DEGRADED 2026-10-07 (ledger_distill): no new graded rows since 2026-10-07 (20095 graded, resolved through 2026-10-06)

## MEASURED -- graded-ledger rules (n=24 current, 41 rows written this month)

### LRULE-2026-10-08-c4d40185 (class:investigator|abs_move_exceeds|h1)
- Rule (SKILL): "investigator magnitude abs_move_exceeds h=1: SKILL, may be used at its measured weight; held-out skill vs climatology +13.44%, discrimination +20.8pp."
- Numbers: n=2360 (held-out 1180), Brier 0.09219 vs climatology 0.1065, skill 0.1344 (all rows 0.112), disc 0.2075, 12 date blocks
- Made from: 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-09-25, 2026-09-28, 2026-09-29, 2026-10-01; resolved through 2026-10-05; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.1344; hash 81572324fb7fff9a9544

### LRULE-2026-10-08-92c6fc64 (class:investigator|return_sign|h5)
- Rule (NO_DISCRIMINATION): "investigator direction return_sign h=5: NO_DISCRIMINATION, weight 0; held-out skill vs climatology -11.08%, discrimination +0.9pp."
- Numbers: n=1760 (held-out 880), Brier 0.2567 vs climatology 0.23109, skill -0.1108 (all rows -0.0926), disc 0.0092, 9 date blocks
- Made from: 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-09-25; resolved through 2026-10-05; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash f98c8825455b27dd5f52

### LRULE-2026-10-08-b9fdabce (class:investigator|abs_move_exceeds|h5)
- Rule (NO_SKILL): "investigator magnitude abs_move_exceeds h=5: NO_SKILL, weight 0; held-out skill vs climatology -1.00%, discrimination +17.9pp."
- Numbers: n=1760 (held-out 880), Brier 0.14878 vs climatology 0.14731, skill -0.01 (all rows -0.0037), disc 0.1795, 9 date blocks
- Made from: 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-09-25; resolved through 2026-10-05; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 70448f9c30039ef13cb6

### LRULE-2026-10-08-29c68ba6 (class:investigator|beats_benchmark|h5)
- Rule (NO_DISCRIMINATION): "investigator direction beats_benchmark h=5: NO_DISCRIMINATION, weight 0; held-out skill vs climatology -2.01%, discrimination +1.5pp."
- Numbers: n=193 (held-out 97), Brier 0.24524 vs climatology 0.24041, skill -0.0201 (all rows 0.0206), disc 0.0147, 2 date blocks
- Made from: 2026-09-25, 2026-09-26; resolved through 2026-10-06; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash e83c5fd63ac362092540

### LRULE-2026-10-08-bfed17fb (class:investigator|beats_benchmark|h1)
- Rule (NO_DISCRIMINATION): "investigator direction beats_benchmark h=1: NO_DISCRIMINATION, weight 0; held-out skill vs climatology -0.77%, discrimination +0.0pp."
- Numbers: n=472 (held-out 236), Brier 0.25045 vs climatology 0.24855, skill -0.0077 (all rows -0.0018), disc 0.0003, 5 date blocks
- Made from: 2026-09-24, 2026-09-25, 2026-09-26, 2026-09-28, 2026-09-29; resolved through 2026-10-03; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash cb1affe36d8a81aa30ca

### LRULE-2026-10-08-1b949a47 (class:personas|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "Personas pooled, abs_move_exceeds h=20: NO_DISCRIMINATION, weight 0; held-out skill -74.08%, discrimination +1.2pp."
- Numbers: n=3165 (held-out 1583), Brier 0.34291 vs climatology 0.19698, skill -0.7408 (all rows -0.7559), disc 0.0122, 2 date blocks
- Made from: 2026-08-11, 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 0b89870010d2dbb97f7b

### LRULE-2026-10-08-06897a54 (class:personas|abs_move_exceeds|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled, abs_move_exceeds h=5: NO_DISCRIMINATION, weight 0; held-out skill -71.04%, discrimination +1.7pp."
- Numbers: n=2346 (held-out 1173), Brier 0.33049 vs climatology 0.19322, skill -0.7104 (all rows -0.725), disc 0.0168, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash d8dfef1dca4df4c9ca38

### LRULE-2026-10-08-477503a4 (class:personas|abs_move_exceeds|h2)
- Rule (NO_DISCRIMINATION): "Personas pooled, abs_move_exceeds h=2: NO_DISCRIMINATION, weight 0; held-out skill -133.49%, discrimination -0.6pp."
- Numbers: n=60 (held-out 30), Brier 0.37358 vs climatology 0.16, skill -1.3349 (all rows -1.5583), disc -0.0063, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 5811389f5a24f7c0efdf

### LRULE-2026-10-08-60cbbeea (class:personas|return_sign|h20)
- Rule (NO_DISCRIMINATION): "Personas pooled, return_sign h=20: NO_DISCRIMINATION, discrimination -0.6pp, held-out skill -19.58% — weight 0, do not use."
- Numbers: n=2479 (held-out 1240), Brier 0.28052 vs climatology 0.23458, skill -0.1958 (all rows -0.1964), disc -0.0062, 2 date blocks
- Made from: 2026-08-11, 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 0c479739544719e99147

### LRULE-2026-10-08-078177a2 (class:personas|drawdown_exceeds|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled, drawdown_exceeds h=5: NO_DISCRIMINATION, discrimination +0.4pp, held-out skill -52.14% — weight 0, do not use."
- Numbers: n=53 (held-out 27), Brier 0.31722 vs climatology 0.2085, skill -0.5214 (all rows -0.406), disc 0.0039, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 7ea4b8f49efdef1c4fd6

### LRULE-2026-10-08-ccdf12b1 (class:personas|beats_benchmark|h20)
- Rule (NO_DISCRIMINATION): "Personas pooled, beats_benchmark h=20: NO_DISCRIMINATION, weight 0; held-out skill -5.81%, discrimination +0.9pp."
- Numbers: n=2098 (held-out 1049), Brier 0.26027 vs climatology 0.24598, skill -0.0581 (all rows -0.0626), disc 0.0089, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 3028a440cec4c775f996

### LRULE-2026-10-08-3b98301a (class:personas|return_sign|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled, return_sign h=5: NO_DISCRIMINATION, discrimination +0.0pp, held-out skill -4.01% — weight 0, do not use."
- Numbers: n=1986 (held-out 993), Brier 0.25962 vs climatology 0.24961, skill -0.0401 (all rows -0.045), disc 0.0003, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 335e62c4d86f0977dc6c

### LRULE-2026-10-08-1e07a73d (class:personas|beats_benchmark|h1)
- Rule (NO_DISCRIMINATION): "Personas pooled, beats_benchmark h=1: NO_DISCRIMINATION, weight 0; held-out skill -5.48%, discrimination +0.7pp."
- Numbers: n=388 (held-out 194), Brier 0.2609 vs climatology 0.24734, skill -0.0548 (all rows -0.0487), disc 0.0065, 8 date blocks
- Made from: 2026-09-26, 2026-09-27, 2026-09-28, 2026-09-29, 2026-09-30, 2026-10-01, 2026-10-02, 2026-10-03; resolved through 2026-10-07; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 327c10e7058a745a6838

### LRULE-2026-10-08-6335caae (class:personas|beats_benchmark|h5)
- Rule (NO_DISCRIMINATION): "Personas pooled, beats_benchmark h=5: NO_DISCRIMINATION, weight 0; held-out skill -8.17%, discrimination -1.1pp."
- Numbers: n=170 (held-out 85), Brier 0.26949 vs climatology 0.24913, skill -0.0817 (all rows -0.1172), disc -0.0114, 3 date blocks
- Made from: 2026-08-12, 2026-09-26, 2026-09-27; resolved through 2026-10-07; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash a8d82a35827ad8c691c4

### LRULE-2026-10-08-ff70c9f0 (class:personas|return_sign|h2)
- Rule (NO_SKILL): "Personas pooled, return_sign h=2: NO_SKILL, held-out skill -15.31% — weight 0, do not use."
- Numbers: n=31 (held-out 16), Brier 0.21621 vs climatology 0.1875, skill -0.1531 (all rows -0.0542), disc 0.0267, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 136397e0f36ab35543d6

### LRULE-2026-10-08-a829cc0f (class:personas|abs_move_exceeds|h1)
- Rule (NO_SKILL): "personas magnitude abs_move_exceeds h=1: NO_SKILL, weight 0; held-out skill vs climatology -7.87%, discrimination +10.1pp."
- Numbers: n=63 (held-out 32), Brier 0.20225 vs climatology 0.1875, skill -0.0787 (all rows -0.7916), disc 0.1011, 6 date blocks
- Made from: 2026-08-12, 2026-09-29, 2026-09-30, 2026-10-01, 2026-10-02, 2026-10-03; resolved through 2026-10-07; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash a7f1625456f6d28020d7

### LRULE-2026-10-08-8267cb05 (class:personas|return_sign|h1)
- Rule (NO_DISCRIMINATION): "Personas pooled, return_sign h=1: NO_DISCRIMINATION, discrimination +1.0pp, held-out skill -8.62% — weight 0, do not use."
- Numbers: n=43 (held-out 22), Brier 0.23563 vs climatology 0.21694, skill -0.0862 (all rows -0.0981), disc 0.01, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash de2f34e2c7dfe6d497ea

### LRULE-2026-10-08-c8821901 (class:personas|drawdown_exceeds|h20)
- Rule (NO_SKILL): "Personas pooled, drawdown_exceeds h=20: NO_SKILL, held-out skill -1.66% — weight 0, do not use."
- Numbers: n=343 (held-out 172), Brier 0.24642 vs climatology 0.24239, skill -0.0166 (all rows -0.0087), disc 0.0242, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash d5a30e147c88dfe0ab95

### LRULE-2026-10-08-0b13f8a6 (decision:PROBE-REFUSED|excess_vs_universe_median|h1)
- Rule (NOT_A_RESULT): "PROBE-REFUSED at h=1 is not a result: mean gap -0.68% per day, t -0.831, weight 0."
- Numbers: n=155, mean gap -0.00679/day, t -0.831, 3 date blocks; Brier n/a (not a probability forecast)
- Made from: 2026-09-21, 2026-09-22, 2026-09-23; resolved through 2026-09-25; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 1f423f6251ceeabfee2c

### LRULE-2026-10-08-eecb1221 (family:biotech_pharma|abs_move_exceeds|h20)
- Rule (NO_SKILL): "biotech_pharma abs_move_exceeds at h=20 is NO_SKILL: held-out skill -250.23%, weight 0."
- Numbers: n=80 (held-out 40), Brier 0.38306 vs climatology 0.10938, skill -2.5023 (all rows -1.6117), disc 0.0443, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 45c442a24d29b24c03bd

### LRULE-2026-10-08-696e5861 (family:options_volatility|abs_move_exceeds|h5)
- Rule (NO_DISCRIMINATION): "options_volatility abs_move_exceeds at h=5 is NO_DISCRIMINATION: held-out skill -140.37%, discrimination +0.2pp, weight 0."
- Numbers: n=230 (held-out 115), Brier 0.35878 vs climatology 0.14926, skill -1.4037 (all rows -1.2712), disc 0.0025, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 8a587a4d3228556e26ad

### LRULE-2026-10-08-3fff9ab3 (family:event_news|abs_move_exceeds|h5)
- Rule (NO_SKILL): "event_news abs_move_exceeds at h=5 is NO_SKILL: held-out skill -92.59%, weight 0."
- Numbers: n=299 (held-out 150), Brier 0.33048 vs climatology 0.1716, skill -0.9259 (all rows -0.8709), disc 0.0298, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash bf76c184313f560a9deb

### LRULE-2026-10-08-b2bfeb1e (family:options_volatility|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "options_volatility abs_move_exceeds at h=20 is NO_DISCRIMINATION: held-out skill -95.27%, discrimination -1.5pp, weight 0."
- Numbers: n=269 (held-out 135), Brier 0.36793 vs climatology 0.18842, skill -0.9527 (all rows -1.0412), disc -0.0154, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash 2939ec9ee5c655ca94ee

### LRULE-2026-10-08-b31550ed (family:execution_momentum|abs_move_exceeds|h20)
- Rule (NO_DISCRIMINATION): "execution_momentum abs_move_exceeds at h=20 is NO_DISCRIMINATION: held-out skill -82.90%, discrimination +0.8pp, weight 0."
- Numbers: n=347 (held-out 174), Brier 0.3557 vs climatology 0.19448, skill -0.829 (all rows -0.8966), disc 0.0082, 1 date blocks
- Made from: 2026-08-12; resolved through 2026-09-24; hindsight_safe True; as of 2026-10-08
- Written by deepseek/deepseek-chat (local: REFUSED: ProviderRefusal: local unreachable: URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>); prompt_weight 0.0; hash b4808b16e199ff13e9f6

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


