import sys
import numpy as np, pandas as pd
P = pd.read_parquet(r'C:/Users/mrthn/aegis-finance/backend/data/optimus/crsp_rebuild/library_panel_2026-09-29T075640Z.parquet',
    columns=['date','symbol','eligible','median_dollar_vol','px_vs_ma200','vol_ratio','rev_5'])
P['date'] = pd.to_datetime(P['date']); P = P[P.eligible.astype(bool)].copy()
fu = pd.read_parquet(r'C:/Users/mrthn/aegis-finance/backend/data/optimus/crsp_rebuild/library_fund_2026-09-29T041550Z.parquet', columns=['date','symbol','gross_margin'])
fu['date'] = pd.to_datetime(fu['date']); P = P.merge(fu, on=['date','symbol'], how='left')
P['band'] = np.select([P.median_dollar_vol >= 1e9, P.median_dollar_vol >= 1e8, P.median_dollar_vol >= 2e7], ['mega','large','mid'], 'small')
out = []; prev = {}
for d, g in P.groupby('date'):
    rows = {}
    L = g[g.median_dollar_vol >= 1e8].dropna(subset=['px_vs_ma200']).nlargest(20, 'px_vs_ma200')
    V = g.dropna(subset=['vol_ratio']).nsmallest(20, 'vol_ratio')
    gm = g.dropna(subset=['gross_margin']); top = gm[gm.gross_margin.rank(pct=True) > 0.7]
    C = top.dropna(subset=['rev_5']).nsmallest(20, 'rev_5')
    for name, S in (('px_large', L), ('vol_comp', V), ('co03', C)):
        if len(S) < 20: continue
        fb = 0
        if name == 'px_large':
            for bnd in ('mega', 'large'):
                h = (S.band == bnd).sum(); pool = ((g.band == bnd) & ~g.symbol.isin(S.symbol)).sum(); fb += max(0, h - pool)
        s = set(S.symbol); to = 1 - len(s & prev.get(name, set())) / 20 if name in prev else np.nan; prev[name] = s
        out.append({'date': d, 'rule': name, 'n_univ': len(g[g.median_dollar_vol >= 1e8]) if name == 'px_large' else len(g),
                    'twin_band_fallback_share': fb / 20 if name == 'px_large' else np.nan, 'turnover': to,
                    'median_mdv_musd': S.median_dollar_vol.median() / 1e6, 'min_mdv_musd': S.median_dollar_vol.min() / 1e6,
                    'share_small_mid': S.band.isin(['small', 'mid']).mean()})
O = pd.DataFrame(out); O['year'] = O.date.dt.year
pd.set_option('display.width', 250)
for r in ('px_large', 'vol_comp', 'co03'):
    t = O[O.rule == r].groupby('year')[['n_univ', 'twin_band_fallback_share', 'turnover', 'median_mdv_musd', 'min_mdv_musd', 'share_small_mid']].mean().round(2)
    print(r); print(t.iloc[::3].to_string() if r != 'px_large' else t.to_string())
    print(r, 'overall turnover', O[O.rule == r].turnover.mean().round(3))
