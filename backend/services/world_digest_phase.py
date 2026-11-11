"""When the world digest should run: by US market phase, not by a fixed clock.

Owner, 2026-11-11: "the digest can run at the end of the day, or early market,
before market, during market, like based on when it should run rather than being
a time code." Until then `AegisWorldDigest` ran every 6 h with `--hours 24`
(the 00:30 HKT run on 2026-11-11 cost $0.271 cold; the 06:30 run $0.053 warm).

One entry point, `decide(now, ...)`, given the current time (always a
parameter -- tests inject a fixed clock, nothing here reads the wall clock):

1. **Phase** from the XNYS calendar (`market_sessions`, early closes included):
   PRE_MARKET (before the open) / SESSION / AFTER_CLOSE on a session day, CLOSED
   on a weekend or holiday. A calendar that cannot be read REFUSES -- the only
   fallback is the weekday arithmetic `market_sessions` exists to delete.
2. **Slot.** Each phase opens a slot at a declared offset from its anchor
   (`WORLD_DIGEST_PHASE_OPENS_MIN`) and serves at most one successful run.
3. **Coverage.** The news since the last COMPLETE run (a successful run with no
   budget-skipped item), minus a small overlap, clamped. Items already typed
   are cache hits ($0), so the overlap re-types nothing; a run that skipped
   items for budget is not complete, so the next window starts where it did
   and the skipped items are typed then rather than lost.
4. **Spend.** The digest owns `WORLD_DIGEST_MONTHLY_SHARE` of the running
   month's DeepSeek cap (read from the shared envelope, read-only). A run's
   budget is min(phase ceiling, share left). Too little left REFUSES; over the
   month's pace, non-essential phases SKIP.

Exit contract (`scripts/world_digest.py --phase-auto`): SKIP -> rc 0 with a
receipt line saying why; REFUSED -> rc 2; RUN -> the run's own rc.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from backend import config as _cfg

ET = ZoneInfo("America/New_York")
PHASES = ("PRE_MARKET", "SESSION", "AFTER_CLOSE", "CLOSED")
SKIP, REFUSED, RUN = "SKIP", "REFUSED", "RUN"
#: The opening bell. `market_sessions` documents why it is not modelled per day:
#: every XNYS session (early closes included) opens at 09:30 ET.
OPEN_ET = time(9, 30)
DIGEST_PURPOSE_PREFIX = "world_digest"


def _utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("an aware datetime is required (inject the clock; never a naive time)")
    return dt.astimezone(timezone.utc)


def market_phase(now: datetime, *, is_session: Optional[Callable[[date], bool]] = None,
                 session_close: Optional[Callable[[date], Optional[datetime]]] = None) -> dict:
    """The XNYS phase of `now` and the slot it belongs to.

    `is_session` / `session_close` default to `market_sessions` (exchange_calendars);
    they raise `SessionCalendarUnavailable` rather than guess."""
    from backend.services import market_sessions as MS
    is_session = is_session or MS.is_session
    session_close = session_close or MS.session_close_utc
    now = _utc(now)
    et = now.astimezone(ET)
    day = et.date()
    midnight = datetime.combine(day, time(0, 0), ET).astimezone(timezone.utc)
    next_midnight = datetime.combine(day + timedelta(days=1), time(0, 0), ET).astimezone(timezone.utc)
    out: dict[str, Any] = {"now_utc": now.isoformat(), "et": et.isoformat(), "et_date": day.isoformat()}
    if not is_session(day):
        phase, open_utc, close_utc = "CLOSED", None, None
        start, end = midnight, next_midnight
    else:
        open_utc = datetime.combine(day, OPEN_ET, ET).astimezone(timezone.utc)
        close_utc = session_close(day)
        if close_utc is None:
            raise ValueError(f"{day} is a session without a close")
        close_utc = _utc(close_utc)
        if now < open_utc:
            phase, start, end = "PRE_MARKET", midnight, open_utc
        elif now < close_utc:
            phase, start, end = "SESSION", open_utc, close_utc
        else:
            phase, start, end = "AFTER_CLOSE", close_utc, next_midnight
    anchor_name, minutes = dict(_cfg.WORLD_DIGEST_PHASE_OPENS_MIN)[phase]
    anchor = {"open": open_utc, "close": close_utc, "midnight": midnight}[anchor_name]
    slot_opens = max(start, anchor + timedelta(minutes=float(minutes)))
    out.update(phase=phase, slot=f"{day.isoformat()}:{phase}",
               open_utc=open_utc.isoformat() if open_utc else None,
               close_utc=close_utc.isoformat() if close_utc else None,
               phase_start_utc=start.isoformat(), phase_end_utc=end.isoformat(),
               slot_opens_utc=slot_opens.isoformat(), in_window=slot_opens <= now < end)
    return out


def digest_month_spend(snapshot: dict) -> dict:
    """Month-to-date digest spend and the month cap from the envelope's month view.

    Counts what the envelope HOLDS (settled peak estimates, retained reservations),
    never a billed balance. Raises on a malformed snapshot (the caller refuses)."""
    from backend.services import provider_budget as PB
    cap_units = snapshot["cap_units"]
    if type(cap_units) is not int or cap_units <= 0:
        raise ValueError("envelope month cap is not a positive integer")
    held = 0
    for r in snapshot["calls"].values():
        if type(r["held_units"]) is not int or r["held_units"] < 0:
            raise ValueError("envelope call row has an invalid held amount")
        if str(r.get("purpose") or "").startswith(DIGEST_PURPOSE_PREFIX):
            held += r["held_units"]
    return {"digest_mtd_usd": held / PB.SCALE, "month_cap_usd": cap_units / PB.SCALE,
            "month": snapshot.get("month"), "blocked": bool(snapshot.get("blocked"))}


def _parse_stamp(stamp: str) -> Optional[datetime]:
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def past_runs(out_dir: Path, *, now: datetime, lookback_days: float = 8.0) -> list[dict]:
    """The successful (not dry-run, not DEGRADED) digests started before `now`,
    newest first, read from their own JSON (stamp, window, extraction). A run
    stamped after `now` (clock skew, a test) is ignored, never trusted."""
    now = _utc(now)
    oldest = now - timedelta(days=lookback_days)
    rows = []
    for p in sorted(Path(out_dir).glob("world_digest_*.json"), reverse=True):
        stamp = _parse_stamp(p.stem[len("world_digest_"):])
        if stamp is None or stamp > now:
            continue
        if stamp < oldest:
            break
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("dry_run") or d.get("status"):
            continue                                  # any status set is a degraded run
        until = (d.get("window") or {}).get("until")
        try:
            until_dt = _utc(datetime.fromisoformat(str(until)))
        except (TypeError, ValueError):
            until_dt = stamp
        ex = d.get("extraction") or {}
        rows.append({"stamp": stamp, "until": until_dt,
                     "complete": int(ex.get("budget_skipped") or 0) == 0,
                     "path": p.name})
    return rows


def coverage(now: datetime, runs: list[dict]) -> dict:
    """[since, now]: from the last COMPLETE run's cutoff minus the overlap, clamped."""
    now = _utc(now)
    lo = float(_cfg.WORLD_DIGEST_PHASE_MIN_HOURS)
    hi = float(_cfg.WORLD_DIGEST_PHASE_MAX_HOURS)
    last = next((r for r in runs if r["complete"]), None)
    if last is None:
        hours, basis = float(_cfg.WORLD_DIGEST_HOURS), "NO_COMPLETE_RUN_DEFAULT_HOURS"
    else:
        hours = (now - last["until"]).total_seconds() / 3600 + float(_cfg.WORLD_DIGEST_PHASE_OVERLAP_H)
        basis = f"SINCE_LAST_COMPLETE_RUN {last['path']}"
    clamped = min(hi, max(lo, hours))
    return {"hours": round(clamped, 3), "since_utc": (now - timedelta(hours=clamped)).isoformat(),
            "basis": basis + ("" if clamped == hours else f" (clamped from {hours:.2f} h)")}


def attempts_in_slot(decisions_path: Path, slot: str) -> int:
    try:
        lines = Path(decisions_path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return 0
    n = 0
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        n += int(r.get("decision") == RUN and r.get("slot") == slot)
    return n


def month_elapsed_fraction(now: datetime) -> float:
    now = _utc(now)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    nxt = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    return (now - start).total_seconds() / (nxt - start).total_seconds()


def decide(now: datetime, *, out_dir: Path, decisions_path: Path,
           snapshot_fn: Callable[[], dict],
           count_new_items: Callable[[datetime, datetime], int],
           phase_fn: Callable[[datetime], dict] = market_phase) -> dict:
    """One decision: {"decision": SKIP | REFUSED | RUN, "reason", ...}. Never pays."""
    now = _utc(now)
    rec: dict[str, Any] = {"t": now.isoformat(), "schema": "world_digest_phase/1"}

    def done(decision: str, reason: str, **kw: Any) -> dict:
        rec.update(decision=decision, reason=reason, **kw)
        return rec

    try:
        ph = phase_fn(now)
    except Exception as exc:                                         # noqa: BLE001
        return done(REFUSED, "CALENDAR_UNAVAILABLE", error=type(exc).__name__)
    rec.update({k: ph[k] for k in ("phase", "slot", "et", "slot_opens_utc", "phase_end_utc")})
    if not ph["in_window"]:
        return done(SKIP, "NOT_IN_WINDOW")
    runs = past_runs(out_dir, now=now)
    opens = datetime.fromisoformat(ph["slot_opens_utc"])
    served = next((r for r in runs if r["stamp"] >= opens), None)
    if served is not None:
        return done(SKIP, "SLOT_SERVED", served_by=served["path"])
    attempts = attempts_in_slot(decisions_path, ph["slot"])
    if attempts >= int(_cfg.WORLD_DIGEST_PHASE_MAX_ATTEMPTS):
        return done(REFUSED, "ATTEMPTS_EXHAUSTED", attempts=attempts)
    cov = coverage(now, runs)
    rec["coverage"] = cov
    try:
        spend = digest_month_spend(snapshot_fn())
    except Exception as exc:                                         # noqa: BLE001
        # Only the exception TYPE crosses: the envelope may carry evidence text.
        return done(REFUSED, "ENVELOPE_UNREADABLE", error=type(exc).__name__)
    share = float(_cfg.WORLD_DIGEST_MONTHLY_SHARE)
    share_usd = share * spend["month_cap_usd"]
    left = share_usd - spend["digest_mtd_usd"]
    pace = share_usd * month_elapsed_fraction(now)
    over_pace = spend["digest_mtd_usd"] > pace + float(_cfg.WORLD_DIGEST_PHASE_PACE_SLACK_USD)
    rec["spend"] = {**spend, "share": share, "share_usd": round(share_usd, 4),
                    "share_left_usd": round(left, 4), "pace_usd": round(pace, 4),
                    "over_pace": over_pace}
    if spend["blocked"]:
        return done(REFUSED, "ENVELOPE_BLOCKED")
    if left < float(_cfg.WORLD_DIGEST_PHASE_MIN_RUN_USD):
        return done(REFUSED, "SHARE_EXHAUSTED")
    if over_pace and ph["phase"] not in tuple(_cfg.WORLD_DIGEST_PHASE_ESSENTIAL):
        return done(SKIP, "OVER_PACE")
    since = datetime.fromisoformat(cov["since_utc"])
    n_new = int(count_new_items(since, now))
    rec["n_items_in_window"] = n_new
    if n_new < int(_cfg.WORLD_DIGEST_PHASE_MIN_NEW_ITEMS):
        return done(SKIP, "NOTHING_NEW")
    ceiling = float(dict(_cfg.WORLD_DIGEST_PHASE_CEILING_USD)[ph["phase"]])
    budget = min(ceiling, left)
    if not math.isfinite(budget) or budget <= 0:
        return done(REFUSED, "NO_FINITE_BUDGET")
    return done(RUN, "DUE", hours=cov["hours"], budget_usd=round(budget, 4),
                ceiling_usd=ceiling, attempt=attempts + 1)

