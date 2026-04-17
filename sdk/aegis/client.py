"""HTTP client used by every namespace. Single place for timeouts / retries /
error handling / base URL management."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests


class AegisError(RuntimeError):
    """Raised when the backend returns a non-2xx status or a transport error."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AegisClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        self.base_url = (
            base_url
            or os.environ.get("AEGIS_API_URL")
            or "http://localhost:8000"
        ).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def _request(self, method: str, path: str, **kw) -> Any:
        url = f"{self.base_url}{path}"
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.request(method, url, timeout=self.timeout, **kw)
                if r.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                if not r.ok:
                    payload = _json_or_text(r)
                    raise AegisError(
                        f"{method} {path} → {r.status_code}: {payload}",
                        status_code=r.status_code,
                        payload=payload,
                    )
                # Binary endpoints (tearsheet.xlsx) return non-JSON
                ctype = r.headers.get("Content-Type", "")
                if "application/json" in ctype:
                    return r.json()
                if "text/html" in ctype:
                    return r.text
                return r.content
            except requests.RequestException as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise AegisError(f"Transport error calling {path}: {e}") from e
        raise AegisError(f"Request failed after retries: {last_err}")

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Optional[dict] = None) -> Any:
        return self._request("POST", path, json=json)


def _json_or_text(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text[:500]


# ── Process-global default client + configure() helper ───────────────────────

_default_client: Optional[AegisClient] = None


def configure(
    base_url: Optional[str] = None,
    *,
    timeout: float = 60.0,
    max_retries: int = 2,
) -> AegisClient:
    """Replace the default client with a new one. Call once at import time if
    you want non-default settings (e.g. pointing at a staging server)."""
    global _default_client
    _default_client = AegisClient(
        base_url=base_url, timeout=timeout, max_retries=max_retries
    )
    return _default_client


def default_client() -> AegisClient:
    global _default_client
    if _default_client is None:
        _default_client = AegisClient()
    return _default_client
