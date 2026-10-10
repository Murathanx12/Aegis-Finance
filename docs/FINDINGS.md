# FINDINGS — Adversarial self-review of V3 Chunks 1–6

## 2026-10-10 — bounded news trace and original-record replay

The isolated PRODUCT_EXPERIMENT examination is recorded in
[DECISION_TRACE_2026-10-10.md](DECISION_TRACE_2026-10-10.md) and
[PAIRED_RESULTS_2026-10-10.md](PAIRED_RESULTS_2026-10-10.md).
Fifty-one original source forecasts reproduce exactly; 34 resolved outcomes
score Brier 0.27176 versus the same-row p50 loss 0.25. Twenty-session rows remain
pending. Analyst inputs affect actual isolated forecast/plan consumers; source
news remains excluded from expected return by design, and historical earned
news trusts of zero cause no paired portfolio effect. No alpha claim follows.

Independent review rejected the first regrade check because the resolver passes
already-resolved rows through. Copies now clear resolution fields first, with a
wrong-recorded-outcome regression and 34 genuinely recomputed matches. Trace
review required correct executed horizon labels and explicit retention of the
existing without-analyst decision-story replay mismatch. Release verification
caught the lab firewall violation: the offline extractor belongs under ft_lab,
and the live-path import guard stays unchanged. Original private receipts and
failures are retained, not rewritten as successes. The fleet grade-chain gap,
Qwen resource/quality gates and activation boundaries remain component-specific.

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

## 2026-10-10 erratum: decision-ledger grading window

The decision grader previously fetched one panel from the earliest due decision through
the grading day, then used each column's first and last non-null prices. It ignored each
row's frozen as-of and expiry, so overlapping decisions could inherit another row's
entry price and an expired decision could receive a later recovery. A 21-session offline
reproduction yielded +20% recorded excess where each frozen-window excess was -10%; this
is a grader defect, not evidence of skill. Missing benchmark closes could also leave a
raw SCORED row without a valid excess.

Future `decision_close_endpoints/2` scores require exact row endpoints for the asset and
SPY, a complete close after the expiry date, and valid ordered price dates and positive
finite closes. Missing evidence remains unpriceable. PROBE and E[r] blend learning gates
ignore unversioned earlier scores; prior ledger, fills and NAV are not rewritten. Those
historical grades remain unverified until a separate dated disposition and may not be
used as new positive learning evidence.

Follow-up: finite positive endpoint prices can still overflow a close ratio, and two
infinite returns can yield a NaN excess. The grader now refuses nonfinite computed
returns before appending; direct learning gates and E[r] reject malformed numeric
grades even if a row carries the new rule marker. Existing rows remain untouched.

## 2026-10-10 — beta continuation examinations

PR #20's exact head was independently reviewed and merged as `86fc8b0e`.
Its main CI passed and the deployed API reports that exact commit, healthy
jobs and fresh NAVs. The registry and recorded lane histories match the
pre-merge receipt; refreshed comparator quotes are a separate changing field.
Publication recovery remains closed.

The frozen analyst-ablation mismatch came from decision-story replay omitting
the planner's 10% fallback cap. The reviewed replay repair restores that cap
without changing the planner, original forecasts or books. Three actual
isolated replays match and send zero orders. Old mismatch evidence is retained.

The independently reviewed census separates runtime forecasts (66,546 unique)
from the isolated cloud snapshot (736), including 112 exact immutable overlaps.
Outcome-present counts include replay and are not certified forward results.
Protected, malformed, conflicting, bounded and inaccessible sources remain
explicit; the census is incomplete and does not itself authorize grading.

The repaired news inspection admits only eligible, nonvoid, nonquarantined
outcomes with valid chronology. Legacy day-only resolutions must precede the
cutoff's UTC day. Cached interpretations remain `BOUND_ONLY`, not semantic
certification. A stored unsupported CACC settlement-date claim is rejected.
The actual retrospective learning consumer retains zero trust; the news-to-
expected-return bridge remains unverified and no live flag was enabled.

A private catch-up reproduces 22 newly graded campaign records, then zero on
rerun, preserving all original immutable inputs. Its exact price windows and
outcomes were independently reproduced. General catch-up guards still require
repair; canonical runtime commits remain inactive until exact identity and
file pins are checked inside the existing writer lock. Missing DBRG and WBD
windows remain unknown rather than zero.

The release suite recorded 14,460 passed, 74 skipped, 126 deselected and two
failures: missing news-validator guard enrollment and missing offline-consumer
classification. Their focused repair is under independent review; a failed
release receipt is not replaced by focused success. NN tests passed 86; FT
tests passed 99. Required release checks still bind.

Read-only fleet diagnostics distinguish five matching position states from
grades ending October 8, and an inaccessible credential-invalid sixth role.
The existing browser owner remains unchanged and its reader is advancing.
Monday competition approval, authentic WLS membership, current Terminal rules
and actual fills remain separate facts. The owner reports the application
submitted, with approval/details pending Monday.

Follow-through at approximately20:45SGT: the two release enrollment repairs
passed independent mutation/actual-consumer review. A frozen CI-simulated full
backend rerun is in progress; the earlier failed receipt is retained. The
one-line health-page presentation fix exposes ALIVE service details by default,
including due-unresolved grading debt. Independent static component rendering
approved the exact change; deployment and per-service restart proof are not
yet observed.

Catch-up writer cycle1 passed the original33 checks but failed seven new
checks in four material boundary groups: voided markers, non-session price
rows, examination output aliases and an expiring owner lease. Its accepted
full private-ledger artifact still proves22 grades/zero rerun and unchanged
immutable/skipped rows. Runtime ledger appends invalidate the old complete-file
authority pin; no runtime write occurred. Final cycle2 is isolated and under
independent review, with46 focused passes claimed by the builder.

The parked R15 catalyst candidate reproduces its existing two P2 findings
despite84 focused passes and remains inactive. Backup archive headers3232
are unclassified; an unsupported fallback context-only label is corrected in
a separate receipt without altering the original or reading new member values.
ATLAS's inactive discussion draft passed independent weight/input review;
supplemental book/engine/member pins match and10 primary-source captures are
portable. Thirteen archiver access failures remain explicit, not empty or
semantically certified. The measured-results index retains original horizon-
specific scores and the actual zero-trust/unchanged-news-plan observations.

Follow-through, October 11 at approximately 02:15 SGT: the canonical catch-up
has now graded the exact 22 original records once, with zero on rerun. A later
native expected-return fit consumed the updates; fitted inputs changed without
forcing changed weights or orders. Five fleet outcomes were graded once and
the subsequent five-account reconciliation found no discrepancies. Original
fields, NAVs, histories and activation gates remain intact.

PRs #21–25 passed their required release checks and exact CI. The latest
production commit `f6e37899` passed live health, fresh NAV, registry and every
paper-lane history canary. The opt-in source guards leave the frozen legacy
news contract unchanged; real strict semantic admission remains unobserved.
The scheduled digest and actual zero-trust shadow consumer are separate facts.

The final manual reader-reload repair passed 83 private checks, but the first
live read-only helper invocation refused `UNKNOWN census` before opening
process handles, producing a context or changing runtime state. The operator
is parked under the repair cap. A fresh status still reports reading, with
32 successful pages in ten minutes and 202 in an hour. This does not certify
future continuous uptime. The new-day learning-cache invocation likewise
refused its fresh memory preflight before an audit or cache write.

The acceptance report's generic queue join erased six unmapped rows' evidence
fields. The corrected matrix retains explicit parked/deferred/preview evidence
for every row, and preserves the prior bytes privately. ATLAS now compares
the original v1/v2 records with its inactive v3 proposal; the v1 field named
`frozen_utc` does not override its recorded `DRAFT_NOT_FROZEN` state.
