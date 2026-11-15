"""The desktop control plane does not exist off the desktop (CH-22 follow-up, 2026-11-15).

Until this, only the mutating control routes were checked, so on the website
deployment every READ of the plane answered. Now:

(a) with `AEGIS_CONTROL_ENABLED` unset, EVERY route under `CONTROL_PLANE_PREFIXES`
    -- enumerated from the real `backend.main.app`, so a route added later is
    covered without being listed -- answers 404 for every method, byte-identical to
    a path that was never written (no 403, 405 or 422 to say it exists); and a
    structural test fails if any such route lacks `control_plane_gate` or the
    `ControlPlaneRoute` class;
(b) with it set, a loopback client with the right Host still reads;
(c) with it set, a foreign Origin, a non-loopback Host, a cross-site fetch or a
    non-loopback TCP peer is refused on READS too.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import control as CR
from backend.tests.local_control import LOCAL_BASE, local_client

#: never on a public allow-list (the brief's list); every one must be gated.
NEVER_PUBLIC = ("/api/control/file", "/api/control/tree", "/api/control/balances",
                "/api/control/fleet", "/api/control/app-log", "/api/control/ledger",
                "/api/control/runs/{pid}/log", "/api/control/reader", "/api/control/sim",
                "/api/control/sim/history", "/api/control/sim/preflight", "/api/control/llama")


def _leaf_routes(application):
    """Route objects with `.path`, `.methods`, `.dependant`, `.original_route`-or-self.

    FastAPI >= 0.14x wraps included routers (`_IncludedRouter`), so `app.routes`
    alone no longer lists the leaves; older versions list them directly."""
    import fastapi.routing as fr
    if hasattr(fr, "iter_route_contexts"):
        return list(fr.iter_route_contexts(application.routes))
    return list(application.routes)


def _is_control_plane(path: str | None) -> bool:
    # prefix match on purpose: `/api/controlX` is still claimed by the plane
    return bool(path) and any(path.startswith(p) for p in CR.CONTROL_PLANE_PREFIXES)


def _control_routes():
    return [r for r in _leaf_routes(app) if _is_control_plane(getattr(r, "path", None))]


def _calls(dependant) -> list:
    out = [dependant.call]
    for sub in dependant.dependencies:
        out += _calls(sub)
    return out


def _concrete(path: str) -> str:
    # any value: off the desktop nothing is routed, so nothing is validated
    return re.sub(r"\{[^}]+\}", "1", path)


def _off(monkeypatch):
    monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)


def _on(monkeypatch):
    monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")


# ------------------------------------------------------------------ structure


def test_the_enumeration_sees_the_whole_plane():
    """A filter that matched nothing would make every test below vacuous."""
    paths = {r.path for r in _control_routes()}
    for must in NEVER_PUBLIC + ("/system-status", "/api/control/system-status",
                                "/api/control/owner-notes", "/api/control/owner-note",
                                "/api/control/ask", "/api/control/ticker/{symbol}/hub",
                                "/api/control/universe", "/api/control/coverage"):
        assert must in paths, f"{must} is not mounted under the control-plane prefixes"
    assert len(paths) >= 45, len(paths)


def test_every_control_plane_route_carries_the_gate_and_the_route_class():
    """THE test that fails when a route is added without the gate: a new router
    under /api/control that is built with a bare `APIRouter` lands here."""
    missing_gate, wrong_class = [], []
    for r in _control_routes():
        original = getattr(r, "original_route", r)
        if not isinstance(original, CR.ControlPlaneRoute):
            wrong_class.append(r.path)
        if CR.control_plane_gate not in _calls(r.dependant):
            missing_gate.append(r.path)
    assert not missing_gate, f"control-plane routes without control_plane_gate: {sorted(set(missing_gate))}"
    assert not wrong_class, f"control-plane routes not built by control_plane_router(): {sorted(set(wrong_class))}"


def test_the_public_schema_does_not_list_the_plane(monkeypatch):
    _off(monkeypatch)
    schema = TestClient(app).get("/openapi.json")
    assert schema.status_code == 200
    listed = [p for p in schema.json().get("paths", {}) if _is_control_plane(p)]
    assert not listed, listed


def test_the_gate_runs_before_the_routes_own_dependencies():
    for r in _control_routes():
        first = r.dependant.dependencies[0].call if r.dependant.dependencies else None
        assert first is CR.control_plane_gate, f"{r.path}: first dependency is {first!r}"


# ------------------------------------------------------------- (a) off -> 404


@pytest.mark.parametrize("which", ["hostile", "local"])
def test_off_the_desktop_every_route_and_method_is_a_plain_404(monkeypatch, which):
    _off(monkeypatch)
    client = TestClient(app) if which == "hostile" else local_client(app)
    never = client.get("/api/control/__never_written__")
    assert never.status_code == 404
    seen = 0
    for r in _control_routes():
        url = _concrete(r.path)
        for method in sorted((r.methods or set()) | {"GET", "POST", "DELETE"}):
            kw = {"content": b"{not json", "headers": {"content-type": "application/json"}} \
                if method == "POST" else {}
            resp = client.request(method, url, **kw)
            assert resp.status_code == 404, (method, url, resp.status_code, resp.text[:200])
            assert resp.content == never.content, (method, url, resp.text[:200])
            seen += 1
    assert seen >= 140, seen


def test_off_the_desktop_the_brief_named_reads_are_404_with_a_query(monkeypatch):
    _off(monkeypatch)
    c = TestClient(app)
    for url in ("/api/control/file?path=README.md", "/api/control/tree?root=scripts",
                "/api/control/balances", "/api/control/fleet", "/api/control/app-log",
                "/api/control/ledger", "/api/control/runs/1/log", "/api/control/reader",
                "/api/control/sim/preflight", "/api/control/llama", "/system-status"):
        assert c.get(url).status_code == 404, url


def test_the_gate_itself_answers_404_when_off(monkeypatch):
    """Second line: if the route class ever stopped hiding a route, the dependency
    still answers 404 rather than letting the read through."""
    from fastapi import HTTPException
    from starlette.requests import Request

    _off(monkeypatch)
    req = Request({"type": "http", "method": "GET", "path": "/api/control/tree",
                   "headers": [(b"host", b"127.0.0.1:8000")], "client": ("127.0.0.1", 5),
                   "server": ("127.0.0.1", 8000), "query_string": b""})
    with pytest.raises(HTTPException) as exc:
        CR.control_plane_gate(req)
    assert exc.value.status_code == 404


# ------------------------------------------------------ (b) desktop -> reads


def test_on_the_desktop_a_local_page_still_reads(monkeypatch, tmp_path):
    _on(monkeypatch)
    from backend import config as C
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    c = local_client(app)
    r = c.get("/api/control/jobs")
    assert r.status_code == 200 and r.json()["whitelist"], r.text[:200]
    r = c.get("/api/control/tree", params={"root": "scripts"})
    assert r.status_code == 200, r.text[:200]
    r = c.get("/api/control/file", params={"path": "backend/routers/control.py"})
    assert r.status_code == 200 and "control_plane_gate" in r.json().get("text", ""), r.text[:200]
    r = c.get("/api/control/owner-notes")
    assert r.status_code == 200, r.text[:200]
    # the systems page with no receipt: its own honest 404 page, not the gate's
    r = c.get("/system-status")
    assert r.status_code == 404 and "No status receipt yet" in r.text


def test_on_the_desktop_a_secret_is_still_refused_by_name(monkeypatch):
    _on(monkeypatch)
    r = local_client(app).get("/api/control/file", params={"path": ".env"})
    assert r.status_code == 403


# --------------------------------------------- (c) desktop -> refused for reads


READS = ("/api/control/jobs", "/api/control/tree", "/api/control/balances",
         "/api/control/owner-notes", "/system-status", "/api/control/system-status")


@pytest.mark.parametrize("url", READS)
def test_on_the_desktop_a_foreign_origin_cannot_read(monkeypatch, url):
    _on(monkeypatch)
    r = local_client(app, headers={"Origin": "https://evil.example"}).get(url)
    assert r.status_code == 403 and "cross-origin" in r.text


@pytest.mark.parametrize("url", READS)
def test_on_the_desktop_a_rebound_host_cannot_read(monkeypatch, url):
    _on(monkeypatch)
    r = TestClient(app, base_url="http://evil.example:8000").get(url)
    assert r.status_code == 403 and "loopback" in r.text


@pytest.mark.parametrize("url", READS)
def test_on_the_desktop_a_cross_site_fetch_cannot_read(monkeypatch, url):
    _on(monkeypatch)
    r = local_client(app, headers={"Sec-Fetch-Site": "cross-site"}).get(url)
    assert r.status_code == 403 and "Sec-Fetch-Site" in r.text


@pytest.mark.parametrize("peer", ["192.168.1.20", "10.0.0.5", "8.8.8.8", "::ffff:192.168.1.20"])
def test_on_the_desktop_a_network_peer_cannot_read_even_with_a_loopback_host(monkeypatch, peer):
    _on(monkeypatch)
    c = TestClient(app, base_url=LOCAL_BASE, client=(peer, 40000))
    for url in READS:
        r = c.get(url)
        assert r.status_code == 403 and "loopback only" in r.text, (peer, url, r.text[:200])


@pytest.mark.parametrize("peer", ["127.0.0.1", "127.5.6.7", "::1", "::ffff:127.0.0.1"])
def test_a_loopback_peer_passes_the_peer_check(monkeypatch, peer):
    _on(monkeypatch)
    r = TestClient(app, base_url=LOCAL_BASE, client=(peer, 40000)).get("/api/control/jobs")
    assert r.status_code == 200, (peer, r.text[:200])
