"""The desktop window opens on the dashboard, and `/` IS the dashboard (CH-22, 2026-11-14).

The default page became `/` (owner: "I want the original dashboard as well").
Found in the smoke run: the API's JSON index (`@app.get("/")`) is registered
before the export is mounted, so `/` answered the endpoint list, not the page.
`mount_desktop_frontend` removes that one route in the desktop app only.
"""

from __future__ import annotations

import pytest
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


_CORS_PROBE = """
import json
from backend.main import app
cors = [m for m in app.user_middleware if getattr(m.cls, "__name__", "") == "CORSMiddleware"]
print(json.dumps(list(cors[0].kwargs.get("allow_origins", []))))
"""


@pytest.mark.parametrize("desktop", [True, False])
def test_desktop_mode_allows_no_cross_origin_reader(desktop):
    """PR #143 review H1: in the desktop app the page is same-origin, so the
    website and :3000 must not be able to read the local control plane. The
    website (no AEGIS_DESKTOP) keeps its list. A fresh process, because the list
    is fixed when `backend.main` is imported."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k not in ("AEGIS_DESKTOP", "ALLOWED_ORIGINS")}
    env["AEGIS_IGNORE_DOTENV"] = "1"
    if desktop:
        env["AEGIS_DESKTOP"] = "1"
    out = subprocess.run([sys.executable, "-c", _CORS_PROBE], cwd=str(repo), env=env,
                         capture_output=True, text=True, timeout=240)
    assert out.returncode == 0, out.stderr[-1500:]
    origins = json.loads(out.stdout.strip().splitlines()[-1])
    if desktop:
        assert origins == []
    else:
        assert "https://aegis-finance-six.vercel.app" in origins and "http://localhost:3000" in origins
