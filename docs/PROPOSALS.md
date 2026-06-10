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
