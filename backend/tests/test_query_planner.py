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


def test_every_third_held_name_is_an_x_search_by_cashtag():
    tools = [QP.templates("held_names", "NVDA", i) for i in range(6)]
    assert [t for t, _ in tools].count("x_search") == 2
    assert ("x_search", "$NVDA") in tools
    assert QP.templates("themes", {"title": "Oil", "keywords": ["opec"]}, 0)[0] == "web_search"


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
                     "tool": "web_search"}, {"agent": "main", "session": session_id,
                                              "tool": "x_search"}]
        return tool_by_session(session_id)
    return calls


def _run(tmp_path, agent, *, calls=None, scope=None, gateway=True, max_q=3, seeds=None):
    return QP.run(max_queries=max_q, opt=tmp_path, now=NOW, agent_fn=agent,
                  tool_calls_fn=calls or _fired(), release_fn=lambda s: True,
                  scope_fn=scope or (lambda: {"verdict": "OK"}),
                  gateway_fn=lambda: gateway, seeds_fn=lambda: seeds or SEEDS)


def test_a_new_host_is_quarantined_never_queued_and_refused_never_queued(tmp_path):
    plan = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=3)
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
    plan = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=1)
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
    plan = QP.plan_queries(SEEDS, day=DAY, ledger=[], max_run=2)
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
                                  "url": pu, "seed_lane": "held_names"}])
    # no page read yet: the zero says so, and it is NOT "no queries"
    y0 = QP.yield_report(now=NOW, opt=tmp_path)
    assert y0["zero_kind"] == "ADMITTED_NOT_YET_READ" and y0["queries"]["queries"] == 1
    _w(tmp_path / "dowjones" / "page_log.jsonl", [
        {"t": t, "host": "cnbc.com", "class": "OK", "url": pu, "lane": "qp:q1"},
        {"t": t, "host": "wsj.com", "class": "OK", "url": ou, "lane": "wsj:front"},
        {"t": t, "host": "wsj.com", "class": "OK", "url": ou + "2", "lane": "wsj:front"}])
    y1 = QP.yield_report(now=NOW, opt=tmp_path)
    assert y1["zero_kind"] == "PAGES_READ_NO_CLAIMS"
    assert y1["planner"]["pages_read"] == 1 and y1["non_planner"]["pages_read"] == 2
    _w(tmp_path / "sources" / "claims.jsonl", [
        {"claim_hash": "h1", "observed_utc": t, "post_url": pu},
        {"claim_hash": "h2", "observed_utc": t, "post_url": ou}])
    _w(tmp_path / "predictions.jsonl", [
        {"made_at": t, "inputs_used": {"claim_hash": "h1"}},
        {"made_at": t, "inputs_used": {"claim_hash": "h1"}},
        {"made_at": t, "inputs_used": {"claim_hash": "h2"}}])
    y2 = QP.yield_report(now=NOW, opt=tmp_path)
    assert y2["zero_kind"] == "YIELDING"
    assert (y2["planner"]["claims"], y2["planner"]["forecast_rows"]) == (1, 2)
    assert (y2["non_planner"]["claims"], y2["non_planner"]["forecast_rows"]) == (1, 1)
    assert y2["planner"]["by_seed_lane"]["held_names"]["forecast_rows"] == 2
    assert y2["planner"]["by_tool"]["web_search"]["pages_read"] == 1
    assert "YIELDING" in y2["line"] and "non-planner pages 2" in y2["line"]


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
                 tool_errors_fn=lambda sid, since: err,
                 scope_fn=lambda: {"verdict": "OK"}, gateway_fn=lambda: True,
                 seeds_fn=lambda: SEEDS)
    assert all(q["tool_unavailable"] for q in rec["queries"])
    assert rec["totals"]["tool_unavailable"] == 2
    assert rec["yield"]["zero_kind"] == "TOOL_FIRED_BUT_UNAVAILABLE"
    assert "2 tool unavailable" in rec["yield"]["line"]
    assert QP.zero_kind(queries=2, tool_fired=2, urls=0, admitted=0, pages=0, claims=0,
                        forecasts=0, tool_unavailable=2) == "TOOL_FIRED_BUT_UNAVAILABLE"
    assert QP.zero_kind(queries=2, tool_fired=2, urls=0, admitted=0, pages=0, claims=0,
                        forecasts=0, tool_unavailable=0) == "QUERIES_RAN_NO_URLS"


def test_a_known_unavailable_tool_is_probed_once_a_day_not_spent_on(tmp_path):
    rows = [{"t": (NOW - timedelta(hours=h)).isoformat(), "day": DAY, "query_id": f"u{h}",
             "seed_lane": "held_names", "tool_unavailable": True} for h in (5, 4, 3)]
    QP._append_jsonl(QP.ledger_path(tmp_path), rows)
    agent = _fake_agent({})
    rec = _run(tmp_path, agent, max_q=8)
    assert rec["status"] == "REFUSED" and rec["refusal"].startswith("TOOL_UNAVAILABLE")
    assert agent.calls == []
    # a day later: exactly ONE probe query
    later = NOW + timedelta(hours=25)
    rec2 = QP.run(max_queries=8, opt=tmp_path, now=later, agent_fn=agent,
                  tool_calls_fn=_fired(), release_fn=lambda s: True,
                  scope_fn=lambda: {"verdict": "OK"}, gateway_fn=lambda: True,
                  seeds_fn=lambda: SEEDS)
    assert len(agent.calls) == 1 and rec2["status"] == "OK"
