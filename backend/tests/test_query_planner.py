"""Chunk C7 (2026-10-06): the search-led query planner, the Dow Jones feeds
owner and the WSJ retired-URL fix, OpenClaw spend on `llm_usage()`, and the
consent-dismiss rule. Offline: every agent turn, transcript read, gateway probe
and HTTP GET is a fake; the suite blocks sockets anyway."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as _config
from backend.services import dowjones_feeds as DF
from backend.services import query_planner as QP
from backend.services import reader_scheduler as RS
from backend.services import web_reader as WR
from backend.tests.test_reader_browse_lane import (  # noqa: F401  (`ledger` is a fixture)
    CNBC_A2, X_POST, _drain, _pages, _pool, ledger)
from backend.tests.test_reader_pool import FakeDriver

FIX = Path(__file__).parent / "fixtures" / "news"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
DAY = NOW.date().isoformat()

SEEDS = {"held_names": [f"T{i}" for i in range(30)],
         "themes": [{"title": f"Theme number {i}", "keywords": ["oil", "rates"]}
                    for i in range(20)],
         "opportunities": [f"OPP{i}" for i in range(20)]}


# ════════════════════════════════ the budget ═════════════════════════════════

def test_a_run_never_exceeds_the_run_day_or_lane_budget():
    bud = {"day": 10, "run": 4, "lanes": {"held_names": 5, "themes": 3, "opportunities": 1}}
    ledger: list[dict] = []
    n_runs = 0
    while True:
        qs = QP.plan_queries(SEEDS, day=DAY, ledger=ledger, bud=bud)
        if not qs:
            break
        n_runs += 1
        assert len(qs) <= bud["run"]
        ledger += [{**q, "t": NOW.isoformat(), "status": "OK"} for q in qs]
        assert n_runs < 20
    today = [r for r in ledger if r["day"] == DAY]
    assert len(today) <= bud["day"]
    for lane, cap in bud["lanes"].items():
        assert sum(1 for r in today if r["seed_lane"] == lane) <= cap
    # lane caps sum to 9 < day cap 10: the lanes bind
    assert len(today) == 9
    # every query id is unique and every query text is plain words
    assert len({r["query_id"] for r in today}) == len(today)
    assert all(QP.clean_text(r["text"]) == r["text"] for r in today)


def test_one_run_covers_every_lane_before_any_lane_twice_and_rotates_seeds():
    bud = {"day": 24, "run": 3, "lanes": {"held_names": 12, "themes": 8, "opportunities": 4}}
    qs = QP.plan_queries(SEEDS, day=DAY, ledger=[], bud=bud)
    assert [q["seed_lane"] for q in qs] == ["held_names", "themes", "opportunities"]
    # yesterday's seeds go to the back of the line today
    yday = (NOW - timedelta(days=1)).date().isoformat()
    led = [{**q, "day": yday, "t": (NOW - timedelta(days=1)).isoformat()} for q in qs]
    qs2 = QP.plan_queries(SEEDS, day=DAY, ledger=led, bud=bud)
    assert {q["seed"] for q in qs2}.isdisjoint({q["seed"] for q in qs})


def test_x_search_is_templated_only_when_the_agent_is_offered_it():
    agent_x = [QP.templates("held_names", "NVDA", i, mode="agent", x_offered=True)
               for i in range(6)]
    assert [t for t, _ in agent_x].count("x_search") == 2 and ("x_search", "$NVDA") in agent_x
    agent_no_x = [QP.templates("held_names", "NVDA", i, mode="agent") for i in range(6)]
    assert {t for t, _ in agent_no_x} == {"web_search"}
    assert QP.templates("themes", {"title": "Oil", "keywords": ["opec"]}, 0,
                        mode="agent")[0] == "web_search"


def test_with_no_provider_the_same_seeds_go_to_the_zero_dollar_sources():
    free = [QP.templates("held_names", "NVDA", i) for i in range(3)]
    assert free == [("gnews_rss", "NVDA stock"), ("gnews_rss", "NVDA stock"),
                    ("edgar_fts", "NVDA")]
    assert QP.templates("themes", {"title": "Oil", "keywords": ["opec"]}, 0)[0] == "gnews_rss"
    assert [QP.templates("opportunities", "VKTX", i)[0] for i in range(2)] \
        == ["gnews_rss", "edgar_fts"]
    qs = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=24)
    assert {q["tool"] for q in qs} <= set(QP.FREE_SOURCES)


def test_the_prompt_asks_for_one_tool_and_forbids_browsing():
    q = {"tool": "web_search", "text": "NVDA stock news this week"}
    p = QP.prompt(q)
    assert "web_search tool exactly once" in p and "Do not open, fetch or browse" in p
    assert "sign in" in p and "message anyone" in p


def test_urls_are_parsed_from_json_or_prose_and_capped():
    assert QP.parse_urls('{"urls": ["https://a.com/1", "https://a.com/1", "https://b.com/2"]}') \
        == ["https://a.com/1", "https://b.com/2"]
    assert QP.parse_urls("see https://www.cnbc.com/x.html, and (https://x.com/a/status/1).") \
        == ["https://www.cnbc.com/x.html", "https://x.com/a/status/1"]
    many = json.dumps({"urls": [f"https://a.com/{i}" for i in range(20)]})
    assert len(QP.parse_urls(many, max_urls=6)) == 6
    assert QP.parse_urls("") == [] and QP.parse_urls("nothing here") == []


# ════════════════════════════════ the classifier ═════════════════════════════

@pytest.mark.parametrize("url,verdict", [
    ("https://www.cnbc.com/2026/10/06/a.html", "admitted"),
    ("https://www.wsj.com/articles/x", "admitted"),
    ("https://x.com/someone/status/1", "admitted"),
    ("https://www.some-new-blog.com/post", "quarantined"),
    ("https://seekingalpha.com/news/1", "quarantined"),
    ("https://www.youtube.com/watch?v=abc", "refused"),
    ("https://www.instagram.com/p/x", "refused"),
    ("https://www.perplexity.ai/search?q=x", "refused"),
    ("https://duckduckgo.com/html/?q=x", "refused"),
    ("https://www.chase.com/", "refused"),
    ("https://mail.google.com/mail/u/0", "refused"),
    ("https://app.alpaca.markets/", "refused"),
    ("https://www.barrons.com/checkout/subscribe", "refused"),
    ("ftp://example.com/x", "refused"),
    ("https://user:pw@www.cnbc.com/x", "refused"),
])
def test_refused_stays_refused_and_a_new_host_is_quarantined(url, verdict):
    assert QP.classify_url(url)[0] == verdict


def test_no_refused_host_is_ever_admitted_from_the_configured_lists():
    from backend.services import browser_policy as BP
    for h in (*WR.NEVER_HOSTS, *BP.MONEY_HOSTS, *BP.CHECKOUT_HOSTS,
              *_config.QUERY_PLANNER_REFUSED_HOSTS):
        assert QP.classify_url(f"https://{h}/anything")[0] == "refused", h


# ════════════════════════════════ the run ════════════════════════════════════

def _fake_agent(replies: dict):
    calls = []

    def agent(msg_file, *, model, timeout, purpose, session_id):
        text = Path(msg_file).read_text(encoding="utf-8")
        calls.append({"purpose": purpose, "session_id": session_id, "prompt": text})
        qid = purpose.rsplit(":", 1)[-1]
        return {"status": "OK", "reply": replies.get(qid, '{"urls": []}'),
                "priced_cost_usd": 0.004, "usage": {"input": 1, "output": 1},
                "call_id": f"c-{qid}"}
    agent.calls = calls
    return agent


def _fired(tool_by_session=None):
    def calls(session_id, since):
        if tool_by_session is None:
            return [{"agent": "main", "session": f"agent:main:explicit:{session_id}",
                     "tool": "web_search"}]
        return tool_by_session(session_id)
    return calls


def _run(tmp_path, agent, *, calls=None, scope=None, gateway=True, max_q=3, seeds=None,
         provider="declared-for-test", stored=None, **kw):
    """An AGENT-mode run (a provider declared for the test), every seam faked."""
    return QP.run(max_queries=max_q, opt=tmp_path, now=NOW, agent_fn=agent,
                  tool_calls_fn=calls or _fired(), release_fn=lambda s: True,
                  scope_fn=scope or (lambda: {"verdict": "OK"}),
                  gateway_fn=lambda: gateway, seeds_fn=lambda: seeds or SEEDS,
                  provider=provider, stored_fn=lambda: set(stored or ()), **kw)


AGENT = {"mode": "agent"}


def test_a_new_host_is_quarantined_never_queued_and_refused_never_queued(tmp_path):
    plan = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=3, **AGENT)
    replies = {plan[0]["query_id"]: json.dumps({"urls": [
        "https://www.cnbc.com/2026/10/06/a.html", "https://www.brand-new-host.io/a",
        "https://www.youtube.com/watch?v=1", "https://www.chase.com/login"]})}
    agent = _fake_agent(replies)
    rec = _run(tmp_path, agent)
    assert rec["status"] == "OK" and len(agent.calls) == 3
    queued = QP._read_jsonl(QP.queue_path(tmp_path))
    assert [r["url"] for r in queued] == ["https://www.cnbc.com/2026/10/06/a.html"]
    assert queued[0]["query_id"] == plan[0]["query_id"]
    assert queued[0]["discovered_via"] == "web_search" and queued[0]["first_seen_utc"]
    quar = QP._read_jsonl(QP.quarantine_path(tmp_path))
    assert [r["host"] for r in quar] == ["www.brand-new-host.io"]
    assert quar[0]["review"].startswith("PENDING")
    t = rec["totals"]
    assert (t["admitted"], t["quarantined"], t["refused"]) == (1, 1, 2)
    assert Path(rec["path"]).name == f"query_planner_{rec['run_id']}.json"
    assert json.loads(Path(rec["path"]).read_text(encoding="utf-8"))["run_id"] == rec["run_id"]
    # the ledger has one row per query, with its verdict counts
    led = QP._read_jsonl(QP.ledger_path(tmp_path))
    assert len(led) == 3 and led[0]["verdicts"] == {"admitted": 1, "quarantined": 1,
                                                    "refused": 2}


def test_urls_from_a_turn_whose_search_tool_never_fired_are_refused(tmp_path):
    plan = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=1, **AGENT)
    agent = _fake_agent({plan[0]["query_id"]: '{"urls": ["https://www.cnbc.com/x.html"]}'})
    rec = _run(tmp_path, agent, calls=lambda sid, since: [], max_q=1)
    assert rec["queries"][0]["tool_fired"] is False
    assert rec["queries"][0]["urls"][0]["verdict"] == "refused"
    assert "NO_TOOL_CALL" in rec["queries"][0]["urls"][0]["reason"]
    assert QP._read_jsonl(QP.queue_path(tmp_path)) == []


def test_a_tool_call_outside_the_read_set_stops_the_run(tmp_path):
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, calls=lambda sid, since: [
        {"agent": "main", "session": sid, "tool": "web_search"},
        {"agent": "main", "session": sid, "tool": "exec"}])
    assert rec["status"] == "REFUSED" and "SCOPE_VIOLATION" in rec["refusal"]
    assert len(agent.calls) == 1


@pytest.mark.parametrize("scope,gateway,why", [
    ({"verdict": "UNSAFE", "config_problems": ["main: LLM turns can reach ['exec']"]}, True,
     "UNSAFE"),
    ({"verdict": "CANNOT_DETERMINE"}, True, "CANNOT_DETERMINE"),
    ({"verdict": "OK"}, False, "gateway not reachable"),
])
def test_an_unsafe_scope_or_a_dead_gateway_refuses_before_any_turn(tmp_path, scope, gateway,
                                                                    why):
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, scope=lambda: scope, gateway=gateway)
    assert rec["status"] == "REFUSED" and why in rec["refusal"]
    assert agent.calls == []
    assert rec["yield"]["zero_kind"] == "NO_QUERIES_RAN"
    assert Path(rec["path"]).exists()                    # a refusal still writes its receipt


def test_the_stop_file_and_the_due_rule_write_a_receipt_and_issue_nothing(tmp_path):
    QP.stop_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    QP.stop_path(tmp_path).write_text("x")
    agent = _fake_agent({})
    assert _run(tmp_path, agent)["status"] == "REFUSED"
    QP.stop_path(tmp_path).unlink()
    QP._append_jsonl(QP.ledger_path(tmp_path), [{"t": (NOW - timedelta(hours=1)).isoformat(),
                                                 "day": DAY, "query_id": "x"}])
    rec = QP.run(due_only=True, opt=tmp_path, now=NOW, agent_fn=agent,
                 scope_fn=lambda: {"verdict": "OK"}, gateway_fn=lambda: True,
                 seeds_fn=lambda: SEEDS)
    assert rec["status"] == "NOT_DUE" and agent.calls == []


def test_the_daily_admitted_cap_defers_and_a_repeat_url_is_a_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "QUERY_PLANNER_MAX_ADMITTED_DAY", 1)
    plan = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=2, **AGENT)
    agent = _fake_agent({plan[0]["query_id"]: '{"urls": ["https://www.cnbc.com/a.html", '
                                              '"https://www.cnbc.com/b.html"]}',
                         plan[1]["query_id"]: '{"urls": ["https://www.cnbc.com/a.html"]}'})
    rec = _run(tmp_path, agent, max_q=2)
    v = [[u["verdict"] for u in q["urls"]] for q in rec["queries"]]
    assert v == [["admitted", "deferred"], ["duplicate"]]


def test_the_run_stops_at_its_usd_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "QUERY_PLANNER_RUN_USD_CAP", 0.005)
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, max_q=3)
    assert len(agent.calls) == 2 and "USD cap" in rec["refusal"]


# ════════════════════════════════ the yield ══════════════════════════════════

def test_the_receipt_names_which_zero_it_is():
    z = QP.zero_kind
    assert z(queries=0, tool_fired=0, urls=0, admitted=0, pages=0, claims=0,
             forecasts=0) == "NO_QUERIES_RAN"
    assert z(queries=3, tool_fired=0, urls=0, admitted=0, pages=0, claims=0,
             forecasts=0) == "QUERIES_RAN_NO_TOOL_CALL"
    assert z(queries=3, tool_fired=3, urls=0, admitted=0, pages=0, claims=0,
             forecasts=0) == "QUERIES_RAN_NO_URLS"
    assert z(queries=3, tool_fired=3, urls=9, admitted=0, pages=0, claims=0,
             forecasts=0) == "URLS_FOUND_NONE_ADMITTED"
    assert z(queries=3, tool_fired=3, urls=9, admitted=4, pages=0, claims=0,
             forecasts=0) == "ADMITTED_NOT_YET_READ"
    assert z(queries=3, tool_fired=3, urls=9, admitted=4, pages=4, claims=0,
             forecasts=0) == "PAGES_READ_NO_CLAIMS"
    assert z(queries=3, tool_fired=3, urls=9, admitted=4, pages=4, claims=2,
             forecasts=0) == "CLAIMS_NO_FORECASTS"
    assert z(queries=3, tool_fired=3, urls=9, admitted=4, pages=4, claims=2,
             forecasts=5) == "YIELDING"


def _w(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_the_yield_attributes_pages_claims_and_forecasts_to_the_query(tmp_path):
    t = (NOW - timedelta(hours=2)).isoformat()
    pu, ou = "https://www.cnbc.com/2026/10/06/planner.html", "https://www.wsj.com/articles/other"
    _w(QP.ledger_path(tmp_path), [{"t": t, "day": DAY, "query_id": "q1",
                                   "seed_lane": "held_names", "tool": "web_search",
                                   "tool_fired": True, "n_urls": 2, "cost_usd": 0.004,
                                   "verdicts": {"admitted": 1, "quarantined": 1}}])
    _w(QP.queue_path(tmp_path), [{"t": t, "query_id": "q1", "discovered_via": "web_search",
                                  "url": pu, "seed_lane": "held_names"},
                                 {"t": t, "query_id": "q1", "discovered_via": "web_search",
                                  "url": ou, "seed_lane": "held_names"}])
    # no page read yet: the zero says so, and it is NOT "no queries"
    y0 = QP.yield_report(now=NOW, opt=tmp_path)
    assert y0["zero_kind"] == "ADMITTED_NOT_YET_READ" and y0["queries"]["queries"] == 1
    before = (NOW - timedelta(hours=11)).isoformat()      # 9 h BEFORE the query existed
    _w(tmp_path / "dowjones" / "page_log.jsonl", [
        # review F2: the fixed reader read `ou` before the query; the same URL is
        # in the planner's queue. It must NOT be planner yield.
        {"t": before, "host": "wsj.com", "class": "OK", "url": ou, "lane": "front:wsj:markets"},
        {"t": before, "host": "cnbc.com", "class": "OK", "url": pu, "lane": "qp:q1"},
        {"t": t, "host": "cnbc.com", "class": "OK", "url": pu, "lane": "qp:q1"},
        {"t": t, "host": "wsj.com", "class": "OK", "url": ou, "lane": "qp:q1"},
        {"t": t, "host": "wsj.com", "class": "OK", "url": ou + "2", "lane": "wsj:front"},
        {"t": t, "host": "cnbc.com", "class": "OK",
         "url": "https://www.cnbc.com/fixed.html", "lane": "front:cnbc:markets"}])
    y1 = QP.yield_report(now=NOW, opt=tmp_path)
    assert y1["zero_kind"] == "PAGES_READ_NO_CLAIMS"
    assert y1["planner"]["pages_read"] == 1 and y1["non_planner"]["pages_read"] == 3
    r1 = y1["claims_per_page_same_hosts"]
    assert r1["pages_before_query_excluded"] == 1 and r1["pages_already_read_excluded"] == 1
    _w(tmp_path / "sources" / "claims.jsonl", [
        {"claim_hash": "h1", "observed_utc": t, "post_url": pu, "query_id": "q1",
         "reader_lane": "qp:q1"},
        # the fixed reader's claim on the SAME url the planner queued: not planner
        {"claim_hash": "h2", "observed_utc": t, "post_url": ou,
         "reader_lane": "front:wsj:markets"},
        {"claim_hash": "h3", "observed_utc": t, "post_url": "https://www.cnbc.com/fixed.html"}])
    _w(tmp_path / "predictions.jsonl", [
        {"made_at": t, "inputs_used": {"claim_hash": "h1"}},
        {"made_at": t, "inputs_used": {"claim_hash": "h1"}},
        {"made_at": t, "inputs_used": {"claim_hash": "h2"}}])
    y2 = QP.yield_report(now=NOW, opt=tmp_path)
    assert y2["zero_kind"] == "YIELDING"
    assert (y2["planner"]["claims"], y2["planner"]["forecast_rows"]) == (1, 2)
    assert (y2["non_planner"]["claims"], y2["non_planner"]["forecast_rows"]) == (2, 1)
    # review F6: per-host claims are bucketed by the REAL host
    assert y2["non_planner"]["by_host_top"]["wsj.com"]["claims"] == 1
    assert y2["non_planner"]["by_host_top"]["cnbc.com"]["claims"] == 1
    r2 = y2["claims_per_page_same_hosts"]
    assert r2["hosts"] == ["cnbc.com"]
    assert (r2["planner_claims_per_page"], r2["fixed_claims_per_page"]) == (1.0, 1.0)
    assert y2["planner"]["by_seed_lane"]["held_names"]["forecast_rows"] == 2
    assert y2["planner"]["by_tool"]["web_search"]["pages_read"] == 1
    assert "YIELDING" in y2["line"] and "non-planner pages 3" in y2["line"]


def test_an_empty_disk_is_no_queries_ran_not_zero_claims(tmp_path):
    y = QP.yield_report(now=NOW, opt=tmp_path)
    assert y["zero_kind"] == "NO_QUERIES_RAN"
    assert y["line"].startswith("query_planner 24h: NO_QUERIES_RAN")


# ═══════════════════════════ the reader pool adopts it ═══════════════════════

def test_the_pool_adopts_planner_urls_once_into_their_own_lane(ledger):
    qf = ledger / "dowjones" / "query_planner_queue.jsonl"
    rows = [{"t": datetime.now(timezone.utc).isoformat(), "query_id": "qa",
             "discovered_via": "web_search", "first_seen_utc": "2026-10-06T00:00:00+00:00",
             "url": CNBC_A2, "question": "oil"},
            {"t": datetime.now(timezone.utc).isoformat(), "query_id": "qb",
             "discovered_via": "x_search", "url": X_POST},
            {"t": datetime.now(timezone.utc).isoformat(), "query_id": "qc",
             "discovered_via": "web_search", "url": "https://www.chase.com/x"}]
    _w(qf, rows)
    pool, _ = _pool(ledger, FakeDriver(_pages()), fronts=[], planner_queue_path=qf)
    pool.refill()
    got = {it["url"]: it for it in pool.pending if it.get("via") == "query_planner"}
    assert set(got) == {CNBC_A2, X_POST}                     # the bank is never queued
    assert got[CNBC_A2]["lane"] == "qp:qa" and got[CNBC_A2]["blane"] == "query_planner"
    assert got[X_POST]["kind"] == "social" and got[X_POST]["blane"] == "query_planner"
    assert got[CNBC_A2]["query_id"] == "qa" and got[CNBC_A2]["discovered_via"] == "web_search"
    pool2, _ = _pool(ledger, FakeDriver(_pages()), fronts=[], planner_queue_path=qf)
    pool2.refill()
    assert not [it for it in pool2.pending if it.get("via") == "query_planner"]


def test_the_planner_lane_is_a_declared_budget_lane_inside_the_same_total():
    assert "query_planner" in RS.BUDGET_LANES
    sh = RS.budget_shares()
    assert abs(sum(sh.values()) - 1.0) < 1e-9 and 0 < sh["query_planner"] <= 0.05
    assert RS.budget_lane({"kind": "article", "host": "cnbc.com", "via": "query_planner"}) \
        == "query_planner"
    assert RS.budget_lane({"kind": "social", "host": "x.com", "lane": "qp:q1"}) \
        == "query_planner"


# ═══════════════════════════════ the WSJ feeds ═══════════════════════════════

def test_the_retired_wsj_url_parses_correctly_and_is_frozen_upstream():
    from scripts import news_pull as NP
    rows = NP.parse_rss2((FIX / "wsj_markets_retired_url_2026-10-06.xml").read_bytes())
    assert len(rows) == 3
    # `Mon, 27 Jan 2025 14:26:00 -0500` -> 19:26 UTC: the parse was never the defect
    assert rows[0]["published"].astimezone(timezone.utc).isoformat() == "2025-01-27T19:26:00+00:00"
    newest = max(r["published"] for r in rows)
    age_h = (NOW - newest).total_seconds() / 3600
    assert age_h > 14_000                                # the ~607 days the receipt printed
    assert DF.feed_verdict("OK", age_h) == "FROZEN_UPSTREAM"


def test_the_live_wsj_url_parses_in_gmt_and_a_fresh_feed_is_ok():
    from scripts import news_pull as NP
    rows = NP.parse_rss2((FIX / "wsj_markets_live_url_2026-10-06.xml").read_bytes())
    assert len(rows) == 3
    assert rows[0]["published"].isoformat() == "2026-10-06T08:45:19+00:00"
    assert DF.feed_verdict("OK", 3.0) == "OK"
    assert DF.feed_verdict("OK", None) == "OK"
    assert DF.feed_verdict("RED", 1.0) == "RED"
    assert DF.feed_verdict("OK", 400.0, frozen_h=336.0) == "FROZEN_UPSTREAM"


def test_the_five_wsj_feeds_point_at_the_live_dow_jones_host():
    from backend.services import news_registry as NR
    for sid in ("wsj_markets", "wsj_business", "wsj_world", "wsj_opinion", "wsj_tech"):
        url = NR.get(sid).endpoint_or_feed
        assert url.startswith("https://feeds.content.dowjones.io/public/rss/"), (sid, url)
        assert "feeds.a.dj.com" not in url


def test_a_frozen_feed_lands_in_refused_or_red(monkeypatch, tmp_path):
    from scripts import news_pull as NP
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)
    raw = (FIX / "wsj_markets_retired_url_2026-10-06.xml").read_bytes()
    monkeypatch.setattr(NP, "_http_get", lambda url, headers=None, timeout=45.0: raw)
    r = DF.pull_feeds(("wsj_markets",), paced=False)
    f = r["per_feed"][0]
    assert f["received"] == 3 and f["verdict"] == "FROZEN_UPSTREAM"
    assert r["refused_or_red"] == ["wsj_markets"] and r["frozen_upstream"] == ["wsj_markets"]


# ═══════════════════════════ OpenClaw spend on llm_usage ═════════════════════

def _call(ts: str, *, agent: str | None = "openclaw", cost: float | None = 0.01,
          status: str = "OK") -> dict:
    return {"call_id": ts, "ts": ts, "provider": "deepseek", "model": "deepseek-flash",
            "purpose": "x", "agent": agent, "tokens_in": 1000 if cost else 0,
            "tokens_out": 100 if cost else 0, "cached_tokens": 0, "cost_usd": cost,
            "meta": {"status": status}, "row_type": "call"}


def test_llm_usage_carries_an_openclaw_block_read_from_a_fixture_ledger(tmp_path):
    from backend.services import llm_analyzer as LA
    base = tmp_path / "llm_calls.jsonl"
    now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
    sep = tmp_path / "llm_calls_2026-09.jsonl"
    oct_ = tmp_path / "llm_calls_2026-10.jsonl"
    _w(sep, [_call("2026-09-29T10:00:00+00:00"), _call("2026-09-29T11:00:00+00:00", cost=None,
                                                       status="TIMEOUT"),
             _call("2026-09-29T12:00:00+00:00", agent=None, cost=5.0)])
    _w(oct_, [_call("2026-10-06T09:00:00+00:00", cost=0.02)])
    u = LA.openclaw_usage(path=base, now=now)
    assert u["calls"] == 3 and u["ok"] == 2                 # the non-openclaw row is not summed
    assert u["usd"] == pytest.approx(0.03)
    assert u["unpriced_calls"] == 1 and u["usd_is_lower_bound"] is True
    assert u["last_call_utc"] == "2026-10-06T09:00:00+00:00"
    assert (u["calls_today"], u["usd_today"]) == (1, pytest.approx(0.02))
    assert u["calls_7d"] == 1                               # 09-29 is 7 days back: outside
    # incremental: an appended row is seen, nothing is double-counted
    with oct_.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_call("2026-10-06T10:00:00+00:00", cost=0.01)) + "\n")
    u2 = LA.openclaw_usage(path=base, now=now)
    assert u2["calls"] == 4 and u2["usd"] == pytest.approx(0.04)


def test_llm_usage_has_the_block_and_never_reads_the_real_ledger_under_pytest():
    from backend.services import llm_analyzer as LA
    oc = LA.llm_usage()["openclaw"]
    assert oc["calls"] is None and oc["status"].startswith("NOT_READ")


# ═══════════════════════════════ consent dismiss ═════════════════════════════

def _snapshot(*nodes: tuple[str, str, str]) -> str:
    return "\n".join(f'- {role} "{name}" [ref={ref}]' for role, name, ref in nodes)


def test_consent_dismiss_clicks_only_one_exact_allowlisted_control():
    s = _snapshot(("heading", "We value your privacy", "e1"), ("button", "Accept all", "e2"),
                  ("link", "Privacy policy", "e3"))
    assert WR.consent_dismiss_ref(s)["ref"] == "e2"
    # a second consent click on the same page load is a STOP
    assert WR.consent_dismiss_ref(s, clicks_this_page=1)["ref"] is None


@pytest.mark.parametrize("nodes", [
    (("button", "Accept offer", "e1"),),                     # not a whole allowlisted phrase
    (("button", "Sign in to accept cookies", "e1"),),
    (("button", "Subscribe", "e1"),),
    (("textbox", "Email", "e1"), ("button", "Agree and subscribe", "e2")),
    (("checkbox", "Accept all", "e1"),),                     # never a checkbox
    (("button", "Accept all", "e1"), ("button", "Accept all", "e2")),   # ambiguous
])
def test_consent_dismiss_refuses_anything_that_is_not_a_plain_consent_control(nodes):
    assert WR.consent_dismiss_ref(_snapshot(*nodes))["ref"] is None


def test_consent_dismiss_prefers_a_pure_dismissal_and_never_follows_a_link_away():
    s = _snapshot(("button", "Accept all", "e1"), ("button", "Reject all", "e2"))
    assert WR.consent_dismiss_ref(s)["ref"] == "e2"
    away = '- link "Got it" [ref=e9] [url=https://other.example.com/consent]'
    assert WR.consent_dismiss_ref(away)["ref"] is None


def test_consent_dismiss_is_not_switched_on():
    assert not getattr(_config, "READER_CONSENT_DISMISS_ENABLED", False)


# ═════════════════ the tool fired but had no provider (measured 10-06) ═══════

def test_a_tool_with_no_provider_is_its_own_named_zero(tmp_path):
    err = [{"tool": "web_search",
            "error": "web_search is disabled or no provider is available."}]
    assert QP.tool_unavailable(err) and not QP.tool_unavailable([]) \
        and not QP.tool_unavailable(None)
    agent = _fake_agent({})
    rec = QP.run(max_queries=2, opt=tmp_path, now=NOW, agent_fn=agent,
                 tool_calls_fn=_fired(), release_fn=lambda s: True,
                 tool_errors_fn=lambda sid, since: err, provider="declared-for-test",
                 scope_fn=lambda: {"verdict": "OK"}, gateway_fn=lambda: True,
                 seeds_fn=lambda: SEEDS, stored_fn=lambda: set())
    assert all(q["tool_unavailable"] for q in rec["queries"])
    assert rec["totals"]["tool_unavailable"] == 2
    assert rec["yield"]["zero_kind"] == "TOOL_FIRED_BUT_UNAVAILABLE"
    assert "2 tool unavailable" in rec["yield"]["line"]
    assert QP.zero_kind(queries=2, tool_fired=2, urls=0, admitted=0, pages=0, claims=0,
                        forecasts=0, tool_unavailable=2) == "TOOL_FIRED_BUT_UNAVAILABLE"
    assert QP.zero_kind(queries=2, tool_fired=2, urls=0, admitted=0, pages=0, claims=0,
                        forecasts=0, tool_unavailable=0) == "QUERIES_RAN_NO_URLS"


def test_no_declared_provider_means_no_agent_turn_ever_even_after_an_x_search_row(
        tmp_path):
    """Review F1: the old streak gate never fired because an un-offered x_search
    turn recorded no error. The gate is now a DECLARED provider: with none, not
    one agent turn is issued, whatever the ledger says."""
    QP._append_jsonl(QP.ledger_path(tmp_path), [
        {"t": (NOW - timedelta(hours=9)).isoformat(), "day": DAY, "query_id": "w1",
         "seed_lane": "held_names", "tool": "web_search", "tool_unavailable": True},
        {"t": (NOW - timedelta(hours=8)).isoformat(), "day": DAY, "query_id": "x1",
         "seed_lane": "held_names", "tool": "x_search", "tool_unavailable": False}])
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, max_q=4, provider=None,
               http_get=lambda url: GNEWS_XML, sec_json=lambda url: EDGAR_JSON)
    assert agent.calls == []
    assert rec["mode"] == "free" and rec["agent_search"]["status"] == "REFUSED"
    assert rec["agent_search"]["reason"].startswith("NO_SEARCH_PROVIDER_DECLARED")
    assert {q["tool"] for q in rec["queries"]} <= set(QP.FREE_SOURCES)


def test_an_unoffered_x_search_turn_is_recorded_as_tool_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "QUERY_PLANNER_X_SEARCH_OFFERED", True)
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, max_q=8, calls=lambda sid, since: [],
               tool_errors_fn=lambda sid, since: [])
    xs = [q for q in rec["queries"] if q["tool"] == "x_search"]
    assert xs, "the fixture must contain an x_search query"
    for q in xs:
        assert q["tool_fired"] is False and q["tool_unavailable"] is True
        assert "not offered" in q["tool_errors"][0]["error"]


def test_web_fetch_or_any_other_tool_in_a_planner_turn_stops_the_run(tmp_path):
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, calls=lambda sid, since: [
        {"agent": "main", "session": sid, "tool": "web_search"},
        {"agent": "main", "session": sid, "tool": "web_fetch"}])
    assert rec["status"] == "REFUSED" and "web_fetch" in rec["refusal"]
    assert len(agent.calls) == 1


# ═══════════════════════════ the $0 sources (offline) ════════════════════════

_P1 = (NOW - timedelta(hours=3)).strftime("%a, %d %b %Y %H:%M:%S GMT")
_OLD = (NOW - timedelta(days=20)).strftime("%a, %d %b %Y %H:%M:%S GMT")
GNEWS_XML = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>q</title>
<item><title>Nvidia Hits a Record on AI Demand - The Wall Street Journal</title>
<link>https://news.google.com/rss/articles/AAA?oc=5</link><pubDate>{_P1}</pubDate>
<source url="https://www.wsj.com">The Wall Street Journal</source></item>
<item><title>Nvidia Up Again - Yahoo Finance</title>
<link>https://news.google.com/rss/articles/BBB?oc=5</link><pubDate>{_P1}</pubDate>
<source url="https://finance.yahoo.com">Yahoo Finance</source></item>
<item><title>Nvidia Valuation Check - Some Blog</title>
<link>https://news.google.com/rss/articles/CCC?oc=5</link><pubDate>{_P1}</pubDate>
<source url="https://www.some-new-blog.com">Some Blog</source></item>
<item><title>Old Nvidia Story - CNBC</title>
<link>https://news.google.com/rss/articles/DDD?oc=5</link><pubDate>{_OLD}</pubDate>
<source url="https://www.cnbc.com">CNBC</source></item>
</channel></rss>""".encode()
EDGAR_JSON = {"hits": {"total": {"value": 2}, "hits": [
    {"_id": "0001045810-26-000078:nvda-20260902.htm",
     "_source": {"ciks": ["0001045810"], "adsh": "0001045810-26-000078", "form": "8-K",
                 "file_date": "2026-09-03",
                 "display_names": ["NVIDIA CORP  (NVDA)  (CIK 0001045810)"]}},
    {"_id": "0001769628-26-000429:x.htm",
     "_source": {"ciks": ["0001769628"], "adsh": "0001769628-26-000429", "form": "8-K",
                 "file_date": "2026-09-17",
                 "display_names": ["CoreWeave, Inc.  (CRWV)  (CIK 0001769628)"]}}]}}


def test_google_news_gives_a_publisher_and_a_headline_and_the_redirect_is_never_used():
    items = QP.parse_gnews(GNEWS_XML, now=NOW)
    assert [i["headline"] for i in items] == ["Nvidia Hits a Record on AI Demand",
                                             "Nvidia Up Again", "Nvidia Valuation Check"]
    assert all("news.google.com" not in json.dumps(i) for i in items)
    q = {"tool": "gnews_rss", "text": "NVDA stock"}
    rows = QP.candidates(q, {"items": [{"kind": "headline", **i} for i in items]})
    v = {r["publisher"]: (r["verdict"], r["kind"]) for r in rows}
    assert v["The Wall Street Journal"] == ("admitted", "search")
    assert v["Yahoo Finance"][0] == "no_site_search"            # allowed, no own search page
    assert v["Some Blog"][0] == "quarantined"
    wsj = next(r for r in rows if r["verdict"] == "admitted")
    assert wsj["url"].startswith("https://www.wsj.com/search?query=") and wsj["site"] == "wsj"
    assert "when%3A7d" in QP.gnews_url("NVDA stock")


def test_edgar_keeps_only_the_companys_own_filings_on_sec_gov():
    rows = QP.parse_edgar(EDGAR_JSON, "NVDA")
    assert [r["url"] for r in rows] == [
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000078/nvda-20260902.htm"]
    assert QP.classify_url(rows[0]["url"])[0] == "admitted"
    assert "forms=8-K" in QP.edgar_url("NVDA", NOW)


def test_a_zero_dollar_run_queues_searches_and_filings_with_their_query_id(tmp_path):
    agent = _fake_agent({})
    already = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000078/nvda-20260902.htm"
    rec = _run(tmp_path, agent, max_q=6, provider=None,
               seeds={"held_names": ["AMD", "TSM", "NVDA"], "themes": [], "opportunities": []},
               http_get=lambda url: GNEWS_XML, sec_json=lambda url: EDGAR_JSON)
    assert agent.calls == [] and rec["status"] == "OK" and rec["spent_usd"] == 0.0
    q = QP._read_jsonl(QP.queue_path(tmp_path))
    kinds = {r["kind"] for r in q}
    assert kinds == {"search", "article"}
    assert all(r["query_id"] and r["discovered_via"] in QP.FREE_SOURCES and r["first_seen_utc"]
               for r in q)
    # the same headline from a second query is a duplicate, never queued twice
    assert len({r["url"] for r in q}) == len(q)
    # and a filing the reader already stored is ALREADY_READ, not planner novelty
    rec2 = _run(tmp_path / "b", agent, max_q=6, provider=None, stored=[QP._norm(already)],
                seeds={"held_names": ["AMD", "TSM", "NVDA"], "themes": [],
                       "opportunities": []},
                http_get=lambda url: GNEWS_XML, sec_json=lambda url: EDGAR_JSON)
    assert rec2["totals"]["already_read"] == 1
    assert rec2["yield"]["queries"]["share_already_read"] is not None


def test_not_due_writes_no_receipt_only_one_runs_line(tmp_path):
    QP._append_jsonl(QP.ledger_path(tmp_path), [{"t": (NOW - timedelta(hours=1)).isoformat(),
                                                 "day": DAY, "query_id": "x"}])
    rec = QP.run(due_only=True, opt=tmp_path, now=NOW, provider=None, seeds_fn=lambda: SEEDS)
    assert rec["status"] == "NOT_DUE" and "path" not in rec
    assert not list(QP.dj_dir(tmp_path).glob("query_planner_2*.json"))
    assert [r["status"] for r in QP._read_jsonl(QP.runs_log_path(tmp_path))] == ["NOT_DUE"]


def test_a_second_planner_while_one_holds_the_lock_refuses(tmp_path):
    assert QP.acquire_lock(tmp_path, now=NOW) is None
    held = QP.lock_path(tmp_path).read_text(encoding="utf-8")
    QP.lock_path(tmp_path).write_text(held.replace(str(__import__("os").getpid()), "1"),
                                      encoding="utf-8")
    rec = QP.run(opt=tmp_path, now=NOW, provider=None, seeds_fn=lambda: SEEDS,
                 http_get=lambda url: GNEWS_XML, sec_json=lambda url: EDGAR_JSON)
    assert rec["status"] == "ALREADY_RUNNING"
    # a stale lock (a crashed run) is taken
    rec2 = QP.run(opt=tmp_path, now=NOW + timedelta(hours=2), provider=None,
                  seeds_fn=lambda: SEEDS, http_get=lambda url: GNEWS_XML,
                  sec_json=lambda url: EDGAR_JSON, max_queries=1)
    assert rec2["status"] == "OK" and not QP.lock_path(tmp_path).exists()


def test_the_supervisor_recognises_a_live_planner_pid(monkeypatch):
    import subprocess
    from scripts import night_reader_supervisor as S

    class R:
        stdout = "python.exe -m backend.services.query_planner --run --due"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert S.pid_alive(4242, S.PLANNER_NEEDLE) is True
    assert S.pid_alive(4242) is False                # the official_sources needle
    assert not S.planner_due(0.0, 1e9, child_alive=S.pid_alive(4242, S.PLANNER_NEEDLE),
                             enabled=True)


def test_a_claim_written_from_a_planner_page_carries_its_query_id(tmp_path):
    from backend.services import dowjones_claims as DC
    art = {"first_seen_utc": NOW.isoformat(), "url": "https://www.wsj.com/articles/x",
           "published_utc": NOW.isoformat(), "column": "wsj_other", "sha": "s1",
           "reached_by": {"lane": "qp:abc123", "query_id": "abc123"}}
    DC.write_forecasts(art, [{"ticker": "NVDA", "direction": "up",
                              "paraphrase": "Analysts expect demand to stay strong."}],
                       ledger_path=tmp_path / "p.jsonl", claims_path=tmp_path / "c.jsonl",
                       local_path=tmp_path / "l.jsonl")
    row = QP._read_jsonl(tmp_path / "c.jsonl")[0]
    assert row["query_id"] == "abc123" and row["reader_lane"] == "qp:abc123"
