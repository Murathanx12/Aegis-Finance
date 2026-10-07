"""C6 (2026-10-06): Telegram as the remote cockpit.

Synthetic receipts in tmp_path, a stub handler table, a fake sender and fake
updates. No network, no model: every model call is a stub that records or
raises, and the deterministic tests pass a `call_fn` that FAILS if touched.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import telegram_cockpit as CK

NOW = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def _no_model(*a, **k):
    raise AssertionError("the deterministic path called a model")


def _handlers(calls: list):
    def mk(name):
        def h(args, msg):
            calls.append((name, list(args)))
            return f"<{name}>"
        return h
    return {n: mk(n) for n in ("nav", "broker", "book", "books", "forecasts", "brief",
                                "system", "pending", "approve", "deny", "research")}


@pytest.fixture
def root(tmp_path):
    pa = tmp_path / "paper_accounts"
    pa.mkdir()
    rows = [
        {"account": "PC-PAPER", "family": "pc_paper", "inception": "2026-09-22",
         "start_capital": 1_000_000.0, "equity": 1_010_000.0, "roi_pct": 1.0,
         "spy_same_window_pct": 0.5, "vs_spy_pp": 0.5, "n_positions": 10,
         "last_mark": "2026-10-05", "status": "LIVE"},
        {"account": "hack2", "family": "alpaca_fleet", "inception": "2026-08-28",
         "start_capital": 100_000.0, "equity": 102_000.0, "roi_pct": 2.0,
         "spy_same_window_pct": 1.0, "vs_spy_pp": 1.0, "n_positions": 20,
         "last_mark": "2026-10-05", "status": "LIVE"},
        {"account": "hack3", "family": "alpaca_fleet", "roi_pct": None,
         "status": "CREDENTIAL_INVALID", "note": "HTTP 401"},
    ]
    (pa / "roi_2026-10-06.json").write_text(json.dumps(
        {"generated_utc": "2026-10-06T05:00:00+00:00", "rows": rows, "aggregate": {}}),
        encoding="utf-8")
    h = tmp_path / "health"
    h.mkdir()
    (h / "health_20261006T150000Z.json").write_text(json.dumps({
        "generated_utc": "2026-10-06T15:00:00+00:00", "counts": {"ALIVE": 2, "STALE": 1},
        "rows": [
            {"name": "openclaw_gateway", "verdict": "ALIVE",
             "detail": "gateway running, probe ok; capability PROVEN by the reader: 200 pages OK in 60 min"},
            {"name": "task:AegisReaderSupervisor", "verdict": "UNKNOWN", "detail": "Last Result 0"},
            {"name": "ranking", "verdict": "STALE", "detail": "5 sessions behind"}]}),
        encoding="utf-8")
    dj = tmp_path / "dowjones"
    dj.mkdir()
    (dj / "reader_status.json").write_text(json.dumps({
        "t": "2026-10-06T15:00:00+00:00", "state": "READING", "pages_ok_10m": 30,
        "pages_ok_60m": 190, "classes_60m": {"wsj.com": {"OK": 40}},
        "by_lane": {"lanes": {"markets_news": {"ok_24h": 400, "loads_24h": 420}}}}),
        encoding="utf-8")
    return tmp_path


# ─────────────────────────── the deterministic table ────────────────────────

@pytest.mark.parametrize("text,intent,entity", [
    ("how is pc paper doing", "account", "PC-PAPER"),
    ("show me the fleet", "fleet", None),
    ("why did we buy ACN", "why_stock", "ACN"),
    ("why did we buy acn?", "why_stock", "ACN"),
    ("compare hack2 to spy", "compare_spy", "hack2"),
    ("compare NVDA to SPY", "compare_spy", "NVDA"),
    ("what's the digest saying", "digest", None),
    ("health", "health", None),
    ("what did the reader read today", "reader", None),
    ("is OpenClaw always on", "openclaw", None),
    ("and vs spy?", "compare_spy", None),
    ("scale to $40k", "scale", None),
    ("how are we doing", "nav", None),
    ("show me the ranked book", "book", None),
    ("books leaderboard", "books", None),
    ("give me the brief", "brief", None),
    ("is the sim running", "status", None),
    ("pending approvals", "pending", None),
    ("evidence on NVDA", "evidence", "NVDA"),
    ("buy NVDA", "refused_action", None),
    ("please stop the sim", "refused_action", None),
    ("approve AP20261006", "refused_action", None),
])
def test_the_intent_table_resolves_plain_questions_without_a_model(text, intent, entity):
    c = CK.classify(text)
    assert c is not None and c["intent"] == intent and c["via"] == "table"
    if entity:
        assert entity in (c.get("account"), c.get("ticker"))
    if intent == "scale":
        assert c["amount"] == 40_000


def test_nothing_matches_hands_off_rather_than_guessing():
    assert CK.classify("hello there") is None
    assert CK.classify("") is None


def test_every_table_intent_is_in_the_enum_and_none_is_an_action():
    assert {i for _, i in CK.INTENT_TABLE} <= set(CK.INTENT_ENUM)
    for i in CK.INTENT_ENUM:
        assert not any(w in i for w in ("buy", "sell", "order", "approve", "cancel", "start", "stop"))


def test_a_question_gets_a_receipt_and_buttons_with_no_model_call(root):
    calls: list = []
    rep = CK.route_text("how is pc paper doing", {"chat": {"id": 111}},
                        handlers=_handlers(calls), root=root, call_fn=_no_model, now=NOW)
    assert "PC-PAPER" in rep["text"] and "+1.00%" in rep["text"] and "roi_2026-10-06" in rep["text"]
    labels = [b["text"] for row in rep["reply_markup"]["inline_keyboard"] for b in row]
    assert labels == ["Compare to SPY", "Scale to $40k", "Scale to $1M", "Fleet"]
    assert all(len(b["callback_data"].encode()) <= 64
               for row in rep["reply_markup"]["inline_keyboard"] for b in row)
    rep = CK.route_text("show me the fleet", {"chat": {"id": 111}},
                        handlers=_handlers(calls), root=root, call_fn=_no_model, now=NOW)
    assert "hack2: +2.00%" in rep["text"] and "hack3: CREDENTIAL_INVALID" in rep["text"]
    rep = CK.route_text("is OpenClaw always on", {"chat": {"id": 111}},
                        handlers=_handlers(calls), root=root, call_fn=_no_model, now=NOW)
    assert rep["text"].count("\n") == 2 and rep["text"].startswith("Gateway: ALIVE")
    assert "Reader: READING" in rep["text"]
    rep = CK.route_text("give me the brief", {"chat": {"id": 111}},
                        handlers=_handlers(calls), root=root, call_fn=_no_model, now=NOW)
    assert rep["text"] == "<brief>" and calls == [("brief", [])]


def test_an_imperative_is_refused_and_runs_nothing(root):
    calls: list = []
    for t in ("buy NVDA", "approve AP1", "cancel all orders", "start the sim"):
        rep = CK.route_text(t, {"chat": {"id": 111}}, handlers=_handlers(calls), root=root,
                            call_fn=_no_model, now=NOW)
        assert rep["text"].startswith("REFUSED") and "reply_markup" not in rep
    assert calls == []


# ─────────────────────────── conversational context ─────────────────────────

def test_and_vs_spy_and_scale_resolve_from_the_thirty_minute_context(root):
    h = _handlers([])
    chat = {"chat": {"id": 111}}
    CK.route_text("how is hack2 doing", chat, handlers=h, root=root, call_fn=_no_model, now=NOW)
    rep = CK.route_text("and vs spy?", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=5))
    assert rep["text"].startswith("(about hack2: carried from your last 30 min")
    assert "+1.00 pp vs SPY" in rep["text"]
    rep = CK.route_text("scale to $40k", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=6))
    assert "$40,000: +$800 -> $40,800" in rep["text"]
    assert rep["text"].split("\n")[1].startswith("LINEAR SCALING, NOT A FORECAST")
    # another chat has its own (empty) context
    rep = CK.route_text("and vs spy?", {"chat": {"id": 222}}, handlers=h, root=root,
                        call_fn=_no_model, now=NOW + timedelta(minutes=6))
    assert rep["text"].startswith("Compare what to SPY?")
    # thirty minutes after the LAST turn, the context is gone
    rep = CK.route_text("and vs spy?", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=37))
    assert rep["text"].startswith("Compare what to SPY?")


# ─────────────────────────── the LLM fallback ───────────────────────────────

def test_the_fallback_refuses_an_invented_intent(root):
    seen = {}

    def fake(system, user, **kw):
        seen.update(system=system, user=user, **kw)
        return '{"intent": "place_order", "ticker": "NVDA"}'
    calls: list = []
    rep = CK.route_text("hello there", {"chat": {"id": 111}}, handlers=_handlers(calls),
                        root=root, call_fn=fake, now=NOW)
    assert "not in the enum" in rep["text"] and "Nothing ran" in rep["text"]
    assert calls == [] and "reply_markup" not in rep
    assert seen["purpose"] == "telegram_router"
    assert all(f"- {i}:" in seen["system"] for i in CK.INTENT_ENUM)       # the enum is SENT
    assert CK.llm_calls_today(root=root, now=NOW) == 1


def test_the_fallback_accepts_an_enum_answer_and_says_so(root):
    rep = CK.route_text("anything new on the paper accounts lately", {"chat": {"id": 111}},
                        handlers=_handlers([]), root=root,
                        call_fn=lambda s, u, **k: '```json\n{"intent": "fleet"}\n```', now=NOW)
    assert "hack2: +2.00%" in rep["text"] and "understood as 'fleet'" in rep["text"]


def test_the_fallback_is_capped_per_day(root, monkeypatch):
    monkeypatch.setattr(CK._cfg, "TELEGRAM_ROUTER_LLM_MAX_PER_DAY", 2)
    n = []
    fake = lambda s, u, **k: n.append(1) or '{"intent": "none"}'           # noqa: E731
    for _ in range(3):
        rep = CK.route_text("hello there", {"chat": {"id": 111}}, handlers=_handlers([]),
                            root=root, call_fn=fake, now=NOW)
    assert len(n) == 2 and "classifier cap reached" in rep["text"]


def test_the_default_fallback_goes_through_call_llm(root, monkeypatch):
    from backend.services import llm_analyzer as LA
    got = {}
    monkeypatch.setattr(LA, "_call_llm", lambda s, u, quality=False, **k: got.update(k) or None)
    out = CK.classify_llm("hello there", root=root, now=NOW)
    assert got["purpose"] == "telegram_router" and "refused" in out


# ─────────────────────────── buttons and callbacks ──────────────────────────

def test_a_callback_id_round_trips_for_its_own_chat_only(root):
    cid = CK.mint("111", "intent", {"intent": "fleet"}, root=root, now=NOW)
    assert len(cid.encode()) <= 64
    assert CK.resolve(cid, "111", root=root, now=NOW)["args"] == {"intent": "fleet"}
    assert CK.resolve(cid, "999", root=root, now=NOW) is None
    assert CK.resolve("c000000000000", "111", root=root, now=NOW) is None
    assert CK.resolve("../../etc", "111", root=root, now=NOW) is None
    assert CK.resolve(cid, "111", root=root, now=NOW + timedelta(hours=49)) is None


def _cq(data, chat="111", who="111"):
    return {"id": "q1", "data": data, "from": {"id": int(who)},
            "message": {"chat": {"id": int(chat)}}}


def test_a_button_runs_its_read_intent(root):
    cid = CK.mint("111", "intent", {"intent": "scale", "account": "hack2", "amount": 1_000_000},
                  root=root, now=NOW)
    rep = CK.handle_callback(cid, _cq(cid), handlers=_handlers([]), owner="111", root=root, now=NOW)
    assert "$1,000,000: +$20,000" in rep["text"]


def test_approval_buttons_only_for_pending_items_the_owner_created(root):
    pend = [{"id": "AP1", "state": "PENDING", "what": "/research NVDA",
             "evidence": {"action": {"cmd": "research", "args": ["NVDA"]}}},
            {"id": "AP2", "state": "PENDING", "what": "seed a lane", "evidence": {"x": 1}}]
    calls: list = []
    h = _handlers(calls)
    rep = CK.reply_for("pending", {}, handlers=h, msg={}, chat="111", root=root,
                       pending_fn=lambda: pend)
    labels = [b["text"] for row in rep["reply_markup"]["inline_keyboard"] for b in row]
    assert labels == ["Approve AP1", "Deny AP1"]
    forged = CK.mint("111", "approve", {"id": "AP2"}, root=root, now=NOW)
    rep = CK.handle_callback(forged, _cq(forged), handlers=h, owner="111", root=root,
                             now=NOW, pending_fn=lambda: pend)
    assert rep["text"].startswith("REFUSED") and ("approve", ["AP2"]) not in calls
    ok = CK.mint("111", "approve", {"id": "AP1"}, root=root, now=NOW)
    CK.handle_callback(ok, _cq(ok), handlers=h, owner="111", root=root, now=NOW,
                       pending_fn=lambda: pend)
    assert ("approve", ["AP1"]) in calls


def test_the_research_button_only_enqueues_the_approval_flow(root):
    pend: list = []
    calls: list = []
    h = _handlers(calls)

    def research(args, msg):                          # what `_routed("research")` does
        calls.append(("research", list(args)))
        pend.append({"id": "AP9", "state": "PENDING",
                     "evidence": {"action": {"cmd": "research", "args": list(args)}}})
        return ""
    h["research"] = research
    cid = CK.mint("111", "research", {"ticker": "ACN"}, root=root, now=NOW)
    rep = CK.handle_callback(cid, _cq(cid), handlers=h, owner="111", root=root, now=NOW,
                             pending_fn=lambda: pend)
    assert calls == [("research", ["ACN"])] and "Nothing is spent" in rep["text"]
    labels = [b["text"] for row in rep["reply_markup"]["inline_keyboard"] for b in row]
    assert labels == ["Approve AP9", "Deny AP9"]


# ─────────────────────────── the poller: owner only ─────────────────────────

def _poll_env(monkeypatch, updates):
    from backend.services import telegram_bridge as TG
    sent, inbox = [], []
    monkeypatch.setattr(TG, "owner_chat_id", lambda: "111")
    monkeypatch.setattr(TG, "updates", lambda **k: updates)
    monkeypatch.setattr(TG, "_call", lambda method, payload=None, **k:
                        sent.append({"method": method, **(payload or {})}) or {})
    monkeypatch.setattr(TG, "_append", lambda path, row: inbox.append(row))
    return TG, sent, inbox


def test_a_non_owner_gets_nothing(monkeypatch, root):
    cid = CK.mint("999", "intent", {"intent": "fleet"}, root=root, now=NOW)
    TG, sent, inbox = _poll_env(monkeypatch, [
        {"message": {"chat": {"id": 999}, "text": "how is pc paper doing"}},
        {"callback_query": _cq(cid, chat="999", who="999")},
        {"callback_query": _cq(cid, chat="111", who="999")},      # owner chat, other sender
    ])
    ran = []
    TG.poll({}, text_handler=lambda t, m: ran.append(t) or "x",
            callback_handler=lambda d, cq: ran.append(d) or "x")
    assert sent == [] and ran == []                       # not even answerCallbackQuery
    assert [r.get("refused") for r in inbox] == ["not the owner chat"] * 3
    # and the cockpit itself re-checks, should a caller forget
    assert CK.handle_callback(cid, _cq(cid, chat="999", who="999"), handlers={},
                              owner="111", root=root, now=NOW) is None


def test_the_owner_tap_is_answered_and_the_reply_carries_buttons(monkeypatch, root):
    TG, sent, inbox = _poll_env(monkeypatch, [
        {"callback_query": _cq("c0123456789ab")},
        {"message": {"chat": {"id": 111}, "text": "how is pc paper doing"}}])
    TG.poll({}, text_handler=lambda t, m: CK.route_text(t, m, handlers=_handlers([]), root=root,
                                                         call_fn=_no_model, now=NOW),
            callback_handler=lambda d, cq: CK.handle_callback(d, cq, handlers={}, owner="111",
                                                              root=root, now=NOW))
    assert [s["method"] for s in sent] == ["answerCallbackQuery", "sendMessage", "sendMessage"]
    assert all(s.get("chat_id") in (None, "111") for s in sent)
    assert "expired or is unknown" in sent[1]["text"]
    assert sent[2]["reply_markup"]["inline_keyboard"] and "PC-PAPER" in sent[2]["text"]


def test_send_puts_the_keyboard_on_the_last_chunk_only(monkeypatch):
    TG, sent, _ = _poll_env(monkeypatch, [])
    kb = {"inline_keyboard": [[{"text": "x", "callback_data": "c0123456789ab"}]]}
    TG.send("a\n" * 3000, markdown=False, tag="reply", reply_markup=kb)
    assert len(sent) == 2 and "reply_markup" not in sent[0] and sent[1]["reply_markup"] == kb


def test_the_agent_wires_the_router_and_the_button_handler():
    import inspect
    from scripts import telegram_agent as TA
    assert "telegram_cockpit" in inspect.getsource(TA.text_reply)
    assert inspect.getsource(TA.main).count("callback_handler=callback_reply") == 2


# ─────────────────────────── review fixes (C6 review 2026-10-06) ─────────────

def test_f1_a_named_ticker_is_never_replaced_by_the_context(root, monkeypatch):
    h = _handlers([])
    chat = {"chat": {"id": 111}}
    rep = CK.route_text("why did we buy ACN", chat, handlers=h, root=root, call_fn=_no_model, now=NOW)
    assert rep["text"].startswith("(about ACN)") and "Why ACN?" in rep["text"]
    rep = CK.route_text("why did hack2 buy NVDA", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=1))
    assert "Why NVDA in hack2?" in rep["text"] and "ACN" not in rep["text"]
    assert rep["text"].startswith("(about NVDA in hack2)")
    # IT is a word AND a ticker: not in the (absent) bars panel -> ask, never ACN
    rep = CK.route_text("why did we buy IT", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=2))
    assert rep["text"].startswith("Which stock?") and "ACN" not in rep["text"]
    # with IT in the bars panel it IS the ticker
    monkeypatch.setattr(CK, "known_symbols", lambda root=None: frozenset({"IT", "ACN"}))
    rep = CK.route_text("why did we buy IT", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=3))
    assert "Why IT?" in rep["text"]
    # a pronoun does carry the context, and the reply says so
    rep = CK.route_text("why did we buy it", chat, handlers=h, root=root, call_fn=_no_model,
                        now=NOW + timedelta(minutes=4))
    assert rep["text"].startswith("(about IT: carried from your last 30 min")


def test_f2_how_are_we_doing_answers_the_mandate_not_the_census(root, monkeypatch):
    monkeypatch.setattr(CK, "_broker_equity", lambda: {"equity": 1_012_000.0})
    p = root / "paper_accounts" / "roi_2026-10-06.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["aggregate"] = {"n_ahead_of_spy": 148, "n_behind_spy": 159}
    p.write_text(json.dumps(d), encoding="utf-8")
    calls: list = []
    for q in ("how are we doing", "how much did we make"):
        rep = CK.route_text(q, {"chat": {"id": 111}}, handlers=_handlers(calls), root=root,
                            call_fn=_no_model, now=NOW)
        # 2026-10-07: the RESULTS block leads; the mandate answer follows it unchanged
        assert rep["text"].startswith("RESULTS")
        lines = rep["text"].split("\n\n", 1)[1].split("\n")
        assert lines[1].startswith("PC-PAPER +1.00% vs SPY +0.50% over its own window")
        assert "live broker equity now $1,012,000 (+1.20% since inception" in lines[2]
        assert "hack2: +2.00% (+1.00 pp vs SPY" in rep["text"]
        assert "collapse factor NOT YET COMPUTED" in rep["text"]
        assert "148" not in rep["text"] and "159" not in rep["text"]
    assert calls == []                                    # not the census handler
    d["aggregate"].update(n_ahead_non_twin=40, n_independent_clusters_ahead=9, collapse_factor=4.4)
    p.write_text(json.dumps(d), encoding="utf-8")
    rep = CK.route_text("how are we doing", {"chat": {"id": 111}}, handlers=_handlers([]),
                        root=root, call_fn=_no_model, now=NOW)
    assert "40 non-twin = 9 independent clusters (collapse factor 4.4)" in rep["text"]
    assert "148" not in rep["text"]


def test_f3_every_reader_returns_a_stamped_answer(root):
    args = {"account": ("PC-PAPER",), "scale": ("hack2", 40_000.0), "why_stock": ("ACN",),
            "stock": ("ACN",), "evidence": ("ACN",), "compare_spy": ("ACN",)}
    for name, fn in CK.READERS.items():
        a = fn(*args.get(name, ()), root=root)
        assert isinstance(a, CK.Answer) and a.kind and a.source, name
        line = CK.stamped(a, now=NOW).split("\n")[-1]
        assert line.startswith("(receipt"), (name, line)


def test_f3_a_stale_receipt_says_stale_and_a_null_is_cannot_determine(root):
    h = _handlers([])
    rep = CK.route_text("how is pc paper doing", {"chat": {"id": 111}}, handlers=h, root=root,
                        call_fn=_no_model, now=NOW)
    assert "as of 2026-10-06 05:00 UTC, 10.0 h old)" in rep["text"] and "STALE" not in rep["text"]
    rep = CK.route_text("how is pc paper doing", {"chat": {"id": 111}}, handlers=h, root=root,
                        call_fn=_no_model, now=NOW + timedelta(hours=20))
    assert "30.0 h old -- STALE (limit 26 h)" in rep["text"]
    p = root / "paper_accounts" / "roi_2026-10-06.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("generated_utc")
    d["rows"][0].update(equity=None, start_capital=None, inception=None, spy_same_window_pct=None)
    p.write_text(json.dumps(d), encoding="utf-8")
    t = CK.account_text("PC-PAPER", root)
    assert "equity CANNOT DETERMINE on CANNOT DETERMINE" in t and "$0" not in t
    assert "since CANNOT DETERMINE" in t and "SPY same window CANNOT DETERMINE" in t
    assert "age CANNOT DETERMINE" in t and "treat as STALE" in t
    # the reader's status is stale after an hour: that is "the reader is not reading"
    assert "STALE (limit 1 h)" in CK.age_line("2026-10-06T12:00:00+00:00", "reader", "x", now=NOW)


def _flood(root, n=10):
    tg = root / "telegram"
    tg.mkdir(exist_ok=True)
    with (tg / "conversation.jsonl").open("a", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"t": (NOW - timedelta(seconds=50 - i)).isoformat(),
                                 "dir": "out", "text": "x"}) + "\n")


def test_f6_a_rate_limited_message_or_tap_is_answered_not_silent(root):
    _flood(root)
    rep = CK.route_text("show me the fleet", {"chat": {"id": 111}}, handlers=_handlers([]),
                        root=root, call_fn=_no_model, now=NOW)
    assert rep["text"].startswith("rate-limited") and "Try again in 11 s" in rep["text"]
    cid = CK.mint("111", "intent", {"intent": "fleet"}, root=root, now=NOW)
    rep = CK.handle_callback(cid, _cq(cid), handlers={}, owner="111", root=root, now=NOW)
    assert rep["text"].startswith("rate-limited")


def test_f6_an_owner_tap_past_the_hourly_cap_still_stops_the_spinner(monkeypatch):
    TG, sent, inbox = _poll_env(monkeypatch, [{"callback_query": _cq("c0123456789ab")}])
    monkeypatch.setattr(TG, "_inbound_allowed", lambda who, **k: who == "stranger")
    ran = []
    TG.poll({}, callback_handler=lambda d, cq: ran.append(d))
    assert ran == [] and [s["method"] for s in sent] == ["answerCallbackQuery"]
    assert "rate-limited" in sent[0]["text"]


def test_f5_every_owner_tap_is_an_append_only_row(root):
    cid = CK.mint("111", "intent", {"intent": "fleet"}, root=root, now=NOW)
    CK.handle_callback(cid, _cq(cid), handlers={}, owner="111", root=root, now=NOW)
    CK.handle_callback("c0123456789ab", _cq("c0123456789ab"), handlers={}, owner="111",
                       root=root, now=NOW)
    CK.handle_callback(cid, _cq(cid, chat="999", who="999"), handlers={}, owner="111",
                       root=root, now=NOW)                        # a stranger: no row
    rows = [json.loads(x) for x in (root / "telegram" / "taps.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert [(r["id"], r["resolved"], r["action"]) for r in rows] == [
        (cid, True, "intent"), ("c0123456789ab", False, None)]
    assert rows[0]["args"] == {"intent": "fleet"} and "Fleet" in rows[0]["reply_first_line"]
