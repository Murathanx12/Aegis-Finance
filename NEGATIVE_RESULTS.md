# Negative Results — what Aegis measured and it didn't work

> This file exists on purpose, at the top level, where a skeptic finds it first.
> A project that runs anti-overfitting discipline *and* tells the truth about its
> negative results is rarer — and more trustworthy — than one that hides them.
> Surfacing this is consistent with [`docs/TRACK_RECORD_POLICY.md`](./docs/TRACK_RECORD_POLICY.md)
> and the fragility-not-timing reframe in `docs/V2_GOALS.md` (A5).

## 1. The timing strategy underperforms buy-and-hold

Source: [`backend/BACKTEST_RESULTS.md`](./backend/BACKTEST_RESULTS.md), signal
engine over 2020-01 → 2025-06 (66 monthly signals).

| Metric | Strategy | Buy-and-hold |
|---|---|---|
| Total return | **+250.9%** | **+740.0%** |
| Sharpe | **0.675** | **0.921** |
| Sell-signal 3M hit-rate | **28.6%** | (target was >55%) |

**Plainly: as a market-*timing* tool, the signal engine loses to doing nothing —
on both absolute and risk-adjusted return.** It is not buried, spun, or framed
away. It is the finding.

### Why this happens (and why it's not a bug)
The sell signals fire during high-VIX, sharp-drawdown periods — which in
2020–2025 were the *best* buying opportunities (mean reversion). All 7 sell
signals landed at VIX > 25; forward-3M returns after them were
`{+2.6, +26.1, +15.4, −0.04, −3.8, +2.8…+7.1}%` — wide and mostly positive. The
engine is **correct about current risk and wrong about forward return**. That is
the well-known, hard truth of short-horizon equity timing, not a defect unique to
this code.

### What we concluded
1. **Aegis is a risk-awareness tool, not a timing tool.** It tells you how exposed
   you are and why (SHAP), not when to jump out.
2. This is exactly why the **crash overlay is deliberately disabled** and why the
   north-star was reframed from *time the crash* to *measure fragility and scale
   exposure as systemic stress rises* (V2_GOALS A5). The research backs it: short-
   horizon crash timing has ≈0 information coefficient.
3. The honest test of whether *acting on Aegis* beats *ignoring it* is not this
   backtest — it is the **forward, leak-free, event-driven paper lane** (BACKLOG
   V4), whose NAV accrues only with elapsed time and cannot be cherry-picked.

## 2. 12-month crash prediction has no skill
The crash model's 3-month Brier (0.046) beats the base rate, but the **12-month
horizon ≈ climatological base rate** — no edge. Lagging indicators dominate its
SHAP at long horizons. The headline 3M number is also computed on a single
walk-forward path over only ~7 stress events. It is **now reported with a
block-bootstrap 95% CI + the positive-event count and a low-event warning**
(`engine.validation.metrics.brier_with_ci`, shipped 2026-06-14) — regenerating
the headline figure *with* its interval is a (slow) walk-forward re-run.

## 3. LPPLS (log-periodic bubble) predictive skill: refuted
Adversarially tested twice in the 2026-06-14 research phase; predictive skill was
refuted both times. LPPLS therefore ships as a **descriptive bubble-structure
flag only** — it never arms a lane and never emits a timing call.

## 4. A survivorship-free backtest universe is not buildable on free data
Source: [`engine/research/survivorship_audit.py`](./engine/research/survivorship_audit.py)
→ `docs/research/SURVIVORSHIP_AUDIT_2026-06-16.md` (run: `python -m engine.research.survivorship_audit`).

Every selection backtest draws its universe from `config.stock_universe` =
*today's* large-caps — survivors only. To de-bias it we'd need the delisted names
back in. We tested whether the free data layer (yfinance) can supply them: of 20
real S&P 500 names that later went bankrupt / were acquired / failed, **15 return
nothing, 4 return a *different* company on the recycled symbol, and only 1 is
genuinely usable (5%).** Controls (AAPL/MSFT/XOM) all clean; stooq was unreachable.

**Plainly: no backtested absolute-alpha number on our data is trustworthy** — it
is inflated by survivorship by an uncorrectable amount, and the DSR/PBO gate
cannot see it (it guards multiple-testing, not a biased universe — this is exactly
how vol-managed momentum printed a false "PASS"). The consequence is not despair:
the **PIT store accrues forward-only with an anti-leak `observed_at` field**, so
selection signals (insider buys, estimate revisions, 13F, multi-factor rank) are
validated by **forward information coefficient + paper-lane NAV**, never by a
historical backtest. Risk overlays (vol-management, ATR exits) are
universe-independent and unaffected.

## 5. The insider collector "ran" but fetched nothing in prod (silent-fragility catch)
Not a strategy result — a process result, and the most important kind. The T9
insider forward-IC collector passed all 12 offline tests and worked on the dev
machine, so the wrap-up reported it live. A **live prod check** (the discipline,
not the tests) found it failing **100% of its SEC fetches** — 50 warnings, every
one a 403 on `www.sec.gov/Archives/`. The IC clock looked alive and was accruing
nothing but fetch failures.

Root cause: `insider_form4` issued **raw, unpaced** `requests.get` calls instead of
routing through the process-wide SEC rate limiter that `edgar_events` enforces
(its own comment: *"ALL EDGAR HTTP must go through it"*). One collector run fires
~360–1000 fetches at `www.sec.gov`; on Railway's fast egress that trips SEC's
10 req/s threshold instantly, and SEC answers with **403, not 429**. Local dev's
handful of calls never tripped it — the classic "tested ≠ works in prod" gap.

The tell that pinpointed it: prod warned **only** on the high-volume Archives host,
never on the low-volume `data.sec.gov` submissions call — same User-Agent, so it
wasn't a UA/IP block; the only difference was request *count*. Fix (2026-06-17):
every SEC call now goes through one `_sec_get` choke-point — shared limiter pacing
(≤8/s), declared UA (env-overridable `SEC_USER_AGENT`), one 403-retry with backoff.
Verified live end-to-end. **The lesson: a collector that runs but fetches nothing
reads as "covered" on every green dashboard — only a live prod check sees the
silence.** T10 (revisions) and T8 (multi-factor) were audited the same way and are
healthy (yfinance paths, no SEC dependency).

## 6. The crash-model retrain "works" and still proves nothing (label sparsity)

The M3 retrain (2026-07-11) rebuilt `crash_model.pkl` end-to-end on the exact
live feature path (86 built → 20 selected; only **5 features survived LASSO**),
loads cleanly through the sidecar contract, predicts on live features without
raising, and passes 214 tests — and it is still **not deployable as a
prediction source**. Walk-forward AUC is *unmeasurable* (the purged validation
window contains zero ≥20%-drawdown events at every horizon), the outputs are
near-constant (the 6m head emits literally one value; trailing-2y std 0.00pp),
and the 12m headline (43%) is ~3× the unconditional base rate with no
demonstrated discrimination. Root cause is the **label**: daily crash-label
rates of 3.2/7.8/15.7% collapse to a handful of independent crash episodes —
a binary ≥20%-drawdown target cannot support learning on one market's history.
Decision: **hold the deploy** (an honest `model_not_deployed` beats a
skill-less number lighting up the overlay), keep TRIAL-CRASH's fragility
composite as the crisis read, and redesign the target per
`docs/research/CRASH_AND_OSS_RESEARCH_2026-07-11.md` (forward max-drawdown
severity via quantile trees, read out as multi-threshold exceedance
probabilities; benchmarked against STLFSI4-as-predictor before any promotion).
The CLAUDE.md "walk-forward AUC ≥ 0.70" health gate is unmeasurable for this
label and moves to PR-AUC/event-window metrics in the redesign.

---
*These are not reasons to distrust the project. They are the reason to trust it.*
