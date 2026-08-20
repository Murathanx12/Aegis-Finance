"""The counting brain: what has this machine actually been right about?

A READER over the append-only arena files. It never writes into them, never
mutates an outcome, and holds no model — it counts. That is deliberate: the
eventual router (P4) must beat a counting baseline before a neural
representation earns its gate, and a baseline you have not built is a baseline
you cannot lose to.

Two populations, never pooled into one statistic:

  decision cells   rules decisions (ENTER/HOLD/REJECT/…) joined to matured
                   outcomes. There is no probability here, so there is no
                   Brier here — `confidence` is a rank transform, not a
                   calibrated belief, and scoring it as one would manufacture
                   calibration out of an ordering.
  forecast cells   LLM PredictionRecords with a real probability and a
                   resolved binary outcome. Brier, base rate, skill and the
                   Murphy decomposition, via `iif1_grader.brier_with_base_rate`.

Every cell carries its n. Below `MIN_CELL_N` a cell reports REFUSED_THIN and
NO rate: a hit rate over four events is a description of four events, and the
whole failure mode this file exists to prevent is one of them being read as
skill.

State conditioning is the decision-day cross-sectional vol63 tercile, read
from the FROZEN snapshot — the same object the decision was made against, so
the state label cannot drift after the fact.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from backend.services.arena import experience as exp_mod
from backend.services.arena import store

logger = logging.getLogger(__name__)

#: Below this, a cell reports its n and refuses to report a rate.
MIN_CELL_N = 20

#: Below this, a cell is not even worth carrying in the payload.
REPORT_FLOOR_N = 1

VOL_STATES = ("LOW_VOL", "MID_VOL", "HIGH_VOL", "UNKNOWN_VOL")

TOOK_ACTIONS = frozenset({"ENTER", "HOLD", "SWAP_IN", "EXEMPT_TRIM"})

LEGS = {
    "forecast": ("excess_return", "outcome_class"),
    "execution": ("execution_excess_return", "execution_outcome_class"),
}


class ReliabilityRefused(RuntimeError):
    """The join this statistic needs does not exist."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── state labels from the frozen snapshots ──────────────────────────────────
def _terciles(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 6:  # two per bucket, minimum, or the label is noise
        return None
    s = sorted(values)
    return s[len(s) // 3], s[2 * len(s) // 3]


def state_labels(root=None) -> dict[str, dict[str, str]]:
    """{decision_date: {ticker: vol tercile label}} from frozen snapshots.

    A day whose snapshot is absent, or too thin to tercile, labels every name
    UNKNOWN_VOL. That is a real category with its own cells — it is not folded
    into MID, which would put un-stated states inside a stated one.
    """
    out: dict[str, dict[str, str]] = {}
    for day in store.snapshot_dates(root):
        snap = store.read_snapshot(day, root) or {}
        names = (snap.get("state") or {}).get("names") or {}
        vols = {t: r.get("vol63") for t, r in names.items()
                if r.get("status") == "ok" and r.get("vol63") is not None}
        cut = _terciles([float(v) for v in vols.values()])
        if cut is None:
            out[day] = {t: "UNKNOWN_VOL" for t in names}
            continue
        lo, hi = cut
        out[day] = {
            t: ("LOW_VOL" if float(v) <= lo
                else "HIGH_VOL" if float(v) > hi else "MID_VOL")
            for t, v in vols.items()
        }
    return out


# ── decision cells ──────────────────────────────────────────────────────────
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _cell_stats(rows: list[dict], *, min_n: int) -> dict:
    """One decision cell. `signed_excess` is the decision-quality unit: excess
    for an action that took the position, MINUS excess for one that passed on
    it, so a positive mean means the decision added value either way."""
    n = len(rows)
    base = {"n": n, "min_n": min_n}
    if n < min_n:
        # The n IS the finding. No rate, so nothing here can be quoted as one.
        return {**base, "verdict": "REFUSED_THIN",
                "note": f"n={n} < min_n={min_n}; no rate computed"}
    signed = [r["_signed"] for r in rows]
    hits = [1 if r["_class"] in ("GOOD_CALL", "GOOD_PASS") else 0 for r in rows]
    excess = [r["_excess"] for r in rows]
    took = [r for r in rows if r["_took"]]
    passed = [r for r in rows if not r["_took"]]
    return {
        **base,
        "verdict": "REPORTED",
        "hit_rate": round(_mean(hits), 4),
        "mean_signed_excess": round(_mean(signed), 6),
        "mean_excess": round(_mean(excess), 6),
        "n_took": len(took),
        "n_passed": len(passed),
        "mean_excess_when_took": (round(_mean([r["_excess"] for r in took]), 6)
                                  if took else None),
        "mean_excess_when_passed": (round(_mean([r["_excess"] for r in passed]), 6)
                                    if passed else None),
    }


def decision_cells(*, root=None, leg: str = "forecast",
                   min_n: int = MIN_CELL_N,
                   by: tuple[str, ...] = ("book_id", "model_id",
                                          "horizon_days", "vol_state")) -> dict:
    """Reliability of the RULES decisions, per cell of `by`.

    Refuses to pool outcome-schema versions: v1 rows carried a single
    close→close leg under the name `excess_return`, v2 splits forecast from
    execution. Counting them together would silently answer the execution
    question with forecast numbers for part of the sample.
    """
    if leg not in LEGS:
        raise ReliabilityRefused(f"unknown leg {leg!r}; expected {sorted(LEGS)}")
    excess_key, class_key = LEGS[leg]
    labels = state_labels(root)
    exps = {e["experience_id"]: e for e in store.read_experiences(root)}
    outs = store.read_outcomes(root)

    legacy = [o for o in outs
              if int(o.get("schema_version") or 1) < exp_mod.OUTCOME_SCHEMA_VERSION]
    usable = [o for o in outs
              if int(o.get("schema_version") or 1) >= exp_mod.OUTCOME_SCHEMA_VERSION]

    cells: dict[tuple, list[dict]] = {}
    unmatched = 0
    unresolved = 0
    for o in usable:
        e = exps.get(o.get("experience_id"))
        if e is None:
            unmatched += 1
            continue
        ex = o.get(excess_key)
        if ex is None:
            unresolved += 1
            continue
        action = o.get("action") or e.get("action")
        took = action in TOOK_ACTIONS
        row = {
            "_excess": float(ex),
            "_signed": float(ex) if took else -float(ex),
            "_class": o.get(class_key) or "UNRESOLVED",
            "_took": took,
        }
        ctx = {
            "book_id": o.get("book_id") or e.get("book_id"),
            "model_id": e.get("model_id"),
            "action": action,
            "horizon_days": o.get("horizon_days"),
            "vol_state": (labels.get(str(o.get("decision_date")), {})
                          .get(o.get("entity_key"), "UNKNOWN_VOL")),
            "policy_version": e.get("policy_version"),
        }
        missing = [k for k in by if k not in ctx]
        if missing:
            raise ReliabilityRefused(
                f"cannot group by {missing} — available keys: {sorted(ctx)}")
        cells.setdefault(tuple(str(ctx[k]) for k in by), []).append(row)

    reported = {}
    for key, rows in sorted(cells.items()):
        if len(rows) < REPORT_FLOOR_N:
            continue
        reported["|".join(key)] = {**dict(zip(by, key)),
                                   **_cell_stats(rows, min_n=min_n)}
    n_reported = sum(1 for c in reported.values()
                     if c.get("verdict") == "REPORTED")
    return {
        "leg": leg,
        "basis": (exp_mod.FORECAST_BASIS if leg == "forecast"
                  else exp_mod.EXECUTION_BASIS),
        "grouped_by": list(by),
        "min_n": min_n,
        "n_outcome_rows": len(outs),
        "n_rows_used": len(usable),
        "n_rows_dropped_legacy_schema": len(legacy),
        "n_outcomes_without_experience": unmatched,
        "n_outcomes_unpriced": unresolved,
        "n_cells": len(reported),
        "n_cells_reported": n_reported,
        "n_cells_refused_thin": len(reported) - n_reported,
        "cells": reported,
    }


# ── forecast cells (LLM predictions with a real probability) ────────────────
def forecast_cells(*, root=None, min_n: int = MIN_CELL_N,
                   by: tuple[str, ...] = ("specialist", "horizon_days",
                                          "vol_state")) -> dict:
    """Brier/skill for the arena's own LLM ledger, per cell.

    Uses `iif1_grader.brier_with_base_rate`, which REFUSES a degenerate base
    rate rather than printing a Brier that would read as a fact about the
    forecaster when it is a fact about the sample.
    """
    from backend.services.iif1_grader import GradeRefused, brier_with_base_rate

    labels = state_labels(root)
    rows = [r for r in store._read_jsonl(store.predictions_path(root))
            if r.get("outcome") is not None and not r.get("void_reason")]
    pending = sum(1 for r in store._read_jsonl(store.predictions_path(root))
                  if r.get("outcome") is None and not r.get("void_reason"))
    cells: dict[tuple, list[dict]] = {}
    for r in rows:
        day = str(r.get("made_at", ""))[:10]
        ctx = {
            "specialist": r.get("specialist"),
            "model": r.get("model"),
            "observable": r.get("observable"),
            "horizon_days": r.get("horizon_days"),
            "vol_state": labels.get(day, {}).get(r.get("ticker"),
                                                 "UNKNOWN_VOL"),
        }
        missing = [k for k in by if k not in ctx]
        if missing:
            raise ReliabilityRefused(
                f"cannot group by {missing} — available keys: {sorted(ctx)}")
        cells.setdefault(tuple(str(ctx[k]) for k in by), []).append(r)

    reported = {}
    for key, group in sorted(cells.items()):
        head = {**dict(zip(by, key)), "n": len(group), "min_n": min_n}
        if len(group) < min_n:
            reported["|".join(key)] = {
                **head, "verdict": "REFUSED_THIN",
                "note": f"n={len(group)} < min_n={min_n}; no Brier computed"}
            continue
        try:
            g = brier_with_base_rate(
                [float(r["probability"]) for r in group],
                [int(r["outcome"]) for r in group],
                label="arena:" + "|".join(key))
        except GradeRefused as exc:
            reported["|".join(key)] = {**head, "verdict": "REFUSED_DEGENERATE",
                                       "note": str(exc)}
            continue
        reported["|".join(key)] = {**head, "verdict": "REPORTED", **g}
    n_reported = sum(1 for c in reported.values()
                     if c.get("verdict") == "REPORTED")
    return {
        "grouped_by": list(by),
        "min_n": min_n,
        "n_resolved": len(rows),
        "n_pending": pending,
        "n_cells": len(reported),
        "n_cells_reported": n_reported,
        "cells": reported,
        "note": ("probabilities here are the LLM's posteriors; nothing in this "
                 "block is evidence of skill (PRODUCT_EXPERIMENT)"),
    }


# ── daily snapshot ─────────────────────────────────────────────────────────
def _compact(report: dict) -> dict:
    """Keep only the cells that actually REPORTED, plus the refusal counts.

    A daily row carrying every thin cell would grow ~500 KB/day on the volume
    to persist the sentence "still not enough data", which the counts already
    say. The full picture stays one recompute away (`/api/arena/reliability?
    live=true`), and the refused cells are counted here so their absence is
    stated rather than assumed.
    """
    cells = report.get("cells") or {}
    kept = {k: v for k, v in cells.items() if v.get("verdict") == "REPORTED"}
    refused: dict[str, int] = {}
    for v in cells.values():
        if v.get("verdict") != "REPORTED":
            refused[v["verdict"]] = refused.get(v["verdict"], 0) + 1
    return {**{k: v for k, v in report.items() if k != "cells"},
            "cells": kept, "cells_omitted_by_verdict": refused,
            "cells_omitted_note": ("non-REPORTED cells are counted, not "
                                   "stored; recompute live for the detail")}


def snapshot(*, today: date | None = None, root=None,
             min_n: int = MIN_CELL_N) -> dict:
    """Append one reliability row per day. Idempotent per (date, min_n)."""
    day = str(today or date.today())
    existing = {(r.get("date"), r.get("min_n"))
                for r in store.read_reliability(root)}
    if (day, min_n) in existing:
        return {"status": "already_snapshotted", "date": day}
    rec = {
        "date": day,
        "computed_at": _now(),
        "min_n": min_n,
        "validation_status": "PRODUCT_EXPERIMENT",
        "simulation": True,
        "decisions_forecast": _compact(decision_cells(root=root,
                                                      leg="forecast",
                                                      min_n=min_n)),
        "decisions_execution": _compact(decision_cells(root=root,
                                                       leg="execution",
                                                       min_n=min_n)),
        "forecasts": _compact(forecast_cells(root=root, min_n=min_n)),
    }
    store.append_reliability([rec], root)
    return {"status": "ok", "date": day,
            "cells_reported": (rec["decisions_forecast"]["n_cells_reported"]
                               + rec["forecasts"]["n_cells_reported"]),
            "cells_total": (rec["decisions_forecast"]["n_cells"]
                            + rec["forecasts"]["n_cells"])}


def latest(root=None) -> dict | None:
    rows = store.read_reliability(root)
    return rows[-1] if rows else None


def _cli() -> None:  # pragma: no cover - manual driver
    print(json.dumps(snapshot(), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    _cli()
