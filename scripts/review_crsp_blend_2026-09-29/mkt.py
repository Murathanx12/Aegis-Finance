import numpy as np, pandas as pd, math
SD = r'C:/Users/mrthn/aegis-finance/backend/data/optimus/crsp_rebuild/library_series_LIB_2026-09-29T0802Z/'
FOUR = ["px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression"]
d = {r: pd.read_parquet(SD + r + '.parquet') for r in FOUR}
idx = d[FOUR[0]].dropna().index
rn = pd.concat([d[r].rule_net.reindex(idx) for r in FOUR], axis=1).mean(1)
tw = pd.concat([d[r].twin21_net.reindex(idx) for r in FOUR], axis=1).mean(1)
mk = d[FOUR[0]].market.reindex(idx)
def cagr(x): x = x.dropna(); return (1 + x).prod() ** (12 / len(x)) - 1
def tb(x):
    x = x.dropna().values; nb = len(x) // 3; s = x[:nb * 3].reshape(nb, 3).sum(1); return s.mean() / (s.std(ddof=1) / math.sqrt(nb))
print('1995-2024 CAGR blend net %.3f twin %.3f market %.3f' % (cagr(rn), cagr(tw), cagr(mk)))
print('blend - market mean %.3f%%/mo t %.2f; twin - market %.3f t %.2f' % ((rn - mk).mean() * 100, tb(rn - mk), (tw - mk).mean() * 100, tb(tw - mk)))
for a, b in (('1995', '1999'), ('2000', '2009'), ('2010', '2019'), ('2020', '2024')):
    s = (rn - mk)[a:b]; print(a, b, 'blend-mkt %.3f%%/mo' % (s.mean() * 100), 'twin-mkt %.3f' % ((tw - mk)[a:b].mean() * 100))
# cost stress: extra round-trip cost on the rule only for the two small-name sleeves (turnover 0.77/0.92), by era
extra = pd.Series(0.0, index=idx)
for r, to in (('co03_reversal_in_high_margin', 0.92), ('vol_compression', 0.77)):
    e = pd.Series(np.where(idx.year < 2001, 0.0150, np.where(idx.year < 2008, 0.0060, 0.0030)), index=idx)  # extra round-trip
    extra += 0.25 * to * e
x = (rn - extra - mk); print('cost-stressed (extra RT 150/60/30 bps pre-01/01-07/08+ on small sleeves, rule only): blend-mkt %.3f t %.2f; blend-twin %.3f' % (x.mean()*100, tb(x), (rn - extra - tw).mean()*100))
g = rn - tw; m = g.std()
print('gap monthly sd %.3f%%; 6-month sd %.2f%%' % (m * 100, m * 100 * math.sqrt(6)))
