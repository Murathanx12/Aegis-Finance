"""Heavy private grade worker; starts only after the native owner binds its Job."""
import json
import hashlib
import sys
from datetime import date, datetime, timedelta, timezone


# Legacy explicit fixture mappings remain available to injected callers. The
# production default loads the pinned original247 manifest, never these as fallback.
REVIEWED_US_LISTINGS = frozenset({"SPY"})
REVIEWED_FOREIGN_CALENDARS = {
    "EVO.ST": "XSTO", "SAAB-B.ST": "XSTO", "HAG.DE": "XETR",
    "RHM.DE": "XETR", "KOG.OL": "XOSL",
}
LISTING_POLICY = "original247_completed_session/2"


def listing_calendar(mic):
    """Installed calendars only; no weekday approximation or network lookup."""
    if mic == "XNYS":
        from backend.services import market_sessions as MS
        return MS._xnys()
    import exchange_calendars as xc
    return xc.get_calendar(mic)


def completed_session_targets(names, session, now, *, calendar_loader=None,
                              listing_calendars=None):
    """Read-only common-S proof for exact reviewed identities, injectable offline."""
    import pandas as pd

    loader = calendar_loader or listing_calendar
    observed = pd.Timestamp(now)
    if observed.tzinfo is None or pd.isna(observed):
        raise ValueError("completed-session observation must be timezone-qualified")
    observed = observed.tz_convert("UTC")
    policy_receipt = None
    policy_error = None
    if listing_calendars is None:
        from scripts import original247_listing_policy as OP
        try:
            policy = OP.load_policy(session=session, observed_at=observed.to_pydatetime(),
                                    calendar_loader=loader)
            identities, policy_receipt = policy["mapping"], policy["receipt"]
        except OP.PolicyError as exc:
            identities = {}
            policy_error = str(exc)
            policy_receipt = {"status": "INVALID", "reason": policy_error}
    else:
        identities = dict(listing_calendars)
    policy_sha = hashlib.sha256(json.dumps(identities, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    targets, proofs, calendars = {}, {}, {}
    for symbol in sorted(names):
        mic = identities.get(symbol)
        row = {"symbol": symbol, "listing_identity": symbol, "calendar": mic,
               "common_session": session.isoformat(), "required_session": None,
               "close_at": None, "eligible_at": None,
               "status": "POLICY_UNAVAILABLE" if policy_error else "UNKNOWN_LISTING_IDENTITY"}
        targets[symbol] = None
        if mic:
            try:
                if mic not in calendars:
                    calendars[mic] = loader(mic)
                cal = calendars[mic]
                if not cal.is_session(session.isoformat()):
                    row["status"] = "LOCAL_NON_SESSION"
                else:
                    close = pd.Timestamp(cal.session_close(session.isoformat()))
                    if pd.isna(close) or close.tzinfo is None:
                        raise ValueError("calendar close must be timezone-qualified")
                    close = close.tz_convert("UTC")
                    eligible = close + pd.Timedelta(minutes=90)
                    row.update(close_at=close.isoformat(), eligible_at=eligible.isoformat())
                    row["status"] = ("SESSION_UNCLOSED" if observed < close else
                                     "WAIT_CLOSE_LAG" if observed < eligible else "COMPLETED_COMMON_SESSION")
                    if row["status"] == "COMPLETED_COMMON_SESSION":
                        targets[symbol] = row["required_session"] = session.isoformat()
            except Exception as exc:
                # Explicit per-listing refusal, never a fallback calendar/date.
                row.update(status="CALENDAR_UNAVAILABLE", error_type=type(exc).__name__)
        proofs[symbol] = row
    return {"policy": LISTING_POLICY, "listing_calendars_sha256": policy_sha,
            "identity_authority": ("pinned original247 frozen-instrument calendar policy"
                                   if listing_calendars is None else "injected reviewed identity mapping"),
            "listing_policy_receipt": policy_receipt,
            "observed_at": observed.isoformat(), "common_session": session.isoformat(),
            "completion_lag_minutes": 90, "required_sessions": targets, "symbols": proofs}


def validate_completion_proofs(targets, reference, names, session, now):
    """Bind adapter evidence to consumer-owned identities, calendars and clock."""
    import pandas as pd

    def aware(value):
        if not isinstance(value, str):
            raise ValueError("timestamp string required")
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError("timezone-qualified timestamp required")
        return stamp.tz_convert("UTC")

    admitted = dict.fromkeys(sorted(names))
    errors = {}
    try:
        if not isinstance(targets, dict):
            raise ValueError("TARGET_PROOF_OBJECT_REQUIRED")
        for key in ("policy", "listing_calendars_sha256", "identity_authority", "common_session",
                    "listing_policy_receipt"):
            if key not in targets or targets[key] != reference[key]:
                raise ValueError(f"TARGET_HEADER_MISMATCH:{key}")
        if (type(targets.get("completion_lag_minutes")) is not int or
                targets["completion_lag_minutes"] != 90):
            raise ValueError("TARGET_HEADER_MISMATCH:completion_lag_minutes")
        if aware(targets.get("observed_at")) != pd.Timestamp(now):
            raise ValueError("TARGET_HEADER_MISMATCH:observed_at")
        for key in ("required_sessions", "symbols"):
            if not isinstance(targets.get(key), dict) or set(targets[key]) - names:
                raise ValueError(f"TARGET_IDENTITY_SET_MISMATCH:{key}")
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return admitted, dict.fromkeys(sorted(names), str(exc))

    for symbol in sorted(names):
        proof = targets["symbols"].get(symbol)
        expected = reference["symbols"][symbol]
        try:
            if (symbol not in targets["required_sessions"] or
                    targets["required_sessions"][symbol] != reference["required_sessions"][symbol]):
                raise ValueError("TARGET_SESSION_MISMATCH")
            if not isinstance(proof, dict):
                raise ValueError("TARGET_SYMBOL_PROOF_REQUIRED")
            for key in ("symbol", "listing_identity", "calendar", "common_session",
                        "required_session", "status"):
                if key not in proof or proof[key] != expected[key]:
                    raise ValueError(f"TARGET_SYMBOL_MISMATCH:{key}")
            for key in ("close_at", "eligible_at"):
                if key not in proof:
                    raise ValueError(f"TARGET_TIME_REQUIRED:{key}")
                if expected[key] is None:
                    if proof[key] is not None:
                        raise ValueError(f"TARGET_TIME_MISMATCH:{key}")
                elif aware(proof[key]) != aware(expected[key]):
                    raise ValueError(f"TARGET_TIME_MISMATCH:{key}")
            if expected["status"] == "COMPLETED_COMMON_SESSION":
                close, eligible = aware(proof["close_at"]), aware(proof["eligible_at"])
                if (eligible != close + pd.Timedelta(minutes=90) or
                        eligible > pd.Timestamp(now) or
                        proof["required_session"] != session.isoformat()):
                    raise ValueError("TARGET_COMPLETION_CLOCK_MISMATCH")
                admitted[symbol] = session.isoformat()
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            errors[symbol] = str(exc)
    return admitted, errors


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


def snapshot_through(bars, session: date, *, require_session=True):
    import pandas as pd

    dates = pd.to_datetime(bars["date"])
    if dates.isna().any():
        raise ValueError("invalid cached dates in bounded bar snapshot")
    snapshot = bars[dates.dt.date <= session].copy(deep=True)
    if require_session and (snapshot.empty or pd.to_datetime(snapshot["date"]).max().date() != session):
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


def run_original(*, now=None, calendar_loader=None, listing_calendars=None,
                 target_adapter=None) -> dict:
    if sys.stdin.buffer.read(1) != b"G":
        raise ValueError("owned parent did not authorize child import")
    from backend.services import global_prices as GP
    from scripts import local_branching as LB

    now = now if now is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("completed-session observation must be timezone-qualified")
    now = now.astimezone(timezone.utc)
    loader = calendar_loader or listing_calendar
    try:
        cal = loader("XNYS")
        sessions = cal.sessions_in_range("2026-10-14", now.date().isoformat())
        eligible = [(s.date(), cal.session_close(s).to_pydatetime()) for s in sessions
                    if cal.session_close(s).to_pydatetime() <= now - timedelta(minutes=90)]
    except Exception as exc:
        return {"action": "WAIT_CONSTITUENT_MARKS", "reason": "XNYS_CALENDAR_UNAVAILABLE",
                "observed_at": now.isoformat(), "error_type": type(exc).__name__}
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
    if listing_calendars is None:
        from scripts import original247_listing_policy as OP
        try:
            OP.load_policy(session=session, observed_at=now, calendar_loader=loader,
                           exact_symbols=names)
        except OP.PolicyError as exc:
            return {"action": "WAIT_CONSTITUENT_MARKS", "session": session.isoformat(),
                    "reason": str(exc), "listing_policy_status": "INVALID"}
    price_paths = (LB.SOURCE_ROOT / "prices_2025_26" / "bars.parquet",
                   LB.SOURCE_ROOT / "llm_portfolio" / "global_bars.parquet")
    if any(not p.exists() or p.stat().st_mtime <= close.timestamp() for p in price_paths):
        return {"action": "WAIT_SHARED_REFRESH", "session": session.isoformat()}
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in price_paths}
    bars = LB.cached_bars(names)
    # Build the consumer's reference before invoking a custom adapter. The
    # adapter's own claimed mapping/hash/completion label is not authority.
    mapping = None if listing_calendars is None else dict(listing_calendars)
    reference = completed_session_targets(names, session, now, calendar_loader=loader,
                                          listing_calendars=mapping)
    targets = (reference if target_adapter is None else
               target_adapter(set(names), session, now, calendar_loader=loader,
                              listing_calendars=None if mapping is None else dict(mapping)))
    reviewed_targets, proof_errors = validate_completion_proofs(targets, reference, names, session, now)
    supplied = targets.get("required_sessions", {}) if isinstance(targets, dict) else {}
    proofs = targets.get("symbols", {}) if isinstance(targets, dict) else {}
    supplied = supplied if isinstance(supplied, dict) else {}
    proofs = {s: p for s, p in proofs.items() if isinstance(p, dict)} if isinstance(proofs, dict) else {}
    provenance = {"completed_session_targets": targets,
                  "completion_proof_validation": {
                      "status": "INVALID" if proof_errors else "VALID", "errors": proof_errors}}
    try:
        if not {"symbol", "date", "open", "close"} <= set(bars.columns):
            raise ValueError("PRICE_DIAGNOSTIC_COLUMNS_REQUIRED")
        snapshot = snapshot_through(bars, session, require_session=False)
        freshness = GP.freshness_diagnostic(snapshot, names, required_session=reviewed_targets)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"action": "WAIT_CONSTITUENT_MARKS", "session": session.isoformat(),
                "reason": "INVALID_PRICE_SNAPSHOT", "error_type": type(exc).__name__,
                "detail": str(exc), "reasons": {
                    s: {"freshness": "INVALID_PRICE_SNAPSHOT",
                        "target": proofs.get(s, {}).get("status", "MISSING_TARGET_PROOF")}
                    for s in sorted(names)}, **provenance}
    provenance["freshness_diagnostic"] = freshness
    mark_status = validate_marks(snapshot, names, session)
    if (freshness["status"] != "COMPLETE_TARGET_COVERAGE" or
            mark_status["action"] != "MARKS_READY"):
        reasons = {}
        for row in freshness["symbols"]:
            s = row["symbol"]
            if row["status"] != "FRESH_AT_REQUIRED_SESSION":
                proof = proofs.get(s, {})
                reasons[s] = {"freshness": row["status"],
                              "target": proof.get("status", "MISSING_TARGET_PROOF")}
                if s in proof_errors:
                    reasons[s]["proof_validation"] = proof_errors[s]
                if supplied.get(s) not in (None, session.isoformat()):
                    reasons[s]["target"] = "DIFFERENT_COMMON_SESSION"
        return {**mark_status, "action": "WAIT_CONSTITUENT_MARKS",
                "reasons": reasons, **provenance}
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
                "basis": "shared llm_portfolio.union_bars, one source per symbol",
                **provenance}
    return grade_once(ledger.parent, session, books, names, snapshot, evidence)


def run() -> dict:
    original = run_original()  # Existing stdin G, original247 logic/history.
    from backend.services.portfolio_intelligence.branch_population_operating import run_owned_population
    population = run_owned_population()
    return {**original, "population1000": population}


if __name__ == "__main__":
    print(json.dumps(run(), default=str), flush=True)
