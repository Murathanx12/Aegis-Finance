"""Build the Order 24 Phase 7 training datasets, with honest weights.

Two rules govern every dataset here, and both exist because the naive
version of each is what produces impressive-looking nonsense.

**1. Date blocks carry equal aggregate weight, rows do not.** A panel
with 226,228 stock-months does not contain 226,228 independent
observations. On any single date the whole cross-section co-moves, and
21-day forward outcomes at adjacent month-ends overlap. Weighting rows
equally silently lets 2020 — a year with more eligible names — outvote
1994, and lets one crisis month speak with the authority of its
cross-section size. Every dataset therefore ships a `date_weight` column
that sums to 1.0 within each date, so each DATE contributes once.

**2. Correlated strategies share weight within a date.** For the
strategy dataset the same logic applies one level up: 216 books that
collapse to ~4 behaviours are not 216 independent samples. Books are
clustered first and weight is split within cluster, so a family with 36
grammar variants does not outvote a family with 4.

Tier PRIVATE under `docs/DECISION_WRDS_RECEIPT_POLICY.md`: these panels
are per-security derived from WRDS and are NOT published. Each writes a
public STUB recording name, sha256, rows, window and schema, so a reader
can tell "does not exist" from "cannot be shown".

    python -m scripts.build_training_datasets --era modern
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from scripts.option_incremental_risk_1 import (              # noqa: E402
    ERAS, WITH_OPT, build)

DATA = _config.OPTIMUS_LEDGER_DIR / "datasets"
STUBS = REPO / "docs" / "datasets"


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def date_weights(dates: pd.Series) -> pd.Series:
    """1/n within each date, so every date sums to 1.0."""
    n = dates.map(dates.value_counts())
    return 1.0 / n.astype(float)


def write_with_stub(df: pd.DataFrame, name: str, meta: dict) -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    STUBS.mkdir(parents=True, exist_ok=True)
    p = DATA / f"{name}.parquet"
    df.to_parquet(p, index=False)
    sha = _sha(p)
    stub = {"dataset": name, "tier": "PRIVATE",
            "reason": "per-security series derived from WRDS-entitled "
                      "sources (CRSP, OptionMetrics); not redistributable",
            "sha256": sha, "rows": int(len(df)),
            "columns": {c: str(df[c].dtype) for c in df.columns},
            "built_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "local_path_relative": str(p.relative_to(_config
                                                     .OPTIMUS_LEDGER_DIR)),
            "entitlement_required": ["WRDS: CRSP", "WRDS: OptionMetrics"],
            "reproducibility": "regenerable by scripts/"
                               "build_training_datasets.py given the same "
                               "entitlement; NOT openly reproducible",
            **meta}
    (STUBS / f"{name}.stub.json").write_text(
        json.dumps(stub, indent=2, default=str), encoding="utf-8")
    return stub


def stock_risk_dataset(era: str) -> dict:
    cfg = ERAS[era]
    print(f"building STOCK_RISK_DATASET_V1 [{era}]...")
    df = build(era)
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)
    df = df.sort_values(["date", "permno"]).reset_index(drop=True)
    df["date_weight"] = date_weights(df["date"])

    keep = (["permno", "date", "date_weight"] + list(WITH_OPT)
            + ["fwd_var"])
    out = df[keep].copy()
    name = f"STOCK_RISK_DATASET_V1_{era}"
    stub = write_with_stub(out, name, {
        "unit": "security x month-end formation date",
        "era": era, "universe": cfg["univ"],
        "window": [str(out["date"].min())[:10],
                   str(out["date"].max())[:10]],
        "n_dates": int(out["date"].nunique()),
        "n_securities": int(out["permno"].nunique()),
        "target": "fwd_var = annualized realized variance over t+1..t+21",
        "weighting": "date_weight sums to 1.0 within each date; a date is "
                     "the evidence unit, a row is not",
        "pit": "features at the month-end close of t; target strictly "
               "t+1..t+21 (CHRONOLOGY-AUDIT-1 C2 PASS); options joined "
               "with sign-asserted non-negative lag (C1 PASS)",
        "missing": "rows lacking any feature are DROPPED, never imputed",
        "known_limits": [
            "options coverage gates the population (~98.5% modern, "
            "~83.5% early) — names without listed options are absent, "
            "which is a real and unmodelled selection",
            "the entitled CRSP vintage ends 2024-12-31",
        ]})
    print(f"  {stub['rows']:,} rows, {stub['n_dates']} dates, "
          f"{stub['n_securities']} securities -> {name}")
    return stub


def strategy_state_dataset() -> dict | None:
    """Rows = book x month, weighted by date THEN by strategy cluster.

    Built from the INFORMATION-DIMENSION-1 corpus if it exists. The
    cluster split is the part that matters: 216 books spanning ~4
    behaviours must not vote 216 times.
    """
    from scripts.strategy_structure_1 import LF
    src = (_config.OPTIMUS_LEDGER_DIR / "structure"
           / "information_dimension_1_books.jsonl")
    if not src.exists():
        print("strategy corpus not present yet — skipped")
        return None
    rows = [json.loads(x) for x in
            src.read_text(encoding="utf-8").splitlines() if x.strip()]
    series = {}
    for r in rows:
        s = pd.Series({pd.Timestamp(int(ts), unit="ms"): v
                       for ts, v in r["monthly"].items()}).sort_index()
        series[r["key"]] = s
    R = pd.DataFrame(series).dropna()
    if R.shape[1] < 2:
        return None

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    C = np.nan_to_num(R.corr().to_numpy(float), nan=0.0)
    np.fill_diagonal(C, 1.0)
    D = 1 - C
    np.fill_diagonal(D, 0.0)
    D = (D + D.T) / 2
    lab = fcluster(linkage(squareform(D, checks=False), method="average"),
                   t=0.3, criterion="distance")
    cl = dict(zip(R.columns, lab))
    n_cl = int(lab.max())

    long = R.stack().rename("ret").reset_index()
    long.columns = ["date", "book", "ret"]
    long["cluster"] = long["book"].map(cl)
    # weight: each date sums to 1; within a date each CLUSTER gets an
    # equal share; within a cluster its books split that share
    per_date_clusters = long.groupby("date")["cluster"].transform("nunique")
    per_date_cluster_n = long.groupby(["date", "cluster"])["book"] \
        .transform("count")
    long["date_weight"] = 1.0 / (per_date_clusters * per_date_cluster_n)

    name = "STRATEGY_STATE_DATASET_V1"
    stub = write_with_stub(long, name, {
        "unit": "book x month, weighted to cluster x date",
        "n_books": int(R.shape[1]), "n_clusters": n_cl,
        "window": [str(long["date"].min())[:10],
                   str(long["date"].max())[:10]],
        "weighting": "each DATE sums to 1.0; within a date each CLUSTER "
                     "gets an equal share and its books split that share "
                     "— 216 books spanning ~4 behaviours must not vote "
                     "216 times",
        "clustering": "average-linkage on 1 - return correlation, cut at "
                      "0.3; descriptive, computed on the full window and "
                      "therefore NOT valid as a prospective label",
        "known_limits": [
            "holdings and per-month turnover paths were not persisted by "
            "the sweep, so holdings-overlap and action-correlation views "
            "are unavailable and the clustering rests on returns alone",
        ]})
    print(f"  {stub['rows']:,} rows, {R.shape[1]} books -> {n_cl} clusters")
    return stub


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern", choices=list(ERAS))
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    built = []
    if not a.skip_stock:
        built.append(stock_risk_dataset(a.era))
    s = strategy_state_dataset()
    if s:
        built.append(s)
    print(f"\nstubs -> {STUBS}")
    for b in built:
        print(f"  {b['dataset']:34s} {b['rows']:>9,} rows  "
              f"sha {b['sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
