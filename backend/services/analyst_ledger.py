"""The analyst snapshot ledger — our own point-in-time target history.

BUILD-1 shipped a scoring term called `rating_drift_3m` and the write-up called
it a revision signal. It is not. It is the change in Yahoo's four-row
recommendation-count table, which counts ratings, not targets. **ΔTarget over
7 / 30 / 90 days did not exist**, because the only source we hold returns the
consensus target as a single current number with no history and no timestamp.

Buying that history is one answer. Starting it is another, and it costs
nothing: every time the engine looks at a name, append what it saw. After a
week there is a 7-day delta; after a quarter there is a 90-day delta; and every
one of them is genuinely point-in-time, because it was written the day it was
observed rather than reconstructed afterwards from today's state.

Two rules this module exists to enforce:

1. **Append only.** A row is never edited. A correction is a new row.
2. **Missing is MISSING.** If the ledger has not seen this ticker twice, the
   delta fields come back `None` with a reason. They are never zero, and they
   are never inferred from the current value. `delta_target_30d = 0.0` and
   "we have no idea" are different facts and the engine must not confuse them.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

LEDGER = Path(__file__).resolve().parents[1] / "data" / "analyst_snapshots.jsonl"

#: The columns of one observation. Frozen — a reader three months from now must
#: be able to parse rows written today.
SNAPSHOT_FIELDS = (
    "ticker", "observed_at", "source", "current_price", "target_low",
    "target_mean", "target_median", "target_high", "n_analysts",
    "consensus_rating", "consensus_label", "recommendation_counts",
    "raw_payload_hash", "retrieval_status",
)

#: Rows the reader could not parse, per file. A corrupt ledger must not read
#: back as a merely smaller one (silent-fragility audit, BUILD-1.1).
MALFORMED_ROWS: dict[str, int] = {}

#: A snapshot older than this is not used to anchor a delta — a "30-day" change
#: measured against a 200-day-old row is not a 30-day change.
WINDOW_TOLERANCE_DAYS = {7: 5, 30: 12, 90: 30}


def payload_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _ledger_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else LEDGER


def snapshot(ticker: str, state: dict, *, source: str = "yahoo",
             path: Path | str | None = None,
             retrieval_status: str = "ok") -> dict:
    """Append one observation of a ticker's analyst state. Returns the row."""
    row = {
        "ticker": ticker.upper(),
        "observed_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "current_price": state.get("price"),
        "target_low": state.get("target_low"),
        "target_mean": state.get("target_mean"),
        "target_median": state.get("target_median"),
        "target_high": state.get("target_high"),
        "n_analysts": state.get("n_analysts"),
        "consensus_rating": state.get("consensus_score"),
        "consensus_label": state.get("consensus_label"),
        "recommendation_counts": state.get("recommendation_counts"),
        "raw_payload_hash": payload_hash({
            k: state.get(k) for k in
            ("price", "target_low", "target_mean", "target_median",
             "target_high", "n_analysts", "consensus_score")}),
        "retrieval_status": retrieval_status,
    }
    p = _ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def snapshot_if_new(ticker: str, state: dict, *, source: str = "yahoo",
                    path: Path | str | None = None,
                    min_hours: float = 20.0) -> Optional[dict]:
    """Append at most one observation per ticker per (roughly) day.

    The brief runs many times a day; the ledger wants a daily series, not a
    log of every page refresh. Returns the row written, or None if today's
    observation already exists.
    """
    if state.get("target_median") is None and state.get("price") is None:
        return None
    existing = read(ticker, path=path)
    if existing:
        last = _as_datetime(existing[-1].get("observed_at"))
        if last is not None:
            age_h = (datetime.now() - last).total_seconds() / 3600.0
            if age_h < min_hours:
                return None
    return snapshot(ticker, state, source=source, path=path)


def _as_datetime(s: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s)[:19])
    except (TypeError, ValueError):
        return None


def read(ticker: Optional[str] = None, *,
         path: Path | str | None = None) -> list[dict]:
    p = _ledger_path(path)
    if not p.exists():
        return []
    want = ticker.upper() if ticker else None
    out, malformed = [], 0
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            # a dropped row is a hole in the history — count it, never let it
            # vanish into a smaller-looking but healthy-looking ledger
            malformed += 1
            continue
        if want is None or row.get("ticker") == want:
            out.append(row)
    if malformed:
        logger.warning("analyst ledger %s: %d malformed row(s) skipped",
                       p.name, malformed)
        MALFORMED_ROWS[str(p)] = malformed
    else:
        MALFORMED_ROWS.pop(str(p), None)
    out.sort(key=lambda r: str(r.get("observed_at")))
    return out


def _as_date(s: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(s)[:19]).date()
    except (TypeError, ValueError):
        return None


def _anchor(rows: list[dict], days: int, today: date) -> Optional[dict]:
    """The row closest to `days` ago, if one exists inside the tolerance."""
    want = today - timedelta(days=days)
    tol = WINDOW_TOLERANCE_DAYS.get(days, max(3, days // 3))
    best, best_gap = None, None
    for r in rows:
        d = _as_date(r.get("observed_at"))
        if d is None or r.get("target_median") is None:
            continue
        gap = abs((d - want).days)
        if gap <= tol and (best_gap is None or gap < best_gap):
            best, best_gap = r, gap
    return best


def target_revisions(ticker: str, *, path: Path | str | None = None,
                     today: Optional[date] = None,
                     rows: Optional[Iterable[dict]] = None) -> dict:
    """Real ΔTarget over 7 / 30 / 90 days, or an explicit MISSING.

    A delta is only produced when the ledger holds an observation near BOTH
    ends of the window. Anything else returns `None` and a reason. There is no
    path through this function that manufactures a revision out of one
    observation.
    """
    hist = list(rows) if rows is not None else read(ticker, path=path)
    today = today or date.today()
    out: dict[str, Any] = {
        "ticker": ticker.upper(),
        "observations": len(hist),
        "history_available": len(hist) >= 2,
        "first_observed": hist[0].get("observed_at") if hist else None,
        "last_observed": hist[-1].get("observed_at") if hist else None,
        "source": "aegis analyst snapshot ledger (own PIT history)",
    }
    latest = next((r for r in reversed(hist)
                   if r.get("target_median") is not None), None)
    for d in (7, 30, 90):
        key = f"delta_target_{d}d"
        if latest is None:
            out[key] = None
            out[key + "_status"] = "MISSING: no snapshot carries a target"
            continue
        anchor = _anchor(hist[:-1] or [], d, today) if len(hist) > 1 else None
        if anchor is None:
            out[key] = None
            out[key + "_status"] = (
                f"MISSING: no snapshot within "
                f"{WINDOW_TOLERANCE_DAYS.get(d)}d of {d} days ago — the ledger "
                f"has {len(hist)} observation(s); history accrues from first use")
            continue
        then = float(anchor["target_median"])
        now = float(latest["target_median"])
        out[key] = round(now / then - 1.0, 4) if then else None
        out[key + "_status"] = "ok"
        out[key + "_anchor"] = anchor.get("observed_at")
    # breadth / dispersion change over the longest window we can actually anchor
    ref = None
    for d in (90, 30, 7):
        ref = _anchor(hist[:-1] or [], d, today) if len(hist) > 1 else None
        if ref is not None:
            out["change_window_days"] = d
            break
    if ref is not None and latest is not None:
        a, b = ref.get("n_analysts"), latest.get("n_analysts")
        out["breadth_change"] = (int(b) - int(a)) if (a is not None and b is not None) else None
        da, db = _dispersion(ref), _dispersion(latest)
        out["dispersion_change"] = (round(db - da, 4)
                                    if (da is not None and db is not None) else None)
    else:
        out["breadth_change"] = None
        out["dispersion_change"] = None
    return out


def _dispersion(row: dict) -> Optional[float]:
    lo, hi, mid = row.get("target_low"), row.get("target_high"), row.get("target_median")
    if lo is None or hi is None or not mid:
        return None
    try:
        return (float(hi) - float(lo)) / float(mid)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def coverage(path: Path | str | None = None) -> dict:
    """What the ledger holds, so the brief can say how old our history is."""
    rows = read(path=path)
    by: dict[str, int] = {}
    for r in rows:
        by[r.get("ticker", "?")] = by.get(r.get("ticker", "?"), 0) + 1
    days = sorted({str(r.get("observed_at"))[:10] for r in rows})
    return {
        "rows": len(rows),
        "malformed_rows": MALFORMED_ROWS.get(str(_ledger_path(path)), 0),
        "tickers": len(by),
        "distinct_days": len(days),
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "revisions_possible": len(days) >= 2,
        "note": ("target-revision fields stay MISSING until this ledger holds "
                 "two observations of the same ticker spanning the window"),
    }
