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
SPLIT_RET = -0.80           # a 1:5 split or a bad bar, not an event


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
    r = m + rng.normal(0.0, 0.01, n)
    r[-1] = SPLIT_RET
    add("SPLT", r)
    return pd.DataFrame(rows, columns=["symbol", "date", "close", "volume"])


def _jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


def _news(src: str, first_seen: datetime, title: str, tickers=(), tags=(),
          published: datetime | None = None, url: str = "https://example.invalid/x") -> tuple:
    pub = published or (first_seen - timedelta(minutes=5))
    return (src, first_seen, {"source": src, "first_seen_utc": _iso(first_seen),
                              "published_utc": _iso(pub),
                              "title": title, "tickers": list(tickers),
                              "entity_tags": list(tags), "url": url})


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "AUTOPSY_MIN_NAMES_ON_DAY", 10)
    monkeypatch.setattr(C, "AUTOPSY_MIN_CORPUS_ROWS", 1)
    fr = tmp_path / "backend" / "data"
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
              tags=["8-K:2.02", "cik:0000012345"],
              url="https://www.sec.gov/Archives/edgar/data/12345/000001234524000007/x-index.htm"),
        # the same filing's EX-99 body: ONE item with the atom row, not two
        _news("sec_edgar_8k_ex99_body", PREV_CLOSE + timedelta(hours=3, minutes=5), "8-K EX-99.1",
              tags=["8-K:2.02", "cik:0000012345", "accession:0000012345-24-000007"],
              url="https://www.sec.gov/Archives/edgar/data/12345/000001234524000007/ex991.htm"),
        # pulled overnight, but PUBLISHED before the previous close: already traded
        _news("sec_edgar_8k_ex99_body", PREV_CLOSE + timedelta(hours=1, minutes=30), "UPLATE EX-99",
              tickers=["UPLATE"], published=PREV_CLOSE - timedelta(hours=9)),
        # a suspect corporate action with a headline: never seeded
        _news("wire", PREV_CLOSE + timedelta(hours=2), "SPLT announces split", tickers=["SPLT"]),
        _news("wire", PREV_CLOSE + timedelta(hours=4), "UPZ quote page", tickers=["UPZ"],
              tags=[C.AUTOPSY_NOT_NEWS_TAGS[0]]),
    ]
    by_file: dict = {}
    for src, fs, row in items:
        by_file.setdefault((src, fs.date().isoformat()), []).append(row)
    # no first_seen and a DATE-ONLY published stamp: dropped and counted, never knowable
    by_file.setdefault(("wire", PREV.isoformat()), []).append(
        {"source": "wire", "published_utc": D.isoformat(), "title": "DNNEW undated",
         "tickers": ["DNNEW"], "entity_tags": [], "url": "https://example.invalid/u"})
    for (src, day), rows in by_file.items():
        _jsonl(dr / "news_corpus" / src / f"{day}.jsonl", rows)
    (dr / "official").mkdir()
    (dr / "official" / "company_tickers.json").write_text(json.dumps(
        {"t": _iso(OPEN), "map": {"12345": "UPK"}}))
    _issuers(fr)
    # a revision dated BEFORE the previous close but first pulled AFTER the open: not knowable
    _revisions(dr, [_rev("UPZ", PREV_CLOSE - timedelta(hours=2), OPEN + timedelta(hours=1))])
    out = tmp_path / "out"
    now = _at(D + timedelta(days=1), 2)
    return {"dr": dr, "fr": fr, "out": out, "now": now}


#: synthetic issuer table: names that never occur in the fixture's headlines,
#: plus bare-word symbols and two names the reader tests resolve.
ISSUERS = [("UPZ", "Upzeta Dynamics Inc."), ("UPK", "Upkappa Corp"), ("DNF", "Dnf Holdings"),
           ("DNC", "Dncharlie Inc."), ("DNNEW", "Dnnew Robotics Inc."), ("UPLATE", "Uplate Ltd"),
           ("AI", "C3.ai, Inc."), ("ON", "ON Semiconductor Corporation"),
           ("ALL", "Allstate Corporation (The)"), ("NOW", "ServiceNow, Inc."),
           ("IT", "Gartner, Inc."), ("A", "Agilent Technologies, Inc."), ("GOLD", "Gold.com, Inc.")]


def _issuers(fr: Path) -> None:
    d = fr / "news_entities"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["symbol,primary_name,aliases,country,is_adr"]
    for s, n in ISSUERS:
        lines.append(f'{s},"{n}","{s}|{n}",US,')
    (d / "issuers.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ny_naive(t: datetime) -> str:
    return t.astimezone(DA.NY).strftime("%Y-%m-%d %H:%M:%S")


def _rev(tk: str, event: datetime, seen: datetime, firm: str = "Synthetic Securities") -> dict:
    return {"ticker": tk, "pulled_at": _iso(seen), "event_date": _ny_naive(event), "firm": firm,
            "from_grade": "Hold", "to_grade": "Buy", "action": "up", "target_action": "Raises",
            "prior_target": 40.0, "current_target": 55.0, "target_change": 0.375,
            "pit_safe": True, "first_seen_utc": _iso(seen)}


def _revisions(dr: Path, rows: list[dict]) -> None:
    (dr / "analyst").mkdir(parents=True, exist_ok=True)
    cols = list(_rev("X", OPEN, OPEN))
    pd.DataFrame(rows, columns=cols).to_parquet(dr / "analyst" / "target_revisions.parquet",
                                                index=False)


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

    assert by["UPK"]["knowable"]["state"] == DA.KNOWABLE_FRESH      # 8-K via the CIK map
    assert by["UPK"]["knowable"]["earliest"]["kind"] == "FILING"
    assert by["UPK"]["knowable"]["n_items"] == 1                     # atom + EX-99 = one filing
    assert by["UPK"]["knowable"]["n_rows"] == 2
    assert by["DNF"]["knowable"]["state"] == DA.KNOWABLE_FRESH
    assert by["DNC"]["knowable"]["state"] == DA.KNOWABLE_ALREADY_TRADED
    # pulled overnight but published before the previous close; its after-open headline ignored
    assert by["UPLATE"]["knowable"]["state"] == DA.KNOWABLE_ALREADY_TRADED
    assert by["UPLATE"]["knowable"]["n_items"] == 1
    assert by["DNNEW"]["knowable"]["state"] == DA.NO_HEADLINE_IN_CORPUS   # undated row dropped
    assert rec["inputs"]["corpus_rows_dropped_undated"] >= 1
    assert by["UPZ"]["knowable"]["state"] == DA.NO_HEADLINE_IN_CORPUS     # a quote page is not news
    assert by["UPZ"]["knowable"]["reader_pages_before_open"] == 1

    s = rec["summary"]
    assert s["n_movers"] == 6 and s["by_side"] == {"UP": 3, "DOWN": 3}
    assert s["missed_but_knowable"] == ["UPK"]                          # fresh only
    assert sorted(s["missed_already_traded"]) == ["DNC", "UPLATE"]
    assert s["by_knowable"][DA.KNOWABLE_FRESH] == 2                      # UPK, DNF (forecast)
    assert s["n_unknown"] == 0
    assert "SPLT" not in by
    assert [x["ticker"] for x in rec["suspects"]] == ["SPLT"]
    assert rec["suspects"][0]["ladder"] == DA.SUSPECT_CORPORATE_ACTION
    assert s["n_suspect_corporate_action"] == 1
    assert any("after the open" in w for w in s["warnings"])            # the PREV contract file
    for m in rec["movers"]:
        for e in m["knowable"]["evidence"]:
            assert datetime.fromisoformat(e["first_seen_utc"]) < OPEN
    assert rec["inputs"]["bars_panel"]["stale"] is False
    assert rec["candidate_set"]["n_funnel"] == 1
    assert rec["candidate_set"]["funnel_age_days_at_open"] == pytest.approx(3.0, abs=0.01)

    queue = [json.loads(x) for x in
             (world["out"] / "research_queue.jsonl").read_text().splitlines()]
    assert sorted(q["ticker"] for q in queue) == ["UPK"]
    out = capsys.readouterr().out
    assert "MISSED BUT KNOWABLE (fresh) 1" in out


def test_second_run_keeps_the_first_receipt_and_dedupes_the_queue(world):
    assert DA.main(_argv(world)) == 0
    world2 = {**world, "now": world["now"] + timedelta(minutes=5)}
    assert DA.main(_argv(world2)) == 0
    runs = sorted(world["out"].glob(f"autopsy_{D.isoformat()}_*.json"))
    assert len(runs) == 2
    assert len((world["out"] / "research_queue.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("rel,code", [
    ("optimus/prices_2025_26/bars.parquet", DA.PANEL_MISSING),
    ("optimus/predictions.jsonl", DA.LEDGER_MISSING),
    ("funnel_night10.json", DA.FUNNEL_MISSING),
    ("optimus/decisions", DA.DECISIONS_MISSING),
    ("optimus/digest", DA.DIGEST_MISSING),
    ("optimus/news_corpus", DA.CORPUS_MISSING),
    ("optimus/official/company_tickers.json", DA.CIK_MAP_MISSING),
    ("news_entities/issuers.csv", DA.ISSUER_MAP_MISSING),
    ("optimus/analyst/target_revisions.parquet", DA.REVISIONS_MISSING),
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


def test_a_stale_input_refuses_unless_allowed_and_the_flag_travels(world, capsys):
    late = {**world, "now": world["now"] + timedelta(days=30)}
    fn = world["fr"] / "funnel_night10.json"
    fn.write_text(json.dumps({"generated_at": _iso(OPEN - timedelta(days=30)),
                              "candidates": [{"ticker": "N01"}]}))
    assert DA.main(_argv(late)) == 2
    err = capsys.readouterr().err
    assert "STALE_INPUT" in err and "bars panel" in err and "funnel" in err
    assert not world["out"].exists(), "a refused run wrote a receipt or an index row"
    assert DA.main(_argv(late, "--allow-stale")) == 0
    rec = _receipt(world)
    assert rec["allow_stale"] is True
    assert rec["inputs"]["bars_panel"]["stale"] is True
    assert rec["inputs"]["bars_panel"]["sessions_behind"] > 1
    assert "[STALE]" in capsys.readouterr().out
    assert len((world["out"] / "index.jsonl").read_text().splitlines()) == 1


def test_a_frozen_forecast_ledger_is_stale(world, capsys):
    led = world["dr"] / "predictions.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines() if x.startswith("{")]
    rows[0]["made_at"] = _iso(OPEN - timedelta(days=10))
    _jsonl(led, rows)
    assert DA.main(_argv(world)) == 2
    assert "forecast ledger" in capsys.readouterr().err


def test_an_unclosed_session_is_refused(world, capsys):
    early = {**world, "now": OPEN + timedelta(minutes=30)}
    assert DA.main(_argv(early)) == 2
    assert "SESSION_NOT_CLOSED" in capsys.readouterr().err
    assert not world["out"].exists()


def test_a_non_session_is_refused(world, capsys):
    sat = next(D - timedelta(days=k) for k in range(1, 8) if (D - timedelta(days=k)).weekday() == 5)
    assert DA.main(_argv(world, "--session", sat.isoformat())) == 2
    assert "NOT_A_SESSION" in capsys.readouterr().err


def test_no_benchmark_is_refused(world, capsys):
    bp = world["dr"] / "prices_2025_26" / "bars.parquet"
    b = pd.read_parquet(bp)
    b[b["symbol"] != "SPY"].to_parquet(bp, index=False)
    assert DA.main(_argv(world)) == 2
    assert "NO_BENCHMARK" in capsys.readouterr().err


def test_out_anywhere_under_backend_data_is_refused(world, tmp_path, capsys):
    other = tmp_path / "funnels"
    other.mkdir()
    (other / "funnel_night10.json").write_text((world["fr"] / "funnel_night10.json").read_text())
    sibling = world["fr"] / "not_optimus"
    argv = ["--data-root", str(world["dr"]), "--funnel-root", str(other), "--out", str(sibling),
            "--now", _iso(world["now"])]
    assert DA.main(argv) == 2
    assert "OUT_INSIDE_DATA_ROOT" in capsys.readouterr().err
    assert not sibling.exists()


def test_lookahead_in_a_cited_item_is_refused():
    row = {"ticker": "X",
           "knowable": {"earliest": {"known_at": _iso(OPEN - timedelta(hours=1)),
                                     "first_seen_utc": _iso(OPEN)},
                        "latest_before_open": None, "evidence": []},
           "forecasts": {"latest": None}, "attention": {"contract_rows": []}}
    with pytest.raises(DA.AutopsyRefused) as e:
        DA.assert_no_lookahead([row], OPEN)
    assert e.value.code == DA.LOOKAHEAD
    # the derived known_at is NOT trusted: the raw stamp decides
    ok = {"first_seen_utc": _iso(OPEN - timedelta(seconds=1)),
          "published_utc": _iso(OPEN - timedelta(hours=2))}
    DA.assert_no_lookahead([{**row, "knowable": {"earliest": ok, "evidence": []}}], OPEN)
    late_pub = {**ok, "published_utc": _iso(OPEN + timedelta(minutes=1))}
    with pytest.raises(DA.AutopsyRefused):
        DA.assert_no_lookahead([{**row, "knowable": {"earliest": late_pub, "evidence": []}}], OPEN)
    undated = {"first_seen_utc": None, "published_utc": D.isoformat()}
    with pytest.raises(DA.AutopsyRefused):
        DA.assert_no_lookahead([{**row, "knowable": {"earliest": undated, "evidence": []}}], OPEN)


def test_empty_corpus_window_is_unknown_not_no_headline():
    empty = {"by_ticker": {}, "n_rows": 0}
    assert DA.knowable("X", empty, empty, prev_close=PREV_CLOSE,
                       open_d=OPEN)["state"] == DA.UNKNOWN


def test_a_midnight_or_date_only_stamp_is_not_a_time():
    assert DA.timed_utc("2024-03-01") is None
    assert DA.timed_utc("2024-03-01T00:00:00+00:00") is None
    assert DA.timed_utc("2024-03-01T11:50:33+00:00") is not None
