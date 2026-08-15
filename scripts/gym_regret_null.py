"""Null distribution of 'regret against the ex-post best of 17 policies'.

If a random / always-hold decision already shows large positive regret under
this denominator, then dataset zero's +26.5pp says nothing about the engine.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\mrthn\aegis-finance")
from backend.services.research_gym.policies import POLICY_MENU, run_policy

import yfinance as yf

spy = yf.download("SPY", start="1993-01-01", end="2026-08-14",
                  progress=False, auto_adjust=True)
px = spy["Close"].squeeze().dropna()
rets = px.pct_change().dropna().values  # FRACTIONS: _apply does 1 + e*r
print(f"SPY daily returns: {len(rets)}")

H = 63
rng = np.random.default_rng(20260815)
N = 4000
starts = rng.integers(0, len(rets) - H - 1, size=N)

names = list(POLICY_MENU)
rows = []
for s in starts:
    win = rets[s:s + H]
    res = {n: run_policy(n, win, cost_bps=5.0).net_return_pct for n in names}
    best = max(res.values())
    rows.append((best, res["hold"], res["sell_100"],
                 res[names[rng.integers(0, len(names))]]))

arr = np.array(rows)
best, hold, sell, rand = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]

print(f"\nNULL REGRET vs ex-post best of {len(names)} policies, H={H}d, n={N}")
print(f"  always-HOLD      mean {np.mean(best-hold):6.2f}pp  median {np.median(best-hold):6.2f}pp")
print(f"  always-SELL_100  mean {np.mean(best-sell):6.2f}pp  median {np.median(best-sell):6.2f}pp")
print(f"  RANDOM policy    mean {np.mean(best-rand):6.2f}pp  median {np.median(best-rand):6.2f}pp")
print(f"\n  P(hold regret > 26.5pp)   = {np.mean((best-hold) > 26.5):.3f}")
print(f"  P(random regret > 26.5pp) = {np.mean((best-rand) > 26.5):.3f}")
print(f"  P(hold regret > 1.0pp = MATERIAL_EDGE_PCT) = {np.mean((best-hold) > 1.0):.3f}")

# Conditional on high-stress starts, which is where the 5 sells live.
vix = yf.download("^VIX", start="1993-01-01", end="2026-08-14",
                  progress=False, auto_adjust=True)["Close"].squeeze().dropna()
v = vix.reindex(px.index).ffill().values[1:]
hi = np.where(v[:len(rets) - H - 1] >= 25)[0]
print(f"\nHigh-stress starts (VIX>=25): {len(hi)}")
sub = rng.choice(hi, size=min(2000, len(hi)), replace=False)
rows2 = []
for s in sub:
    win = rets[s:s + H]
    res = {n: run_policy(n, win, cost_bps=5.0).net_return_pct for n in names}
    rows2.append((max(res.values()), res["hold"], res["sell_100"]))
a2 = np.array(rows2)
print(f"  VIX>=25 | always-HOLD regret     mean {np.mean(a2[:,0]-a2[:,1]):6.2f}pp")
print(f"  VIX>=25 | always-SELL_100 regret mean {np.mean(a2[:,0]-a2[:,2]):6.2f}pp")

# Effective independent sample size of the VIX>=35 bucket.
v_all = vix.values
n35 = int((v_all >= 35).sum())
grp, prev, gaps = 0, -99, []
idx = np.where(v_all >= 35)[0]
for i in idx:
    if i - prev > 21:
        grp += 1
    prev = i
print(f"\nVIX>=35 daily obs: {n35}; distinct episodes (>21d apart): {grp}; "
      f"overlap-adjusted n = {n35/63:.1f}")
