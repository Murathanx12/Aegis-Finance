"""The `forecast_grader` status row counts what the GRADER says is owed.

The row used to count "no `resolved_at`, past `resolves_after`" with a regex. A
voided row never carries `resolved_at`, so every void read as overdue (576 on a
ledger that owed 171). The row now calls `forecast_grader.bucket_of`.

Synthetic rows only; every date is derived from `now` (protocol item 5).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.services import forecast_grader as FG
from backend.services import system_health as SH


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _ctx(tmp_path: Path, now: datetime) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=now, repo=tmp_path,
                       run=lambda argv, t: (None, "FileNotFoundError: not installed"),
                       http_json=lambda url, t: (None, 0.0, "URLError: refused"),
                       pid_cmdline=lambda pid: None, railway_url="http://railway.invalid")


def _write(tmp_path: Path, lines: list[str]) -> None:
    p = tmp_path / "optimus" / "predictions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _row(now: datetime, due_in_days, **kw) -> dict:
    ra = (now.date() + timedelta(days=due_in_days)).isoformat() if due_in_days is not None else None
    base = {"prediction_id": f"p{len(kw)}{due_in_days}", "ticker": "AAA",
            "observable": "return_sign", "horizon_days": 5,
            "made_at": (now - timedelta(days=30)).isoformat(timespec="seconds"),
            "resolves_after": ra, "resolved_at": None, "outcome": None}
    base.update(kw)
    return base


def _synthetic(now: datetime) -> list[dict]:
    resolved = (now - timedelta(hours=3)).isoformat(timespec="seconds")
    return [
        _row(now, -6),                                              # owed
        _row(now, 0),                                               # owed: due TODAY (>=)
        _row(now, -4, observable="no_such_observable"),             # owed, another bucket
        _row(now, -9, void_reason="UNRESOLVABLE_DELISTED"),         # voided, no resolved_at
        _row(now, -8, void_reason="UNRESOLVABLE_NO_EQUITY_BAR"),    # voided
        _row(now, -7, void_reason="UNRESOLVABLE_NO_BAR_PAST_HORIZON"),
        _row(now, -5, outcome=1, resolved_at=resolved),             # graded
        _row(now, -5, outcome=0, resolved_at=resolved),             # graded (0 is an outcome)
        _row(now, 30, made_at=now.isoformat(timespec="seconds")),   # not due, window open
        _row(now, None, resolves_after="soon"),                     # unreadable date
        _row(now, None),                                            # no date at all
    ]


def test_the_row_counts_owed_voided_graded_not_due_and_undated(tmp_path):
    now = _now()
    rows = _synthetic(now)
    _write(tmp_path, [json.dumps(r) for r in rows] + ["{not json"])
    ctx = _ctx(tmp_path, now)
    L = SH._ledger_scan(ctx)
    assert (L["grade_owed"], L["voided"], L["graded"], L["not_yet_due"], L["undated"],
            L["unparsed"]) == (3, 3, 2, 1, 2, 1)
    assert L["due_unresolved"] == 3 and L["rows"] == 12
    g = SH.p_forecast_grader(ctx)
    assert "grade owed: 3; voided: 3; window closed, not yet due: " in g.detail
    assert "2 row(s) with an unreadable resolves_after" in g.detail
    assert "1 unparseable line(s)" in g.detail


def test_drift_the_rows_count_is_bucket_of_on_the_same_rows(tmp_path):
    """The row's numbers are `forecast_grader.bucket_of`'s, not a copy of its rule."""
    now = _now()
    rows = _synthetic(now)
    today = now.date()
    buckets = Counter(FG.bucket_of(r, today=today) for r in rows)
    dated = [r for r in rows
             if FG.bucket_of({"resolves_after": r["resolves_after"]}, today=date.min) == "not_yet_due"]
    owed = sum(1 for r in dated
               if FG.bucket_of(r, today=today) not in ("graded", "VOID", "not_yet_due"))
    assert owed == 3
    _write(tmp_path, [json.dumps(r) for r in rows])
    L = SH._ledger_scan(_ctx(tmp_path, now))
    assert L["grade_owed"] == owed
    assert L["voided"] == buckets["VOID"]
    assert L["graded"] == buckets["graded"]
    assert L["not_yet_due"] == buckets["not_yet_due"]
    assert L["grade_owed"] + L["undated"] == sum(
        n for b, n in buckets.items() if b not in ("graded", "VOID", "not_yet_due"))
    assert sum(L["owed_by_bucket"].values()) == owed
    assert set(L["owed_by_bucket"]) <= set(FG.BUCKETS)


def test_voided_rows_alone_do_not_make_the_grader_stale(tmp_path):
    """The defect: voids past their date, and a grader that last resolved days ago."""
    now = _now()
    old = (now - timedelta(days=9)).isoformat(timespec="seconds")
    voids = [_row(now, -20 - i, void_reason="UNRESOLVABLE_DELISTED") for i in range(5)]
    _write(tmp_path, [json.dumps(r) for r in voids + [_row(now, -12, outcome=1, resolved_at=old)]])
    g = SH.p_forecast_grader(_ctx(tmp_path, now))
    assert g.verdict == "ALIVE" and "grade owed: 0; voided: 5" in g.detail
    # the same ledger with ONE row genuinely owed keeps the old threshold
    _write(tmp_path, [json.dumps(r) for r in voids + [_row(now, -12, outcome=1, resolved_at=old),
                                                      _row(now, -3)]])
    g = SH.p_forecast_grader(_ctx(tmp_path, now))
    assert g.verdict == "STALE" and "grade owed: 1; voided: 5" in g.detail


def test_a_ledger_no_row_of_which_parses_is_unknown_never_zero(tmp_path):
    now = _now()
    _write(tmp_path, ["{broken", "also broken"])
    g = SH.p_forecast_grader(_ctx(tmp_path, now))
    assert g.verdict == "UNKNOWN" and "CANNOT DETERMINE" in g.detail
    assert "grade owed: 0" not in g.detail


def test_open_rows_that_cannot_be_dated_are_unknown_never_zero(tmp_path):
    now = _now()
    res = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    _write(tmp_path, [json.dumps(r) for r in (
        _row(now, None), _row(now, None, resolves_after="next week"),
        _row(now, -5, outcome=1, resolved_at=res))])
    g = SH.p_forecast_grader(_ctx(tmp_path, now))
    assert g.verdict == "UNKNOWN" and "CANNOT DETERMINE" in g.detail
    assert "grade owed: 0" not in g.detail


def test_no_ledger_is_unknown(tmp_path):
    g = SH.p_forecast_grader(_ctx(tmp_path, _now()))
    assert g.verdict == "UNKNOWN"


def test_window_closed_not_due_is_counted_or_declared_not_computed(tmp_path, monkeypatch):
    """A row whose trading window closed but whose resolver date is ahead is not owed."""
    now = _now()
    r = _row(now, 3, horizon_days=1, made_at=(now - timedelta(days=20)).isoformat(timespec="seconds"))
    res = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    _write(tmp_path, [json.dumps(r), json.dumps(_row(now, -5, outcome=1, resolved_at=res))])
    L = SH._ledger_scan(_ctx(tmp_path, now))
    assert L["grade_owed"] == 0 and L["not_yet_due"] == 1
    assert L["window_closed_not_due"] == 1

    from backend.services import forecast_expiry as FE

    def _no_calendar(lo, hi):
        raise RuntimeError("no calendar")
    monkeypatch.setattr(FE, "session_calendar", _no_calendar)
    ctx = _ctx(tmp_path, now)
    assert SH._ledger_scan(ctx)["window_closed_not_due"] is None
    assert "window closed, not yet due: not computed" in SH.p_forecast_grader(ctx).detail
