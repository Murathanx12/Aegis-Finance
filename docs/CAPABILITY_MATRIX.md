# Capability Matrix — what's measured vs. what's descriptive

> **V2 Goal 3 deliverable** (was missing; this is the first pass, 2026-06-14).
> Classifies every surfaced capability so a visitor can tell, at a glance, what
> carries a *measured out-of-sample skill number* from what is honest-but-unproven
> context. The rule (canon): a signal shown without a measured number is labelled
> **descriptive**; nothing is called "it works" until a forward number says so.
>
> **Status:** ~104 services exist; this pass classifies the load-bearing /
> user-surfaced ones with evidence. The long tail is marked **⏳ UNAUDITED** with
> the method to finish below. Completing it is BACKLOG M5/H-class follow-up.

**Classes:**
- 🟢 **VALIDATED** — has a measured, out-of-sample skill/error number (cite it).
- 🟡 **DESCRIPTIVE** — labelled, no skill claim; shown as context only.
- 🔧 **METHODOLOGY/INFRA** — discipline & plumbing, not a market signal.
- ⏳ **UNAUDITED** — built, plausibly correct, not yet classified.
- 🗑 **CRUFT** — superseded/unused (none confirmed yet; flag during the audit).

---

## 🟢 Validated (measured number on record)

| Capability | Number | Source / caveat |
|---|---|---|
| Crash model, 3-month | Brier **0.046** vs base-rate 0.12 | `BACKTEST_RESULTS.md`. **Caveat:** single-path walk-forward, ~7 events, **no CI yet** (BACKLOG M2). "Modest." |
| Regime detection | 5/5 labelled periods correct | `BACKTEST_RESULTS.md` Task 2 (in-sample stress checks). |
| Risk score stress | 6/6 elevated when expected | `BACKTEST_RESULTS.md` Task 3. |
| Overfitting guards (PSR/DSR/PBO/Harvey-Liu) | known-answer tests pass | `engine/validation/overfitting.py` — these *gate* adoption; validated as machinery, not a market edge. |
| Monte Carlo (Merton-corrected) | output range matches consensus (~5.9% 5Y) | `monte_carlo.py`; compensator correct. Range-validation, not predictive skill. |

## 🟡 Descriptive (labelled, no skill claim — by design)

| Capability | Why descriptive |
|---|---|
| **Fragility composite** (`fragility.py`) | Equal-weighted, never fitted; forward Brier accruing under TRIAL-CRASH (`insufficient_forward_data` until ≥30 matured obs). |
| **LPPLS bubble flag** | Predictive skill adversarially refuted ×2; structure-only, never arms a lane. |
| **SOS / Sahm recession flags** (`macro_indicators.py`) | Coincident-to-lagging by construction; no leading-indicator language (string-pinned in tests). |
| **Crash timeline (60-mo)**, **survival/Cox**, **BOCPD changepoint** | Model outputs without a forward skill number. |
| **Momentum / cross-sectional rank** | Documented as descriptive, not alpha (V2_ROADMAP). |
| **Options intelligence, insider signal, news/GDELT/FinBERT, Google-Trends** | Context features; news must pass the Brier gate (Goal 5) before any signal claim. |
| **Factor grades (Value/Growth/Profitability/Revisions)** | Not Alphalens-validated yet (Goal 4 → `FACTOR_VALIDATION.md`). |
| **Copula tail-dep, turbulence/absorption, net-liquidity, liquidity risk (Amihud/Kyle/Roll), bubble/systemic** | Risk descriptors; feed fragility, not standalone signals. |

## 🔧 Methodology / infrastructure (not a market signal)

Portfolio construction (HRP/BL/risk-parity/Mean-CVaR — HRP under live TRIAL-001),
attribution (Brinson/MCTR), stress testing, drawdown/rolling-returns, retirement
MC, savings, conformal intervals, drift detector, data_quality, cache,
reference/paper-lane engine, experiment registry, evolution loop, polygon/data
fetchers, SDK.

## ⏳ Unaudited (the long tail — finish the pass here)
~60+ remaining services (e.g. `volatility_analytics`, `sector_rotation`,
`risk_number`, `technical_analysis`, `earnings_intelligence`, `economic_surprise`,
`covariance` denoising, `external_validator`, `regime_validator`, ESG/FX/crypto/
bond/commodities v13 surfaces). Each needs one line: class + evidence + whether
user-surfaced.

### Method to complete (one sitting)
1. `git ls-files backend/services` → for each, grep where it's exposed (router/UI).
2. If a router surfaces it → does the surface carry a measured number? → 🟢/🟡.
3. If nothing surfaces it and nothing imports it → 🗑 candidate.
4. Record each row; **surface area must shrink or hold, never grow** (Goal 3).
