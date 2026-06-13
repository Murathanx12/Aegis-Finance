# Session Post-Mortem — 2026-06-14 — Crash overlay was structurally dark (P0)

## The finding (bigger than the reported symptom)

`/api/health/full` carried a recurring WARNING every daily check:
`CrashPredictor.predict_proba() missing 1 required positional argument:
'features'`. The reported diagnosis was "a call-signature regression since the
06-10 deploy." Tracing it turned up a deeper, two-cause failure — the overlay
has **never** been operational in production, on any config version:

1. **Wrong call site.** `reference_engine._get_crash_prob()` called
   `predict_proba()` with no args and expected a dict with `"crash_3m"`; the
   real signature is `predict_proba(features, "3m") -> np.ndarray`. The replay
   path (`replay._get_crash_prob_as_of`) always did it correctly. `git log -S`
   dates the broken call to the first PI commit `116d1e5` — it never worked.
2. **No model in prod.** `crash_model.pkl` is gitignored (`*.pkl`,
   `.gitignore:14`) and was never baked into the Railway image. Confirmed live:
   `GET /api/crash/prediction` → `status: model_not_trained`. So even with the
   call fixed, prod has nothing to evaluate.

A third, related honesty bug: `config.py:29` claimed "MODEL_DIR are immutable,
version-controlled, and baked into the image" — false for the `.pkl`. Fixed.

## The decision (Murat) — fix honestly, do NOT arm

The overlay is a risk control the lane mandates assume is active. Two
guardrail-driven choices were rejected and one adopted:

- **Rejected — `git add -f` the .pkl to arm the overlay now.** Two violations:
  (a) arming a risk control on day 6 changes the strategy of in-flight,
  pre-registered lanes (breaks TRIAL-001's pre-registration); (b) it ships an
  unprovenanced binary whose training window can't be certified leakage-safe —
  the one property the project exists to guarantee.
- **Rejected — train-on-boot.** Non-deterministic, re-trains per redeploy, no
  audit trail; destroys the forward/uncopyable property of the record.
- **Adopted — fix the bug, keep the overlay off, make the dark state loud,**
  and relabel honestly. Arm later only on NEW pre-registered lanes with a
  version-controlled, provenance-documented model.

## What shipped

- **Call site fixed** (`_evaluate_crash_overlay`): mirrors the live dashboard
  path — shared predictor, current features via `build_feature_matrix`, correct
  `predict_proba(features, "3m")`. Returns `(prob, status)` where status ∈
  `{evaluated, override, model_not_deployed, feature_unavailable,
  predict_error}`.
- **De-spammed:** `model_not_deployed` is logged **once per process** at INFO
  (it is always visible in health regardless); a genuine error with a model
  PRESENT still WARNs every time.
- **Loud, not silent:** every daily check writes a `crash_overlay_eval` audit
  row per lane (`status, crash_prob_3m, armed, threshold`).
  `scheduler.overlay_status()` reads the latest row per lane;
  `/api/health/full` gained an `overlay` block with an `all_operational`
  canary — when false, the overlay engine is dark. A dead overlay can no
  longer hide for days.
- **`config.py:29` comment corrected** to state the `.pkl` is gitignored and
  prod has no model.
- **Tests:** `test_crash_overlay_observability.py` (7) — no-model returns a
  status not an exception; the call-signature regression guard (predict_proba
  must receive a features DataFrame + "3m"); the daily check persists the eval
  row; the `all_operational` canary trips when dark. Updated 4 existing patch
  sites from `_get_crash_prob` → `_evaluate_crash_overlay`. Full PI suite:
  **377 passed, 2 deselected.**

## Contamination assessment (track record)

- **Window:** inception 2026-06-08 → 2026-06-14, all four lanes, config v1 AND
  v2. The overlay was dormant the entire time.
- **Would it have armed?** Cannot be computed in prod (no model). But the tape
  was calm — lanes +0.13%…+0.42%, no SPY −20% — and thresholds are 0.25–0.40
  3m crash prob. In a quiet regime the overlay would almost certainly have been
  dormant *even if operational*. The contamination is therefore **theoretical,
  not realized**: had the overlay worked, it would very likely have cut nothing
  over this window.
- **Verdict — the record stands; NO segment boundary.** A config-note boundary
  marks a *change in strategy*. Nothing changed: the overlay was never on, and
  we are deliberately keeping it off on these lanes. Relabeling it as "no crash
  protection since inception" is documentation, not a strategy change, so it
  does not warrant a new segment (which would falsely imply the lanes' behavior
  shifted on 06-14). This is the TRACK_RECORD_POLICY call — recorded here for
  Murat. *(Murat to confirm.)*

## TRIAL-001 impact — valid, annotated

Both HRP (`balanced`) and EW (`balanced-ew-control`) arms ran with the overlay
equally dark. The overlay is a shared control applied identically to both; the
trial isolates HRP-vs-EW on the equity sleeve, which the overlay never touches.
So the primary metric (relative net Sharpe) is **unbiased**. Not a
contamination-clause defect (that clause is for per-lane data/accounting
defects; this is an engine-wide dormant feature, symmetric across arms). No
window extension. Annotation appended to `docs/TRIALS/TRIAL-001-hrp-vs-ew.md`.

## Surprises / rejected

- **Surprise:** the WARNING looked like a 06-10 regression; it was a
  since-inception structural gap masked by a swallowed exception — exactly the
  third silent-fallback bug after `mark_all_lanes` and rebalance-positions. The
  pattern (try/except that hides a dead subsystem) is the recurring enemy; the
  fix template is now "persist a status row + a health canary," not just "fix
  the call."
- **Rejected:** caching `_evaluate_crash_overlay` across the 4 per-lane calls
  in a cycle — the data layer already caches fetches, and in prod it
  short-circuits at `model_not_deployed` before any fetch. Not worth the state.

## Next

1. Live-verify after deploy: next daily check writes `crash_overlay_eval` rows;
   `/api/health/full` `overlay.all_operational == false` with per-lane
   `model_not_deployed`; the per-cycle WARNING is gone (replaced by one INFO).
2. Then P1 #6 (lane framework) — unblocked once this ships clean.
3. Backlog (NOT this session): provenance-documented crash model + new
   pre-registered overlay lanes, if/when the overlay is to be armed.
