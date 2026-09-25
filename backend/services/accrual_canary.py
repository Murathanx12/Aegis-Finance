"""Receipts that can go red: is anything still ACCRUING?

WHY THIS EXISTS (chunk C0, 2026-09-25)
======================================
Every health row in this repo used to answer "is the file there?" and none
answered "is the file still growing?". The forecast ledger went quiet from
2026-09-11 to 2026-09-24 -- zero new rows from the only arm with skill -- and
`/api/health/full` stayed green because the ledger existed and was readable.
The same shape three more times:

* an OpenClaw quest returned an EMPTY log on 2026-09-24 and nothing counted it;
* two sim sessions crashed on 09-22/23 and `sessions.jsonl` only learned about
  a session when it FINISHED, so a crash left no row at all;
* `roi_ranking.n_considered` printed `2` for six weeks beside a funnel that
  held 40, and nothing compared the two numbers.

So each function here returns a status that can be `DEGRADED` and a reason
that names the number, and an input that cannot be dated is `UNKNOWN`, never
`ok`. A health row that prints a date and cannot go red is decoration.

Cheap by construction: the ledger is ~27 MB and read on every health call, so
only its TAIL is parsed (`TAIL_BYTES`). Rows are appended in time order, so the
tail holds the newest ones; a tail with no parseable stamp is UNKNOWN.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: How much of a JSONL ledger's end is read. ~8 MB is ~7k forecast rows.
TAIL_BYTES = 8 * 1024 * 1024

#: The registered collectors and the PIT-store key prefix each writes under.
COLLECTOR_PREFIXES: dict[str, str] = {
    "congress": "congress:",
    "ark": "ark:",
    "13f": "13f:",
    "insider_cmp": "insider_cmp:",
    "revisions": "revisions_score:",
    "pead": "pead_score:",
    "quality": "quality_score:",
    "multifactor": "multifactor_score:",
    "smartgrowth": "smartgrowth_pick:",
}


def _tail_lines(path: Path, tail_bytes: int = TAIL_BYTES) -> list[str]:
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - tail_bytes))
        blob = fh.read()
    lines = blob.decode("utf-8", errors="replace").splitlines()
    if size > tail_bytes and lines:
        lines = lines[1:]                  # the first line is probably torn
    return lines


def _parse_day(v: Any) -> date | None:
    if not v:
        return None
    try:
        ts = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc)
    return ts.date()


# ─────────────────────────────── forecast accrual ────────────────────────────

def forecast_accrual(ledger_path: Path, *, today: date,
                     window_days: int = 3,
                     tail_bytes: int = TAIL_BYTES) -> dict:
    """Did the forecast ledger gain rows in the last `window_days` UTC days?

    `ok` needs at least one row whose `made_at` falls in the window.
    `DEGRADED` is a readable ledger with none. `UNKNOWN` is a ledger that is
    absent or carries no parseable `made_at` -- an undateable ledger is not a
    fresh one.
    """
    ledger_path = Path(ledger_path)
    base = {"check": "forecast_accrual", "path": str(ledger_path),
            "window_days": window_days, "rows_by_day": {},
            "last_new_row_utc": None}
    if not ledger_path.exists():
        return {**base, "status": "UNKNOWN",
                "reason": f"no forecast ledger at {ledger_path}"}
    try:
        lines = _tail_lines(ledger_path, tail_bytes)
    except OSError as exc:
        return {**base, "status": "UNKNOWN", "reason": f"unreadable: {exc}"}

    start = today - timedelta(days=window_days)
    by_day: dict[str, int] = {}
    last: str | None = None
    n_dated = 0
    for ln in lines:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        stamp = row.get("made_at")
        d = _parse_day(stamp)
        if d is None:
            continue
        n_dated += 1
        if last is None or str(stamp) > last:
            last = str(stamp)
        if start < d <= today:
            by_day[d.isoformat()] = by_day.get(d.isoformat(), 0) + 1

    base.update(rows_by_day=dict(sorted(by_day.items())), last_new_row_utc=last)
    if n_dated == 0:
        return {**base, "status": "UNKNOWN",
                "reason": ("no row in the ledger's tail carries a parseable "
                           "`made_at`; its age CANNOT BE DETERMINED")}
    n = sum(by_day.values())
    if n == 0:
        return {**base, "status": "DEGRADED",
                "reason": (f"0 new rows in the last {window_days} day(s) "
                           f"(newest made_at {last}); forecasts have stopped "
                           f"accruing")}
    return {**base, "status": "ok",
            "reason": f"{n} new row(s) in the last {window_days} day(s)"}


# ─────────────────────────────── collector liveness ─────────────────────────

def collector_liveness(db_path: Path, *, today: date,
                       window_days: int = 7) -> list[dict]:
    """One row per registered collector: rows written in the last week.

    Read-only (`mode=ro`), so a health call can never create or lock the DB.
    A collector with no row in the window is `DEGRADED`; one that has NEVER
    written is `DEGRADED` too, and says so -- `congress` writing zero rows for
    months was invisible precisely because nothing enumerated the plan.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return [{"collector": k, "status": "UNKNOWN", "n_rows_7d": None,
                 "last_row_date": None, "reason": f"no PIT store at {db_path}"}
                for k in COLLECTOR_PREFIXES]
    since = (today - timedelta(days=window_days)).isoformat()
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return [{"collector": k, "status": "UNKNOWN", "n_rows_7d": None,
                 "last_row_date": None, "reason": f"unopenable: {exc}"}
                for k in COLLECTOR_PREFIXES]
    try:
        for name, prefix in COLLECTOR_PREFIXES.items():
            try:
                n7, last = con.execute(
                    "SELECT SUM(CASE WHEN observed_at >= ? THEN 1 ELSE 0 END), "
                    "MAX(observed_at) FROM pit_observations WHERE key LIKE ?",
                    (since, prefix + "%")).fetchone()
            except sqlite3.Error as exc:
                out.append({"collector": name, "status": "UNKNOWN",
                            "n_rows_7d": None, "last_row_date": None,
                            "reason": f"query failed: {exc}"})
                continue
            n7 = int(n7 or 0)
            row = {"collector": name, "prefix": prefix, "n_rows_7d": n7,
                   "last_row_date": (str(last)[:10] if last else None)}
            if last is None:
                row.update(status="DEGRADED", reason="has NEVER written a row")
            elif n7 == 0:
                row.update(status="DEGRADED",
                           reason=f"0 rows in {window_days}d; last {str(last)[:10]}")
            else:
                row.update(status="ok", reason=f"{n7} rows in {window_days}d")
            out.append(row)
    finally:
        con.close()
    return out


# ─────────────────────────────── stuck counters ─────────────────────────────

def stuck_counter(values: Iterable[int], *, min_run: int = 5) -> bool:
    """True when the same integer repeats CONSECUTIVELY at least `min_run` times.

    A count that never moves is the signature of a static input -- the
    `n_considered: 2` that sat beside a 40-name funnel for six weeks.
    """
    run, prev = 0, object()
    for v in values:
        if v is None:
            run, prev = 0, object()
            continue
        run = run + 1 if v == prev else 1
        prev = v
        if run >= min_run:
            return True
    return False


def n_considered_row(decisions_dir: Path, funnel_path: Path | None = None, *,
                     last: int = 6, min_run: int = 5) -> dict:
    """The decision contract's `n_considered` over the last `last` days,
    printed on ONE line beside the funnel's `n_candidates`.

    The two numbers disagreeing is the finding; either alone looked healthy.
    """
    decisions_dir = Path(decisions_dir)
    files = sorted(p for p in decisions_dir.glob("20??-??-??.json"))[-last:]
    vals: list[int | None] = []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            v = (d.get("roi_ranking") or {}).get("n_considered")
            vals.append(int(v) if v is not None else None)
        except (OSError, ValueError, TypeError):
            vals.append(None)
    n_cand = None
    if funnel_path is not None:
        try:
            fp = json.loads(Path(funnel_path).read_text(encoding="utf-8"))
            n_cand = len(fp.get("candidates") or [])
        except (OSError, ValueError):
            n_cand = None
    days = [p.stem for p in files]
    line = (f"n_considered {vals} over {days[0] if days else '-'}.."
            f"{days[-1] if days else '-'} | funnel n_candidates {n_cand}")
    row = {"check": "n_considered", "values": vals, "days": days,
           "funnel_n_candidates": n_cand, "line": line}
    if not [v for v in vals if v is not None]:
        return {**row, "status": "UNKNOWN",
                "reason": "no decision contract carries roi_ranking.n_considered"}
    if stuck_counter(vals, min_run=min_run):
        return {**row, "status": "DEGRADED",
                "reason": (f"n_considered has not moved for >= {min_run} "
                           f"contracts -- a static candidate input. {line}")}
    return {**row, "status": "ok", "reason": line}


# ─────────────────────────────── openclaw telemetry ─────────────────────────

def openclaw_telemetry(ledger_base: Path | None = None, *, today: date,
                       window_days: int = 3,
                       tail_bytes: int = TAIL_BYTES) -> dict:
    """OpenClaw calls in the telemetry ledger, and whether any came back EMPTY.

    `DEGRADED` when a call in the window has `meta.status == "EMPTY_LOG"` (or
    any non-OK status); `IDLE` when there were no OpenClaw calls at all -- not
    red, because not browsing is a legitimate night; `ok` otherwise.
    """
    try:
        from backend.services import llm_telemetry as LT
        base = Path(ledger_base) if ledger_base is not None else LT.LLM_CALLS
        files = LT.ledger_files(base)
    except Exception as exc:                                       # noqa: BLE001
        return {"check": "openclaw_telemetry", "status": "UNKNOWN",
                "reason": f"telemetry unreadable: {exc}"}
    start = today - timedelta(days=window_days)
    n, bad, cost = 0, {}, 0.0
    for f in files[-2:]:                   # this month and the previous one
        try:
            lines = _tail_lines(f, tail_bytes)
        except OSError:
            continue
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            meta = r.get("meta") or {}
            if meta.get("via") != "openclaw" and not str(
                    r.get("purpose") or "").startswith("openclaw:"):
                continue
            d = _parse_day(r.get("ts"))
            if d is None or not (start < d <= today):
                continue
            n += 1
            cost += float(r.get("cost_usd") or 0.0)
            st = meta.get("status") or "OK"
            if st != "OK":
                bad[st] = bad.get(st, 0) + 1
    row = {"check": "openclaw_telemetry", "window_days": window_days,
           "n_calls": n, "not_ok": bad, "cost_usd": round(cost, 4)}
    if n == 0:
        return {**row, "status": "IDLE",
                "reason": f"no OpenClaw call in {window_days}d"}
    if bad:
        return {**row, "status": "DEGRADED",
                "reason": f"{sum(bad.values())} of {n} OpenClaw call(s) not OK: {bad}"}
    return {**row, "status": "ok", "reason": f"{n} OpenClaw call(s), all OK"}


# ─────────────────────────────── the health row ─────────────────────────────

def health(*, today: date | None = None) -> dict:
    """The composite row for `/api/health/full`. Never raises."""
    from backend import config as C
    today = today or datetime.now(timezone.utc).date()
    rows: dict[str, Any] = {}
    try:
        rows["forecast_accrual"] = forecast_accrual(
            Path(C.OPTIMUS_LEDGER_DIR) / "predictions.jsonl", today=today)
    except Exception as exc:                                       # noqa: BLE001
        rows["forecast_accrual"] = {"status": "UNKNOWN", "reason": str(exc)[:200]}
    try:
        from backend import db as _db
        rows["collectors"] = collector_liveness(_db.DB_PATH, today=today)
    except Exception as exc:                                       # noqa: BLE001
        rows["collectors"] = [{"status": "UNKNOWN", "reason": str(exc)[:200]}]
    try:
        rows["openclaw"] = openclaw_telemetry(today=today)
    except Exception as exc:                                       # noqa: BLE001
        rows["openclaw"] = {"status": "UNKNOWN", "reason": str(exc)[:200]}
    try:
        rows["n_considered"] = n_considered_row(
            Path(C.OPTIMUS_LEDGER_DIR) / "decisions",
            getattr(C, "IC_FUNNEL_PATH", None))
    except Exception as exc:                                       # noqa: BLE001
        rows["n_considered"] = {"status": "UNKNOWN", "reason": str(exc)[:200]}

    reasons = []
    for k in ("forecast_accrual", "openclaw", "n_considered"):
        if rows[k].get("status") in ("DEGRADED", "UNKNOWN"):
            reasons.append(f"{k}: {rows[k].get('reason')}")
    for c in rows["collectors"]:
        if c.get("status") in ("DEGRADED", "UNKNOWN"):
            reasons.append(f"collector {c.get('collector')}: {c.get('reason')}")
    return {"status": "ok" if not reasons else "DEGRADED",
            "degraded_reasons": reasons, **rows}
