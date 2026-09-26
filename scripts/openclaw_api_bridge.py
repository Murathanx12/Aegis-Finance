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
import urllib.error
import urllib.request

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
    return _get("/api/health/full")


def aegis_pi_get(route: str) -> str:
    """GET /api/pi/<route> for one allow-listed read route (e.g. 'alerts',
    'track-record', 'lane/<id>/positions'). Refuses anything else."""
    if not route_allowed(route):
        return json.dumps({"refused": f"route {route!r} is not an allow-listed read route",
                           "allowed": list(READ_ROUTES)})
    return _get("/api/pi/" + route.strip().strip("/"))


def main() -> None:
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("aegis_api")
    server.tool()(aegis_health_full)
    server.tool()(aegis_pi_get)
    server.run()


if __name__ == "__main__":
    main()
