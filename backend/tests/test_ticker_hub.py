"""CH-22 ticker hub: tagging rules (incl. the common-word traps), incremental build,
the stale flag, the 403/404 contract. Small synthetic fixtures under tmp_path; dates
are derived from `now`, never written as calendar literals."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import news_entities as NE
from backend.services import ticker_hub as TH

NOW = datetime.now(timezone.utc).replace(microsecond=0)
DAY = NOW.date().isoformat()

ISSUERS = """symbol,primary_name,aliases,country,is_adr
A,"Agilent Technologies, Inc.",A|Agilent Technologies,US,
AAPL,Apple Inc.,AAPL|Apple,US,
ALL,Allstate Corporation (The),ALL|Allstate Corporation (The),US,
FCF,First,FCF|First,US,
IT,"Gartner, Inc.","IT|Gartner, Inc.",US,
NOW,"ServiceNow, Inc.","NOW|ServiceNow, Inc.",US,
NVDA,NVIDIA Corporation,NVDA|NVIDIA Corporation,US,
ON,ON Semiconductor Corporation,ON|ON Semiconductor Corporation,US,
PPLI,People Incorporated,PPLI|People Incorporated,US,
QMCO,Quantum Corporation,QMCO|Quantum Corporation,US,
SOLI,Solidion Technology Inc.,SOLI|Solidion Technology,US,
TINY,Tinycap Widgets Inc.,TINY|Tinycap Widgets,US,
"""


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _row(src: str, title: str, *, minutes_ago: int = 30, url: str = "", body: str = "",
         tickers=None, tags=None) -> dict:
    t = NOW - timedelta(minutes=minutes_ago)
    return {"source": src, "first_seen_utc": _iso(t), "published_utc": _iso(t - timedelta(minutes=5)),
            "url": url or f"https://example.com/{abs(hash(title))}", "title": title, "body": body,
            "lang": "en", "tickers": tickers or [], "entity_tags": tags or [], "raw_id": title[:20]}


def _append(root: Path, src: str, rows: list[dict]) -> None:
    p = root / "news_corpus" / src / f"{DAY}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "optimus"
    (root / "official").mkdir(parents=True)
    (root / "official" / "company_tickers.json").write_text(
        json.dumps({"t": _iso(NOW), "map": {"1881551": "SOLI"}}), encoding="utf-8")
    (root / "potential_universe").mkdir()
    with (root / "potential_universe" / f"{DAY}.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"artefact": "header"}) + "\n")
        for s, sec in (("NVDA", "Semiconductors"), ("ON", "Semiconductors"), ("AAPL", "Technology"),
                       ("TINY", "Machinery")):
            fh.write(json.dumps({"symbol": s, "identity": {"sector": sec}}) + "\n")
    _append(root, "wsj_tech", [
        _row("wsj_tech", "Nvidia Shares Fall After Earnings", url="https://www.wsj.com/tech/nvda-1?mod=rss"),
        _row("wsj_tech", "Quantum Computers Are Poised to Crack Encryption",
             tickers=["QMCO"], tags=["resolved:QMCO=name"]),
        _row("wsj_tech", "IT spending rises (IT) as ON the move and ALL in", minutes_ago=40),
        _row("wsj_tech", "Gartner stock: $IT rallies; ON Semiconductor (NASDAQ: ON) beats", minutes_ago=50),
        _row("wsj_tech", "A quiet day for markets", minutes_ago=60),
        _row("wsj_tech", "Tinycap Widgets wins a contract", minutes_ago=70),
    ])
    _append(root, "google_news_rss_en_us", [
        _row("google_news_rss_en_us", "Six dead, 15 injured in Krakow attack - The Australian",
             tickers=["PPLI"], tags=["resolved:PPLI=name"]),
        _row("google_news_rss_en_us", "How a Mississippi election came down to the clerk - The Post",
             tickers=["FCF"], tags=["resolved:FCF=name"]),
        _row("google_news_rss_en_us", "Chip stocks: the people who sold - Barron's",
             tickers=["NVDA"], tags=["resolved:NVDA=cashtag"], minutes_ago=20),
    ])
    _append(root, "sec_edgar_8k_current_atom", [
        _row("sec_edgar_8k_current_atom", "8-K - Solidion Technology Inc. (0001881551) (Filer)",
             tags=["8-K:2.02", "cik:0001881551"]),
    ])
    # the reader's page store: one article reached by ticker, one front page with links
    d = root / "news_corpus" / "dowjones" / "barrons" / DAY
    d.mkdir(parents=True)
    (d / "aaa.json").write_text(json.dumps({
        "publisher": "barrons", "url": "https://www.barrons.com/articles/apple-x", "page_kind": "article",
        "page_class": "OK", "title": "Apple Sells More Phones | Barron's", "first_seen_utc": _iso(NOW - timedelta(hours=2)),
        "published_utc": None, "text": "Apple said ...", "reached_by": {"lane": "search:AAPL", "ticker": "AAPL"},
        "tickers_named": ["AAPL", "A"], "outbound_links": []}), encoding="utf-8")
    (d / "bbb.json").write_text(json.dumps({
        "publisher": "barrons", "url": "https://www.barrons.com/", "page_kind": "front", "page_class": "OK",
        "title": "front", "first_seen_utc": _iso(NOW - timedelta(hours=3)), "reached_by": {"lane": "front"},
        "outbound_links": [{"url": "https://www.barrons.com/articles/nvda-y", "text": "Nvidia Stock Is Down. Here Is Why."},
                           {"url": "https://www.barrons.com/subscribe", "text": "Subscribe"},
                           {"url": "https://www.barrons.com/articles/q", "text": "Bond yields climb as the Fed waits"}]}),
        encoding="utf-8")
    # world digest typed row for the WSJ Nvidia URL
    dg = root / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl"
    dg.parent.mkdir(parents=True)
    dg.write_text(json.dumps({"cache_key": "k", "row": {"url": "https://www.wsj.com/tech/nvda-1?mod=other",
                                                        "event_type": "earnings", "topic": "Nvidia results",
                                                        "sentiment": -0.3, "tickers": []}}) + "\n",
                  encoding="utf-8")
    # forecast ledger (legacy single file)
    preds = [
        {"prediction_id": "p1", "ticker": "NVDA", "observable": "return_sign", "probability": 0.6,
         "horizon_days": 5, "made_at": _iso(NOW - timedelta(days=10)), "resolved_at": DAY,
         "outcome": 1, "brier": 0.16, "resolution_detail": {"realised_return": 0.03}},
        {"prediction_id": "p2", "ticker": "NVDA", "observable": "return_sign", "probability": 0.4,
         "horizon_days": 60, "made_at": _iso(NOW - timedelta(days=1)), "resolved_at": None, "outcome": None},
        {"prediction_id": "p3", "ticker": "AAPL", "observable": "abs_move_exceeds", "probability": 0.5,
         "horizon_days": 20, "made_at": _iso(NOW - timedelta(days=2)), "outcome": None},
    ]
    (root / "predictions.jsonl").write_text("".join(json.dumps(p) + "\n" for p in preds), encoding="utf-8")
    return root


@pytest.fixture()
def paths(data_root: Path, tmp_path: Path) -> dict:
    ip = tmp_path / "issuers.csv"
    ip.write_text(ISSUERS, encoding="utf-8")
    P = TH.default_paths(data_root)
    P["issuers"] = ip
    return P


def _build(data_root: Path, paths: dict, out: Path, now: datetime = NOW) -> dict:
    return TH.build(data_root, out=out, now=now, paths=paths)


def _tags(out: Path) -> dict[str, list]:
    return {r["title"]: sorted((t["t"], t["m"]) for t in r["tags"]) for r in TH.iter_index_rows(out)}


def test_tagging_rules_and_common_word_traps(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    rec = _build(data_root, paths, out)
    tags = _tags(out)
    # a collector NAME match is not trusted, and the strict resolver refuses it too
    assert not any("Krakow" in t for t in tags), tags
    assert not any("Mississippi" in t for t in tags)
    assert not any("Quantum" in t for t in tags)
    # bare word symbols never match from text or a bare parenthesis
    assert not any(t.startswith("IT spending") for t in tags)
    # explicit tokens do
    g = next(v for k, v in tags.items() if k.startswith("Gartner stock"))
    assert ("IT", "text_token") in g or ("IT", "name_match") in g
    assert ("ON", "text_token") in g or ("ON", "name_match") in g
    assert all(sym not in ("ALL", "A", "NOW") for sym, _ in g)
    # provider explicit token kept as source_field
    chip = next(v for k, v in tags.items() if k.startswith("Chip stocks"))
    assert ("NVDA", "source_field") in chip
    # name match, SEC by CIK, reader lane, reader front link, cased alias
    assert ("NVDA", "name_match") in tags["Nvidia Shares Fall After Earnings"]
    assert ("SOLI", "sec_cik") in next(v for k, v in tags.items() if "Solidion" in k)
    apple = tags["Apple Sells More Phones"]
    assert ("AAPL", "source_field") in apple and not any(s == "A" for s, _ in apple)
    assert ("NVDA", "name_match") in tags["Nvidia Stock Is Down. Here Is Why."]
    assert "Subscribe" not in tags and "Bond yields climb as the Fed waits" not in tags
    assert ("TINY", "name_match") in tags["Tinycap Widgets wins a contract"]
    # untagged rows are counted, not stored
    assert rec["rows_untagged_new"] >= 5 and rec["untagged_share_new"] is not None
    assert "A quiet day for markets" not in tags


def test_hub_payload_news_forecasts_related_and_typed_event(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    h = TH.hub("nvda", data_root=data_root, out=out, days=30, now=NOW)
    assert h["ticker"] == "NVDA"
    titles = [r["title"] for r in h["news"]]
    assert "Nvidia Shares Fall After Earnings" in titles and "Nvidia Stock Is Down. Here Is Why." in titles
    stamps = [r["first_seen_utc"] for r in h["news"]]
    assert stamps == sorted(stamps, reverse=True)
    wsj = next(r for r in h["news"] if r["title"] == "Nvidia Shares Fall After Earnings")
    assert wsj["event"]["event_type"] == "earnings"      # joined by URL, query string ignored
    assert wsj["tagged_by"] == ["name_match"]
    fc = h["forecasts"]
    assert fc["counts"]["open"] == 1 and fc["counts"]["resolved"] == 1
    assert fc["resolved"][0]["realised_return"] == 0.03
    assert any(r["ticker"] == "ON" and r["link"] == "same_sector" for r in h["related"])
    assert h["coverage"]["status"] == "OK" and h["coverage"]["n_rows"] == len(h["news"])
    assert h["calendar"]["status"] in ("OK", "CALENDAR_UNREADABLE")
    with pytest.raises(KeyError):
        TH.hub("ZZZZ", data_root=data_root, out=out, now=NOW)


def test_incremental_build_reads_only_new_rows(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    first = _build(data_root, paths, out)
    n0 = first["rows_in_index"]
    again = _build(data_root, paths, out, now=NOW + timedelta(seconds=5))
    assert again["rows_read_new"] == 0 and again["rows_in_index"] == n0
    _append(data_root, "wsj_tech", [_row("wsj_tech", "Nvidia (NVDA) unveils a new chip", minutes_ago=1)])
    third = _build(data_root, paths, out, now=NOW + timedelta(seconds=10))
    assert third["rows_read_new"] == 1 and third["rows_in_index"] == n0 + 1
    # the same headline in a second feed folds into one row
    _append(data_root, "wsj_markets", [_row("wsj_markets", "Nvidia (NVDA) unveils a new chip", minutes_ago=1)])
    fourth = _build(data_root, paths, out, now=NOW + timedelta(seconds=15))
    assert fourth["rows_in_index"] == n0 + 1
    row = next(r for r in TH.iter_index_rows(out) if r["title"] == "Nvidia (NVDA) unveils a new chip")
    assert set(row["feeds"]) == {"wsj_tech", "wsj_markets"}
    # a request never needs the corpus: delete it and the hub still answers
    import shutil
    shutil.rmtree(data_root / "news_corpus")
    h = TH.hub("NVDA", data_root=data_root, out=out, now=NOW + timedelta(seconds=20))
    assert any(r["title"] == "Nvidia (NVDA) unveils a new chip" for r in h["news"])


def test_stale_flag_compares_the_build_time_with_now(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    later = NOW + timedelta(hours=float(TH.C.TICKER_HUB_STALE_HOURS) + 1)
    h = TH.hub("NVDA", data_root=data_root, out=out, now=later)
    assert h["coverage"]["status"] == "STALE" and h["coverage"]["index_age_s"] > 3600
    assert "STALE" in h["coverage"]["detail"]
    st = TH.index_status(tmp_path / "nothing_here", NOW)
    assert st["status"] == "NO_INDEX"


def test_refusals_are_named(tmp_path, paths):
    with pytest.raises(TH.TickerHubRefused) as e:
        TH.build(tmp_path / "missing", out=tmp_path / "o", now=NOW,
                 paths={**paths, "corpus": tmp_path / "missing" / "news_corpus"})
    assert e.value.code == TH.CORPUS_MISSING
    empty = tmp_path / "empty"
    (empty / "news_corpus").mkdir(parents=True)
    with pytest.raises(TH.TickerHubRefused) as e2:
        TH.build(empty, out=tmp_path / "o2", now=NOW, paths={**TH.default_paths(empty), "issuers": paths["issuers"]})
    assert e2.value.code == TH.NOTHING_INDEXED


def test_cli_build_exit_codes(data_root, paths, tmp_path, monkeypatch, capsys):
    from scripts import ticker_hub as cli
    monkeypatch.setattr(NE, "entities_dir", lambda: paths["issuers"].parent)   # holds issuers.csv
    rc = cli.main(["build", "--data-root", str(data_root), "--out", str(tmp_path / "hub"), "--now", _iso(NOW)])
    out = capsys.readouterr().out
    assert rc == 0 and "rows read (new)" in out and "tags by method" in out
    empty = tmp_path / "empty"
    (empty / "news_corpus").mkdir(parents=True)
    assert cli.main(["build", "--data-root", str(empty), "--out", str(tmp_path / "o3")]) == 2
    assert cli.main(["build", "--data-root", str(tmp_path / "nope"), "--out", str(tmp_path / "o4")]) == 2


def test_feed_filters_and_facets(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    f = TH.feed(data_root=data_root, out=out, sector="Semiconductors", days=30, now=NOW)
    syms = {t["t"] for r in f["rows"] for t in r["tags"]}
    assert "NVDA" in syms or "ON" in syms
    assert all(any(t["t"] in ("NVDA", "ON") for t in r["tags"]) for r in f["rows"])
    assert {x["key"] for x in f["facets"]["sector"]} >= {"Semiconductors"}
    f2 = TH.feed(data_root=data_root, out=out, ticker="NVDA", source="wsj_tech", days=30, now=NOW)
    assert f2["rows"] and all(r["source"] == "wsj_tech" for r in f2["rows"])
    with pytest.raises(KeyError):
        TH.feed(data_root=data_root, out=out, ticker="ZZZZ", now=NOW)


def test_routes_403_when_disabled_and_404_unknown(data_root, paths, tmp_path, monkeypatch):
    from backend.routers import ticker_hub as R
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    app = FastAPI()
    app.include_router(R.router)
    c = TestClient(app)
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    assert c.get("/api/control/ticker/NVDA/hub").status_code == 403
    assert c.get("/api/control/news/feed?ticker=NVDA").status_code == 403
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(TH, "default_data_root", lambda: data_root)
    monkeypatch.setattr(TH, "hub_dir", lambda dr, o=None: out)
    r = c.get("/api/control/ticker/NVDA/hub?days=30")
    assert r.status_code == 200 and r.json()["news"]
    assert c.get("/api/control/ticker/ZZZZ/hub").status_code == 404
    assert c.get("/api/control/news/feed?ticker=ZZZZ").status_code == 404
    assert c.get("/api/control/ticker/NV%3BDA/hub").status_code == 422
    assert c.get("/api/control/news/feed?sector=Semiconductors").status_code == 200
