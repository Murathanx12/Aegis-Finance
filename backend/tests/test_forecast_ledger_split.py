"""The forecast ledger split: monthly streams, the manifest chain, the migration.

Every test runs in `tmp_path`. The real `predictions.jsonl` is never written by
this suite: the only thing ever run against it is `scripts.ledger_split --plan`,
by hand, and that writes nothing. Months are derived from today's UTC month
(protocol item 5): "three months ago" is always closed and past the seal grace,
"this month" is always open.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import belief_state as B
from backend.services import forecast_ledger as FL
from backend.services import forecast_ledger_migration as MIG

NOW = datetime.now(timezone.utc)


def _month_start(back: int) -> datetime:
    y, m = NOW.year, NOW.month - back
    while m <= 0:
        m += 12
        y -= 1
    return datetime(y, m, 1, tzinfo=timezone.utc)


OLD = _month_start(3)          # closed, always past the grace period
MID = _month_start(2)          # closed, always past the grace period
CUR = _month_start(0)          # the open month


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _new14(pid_seed: str, made: datetime, **kw) -> dict:
    """A 1.4.0 row exactly as `make_prediction` writes it."""
    base = dict(ticker="AAA", specialist=f"spec:{pid_seed}",
                observable=B.Observable.RETURN_SIGN, horizon_days=5,
                probability=0.6, thesis=f"t {pid_seed}", counter_thesis="c",
                next_observable="n", model="m", model_version="v", prompt="p",
                input_snapshot={"seed": pid_seed}, made_at=_iso(made))
    base.update(kw)
    return asdict(B.make_prediction(**base))


V100_KEYS = ["prediction_id", "ticker", "specialist", "observable", "horizon_days",
             "probability", "threshold", "benchmark", "made_at", "resolves_after", "thesis",
             "counter_thesis", "next_observable", "model", "model_version", "prompt_hash",
             "input_snapshot_hash", "schema_version", "resolved_at", "outcome", "brier",
             "resolution_detail"]


def _old100(pid: str, made: datetime) -> dict:
    """A 1.0.0 row in the real file's key order (the M1 fields do not exist)."""
    vals = {"prediction_id": pid, "ticker": "BBB", "specialist": "biotech",
            "observable": "return_sign", "horizon_days": 60, "probability": 0.55,
            "threshold": None, "benchmark": None, "made_at": _iso(made),
            "resolves_after": (made + timedelta(days=90)).date().isoformat(),
            "thesis": "x", "counter_thesis": "y", "next_observable": "z",
            "model": "deepseek-chat", "model_version": "v4", "prompt_hash": "p" * 16,
            "input_snapshot_hash": "i" * 16, "schema_version": "1.0.0",
            "resolved_at": None, "outcome": None, "brier": None, "resolution_detail": {}}
    return {k: vals[k] for k in V100_KEYS}


def _resolve_like_the_resolver(row: dict, day: datetime, outcome: int = 1,
                               benchmark: bool = False) -> dict:
    """What `resolve_one` does to a row, key order included (in place on old
    keys, APPENDED for keys a 1.0.0 row never had)."""
    r = dict(row)
    r["outcome"] = outcome
    r["resolved_at"] = day.date().isoformat()
    r["brier"] = float((r["probability"] - outcome) ** 2)
    if benchmark:
        r["vs_benchmark"] = 0.012
    r["calibration_bucket"] = B.calibration_bucket_of(r["probability"])
    r["resolution_detail"] = {"realised_return": 0.03, "n_bars": 6}
    return r


def _void(row: dict, when: datetime | None, reason: str = "UNRESOLVABLE_DELISTED: x") -> dict:
    r = dict(row)
    r["void_reason"] = reason
    if when is not None:
        r["voided_at"] = _iso(when)
        r["voided_by"] = "forecast_grader.void_unresolvable"
    return r


def _legacy_rows() -> list[dict]:
    r1 = _new14("open-old", OLD + timedelta(days=2))
    r2 = _resolve_like_the_resolver(_new14("res-old", OLD + timedelta(days=3)),
                                    MID + timedelta(days=4))
    r3 = _resolve_like_the_resolver(_old100("v100resolved0001", OLD + timedelta(days=4)),
                                    MID + timedelta(days=5), outcome=0)
    r4 = _void(_old100("v100voided000002", OLD + timedelta(days=5)), MID + timedelta(days=6))
    r5 = _void(_old100("v100undated00003", OLD + timedelta(days=6)), None,
               reason="threshold given in percent")
    r6 = _resolve_like_the_resolver(
        _new14("bench-mid", MID + timedelta(days=1), observable=B.Observable.BEATS_BENCHMARK,
               benchmark="SPY"), CUR, benchmark=True)
    r7 = _new14("open-cur", CUR + timedelta(hours=1))
    return [r1, r2, r3, r4, r5, r6, r7]


def _write_legacy(path: Path, rows: list[dict], *, crlf: bool = True) -> bytes:
    nl = "\r\n" if crlf else "\n"
    data = (nl.join(json.dumps(r, ensure_ascii=False) for r in rows) + nl).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


@pytest.fixture
def ledger(tmp_path) -> Path:
    p = tmp_path / "optimus" / "predictions.jsonl"
    _write_legacy(p, _legacy_rows())
    return p


def _apply(p: Path) -> dict:
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    return MIG.apply(p, expect_sha256=sha, now=NOW, history=False)


def _m(dt: datetime) -> str:
    return f"{dt:%Y-%m}"


# ─────────────────────────────── the split ───────────────────────────────────

def test_split_round_trip_preserves_every_row_its_order_and_its_hash(ledger):
    before = B.read_predictions(ledger)
    res = _apply(ledger)
    assert res["status"] == "APPLIED", res
    after = B.read_predictions(ledger)
    assert after == before                                  # dict-equal, in order
    assert [list(r) for r in after] == [list(r) for r in before]   # key order too
    assert ([FL.canonical_row_hash(r) for r in after]
            == [FL.canonical_row_hash(r) for r in before])


def test_frozen_fields_are_identical_and_only_resolution_fields_move(ledger):
    rows = B.read_predictions(ledger)
    for row in rows:
        forecast, event = MIG.split_row(row)
        assert MIG._frozen(forecast) == MIG._frozen(row)
        if event is None:
            assert forecast == row
        else:
            assert set(event["set"]) <= FL.RESOLUTION_KEYS
            folded = dict(forecast)
            folded.update(event["set"])
            assert folded == row and list(folded) == list(row)


def test_a_graded_1_0_0_row_splits_back_into_the_shape_it_was_made_in(ledger):
    """The resolver APPENDED `calibration_bucket` to a 1.0.0 row; the forecast
    half drops it, the event carries it, and the fold puts it back last."""
    row = next(r for r in B.read_predictions(ledger) if r["prediction_id"] == "v100resolved0001")
    forecast, event = MIG.split_row(row)
    assert list(forecast) == V100_KEYS
    assert forecast["outcome"] is None and forecast["resolution_detail"] == {}
    assert event["event"] == "resolve" and event["set"]["outcome"] == 0
    assert list(event["set"])[-1] == "calibration_bucket"
    assert event["month_basis"] == "resolved_at" and event["_month"] == _m(MID)


def test_voids_file_by_voided_at_and_an_undated_void_says_so(ledger):
    rows = {r["prediction_id"]: r for r in B.read_predictions(ledger)}
    f4, e4 = MIG.split_row(rows["v100voided000002"])
    assert "voided_at" not in f4 and "voided_by" not in f4 and f4["void_reason"] is None
    assert e4["event"] == "void" and e4["_month"] == _m(MID) and e4["month_basis"] == "voided_at"
    f5, e5 = MIG.split_row(rows["v100undated00003"])
    assert e5["_month"] == _m(OLD) and e5["month_basis"].startswith("made_at")


def test_streams_are_lf_only_and_open_rows_keep_the_legacy_bytes(ledger):
    legacy_lines = ledger.read_bytes().split(b"\r\n")
    _apply(ledger)
    root = ledger.parent
    raw = b"".join(p.read_bytes() for p in sorted((root / "forecasts").glob("*.jsonl"))
                   + sorted((root / "resolutions").glob("*.jsonl")))
    assert b"\r" not in raw
    open_old = next(ln for ln in legacy_lines if b"spec:open-old" in ln)
    assert open_old + b"\n" in (root / "forecasts" / f"forecasts_{_m(OLD)}.jsonl").read_bytes()


def test_forecasts_are_filed_by_made_month_and_events_by_recorded_month(ledger):
    _apply(ledger)
    root = ledger.parent
    names = sorted(p.name for p in (root / "forecasts").glob("*.jsonl"))
    assert names == sorted({f"forecasts_{_m(OLD)}.jsonl", f"forecasts_{_m(MID)}.jsonl",
                            f"forecasts_{_m(CUR)}.jsonl"})
    ev = sorted(p.name for p in (root / "resolutions").glob("*.jsonl"))
    assert ev == sorted({f"resolutions_{_m(OLD)}.jsonl", f"resolutions_{_m(MID)}.jsonl",
                         f"resolutions_{_m(CUR)}.jsonl"})


# ─────────────────────────────── the compatibility switch ────────────────────

def test_the_backend_is_legacy_before_and_streams_after_and_says_why(ledger):
    be = FL.backend_for(ledger)
    assert be.kind == "legacy" and "no migration marker" in be.reason
    assert FL.status(ledger)["backend"] == "legacy"
    _apply(ledger)
    be = FL.backend_for(ledger)
    assert be.kind == "streams" and be.marker["legacy_sha256"]
    d = be.describe()
    assert d["backend"] == "streams" and d["migrated_at_utc"] and d["legacy_sha256"]
    st = FL.status(ledger, rehash=True)
    assert st["status"] == "ok", st["problems"]
    assert st["legacy_frozen_intact"] is True
    assert B.ledger_health(ledger)["ledger_backend"]["backend"] == "streams"


def test_a_marker_for_another_file_leaves_this_file_legacy(ledger):
    _apply(ledger)
    other = ledger.parent / "leakage_probe_predictions.jsonl"
    other.write_text(json.dumps(_new14("probe", OLD)) + "\n", encoding="utf-8")
    assert FL.backend_for(other).kind == "legacy"
    assert len(B.read_predictions(other)) == 1


def test_an_unreadable_marker_refuses_rather_than_falling_back(ledger):
    _apply(ledger)
    FL.marker_path(ledger).write_text("{not json", encoding="utf-8")
    with pytest.raises(FL.ForecastLedgerError, match="Readers REFUSE"):
        B.read_predictions(ledger)
    FL.marker_path(ledger).write_text(json.dumps({"schema": "something/else"}), encoding="utf-8")
    with pytest.raises(FL.ForecastLedgerError, match="not a forecast_ledger_migration"):
        FL.backend_for(ledger)


def test_the_grader_receipt_names_the_backend_or_the_refusal(ledger):
    from backend.services import forecast_grader as FG
    assert FG._ledger_backend(ledger)["backend"] == "legacy"
    _apply(ledger)
    assert FG._ledger_backend(ledger)["backend"] == "streams"
    FL.marker_path(ledger).write_text("garbage", encoding="utf-8")
    assert FG._ledger_backend(ledger)["backend"] == "REFUSED"


def test_the_resolver_report_names_the_backend(tmp_path):
    p = tmp_path / "led.jsonl"
    B.append([B.make_prediction(ticker="AAA", specialist="s", observable=B.Observable.RETURN_SIGN,
                                horizon_days=5, probability=0.7, thesis="t", counter_thesis="c",
                                next_observable="n", model="m", model_version="v", prompt="p",
                                input_snapshot={"a": 1}, made_at="2025-02-03T00:00:00")], p)
    rep = B.resolve_all(_prices(), p)
    assert rep["ledger_backend"] == "legacy" and rep["newly_resolved"] == 1


# ─────────────────────────────── writing after the switch ────────────────────

def _prices(n=400):
    idx = pd.bdate_range("2025-01-01", periods=n)
    rng = np.random.default_rng(0)
    up = 100 * np.cumprod(1 + 0.002 + rng.normal(0, 0.005, n))
    return pd.DataFrame({"AAA": up, "SPY": np.linspace(100, 110, n)}, index=idx)


def test_appends_go_to_the_made_month_stream_and_never_touch_the_legacy_file(ledger):
    _apply(ledger)
    legacy_sha = hashlib.sha256(ledger.read_bytes()).hexdigest()
    rec = B.make_prediction(ticker="NEW", specialist="s", observable=B.Observable.RETURN_SIGN,
                            horizon_days=5, probability=0.7, thesis="t", counter_thesis="c",
                            next_observable="n", model="m", model_version="v", prompt="p",
                            input_snapshot={"n": 1}, made_at=_iso(CUR + timedelta(hours=2)))
    B.append([rec], ledger)
    B.append([rec], ledger)                         # the duplicate is refused by id
    rows = B.read_predictions(ledger)
    assert sum(1 for r in rows if r["prediction_id"] == rec.prediction_id) == 1
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == legacy_sha
    cur = (ledger.parent / "forecasts" / f"forecasts_{_m(CUR)}.jsonl").read_bytes()
    assert rec.prediction_id.encode() in cur and b"\r" not in cur


def test_a_late_forecast_for_a_sealed_month_is_filed_in_the_open_month(ledger):
    _apply(ledger)
    assert _m(OLD) in FL.sealed_months(FL.backend_for(ledger), "forecasts")
    late = _new14("late-restore", OLD + timedelta(days=9))
    out = FL.append_forecasts([late], ledger)
    assert out["late_filed"] == 1 and out["months"] == [_m(NOW)]
    sealed = (ledger.parent / "forecasts" / f"forecasts_{_m(OLD)}.jsonl").read_bytes()
    assert late["prediction_id"].encode() not in sealed
    assert FL.verify_chain(ledger)["status"] == "ok"
    assert any(r["prediction_id"] == late["prediction_id"] for r in B.read_predictions(ledger))


def test_resolve_all_after_the_switch_writes_events_and_no_forecast_bytes(tmp_path):
    p = tmp_path / "optimus" / "predictions.jsonl"
    old = _new14("grade-me", datetime(2025, 2, 3, tzinfo=timezone.utc), probability=0.9)
    _write_legacy(p, [old])
    _apply(p)
    f_before = {q.name: q.read_bytes() for q in (p.parent / "forecasts").glob("*.jsonl")}
    rep = B.resolve_all(_prices(), p)
    assert rep["newly_resolved"] == 1 and rep["ledger_backend"] == "streams"
    assert {q.name: q.read_bytes() for q in (p.parent / "forecasts").glob("*.jsonl")} == f_before
    events = (p.parent / "resolutions" / f"resolutions_{_m(NOW)}.jsonl").read_text().splitlines()
    ev = json.loads(events[-1])
    assert ev["event"] == "resolve" and ev["writer"] == "belief_state.resolve_all"
    assert ev["recorded_at"] and ev["set"]["outcome"] == 1
    row = B.read_predictions(p)[0]
    assert row["outcome"] == 1 and row["brier"] == pytest.approx(0.01)
    assert B.resolve_all(_prices(), p)["newly_resolved"] == 0          # first grade stands


def test_voids_after_the_switch_are_events_too(ledger):
    _apply(ledger)
    pid = _new14("open-cur", CUR + timedelta(hours=1))["prediction_id"]   # deterministic id
    row = {r["prediction_id"]: r for r in B.read_predictions(ledger)}[pid]
    assert row["outcome"] is None and not row.get("void_reason")
    voided = _void(row, NOW)
    out = FL.record_terminal(ledger, [(row, voided)], kind="void", writer="test")
    assert out == {"backend": "streams", "written": 1, "skipped_already_terminal": 0,
                   "month": _m(NOW)}
    again = {r["prediction_id"]: r for r in B.read_predictions(ledger)}[row["prediction_id"]]
    assert again["void_reason"] and again["voided_by"] == "forecast_grader.void_unresolvable"


# ─────────────────────────────── duplicates are a rule ───────────────────────

def test_the_first_terminal_event_wins_and_later_ones_are_counted(ledger):
    _apply(ledger)
    target = next(r for r in B.read_predictions(ledger) if r["outcome"] is not None)
    path = ledger.parent / "resolutions" / f"resolutions_{_m(NOW)}.jsonl"
    dup = {"schema": FL.EVENT_SCHEMA, "prediction_id": target["prediction_id"],
           "event": "resolve", "set": {"outcome": 1 - target["outcome"]},
           "recorded_at": _iso(NOW), "writer": "a second grader", "month_basis": "recorded_at"}
    orphan = dict(dup, prediction_id="no-such-forecast")
    with path.open("ab") as fh:                       # a hand edit, bypassing the writer
        fh.write(FL.row_line(dup) + FL.row_line(orphan))
    stats = FL.FoldStats()
    rows = {r["prediction_id"]: r for r in FL.read_rows(ledger, stats=stats)}
    assert rows[target["prediction_id"]]["outcome"] == target["outcome"]
    assert stats.duplicate_terminal_events == [target["prediction_id"]]
    assert stats.orphan_events == ["no-such-forecast"]


def test_the_writer_skips_a_second_terminal_event_and_refuses_an_orphan(ledger):
    _apply(ledger)
    row = next(r for r in B.read_predictions(ledger) if r["outcome"] is None
               and not r.get("void_reason"))
    ev = FL.make_event(row, _resolve_like_the_resolver(row, NOW), kind="resolve", writer="t")
    assert FL.append_events([ev], ledger)["written"] == 1
    assert FL.append_events([ev], ledger) == {"backend": "streams", "written": 0,
                                               "skipped_already_terminal": 1, "month": _m(NOW)}
    with pytest.raises(FL.ForecastLedgerError, match="no forecast stream holds"):
        FL.append_events([dict(ev, prediction_id="ghost")], ledger)


def test_an_event_may_not_rewrite_what_was_forecast(ledger):
    row = B.read_predictions(ledger)[0]
    bad = dict(row, probability=0.99, outcome=1)
    with pytest.raises(FL.ForecastLedgerError, match="frozen forecast field 'probability'"):
        FL.make_event(row, bad, kind="resolve", writer="t")
    with pytest.raises(FL.ForecastLedgerError, match="delete"):
        FL.make_event(row, {k: v for k, v in row.items() if k != "thesis"},
                      kind="resolve", writer="t")


def test_a_torn_tail_is_refused_not_glued(ledger):
    _apply(ledger)
    cur = ledger.parent / "forecasts" / f"forecasts_{_m(NOW)}.jsonl"
    with cur.open("ab") as fh:
        fh.write(b'{"prediction_id": "half')
    with pytest.raises(FL.ForecastLedgerError, match="torn append"):
        FL.append_forecasts([_new14("after-tear", NOW)], ledger)


# ─────────────────────────────── the manifest chain ──────────────────────────

def test_closed_months_are_sealed_in_chain_order_and_genesis_carries_the_break(ledger):
    res = _apply(ledger)
    sealed = [(s["stream"], s["month"]) for s in res["sealed"]]
    assert sealed == [("forecasts", _m(OLD)), ("resolutions", _m(OLD)),
                      ("forecasts", _m(MID)), ("resolutions", _m(MID))]
    mdir = FL.manifest_dir_for(ledger)
    mans = [json.loads((mdir / f"{s}_{m}.json").read_text()) for s, m in sealed]
    assert mans[0]["genesis"] is True and mans[0]["prev_manifest_sha256"] is None
    lcb = mans[0]["legacy_chain_break"]
    assert lcb["status"] == "NO_ROW_CHAIN" and lcb["first_mismatch_line"] is None
    assert "NOT being repaired" in lcb["statement_not_repaired"]
    assert "restarts at this manifest chain" in lcb["statement_restart"]
    assert lcb["source_sha256"] == hashlib.sha256(ledger.read_bytes()).hexdigest()
    for prev, man in zip(mans, mans[1:]):
        assert man["prev_manifest_sha256"] == prev["manifest_sha256"]
    for man in mans:
        assert FL.manifest_hash(man) == man["manifest_sha256"]
    assert f"forecasts_{_m(CUR)}" not in {f"{s}_{m}" for s, m in sealed}   # open month
    assert FL.verify_chain(ledger)["status"] == "ok"


def test_a_changed_sealed_stream_breaks_the_chain_and_refuses_the_next_seal(ledger):
    _apply(ledger)
    f = ledger.parent / "forecasts" / f"forecasts_{_m(OLD)}.jsonl"
    data = bytearray(f.read_bytes())
    data[10] = ord("X") if data[10] != ord("X") else ord("Y")      # same size, one byte
    f.write_bytes(bytes(data))
    v = FL.verify_chain(ledger)
    assert v["status"] == "BROKEN" and any("a SEALED month changed" in p for p in v["problems"])
    assert FL.status(ledger, rehash=True)["status"] == "DEGRADED"
    with pytest.raises(FL.SealRefused, match="does not verify"):
        FL.seal_closed(ledger, now=NOW, apply=True)


def test_a_missing_or_wrong_predecessor_refuses_the_seal(ledger):
    _apply(ledger)
    mdir = FL.manifest_dir_for(ledger)
    (mdir / f"forecasts_{_m(OLD)}.json").unlink()            # remove genesis
    v = FL.verify_chain(ledger)
    assert v["status"] == "BROKEN"
    assert any("prev_manifest_sha256" in p for p in v["problems"])
    with pytest.raises(FL.SealRefused):
        FL.seal_closed(ledger, now=NOW, apply=True)


def test_an_edited_manifest_is_caught(ledger):
    _apply(ledger)
    mp = FL.manifest_dir_for(ledger) / f"resolutions_{_m(MID)}.json"
    man = json.loads(mp.read_text())
    man["rows"] += 1
    mp.write_text(json.dumps(man))
    assert any("edited after sealing" in p for p in FL.verify_chain(ledger)["problems"])


def test_a_month_inside_its_grace_period_is_not_sealed(tmp_path):
    prev_month_end = CUR - timedelta(hours=1)
    p = tmp_path / "optimus" / "predictions.jsonl"
    _write_legacy(p, [_new14("edge", prev_month_end)])
    within = CUR + timedelta(hours=6)                        # grace is a whole day
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert MIG.apply(p, expect_sha256=sha, now=within, history=False)["sealed"] == []
    plan = FL.seal_closed(p, now=within, apply=False)
    assert plan["would_seal"] == []
    after = FL.seal_closed(p, now=CUR + timedelta(days=2), apply=False)
    assert [w["month"] for w in after["would_seal"]] == [_m(prev_month_end)]


def test_an_unsealed_month_before_the_chain_tail_is_refused(ledger):
    _apply(ledger)
    stray = ledger.parent / "forecasts" / f"forecasts_{_m(_month_start(5))}.jsonl"
    stray.write_bytes(FL.row_line(_new14("stray", _month_start(5))))
    assert any("before the chain tail" in p for p in FL.verify_chain(ledger)["problems"])
    with pytest.raises(FL.SealRefused):
        FL.seal_closed(ledger, now=NOW, apply=True)


# ─────────────────────────────── the migration command ───────────────────────

def test_the_plan_writes_nothing_and_carries_the_chain_break(ledger):
    before = sorted(p.relative_to(ledger.parent) for p in ledger.parent.rglob("*"))
    plan = MIG.plan(ledger, now=NOW)
    after = sorted(p.relative_to(ledger.parent) for p in ledger.parent.rglob("*"))
    assert before == after
    assert plan["status"] == "READY" and plan["writes"] == "none"
    assert plan["source"]["sha256"] == hashlib.sha256(ledger.read_bytes()).hexdigest()
    assert plan["source"]["crlf_lines"] == 7
    assert plan["verification"]["ok"] and plan["verification"]["fold_equals_legacy"] == 7
    assert plan["legacy_chain_break"]["status"] == "NO_ROW_CHAIN"
    assert "prompt_hash" in plan["legacy_chain_break"]["hash_fields_present"]
    assert plan["manifest_plan"]["genesis"] == f"forecasts_{_m(OLD)}"
    assert plan["next"].endswith(plan["source"]["sha256"])
    text = MIG.render_plan(plan)
    assert plan["source"]["sha256"] in text and "NO_ROW_CHAIN" in text


def test_apply_refuses_without_a_fingerprint_and_writes_nothing(ledger):
    with pytest.raises(FL.MigrationRefused, match="source fingerprint"):
        MIG.apply(ledger, expect_sha256=None, now=NOW, history=False)
    assert not FL.marker_path(ledger).exists()
    assert not (ledger.parent / "forecasts").exists()


def test_apply_refuses_when_the_source_changed_after_the_plan(ledger):
    plan = MIG.plan(ledger, now=NOW)
    with ledger.open("ab") as fh:                 # a writer appended after the plan
        fh.write(json.dumps(_new14("after-plan", NOW)).encode() + b"\r\n")
    with pytest.raises(FL.MigrationRefused, match="changed since the plan"):
        MIG.apply(ledger, expect_sha256=plan["source"]["sha256"], now=NOW, history=False)
    assert FL.backend_for(ledger).kind == "legacy"
    assert not list((ledger.parent).rglob("forecasts_*.jsonl"))


def test_apply_against_a_saved_plan_file(ledger, tmp_path):
    plan = MIG.plan(ledger, now=NOW)
    pf = tmp_path / "plan.json"
    pf.write_text(json.dumps(plan, default=str), encoding="utf-8")
    assert MIG.apply(ledger, plan_file=pf, now=NOW, history=False)["status"] == "APPLIED"


def test_apply_is_idempotent_for_the_same_source_and_refuses_another(ledger):
    sha = hashlib.sha256(ledger.read_bytes()).hexdigest()
    assert MIG.apply(ledger, expect_sha256=sha, now=NOW, history=False)["status"] == "APPLIED"
    again = MIG.apply(ledger, expect_sha256=sha, now=NOW, history=False)
    assert again["status"] == "ALREADY_APPLIED" and again["writes"] == "none"
    with pytest.raises(FL.MigrationRefused, match="second application is refused"):
        MIG.apply(ledger, expect_sha256="0" * 64, now=NOW, history=False)


def test_apply_rolls_back_when_the_legacy_file_moves_during_the_apply(ledger, monkeypatch):
    sha = hashlib.sha256(ledger.read_bytes()).hexdigest()
    monkeypatch.setattr(MIG.FL, "sha256_file", lambda p: "f" * 64)
    with pytest.raises(FL.MigrationRefused, match="changed DURING the apply"):
        MIG.apply(ledger, expect_sha256=sha, now=NOW, history=False)
    monkeypatch.undo()
    assert not FL.marker_path(ledger).exists()
    assert not list(ledger.parent.rglob("forecasts_*.jsonl"))
    assert not list(ledger.parent.rglob("resolutions_*.jsonl"))
    assert FL.backend_for(ledger).kind == "legacy"


def test_an_interrupted_apply_is_refused_until_discarded(ledger):
    stray = ledger.parent / "forecasts" / f"forecasts_{_m(OLD)}.jsonl"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"{}\n")
    assert FL.status(ledger)["status"] == "DEGRADED"             # strays beside legacy
    sha = hashlib.sha256(ledger.read_bytes()).hexdigest()
    with pytest.raises(FL.MigrationRefused, match="interrupted --apply"):
        MIG.apply(ledger, expect_sha256=sha, now=NOW, history=False)
    assert MIG.discard_partial(ledger)["status"] == "DISCARDED"
    assert MIG.apply(ledger, expect_sha256=sha, now=NOW, history=False)["status"] == "APPLIED"
    with pytest.raises(FL.MigrationRefused, match="never discarded"):
        MIG.discard_partial(ledger)


def test_the_cli_plans_and_refuses_an_unfingerprinted_apply(ledger, capsys):
    from scripts import ledger_split as CLI
    assert CLI.main(["--plan", "--legacy", str(ledger)]) == 0
    out = capsys.readouterr().out
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() in out
    assert CLI.main(["--apply", "--legacy", str(ledger)]) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert CLI.main(["--status", "--legacy", str(ledger)]) == 0


# ─────────────────────────────── the remembered chain ────────────────────────

def test_a_ledger_without_chain_fields_is_reported_as_having_no_chain(ledger):
    rep = MIG.legacy_chain_report(ledger.read_bytes())
    assert rep["status"] == "NO_ROW_CHAIN"
    assert rep["chain_fields_found"] == {}
    assert rep["first_mismatch_line"] is None and rep["hash_found"] is None


def test_the_verifier_finds_the_actual_first_mismatch_in_a_chained_ledger():
    lines = []
    prev = None
    for i in range(8):
        row = {"prediction_id": f"p{i}", "v": i}
        if prev is not None:
            row["prev_hash"] = hashlib.sha256(prev).hexdigest()
        prev = json.dumps(row).encode()
        lines.append(prev)
    lines[3] = lines[3].replace(b'"v": 3', b'"v": 33')        # tamper line 4
    raw = b"\n".join(lines) + b"\n"
    rep = MIG.legacy_chain_report(raw)
    assert rep["status"] == "BROKEN" and rep["scheme"] == "prev_line_sha256"
    assert rep["first_mismatch_line"] == 5
    assert rep["previous_hash_expected"] == hashlib.sha256(lines[3]).hexdigest()
    assert rep["hash_found"] == json.loads(lines[4])["prev_hash"]
    assert rep["first_mismatch_prediction_id"] == "p4"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_git_history_replay_finds_the_first_byte_and_semantic_breaks(tmp_path):
    repo = tmp_path / "repo"
    led = repo / "backend" / "data" / "optimus" / "predictions.jsonl"
    rows = [_new14(f"h{i}", OLD + timedelta(days=i)) for i in range(4)]

    def git(*args):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", *args], cwd=repo, check=True,
                       capture_output=True)

    repo.mkdir()
    git("init", "-q")
    _write_legacy(led, rows[:2], crlf=False)
    git("add", "-A")
    git("commit", "-q", "-m", "v1")
    _write_legacy(led, rows[:3], crlf=False)                   # an append
    git("commit", "-q", "-am", "v2")
    _write_legacy(led, rows[:3], crlf=True)                    # a CRLF rewrite
    git("commit", "-q", "-am", "v3")
    rep = MIG.legacy_history_report(led, repo=repo)
    assert rep["status"] == "CONTINUOUS" and rep["versions"] == 3
    fb = rep["first_byte_discontinuity"]
    assert fb["line"] == 1 and "CR added" in fb["classification"]
    assert fb["previous_line_sha256"] != fb["found_line_sha256"]
    _write_legacy(led, [rows[0], rows[2], rows[3]], crlf=True)  # row h1 vanishes
    git("commit", "-q", "-am", "v4")
    rep = MIG.legacy_history_report(led, repo=repo)
    assert rep["status"] == "DISCONTINUOUS"
    assert rep["first_semantic_break"]["removed"] == 1


def test_history_outside_a_checkout_is_not_computed_and_says_why(ledger):
    rep = MIG.legacy_history_report(ledger, repo=ledger.parent / "nowhere")
    assert rep["status"] == "NOT_COMPUTED" and rep["reason"]


# ─────────────────────────────── the read surfaces ───────────────────────────

def test_logical_lines_and_tails_agree_with_the_folded_rows(ledger):
    before_lines = [json.loads(x) for x in FL.logical_lines(ledger)]
    _apply(ledger)
    folded = B.read_predictions(ledger)
    assert [json.loads(x) for x in FL.logical_lines(ledger)] == folded == before_lines
    tail = [json.loads(x) for x in FL.tail_lines(ledger, tail_bytes=10 ** 9)]
    assert [r["prediction_id"] for r in tail] == [r["prediction_id"] for r in folded]
    assert FL.row_count(ledger) == len(folded) == 7


def test_fingerprints_and_digests_move_when_a_backing_file_does(ledger):
    assert FL.content_digest(ledger) == hashlib.sha256(ledger.read_bytes()).hexdigest()
    _apply(ledger)
    fp, dg = FL.fingerprint(ledger), FL.content_digest(ledger)
    FL.append_forecasts([_new14("moves", NOW)], ledger)
    assert FL.fingerprint(ledger) != fp and FL.content_digest(ledger) != dg


def test_the_parquet_archiver_never_touches_a_stream_file(ledger):
    from backend.services import ledger_archive as LA
    _apply(ledger)
    f = ledger.parent / "forecasts" / f"forecasts_{_m(OLD)}.jsonl"
    with pytest.raises(LA.ArchiveRefused, match="manifest chain"):
        LA.archive_month(f, now=NOW, archive_dir=ledger.parent / "a",
                         manifest_dir=ledger.parent / "m")
    assert not any(c["path"].endswith(f.name) for c in LA.find_candidates(ledger.parent, now=NOW))


# ─────────────────────────────── the legacy path stays honest ────────────────

def test_a_legacy_rewrite_keeps_rows_appended_while_it_graded(tmp_path):
    p = tmp_path / "led.jsonl"
    rows = [_new14("a", OLD), _new14("b", OLD + timedelta(days=1))]
    _write_legacy(p, rows, crlf=False)
    graded = _resolve_like_the_resolver(rows[0], MID)
    late = _new14("c-late", OLD + timedelta(days=2))
    with p.open("a", encoding="utf-8") as fh:            # appended between read and write
        fh.write(json.dumps(late) + "\n")
    assert FL.legacy_rewrite(p, {graded["prediction_id"]: graded}) == 1
    after = {r["prediction_id"]: r for r in B.read_predictions(p)}
    assert set(after) == {rows[0]["prediction_id"], rows[1]["prediction_id"],
                          late["prediction_id"]}
    assert after[rows[0]["prediction_id"]]["outcome"] == 1
    assert not list(tmp_path.glob("led.jsonl.tmp*"))


def test_a_legacy_rewrite_never_regrades_a_terminal_row(tmp_path):
    p = tmp_path / "led.jsonl"
    first = _resolve_like_the_resolver(_new14("x", OLD), MID, outcome=1)
    _write_legacy(p, [first], crlf=False)
    second = dict(first, outcome=0)
    assert FL.legacy_rewrite(p, {first["prediction_id"]: second}) == 0
    assert B.read_predictions(p)[0]["outcome"] == 1


def test_the_legacy_file_is_never_rewritten_after_the_switch(ledger):
    _apply(ledger)
    row = B.read_predictions(ledger)[0]
    with pytest.raises(FL.ForecastLedgerError, match="frozen"):
        FL.legacy_rewrite(ledger, {row["prediction_id"]: dict(row, outcome=1)})


def test_the_lock_is_reentrant_for_the_holding_thread(tmp_path):
    with FL.ledger_lock(tmp_path):
        with FL.ledger_lock(tmp_path):
            pass
    with FL.ledger_lock(tmp_path, timeout_s=1):
        pass
