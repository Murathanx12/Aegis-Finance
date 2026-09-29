"""Audit what OpenClaw LLM turns may do and what they did (2026-09-29).

    python -m scripts.openclaw_tool_audit                 # last 24 h, writes a receipt
    python -m scripts.openclaw_tool_audit --hours 72
    python -m scripts.openclaw_tool_audit --since-utc 2026-09-29T03:10:00Z
    python -m scripts.openclaw_tool_audit --no-receipt

Reads `~/.openclaw/openclaw.json` (tool policy only; no value of a key or
token is printed) and every agent's transcript store read-only, then prints:

* the config problems -- any LLM-capable agent that can reach a shell, a file
  write, a messaging / publishing tool, the browser or automation;
* every tool call in the window outside the read set (web_search, web_fetch,
  x_search, memory_*, session_status, the two read-only MCP servers).

Exit 0 OK, 1 UNSAFE, 2 CANNOT_DETERMINE. The logic lives in
`backend/services/openclaw_tool_scope.py`; `system_health` runs the same audit
as the `openclaw_tool_scope` probe in every health pass (the daily pass's
`health` step), which is this check's scheduled caller. Receipts go to
`backend/data/optimus/openclaw/tool_audit_<run id>.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                   # noqa: E402
from backend.services import openclaw_tool_scope as OTS               # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--since-utc", default=None, help="audit calls from this instant instead")
    ap.add_argument("--home", default=None, help="OpenClaw state dir (default ~/.openclaw)")
    ap.add_argument("--no-receipt", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    hours = a.hours
    if a.since_utc:
        since = datetime.fromisoformat(a.since_utc.replace("Z", "+00:00"))
        hours = max(0.0, (now - since).total_seconds() / 3600.0)
    r = OTS.audit(Path(a.home) if a.home else None, now=now, hours=hours)
    print(f"openclaw tool audit {r['generated_utc']}  window {hours:.2f} h  "
          f"verdict {r['verdict']}")
    print(f"  agents audited: {r['agents_audited']}")
    print(f"  config problems: {len(r['config_problems'])}")
    for p in r["config_problems"]:
        print(f"    - {p}")
    print(f"  tool calls in window: {r['n_calls']}  by tool: {r['calls_by_tool']}")
    print(f"  outside the guarded / read set: {r['n_violations']}")
    for v in r["violations"][:40]:
        print(f"    {v['utc']}  {v['agent']:<14} {v['tool']:<12} {v['session'][:60]}  "
              f"{v['args_head']}")
    if r["n_violations"] > 40:
        print(f"    ... {r['n_violations'] - 40} more in the receipt")
    if r["store_errors"]:
        print(f"  store errors: {r['store_errors']}")
    if not a.no_receipt:
        out = Path(_cfg.OPTIMUS_LEDGER_DIR) / "openclaw"
        out.mkdir(parents=True, exist_ok=True)
        run_id = now.strftime("%Y%m%dT%H%M%SZ")
        p = out / f"tool_audit_{run_id}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
        tmp.replace(p)
        print(f"  receipt: {p}")
    return {"OK": 0, "UNSAFE": 1}.get(r["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
