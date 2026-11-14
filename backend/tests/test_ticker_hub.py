"""CH-22 ticker hub: tagging rules (the common-word, boilerplate and digest traps), tiers,
row ids, dates, stories, related ranking, incremental build, generations and damage,
dead sources, and the route guards. Small synthetic fixtures under tmp_path; every
headline is invented; dates are derived from `now`, never written as calendar literals."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import news_entities as NE
from backend.services import ticker_hub as TH
from backend.tests.local_control import local_client

NOW = datetime.now(timezone.utc).replace(microsecond=0)
DAY = NOW.date().isoformat()

ISSUERS = """symbol,primary_name,aliases,country,is_adr
A,"Agilent Technologies, Inc.",A|Agilent Technologies,US,
ACA,Arcosa Inc.,ACA|Arcosa,US,
WAT,Waters Corporation,WAT|Waters Corporation,US,
UVV,Universal Corporation,UVV|Universal Corporation,US,
R,"Ryder System, Inc.","R|Ryder System, Inc.",US,
RS,Reliance Steel & Aluminum Co.,RS|Reliance Steel,US,
META,"Meta Platforms, Inc.","META|Meta Platforms, Inc.",US,
AAAA,Aardvark Chipworks Inc.,AAAA|Aardvark Chipworks,US,
AAPL,Apple Inc.,AAPL|Apple,US,
ALL,Allstate Corporation (The),ALL|Allstate Corporation (The),US,
FCF,First,FCF|First,US,
GOOGL,Alphabet Inc.,GOOGL|Alphabet|Google,US,
IT,"Gartner, Inc.","IT|Gartner, Inc.",US,
NOW,"ServiceNow, Inc.","NOW|ServiceNow, Inc.",US,
NVDA,NVIDIA Corporation,NVDA|NVIDIA Corporation,US,
ON,ON Semiconductor Corporation,ON|ON Semiconductor Corporation,US,
PPLI,People Incorporated,PPLI|People Incorporated,US,
QMCO,Quantum Corporation,QMCO|Quantum Corporation,US,
SOLI,Solidion Technology Inc.,SOLI|Solidion Technology,US,
TINY,Tinycap Widgets Inc.,TINY|Tinycap Widgets,US,
ZETA,Zetawave Semis Inc.,ZETA|Zetawave Semis,US,
FISI,"Financial Institutions, Inc.","FISI|Financial Institutions, Inc.",US,
"""

FILLER = "Lorem ipsum dolor sit amet. " * 40


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _row(src: str, title: str, *, minutes_ago: int = 30, url: str = "", body: str = "",
         tickers=None, tags=None, published: datetime | None = None) -> dict:
    t = NOW - timedelta(minutes=minutes_ago)
    pub = published if published is not None else t - timedelta(minutes=5)
    return {"source": src, "first_seen_utc": _iso(t), "published_utc": _iso(pub),
            "url": url or f"https://example.com/{abs(hash((src, title)))}", "title": title, "body": body,
            "lang": "en", "tickers": tickers or [], "entity_tags": tags or [], "raw_id": title[:20]}


def _append(root: Path, src: str, rows: list[dict]) -> None:
    p = root / "news_corpus" / src / f"{DAY}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _page(d: Path, name: str, **kw) -> None:
    base = {"publisher": "barrons", "page_kind": "article", "page_class": "OK", "published_utc": None,
            "reached_by": {"lane": "front"}, "tickers_named": [], "outbound_links": []}
    (d / name).write_text(json.dumps({**base, **kw}), encoding="utf-8")


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "optimus"
    (root / "official").mkdir(parents=True)
    (root / "official" / "company_tickers.json").write_text(
        json.dumps({"t": _iso(NOW), "map": {"1881551": "SOLI"}}), encoding="utf-8")
    (root / "potential_universe").mkdir()
    with (root / "potential_universe" / f"{DAY}.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"artefact": "header"}) + "\n")
        for s, sec, dv in (("NVDA", "Semiconductors", 9e10), ("ON", "Semiconductors", 1e9),
                           ("ZETA", "Semiconductors", 5e8), ("AAAA", "Semiconductors", 1e6),
                           ("AAPL", "Technology", 8e10), ("TINY", "Machinery", 1e6)):
            fh.write(json.dumps({"symbol": s, "identity": {"sector": sec},
                                 "execution": {"median_dollar_volume": dv}}) + "\n")
    _append(root, "wsj_tech", [
        _row("wsj_tech", "Nvidia Shares Slip in a Fixture Session", url="https://www.wsj.com/tech/nvda-1?mod=rss"),
        _row("wsj_tech", "Quantum Advances Could Reshape Online Banking Security",
             tickers=["QMCO"], tags=["resolved:QMCO=name"]),
        _row("wsj_tech", "IT spending rises (IT) as ON the move and ALL in", minutes_ago=40),
        _row("wsj_tech", "Gartner stock: $IT rallies; ON Semiconductor (NASDAQ: ON) beats", minutes_ago=50),
        _row("wsj_tech", "A quiet day for markets", minutes_ago=60),
        _row("wsj_tech", "Tinycap Widgets wins a contract", minutes_ago=70),
        _row("wsj_tech", "How Financial Institutions in Asia Train New Staff", minutes_ago=75),
        _row("wsj_tech", "Nvidia and ON Semiconductor Sign a Fixture Supply Deal", minutes_ago=80),
    ])
    _append(root, "google_news_rss_en_us", [
        _row("google_news_rss_en_us", "Storm leaves People stranded on a coastal road - The Daily Paper",
             tickers=["PPLI"], tags=["resolved:PPLI=name"]),
        _row("google_news_rss_en_us", "First snowfall of the season closes mountain passes - The Post",
             tickers=["FCF"], tags=["resolved:FCF=name"]),
        _row("google_news_rss_en_us", "Chip stocks: the people who sold - Fixture Weekly",
             tickers=["NVDA"], tags=["resolved:NVDA=cashtag"], minutes_ago=20),
    ])
    lane_row = _row("dj_reader_marketwatch", "Should I keep going to free annuity dinners?", tickers=["TINY"],
                    body="A reader asks about annuity sales pitches. " * 30)
    lane_row["fetcher"] = "web_reader"
    lane_ok = _row("dj_reader_marketwatch", "Tinycap Widgets Doubles Its Dividend", tickers=["TINY"], minutes_ago=31)
    lane_ok["fetcher"] = "web_reader"
    _append(root, "dj_reader_marketwatch", [lane_row, lane_ok])
    _append(root, "sec_edgar_8k_current_atom", [
        _row("sec_edgar_8k_current_atom", "8-K - Solidion Technology Inc. (0001881551) (Filer)",
             tags=["8-K:2.02", "cik:0001881551"]),
    ])
    d = root / "news_corpus" / "dowjones" / "barrons" / DAY
    d.mkdir(parents=True)
    _page(d, "aaa.json", url="https://www.barrons.com/articles/apple-x", title="Apple Shares Rise on Phone Sales | Barron's",
          first_seen_utc=_iso(NOW - timedelta(hours=2)), text="Apple said ...",
          reached_by={"lane": "search:AAPL", "ticker": "AAPL"}, tickers_named=["AAPL", "A"])
    _page(d, "ccc.json", url="https://www.barrons.com/articles/fed-1", title="Central Bank Pauses in Fixture Land",
          first_seen_utc=_iso(NOW - timedelta(hours=4)), text=FILLER + " Most read: Nvidia falls. " + FILLER)
    _page(d, "ddd.json", url="https://www.barrons.com/articles/chips-2", title="Chipmakers Drift Lower Into the Bell",
          first_seen_utc=_iso(NOW - timedelta(hours=5)),
          text=FILLER + " Nvidia led the decline. Nvidia fell 4%. " + FILLER)
    _page(d, "eee.json", url="https://www.barrons.com/articles/iran-3", title="Crude Eases as Fixture Talks Resume",
          first_seen_utc=_iso(NOW - timedelta(hours=6)),
          text="More Videos 01:21 Nvidia investigates its CEO 02:09 Will Huang remain CEO of Nvidia? "
               "Crude Eases as Fixture Talks Resume. " + FILLER, reached_by={"lane": "related"})
    _page(d, "ggg.json", url="https://www.barrons.com/articles/retire-4", title="Four Budget Habits for Savers in a Shaky Year",
          first_seen_utc=_iso(NOW - timedelta(hours=7)),
          text="Four Budget Habits for Savers in a Shaky Year. NVDA -3.2% " + FILLER, tickers_named=["NVDA"])
    _page(d, "hhh.json", url="https://www.barrons.com/articles/fruit-5",
          title="A Weekend Hunt for the Sweetest Apple at the Orchard", first_seen_utc=_iso(NOW - timedelta(hours=8)),
          text="A Weekend Hunt for the Sweetest Apple at the Orchard. An Apple a day; the Apple orchard sells "
               "to Tinycap Widgets. " + FILLER)
    _page(d, "bbb.json", url="https://www.barrons.com/", page_kind="front", title="front",
          first_seen_utc=_iso(NOW - timedelta(hours=3)),
          outbound_links=[{"url": "https://www.barrons.com/articles/nvda-y", "text": "Nvidia Stock Drifts Lower in a Synthetic Session"},
                          {"url": "https://www.barrons.com/subscribe", "text": "Subscribe"},
                          {"url": "https://www.barrons.com/q", "text": "Bond yields climb as the central bank waits"},
                          {"url": "https://www.barrons.com/quote/zeta", "text": "ZETA Zetawave Semis Inc. 12.34 -1.50 (-10.84%)"}])
    dg = root / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl"
    dg.parent.mkdir(parents=True)
    dg.write_text(json.dumps({"cache_key": "k", "row": {"url": "https://www.wsj.com/tech/nvda-1?mod=other",
                                                        "event_type": "earnings", "topic": "Nvidia results",
                                                        "sentiment": -0.3, "tickers": []}}) + "\n",
                  encoding="utf-8")
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


def _tiers(out: Path) -> dict[str, dict]:
    return {r["title"]: {t["t"]: t["tier"] for t in r["tags"]} for r in TH.iter_index_rows(out)}


# ─────────────────────────────── tagging

def test_tagging_rules_and_common_word_traps(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    rec = _build(data_root, paths, out)
    tags = _tags(out)
    assert not any("Storm leaves People" in t for t in tags), tags
    assert not any("First snowfall" in t for t in tags)
    assert not any(t.startswith("Quantum Advances") for t in tags)
    assert not any(t.startswith("IT spending") for t in tags)
    g = next(v for k, v in tags.items() if k.startswith("Gartner stock"))
    assert ("IT", "text_token") in g or ("IT", "name_match") in g
    assert ("ON", "text_token") in g or ("ON", "name_match") in g
    assert all(sym not in ("ALL", "A", "NOW") for sym, _ in g)
    chip = next(v for k, v in tags.items() if k.startswith("Chip stocks"))
    assert ("NVDA", "source_field") in chip
    assert ("NVDA", "name_match") in tags["Nvidia Shares Slip in a Fixture Session"]
    assert ("SOLI", "sec_cik") in next(v for k, v in tags.items() if "Solidion" in k)
    apple = tags["Apple Shares Rise on Phone Sales"]
    assert ("AAPL", "source_field") in apple and not any(s == "A" for s, _ in apple)
    assert ("NVDA", "name_match") in tags["Nvidia Stock Drifts Lower in a Synthetic Session"]
    assert "Subscribe" not in tags and "Bond yields climb as the central bank waits" not in tags
    assert ("TINY", "name_match") in tags["Tinycap Widgets wins a contract"]
    assert rec["rows_untagged_new"] >= 5 and rec["untagged_share_new"] is not None
    assert "A quiet day for markets" not in tags
    assert "Central Bank Pauses in Fixture Land" not in tags          # one sidebar mention
    assert ("NVDA", "name_match") in tags["Chipmakers Drift Lower Into the Bell"]
    assert not any("Financial Institutions" in t for t in tags)
    assert "Should I keep going to free annuity dinners?" not in tags
    assert ("TINY", "reader_lane") in tags["Tinycap Widgets Doubles Its Dividend"]
    assert "Crude Eases as Fixture Talks Resume" not in tags
    assert "Four Budget Habits for Savers in a Shaky Year" not in tags
    assert "A Weekend Hunt for the Sweetest Apple at the Orchard" not in tags
    assert not any(t.startswith("ZETA Zetawave") for t in tags)       # a quote chip, not news
    assert rec["counts"]["quote_chips_skipped"] >= 1
    assert rec["counts"].get("reader_lane_unconfirmed", 0) >= 1


def test_google_news_boilerplate_never_tags_the_aggregator(tmp_path, data_root, paths):
    """Review F1: every Google News cluster body ends with a 'full coverage' link in the
    edition's language; one 'Google' in it tagged GOOGL on ~4,100 unrelated rows."""
    for i, phrase in enumerate(("View Full Coverage on Google News", "Google ニュースで見出しと意見をもっと見る",
                                "在Google 新闻上查看更多头条新闻和观点")):
        body = ('<ol><li><a href="https://news.google.com/rss/articles/x">Storm hits a coastal town</a>&nbsp;'
                '<font color="#6f6f6f">Local Paper</font></li></ol><strong><a href="https://news.google.com/stories/y">'
                f'{phrase}</a></strong>')
        _append(data_root, "google_news_rss_en_gb", [_row("google_news_rss_en_gb", f"Storm hits coastal town {i} - Local Paper",
                                                           body=body)])
    # the same text WITHOUT the story link still names Google once in a short body: not a tag
    _append(data_root, "google_news_rss_en_gb", [_row("google_news_rss_en_gb", "Harbour fireworks delayed - Local Paper",
                                                       body="Harbour fireworks delayed. See more on Google News")])
    # a short body naming a company once by NAME does not tag; an explicit symbol does (mentions tier)
    _append(data_root, "google_news_rss_en_gb", [
        _row("google_news_rss_en_gb", "Factory reopens after floods - Local Paper", body="Tinycap Widgets staff return."),
        _row("google_news_rss_en_gb", "Factory output recovers - Local Paper", body="Shares of $TINY rose."),
    ])
    out = tmp_path / "hub"
    rec = _build(data_root, paths, out)
    tags = _tags(out)
    assert not any("Storm hits coastal town" in k for k in tags), "unrelated GN cluster tagged"
    assert "Harbour fireworks delayed" not in tags
    assert "Factory reopens after floods" not in tags
    assert ("TINY", "text_token") in tags["Factory output recovers"]
    assert _tiers(out)["Factory output recovers"]["TINY"] == "mentions"
    assert rec["counts"].get("quote_chips_skipped", 0) >= 1


def test_digest_ticker_needs_the_text_and_ranks_last(tmp_path, data_root, paths):
    """Review F2: the digest's 'First' -> FCF was taken verbatim and ranked above titles."""
    dg = data_root / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl"
    _append(data_root, "google_news_rss_en_us", [
        _row("google_news_rss_en_us", "First Thing: storm closes airports - The Daily",
             url="https://www.example.org/first-thing-x"),
        _row("google_news_rss_en_us", "Tinycap Widgets opens a plant - The Daily", url="https://www.example.org/tiny-y"),
    ])
    with dg.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cache_key": "k2", "row": {"url": "https://www.example.org/first-thing-x",
                                                        "event_type": "other", "tickers": ["FCF"]}}) + "\n")
        fh.write(json.dumps({"cache_key": "k3", "row": {"url": "https://www.example.org/tiny-y",
                                                        "event_type": "product", "tickers": ["TINY"]}}) + "\n")
    out = tmp_path / "hub"
    rec = _build(data_root, paths, out)
    tags = _tags(out)
    assert not any("First Thing" in k for k in tags), "digest FCF from 'First' accepted"
    assert tags["Tinycap Widgets opens a plant"] == [("TINY", "name_match")]   # the title decides, not the digest
    assert rec["counts"]["digest_unconfirmed"] >= 1


def test_tiers_about_is_the_title_or_the_filing(tmp_path, data_root, paths):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    tiers = _tiers(out)
    assert tiers["Nvidia Shares Slip in a Fixture Session"]["NVDA"] == "about"
    assert tiers["Chipmakers Drift Lower Into the Bell"]["NVDA"] == "mentions"     # body only
    assert tiers["Chip stocks: the people who sold"]["NVDA"] == "mentions"          # provider field only
    assert next(v for k, v in tiers.items() if "Solidion" in k)["SOLI"] == "about"   # SEC by CIK
    h_about = TH.hub("NVDA", data_root=data_root, out=out, now=NOW)
    h_all = TH.hub("NVDA", data_root=data_root, out=out, now=NOW, tier="all")
    ta = {r["title"] for r in h_about["news"]}
    tall = {r["title"] for r in h_all["news"]}
    assert "Chipmakers Drift Lower Into the Bell" not in ta and "Chipmakers Drift Lower Into the Bell" in tall
    assert all(r["tier"] == "about" for r in h_about["news"])
    assert h_about["tier_counts"]["about"] < h_about["tier_counts"]["all"]



def test_explicit_tokens_need_to_be_unambiguous(tmp_path, data_root, paths):
    """The re-measured sample: "Affordable Care Act (ACA)" -> ACA, "MESA(R)" -> R, "$A" -> A.
    A bare (XYZ) needs the issuer named in the same text; a one-letter token never tags."""
    _append(data_root, "wsj_business", [
        _row("wsj_business", "Insurer wins an Affordable Care Act (ACA) contract in Texas"),
        _row("wsj_business", "Spine maker clears review for its MESA(R) implant"),
        _row("wsj_business", "Fixture bank lifts its outlook", body="Shares of $A traded higher after the call."),
        _row("wsj_business", "Meta (META) Draws Fresh Fixture Scrutiny"),
        _row("wsj_business", "Arcosa (ACA) wins a bridge order"),
        _row("wsj_business", "Drone threat grows near fixture coastal Waters"),
        _row("wsj_business", "Universal early schooling plan wins fixture backing"),
        _row("wsj_business", "Waters Corp shares rise after fixture results"),
    ])
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    tags = _tags(out)
    assert "Insurer wins an Affordable Care Act (ACA) contract in Texas" not in tags
    assert "Spine maker clears review for its MESA(R) implant" not in tags
    assert "Fixture bank lifts its outlook" not in tags
    meta = tags["Meta (META) Draws Fresh Fixture Scrutiny"]
    assert ("META", "text_token") in meta or ("META", "name_match") in meta
    assert any(s == "ACA" for s, _ in tags["Arcosa (ACA) wins a bridge order"])
    # surname / place / adjective names need an attached cue (about-tier sample: WAT, UVV)
    assert "Drone threat grows near fixture coastal Waters" not in tags
    assert "Universal early schooling plan wins fixture backing" not in tags
    assert ("WAT", "name_match") in tags["Waters Corp shares rise after fixture results"]


def test_digest_never_confirms_by_a_filing_title(tmp_path, data_root, paths):
    """A filing's title is the filer's name: 'Reliance Global Group' is not RS (sample)."""
    _append(data_root, "sec_edgar_8k_current_atom", [
        _row("sec_edgar_8k_current_atom", "8-K - Reliance Steel Global Fixture Group (0009999999) (Filer)",
             url="https://www.sec.gov/fixture/rs-1", tags=["8-K:8.01", "cik:0009999999"])])
    dg = data_root / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl"
    with dg.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cache_key": "k9", "row": {"url": "https://www.sec.gov/fixture/rs-1",
                                                        "event_type": "other", "tickers": ["RS"]}}) + "\n")
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    assert not any("Reliance Steel Global Fixture Group" in k for k in _tags(out))

# ─────────────────────────────── ids, dates, stories

def test_row_id_keeps_different_non_latin_headlines_apart_and_old_cache_is_rebuilt(tmp_path, data_root, paths):
    """Review F5: v1 kept only [a-z0-9] of a title, so two Chinese headlines with 'AI' collided."""
    _append(data_root, "google_news_rss_zh_cn", [
        _row("google_news_rss_zh_cn", "AI芯片概念股大涨 英伟达领涨 - 中山网", url="https://e.cn/1"),
        _row("google_news_rss_zh_cn", "AI监管新规出台 英伟达回应 - 中山网", url="https://e.cn/2"),
    ])
    assert TH.row_id("s", "AI芯片概念股大涨", "u1") != TH.row_id("s", "AI监管新规出台", "u2")
    out = tmp_path / "hub"
    out.mkdir()
    (out / "state.json").write_text("{}", encoding="utf-8")                      # a v1 cache
    (out / "rows_2026-01.jsonl").write_text('{"id":"x","title":"old"}\n', encoding="utf-8")
    rec = _build(data_root, paths, out)
    assert rec["counts"]["v1_files_removed"] >= 2
    titles = [r["title"] for r in TH.iter_index_rows(out)]
    assert "AI芯片概念股大涨 英伟达领涨" in titles and "AI监管新规出台 英伟达回应" in titles
    assert "old" not in titles


def test_published_time_places_the_row_and_old_articles_are_not_recent(tmp_path, data_root, paths):
    """Review F6: a 2-year-old article first seen today read as today's news."""
    _append(data_root, "wsj_tech", [
        _row("wsj_tech", "Nvidia Archive Piece From Long Ago", minutes_ago=10, published=NOW - timedelta(days=700)),
        _row("wsj_tech", "Nvidia Two Days Old Fixture Note", minutes_ago=10, published=NOW - timedelta(days=2)),
    ])
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    h = TH.hub("NVDA", data_root=data_root, out=out, now=NOW, days=30)
    titles = {r["title"]: r for r in h["news"]}
    assert "Nvidia Archive Piece From Long Ago" not in titles
    two = titles["Nvidia Two Days Old Fixture Note"]
    assert two["eff_utc"] == two["published_utc"] and two["show_both_times"] is True
    h3 = TH.hub("NVDA", data_root=data_root, out=out, now=NOW, days=1)
    assert "Nvidia Two Days Old Fixture Note" not in {r["title"] for r in h3["news"]}


def test_copies_of_one_story_are_one_story_with_a_count(tmp_path, data_root, paths):
    _append(data_root, "wsj_markets", [_row("wsj_markets", "Nvidia Shares Slip in a Fixture Session",
                                            url="https://www.wsj.com/tech/nvda-1?mod=markets")])
    _append(data_root, "google_news_rss_en_sg", [_row("google_news_rss_en_sg", "Nvidia Shares Slip in a Fixture Session - WSJ")])
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    h = TH.hub("NVDA", data_root=data_root, out=out, now=NOW)
    st = [r for r in h["news"] if r["title"] == "Nvidia Shares Slip in a Fixture Session"]
    assert len(st) == 1 and st[0]["copies"] == 3
    assert set(st[0]["sources"]) == {"wsj_tech", "wsj_markets", "google_news_rss_en_sg"}
    assert h["coverage"]["n_stories"] < h["coverage"]["n_rows"]


def test_news_pages_load_more(tmp_path, data_root, paths):
    _append(data_root, "wsj_tech", [_row("wsj_tech", f"Nvidia fixture headline number {i}", minutes_ago=100 + i)
                                    for i in range(12)])
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    p1 = TH.news("NVDA", data_root=data_root, out=out, now=NOW, limit=5)
    p2 = TH.news("NVDA", data_root=data_root, out=out, now=NOW, limit=5, offset=5)
    assert p1["coverage"]["has_more"] and len(p1["news"]) == 5 and len(p2["news"]) == 5
    assert not ({r["id"] for r in p1["news"]} & {r["id"] for r in p2["news"]})


def test_related_peers_ranked_by_comention_then_dollar_volume(tmp_path, data_root, paths):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    rel = [r for r in TH.hub("NVDA", data_root=data_root, out=out, now=NOW)["related"] if r["link"] == "same_sector"]
    order = [r["ticker"] for r in rel]
    assert order[:3] == ["ON", "ZETA", "AAAA"]          # ON co-mentioned; then by dollar volume, not A-Z
    assert rel[0]["n"] >= 1 and "co-mention" in rel[0]["rank_by"].replace("name both", "co-mention")


# ─────────────────────────────── incremental, generations, damage

def test_incremental_build_reads_only_new_rows(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    first = _build(data_root, paths, out)
    n0 = first["rows_in_index"]
    again = _build(data_root, paths, out, now=NOW + timedelta(seconds=5))
    assert again["rows_read_new"] == 0 and again["rows_in_index"] == n0
    _append(data_root, "wsj_tech", [_row("wsj_tech", "Nvidia (NVDA) unveils a fixture chip", minutes_ago=1)])
    third = _build(data_root, paths, out, now=NOW + timedelta(seconds=10))
    assert third["rows_read_new"] == 1 and third["rows_in_index"] == n0 + 1
    gens = [p.name for p in out.iterdir() if p.is_dir() and p.name.startswith("g_")]
    assert len(gens) <= int(TH.C.TICKER_HUB_KEEP_GENERATIONS)
    shutil.rmtree(data_root / "news_corpus")             # a request never needs the corpus
    h = TH.hub("NVDA", data_root=data_root, out=out, now=NOW + timedelta(seconds=20))
    assert any(r["title"] == "Nvidia (NVDA) unveils a fixture chip" for r in h["news"])


def test_rows_first_seen_after_the_build_clock_wait_for_the_next_build(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _append(data_root, "wsj_tech", [_row("wsj_tech", "Nvidia (NVDA) future headline", minutes_ago=-60)])
    d = data_root / "news_corpus" / "dowjones" / "ft" / DAY
    d.mkdir(parents=True)
    _page(d, "fff.json", publisher="ft", url="https://www.ft.com/", page_kind="front", title="ft",
          first_seen_utc=_iso(NOW + timedelta(minutes=30)),
          outbound_links=[{"url": "https://www.ft.com/content/x", "text": "Nvidia faces fixture lawsuit questions after exit"}])
    first = _build(data_root, paths, out)
    titles = {r["title"] for r in TH.iter_index_rows(out)}
    assert "Nvidia (NVDA) future headline" not in titles
    assert first["counts"]["deferred_after_now"] == 2
    _build(data_root, paths, out, now=NOW + timedelta(hours=2))
    titles = {r["title"] for r in TH.iter_index_rows(out)}
    assert {"Nvidia (NVDA) future headline", "Nvidia faces fixture lawsuit questions after exit"} <= titles


def _copy(out: Path, tmp_path: Path, name: str) -> tuple[Path, Path]:
    dst = tmp_path / name
    shutil.copytree(out, dst)
    return dst, TH.current_dir(dst)


def test_a_damaged_index_is_red_by_name_never_ok_404_or_500(data_root, paths, tmp_path):
    """Review F7, each case on a copy: truncated postings, rows out of step with postings,
    a corrupt universe, a missing forecasts file, a corrupt CURRENT."""
    from scripts import ticker_hub as cli
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    assert TH.verify(out)["status"] == "OK"
    month = NOW.strftime("%Y-%m")

    a, ga = _copy(out, tmp_path, "trunc")
    p = ga / f"postings_{month}.json"
    p.write_bytes(p.read_bytes()[: p.stat().st_size // 2])
    h = TH.hub("NVDA", data_root=data_root, out=a, now=NOW)
    assert h["coverage"]["status"] == "DEGRADED"
    assert any("postings" in x for x in h["coverage"]["problems"])
    assert cli.main(["verify", "--data-root", str(data_root), "--out", str(a)]) == 2

    b, gb = _copy(out, tmp_path, "step")
    rp = gb / f"rows_{month}.jsonl"
    lines = rp.read_bytes().splitlines(keepends=True)
    rp.write_bytes(lines[0][:-1] + b" \n" + b"".join(lines[1:]))       # every later offset shifts by one byte
    h = TH.hub("NVDA", data_root=data_root, out=b, now=NOW)
    assert h["coverage"]["status"] == "DEGRADED"

    c, gc = _copy(out, tmp_path, "uni")
    (gc / "universe.json").write_text("{not json", encoding="utf-8")
    h = TH.hub("NVDA", data_root=data_root, out=c, now=NOW)            # no KeyError -> no 404
    assert h["coverage"]["status"] == "DEGRADED"
    assert any("UNIVERSE" in x or "universe" in x for x in h["coverage"]["problems"])

    e, ge = _copy(out, tmp_path, "fc")
    (ge / "forecasts.jsonl").unlink()
    h = TH.hub("NVDA", data_root=data_root, out=e, now=NOW)            # no FileNotFoundError -> no 500
    assert h["forecasts"]["status"] == "FORECASTS_MISSING" and h["coverage"]["status"] == "DEGRADED"

    f, _gf = _copy(out, tmp_path, "cur")
    (f / TH.CURRENT_NAME).write_text("{trunc", encoding="utf-8")
    assert TH.index_status(f, NOW)["status"] == "DEGRADED"


def test_dead_sources_are_listed_with_their_age(tmp_path, data_root, paths):
    _append(data_root, "alpaca_benzinga_news", [_row("alpaca_benzinga_news", "Nvidia fixture wire story",
                                                     minutes_ago=60 * 24 * 5)])
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    st = TH.index_status(out, NOW)
    stale = {x["source"] for x in st["stale_sources"]}
    assert "alpaca_benzinga_news" in stale and "wsj_tech" not in stale
    ages = {x["source"]: x for x in st["sources"]}
    assert ages["alpaca_benzinga_news"]["age_hours"] > 48


def test_stale_flag_compares_the_build_time_with_now(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    later = NOW + timedelta(hours=float(TH.C.TICKER_HUB_STALE_HOURS) + 1)
    h = TH.hub("NVDA", data_root=data_root, out=out, now=later)
    assert h["coverage"]["status"] == "STALE" and h["coverage"]["index_age_s"] > 3600
    assert TH.index_status(tmp_path / "nothing_here", NOW)["status"] == "NO_INDEX"


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


def test_cli_build_and_verify_exit_codes(data_root, paths, tmp_path, monkeypatch, capsys):
    from scripts import ticker_hub as cli
    monkeypatch.setattr(NE, "entities_dir", lambda: paths["issuers"].parent)   # holds issuers.csv
    rc = cli.main(["build", "--data-root", str(data_root), "--out", str(tmp_path / "hub"), "--now", _iso(NOW)])
    out = capsys.readouterr().out
    assert rc == 0 and "rows read (new)" in out and "tags in the index by method" in out and "verify: OK" in out
    assert cli.main(["verify", "--data-root", str(data_root), "--out", str(tmp_path / "hub")]) == 0
    empty = tmp_path / "empty"
    (empty / "news_corpus").mkdir(parents=True)
    assert cli.main(["build", "--data-root", str(empty), "--out", str(tmp_path / "o3")]) == 2
    assert cli.main(["build", "--data-root", str(tmp_path / "nope"), "--out", str(tmp_path / "o4")]) == 2


def test_hub_payload_forecasts_and_typed_event(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    h = TH.hub("nvda", data_root=data_root, out=out, days=30, now=NOW)
    assert h["ticker"] == "NVDA"
    stamps = [r["eff_utc"] for r in h["news"]]
    assert stamps == sorted(stamps, reverse=True)
    wsj = next(r for r in h["news"] if r["title"] == "Nvidia Shares Slip in a Fixture Session")
    assert wsj["event"]["event_type"] == "earnings"
    assert wsj["tagged_by"] == ["name_match"]
    fc = h["forecasts"]
    assert fc["counts"]["open"] == 1 and fc["counts"]["resolved"] == 1
    assert fc["resolved"][0]["realised_return"] == 0.03
    assert h["coverage"]["status"] == "OK"
    with pytest.raises(KeyError):
        TH.hub("ZZZZ", data_root=data_root, out=out, now=NOW)


def test_feed_filters_and_facets(data_root, paths, tmp_path):
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    f = TH.feed(data_root=data_root, out=out, sector="Semiconductors", days=30, now=NOW)
    assert f["rows"] and all(any(t["t"] in ("NVDA", "ON", "ZETA", "AAAA") for t in r["tags"]) for r in f["rows"])
    assert {x["key"] for x in f["facets"]["sector"]} >= {"Semiconductors"}
    f2 = TH.feed(data_root=data_root, out=out, ticker="NVDA", source="wsj_tech", days=30, now=NOW)
    assert f2["rows"] and all(r["source"] == "wsj_tech" for r in f2["rows"])
    with pytest.raises(KeyError):
        TH.feed(data_root=data_root, out=out, ticker="ZZZZ", now=NOW)


# ─────────────────────────────── routes

def test_routes_guarded_403_404_and_dns_rebinding(data_root, paths, tmp_path, monkeypatch):
    from backend.routers import ticker_hub as R
    out = tmp_path / "hub"
    _build(data_root, paths, out)
    app = FastAPI()
    app.include_router(R.router)
    c = local_client(app)
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    assert c.get("/api/control/ticker/NVDA/hub").status_code == 403
    assert c.get("/api/control/news/feed?ticker=NVDA").status_code == 403
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    monkeypatch.setattr(TH, "default_data_root", lambda: data_root)
    monkeypatch.setattr(TH, "hub_dir", lambda dr, o=None: out)
    r = c.get("/api/control/ticker/NVDA/hub?days=30")
    assert r.status_code == 200 and r.json()["news"]
    assert c.get("/api/control/ticker/NVDA/news?offset=0&limit=2&tier=all").status_code == 200
    assert c.get("/api/control/ticker/ZZZZ/hub").status_code == 404
    assert c.get("/api/control/news/feed?ticker=ZZZZ").status_code == 404
    assert c.get("/api/control/ticker/NV%3BDA/hub").status_code == 422
    assert c.get("/api/control/news/feed?sector=Semiconductors").status_code == 200
    # DNS rebinding: an attacker's name resolving to 127.0.0.1 -> Host is not loopback
    rebind = TestClient(app, base_url="http://evil.example:8000")
    assert rebind.get("/api/control/ticker/NVDA/hub").status_code == 403
    assert rebind.get("/api/control/news/feed").status_code == 403
    cross = local_client(app, headers={"Origin": "http://evil.example"})
    assert cross.get("/api/control/ticker/NVDA/hub").status_code == 403
