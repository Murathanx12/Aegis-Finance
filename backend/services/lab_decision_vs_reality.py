"""DECISION VS REALITY — one daily roll-up across every mechanism.

Chunk 14, spec `docs/research_notes/2026-09-13/spec_always_on_lab.md` section 3.3.
Murat, 2026-09-13: "decision vs reality".

THIS MODULE RE-GRADES NOTHING
=============================
Every `PredictionRecord` the system writes is already graded by its OWN
mechanism's existing grader — the books by `book_forecasts.trailing_ir` and the
ledger resolver, the scenario forecasts by X3's own, the morning read by its
own. This is a NEW AGGREGATE over what those graders already wrote: once an
hour, every record RESOLVED in the trailing window, grouped by mechanism, by
event type and by regime, with one worst miss carrying its thesis and
counter-thesis side by side.

It is roadmap lane B6's "Regret page" generalised: B6 is the PER-BOOK view;
this is the CROSS-mechanism roll-up B6 does not attempt.

THE ADMISSION GATE IS IMPORTED, NOT RE-IMPLEMENTED
==================================================
`ledger_retrieval.visible_at(record, t)` decides what may be read at `t`, and
it is called here rather than approximated. A record graded early must not be
ADMITTED early: "resolved before t, graded before t, outcome present" is four
clauses and a re-implementation gets three of them right. `test_..._admits_only
_hindsight_safe_rows` asserts through a spy that the real predicate ran, so an
edit that inlines a similar-looking check fails rather than drifting from M3.

A DAY WITH NOTHING RESOLVED STILL WRITES A RECEIPT
==================================================
Every declared mechanism gets a row with `n_resolved: 0` rather than being
omitted. A group that vanishes is a group nobody notices is missing — the rule
this repository has restated more often than any other and skipped most.

WHAT IT IS NOT
==============
Not a promotion gate, not a capital decision, not an order path. It reads
ledgers and writes one JSON file. The `worst_miss` block is for a human to
read; nothing downstream branches on it.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("lab_decision_vs_reality")

#: Every mechanism this roll-up REPORTS ON, whether or not it has written a
#: record yet. Declared rather than discovered: a mechanism that has produced
#: nothing is the one a reader most needs to see named, and discovering the
#: group list from the data makes an absent mechanism invisible.
#:
#: `status` is what the mechanism is TODAY, in one word a card can print.
DECLARED_MECHANISMS: tuple[tuple[str, str, str], ...] = (
    ("paper_book_v1", "live", "the paper books' own per-decision forecasts (B5)"),
    ("x3_scenario_forecast_v1", "not_wired_yet",
     "X3's contract exists and is tested; it needs L2's typed rows and E1's "
     "base-rate table, neither of which has real data yet"),
    ("reaction_longshort_v1", "live", "the reaction book's event-clock forecasts"),
    ("hiring_pivot_ai_v1", "live",
     "ATS job-board AI-role share, TRIAL-HIRING-PIVOT-1"),
    ("holders_13f_v1", "live_weak",
     "13F institutional ownership; 45-day filing lag, THIN by construction"),
    ("pivot_to_ai_narrative_v1", "placeholder",
     "awaits a strategic-pivot event id in the typed vocabulary"),
    ("management_motivation_v1", "placeholder",
     "no collector exists: earnings-call and shareholder-letter text is not "
     "ingested as a labelled source in this repository"),
)

#: The trailing window the hourly tick reports on.
WINDOW_HOURS = 24

#: Below this, a Brier is printed but no verdict is drawn from it. The number is
#: `calibration.MIN_N_FOR_DECOMPOSITION`'s sibling and is deliberately smaller:
#: a 24-hour window will rarely carry 45 resolutions, and a roll-up that says
#: `insufficient_n` every single day teaches its reader to skip it.
MIN_N_FOR_A_VERDICT = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def read_ledger(path: Path | None = None) -> list[dict]:
    """The prediction ledger, through `belief_state`'s own reader."""
    from backend.services import belief_state
    return belief_state.read_predictions(path)


def resolved_in_window(rows: Iterable[dict], *, as_of: datetime,
                       window_hours: int = WINDOW_HOURS,
                       visible=None) -> tuple[list[dict], dict]:
    """Records resolved inside the window AND admissible at `as_of`.

    Two gates, in this order, and both of them matter:

    1. `visible_at(record, as_of.date())` — the hindsight gate, IMPORTED. It is
       what stops a record graded after the cut-off from being read as if it
       had been graded before it.
    2. the window — `resolved_at` inside the trailing `window_hours`.

    Returns (rows, why-the-rest-were-dropped), because a roll-up that came back
    empty and a roll-up that was never run look identical to a reader unless
    the dropped counts are printed beside the kept ones.
    """
    if visible is None:
        from backend.services.ledger_retrieval import visible_at as visible
    cutoff = as_of - timedelta(hours=window_hours)
    kept: list[dict] = []
    dropped: dict = {"not_visible_at_as_of": 0, "outside_window": 0,
                     "no_resolved_at": 0, "reasons": {}}
    for r in rows:
        ok, why = visible(r, as_of.date())
        if not ok:
            dropped["not_visible_at_as_of"] += 1
            dropped["reasons"][why or "unstated"] = \
                dropped["reasons"].get(why or "unstated", 0) + 1
            continue
        when = _as_dt(r.get("resolved_at") or r.get("graded_at"))
        if when is None:
            dropped["no_resolved_at"] += 1
            continue
        if not (cutoff <= when <= as_of):
            dropped["outside_window"] += 1
            continue
        kept.append(r)
    return kept, dropped


def _brier(rows: list[dict]) -> dict:
    from backend.services import calibration
    res = calibration.resolved_rows(rows)
    if not res:
        return {"n": 0, "brier": None, "decomposition": "insufficient_n"}
    return calibration.brier_decomposition(
        [float(r["probability"]) for r in res], [float(r["outcome"]) for r in res])


def _base_rate_brier(rows: list[dict]) -> float | None:
    """The POINT-IN-TIME base-rate control's own Brier on the same rows."""
    from backend.services import calibration
    res = calibration.resolved_rows(rows)
    if not res:
        return None
    row = calibration.base_rate_row(res)
    b = row.get("brier")
    return None if b is None else float(b)


def _group(rows: list[dict], key) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(key(r) or "unstated", []).append(r)
    return out


def _mechanism_row(mech: str, rows: list[dict], status: str, what: str) -> dict:
    dec = _brier(rows)
    n = int(dec.get("n") or 0)
    base = _base_rate_brier(rows)
    brier = dec.get("brier")
    delta = (None if (brier is None or base is None) else round(brier - base, 6))
    row = {
        "mechanism_id": mech,
        "declared_status": status,
        "what": what,
        "n_resolved": n,
        "brier": (None if brier is None else round(float(brier), 6)),
        "base_rate_brier": (None if base is None else round(base, 6)),
        "brier_vs_base_rate": delta,
        "beats_base_rate": (None if delta is None else bool(delta < 0)),
        "reliability": dec.get("reliability"),
        "resolution": dec.get("resolution"),
        "uncertainty": dec.get("uncertainty"),
        "murphy": dec.get("decomposition"),
    }
    if n == 0:
        row["status"] = ("not_wired_yet" if status in ("not_wired_yet", "placeholder")
                         else "nothing_resolved_in_window")
    elif n < MIN_N_FOR_A_VERDICT:
        row["status"] = "insufficient_n"
        row["insufficient_n_note"] = (
            f"{n} resolved in the window, below {MIN_N_FOR_A_VERDICT}. The Brier "
            f"is printed and no verdict is drawn from it.")
    else:
        row["status"] = "ok"
    return row


def worst_miss(rows: list[dict]) -> dict | None:
    """The single worst-scored record, with its own thesis and counter-thesis.

    Both sides, verbatim from the record, because the useful unit is
    "what we believed, what would have falsified it, and what happened" — a
    gallery of misses without the counter-thesis is a gallery of survivors with
    the sign flipped.
    """
    from backend.services import calibration
    res = calibration.resolved_rows(rows)
    if not res:
        return None
    scored = [(float(r["probability"]) - float(r["outcome"])) ** 2 for r in res]
    i = max(range(len(res)), key=lambda k: scored[k])
    r = res[i]
    return {
        "mechanism_id": r.get("mechanism_id"),
        "record_id": r.get("prediction_id"),
        "ticker": r.get("ticker"),
        "observable": r.get("observable"),
        "thesis": r.get("thesis"),
        "counter_thesis": r.get("counter_thesis"),
        "predicted": float(r["probability"]),
        "outcome": int(r["outcome"]),
        "brier": round(scored[i], 6),
        "made_at": r.get("made_at"),
        "resolved_at": r.get("resolved_at"),
        "control_twin_id": r.get("control_twin_id"),
        "vs_control": r.get("vs_control"),
        "vs_benchmark": r.get("vs_benchmark"),
    }


def report(*, as_of: datetime | None = None, rows: Iterable[dict] | None = None,
           path: Path | None = None, window_hours: int = WINDOW_HOURS,
           visible=None) -> dict:
    """The whole cross-mechanism roll-up. Reads ledgers; writes nothing."""
    as_of = as_of or datetime.now(timezone.utc)
    pool = list(rows) if rows is not None else read_ledger(path)
    kept, dropped = resolved_in_window(pool, as_of=as_of,
                                       window_hours=window_hours, visible=visible)

    by_mech = _group(kept, lambda r: r.get("mechanism_id"))
    declared = {m: (s, w) for m, s, w in DECLARED_MECHANISMS}
    mech_rows = [_mechanism_row(m, by_mech.get(m, []), s, w)
                 for m, (s, w) in declared.items()]
    # A mechanism writing records that nobody declared is a finding, not a
    # silent extra row: it means this module's declared list has drifted behind
    # the code that writes forecasts.
    undeclared = sorted(set(by_mech) - set(declared))
    mech_rows += [_mechanism_row(m, by_mech[m], "UNDECLARED",
                                 "writes records but is not in DECLARED_MECHANISMS")
                  for m in undeclared]

    by_event = {k: _brier(v) | {"n_resolved": len(v)}
                for k, v in _group(kept, lambda r: r.get("observable")).items()}
    by_regime = {k: _brier(v) | {"n_resolved": len(v)}
                 for k, v in _group(kept, lambda r: (r.get("resolution_detail") or {})
                                    .get("regime") or r.get("era_tag")).items()}

    overall = _brier(kept)
    return {
        "receipt": "decision_vs_reality",
        "licence": "PRODUCT_EXPERIMENT",
        "stage": "pnl",
        "llm_spend_usd": 0.0,
        "utc": _now(),
        "as_of": as_of.isoformat(timespec="seconds"),
        "window": f"trailing_{window_hours}h",
        "pool_size": len(pool),
        "n_resolved": len(kept),
        "dropped": dropped,
        "overall": overall,
        "by_mechanism": mech_rows,
        "by_event_type": by_event,
        "by_regime": by_regime,
        "undeclared_mechanisms": undeclared,
        "worst_miss": worst_miss(kept),
        "min_n_for_a_verdict": MIN_N_FOR_A_VERDICT,
        "headline": (f"{len(kept)} record(s) resolved in the trailing "
                     f"{window_hours}h across "
                     f"{sum(1 for r in mech_rows if r['n_resolved'])} mechanism(s) "
                     f"of {len(mech_rows)} reported"),
        "read_me_first": (
            "This RE-GRADES NOTHING. Every record was already graded by its own "
            "mechanism's grader; this is the cross-mechanism roll-up of what "
            "those graders wrote, admitted through `ledger_retrieval.visible_at` "
            "so a record graded after the cut-off is not read as if it had been "
            "graded before it. Every declared mechanism has a row even at "
            "n_resolved 0 — a group that vanishes is a group nobody notices is "
            "missing. Nothing downstream branches on `worst_miss`."),
    }


def receipt_path(day: str | None = None, out: Path | None = None) -> Path:
    day = day or (os.getenv("NIGHT_RUN_DATE")
                  or datetime.now().strftime("%Y-%m-%d"))
    if out is None:
        from scripts import night_factory_jobs as J
        out = J._out()
    return Path(out) / f"decision_vs_reality_{day}.json"


def write_report(payload: dict, *, day: str | None = None,
                 out: Path | None = None) -> Path:
    p = receipt_path(day, out)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


__all__ = ["DECLARED_MECHANISMS", "MIN_N_FOR_A_VERDICT", "WINDOW_HOURS",
           "read_ledger", "receipt_path", "report", "resolved_in_window",
           "worst_miss", "write_report"]
