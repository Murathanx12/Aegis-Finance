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

* "works" needs a POSITIVE held-out or forward number with its n printed;
  "does not" needs a NEGATIVE one with its n. A number without an n is not
  admitted to either sentence.
* the experiment is chosen by `P(changes the roadmap) x value - cost` from the
  short DECLARED list `EXPERIMENTS`. P and value are declared priors, printed
  in the report; cost is read from the day's spend; an experiment whose input
  receipt does not exist is INELIGIBLE, never ranked on a guess.

"more / less compute tomorrow" is derived, not opined: a purpose that spent
today and whose linked forecast rows (telemetry `prediction_ids`) include no
graded row among those already due -- or that links to no forecast row at
all -- gets LESS; one whose graded rows sit in a family with positive held-out
skill gets MORE; one whose rows are simply not due yet HOLDs.

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
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
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

#: The declared experiment list. p = prior probability the result changes the
#: roadmap; value_usd = value of the decision it would improve; the cost is
#: computed from the day's receipts (see `_experiments`). Edit here, in one
#: place, and the report prints what it used.
EXPERIMENTS: list[dict[str, Any]] = [
    {"id": "LIB_SEALED_TOP1_FORWARD",
     "what": "the strategy library's sealed top-1 as a frozen forward paper book",
     "p": 0.30, "value_usd": 20000.0,
     "needs": "strategy_library/leaderboard_<date>.json",
     "cost_basis": "rule book: $0 LLM"},
    {"id": "INVESTIGATOR_DIRECTION_CALIBRATION",
     "what": "calibrate the investigator's DIRECTION rows (skill unmeasured) over 21 sessions",
     "p": 0.40, "value_usd": 10000.0,
     "needs": "forecasts/day_<date>.json",
     "cost_basis": "21 x today's u_forecast spend"},
    {"id": "SOURCE_REGISTRY_FIRST_GRADED_WEEK",
     "what": "grade the source registry's first week of claims (chunk B)",
     "p": 0.20, "value_usd": 8000.0,
     "needs": "sources/",
     "cost_basis": "7 x the $2/day OpenClaw cap"},
    {"id": "CHUNK_A_CANDIDATE_FEATURE",
     "what": "test chunk A's candidate fast-mover feature against matched controls forward",
     "p": 0.30, "value_usd": 8000.0,
     "needs": "forensics/fast_movers_<date>.json with a candidate feature",
     "cost_basis": "$5 flat (bars + one OpenClaw read per name)"},
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
    if not path.exists():
        return {"path": path, "exists": False, "rows": rows}
    for r in _jsonl(path):
        pid = str(r.get("prediction_id") or "")
        if not pid:
            continue
        rows[pid] = {
            "specialist": str(r.get("mechanism_id") or r.get("specialist") or "UNATTRIBUTED"),
            "outcome": r.get("outcome"), "brier": r.get("brier"),
            "resolved_at": _day_of(r.get("resolved_at")),
            "resolves_after": _day_of(r.get("resolves_after")),
        }
    return {"path": path, "exists": True, "rows": rows}


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
            orph = [o["module"] for o in a.get("orphans") or []]
            _say(sec, f"code that computes for nobody (signal_reachability orphans): {a.get('n_orphaned')} "
                      f"of {a.get('n_modules')} modules: {', '.join(orph[:8])}" + (" ..." if len(orph) > 8 else ""),
                 REPO / "backend" / "services" / "signal_reachability.py")
            sec["orphans"] = orph
        except Exception as exc:                                   # noqa: BLE001
            _say(sec, f"signal_reachability audit failed: {type(exc).__name__}: {exc}"[:200])
    return sec


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


def _family_skill(base: Path, day: str) -> dict[str, tuple[float, int]]:
    acc: dict[str, list] = defaultdict(list)
    for a in _arms(_load(base / "reputation" / f"reputation_{day}.json")).values():
        if a.get("skill") is None or not a.get("n"):
            continue
        acc[str(a.get("family") or _family(a.get("arm")))].append((float(a["skill"]), int(a["n"])))
    out = {}
    for f, xs in acc.items():
        n = sum(k for _, k in xs)
        out[f] = (sum(s * k for s, k in xs) / n, n)
    return out


def s_compute(day: str, base: Path, ledger: dict, spend: dict, books: dict) -> dict:
    sec = _section("compute", "More or less compute tomorrow?")
    sec["decisions"] = {}
    if not spend["by_purpose"]:
        _nodata(sec, f"no LLM call stamped {day} in the telemetry ledger",
                spend["files"][-1] if spend["files"] else None)
        return sec
    tp = spend["files"][-1]
    fam_skill = _family_skill(base, day)
    rows = ledger["rows"]
    n_graded_books = len(books.get("books_graded") or [])
    for purpose, usd in sorted(spend["by_purpose"].items(), key=lambda kv: -kv[1]):
        mine = [rows[p] for p in spend["pids_by_purpose"].get(purpose, set()) if p in rows]
        due = [r for r in mine if r["resolves_after"] and r["resolves_after"] <= day]
        graded = [r for r in mine if r["outcome"] is not None]
        fams = Counter(_family(r["specialist"]) for r in graded)
        fam = fams.most_common(1)[0][0] if fams else None
        sk = fam_skill.get(fam) if fam else None
        feeds_books = ("portfolio" in purpose or "book" in purpose) and n_graded_books > 0
        if graded and sk and sk[0] > 0:
            verdict = "MORE"
            why = f"{len(graded)} graded row(s); family `{fam}` held-out skill {_pct(sk[0])} (n={sk[1]})"
        elif feeds_books:
            verdict, why = "HOLD", f"feeds books and {n_graded_books} book(s) graded today"
        elif not mine:
            verdict, why = "LESS", "spent and produced no forecast row the grader can ever grade"
        elif graded:
            verdict = "LESS"
            why = (f"{len(graded)} graded row(s) but family `{fam}` held-out skill "
                   + (f"{_pct(sk[0])} (n={sk[1]})" if sk else "unmeasured"))
        elif due:
            verdict, why = "LESS", f"{len(due)} linked row(s) already due and none graded"
        else:
            first_due = min((r["resolves_after"] for r in mine if r["resolves_after"]), default="?")
            verdict, why = "HOLD", f"{len(mine)} linked row(s), none due yet (first due {first_due})"
        sec["decisions"][purpose] = {"verdict": verdict, "usd": usd, "why": why,
                                     "n_calls": spend["n_calls"].get(purpose, 0)}
        provs = ", ".join(f"{pv} {_usd(v)}" for (pu, pv), v in spend["by_pp"].items() if pu == purpose)
        _say(sec, f"{verdict}: `{purpose}` spent {_usd(usd)} on {spend['n_calls'].get(purpose, 0)} "
                  f"call(s) [{provs}] -- {why}", tp)
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


# ─────────────────────────────── the three sentences ────────────────────────

def _experiments(day: str, base: Path, sections: dict, spend: dict) -> list[dict]:
    out = []
    lib = sections["best_strategy"].get("library") or {}
    fc = _load(base / "forecasts" / f"day_{day}.json")
    feats = sections["features"].get("features") or []
    for e in EXPERIMENTS:
        row = {**e, "eligible": False, "p_used": e["p"], "cost_usd": None, "ev_usd": None, "why": ""}
        if e["id"] == "LIB_SEALED_TOP1_FORWARD":
            if lib.get("top1"):
                row.update(eligible=True, cost_usd=0.0)
                if lib.get("sealed"):
                    row["why"] = f"sealed top-1 `{lib['top1']}`"
                else:
                    row["p_used"] = e["p"] * 0.5
                    row["why"] = f"top-1 `{lib['top1']}` ranked on HINDSIGHT only (no sealed column): P halved"
            else:
                row["why"] = f"{NO_DATA}: no library leaderboard"
        elif e["id"] == "INVESTIGATOR_DIRECTION_CALIBRATION":
            if isinstance(fc, dict):
                uf = spend["by_purpose"].get("u_forecast", float(fc.get("spent_usd") or 0.0))
                unmeasured = "unmeasured" in str(fc.get("direction_rows", ""))
                row.update(eligible=True, cost_usd=21 * uf)
                if not unmeasured:
                    row["p_used"] = e["p"] * 0.5
                row["why"] = (f"direction skill {'UNMEASURED' if unmeasured else 'already measured (P halved)'}"
                              f" per forecasts/day_{day}.json; u_forecast spend today {_usd(uf)}")
            else:
                row["why"] = f"{NO_DATA}: no forecasts/day_{day}.json"
        elif e["id"] == "SOURCE_REGISTRY_FIRST_GRADED_WEEK":
            if (base / "sources").exists():
                row.update(eligible=True, cost_usd=14.0, why="sources/ exists")
            else:
                row["why"] = f"{NOT_BUILT}: sources/ does not exist"
        elif e["id"] == "CHUNK_A_CANDIDATE_FEATURE":
            if feats:
                surv = sections["features"].get("n_surviving", 0)
                row.update(eligible=True, cost_usd=5.0)
                if not surv:
                    row["p_used"] = e["p"] * 0.5
                row["why"] = f"{len(feats)} candidate feature(s), {surv} surviving matched controls"
            else:
                row["why"] = f"{NO_DATA}: no candidate feature from chunk A"
        if row["eligible"]:
            row["ev_usd"] = row["p_used"] * e["value_usd"] - row["cost_usd"]
        out.append(row)
    return out


def three_sentences(day: str, base: Path, sections: dict, spend: dict) -> dict:
    rp = base / "reputation" / f"reputation_{day}.json"
    arms = [a for a in _arms(_load(rp)).values()
            if a.get("skill") is not None and (a.get("n") or 0) >= MIN_N_SENTENCE]
    books = sections["books_vs_spy"]
    lp = _rel(base / "llm_portfolio" / f"leaderboard_{day}.json")
    works, doesnt = [], []
    if arms:
        best = max(arms, key=lambda a: a["skill"])
        worst = min(arms, key=lambda a: a["skill"])
        if best["skill"] > 0:
            works.append(f"the `{best['arm']}` forecasts, held-out Brier skill {_pct(best['skill'])} vs "
                         f"climatology (n={best['n']} held-out rows, `{_rel(rp)}`)")
        if worst["skill"] < 0:
            doesnt.append(f"the `{worst['arm']}` forecasts, held-out Brier skill {_pct(worst['skill'])} "
                          f"(n={worst['n']} held-out rows, `{_rel(rp)}`)")
    graded = books.get("books_graded") or []
    ahead = [b for b in graded if float(b["vs_benchmark"]) > 0]
    behind = [b for b in graded if float(b["vs_benchmark"]) < 0]
    if ahead:
        b = max(ahead, key=lambda b: float(b["vs_benchmark"]))
        works.append(f"forward book `{b.get('name')}` {_pct(b['vs_benchmark'])} vs {b.get('benchmark')} "
                     f"(n={b.get('sessions')} sessions; {len(ahead)} of {len(graded)} graded books ahead, `{lp}`)")
    if behind:
        doesnt.append(f"{len(behind)} of {len(graded)} graded forward books trail their benchmark "
                      f"(n={len(graded)} books, `{lp}`)")
    agg = books.get("accounts_agg") or {}
    if agg.get("n") and (agg.get("n_behind") or 0) > (agg.get("n_ahead") or 0):
        doesnt.append(f"the paper accounts: {agg['n_behind']} of {agg['n']} behind SPY over their own windows, "
                      f"pooled ROI {_num(agg.get('roi_pct'), 3)}% (n={agg['n']} accounts, "
                      f"`{_rel(base / 'paper_accounts' / f'roi_{day}.json')}`)")
    exps = _experiments(day, base, sections, spend)
    elig = sorted([e for e in exps if e["eligible"]], key=lambda e: -e["ev_usd"])
    s1 = ("WHAT CURRENTLY WORKS: " + "; ".join(works) + ".") if works else (
        f"WHAT CURRENTLY WORKS: nothing admissible -- {NO_DATA} with a positive held-out or forward "
        f"number and its n printed.")
    s2 = ("WHAT DOES NOT: " + "; ".join(doesnt) + ".") if doesnt else (
        f"WHAT DOES NOT: nothing admissible -- {NO_DATA} with a negative held-out or forward "
        f"number and its n printed.")
    if elig:
        e = elig[0]
        ru = f"; runner-up `{elig[1]['id']}` EV ${elig[1]['ev_usd']:,.0f}" if len(elig) > 1 else ""
        s3 = (f"THE SINGLE HIGHEST-EV NEXT EXPERIMENT: `{e['id']}` -- {e['what']}; EV = P {e['p_used']:.2f} "
              f"x value ${e['value_usd']:,.0f} - cost ${e['cost_usd']:,.2f} = ${e['ev_usd']:,.0f} "
              f"({e['why']}){ru}.")
    else:
        s3 = (f"THE SINGLE HIGHEST-EV NEXT EXPERIMENT: none eligible -- every declared experiment lacks "
              f"its input receipt ({NO_DATA}).")
    return {"works": s1, "does_not": s2, "next_experiment": s3, "experiments": exps}


# ─────────────────────────────── build / write ──────────────────────────────

_DEFAULT = object()


def build(day: str, *, base: Path | None = None, repo: Path | None = None,
          db_path: Any = _DEFAULT, code_audit: bool = True) -> dict:
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
    S: dict[str, dict] = {}
    S["resolved"] = s_resolved(day, base, ledger)
    S["credibility"] = s_credibility(day, base)
    S["books_vs_spy"] = s_books(day, base)
    S["fast_movers"], S["mechanism"], movers = s_fast_movers(day, base)
    S["capture"] = s_capture(day, base, movers)
    S["best_strategy"] = s_best(day, base, S["books_vs_spy"])
    S["features"] = s_features(day, base)
    S["unconsumed"] = s_unconsumed(day, base, repo=repo, db_path=db_path, code_audit=code_audit)
    S["compute"] = s_compute(day, base, ledger, spend, S["books_vs_spy"])
    S["decisions"] = s_decisions(day, base)
    S["learned"] = s_learned(day, base)
    S["health"] = s_health(day, base, db_path)
    closing = three_sentences(day, base, S, spend)
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
    out += ["## Declared experiments (P x value - cost)", "",
            "| id | eligible | P used | value | cost | EV | why |", "|---|---|---|---|---|---|---|"]
    for e in c["experiments"]:
        out.append(f"| {e['id']} | {e['eligible']} | {e['p_used']:.2f} | {_money(e['value_usd'], 0)} | "
                   f"{_money(e['cost_usd'], 2)} | {_money(e['ev_usd'], 0)} | {e['why']} |")
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
