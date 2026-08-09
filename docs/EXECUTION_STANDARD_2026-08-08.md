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

---

# AMENDMENT 2026-08-09 — G4a factor gate, the FACTOR-HARVEST label, and
# the NEAR-MISS verdict class

**Forward-only. PF-1 is NOT re-scored under this amendment** — its verdicts
stand as adjudicated under the rule frozen on 2026-08-08. This amendment binds
every registration opened on or after 2026-08-09.

Written because PF-1 produced a strategy that beat the market by +5.21 %/yr net
over 59.5 years, at lower drawdown, beating 100 turnover-matched random books —
and whose FF5+UMD alpha was +0.89 %/yr with t = 0.71. The old rule had no way to
say what that is.

### (a) G4a — the factor gate, and the two things a strategy may graduate as

G4 (beats controls) gains a sub-gate. Every money run reports a CAPM and an
FF5+UMD (Fama-French 5 + momentum) regression of monthly net excess returns.

**G4a — ENGINE SKILL bar:** annualized FF5+UMD alpha **≥ +2.0 %/yr with
t ≥ 2.0** over the full evaluated window. Registered here, before the PF-2
compute that will be judged by it.

Consequences, both directions:

- A strategy passing every gate **including G4a** may be claimed as **ENGINE
  SKILL** — the engine found something the standard factors do not span.
- A strategy passing every gate **except G4a** is **not** a failure. It
  graduates as a **FACTOR-HARVEST PRODUCT**: a well-built, cost-aware,
  low-drawdown implementation of premia that are already public. This is a
  legitimate deliverable and may proceed down the stage ladder. It may **never**
  be described as engine alpha, model skill, or a discovery, in any document,
  UI string, or lane label.
- The distinction is a labelling gate, not a permission gate. Both labels still
  require G1-G9. Neither label is available to a strategy that fails them.

**Why t ≥ 2.0 and not the lfdr-anchored t ≈ 4.0 used for claim promotion:** the
t ≈ 4.0 bar governs *forward* claim promotion in the belief ledger, where the
multiple-testing denominator is thousands of claims. G4a governs the *labelling*
of a small, pre-registered set of portfolio candidates whose returns have
already cleared an independent placebo gate; 2.0 is the conventional
factor-model bar (Fama-French, Novy-Marx) and is the right instrument here. The
two bars are not interchangeable and neither replaces the other.

### (b) The verdict taxonomy gains NEAR-MISS(gate)

`WINNER` · `NEAR-MISS(<gate>)` · `UNRESOLVED(<reason>)` · `FAILED`

**NEAR-MISS(gate)** = failed **exactly one** gate, with the placebo gate PASSED
and net excess positive. It records the specific gate in the verdict string.

A NEAR-MISS does **not** graduate and does **not** seed a lane. Its only
privilege is that a successor addressing that one gate may be registered without
being treated as a rescue — and the successor must carry its own prediction and
be judged on its own receipts. Post-hoc promotion of a variant that happened to
clear the failed gate remains forbidden; that is precisely the cherry-picking
this taxonomy exists to make visible rather than tempting.

### (c) Recorded measurement — what the turnover-matched placebo actually tests

PF-1 ran 600 placebo books across six strategies. Measured properties, now
standing:

- Random selection at realistic turnover **loses** −2 to −3 %/yr on broad
  universes; trading costs alone sink it. Any strategy with positive net excess
  clears such a band nearly automatically.
- The band **widens where books are concentrated or windows are short** — p95
  went positive (+0.23%, +0.25%/yr) for the 10-name and 15.8-year specs versus
  −0.30% to −0.66% for broad-universe specs. Both PF-1 placebo failures occurred
  there.

Therefore: **the placebo gate is a test of construction artifacts and of luck in
thin books — it is not, and must never be cited as, evidence that an edge is
more than factor exposure.** That question is G4a's alone. The equal-weight-
universe control and the FF5+UMD regression are the sharp instruments; the
placebo band stays as a necessary but weak gate.

---

# AMENDMENT 2026-08-09 (second) — the PRODUCT TRACK and its own gate set

**Forward-only. Nothing already adjudicated is re-scored or re-labelled under
this amendment** — in particular `PF-ENGINE-ALPHA-2` keeps its PF-2 verdict of
FAILED, and is *not* retro-promoted. This amendment binds registrations opened
on or after 2026-08-09 (second amendment).

Authorized by Murat 2026-08-09 in answer to the open question raised in the
PF-2 verdict: *is the regime-breadth gate right for long-only factor books?*

**The answer adopted is: do not loosen the gate — split the claim.** Requiring
positive excess in ≥4 of 5 regime blocks is the correct bar for the claim *"our
engine is skilled."* It is the wrong bar for a different, also-honest claim:
*"this is a better thing to buy than anything you could otherwise pick."* One
gate set was being asked to adjudicate two different sentences. So there are now
two tracks, and a candidate must declare which one it is registered under
**before** its compute.

### (a) The two tracks

| | ENGINE-SKILL TRACK | PRODUCT TRACK |
|---|---|---|
| the sentence | the engine found something the standard factors do not span | this is a better investable holding than the alternatives |
| G4a FF5+UMD α ≥ +2 %/yr, t ≥ 2.0 | **GATING** | reported, not gating |
| regime breadth ≥4/5 blocks | **GATING** | **REPORTED AS DISCLOSURE, not gating** |
| product bar (below) | reported | **GATING** |
| G1 materiality, G3 placebo, G8 ruin, grid stability | gating | gating |
| **G2 holdout + G7 daily simulator** | **required before paper** | **required before paper** |
| may be called engine alpha / model skill / a discovery | yes | **never, in any document, UI string, or lane label** |

### (b) The product bar (registered here, before the compute it judges)

A product-track candidate passes its bar when, on the full evaluated window
excluding the holdout, it beats **every** pre-registered investable alternative
on **excess terminal wealth**, subject to the ruin constraint P(maxDD > 60 %)
≤ 0.20. The alternative set must be frozen in the registration and must contain
at minimum: the benchmark itself, the equal-weight universe, a simple
value+profitability screen, and a naive multifactor mix — all net of the same
cost model. "Beats the market" alone is not a product bar; the comparison is
against what a person could actually have bought instead.

### (c) Mandatory disclosure, because a non-gating metric must still be printed

A product-track graduate must publish, in the same artifact as its headline
number: per-regime-block excess (including every negative block, named), the
worst calendar year, time underwater, and the FF5+UMD decomposition showing
**which known premia it is harvesting**. The label exists so a user knows what
they are buying. A product-track result presented without its negative blocks is
a violation of this standard, not an oversight.

### (d) What this amendment explicitly does NOT do

- It does not lower any bar for engine-skill claims. G4a and regime breadth are
  unchanged there.
- It does not create a path to a lane that skips G2 or G7. Both tracks still
  require the holdout and the daily simulator before paper.
- It does not retro-apply. `PF-ENGINE-ALPHA-2` is FAILED and stays FAILED; if it
  is to run on the product track it must be registered fresh, under a new ID,
  with the honest disclosure that its product-bar numbers were already computed
  and are therefore not blind (see `TRIALS/PREREG_PF_ENGINE_ALPHA_PRODUCT_2.md`).

The reason for (d) is the same reason the standard exists: a gate that is
rewritten to admit the candidate that just failed it is not a gate. Splitting a
claim into two honestly-labelled claims is legitimate; moving the line is not.
