"""Put every receipt on the leaderboard, whether or not the queue ran it.

`scripts/night_factory` appends a leaderboard row as each job finishes, so a job
started directly (`python -m scripts.night_g3_evolve_v2`) writes a receipt that
never reaches `LEADERBOARD.md` -- and the leaderboard is what the morning read,
and now `/api/control/leaderboard`, actually shows. A result that is on disk but
not on the board is invisible in exactly the way the 09-05/09-06 red CI was.

This scans the night directory, finds receipts with no row, and appends them
through `night_factory.append_leaderboard` -- the same function, so a row here
and a row the queue wrote are formatted by one piece of code.

    python -m scripts.night_leaderboard_sync            # append what is missing
    python -m scripts.night_leaderboard_sync --dry-run  # say what it would add
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.night_factory import LEADERBOARD, OUT, append_leaderboard   # noqa: E402

RECEIPT = re.compile(r"^(?P<job>.+)_run(?P<run>\d{2})\.json$")


def existing_rows() -> set[tuple[str, int]]:
    if not LEADERBOARD.exists():
        return set()
    out = set()
    for line in LEADERBOARD.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 3 and cells[2].isdigit():
            out.add((cells[1], int(cells[2])))
    return out


def rebuild() -> int:
    """Regenerate every row from the receipts.

    Needed once on 2026-09-09: the board's writer filed P6 as REFUSED because
    that word appeared inside a sentence about something else, and RW1's headline
    contains a literal `|` which split its row into extra columns. Both are fixed
    in `night_factory`; the rows already on disk are not, and a board is only
    useful if the rows agree with the receipts.
    """
    head, _, _ = LEADERBOARD.read_text(encoding="utf-8").partition("| job | run |")
    LEADERBOARD.write_text(head + "| job | run | status | headline | family max p | utc |\n"
                                  "|---|---|---|---|---|---|\n", encoding="utf-8")
    n = 0
    for p in sorted(OUT.glob("*_run*.json"), key=lambda x: x.stat().st_mtime):
        m = RECEIPT.match(p.name)
        if not m or p.name.endswith("_smoke.json"):
            continue
        try:
            append_leaderboard(m.group("job"), int(m.group("run")),
                               json.loads(p.read_text(encoding="utf-8")))
            n += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  SKIP {p.name}: {type(exc).__name__}")
    n += _append_amendments()
    print(f"{n} row(s) rebuilt from receipts into {LEADERBOARD}")
    return 0


def _append_amendments() -> int:
    """An amendment must reach the board, or the retracted stamp is the one read.

    `D3_verdict_amendment.json` corrected D3's PRODUCT_PROMISING to ERA_DECAYED
    on the night it was written, and the board still showed the original --
    the same shape as [a withdrawal by header leaves the number standing].
    An amendment row is filed under run 99 so it sorts last and cannot be
    mistaken for a fresh run.
    """
    n = 0
    # `*_amendment.json`, not `*_verdict_amendment.json`: C2's 2026-09-10 cost-model
    # amendment is named `C2_cost_model_amendment.json` and the narrower glob would
    # have left the artefact net line as the only row on the board -- the exact
    # failure this function exists to prevent.
    for p in sorted(OUT.glob("*_amendment.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        amends = d.get("amends")
        if isinstance(amends, list):
            amends = amends[0] if amends else None
        job = str(amends or p.name.split("_amendment")[0].rsplit("_", 2)[0])
        append_leaderboard(job.split("_run")[0], 99, {
            "verdict": str(d.get("corrected_verdict") or "AMENDED"),
            "headline": f"AMENDMENT to {job}: {str(d.get('why') or '')}",
            "family_max_p": d.get("family_max_p"),
            "written_utc": d.get("written_utc")})
        n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="regenerate every row from the receipts (idempotent)")
    a = ap.parse_args(argv)
    if a.rebuild:
        return rebuild()
    have = existing_rows()
    added = []
    for p in sorted(OUT.glob("*_run*.json")):
        m = RECEIPT.match(p.name)
        if not m or p.name.endswith("_smoke.json"):
            continue
        job, run = m.group("job"), int(m.group("run"))
        if (job, run) in have:
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  a corrupt receipt is a finding, not a crash
            print(f"  SKIP {p.name}: unreadable ({type(exc).__name__})")
            continue
        added.append((job, run, str(payload.get("verdict"))[:60]))
        if not a.dry_run:
            append_leaderboard(job, run, payload)
    for job, run, verdict in added:
        print(f"  {'would add' if a.dry_run else 'added'} {job} run {run}: {verdict}")
    print(f"{len(added)} row(s){' would be' if a.dry_run else ''} appended to {LEADERBOARD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
