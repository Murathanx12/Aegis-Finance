"""AEGIS-PANEL-2 — the full-history, all-cap panel (the scale the
sensitivity worlds demanded).

    python -m scripts.aegis_panel2_build            # audit print only
    python -m scripts.aegis_panel2_build --write    # + write artifacts

Sources: `wrds/jkp_full/jkp_usa_*.parquet` (1926–2012, named consumer
AEGIS-PANEL-2) + `wrds/jkp_global_factor_usa.parquet` (2013–2024). The
builder REFUSES if any chunk of the declared plan is absent — a panel
quietly built over a hole would wear the full window's label.

Differences from v1, all declared:
  * Universe: ALL US common stocks (`common=1, obs_main=1, primary_sec=1`,
    CRSP shrcd via `crsp_shrcd in (10,11)` where present) — no price or
    dollar-volume floor. Size/liquidity become COLUMNS, not gates, so
    tournaments can condition on them instead of inheriting a filter.
  * Label: JKP `ret_exc_lead1m` (their delisting-aware construction —
    the v1 cross-check measured corr 0.99987 against our own spine lead,
    so the two constructions are interchangeable; v2 uses JKP's because
    the pre-2013 spine does not exist and building one is not this
    consumer's job).
  * Features: the same JKP column families as v1 (family map reused from
    `backend.services.aegis_panel`); the 7 price-floor features are NOT
    recomputed here — the floor arms for TOURNAMENT-2 come from JKP's own
    price columns (`ret_12_1`, `ret_1_0`, `rvol_252d`…), declared in that
    prereg, so v2 needs no daily-file join at all.

Nothing here registers or runs a model. TOURNAMENT-2's prereg owns folds,
arms and the planted-detectability gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.aegis_panel import (JKP_EXCLUDE,       # noqa: E402
                                          PanelRefused, family_map)
from scripts.wrds_pull_jkp_full import USA_CHUNKS            # noqa: E402

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
CHUNK_DIR = WRDS / "jkp_full"
MODERN = WRDS / "jkp_global_factor_usa.parquet"
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
LABEL = "ret_exc_lead1m"


def _load_all() -> pd.DataFrame:
    missing = [f"jkp_usa_{lo}_{hi}.parquet" for lo, hi in USA_CHUNKS
               if not (CHUNK_DIR / f"jkp_usa_{lo}_{hi}.parquet").exists()]
    if missing:
        raise PanelRefused(
            f"{len(missing)} chunk(s) of the declared plan absent "
            f"(pull incomplete?): {missing[:5]}… — a panel over a hole "
            f"is refused, never built.")
    if not MODERN.exists():
        raise PanelRefused(f"{MODERN} missing")

    n_raw = 0

    def _one(p: Path) -> pd.DataFrame:
        nonlocal n_raw
        d = pd.read_parquet(p)
        n_raw += len(d)
        # filter per chunk BEFORE concat, downcast features to float32 —
        # 4.2M rows × 440 float64 would peak ~15 GB at the join otherwise
        for col, want in (("common", 1), ("obs_main", 1),
                          ("primary_sec", 1)):
            if col in d.columns:
                d = d[d[col] == want]
        if "crsp_shrcd" in d.columns:
            d = d[d["crsp_shrcd"].isin((10, 11))
                  | d["crsp_shrcd"].isna()]
        keep64 = {"permno", "gvkey", "eom", "date", LABEL}
        for c in d.columns:
            if d[c].dtype == "float64" and c not in keep64:
                d[c] = d[c].astype("float32")
        return d

    parts = [_one(CHUNK_DIR / f"jkp_usa_{lo}_{hi}.parquet")
             for lo, hi in USA_CHUNKS]
    parts.append(_one(MODERN))
    df = pd.concat(parts, ignore_index=True)
    return df, n_raw


def build() -> tuple[pd.DataFrame, dict]:
    df, n_raw = _load_all()
    df["eom"] = pd.to_datetime(df["eom"])
    df = df.sort_values(["eom", "permno"], na_position="last")
    dup = df.duplicated(["permno", "eom"], keep=False) & df["permno"].notna()
    if dup.any():
        raise PanelRefused(f"{int(dup.sum())} duplicate permno-eom rows "
                           f"after filters — resolve, never dedupe blind")

    feat_cols = [c for c in df.columns if c not in JKP_EXCLUDE]
    fam = family_map(feat_cols)
    years = df["eom"].dt.year
    cov = {f: round(float(df[[c for c, ff in fam.items() if ff == f]]
                          .notna().mean().mean()), 4)
           for f in sorted(set(fam.values()))}
    coverage = {
        "panel": "AEGIS-PANEL-2",
        "n_rows": int(len(df)), "n_rows_raw": int(n_raw),
        "n_months": int(df["eom"].nunique()),
        "n_permnos": int(df["permno"].nunique()),
        "window": [str(df["eom"].min().date()),
                   str(df["eom"].max().date())],
        "n_rows_with_label": int(df[LABEL].notna().sum()),
        "rows_per_year_quartiles": {
            "q25": int(years.value_counts().quantile(0.25)),
            "median": int(years.value_counts().median()),
            "q75": int(years.value_counts().quantile(0.75))},
        "coverage_by_family": cov,
        "unmapped_columns": sorted(c for c, f in fam.items()
                                   if f == "UNMAPPED"),
        "universe_note": "ALL-CAP: size/liquidity are columns, not "
                         "gates; thin-name beta attenuation applies to "
                         "price-risk columns (Dimson correction is a "
                         "TOURNAMENT-2 concern, measured 2026-08-22)",
    }
    return df, coverage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aegis_panel2_build")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    df, cov = build()
    print(json.dumps({k: v for k, v in cov.items()
                      if k != "coverage_by_family"}, indent=2))
    print("coverage_by_family:", json.dumps(cov["coverage_by_family"]))
    if a.write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        p = OUT_DIR / "aegis_panel_v2.parquet"
        df.to_parquet(p, index=False)
        (OUT_DIR / "aegis_panel_v2_coverage.json").write_text(
            json.dumps(cov, indent=2), encoding="utf-8")
        (OUT_DIR / "aegis_panel_v2.meta.json").write_text(json.dumps({
            "dataset": "AEGIS-PANEL-2",
            "built_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "sources": ["jkp_full/jkp_usa_*.parquet",
                        "jkp_global_factor_usa.parquet"],
            "label": LABEL + " (JKP delisting-aware; corr 0.99987 vs the "
                             "v1 spine construction on the overlap)",
            "consumer_of": "TRAINING gate — TOURNAMENT-2 (prereg owns "
                           "folds/arms/detectability gate)",
        }, indent=2), encoding="utf-8")
        print(f"wrote {p}")
    else:
        print("--write not given: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
