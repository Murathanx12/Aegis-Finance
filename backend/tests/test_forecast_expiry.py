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
    assert (r["EXPIRED_GRADED"], r["VOID"], r["GRADE_OWED"], r["WINDOW_CLOSED_NOT_DUE"], r["ACTIVE"],
            r["UNDATED"]) == (1, 1, 2, 0, 1, 2)
    assert r["unparseable_lines"] == 1
    assert _sha(led) == before                               # not one byte of the ledger moved
    assert FE.snapshot_tree(root) == files_before            # nothing written under the data root
    names = {u["forecast_id"] for u in rec["undated"]["rows"]}
    assert names == {"n1", "line:7"}
    side = [json.loads(x) for x in FE.expiry_path(out).read_text(encoding="utf-8").splitlines()]
    raw_lines = led.read_bytes().splitlines()
    for s in side:                                            # each side row names its frozen line's hash
        assert s["row_sha256"] == hashlib.sha256(raw_lines[s["line"] - 1]).hexdigest()
    disp = rec["grade_owed"]["dispositions"]
    assert disp[FE.RESOLVABLE_NOW] == 1 and disp[FE.VOID_PROPOSED] == 1
    assert "WHOLE ledger" in rec["score"]["population"] and "CH-12" in rec["score"]["population"]
    assert "not comparable" in rec["score"]["population"]


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
    assert json.loads(lines[-1])["state"] == FE.GRADE_OWED


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


def test_waiting_input_names_a_book_nav_and_a_bar_only_in_the_global_panel(tmp_path):
    root, _ = _fixture(tmp_path)
    sess = FE.session_calendar(date(2025, 11, 3), date(2026, 1, 30))
    (root / "llm_portfolio").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"symbol": "005930.KS", "date": [pd.Timestamp(d) for d in sess]}).to_parquet(
        root / "llm_portfolio" / "global_bars.parquet", index=False)
    panel = FE.load_panel(root, ["005930.KS", "book:abc", "SPY"])
    k = FE.disposition(_row("k", made_at="2025-12-01T15:00:00+00:00", ticker="005930.KS"), as_of=AS_OF, panel=panel)
    assert k["disposition"] == FE.WAITING_INPUT and "global_bars.parquet" in k["waiting_for"]
    assert "window mismatch" in k["waiting_for"] and "own exchange calendar" in k["waiting_for"]
    b = FE.disposition(_row("b", made_at="2025-12-01T15:00:00+00:00", ticker="book:abc",
                            observable="beats_benchmark", benchmark="book:twin"), as_of=AS_OF, panel=panel)
    assert b["disposition"] == FE.WAITING_INPUT and "nav:book:abc" in b["waiting_for"]


def test_a_young_book_keeps_its_fair_twin_rung_and_an_old_one_is_cannot_determine():
    from backend.services import book_dna as BD
    p = BD.params()
    sessions = [d.isoformat() for d in FE.session_calendar(date(2025, 1, 2), date(2025, 12, 31))]
    why = ">= 21 sessions, excess > 0, 3 of 3 sub-windows positive; excess over the fair twin +1.00 pp"
    young = {"account": "young", "category": "strategy", "rule": None, "inception": sessions[0],
             "last_mark": sessions[40], "sessions_graded": 40, "excess_pp": 3.0,
             "fair_twin": {"excess_over_twin_pp": 1.0}, "evidence": {"label": "REPLICATED", "why": why},
             "_series": [(d, 0.002, 0.001) for d in sessions[1:41]]}
    old = dict(young, account="old", last_mark=sessions[-1], sessions_graded=len(sessions) - 1,
               _series=[(d, 0.002, 0.001) for d in sessions[1:]])
    rows = {r["account"]: r for r in FE.label_stepdown([young, old], spy_sessions=sessions, p=p,
                                                        n_trailing=63, vol_cut=0.2)}
    assert rows["young"]["trailing_label"] == "REPLICATED" and rows["young"]["step_down"] == "NO"
    assert rows["old"]["trailing_label"] == "EARLY_EVIDENCE"
    assert rows["old"]["step_down"] == "CANNOT_DETERMINE" and rows["old"]["would_step_down"] is False


def test_the_cli_sweeps_a_synthetic_root_and_refuses_an_out_inside_it(tmp_path, capsys):
    from scripts import forecast_expiry as CLI
    root, led = _fixture(tmp_path)
    before = _sha(led)
    rc = CLI.main(["sweep", "--data-root", str(root), "--out", str(tmp_path / "o"), "--as-of", "2025-12-31",
                   "--no-campaign"])
    assert rc == 0 and _sha(led) == before
    assert "reconciles: True" in capsys.readouterr().out
    assert CLI.main(["sweep", "--data-root", str(root), "--out", str(root.parent / "x"), "--no-campaign"]) == 2
    d = FE.tree_diff({"a": 1}, {"a": 1, "forecast_expiry/expiry.jsonl": 5})
    assert CLI._ours_or_zero(d) == 4
    assert CLI._ours_or_zero(FE.tree_diff({"a": 1}, {"a": 2, "news/x.json": 3})) == 0


# ─────────────────────────────── fix round (review 2026-11-15) ──────────────

def _states_over_time(row: dict, days: list) -> dict:
    sessions = FE.session_calendar(date(2025, 6, 2), date(2026, 6, 30))
    return {d: FE.classify(row, as_of=d, sessions=sessions)["state"] for d in days}


def test_a_closed_window_before_the_resolver_date_is_not_a_grade_owed():
    r = _row("w", made_at="2025-12-01T15:00:00+00:00", h=5)
    sessions = FE.session_calendar(date(2025, 6, 2), date(2026, 6, 30))
    vu = date.fromisoformat(FE.derive_valid_until(r, sessions)["valid_until"])
    ra = date.fromisoformat(r["resolves_after"])
    assert vu < ra - timedelta(days=1)                       # the fixture has days between the two
    got = _states_over_time(r, [vu, vu + timedelta(days=1), ra - timedelta(days=1), ra, ra + timedelta(days=9)])
    assert list(got.values()) == [FE.ACTIVE, FE.WINDOW_CLOSED_NOT_DUE, FE.WINDOW_CLOSED_NOT_DUE,
                                  FE.GRADE_OWED, FE.GRADE_OWED]
    assert "EXPIRED_UNGRADED" not in FE.STATES and len(FE.STATES) == 6


def test_grade_owed_is_the_graders_own_due_rule_and_cannot_drift():
    """GRADE_OWED must be exactly `forecast_grader.bucket_of`'s "due, ungraded, unvoided".

    Two halves: the boundary the receipt's bridge is written against (>=, not >), and
    agreement of every classification with bucket_of over a grid."""
    from backend.services import forecast_grader as FG
    assert FE.GRADER_NOT_YET_DUE in FG.BUCKETS
    r = _row("d", made_at="2025-12-01T15:00:00+00:00", h=5)
    ra = date.fromisoformat(r["resolves_after"])
    assert FG.bucket_of(r, today=ra - timedelta(days=1)) == FE.GRADER_NOT_YET_DUE
    assert FG.bucket_of(r, today=ra) != FE.GRADER_NOT_YET_DUE          # due ON the date
    sessions = FE.session_calendar(date(2025, 6, 2), date(2026, 6, 30))
    rows = [_row("a", made_at="2025-12-01T15:00:00+00:00", h=5),
            _row("b", made_at="2025-11-14T15:00:00+00:00", h=20, ticker=""),          # lacks a target
            _row("c", made_at="2025-12-05T15:00:00+00:00", h=10, observable="no_such_observable"),
            _row("f", made_at="2025-12-01T15:00:00+00:00", h=21, ticker="005930.KS"),  # foreign
            _row("g", made_at="2025-12-01T15:00:00+00:00", h=5, outcome=1),
            _row("v", made_at="2025-12-01T15:00:00+00:00", h=5, void_reason="UNRESOLVABLE_DELISTED: t")]
    n_owed = 0
    for row in rows:
        for k in range(0, 90):
            d = date(2025, 11, 20) + timedelta(days=k)
            st = FE.classify(row, as_of=d, sessions=sessions)["state"]
            due = FG.bucket_of(row, today=d) not in ("graded", "VOID", FE.GRADER_NOT_YET_DUE)
            assert (st == FE.GRADE_OWED) == due, (row["prediction_id"], d, st)
            n_owed += int(due)
    assert n_owed > 100                                        # the grid really crossed the boundary


def test_the_receipt_bridges_the_loose_count_to_grade_owed(tmp_path):
    root = tmp_path / "data" / "optimus"
    today_row = _row("t1", made_at="2025-12-15T15:00:00+00:00", h=5)
    as_of = date.fromisoformat(today_row["resolves_after"])            # due exactly today
    rows = [today_row,
            _row("p1", made_at="2025-12-01T15:00:00+00:00"),            # past, ungraded
            _row("p2", made_at="2025-12-02T15:00:00+00:00"),
            _row("v1", made_at="2025-11-03T15:00:00+00:00", void_reason="UNRESOLVABLE_DELISTED: t"),
            _row("v2", made_at="2025-11-04T15:00:00+00:00", void_reason="UNRESOLVABLE_DELISTED: t"),
            _row("v3", made_at="2025-11-05T15:00:00+00:00", void_reason="UNRESOLVABLE_DELISTED: t"),
            _row("g1", made_at="2025-11-03T15:00:00+00:00", outcome=1),  # has resolved_at: not in the loose count
            _row("w1", made_at="2025-12-16T15:00:00+00:00", h=5),       # window closed, not due
            _row("a1", made_at="2025-12-22T15:00:00+00:00", h=60)]
    _write_ledger(root, rows)
    _write_bars(root, {"AAA": (date(2025, 6, 2), date(2026, 1, 30))})
    rec = FE.sweep(data_root=root, out_dir=tmp_path / "out", as_of=as_of, write=False)
    r = rec["reconciliation"]["predictions"]
    assert (r["GRADE_OWED"], r["WINDOW_CLOSED_NOT_DUE"], r["ACTIVE"], r["VOID"]) == (3, 1, 1, 3)
    b = rec["grade_owed"]["bridge"]
    assert b["rows_without_resolved_at_past_resolves_after"] == 5      # p1, p2 and the three voids
    assert b["minus_voided_on_record"] == 3
    assert b["equals_ungraded_unvoided_past_resolves_after"] == 2
    assert b["plus_due_today_resolves_after_equals_as_of"] == 1
    assert b["equals"] == b["GRADE_OWED"] == r["GRADE_OWED"] and b["reconciles"] is True
    assert rec["window_closed_not_due"]["n"] == 1
    assert rec["window_closed_not_due"]["waiting_for"] == {"resolver_date": 1}


def test_a_backwards_state_move_is_refused_with_the_ids_unless_allowed(tmp_path, capsys):
    from scripts import forecast_expiry as CLI
    root, led = _fixture(tmp_path)
    out = tmp_path / "out"
    t0 = pd.Timestamp("2026-01-01T00:00Z").to_pydatetime()
    FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0)
    side_before = _sha(FE.expiry_path(out))
    # the graded row loses its outcome and the voided row its void: both would move backwards
    lines = led.read_bytes().splitlines()
    g1, v1 = json.loads(lines[0]), json.loads(lines[1])
    g1.update(outcome=None, brier=None, resolved_at=None)
    v1.update(void_reason=None)
    lines[0], lines[1] = json.dumps(g1).encode(), json.dumps(v1).encode()
    led.write_bytes(b"\n".join(lines) + b"\n")
    with pytest.raises(FE.ForecastExpiryRegress) as ei:
        FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0 + timedelta(hours=1))
    assert {m["forecast_id"] for m in ei.value.moves} == {"g1", "v1"}
    assert {(m["from"], m["to"]) for m in ei.value.moves} == {(FE.EXPIRED_GRADED, FE.GRADE_OWED),
                                                             (FE.VOID, FE.GRADE_OWED)}
    assert all(m["row_sha256_changed"] for m in ei.value.moves)
    assert _sha(FE.expiry_path(out)) == side_before             # nothing appended
    refused = list((out / "forecast_expiry").glob("regress_refused_*.json"))
    assert len(refused) == 1 and json.loads(refused[0].read_text(encoding="utf-8"))["n"] == 2
    rc = CLI.main(["sweep", "--data-root", str(root), "--out", str(out), "--as-of", AS_OF.isoformat(),
                   "--no-campaign"])
    printed = capsys.readouterr().out
    assert rc == 3 and "g1" in printed and "v1" in printed and "EXPIRED_GRADED -> GRADE_OWED" in printed
    assert _sha(FE.expiry_path(out)) == side_before
    ok = FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0 + timedelta(hours=2), allow_regress=True)
    assert ok["side_ledger"]["regress_n"] == 2 and ok["side_ledger"]["rows_appended"] == 2
    tail = [json.loads(x) for x in FE.expiry_path(out).read_text(encoding="utf-8").splitlines()[-2:]]
    assert all(t["regress"] is True and t["prev_row_sha256"] and "state" in t["changes"] for t in tail)


def test_an_as_of_earlier_than_the_side_ledgers_newest_entry_is_refused(tmp_path):
    from scripts import forecast_expiry as CLI
    root, _ = _fixture(tmp_path)
    out = tmp_path / "out"
    t0 = pd.Timestamp("2026-01-01T00:00Z").to_pydatetime()
    FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0)
    before = _sha(FE.expiry_path(out))
    earlier = AS_OF - timedelta(days=22)
    with pytest.raises(FE.ForecastExpiryRefused) as ei:
        FE.sweep(data_root=root, out_dir=out, as_of=earlier, now=t0 + timedelta(hours=1))
    assert not isinstance(ei.value, FE.ForecastExpiryRegress) and AS_OF.isoformat() in str(ei.value)
    assert CLI.main(["sweep", "--data-root", str(root), "--out", str(out), "--as-of", earlier.isoformat(),
                     "--no-campaign"]) == 2
    assert _sha(FE.expiry_path(out)) == before
    # a fresh --out has no history to contradict: the same early date is accepted there
    assert FE.sweep(data_root=root, out_dir=tmp_path / "fresh", as_of=earlier, now=t0)["as_of"] == earlier.isoformat()
    # with the override the backwards rows are appended, each one flagged
    rec = FE.sweep(data_root=root, out_dir=out, as_of=earlier, now=t0 + timedelta(hours=2), allow_regress=True)
    assert rec["side_ledger"]["regress_n"] >= 1
    assert {m["to"] for m in rec["side_ledger"]["regress"]} <= {FE.ACTIVE, FE.WINDOW_CLOSED_NOT_DUE}


def test_a_changed_row_sha256_alone_is_recorded(tmp_path):
    root, led = _fixture(tmp_path)
    out = tmp_path / "out"
    t0 = pd.Timestamp("2026-01-01T00:00Z").to_pydatetime()
    FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0)
    lines = led.read_bytes().splitlines()
    a1 = json.loads(lines[4])
    assert a1["prediction_id"] == "a1"
    old_sha = hashlib.sha256(lines[4]).hexdigest()
    a1["probability"] = 0.9                                     # the frozen row's bytes moved; its state did not
    lines[4] = json.dumps(a1).encode()
    led.write_bytes(b"\n".join(lines) + b"\n")
    rec = FE.sweep(data_root=root, out_dir=out, as_of=AS_OF, now=t0 + timedelta(hours=1))
    assert rec["side_ledger"]["rows_appended"] == 1
    assert rec["side_ledger"]["appended_row_sha256_changed_only"] == 1 and rec["side_ledger"]["regress_n"] == 0
    last = json.loads(FE.expiry_path(out).read_text(encoding="utf-8").splitlines()[-1])
    assert last["forecast_id"] == "a1" and last["changes"] == ["row_sha256"]
    assert last["prev_row_sha256"] == old_sha and last["row_sha256"] == hashlib.sha256(lines[4]).hexdigest()
    assert last["state"] == last["prev_state"] == FE.ACTIVE


def test_a_non_us_ticker_gets_no_us_valid_until(tmp_path):
    sessions = FE.session_calendar(date(2025, 6, 2), date(2026, 6, 30))
    assert FE.is_foreign_ticker("005930.KS") and FE.is_foreign_ticker("7011.T")
    assert not FE.is_foreign_ticker("BRK-B") and not FE.is_foreign_ticker("DX-Y.NYB")
    assert not FE.is_foreign_ticker("AAA") and not FE.is_foreign_ticker("book:abc")
    r = _row("k", made_at="2025-12-01T15:00:00+00:00", h=21, ticker="005930.KS")
    v = FE.derive_valid_until(r, sessions)
    assert v["valid_until"] is None and v["basis"] == FE.BASIS_FOREIGN == "foreign_calendar_unverified"
    ra = date.fromisoformat(r["resolves_after"])
    c = FE.classify(r, as_of=ra - timedelta(days=1), sessions=sessions)
    assert c["state"] == FE.UNDATED and c["basis"] == FE.BASIS_FOREIGN and c["valid_until"] is None
    assert "foreign_calendar_unverified" in c["reason"]
    assert FE.classify(r, as_of=ra, sessions=sessions)["state"] == FE.GRADE_OWED   # the grader's date rule still binds
    us = FE.derive_valid_until(dict(r, ticker="AAA"), sessions)
    assert us["basis"] == "session_calendar" and us["valid_until"]
    root = tmp_path / "data" / "optimus"
    _write_ledger(root, [r, _row("u", made_at="2025-12-01T15:00:00+00:00", h=21)])
    _write_bars(root, {"AAA": (date(2025, 6, 2), date(2026, 1, 30))})
    rec = FE.sweep(data_root=root, out_dir=tmp_path / "out", as_of=ra - timedelta(days=1), write=False)
    assert rec["valid_until_basis_counts"] == {"foreign_calendar_unverified": 1, "session_calendar": 1}
    assert rec["foreign_calendar_unverified"]["n"] == 1 and rec["undated"]["n_foreign_calendar_unverified"] == 1
    assert rec["reconciliation"]["predictions"]["reconciles"]


def test_the_missing_session_count_in_a_waiting_note_is_derived_from_the_panel(tmp_path):
    root = tmp_path / "data" / "optimus"
    sess = FE.session_calendar(date(2025, 6, 2), date(2026, 1, 30))
    start = date(2025, 12, 1)
    in_window = [d for d in sess if d >= start]
    holes = set(in_window[3:11:2])                              # some sessions the ticker has no bar for
    recs = [{"symbol": "SPY", "date": pd.Timestamp(d), "close": 1.0} for d in sess]
    recs += [{"symbol": "GAPPY", "date": pd.Timestamp(d), "close": 1.0} for d in sess if d not in holes]
    (root / "prices_2025_26").mkdir(parents=True)
    pd.DataFrame(recs).to_parquet(root / "prices_2025_26" / "bars.parquet", index=False)
    panel = FE.load_panel(root, ["GAPPY", "SPY"])
    h = len(in_window) - 1                                      # needs every session of the window
    d = FE.disposition(_row("x", made_at="2025-12-01T15:00:00+00:00", h=h, ticker="GAPPY"),
                       as_of=date(2026, 3, 31), panel=panel)
    assert d["disposition"] == FE.WAITING_INPUT
    have = len(in_window) - len(holes)
    assert f"bars:GAPPY ({have} of the {h + 1} needed" in d["waiting_for"]
    assert f"the panel holds {len(in_window)} sessions" in d["waiting_for"]
    assert f"so {len(holes)} are missing for this ticker" in d["waiting_for"]


def test_the_label_report_says_how_many_books_the_step_down_really_tests():
    from backend.services import book_dna as BD
    p = BD.params()
    sessions = [d.isoformat() for d in FE.session_calendar(date(2025, 1, 2), date(2025, 12, 31))]

    def book(name, n, label, category="strategy"):
        return {"account": name, "category": category, "rule": None, "inception": sessions[0],
                "last_mark": sessions[n], "sessions_graded": n, "excess_pp": 3.0,
                "evidence": {"label": label, "why": "synthetic"},
                "_series": [(d, 0.002, 0.001) for d in sessions[1:n + 1]]}
    books = [book("young_early", 40, "EARLY_EVIDENCE"), book("young_twin", 30, "EARLY_EVIDENCE", "control"),
             book("young_observed", 10, "OBSERVED(10)"), book("old_early", 200, "EARLY_EVIDENCE"),
             book("old_observed", 150, "OBSERVED(150)")]
    rows = FE.label_stepdown(books, spy_sessions=sessions, p=p, n_trailing=63, vol_cut=0.2)
    cov = FE.stepdown_coverage(rows, n_trailing=63)
    assert (cov["n_books"], cov["n_whole_window"]) == (5, 3)
    assert (cov["n_above_observed"], cov["n_above_observed_whole_window"], cov["n_really_tested"]) == (3, 2, 1)
    assert cov["really_tested"] == ["old_early"] and cov["n_above_observed_not_a_strategy_book"] == 1
    assert "tests 1 book" in cov["statement"] and "3 of 5 books are younger than the 63-session" in cov["statement"]
