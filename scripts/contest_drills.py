"""Contest FAILURE DRILLS: every way the day can go wrong, executed and recorded pass/fail.

    python -m scripts.contest_drills            # writes contest/rehearsal/drills/drills_<utc>.json + .md

Each drill runs the REAL code path (the desk, the order sheet, the grader, the calendar) on a
constructed input whose right answer is known, plus the machine checks that cannot be
constructed (the scheduled tasks' wake settings, the power plan). A drill that could not run is
reported as NOT_RUN, never as PASS. Dates are derived from today; nothing is sent anywhere.
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc     # noqa: E402
from scripts import contest_desk as desk       # noqa: E402
from scripts import contest_orders as co       # noqa: E402
from scripts import contest_rehearsal as reh   # noqa: E402

TODAY = date.today()


def _next_weekday(d: date, n: int = 1) -> date:
    x = d
    k = 0
    while k < n:
        x += timedelta(days=1)
        if x.weekday() < 5:
            k += 1
    return x


def _ranked(rows: list[dict]) -> pd.DataFrame:
    """A desk-shaped ranking: symbol, bbg_ticker, market, pre_date, react_date, timing, rank..."""
    r = pd.DataFrame(rows)
    r["bbg_ticker"] = r.get("bbg_ticker", r.symbol.map(cc.bloomberg_ticker))
    r["market"] = r.symbol.map(cc.market_of)
    r["rank"] = np.arange(1, len(r) + 1)
    for c, v in (("timing", "AMC"), ("date_status", "VENDOR_ANNOUNCED"), ("date_confirmed", False),
                 ("trail_abs", 0.08), ("membership", "UNCONFIRMED_MEMBERSHIP")):
        if c not in r.columns:
            r[c] = v
    return r


def _prices(px: dict) -> Callable:
    def price_of(sym: str):
        v = px.get(sym, 50.0)
        return float(v), 1.0, "USD"
    return price_of


def _us_day() -> date:
    """A future weekday that is a NYSE session (so a US buy opens inside its sheet window)."""
    d = _next_weekday(TODAY, 3)
    sess, _ = desk.future_sessions("AAPL", d, d + timedelta(days=10))
    return sess[0].date()


def _mk_world(day: date, n: int, timing: str = "AMC") -> pd.DataFrame:
    react = pd.Timestamp(desk.future_sessions("AAPL", day + timedelta(days=1), day + timedelta(days=10))[0][0])
    rows = [{"symbol": s, "pre_date": pd.Timestamp(day), "react_date": react, "timing": timing,
             "trail_abs": 0.12 - 0.01 * i} for i, s in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"][:n])]
    return _ranked(rows)


def _before_open(day: date, sym: str = "AAPL") -> pd.Timestamp:
    return co.session_open_utc(sym, day) - pd.Timedelta(hours=8)


# ───────────────────────────── the drills ─────────────────────────────

def d01_date_moved() -> dict:
    """Earnings date moved or wrong: (a) miss rates measured on disk; (b) a frozen sheet is never
    rewritten; (c) the sheet always carries reserves to take when EVTS shows a moved date."""
    ev = {}
    files = sorted(reh.MISS_DIR.glob("vendor_miss_*.json")) if reh.MISS_DIR.exists() else []
    if files:
        v = json.loads(files[-1].read_text(encoding="utf-8"))
        ev["receipt"] = files[-1].name
        ev["A_ibes_vs_sec"] = {k: v["sections"]["A_ibes_vs_sec8k"].get(k) for k in
                               ("n_matched", "share_same_date", "share_off_ge2bd", "share_reaction_session_differs")}
        ev["B_pattern_14d"] = {k: v["sections"]["B_pattern_estimator_14d_ahead"].get(k) for k in
                               ("n", "share_exact", "share_off_ge2bd")}
        if "D_forward_nasdaq_vs_yahoo_screener" in v["sections"]:
            ev["D_forward"] = v["sections"]["D_forward_nasdaq_vs_yahoo_screener"]
    with tempfile.TemporaryDirectory() as td:
        folder, log = Path(td) / "sheets", Path(td) / "freeze.jsonl"
        payload = {"day": "x", "freeze_utc": "t", "tickets": [], "control": {"sheet_code": "X", "n_lines": 0}}
        reh.freeze(TODAY, payload, "md", "txt", folder=folder, log=log)
        try:
            reh.freeze(TODAY, payload, "md2", "txt2", folder=folder, log=log)
            refused = False
        except reh.FrozenSheetExists:
            refused = True
    day = _us_day()
    world = _mk_world(day, 7)
    t, res, _ = reh.build_tickets(day, world, [], nav_usd=1e6, now_utc=_before_open(day), price_of=_prices({}))
    ok = refused and len(res) >= 2 and bool(files)
    return {"pass": ok, "evidence": {**ev, "second_freeze_refused": refused, "reserves_on_sheet": int(len(res))},
            "action": "Before each BUY, EVTS <GO>: if the date moved out of the hold, SKIP and take the next reserve. "
                      "A moved date AFTER entry: sell at the planned exit anyway (the rule never extends a hold)."}


def d02_time_unknown() -> dict:
    day = pd.Timestamp(_us_day())
    stamp = desk.calendar_stamp("AAPL", day, None)
    sess, _ = desk.future_sessions("AAPL", day - pd.Timedelta(days=7), day + pd.Timedelta(days=14))
    pre, react, timing = cc.event_sessions(stamp, "AAPL", sess)
    held = react - pre
    stamp_jp = pd.Timestamp(datetime(day.year, day.month, day.day, 0, 0), tz="UTC")   # Yahoo's placeholder
    _, _, tj = cc.event_sessions(stamp_jp, "7203.T", sess)
    ok = timing == "UNKNOWN" and held == 2 and sess[pre] < day < sess[react] and tj == "UNKNOWN"
    return {"pass": bool(ok), "evidence": {"timing": timing, "sessions_held": int(held),
                                           "buy": str(sess[pre].date()), "sell": str(sess[react].date()),
                                           "jp_00utc_stamp": tj},
            "action": "An unknown report time is held TWO sessions (buy the session before the date, sell the "
                      "session after it). Confirm the time on EVTS; if it is known, the one-session hold applies."}


def d03_fewer_than_five() -> dict:
    day = _us_day()
    t, _, notes = reh.build_tickets(day, _mk_world(day, 3), [], nav_usd=1e6, now_utc=_before_open(day),
                                    price_of=_prices({}))
    buys = [x for x in t if x.side == "BUY"]
    gross = sum(x.notional_usd for x in buys) / 1e6
    ok = len(buys) == 3 and gross <= 0.60 + 1e-9 and any("slots filled" in n for n in notes)
    return {"pass": ok, "evidence": {"buys": len(buys), "gross_at_limit": round(gross, 4), "notes": notes},
            "action": "Fewer than five names: buy what there is and leave the rest in cash (filling slots with "
                      "high-vol names measured -1.0 pp a season, t -1.2). Do NOT double a slot: the 20% cap binds."}


def d04_not_in_wls() -> dict:
    univ = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"], "bbg_ticker": ["AAA US Equity", "BBB US Equity",
                                                                        "CCC US Equity"]})
    with tempfile.TemporaryDirectory() as td:
        pd.DataFrame({"Ticker": ["AAA US Equity", "CCC US Equity"]}).to_csv(Path(td) / "wls.csv", index=False)
        marked = cc.apply_wls(univ, folder=Path(td))
    cands = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"], "trail_abs": [0.10, 0.20, 0.05], "n_prior": [8, 8, 8],
                          "dv63": [5e7] * 3, "price_usd": [20.0] * 3, "has_bars": [True] * 3,
                          "membership": marked.membership.tolist()})
    ok_r, refused = desk.rank_candidates(cands, k=2)
    top = ok_r[ok_r.weight > 0].symbol.tolist()
    ok = ("BBB" in refused.symbol.tolist() and top == ["AAA", "CCC"]
          and refused.set_index("symbol").at["BBB", "refusal"] == "REFUSED_NOT_IN_WLS")
    return {"pass": bool(ok), "evidence": {"membership": dict(zip(marked.symbol, marked.membership)), "top": top,
                                           "refused": refused[["symbol", "refusal"]].to_dict("records")},
            "action": "With the MEMB export in contest/wls/, a non-member is refused and the next name moves up. "
                      "Without it every name says UNCONFIRMED: check MEMB on the Terminal before each BUY."}


def d05_halt_gap() -> dict:
    day = pd.Timestamp(_next_weekday(TODAY - timedelta(days=20), 1))
    days = pd.bdate_range(day, periods=4)
    px = pd.DataFrame({"symbol": ["HALT"] * 4 + ["GAP"] * 4 + ["LATEX"] * 4 + [reh.BENCH] * 4,
                       "date": list(days) * 4,
                       "open": [np.nan, 10, 10, 10] + [100, 101, 102, 103] + [50, np.nan, 52, 53] + [100, 100.5, 101, 101.5],
                       "close": [10] * 4 + [100] * 4 + [50] * 4 + [100] * 4})
    pos = [{"pos_id": "h", "sheet": "s", "symbol": "HALT", "bbg": "HALT US Equity", "market": "US", "qty": 100,
            "entry_session": str(days[0].date()), "sell": {"session_date": str(days[1].date())}, "currency": "USD",
            "limit_local": 11.0},
           {"pos_id": "g", "sheet": "s", "symbol": "GAP", "bbg": "GAP US Equity", "market": "US", "qty": 100,
            "entry_session": str(days[0].date()), "sell": {"session_date": str(days[1].date())}, "currency": "USD",
            "limit_local": 95.0},
           {"pos_id": "x", "sheet": "s", "symbol": "LATEX", "bbg": "LATEX US Equity", "market": "US", "qty": 100,
            "entry_session": str(days[0].date()), "sell": {"session_date": str(days[1].date())}, "currency": "USD",
            "limit_local": 55.0}]
    rows = {r["pos_id"]: r for r in reh.grade_positions(pos, px, pd.DataFrame(), px[px.symbol == reh.BENCH],
                                                         today=TODAY)}
    g = co.split_check(100.0, 140.0)
    ok = (rows["h"]["state"] == "NO_FILL_HALTED" and rows["g"]["state"] == "NO_FILL_ABOVE_LIMIT"
          and rows["x"]["state"] == "CLOSED" and rows["x"]["exit_session"] == str(days[2].date())
          and g["verdict"] == "GAP")
    return {"pass": bool(ok), "evidence": {"halted_at_entry": rows["h"]["state"], "gap_above_limit": rows["g"]["state"],
                                           "halted_at_exit_exits_next_open": rows["x"].get("exit_session"),
                                           "gap_40pct_check": g},
            "action": "Halted at the buy: no fill, cash. Halted at the sell: sell at the next open. A gap beyond "
                      "the limit: the BUY does not fill; never chase it with a market order."}


def d06_price_source_down() -> dict:
    def boom(*a, **k):
        raise ConnectionError("simulated outage")
    day = pd.Timestamp(_next_weekday(TODAY - timedelta(days=20), 1))
    pos = [{"pos_id": "p", "sheet": "s", "symbol": "ZZZNOTREAL", "bbg": "ZZZNOTREAL US Equity", "market": "US",
            "qty": 10, "entry_session": str(day.date()), "sell": None, "currency": "USD"}]
    px, src = reh.fetch_opens(["ZZZNOTREAL", reh.BENCH], day.date(), TODAY, downloader=boom)
    rows = reh.grade_positions(pos, px[px.symbol == "ZZZNOTREAL"], pd.DataFrame(), px[px.symbol == reh.BENCH],
                               today=TODAY)
    # the desk's refresh failure path: refresh_bars_for raising is caught by live_sheet (string receipt)
    rec: dict = {}
    try:
        orig, orig_dir = cc._yf_download, cc.BARS_DIR
        cc._yf_download = boom
        with tempfile.TemporaryDirectory() as td:
            cc.BARS_DIR = Path(td)                  # never touch the real bar files from a drill
            try:
                r = cc.pull_bars(["ZZZNOTREAL"], "US", start=str(TODAY - timedelta(days=10)), sleep=0.0)
                rec["pull_bars"] = {k: r.get(k) for k in ("n_failed", "failed", "rows")}
            finally:
                cc._yf_download, cc.BARS_DIR = orig, orig_dir
    except Exception as exc:                                    # noqa: BLE001
        rec["pull_bars_raised"] = f"{type(exc).__name__}"
    ages = ["US: last bar 2020-01-01 (9000 days) STALE"]
    ok = src in ("disk_fallback", "NONE") and rows[0]["state"] in ("PENDING_PRICE", "NO_FILL_HALTED") \
        and rows[0]["state"] == "PENDING_PRICE"
    return {"pass": bool(ok), "evidence": {"source_after_outage": src, "grade_state": rows[0]["state"],
                                           "pull_bars": rec, "stale_banner_rule": "any market > 4 days -> STALE banner"},
            "action": "Price source down: the sheet is still written from the last bars and carries a PRICE SOURCE "
                      "STALE banner; check every reference price on the Terminal. Grading waits (PENDING), never guesses."}


def d07_pc_asleep() -> dict:
    tasks = {n: reh.task_settings(n) for n in (reh.TASK_NAME, reh.DESK_TASK)}
    wake_timers = reh.wake_timers_enabled()
    # logic: a late freeze voids the lines whose session already opened; a missed sell is OVERDUE
    day = _us_day()
    world = _mk_world(day, 3)
    late = co.session_open_utc("AAPL", day) + pd.Timedelta(hours=1)
    t, _, _ = reh.build_tickets(day, world, [], nav_usd=1e6, now_utc=late, price_of=_prices({}))
    held = [{"pos_id": "old", "symbol": "OLD", "bbg": "OLD US Equity", "market": "US", "qty": 10, "currency": "USD",
             "planned_exit_session": str((pd.Timestamp(day) - pd.Timedelta(days=1)).date()),
             "planned_exit_open_utc": str(co.session_open_utc("OLD", pd.Timestamp(day)) - pd.Timedelta(days=1))}]
    t2, _, _ = reh.build_tickets(day, world.iloc[0:0], held, nav_usd=1e6, now_utc=late, price_of=_prices({}))
    logic_ok = all(x.status == "VOID_LATE" for x in t if x.side == "BUY") and t2 and t2[0].status == "OVERDUE"
    ac_never = reh.ac_never_sleeps()
    machine_ok = all(isinstance(v, dict) and v.get("Wake") and v.get("Catchup") for v in tasks.values()) \
        and (wake_timers is True or ac_never is True)
    return {"pass": bool(logic_ok and machine_ok), "logic_pass": bool(logic_ok), "machine_pass": bool(machine_ok),
            "evidence": {"tasks": tasks, "power_plan_wake_timers_ac": wake_timers, "ac_sleep_never": ac_never,
                         "late_buys_void": [x.status for x in t if x.side == "BUY"],
                         "missed_sell": t2[0].status if t2 else None},
            "action": "Tasks wake the PC and run late when missed (StartWhenAvailable). A sheet frozen after a "
                      "session opened VOIDS that session's buys; a missed sell prints as OVERDUE for the next open. "
                      "Interactive-only tasks need the owner signed in: leave the PC signed in and plugged in."}


def d08_holiday() -> dict:
    y = TODAY.year if TODAY.month < 11 else TODAY.year + 1
    first = date(y, 10, 1)
    mondays = [first + timedelta(days=i) for i in range(31) if (first + timedelta(days=i)).weekday() == 0]
    sports_day = mondays[1]                                      # Japan: 2nd Monday of October
    sess_jp, src_jp = desk.future_sessions("7203.T", sports_day - timedelta(days=5), sports_day + timedelta(days=5))
    sess_cn, src_cn = desk.future_sessions("600519.SS", date(y, 10, 1), date(y, 10, 3))
    sess_us, _ = desk.future_sessions("AAPL", sports_day - timedelta(days=3), sports_day + timedelta(days=3))
    # a JP report the morning after Sports Day: the buy session must be the Friday before, not the holiday
    stamp = pd.Timestamp(datetime.combine(sports_day + timedelta(days=1), datetime.min.time())).tz_localize(
        "Asia/Tokyo").tz_convert("UTC") + pd.Timedelta(hours=7)   # 07:00 JST = BMO
    pre, react, tim = cc.event_sessions(stamp, "7203.T", sess_jp)
    ok = (pd.Timestamp(sports_day) not in sess_jp and pd.Timestamp(sports_day) in sess_us
          and len(sess_cn) == 0 and sess_jp[pre] < pd.Timestamp(sports_day) and "exchange_calendars" in src_jp)
    try:
        import exchange_calendars as xc                         # noqa: PLC0415
        early = {c: [str(d.date()) for d in xc.get_calendar(c).early_closes
                     if pd.Timestamp(date(y, 10, 1)) <= d <= pd.Timestamp(date(y, 11, 30))]
                 for c in ("XNYS", "XLON", "XSTO", "XHKG", "XTKS")}
    except Exception as exc:                                    # noqa: BLE001
        early = {"error": str(exc)}
    return {"pass": bool(ok), "evidence": {"jp_sports_day": str(sports_day), "jp_source": src_jp,
                                           "jp_buy_session_for_next_day_print": str(sess_jp[pre].date()),
                                           "cn_sessions_oct1_3": len(sess_cn), "us_open_that_day": True,
                                           "early_closes_oct_nov": early},
            "finding": "Before tonight the desk assigned future sessions with pd.bdate_range (weekdays): it would "
                       "have bought Japanese names on Sports Day (contest day 1) and Chinese names in Golden Week. "
                       "Fixed: desk.future_sessions uses exchange_calendars.",
            "action": "Holidays come from exchange_calendars (verify on the Terminal's CDR <GO>). No US holiday or "
                      "half day falls inside Oct 12 - Nov 13; the US half day is Nov 27, after the contest."}


def d09_split() -> dict:
    s = co.split_check(200.0, 100.5)
    c = co.split_check(10.0, 99.0)
    ok = s["verdict"] == "SPLIT_SUSPECT" and abs(s["split_ratio"] - 0.5) < 1e-9 and c["verdict"] == "SPLIT_SUSPECT"
    return {"pass": bool(ok), "evidence": {"2_for_1": s, "1_for_10_consolidation": c},
            "action": "If the Terminal price is beyond 30% of the sheet's reference, look at CACS <GO>. A split: "
                      "shares = sheet shares / ratio, same dollars. No split: SKIP (gap)."}


def d10_share_classes() -> dict:
    r = pd.DataFrame({"symbol": ["GOOGL", "GOOG", "FOXA", "FOX", "AAA"],
                      "name": ["Alphabet Inc. Class A", "Alphabet Inc. Class C", "Fox Corporation Class A",
                               "Fox Corporation Class B", "Aaa Holdings"]})
    kept, dup = co.dedupe_issuers(r)
    u = cc.latest_universe()
    n_multi = None
    if u is not None:
        keys = [co.issuer_key(s, n) for s, n in zip(u.symbol, u.name)]
        vc = pd.Series(keys).value_counts()
        n_multi = int((vc > 1).sum())
        examples = vc[vc > 1].head(8).index.tolist()
    ok = kept.symbol.tolist() == ["GOOGL", "FOXA", "AAA"] and len(dup) == 2
    return {"pass": bool(ok), "evidence": {"kept": kept.symbol.tolist(), "refused": dup[["symbol", "refusal"]].to_dict("records"),
                                           "universe_issuers_with_2plus_listings": n_multi,
                                           "examples": examples if u is not None else None},
            "finding": "The desk ranked every listing separately: two classes of one issuer report on the same day "
                       "and would have taken two slots (40% on one print). The order sheet keeps the better-ranked one.",
            "action": "One line per issuer; the refused class is printed with REFUSED_SAME_ISSUER_AS."}


def d11_defect_flag() -> dict:
    defects = co.latest_defects()
    sym, when = None, None
    for s, rows in defects.items():
        if s.startswith("_"):
            continue
        for kind, w in rows:
            if w and pd.Timestamp(w) >= pd.Timestamp(TODAY) - pd.Timedelta(days=700):
                sym, when = s, w
                break
        if sym:
            break
    flag = co.defect_flag(sym, TODAY, defects) if sym else None
    ranked = pd.DataFrame({"symbol": [sym or "XX", "CLEAN1"], "name": ["x", "y"]})
    kept, refused = reh.filter_ranked(ranked, TODAY, defects)
    stitched = sorted(cc.stitched_cut_symbols())[:5]
    ok = bool(sym) and flag is not None and kept.symbol.tolist() == ["CLEAN1"]
    return {"pass": ok, "evidence": {"defect_file": defects.get("_file"), "flagged_example": sym, "defect_date": when,
                                     "refusal": flag, "stitched_cut_loaded_this_process": stitched},
            "action": "A name with a bar defect inside its trailing window is refused (its past-move average is not "
                      "trusted); a reused ticker's old history is cut before any feature (contest_calendar.cut_stitched)."}


def d12_cap_drift() -> dict:
    p = pd.DataFrame({"symbol": list("ABCDE"), "qty": [2000] * 5, "price_usd": [150.0, 100, 100, 100, 100]})
    nav = float((p.qty * p.price_usd).sum())
    dc = co.drift_check(p, nav)
    a = dc.set_index("symbol").loc["A"]
    # the budget-at-limit guard: a gap to the limit cannot breach the cap
    sz = co.size_ticket(100.0, 1.0, 200_000.0, 1)
    worst = sz["qty"] * sz["limit_local"]
    # never more than K positions at any open: a two-session hold keeps its slot
    day = _us_day()
    held = [{"pos_id": f"h{i}", "symbol": f"H{i}", "bbg": f"H{i} US Equity", "market": "US", "qty": 10, "currency": "USD",
             "planned_exit_session": str((pd.Timestamp(day) + pd.Timedelta(days=7)).date()),
             "planned_exit_open_utc": str(co.session_open_utc("AAPL", pd.Timestamp(day)) + pd.Timedelta(days=7))}
            for i in range(3)]
    t, res, _ = reh.build_tickets(day, _mk_world(day, 5), held, nav_usd=1e6, now_utc=_before_open(day),
                                  price_of=_prices({}))
    buys = [x for x in t if x.side == "BUY"]
    ok = bool(a.over_nav_cap) and a.trim_shares_if_at_all_times > 0 and worst <= 200_000 + 1e-6 and len(buys) == 2
    return {"pass": ok, "evidence": {"A_pct_nav_after_+50pct": round(float(a.pct_nav), 4),
                                     "A_trim_shares_if_cap_at_all_times": int(a.trim_shares_if_at_all_times),
                                     "notional_at_limit": worst, "buys_with_3_slots_held": len(buys)},
            "finding": "The desk bought five new names every day even while two-session holds were still open "
                       "(gross could exceed 100%, i.e. leverage the T&C forbid). The order sheet counts held slots.",
            "action": "OWNER MUST CONFIRM whether the 20% cap binds at entry or at all times. Until then: size so the "
                      "notional AT THE LIMIT is under min(20% NAV, $200k); if a position drifts above 20% and the "
                      "rule is 'at all times', sell the printed trim shares at the next open."}


def d13_manual_entry() -> dict:
    day = _us_day()
    t, _, _ = reh.build_tickets(day, _mk_world(day, 3), [], nav_usd=1e6, now_utc=_before_open(day),
                                price_of=_prices({"AAA": 41.37, "BBB": 7.9, "CCC": 123.0}))
    good = "\n".join(f"{x.side} {co.norm_bbg(x.bbg)} {x.qty}" for x in t)
    a, b, c = t[0], t[1], t[2]
    cases = {
        "correct": good,
        "slipped_zero": good.replace(f"{a.side} {co.norm_bbg(a.bbg)} {a.qty}", f"{a.side} {co.norm_bbg(a.bbg)} {a.qty * 10}"),
        "transposed_digits": good.replace(f" {b.qty}", f" {str(b.qty)[::-1]}") if str(b.qty) != str(b.qty)[::-1] else None,
        "side_flipped": good.replace(f"BUY {co.norm_bbg(c.bbg)}", f"SELL {co.norm_bbg(c.bbg)}"),
        "ticker_typo": good.replace(co.norm_bbg(a.bbg), co.norm_bbg(a.bbg).replace("AAA", "AAB")),
        "no_exchange_code": good.replace(co.norm_bbg(b.bbg), co.norm_bbg(b.bbg).split(" ")[0]),
        "missing_line": "\n".join(good.splitlines()[:-1]),
    }
    got = {}
    for k, txt in cases.items():
        if txt is None:
            continue
        r = co.verify(t, txt)
        got[k] = {"ok": r["ok"], "kinds": sorted({p["kind"] for p in r["problems"]}),
                  "codes_match": r["sheet_code_entered"] == r["sheet_code_expected"]}
    ok = got["correct"]["ok"] and got["correct"]["codes_match"] and all(not v["ok"] and not v["codes_match"]
                                                                       for k, v in got.items() if k != "correct")
    return {"pass": bool(ok), "evidence": got,
            "action": "Type from the sheet, then paste the blotter into `contest_rehearsal verify`: it names every "
                      "missing ticket, wrong quantity (a slipped zero, swapped digits), flipped side and mistyped "
                      "ticker, and prints the SHEET CODE only when the entry is exact."}


DRILLS = [("01 earnings date moved or wrong", d01_date_moved), ("02 report time unknown", d02_time_unknown),
          ("03 fewer than five names", d03_fewer_than_five), ("04 name not in WLS", d04_not_in_wls),
          ("05 halted or gapping name", d05_halt_gap), ("06 price source down", d06_price_source_down),
          ("07 PC asleep at sheet time", d07_pc_asleep), ("08 holiday or half day", d08_holiday),
          ("09 split between sheet and fill", d09_split), ("10 two share classes", d10_share_classes),
          ("11 stitched or defect-flagged ticker", d11_defect_flag), ("12 20% cap breached by drift", d12_cap_drift),
          ("13 manual-entry mistake", d13_manual_entry)]


def run_all() -> dict:
    out = {"run_utc": cc.utc_stamp(), "today": str(TODAY), "drills": []}
    for name, fn in DRILLS:
        try:
            r = fn()
            r["verdict"] = "PASS" if r.get("pass") else "FAIL"
        except Exception as exc:                                # noqa: BLE001
            r = {"verdict": "NOT_RUN", "error": f"{type(exc).__name__}: {exc}",
                 "trace": traceback.format_exc()[-1500:]}
        r["drill"] = name
        out["drills"].append(r)
        print(f"{name}: {r['verdict']}", flush=True)
    return out


def to_md(res: dict) -> str:
    L = [f"# Contest failure drills ({res['run_utc']} UTC)", "",
         "| drill | verdict | finding / action |", "|---|---|---|"]
    for d in res["drills"]:
        txt = (d.get("finding", "") + " " + d.get("action", "")).strip() or d.get("error", "")
        L.append(f"| {d['drill']} | {d['verdict']} | {txt} |")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    res = run_all()
    reh.DRILL_DIR.mkdir(parents=True, exist_ok=True)
    p = reh.DRILL_DIR / f"drills_{res['run_utc']}.json"
    cc.write_json(res, p)
    (p.with_suffix(".md")).write_text(to_md(res), encoding="utf-8")
    print("receipt:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
