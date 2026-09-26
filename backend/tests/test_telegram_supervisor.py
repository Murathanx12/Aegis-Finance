"""The Telegram agent's liveness evidence (review 2026-09-26 §5 item 3).

The agent died 2026-09-23 01:07Z with no supervisor and `agent.pid` holding a
UTF-8 BOM and a dead pid, while the only health check read the bot TOKEN.
These pin the agent's own evidence: a heartbeat row it writes each loop, read
by age, and a supervisor backoff that resets after a healthy run. No network,
no process is started.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts import telegram_agent as T


def test_the_heartbeat_is_json_without_a_bom_and_names_its_pid(tmp_path):
    p = tmp_path / "heartbeat.json"
    row = T.beat(loops=3, last_poll="ok", path=p)
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "F17: a BOM made agent.pid unparseable"
    assert json.loads(raw.decode("utf-8"))["pid"] == row["pid"]
    assert row["loops"] == 3 and row["last_poll"] == "ok"


def test_heartbeat_age_is_read_from_the_row_not_the_file(tmp_path):
    p = tmp_path / "heartbeat.json"
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")
    p.write_text(json.dumps({"utc": old, "pid": 1}), encoding="utf-8")
    age = T.heartbeat_age_s(p)
    assert 1700 < age < 1900, "age comes from the row's own stamp, never st_mtime"
    assert T.heartbeat_age_s(tmp_path / "absent.json") is None


def test_the_backoff_doubles_to_a_cap_and_resets_after_a_healthy_run():
    assert T.next_backoff(T.BACKOFF_MIN_S, 1) == 2 * T.BACKOFF_MIN_S
    assert T.next_backoff(T.BACKOFF_MAX_S, 1) == T.BACKOFF_MAX_S
    assert T.next_backoff(T.BACKOFF_MAX_S, T.HEALTHY_S + 1) == T.BACKOFF_MIN_S


def test_the_supervisor_kills_only_by_pid():
    import ast
    from pathlib import Path
    src = Path(T.__file__).read_text(encoding="utf-8")
    consts = [n.value for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "/IM" not in consts, "CLAUDE.md protocol 6: never kill by image name"
    assert "/PID" in consts
