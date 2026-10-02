"""Contest dress rehearsal: order sheet, freeze, grading, drills' mechanics, strategy lab.

Synthetic inputs, dates derived from today, no network."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts import contest_calendar as cc
from scripts import contest_desk as desk
from scripts import contest_orders as co
from scripts import contest_rehearsal as reh

TODAY = date.today()


def _us_session_ahead(n: int = 3) -> date:
    d = TODAY + timedelta(days=n)
    sess, _ = desk.future_sessions("AAPL", d, d + timedelta(days=14))
    return sess[0].date()


def _world(day: date, syms: list[str], timing: str = "AMC") -> pd.DataFrame:
    sess, _ = desk.future_sessions("AAPL", day + timedelta(days=1), day + timedelta(days=14))
    react = pd.Timestamp(sess[0])
    r = pd.DataFrame({"symbol": syms, "pre_date": pd.Timestamp(day), "react_date": react, "timing": timing,
                      "trail_abs": np.linspace(0.12, 0.05, len(syms))})
    r["bbg_ticker"] = r.symbol.map(cc.bloomberg_ticker)
    r["market"] = "US"
    r["rank"] = np.arange(1, len(r) + 1)
    r["date_status"] = "VENDOR_ANNOUNCED"
    r["date_confirmed"] = False
    return r


def _price(px: dict | None = None):
    px = px or {}
    return lambda s: (float(px.get(s, 50.0)), 1.0, "USD")


def _before(day: date) -> pd.Timestamp:
    return co.session_open_utc("AAPL", day) - pd.Timedelta(hours=6)


# ───────────────────────────── the order sheet ─────────────────────────────

def test_tickets_size_under_the_cap_at_the_limit():
    day = _us_session_ahead()
    t, res, _ = reh.build_tickets(day, _world(day, list("ABCDEFG")), [], nav_usd=1_000_000,
                                  now_utc=_before(day), price_of=_price({"A": 33.33, "B": 7.1}))
    buys = [x for x in t if x.side == "BUY"]
    assert len(buys) == 5 and len(res) == 2
    for b in buys:
        assert b.qty * b.limit_local <= 200_000 + 1e-6
        assert b.status == "LIVE" and b.bbg.endswith(" US Equity")
        assert b.code == co.line_code(b.side, b.bbg, b.qty)


def test_cap_uses_the_smaller_reading():
    up = co.cap_usd(1_500_000)
    down = co.cap_usd(800_000)
    assert up["binding"] == pytest.approx(200_000) and up["binding_reading"] == "20% of notional"
    assert down["binding"] == pytest.approx(160_000) and down["binding_reading"] == "20% of current NAV"


def test_board_lot_rounds_down():
    sz = co.size_ticket(3721.0, 157.0, 200_000.0, 100)
    assert sz["qty"] % 100 == 0 and sz["notional_usd_at_limit"] <= 200_000


def test_late_freeze_voids_opened_sessions_and_missed_sell_is_overdue():
    day = _us_session_ahead()
    late = co.session_open_utc("AAPL", day) + pd.Timedelta(minutes=10)
    t, _, _ = reh.build_tickets(day, _world(day, list("AB")), [], nav_usd=1e6, now_utc=late, price_of=_price())
    assert {x.status for x in t if x.side == "BUY"} == {"VOID_LATE"}
    held = [{"pos_id": "p", "symbol": "OLD", "bbg": "OLD US Equity", "market": "US", "qty": 7, "currency": "USD",
             "planned_exit_session": str(day - timedelta(days=1)),
             "planned_exit_open_utc": str(late - pd.Timedelta(days=1))}]
    t2, _, _ = reh.build_tickets(day, _world(day, [])[0:0], held, nav_usd=1e6, now_utc=late, price_of=_price())
    assert len(t2) == 1 and t2[0].side == "SELL" and t2[0].status == "OVERDUE" and t2[0].qty == 7


def test_held_two_session_positions_keep_their_slots():
    day = _us_session_ahead()
    far = co.session_open_utc("AAPL", day) + pd.Timedelta(days=6)
    held = [{"pos_id": f"h{i}", "symbol": f"H{i}", "bbg": f"H{i} US Equity", "market": "US", "qty": 1,
             "currency": "USD", "planned_exit_session": str((far.date())), "planned_exit_open_utc": str(far)}
            for i in range(4)]
    t, _, _ = reh.build_tickets(day, _world(day, list("ABCDE")), held, nav_usd=1e6, now_utc=_before(day),
                                price_of=_price())
    assert sum(1 for x in t if x.side == "BUY") == 1


def test_fewer_names_leave_cash_and_say_so():
    day = _us_session_ahead()
    t, _, notes = reh.build_tickets(day, _world(day, list("AB")), [], nav_usd=1e6, now_utc=_before(day),
                                    price_of=_price())
    assert sum(1 for x in t if x.side == "BUY") == 2
    assert any("60% of the book stays in cash" in n for n in notes)


def test_render_has_control_block_and_code():
    day = _us_session_ahead()
    t, _, _ = reh.build_tickets(day, _world(day, list("ABC")), [], nav_usd=1e6, now_utc=_before(day),
                                price_of=_price())
    md, short = co.render(t, day=str(day), nav_usd=1e6, cap=co.cap_usd(1e6), freeze_utc="x")
    code = co.sheet_code(t)
    assert code in md and code in short and "CONTROL" in md


# ───────────────────────────── manual entry ─────────────────────────────

def _tickets():
    day = _us_session_ahead()
    t, _, _ = reh.build_tickets(day, _world(day, ["AAA", "BBB", "CCC"]), [], nav_usd=1e6, now_utc=_before(day),
                                price_of=_price({"AAA": 41.37, "BBB": 7.9, "CCC": 123.0}))
    return t


def test_verify_accepts_the_exact_entry_and_matches_the_code():
    t = _tickets()
    txt = "\n".join(f"{x.side} {co.norm_bbg(x.bbg)} {x.qty:,}" for x in reversed(t))
    r = co.verify(t, txt)
    assert r["ok"] and r["sheet_code_entered"] == r["sheet_code_expected"]


@pytest.mark.parametrize("mutate,kind", [
    (lambda t, s: s.replace(f"AAA US {t[0].qty}", f"AAA US {t[0].qty * 10}"), "QTY_SLIPPED_ZERO"),
    (lambda t, s: s.replace("BUY CCC", "SELL CCC"), "SIDE_FLIPPED"),
    (lambda t, s: s.replace("AAA US", "AAB US"), "TICKER_TYPO"),
    (lambda t, s: s.replace("BBB US", "BBB"), "EXCHANGE_CODE_MISSING"),
    (lambda t, s: "\n".join(s.splitlines()[:-1]), "MISSING_TICKET"),
])
def test_verify_names_each_mistake(mutate, kind):
    t = _tickets()
    good = "\n".join(f"{x.side} {co.norm_bbg(x.bbg)} {x.qty}" for x in t)
    r = co.verify(t, mutate(t, good))
    assert not r["ok"] and kind in {p["kind"] for p in r["problems"]}
    assert r["sheet_code_entered"] != r["sheet_code_expected"]


def test_parse_blotter_numeric_asian_ticker():
    got = co.parse_blotter("Buy 7453 JT 1,200\nSELL,700 HK,500")
    assert got[0] == {"raw": "Buy 7453 JT 1,200", "side": "BUY", "bbg": "7453 JT", "qty": 1200}
    assert got[1]["bbg"] == "700 HK" and got[1]["qty"] == 500 and got[1]["side"] == "SELL"


# ───────────────────────────── pre-trade checks ─────────────────────────────

def test_split_check():
    assert co.split_check(100, 110)["verdict"] == "OK"
    s = co.split_check(300, 100.4)
    assert s["verdict"] == "SPLIT_SUSPECT" and s["split_ratio"] == pytest.approx(1 / 3, abs=1e-4)
    assert co.split_check(100, 145)["verdict"] == "GAP"


def test_share_classes_keep_one_line_per_issuer():
    r = pd.DataFrame({"symbol": ["GOOGL", "GOOG", "NEWA", "NEWB", "X"],
                      "name": ["Alphabet Inc.", "Alphabet Inc.", "Newco Holdings Class A", "Newco Holdings Class B", "Xylo"]})
    kept, dup = co.dedupe_issuers(r)
    assert kept.symbol.tolist() == ["GOOGL", "NEWA", "X"]
    assert set(dup.refusal) == {"REFUSED_SAME_ISSUER_AS GOOGL", "REFUSED_SAME_ISSUER_AS NEWA"}


def test_defect_flag_respects_the_lookback():
    recent = str((pd.Timestamp(TODAY) - pd.Timedelta(days=30)).date())
    old = str((pd.Timestamp(TODAY) - pd.Timedelta(days=3000)).date())
    d = {"_file": "f", "NEW": [("SPIKE", recent)], "OLD": [("SPIKE", old)]}
    assert co.defect_flag("NEW", TODAY, d) and co.defect_flag("OLD", TODAY, d) is None


def test_drift_check_prints_trim():
    p = pd.DataFrame({"symbol": list("AB"), "qty": [1000, 1000], "price_usd": [300.0, 100.0]})
    out = co.drift_check(p, 1_000_000).set_index("symbol")
    assert bool(out.at["A", "over_nav_cap"]) and out.at["A", "trim_shares_if_at_all_times"] == 334
    assert not bool(out.at["B", "over_nav_cap"])


# ───────────────────────────── calendar ─────────────────────────────

def test_future_sessions_skip_japans_second_monday_of_october():
    pytest.importorskip("exchange_calendars")
    y = TODAY.year if TODAY.month < 11 else TODAY.year + 1
    mondays = [date(y, 10, d) for d in range(1, 32) if date(y, 10, d).weekday() == 0]
    hol = pd.Timestamp(mondays[1])
    jp, src = desk.future_sessions("7203.T", hol - pd.Timedelta(days=4), hol + pd.Timedelta(days=4))
    us, _ = desk.future_sessions("AAPL", hol - pd.Timedelta(days=4), hol + pd.Timedelta(days=4))
    assert hol not in jp and hol in us and src.startswith("exchange_calendars")


# ───────────────────────────── freeze and grade ─────────────────────────────

def test_freeze_is_write_once(tmp_path):
    payload = {"day": "d", "freeze_utc": "t", "tickets": [], "control": {"sheet_code": "C", "n_lines": 0}}
    rec = reh.freeze(TODAY, payload, "m", "s", folder=tmp_path / "s", log=tmp_path / "log.jsonl")
    assert len(rec["sha256"]) == 64
    with pytest.raises(reh.FrozenSheetExists):
        reh.freeze(TODAY, payload, "m", "s", folder=tmp_path / "s", log=tmp_path / "log.jsonl")
    assert len((tmp_path / "log.jsonl").read_text().splitlines()) == 1


def _px(days, rows):
    out = []
    for sym, opens in rows.items():
        for d, o in zip(days, opens):
            out.append({"symbol": sym, "date": d, "open": o, "close": o})
    return pd.DataFrame(out)


def test_grade_states_and_usd_pnl():
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=3), periods=4)
    px = _px(days, {"W": [10, 11, 12, 13], "H": [np.nan, 5, 5, 5], "X": [20, np.nan, 22, 22],
                    reh.BENCH: [100, 101, 102, 103]})
    mk = lambda pid, s, lim=None: {"pos_id": pid, "sheet": "s", "symbol": s, "bbg": f"{s} US Equity", "market": "US",
                                  "qty": 100, "entry_session": str(days[0].date()), "currency": "USD",
                                  "limit_local": lim, "sell": {"session_date": str(days[1].date())}}
    rows = {r["pos_id"]: r for r in reh.grade_positions([mk("w", "W"), mk("h", "H"), mk("x", "X"), mk("l", "W", 9.0)],
                                                         px, pd.DataFrame(), px[px.symbol == reh.BENCH], today=TODAY)}
    assert rows["w"]["state"] == "CLOSED" and rows["w"]["pnl_usd"] == pytest.approx(100.0)
    assert rows["w"]["bench_ret"] == pytest.approx(0.01)
    assert rows["h"]["state"] == "NO_FILL_HALTED"
    assert rows["x"]["exit_session"] == str(days[2].date()) and rows["x"]["exit_delayed"]
    assert rows["l"]["state"] == "NO_FILL_ABOVE_LIMIT"
    s = reh.book_summary(list(rows.values()), bench=px[px.symbol == reh.BENCH])
    assert s["n_closed"] == 2 and s["pnl_usd_0bps"] == pytest.approx(300.0)
    assert s["relative_0bps"] == pytest.approx(300.0 / 1e6 - 0.02)


def test_price_outage_leaves_grades_pending():
    def boom(*a, **k):
        raise ConnectionError("down")
    d0 = TODAY - timedelta(days=10)
    px, src = reh.fetch_opens(["ZZZNOTREAL1"], d0, TODAY, downloader=boom)
    assert src in ("disk_fallback", "NONE")
    pos = [{"pos_id": "p", "sheet": "s", "symbol": "ZZZNOTREAL1", "bbg": "Z US Equity", "market": "US", "qty": 1,
            "entry_session": str(d0), "sell": None, "currency": "USD"}]
    rows = reh.grade_positions(pos, px[px.symbol == "ZZZNOTREAL1"], pd.DataFrame(), px.iloc[0:0], today=TODAY)
    assert rows[0]["state"] == "PENDING_PRICE"


# ───────────────────────────── strategy lab ─────────────────────────────

def test_lab_book_path_gross_and_exits():
    from scripts import contest_book_compare as cbc
    from scripts import contest_strategy_lab as lab
    T, N = 12, 8
    r = np.full((T, N), 0.01)
    m = cbc.Mkt(r=r, last=np.zeros((T, N), bool), bench=np.zeros(T), liq=np.ones((T, N), bool),
                sig=np.ones((T, N)) * 0.02, n_faults=0)
    ev = pd.DataFrame({"pre_i": [2] * 6 + [3], "react_i": [3] * 6 + [5], "ci": list(range(6)) + [6],
                       "trail_abs": [.9, .8, .7, .6, .5, .4, .3], "on_cadence": True})
    days = np.arange(1, 10)
    oc = np.full((T, N), 0.05)
    through = lab.book_path(days, ev, m, k=5, rank="trail", exit="through", oc=oc)
    assert through.gross.max() <= 1.0 + 1e-9
    assert through.set_index("t").at[2, "book"] == pytest.approx(5 * 0.2 * 0.01)
    before = lab.book_path(days, ev, m, k=5, rank="trail", exit="before", oc=oc)
    assert before.set_index("t").at[2, "book"] == pytest.approx(5 * 0.2 * 0.05)
    assert before.set_index("t").at[2, "traded"] == pytest.approx(2.0)      # in and out the same day
    three = lab.book_path(days, ev, m, k=3, rank="trail", exit="through", oc=oc)
    assert three.gross.max() == pytest.approx(0.6)
    mt = lab.book_path(days, ev, m, k=5, rank="maxtail", exit="hold")
    assert (mt.gross == 1.0).all() and mt.traded.iloc[0] == pytest.approx(1.0)


# ───────────────────────────── modes and the wind-down ─────────────────────────────

def test_use_mode_switches_folders_and_last_day():
    try:
        reh.use_mode("contest")
        assert reh.SHEET_DIR.parent.name == "live" and reh.LAST_SHEET_DAY == cc.CONTEST_END - timedelta(days=1)
        reh.use_mode("rehearsal")
        assert reh.SHEET_DIR.parent.name == "rehearsal" and reh.LAST_SHEET_DAY == cc.CONTEST_START - timedelta(days=3)
    finally:
        reh.use_mode("rehearsal")


def test_sell_only_sheet_closes_a_frozen_position(tmp_path, monkeypatch):
    for name in ("SHEET_DIR", "CAL_DIR", "DESK_HOLD", "GRADE_DIR"):
        monkeypatch.setattr(reh, name, tmp_path / name.lower())
    monkeypatch.setattr(reh, "FREEZE_LOG", tmp_path / "freeze.jsonl")
    monkeypatch.setattr(reh, "REH", tmp_path)
    buy_day = _us_session_ahead(2)
    t, _, _ = reh.build_tickets(buy_day, _world(buy_day, ["AAA"]), [], nav_usd=1e6, now_utc=_before(buy_day),
                                price_of=_price())
    payload = {"day": str(buy_day), "freeze_utc": "x", "tickets": co.to_json(t), "control": co.control_block(t)}
    reh.freeze(buy_day, payload, "m", "s")
    exit_day = pd.Timestamp(t[0].extra["exit_session"]).date()
    rec = reh.sheet(exit_day, buys=False, now=co.session_open_utc("AAA", exit_day) - pd.Timedelta(hours=10))
    o = reh.load_orders(str(exit_day))
    sells = [x for x in o["tickets"] if x["side"] == "SELL"]
    assert rec["n_live"] == 1 and len(sells) == 1 and sells[0]["qty"] == t[0].qty
    assert reh.open_positions() == []
