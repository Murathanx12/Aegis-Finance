"""Throwaway (review 2026-09-29): rule - twin21 series of every LIB_2026-09-29T0802Z rule -> <dir>/D.pkl, plus meta.json.
usage: python scripts/review_crsp_blend_2026-09-29/build_series.py <workdir>; then sel.py / sel2.py / wf.py / fac.py / reg.py / impl.py / mkt.py / dsr.py <workdir>."""
import json, os, sys
import pandas as pd
N = sys.argv[1]; os.makedirs(N, exist_ok=True)
R = 'backend/data/optimus/crsp_rebuild/'
SD = R + 'library_series_LIB_2026-09-29T0802Z/'
pd.DataFrame({f[:-8]: (lambda x: x.rule_net - x.twin21_net)(pd.read_parquet(SD + f)) for f in os.listdir(SD)}).to_pickle(N + '/D.pkl')
rows = [json.loads(l) for l in open(R + 'library_rules_LIB_2026-09-29T0802Z.jsonl')]
b = json.load(open(R + 'library_board_LIB_2026-09-29T0802Z__2026-09-29T081355Z.json'))
json.dump({'tested': [r['rule'] for r in rows if r.get('status') == 'RUN' and not r['control']], 'cands': b['candidates']}, open(N + '/meta.json', 'w'))
