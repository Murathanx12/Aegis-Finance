"""AEGIS-PANEL-2's declared instrument spec: the floor, the features, the key.

Panel-1 was built by joining a CRSP-PIT spine to JKP characteristics and
computing seven PRICE_FLOOR features from daily prices. Panel-2 is built
straight from JKP's own USA history and deliberately does NOT recompute those
seven (`scripts/aegis_panel2_build.py`, docstring): "the floor arms for
TOURNAMENT-2 come from JKP's own price columns ... declared in that prereg, so
v2 needs no daily-file join at all."

That deferral put the floor on the critical path of something that must happen
BEFORE the prereg exists. The detectability gate requires planted worlds run on
this panel, every planted world contrasts its arms against the floor, and the
prereg that was supposed to declare the floor cannot be written until the gate
passes. So the floor is declared HERE, once, ahead of the prereg, under the
only condition that makes a pre-declaration honest:

  **the mapping is chosen by CONSTRUCTION, never by outcome.** Each panel-2
  floor column is the JKP column that computes the same quantity as its
  panel-1 counterpart, at the nearest available horizon. Nothing below was
  selected by looking at a return, an IC, or a contrast, and the frozen
  receipt exists so a later reader can check that the set did not move after
  results arrived.

One substitution is inexact and is named rather than buried: JKP publishes no
63-day realised volatility, so panel-1's `vol_63` maps to `rvol_252d`, the
nearest realised-vol horizon. Every other pairing is exact.

Keeping the floor construction-matched to panel-1 (rather than inventing a
new baseline from the same columns) is what makes panel-2's contrast readable
against panel-1's NOT_ESTABLISHED: the instrument changes scale and universe,
not the question.

ONE STRUCTURAL DIFFERENCE, stated because it changes what a verdict means.
On panel-1 the floor was computed from daily prices and was DISJOINT from the
412 JKP characteristics. Here the floor columns are drawn from the
characteristic set itself, so the full arm strictly contains the floor arm and
the contrast asks the sharper question: **do the other 405 characteristics add
anything beyond these 7 price columns?** Panel-1's full arm also contained its
floor, so the nesting is the same shape — but there the floor was extra
information and here it is a subset, and a reader comparing the two receipts
should know which.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend import config as _config

PANEL = "AEGIS-PANEL-2"
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "aegis_panel"
PANEL_PATH = OUT_DIR / "aegis_panel_v2.parquet"
META_PATH = OUT_DIR / "aegis_panel_v2.meta.json"
PANEL1_META = OUT_DIR / "aegis_panel_v1.meta.json"

#: The label JKP carries natively: next month's delisting-aware excess return.
LABEL = "ret_exc_lead1m"

#: Row keys. `eom` is the formation month end; `date` is the observation date
#: the IC is computed by.
DATE_COL = "date"
MONTH_COL = "eom"
ENTITY_COL = "permno"

#: panel-1 floor feature -> panel-2 JKP column, matched on what the number IS.
#: Ordered as panel-1 declares them so the correspondence is readable.
FLOOR_MAP: dict[str, str] = {
    "mom_21": "ret_1_0",             # trailing 1-month total return
    "mom_63": "ret_3_0",             # trailing 3-month
    "mom_126": "ret_6_0",            # trailing 6-month
    "mom_252_21": "ret_12_1",        # 12-1 momentum (exact analogue)
    "vol_21": "rvol_21d",            # 21-day realised volatility
    "vol_63": "rvol_252d",           # INEXACT: no 63d rvol in JKP
    "dd_252": "prc_highprc_252d",    # price relative to its 252-day high
}

FLOOR_FEATURES: tuple[str, ...] = tuple(FLOOR_MAP.values())

#: Named so a reader never has to diff two tuples to find the soft spot.
INEXACT_FLOOR_PAIRS = {"vol_63": "rvol_252d"}


class Panel2SpecRefused(RuntimeError):
    """The panel on disk cannot supply the instrument this spec declares."""


def _panel_columns() -> list[str]:
    import pyarrow.parquet as pq

    if not PANEL_PATH.exists():
        raise Panel2SpecRefused(
            f"{PANEL_PATH} does not exist — AEGIS-PANEL-2 has not been built, "
            f"and a spec over an absent panel describes nothing")
    return list(pq.ParquetFile(PANEL_PATH).schema_arrow.names)


def resolve(columns: list[str] | None = None) -> dict:
    """The instrument, derived from the panel on disk and REFUSED if incomplete.

    Derives rather than hardcodes the feature list: the 412 characteristics are
    panel-1's declared family map intersected with what panel-2 actually
    carries, so a column that silently vanished from the build cannot sit in an
    arm's feature list as a name nobody supplies. A missing FLOOR column is
    fatal — every contrast in the tournament is measured against the floor, and
    a floor quietly short one feature would move every number in the receipt
    while the arm names stayed the same.
    """
    cols = list(columns) if columns is not None else _panel_columns()
    have = set(cols)

    missing_floor = [c for c in FLOOR_FEATURES if c not in have]
    if missing_floor:
        raise Panel2SpecRefused(
            f"panel-2 is missing declared FLOOR columns {missing_floor} — the "
            f"baseline every arm is contrasted against cannot be built, so no "
            f"contrast on this panel means what its name says")
    for c in (LABEL, DATE_COL, MONTH_COL, ENTITY_COL):
        if c not in have:
            raise Panel2SpecRefused(
                f"panel-2 is missing the required column {c!r}")

    fam1 = json.loads(PANEL1_META.read_text(encoding="utf-8"))["family_map"]
    # panel-1's PRICE_FLOOR entries are its OWN construction and are replaced
    # here by the JKP analogues above; everything else is a JKP characteristic.
    chars = {c: f for c, f in fam1.items()
             if f != "PRICE_FLOOR" and c in have}
    absent = sorted(c for c, f in fam1.items()
                    if f != "PRICE_FLOOR" and c not in have)
    if absent:
        raise Panel2SpecRefused(
            f"{len(absent)} characteristic(s) declared by panel-1's family map "
            f"are absent from panel-2 ({absent[:8]}...) — the 'same instrument "
            f"at scale' claim would be false, and silently so")

    family_map = dict(chars)
    family_map.update({c: "PRICE_FLOOR" for c in FLOOR_FEATURES})
    # The floor columns ARE characteristics here — unlike panel-1, where the
    # floor was computed from daily prices and was disjoint from JKP. So
    # `full` is the 412 characteristics with the floor already among them, and
    # the nesting is exact: the contrast asks whether the OTHER 405 add
    # anything beyond these 7. Listing the floor twice would hand the full arm
    # duplicate columns and quietly change what it was fed.
    full = list(FLOOR_FEATURES) + sorted(c for c in chars
                                         if c not in set(FLOOR_FEATURES))
    return {
        "panel": PANEL,
        "label": LABEL,
        "floor": list(FLOOR_FEATURES),
        "full": full,
        "family_map": family_map,
        "n_characteristics": len(chars),
        "n_full_features": len(full),
        "floor_is_subset_of_full": True,
        "n_beyond_floor": len(full) - len(FLOOR_FEATURES),
        "keys": {"date": DATE_COL, "month": MONTH_COL, "entity": ENTITY_COL},
    }


def spec_hash(spec: dict | None = None) -> str:
    """Identity of the INSTRUMENT (not the data). A receipt carries both, so
    a floor that moved after results arrived is visible as a changed hash."""
    spec = spec or resolve()
    payload = {"floor": spec["floor"], "full": spec["full"],
               "label": spec["label"]}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def panel_hash(path: Path = PANEL_PATH) -> str:
    """Content hash of the panel file — what the detectability gate compares
    against, so panel-1 evidence can never license a panel-2 run."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def freeze(out: Path | None = None) -> dict:
    """Write the declaration receipt. Idempotent while the spec is unchanged;
    a changed spec writes a changed hash rather than overwriting silently."""
    spec = resolve()
    rec = {
        "declaration": "AEGIS_PANEL_2_INSTRUMENT",
        "panel": PANEL,
        "declared_at": "2026-08-23",
        "chosen_by": ("construction-matched to AEGIS-PANEL-1's floor; no "
                      "outcome, IC or contrast was consulted"),
        "floor_map": FLOOR_MAP,
        "inexact_pairs": INEXACT_FLOOR_PAIRS,
        "n_characteristics": spec["n_characteristics"],
        "label": LABEL,
        "spec_hash": spec_hash(spec),
        "panel_hash": panel_hash(),
        "note": ("declared BEFORE the TOURNAMENT-2 prereg because the "
                 "detectability gate the prereg is blocked on cannot run "
                 "without a floor; the prereg must CITE this hash, not "
                 "restate the set"),
    }
    p = out or (OUT_DIR / "aegis_panel2_instrument.json")
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


if __name__ == "__main__":  # pragma: no cover — thin CLI
    print(json.dumps(freeze(), indent=2))
