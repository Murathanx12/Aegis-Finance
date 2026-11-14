"""The owner's "Note to Claude" inbox (CH-22, 2026-11-14).

Pinned here: the two routes refuse when the control plane is off (the notes are
never public), an empty note is a 422 and writes nothing, a saved note comes back
with its id, the file only ever grows (append-only; mark-read appends a status
row), GET is newest first, and the router imports no broker and calls no LLM.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import owner_inbox as R
from scripts import owner_inbox as IB


def _client(monkeypatch, tmp_path, enabled: bool = True) -> TestClient:
    monkeypatch.setattr(IB.C, "OPTIMUS_LEDGER_DIR", tmp_path)
    if enabled:
        monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
    else:
        monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app)


def _file(tmp_path: Path) -> Path:
    return tmp_path / "owner_inbox" / "notes.jsonl"


def test_both_routes_refuse_when_the_control_plane_is_off(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, enabled=False)
    assert c.post("/api/control/owner-note", json={"text": "hi"}).status_code == 403
    assert c.get("/api/control/owner-notes").status_code == 403
    assert not _file(tmp_path).exists()


@pytest.mark.parametrize("text", ["", "   \n\t ", None, 42])
def test_an_empty_or_non_text_note_is_a_422_and_writes_nothing(monkeypatch, tmp_path, text):
    c = _client(monkeypatch, tmp_path)
    r = c.post("/api/control/owner-note", json={"text": text})
    assert r.status_code == 422
    assert not _file(tmp_path).exists()


def test_a_note_over_the_limit_is_refused_not_cut(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.post("/api/control/owner-note", json={"text": "x" * (IB.C.OWNER_INBOX_MAX_CHARS + 1)})
    assert r.status_code == 422 and "limit" in r.json()["detail"]
    assert not _file(tmp_path).exists()


def test_a_saved_note_returns_its_id_and_is_on_disk(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.post("/api/control/owner-note", json={"text": "  check NVDA tomorrow \n", "page": "/stock/NVDA"})
    assert r.status_code == 200
    note = r.json()["note"]
    assert note["text"] == "check NVDA tomorrow"           # trimmed
    assert note["status"] == "unread" and note["page"] == "/stock/NVDA" and note["utc"]
    assert len(note["id"]) == 36
    rows = [json.loads(x) for x in _file(tmp_path).read_text(encoding="utf-8").splitlines()]
    assert rows == [note]


def test_the_file_only_grows_and_get_is_newest_first(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    ids = []
    sizes = []
    for i in range(3):
        ids.append(c.post("/api/control/owner-note", json={"text": f"note {i}"}).json()["note"]["id"])
        sizes.append(_file(tmp_path).stat().st_size)
    before = _file(tmp_path).read_bytes()
    assert sizes == sorted(sizes) and len(set(sizes)) == 3
    IB.mark(ids[0], data_root=tmp_path)
    after = _file(tmp_path).read_bytes()
    assert after.startswith(before) and len(after) > len(before)   # appended, never rewritten
    got = c.get("/api/control/owner-notes").json()
    assert [n["id"] for n in got["notes"]] == list(reversed(ids))
    assert got["n_notes"] == 3 and got["n_unread"] == 2
    assert {n["id"]: n["status"] for n in got["notes"]}[ids[0]] == "read"
    assert [n["id"] for n in c.get("/api/control/owner-notes?limit=2").json()["notes"]] == [ids[2], ids[1]]
    assert c.get("/api/control/owner-notes?limit=0").status_code == 422


def test_a_torn_line_is_counted_not_fatal(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    c.post("/api/control/owner-note", json={"text": "kept"})
    with open(_file(tmp_path), "a", encoding="utf-8") as fh:
        fh.write('{"kind": "note", "id": "x", "te\n')
    got = c.get("/api/control/owner-notes").json()
    assert got["n_notes"] == 1 and got["unreadable_lines"] == 1


# -- the CLI the brain session reads the notes with --------------------------------

def test_cli_list_and_mark_read(tmp_path, capsys):
    a = IB.add_note("first", data_root=tmp_path)
    b = IB.add_note("second", data_root=tmp_path)
    assert IB.main(["list", "--data-root", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [n["id"] for n in out["notes"]] == [b["id"], a["id"]] and out["n_unread"] == 2
    assert IB.main(["mark-read", a["id"], "--data-root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert IB.main(["list", "--unread", "--data-root", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [n["id"] for n in out["notes"]] == [b["id"]] and out["n_unread"] == 1
    assert IB.main(["list", "--data-root", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "2 notes, 1 unread" in text and "[read]" in text and "second" in text


def test_cli_mark_read_of_an_unknown_id_is_a_red_exit(tmp_path, capsys):
    IB.add_note("only", data_root=tmp_path)
    before = IB.inbox_path(tmp_path).read_bytes()
    assert IB.main(["mark-read", "not-an-id", "--data-root", str(tmp_path)]) == 2
    assert "REFUSED" in capsys.readouterr().err
    assert IB.inbox_path(tmp_path).read_bytes() == before


def test_cli_list_of_a_missing_inbox_says_zero(tmp_path, capsys):
    assert IB.main(["list", "--data-root", str(tmp_path)]) == 0
    assert "0 notes, 0 unread" in capsys.readouterr().out
    assert not IB.inbox_path(tmp_path).exists()


# -- authority: no broker, no LLM, no outbound call --------------------------------

@pytest.mark.parametrize("mod", [R, IB])
def test_the_inbox_imports_no_broker_llm_or_network(mod):
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module or ''}.{a.name}" for a in node.names)
    joined = " ".join(sorted(names)).lower()
    forbidden = ("alpaca", "broker", "order", "trade_api", "llm", "deepseek", "requests",
                 "httpx", "urllib", "subprocess", "provider_budget")
    assert not [f for f in forbidden if f in joined], sorted(names)


def test_the_router_is_registered_in_the_app():
    src = (Path(R.__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(owner_inbox.router)" in src
