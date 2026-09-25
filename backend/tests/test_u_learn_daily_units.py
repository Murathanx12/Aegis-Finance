"""The learn rota's once-per-day module units (2026-09-26).

Murat: "maximise backtests ... that is your ultimate purpose on this nightly
simulation." The backtest factory and the rule distillation run as modules,
once per UTC day, out of process; a failed run is DEGRADED on the receipt and
is retried next cycle; a successful run is not repeated the same day.
"""
from datetime import date
from types import SimpleNamespace

import scripts.sim_run as SR


def _runner(rc: int):
    calls = []

    def run(argv):
        calls.append(argv)
        return SimpleNamespace(returncode=rc, stdout="ran", stderr="")
    run.calls = calls
    return run


def test_rota_carries_both_daily_units():
    assert "backtest_factory" in SR._DAILY_MODULE_UNITS and "distil" in SR._DAILY_MODULE_UNITS
    assert SR._DAILY_MODULE_UNITS["backtest_factory"][:2] == ["-m", "scripts.night_backtest_factory"]


def test_a_unit_runs_once_per_day_and_is_skipped_after_success(tmp_path):
    run = _runner(0)
    r1 = SR._daily_module_unit("backtest_factory", tmp_path, today=date(2026, 9, 26), runner=run)
    assert r1["rc"] == 0 and r1["status"] == "ok" and r1["day"] == "2026-09-26"
    r2 = SR._daily_module_unit("backtest_factory", tmp_path, today=date(2026, 9, 26), runner=run)
    assert "already ran today" in r2["skipped"]
    assert len(run.calls) == 1 and run.calls[0][1:] == ["-m", "scripts.night_backtest_factory"]
    r3 = SR._daily_module_unit("backtest_factory", tmp_path, today=date(2026, 9, 27), runner=run)
    assert r3["rc"] == 0 and len(run.calls) == 2


def test_a_failed_unit_is_degraded_and_retried(tmp_path):
    bad = _runner(3)
    r1 = SR._daily_module_unit("backtest_factory", tmp_path, today=date(2026, 9, 26), runner=bad)
    assert r1["status"].startswith("DEGRADED")
    r2 = SR._daily_module_unit("backtest_factory", tmp_path, today=date(2026, 9, 26), runner=bad)
    assert r2["status"].startswith("DEGRADED") and len(bad.calls) == 2
