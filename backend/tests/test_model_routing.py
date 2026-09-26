"""Chunk G -- model routing, pinned.

* the routing TABLE: each Telegram command reaches the provider Murat named,
  and the four money/state commands read receipts and make NO model call;
* `llama_server.ensure` starts once, and the idle watchdog stops BY PID (a fake
  process: the stop goes through `taskkill /PID <n>`, never an image name);
* NVIDIA is a NAMED provider: it parses `content` ONLY (an empty content is a
  REFUSAL counted per provider, never a chain of thought parsed as an answer),
  retries 429 with backoff, pins the language, and writes a telemetry row
  priced from the house table -- while DeepSeek stays the sole PRIMARY;
* G-fix (adjudication row 7): `/research` answers with EVIDENCE (eight fields,
  `n/a: <why>` when a source is missing, <= 600 chars); `/compare` reads the
  extraction bake-off E-G1, whose system prompt carries the enum it names and
  whose receipt is flushed every 20 rows with the system on the first flush;
  the promise grader has a once-per-UTC-day caller;
* nothing starts llama-server at boot any more.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import llama_server as LS
from backend.services import llm_analyzer as LA
from backend.services import model_routing as MR


# ─────────────────────────────── fixtures ───────────────────────────────────

def _receipts(root):
    (root / "paper_accounts").mkdir(parents=True)
    (root / "paper_accounts" / "roi_2026-09-26.json").write_text(json.dumps({
        "generated_utc": "2026-09-26T03:57:21+00:00",
        "aggregate": {"priced_excluding_control_twins": {"n": 2, "sum_equity": 201000.0,
                                                         "pnl": 1000.0, "roi_pct": 0.5},
                      "n_ahead_of_spy": 1, "n_behind_spy": 1},
        "rows": [{"account": "book-a", "family": "night_books", "roi_pct": 1.2, "vs_spy_pp": 0.4},
                 {"account": "book-a-twin", "family": "night_books_twin", "roi_pct": 9.0,
                  "vs_spy_pp": 9.0}]}), encoding="utf-8")
    (root / "sim").mkdir()
    (root / "sim" / "session.json").write_text(json.dumps({
        "id": "e237a0255b9f", "state": "STOPPED", "mode": "paper_profit", "cycle": 86,
        "started": "2026-09-25T19:23:48+00:00", "heartbeat": "2026-09-26T02:53:48+00:00",
        "ended": "2026-09-26T02:54:21+00:00", "end_reason": "stop requested"}), encoding="utf-8")
    (root / "llm_portfolio").mkdir()
    (root / "llm_portfolio" / "leaderboard_2026-09-26.json").write_text(json.dumps({
        "bars_through": "2026-09-24", "n_books": 2, "n_twins": 4,
        "books": [{"name": "rev_flow", "status": "LIVE", "net_to_date": 0.02,
                   "vs_benchmark": 0.01, "benchmark": "SPY"},
                  {"name": "other", "status": "PENDING", "vs_benchmark": None}]}),
        encoding="utf-8")
    (root / "forecasts").mkdir()
    (root / "forecasts" / "day_2026-09-26.json").write_text(json.dumps({
        "day": "2026-09-26", "state": "DONE", "specialist": "investigator:evidence_v3",
        "model": "deepseek/deepseek-flash", "horizons": [1, 5], "done": ["A", "B"],
        "unpriced": [], "refused": [], "n_rows_written": 4, "spent_usd": 0.3,
        "cap_usd": 2.0}), encoding="utf-8")
    return root


def _no_model(*a, **k):
    raise AssertionError("a deterministic command reached a model")


def _fake_call(texts: dict | None = None, log: list | None = None):
    texts = texts or {}

    def call(provider, system, user, *, purpose, **kw):
        if log is not None:
            log.append({"provider": provider, "user": user, "purpose": purpose, **kw})
        return {"provider": provider, "model": f"{provider}-model", "ok": True,
                "status": "OK", "text": texts.get(provider, f"answer from {provider}"),
                "cost_usd": 0.0 if provider != "deepseek" else 0.00042,
                "cost_status": "LISTED", "latency_s": 1.5, "error": None}
    return call


# ─────────────────────────────── the table ──────────────────────────────────

def test_the_routing_table_is_the_one_murat_specified():
    assert MR.ROUTES == {
        "nav": "deterministic", "status": "deterministic", "books": "deterministic",
        "forecasts": "deterministic", "ask": "local", "research": "evidence",
        "deep": "deepseek|nvidia", "compare": "bakeoff_read"}
    assert MR.BAKEOFF_ARMS == ("rules", "deepseek", "nvidia", "local")


@pytest.mark.parametrize("cmd", sorted(MR.DETERMINISTIC))
def test_deterministic_commands_read_receipts_and_make_no_model_call(cmd, tmp_path):
    root = _receipts(tmp_path)
    out = MR.route(cmd, [], call_fn=_no_model, quest_fn=_no_model, root=root,
                   llama_status=lambda: {"listening": False, "ready": False, "pid": None,
                                         "detail": "not running"})
    assert "CANNOT DETERMINE" not in out, out
    marker = {"nav": "book-a", "status": "e237a0255b9f", "books": "rev_flow",
              "forecasts": "investigator:evidence_v3"}[cmd]
    assert marker in out
    if cmd == "nav":
        assert "book-a-twin" not in out          # control twins are not accounts


def test_a_missing_receipt_says_CANNOT_DETERMINE_not_zero(tmp_path):
    for cmd in ("nav", "books", "forecasts"):
        assert "CANNOT DETERMINE" in MR.route(cmd, [], call_fn=_no_model, root=tmp_path)


def test_ask_goes_to_the_LOCAL_model_and_prints_provider_cost_latency():
    log = []
    out = MR.route("ask", ["what", "is", "beta?"], call_fn=_fake_call(log=log))
    assert [x["provider"] for x in log] == ["local"]
    assert log[0]["ensure_reason"] == "telegram:/ask"
    assert "local · local-model · cost $0.00000 · latency 1.5s" in out


@pytest.mark.parametrize("text,provider", [("why did MU move", "deepseek"),
                                           ("why did MU move --nvidia", "nvidia")])
def test_deep_is_deepseek_unless_nvidia_is_named(text, provider):
    log = []
    out = MR.route("deep", text.split(), call_fn=_fake_call(log=log))
    assert [x["provider"] for x in log] == [provider]
    assert "--nvidia" not in log[0]["user"]
    assert f"_{provider} · " in out


# ─────────────────────────────── /research = evidence ───────────────────────

def _evidence_world(tmp_path):
    """Every source the evidence reply reads, as a tiny on-disk world."""
    import pandas as pd
    root = tmp_path / "optimus"
    (root / "pc_book" / "2026-09-26").mkdir(parents=True)
    (root / "pc_book" / "2026-09-26" / "ranking.json").write_text(json.dumps({
        "asof": "2026-09-21", "n_eligible": 2929,
        "top": [{"rank": 7, "symbol": "MU", "decile": 9,
                 "expected_relative_return_21d_net": 0.012}]}), encoding="utf-8")
    books = tmp_path / "books.jsonl"
    rows = [{"schema": "llm_portfolio/1", "kind": "personal", "name": "human_ai_v1",
             "book_id": "b1", "positions": [{"ticker": "MU", "weight": 0.06}]},
            {"schema": "llm_portfolio/1", "kind": "personal", "name": "voided_book",
             "book_id": "b2", "positions": [{"ticker": "MU", "weight": 0.6}]},
            {"schema": "llm_portfolio/void", "kind": "void", "book_id": "b2",
             "reason": "VOID_BEFORE_ENTRY"},
            {"schema": "llm_portfolio/1", "kind": "twin", "name": "human_ai_v1__random",
             "book_id": "b3", "positions": [{"ticker": "MU", "weight": 0.05}]}]
    books.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    cards = tmp_path / "cards"
    for day, verdict in (("2026-09-19", "neutral"), ("2026-09-26", "supports")):
        (cards / day).mkdir(parents=True)
        (cards / day / "MU.json").write_text(json.dumps({
            "ticker": "MU", "asof": day, "verdict": verdict, "confidence": "med",
            "schema": "thesis_card/v2", "web_what_changed_30_90d": f"text {day}",
            "falsifier": "FQ4 revenue below $49.0B on 2026-09-30"}), encoding="utf-8")
    preds = tmp_path / "predictions.jsonl"
    preds.write_text("\n".join(json.dumps(r) for r in [
        {"prediction_id": "old1", "ticker": "MU", "specialist": "investigator:v3",
         "observable": "abs_move_exceeds", "horizon_days": 1, "probability": 0.4,
         "made_at": "2026-09-20T00:00:00+00:00"},
        {"prediction_id": "new2", "ticker": "MU", "specialist": "investigator:v3",
         "observable": "abs_move_exceeds", "horizon_days": 5, "probability": 0.41,
         "made_at": "2026-09-25T00:00:00+00:00"},
        {"prediction_id": "zz", "ticker": "MUX", "specialist": "x", "made_at": "2026-09-26"}]
    ) + "\n", encoding="utf-8")
    days = pd.bdate_range("2026-05-01", "2026-09-21")
    closes = [100.0 * (1.01 if i % 2 else 0.99) ** (i % 7) for i in range(len(days))]
    bars = pd.DataFrame({"symbol": "MU", "date": days, "close": closes})
    revisions = pd.DataFrame({
        "ticker": ["MU"] * 4, "event_date": ["2026-09-24", "2026-09-22", "2026-09-10",
                                             "2026-08-01"],
        "firm": ["BMO", "Citi", "UBS", "MS"], "target_action": ["Raises", "Raises",
                                                                 "Lowers", "Raises"],
        "prior_target": [100.0, 100.0, 100.0, 100.0],
        "current_target": [120.0, 110.0, 90.0, 110.0], "pit_safe": True})
    eightk = pd.DataFrame({"ticker": ["MU", "MU", "ZZ"],
                           "filing_date": ["2025-09-23", "2026-06-24", "2026-09-10"],
                           "items_joined": ["2.02,9.01", "2.02,9.01", "8.01"]})
    return dict(root=root, books_path=books, cards_root=cards, predictions_path=preds,
                bars=bars, revisions=revisions, eightk=eightk)


def test_research_is_EVIDENCE_every_field_from_disk_under_600_chars(tmp_path):
    from datetime import date
    w = _evidence_world(tmp_path)
    text, res = MR.research("mu", today=date(2026, 9, 26), **w)
    ev = res["evidence"]
    assert len(text) <= MR.RESEARCH_MAX_CHARS
    for k in MR.EVIDENCE_FIELDS:
        assert f"{k}: " in text, k
    assert ev["HELD"] == "1/1 books: human_ai_v1 6.0%"     # the void and the twin are not books held
    assert "7/2929 decile 9" in ev["RANK"] and "+1.20%" in ev["RANK"]
    assert ev["REV21d"].startswith("net +1 (2 up/1 down, 3 firms)")  # 08-01 is outside 21d
    assert ev["NEXT"].startswith("earnings est 2026-09-22") and "year-ago" in ev["NEXT"]
    assert "σ/day" in ev["STOP"] and "-2σ" in ev["STOP"]
    assert ev["CHANGED"].startswith("2026-09-19->2026-09-26") and "neutral/med -> supports/med" in ev["CHANGED"]
    assert ev["FORECAST"].startswith("new2 ")
    assert ev["FALSIFIER"].startswith("FQ4 revenue below")
    assert "*Research*" not in text and "bull" not in text.lower()   # not comments


def test_research_prints_n_a_WHY_for_every_missing_source_never_blank(tmp_path):
    from datetime import date
    empty = tmp_path / "nothing"
    empty.mkdir()
    ev = MR.evidence("ZZZZ", today=date(2026, 9, 26), root=empty,
                     books_path=empty / "books.jsonl", cards_root=empty / "cards",
                     predictions_path=empty / "p.jsonl")
    for k in ("HELD", "RANK", "REV21d", "STOP", "CHANGED", "FORECAST", "FALSIFIER"):
        assert ev[k].startswith("n/a: ") and len(ev[k]) > len("n/a: "), (k, ev[k])
    assert ev["NEXT"].startswith("UNKNOWN (")
    assert len(MR.evidence_text(ev)) <= 600


def test_research_text_trims_the_longest_field_first_never_drops_one():
    ev = {"ticker": "MU", "asof": "2026-09-26", **{k: "x" * 40 for k in MR.EVIDENCE_FIELDS}}
    ev["FALSIFIER"] = "f" * 900
    t = MR.evidence_text(ev)
    assert len(t) <= 600 and all(f"{k}: " in t for k in MR.EVIDENCE_FIELDS)
    assert ("x" * 40) in t                                    # the short fields survive


def test_research_quest_flag_runs_the_card_path_first_and_calls_no_model_otherwise(tmp_path):
    w = _evidence_world(tmp_path)
    runs = []
    out = MR.route("research", ["MU", "--quest"], call_fn=_no_model, root=w["root"],
                   quest_fn=lambda t: runs.append(t) or {"state": "DONE", "done": ["MU"],
                                                         "refused": [], "forecast_rows_written": 3})
    assert runs == ["MU"] and "forecast rows 3" in out
    out2 = MR.route("research", ["MU"], call_fn=_no_model, quest_fn=_no_model, root=w["root"])
    assert out2.startswith("MU ") and "HELD: " in out2


# ─────────────────────────────── /compare = bake-off E-G1 ───────────────────

def test_the_bakeoff_system_prompt_SENDS_the_enum_it_names():
    from backend.services import event_vocabulary as V
    sysp = MR.bakeoff_system()
    for eid in V.EVENT_TYPES:
        assert f"- {eid}\n" in sysp + "\n", eid
    for key in ("ticker", "event_type", "direction", "magnitude_bucket"):
        assert f'"{key}"' in sysp


def test_parse_extraction_refuses_out_of_enum_never_coerces():
    ok, why = MR.parse_extraction('{"ticker":"MU","event_type":"analyst_target_change",'
                                  '"direction":1,"magnitude_bucket":"small"}')
    assert why is None and ok["event_type"] == "analyst_target_change" and ok["magnitude_bucket"] == "SMALL"
    assert MR.parse_extraction('{"ticker":"MU","event_type":"acquisition","direction":1}')[1] \
        .startswith("SCHEMA:event_type")
    assert MR.parse_extraction('{"event_type":"no_event","direction":2}')[1] == "SCHEMA:direction"
    assert MR.parse_extraction("sure! here you go")[1] == "UNPARSEABLE"
    assert MR.parse_extraction(None)[1] == "EMPTY"


def _item(i, stratum="matched", direction=1, tickers=("MU",), title="Citi raises MU price target"):
    return {"item_id": f"E-G1-{i:03d}", "source": "yfinance_ticker_news",
            "document_date": "2026-09-15", "title": title, "body": "(NASDAQ: MU) body",
            "tickers": list(tickers), "window": ["2026-09-13", "2026-09-22"],
            "gold": {"stratum": stratum, "direction": direction if stratum == "matched" else None}}


def test_grading_counts_invented_analyst_facts_and_a_refusal_as_wrong():
    g = MR.grade_extraction({"ticker": "NASDAQ:MU", "event_type": "analyst_target_change",
                             "direction": 1}, _item(0))
    assert g["ticker"] and g["event_type"] and g["direction"]
    g = MR.grade_extraction({"ticker": "MU", "event_type": "analyst_rating_change",
                             "direction": 1}, _item(1, stratum="unmatched"))
    assert g["event_type"] is False and g["invented_analyst"] and g["direction"] is None
    g = MR.grade_extraction(None, _item(2))
    assert g["ticker"] is False and g["event_type"] is False and g["direction"] is False


def test_rules_arm_is_a_real_baseline():
    r = MR.rules_arm(_item(0))
    assert r["ticker"] == "MU" and r["event_type"] == "analyst_target_change" and r["direction"] == 1


def test_run_bakeoff_flushes_every_20_rows_with_the_SYSTEM_on_the_first_flush(tmp_path):
    items = [_item(i) for i in range(12)] + [_item(12 + i, stratum="unmatched",
                                                   title="MU opens a fab") for i in range(3)]
    flushed = []
    out = tmp_path / "bakeoff.json"
    import backend.services.model_routing as M
    real_replace = Path.replace

    def spy_replace(self, target):
        if Path(target) == out:
            flushed.append(json.loads(Path(self).read_text(encoding="utf-8")))
        return real_replace(self, target)

    def call(provider, system, user, *, purpose, **kw):
        assert "- analyst_target_change" in system        # the enum rides on EVERY call
        assert kw["temperature"] == 0.0
        et = "analyst_target_change" if provider != "nvidia" else "no_event"
        return {"provider": provider, "model": f"{provider}-req", "served_model": f"{provider}-served",
                "ok": True, "status": "OK", "latency_s": 0.1, "error": None,
                "cost_usd": 0.001 if provider == "deepseek" else 0.0, "cost_status": "LISTED",
                "text": json.dumps({"ticker": "MU", "event_type": et, "direction": 1,
                                    "magnitude_bucket": "SMALL"})}
    stops = []
    import pytest as _pt
    mp = _pt.MonkeyPatch()
    mp.setattr(Path, "replace", spy_replace)
    try:
        res = M.run_bakeoff(items, call_fn=call, out_path=out, cap_usd=0.005, flush_every=20,
                            nvidia_gap_s=0, stop_local=lambda: stops.append(1) or {"pid": 1})
    finally:
        mp.undo()
    assert flushed[0]["n_rows"] == 0 and "- analyst_target_change" in flushed[0]["system"]
    assert [f["n_rows"] for f in flushed[1:-1]] == [20, 40, 60]
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["state"] == "DONE" and d["n_rows"] == 60 and stops == [1]
    assert {r["model"] for r in d["rows"] if r["arm"] == "local"} == {"local-served"}
    ds = [r for r in d["rows"] if r["arm"] == "deepseek"]
    assert sum(1 for r in ds if r["status"] == "BUDGET_CAP") == 10     # the $0.005 cap binds
    s = d["summary"]
    assert s["deepseek"]["cost_usd"] == pytest.approx(0.005)
    assert s["deepseek"]["refusal_rate"] == pytest.approx(10 / 15, abs=1e-3)
    assert s["nvidia"]["event_type_acc"] == pytest.approx(3 / 15, abs=1e-3)  # right only on unmatched
    assert s["_nvidia_vs_deepseek"]["n_event_type_disagree"] == 5
    assert res["local_server_after"] == {"pid": 1}


def test_compare_is_a_READ_of_the_bakeoff_receipt_and_calls_no_model(tmp_path):
    assert "CANNOT DETERMINE" in MR.route("compare", [], call_fn=_no_model, root=tmp_path)
    (tmp_path / "model_routing").mkdir()
    (tmp_path / "model_routing" / "bakeoff_E-G1_2026-09-26.json").write_text(json.dumps({
        "state": "DONE", "n_items": 240, "arms": ["rules", "deepseek"],
        "summary": {"rules": {"field_accuracy": 0.5, "refusal_rate": 0.0, "cost_usd": 0.0,
                              "latency_median_s": 0.0},
                    "deepseek": {"field_accuracy": 0.8, "refusal_rate": 0.01,
                                 "cost_usd": 0.06, "latency_median_s": 1.2}},
        "rows": []}), encoding="utf-8")
    out = MR.route("compare", ["MU"], call_fn=_no_model, root=tmp_path)
    assert "`deepseek` acc 80.0%" in out and "$0.0600" in out and "direction is not asked" in out


# ─────────────────────────────── the promise grader's daily caller ──────────

def test_promises_are_graded_once_per_UTC_day_from_the_first_due_date(tmp_path):
    from datetime import date
    calls = []
    run = lambda: calls.append(1) or {"graded": 2}                          # noqa: E731
    assert MR.grade_promises_daily(today=date(2026, 9, 29), root=tmp_path,
                                   runner=run)["action"] == "skip"
    a = MR.grade_promises_daily(today=date(2026, 9, 30), root=tmp_path, runner=run)
    b = MR.grade_promises_daily(today=date(2026, 9, 30), root=tmp_path, runner=run)
    c = MR.grade_promises_daily(today=date(2026, 10, 1), root=tmp_path, runner=run)
    assert (a["action"], b["action"], c["action"]) == ("ran", "skip", "ran") and calls == [1, 1]
    lines = (tmp_path / "model_routing" / "grade_promises_daily.jsonl").read_text().splitlines()
    assert [json.loads(x)["day"] for x in lines] == ["2026-09-30", "2026-10-01"]


def test_a_failed_grade_is_a_receipt_line_not_a_raise_and_is_retried(tmp_path):
    from datetime import date

    def boom():
        raise RuntimeError("sec.gov 503")
    a = MR.grade_promises_daily(today=date(2026, 10, 2), root=tmp_path, runner=boom)
    assert a["state"] == "ERROR" and "503" in a["error"]
    b = MR.grade_promises_daily(today=date(2026, 10, 2), root=tmp_path, runner=lambda: {})
    assert b["action"] == "ran" and b["state"] == "OK"


# ─────────────────────────────── ensure / idle ──────────────────────────────

@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    """A fake llama-server: state in a dict, the OS calls recorded."""
    monkeypatch.setattr(LS, "OWNER_FILE", tmp_path / "owner.json")
    state = {"listening": False, "pid": None, "starts": 0, "os_calls": []}

    def status():
        owner = LS._read_owner()
        mine = bool(state["listening"] and owner.get("pid") == state["pid"])
        return {"listening": state["listening"], "ready": state["listening"],
                "pid": state["pid"], "started_by_aegis": mine,
                "foreign": bool(state["listening"] and not mine), "detail": "fake"}

    def start(wait_s=90.0, bind=True):
        state["starts"] += 1
        state.update(listening=True, pid=4242)
        LS._write_owner({"pid": 4242, "started_utc": LS._now(), "owner_pid": os.getpid()})
        return {"ok": True, "action": "started", "pid": 4242, "status": status()}

    def run(cmd, **kw):
        state["os_calls"].append(list(cmd))
        if cmd[:2] == ["taskkill", "/PID"]:
            state.update(listening=False, pid=None)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(LS, "status", status)
    monkeypatch.setattr(LS, "start", start)
    monkeypatch.setattr(LS, "health_ok", lambda timeout=2.0: state["listening"])
    monkeypatch.setattr(LS, "busy", lambda timeout=2.0: False)
    monkeypatch.setattr(LS, "pid_alive", lambda pid: False)
    monkeypatch.setattr(LS.qsp, "run", run)
    monkeypatch.setattr(LS.os, "kill", lambda pid, sig: run(["taskkill", "/PID", str(pid)]))
    monkeypatch.setattr(LS, "start_watchdog", lambda: True)
    return state


def test_ensure_starts_ONCE_and_records_what_it_was_started_for(fake_server):
    a = LS.ensure("telegram:/ask", wait_s=0)
    b = LS.ensure("telegram:/compare", wait_s=0)
    assert fake_server["starts"] == 1
    assert a["action"] == "started" and a["started_for"] == "telegram:/ask"
    assert b["action"] == "reused" and b["started_for"] == "telegram:/ask"
    assert b["requested_for"] == "telegram:/compare"
    owner = LS._read_owner()
    assert owner["uses"] == 2 and owner["last_used_for"] == "telegram:/compare"


def test_idle_watchdog_stops_BY_PID_after_the_idle_window(fake_server):
    LS.ensure("telegram:/ask", wait_s=0)
    t0 = LS._read_owner()["last_used_ts"]
    early = LS.idle_check(now=t0 + LS.IDLE_SHUTDOWN_S - 5)
    assert early["action"] == "none" and fake_server["listening"]
    late = LS.idle_check(now=t0 + LS.IDLE_SHUTDOWN_S + 5)
    assert late["action"] == "idle_stopped" and late["pid"] == 4242
    assert late["started_for"] == "telegram:/ask"
    kills = [c for c in fake_server["os_calls"] if c and c[0] == "taskkill"]
    assert kills and all(c[1] == "/PID" and c[2] == "4242" for c in kills)
    assert not any("/IM" in c for c in fake_server["os_calls"])
    assert not fake_server["listening"]


def test_only_the_STARTING_process_may_idle_stop(fake_server):
    LS.ensure("telegram:/ask", wait_s=0)
    owner = LS._read_owner()
    owner["owner_pid"] = os.getpid() + 1          # another Aegis instance started it
    LS._write_owner(owner)
    out = LS.idle_check(now=owner["last_used_ts"] + 10 * LS.IDLE_SHUTDOWN_S)
    assert out["action"] == "none" and out["reason"] == "not the starting process"
    assert fake_server["listening"]


def test_a_reused_ORPHAN_is_re_owned_by_the_process_using_it(fake_server):
    LS.ensure("bakeoff", wait_s=0)
    owner = LS._read_owner()
    owner["owner_pid"] = 999_999_999                 # the starter died (pid_alive -> False)
    LS._write_owner(owner)
    LS.ensure("bakeoff", wait_s=0)
    after = LS._read_owner()
    assert after["owner_pid"] == os.getpid() and after["owner_adopted_from"] == 999_999_999
    assert fake_server["starts"] == 1


def test_ensure_honours_the_operator_hold(fake_server):
    LS.hold_path().write_text("suite", encoding="utf-8")
    out = LS.ensure("telegram:/ask", wait_s=0)
    assert out["ok"] is False and out["reason"] == "OPERATOR_HOLD"
    assert fake_server["starts"] == 0


def test_a_foreign_server_is_used_but_never_adopted(fake_server):
    fake_server.update(listening=True, pid=999)          # nobody's owner note
    out = LS.ensure("telegram:/ask", wait_s=0)
    assert out["action"] == "reused" and out["started_for"] is None
    assert fake_server["starts"] == 0 and LS._read_owner() == {}


# ─────────────────────────────── NVIDIA ─────────────────────────────────────

class _FakeClient:
    def __init__(self, content, reasoning=None, usage=(120, 30)):
        msg = SimpleNamespace(content=content, reasoning_content=reasoning)
        self.resp = SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1],
                                  prompt_cache_hit_tokens=0))
        self.sent = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        return self.resp


def test_nvidia_is_a_named_provider_that_parses_and_records_telemetry(tmp_path, monkeypatch):
    from backend.services import llm_telemetry as T
    tele = tmp_path / "calls.jsonl"
    monkeypatch.setenv(C.LLM_TELEMETRY_PATH_ENV, str(tele))
    fake = _FakeClient("MU beats SPY. P_BEATS_SPY_5D: 0.6")
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: fake)
    r = LA.call_named("nvidia", "sys", "user", purpose="compare:nvidia")
    assert r["ok"] and r["provider"] == "nvidia" and "0.6" in r["text"]
    assert r["model"] == C.MODEL_ROUTING_NVIDIA_MODEL
    assert r["tokens_in"] == 120 and r["tokens_out"] == 30
    assert r["cost_status"] == "LISTED" and r["cost_usd"] == 0.0   # NIM free tier, a LINE
    assert fake.sent[0]["messages"][0]["content"].endswith(LA._LANGUAGE_PIN)
    rows = T.read_calls(tele)
    assert len(rows) == 1 and rows[0]["provider"] == "nvidia"
    assert rows[0]["purpose"] == "compare:nvidia" and rows[0]["cost_usd"] == 0.0


def test_an_empty_content_is_a_REFUSAL_never_the_reasoning_parsed_as_an_answer(monkeypatch):
    monkeypatch.setattr(LA, "_get_nvidia_client",
                        lambda: _FakeClient(None, "if momentum holds, P_BEATS_SPY_5D: 0.6 ... but"))
    before = LA.EMPTY_CONTENT_REFUSALS.get("nvidia", 0)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["ok"] is False and r["text"] is None and r["status"] == "REFUSED_EMPTY_CONTENT"
    assert "reasoning_content present" in r["error"]
    assert LA.EMPTY_CONTENT_REFUSALS["nvidia"] == before + 1
    assert LA.llm_usage()["empty_content_refusals"]["nvidia"] == before + 1


class _RateLimited(Exception):
    status_code = 429


def test_nvidia_retries_429_with_backoff_then_answers(monkeypatch):
    fake = _FakeClient("answer")
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimited("Too Many Requests")
        return fake.resp
    fake.chat.completions.create = create
    sleeps = []
    monkeypatch.setattr(LA.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: fake)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["ok"] and r["text"] == "answer" and r["n_429"] == 2 and calls["n"] == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] - C.MODEL_ROUTING_NVIDIA_JITTER_S
    assert all(s >= C.MODEL_ROUTING_NVIDIA_BACKOFF_S for s in sleeps)


def test_nvidia_gives_up_after_three_429s_as_RATE_LIMITED(monkeypatch):
    fake = _FakeClient("never")

    def create(**kw):
        raise _RateLimited("Too Many Requests")
    fake.chat.completions.create = create
    monkeypatch.setattr(LA.time, "sleep", lambda s: None)
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: fake)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["ok"] is False and r["status"] == "RATE_LIMITED" and r["n_429"] == 3


def test_a_non_429_error_is_not_retried(monkeypatch):
    fake = _FakeClient("never")
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        raise ValueError("400 bad request")
    fake.chat.completions.create = create
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: fake)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["status"] == "ERROR" and calls["n"] == 1


def test_the_adjudicator_is_a_non_reasoning_INSTRUCT_model_recorded_with_its_date():
    assert C.MODEL_ROUTING_NVIDIA_MODEL == C.NVIDIA_ADJUDICATOR_MODEL
    assert "instruct" in C.NVIDIA_ADJUDICATOR_MODEL and "nemotron-3-super" not in C.NVIDIA_ADJUDICATOR_MODEL
    assert C.NVIDIA_ADJUDICATOR_MODEL_CHOSEN == "2026-09-26"
    assert LA._nvidia_model() == C.NVIDIA_ADJUDICATOR_MODEL
    assert LA.cost_status(C.NVIDIA_ADJUDICATOR_MODEL) == "LISTED"      # free tier, a LINE
    assert LA.cost_status("local") == "LISTED"                           # no permanent LOWER BOUND


def test_the_row_records_the_model_the_PROVIDER_says_answered(monkeypatch):
    fake = _FakeClient("hi")
    fake.resp.model = "deepseek-flash"
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: fake)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["served_model"] == "deepseek-flash" and r["model"] == C.NVIDIA_ADJUDICATOR_MODEL


def test_nvidia_without_a_key_is_a_REFUSAL_not_a_fallback(monkeypatch):
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: None)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["ok"] is False and r["status"] == "NOT_CONFIGURED" and r["text"] is None


def test_deepseek_stays_the_sole_PRIMARY_and_nvidia_is_listed_as_adjudicator():
    assert LA.SOLE_PROVISIONED_PROVIDER == "deepseek"
    st = LA.provider_status()
    assert st["roles"] == {"deepseek": "primary", "nvidia": "adjudicator",
                           "local": "on_demand"}
    assert st["named"]["nvidia"]["role"] == "adjudicator"
    assert "nvidia" not in st["configured"]          # never a candidate for `active`


def test_cost_status_is_derived_from_the_price_table():
    assert LA.cost_status("deepseek-chat") == "LISTED"
    assert LA.cost_status("no-such-model-x") == "UNPRICED"
    for name, row in C.MODEL_ROUTING_PROVIDERS.items():
        assert row["cost_status"] == LA.cost_status(row["model"]), name


def test_local_route_goes_through_ensure_and_refuses_when_it_cannot_start(monkeypatch):
    seen = []
    monkeypatch.setattr(LS, "ensure", lambda reason, **k: seen.append(reason) or
                        {"ok": False, "action": "refused", "reason": "OPERATOR_HOLD"})
    r = LA.call_named("local", "s", "u", purpose="telegram:ask",
                      ensure_reason="telegram:/ask")
    assert seen == ["telegram:/ask"]
    assert r["status"] == "LOCAL_UNAVAILABLE" and "OPERATOR_HOLD" in r["error"]


# ─────────────────────────────── boot ───────────────────────────────────────

def test_nothing_starts_llama_server_at_boot():
    assert C.MODEL_ROUTING_START_AT_BOOT is False
    assert C.LAB_STARTS_MODEL_SERVER is C.MODEL_ROUTING_START_AT_BOOT
    assert C.MODEL_ROUTING_IDLE_SHUTDOWN_S == 900
    import inspect
    from scripts import night_run_until as N
    assert "MODEL_ROUTING_START_AT_BOOT" in inspect.getsource(N.Night.run)
    from desktop import aegis_desktop as AD
    assert "MODEL_ROUTING_START_AT_BOOT" in inspect.getsource(AD.main)


def test_the_telegram_agent_routes_through_the_table():
    from scripts import telegram_agent as TA
    for cmd in MR.ROUTES:
        assert TA.HANDLERS[cmd].__name__ == f"routed_{cmd}", cmd


# ─────────────────────────────── Telegram redaction ─────────────────────────

def test_error_text_is_REDACTED_before_it_reaches_telegram(monkeypatch):
    from pathlib import Path as _P

    from backend.services import telegram_bridge as TG
    home = str(_P.home())
    fake = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3"            # a FAKE key, never a real one
    nv = "nvapi-" + "Z" * 30
    SEP = chr(92)                                            # a Windows path separator
    tb = ("Traceback (most recent call last):\n"
          f'  File "{home}{SEP}aegis-finance{SEP}backend{SEP}services{SEP}llm_analyzer.py", line 540\n'
          f"openai.AuthenticationError: 401 Incorrect API key provided: {fake}\n"
          f"{{'api_key': '{fake}', 'token': 'abcdefghijklmnopqrstuvwxyz0123'}}\n"
          f"NVIDIA_API_KEY={nv}\n"
          "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123\n"
          f"loaded {home.replace(chr(92), '/')}/aegis-finance/.env")
    out = TG.redact(tb)
    for secret in (fake, nv, "abcdefghijklmnopqrstuvwxyz0123", "abcdefghijklmnopqrstuvwxyz123",
                   home, home.replace("\\", "/")):
        assert secret not in out, secret
    assert f"~{SEP}aegis-finance{SEP}backend" in out and "llm_analyzer.py" in out   # still readable
    assert "NVIDIA_API_KEY=<redacted>" in out
    sent = []
    monkeypatch.setattr(TG, "owner_chat_id", lambda: "1")
    monkeypatch.setattr(TG, "_call", lambda method, payload=None, **k: sent.append(payload) or {})
    monkeypatch.setattr(TG, "_append", lambda *a, **k: None)
    TG.send(tb)
    assert sent and all(fake not in p["text"] and nv not in p["text"] for p in sent)


def test_a_handler_exception_reaches_the_phone_redacted(monkeypatch):
    from backend.services import telegram_bridge as TG
    fake = "token=" + "q" * 32
    monkeypatch.setattr(TG, "owner_chat_id", lambda: "1")
    monkeypatch.setattr(TG, "updates", lambda **k: [{"message": {"chat": {"id": 1},
                                                                 "text": "/boom"}}])
    monkeypatch.setattr(TG, "_append", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(TG, "_call", lambda method, payload=None, **k: sent.append(payload) or {})

    def boom(args, msg):
        raise RuntimeError(f"failed with {fake}")
    TG.poll({"boom": boom})
    assert sent and "q" * 32 not in sent[0]["text"] and "<redacted>" in sent[0]["text"]


def test_the_telegram_digest_runs_the_promise_grader_once_per_day(monkeypatch, tmp_path):
    from datetime import date

    from scripts import telegram_agent as TA
    calls = []
    monkeypatch.setattr(MR, "grade_promises_daily",
                        lambda today=None: calls.append(today) or
                        {"action": "ran", "day": "2026-10-01", "state": "OK", "elapsed_s": 1.0})
    TA._DAILY_DONE.clear()
    first = TA.daily_jobs(today=date(2026, 10, 1))
    second = TA.daily_jobs(today=date(2026, 10, 1))
    assert first and "promises graded (2026-10-01): OK" in first[0]
    assert second == [] and len(calls) == 1
    import inspect
    assert "daily_jobs()" in inspect.getsource(TA.main)          # the serve loop + --brief call it
