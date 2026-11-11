"""The investigator, with the typed news it was never shown: a PAIRED arm.

    python -m scripts.night_investigator_news --day 2026-11-10            # the night run
    python -m scripts.night_investigator_news --day D --tickers NVDA --ledger <scratch.jsonl>
    python -m scripts.night_investigator_news --pair-report [--ledger <predictions.jsonl>]
    python -m scripts.night_investigator_news --mde [--ledger <predictions.jsonl>]

WHY A SEPARATE ARM AND NOT A FIELD IN THE EXISTING PACKET
=========================================================
`investigator:*` is the only forecaster with measured held-out skill (§64), and
its prompt says it has "no memory of this company's recent news". Whether typed
news ADDS to that process is one question with one clean experiment: the same
process, the same names, the same UTC day, the same h=1 / h=5 question and the
same grader, with exactly one difference -- the packet carries the typed
world-digest rows about the name and about its graph neighbours.

So this arm:

* forecasts the names the plain arm (`investigator:evidence_v3`, the sim's
  `u_forecast`) forecast on the SAME UTC day, read from that day's receipt
  (`forecasts/day_<day>.json`), and refuses when there is none;
* rebuilds the plain arm's packet with the plain arm's own `packet_for` and
  records its hash (`base_packet_hash`); a name whose base differs from the
  plain row's `input_snapshot_hash` is not asked (`base_mismatch`), and
  `pair_report` pools only pairs whose two hashes are equal (review 3);
* adds `news_typed` (rows about the name) and `neighbour_news` (rows about its
  graph neighbours, CONTEXT ONLY: the neighbour's ticker and the relation type,
  never a sign, weight or expected size from the graph);
* writes frozen `beats_benchmark` rows under its own specialist id
  (`config.INVESTIGATOR_NEWS_SPECIALIST`) to the same ledger kind, so
  `forecast_grader` grades them like every other row and `pair_report` joins
  the two arms on (ticker, decision_date, horizon).

The trading plan does not read this arm: E[r]'s `FORECAST_GRADED` reads only
`investigator:` and `thesis_card:`, and `forecast_writers()` lists
`investigator_news:` as NOT READ. Its reason is not registered in
`NOT_READ_BY_DESIGN` / `FORECAST_WRITERS` because both are pinned by the frozen PC
policy epoch; registering it belongs with the next attended epoch.

POINT IN TIME
=============
A typed row is admitted only when its public time (`published_utc`), the time
we first saw it (`first_seen_utc`) and the time it was typed (`cached_utc`) are
all known and at or before the FREEZE CUTOFF, which is the earlier of this run's
clock and the plain arm's `started_utc` for the day (so the two arms see the
same news clock and the news arm cannot win on later information). Every other
matched row is excluded and COUNTED by reason, per name and per run.

SPEND
=====
Through the guarded DeepSeek path only (`llm_analyzer.call_named` ->
`provider_budget.attempt`, the host envelope). A per-run budget
(`config.INVESTIGATOR_NEWS_RUN_BUDGET_USD`, `--budget-usd`) stops the run
before the next call could exceed it (exit 3, PARTIAL). A guard refusal is a
red exit 2 with the guard's own line. No retry, no fallback provider.

Known confound, stated rather than hidden: the plain arm reaches DeepSeek Flash
through the OpenClaw gateway; this arm calls the API directly. Names with ZERO
admitted news rows are therefore a built-in control: on them the two arms
differ only by transport and contract wording, so `pair_report` prints the
difference separately for names with and without news.

PRODUCT_EXPERIMENT licence. Nothing here is a skill claim or a trade.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                   # noqa: E402
from scripts import night_investigator_forecast as NIF               # noqa: E402

SPECIALIST = str(getattr(_cfg, "INVESTIGATOR_NEWS_SPECIALIST", "investigator_news:evidence_v3"))
PAIR_SPECIALIST = NIF.SPECIALIST_DAILY
MODEL_VERSION = "evidence_v3_news1"
#: The attended smoke proof writes under this id so it can never pair or pool.
SMOKE_SPECIALIST = "investigator_news_smoke:evidence_v3"
SMOKE_MAX_NAMES = 3

CONTRACT_NEWS = NIF.CONTRACT_DAILY.replace(
    """1. Reason ONLY from the evidence given. You have no browsing here and no
   memory of this company's recent news. If a field is null, it is UNKNOWN --
   say so rather than filling it in. Do not call any tool.""",
    """1. Reason ONLY from the evidence given. You have no browsing here. The
   packet MAY carry `news_typed`: machine-typed summaries of news items about
   this company that were public before this forecast, and `neighbour_news`:
   items about companies that usually trade with it (context only: the
   relation says nothing about direction). `sentiment` there is a model's
   reading of a headline, not a fact about the price, and an empty list means
   no typed item was found, not that nothing happened. If a field is null, it
   is UNKNOWN -- say so rather than filling it in. Do not call any tool.""")
assert CONTRACT_NEWS != NIF.CONTRACT_DAILY, "the plain contract changed; re-derive CONTRACT_NEWS"

#: Exit codes. A guard's refusal is red, and so is a run its own budget cut short.
RC_DONE, RC_REFUSED, RC_PARTIAL = 0, 2, 3

#: Fields copied from a typed digest row into the packet. No url (it can carry
#: query strings), no free text beyond a sanitised topic.
NEWS_FIELDS = ("published_utc", "source", "kind", "event_type", "sentiment",
               "uncertainty", "novelty", "provenance")


def _c(name: str, default: Any) -> Any:
    return getattr(_cfg, name, default)


def _utc(v: Any) -> Optional[datetime]:
    if v in (None, ""):
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc) if d.tzinfo else None


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


def digest_cache_path(data_root: Optional[Path] = None) -> Path:
    root = Path(data_root) if data_root else Path(_cfg.OPTIMUS_LEDGER_DIR)
    return root / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl"


def receipt_dir(data_root: Optional[Path] = None) -> Path:
    root = Path(data_root) if data_root else Path(_cfg.OPTIMUS_LEDGER_DIR)
    return root / "investigator_news"


# ─────────────────────────────── the news rows ───────────────────────────────

def load_typed_rows(path: Path, *, cutoff: datetime, lookback_hours: float) -> dict:
    """Every typed digest row whose PUBLIC time could fall in the window, indexed
    by every ticker it names (verified or not). Rows are filtered for PIT per
    name later, so exclusions are counted where they happen."""
    since = cutoff - timedelta(hours=float(lookback_hours))
    by_ticker: dict[str, list[dict]] = {}
    n_lines = n_bad = n_old = 0
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False, "by_ticker": {}, "n_lines": 0}
    with p.open(encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            n_lines += 1
            try:
                w = json.loads(ln)
            except ValueError:
                n_bad += 1
                continue
            row = (w or {}).get("row") if isinstance(w, dict) else None
            if not isinstance(row, dict):
                n_bad += 1
                continue
            pub = _utc(row.get("published_utc"))
            # with no public time, first sight bounds it from above: a row first
            # seen before the window was published before it too
            bound = pub or _utc(row.get("first_seen_utc"))
            if bound is not None and bound < since:
                n_old += 1
                continue
            verified = {str(t).upper() for t in row.get("tickers") or [] if t}
            unverified = {str(t).upper() for t in row.get("tickers_unverified") or [] if t}
            if not (verified | unverified):
                continue
            rec = {"row": row, "cached_utc": w.get("cached_utc"), "verified": verified}
            for t in verified | unverified:
                by_ticker.setdefault(t, []).append(rec)
    return {"path": str(p), "exists": True, "by_ticker": by_ticker, "n_lines": n_lines,
            "n_unparsed": n_bad, "n_older_than_window": n_old, "window_start_utc": _iso(since)}


def pit_filter(recs: Iterable[dict], *, cutoff: datetime, lookback_hours: float,
               excluded: Counter) -> list[dict]:
    """Admit a row only when published, first seen AND typed at or before the
    cutoff. Every refusal increments `excluded[<reason>]`."""
    since = cutoff - timedelta(hours=float(lookback_hours))
    out = []
    for rec in recs:
        row = rec["row"]
        pub = _utc(row.get("published_utc"))
        seen = _utc(row.get("first_seen_utc"))
        typed = _utc(rec.get("cached_utc"))
        if pub is None:
            excluded["PUBLIC_TIME_UNKNOWN"] += 1
        elif pub > cutoff:
            excluded["PUBLIC_AFTER_FREEZE"] += 1
        elif seen is None or seen > cutoff:
            excluded["FIRST_SEEN_UNKNOWN_OR_AFTER_FREEZE"] += 1
        elif typed is None or typed > cutoff:
            excluded["TYPED_UNKNOWN_OR_AFTER_FREEZE"] += 1
        elif pub < since:
            excluded["OLDER_THAN_LOOKBACK"] += 1
        else:
            out.append(rec)
    return out


def _compact(rec: dict, ticker: str) -> dict:
    from backend.services import world_digest as WD
    row = rec["row"]
    # line-wise first (a line that addresses a model is dropped), then one line
    topic, _ = WD.sanitize_text(str(row.get("topic") or ""))
    topic = " ".join(topic.split())[:160]
    out = {k: row.get(k) for k in NEWS_FIELDS}
    out["topic"] = topic
    out["about"] = ticker
    out["ticker_verified"] = ticker in rec["verified"]
    return out


def _dedupe_newest(recs: list[dict], limit: int) -> list[dict]:
    seen, out = set(), []
    for rec in sorted(recs, key=lambda r: str(r["row"].get("published_utc")), reverse=True):
        key = rec["row"].get("item_id") or (rec["row"].get("topic"), rec["row"].get("source"))
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
        if len(out) >= limit:
            break
    return out


# ─────────────────────────── graph neighbours (context) ──────────────────────

def graph_neighbours_fn(*, graph_dir: Optional[Path], cutoff: datetime,
                        k: int) -> tuple[Callable[[str], list[dict]], dict]:
    """(ticker -> [{ticker, relation}], status). Context only: no sign, weight
    or size leaves the graph. A graph built AFTER the cutoff, a red status or an
    absent module gives no neighbours, and the status says which."""
    try:
        import importlib
        UG = importlib.import_module("backend.services.universe_graph")
    except ImportError as exc:
        return (lambda t: []), {"status": "MODULE_ABSENT", "error": str(exc)[:120]}
    try:
        st = UG.status(graph_dir, now=cutoff)
        if st.get("red"):
            return (lambda t: []), {"status": f"GRAPH_{st.get('status')}", "line": st.get("line")}
        g = UG.load_graph(graph_dir)
    except Exception as exc:                                         # noqa: BLE001
        return (lambda t: []), {"status": "GRAPH_UNREADABLE", "error": type(exc).__name__}
    if str(g.as_of) > cutoff.date().isoformat():
        return (lambda t: []), {"status": "GRAPH_AFTER_FREEZE", "as_of": g.as_of}
    # review 3: `as_of` is a DATE, so a graph built later on the cutoff's own
    # date passed. Compare the build's own clock; an undateable build is refused.
    built = None
    try:
        gd = Path(st.get("dir") or graph_dir)
        meta = json.loads((gd / str(st.get("build_id")) / "receipt.json").read_text(encoding="utf-8"))
        built = _utc(meta.get("built_utc"))
    except (OSError, ValueError, TypeError):
        built = None
    if built is None:
        return (lambda t: []), {"status": "GRAPH_BUILD_TIME_UNKNOWN", "as_of": g.as_of}
    if built > cutoff:
        return (lambda t: []), {"status": "GRAPH_AFTER_FREEZE", "as_of": g.as_of,
                                "built_utc": _iso(built)}

    def neigh(t: str) -> list[dict]:
        out, seen = [], set()
        for e in g.out.get(UG.company_id(t), []):
            if not str(e.dst).startswith("company:"):
                continue
            sym = str(e.dst).split(":", 1)[1]
            if sym in seen or sym == t:
                continue
            seen.add(sym)
            out.append({"ticker": sym, "relation": e.type})
            if len(out) >= k:
                break
        return out
    return neigh, {"status": "OK", "as_of": g.as_of, "build_id": st.get("build_id")}


# ─────────────────────────────── the packet ──────────────────────────────────

def news_packet(base: dict, *, ticker: str, typed: dict, neighbours: list[dict],
                cutoff: datetime, lookback_hours: float, max_direct: int,
                max_neigh_rows: int, excluded_run: Counter) -> tuple[dict, dict]:
    """(packet, provenance). The packet is `base` plus two lists; `base` is
    untouched so its hash pairs with the plain arm's row."""
    ex_direct: Counter = Counter()
    direct = _dedupe_newest(pit_filter(typed["by_ticker"].get(ticker, []), cutoff=cutoff,
                                       lookback_hours=lookback_hours, excluded=ex_direct),
                            max_direct)
    ex_neigh: Counter = Counter()
    pool = []
    for n in neighbours:
        for rec in pit_filter(typed["by_ticker"].get(n["ticker"], []), cutoff=cutoff,
                              lookback_hours=lookback_hours, excluded=ex_neigh):
            pool.append((n, rec))
    direct_ids = {r["row"].get("item_id") for r in direct}
    pool = [(n, r) for n, r in pool if r["row"].get("item_id") not in direct_ids]
    pool.sort(key=lambda nr: str(nr[1]["row"].get("published_utc")), reverse=True)
    neigh_rows, seen = [], set()
    for n, rec in pool:
        key = rec["row"].get("item_id") or rec["row"].get("topic")
        if key in seen:
            continue
        seen.add(key)
        c = _compact(rec, n["ticker"])
        c["relation_to_subject"] = n["relation"]
        neigh_rows.append(c)
        if len(neigh_rows) >= max_neigh_rows:
            break
    excluded_run.update(ex_direct)
    excluded_run.update(ex_neigh)
    pk = {**base,
          "news_typed": [_compact(r, ticker) for r in direct],
          "neighbour_news": neigh_rows,
          "news_freeze_cutoff_utc": _iso(cutoff),
          "news_lookback_hours": float(lookback_hours)}
    prov = {"n_news_direct": len(direct), "n_news_neighbour": len(neigh_rows),
            "news_item_ids": [r["row"].get("item_id") for r in direct],
            "neighbours": [n["ticker"] for n in neighbours],
            "excluded_direct": dict(ex_direct), "excluded_neighbour": dict(ex_neigh)}
    return pk, prov


# ─────────────────────────────── the plain arm ───────────────────────────────

def plain_receipt(day: str, *, rdir: Optional[Path] = None) -> Optional[dict]:
    p = (Path(rdir) if rdir else NIF.forecast_day_dir()) / f"day_{day}.json"
    try:
        return {**json.loads(p.read_text(encoding="utf-8")), "_path": str(p)}
    except (OSError, ValueError):
        return None


def _default_ask(model_tokens: int) -> Callable[[dict], dict]:
    def ask(pk: dict) -> dict:
        from backend.services import llm_analyzer as LA
        user = NIF._message(pk, "").lstrip("\n")
        res = LA.call_named("deepseek", CONTRACT_NEWS, user,
                            purpose=str(_c("INVESTIGATOR_NEWS_PURPOSE", "investigator_news")),
                            max_tokens=int(model_tokens), production_budget=False,
                            temperature=float(_c("INVESTIGATOR_NEWS_TEMPERATURE", 0.3)))
        out = (NIF.parse_reply(res.get("text") or "", keys=("probability_1d", "probability_5d"))
               if res.get("ok") else {"refused": f"{res.get('status')}: {res.get('error')}"[:300]})
        out["_call"] = {k: res.get(k) for k in ("status", "model", "served_model", "cost_usd",
                                                 "budget_charge_usd", "billing_status",
                                                 "tokens_in", "tokens_out", "latency_s",
                                                 "reservation_id", "error")}
        return out
    return ask


def run(day: str, *, tickers: Optional[list[str]] = None, budget_usd: Optional[float] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
        plain: Optional[dict] = None, plain_dir: Optional[Path] = None,
        packet_fn: Optional[Callable[[str], Optional[dict]]] = None,
        ask_fn: Optional[Callable[[dict], dict]] = None,
        typed_path: Optional[Path] = None,
        neighbours_fn: Optional[Callable[[str], list[dict]]] = None,
        graph_dir: Optional[Path] = None,
        ledger_path: Optional[Path] = None, out_dir: Optional[Path] = None,
        write: bool = True, smoke: bool = False,
        plain_hashes: Optional[dict] = None) -> dict:
    """One night of the paired arm. Returns the receipt (also written).

    `smoke=True` is the attended single-name proof of the packet and the row:
    cutoff = the run clock (NOT paired with the plain arm), specialist
    `SMOKE_SPECIALIST` (never pooled), at most `SMOKE_MAX_NAMES` names, and only
    into an explicit ledger that is not the live one."""
    from backend.services import belief_state as B
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    now = now_fn()
    budget = float(budget_usd if budget_usd is not None
                   else _c("INVESTIGATOR_NEWS_RUN_BUDGET_USD", 0.18))
    lookback = float(_c("INVESTIGATOR_NEWS_LOOKBACK_HOURS", 48))
    max_direct = int(_c("INVESTIGATOR_NEWS_MAX_DIRECT_ROWS", 5))
    max_neigh = int(_c("INVESTIGATOR_NEWS_MAX_NEIGHBOURS", 5))
    max_neigh_rows = int(_c("INVESTIGATOR_NEWS_MAX_NEIGHBOUR_ROWS", 3))
    per_call_reserve = float(_c("INVESTIGATOR_NEWS_PER_CALL_RESERVE_USD", 0.004))
    odir = Path(out_dir) if out_dir else receipt_dir()
    rec: dict = {"receipt": "investigator_news_day", "day": day, "specialist": SPECIALIST,
                 "pair_specialist": PAIR_SPECIALIST, "licence": "PRODUCT_EXPERIMENT",
                 "model_version": MODEL_VERSION, "budget_usd": budget, "state": "RUNNING",
                 "started_utc": _iso(now), "done": [], "refused": [], "unpriced": [],
                 "not_asked": [], "n_rows_written": 0, "spent_usd": 0.0, "calls": 0,
                 "excluded_news_rows": {}, "names_with_news": 0,
                 "base_mismatch": [], "base_unverified": [],
                 "not_read_by_plan": ("E[r] FORECAST_GRADED reads investigator: only; "
                                      "forecast_writers lists investigator_news: as NOT READ")}

    def finish(state: str, rc: int, why: Optional[str] = None) -> dict:
        rec.update(state=state, exit_code=rc, ended_utc=_iso(now_fn()))
        if why:
            rec["why"] = why
        if write:
            odir.mkdir(parents=True, exist_ok=True)
            NIF.write_receipt(odir / f"day_{day}.json", rec)
        return rec

    if now.date().isoformat() != day:
        return finish("REFUSED_PAIR_DAY_MISMATCH", RC_REFUSED,
                      f"the run clock is {now.date()} UTC, not {day}: the grader enters every "
                      "row at the close of its made_at UTC date, so a row made on another day "
                      "would not pair with the plain arm's entry")
    plain = plain if plain is not None else plain_receipt(day, rdir=plain_dir)
    if not plain or not plain.get("done"):
        return finish("REFUSED_NO_PLAIN_ARM", RC_REFUSED,
                      f"no {PAIR_SPECIALIST} receipt with forecast names for {day} "
                      f"({(plain or {}).get('state')}); the arm only runs paired")
    p_start = _utc(plain.get("started_utc"))
    if p_start is None:
        return finish("REFUSED_NO_PLAIN_ARM", RC_REFUSED, "plain arm receipt has no started_utc")
    cutoff = now if smoke else min(now, p_start)
    names = [str(t).upper() for t in (tickers or plain["done"])]
    spec = SMOKE_SPECIALIST if smoke else SPECIALIST
    if smoke:
        live = Path(B.PREDICTIONS).resolve()
        if (ledger_path is None or Path(ledger_path).resolve() == live or not tickers
                or len(names) > SMOKE_MAX_NAMES):
            return finish("REFUSED_SMOKE_SCOPE", RC_REFUSED,
                          f"smoke needs --tickers (<= {SMOKE_MAX_NAMES}) and an explicit "
                          "--ledger that is not the live predictions ledger")
        rec.update(smoke=True, specialist=spec)
    not_plain = [t for t in names if t not in set(plain["done"])]
    rec.update(freeze_cutoff_utc=_iso(cutoff), plain_receipt=plain.get("_path"),
               plain_started_utc=plain.get("started_utc"), names_requested=len(names),
               names_not_in_plain_arm=not_plain)
    typed = load_typed_rows(Path(typed_path) if typed_path else digest_cache_path(),
                            cutoff=cutoff, lookback_hours=lookback)
    rec["typed_source"] = {k: v for k, v in typed.items() if k != "by_ticker"}
    if not typed.get("exists"):
        return finish("REFUSED_NO_TYPED_NEWS", RC_REFUSED,
                      f"no typed digest cache at {typed['path']}: without it the arm is the "
                      "plain arm with a different contract, which measures nothing")
    if neighbours_fn is None:
        neighbours_fn, gstat = graph_neighbours_fn(graph_dir=graph_dir, cutoff=cutoff, k=max_neigh)
    else:
        gstat = {"status": "INJECTED"}
    rec["graph"] = gstat
    if packet_fn is None:
        inputs = NIF.evidence_inputs(asof=day)
        packet_fn = lambda t: NIF.packet_for(t, inputs)               # noqa: E731
    ask_fn = ask_fn or _default_ask(int(_c("INVESTIGATOR_NEWS_MAX_TOKENS", 700)))

    # review 3: the base packet is rebuilt from the LATEST bars/filings at this
    # run's clock; if they refreshed after the plain arm froze its row, the two
    # packets differ and the difference would be credited to news. Compare with
    # the plain row's own hash BEFORE paying; pair_report re-checks every pair.
    if plain_hashes is None and not smoke:
        plain_hashes = plain_base_hashes(day, ledger_path)
    excluded: Counter = Counter()
    built = []
    for t in names:
        base = packet_fn(t)
        if base is None:
            rec["unpriced"].append(t)
            continue
        bh = B._hash(base)
        if not smoke:
            known = (plain_hashes or {}).get(t)
            if known and bh not in known:
                rec["base_mismatch"].append(t)
                continue
            if not known:
                rec["base_unverified"].append(t)
        pk, prov = news_packet(base, ticker=t, typed=typed, neighbours=neighbours_fn(t),
                               cutoff=cutoff, lookback_hours=lookback, max_direct=max_direct,
                               max_neigh_rows=max_neigh_rows, excluded_run=excluded)
        prov["base_packet_hash"] = bh
        built.append((t, pk, prov))
    rec["excluded_news_rows"] = dict(excluded)
    rec["names_with_news"] = sum(1 for _, _, p in built if p["n_news_direct"] + p["n_news_neighbour"])
    # names WITH news first: if the budget ends the run, the informative pairs exist
    built.sort(key=lambda x: -(x[2]["n_news_direct"] + x[2]["n_news_neighbour"]))

    max_tokens = int(_c("INVESTIGATOR_NEWS_MAX_TOKENS", 700))
    for i, (t, pk, prov) in enumerate(built):
        # the guard's own quote for THIS packet, never less than the fixed floor
        # (review 3: a large packet's reservation exceeds the fixed estimate)
        reserve_usd = max(per_call_reserve, _quote_usd(pk, max_tokens))
        if rec["spent_usd"] + reserve_usd > budget:
            rec["not_asked"] = [x[0] for x in built[i:]]
            return finish("PARTIAL_RUN_BUDGET", RC_PARTIAL,
                          f"spent ${rec['spent_usd']:.4f}; the next call could pass the run "
                          f"budget ${budget:.2f}; {len(rec['not_asked'])} name(s) not asked")
        ans = ask_fn(pk)
        call = ans.pop("_call", {}) or {}
        rec["calls"] += 1
        charge = call.get("budget_charge_usd")
        if charge is None:
            charge = call.get("cost_usd")
        rec["spent_usd"] = round(rec["spent_usd"] + float(charge or 0.0), 6)
        if call.get("status") == "BUDGET_REFUSED":
            rec["not_asked"] = [x[0] for x in built[i:]]
            return finish("REFUSED_GUARD", RC_REFUSED, str(call.get("error") or "")[:400])
        ps = {h: ans.get(f"probability_{h}d") for h in NIF.DAILY_HORIZONS}
        if "refused" in ans or not all(isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0
                                       for v in ps.values()):
            rec["refused"].append({"ticker": t, "why": str(ans.get("refused")
                                                           or f"probabilities {ps}")[:200]})
            if len(rec["refused"]) >= 3 and not rec["done"]:
                rec["not_asked"] = [x[0] for x in built[i + 1:]]
                return finish("REFUSED_DEPENDENCY", RC_REFUSED,
                              "three refusals before any forecast: the call path is down")
            continue
        recs = []
        made_at = _iso(now_fn())
        for h, raw in ps.items():
            raw = float(raw)
            prob, basis = NIF.recalibrate(raw, B.Observable.BEATS_BENCHMARK)
            recs.append(B.make_prediction(
                ticker=t, specialist=spec, observable=B.Observable.BEATS_BENCHMARK,
                horizon_days=h, probability=prob, benchmark="SPY",
                thesis=json.dumps(ans.get("facts_used"))[:1200],
                counter_thesis=str(ans.get("falsifier"))[:800],
                next_observable=json.dumps(ans.get("what_is_missing"))[:300],
                model=str(call.get("served_model") or call.get("model") or "deepseek"),
                model_version=MODEL_VERSION, prompt=CONTRACT_NEWS, input_snapshot=pk,
                made_at=made_at, licence="PRODUCT_EXPERIMENT", decision_date=day,
                raw_probability=raw, shrink_basis=basis,
                inputs_used={**prov, "pair_specialist": None if smoke else PAIR_SPECIALIST,
                             "smoke": smoke,
                             "freeze_cutoff_utc": _iso(cutoff)},
                notes_text=(f"investigator_news {day}: raw {raw:.3f} ({basis}); news "
                            f"{prov['n_news_direct']} direct + {prov['n_news_neighbour']} "
                            f"neighbour; pair {PAIR_SPECIALIST}")))
        if write:
            B.append(recs, path=ledger_path)
        rec["n_rows_written"] += len(recs) if write else 0
        rec["done"].append(t)
        if write:
            NIF.write_receipt(odir / f"day_{day}.json", rec)
    if not rec["done"]:
        return finish("DEGRADED", RC_REFUSED, "zero forecasts written")
    lost = len(rec["refused"]) + len(rec["base_mismatch"])
    share = lost / max(1, lost + len(rec["done"]))
    limit = float(_c("INVESTIGATOR_NEWS_MAX_REFUSED_SHARE", 0.5))
    if share > limit:
        return finish("DEGRADED", RC_REFUSED,
                      f"{lost} of {lost + len(rec['done'])} name(s) refused or unpaired "
                      f"({share:.0%} > {limit:.0%}); {len(rec['done'])} forecast(s) written")
    return finish("DONE", RC_DONE)


def _quote_usd(pk: dict, max_tokens: int) -> float:
    """The provider guard's reservation for this packet (USD); 0 if unquotable,
    which leaves the fixed floor in force."""
    try:
        from backend.services import provider_budget as PB
        user = NIF._message(pk, "").lstrip("\n")
        return PB.quote(CONTRACT_NEWS, user, int(max_tokens))["reserved_units"] / PB.SCALE
    except Exception:                                                # noqa: BLE001
        return 0.0


def plain_base_hashes(day: str, ledger_path: Optional[Path] = None) -> dict:
    """ticker -> {input_snapshot_hash} of the plain arm's rows for `day`."""
    try:
        rows = _ledger_rows(Path(ledger_path) if ledger_path else None, (PAIR_SPECIALIST,))
    except OSError:
        return {}
    out: dict = {}
    for r in rows:
        if str(r.get("decision_date") or str(r.get("made_at"))[:10]) != day:
            continue
        h = r.get("input_snapshot_hash")
        if h:
            out.setdefault(str(r.get("ticker")).upper(), set()).add(h)
    return out


# ─────────────────────────────── the comparison ──────────────────────────────

def _brier(r: dict) -> Optional[float]:
    b = r.get("brier")
    if b is not None:
        try:
            return float(b)
        except (TypeError, ValueError):
            return None
    o, p = r.get("outcome"), r.get("probability")
    if o is None or p is None:
        return None
    return (float(p) - float(o)) ** 2


def pair_report(rows: Iterable[dict], *, horizon: int = 1) -> dict:
    """Paired Brier difference news - plain on identical (ticker, decision_date, h)
    AND identical base packet (the news row's `inputs_used.base_packet_hash`
    equals the plain row's `input_snapshot_hash`), graded rows only, with a
    date-clustered standard error (a day's names share the market). Split by
    whether the news arm's packet had any admitted news.

    Review 3: the base packet is rebuilt at the news arm's run time from the
    latest bars and filings, so a late run can carry a newer close or quarter
    than the plain row; pooling that pair credits the difference to news. Such
    pairs, and pairs whose hash cannot be checked, are excluded and counted."""
    plain: dict = {}
    news: dict = {}
    for r in rows:
        if int(r.get("horizon_days") or 0) != horizon or r.get("void_reason"):
            continue
        b = _brier(r)
        if b is None:
            continue
        k = (r.get("ticker"), str(r.get("decision_date") or str(r.get("made_at"))[:10]))
        if r.get("specialist") == PAIR_SPECIALIST:
            plain[k] = (b, r.get("input_snapshot_hash"))
        elif r.get("specialist") == SPECIALIST:
            iu = r.get("inputs_used") or {}
            news[k] = (b, int(iu.get("n_news_direct") or 0) + int(iu.get("n_news_neighbour") or 0),
                       iu.get("base_packet_hash"))
    excluded = Counter({"base_mismatch": 0, "base_unknown": 0, "news_without_plain": 0,
                        "plain_without_news": sum(1 for k in plain if k not in news)})
    valid: dict = {}
    for k, (b, n, bh) in news.items():
        if k not in plain:
            excluded["news_without_plain"] += 1
            continue
        pb, ph = plain[k]
        if not bh or not ph:
            excluded["base_unknown"] += 1
        elif bh != ph:
            excluded["base_mismatch"] += 1
        else:
            valid[k] = (b - pb, n)
    out: dict = {"horizon": horizon,
                 "pair_on": "(ticker, decision_date, horizon) and base_packet_hash == "
                            "plain input_snapshot_hash",
                 "difference": "brier(news) - brier(plain); negative = news arm better",
                 "excluded": dict(excluded),
                 "caveat": ("the arms also differ in transport and temperature (disclosed); the "
                            "with/without-news split is not a clean control either, because the "
                            "names that carried news are not exchangeable with those that did not")}
    for label, keep in (("all", lambda n: True), ("with_news", lambda n: n > 0),
                        ("without_news", lambda n: n == 0)):
        d_by_day: dict = {}
        for k, (diff, n) in valid.items():
            if keep(n):
                d_by_day.setdefault(k[1], []).append(diff)
        diffs = [x for v in d_by_day.values() for x in v]
        if not diffs:
            out[label] = {"n_pairs": 0, "n_days": 0}
            continue
        mean = sum(diffs) / len(diffs)
        day_means = [sum(v) / len(v) for v in d_by_day.values()]
        nd = len(day_means)
        se = (math.sqrt(sum((m - sum(day_means) / nd) ** 2 for m in day_means) / (nd - 1)) / math.sqrt(nd)
              if nd > 1 else None)
        out[label] = {"n_pairs": len(diffs), "n_days": nd, "mean_brier_diff": round(mean, 6),
                      "se_date_clustered": None if se is None else round(se, 6),
                      "t": None if not se else round(mean / se, 2)}
    out["claim"] = "none: an observation; a difference needs the MDE's n before it says anything"
    return out


def mde_table(rows: Iterable[dict], *, horizon: int = 1, alpha: float = 0.05,
              power: float = 0.80, rho: float = 0.5,
              names_per_night: Optional[float] = None,
              deltas_skill: tuple = (0.01, 0.02, 0.05)) -> dict:
    """Paired forecasts needed to detect a Brier-skill improvement, from the PLAIN
    arm's own graded rows: per-row Brier sd, the date design effect (names on one
    day share the market), and an assumed correlation `rho` between the two
    arms' per-row Brier on the same name/day (stated, not measured: no pairs
    exist yet). Skill is relative to a coin (Brier 0.25), so +1% skill is a
    Brier reduction of 0.0025. `names_per_night` (default: the plain arm's) is
    the number of PAIRS a night adds, e.g. only the names that carried news."""
    from statistics import NormalDist
    briers, by_day = [], {}
    for r in rows:
        if r.get("specialist") != PAIR_SPECIALIST or int(r.get("horizon_days") or 0) != horizon:
            continue
        if r.get("void_reason"):
            continue
        b = _brier(r)
        if b is None:
            continue
        briers.append(b)
        by_day.setdefault(str(r.get("decision_date") or str(r.get("made_at"))[:10]), []).append(b)
    if len(briers) < 30 or len(by_day) < 3:
        return {"status": "INSUFFICIENT", "n_graded": len(briers), "n_days": len(by_day)}
    n = len(briers)
    mean = sum(briers) / n
    var = sum((b - mean) ** 2 for b in briers) / (n - 1)
    m_bar = n / len(by_day)
    day_means = [sum(v) / len(v) for v in by_day.values()]
    var_day = sum((x - mean) ** 2 for x in day_means) / (len(day_means) - 1)
    # ICC from the variance of day means: var(day mean) ~ var * (1 + (m-1) icc) / m
    icc = max(0.0, min(1.0, ((var_day * m_bar / var) - 1) / max(m_bar - 1, 1)))
    m_pairs = float(names_per_night) if names_per_night else m_bar
    deff = 1 + (m_pairs - 1) * icc
    sd_diff = math.sqrt(2 * var * (1 - rho))
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    rows_out = []
    for s in deltas_skill:
        delta = 0.25 * s
        n_iid = (z * sd_diff / delta) ** 2
        n_pairs = n_iid * deff
        rows_out.append({"skill_improvement": s, "brier_reduction": round(delta, 5),
                         "pairs_iid": math.ceil(n_iid), "pairs_with_date_deff": math.ceil(n_pairs),
                         "nights": math.ceil(n_pairs / m_pairs)})
    return {"status": "OK", "horizon": horizon, "n_graded_plain": n, "n_days": len(by_day),
            "names_per_day": round(m_bar, 1), "mean_brier": round(mean, 5),
            "brier_skill_vs_coin": round(1 - mean / 0.25, 4), "sd_brier": round(math.sqrt(var), 5),
            "icc_date": round(icc, 4), "pairs_per_night": m_pairs,
            "design_effect": round(deff, 2), "rho_assumed": rho, "sd_diff": round(sd_diff, 5),
            "alpha": alpha, "power": power, "table": rows_out}


def _ledger_rows(path: Optional[Path], specialists: tuple) -> list[dict]:
    """Rows of the named specialists from a ledger (default: the live one)."""
    from backend.services import belief_state as B
    p = Path(path) if path else B.PREDICTIONS
    out = []
    needles = tuple(f'"{s}"' for s in specialists)
    with p.open(encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if not any(n in ln for n in needles):
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("specialist") in specialists:
                out.append(r)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")          # type: ignore[union-attr]
        except Exception:                                            # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="night_investigator_news")
    ap.add_argument("--day", default=None, help="UTC day; default today (must equal the run clock)")
    ap.add_argument("--tickers", default=None, help="comma list; default the plain arm's names")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--ledger", default=None, help="forecast ledger (default: the live one)")
    ap.add_argument("--out", default=None, help="receipt dir (default <optimus>/investigator_news)")
    ap.add_argument("--graph-dir", default=None)
    ap.add_argument("--dry-run", action="store_true", help="build packets, print the first, ask nothing")
    ap.add_argument("--smoke", action="store_true",
                    help="attended proof: cutoff = now, <= 3 --tickers, explicit non-live --ledger")
    ap.add_argument("--pair-report", action="store_true")
    ap.add_argument("--mde", action="store_true")
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--rho", type=float, default=0.5, help="MDE: assumed between-arm Brier correlation")
    ap.add_argument("--pairs-per-night", type=float, default=None,
                    help="MDE: pairs a night adds (default: the plain arm's names per day)")
    a = ap.parse_args(argv)
    if a.pair_report or a.mde:
        rows = _ledger_rows(Path(a.ledger) if a.ledger else None, (PAIR_SPECIALIST, SPECIALIST))
        res = (pair_report(rows, horizon=a.horizon) if a.pair_report else
               mde_table(rows, horizon=a.horizon, rho=a.rho, names_per_night=a.pairs_per_night))
        print(json.dumps(res, indent=1))
        if a.pair_report:
            # a report that pooled nothing is red, not an empty success (review 3)
            return 0 if (res.get("all") or {}).get("n_pairs") else RC_REFUSED
        return 0 if res.get("status") == "OK" else RC_REFUSED
    day = a.day or datetime.now(timezone.utc).date().isoformat()
    tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()] if a.tickers else None
    if a.dry_run:
        captured: list = []

        def ask(pk: dict) -> dict:
            captured.append(pk)
            return {"refused": "dry-run: nothing asked"}
        rec = run(day, tickers=tickers, budget_usd=a.budget_usd, ask_fn=ask,
                  graph_dir=Path(a.graph_dir) if a.graph_dir else None, write=False)
        if captured:
            print(json.dumps(captured[0], indent=1, default=str))
        print(json.dumps({k: rec.get(k) for k in ("state", "freeze_cutoff_utc", "names_requested",
                                                  "names_with_news", "excluded_news_rows",
                                                  "graph", "unpriced")}, indent=1, default=str))
        return 0
    rec = run(day, tickers=tickers, budget_usd=a.budget_usd, smoke=a.smoke,
              graph_dir=Path(a.graph_dir) if a.graph_dir else None,
              ledger_path=Path(a.ledger) if a.ledger else None,
              out_dir=Path(a.out) if a.out else None)
    print(json.dumps({k: rec.get(k) for k in ("state", "exit_code", "why", "spent_usd", "calls",
                                              "n_rows_written", "names_with_news",
                                              "excluded_news_rows", "graph", "freeze_cutoff_utc")},
                     indent=1, default=str))
    return int(rec.get("exit_code", RC_REFUSED))


if __name__ == "__main__":
    raise SystemExit(main())
