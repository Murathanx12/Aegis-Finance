"""THE MORNING SCOREBOARD — the economics first, before any step list.

Murat's item 12, 2026-09-20, verbatim: *"every morning print the economic
scoreboard first: NAV vs SPY, active-alpha P&L, exploration P&L, decisions
made, forecasts matured and graded, calibration, strongest new positive signal,
strongest killed signal, and one sentence on whether anything learned changed
capital."* Roadmap §15.2 chunk 21.

ONE function composes it (`compose`), and it computes NOTHING of its own: every
number is read off a receipt that already exists on disk, through a named
module-level indirection so a test replaces the read rather than the world
(`morning.py`'s pattern, and the house convention). A second function
(`render`) turns the object into the paragraph the desktop Ask and the daily
pass print first.

THE RULE THAT GOVERNS EVERY FIELD
=================================
**A field that cannot be derived prints `CANNOT DETERMINE: <why>`, never a
zero.** A scoreboard that shows `0.0%` where it means "nothing on this machine
has ever marked a NAV" is worse than an empty page, because the reader acts on
it. Four of the nine fields are in that state in this checkout today, and each
says which file was empty and why — this is a fact about the programme (the
laptop does not mark to market; nothing has been SCORED yet), not a defect in
the reader, and it will fill itself in as the receipts arrive.

WHAT IT READS, AND WHAT IT REFUSES TO READ
==========================================
* the decision contract for the day (`decision_contract.latest`) — the capital
  resolution, the authority census, the directions;
* the decision ledger (`decision_ledger`) — DECIDED today, and the realised
  returns on `SCORED` rows, joined BACK to the contract rows so each one is
  attributed to the authority that took it (EXPLOIT P&L and EXPLORE P&L are
  different questions and must never be summed);
* the newest `grade_forecasts_*.json` — matured and graded;
* the newest `decision_vs_reality_*.json` — Brier against the per-mechanism
  BASE-RATE Brier, which is the climatology this repo actually computes;
* the book replay receipts — the strongest new positive and the strongest
  killed, dated by the receipt's OWN stamp (in its filename), never by the
  filesystem: a gate on `st_mtime` is a gate on checkout time (CLAUDE.md
  session protocol 7), and on a fresh CI checkout every receipt would be
  "written today".

It reads no model, spends nothing, writes nothing and places nothing.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config

logger = logging.getLogger(__name__)

LICENCE = "PRODUCT_EXPERIMENT"

#: `<book>_<YYYY-MM-DDTHHMMSSZ>[_smoke].json` — the stamp the WRITER put in the
#: name. Used instead of `st_mtime` on purpose (session protocol 7).
_STAMP = re.compile(r"_(\d{4}-\d{2}-\d{2})T(\d{6})Z")

#: The two receipt families the night writes, newest-first by their own stamp.
_GRADE_GLOB = "grade_forecasts_*.json"
_DVR_GLOB = "decision_vs_reality_*.json"


def _cd(what: str) -> str:
    return f"CANNOT DETERMINE: {what}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_date(asof: date | str | None) -> date:
    if asof is None:
        return datetime.now(timezone.utc).date()
    if isinstance(asof, date):
        return asof
    return date.fromisoformat(str(asof))


# ===========================================================================
# THE INDIRECTIONS. One line each, so a test replaces the NAME.
# ===========================================================================


def decisions_dir() -> Path:
    from backend.services.decision_contract import DECISIONS_DIR
    return DECISIONS_DIR


def contract_blob(asof: date | str, out_dir: Path | None = None) -> dict | None:
    from backend.services import decision_contract as DC
    return DC.latest(asof, out_dir=out_dir)


def ledger_rows(path: Path | None = None) -> list[dict]:
    from backend.services import decision_ledger as DL
    return DL.read(path)


def ledger_summary(asof: date | str, path: Path | None = None) -> dict:
    from backend.services import decision_ledger as DL
    return DL.summary(asof, path=path)


def night_dir() -> Path:
    from backend.services.forecast_grader import out_dir
    return Path(out_dir())


def replay_dir() -> Path:
    from backend.services.decision_contract import REPO
    return REPO / "backend" / "data" / "optimus" / "first_books" / "replay"


def nav_map() -> tuple[dict[str, list[tuple[str, float]]], list[str]]:
    """(series by lane/book, problems). Often EMPTY: the laptop does not mark
    to market, the deployment does (`morning.py`).

    The PROBLEMS are returned rather than logged away. "No NAV exists" and
    "the NAV reader raised" are different findings that would otherwise print
    the same sentence — the exact silent-fragility shape this repo audits for,
    where a caught exception becomes an empty result that reads as a fact.
    """
    out: dict[str, list[tuple[str, float]]] = {}
    problems: list[str] = []
    try:
        from backend.services.morning import lane_nav_series
        out.update(lane_nav_series() or {})
    except Exception as exc:                                       # noqa: BLE001
        logger.info("scoreboard: lane NAV unreadable: %s", exc)
        problems.append(f"lane NAV unreadable ({type(exc).__name__}: {exc})")
    try:
        from backend.services.paper_books import nav_series
        out.update(nav_series() or {})
    except Exception as exc:                                       # noqa: BLE001
        logger.info("scoreboard: book NAV unreadable: %s", exc)
        problems.append(f"book NAV unreadable ({type(exc).__name__}: {exc})")
    return out, problems


def spy_closes(start: str, end: str) -> list[tuple[str, float]]:
    """SPY closes from the bars panel on disk, inclusive. [] when absent."""
    try:
        from backend.services.paper_books import load_bars
        bars = load_bars()
    except Exception as exc:                                       # noqa: BLE001
        logger.info("scoreboard: bars unreadable: %s", exc)
        return []
    if bars is None or getattr(bars, "empty", True):
        return []
    try:
        frame = bars[bars["symbol"] == config.SCOREBOARD_BENCHMARK_SYMBOL]
        frame = frame[(frame["date"].astype(str) >= str(start))
                      & (frame["date"].astype(str) <= str(end))]
        return [(str(d), float(c)) for d, c in
                zip(frame["date"], frame["close"]) if float(c) > 0]
    except Exception as exc:                                       # noqa: BLE001
        logger.info("scoreboard: SPY slice failed: %s", exc)
        return []


# ===========================================================================
# THE FIELDS
# ===========================================================================


def _pct_change(series: list[tuple[str, float]]) -> Optional[float]:
    rows = sorted((d, v) for d, v in series if v and math.isfinite(float(v)))
    if len(rows) < 2 or rows[0][1] <= 0:
        return None
    return 100.0 * (rows[-1][1] / rows[0][1] - 1.0)


def nav_vs_spy(navs: dict[str, list[tuple[str, float]]] | None = None) -> Any:
    """Aggregate NAV since inception against SPY over the SAME window.

    `CANNOT DETERMINE` rather than 0.0% when no NAV exists on this machine —
    which is the state of `paper_nav` in this checkout, and reporting it as a
    flat line would read as "we tracked the market" instead of "nobody marked".
    """
    if navs is None:
        navs, problems = nav_map()
    else:
        problems = []
    usable = {k: v for k, v in (navs or {}).items() if v and len(v) >= 2}
    if not usable:
        if problems:
            return _cd(
                "the NAV readers REFUSED rather than returned nothing, which "
                "is a different finding: " + "; ".join(problems))
        return _cd(
            "no NAV series exists on this machine — `paper_nav` is empty here "
            "because the laptop does not mark to market, the deployment does. "
            "A zero here would read as 'flat against the market'; it means "
            "'nobody marked'")
    rows = []
    starts, ends = [], []
    for book, series in sorted(usable.items()):
        pct = _pct_change(series)
        if pct is None:
            continue
        ordered = sorted(series)
        starts.append(str(ordered[0][0]))
        ends.append(str(ordered[-1][0]))
        rows.append({"book": book, "pct": round(pct, 4),
                     "first_date": str(ordered[0][0]),
                     "last_date": str(ordered[-1][0]),
                     "n_marks": len(series)})
    if not rows:
        return _cd("every NAV series on disk has fewer than two usable marks")
    start, end = min(starts), max(ends)
    spy = spy_closes(start, end)
    spy_pct = _pct_change(spy)
    mean_pct = sum(r["pct"] for r in rows) / len(rows)
    out = {
        "n_books": len(rows),
        "mean_since_inception_pct": round(mean_pct, 4),
        "window": {"first_date": start, "last_date": end},
        "books": rows,
        "benchmark_symbol": config.SCOREBOARD_BENCHMARK_SYMBOL,
    }
    if problems:
        out["partial"] = problems
    if spy_pct is None:
        out["benchmark_pct"] = _cd(
            f"no {config.SCOREBOARD_BENCHMARK_SYMBOL} closes on disk between "
            f"{start} and {end}, so the excess cannot be differenced")
        out["excess_pct"] = out["benchmark_pct"]
    else:
        out["benchmark_pct"] = round(spy_pct, 4)
        out["excess_pct"] = round(mean_pct - spy_pct, 4)
        out["n_benchmark_marks"] = len(spy)
    return out


def _contract_index(out_dir: Path, *, days: int) -> dict[str, dict]:
    """decision_id -> the row's authority, weight, ticker and capital.

    A window of per-day files, the same shape `decision_contract` already
    scans. It is what makes a realised return ATTRIBUTABLE: the ledger knows
    what a decision earned and only the contract knows which authority took
    it.
    """
    folder = Path(out_dir)
    index: dict[str, dict] = {}
    if not folder.is_dir():
        return index
    floor = datetime.now(timezone.utc).date() - timedelta(days=int(days))
    for p in sorted(folder.glob("*.json"), reverse=True):
        try:
            if date.fromisoformat(p.stem) < floor:
                continue
        except ValueError:
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in blob.get("rows") or []:
            budget = row.get("position_budget") or {}
            index[str(row.get("decision_id"))] = {
                "ticker": row.get("ticker"),
                "authority": row.get("authority"),
                "direction": row.get("direction"),
                "weight": budget.get("weight"),
                "capital_usd": budget.get("capital_usd"),
                "asof": row.get("asof"),
            }
    return index


def realised_pnl(*, ledger: list[dict], index: dict[str, dict],
                 authority: str) -> Any:
    """Weighted realised return for one authority, or the named absence.

    `weight x realised_return`, summed over `SCORED` ledger rows whose contract
    row carried this authority. Nothing is annualised, nothing is compounded
    and nothing is filled in: a decision with no `realised_return` on its
    SCORED row is COUNTED as unpriced rather than treated as a zero.
    """
    taken = 0
    unpriced = 0
    weighted = 0.0
    dollars = 0.0
    dollars_known = False
    names: list[dict] = []
    for r in ledger or []:
        if str(r.get("state")) != "SCORED":
            continue
        meta = index.get(str(r.get("decision_id")))
        if not meta or meta.get("authority") != authority:
            continue
        detail = r.get("detail") or {}
        ret = detail.get("realised_return")
        try:
            ret = float(ret)
            weight = float(meta.get("weight") or 0.0)
        except (TypeError, ValueError):
            unpriced += 1
            continue
        if not math.isfinite(ret):
            unpriced += 1
            continue
        taken += 1
        weighted += weight * ret
        cap = meta.get("capital_usd")
        if cap is not None:
            try:
                dollars += weight * ret * float(cap)
                dollars_known = True
            except (TypeError, ValueError):
                pass
        names.append({"ticker": meta.get("ticker"), "asof": meta.get("asof"),
                      "weight": weight, "realised_return": ret})
    if not taken:
        return _cd(
            f"no {authority} decision has been SCORED yet — the ledger holds "
            f"no `SCORED` row for one ({unpriced} scored row(s) carried no "
            f"usable realised return). A decision is scored when its own "
            f"expiry passes and the grader joins it to close-to-close "
            f"returns; until then a P&L number would be invented")
    out = {
        "n_scored": taken,
        "n_unpriced": unpriced,
        "weighted_return_pct": round(100.0 * weighted, 4),
        "basis": ("sum of weight x realised close-to-close return over SCORED "
                  "rows attributed to this authority by their contract row; "
                  "not annualised, not compounded"),
        "names": names[:int(config.SCOREBOARD_MAX_NAMES)],
    }
    out["dollars"] = (round(dollars, 2) if dollars_known else
                      _cd("no scored row carried the capital it was sized at"))
    return out


def _newest_by_stamp(folder: Path, pattern: str) -> tuple[dict | None, str]:
    """(blob, path) for the newest matching receipt, by ITS OWN name stamp."""
    base = Path(folder)
    if not base.is_dir():
        # the night folders are dated siblings; look one level up too
        parent = base.parent
        cands = sorted(parent.glob(f"*/{pattern}")) if parent.is_dir() else []
    else:
        cands = sorted(base.glob(pattern))
        parent = base.parent
        if not cands and parent.is_dir():
            cands = sorted(parent.glob(f"*/{pattern}"))
    if not cands:
        return None, ""
    newest = cands[-1]
    try:
        return json.loads(newest.read_text(encoding="utf-8")), str(newest)
    except (OSError, ValueError) as exc:
        logger.warning("scoreboard: %s unreadable: %s", newest, exc)
        return None, str(newest)


def forecasts(folder: Path | None = None) -> Any:
    blob, path = _newest_by_stamp(Path(folder or night_dir()), _GRADE_GLOB)
    if not blob:
        return _cd("no `grade_forecasts_*.json` receipt is on disk, so nothing "
                   "can be said about how many forecasts matured")
    totals = blob.get("totals") or {}
    return {
        "newly_resolved": blob.get("newly_resolved"),
        "graded_after_this_run": blob.get("graded_after_this_run"),
        "n_records": blob.get("n_records"),
        "not_yet_due": totals.get("not_yet_due"),
        "waiting_on_a_bar": totals.get("NO_BAR_FOR_RESOLUTION_DATE"),
        "receipt": path,
        "headline": blob.get("headline"),
    }


def calibration(folder: Path | None = None) -> Any:
    """Brier against this repo's own climatology — the per-mechanism BASE-RATE
    Brier — or the named absence. `decision_vs_reality` computes both."""
    blob, path = _newest_by_stamp(Path(folder or night_dir()), _DVR_GLOB)
    if not blob:
        return _cd("no `decision_vs_reality_*.json` receipt is on disk, so no "
                   "calibration has been computed")
    overall = blob.get("overall") or {}
    n = int(overall.get("n") or 0)
    if not n or overall.get("brier") is None:
        return _cd(
            f"the newest calibration receipt ({path}) resolved {n} forecast(s) "
            f"inside its {blob.get('window')} window, so its Brier is null. A "
            f"number here would be a Brier over an empty set")
    beaten = [row for row in (blob.get("by_mechanism") or [])
              if row.get("beats_base_rate") is True]
    return {
        "n_resolved": n,
        "brier": overall.get("brier"),
        "decomposition": overall.get("decomposition"),
        "mechanisms_beating_their_base_rate": [r.get("mechanism_id")
                                               for r in beaten],
        "n_mechanisms": len(blob.get("by_mechanism") or []),
        "receipt": path,
        "headline": blob.get("headline"),
    }


def _replay_rows(folder: Path, *, asof: date, window_days: int) -> list[dict]:
    """Every book replay receipt stamped inside the window, both shapes.

    Two generations of receipt live in that folder (`cells.primary_floor` and
    the older flat `result`); both carry the same two numbers, and a reader
    that knew only one would silently rank half the evidence.
    """
    base = Path(folder)
    if not base.is_dir():
        return []
    floor = asof - timedelta(days=int(window_days))
    rows: list[dict] = []
    for p in sorted(base.glob("*.json")):
        m = _STAMP.search(p.name)
        if not m:
            continue
        try:
            stamped = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if stamped < floor or stamped > asof:
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cell = ((blob.get("cells") or {}).get("primary_floor") or {})
        result = cell.get("result") or blob.get("result") or {}
        excess = result.get("mean_excess_net_monthly")
        t_stat = result.get("nw_lag2_t")
        if excess is None or t_stat is None:
            continue
        rows.append({
            "book": blob.get("book") or p.stem,
            "stamped": str(stamped),
            "smoke": bool(blob.get("smoke")),
            "signed": blob.get("signed"),
            "mean_excess_net_monthly": float(excess),
            "nw_lag2_t": float(t_stat),
            "n_blocks": result.get("n_blocks"),
            "floor_usd": result.get("floor_usd"),
            "verdict": blob.get("verdict") or _cd(
                "this receipt generation carries no verdict field"),
            "receipt": str(p),
        })
    return rows


def strongest_new_positive(folder: Path | None = None, *, asof: date,
                           window_days: int) -> Any:
    rows = [r for r in _replay_rows(Path(folder or replay_dir()), asof=asof,
                                    window_days=window_days)
            if not r["smoke"] and r["mean_excess_net_monthly"] > 0]
    if not rows:
        return _cd(
            f"no non-smoke book replay receipt stamped in the last "
            f"{window_days} day(s) carries a positive net excess over its "
            f"twin. Nothing new is positive, which is a reading and not a gap")
    return max(rows, key=lambda r: r["nw_lag2_t"])


def strongest_killed(folder: Path | None = None, *, asof: date,
                     window_days: int) -> Any:
    rows = [r for r in _replay_rows(Path(folder or replay_dir()), asof=asof,
                                    window_days=window_days)
            if not r["smoke"]
            and str(r["verdict"]).startswith(tuple(config.SCOREBOARD_KILL_VERDICTS))]
    if not rows:
        return _cd(
            f"no non-smoke book replay receipt stamped in the last "
            f"{window_days} day(s) carries a kill verdict "
            f"({', '.join(config.SCOREBOARD_KILL_VERDICTS)})")
    return min(rows, key=lambda r: r["mean_excess_net_monthly"])


def _previous_contract(out_dir: Path, *, asof: date) -> tuple[dict | None, str]:
    folder = Path(out_dir)
    if not folder.is_dir():
        return None, ""
    for p in sorted(folder.glob("*.json"), reverse=True):
        try:
            day = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if day >= asof:
            continue
        try:
            return json.loads(p.read_text(encoding="utf-8")), str(p)
        except (OSError, ValueError):
            continue
    return None, ""


def learning_changed_capital(today: dict | None, previous: dict | None,
                             previous_path: str = "") -> str:
    """ONE sentence: did anything learned move a dollar since the last contract?

    Derived by DIFFERENCING two contracts' capital resolutions and authority
    sets, because that is the only mechanical version of the question. It
    answers `no` loudly when the answer is no — the rule Murat made absolute
    (§15.1) is that a module is not finished until capital, a weight or a
    hypothesis moved, and a scoreboard that cannot say `no` cannot say `yes`.
    """
    if not today:
        return _cd("no decision contract exists for today, so nothing can be "
                   "differenced and the day changed no capital at all")
    now_res = today.get("capital_resolution") or {}
    if not now_res:
        return _cd(
            "today's contract predates the capital resolution (chunk 21) and "
            "carries none, so there is no split to difference. This is not "
            "'no capital moved' — it is 'the file cannot say'")
    if not previous:
        return (
            f"yes (first contract on file): the day resolved "
            f"{float(now_res.get('active_exploit_pct') or 0.0):.2%} to active "
            f"EXPLOIT and "
            f"{float(now_res.get('active_explore_pct') or 0.0):.2%} to active "
            f"EXPLORE, with no earlier contract to difference it against")
    old_res = previous.get("capital_resolution") or {}
    if not old_res:
        return (
            f"CANNOT DETERMINE whether capital moved: the previous contract "
            f"({previous_path}) predates the capital resolution and carries "
            f"none, so today's "
            f"{float(now_res.get('active_explore_pct') or 0.0):.2%} EXPLORE "
            f"and {float(now_res.get('active_exploit_pct') or 0.0):.2%} "
            f"EXPLOIT cannot be differenced against it")

    def _auth(blob: dict, name: str) -> set[str]:
        return {str(r.get("ticker")) for r in (blob.get("rows") or [])
                if r.get("authority") == name
                and float((r.get("position_budget") or {}).get("weight") or 0)
                > 0}

    moved = []
    for key, label in (("active_exploit_pct", "EXPLOIT"),
                       ("active_explore_pct", "EXPLORE"),
                       ("cash_pct", "cash"), ("benchmark_pct", "benchmark")):
        a = float(old_res.get(key) or 0.0)
        b = float(now_res.get(key) or 0.0)
        if abs(b - a) > 1e-9:
            moved.append(f"{label} {a:.2%} -> {b:.2%}")
    added = (_auth(today, "EXPLOIT") | _auth(today, "EXPLORE")) - (
        _auth(previous, "EXPLOIT") | _auth(previous, "EXPLORE"))
    dropped = (_auth(previous, "EXPLOIT") | _auth(previous, "EXPLORE")) - (
        _auth(today, "EXPLOIT") | _auth(today, "EXPLORE"))
    if not moved and not added and not dropped:
        return (f"no: the split is identical to {previous.get('date')} — same "
                f"names, same authorities, same shares of capital. Nothing "
                f"learned since then has moved a dollar")
    parts = [p for p in (", ".join(moved),
                         ("added " + ", ".join(sorted(added))) if added else "",
                         ("dropped " + ", ".join(sorted(dropped)))
                         if dropped else "") if p]
    return (f"yes: since {previous.get('date')}, " + "; ".join(parts))


# ===========================================================================
# THE ONE FUNCTION
# ===========================================================================


def compose(*, asof: date | str | None = None,
            out_dir: Path | None = None,
            ledger_path: Path | None = None,
            night_folder: Path | None = None,
            replay_folder: Path | None = None,
            window_days: int | None = None,
            navs: dict | None = None) -> dict:
    """The morning scoreboard, composed from receipts on disk. Writes nothing.

    Every parameter is a PATH the caller may redirect, so the fast suite
    composes a whole scoreboard in `tmp_path` and never touches
    `backend/data` — and so a reader can rebuild a past morning by pointing at
    the day's folders.
    """
    day = _as_date(asof)
    folder = Path(out_dir) if out_dir is not None else decisions_dir()
    window = int(window_days if window_days is not None
                 else config.SCOREBOARD_WINDOW_DAYS)

    today_blob = contract_blob(day, out_dir=folder)
    prev_blob, prev_path = _previous_contract(folder, asof=day)
    ledger = ledger_rows(ledger_path)
    index = _contract_index(folder, days=int(config.SCOREBOARD_JOIN_DAYS))
    states = ledger_summary(day, path=ledger_path)

    counts = (today_blob or {}).get("count_by_direction") or {}
    decisions = {
        "contract": (today_blob or {}).get("path") or _cd(
            "no decision contract was written for this day"),
        "count_by_direction": counts or _cd(
            "no contract, so no direction was decided"),
        "count_by_authority": ((today_blob or {}).get("authority") or {}).get(
            "count_by_authority_over_rows") or _cd(
            "the contract carries no authority census (the legacy heuristic "
            "sizing is on, or the file predates chunk 21)"),
        "ledger_states": states.get("count_by_state"),
        "n_decisions_in_ledger_today": states.get("n_decisions"),
    }

    board = {
        "receipt": "morning_scoreboard",
        "roadmap_item": "chunk 21",
        "licence": LICENCE,
        "llm_spend_usd": 0.0,
        "date": str(day),
        "written_utc": _now(),
        "nav_vs_spy": nav_vs_spy(navs),
        "exploit_pnl": realised_pnl(ledger=ledger, index=index,
                                    authority="EXPLOIT"),
        "explore_pnl": realised_pnl(ledger=ledger, index=index,
                                    authority="EXPLORE"),
        "decisions": decisions,
        "capital_resolution": ((today_blob or {}).get("capital_resolution")
                               or _cd("no contract, so no dollar resolved")),
        "forecasts": forecasts(night_folder),
        "calibration": calibration(night_folder),
        "strongest_new_positive": strongest_new_positive(
            replay_folder, asof=day, window_days=window),
        "strongest_killed": strongest_killed(
            replay_folder, asof=day, window_days=window),
        "learning_changed_capital": learning_changed_capital(
            today_blob, prev_blob, prev_path),
        "window_days": window,
        "read_me_first": (
            "Every number here was read off a receipt that already existed; "
            "this module computes nothing and writes nothing. A field that "
            "could not be derived says CANNOT DETERMINE and names the file it "
            "wanted — never a zero, because a zero in a P&L column reads as "
            "'we broke even' when it means 'nothing has been scored'."),
    }
    board["headline"] = _headline(board)
    return board


def _headline(board: dict) -> str:
    res = board.get("capital_resolution")
    if isinstance(res, dict):
        split = (f"{float(res.get('benchmark_pct') or 0):.1%} benchmark / "
                 f"{float(res.get('active_exploit_pct') or 0):.2%} exploit / "
                 f"{float(res.get('active_explore_pct') or 0):.2%} explore / "
                 f"{float(res.get('cash_pct') or 0):.1%} cash")
    else:
        split = str(res)
    counts = (board.get("decisions") or {}).get("count_by_direction")
    made = (f"{counts.get('BUY', 0)} BUY, {counts.get('WATCH', 0)} WATCH, "
            f"{counts.get('REFUSED', 0)} REFUSED"
            if isinstance(counts, dict) else str(counts))
    return (f"{board.get('date')}: {split}; decisions {made}; "
            f"learning changed capital — {board.get('learning_changed_capital')}")


def _one(value: Any, *, money: bool = False) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if money:
            d = value.get("dollars")
            return (f"{value.get('weighted_return_pct')}% weighted over "
                    f"{value.get('n_scored')} scored row(s)"
                    + (f" ({d})" if isinstance(d, str) else f" (${d:,.2f})"))
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:400]
    return str(value)


def render(board: dict) -> str:
    """The paragraph the desktop Ask and the daily pass print FIRST.

    Computed from the object, not generated: the two surfaces must not be able
    to disagree about what this morning said, and no model is in this path.
    """
    nav = board.get("nav_vs_spy")
    nav_line = (nav if isinstance(nav, str) else
                f"{nav.get('mean_since_inception_pct')}% across "
                f"{nav.get('n_books')} book(s) vs "
                f"{nav.get('benchmark_symbol')} {nav.get('benchmark_pct')}% "
                f"(excess {nav.get('excess_pct')})")
    fc = board.get("forecasts")
    cal = board.get("calibration")
    pos = board.get("strongest_new_positive")
    killed = board.get("strongest_killed")
    lines = [
        f"### the morning scoreboard — {board.get('date')}",
        f"- NAV vs {config.SCOREBOARD_BENCHMARK_SYMBOL}: {nav_line}",
        f"- EXPLOIT P&L: {_one(board.get('exploit_pnl'), money=True)}",
        f"- EXPLORE P&L: {_one(board.get('explore_pnl'), money=True)}",
        f"- every dollar today: {_capital_line(board)}",
        f"- decisions: {_decisions_line(board)}",
        f"- forecasts matured and graded: "
        f"{fc if isinstance(fc, str) else fc.get('headline')}",
        f"- calibration: "
        f"{cal if isinstance(cal, str) else _calibration_line(cal)}",
        f"- strongest new positive: "
        f"{pos if isinstance(pos, str) else _book_line(pos)}",
        f"- strongest killed: "
        f"{killed if isinstance(killed, str) else _book_line(killed)}",
        f"- learning changed capital: {board.get('learning_changed_capital')}",
    ]
    return "\n".join(lines)


def _capital_line(board: dict) -> str:
    res = board.get("capital_resolution")
    if isinstance(res, str):
        return res
    return str(res.get("nothing_happened_is_not_allowed"))


def _decisions_line(board: dict) -> str:
    d = board.get("decisions") or {}
    counts = d.get("count_by_direction")
    auth = d.get("count_by_authority")
    return (f"{counts if isinstance(counts, str) else json.dumps(counts, sort_keys=True)}"
            f"; authorities "
            f"{auth if isinstance(auth, str) else json.dumps(auth, sort_keys=True)}"
            f"; ledger {json.dumps(d.get('ledger_states') or {}, sort_keys=True)}")


def _calibration_line(cal: dict) -> str:
    return (f"Brier {cal.get('brier')} over {cal.get('n_resolved')} resolved; "
            f"{len(cal.get('mechanisms_beating_their_base_rate') or [])} of "
            f"{cal.get('n_mechanisms')} mechanisms beat their own base rate")


def _book_line(row: dict) -> str:
    return (f"{row.get('book')} {row.get('mean_excess_net_monthly'):+.6f}/month "
            f"at NW t {row.get('nw_lag2_t')} over {row.get('n_blocks')} blocks "
            f"(stamped {row.get('stamped')}) — {row.get('verdict')}")


__all__ = ["LICENCE", "calibration", "compose", "forecasts",
           "learning_changed_capital", "nav_vs_spy", "realised_pnl", "render",
           "strongest_killed", "strongest_new_positive"]
