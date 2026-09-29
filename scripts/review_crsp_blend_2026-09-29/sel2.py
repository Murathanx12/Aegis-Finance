import sys, json, math
import numpy as np, pandas as pd
N = sys.argv[1]
D = pd.read_pickle(N + '/D.pkl'); meta = json.load(open(N + '/meta.json')); D = D[meta['tested']]
hold = pd.DatetimeIndex(D.index) + pd.offsets.BDay(1)
def tb(x):
    x = np.asarray(x); x = x[~np.isnan(x)]; nb = len(x) // 3
    if nb < 5: return np.nan
    s = x[:nb*3].reshape(nb, 3).sum(1); return s.mean() / (s.std(ddof=1) / math.sqrt(nb))
def cands(mi):
    Din = D[mi]; hy = hold[mi].year; mid = int(np.median(hy)); ok = []
    for c in D.columns:
        y = pd.Series(Din[c].values, index=hy).dropna()
        if len(y) < 48: continue
        ys = y.groupby(level=0).sum(); srt = np.sort(y.values); n = int(len(srt)*.05)
        if y[y.index < mid].mean() > 0 and y[y.index >= mid].mean() > 0 and (ys > 0).mean() > .5 and srt[n:len(srt)-n].mean() > 0 and min(y[y.index != q].mean() for q in ys.index) > 0: ok.append(c)
    return ok
def pick(Din, ok, key, rho):
    corr = Din[ok].corr(); sc = {c: (Din[c].mean() if key == 'mean' else tb(Din[c].values)) for c in ok}
    out = []
    for c in sorted(ok, key=lambda c: -sc[c]):
        if rho is None or all(abs(corr.loc[c, p]) < rho for p in out): out.append(c)
        if len(out) == 4: break
    return out
res = []
for split in (2003, 2005, 2007, 2009, 2011):
    for direction in ('fwd', 'bwd'):
        mi = (hold.year <= split) if direction == 'fwd' else (hold.year > split)
        ok = cands(mi); Din = D[mi]
        for key in ('mean', 't'):
            for rho in (0.3, 0.5, None):
                p = pick(Din, ok, key, rho); bl = D.loc[~mi, p].dropna().mean(1)
                res.append({'split': split, 'dir': direction, 'key': key, 'rho': rho, 'oos_mean': bl.mean()*100, 'oos_t': tb(bl.values), 'n': len(bl), 'pick': '+'.join(p)})
R = pd.DataFrame(res)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 90)
print(R.groupby('dir')[['oos_mean', 'oos_t']].describe().round(2).T)
print(R[R.dir == 'fwd'][['split','key','rho','oos_mean','oos_t','n']].round(2).to_string())
print('fwd (select early, test later): share of 30 variants with OOS t>=2', (R[R.dir=='fwd'].oos_t >= 2).mean().round(2), 'mean OOS %/mo', R[R.dir=='fwd'].oos_mean.mean().round(3))
print('bwd: share t>=2', (R[R.dir=='bwd'].oos_t >= 2).mean().round(2), 'mean', R[R.dir=='bwd'].oos_mean.mean().round(3))
