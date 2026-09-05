# TIER 1 AMENDMENT — 2026-09-07 — THE GROWTH BOOK: beat SPY's terminal wealth at a declared drawdown budget

**Status: ACTIVE, amends `ROADMAP_2026-09-04_PROFIT_ENGINE.md` (B8/B9).**
**Authority:** `AEGIS_STRATEGIC_INVARIANTS.md` §1 ("maximize expected compound
return subject to explicit survival constraints; risk is a budget for measured
asymmetric opportunity, not a goal to minimize") and `OPTIMUS_OBJECTIVE.md` §0
("risk-adjusted or deliberately risk-seeking, by declared choice").

## 1. Murat's ruling (2026-09-07, his words, cleaned)

*Beating the S&P 500 on a backtest is easy; learn from other projects. The NN
focuses on noise — find a workaround with the NN and the engine. It is tragic
the engine made 30% in five years of bull market. The forward paper accounts
should learn from that too. Conservative-ATR and aggressive, five-month-old
simple strategies, beat SPY forward while the backtests fail. Run backtests
until the NN matures. Unlimited time.*

## 2. What is true, stated once

1. **The program has two rulers and has been reporting only one.** The
   RESEARCH_CLAIM ruler (excess over a beta-matched benchmark, after costs,
   family-corrected) is the right bar for the word *alpha*. Under it, nothing
   we own passes, and that verdict stands. The **product ruler** for the
   aggressive/extreme-growth personalities is *after-cost terminal wealth at
   a declared drawdown budget, with survival guaranteed and beta reported*.
   Under it, the neural ensemble's backtest (TW 49 vs SPY 14, β 1.33, maxDD
   to be measured) and the forward lanes' beta tilts are legitimate
   candidates. We never scored anything under the product ruler. That is
   the gap, and it is ours.
2. **Beta is allowed. Hidden beta is not.** Every growth-book receipt
   prints β, the intercept and its t, maxDD, CVaR₅, P(ruin) at the largest
   admissible book, and the leverage-neutral comparison (TW at SPY's own
   realized volatility). A book that wins only by borrowing beta must say so
   in its first line; it may still win.
3. **The old timing engine's 30% was cash drag.** Forward books never hold
   cash without a thesis; the parking orbit is the benchmark. Already law
   (B2, B9); restated because it is the reason the tragedy happened.
4. **Forward n is three months.** The website lanes' ordering vs SPY is
   inside the noise (SE on an annualized Sharpe ≈ 2.1). The lanes *are*
   evidence that beta-tilted books beat SPY in a bull leg, which is exactly
   what the product ruler predicts; they are not evidence of skill.
5. **"Learn from other projects"** means the published growth recipes:
   time-series momentum / trend filter on the index (Faber 2007; Moskowitz-
   Ooi-Pedersen 2012), volatility-managed portfolios (Moreira-Muir 2017),
   volatility-scaled momentum that removes momentum crashes (Barroso-Santa-
   Clara 2015; Daniel-Moskowitz 2016), quality-momentum tilts, leveraged
   index with a trend filter, risk-parity style leverage. Each is a genome
   in the evolution lab, tested on OUR tape with OUR costs, not quoted.

## 3. The Growth Book lane (PRODUCT_EXPERIMENT; runs until the NN matures)

**Objective (declared, hashed before the first run):**
`maximize after-cost terminal wealth 1999-2024 subject to maxDD ≤ 1.25 × SPY's maxDD over the same months, monthly CVaR₅ ≤ 1.5 × SPY's, no month worse than −40%, gross ≤ 2.0×, financing at RF + 100 bps on borrowed notional.`
Report every candidate at 10 and 25 bps/side. Benchmarks in the same table:
SPY TR; SPY TR levered to the drawdown budget (the honest "beta only"
benchmark); equal-weight tradable universe.

**Development / sealed test:** development 1999-2015 (search freely; CPCV +
PBO for ranking); **sealed test 2016-2024** (the bull era Murat is judged
against) opened once per frozen champion; family-max over every genome
looked at; DSR reported. A champion that beats levered-SPY on the sealed era
starts forward paper on hack4 under a frozen contract with the B2 hold
fields and the leverage ladder 1× → 1.5× → 2×.

**Genome families (generation 0):** SPY buy-and-hold · SPY + 10-month trend
filter (cash → T-bills when below) · SPY vol-managed (target vol = realized
SPY vol; Moreira-Muir) · 12-1 momentum top-50 VW, floored · vol-scaled
momentum · quality-momentum (profitability × momentum) · lgbm_clf top-50 ·
nn_pre_causal ensemble top-50 · each of the above with a drawdown-control
overlay (scale exposure by trailing 3-month drawdown) · each with a
trend-filter gate · combinations at 50/50 · levered variants to the
drawdown budget. LLM agents may propose mutations naming the closest corpse.

**The NN's job in this lane (the workaround):** not selection. A sequence
model on market/regime features (realized vol, term structure, credit
spread, breadth, drawdown state, the four unsupervised states if they ever
validate) forecasting the **next-month return distribution of each book**
(quantile heads q05/q50/q95, calibrated). Exposure = fractional-Kelly on the
forecast, capped by the drawdown budget. **Graded against the Moreira-Muir
baseline** (trailing realized vol only): the NN "matures" when its
vol-targeting beats trailing-vol targeting on after-cost TW at equal maxDD
in the sealed era with DSR > 0.95. Until then it is a shadow and the
baseline trades. Every retrain is walk-forward; the sealed era is never
seen in training.

**Forward paper learns from it:** hack4 runs the frozen champion; the
nightly report attributes P&L into β × market, intercept, sizing, costs,
and cash drag; the leverage rung advances only on compound wealth after
drawdown over ≥ 20 sessions (B9).

## 4. What does not change

Alpha claims keep the RESEARCH_CLAIM ruler. Sealed test era opened once.
No LLM authority over capital. Costs never omitted. Survival constraints
are hard. Every receipt prints β first. The word "beats SPY" is never
written without "at β = x, maxDD = y, after z bps".

## 5. Gate

A frozen growth champion with: sealed-era TW > levered-SPY TW at equal
drawdown budget, after 25 bps, DSR > 0.95 over the family, positive in ≥ 2
of 3 development eras, β and intercept printed, forward paper started on
hack4 with a 20-session rung schedule. Or the honest result: "at this
drawdown budget nothing beats levered SPY after costs", with the family
size — which would itself be worth knowing.
