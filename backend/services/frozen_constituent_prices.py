"""Refresh the five inherited original247 European inputs, never grade them.

The scheduled US SIP refresh cannot supply these listings. Use the EXISTING
global_prices cache lock, daily-attempt markers and append-only writer. The
exact listing/calendar crosswalk is inherited from the reviewed frozen policy;
it is not a new listing-status, FX, price-basis or investment-policy assertion.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd

CALENDARS = {"EVO.ST": "XSTO", "HAG.DE": "XETR", "KOG.OL": "XOSL",
             "RHM.DE": "XETR", "SAAB-B.ST": "XSTO"}
POLICY_SHA256 = "7e5003eb267eb05acf461aec5c5ac6877b1da3f1d2d322d8c9c13ee48c21e696"
FROZEN_DATE = date(2026, 10, 14)


def completed_plan(session, observed_at, *, calendar_loader=None):
    """Require real common-session calendars and close lags, before any IO.

    Do not substitute a prior European session on a local holiday: the current
    consumer requires the exact common XNYS label and must keep waiting then.
    """
    if type(session) is not date or session < FROZEN_DATE:
        raise ValueError("EXACT_POST_FREEZE_SESSION_REQUIRED")
    observed = pd.Timestamp(observed_at)
    if pd.isna(observed) or observed.tzinfo is None:
        raise ValueError("AWARE_OBSERVATION_REQUIRED")
    observed = observed.tz_convert("UTC")
    if calendar_loader is None:
        import exchange_calendars as xc

        def calendar_loader(mic):
            return xc.get_calendar(mic, start=str(session - timedelta(days=401)),
                                   end=str(session + timedelta(days=7)))
    calendars = {mic: calendar_loader(mic) for mic in {"XNYS", *CALENDARS.values()}}
    proofs = {}
    for mic, cal in calendars.items():
        if not cal.is_session(session.isoformat()):
            raise ValueError(f"WAIT_EXACT_LISTING_SESSION:{mic}:{session}")
        close = pd.Timestamp(cal.session_close(session.isoformat())).tz_convert("UTC")
        eligible = close + pd.Timedelta(minutes=20 if mic == "XNYS" else 90)
        if eligible > observed:
            raise ValueError(f"WAIT_SESSION_COMPLETION:{mic}:{session}")
        proofs[mic] = {"calendar": mic, "close_at": close.isoformat(),
                       "eligible_at": eligible.isoformat(), "exchange_timezone": str(cal.tz)}
    return calendars, {symbol: {**proofs[mic], "symbol": symbol,
                               "session": session.isoformat()}
                       for symbol, mic in CALENDARS.items()}


def refresh_required_marks(session, *, observed_at=None, path=None,
                           downloader=None, calendar_loader=None):
    """Called only by the existing scheduled refresh; injected in offline tests.

    One singleton download call for each due listing avoids hiding these five
    inside a large mixed-market batch. The legacy once-per-day attempt rule is
    NOT bypassed, even on missing marks. Invalid/empty responses add no rows;
    exact-session coverage and causes are returned to the owning refresh receipt.
    """
    from backend.services import global_prices as GP
    from backend.services.global_price_admission import staged_sha256

    observed_at = observed_at or datetime.now(timezone.utc)
    calendars, proofs = completed_plan(session, observed_at, calendar_loader=calendar_loader)
    observed = pd.Timestamp(observed_at).tz_convert("UTC")
    targets = dict.fromkeys(sorted(CALENDARS), session.isoformat())
    history_start = max(FROZEN_DATE, session - timedelta(days=400))
    errors, calls = [], []
    download = downloader or GP._yf_download

    def isolated_download(due, start, end):
        frames = []
        effective_start = max(history_start, pd.Timestamp(start).date())
        if not set(due) <= set(CALENDARS):
            raise ValueError("FROZEN_CONSTITUENT_FETCH_SCOPE")
        # GP invokes this callback while holding its existing cache lock.
        # Its concat writer is safe for the observed live schema only; refuse
        # unsupported historical dtypes before any provider call/publication.
        retained = GP.read_cache(path)
        supported = {"symbol": "object", "date": "datetime64[ns]",
                     **dict.fromkeys(["open", "high", "low", "close", "volume"], "float64"),
                     "source": "object", "pulled_utc": "object"}
        if not retained.empty and (
                list(retained.columns) != GP.COLUMNS or
                {col: str(retained[col].dtype) for col in GP.COLUMNS} != supported):
            errors.append({"symbol": None, "error": "UNSUPPORTED_RETAINED_CACHE_SCHEMA_NO_PUBLICATION"})
            return pd.DataFrame(columns=GP.COLUMNS[:7])
        for symbol in due:
            try:
                # Catch up missing eligible history after an outage as well as
                # today's exact mark. Never request a later session.
                calls.append(symbol)
                got = download([symbol], effective_start, session + timedelta(days=1))
                if got is None or got.empty:
                    raise ValueError("EMPTY_REQUIRED_MARK_RESPONSE")
                if not set(GP.COLUMNS[:7]) <= set(got.columns):
                    raise ValueError("REQUIRED_OHLCV_COLUMNS")
                got = got[GP.COLUMNS[:7]].copy()
                if set(got["symbol"]) != {symbol}:
                    raise ValueError("EXACT_FROZEN_SYMBOL_REQUIRED")
                stamps = pd.to_datetime(got["date"])
                cal = calendars[CALENDARS[symbol]]
                if stamps.dt.tz is not None:
                    if str(stamps.dt.tz) != str(cal.tz):
                        raise ValueError("EXACT_LISTING_TIMEZONE_REQUIRED")
                    stamps = stamps.dt.tz_localize(None)
                if stamps.isna().any() or not stamps.eq(stamps.dt.normalize()).all():
                    raise ValueError("EXACT_LOCAL_SESSION_DATE_REQUIRED")
                got["date"] = stamps.astype("datetime64[ns]")
                if got[["symbol", "date"]].duplicated().any():
                    raise ValueError("DUPLICATE_REQUIRED_MARKS")
                # Reuse the admission contract's strict OHLCV validation, in
                # bounded chunks; do not call its publication API.
                for offset in range(0, len(got), 256):
                    staged_sha256(got.iloc[offset:offset + 256])
                # Only new candidate values are normalized. Existing rows are
                # not cast or rewritten; their supported float schema is pinned.
                got[["open", "high", "low", "close", "volume"]] = got[
                    ["open", "high", "low", "close", "volume"]].astype("float64")
                for day in got["date"]:
                    label = day.date()
                    if label < effective_start or label > session or not cal.is_session(str(label)):
                        raise ValueError("UNREQUESTED_OR_NONSESSION_MARK")
                    if pd.Timestamp(cal.session_close(str(label))) + pd.Timedelta(minutes=90) > observed:
                        raise ValueError("UNCOMPLETED_MARK")
                if (got["date"] == pd.Timestamp(session)).sum() != 1:
                    raise ValueError("MISSING_EXACT_REQUIRED_MARK")
                frames.append(got)
            except Exception as exc:
                # Retain the operational cause; no false zero, forward fill,
                # proxy replacement, history rewrite or retry is performed.
                errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"[:300]})
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=GP.COLUMNS[:7])

    # Same cutoff/key as scripts.llm_portfolio.pull_today. Existing daily markers
    # remain authoritative; a prior incomplete attempt is reported, not reset.
    today = max(observed.date(), session + timedelta(days=1))
    bars = GP.ensure(sorted(CALENDARS), start=history_start,
                     path=path, today=today, downloader=isolated_download,
                     required_session=targets)
    coverage = GP.freshness_diagnostic(bars, CALENDARS, required_session=targets)
    # Latest-session coverage is insufficient: retain exact interior holes after
    # an outage, excluding actual exchange closures rather than forward filling.
    common_days = calendars["XNYS"].sessions_in_range(str(history_start), str(session))
    history = []
    for symbol, mic in sorted(CALENDARS.items()):
        required = [day.date().isoformat() for day in common_days
                    if calendars[mic].is_session(day.date().isoformat())]
        symbol_rows = bars[bars["symbol"] == symbol]
        missing, invalid = [], []
        for day in required:
            mark = symbol_rows[symbol_rows["date"] == pd.Timestamp(day)]
            if mark.empty:
                missing.append(day)
                continue
            try:
                if len(mark) != 1:
                    raise ValueError("DUPLICATE_RETAINED_MARK")
                staged_sha256(mark[GP.COLUMNS[:7]])
            except (ValueError, TypeError) as exc:
                invalid.append({"session": day, "error": f"{type(exc).__name__}: {exc}"[:200]})
        history.append({"symbol": symbol, "n_required": len(required),
                        "missing_sessions": missing, "invalid_sessions": invalid})
    history_ready = all(not row["missing_sessions"] and not row["invalid_sessions"] for row in history)
    legacy = bars.attrs["receipt"]
    ready = coverage["status"] == "COMPLETE_TARGET_COVERAGE" and history_ready and not errors
    return {"schema": "frozen_constituent_refresh/1", "status": "ok" if ready else "refused",
            "required_session": session.isoformat(), "observed_at": observed.isoformat(),
            "calendar_policy_sha256": POLICY_SHA256, "completed_sessions": proofs,
            "coverage": coverage, "download_calls": calls, "errors": errors,
            "history_coverage": {"status": "COMPLETE" if history_ready else "INCOMPLETE",
                                 "start": str(history_start), "end": str(session), "symbols": history},
            "n_pulled_now": legacy["n_pulled_now"],
            "n_skipped_pulled_today": legacy["n_skipped_pulled_today"],
            "n_new_rows": legacy["n_new_rows"],
            "reason": None if ready else "WAIT_EXACT_FROZEN_MARKS; daily attempt markers preserved",
            "basis": "UNADJUSTED_LOCAL_NO_FX_NO_DIVIDENDS; observed inputs, not historical PIT availability"}
