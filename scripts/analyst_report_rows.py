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


def _git_top(path: Path) -> Path | None:
    """The nearest enclosing git checkout (a `.git` dir OR file: worktrees use a
    file), or None. Not just THIS checkout: the runtime checkout and every
    sibling worktree of this public repo are just as tracked."""
    for d in [path, *path.parents]:
        if (d / ".git").exists():
            return d
    return None


def out_path_allowed(out: Path) -> bool:
    """Outside every git checkout, or a path git itself says is ignored.

    Inside a checkout, the answer comes from `git check-ignore` (read-only), not
    from a path comparison: Windows case, relative paths and symlinks all
    resolve the same way for git. Git missing or erroring -> refused.
    """
    import subprocess
    out = Path(out).resolve()
    top = _git_top(out.parent)
    if top is None:
        return True
    try:
        r = subprocess.run(["git", "-C", str(top), "check-ignore", "-q", str(out)],
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


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
            print(f"REFUSED: {out} is inside a git checkout and not ignored by it "
                  f"(use {PRIVATE_DIR} or a path outside every checkout); rows from a "
                  f"licensed report are never committed")
            return 2
        try:
            n = ARR.append_rows(rows, out)
        except ARR.ReportInvalid as exc:
            print(f"REFUSED: {exc}")
            return 2
        print(f"appended {n} new row(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
