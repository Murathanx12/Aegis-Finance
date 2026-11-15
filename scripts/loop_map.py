"""The loop map (ROADMAP CH-56): one generated page of the loop as it runs today.

    python -m scripts.loop_map --data-root <backend/data> [--out <dir>] [--now <iso>]

Reads receipts and configuration only (`backend.services.loop_map` holds the declared
LINKS table and the reader). Writes, atomically, into `--out` (default
`<data-root>/optimus/loop_map/`):

    loop_<utc>.json            links, statuses, ages, evidence path per status, counts, top line
    loop_<utc>.md              the same as tables + three Mermaid diagrams
    loop_<utc>_feedback.mmd    diagram 1: the feedback loop, each edge labelled by its status
    loop_<utc>_layers.mmd      diagram 2: M0 foundation .. M6 show with their tasks
    loop_<utc>_objects.mmd     diagram 3: object relationships with the joining id field

Exit 0: written and faithful, even with open links (they are the finding; the count is
printed). Exit 2: the input root is missing, empty, or holds none of the declared
receipts (a wrong directory must not produce an all-ABSENT map that looks like a
finding); nothing is written. Exit 3: not written (bad `--now`, write or verify failed).
No network, no subprocess, no LLM, no broker. Nothing is dated by file mtime.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as C  # noqa: E402
from backend.services import loop_map as LM  # noqa: E402
from scripts import system_status as SS  # noqa: E402


def write_all(rec: dict, out_dir: Path) -> list[Path]:
    """The five files, each temp -> replace; the JSON is read back and compared."""
    base = f"loop_{rec['run']}"
    text = json.dumps(rec, indent=1, default=str)
    files = [(out_dir / f"{base}.json", text),
             (out_dir / f"{base}.md", LM.render_markdown(rec)),
             (out_dir / f"{base}_feedback.mmd", LM.mermaid_feedback(rec)),
             (out_dir / f"{base}_layers.mmd", LM.mermaid_layers(rec)),
             (out_dir / f"{base}_objects.mmd", LM.mermaid_objects(rec))]
    written = [SS.write_atomic(p, t) for p, t in files]
    back = SS.read_json(written[0])
    if not isinstance(back, dict) or back.get("top_line") != rec["top_line"]:
        raise OSError(f"{written[0]} did not read back")
    return written


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Map the loop from receipts and config (read-only).")
    ap.add_argument("--data-root", type=Path, required=True, help="the `backend/data` folder to read")
    ap.add_argument("--out", type=Path, default=None, help="default: <data-root>/optimus/loop_map")
    ap.add_argument("--now", default=None, help="ISO time to judge ages at (default: the wall clock)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    now = datetime.now(timezone.utc)
    if a.now:
        now = SS.parse_ts(a.now)
        if now is None:
            print(f"LOOP_MAP NOT WRITTEN: --now {a.now!r} is not a time", file=sys.stderr)
            return 3
    why = LM.root_is_empty(a.data_root)
    if why:
        print(f"LOOP_MAP REFUSED: {why}", file=sys.stderr)
        return 2
    rec = LM.build(a.data_root, now=now)
    if rec["n_links"] and rec["counts"]["ABSENT"] == rec["n_links"]:
        print(f"LOOP_MAP REFUSED: none of the {rec['n_links']} declared producer receipts exists under "
              f"{a.data_root}; this is not a `backend/data` folder", file=sys.stderr)
        return 2
    out_dir = a.out or (a.data_root / "optimus" / C.LOOP_MAP_DIRNAME)
    try:
        written = write_all(rec, out_dir)
    except OSError as exc:
        print(f"LOOP_MAP NOT WRITTEN: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    if not a.quiet:
        print(rec["top_line"])
        print(f"open links: {rec['n_open']} of {rec['n_links']}; loop closed: "
              f"{'YES' if rec['loop_closed'] else 'NO'}"
              + ("" if rec["loop_closed"] else f" (no flowing link on {', '.join(rec['open_pairs'])})"))
        for r in rec["links"]:
            if r["status"] != "FLOWING":
                print(f"  {r['status']:<16} {r['id']}: {r['reason']}")
        print(f"written: {written[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
