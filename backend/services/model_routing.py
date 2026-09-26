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
    /research <ticker> [--quest]     evidence        nine dated fields from disk, <=600 chars;
                                                     --quest runs the thesis-card path first
    /deep <q> [--nvidia]             deepseek|nvidia DeepSeek unless --nvidia is in the text
    /compare [ticker]                bakeoff_read    the E-G1 extraction table (read-only)

G-FIX (adjudication row 7, 2026-09-26)
======================================
The review found `/research` threw the quest's evidence away and sent comments,
and `/compare` measured DIRECTION (held-out skill -7.9%) on six price numbers.
`/research` now answers with evidence (holdings, rank decile, revisions, next
catalyst, stop in sigma, what changed, forecast id, falsifier); `/compare` reads
the extraction bake-off E-G1, which grades four arms against the
analyst-revisions file the same day. Magnitude stays the forward test.

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
    "research": "evidence",
    "deep": "deepseek|nvidia",
    "compare": "bakeoff_read",
}
DETERMINISTIC = frozenset(k for k, v in ROUTES.items() if v == "deterministic")


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
    lines.append("_local model starts on demand (/ask, batch typing) and the reaper stops it "
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


# ─────────────────────────────── /research ──────────────────────────────────
#
# G-fix, adjudication row 7. Chunk G's /research ran the quest with NO engine
# inputs, parsed the twelve answers, X reads, dated claims and promises -- and
# threw them away, sending bull/bear/falsifier[:400]: comments. The reply is now
# EVIDENCE: nine dated fields read from files already on disk, each printing
# `n/a: <why>` when its source is missing (never silently blank), in <= 600
# characters. No model is called for the reply. `--quest` additionally runs the
# full thesis-card path (`scripts.thesis_cards.run`: engine inputs loaded, prior
# card and open promises passed, card + claims + promises + forecast rows
# written, synthesis on DeepSeek) BEFORE the evidence is read, so "what
# changed" then includes the card it just wrote.

RESEARCH_MAX_CHARS = 600
STOP_SIGMAS = 2.0
SIGMA_WINDOW = 63
REVISION_DAYS = 21


def _na(why: str) -> str:
    return f"n/a: {why}"


def _fmt_day(v: Any) -> str:
    return str(v)[:10] if v else "?"


def _holdings(t: str, books_path: Path | None) -> str:
    try:
        from backend.services import llm_portfolio as LP
        books = LP.read_books(books_path)          # voided books are left out
    except FileNotFoundError:
        return _na("no llm_portfolio books.jsonl")
    except Exception as exc:                                       # noqa: BLE001
        return _na(f"books unreadable ({type(exc).__name__})")
    held = []
    n_books = 0
    for b in books:
        if b.get("kind") == "twin":
            continue
        n_books += 1
        for p in b.get("positions") or []:
            if str(p.get("ticker", "")).upper() == t:
                held.append((float(p.get("weight") or 0.0), str(b.get("name"))))
    if not n_books:
        return _na("no frozen non-twin book")
    if not held:
        return f"none of {n_books} books"
    held.sort(reverse=True)
    s = ", ".join(f"{n[:22]} {w * 100:.1f}%" for w, n in held[:3])
    return f"{len(held)}/{n_books} books: {s}" + (" ..." if len(held) > 3 else "")


def _latest_ranking(root: Path) -> tuple[Path | None, dict | None]:
    files = sorted((root / "pc_book").glob("*/ranking.json"))
    if not files:
        return None, None
    return files[-1], _load(files[-1])


def _rank(t: str, root: Path) -> str:
    p, r = _latest_ranking(root)
    if not r:
        return _na("no pc_book/*/ranking.json receipt")
    for x in r.get("top") or []:
        if str(x.get("symbol", "")).upper() == t:
            er = x.get("expected_relative_return_21d_net")
            return (f"{x.get('rank')}/{r.get('n_eligible')} decile {x.get('decile')} "
                    f"E[r21 net rel] {'unmeasured' if er is None else f'{float(er) * 100:+.2f}%'}"
                    f" (asof {r.get('asof')})")
    return _na(f"not in the top {len(r.get('top') or [])} the receipt persists "
               f"(asof {r.get('asof')}, {r.get('n_eligible')} eligible)")


def _revisions(t: str, today: date, root: Path, revisions=None) -> str:
    try:
        import pandas as pd
        from backend.services import revision_flow as RF
        if revisions is None:
            path = root / "analyst" / "target_revisions.parquet"
            if not path.exists():
                return _na("no analyst/target_revisions.parquet")
            revisions = pd.read_parquet(path, filters=[("ticker", "in", [t])])
        rv = revisions[revisions["ticker"].astype(str).str.upper() == t]
        if rv.empty:
            return _na("ticker absent from the revisions file")
        prep = RF.prepare(rv)
        hi = pd.Timestamp(today) + pd.Timedelta(days=1)
        lo = pd.Timestamp(today) - pd.Timedelta(days=REVISION_DAYS)
        w = prep[(prep["t"] >= lo) & (prep["t"] < hi)]
        if w.empty:
            return f"0 in {REVISION_DAYS}d (last {_fmt_day(prep['t'].max())})"
        up, dn = int((w["sign"] > 0).sum()), int((w["sign"] < 0).sum())
        return (f"net {up - dn:+d} ({up} up/{dn} down, {w['firm'].nunique()} firms), "
                f"last {_fmt_day(w['t'].max())}")
    except Exception as exc:                                       # noqa: BLE001
        return _na(f"revisions unreadable ({type(exc).__name__}: {str(exc)[:60]})")


EIGHTK_FILE_MAX_AGE_DAYS = 30


def _catalyst(t: str, today: date, root: Path, eightk=None) -> str:
    """Next earnings print, ESTIMATED from EDGAR 8-K item 2.02 (the factory's
    freeze-gate source): the year-ago 2.02 + 364d, else the last 2.02 + 91d.
    Stale file or no 2.02 history -> UNKNOWN."""
    try:
        import pandas as pd
        if eightk is None:
            path = root / "edgar_8k" / "eightk_items.parquet"
            if not path.exists():
                return "UNKNOWN (no edgar_8k/eightk_items.parquet)"
            eightk = pd.read_parquet(path, columns=["ticker", "filing_date", "items_joined"])
        ek = eightk.copy()
        ek["filing_date"] = pd.to_datetime(ek["filing_date"], errors="coerce")
        ek = ek[ek["filing_date"].notna() & (ek["filing_date"] <= pd.Timestamp(today))]
        end = ek["filing_date"].max() if len(ek) else None
        if end is None or (pd.Timestamp(today) - end).days > EIGHTK_FILE_MAX_AGE_DAYS:
            return f"UNKNOWN (8-K file ends {_fmt_day(end)})"
        e = ek[(ek["ticker"].astype(str).str.upper() == t)
               & ek["items_joined"].fillna("").astype(str).str.contains("2.02", regex=False)]
        if e.empty:
            return "UNKNOWN (no 8-K 2.02 history)"
        dates = sorted(e["filing_date"])
        last = dates[-1]
        # the NEXT print after the last one: a year-ago 2.02 + 364d that lands
        # more than 30 days after the last print, else the last + 91d
        yago = [d + pd.Timedelta(days=364) for d in dates
                if d + pd.Timedelta(days=364) > last + pd.Timedelta(days=30)]
        est, rule = ((min(yago), "year-ago 2.02 +364d") if yago
                     else (last + pd.Timedelta(days=91), "last 2.02 +91d"))
        late = (f", after the file's end {_fmt_day(end)}: not yet seen"
                if est < pd.Timestamp(today) and est > end else "")
        return (f"earnings est {_fmt_day(est)} ({rule}; last 2.02 {_fmt_day(last)}{late})")
    except Exception as exc:                                       # noqa: BLE001
        return f"UNKNOWN ({type(exc).__name__})"


def _stop(t: str, today: date, root: Path, bars=None) -> str:
    try:
        import pandas as pd
        if bars is None:
            path = root / "prices_2025_26" / "bars.parquet"
            if not path.exists():
                return _na("no prices_2025_26/bars.parquet")
            bars = pd.read_parquet(path, columns=["symbol", "date", "close"],
                                   filters=[("symbol", "in", [t])])
        b = bars[bars["symbol"].astype(str).str.upper() == t].copy()
        b["d"] = pd.to_datetime(b["date"])
        b = b[b["d"] <= pd.Timestamp(today)].sort_values("d")
        c = b["close"].astype(float).tolist()
        if len(c) < SIGMA_WINDOW + 1:
            return _na(f"{len(c)} bars < {SIGMA_WINDOW + 1}")
        r = [c[i] / c[i - 1] - 1.0 for i in range(len(c) - SIGMA_WINDOW, len(c))]
        mu = sum(r) / len(r)
        sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1))
        px = c[-1]
        stop = px * (1.0 - STOP_SIGMAS * sd)
        return (f"1σ/day {sd * 100:.2f}% ({SIGMA_WINDOW}d) -> -{STOP_SIGMAS:g}σ "
                f"${stop:,.2f} from ${px:,.2f} ({_fmt_day(b['d'].iloc[-1])})")
    except Exception as exc:                                       # noqa: BLE001
        return _na(f"bars unreadable ({type(exc).__name__})")


def _cards(t: str, cards_root: Path | None) -> tuple[str, str]:
    """(what changed since the previous card, the falsifier)."""
    try:
        from backend.services import thesis_card as TC
        hist = TC.card_history(t, root=cards_root)
    except Exception as exc:                                       # noqa: BLE001
        why = _na(f"card ledger unreadable ({type(exc).__name__})")
        return why, why
    if not hist:
        return _na("no thesis card for this ticker"), _na("no thesis card")
    cur = hist[-1]
    fal = cur.get("falsifier") or cur.get("web_what_would_falsify")
    fal = str(fal) if fal else _na(f"card {cur.get('asof')} states none")
    if len(hist) == 1:
        return (f"first card {cur.get('asof')} ({cur.get('verdict')}/{cur.get('confidence')}, "
                f"{len(cur.get('claims') or [])} dated claims)"), fal
    d = TC.diff_cards(hist[-2], cur)
    if d.get("schema_change"):
        ch = f"schema {d['schema_change']}"
    else:
        ch = (f"{len(d.get('changed') or [])} answers changed, {len(d.get('new') or [])} new"
              + (f", verdict {d['verdict_change']}" if d.get("verdict_change") else ", verdict same"))
    return f"{hist[-2].get('asof')}->{cur.get('asof')}: {ch}", fal


def _forecast(t: str, predictions_path: Path | None) -> str:
    from backend.services import belief_state as B
    path = Path(predictions_path or B.PREDICTIONS)
    if not path.exists():
        return _na("no predictions.jsonl")
    needle = f'"ticker": "{t}"'
    best = None
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if needle not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if str(r.get("ticker", "")).upper() != t:
                    continue
                if best is None or str(r.get("made_at") or "") > str(best.get("made_at") or ""):
                    best = r
    except OSError as exc:
        return _na(f"predictions unreadable ({type(exc).__name__})")
    if best is None:
        return _na("no forecast row for this ticker")
    p = best.get("probability")
    return (f"{best.get('prediction_id')} {str(best.get('specialist'))[:24]} "
            f"{best.get('observable')} h={best.get('horizon_days')} "
            f"p={'?' if p is None else f'{float(p):.2f}'} ({_fmt_day(best.get('made_at'))})")


EVIDENCE_FIELDS = ("HELD", "RANK", "REV21d", "NEXT", "STOP", "CHANGED", "FORECAST",
                   "FALSIFIER")


def evidence(ticker: str, *, root: Path | None = None, today: date | None = None,
             bars=None, revisions=None, eightk=None, books_path: Path | None = None,
             cards_root: Path | None = None, predictions_path: Path | None = None) -> dict:
    """The eight evidence fields for `ticker`, each a string (value or `n/a: why`)."""
    t = str(ticker).upper().strip()
    root = root or ledger_dir()
    today = today or date.today()
    changed, falsifier = _cards(t, cards_root)
    return {"ticker": t, "asof": str(today),
            "HELD": _holdings(t, books_path),
            "RANK": _rank(t, root),
            "REV21d": _revisions(t, today, root, revisions),
            "NEXT": _catalyst(t, today, root, eightk),
            "STOP": _stop(t, today, root, bars),
            "CHANGED": changed,
            "FORECAST": _forecast(t, predictions_path),
            "FALSIFIER": falsifier}


def evidence_text(ev: dict, *, max_chars: int = RESEARCH_MAX_CHARS) -> str:
    """At most `max_chars`, every field present: the longest line is trimmed
    first, so a long falsifier never pushes the holdings off the screen."""
    head = f"{ev['ticker']} {ev['asof']} evidence"
    lines = {k: str(ev.get(k) or _na("missing")) for k in EVIDENCE_FIELDS}

    def total() -> int:
        return len(head) + sum(len(k) + 2 + len(v) + 1 for k, v in lines.items())
    while total() > max_chars:
        k = max(lines, key=lambda x: len(lines[x]))
        over = total() - max_chars
        v = lines[k]
        keep = max(12, len(v) - over - 1)
        if keep >= len(v):
            break
        lines[k] = v[:keep].rstrip() + "…"
    return "\n".join([head] + [f"{k}: {v}" for k, v in lines.items()])


def research(ticker: str, *, quest: bool = False,
             quest_fn: Callable[[str], dict] | None = None, **ev_kw) -> tuple[str, dict]:
    """`/research T` -> the evidence reply ($0, no model). `/research T --quest`
    -> the full thesis-card run first (card, claims, promises, forecast rows,
    DeepSeek synthesis), then the evidence reply."""
    t = str(ticker).upper().strip()
    run = None
    if quest:
        run = (quest_fn or _thesis_card_run)(t)
    ev = evidence(t, **ev_kw)
    text = evidence_text(ev)
    if run is not None:
        tail = (f"\n_card run: {run.get('state')} · done {len(run.get('done') or [])} · "
                f"refused {len(run.get('refused') or [])} · "
                f"forecast rows {run.get('forecast_rows_written')}_")
        text += tail
    return text, {"evidence": ev, "card_run": run, "chars": len(text)}


def _thesis_card_run(ticker: str) -> dict:
    from scripts import thesis_cards as TCS
    return TCS.run(universe=[{"ticker": ticker, "kind": "personal",
                              "source": "telegram:/research"}],
                   max_quests=1, retry_refused=True)


# ─────────────────────────────── /compare = bake-off E-G1 ───────────────────
#
# G-fix, adjudication row 7. Chunk G's /compare asked three models "P(5-day
# return > SPY)" on six price numbers: DIRECTION, where this system's held-out
# skill is -7.9% -- a noise contest -- at a tap rate that needs years for a
# read-out. DeepSeek's value here is READING text into typed fields, so the
# routing question is answered by EXTRACTION accuracy against mechanical truth:
#
#   240 dated news items (first_seen_utc <= 2026-09-20, archive rows excluded by
#   `news_registry.grade_row`) -> four arms (local llama-server, deepseek-chat,
#   the NVIDIA instruct adjudicator, a rules baseline) -> {ticker, event_type
#   (the full vocabulary enum IS in the system prompt), direction,
#   magnitude_bucket} -> graded against `analyst/target_revisions.parquet`.
#
# GOLD, declared before the run:
#   MATCHED   (180): the item's text names an analyst action AND a tagged
#             ticker has a raise/lower (target_action Raises/Lowers, else
#             action up/down) dated in [published - 2d, first_seen + 5
#             sessions]. Gold event_type = the analyst family
#             {analyst_rating_change, analyst_target_change,
#             analyst_initiation}; gold direction = the sign of the net
#             revisions (ungraded when they net to zero).
#   UNMATCHED (60):  no analyst words and NO revision of any kind for any
#             tagged ticker in the window. Gold = "not an analyst event": an
#             analyst_* answer is an invented fact. Direction ungraded.
#   ticker:   correct when the answer is one of the item's tagged tickers.
# The lower bound reaches 2 days before `published_utc` because an article
# reports an action that already happened; "within 5 sessions after
# first_seen" alone would miss the very revision the article is about.
#
# Magnitude is NOT graded here: it stays the forward test (u_forecast).

BAKEOFF_ID = "E-G1"
ANALYST_TYPES = frozenset({"analyst_rating_change", "analyst_target_change",
                           "analyst_initiation"})
BAKEOFF_ARMS: tuple[str, ...] = ("rules", "deepseek", "nvidia", "local")
#: Words that name an analyst ACTION, not analysts in general: "Analysts
#: expect AI capex..." is not a rating change (the first dry run's item 0 was
#: exactly that, so a bare `analyst` was dropped before any arm was called).
#: Read on the TITLE only, and verb forms only: the second dry run found
#: "Apple Watch ... Every upgrade" and "Is AMETEK Outperforming the S&P 500?"
#: matched on body/noun forms. Both were removed before any arm was called.
_ANALYST_WORDS = re.compile(
    r"price target|\bPT\b|\b(?:up|down)graded\b|\b(?:up|down)grades?\s+(?:\S+\s+){0,4}to\b|"
    r"initiat\w* (?:coverage|at\b)|reiterat\w*|\boutperform\b|\boverweight\b|"
    r"\bunderweight\b|(?:buy|sell|hold|neutral) rating|"
    r"(?:raise|lift|boost|hike|cut|lower|trim|slash)(?:s|es|ed)? (?:\S+ ){0,3}targets?", re.I)
_HTML = re.compile(r"<[^>]+>")


def _plain(s: Any, n: int = 1500) -> str:
    import html as _html
    t = _html.unescape(_HTML.sub(" ", str(s or "")))
    return re.sub(r"\s+", " ", t).strip()[:n]


def bakeoff_system() -> str:
    """The system prompt, WITH the enum it refers to (a prompt that names a
    schema it never sends is the 2026-09-13 defect: 54% refusals)."""
    from backend.services import event_vocabulary as V
    ids = "\n".join(f"- {i}" for i in V.EVENT_TYPES)
    return (
        "You extract ONE structured event from one financial news document. Output "
        "exactly one JSON object with exactly these four keys and nothing else:\n"
        '{"ticker": "<the primary listed ticker the document is about, uppercase, no '
        'exchange prefix; null if none>", "event_type": "<one id from the list '
        'below>", "direction": <-1, 0 or 1 for that ticker>, "magnitude_bucket": '
        f'"<one of {", ".join(V.MAGNITUDE_BUCKETS)}>"}}\n'
        "Rules: event_type must be copied EXACTLY from the list; if nothing dated and "
        "decision-relevant about the company is reported, use no_event. direction is "
        "relative to that ticker only (an upgrade or a raised price target is +1, a "
        "downgrade or a cut target is -1). magnitude_bucket is the typical 1-2 session "
        "absolute move for an event of this type: NEGLIGIBLE <0.5%, SMALL 0.5-2%, "
        "MODERATE 2-5%, LARGE 5-10%, EXTREME >=10%. Do not invent facts the document "
        "does not state. No markdown, no prose.\n\n"
        f"The {len(V.EVENT_TYPES)} event_type ids:\n{ids}")


def bakeoff_user(item: dict) -> str:
    return (f"Document date: {item['document_date']}\nSource: {item['source']}\n"
            f"Title: {item['title']}\nBody (may be truncated): {item['body']}\n\n"
            "Output the JSON object only.")


def parse_extraction(text: str | None) -> tuple[dict | None, str | None]:
    """(parsed, refusal_reason). Out-of-enum values are a refusal, never coerced."""
    from backend.services import event_vocabulary as V
    if not text:
        return None, "EMPTY"
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, "UNPARSEABLE"
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None, "UNPARSEABLE"
    if not isinstance(d, dict):
        return None, "UNPARSEABLE"
    et = str(d.get("event_type") or "").strip()
    if et not in V.EVENT_TYPES:
        return None, f"SCHEMA:event_type={et[:40]!r}"
    try:
        di = int(d.get("direction"))
    except (TypeError, ValueError):
        return None, "SCHEMA:direction"
    if di not in (-1, 0, 1):
        return None, "SCHEMA:direction"
    mb = str(d.get("magnitude_bucket") or "").strip().upper()
    tk = d.get("ticker")
    return {"ticker": None if tk in (None, "", "null") else str(tk),
            "event_type": et, "direction": di,
            "magnitude_bucket": mb if mb in V.MAGNITUDE_BUCKETS else None}, None


_RULE_TICKER = [
    re.compile(r"\((?:NYSE|NASDAQ|Nasdaq|NYSE ?American|AMEX|OTC\w*|TSX|LSE)\s*[:\s]\s*"
               r"([A-Z][A-Z0-9.]{0,6})\)"),
    re.compile(r"\$([A-Z]{1,5})\b"),
    re.compile(r"\(([A-Z]{1,5})\)"),
]


def rules_arm(item: dict) -> dict:
    """The $0 baseline every model must beat: regexes, no reading."""
    txt = f"{item['title']} {item['body']}"
    tk = None
    for rx in _RULE_TICKER:
        m = rx.search(txt)
        if m:
            tk = m.group(1)
            break
    low = txt.lower()
    if "price target" in low or re.search(r"\bpt\b", low):
        et = "analyst_target_change"
    elif "upgrad" in low or "downgrad" in low:
        et = "analyst_rating_change"
    elif re.search(r"initiat\w* (coverage|at)", low):
        et = "analyst_initiation"
    elif re.search(r"earnings|quarterly results|\bq[1-4]\b.*results|eps", low):
        et = "earnings_report"
    elif re.search(r"acquir|merger|to buy\b|takeover", low):
        et = "mergers_acquisitions"
    elif "guidance" in low or "outlook" in low:
        et = "guidance_change"
    elif "dividend" in low:
        et = "regular_dividend_declaration"
    else:
        et = "no_event"
    up = len(re.findall(r"upgrad|raise|boost|lift|beat|surge|jump|outperform|overweight", low))
    dn = len(re.findall(r"downgrad|lower|cut|trim|miss|plunge|fall|underperform|underweight", low))
    return {"ticker": tk, "event_type": et, "direction": (up > dn) - (dn > up),
            "magnitude_bucket": "SMALL"}


def _norm_tk(x: Any) -> str:
    s = str(x or "").upper().strip().lstrip("$")
    s = s.split(":")[-1].strip()
    return s


def grade_extraction(pred: dict | None, item: dict) -> dict:
    """Per-field correctness (True/False/None=ungraded). A refusal is wrong on
    every graded field -- a model that answers nothing is not accurate."""
    gold = item["gold"]
    tks = {_norm_tk(t) for t in item.get("tickers") or []}
    tks |= {t.split(".")[0] for t in tks}
    out: dict[str, Any] = {"ticker": False, "event_type": False,
                           "direction": None if gold.get("direction") in (None, 0) else False}
    if pred is None:
        return out
    ptk = _norm_tk(pred.get("ticker"))
    out["ticker"] = bool(ptk) and (ptk in tks or ptk.split(".")[0] in tks)
    et = pred.get("event_type")
    out["event_type"] = (et in ANALYST_TYPES) if gold["stratum"] == "matched" \
        else (et not in ANALYST_TYPES)
    if out["direction"] is not None:
        out["direction"] = int(pred.get("direction") or 0) == int(gold["direction"])
    out["invented_analyst"] = (gold["stratum"] == "unmatched" and et in ANALYST_TYPES)
    return out


def bakeoff_sample(*, n: int | None = None, n_matched: int | None = None,
                   seen_max: str | None = None, seed: int = 20260926,
                   corpus_dir: Path | None = None, revisions=None,
                   root: Path | None = None) -> tuple[list[dict], dict]:
    """(items, census). Deterministic under `seed`; archive rows excluded."""
    import random

    import pandas as pd
    from backend.services import news_registry as NR
    n = int(n or getattr(_cfg, "MODEL_ROUTING_BAKEOFF_N", 240))
    n_matched = int(n_matched if n_matched is not None
                    else getattr(_cfg, "MODEL_ROUTING_BAKEOFF_N_MATCHED", 180))
    seen_max = str(seen_max or getattr(_cfg, "MODEL_ROUTING_BAKEOFF_SEEN_MAX", "2026-09-20"))
    after = int(getattr(_cfg, "MODEL_ROUTING_BAKEOFF_SESSIONS_AFTER", 5))
    before = int(getattr(_cfg, "MODEL_ROUTING_BAKEOFF_DAYS_BEFORE", 2))
    root = root or ledger_dir()
    corpus_dir = Path(corpus_dir or root / "news_corpus")
    if revisions is None:
        revisions = pd.read_parquet(root / "analyst" / "target_revisions.parquet",
                                    columns=["ticker", "event_date", "target_action", "action"])
    rv = revisions.copy()
    rv["t"] = pd.to_datetime(rv["event_date"], errors="coerce").dt.normalize()
    rv = rv[rv["t"].notna()]
    ta = rv["target_action"].astype(str).str.lower()
    act = rv["action"].astype(str).str.lower()
    rv["sign"] = 0
    rv.loc[ta.str.startswith("rais"), "sign"] = 1
    rv.loc[ta.str.startswith("lower"), "sign"] = -1
    rv.loc[(rv["sign"] == 0) & (act == "up"), "sign"] = 1
    rv.loc[(rv["sign"] == 0) & (act == "down"), "sign"] = -1
    rv["ticker"] = rv["ticker"].astype(str).str.upper()
    by_t = {k: v for k, v in rv.groupby("ticker")}
    census = {"rows_read": 0, "after_seen_max": 0, "archive": 0, "no_ticker": 0,
              "matched_pool": 0, "unmatched_pool": 0, "neither": 0, "dupe_title": 0}
    matched, unmatched, seen_titles = [], [], set()
    for d in sorted(p for p in corpus_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for f in sorted(d.glob("*.jsonl")):
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    census["rows_read"] += 1
                    fs = str(r.get("first_seen_utc") or "")[:10]
                    if not fs or fs > seen_max:
                        census["after_seen_max"] += 1
                        continue
                    g = NR.grade_row(r)
                    if g.get("pit_grade") == NR.ARCHIVE_GRADE:
                        census["archive"] += 1
                        continue
                    tickers = [str(x).upper() for x in (r.get("tickers") or []) if x]
                    if not tickers:
                        census["no_ticker"] += 1
                        continue
                    title = _plain(r.get("title"), 300)
                    if not title or title.lower() in seen_titles:
                        census["dupe_title"] += 1
                        continue
                    pub = str(r.get("published_utc") or fs)[:10]
                    lo = pd.Timestamp(pub) - pd.Timedelta(days=before)
                    hi = pd.Timestamp(fs) + pd.offsets.BDay(after)
                    body = _plain(r.get("body"))
                    kw = bool(_ANALYST_WORDS.search(f"{title} {body[:400]}"))
                    signs, anyrev = [], False
                    for t in tickers:
                        x = by_t.get(t)
                        if x is None:
                            continue
                        w = x[(x["t"] >= lo) & (x["t"] <= hi)]
                        anyrev = anyrev or len(w) > 0
                        signs += [int(s) for s in w["sign"] if s != 0]
                    item = {"source": d.name, "raw_id": r.get("raw_id") or r.get("url"),
                            "first_seen_utc": r.get("first_seen_utc"),
                            "published_utc": r.get("published_utc"),
                            "document_date": pub, "title": title, "body": body,
                            "tickers": tickers, "window": [str(lo.date()), str(hi.date())]}
                    if kw and signs:
                        net = sum(signs)
                        item["gold"] = {"stratum": "matched", "n_revisions": len(signs),
                                        "direction": (net > 0) - (net < 0)}
                        matched.append(item)
                    elif not kw and not anyrev:
                        item["gold"] = {"stratum": "unmatched", "n_revisions": 0,
                                        "direction": None}
                        unmatched.append(item)
                    else:
                        census["neither"] += 1
                        continue
                    seen_titles.add(title.lower())
    census["matched_pool"], census["unmatched_pool"] = len(matched), len(unmatched)
    rng = random.Random(seed)
    k_m = min(n_matched, len(matched))
    k_u = min(n - k_m, len(unmatched))
    items = rng.sample(matched, k_m) + rng.sample(unmatched, k_u)
    for i, it in enumerate(items):
        it["item_id"] = f"{BAKEOFF_ID}-{i:03d}"
    census.update(seed=seed, n=len(items), n_matched=k_m, n_unmatched=k_u,
                  by_source={s: sum(1 for x in items if x["source"] == s)
                             for s in sorted({x["source"] for x in items})})
    return items, census


def _arm_call(arm: str, item: dict, system: str, call_fn) -> dict:
    t0 = time.perf_counter()
    if arm == "rules":
        pred = rules_arm(item)
        return {"arm": arm, "model": "rules:v1", "status": "OK", "cost_usd": 0.0,
                "cost_status": "LISTED", "latency_s": round(time.perf_counter() - t0, 4),
                "pred": pred, "refusal": None, "raw": None}
    r = _call(arm, system, bakeoff_user(item), purpose=f"bakeoff:{BAKEOFF_ID}:{arm}",
              call_fn=call_fn, max_tokens=150, temperature=0.0,
              ensure_reason=f"bakeoff:{BAKEOFF_ID}",
              validate=lambda txt: parse_extraction(txt)[0] is not None)
    pred, why = (parse_extraction(r.get("text")) if r.get("ok")
                 else (None, str(r.get("status"))))
    return {"arm": arm, "model": r.get("served_model") or r.get("model"),
            "requested_model": r.get("model"), "status": r.get("status"),
            "cost_usd": r.get("cost_usd"), "cost_status": r.get("cost_status"),
            "latency_s": r.get("latency_s"), "n_429": r.get("n_429"),
            "pred": pred, "refusal": why, "raw": (r.get("text") or "")[:300] or None,
            "error": r.get("error")}


_NO_WIRE = frozenset({"LOCAL_UNAVAILABLE", "NOT_CONFIGURED", "BUDGET_REFUSED",
                      "BUDGET_CAP", "UNKNOWN_PROVIDER"})


def _summarise(rows: list[dict], arms: tuple[str, ...]) -> dict:
    out = {}
    for a in arms:
        rs = [x for x in rows if x["arm"] == a]
        if not rs:
            continue
        g = [x["grade"] for x in rs]
        fields = [v for gg in g for k, v in gg.items()
                  if k in ("ticker", "event_type", "direction") and v is not None]
        lat = sorted(float(x["latency_s"]) for x in rs if x.get("latency_s") is not None)
        # a row that never reached the wire (no key, no server, cap) cost $0;
        # only a wire attempt with no usage is UNPRICED
        costs = [0.0 if x.get("cost_usd") is None and x.get("status") in _NO_WIRE
                 else x.get("cost_usd") for x in rs]
        n_un = sum(1 for x in rs if x["item_stratum"] == "unmatched")

        def acc(k):
            v = [gg[k] for gg in g if gg.get(k) is not None]
            return round(sum(v) / len(v), 4) if v else None
        out[a] = {"n": len(rs),
                  "models_seen": sorted({str(x.get("model")) for x in rs}),
                  "field_accuracy": round(sum(fields) / len(fields), 4) if fields else None,
                  "ticker_acc": acc("ticker"), "event_type_acc": acc("event_type"),
                  "direction_acc": acc("direction"),
                  "n_direction_graded": sum(1 for gg in g if gg.get("direction") is not None),
                  "invented_analyst_rate": (round(sum(1 for gg in g if gg.get("invented_analyst"))
                                                  / n_un, 4) if n_un else None),
                  "refusal_rate": round(sum(1 for x in rs if x["pred"] is None) / len(rs), 4),
                  "refusals_by_reason": {k: sum(1 for x in rs if x["refusal"] == k)
                                         for k in sorted({str(x["refusal"]) for x in rs
                                                          if x["pred"] is None})},
                  "cost_usd": (None if any(c is None for c in costs)
                               else round(sum(costs), 6)),
                  "n_unpriced": sum(1 for c in costs if c is None),
                  "latency_median_s": lat[len(lat) // 2] if lat else None,
                  "latency_p90_s": lat[int(len(lat) * 0.9)] if lat else None,
                  "n_429": sum(int(x.get("n_429") or 0) for x in rs)}
    # NVIDIA as an adjudicator: on the items where it disagrees with DeepSeek's
    # event_type, how often is NVIDIA the one that is right?
    by_item: dict[str, dict] = {}
    for x in rows:
        by_item.setdefault(x["item_id"], {})[x["arm"]] = x
    dis = [(v["deepseek"], v["nvidia"]) for v in by_item.values()
           if "deepseek" in v and "nvidia" in v and v["deepseek"]["pred"] and v["nvidia"]["pred"]
           and v["deepseek"]["pred"]["event_type"] != v["nvidia"]["pred"]["event_type"]]
    both = sum(1 for v in by_item.values() if "deepseek" in v and "nvidia" in v
               and v["deepseek"]["pred"] and v["nvidia"]["pred"])
    out["_nvidia_vs_deepseek"] = {
        "n_both_answered": both, "n_event_type_disagree": len(dis),
        "nvidia_right_on_disagreements": (round(sum(1 for _, nv in dis if nv["grade"]["event_type"])
                                                / len(dis), 4) if dis else None),
        "rule": "NVIDIA stays adjudicator only if right on > 50% of disagreements"}
    return out


def run_bakeoff(items: list[dict], *, arms: tuple[str, ...] = BAKEOFF_ARMS, call_fn=None,
                out_path: Path | None = None, cap_usd: float | None = None,
                flush_every: int | None = None, census: dict | None = None,
                nvidia_gap_s: float | None = None, stop_local: Callable[[], dict] | None = None,
                ) -> dict:
    """Four arms over the SAME items; a receipt flushed every `flush_every` rows
    with the wire `system` captured on the FIRST flush. DeepSeek stops at the
    cap (remaining rows say BUDGET_CAP -- a refusal, not a zero). Arms run in
    parallel threads; the local server is stopped by PID at the end."""
    import threading
    system = bakeoff_system()
    from backend.services import llm_language as _lang
    wire_system = _lang.pin(system) if hasattr(_lang, "pin") else system
    cap = float(cap_usd if cap_usd is not None else getattr(_cfg, "MODEL_ROUTING_BAKEOFF_CAP_USD", 0.15))
    every = int(flush_every or getattr(_cfg, "MODEL_ROUTING_BAKEOFF_FLUSH_EVERY", 20))
    gap = float(nvidia_gap_s if nvidia_gap_s is not None
                else getattr(_cfg, "MODEL_ROUTING_BAKEOFF_NVIDIA_MIN_GAP_S", 2.0))
    out_path = Path(out_path or receipt_dir() / f"bakeoff_{BAKEOFF_ID}_{date.today()}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    lock = threading.Lock()
    spent = {"deepseek": 0.0}
    state = {"flushes": 0, "started_utc": _now()}

    def doc(final: bool) -> dict:
        return {"receipt": "model_routing_bakeoff", "bakeoff": BAKEOFF_ID,
                "schema": "model_routing_bakeoff/1", "licence": "PRODUCT_EXPERIMENT",
                "state": "DONE" if final else "RUNNING", "started_utc": state["started_utc"],
                "updated_utc": _now(), "cap_usd": cap, "spent_deepseek_usd": round(spent["deepseek"], 6),
                "arms": list(arms), "n_items": len(items), "n_rows": len(rows),
                "system": wire_system, "system_sha256": _sha(wire_system),
                "user_template_example": bakeoff_user(items[0]) if items else None,
                "gold_rule": ("matched: analyst words + a raise/lower for a tagged ticker in "
                              "[published-2d, first_seen+5 sessions] -> analyst_* family, "
                              "direction = sign(net); unmatched: no analyst words, no revision "
                              "of any kind -> not analyst_*; ticker: one of the tagged tickers"),
                "census": census, "summary": _summarise(rows, arms),
                "rows": rows}

    def flush(final: bool = False) -> None:
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc(final), indent=1, default=str), encoding="utf-8")
        tmp.replace(out_path)
        state["flushes"] += 1

    def add(item: dict, res: dict) -> None:
        res["item_id"] = item["item_id"]
        res["item_stratum"] = item["gold"]["stratum"]
        res["grade"] = grade_extraction(res["pred"], item)
        with lock:
            rows.append(res)
            if len(rows) % every == 0:
                flush()

    def worker(arm: str) -> None:
        last = 0.0
        for it in items:
            if arm == "deepseek":
                with lock:
                    over = spent["deepseek"] >= cap
                if over:
                    add(it, {"arm": arm, "model": None, "status": "BUDGET_CAP", "cost_usd": 0.0,
                             "cost_status": "LISTED", "latency_s": None, "pred": None,
                             "refusal": "BUDGET_CAP", "raw": None})
                    continue
            if arm == "nvidia" and gap > 0:
                wait = last + gap - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                last = time.monotonic()
            try:
                res = _arm_call(arm, it, system, call_fn)
            except Exception as exc:                                # noqa: BLE001
                res = {"arm": arm, "model": None, "status": "ERROR", "cost_usd": None,
                       "cost_status": None, "latency_s": None, "pred": None,
                       "refusal": "ERROR", "raw": None, "error": f"{type(exc).__name__}: {exc}"[:200]}
            if arm == "deepseek" and res.get("cost_usd") is not None:
                with lock:
                    spent["deepseek"] += float(res["cost_usd"])
            add(it, res)

    flush()                                     # the system prompt is on disk before any call
    threads = [threading.Thread(target=worker, args=(a,), name=f"bakeoff-{a}") for a in arms]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    local_stop = None
    if "local" in arms:
        local_stop = (stop_local or _stop_local_server)()
    d = doc(True)
    d["local_server_after"] = local_stop
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    tmp.replace(out_path)
    return {"path": str(out_path), "summary": d["summary"], "n_rows": len(rows),
            "spent_deepseek_usd": d["spent_deepseek_usd"], "local_server_after": local_stop}


def _sha(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _stop_local_server() -> dict:
    """Stop the server BY PID if Aegis started it, and prove it is down."""
    from backend.services import llama_server as LS
    before = LS.status()
    r = LS.stop(allow_foreign=False) if before.get("started_by_aegis") else {
        "ok": not before.get("listening"), "action": "none" if not before.get("listening")
        else "refused_foreign", "pid": before.get("pid")}
    pid = before.get("pid") or r.get("pid")
    after = LS.status()
    return {"pid": pid, "stop": {k: r.get(k) for k in ("ok", "action", "pid", "escalated_to_force")},
            "listening_after": after.get("listening"),
            "pid_alive_after": bool(pid) and LS.pid_alive(int(pid))}


def bakeoff_table(receipt: dict) -> list[str]:
    s = receipt.get("summary") or {}
    lines = []
    for a in receipt.get("arms") or []:
        x = s.get(a)
        if not x:
            continue
        cost = "UNPRICED" if x.get("cost_usd") is None else f"${float(x['cost_usd']):.4f}"
        acc = x.get("field_accuracy")
        lines.append(f"`{a}` acc {'-' if acc is None else f'{acc * 100:.1f}%'} "
                     f"(tk {_p(x.get('ticker_acc'))} ev {_p(x.get('event_type_acc'))} "
                     f"dir {_p(x.get('direction_acc'))}) · refuse {_p(x.get('refusal_rate'))} · "
                     f"{cost} · p50 {x.get('latency_median_s')}s")
    return lines


def _p(x: Any) -> str:
    return "-" if x is None else f"{float(x) * 100:.0f}%"


def compare_text(ticker: str | None = None, *, root: Path | None = None) -> str:
    """`/compare [T]`: READ-ONLY. The latest E-G1 table (and T's items in it)."""
    rd = receipt_dir(root)
    p = _latest(rd, f"bakeoff_{BAKEOFF_ID}_*.json") if rd.exists() else None
    d = _load(p)
    if not d:
        return (f"*Compare* -- CANNOT DETERMINE: no `model_routing/bakeoff_{BAKEOFF_ID}_*.json`. "
                f"The bake-off is a batch: `python -m scripts.bakeoff_eg1`.")
    lines = [f"*Compare* = extraction bake-off {BAKEOFF_ID} (`{p.name}`, {d.get('state')}, "
             f"{d.get('n_items')} items, graded vs analyst revisions)"] + bakeoff_table(d)
    nv = (d.get("summary") or {}).get("_nvidia_vs_deepseek") or {}
    if nv:
        lines.append(f"NVIDIA vs DeepSeek: {nv.get('n_event_type_disagree')} event disagreements, "
                     f"NVIDIA right on {_p(nv.get('nvidia_right_on_disagreements'))}")
    if ticker:
        t = str(ticker).upper()
        ids = {it for it in {r.get("item_id") for r in d.get("rows") or []}}
        mine = [r for r in d.get("rows") or [] if r.get("item_id") in ids
                and t in str((r.get("pred") or {}).get("ticker") or "").upper()]
        lines.append(f"{t}: {len(mine)} answers name it in this bake-off")
    lines.append("_direction is not asked: held-out direction skill is -7.9%. Magnitude is "
                 "the forward test in u_forecast._")
    return "\n".join(lines)


# ─────────────────────────────── the daily digest hook ──────────────────────

def grade_promises_daily(*, today: date | None = None, root: Path | None = None,
                         runner: Callable[[], dict] | None = None) -> dict:
    """Run `source_reads --grade-promises` once per UTC day from
    MODEL_ROUTING_GRADE_PROMISES_FROM on; one receipt line per day.

    Nothing graded promises after 2026-09-30 (G-fix task 6). The stamp file
    makes it once per UTC day however often the digest fires; a failure is a
    receipt line, never a raise into the bot loop.
    """
    today = today or datetime.now(timezone.utc).date()
    start = str(getattr(_cfg, "MODEL_ROUTING_GRADE_PROMISES_FROM", "2026-09-30"))
    rd = receipt_dir(root)
    rd.mkdir(parents=True, exist_ok=True)
    log = rd / "grade_promises_daily.jsonl"
    if str(today) < start:
        return {"action": "skip", "reason": f"before {start}", "day": str(today)}
    done = set()
    if log.exists():
        for ln in log.read_text(encoding="utf-8").splitlines():
            try:
                x = json.loads(ln)
            except ValueError:
                continue
            if x.get("state") in ("OK", "REFUSED"):
                done.add(x.get("day"))
    if str(today) in done:
        return {"action": "skip", "reason": "already ran today", "day": str(today)}
    t0 = time.perf_counter()
    try:
        if runner is None:
            from scripts import source_reads as SRD
            res = SRD.run_grade_promises(None)
        else:
            res = runner()
        row = {"day": str(today), "at": _now(), "state": "OK",
               "elapsed_s": round(time.perf_counter() - t0, 2),
               "result": {k: v for k, v in (res or {}).items()
                          if isinstance(v, (int, float, str, bool)) or v is None}}
    except Exception as exc:                                       # noqa: BLE001
        row = {"day": str(today), "at": _now(), "state": "ERROR",
               "elapsed_s": round(time.perf_counter() - t0, 2),
               "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return {"action": "ran", **row, "receipt": str(log)}


def route(cmd: str, args: list[str], *, call_fn=None, quest_fn=None,
          root: Path | None = None, llama_status=None) -> str:
    """The dispatcher the Telegram agent calls. Deterministic commands never
    touch `call_fn`; `/research` and `/compare` are evidence reads."""
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
        tick = [a for a in args if not a.startswith("--")]
        if not tick:
            return "Usage: `/research <ticker> [--quest]`"
        kw = {"root": root} if root is not None else {}
        return research(tick[0], quest="--quest" in args, quest_fn=quest_fn, **kw)[0]
    if cmd == "compare":
        return compare_text(args[0] if args else None, root=root)
    raise KeyError(f"no route for /{cmd}")


__all__ = ["ROUTES", "DETERMINISTIC", "route", "ask", "deep", "research", "evidence",
           "evidence_text", "compare_text", "bakeoff_sample", "run_bakeoff", "bakeoff_system",
           "parse_extraction", "rules_arm", "grade_extraction", "grade_promises_daily",
           "nav_text", "status_text", "books_text", "forecasts_text", "footer",
           "deep_provider"]
