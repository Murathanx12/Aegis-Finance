# Proposals — awaiting Murat's approve/kill

> Beyond-scope or judgment-required items surfaced during autonomous work.
> Format: What / Why now / Evidence / Cost / Risk to guardrails /
> Recommendation. Each should be decidable in under two minutes.

**Verdicts 2026-06-10 (Murat):**
- #1 replay-cache UTC TTL — **APPROVED**, queued for next grind session.
- #2 np.bool_ leak — **APPROVED**, ✅ landed 2026-06-10 (track-record-ui session).
- #3 intent gaps — **routed to the evolution loop** as its first candidates
  (recorded in V2_GOALS.md Goal 2); not hand-edits.
- #4 PI-scoped mypy — **APPROVED**, queued for next grind session.
- #5 F841 sweep — **APPROVED**, queued for next grind session.

---

## 1. Replay-cache UTC TTL fix (V1.x roadmap item, now evidence-backed)

**What:** Replace `datetime.utcnow()` (deprecated, naive) in `db.py`
`save_cached_replay` with `datetime.now(timezone.utc)`, and key the replay
cache by last-bar date instead of calendar `today()`.
**Why now:** Cycle-1 tz sweep confirmed the naive-UTC string is compared
against naive-local timestamps; on a non-UTC host the TTL is wrong by the
UTC offset. Already on the V2_ROADMAP as V1.x item 3 (~75 min).
**Evidence:** `db.py:393`, roadmap §1 V1.x.
**Cost:** ~1 hour + tests.
**Risk:** None to track record (replay cache only). Stored-format change
must be done with a parse-both-formats reader.
**Recommendation:** Approve — schedule as its own cycle.

## 2. `RegimeValidation.confirmed` leaks `np.bool_`

**What:** Cast numpy bools to Python bools at the dataclass boundary in
`regime_validator.py`.
**Why now:** Found while fixing E712 — `np.True_ is True` is False;
non-pydantic JSON encoders crash on np.bool_.
**Evidence:** grind log cycle 3; test asserts had to use truthiness.
**Cost:** 15 min.
**Risk:** None (type hygiene, value identical).
**Recommendation:** Approve.

## 3. Documented-intent gaps: `cov_lw` and `vix_deep_contango`

**What:** Two F841 findings are not dead code but unimplemented intent:
(a) `covariance_diagnostics` computes Ledoit-Wolf cov and never compares it
(docstring promises the comparison); (b) `regime_detector` reads the
`vix_deep_contango` threshold from config and never applies it — a
configured rule that does not exist.
**Why now:** Surfaced by the lint ratchet; left untouched because both
would change frozen-V1 engine behavior if "fixed".
**Evidence:** `covariance.py:270`, `regime_detector.py:55`.
**Cost:** (a) additive diagnostics field, ~30 min; (b) a rule change —
belongs to the Step #3 guarded evolution loop, NOT a hand-edit.
**Risk:** (b) is a live-rule change; hand-editing it would violate the
versioned-config discipline.
**Recommendation:** (a) approve as additive; (b) park as a registered
candidate for the evolution loop. Either way, delete the dead reads now if
you accept the lint debt staying visible until then.

## 4. mypy adoption (A3 follow-on)

**What:** Add mypy as dev-dep with a minimal config over
`backend/services/portfolio_intelligence/` only (the money-adjacent code),
ratchet errors the same way as ruff.
**Why now:** ruff ratchet landed (217→36); types are the next cheapest
bug-class. Full-repo mypy on 85 services would drown signal — scope to PI.
**Cost:** 1-2 cycles.
**Risk:** None (dev tooling).
**Recommendation:** Approve, PI-scope only.

## 5. Dead-code sweep behind the F841 residue

**What:** 32 unused-variable findings remain; ~13 in services. Most are
harmless dead assignments; each needs a 2-minute per-site check (some RHS
have side effects, two are item-3's intent gaps).
**Why now:** Keeps the ratchet moving toward zero.
**Cost:** 1 cycle.
**Risk:** Low; behavior-identical deletions only, tests prove.
**Recommendation:** Approve as a low-priority filler cycle.

---

## P-grind-2026-06-14a — Evolution loop Chunk 2: batch orchestrator over *binding* Phase-A params
**What:** Wrap `rule_evolution.evolve_param` in a batch runner over the survivorship-safe Phase-A param space, each proposal auto-deflated against the cumulative (effective-N) trial count, each recorded adopted/rejected — passing candidates STOP at PROPOSALS (never auto-adopt).
**Why now:** Chunk 1 landed clean (the guard provably bites). Chunk 2 is the next plan step.
**Evidence (this session):** The real-data run showed `rebalance_trigger_drift` does NOT bind for a *monthly-cadence* lane (all grid values → identical Sharpe 0.2703, sr_variance=0 → `no_effect`). **So Chunk 2 must pick params that actually bind:** `optimizer_params.lookback_days`/`min_observations`, sleeve %, or drift **only on a weekly-cadence lane**. Drift on monthly lanes is a dead param — skip it. Nested params (e.g. `optimizer_params.*`, `crash_overlay.*`) need a deep-merge in the override hook (currently top-level only).
**Cost:** 1–2 cycles. Real-data grids are ~10 min each (25-yr fetch + HRP); fine overnight, slow interactively — restrict to broad-ETF + macro universe (survivorship-safe + faster).
**Risk to guardrails:** Low if the never-auto-adopt + no-paper_nav rails hold (they're enforced in code). Phase-A scope only; individual-stock/smart-money lanes need the as-of-constituents + SEC layer (Phase B).
**Recommendation:** Approve as the next evolution cycle; pick a binding param first.

## P-grind-2026-06-14b — rules.py pct_change deprecation needs a config-versioned migration (NOT a silent fix)
**What:** `rules.py:151` uses `panel.pct_change()` with the deprecated default `fill_method='pad'`. Pandas will remove it; the naive fix (`fill_method=None`) changes NA handling → changes HRP input returns → **changes live weights**.
**Why now:** It's a future hard breakage, and it sits on the lane decision path (frozen-engine-adjacent).
**Evidence:** 30 FutureWarnings per replay run this session.
**Cost:** Small code, but it is a behavior change — must land as a SHA-versioned config change with a clean v2→v3 segment boundary (same discipline as Step #2), NOT a drive-by edit.
**Risk to guardrails:** Changing it silently would corrupt the track record's segment continuity. **Do NOT auto-fix.**
**Recommendation:** Murat schedules it as a deliberate config-version bump; until then it's a harmless warning.

## P-grind-2026-06-14c — Mark network-bound tests `slow` so the "fast" suite is actually fast
**What:** Several tests not marked `@pytest.mark.slow` hit yfinance/FRED/Kenneth-French (e.g. factor_model, real_analyzer, replay) — so `pytest -m "not slow"` runs 30+ min, not CLAUDE.md's "~4 min".
**Why now:** A multi-cycle grind/CI needs a genuinely fast precondition gate; the current one is impractical per-cycle.
**Evidence:** This session's `-m "not slow"` run exceeded 30 min and was abandoned as a gate; targeted PI runs (~5 min) were used instead.
**Cost:** 1 cycle to audit markers; pure test-metadata, no runtime code change.
**Risk to guardrails:** None (test-only).
**Recommendation:** Approve; restores a trustworthy fast gate. CLAUDE.md's test-timing note should be corrected too.
