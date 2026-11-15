"""
Aegis Finance — Request Timing Middleware
==========================================

Logs request duration, adds X-Process-Time header, warns on slow requests.
Provides observability for identifying performance bottlenecks.

Usage:
    from backend.middleware import add_timing_middleware
    add_timing_middleware(app)
"""

import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.config import config
from backend.services import usage_receipt

logger = logging.getLogger(__name__)

SLOW_REQUEST_THRESHOLD_S = config["performance"]["slow_request_threshold_s"]


def _record_usage(request: Request, status: int) -> None:
    """Feed the usage receipt (flag-gated by the caller). Never raises, never logs an identifier."""
    try:
        route = getattr(request.scope.get("route"), "path", None)
        peer = request.client.host if request.client else None
        ip = usage_receipt.client_ip(request.headers, peer)
        usage_receipt.get_recorder().record_request(
            route=route,
            path_params=request.scope.get("path_params") or {},
            status=status,
            ip=ip,
            user_agent=request.headers.get("user-agent", ""),
            raw_path=request.url.path,
        )
    except Exception as exc:  # observability must not break a request
        logger.warning("usage receipt failed: %s", type(exc).__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure and log request processing time."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        usage_on = usage_receipt.is_enabled() and not request.url.path.startswith("/api/usage/")
        try:
            response = await call_next(request)
        except Exception:
            if usage_on:
                _record_usage(request, 500)
            raise
        duration_s = time.perf_counter() - start
        if usage_on:
            _record_usage(request, response.status_code)

        # Add timing header to every response
        response.headers["X-Process-Time"] = f"{duration_s:.3f}s"

        path = request.url.path
        method = request.method

        if duration_s >= SLOW_REQUEST_THRESHOLD_S:
            logger.warning(
                "SLOW REQUEST: %s %s took %.1fs", method, path, duration_s
            )
        elif duration_s >= 1.0:
            logger.info(
                "%s %s completed in %.2fs", method, path, duration_s
            )

        return response


def add_timing_middleware(app):
    """Register timing middleware on a FastAPI app."""
    app.add_middleware(TimingMiddleware)
