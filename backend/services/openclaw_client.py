"""The ONE way Aegis talks to OpenClaw's browser — one profile, named every time.

WHY A WRAPPER AND NOT BARE `openclaw browser ...`
=================================================
On 2026-09-22 `scripts/openclaw_login.py` shelled out as

    openclaw browser open ...
    openclaw browser snapshot
    openclaw browser fill ...

with no profile named, so every call depended on whatever `browser.defaultProfile`
happened to be at that moment. During the same afternoon that default moved four
times — `openclaw`, a short-lived `muratclaw` with an explicit CDP url, back to
`openclaw`, then `muratclaw` again — and a config edit or a `create-profile` from
anywhere would have moved it again silently. A browser profile is **logged-in
account access**; "whatever the default is" is not an acceptable way to choose
one.

So:

* every call names `--browser-profile` explicitly, from `AEGIS_OPENCLAW_PROFILE`
  (default `muratclaw`);
* `browser.defaultProfile` is ALSO set to the same name, as a second line of
  defence rather than the first;
* a mismatch or a missing profile **REFUSES** with
  `REFUSED_BROWSER_PROFILE_UNAVAILABLE`. It never falls back to another profile,
  because the fallback is precisely the failure — a Guest window, the generic
  `openclaw` profile, or somebody else's signed-in Chrome.

WHAT THE BROWSER MAY REACH
==========================
`DENIED_DOMAINS` is enforced HERE, before the call leaves Python, and is not a
suggestion to the model. Murat's one strict rule, 2026-09-22:

    "the only strickt guidance is that openclaw cant be used for payments or
     like that"

Brokerage, banking and payment domains are refused outright. Aegis reaches the
broker through `pc_broker`, where an order carries a `client_order_id`, a
mandate check and a receipt. A browser agent with a funded account open has none
of that, and no research question needs one.

`evaluate` (arbitrary JavaScript in the page) is refused for the same reason
OpenClaw's own security notes warn about it: a page the agent did not write
becomes a place to put instructions for the agent. Snapshot, navigate, click,
type, fill and download cover the research surface without that.

WHAT THIS MODULE DOES NOT DO
============================
It does not decide anything and it does not message anyone. OpenClaw produces
evidence; Aegis decides; `telegram_bridge` is the only thing that speaks to
Murat. The chain is

    OpenClaw -> Aegis -> Telegram          never        OpenClaw -> human

which is the structural fix for the WhatsApp incident, not a policy about it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

PROFILE_ENV = "AEGIS_OPENCLAW_PROFILE"
DEFAULT_PROFILE = "muratclaw"

#: Refused before the call leaves Python. Substring match on the URL, because a
#: path or a subdomain is enough to reach a login page.
DENIED_DOMAINS: tuple[str, ...] = (
    "alpaca.markets", "paypal.", "stripe.com", "coinbase.", "binance.",
    "interactivebrokers.", "schwab.com", "fidelity.com", "robinhood.",
    "revolut.", "wise.com", "wellsfargo.", "chase.com", "hsbc.",
    "bankofamerica.", "citibank.", "amazon.com/gp/buy", "checkout.",
)

#: Verbs Aegis is allowed to drive. `evaluate` is deliberately absent.
ALLOWED_VERBS: frozenset[str] = frozenset({
    "open", "navigate", "snapshot", "click", "type", "fill", "press", "hover",
    "tabs", "close", "focus", "download", "pdf", "console", "errors", "status",
    "profiles", "start", "stop",
})


class OpenClawRefused(RuntimeError):
    """The browser will not be driven. Never swallowed into a no-op."""


def profile() -> str:
    return (os.environ.get(PROFILE_ENV) or DEFAULT_PROFILE).strip()


def _bin() -> str:
    exe = os.environ.get("OPENCLAW_BIN") or shutil.which("openclaw") or "openclaw"
    return exe


#: The CLI colourises its output even when not attached to a terminal, and it
#: puts the escape sequence BETWEEN the label and the value:
#:
#:     'Connectivity probe:[39m [38;2;47;191;113mok[39m'
#:
#: so `"Connectivity probe: ok" in text` is False no matter what the gateway is
#: doing. `health()` matched exactly that literal, which means it had ALWAYS
#: returned "DO NOT BROWSE: gateway unreachable" and the night runner was never
#: once permitted to browse -- a gate that could not go green, which this repo
#: calls a broken gate rather than a strict one. Found 2026-09-24 only because
#: two agent quests demonstrably succeeded while health() called the gateway
#: unreachable.
_ANSI = re.compile(r"\[[0-9;]*m")


def _strip(text: str | None) -> str:
    return _ANSI.sub("", text or "")


def _run(args: list[str], *, timeout: float = 180.0) -> subprocess.CompletedProcess:
    r = subprocess.run([_bin(), *args], capture_output=True, text=True,
                       timeout=timeout, shell=(os.name == "nt"))
    # Strip centrally. Every parser downstream matches on plain text, and a
    # receipt full of escape codes is unreadable besides.
    return subprocess.CompletedProcess(r.args, r.returncode,
                                       _strip(r.stdout), _strip(r.stderr))


def check_url(url: str) -> None:
    low = (url or "").lower()
    for d in DENIED_DOMAINS:
        if d in low:
            raise OpenClawRefused(
                f"REFUSED_DOMAIN: {url!r} matches the denied pattern {d!r}. "
                f"Money-moving sites are not reachable from the research "
                f"browser, by design — the broker is reached through "
                f"`pc_broker`, where an order carries a client_order_id, a "
                f"mandate check and a receipt.")


def profiles() -> list[dict]:
    """Every configured browser profile, parsed from `openclaw browser profiles`."""
    r = _run(["browser", "profiles"])
    out, cur = [], None
    for line in (r.stdout or "").splitlines():
        # Only UNINDENTED lines name a profile. `openclaw browser profiles`
        # prints `muratclaw: stopped [default]` then indented continuations
        # (`  port: 18801, color: ...`), and stripping first made "port" and
        # "transport" look like profiles — which would have let
        # `assert_profile` pass on a name that does not exist.
        if line[:1].isspace() or not line.strip():
            if cur is not None and "port:" in line:
                p = re.search(r"port:\s*(\d+)", line)
                if p:
                    cur["port"] = int(p.group(1))
            continue
        m = re.match(r"^(\S+):\s*(\w+)(\s*\[(.+)\])?", line.strip())
        if m:
            cur = {"name": m.group(1), "state": m.group(2),
                   "tag": (m.group(4) or "").strip()}
            out.append(cur)
    return out


def assert_profile(strict: bool = True) -> dict:
    """The profile Aegis is pinned to must EXIST. No fallback, ever."""
    want = profile()
    found = next((p for p in profiles() if p["name"] == want), None)
    if found is None:
        msg = (f"REFUSED_BROWSER_PROFILE_UNAVAILABLE: no OpenClaw browser "
               f"profile named {want!r}. Create it with "
               f"`openclaw browser create-profile --name {want} --driver openclaw`. "
               f"Aegis does NOT fall back to another profile: a fallback is how "
               f"a run ends up in a Guest window or somebody else's signed-in "
               f"Chrome.")
        if strict:
            raise OpenClawRefused(msg)
        return {"ok": False, "profile": want, "detail": msg}
    return {"ok": True, "profile": want, **found}


def browser(verb: str, *args: str, url: str | None = None,
            timeout: float = 180.0) -> dict:
    """Drive the browser. The profile is named on EVERY call.

    `verb` must be in `ALLOWED_VERBS`; `evaluate` is not, so a page cannot be
    handed arbitrary JavaScript from here.
    """
    if verb not in ALLOWED_VERBS:
        raise OpenClawRefused(
            f"REFUSED_VERB: {verb!r} is not in the allowed set. "
            f"`evaluate` in particular is refused: running arbitrary JavaScript "
            f"in a page the agent did not write turns that page into a place to "
            f"put instructions for the agent.")
    if url:
        check_url(url)
    for a in args:
        if isinstance(a, str) and a.lower().startswith(("http://", "https://")):
            check_url(a)

    assert_profile()
    argv = ["browser", "--browser-profile", profile(), verb, *args]
    if url:
        argv.append(url)
    r = _run(argv, timeout=timeout)
    return {"verb": verb, "profile": profile(), "rc": r.returncode,
            "stdout": (r.stdout or "").strip(),
            "stderr": (r.stderr or "").strip()[:600]}


def agent(message_file: str, *, model: str = "deepseek/deepseek-v4-pro",
          timeout: float = 600.0, purpose: str = "openclaw:agent",
          session_id: str | None = None,
          telemetry_path: Any = None) -> dict:
    """One agent turn. `--deliver` is NEVER passed: OpenClaw messages nobody.

    The reply comes back to Aegis as text. Whether Murat hears about it is
    Aegis's decision and `telegram_bridge`'s job.

    EVERY CALL IS A TELEMETRY ROW (2026-09-25, chunk C0)
    ----------------------------------------------------
    Until today an OpenClaw turn spent DeepSeek money and left no row in
    `llm_calls_<month>.jsonl`, so every spend total and every dollar cap in the
    repo was blind to it. `--json` returns OpenClaw's own envelope, which
    carries the token usage (`result.meta.agentMeta.usage`) and the model that
    actually answered; the row is priced from those tokens with the house table
    (`LLM_PRICE_PER_MTOK`), and OpenClaw's own cost estimate travels in `meta`
    beside it so the two can be compared. Measured on the first call: 30,262
    input + 6,784 cached + 2,034 output tokens for a 2.7k-char prompt -- the
    agent's system prompt and tool schemas are ~90% of every call.

    AN EMPTY REPLY IS A FAILURE WITH A ROW, NOT A SILENCE. rc 0 with no text is
    written as `meta.status = "EMPTY_LOG"` and `accrual_canary` turns it red --
    the 2026-09-24 `q2_power_bottleneck` quest returned exactly that and nothing
    noticed.

    A FRESH SESSION PER CALL. Without `--session-id` every turn lands in the
    main session and inherits the previous turns' context: ticker A's evidence
    sits in ticker B's prompt, and the prompt grows with every call.
    """
    import uuid as _uuid

    sid = session_id or f"aegis-{re.sub(r'[^A-Za-z0-9_-]', '-', purpose)}-{_uuid.uuid4().hex[:12]}"
    t0 = time.time()
    try:
        r = _run(["agent", "--message-file", message_file, "--model", model,
                  "--json", "--session-id", sid], timeout=timeout)
        rc, out, err = r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc, out, err = None, "", f"TimeoutExpired: {exc}"[:600]
    latency_ms = (time.time() - t0) * 1000.0
    env = parse_envelope(out)
    reply = env["reply"] if env["parsed"] else out.strip()
    if rc is None:
        status = "TIMEOUT"
    elif rc != 0:
        status = "RC_NONZERO"
    elif not reply.strip():
        status = "EMPTY_LOG"
    elif not env["parsed"]:
        status = "UNPARSEABLE_ENVELOPE"
    else:
        status = "OK"
    call_id = _record_telemetry(
        model=env.get("response_model") or model, purpose=purpose,
        message_file=message_file, usage=env.get("usage") or {},
        latency_ms=latency_ms, status=status, rc=rc, session_id=sid,
        openclaw_cost_usd=env.get("openclaw_cost_usd"),
        run_id=env.get("run_id"), error=(err[:300] if status != "OK" else None),
        path=telemetry_path)
    return {"rc": rc, "reply": reply, "stderr": err.strip()[:600],
            "model": model, "status": status, "session_id": sid,
            "usage": env.get("usage") or {}, "call_id": call_id,
            "openclaw_cost_usd": env.get("openclaw_cost_usd"),
            "latency_s": round(latency_ms / 1000.0, 2)}


def parse_envelope(stdout: str) -> dict:
    """OpenClaw's `--json` envelope -> reply text, usage, cost, model.

    Tolerant of a log line before the JSON (the CLI prints banners on some
    paths). `parsed` is False when no envelope was found, and the caller then
    treats raw stdout as the reply -- the pre-`--json` behaviour.
    """
    out = {"parsed": False, "reply": "", "usage": {}, "openclaw_cost_usd": None,
           "response_model": None, "run_id": None}
    txt = stdout or ""
    if "{" not in txt:
        return out
    try:
        d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except ValueError:
        return out
    if not isinstance(d, dict) or "result" not in d:
        return out
    res = d.get("result") or {}
    pay = res.get("payloads") or []
    out["reply"] = "\n".join(str(p.get("text") or "") for p in pay
                             if isinstance(p, dict)).strip()
    meta = (res.get("meta") or {}).get("agentMeta") or {}
    u = meta.get("usage") or {}
    out["usage"] = {"input": int(u.get("input") or 0),
                    "output": int(u.get("output") or 0),
                    "cache_read": int(u.get("cacheRead") or 0),
                    "reasoning": int(u.get("reasoningTokens") or 0)}
    out["openclaw_cost_usd"] = meta.get("costUsd")
    rec = ((meta.get("terminalReceipt") or {}).get("effective") or {})
    out["response_model"] = rec.get("responseModel") or meta.get("model")
    out["run_id"] = d.get("runId")
    out["parsed"] = True
    return out


def _record_telemetry(*, model: str, purpose: str, message_file: str,
                      usage: dict, latency_ms: float, status: str, rc: Any,
                      session_id: str, openclaw_cost_usd: Any, run_id: Any,
                      error: str | None, path: Any) -> str | None:
    """One row in the SAME ledger `llm_telemetry` writes. Never raises."""
    try:
        from backend.services import llm_telemetry as LT
        bare = str(model).split("/", 1)[-1]
        try:
            prompt = open(message_file, encoding="utf-8").read()
        except OSError:
            prompt = message_file
        priced = bool(usage.get("input") or usage.get("output"))
        rec = LT.build_call(
            provider="deepseek", model=bare, purpose=purpose, agent="openclaw",
            prompt=prompt, tokens_in=int(usage.get("input") or 0),
            tokens_out=int(usage.get("output") or 0),
            cached_tokens=int(usage.get("cache_read") or 0),
            latency_ms=latency_ms, schema_valid=(status == "OK"), error=error,
            meta={"via": "openclaw", "status": status, "rc": rc,
                  "session_id": session_id, "run_id": run_id,
                  "openclaw_cost_usd": openclaw_cost_usd,
                  "reasoning_tokens": usage.get("reasoning"),
                  "cost_status": ("PRICED_FROM_USAGE" if priced
                                  else "UNPRICED_OPENCLAW")})
        if not priced:
            # No usage came back: the spend is UNKNOWN, not zero. A None cost
            # makes every total that includes it a declared lower bound.
            rec.cost_usd = None
        LT.append([rec], path=path)
        return rec.call_id
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("openclaw telemetry row not written (%s: %s) -- this "
                       "call's spend is MISSING from the ledger",
                       type(exc).__name__, exc)
        return None


# ───────────────────────────────── health ───────────────────────────────────

@dataclass
class Health:
    ok: bool
    rows: dict

    def as_dict(self) -> dict:
        return {"receipt": "openclaw_health", "ok": self.ok,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **self.rows}


def health(*, probe_web: bool = False) -> Health:
    """The gate the night runner reads BEFORE it browses.

    A red here means do not browse — it does not mean browse with something
    else. `profile_pinned` is the row that matters: everything downstream
    assumes the logged-in session belongs to the account Murat intended.
    """
    rows: dict[str, Any] = {"profile_wanted": profile()}
    try:
        g = _run(["gateway", "status"], timeout=90)
        txt = (g.stdout or "") + (g.stderr or "")
        rows["gateway_probe_ok"] = "Connectivity probe: ok" in txt
        rows["gateway_running"] = "Runtime: running" in txt
    except (OSError, subprocess.SubprocessError) as exc:
        rows["gateway_probe_ok"] = False
        rows["gateway_error"] = str(exc)[:200]

    p = assert_profile(strict=False)
    rows["profile_pinned"] = bool(p.get("ok"))
    rows["profile_detail"] = p.get("detail") or p.get("state")
    rows["profile_is_default_too"] = _default_profile_matches()

    rows["denied_domains"] = len(DENIED_DOMAINS)
    rows["evaluate_allowed"] = "evaluate" in ALLOWED_VERBS   # must be False
    rows["messaging_channels"] = _channel_count()

    if probe_web:
        rows["web"] = _probe_web()

    ok = bool(rows.get("gateway_probe_ok") and rows.get("profile_pinned")
              and not rows["evaluate_allowed"]
              and rows.get("messaging_channels") == 0)
    rows["verdict"] = (
        "READY" if ok else
        "DO NOT BROWSE: " + ", ".join(
            k for k, v in (("gateway unreachable", not rows.get("gateway_probe_ok")),
                           (f"profile {profile()!r} unavailable", not rows.get("profile_pinned")),
                           ("evaluate is allowed", rows["evaluate_allowed"]),
                           ("a messaging channel is configured",
                            rows.get("messaging_channels", 0) != 0))
            if v))
    return Health(ok, rows)


def _default_profile_matches() -> bool | None:
    r = _run(["config", "get", "browser.defaultProfile"], timeout=60)
    txt = (r.stdout or "").strip().strip('"')
    return (txt == profile()) if txt else None


def _channel_count() -> int:
    """OpenClaw must have NO chat channel. Aegis owns the messaging."""
    r = _run(["channels", "list"], timeout=90)
    txt = (r.stdout or "") + (r.stderr or "")
    if "no configured chat channels" in txt.lower():
        return 0
    return len([l for l in txt.splitlines() if l.strip().startswith("- ")])


def _probe_web() -> dict:
    out = {}
    for name, url in (("sec", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=10"),
                      ("reddit", "https://www.reddit.com/r/stocks/")):
        try:
            r = browser("open", url=url, timeout=120)
            out[name] = "opened" if r["rc"] == 0 else f"rc {r['rc']}"
        except OpenClawRefused as exc:
            out[name] = f"refused: {str(exc)[:120]}"
    return out
