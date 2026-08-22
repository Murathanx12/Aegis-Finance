"""Materialize AEGIS-PANEL-1 (Order 28 §2).

    python -m scripts.aegis_panel_build            # audit print only
    python -m scripts.aegis_panel_build --write    # + write artifacts

Deterministic join of the PIT spine, the JKP characteristics file and the
CRSP daily floor features. The coverage report is a deliverable equal to
the parquet: it states which families exist, per year, and which columns
the family map failed to claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import aegis_panel as AP      # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aegis_panel_build")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    res = AP.build()
    c = res.coverage
    print("=" * 74)
    print(f"{AP.PANEL} — materialization")
    print("=" * 74)
    print(f"rows {c['n_rows']:,}  months {c['n_months']}  "
          f"permnos {c['n_permnos']:,}  window {c['window']}")
    print(f"feature columns {c['n_feature_columns']}  "
          f"primary-labeled rows {c['n_rows_with_primary_label']:,}  "
          f"jkp match rate {c['jkp_match_rate']:.1%}")
    print("\nfamilies (n columns):")
    for f, n in c["families"].items():
        print(f"  {f:24s} {n}")
    if c["unmapped_columns"]:
        print(f"\nUNMAPPED ({len(c['unmapped_columns'])}): "
              f"{c['unmapped_columns']}")
    print("\ndeclared absent families:")
    for f, why in c["declared_absent_families"].items():
        print(f"  {f:12s} {why}")
    print("\ncoverage by year (mean non-null fraction per family):")
    print(json.dumps(c["coverage_by_year_family"], indent=1))

    if a.write:
        paths = AP.write(res)
        for k, p in paths.items():
            print(f"wrote {k}: {p}")
    else:
        print("\n--write not given: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
