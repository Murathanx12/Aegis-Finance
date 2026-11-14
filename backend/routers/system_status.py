"""The systems dashboard's two read-only routes (CH-22a) -- local desktop only.

    GET /system-status           the page (HTML), rendered from the newest receipt
    GET /api/control/system-status   the receipt (JSON)

Both only READ `<optimus>/system_status/status.json`, which `python -m
scripts.system_status --html` writes. Neither runs the collector: the collector
shells out (schtasks, gh) and belongs to a scheduled task or an attended command,
not to a request. If the receipt is missing the page says so and names the
command; if it is old the page says how old (the same limit the collector uses).

Gated like the rest of the control plane (`AEGIS_CONTROL_ENABLED=1`, set by the
desktop shell on its own process only): on Railway the receipt does not exist and
the route answers 403, so the page is never public.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from backend import config as C
from backend.routers.control import _require_enabled

router = APIRouter(tags=["system-status"])

REFRESH_COMMAND = "python -m scripts.system_status --html"


def receipt_path() -> Path:
    return Path(C.OPTIMUS_LEDGER_DIR) / "system_status" / "status.json"


def _load() -> dict | None:
    try:
        d = json.loads(receipt_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("receipt") == "system_status/1" else None


@router.get("/api/control/system-status")
def system_status_json() -> dict:
    _require_enabled()
    rec = _load()
    if rec is None:
        raise HTTPException(status_code=404, detail=f"no system_status receipt at {receipt_path()}; run `{REFRESH_COMMAND}`")
    return rec


@router.get("/system-status", response_class=HTMLResponse)
def system_status_page() -> HTMLResponse:
    _require_enabled()
    rec = _load()
    if rec is None:
        # PR #143 review L3: the no-receipt page needs the same way back to the app
        from scripts.system_status import NAV_LINKS
        nav = " · ".join(f"<a href='{html.escape(h, quote=True)}'>{html.escape(t)}</a>"
                         for t, h in NAV_LINKS)
        body = ("<!doctype html><meta charset=utf-8><title>Aegis systems</title>"
                f"<body style='font:14px system-ui;padding:24px'><nav aria-label='Aegis app'>{nav}</nav>"
                "<h1>Aegis systems</h1>"
                f"<p>No status receipt yet at <code>{html.escape(str(receipt_path()))}</code>.</p>"
                f"<p>Run <code>{html.escape(REFRESH_COMMAND)}</code> (read-only), then reload.</p>"
                "<p><a href='/desktop'>Open the lists</a></p></body>")
        return HTMLResponse(body, status_code=404)
    from scripts.system_status import render_html
    return HTMLResponse(render_html(rec))
