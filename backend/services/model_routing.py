"""Model routing for the operator surface (chunk G, 2026-09-26).

Murat's brief, section G, verbatim substance:

    llama-server not permanently resident; OpenClaw localService; idle
    shutdown; Telegram /nav /status /books /forecasts deterministic; /ask local
    on demand; /research OpenClaw + local; /deep DeepSeek or NVIDIA; /compare
    all three frozen and graded; cost and incremental accuracy per provider.

THE TABLE (`ROUTES`), and the one rule behind it
================================================
A question about MONEY or STATE is answered from a receipt on disk and never by
a model -- a model asked "what is my NAV" can only paraphrase a number it was
handed, and a paraphrase of money is a new way to be wrong. Only a question
that needs judgment reaches a model, and then the reply names which model, what
it cost and how long it took, so the phone shows the price of every answer.

    /nav /status /books /forecasts   deterministic   receipts, no model call
    /ask <q>                         local           llama_server.ensure, on demand
    /research <ticker>               openclaw+local  the thesis-card quest, local synthesis
    /deep <q> [--nvidia]             deepseek|nvidia DeepSeek unless --nvidia is in the text
    /compare <ticker>                all three       ONE packet, three frozen forecast rows

/compare IS A MEASUREMENT, NOT A CHAT
=====================================
The same evidence packet (hashed) goes to local, DeepSeek and NVIDIA. Each
answer that states a probability becomes a `PredictionRecord` --
`specialist = compare:<provider>`, `beats_benchmark` vs SPY at h=5, the raw
probability unshrunk -- in the same ledger every other forecast lives in, so
the existing resolver and grader score it like any other row. The receipt
`model_routing/compare_<date>.json` aggregates cost, latency and (once graded)
Brier per provider. That is rule 7 of the session order: cost per provider is
measured, never assumed.

Nothing here places an order, sizes a position, or approves anything.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend import config as _cfg

logger = logging.getLogger(__name__)

#: command -> route. The TABLE is the contract the tests pin.
ROUTES: dict[str, str] = {
    "nav": "deterministic",
    "status": "deterministic",
    "books": "deterministic",
    "forecasts": "deterministic",
    "ask": "local",
    "research": "openclaw+local",
    "deep": "deepseek|nvidia",
    "compare": "local+deepseek+nvidia",
}
DETERMINISTIC = frozenset(k for k, v in ROUTES.items() if v == "deterministic")
COMPARE_PROVIDERS: tuple[str, ...] = ("local", "deepseek", "nvidia")
COMPARE_MECHANISM = "model_routing_compare_v1"


def ledger_dir() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR)


def receipt_dir(root: Path | None = None) -> Path:
    return (root or ledger_dir()) / "model_routing"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _latest(root: Path, pattern: str) -> Path | None:
    files = sorted(root.glob(pattern))
    return files[-1] if files else None


def _load(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pct(x: Any, nd: int = 2) -> str:
    try:
        return f"{float(x):+.{nd}f}%"
    except (TypeError, ValueError):
        return "n/a"


# ─────────────────────────────── deterministic ──────────────────────────────

def nav_text(root: Path | None = None) -> str:
    """Every paper account from the ROI receipt. No broker call, no model."""
    root = root or ledger_dir()
    p = _latest(root / "paper_accounts", "roi_*.json")
    d = _load(p)
    if not d:
        return "*NAV* -- CANNOT DETERMINE: no `paper_accounts/roi_*.json` receipt on disk."
    agg = (d.get("aggregate") or {})
    allp = agg.get("priced_excluding_control_twins") or agg.get("all_priced") or {}
    lines = [f"*NAV* (receipt `{p.name}`, {d.get('generated_utc')})",
             f"{allp.get('n', '?')} priced accounts ex-twins: equity "
             f"${float(allp.get('sum_equity') or 0):,.0f}, P&L "
             f"${float(allp.get('pnl') or 0):,.0f} ({_pct(allp.get('roi_pct'), 3)})",
             f"ahead of SPY {agg.get('n_ahead_of_spy', '?')} · behind {agg.get('n_behind_spy', '?')}"]
    rows = [r for r in (d.get("rows") or []) if r.get("roi_pct") is not None
            and "twin" not in str(r.get("family"))]
    rows.sort(key=lambda r: float(r.get("vs_spy_pp") or -1e9), reverse=True)
    for r in rows[:6]:
        lines.append(f"`{str(r.get('account'))[:24]}` {_pct(r.get('roi_pct'))} "
                     f"vs SPY {_pct(r.get('vs_spy_pp'))}pp")
    lines.append("_from the receipt, not the broker; every book is PRODUCT_EXPERIMENT._")
    return "\n".join(lines)


def status_text(root: Path | None = None, *, llama_status: Callable[[], dict] | None = None) -> str:
    """Simulation state from `sim/session.json` plus the model server probe."""
    root = root or ledger_dir()
    s = _load(root / "sim" / "session.json")
    lines = ["*Status*"]
    if s:
        lines.append(f"sim `{s.get('id')}` {s.get('state')} · mode {s.get('mode')} · "
                     f"cycle {s.get('final_cycle') or s.get('cycle')}")
        lines.append(f"started {s.get('started')} · heartbeat {s.get('heartbeat')}")
        if s.get("end_reason"):
            lines.append(f"ended {s.get('ended')}: {s.get('end_reason')}")
    else:
        lines.append("sim -- CANNOT DETERMINE: no `sim/session.json`")
    try:
        if llama_status is None:
            from backend.services import llama_server as LS
            llama_status = LS.status
        st = llama_status()
        lines.append(f"local model: listening={st.get('listening')} ready={st.get('ready')} "
                     f"pid={st.get('pid')} ({st.get('detail')})")
    except Exception as exc:                                       # noqa: BLE001
        lines.append(f"local model: probe failed `{type(exc).__name__}`")
    lines.append("_local model starts on demand (/ask, /research, /compare) and stops "
                 f"after {int(getattr(_cfg, 'MODEL_ROUTING_IDLE_SHUTDOWN_S', 900))}s idle._")
    return "\n".join(lines)


def books_text(root: Path | None = None) -> str:
    root = root or ledger_dir()
    p = _latest(root / "llm_portfolio", "leaderboard_*.json")
    d = _load(p)
    if not d:
        return "*Books* -- CANNOT DETERMINE: no `llm_portfolio/leaderboard_*.json`."
    books = d.get("books") or []
    by_status: dict[str, int] = {}
    for b in books:
        by_status[str(b.get("status"))] = by_status.get(str(b.get("status")), 0) + 1
    lines = [f"*Books* (`{p.name}`, bars through {d.get('bars_through')})",
             f"{d.get('n_books')} books · {d.get('n_twins')} twins · "
             + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items()))]
    graded = [b for b in books if b.get("vs_benchmark") is not None]
    graded.sort(key=lambda b: float(b["vs_benchmark"]), reverse=True)
    for b in graded[:8]:
        lines.append(f"`{str(b.get('name'))[:28]}` net {_pct((b.get('net_to_date') or 0) * 100)} "
                     f"vs {b.get('benchmark')} {_pct(float(b['vs_benchmark']) * 100)}")
    if not graded:
        lines.append("_no book has a graded session yet._")
    return "\n".join(lines)


def forecasts_text(root: Path | None = None) -> str:
    root = root or ledger_dir()
    p = _latest(root / "forecasts", "day_*.json")
    d = _load(p)
    if not d:
        return "*Forecasts* -- CANNOT DETERMINE: no `forecasts/day_*.json`."
    return "\n".join([
        f"*Forecasts* {d.get('day')} -- {d.get('state')}",
        f"specialist `{d.get('specialist')}` · model `{d.get('model')}` · horizons {d.get('horizons')}",
        f"{len(d.get('done') or [])} names done · {len(d.get('unpriced') or [])} unpriced · "
        f"{len(d.get('refused') or [])} refused · {d.get('n_rows_written')} rows",
        f"spent ${float(d.get('spent_usd') or 0):.4f} of cap ${float(d.get('cap_usd') or 0):.2f}",
    ])


# ─────────────────────────────── model routes ───────────────────────────────

def _call(provider: str, system: str, user: str, *, purpose: str,
          call_fn: Callable[..., dict] | None = None, **kw) -> dict:
    if call_fn is None:
        from backend.services import llm_analyzer as LA
        call_fn = LA.call_named
    return call_fn(provider, system, user, purpose=purpose, **kw)


def footer(r: dict) -> str:
    """provider · model · cost · latency, on every model reply."""
    cost = r.get("cost_usd")
    c = ("UNPRICED" if cost is None and r.get("cost_status") == "UNPRICED"
         else "n/a" if cost is None else f"${float(cost):.5f}")
    lat = r.get("latency_s")
    return (f"\n\n_{r.get('provider')} · {r.get('model')} · cost {c} · "
            f"latency {'n/a' if lat is None else f'{float(lat):.1f}s'} · {r.get('status')}_")


ASK_SYSTEM = ("You are Aegis's local research assistant. Answer briefly and plainly. "
              "If you do not know, say so. Never give an instruction to trade.")


def ask(question: str, *, call_fn=None) -> tuple[str, dict]:
    r = _call("local", ASK_SYSTEM, question, purpose="telegram:ask",
              ensure_reason="telegram:/ask", call_fn=call_fn)
    body = r.get("text") or f"*No answer* -- `{r.get('status')}`: {r.get('error')}"
    return body + footer(r), r


def deep_provider(text: str) -> str:
    return "nvidia" if "--nvidia" in (text or "").split() else "deepseek"


def deep(text: str, *, call_fn=None) -> tuple[str, dict]:
    provider = deep_provider(text)
    q = " ".join(w for w in (text or "").split() if w != "--nvidia")
    r = _call(provider, ASK_SYSTEM, q, purpose="telegram:deep", call_fn=call_fn)
    body = r.get("text") or f"*No answer* -- `{r.get('status')}`: {r.get('error')}"
    return body + footer(r), r


def research(ticker: str, *, quest_fn: Callable[[str, str], dict] | None = None,
             call_fn=None, asof: date | None = None) -> tuple[str, dict]:
    """The thesis-card quest through OpenClaw, synthesised by the LOCAL model.

    The engine side is built with no inputs loaded (UNAVAILABLE, listed as such
    by `engine_side`): a phone command must not load the 1.3M-row bars panel.
    """
    from backend.services import thesis_card as TC
    t = str(ticker).upper()
    engine = TC.engine_side(t, asof=asof or date.today())
    prompt = TC.quest_prompt(t, engine)
    if quest_fn is None:
        quest_fn = _openclaw_quest
    q = quest_fn(t, prompt)
    web = TC.parse_reply(q.get("reply") or "")
    synth_calls: list[dict] = []

    def _local(system, user, *, purpose, validate=None):
        r = _call("local", system, user, purpose=purpose, validate=validate,
                  ensure_reason="telegram:/research", call_fn=call_fn)
        synth_calls.append(r)
        return r.get("text")

    syn = TC.synthesize(engine, web, model="local", call_fn=_local)
    r = synth_calls[-1] if synth_calls else {"provider": "local", "status": "NOT_CALLED"}
    lines = [f"*Research* {t}",
             f"quest: {q.get('status')} · {q.get('latency_s') or q.get('elapsed_s')}s · "
             f"openclaw cost {q.get('openclaw_cost_usd') or q.get('cost_usd')}",
             f"web parse: {web.get('parse')}",
             f"verdict *{syn.get('verdict')}* · confidence {syn.get('confidence')} · "
             f"synth {syn.get('synth_status')}"]
    for k in ("bull", "bear", "falsifier"):
        if syn.get(k):
            lines.append(f"*{k}*: {str(syn[k])[:400]}")
    return "\n".join(lines) + footer(r), {"quest": q, "web_parse": web.get("parse"),
                                          "synth": syn, "local": r}


def _openclaw_quest(ticker: str, prompt: str) -> dict:
    import tempfile
    from backend.services import openclaw_client as OC
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(prompt)
        msg = fh.name
    try:
        return OC.agent(msg, purpose="telegram:research_quest")
    finally:
        Path(msg).unlink(missing_ok=True)


# ─────────────────────────────── /compare ───────────────────────────────────

COMPARE_SYSTEM = (
    "You are one of several independent forecasters given the SAME evidence packet. "
    "Question: will this stock's total return over the next 5 trading sessions beat "
    "SPY's? Use only the packet. Reply in at most 120 words, then exactly three final "
    "lines:\nFOR: <one sentence>\nAGAINST: <one sentence>\nP_BEATS_SPY_5D: <a number "
    "between 0 and 1>")

_P_RE = re.compile(r"P_BEATS_SPY_5D\s*[:=]\s*\**\s*([01](?:\.\d+)?|\.\d+)", re.I)


def parse_probability(text: str | None) -> float | None:
    """The stated probability, or None -- never coerced, never defaulted to 0.5."""
    if not text:
        return None
    m = _P_RE.findall(text)
    if not m:
        return None
    try:
        p = float(m[-1])
    except ValueError:
        return None
    return p if 0.0 <= p <= 1.0 else None


def _line(text: str | None, key: str) -> str | None:
    for ln in (text or "").splitlines():
        if ln.strip().upper().startswith(key + ":"):
            return ln.split(":", 1)[1].strip() or None
    return None


def build_packet(ticker: str, *, asof: date | None = None,
                 bars_path: Path | None = None, bars=None) -> dict:
    """The ONE evidence packet: point-in-time price facts from the local panel.

    Reads only this ticker's rows (a filtered parquet read). `bars`, when given,
    is a DataFrame with `date`/`close` and replaces the read (tests).
    """
    t = str(ticker).upper()
    a = asof or date.today()
    pkt: dict[str, Any] = {"ticker": t, "asof": str(a), "benchmark": "SPY",
                           "question": "P(5-session total return > SPY's)",
                           "source": "prices_2025_26/bars.parquet (close <= asof)"}
    try:
        if bars is None:
            import pandas as pd
            path = bars_path or (ledger_dir() / "prices_2025_26" / "bars.parquet")
            bars = pd.read_parquet(path, columns=["symbol", "date", "close", "volume"],
                                   filters=[("symbol", "in", [t, "SPY"])])
        df = bars.copy()
        if "symbol" not in df.columns:
            df["symbol"] = t
        df["d"] = df["date"].astype(str).str[:10]
        df = df[df["d"] <= str(a)].sort_values("d")

        def _facts(sym: str) -> dict:
            s = df[df["symbol"] == sym]["close"].astype(float).tolist()
            if len(s) < 2:
                return {"n_bars": len(s)}

            def ret(n: int):
                return round(s[-1] / s[-1 - n] - 1.0, 4) if len(s) > n else None
            rets = [s[i] / s[i - 1] - 1.0 for i in range(max(1, len(s) - 21), len(s))]
            mu = sum(rets) / len(rets)
            vol = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1))
            return {"n_bars": len(s), "last_close": round(s[-1], 4),
                    "ret_5d": ret(5), "ret_21d": ret(21), "ret_63d": ret(63),
                    "vol_21d_daily": round(vol, 4)}
        pkt["stock"] = _facts(t)
        pkt["spy"] = _facts("SPY")
        pkt["last_bar"] = df["d"].iloc[-1] if len(df) else None
    except Exception as exc:                                       # noqa: BLE001
        pkt["price_facts"] = f"UNAVAILABLE: {type(exc).__name__}: {str(exc)[:160]}"
    return pkt


def packet_hash(packet: dict) -> str:
    from backend.services.belief_state import _hash
    return _hash(packet)


def compare(ticker: str, *, packet: dict | None = None, call_fn=None,
            ledger_path: Path | None = None, receipt_root: Path | None = None,
            providers: tuple[str, ...] = COMPARE_PROVIDERS,
            asof: date | None = None) -> tuple[str, dict]:
    """ONE packet -> local, DeepSeek, NVIDIA -> one frozen forecast row each."""
    from backend.services import belief_state as B
    t = str(ticker).upper()
    a = asof or date.today()
    pkt = packet if packet is not None else build_packet(t, asof=a)
    h = packet_hash(pkt)
    user = "EVIDENCE PACKET:\n" + json.dumps(pkt, sort_keys=True, default=str)
    horizon = int(getattr(_cfg, "MODEL_ROUTING_COMPARE_HORIZON", 5))
    bench = str(getattr(_cfg, "MODEL_ROUTING_COMPARE_BENCHMARK", "SPY"))
    answers, rows = [], []
    for prov in providers:
        r = _call(prov, COMPARE_SYSTEM, user, purpose=f"compare:{prov}",
                  ensure_reason="telegram:/compare", call_fn=call_fn,
                  validate=lambda txt: parse_probability(txt) is not None)
        p = parse_probability(r.get("text"))
        ans = {"provider": prov, "model": r.get("model"), "status": r.get("status"),
               "cost_usd": r.get("cost_usd"), "cost_status": r.get("cost_status"),
               "latency_s": r.get("latency_s"), "p": p, "prediction_id": None,
               "error": r.get("error")}
        if r.get("ok") and p is not None:
            rec = B.make_prediction(
                ticker=t, specialist=f"compare:{prov}",
                observable=B.Observable.BEATS_BENCHMARK, horizon_days=horizon,
                benchmark=bench, probability=p, raw_probability=p,
                shrink_basis="none: raw model probability, unshrunk (compare route)",
                thesis=(_line(r["text"], "FOR") or r["text"][:400]),
                counter_thesis=(_line(r["text"], "AGAINST") or "not stated by the model"),
                next_observable=f"{t} total return vs {bench} over {horizon} sessions",
                model=str(r.get("model")), model_version=str(r.get("model")),
                prompt=COMPARE_SYSTEM + "\n" + user, input_snapshot=pkt,
                mechanism_id=COMPARE_MECHANISM, decision_date=str(a),
                inputs_used={"packet_hash": h, "provider": prov},
                licence="PRODUCT_EXPERIMENT",
                notes_text=(f"compare packet_hash={h} cost_usd={r.get('cost_usd')} "
                            f"latency_s={r.get('latency_s')}"))
            rows.append(rec)
            ans["prediction_id"] = rec.prediction_id
        elif r.get("ok"):
            ans["status"] = "NO_PROBABILITY"
        answers.append(ans)
    if rows:
        B.append(rows, ledger_path)
    event = {"at": _now(), "ticker": t, "asof": str(a), "packet_hash": h,
             "horizon_days": horizon, "benchmark": bench, "answers": answers}
    receipt = write_compare_receipt(event, root=receipt_root, ledger_path=ledger_path)
    lines = [f"*Compare* {t} · packet `{h}` · h={horizon} vs {bench}"]
    for x in answers:
        c = ("UNPRICED" if x["cost_usd"] is None and x.get("cost_status") == "UNPRICED"
             else "n/a" if x["cost_usd"] is None else f"${float(x['cost_usd']):.5f}")
        lat = "n/a" if x["latency_s"] is None else f"{float(x['latency_s']):.1f}s"
        p_txt = "--" if x["p"] is None else f"{x['p']:.2f}"
        lines.append(f"`{x['provider']}` p={p_txt} · {x['status']} · cost {c} · {lat}")
    lines.append(f"_{len(rows)} row(s) frozen as `compare:<provider>`; graded when "
                 f"{horizon} sessions have passed. Receipt `{receipt.name}`._")
    return "\n".join(lines), {"packet_hash": h, "answers": answers,
                              "prediction_ids": [r.prediction_id for r in rows],
                              "receipt": str(receipt)}


def _brier_by_provider(ledger_path: Path | None) -> dict:
    from backend.services import belief_state as B
    try:
        preds = B.read_predictions(ledger_path) if ledger_path else B.read_predictions()
    except Exception as exc:                                       # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}
    out: dict[str, dict] = {}
    for r in preds:
        sp = str(r.get("specialist") or "")
        if not sp.startswith("compare:"):
            continue
        prov = sp.split(":", 1)[1]
        b = out.setdefault(prov, {"n_rows": 0, "n_graded": 0, "brier": None, "_sq": 0.0})
        b["n_rows"] += 1
        o = r.get("outcome")
        if o is None:
            continue
        try:
            y = float(o)
        except (TypeError, ValueError):
            continue
        b["n_graded"] += 1
        b["_sq"] += (float(r["probability"]) - y) ** 2
    for b in out.values():
        b["brier"] = round(b["_sq"] / b["n_graded"], 5) if b["n_graded"] else None
        b.pop("_sq")
    return out


def write_compare_receipt(event: dict, *, root: Path | None = None,
                          ledger_path: Path | None = None,
                          day: str | None = None) -> Path:
    """Append the event to `compare_<day>.json` and re-derive the aggregates."""
    d = receipt_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    day = day or str(date.today())
    path = d / f"compare_{day}.json"
    cur = _load(path) or {}
    events = list(cur.get("events") or []) + [event]
    agg: dict[str, dict] = {}
    for e in events:
        for x in e.get("answers") or []:
            a = agg.setdefault(x["provider"], {"n_calls": 0, "n_ok": 0, "n_rows": 0,
                                               "cost_usd": 0.0, "n_unpriced": 0,
                                               "latency_s_sum": 0.0, "n_latency": 0})
            a["n_calls"] += 1
            a["n_ok"] += int(x.get("status") == "OK")
            a["n_rows"] += int(bool(x.get("prediction_id")))
            if x.get("cost_usd") is None:
                a["n_unpriced"] += 1
            else:
                a["cost_usd"] = round(a["cost_usd"] + float(x["cost_usd"]), 8)
            if x.get("latency_s") is not None:
                a["latency_s_sum"] += float(x["latency_s"])
                a["n_latency"] += 1
    for a in agg.values():
        a["mean_latency_s"] = (round(a["latency_s_sum"] / a["n_latency"], 3)
                               if a["n_latency"] else None)
        a["cost_per_row_usd"] = (round(a["cost_usd"] / a["n_rows"], 8) if a["n_rows"] else None)
        a.pop("latency_s_sum")
        a.pop("n_latency")
    doc = {"receipt": "model_routing_compare", "schema": "model_routing_compare/1",
           "day": day, "licence": "PRODUCT_EXPERIMENT", "updated_utc": _now(),
           "n_events": len(events), "by_provider": agg,
           "graded_by_provider": _brier_by_provider(ledger_path),
           "read_me_first": ("Every /compare sends ONE hashed packet to local, DeepSeek and "
                             "NVIDIA; each stated probability is a frozen forecast row "
                             "(specialist compare:<provider>, beats_benchmark vs SPY, h=5, "
                             "raw p). cost_usd sums telemetry-priced calls; n_unpriced counts "
                             "calls whose cost is unknown (a total with any is a LOWER BOUND). "
                             "Brier appears once the grader has resolved rows."),
           "events": events}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)
    return path


def route(cmd: str, args: list[str], *, call_fn=None, quest_fn=None,
          root: Path | None = None, llama_status=None) -> str:
    """The dispatcher the Telegram agent calls. Deterministic commands never
    touch `call_fn`."""
    cmd = cmd.lower()
    if cmd == "nav":
        return nav_text(root)
    if cmd == "status":
        return status_text(root, llama_status=llama_status)
    if cmd == "books":
        return books_text(root)
    if cmd == "forecasts":
        return forecasts_text(root)
    text = " ".join(args).strip()
    if cmd == "ask":
        return ask(text, call_fn=call_fn)[0] if text else "Usage: `/ask <question>`"
    if cmd == "deep":
        return deep(text, call_fn=call_fn)[0] if text else "Usage: `/deep <question> [--nvidia]`"
    if cmd == "research":
        return (research(args[0], quest_fn=quest_fn, call_fn=call_fn)[0] if args
                else "Usage: `/research <ticker>`")
    if cmd == "compare":
        return compare(args[0], call_fn=call_fn)[0] if args else "Usage: `/compare <ticker>`"
    raise KeyError(f"no route for /{cmd}")


__all__ = ["ROUTES", "DETERMINISTIC", "COMPARE_PROVIDERS", "route", "ask", "deep",
           "research", "compare", "build_packet", "packet_hash", "parse_probability",
           "write_compare_receipt", "nav_text", "status_text", "books_text",
           "forecasts_text", "footer", "deep_provider"]
