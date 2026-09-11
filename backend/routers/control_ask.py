"""ASK AEGIS — the answering route, alone in its own module (roadmap O6).

WHY THIS IS NOT IN `control.py`
===============================
The property that makes an assistant safe to point at a checkout is negative:
**it cannot write, cannot spawn, cannot reach a broker, cannot POST anywhere.**
A negative property can only be proved over a file that contains nothing else,
and `control.py` legitimately spawns night jobs and writes a run registry. So
the ask path moved here, and `backend/tests/test_ask_authority.py` walks the AST
of THIS module and `services/ask_tools.py` and fails on `open(..., "w")`,
`subprocess`, a broker symbol, or an outbound POST.

WHAT IT DOES
============
1. Routes the question deterministically (`ask_tools.route`) to ONE read tool —
   a repo file, a job's newest receipt, the fleet, tonight's plan, today's
   morning receipt, the universe header, or the canon default. Until today the
   assistant saw exactly one thing, the last two nights' `LEADERBOARD.md`, and
   answered "look at scripts/night_g3_evolve_v2.py" from it.
2. Answers a FORECAST question from the morning's own rows WITHOUT the model,
   because a forecast generated at question time is in no ledger and cannot be
   graded tomorrow. That is the one sentence this assistant must never produce.
3. Otherwise hands the model the retrieved text and appends a `sources:` line
   computed from the files that were actually opened — never asked of the model,
   which would invent one.

The O7 behaviour is unchanged: `start=true` starts the local model only when
NOTHING is listening, waits for readiness rather than for the socket, and never
stops anything at all.
"""

from __future__ import annotations

import os
import time

from fastapi import APIRouter, HTTPException

from backend.routers.control import _now, _require_enabled
from backend.services import ask_tools

router = APIRouter(prefix="/api/control", tags=["control"])


ASK_SYSTEM = (
    "You are the Aegis desktop assistant. You READ receipts and explain them. "
    "You have no authority: you cannot run jobs, seal books, arm lanes, size positions "
    "or place orders, and you must never imply otherwise. "
    "Every number you state must appear in the context you were given; if a number is "
    "not there, say you do not have it rather than estimating. "
    "If a result has a control, quote the control beside it. If an estimate has a "
    "standard error, quote it. Answer in English."
)

#: how often readiness is polled while a model loads. A constant so a test can
#: shorten it; a multi-GB model takes tens of seconds, and a tighter poll buys
#: nothing but CPU.
ASK_POLL_S = float(os.getenv("AEGIS_ASK_POLL_S", "1.0"))

#: Two blank lines between the answer and its sources line. Named so the string
#: survives being edited by a tool that rewrites escapes.
_GAP = "\n\n"

#: Questions that ask for a FORECAST rather than for a receipt. These are
#: answered from the ledger, deterministically, with no model in the path.
_FORECAST_INTENT = ("what do you think happens", "what happens today",
                    "what will happen", "what do you expect", "predict",
                    "forecast", "outlook for today", "think today")


def _is_forecast_question(q: str) -> bool:
    low = q.lower()
    return any(w in low for w in _FORECAST_INTENT)


def _wait_until_ready(ls, budget_s: float) -> bool:
    """Poll `status()` until the model answers, or the budget runs out.

    `listening` is not `ready`: llama-server binds its port in about half a
    second with a fifth of the weights resident, and a question sent in that
    window used to come back as a refusal telling the user to start a server
    that was already starting. Waiting is the honest answer to "loading".
    """
    deadline = time.time() + max(0.0, budget_s)
    while True:
        if ls.status().get("ready"):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(min(ASK_POLL_S, max(0.0, deadline - time.time())))


@router.post("/ask")
def ask(question: str, backend: str = "local_gguf", max_tokens: int = 700,
        start: bool = False, wait_s: float = 90.0) -> dict:
    """Answer from the project, and — only when asked — start the model first.

    Three things happen before the model is consulted: the question is ROUTED to
    exactly one read tool; a forecast question is answered from today's morning
    rows and returns with no model call at all; and the `sources:` line is
    computed from the paths actually opened.

    `start=true` is the Ask page's button, not a default: starting a multi-GB
    server is a decision about somebody's VRAM, so it is taken by a person and
    the payload says whether it happened (`started`) and what it cost in
    wall-clock seconds (`waited_s`). The foreign-server rule is structural: a
    start is attempted ONLY when nothing is listening, and this route never
    stops anything at all.
    """
    _require_enabled()
    q = (question or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="question is empty")

    ctx = ask_tools.build_context(q)
    common = {"utc": _now(), "question": q,
              "tool": ctx["tool"], "tool_arg": ctx["tool_arg"],
              "routed_because": ctx["routed_because"],
              "tools_available": ctx["tools_available"],
              "context_sources": ctx["sources"],
              "context_truncated": ctx["truncated"],
              "authority": ("READER ONLY: this endpoint cannot run, seal, arm or "
                            "order anything"),
              "cost_usd": 0.0}

    # THE LEDGER ANSWERS FOR ITSELF. No model, no invention, no exception.
    if ctx["tool"] == "morning" and _is_forecast_question(q):
        rows, receipt = ask_tools.morning_forecast_rows()
        answer = ask_tools.forecast_answer(rows, receipt)
        sources = [receipt] if receipt else []
        return {**common, "ok": True, "answered_by": "ledger",
                "answer": answer + _GAP + ask_tools.sources_line(sources),
                "context_sources": sources, "model": None, "backend": "none",
                "morning_has_run": receipt is not None,
                "n_forecast_rows": len(rows),
                "note": ("answered from the forecast rows the morning wrote before "
                         "the session; no model was called, so nothing here can be "
                         "a forecast that is not already in the ledger")}

    from backend.services import free_inference as fi
    from backend.services import llama_server as ls
    st = ls.status()
    started = False
    waited_s = 0.0
    start_result: dict | None = None
    if backend == "local_gguf" and not st.get("ready"):
        budget = max(0.0, min(float(wait_s), 600.0))
        t0 = time.time()
        if st.get("listening"):
            # somebody's server -- ours or not -- is loading. Wait; start nothing.
            _wait_until_ready(ls, budget)
        elif start:
            start_result = ls.start(wait_s=budget)
            started = bool(start_result.get("ok")) and start_result.get("action") in {
                "started", "starting"}
            if started:
                _wait_until_ready(ls, max(0.0, budget - (time.time() - t0)))
        waited_s = round(time.time() - t0, 1)
        st = ls.status()
    if backend == "local_gguf" and not st.get("ready"):
        # a refusal that names the fix, rather than a 500 from a dead socket
        fix = ("Start it from the Services page (or POST /api/control/llama/start)."
               if not start else
               "It was asked to start and is not answering yet; the log is at "
               "~/llama/server.log.")
        return {**common, "ok": False, "answer": None,
                "refusal": "the local model is not ready: " + str(st.get("detail")) + ". " + fix,
                "started": started, "waited_s": waited_s,
                "start_result": start_result, "llama": st}

    prompt = (ASK_SYSTEM + _GAP
              + "--- WHAT YOU MAY READ (routed: " + str(ctx["routed_because"]) + ") ---\n"
              + ctx["text"] + "\n--- END ---" + _GAP
              + "Question: " + q + "\n")
    try:
        reply = fi.complete(backend=backend, prompt=prompt, max_tokens=int(max_tokens))
    except Exception as exc:  # noqa: BLE001 - surface the reason, never a blank page
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc
    text = getattr(reply, "text", None) or getattr(reply, "content", None) or str(reply)
    return {**common, "ok": True, "answered_by": "local_model",
            "answer": str(text).rstrip() + _GAP + ask_tools.sources_line(ctx["sources"]),
            "backend": backend, "model": st.get("model"),
            "started": started, "waited_s": waited_s}
