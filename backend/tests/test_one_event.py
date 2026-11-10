"""CH-31 one event end to end: synthetic event, offline, no network, no LLM."""
from __future__ import annotations

import json
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend.services import one_event as OE

ACC = "0001234567-26-000123"
URL = "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000123/ex99-1.htm"
SECRET_ACCOUNT = "PA-SYNTHETIC-ACCOUNT-0000"


def _sessions(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture
def world(tmp_path: Path):
    """A data root whose clock is derived from a fixed synthetic Monday."""
    root = tmp_path / "optimus"
    now = datetime(2030, 3, 4, 15, 0, tzinfo=timezone.utc)          # Monday, US session open
    pub = now - timedelta(hours=3)
    corpus = root / "news_corpus" / "sec_edgar_8k_ex99_body"
    corpus.mkdir(parents=True)
    row = {"source": "sec_edgar_8k_ex99_body", "published_utc": pub.isoformat(),
           "first_seen_utc": (pub + timedelta(minutes=40)).isoformat(),
           "url": URL, "title": "8-K - Heldco Inc. - EX-99.1", "raw_id": f"{ACC}:ex99-1.htm",
           "body": "Heldco reports fourth quarter financial results; revenue fell.",
           "tickers": ["HELD"], "entity_tags": ["8-K:2.02", f"accession:{ACC}"],
           "pit_grade": "native_stamp"}
    (corpus / f"{now.date()}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    pc = root / "pc_book"
    pc.mkdir(parents=True)
    snap = {"t": (now - timedelta(hours=1)).isoformat(), "account_number": SECRET_ACCOUNT,
            "equity": 100000.0, "positions": [
                {"symbol": "HELD", "qty": 10, "market_value": 5000.0},
                {"symbol": "PEER", "qty": 10, "market_value": 3000.0}]}
    (pc / "state_latest.json").write_text(json.dumps(snap), encoding="utf-8")
    funnel = tmp_path / "funnel_night10.json"
    funnel.write_text(json.dumps({"generated_at": (now - timedelta(days=2)).isoformat(),
                                  "candidates": [{"ticker": "OTHER"}]}), encoding="utf-8")
    # bars: ten sessions BEFORE now and eight after (the future is only read by the grader)
    days = _sessions(now.date() - timedelta(days=14), 18)
    rows = []
    for i, d in enumerate(days):
        rows += [{"symbol": "SPY", "date": pd.Timestamp(d), "close": 100.0 + i * 0.1},
                 {"symbol": "HELD", "date": pd.Timestamp(d), "close": 50.0 - (i * 0.5 if d > now.date() else 0)},
                 {"symbol": "PEER", "date": pd.Timestamp(d), "close": 20.0}]
    (root / "prices_2025_26").mkdir()
    pd.DataFrame(rows).to_parquet(root / "prices_2025_26" / "bars.parquet")
    return {"root": root, "now": now, "funnel": funnel, "out": tmp_path / "out", "row": row}


def _typed(world, sentiment: float) -> None:
    p = world["root"] / "news_corpus" / "_digest_cache"
    p.mkdir(parents=True)
    (p / "extract_wd_v1.jsonl").write_text(json.dumps({"cache_key": "k", "row": {
        "url": URL, "sentiment": sentiment, "tickers": ["HELD"], "event_type": "earnings",
        "extract_model": "deepseek:synthetic"}}) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def no_graph(monkeypatch):
    monkeypatch.setattr(OE, "_graph_module", lambda: (None, "ImportError: synthetic absence"))


def _run(world, **kw):
    return OE.run_one(data_root=world["root"], source="sec_edgar_8k_ex99_body", key=ACC,
                      now=world["now"], out_dir=world["out"], funnel_path=world["funnel"], **kw)


def _stage(rec, name):
    return next(s for s in rec["stages"] if s["name"] == name)


def test_chain_with_typed_direction_and_held_earnings(world):
    _typed(world, -0.6)
    rec = _run(world)
    assert [s["name"] for s in rec["stages"]] == list(OE.STAGES)
    assert _stage(rec, "SENSE")["status"] == OE.SUCCESS
    assert _stage(rec, "SENSE")["data"]["direction"] == -1
    assert _stage(rec, "SENSE")["data"]["direction_source"] == "typed_digest_row"
    u = _stage(rec, "UNIVERSE")
    assert u["status"] == OE.DEGRADED and u["reason"].startswith("GRAPH_MODULE_ABSENT")
    d = _stage(rec, "DECIDE")
    assert d["status"] == OE.SUCCESS
    assert d["data"]["owner_warning"]["status"] == "PROVISIONAL"
    assert "OWNER_WARNING_DRAFT" in d["data"]["actions"] and "NO_TRADE_REASONED" in d["data"]["actions"]
    a = _stage(rec, "ACT")
    assert a["status"] == OE.BLOCKED and a["intended_block"]
    assert all(i["sent"] is False for i in a["data"]["intents"])
    assert rec["exit_code"] == 0 and rec["red_stages"] == []
    assert set(rec["chain"]) == set(OE.STAGES) and all(rec["chain"].values())
    assert SECRET_ACCOUNT not in json.dumps(rec)


def test_untyped_direction_is_degraded_not_guessed(world):
    rec = _run(world)
    s = _stage(rec, "SENSE")
    assert s["status"] == OE.DEGRADED and "DIRECTION_UNTYPED" in s["reason"]
    assert s["data"]["direction"] is None
    learn = _stage(rec, "LEARN")
    assert "NO_DIRECTIONAL_CLAIM" in learn["reason"]


def test_missing_event_is_red(world):
    rec = OE.run_one(data_root=world["root"], source="sec_edgar_8k_ex99_body", key="nope",
                     now=world["now"], out_dir=world["out"], funnel_path=world["funnel"])
    assert _stage(rec, "SENSE")["status"] == OE.BLOCKED
    assert rec["exit_code"] == 2 and "SENSE" in rec["red_stages"]


def test_future_timestamp_is_refused(world):
    early = world["now"] - timedelta(hours=6)                        # before the filing
    rec = OE.run_one(data_root=world["root"], source="sec_edgar_8k_ex99_body", key=ACC,
                     now=early, out_dir=world["out"], funnel_path=world["funnel"])
    assert _stage(rec, "SENSE")["reason"] == "NO_VALID_PUBLIC_TIMESTAMP"
    assert rec["exit_code"] == 2


def test_stale_positions_degrade_decide(world):
    later = world["now"] + timedelta(hours=30)
    rec = OE.run_one(data_root=world["root"], source="sec_edgar_8k_ex99_body", key=ACC,
                     now=later, out_dir=world["out"], funnel_path=world["funnel"])
    d = _stage(rec, "DECIDE")
    assert d["status"] == OE.DEGRADED and "POSITIONS_STALE" in d["reason"]
    assert d["data"]["owner_warning"]["status"] == "REFUSED"


def test_forecasts_frozen_once_and_graded_on_bars(world):
    _typed(world, -0.6)
    rec = _run(world)
    learn = _stage(rec, "LEARN")
    assert learn["status"] == OE.SUCCESS and learn["data"]["n_new"] == 2
    again = _run(world)
    assert _stage(again, "LEARN")["data"]["n_new"] == 0
    fpath = world["out"] / "forecasts.jsonl"
    rows = [json.loads(x) for x in fpath.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and {r["horizon_sessions"] for r in rows} == {1, 5}
    assert all(r["made_at"] == world["now"].isoformat(timespec="seconds") for r in rows)
    res = OE.grade(fpath, data_root=world["root"], now=world["now"] + timedelta(days=14))
    assert res["counts"]["graded"] == 2
    g = {x["horizon_sessions"]: x for x in res["new_grades"]}
    # entry = the close of the session the forecast was made in (16:00 NY >= made_at)
    assert g[1]["entry_date"] == str(world["now"].date())
    assert g[1]["market_adjusted"] < 0 and g[1]["hit"] is True
    assert OE.grade(fpath, data_root=world["root"], now=world["now"])["counts"]["already"] == 2


def test_grade_pending_when_bars_end(world):
    _typed(world, 0.5)
    _run(world)
    bars = world["root"] / "prices_2025_26" / "bars.parquet"
    df = pd.read_parquet(bars)
    df[df["date"] <= pd.Timestamp(world["now"].date())].to_parquet(bars)
    res = OE.grade(world["out"] / "forecasts.jsonl", data_root=world["root"], now=world["now"])
    assert res["counts"]["pending"] == 2 and res["counts"]["graded"] == 0


def test_entry_session_respects_close_clock():
    d1, d2 = date(2030, 3, 4), date(2030, 3, 5)
    before_close = datetime(2030, 3, 4, 20, 30, tzinfo=timezone.utc)   # 15:30 EST
    after_close = datetime(2030, 3, 4, 21, 30, tzinfo=timezone.utc)    # 16:30 EST
    assert OE.entry_session(before_close, [d1, d2]) == d1
    assert OE.entry_session(after_close, [d1, d2]) == d2


def test_graph_lights_up_when_module_present(world, monkeypatch):
    _typed(world, -0.6)

    class Imp:
        def __init__(self, target, h):
            self.target, self.h = target, h

        def to_dict(self):
            return {"target": self.target, "target_type": "company", "horizon": self.h,
                    "expected_direction": -1, "expected_size": -0.01,
                    "confidence_label": "MEDIUM", "path": ["company:HELD", self.target], "n": 30}

    g = types.SimpleNamespace(nodes={"company:HELD": 1, "company:PEER": 1}, as_of="2030-03-01")
    fake = types.SimpleNamespace(
        status=lambda d, now=None: {"status": "OK", "red": False, "as_of": "2030-03-01",
                                    "age_days": 3, "dir": str(d), "line": "ok"},
        load_graph=lambda d: g, company_id=lambda s: f"company:{s}",
        propagate=lambda graph, ev: [Imp("company:PEER", 1), Imp("company:PEER", 5)],
        holdings_exposure=lambda graph, held, evs: [
            {"ticker": "PEER", "horizon": 1, "expected_direction": -1, "expected_size": -0.01,
             "confidence_label": "MEDIUM", "path": ["company:HELD", "company:PEER"]}],
        owner_warnings=lambda graph, held, evs, min_label="MEDIUM": [{"text": "PEER: adverse"}],
        funnel_candidates=lambda graph, evs, **kw: [])
    monkeypatch.setattr(OE, "_graph_module", lambda: (fake, None))
    rec = _run(world, graph_dir=world["root"] / "universe_graph")
    u = _stage(rec, "UNIVERSE")
    assert u["status"] == OE.SUCCESS and u["data"]["connected"][0]["target"] == "company:PEER"
    d = _stage(rec, "DECIDE")
    assert d["data"]["held_connected"][0]["ticker"] == "PEER"
    assert "OWNER_WARNING_DRAFT_CONNECTED" in d["data"]["actions"]
    learn = _stage(rec, "LEARN")
    assert {r for r in learn["data"]["forecast_ids"]} and learn["data"]["n_rows"] == 4


def test_cli_exit_codes(world, capsys):
    from scripts import one_event as CLI
    args = ["run", "--data-root", str(world["root"]), "--source", "sec_edgar_8k_ex99_body",
            "--funnel", str(world["funnel"]), "--out", str(world["out"]),
            "--now", world["now"].isoformat()]
    assert CLI.main(args + ["--key", ACC]) == 0
    assert "ATTENDED_ACTIVATION_REQUIRED (intended)" in capsys.readouterr().out
    assert CLI.main(args + ["--key", "missing"]) == 2
    receipts = list((world["out"] / "receipts").glob("*.json"))
    assert len(receipts) == 2


def test_unverified_typed_ticker_gives_direction_but_degrades(world):
    p = world["root"] / "news_corpus" / "_digest_cache"
    p.mkdir(parents=True)
    (p / "extract_wd_v1.jsonl").write_text(json.dumps({"cache_key": "k", "row": {
        "url": URL, "sentiment": 0.4, "tickers": [], "tickers_unverified": ["HELD"],
        "event_type": "earnings"}}) + "\n", encoding="utf-8")
    s = _stage(_run(world), "SENSE")
    assert s["data"]["direction"] == 1 and s["status"] == OE.DEGRADED
    assert "TYPED_TICKER_UNVERIFIED" in s["reason"]
