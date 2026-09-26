"""Is the whole stack actually up? A thin wrapper over `system_health`.

    python -m scripts.stack_health                 # the probe table + receipts
    python -m scripts.stack_health --deep          # also asks the models a question
    python -m scripts.stack_health --json          # the receipt on stdout
    python -m scripts.stack_health --only telegram_agent,sim_session
    python -m scripts.stack_health --no-proc       # file-derived probes only

ONE TRUTH SOURCE (2026-09-27, review 2026-09-26 §4.3: "do not keep two truth
sources"). This file used to run its own six checks, and two of them lied:
`check_telegram` measured the bot token (`getMe`) and said READY a day after the
agent died; `check_sim` counted COMPLETED/STOPPED as ok with nothing running
(review F2). Every row now comes from `backend.services.system_health`, whose
verdicts are DERIVED from evidence the producer wrote (a stamp inside a receipt,
a pid answering with its module, an HTTP body field, a row-count delta) -- never
an mtime, never a config read.

Exit code is `health_probe`'s: 1 any DEAD, 2 any STALE, 3 every row UNKNOWN,
else 0. `--deep` adds two MEASUREMENT rows the probes do not make (a local
completion and a DeepSeek completion); a failed completion is a DEAD row and
enters the same exit code. `run()` keeps the shape `/api/control/sim/preflight`
and the desktop page read: {green, red, rows: {name: {...}}, at}.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402
from backend.services import system_health as SH            # noqa: E402

PING = "Reply with exactly: PONG"


def _t(fn) -> tuple[Any, float, Optional[str]]:
    t0 = time.time()
    try:
        return fn(), round(time.time() - t0, 2), None
    except Exception as exc:                                   # noqa: BLE001
        return None, round(time.time() - t0, 2), f"{type(exc).__name__}: {exc}"[:240]


# ── --deep: the two measurements the probes do not make ─────────────────────

def _local_completion(prompt: str) -> str:
    import urllib.request
    from backend.services import llama_server as LS
    url = getattr(LS, "BASE_URL", "http://127.0.0.1:8080") + "/v1/chat/completions"
    body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                       "max_tokens": 16, "temperature": 0}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as fh:        # noqa: S310 loopback
        d = json.load(fh)
    return d["choices"][0]["message"]["content"].strip()[:80]


def deep_local_model() -> dict:
    r, dt, err = _t(lambda: _local_completion(PING))
    ok = bool(r and "PONG" in str(r).upper())
    return {"name": "deep:local_model", "verdict": "ALIVE" if ok else "DEAD",
            "detail": f"completion {r!r} in {dt}s" if r else f"no completion: {err}",
            "proof": "POST :8080/v1/chat/completions"}


def deep_deepseek() -> dict:
    import urllib.request
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return {"name": "deep:deepseek", "verdict": "UNKNOWN",
                "detail": "DEEPSEEK_API_KEY absent", "proof": None}
    body = json.dumps({"model": "deepseek-chat", "max_tokens": 16, "temperature": 0,
                       "messages": [{"role": "user", "content": PING}]}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    r, dt, err = _t(lambda: json.load(urllib.request.urlopen(req, timeout=90)))  # noqa: S310
    if err:
        return {"name": "deep:deepseek", "verdict": "DEAD", "detail": err, "proof": None}
    msg = r["choices"][0]["message"]["content"].strip()[:60]
    # the model id the PROVIDER reports: since 2026-09-14 an unpriced
    # `deepseek-flash`, which makes every dollar cap a lower bound of $0
    model = (r.get("usage") or {}).get("model") or r.get("model")
    return {"name": "deep:deepseek", "verdict": "ALIVE" if "PONG" in msg.upper() else "DEAD",
            "detail": f"reply {msg!r} in {dt}s; provider model {model}", "proof": "chat/completions"}


# ── the wrapper ─────────────────────────────────────────────────────────────

def run(deep: bool = False, *, only: Optional[set] = None, allow_proc: bool = True,
        persist: bool = False) -> dict:
    """The system_health table, plus the `--deep` rows, in the preflight shape."""
    out = SH.run(ctx=SH.make_ctx(allow_proc=allow_proc), only=only, persist=persist)
    rows = list(out.get("rows") or [])
    if deep:
        rows += [deep_local_model(), deep_deepseek()]
    rc = SH.exit_code(rows)
    red = [r["name"] for r in rows if r.get("verdict") in ("DEAD", "STALE")]
    return {"receipt": "stack_health", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "deep": deep, "green": rc == 0, "red": red,
            "unknown": [r["name"] for r in rows if r.get("verdict") == "UNKNOWN"],
            "exit_code": rc, "counts": SH.counts(rows),
            "rows": {r["name"]: {"ok": r.get("verdict") == "ALIVE",
                                 **{k: v for k, v in r.items() if k != "name"}} for r in rows},
            "system_health_receipt": out.get("path"),
            "read_me_first": ("A thin wrapper over backend.services.system_health: every "
                              "verdict is derived from evidence the producer wrote. Exit "
                              "code 1 DEAD / 2 STALE / 3 all UNKNOWN / 0 otherwise.")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the stack's health: system_health probes")
    ap.add_argument("--deep", action="store_true",
                    help="also ask the local model and DeepSeek a question")
    ap.add_argument("--out", default=None, help="where the stack_health receipt goes")
    ap.add_argument("--json", action="store_true", help="print the receipt as JSON")
    ap.add_argument("--only", default="", help="comma-separated probe names")
    ap.add_argument("--no-proc", action="store_true",
                    help="skip probes that shell out or open a socket")
    ap.add_argument("--no-write", action="store_true", help="write no receipt")
    a = ap.parse_args(argv)
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    res = run(deep=a.deep, only=only, allow_proc=not a.no_proc, persist=not a.no_write)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    except Exception:                                                # noqa: BLE001
        pass
    if a.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        rows = sorted(res["rows"].items(),
                      key=lambda kv: (SH.VERDICT_ORDER.get(kv[1].get("verdict"), 9), kv[0]))
        print(f"stack health {res['at']}  counts {res['counts']}  rc {res['exit_code']}")
        for name, r in rows:
            print(f"{r.get('verdict', '?'):<8} {name[:34]:<34} {str(r.get('detail'))[:100]}")
        print()
        print("GREEN -- the stack can run a night" if res["green"]
              else f"NOT GREEN (rc {res['exit_code']}): {', '.join(res['red']) or 'all UNKNOWN'}")
    if not a.no_write:
        out = Path(a.out) if a.out else _cfg.OPTIMUS_LEDGER_DIR / f"stack_health_{date.today()}.json"
        out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        if not a.json:
            print(f"-> {out}")
    return int(res["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
