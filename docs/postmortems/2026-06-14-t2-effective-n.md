# Session Post-Mortem — 2026-06-14 — T2: effective-N for the registry DSR

## What shipped

The experiment registry now computes and reports an **effective independent-trial
count** (`N_eff`) alongside the raw cumulative trial count — the participation
ratio of the eigenvalues of the lane-return correlation matrix,
`N_eff = (Σλ)²/Σλ²` (= N for orthogonal streams, → 1 as they become collinear).

- `engine/validation/overfitting.py::effective_number_of_trials(returns_matrix)`
  — pure function; statuses `{ok, single_stream, insufficient_history, degenerate}`;
  on any non-ok status `n_eff` falls back to `float(n_streams)` so a degenerate
  estimate can never be *smaller* (looser).
- `experiment_registry.effective_independent_trials()` — pulls each
  `REFERENCE_LANE`'s `paper_nav`, aligns on common dates, converts to daily
  returns, returns the reported view. Defensive (no lanes → `no_data`).
- `evaluate_candidate` — **gate logic byte-unchanged.** It still deflates the DSR
  against the raw cumulative count. Added *reported-only* keys
  (`effective_independent_trials`, `expected_max_sharpe_at_raw_n`,
  `expected_max_sharpe_at_effective_n`).
- DB schema **v5**: additive nullable `rule_experiments.effective_trials`
  (idempotent, table-existence-guarded migration); threaded through
  `insert_experiment` and `record_trial`.
- `/api/pi/registry` now returns `cumulative_trials` (gate) **and**
  `effective_independent_trials` (reported, labelled non-gating), plus the
  per-row `effective_trials`.

## The decision that shaped it (Murat — option 2)

The research §2 prose said raw-count DSR is "too lenient." Tracing the actual
mechanics surfaced the opposite: `expected_max_sharpe` is **monotonically
increasing in N**, and `N_eff ≤ N_raw` always — so feeding N_eff would make the
DSR **more lenient**, not stricter. That direction ambiguity was escalated rather
than resolved silently (getting it wrong inverts an overfitting guard). Murat's
call: **N_eff is the correct LdP independent-trial estimate and we want it
computed, persisted, and exposed — but it must NEVER loosen the adoption gate
below the raw count**, because (a) the correlation matrix is meaningless at
current sample size, and (b) a too-lenient guard (false skill claim) is the
failure mode this project most needs to avoid. Raw count = strictness floor over
all rows; N_eff = reported diagnostic over lane streams only. Revisit feeding
N_eff to the gate only when lane history is long enough to be stable — as its own
registered decision.

## Verification (the measured numbers)

- **Gate invariance** (load-bearing): `evaluate_candidate`'s `dsr`, `survives`,
  `n_trials`, `expected_max_sharpe_h0`, `verdict` are byte-identical with and
  without lane streams present, and equal the pure raw-count
  `deflated_sharpe_from_returns`. N_eff cannot leak into the decision.
- **Pinning test**: adding `balanced-ew-control` as a ρ≈0.99 clone of balanced
  raises raw N by 1 while `N_eff` moves <0.2.
- **Unit**: orthogonal → N_eff≈N; identical → 1.0; insufficient history →
  fallback to N; degenerate (flat stream) → fallback; bounded [1, N].
- **18 new tests; full PI + overfitting + health suite: 425 passed (8 min).**

## Surprises / rejected

- **Surprise:** the migration test fixture (`test_v3_db_migrates_to_v4`) fakes a
  v3 db from `_SCHEMA_V1` alone, which lacks `rule_experiments` (it's created in
  the 2→3 migration). A bare `ALTER` in v5 would have crashed that path → made
  the v5 migration table-existence-guarded and column-idempotent.
- **Rejected:** computing a competing `dsr_at_effective_n` for the *gate* — it
  would either equal the raw-count DSR (when raw is the floor) or violate the
  floor; pointless. The honest reported view is N_eff itself + the expected-max
  bar under each N.
- **Rejected:** a DB column per moment/eigenvalue — `effective_trials` (the
  scalar) is the auditable figure; the rest is recomputable from `paper_nav`.

## Next

1. **T3 — SOS recession indicator** (FRED `IURSA`; `compute_sos_signal`; shown
   next to Sahm with lag-to-onset framing; no leading-indicator language).
   Offline-verifiable, small. Plan-first per Phase 3.
2. **T1 — LPPLS descriptive flag** (D1: existing nested-MC fitter; never arms a
   lane; forward Brier vs climatology).
3. **P1 #6 — lane framework** (now unblocked; correlated lanes reflected in the
   reported N_eff view).
