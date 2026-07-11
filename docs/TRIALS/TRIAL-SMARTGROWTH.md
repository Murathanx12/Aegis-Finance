# TRIAL-SMARTGROWTH — concentrated smart-money growth basket (forward test)

> **Pre-registered 2026-07-12.** Murat's thesis, made falsifiable: "don't hide
> in funds — pick stocks like I did this year, from the tech market, forecast
> prices, and what real investors are doing." This trial commits a FROZEN
> selection rule built from the engine's own pre-registered signal streams and
> starts its forward clock. Descriptive until proven; never arms a lane; a
> NAV lane seed (attended) is the ADOPT action, not the starting point.

## Selection rule (frozen)

Weekly, over the candidate universe (screener universe ∪ tickers with a live
`congress_score` / `ark_score` / `multifactor_score` PIT row):

    component z-scores across the cross-section, then
    smartgrowth_score = 0.35·momentum(multifactor_score)
                      + 0.25·revisions(revisions_score)
                      + 0.20·smart_money(congress_score + ark_score)
                      + 0.20·analyst_upside(clipped)

- `analyst_upside` = targetMeanPrice/price − 1, **clipped to ±50%**, only
  counted with ≥ 4 analysts — Murat's "forecast prices" input, included
  deliberately DESPITE our own T10 finding that raw implied upside is a flawed
  level (KYTX +286% fluke); the clip + analyst-count floor are the containment.
  Its 0.20 weight is part of the hypothesis, not tunable.
- A component missing for the whole cross-section (e.g. ark_score before its
  21-session baseline) drops out and the remaining weights renormalize; the
  payload records which components were live. A component missing for one
  ticker contributes its cross-sectional mean (z=0).
- **Basket:** top 10 by score, equal-weight. No sector cap (the tech tilt is
  the thesis). Weekly refresh, snapshotted as `smartgrowth_pick:{ticker}` =
  0.10 with full component payloads.
- **Fetch bound (frozen):** analyst upside is fetched for the top-30 names by
  the 3-component preliminary blend; the final ranking is over those 30.

## Primary metric & decision rule

- **Primary:** forward return of the weekly-refreshed EW top-10 basket
  (computed from PIT pick snapshots + subsequent prices, costs 10 bps/side on
  turnover) **vs QQQ** — the benchmark Murat's thesis competes with — over the
  trial window. Co-primary: max drawdown vs QQQ (reported, must not be
  catastrophically worse: > 1.5× QQQ's DD = reject regardless of return).
- **Adopt** (→ seed an attended NAV lane, new YAML + hash): basket beats QQQ
  total return over ≥ 6 months AND Sharpe not worse than QQQ − 0.15.
- **Reject:** trails QQQ by ≥ 5 pts total return at 12 months, or the DD
  condition trips.
- **Earliest decision:** 2027-01-12. Monthly reads reported only.
- **Crash-event override:** SPY drawdown ≥ 20% defers decisions ≥ 6 months
  past trough. **Contamination clause:** a defect in any input stream excludes
  affected weeks, documented in NEGATIVE_RESULTS.md.

## Honest prior

Mixed-to-weak. Concentrated momentum baskets have the strongest documented
premium but brutal crash behavior (momentum crashes); analyst upside is
documented-flawed (our T10); congressional/ARK following is likely faded/
negative (TRIAL-CONGRESS-IC / TRIAL-ARK-IC priors). The blend may still work
as a filter stack — that is exactly what the forward clock decides. Murat's
own 2026 returns are one hot year of survivor evidence and are NOT data here
(canon: personal returns are never training data).

## What this rule may NOT do

- Trade, size, or arm anything; no buy/sell framing in any UI surface — the
  basket renders as "measured candidates" only until adopted.
- Change weights, clip, floor, basket size, cadence, or benchmark mid-trial
  (annotations only; a change = abandon + successor).
- Be evaluated on any backtest (T7 — forward only).

## Status

- ✅ 2026-07-12: `smartgrowth.py` (frozen scorer + weekly collector on the PIT
  store) wired into `_daily_check`; registry row via `ensure_smartgrowth_trial`.
  First picks snapshot on the next daily check; several components start
  sparse (congress just began accruing, ark_score self-arms ~mid-Aug) — the
  payload records live components per week.
- ⬜ First monthly read (reported only).
- ⬜ ADOPT path: attended NAV lane seed (own YAML + hash) per seed-a-lane.
