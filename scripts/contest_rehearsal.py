"""Contest DRESS REHEARSAL: the desk run every session before the contest, exactly as on the day.

    python -m scripts.contest_rehearsal daily                 # grade what is due, then freeze today's sheet
    python -m scripts.contest_rehearsal sheet --date 2026-10-01
    python -m scripts.contest_rehearsal grade
    python -m scripts.contest_rehearsal verify --date <d> --entered blotter.txt
    python -m scripts.contest_rehearsal drills                # the failure drills, pass/fail receipt
    python -m scripts.contest_rehearsal vendor-miss           # date / time miss rates from sources on disk
    python -m scripts.contest_rehearsal status
    python -m scripts.contest_rehearsal contract              # declare the shadow books' frozen rules (once)
    python -m scripts.contest_rehearsal dry --date <d>        # preview every book's sheet; freezes nothing
    python -m scripts.contest_rehearsal gate                  # the live desk's MEMB + REGISTERED gate

What a rehearsal day is (identical to a contest day except for the folder):
1. at ~14:30 Hong Kong time the scheduled task grades every position whose exit bar exists, then
   builds the desk's ranking for the sheet window [d 14:00 HKT, d+1 14:00 HKT) (Europe d, US d,
   Asia d+1) from a near-dated calendar in `rehearsal/calendar/` (the contest calendar in
   `contest/calendar/` is never touched);
2. the ranking becomes an ORDER SHEET (`contest_orders`): SELL tickets for positions whose exit
   session opens in the window, BUY tickets in opening order, shares from the $1M capital at
   the binding cap, a limit, a control block and a sheet code;
3. the sheet is FROZEN: `orders.json` is written once (a second write is refused) and its
   sha256 is appended to `freeze_log.jsonl`. A line whose session opened before the freeze is
   VOID_LATE and is never graded (no back-filled evidence);
4. grading buys at the OPEN of the buy session and sells at the OPEN of the exit session
   (the reaction session; an untimed print is held two sessions), in shares, in USD, against
   ACWI (the WLS proxy) over the same opens.

Three books, one schedule (2026-10-07): ROT5_TRAIL (the order sheet), and two SHADOW books with
frozen contracts in freeze_log.jsonl -- ROT5_DIR (the same universe and sizing, names with net-Sell
consensus or net analyst lowerings dropped) and MAXTAIL_BH (the runbook's fallback). All three are
frozen at the same `now` (a late freeze is VOID_LATE for all) and graded by the same grader; the
scoreboard prints them side by side. Every sheet prints its worst case in dollars and refuses a
ticket above the 20% cap. CONTEST mode refuses the live sheet without a WLS MEMB export and the
owner's hand-made contest/REGISTERED file.

PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. Places no order, sends
nothing, $0 LLM. Whatever it returns is never evidence of the project's skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc     # noqa: E402
from scripts import contest_desk as desk       # noqa: E402
from scripts import contest_orders as co       # noqa: E402
from scripts import contest_direction as cd    # noqa: E402

REH = cc.CONTEST / "rehearsal"
SHEET_DIR = REH / "sheets"
CAL_DIR = REH / "calendar"
DESK_HOLD = REH / "desk_holdings"
GRADE_DIR = REH / "grades"
DRILL_DIR = REH / "drills"
MISS_DIR = REH / "vendor_miss"
FREEZE_LOG = REH / "freeze_log.jsonl"
RUN_LOG = REH / "runs.jsonl"
STOP_FILES = (cc.CONTEST / "STOP", REH / "STOP")
LAST_SHEET_DAY = cc.CONTEST_START - timedelta(days=3)   # the rehearsal writes sheets through this day
CAL_BACK, CAL_FWD = 3, 12
WIND_DOWN_DAYS = 5          # SELL-only sheets after the last buying day, so every position is closed
K = desk.K_SLOTS
BENCH = "ACWI"
TASK_NAME = "AegisContestRehearsal"
MODE = "REHEARSAL"


def use_mode(mode: str) -> None:
    """REHEARSAL (contest/rehearsal/, sheets through CONTEST_START - 3 days) or CONTEST
    (contest/live/, sheets from CONTEST_START - 3 days through CONTEST_END). Same code path."""
    global REH, SHEET_DIR, CAL_DIR, DESK_HOLD, GRADE_DIR, DRILL_DIR, MISS_DIR, FREEZE_LOG, RUN_LOG,         STOP_FILES, LAST_SHEET_DAY, MODE
    mode = mode.upper()
    if mode not in ("REHEARSAL", "CONTEST"):
        raise ValueError(mode)
    MODE = mode
    REH = cc.CONTEST / ("rehearsal" if mode == "REHEARSAL" else "live")
    SHEET_DIR, CAL_DIR, DESK_HOLD = REH / "sheets", REH / "calendar", REH / "desk_holdings"
    GRADE_DIR, DRILL_DIR, MISS_DIR = REH / "grades", cc.CONTEST / "rehearsal" / "drills",         cc.CONTEST / "rehearsal" / "vendor_miss"
    FREEZE_LOG, RUN_LOG = REH / "freeze_log.jsonl", REH / "runs.jsonl"
    STOP_FILES = (cc.CONTEST / "STOP", REH / "STOP")
    # contest: the last buying sheet is the day before the end (its prints react on the last day)
    LAST_SHEET_DAY = cc.CONTEST_START - timedelta(days=3) if mode == "REHEARSAL" else cc.CONTEST_END - timedelta(days=1)
DESK_TASK = "AegisContestDesk"


class FrozenSheetExists(RuntimeError):
    """A frozen sheet is never rewritten."""


# ───────────────────────────── positions (derived from frozen sheets) ─────────────────────────────

def frozen_days(folder: Optional[Path] = None) -> list[str]:
    folder = folder or SHEET_DIR
    return sorted(p.name for p in folder.iterdir() if (p / "orders.json").exists()) if folder.exists() else []


def load_orders(day: str, folder: Optional[Path] = None) -> dict:
    folder = folder or SHEET_DIR
    return json.loads((folder / day / "orders.json").read_text(encoding="utf-8"))


def positions(folder: Optional[Path] = None, *, before: Optional[str] = None) -> list[dict]:
    """Every position opened by a LIVE BUY ticket on a frozen sheet, with its SELL if one exists."""
    pos: dict[str, dict] = {}
    for d in frozen_days(folder):
        if before is not None and d >= before:
            break
        o = load_orders(d, folder)
        for t in o.get("tickets", []):
            if t["status"] == "VOID_LATE":
                continue
            if t["side"] == "BUY":
                pid = f"{d}:{co.norm_bbg(t['bbg'])}"
                pos[pid] = {"pos_id": pid, "sheet": d, "symbol": t["symbol"], "bbg": t["bbg"], "market": t["market"],
                            "qty": int(t["qty"]), "entry_session": t["session_date"], "entry_open_utc": t["open_utc"],
                            "planned_exit_session": t["extra"].get("exit_session"),
                            "planned_exit_open_utc": t["extra"].get("exit_open_utc"),
                            "limit_local": t.get("limit_local"), "ref_local": t["extra"].get("ref_local"),
                            "currency": t["currency"], "notional_usd": float(t.get("notional_usd") or 0.0),
                            "trail_abs": t["extra"].get("trail_abs"), "sell": None}
            elif t["side"] == "SELL" and t["extra"].get("pos_id") in pos:
                pos[t["extra"]["pos_id"]]["sell"] = {"sheet": d, "session_date": t["session_date"],
                                                     "open_utc": t["open_utc"], "status": t["status"]}
    return list(pos.values())


def open_positions(folder: Optional[Path] = None, *, before: Optional[str] = None) -> list[dict]:
    return [p for p in positions(folder, before=before) if p["sell"] is None]


# ───────────────────────────── the ticket builder (pure) ─────────────────────────────

def next_session_open(symbol: str, after_utc: pd.Timestamp) -> tuple[str, pd.Timestamp]:
    """The first session of the listing whose open is after `after_utc` (exchange calendar)."""
    start = after_utc.tz_convert(cc.session_hours(symbol)[0]).normalize().tz_localize(None)
    sess, _ = desk.future_sessions(symbol, start - pd.Timedelta(days=1), start + pd.Timedelta(days=15))
    for s in sess:
        o = co.session_open_utc(symbol, s)
        if o > after_utc:
            return str(s.date()), o
    s = start + pd.Timedelta(days=1)
    return str(s.date()), co.session_open_utc(symbol, s)


def build_tickets(day: date, ranked: pd.DataFrame, held: list[dict], *, nav_usd: float,
                  now_utc: pd.Timestamp, price_of: Callable[[str], tuple[float, float, str]],
                  k: int = K) -> tuple[list[co.Ticket], pd.DataFrame, list[str]]:
    """SELLs for held positions exiting in this window (or overdue), then BUYs in opening order.

    `ranked`: the desk's eligible names in rank order (symbol, bbg_ticker, pre_date, react_date,
    timing, market, trail_abs, date_status...). `price_of(symbol)` -> (ref_local, fx_local_per_usd,
    currency). Never more than `k` positions are held at any open (a two-session hold keeps its
    slot). Returns (tickets, reserves, notes)."""
    w0, w1 = desk.sheet_window(day)
    w0u, w1u = w0.tz_convert("UTC"), w1.tz_convert("UTC")
    cap = co.cap_usd(nav_usd)
    tickets: list[co.Ticket] = []
    notes: list[str] = []
    n = 0
    # 1) SELL
    live_held = []
    for p in held:
        ex_open = pd.Timestamp(p["planned_exit_open_utc"]) if p.get("planned_exit_open_utc") else None
        if ex_open is None:
            live_held.append(p)
            continue
        if ex_open < w1u:
            if ex_open <= now_utc:                    # the planned exit has passed: overdue
                sd, so = next_session_open(p["symbol"], now_utc)
                status, note = "OVERDUE", f"planned exit {p['planned_exit_session']} was missed; sell at the next open"
            else:
                sd, so = p["planned_exit_session"], ex_open
                status, note = "LIVE", "report has happened by this open"
            n += 1
            tickets.append(co.Ticket(
                n=n, side="SELL", bbg=p["bbg"], symbol=p["symbol"], market=p["market"], qty=int(p["qty"]),
                order_type="MARKET AT OPEN", limit_local=None, currency=p.get("currency", "USD"),
                session_date=sd, open_utc=str(so), open_hkt=f"{so.tz_convert(cc.HKT):%a %d %b %H:%M}",
                open_ny=f"{so.tz_convert(co.NY):%a %H:%M}", notional_usd=0.0, status=status, note=note,
                extra={"pos_id": p["pos_id"]}))
            p = {**p, "_exit_at": so}
        live_held.append(p)
    # 2) BUY: walk the ranking; a name is bought when a slot is free at ITS open
    exits = [(pd.Timestamp(p["_exit_at"]) if p.get("_exit_at") is not None
              else pd.Timestamp(p["planned_exit_open_utc"]) if p.get("planned_exit_open_utc") else w1u + pd.Timedelta(days=30))
             for p in live_held]
    held_syms = {p["symbol"] for p in live_held}
    bought: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    reserves = []
    if ranked is None or ranked.empty:
        notes.append("No name reports in this window: every slot stays in cash (the rule holds cash; "
                     "filling slots measured -1.0 pp, t -1.2).")
        return tickets, pd.DataFrame(), notes
    for r in ranked.itertuples():
        sym = r.symbol
        if sym in held_syms:
            continue
        buy_day = pd.Timestamp(r.pre_date)
        b_open = co.session_open_utc(sym, buy_day)
        if not (w0u <= b_open < w1u):
            continue
        n_live = sum(1 for e in exits if e > b_open) + sum(1 for (bo, be) in bought if bo <= b_open < be)
        if n_live >= k or len(bought) >= k:
            reserves.append(r)
            continue
        react = pd.Timestamp(r.react_date) if pd.notna(r.react_date) else None
        if react is None:
            reserves.append(r)
            continue
        ex_open = co.session_open_utc(sym, react)
        try:
            ref_local, fx, ccy = price_of(sym)
            lot = co.lot_size(sym)
            sz = co.size_ticket(ref_local, fx, cap["binding"], lot)
        except co.OrderRefused as exc:
            notes.append(f"{sym}: not ticketed ({exc}); next in rank")
            reserves.append(r)
            continue
        status = "VOID_LATE" if b_open <= now_utc else "LIVE"
        n += 1
        conf = "CONFIRMED" if bool(getattr(r, "date_confirmed", False)) else f"NOT CONFIRMED ({getattr(r, 'date_status', '?')})"
        tickets.append(co.Ticket(
            n=n, side="BUY", bbg=r.bbg_ticker, symbol=sym, market=r.market, qty=sz["qty"], order_type="LIMIT",
            limit_local=sz["limit_local"], currency=ccy, session_date=str(buy_day.date()), open_utc=str(b_open),
            open_hkt=f"{b_open.tz_convert(cc.HKT):%a %d %b %H:%M}", open_ny=f"{b_open.tz_convert(co.NY):%a %H:%M}",
            notional_usd=sz["notional_usd_at_limit"], status=status,
            note=(f"report {_report_day(r)} {getattr(r, 'timing', '?')}, sell at the {react.date()} open; "
                  f"{conf}; lot {sz['lot_status']}"),
            report=f"{getattr(r, 'timing', '?')} {conf}",
            extra={"exit_session": str(react.date()), "exit_open_utc": str(ex_open), "ref_local": ref_local,
                   "fx_local_per_usd": fx, "rank": int(getattr(r, "rank", 0)),
                   "trail_abs": float(getattr(r, "trail_abs", float("nan"))),
                   "date_status": str(getattr(r, "date_status", "")), "timing": str(getattr(r, "timing", "")),
                   "membership": str(getattr(r, "membership", "")), "sizing": sz, "cap": cap}))
        bought.append((b_open, ex_open))
    live_buys = [t for t in tickets if t.side == "BUY"]
    if 0 < len(live_buys) < k:
        notes.append(f"{len(live_buys)} of {k} slots filled: {100 - 20 * len(live_buys)}% of the book stays in cash "
                     "by rule (fewer names report in this window).")
    for t in tickets:
        t.code = co.line_code(t.side, t.bbg, t.qty)
    res = pd.DataFrame([{"symbol": r.symbol, "bbg_ticker": r.bbg_ticker, "rank": getattr(r, "rank", None),
                         "pre_date": r.pre_date} for r in reserves[:8]])
    return tickets, res, notes


def _report_day(r: Any) -> str:
    """The report's local date from the desk's stamp (the calendar date), else 'n/a'."""
    ts = getattr(r, "ts_utc", None)
    if ts is None or pd.isna(ts):
        return "n/a"
    return str(pd.Timestamp(ts).tz_convert(cc.session_hours(r.symbol)[0]).date())


def filter_ranked(ranked: pd.DataFrame, asof: date, defects: Optional[dict] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Order-level refusals on top of the desk's: bar-defect flags, then one line per issuer."""
    if ranked is None or ranked.empty:
        return ranked, pd.DataFrame()
    defects = co.latest_defects() if defects is None else defects
    r = ranked.copy()
    flag = [co.defect_flag(s, asof, defects) for s in r.symbol]
    refused = r[[f is not None for f in flag]].assign(refusal=[f for f in flag if f is not None])
    r = r[[f is None for f in flag]]
    # a date projected from past same-quarter prints was exact on 27.7% of 19,210 past US prints
    # (vendor_miss section B, 14 days ahead): a slot on it is mostly a slot without an event
    if "date_status" in r.columns:
        est = r.date_status.astype(str).eq("ESTIMATED_PATTERN") & ~r.get("date_confirmed", False).astype(bool)
        refused = pd.concat([refused, r[est].assign(
            refusal="REFUSED_DATE_ESTIMATED_ONLY (pattern date exact on 28% of past prints; confirm on EVTS to use)")],
            ignore_index=True)
        r = r[~est]
    r, dup = co.dedupe_issuers(r)
    return r, pd.concat([refused, dup], ignore_index=True)


# ───────────────────────────── prices ─────────────────────────────

def local_close(symbol: str, before: date) -> Optional[tuple[float, str]]:
    """(last close in the listing's currency strictly before `before`, date)."""
    m = cc.market_of(symbol)
    paths = ([cc.bars_path("US"), cc.OPT / "prices_deep" / "bars.parquet"] if m == "US" else [cc.bars_path(m)])
    best = None
    for p in paths:
        if not p.exists():
            continue
        try:
            b = pd.read_parquet(p, columns=["symbol", "date", "close"], filters=[("symbol", "=", symbol)])
        except Exception:                                      # noqa: BLE001
            continue
        b = b[pd.to_datetime(b.date) < pd.Timestamp(before)].dropna(subset=["close"])
        if len(b):
            last = b.sort_values("date").iloc[-1]
            if best is None or pd.Timestamp(last.date) > pd.Timestamp(best[1]):
                best = (float(last.close), str(pd.Timestamp(last.date).date()))
    return best


def fx_now(currency: str) -> float:
    if currency in ("USD", "", None):
        return 1.0
    t = cc.CCY_FX.get(currency, "")
    p = cc.bars_path("FX")
    if t and p.exists():
        f = pd.read_parquet(p, columns=["symbol", "date", "close"], filters=[("symbol", "=", t)])
        if len(f):
            v = float(f.sort_values("date").close.iloc[-1])
            return v * (100.0 if currency == "GBp" else 1.0)
    raise co.OrderRefused(f"no FX rate for {currency}")


def make_price_of(day: date, universe: Optional[pd.DataFrame], panel_px: dict) -> Callable:
    ccy = dict(zip(universe.symbol, universe.currency)) if universe is not None else {}

    def price_of(sym: str) -> tuple[float, float, str]:
        c = ccy.get(sym) or cc.MARKETS[cc.market_of(sym)].currency
        lc = local_close(sym, day)
        if lc is not None:
            return lc[0], fx_now(c), c
        pu = panel_px.get(sym)
        if pu and np.isfinite(pu):
            f = fx_now(c)
            return pu * f, f, c
        raise co.OrderRefused("no reference price on disk")
    return price_of


# ───────────────────────────── freeze ─────────────────────────────

def nav_now(folder: Optional[Path] = None, *, override: bool = True) -> float:
    """NAV for sizing: the owner's Terminal NAV when written to <root>/nav_override.json
    ({"nav_usd": ..., "asof": ...}) and newer than the last grade; else the last grade; else $1M.
    `override=False` (the shadow books): their own last grade, never the Terminal's NAV."""
    folder = folder or GRADE_DIR
    files = sorted(folder.glob("grade_*.json")) if folder.exists() else []
    ov = REH / "nav_override.json"
    if override and ov.exists():
        o = json.loads(ov.read_text(encoding="utf-8"))
        if not files or ov.stat().st_mtime >= files[-1].stat().st_mtime:
            return float(o["nav_usd"])
    if not files:
        return co.NOTIONAL_USD
    g = json.loads(files[-1].read_text(encoding="utf-8"))
    return float(g.get("nav_usd_0bps", co.NOTIONAL_USD))


def freeze(day: date, payload: dict, md: str, short: str, extra_files: dict | None = None,
           folder: Optional[Path] = None, log: Optional[Path] = None) -> dict:
    folder, log = folder or SHEET_DIR, log or FREEZE_LOG
    out = folder / str(day)
    f = out / "orders.json"
    if f.exists():
        raise FrozenSheetExists(f"{f} is frozen (written {load_orders(str(day), folder).get('freeze_utc')})")
    out.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=1, default=str)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, f)
    (out / "order_sheet.md").write_text(md, encoding="utf-8")
    (out / "order_sheet.txt").write_text(short + "\n", encoding="utf-8")
    for name, text in (extra_files or {}).items():
        (out / name).write_text(text, encoding="utf-8")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    rec = {"day": str(day), **({"strategy": payload["strategy"]} if payload.get("strategy") else {}),
           "freeze_utc": payload["freeze_utc"], "sha256": sha,
           "sheet_code": payload["control"]["sheet_code"], "n_live": payload["control"]["n_lines"],
           "n_void_late": sum(1 for t in payload["tickets"] if t["status"] == "VOID_LATE")}
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


LICENCE_SHORT = "PRODUCT_EXPERIMENT"


def strat_dirs(name: str) -> tuple[Path, Path, Path]:
    """A shadow book's own (sheets, grades, desk_holdings) under <root>/strategies/<name>/."""
    r = REH / "strategies" / name
    return r / "sheets", r / "grades", r / "desk_holdings"


def live_book() -> str:
    """CONTEST mode: which declared book the live order sheet trades. The owner writes the name into
    contest/live/BOOK by hand (absent -> ROT5_TRAIL). Anything else is refused, not guessed."""
    f = cc.CONTEST / "live" / "BOOK"
    name = f.read_text(encoding="utf-8").strip().upper() if f.exists() else "ROT5_TRAIL"
    if name not in ("ROT5_TRAIL", "ROT5_DIR"):
        raise desk.SheetRefused(f"contest/live/BOOK names {name!r}; the live sheet supports ROT5_TRAIL or ROT5_DIR "
                                "(MAXTAIL_BH is bought once by hand from its rehearsal sheet)")
    return name


def _sig63_of(panel: Any, sym: str, day: date) -> float:
    if panel is None:
        return float("nan")
    j = panel.col.get(sym)
    i = panel.idx(pd.Timestamp(day) - pd.Timedelta(days=1))
    if j is None or i < 0:
        return float("nan")
    return float(panel.sig63[i, j])


def book_after(tickets: list, held: list[dict], panel: Any, day: date) -> tuple[list[dict], float]:
    """The book once this sheet's tickets fill: held names not sold here + new BUYs. Returns
    (rows for the worst case, notional of the held names kept)."""
    sold = {t.extra.get("pos_id") for t in tickets if t.side == "SELL"}
    book, held_n = [], 0.0
    for p in held:
        if p["pos_id"] in sold:
            continue
        n = float(p.get("notional_usd") or 0.0)
        held_n += n
        book.append({"symbol": p["symbol"], "notional_usd": n, "sig63": _sig63_of(panel, p["symbol"], day),
                     "trail_abs": p.get("trail_abs")})
    for t in tickets:
        if t.side == "BUY" and t.status != "VOID_LATE":
            book.append({"symbol": t.symbol, "notional_usd": float(t.notional_usd),
                         "sig63": _sig63_of(panel, t.symbol, day), "trail_abs": t.extra.get("trail_abs")})
    return book, held_n


def _emit(day: date, payload: dict, md: str, short: str, *, name: str, folder: Path,
          extra_files: Optional[dict] = None, dry: bool = False) -> dict:
    """Freeze (write once + freeze_log) or, with `dry`, write a preview under <root>/dry/<day>/<name>/
    that nothing reads as a position and no log records."""
    if not dry:
        return freeze(day, payload, md, short, extra_files=extra_files, folder=folder)
    out = REH / "dry" / str(day) / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "orders_DRY.json").write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    (out / "order_sheet_DRY.md").write_text(md, encoding="utf-8")
    (out / "order_sheet_DRY.txt").write_text(short + "\n", encoding="utf-8")
    for fn, text in (extra_files or {}).items():
        (out / fn).write_text(text, encoding="utf-8")
    try:
        where = str(out.relative_to(REPO))
    except ValueError:
        where = str(out)
    return {"day": str(day), "strategy": name, "DRY": where,
            "n_live": payload["control"]["n_lines"], "sheet_code": payload["control"]["sheet_code"]}


def _priced_sheet(day: date, ranked: pd.DataFrame, held: list[dict], *, nav: float, now: pd.Timestamp,
                  universe: Optional[pd.DataFrame], panel: Any, label: str) -> dict:
    """Tickets + the cap refusal + the worst case, shared by every book."""
    panel_px = dict(zip(ranked.symbol, ranked.price_usd)) if len(ranked) and "price_usd" in ranked else {}
    tickets, reserves, notes = build_tickets(day, ranked, held, nav_usd=nav, now_utc=now,
                                             price_of=make_price_of(day, universe, panel_px))
    cap = co.cap_usd(nav)
    book, held_n = book_after(tickets, held, panel, day)
    cd.assert_cap(tickets, nav_usd=nav, cap_binding=cap["binding"], held_notional_usd=held_n,
                  notional_usd=co.NOTIONAL_USD, cap=co.CAP)
    wc = cd.worst_case(nav_usd=nav, cap_binding=cap["binding"], book=book, k=K)
    return {"tickets": tickets, "reserves": reserves, "notes": notes, "cap": cap, "worst_case": wc,
            "worst_lines": cd.worst_case_lines(wc, label)}


def sheet(day: date, *, refresh: bool = True, now: Optional[pd.Timestamp] = None, buys: bool = True,
          dry: bool = False) -> dict:
    """Build, render and FREEZE the sheet for `day`. `buys=False`: SELL tickets only (the
    rehearsal's wind-down after its last buying day). `dry=True`: write previews under
    <root>/dry/ and freeze nothing. In REHEARSAL mode the shadow books (ROT5_DIR, MAXTAIL_BH)
    are built from the same inputs at the same `now`, after ROT5_TRAIL is frozen."""
    if MODE == "CONTEST" and not dry:
        ok, reasons = cd.live_gate(cc.CONTEST)
        if not ok:
            p = cd.gate_receipt(reasons, day, contest_dir=cc.CONTEST)
            raise cd.LiveGateRefused(f"live order sheet refused (receipt {p.name}): " + "; ".join(reasons))
    if not dry and (SHEET_DIR / str(day) / "orders.json").exists():
        raise FrozenSheetExists(f"sheet {day} is already frozen")
    receipt: dict = {"day": str(day), "started_utc": cc.utc_stamp(), "mode": MODE}
    if buys:
        L = desk.live_sheet(day, refresh=refresh, cal_dir=CAL_DIR,
                            cal_window=(day - timedelta(days=CAL_BACK), day + timedelta(days=CAL_FWD)),
                            holdings_dir=DESK_HOLD, receipt=receipt)
        sh = L["sheet"]
    else:
        sh = desk.Sheet(day, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(columns=["symbol"]),
                        ["SELL-only wind-down sheet: no new positions."])
        L = {"sheet": sh, "cal_file": None, "header": "SELL-only wind-down sheet", "bars_age": []}
    now = now if now is not None else co.now_utc()
    ranked = sh.buys if len(sh.buys) else pd.DataFrame()
    if len(ranked) and MODE == "CONTEST":
        # no buy session that opens before the contest starts (09:00 New York on the first day: the
        # Asian sessions of that date open the evening before in New York)
        start = cd.contest_start_utc()
        ranked = ranked[[co.session_open_utc(s, p) >= start for s, p in zip(ranked.symbol, ranked.pre_date)]]
    ranked, refused2 = filter_ranked(ranked, day)
    ranked_trail = ranked
    book_name, dmeta = "ROT5_TRAIL", None
    if MODE == "CONTEST":
        book_name = live_book()
        if book_name == "ROT5_DIR" and ranked is not None and len(ranked):
            ranked, dropped, dmeta = cd.direction_rank(ranked, day, now_utc=now)
            refused2 = pd.concat([refused2, dropped], ignore_index=True)
    universe = cc.latest_universe()
    held = open_positions(before=str(day))
    nav = nav_now()
    P = _priced_sheet(day, ranked if ranked is not None else pd.DataFrame(), held, nav=nav, now=now,
                      universe=universe, panel=L.get("panel"), label=book_name)
    tickets, reserves, notes, cap = P["tickets"], P["reserves"], P["notes"], P["cap"]
    stale = [a for a in L.get("bars_age", []) if "STALE" in a]
    header = [(f"REHEARSAL (paper; nothing is entered anywhere). " if MODE == "REHEARSAL" else
               "CONTEST: the owner enters these tickets in TMSG by hand; nothing is sent from here. ")
              + f"Book **{book_name}**. Desk sheet window "
              f"{desk.sheet_window(day)[0]:%a %d %b %H:%M} to {desk.sheet_window(day)[1]:%a %d %b %H:%M} HKT.",
              f"Calendar: {L['cal_file']} (near-dated, {REH.name} folder). Membership: "
              f"{'WLS export' if cc.load_wls_export() is not None else 'PROXY, UNCONFIRMED (no WLS export yet)'}.",
              f"Licence: {desk.LICENCE} Zero direction skill is assumed."]
    header += P["worst_lines"]
    if dmeta:
        header.append(f"Direction filter ROT5_DIR (contract {str(dmeta.get('contract_sha256', ''))[:16]}): source "
                      f"{dmeta.get('last_pulled_utc')} ({dmeta.get('source_age_days')} days old); "
                      f"{dmeta.get('n_dropped')} dropped, {dmeta.get('n_unrated')} unrated.")
    if stale:
        header.append(f"**PRICE SOURCE STALE**: {'; '.join(stale)}. Check every price on the Terminal before "
                      "entering (a move beyond 30% of the sheet's reference: see the split/gap rule).")
    if isinstance(receipt.get("calendar"), str) and "FAILED" in receipt["calendar"]:
        header.append(f"**CALENDAR REFRESH FAILED**: {receipt['calendar']}")
    if isinstance(receipt.get("bars"), str) and "FAILED" in receipt["bars"]:
        header.append(f"**BAR REFRESH FAILED**: {receipt['bars']}")
    for nt in notes:
        header.append(f"Note: {nt}")
    if len(reserves):
        header.append("Reserves (take the next when a name is not in WLS, its date moved, or it is not tradable): "
                      + ", ".join(f"{r.bbg_ticker}" for r in reserves.itertuples()))
    freeze_utc = now.strftime("%Y-%m-%dT%H:%M:%S")
    md, short = co.render(tickets, day=str(day), nav_usd=nav, cap=cap, freeze_utc=freeze_utc, header=header)
    desk_md, _ = desk.render_sheet(sh, header_extra=L["header"])
    refused_all = pd.concat([sh.refused, refused2], ignore_index=True) if len(sh.refused) or len(refused2) else pd.DataFrame()
    payload = {"day": str(day), "mode": MODE, "strategy": book_name, "freeze_utc": freeze_utc,
               "licence": desk.LICENCE,
               "window_hkt": [str(x) for x in desk.sheet_window(day)], "nav_usd": nav, "cap": cap,
               "tickets": co.to_json(tickets), "control": co.control_block(tickets),
               "reserves": reserves.astype(str).to_dict("records") if len(reserves) else [],
               "refused": refused_all[["symbol", "refusal"]].astype(str).to_dict("records") if len(refused_all) else [],
               "n_ranked": int(len(ranked)) if ranked is not None else 0, "calendar_file": L["cal_file"],
               "bars_age": L.get("bars_age"),
               "refresh": {k: v for k, v in receipt.items() if k in ("universe", "calendar", "bars", "implied")},
               "notes": notes, "worst_case": P["worst_case"], "direction": dmeta}
    rec = _emit(day, payload, md, short, name=book_name, folder=SHEET_DIR,
                extra_files={"desk_sheet.md": desk_md}, dry=dry)
    if not dry:
        DESK_HOLD.mkdir(parents=True, exist_ok=True)
        cc.write_json({"day": str(day), "buys": [{"symbol": t.symbol, "bbg_ticker": t.bbg,
                                                  "react_date": t.extra.get("exit_session")}
                                                 for t in tickets if t.side == "BUY" and t.status != "VOID_LATE"]},
                      DESK_HOLD / f"{day}_holdings.json")
    print(short)
    if MODE == "REHEARSAL":
        rec["alternates"] = alt_sheets(day, L=L, ranked=ranked_trail, now=now, buys=buys, universe=universe, dry=dry)
    return rec


def alt_sheets(day: date, *, L: dict, ranked: pd.DataFrame, now: pd.Timestamp, buys: bool,
               universe: Optional[pd.DataFrame], dry: bool = False) -> dict:
    """The shadow books, each in its own try: one book's failure is that book's REFUSED line."""
    out: dict = {}
    for name in cd.STRATEGIES:
        try:
            out[name] = alt_sheet(name, day, L=L, ranked=ranked, now=now, buys=buys, universe=universe, dry=dry)
        except FrozenSheetExists as exc:
            out[name] = f"ALREADY_FROZEN: {exc}"
        except Exception as exc:                               # noqa: BLE001
            out[name] = f"REFUSED {type(exc).__name__}: {exc}"
            print(f"[{name}] {out[name]}")
    return out


def _maxtail_as_ranked(day: date, L: dict, now: pd.Timestamp, universe: Optional[pd.DataFrame]) -> pd.DataFrame:
    """MAXTAIL_BH's candidates shaped for build_tickets: buy session = the listing's first open in the
    window after `now`; exit = its first open after the last buying sheet's window."""
    panel, events = L.get("panel"), L.get("events")
    if panel is None or events is None:
        return pd.DataFrame()
    cand = cd.maxtail_ranked(day, panel, events, universe)
    if cand.empty:
        return cand
    defects = co.latest_defects()
    cand = cand[[co.defect_flag(s, day, defects) is None for s in cand.symbol]]
    cand, _ = co.dedupe_issuers(cand)
    w0, w1 = desk.sheet_window(day)
    w0u, w1u = w0.tz_convert("UTC"), w1.tz_convert("UTC")
    hold_after = desk.sheet_window(LAST_SHEET_DAY)[1].tz_convert("UTC")
    rows = []
    for r in cand.itertuples():
        try:
            sd, so = next_session_open(r.symbol, max(now, w0u))
            if not (w0u <= so < w1u):
                continue
            xd, _ = next_session_open(r.symbol, max(hold_after, so))
        except Exception:                                      # noqa: BLE001
            continue
        rows.append({"symbol": r.symbol, "bbg_ticker": r.bbg_ticker, "name": r.name, "market": r.market,
                     "pre_date": pd.Timestamp(sd), "react_date": pd.Timestamp(xd), "timing": "BUY_AND_HOLD",
                     "trail_abs": float("nan"), "sig63": float(r.sig63), "price_usd": float(r.price_usd),
                     "date_status": "BUY_AND_HOLD", "date_confirmed": True, "membership": r.membership})
    out = pd.DataFrame(rows)
    if len(out):
        out["rank"] = np.arange(1, len(out) + 1)
    return out


def alt_sheet(name: str, day: date, *, L: dict, ranked: pd.DataFrame, now: pd.Timestamp, buys: bool,
              universe: Optional[pd.DataFrame], dry: bool = False) -> dict:
    sd, gd, _ = strat_dirs(name)
    contract = cd.contract_sha(name)
    if not dry:
        cd.ensure_contract(name, FREEZE_LOG)
        if (sd / str(day) / "orders.json").exists():
            raise FrozenSheetExists(f"{name} sheet {day} is already frozen")
    held = open_positions(sd, before=str(day))
    nav = nav_now(gd, override=False)
    extra_notes, dmeta, dropped = [], None, pd.DataFrame()
    r = pd.DataFrame()
    if buys and name == "ROT5_DIR" and ranked is not None and len(ranked):
        r, dropped, dmeta = cd.direction_rank(ranked, day, now_utc=now)
    elif buys and name == "MAXTAIL_BH":
        if positions(sd, before=str(day)):
            extra_notes.append("MAXTAIL_BH bought once on its first sheet; this sheet carries no BUY.")
        else:
            r = _maxtail_as_ranked(day, L, now, universe)
    P = _priced_sheet(day, r if r is not None else pd.DataFrame(), held, nav=nav, now=now, universe=universe,
                      panel=L.get("panel"), label=name)
    tickets, reserves, notes, cap = P["tickets"], P["reserves"], P["notes"] + extra_notes, P["cap"]
    header = [f"SHADOW BOOK **{name}** (REHEARSAL; paper; never entered; graded beside ROT5_TRAIL by the same "
              f"grader). Contract {contract[:16]} ({LICENCE_SHORT}). Window "
              f"{desk.sheet_window(day)[0]:%a %d %b %H:%M} to {desk.sheet_window(day)[1]:%a %d %b %H:%M} HKT."]
    header += P["worst_lines"]
    if dmeta:
        header.append(f"Direction source: last pull {dmeta.get('last_pulled_utc')} ({dmeta.get('source_age_days')} "
                      f"days old); of {dmeta.get('n_in', 0)} ROT5_TRAIL names: {dmeta.get('n_admitted', 0)} admitted, "
                      f"{dmeta.get('n_unrated', 0)} unrated (admitted, no evidence), {dmeta.get('n_dropped', 0)} dropped.")
        for x in dropped.itertuples():
            header.append(f"Dropped: {getattr(x, 'bbg_ticker', x.symbol)} -- {x.refusal}")
    for nt in notes:
        header.append(f"Note: {nt}")
    if len(reserves):
        header.append("Reserves: " + ", ".join(f"{x.bbg_ticker}" for x in reserves.itertuples()))
    freeze_utc = now.strftime("%Y-%m-%dT%H:%M:%S")
    md, short = co.render(tickets, day=str(day), nav_usd=nav, cap=cap, freeze_utc=freeze_utc, header=header)
    md = md.replace(f"# ORDER SHEET {day}", f"# SHADOW SHEET {name} {day}", 1)
    short = f"[{name}] " + short
    cols = [c for c in ("symbol", "verdict", "cons", "n_firms", "net_raises90", "rev_mom", "trail_abs", "trail_rank",
                        "rank", "sig63") if len(r) and c in r.columns]
    payload = {"day": str(day), "mode": MODE, "strategy": name, "contract_sha256": contract, "freeze_utc": freeze_utc,
               "licence": desk.LICENCE, "window_hkt": [str(x) for x in desk.sheet_window(day)], "nav_usd": nav,
               "cap": cap, "tickets": co.to_json(tickets), "control": co.control_block(tickets),
               "reserves": reserves.astype(str).to_dict("records") if len(reserves) else [],
               "refused": dropped[["symbol", "refusal"]].astype(str).to_dict("records") if len(dropped) else [],
               "ranked": r[cols].astype(str).to_dict("records") if cols else [],
               "n_ranked": int(len(r)), "notes": notes, "worst_case": P["worst_case"], "direction": dmeta,
               "written_utc": cc.utc_stamp()}    # `freeze_utc` is the shared decision time; this is the write
    rec = _emit(day, payload, md, short, name=name, folder=sd, dry=dry)
    print(short)
    return rec


# ───────────────────────────── grading ─────────────────────────────

def fetch_opens(symbols: list[str], start: date, end: date, *,
                downloader: Optional[Callable] = None) -> tuple[pd.DataFrame, str]:
    """Daily open/close for `symbols` (local currency). Primary: yfinance; fallback: bars on disk."""
    dl = downloader or cc._yf_download
    try:
        got = dl(sorted(set(symbols)), start, end + timedelta(days=1))
        if got is not None and len(got):
            got = got.copy()
            d = pd.to_datetime(got["date"])
            if getattr(d.dt, "tz", None) is not None:
                d = d.dt.tz_localize(None)
            got["date"] = d.dt.normalize()
            got["symbol"] = got["symbol"].astype(str).str.upper()
            return got[["symbol", "date", "open", "close"]], "yfinance"
    except Exception as exc:                                   # noqa: BLE001
        print(f"  primary price source FAILED: {type(exc).__name__}: {exc}", flush=True)
    frames = []
    for m in {cc.market_of(s) for s in symbols} | {"FX"}:
        for p in ([cc.bars_path("US"), cc.OPT / "prices_deep" / "bars.parquet"] if m == "US" else [cc.bars_path(m)]):
            if p.exists():
                try:
                    b = pd.read_parquet(p, columns=["symbol", "date", "open", "close"],
                                        filters=[("symbol", "in", sorted(set(symbols)))])
                    frames.append(b)
                except Exception:                              # noqa: BLE001
                    pass
    if frames:
        b = pd.concat(frames, ignore_index=True)
        b["date"] = pd.to_datetime(b.date).dt.normalize()
        return b.drop_duplicates(["symbol", "date"]), "disk_fallback"
    return pd.DataFrame(columns=["symbol", "date", "open", "close"]), "NONE"


def _open_on(px: pd.DataFrame, sym: str, day: Any) -> Optional[float]:
    r = px[(px.symbol == sym) & (px.date == pd.Timestamp(day).normalize())]
    if len(r) and np.isfinite(r.open.iloc[0]) and r.open.iloc[0] > 0:
        return float(r.open.iloc[0])
    return None


def _first_open_from(px: pd.DataFrame, sym: str, day: Any) -> tuple[Optional[float], Optional[str]]:
    r = px[(px.symbol == sym) & (px.date >= pd.Timestamp(day).normalize())].sort_values("date")
    r = r[np.isfinite(r.open) & (r.open > 0)]
    if len(r):
        return float(r.open.iloc[0]), str(r.date.iloc[0].date())
    return None, None


def grade_positions(pos: list[dict], px: pd.DataFrame, fx: pd.DataFrame, bench: pd.DataFrame,
                    *, today: date) -> list[dict]:
    """One row per position: FILLED / NO_FILL_HALTED / PENDING / OPEN, with USD P&L when closed."""
    out = []
    for p in pos:
        row = {k: p[k] for k in ("pos_id", "sheet", "symbol", "bbg", "market", "qty", "entry_session")}
        e_day = pd.Timestamp(p["entry_session"])
        if e_day.date() >= today:
            row["state"] = "PENDING_ENTRY"
            out.append(row)
            continue
        e_px = _open_on(px, p["symbol"], e_day)
        if e_px is None:
            has_any = len(px[(px.symbol == p["symbol"]) & (px.date >= e_day)]) > 0
            row["state"] = "NO_FILL_HALTED" if has_any else "PENDING_PRICE"
            out.append(row)
            continue
        row["entry_px"] = e_px
        lim = p.get("limit_local")
        if lim is not None and e_px > float(lim) * (1 + 1e-9):
            row["state"] = "NO_FILL_ABOVE_LIMIT"
            row["note"] = f"open {e_px} above limit {lim}: the order does not fill; cash"
            out.append(row)
            continue
        sell = p.get("sell")
        if sell is None:
            row["state"] = "OPEN"
            out.append(row)
            continue
        s_day = pd.Timestamp(sell["session_date"])
        if s_day.date() >= today:
            row["state"] = "OPEN"
            out.append(row)
            continue
        x_px, x_day = _first_open_from(px, p["symbol"], s_day)
        if x_px is None:
            row["state"] = "PENDING_PRICE"
            out.append(row)
            continue
        row.update(exit_px=x_px, exit_session=x_day, exit_delayed=x_day != str(s_day.date()))
        ccy = p.get("currency", "USD")
        f_e = _fx_on(fx, ccy, e_day)
        f_x = _fx_on(fx, ccy, pd.Timestamp(x_day))
        row["ret_local"] = x_px / e_px - 1
        usd_in = p["qty"] * e_px / f_e
        usd_out = p["qty"] * x_px / f_x
        row["notional_usd"] = round(usd_in, 2)
        row["pnl_usd"] = round(usd_out - usd_in, 2)
        b0, _ = _first_open_from(bench, BENCH, e_day)
        b1, _ = _first_open_from(bench, BENCH, pd.Timestamp(x_day))
        row["bench_ret"] = (b1 / b0 - 1) if (b0 and b1) else None
        # split check on the fill vs the sheet's reference
        if p.get("ref_local"):
            row["fill_vs_ref"] = co.split_check(float(p["ref_local"]), e_px)["verdict"]
        row["state"] = "CLOSED"
        out.append(row)
    return out


def _fx_on(fx: pd.DataFrame, ccy: str, day: pd.Timestamp) -> float:
    if ccy in ("USD", "", None):
        return 1.0
    t = cc.CCY_FX.get(ccy, "")
    r = fx[(fx.symbol == t) & (fx.date <= day)].sort_values("date") if t and len(fx) else pd.DataFrame()
    if len(r):
        return float(r.close.iloc[-1]) * (100.0 if ccy == "GBp" else 1.0)
    return fx_now(ccy)


def book_summary(rows: list[dict], *, nav0: float = co.NOTIONAL_USD, bench: Optional[pd.DataFrame] = None) -> dict:
    closed = [r for r in rows if r.get("state") == "CLOSED"]
    pnl = sum(r["pnl_usd"] for r in closed)
    notional = sum(r["notional_usd"] for r in closed)
    out = {"n_positions": len(rows), "n_closed": len(closed),
           "states": pd.Series([r.get("state") for r in rows]).value_counts().to_dict() if rows else {},
           "pnl_usd_0bps": round(pnl, 2), "nav_usd_0bps": round(nav0 + pnl, 2),
           "book_ret_0bps": round(pnl / nav0, 6)}
    for bps in (10, 25):
        c = 2 * notional * bps / 1e4
        out[f"nav_usd_{bps}bps"] = round(nav0 + pnl - c, 2)
        out[f"book_ret_{bps}bps"] = round((pnl - c) / nav0, 6)
    if closed and bench is not None and len(bench):
        d0 = min(pd.Timestamp(r["entry_session"]) for r in closed)
        d1 = max(pd.Timestamp(r["exit_session"]) for r in closed)
        b0, _ = _first_open_from(bench, BENCH, d0)
        b1, _ = _first_open_from(bench, BENCH, d1)
        if b0 and b1:
            out["bench_ret"] = round(b1 / b0 - 1, 6)
            out["bench_window"] = [str(d0.date()), str(d1.date())]
            for bps in (0, 10, 25):
                out[f"relative_{bps}bps"] = round(out[f"book_ret_{bps}bps"] - out["bench_ret"], 6)
    return out


def _mark_open(rows: list[dict], pos: list[dict], px: pd.DataFrame, fx: pd.DataFrame) -> None:
    """Unrealised USD P&L of OPEN rows at the last close on file (a mark, not a fill)."""
    by = {p["pos_id"]: p for p in pos}
    for r in rows:
        if r.get("state") != "OPEN" or r.get("entry_px") is None:
            continue
        p = by.get(r["pos_id"], {})
        e_day = pd.Timestamp(r["entry_session"]).normalize()
        m = px[(px.symbol == r["symbol"]) & (px.date >= e_day)].dropna(subset=["close"]).sort_values("date")
        if not len(m):
            continue
        mk, md_ = float(m.close.iloc[-1]), m.date.iloc[-1]
        ccy = p.get("currency", "USD")
        r["mark_px"], r["mark_date"] = mk, str(pd.Timestamp(md_).date())
        r["unrealised_usd"] = round(r["qty"] * (mk / _fx_on(fx, ccy, pd.Timestamp(md_))
                                                - r["entry_px"] / _fx_on(fx, ccy, e_day)), 2)


def book_metrics(rows: list[dict], summ: dict, *, nav0: float = co.NOTIONAL_USD) -> dict:
    """The side-by-side line: hit rates, the TAIL check (share of P&L from the top name, and the
    relative result without it) and the unrealised mark of open positions."""
    closed = [r for r in rows if r.get("state") == "CLOSED"]
    out: dict = {"n_closed": len(closed),
                 "n_open": sum(1 for r in rows if r.get("state") == "OPEN"),
                 "unrealised_usd": round(sum(r.get("unrealised_usd") or 0.0 for r in rows if r.get("state") == "OPEN"), 2)}
    if not closed:
        return out
    pnl = np.array([r["pnl_usd"] for r in closed], dtype=float)
    out["hit_rate_abs"] = round(float((np.array([r["ret_local"] for r in closed]) > 0).mean()), 4)
    rel = [r["ret_local"] - r["bench_ret"] for r in closed if r.get("bench_ret") is not None]
    out["hit_rate_vs_bench"] = round(float((np.array(rel) > 0).mean()), 4) if rel else None
    net = float(pnl.sum())
    top = closed[int(np.argmax(np.abs(pnl)))]
    gains = float(pnl[pnl > 0].sum())
    out["top_name"] = f"{top['bbg']} ({top['sheet']})"
    out["top_pnl_usd"] = round(float(top["pnl_usd"]), 2)
    out["top_share_of_net_pnl"] = round(float(top["pnl_usd"]) / net, 4) if abs(net) > 1e-9 else None
    best = float(pnl.max())
    out["best_share_of_gross_gains"] = round(best / gains, 4) if gains > 0 else None
    if summ.get("bench_ret") is not None:
        out["relative_0bps_without_top"] = round((net - float(top["pnl_usd"])) / nav0 - summ["bench_ret"], 6)
    return out


def latest_worst_case(folder: Path) -> Optional[dict]:
    days = frozen_days(folder)
    for d in reversed(days):
        w = load_orders(d, folder).get("worst_case")
        if w:
            return {"sheet": d, **w}
    return None


def books() -> dict[str, tuple[Path, Path]]:
    """Every book the grader grades: ROT5_TRAIL, then each shadow book with a sheets folder."""
    b = {"ROT5_TRAIL": (SHEET_DIR, GRADE_DIR)}
    if MODE == "REHEARSAL":
        for n in cd.STRATEGIES:
            sd, gd, _ = strat_dirs(n)
            if sd.exists():
                b[n] = (sd, gd)
    return b


def grade(*, today: Optional[date] = None, downloader: Optional[Callable] = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    bk = books()
    pos_by = {n: positions(sd) for n, (sd, _) in bk.items()}
    allpos = [p for v in pos_by.values() for p in v]
    if not allpos:
        rec = {"graded_utc": cc.utc_stamp(), "n_positions": 0, "note": "no frozen positions yet"}
        print(json.dumps(rec))
        return rec
    syms = sorted({p["symbol"] for p in allpos} | {BENCH})
    start = min(pd.Timestamp(p["entry_session"]) for p in allpos).date() - timedelta(days=5)
    px, src = fetch_opens(syms, start, today, downloader=downloader)
    fxp = cc.bars_path("FX")
    fx = pd.read_parquet(fxp, columns=["symbol", "date", "close"]) if fxp.exists() else pd.DataFrame()
    if len(fx):
        fx["date"] = pd.to_datetime(fx.date).dt.normalize()
    bench = px[px.symbol == BENCH]
    stamp = cc.utc_stamp()
    recs: dict = {}
    for n, (sd, gd) in bk.items():
        rows = grade_positions(pos_by[n], px, fx, bench, today=today)
        _mark_open(rows, pos_by[n], px, fx)
        summ = book_summary(rows, bench=bench)
        recs[n] = {"graded_utc": stamp, "today_utc": str(today), "strategy": n, "price_source": src, **summ,
                   "metrics": book_metrics(rows, summ), "latest_worst_case": latest_worst_case(sd),
                   "rows": rows, "licence": desk.LICENCE, "benchmark": f"{BENCH} opens (WLS proxy)",
                   **({"contract_sha256": cd.contract_sha(n)} if n in cd.RULES else {})}
    main = recs["ROT5_TRAIL"]
    # the fair comparison: ROT5_TRAIL on the SAME sheets as the shadow books (they start later)
    same = {}
    for n in recs:
        if n == "ROT5_TRAIL":
            continue
        days = frozen_days(bk[n][0])
        if days:
            rr = [r for r in main["rows"] if r["sheet"] >= days[0]]
            s2 = book_summary(rr, bench=bench)
            same[n] = {"from_sheet": days[0], **{k: v for k, v in s2.items() if k != "states"},
                       "metrics": book_metrics(rr, s2)}
    main["alternates"] = {n: {k: v for k, v in r.items() if k != "rows"} for n, r in recs.items() if n != "ROT5_TRAIL"}
    main["trail_on_same_sheets"] = same
    for n, (sd, gd) in bk.items():
        gd.mkdir(parents=True, exist_ok=True)
        cc.write_json(recs[n], gd / f"grade_{stamp}.json")
    (REH / "SCOREBOARD.md").write_text(scoreboard_md(main, recs), encoding="utf-8")
    print(json.dumps({k: v for k, v in main.items() if k not in ("rows", "alternates", "trail_on_same_sheets")},
                     default=str))
    return main


def _side_line(label: str, s: dict) -> str:
    m = s.get("metrics", {}) or {}
    def f(v: Any, spec: str) -> str:
        return "n/a" if v is None else format(v, spec)
    w = s.get("latest_worst_case") or {}
    wtxt = ("n/a" if not w else
            f"{w.get('sheet')}: 5x${w.get('cap_binding_usd', 0):,.0f}; "
            + ", ".join(f"{k} stop ${-v:,.0f}" for k, v in (w.get("largest_at_stop_usd") or {}).items())
            + (f"; 2σ63 ${-w['largest_at_2sigma63_usd']:,.0f}" if w.get("largest_at_2sigma63_usd") is not None else ""))
    return (f"| {label} | {m.get('n_closed', s.get('n_closed', 0))} / {m.get('n_open', 0)} "
            f"| {f(s.get('pnl_usd_0bps'), '+,.0f')} | {f(m.get('unrealised_usd'), '+,.0f')} "
            f"| {f(s.get('relative_0bps'), '+.2%')} / {f(s.get('relative_10bps'), '+.2%')} / {f(s.get('relative_25bps'), '+.2%')} "
            f"| {f(m.get('hit_rate_vs_bench'), '.0%')} ({f(m.get('hit_rate_abs'), '.0%')} abs) "
            f"| {m.get('top_name', 'n/a')} {f(m.get('top_share_of_net_pnl'), '.0%')} of net; best {f(m.get('best_share_of_gross_gains'), '.0%')} of gains "
            f"| {f(m.get('relative_0bps_without_top'), '+.2%')} | {wtxt} |")


def scoreboard_md(rec: dict, recs: Optional[dict] = None) -> str:
    recs = recs or {"ROT5_TRAIL": rec}
    L = ["# Contest rehearsal scoreboard (derived view; the receipts are grades/grade_*.json and "
         "strategies/<book>/grades/grade_*.json)", "",
         f"Graded {rec['graded_utc']} UTC; price source: {rec.get('price_source')}; benchmark {BENCH} opens "
         "(WLS proxy). Every book is frozen at the same time by the same task and graded here by the same code.", "",
         "## Books side by side", "",
         "| book | closed / open | realised P&L $ (0 bps) | unrealised $ (mark) | relative 0 / 10 / 25 bps "
         "| hit rate vs bench | TAIL: top name share | relative without top name | worst case (latest sheet) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for n, r in recs.items():
        L.append(_side_line(n, r))
    for n, s in (rec.get("trail_on_same_sheets") or {}).items():
        L.append(_side_line(f"ROT5_TRAIL on {n}'s sheets (from {s['from_sheet']})", s))
    L += ["", "Read the same-sheets line, not the full ROT5_TRAIL line, when comparing: the shadow books start "
          "later. A handful of positions decides nothing; the TAIL column says how much one name carries.", ""]
    for n, r in recs.items():
        L += [f"## {n}", "",
              f"- positions: {r.get('n_positions')} ({r.get('states')})",
              f"- book P&L at 0 bps: ${r.get('pnl_usd_0bps', 0):,.0f}; NAV ${r.get('nav_usd_0bps', 0):,.0f}",
              f"- relative vs {BENCH}: 0 bps {r.get('relative_0bps', 'n/a')}, 10 bps {r.get('relative_10bps', 'n/a')}, "
              f"25 bps {r.get('relative_25bps', 'n/a')} over {r.get('bench_window', 'n/a')}", "",
              "| sheet | ticker | qty | entry | exit | state | ret (local) | P&L USD | bench | note |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        def fm(v: Any, spec: str) -> str:
            return "" if v is None else format(v, spec)
        for x in r.get("rows", []):
            pnl = x.get("pnl_usd")
            note = x.get("note", "")
            if pnl is None and x.get("unrealised_usd") is not None:
                note = (note + "; " if note else "") + f"mark {x['mark_date']} {x['unrealised_usd']:+,.0f}"
            L.append(f"| {x['sheet']} | {x['bbg']} | {x['qty']:,} | {x.get('entry_session')} {x.get('entry_px', '')} "
                     f"| {x.get('exit_session', '')} {x.get('exit_px', '')} | {x.get('state')} "
                     f"| {fm(x.get('ret_local'), '+.2%')} | {fm(pnl, '+,.0f')} "
                     f"| {fm(x.get('bench_ret'), '+.2%')} | {note} |")
        L.append("")
    return "\n".join(L) + "\n"


# ───────────────────────────── vendor-date miss rates ─────────────────────────────

def _bdays_between(a: pd.Series, b: pd.Series) -> np.ndarray:
    a = pd.to_datetime(a).dt.normalize().to_numpy(dtype="datetime64[D]")
    b = pd.to_datetime(b).dt.normalize().to_numpy(dtype="datetime64[D]")
    return np.busday_count(np.minimum(a, b), np.maximum(a, b))


def timing_class(ts_utc: pd.Series, symbol: str = "AAPL") -> pd.Series:
    """BMO / AMC / INTRA / UNKNOWN for US stamps (New York time)."""
    return pd.Series([cc.stamp_timing(t, symbol)[1] for t in ts_utc], index=ts_utc.index)


def vendor_miss(*, sample: int = 20000, seed: int = 20261012) -> dict:
    """Miss rates from sources ON DISK (no network):

    A. IBES actuals vs SEC 8-K 2.02 acceptance (US, past seasons): two after-the-fact sources.
       Date disagreement in business days, and BMO/AMC disagreement where both are timed.
    B. The desk's own forward estimator (ESTIMATED_PATTERN) replayed on past 8-K prints: the
       estimate made 14 days before each print vs the print.
    C. Nasdaq's day listings (fetched 2026-09-28) vs Yahoo's US stamps for the same days.
    D. Two FORWARD vendors for the same future days: Nasdaq day files vs Yahoo's screener date.
    """
    rng = np.random.default_rng(seed)
    out: dict = {"what": "vendor date/time miss rates from files on disk; no network", "sections": {}}
    sec = cc.us_8k_events()
    sec["day"], sec["timing"] = zip(*[cc.stamp_timing(t, "AAPL") for t in sec.ts_utc])
    from scripts import contest_book_compare as cbc            # noqa: PLC0415
    ib = cbc.ibes_stamps()
    ib["day"], ib["timing"] = zip(*[cc.stamp_timing(t, "AAPL") for t in ib.ts_utc])
    # A: match each IBES print to the nearest 8-K print of the same symbol within 10 calendar days
    s = sec[["symbol", "day", "timing"]].sort_values("day")
    i = ib[["symbol", "day", "timing"]].sort_values("day")
    s2 = s.rename(columns={"day": "day_sec_actual", "timing": "timing_sec2"})
    m = pd.merge_asof(i.rename(columns={"timing": "timing_ibes"}), s2, left_on="day", right_on="day_sec_actual",
                      by="symbol", direction="nearest", tolerance=pd.Timedelta(days=10))
    m = m.dropna(subset=["day_sec_actual"])
    m["bd"] = _bdays_between(m["day"], m["day_sec_actual"])
    # the reaction session is what the desk trades: AMC on D and BMO on D+1 react the same session
    def react(day, tim):
        d = pd.to_datetime(day).dt.normalize()
        nxt = d + pd.offsets.BDay(1)
        return np.where(np.asarray(tim) == "AMC", nxt, d)
    timed = m[(m.timing_ibes.isin(["AMC", "BMO"])) & (m.timing_sec2.isin(["AMC", "BMO"]))]
    rs_i = pd.to_datetime(react(timed["day"], timed.timing_ibes))
    rs_s = pd.to_datetime(react(timed["day_sec_actual"], timed.timing_sec2))
    by_year = {}
    m["year"] = pd.to_datetime(m["day"]).dt.year
    for y, g in m.groupby("year"):
        by_year[int(y)] = {"n": int(len(g)), "same_day": round(float((g.bd == 0).mean()), 4),
                           "off_ge_1bd": round(float((g.bd >= 1).mean()), 4)}
    out["sections"]["A_ibes_vs_sec8k"] = {
        "n_matched": int(len(m)), "share_same_date": round(float((m.bd == 0).mean()), 4),
        "share_off_1bd": round(float((m.bd == 1).mean()), 4), "share_off_ge2bd": round(float((m.bd >= 2).mean()), 4),
        "n_both_timed": int(len(timed)),
        "share_timing_class_differs": round(float((timed.timing_ibes.to_numpy() != timed.timing_sec2.to_numpy()).mean()), 4),
        "share_reaction_session_differs": round(float((rs_i.to_numpy() != rs_s.to_numpy()).mean()), 4),
        "ibes_unknown_time_share": round(float((ib.timing == "UNKNOWN").mean()), 4),
        "by_year": by_year,
        "reading": "disagreement between two AFTER-THE-FACT sources: a floor on date error, not the forward miss rate"}
    # B: the desk's forward estimator replayed
    ev = sec[pd.to_datetime(sec["day"]) >= pd.Timestamp("2022-01-01")]
    idx = rng.choice(len(ev), size=min(sample, len(ev)), replace=False)
    ev = ev.iloc[np.sort(idx)]
    hist = {k: g.ts_utc.sort_values() for k, g in sec.groupby("symbol")}
    rows = []
    for r in ev.itertuples():
        h = hist.get(r.symbol)
        asof = (pd.Timestamp(r.day) - pd.Timedelta(days=14)).date()
        hh = h[h.dt.tz_convert(None).dt.date <= asof] if h is not None else None
        if hh is None or len(hh) < 4:
            continue
        e = cc.estimate_from_history(hh, asof)
        if e is None:
            continue
        err = int(np.busday_count(min(e["date"], pd.Timestamp(r.day).date()), max(e["date"], pd.Timestamp(r.day).date())))
        rows.append({"err_bd": err, "conf": e["confidence"], "year": pd.Timestamp(r.day).year})
    b = pd.DataFrame(rows)
    out["sections"]["B_pattern_estimator_14d_ahead"] = {
        "n": int(len(b)), "share_exact": round(float((b.err_bd == 0).mean()), 4) if len(b) else None,
        "share_within_1bd": round(float((b.err_bd <= 1).mean()), 4) if len(b) else None,
        "share_off_ge2bd": round(float((b.err_bd >= 2).mean()), 4) if len(b) else None,
        "by_confidence": {c: {"n": int(len(g)), "exact": round(float((g.err_bd == 0).mean()), 4)}
                          for c, g in b.groupby("conf")} if len(b) else {},
        "by_year": {int(y): round(float((g.err_bd == 0).mean()), 4) for y, g in b.groupby("year")} if len(b) else {},
        "reading": "the desk's ESTIMATED_PATTERN rows (projected from past same-quarter prints) as a FORWARD estimate"}
    # C: Nasdaq (fetched 09-28) vs Yahoo US stamps, same days
    nd_dir = cc.CAL_DIR / "nasdaq_days"
    nd = pd.concat([pd.read_parquet(f) for f in sorted(nd_dir.glob("*.parquet"))], ignore_index=True) \
        if nd_dir.exists() else pd.DataFrame()
    if len(nd) and cc.HIST_US_PATH.exists():
        y = pd.read_parquet(cc.HIST_US_PATH)
        y["ts_utc"] = pd.to_datetime(y.ts_utc, utc=True)
        y["day"], y["timing"] = zip(*[cc.stamp_timing(t, "AAPL") for t in y.ts_utc])
        nd["date"] = pd.to_datetime(nd.date)
        j = pd.merge_asof(nd.sort_values("date"), y[["symbol", "day", "timing"]].sort_values("day"),
                          left_on="date", right_on="day", by="symbol", direction="nearest",
                          tolerance=pd.Timedelta(days=10), suffixes=("_nasdaq", "_yahoo"))
        jj = j.dropna(subset=["day"])
        tt = jj[jj.timing_nasdaq.isin(["AMC", "BMO"]) & jj.timing_yahoo.isin(["AMC", "BMO"])]
        out["sections"]["C_nasdaq_vs_yahoo_same_days"] = {
            "nasdaq_rows": int(len(nd)), "matched_to_yahoo": int(len(jj)),
            "share_same_date": round(float((jj.date == jj.day).mean()), 4) if len(jj) else None,
            "share_timing_differs": round(float((tt.timing_nasdaq != tt.timing_yahoo).mean()), 4) if len(tt) else None,
            "nasdaq_unknown_time_share": round(float((nd.timing == "UNKNOWN").mean()), 4),
            "fetched": "all Nasdaq day files were fetched 2026-09-28 (past days retro, 09-29..10-02 forward)"}
    # D: two forward vendors on the same future days
    u = cc.latest_universe()
    if u is not None and len(nd):
        fwd = nd[nd.date >= pd.Timestamp("2026-09-29")]
        us = u[(u.market == "US") & u.earn_ts_start.notna()].copy()
        us["yday"] = pd.to_datetime(us.earn_ts_start, unit="s", utc=True).dt.tz_convert(co.NY).dt.normalize().dt.tz_localize(None)
        jj = fwd.merge(us[["symbol", "yday", "earn_is_estimate"]], on="symbol", how="left")
        jj = jj.dropna(subset=["yday"])
        out["sections"]["D_forward_nasdaq_vs_yahoo_screener"] = {
            "nasdaq_forward_rows": int(len(fwd)), "with_yahoo_date": int(len(jj)),
            "share_same_date": round(float((jj.date == jj.yday).mean()), 4) if len(jj) else None,
            "share_same_date_when_yahoo_says_announced": round(float((jj[~jj.earn_is_estimate.astype(bool)].date
                                                                      == jj[~jj.earn_is_estimate.astype(bool)].yday).mean()), 4)
            if len(jj[~jj.earn_is_estimate.astype(bool)]) else None,
            "reading": "two forward vendors disagreeing on the same future print; the realised check is prospective "
                       "(graded by the rehearsal as the prints happen)"}
    return out


def cmd_vendor_miss() -> Path:
    res = vendor_miss()
    MISS_DIR.mkdir(parents=True, exist_ok=True)
    p = MISS_DIR / f"vendor_miss_{cc.utc_stamp()}.json"
    cc.write_json(res, p)
    print(json.dumps(res, indent=1, default=str)[:6000])
    return p


# ───────────────────────────── the scheduled task ─────────────────────────────

TASK_CMD = cc.CONTEST / "contest_rehearsal_task.cmd"


def task_cmd_text() -> str:
    return ("@echo off\r\n"
            "rem AegisContestRehearsal: grades the rehearsal, then freezes today's rehearsal sheet.\r\n"
            "rem Places no order, sends nothing. STOP: backend\\data\\optimus\\contest\\STOP or contest\\rehearsal\\STOP.\r\n"
            f"cd /d {REPO}\r\n"
            "if exist backend\\data\\optimus\\contest\\STOP exit /b 0\r\n"
            "if exist backend\\data\\optimus\\contest\\rehearsal\\STOP exit /b 0\r\n"
            "set AEGIS_PERSONAL_MODE=0\r\n"
            ".venv\\Scripts\\python.exe -u -m scripts.contest_rehearsal daily "
            ">> backend\\data\\optimus\\contest\\logs\\rehearsal_task.log 2>&1\r\n")


def task_settings(name: str) -> dict:
    """Read the scheduled task's wake / catch-up settings (PowerShell, read-only)."""
    ps = (f"$t = Get-ScheduledTask -TaskName '{name}' -ErrorAction Stop; "
          "$s = $t.Settings; $tr = $t.Triggers | Select-Object -First 1; "
          "[pscustomobject]@{Wake=$s.WakeToRun; Catchup=$s.StartWhenAvailable; "
          "Battery=$s.DisallowStartIfOnBatteries; StopOnBattery=$s.StopIfGoingOnBatteries; "
          "Start=$tr.StartBoundary; End=$tr.EndBoundary; Logon=$t.Principal.LogonType; State=\"$($t.State)\"} "
          "| ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {"error": r.stderr.strip()[:300]}
    except Exception as exc:                                   # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def ac_never_sleeps() -> Optional[bool]:
    """Power plan: 'Sleep after' on AC is Never (read-only powercfg query)."""
    try:
        r = subprocess.run(["powercfg", "/q", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"],
                           capture_output=True, text=True, timeout=30)
        for ln in r.stdout.splitlines():
            if "Current AC Power Setting Index" in ln:
                return int(ln.split(":")[-1].strip(), 16) == 0
    except Exception:                                          # noqa: BLE001
        return None
    return None


def wake_timers_enabled() -> Optional[bool]:
    """Power plan 'Allow wake timers' on AC (read-only powercfg query)."""
    try:
        r = subprocess.run(["powercfg", "/q", "SCHEME_CURRENT", "SUB_SLEEP", "BD3B718A-0680-4D9D-8AB2-E1D2B4AC806D"],
                           capture_output=True, text=True, timeout=30)
        for ln in r.stdout.splitlines():
            if "Current AC Power Setting Index" in ln:
                return int(ln.split(":")[-1].strip(), 16) != 0
    except Exception:                                          # noqa: BLE001
        return None
    return None


# ───────────────────────────── daily ─────────────────────────────

def daily(day: Optional[date] = None) -> int:
    day = day or date.today()
    run = {"started_utc": cc.utc_stamp(), "day": str(day)}
    if any(p.exists() for p in STOP_FILES):
        run["result"] = "STOP file present"
        _log_run(run)
        print(run["result"])
        return 0
    try:
        g = grade()
        run["grade"] = {k: g.get(k) for k in ("n_positions", "n_closed", "price_source", "relative_0bps")}
        run["grade"]["alternates"] = {n: {k: a.get(k) for k in ("n_positions", "n_closed", "relative_0bps")}
                                      for n, a in (g.get("alternates") or {}).items()}
    except Exception as exc:                                   # noqa: BLE001
        run["grade"] = f"FAILED {type(exc).__name__}: {exc}"
    first = cc.CONTEST_START - timedelta(days=1) if MODE == "CONTEST" else date.min
    wind_down = LAST_SHEET_DAY < day <= LAST_SHEET_DAY + timedelta(days=WIND_DOWN_DAYS)
    if first <= day <= LAST_SHEET_DAY or wind_down:
        try:
            rec = sheet(day, buys=not wind_down)
            run["sheet"] = rec
        except FrozenSheetExists as exc:
            run["sheet"] = f"ALREADY_FROZEN: {exc}"
        except cd.LiveGateRefused as exc:
            run["sheet"] = f"REFUSED_LIVE_GATE: {exc}"
        except Exception as exc:                               # noqa: BLE001
            run["sheet"] = f"FAILED {type(exc).__name__}: {exc}"
    else:
        run["sheet"] = f"no {MODE.lower()} sheet on {day} (sheets {first} .. {LAST_SHEET_DAY}, sells to +{WIND_DOWN_DAYS}d)"
    run["finished_utc"] = cc.utc_stamp()
    _log_run(run)
    print(json.dumps(run, default=str)[:2000])
    return 0


def _log_run(run: dict) -> None:
    REH.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run, default=str) + "\n")


def status() -> str:
    L = [f"frozen sheets: {frozen_days()}"]
    for p in positions():
        L.append(f"  {p['pos_id']}: qty {p['qty']} entry {p['entry_session']} exit plan {p['planned_exit_session']} "
                 f"sell {'-' if p['sell'] is None else p['sell']['session_date']}")
    files = sorted(GRADE_DIR.glob("grade_*.json")) if GRADE_DIR.exists() else []
    if files:
        g = json.loads(files[-1].read_text(encoding="utf-8"))
        L.append(f"last grade {files[-1].name}: {({k: g.get(k) for k in ('n_closed', 'nav_usd_0bps', 'relative_0bps')})}")
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["daily", "sheet", "grade", "verify", "drills", "vendor-miss", "status", "task-cmd",
                                    "nav", "contract", "dry", "gate"])
    ap.add_argument("--set", type=float, default=None, help="nav: the Terminal's NAV in USD, used to size the next sheet")
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-refresh", action="store_true")
    ap.add_argument("--entered", default=None, help="file with the blotter as typed into TMSG")
    ap.add_argument("--mode", default="rehearsal", choices=["rehearsal", "contest"])
    a = ap.parse_args(argv)
    use_mode(a.mode)
    day = date.fromisoformat(a.date) if a.date and a.date != "today" else date.today()
    if a.cmd == "daily":
        return daily(day)
    if a.cmd == "sheet":
        sheet(day, refresh=not a.no_refresh)
        return 0
    if a.cmd == "contract":
        for n in cd.STRATEGIES:
            r = cd.ensure_contract(n, FREEZE_LOG)
            print(f"{n}: contract {r['contract_sha256']} declared {r['declared_utc']} in {FREEZE_LOG.name}")
        return 0
    if a.cmd == "dry":
        rec = sheet(day, refresh=not a.no_refresh, dry=True)
        print(json.dumps(rec, default=str, indent=1))
        return 0
    if a.cmd == "gate":
        ok, reasons = cd.live_gate(cc.CONTEST)
        print("LIVE GATE OPEN" if ok else "LIVE GATE REFUSES: " + "; ".join(reasons))
        return 0 if ok else 2
    if a.cmd == "grade":
        grade()
        return 0
    if a.cmd == "verify":
        o = load_orders(str(day))
        res = co.verify(co.from_json(o["tickets"]), Path(a.entered).read_text(encoding="utf-8"))
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 2
    if a.cmd == "drills":
        from scripts import contest_drills                     # noqa: PLC0415
        return contest_drills.main([])
    if a.cmd == "vendor-miss":
        cmd_vendor_miss()
        return 0
    if a.cmd == "status":
        print(status())
        return 0
    if a.cmd == "nav":
        if a.set is None or not (1e5 <= a.set <= 1e8):
            print("usage: nav --set <USD between 100,000 and 100,000,000> [--mode contest]")
            return 2
        cc.write_json({"nav_usd": a.set, "asof_utc": cc.utc_stamp(), "source": "owner, from the Terminal"},
                      REH / "nav_override.json")
        print(f"next {MODE.lower()} sheet sizes on NAV ${a.set:,.0f}")
        return 0
    if a.cmd == "task-cmd":
        TASK_CMD.write_text(task_cmd_text(), encoding="utf-8", newline="")
        print(TASK_CMD)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
