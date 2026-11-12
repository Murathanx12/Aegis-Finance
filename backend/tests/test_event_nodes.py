"""CH-35 slice 1: event nodes -- offline, synthetic corpus, injected clocks."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import event_nodes as EN
from backend.services import news_entities as NE

NOW = datetime.now(timezone.utc).replace(microsecond=0, second=0, minute=0) - timedelta(days=3)


def _tbl(tmp_path: Path):
    p = tmp_path / "issuers.csv"
    p.write_text(
        "symbol,primary_name,aliases,country,is_adr\n"
        "AI,\"C3.ai, Inc.\",AI|C3.ai,US,\n"
        "ALL,Allstate Corporation (The),ALL,US,\n"
        "AVGO,Broadcom Inc.,AVGO|Broadcom Inc.,US,\n"
        "GOLD,\"Gold.com, Inc.\",GOLD,US,\n"
        "INTC,Intel Corporation,INTC|Intel Corporation,US,\n"
        "IT,\"Gartner, Inc.\",IT,US,\n"
        "MRVL,\"Marvell Technology, Inc.\",MRVL,US,\n"
        "NOW,\"ServiceNow, Inc.\",NOW,US,\n"
        "NVDA,NVIDIA Corporation,NVDA|NVIDIA Corporation,US,\n"
        "ON,ON Semiconductor Corporation,ON,US,\n"
        "TGT,Target Corporation,TGT|Target,US,\n"
        "A,\"Agilent Technologies, Inc.\",A|Agilent Technologies,US,\n",
        encoding="utf-8")
    a = tmp_path / "adrs.csv"
    a.write_text("us_symbol,local_symbol,us_short_name_yfinance\n", encoding="utf-8")
    return NE._Tables(p, a)


def _row(src, fs, title, body="", pub=None, tickers=None, tags=None, url=None):
    return {"source": src, "first_seen_utc": fs.isoformat(), "published_utc": pub.isoformat() if pub else "",
            "url": url or f"https://example.test/{abs(hash(title))}", "title": title, "body": body,
            "tickers": tickers or [], "entity_tags": tags or []}


def _write(root: Path, rows: list[dict]) -> Path:
    corpus = root / "news_corpus"
    for r in rows:
        d = corpus / r["source"]
        d.mkdir(parents=True, exist_ok=True)
        day = r["first_seen_utc"][:10]
        with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
    return corpus


def _filings(root: Path, rows: list[dict]) -> Path:
    p = root / "filing_events.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


_FILLER = ["Intel wins foundry order from carmaker", "Broadcom raises dividend after record quarter",
           "Gartner sees cloud budgets flat next year", "ServiceNow buys workflow startup",
           "Allstate storm losses climb in October", "Agilent Technologies trims lab outlook",
           "C3.ai names new finance chief", "Marvell ships optical module samples",
           "Intel cuts prices on server parts", "Broadcom closes software deal",
           "Gartner hires bank veteran", "ServiceNow lifts subscription forecast"]


def _story(t0: datetime) -> list[dict]:
    # an ordinary corpus around the story: IDF needs a background to be an IDF
    filler = [_row("wsj_business", t0 - timedelta(hours=2, minutes=k), t, "routine company news item")
              for k, t in enumerate(_FILLER)]
    return filler + [
        _row("dj_reader_barrons", t0, "Nvidia Stock Tumbles. Jensen Huang Could Be Out Soon. - Barron's",
             "The board of Nvidia may oust chief executive Jensen Huang after the scandal."),
        _row("mw_topstories", t0 + timedelta(minutes=40),
             "Nasdaq futures fall as Nvidia sinks 8% after hours on report board may oust Huang",
             "Shares of Nvidia fell after a report the board may oust Huang.", pub=t0 + timedelta(minutes=35)),
        _row("google_news_rss_en_hk", t0 + timedelta(hours=7),
             "Nvidia board ousts Huang as chief executive scandal widens - Financial Times",
             "Huang ousted by board after scandal; Broadcom and Intel shares moved."),
        _row("google_news_rss_en_us", t0 + timedelta(hours=7, minutes=1),
             "Nvidia board ousts Huang as chief executive scandal widens - Financial Times",
             "Huang ousted by board after scandal."),
        # a DIFFERENT Nvidia story, same window
        _row("wsj_tech", t0 + timedelta(hours=3),
             "Nvidia unveils liquid-cooled datacenter rack for robotics developers",
             "The new rack product ships next quarter to robotics developers in Europe."),
    ]


def _cluster(tmp_path, rows, *, now=None, since=None, filings=()):
    tbl = _tbl(tmp_path)
    corpus = _write(tmp_path, rows)
    fp = _filings(tmp_path, list(filings))
    now = now or NOW + timedelta(days=1)
    since = since or NOW - timedelta(days=1)
    items, stats = EN.read_rows(corpus, fp, since=since, now=now, cik_map={1045810: "NVDA"}, tbl=tbl)
    clusters, cst = EN.cluster_items(items, tbl)
    return items, stats, clusters, tbl


def test_same_issuer_story_joins_and_a_different_story_stays_apart(tmp_path):
    items, stats, clusters, _ = _cluster(tmp_path, _story(NOW))
    # the two Google editions of one FT article are ONE item with two regions
    ft = [i for i in items if "Financial Times" == i.publisher]
    assert len(ft) == 1 and ft[0].regions == {"HK", "US"}
    nv = [c for c in clusters if "NVDA" in c.issuers]
    sizes = sorted(len(c.members) for c in nv)
    assert sizes == [1, 3], [[m.title for m in c.members] for c in nv]
    big = max(nv, key=lambda c: len(c.members))
    assert all("unveils" not in m.title for m in big.members)
    assert all(j["score"] is None or j["score"] >= EN.C.EVENT_NODES_JOIN_MIN_SIMILARITY for j in big.joins)


def test_rows_after_now_are_never_read(tmp_path):
    rows = _story(NOW)
    rows.append(_row("dj_reader_marketwatch", NOW + timedelta(hours=30),
                     "Nvidia Shares Sink After Huang Is Ousted as CEO", "Huang ousted by the board."))
    rows.append(_row("wsj_tech", NOW + timedelta(hours=2), "Nvidia board weighs Huang ouster",
                     "board Huang oust", pub=NOW + timedelta(hours=40)))
    now = NOW + timedelta(hours=12)
    items, stats, clusters, _ = _cluster(tmp_path, rows, now=now)
    assert stats["dropped_after_now"] == 1
    assert stats["dropped_published_after_now"] == 1
    assert all(i.first_seen <= now and (i.published is None or i.published <= now) for i in items)


def test_lookahead_guard_refuses_a_node_with_future_evidence():
    node = {"event_id": "x", "evidence": [{"first_seen_utc": (NOW + timedelta(hours=1)).isoformat(),
                                           "published_utc": None}]}
    with pytest.raises(EN.EventNodesRefused) as e:
        EN.assert_no_lookahead([node], NOW)
    assert e.value.code == EN.LOOKAHEAD


def test_decay_halves_at_the_half_life():
    hl = EN.C.EVENT_NODES_HALF_LIFE_HOURS
    assert EN.decay(8.0, NOW, NOW) == pytest.approx(8.0)
    assert EN.decay(8.0, NOW, NOW + timedelta(hours=hl)) == pytest.approx(4.0)
    assert EN.decay(8.0, NOW, NOW + timedelta(hours=2 * hl)) == pytest.approx(2.0)
    node = {"first_seen_utc": NOW.isoformat(), "importance": {"importance_0": 3.0},
            "decay": {"half_life_hours": 10.0}}
    assert EN.importance_now(node, NOW + timedelta(hours=10)) == pytest.approx(1.5)


def test_bare_words_never_connect(tmp_path):
    tbl = _tbl(tmp_path)
    text = ("A new AI chip: IT spending is ON the rise, ALL eyes are NOW on GOLD. "
            "Artificial intelligence (AI) and (IT) budgets. Price target cut at Target? the Nasdaq rose.")
    assert EN.strict_tickers(text, tbl) == {}
    got = EN.strict_tickers("$AI jumps; NYSE: ON rises; Intel and Marvell fall; Nvidia too", tbl)
    assert got.get("AI") == "cashtag" and got.get("ON") == "venue_ticker"
    assert got.get("INTC", "").startswith("name:") and got.get("NVDA", "")
    assert got.get("MRVL", "").startswith("alias_map:")


def test_chain_verifies_and_detects_a_tampered_row(tmp_path):
    store = tmp_path / "out" / EN.STORE_NAME
    n1 = {"event_id": "ev1", "content_hash": "h1", "importance": {"importance_0": 1.0}}
    n2 = {"event_id": "ev2", "content_hash": "h2", "importance": {"importance_0": 2.0}}
    r = EN.append_nodes(store, [n1, n2])
    assert r["appended"] == 2 and EN.verify_chain(store)["ok"]
    assert EN.append_nodes(store, [n1])["appended"] == 0          # unchanged -> no new version
    n1b = dict(n1, content_hash="h1b")
    assert EN.append_nodes(store, [n1b])["appended"] == 1
    rows = EN.read_store(store)
    assert rows[-1]["node_version"] == 2 and rows[-1]["supersedes_row_hash"] == rows[0]["row_hash"]
    lines = store.read_text(encoding="utf-8").splitlines()
    t = json.loads(lines[1])
    t["importance"]["importance_0"] = 99.0
    lines[1] = json.dumps(t, sort_keys=True)
    store.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = EN.verify_chain(store)
    assert not v["ok"] and v["first_bad"] == 1
    with pytest.raises(EN.EventNodesRefused) as e:
        EN.append_nodes(store, [dict(n2, content_hash="h2b")])
    assert e.value.code == EN.CHAIN_BROKEN


def _node():
    return {"event_id": "ev", "primary_ticker": "NVDA", "first_seen_utc": NOW.isoformat(),
            "content_hash": "c",
            "evidence": [{"title": "Nvidia reports earnings Nov. 17", "publisher": "X", "regions": ["US"],
                          "published_utc": NOW.isoformat(), "first_seen_utc": NOW.isoformat()},
                         {"title": "Huang out", "publisher": "Y", "regions": [],
                          "published_utc": None, "first_seen_utc": NOW.isoformat()}],
            "connected_names": {"co_mention": [{"ticker": "AVGO"}], "graph": [{"ticker": "AMD"}]}}


def _texts():
    return ["Nvidia reports earnings Nov. 17\nThe chip maker reports results on Nov. 17 after the bell.",
            "Huang out\nThe board voted."]


def _ok(text):
    return lambda s, u, m: {"ok": True, "status": "OK", "text": text, "provider": "stub"}


def test_fill_accepts_a_cited_date_and_refuses_the_rest():
    yr = NOW.year
    reply = json.dumps({
        "dated_facts": [
            {"date": f"{yr}-11-17", "fact": "earnings", "evidence_index": 0, "quote": "reports results on Nov. 17"},
            {"date": f"{yr}-11-17", "fact": "x", "evidence_index": 7, "quote": "Nov. 17"},       # out of range
            {"date": f"{yr}-11-20", "fact": "y", "evidence_index": 0, "quote": "Nov. 17"},        # uncited date
            {"date": f"{yr}-11-17", "fact": "z", "evidence_index": 1, "quote": "The board voted."},  # date not in item
        ],
        "stances": [{"ticker": "AVGO", "stance": "up", "evidence_index": 1},
                    {"ticker": "AVGO", "stance": "up", "evidence_index": -1},
                    {"ticker": "TGT", "stance": "down", "evidence_index": 0}],
        "open_questions": ["Who replaces Huang?"]})
    out = EN.fill_event(_node(), _texts(), call=_ok(reply))
    assert [f["evidence_index"] for f in out["dated_facts"]] == [0]
    assert out["refused"]["evidence_index_out_of_range"] == 2
    assert out["refused"]["uncited_date"] == 2
    assert out["refused"]["stance_ticker_not_connected"] == 1
    assert out["stances"] == [{"ticker": "AVGO", "stance": "up", "evidence_index": 1}]
    assert out["status"] == "FILLED"


def test_fill_refuses_non_json_and_budget_refusal_and_provider_failure():
    with pytest.raises(EN.EventFillRefused) as e:
        EN.fill_event(_node(), _texts(), call=_ok("Sure! Here are the facts: ..."))
    assert e.value.code == EN.FILL_NOT_JSON
    with pytest.raises(EN.EventFillRefused) as e:
        EN.fill_event(_node(), _texts(), call=lambda s, u, m: {"ok": False, "status": "BUDGET_REFUSED",
                                                              "error": "cap reached"})
    assert e.value.code == EN.FILL_BUDGET_REFUSED
    with pytest.raises(EN.EventFillRefused) as e:
        EN.fill_event(_node(), _texts(), call=lambda s, u, m: {"ok": False, "status": "ERROR"})
    assert e.value.code == EN.FILL_PROVIDER_FAILED
    out = EN.validate_fill(json.dumps({"dated_facts": [{"date": "x", "evidence_index": 99, "quote": "q"}],
                                       "stances": [], "open_questions": []}), _node(), _texts())
    assert out["status"].startswith("REFUSED_") and out["n_accepted"] == 0


def test_missing_input_is_a_named_refusal(tmp_path):
    with pytest.raises(EN.EventNodesRefused) as e:
        EN.check_inputs(EN.default_paths(tmp_path / "nowhere"))
    assert e.value.code == EN.CORPUS_MISSING


def test_cli_refuses_missing_input_with_rc2_and_writes_nothing(tmp_path, capsys):
    from scripts import event_nodes as CLI
    out = tmp_path / "out"
    rc = CLI.main(["build", "--data-root", str(tmp_path / "nowhere"), "--out", str(out),
                   "--now", NOW.isoformat()])
    assert rc == 2
    assert not out.exists()
    assert "CORPUS_MISSING" in capsys.readouterr().out
