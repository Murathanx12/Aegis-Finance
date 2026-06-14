# Aegis Finance — V2 Roadmap

> Companion to `STATE_OF_THE_REPO.md` (verified inventory) and `v2_candidates.md` (deferred features). This doc draws the **version boundary**, lists what's broken / missing / needed, and specifies how to fold in **Optimus** and **open-source projects**. Written for Claude Code to execute across future sessions. Goal unchanged: a reliable, *honestly-measured* investment guide tool — not a Bloomberg clone.

---

## 2026-06-14 — Research-driven addenda (supersedes where it conflicts below)

> Folds in two adversarially-verified research runs (see
> **`DEEP_RESEARCH_2026-06-14_DECISION.md`** for the cited findings) plus the current
> deployed reality. **§1–§7 below were written pre-deploy and read "ship V1" — V1 has
> been live since 2026-06-08; treat them as the standing engine plan, this section as the
> current head.** The discipline is unchanged and now literature-backed: *descriptive
> until measured, loud not silent, no claim ahead of the out-of-sample number.*

### Where we are now (verified)
Live forward track record, day 6, 4 lanes (conservative/balanced/aggressive +
balanced-ew-control), config v2 (`628456e4`, leakage-safe HRP) with a clean v1→v2 segment
boundary. Experiment registry live with TRIAL-001 (HRP-vs-EW) pre-registered; cumulative
trial count = 1. Optimus MCP server wired (Goal 6 closed). Crash overlay deliberately
**off** and now loudly observable (`ecb1be3`). DSR/PBO guards exist (`overfitting.py`).

### What the research changed (net-new, beyond §1–§7)
1. **A bubble/fragility lane is justified — but only as a descriptive flag.** LPPLS's
   predictive skill was **adversarially refuted**; it measures bubble *structure*, not
   timing. It enters as a measured trial, never an armed signal.
2. **The macro lane has a better recession flag than Sahm:** the Richmond Fed **SOS**
   indicator (free FRED `IURSA`), 7/7 recessions since 1971, zero false positives, leads
   Sahm — but still **coincident-to-lagging**, framed by lag-to-onset.
3. **The effective-N gap in DSR is real and load-bearing:** the False Strategy Theorem
   assumes independent trials; correlated lanes make raw-N DSR too lenient. Must be fixed
   **before** §P1 lane expansion adds correlated lanes.
4. **The hindsight firewall is now empirically grounded** (profit-mirage / ~37% leakage /
   p=0.033) — reinforces the Optimus boundary (§5) and the no-RL-on-P&L anti-goal.
5. **Smart-money signals have a durable-vs-noise split:** insider *opportunistic* trades
   (~82 bps/mo) and *long-horizon* 13F cloning carry edge; *routine* insider trades and
   *45-day-lagged high-turnover* 13F cloning do not. Any future Goal-5/smart-money work
   filters on this, gated against a baseline.

### The three queued tickets (PLANNED — not started; await Murat's go)

| # | Ticket | Pre-registered OOS done-when | Sequence |
|---|---|---|---|
| **T1** | **LPPLS as a measured regime flag** (existing `bubble_detector.py` → scheduled eval, `lppls_eval` audit row + `/api/health/full` canary mirroring the overlay template, pre-registered TRIAL-LPPLS, forward Brier harness vs climatology baseline, PI card labeled "descriptive, not a timing tool"). **HARD: never arms a lane.** | Flag computes on schedule; forward Brier+calibration by horizon (30/60/90d) accumulating vs base-rate baseline; UI implies no prediction; zero lane wiring. *Skill claim only after a pre-registered forward window.* | After deploy unsticks; **open decision:** keep existing nested-MC fitter vs rewrite to quantile regression (per source). Largest ticket. |
| **T2** | **Effective-N correction for registry DSR** (participation-ratio `N_eff=(Σλ)²/Σλ²` over lane-return correlation; feed N_eff to DSR not raw count; expose both at `/api/pi/registry`; graceful raw-N fallback under short history). | `/api/pi/registry` returns raw N **and** effective-N; DSR uses effective-N; pinning test: a near-duplicate lane (ρ≈0.99) moves N_eff <~0.1 while raw N +1. | **Must land before §P1 #6** (mirror/conviction lanes are correlated). Fully test-verifiable offline. |
| **T3** | **SOS recession indicator** (add FRED `IURSA`; new `macro_indicators.py::compute_sos_signal`; display alongside Sahm in `/api/macro` with lag-to-onset framing). | SOS computes from FRED; shows next to Sahm with honest lag framing; **no prediction claim** (string-assert no leading-indicator language). | Independent, small, offline-verifiable. |

### Open decisions blocking the build (carry forward)
- **D1 — LPPLS calibration:** existing `lppls`-library nested-MC fitter (faster; predictive skill was refuted anyway, so the *measurement harness* matters more than fit precision) **vs** quantile-regression rewrite (matches the verified source letter). Unresolved.
- **D2 — Deploy gap:** `ecb1be3` (last session's overlay observability fix) is pushed to `origin/main` but **Railway is still serving `e759bf7`**. T1's schedule/canary can't be live-verified until this unsticks; recommend resolving before/with T1.

### Recommended sequence
**T2 → T3 this session-class (offline-verifiable, T2 unblocks P1 #6), T1 next** (largest, gated on D1 + D2). Then the existing §P1 #6 lane framework. Follow-up research pass owed on the **unverified** items (Section 4 data-ToS, Section 5 real-time signals, CSCV/slippage mechanics) before any of those ship as asserted.

### Where we should become (honest, anti-goal-respecting)
Same north star as the one-paragraph version at the bottom of this doc — now with three
measured additions (a descriptive fragility flag, an honest recession flag, a tighter
overfitting guard) and a literature-grounded firewall. **None of it ships as "it works"
until a forward out-of-sample number says so; no skill claims before 24 months.**

---

## 0. The single most important call: freeze the engine set

The codebase has ~85 service modules and ~2,300 tests. The risk for this project is **not** too few features — it's too many unaudited ones diluting the one thing that makes Aegis defensible: *honest measurement*. A tool that says "here are 85 signals" but can't tell you which ones actually predict is no better than the opaque competitors.

So the load-bearing discipline for V1→V2:

- **V1 freezes the engine set.** No new engines. Ship what exists, deploy, start the track record.
- **The remaining engine work (Step #2, Step #3) makes EXISTING engines honest and self-improving — it does not add new ones.**
- **V2's biggest hidden need is consolidation, not expansion** (see §4, Capability Audit).

If a session is tempted to "add one more model," the answer is no until the audit in §4 has classified what's already there.

---

## 1. Version boundary (what ships when)

### V1 — ship now (deployed from commit `2d6a94a`)
- All engines built + validated honestly (crash Brier 0.046 @ 3M with honest 12M-no-skill finding; MC with Merton compensator; regime/HMM; FF5 factor model; factor grades with **momentum validated as descriptive, not alpha**; fundamentals via EDGAR + Piotroski; overfitting guards PBO/DSR/CPCV).
- Paper accounts: equal-weight + crash-overlay-to-**cash** + sector caps + cash sleeve earning rf + **live MTM** + replay unified on `nav.py` + Aegis-owned experiment registry with cumulative-trials guard.
- Honest config (no overclaiming; `optimizer: equal_weight`, intent in `planned_optimizer`).
- Deploy gate cleared in code (migration, scheduler `/health/scheduler` canary, idempotent inception, FRED rf logging).
- **Volume-shadow trap fixed (`AEGIS_DATA_DIR`).** Mutable state (`aegis_pi.db`, APScheduler job store) resolves from `AEGIS_DATA_DIR`; the immutable `paper_portfolios.yaml` + `MODEL_DIR` stay baked in the image. On Railway: set `AEGIS_DATA_DIR=/data` and mount the volume at **`/data`** — NOT at `backend/data` (that would shadow the config YAML and break lane init on first boot). Contract pinned by `test_deploy_gate.py`.
- **Deploy → forward track record begins.** This is the line in the sand. Track-record anchor: `config_version = 82be14cb6039bfae`, inception_date = first Railway boot.

**V1's honest limitations (documented, not hidden):**
- Lanes are equal-weight, not optimized (Step #2 fixes this).
- Replay uses a `crash_prob_override` stub, not the live model (V1.x fixes this).
- Survivorship: full-universe replay flagged; ETF-only diagnostic is the honest baseline.

### V1.x — immediate post-deploy (days–weeks, low-risk)
1. **Step #2 — leakage-safe optimization.** Wire HRP (conservative/aggressive) + Black-Litterman (balanced) through an **as-of price path** (the latent leakage trap: `optimize_hrp` currently fetches its own latest 504d returns with no as-of bound — it MUST see only data ≤ the check date). Land as a **SHA-versioned config change** so the track record segments cleanly (v1 equal-weight → v2 optimized). Validate zero leakage with a regression test (replay result identical whether or not "future" data exists in the frame).
2. **Live V7 crash model in replay** (from `v2_candidates.md`). Replace the stub with the real model against `MarketDataAtTimestamp`-sliced features. Blocker to clear first: validate the as-of feature reconstruction matches V7's training inputs bit-for-bit, or it silently returns garbage probabilities.
3. **Replay cache fixes** (from `v2_candidates.md`, ~75 min total): UTC time-based TTL (not calendar-day), last-bar-date market-data key (not `today()`). Low-risk, removes spurious recomputes.
4. **Optimus MCP server** (see §5) — independent of the above, high workflow leverage, can slot anytime.

### V2 — the bigger build (the real roadmap)
- **Step #3 — the guarded rule-evolution loop** (§3). The "evolve by itself" engine.
- **PIT fundamentals panel** → honestly validate the 4 fundamental factors (§4).
- **DeepSeek per-stock news flag** (surprise detection, measured) (§4).
- **Capability audit & consolidation** of the 85 services (§4) — the highest-leverage debt paydown.
- **PM-attribution surface** as the track record matures toward the 24-month skill threshold.
- Conditional items from `v2_candidates.md`: survivorship-free universe (if funding/free data), LLM portfolio commentary (if 60 days unattended + ≥30 logged decisions).

---

## 2. What's broken / technical debt

| Item | Severity | Fix | When |
|---|---|---|---|
| Replay uses a `crash_prob_override` stub, not the live model | Medium | Wire V7 against as-of features (validate reconstruction first) | V1.x |
| Replay cache: calendar-day TTL + `today()` market-data key cause spurious recomputes | Low | UTC TTL + last-bar-date key | V1.x |
| Momentum grade is a 3M/6M/12M blend, not the pure 12-1 that validated best (IC 0.0147 vs blend's lower) | Low | Make "12-1 vs blend" a guard-tested experiment in the Step #3 loop, not a hand-pick | V2 |
| Live cash rf-accrual over elapsed days is a refinement (replay already accrues via `nav_series` rf_daily) | Low | Accrue rf on the live CASH balance between marks using days elapsed | V1.x |
| **85-service sprawl, largely unaudited** | **High (latent)** | Capability audit: classify validated / built-unvalidated / experimental; validate, hide, or cut | **V2 (§4)** |
| Equal-weight lanes are honest but suboptimal | n/a (by design) | Step #2 optimization | V1.x |

The sprawl is the biggest hidden debt. Modules like `copula_tail`, `tail_dependence`, `systemic_risk`, `survival_model`, `pair_trading`, `crypto`/`defi`, `esg`, `short_interest`, `sector_rotation`, `options_intelligence`, `mpc_optimizer` may or may not be tested, router-wired, UI-exposed, or validated for skill. Until audited, they're unverified surface area that dilutes the honesty story.

---

## 3. Step #3 — the guarded rule-evolution loop (the "evolve by itself" engine)

This is the feature most wanted and the one most likely to self-destruct if built wrong. The registry + guard primitive already exist (`experiment_registry.py`, `overfitting.py`); **the loop that drives them does not.**

**What it does:** proposes rule-parameter changes (drift threshold, crash-prob threshold, equity-cut size, momentum definition, even new lane configs) → tests each on walk-forward / CPCV out-of-sample → adopts a change **only if it survives DSR ≥ 0.95 and PBO < 0.5 deflated against the *cumulative* trial count** → lands the survivor as a SHA-versioned config change.

**The two non-negotiable contracts (these keep it from becoming an overfitting machine):**
1. **Deflate against cumulative trials, not per-batch.** Already enforced in `evaluate_candidate` (`n_trials = existing + batch`). Do not regress this.
2. **Record EVERY candidate evaluated — rejected ones too — via `record_trial`.** If the loop tests 60 configs a night but records only the 1 winner, the cumulative count undercounts, the bar stays artificially low, and the guard erodes. The `verdict` column ('adopted'|'rejected') exists precisely to hold rejected trials. **This is the contract that, if violated, silently breaks the whole guarantee.**

**What it must NOT be:** an RL agent optimizing its own trading on its own P&L. That learns noise and dies live. The loop proposes *rules*, tested *out-of-sample*, gated by *deflation* — measurement, not autonomous trading.

**Acceptance:** an overfit candidate must be rejected *with the DSR/PBO numbers shown*; a synthetic robust strategy must be adopted; the registry's cumulative count must visibly tighten the bar over successive runs.

---

## 4. What's missing / needed (V2 build items)

### 4a. PIT fundamentals panel → validate the 4 fundamental factors
The factor-grade validation (Chunk 2) honestly deferred Value/Growth/Profitability/Revisions because a rigorous historical IC needs **as-filed, point-in-time** data (restated data = look-ahead). Build it by extending `fundamentals.py`'s EDGAR pipeline to **capture filing dates and persist a historical panel** across the full universe, then run Alphalens-style IC at real sample size. Honest numbers for all five factors — at scale, not a 20-ticker hack.

### 4b. DeepSeek per-stock news flag
DeepSeek (`llm_analyzer.py`) and GDELT news exist. Build the per-stock news→movement layer as a **surprise/event-detection flag, NOT a price predictor** (news is coincident-to-lagging — same trap as the unemployment-z-score finding). **Acceptance gate:** improves out-of-sample Brier over the no-news baseline, OR ships as human-readable context with the negative result documented. Either outcome is fine; measure it.

### 4c. Capability audit & consolidation (the highest-leverage debt paydown)
Classify every one of the ~85 services into:
- **Validated & exposed** — tested, router-wired, UI-visible, and (where it makes a predictive claim) skill-measured. Keep and feature.
- **Built but unvalidated** — exists and tested for correctness, but no out-of-sample skill measurement. Either validate (Alphalens/Brier/backtest) or label "descriptive, not predictive" like momentum.
- **Experimental cruft** — half-wired, untested, or unexposed. Hide behind a flag or cut.

Output: a `CAPABILITY_MATRIX.md` that, for each service, states what it does, whether it's tested, whether it's exposed, and whether its predictive claim (if any) is validated. This is what lets Aegis honestly say "these signals are measured; these are descriptive" — the core differentiator, applied at platform scale.

### 4d. PM-attribution surface
As the live track record matures, build the surface that measures whether each lane (and the personal conviction lane) beats SPY/AGG/60-40 with FF5 attribution — the honest "does this add value" answer. No skill claims until ≥24 months of tracked decisions (already in config: `skill_min_months: 24`).

---

## 5. Optimus integration (how)

**Boundary (do not violate):** Aegis and Optimus stay **separate products** — Railway vs laptop, public vs personal. **Optimus READS Aegis; it never owns Aegis's operational data.** The experiment registry, track record, and config live in Aegis (where the loop runs, and for open-source reproducibility). Optimus ingests them as corpus.

**The missing piece:** Optimus is ~40% complete (ingest/query/deprecate/audit tested; Aegis already ingested as corpus). The **MCP server is an empty `/mcp/` dir** — which is the whole point, because without it Optimus can't feed Aegis context to Claude Code.

**Sequence:**
1. Deploy V1 (Aegis stable + documented).
2. **Build the Optimus MCP server** (`/mcp/` entrypoint) — do this early in V1.x/V2; it's independent of the Aegis engine work and pays off every session.
3. Have Optimus ingest: Aegis corpus (partially done — 4 pages, 13 claims) + the experiment registry (read-only) + the methodology docs.
4. Wire Claude Code → Optimus MCP. **This ends the context-loss tax** that this entire re-entry arc demonstrated: every future session starts already knowing Aegis's verified state, decisions, and guardrails — no re-pasting briefs, no re-auditing.

**Why it's worth it:** the single biggest recurring cost in this project has been reconstructing context after a pause. The MCP server is the structural fix.

---

## 6. Open-source projects (how to fold in + license firewall)

**Use directly (MIT / BSD / Apache — safe for the MIT repo):**
| Library | License | Use in Aegis |
|---|---|---|
| PyPortfolioOpt | MIT | Step #2 optimization — efficient frontier, Black-Litterman (already integrated) |
| Riskfolio-Lib | BSD-3 | Step #2 — HRP, risk parity, **CDaR** (drawdown-based optimization Aegis lacks) (already integrated) |
| Alphalens | Apache-2.0 | §4a PIT factor validation — IC, quantile spreads |
| vectorbt | Apache-2.0 | Faster replay at scale if the Step #3 loop's backtests get slow |
| QuantStats / pyfolio / empyrical | Apache-2.0 | Tear sheets + performance/risk reporting for the live track record |
| mlfinlab | (verify per-module) | Reference patterns for CPCV / triple-barrier (Aegis already implements these — use as cross-check) |
| pandas-ta | MIT | Additional technical indicators if needed |

**⚠️ Study only, NEVER copy code:**
| Project | License | Rule |
|---|---|---|
| **OpenBB** | **AGPL-v3** | Viral copyleft. Study its "connect once, consume everywhere" data-layer architecture for ideas; **never copy code into the MIT-licensed Aegis repo.** Write your own. |
| Microsoft Qlib | MIT | Safe to borrow patterns from for the ML-quant pipeline (DataServer concept, feature→signal→portfolio flow) |
| FinRL | MIT | Only relevant if RL is ever revisited (it was correctly rejected); reference only |

**Data sources (free/legal):** SEC EDGAR (unlimited, the PIT panel foundation), FMP (250/day, fundamentals), Finnhub (generous, news/calendar/insider — ships an MCP server), Alpha Vantage (25/day, ships an MCP server — relevant for the Optimus angle), FRED (rf + macro). **IEX Cloud is dead (Aug 2024) — never wire it.**

---

## 7. Recommended V2 sequence

1. **Deploy V1** → clock starts (Railway setup is the user's side; code is ready at `2d6a94a`).
2. **Step #2 leakage-safe optimization** (versioned config change; track record segments v1→v2).
3. **Optimus MCP server** (independent, high leverage — slot here or in parallel; ends the context tax).
4. **PIT fundamentals panel + validate the 4 factors** (Alphalens at real scale).
5. **Step #3 guarded rule-evolution loop** (the evolve-by-itself engine; honor both contracts in §3).
6. **DeepSeek news flag** (measured vs Brier baseline).
7. **Capability audit & consolidation** → `CAPABILITY_MATRIX.md` (can run in parallel anytime; the honesty-at-scale payoff).
8. **PM-attribution surface** as the track record approaches 24 months.

Items 2–7 each land as discrete, tested, `/clear`'d sessions with an acceptance gate, at `--effort xhigh` for the math-heavy ones (Step #2 leakage proofs, Step #3 loop) and `high`/`sonnet` for mechanical ones.

---

## The one-paragraph version for Claude Code

V1 is engine-complete — freeze the engine set, ship it, deploy, start the track record; do NOT add new engines. The remaining engine work makes existing engines honest and self-improving: Step #2 (leakage-safe HRP/BL optimization through an as-of price path, landed as a versioned config change) and Step #3 (the guarded rule-evolution loop — the registry + guards exist, the loop doesn't; it must deflate against cumulative trials and record every candidate including rejects, or it becomes an overfitting machine; it proposes rules tested out-of-sample, never an RL trader on its own P&L). V2's biggest hidden need is a capability audit of the ~85 services into validated/unvalidated/cruft, producing a `CAPABILITY_MATRIX.md` so Aegis can honestly say which signals are measured and which are descriptive — the differentiator at scale. Validate the 4 fundamental factors via a real point-in-time EDGAR panel (Alphalens). Build the DeepSeek news layer as a measured surprise-flag, not a predictor. Integrate Optimus only via its MCP server (Aegis reads-from / Optimus-owns-nothing-of-Aegis), which ends the context-loss tax this whole arc demonstrated. Use PyPortfolioOpt/Riskfolio/Alphalens/vectorbt/QuantStats freely; study OpenBB's architecture but never copy its AGPL code into the MIT repo. Every new signal or rule change must beat its baseline out-of-sample under the guards, or be documented as a negative result.
