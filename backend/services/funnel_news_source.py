"""CH-14a -- news and fresh filings ADD names to the opportunity funnel.

The funnel (`opportunity_funnel`) took no name from news: of 30 top idiosyncratic
movers on 2026-11-11, 18 were in the universe and never became a candidate, and 3
of those had a fresh overnight 8-K before the open. This module turns two local,
already-collected inputs into names the funnel must CONSIDER:

    news    the newest world digest WITH typed rows inside the freshness window
            (`optimus/digest/world_digest_*.json`): each theme's `top_tickers`
            (tickers the extractor tied to articles) and every typed ticker
            implication the digest did not refuse. A name needs at least one
            MENTIONED row (in an article); model-inferred rows (`mentioned:
            False`) are counted but never offer a name by themselves. A ticker
            must map to an issuer in `news_entities/issuers.csv` (the issuer table
            the universe graph uses); a bare word is never enough.
    filing  8-K / 8-K/A rows of `optimus/official/tables/filing_events.jsonl`
            with the SEC's own ticker field and at least one item on
            `FUNNEL_NEWS_FILING_ITEMS`, public after the previous US close and
            before the next open (weekday clock; exchange holidays NOT modelled)

What a news name may and may not do (`admit`):
  * the ranker's candidate list is emitted EXACTLY as with the flag off: same
    names, same order, same scores. A ranker name that news also mentions gets
    an extra tag in `sources` and does not move. Consumers that read the
    candidate list (pc_own_index takes the first N in file order) see no change.
  * every other news/filing name goes to a SEPARATE block, `added_by_source`,
    with its sources, net direction, evidence, the screens it passed or failed
    (stage 0 listed common/ADR, the stage-1 eligibility screens, stage-3
    fundamentals) and the ranker-only stages it did NOT face (the 1,500
    truncation, the stage-2 low-volatility shortlist, the stage-3 order cut, the
    stage-4 profitability rank). It sets no weight and changes no score.
  * the snapshot therefore stores the control: a later grader can compare the
    ranker's list against ranker + added.

Freshness is judged on CONTENT: a digest with zero typed implications is skipped
(the next older one inside the window is used, and the skip is printed);
older than FUNNEL_NEWS_DIGEST_MAX_AGE_HOURS (from its own as_of, never mtime) is
STALE. No look-ahead: a digest whose stamp or as_of is after the build time, or a
filing public or first seen after it, is refused and counted; a date-only or
naive stamp is refused, never assumed midnight UTC. The stamp used is recorded
per evidence row.

No LLM, no network. Off by default (`config.FUNNEL_NEWS_SOURCE_ENABLED`).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from backend import config as _cfg

SOURCE_RANKER = "ranker"
SOURCE_NEWS = "news"
SOURCE_FILING = "filing"
NEWS_SOURCES = (SOURCE_NEWS, SOURCE_FILING)
#: CH-35 slice 2: event nodes as a third source (EVENT_NODES_FUNNEL_SOURCE_ENABLED, default OFF)
SOURCE_EVENT = "event"
ALL_SOURCES = (SOURCE_NEWS, SOURCE_FILING, SOURCE_EVENT)

FILING_FORMS = frozenset({"8-K", "8-K/A"})
_STAMP = re.compile(r"^(\d{8}T\d{6}Z)$")
_TICKER = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")   # == world_digest._TICKER

#: The ranker-only stages an added name never faced (item 3 of the review).
RANKER_ONLY_STAGES = (
    "stage1_size_stratified_truncation_to_1500",
    "stage2_low_volatility_shortlist_to_250",
    "stage3_shortlist_order_to_40",
    "stage4_profitability_rank_to_25",
)


# ─────────────────────────────── small helpers ──────────────────────────────

def _to_dt(ts: Any) -> Optional[datetime]:
    """An aware UTC datetime, or None. A date-only or naive stamp is REFUSED
    (None), never assumed to be midnight UTC. The digest file stamp
    `YYYYMMDDTHHMMSSZ` is explicitly UTC and accepted."""
    if not ts:
        return None
    s = str(ts).strip()
    m = _STAMP.match(s)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if "T" not in s and " " not in s:
        return None                                  # date only
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None                                  # naive
    return t.astimezone(timezone.utc)


def _iso(t: Optional[datetime]) -> Optional[str]:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds") if t else None


def _issuer_id(sym: str) -> str:
    from backend.services.universe_graph import company_id  # the graph's node id
    return company_id(sym)


def digest_dir() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / "digest"


def filings_path() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / "official" / "tables" / "filing_events.jsonl"


def issuers_path() -> Path:
    return Path(_cfg.BACKEND_DIR) / "data" / "news_entities" / "issuers.csv"


def load_issuers(path: Optional[Path] = None) -> Optional[dict]:
    """symbol -> primary_name from the issuer table the universe graph reads."""
    p = Path(path) if path else issuers_path()
    if not p.exists():
        return None
    out = {}
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            s = str(r.get("symbol") or "").upper().strip()
            if s:
                out[s] = str(r.get("primary_name") or "")
    return out


def _direction_of(rows: list) -> str:
    ds = {str(e.get("direction")) for e in rows if e.get("direction") in ("up", "down")}
    if ds == {"up"}:
        return "up"
    if ds == {"down"}:
        return "down"
    if ds == {"up", "down"}:
        return "mixed"
    return "unstated"


# ─────────────────────────────── news (digest) ──────────────────────────────

def _typed_counts(themes: list) -> tuple[int, int]:
    n_typed = sum(len(th.get("implications") or []) for th in themes)
    n_tick = sum(len(th.get("top_tickers") or []) for th in themes) + sum(
        1 for th in themes for i in th.get("implications") or [] if i.get("subject_type") == "ticker")
    return n_typed, n_tick


def digest_names(build_time: datetime, *, root: Optional[Path] = None,
                 max_age_hours: Optional[float] = None,
                 issuers: Optional[dict] = None) -> dict:
    """Names from the newest digest WITH typed rows, stamped before `build_time`
    and inside the freshness window; every skip is printed with its reason."""
    d = Path(root) if root else digest_dir()
    max_age = float(_cfg.FUNNEL_NEWS_DIGEST_MAX_AGE_HOURS if max_age_hours is None
                    else max_age_hours)
    out: dict = {"dir": str(d), "digest_id": None, "as_of": None, "age_hours": None,
                 "n_themes": 0, "n_typed_rows": 0, "n_ticker_rows": 0,
                 "refused_after_build": [], "skipped": [], "status": "MISSING",
                 "names": {}, "inferred_only_not_offered": [], "no_issuer_mapping": [],
                 "degradations": []}
    files = sorted(d.glob("world_digest_*.json")) if d.exists() else []
    if not files:
        out["degradations"].append(f"NEWS_DIGEST_MISSING: no world_digest_*.json under {d}")
        return out
    chosen = None
    newest_seen = None
    for fp in reversed(files):
        sid = fp.stem.removeprefix("world_digest_")
        stamp = _to_dt(sid)
        if stamp is None:
            out["skipped"].append({"digest_id": sid, "why": "unparsable file stamp"})
            continue
        if stamp > build_time:
            out["refused_after_build"].append(sid)
            continue
        try:
            got = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out["skipped"].append({"digest_id": sid, "why": "unreadable"})
            continue
        if not isinstance(got, dict) or got.get("dry_run") or got.get("themes") is None:
            out["skipped"].append({"digest_id": sid, "why": "dry run or no themes"})
            continue
        raw_as_of = (got.get("world_state") or {}).get("as_of")
        as_of = _to_dt(raw_as_of) if raw_as_of else stamp
        if as_of is None:
            out["skipped"].append({"digest_id": sid, "why": f"as_of {raw_as_of!r} is date-only "
                                                           f"or naive: refused"})
            continue
        if as_of > build_time:        # started before, finished after: still the future
            out["refused_after_build"].append(sid)
            continue
        age_h = (build_time - as_of).total_seconds() / 3600.0
        newest_seen = newest_seen or (sid, round(age_h, 2))
        if age_h > max_age:
            break                     # every older file is older still
        n_typed, _ = _typed_counts(got.get("themes") or [])
        if n_typed == 0:
            out["skipped"].append({"digest_id": sid, "age_hours": round(age_h, 2),
                                   "why": "0 typed implications (EMPTY) -- an older digest "
                                          "with typed rows is used instead"})
            continue
        chosen = (sid, got, as_of, age_h)
        break
    if chosen is None:
        if newest_seen is None:
            out["degradations"].append(
                f"NEWS_DIGEST_MISSING: no usable digest at or before {_iso(build_time)} "
                f"({len(out['refused_after_build'])} refused as after build time)")
        elif any("EMPTY" in s["why"] for s in out["skipped"]):
            out["status"] = "EMPTY"
            out["degradations"].append(
                f"NEWS_DIGEST_EMPTY: no digest with typed implications inside {max_age:g} h "
                f"(newest {newest_seen[0]}, {newest_seen[1]} h) -- contributes 0 names")
        else:
            out["status"] = "STALE"
            out["degradations"].append(
                f"NEWS_DIGEST_STALE: newest digest {newest_seen[0]} is {newest_seen[1]} h old "
                f"(> {max_age:g} h) -- contributes 0 names")
        return out
    sid, got, as_of, age_h = chosen
    themes = got.get("themes") or []
    n_typed, n_tick = _typed_counts(themes)
    did = str(got.get("stamp") or sid)
    stamp_used = _iso(as_of)
    rows: dict[str, list] = {}
    for th in themes:
        title = str(th.get("title") or "")[:120]
        for t in th.get("top_tickers") or []:
            t = str(t).upper().strip()
            rows.setdefault(t, []).append(
                {"source": SOURCE_NEWS, "via": "top_ticker", "theme": title, "direction": None,
                 "mentioned": True, "digest_id": did, "stamp_used": stamp_used})
        for imp in th.get("implications") or []:
            if imp.get("subject_type") != "ticker" or imp.get("refused"):
                continue
            t = str(imp.get("subject") or "").upper().strip()
            rows.setdefault(t, []).append(
                {"source": SOURCE_NEWS, "via": "implication", "theme": title,
                 "direction": imp.get("direction"), "order": imp.get("order"),
                 "confidence": imp.get("confidence"),
                 "mentioned": bool(imp.get("mentioned")), "digest_id": did,
                 "stamp_used": stamp_used})
    names = {}
    for t, ev in sorted(rows.items()):
        if not _TICKER.match(t):
            continue
        if issuers is None or t not in issuers:
            out["no_issuer_mapping"].append(t)
            continue
        if not any(e["mentioned"] for e in ev):
            out["inferred_only_not_offered"].append(t)
            continue
        names[t] = ev
    out.update({"digest_id": did, "as_of": stamp_used, "age_hours": round(age_h, 2),
                "n_themes": len(themes), "n_typed_rows": n_typed, "n_ticker_rows": n_tick,
                "fresh_flag_ignored": got.get("fresh"), "status": "FRESH", "names": names})
    if issuers is None:
        out["degradations"].append("ISSUER_MAP_MISSING: news_entities/issuers.csv not found -- "
                                   "no digest ticker can be mapped, 0 news names offered")
    if out["skipped"]:
        out["degradations"].append(
            "NEWS_DIGEST_FALLBACK: used " + did + "; skipped " + "; ".join(
                f"{s['digest_id']} ({s['why']})" for s in out["skipped"]))
    if n_tick == 0:
        out["degradations"].append(f"NEWS_DIGEST_NO_TICKERS: digest {did} has {n_typed} typed rows "
                                   f"and 0 ticker rows -- contributes 0 names")
    return out


# ─────────────────────────────── filings (8-K) ──────────────────────────────

def overnight_window(build_time: datetime) -> tuple[datetime, datetime]:
    """(previous US close, min(build_time, next open)) in UTC; weekdays only."""
    import pandas as pd
    et = pd.Timestamp(build_time).tz_convert("America/New_York")
    close = et.normalize() + pd.Timedelta(hours=16)
    while close > et or close.weekday() >= 5:
        close = (close - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=16)
    nxt = close.normalize() + pd.Timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt = nxt + pd.Timedelta(days=1)
    open_ = nxt + pd.Timedelta(hours=9, minutes=30)
    end = min(et, open_)
    return (close.tz_convert("UTC").to_pydatetime(), end.tz_convert("UTC").to_pydatetime())


def filing_names(build_time: datetime, *, path: Optional[Path] = None,
                 items: Optional[Iterable[str]] = None) -> dict:
    """8-K filers public inside the overnight window, knowable by build time, with
    at least one allow-listed item."""
    p = Path(path) if path else filings_path()
    allow = frozenset(str(x) for x in (_cfg.FUNNEL_NEWS_FILING_ITEMS if items is None else items))
    start, end = overnight_window(build_time)
    out: dict = {"path": str(p), "window_utc": [_iso(start), _iso(end)],
                 "window_note": "weekday clock; exchange holidays not modelled",
                 "items_allowed": sorted(allow),
                 "n_8k_rows": 0, "n_8k_with_ticker": 0, "newest_8k_public": None,
                 "refused_after_build": 0, "refused_unstamped": 0, "n_in_window": 0,
                 "n_in_window_item_ok": 0, "dropped_by_item": {}, "status": "MISSING",
                 "names": {}, "degradations": []}
    if not p.exists():
        out["degradations"].append(f"FILINGS_MISSING: {p} does not exist")
        return out
    names: dict[str, list] = {}
    dropped_items: Counter = Counter()
    newest = None
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("form_type") or "") not in FILING_FORMS:
                continue
            out["n_8k_rows"] += 1
            t = str(r.get("ticker") or "").upper().strip()
            if not t:
                continue
            out["n_8k_with_ticker"] += 1
            pub = _to_dt(r.get("public_utc"))
            seen = _to_dt(r.get("first_seen_utc")) if r.get("first_seen_utc") else pub
            if pub is None or seen is None:
                out["refused_unstamped"] += 1
                continue
            knowable = max(pub, seen)
            if pub > build_time or knowable > build_time:
                out["refused_after_build"] += 1
                continue
            newest = pub if newest is None or pub > newest else newest
            if not (start < pub <= end) or not _TICKER.match(t):
                continue
            out["n_in_window"] += 1
            its = [str(x) for x in (r.get("items") or [])]
            ok = [x for x in its if x in allow]
            if not ok:
                for x in its or ["(no items)"]:
                    dropped_items[x] += 1
                continue
            out["n_in_window_item_ok"] += 1
            names.setdefault(t, []).append(
                {"source": SOURCE_FILING, "via": str(r.get("form_type")),
                 "accession": r.get("accession"), "items": its[:8], "items_allowed": ok,
                 "direction": None, "mentioned": True,
                 "public_utc": _iso(pub), "first_seen_utc": _iso(seen),
                 "stamp_used": _iso(knowable)})
    out["newest_8k_public"] = _iso(newest)
    out["dropped_by_item"] = dict(sorted(dropped_items.items()))
    out["names"] = dict(sorted(names.items()))
    if names:
        out["status"] = "FRESH"
    else:
        out["status"] = "NONE_IN_WINDOW"
        out["degradations"].append(
            f"FILINGS_NONE_IN_WINDOW: 0 mapped 8-Ks with an allowed item public in "
            f"({_iso(start)}, {_iso(end)}]; newest knowable 8-K public at {_iso(newest)}")
    return out


# ─────────────────────────────── events (CH-35) ─────────────────────────────

def event_store_path() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / str(_cfg.EVENT_NODES_DIRNAME) / "event_nodes.jsonl"


def event_names(build_time: datetime, *, store: Optional[Path] = None) -> dict:
    """The primary issuer and the connected names (EVENT_NODES_FUNNEL_LINKS) of every
    event node known at `build_time` (version built at or before it) whose importance
    decayed to `build_time` is at least EVENT_NODES_FUNNEL_MIN_IMPORTANCE. Evidence is
    the event id, role and link; never a title."""
    from backend.services import event_nodes as EN
    p = Path(store) if store else event_store_path()
    out: dict = {"path": str(p), "status": "MISSING", "names": {}, "degradations": [],
                 "min_importance": float(_cfg.EVENT_NODES_FUNNEL_MIN_IMPORTANCE),
                 "links": list(_cfg.EVENT_NODES_FUNNEL_LINKS), "n_nodes_known": 0, "n_events_offering": 0}
    if not p.is_file():
        out["degradations"].append(f"EVENT_NODES_STORE_MISSING: {p} does not exist")
        return out
    known = EN.nodes_known_at(p, build_time)
    out["n_nodes_known"] = len(known["nodes"])
    out["n_versions_after_build_skipped"] = known["n_versions_after_t_skipped"]
    links = set(_cfg.EVENT_NODES_FUNNEL_LINKS)
    thr = float(_cfg.EVENT_NODES_FUNNEL_MIN_IMPORTANCE)
    mx = float(_cfg.EVENT_NODES_CONSUMER_MAX_AGE_HOURS)
    names: dict[str, list] = {}
    for n in sorted(known["nodes"].values(), key=lambda n: n["event_id"]):
        fs = _to_dt(n.get("first_seen_utc"))
        if fs is None or fs >= build_time or (build_time - fs).total_seconds() / 3600.0 > mx:
            continue
        roles = EN.roles_of(n)
        b0 = EN.node_brief(n, n["primary_ticker"], build_time, roles[n["primary_ticker"]])
        if b0["importance_at"] < thr:
            continue
        out["n_events_offering"] += 1
        for t, role in roles.items():
            if role["link"] not in links or not _TICKER.match(t):
                continue
            b = EN.node_brief(n, t, build_time, role)
            names.setdefault(t, []).append(
                {"source": SOURCE_EVENT, "via": role["link"], "event_id": b["event_id"],
                 "parent_id": b["parent_id"], "event_primary": b["primary_ticker"], "role": b["role"],
                 "importance_at_build": b["importance_at"], "link_weight": b["link_weight"], "direction": None,
                 "mentioned": role["link"] in ("primary", "co_mention"),
                 "first_seen_utc": b["first_seen_utc"], "stamp_used": b["version_built_utc"]})
    for t in names:
        names[t].sort(key=lambda e: (-e["importance_at_build"], e["event_id"]))
    out["names"] = dict(sorted(names.items()))
    out["status"] = "FRESH" if names else "NONE_ABOVE_THRESHOLD"
    if not names:
        out["degradations"].append(f"EVENTS_NONE_ABOVE_THRESHOLD: 0 of {out['n_nodes_known']} known nodes at "
                                   f"or above importance {thr} at {_iso(build_time)}")
    return out


# ─────────────────────────────── collect + admit ────────────────────────────

def collect(build_time: datetime, *, digest_root: Optional[Path] = None,
            filings: Optional[Path] = None, filings_enabled: Optional[bool] = None,
            max_age_hours: Optional[float] = None, issuers: Any = "default",
            events_enabled: Optional[bool] = None, event_store: Optional[Path] = None) -> dict:
    """Every name news/filings offer, with its sources, direction, evidence and
    the stamp used per evidence row."""
    imap = load_issuers() if isinstance(issuers, str) and issuers == "default" else (
        load_issuers(issuers) if isinstance(issuers, (str, Path)) else issuers)
    dg = digest_names(build_time, root=digest_root, max_age_hours=max_age_hours, issuers=imap)
    use_f = bool(_cfg.FUNNEL_NEWS_FILINGS_ENABLED if filings_enabled is None
                 else filings_enabled)
    fl = filing_names(build_time, path=filings) if use_f else {
        "status": "OFF", "names": {}, "degradations": []}
    use_e = bool(_cfg.EVENT_NODES_FUNNEL_SOURCE_ENABLED if events_enabled is None else events_enabled)
    evb = event_names(build_time, store=event_store) if use_e else None
    per: dict[str, dict] = {}
    for block in (dg, fl) + ((evb,) if evb is not None else ()):
        for t, ev in (block.get("names") or {}).items():
            row = per.setdefault(t, {"issuer_id": _issuer_id(t),
                                     "issuer_name": (imap or {}).get(t), "sources": [],
                                     "evidence": []})
            row["evidence"].extend(ev)
    for row in per.values():
        ev = row["evidence"]
        row["sources"] = [s for s in ALL_SOURCES if any(e["source"] == s for e in ev)]
        news_ev = [e for e in ev if e["source"] == SOURCE_NEWS]
        row["net_direction"] = _direction_of(news_ev)
        row["n_mentioned"] = sum(1 for e in ev if e.get("mentioned"))
        row["n_inferred"] = sum(1 for e in ev if not e.get("mentioned"))
    degr = list(dg.get("degradations") or []) + list(fl.get("degradations") or [])
    dg_pub = {k: v for k, v in dg.items() if k != "names"}
    fl_pub = {k: v for k, v in fl.items() if k != "names"}
    dg_pub["n_names"] = len(dg.get("names") or {})
    fl_pub["n_names"] = len(fl.get("names") or {})
    out = {"build_time": _iso(build_time), "digest": dg_pub, "filings": fl_pub,
           "names": dict(sorted(per.items())), "degradations": degr}
    if evb is not None:
        ev_pub = {k: v for k, v in evb.items() if k != "names"}
        ev_pub["n_names"] = len(evb.get("names") or {})
        out["events"] = ev_pub
        out["degradations"] = degr + list(evb.get("degradations") or [])
    return out


def _strength(t: str, names: dict) -> tuple:
    """Evidence strength, strongest first: news by mentioned rows, all rows and
    the highest stated confidence; filings by allow-listed items and filings."""
    ev = names[t]["evidence"]
    news = [e for e in ev if e["source"] == SOURCE_NEWS]
    if ev and all(e["source"] == SOURCE_EVENT for e in ev):
        # strongest event first, then more events, then the closest link (primary <
        # co-mention < graph link by |weight|), then the ticker
        imp = max((float(e.get("importance_at_build") or 0.0) for e in ev), default=0.0)
        link = min((0.0 if e.get("via") == "primary" else 1.0 if e.get("via") == "co_mention"
                    else 2.0 - min(1.0, abs(float(e.get("link_weight") or 0.0)))) for e in ev)
        return (-imp, -len(ev), link, t)
    if news:
        conf = max((float(e.get("confidence") or 0.0) for e in news), default=0.0)
        return (-sum(1 for e in news if e.get("mentioned")), -len(news), -conf, t)
    items = sum(len(e.get("items_allowed") or []) for e in ev)
    return (-items, -len(ev), 0.0, t)


ScreenFn = Callable[[list], dict]        # names -> {ticker: (Candidate|None, screen)}
EnrichFn = Callable[[list], list]        # Candidates -> enriched Candidates


def both_numbers(receipt: dict) -> str:
    """The two numbers that are never printed one without the other."""
    f = receipt["final"]
    return (f"{f['tagged_in_ranker_final']} of {f['n']} ranker candidates carry a news/filing tag; "
            f"{receipt['added_by_source']['n_added']} names added only by news/filing "
            f"(separate block, not in the candidate list); "
            f"{receipt['offered']['total']} names offered")


def admit(news: dict, ranker_s3: list, ranker_s4: list, *, universe: Iterable[str],
          screen_fn: ScreenFn, enrich_fn: EnrichFn,
          max_enrich_news: Optional[int] = None,
          max_enrich_filing: Optional[int] = None) -> dict:
    """Tag the ranker's lists in place (no move, no re-score) and build the
    separate `added_by_source` block for every other offered name.

    Returns {"stage3": ranker_s3, "final": ranker_s4, "added": [rows], "receipt"}.
    """
    names: dict = news.get("names") or {}
    cap_news = int(_cfg.FUNNEL_NEWS_MAX_ENRICH_NEWS if max_enrich_news is None
                   else max_enrich_news)
    cap_fil = int(_cfg.FUNNEL_NEWS_MAX_ENRICH_FILING if max_enrich_filing is None
                  else max_enrich_filing)
    with_events = "events" in news
    cap_ev = int(_cfg.EVENT_NODES_FUNNEL_MAX_ENRICH)
    uni = set(universe)
    s3_by = {c.ticker: c for c in ranker_s3}
    s4_set = {c.ticker for c in ranker_s4}

    for c in list(ranker_s3) + list(ranker_s4):
        row = names.get(c.ticker)
        c.sources = [SOURCE_RANKER] + (row["sources"] if row else [])
        if row:
            c.news_evidence = row["evidence"][:6]
            c.news_net_direction = row["net_direction"]

    added: dict[str, dict] = {}
    for t in names:
        if t in s4_set:
            continue
        r = names[t]
        added[t] = {"ticker": t, "issuer_id": r["issuer_id"], "issuer_name": r.get("issuer_name"),
                    "sources": list(r["sources"]), "net_direction": r["net_direction"],
                    "n_mentioned": r["n_mentioned"], "n_inferred": r["n_inferred"],
                    "evidence": r["evidence"][:8], "admitted": False, "dropped_by": None,
                    "screens": {"stage0_universe": "not_reached",
                                "stage1_eligibility": "not_reached",
                                "stage3_fundamentals": "not_reached"},
                    "stages_not_faced": list(RANKER_ONLY_STAGES), "candidate": None}

    def drop(t: str, why: str) -> None:
        added[t]["dropped_by"] = why

    # names the ranker kept at stage 3 and cut at stage 4: they faced every stage
    for t, row in added.items():
        if t in s3_by:
            row["screens"] = {k: "pass" for k in row["screens"]}
            row["stages_not_faced"] = []
            row["stages_faced_note"] = ("ranker stages 0-3 passed; stage-4 profitability rank "
                                        "FACED and cut below the final list")
            row["admitted"] = True
            row["candidate"] = s3_by[t].to_dict()
    need = [t for t in added if t not in s3_by]
    for t in need:
        if t not in uni:
            added[t]["screens"]["stage0_universe"] = "fail"
            drop(t, "stage0_universe")
        else:
            added[t]["screens"]["stage0_universe"] = "pass"
    in_uni = [t for t in need if t in uni]
    screened = screen_fn(in_uni) if in_uni else {}
    passed = []
    for t in in_uni:
        cand, screen = screened.get(t, (None, "no_price_history"))
        if cand is None:
            added[t]["screens"]["stage1_eligibility"] = screen or "no_price_history"
            drop(t, screen or "no_price_history")
        else:
            added[t]["screens"]["stage1_eligibility"] = "pass"
            passed.append(cand)
    p_news = sorted([c for c in passed if SOURCE_NEWS in names[c.ticker]["sources"]],
                    key=lambda c: _strength(c.ticker, names))
    p_fil = sorted([c for c in passed if SOURCE_NEWS not in names[c.ticker]["sources"]
                    and names[c.ticker]["sources"] != [SOURCE_EVENT]],
                   key=lambda c: _strength(c.ticker, names))
    # event-only names: their own bucket and cap, the same screens (empty unless events are on)
    p_ev = sorted([c for c in passed if names[c.ticker]["sources"] == [SOURCE_EVENT]],
                  key=lambda c: _strength(c.ticker, names))
    to_enrich = p_news[:cap_news] + p_fil[:cap_fil] + p_ev[:cap_ev]
    for c in p_news[cap_news:]:
        drop(c.ticker, "news_enrich_cap")
    for c in p_fil[cap_fil:]:
        drop(c.ticker, "filing_enrich_cap")
    for c in p_ev[cap_ev:]:
        drop(c.ticker, "event_enrich_cap")
    enriched = enrich_fn(to_enrich) if to_enrich else []
    got = {c.ticker: c for c in enriched}
    for c in to_enrich:
        if c.ticker in got:
            added[c.ticker]["screens"]["stage3_fundamentals"] = "pass"
            added[c.ticker]["admitted"] = True
            added[c.ticker]["candidate"] = got[c.ticker].to_dict()
        else:
            added[c.ticker]["screens"]["stage3_fundamentals"] = "fail"
            drop(c.ticker, "stage3_fundamentals")

    rows = sorted(added.values(), key=lambda r: (not r["admitted"], _strength(r["ticker"], names)))
    by_screen: dict[str, list] = {}
    for r in rows:
        if r["dropped_by"]:
            by_screen.setdefault(r["dropped_by"], []).append(r["ticker"])
    admitted = [r for r in rows if r["admitted"]]
    tagged = [c.ticker for c in ranker_s4 if len(getattr(c, "sources", [])) > 1]
    receipt = {
        "offered": {"total": len(names),
                    "news": sum(1 for r in names.values() if SOURCE_NEWS in r["sources"]),
                    "filing": sum(1 for r in names.values() if SOURCE_FILING in r["sources"]),
                    **({"event": sum(1 for r in names.values() if SOURCE_EVENT in r["sources"]),
                        "event_only": sum(1 for r in names.values() if r["sources"] == [SOURCE_EVENT])}
                       if with_events else {}),
                    "by_direction": dict(Counter(r["net_direction"] for r in names.values()))},
        "final": {"n": len(ranker_s4), "unchanged": True,
                  "tagged_in_ranker_final": len(tagged), "tagged_names": tagged,
                  "news_tag_share_of_ranker_final": (round(len(tagged) / len(ranker_s4), 4)
                                                     if ranker_s4 else None)},
        "stage3": {"n": len(ranker_s3),
                   "tagged": [c.ticker for c in ranker_s3 if len(getattr(c, "sources", [])) > 1]},
        "added_by_source": {"n_added": len(admitted),
                            "added": [{"ticker": r["ticker"], "sources": r["sources"],
                                       "net_direction": r["net_direction"]} for r in admitted],
                            "n_dropped": sum(1 for r in rows if r["dropped_by"]),
                            "dropped_by_screen": by_screen},
        "caps": {"news": cap_news, "filing": cap_fil, **({"event": cap_ev} if with_events else {})},
        "control_note": ("the candidate list is the ranker's own, unchanged; `added_by_source` "
                         "is separate, so a grader can compare ranker-only against "
                         "ranker + added from this one snapshot"),
    }
    receipt["both_numbers"] = both_numbers(receipt)
    return {"stage3": ranker_s3, "final": ranker_s4, "added": rows, "receipt": receipt}


# ───────────────────── offline replay (no network) ───────────────────────────
#
# The live funnel needs Finnhub + yfinance. The replay rebuilds ONLY what can be
# rebuilt offline and says which stage was reused: the ranker's lists come from
# a stored snapshot (only stage 4 is stored, so the snapshot's 25 stand in for
# the ranker's stage 3 as well), stage-0 from the cached symbol list, stage-1
# screens from the local daily bars (dates before the build day), and stage-3
# fundamentals from local SEC facts filed before the build time (live uses
# Finnhub / yfinance, so the replay's fundamentals source differs and is named).

def _bars_screen(bars: Path, as_of: datetime) -> ScreenFn:
    import pandas as pd
    from backend.services import opportunity_funnel as F

    def fn(names: list) -> dict:
        if not names:
            return {}
        df = pd.read_parquet(bars, columns=["symbol", "date", "close", "volume"],
                             filters=[("symbol", "in", list(names))])
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"].dt.date < as_of.date()]
        df = df[df["date"] >= df["date"].max() - pd.Timedelta(days=366)] if len(df) else df
        close = df.pivot_table(index="date", columns="symbol", values="close")
        vol = df.pivot_table(index="date", columns="symbol", values="volume")
        return {t: F.eligibility(t, close, vol) for t in names}
    return fn


def _sec_enrich(facts: Path, as_of: datetime) -> EnrichFn:
    import pandas as pd

    def fn(cands: list) -> list:
        if not cands:
            return []
        want = [c.ticker for c in cands]
        df = pd.read_parquet(facts, columns=["ticker", "fact", "filed", "period_days", "val"],
                             filters=[("ticker", "in", want),
                                      ("fact", "in", ["revenue", "cogs", "assets"])])
        df = df[pd.to_datetime(df["filed"]) < pd.Timestamp(as_of.date())]
        out = []
        for c in cands:
            g = df[df["ticker"] == c.ticker].sort_values("filed")
            ann = g[g["period_days"].between(350, 380)]
            rev, cogs = ann[ann.fact == "revenue"], ann[ann.fact == "cogs"]
            assets = g[g.fact == "assets"]
            if rev.empty or cogs.empty or assets.empty or not assets["val"].iloc[-1]:
                continue
            c.quality = float(rev["val"].iloc[-1] - cogs["val"].iloc[-1]) / float(assets["val"].iloc[-1])
            c.stage = 3
            c.why.append(f"gross profitability {c.quality:.2f} (REPLAY: local SEC facts filed "
                         f"before {as_of.date()}, standing in for the live Finnhub/yfinance call)")
            out.append(c)
        return out
    return fn


def _sha(p: Path) -> Optional[str]:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None


def _live_state(data_root: Path) -> dict:
    """What the replay must never change: the live snapshot and its history."""
    snap = data_root / "funnel_night10.json"
    hist = data_root / "funnel_history"
    return {"funnel_snapshot_sha": _sha(snap),
            "funnel_history_files": len(list(hist.glob("*"))) if hist.exists() else 0}


def replay(as_of: datetime, *, data_root: Path, snapshot: Path, out_dir: Path,
           event_store: Optional[Path] = None) -> tuple[dict, int]:
    from backend.services import opportunity_funnel as F

    snap = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    gen = _to_dt(snap.get("generated_at"))
    if gen is None or gen > as_of:
        print(f"REFUSED: snapshot generated_at {snap.get('generated_at')} is not before "
              f"the build time {_iso(as_of)} (look-ahead)")
        return {}, 2
    fields = set(F.Candidate.__dataclass_fields__)
    s4 = [F.Candidate(**{k: v for k, v in c.items() if k in fields})
          for c in snap.get("candidates") or []]
    uni_p = data_root / "funnel_cache" / "universe.json"
    uni = json.loads(uni_p.read_text(encoding="utf-8"))
    opt = data_root / "optimus"
    fil = opt / "official" / "tables" / "filing_events.jsonl"
    bars = opt / "prices_2025_26" / "bars.parquet"
    facts = opt / "fundamentals_sec" / "sec_facts_history.parquet"
    news = collect(as_of, digest_root=opt / "digest", filings=fil,
                   issuers=data_root / "news_entities" / "issuers.csv",
                   event_store=(Path(event_store) if event_store else
                                opt / str(_cfg.EVENT_NODES_DIRNAME) / "event_nodes.jsonl"))
    res = admit(news, list(s4), list(s4), universe=uni["tickers"],
                screen_fn=_bars_screen(bars, as_of), enrich_fn=_sec_enrich(facts, as_of))
    before = [(c.get("ticker"), c.get("score")) for c in snap.get("candidates") or []]
    after = [(c.ticker, c.score) for c in res["final"]]
    res["receipt"]["final"]["unchanged"] = before == after
    payload = {
        "schema": "funnel_news_replay/v2", "build_time": _iso(as_of),
        "recomputed": ["news/filing names (digest + filing_events)",
                       "stage-0 membership of news names (cached universe.json)",
                       "stage-1 screens of news names (local bars, dates < build day)",
                       "stage-3 fundamentals of news names (local SEC facts; live uses Finnhub)",
                       "tagging of the ranker's list + the separate added_by_source block"],
        "reused": {"ranker_stage4": {"path": str(snapshot), "generated_at": snap.get("generated_at"),
                                     "n": len(s4), "stages": snap.get("stages")},
                   "ranker_stage3": "NOT STORED on the snapshot: the 25 stand in for the 40",
                   "universe": {"path": str(uni_p), "n": uni.get("n"),
                                "fetched_at": uni.get("fetched_at")}},
        "inputs": {str(p): {"bytes": p.stat().st_size if p.exists() else None}
                   for p in (bars, facts, fil, uni_p)},
        "news_source": {**{k: v for k, v in news.items() if k != "names"},
                        "per_name": news["names"], **res["receipt"]},
        "candidates": [c.to_dict() for c in res["final"]],
        "added_by_source": res["added"],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y%m%dT%H%M%SZ")
    fp = out_dir / f"funnel_news_replay_{stamp}.json"
    tmp = fp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(fp)
    payload["_written"] = str(fp)
    return payload, 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="CH-14a offline replay: which names news and "
                                             "filings add to a stored funnel snapshot.")
    ap.add_argument("--as-of", required=True, help="build time, ISO UTC")
    ap.add_argument("--data-root", default=str(Path(_cfg.BACKEND_DIR) / "data"),
                    help="the backend/data folder to READ (never written)")
    ap.add_argument("--snapshot", default=None, help="default <data-root>/funnel_night10.json")
    ap.add_argument("--out", required=True, help="output directory (never the data folder)")
    ap.add_argument("--event-store", default=None,
                    help="event-node store read when EVENT_NODES_FUNNEL_SOURCE_ENABLED (CH-35)")
    a = ap.parse_args(argv)
    as_of = _to_dt(a.as_of)
    root = Path(a.data_root).resolve()
    out_dir = Path(a.out).resolve()
    if as_of is None or out_dir == root or root in out_dir.parents:
        print("REFUSED: --as-of unparsable or --out inside the data folder")
        return 2
    before = _live_state(root)
    payload, rc = replay(as_of, data_root=root,
                         snapshot=Path(a.snapshot) if a.snapshot else root / "funnel_night10.json",
                         out_dir=out_dir, event_store=Path(a.event_store) if a.event_store else None)
    after = _live_state(root)
    print(f"live state before {before}")
    print(f"live state after  {after}")
    if rc:
        return rc
    ns = payload["news_source"]
    dg, fl = ns["digest"], ns["filings"]
    print(f"digest {dg.get('digest_id')} age {dg.get('age_hours')} h typed rows "
          f"{dg.get('n_typed_rows')} ticker rows {dg.get('n_ticker_rows')} status {dg.get('status')}; "
          f"inferred-only not offered {len(dg.get('inferred_only_not_offered') or [])}, "
          f"no issuer mapping {len(dg.get('no_issuer_mapping') or [])}")
    print(f"filings {fl.get('status')}: in window {fl.get('n_in_window')}, allowed item "
          f"{fl.get('n_in_window_item_ok')}, dropped by item {fl.get('dropped_by_item')}")
    for d in ns["degradations"]:
        print(f"DEGRADED: {d}")
    if ns.get("events"):
        e = ns["events"]
        print(f"events {e.get('status')}: nodes known {e.get('n_nodes_known')}, events offering "
              f"{e.get('n_events_offering')} (importance >= {e.get('min_importance')}), names {e.get('n_names')}")
    print(f"ranker final unchanged: {ns['final']['unchanged']}")
    print(ns["both_numbers"])
    print(f"added: {[(r['ticker'], '+'.join(r['sources']), r['net_direction']) for r in ns['added_by_source']['added']]}")
    for s_, ts in ns["added_by_source"]["dropped_by_screen"].items():
        print(f"  dropped by {s_}: {len(ts)} {ts[:12]}")
    print(f"-> {payload['_written']}")
    return 1 if before != after else 0


if __name__ == "__main__":
    sys.exit(main())
