# OPUS PROMPT — Gate M Recalibration (RECAL-1), 2026-08-06

Copy-paste body below. Ratification record: Murat approved the IC-gate
recalibration on 2026-08-06 ("fix immediately").

---

You are running the Gate M recalibration for the Aegis strategy factory.
Work in `C:\Users\mrthn\Aegis module` (venv `.venv\Scripts\python.exe`,
package `aegis_brain/calibration/`, outputs `runs/GATE-M1/`, gitignored).
Companion docs live in `C:\Users\mrthn\aegis-finance\docs\`.

## Step 0 — Read state first, re-derive nothing
Read, in order: `Aegis module/docs/GATE_M1_VERDICT_2026-08-06.md`,
`aegis-finance/docs/OPUS_HANDOFF_DECISION_ENGINE_2026-08-05.md`,
`runs/GATE-M1/stage3_tables.json`, `runs/GATE-M1/threshold_sweep.json`,
`aegis_brain/calibration/run_grid.py` + `posterior.py` + `sweep.py`
docstrings. Also call `aegis_verified_state` + `aegis_canon` (optimus MCP).
Banked negative results are FINAL — do not re-derive: cross-segment scan
reuse is invalid (migration leak); c_t re-standardization stays
deterministic; posterior bucket likelihood too sparse under the OLD gate.

## Context (measured, n=250×13 cells, commit f6d4195)
The frozen pipeline's FDR is 0 but false-kill is 100% at every injected
edge strength on all four designs — 0 adoptions in 3,250 trials. Three
stacked killers: (1) explore t_net≥1.5 (cost drag: null decile book
E[t_net]=−0.91; TRUE α=0.4 edge has t_net −0.23 but t_ic +1.67);
(2) confirm wall (BRAIN-008: t_net≥0.8 AND t_ic≥1.5) — killed 14/17 of
constant-edge survivors; (3) DSR killed the remaining 3. Also: small-cap
edges are structurally invisible (explore scans largemid only).

## RATIFIED DECISION (RECAL-1) — implement this
Information-gated ladder: explore gates on t_ic (headline t_ic≥2.0,
sensitivity 1.5); t_net demoted to reported diagnostic everywhere; the
cost hurdle moves to the implementation/sizing layer (turnover
engineering + posterior sizing ladder <60%→0×, 60-70→0.25×, 70-80→0.5×,
80-90→0.75×, >90→1×). NOTE: M1 showed confirm and DSR are independent
killers, so recalibrating explore alone will NOT restore end-to-end
adoption — you must propose the confirm/DSR treatment too (e.g. confirm
gates on t_ic with t_net diagnostic; DSR computed on a cost-aware sized
book rather than the raw decile book). Design it, justify it in the spec,
measure it.

## Rules of the game
- The SIMULATOR is a calibration instrument: you MAY iterate gate designs
  against it freely (ground truth is known; this is not data snooping).
  Real data may be touched ONLY ONCE, after the new ladder is frozen.
- Production pipeline stays byte-unchanged (assert_production_constants at
  every entry). New rule = a parameterized ruleset alongside frozen
  BRAIN-008, candidate name BRAIN-009. Seeded rng only (SEED_BASE+rep);
  no network in tests; every silent path raises; commit per stage with a
  verdict line.

## Step 1 — Pre-register RECAL-1 spec (commit BEFORE any grid read)
Spec doc in `Aegis module/docs/`: full new ladder (explore, confirm, DSR
input, sizing ladder), acceptance targets, and the one-shot real-replay
plan (Step 4). Acceptance targets: FDR at α=0 ≤ 5% (Wilson), end-to-end
P(adopt) at α=0.4/I2 ≥ 30% (stretch 50%), P(adopt) at α=0 ≤ 2%,
posterior map monotone and shipped.

## Step 2 — Re-grid on the new ladder
Cheap where banked: explore re-gating needs only (inj_t_net, inj_t_ic)
from the 3,250 banked rep files (sweep.py pattern). Downstream stages
(confirm scans for newly-graduating reps, DSR, PBO) need fresh runs — the
old grid only ran confirm for old-gate graduates. Reuse the chain
machinery: `scripts/run_m1_overnight.cmd [workers]` (idempotent rep files;
15 workers need ~18GB, use 4-8 on a loaded machine; LOCK the machine,
never sign out; spawn workers match `multiprocessing.spawn` in process
filters; keeper schtask M1GridKeeper exists, currently disabled). Use new
rep filenames (e.g. `rep_r1_*.json`) — never overwrite the BRAIN-008 grid.
If acceptance targets fail, iterate the ladder (each iteration = its own
committed spec delta + rerun), until targets pass or you can prove a
ceiling and report it.

## Step 3 — Posterior map on the winning ladder
Re-estimate with the pre-registered posterior machinery (posterior.py
buckets, Jeffreys add-half, monotonicity ship gate). Ship only if
monotone. Regenerate exhibits A/B.

## Step 4 — ONE-SHOT replay of the 179 real candidates (only after freeze)
Freeze the winning ladder (commit hash = the freeze record). Then replay
the banked explore scans of the 179 closed-search candidates under
BRAIN-009 exactly once, DSR at n_trials=179 (production deflation).
Survivors advance to confirm; confirm passes get a written proposal for
paper-lane seeding via the seed-a-lane skill — seeding is ATTENDED, Murat
flips flags; you never seed autonomously. No real money; forward clocks
only; no skill claims before 24 months (CANON). Do NOT run any new signal
families — search is closed at 179.

## Report (end of session)
1. New Tables 1-2 (FDR, power per α×design, stage attribution) vs old.
2. Acceptance targets: pass/fail each, with Wilson intervals.
3. Posterior map shipped y/n + exhibit B.
4. The resurrected list: which of the 179 pass BRAIN-009 explore, which
   pass confirm, with t_ic/t_net/DSR stats and the sizing-ladder band each
   would get. Seeding proposals only — no flags flipped.
5. Anything that still kills >50% of true edges end-to-end, named plainly.
