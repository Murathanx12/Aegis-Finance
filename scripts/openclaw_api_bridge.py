"""Aegis's own FastAPI, exposed to OpenClaw as READ-ONLY MCP tools (stdio).

    openclaw mcp add aegis_api --command <optimus venv python> \\
        --arg C:\\Users\\mrthn\\aegis-finance\\scripts\\openclaw_api_bridge.py \\
        --include aegis_health_full,aegis_pi_get --approval prompt

Two tools, GET only, never a broker or order route:

* `aegis_health_full()`   -> GET /api/health/full
* `aegis_pi_get(route)`   -> GET /api/pi/<route>, where `route` must match
  `READ_ROUTES` (registry, alerts, track-record, lane positions, ...).

It runs under the Optimus venv's Python (which carries the `mcp` SDK), and it
needs no key: the routes are the public read surface of the deployed backend
(`AEGIS_API_BASE`, default the production URL Optimus already reads). The
chain stays `OpenClaw -> Aegis -> Telegram`: this bridge answers the agent, and
nothing here can message anyone or place anything.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = os.environ.get("AEGIS_API_BASE", "https://aegis-finance-production.up.railway.app").rstrip("/")

#: The ONLY `/api/pi/*` paths the bridge will GET (portfolio_intelligence.py
#: read routes). Anything else is refused before a request is made.
READ_ROUTES: tuple[str, ...] = (
    r"registry", r"fragility", r"risk-watch", r"alerts", r"conviction/calibration",
    r"conviction/decisions", r"track-record", r"paper-accounts", r"compare",
    r"lane/[A-Za-z0-9_\-]+/(positions|stats-ci|tearsheet)",
    r"reference/[A-Za-z0-9_\-]+/(state|history|explain|snapshot)",
)
_ROUTE_RE = re.compile(r"^(" + "|".join(READ_ROUTES) + r")$")
MAX_CHARS = 20000

#: The heartbeat the health probe reads (C8, 2026-10-07): before it, the
#: `openclaw_api_bridge` row was UNKNOWN every night because the bridge wrote
#: nothing. One JSON file, rewritten atomically on server start and on EVERY tool
#: call -- the last call's own stamp, tool, ok/error, and running counts. Stdlib
#: only (this runs under the Optimus venv); a failed write never fails a call.
_DATA_DIR = Path(os.environ.get("AEGIS_DATA_DIR") or Path(__file__).resolve().parents[1] / "backend" / "data")
HEARTBEAT = _DATA_DIR / "optimus" / "openclaw_api_bridge" / "heartbeat.json"
_STATE: dict = {"n_calls": 0, "n_errors": 0}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _beat(**kw) -> None:
    try:
        _STATE.update(kw)
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(HEARTBEAT.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"receipt": "openclaw_api_bridge", "pid": os.getpid(), **_STATE}, fh)
        os.replace(tmp, HEARTBEAT)
    except Exception:  # noqa: BLE001 -- the heartbeat must never break the tool
        pass


def _record(tool: str, route: str, body: str) -> str:
    err = refused = None          # a refused route is the bridge WORKING; an error is not
    try:
        j = json.loads(body)
        if isinstance(j, dict):
            err = str(j["error"])[:200] if "error" in j else None
            refused = str(j["refused"])[:200] if "refused" in j else None
    except ValueError:
        pass
    _STATE["n_calls"] = int(_STATE.get("n_calls") or 0) + 1
    if err:
        _STATE["n_errors"] = int(_STATE.get("n_errors") or 0) + 1
    _beat(last_call_utc=_utc(), last_tool=tool, last_route=route, last_ok=err is None,
          last_error=err, last_refused=refused)
    return body


def route_allowed(route: str) -> bool:
    r = (route or "").strip().strip("/")
    return bool(_ROUTE_RE.match(r.split("?")[0])) and ".." not in r


def _get(path: str) -> str:
    req = urllib.request.Request(API_BASE + path, method="GET",
                                 headers={"User-Agent": "aegis-openclaw-bridge/1"})
    try:
        with urllib.request.urlopen(req, timeout=45) as fh:  # noqa: S310 fixed base
            body = fh.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"HTTP {e.code}", "path": path})
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"{type(e).__name__}: {e}"[:200], "path": path})
    return body[:MAX_CHARS]


def aegis_health_full() -> str:
    """GET /api/health/full from the deployed Aegis backend (read-only)."""
    return _record("aegis_health_full", "/api/health/full", _get("/api/health/full"))


def aegis_pi_get(route: str) -> str:
    """GET /api/pi/<route> for one allow-listed read route (e.g. 'alerts',
    'track-record', 'lane/<id>/positions'). Refuses anything else."""
    if not route_allowed(route):
        return _record("aegis_pi_get", str(route)[:80],
                       json.dumps({"refused": f"route {route!r} is not an allow-listed read route",
                                   "allowed": list(READ_ROUTES)}))
    return _record("aegis_pi_get", route, _get("/api/pi/" + route.strip().strip("/")))


def main() -> None:
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("aegis_api")
    _beat(started_utc=_utc(), transport="mcp_stdio")
    server.tool()(aegis_health_full)
    server.tool()(aegis_pi_get)
    server.run()


if __name__ == "__main__":
    main()
