"""THE NIGHTLY NN LAB — E1, then E4, then E5, and one question they cannot answer.

Chunk 14, spec `docs/research_notes/2026-09-13/spec_always_on_lab.md` section 3.5.
Murat, 2026-09-13: "run backtest for NN, do a learning lab for it to
continuously learn."

WHAT "CONTINUOUSLY LEARN" MEANS HERE, SAID ONCE SO IT CANNOT DRIFT
==================================================================
Every night the queue is idle, three existing jobs run IN ORDER and are not
rebuilt:

1. `E1_event_head` — refit the typed-event tabular head on the CURRENT typed
   table. That table grows as L2 produces rows; today it is still the keyword
   proxy, and the receipt's `event_source` field says so every night, unprompted.
2. `E4_adwin_gated_refit` — ADWIN-gated refitting against fixed monthly
   refitting, on IDENTICAL test dates.
3. `E5_stopping_rules` — DSR and PBO over the accumulated evaluation log. A
   no-op with a STATED reason when no search ran that night, never a silent skip.

THE ONE NEW THING: `beat_last_night`
====================================
Tonight's head's IC on a FIXED held-out month, against LAST NIGHT'S head on the
SAME month. The month is the most recent FULLY-CLOSED calendar month, and it is
fixed for the comparison on purpose: re-evaluating last night's head on a NEW
month would confound "did the head improve" with "did the month get easier",
and the answer would look like learning either way.

`n_nights_compared < 2` -> `beat_last_night: null`. Not False, not True:
there is nothing to compare against yet, and saying so is the answer.

WHAT THE NIGHTLY REFIT MAY NEVER DO
===================================
* **No training on future information.** The held-out month is CLOSED before
  the refit that grades against it starts, and the embargo/PIT machinery is
  `learner/event_head.py`'s own — this module calls those jobs, it does not get
  a parallel, easier-to-violate copy of them.
* **No target leakage.** Same allowlist discipline as everywhere else; this
  module adds no feature and touches no column.
* **It never touches a live book's frozen `Strategy`.** A nightly refit changes
  the RESEARCH head. A mutation is a NEW book, never an edit to one already
  accruing forward evidence — the PRODUCT_EXPERIMENT / CAPITAL_CANDIDATE
  boundary, restated for this loop so "continuously learn" cannot be read as
  licence to make a live book's construction a moving target.
* **DEPRIORITIZED, never deleted.** E5's own verdict vocabulary, unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger("lab_nn")

#: The nightly sequence, in order, as `night_factory_jobs.JOBS` ids with a
#: minute box each. Declared here and walked; a job that raises still leaves a
#: row, because half a night is still a night.
SEQUENCE: tuple[tuple[str, int], ...] = (
    ("E1_event_head", 60),
    ("E4_adwin_gated_refit", 45),
    ("E5_stopping_rules", 20),
)

#: Nights of history needed before `beat_last_night` can be anything but null.
MIN_NIGHTS_TO_COMPARE = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def history_path() -> Path:
    """Cumulative, one line per head per night. NOT in the per-date night folder:
    "last night" has to be readable without knowing which date last night was."""
    return Path(_config.DATA_DIR) / "optimus" / "nn_lab_history.jsonl"


def receipt_path(day: str) -> Path:
    from scripts import night_factory_jobs as J
    return J._out() / f"NN_lab_{day}.json"


def held_out_month(today: date | None = None) -> str:
    """The most recent FULLY-CLOSED calendar month, as `YYYY-MM`.

    Fixed, never a moving window. "Did tonight beat last night" is only a
    question about the head if both heads answered the SAME question; a rolling
    window makes the month a second moving part and the comparison
    uninterpretable. Derived from `today`, never written as a literal.
    """
    today = today or date.today()
    first_of_this = today.replace(day=1)
    last_closed = first_of_this.replace(year=first_of_this.year - 1, month=12) \
        if first_of_this.month == 1 else first_of_this.replace(month=first_of_this.month - 1)
    return f"{last_closed.year:04d}-{last_closed.month:02d}"


def held_out_ic(daily_csv: Path | str, month: str) -> dict:
    """Mean IC per head over the held-out month, from E1's own daily table.

    Read from the per-date CSV the job already writes rather than recomputed:
    a second implementation of "the IC" is a second answer, and the receipt
    shows the job's.

    Returns `{}` when the month is absent from the table — which is a real and
    common state early on, and is reported as such rather than as zero.
    """
    import pandas as pd

    p = Path(daily_csv)
    if not p.exists():
        return {"heads": {}, "status": "DAILY_TABLE_ABSENT", "path": str(p)}
    dd = pd.read_csv(p)
    if "date" not in dd.columns:
        return {"heads": {}, "status": "DAILY_TABLE_HAS_NO_DATE_COLUMN", "path": str(p)}
    dd["date"] = pd.to_datetime(dd["date"], errors="coerce")
    sl = dd[dd["date"].dt.strftime("%Y-%m") == month]
    if sl.empty:
        return {"heads": {}, "status": "MONTH_NOT_IN_TABLE", "month": month,
                "n_dates_in_table": int(len(dd)), "path": str(p)}
    heads = {}
    for col in sl.columns:
        if not col.startswith("ic_"):
            continue
        series = sl[col].astype(float)
        vals = series[series.notna()]
        if vals.empty:
            continue
        heads[col[3:]] = {"ic": round(float(vals.mean()), 6),
                          "n_date_blocks": int(len(vals))}
    return {"heads": heads, "status": "ok", "month": month,
            "n_dates": int(len(sl)), "path": str(p)}


def read_history(path: Path | None = None) -> list[dict]:
    p = path or history_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def append_history(rows: list[dict], path: Path | None = None) -> Path:
    p = path or history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    return p


def compare_to_last_night(head: str, ic_tonight: float, month: str, *,
                          history: list[dict] | None = None,
                          today: str | None = None) -> dict:
    """Tonight vs the previous night, on the SAME head and the SAME month.

    `beat_last_night` is null with fewer than two nights: nothing to compare
    against yet is a state, not a False.
    """
    history = read_history() if history is None else history
    same = [h for h in history
            if h.get("head") == head and h.get("held_out_month") == month
            and h.get("date") != today]
    same.sort(key=lambda h: str(h.get("date") or ""))
    n = len(same) + 1
    if n < MIN_NIGHTS_TO_COMPARE:
        return {"head": head, "held_out_month": month,
                "ic_tonight": round(float(ic_tonight), 6), "ic_last_night": None,
                "beat_last_night": None, "n_nights_compared": n,
                "why": (f"{n} night(s) of history on this head and month; "
                        f"{MIN_NIGHTS_TO_COMPARE} are needed. Null, not False — "
                        f"nothing to compare against yet is a state.")}
    last = float(same[-1]["ic"])
    return {"head": head, "held_out_month": month,
            "ic_tonight": round(float(ic_tonight), 6),
            "ic_last_night": round(last, 6),
            "beat_last_night": bool(float(ic_tonight) > last),
            "delta": round(float(ic_tonight) - last, 6),
            "n_nights_compared": n,
            "last_night_date": same[-1].get("date")}


def run_job(job: str, minutes: int) -> dict:
    """One sequence job, through the SAME registry the night factory dispatches."""
    from scripts.night_factory_jobs import JOBS
    if job not in JOBS:
        return {"job": job, "status": "refused",
                "why": f"{job!r} is not in night_factory_jobs.JOBS"}
    t0 = time.time()
    try:
        payload = JOBS[job]()
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("nn lab job %s raised", job)
        return {"job": job, "status": "error", "box_minutes": minutes,
                "detail": f"{type(exc).__name__}: {exc}"[:400],
                "seconds": round(time.time() - t0, 1)}
    return {"job": job, "status": payload.get("status") or "done",
            "box_minutes": minutes, "verdict": payload.get("verdict"),
            "headline": payload.get("headline"),
            "event_source": payload.get("event_source"),
            "daily_csv": payload.get("daily_csv"),
            "seconds": round(time.time() - t0, 1)}


def run_nn_lab(*, today: date | None = None, sequence=None, runner=None,
               history_file: Path | None = None) -> dict:
    """The whole nightly sequence plus the `beat_last_night` comparison.

    Never raises for a job's sake: a job that failed leaves a row, because half
    a night is still a night and the operator needs the receipt more than the
    traceback.
    """
    today = today or date.today()
    day = today.isoformat()
    month = held_out_month(today)
    runner = runner or run_job
    rows = [runner(job, minutes) for job, minutes in (sequence or SEQUENCE)]

    e1 = next((r for r in rows if r["job"] == "E1_event_head"), None)
    ic_block: dict = {"heads": {}, "status": "E1_DID_NOT_RUN"}
    if e1 and e1.get("daily_csv"):
        ic_block = held_out_ic(e1["daily_csv"], month)

    history = read_history(history_file)
    comparisons = []
    new_rows = []
    for head, cell in sorted((ic_block.get("heads") or {}).items()):
        comparisons.append(compare_to_last_night(head, cell["ic"], month,
                                                 history=history, today=day))
        new_rows.append({"date": day, "head": head, "held_out_month": month,
                         "ic": cell["ic"], "n_date_blocks": cell["n_date_blocks"],
                         "written_utc": _now()})
    if new_rows:
        append_history(new_rows, history_file)

    beat = [c for c in comparisons if c["beat_last_night"] is True]
    undecided = [c for c in comparisons if c["beat_last_night"] is None]
    payload = {
        "receipt": "NN_lab",
        "licence": "PRODUCT_EXPERIMENT", "stage": "features",
        "llm_spend_usd": 0.0,
        "utc": _now(), "date": day,
        "held_out_month": month,
        "held_out_month_rule": (
            "the most recent FULLY-CLOSED calendar month, derived from today and "
            "FIXED for the comparison: re-evaluating last night's head on a new "
            "month would confound 'did the head improve' with 'did the month get "
            "easier', and the answer would look like learning either way"),
        "sequence": rows,
        "held_out_ic": ic_block,
        "comparisons": comparisons,
        "n_heads": len(comparisons),
        "n_beat_last_night": len(beat),
        "n_undecided": len(undecided),
        "event_source": (e1 or {}).get("event_source"),
        "history_path": str(history_file or history_path()),
        "refusals": [f"{r['job']}: {r.get('detail') or r.get('why')}"
                     for r in rows if r["status"] in ("error", "refused")],
        "never": [
            "no training on future information: the held-out month is CLOSED "
            "before the refit that grades against it starts, and the embargo is "
            "the head's own, not a copy",
            "no target leakage: this module adds no feature and touches no column",
            "no live book's frozen Strategy is changed: a mutation is a NEW book",
            "DEPRIORITIZED, never deleted, never re-promoted on the same regime",
        ],
        "headline": (
            f"{len(comparisons)} head(s) on held-out {month}; "
            f"{len(beat)} beat last night, {len(undecided)} undecided "
            f"(fewer than {MIN_NIGHTS_TO_COMPARE} nights of history); "
            f"{sum(1 for r in rows if r['status'] in ('error', 'refused'))} "
            f"job(s) did not complete"),
    }
    return payload


def write_receipt(payload: dict, *, day: str | None = None,
                  out: Path | None = None) -> Path:
    day = day or payload.get("date") or date.today().isoformat()
    p = Path(out) / f"NN_lab_{day}.json" if out is not None else receipt_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


__all__ = ["MIN_NIGHTS_TO_COMPARE", "SEQUENCE", "append_history",
           "compare_to_last_night", "held_out_ic", "held_out_month",
           "history_path", "read_history", "receipt_path", "run_job",
           "run_nn_lab", "write_receipt"]
