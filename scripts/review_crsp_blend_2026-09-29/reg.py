import sys, math
import numpy as np, pandas as pd
N = sys.argv[1]
D = pd.read_pickle(N + '/D.pkl'); F = pd.read_pickle(N + '/F.pkl')
FOUR = ["px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression"]
blend = D[FOUR].dropna().mean(1)
ff = pd.read_parquet(r'C:/Users/mrthn/aegis-finance/backend/data/optimus/wrds/ff_factors_monthly.parquet', columns=['date','mktrf','smb','hml','umd'])
ff['m'] = pd.to_datetime(ff.date).dt.to_period('M'); ff = ff.set_index('m')[['mktrf','smb','hml','umd']]
hp = (pd.DatetimeIndex(blend.index) + pd.offsets.BDay(1)).to_period('M')
X = ff.reindex(hp).set_index(blend.index).join(F.reindex(blend.index))
def nw(y, X, L=3):
    X = np.column_stack([np.ones(len(y)), X]); b = np.linalg.lstsq(X, y, rcond=None)[0]; e = y - X @ b
    n = len(y); XtXi = np.linalg.inv(X.T @ X); S = (X * e[:, None]).T @ (X * e[:, None])
    for l in range(1, L + 1):
        w = 1 - l / (L + 1); G = (X[l:] * e[l:, None]).T @ (X[:-l] * e[:-l, None]); S += w * (G + G.T)
    V = XtXi @ S @ XtXi; return b, b / np.sqrt(np.diag(V))
def run(y, cols, lab):
    Z = X[cols].join(y.rename('y')).dropna(); b, t = nw(Z.y.values, Z[cols].values)
    print(f'{lab:55s} n={len(Z)} alpha={b[0]*100:+.3f}%/mo t={t[0]:+.2f} | ' + ' '.join(f'{c}={bb:+.2f}({tt:+.1f})' for c, bb, tt in zip(cols, b[1:], t[1:])))
sets = {'FF3+UMD': ['mktrf','smb','hml','umd'],
        'FF3+UMD+LVOL+BAB+LIVOL': ['mktrf','smb','hml','umd','LVOL','BAB','LIVOL'],
        '+PROF+LOWLEV (FF5-ish proxy)': ['mktrf','smb','hml','umd','LVOL','BAB','LIVOL','PROF','LOWLEV'],
        '+TREND_L (large-cap MA200 L/S)': ['mktrf','smb','hml','umd','LVOL','BAB','LIVOL','PROF','LOWLEV','TREND_L']}
for k, c in sets.items(): run(blend, c, 'blend gap ' + k)
post = blend[blend.index >= '1999-12-31']
for k, c in list(sets.items())[1:]: run(post, c, 'blend gap 2000-2024 ' + k)
for r in FOUR: run(D[r].dropna(), sets['+TREND_L (large-cap MA200 L/S)'], r)
print('blend decision>=1999-12: mean %.3f n %d' % (post.mean()*100, len(post)))
