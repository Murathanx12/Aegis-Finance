# Session Post-Mortem — 2026-06-14 — Research phase closed, decisions applied to canon

## What this session did

Closed out the 2026-06-14 deep-research phase (two adversarially-verified runs)
and folded the decisions into the repo. No engine code touched. Committed the
research artifacts, resolved both open decisions, applied two canon updates, and
verified the deploy state against live `/api/health/full` rather than the
research session's stale narration.

## The correction that mattered (critic-by-default)

The research-session narration carried D2 as a live blocker: *"`ecb1be3` is on
`origin/main` but Railway serves `e759bf7`; the `predict_proba` WARNING keeps
firing; overlay observability unverified."* **All three were stale by the time
this session checked live state.** `/api/health/full` (via Optimus
`aegis_verified_state`) showed:

- Live deploy commit = `ecb1be3` (v0.2.0, up ~11h) — Railway auto-deploy fired,
  it just lagged past the research session's check window.
- `recent_warnings: []` — the `predict_proba` WARNING is gone.
- `overlay` block live: all 4 lanes `model_not_deployed`, `all_operational:false`,
  fresh `last_evaluated` stamps — the "loud, not silent" dark-state from the
  06-14 crash-overlay fix is working in prod.

So D2 needed **no `railway redeploy`**. The crash-overlay postmortem's
"Next #1: live-verify" is satisfied; T1's schedule/canary path is unblocked.
**Lesson: verify deploy claims against live health, not against a prior session's
write-up — auto-deploy lag makes "it didn't deploy" a false positive.**

## Decisions resolved (Murat)

- **D1 — LPPLS calibration → use the existing nested-MC fitter as-is.** Predictive
  skill was adversarially refuted twice; LPPLS ships descriptive-only regardless
  of calibration, so a quantile-regression rewrite would polish a signal we've
  pre-committed not to trust. Revisit only if forward Brier ever shows skill.
- **D2 — deploy gap → resolved by self-recovery** (above). No action needed.

## Canon updates applied (docs only)

1. **V2_GOALS A2 (LLM-lane firewall)** — added the empirical basis: the "profit
   mirage" (backtested LLM returns evaporate past the knowledge cutoff; lookahead
   inflates apparent predictive power by ~37% of the standalone effect; OOS the
   leakage is insignificant at p=0.033). *Sources: arXiv 2510.07920, 2512.23847.*
   The firewall is no longer held on faith — it is quantitatively backed.
2. **V2_GOALS A5 (psychohistory north star)** — reframed the crash thesis from
   **"time the crash"** to **"measure fragility and scale exposure as systemic
   stress rises."** Verified research: short-horizon crash *timing* has near-zero
   IC, and false positives force exit from compounding bull runs (worse for
   returns than the crashes themselves). This is the achievable, anti-goal-
   respecting form of the instinct — and it retroactively validates keeping the
   crash overlay disabled (no timing tool was ever worth arming).
3. **V2_ROADMAP** — D1/D2 marked RESOLVED with evidence; T1 sequence cell and
   recommended sequence updated (T2 → T3 → T1 → P1 #6).

## Next

1. **T2 — effective-N correction for registry DSR** (offline-verifiable; must land
   before P1 #6 because mirror/conviction lanes are correlated). Plan-first per
   Phase 3, await approval before code.
2. Then T3 (SOS recession indicator), then T1 (LPPLS descriptive flag), then
   P1 #6 (lane framework).
3. Follow-up research pass owed on the UNVERIFIED items (Section 4 data-ToS,
   Section 5 real-time signals, CSCV/slippage mechanics) before any ship asserted.

## Surprises / rejected

- **Surprise:** the entire "first build action" (unstick the deploy) had already
  resolved itself — the session's first real act was confirming that, not doing it.
- **Rejected:** editing the DEEP_RESEARCH decision doc to "correct" the D2 line —
  it's a dated point-in-time research artifact; the resolution belongs in the
  living roadmap + this postmortem, not retconned into the research record.
