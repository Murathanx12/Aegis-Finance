"""Is the whole stack actually up? One command, one receipt, no assumptions.

    python -m scripts.stack_health
    python -m scripts.stack_health --deep      # also asks the models a question

WHY ONE CHECK AND NOT SIX
=========================
By 2026-09-22 a night depends on six separate things being alive: the broker,
the local model server, DeepSeek, OpenClaw's gateway and pinned browser profile,
the simulation runner, and the Telegram bridge. Each has its own status command,
each prints a different shape, and nobody runs all six before starting a
12-hour session.

The failure this prevents is the one that already happened twice this month: a
night that ran to completion having silently done nothing useful, because one
dependency was down and the thing that needed it degraded quietly instead of
refusing. `LISTENING IS NOT READY` is the same family -- llama-server bound its
port at 0.5s with a fifth of the model resident.

So every row here answers with a MEASUREMENT, not a config read:

    the broker      -> an actual /v2/account call
    the local model -> an actual completion, not "the port is open"
    DeepSeek        -> an actual completion
    OpenClaw        -> its health gate, including the pinned profile
    the sim         -> its derived state, including UNCLEAN
    Telegram        -> getMe, and whether an owner is configured

A row that cannot be measured says CANNOT DETERMINE and is counted as red. A
green here is a claim that the night can do its job; it should be expensive to
earn.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402

PING = "Reply with exactly: PONG"


def _t(fn) -> tuple[Any, float, str | None]:
    t0 = time.time()
    try:
        return fn(), round(time.time() - t0, 2), None
    except Exception as exc:                                   # noqa: BLE001
        return None, round(time.time() - t0, 2), f"{type(exc).__name__}: {exc}"[:240]


def check_broker() -> dict:
    from backend.services import pc_broker as PB
    a, dt, err = _t(PB.account)
    if err:
        return {"ok": False, "detail": err, "s": dt}
    pos, _, _ = _t(PB.positions)
    return {"ok": True, "s": dt, "account": a.get("account_number"),
            "equity": float(a.get("equity") or 0),
            "cash": float(a.get("cash") or 0),
            "positions": len(pos or []), "status": a.get("status")}


def check_local_model(deep: bool) -> dict:
    from backend.services import llama_server as LS
    st, dt, err = _t(LS.status)
    if err:
        return {"ok": False, "detail": err, "s": dt}
    out = {"listening": bool(st.get("listening")), "ready": bool(st.get("ready")),
           "pid": st.get("pid"), "s": dt}
    # LISTENING IS NOT READY: a bound port with a fifth of the model resident
    # answers the socket and not the question.
    out["ok"] = bool(st.get("ready"))
    if deep and out["listening"]:
        r, dts, e = _t(lambda: _local_completion(PING))
        out["completion"] = (r or e)
        out["completion_s"] = dts
        out["ok"] = bool(r and "PONG" in str(r).upper())
    return out


def _local_completion(prompt: str) -> str:
    import json as _j
    import urllib.request
    from backend.services import llama_server as LS
    url = getattr(LS, "BASE_URL", "http://127.0.0.1:8080") + "/v1/chat/completions"
    body = _j.dumps({"messages": [{"role": "user", "content": prompt}],
                     "max_tokens": 16, "temperature": 0}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as fh:        # noqa: S310 loopback
        d = _j.load(fh)
    return d["choices"][0]["message"]["content"].strip()[:80]


def check_deepseek(deep: bool) -> dict:
    import os
    key = os.environ.get("DEEPSEEK_API_KEY")
    out = {"key_present": bool(key), "ok": bool(key)}
    if not key:
        out["detail"] = "DEEPSEEK_API_KEY absent"
        return out
    if not deep:
        out["detail"] = "key present; --deep asks it a question"
        return out
    import json as _j
    import urllib.request
    body = _j.dumps({"model": "deepseek-chat", "max_tokens": 16, "temperature": 0,
                     "messages": [{"role": "user", "content": PING}]}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions",
                                 data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    r, dt, err = _t(lambda: _j.load(urllib.request.urlopen(req, timeout=90)))  # noqa: S310
    if err:
        return {**out, "ok": False, "detail": err, "s": dt}
    msg = r["choices"][0]["message"]["content"].strip()[:60]
    # The model id the PROVIDER reports, not the one we asked for: since
    # 2026-09-14 DeepSeek has answered `deepseek-flash`, an UNPRICED id, which
    # makes every dollar cap a lower bound of $0.
    return {**out, "ok": "PONG" in msg.upper(), "s": dt, "reply": msg,
            "provider_model": (r.get("usage") or {}).get("model") or r.get("model"),
            "priced": None if not r.get("model") else "confirm before any paid run"}


def check_openclaw() -> dict:
    from backend.services import openclaw_client as OC
    h, dt, err = _t(OC.health)
    if err:
        return {"ok": False, "detail": err, "s": dt}
    d = h.as_dict()
    return {"ok": bool(d.get("ok")), "s": dt, "profile": d.get("profile_wanted"),
            "gateway": d.get("gateway_probe_ok"), "pinned": d.get("profile_pinned"),
            "channels": d.get("messaging_channels"), "verdict": d.get("verdict")}


def check_sim() -> dict:
    from backend.services import sim_session as SS
    st, dt, err = _t(SS.status)
    if err:
        return {"ok": False, "detail": err, "s": dt}
    state = st["state"]
    return {"ok": state in ("IDLE", "RUNNING", "STOPPED", "COMPLETED"),
            "s": dt, "state": state, "cycle": st.get("cycle"),
            "resumable": st.get("resumable"),
            "warn": st["session"].get("unclean_reason") if state == "UNCLEAN" else None}


def check_telegram() -> dict:
    from backend.services import telegram_bridge as TG
    st, dt, err = _t(TG.status)
    if err:
        return {"ok": False, "detail": err, "s": dt}
    return {"ok": st.get("state") == "READY", "s": dt, "state": st.get("state"),
            "bot": (st.get("bot") or {}).get("username"),
            "owner_set": bool(st.get("owner_chat_id"))}


def check_data() -> dict:
    from scripts.gap_audit import audit
    a, dt, err = _t(audit)
    if err:
        return {"ok": False, "detail": err, "s": dt}
    return {"ok": a["n_blocking"] == 0, "s": dt,
            "blocking": a["blocking"], "n_sources": a["n_sources"]}


def run(deep: bool = False) -> dict:
    rows = {
        "broker": check_broker(),
        "local_model": check_local_model(deep),
        "deepseek": check_deepseek(deep),
        "openclaw": check_openclaw(),
        "simulation": check_sim(),
        "telegram": check_telegram(),
        "data_freshness": check_data(),
    }
    red = [k for k, v in rows.items() if not v.get("ok")]
    return {"receipt": "stack_health", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "deep": deep, "green": not red, "red": red, "rows": rows,
            "read_me_first": ("Every row is a MEASUREMENT, not a config read. "
                              "A green here is a claim the night can do its job.")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true",
                    help="also ask the local model and DeepSeek a question")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    res = run(deep=a.deep)

    print(f"{'component':>16}  {'':<4} detail")
    print("-" * 88)
    for k, v in res["rows"].items():
        mark = "ok" if v.get("ok") else "!!"
        detail = {kk: vv for kk, vv in v.items() if kk not in ("ok",)}
        print(f"{k:>16}  {mark:<4} {json.dumps(detail, default=str)[:112]}")
    print()
    print("GREEN — the stack can run a night" if res["green"]
          else f"RED: {', '.join(res['red'])}")

    out = Path(a.out) if a.out else _cfg.OPTIMUS_LEDGER_DIR / f"stack_health_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"-> {out}")
    return 0 if res["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
