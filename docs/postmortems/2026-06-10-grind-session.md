# Grind Session — 2026-06-10 (autonomous, Murat away)

> SESSION SUMMARY is written at the top when the session ends. Cycles below, newest last.

## SESSION SUMMARY

**5 cycles, 5 commits pushed to `lab/autonomous-rd`:**
1. `5dff6af` — silent degradation made loud (real_analyzer beta loop
   isolation, sector-map + replay-universe + shutdown logging); flaky
   `test_monotonic_horizons` rewritten against the enforced contract.
2. `6b0d4b6` — optimizer invariant/property tests (+12); found & fixed
   `compare_methods` TypeError that killed the optimizer-comparison
   endpoint on every call.
3. `9b4c83a` — ruff ratchet 217 → 36; duplicate `tail_risk` config key
   (F601) removed; F821 annotation fix; `ruff.toml` pins the rule set.
4. `5323758` — `docs/TRACK_RECORD_POLICY.md` + shared `MethodologyBanner`;
   replay/compare pages relabeled methodology, "Performance Metrics" →
   "Backtested Metrics".
5. (this commit) — `docs/PROPOSALS.md` (5 entries) + session summary.

**Measured deltas:**
- Tests: 2339 → 2356 collected (+15 new, 2 rewritten); full fast suite
  **2344 passed / 0 failed** (mid-session gate; final gate in this commit's
  log line below).
- Ruff errors: **217 → 36** (config pinned; floor recorded).
- Coverage (high-risk math set): portfolio_optimizer **58% → 72%**,
  target-set 75% → 80%.
- Bugs: **6 fixed** (beta-loop abort, 3 silent swallows, compare_methods
  crash, duplicate config key), **4 documented-not-built** (replay-cache
  UTC TTL, np.bool_ leak, cov_lw gap, deep_contango gap — see
  PROPOSALS.md), **~25 sweep candidates rejected** with reasons (cycle-1
  log) so they aren't re-litigated.

**Abandoned/dead-ends:** none hit the 3-attempt thrash guard. One
self-inflicted break (E712 → `is True` on np.bool_) caught by targeted
rerun within the same cycle.

**PROPOSALS.md added (titles):** replay-cache UTC TTL fix; np.bool_
dataclass leak; documented-intent gaps (cov_lw / vix_deep_contango); mypy
adoption (PI-scoped); F841 dead-code sweep.

**Top 3 next actions for Murat (priority order):**
1. **Trigger the Railway redeploy** (dashboard or `railway up`) — commits
   `6ed841a..5323758` are waiting; until then the history endpoint stub is
   what's live and `paper_nav` rows remain unverifiable. Ideally enable
   auto-deploy from `lab/autonomous-rd`.
2. After redeploy: verify `/health/scheduler` shows `nav.all_fresh: true`
   and `/api/pi/reference/balanced/history?period=ALL` returns real NAV
   rows since 2026-06-08 — closes the "are rows landing?" question.
3. Approve/kill the 5 PROPOSALS.md entries (each <2 min) and write the
   missing `docs/V2_GOALS.md` "Murat's additions" section that go.md
   expects.

**Needs Murat specifically:** the redeploy (item 1); V2_GOALS.md; proposal
verdicts. No write-path patches were needed this session — the track
record was never touched.

**Final gate: full fast suite 2356 passed / 0 failed (15:01).** Tree green,
pushed, clean.

---

## Cycle log

### Cycle 1 — A1 bug hunt (swallowed exceptions / None / tz / mutable defaults)

**Method:** 3 parallel sweep agents over `backend/services/` + `backend/routers/`
(tz-naive datetimes; unhandled None/empty-series; mutable defaults + float eq +
swallowed exceptions). ~30 candidates returned; most did NOT survive manual
verification — lesson: pattern-grep findings need code-level confirmation
before they count as bugs.

**Confirmed + fixed (with tests, `test_degradation_logging.py`):**
1. `real_analyzer.py` beta loop — one ticker's failed factor decomposition
   aborted ALL remaining tickers silently; concentration flags then computed
   on a partial beta_map presented as complete. Extracted `_compute_beta_map`
   with per-ticker isolation + warning per drop.
2. `real_analyzer._get_sector_map` — config-load failure silently produced a
   blank/incomplete sector breakdown (reads as "no exposure"). Now warns.
3. `replay._get_ticker_universe_prices` — fetch failure silently shrank the
   replay universe (backtest looks valid, computed from partial data). Now
   logs every dropped ticker.
4. `main.py` lifespan — scheduler shutdown swallow now logs.

**Verified-NOT-bugs (recorded so they aren't re-litigated):**
- `market_dashboard.py:83` / `stock.py:439` YTD "IndexError" — guarded by the
  inline conditional; agent misread evaluation order.
- `earnings_intelligence.py:132` zero-denominator — enclosing try/except
  degrades to missing fields + debug log; acceptable.
- `providers/base.py:156` `capabilities: list = []` — every concrete provider
  overrides it; nothing mutates; latent only. Candidate for a `ClassVar`
  annotation in the ruff cycle, not a live bug.
- tz-naive comparisons in PI (`scheduler._hourly_mtm` cache check etc.) —
  all PI timestamps written naive from the same clock (Railway=UTC), so
  comparisons stay coherent; the one risky compare is inside try/except that
  degrades to "run MTM anyway". Real item extracted: `db.py:393` uses
  deprecated naive `utcnow()` for replay-cache `computed_at` — ties into the
  V1.x "replay cache UTC TTL" roadmap item; do as its own cycle, not a
  drive-by (changing the stored format affects TTL parsing).

**Deferred (logged, not built):** `cache._disk_get` corruption swallow →
debug-log candidate; replay-cache UTC TTL cycle.

**Red-suite fix (VERIFY found it):** full fast suite came back
1 failed / 2339 passed — `test_crash_calibration::test_monotonic_horizons`.
Flaky by construction: asserted monotonicity on RAW per-horizon
`predict_proba` outputs (+0.05 slack) using live yfinance/FRED data; the
per-horizon models are independent and can legitimately cross. The engine
contract is `predict_all_horizons` (post-processed, enforced at
`crash_model.py:439`). Rewrote the test against the production path with
strict assertions + [0,1] range checks. Passed isolated before AND after —
the lesson: a live-data test of an unenforced property WILL flake; test the
enforced contract.

**Measured:** suite 2339 passed/1 failed → fix applied; affected-module
targeted runs green (51 + 3 + 2). New tests: +3 (degradation logging).

### Cycle 2 — A2 coverage on highest-risk math (invariant + property tests)

**Selected:** portfolio_optimizer.py was the weakest high-risk module
(58% vs covariance 92%, crash_model 81%). Added
`test_optimizer_invariants.py`: long-only/fully-invested/subset invariants
for all four optimizers (offline, `_fetch_returns` patched with synthetic
correlated returns), hypothesis property tests for
`adjust_weights_for_liquidity` (never invents weight, conserves sum when a
liquid asset survives, hard-floors thin names), and a 200-example property
test that `predict_all_horizons` orders ANY raw per-horizon outputs.

**Bug found by the new tests (then fixed):** `_recommend_method` raised
`TypeError: '>' not supported between NoneType and int` — equal_weight
fallback always carries `sharpe_ratio: None`, and `compare_methods` always
includes equal_weight, so **every** `compare_methods` call (router:
`portfolio.py:778`, the optimizer-comparison endpoint) died at the
recommendation step. `.get(key, -999)` does not protect against an explicit
None value. Lesson: invariant tests on fallback paths find bugs the happy-path
tests never touch; also nothing was testing the endpoint's service function
end-to-end offline.

**Measured:** portfolio_optimizer 58% → 72% (Miss 102 → 69); target-set
total 75% → 80%. +12 tests (82 in the affected set, all green).
pytest-cov installed (dev-dep; license MIT, standard tooling).

**Deferred:** crash_model 81% — remaining misses are training/IO paths;
diminishing returns vs the optimizer gap. `_fetch_returns` (54-89) is
network-only by design — left uncovered deliberately.

### Cycle 3 — A3 static hygiene ratchet (ruff)

**Baseline 217 errors → 36** (32 F841 unused-variable, 4 E741 ambiguous
names; the remainder needs per-site judgment, not autofix). `ruff.toml`
added pinning the rule set; the count never rises.

**Real bugs found by lint:**
- `config.py` had a duplicate `"tail_risk"` key (F601) — first block
  silently dead. Both blocks were byte-identical, so deleting one is
  provably behavior-identical. (If they had differed, the fix would have
  been to delete the LATER one to preserve runtime behavior — last key wins.)
- `routers/portfolio.py` annotation referenced undefined `pandas` (F821) —
  string annotation so dormant, fixed with TYPE_CHECKING import.
- 173 unused imports auto-fixed after diff review; the 4 ruff would NOT
  autofix were availability probes (`pypfopt`, `ta`) — annotated
  `# noqa: F401` instead. Verified via full pytest collection (2356 tests,
  zero import errors) + backend.main import smoke.

**Self-inflicted + caught:** "fixed" two E712 test asserts to `is True` —
broke them, because `validate_regime(...).confirmed` is `np.bool_`, and
`np.True_ is True` is False. Correct form is truthiness. **Side-find:**
`RegimeValidation.confirmed` leaks `np.bool_` into a dataclass (JSON
serialization hazard with non-pydantic encoders) — logged, not fixed
(descriptive service, low stakes, engine frozen).

**Documented-intent gaps surfaced by F841 (logged, NOT built — frozen
engine):**
- `covariance.covariance_diagnostics` computes Ledoit-Wolf cov (`cov_lw`)
  and never uses it, while the docstring promises an LW comparison.
- `regime_detector` reads `vix_deep_contango` threshold from config and
  never applies it — a configured rule that does not exist in the logic.
Both are evolution-loop candidates (Step #3), not hand-edits.

**Measured:** ruff 217 → 36; targeted tests 178 + 520 green; collection
2356 tests clean. mypy deferred to a future cycle (out of budget).

**Cycle-2 VERIFY suite landed mid-cycle-4: 2344 passed, 0 failed** —
tree confirmed green including the cycle-1 flaky-test fix.

### Cycle 4 — B4: track-record policy + methodology relabeling (P0 #4 prep)

**Shipped `docs/TRACK_RECORD_POLICY.md`:** live forward NAV (`paper_nav`,
inception 2026-06-08) is the ONLY thing allowed to be called "track
record"; replay/compare pages are methodology simulations and must carry
the shared banner; exact copy lives in the policy doc; rules for future
pages (backtest numbers never use "performance" unqualified; unmeasured
signals labeled descriptive).

**Frontend:** new shared `MethodologyBanner` component replaces three
copy-pasted survivorship disclaimers (PI landing, /reference, /compare).
Retitled: reference page → "… — Methodology Backtest" with "not the live
track record" subtitle; compare page → "Compare Portfolios — Methodology
(Backtested)"; "Performance Metrics" table → "Backtested Metrics".

**Why labels-only:** the live equity-curve page (P0 #2) is blocked on the
un-deployed history endpoint (Railway redeploy needed — Murat). Labeling
the methodology pages NOW means that when the live curve ships, no page
contradicts it.

**Measured:** `npx next build` green, all 20+ routes compile. The
"no two pages tell different performance stories" done-when is satisfiable
only after P0 #2 ships; this cycle removes the contradicting *claims*.
