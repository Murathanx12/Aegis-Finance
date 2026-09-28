"""Browser verbs over the gateway's `POST /tools/invoke`: no process per verb.

LANE O3, 2026-09-28. Every OpenClaw CLI call is a fresh `node openclaw.mjs`
process: measured 7-12 s per browser verb on 2026-09-28 (status 9.4 s, tabs
7.3 s, snapshot 11.8 s), against 0.4-1.8 s for the same verbs over one
keep-alive HTTP connection to the gateway.

THIS MODULE HOLDS NO POLICY. It is a TRANSPORT: `openclaw_client._run` hands
it the same argv it would hand the CLI, after every guard has run, and gets
back a `CompletedProcess` whose stdout is shaped like the CLI's, so every
parser and every post-action check downstream is the same code on both
routes. `test_openclaw_http_transport` counts the guards per action on both
transports and fails if the HTTP path skips one.

What it maps (anything else returns None and the caller uses the CLI):

    tabs, status            -> {"action": <verb>}                 stdout = JSON details
    navigate URL            -> {"action": "navigate", targetUrl}  stdout = "navigated to <url>"
    open URL                -> {"action": "open", targetUrl}      stdout = JSON details
    close / focus ID        -> {"action": <verb>, targetId}       stdout = JSON details
    snapshot                -> {"action": "snapshot", ...}        stdout = the snapshot text
    evaluate --fn F         -> {"action": "act", kind: evaluate}  stdout = JSON {targetId, result}
    press K / click R       -> {"action": "act", kind, key|ref}   stdout = JSON details
    scrollintoview R        -> {"action": "act", kind: scrollIntoView, ref}
    wait --time N           -> {"action": "act", kind: wait, timeMs}

A snapshot the gateway TRUNCATED (its tool result is capped at 16,000
characters, measured 2026-09-28: `maxChars` does not lift it) comes back with
`http_truncated = True` and the caller re-runs that one verb on the CLI; a
truncated snapshot would silently drop the links at the end of a page.

Errors: an HTTP error or `ok: false` is rc 1 with the gateway's message on
stderr (the same shape as a failed CLI verb); a refused connection is rc 1 with
"gateway unreachable: ECONNREFUSED" so `web_reader.GATEWAY_DOWN` matches it; a
timeout raises `subprocess.TimeoutExpired`, as the CLI route does.

The gateway token is read from `OPENCLAW_GATEWAY_TOKEN` or `openclaw.json`
(`gateway.auth.token`) and is never logged, printed or put in an error.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from backend import config as _config

#: Verbs served over HTTP. Everything else (profiles, start, stop, gateway,
#: config, channels, agent, screenshot) stays on the CLI.
HTTP_VERBS: frozenset[str] = frozenset({"tabs", "status", "navigate", "open", "close", "focus",
                                        "snapshot", "evaluate", "press", "click",
                                        "scrollintoview", "wait"})

_VALUE_FLAGS = frozenset({"--browser-profile", "--target-id", "--fn", "--time", "--format",
                          "--limit", "--max-chars", "--label"})
_BOOL_FLAGS = frozenset({"--json", "--urls", "--interactive", "--compact"})

_WRAP_START = re.compile(r"<<<EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>\s*\n(?:Source:[^\n]*\n)?"
                         r"(?:---\s*\n)?", re.S)
_WRAP_END = re.compile(r"\n?<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>\s*$", re.S)


def navigate_timeout_ms() -> int:
    """`timeoutMs` for an HTTP navigate/open: config, clamped to the gateway's
    own 1-120 s range."""
    v = int(getattr(_config, "OPENCLAW_HTTP_NAVIGATE_TIMEOUT_MS", 75000) or 75000)
    return max(1000, min(120000, v))


def base_url() -> str:
    return (f"http://{getattr(_config, 'OPENCLAW_GATEWAY_HOST', '127.0.0.1')}:"
            f"{int(getattr(_config, 'OPENCLAW_GATEWAY_PORT', 18789))}")


def _token_from_config() -> str | None:
    env = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if env:
        return env
    p = Path(getattr(_config, "OPENCLAW_CONFIG_PATH", Path.home() / ".openclaw" / "openclaw.json"))
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tok = ((d.get("gateway") or {}).get("auth") or {}).get("token")
    return str(tok) if tok else None


def parse_argv(args: list[str]) -> dict | None:
    """`browser [--browser-profile P] [--json] VERB [pos...] [--flag v]` ->
    `{profile, verb, pos, flags}`, or None when it is not a browser verb."""
    if not args or args[0] != "browser":
        return None
    flags: dict[str, Any] = {}
    pos: list[str] = []
    i = 1
    while i < len(args):
        a = str(args[i])
        if a in _VALUE_FLAGS and i + 1 < len(args):
            flags[a] = str(args[i + 1])
            i += 2
            continue
        if a in _BOOL_FLAGS:
            flags[a] = True
            i += 1
            continue
        if a.startswith("--"):
            return None                      # an unknown flag: let the CLI own it
        pos.append(a)
        i += 1
    if not pos:
        return None
    return {"profile": flags.get("--browser-profile"), "verb": pos[0], "pos": pos[1:],
            "flags": flags}


def tool_args(p: dict) -> dict | None:
    """The `/tools/invoke` `args` for a parsed argv, or None if not served."""
    verb, pos, fl = p["verb"], p["pos"], p["flags"]
    if verb not in HTTP_VERBS:
        return None
    out: dict[str, Any] = {}
    if p.get("profile"):
        out["profile"] = p["profile"]
    tid = fl.get("--target-id")
    if verb in ("tabs", "status"):
        out["action"] = verb
    elif verb in ("navigate", "open"):
        if not pos:
            return None
        out.update(action=verb, targetUrl=pos[0])
        if tid and verb == "navigate":
            out["targetId"] = tid
        # Playwright's default wait for "load" is 20 s; MarketWatch fires it after
        # 50-60 s, and the gateway then answers only "tool execution failed"
        # (the rc 1 left unexplained by the lane-O build; reproduced 2026-09-28)
        out["timeoutMs"] = navigate_timeout_ms()
    elif verb in ("close", "focus"):
        t = pos[0] if pos else tid
        if not t:
            return None
        out.update(action=verb, targetId=t)
    elif verb == "snapshot":
        out.update(action="snapshot", snapshotFormat=fl.get("--format", "ai"))
        if tid:
            out["targetId"] = tid
        for k, name in (("--urls", "urls"), ("--interactive", "interactive"),
                        ("--compact", "compact")):
            if fl.get(k):
                out[name] = True
        if fl.get("--limit"):
            out["limit"] = int(fl["--limit"])
    elif verb == "evaluate":
        if not fl.get("--fn") or not tid:
            return None
        out.update(action="act", kind="evaluate", fn=fl["--fn"], targetId=tid)
    elif verb in ("press", "click", "scrollintoview"):
        if not pos or not tid:
            return None
        kind = {"press": "press", "click": "click", "scrollintoview": "scrollIntoView"}[verb]
        out.update(action="act", kind=kind, targetId=tid)
        out["key" if verb == "press" else "ref"] = pos[0]
    elif verb == "wait":
        if not fl.get("--time"):
            return None
        out.update(action="act", kind="wait", timeMs=int(fl["--time"]))
        if tid:
            out["targetId"] = tid
    return out


def unwrap(text: str) -> str:
    """The payload inside the gateway's EXTERNAL_UNTRUSTED_CONTENT wrapper (the
    security notice before it and the end marker after it removed)."""
    t = text or ""
    m = _WRAP_START.search(t)
    if m:
        t = t[m.end():]
    return _WRAP_END.sub("", t)


def render(verb: str, result: dict) -> tuple[str, bool]:
    """(CLI-shaped stdout, truncated?) for one tool result."""
    details = result.get("details") if isinstance(result, dict) else None
    details = details if isinstance(details, dict) else {}
    content = result.get("content") if isinstance(result, dict) else None
    text = ""
    if isinstance(content, list):
        text = "\n".join(str(c.get("text") or "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text")
    if verb == "navigate":
        return f"navigated to {details.get('url') or ''}", False
    if verb == "snapshot":
        snap = details.get("snapshot")
        body = snap if isinstance(snap, str) and snap else unwrap(text)
        truncated = bool(details.get("truncated")) or "[truncated" in body[-200:]
        return body, truncated
    if verb == "evaluate":
        res = details.get("result", details)
        return json.dumps({"ok": details.get("ok", True), "targetId": details.get("targetId"),
                           "url": details.get("url"), "result": res}), False
    clean = {k: v for k, v in details.items() if k != "externalContent"}
    return json.dumps(clean) if clean else (unwrap(text) or "ok"), False


class HttpTransport:
    """One keep-alive session to the gateway. `session` is anything with a
    `post(url, json=, headers=, timeout=)` returning an object with
    `.status_code` and `.json()` -- `requests.Session` in production, a fake in
    tests."""

    def __init__(self, *, session: Any = None, token_fn: Callable[[], str | None] | None = None,
                 url: str | None = None) -> None:
        self._session = session
        self._token_fn = token_fn or _token_from_config
        self._url = url
        self.calls = 0

    def _sess(self) -> Any:
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def serves(self, args: list[str]) -> bool:
        p = parse_argv([str(a) for a in args])
        return bool(p) and tool_args(p) is not None

    def run(self, args: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess | None:
        p = parse_argv([str(a) for a in args])
        if not p:
            return None
        targs = tool_args(p)
        if targs is None:
            return None
        tok = self._token_fn()
        if not tok:
            return subprocess.CompletedProcess(args, 1, "", "gateway token unavailable: set "
                                               "OPENCLAW_GATEWAY_TOKEN or gateway.auth.token")
        url = (self._url or base_url()) + "/tools/invoke"
        self.calls += 1
        try:
            body: dict[str, Any] = {"tool": "browser", "args": targs}
            agent = getattr(_config, "OPENCLAW_HTTP_AGENT_ID", None)
            if agent:
                # `/tools/invoke` evaluates the named agent's tool policy
                # (default: "main"). A dedicated agent id lets the owner deny
                # `browser` to the LLM agent while this guarded path keeps it.
                body["agentId"] = str(agent)
            if "timeoutMs" in targs:
                # the HTTP wait must outlast the page-load wait it carries
                timeout = max(float(timeout), targs["timeoutMs"] / 1000.0 + 15.0)
            r = self._sess().post(url, json=body,
                                  headers={"Authorization": f"Bearer {tok}"}, timeout=timeout)
        except Exception as exc:                                    # noqa: BLE001
            name = type(exc).__name__
            if "Timeout" in name:
                raise subprocess.TimeoutExpired(cmd=["POST", "/tools/invoke", p["verb"]],
                                                timeout=timeout) from None
            msg = str(exc).replace(tok, "REDACTED")[:200]
            if "Connection" in name or "refused" in msg.lower():
                return subprocess.CompletedProcess(
                    args, 1, "", f"gateway unreachable: ECONNREFUSED ({name}: {msg})")
            return subprocess.CompletedProcess(args, 1, "", f"http transport {name}: {msg}")
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code != 200 or not (isinstance(body, dict) and body.get("ok")):
            err = (body.get("error") if isinstance(body, dict) else None) or {}
            msg = (err.get("message") if isinstance(err, dict) else str(err)) or \
                f"HTTP {r.status_code}"
            return subprocess.CompletedProcess(args, 1, "", str(msg).replace(tok, "REDACTED")[:600])
        out, truncated = render(p["verb"], body.get("result") or {})
        cp = subprocess.CompletedProcess(args, 0, out, "")
        cp.http_truncated = truncated  # type: ignore[attr-defined]
        return cp
