"""Export ft_lab's T2 predictions for one hypothesis-lab fold to the file
`backend.services.hyp_cells.t2_predictions` reads.

    python -m ft_lab.export_fold_t2 --fold F2025

2026-09-30 (integration): `hyp_cells` used to import `ft_lab.baselines` lazily
to refit F2025 itself, which put an ft_lab import on a `backend/` module and
broke the firewall `ft_lab/tests/test_split_and_leakage.py` pins (ft_lab is
never imported by the live path). The refit is unchanged and lives here; the
backend module reads the cached file and refuses, naming this command, when
it is absent. Offline, $0, no network.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def export(fold: str) -> Path:
    import pandas as pd
    from backend.services import hyp_cells as HC
    from ft_lab import baselines as FB
    f = HC.FOLDS[fold]
    c = pd.read_parquet(HC.CELLS)
    c = c[c["entry_date"] <= f["test"][1]].reset_index(drop=True)
    tr, va, te = (HC._in(c["entry_date"], *f[k]) for k in ("fit", "val", "test"))
    FB.run_fold(c, tr, va, te, use_emb=False)
    out = c.loc[tr | va | te, ["symbol", "entry_date", "B2_trailing_meta", "T2_trailing_meta_tfidf"]] \
        .rename(columns={"B2_trailing_meta": "B2", "T2_trailing_meta_tfidf": "T2"})
    p = HC.t2_cache_path(fold)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(p, index=False)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fold", default="F2025")
    a = ap.parse_args(argv)
    print(f"-> {export(a.fold)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
