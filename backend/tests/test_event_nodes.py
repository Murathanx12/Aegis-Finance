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
        "PPLI,People Incorporated,PPLI|People Incorporated,US,\n"
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
    assert all(j["joined"] and j["score"] >= EN.C.EVENT_NODES_JOIN_MIN_SIMILARITY for j in big.joins)


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
    # a single-word issuer name the window writes in lowercase is a word
    assert EN.strict_tickers("six people killed in shooting", tbl) == {}
    common = EN.common_word_keys(["six people killed", "people trapped", "People flee"], tbl)
    assert "people" in common
    assert EN.strict_tickers("People trapped after building collapse", tbl, common) == {}
    assert "PPLI" in EN.strict_tickers("People Incorporated shares jump", tbl, common)


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
        "stances": [{"ticker": "AVGO", "stance": "up", "evidence_index": 1, "quote": "The board voted."},
                    {"ticker": "AVGO", "stance": "up", "evidence_index": 1},
                    {"ticker": "AVGO", "stance": "up", "evidence_index": -1},
                    {"ticker": "TGT", "stance": "down", "evidence_index": 0}],
        "open_questions": ["Who replaces Huang?"]})
    out = EN.fill_event(_node(), _texts(), call=_ok(reply))
    assert [f["evidence_index"] for f in out["dated_facts"]] == [0]
    assert out["refused"]["evidence_index_out_of_range"] == 2
    assert out["refused"]["uncited_date"] == 2
    assert out["refused"]["stance_ticker_not_connected"] == 1
    assert [(s["ticker"], s["evidence_index"]) for s in out["stances"]] == [("AVGO", 1)]
    assert out["refused"]["stance_quote_not_in_evidence"] == 1
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


def test_a_split_is_visible_in_the_node():
    def n(eid, sym, joins):
        return {"event_id": eid, "primary_ticker": sym, "n_evidence": len(joins),
                "timeline": [{"title": f"title {eid}"}],
                "evidence": [{"item_key": j["item"], "title": j["item"]} for j in joins], "joins": joins}
    a = n("a", "NVDA", [{"item": "x", "score": 0.9, "joined": True, "nearest": "y"},
                        {"item": "y", "score": 0.21, "joined": True, "nearest": "x"}])
    b = n("b", "NVDA", [{"item": "z", "score": 0.1, "joined": False, "nearest": None}])
    c = n("c", "AVGO", [{"item": "w", "score": None, "joined": False, "nearest": None}])
    EN.annotate_split_and_merge([a, b, c])
    assert [s["event_id"] for s in a["same_issuer_siblings"]] == ["b"]
    assert c["same_issuer_siblings"] == []
    assert a["weakest_joins"][0]["score"] == 0.21


# ───────────────────────── review round 1 (#128) ─────────────────────────

def _pipeline(tmp_path, rows, *, since, now, store, filings=()):
    tbl = _tbl(tmp_path)
    corpus = tmp_path / "news_corpus"
    if corpus.exists():
        import shutil
        shutil.rmtree(corpus)
    _write(tmp_path, rows)
    fp = _filings(tmp_path, list(filings))
    items, stats = EN.read_rows(corpus, fp, since=since, now=now, cik_map={}, tbl=tbl)
    clusters, cst = EN.cluster_items(items, tbl)
    cst.pop("old_context_unattached", None)
    nodes = [EN.build_node(c, now=now, build_id="b") for c in clusters]
    stored = EN.latest_nodes(EN.read_store(store))
    retire = EN.assign_identity(nodes, stored, since=since)
    for n in nodes:
        EN.finalize_node(n, {}, now=now)
    EN.append_rows(store, nodes, retire=retire)
    return nodes, stats, retire


def _huang_node(latest):
    return [n for n in latest.values() if any("Huang" in e["title"] for e in n["evidence"])]


def test_identity_holds_under_a_shifted_window_and_more_rows(tmp_path):
    store = tmp_path / "out" / EN.STORE_NAME
    rows = _story(NOW)
    _pipeline(tmp_path, rows, since=NOW - timedelta(hours=6), now=NOW + timedelta(hours=12), store=store)
    first = _huang_node(EN.latest_nodes(EN.read_store(store)))
    assert len(first) == 1
    more = rows + [_row("dj_reader_marketwatch", NOW + timedelta(hours=9),
                        "Nvidia Shares Sink After Huang Is Ousted as CEO",
                        "The board ousted chief executive Jensen Huang after the scandal.")]
    _pipeline(tmp_path, more, since=NOW + timedelta(hours=5), now=NOW + timedelta(hours=18), store=store)
    latest = EN.latest_nodes(EN.read_store(store))
    hu = _huang_node(latest)
    assert len(hu) == 1, [n["event_id"] for n in hu]
    assert hu[0]["event_id"] == first[0]["event_id"] and hu[0]["node_version"] == 2
    keys = [e["item_key"] for n in latest.values() for e in n["evidence"]]
    assert len(keys) == len(set(keys))                    # no item in two latest nodes
    titles = {e["title"] for e in hu[0]["evidence"]}
    assert "Nvidia Stock Tumbles. Jensen Huang Could Be Out Soon." in titles   # carried forward
    assert "Nvidia Shares Sink After Huang Is Ousted as CEO" in titles
    assert EN.verify_chain(store)["ok"]


def test_a_merge_retires_the_absorbed_node(tmp_path):
    store = tmp_path / "out" / EN.STORE_NAME
    a = {"event_id": "ev_a", "content_hash": "ha", "evidence": [{"item_key": "k1"}, {"item_key": "k2"}]}
    b = {"event_id": "ev_b", "content_hash": "hb", "evidence": [{"item_key": "k3"}, {"item_key": "k4"}]}
    EN.append_rows(store, [a, b])
    new = {"event_id": "ev_new", "evidence": [{"item_key": k, "first_seen_utc": NOW.isoformat()}
                                              for k in ("k1", "k2", "k3", "k4", "k5")]}
    retire = EN.assign_identity([new], EN.latest_nodes(EN.read_store(store)), since=NOW - timedelta(days=1))
    assert new["event_id"] in ("ev_a", "ev_b")
    other = ({"ev_a", "ev_b"} - {new["event_id"]}).pop()
    assert retire == [{"event_id": other, "survivor": new["event_id"], "reason": "MERGED_INTO_SURVIVOR"}]
    EN.append_rows(store, [dict(new, content_hash="hn")], retire=retire)
    assert list(EN.latest_nodes(EN.read_store(store))) == [new["event_id"]]


def test_an_old_article_is_old_context_and_never_anchors(tmp_path):
    rows = _story(NOW)
    # the reader re-reads a story published two weeks ago, inside the window
    rows.append(_row("dj_reader_wsj", NOW - timedelta(hours=1),
                     "Jensen Huang Investigation Rocks Nvidia as Board Investigates",
                     "The board of Nvidia investigates chief executive Jensen Huang scandal.",
                     pub=NOW - timedelta(days=14)))
    # a date-only publication stamp is kept AS A DATE, ordered at the end of that day
    r = _row("wsj_world", NOW + timedelta(minutes=30), "Nvidia board weighs Huang ouster scandal",
             "board Huang oust scandal chief")
    r["published_utc"] = (NOW + timedelta(minutes=30)).date().isoformat()
    rows.append(r)
    store = tmp_path / "s" / EN.STORE_NAME
    nodes, stats, _ = _pipeline(tmp_path, rows, since=NOW - timedelta(hours=3),
                                now=NOW + timedelta(days=2), store=store)
    hu = [n for n in nodes if any("Tumbles" in e["title"] for e in n["evidence"])][0]
    assert all("Investigation Rocks" not in e["title"] for e in hu["evidence"])
    assert [o["title"] for o in hu["old_context"]] == [
        "Jensen Huang Investigation Rocks Nvidia as Board Investigates"]
    assert hu["old_context"][0]["status"] == "OLD_CONTEXT"
    assert hu["first_seen_utc"] == NOW.isoformat()                     # not the re-read stamp
    assert stats["items_old_context"] == 1
    dated = [e for e in hu["evidence"] if e["published_date"]]
    assert dated and dated[0]["published_utc"] is None
    assert dated[0]["event_time_utc"].endswith("23:59:59+00:00")


def test_price_reaction_starts_after_first_seen_and_is_not_importance():
    import numpy as np
    import pandas as pd
    days = list(pd.bdate_range(end=pd.Timestamp(datetime.now(timezone.utc).date()) - pd.Timedelta(days=30),
                               periods=60))
    rng = np.random.default_rng(1)
    closes = {"XYZ": [], "SPY": []}
    px, sp = 100.0, 100.0
    for d in days:
        px *= 1 + rng.normal(0, 0.01)
        sp *= 1 + rng.normal(0, 0.005)
        closes["XYZ"].append([d, px])
        closes["SPY"].append([d, sp])
    k = 40
    fs = EN._close_utc(days[k]) - timedelta(minutes=10)              # 10 minutes before a close
    pr = EN.price_reaction("XYZ", fs, {"closes": closes})
    assert pr["status"] == "OK" and pr["session"] == days[k + 1].date().isoformat()
    assert datetime.fromisoformat(pr["prior_close_utc"]) >= fs
    imp = EN.importance([{"publisher": "X", "regions": [], "kind": "article", "items_8k": []}],
                        "XYZ", {}, fs)
    assert "price_reaction" not in imp["components"] and imp["components"]["items"] == 0.0


def test_capitalised_common_words_need_an_attached_cue(tmp_path):
    from collections import Counter
    p = tmp_path / "issuers2.csv"
    p.write_text("symbol,primary_name,aliases,country,is_adr\n"
                 "OUST,\"Ouster, Inc.\",OUST|Ouster,US,\n"
                 "ORCL,Oracle Corporation,ORCL|Oracle,US,\n"
                 "NVDA,NVIDIA Corporation,NVDA,US,\n", encoding="utf-8")
    a = tmp_path / "adrs2.csv"
    a.write_text("us_symbol,local_symbol,us_short_name_yfinance\n", encoding="utf-8")
    t2 = NE._Tables(p, a)
    ref = Counter()
    for text in ("Nvidia Shares Sink After Huang Ouster", "Since Ouster, the board has been quiet",
                 "The Oracle of Omaha buys more stock"):
        got = EN.strict_tickers(text, t2, refused=ref)
        assert "OUST" not in got and "ORCL" not in got, (text, got)
    assert ref["common_word:ouster"] == 2 and ref["common_word:oracle"] == 1
    assert "OUST" in EN.strict_tickers("Ouster Inc wins lidar order", t2)
    assert "OUST" in EN.strict_tickers("Ouster shares jump 20%", t2)
    assert "ORCL" in EN.strict_tickers("Oracle Corporation raises cloud forecast", t2)


def test_a_shared_person_bigram_joins_titles(tmp_path, monkeypatch):
    # three shared stems needed by tokens, so only the person bigram can join these
    monkeypatch.setattr(EN.C, "EVENT_NODES_JOIN_MIN_SHARED_TOKENS", 3)
    items = [EN.Item(key=f"k{i}", source="s", publisher=p, kind="article", title=t, url="",
                     first_seen=NOW + timedelta(hours=i), published=None,
                     title_tickers={"NVDA": "name:nvidia"})
             for i, (p, t) in enumerate([("A", "Nvidia names successor as Jensen Huang exits"),
                                         ("B", "Taiwan mourns as Jensen Huang leaves Nvidia"),
                                         ("C", "Nvidia ships new robotics rack to Europe")])]
    clusters, st = EN.cluster_items(items, _tbl(tmp_path))
    sizes = sorted(len(c.members) for c in clusters)
    assert sizes == [1, 2] and st["bigram_joins"] >= 1 and "Jensen Huang" in st["live_person_bigrams"]


def test_graph_and_calendar_built_after_now_are_refused(tmp_path):
    import pandas as pd
    g = tmp_path / "graph" / "ug_future"
    g.mkdir(parents=True)
    (g / "receipt.json").write_text(json.dumps({"built_utc": (NOW + timedelta(days=1)).isoformat(),
                                                "as_of": "x"}), encoding="utf-8")
    graph, meta = EN.select_graph(tmp_path / "graph", NOW)
    assert graph is None and meta["status"] == "GRAPH_BUILT_AFTER_NOW"
    cal = tmp_path / "cal"
    cal.mkdir()
    day = NOW.date().isoformat()
    pd.DataFrame([{"symbol": "NVDA", "date": pd.Timestamp(NOW.date() + timedelta(days=2)), "status": "X",
                   "timing": "AMC", "source": "s"}]).to_parquet(cal / f"calendar_{day}.parquet")
    (cal / f"calendar_{day}_receipt.json").write_text(json.dumps(
        {"written_utc": (NOW + timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ"),
         "window": [day, day]}), encoding="utf-8")
    out = EN.calendar_dates(cal, {"NVDA"}, NOW)
    assert out["status"] == "NO_CALENDAR_BY_NOW" and out["skipped_after_now"]
    later = EN.calendar_dates(cal, {"NVDA"}, NOW + timedelta(hours=2))
    assert later["status"] == "OK" and later["dates"]["NVDA"]
    node = {"primary_ticker": "NVDA", "evidence": [{"publisher": "X", "regions": [], "kind": "article",
                                                    "items_8k": [], "title": "t", "title_tickers": {},
                                                    "first_seen_utc": NOW.isoformat(), "item_key": "k"}]}
    EN.finalize_node(node, {"calendar": {"file": "c", "coverage_end": day, "dates": {}}}, now=NOW)
    assert any(d.startswith("CALENDAR_HORIZON_SHORT") for d in node["degradations"])


def test_forward_calendar_labels_on_the_node_not_covered_vs_no_date_vs_stale(tmp_path):
    """CH-35/CH-08: event nodes read next dates from the forward catalyst calendar, and
    a node says WHICH kind of 'no date' it has. Dates derived from NOW, no literal."""
    from backend.services import forward_calendar as FC

    def q(sym, d):
        ts = int(datetime(d.year, d.month, d.day, 21, tzinfo=timezone.utc).timestamp())
        return {"symbol": sym, "quoteType": "EQUITY", "earningsTimestamp": ts,
                "earningsTimestampStart": ts, "earningsTimestampEnd": ts,
                "isEarningsDateEstimate": False}

    def pull(tbl, at):
        clock = iter(at + timedelta(seconds=i) for i in range(1, 1000))
        FC.pull(list(tbl), tmp_path, fetch=lambda syms: {s: tbl[s] for s in syms if s in tbl},
                macro=False, now_fn=lambda: next(clock), sleep_fn=lambda s: None)

    day = FC.market_date(NOW)
    pull({"OLDCO": q("OLDCO", day + timedelta(days=10))}, NOW - timedelta(days=30))
    pull({"NVDA": q("NVDA", day + timedelta(days=5)),
          "QUIET": q("QUIET", day + timedelta(days=200))}, NOW - timedelta(hours=2))
    store = tmp_path / str(EN.C.FORWARD_CALENDAR_DIRNAME)
    assert EN.default_paths(tmp_path)["calendar"] == store
    cal = EN.calendar_dates(store, {"NVDA", "QUIET", "OLDCO", "NEVER"}, NOW)
    assert cal["status"] == "OK" and cal["writer"] == "scripts/forward_calendar.py pull"
    assert cal["dates"]["NVDA"][0]["date"] == (day + timedelta(days=5)).isoformat()
    assert cal["dates"]["QUIET"] == [] and "OLDCO" not in cal["dates"] and "NEVER" not in cal["dates"]
    want = {"NVDA": "DATE_IN_HORIZON", "QUIET": "NO_DATE_IN_HORIZON", "NEVER": "NOT_COVERED",
            "OLDCO": "CALENDAR_STALE"}
    for sym, label in want.items():
        node = {"primary_ticker": sym, "evidence": [{"publisher": "X", "regions": [], "kind": "article",
                                                     "items_8k": [], "title": "t", "title_tickers": {},
                                                     "first_seen_utc": NOW.isoformat(), "item_key": "k"}]}
        EN.finalize_node(node, {"calendar": cal}, now=NOW)
        assert node["next_dates_label"] == label, sym
        assert not any(d.startswith("CALENDAR_HORIZON_SHORT") for d in node["degradations"])
        flagged = [d for d in node["degradations"] if d.startswith("NEXT_DATES_")]
        assert bool(flagged) == (label in ("NOT_COVERED", "CALENDAR_STALE")), (sym, flagged)
        assert bool(node["next_dates"]) == (label == "DATE_IN_HORIZON")
    # before the first pull nothing is covered: no look-ahead into a later snapshot
    early = EN.calendar_dates(store, {"NVDA"}, NOW - timedelta(days=31))
    assert early["status"] == "NO_CALENDAR_BY_NOW" and early["labels"]["NVDA"]["label"] == "NOT_COVERED"


def test_forecasts_are_bounded_by_first_seen():
    rows = [{"made_at": (NOW - timedelta(hours=2)).isoformat()},
            {"made_at": (NOW + timedelta(hours=1)).isoformat()}]
    assert EN._forecasts_before(rows, NOW) == rows[:1]


def test_filing_weight_by_item_and_single_item_scores_zero():
    assert EN.filing_weight(["9.01"]) == 0.0
    assert EN.filing_weight(["5.02", "9.01"]) == 1.0
    assert EN.filing_weight(["5.07"]) < 0.2
    one = EN.importance([{"publisher": "SEC", "regions": ["US"], "kind": "filing", "items_8k": ["9.01"]}],
                        "X", {}, NOW)
    assert one["components"]["items"] == 0.0 and one["components"]["filing"] == 0.0


def test_cli_zero_rows_everywhere_is_rc2(tmp_path, monkeypatch, capsys):
    from scripts import event_nodes as CLI
    fake = {"build_id": "b", "since": "s", "now": "n",
            "read": {"rows_read": 0, "files": 0, "items": 0, "dropped_after_now": 0,
                     "dropped_published_after_now": 0, "dropped_undated": 0, "dropped_not_news": 0,
                     "rows_unresolved": 0, "bad_json_lines": 0, "filing_rows_without_first_seen": 0,
                     "rows_date_only_publication": 0, "per_source": {}, "newest_per_source": {}},
            "clustering": {"n_unclustered_no_title_issuer": 0, "join_gap_hours": 24, "join_threshold": 0.2},
            "graph": {}, "bars_last_session": None, "calendar": {}, "positions": {},
            "identity": {"n_stored_latest": 0, "n_versions": 0, "retire": []}, "parents": [], "nodes": []}
    monkeypatch.setattr(CLI.EN, "build", lambda *a, **k: fake)
    rc = CLI.main(["build", "--data-root", str(tmp_path), "--out", str(tmp_path / "o"),
                   "--now", NOW.isoformat()])
    assert rc == 2 and "NO_CORPUS_ROWS" in capsys.readouterr().out


def test_append_fill_refuses_an_unknown_node(tmp_path):
    store = tmp_path / EN.STORE_NAME
    EN.append_rows(store, [{"event_id": "ev_x", "content_hash": "h", "evidence": []}])
    with pytest.raises(EN.EventNodesRefused) as e:
        EN.append_fill(store, {"event_id": "ev_nope", "node_content_hash": "h"})
    assert e.value.code == EN.UNKNOWN_EVENT
    assert EN.append_fill(store, {"event_id": "ev_x", "node_content_hash": "h"})["appended"] == 1
