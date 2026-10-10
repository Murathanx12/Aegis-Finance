"""Decision Story: one id chain per candidate per session, and the alternatives
the plan did NOT take, frozen at decision time (chunk C11, 2026-10-06).

WHY THIS EXISTS
===============
Mission rule 1 asks, of every decision: *given what was knowable at t, what
action, what alternative, what happened, why, and what should change?* Until
this module the plan receipt answered only the first. A HOLD or a REFUSE left
no trace a grader could price, so the system was "comfortable not deciding":
not deciding had no measured cost. The roadmap (2026-10-06 §2 item 8) refuses
to *punish* abstention -- a learner rewarded for acting acts on noise -- and
instead makes it MEASURABLE: every candidate freezes its BUY counterfactual
(and its sizing, exit and leave-one-source-out siblings) at the moment of the
decision, and `regret_ledger.grade_due` prices them on real bars later.

THE CHAIN
=========
    event_ids -> evidence_ids -> forecast_ids -> decision_id
              -> order_or_abstention_id -> outcome_ids -> attribution_ids

Existing ids are REUSED: forecast and news rows carry `prediction_id`, a
broker order carries its `order_id`, the plan's E[r] receipt / ranking /
funnel / contract are addressed by path + key. Only `decision_id` and
`abstention_id` are minted here; `outcome_ids` / `attribution_ids` are
DETERMINISTIC from the decision id and the horizon, so the chain is complete
at write time and the grader fills the outcome without touching the story.

FROZEN, APPEND-ONLY
===================
`stories_<YYYY-MM>.jsonl` (kind `decision` and `order_link`) and
`alternatives_<YYYY-MM>.jsonl` are monthly, so the C10 archival pattern
applies. A row is never rewritten: a decision whose (action, weight, acting)
is unchanged since the last cycle is not written again (the plan runs every
five minutes), a changed one is a NEW decision, and an order sent in a later
cycle is an appended `order_link` row. Every row carries a sha256 seal.

Alternatives read NO bar after `asof`: an injected bars frame is cut at
`asof` before anything reads it, and wall-clock stamps live only on the
story row, never on an alternative, so two freezes from the same inputs
produce byte-identical alternative rows whatever the future holds.

LEAVE-ONE-SOURCE-OUT, OR `NOT_SEPARABLE`
========================================
The plan is replayed (`replan`) from its own frozen scoring inputs with one
source removed. The replay is CHECKED against the actual targets first; if it
does not reproduce them, every leave-one-out row is NOT_SEPARABLE. A source
the plan cannot be re-evaluated without (the funnel ranked or filtered on it,
and the funnel is not re-run here) is NOT_SEPARABLE for the names it could
move -- never a fabricated weight. A source the plan does not read at all
(news, today) is IDENTICAL_NOT_READ: its MDC is zero by construction, which
says the plan ignores news, not that news is worthless.

No order is ever sent from an alternative. No LLM is called.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend import config as _cfg

logger = logging.getLogger(__name__)

STORY_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "decision_story"
SCHEMA_VERSION = 1

#: The horizons every alternative is graded at (roadmap C11: 5/21/63).
HORIZONS: tuple[int, ...] = (5, 21, 63)

#: The leave-one-source-out set (roadmap C11 brief item 2).
LOO_SOURCES: tuple[str, ...] = ("news", "analyst", "price_momentum", "regime", "llm")

#: E[r] components each source owns. DERIVED checks below refuse a mapping that
#: has drifted from `expected_return.COMPONENTS`.
SOURCE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "news": (),
    "analyst": ("revision_flow", "source_reliability"),
    "price_momentum": ("ranker",),
    "regime": (),
    "llm": ("investigator_dir", "thesis_card"),
}

#: Words that, found in the funnel's `ranked_by` / `filtered_by`, mean the
#: shortlist itself was selected on that source -- the funnel is not re-run
#: here, so PROBE names are then NOT_SEPARABLE for it.
SOURCE_FUNNEL_TERMS: dict[str, tuple[str, ...]] = {
    "news": ("news", "headline", "digest", "sentiment"),
    "analyst": ("analyst", "revision", "rating", "target"),
    "price_momentum": ("momentum", "volatil", "liquid", "price", "reversal", "52w",
                       "dollar", "return"),
    "regime": ("regime", "vix", "macro"),
    "llm": ("llm", "investigator", "thesis", "persona", "card"),
}

#: E[r]'s own declaration of the forecast prefixes it does NOT read. If news
#: ever leaves this table, the news leave-one-out stops being IDENTICAL.
NEWS_PREFIXES: tuple[str, ...] = ("source:", "news_digest:")
FORECAST_PREFIXES: tuple[str, ...] = ("investigator:", "thesis_card:")

ABSTENTION_ACTIONS = ("HOLD", "REFUSE")


# ───────────────────────────────── helpers ──────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def seal(row: dict) -> str:
    body = {k: v for k, v in row.items() if k != "sha256"}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def _h(*parts: Any, n: int = 16) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:n]


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def month_of(asof: str) -> str:
    return str(asof)[:7]


def stories_path(story_dir: Path, asof: str) -> Path:
    return Path(story_dir) / f"stories_{month_of(asof)}.jsonl"


def alternatives_path(story_dir: Path, asof: str) -> Path:
    return Path(story_dir) / f"alternatives_{month_of(asof)}.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not Path(path).is_file():
        return out
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                logger.warning("decision_story: unparseable row in %s skipped", path)
    return out


def _append(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(_canon(r) + "\n")


def mint_decision_id(*, asof: str, ticker: str, policy_version: str, action: str,
                     target_weight: float, acting: bool) -> str:
    """Same (asof, ticker, policy, action, weight to 4dp, acting) -> same id:
    a five-minute loop that re-decides the same thing writes it once."""
    return "dec_" + _h(asof, ticker, policy_version, action,
                       f"{float(target_weight):.4f}", bool(acting))


def abstention_id(decision_id: str) -> str:
    return "abs_" + decision_id[4:]


def outcome_id(decision_id: str, h: int) -> str:
    return f"out_{decision_id[4:]}_h{int(h)}"


def attribution_id(decision_id: str, h: int) -> str:
    return f"att_{decision_id[4:]}_h{int(h)}"


# ──────────────────────── separability, derived ─────────────────────────────

def mapping_check() -> dict:
    """Refuse a source map that has drifted from what E[r] actually is."""
    from backend.services import expected_return as ER
    mapped = {c for cs in SOURCE_COMPONENTS.values() for c in cs}
    unknown = sorted(mapped - set(ER.COMPONENTS))
    news_unread = all(p in ER.NOT_READ_BY_DESIGN for p in NEWS_PREFIXES)
    return {"ok": not unknown, "unknown_components": unknown,
            "unmapped_components": sorted(set(ER.COMPONENTS) - mapped),
            "news_not_read_by_er": news_unread}


def funnel_separable(source: str, evidence_basis: dict | None,
                     probe_weighting: str | None) -> tuple[bool, str]:
    """Can the PROBE side of the plan be re-evaluated without `source`?"""
    if not isinstance(evidence_basis, dict) or not (
            evidence_basis.get("ranked_by") or evidence_basis.get("filtered_by")):
        return False, ("the funnel carries no evidence_basis: what selected the "
                       "shortlist cannot be told, and the funnel is not re-run here")
    used = [str(x) for x in (evidence_basis.get("ranked_by") or [])
            + (evidence_basis.get("filtered_by") or [])]
    hits = [u for u in used if any(t in u.lower() for t in SOURCE_FUNNEL_TERMS[source])]
    if hits:
        return False, (f"the funnel selected the shortlist on {hits}; the funnel is "
                       f"not re-run without {source}")
    if source == "price_momentum" and probe_weighting in ("inverse_vol", "bigmove_tilt"):
        return False, f"PROBE weights are {probe_weighting}, a price-derived sigma"
    return True, f"the funnel ranked on {used}: none is {source}"


# ─────────────────────────── the E[r] view, minus ────────────────────────────

def er_names_minus(names: dict, drop: str | None, *, regime_scale: float) -> tuple[dict, dict]:
    """The E[r] `names` block recomputed with one source's components removed.

    Weights renormalise over the remaining awake components (the layer's own
    sleeping-experts rule). Exact when the layer used EQUAL weights; for
    reputation weights the proportional renormalisation is an approximation
    and the returned meta says so. `regime` sets the scale to 1.0; `llm` also
    drops the magnitude size scale (`investigator_mag`, sizing only).
    """
    comps = set(SOURCE_COMPONENTS.get(drop or "", ()))
    s_new = 1.0 if drop == "regime" else float(regime_scale)
    out: dict = {}
    approx = False
    llm_catalyst: list[str] = []
    for t, nm in (names or {}).items():
        nn: dict = {}
        for k, cell in nm.items():
            if not (isinstance(k, str) and k.startswith("h") and isinstance(cell, dict)):
                continue
            x = {c: v for c, v in (cell.get("x") or {}).items() if c not in comps}
            if drop == "llm" and "catalyst" in x:
                llm_catalyst.append(t)

            def _renorm(w: dict) -> dict:
                w2 = {c: float(w.get(c) or 0.0) for c in x}
                s = sum(w2.values())
                return {c: (v / s if s > 0 else 0.0) for c, v in w2.items()}
            w_used = _renorm(cell.get("weights") or {})
            w_rep = _renorm(cell.get("weights_reputation") or {})
            if cell.get("weights_source") not in (None, "equal") and comps & set(cell.get("x") or {}):
                approx = True
            er = None
            if cell.get("er") is not None and x:
                er = s_new * sum(w_used[c] * float(x[c]) for c in x)
            nn[k] = {**cell, "x": x, "weights": w_used, "weights_reputation": w_rep,
                     "components_awake": list(x), "er": er}
        mag = float(nm.get("size_scale_mag", 1.0) or 1.0)
        if drop == "llm":
            mag = 1.0
        nn["size_scale_mag"] = mag
        nn["size_scale"] = min(1.0, mag * min(s_new, 1.0))
        out[t] = nn
    return out, {"approximation": ("reputation weights renormalised proportionally "
                                   "over the remaining components") if approx else None,
                 "llm_catalyst_names": sorted(set(llm_catalyst))}


# ───────────────────────────────── replay ────────────────────────────────────

def replan(inp: dict, names: dict | None, *, pool_override: list | None = None) -> dict:
    """u_plan's selection and sizing (scripts/sim_run.py, the EXPLOIT/PROBE
    block), PURE, from frozen inputs. Returns {ticker: target weight} plus the
    sets. `replay_check` proves it reproduces the live plan before any
    leave-one-out row is trusted."""
    from backend.services import policy_state as PS
    pool = list(inp["pool"] if pool_override is None else pool_override)
    book = int(inp["book_size"])
    top = pool[:book]
    er_present = names is not None

    def _er21(sym: str) -> float | None:
        cell = ((names or {}).get(str(sym).upper()) or {}).get("h21")
        return None if not cell else cell.get("er")

    er_pool = [(x, _er21(x["symbol"])) for x in pool]
    if er_present and any(e is not None for _, e in er_pool):
        ex_pick = sorted([(x, e) for x, e in er_pool if e is not None and e > 0],
                         key=lambda z: -z[1])[:book]
    else:
        ex_pick = [(x, None) for x in top]
    g = inp["gates"]
    exploit_acting = (g["mode"] == "paper_profit" and g["ranker_may_trade"]
                      and g["blend_may_trade"] and bool(ex_pick))
    sl = list(inp["shortlist"])
    if inp.get("rep_weights") is not None and er_present:
        sl, _ = PS.probe_order(sl, {"names": names}, inp["rep_weights"], sigma=inp["sig_by"])
    exploit_syms = [x["symbol"] for x, _ in ex_pick]
    probe_rows = [x for x in sl if not (exploit_acting and x["ticker"] in exploit_syms)]
    probe_rows = probe_rows[:int(inp["probe_max_names"])]
    w_probe, _ = PS.probe_weights([x["ticker"] for x in probe_rows], inp["sig_by"],
                                  inp["probe_weighting"], max_weight=float(inp["probe_max_weight"]),
                                  gross_cap=float(inp["probe_gross_cap"]))
    probe_syms = [x["ticker"] for x in probe_rows]
    ex_syms = [s for s in exploit_syms if s not in probe_syms]
    room = max(0.0, 1.0 - sum(w_probe.values()))
    ex_er = {x["symbol"]: e for x, e in ex_pick if x["symbol"] in ex_syms}
    if ex_syms and all(ex_er.get(s) is not None for s in ex_syms):
        tot = sum(ex_er[s] for s in ex_syms)

        def _scale(s: str) -> float:
            return float(((names or {}).get(str(s).upper()) or {}).get("size_scale", 1.0))
        w_ex = {s: min(float(inp["exploit_max_weight"]), room * ex_er[s] / tot) * _scale(s)
                for s in ex_syms}
    else:
        # Match u_plan's capped inventory fallback when no E[r] is awake.
        w_eq = (min(room / len(ex_syms), float(inp["exploit_max_weight"]))
                if ex_syms else 0.0)
        w_ex = {s: w_eq for s in ex_syms}
    return {"weights": {**w_ex, **w_probe}, "probe_syms": probe_syms, "ex_syms": ex_syms,
            "exploit_acting": exploit_acting,
            "shortlist_order": [x["ticker"] for x in sl],
            "pool_order": [x["symbol"] for x, _ in ex_pick]}


def replay_check(inp: dict, names: dict | None, *, tol: float = 1e-9) -> dict:
    rp = replan(inp, names)
    actual = {k: float(v) for k, v in inp["actual_weights"].items()}
    keys = set(actual) | set(rp["weights"])
    diff = {k: (actual.get(k, 0.0), rp["weights"].get(k, 0.0)) for k in keys
            if abs(actual.get(k, 0.0) - rp["weights"].get(k, 0.0)) > tol}
    return {"matches": not diff, "n_diff": len(diff),
            "diff": dict(list(diff.items())[:8]), "replay": rp}


# ───────────────────────────── evidence lookup ───────────────────────────────

def index_predictions(preds: Iterable[dict] | None, asof: str, tickers: Iterable[str], *,
                      news_days: int = 5) -> dict:
    """ticker -> {forecasts: [...], events: [...]} from rows made on or before
    `asof` (nothing later is read). Forecasts: the latest made day per E[r]
    forecast prefix. Events: news rows within `news_days` calendar days."""
    want = {str(t).upper() for t in tickers}
    lo = (date.fromisoformat(asof).toordinal() - news_days)
    by: dict[str, dict] = {t: {"fc": {}, "events": []} for t in want}
    for r in preds or []:
        t = str(r.get("ticker") or "").upper()
        if t not in want:
            continue
        made = str(r.get("made_at") or "")
        day = made[:10]
        if not day or day > asof:
            continue
        spec = str(r.get("specialist") or "")
        rec = {"id": r.get("prediction_id"), "made_at": made, "specialist": spec,
               "price": _f((r.get("inputs_used") or {}).get("price_at_write"))
               if isinstance(r.get("inputs_used"), dict) else None}
        if any(spec.startswith(p) for p in FORECAST_PREFIXES):
            pre = spec.split(":", 1)[0]
            cur = by[t]["fc"].get(pre)
            if cur is None or day > cur["day"]:
                by[t]["fc"][pre] = {"day": day, "rows": [rec]}
            elif day == cur["day"]:
                cur["rows"].append(rec)
        elif any(spec.startswith(p) for p in NEWS_PREFIXES):
            try:
                if date.fromisoformat(day).toordinal() < lo:
                    continue
            except ValueError:
                continue
            iu = r.get("inputs_used") if isinstance(r.get("inputs_used"), dict) else {}
            rec["published_at"] = (iu.get("published_at") or iu.get("published")
                                   or iu.get("article_published_at"))
            by[t]["events"].append(rec)
    out = {}
    for t, v in by.items():
        fcs = [x for blk in v["fc"].values() for x in blk["rows"]]
        out[t] = {"forecasts": sorted(fcs, key=lambda x: x["made_at"])[-12:],
                  "events": sorted(v["events"], key=lambda x: x["made_at"])[-12:]}
    return out


def _bar_close(bars: Any, sym: str, day: str | None) -> float | None:
    if bars is None or not day:
        return None
    try:
        sub = bars[(bars["symbol"] == sym) & (bars["date"] <= day)]
        return None if sub.empty else float(sub.iloc[-1]["close"])
    except Exception:                                              # noqa: BLE001
        return None


def cut_bars(bars: Any, asof: str) -> Any:
    """Nothing after `asof` is readable by the freezer (the PIT rule)."""
    if bars is None:
        return None
    import pandas as pd
    b = bars.copy()
    b["date"] = pd.to_datetime(b["date"])
    return b[b["date"] <= pd.Timestamp(asof)].reset_index(drop=True)


# ───────────────────────── the exchange session (review F3) ──────────────────

#: A decision is keyed on the XNYS session whose price it can first trade at,
#: never on the ET calendar date: a Saturday plan and a Friday-evening plan are
#: the SAME decision about Monday's open, not two observations priced at a
#: close already printed.
ET_OPEN = (9, 30)
ET_CLOSE = (16, 0)


def _is_session(d: date) -> bool:
    from datetime import timedelta
    from backend.services.counterfactual_prices import sessions_after
    return sessions_after(d - timedelta(days=1), 1)[0] == d


def _next_session(d: date) -> date:
    from backend.services.counterfactual_prices import sessions_after
    return sessions_after(d, 1)[0]


def reference_session(decision_at: str) -> dict:
    """{session, entry_basis, why} for a decision stamped `decision_at` (UTC).

    * a session day before 09:30 ET -> that session's OPEN;
    * a session day 09:30-16:00 ET  -> that session's CLOSE (a market-on-close
      order is feasible; the close prints after the decision);
    * after 16:00 ET, or a weekend/holiday -> the NEXT session's OPEN.
    The entry is always a price that prints AFTER the decision."""
    from zoneinfo import ZoneInfo
    t = datetime.fromisoformat(str(decision_at).replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    et = t.astimezone(ZoneInfo("America/New_York"))
    d = et.date()
    hm = (et.hour, et.minute)
    if _is_session(d):
        if hm < ET_OPEN:
            return {"session": d.isoformat(), "entry_basis": "open",
                    "why": "decided before the open: enter at this session's open"}
        if hm < ET_CLOSE:
            return {"session": d.isoformat(), "entry_basis": "close",
                    "why": "decided during the session: enter at this session's close"}
        nxt = _next_session(d)
        return {"session": nxt.isoformat(), "entry_basis": "open",
                "why": "decided after the close: enter at the next session's open"}
    nxt = _next_session(d)
    return {"session": nxt.isoformat(), "entry_basis": "open",
            "why": f"{d.isoformat()} is not an XNYS session: enter at the next session's open"}


# ───────────────────────────── shadow news (review F7) ───────────────────────

SHADOW_NEWS_DECISIONS = (Path(_cfg.OPTIMUS_LEDGER_DIR) / "news_digest" / "shadow"
                         / "decisions.jsonl")


def shadow_news_view(decision_at: str, path: Path | None = None) -> dict | None:
    """The newest SHADOW_NEWS_v0 row written ON OR BEFORE `decision_at` (PIT):
    its signal and the trusts its contract earned. None when there is none."""
    rows = read_jsonl(Path(path or SHADOW_NEWS_DECISIONS))
    ok = [r for r in rows if str(r.get("t") or "") <= str(decision_at)
          and isinstance(r.get("signal"), dict)]
    if not ok:
        return None
    r = max(ok, key=lambda x: str(x.get("t")))
    return {"t": r.get("t"), "digest_id": r.get("digest_id"),
            "contract_hash": r.get("contract_hash"), "signal": r["signal"],
            "trust_dir": float(r.get("trust_dir") or 0.0),
            "trust_size": float(r.get("trust_size") or 0.0)}


# ───────────────────────────────── freeze ────────────────────────────────────

def _action(*, target: float, held_w: float, acting: bool, planned_qty: int,
            side: str | None) -> tuple[str, float]:
    """(action, effective weight the account carries after this decision)."""
    if acting and planned_qty > 0 and side == "buy":
        return "BUY", target
    if acting and planned_qty > 0 and side == "sell":
        return ("EXIT" if target <= 0 else "SELL"), target
    if held_w > 0:
        return "HOLD", held_w
    return "REFUSE", 0.0


def cohort_of(*, state: str, action: str, held_w: float, in_shortlist: bool) -> str:
    """Abstentions answer different questions (review F2), so they are graded
    in separate cohorts and never summed together."""
    if action in ("BUY", "SELL", "EXIT"):
        return "acted"
    if held_w > 0:
        return "held_resize"
    if state in ("PROBE", "EXPLOIT"):
        return "picked_blocked"
    return "shortlist_not_taken" if in_shortlist else "ranker_pool"


def live_stories_on_disk(story_dir: Path) -> dict:
    sessions = []
    n = 0
    for p in sorted(Path(story_dir).glob("stories_*.jsonl")):
        for r in read_jsonl(p):
            if r.get("kind") == "decision":
                n += 1
                sessions.append(str(r.get("session") or r.get("asof")))
    return {"n": n, "oldest_session": min(sessions) if sessions else None,
            "n_sessions": len(set(sessions))}


def freeze_plan(inp: dict, *, er_view: dict | None, predictions: list[dict] | None = None,
                story_dir: Path | None = None, now: str | None = None,
                bars: Any = None, shadow_news: Any = "auto",
                write: bool = True) -> dict:
    """Write one story per candidate per SESSION and its frozen alternatives.

    `inp` is the plan's own scoring inputs (built in `sim_run.u_plan`).
    `actual_weights` are the targets BEFORE the order-path gate (what `replan`
    reproduces); `post_gate_weights` and `order_gate_scale_exploit` carry what
    the gate did. Never orders. Idempotent per session: the same decision is
    written once however many cycles or calendar days re-decide it."""
    from backend.services import pc_broker as PB
    from backend.services import xs_ranker as XR
    story_dir = Path(story_dir or STORY_DIR)
    asof = str(inp["asof"])
    now = now or _now()
    ref = reference_session(now)
    session = ref["session"]
    equity = float(inp["equity"])
    bars = cut_bars(bars, asof)
    names = (er_view or {}).get("names") if er_view is not None else None
    scale = float(((er_view or {}).get("regime") or {}).get("scale", 1.0) or 1.0)
    prices = inp.get("prices") or {}
    pos_by = {str(p.get("symbol")): p for p in inp.get("positions") or []}
    post_gate = {k: float(v) for k, v in (inp.get("post_gate_weights")
                                          or inp["actual_weights"]).items()}
    gate_scale = float(inp.get("order_gate_scale_exploit", 1.0) or 1.0)
    if isinstance(shadow_news, str) and shadow_news == "auto":
        shadow_news = shadow_news_view(now, inp.get("shadow_news_path"))

    def _held_w(sym: str) -> float:
        p = pos_by.get(sym)
        if not p:
            return 0.0
        mv = _f(p.get("market_value"))
        if mv is None:
            px = _f(prices.get(sym)) or _bar_close(bars, sym, asof)
            mv = (float(p.get("qty") or 0.0) * px) if px else None
        return (mv / equity) if (mv is not None and equity > 0) else 0.0

    # ---- the replay, then every leave-one-out ----------------------------------
    chk = replay_check(inp, names)
    mp = mapping_check()
    loo: dict[str, dict] = {}
    for src in LOO_SOURCES:
        sep, why = funnel_separable(src, inp.get("funnel_evidence_basis"),
                                    inp.get("probe_weighting"))
        entry = {"probe_separable": sep, "probe_why": why, "weights": None,
                 "approximation": None, "status": "OK", "why": None,
                 "not_separable_names": [], "gate_bound_names": [], "er_names": None}
        if not chk["matches"]:
            entry.update(status="NOT_SEPARABLE",
                         why=f"the replay does not reproduce the live plan ({chk['n_diff']} "
                             f"weights differ): no leave-one-out is trusted")
            loo[src] = entry
            continue
        if not mp["ok"]:
            entry.update(status="NOT_SEPARABLE",
                         why=f"source map names unknown E[r] components {mp['unknown_components']}")
            loo[src] = entry
            continue
        if src == "news":
            if not mp["news_not_read_by_er"]:
                entry.update(status="NOT_SEPARABLE",
                             why="news prefixes are no longer in expected_return."
                                 "NOT_READ_BY_DESIGN: news may now reach E[r] through a "
                                 "component this module does not map")
            elif sep:
                entry.update(status="IDENTICAL_NOT_READ",
                             weights=dict(chk["replay"]["weights"]), er_names=names,
                             why=("the plan does not read news (expected_return."
                                  "NOT_READ_BY_DESIGN; the funnel does not rank or filter on "
                                  "it): the decision without news IS the decision. Its MDC "
                                  "is zero by construction; the news question is answered by "
                                  "the plan_plus_shadow_news alternative instead"))
            else:
                entry.update(status="NOT_SEPARABLE", why=why)
            loo[src] = entry
            continue
        nm2, meta = (er_names_minus(names, src, regime_scale=scale)
                     if names is not None else (None, {"approximation": None,
                                                        "llm_catalyst_names": []}))
        pool_o = [] if src == "price_momentum" else None
        rp = replan(inp, nm2, pool_override=pool_o)
        entry.update(weights=rp["weights"], approximation=meta["approximation"],
                     er_names=nm2, exploit_empty=not rp["ex_syms"])
        bad = set(meta.get("llm_catalyst_names") or [])
        if not sep:
            bad |= {x["ticker"] for x in inp["shortlist"]}
            if rp["ex_syms"]:
                bad |= {x["symbol"] for x in inp["pool"]}
        if gate_scale < 1.0 and (rp["ex_syms"] or inp["ex_syms"]):
            # review F5: the order-path gate scaled EXPLOIT before the freeze;
            # its scale for a DIFFERENT book is not modelled here
            entry["gate_bound_names"] = sorted(set(rp["ex_syms"]) | set(inp["ex_syms"]))
            bad |= set(entry["gate_bound_names"])
        entry["not_separable_names"] = sorted(bad)
        entry["why"] = (why if not sep else
                        (f"recomputed from the plan's own inputs without {src}" +
                         ("; catalyst x may carry LLM thesis-card events for "
                          f"{sorted(meta['llm_catalyst_names'])}"
                          if meta.get("llm_catalyst_names") else "")))
        if src == "price_momentum":
            entry["why"] += ("; the ranker is price/volume features only, so EXPLOIT has "
                             "no candidate pool without them")
        loo[src] = entry

    # ---- candidates -----------------------------------------------------------
    rp0 = chk["replay"]
    probe_syms, ex_syms = list(inp["probe_syms"]), list(inp["ex_syms"])
    sl_t = [x["ticker"] for x in inp["shortlist"]]
    pool_s = [str(x["symbol"]) for x in inp["pool"]]
    cand: list[str] = list(dict.fromkeys(sl_t + pool_s + list(pos_by)))
    sl_by = {x["ticker"]: x for x in inp["shortlist"]}
    pool_by = {str(x["symbol"]): x for x in inp["pool"]}
    nxt_probe = next((t for t in rp0["shortlist_order"]
                      if t not in probe_syms and t not in ex_syms), None)
    nxt_ex = next((s for s in pool_s if s not in ex_syms and s not in probe_syms
                   and s not in rp0["pool_order"]), None)
    plans = inp.get("plans") or {}
    sent_by = {str(s.get("symbol")): s for s in inp.get("sent") or []
               if s.get("status") == "submitted"}
    idx = index_predictions(predictions, asof, cand)
    w_default = min(float(inp["probe_max_weight"]),
                    float(inp["probe_gross_cap"]) / max(1, int(inp["probe_max_names"])))
    name_cap = float(PB.MAX_NAME_FRAC)
    funnel_at = inp.get("funnel_generated_at")

    def _mdv(sym: str | None) -> float | None:
        if not sym:
            return None
        return (_f((sl_by.get(sym) or {}).get("median_dollar_vol"))
                or _f((pool_by.get(sym) or {}).get("median_dollar_vol")))

    # plan + shadow news (review F7): the SHADOW_NEWS_v0 tilt over plan_full,
    # restricted to the plan's own candidates (a new name needs a story to grade)
    sn_alt: dict[str, dict] = {}
    if shadow_news:
        from backend.services import world_digest as WD
        base = {t: float(w) for t, w in rp0["weights"].items() if w > 0}
        for label, td, ts in (("plan_plus_shadow_news", shadow_news["trust_dir"],
                               shadow_news["trust_size"]),
                              ("plan_plus_shadow_news_full", 1.0, 1.0)):
            sn_alt[label] = (WD.shadow_decision(base, shadow_news["signal"], trust_dir=td,
                                                trust_size=ts, universe=set(cand))
                             if base else {})

    old_rows = (read_jsonl(stories_path(story_dir, session))
                + (read_jsonl(stories_path(story_dir, asof))
                   if month_of(asof) != month_of(session) else []))
    existing = {r.get("decision_id") for r in old_rows if r.get("kind") == "decision"}
    linked = {r.get("decision_id") for r in old_rows if r.get("kind") == "order_link"}
    stories, alts, links = [], [], []
    n_abst, n_same_session = 0, 0
    not_sep_sources: set[str] = set()
    for t in cand:
        target = float(post_gate.get(t, 0.0))
        state = ("PROBE" if t in probe_syms else "EXPLOIT" if t in ex_syms else
                 "HELD_NOT_TARGET" if t in pos_by else "NOT_SELECTED")
        acting = bool(inp["probe_acting"] if state == "PROBE" else
                      inp["exploit_acting"] if state == "EXPLOIT" else
                      (inp["probe_acting"] if t in inp.get("prior_probe", []) else
                       inp["exploit_acting"]) if state == "HELD_NOT_TARGET" else False)
        p = plans.get(t) or {}
        held_w = _held_w(t)
        action, eff_w = _action(target=target, held_w=held_w, acting=acting,
                                planned_qty=int(p.get("qty") or 0), side=p.get("side"))
        did = mint_decision_id(asof=session, ticker=t, policy_version=inp["policy_version"],
                               action=action, target_weight=eff_w, acting=acting)
        is_abst = action in ABSTENTION_ACTIONS
        n_abst += int(is_abst)
        sent = sent_by.get(t)
        if did in existing:
            n_same_session += 1
            if sent and did not in linked:
                links.append({"kind": "order_link", "schema": SCHEMA_VERSION,
                              "decision_id": did, "asof": asof, "session": session,
                              "ticker": t,
                              "order_id": sent.get("order_id") or sent.get("client_order_id"),
                              "order_at": sent.get("submitted_at") or now,
                              "price_at_order": _f(prices.get(t))})
            continue
        mdv = _mdv(t)
        rt_bps = float(XR.round_trip_bps(mdv))
        cells = ((names or {}).get(t.upper()) or {}) if names is not None else {}

        def _ers(nm: dict | None, sym: str = t) -> dict:
            c = ((nm or {}).get(sym.upper()) or {})
            return {f"h{h}": (c.get(f"h{h}") or {}).get("er") for h in HORIZONS}
        plan_w = float(rp0["weights"].get(t, 0.0))
        ref_w = eff_w if eff_w > 0 else (plan_w if plan_w > 0 else w_default)
        sel = (nxt_probe if state == "PROBE" else nxt_ex if state == "EXPLOIT" else None)
        info = idx.get(t.upper()) or {"forecasts": [], "events": []}
        fc, ev = info["forecasts"], info["events"]
        cohort = cohort_of(state=state, action=action, held_w=held_w, in_shortlist=t in sl_by)
        # ---- frozen alternatives (no wall-clock, no bar after asof) -----------
        a_rows: list[dict] = []

        def _alt(name: str, w: float | None, er: dict, *, status: str = "OK",
                 why: str | None = None, ticker: str | None = None, **extra: Any) -> None:
            row = {"kind": "alternative", "schema": SCHEMA_VERSION, "decision_id": did,
                   "asof": asof, "session": session, "ticker": ticker or t, "alt": name,
                   "target_weight": None if w is None else round(float(w), 8),
                   "expected_return": er, "horizons": list(HORIZONS),
                   "status": status, "why": why, "places_orders": False, **extra}
            row["sha256"] = seal(row)
            a_rows.append(row)
        er_full = _ers(names)
        _alt("actual", eff_w, er_full, action=action, acting=acting,
             planned_target_weight=round(target, 8))
        _alt("plan_full", plan_w, er_full,
             why="the plan's target before the acting gate and the order-path gate "
                 "(the MDC baseline, and the counterfactual of a picked-but-blocked name)")
        _alt("no_trade", held_w, er_full, why="keep what is held; trade nothing")
        _alt("buy_default", w_default, er_full,
             why="PROBE default size min(PROBE_MAX_WEIGHT, PROBE_GROSS_CAP/PROBE_MAX_NAMES)")
        _alt("buy_half", 0.5 * ref_w, er_full, why="half the reference size (diagnostic)")
        _alt("buy_double_capped", min(2.0 * ref_w, name_cap), er_full,
             why=(f"twice the reference size, capped at pc_broker.MAX_NAME_FRAC {name_cap:.0%}; "
                  f"above PROBE_MAX_WEIGHT it answers a different mandate (diagnostic)"))
        _alt("enter_next_open", ref_w, er_full,
             why=("the same size entered at the NEXT tradable open after the reference "
                  "entry, same exit (timing diagnostic). An earlier entry is not an action "
                  "the plan could have taken and is not frozen"))
        if held_w > 0:
            _alt("exit_now", 0.0, er_full, why="sell the held line at the reference entry")
            _alt("hold", held_w, er_full, why="keep the held line as it is")
        if sel:
            _alt("selection_next_ranked", ref_w, _ers(names, sel),
                 ticker=sel, median_dollar_vol=_mdv(sel),
                 why=(f"the next-ranked {state} candidate not taken, at this size; graded "
                      f"ONCE per session against the taken book, at its own cost band"),
                 instead_of=t)
        for label, book in sn_alt.items():
            _alt(label, float(book.get(t, 0.0)), er_full,
                 why=(f"SHADOW_NEWS_v0 tilt over plan_full (contract "
                      f"{shadow_news['contract_hash']}, row {shadow_news['t']}, trust "
                      + (f"dir {shadow_news['trust_dir']} size {shadow_news['trust_size']})"
                         if label == "plan_plus_shadow_news" else "1/1: diagnostic)")))
        if not sn_alt:
            _alt("plan_plus_shadow_news", None, {f"h{h}": None for h in HORIZONS},
                 status="NOT_AVAILABLE",
                 why="no SHADOW_NEWS_v0 row was written on or before the decision")
        for src, e in loo.items():
            name = f"loo_{src}"
            if e["status"] == "NOT_SEPARABLE" or t in e["not_separable_names"]:
                not_sep_sources.add(src)
                why = e["why"]
                if e["status"] != "NOT_SEPARABLE":
                    if t in e.get("gate_bound_names", []):
                        why = (f"NOT_SEPARABLE because the order gate bound: EXPLOIT scaled "
                               f"by {gate_scale:.3f} before the freeze, and the gate's scale "
                               f"for the leave-one-out book is not modelled")
                    elif t in sl_by and not e["probe_separable"]:
                        why = e["probe_why"]
                _alt(name, None, {f"h{h}": None for h in HORIZONS}, status="NOT_SEPARABLE",
                     why=why)
            else:
                _alt(name, (e["weights"] or {}).get(t, 0.0), _ers(e["er_names"]),
                     status=e["status"], why=e["why"],
                     approximation=e.get("approximation"))
        alts.extend(a_rows)
        alt_sha = hashlib.sha256("".join(r["sha256"] for r in a_rows).encode()).hexdigest()
        # ---- the story ----------------------------------------------------------
        published = sorted(str(x["published_at"]) for x in ev if x.get("published_at"))
        latency = {
            "published_at": published[0] if published else None,
            "aegis_detected_at": (min(x["made_at"] for x in ev) if ev else
                                  (funnel_at if t in sl_by else None)),
            "forecast_at": (max(x["made_at"] for x in fc) if fc else
                            (er_view or {}).get("written_utc")),
            "decision_at": now,
            "order_at": (sent or {}).get("submitted_at"),
            "fill_at": None,
            "prices": {"published_at": None,
                       "aegis_detected_at": None,
                       "forecast_at": next((x["price"] for x in reversed(fc)
                                            if x.get("price") is not None), None),
                       "decision_at": _f(prices.get(t)),
                       "order_at": _f(prices.get(t)) if sent else None,
                       "fill_at": None},
            "notes": ("prices are quotes/forecast-row prices where one exists; no intraday "
                      "bar store is read at decision time; fill_at arrives with the outcome"),
        }
        story = {
            "kind": "decision", "schema": SCHEMA_VERSION, "decision_id": did,
            "asof": asof, "session": session, "entry_basis": ref["entry_basis"],
            "entry_rule": ref["why"], "ticker": t, "mode": inp.get("mode"),
            "policy_id": inp.get("policy_id"), "policy_version": inp["policy_version"],
            "session_id": inp.get("session_id"),
            "state": state, "action": action, "cohort": cohort,
            "acting": acting, "virtual": not acting, "abstention": is_abst,
            "target_weight": round(target, 8), "plan_full_weight": round(plan_w, 8),
            "held_weight": round(held_w, 8), "effective_weight": round(eff_w, 8),
            "equity": equity, "reference_price": _f(prices.get(t)),
            "median_dollar_vol": mdv, "cost_round_trip_bps": rt_bps,
            "cost_basis": ("xs_ranker.round_trip_bps on the frozen median dollar volume; "
                           "none frozen -> the grader derives it from the panel (PIT)"),
            "selector_rank": ((sl_t.index(t) + 1) if t in sl_t else
                              (pool_s.index(t) + 1) if t in pool_s else None),
            "reason": (p.get("reason") or p.get("refused") or
                       ("not selected by the plan" if state == "NOT_SELECTED" else None)),
            "refused": p.get("refused"),
            "next_ranked_not_taken": sel,
            "order_gate_scale_exploit": gate_scale,
            "chain": {
                "event_ids": [x["id"] for x in ev],
                "event_ids_read_by_plan": False,
                "evidence_ids": [a for a in (
                    (f"{(er_view or {}).get('path')}#{t}" if (er_view or {}).get("path") and cells else None),
                    (f"ranking:{inp.get('ranking_model_version')}@{inp.get('ranking_asof')}#rank"
                     f"{pool_s.index(t) + 1}" if t in pool_s else None),
                    (f"funnel@{funnel_at}#{t}" if t in sl_by else None),
                    (f"{inp.get('contract_path')}#{t}" if inp.get("contract_status") == "present" else None),
                    (f"shadow_news:{shadow_news['contract_hash']}@{shadow_news['t']}#{t}"
                     if shadow_news and t in (shadow_news.get("signal") or {}) else None),
                ) if a],
                "forecast_ids": [x["id"] for x in fc],
                "decision_id": did,
                "order_or_abstention_id": (abstention_id(did) if is_abst else
                                           ((sent or {}).get("order_id")
                                            or (sent or {}).get("client_order_id")
                                            or f"pending_order:{did}")),
                "outcome_ids": {f"h{h}": outcome_id(did, h) for h in HORIZONS},
                "attribution_ids": {f"h{h}": attribution_id(did, h) for h in HORIZONS},
            },
            "latency": latency,
            "n_alternatives": len(a_rows), "alternatives_sha256": alt_sha,
            "replay_matches_actual": chk["matches"],
            "built_utc": now,
        }
        story["sha256"] = seal(story)
        stories.append(story)
        existing.add(did)

    if write:
        _append(alternatives_path(story_dir, session), alts)
        _append(stories_path(story_dir, session), stories + links)
    first_grade = first_grade_date(session)
    disk = live_stories_on_disk(story_dir) if write else {"n": None, "oldest_session": None}
    gate_txt = "" if gate_scale >= 1.0 else f"; order gate scaled EXPLOIT x{gate_scale:.3f}"
    line = (f"{n_abst} abstentions frozen with BUY counterfactuals for session {session}; "
            f"first grades at {first_grade}; replay "
            f"{'MATCHES' if chk['matches'] else 'MISMATCH (every leave-one-out NOT_SEPARABLE)'}"
            f"{gate_txt}; live stories on disk: {disk['n']}, oldest session "
            f"{disk['oldest_session']}")
    return {"status": "OK", "line": line, "session": session,
            "entry_basis": ref["entry_basis"], "n_candidates": len(cand),
            "n_new_stories": len(stories), "n_same_session_skipped": n_same_session,
            "n_alternatives_written": len(alts),
            "n_order_links": len(links), "n_abstentions": n_abst,
            "alternatives_per_decision": (len(alts) / len(stories)) if stories else 0,
            "replay_matches_actual": chk["matches"], "replay_diff": chk["diff"],
            "order_gate_scale_exploit": gate_scale,
            "shadow_news": ({k: shadow_news[k] for k in ("t", "contract_hash", "trust_dir",
                                                         "trust_size")}
                            if shadow_news else None),
            "not_separable_sources": sorted(not_sep_sources),
            "loo_status": {s: {"status": e["status"], "probe_separable": e["probe_separable"],
                               "n_not_separable_names": len(e["not_separable_names"]),
                               "why": (e["why"] or "")[:240]} for s, e in loo.items()},
            "first_grade_date": first_grade, "live_stories": disk,
            "stories_path": str(stories_path(story_dir, session)),
            "alternatives_path": str(alternatives_path(story_dir, session)),
            "stories": stories, "alternatives": alts}


def first_grade_date(session: str) -> str | None:
    """The exit session of the shortest horizon, counted from the reference
    session (entry at its open/close)."""
    try:
        from backend.services import decision_contract as DC
        return str(DC.sessions_expiry(date.fromisoformat(session), min(HORIZONS))[0])[:10]
    except Exception:                                              # noqa: BLE001
        return None


__all__ = ["HORIZONS", "LOO_SOURCES", "STORY_DIR", "freeze_plan", "replan", "replay_check",
           "er_names_minus", "funnel_separable", "index_predictions", "mint_decision_id",
           "read_jsonl", "seal", "first_grade_date", "cut_bars", "mapping_check",
           "reference_session", "shadow_news_view", "cohort_of", "live_stories_on_disk"]
