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

logger = logging.getLogger(__name__)

SLOW_REQUEST_THRESHOLD_S = config["performance"]["slow_request_threshold_s"]


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure and log request processing time."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_s = time.perf_counter() - start

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
