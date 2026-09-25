"""The book factory: ten declared strategies, one DeepSeek call each, frozen with twins.

    python -m scripts.book_factory generate --kind competition --n 10 \
        --notes docs/research_notes/2026-09-25/research_themes.md \
                research_global_candidates.md research_pharma.md research_social.md
    python -m scripts.book_factory generate --kind personal --n 10 --notes ...
    python -m scripts.book_factory strategies            # print STRATEGIES

WHAT IT DOES (Builder O2, 2026-09-25; orders in
docs/HANDOFF_2026-09-25_PM_AMENDMENT_BOOKS_FORECASTS_REVIEW.md)
==========================================================================
1. Assembles ONE evidence pack, shared by every book: per candidate name the
   briefing row (`llm_portfolio.build_briefing`), the 90-day analyst revision
   flow computed directly from `analyst/target_revisions.parquet` (strictly
   `event_date < asof`, `pit_safe` only), the last 14 days of news-corpus
   headlines tagged with the ticker, the Q4 catalyst YAML rows, and the
   research notes passed with `--notes` as text.
2. For each of N strategies in `STRATEGIES[kind]`, asks DeepSeek (via
   `llm_analyzer`'s client, language pin and telemetry) for ONE book in a FLAT
   JSON schema -- no nested objects, positions as `TICKER|weight|theme|thesis|
   falsifier` strings, because nested JSON broke 55% of parses on 09-24. A
   reply that is not JSON is lifted line by line and marked `parse: degraded`.
3. Sends the same prompt to the local llama-server when its /health answers;
   both answers are saved, only DeepSeek's is frozen (with its twins).
4. Spend is read from the SAME telemetry ledger `llm_analyzer` writes
   (purpose `book_factory`), before every call, capped at
   `config.BOOK_FACTORY_CAP_USD` per run. Unknown spend refuses; a ledger that
   cannot see the first call stops the run (the 2026-09-21 cap breach was a
   cap reading a different ledger than the writer).

The shared evidence comes FIRST in the prompt and the strategy LAST, so every
call after the first reads the long prefix from DeepSeek's cache at ~1/50 of
the price.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd                                         # noqa: E402

from backend import config as C                             # noqa: E402
from backend.services import llm_portfolio as LP            # noqa: E402

logger = logging.getLogger(__name__)

CATALYSTS_PATH = (Path(C.OPTIMUS_LEDGER_DIR) / "pm_catalysts"
                  / "catalysts_2026-Q4.yaml")
NEWS_ROOT = Path(C.OPTIMUS_LEDGER_DIR) / "news_corpus"

# ───────────────────────────── the strategies ───────────────────────────────
# Edit freely (Fable). `id` becomes part of the book name; `brief` is the only
# strategy text the model sees. Ten per kind, so the grade compares lenses.

_LENSES = [
    ("ai_power_global", "AI power bottleneck, worldwide: power generation, grid, "
     "cooling, transformers, turbines and the memory that AI capex buys. Prefer "
     "names with a dated observable (backlog, orders, earnings) in the window."),
    ("catalyst_calendar", "Catalyst calendar: only names with a DATED catalyst in "
     "the CATALYSTS evidence (earnings, PDUFA, investor day) inside the horizon. "
     "Diversify across dates so no single day decides the book."),
    ("revision_flow_leaders", "Analyst revision flow: names with the strongest "
     "90-day net target RAISES across >= 3 distinct firms. The flow, not the "
     "target level (target-level upside is measured perverse)."),
    ("policy_geopolitics", "Policy and geopolitics: tariffs, CHIPS/industrial "
     "policy, defence rearmament, critical minerals, government equity stakes. "
     "Name the policy event each position depends on."),
    ("retail_attention_contrarian", "Retail-attention contrarian: where headline "
     "counts spiked but analyst flow disagrees, side with the flow; avoid names "
     "that are only attention. Say which crowd you are fading."),
    ("pharma_binary_basket", "Pharma binary basket: PDUFA/readout names from the "
     "CATALYSTS evidence, sized for the CRL tail (a CRL averages -33% over 5 "
     "days), plus large-cap pharma ballast. No single binary above 5%."),
    ("quality_momentum", "Quality momentum: liquid names with strong 6-12 month "
     "momentum (mom_252_21) AND improving gross margin; avoid names far above "
     "their 200-day with falling margins."),
    ("small_cap_catalyst", "Small-cap catalyst: smaller but liquid names (band "
     "small/mid) with a dated catalyst; pay attention to cost_bps, you pay it."),
    ("asia_supply_chain", "Asia supply chain: Taiwan/Korea/Japan semis, "
     "packaging, test and components, plus their US customers; global tickers "
     "use the yfinance suffix (2330.TW, 000660.KS, 8035.T)."),
    ("ensemble", "Ensemble: only names that at least TWO of the other lenses "
     "(power, catalysts, revision flow, policy, quality momentum, Asia supply "
     "chain) would pick. Say which two for each name."),
]

STRATEGIES: dict[str, list[dict]] = {
    "competition": [
        {"id": i, "brief": b + " Competition rules: long only, global, <= 10% "
         "per name, >= 8 names, NO ETFs, cash <= 2%, graded as relative P&L vs "
         "the Bloomberg WLS index from 2026-10-12 to 2026-11-13."}
        for i, b in _LENSES],
    "personal": [
        {"id": i, "brief": b + " Personal book: long only, 6-month horizon "
         "(126 sessions), no per-name cap, declare cash explicitly (0 is a "
         "declaration), graded net of costs against SPY."}
        for i, b in _LENSES],
}

OBJECTIVES = {"competition": C.BOOK_COMPETITION_OBJECTIVE,
              "personal": C.BOOK_PERSONAL_OBJECTIVE}

POSITION_FORMAT = "TICKER|weight|theme|thesis|falsifier"


# ───────────────────────────── evidence pack ────────────────────────────────

def _cutoff(asof: date) -> pd.Timestamp:
    """News known at generation: now (UTC) when asof is today, else asof 00:00."""
    now = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    a = pd.Timestamp(asof)
    return now if a.date() >= now.date() else a


def revision_flow(revisions: pd.DataFrame, *, asof: Any,
                  window_days: int = C.BOOK_FACTORY_REVISION_DAYS) -> dict[str, dict]:
    """Per ticker, over (asof - window, asof): net raises, distinct firms,
    median target change. STRICTLY `event_date < asof`; `pit_safe` rows only."""
    if revisions is None or revisions.empty:
        return {}
    a = pd.Timestamp(asof)
    r = revisions[revisions["pit_safe"].astype(bool)].copy()
    r["event_date"] = pd.to_datetime(r["event_date"], errors="coerce")
    r = r[(r["event_date"] < a) & (r["event_date"] >= a - pd.Timedelta(days=window_days))]
    if r.empty:
        return {}
    act = r["target_action"].astype(str).str.strip().str.lower()
    r["_up"] = (act == "raises").astype(int)
    r["_dn"] = (act == "lowers").astype(int)
    out = {}
    for t, g in r.groupby("ticker"):
        tc = pd.to_numeric(g["target_change"], errors="coerce").dropna()
        out[str(t)] = {"net_raises": int(g["_up"].sum() - g["_dn"].sum()),
                       "n_raises": int(g["_up"].sum()), "n_lowers": int(g["_dn"].sum()),
                       "n_firms": int(g["firm"].nunique()),
                       "n_events": int(len(g)),
                       "median_target_change": (round(float(tc.median()), 4)
                                                if len(tc) else None)}
    return out


def news_evidence(tickers: Iterable[str], *, asof: Any, root: Path = NEWS_ROOT,
                  days: int = C.BOOK_FACTORY_NEWS_DAYS) -> dict[str, dict]:
    """Headline count + top-5 titles per ticker over the last `days`, from the
    news corpus (`<source>/<first_seen date>.jsonl`, `tickers[]`)."""
    want = {str(t).upper() for t in tickers}
    cut = _cutoff(pd.Timestamp(asof).date())
    lo = cut - pd.Timedelta(days=days)
    hits: dict[str, list[tuple[str, str, str]]] = {}
    root = Path(root)
    if not root.exists():
        return {}
    for src in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for f in sorted(src.glob("*.jsonl")):
            try:
                fd = pd.Timestamp(f.stem)
            except ValueError:
                continue
            if fd < lo.normalize() or fd > cut.normalize():
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ts = [str(x).upper() for x in (r.get("tickers") or [])]
                if not ts or not want.intersection(ts):
                    continue
                pub = pd.to_datetime(r.get("published_utc"), errors="coerce", utc=True)
                seen = pd.to_datetime(r.get("first_seen_utc"), errors="coerce", utc=True)
                if pd.isna(pub) or pd.isna(seen):
                    continue
                pub, seen = pub.tz_localize(None), seen.tz_localize(None)
                if not (lo <= pub <= cut) or seen > cut:
                    continue
                for t in want.intersection(ts):
                    hits.setdefault(t, []).append(
                        (str(pub), src.name, str(r.get("title") or "")[:160]))
    out = {}
    for t, rows in hits.items():
        rows = sorted(set(rows), reverse=True)
        out[t] = {"n_headlines": len(rows),
                  "top_titles": [f"[{s}] {title}" for _p, s, title in rows[:5]]}
    return out


def load_catalysts(path: Path = CATALYSTS_PATH) -> list[dict]:
    import yaml
    p = Path(path)
    if not p.exists():
        return []
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = doc.get("catalysts") or []
    return [{**r, "date": str(r.get("date")), "ticker": str(r.get("ticker"))}
            for r in rows if isinstance(r, dict)]


#: Bloomberg exchange code -> yfinance suffix.
_BBG = {"TT": ".TW", "KS": ".KS", "KQ": ".KQ", "JP": ".T", "JT": ".T",
        "HK": ".HK", "NA": ".AS", "FP": ".PA", "GY": ".DE", "GR": ".DE",
        "LN": ".L", "SS": ".ST", "NO": ".OL", "IM": ".MI", "CN": ".TO",
        "AU": ".AX", "AT": ".AX", "SW": ".SW", "SE": ".SW", "CH": ".SS",
        "CG": ".SS", "CS": ".SZ", "IN": ".NS", "IS": ".NS", "DC": ".CO",
        "FH": ".HE", "BB": ".BR", "SM": ".MC", "US": ""}


def bbg_to_yf(code: str) -> Optional[str]:
    """"2330 TT" -> "2330.TW"; "NOVO B DC" -> "NOVO-B.CO"; "TSM US" -> "TSM"."""
    parts = str(code).strip().split()
    if len(parts) < 2 or parts[-1] not in _BBG:
        return None
    return "-".join(parts[:-1]).upper() + _BBG[parts[-1]]


_BOLD = re.compile(r"\*\*([A-Z][A-Z0-9]{0,5})\*\*")
_BBG_CODE = re.compile(r"\b([0-9A-Z]{1,6}(?: [A-Z])? (?:" + "|".join(
    k for k in _BBG if k != "US") + r"))\b")
#: "800V DC" is a voltage, not a Copenhagen listing.
_UNIT = re.compile(r"^\d+(?:\.\d+)?[VAWK] ")
_CELL = re.compile(r"^\|\s*(?:\d+\s*\|\s*)?\**([A-Z]{1,5})\**\s*\|", re.M)


def tickers_from_notes(text: str, *, universe: Optional[set] = None) -> list[str]:
    """Tickers a research note names: bold symbols, first table cells and
    Bloomberg codes. US-looking symbols must be in `universe` when given."""
    found: list[str] = []
    for m in _BBG_CODE.finditer(text):
        y = bbg_to_yf(m.group(1))
        if y and not _UNIT.match(m.group(1)):
            found.append(y)
    for rx in (_BOLD, _CELL):
        for m in rx.finditer(text):
            t = m.group(1)
            if universe is None or t in universe:
                found.append(t)
    seen, out = set(), []
    for t in found:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _read_notes(paths: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    """Notes as text. A bare filename resolves against the previous note's
    directory, so `--notes dir/a.md b.md` works."""
    notes, missing, last_dir = {}, [], None
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute() and not (REPO / p).exists() and last_dir is not None:
            p = last_dir / p.name
        full = p if p.is_absolute() else REPO / p
        if not full.exists():
            missing.append(str(raw))
            continue
        last_dir = full.parent
        notes[full.name] = full.read_text(encoding="utf-8")[:C.BOOK_FACTORY_NOTE_MAX_CHARS]
    return notes, missing


def build_evidence(*, asof: date, notes: dict[str, str], briefing_rows: dict[str, dict],
                   revisions: Optional[pd.DataFrame], catalysts: list[dict],
                   news_root: Path, extra_tickers: Iterable[str] = (),
                   max_candidates: int = C.BOOK_FACTORY_MAX_CANDIDATES) -> dict:
    universe = set(briefing_rows) or None
    rf = revision_flow(revisions, asof=asof) if revisions is not None else {}
    cands: list[str] = []

    def _add(ts):
        for t in ts:
            t = str(t).upper()
            if t and t != "CASH" and t not in cands:
                cands.append(t)

    _add(r["ticker"] for r in catalysts)
    for text in notes.values():
        _add(tickers_from_notes(text, universe=universe))
    _add(extra_tickers)
    leaders = sorted((t for t, v in rf.items() if v["n_firms"] >= 3),
                     key=lambda t: -(rf[t]["net_raises"] * rf[t]["n_firms"]))
    _add(leaders[:40])
    cands = cands[:max_candidates]
    news = news_evidence(cands, asof=asof, root=news_root)
    cat_by: dict[str, list] = {}
    for r in catalysts:
        cat_by.setdefault(r["ticker"].upper(), []).append(
            f"{r['date']} {r['kind']}: {r['what']} ({r['verified_from']})")
    rows = []
    for t in cands:
        rows.append({"t": t, "briefing": briefing_rows.get(t),
                     "revision_flow_90d": rf.get(t),
                     "news_14d": news.get(t, {"n_headlines": 0, "top_titles": []}),
                     "catalysts": cat_by.get(t, [])})
    pack = {"asof": str(asof), "n_candidates": len(rows), "candidates": rows,
            "notes": notes,
            "field_notes": {
                "briefing": "point-in-time price/volume/fundamental row from llm_portfolio.build_briefing (US names only); null = not in the US panel",
                "revision_flow_90d": "analyst target actions strictly before asof over 90 days: net_raises = raises - lowers; n_firms distinct firms",
                "news_14d": "headline count and 5 newest titles tagged with the ticker in our news corpus",
                "catalysts": "hand-verified dated events; `aggregator` means the day is not primary-sourced"}}
    pack["evidence_hash"] = LP._hash({"c": rows, "n": sorted(notes)})
    return pack


# ───────────────────────────── the prompt ───────────────────────────────────

def size_rule(kind: str) -> str:
    if kind == "competition":
        return (f"{C.BOOK_COMPETITION_MIN_NAMES} to 25 names, each weight <= "
                f"{C.BOOK_COMPETITION_MAX_WEIGHT}, cash_weight <= "
                f"{C.BOOK_COMPETITION_MAX_CASH}, no ETFs")
    return "at least 5 names, any weight, cash_weight declared"


def shape_defect(parsed: dict, kind: str,
                 finish_reason: Optional[str] = None) -> Optional[str]:
    """What is structurally wrong with a parsed book, or None. Checked BEFORE
    freeze so an unfinished answer can be re-asked once. A reply cut off at
    max_tokens is a defect even when its positions parsed: the book the model
    meant may not be the book that arrived."""
    pos = [p for p in parsed.get("positions") or [] if p["ticker"] != "CASH"]
    try:
        cash = float(parsed.get("cash_weight") or 0.0)
    except (TypeError, ValueError):
        cash = 0.0
    tot = sum(p["weight"] for p in pos) + cash
    need = C.BOOK_COMPETITION_MIN_NAMES if kind == "competition" else 5
    probs = []
    if len(pos) < need:
        probs.append(f"{len(pos)} position(s), need at least {need}")
    # Strictly inside freeze's own 0.98-1.02 window: a total that lands ON the
    # boundary (1.0200 by float) passed here and was refused at freeze on
    # 2026-09-25; anything the freeze could refuse is a defect here first.
    if not 0.981 <= tot <= 1.019:
        probs.append(f"weights plus cash sum to {tot:.3f}, not 1.0")
    if finish_reason == "length":
        probs.append("reply truncated at max_tokens (finish_reason=length); keep "
                     "strategy and what_i_did_not_buy short")
    return "; ".join(probs) or None


#: A weight total inside this band, with every position present, is the model
#: failing to add (measured 2026-09-25: 7 of 10 personal books came back at
#: 1.02-1.12 after one re-ask). Outside it the book is a different book and
#: stays refused. The rescale is STAMPED on the record; it is never silent.
RESCALE_BAND = (0.90, 1.15)
#: When the model STATED its cash weight, the overshoot is in the position
#: weights alone (competition books came back at 1.22-1.54 with 20 names at
#: 5-10% each and "cash_weight: 0.02"): the names and their relative sizes are
#: the intent, the total is not. A stated cash line widens the band.
RESCALE_BAND_WITH_CASH = (0.85, 1.60)


def rescale_arithmetic(parsed: dict) -> tuple[dict, Optional[float]]:
    """Scale positions + cash to 1.0 when the total is an arithmetic slip.

    Returns (parsed, original_total) when rescaled, (parsed, None) otherwise.
    The original total is written into the book so the freeze record says
    the factory touched the weights and by how much.
    """
    pos = [p for p in parsed.get("positions") or [] if p.get("ticker") != "CASH"]
    cash_stated = parsed.get("cash_weight") is not None
    try:
        cash = float(parsed.get("cash_weight") or 0.0)
    except (TypeError, ValueError):
        cash, cash_stated = 0.0, False
    tot = sum(float(p.get("weight") or 0.0) for p in pos) + cash
    band = RESCALE_BAND_WITH_CASH if cash_stated else RESCALE_BAND
    if tot <= 0 or not (band[0] <= tot <= band[1]) or abs(tot - 1.0) < 1e-9:
        return parsed, None
    for p in parsed.get("positions") or []:
        if p.get("ticker") != "CASH":
            p["weight"] = round(float(p.get("weight") or 0.0) / tot, 6)
    parsed["cash_weight"] = round(cash / tot, 6)
    parsed["weights_rescaled_from"] = round(tot, 4)
    parsed["strategy"] = (str(parsed.get("strategy") or "") +
                          f" [factory: weights and cash rescaled from a stated total "
                          f"of {tot:.4f} to 1.0 -- the model's arithmetic, not its intent]")
    return parsed, round(tot, 4)


def _defect(parsed: dict, status: str, ans: dict, kind: str) -> Optional[str]:
    """Shape defect of one answer. A failed parse is re-askable only when the
    reply was cut off; garbage asked again is the same garbage."""
    fr = ans.get("finish_reason")
    if status == "failed" and fr != "length":
        return None
    return shape_defect(parsed, kind, finish_reason=fr)


def build_prompt(pack: dict, *, kind: str, strategy: dict) -> tuple[str, str]:
    size_rule_ = size_rule(kind)
    system = (
        "You are a portfolio manager building ONE long-only equity book from the "
        "evidence given. Use only tickers that appear in the evidence (global "
        "names with their yfinance suffix, e.g. 2330.TW). Never invent analyst "
        "targets, dates or facts that are not in the evidence.\n"
        "Return ONLY a json object with exactly these keys, all values flat:\n"
        '  "name": short snake_case name\n'
        '  "cash_weight": number between 0 and 1\n'
        f'  "positions": array of strings, each "{POSITION_FORMAT}" -- weight a '
        "fraction (0.08, not 8), theme one word (semis, power_grid, lithium, "
        "quantum, nuclear, biotech, gambling, robotics, defense, energy, "
        "materials, software, policy), thesis one sentence naming the evidence "
        "field that drove it, falsifier the dated observation that would prove "
        "it wrong; no '|' inside a field\n"
        '  "strategy": at most 120 words: what you bet on and what would make you wrong\n'
        '  "objective": one line\n'
        f'  "what_i_did_not_buy": array of at most {C.BOOK_FACTORY_MAX_NOT_BOUGHT} '
        'strings, each "TICKER|reason" with a reason under 15 words\n'
        "Emit the keys in that order. THE BOOK IS THE WHOLE ARRAY: `positions` "
        f"lists EVERY holding ({size_rule_}), and the position weights plus "
        "cash_weight sum to 1.0 -- add them up before answering. "
        "A book of one position is an unfinished answer. Example of two "
        "entries: [\"VRT|0.08|power_grid|deferred revenue doubled (news_14d)|"
        "Q3 backlog growth stalls in late Oct\", \"2330.TW|0.07|semis|Q3 "
        "earnings Oct 15 (catalysts)|capex guide cut on Oct 15\"]. "
        "No nested objects.")
    evidence = json.dumps({k: pack.get(k) for k in ("asof", "field_notes", "candidates")},
                          separators=(",", ":"), default=str)
    notes = "\n\n".join(f"=== NOTE {n} ===\n{t}" for n, t in (pack.get("notes") or {}).items())
    user = (f"EVIDENCE (identical for every book in this run)\n{evidence}\n\n"
            f"RESEARCH NOTES\n{notes}\n\n"
            f"YOUR STRATEGY: {strategy['id']} ({kind})\n{strategy['brief']}\n"
            f"Objective: {OBJECTIVES[kind]}\nReturn the json object now.")
    return system, user


# ───────────────────────────── parsing ──────────────────────────────────────

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)
_LINE = re.compile(r'"?\s*([A-Z0-9][A-Z0-9.\-]{0,11})\s*\|\s*([0-9]*\.?[0-9]+)\s*\|'
                   r'([^|"\n]*)\|([^|"\n]*)\|([^"\n]*)')


def _split_position(s: str) -> Optional[dict]:
    parts = [x.strip() for x in str(s).split("|")]
    if len(parts) < 2:
        return None
    try:
        w = float(parts[1])
    except ValueError:
        return None
    return {"ticker": parts[0].upper(), "weight": w,
            "theme": (parts[2] if len(parts) > 2 else "") or None,
            "thesis": parts[3] if len(parts) > 3 else "",
            "falsifier": "|".join(parts[4:]) if len(parts) > 4 else ""}


def parse_answer(text: str) -> tuple[dict, str]:
    """(book fields, "ok" | "degraded" | "failed")."""
    raw = _FENCE.sub("", (text or "").strip())
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("not an object")
        pos = [p for p in (_split_position(s) for s in obj.get("positions") or []) if p]
        return ({"name": obj.get("name"), "strategy": obj.get("strategy"),
                 "objective": obj.get("objective"),
                 "cash_weight": obj.get("cash_weight"),
                 "positions": pos,
                 "what_i_did_not_buy": [str(x) for x in obj.get("what_i_did_not_buy") or []]},
                "ok" if pos else "failed")
    except ValueError:
        pass
    pos = []
    for m in _LINE.finditer(raw):
        pos.append({"ticker": m.group(1).upper(), "weight": float(m.group(2)),
                    "theme": m.group(3).strip() or None, "thesis": m.group(4).strip(),
                    "falsifier": m.group(5).strip()})
    cash = re.search(r'"cash_weight"\s*:\s*([0-9.]+)', raw)
    strat = re.search(r'"strategy"\s*:\s*"([^"]*)"', raw)
    return ({"name": None, "strategy": strat.group(1) if strat else None,
             "objective": None, "cash_weight": float(cash.group(1)) if cash else None,
             "positions": pos, "what_i_did_not_buy": []},
            "degraded" if pos else "failed")


def to_book(parsed: dict, *, strategy: dict, kind: str, asof: Any, model: str,
            parse: str, evidence_hash: Optional[str] = None,
            prompt_hash: Optional[str] = None) -> dict:
    """The model's answer in `llm_portfolio.freeze`'s shape. Name and objective
    are OURS -- a model does not get to rename the experiment it is in."""
    pos = [dict(p) for p in parsed["positions"] if p["ticker"] != "CASH"]
    cash = parsed.get("cash_weight")
    try:
        cash = float(cash) if cash is not None else None
    except (TypeError, ValueError):
        cash = None
    if cash is None:
        cash = max(0.0, 1.0 - sum(p["weight"] for p in pos))
        cash = cash if cash > 1e-6 else 0.0
    if kind == "personal" or cash > 0:
        pos.append({"ticker": "CASH", "weight": cash, "thesis": "declared cash"})
    return {"name": f"{kind[:4]}_{strategy['id']}_{asof}", "kind": kind,
            "objective": OBJECTIVES[kind], "model": model,
            "strategy": (parsed.get("strategy") or strategy["brief"]),
            "what_i_did_not_buy": parsed.get("what_i_did_not_buy") or [],
            "source": "book_factory", "parse": parse,
            "evidence_hash": evidence_hash, "prompt_hash": prompt_hash,
            "positions": pos}


# ───────────────────────────── the callers ──────────────────────────────────

def deepseek_call(system: str, user: str, *, max_tokens: int) -> dict:
    """One DeepSeek call on `llm_analyzer`'s path: its client, its language pin,
    its daily call budget and breaker, its telemetry row, its non-English
    refusal. `_call_llm` itself caps replies at 500 tokens, too short for a
    book, which is why this does not go through it."""
    from backend.services import llm_analyzer as LA
    from backend.services import llm_telemetry as LT
    purpose = C.BOOK_FACTORY_PURPOSE
    if not LA._DEEPSEEK_API_KEY:
        return {"text": None, "error": "no DEEPSEEK_API_KEY"}
    if not LA._acquire_call_budget():
        return {"text": None, "error": "llm_analyzer daily call cap or billing breaker"}
    client = LA._get_openai_client()
    if client is None:
        return {"text": None, "error": "DeepSeek client unavailable"}
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=LA._DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system + LA._LANGUAGE_PIN},
                      {"role": "user", "content": user}],
            max_tokens=max_tokens, temperature=0.4,
            response_format={"type": "json_object"})
    except Exception as exc:                                 # noqa: BLE001
        LA._record("deepseek", LA._DEEPSEEK_MODEL, purpose, system=system,
                   user=user, t0=t0, error=exc)
        if LA._is_billing_error(exc):
            LA._trip_breaker(exc)
        return {"text": None, "error": f"{type(exc).__name__}: {exc}"}
    text = (resp.choices[0].message.content or "").strip()
    LA._record("deepseek", LA._DEEPSEEK_MODEL, purpose, system=system, user=user,
               resp=resp, text=text, t0=t0,
               validate=lambda t: parse_answer(t)[1] == "ok")
    u = LT.extract_usage(resp, "deepseek")
    cost = LT.price_call(LA._DEEPSEEK_MODEL, u["tokens_in"], u["tokens_out"],
                         u["cached_tokens"])
    out = {"text": text, "model": LA._DEEPSEEK_MODEL,
           "served_model": getattr(resp, "model", None), "cost_usd": cost,
           "finish_reason": getattr(resp.choices[0], "finish_reason", None),
           "error": None, **u}
    if LA._refuse_non_english("deepseek", purpose, text):
        out.update(text=None, error="refused: reply not in English")
    return out


def local_call(system: str, user: str, *, max_tokens: int) -> Optional[dict]:
    """The same prompt to the local llama-server. None when it is not up."""
    import requests
    base = C.BOOK_FACTORY_LOCAL_LLM_URL.rstrip("/")
    try:
        if requests.get(f"{base}/health", timeout=2).status_code != 200:
            return None
    except requests.RequestException:
        return None
    # A prompt longer than the server's context is not sent: it would fail
    # after minutes of prompt evaluation. ~4 characters per token.
    est_tokens = (len(system) + len(user)) // 4
    try:
        n_ctx = int(requests.get(f"{base}/props", timeout=2).json()
                    .get("default_generation_settings", {}).get("n_ctx") or 0)
    except (requests.RequestException, ValueError, TypeError):
        n_ctx = 0
    if n_ctx and est_tokens + max_tokens > n_ctx:
        return {"text": None, "model": "llama-server", "n_ctx": n_ctx,
                "error": f"NOT SENT: prompt ~{est_tokens} tokens + {max_tokens} "
                         f"reply > n_ctx {n_ctx}"}
    try:
        r = requests.post(f"{base}/v1/chat/completions", timeout=C.BOOK_FACTORY_LOCAL_TIMEOUT_S,
                          json={"messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": user}],
                                "max_tokens": max_tokens, "temperature": 0.4})
        j = r.json()
        if r.status_code != 200:
            return {"text": None, "model": "llama-server",
                    "error": f"HTTP {r.status_code}: {str(j)[:300]}"}
        return {"text": j["choices"][0]["message"]["content"],
                "model": j.get("model", "llama-server"), "error": None,
                "usage": j.get("usage")}
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {"text": None, "model": "llama-server",
                "error": f"{type(exc).__name__}: {exc}"}


def ledger_spend(since: str) -> dict:
    from backend.services import llm_telemetry as LT
    return LT.spend(since=since, purpose=C.BOOK_FACTORY_PURPOSE)


# ───────────────────────────── generate ─────────────────────────────────────

def _load_briefing_rows(asof: date) -> tuple[dict, str]:
    p = LP.briefing_path(str(asof))
    if not p.exists():
        cands = sorted(LP.ledger_dir().glob("briefing_*.json"))
        cands = [c for c in cands if c.stem.split("_", 1)[1] <= str(asof)]
        p = cands[-1] if cands else None
    if p is None:
        brief = LP.build_briefing()
        src = f"built now (asof {brief['asof']})"
    else:
        brief = json.loads(p.read_text(encoding="utf-8"))
        src = f"{p.name} (asof {brief.get('asof')})"
    return {r["t"]: r for r in brief.get("rows", [])}, src


def generate(*, kind: str, n: int, asof: date, out_dir: Path, notes: list[str],
             llm: Callable = deepseek_call, local: Callable = local_call,
             spend: Callable = ledger_spend, freeze: bool = True,
             twins: bool = True, seed: int = 20260925,
             us_bars: Optional[pd.DataFrame] = None,
             resolve: Optional[Callable] = None,
             revisions: Optional[pd.DataFrame] = None,
             only: Optional[set[str]] = None,
             news_root: Path = NEWS_ROOT, catalysts: Optional[list] = None,
             briefing_rows: Optional[dict] = None,
             extra_tickers: Iterable[str] = (),
             max_candidates: int = C.BOOK_FACTORY_MAX_CANDIDATES,
             out: Callable = print) -> dict:
    if kind not in STRATEGIES:
        raise LP.Refusal(f"REFUSED: kind must be one of {sorted(STRATEGIES)}")
    run_start = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def say(msg: str) -> None:
        lines.append(msg)
        out(msg)

    note_text, missing = _read_notes(notes)
    if missing:
        say(f"MISSING NOTES (not read): {missing}")
    brief_src = "injected"
    if briefing_rows is None:
        briefing_rows, brief_src = _load_briefing_rows(asof)
    if revisions is None:
        rp = Path(C.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
        revisions = pd.read_parquet(rp) if rp.exists() else None
        if revisions is None:
            say(f"NO REVISIONS FILE at {rp}; revision_flow is empty")
    catalysts = load_catalysts() if catalysts is None else catalysts
    pack = build_evidence(asof=asof, notes=note_text, briefing_rows=briefing_rows,
                          revisions=revisions, catalysts=catalysts,
                          news_root=news_root, extra_tickers=extra_tickers,
                          max_candidates=max_candidates)
    (out_dir / "evidence_pack.json").write_text(
        json.dumps(pack, indent=1, default=str), encoding="utf-8")
    say(f"evidence: {pack['n_candidates']} candidates, {len(note_text)} notes, "
        f"{len(catalysts)} catalysts, briefing {brief_src}, hash {pack['evidence_hash']}")

    strategies = STRATEGIES[kind][:n]
    if only:
        strategies = [st for st in strategies if st['id'] in only]
    cap = float(C.BOOK_FACTORY_CAP_USD)
    est = float(C.BOOK_FACTORY_EST_CALL_USD)
    rc = {"kind": kind, "asof": str(asof), "run_start_utc": run_start,
          "cap_usd": cap, "n_requested": len(strategies), "n_called": 0,
          "n_frozen": 0, "n_refused": 0, "stopped": None, "books": [],
          "local": {"status": "not attempted"}, "notes_missing": missing}
    local_up: Optional[bool] = None
    own_cost = 0.0

    for i, strat in enumerate(strategies):
        s = spend(run_start)
        if not s:
            rc["stopped"] = "SPEND UNKNOWN: the telemetry ledger could not be read; refusing to call"
            say(rc["stopped"])
            break
        if s.get("total_is_lower_bound"):
            rc["stopped"] = "SPEND LOWER BOUND: an unpriced call is in this run; refusing"
            say(rc["stopped"])
            break
        spent = float(s.get("total_cost_usd") or 0.0)
        if i > 0 and int(s.get("n_calls") or 0) == 0:
            rc["stopped"] = (f"LEDGER BLIND: {rc['n_called']} call(s) made, the ledger "
                             f"shows 0 for purpose {C.BOOK_FACTORY_PURPOSE}; the cap "
                             f"cannot bind, stopping")
            say(rc["stopped"])
            break
        if i == 1:
            say(f"cap check after first flush: ledger ${spent:.4f} vs own ${own_cost:.4f}")
        if spent + est > cap:
            rc["stopped"] = (f"CAP: ${spent:.4f} spent + ${est:.2f} next > "
                             f"${cap:.2f} cap")
            say(rc["stopped"])
            break

        system, user = build_prompt(pack, kind=kind, strategy=strat)
        size_rule_ = size_rule(kind)
        ph = hashlib.sha256((system + user).encode()).hexdigest()[:16]
        stem = f"{kind}_{strat['id']}"
        ans = llm(system, user, max_tokens=C.BOOK_FACTORY_MAX_TOKENS)
        rc["n_called"] += 1
        own_cost += float(ans.get("cost_usd") or 0.0)
        parsed, status = parse_answer(ans.get("text") or "")
        defect = _defect(parsed, status, ans, kind)
        reasks = 0
        while defect and reasks < C.BOOK_FACTORY_MAX_REASKS:
            s2 = spend(run_start) or {}
            if not s2 or float(s2.get("total_cost_usd") or 0.0) + est > cap:
                break
            reasks += 1
            say(f"  {stem}: incomplete answer ({defect}); re-asking once")
            (out_dir / f"{stem}.deepseek.first.json").write_text(json.dumps(
                {**ans, "parse": status, "parsed": parsed, "defect": defect},
                indent=1, default=str), encoding="utf-8")
            # Same prefix, so the re-ask reads the evidence from the cache.
            ans = llm(system, user + (
                f"\n\nYOUR PREVIOUS ANSWER WAS UNFINISHED: {defect}. Return the "
                f"COMPLETE json object again ({size_rule_} and weights plus "
                f"cash_weight summing to 1.0)."), max_tokens=C.BOOK_FACTORY_MAX_TOKENS)
            rc["n_called"] += 1
            own_cost += float(ans.get("cost_usd") or 0.0)
            parsed, status = parse_answer(ans.get("text") or "")
            defect = _defect(parsed, status, ans, kind)
        rescaled_from = None
        if (defect and status != "failed" and defect.startswith("weights plus cash sum")
                and ";" not in defect):
            parsed, rescaled_from = rescale_arithmetic(parsed)
            if rescaled_from is not None:
                say(f"  {stem}: weights summed to {rescaled_from:.4f}; rescaled to 1.0 and stamped")
                defect = _defect(parsed, status, ans, kind)
        (out_dir / f"{stem}.deepseek.json").write_text(json.dumps(
            {**ans, "parse": status, "parsed": parsed, "prompt_hash": ph,
             "strategy": strat}, indent=1, default=str), encoding="utf-8")
        entry = {"strategy": strat["id"], "parse": status, "reasks": reasks,
                 "shape_defect": defect, "weights_rescaled_from": rescaled_from,
                 "cost_usd": ans.get("cost_usd"), "error": ans.get("error"),
                 "served_model": ans.get("served_model")}

        if local_up is not False:
            la = local(system, user, max_tokens=C.BOOK_FACTORY_MAX_TOKENS)
            if la is None:
                local_up = False
                rc["local"] = {"status": f"SKIPPED: {C.BOOK_FACTORY_LOCAL_LLM_URL}/health "
                                         f"did not answer"}
                say(rc["local"]["status"])
            else:
                local_up = True
                lp, lst = parse_answer(la.get("text") or "")
                (out_dir / f"{stem}.local.json").write_text(json.dumps(
                    {**la, "parse": lst, "parsed": lp, "prompt_hash": ph},
                    indent=1, default=str), encoding="utf-8")
                rc["local"] = {"status": "saved (not frozen)"}
                entry["local_parse"] = lst
                entry["local_error"] = la.get("error")

        if status == "failed":
            entry["frozen"] = False
            say(f"  {stem}: parse FAILED ({ans.get('error') or 'no positions'})")
        elif freeze:
            from scripts.llm_portfolio import freeze_with_twins
            book = to_book(parsed, strategy=strat, kind=kind, asof=asof,
                           model=ans.get("served_model") or ans.get("model") or "deepseek",
                           parse=status, evidence_hash=pack["evidence_hash"],
                           prompt_hash=ph)
            frc, frozen = freeze_with_twins([book], us_bars=us_bars, resolve=resolve,
                                            twins=twins, seed=seed,
                                            check_prices=us_bars is not None, out=say)
            parent = [f for f in frozen if f.get("kind") != "twin"]
            entry["frozen"] = bool(parent)
            entry["book_id"] = parent[0]["book_id"] if parent else None
            if parent:
                rc["n_frozen"] += 1
            else:
                rc["n_refused"] += 1
                (out_dir / f"{stem}.refused.json").write_text(
                    json.dumps(book, indent=1, default=str), encoding="utf-8")
        rc["books"].append(entry)

    final = spend(run_start) or {}
    rc["ledger_spend_usd"] = final.get("total_cost_usd")
    rc["own_cost_usd"] = round(own_cost, 6)
    rc["lines"] = lines
    (out_dir / "receipt.json").write_text(json.dumps(rc, indent=1, default=str),
                                          encoding="utf-8")
    say(f"{kind}: {rc['n_called']} called, {rc['n_frozen']} frozen, "
        f"{rc['n_refused']} refused; spend ledger ${rc['ledger_spend_usd']} / own "
        f"${rc['own_cost_usd']:.4f}; cap ${cap:.2f}" +
        (f"; STOPPED: {rc['stopped']}" if rc["stopped"] else ""))
    return rc


def cmd_generate(a) -> int:
    from backend.services import global_prices as GP
    from backend.services import xs_ranker as XR
    asof = date.today() if a.asof in (None, "today") else date.fromisoformat(a.asof)
    out_dir = Path(a.out) if a.out else (LP.ledger_dir() / "factory" / str(asof))
    us_bars = XR.load_bars(XR.survivorship_free_paths()) if not a.no_freeze else None
    rc = generate(kind=a.kind, n=a.n, asof=asof, out_dir=out_dir, notes=a.notes or [],
                  freeze=not a.no_freeze, twins=not a.no_twins, seed=a.seed,
                  us_bars=us_bars, resolve=GP.resolve,
                  local=(lambda *x, **k: None) if a.no_local else local_call,
                  max_candidates=a.max_candidates,
                  only=set(x.strip() for x in a.only.split(',') if x.strip()) if a.only else None)
    print(f"-> {out_dir}")
    return 0 if rc["n_called"] and not rc["stopped"] else 2


def cmd_strategies(a) -> int:
    print(json.dumps(STRATEGIES, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="N books of one kind, one DeepSeek call each")
    g.add_argument("--kind", choices=sorted(STRATEGIES), required=True)
    g.add_argument("--n", type=int, default=10)
    g.add_argument("--asof", default="today")
    g.add_argument("--out", default=None)
    g.add_argument("--notes", nargs="*", default=[])
    g.add_argument("--seed", type=int, default=20260925)
    g.add_argument("--max-candidates", type=int, default=C.BOOK_FACTORY_MAX_CANDIDATES)
    g.add_argument("--no-freeze", action="store_true", help="save answers only")
    g.add_argument("--no-twins", action="store_true")
    g.add_argument("--no-local", action="store_true", help="skip llama-server")
    g.add_argument("--only", default=None, help="comma list of strategy ids to (re)generate")
    g.set_defaults(fn=cmd_generate)
    s = sub.add_parser("strategies", help="print STRATEGIES")
    s.set_defaults(fn=cmd_strategies)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
