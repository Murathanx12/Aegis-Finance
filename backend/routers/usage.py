"""Usage receipt routes (flag-gated; see backend/services/usage_receipt.py).

    POST /api/usage/pageview   {"path": "/stock/NVDA"}   -> 204  (beacon, no cookies)
    GET  /api/usage/summary    header X-Usage-Token      -> counts since process start

Both answer 404 unless AEGIS_USAGE_RECEIPT=1. The summary also needs AEGIS_USAGE_TOKEN to be
set (it refuses when unset) and the same value in the `X-Usage-Token` header.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, Response

from backend.config import config
from backend.services import usage_receipt as ur

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _require_enabled() -> None:
    if not ur.is_enabled():
        raise HTTPException(status_code=404, detail="Not Found")


@router.post("/pageview", status_code=204)
async def pageview(request: Request) -> Response:
    _require_enabled()
    origin = request.headers.get("origin")
    allowed = getattr(request.app.state, "cors_origins", None) or []
    if not origin or origin not in allowed:
        raise HTTPException(status_code=403, detail="origin not allowed")
    limit = config["usage_receipt"]["beacon_max_body_bytes"]
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail="body too large")
    body = await request.body()
    if len(body) > limit:
        raise HTTPException(status_code=413, detail="body too large")
    try:
        data = json.loads(body.decode("utf-8"))
        path = data.get("path") if isinstance(data, dict) and set(data) == {"path"} else None
    except (ValueError, UnicodeDecodeError):
        path = None
    template = ur.normalize_page(path) if path is not None else None
    if template is None:
        raise HTTPException(status_code=422, detail="path not allowed")
    peer = request.client.host if request.client else None
    ip = ur.client_ip(request.headers, peer)
    outcome = ur.get_recorder().record_pageview(template, ip, request.headers.get("user-agent", ""))
    if outcome == "rate_limited":
        raise HTTPException(status_code=429, detail="rate limited")
    return Response(status_code=204)


@router.get("/summary")
def summary(request: Request) -> dict:
    _require_enabled()
    ok, reason = ur.token_ok(request.headers.get(ur.TOKEN_HEADER))
    if not ok:
        raise HTTPException(status_code=403 if reason == "bad_token" else 503,
                            detail=f"usage summary refused: {reason}")
    return ur.get_recorder().summary()
