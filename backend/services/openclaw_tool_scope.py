"""What an OpenClaw LLM turn is ALLOWED to do, and what it actually did.

WHY (2026-09-29, review F1 of the reader pool)
==============================================
`browser_policy` binds Python callers only. On 2026-09-28 14:08-14:11 UTC a
thesis-card quest -- an LLM turn of the `main` agent, whose tool profile was
`coding` with only `browser` denied -- used `exec` to run `openclaw browser
open` against the dedicated signed-in Chrome (one host not on the allowlist)
and `openclaw browser evaluate --fn <its own JavaScript>`, outside every guard.
The owner's rules (read-only; no payments; no messages or e-mails; no posting;
only allowlisted hosts; only through the guarded path) were being kept by the
model's good behaviour, not by code.

The fix is in `~/.openclaw/openclaw.json` (OpenClaw 2026.9.5 keys, see
`docs/gateway/config-tools/tool-policy.md` in the install):

* `tools.profile = "minimal"` and a global `tools.deny` of every shell, file
  write, messaging, UI and automation tool;
* `agents.entries.main.tools = {profile: "minimal", alsoAllow: [web_search,
  web_fetch, x_search, memory_search, memory_get, bundle-mcp], deny: [... ,
  "browser"]}` -- every LLM turn Aegis runs (`openclaw_client.agent`) and the
  Telegram / heartbeat turns use `main`;
* `aegis-browser` keeps `minimal + browser`: the guarded transport
  (`openclaw_http`, `POST /tools/invoke`), never an LLM turn.

This module makes both halves checkable, offline and without the gateway:

* `config_problems(cfg)` -- PURE. Resolves each agent's effective tool set
  from the profile / group / allow / deny layers and names every LLM-capable
  agent that can reach a FORBIDDEN tool (shell, file write, messaging or
  publishing, browser / UI, automation). A layer it cannot resolve
  (`byProvider`, `toolsBySender`, `elevated`, an unknown profile) is a problem,
  never a pass: a guard that cannot read its input refuses.
* `tool_calls(home, since)` -- every tool call recorded in each agent's
  transcript store (`agents/<id>/agent/openclaw-agent.sqlite`, opened
  read-only) since `since`, and `violations()` -- the ones outside the read
  set. A `browser` call in ANY transcript is a violation: the guarded path
  (`/tools/invoke`) is not an LLM turn and leaves no transcript.

`scripts/openclaw_tool_audit.py` is the CLI; `system_health` runs
`p_openclaw_tool_scope` in every health pass (the daily pass's `health` step),
so a widened config or an LLM that reached a shell turns a row red.

Never prints a secret: config values are read for tool policy only, and a
tool call's arguments are reduced to a short, redacted head.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

#: OpenClaw 2026.9.5 tool groups (docs/gateway/config-tools/tool-policy.md).
GROUPS: dict[str, frozenset[str]] = {
    "group:runtime": frozenset({"exec", "process", "code_execution", "bash"}),
    "group:fs": frozenset({"read", "write", "edit", "apply_patch"}),
    "group:sessions": frozenset({"sessions", "sessions_list", "sessions_history",
                                 "sessions_search", "conversations_list", "conversations_send",
                                 "conversations_turn", "sessions_send", "sessions_spawn",
                                 "sessions_yield", "subagents", "session_status",
                                 "suggest_task", "dismiss_task"}),
    "group:memory": frozenset({"memory_search", "memory_get"}),
    "group:web": frozenset({"web_search", "x_search", "web_fetch"}),
    "group:ui": frozenset({"browser", "screen", "dashboard", "terminal", "portal", "canvas",
                           "show_widget"}),
    "group:automation": frozenset({"heartbeat_respond", "automations", "cron", "gateway",
                                   "plugins", "openclaw"}),
    "group:messaging": frozenset({"message"}),
    "group:nodes": frozenset({"nodes", "computer"}),
    "group:agents": frozenset({"agents_list", "get_goal", "create_goal", "update_goal",
                               "progress_card", "ask_user", "skill_workshop"}),
    "group:media": frozenset({"view_image", "image_generate", "music_generate",
                              "video_generate", "tts", "pdf"}),
}
#: Every tool id this module knows, plus the catalogue entries the 09-29 review
#: listed that no group names.
KNOWN_TOOLS: frozenset[str] = frozenset().union(*GROUPS.values()) | frozenset(
    {"bundle-mcp", "secrets", "github_publish", "apply_patch", "ls"})

#: Profiles (same doc). `full` and an UNSET profile leave core tools unfiltered.
PROFILES: dict[str, frozenset[str] | None] = {
    "minimal": frozenset({"session_status", "gateway"}),
    "coding": (GROUPS["group:fs"] | GROUPS["group:runtime"] | GROUPS["group:web"]
               | GROUPS["group:sessions"] | GROUPS["group:memory"]
               | frozenset({"cron", "gateway", "get_goal", "create_goal", "update_goal",
                            "progress_card", "ask_user", "skill_workshop", "view_image",
                            "image_generate", "music_generate", "video_generate",
                            "bundle-mcp"})),
    "messaging": (GROUPS["group:messaging"]
                  | frozenset({"sessions", "sessions_list", "sessions_history",
                               "sessions_search", "conversations_list", "conversations_send",
                               "conversations_turn", "sessions_send", "sessions_spawn",
                               "sessions_yield", "subagents", "session_status", "gateway",
                               "ask_user", "bundle-mcp"})),
    "full": None,
}

#: What an LLM turn may NEVER hold: shell, file write, messaging / publishing,
#: the browser and every other UI surface, automation.
FORBIDDEN: frozenset[str] = frozenset(
    GROUPS["group:runtime"] | {"write", "edit", "apply_patch"}
    | GROUPS["group:messaging"]
    | {"conversations_send", "conversations_turn", "sessions_send", "sessions_spawn",
       "subagents", "github_publish", "secrets"}
    | GROUPS["group:ui"] | GROUPS["group:nodes"]
    | {"cron", "automations", "gateway", "plugins", "openclaw"})

#: Tool calls a transcript may show without a violation (the read set). MCP
#: tools arrive as `<server>__<tool>`; only the two configured read servers.
READ_TOOLS: frozenset[str] = frozenset(
    {"web_search", "web_fetch", "x_search", "memory_search", "memory_get",
     "session_status", "heartbeat_respond"})
READ_MCP_PREFIXES: tuple[str, ...] = ("optimus__", "aegis_api__")

#: Agents that are TRANSPORT only (no LLM turn is ever run on them). They may
#: hold `browser` and nothing else beyond `minimal`; any transcript under one is
#: itself a violation.
TRANSPORT_AGENTS: dict[str, frozenset[str]] = {"aegis-browser": frozenset({"browser"})}

UNRESOLVABLE_TOOL_KEYS = ("byProvider", "toolsBySender", "elevated", "sandbox", "codeMode")


def default_home() -> Path:
    try:
        from backend import config as _c
        return Path(getattr(_c, "OPENCLAW_CONFIG_PATH")).parent
    except Exception:                                               # noqa: BLE001
        return Path.home() / ".openclaw"


def load_config(home: Path | None = None) -> dict | None:
    p = Path(home or default_home()) / "openclaw.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ─────────────────────────────── policy resolution (pure) ───────────────────

def _expand(entries: Iterable[str] | None) -> tuple[set[str], bool]:
    """Names + groups -> tool ids. Returns (ids, wildcard_seen)."""
    out: set[str] = set()
    wild = False
    for e in entries or []:
        e = str(e).strip().lower()
        if e in GROUPS:
            out |= GROUPS[e]
        elif e == "group:openclaw":
            out |= (frozenset().union(*GROUPS.values())
                    - {"read", "write", "edit", "apply_patch", "exec", "process", "canvas"})
        elif e == "group:plugins":
            out.add("bundle-mcp")
        elif "*" in e:
            wild = True
            rx = re.compile("^" + re.escape(e).replace(r"\*", ".*") + "$")
            out |= {t for t in KNOWN_TOOLS if rx.match(t)}
        else:
            out.add("exec" if e == "bash" else e)
    return out, wild


def effective_tools(cfg: dict, agent_id: str) -> dict:
    """The tool ids an agent's turns can call, from `tools` and
    `agents.entries.<id>.tools`. `{"tools": set | None, "problems": [...]}`;
    `tools = None` means UNFILTERED (full / unset profile / `*` allow)."""
    g = dict((cfg.get("tools") or {}))
    a = dict(((cfg.get("agents") or {}).get("entries") or {}).get(agent_id, {}).get("tools")
             or {})
    problems: list[str] = []
    for layer, d in (("tools", g), (f"agents.entries.{agent_id}.tools", a)):
        for k in UNRESOLVABLE_TOOL_KEYS:
            if d.get(k) not in (None, {}, [], False):
                if k == "elevated" and not (d.get(k) or {}).get("enabled"):
                    continue
                problems.append(f"{layer}.{k} is set; this audit cannot resolve it")
        if "allow" in d and "alsoAllow" in d:
            problems.append(f"{layer}: allow and alsoAllow together (config validation rejects it)")
    profile = a.get("profile", g.get("profile"))
    if profile is None or profile == "full":
        base: set[str] | None = None
    elif profile in PROFILES:
        base = set(PROFILES[profile] or ())
    else:
        problems.append(f"unknown tool profile {profile!r}")
        base = None
    for d in (g, a):
        allow, wild_a = _expand(d.get("allow"))
        also, wild_b = _expand(d.get("alsoAllow"))
        if wild_a or wild_b:
            if any(str(x).strip() == "*" for x in list(d.get("allow") or [])
                   + list(d.get("alsoAllow") or [])):
                base = None
        if base is not None:
            # an audit over-estimates: `allow` is read as ADDING to the profile
            # (were it a narrowing, the true set is smaller, never larger)
            base |= allow | also
    deny: set[str] = set()
    for d in (g, a):
        dd, _ = _expand(d.get("deny"))
        deny |= dd
    if base is None:
        # unfiltered: everything known except what is denied
        tools = set(KNOWN_TOOLS) - deny
        unfiltered = True
    else:
        tools = base - deny
        unfiltered = False
    return {"tools": tools, "unfiltered": unfiltered, "deny": deny, "profile": profile,
            "problems": problems}


def agent_ids(cfg: dict) -> list[str]:
    ids = set(((cfg.get("agents") or {}).get("entries") or {}).keys())
    ids.add("main")                          # always present, default target of `agent`
    for b in cfg.get("bindings") or []:
        if isinstance(b, dict) and b.get("agentId"):
            ids.add(str(b["agentId"]))
    for k in ("heartbeat", "systemAgent"):
        v = (((cfg.get("agents") or {}).get("defaults") or {}).get(k) or {})
        if isinstance(v, dict) and v.get("agentId"):
            ids.add(str(v["agentId"]))
    if (cfg.get("talk") or {}).get("agentId"):
        ids.add(str(cfg["talk"]["agentId"]))
    return sorted(ids)


def config_problems(cfg: dict | None, *, transport: dict[str, frozenset[str]] | None = None
                    ) -> list[str]:
    """PURE. Every reason the config lets an LLM turn act. [] = safe."""
    if not isinstance(cfg, dict):
        return ["CANNOT DETERMINE: no readable openclaw.json"]
    transport = TRANSPORT_AGENTS if transport is None else transport
    out: list[str] = []
    bound = {str(b.get("agentId")) for b in cfg.get("bindings") or [] if isinstance(b, dict)}
    for aid in agent_ids(cfg):
        eff = effective_tools(cfg, aid)
        out += [f"{aid}: {p}" for p in eff["problems"]]
        if aid in transport:
            if aid in bound:
                out.append(f"{aid}: a TRANSPORT agent is bound to a channel (it would run LLM turns)")
            extra = (eff["tools"] - PROFILES["minimal"] - transport[aid]) & FORBIDDEN
            if eff["unfiltered"]:
                out.append(f"{aid}: transport agent has an unfiltered tool profile")
            elif extra:
                out.append(f"{aid}: transport agent can reach {sorted(extra)}")
            continue
        if eff["unfiltered"]:
            out.append(f"{aid}: unfiltered tool profile ({eff['profile'] or 'unset'}); "
                       f"forbidden not denied: {sorted(FORBIDDEN - eff['deny'])}")
            continue
        bad = eff["tools"] & FORBIDDEN
        if bad:
            out.append(f"{aid}: LLM turns can reach {sorted(bad)}")
    return out


# ─────────────────────────────── what the agents actually did ────────────────

_SECRETISH = re.compile(r"[A-Za-z0-9_\-]{24,}")


def _redact_head(args: Any, n: int = 80) -> str:
    try:
        s = json.dumps(args, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = str(args)
    s = re.sub(r"(?i)(token|key|secret|password|authorization|bearer)[\"'=:\s]+[^\s\"',}]+",
               r"\1=REDACTED", s)
    return _SECRETISH.sub("REDACTED", s)[:n]


def transcript_stores(home: Path) -> list[tuple[str, Path]]:
    root = Path(home) / "agents"
    if not root.exists():
        return []
    return [(p.parent.parent.name, p)
            for p in sorted(root.glob("*/agent/openclaw-agent.sqlite"))]


def tool_calls(home: Path, since: datetime) -> tuple[list[dict], list[str]]:
    """Every tool call in every agent's transcript since `since` (UTC).
    Returns (calls, errors). Opens each store READ-ONLY."""
    since_ms = int(since.timestamp() * 1000)
    calls: list[dict] = []
    errors: list[str] = []
    for aid, db in transcript_stores(home):
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
        except sqlite3.Error as exc:
            errors.append(f"{aid}: {type(exc).__name__}: {exc}"[:200])
            continue
        try:
            keys = dict(con.execute("select current_session_id, session_key from session_nodes"
                                    ).fetchall())
            rows = con.execute("select session_id, event_json, created_at from transcript_events "
                               "where created_at >= ? order by created_at", (since_ms,)).fetchall()
        except sqlite3.Error as exc:
            errors.append(f"{aid}: {type(exc).__name__}: {exc}"[:200])
            rows, keys = [], {}
        finally:
            con.close()
        for sid, ej, ca in rows:
            try:
                e = json.loads(ej)
            except ValueError:
                continue
            m = e.get("message")
            if not isinstance(m, dict) or m.get("role") != "assistant":
                continue
            for it in m.get("content") or []:
                if isinstance(it, dict) and it.get("type") == "toolCall":
                    calls.append({"agent": aid, "session": keys.get(sid, sid),
                                  "utc": datetime.fromtimestamp(ca / 1000, timezone.utc)
                                  .isoformat(timespec="seconds"),
                                  "tool": str(it.get("name") or ""),
                                  "args_head": _redact_head(it.get("arguments"))})
    return calls, errors


def is_read_call(call: dict, *, transport: dict[str, frozenset[str]] | None = None) -> bool:
    transport = TRANSPORT_AGENTS if transport is None else transport
    if call.get("agent") in transport:
        return False                      # a transport agent never runs a turn
    t = call.get("tool") or ""
    return t in READ_TOOLS or t.startswith(READ_MCP_PREFIXES)


def violations(calls: list[dict]) -> list[dict]:
    return [c for c in calls if not is_read_call(c)]


def audit(home: Path | None = None, *, now: datetime | None = None,
          hours: float = 24.0) -> dict:
    home = Path(home or default_home())
    now = now or datetime.now(timezone.utc)
    cfg = load_config(home)
    probs = config_problems(cfg)
    calls, errors = tool_calls(home, now - timedelta(hours=hours)) if cfg is not None \
        else ([], ["no config"])
    bad = violations(calls)
    by_tool: dict[str, int] = {}
    for c in calls:
        by_tool[c["tool"]] = by_tool.get(c["tool"], 0) + 1
    return {"receipt": "openclaw_tool_audit", "generated_utc": now.isoformat(timespec="seconds"),
            "home": str(home), "config_found": cfg is not None, "window_h": hours,
            "config_problems": probs, "n_calls": len(calls), "calls_by_tool": by_tool,
            "violations": bad, "n_violations": len(bad), "store_errors": errors,
            "agents_audited": agent_ids(cfg) if cfg else [],
            "verdict": ("CANNOT_DETERMINE" if cfg is None else
                        "UNSAFE" if (probs or bad) else "OK")}


# ─────────────────────────────── the health probe ────────────────────────────

def p_openclaw_tool_scope(ctx: Any):
    """`system_health` probe. UNKNOWN without a config; DEAD when the config
    lets an LLM turn reach a forbidden tool or a transcript shows a call
    outside the read set in the last 24 h; ALIVE otherwise."""
    from backend.services import system_health as SH
    home = ctx.path("openclaw_home", default_home())
    if load_config(home) is None:
        return SH._unknown(f"no readable openclaw.json under {home}")
    r = audit(home, now=ctx.now, hours=24.0)
    proof = ("openclaw.json tool policy resolved offline + agents/*/agent/"
             "openclaw-agent.sqlite transcript_events (read-only), last 24 h")
    if r["verdict"] == "UNSAFE":
        heads = [f"{v['utc']} {v['agent']} {v['tool']}" for v in r["violations"][:5]]
        return SH.ProbeResult("DEAD", SH._iso(ctx.now), 0.0,
                              f"UNSAFE: {len(r['config_problems'])} config problem(s) "
                              f"{r['config_problems'][:3]}; {r['n_violations']} tool call(s) "
                              f"outside the read set in 24 h {heads}",
                              delta=r["n_violations"] + len(r["config_problems"]), proof=proof)
    return SH.ProbeResult("ALIVE", SH._iso(ctx.now), 0.0,
                          f"LLM turns read-only; {r['n_calls']} tool call(s) in 24 h, 0 outside "
                          f"the read set" + (f"; store errors {r['store_errors']}"
                                             if r["store_errors"] else ""),
                          delta=0, proof=proof)
