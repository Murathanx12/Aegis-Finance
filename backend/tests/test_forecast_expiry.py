"""CH-42 forecast and evidence expiry: synthetic ledgers only, no network.

Every `as_of` is passed explicitly and every date is historical, so no test
depends on the day it runs."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.services import forecast_expiry as FE

AS_OF = date(2025, 12, 31)


def _row(pid: str, *, made_at: str, h: int = 5, ticker: str = "AAA", outcome=None,
         void_reason=None, probability: float = 0.6, observable: str = "return_sign",
         benchmark=None, resolves_after: str | None = None, **extra) -> dict:
    from backend.services.belief_state import PredictionRecord
    r = {"prediction_id": pid, "ticker": ticker, "specialist": "test:v0", "observable": observable,
         "horizon_days": h, "probability": probability, "threshold": None, "benchmark": benchmark,
         "made_at": made_at,
         "resolves_after": resolves_after or PredictionRecord.resolution_date(made_at, h if isinstance(h, int) else 5),
         "outcome": outcome, "brier": (None if outcome is None else (probability - outcome) ** 2),
         "resolved_at": None if outcome is None else made_at, "void_reason": void_reason}
    r.update(extra)
    return r


def _write_ledger(root: Path, rows: list) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / "predictions.jsonl"
    with open(p, "wb") as fh:
        for r in rows:
            fh.write(((r if isinstance(r, str) else json.dumps(r)) + "\n").encode("utf-8"))
    return p


def _write_bars(root: Path, symbols: dict) -> None:
    """symbols: {sym: (first_session, last_session)} on the real XNYS calendar."""
    sess = FE.session_calendar(date(2025, 6, 2), date(2026, 1, 30))
    recs = []
    for sym, (lo, hi) in symbols.items():
        for d in sess:
            if lo <= d <= hi:
                recs.append({"symbol": sym, "date": pd.Timestamp(d), "close": 100.0})
    (root / "prices_2025_26").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(recs).to_parquet(root / "prices_2025_26" / "bars.parquet", index=False)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ─────────────────────────────── valid_until ────────────────────────────────

def test_horizon_counts_sessions_and_skips_a_holiday_inside_the_window():
    # a synthetic calendar with one weekday holiday (Wed 2025-12-24 missing)
    days = [date(2025, 12, 22) + timedelta(days=i) for i in range(14)]
    sessions = [d for d in days if d.weekday() < 5 and d != date(2025, 12, 24)]
    r = _row("a", made_at="2025-12-22T15:00:00+00:00", h=3)
    v = FE.derive_valid_until(r, sessions)
    # entry 12-22, then 12-23, (12-24 holiday), 12-25, 12-26 -> 3 sessions later is 12-26
    assert v["entry_session"] == "2025-12-22" and v["valid_until"] == "2025-12-26"
    assert v["basis"] == "session_calendar"


def test_real_xnys_calendar_christmas_inside_a_five_session_window():
    sessions = FE.session_calendar(date(2025, 12, 1), date(2026, 1, 31))
    assert date(2025, 12, 25) not in sessions
    # made on a Saturday: the entry is the next session (Mon 12-22)
    v = FE.derive_valid_until(_row("b", made_at="2025-12-20T10:00:00+00:00", h=5), sessions)
    assert v["entry_session"] == "2025-12-22"
    assert v["valid_until"] == "2025-12-30"   # 23, 24, 26, 29, 30 (25 is a holiday)


def test_an_undatable_row_is_undated_and_named():
    sessions = FE.session_calendar(date(2025, 12, 1), date(2026, 1, 31))
    r = _row("u", made_at="2025-12-22T10:00:00+00:00", h=5)
    r["horizon_days"], r["resolves_after"] = None, None
    c = FE.classify(r, as_of=AS_OF, sessions=sessions)
    assert c["state"] == FE.UNDATED and c["valid_until"] is None
    assert "horizon_days None" in c["reason"] and "resolves_after" in c["reason"]
    # a row with no horizon but its own target date is dated from that date, never UNDATED
    r2 = dict(r, resolves_after="2025-12-29")
    assert FE.classify(r2, as_of=AS_OF, sessions=sessions)["basis"] == "resolves_after"


# ─────────────────────────────── the sweep ──────────────────────────────────

def _fixture(tmp_path: Path):
    root = tmp_path / "data" / "optimus"
    rows = [
        _row("g1", made_at="2025-11-03T15:00:00+00:00", outcome=1),                  # graded
        _row("v1", made_at="2025-11-03T15:00:00+00:00",
             void_reason="UNRESOLVABLE_DELISTED: test"),                              # void on record
        _row("e1", made_at="2025-12-01T15:00:00+00:00", ticker="AAA"),               # owed, resolvable
        _row("e2", made_at="2025-12-01T15:00:00+00:00", ticker="DEAD"),              # owed, delisted
        _row("a1", made_at="2025-12-29T15:00:00+00:00", h=20),                       # active
        _row("n1", made_at="2025-12-22T15:00:00+00:00", h=None, resolves_after=None),  # undated
        "{not json",
    ]
    rows[5]["horizon_days"] = None
    rows[5]["resolves_after"] = None
    led = _write_ledger(root, rows)
    _write_bars(root, {"AAA": (date(2025, 6, 2), date(2026, 1, 30)),
                       "SPY": (date(2025, 6, 2), date(2026, 1, 30)),
                       "DEAD": (date(2025, 6, 2), date(2025, 12, 3))})
    return root, led


def test_counts_reconcile_and_the_frozen_rows_never_change(tmp_path):
    root, led = _fixture(tmp_path)
    before = _sha(led)
    files_before = FE.snapshot_tree(root)
    out = tmp_path / "out"
    rec = FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=pd.Timestamp("2026-01-01T00:00Z").to_pydatetime())
    r = rec["reconciliation"]["predictions"]
    assert r["rows_read"] == 7 and r["reconciles"]
    assert (r["EXPIRED_GRADED"], r["VOID"], r["EXPIRED_UNGRADED"], r["ACTIVE"], r["UNDATED"]) == (1, 1, 2, 1, 2)
    assert r["unparseable_lines"] == 1
    assert _sha(led) == before                               # not one byte of the ledger moved
    assert FE.snapshot_tree(root) == files_before            # nothing written under the data root
    names = {u["forecast_id"] for u in rec["undated"]["rows"]}
    assert names == {"n1", "line:7"}
    side = [json.loads(x) for x in FE.expiry_path(out).read_text(encoding="utf-8").splitlines()]
    raw_lines = led.read_bytes().splitlines()
    for s in side:                                            # each side row names its frozen line's hash
        assert s["row_sha256"] == hashlib.sha256(raw_lines[s["line"] - 1]).hexdigest()
    disp = rec["expired_ungraded"]["dispositions"]
    assert disp[FE.RESOLVABLE_NOW] == 1 and disp[FE.VOID_PROPOSED] == 1


def test_a_second_sweep_appends_only_state_changes(tmp_path):
    root, _ = _fixture(tmp_path)
    out = tmp_path / "out"
    t0 = pd.Timestamp("2026-01-01T00:00Z").to_pydatetime()
    first = FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0)
    assert first["side_ledger"]["rows_appended"] == 7
    again = FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0 + timedelta(hours=1))
    assert again["side_ledger"]["rows_appended"] == 0
    # far enough ahead that the active 20-session forecast has expired: exactly one change
    later = FE.sweep(data_root=root, out_dir=out, as_of=date(2026, 3, 2), now=t0 + timedelta(days=60))
    assert later["side_ledger"]["rows_appended"] == 1
    lines = FE.expiry_path(out).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 8 and json.loads(lines[-1])["forecast_id"] == "a1"
    assert json.loads(lines[-1])["state"] == FE.EXPIRED_UNGRADED


def test_the_void_rule_is_stated_before_counting_and_ignores_the_score(tmp_path):
    root, _ = _fixture(tmp_path)
    rec = FE.sweep(data_root=root, out_dir=tmp_path / "out", as_of=AS_OF, write=False)
    keys = list(rec)
    assert keys.index("void_rule") < keys.index("reconciliation")
    assert "never reads probability, outcome or brier" in rec["void_rule"]
    panel = FE.load_panel(root, ["AAA", "DEAD"])
    for t, want in (("DEAD", FE.VOID_PROPOSED), ("AAA", FE.RESOLVABLE_NOW)):
        got = {FE.disposition(_row("x", made_at="2025-12-01T15:00:00+00:00", ticker=t, probability=p),
                              as_of=AS_OF, panel=panel)["disposition"] for p in (0.01, 0.5, 0.99)}
        assert got == {want}                                   # the probability cannot move a disposition
    d = FE.disposition(_row("x", made_at="2025-12-01T15:00:00+00:00", ticker="DEAD"), as_of=AS_OF, panel=panel)
    assert d["code"] == "UNRESOLVABLE_DELISTED" and d["on_record"] is False
    w = FE.disposition(_row("y", made_at="2025-12-01T15:00:00+00:00", ticker="NOBARS"), as_of=AS_OF, panel=panel)
    assert w["disposition"] == FE.WAITING_INPUT and "bars:NOBARS" in w["waiting_for"]


def test_campaign_overdue_ids_are_accounted_for_one_by_one(tmp_path):
    root, _ = _fixture(tmp_path)
    copy = [_row("g1", made_at="2025-11-03T15:00:00+00:00"),       # overdue in the copy, graded live
            _row("v1", made_at="2025-11-03T15:00:00+00:00"),       # overdue in the copy, void live
            _row("e2", made_at="2025-12-01T15:00:00+00:00", ticker="DEAD"),
            _row("e1", made_at="2025-12-01T15:00:00+00:00"),
            _row("gone", made_at="2025-11-03T15:00:00+00:00"),     # not in the live ledger
            _row("fresh", made_at="2025-12-29T15:00:00+00:00", h=20)]  # not overdue: not counted
    lines = [(i + 1, (json.dumps(r) + "\n").encode()) for i, r in enumerate(copy)]
    rec = FE.sweep(data_root=root, out_dir=tmp_path / "out", as_of=AS_OF, campaign_lines=lambda: iter(lines),
                   campaign_label="synthetic copy")
    c = rec["campaign"]
    assert c["n_overdue"] == 5 and c["reconciles"]
    assert c["dispositions"][FE.RESOLVED] == 1
    assert c["dispositions"][FE.VOID_PROPOSED] == 2 and c["void_on_ledger_record"] == 1
    assert c["dispositions"][FE.RESOLVABLE_NOW] == 1 and c["dispositions"][FE.NOT_IN_LEDGER] == 1
    acc = Path(rec["receipt_path"]).parent.glob("campaign_accounting_*.jsonl")
    ids = {json.loads(x)["forecast_id"] for f in acc for x in f.read_text(encoding="utf-8").splitlines()}
    assert ids == {"g1", "v1", "e2", "e1", "gone"}


def test_refuses_an_out_inside_the_data_folder_and_a_missing_ledger(tmp_path):
    root, _ = _fixture(tmp_path)
    with pytest.raises(FE.ForecastExpiryRefused):
        FE.sweep(data_root=root, out_dir=root / "forecast_expiry_out", as_of=AS_OF)
    with pytest.raises(FE.ForecastExpiryRefused):
        FE.sweep(data_root=root.parent, out_dir=tmp_path / "out2", as_of=AS_OF)   # no predictions.jsonl
    assert not (root / "forecast_expiry_out").exists()


# ─────────────────────────────── labels ─────────────────────────────────────

def test_a_label_earned_early_steps_down_on_a_losing_trailing_window():
    from backend.services import book_dna as BD
    sessions = [d.isoformat() for d in FE.session_calendar(date(2025, 1, 2), date(2025, 12, 31))]
    inc = sessions[0]
    win = [(d, 0.004, 0.001) for d in sessions[1:120]]           # ahead of SPY early on
    lose = [(d, -0.002, 0.001) for d in sessions[120:]]          # behind SPY over the last ~130
    ser = win + lose
    p = BD.params()
    sub = BD.subwindows(ser, len(ser))
    b = 1.0
    s = 1.0
    for _, x, y in ser:
        b, s = b * (1 + x), s * (1 + y)
    exc = 100 * (b - s)
    lab = BD.evidence_label(sessions=len(ser), excess_pp=exc, sub=sub, fair_twin_excess_pp=None,
                            replicated_by=None, p=p)
    book = {"account": "bk", "category": "strategy", "family": "night_books", "rule": None,
            "inception": inc, "last_mark": sessions[-1], "sessions_graded": len(ser), "excess_pp": exc,
            "evidence": {"label": "EARLY_EVIDENCE", "why": "synthetic"}, "_series": ser}
    rows = FE.label_stepdown([book], spy_sessions=sessions, p=p, n_trailing=63, vol_cut=0.2)
    r = rows[0]
    assert r["trailing_window"]["sessions"] == 63 and r["trailing_window"]["n_periods"] == 63
    assert r["trailing_label"].startswith("OBSERVED") and r["would_step_down"] is True
    assert r["earned_regime"]["status"] == "OK" and r["earned_regime"]["tag"].startswith("SPY_UP")
    assert lab["label"] in ("EARLY_EVIDENCE", "OBSERVED(%d)" % len(ser))   # the full-window rule is book_dna's own


def test_a_book_younger_than_the_window_is_its_own_trailing_window():
    sessions = [d.isoformat() for d in FE.session_calendar(date(2025, 1, 2), date(2025, 3, 31))]
    ser = [(d, 0.001, 0.0) for d in sessions[1:30]]
    out, n, lo, whole = FE.trailing_series(ser, sessions, sessions[0], sessions[29], 63, 29)
    assert whole is True and n == 29 and len(out) == 29
