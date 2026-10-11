"""Synthetic target/provenance guards only, no numerical model/data job."""
import copy
import json
import os
from pathlib import Path
import subprocess

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from backend.services import beta_v1_numerical as numerical
from backend.services import beta_v1_policy as policy
from backend.services import xs_ranker as xr
from scripts import beta_v1_numerical_receipt as runner


def fixture_panel():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-01-02", "2025-03-31").tz_localize(None)
    rows = []
    for symbol, rate in (("AAA", .01), ("BBB", .002)):
        for i, date in enumerate(sessions):
            rows.append({"symbol": symbol, "date": date, "close": 10*(1+rate)**i,
                "open": 5*(1+rate)**i, "eligible": True, "median_dollar_vol": 30_000_000})
    return pd.DataFrame(rows)


def test_new_target_close_not_original_open_and_exact_21_sessions():
    panel = fixture_panel()
    own, _ = numerical.close_target(panel)
    legacy = xr.build_target(panel)
    first = own.iloc[0]
    assert first["fwd_ret"] == pytest.approx(1.01**21-1)
    assert legacy.iloc[0]["fwd_ret"] == pytest.approx(2*1.01**21-1)
    assert first["fwd_ret"] != legacy.iloc[0]["fwd_ret"]
    assert policy._session_count(pd.Timestamp(first["label_start_at"]), pd.Timestamp(first["label_end_at"])) == 21
    assert numerical.TARGET in numerical.specification()["target"]


def test_missing_xnys_session_refuses_target_and_whole_benchmark_not_zero():
    panel = fixture_panel()
    panel = panel.drop(panel[(panel.symbol == "AAA")].index[10])
    own, audit = numerical.close_target(panel)
    first = own.iloc[0]
    assert pd.isna(first["fwd_ret"]) and pd.isna(first["y"])
    bbb = own[(own.symbol == "BBB") & (own.date == first.date)].iloc[0]
    assert np.isfinite(bbb.fwd_ret) and pd.isna(bbb.bench_fwd_ret)
    assert audit["benchmark_incomplete_dates"] > 0


def test_exact_actual_label_end_purges_before_test_formation():
    panel, _ = numerical.close_target(fixture_panel())
    train_end = pd.Timestamp("2025-01-15")
    start, end = pd.Timestamp("2025-02-03"), pd.Timestamp("2025-02-10")
    train, test, receipt = numerical.fold_rows(panel, train_end, start, end)
    assert not test.empty and receipt["purged_by_actual_label_end"] > 0
    assert all(pd.Timestamp(v) <= pd.Timestamp(receipt["first_test_formation_at"]) for v in train.label_end_at)


def test_production_cutoff_mature_labels_only_and_no_date_approximation():
    panel, _ = numerical.close_target(fixture_panel())
    cutoff = "2025-02-07T21:00:00Z"
    selected = numerical.mature_rows(panel, cutoff)
    assert len(selected) and all(pd.Timestamp(v) <= pd.Timestamp(cutoff) for v in selected.label_end_at)
    with pytest.raises(ValueError):
        numerical.mature_rows(panel, "2025-02-07")


def provenance():
    return {"dataset_hash": "a"*64, "feature_hash": "b"*64, "feature_values_hash": "b"*64, "parameter_hash": "c"*64,
        "model_serialized_sha256": "d"*64, "calibration_hash": "e"*64, "code_hash": "f"*64,
        "latest_train_label_end": "2026-10-09T20:00:00Z", "latest_calibration_label_end": "2026-10-09T20:00:00Z",
        "return_cost_basis": "GROSS_NATIVE_PRICE_CLOSE_EXCESS", "target": numerical.TARGET,
        "objective_version": numerical.OBJECTIVE}


def ranking():
    return pd.DataFrame([{"symbol": "AAA", "date": pd.Timestamp("2026-10-09"), "sessions_seen": 252,
        "calibration_measured": True, "expected_relative_return_21d": .03,
        "expected_relative_return_21d_net": .029}])


def test_current_receipt_not_backdated_and_future_exact_close_contract_admitted():
    result = numerical.normalize_current(ranking(), receipt_at="2026-10-11T08:00:00Z",
        feature_asof="2026-10-09", provenance=provenance())
    row = result["qualified_return_records"][0]
    assert row["forecast_at"] == "2026-10-11T08:00:00+00:00"
    assert row["label_start_at"] == "2026-10-12T20:00:00+00:00"
    assert row["x"] == .03 and row["horizon"] == 21
    admitted, rejected, _ = policy._admit([row], result["qualified_return_qualifications"],
        definitions=result["qualified_return_definitions"], task="expected_excess_return", horizon=21,
        objective_version=numerical.OBJECTIVE, cutoff=pd.Timestamp(result["asof_utc"]), grade=False)
    assert len(admitted) == 1 and not rejected
    clone = numerical.normalize_current(ranking(), receipt_at="2026-10-11T08:00:00Z",
        feature_asof="2026-10-09", provenance=copy.deepcopy(provenance()))
    assert clone == result


@pytest.mark.parametrize("change", [{"return_cost_basis": "NET_EXISTING_LIQUIDITY_CURVE"},
    {"model_serialized_sha256": "unknown"}, {"target": "NEXT_OPEN_TO_T_PLUS_22_CLOSE"},
    {"latest_train_label_end": "2026-10-12T20:00:00Z"},
    {"latest_calibration_label_end": "2026-10-12T20:00:00Z"}])
def test_net_legacy_target_missing_or_future_provenance_refuses(change):
    with pytest.raises((ValueError, numerical.NumericalRefused)):
        numerical.normalize_current(ranking(), receipt_at="2026-10-11T08:00:00Z",
            feature_asof="2026-10-09", provenance={**provenance(), **change})


def test_last_closed_feature_session_and_real_history_required():
    with pytest.raises(numerical.NumericalRefused):
        numerical.normalize_current(ranking(), receipt_at="2026-10-12T21:00:00Z",
            feature_asof="2026-10-09", provenance=provenance())
    row = ranking()
    row["sessions_seen"] = 20
    result = numerical.normalize_current(row, receipt_at="2026-10-11T08:00:00Z",
        feature_asof="2026-10-09", provenance=provenance())
    assert not result["qualified_return_records"] and result["unavailable"]


def test_original_features_params_and_calibration_gates_preserved():
    spec = numerical.specification()
    assert spec["features"] == list(xr.FEATURES) and len(spec["features"]) == 24
    assert spec["parameters"] == xr.LGB_PARAMS and spec["parameters"]["n_estimators"] == 350
    assert spec["min_train_rows"] == 40_000 and spec["min_decision_dates"] == 120
    assert spec["min_decile_rows"] == 500 and spec["min_decile_month_blocks"] == 6
    assert spec["cpu_threads"] == 2


def test_current_unmeasured_decile_not_zero_or_net_fallback():
    row = ranking()
    row["calibration_measured"] = False
    result = numerical.normalize_current(row, receipt_at="2026-10-11T08:00:00Z",
        feature_asof="2026-10-09", provenance=provenance())
    assert not result["qualified_return_records"] and result["unavailable"]


def test_resource_cap_fail_loud():
    budget = numerical.Budget(max_rows=1)
    with pytest.raises(numerical.NumericalRefused):
        budget.check("fixture", rows=2)


def price_fixture():
    panel = fixture_panel().drop(columns=["eligible", "median_dollar_vol"])
    panel["high"] = panel["close"]*1.01
    panel["low"] = panel["close"]*.99
    panel["volume"] = 3_000_000
    panel["_src"] = "bars_delisted"
    return panel


def test_price_duplicate_conflict_refuses_instead_of_first_source_wins():
    bars = price_fixture()
    changed = bars.iloc[[0]].copy()
    changed["close"] = 99
    with pytest.raises(numerical.NumericalRefused, match="conflicting duplicate"):
        numerical.prepare_prices(pd.concat([bars, changed]), registrants={"by_ticker": {},
            "cik_first": pd.Series(dtype="datetime64[ns]"), "sources": ["fixture"]})


def test_existing_stitch_guard_receives_explicit_metadata_and_gaps_split(monkeypatch):
    bars = price_fixture()
    bars = bars.drop(bars[(bars.symbol == "AAA")].index[10])
    registrants = {"by_ticker": {"AAA": {"cik": 123, "first_filed": pd.Timestamp("2020-01-01"), "source": "fixture"}},
        "cik_first": pd.Series(dtype="datetime64[ns]"), "sources": ["fixture"]}
    original = numerical.st.split_stitched
    calls = []
    def guarded(frame, **kwargs):
        calls.append(kwargs["regs"])
        return original(frame, **kwargs)
    monkeypatch.setattr(numerical.st, "split_stitched", guarded)
    monkeypatch.setattr(numerical.st, "registrants", lambda *a, **k: pytest.fail("implicit metadata read"))
    prepared, audit = numerical.prepare_prices(bars, registrants=registrants)
    assert calls == [registrants] and audit["additional_gap_segments"] == 1
    assert "AAA#GAP1" in prepared.symbol.values and "AAA" in prepared.symbol.values
    assert audit["stitch"]["defect_screen"]


def test_insufficient_month_calibration_does_not_get_return_number():
    frame = pd.DataFrame({"date": pd.to_datetime(np.repeat(["2025-01-02", "2025-02-03", "2025-03-03", "2025-04-01", "2025-05-01"], 120)),
        "decile": 9, "score": np.tile(np.arange(120), 5), "fwd_rel": np.tile(np.arange(120)/10000, 5)})
    calibration = xr.calibrate(frame)["deciles"][0]
    assert calibration["n_rows"] == 600 and calibration["n_blocks"] == 5
    assert not calibration["measured"] and calibration["mean_rel_return"] is None


class OwnedWorker:
    """Pure process handle fixture: actual interpreter303, redirector202."""
    pid = 303
    returncode = None

    def __init__(self):
        self.killed, self.reaped = [], False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed.append(self.pid)
        self.returncode = -9

    def wait(self, timeout):
        assert self.returncode is not None
        self.reaped = True
        return self.returncode


def test_redirector_identity_refused_and_real_4gib_worker_is_measured_killed_reaped():
    base, site, _ = runner.direct_environment()
    identity = {"pid": 303, "nonce": "fixture", "sys_executable": str(base), "user_site_disabled": True,
        "package_origins": {name: str(site/name/"__init__.py") for name in runner.DEPENDENCIES}}
    with pytest.raises(ValueError, match="ownership"):
        runner.validate_identity(identity, pid=202, base=base, site=site, nonce="fixture")
    runner.validate_identity(identity, pid=303, base=base, site=site, nonce="fixture")
    worker, queries = OwnedWorker(), []
    def rss(pid):
        queries.append(pid)
        return 4*1024**3 if pid == 303 else 100*1024**2
    verdict = runner.guard_worker(worker, rss_query=rss, clock=lambda: 0)
    assert queries == [303, None] and 202 not in queries
    assert verdict["status"] == "REFUSED_OUTER_LIMIT" and verdict["owned_pids"] == [303]
    assert worker.killed == [303] and worker.reaped
    assert verdict["peak_aggregate_high_water_rss_bytes"] == 4*1024**3+100*1024**2


def test_outer_interrupts_blocking_worker_without_inner_checkpoint():
    worker, timer = OwnedWorker(), [0.0]
    def sleep(seconds):
        timer[0] += seconds
    verdict = runner.guard_worker(worker, rss_query=lambda pid: 1, sleep=sleep,
        clock=lambda: timer[0], max_seconds=.1)
    assert verdict["status"] == "REFUSED_OUTER_LIMIT"
    assert worker.killed == [303] and worker.reaped
    assert verdict["elapsed_seconds"] >= .1


def test_query_failure_reaps_only_actual_owned_worker():
    worker = OwnedWorker()
    def failed(pid):
        raise OSError("fixture measurement denied")
    verdict = runner.guard_worker(worker, rss_query=failed, clock=lambda: 0)
    assert verdict["status"] == "REFUSED_OUTER_LIMIT"
    assert worker.killed == [303] and worker.reaped


def test_near_completion_limit_keeps_success_worker_receipt_but_outer_refuses(tmp_path):
    worker = OwnedWorker()
    worker_receipt = tmp_path/"beta_v1_numerical_receipt.json"
    runner.atomic_receipt(worker_receipt, {"result": "fixture late success"})
    before = runner.file_sha256(worker_receipt)
    def late_completion():
        worker.returncode = 0
    verdict = runner.guard_worker(worker, rss_query=lambda pid: 4*1024**3 if pid else 1,
        clock=lambda: 0, extra_check=late_completion)
    runner.atomic_receipt(tmp_path/"outer_completion.json", verdict)
    assert verdict["status"] == "REFUSED_OUTER_LIMIT" and not verdict["worker_receipt_resource_qualified"]
    assert runner.file_sha256(worker_receipt) == before and worker.reaped
    with pytest.raises(numerical.NumericalRefused):
        runner.atomic_receipt(tmp_path/"outer_completion.json", verdict)


def test_success_outer_records_real_pid_peak_and_deadline_completion_boundary():
    worker, timer = OwnedWorker(), [0.0]
    def finish(seconds):
        timer[0] += seconds
        worker.returncode = 0
    verdict = runner.guard_worker(worker, rss_query=lambda pid: 100 if pid else 200,
        clock=lambda: timer[0], sleep=finish, final_peak_query=lambda owned: 300)
    assert verdict["status"] == "BOUNDED_COMPLETION"
    assert verdict["peak_aggregate_high_water_rss_bytes"] == 300 and verdict["owned_pids"] == [303]
    assert not verdict["worker_receipt_resource_qualified"]  # final owner receipt/identity still required
    worker, timer = OwnedWorker(), [0.0]
    def finish_late(seconds):
        timer[0] = 480.001
        worker.returncode = 0
    late = runner.guard_worker(worker, rss_query=lambda pid: 1, clock=lambda: timer[0], sleep=finish_late)
    assert late["status"] == "REFUSED_OUTER_LIMIT" and late["worker_exit_code"] == 0


def test_final_interval_4gib_peak_and_exit_refused_from_exact_owned_handle():
    worker, timer, final_handles = OwnedWorker(), [0.0], []
    worker._handle = object()
    def complete(seconds):
        timer[0] += seconds
        worker.returncode = 0  # peak and exit occurred between50ms samples
    def final_query(owned):
        final_handles.append(owned._handle)
        return 4*1024**3+200
    result = runner.guard_worker(worker, rss_query=lambda pid: 100 if pid else 200,
        clock=lambda: timer[0], sleep=complete, final_peak_query=final_query)
    assert final_handles == [worker._handle]
    assert result["status"] == "REFUSED_OUTER_LIMIT"
    assert result["final_owned_handle_peak_proved"]
    assert result["peak_aggregate_high_water_rss_bytes"] == 4*1024**3+200
    assert result["final_aggregate_high_water_rss_bytes"] == 4*1024**3+200
    assert result["worker_exit_code"] == 0 and worker.reaped


def test_final_handle_query_failure_refuses_despite_success_receipt(tmp_path):
    worker, timer = OwnedWorker(), [0.0]
    receipt = tmp_path/"beta_v1_numerical_receipt.json"
    runner.atomic_receipt(receipt, {"result": "fixture success"})
    before = runner.file_sha256(receipt)
    def complete(seconds):
        timer[0] += seconds
        worker.returncode = 0
    def failed(owned):
        raise OSError("final OS counters unavailable")
    result = runner.guard_worker(worker, rss_query=lambda pid: 100, clock=lambda: timer[0],
        sleep=complete, final_peak_query=failed)
    assert result["status"] == "REFUSED_OUTER_LIMIT" and not result["final_owned_handle_peak_proved"]
    assert "final exact-owned-handle" in result["reason"]
    runner.atomic_receipt(tmp_path/"outer_completion.json", result)
    assert runner.file_sha256(receipt) == before and worker.reaped


def test_no_final_query_cannot_qualify_completed_worker():
    worker = OwnedWorker()
    def complete(seconds):
        worker.returncode = 0
    result = runner.guard_worker(worker, rss_query=lambda pid: 100, clock=lambda: 0, sleep=complete)
    assert result["status"] == "REFUSED_OUTER_LIMIT"
    assert not result["final_owned_handle_peak_proved"]


def test_direct_cpython_light_identity_probe_uses_exact_venv_dependencies(tmp_path):
    """Stdlib find_spec only; no numerical imports/data/models; child<64MiB."""
    base, site, env = runner.direct_environment()
    probe = tmp_path/"identity_probe.py"
    probe.write_text("import json,time\nfrom scripts.beta_v1_numerical_receipt import worker_identity\n"
        "print(json.dumps(worker_identity('pure-probe')),flush=True)\ntime.sleep(.15)\n", encoding="utf-8")
    child = subprocess.Popen([str(base), "-S", str(probe)], cwd=runner.ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        identity = json.loads(child.stdout.readline())
        runner.validate_identity(identity, pid=child.pid, base=base, site=site, nonce="pure-probe",
            expected_origins={name: runner.importlib.util.find_spec(name).origin for name in runner.DEPENDENCIES})
        assert numerical.rss_bytes(child.pid, peak=True) < 64*1024**2
        out, error = child.communicate(timeout=5)
        assert child.returncode == 0 and not error
        assert identity["pid"] == child.pid and Path(identity["sys_executable"]) == base
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
