"""Seeds: every seed any run used is recorded; a new night draws OUTSIDE that set.

CLAUDE.md protocol item 9: a fixed seed schedule made every night a bit-identical
replay (541/541 genomes overlapped). Reproducibility WITHIN a run comes from the
recorded seed; accumulation ACROSS runs comes from never reusing one.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from nn_lab import config as C


def used(path: Path | None = None) -> set[int]:
    path = Path(path or C.SEEDS_LEDGER)
    out: set[int] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.update(int(s) for s in json.loads(line).get("seeds", []))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    return out


def draw(n: int = 1, path: Path | None = None, *, _source=secrets.randbelow) -> list[int]:
    """n fresh seeds, none of which any earlier run recorded, and distinct from each other."""
    taken = used(path)
    out: list[int] = []
    while len(out) < n:
        s = int(_source(2**31 - 1))
        if s not in taken and s not in out:
            out.append(s)
    return out


def record(seeds, source: str, path: Path | None = None) -> None:
    path = Path(path or C.SEEDS_LEDGER)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"source": source, "seeds": [int(s) for s in seeds],
                             "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
