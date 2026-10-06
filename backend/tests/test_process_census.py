"""C14 (2026-10-07): the gateway process leak -- census thresholds and the
one-shot session's release lifecycle. Offline: no gateway, no CLI, no real
process table, no machine OpenClaw home.

The defect: every `openclaw_client.agent()` turn opens a fresh OpenClaw
session; the gateway starts the two stdio MCP servers declared in its config
(Optimus + `openclaw_api_bridge`) for it; `release_session` ARCHIVED the
session, which does not retire that runtime, and reported success. 146 turns
left 146 pairs alive (x2 for the venv shim) until they were killed by hand.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import openclaw_client as OC
from backend.services import openclaw_tool_scope as OTS
from backend.services import process_census as PC
from backend.services import system_health as SH

NOW = datetime.now(timezone.utc).replace(microsecond=0)
GATEWAY_CMD = r'"C:\node\node.exe" C:\npm\node_modules\openclaw\dist\index.js gateway --port 1'
SHIM = r"C:\x\optimus\.venv\Scripts\python.exe"
REAL = r'"C:\py\python.exe"'
MCP = r"C:\x\optimus\mcp\server.py"
BRIDGE = r"C:\x\aegis-finance\scripts\openclaw_api_bridge.py"
FAMS = {"optimus_mcp": (r"optimus[\\/]mcp[\\/]server\.py", 2),
        "api_bridge": (r"openclaw_api_bridge", 2)}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _pair(pid: int, ppid: int, script: str, created: datetime) -> list[dict]:
    """A venv launcher shim and its interpreter child: ONE logical instance."""
    return [{"pid": pid, "ppid": ppid, "name": "python.exe", "created_utc": _iso(created),
             "cmd": f"{SHIM} {script}"},
            {"pid": pid + 1, "ppid": pid, "name": "python.exe",
             "created_utc": _iso(created + timedelta(seconds=1)), "cmd": f"{REAL} {script}"}]


def _table(n_sessions: int, *, gateway_pid: int = 10) -> list[dict]:
    rows = [{"pid": gateway_pid, "ppid": 1, "name": "node.exe",
             "created_utc": _iso(NOW - timedelta(hours=12)), "cmd": GATEWAY_CMD}]
    for i in range(n_sessions):
        t = NOW - timedelta(minutes=60 - i)
        rows += _pair(1000 + 10 * i, gateway_pid, MCP, t)
        rows += _pair(5000 + 10 * i, gateway_pid, BRIDGE, t)
    return rows


# ─────────────────────────────── census verdicts ──────────────────────────────

@pytest.mark.parametrize("n,verdict,state", [
    (0, "ALIVE", None), (2, "ALIVE", None),          # at the cap
    (3, "STALE", "DEGRADED"), (4, "STALE", "DEGRADED"),  # above cap, at 2x
    (5, "DEAD", "DEAD"),                             # above 2x
])
def test_census_verdict_follows_the_cap_and_twice_the_cap(n, verdict, state):
    c = PC.census(_table(n), FAMS, dead_mult=2.0)
    for fam in ("optimus_mcp", "api_bridge"):
        assert c[fam]["instances"] == n, c[fam]
        assert c[fam]["raw"] == 2 * n                # shim + interpreter
        assert (c[fam]["verdict"], c[fam]["state"]) == (verdict, state)


def test_census_names_the_parent_and_the_oldest_creation():
    c = PC.census(_table(5), FAMS, dead_mult=2.0)["api_bridge"]
    assert c["parents"] == [{"ppid": 10, "count": 5, "parent": "node.exe (openclaw gateway)"}]
    assert c["oldest_utc"] == (NOW - timedelta(minutes=60)).isoformat(timespec="seconds")
    line = PC.render(c)
    assert line.startswith("DEAD:") and "openclaw gateway" in line and "oldest created" in line
    assert "nothing was terminated" in line


def test_a_shim_child_is_not_a_second_instance_but_two_sessions_are_two():
    rows = _pair(100, 10, MCP, NOW) + _pair(200, 10, MCP, NOW)
    c = PC.census(rows, FAMS)["optimus_mcp"]
    assert (c["instances"], c["raw"]) == (2, 4)


def test_an_unrelated_python_is_not_counted():
    rows = [{"pid": 7, "ppid": 1, "name": "python.exe", "created_utc": _iso(NOW),
             "cmd": "python -m pytest backend/tests/test_process_census.py"}]
    c = PC.census(rows, FAMS)
    assert all(v["instances"] == 0 and v["verdict"] == "ALIVE" for v in c.values())


def test_the_declared_families_match_the_real_command_line_shapes():
    """The shipped config's regexes, against the command-line SHAPES seen on
    2026-10-07 (generic paths)."""
    fams = PC.families()
    assert set(fams) >= {"optimus_mcp", "api_bridge", "sim_run", "reader", "telegram"}
    shapes = {
        "optimus_mcp": f"{SHIM} {MCP}",
        "api_bridge": f"{SHIM} {BRIDGE}",
        "sim_run": r"C:\x\.venv\Scripts\pythonw.exe -m scripts.sim_run --session abc",
        "reader": r"C:\x\.venv\Scripts\python.exe -m scripts.reader_pool --handoff",
        "telegram": r"C:\x\.venv\Scripts\pythonw.exe -m scripts.telegram_agent --serve",
    }
    for fam, cmd in shapes.items():
        assert PC._family_of(cmd, fams) == fam, (fam, cmd)
    for fam, (_rx, cap) in fams.items():
        assert int(cap) >= 1, fam


# ─────────────────────────────── the probe ───────────────────────────────────

def _ctx(tmp_path: Path, reader=None) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    od.mkdir(exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=NOW, repo=tmp_path, process_rows=reader)


def test_probe_without_a_reader_is_unknown_never_alive(tmp_path):
    r = PC.p_process_census(_ctx(tmp_path))
    assert r.verdict == "UNKNOWN" and "not counted" in r.detail


@pytest.mark.parametrize("reader", [lambda: None, lambda: (_ for _ in ()).throw(OSError("x"))])
def test_probe_with_an_unreadable_table_is_unknown(tmp_path, reader):
    assert PC.p_process_census(_ctx(tmp_path, reader)).verdict == "UNKNOWN"


def test_probe_goes_degraded_then_dead_on_the_leak_shape(tmp_path, monkeypatch):
    from backend import config as C
    monkeypatch.setattr(C, "PROCESS_CENSUS_FAMILIES", FAMS)
    monkeypatch.setattr(C, "PROCESS_CENSUS_DEAD_MULT", 2.0)
    ok = PC.p_process_census(_ctx(tmp_path, lambda: _table(2)))
    assert {k: v.verdict for k, v in ok.items()} == {"optimus_mcp": "ALIVE", "api_bridge": "ALIVE"}
    deg = PC.p_process_census(_ctx(tmp_path, lambda: _table(3)))
    assert deg["api_bridge"].verdict == "STALE" and deg["api_bridge"].state == "DEGRADED"
    dead = PC.p_process_census(_ctx(tmp_path, lambda: _table(146)))
    assert dead["optimus_mcp"].verdict == "DEAD" and dead["optimus_mcp"].delta == 146
    rows = SH.run_probes(_ctx(tmp_path, lambda: _table(146)), only={"process_census"})
    assert SH.exit_code(rows) == 1
    assert {r["name"] for r in rows} == {"process_census:optimus_mcp", "process_census:api_bridge"}


def test_the_probe_is_registered_as_a_process_probe():
    p = [p for p in SH.PROBES if p.name == "process_census"]
    assert len(p) == 1 and p[0].needs_proc is True and p[0].where == "pc"


def test_the_census_module_never_terminates_anything():
    src = Path(PC.__file__).read_text(encoding="utf-8")
    code = src.split('"""', 2)[2]                    # skip the module docstring
    for banned in ("taskkill", "Stop-Process", ".kill(", ".terminate(", "os.kill"):
        assert banned not in code, banned


# ─────────────────────────────── the release lifecycle ────────────────────────

_DELETED = {"ok": True, "operation": "delete", "dryRun": False,
            "results": [{"key": "k", "ok": True, "status": "deleted", "archived": []}]}


@pytest.fixture()
def iso(monkeypatch, tmp_path):
    """Hermetic: no machine OpenClaw home, no real ledger dir, no real CLI."""
    ledger = tmp_path / "openclaw_sessions" / "released_tool_calls.jsonl"
    monkeypatch.setattr(OC, "released_tool_calls_path", lambda: ledger)
    monkeypatch.setattr(OTS, "default_home", lambda: tmp_path / "no_home")
    calls: list[list[str]] = []
    state = {"delete_rc": 0, "delete_out": json.dumps(_DELETED)}

    def run(args, *, timeout=180.0):
        calls.append(list(args))
        if args[:2] == ["sessions", "delete"]:
            return subprocess.CompletedProcess(args, state["delete_rc"], state["delete_out"], "")
        return subprocess.CompletedProcess(args, 0, "{}", "")
    monkeypatch.setattr(OC, "_run", run)
    return {"calls": calls, "ledger": ledger, "state": state}


def test_release_deletes_the_session_and_snapshots_its_tool_calls(iso, monkeypatch):
    t = NOW - timedelta(minutes=1)
    mine = {"agent": "main", "session": f"{OC.SESSION_KEY_PREFIX}aegis-x-1", "utc": _iso(t),
            "tool": "optimus__brain_query", "args_head": "{}"}
    other = {**mine, "session": f"{OC.SESSION_KEY_PREFIX}aegis-y-2"}
    monkeypatch.setattr(OTS, "tool_calls", lambda home, since: ([mine, other], []))
    assert OC.release_session("aegis-x-1", mode="delete") is True
    assert iso["calls"] == [["sessions", "delete", f"{OC.SESSION_KEY_PREFIX}aegis-x-1",
                             "--yes", "--json"]]
    snap = [json.loads(l) for l in iso["ledger"].read_text(encoding="utf-8").splitlines()]
    assert len(snap) == 1 and snap[0]["n_calls"] == 1 and snap[0]["calls"] == [mine]


def test_a_failed_delete_falls_back_to_archive_and_says_false(iso, monkeypatch):
    monkeypatch.setattr(OTS, "tool_calls", lambda home, since: ([], []))
    iso["state"].update(delete_rc=1, delete_out="")
    assert OC.release_session("aegis-x-1", mode="delete") is False
    assert [c[:2] for c in iso["calls"]] == [["sessions", "delete"], ["sessions", "archive"]]


def test_an_unconfirmed_delete_is_not_a_release(iso, monkeypatch):
    """rc 0 with no `deleted` status is the remedy that reports success and
    changes nothing -- exactly what the archive did for a week."""
    monkeypatch.setattr(OTS, "tool_calls", lambda home, since: ([], []))
    iso["state"].update(delete_out=json.dumps({"ok": True, "results": [{"status": "not_found"}]}))
    assert OC.release_session("aegis-x-1", mode="delete") is False


def test_no_snapshot_no_delete_the_audit_evidence_outranks_the_memory(iso, monkeypatch):
    def boom(home, since):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(OTS, "tool_calls", boom)
    assert OC.release_session("aegis-x-1", mode="delete") is False
    assert [c[:2] for c in iso["calls"]] == [["sessions", "archive"]]
    assert not iso["ledger"].exists()


def test_archive_mode_is_the_pre_c14_path_and_never_claims_a_release(iso):
    assert OC.release_session("aegis-x-1", mode="archive") is False
    assert [c[:2] for c in iso["calls"]] == [["sessions", "archive"]]


def test_release_never_raises(iso, monkeypatch):
    monkeypatch.setattr(OTS, "tool_calls", lambda home, since: ([], []))

    def run(args, *, timeout=180.0):
        raise subprocess.TimeoutExpired(args, timeout)
    monkeypatch.setattr(OC, "_run", run)
    assert OC.release_session("aegis-x-1") is False


def test_agent_releases_its_session_even_when_telemetry_raises(iso, monkeypatch, tmp_path):
    """The child-lifecycle contract: whatever happens after the turn, the
    session (and with it the gateway's MCP children) is released."""
    released: list[str] = []
    monkeypatch.setattr(OC, "release_session",
                        lambda sid, **k: released.append(sid) or True)

    def boom(**k):
        raise RuntimeError("ledger write failed")
    monkeypatch.setattr(OC, "_record_telemetry", boom)
    msg = tmp_path / "m.md"
    msg.write_text("hello", encoding="utf-8")
    with pytest.raises(RuntimeError):
        OC.agent(str(msg), purpose="u_forecast")
    assert len(released) == 1 and released[0].startswith("aegis-u_forecast-")


def test_agent_releases_its_session_after_a_timeout(iso, monkeypatch, tmp_path):
    released: list[str] = []
    monkeypatch.setattr(OC, "release_session",
                        lambda sid, **k: released.append(sid) or True)
    monkeypatch.setattr(OC, "_record_telemetry", lambda **k: "call-1")

    def run(args, *, timeout=180.0):
        raise subprocess.TimeoutExpired(args, timeout)
    monkeypatch.setattr(OC, "_run", run)
    msg = tmp_path / "m.md"
    msg.write_text("hello", encoding="utf-8")
    r = OC.agent(str(msg), purpose="u_forecast")
    assert r["status"] == "TIMEOUT" and r["session_released"] is True and len(released) == 1


def test_a_caller_owned_session_is_not_released(iso, monkeypatch, tmp_path):
    released: list[str] = []
    monkeypatch.setattr(OC, "release_session", lambda sid, **k: released.append(sid) or True)
    monkeypatch.setattr(OC, "_record_telemetry", lambda **k: "call-1")
    msg = tmp_path / "m.md"
    msg.write_text("hello", encoding="utf-8")
    r = OC.agent(str(msg), session_id="caller-owned")
    assert released == [] and r["session_released"] is None


# ─────────────────────────────── the audit still sees released calls ─────────

def test_the_tool_scope_audit_reads_released_sessions_back(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "openclaw" / "openclaw_tool_scope_2026-09-29.json"
    home = tmp_path / "home"
    home.mkdir()
    (home / "openclaw.json").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    ledger = tmp_path / "released.jsonl"
    recent = {"agent": "main", "session": f"{OC.SESSION_KEY_PREFIX}aegis-x-1",
              "utc": _iso(NOW - timedelta(hours=1)), "tool": "exec", "args_head": "x"}
    old = {**recent, "utc": _iso(NOW - timedelta(hours=30))}
    ledger.write_text(json.dumps({"calls": [recent, old]}) + "\n", encoding="utf-8")
    r = OTS.audit(home, now=NOW, hours=24, released_path=ledger)
    assert r["verdict"] == "UNSAFE" and [v["tool"] for v in r["violations"]] == ["exec"]
    clean = OTS.audit(home, now=NOW, hours=24, released_path=tmp_path / "absent.jsonl")
    assert clean["verdict"] == "OK" and clean["n_calls"] == 0
