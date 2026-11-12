"""CH-13 discovery-failure autopsy on a small synthetic world.

Offline. Every date comes from a FIXED synthetic calendar (the first 150 XNYS
sessions of 2024), never from today. Every file lives under tmp_path.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import discovery_autopsy as DA
from backend.services import market_sessions as MS

SESSIONS = MS.sessions_in_year(2024)[:150]
D = SESSIONS[-1]
PREV = SESSIONS[-2]
OPEN = DA.session_open_utc(D)
PREV_CLOSE = MS.session_close_utc(PREV)

#: name -> residual on D (beta 1 to SPY, idiosyncratic sigma 1% unless noted)
SPECIAL = {"UPZ": 0.10, "UPK": 0.08, "UPLATE": 0.07,
           "DNNEW": -0.10, "DNF": -0.09, "DNC": -0.08}
UPRAW_SIGMA = 0.08          # a very volatile name: the largest RAW move, a small z
UPRAW_RESID = 0.12


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


def _at(day, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=timezone.utc)


def _bars() -> pd.DataFrame:
    rng = np.random.default_rng(13)
    n = len(SESSIONS)
    m = rng.normal(0.0, 0.01, n)
    m[-1] = 0.004
    rows = []

    def add(sym: str, rets: np.ndarray, start: int = 0) -> None:
        px = 50.0 * np.cumprod(1.0 + rets)
        for i in range(start, n):
            rows.append((sym, pd.Timestamp(SESSIONS[i]), float(px[i]), 1_000_000))

    add("SPY", m)
    for j in range(40):
        r = m + rng.normal(0.0, 0.01, n)
        r[-1] = m[-1] + rng.normal(0.0, 0.001)          # quiet on D: no accidental mover
        add(f"N{j:02d}", r)
    for sym, resid in SPECIAL.items():
        r = m + rng.normal(0.0, 0.01, n)
        r[-1] = m[-1] + resid
        add(sym, r, start=(n - 30 if sym == "DNNEW" else 0))
    r = m + rng.normal(0.0, UPRAW_SIGMA, n)
    r[-1] = m[-1] + UPRAW_RESID
    add("UPRAW", r)
    return pd.DataFrame(rows, columns=["symbol", "date", "close", "volume"])


def _jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


def _news(src: str, first_seen: datetime, title: str, tickers=(), tags=()) -> tuple:
    return (src, first_seen, {"source": src, "first_seen_utc": _iso(first_seen),
                              "published_utc": _iso(first_seen - timedelta(minutes=5)),
                              "title": title, "tickers": list(tickers),
                              "entity_tags": list(tags), "url": "https://example.invalid/x"})


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "AUTOPSY_MIN_NAMES_ON_DAY", 10)
    monkeypatch.setattr(C, "AUTOPSY_MIN_CORPUS_ROWS", 1)
    fr = tmp_path / "data"
    dr = fr / "optimus"
    (dr / "prices_2025_26").mkdir(parents=True)
    _bars().to_parquet(dr / "prices_2025_26" / "bars.parquet", index=False)

    _jsonl(dr / "predictions.jsonl", [
        {"prediction_id": "p1", "ticker": "DNF", "made_at": _iso(_at(D, 0) - timedelta(days=2)),
         "resolves_after": (D + timedelta(days=20)).isoformat(), "observable": "beats_benchmark",
         "probability": 0.3, "specialist": "test", "horizon_days": 20},
        # made AFTER the open: must not lift UPZ to FORECAST
        {"prediction_id": "p2", "ticker": "UPZ", "made_at": _iso(OPEN + timedelta(hours=1)),
         "resolves_after": (D + timedelta(days=20)).isoformat(), "observable": "beats_benchmark",
         "probability": 0.7},
        "not json at all",
    ])

    dec = dr / "decisions"
    dec.mkdir()
    (dec / f"{D.isoformat()}.json").write_text(json.dumps({
        "written_utc": _iso(PREV_CLOSE + timedelta(hours=1)),
        "rows": [{"ticker": "DNC", "direction": "LONG"}, {"ticker": "AGENCY_BOOK:X"}]}))
    # a contract file written AFTER D's open: its names are not "generated before"
    (dec / f"{PREV.isoformat()}.json").write_text(json.dumps({
        "written_utc": _iso(OPEN + timedelta(hours=2)), "rows": [{"ticker": "UPZ"}]}))

    (fr / "funnel_night10.json").write_text(json.dumps({
        "generated_at": _iso(OPEN - timedelta(days=3)), "candidates": [{"ticker": "N01"}]}))
    (fr / "funnel_history").mkdir()
    (fr / "funnel_history" / "funnel_after.json").write_text(json.dumps({
        "generated_at": _iso(OPEN + timedelta(hours=5)), "candidates": [{"ticker": "UPZ"}]}))

    dg = dr / "digest"
    dg.mkdir()
    stamp = (PREV_CLOSE + timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
    (dg / f"world_digest_{stamp}.json").write_text(json.dumps(
        {"themes": [{"title": "theme", "top_tickers": ["DNC"]}]}))

    items = [
        _news("wire", PREV_CLOSE + timedelta(hours=1), "macro filler"),
        _news("wire", PREV_CLOSE + timedelta(hours=2), "DNF guides lower", tickers=["DNF"]),
        _news("wire", OPEN + timedelta(minutes=30), "UPLATE soars", tickers=["UPLATE"]),
        _news("wire", PREV_CLOSE - timedelta(days=2), "DNC loses contract", tickers=["DNC"]),
        _news("sec_edgar_8k_current_atom", PREV_CLOSE + timedelta(hours=3), "8-K",
              tags=["8-K:2.02", "cik:0000012345"]),
        _news("wire", PREV_CLOSE + timedelta(hours=4), "UPZ quote page", tickers=["UPZ"],
              tags=[C.AUTOPSY_NOT_NEWS_TAGS[0]]),
    ]
    by_file: dict = {}
    for src, fs, row in items:
        by_file.setdefault((src, fs.date().isoformat()), []).append(row)
    for (src, day), rows in by_file.items():
        _jsonl(dr / "news_corpus" / src / f"{day}.jsonl", rows)
    (dr / "official").mkdir()
    (dr / "official" / "company_tickers.json").write_text(json.dumps(
        {"t": _iso(OPEN), "map": {"12345": "UPK"}}))
    out = tmp_path / "out"
    now = _at(D + timedelta(days=1), 2)
    return {"dr": dr, "fr": fr, "out": out, "now": now}


def _argv(w, *extra) -> list[str]:
    return ["--data-root", str(w["dr"]), "--out", str(w["out"]), "--now", _iso(w["now"]), *extra]


def _receipt(w) -> dict:
    return json.loads((w["out"] / f"autopsy_{D.isoformat()}.json").read_text(encoding="utf-8"))


def test_end_to_end_classifies_both_tails(world, capsys):
    before = sorted(p.relative_to(world["fr"]) for p in world["fr"].rglob("*"))
    assert DA.main(_argv(world)) == 0
    after = sorted(p.relative_to(world["fr"]) for p in world["fr"].rglob("*"))
    assert before == after, "the autopsy wrote into the data folder"
    rec = _receipt(world)
    assert rec["session"] == D.isoformat()
    by = {m["ticker"]: m for m in rec["movers"]}
    assert [m["ticker"] for m in rec["movers"] if m["side"] == "UP"] == ["UPZ", "UPK", "UPLATE"]
    assert {m["ticker"] for m in rec["movers"] if m["side"] == "DOWN"} == {"DNNEW", "DNF", "DNC"}
    assert "UPRAW" not in by, "a big raw move on a volatile name is not a big z"

    assert by["UPZ"]["ladder"] == DA.IN_UNIVERSE_NOT_CANDIDATE      # after-open forecast/contract/funnel ignored
    assert by["DNF"]["ladder"] == DA.FORECAST
    assert by["DNC"]["ladder"] == DA.CANDIDATE_NOT_FORECAST
    assert by["DNNEW"]["ladder"] == DA.NOT_IN_UNIVERSE
    assert by["DNC"]["attention"]["n_world_digest"] == 1

    assert by["UPK"]["knowable"]["state"] == DA.KNOWABLE_OVERNIGHT   # 8-K via the CIK map
    assert by["UPK"]["knowable"]["earliest"]["kind"] == "FILING"
    assert by["DNF"]["knowable"]["state"] == DA.KNOWABLE_OVERNIGHT
    assert by["DNC"]["knowable"]["state"] == DA.KNOWABLE_EARLIER
    assert by["UPLATE"]["knowable"]["state"] == DA.NO_HEADLINE_IN_CORPUS  # headline after the open
    assert by["UPZ"]["knowable"]["state"] == DA.NO_HEADLINE_IN_CORPUS     # a quote page is not news
    assert by["UPZ"]["knowable"]["reader_pages_before_open"] == 1

    s = rec["summary"]
    assert s["n_movers"] == 6 and s["by_side"] == {"UP": 3, "DOWN": 3}
    assert s["n_missed_but_knowable"] == 2                               # UPK, DNC
    assert s["n_unknown"] == 0
    for m in rec["movers"]:
        for e in m["knowable"]["evidence"]:
            assert datetime.fromisoformat(e["known_at"]) < OPEN
    assert rec["inputs"]["bars_panel"]["stale"] is False
    assert rec["candidate_set"]["n_funnel"] == 1
    assert rec["candidate_set"]["funnel_age_days_at_open"] == pytest.approx(3.0, abs=0.01)

    queue = [json.loads(x) for x in
             (world["out"] / "research_queue.jsonl").read_text().splitlines()]
    assert sorted(q["ticker"] for q in queue) == ["DNC", "UPK"]
    out = capsys.readouterr().out
    assert "MISSED BUT KNOWABLE 2" in out


def test_second_run_keeps_the_first_receipt_and_dedupes_the_queue(world):
    assert DA.main(_argv(world)) == 0
    world2 = {**world, "now": world["now"] + timedelta(minutes=5)}
    assert DA.main(_argv(world2)) == 0
    runs = sorted(world["out"].glob(f"autopsy_{D.isoformat()}_*.json"))
    assert len(runs) == 2
    assert len((world["out"] / "research_queue.jsonl").read_text().splitlines()) == 2


@pytest.mark.parametrize("rel,code", [
    ("optimus/prices_2025_26/bars.parquet", DA.PANEL_MISSING),
    ("optimus/predictions.jsonl", DA.LEDGER_MISSING),
    ("funnel_night10.json", DA.FUNNEL_MISSING),
    ("optimus/decisions", DA.DECISIONS_MISSING),
    ("optimus/digest", DA.DIGEST_MISSING),
    ("optimus/news_corpus", DA.CORPUS_MISSING),
    ("optimus/official/company_tickers.json", DA.CIK_MAP_MISSING),
])
def test_a_missing_input_is_a_named_nonzero_exit(world, capsys, rel, code):
    import shutil
    p = world["fr"] / rel
    shutil.rmtree(p) if p.is_dir() else p.unlink()
    assert DA.main(_argv(world)) == 2
    assert f"REFUSED {code}" in capsys.readouterr().err
    assert not world["out"].exists()


def test_out_inside_the_data_root_is_refused(world, capsys):
    argv = ["--data-root", str(world["dr"]), "--out", str(world["dr"] / "autopsy"),
            "--now", _iso(world["now"])]
    assert DA.main(argv) == 2
    assert "OUT_INSIDE_DATA_ROOT" in capsys.readouterr().err
    assert not (world["dr"] / "autopsy").exists()


def test_zero_movers_is_refused(world, monkeypatch, capsys):
    monkeypatch.setattr(C, "AUTOPSY_MIN_ABS_Z", 1000.0)
    assert DA.main(_argv(world)) == 2
    assert "NO_MOVERS" in capsys.readouterr().err


def test_thin_panel_is_refused(world, monkeypatch, capsys):
    monkeypatch.setattr(C, "AUTOPSY_MIN_NAMES_ON_DAY", 10_000)
    assert DA.main(_argv(world)) == 2
    assert "THIN_PANEL" in capsys.readouterr().err


def test_a_stale_panel_and_funnel_are_flagged_not_silent(world, capsys):
    late = {**world, "now": world["now"] + timedelta(days=30)}
    fn = world["fr"] / "funnel_night10.json"
    fn.write_text(json.dumps({"generated_at": _iso(OPEN - timedelta(days=30)),
                              "candidates": [{"ticker": "N01"}]}))
    assert DA.main(_argv(late)) == 0
    rec = _receipt(world)
    assert rec["inputs"]["bars_panel"]["stale"] is True
    assert rec["inputs"]["bars_panel"]["sessions_behind"] > 1
    stale = " ".join(rec["summary"]["stale_inputs"])
    assert "bars panel" in stale and "funnel" in stale
    assert "[STALE]" in capsys.readouterr().out


def test_lookahead_in_a_cited_item_is_refused():
    row = {"ticker": "X",
           "knowable": {"earliest": {"known_at": _iso(OPEN)}, "latest_before_open": None,
                        "evidence": []},
           "forecasts": {"latest": None}, "attention": {"contract_rows": []}}
    with pytest.raises(DA.AutopsyRefused) as e:
        DA.assert_no_lookahead([row], OPEN)
    assert e.value.code == DA.LOOKAHEAD
    DA.assert_no_lookahead([{**row, "knowable": {"earliest": {"known_at": _iso(
        OPEN - timedelta(seconds=1))}, "evidence": []}}], OPEN)


def test_empty_corpus_window_is_unknown_not_no_headline():
    empty = {"by_ticker": {}, "n_rows": 0}
    assert DA.knowable("X", empty, empty)["state"] == DA.UNKNOWN
