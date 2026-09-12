"""The objects lane X reads: R2's persisted answers, and a seeded cell draw.

Three X-lane jobs (`night_x_anonymisation_gap`, `night_l3_lookahead`,
`night_x4_regime_route`) all start from the SAME two things -- the answers
`night_r2_monthly_llm.py` appends as it reads, and a reproducible subset of
cells to re-ask. Writing that twice is how two jobs come to disagree about
which 300 cells they ran, and a disagreement like that is invisible in a
receipt: both say "300 cells".

So the draw lives here, it is STRATIFIED BY MONTH BLOCK, and it is hashed. The
stratification is not decoration: the monthly block is the dependence unit
(canon section 58), and a uniform draw over 18,501 cells can leave a block with
two cells in it, which then contributes a block mean built from two names to a
Newey-West t over 19 blocks. Equal allocation per block is the cheapest way to
stop that, and `cells_sha256` is what lets a later run prove it asked the same
question -- the fix for a night that turned out to be a replay (2026-09-10).
"""

from __future__ import annotations

import hashlib
import json
import random
import os
from pathlib import Path

def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT`.

    NOT `Path(__file__)`-rooted. Inside the packaged app `__file__` lives under
    `_internal/`, which is empty, so a path built that way reads a directory
    that does not exist and returns NOTHING without failing -- defect family
    #14, five instances in one day on 2026-09-10. `test_frozen_path_family.py`
    is the gate, and it caught this module on its first full suite run.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


REPO = _repo_root()

#: R2's PANEL-B answers, appended one line per cell as the read proceeds.
R2_PANEL_B_ANSWERS = (REPO / "backend" / "data" / "optimus" /
                      "night_factory_2026-09-10" / "R2_widened_panelB_answers.jsonl")

#: The receipt PANEL-B's read files. `PENDING_MODEL` as of 2026-09-12: it was
#: written before any model call, so its AMNESIA canary block does not exist and
#: `amnesia_gap` falls back to the answers file. Which source was used is
#: RETURNED, never assumed.
R2_PANEL_B_RECEIPT = (REPO / "backend" / "data" / "optimus" /
                      "night_factory_2026-09-10" / "R2_widened_panelB_run01.json")


def read_answers(path: Path | None = None) -> list[dict]:
    """R2's answer rows, or `[]` when the file is not on this checkout.

    `[]` rather than an exception: a job that has no answers to read must say
    so in its receipt, not traceback. Callers check the length.
    """
    path = path or R2_PANEL_B_ANSWERS
    if not Path(path).is_file():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a half-written last line during a live read
    return out


def by_tag(rows: list[dict], tag: str) -> list[dict]:
    return [r for r in rows if str(r.get("tag")) == tag]


def sign_accuracy(rows: list[dict]) -> tuple[float | None, int]:
    """Directional hit rate and its n, on R2's own convention.

    FLAT calls (`dir == 0`) are excluded from the numerator AND the
    denominator, exactly as `night_r2_monthly_llm.grade` does -- a model that
    says FLAT has made no directional call, and counting it as a miss would
    make abstention look like error.
    """
    graded = [r for r in rows
              if r.get("dir") not in (None, 0) and r.get("fwd") is not None]
    if not graded:
        return None, 0
    hits = sum(1 for r in graded
               if (float(r["fwd"]) > 0) == (int(r["dir"]) > 0))
    return hits / len(graded), len(graded)


def amnesia_gap(receipt: Path | None = None, answers: Path | None = None) -> dict:
    """R2's real-name-minus-masked canary gap, from the receipt if it has one.

    Spec section 2.3 says IMPORT this rather than re-derive it. R2's PANEL-B
    receipt is `PENDING_MODEL` (written before the first model call) and carries
    no canary block, so the fallback reads the canary rows out of R2's own
    persisted answers -- still R2's output, not a fresh computation on different
    cells. `source` says which, because "imported" and "re-derived from the same
    file" are different claims and only one of them is what the spec asked for.
    """
    path = Path(receipt or R2_PANEL_B_RECEIPT)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                          # noqa: BLE001
            payload = {}
        canary = payload.get("AMNESIA_canary") or {}
        gap = canary.get("accuracy_gap_real_minus_masked")
        if gap is not None:
            return {"gap": float(gap), "source": str(path),
                    "how": "imported from R2's own canary receipt"}
    rows = read_answers(answers)
    real, n_real = sign_accuracy(by_tag(rows, "canary_REAL_names"))
    mask, n_mask = sign_accuracy(by_tag(rows, "canary_MASKED"))
    if real is None or mask is None:
        return {"gap": None, "source": str(answers or R2_PANEL_B_ANSWERS),
                "how": ("CANNOT DETERMINE: R2's receipt carries no canary block and its "
                        "answers file has no gradeable canary rows")}
    return {"gap": round(real - mask, 4), "source": str(answers or R2_PANEL_B_ANSWERS),
            "how": ("re-derived from R2's PERSISTED canary answers -- its receipt is "
                    "PENDING_MODEL and carries no canary block"),
            "real_names_accuracy": round(real, 4), "n_real": n_real,
            "masked_accuracy": round(mask, 4), "n_masked": n_mask}


def stratified_cells(keys, *, n: int, seed: int, block_of=None) -> list:
    """`n` cells drawn EQUALLY ACROSS DATE BLOCKS, deterministically.

    `keys` is any iterable of cell keys; `block_of` maps a key to its block
    (default: the second element, which is the month in every X-lane key shape).
    Blocks are filled round-robin from their own shuffled order, so a short
    block contributes everything it has and the remainder spills to the blocks
    that still have cells -- the draw is `min(n, len(keys))` and never silently
    short.
    """
    block_of = block_of or (lambda k: k[1])
    buckets: dict[str, list] = {}
    for k in sorted(keys):
        buckets.setdefault(str(block_of(k)), []).append(k)
    rng = random.Random(seed)
    for b in buckets.values():
        rng.shuffle(b)
    out: list = []
    order = sorted(buckets)
    while len(out) < n and any(buckets[b] for b in order):
        for b in order:
            if not buckets[b]:
                continue
            out.append(buckets[b].pop())
            if len(out) >= n:
                break
    return sorted(out)


def cells_fingerprint(cells) -> dict:
    """A hash of the exact cell list, so a re-run can prove it asked the same.

    2026-09-10's lesson in the other direction: a night that reproduced a
    previous night's genomes exactly had discovery zero and nothing in the code
    could say so. Here reproducing the list exactly is the POINT (the model was
    down; the same cells must be asked when it is up), and the hash is how that
    is checked rather than asserted.
    """
    payload = json.dumps([list(c) for c in cells], separators=(",", ":"), sort_keys=False)
    return {"n_cells": len(list(cells)),
            "cells_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}
