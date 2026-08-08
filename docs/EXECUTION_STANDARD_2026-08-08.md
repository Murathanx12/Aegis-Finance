# EXECUTION STANDARD — Simulate first, paper second (FROZEN 2026-08-08)

**Binding rule (Murat, 2026-08-08, via GPT directive, adopted):**
**NO NEW STRATEGY ENTERS A PAPER LANE UNTIL IT HAS SURVIVED A SERIOUS
HISTORICAL SIMULATION AND SHOWN A MATERIAL, REPEATABLE NET ADVANTAGE
OVER SPY.** Paper lanes become forward/operational validation, not
discovery. High-volatility, concentrated, asymmetric strategies are
explicitly allowed — the bar is evidence quality, never risk level.
Existing 10 lanes keep their clocks (rule is forward-looking; the track
record is not retroactively touched).

## 1. Reconciliation with canon (why this is consistent, not a reversal)

The replay night proved 72-month confirm windows are UNDERPOWERED for
plausible net edges (SPY itself prints t≈1.1). That made forward lanes
"the adequate instrument" — *for short windows*. The era instrument then
proved the counterpart: over LONG windows the money question IS
answerable in backtest (CBOperProf net t 4.30 over 17 years at punitive
costs). So the standard is: **money claims from backtests require long,
multi-regime, survivorship-free panels + controls + untouched holdouts.**
Short-window backtests remain direction checks. Paper lanes validate
operations and the unseen regime. Canon line updated accordingly; nothing
else in canon changes (pre-register before compute, placebo gates,
one-shot holdouts, LLM narrates / engine computes).

## 2. The stage ladder (every strategy moves in order)

1. Research evidence (literature/mechanism)
2. Historical backtest evidence (era panel + modern panel, controls)
3. Historical event/news replay evidence (LLM strategies only)
4. Full historical daily simulation (sequential, belief-updating)
5. Paper-account forward validation (operational questions only)
6. Live capital (Murat's decision, outside scope)

## 3. Graduation gates (per strategy, receipt = one-page scorecard)

G1 material historical outperformance (net) · G2 untouched holdout pass
(failure recorded, no quiet re-runs; post-hoc edits contaminate → new
holdout required) · G3 robustness to parameter/cost/universe
perturbation · G4 beats controls (random-with-identical-turnover,
factor, sector-neutral as appropriate) · G5 plausible economic
mechanism · G6 not driven by one stock/year/event · G7 survives full
daily simulation · G8 no unacceptable catastrophic-impairment
probability · G9 → paper lane (Murat flips flag).

**"Material" (frozen default, overridable per registration):** net excess
CAGR ≥ +3%/yr vs SPY over the full available panel AND positive net
excess in ≥ 4 of 6 regime blocks (pre-2008, GFC, post-crisis bull, COVID,
2022 bear, 2023+ mega-cap) AND holdout-positive. Ranking objective:
excess terminal wealth subject to a ruin constraint (catastrophic
impairment = modeled P(>60% drawdown) beyond registered tolerance) —
NOT Sharpe-maximization; aggressive books survive if payoff justifies
risk. Report the full metric slate + terminal-wealth distribution, and
performance BY regime, always.

**Two outputs, always:** WINNERS and UNRESOLVED. Unresolved ≠ dead —
"the test was structurally incapable" is a recorded verdict class
(that distinction is NEGATIVE_RESULTS §34's lesson, now standing).

## 4. What already exists (do NOT rebuild — extend)

| GPT ask | Existing machinery |
|---|---|
| Immutable experiment IDs, exact reproduction | TRIALS/registry.jsonl + frozen specs + hashes (179 candidates accounted) |
| Train/validation/holdout separation | Explore 2004-2018 / confirm 2019-2024 one-shot discipline; era panel windows registered per use |
| Control arms incl. random-identical-turnover | Placebo-gate standing rule; REAL-NULL-2 floors (20k information-free nulls); family-null veto |
| Multiple-testing accounting | Registry counts every variant; lfdr-anchored promotion bar t≈4.0 from measured 3/196 base rate |
| Realistic costs | KO cost model (measured largemid wedge 3.73bps vs flat 25); KO-primary rule for largemid |
| Survivorship-free long panel | CRSP 1962-2001 spine (real delisting returns) + post-2002 panel = 63yr |
| Resurrection protocol | ALREADY RAN ONCE: kill-audit taxonomy (receipt-based vs threshold-only) → one-shot replay → 10 adoptions confirmed out-of-sample. Standing queue: si_chg_low (top), 32 below-cap survivors unread, 22 largemid KO re-adjudication, 13 scan-error triage. GPT's A–K classes map onto the kill-audit taxonomy; extend, don't redo |
| Gate-power calibration | GATE-M1/RECAL-1: gates are measured against injected edges before their kills are trusted |
| "Why did this win" audit | Attribution machinery (long-leg share, factor decomposition, capture diagnostics) — §28/§17 receipts exist |

**Genuinely new builds (the real work):** (N1) portfolio-level factory
harness with the multi-dimensional objective + scorecards; (N2) LLM
historical event-replay environment; (N3) full sequential daily
simulator with belief updating; (N4) LLM/non-LLM baseline bank.

## 5. Gaps in the directive, filled (the points Murat asked me to add)

1. **LLM replay contamination — the big one.** An LLM cannot "believe it
   is 2021": it has READ 2021–2025. R1 measured historical replay of
   claim generators as near-worthless when unmasked; KTD-Fin's ablation
   showed the ticker name alone drives behavior. Therefore the replay
   environment REQUIRES the masking protocol: anonymized tickers,
   shifted/masked dates, entity-scrubbed text — plus **contamination
   canaries** (periodically ask the masked model to identify the
   company/period/outcome; if it can, the sample is burned). Unmasked
   replay is diagnostic-only, never evidence. Forward claims (the ledger)
   remain the gold standard; replay produces *bounds and baselines*, not
   proof of LLM alpha.
2. **PIT news source hierarchy.** Yahoo Finance is survivorship-biased
   and not point-in-time — direction checks only. Frozen hierarchy:
   CRSP/Compustat (money claims) > SEC EDGAR full-text (8-K, 10-K/Q,
   Form 4 — immutable original text with true timestamps; THE spine for
   event replay) > FDA archives > GDELT (timestamped historical news) >
   Bigdata.com/RavenPack MCP (rich tagged news history; attended sessions
   only — interactive auth may not survive headless runs) > FMP >
   yfinance. Every replay record carries publication/availability/
   retrieval timestamps + source version.
3. **Delisting returns** must flow through the simulator (we have real
   dlrets pre-2002; post-2002 handled in panel) — a factory that drops
   delisted names re-imports survivorship bias through the back door.
4. **Regime look-ahead.** PF-REGIME-SWITCH and all regime-conditioned
   tests must compute regime labels from data available at t (walk-
   forward), never from full-sample regime fits. Regime *reporting*
   blocks may be defined ex-post; regime *trading inputs* may not.
5. **Compute realism for the daily simulator.** LLM-in-the-loop for
   every simulated day × years = cost explosion. Design: quant layer
   runs daily; LLM fires only on event triggers (sampled N per class,
   pre-registered N); responses cached immutably keyed by (masked
   context hash); spend guards live. First forecast per event is
   immutable — no self-revision (leakage).
6. **Memory ablation ladder** (GPT §15 = our queued novel experiment,
   extended): arms A no-memory / B raw-evidence / C structured event
   memory / D calibrated claim-type memory / E narrative memory — run
   as a pre-registered two-arm-per-comparison design inside the replay
   environment. This is the field's missing experiment (0-for-19).
7. **Baseline bank before LLM credit** (GPT §13, adopted verbatim):
   historical base rate, logistic regression on event features, analyst
   consensus where applicable, factor model. The LLM earns attention
   only above the best cheap baseline.
8. **Overnight campaign accounting.** Every variant auto-registers into
   the registry with a family ID; the night's total experiment count is
   printed on every scorecard (the 10,000-trials trap is answered by
   the base-rate machinery, but only if the denominator is honest).
9. **Execution realism carried from lane lessons:** rebalance timing
   (16:30 ET), idempotency guards, panel-cache poisoning fix — the
   simulator inherits the production rebalance code path where possible
   so G7 actually tests what paper will run.
10. **GP/RISK-SAT sequencing change:** the pending GP lane flag now
    waits for its factory scorecard (it already holds era receipts —
    likely the first graduate). RISK-SAT-1 (conviction satellite) also
    runs through the harness as PF-RISK-SAT-1 first. Nothing seeds
    until it graduates. This supersedes the "awaiting flag" status.

## 6. Immediate task order (frozen; matches GPT §25 merged with ours)

T1 this doc (rule frozen) · T2 factory harness (overnight-capable) ·
T3 re-run PF-1 six under the harness before inventing new strategies ·
T4 LLM event-replay harness (earnings, FDA/PDUFA, insider clusters
first — SEC-anchored, masked) · T5 PIT data controls + source hierarchy
enforcement · T6 baseline bank · T7 full daily simulator (sequential
belief updates; measures "does learning improve performance over
simulated years, not just change behavior") · T8 resurrection queue
processing (existing queue first) · T9 overnight campaigns (variants,
combinations, interactions — standalone + marginal + interaction
contribution reported per signal) · T10 graduates → paper (Murat's
flags).
