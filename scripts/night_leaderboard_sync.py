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

from scripts.night_factory import (LEADERBOARD, OUT, _status,            # noqa: E402
                                   append_leaderboard)

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



# ------------------------------------------------- the replicated negative

#: where the night directories live. One per run date.
NIGHTS = REPO / "backend" / "data" / "optimus"
NIGHT_DIR = re.compile(r"^night_factory_(?P<date>\d{4}-\d{2}-\d{2})$")


def night_dirs(base: Path | None = None) -> list[Path]:
    """Every night directory, ORDERED BY NAME.

    Never by mtime: a fresh CI checkout rewrites every one of them, so an
    mtime order is an order on checkout time (CLAUDE.md session protocol 7).
    """
    base = base or NIGHTS
    if not base.is_dir():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir() and NIGHT_DIR.match(p.name)),
                  key=lambda p: p.name)


def prior_verdicts(job: str, *, before: tuple[str, int], base: Path | None = None
                   ) -> list[tuple[str, int, str]]:
    """`[(night date, run, status)]` for `job` STRICTLY before `(night, run)`,
    oldest first. `status` is the receipt's own leading tag, read by the same
    `night_factory._status` the board uses -- comparing raw verdict prose would
    call two identical findings different because one sentence was reworded."""
    out: list[tuple[str, int, str]] = []
    for d in night_dirs(base):
        m = NIGHT_DIR.match(d.name)
        date = m.group("date") if m else d.name
        for p in sorted(d.glob(f"{job}_run*.json")):
            rm = RECEIPT.match(p.name)
            if not rm or rm.group("job") != job or p.name.endswith("_smoke.json"):
                continue
            run = int(rm.group("run"))
            if (date, run) >= before:
                continue
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:                                  # noqa: BLE001
                continue
            out.append((date, run, _status(payload)))
    return out


def consistency_note(job: str, run: int, payload: dict, *, night: str | None = None,
                     base: Path | None = None) -> str | None:
    """`REPLICATED xN` when this run's verdict repeats the previous run's.

    N3_frozen_embedding_head returned FAILED_VARIANT on 2026-09-10 and again on
    2026-09-11, and the board showed two rows that looked like two unrelated
    disappointments. They are not: a negative that reproduces on a second
    night is stronger evidence than one that happened once, and the board is
    where that is either visible or lost. This says it in the row.

    A CHANGED verdict is not annotated -- that is a different finding and it
    deserves its own read, not a badge.
    """
    night = night or (NIGHT_DIR.match(OUT.name).group("date")
                      if NIGHT_DIR.match(OUT.name) else OUT.name)
    status = _status(payload)
    prior = prior_verdicts(job, before=(night, run), base=base)
    if not prior or prior[-1][2] != status:
        return None
    streak, dates = 1, []
    for date, prev_run, prev_status in reversed(prior):
        if prev_status != status:
            break
        streak += 1
        dates.append(f"{date} run {prev_run:02d}")
    return (f"[REPLICATED x{streak}: {status} also on {', '.join(dates)}]")


def with_consistency(job: str, run: int, payload: dict, *, night: str | None = None,
                     base: Path | None = None) -> dict:
    """`payload` with the note prefixed to the headline, or `payload` unchanged."""
    note = consistency_note(job, run, payload, night=night, base=base)
    if not note:
        return payload
    return {**payload, "consistency": note,
            "headline": f"{note} {payload.get('headline') or ''}".strip()}


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
            job, run = m.group("job"), int(m.group("run"))
            append_leaderboard(job, run, with_consistency(
                job, run, json.loads(p.read_text(encoding="utf-8"))))
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
        payload = with_consistency(job, run, payload)
        added.append((job, run, (payload.get("consistency") or "")
                      + str(payload.get("verdict"))[:60]))
        if not a.dry_run:
            append_leaderboard(job, run, payload)
    for job, run, verdict in added:
        print(f"  {'would add' if a.dry_run else 'added'} {job} run {run}: {verdict}")
    print(f"{len(added)} row(s){' would be' if a.dry_run else ''} appended to {LEADERBOARD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
