"""The desktop window opens on the dashboard, and `/` IS the dashboard (CH-22, 2026-11-14).

The default page became `/` (owner: "I want the original dashboard as well").
Found in the smoke run: the API's JSON index (`@app.get("/")`) is registered
before the export is mounted, so `/` answered the endpoint list, not the page.
`mount_desktop_frontend` removes that one route in the desktop app only.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _export(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("<html>the dashboard</html>", encoding="utf-8")
    return out


def _app() -> FastAPI:
    application = FastAPI()

    @application.get("/")
    async def _index():                                      # noqa: ANN202
        return {"name": "Aegis Finance API"}

    @application.get("/api/health")
    async def _health():                                     # noqa: ANN202
        return {"ok": True}

    return application


def test_root_serves_the_export_not_the_json_index_on_the_desktop(tmp_path, monkeypatch):
    from backend.main import mount_desktop_frontend

    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    monkeypatch.setenv("AEGIS_DESKTOP_FRONTEND", str(_export(tmp_path)))
    application = _app()
    info = mount_desktop_frontend(application)
    assert info["mounted"] and info["root_index_routes_removed"] == 1
    c = TestClient(application)
    r = c.get("/")
    assert r.status_code == 200 and "the dashboard" in r.text
    assert r.headers["content-type"].startswith("text/html")
    assert "the dashboard" in c.get("/?_rsc=abc").text        # the client router's fetch
    assert c.get("/api/health").json() == {"ok": True}         # the API is untouched


def test_the_json_index_stays_when_nothing_is_mounted(tmp_path, monkeypatch):
    from backend.main import mount_desktop_frontend

    monkeypatch.delenv("AEGIS_DESKTOP", raising=False)
    application = _app()
    assert mount_desktop_frontend(application)["mounted"] is False
    assert TestClient(application).get("/").json() == {"name": "Aegis Finance API"}
    # and with the flag but no export, the API keeps its index too
    monkeypatch.setenv("AEGIS_DESKTOP", "1")
    monkeypatch.setenv("AEGIS_DESKTOP_FRONTEND", str(tmp_path / "missing"))
    assert mount_desktop_frontend(application)["mounted"] is False
    assert TestClient(application).get("/").json() == {"name": "Aegis Finance API"}
