"""Heavy private grade worker; starts only after the native owner binds its Job."""
import json
import hashlib
import sys
from datetime import date, datetime, timedelta, timezone


def validate_marks(bars, names: set[str], session: date) -> dict:
    """Exact-session marks for every frozen held name and SPY, never forward fill."""
    import numpy as np
    import pandas as pd

    marks = bars[pd.to_datetime(bars["date"]).dt.date == session].copy()
    marks = marks[marks["symbol"].isin(names)]
    counts = marks.groupby("symbol").size().to_dict()
    bad = sorted(s for s in names if counts.get(s) != 1)
    if bad:
        return {"action": "WAIT_CONSTITUENT_MARKS", "session": session.isoformat(),
                "missing_or_duplicate": bad}
    opened = pd.to_numeric(marks["open"], errors="coerce")
    closed = pd.to_numeric(marks["close"], errors="coerce")
    valid = opened.notna() & closed.notna() & (opened > 0) & (closed > 0)
    valid &= np.isfinite(opened.astype(float)) & np.isfinite(closed.astype(float))
    if not valid.all():
        return {"action": "WAIT_CONSTITUENT_MARKS", "session": session.isoformat(),
                "invalid": sorted(marks.loc[~valid, "symbol"].astype(str).tolist())}
    return {"action": "MARKS_READY", "session": session.isoformat(), "n_symbols": len(names)}


def panel_identity(price_paths, names: set[str], bars) -> dict[str, str]:
    """Record the shared union's winning whole-series panel for every symbol."""
    import pandas as pd

    latest = []
    for path in price_paths:
        frame = pd.read_parquet(path, columns=["symbol", "date"],
                                filters=[("symbol", "in", sorted(names))])
        latest.append(frame.groupby("symbol")["date"].max().to_dict())
    out = {}
    for symbol in sorted(names):
        us, global_ = latest[0].get(symbol), latest[1].get(symbol)
        if us is None and global_ is None:
            raise ValueError(f"canonical price identity absent: {symbol}")
        use_global = global_ is not None and (us is None or global_ > us)
        selected = global_ if use_global else us
        actual = bars.loc[bars["symbol"] == symbol, "date"].max()
        if actual != selected:
            raise ValueError(f"shared union changed source identity: {symbol}")
        out[symbol] = "global_bars" if use_global else "prices_2025_26"
    return out


def snapshot_through(bars, session: date):
    import pandas as pd

    snapshot = bars[pd.to_datetime(bars["date"]).dt.date <= session].copy(deep=True)
    if snapshot.empty or pd.to_datetime(snapshot["date"]).max().date() != session:
        raise ValueError("validated session absent from bounded bar snapshot")
    return snapshot


def prior_valid_grade(daydir, session: date, books: list[dict], names: set[str]):
    """Only a complete same-session pinned receipt can suppress a new grade."""
    from scripts import local_branching as LB

    ids = sorted(b["book_id"] for b in books)
    expected_hash = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
    if len(ids) != 247 or expected_hash != LB.FROZEN_IDS_SHA256:
        raise ValueError("frozen books differ before same-session receipt lookup")
    for path in sorted(daydir.glob("grade_*.json"), reverse=True):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"malformed private grade receipt: {path.name}") from exc
        if row.get("grade_day") != session.isoformat():
            continue
        observed_ids = [b.get("book_id") for b in row.get("books", []) if isinstance(b, dict)]
        evidence = row.get("grade_evidence") or {}
        bar_sha = evidence.get("bar_inputs_sha256") or {}
        panels = evidence.get("symbol_panel_identity") or {}
        if (row.get("licence") == "PRODUCT_EXPERIMENT" and
                row.get("source_ledger_sha256") == LB.FROZEN_LEDGER_SHA256 and
                row.get("freeze_receipt_sha256") == LB.FROZEN_RECEIPT_SHA256 and
                row.get("bars_through") == session.isoformat() and
                row.get("benchmark_last_bar") == session.isoformat() and
                row.get("n_books") == 247 and row.get("n_twins") == 0 and
                len(observed_ids) == 247 and sorted(observed_ids) == ids and
                evidence.get("all_constituents_mark_session") == session.isoformat() and
                evidence.get("n_constituents_including_spy") == len(names) and
                set(panels) == names and len(bar_sha) == 2 and
                all(isinstance(v, str) and len(v) == 64 for v in bar_sha.values())):
            return path
        raise ValueError(f"same-session private grade exists but fails frozen proof: {path.name}")
    return None


def grade_once(daydir, session: date, books: list[dict], names: set[str], snapshot, evidence: dict) -> dict:
    from scripts import local_branching as LB

    existing = prior_valid_grade(daydir, session, books, names)
    if existing is not None:
        return {"action": "ALREADY_GRADED", "session": session.isoformat(),
                "grade_receipt": str(existing), "n_books": 247}
    result = LB.execute("grade", LB.FROZEN_COHORT, grade_day=session,
                        bars_override=snapshot, grade_evidence=evidence,
                        expected_session=session)
    if (result.get("n_books") != 247 or result.get("n_twins") != 0 or
            result.get("bars_through") != session.isoformat() or
            result.get("benchmark_last_bar") != session.isoformat()):
        raise ValueError("shared grader returned an unbounded private session")
    return {"action": "GRADED", "session": session.isoformat(), **result,
            "grade_evidence": evidence}


def run_original() -> dict:
    if sys.stdin.buffer.read(1) != b"G":
        raise ValueError("owned parent did not authorize child import")
    from backend.services import market_sessions as MS
    from scripts import local_branching as LB

    now = datetime.now(timezone.utc)
    cal = MS._xnys()
    sessions = cal.sessions_in_range("2026-10-14", now.date().isoformat())
    eligible = [(s.date(), cal.session_close(s).to_pydatetime()) for s in sessions
                if cal.session_close(s).to_pydatetime() <= now - timedelta(minutes=90)]
    if not eligible:
        return {"action": "WAIT_ENTRY"}
    session, close = eligible[-1]
    if session <= LB.FROZEN_COHORT:
        return {"action": "WAIT_ENTRY", "session": session.isoformat()}
    ledger = LB.OUT / LB.FROZEN_COHORT.isoformat() / "books.jsonl"
    books = LB.verified_frozen_books(ledger, ledger.parent / "freeze_receipt.json")
    names = LB.LP.book_tickers(books) | {"SPY"}
    existing = prior_valid_grade(ledger.parent, session, books, names)
    if existing is not None:
        return {"action": "ALREADY_GRADED", "session": session.isoformat(),
                "grade_receipt": str(existing), "n_books": 247}
    price_paths = (LB.SOURCE_ROOT / "prices_2025_26" / "bars.parquet",
                   LB.SOURCE_ROOT / "llm_portfolio" / "global_bars.parquet")
    if any(not p.exists() or p.stat().st_mtime <= close.timestamp() for p in price_paths):
        return {"action": "WAIT_SHARED_REFRESH", "session": session.isoformat()}
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in price_paths}
    bars = LB.cached_bars(names)
    mark_status = validate_marks(bars, names, session)
    if mark_status["action"] != "MARKS_READY":
        return mark_status
    panels = panel_identity(price_paths, names, bars)
    # The shared union selects one complete vendor series per symbol; record
    # both input snapshots so a later grade cannot silently change basis.
    input_sha = {p.name + ":" + p.parent.name: LB.digest(p) for p in price_paths}
    after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in price_paths}
    if before != after:
        return {"action": "WAIT_SHARED_REFRESH", "session": session.isoformat(),
                "reason": "price input changed while read; retry from one snapshot"}
    evidence = {"all_constituents_mark_session": session.isoformat(),
                "n_constituents_including_spy": len(names),
                "bar_inputs_sha256": input_sha,
                "symbol_panel_identity": panels,
                "basis": "shared llm_portfolio.union_bars, one source per symbol"}
    snapshot = snapshot_through(bars, session)
    return grade_once(ledger.parent, session, books, names, snapshot, evidence)


def run() -> dict:
    original = run_original()  # Existing stdin G, original247 logic/history.
    from backend.services.portfolio_intelligence.branch_population_operating import run_owned_population
    population = run_owned_population()
    return {**original, "population1000": population}


if __name__ == "__main__":
    print(json.dumps(run(), default=str), flush=True)
