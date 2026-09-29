import sys; sys.path.insert(0, r'C:/Users/mrthn/aegis-finance')
import pandas as pd
from learner.inference import deflated_sharpe
D = pd.read_pickle(sys.argv[1] + '/D.pkl')
FOUR = ["px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression"]
b = D[FOUR].dropna().mean(1).tolist()
for n in (1298, 1296 + 40920, 1296 + 12_400_000 // 1):
    r = deflated_sharpe(b, n_trials=n); print(n, 'dsr', round(r.get('dsr'), 4), 'sr0', r.get('sharpe_benchmark_sr0'), 'z', r.get('z'))
post = D[FOUR].dropna().mean(1); post = post[post.index >= '2007-12-31'].tolist()
for n in (1298, 42216):
    r = deflated_sharpe(post, n_trials=n); print('2008-2024 only', n, 'dsr', round(r.get('dsr'), 4))
