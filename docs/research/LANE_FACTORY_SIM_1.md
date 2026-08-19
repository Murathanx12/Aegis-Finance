# LANE-FACTORY-SIM-1 — mass simulated lanes on the PIT panel (design)

Registered 2026-08-19 evening. Origin: Murat's push to make "launch
lanes continuously" WORK — which it can, in silico, where sprawl is a
feature and the referee charges for every try. The live-fleet rejection
stands; this is the safe version of the same appetite.

## What it is

A simulator that runs THOUSANDS of lane rule-variants over the CRSP PIT
substrate (2013–2024, 6,894 PERMNOs, delistings included, per-name TAQ
costs where retired) exactly the way the real lanes run: monthly
rebalance cadence, cash accounting, cost charged both ways, formation
only on data public at formation time.

## The rule grammar (v1, frozen before any run)

universe filter × ranking signal (from finratio / JKP chars / IBES
revisions — the pulled substrate) × weighting (equal / inverse-vol /
rank) × rebalance cadence × winner-handling (trim-at-rebalance vs
+40-exempt-60td, from CONVEXITY-PRESERVATION-1) × risk overlay (none /
vol-target). Grammar is enumerable and DECLARED; m = the full
enumeration, not the subset that got run.

## Discipline (what makes mass search legal here)

- **SCREEN = BH-FDR(m = enumerated grammar)**; survivors go to
  **CONFIRM = Holm on a held-out slice** (time OR securities, declared
  per §60 — never chosen after looking).
- Every book reports net-of-cost, delisting-inclusive returns; §58
  n_effective in DATE BLOCKS; §64 power printed per comparison.
- Survivors do NOT become live lanes directly: they become CANDIDATES
  for the next quarterly generation window, each needing its own
  transport prereg + control twin (quarterly-generations rule 2).
- Corpse check against the 206-predictor net-negative library before
  any candidate is celebrated: rediscovering a known-dead signal is a
  test of the simulator, not a finding.

## The learning loop (Murat's NN + LLM reviewer, made concrete)

1. Simulator produces (rule, period) → outcome tuples at scale.
2. NN trains to predict lane outcomes from rule + regime features
   (risk outcomes first, §59 — they resolve; return labels carry their
   MDE).
3. LLM autopsies the NN's largest errors (existing gym autopsy→rule
   machinery) and proposes grammar extensions; every proposal enters as
   a HYPOTHESIS with declared priors, never as a silent grammar edit.
4. Graded nightly records (first grades 2026-08-21) join as forward
   validation the simulator can never contaminate.

## Cost note

Paper accounts cost ~nothing to run but are slow (calendar time).
Simulation costs compute but is fast. That asymmetry is the whole
argument: burn compute on history, spend calendar only on the few
survivors.

## Build order (machine jobs)

1. Book engine over crsp_dsf_* parquets (positions → daily NAV, costs,
   delistings) + tests against known-answer paths.
2. Grammar enumeration + registry (every variant gets an id; m is
   written down before run 1).
3. First sweep: the G2 candidates' historical twins (winner-exempt ×
   inverse-vol cells) — doubles as the §64 basis for the G2 preregs.
4. FDR/Holm harness reuse from `net_tournament`.

— design only; no book has been simulated as of this commit
