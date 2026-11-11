"""One broker / analyst report -> validated, dated rows the universe can ingest.

CH-32 (roadmap M1 SENSE): analyst and Bloomberg material becomes skills and
features. The `analyst-report-extract` project skill (`.claude/skills/`) tells
a session WHAT to pull out of a report; this module is the contract the output
must satisfy before anything downstream reads it.

WHAT IS EXTRACTED (the structure of a sell-side note)
-----------------------------------------------------
header        broker, ticker, published date, rating (raw label + normalised),
              price target, PRIOR price target, price at publication
scenarios     upside / base / downside with price targets, stated probabilities
              (usually NOT stated -- then None, never invented) and the
              operating assumptions behind each
eps_revisions period, from -> to, consensus; the % change is RECOMPUTED here
key_debates   the questions the note says the market is arguing about
catalysts     dated events; a date the note does not give stays None
falsifiers    what would show the thesis wrong: an observable plus a by-date

THE POINT-IN-TIME RULE
----------------------
A row is knowable at `knowable_at = max(published_at, first_held_at)`: a note
published on the 27th that reached us on the 3rd is evidence from the 3rd. A
consumer that joins on `published_at` is reading the future. Every row carries
both, and `pit_safe` says whether `first_held_at` was recorded (False = the
date we got it is unknown, so the row may not enter a backtest).

LICENSED TEXT NEVER ENTERS THE REPO
-----------------------------------
Reports are licensed (UBS, Bloomberg, Capital IQ). Extracted rows live under a
gitignored data path or `AEGIS_DOCUMENTS/`; this module and its tests carry
only synthetic examples. Text fields are capped (`MAX_TEXT`) so a row is a
paraphrase-length pointer with a page reference, not a copy of the note.

    python -m scripts.analyst_report_rows validate <report.json> [--out rows.jsonl]
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "analyst-report-rows-1.0.0"

#: A text field is a pointer, not a copy of licensed prose.
MAX_TEXT = 240

#: Normalised rating. Broker labels map here; anything else is "unknown" with
#: the raw label kept, never guessed.
RATING_MAP = {
    "buy": "buy", "outperform": "buy", "overweight": "buy", "strong buy": "buy",
    "accumulate": "buy", "add": "buy", "positive": "buy",
    "neutral": "hold", "hold": "hold", "equal-weight": "hold", "equal weight": "hold",
    "market perform": "hold", "sector perform": "hold", "in-line": "hold",
    "sell": "sell", "underperform": "sell", "underweight": "sell", "reduce": "sell",
    "negative": "sell", "strong sell": "sell",
}
SCENARIO_NAMES = ("upside", "base", "downside")
#: |stated pct change - recomputed| above this is flagged, not silently fixed.
PCT_TOLERANCE = 1.0
ROW_KINDS = ("rating", "price_target", "scenario", "eps_revision", "key_debate",
             "catalyst", "falsifier")


class ReportInvalid(ValueError):
    """The report does not satisfy the schema; the message lists every error."""


def _day(v: Any) -> str | None:
    if v is None or v == "":
        return None
    t = str(v)
    if len(t) > 10 and t[10] not in "T ":
        return "INVALID"
    try:
        return date.fromisoformat(t[:10]).isoformat()
    except ValueError:
        return "INVALID"


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return f


def _text(v: Any) -> str:
    return " ".join(str(v or "").split())


def _page(v: Any, errs: list[str], where: str) -> int | None:
    if v is None or v == "":
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        errs.append(f"{where}: page must be an integer or null")
        return None
    if not 0 < n < 10_000:
        errs.append(f"{where}: page {n} out of range")
        return None
    return n


def normalise_rating(raw: Any) -> str:
    return RATING_MAP.get(_text(raw).lower(), "unknown")


def source_id(report: dict) -> str:
    """Stable id: the source file hash if given, else a hash of the header."""
    h = report.get("source_sha256")
    if h:
        return str(h)[:16]
    body = {k: report.get(k) for k in ("broker", "ticker", "published_at", "title")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def validate_report(report: Any) -> tuple[dict | None, list[str]]:
    """(clean report, errors). Every error is listed; nothing is repaired silently.

    Warnings (a stated % that disagrees with the recomputed one, a probability
    set that does not sum to 1) are kept on the report under `warnings`; they do
    not invalidate it because the note itself may be internally inconsistent,
    and that is a finding about the note.
    """
    errs: list[str] = []
    warns: list[str] = []
    if not isinstance(report, dict):
        return None, ["not an object"]
    out: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    for k, cap in (("broker", 80), ("ticker", 20)):
        if not _text(report.get(k)):
            errs.append(f"missing {k}")
        if len(_text(report.get(k))) > cap:
            errs.append(f"{k} longer than {cap} characters")
        out[k] = _text(report.get(k))[:cap]
    out["ticker"] = out["ticker"].upper()
    out["title"] = _text(report.get("title"))[:MAX_TEXT]
    pub = _day(report.get("published_at"))
    held = _day(report.get("first_held_at"))
    if pub in (None, "INVALID"):
        errs.append("published_at must be an ISO date")
    if held == "INVALID":
        errs.append("first_held_at must be an ISO date or null")
    if pub not in (None, "INVALID") and held not in (None, "INVALID") and held < pub:
        errs.append(f"first_held_at {held} precedes published_at {pub}")
    out["published_at"], out["first_held_at"] = pub, held
    out["knowable_at"] = (max(pub, held) if pub not in (None, "INVALID")
                          and held not in (None, "INVALID") else pub)
    out["pit_safe"] = held not in (None, "INVALID")
    out["source_sha256"] = report.get("source_sha256")
    out["source_id"] = source_id(report)

    if len(_text(report.get("rating"))) > 60:
        errs.append("rating longer than 60 characters")
    out["rating_raw"] = _text(report.get("rating"))[:60]
    out["rating"] = normalise_rating(report.get("rating"))
    for k in ("price_target", "prior_price_target", "price_at_publication"):
        v = _num(report.get(k))
        if v is not None and not (math.isfinite(v) and v > 0):
            errs.append(f"{k} must be a positive number or null")
        out[k] = v
    pt, prior, px = out["price_target"], out["prior_price_target"], out["price_at_publication"]
    out["target_change_pct"] = (round(100.0 * (pt / prior - 1.0), 4)
                                if pt and prior and math.isfinite(pt) and math.isfinite(prior)
                                else None)
    out["implied_upside_pct"] = (round(100.0 * (pt / px - 1.0), 4)
                                 if pt and px and math.isfinite(pt) and math.isfinite(px)
                                 else None)

    scen = []
    for i, s in enumerate(report.get("scenarios") or []):
        if not isinstance(s, dict):
            errs.append(f"scenario {i}: not an object")
            continue
        name = _text(s.get("name")).lower()
        if name not in SCENARIO_NAMES:
            errs.append(f"scenario {i}: name {name!r} not in {SCENARIO_NAMES}")
        prob = _num(s.get("probability"))
        if prob is not None and not (math.isfinite(prob) and 0.0 <= prob <= 1.0):
            errs.append(f"scenario {name}: probability must be in [0, 1] or null")
        spt = _num(s.get("price_target"))
        if spt is not None and not (math.isfinite(spt) and spt > 0):
            errs.append(f"scenario {name}: price_target must be positive or null")
        assum = s.get("assumptions") or {}
        if not isinstance(assum, dict):
            errs.append(f"scenario {name}: assumptions must be an object")
            assum = {}
        clean_assum = {}
        for ak, av in assum.items():
            nv = _num(av)
            if nv is not None and not math.isfinite(nv):
                errs.append(f"scenario {name}: assumption {str(ak)[:40]!r} is not a number")
                continue
            clean_assum[str(ak)[:60]] = nv
        if name in {x["name"] for x in scen}:
            errs.append(f"scenario {name}: duplicate scenario name")
        scen.append({"name": name, "probability": prob, "price_target": spt,
                     "assumptions": clean_assum})
    probs = [s["probability"] for s in scen]
    if scen and all(p is not None for p in probs) and abs(sum(probs) - 1.0) > 0.01:
        warns.append(f"scenario probabilities sum to {sum(probs):.3f}, not 1")
    if scen and any(p is None for p in probs) and any(p is not None for p in probs):
        warns.append("some scenario probabilities stated, some not")
    out["scenarios"] = scen

    eps = []
    for i, e in enumerate(report.get("eps_revisions") or []):
        if not isinstance(e, dict) or not _text(e.get("period")):
            errs.append(f"eps_revision {i}: needs a period")
            continue
        f, t, c = _num(e.get("eps_from")), _num(e.get("eps_to")), _num(e.get("consensus"))
        for nm, v in (("eps_from", f), ("eps_to", t), ("consensus", c)):
            if v is not None and not math.isfinite(v):
                errs.append(f"eps_revision {e.get('period')}: {nm} is not a number")
        pct = (round(100.0 * (t / f - 1.0), 4)
               if f not in (None, 0) and t is not None and math.isfinite(f) and math.isfinite(t)
               and f > 0 else None)
        stated = _num(e.get("pct_change_stated"))
        if stated is not None and not math.isfinite(stated):
            errs.append(f"eps_revision {e.get('period')}: pct_change_stated is not a number "
                        f"(write 10.0, not '10%')")
            stated = None
        if stated is not None and pct is not None and abs(stated - pct) > PCT_TOLERANCE:
            warns.append(f"eps {e.get('period')}: stated {stated}% vs recomputed {pct}%")
        eps.append({"period": _text(e.get("period"))[:40],
                    "fiscal_context": _text(e.get("fiscal_context"))[:40],
                    "eps_from": f, "eps_to": t, "pct_change": pct,
                    "pct_change_stated": stated, "consensus": c,
                    "vs_consensus_pct": (round(100.0 * (t / c - 1.0), 4)
                                         if t is not None and c and c > 0 and math.isfinite(c)
                                         and math.isfinite(t) else None)})
    out["eps_revisions"] = eps

    out["key_debates"] = [{"text": _text(d.get("text") if isinstance(d, dict) else d)[:MAX_TEXT],
                           "page": (_page(d.get("page"), errs, f"key_debate {i}")
                                    if isinstance(d, dict) else None)}
                          for i, d in enumerate(report.get("key_debates") or []) if _text(
                              d.get("text") if isinstance(d, dict) else d)]
    cats = []
    for i, c in enumerate(report.get("catalysts") or []):
        if not isinstance(c, dict) or not _text(c.get("event")):
            errs.append(f"catalyst {i}: needs an event")
            continue
        d = _day(c.get("expected_date"))
        if d == "INVALID":
            errs.append(f"catalyst {i}: expected_date must be an ISO date or null")
        cats.append({"event": _text(c.get("event"))[:MAX_TEXT], "expected_date": d,
                     "date_stated_by_source": bool(c.get("date_stated_by_source", d is not None)),
                     "page": _page(c.get("page"), errs, f"catalyst {i}")})
    out["catalysts"] = cats
    fals = []
    for i, f_ in enumerate(report.get("falsifiers") or []):
        if not isinstance(f_, dict) or not _text(f_.get("statement")):
            errs.append(f"falsifier {i}: needs a statement")
            continue
        if not _text(f_.get("observable")):
            errs.append(f"falsifier {i}: needs an observable (what would be measured)")
        by = _day(f_.get("by_date"))
        if by in (None, "INVALID"):
            errs.append(f"falsifier {i}: needs a by_date (when it can be checked)")
        fals.append({"statement": _text(f_.get("statement"))[:MAX_TEXT],
                     "observable": _text(f_.get("observable"))[:MAX_TEXT], "by_date": by,
                     "origin": ("source" if f_.get("origin") == "source" else "aegis_hypothesis")})
    out["falsifiers"] = fals
    if not fals:
        errs.append("at least one falsifier is required: a thesis nobody can check is not a row")
    out["warnings"] = warns
    if errs:
        return None, errs
    return out, []


def to_rows(report: dict) -> list[dict]:
    """A VALIDATED report -> one dated row per fact. Refuses an unvalidated one."""
    if report.get("schema_version") != SCHEMA_VERSION:
        raise ReportInvalid("to_rows needs the output of validate_report")
    base = {"schema_version": SCHEMA_VERSION, "source_id": report["source_id"],
            "broker": report["broker"], "ticker": report["ticker"],
            "published_at": report["published_at"], "first_held_at": report["first_held_at"],
            "knowable_at": report["knowable_at"], "pit_safe": report["pit_safe"]}
    rows: list[dict] = [
        {**base, "kind": "rating", "field": "rating", "value": report["rating"],
         "raw": report["rating_raw"]},
        {**base, "kind": "price_target", "field": "price_target", "value": report["price_target"],
         "prior": report["prior_price_target"], "change_pct": report["target_change_pct"],
         "price_at_publication": report["price_at_publication"],
         "implied_upside_pct": report["implied_upside_pct"],
         # The LEVEL is a stale opinion and ranked PERVERSE here (signal_registry
         # `analyst_target_upside_xs`); the CHANGE is the information.
         "rank_on": "change_pct"},
    ]
    for s in report["scenarios"]:
        rows.append({**base, "kind": "scenario", "field": s["name"], "value": s["price_target"],
                     "probability": s["probability"], "assumptions": s["assumptions"]})
    for e in report["eps_revisions"]:
        rows.append({**base, "kind": "eps_revision", "field": e["period"],
                     "value": e["pct_change"], **{k: e[k] for k in (
                         "fiscal_context", "eps_from", "eps_to", "consensus",
                         "vs_consensus_pct", "pct_change_stated")}})
    for d in report["key_debates"]:
        rows.append({**base, "kind": "key_debate", "field": "debate", "value": d["text"],
                     "page": d["page"]})
    for c in report["catalysts"]:
        rows.append({**base, "kind": "catalyst", "field": "event", "value": c["event"],
                     "expected_date": c["expected_date"],
                     "date_stated_by_source": c["date_stated_by_source"], "page": c["page"]})
    for f in report["falsifiers"]:
        rows.append({**base, "kind": "falsifier", "field": f["observable"], "value": f["statement"],
                     "by_date": f["by_date"], "origin": f["origin"]})
    seen: dict[tuple, int] = {}
    for r in rows:
        key = (r["source_id"], r["kind"], str(r["field"]))
        ordinal = seen.get(key, 0)
        seen[key] = ordinal + 1
        r["row_id"] = hashlib.sha256(json.dumps([*key, ordinal]).encode()).hexdigest()[:16]
        r["content_hash"] = hashlib.sha256(json.dumps(
            {k: v for k, v in r.items() if k not in ("row_id", "content_hash")},
            sort_keys=True, default=str).encode()).hexdigest()[:16]
    return rows


def visible_at(rows: Iterable[dict], asof: str) -> list[dict]:
    """Rows a decision dated `asof` may read: knowable STRICTLY before it, and
    point-in-time safe. The same asymmetry as `ledger_retrieval.visible_at`."""
    a = _day(asof)
    if a in (None, "INVALID"):
        raise ReportInvalid(f"asof {asof!r} is not a date")
    return [r for r in rows if r.get("pit_safe") and r.get("knowable_at")
            and str(r["knowable_at"]) < a]


def append_rows(rows: Iterable[dict], path: Path) -> int:
    """Append-only, temp -> verify -> replace. An identical row (same row_id AND
    content_hash) is not written twice. A DIFFERENT extraction of a source that
    is already in the file is refused: a re-extraction with a later
    `first_held_at` appended beside the old rows would leave the old, earlier
    `knowable_at` visible -- a point-in-time hole. Correct a source by writing
    to a new file and replacing the old one by hand. Returns rows written."""
    path = Path(path)
    have: dict[str, str] = {}
    sources_in_file: set[str] = set()
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    for line in old.splitlines():
        try:
            r0 = json.loads(line)
            have[r0["row_id"]] = r0.get("content_hash", "")
            sources_in_file.add(r0["source_id"])
        except (ValueError, KeyError, TypeError):
            continue
    rows = list(rows)
    changed = [r["row_id"] for r in rows
               if r.get("row_id") in have and have[r["row_id"]] != r.get("content_hash")]
    fresh_from_known = [r["row_id"] for r in rows
                        if r.get("row_id") not in have and r.get("source_id") in sources_in_file]
    if changed or fresh_from_known:
        raise ReportInvalid(
            f"{path} already holds a different extraction of source "
            f"{rows[0].get('source_id') if rows else '?'} ({len(changed)} changed, "
            f"{len(fresh_from_known)} new rows); refusing to append beside it")
    new = [r for r in rows if r.get("row_id") not in have]
    if not new:
        return 0
    body = old + ("" if not old or old.endswith("\n") else "\n") + "".join(
        json.dumps(r, sort_keys=True, default=str) + "\n" for r in new)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body)
    if Path(tmp).read_text(encoding="utf-8") != body:
        Path(tmp).unlink(missing_ok=True)
        raise OSError(f"verify failed writing {path}")
    os.replace(tmp, path)
    return len(new)
