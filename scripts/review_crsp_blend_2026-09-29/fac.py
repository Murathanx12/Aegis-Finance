import sys, math, json
import numpy as np, pandas as pd
sys.path.insert(0, r'C:/Users/mrthn/aegis-finance')
N = sys.argv[1]
P = pd.read_parquet(r'C:/Users/mrthn/aegis-finance/backend/data/optimus/crsp_rebuild/library_panel_2026-09-29T075640Z.parquet',
    columns=['date','symbol','eligible','median_dollar_vol','vol_252','beta_252','idio_vol_63','vol_ratio','px_vs_ma200','rev_5','fwd_ret','mkt_trend_up','delisted_in_period'])
P['date'] = pd.to_datetime(P['date']); P = P[P.eligible.astype(bool)]
# universe counts
P['large'] = P.median_dollar_vol >= 1e8
g = P.groupby(P.date.dt.year)
cnt = pd.DataFrame({'eligible_mean_per_month': g.size()/12, 'large_mean_per_month': g['large'].sum()/12})
print(cnt.round(0).astype(int).to_string())
# factors: EW long-short terciles among eligible
def ls(col, low_good=True, uni=None):
    Q = P if uni is None else P[uni]
    def f(d):
        d = d.dropna(subset=[col, 'fwd_ret'])
        if len(d) < 30: return np.nan
        q = d[col].rank(pct=True)
        lo = d.loc[q <= 1/3, 'fwd_ret'].mean(); hi = d.loc[q > 2/3, 'fwd_ret'].mean()
        return (lo - hi) if low_good else (hi - lo)
    return Q.groupby('date').apply(f)
F = pd.DataFrame({'LVOL': ls('vol_252'), 'BAB': ls('beta_252'), 'LIVOL': ls('idio_vol_63'),
                  'LVOL_L': ls('vol_252', uni=P.large), 'TREND_L': ls('px_vs_ma200', low_good=False, uni=P.large)})
# fund proxies
fu = pd.read_parquet(r'C:/Users/mrthn/aegis-finance/backend/data/optimus/crsp_rebuild/library_fund_2026-09-29T041550Z.parquet', columns=['date','symbol','gp_at','debt_at'])
fu['date'] = pd.to_datetime(fu['date'])
Q = P[['date','symbol','fwd_ret']].merge(fu, on=['date','symbol'], how='left')
def ls2(col, low_good):
    def f(d):
        d = d.dropna(subset=[col, 'fwd_ret']);
        if len(d) < 30: return np.nan
        q = d[col].rank(pct=True); lo = d.loc[q <= 1/3, 'fwd_ret'].mean(); hi = d.loc[q > 2/3, 'fwd_ret'].mean()
        return (lo-hi) if low_good else (hi-lo)
    return Q.groupby('date').apply(f)
F['PROF'] = ls2('gp_at', False); F['LOWLEV'] = ls2('debt_at', True)
F.to_pickle(N + '/F.pkl')
print(F.describe().T[['mean','std']].mul(100).round(3))
