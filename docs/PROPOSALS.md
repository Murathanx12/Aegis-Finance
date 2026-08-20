# Proposals — awaiting Murat's approve/kill

> Beyond-scope or judgment-required items surfaced during autonomous work.
> Format: What / Why now / Evidence / Cost / Risk to guardrails /
> Recommendation. Each should be decidable in under two minutes.

**Verdicts 2026-06-14 (Murat, /go consolidation+ship session):**
- **P-grind-2026-06-14a** (evolution-loop Chunk 2 batch orchestrator) —
  **APPROVED for a LATER session, not now.** Pick a *binding* param first (not
  monthly-cadence drift).
- **P-grind-2026-06-14b** (`rules.py` pct_change deprecation) — **FLAG-ONLY,
  PARKED.** Stays a harmless warning until it gets its **own config-versioned
  session** (v2→v3 segment boundary); never a silent/drive-by fix.
- **P-grind-2026-06-14c** (fast-suite gate) + **pytest-xdist** — **APPROVED**
  as the true fast-suite gate (parallel execution + the network-test `slow`
  marker audit; correct CLAUDE.md timing note).
- **Lockfile** (BACKLOG H2) — **logged as a deploy-env task**, to be generated
  with `pip freeze` on Railway when Murat next touches the deploy directly (a
  local freeze would mismatch prod). `lightgbm>=4.6.0` floor + CI `pip-audit`
  cover the CVE class meanwhile.

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

## P-grind-2026-08-19a — UNIVERSE-SURVIVAL-STRESS-1: CRSP PIT universe as the NET robustness axis
**What:** Second canonical panel from CRSP permanent identifiers (PERMNO): historical eligibility decided only from information at t, delisted names included, ticker as dated alias, frozen liquidity/exchange filters. Then the declared sensitivity: does the tournament's ARM RANKING move between the 2026-selected 182 and the PIT universe?
**Why now:** The NET panel's universe is a 2026 selection applied to 2013+ (declared in the amended prereg, which caps interpretation until this runs). EA/MRSH/XYZ/PXD proved identity is not static. External review round 3's top structural point.
**Evidence:** Amended prereg §Universe-selection limitation; WRDS CRSP entitled and psycopg2 route proven (port 9737 open).
**Cost:** 1–2 sessions (CRSP pull + panel build + sensitivity dataset; no tournament verdict — that stays signature-gated).
**Risk to guardrails:** None; new data, new registration, §61-capped.
**Recommendation:** Approve. If the arm ranking flips, "architecture alpha" was sample construction — a major finding either way.

## P-grind-2026-08-19b — EXPECTATION-BACKFILL-1: populate G4 so the tournament's +expectations rung exists
**What:** PIT expectations store: analyst estimate level/dispersion/revision direction+acceleration/staleness keyed on PUBLICATION timestamp (not period-end), earnings consensus-vs-actual, econ surprise. Feeds `g4_expectation.ExpectationRecord` at scale and materializes the NET ablation ladder's declared-ABSENT "+expectations" family.
**Why now:** G4 V1 is built but empty; the coverage audit says the ladder's floor is the data's. This is the highest-leverage data build in the queue — 4 of 13 daemon jobs block on event/expectation stores.
**Evidence:** `net_panel_v1_coverage.json` declares the family absent; daemon classification receipt names it as the blocker for EVENT-RESOLUTION-CURVE-1, INFORMATION-PROCESSING-GAP-1, REACTION-GAP-1, SEQUENCE-OF-EVIDENCE-1.
**Cost:** 1 session for earnings/estimates (yfinance/FMP/SEC already integrated); IBES via WRDS as the deeper rung.
**Risk to guardrails:** None; collector + store + PIT future-mutation test per house rule.
**Recommendation:** Approve — first build after the merge.

## P-grind-2026-08-19c — HISTORICAL-COST-REGIME-1: TAQ 2003+ regime-conditional spread curves
**What:** Pull quoted/effective spreads for the panel names across historical vol regimes (2008, 2020, calm years) from entitled taqm_2003..2026; fit spread-vs-VIX-regime curves per liquidity tier. Every NET verdict gains a stress-cost sensitivity instead of assuming today's 23 calm days price all history.
**Why now:** The current cost calibration is 23 days of ONE regime; adjudication B7 asked for regime-drift checks. "A count of survivors is a fact about the cost rate until it carries one" — and the rate is regime-dependent.
**Evidence:** Entitlement probe: taqm_2003..taqm_2026 SELECT OK. wct_* server-side NBBO join makes each year ~30 min.
**Cost:** ~1 session of WRDS queries, $0.
**Risk to guardrails:** None.
**Recommendation:** Approve.

## P-grind-2026-08-19d — NAV-RULES-DRIFT-MONITOR: daily replay reconciliation on the lanes
**What:** Read-only daily job: replay each lane's declared rules on its current positions/prices, diff vs authoritative paper_nav, alert when divergence exceeds a declared tolerance or jumps discretely. The 06-24/07-14/07-17/07-30/08-10 conviction jumps would each have been flagged the morning after instead of discovered in a forensic session eight weeks later.
**Why now:** The 14-pt gap investigation found FIVE accounting-jump days; every one aged silently.
**Evidence:** `decision_reconstruction_2026-08-19.json` (jump table); cross_arms_1.json (level divergence).
**Cost:** Small — the replay machinery exists (`lane_autopsy_cross_arms.py`); this is a daily thin wrapper + one health field.
**Risk to guardrails:** Read-only; needs the positions endpoint (on this branch) deployed.
**Recommendation:** Approve after merge.

## P-grind-2026-08-19e — Convexity outcome-family extension (CONVEXITY-CAPTURE + REENTRY-OPTION-VALUE)
**What:** Extend the episode outcome family before the trial runs: fraction of max favorable excursion captured, peak giveback, time underwater, recovery probability, right-tail truncation per arm; and a distinct REENTRY-OPTION-VALUE-1 descendant (trim-and-reenter on renewed confirmation) so exit experiments stop understating the option to return.
**Why now:** The episodes exist (23,011) and the executor's power audit says the contrast is answerable ~7× over (MDE 0.0045 vs declared 0.030) — the registration should ask richer questions while it's being signed anyway. Adding outcomes AFTER results would be §37.
**Evidence:** executor receipt 2026-08-19 (audit block); external review round 3 §9–10.
**Cost:** Half a session on the episode builder + registration text.
**Risk to guardrails:** None if amended pre-signature; forbidden after.
**Recommendation:** Approve — fold into the prereg draft before signing.

## P-grind-2026-08-19f — Four new research families from review round 3 (daemon `hypothesis_source` entries)
**What:** BELIEF-SHOCK-DECOMPOSITION-1 (LLM decomposes announcements into revenue/margin/guidance/... shock VECTOR; market prices each component — vs scalar sentiment) · LLM-PERCEPTION-vs-ALPHA-1 (every LLM feature scored twice: explains the immediate reaction vs predicts the post-first-executable-price residual) · DAY-NIGHT-INFORMATION-1 (decompose event paths: overnight gap/auction/first-30m/rest/d1-5/d6-20 — where does the learnable fraction live) · REACTION-RESIDUAL-1 (predict the JUSTIFIED immediate move; the gap is the candidate — extends REACTION-GAP-1, names it as parent).
**Why now:** Each has a 2025–26 literature seed (NBER w35093, RFS hhag062/hhag036, Mgmt Sci Siano), imports as `hypothesis_source` (§61 cap), and none collides with a corpse — checked against NEGATIVE_RESULTS and the queue (MODEL-DISAGREEMENT-TOPOLOGY folds into existing MODEL-DISAGREEMENT-1 as its state design, not a new trial).
**Evidence:** Review round 3 §research-directions; all four block on the same PIT event/expectation stores as proposal b.
**Cost:** Registration text now; runnable only after proposal b ships.
**Risk to guardrails:** None; all enter through pre-register-trial with corpses named.
**Recommendation:** Approve registrations; sequencing after EXPECTATION-BACKFILL-1.

## P-day-2026-08-19a — NAV date-stamp semantics (write-path, the gap's root cause)
**What:** `mark_lane_to_market` stamps NAV rows `date.today()` while `_get_current_prices` serves the last completed DAILY bar (usually the previous session's close at the 16:30 ET mark, behind a 15min–1hr cache). Fix: stamp the row with the price bar's own date (`series.index[-1]`); freshness canary moves to bar-date semantics. No rewrite of historical rows — the offset is uniform; annotate, don't rewrite.
**Why now:** This is THE mechanism behind the "unreconcilable" 14-point gap (corr(NAV_t, close_{t−1}) = 0.974). Every same-day comparison against market data is silently off by one day; `all_fresh` certifies one day more freshness than the data has.
**Evidence:** `docs/conviction_replay/GAP_RESOLUTION_2026-08-19.md` (mechanism located in code + measured).
**Cost:** Small diff, but on the SACRED write path — needs your explicit go + a config_version note so the semantics change is a documented boundary, not a silent restatement.
**Risk to guardrails:** CANON §5 — this is exactly the class that must not ship unattended; that is why it is a proposal.
**Recommendation:** Approve for the next attended session with lane-integrity-check before/after; until then all replays align NAV_t ↔ close_{t−1} (scripts updated).
**ADDED 2026-08-20 — DECIDED, and the first version of this note was WRONG.**

The note first written here claimed lane NAV and the benchmark were shifted together, so that lane-vs-SPY currently cancels and a partial fix would break it. That was an assumption, and it does not survive contact with the code. The facts, each checkable:

1. `mark_lane_to_market` stamps the NAV row `date.today()` while `_get_current_prices` serves the last COMPLETED daily bar — so NAV_t carries price_{t−1}.
2. `mark_lane_to_market` persists **only** the lane's NAV. No benchmark value is stored beside it (pinned by `test_benchmark_is_not_persisted_with_nav`).
3. `comparator._fetch_benchmark_returns` pulls SPY from yfinance indexed by **true bar date**. It does not share the lane's offset.
4. `real_analyzer._compute_beta_tracking` joins portfolio and benchmark on the **date index**.

**Therefore lane-vs-benchmark is ALREADY misaligned by one day, and the fix repairs it.** Lane-vs-lane cancels (every lane carries the same stamp); beta, tracking error and information ratio vs SPY do not. Measured on a known-answer world where true beta is exactly 1.5 (`test_nav_benchmark_alignment.py`): aligned recovers 1.5; a one-day offset collapses the measured beta below 0.3.

**DECISION: ship the lane-NAV stamp fix, and do NOT touch the benchmark fetch.** The danger runs opposite to the original note — the failure mode to guard against is someone "helpfully" shifting the benchmark to match, which reintroduces the misalignment the fix just removed (pinned by `test_shifting_the_benchmark_too_does_not_fix_it`).

Acceptance criteria before shipping:
1. `backend/tests/portfolio_intelligence/test_nav_benchmark_alignment.py` green (it is, 4/4) — it fails if a benchmark is ever persisted into `paper_nav`, which would change this whole analysis.
2. Enumerate every series joined to lane NAV for display or attribution and confirm each is bar-date stamped **after** the change; the benchmark already is.
3. Re-run beta/TE/IR on a lane before and after; beta vs SPY should move toward a plausible equity value and away from ~0. Measured, not asserted.
4. The `config_version` note records the boundary date so pre-fix and post-fix chart segments are never silently concatenated.
5. `lane-integrity-check` both sides; historical rows are annotated, never rewritten.

Rationale unchanged, and now better supported: this is the third temporal-alignment defect the programme has paid for (FRED publication-vs-reference date, collectors writing zeros, NAV stamping), and the first version of this very note was a *fourth* instance of the same reasoning error — assuming an alignment instead of measuring it.
