"""One event, end to end (ROADMAP CH-31): SENSE -> UNIVERSE -> DECIDE -> ACT -> LEARN.

    python -m scripts.one_event list  --data-root <optimus dir> [--hours 48]
    python -m scripts.one_event run   --data-root <optimus dir> --source <corpus dir> --key <raw_id|url|accession>
    python -m scripts.one_event grade --out <dir> --data-root <optimus dir>

WHAT THIS IS
============
The acceptance test of the loop in ROADMAP §2: one real, dated event is taken
through every module and a single receipt says, per stage, SUCCESS / DEGRADED /
BLOCKED with a reason and the path of the evidence it read. It does not invent
a new decision system. Each stage calls what already exists:

    SENSE     the stored corpus row (`news_corpus/<source>/<day>.jsonl`): public
              timestamp, source, url; direction only from a TYPED digest row
              (`_digest_cache/extract_wd_v1.jsonl`) or an operator flag, never guessed
    UNIVERSE  `backend.services.universe_graph` (CH-30). The graph is read from
              `--graph-dir`, else `<data-root>/universe_graph` (the same dir
              `config.UNIVERSE_GRAPH_DIR` names for the default data root), so a
              worktree pointed at the runtime's data reads the runtime's graph.
              Imported lazily: a checkout without the module is DEGRADED with that
              reason rather than crashing; a missing / stale build is DEGRADED red
    DECIDE    the latest broker-truth positions receipt (`pc_book/state_latest.json`),
              the funnel snapshot, `owner_event_warning.build_warning` for a held
              earnings 8-K, the graph's `holdings_exposure` / `owner_warnings` /
              `funnel_candidates`; and, read from code, the fact that the plan
              does not read news (`expected_return.NOT_READ_BY_DESIGN`,
              `config.NEWS_TILT_IN_PLAN`). A reasoned no-trade is a valid decision
    ACT       a DRY-RUN intent: the alert / funnel addition / order that WOULD be
              produced. Nothing is sent. BLOCKED "ATTENDED_ACTIVATION_REQUIRED" is
              the intended, honest status (no LLM or code path holds authority)
    LEARN     frozen forecast rows (h = 1 and 5 sessions, market-adjusted vs SPY)
              appended to `<out>/forecasts.jsonl` BEFORE any outcome exists, and
              `grade()` that prices them on bars when their horizon has passed.
              Every row carries `written_utc`, the REAL wall clock (`_wall_clock`,
              never `--now`). A row whose simulated `made_at` differs from it by
              more than `ONE_EVENT_REPLAY_TOLERANCE_S` is `replay: true` and is
              never graded as forward evidence; the grader also refuses a row with
              no real write time, or one written after its entry close

The five ids (event_id -> universe_id -> decision_id -> intent_id ->
forecast_ids) are linked on one receipt. Exit code 2 when any stage is BLOCKED
for a reason that is not the intended one. No LLM call, no network, no order.
PRODUCT_EXPERIMENT licence; nothing here is a skill claim.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from backend import config as _cfg

SUCCESS, DEGRADED, BLOCKED = "SUCCESS", "DEGRADED", "BLOCKED"
STAGES = ("SENSE", "UNIVERSE", "DECIDE", "ACT", "LEARN")
#: The only BLOCKED reason that does not turn the exit code red: activation of
#: an alert or order is the owner's, attended, by design.
INTENDED_BLOCKS = frozenset({"ATTENDED_ACTIVATION_REQUIRED"})
NY = ZoneInfo("America/New_York")
SCHEMA = "one-event/1"


def _wall_clock() -> datetime:
    """The real UTC write time. `--now` never reaches it (review 2, S65, B1): a
    simulated clock may choose which corpus rows are visible, never when a
    forecast was frozen. Tests monkeypatch this function, nothing else does."""
    return datetime.now(timezone.utc)


# ─────────────────────────────── small helpers ───────────────────────────────

def _sha(*parts: Any, n: int = 16) -> str:
    h = hashlib.sha256("\x1f".join(json.dumps(p, sort_keys=True, default=str)
                                   for p in parts).encode("utf-8"))
    return h.hexdigest()[:n]


def _utc(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(timezone.utc)


def _jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
    except FileNotFoundError:
        return []
    return out


@dataclass
class Stage:
    name: str
    status: str
    reason: str
    stage_id: Optional[str] = None
    evidence: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    @property
    def intended(self) -> bool:
        return self.status == BLOCKED and self.reason in INTENDED_BLOCKS

    def to_dict(self) -> dict:
        d = asdict(self)
        d["intended_block"] = self.intended
        return d


# ─────────────────────────────────── SENSE ───────────────────────────────────

def _items_of(row: dict) -> list[str]:
    return sorted({t.split(":", 1)[1] for t in (row.get("entity_tags") or [])
                   if isinstance(t, str) and t.startswith("8-K:")})


def _accession_of(row: dict) -> Optional[str]:
    for t in row.get("entity_tags") or []:
        if isinstance(t, str) and t.startswith("accession:"):
            return t.split(":", 1)[1]
    rid = str(row.get("raw_id") or "")
    return rid.split(":", 1)[0] if rid.count("-") == 2 and ":" in rid else None


def corpus_days(now: datetime, hours: float) -> list[str]:
    start = (now - timedelta(hours=hours)).date()
    n = (now.date() - start).days
    return [str(start + timedelta(days=i)) for i in range(n + 2)]


def list_events(data_root: Path, *, now: datetime, hours: float = 48.0,
                sources: Optional[Iterable[str]] = None) -> list[dict]:
    """Every stored corpus row published in the window that names >= 1 ticker."""
    base = Path(data_root) / "news_corpus"
    srcs = list(sources) if sources else sorted(
        p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("_")) \
        if base.exists() else []
    since = now - timedelta(hours=hours)
    out = []
    for s in srcs:
        for day in corpus_days(now, hours):
            p = base / s / f"{day}.jsonl"
            for r in _jsonl(p):
                pub = _utc(r.get("published_utc"))
                if pub is None or not (since <= pub <= now) or not r.get("tickers"):
                    continue
                out.append({"source": s, "path": str(p), "published_utc": pub.isoformat(),
                            "tickers": r.get("tickers"), "title": str(r.get("title") or "")[:160],
                            "key": r.get("raw_id") or r.get("url"), "items": _items_of(r)})
    out.sort(key=lambda r: r["published_utc"], reverse=True)
    return out


def find_event(data_root: Path, source: str, key: str, *, now: datetime,
               hours: float = 96.0) -> tuple[Optional[dict], Optional[str]]:
    """The stored row whose raw_id, url or accession equals `key` (newest file first)."""
    base = Path(data_root) / "news_corpus" / source
    for day in reversed(corpus_days(now, hours)):
        p = base / f"{day}.jsonl"
        for r in _jsonl(p):
            if key in (r.get("raw_id"), r.get("url"), _accession_of(r)):
                return r, str(p)
    return None, None


def typed_direction(data_root: Path, url: Optional[str], ticker: Optional[str], *,
                    min_abs_sentiment: float = 0.2) -> Optional[dict]:
    """The world digest's TYPED extraction of this item, when one exists.

    Direction is the sign of the typed `sentiment` when |sentiment| >= the floor
    and the row names the ticker; otherwise None (never guessed from text here).
    """
    if not url:
        return None
    p = Path(data_root) / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl"
    if not p.exists():
        return None
    needle = json.dumps(url)[1:-1]
    hit = None
    with open(p, encoding="utf-8") as fh:
        for ln in fh:
            if needle not in ln:
                continue
            try:
                row = json.loads(ln).get("row") or {}
            except ValueError:
                continue
            if row.get("url") == url:
                hit = row
    if hit is None:
        return None
    s = hit.get("sentiment")
    names = set(hit.get("tickers") or [])
    unverified = set(hit.get("tickers_unverified") or [])
    # The digest verifies a ticker as the SUBJECT only through a narrow title
    # grammar and never for primary (SEC) sources, so most rows carry the name in
    # `tickers_unverified`. Accept it there too, and say so: the caller degrades.
    verified = ticker is None or ticker in names
    named = verified or ticker in unverified
    d = None
    if isinstance(s, (int, float)) and math.isfinite(s) and abs(s) >= min_abs_sentiment and named:
        d = 1 if s > 0 else -1
    return {"direction": d, "sentiment": s, "event_type": hit.get("event_type"),
            "tickers": sorted(names), "tickers_unverified": sorted(unverified),
            "ticker_verified": bool(verified), "topic": str(hit.get("topic") or "")[:160],
            "extract_model": hit.get("extract_model"),
            "provenance": hit.get("provenance"), "cache_path": str(p)}


def sense(row: Optional[dict], path: Optional[str], *, source: str, key: str, now: datetime,
          data_root: Path, ticker: Optional[str] = None, direction: Optional[int] = None,
          max_age_hours: float = 72.0) -> tuple[Stage, Optional[dict]]:
    if row is None:
        return Stage("SENSE", BLOCKED, "EVENT_NOT_FOUND", data={"source": source, "key": key}), None
    pub = _utc(row.get("published_utc"))
    seen = _utc(row.get("first_seen_utc"))
    if pub is None or pub > now:
        return Stage("SENSE", BLOCKED, "NO_VALID_PUBLIC_TIMESTAMP", evidence=[path or ""],
                     data={"published_utc": row.get("published_utc")}), None
    tickers = [t for t in (row.get("tickers") or []) if isinstance(t, str)]
    reasons = []
    t_src = "corpus_row"
    if ticker:
        if ticker not in tickers:
            t_src = "operator"
            reasons.append("TICKER_FROM_OPERATOR")
        primary = ticker
    elif len(tickers) == 1:
        primary = tickers[0]
    elif tickers:
        primary = tickers[0]
        reasons.append("MULTIPLE_TICKERS_FIRST_TAKEN")
    else:
        primary = None
        reasons.append("NO_TICKER_RESOLVED")
    typed = typed_direction(data_root, row.get("url"), primary)
    if direction is not None:
        d, d_src = int(direction), "operator"
        reasons.append("DIRECTION_FROM_OPERATOR")
    elif typed and typed.get("direction"):
        d, d_src = int(typed["direction"]), "typed_digest_row"
        if not typed.get("ticker_verified"):
            reasons.append("TYPED_TICKER_UNVERIFIED")
    else:
        d, d_src = None, None
        reasons.append("DIRECTION_UNTYPED")
    age_h = (now - pub).total_seconds() / 3600.0
    if age_h > max_age_hours:
        reasons.append("STALE_EVENT")
    ev = {"source": source, "source_path": path, "key": key, "raw_id": row.get("raw_id"),
          "url": row.get("url"), "title": str(row.get("title") or "")[:240],
          "published_utc": pub.isoformat(), "first_seen_utc": seen.isoformat() if seen else None,
          "capture_lag_min": round((seen - pub).total_seconds() / 60.0, 1) if seen else None,
          "age_hours": round(age_h, 2), "tickers": tickers, "primary_ticker": primary,
          "ticker_source": t_src, "items": _items_of(row), "accession": _accession_of(row),
          "direction": d, "direction_source": d_src, "typed": typed,
          "body_sha": _sha(row.get("body") or "", n=20), "pit_grade": row.get("pit_grade")}
    ev["event_id"] = "ev_" + _sha(source, row.get("raw_id") or row.get("url"), ev["published_utc"])
    # every reason above is a degradation: SUCCESS means none applied
    status = DEGRADED if (reasons or primary is None) else SUCCESS
    ev_paths = [path or ""] + ([typed["cache_path"]] if typed else [])
    return Stage("SENSE", status, ";".join(reasons) or "OK", ev["event_id"], ev_paths,
                 {k: v for k, v in ev.items() if k != "typed"} | {"typed": typed}), ev


# ───────────────────────────────── UNIVERSE ──────────────────────────────────

def _graph_module():
    try:
        return importlib.import_module("backend.services.universe_graph"), None
    except ImportError as exc:
        return None, f"{type(exc).__name__}: {exc}"[:200]


def default_graph_dir(data_root: Path) -> Path:
    """`<data-root>/universe_graph`: where `universe_graph build` writes for that root.

    Derived from the data root (like the funnel and positions defaults), not from
    `config.UNIVERSE_GRAPH_DIR`, so `--data-root <runtime optimus>` from a worktree
    reads the runtime's graph and not the worktree's empty one. For the default
    data root the two are the same directory.
    """
    return Path(data_root) / "universe_graph"


def funnel_state(funnel_path: Path, *, now: datetime) -> dict:
    try:
        d = json.loads(Path(funnel_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"path": str(funnel_path), "ok": False, "error": type(exc).__name__,
                "tickers": [], "age_days": None, "stale": True}
    gen = _utc(d.get("generated_at"))
    age = (now - gen).total_seconds() / 86400.0 if gen else None
    limit = float(getattr(_cfg, "ONE_EVENT_FUNNEL_STALE_DAYS", 10))
    return {"path": str(funnel_path), "ok": True, "generated_at": d.get("generated_at"),
            "age_days": None if age is None else round(age, 2),
            "stale": age is None or age > limit, "stale_after_days": limit,
            "tickers": [c.get("ticker") for c in d.get("candidates") or [] if c.get("ticker")]}


def universe(ev: Optional[dict], *, now: datetime, graph_dir: Optional[Path],
             funnel_path: Path, top_k: int = 12) -> tuple[Stage, Optional[dict]]:
    if ev is None or not ev.get("primary_ticker"):
        return Stage("UNIVERSE", BLOCKED, "NO_RESOLVED_NODE_FROM_SENSE"), None
    t = ev["primary_ticker"]
    fun = funnel_state(funnel_path, now=now)
    uni: dict = {"node_ticker": t, "in_funnel": t in fun["tickers"],
                 "funnel": {k: v for k, v in fun.items() if k != "tickers"},
                 "funnel_size": len(fun["tickers"]), "graph": None, "implications": [],
                 "connected": [], "graph_skill_note": (
                     "CH-30 walk-forward check: graph sign does not beat a matched random control "
                     "(h1 50.20% vs 50.04%, h5 50.01% vs 50.15%); implications are CONTEXT, not "
                     "a forecast with skill")}
    evidence = [str(funnel_path)]
    UG, err = _graph_module()
    if UG is None:
        uni["graph"] = {"status": "MODULE_ABSENT", "error": err}
        uni["universe_id"] = "un_" + _sha(ev["event_id"], "no-graph", fun.get("generated_at"))
        return Stage("UNIVERSE", DEGRADED,
                     "GRAPH_MODULE_ABSENT: backend.services.universe_graph not importable on "
                     "this checkout (CH-30); node resolved against the funnel only",
                     uni["universe_id"], evidence, uni), uni
    st = UG.status(graph_dir, now=now)
    uni["graph"] = {k: st.get(k) for k in ("status", "red", "as_of", "age_days", "build_id",
                                             "counts", "dir", "line")}
    evidence.append(str(st.get("dir")))
    reasons = []
    if st.get("red"):
        reasons.append(f"GRAPH_{st.get('status')}")
        if st.get("status") in ("MISSING", "UNKNOWN"):
            uni["universe_id"] = "un_" + _sha(ev["event_id"], st.get("status"))
            return Stage("UNIVERSE", DEGRADED, ";".join(reasons), uni["universe_id"], evidence,
                         uni), uni
    g = UG.load_graph(graph_dir)
    nid = UG.company_id(t)
    uni["node_id"] = nid
    if nid not in g.nodes:
        reasons.append("NODE_NOT_IN_GRAPH (graph v1 holds the liquid top-N only)")
        uni["universe_id"] = "un_" + _sha(ev["event_id"], g.as_of, "no-node")
        return Stage("UNIVERSE", DEGRADED, ";".join(reasons), uni["universe_id"], evidence,
                     uni), uni
    d = ev.get("direction")
    conditional = d is None
    gev = {"node_id": nid, "direction": d if d else 1, "as_of": now.date().isoformat()}
    try:
        imps = UG.propagate(g, gev)
    except Exception as exc:                                         # noqa: BLE001
        reasons.append(f"PROPAGATE_REFUSED: {type(exc).__name__}: {exc}"[:200])
        uni["universe_id"] = "un_" + _sha(ev["event_id"], g.as_of, "refused")
        return Stage("UNIVERSE", DEGRADED, ";".join(reasons), uni["universe_id"], evidence,
                     uni), uni
    rows = [i.to_dict() for i in imps]
    uni["implications"] = rows[:top_k]
    uni["n_implications"] = len(rows)
    seen, conn = set(), []
    for r in rows:
        tgt = r.get("target")
        if tgt in seen:
            continue
        seen.add(tgt)
        conn.append({"target": tgt, "type": r.get("target_type"), "path": r.get("path"),
                     "confidence": r.get("confidence_label")})
    uni["connected"] = conn[:top_k]
    uni["graph_event"] = gev
    uni["direction_conditional"] = conditional
    if conditional:
        reasons.append("DIRECTION_UNKNOWN: implications computed for direction=+1; flip every "
                       "sign if the event is adverse")
    uni["universe_id"] = "un_" + _sha(ev["event_id"], g.as_of, gev)
    status = DEGRADED if reasons else SUCCESS
    return Stage("UNIVERSE", status, ";".join(reasons) or "OK", uni["universe_id"], evidence,
                 uni), uni


# ────────────────────────────────── DECIDE ───────────────────────────────────

def positions_receipt(path: Path, *, now: datetime) -> dict:
    """The broker-truth PC-PAPER positions. The account number is never copied."""
    try:
        snap = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "path": str(path), "error": type(exc).__name__}
    t = _utc(snap.get("t"))
    age_h = (now - t).total_seconds() / 3600.0 if t else None
    limit = float(getattr(_cfg, "ONE_EVENT_POSITIONS_STALE_HOURS", 24))
    pos = {}
    for p in snap.get("positions") or []:
        try:
            pos[str(p["symbol"])] = float(p["market_value"])
        except (KeyError, TypeError, ValueError):
            continue
    return {"ok": True, "path": str(path), "t": snap.get("t"),
            "age_hours": None if age_h is None else round(age_h, 2),
            "stale": age_h is None or age_h > limit or age_h < 0, "stale_after_hours": limit,
            "equity": snap.get("equity"), "positions": pos, "n_positions": len(pos)}


def _owner_warning_snapshot(pr: dict) -> str:
    """PC-PAPER snapshot in `owner_event_warning.build_warning`'s normalized schema."""
    return json.dumps({"lane": "PC-PAPER", "as_of": _utc(pr["t"]).isoformat(),
                       "equity_usd": float(pr["equity"]),
                       "positions": [{"ticker": k, "market_value_usd": v, "instrument": "equity",
                                      "leverage": 1} for k, v in sorted(pr["positions"].items())
                                     if v > 0]})


def _owner_warning_row(row: dict, ev: dict) -> Optional[str]:
    """The 8-K corpus row in build_warning's normalized schema (earnings only)."""
    if "2.02" not in (ev.get("items") or []) or not ev.get("accession"):
        return None
    return json.dumps({"ticker": ev["primary_ticker"], "form": "8-K", "exhibit": "EX-99.1",
                       "item": "2.02", "event_type": "earnings_results",
                       "accession": ev["accession"], "url": ev.get("url"),
                       "published_at": ev["published_utc"],
                       "captured_at": ev.get("first_seen_utc") or ev["published_utc"],
                       "body": row.get("body") or ""})


def plan_reads_news() -> dict:
    """What the existing decision code does with news, read from the code itself."""
    out: dict = {"news_tilt_in_plan": bool(getattr(_cfg, "NEWS_TILT_IN_PLAN", False))}
    try:
        from backend.services import expected_return as ER
        nr = getattr(ER, "NOT_READ_BY_DESIGN", {})
        out["expected_return_not_read"] = {k: v[:120] for k, v in nr.items()
                                           if k in ("source:", "news_digest:")}
    except Exception as exc:                                         # noqa: BLE001
        out["expected_return_not_read"] = f"unreadable: {type(exc).__name__}"
    out["line"] = ("the PC plan does not read news: E[r] excludes `source:` and `news_digest:` "
                   f"rows by design and NEWS_TILT_IN_PLAN={out['news_tilt_in_plan']}")
    return out


def decide(ev: Optional[dict], row: Optional[dict], uni: Optional[dict], *, now: datetime,
           positions_path: Path, graph_dir: Optional[Path]) -> tuple[Stage, Optional[dict]]:
    if ev is None or not ev.get("primary_ticker"):
        return Stage("DECIDE", BLOCKED, "NO_EVENT_NODE"), None
    t = ev["primary_ticker"]
    reasons, evidence = [], [str(positions_path)]
    pr = positions_receipt(positions_path, now=now)
    held = pr.get("positions", {}) if pr.get("ok") else {}
    equity = float(pr.get("equity") or 0) if pr.get("ok") else 0.0
    if not pr.get("ok"):
        reasons.append("NO_POSITIONS_RECEIPT")
    elif pr["stale"]:
        reasons.append(f"POSITIONS_STALE ({pr['age_hours']} h)")
    if uni and uni.get("funnel", {}).get("stale"):
        reasons.append(f"FUNNEL_STALE ({uni['funnel'].get('age_days')} d)")
    dec: dict = {"ticker": t, "plan_reads_news": plan_reads_news(),
                 "positions": {k: pr.get(k) for k in ("path", "t", "age_hours", "stale",
                                                       "n_positions", "equity")},
                 "held_direct": None, "held_connected": [], "owner_warning": None,
                 "graph_owner_warnings": [], "funnel": None, "actions": [], "why": []}
    if t in held:
        w = held[t] / equity if equity > 0 else None
        dec["held_direct"] = {"ticker": t, "market_value_usd": round(held[t], 2),
                              "weight": None if w is None else round(w, 5),
                              "conditional_loss_usd": {"5pct": round(held[t] * .05, 2),
                                                       "10pct": round(held[t] * .10, 2)}}
    # the existing 8-K owner-warning adapter, verbatim, on a held earnings 8-K
    if pr.get("ok") and row is not None and t in held:
        src = _owner_warning_row(row, ev)
        if src is not None:
            from backend.services import owner_event_warning as OEW
            art = OEW.build_warning(src, _owner_warning_snapshot(pr), now=now)
            dec["owner_warning"] = {k: art.get(k) for k in (
                "status", "reason", "ticker", "exposure_weight", "saved_exposure_usd",
                "conditional_loss_usd", "paper_decision", "forecast_status", "event_key")}
    # graph consumers (CH-30 report: the three exact calls)
    UG, _ = _graph_module()
    graph_ran = False
    if UG is not None and uni and uni.get("graph_event"):
        try:
            g = UG.load_graph(graph_dir)
            gev = [uni["graph_event"]]
            dec["held_connected"] = [
                {k: r.get(k) for k in ("ticker", "horizon", "expected_direction", "expected_size",
                                        "confidence_label", "path")}
                for r in UG.holdings_exposure(g, [h for h in held if h != t], gev)][:20]
            dec["graph_owner_warnings"] = [r.get("text") for r in UG.owner_warnings(
                g, [h for h in held if h != t], gev)][:10] if not uni.get(
                "direction_conditional") else []
            if uni.get("direction_conditional"):
                # a sign computed for direction=+1 on an event of unknown sign is
                # not a candidate reason; the exposure rows stay, labelled
                dec["held_connected_conditional_on_direction"] = True
                dec["funnel"] = {"graph_candidates": [],
                                 "note": "skipped: event direction unknown"}
            else:
                dec["funnel"] = {"graph_candidates": [
                    {k: r.get(k) for k in ("ticker", "expected_direction", "expected_size",
                                            "confidence_label", "path")}
                    for r in UG.funnel_candidates(g, gev, horizon=5, min_label="MEDIUM",
                                                  top_k=10)]}
            graph_ran = True
        except Exception as exc:                                     # noqa: BLE001
            reasons.append(f"GRAPH_CONSUMERS_FAILED: {type(exc).__name__}"[:120])
    elif UG is None:
        reasons.append("GRAPH_CONSUMERS_NOT_RUN: universe_graph not importable, so held "
                       "connected names were NOT checked")
    else:
        gst = ((uni or {}).get("graph") or {}).get("status") or "no graph event"
        reasons.append(f"GRAPH_CONSUMERS_NOT_RUN: UNIVERSE produced no graph event ({gst}), "
                       "so held connected names were NOT checked")
    dec["graph_consumers_ran"] = graph_ran
    gstat = (uni or {}).get("graph") or {}
    if graph_ran and gstat.get("red"):
        # review 3: consumers that ran on a STALE (red) graph are not a clean SUCCESS
        reasons.append(f"GRAPH_{gstat.get('status')}: consumers ran on a red graph")
    # the decision itself: a reasoned row, never silence
    acts, why = [], []
    if dec["owner_warning"] and dec["owner_warning"].get("status") == "PROVISIONAL":
        acts.append("OWNER_WARNING_DRAFT")
        why.append("held name filed an earnings 8-K; owner_event_warning built a PROVISIONAL "
                   "warning (HOLD_EXISTING / NO_NEW_BET / REVIEW_NEW_EVIDENCE)")
    elif dec["held_direct"]:
        acts.append("REVIEW_HOLDING")
        why.append(f"{t} is held ({dec['held_direct']['weight']} of equity)"
                   + (f"; owner_event_warning: {dec['owner_warning']['status']} "
                      f"{dec['owner_warning']['reason']}" if dec["owner_warning"] else
                      "; owner_event_warning covers earnings 8-Ks only"))
    if dec["graph_owner_warnings"]:
        acts.append("OWNER_WARNING_DRAFT_CONNECTED")
        why.append(f"{len(dec['graph_owner_warnings'])} adverse MEDIUM+ graph implication(s) "
                   "land on other held names")
    if not dec["held_direct"]:
        if uni and uni.get("in_funnel"):
            why.append(f"{t} is already in the funnel snapshot")
        else:
            acts.append("FUNNEL_CANDIDATE_PROPOSED")
            why.append(f"{t} is not held and not in the {uni.get('funnel_size') if uni else '?'}"
                       f"-name funnel; propose it as an event-sourced candidate "
                       f"(source=event:{ev['event_id']})")
    acts.append("NO_TRADE_REASONED")
    why.append("no order: no calibrated event forecast exists (news_digest trust is 0 by "
               "construction; the CH-30 graph sign does not beat a random control), and "
               + dec["plan_reads_news"]["line"])
    dec["actions"], dec["why"] = acts, why
    dec["decision_id"] = "de_" + _sha(ev["event_id"], (uni or {}).get("universe_id"), acts,
                                      pr.get("t"))
    status = DEGRADED if reasons else SUCCESS
    return Stage("DECIDE", status, ";".join(reasons) or "OK", dec["decision_id"], evidence,
                 dec), dec


# ──────────────────────────────────── ACT ────────────────────────────────────

def act(ev: Optional[dict], dec: Optional[dict]) -> tuple[Stage, Optional[dict]]:
    if ev is None or dec is None:
        return Stage("ACT", BLOCKED, "NO_DECISION"), None
    intents = []
    if "OWNER_WARNING_DRAFT" in dec["actions"] or "OWNER_WARNING_DRAFT_CONNECTED" in dec["actions"]:
        texts = ([f"{ev['primary_ticker']}: {ev['title'][:140]} ({ev['published_utc']}). "
                  "Paper posture HOLD_EXISTING / NO_NEW_BET / REVIEW_NEW_EVIDENCE."]
                 if "OWNER_WARNING_DRAFT" in dec["actions"] else []) + dec["graph_owner_warnings"]
        intents.append({"kind": "owner_alert", "channel": "telegram_bridge.send_owner_once",
                        "texts": texts[:5], "sent": False})
    if "REVIEW_HOLDING" in dec["actions"]:
        hd = dec["held_direct"]
        intents.append({"kind": "review_holding", "ticker": hd["ticker"],
                        "worst_case_usd_if_5pct": hd["conditional_loss_usd"]["5pct"],
                        "worst_case_usd_if_10pct": hd["conditional_loss_usd"]["10pct"],
                        "sent": False})
    if "FUNNEL_CANDIDATE_PROPOSED" in dec["actions"]:
        extra = [ev["primary_ticker"]] + [r["ticker"] for r in
                                          ((dec.get("funnel") or {}).get("graph_candidates") or [])]
        intents.append({"kind": "funnel_extra", "call": "opportunity_funnel.run(extra=...)",
                        "tickers": list(dict.fromkeys(extra))[:10],
                        "source_tag": f"event:{ev['event_id']}", "sent": False})
    intents.append({"kind": "order", "order": None, "worst_case_usd": 0.0,
                    "why": "NO_TRADE_REASONED: the decision produced no order", "sent": False})
    out = {"intents": intents, "dry_run": True,
           "intent_id": "in_" + _sha(dec["decision_id"], intents)}
    return Stage("ACT", BLOCKED, "ATTENDED_ACTIVATION_REQUIRED", out["intent_id"], [],
                 out), out


# ─────────────────────────────────── LEARN ───────────────────────────────────

def session_close(d: Any) -> Optional[datetime]:
    """The exchange calendar's real close for session `d` (UTC), early closes
    included (13:00 ET on half days); None when `d` is not a session. Raises
    when the calendar cannot be read: a 16:00 guess is the bug it replaces."""
    from backend.services import market_sessions as MS
    return MS.session_close_utc(d)


def entry_session(made_at: datetime, dates: list) -> Optional[Any]:
    """The first session whose REAL close (exchange calendar, half days at
    13:00 ET) is at or after `made_at`. A bar dated on a non-session is skipped."""
    for d in dates:
        close = session_close(d)
        if close is not None and close >= made_at:
            return d
    return None


def is_replay(made_at: datetime, written_at: datetime) -> bool:
    """True when the simulated `made_at` is not the real write time."""
    tol = float(getattr(_cfg, "ONE_EVENT_REPLAY_TOLERANCE_S", 300))
    return abs((written_at - made_at).total_seconds()) > tol


def forecast_rows(ev: dict, uni: Optional[dict], dec: dict, *, made_at: datetime,
                  written_at: Optional[datetime] = None,
                  horizons: Iterable[int] = (1, 5), max_connected: int = 8) -> list[dict]:
    """Frozen BEFORE any outcome. Direction None means 'no directional claim'
    (graded for size only); the graph's rows carry its own expected sign.

    `written_at` is the real wall clock (default `_wall_clock()`) and is sealed
    into the row. A replay row gets its own id, so it can never occupy the id a
    later forward run of the same event needs."""
    written_at = written_at or _wall_clock()
    replay = is_replay(made_at, written_at)
    targets = [{"ticker": ev["primary_ticker"], "role": "event_node",
                "predicted_direction": ev.get("direction"),
                "direction_source": ev.get("direction_source"), "expected_size": None,
                "confidence_label": None, "path": None}]
    seen = {ev["primary_ticker"]}
    for r in (uni or {}).get("implications") or []:
        if r.get("target_type") != "company":
            continue
        sym = str(r.get("target", "")).split(":", 1)[-1]
        if sym in seen or len(targets) > max_connected:
            continue
        seen.add(sym)
        cond = (uni or {}).get("direction_conditional")
        targets.append({"ticker": sym, "role": "graph_implication",
                        "predicted_direction": None if cond else r.get("expected_direction"),
                        "direction_source": None if cond else "universe_graph",
                        "expected_size": None if cond else r.get("expected_size"),
                        "confidence_label": r.get("confidence_label"), "path": r.get("path"),
                        "graph_horizon": r.get("horizon")})
    rows = []
    for tg in targets:
        for h in horizons:
            r = {"schema": "one-event-forecast/1", "event_id": ev["event_id"],
                 "decision_id": dec["decision_id"], "ticker": tg["ticker"], "role": tg["role"],
                 "horizon_sessions": int(h), "made_at": made_at.isoformat(timespec="seconds"),
                 "written_utc": written_at.isoformat(timespec="seconds"), "replay": replay,
                 "evidence": "REPLAY" if replay else "FORWARD",
                 "event_published_utc": ev["published_utc"],
                 "entry_rule": "close of the first session whose real XNYS close >= made_at",
                 "observable": "log-free simple return over h sessions after entry minus SPY's",
                 "benchmark": "SPY", "predicted_direction": tg["predicted_direction"],
                 "direction_source": tg["direction_source"], "expected_size": tg["expected_size"],
                 "confidence_label": tg["confidence_label"], "path": tg["path"],
                 "licence": "PRODUCT_EXPERIMENT", "skill_claim": "none"}
            r["forecast_id"] = "fc_" + (
                _sha(ev["event_id"], tg["ticker"], int(h)) if not replay
                else _sha(ev["event_id"], tg["ticker"], int(h), "replay", r["made_at"]))
            r["seal"] = _sha(r, n=24)
            rows.append(r)
    return rows


def append_forecasts(path: Path, rows: list[dict]) -> tuple[int, int]:
    """Append-only; a forecast id already present is never written twice. The
    de-duplication read happens under the same lock as the append, and each line
    is fsynced: a ledger that claims "frozen before" must survive a crash."""
    from backend.services import disk_guard as DG
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with DG.file_lock(path.with_name(path.name + ".lock")):        # re-entrant below
        have = {r.get("forecast_id") for r in _jsonl(path)}
        new = [r for r in rows if r["forecast_id"] not in have]
        for r in new:
            DG.locked_append_line(path, json.dumps(r, sort_keys=True), fsync=True)
    return len(new), len(rows) - len(new)


def bar_paths(data_root: Path) -> list[Path]:
    dr = Path(data_root)
    out = [p for p in (dr / "prices_2025_26" / "bars.parquet",
                       dr / "prices_deep" / "bars.parquet") if p.exists()]
    return out[:1]


def load_closes(paths: list[Path], symbols: Iterable[str]):
    import pandas as pd
    syms = sorted(set(symbols) | {"SPY"})
    frames = []
    for p in paths:
        try:
            frames.append(pd.read_parquet(p, columns=["symbol", "date", "close"],
                                          filters=[("symbol", "in", syms)]))
        except Exception:                                            # noqa: BLE001
            continue
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames).drop_duplicates(["symbol", "date"], keep="last")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.pivot(index="date", columns="symbol", values="close").sort_index()


def grade(forecasts_path: Path, *, data_root: Path, now: datetime,
          grades_path: Optional[Path] = None) -> dict:
    """Price every frozen row whose horizon has passed on the bars on disk.

    PENDING when the bars do not reach entry + h sessions; UNGRADEABLE when the
    ticker or SPY has no bars. A grade row is written once per forecast id.

    Refused, never graded (review 2, S65, B1): NO_WRITE_TIME (no real
    `written_utc`, so the freeze cannot be proven), REPLAY (a `--now` row),
    FROZEN_LATE (the entry close -- the calendar's real close, 13:00 ET on a
    half day -- is not after the real write time) and SEAL_MISMATCH (the row
    was edited after it was sealed; review 3).
    """
    rows = _jsonl(Path(forecasts_path))
    gp = Path(grades_path) if grades_path else Path(forecasts_path).with_name("grades.jsonl")
    done = {r.get("forecast_id") for r in _jsonl(gp)}
    px = load_closes(bar_paths(data_root), [r["ticker"] for r in rows]) if rows else None
    last_bar = None if px is None or px.empty else str(px.index[-1])
    counts = {"graded": 0, "pending": 0, "ungradeable": 0, "already": 0,
              "no_write_time": 0, "replay_excluded": 0, "frozen_late": 0,
              "seal_mismatch": 0}
    out = []
    for r in rows:
        if r["forecast_id"] in done:
            counts["already"] += 1
            continue
        written = _utc(r.get("written_utc"))
        if written is None:
            counts["no_write_time"] += 1
            continue
        if r.get("replay") is not False:
            counts["replay_excluded"] += 1
            continue
        made = _utc(r["made_at"])
        if px is None or px.empty or r["ticker"] not in px.columns or "SPY" not in px.columns:
            counts["ungradeable"] += 1
            continue
        s = px[[r["ticker"], "SPY"]].dropna()
        dates = list(s.index)
        e = entry_session(made, dates) if made else None
        h = int(r["horizon_sessions"])
        if e is None or dates.index(e) + h >= len(dates):
            counts["pending"] += 1
            continue
        if session_close(e) <= written:          # real close; 13:00 ET on a half day
            counts["frozen_late"] += 1
            continue
        if r.get("seal") != _sha({k: v for k, v in r.items() if k != "seal"}, n=24):
            counts["seal_mismatch"] += 1        # hand-edited after freezing
            continue
        i = dates.index(e)
        x = dates[i + h]
        ret = float(s[r["ticker"]].iloc[i + h] / s[r["ticker"]].iloc[i] - 1)
        spy = float(s["SPY"].iloc[i + h] / s["SPY"].iloc[i] - 1)
        adj = ret - spy
        d = r.get("predicted_direction")
        g = {"forecast_id": r["forecast_id"], "event_id": r["event_id"], "ticker": r["ticker"],
             "horizon_sessions": h, "entry_date": str(e), "exit_date": str(x),
             "ret": round(ret, 6), "spy_ret": round(spy, 6), "market_adjusted": round(adj, 6),
             "predicted_direction": d, "hit": None if not d else bool((adj > 0) == (d > 0)),
             "abs_error_vs_expected": (None if r.get("expected_size") is None
                                       else round(abs(adj - float(r["expected_size"])), 6)),
             "graded_at": now.isoformat(timespec="seconds"), "bars_last": last_bar}
        out.append(g)
        counts["graded"] += 1
    if out:
        from backend.services import disk_guard as DG
        for g in out:
            DG.locked_append_line(gp, json.dumps(g, sort_keys=True))
    return {"forecasts": str(forecasts_path), "grades": str(gp), "bars_last": last_bar,
            "counts": counts, "new_grades": out}


def learn(ev: Optional[dict], uni: Optional[dict], dec: Optional[dict], *, now: datetime,
          out_dir: Path, data_root: Path, write: bool = True) -> tuple[Stage, Optional[dict]]:
    if ev is None or dec is None:
        return Stage("LEARN", BLOCKED, "NOTHING_TO_FORECAST"), None
    written_at = _wall_clock()
    rows = forecast_rows(ev, uni, dec, made_at=now, written_at=written_at)
    replay = is_replay(now, written_at)
    fpath = Path(out_dir) / "forecasts.jsonl"
    reasons = []
    if write:
        try:
            n_new, n_dup = append_forecasts(fpath, rows)
        except OSError as exc:
            return Stage("LEARN", BLOCKED, f"FORECAST_WRITE_FAILED: {type(exc).__name__}",
                         evidence=[str(fpath)]), None
    else:
        n_new, n_dup = 0, 0
        reasons.append("NO_WRITE_REQUESTED")
    px = load_closes(bar_paths(data_root), {r["ticker"] for r in rows})
    missing = sorted({r["ticker"] for r in rows} - set(getattr(px, "columns", [])))
    if missing:
        reasons.append(f"NO_BARS_FOR {','.join(missing)[:80]} (ungradeable until bars exist)")
    if not any(r.get("predicted_direction") for r in rows):
        reasons.append("NO_DIRECTIONAL_CLAIM (rows graded for size only)")
    if replay:
        reasons.append(f"REPLAY_NOT_FORWARD_EVIDENCE (--now {now.isoformat(timespec='seconds')}"
                       f" vs wall clock {written_at.isoformat(timespec='seconds')}; the grader "
                       "excludes these rows)")
    if write and n_new == 0:
        reasons.append(f"NOTHING_NEW_FROZEN ({n_dup} row(s) already present)")
    last_bar = None if px is None or px.empty else str(px.index[-1])
    out = {"forecast_ids": [r["forecast_id"] for r in rows], "n_rows": len(rows),
           "n_new": n_new, "n_already_present": n_dup, "path": str(fpath),
           "bars_last": last_bar, "grader": "backend.services.one_event.grade "
           "(python -m scripts.one_event grade --out <dir> --data-root <optimus>)",
           "first_gradeable": "entry close + h sessions; h=1 and h=5",
           "written_utc": written_at.isoformat(timespec="seconds"), "replay": replay}
    status = DEGRADED if reasons else SUCCESS
    return Stage("LEARN", status, ";".join(reasons) or "OK",
                 "le_" + _sha(out["forecast_ids"]), [str(fpath)], out), out


# ─────────────────────────────────── chain ───────────────────────────────────

def run_one(*, data_root: Path, source: str, key: str, now: datetime, out_dir: Path,
            graph_dir: Optional[Path] = None, funnel_path: Optional[Path] = None,
            positions_path: Optional[Path] = None, ticker: Optional[str] = None,
            direction: Optional[int] = None, write: bool = True) -> dict:
    data_root = Path(data_root)
    funnel_path = Path(funnel_path) if funnel_path else data_root.parent / "funnel_night10.json"
    positions_path = Path(positions_path) if positions_path else data_root / "pc_book" / "state_latest.json"
    graph_dir = Path(graph_dir) if graph_dir else default_graph_dir(data_root)
    row, path = find_event(data_root, source, key, now=now)
    s1, ev = sense(row, path, source=source, key=key, now=now, data_root=data_root,
                   ticker=ticker, direction=direction)
    s2, uni = universe(ev, now=now, graph_dir=graph_dir, funnel_path=funnel_path)
    s3, dec = decide(ev, row, uni, now=now, positions_path=positions_path, graph_dir=graph_dir)
    s4, _ = act(ev, dec)
    s5, _ = learn(ev, uni, dec, now=now, out_dir=out_dir, data_root=data_root, write=write)
    stages = [s1, s2, s3, s4, s5]
    red = [s.name for s in stages if s.status == BLOCKED and not s.intended]
    rec = {"schema": SCHEMA, "run_at": now.isoformat(timespec="seconds"),
           "data_root": str(data_root), "chain": {s.name: s.stage_id for s in stages},
           "stages": [s.to_dict() for s in stages], "red_stages": red,
           "exit_code": 2 if red else 0, "licence": "PRODUCT_EXPERIMENT",
           "no_order_sent": True, "llm_calls": 0}
    rec["receipt_id"] = "rc_" + _sha(rec["chain"], rec["run_at"])
    return rec


def write_receipt(rec: dict, out_dir: Path) -> Path:
    from backend.services import disk_guard as DG
    d = Path(out_dir) / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    stamp = rec["run_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    p = d / f"one_event_{stamp}_{rec['chain'].get('SENSE') or 'none'}.json"
    DG.atomic_write_json(p, rec)
    return p


def table(rec: dict) -> str:
    lines = [f"{'stage':<9} {'status':<9} {'id':<20} reason"]
    for s in rec["stages"]:
        flag = " (intended)" if s.get("intended_block") else ""
        lines.append(f"{s['name']:<9} {s['status']:<9} {str(s.get('stage_id') or '-'):<20} "
                     f"{s['reason'][:150]}{flag}")
    lines.append(f"exit {rec['exit_code']}; red stages: {rec['red_stages'] or 'none'}; "
                 f"no order sent; llm calls 0")
    return "\n".join(lines)
