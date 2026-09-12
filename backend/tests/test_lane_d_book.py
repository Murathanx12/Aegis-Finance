"""T4 — lane D's day-trading book (D1) and the Monday-night protocol (D5).

Two things are pinned here that nothing else would catch: the book's declared
worst case in dollars (session protocol rule 4, and the 28 Aug lesson that a
wider stop on uncapped gross is a bigger loss), and the night loop's five
refusals — the power plan, the STOP file, the two clocks, the receipt that is
written even when there was nothing to do, and the absence of any order path.
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.tests.test_desktop_control_surface import executable_source
from scripts import monday_night as MN
from scripts import seed_lane_d_book as SD

HKT = ZoneInfo("Asia/Hong_Kong")
REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# D1 — the contract


def test_the_book_is_a_thirty_minute_book_with_a_named_placeholder_signal():
    s = SD.lane_d_book()
    assert s.signal.name == "native_stamped_headline_in_first_hour"
    assert s.engine_params["intraday"]["bar_minutes"] == 30
    assert s.engine_params["intraday"]["entry_window_et"] == ["09:30", "10:30"]
    assert "PLACEHOLDER" in s.signal.note and "L2" in s.signal.note


def test_the_book_is_forced_flat_at_the_close():
    s = SD.lane_d_book()
    assert s.engine_params["intraday"]["hold_rule"] == "session_end"
    assert s.engine_params["intraday"]["forced_flat_at_close"] is True


def test_the_signal_is_one_book_cadence_can_reach():
    from backend.services import book_signals as BS
    assert SD.lane_d_book().signal.name in BS.REGISTRY


def test_k_is_twelve_equal_weight():
    c = SD.lane_d_book().construction
    assert c.k == 12 and c.weighting == "ew"


def test_the_daily_loss_limit_is_printed_as_n_times_notional_times_stop():
    s = SD.lane_d_book()
    wc = SD.worst_case_print(s)
    # 12 names x 8.33% x 2% stop = 2.00% of equity, gross 1.00x
    assert wc["n_names"] == 12
    assert wc["worst_case_pct_of_equity"] == pytest.approx(0.02, abs=1e-4)
    assert wc["gross_over_equity"] == pytest.approx(1.0, abs=1e-4)
    assert wc["gross_within_cap"] is True
    assert "x" in wc["daily_loss_limit"] and "%" in wc["daily_loss_limit"]


def test_the_gross_line_is_printed_beside_the_stop_line():
    """28 Aug: twelve names x 25% was 300% gross, and widening the stop turned
    -9% into -24%. Neither number means anything without the other."""
    wc = SD.worst_case_print(SD.lane_d_book())
    assert "gross" in wc["verdict"]
    assert wc["stop_pct"] is not None


def test_the_cost_model_is_the_retail_assumption_and_is_labelled_pending():
    s = SD.lane_d_book()
    assert s.costs.transaction_cost_bps == 25.0
    assert s.engine_params["cost_curve"] == "retail_paper_pending_D2"
    assert "pending_D2" in SD.COST_CURVE


def test_periods_per_year_is_recalibrated_off_the_monthly_default():
    assert SD.lane_d_book().objective.periods_per_year == 252


def test_the_origin_text_is_murats_sentence_verbatim():
    assert "1% return every day" in SD.ORIGIN_TEXT
    assert "leave the PC open on Monday nights" in SD.ORIGIN_TEXT
    # and the arithmetic travels with it rather than living in a slide
    assert "1,127%/yr" in SD.ORIGIN_TEXT


def test_the_book_declares_the_population_prior_in_its_loss_budget():
    lb = SD.lane_d_book().loss_budget
    assert lb.expected_losers > lb.positions_judged / 2
    assert "Taiwanese" in lb.note or "Brazilian" in lb.note


def test_the_contract_is_a_product_experiment_with_no_order_path():
    s = SD.lane_d_book()
    assert s.licence.value == "PRODUCT_EXPERIMENT"
    assert s.engine_params["no_order_path"] is True


def test_the_thirty_minute_cadence_earns_the_overnight_twin():
    from backend.services import paper_books as PB
    from backend.tests.book_helpers import synthetic_bars

    twins = PB.make_twins(SD.lane_d_book(), cadence="30m",
                          bars=synthetic_bars(), asof=date.today())
    kinds = {t.strategy.engine_params["twin"]["kind"] for t in twins}
    assert "overnight_only" in kinds
    assert "random_universe" in kinds          # = random entry, same clock


# --------------------------------------------------------------------------
# D5 — the Monday-night protocol


def test_the_window_is_the_us_session_in_both_clocks():
    w = MN.window_in_et(date(2026, 9, 14))          # a Monday
    assert w["start_hkt"].startswith("2026-09-14T21:30")
    assert w["end_hkt"].startswith("2026-09-15T04:00")
    # 21:30 HKT on a September Monday is 09:30 ET, the cash open
    assert "T09:30" in w["start_et"]
    assert "T16:00" in w["end_et"]


def test_the_et_mapping_is_recomputed_and_not_hard_coded():
    """US DST moves the window by an hour; a constant that was right in
    September is wrong in December."""
    sep = MN.window_in_et(date(2026, 9, 14))
    dec = MN.window_in_et(date(2026, 12, 14))
    assert sep["start_et"][:16] != dec["start_et"][:16]
    assert "T09:30" in sep["start_et"]
    assert "T08:30" in dec["start_et"]              # EST, one hour earlier


def test_inside_window_spans_midnight():
    assert MN.inside_window(datetime(2026, 9, 14, 22, 0, tzinfo=HKT))
    assert MN.inside_window(datetime(2026, 9, 15, 3, 59, tzinfo=HKT))
    assert not MN.inside_window(datetime(2026, 9, 15, 4, 1, tzinfo=HKT))
    assert not MN.inside_window(datetime(2026, 9, 14, 12, 0, tzinfo=HKT))


def test_a_two_pass_dry_run_writes_one_receipt_per_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")
    slept: list = []
    s = MN.run(passes=2, interval_s=1, dry_run=True, sleeper=slept.append)
    assert s["n_passes"] == 2
    assert s["stopped_by"] == "pass_count"
    files = sorted(p.name for p in tmp_path.glob("pass_*.json"))
    assert len(files) == 2
    assert len(sorted(tmp_path.glob("session_*.json"))) == 1
    # it slept BETWEEN the passes and not after the last one
    assert slept == [1.0]


def test_a_pass_with_nothing_to_do_still_writes_a_receipt(tmp_path, monkeypatch):
    """Invariant 15: a silent pass and a dead scheduler are the same
    observation unless one of them leaves a file."""
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")
    MN.run(passes=1, interval_s=0, dry_run=True, sleeper=lambda s: None)
    blob = json.loads(next(tmp_path.glob("pass_*.json")).read_text(encoding="utf-8"))
    assert blob["nothing_to_do"] is True
    assert blob["reason"]
    assert blob["pid"]


def test_every_pass_receipt_carries_both_clocks(tmp_path, monkeypatch):
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")
    MN.run(passes=1, interval_s=0, dry_run=True, sleeper=lambda s: None)
    blob = json.loads(next(tmp_path.glob("pass_*.json")).read_text(encoding="utf-8"))
    for k in ("ran_at_utc", "ran_at_hkt", "ran_at_et"):
        assert blob[k]


def test_a_stop_file_ends_the_loop_between_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")
    (tmp_path / MN.STOP_FILENAME).write_text("stop", encoding="utf-8")
    s = MN.run(passes=5, interval_s=0, dry_run=True, sleeper=lambda x: None)
    assert s["stopped_by"] == "stop_file"
    assert s["n_passes"] == 0


def test_a_stop_file_written_mid_run_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")

    def sleeper(_s):
        (tmp_path / MN.STOP_FILENAME).write_text("stop", encoding="utf-8")

    s = MN.run(passes=5, interval_s=0, dry_run=True, sleeper=sleeper)
    assert s["stopped_by"] == "stop_file"
    assert s["n_passes"] == 1


def test_the_loop_refuses_when_the_power_plan_allows_sleep(tmp_path, monkeypatch):
    from scripts import night_factory as NF
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setattr(NF, "refuse_if_the_machine_may_sleep",
                        lambda: "REFUSED: the active power plan sleeps after 1800s")
    s = MN.run(passes=2, interval_s=0, dry_run=True, sleeper=lambda x: None)
    assert s["stopped_by"] == "power_plan"
    assert s["n_passes"] == 0
    assert "REFUSED" in s["refused"]


def test_the_power_check_is_the_factory_s_own_and_not_a_second_copy():
    code = executable_source(REPO / "scripts" / "monday_night.py")
    assert "NF.refuse_if_the_machine_may_sleep()" in code
    assert "powercfg" not in code          # no re-implementation


def test_the_gpu_line_is_recorded_on_the_session(tmp_path, monkeypatch):
    from scripts import night_factory as NF
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setattr(NF, "refuse_if_the_machine_may_sleep", lambda: None)
    monkeypatch.setattr(NF, "gpu_line", lambda: "GPU: a test card | 1 MiB")
    s = MN.run(passes=1, interval_s=0, dry_run=True, sleeper=lambda x: None)
    assert s["gpu"] == "GPU: a test card | 1 MiB"


def test_the_session_receipt_writes_down_its_own_pid_before_any_work(tmp_path,
                                                                     monkeypatch):
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")
    s = MN.run(passes=1, interval_s=0, dry_run=True, sleeper=lambda x: None)
    assert isinstance(s["pid"], int) and s["pid"] > 0
    assert "taskkill" in s["pid_note"]          # the rule, quoted on the row


def test_the_loop_stops_when_the_window_closes(tmp_path, monkeypatch):
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setenv("AEGIS_NIGHT_ALLOW_SLEEP", "1")
    noon = datetime(2026, 9, 14, 12, 0, tzinfo=HKT)
    s = MN.run(passes=5, interval_s=0, dry_run=False, write_receipts=False,
               now_fn=lambda: noon, sleeper=lambda x: None)
    assert s["stopped_by"] == "window_closed"
    assert s["n_passes"] == 0


# --------------------------------------------------------------------------
# no order path — read the AST, never grep, because this file names the words


BROKER_MODULES = ("alpaca", "alpaca_trade_api", "ib_insync", "tradeapi")
BROKER_CALLS = ("submit_order", "place_order", "create_order")


def test_the_monday_night_loop_imports_no_broker_and_places_no_order():
    tree = ast.parse((REPO / "scripts" / "monday_night.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0].lower() for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0].lower())
    assert not (imported & set(BROKER_MODULES))
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    calls |= {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not (calls & set(BROKER_CALLS))


def test_the_lane_d_seeder_imports_no_broker_either():
    """AST, not grep: `alpaca_benzinga_news` is a NEWS CORPUS directory and a
    substring guard cannot tell it from the broker SDK. The first run of this
    test failed on exactly that, which is the CLAUDE.md rule-10 shape."""
    tree = ast.parse((REPO / "scripts" / "seed_lane_d_book.py")
                     .read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0].lower() for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0].lower())
    assert not (imported & set(BROKER_MODULES))
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    calls |= {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not (calls & set(BROKER_CALLS))


def test_neither_module_reaches_an_order_path_through_the_control_plane():
    """`create-from-contract` is the only route either module calls."""
    for name in ("monday_night.py", "seed_lane_d_book.py"):
        code = executable_source(REPO / "scripts" / name)
        routes = [ln for ln in code.splitlines() if "/api/" in ln]
        assert all("books/create-from-contract" in ln for ln in routes), name


def test_the_interval_default_is_thirty_minutes():
    assert MN.PASS_INTERVAL_S == 30 * 60
    assert timedelta(seconds=MN.PASS_INTERVAL_S) == timedelta(minutes=30)


def test_the_pass_receipt_says_the_marking_granularity_is_not_intraday(tmp_path,
                                                                       monkeypatch):
    """A 30-minute book graded from daily closes is not a 30-minute book's
    result, and the row has to say so."""
    from backend.services import book_cadence as BC
    monkeypatch.setattr(MN, "receipt_dir", lambda: tmp_path)
    monkeypatch.setattr(BC, "run_pass",
                        lambda cadence, **kw: {"n_marked": 0, "n_refused": 0,
                                               "nothing_to_do": True})
    p = MN.one_pass(dry_run=False, now=datetime.now(timezone.utc), index=0)
    assert p["intraday_bars_available"] is False
    assert p["granularity"] == "daily_close"
