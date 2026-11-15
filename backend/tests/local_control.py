"""A TestClient shaped like the desktop app's own page talking to its own server.

Since the PR #143 review (H1) every state-changing control route refuses a request
whose Host is not loopback-with-the-served-port, whose Origin is foreign, or whose
POST is not `Content-Type: application/json`. The default TestClient sends
`Host: testserver` and no Content-Type, i.e. exactly the hostile shape. Tests of
what a route DOES use this client; tests of the guard build the hostile one.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

LOCAL_BASE = "http://127.0.0.1:8000"
JSON_HEADERS = {"Content-Type": "application/json"}


def local_client(app, **kw) -> TestClient:
    headers = {**JSON_HEADERS, **kw.pop("headers", {})}
    return TestClient(app, base_url=LOCAL_BASE, headers=headers, **kw)
