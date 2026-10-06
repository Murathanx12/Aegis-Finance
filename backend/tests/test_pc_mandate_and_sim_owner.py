"""PC-PAPER mandate from the broker, the scaled view, and the sim owner (chunk C2, 2026-10-06).

OWNER DECISION 2026-10-06: PC-PAPER is a ~$1,000,000 paper experiment. The
decision contract is sized on the BROKER's equity read, never a literal; the
owner's own capital is a SCALED VIEW in whole shares that places no order. And
the sim has a scheduled owner, so "no sim in US hours" is a receipt with a
reason, never a week of silence.

No test reads this machine's broker files: every equity read is a fixture
stamped relative to NOW, and every clock is derived from today.
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config
from backend.services import decision_contract as DC
from backend.services import system_health as SH
from scripts import task_keeper as K

REPO = Path(__file__).resolve().parents[2]
EQ = 1_234_567.0                      # deliberately not any configured level
#: captured before the autouse fixture replaces the module attribute
REAL_PC_PAPER_EQUITY = DC.pc_paper_equity


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh(equity_usd: float = EQ, *, age: timedelta = timedelta(0), positions=None) -> dict:
    return {"equity_usd": equity_usd, "source": "fixture",
            "as_of": (_now() - age).isoformat(timespec="seconds"),
            "positions": positions or []}


@pytest.fixture(autouse=True)
def no_local_equity(monkeypatch):
    monkeypatch.setattr(DC, "pc_paper_equity", lambda **_: None)
    # no machine bars or ranking: names without a sigma price at the fallback
    monkeypatch.setattr(DC, "risk_inputs",
                        lambda: {"sigmas": {}, "exploit": {"symbols": [], "source": None}})


# ───────────────────────── 1. capital is derived from equity ─────────────────

def test_the_contract_capital_is_the_broker_equity(tmp_path, monkeypatch):
    monkeypatch.setattr(DC, "pc_paper_equity", lambda **_: _fresh())
    monkeypatch.setattr(DC, "agency_options", lambda day: ([], ""))
    DC.build_daily_contracts(asof=_now().date(), funnel_path=tmp_path / "absent.json",
                             out_dir=tmp_path, write=True)
    blob = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert blob["capital_usd"] == EQ
    rec = blob["capital_reconciliation"]
    assert rec["capital_usd"] == rec["broker_equity_usd"] == EQ
    assert rec["status"] == "OK" and rec["disagreements"] == []
    assert rec["capital_source"].startswith("derived: PC-PAPER broker equity read")
    assert rec["broker_equity_source"] == "fixture"
    assert blob["mandate"]["status"] == "OK"
    assert blob["worst_case_largest_admissible_book"]["equity_usd"] == EQ


def test_no_literal_owner_capital_on_the_sizing_path():
    """40,000 (the owner's real capital) may live only in config's scaled-view
    levels. A literal on the contract / plan / owner path is how the account
    was sized on the wrong number for ten days."""
    banned = {40_000, 40_000.0}
    for rel in ("backend/services/decision_contract.py", "scripts/sim_run.py",
                "scripts/task_keeper.py", "backend/services/pc_broker.py"):
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and not isinstance(n.value, bool)
                and isinstance(n.value, (int, float)) and n.value in banned]
        assert not hits, f"{rel}: literal owner capital at lines {hits}"
    assert any(float(c) == 40_000.0 for c in config.IC_CAPITAL_LEVELS)


def test_no_broker_read_is_unreconciled_by_name():
    m = DC.account_mandate(None, equity=None)
    assert m["status"] == "UNRECONCILED"
    assert m["capital_usd"] == max(float(c) for c in config.IC_CAPITAL_LEVELS)
    assert [d.split(":")[0] for d in m["disagreements"]] == ["NO_BROKER_EQUITY_READ"]
    assert "broker equity UNREAD" in m["line"]


def test_a_stale_broker_read_is_unreconciled():
    old = timedelta(days=float(config.PC_MANDATE_EQUITY_MAX_AGE_DAYS) + 2)
    m = DC.account_mandate(None, equity=_fresh(age=old))
    assert m["status"] == "UNRECONCILED"
    assert any(d.startswith("BROKER_EQUITY_STALE") for d in m["disagreements"])


def test_a_named_capital_inside_the_tolerance_is_ok_outside_is_not():
    tol = float(config.PC_MANDATE_CAPITAL_TOLERANCE)
    inside = DC.account_mandate(EQ * (1 + tol / 2), equity=_fresh())
    outside = DC.account_mandate(EQ * (1 + tol * 2), equity=_fresh())
    assert inside["status"] == "OK"
    assert outside["status"] == "UNRECONCILED"
    assert outside["disagreements"][0].startswith("CAPITAL_BASES_DISAGREE")


def test_the_newest_read_wins_by_its_own_stamp_not_the_file_time(tmp_path):
    newer, older = tmp_path / "a.json", tmp_path / "b.json"
    t_new = _now() - timedelta(hours=1)
    newer.write_text(json.dumps({"t": t_new.isoformat(), "equity": 1_100_000.0}),
                     encoding="utf-8")
    # written LAST, so its mtime is newest -- but its own stamp is older
    older.write_text(json.dumps({"t": (t_new - timedelta(days=3)).isoformat(),
                                 "equity": 900_000.0}), encoding="utf-8")
    eq = REAL_PC_PAPER_EQUITY(files=[newer, older])
    assert eq["equity_usd"] == 1_100_000.0 and eq["source"] == newer.name
    assert eq["age_days"] == pytest.approx(1 / 24, abs=0.01)
    assert REAL_PC_PAPER_EQUITY(files=[]) is None


# ───────────────────────── 2. the worst case, printed and gated ──────────────

HOT = {f"X{i}": 0.06 for i in range(8)}          # the ranker's names: 6%/day
CALM = {f"H{i}": 0.02 for i in range(10)}        # the held PROBE names: 2%/day


def _risk(sigmas: dict, exploit: list) -> dict:
    return {"sigmas": sigmas, "exploit": {"symbols": exploit, "source": "fixture"}}


def _held(names: list, w: float = 0.02) -> list:
    return [{"symbol": n, "market_value": w * EQ, "current_price": 10.0} for n in names]


def test_the_worst_case_is_priced_per_name_by_sleeve_and_the_verdict_is_derived(monkeypatch):
    sig = {**HOT, **CALM, **{f"U{i}": 0.01 * (i + 1) for i in range(10)}}
    monkeypatch.setattr(DC, "risk_inputs", lambda: _risk(sig, list(HOT)))
    monkeypatch.setattr(DC, "pc_paper_equity", lambda **_: _fresh(positions=_held(list(CALM))))
    blob = DC.payload([], asof=_now().date(), capital=EQ, candidates=None)
    t = blob["mandate"]["worst_case_table"]
    rows = {r["sleeve"]: r for r in t["rows"]}
    k = float(config.PROBE_WORST_CASE_SIGMA)
    ex_w = min(config.ER_EXPLOIT_MAX_WEIGHT, 0.12)
    ex_gross = rows["EXPLOIT"]["gross_over_equity"]
    assert rows["EXPLOIT"]["worst_case_k_sigma_frac"] == pytest.approx(ex_gross * k * 0.06)
    assert rows["PROBE"]["worst_case_k_sigma_frac"] == pytest.approx(
        config.PROBE_GROSS_CAP * k * 0.02)
    assert rows["EXPLOIT"]["avg_sigma"] == pytest.approx(0.06)
    total = ex_gross * k * 0.06 + config.PROBE_GROSS_CAP * k * 0.02
    limit = float(config.PC_WORST_CASE_MAX_FRAC_OF_EQUITY)
    # the verdict is DERIVED from the config and the names, never asserted as PASS
    want = "PASS" if total <= limit else "REFUSE"
    assert t["verdict"] == want and t["total_frac"] == pytest.approx(total)
    assert t["universe"]["median"]["frac"] is not None and t["universe"]["p90"]["frac"] is not None
    if want == "REFUSE":
        cap = (limit - config.PROBE_GROSS_CAP * k * 0.02) / (k * 0.06)
        assert t["trading_verdict"] == "PASS_EXPLOIT_CAPPED"
        assert t["exploit_gross_cap"] == pytest.approx(cap)
        # sized down, not refused outright: no WORST_CASE disagreement
        assert not any(d.startswith("WORST_CASE") for d in blob["mandate"]["disagreements"])
    assert ex_w > 0


def test_a_probe_book_over_the_limit_refuses_and_the_owner_will_not_trade(monkeypatch):
    sig = {**{n: 0.30 for n in CALM}}                # PROBE alone: 0.20 x 3 x 30% = 18%
    m = DC.account_mandate(None, equity=_fresh(positions=_held(list(CALM))),
                           risk=_risk(sig, list(HOT)))
    assert m["worst_case_gate"]["trading_verdict"] == "REFUSE"
    assert any(d.startswith("WORST_CASE_ABOVE_LIMIT") for d in m["disagreements"])
    mode, why = K.sim_owner_mode(m, {"ok": True})
    assert mode == "observe" and why.startswith("WORST CASE REFUSE")


def test_a_failed_live_read_never_trades_on_a_file():
    ok = {"status": "OK", "account_verified": True, "disagreements": [],
          "worst_case_gate": {"trading_verdict": "PASS"}}
    assert K.sim_owner_mode(ok, {"ok": True})[0] == config.SIM_OWNER_MODE
    mode, why = K.sim_owner_mode(ok, {"ok": False, "why": "HTTP 503"})
    assert mode == "observe" and why.startswith("LIVE BROKER READ FAILED")
    mode, why = K.sim_owner_mode({**ok, "account_verified": False}, {"ok": True})
    assert mode == "observe" and why.startswith("ACCOUNT UNVERIFIED")


def test_a_read_from_another_account_is_skipped(tmp_path):
    want = config.PC_PAPER_ACCOUNT_NUMBER
    mine, other = tmp_path / "a.json", tmp_path / "b.json"
    t = _now()
    mine.write_text(json.dumps({"t": (t - timedelta(days=1)).isoformat(), "equity": 1e6,
                                "account_number": want}), encoding="utf-8")
    other.write_text(json.dumps({"t": t.isoformat(), "equity": 2e6,
                                 "account_number": "SOMEONE_ELSE"}), encoding="utf-8")
    eq = REAL_PC_PAPER_EQUITY(files=[mine, other])
    assert eq["equity_usd"] == 1e6 and eq["account_verified"] is True
    assert eq["n_foreign_account_reads_skipped"] == 1
    m = DC.account_mandate(None, equity={**_fresh(), "account_number": "SOMEONE_ELSE"})
    assert any(d.startswith("ACCOUNT_MISMATCH") for d in m["disagreements"])


def test_positions_and_sleeve_basis_are_reconciled_against_the_broker():
    rows = [{"ticker": "AGENCY_BOOK:x", "instrument_kind": "book", "direction": "BUY",
             "position_budget": {"weight": 0.1, "dollars": 0.04 * EQ}}]
    eq = {**_fresh(positions=_held(list(CALM))), "cash_usd": 0.8 * EQ}
    res = DC.capital_resolution([], capital=EQ)                 # all core, no active
    r = DC.positions_reconciliation(rows, capital=EQ, equity=eq, resolution=res)
    kinds = {d.split(":")[0] for d in r["disagreements"]}
    assert kinds == {"SLEEVE_BASIS_DISAGREES", "POSITIONS_DISAGREE"}
    assert r["broker"]["cash_pct"] == pytest.approx(0.8)
    assert r["status"] == "UNRECONCILED"


def test_the_contract_states_the_broker_cash_beside_its_notional_core(monkeypatch):
    monkeypatch.setattr(DC, "pc_paper_equity",
                        lambda **_: {**_fresh(positions=_held(list(CALM))), "cash_usd": 0.8 * EQ})
    blob = DC.payload([], asof=_now().date(), capital=EQ)
    cr = blob["capital_resolution"]
    assert cr["broker_actual"]["cash_pct"] == pytest.approx(0.8)
    assert "80.00% cash" in cr["nothing_happened_is_not_allowed"]
    assert "same capital" not in cr["basis"]
    assert blob["mandate"]["status"] == "UNRECONCILED"
    assert blob["capital_reconciliation"]["capital_status"] == "OK"
    assert blob["capital_reconciliation"]["positions_status"] == "UNRECONCILED"


def test_the_order_path_sizes_exploit_down_and_blocks_an_over_limit_probe():
    from backend.services import pc_risk as PR
    k, limit = 3.0, 0.10
    w = {**{f"X{i}": 0.10 for i in range(8)}, **{f"H{i}": 0.02 for i in range(10)}}
    sleeve = {s: ("EXPLOIT" if s.startswith("X") else "PROBE") for s in w}
    cb = PR.cap_book(w, sleeve, {**HOT, **CALM}, k=k, limit=limit, fallback=0.05)
    assert cb["before_frac"] == pytest.approx(0.8 * 3 * 0.06 + 0.2 * 3 * 0.02)
    assert cb["after_frac"] == pytest.approx(limit) and cb["block"] is None
    assert all(cb["weights"][f"H{i}"] == 0.02 for i in range(10))     # PROBE untouched
    assert cb["weights"]["X0"] < 0.10
    hot_probe = PR.cap_book({f"H{i}": 0.02 for i in range(10)}, {}, {f"H{i}": 0.30 for i in range(10)},
                            k=k, limit=limit, fallback=0.05)
    assert hot_probe["block"] and hot_probe["block"].startswith("WORST CASE REFUSE")


def test_the_limits_are_not_moved_by_the_mandate():
    before = (config.PROBE_MAX_WEIGHT, config.PROBE_GROSS_CAP, config.ER_EXPLOIT_MAX_WEIGHT,
              config.PC_WORST_CASE_MAX_FRAC_OF_EQUITY)
    DC.account_mandate(None, equity=_fresh())
    assert before == (config.PROBE_MAX_WEIGHT, config.PROBE_GROSS_CAP,
                      config.ER_EXPLOIT_MAX_WEIGHT, config.PC_WORST_CASE_MAX_FRAC_OF_EQUITY)


# ───────────────────────── 3. the scaled view ─────────────────────────────────

def test_scaled_view_arithmetic_and_the_names_it_cannot_execute():
    pos = [{"ticker": "AAA", "weight": 0.02, "price": 457.45},   # $800 -> 1 share
           {"ticker": "BBB", "weight": 0.02, "price": 1200.0},   # $800 < 1 share
           {"ticker": "CCC", "weight": 0.05, "price": 30.0},     # $2,000 -> 66 shares
           {"ticker": "DDD", "weight": 0.01, "price": None}]     # cannot determine
    level = 40_000.0
    v = DC.scaled_view(pos, level_usd=level, source_capital_usd=EQ, label="t")
    rows = {r["ticker"]: r for r in v["rows"]}
    assert rows["AAA"]["shares"] == 1 and rows["AAA"]["notional_usd"] == pytest.approx(457.45)
    assert rows["CCC"]["shares"] == 66 and rows["CCC"]["notional_usd"] == pytest.approx(1980.0)
    assert rows["BBB"]["shares"] == 0 and rows["BBB"]["executable"] is False
    assert [x["ticker"] for x in v["not_executable"]] == ["BBB"]
    assert v["not_executable"][0]["one_share_usd"] == 1200.0
    assert "1 share $1,200.00 > 2.00% x $40,000 = $800.00" in v["not_executable"][0]["why"]
    assert v["no_price"] == ["DDD"] and rows["DDD"]["executable"] is None
    assert v["n_executable"] == 2 and v["n_names"] == 4
    assert v["executable_usd"] == pytest.approx(457.45 + 1980.0)
    assert v["target_gross_over_level"] == pytest.approx(0.10)
    assert v["cash_residual_usd"] == pytest.approx(0.10 * level - 457.45 - 1980.0)
    assert v["scale"] == pytest.approx(level / EQ)
    assert v["places_orders"] is False
    assert "NOT executable: BBB" in v["line"] and "places no order" in v["line"]


def test_every_contract_carries_scaled_views_at_every_level(monkeypatch):
    held = [{"symbol": "TSM", "market_value": 20_000.0, "current_price": 457.45, "qty": 44},
            {"symbol": "BIG", "market_value": 20_000.0, "current_price": 2_000.0, "qty": 10}]
    monkeypatch.setattr(DC, "pc_paper_equity",
                        lambda **_: _fresh(1_000_000.0, positions=held))
    blob = DC.payload([], asof=_now().date(), capital=1_000_000.0)
    sv = blob["scaled_views"]
    assert sv["places_orders"] is False
    views = sv["pc_paper_held"]["views"]
    assert set(views) == {f"{float(c):.0f}" for c in config.IC_CAPITAL_LEVELS}
    at40 = views["40000"]
    # 2% of $40,000 = $800: one TSM share fits, one BIG share ($2,000) does not
    assert [x["ticker"] for x in at40["not_executable"]] == ["BIG"]
    assert views["1000000"]["n_executable"] == 2


# ───────────────────────── 4. the sim owner ──────────────────────────────────

def _et_on_a_weekday(hh: int, mm: int = 0) -> datetime:
    """A UTC instant at hh:mm US/Eastern on the next weekday from today."""
    from zoneinfo import ZoneInfo
    d = date.today()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, hh, mm,
                    tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)


IDLE = {"state": "COMPLETED", "session": {"id": "old", "state": "COMPLETED",
                                          "end_reason": "requested duration elapsed"}}
OK_MANDATE = {"status": "OK", "disagreements": [],
              "worst_case_gate": {"verdict": "PASS", "line": "WORST CASE PASS"}}


def test_window_and_duration_are_computed_in_eastern_time():
    w = K.sim_window(_et_on_a_weekday(10, 0), session_day=True)
    assert w["in_window"] and w["hours"] == 8            # 10:00 -> 17:00 ET needs 7 h
    assert K.sim_window(_et_on_a_weekday(12, 0), session_day=True)["hours"] == 6
    assert not K.sim_window(_et_on_a_weekday(8, 0), session_day=True)["in_window"]
    assert not K.sim_window(_et_on_a_weekday(15, 45), session_day=True)["in_window"]
    assert not K.sim_window(_et_on_a_weekday(11, 0), session_day=False)["in_window"]


def _owner(folder: Path, *, now, sim=IDLE, mandate=OK_MANDATE, start=None, stop=False,
           session_day=True, disk=(True, "")):
    folder.mkdir(parents=True, exist_ok=True)
    calls: list = []

    def _start(**kw):
        calls.append(kw)
        if start:
            return start(**kw)
        return {"id": "new1", "pid": 4242, "planned_end": "x"}

    stop_path = folder / "OWNER_STOP"
    if stop:
        stop_path.write_text("x", encoding="utf-8")
    log = folder / "owner.jsonl"
    row = K.ensure_sim(now_utc=now, status=lambda: sim, start=_start,
                       session_day=lambda d: session_day,
                       broker_read=lambda: {"ok": True, "equity": EQ},
                       mandate=lambda: mandate, disk=lambda: disk,
                       stop_path=stop_path, log_path=log)
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    return row, rows, calls


def test_the_owner_starts_a_trading_session_on_an_ok_mandate(tmp_path):
    row, rows, calls = _owner(tmp_path, now=_et_on_a_weekday(10, 0))
    assert row["action"] == "started" and row["session"] == "new1"
    assert calls == [{"hours": 8, "mode": config.SIM_OWNER_MODE}]
    assert row["trade_refused"] is None and rows[-1]["run_id"] == row["run_id"]


def test_an_unreconciled_mandate_starts_observe_and_names_why(tmp_path):
    m = {"status": "UNRECONCILED", "disagreements": ["BROKER_EQUITY_STALE: x"],
         "worst_case_gate": {"verdict": "PASS"}}
    row, _, calls = _owner(tmp_path, now=_et_on_a_weekday(10, 0), mandate=m)
    assert calls[0]["mode"] == "observe"
    assert row["trade_refused"] == "MANDATE UNRECONCILED: BROKER_EQUITY_STALE"


def test_a_refused_start_is_a_receipt_not_a_silence(tmp_path):
    def boom(**_):
        raise RuntimeError("a simulation is already RUNNING")
    row, rows, _ = _owner(tmp_path, now=_et_on_a_weekday(10, 0), start=boom)
    assert row["action"] == "refused" and "already RUNNING" in row["why"]
    assert rows and rows[-1]["action"] == "refused" and rows[-1]["run_id"]


def test_outside_the_window_pause_and_disk_each_write_a_reason(tmp_path):
    row, _, calls = _owner(tmp_path / "a", now=_et_on_a_weekday(7, 0))
    assert row["action"] == "outside_window" and "before the first start" in row["why"]
    assert not calls
    row, _, calls = _owner(tmp_path / "b", now=_et_on_a_weekday(10, 0), stop=True)
    assert row["action"] == "paused" and not calls
    row, _, calls = _owner(tmp_path / "c", now=_et_on_a_weekday(10, 0), disk=(False, "full"))
    assert row["action"] == "refused" and row["why"].startswith("REFUSED_DISK") and not calls


def test_a_session_already_running_is_left_alone(tmp_path):
    sim = {"state": "RUNNING", "session": {"id": "live", "pid": 1, "mode": "paper_profit"}}
    row, _, calls = _owner(tmp_path, now=_et_on_a_weekday(10, 0), sim=sim)
    assert row["action"] == "alive" and not calls


def test_an_operator_stop_today_is_not_overridden(tmp_path):
    now = _et_on_a_weekday(11, 0)
    sim = {"state": "STOPPED", "session": {"id": "s", "state": "STOPPED",
                                           "end_reason": "stop requested",
                                           "ended": (now - timedelta(minutes=30)).isoformat()}}
    row, _, calls = _owner(tmp_path, now=now, sim=sim)
    assert row["action"] == "stopped_by_operator" and not calls


def test_the_owner_task_is_in_the_registration():
    ps = K.registration_ps()
    assert K.TASK_SIM in ps and "scripts.task_keeper sim" in ps
    assert "-Minutes 30" in ps


# ───────────────────────── 5. health reads the owner ──────────────────────────

def _ctx(tmp_path: Path, now: datetime) -> SH.ProbeCtx:
    od = tmp_path / "optimus"
    (od / "sim").mkdir(parents=True, exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=now, repo=tmp_path, allow_proc=False)


def _in_session_now() -> datetime:
    last = SH.last_closed_session(_now())
    return datetime(last.year, last.month, last.day, 17, 0, tzinfo=timezone.utc)


def _session_file(ctx, now):
    (ctx.optimus_dir / "sim" / "session.json").write_text(json.dumps(
        {"id": "s1", "state": "COMPLETED", "ended": (now - timedelta(hours=20)).isoformat()}),
        encoding="utf-8")


def _owner_row(ctx, at, **row):
    with (ctx.optimus_dir / "sim" / "owner.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"utc": at.isoformat(timespec="seconds"), "run_id": "r1",
                             **row}) + "\n")


def test_health_reports_a_fresh_owner_refusal_as_refused_not_dead(tmp_path):
    now = _in_session_now()
    ctx = _ctx(tmp_path, now)
    _session_file(ctx, now)
    _owner_row(ctx, now - timedelta(minutes=10), job="sim", action="refused",
               why="REFUSED_DISK: full")
    r = SH.p_sim_session(ctx)
    assert r.verdict == "REFUSED" and "REFUSED_DISK" in r.detail
    assert SH.exit_code([{"verdict": "REFUSED"}]) == 2


def test_health_without_an_owner_receipt_is_dead(tmp_path):
    now = _in_session_now()
    ctx = _ctx(tmp_path, now)
    _session_file(ctx, now)
    assert SH.p_sim_session(ctx).verdict == "DEAD"
    _owner_row(ctx, now - timedelta(hours=5), job="sim", action="refused", why="old")
    r = SH.p_sim_session(ctx)
    assert r.verdict == "DEAD" and "not written a receipt" in r.detail


def test_health_an_owner_start_whose_session_is_gone_is_dead(tmp_path):
    now = _in_session_now()
    ctx = _ctx(tmp_path, now)
    _session_file(ctx, now)
    _owner_row(ctx, now - timedelta(minutes=5), job="sim", action="started", session="s9")
    assert SH.p_sim_session(ctx).verdict == "DEAD"


def test_health_the_owners_pause_is_stopped_by_operator(tmp_path):
    now = _in_session_now()
    ctx = _ctx(tmp_path, now)
    _session_file(ctx, now)
    _owner_row(ctx, now - timedelta(minutes=5), job="sim", action="paused", why="OWNER_STOP")
    assert SH.p_sim_session(ctx).verdict == "STOPPED_BY_OPERATOR"


# ───────────────────────── review C2 F3 / F6 / F7 / F8 ───────────────────────

def test_the_owner_pause_also_stops_a_running_session(tmp_path):
    sim = {"state": "RUNNING", "session": {"id": "live", "pid": 1, "mode": "paper_profit"}}
    asked: list = []
    (tmp_path / "OWNER_STOP").write_text("x", encoding="utf-8")
    row = K.ensure_sim(now_utc=_et_on_a_weekday(10, 0), status=lambda: sim,
                       start=lambda **kw: pytest.fail("must not start"),
                       session_day=lambda d: True, stop_path=tmp_path / "OWNER_STOP",
                       log_path=tmp_path / "owner.jsonl",
                       stop_running=lambda **kw: asked.append(kw) or {"ok": True})
    assert row["action"] == "paused" and asked == [{"reason": "OWNER_STOP"}]
    assert row["stop_requested"] == {"ok": True}


def test_a_concurrent_start_is_refused_by_the_lock(tmp_path, monkeypatch):
    from backend.services import sim_session as SS
    monkeypatch.setattr(SS, "STATE_DIR", tmp_path)
    monkeypatch.setattr(SS, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(SS, "STOP_FLAG", tmp_path / "STOP_REQUESTED")
    monkeypatch.setattr(SS, "HISTORY_PATH", tmp_path / "sessions.jsonl")
    monkeypatch.setattr(SS, "START_LOCK", tmp_path / "start.lock")
    (tmp_path / "start.lock").write_text("{}", encoding="utf-8")       # a starter in flight
    with pytest.raises(SS.SimRefused, match="another start is in progress"):
        SS.start(hours=6, mode="observe", launcher=lambda s: 4242)
    (tmp_path / "start.lock").unlink()
    first = SS.start(hours=6, mode="observe", launcher=lambda s: None)  # pid not yet known
    assert SS.status()["state"] == "STARTING"
    with pytest.raises(SS.SimRefused):
        SS.start(hours=6, mode="observe", launcher=lambda s: 4243)
    assert not (tmp_path / "start.lock").exists() and first["id"]


def test_health_says_observe_only_and_counts_orders(tmp_path):
    now = _now()
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "optimus", now=now, repo=tmp_path, allow_proc=False,
                      pid_cmdline=lambda p: "python -m scripts.sim_run --session s1")
    (ctx.optimus_dir / "sim").mkdir(parents=True)
    (ctx.optimus_dir / "sim" / "session.json").write_text(json.dumps(
        {"id": "s1", "state": "RUNNING", "pid": 77, "mode": "observe",
         "heartbeat": now.isoformat()}), encoding="utf-8")
    day = ctx.optimus_dir / "pc_book" / now.date().isoformat()
    day.mkdir(parents=True)
    (day / "decisions.jsonl").write_text(json.dumps(
        {"t": now.isoformat(), "sent": [{"status": "accepted"}, {"status": "skipped"}]}) + "\n",
        encoding="utf-8")
    r = SH.p_sim_session(ctx)
    assert "orders sent 1" in r.detail
    assert r.verdict == "ALIVE_OBSERVE_ONLY"


def test_the_window_holds_across_the_dst_change():
    """2026-11-02 is the first Monday on EST: 09:00 ET is 14:00 UTC (not 13:00)."""
    from zoneinfo import ZoneInfo
    est_monday = datetime(2026, 11, 2, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    assert est_monday.astimezone(timezone.utc).hour == 14
    w = K.sim_window(est_monday.astimezone(timezone.utc), session_day=True)
    assert w["in_window"] and w["now_et"].endswith("-05:00")
    early = (est_monday - timedelta(minutes=30)).astimezone(timezone.utc)
    assert not K.sim_window(early, session_day=True)["in_window"]
