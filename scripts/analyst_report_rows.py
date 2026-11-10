"""Validate one extracted analyst report and (optionally) append its dated rows.

    python -m scripts.analyst_report_rows validate <report.json>
    python -m scripts.analyst_report_rows validate <report.json> --out <rows.jsonl>

The JSON is what the `analyst-report-extract` skill produces. An invalid report
exits 2 and lists every error; nothing is written. `--out` must be a gitignored
data path or a path outside the repo: rows from a licensed report are not
committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import analyst_report_rows as ARR  # noqa: E402


#: The one in-repo place rows may go; `.gitignore` excludes it (2026-11-11).
PRIVATE_DIR = REPO / "backend" / "data" / "optimus" / "analyst_reports"


def out_path_allowed(out: Path) -> bool:
    """Outside the repo, or under the gitignored PRIVATE_DIR. Nothing else."""
    out = Path(out).resolve()
    repo = REPO.resolve()
    if repo != out and repo not in out.parents:
        return True
    priv = PRIVATE_DIR.resolve()
    return priv in out.parents


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="validate an extracted analyst report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("report")
    v.add_argument("--out", default=None, help="append rows to this JSONL")
    a = ap.parse_args(argv)
    try:
        obj = json.loads(Path(a.report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"REFUSED: cannot read {a.report}: {type(exc).__name__}: {exc}")
        return 2
    rep, errs = ARR.validate_report(obj)
    if rep is None:
        print("INVALID:\n  " + "\n  ".join(errs))
        return 2
    rows = ARR.to_rows(rep)
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(json.dumps({"ticker": rep["ticker"], "broker": rep["broker"],
                      "knowable_at": rep["knowable_at"], "pit_safe": rep["pit_safe"],
                      "rating": rep["rating"], "target_change_pct": rep["target_change_pct"],
                      "rows_by_kind": kinds, "warnings": rep["warnings"]}, indent=1))
    if a.out:
        out = Path(a.out).resolve()
        if not out_path_allowed(out):
            print(f"REFUSED: {out} is inside the repo but not under {PRIVATE_DIR} "
                  f"(gitignored); rows from a licensed report are never committed")
            return 2
        n = ARR.append_rows(rows, out)
        print(f"appended {n} new row(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
