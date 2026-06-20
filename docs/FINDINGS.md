# FINDINGS — Adversarial self-review of V3 Chunks 1–6

**Date:** 2026-06-20 (AFK verify/harden session) · **Scope:** code committed in Chunks 1–6.
**Method:** red-team for *silent fragility* — swallowed exceptions, NaN propagation,
degenerate input producing plausible-but-wrong output, and bypasses of the safety claims.

Legend: 🔴 fixed this session · 🟡 known gap, test-pinned, hardening → backlog · ⚪ noted/minor.

---

## Ranked findings

### 🔴 F1 — `exposure_multiplier(NaN)` returned `status="ok"` with `multiplier=NaN`
**Severity: high (silent-wrong).** A NaN fragility composite produced a NaN multiplier
reported as healthy. A NaN composite is reachable upstream (see F7). Rotation accidentally
no-ops it (`NaN < 1.0` is False → full exposure), but any consumer reading the multiplier
gets garbage-as-ok.
**Fix:** NaN composite now treated like `None` → `status="unavailable"`, `multiplier=None`.
Commit `fix(fragility): exposure_multiplier returns unavailable on NaN composite`. Test:
`test_nan_composite_unavailable` (fails before, passes after).

### 🔴 F2 — `score_forward_ic` reported `status="scored"` on an all-NaN panel
**Severity: medium (silent-degenerate).** The sufficiency gate counted raw rows, so a big
panel whose factor/forward-returns were all NaN passed the gate and returned
`status="scored"` with an empty IC (`n_periods=0`) — a grade it didn't have.
**Fix:** drop NaN factor/fwd rows before the gate → degenerate panel correctly reports
`insufficient_history`. Commit `fix(forward_ic): drop NaN rows before the sufficiency gate`.
Test: `test_all_nan_forward_returns_insufficient`.

### 🟡 F3 — feature-hash guard is bypassed when the sidecar is absent
**Severity: medium (safety-claim boundary).** The guard rejects a tampered model **only when
the sidecar exists** (proven: `test_feature_hash_mismatch_fails_loud`). Delete the sidecar and
a model with a tampered feature contract loads as trained via the legacy back-compat path.
**Status:** behavior pinned by `test_sidecar_deletion_bypasses_guard_known_gap`. Hardening
(an opt-in strict "no sidecar → refuse" mode) is a **change**, not a fix → backlog B4.
The safety claim therefore holds as: *"rejects a tampered model **when provenance is
present**"* — true, and verified.

### 🟡 F4 — `require_sizing_grade(None)` raises `AttributeError`, not `DataIntegrityError`
**Severity: low.** Passing `None`/non-str as source crashes in `.lower()`. It is still *loud*
(raises), so the "fails loud" claim holds, but the exception type is ungraceful.
**Status:** hardening (`get_guarantees` coerces non-str → directional) is a behavior change →
backlog B3. The exhaustive bypass test (`TestSizingGradeBypassAttempts`) confirms every
*registered* directional source raises `DataIntegrityError`.

### 🟡 F5 — `require_sizing_grade("sharadar")` passes on the registry alone
**Severity: medium (defense-in-depth).** The registry says sharadar is sizing-grade, but **no
Sharadar adapter exists yet** — a caller using only `require_sizing_grade` (without also
running `survivorship_probe` + `assert_survivorship_safe`) could believe it has sizing data it
cannot actually fetch. The two-gate design (registry gate + empirical probe) covers this, but
the contract isn't enforced in one call. → backlog B5 (make the registry gate also check
source availability, or document the mandatory two-gate contract).

### ⚪ F6 — `survivorship_probe` `len(s)` is outside the try
**Severity: low (edge).** Only the `fetch_history` call is wrapped; if a fetcher returns a
non-sized object (e.g. a scalar), `len(s)` raises `TypeError` (loud, not silent). → backlog B10.

### 🟡 F7 — upstream: `compute_fragility_index` can yield a NaN composite (root cause of F1)
**Severity: medium — but OUT OF SCOPE for fixes (pre-existing, not Chunk 1–6 code).** If any
input normalizes to NaN, `np.mean(norms)` returns NaN because `_clip01(NaN)` is NaN and the
`available` flag (`normalized is not None`) treats NaN as available. F1 hardened the consumer;
the producer should also drop NaN norms. → backlog B1 (HIGH).

### 🟡 F8 — `data_grade` stamp does not reach the candidate verdict
**Severity: medium.** `ReplayResult` and `forward_ic_scorecard` are stamped, but the
`evaluate_candidate` / `rule_evolution` DSR/PBO **verdict** carries no `data_grade` — a verdict
from a free-data (directional) backtest reads as gradeless. → backlog B2 (also Track 2). These
are pre-existing modules, so propagation is a change, not a fix.

### ⚪ F9 — rotator with an equity-only universe stays fully invested at high fragility
**Severity: informational (correct-by-construction).** With no defensive sleeve present, there
is nowhere to rotate, so high fragility leaves equity at 1.0. Pinned by
`test_single_asset_equity_only`. Not wrong, but surprising — documented.

---

## Checked and found CLEAN (no action)
- `inverse_vol_weights` / `crossasset_target_weights` on zero-vol, all-NaN, empty, mixed-NaN →
  return `{}` or drop the bad column; never a NaN/negative weight (property + degenerate tests).
- `exposure_multiplier` with a misconfigured `neutral >= high` → no divide-by-zero (the linear
  branch is unreachable in that case).
- `forward_ic.build_signal_panel` reads factors via `get_series_observable` (leak-free) and uses
  forward prices only as the realized label (see LOOKAHEAD_AUDIT F-paths).
- `replay._get_crash_prob_as_of` fix is fail-safe: returns `None` (skips the date) when the
  model's features aren't all present, rather than feeding a mismatched matrix.
- Crash-model load fails loud (sets `is_trained=False`) on feature-hash mismatch → overlay stays
  `model_not_deployed` rather than serving a broken model.

## Safety-claim verdicts (the two the brief named)
1. **"`require_sizing_grade` fails loud on every directional-only path"** — ✅ TRUE for every
   registered directional source + unknown sources (parametrized bypass tests). Caveat F4 (None
   input → AttributeError, still loud) and F5 (registry-only confidence) noted.
2. **"the feature-hash guard rejects a tampered model"** — ✅ TRUE when the sidecar is present
   (proven). ⚠️ bypassed when the sidecar is deleted (F3, pinned + backlogged).
