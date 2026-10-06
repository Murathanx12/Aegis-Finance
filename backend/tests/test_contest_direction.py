"""Contest rehearsal C9: ROT5_DIR beside ROT5_TRAIL, the worst case, the 20% cap refusal, the live
desk's MEMB + REGISTERED gate, and New York -> Hong Kong times.

Synthetic inputs, dates derived from today, no network."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from scripts import contest_calendar as cc
from scripts import contest_desk as desk
from scripts import contest_direction as cd
from scripts import contest_orders as co
from scripts import contest_rehearsal as reh

TODAY = date.today()
REPO = Path(__file__).resolve().parents[2]


def _us_session_ahead(n: int = 3) -> date:
    d = TODAY + timedelta(days=n)
    sess, _ = desk.future_sessions("AAPL", d, d + timedelta(days=14))
    return sess[0].date()


def _world(day: date, syms: list[str]) -> pd.DataFrame:
    sess, _ = desk.future_sessions("AAPL", day + timedelta(days=1), day + timedelta(days=14))
    r = pd.DataFrame({"symbol": syms, "pre_date": pd.Timestamp(day), "react_date": pd.Timestamp(sess[0]),
                      "timing": "AMC", "trail_abs": np.linspace(0.12, 0.05, len(syms))})
    r["bbg_ticker"] = r.symbol.map(cc.bloomberg_ticker)
    r["market"] = "US"
    r["rank"] = np.arange(1, len(r) + 1)
    r["date_status"] = "VENDOR_ANNOUNCED"
    r["date_confirmed"] = False
    return r


def _price(s: str):
    return (50.0, 1.0, "USD")


def _before(day: date) -> pd.Timestamp:
    return co.session_open_utc("AAPL", day) - pd.Timedelta(hours=6)


def _rev(asof: date, *, pulled_days_ago: float = 1.0) -> pd.DataFrame:
    """Dated rows relative to `asof`: B is net Sell, C has net lowerings, A/D/E are Buy-rated with raises,
    F and G carry no rows (UNRATED). A Sell on A dated AFTER asof must be ignored (point in time)."""
    pulled = (pd.Timestamp(asof, tz="UTC") - pd.Timedelta(days=pulled_days_ago)).isoformat()
    t = lambda k: str(pd.Timestamp(asof) - pd.Timedelta(days=k))
    rows = []
    for s in ("A", "D", "E"):
        rows += [(s, t(20), "F1", "Buy", "main", "Raises"), (s, t(40), "F2", "Overweight", "up", "Raises")]
    rows += [("B", t(10), "F1", "Sell", "down", "Lowers"), ("B", t(30), "F2", "Underweight", "main", ""),
             ("B", t(50), "F3", "Hold", "main", "Raises")]
    rows += [("C", t(10), "F1", "Buy", "main", "Lowers"), ("C", t(20), "F2", "Neutral", "main", "Lowers"),
             ("C", t(70), "F3", "Buy", "main", "Raises")]
    rows += [("A", str(pd.Timestamp(asof) + pd.Timedelta(days=1)), "F9", "Sell", "down", "Lowers")]
    d = pd.DataFrame(rows, columns=["ticker", "event_date", "firm", "to_grade", "action", "target_action"])
    d["pulled_at"] = pulled
    # the after-asof row cannot have been pulled before it happened: give it a later pull stamp too
    d.loc[d.firm == "F9", "pulled_at"] = (pd.Timestamp(asof, tz="UTC") + pd.Timedelta(days=2)).isoformat()
    return d


# ───────────────────────────── ROT5_DIR vs ROT5_TRAIL ─────────────────────────────

def test_dir_drops_a_sell_consensus_name_that_trail_buys_and_keeps_the_sizing():
    day = _us_session_ahead()
    world = _world(day, list("ABCDEFG"))
    now = _before(day)
    rev = _rev(day)
    rdir, dropped, meta = cd.direction_rank(world, day, rev=rev, now_utc=now)
    assert set(dropped.symbol) == {"B", "C"}
    assert dict(zip(dropped.symbol, dropped.verdict)) == {"B": "DROP_NET_SELL", "C": "DROP_NET_LOWERING"}
    assert set(rdir.symbol) == set("ADEFG") and set(rdir.symbol) <= set(world.symbol)    # same universe, filtered
    assert rdir.set_index("symbol").loc["A", "verdict"] == "ADMIT"                        # the after-asof Sell is ignored
    assert set(rdir[rdir.verdict == "UNRATED"].symbol) == {"F", "G"}
    t_trail, _, _ = reh.build_tickets(day, world, [], nav_usd=1e6, now_utc=now, price_of=_price)
    t_dir, _, _ = reh.build_tickets(day, rdir, [], nav_usd=1e6, now_utc=now, price_of=_price)
    bt = {t.symbol: t for t in t_trail if t.side == "BUY"}
    bd = {t.symbol: t for t in t_dir if t.side == "BUY"}
    assert "B" in bt and "B" not in bd and "C" not in bd
    assert len(bt) == len(bd) == reh.K
    for s in set(bt) & set(bd):                     # identical sizing, entry and exit on shared names
        assert (bt[s].qty, bt[s].limit_local, bt[s].session_date, bt[s].extra["exit_session"]) == \
               (bd[s].qty, bd[s].limit_local, bd[s].session_date, bd[s].extra["exit_session"])
    assert meta["contract_sha256"] == cd.contract_sha("ROT5_DIR")


def test_dir_orders_inside_a_one_point_magnitude_bucket_by_revision_momentum():
    day = _us_session_ahead()
    w = _world(day, ["P", "Q"])
    w["trail_abs"] = [0.0790, 0.0710]              # same 7% bucket; Q has the better revisions
    rev = pd.DataFrame({"ticker": ["P", "Q", "Q"], "firm": ["F1", "F1", "F2"],
                        "event_date": [str(pd.Timestamp(day) - pd.Timedelta(days=5))] * 3,
                        "to_grade": ["Buy", "Buy", "Buy"], "action": ["main", "up", "main"],
                        "target_action": ["Lowers", "Raises", "Raises"]})
    rev["pulled_at"] = (pd.Timestamp(day, tz="UTC") - pd.Timedelta(days=1)).isoformat()
    r, dropped, _ = cd.direction_rank(w, day, rev=rev, now_utc=_before(day))
    assert list(dropped.symbol) == ["P"]           # P: one lowering, net -1 -> dropped, not re-ordered
    w2 = w.copy()
    rev2 = rev[rev.ticker == "Q"].copy()
    r2, _, _ = cd.direction_rank(w2, day, rev=rev2, now_utc=_before(day))
    assert list(r2.symbol) == ["Q", "P"]           # P unrated (rev_mom 0) falls behind Q inside the bucket


def test_dir_refuses_a_stale_direction_source():
    day = _us_session_ahead()
    with pytest.raises(cd.DirectionRefused):
        rev = _rev(day, pulled_days_ago=30)
        cd.direction_rank(_world(day, list("AB")), day, rev=rev[rev.firm != "F9"], now_utc=_before(day))


# ───────────────────────────── worst case and the cap ─────────────────────────────

def test_worst_case_prints_the_largest_book_in_dollars():
    book = [{"symbol": s, "notional_usd": 200_000.0, "sig63": sg, "trail_abs": 0.08}
            for s, sg in zip("ABCDE", (0.02, 0.03, 0.04, 0.05, 0.06))]
    w = cd.worst_case(nav_usd=1_000_000.0, cap_binding=200_000.0, book=book, k=5)
    assert w["largest_admissible_gross_usd"] == pytest.approx(1_000_000.0)
    assert w["largest_admissible_gross_over_equity"] == pytest.approx(1.0)
    assert w["largest_at_stop_usd"]["5%"] == pytest.approx(-50_000.0)
    assert w["largest_at_2sigma63_usd"] == pytest.approx(-1_000_000.0 * 2 * 0.06)
    assert w["book_at_2sigma63_usd"] == pytest.approx(-sum(200_000 * 2 * s for s in (0.02, 0.03, 0.04, 0.05, 0.06)))
    assert w["book_at_2x_trailing_move_usd"] == pytest.approx(-1_000_000 * 2 * 0.08)
    lines = cd.worst_case_lines(w, "X")
    assert "$1,000,000" in lines[0] and "$50,000" in lines[0] and "carries a stop" in lines[1]


def _ticket(notional: float, qty: int = 100, side: str = "BUY") -> co.Ticket:
    return co.Ticket(n=1, side=side, bbg="ZZZ US Equity", symbol="ZZZ", market="US", qty=qty, order_type="LIMIT",
                     limit_local=1.0, currency="USD", session_date=str(TODAY), open_utc="x", open_hkt="x",
                     open_ny="x", notional_usd=notional)


def test_cap_refuses_a_name_above_twenty_percent_and_gross_above_nav():
    cd.assert_cap([_ticket(199_999.0)], nav_usd=1e6, cap_binding=200_000.0)
    with pytest.raises(cd.CapRefused, match="20% cap"):
        cd.assert_cap([_ticket(200_001.0)], nav_usd=1e6, cap_binding=200_000.0)
    with pytest.raises(cd.CapRefused, match="20% cap"):         # the NAV reading binds when NAV fell
        cd.assert_cap([_ticket(170_000.0)], nav_usd=800_000.0, cap_binding=co.cap_usd(800_000.0)["binding"])
    with pytest.raises(cd.CapRefused, match="no leverage"):
        cd.assert_cap([_ticket(199_000.0)] * 2, nav_usd=1e6, cap_binding=200_000.0, held_notional_usd=700_000.0)
    v = _ticket(900_000.0)
    v.status = "VOID_LATE"                                    # a void line is never entered: not counted
    cd.assert_cap([v], nav_usd=1e6, cap_binding=200_000.0)


# ───────────────────────────── contracts ─────────────────────────────

def test_contract_is_declared_once_and_an_edit_refuses(tmp_path, monkeypatch):
    log = tmp_path / "freeze_log.jsonl"
    r1 = cd.ensure_contract("ROT5_DIR", log)
    r2 = cd.ensure_contract("ROT5_DIR", log)
    assert r1["contract_sha256"] == r2["contract_sha256"] == cd.contract_sha("ROT5_DIR")
    assert sum(1 for _ in log.read_text(encoding="utf-8").splitlines()) == 1
    edited = {**cd.RULES, "ROT5_DIR": {**cd.RULES["ROT5_DIR"], "max_source_age_days": 99}}
    monkeypatch.setattr(cd, "RULES", edited)
    with pytest.raises(cd.ContractChanged):
        cd.ensure_contract("ROT5_DIR", log)


def test_every_book_freezes_at_the_same_now(tmp_path, monkeypatch):
    for name in ("SHEET_DIR", "CAL_DIR", "DESK_HOLD", "GRADE_DIR"):
        monkeypatch.setattr(reh, name, tmp_path / name.lower())
    monkeypatch.setattr(reh, "FREEZE_LOG", tmp_path / "freeze.jsonl")
    monkeypatch.setattr(reh, "REH", tmp_path)
    day = _us_session_ahead(2)
    rec = reh.sheet(day, buys=False, now=_before(day))
    assert set(rec["alternates"]) == set(cd.STRATEGIES)
    lines = [json.loads(x) for x in (tmp_path / "freeze.jsonl").read_text(encoding="utf-8").splitlines()]
    contracts = [x for x in lines if x.get("kind") == "STRATEGY_CONTRACT"]
    sheets = [x for x in lines if x.get("kind") != "STRATEGY_CONTRACT"]
    assert {c["strategy"] for c in contracts} == set(cd.STRATEGIES)
    assert {s.get("strategy") for s in sheets} == {"ROT5_TRAIL", *cd.STRATEGIES}
    assert len({s["freeze_utc"] for s in sheets}) == 1
    for n in cd.STRATEGIES:
        o = json.loads((tmp_path / "strategies" / n / "sheets" / str(day) / "orders.json").read_text(encoding="utf-8"))
        assert o["contract_sha256"] == cd.contract_sha(n) and "worst_case" in o


def test_grader_prints_the_books_side_by_side(tmp_path, monkeypatch):
    for name in ("SHEET_DIR", "CAL_DIR", "DESK_HOLD", "GRADE_DIR"):
        monkeypatch.setattr(reh, name, tmp_path / name.lower())
    monkeypatch.setattr(reh, "FREEZE_LOG", tmp_path / "freeze.jsonl")
    monkeypatch.setattr(reh, "REH", tmp_path)
    days = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=3), periods=3)

    def tk(n, side, sym, sess, pos_id=None):
        t = co.Ticket(n=n, side=side, bbg=f"{sym} US Equity", symbol=sym, market="US", qty=1000,
                      order_type="LIMIT" if side == "BUY" else "MARKET AT OPEN", limit_local=None, currency="USD",
                      session_date=str(sess.date()), open_utc=str(co.session_open_utc(sym, sess)), open_hkt="x",
                      open_ny="x", notional_usd=10_000.0 if side == "BUY" else 0.0,
                      extra={"exit_session": str(days[1].date()), "trail_abs": 0.05} if side == "BUY" else {"pos_id": pos_id})
        return t
    trail_sd = reh.SHEET_DIR
    dir_sd, _, _ = reh.strat_dirs("ROT5_DIR")
    d0, d1 = str(days[0].date()), str(days[1].date())
    for folder, syms in ((trail_sd, ["W", "L"]), (dir_sd, ["W"])):
        buys = [tk(i + 1, "BUY", s, days[0]) for i, s in enumerate(syms)]
        reh.freeze(days[0].date(), {"freeze_utc": "x", "tickets": co.to_json(buys), "control": co.control_block(buys)},
                   "m", "s", folder=folder)
        sells = [tk(i + 1, "SELL", s, days[1], pos_id=f"{d0}:{s} US") for i, s in enumerate(syms)]
        reh.freeze(days[1].date(), {"freeze_utc": "x", "tickets": co.to_json(sells), "control": co.control_block(sells)},
                   "m", "s", folder=folder)
    px = pd.DataFrame([{"symbol": s, "date": d, "open": o, "close": o}
                       for s, opens in {"W": [10, 13, 13], "L": [10, 9, 9], reh.BENCH: [100, 101, 101]}.items()
                       for d, o in zip(days, opens)])
    g = reh.grade(today=TODAY, downloader=lambda syms, a, b: px)
    assert g["n_closed"] == 2 and g["alternates"]["ROT5_DIR"]["n_closed"] == 1
    assert g["alternates"]["ROT5_DIR"]["pnl_usd_0bps"] == pytest.approx(3_000.0)
    m = g["metrics"]
    assert m["top_name"].startswith("W US Equity") and m["top_share_of_net_pnl"] == pytest.approx(3_000 / 2_000)
    assert m["relative_0bps_without_top"] == pytest.approx(-1_000 / 1e6 - 0.01)
    sb = (tmp_path / "SCOREBOARD.md").read_text(encoding="utf-8")
    assert "## Books side by side" in sb and "| ROT5_DIR |" in sb and "ROT5_TRAIL on ROT5_DIR's sheets" in sb
    assert (tmp_path / "strategies" / "ROT5_DIR" / "grades").exists()


# ───────────────────────────── the live gate ─────────────────────────────

def test_live_gate_refuses_without_memb_and_registered_and_writes_a_receipt(tmp_path):
    ok, reasons = cd.live_gate(tmp_path)
    assert not ok and len(reasons) == 2
    assert any("MEMB" in r for r in reasons) and any("REGISTERED" in r for r in reasons)
    p = cd.gate_receipt(reasons, TODAY, contest_dir=tmp_path)
    rec = json.loads(p.read_text(encoding="utf-8"))
    assert rec["result"] == "REFUSED" and rec["reasons"] == reasons and rec["places_orders"] is False
    assert "REFUSED" in (tmp_path / "logs" / "contest_live_gate.log").read_text(encoding="utf-8")
    (tmp_path / "wls").mkdir()
    _memb(tmp_path / "wls" / "memb.csv", 1200)
    ok, reasons = cd.live_gate(tmp_path)
    assert not ok and len(reasons) == 1 and "REGISTERED" in reasons[0]
    (tmp_path / "REGISTERED").write_text("", encoding="utf-8")
    assert cd.live_gate(tmp_path) == (True, [])


def test_contest_daily_refuses_the_live_sheet_and_the_rehearsal_does_not_ask(tmp_path):
    orig = cc.CONTEST
    try:
        cc.CONTEST = tmp_path
        reh.use_mode("contest")
        rc = reh.daily(cc.CONTEST_START)
        run = json.loads((tmp_path / "live" / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert rc == 0 and run["sheet"].startswith("REFUSED_LIVE_GATE")
        assert list((tmp_path / "live" / "refusals").glob("live_gate_*.json"))
        assert not (tmp_path / "live" / "sheets").exists()
    finally:
        cc.CONTEST = orig
        reh.use_mode("rehearsal")
    assert reh.MODE == "REHEARSAL" and reh.REH == cc.CONTEST / "rehearsal"


# ───────────────────────────── New York -> Hong Kong ─────────────────────────────

@pytest.mark.parametrize("ahead", [0, 30, 60, 120, 200])
def test_freeze_time_is_computed_in_et_with_the_dst_rule(ahead):
    d = TODAY + timedelta(days=ahead)
    f = cd.freeze_time_et(d)
    hk = datetime(d.year, d.month, d.day, 14, 30, tzinfo=ZoneInfo("Asia/Hong_Kong"))
    gap_h = (hk.utcoffset() - f.utcoffset()).total_seconds() / 3600
    assert f == hk and gap_h in (12.0, 13.0)
    assert gap_h == (12.0 if f.dst() else 13.0)                 # NY on daylight time: 12 h behind HKT
    assert (f.hour, f.minute) == ((2, 30) if f.dst() else (1, 30))
    assert f < cd.us_open_et(d)                                 # the sheet freezes before that day's US open


def test_contest_deadlines_in_hkt_are_derived_from_new_york():
    t = cd.contest_times()
    fmt = lambda x: x.strftime("%b %d %H:%M")
    assert fmt(t["registration_closes"]["hkt"]) == "Oct 05 11:59"
    assert fmt(t["contest_starts"]["hkt"]) == "Oct 12 21:00"
    assert fmt(t["initial_positions_due"]["hkt"]) == "Oct 17 11:59"
    assert fmt(t["contest_ends"]["hkt"]) == "Nov 14 06:00"      # NY is UTC-5 after Nov 1
    assert cd.contest_start_utc() == pd.Timestamp("2026-10-12 13:00", tz="UTC")


def test_runbook_prints_the_derived_times():
    text = (REPO / "docs" / "CONTEST_RUNBOOK_2026-10.md").read_text(encoding="utf-8")
    for k, v in cd.contest_times().items():
        ny, hk = v["ny"], v["hkt"]
        assert f"{ny:%b} {ny.day} {ny:%H:%M} NY" in text, k
        assert f"{hk:%b} {hk.day} {hk:%H:%M} HKT" in text, k
    assert "Oct 4 23:59 HKT" not in text


# ───────────────────────────── review C9 fixes ─────────────────────────────

def _memb(path: Path, n: int, header: str = "WLS Index Members") -> None:
    rows = "\n".join(f"T{i:05d} US Equity,Name {i}" for i in range(n))
    path.write_text(f"{header},\nTicker,Name\n{rows}\n" if header else f"Ticker,Name\n{rows}\n", encoding="utf-8")


def test_wls_check_needs_the_wls_header_and_a_thousand_rows(tmp_path):
    w = tmp_path / "wls"
    w.mkdir()
    _memb(w / "memb.csv", 10)
    ok, why, info = cd.wls_export_check(w)
    assert not ok and "1000" in why.replace(",", "")
    _memb(w / "memb.csv", 1500, header="")                     # another index's MEMB: no WLS anywhere
    ok, why, _ = cd.wls_export_check(w)
    assert not ok and "WLS" in why
    _memb(w / "memb.csv", 1500)
    ok, why, info = cd.wls_export_check(w)
    assert ok and info["rows"] >= 1000 and info["file"] == "memb.csv"


def test_first_seen_after_the_freeze_is_excluded_and_the_source_is_fingerprinted():
    day = _us_session_ahead()
    now = _before(day)
    rev = _rev(day)
    rev["first_seen_utc"] = rev["pulled_at"]
    # the vendor ADDS a Sell on E dated last month, first served after the freeze: a rewrite of history
    extra = pd.DataFrame([{"ticker": "E", "event_date": str(pd.Timestamp(day) - pd.Timedelta(days=30)), "firm": "F7",
                           "to_grade": "Sell", "action": "down", "target_action": "Lowers",
                           "pulled_at": (now + pd.Timedelta(hours=3)).isoformat(),
                           "first_seen_utc": (now + pd.Timedelta(hours=3)).isoformat()},
                          {"ticker": "E", "event_date": str(pd.Timestamp(day) - pd.Timedelta(days=31)), "firm": "F8",
                           "to_grade": "Sell", "action": "down", "target_action": "Lowers",
                           "pulled_at": (now + pd.Timedelta(hours=3)).isoformat(),
                           "first_seen_utc": (now + pd.Timedelta(hours=3)).isoformat()}])
    rev2 = pd.concat([rev, extra], ignore_index=True)
    d, meta = cd.analyst_direction(["E"], day, rev2, now_utc=now)
    assert d.verdict.iloc[0] == "ADMIT" and meta["rows_first_seen_after_the_freeze_excluded"] == 2
    later, _ = cd.analyst_direction(["E"], day, rev2, now_utc=now + pd.Timedelta(hours=4))
    assert d.n_sell.iloc[0] == 0 and later.n_sell.iloc[0] == 2  # visible only to a decision made after it
    fp = meta["fingerprint"]
    assert len(fp["sha256"]) == 64 and fp["rows"] == len(rev2)


def test_contract_covers_the_code_and_a_new_version_records_what_it_supersedes(tmp_path, monkeypatch):
    src = tmp_path / "strategy.py"
    src.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(cd, "CODE_FILES", (src,))
    a = cd.contract_sha("ROT5_DIR")
    src.write_text("x = 2\n", encoding="utf-8")
    assert cd.contract_sha("ROT5_DIR") != a                    # the code is in the hash, not only the prose
    src.write_bytes(b"x = 2\r\n")
    assert cd.contract_sha("ROT5_DIR") == cd.contract_sha("ROT5_DIR")
    log = tmp_path / "log.jsonl"
    r1 = cd.ensure_contract("ROT5_DIR", log)
    assert r1["code_sha256"] == cd.code_sha() and r1["rule_sha256"] == cd.rule_sha("ROT5_DIR")
    src.write_text("x = 3\n", encoding="utf-8")
    with pytest.raises(cd.ContractChanged):
        cd.ensure_contract("ROT5_DIR", log)
    bumped = {**cd.RULES, "ROT5_DIR": {**cd.RULES["ROT5_DIR"], "version": cd.RULES["ROT5_DIR"]["version"] + 1}}
    monkeypatch.setattr(cd, "RULES", bumped)
    r2 = cd.ensure_contract("ROT5_DIR", log)
    assert r2["supersedes"] == r1["contract_sha256"]


@pytest.mark.parametrize("raw", [
    "ROT5_DIR".encode("utf-16"),                              # PowerShell 5.1: echo ROT5_DIR > BOOK
    "﻿ROT5_DIR\r\n".encode("utf-8"),                     # Set-Content -Encoding utf8 (BOM)
    b"  rot5_dir  \n\n",
])
def test_book_file_tolerates_powershell_encodings(tmp_path, raw):
    p = tmp_path / "BOOK"
    p.write_bytes(raw)
    assert cd.read_book_file(p) == ("ROT5_DIR", None)


def test_a_bad_book_file_never_loses_the_day(tmp_path):
    orig = cc.CONTEST
    try:
        cc.CONTEST = tmp_path
        (tmp_path / "live").mkdir()
        (tmp_path / "live" / "BOOK").write_text("ROT6_WHATEVER", encoding="utf-8")
        book, why = reh.live_book(TODAY)
        assert book == "ROT5_TRAIL" and "ROT6_WHATEVER" in why
        txt = (tmp_path / "live" / f"REFUSED_{TODAY}.txt").read_text(encoding="utf-8")
        assert "trades the default ROT5_TRAIL" in txt and "Set-Content" in txt
        (tmp_path / "live" / "BOOK").write_bytes("MAXTAIL_EVT".encode("utf-16"))
        assert reh.live_book(TODAY) == ("MAXTAIL_EVT", None)
    finally:
        cc.CONTEST = orig


def test_dry_previews_are_bannered_and_never_under_live(tmp_path):
    md, short = reh._dryify("# ORDER SHEET 2026-01-01  (frozen x UTC)\n\nbody | LIVE |\n", "ORDERS x",
                            name="ROT5_TRAIL", day=TODAY, stamp="s", gate="g")
    first = md.splitlines()[0]
    assert first.startswith("# " + reh.DRY_TITLE) and "frozen x" not in first and "ORDER SHEET 2026" not in md
    assert short.startswith(reh.DRY_TITLE) and md.count(reh.DRY_TITLE) >= 2
    orig = cc.CONTEST
    try:
        cc.CONTEST = tmp_path
        reh.use_mode("contest")
        root = reh._dry_root()
        assert (tmp_path / "live") not in root.parents and root != tmp_path / "live"
    finally:
        cc.CONTEST = orig
        reh.use_mode("rehearsal")


def test_drift_line_prints_the_trim_and_says_the_rule_is_open():
    held = [{"pos_id": "p1", "symbol": "UP", "bbg": "UP US Equity", "qty": 2000},
            {"pos_id": "p2", "symbol": "FLAT", "bbg": "FLAT US Equity", "qty": 1000}]
    px = {"UP": 124.0, "FLAT": 100.0}
    lines, recs = reh.drift_lines(held, [], 1_048_000.0, lambda s: (px[s], 1.0, "USD"))
    assert "NOT settled" in lines[0]
    up = next(r for r in recs if r["symbol"] == "UP")
    assert up["pct_nav"] == pytest.approx(248_000 / 1_048_000, abs=1e-4)
    assert up["trim_shares_if_at_all_times"] == int(np.ceil((248_000 - 200_000) / 124.0))
    assert next(r for r in recs if r["symbol"] == "FLAT")["trim_shares_if_at_all_times"] == 0


def test_contest_window_refuses_first_day_asia_and_europe_and_prints_after_the_end():
    start = cd.contest_start_utc()
    first = pd.Timestamp(start.tz_convert("America/New_York").date())
    last = pd.Timestamp(cc.CONTEST_END)
    r = pd.DataFrame({"symbol": ["7203.T", "SAP.DE", "AAPL", "MSFT"],
                      "pre_date": [first, first, first, last],
                      "react_date": [first + pd.Timedelta(days=1)] * 3 + [last + pd.Timedelta(days=3)]})
    ok, refused = reh._contest_window_filter(r)
    assert list(ok.symbol) == ["AAPL"]
    why = dict(zip(refused.symbol, refused.refusal))
    assert why["7203.T"].startswith("REFUSED_BEFORE_CONTEST_START") and why["SAP.DE"].startswith("REFUSED_BEFORE")
    assert why["MSFT"].startswith("REFUSED_REACTS_AFTER_CONTEST_END")


def _panel_and_events(day: date):
    dates = pd.bdate_range(end=pd.Timestamp(day) - pd.Timedelta(days=1), periods=90)
    rng = np.random.default_rng(7)
    syms = ["AAA", "BBB", "CCC", "JMP", "DDD", "EEE", "FFF"]
    vol = {"AAA": 0.06, "BBB": 0.05, "CCC": 0.04, "JMP": 0.02, "DDD": 0.03, "EEE": 0.025, "FFF": 0.022}
    C = np.empty((len(dates), len(syms)))
    for j, s in enumerate(syms):
        C[:, j] = 50 * np.exp(np.cumsum(rng.normal(0, vol[s], len(dates))))
    C[60:, syms.index("JMP")] *= 3.0                       # a x3 one-day jump: a split / stitch, not volatility
    lr = np.vstack([np.full((1, C.shape[1]), np.nan), np.diff(np.log(C), axis=0)])
    sig = pd.DataFrame(lr).rolling(63, min_periods=40).std().to_numpy()
    panel = desk.Panel(dates, pd.Index(syms), C.astype("float32"), C.astype("float32"),
                       np.full(C.shape, 50e6, dtype="float32"), sig.astype("float32"),
                       np.array(["US"] * len(syms)), {s: i for i, s in enumerate(syms)})
    ev = pd.DataFrame({"symbol": [s for s in syms for _ in range(4)], "absr": 0.05})
    return panel, ev


def test_maxtail_ranks_raw_sigma_and_refuses_x2_jumps():
    day = _us_session_ahead()
    panel, ev = _panel_and_events(day)
    ranked, jumps = cd.maxtail_ranked(day, panel, ev, None)
    assert list(jumps.symbol) == ["JMP"] and jumps.refusal.iloc[0].startswith("REFUSED_JUMP_X2")
    assert "JMP" not in set(ranked.symbol)
    assert list(ranked.symbol[:3]) == ["AAA", "BBB", "CCC"]    # raw sigma63 order, no ex-max estimator
    only, _ = cd.maxtail_ranked(day, panel, ev, None, only={"CCC", "DDD"})
    assert set(only.symbol) == {"CCC", "DDD"}


def test_contest_maxtail_buys_once_after_the_start_and_holds_past_the_end():
    day = _us_session_ahead()
    panel, ev = _panel_and_events(day)
    now = _before(day)
    nb = co.session_open_utc("AAPL", day) - pd.Timedelta(minutes=1)
    hold = co.session_open_utc("AAPL", day) + pd.Timedelta(days=30)
    r, jumps, desc = reh._maxtail_as_ranked(day, {"panel": panel, "events": ev}, now, None, name="MAXTAIL_BH",
                                            not_before=nb, hold_after=hold)
    assert len(r) >= 5 and "JMP" not in set(r.symbol) and "raw sigma63" in desc
    assert all(co.session_open_utc(s, p) >= nb for s, p in zip(r.symbol, r.pre_date))
    assert all(co.session_open_utc(s, x) > hold for s, x in zip(r.symbol, r.react_date))
    t, _, _ = reh.build_tickets(day, r, [], nav_usd=1e6, now_utc=now, price_of=_price)
    buys = [x for x in t if x.side == "BUY"]
    assert len(buys) == reh.K
    cd.assert_cap(t, nav_usd=1e6, cap_binding=200_000.0)
