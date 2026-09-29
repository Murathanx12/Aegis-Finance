import json, math, itertools, sys
import numpy as np, pandas as pd
sys.path.insert(0, r'C:/Users/mrthn/aegis-finance')
from backend.services import crsp_rebuild as CR
S = sys.argv[1] + '/'
D = pd.read_pickle(S + 'D.pkl'); meta = json.load(open(S + 'meta.json'))
tested, cands = meta['tested'], meta['cands']
D = D[[c for c in tested if c in D]]
print('n tested with series', D.shape[1], 'cands', len(cands))
FOUR = ["px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression"]
def tblk(x):
    x = x[~np.isnan(x)]; n = len(x)
    if n < 30: return np.nan
    nb = n // 3; s = x[:nb*3].reshape(nb, 3).sum(1)
    return s.mean() / (s.std(ddof=1) / math.sqrt(nb))
X = D.values
def blend_t(idx):
    m = X[:, idx]; ok = ~np.isnan(m).any(1)
    return tblk(m[ok].mean(1)), m[ok].mean(1).mean()
t0, m0 = blend_t([D.columns.get_loc(c) for c in FOUR]); print('chosen t (my blocks)', round(t0,3), 'mean', round(m0*100,3))
ci = [D.columns.get_loc(c) for c in cands]
ts = []; ms = []
for c in itertools.combinations(ci, 4):
    t, m = blend_t(list(c)); ts.append(t); ms.append(m)
ts = np.array(ts); ms = np.array(ms)
print('4-of-33 candidates: n', len(ts), 'median t', np.nanmedian(ts).round(2), 'p90', np.nanpercentile(ts,90).round(2), 'max', np.nanmax(ts).round(2), 'share >= chosen', np.mean(ts >= t0).round(4), 'rank', int((ts > t0).sum())+1)
print('   mean %/mo median', (np.nanmedian(ms)*100).round(3), 'share t>=3', np.mean(ts>=3).round(3), 'share t>=4', np.mean(ts>=4).round(3))
rng = np.random.default_rng(7); allidx = np.arange(D.shape[1]); rt = []
for _ in range(60000):
    c = rng.choice(allidx, 4, replace=False); rt.append(blend_t(list(c))[0])
rt = np.array(rt)
print('random 4 of 133: median t', np.nanmedian(rt).round(2), 'p95', np.nanpercentile(rt,95).round(2), 'p99', np.nanpercentile(rt,99).round(2), 'max', np.nanmax(rt).round(2), 'share>=chosen', np.mean(rt>=t0).round(5))
# is the blend's t just diversification? average single-rule t of the four
print('single t of four', {c: round(tblk(D[c].values),2) for c in FOUR})
# honest split-sample selection
hold = pd.DatetimeIndex(D.index) + pd.offsets.BDay(1)
def sel(mask_in, subsplit):
    Din = D[mask_in]; hy = hold[mask_in].year
    ok = []
    for c in D.columns:
        s = Din[c]; y = pd.Series(s.values, index=hy).dropna()
        if len(y) < 60: continue
        a = y[y.index < subsplit].mean(); b_ = y[y.index >= subsplit].mean()
        ys = y.groupby(level=0).sum()
        srt = np.sort(y.values); n = int(len(srt)*0.05); tm = srt[n:len(srt)-n].mean()
        loo = min(y[y.index != yy].mean() for yy in ys.index)
        if a > 0 and b_ > 0 and (ys > 0).mean() > 0.5 and tm > 0 and loo > 0: ok.append(c)
    corr = Din[ok].corr()
    order = sorted(ok, key=lambda c: -Din[c].mean())
    pick = []
    for c in order:
        if all(abs(corr.loc[c, p]) < 0.3 for p in pick): pick.append(c)
        if len(pick) == 4: break
    return ok, pick
for name, lo, hi, sub in (('select 1991-2007 -> test 2008-2024', 1991, 2007, 1999), ('select 2008-2024 -> test 1991-2007', 2008, 2024, 2016), ('full-sample (sanity)', 1991, 2024, 2008)):
    mi = (hold.year >= lo) & (hold.year <= hi)
    ok, pick = sel(mi, sub)
    mo = ~mi if name != 'full-sample (sanity)' else mi
    bl = D.loc[mo, pick].dropna().mean(1)
    bi = D.loc[mi, pick].dropna().mean(1)
    print(name, 'n cand', len(ok), 'pick', pick)
    print('   in-sample mean %.3f t %.2f | out-of-sample mean %.3f t %.2f n %d' % (bi.mean()*100, tblk(bi.values), bl.mean()*100, tblk(bl.values), len(bl)))
    print('   chosen FOUR over same OOS window: mean %.3f t %.2f' % (D.loc[mo, FOUR].dropna().mean(1).mean()*100, tblk(D.loc[mo, FOUR].dropna().mean(1).values)))
# average OOS of all candidates-in-sample (no picking)
for lo, hi, sub in ((1991, 2007, 1999), (2008, 2024, 2016)):
    mi = (hold.year >= lo) & (hold.year <= hi); ok, _ = sel(mi, sub)
    ew = D.loc[~mi, ok].mean(1)
    print(f'EW of all {len(ok)} in-sample candidates ({lo}-{hi}) OOS mean %.3f t %.2f; EW of all 133 OOS mean %.3f t %.2f' % (ew.mean()*100, tblk(ew.values), D.loc[~mi].mean(1).mean()*100, tblk(D.loc[~mi].mean(1).values)))
