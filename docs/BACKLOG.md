# Aegis — Master Backlog

> **The durable, in-repo tracker so nothing is lost.** Created 2026-06-14 from the
> external-review validation pass ([`REVIEW_VALIDATION_2026-06-14.md`](./REVIEW_VALIDATION_2026-06-14.md))
> plus bigger-picture ideas. Every item carries: **what**, **why it's real**, the
> **chosen approach**, the **alternatives considered and why this one won**, the
> **guardrail/risk**, and **status**. This file supersedes ad-hoc TODOs.
>
> **Status legend:** ⬜ open · 🔵 in progress · ✅ done (this session) · ⏸ parked · ❌ rejected
> **Hard stops (never crossed without an attended session):** no `paper_nav`
> write-path change · no rule auto-adopted · no overlay armed on existing lanes ·
> no git history rewrite of shared `main` · no skill claim before 24 months.

---

## SECTION T — Thematic-Momentum & Exit Discipline (V3 workstream, 2026-06-15)

> Origin: Murat's "we lag SPY, we play too safe, buy the next big thing early
> and stop selling winners too soon — prove me wrong with real values." Full
> plan + thesis reconciliation + pre-registered trial:
> [`research/THEMATIC_MOMENTUM_2026-06-15.md`](./research/THEMATIC_MOMENTUM_2026-06-15.md).
> Key reframe: the testable thesis is *early cross-sectional momentum + exit
> discipline on individual names* (supported by Odean/JT/AMP), NOT theme-ETFs
> at peak (the Ben-David trap). The LLM/brain layer is forward-only (profit-
> mirage firewall); the mechanical layer is backtested under DSR/PBO.

| ID | Item | Status |
|---|---|---|
| ✅ T0 | Reconciliation doc + chunk plan + TRIAL-THEME pre-registration | done 2026-06-15 |
| ✅ T2 | Exit engine: ATR Chandelier trailing stop, vol-target sizing, fractional Kelly (`services/exit_engine.py`, 19 tests ✅). The research-identified #1 gap — engine previously had NO way to "let a winner run." Descriptive-only. | done 2026-06-15 |
| ✅ T1 | Secular theme baskets, point-in-time membership (`data/theme_baskets.yaml` + `services/theme_baskets.py`, 13 tests) | done 2026-06-15 |
| ✅ T3 | `thematic_momentum.py` — 12-1 momentum entry within as-of baskets + vol-target sizing | done 2026-06-15 |
| ✅ T4 | **Decisive backtest** 2015→2025 vs SPY (`engine/research/thematic_backtest.py`). **Result: leaning REJECT.** Neutral cfg LOSES to SPY (+11.2% vs +12.8% CAGR, 0.64 vs 0.75 Sharpe); only best-of-15 beats it, PBO=0.37 fragile, edge is bull-beta not selection alpha, survivorship-inflated. One real lesson: exits cut maxDD −25.6% vs −33.7%. See research doc §7. | done 2026-06-15 |
| ✅ T4b | Controls close-out. **TRIAL-THEME = REJECT.** Theme-momentum selection edge = −0.08 Sharpe vs controls (worse than generic broad momentum AND than equal-weighting the themes); PBO=0.66 overfit → gate FAILS. EW-themes beat SPY (+21.2%) but that's hindsight theme-pick + survivorship (I chose 2026's winners), not prospective skill. Exits = drawdown control (−30.6% vs −33.7%). Mechanical sub-question ENDED. See research doc §8. | done 2026-06-15 |
| ✅ T6 | Vol-managed momentum (3a, Barroso–Santa-Clara). **ADOPT as risk overlay** (Sharpe constant 1.17, maxDD −41%→−13%, leakage-safe). **But absolute Sharpe survivorship-inflated** (universe = today's large-caps); gate "PASS" is false-positive — DSR/PBO ≠ survivorship guard. Alpha claim needs point-in-time universe. See `research/VOL_MANAGED_MOMENTUM_2026-06-15.md`. | done 2026-06-15 |
| ❌ T7 | Point-in-time / delisted-inclusive universe. **REJECT-on-free-data (2026-06-16).** Audit (`engine/research/survivorship_audit.py`): of 20 delisted S&P names, 15 return nothing, 4 return a *different* company on a recycled symbol, only 1 usable (5%). yfinance cannot supply a survivorship-free universe; stooq unreachable; CRSP/Norgate paid (not held). **Consequence: no backtested absolute-alpha claim on our data is trustworthy → selection signals validate FORWARD (PIT-store IC + paper NAV), NOT by backtest.** See `research/SURVIVORSHIP_AUDIT_2026-06-16.md`, NEGATIVE_RESULTS §4. | done (rejected) 2026-06-16 |
| ⬜ T5 | Forward conviction lane — the ONLY honest test of "pick winning themes early" (backtest can't; it's hindsight). = **Priority 3**. | open |
| ⬜ T8 | Multi-factor score (momentum+value+quality via factor_grades) — strategy-improvement 3b. **Reframed by T7:** run as a FORWARD IC trial on PIT data, not a survivor-universe backtest (any backtest = direction-check only, stamped contaminated). | open |
| 🔵 T9 | Insider opportunistic-buy signal (item 3) as a FORWARD IC trial. **Signal + source + collector WIRED 2026-06-16:** `compute_opportunistic_buy_score` (open-market `P` only, distinct-buyer cluster + tanh($) bonus) + `insider_form4.py` (raw SEC Form 4 XML, hang-proof — **Finnhub free lacks code/price; edgartools hung ~50min, both rejected**) + `insider_collector.py` snapshotting `insider_opp:{ticker}` into the PIT store, weekly-throttled, in `_daily_check` (descriptive, UTC leak-safe). 18 tests (12 signal/source + 6 collector). Pre-registered `TRIALS/TRIAL-INSIDER-IC.md`. **Forward IC clock starts next deploy.** Remaining: rank-IC measurement once a forward window accrues; widen 12-name cross-section later. | collector wired; IC accruing |
| 🔵 T10 | Flip the analyst factor → revision MOMENTUM (item 4). **Built & wired 2026-06-17:** `compute_revision_momentum_score` (net Raises−Lowers + up−downgrades over 90d from yfinance `.upgrades_downgrades`, leak-safe; implied-upside abandoned) + `revisions_collector.py` (on generic `pit_score_collector`) → `revisions_score:{ticker}` into PIT, weekly, in `_daily_check`. Verified discrimination: NVDA +23 / AAPL +16 / DKNG −4 / KYTX 0. 10 tests. Pre-reg `TRIALS/TRIAL-REVISIONS-IC.md`. Forward IC clock starts next deploy. | collector wired; IC accruing |
| ✅ P3 | **Plan 3 — active mirror management WIRED** (item 2). `run_all_book_management` now runs in `scheduler.py:_daily_check` (mirror monthly/drift cadence + conviction decisions), isolated by book config hash, **no-op until `AEGIS_SEED_BOOK_LANES=1`** seeds the lanes. Tests: `test_book_management.py::TestPlan3Wiring` (no-op-pre-seed) + `test_scheduler.py::TestDailyCheckWiresBookLanes`. This is the forward selection-edge instrument T7's reject made the only honest one. Remaining: Murat flips the seed flag. | done 2026-06-16 |

---

## DONE THIS SESSION (2026-06-14)

| ID | Item | What was done |
|---|---|---|
| ✅ H2a | LightGBM security floor | `requirements.txt` → `lightgbm>=4.6.0` (CVE-2024-43598, verified). |
| ✅ H1a | Stop lab/transcript bloat | `.gitignore` now excludes `lab/experiments/*/data*` + the transcript. (Untrack of *existing* files is a documented one-liner — left for an attended commit, see H1.) |
| ✅ H4 | CLAUDE.md counts | 13→19 routers, 44→100+ services, 1177+→2460+ tests. |
| ✅ H3 | CI | `.github/workflows/ci.yml` added (offline pytest + ruff + pip-audit + next build). |
| ✅ M1 | Surface negative result | `NEGATIVE_RESULTS.md` written (root, visible). |
| ✅ M5 | Capability matrix | First-pass [`CAPABILITY_MATRIX.md`](./CAPABILITY_MATRIX.md) (V2 Goal 3). |
| ✅ doc | Data-layer design | [`V3_DATA_LAYER_DESIGN.md`](./V3_DATA_LAYER_DESIGN.md) — the linchpin. |
| ✅ doc | This backlog + the validation ledger | persistent trackers. |

---

## SECTION H — Hardening (verified real, cheap, no track-record risk)

### H1 ⬜ Untrack the lab scratch + transcript (do first, attended)
- **Real?** Yes — 2,587 files / 7.7 MB tracked; transcript with a space in its name.
- **Chosen approach:** `git rm -r --cached lab/experiments && git rm --cached "docs/v2 session transcript"` then commit. Working tree preserved. `.gitignore` already updated this session so nothing re-adds them.
- **Alternatives:** (a) full `git filter-repo` history rewrite to reclaim the 7.7 MB from history — **rejected**: rewriting shared `main` history is high-risk for ~7 MB on a repo this size; not worth it. (b) move artifacts to an external store — overkill for now. Stop-tracking-going-forward is the right cost/benefit.
- **Guardrail:** history rewrite is on the hard-stop list. Untrack only.

### H2 ⬜ Full dependency lockfile + pip-audit gate
- **Real?** Yes — all `>=`. H2a (lightgbm floor) done.
- **Chosen approach:** generate `requirements.lock` via `pip freeze` **in the Railway deploy env** (so it matches what actually ships), commit it, install from it in prod; keep `requirements.txt` as the loose dev spec. CI `pip-audit` (H3) reports real CVEs against the resolved set continuously.
- **Alternatives:** (a) hand-pin `==` in `requirements.txt` — **rejected**: can't resolve a correct full graph without the deploy env; would drift from prod. (b) pip-tools `requirements.in`→`.txt` compile — good, heavier; adopt if the lockfile churns. (c) trust DeepSeek's asserted CVE versions — **rejected**, unverified.
- **Guardrail:** none (additive).

### H3 ✅ CI workflow
- **Chosen approach:** GitHub Actions: `pytest -m "not slow"` (already network-blocked + timeout-guarded), `ruff check`, `pip-audit`, `next build`. ruff + pip-audit start **advisory (continue-on-error)** so first runs aren't red on pre-existing lint/CVE; pytest + build are blocking.
- **Alternatives:** (a) make everything blocking immediately — **rejected**: a red CI on day one trains people to ignore it; ratchet lint/audit to blocking once clean. (b) add the slow (network) suite to CI — **rejected**: flaky + needs API keys; keep CI offline-deterministic.

### H5 ⬜ `except Exception` swallower audit (the silent-fragility class)
- **Real?** Yes — 469 total, ~15% swallow silently. This class has bitten the project repeatedly ("silent degradation made loud").
- **Chosen approach:** targeted — grep the swallowers (those that `pass` / `return None` with no log), route data-fetch failures through `data_quality.py` so degradation is **loud**, leave the legitimate log-and-degrade ones. ~70 sites, not 469.
- **Alternatives:** (a) blanket-rewrite all 469 — **rejected**: most are correct (transient yfinance), churn-for-churn, high regression risk. (b) add a lint rule banning bare swallow — good follow-on once the audit defines the allowed pattern.
- **Guardrail:** behaviour-preserving; add a test per fixed swallower.

---

## SECTION M — Methodology honesty (touches numbers, no write-path)

### M1 ✅ Surface the backtest underperformance — done (`NEGATIVE_RESULTS.md`).

### M2 🔵 Crash Brier: error bar + event count (or CPCV) — mechanism SHIPPED
- **Real?** Yes — headline 0.046 is single-path, ~7 sell events, no CI.
- **Chosen approach:** attach a **block-bootstrap CI** (resample the walk-forward prediction/outcome pairs in time-contiguous blocks) **and** print the positive-event count next to every reported Brier. Then, as a second pass, run it through the existing CPCV harness for a distribution.
- **Alternatives:** (a) CPCV-only — **rejected as the *first* step**: bigger change, and a CI on the existing number is the honest minimum and ships today. (b) leave it — **rejected**: a number with no error bar on ~7 events is the exact over-claim the project's discipline forbids.
- **Guardrail:** methodology number; no write-path. Update README + METHODOLOGY together so the two never disagree.
- **Research update 2026-06-14:** CPCV with purge/embargo is the best-documented overfitting defense (lower PBO, higher DSR than Walk-Forward — Arian/Norouzi/Seco 2024). Block-bootstrap CI ships first; CPCV is the stronger second pass. Caveat: off-by-one purging silently leaks — implement carefully; Walk-Forward stays better for *live-sim* realism.
- **🔵 Shipped 2026-06-14:** `brier_with_ci` (`engine/validation/metrics.py`) — block bootstrap (not i.i.d., because overlapping-horizon crash labels autocorrelate) + positive-event count + `low_event_warning` (<10 events); wired into `walk_forward.run_backtest` and its logs/summary; METHODOLOGY + NEGATIVE_RESULTS updated; 12 tests. **Remaining:** (a) re-run the walk-forward to regenerate the README headline 0.046 *with* its CI (slow), (b) optional CPCV second pass.

### M3 🔴 Crash-model is BROKEN + reproducibility sidecar (escalated 2026-06-15)
- **Confirmed broken live (2026-06-15):** feature mismatch — the pipeline now
  builds **67 features, the model was trained on 30** → `predict` raises
  `LightGBM Fatal: number of features (67) != (30)`. Surfaced loudly during the
  2020→date replay (every check date). This is *why* the overlay is
  `model_not_deployed` and the replay falls back to a crash-prob stub.
- **Fix:** retrain `crash_model.pkl` on the current feature set + pinned sklearn,
  ship a metadata sidecar (train date, sklearn version, **feature count + hash**,
  sha256), assert it at load (fail loud on mismatch). The feature-hash check would
  have caught this. Precondition for *ever* arming an overlay.
- **Was parked as "low urgency"** (model dark so it corrupts nothing) — still true
  it corrupts no track record, but it's now a confirmed broken capability, not a
  latent risk. Bump when the crash/fragility work resumes.
- **Chosen approach (when armed):** write a `crash_model.meta.json` sidecar (train date, sklearn version, feature hash, file sha256) next to the `.pkl`; assert it at load; fail **loud** on mismatch; retrain on the pinned sklearn. This is a precondition of *ever* arming an overlay (must be on new pre-registered lanes with a provenanced binary — per TRIAL-001).
- **Alternatives:** (a) do it now — fine but no payoff while dark. (b) ONNX/skops instead of pickle — heavier; revisit if cross-version drift recurs.

### M4 ⬜ README repositioning (lead with the honesty infrastructure)
- **Real?** Strategic, not a bug. Both Claude passes + GPT converge: lead with the wedge (per-prediction SHAP, forward-only uncopyable track record, deflation guards, pre-registered trials), demote the breadth to an appendix, link `NEGATIVE_RESULTS.md`.
- **Chosen approach:** rewrite README top-of-fold around "the only market tool that shows you exactly why it's probably wrong, and keeps an honest forward scorecard." Keep breadth as a collapsed "techniques implemented" section.
- **Alternatives:** (a) keep the feature-grid comparison vs OpenBB/QuantConnect — **rejected**: we lose the breadth/data contest to mature tools; don't fight on the weak axis. (b) do it now — deferred to the V3 UI phase where the equity-curve UI lands alongside.

---

## SECTION V — Vision / strategy (the bigger asks — "think bigger")

> These answer Murat's prompt directly: *the crash hypothesis with real values,
> the Optimus brain as the edge, scraping investors/firms/politicians, and the
> paper accounts as racers.* All respect the anti-goals (no real-money trading, no
> RL-on-own-P&L, no skill claim before 24 months).

### V1 — Answer "is the market about to crash?" with measured values
- **The honest reframe (canon A5, research-backed):** short-horizon crash *timing*
  has ≈0 IC, and false-positive de-risking exits compounding bull runs (worse for
  returns than crashes). So the answerable question is **not** "when does it
  crash" but **"how fragile is the system right now, and is fragility rising?"**
- **What's already built:** `fragility.py` composite — 8 equal-weighted inputs
  (LPPLS, SOS, Sahm, turbulence, absorption, net-liquidity drain, HY-OAS, IG-OAS),
  descriptive-only, never arms a lane, **TRIAL-CRASH pre-registered** (forward
  Brier vs 20%-drawdown baseline). Current live read: **all quiet** (LPPLS 0.0,
  SOS 0.0, Sahm 0.1) — the engine tempers the strong prior with evidence.
- **Chosen approach to extend it:** add Murat's thesis drivers as **tested
  candidate inputs**, each entering the composite only after a registered IC/Brier
  trial, each shipping as a labelled descriptive column either way:
  - **IPO-issuance froth** (the original hypothesis trigger) — issuance volume /
    first-day-pop z-score. Source: SEC EDGAR S-1/424B + a count feed.
  - **VIX term-structure backwardation** + **put-skew** (already stubbed as
    candidates in `fragility.py`).
  - **Valuation stretch** (Shiller CAPE, equity-risk-premium vs real yield).
  - **Concentration / AI-bubble proxy** (top-N market-cap share, semis breadth).
  - **Margin debt / leverage** (FRED `BOGZ1FL663067003Q`-class).
- **Alternatives:** (a) fit composite weights to past crashes — **rejected**: that
  is exactly the hindsight overfitting the project refuses; equal-weight stays. (b)
  ship a single "crash probability %" headline — **rejected**: implies timing skill
  we measured as absent. A continuous fragility index that *scales exposure* is the
  surviving form of the psychohistory instinct.
- **Guardrail:** descriptive until forward Brier earns more; never arms a lane;
  every candidate is a registered trial (DSR/PBO deflated against cumulative count).
- **Research update 2026-06-14** (`FRAGILITY_RESEARCH_2026-06-14.md`): absorption
  ratio = validated *leading* fragility measure (keep, weight it); turbulence =
  OOS skill but **coincident** (label it, use de-risk-on-persistence, not as a
  leading trigger); LPPL = refuted again (descriptive-only confirmed). The crash
  hypothesis read: **mixed, not pre-crash** — IPO activity is below 1999/2021;
  the mania is in *private* AI capex ($267B Q1'26 VC, ~$140B in two deals), not
  yet public equity. Secondary-market gauges (CAPE/ERP/Mag-7/margin/OAS/MOVE/VIX)
  are **unverified** — source them via V3 and measure forward, don't assert.
- **🔵 Shipped 2026-06-14:** each composite input now carries a `lead_lag` label
  (turbulence=coincident, absorption=leading, Sahm/SOS=lagging, etc.) + a
  secondary equal-weight `leading_composite` view. The main `composite` (the
  TRIAL-CRASH metric) is **unchanged** — labels add transparency, they do NOT
  re-weight (no-fit-weights canon held). `fragility.py` + 3 tests. **Next:** wire
  the candidate inputs (IPO froth via V3, VIX term, put-skew) as registered trials.

### V2 — Persist the real portfolio server-side + the mirror lane (V2 Goal 8)
- **Real?** Yes — "My Portfolio" is `localStorage` only; nothing watches it.
- **Chosen approach:** move holdings into the existing PI SQLite; run the live
  engine (real_analyzer, factor model, crash overlay status, fragility) against
  *Murat's actual book* each scheduler tick; stand up the **mirror lane** (Aegis
  manages the same inception book by its own rules) so attribution can one day
  answer "did Aegis beat Murat on Murat's own book." Conviction lane (Murat's real
  decisions + rationale) already has capture endpoint+CLI.
- **Alternatives:** (a) keep it client-side — **rejected**: can't alert or watch
  what isn't persisted. (b) a full multi-user accounts system — **rejected**: scope
  creep; single-user server-side is enough.
- **Guardrail:** holdings store is separate from `paper_nav`; no skill claim early
  (a ~14-name book means months of divergence are statistically meaningless).

### V3 — The point-in-time / as-of data layer (THE linchpin) — see [`V3_DATA_LAYER_DESIGN.md`](./V3_DATA_LAYER_DESIGN.md)
- **🔵 Status (2026-06-14):** foundation SHIPPED. `pit_observations` table (schema v7, `backend/db.py`) + `snapshot`/`get_latest_observable`/`get_series_observable`/`get_revisions` (13 tests). First collector `backend/services/pit_collectors.py` — EDGAR 13F filing activity, lag captured natively (as_of=report period, observed_at=filing date), per-institution failure isolation, EDGAR rate-limiter (8/s) added to `edgar_events.py` (10 tests). **Next:** 13F holdings infotable extraction (2b); wire a scheduler collector job; add congress/options/breadth/sentiment collectors (needs the owed follow-up research).
- **Why it's the linchpin:** it is the one decision that makes (a) scraping safe,
  (b) lane feedback leak-free, and (c) a compounding, uncopyable data moat. Without
  it, scraped *current* values silently poison every backtest with look-ahead bias
  — the exact failure that would destroy the credibility the project has earned.
- **Chosen approach:** `snapshot(key, value, as_of_ts, source, revision)` store;
  never overwrite, keep revisions; **API-first, scrape-last**; every writer wrapped
  in `data_quality.py`. Backfill nothing — let it accrue forward.
- **Data priorities (the "track investors/firms/politicians" ask, API-first):**
  1. **SEC EDGAR 13F** (institutional positioning — "where the big players are").
  2. **SEC Form 4** insider clusters (have some via Finnhub; go direct).
  3. **Congressional trading** (STOCK Act disclosures / Capitol Trades-style) —
     "track politicians," but on a 30–45-day legal disclosure lag → strictly a
     descriptive/regime feature, never a timing signal. Honesty label mandatory.
  4. **Options positioning** (IV skew, P/C, gamma, VIX term) — real chains.
  5. **Breadth + sentiment/positioning** (%>200dma, A/D, AAII, NAAIM, Fear&Greed).
  6. **Funding/credit stress** (SOFR, MOVE, repo) — extends existing NFCI/OAS.
- **Alternatives:** (a) scrape-first for speed — **rejected**: ToS risk + silent
  breakage + no provenance. (b) one big vendor (e.g. paid Polygon tier) — deferred;
  free/official first, pay only where it proves out.
- **Guardrail:** scrapers fail loud through `data_quality`; politician/insider data
  is descriptive-only with the disclosure-lag stated.

### V4 — Alert / notification engine + event-driven "trade-the-alerts" lane
- **Real?** Yes — **no alerting layer exists** (every "alert" today is a UI icon).
  This is the highest-leverage missing piece for "help me invest / notify me."
- **Chosen approach (two parts):**
  - **Alert engine:** a rules table (`regime_change`, `crash_3m > θ`, `risk_score
    Δ>1σ/day`, `drift_detector fired`, `held_name signal Buy→Sell`, `fragility
    armed`) evaluated each scheduler tick against the PIT store, with
    dedupe/cooldown. Delivery: Telegram bot or Discord webhook (~30 lines, free),
    email as backup. **Framed as risk-awareness, not orders** — every alert carries
    historical-analogue context (e.g. "crash-prob crossed 20%; last 4 times fwd-3m
    was {+26,+15,−4,+3}% — wide and mostly positive").
  - **Event-driven lane:** a new pre-registered paper lane that *acts on the
    alerts*. Its forward NAV becomes the live, leak-free answer to "does acting on
    Aegis beat ignoring it?" — the thing the backtest (A6) cannot prove.
- **Alternatives:** (a) day-trading lane (Murat's "racers" instinct, literal) —
  **rejected**: txn costs swamp any edge, multiple-testing surface explodes, and
  hourly free data has no intraday edge to harvest. Instead run **multiple lanes at
  multiple horizons** (monthly / weekly tactical / event-driven) as separate
  pre-registered hypotheses — same benefit (more decisions, faster power) at the
  timescale where the engine might actually have edge. (b) push raw numbers —
  **rejected**: the digest (LLM-synthesised 3-sentence "what changed / what it means
  / what's uncertain") is the product, not the firehose.
- **Guardrail:** alerts never say buy/sell unless the signal passed the Brier gate
  (Goal 5); the event lane is forward-only and pre-registered; no auto-adopt.

### V5 — The Optimus brain as the edge (process-learning, not P&L-learning)
- **What it is:** Optimus is the private context layer — it ingests session
  postmortems, decision rationales, rejected experiments, verified state, canon.
  It is **how the system "learns from mistakes"** without weight-updates on its own
  returns (which learns noise and dies live — the A2 firewall, now quantitatively
  backed by the profit-mirage research).
- **Chosen approach to build it better:**
  - **Close the feedback loop:** the LLM-conviction lane proposes portfolio
    decisions *using Optimus context*, every decision logged + attributed against
    the rules baselines → measured "AI managing money," forward-only.
  - **Brain-writes-back:** after each session, auto-distil the postmortem +
    rejected trials into the corpus so the next session starts smarter (the
    context-loss tax, V2 Goal 6 — server exists; tighten the write path).
  - **Calibration memory:** when the brain makes a call (fragility read, conviction
    decision), store it with the forward outcome so its *own* reliability curve
    accrues — the brain is graded the same honest way the lanes are.
- **Alternatives:** (a) fine-tune a model on Aegis's P&L — **rejected** (anti-goal:
  RL-on-own-P&L learns noise; profit-mirage shows backtest "experience" is
  hindsight-contaminated). (b) bigger context dump per session — **rejected**:
  retrieval + distilled corpus beats raw dump. The edge is *process knowledge that
  compounds*, never a cleverer predictor.
- **Guardrail:** brain ingests process, never trains on P&L; conviction lane is
  forward-only; firewall test-pinned.
- **Research update 2026-06-14:** new hard number for the firewall — KTD-Fin
  (arXiv 2605.28359, May 2026): under blinded eval **Claude Opus 4.7 = +58.80%
  return but +0.2% selection alpha; 9/10 models negative selection alpha**.
  Returns collapse into style-factor harvesting; agents memorize tickers, not
  causality. Borrow FactFin's counterfactual-perturbation prompting to force
  causal (not memorized) reasoning in the conviction lane. Add this citation to
  canon A2 alongside arXiv 2510.07920.

### V6 ⏸ "Lead with the answer" UI + decision-engine framing (V3 UI phase)
- One-screen health report ("Market Health 72/100 — credit stress rising; your
  book's 2022-style drawdown ≈ −18%"); simulation outputs phrased as decisions
  ("23% chance of −35% in a recession regime"), not raw paths; the live
  equity-curve UI (all lanes vs benchmarks, segment boundaries, freshness).

### V7 ⏸ Optimizer honesty (HRP/risk-parity + regime over Black-Litterman)
- GPT's one solid quant point: garbage expected returns make BL elegant-but-wrong
  for retail. **Already being tested forward** by TRIAL-001 (HRP vs EW). Revisit the
  BL path only after that trial reads out (earliest 2027-06-10). Logged, parked.

### V8 ⏸ Tiered coverage — "budget JP Morgan" (canon A1)
- Tier-2 broad descriptive coverage (~S&P 500 + Russell 1000: consensus targets,
  implied upside, ratings) at near-zero compute; Tier-1 deep analysis for ~50–100
  promoted tickers. Analyst-implied-upside ships as a registered IC trial.

---

## SECTION X — Explicitly rejected (do not re-open)
See [`REVIEW_VALIDATION_2026-06-14.md`](./REVIEW_VALIDATION_2026-06-14.md) §D.
Amputate-70% · OAuth2/auth · rate-limiting-as-critical · pandas query() injection ·
pickle-RCE-panic · production-readiness-grade-F framing.

---

## Suggested sequence
1. **H1, H2** (untrack + lockfile) — attended, 30 min, closes the cheap real class.
2. **M2** (Brier CI) — honest error bars, ships today, no write-path.
3. **V3 data layer** (start the PIT store + snapshot what we already fetch) — the
   linchpin; backfill nothing, let it accrue.
4. **V4 alert engine + event-driven lane** — turns "a site I forget to open" into
   "a thing that taps me on the shoulder," and forward-proves the thesis.
5. **V1 fragility candidate inputs** (IPO froth first) — the crash hypothesis,
   measured.
6. **H5, M4, V6** — audit, README, UI — as the V3 product phase lands.
