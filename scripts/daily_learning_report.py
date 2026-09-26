"""The daily learning report -- one section per question Murat asked, no prose.

    python -m scripts.daily_learning_report --date 2026-09-26
    -> backend/data/optimus/learning_reports/report_<date>.md  (+ .json)

WHY (chunk I, 2026-09-26; `docs/research_notes/2026-09-26/external_session_brief_2026-09-26.md` §I)
=====================================================================================================
Every stage of the pipeline writes a receipt, and nothing read them together.
A day ended with thirty files and no answer to "what did we learn?". This
script is the reader: each of Murat's questions is a section, each number in
a section carries the path of the file it came from, and a section whose
input does not exist for the date says `no data today` (or `not yet built`
when the producing chunk has not landed) instead of borrowing yesterday's.

The day ends with three sentences -- WHAT CURRENTLY WORKS / WHAT DOES NOT /
THE SINGLE HIGHEST-EV NEXT EXPERIMENT -- and every one is TEMPLATED FROM
NUMBERS. There is no LLM anywhere in this file, so the report cannot say
anything its receipts do not. Two rules bind the sentences:

* "works" needs a POSITIVE held-out or forward number with its n printed,
  named at its (arm, observable, horizon) cell -- never the arm-blended number,
  which let a volatility forecaster wear a stock-picker's score (review
  2026-09-26 H+I §2.1). An LLM MAGNITUDE cell must also beat the free
  sigma_63 vol prior (`forecast_reputation.vol_prior_skill`) on the same
  held-out rows, printed beside it; when the prior wins, the sentence says the
  prior works and the LLM does not add.
* "does not" needs a NEGATIVE number on a LIVE surface with its n: an arm
  retired at weight 0 is a corpse and is never named.
* the experiment is chosen from `EXPERIMENT_CANDIDATES` by
  EV = P x C x Delta x T - cost, where P is DERIVED (the power a perfectly
  calibrated forecaster with the measured stated-p spread could reach, times a
  declared factor for the sign of the measured skill), C is the capital at risk
  in the surface the result would change, and anything ALREADY RUNNING is
  ineligible. The hand-set table this replaced ranked two running experiments
  on its first day (review §2.2, §3).

"more / less compute tomorrow" reads each purpose's graded rows at their
(arm, observable, horizon) cell, never the family: MORE only on a positive
held-out cell (and, for magnitude, a win over the free prior); a purpose that
spent $0 gets NO_VERDICT; rows already due but ungraded are WAITING_ON_GRADER
(the grader's lateness is not the purpose's); rows not yet due HOLD; a purpose
that links to no forecast row at all gets LESS.

The code-reachability line excludes `backend/tests` (591 of the 614 "orphans"
on 2026-09-26 were test files) and prints every remaining orphan with its
recorded reason; one with no reason is RED.

Dates are UTC days (`ts`, `made_at`, `resolved_at` are UTC); files are read by
the date in their NAME or their own stamp, never by filesystem mtime (CLAUDE.md
protocol 7).

"Data nobody consumed" is the cheap version: a receipt family (top-level
folder under the ledger dir) or a PIT collector prefix that got rows dated
today, and that no more than ONE non-test source file names (the writer). The
read side is generous -- any quoted mention counts -- so the list errs quiet.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logger = logging.getLogger(__name__)

SCHEMA = "daily_learning_report/1"
NO_DATA = "no data today"
NOT_BUILT = "not yet built"

#: A held-out arm is admitted to the closing sentences only at this many rows.
MIN_N_SENTENCE = 50

#: Spend below this prints as $0.0000 and gets no compute verdict.
ZERO_SPEND_USD = 5e-5

#: The free baseline every LLM MAGNITUDE forecast must beat before "works" may
#: name it (review 2026-09-26 H+I §2.1): `forecast_reputation.vol_prior_skill`,
#: p = 2(1 - Phi(thr / (sigma_63 sqrt h))), on the same held-out rows.
VOL_PRIOR_HORIZONS: tuple[int, ...] = (1, 5)
BARS_REL = Path("prices_2025_26") / "bars.parquet"

# ─────────────────────────────── the experiment list ────────────────────────
#
# The hand-set EXPERIMENTS table (P and value as builder constants) is gone:
# on its first day it ranked two experiments that were already running
# (review 2026-09-26 H+I §2.2, §3). Every candidate now carries
#
#   P  = power x PRIOR_FACTOR[sign of the measured held-out skill]
#        power   = Phi(t_max - 1.96), t_max = sd(p) sqrt(n_eff) / (2 sqrt(b(1-b)))
#                  -- the t a PERFECTLY calibrated forecaster with that stated-p
#                  spread could reach; its Brier-skill ceiling is sd(p)^2/(b(1-b)),
#                  so an arm whose p spans 0.02 cannot earn more than ~0.3%.
#        n_eff   = rows per made-day x non-overlapping blocks in the window
#   V  = C x Delta x T, C = capital at risk in the surface the result changes
#        (read from a receipt where one exists), Delta and T declared with source
#   EV = P x V - cost ;  an experiment ALREADY RUNNING is ineligible, whatever EV.
#
#: P's second factor: a measured positive still has to replicate forward; a
#: measured non-positive says the effect is probably absent. Declared, printed.
PRIOR_FACTOR: dict[str, float] = {"positive": 0.5, "unmeasured": 0.35, "non_positive": 0.25}
#: Two-sided 5% bar for "the result changes the roadmap".
T_BAR = 1.96

EXPERIMENT_CANDIDATES: list[dict[str, Any]] = [
    {"id": "PROBE_WEIGHTING_3WAYS",
     "what": ("the same PROBE names weighted three ways (equal / inverse-sigma_63 / "
              "big-predicted-|move| tilt), frozen as $1M twins; arm differences "
              "regressed on SPY, IWM, MTUM, USMV"),
     "forecaster": "vol_prior_h1", "window_sessions": 21, "block_sessions": 1,
     "surface": "PC-PAPER", "capital_default_usd": 1_000_000.0,
     "delta": 0.03375,
     "delta_source": ("0.5 x gamma 3 x (0.25^2 - 0.20^2): inverse-sigma cuts book vol "
                      "25% -> 20% at the same mean (reviewer H+I §5; USMV regression tests it)"),
     "years": 1.0, "cost_usd": 0.0,
     "running_pattern": r"probe.*(inv|ew|equal|tilt)"},
    {"id": "FORMULA_VS_LLM_RESIDUAL",
     "what": ("write the sigma_63 prior as its own `formula:vol63` arm and grade the LLM "
              "on Brier improvement OVER it on the next 6 date blocks"),
     "forecaster": "prior_minus_llm_h1", "window_sessions": 6, "block_sessions": 1,
     "surface": "u_forecast LLM spend (annualised)", "capital_default_usd": None,
     "delta": 1.0, "delta_source": "the whole magnitude budget is freed if the prior wins",
     "years": 1.0, "cost_usd": 0.0,
     "running_pattern": r"^formula:vol63"},
    {"id": "INVESTIGATOR_DIRECTION_CALIBRATION",
     "what": "calibrate the investigator's DIRECTION rows over 21 sessions",
     "forecaster": "direction_rows", "window_sessions": 21, "block_sessions": 5,
     "surface": "PC-PAPER", "capital_default_usd": 1_000_000.0,
     "delta": 0.01,
     "delta_source": "upper bound: a direction signal this flat is worth <= 1%/yr (reviewer H+I §2.2)",
     "years": 1.0, "cost_usd": None,
     "running_pattern": None},
]


# ─────────────────────────────── small helpers ──────────────────────────────

def _base_default() -> Path:
    from backend import config as C
    return Path(C.OPTIMUS_LEDGER_DIR)


def _rel(p: Path | str) -> str:
    p = Path(p)
    try:
        return p.resolve().relative_to(REPO.resolve()).as_posix()
    except (ValueError, OSError):
        return p.as_posix()


def _load(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(p: Path):
    try:
        fh = Path(p).open(encoding="utf-8")
    except OSError:
        return
    with fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                yield json.loads(ln)
            except ValueError:
                continue


def _pct(v: Any, nd: int = 2) -> str:
    try:
        return f"{float(v) * 100:+.{nd}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(v: Any, nd: int = 2) -> str:
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


def _usd(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "n/a"
    return f"${x:,.4f}" if abs(x) < 10 else f"${x:,.0f}"


def _day_of(v: Any) -> str:
    return str(v or "")[:10]


def _section(sid: str, question: str) -> dict:
    return {"id": sid, "question": question, "status": "OK", "lines": []}


def _say(sec: dict, text: str, path: Path | str | None = None) -> None:
    sec["lines"].append(text + (f" (`{_rel(path)}`)" if path is not None else ""))


def _nodata(sec: dict, why: str, path: Path | str | None = None,
            latest: Path | None = None) -> None:
    sec["status"] = "NO_DATA"
    _say(sec, f"{NO_DATA}: {why}", path)
    if latest is not None:
        _say(sec, "latest receipt of this kind (not read as today's)", latest)


def _latest_before(folder: Path, pattern: str, day: str) -> Path | None:
    best = None
    if not folder.exists():
        return None
    for p in folder.glob(pattern):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
        if m and m.group(1) < day and (best is None or m.group(1) > best[0]):
            best = (m.group(1), p)
    return best[1] if best else None


def _family(specialist: Any) -> str:
    return str(specialist).split(":")[0]


# ─────────────────────────────── the ledger ─────────────────────────────────

def _read_ledger(base: Path) -> dict:
    """One pass over predictions.jsonl, minimal fields per row."""
    path = base / "predictions.jsonl"
    rows: dict[str, dict] = {}
    raw: list[dict] = []
    if not path.exists():
        return {"path": path, "exists": False, "rows": rows, "raw": raw}
    for r in _jsonl(path):
        raw.append(r)
        pid = str(r.get("prediction_id") or "")
        if not pid:
            continue
        rows[pid] = {
            "specialist": str(r.get("mechanism_id") or r.get("specialist") or "UNATTRIBUTED"),
            "outcome": r.get("outcome"), "brier": r.get("brier"),
            "observable": r.get("observable"), "horizon": r.get("horizon_days"),
            "resolved_at": _day_of(r.get("resolved_at")),
            "resolves_after": _day_of(r.get("resolves_after")),
        }
    return {"path": path, "exists": True, "rows": rows, "raw": raw}


# ─────────────────────────────── sections ───────────────────────────────────

def s_resolved(day: str, base: Path, ledger: dict) -> dict:
    sec = _section("resolved", "What resolved today?")
    rec, rp = None, None
    for p in sorted(base.glob(f"night_factory_*/grade_forecasts_{day}.json")):
        d = _load(p)
        if isinstance(d, dict) and (rec is None or str(d.get("written_utc")) > str(rec.get("written_utc"))):
            rec, rp = d, p
    today_rows = [r for r in ledger["rows"].values() if r["resolved_at"] == day]
    sec["n_resolved_today"] = len(today_rows)
    if rec is None and not today_rows:
        _nodata(sec, f"no grade receipt for {day} and no ledger row carries resolved_at={day}",
                ledger["path"] if ledger["exists"] else None)
        return sec
    if rec is not None:
        t = rec.get("totals") or {}
        _say(sec, f"grader: {int(rec.get('newly_resolved') or 0)} newly resolved; "
                  f"{int(rec.get('graded_after_this_run') or 0):,} of {int(rec.get('n_records') or 0):,} "
                  f"records graded; {int(t.get('not_yet_due') or 0):,} not yet due; "
                  f"{int(t.get('NO_BAR_FOR_RESOLUTION_DATE') or 0):,} wait on a bar", rp)
    _say(sec, f"ledger rows with resolved_at={day}: n={len(today_rows)}", ledger["path"])
    fam: dict[str, list] = defaultdict(list)
    for r in today_rows:
        fam[_family(r["specialist"])].append(r)
    for f, rs in sorted(fam.items(), key=lambda kv: -len(kv[1]))[:8]:
        br = [float(r["brier"]) for r in rs if r["brier"] is not None]
        ones = sum(1 for r in rs if r["outcome"] == 1)
        _say(sec, f"  {f}: n={len(rs)}, mean Brier {_num(sum(br) / len(br), 4) if br else 'n/a'}, "
                  f"outcome=1 share {_pct(ones / len(rs), 1)}", ledger["path"])
    return sec


def _arms(rep: Any) -> dict[str, dict]:
    if not isinstance(rep, dict):
        return {}
    return {str(a.get("arm")): a for a in (rep.get("arms") or []) if a.get("arm")}


def s_credibility(day: str, base: Path) -> dict:
    sec = _section("credibility", "Which sources gained or lost credibility?")
    src = base / "sources"
    if not src.exists():
        _say(sec, f"source registry (chunk B): {NOT_BUILT} -- `sources/` does not exist")
    else:
        files = sorted(src.glob(f"*{day}*.json"))
        if not files:
            _say(sec, f"source registry: {NO_DATA} (no file dated {day})", src)
        for p in files[:3]:
            d = _load(p)
            items = (d.get("sources") or d.get("rows") or []) if isinstance(d, dict) else []
            _say(sec, f"source registry: {len(items)} source rows", p)
            ranked = [x for x in items if isinstance(x, dict)
                      and isinstance(x.get("reliability", x.get("weight")), (int, float))]
            ranked.sort(key=lambda x: -float(x.get("reliability", x.get("weight"))))
            for x in ranked[:3]:
                _say(sec, f"  {x.get('source_id') or x.get('name')}: reliability "
                          f"{_num(x.get('reliability', x.get('weight')), 3)} (n={x.get('n', 'n/a')})", p)
    rp = base / "reputation" / f"reputation_{day}.json"
    rep = _load(rp)
    if not isinstance(rep, dict):
        _nodata(sec, f"no reputation receipt for {day}", None,
                _latest_before(base / "reputation", "reputation_*.json", day))
        return sec
    arms = _arms(rep)
    prev_p = _latest_before(base / "reputation", "reputation_*.json", day)
    parms = _arms(_load(prev_p)) if prev_p else {}
    if parms:
        deltas = []
        for k, a in arms.items():
            b = parms.get(k)
            if b and a.get("skill") is not None and b.get("skill") is not None:
                deltas.append((float(a["skill"]) - float(b["skill"]), k, a, b))
        deltas.sort(key=lambda x: x[0])
        gained = [d for d in reversed(deltas) if d[0] > 1e-9][:3]
        lost = [d for d in deltas if d[0] < -1e-9][:3]
        for tag, rows in (("gained", gained), ("lost", lost)):
            for dl, k, a, b in rows:
                _say(sec, f"{tag}: `{k}` held-out skill {_pct(b['skill'])} -> {_pct(a['skill'])} "
                          f"({_pct(dl)}; n {b.get('n')} -> {a.get('n')}) vs {prev_p.name}", rp)
        if not gained and not lost:
            _say(sec, f"no arm's held-out skill moved between {prev_p.name} and today "
                      f"({len(deltas)} arms compared)", rp)
    else:
        _say(sec, "no earlier reputation receipt to compare; levels only", rp)
        for k, a in sorted(arms.items(), key=lambda kv: -(kv[1].get("skill") or -9))[:3]:
            _say(sec, f"  `{k}`: held-out skill {_pct(a.get('skill'))} (n={a.get('n')})", rp)
    return sec


def _non_twin(b: dict) -> bool:
    return not b.get("twin") and "__" not in str(b.get("name", ""))


def s_books(day: str, base: Path) -> dict:
    sec = _section("books_vs_spy", "Which books beat SPY?")
    lp = base / "llm_portfolio" / f"leaderboard_{day}.json"
    rp = base / "paper_accounts" / f"roi_{day}.json"
    lb, roi = _load(lp), _load(rp)
    sec["books_graded"], sec["accounts_live"], sec["accounts_agg"] = [], [], {}
    if not isinstance(lb, dict) and not isinstance(roi, dict):
        _nodata(sec, f"no book leaderboard and no paper-account ROI receipt for {day}")
        return sec
    if isinstance(lb, dict):
        books = [b for b in (lb.get("books") or []) if _non_twin(b)]
        graded = [b for b in books if b.get("vs_benchmark") is not None]
        beat = [b for b in graded if float(b["vs_benchmark"]) > 0]
        _say(sec, f"frozen books: {len(graded)} of {len(books)} graded; {len(beat)} beat their "
                  f"benchmark (bars through {lb.get('bars_through')})", lp)
        why = Counter(str(b.get("why")) for b in books if b.get("vs_benchmark") is None)
        if why and not graded:
            w, n = why.most_common(1)[0]
            _say(sec, f"  ungraded because: {w} (n={n})", lp)
        for b in sorted(graded, key=lambda b: -float(b["vs_benchmark"]))[:3]:
            _say(sec, f"  `{b.get('name')}`: {_pct(b['vs_benchmark'])} vs {b.get('benchmark')} "
                      f"over {b.get('sessions')} session(s), net {_pct(b.get('net_to_date'))}", lp)
        sec["books_graded"] = graded
    else:
        _say(sec, f"frozen books: {NO_DATA} (no leaderboard_{day}.json)")
    if isinstance(roi, dict):
        agg = roi.get("aggregate") or {}
        ap = agg.get("all_priced") or {}
        _say(sec, f"paper accounts (own window, to date -- not a one-day number): "
                  f"{agg.get('n_ahead_of_spy')} ahead of SPY, {agg.get('n_behind_spy')} behind, "
                  f"n={ap.get('n')} priced, pooled ROI {_num(ap.get('roi_pct'), 3)}%", rp)
        live = [r for r in (roi.get("rows") or []) if r.get("status") == "LIVE"
                and "twin" not in str(r.get("family")) and r.get("vs_spy_pp") is not None]
        for r in sorted(live, key=lambda r: -float(r["vs_spy_pp"]))[:3]:
            _say(sec, f"  `{r.get('account')}` ({r.get('family')}): {_num(r['vs_spy_pp'])} pp vs SPY "
                      f"since {r.get('inception')}, last mark {r.get('last_mark')}", rp)
        sec["accounts_live"] = live
        sec["accounts_agg"] = {"n_ahead": agg.get("n_ahead_of_spy"), "n_behind": agg.get("n_behind_spy"),
                               "n": ap.get("n"), "roi_pct": ap.get("roi_pct")}
    else:
        _say(sec, f"paper accounts: {NO_DATA} (no roi_{day}.json)")
    return sec


def _forensics(day: str, base: Path) -> tuple[Path, Any, str]:
    folder = base / "forensics"
    p = folder / f"fast_movers_{day}.json"
    if not folder.exists():
        return p, None, f"{NOT_BUILT} -- `forensics/` does not exist (chunk A)"
    d = _load(p)
    if d is None:
        return p, None, f"no forensics/fast_movers_{day}.json"
    return p, d, ""


def _movers(d: Any) -> list[dict]:
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    if not isinstance(d, dict):
        return []
    for k in ("cases", "movers", "rows", "fast_movers", "positions", "events"):
        v = d.get(k)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def _m_entry(r: dict) -> str:
    return _day_of(r.get("S") or r.get("entry_date") or r.get("entry_ts") or r.get("entry")
                   or r.get("date"))


def _catalyst(r: dict) -> str:
    ex = r.get("ex_post_catalyst") or r.get("catalyst")
    if isinstance(ex, dict):
        for k in ("headline", "title", "top_title", "titles", "top_titles", "label"):
            v = ex.get(k)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, str) and v:
                return v
        return f"mechanism {r.get('mechanism') or 'not recorded'}"
    return str(ex) if ex else f"mechanism {r.get('mechanism') or 'not recorded'}"


def _credited(r: dict) -> bool:
    return str(r.get("credit")) == "credited"


def _m_class(r: dict) -> str:
    return str(r.get("classification") or r.get("class") or r.get("label") or "UNCLASSIFIED")


def _m_move(r: dict) -> Any:
    for k in ("move", "max_abs_move", "ret", "return", "ret_1d", "ret_5d"):
        if r.get(k) is not None:
            return r.get(k)
    return None


def s_fast_movers(day: str, base: Path) -> tuple[dict, dict, list[dict]]:
    sec = _section("fast_movers", "Fast movers: which did we predict, which did we miss, and why did they move?")
    mech = _section("mechanism", "Did AEGIS predict the mechanism?")
    p, d, why = _forensics(day, base)
    rows = _movers(d) if d is not None else []
    if not rows:
        w = why or "the forensics receipt lists no movers"
        _nodata(sec, w, p if d is not None else None)
        _nodata(mech, w, p if d is not None else None)
        return sec, mech, []
    pred = [r for r in rows if r.get("predicted") is True or _m_class(r) == "PREDICTED_MECHANISM"]
    fav = [r for r in rows if r.get("direction") is None or float(r.get("direction") or 1) * float(_m_move(r) or 0) > 0]
    _say(sec, f"fast movers: n={len(rows)} ({len(fav)} favourable); predicted {len(pred)}, missed "
              f"{len(rows) - len(pred)}; credited vs matched controls {sum(map(_credited, rows))}", p)
    rows = sorted(rows, key=lambda r: (not r.get("priority"), -abs(float(_m_move(r) or 0))))
    for r in rows[:10]:
        _say(sec, f"  {r.get('ticker')} ({r.get('book', '?')}) entry {_m_entry(r)} move "
                  f"{_pct(_m_move(r), 1)}: {_m_class(r)}, credit {r.get('credit', 'n/a')}; "
                  f"ex post: {_catalyst(r)[:90]}", p)
    cls = Counter(_m_class(r) for r in rows)
    k = cls.get("PREDICTED_MECHANISM", 0)
    npred = sum(1 for r in rows if r.get("predicted") is True)
    _say(mech, f"PREDICTED_MECHANISM {k} of {len(rows)} ({_pct(k / len(rows), 1)}); other classes: "
               + (", ".join(f"{c} {v}" for c, v in cls.most_common() if c != "PREDICTED_MECHANISM") or "none"), p)
    _say(mech, f"mechanism visible at entry (`predicted`): {npred} of {len(rows)}; credited (beat the "
               f"matched-control median by >= 1 sigma_h with the mechanism visible): "
               f"{sum(map(_credited, rows))} of {len(rows)}", p)
    return sec, mech, rows


def _tickers_of(pos: Any) -> set[str]:
    if isinstance(pos, str):
        return {t.upper() for t in re.findall(r"['\"]ticker['\"]\s*:\s*['\"]([^'\"]+)['\"]", pos)}
    return {str(x.get("ticker")).upper() for x in (pos or []) if isinstance(x, dict) and x.get("ticker")}


def _books_positions(base: Path) -> tuple[Path, list[dict]]:
    p = base / "llm_portfolio" / "books.jsonl"
    out = [{"name": str(b.get("name")), "model": str(b.get("model") or ""),
            "asof": _day_of(b.get("asof") or b.get("frozen_utc")),
            "tickers": _tickers_of(b.get("positions"))} for b in _jsonl(p)]
    return p, out


def s_capture(day: str, base: Path, movers: list[dict]) -> dict:
    sec = _section("capture", "Which strategy would have captured them?")
    if not movers:
        _, _, why = _forensics(day, base)
        _nodata(sec, why or "no fast movers to join")
        return sec
    bp, books = _books_positions(base)
    if not books:
        _nodata(sec, "no frozen books to join the movers to", bp)
        return sec
    lib = [b for b in books if b["model"].startswith("rule:strategy_library:") and "__" not in b["name"]]
    lib_names = {b["name"] for b in lib}
    first_lib = min((b["asof"] for b in lib), default=None)
    n_cap = 0
    for r in movers:
        t, entry = str(r.get("ticker") or "").upper(), _m_entry(r)
        held = sorted({b["name"] for b in lib if t in b["tickers"] and b["asof"] <= entry})
        later = sorted({b["name"] for b in lib if t in b["tickers"] and b["asof"] > entry})
        other = sorted({b["name"] for b in books if b["name"] not in lib_names and "__" not in b["name"]
                        and t in b["tickers"] and b["asof"] <= entry})
        n_cap += bool(held)
        _say(sec, f"{t} entry {entry}: library books holding it on entry: {', '.join(held[:4]) or 'none'}"
                  + (f"; held only AFTER entry (hindsight, not credited): {', '.join(later[:3])}" if later else "")
                  + (f"; other frozen books on entry: {', '.join(other[:3])}" if other else ""), bp)
    _say(sec, f"captured by a library book frozen on/before entry: {n_cap} of {len(movers)}; library "
              f"holdings are stored from {first_lib or 'never'} (an earlier entry cannot be credited)", bp)
    sec["n_captured"] = n_cap
    return sec


def _sealed_key(row: dict) -> str | None:
    for k, v in row.items():
        if "sealed" in k.lower() and isinstance(v, (int, float)) and not isinstance(v, bool):
            return k
    return None


def s_best(day: str, base: Path, books: dict) -> dict:
    sec = _section("best_strategy", "Best historical / sealed / forward strategy")
    lp = base / "strategy_library" / f"leaderboard_{day}.json"
    lb = _load(lp)
    sec["library"] = {}
    found = False
    if isinstance(lb, dict) and (lb.get("top_by_dsr") or lb.get("all_rows")):
        found = True
        top = (lb.get("top_by_dsr") or lb.get("all_rows"))[0]
        _say(sec, f"historical (HINDSIGHT, top by DSR): `{top.get('id')}` CAGR since 2020 "
                  f"{_pct(top.get('hindsight_cagr_since_2020'), 1)} vs SPY "
                  f"{_pct(top.get('hindsight_spy_cagr_since_2020'), 1)}; DSR {_num(top.get('dsr'), 3)} "
                  f"(n={top.get('dsr_n_trials')} cells); by-year `{top.get('by_year_signs')}`; LOO-worst "
                  f"{_pct(top.get('loo_worst_mean_active'))}/mo; t {_num(top.get('t_active_horizon_blocks'))} "
                  f"on {top.get('n_blocks_horizon')} blocks", lp)
        rows = list(lb.get("all_rows") or []) + list(lb.get("top_by_dsr") or [])
        key = next((k for k in (_sealed_key(r) for r in rows) if k), None)
        if key:
            best = max((r for r in rows if isinstance(r.get(key), (int, float))), key=lambda r: r[key])
            _say(sec, f"sealed: `{best.get('id')}` {key} {_pct(best.get(key))}", lp)
            sec["library"] = {"top1": best.get("id"), "sealed": True, "key": key}
        else:
            _say(sec, f"sealed: {NOT_BUILT} -- no sealed/OOS column on the leaderboard (chunk D)", lp)
            sec["library"] = {"top1": top.get("id"), "sealed": False}
    else:
        _say(sec, f"historical / sealed: {NO_DATA} (no strategy_library/leaderboard_{day}.json)")
    cands = []
    for b in books.get("books_graded") or []:
        cands.append((float(b["vs_benchmark"]), f"`{b.get('name')}` {_pct(b['vs_benchmark'])} vs "
                      f"{b.get('benchmark')} over {b.get('sessions')} session(s)",
                      base / "llm_portfolio" / f"leaderboard_{day}.json"))
    for r in books.get("accounts_live") or []:
        cands.append((float(r["vs_spy_pp"]) / 100.0, f"`{r.get('account')}` {_num(r['vs_spy_pp'])} pp vs SPY "
                      f"since {r.get('inception')} (last mark {r.get('last_mark')})",
                      base / "paper_accounts" / f"roi_{day}.json"))
    if cands:
        found = True
        _, txt, p = max(cands, key=lambda c: c[0])
        _say(sec, f"forward (best graded, own window): {txt}", p)
    else:
        _say(sec, f"forward: {NO_DATA} (no graded forward book or live account)")
    if not found:
        sec["status"] = "NO_DATA"
    return sec


def s_features(day: str, base: Path) -> dict:
    sec = _section("features", "Features surviving matched controls")
    sec["features"], sec["n_surviving"] = [], 0
    p, d, why = _forensics(day, base)
    if d is None:
        _nodata(sec, why)
        return sec
    feats = []
    cases = _movers(d)
    if cases and any(isinstance(r.get("candidate_feature"), dict) for r in cases):
        agg: dict[str, dict] = {}
        for r in cases:
            f = r.get("candidate_feature")
            if not isinstance(f, dict) or not f.get("name"):
                continue
            a = agg.setdefault(f["name"], {"name": f["name"], "n": 0, "n_credited": 0,
                                           "observable_pre_entry": 0})
            a["n"] += 1
            a["n_credited"] += int(_credited(r))
            a["observable_pre_entry"] += int(bool(f.get("observable_pre_entry")))
        for a in agg.values():
            a["survives_matched_controls"] = a["n_credited"] > 0
        feats = list(agg.values())
    elif isinstance(d, dict):
        feats = [f for f in (d.get("candidate_features") or d.get("features") or []) if isinstance(f, dict)]
    if not feats:
        _nodata(sec, "the forensics receipt proposes no candidate feature", p)
        return sec
    surv = [f for f in feats if f.get("survives_matched_controls") is True or f.get("survives") is True]
    _say(sec, f"candidate features: {len(feats)}; surviving matched controls: {len(surv)}", p)
    for f in feats[:6]:
        eff = f.get("lift") if f.get("lift") is not None else f.get("effect")
        extra = (f", credited {f['n_credited']} of {f['n']} case(s), observable pre-entry in "
                 f"{f['observable_pre_entry']}" if "n_credited" in f else f", effect {_pct(eff)}")
        _say(sec, f"  `{f.get('feature') or f.get('name')}`: survives="
                  f"{f.get('survives_matched_controls', f.get('survives'))}, n={f.get('n', 'n/a')}{extra}", p)
    sec["features"], sec["n_surviving"] = feats, len(surv)
    return sec


# ─────────────────────────────── data nobody consumed ───────────────────────

SOURCE_ROOTS = ("backend", "scripts", "engine", "lab")
_SELF = Path(__file__).resolve()
#: Files that enumerate names without consuming them.
_NOT_READERS = {"accrual_canary.py"}


def _source_texts(repo: Path) -> dict[Path, str]:
    out = {}
    for root in SOURCE_ROOTS:
        r = repo / root
        if not r.exists():
            continue
        for p in r.rglob("*.py"):
            low = {x.lower() for x in p.parts}
            if "tests" in low or p.name.startswith("test_") or p.name in _NOT_READERS:
                continue
            if p.resolve() == _SELF:
                continue
            try:
                out[p] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return out


def _readers(texts: dict[Path, str], token: str) -> list[Path]:
    pats = (f'"{token}', f"'{token}", f"/{token}/", f"/{token}_")
    return [p for p, t in texts.items() if any(x in t for x in pats)]


def s_unconsumed(day: str, base: Path, *, repo: Path, db_path: Path | None,
                 code_audit: bool) -> dict:
    sec = _section("unconsumed", "Data nobody consumed")
    sec["unconsumed"] = []
    texts = _source_texts(repo)
    found_any = False
    tops: Counter = Counter()
    if base.exists():
        for p in base.rglob(f"*{day}*"):
            if p.is_file():
                top = p.relative_to(base).parts[0]
                if top != "learning_reports" and not top.endswith((".log", ".err")):
                    tops[top] += 1
    for top, n in sorted(tops.items()):
        found_any = True
        name = top
        if (base / top).is_file():
            name = re.sub(r"\.\w+$", "", name)
        name = re.sub(r"_?\d{4}-\d{2}-\d{2}.*$", "", name) or top
        rd = _readers(texts, name)
        if len(rd) <= 1:
            sec["unconsumed"].append({"what": top, "kind": "receipt", "n_files_today": n,
                                      "n_source_files_naming_it": len(rd)})
            _say(sec, f"UNREAD: `{top}` got {n} file(s) dated {day}; non-test source files naming "
                      f"`{name}`: {len(rd)} ({', '.join(_rel(x) for x in rd) or 'none'}) -- a writer "
                      f"at most, no reader", base / top)
    if db_path is not None and Path(db_path).exists():
        try:
            from backend.services.accrual_canary import COLLECTOR_PREFIXES
            con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
            try:
                for cname, prefix in COLLECTOR_PREFIXES.items():
                    n = con.execute("SELECT COUNT(*) FROM pit_observations WHERE key LIKE ? "
                                    "AND substr(observed_at,1,10)=?", (prefix + "%", day)).fetchone()[0]
                    if not n:
                        continue
                    found_any = True
                    rd = _readers(texts, prefix)
                    if len(rd) <= 1:
                        sec["unconsumed"].append({"what": prefix, "kind": "pit_collector",
                                                  "n_rows_today": int(n),
                                                  "n_source_files_naming_it": len(rd)})
                        _say(sec, f"UNREAD: collector `{cname}` wrote {n} PIT row(s) today; non-test "
                                  f"source files naming `{prefix}`: {len(rd)}", db_path)
            finally:
                con.close()
        except (sqlite3.Error, ImportError) as exc:
            _say(sec, f"PIT store unreadable: {type(exc).__name__}: {exc}"[:200], db_path)
    if not found_any:
        _nodata(sec, f"no receipt or PIT row dated {day} was written")
    elif not sec["unconsumed"]:
        _say(sec, f"every receipt family and collector written on {day} is named by a second source file")
    if code_audit:
        try:
            from backend.services import signal_reachability as SR
            a = SR.audit()
            srp = REPO / "backend" / "services" / "signal_reachability.py"
            allo = a.get("orphans") or []
            tests = [o for o in allo if _is_test_module(o["module"])]
            real = [o for o in allo if not _is_test_module(o["module"])]
            n_mod = int(a.get("n_modules") or 0) - sum(1 for _ in _test_modules(a))
            unreasoned = [o["module"] for o in real if not o.get("reason")]
            _say(sec, f"code that computes for nobody (signal_reachability orphans, `backend/tests` "
                      f"excluded): {len(real)} of {n_mod} non-test modules; {len(unreasoned)} with no "
                      f"recorded reason" + (" -- RED" if unreasoned else " (green)")
                      + f"; {len(tests)} test modules excluded (a test is not an orphan)", srp)
            for o in real:
                why = str(o.get("reason") or "").strip()
                _say(sec, f"  {'RED ' if not why else ''}`{o['module']}`: "
                          + (why[:160] + ("..." if len(why) > 160 else "") if why else "NO RECORDED REASON"))
            sec["orphans"] = [o["module"] for o in real]
            sec["orphans_unreasoned"] = unreasoned
            if unreasoned:
                sec["status"] = "RED"
        except Exception as exc:                                   # noqa: BLE001
            _say(sec, f"signal_reachability audit failed: {type(exc).__name__}: {exc}"[:200])
    return sec


def _is_test_module(m: str) -> bool:
    return m.startswith("backend.tests") or ".tests." in m or m.rsplit(".", 1)[-1].startswith("test_")


def _test_modules(a: dict):
    for o in a.get("orphans") or []:
        if _is_test_module(o["module"]):
            yield o["module"]
    for m in a.get("tooling_only") or []:
        if _is_test_module(m):
            yield m


# ─────────────────────────────── compute ────────────────────────────────────

def _telemetry_files(base: Path) -> list[Path]:
    return sorted(p for p in base.glob("llm_calls_*.jsonl")
                  if re.fullmatch(r"llm_calls_\d{4}-\d{2}\.jsonl", p.name))


def _spend(day: str, base: Path) -> dict:
    files = _telemetry_files(base)
    by_purpose: dict[str, float] = defaultdict(float)
    by_pp: dict[tuple, float] = defaultdict(float)
    n_calls: Counter = Counter()
    call_purpose: dict[str, str] = {}
    linked: dict[str, set] = defaultdict(set)
    for f in files:
        for r in _jsonl(f):
            cid = str(r.get("call_id") or "")
            purpose = str(r.get("purpose") or "")
            if purpose and cid:
                call_purpose[cid] = purpose
            pids = r.get("prediction_ids") or []
            if pids and cid:
                linked[cid].update(str(x) for x in pids)
            if purpose and _day_of(r.get("ts")) == day and r.get("row_type", "call") == "call":
                c = float(r.get("cost_usd") or 0.0)
                by_purpose[purpose] += c
                by_pp[(purpose, str(r.get("provider") or "?"))] += c
                n_calls[purpose] += 1
    pids_by_purpose: dict[str, set] = defaultdict(set)
    for cid, pids in linked.items():
        p = call_purpose.get(cid)
        if p:
            pids_by_purpose[p] |= pids
    return {"files": files, "by_purpose": dict(by_purpose), "by_pp": dict(by_pp),
            "n_calls": dict(n_calls), "pids_by_purpose": pids_by_purpose}


def _last_grader_run(base: Path, day: str) -> str | None:
    best = None
    for p in base.glob("night_factory_*/grade_forecasts_*.json"):
        m = re.search(r"grade_forecasts_(\d{4}-\d{2}-\d{2})", p.name)
        if m and m.group(1) <= day and (best is None or m.group(1) > best):
            best = m.group(1)
    return best


def _cell_verdict(key: tuple, cells: dict, ev: dict) -> tuple[str, str]:
    """MORE / LESS / HOLD for one (arm, observable, horizon) cell -- the cell's
    own held-out skill, and for magnitude, its margin over the free prior."""
    arm, obs, h = key
    c = cells.get(key)
    tag = f"`{arm}` {obs} h={h}"
    if c is None or (c.get("n") or 0) < MIN_N_SENTENCE:
        return "HOLD", f"{tag}: held-out skill unmeasured (n={0 if c is None else c.get('n')})"
    if arm not in ev["live"] and ev["live"]:
        return "LESS", f"{tag}: arm retired at weight 0 (cell {_pct(c['skill'])}, n={c['n']})"
    if c["skill"] <= 0:
        return "LESS", f"{tag}: held-out skill {_pct(c['skill'])} (n={c['n']})"
    if obs == "abs_move_exceeds":
        a = ev["vol_arm"].get((arm, h)) or {}
        if a.get("status") != "OK":
            return "HOLD", (f"{tag}: {_pct(c['skill'])} (n={c['n']}) but no comparison with the "
                            f"free vol prior ({a.get('reason') or ev.get('bars_status')})")
        if a.get("winner") == "prior":
            return "LESS", (f"{tag}: {_pct(c['skill'])} (n={c['n']}), but the $0 sigma_63 prior scores "
                            f"{_pct(a['skill_prior'])} vs the LLM {_pct(a['skill_llm'])} on the same "
                            f"n={a['n_heldout']} rows")
        return "MORE", (f"{tag}: LLM {_pct(a['skill_llm'])} beats the free prior "
                        f"{_pct(a['skill_prior'])} (n={a['n_heldout']})")
    return "MORE", f"{tag}: held-out skill {_pct(c['skill'])} (n={c['n']})"


def s_compute(day: str, base: Path, ledger: dict, spend: dict, books: dict, ev: dict) -> dict:
    """More or less compute, per purpose, read at (arm, observable, horizon).

    Review 2026-09-26 H+I §2.2: the old verdict read the FAMILY's blended skill,
    so a purpose writing direction rows got MORE on magnitude credit; it said
    LESS for a purpose that spent $0; and it blamed a purpose for the grader's
    lateness. Now: $0 -> NO_VERDICT; due-but-ungraded -> WAITING_ON_GRADER; a
    graded purpose takes the verdict of the cell holding most of its graded
    rows, every cell printed."""
    sec = _section("compute", "More or less compute tomorrow?")
    sec["decisions"] = {}
    if not spend["by_purpose"]:
        _nodata(sec, f"no LLM call stamped {day} in the telemetry ledger",
                spend["files"][-1] if spend["files"] else None)
        return sec
    tp = spend["files"][-1]
    cells = {(c["arm"], str(c.get("observable")), int(c["horizon_days"])): c for c in ev["cells"]}
    rows = ledger["rows"]
    n_graded_books = len(books.get("books_graded") or [])
    grader = _last_grader_run(base, day)
    for purpose, usd in sorted(spend["by_purpose"].items(), key=lambda kv: -kv[1]):
        mine = [rows[p] for p in spend["pids_by_purpose"].get(purpose, set()) if p in rows]
        due = [r for r in mine if r["resolves_after"] and r["resolves_after"] <= day]
        graded = [r for r in mine if r["outcome"] is not None]
        feeds_books = ("portfolio" in purpose or "book" in purpose) and n_graded_books > 0
        detail: list[str] = []
        if usd < ZERO_SPEND_USD:
            verdict, why = "NO_VERDICT", f"spent {_usd(usd)} (~$0) -- no compute to add or cut"
        elif graded:
            by_cell = Counter((r["specialist"], str(r["observable"]), int(float(r["horizon"] or 0)))
                              for r in graded)
            verdicts = {k: _cell_verdict(k, cells, ev) for k in by_cell}
            top = by_cell.most_common(1)[0][0]
            verdict = verdicts[top][0]
            why = f"{len(graded)} graded row(s); dominant cell {verdicts[top][1]}"
            detail = [f"  {verdicts[k][0]} x{n}: {verdicts[k][1]}" for k, n in by_cell.most_common()
                      if k != top]
        elif feeds_books:
            verdict, why = "HOLD", f"feeds books and {n_graded_books} book(s) graded today"
        elif not mine:
            verdict, why = "LESS", "spent and produced no forecast row the grader can ever grade"
        elif due:
            verdict = "WAITING_ON_GRADER"
            why = (f"{len(due)} linked row(s) already due and none graded -- the grader's lateness, "
                   f"not the purpose's (last grader receipt: {grader or 'none found'})")
        else:
            first_due = min((r["resolves_after"] for r in mine if r["resolves_after"]), default="?")
            verdict, why = "HOLD", f"{len(mine)} linked row(s), none due yet (first due {first_due})"
        sec["decisions"][purpose] = {"verdict": verdict, "usd": usd, "why": why,
                                     "n_calls": spend["n_calls"].get(purpose, 0)}
        provs = ", ".join(f"{pv} {_usd(v)}" for (pu, pv), v in spend["by_pp"].items() if pu == purpose)
        _say(sec, f"{verdict}: `{purpose}` spent {_usd(usd)} on {spend['n_calls'].get(purpose, 0)} "
                  f"call(s) [{provs}] -- {why}", tp)
        for d in detail:
            _say(sec, d, tp)
    sec["total_usd"] = sum(spend["by_purpose"].values())
    _say(sec, f"total LLM spend stamped {day} (UTC): {_usd(sec['total_usd'])}", tp)
    return sec


# ─────────────────────────────── supporting sections ────────────────────────

def s_decisions(day: str, base: Path) -> dict:
    sec = _section("decisions", "Decisions, plan and review today (supporting)")
    ap = base / "decisions" / f"autopsy_{day}.json"
    pp = base / "decisions" / "pc_plan" / f"{day}.json"
    rp = base / "review" / f"review_{day}.json"
    any_ = False
    a = _load(ap)
    if isinstance(a, dict):
        any_ = True
        h = (a.get("headline") or {}).get("1") or {}
        _say(sec, f"autopsy h=1 {h.get('pair', '')}: day-matched gap {_pct(h.get('day_matched_gap'))} "
                  f"(t {_num(h.get('day_matched_t'))}, {h.get('n_date_blocks')} date blocks); "
                  f"refused-but-rose {len(a.get('refused_but_rose') or [])}, "
                  f"bought-but-fell {len(a.get('bought_but_fell') or [])}", ap)
    else:
        _say(sec, f"autopsy: {NO_DATA} (no decisions/autopsy_{day}.json)")
    p = _load(pp)
    if isinstance(p, dict):
        any_ = True
        c = Counter(str(r.get("direction")) for r in p.get("rows") or [])
        _say(sec, "plan rows by direction: " + (", ".join(f"{k} {v}" for k, v in c.most_common()) or "none"), pp)
    else:
        _say(sec, f"plan: {NO_DATA} (no decisions/pc_plan/{day}.json)")
    r = _load(rp)
    if isinstance(r, dict):
        any_ = True
        _say(sec, "review labels: " + ", ".join(f"{k} {v}" for k, v in (r.get("counts") or {}).items()), rp)
    else:
        _say(sec, f"review: {NO_DATA} (no review/review_{day}.json)")
    if not any_:
        sec["status"] = "NO_DATA"
        latest = _latest_before(base / "decisions", "autopsy_*.json", day)
        if latest:
            _say(sec, "latest autopsy (not read as today's)", latest)
    return sec


def s_learned(day: str, base: Path) -> dict:
    sec = _section("learned", "What the night learned: rules, learn runs, policy (supporting)")
    brain = base / "brain"
    runs = [r for r in _jsonl(brain / "learn_runs.jsonl") if _day_of(r.get("as_of")) == day]
    rules = [r for r in _jsonl(brain / "learned_rules.jsonl") if _day_of(r.get("created_utc")) == day]
    journal = [r for r in _jsonl(base / "pc_book" / "policy_journal.jsonl") if _day_of(r.get("t")) == day]
    if not runs and not rules and not journal:
        _nodata(sec, "no learn run, learned rule or policy change dated today")
        return sec
    seen = Counter((r.get("job"), r.get("status"), r.get("n_rules_written"), r.get("reason")) for r in runs)
    for (job, st, nw, reason), k in seen.items():
        _say(sec, f"learn run `{job}` x{k}: {st}, {nw} rule(s) written" + (f" -- {reason}" if reason else ""),
             brain / "learn_runs.jsonl")
    if rules:
        v = Counter(str(r.get("verdict")) for r in rules)
        _say(sec, f"learned rules dated today: n={len(rules)} ("
                  + ", ".join(f"{k} {n}" for k, n in v.most_common()) + ")", brain / "learned_rules.jsonl")
        pos = [r for r in rules if isinstance(r.get("skill"), (int, float)) and r["skill"] > 0
               and (r.get("n_heldout") or 0) >= MIN_N_SENTENCE]
        for r in sorted(pos, key=lambda r: -r["skill"])[:3]:
            _say(sec, f"  positive: `{r.get('fact_key')}` held-out skill {_pct(r['skill'])} "
                      f"(n={r.get('n_heldout')})", brain / "learned_rules.jsonl")
    if journal:
        keys = Counter(str(r.get("key")) for r in journal)
        _say(sec, "policy keys changed today: " + ", ".join(f"{k} x{n}" for k, n in keys.items()),
             base / "pc_book" / "policy_journal.jsonl")
    return sec


def s_health(day: str, base: Path, db_path: Path | None) -> dict:
    sec = _section("health", "Accrual canary (supporting)")
    ledger = base / "predictions.jsonl"
    if not ledger.exists():
        _nodata(sec, "no forecast ledger to check")
        return sec
    try:
        from backend.services import accrual_canary as A
        d = date.fromisoformat(day)
        fa = A.forecast_accrual(ledger, today=d)
        _say(sec, f"forecast accrual: {fa.get('status')} -- {fa.get('reason')}", ledger)
        if db_path is not None and Path(db_path).exists():
            for c in A.collector_liveness(Path(db_path), today=d):
                if c.get("status") != "ok":
                    _say(sec, f"collector `{c.get('collector')}`: {c.get('status')} -- {c.get('reason')}", db_path)
        funnel = None
        try:
            from backend import config as C
            if Path(C.OPTIMUS_LEDGER_DIR).resolve() == base.resolve():
                funnel = getattr(C, "IC_FUNNEL_PATH", None)
        except Exception:                                          # noqa: BLE001
            funnel = None
        nc = A.n_considered_row(base / "decisions", funnel)
        _say(sec, f"n_considered: {nc.get('status')} -- {str(nc.get('reason'))[:160]}", base / "decisions")
    except Exception as exc:                                       # noqa: BLE001
        _say(sec, f"accrual canary failed: {type(exc).__name__}: {exc}"[:200])
    return sec


# ─────────────────────────────── the evidence the sentences read ────────────
#
# One place computes what the closing sentences, the compute verdicts and the
# experiment list are allowed to say: the reputation receipt's per-CELL skill
# (arm, observable, horizon) -- never the arm-blended or family number, which
# lets a volatility forecaster wear a stock-picker's score -- the live arms
# (weight > 0; a weight-0 arm is retired and is never named), and the free
# vol prior beside every LLM magnitude cell.

DIRECTION_OBSERVABLES = ("return_sign", "beats_benchmark")


def _cells(rep: Any) -> list[dict]:
    if not isinstance(rep, dict):
        return []
    out = []
    for c in rep.get("arms_by_observable") or []:
        if c.get("skill") is None or c.get("arm") is None:
            continue
        h = c.get("horizon_days")
        try:
            h = int(float(h))
        except (TypeError, ValueError):
            continue
        out.append({**c, "horizon_days": h})
    return out


def _live_arms(rep: Any) -> set[str]:
    return {k for k, a in _arms(rep).items() if float(a.get("weight") or 0.0) > 0.0}


def _load_bars(base: Path, tickers: set[str], bars_path: Path | None):
    p = Path(bars_path) if bars_path is not None else base / BARS_REL
    if not p.exists():
        return None, p
    try:
        import pandas as pd
        cols = ["symbol", "date", "close"]
        try:
            b = pd.read_parquet(p, columns=cols, filters=[("symbol", "in", sorted(tickers))])
        except Exception:                                          # noqa: BLE001
            b = pd.read_parquet(p, columns=cols)
            b = b[b["symbol"].astype(str).str.upper().isin(tickers)]
        return b, p
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("bars unreadable at %s: %s", p, exc)
        return None, p


def _pooled_skill(g, *, observable: str, horizon: int, arms: set[str]) -> dict:
    """Pooled held-out skill of the live arms on one (observable, horizon):
    later half by made_at, climatology = TRAINING-half base rate (the
    reviewer's split, the same one `vol_prior_skill` uses)."""
    import numpy as np
    import pandas as pd
    s = g[(g["observable"].astype(str) == observable)
          & (pd.to_numeric(g["horizon_days"], errors="coerce") == horizon)
          & (g["arm"].astype(str).isin(arms))]
    if len(s) < 2:
        return {"n": 0, "skill": None}
    s = s.sort_values("made_at", kind="stable")
    tr, te = s.iloc[: len(s) // 2], s.iloc[len(s) // 2:]
    b = float(tr["y"].mean())
    y, p = te["y"].to_numpy(float), te["p"].to_numpy(float)
    clim = float(np.mean((b - y) ** 2))
    sk = (1.0 - float(np.mean((p - y) ** 2)) / clim) if clim > 0 else None
    return {"n": int(len(te)), "skill": sk, "observable": observable, "horizon": horizon}


def gather_evidence(day: str, base: Path, ledger: dict, *, bars_path: Path | None = None) -> dict:
    """Everything the sentences may cite, computed once. Pure reads, $0."""
    from backend.services import forecast_reputation as FR
    rp = base / "reputation" / f"reputation_{day}.json"
    rep = _load(rp)
    ev: dict[str, Any] = {"rep_path": rp, "rep_ok": isinstance(rep, dict),
                          "cells": _cells(rep), "live": _live_arms(rep),
                          "vol": {}, "vol_arm": {}, "direction": [], "bars_path": None,
                          "bars_status": "not needed", "direction_recent": {}}
    raw = ledger.get("raw") or []
    g = FR.graded_frame_from_rows(raw)
    live = ev["live"] or {a for a in g["arm"].astype(str).unique() if a.startswith("investigator:")}
    ev["live_or_investigator"] = live
    # the free prior beside every magnitude horizon the live arms answer
    mag = g[(g["observable"].astype(str) == FR.MAGNITUDE_OBSERVABLE)
            & g["arm"].astype(str).isin(live)]
    if len(mag):
        bars, bp = _load_bars(base, set(mag["ticker"].astype(str).str.upper()), bars_path)
        ev["bars_path"] = bp
        if bars is None:
            ev["bars_status"] = f"no bars at {_rel(bp)}"
        else:
            ev["bars_status"] = "ok"
            sub = g[g["arm"].astype(str).isin(live)]
            for h in VOL_PRIOR_HORIZONS:
                ev["vol"][h] = FR.vol_prior_skill(sub, horizon=h, bars=bars, arm_prefix="")
            for c in ev["cells"]:
                if (c.get("observable") == FR.MAGNITUDE_OBSERVABLE and c["arm"] in live
                        and (c.get("n") or 0) >= MIN_N_SENTENCE):
                    ev["vol_arm"][(c["arm"], c["horizon_days"])] = FR.vol_prior_skill(
                        g, horizon=c["horizon_days"], bars=bars, arm=c["arm"])
    # direction, pooled over the live arms, per (observable, horizon)
    for obs in DIRECTION_OBSERVABLES:
        for h in sorted({int(x) for x in g.loc[g["observable"].astype(str) == obs, "horizon_days"]
                         .dropna().astype(float)}):
            r = _pooled_skill(g, observable=obs, horizon=h, arms=live)
            if r["skill"] is not None:
                ev["direction"].append(r)
    # the direction rows being written NOW (graded or not): their stated-p spread
    import numpy as np
    lo = (date.fromisoformat(day) - timedelta(days=3)).isoformat()
    ps, days_ = [], Counter()
    for r in raw:
        if (str(r.get("observable")) == "beats_benchmark"
                and str(r.get("specialist") or "").startswith("investigator:")
                and lo <= _day_of(r.get("made_at")) <= day):
            try:
                ps.append(float(r.get("probability")))
                days_[_day_of(r.get("made_at"))] += 1
            except (TypeError, ValueError):
                continue
    if ps:
        ev["direction_recent"] = {"n": len(ps), "sd_p": float(np.std(ps)),
                                  "p_min": float(min(ps)), "p_max": float(max(ps)),
                                  "rows_per_day": len(ps) / max(1, len(days_)),
                                  "since": lo}
    return ev


def _pct_or(v: Any) -> str:
    return "n/a" if v is None else _pct(v)


# ─────────────────────────────── the three sentences ────────────────────────

def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def power_line(sd_p: float, base_rate: float, n_eff: float) -> dict:
    """What a PERFECTLY calibrated forecaster with this stated-p spread could
    show: Brier-skill ceiling sd^2/(b(1-b)), and the t it reaches on n_eff
    independent rows, t = sd sqrt(n_eff) / (2 sqrt(b(1-b)))."""
    b = min(max(float(base_rate), 1e-6), 1 - 1e-6)
    v = b * (1 - b)
    ceiling = sd_p ** 2 / v
    t_max = sd_p * math.sqrt(max(n_eff, 0.0)) / (2 * math.sqrt(v))
    return {"sd_p": sd_p, "base_rate": b, "n_eff": n_eff, "ceiling": ceiling,
            "t_max": t_max, "power": _phi(t_max - T_BAR)}


def _capital(base: Path, day: str, surface: str, default: float | None) -> tuple[float | None, str]:
    rp = base / "paper_accounts" / f"roi_{day}.json"
    roi = _load(rp)
    if isinstance(roi, dict):
        for r in roi.get("rows") or []:
            if str(r.get("account")) == surface:
                c = r.get("start_capital") or r.get("equity")
                if isinstance(c, (int, float)) and c > 0:
                    return float(c), f"{surface} capital {_usd(c)} (`{_rel(rp)}`)"
    if default is not None:
        return float(default), f"{surface} declared notional {_usd(default)} (no receipt row)"
    return None, f"{surface}: no capital figure"


def _running(e: dict, base: Path, ledger: dict, ev: dict) -> str | None:
    if e["id"] == "INVESTIGATOR_DIRECTION_CALIBRATION":
        dr = ev.get("direction_recent") or {}
        if dr.get("n"):
            return (f"already running: {dr['n']} investigator `beats_benchmark` rows made since "
                    f"{dr['since']} (u_forecast writes them daily whatever this report says)")
        return None
    pat = e.get("running_pattern")
    if not pat:
        return None
    rx = re.compile(pat, re.I)
    if e["id"] == "FORMULA_VS_LLM_RESIDUAL":
        n = sum(1 for r in ledger.get("raw") or [] if rx.search(str(r.get("specialist") or "")))
        return f"already running: {n} `formula:vol63` ledger rows" if n else None
    bp = base / "llm_portfolio" / "books.jsonl"
    hits = sorted({str(b.get("name")) for b in _jsonl(bp) if rx.search(str(b.get("name") or ""))})
    return f"already running: frozen book(s) {', '.join(hits[:3])}" if hits else None


def _experiments(day: str, base: Path, ledger: dict, ev: dict, spend: dict) -> list[dict]:
    out = []
    v1 = ev.get("vol", {}).get(1) or {}
    uf = float(spend["by_purpose"].get("u_forecast", 0.0))
    for e in EXPERIMENT_CANDIDATES:
        row = {"id": e["id"], "what": e["what"], "eligible": False, "p_used": None,
               "capital_usd": None, "delta": e["delta"], "years": e["years"],
               "value_usd": None, "cost_usd": e["cost_usd"], "ev_usd": None,
               "power": None, "why": "", "delta_source": e["delta_source"]}
        blocks = max(1, e["window_sessions"] // e["block_sessions"])
        pl, measured = None, "unmeasured"
        if e["forecaster"] == "vol_prior_h1":
            if v1.get("status") == "OK" and v1.get("p_spread_prior") is not None:
                per_day = v1["n_heldout"] / max(1, sum(1 for d in v1["by_day"]
                                                       if d["day"] >= v1["heldout_from"]))
                pl = power_line(v1["p_spread_prior"], v1["climatology_base_rate"], per_day * blocks)
                measured = "positive" if (v1.get("skill_prior") or 0) > 0 else "non_positive"
            else:
                row["why"] = f"{NO_DATA}: no vol-prior comparison ({v1.get('reason') or ev.get('bars_status')})"
        elif e["forecaster"] == "prior_minus_llm_h1":
            days = v1.get("by_day") or [] if v1.get("status") == "OK" else []
            if len(days) >= 2:
                d = [x["brier_llm"] - x["brier_prior"] for x in days]
                m = sum(d) / len(d)
                sd = math.sqrt(sum((x - m) ** 2 for x in d) / (len(d) - 1)) or 1e-9
                t = m / sd * math.sqrt(blocks)
                pl = {"t_max": t, "power": _phi(t - T_BAR), "ceiling": None,
                      "sd_p": None, "n_eff": blocks,
                      "note": f"per-day Brier(LLM) - Brier(prior): mean {m:+.4f}, sd {sd:.4f}, {len(d)} days"}
                measured = "positive" if m > 0 else "non_positive"
            else:
                row["why"] = f"{NO_DATA}: fewer than 2 days with both forecasts"
        elif e["forecaster"] == "direction_rows":
            dr = ev.get("direction_recent") or {}
            if dr.get("n"):
                pl = power_line(dr["sd_p"], 0.5, dr["rows_per_day"] * blocks)
                pd_ = [x for x in ev.get("direction") or [] if x["n"] >= MIN_N_SENTENCE]
                if pd_:
                    measured = "positive" if max(x["skill"] for x in pd_) > 0 else "non_positive"
            else:
                row["why"] = f"{NO_DATA}: no investigator direction rows made since {day}-3d"
            row["cost_usd"] = 21 * uf
        if pl is not None:
            row["power"] = pl
            row["measured"] = measured
            row["p_used"] = pl["power"] * PRIOR_FACTOR[measured]
        if e["id"] == "FORMULA_VS_LLM_RESIDUAL":
            cap, cap_why = (uf * 365.0, f"u_forecast spend {_usd(uf)}/day x 365") if uf else (
                None, "no u_forecast spend today")
        else:
            cap, cap_why = _capital(base, day, e["surface"], e["capital_default_usd"])
        row["capital_usd"], row["capital_source"] = cap, cap_why
        if row["p_used"] is not None and cap is not None:
            row["value_usd"] = cap * e["delta"] * e["years"]
            row["ev_usd"] = row["p_used"] * row["value_usd"] - float(row["cost_usd"] or 0.0)
            run = _running(e, base, ledger, ev)
            if run:
                row["why"] = run
            else:
                row["eligible"] = True
                ceil = pl.get("ceiling")
                row["why"] = (f"P = power {pl['power']:.2f} (t_max {pl['t_max']:.2f}"
                              + (f", skill ceiling {_pct(ceil)}" if ceil is not None else "")
                              + f") x prior {PRIOR_FACTOR[measured]} ({measured}); C: {cap_why}")
        elif not row["why"]:
            row["why"] = f"{NO_DATA}: {cap_why}"
        out.append(row)
    return out


def _admit_works(ev: dict) -> list[str]:
    """Candidate "works" clauses (refusals start NOT ADMITTED).

    Per magnitude horizon the live LLM arms answer, the POOLED comparison with
    the free sigma_63 prior is printed first (same held-out rows, both
    numbers). If the prior wins it is the prior that works and the LLM does not
    add. A single arm that beats the prior on its own held-out rows is named
    after it, flagged as the best of N arms (a selection, not a pre-declared
    test) with its days-won count. Non-magnitude cells have no free prior and
    are admitted against climatology, said so."""
    from backend.services import forecast_reputation as FR
    rp = _rel(ev["rep_path"])
    live = ev["live"]
    cells = [c for c in ev["cells"] if c["arm"] in live and (c.get("n") or 0) >= MIN_N_SENTENCE
             and c["skill"] > 0]
    works: list[str] = []
    mag = [c for c in cells if c.get("observable") == FR.MAGNITUDE_OBSERVABLE]
    for h in sorted({c["horizon_days"] for c in mag}):
        hc = sorted((c for c in mag if c["horizon_days"] == h), key=lambda c: -c["skill"])
        n_arms = len({c["arm"] for c in ev["cells"] if c["arm"] in live
                      and c.get("observable") == FR.MAGNITUDE_OBSERVABLE and c["horizon_days"] == h})
        cell = f"{FR.MAGNITUDE_OBSERVABLE} h={h}"
        v = ev["vol"].get(h) or {}
        beat = [(c, ev["vol_arm"][(c["arm"], h)]) for c in hc
                if (ev["vol_arm"].get((c["arm"], h)) or {}).get("status") == "OK"
                and ev["vol_arm"][(c["arm"], h)].get("winner") == "llm"]
        if v.get("status") != "OK":
            why = v.get("reason") or ev.get("bars_status") or "no comparison"
            works.append(f"NOT ADMITTED: `{hc[0]['arm']}` {cell} {_pct(hc[0]['skill'])} (n={hc[0]['n']}) "
                         f"could not be compared to the free sigma_63 prior ({why}), so it is not "
                         f"called working")
            continue
        pooled = (f"{cell}: the free sigma_63 vol prior {_pct(v['skill_prior'])} vs the live LLM arms' "
                  f"posterior {_pct(v['skill_llm'])} on the same n={v['n_heldout']} held-out rows "
                  f"(prior wins {v['days_prior_wins']} of {v['n_days']} days)")
        if v.get("winner") == "prior":
            best = hc[0]
            a = ev["vol_arm"].get((best["arm"], h)) or {}
            txt = pooled + " -- the prior works and the LLM does not add"
            if beat:
                c, a = beat[0]
                txt += (f"; only `{c['arm']}` beats it on its own rows, LLM {_pct(a['skill_llm'])} vs "
                        f"prior {_pct(a['skill_prior'])} (n={a['n_heldout']}; best of {n_arms} live arms, "
                        f"a selection; prior wins {a['days_prior_wins']} of {a['n_days']} days)")
            else:
                txt += (f" (best LLM cell `{best['arm']}` {_pct(best['skill'])} vs climatology, "
                        f"n={best['n']}"
                        + (f"; on its own rows LLM {_pct(a.get('skill_llm'))} vs prior "
                           f"{_pct(a.get('skill_prior'))}" if a.get("status") == "OK" else "") + ")")
        else:
            txt = pooled + " -- the LLM beats the free prior"
        works.append(txt + f" (`{rp}`, bars `{_rel(ev['bars_path'])}`)")
    for c in cells:
        if c.get("observable") == FR.MAGNITUDE_OBSERVABLE:
            continue
        works.append(f"`{c['arm']}` {c.get('observable')} h={c['horizon_days']}: {_pct(c['skill'])} vs "
                     f"climatology (n={c['n']}; no free prior defined for this observable, `{rp}`)")
    return works


def three_sentences(day: str, base: Path, sections: dict, spend: dict, ev: dict,
                    ledger: dict) -> dict:
    books = sections["books_vs_spy"]
    lp = _rel(base / "llm_portfolio" / f"leaderboard_{day}.json")
    cand = _admit_works(ev)
    admitted = [w for w in cand if not w.startswith("NOT ADMITTED")]
    works = [w for w in cand if w.startswith("NOT ADMITTED")]
    doesnt: list[str] = []
    rp = _rel(ev["rep_path"])
    # direction: pooled over live arms, and the worst live direction cell
    dneg = sorted((x for x in ev.get("direction") or [] if x["n"] >= MIN_N_SENTENCE and x["skill"] < 0),
                  key=lambda x: x["skill"])
    if dneg:
        x = dneg[0]
        worst = sorted((c for c in ev["cells"] if c["arm"] in ev["live"]
                        and c.get("observable") in DIRECTION_OBSERVABLES
                        and (c.get("n") or 0) >= MIN_N_SENTENCE and c["skill"] < 0),
                       key=lambda c: c["skill"])
        doesnt.append(f"LLM direction: the live arms' `{x['observable']}` h={x['horizon']} held out "
                      f"{_pct(x['skill'])} (n={x['n']} rows, pooled later half vs the training-half base rate)"
                      + (f"; worst live cell `{worst[0]['arm']}` {_pct(worst[0]['skill'])} (n={worst[0]['n']})"
                         if worst else "") + f" (`{rp}`)")
    for h, v in sorted((ev.get("vol") or {}).items()):
        if (v.get("status") == "OK" and v.get("skill_llm_own_prior") is not None
                and v["skill_llm_own_prior"] > (v.get("skill_llm") or 0)):
            doesnt.append(f"the LLM's evidence step on magnitude h={h}: posterior {_pct(v['skill_llm'])} vs "
                          f"its own stated prior {_pct(v['skill_llm_own_prior'])} on n={v['n_heldout']} "
                          f"held-out rows (reading the dossier lowered skill)")
    graded = books.get("books_graded") or []
    ahead = [b for b in graded if float(b["vs_benchmark"]) > 0]
    behind = [b for b in graded if float(b["vs_benchmark"]) < 0]
    if ahead:
        b = max(ahead, key=lambda b: float(b["vs_benchmark"]))
        admitted.append(f"forward book `{b.get('name')}` {_pct(b['vs_benchmark'])} vs {b.get('benchmark')} "
                        f"(n={b.get('sessions')} sessions; {len(ahead)} of {len(graded)} graded books ahead, `{lp}`)")
    if behind:
        doesnt.append(f"{len(behind)} of {len(graded)} graded forward books trail their benchmark "
                      f"(n={len(graded)} books, `{lp}`)")
    agg = books.get("accounts_agg") or {}
    if agg.get("n") and (agg.get("n_behind") or 0) > (agg.get("n_ahead") or 0):
        doesnt.append(f"the paper accounts: {agg['n_behind']} of {agg['n']} behind SPY over their own windows, "
                      f"pooled ROI {_num(agg.get('roi_pct'), 3)}% (n={agg['n']} accounts, "
                      f"`{_rel(base / 'paper_accounts' / f'roi_{day}.json')}`)")
    exps = _experiments(day, base, ledger, ev, spend)
    elig = sorted([e for e in exps if e["eligible"]], key=lambda e: -e["ev_usd"])
    s1 = ("WHAT CURRENTLY WORKS: " + "; ".join(admitted + works) + ".") if admitted else (
        f"WHAT CURRENTLY WORKS: nothing admissible -- {NO_DATA} with a positive held-out or forward "
        f"number, its n, and (for magnitude) a win over the free vol prior"
        + ("; " + "; ".join(works) if works else "") + ".")
    s2 = ("WHAT DOES NOT: " + "; ".join(doesnt) + ".") if doesnt else (
        f"WHAT DOES NOT: nothing admissible -- {NO_DATA} with a negative held-out or forward "
        f"number on a LIVE surface and its n printed.")
    if elig:
        e = elig[0]
        ru = f"; runner-up `{elig[1]['id']}` EV ${elig[1]['ev_usd']:,.0f}" if len(elig) > 1 else ""
        s3 = (f"THE SINGLE HIGHEST-EV NEXT EXPERIMENT: `{e['id']}` -- {e['what']}; EV = P {e['p_used']:.2f} "
              f"x C ${e['capital_usd']:,.0f} x Delta {e['delta']:.4f} x T {e['years']:g}y "
              f"- cost ${float(e['cost_usd'] or 0):,.2f} = ${e['ev_usd']:,.0f} ({e['why']}){ru}.")
    else:
        why = "; ".join(f"`{e['id']}`: {e['why']}" for e in exps)
        s3 = (f"THE SINGLE HIGHEST-EV NEXT EXPERIMENT: none eligible -- no derived ranking yet "
              f"({NO_DATA} or already running: {why}).")
    return {"works": s1, "does_not": s2, "next_experiment": s3, "experiments": exps}


# ─────────────────────────────── build / write ──────────────────────────────

_DEFAULT = object()


def build(day: str, *, base: Path | None = None, repo: Path | None = None,
          db_path: Any = _DEFAULT, code_audit: bool = True,
          bars_path: Path | None = None) -> dict:
    base = Path(base) if base is not None else _base_default()
    repo = Path(repo) if repo is not None else REPO
    if db_path is _DEFAULT:
        try:
            from backend import db as _db
            db_path = Path(_db.DB_PATH)
        except Exception:                                          # noqa: BLE001
            db_path = None
    ledger = _read_ledger(base)
    spend = _spend(day, base)
    ev = gather_evidence(day, base, ledger, bars_path=bars_path)
    S: dict[str, dict] = {}
    S["resolved"] = s_resolved(day, base, ledger)
    S["credibility"] = s_credibility(day, base)
    S["books_vs_spy"] = s_books(day, base)
    S["fast_movers"], S["mechanism"], movers = s_fast_movers(day, base)
    S["capture"] = s_capture(day, base, movers)
    S["best_strategy"] = s_best(day, base, S["books_vs_spy"])
    S["features"] = s_features(day, base)
    S["unconsumed"] = s_unconsumed(day, base, repo=repo, db_path=db_path, code_audit=code_audit)
    S["compute"] = s_compute(day, base, ledger, spend, S["books_vs_spy"], ev)
    S["decisions"] = s_decisions(day, base)
    S["learned"] = s_learned(day, base)
    S["health"] = s_health(day, base, db_path)
    closing = three_sentences(day, base, S, spend, ev, ledger)
    closing["vol_prior"] = {str(h): {k: v for k, v in r.items() if k != "by_day"}
                            for h, r in (ev.get("vol") or {}).items()}
    return {"schema": SCHEMA, "receipt": "daily_learning_report", "date": day,
            "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base": _rel(base),
            "read_me_first": ("Every sentence is templated from receipt numbers; no LLM wrote any of it. "
                              "A section with no input for this date says `no data today` or `not yet "
                              "built`; nothing is borrowed from another day. Dates are UTC."),
            "sections": S, "closing": closing}


_BULKY = ("books_graded", "accounts_live", "features")


def _strip(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k not in _BULKY}
    if isinstance(o, (list, tuple)):
        return [_strip(x) for x in o]
    if isinstance(o, set):
        return sorted(o)
    return o


def _money(v: Any, nd: int) -> str:
    return "n/a" if v is None else f"${float(v):,.{nd}f}"


def render_md(rep: dict) -> str:
    c = rep["closing"]
    out = [f"# Daily learning report -- {rep['date']}", "", f"> {rep['read_me_first']}", "",
           "## The three sentences", "",
           f"1. {c['works']}", f"2. {c['does_not']}", f"3. {c['next_experiment']}", ""]
    for sec in rep["sections"].values():
        out += [f"## {sec['question']}", ""]
        if sec["status"] != "OK":
            out += [f"_status: {sec['status']}_", ""]
        out += [f"- {ln}" for ln in sec["lines"]] + [""]
    vp = c.get("vol_prior") or {}
    if vp:
        out += ["## The free vol prior beside the LLM (magnitude, held out, same rows)", "",
                "| h | n held out | LLM posterior | LLM's own prior | sigma_63 prior | prior wins days | winner |",
                "|---|---|---|---|---|---|---|"]
        for h, r in sorted(vp.items()):
            if r.get("status") != "OK":
                out.append(f"| {h} | - | - | - | - | - | REFUSED: {r.get('reason')} |")
                continue
            out.append(f"| {h} | {r['n_heldout']} | {_pct_or(r.get('skill_llm'))} | "
                       f"{_pct_or(r.get('skill_llm_own_prior'))} | {_pct_or(r.get('skill_prior'))} | "
                       f"{r['days_prior_wins']} of {r['n_days']} | {r['winner']} |")
        out.append("")
    out += ["## Experiment candidates (EV = P x C x Delta x T - cost; P derived, not declared)", "",
            f"P = Phi(t_max - {T_BAR}) x prior factor {PRIOR_FACTOR}; t_max = sd(p) sqrt(n_eff) / "
            f"(2 sqrt(b(1-b))); Brier-skill ceiling = sd(p)^2 / (b(1-b)). Already running = ineligible.", "",
            "| id | eligible | power | ceiling | P | C | Delta | cost | EV | why |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for e in c["experiments"]:
        pw = e.get("power") or {}
        ce = pw.get("ceiling")
        out.append(f"| {e['id']} | {e['eligible']} | "
                   f"{'n/a' if not pw else format(pw['power'], '.2f')} | "
                   f"{'n/a' if ce is None else _pct(ce)} | "
                   f"{'n/a' if e['p_used'] is None else format(e['p_used'], '.3f')} | "
                   f"{_money(e['capital_usd'], 0)} | {e['delta']:.4f} | {_money(e['cost_usd'], 2)} | "
                   f"{_money(e['ev_usd'], 0)} | {e['why']} |")
    out.append("")
    return "\n".join(out)


def out_dir(base: Path | None = None) -> Path:
    return (Path(base) if base is not None else _base_default()) / "learning_reports"


def write_report(day: str, *, base: Path | None = None, out: Path | None = None, **kw) -> dict:
    rep = build(day, base=base, **kw)
    d = Path(out) if out is not None else out_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    jp, mp = d / f"report_{day}.json", d / f"report_{day}.md"
    tmp = d / f"report_{day}.json.tmp"
    tmp.write_text(json.dumps(_strip(rep), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(jp)
    mp.write_text(render_md(rep), encoding="utf-8")
    return {"json": str(jp), "md": str(mp), "closing": rep["closing"],
            "unconsumed": rep["sections"]["unconsumed"].get("unconsumed", [])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write the daily learning report for one UTC day.")
    ap.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    ap.add_argument("--no-code-audit", action="store_true",
                    help="skip the signal_reachability orphan scan")
    a = ap.parse_args(argv)
    date.fromisoformat(a.date)
    res = write_report(a.date, code_audit=not a.no_code_audit)
    c = res["closing"]
    print(res["md"])
    for k in ("works", "does_not", "next_experiment"):
        print(c[k])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
