"""OpenClaw LLM turns are read-only (2026-09-29, reader-pool review F1).

A thesis-card quest -- an LLM turn of the `main` agent, tool profile `coding`
with only `browser` denied -- used `exec` to drive the dedicated signed-in
Chrome with its own JavaScript on 2026-09-28. These tests read a FIXTURE copy
of the tool-scope shape of `~/.openclaw/openclaw.json` (no secret sections)
and fail if any LLM-capable agent can reach a shell, a file write, a
messaging / publishing tool or the browser. Offline: no gateway, no CLI.
"""
from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import openclaw_tool_scope as OTS
from backend.services import thesis_card as TC

FIXTURE = Path(__file__).parent / "fixtures" / "openclaw" / "openclaw_tool_scope_2026-09-29.json"
SHELL = {"exec", "process", "code_execution", "bash"}
WRITE = {"write", "edit", "apply_patch"}
MESSAGE = {"message", "conversations_send", "conversations_turn", "sessions_send",
           "sessions_spawn", "subagents", "github_publish"}
BROWSER = {"browser", "terminal", "screen", "computer", "canvas"}


@pytest.fixture()
def cfg() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_carries_no_secret_section(cfg):
    txt = FIXTURE.read_text(encoding="utf-8").lower()
    for k in ("token", "apikey", "api_key", "password", "secretref"):
        assert k not in txt, k
    assert "gateway" not in cfg and "models" not in cfg and "auth" not in cfg


def test_no_llm_capable_agent_can_reach_shell_write_message_or_browser(cfg):
    assert OTS.config_problems(cfg) == []
    for aid in OTS.agent_ids(cfg):
        if aid in OTS.TRANSPORT_AGENTS:
            continue
        eff = OTS.effective_tools(cfg, aid)
        assert not eff["unfiltered"], aid
        reach = eff["tools"]
        assert not reach & SHELL, (aid, reach & SHELL)
        assert not reach & WRITE, (aid, reach & WRITE)
        assert not reach & MESSAGE, (aid, reach & MESSAGE)
        assert not reach & BROWSER, (aid, reach & BROWSER)


def test_main_keeps_its_read_tools(cfg):
    reach = OTS.effective_tools(cfg, "main")["tools"]
    assert {"web_search", "web_fetch", "memory_search"} <= reach


def test_the_transport_agent_holds_browser_only_and_is_bound_to_nothing(cfg):
    eff = OTS.effective_tools(cfg, "aegis-browser")
    assert "browser" in eff["tools"]
    assert not (eff["tools"] - OTS.PROFILES["minimal"] - {"browser"}) & OTS.FORBIDDEN
    assert all(b.get("agentId") != "aegis-browser" for b in cfg.get("bindings") or [])


def test_the_config_of_2026_09_28_is_caught(cfg):
    """The shape that let the quest reach `exec`: global `coding`, main denies
    only `browser`."""
    old = copy.deepcopy(cfg)
    old["tools"] = {"profile": "coding"}
    old["agents"]["entries"]["main"]["tools"] = {"deny": ["browser"]}
    probs = OTS.config_problems(old)
    assert probs and "exec" in probs[0] and probs[0].startswith("main:")


def _undeny(c: dict) -> dict:
    """Both deny layers removed, so an allow is not masked (deny wins)."""
    c["tools"].pop("deny", None)
    c["agents"]["entries"]["main"]["tools"].pop("deny", None)
    return c["agents"]["entries"]["main"]["tools"]


def test_a_deny_wins_over_an_allow(cfg):
    cfg["agents"]["entries"]["main"]["tools"]["alsoAllow"] += ["exec", "group:fs", "message"]
    assert OTS.config_problems(cfg) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda c: _undeny(c)["alsoAllow"].append("exec"), "exec"),
    (lambda c: _undeny(c)["alsoAllow"].append("group:fs"), "write"),
    (lambda c: _undeny(c)["alsoAllow"].append("message"), "message"),
    (lambda c: _undeny(c)["alsoAllow"].append("browser"), "browser"),
    (lambda c: c["tools"]["deny"].remove("group:runtime") or
     c["agents"]["entries"].__setitem__("research", {"tools": {"profile": "coding"}}),
     "research"),
    (lambda c: c["agents"]["entries"]["main"]["tools"].__setitem__("profile", "full"),
     "unfiltered"),
    (lambda c: c["agents"]["entries"]["main"]["tools"].pop("profile") and
     c["tools"].pop("profile"), "unfiltered"),
    (lambda c: c["agents"]["entries"]["main"]["tools"]["alsoAllow"].append("*"), "unfiltered"),
    (lambda c: c["tools"].__setitem__("toolsBySender", {"*": {"alsoAllow": ["exec"]}}),
     "cannot resolve"),
    (lambda c: c["bindings"].append({"agentId": "aegis-browser", "match": {"channel": "telegram"}}),
     "bound to a channel"),
])
def test_any_widening_is_named(cfg, mutate, needle):
    mutate(cfg)
    probs = OTS.config_problems(cfg)
    assert probs and any(needle in p for p in probs), probs


def test_no_config_is_cannot_determine_never_safe():
    assert OTS.config_problems(None)[0].startswith("CANNOT DETERMINE")


# ─────────────────────────── the transcript half ─────────────────────────────

def _store(home: Path, agent: str, calls: list[tuple[str, dict, datetime]]) -> None:
    db = home / "agents" / agent / "agent" / "openclaw-agent.sqlite"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute("create table session_nodes (session_key text, current_session_id text)")
    con.execute("create table transcript_events (session_id text, seq int, event_json text, "
                "created_at int)")
    con.execute("insert into session_nodes values ('agent:main:explicit:aegis-q-1', 's1')")
    for i, (name, args, t) in enumerate(calls):
        ev = {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "x"},
            {"type": "toolCall", "id": f"c{i}", "name": name, "arguments": args}]}}
        con.execute("insert into transcript_events values (?,?,?,?)",
                    ("s1", i, json.dumps(ev), int(t.timestamp() * 1000)))
    con.commit()
    con.close()


def test_the_audit_names_every_call_outside_the_read_set(tmp_path, cfg):
    now = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
    (tmp_path / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    _store(tmp_path, "main", [
        ("web_fetch", {"url": "https://www.sec.gov/x"}, now - timedelta(hours=1)),
        ("optimus__brain_query", {"q": "x"}, now - timedelta(hours=1)),
        ("exec", {"command": "openclaw browser open https://x.com/Microsoft --token "
                             "abcdefghijklmnopqrstuvwxyz0123456789"}, now - timedelta(hours=2)),
        ("browser", {"action": "evaluate"}, now - timedelta(hours=3)),
        ("exec", {"command": "old"}, now - timedelta(hours=30)),          # outside 24 h
    ])
    r = OTS.audit(tmp_path, now=now, hours=24)
    assert r["verdict"] == "UNSAFE" and r["config_problems"] == []
    assert [v["tool"] for v in r["violations"]] == ["browser", "exec"]
    assert r["n_calls"] == 4
    heads = " ".join(v["args_head"] for v in r["violations"])
    assert "abcdefghijklmnopqrstuvwxyz" not in heads and "REDACTED" in heads


def test_a_transport_agent_transcript_is_itself_a_violation(tmp_path, cfg):
    now = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
    (tmp_path / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    _store(tmp_path, "aegis-browser", [("web_search", {"q": "x"}, now - timedelta(hours=1))])
    r = OTS.audit(tmp_path, now=now)
    assert r["n_violations"] == 1


def test_a_clean_window_is_ok(tmp_path, cfg):
    now = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
    (tmp_path / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    _store(tmp_path, "main", [("web_search", {"q": "x"}, now - timedelta(hours=1))])
    assert OTS.audit(tmp_path, now=now)["verdict"] == "OK"


def test_the_health_probe_is_unknown_without_a_config_and_dead_when_unsafe(tmp_path, cfg):
    from backend.services import system_health as SH
    now = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, now=now,
                      paths={"openclaw_home": tmp_path / "oc"})
    assert OTS.p_openclaw_tool_scope(ctx).verdict == "UNKNOWN"
    (tmp_path / "oc").mkdir()
    (tmp_path / "oc" / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert OTS.p_openclaw_tool_scope(ctx).verdict == "ALIVE"
    _store(tmp_path / "oc", "main", [("exec", {"command": "x"}, now - timedelta(hours=1))])
    assert OTS.p_openclaw_tool_scope(ctx).verdict == "DEAD"
    assert any(p.name == "openclaw_tool_scope" for p in SH.PROBES)


# ─────────────────── the thesis-card quest reads pages only via the reader ────

def test_the_quest_prompt_forbids_browser_and_shell_and_carries_guarded_pages():
    e = TC.engine_side("AAA", asof="2026-09-28", bars=None, revisions=None, news_rows=[],
                       catalysts=[], predictions=[])
    p = TC.quest_prompt("AAA", e, social_reads=[
        {"host": "x.com", "url": "https://x.com/search?q=%24AAA&f=live",
         "read_utc": "2026-09-28T10:00:00+00:00", "text": "@AAAcorp shipping HBM4",
         "chars": 22, "truncated": False}])
    assert "logged-in X (x.com) account" not in p and "Use your browser" not in p
    assert "NO browser, NO shell" in p
    assert "@AAAcorp shipping HBM4" in p and "UNTRUSTED" in p
    p0 = TC.quest_prompt("AAA", e)
    assert "none were read by the guarded reader" in p0


def test_guarded_social_reads_are_point_in_time_and_newest_per_host(tmp_path):
    def row(host, t, text, ticker="AAA"):
        return json.dumps({"source_kind": "social", "host": host, "ticker": ticker,
                           "url": f"https://{host}/q", "read_utc": t, "text": text})
    (tmp_path / "x.com").mkdir()
    (tmp_path / "x.com" / "2026-09-27.jsonl").write_text(
        row("x.com", "2026-09-27T09:00:00+00:00", "older") + "\n", encoding="utf-8")
    (tmp_path / "x.com" / "2026-09-28.jsonl").write_text(
        row("x.com", "2026-09-28T09:00:00+00:00", "newest") + "\n"
        + row("x.com", "2026-09-28T10:00:00+00:00", "other name", ticker="BBB") + "\n",
        encoding="utf-8")
    (tmp_path / "x.com" / "2026-09-29.jsonl").write_text(
        row("x.com", "2026-09-29T09:00:00+00:00", "FUTURE") + "\n", encoding="utf-8")
    got = TC.guarded_social_reads("aaa", asof="2026-09-28", root=tmp_path)
    assert [g["text"] for g in got] == ["newest"]
    assert TC.guarded_social_reads("AAA", asof="2026-09-28", root=tmp_path,
                                   max_age_h=1) == []
