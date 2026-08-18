"""Materialize AEGIS-NET-PANEL-1 (Order 20 §2.3).

    python -m scripts.net_panel_materialize            # print audit only
    python -m scripts.net_panel_materialize --write    # + write the artifacts

Writes `backend/data/optimus/net_panel/net_panel_v1.parquet` (+ coverage and
meta JSON). Deterministic: same source bytes, same rows, no RNG. The coverage
report is the deliverable as much as the parquet — it states which feature
families are AVAILABLE on this machine and which are ABSENT, so the
tournament's ablation ladder knows its floor is the data's, not the world's.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import net_panel as NP        # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="net_panel_materialize")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--horizon-days", type=int, default=20)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    px = NP.load_price_panel()
    print("=" * 74)
    print(f"{NP.PANEL} — materialization")
    print("=" * 74)
    print(f"source     {NP.PRICE_SOURCE.name}: {px.shape[0]} days x "
          f"{px.shape[1]} names, {px.index[0].date()} -> {px.index[-1].date()}")

    res = NP.materialize(px, horizon_days=a.horizon_days)
    c = res.coverage
    print(f"\nrows       {c['n_rows']}   decision dates "
          f"{c['n_decision_dates']} (monthly blocks — the §58 unit)")
    print(f"names/date {c['names_per_date']}")
    print(f"dead       {sorted(c['dead_names'])}")
    print(f"excluded   {c['excluded_name_dates']}")
    print(f"dropped at horizon end: {c['dropped_at_horizon_end']}")
    print(f"output missingness: {c['missingness_in_output']:.4%}")
    print("\nfeature families (the ablation ladder's floor):")
    for fam, status in c["feature_families"].items():
        print(f"  {fam:16s} {status}")

    if a.write:
        paths = NP.write(res)
        for k, p in paths.items():
            print(f"\nwrote {k}: {p.relative_to(REPO)}"
                  if str(p).startswith(str(REPO)) else f"wrote {k}: {p}")
    else:
        print("\n--write not given: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
