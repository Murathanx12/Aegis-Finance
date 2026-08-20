"""WRDS metadata integrity audit — do the labels describe the data?

Found 2026-08-20 (Order 24 Phase 0): every `wrds/*.meta.json` on disk
claimed `window = [2013-01-01, 2024-12-31]`, because `_write()` stamped
the module constants instead of reading the frame. That is false for
every early-era dataset (finratio_early is really 1990-2012, the 13F
per-year files are really 1996..2012, ...). The parquets were correct;
only the labels lied. This is exactly the class of defect that becomes
invisible once a large model consumes the substrate, so it is fixed
BEFORE any teacher-model training.

    python -m scripts.wrds_meta_audit            # audit only, no writes
    python -m scripts.wrds_meta_audit --repair   # rewrite metas in place

Repair NEVER discards the original claim: the stale window is preserved
under `window_declared_stale` with a `metadata_correction` block, so the
audit chain records that a correction happened rather than hiding it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
RECEIPT = WRDS / "meta_audit_2026-08-20.json"

DATE_HINTS = ("date", "dat", "eom", "public", "statpers", "rdq")
# datasets whose true universe is the early-era PIT screen, not v1
EARLY_MARKERS = ("_early", "tr13f_s34_19", "tr13f_s34_200", "tr13f_s34_201")
EARLY_UNIVERSE = ("crsp_pit_monthly_early screened PERMNOs (early-era "
                  "held-out confirmation slice)")


def _sha(p: Path, cap: int = 64 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        read = 0
        while read < cap:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
            read += len(b)
    return h.hexdigest()[:16]


def _ranges(df: pd.DataFrame) -> dict:
    out = {}
    for c in df.columns:
        if not any(k in c.lower() for k in DATE_HINTS):
            continue
        try:
            s = pd.to_datetime(df[c], errors="coerce").dropna()
        except Exception:
            continue
        if len(s):
            out[c] = [str(s.min())[:10], str(s.max())[:10]]
    return out


def _is_early(name: str) -> bool:
    if name.endswith("_early"):
        return True
    if name.startswith("crsp_dsf_"):
        return int(name.rsplit("_", 1)[1]) < 2013
    if name.startswith("tr13f_s34_"):
        return int(name.rsplit("_", 1)[1]) < 2013
    if name.startswith("optionm_surface30d_"):
        return int(name.rsplit("_", 1)[1]) < 2013
    return False


def audit(repair: bool = False) -> dict:
    rows, corrected = [], 0
    for mp in sorted(WRDS.glob("*.meta.json")):
        name = mp.name[: -len(".meta.json")]
        pq = WRDS / f"{name}.parquet"
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if not pq.exists():
            rows.append({"dataset": name, "status": "META_WITHOUT_PARQUET"})
            continue

        df = pd.read_parquet(pq)
        ranges = _ranges(df)
        pit = str(meta.get("pit_knowledge_column", ""))
        pit_col = pit.split(";")[0].split()[0].strip().lower() if pit else ""
        if pit_col in ranges:
            window, wsrc = ranges[pit_col], pit_col
        elif ranges:
            window = [min(v[0] for v in ranges.values()),
                      max(v[1] for v in ranges.values())]
            wsrc = "union:" + ",".join(sorted(ranges))
        else:
            window, wsrc = None, "no date column"

        declared = meta.get("window")
        rows_ok = int(meta.get("rows", -1)) == len(df)
        win_ok = declared == window
        early = _is_early(name)
        uni_ok = (not early) or ("early" in str(meta.get("universe", "")))
        status = "OK" if (rows_ok and win_ok and uni_ok) else "MISLABELLED"

        rec = {"dataset": name, "status": status,
               "rows_declared": meta.get("rows"), "rows_actual": len(df),
               "rows_match": rows_ok,
               "window_declared": declared, "window_actual": window,
               "window_source": wsrc, "window_match": win_ok,
               "is_early_era": early, "universe_label_ok": uni_ok,
               "date_ranges_observed": ranges,
               "parquet_sha256_head": _sha(pq)}
        rows.append(rec)

        if repair and status != "OK":
            meta.setdefault("metadata_correction", {})
            meta["metadata_correction"] = {
                "corrected_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
                "by": "scripts/wrds_meta_audit.py --repair",
                "reason": "_write() stamped module constants START/END and "
                          "a fixed universe string for every dataset; the "
                          "parquets were correct, the labels were not",
                "window_declared_stale": declared,
                "universe_declared_stale": meta.get("universe"),
            }
            meta["window"] = window
            meta["window_source"] = wsrc
            meta["date_ranges_observed"] = ranges
            meta["rows"] = len(df)
            if early:
                meta["universe"] = EARLY_UNIVERSE
            mp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            corrected += 1

    bad = [r for r in rows if r.get("status") == "MISLABELLED"]
    out = {"audit": "WRDS-META-INTEGRITY-1",
           "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "repaired": repair, "n_datasets": len(rows),
           "n_mislabelled": len(bad), "n_corrected": corrected,
           "verdict": ("LABELS_ONLY — every parquet's row count and date "
                       "content is internally consistent; the defect was "
                       "confined to the meta.json window/universe fields"
                       if all(r.get("rows_match", True) for r in rows)
                       else "DATA_DISCREPANCY — row counts disagree, "
                            "investigate before any training use"),
           "datasets": rows}
    RECEIPT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repair", action="store_true")
    a = ap.parse_args()
    r = audit(repair=a.repair)
    print(f"datasets={r['n_datasets']} mislabelled={r['n_mislabelled']} "
          f"corrected={r['n_corrected']}")
    print(r["verdict"])
    for d in r["datasets"]:
        if d.get("status") != "OK":
            print(f"  {d['dataset']:28s} declared={d.get('window_declared')} "
                  f"actual={d.get('window_actual')}")
    print(f"receipt -> {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
