import sys, json, math
import numpy as np, pandas as pd
N = sys.argv[1]
exec(open(__import__('os').path.join(__import__('os').path.dirname(__file__), 'sel2.py')).read().split('res = []')[0].replace("N = sys.argv[1]", "N = %r" % N))
out = []; picks = {}
for key, rho in (('mean', 0.3), ('mean', 0.5), ('t', 0.3), ('mean', None)):
    parts = []
    for Y in range(2001, 2025):
        mi = hold.year < Y
        ok = cands(mi); p = pick(D[mi], ok, key, rho) if len(ok) >= 4 else ok
        if not p: continue
        mo = hold.year == Y
        parts.append(D.loc[mo, p].mean(1)); picks.setdefault((key, rho), []).append((Y, p))
    s = pd.concat(parts).dropna()
    h = pd.Series(s.values, index=pd.DatetimeIndex(s.index) + pd.offsets.BDay(1))
    yrs = h.groupby(h.index.year).sum()
    print(f'walk-forward annual reselection key={key} rho={rho}: 2001-2024 OOS mean {s.mean()*100:+.3f}%/mo t {tb(s.values):+.2f} n {len(s)}; positive years {(yrs>0).sum()}/{len(yrs)}; 2001-12 {h[:"2012"].mean()*100:+.3f} 2013-24 {h["2013":].mean()*100:+.3f}')
FOUR = ["px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression"]
for (key, rho), L in picks.items():
    if key == 'mean' and rho == 0.3:
        for Y, p in L[::4]: print('  ', Y, p)
        cnt = pd.Series([c for _, p in L for c in p]).value_counts(); print('   most picked:', cnt.head(8).to_dict()); print('   times the FOUR were picked:', {c: int(cnt.get(c, 0)) for c in FOUR})
