"""Calibration report for the prediction ledger — the cross-tab calibration()
could not produce.

`belief_state.calibration()` slices by ONE key. The question the ledger exists
to answer is jointly conditional — "is the biotech specialist overconfident on
6-month drawdown calls?" — so this report cross-tabs by
specialist × observable × horizon_days. PredictionRecord has NO category
field: the SPECIALIST is the category (each specialist covers one sector/role
by construction), and inventing a second category axis here would be a schema
claim the records cannot back.

HONESTY CONVENTIONS (same as conviction_calibration.reliability_curve)
----------------------------------------------------------------------
* Every cell prints its n. A sparse cell prints n and None — never a smoothed,
  shrunk, or borrowed number.
* Unmatured records are counted as PENDING in their cell and are never scored.
* Void records appear only in the totals (n_void); they are in no cell —
  grading one would charge a forecaster for a defect.
* `beats_climatology` is the only recognised meaning of "the forecast was
  informative", and it is None until the cell has resolved records.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.services.belief_state import ledger_health, read_predictions

#: Composite-key separator for the cross-tab. Ticker names never contain it.
KEY_SEP = "|"


def _cell_stats(records: list[dict]) -> dict:
    """Stats for one cell. Resolved records only feed the scores; pending ones
    only feed the pending count. None where there is nothing to compute."""
    resolved = [r for r in records if r.get("outcome") is not None]
    pending = [r for r in records if r.get("outcome") is None]
    out: dict = {
        "n": len(records),
        "n_resolved": len(resolved),
        "n_pending": len(pending),
        "brier": None,
        "climatology_brier": None,
        "beats_climatology": None,
        "base_rate": None,
        "mean_probability": None,
        "overconfidence": None,
    }
    if not resolved:
        return out
    briers = [r["brier"] for r in resolved]
    base = sum(r["outcome"] for r in resolved) / len(resolved)
    mean_p = sum(r["probability"] for r in resolved) / len(resolved)
    brier = sum(briers) / len(briers)
    clim = base * (1 - base)
    out.update({
        "brier": brier,
        "climatology_brier": clim,
        "beats_climatology": bool(brier < clim),
        "base_rate": base,
        "mean_probability": mean_p,
        "overconfidence": mean_p - base,
    })
    return out


def calibration_report(path: Path | None = None, *,
                       today: date | None = None) -> dict:
    """Specialist × observable × horizon_days cross-tab, plus a per-specialist
    aggregate. Keys are composite strings "specialist|observable|horizon".

    `today` is injectable and feeds the attached ledger_health row; the scoring
    itself never looks at the clock — a record is scored iff resolve_all
    already graded it, and pending records are counted, never scored.
    """
    today = today or date.today()
    rows = read_predictions(path)
    scoreable = [r for r in rows if not r.get("void_reason")]

    cells: dict[str, list[dict]] = {}
    by_specialist: dict[str, list[dict]] = {}
    for r in scoreable:
        key = KEY_SEP.join([str(r.get("specialist", "?")),
                            str(r.get("observable", "?")),
                            str(r.get("horizon_days", "?"))])
        cells.setdefault(key, []).append(r)
        by_specialist.setdefault(str(r.get("specialist", "?")), []).append(r)

    return {
        "as_of": str(today),
        "n_records": len(rows),
        "n_void": sum(1 for r in rows if r.get("void_reason")),
        "n_resolved": sum(1 for r in scoreable
                          if r.get("outcome") is not None),
        "n_pending": sum(1 for r in scoreable if r.get("outcome") is None),
        "key": f"specialist{KEY_SEP}observable{KEY_SEP}horizon_days "
               "(specialist IS the category — the schema has no separate one)",
        "cells": {k: _cell_stats(v) for k, v in sorted(cells.items())},
        "by_specialist": {k: _cell_stats(v)
                          for k, v in sorted(by_specialist.items())},
        "health": ledger_health(path, today=today),
        "note": ("sparse cells print n and None, never a smoothed number; "
                 "pending records are counted and never scored; a Brier below "
                 "climatology is the only recognised meaning of 'informative'"),
    }
