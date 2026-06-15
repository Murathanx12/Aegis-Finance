# Volatility-Managed Momentum (TRIAL-VMM) — 2026-06-15

> Strategy-improvement 3a (Murat's priority list). Barroso–Santa-Clara vol-scaling
> on broad-universe 12-1 momentum, through the same DSR/PBO gate that rejected
> thematic. `engine/research/vol_managed_momentum.py`. **Two findings: one a clean
> win, one a trap the gate did NOT catch — both worth keeping.**

## Results (2015-06 → 2025-06, 10 bps, vs SPY)

| Strategy | CAGR | Sharpe | Max DD | CAGR @ SPY-vol |
|---|---|---|---|---|
| SPY buy & hold | +12.8% | 0.75 | −33.7% | +12.8% |
| Momentum, unmanaged | +35.0% | **1.17** | −41.3% | +21.8% |
| Vol-managed (tv 0.10, lb 63) | +12.5% | **1.17** | **−13.5%** | +21.9% |
| Vol-managed (tv 0.20, lb 63) | +25.2% | 1.17 | −25.7% | +21.9% |

PBO 0.37, DSR 1.000 vs 24 trials → the mechanical gate reads **PASS**.

## Finding 1 (clean win, ADOPT): vol-management is real, leakage-safe risk control

Vol-scaling did exactly what Barroso–Santa-Clara say: it held Sharpe **constant**
(1.17 → 1.17 — vol-targeting is a leverage transform, Sharpe is scale-invariant)
while **cutting max drawdown from −41% to −13%** at tv=0.10. You dial the target
vol to choose your risk/return point on a fixed Sharpe ray: tv 0.10 → +12.5% at
−13.5% DD; tv 0.20 → +25.2% at −25.7% DD. The construction is lagged (uses only
past vol) → no look-ahead. **This is the cleanest "improve the method" result of
the arc: a universe-independent risk overlay worth running on whatever strategy
goes forward** (same family as the ATR exit, but smoother and portfolio-level).

*Caveat:* the Barroso Sharpe *boost* comes from dodging momentum **crashes**
(2009-style +163% loser rallies). Our 2015–2025 window has no such event, so only
the vol/drawdown-control half shows — the Sharpe-boost half is untested here.

## Finding 2 (the trap the gate MISSED): the 1.17 Sharpe is survivorship-inflated

**The "PASS" is NOT a clean SPY-beat, and here is exactly why.** The broad
universe is `config.stock_universe` — **today's** large-caps (NVDA, AVGO, AAPL…).
Running momentum inside a basket of *stocks already known to have become winners
by 2026* is textbook survivorship bias. The +35% / 1.17 Sharpe is inflated by the
universe definition, not by skill. DSR=1.000 saturated **because** the Sharpe was
artificially high — **the gate deflates against multiple testing, it does NOT and
cannot see a biased universe.** Same survivorship artifact that inflated
EW-themes; it just slipped past the gate this time and printed "PASS."

**Lesson (write to the brain): the DSR/PBO gate is necessary but not sufficient —
survivorship is the silent killer it can't catch. A point-in-time / delisted-
inclusive universe is required before ANY absolute alpha claim. The only fully
honest test remains forward (the paper lanes).**

## Verdict & next

- **TRIAL-VMM (risk overlay): ADOPT-candidate.** Vol-management is a legitimate,
  leakage-safe drawdown control. Pre-register it forward as an overlay on a paper
  lane (alongside / instead of the ATR exit) — measured on forward NAV, where
  survivorship can't contaminate it.
- **TRIAL-VMM (alpha claim): NOT proven.** Do NOT register a "momentum beats SPY"
  lane off this number — the universe is survivor-biased. The real alpha test
  needs a point-in-time universe (historical index membership incl. delisted) —
  queued as the prerequisite for any momentum-alpha forward lane.
- Re-confirms the path: keep momentum + **vol-management/exits as risk control**,
  prove absolute edge **forward**, never trust a backtest Sharpe without a
  survivor-free universe.
