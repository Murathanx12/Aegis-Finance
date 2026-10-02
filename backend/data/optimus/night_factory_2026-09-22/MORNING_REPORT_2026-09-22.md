# MORNING REPORT 2026-09-22

Night folder `C:\Users\mrthn\aegis-finance\backend\data\optimus\night_factory_2026-09-22` — 31 receipt(s). Written 2026-09-22T04:17:16+00:00. Licence PRODUCT_EXPERIMENT; no model was called.

## 1. Paper NAV vs SPY
- CANNOT DETERMINE: the live market loop wrote no NAV: it did not run, or it held no broker lease. This is an OPERATIONAL finding, not a missing number — the account can be read in one call (looked for `C:\Users\mrthn\aegis-finance\backend\data\optimus\pc_book\2026-09-22\nav.jsonl`)
- internal NAV vs SPY: 22 books, mean +1.07% vs SPY +0.99% = excess +0.08% (2026-09-11..2026-09-21); best e693c3e4 +10.17%, worst f7ec2286 -2.43%
- EXPLOIT P&L: CANNOT DETERMINE: no EXPLOIT decision has been SCORED yet — the ledger holds no `SCORED` row for one (0 scored row(s) carried no usable realised return). A decision is scored when its own expiry passes and the grader joins it to close-to-close returns; until then a P&L number would be invented
- EXPLORE P&L: CANNOT DETERMINE: no EXPLORE decision has been SCORED yet — the ledger holds no `SCORED` row for one (0 scored row(s) carried no usable realised return). A decision is scored when its own expiry passes and the grader joins it to close-to-close returns; until then a P&L number would be invented
- capital resolved: every dollar resolved today: 99.75% benchmark core, 0.00% active EXPLOIT across 0 name(s), 0.25% active EXPLORE across 1 name(s), 0.00% cash. 'No active trade' is an allowed outcome; 'nothing happened' is not, and this line is the proof it did not happen.

## 1b. The twenty best next-month names
- 2,909 eligible names ranked as of 2026-09-21 (model 374d20ee23a8, 20.1s)
- **MEASURED_NEGATIVE** — a top-18 book earned -4.22% relative per 21 sessions NET out of sample over 7 month-blocks (IC -0.0316). This is not an uncertain bet, it is a measured losing one. Refusing it is evidence-led, not timid — fix the ranking, then trade it.

| # | ticker | decile | exp rel 21d (net) | downside p20 | P(beat) | liquidity |
|---|---|---|---|---|---|---|
| 1 | FLNC | 9 | -1.93% | -12.07% | 40% | mid |
| 2 | ALMS | 9 | -1.93% | -12.07% | 40% | mid |
| 3 | WAY | 9 | -1.93% | -12.07% | 40% | mid |
| 4 | DUOL | 9 | -1.85% | -12.07% | 40% | large |
| 5 | GDDY | 9 | -1.85% | -12.07% | 40% | large |
| 6 | MPLT | 9 | -2.10% | -12.07% | 40% | small |
| 7 | NICE | 9 | -1.93% | -12.07% | 40% | mid |
| 8 | ALHC | 9 | -1.93% | -12.07% | 40% | mid |
| 9 | DBVT | 9 | -2.10% | -12.07% | 40% | small |
| 10 | GWRE | 9 | -1.85% | -12.07% | 40% | large |
| 11 | MNSO | 9 | -2.10% | -12.07% | 40% | small |
| 12 | BIOA | 9 | -2.10% | -12.07% | 40% | small |
| 13 | PEGA | 9 | -1.93% | -12.07% | 40% | mid |
| 14 | EVMN | 9 | -2.10% | -12.07% | 40% | small |
| 15 | DXC | 9 | -1.93% | -12.07% | 40% | mid |
| 16 | CNXC | 9 | -1.93% | -12.07% | 40% | mid |
| 17 | ZUMZ | 9 | -2.10% | -12.07% | 40% | small |
| 18 | LI | 9 | -1.93% | -12.07% | 40% | mid |

## 2. EXPLOIT / EXPLORE / PROBE
- direction: {'BUY': 4, 'WATCH': 0, 'SELL': 0, 'PROBE': 152, 'REFUSED': 1}
- authority: {'EXPLORE': 4, 'REFUSED': 1, 'PROBE': 152}
- EXPLORE names (4): AGENCY_BOOK:aggressive, AGENCY_BOOK:balanced, AGENCY_BOOK:extreme_growth, CVLG
- PROBE names (38): AAPL, AMZN, ANIP, APOG, AVPT, BBSI, BOX, BTSG, BWA, CCEP, CON, CRAI ...
- decision ledger states: {'DECIDED': 157}

## 3. Expected-return leaders
- ROI rule: expected_return_net / downside, top K, fractional Kelly; considered 2, scored 0, not calibrated 2
  - CVLG (profitability_small): +0.3576%/horizon, calibration WEAK
  - INDV (insider_opportunistic): -0.0726%/horizon, calibration WEAK

## 4. Calibration verdicts
- C7_signal_calibration_run01: 3 leadable signal(s): 0 CALIBRATED, 3 WEAK, 0 INVERTED, 0 NO_PANEL, 0 REFUSED
- per-signal: {"profitability_small": {"verdict": "WEAK", "net_spread_pct": 0.644511, "net_t": 1.5879, "holm_p": 1.0, "n_date_blocks": 191, "file": "backend\\data\\optimus\\calibration\\profitability_small_2026-09-22.json"}, "insider_opportunistic": {"verdict": "WEAK", "net_spread_pct": -0.046304, "net_t": -0.3482, "holm_p": 1.0, "n_date_blocks": 191, "file": "backend\\data\\optimus\\calibration\\insider_opport

## 5. Largest graded errors and the curriculum
- 25039 error rows (14703 gradeable, 10336 ungradeable and every one carries its reason); biggest cluster UNGRADEABLE at 10336; Brier 0.262538 vs climatology 0.224378 (skill -0.170073) on 14703 graded rows
  - RTX 2026-08-19 investigator:A_snapshot: expected 0.02, actual 1 (RIGHT_DIRECTION_WRONG_MAGNITUDE)
  - NOC 2026-08-17 investigator:C_tools_only: expected 0.02, actual 1 (RIGHT_DIRECTION_WRONG_MAGNITUDE)
  - NOC 2026-08-17 investigator:B_tools: expected 0.03, actual 1 (RIGHT_DIRECTION_WRONG_MAGNITUDE)
  - NOC 2026-08-17 investigator:D_all: expected 0.03, actual 1 (RIGHT_DIRECTION_WRONG_MAGNITUDE)
  - V 2026-08-19 investigator:B_tools: expected 0.04, actual 1 (RIGHT_DIRECTION_WRONG_MAGNITUDE)
  - CURRICULUM RIGHT_DIRECTION_WRONG_MAGNITUDE (n 2983, priority 1922.5608): Re-grade the threshold observables against the REALISED distribution of |return| at that horizon: if the calls are biased one way, the threshold prior is wrong and it is a constant, not a model.
  - CURRICULUM WRONG_DIRECTION (n 2200, priority 1302.47): Split the sign misses by mechanism and re-ask whether the mechanism has ANY directional content: a mechanism whose sign accuracy is 0.5 on its own graded rows should be reduced to a magnitude/volatility forecaster rather than repaired as a direction forecaster.
  - CURRICULUM LOW_CONFIDENCE_RIGHT (n 4033, priority 1132.3405): Test whether the p<=0.55 rows carry usable information the sizing throws away -- a mechanism that is right at 0.52 more often than 52% is under-confident, and under-confidence costs size, not accuracy.

## 6. Missed opportunities
- 30 largest unmatched move(s) over 21 sessions (best 5-session |excess vs SPY|, floor $5,000,000); 30 not in the universe, 0 carried a BUY/PROBE; 10 with no precursor and both readers saying unforeseeable; local 0.5833 vs deepseek 0.68 hit rate; $0.0064 of $4.50
- paired: {"local_gguf": {"n_graded": 24, "n_hit": 14, "hit_rate": 0.5833, "brier": {"brier": 0.688854, "n": 24, "hit_rate": 0.5833, "brier_of_always_predicting_the_base_rate": 0.243056, "note": "a Brier above 
  - {"ticker": "MRNA", "window_start": "2026-08-13", "window_end": "2026-08-19", "excess_pct": 176.3317, "abs_excess_pct": 176.3317, "direction": "UP", "median_dollar_vol": 2337534696.
  - {"ticker": "DFNS", "window_start": "2026-08-18", "window_end": "2026-08-24", "excess_pct": -83.7163, "abs_excess_pct": 83.7163, "direction": "DOWN", "median_dollar_vol": 7925792.0,
  - {"ticker": "CAPR", "window_start": "2026-08-13", "window_end": "2026-08-19", "excess_pct": 78.6488, "abs_excess_pct": 78.6488, "direction": "UP", "median_dollar_vol": 53924017.3, "
  - {"ticker": "AMLX", "window_start": "2026-08-17", "window_end": "2026-08-21", "excess_pct": 74.4454, "abs_excess_pct": 74.4454, "direction": "UP", "median_dollar_vol": 59307648.7, "
  - {"ticker": "ARCT", "window_start": "2026-08-19", "window_end": "2026-08-25", "excess_pct": 68.987, "abs_excess_pct": 68.987, "direction": "UP", "median_dollar_vol": 15659098.0, "ae

## 7. Drift
- NO DRIFT DETECTED: ADWIN refit 1x vs FIXED 14
- timeline: [{"test_month": "2025-08", "adwin_refit": true, "reason": "first fit", "model_fitted_for": "2025-08", "adwin_state": {"width": 21, "mean": 0.2773559, "variance": 0.0032939907, "n_detections": 0, "last_detection_at": null

## 8. Champion vs challengers
- E1_event_head: rejected (status done) — GBM/EVENT: EVENT - SHUFFLE IC +0.0004 (t 0.097, Holm p 1.0) over 276 date blocks -> NO | GBM/SCALAR: SCALAR - SCALAR_SHUFFLE IC +0.0032 (t 0.979, Holm p 1.0) over 276 date blocks -> NO | StockMixer_T1
- E3_adaptive_conformal: NO_IMPROVEMENT (status done) — nominal 90% on 276 date blocks, arm GBM_EVENT: HIGH-vol realised coverage NAIVE 0.8587 / ACI 0.8804 / ACI_WEIGHTED 0.8696; LOW-vol NAIVE 0.8333 / ACI 0.8462
- E4_adwin_gated_refit: NO_IMPROVEMENT (status done) — ADWIN refit 1 times vs FIXED 14 on 276 identical test dates; ADWIN - FIXED IC +0.0103 (t 1.818, p 0.0702); 255 dates ran on a stale model, max age 13 months; fit seconds 0.87 vs 28.66
- E5_stopping_rules: NO_IMPROVEMENT (status unknown) — 4 lineages admitted at banks_met>=2 out of 251 (595 distinct genomes); 1 ACTIVE, 3 CANNOT_DETERMINE; PBO insufficient_windows

## 9. Gym
- CANNOT DETERMINE: no gym receipt (looked for `night_factory_<date>/S2_scenario_gym_run*.json`)

## 10. Bandit / OPE
_(16 body line(s) truncated to keep the report under 120 lines; the elided sections are recoverable from the receipts in `C:\Users\mrthn\aegis-finance\backend\data\optimus\night_factory_2026-09-22`. First elided line: - bandit / off-policy evaluation: CANNOT DETERMINE — 0 SCORED decision row(s) on)_

## THE FIVE QUESTIONS
**Q1 — Is AEGIS objectively better than last night? NO.** NO receipt in this night's folder carries a MODEL_IMPROVED:/CAPITAL_CHANGED:/WEIGHT_CHANGED: line with a measured before -> after, so nothing measurable moved. Engineering happened; the numbers did not. (12 line(s) carried the prefix and no measured before -> after, and do not count.)

**Q2 — What measurably improved?**
- none

**Q3 — What belief changed or died?**
- `J3_morning_report_run01` HYPOTHESIS_KILLED:
- `J3_morning_report_run01` BELIEF_CHANGED:
- `J3_morning_report_run01` HYPOTHESIS_KILLED:
- `J3_morning_report_run01` BELIEF_CHANGED:
- `J3_morning_report_run01` HYPOTHESIS_KILLED:
- `J3_morning_report_run01` BELIEF_CHANGED:
- `J3_morning_report_run01` HYPOTHESIS_KILLED:
- `J3_morning_report_run01` BELIEF_CHANGED:

**Q4 — What is owed, and when?**
- AAPL (PROBE/PROBE) first grade 2026-09-29
- AAPL (PROBE/PROBE) first grade 2026-10-21
- AAPL (PROBE/PROBE) first grade 2026-12-21
- AAPL (PROBE/PROBE) first grade 2027-03-24
- AGENCY_BOOK:aggressive (BUY/EXPLORE) first grade 2026-10-22
- AGENCY_BOOK:balanced (BUY/EXPLORE) first grade 2026-10-22
- AGENCY_BOOK:extreme_growth (BUY/EXPLORE) first grade 2026-09-29
- AMZN (PROBE/PROBE) first grade 2026-09-29
- AMZN (PROBE/PROBE) first grade 2026-10-21
- AMZN (PROBE/PROBE) first grade 2026-12-21
- WEAK near-miss: CVLG/profitability_small: WEAK, spread t 1.5879, Holm p 1.0
- WEAK near-miss: INDV/insider_opportunistic: WEAK, spread t -0.3482, Holm p 1.0

**Q5 — What should tonight test?** RIGHT_DIRECTION_WRONG_MAGNITUDE (n 2983): Re-grade the threshold observables against the REALISED distribution of |return| at that horizon: if the calls are biased one way, the threshold prior is wrong and it is a constant, not a model.

