"""Order 2: the constant that voided Night 1, pinned so it cannot come back.

WHAT WAS ACTUALLY WRONG
=======================
`MAX_TOKENS = 1600`. Measured live on 2026-08-15 against the frozen Night-1
snapshot: every barren cell returned `finish_reason="length"` with `tokens_out`
exactly 1600; the two that produced came in at 1396 and 1591. Re-run at 4000,
8/8 produced. On a reasoning model `max_tokens` bounds thinking AND answer, so
below the budget the model needs the reply arrives EMPTY rather than half-formed
— which is why `n_chars: 0` was the common signature.

THE SUSPECT THAT WAS WRONG, AND WHY IT MATTERS THAT IT WAS WRONG
================================================================
The inherited leading suspect was "a size bound stated in percent where a
fraction is required". It cannot have been: `return_sign` carries
`threshold=None` and skips that check entirely, so a percent bug yields
`n_forecasts == 1`, never 0 — and every barren cell was exactly 0. The live
probe then refuted it a second time, empirically: every reply that parsed
carried `threshold` as a proper fraction. The percent bug was real, but it
belongs to the 2026-08-11 swarm (6 void records), not to this night.

That test is the first one below, because arithmetic that rules out a suspect
before any money is spent is the cheapest instrument in the building.
"""

from __future__ import annotations

import json

from backend.services import investigator_agent as A
from backend.services import investigator_night as N


class _Reply:
    def __init__(self, text="", finish_reason="stop", tokens_out=10):
        self.text = text
        self.model_version = "deepseek-v4-flash"
        self.tokens_in = 100
        self.tokens_out = tokens_out
        self.cached_tokens = 0
        self.latency_ms = 1.0
        self.retries = 0
        self.finish_reason = finish_reason


def _forecast_body(threshold_scale=1.0):
    return json.dumps({"forecasts": [
        {"observable": o, "horizon_days": h,
         "threshold": (None if t is None else t * threshold_scale),
         "prior": 0.2, "posterior": 0.25, "rationale": "r"}
        for o, h, t in A.FORECAST_CELLS]})


# ── the refutation, done in arithmetic ──────────────────────────────────────

def test_a_percent_size_bound_cannot_produce_a_zero_forecast_cell():
    # 5 instead of 0.05, 3 instead of 0.03 — the suspected bug, exactly.
    kept, drops = A.Investigator._validate(
        json.loads(_forecast_body(threshold_scale=100.0))["forecasts"])

    # The direction cell has no threshold, so it SURVIVES a percent bug. A cell
    # that dies of this reports 1, and Night 1's barren cells all reported 0.
    assert len(kept) == 1
    assert kept[0]["observable"] == "return_sign"
    assert drops == {A.DROP_SIZE_BOUND_NOT_A_FRACTION: 2}


def test_a_correct_fraction_size_bound_keeps_every_cell():
    kept, drops = A.Investigator._validate(
        json.loads(_forecast_body())["forecasts"])
    assert len(kept) == len(A.FORECAST_CELLS)
    assert drops == {}


# ── the real cause, and that it is now NAMED rather than generic ────────────

def test_a_truncated_forecast_is_reported_as_truncation_not_as_a_bad_reply():
    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            # The exact live signature: cut off at the ceiling, empty body.
            return _Reply(text="", finish_reason="length", tokens_out=1600)
        return _Reply(text=json.dumps({"ok": True}))

    inv = A.Investigator("A_snapshot", llm_call=llm).investigate("X", {})
    row = inv.as_row()

    assert inv.status == "no_forecast"
    assert row["terminal_drop_reason"] == A.DROP_REPLY_TRUNCATED
    assert row["n_truncated_calls"] == 1
    assert "length" in row["finish_reasons"]
    # The distinction is the whole point: our ceiling, not the model's格式.
    assert row["terminal_drop_reason"] != A.DROP_CALL_FAILED


def test_an_unparseable_but_complete_reply_is_blamed_on_the_model():
    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            return _Reply(text="this is not json", finish_reason="stop")
        return _Reply(text=json.dumps({"ok": True}))

    row = A.Investigator("A_snapshot", llm_call=llm).investigate("X", {}).as_row()

    assert row["terminal_drop_reason"] == A.DROP_REPLY_UNPARSEABLE
    assert row["n_truncated_calls"] == 0


def test_no_reply_at_all_is_blamed_on_transport():
    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            raise RuntimeError("connection reset")
        return _Reply(text=json.dumps({"ok": True}))

    row = A.Investigator("A_snapshot", llm_call=llm).investigate("X", {}).as_row()

    assert row["terminal_drop_reason"] == A.DROP_CALL_TRANSPORT_FAILED


# ── D3: a barren row explains itself on the receipt ─────────────────────────

def test_every_drop_reason_is_in_the_closed_vocabulary():
    # A receipt read every morning during a 40-night blind may not carry a
    # model-stated number. The vocabulary is closed so a reason cannot grow one.
    for name in dir(A):
        if name.startswith("DROP_") and name != "DROP_REASONS":
            assert getattr(A, name) in A.DROP_REASONS, name


def test_a_producing_cell_has_no_terminal_drop_reason():
    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            return _Reply(text=_forecast_body())
        return _Reply(text=json.dumps({"ok": True}))

    row = A.Investigator("A_snapshot", llm_call=llm).investigate("X", {}).as_row()

    assert row["n_forecasts"] == len(A.FORECAST_CELLS)
    assert row["terminal_drop_reason"] == ""


def test_terminal_drop_reason_is_deterministic_under_a_tie():
    inv = A.Investigation(arm="A_snapshot", ticker="X")
    inv.forecast_drops = {A.DROP_FIELD_MISSING: 2, A.DROP_CELL_NOT_REQUESTED: 2}
    # Dict order must not decide what a receipt says.
    assert inv.terminal_drop_reason == A.Investigation(
        arm="A_snapshot", ticker="X",
        forecast_drops={A.DROP_CELL_NOT_REQUESTED: 2,
                        A.DROP_FIELD_MISSING: 2}).terminal_drop_reason


# ── the integrity guard: an uneven loss voids the night ─────────────────────

def test_truncation_report_measures_the_gap_not_the_pool():
    # Night 1's actual shape: 15/40 control, 8/10 treatment.
    per_arm = {"A_snapshot": {"n_cells": 40, "n_cells_truncated": 15},
               "B_tools": {"n_cells": 10, "n_cells_truncated": 8}}

    t = N.truncation_report(per_arm)

    assert t["worst_arm"] == "B_tools"
    assert round(t["worst_arm_rate"], 2) == 0.80
    assert round(t["pooled_rate"], 2) == 0.46
    # Pooling would have called this a 46% problem. It is an 80% problem in the
    # arm under test, against 38% in its control — a 43-point gap between the
    # two things the trial exists to compare.
    assert round(t["per_arm_rate"]["A_snapshot"], 3) == 0.375
    assert round(t["spread"], 3) == 0.425


def test_a_night_that_truncates_unevenly_is_void_and_mints_nothing(monkeypatch,
                                                                   tmp_path):
    monkeypatch.setattr(N, "SANDBOX_RECEIPTS_DIR", tmp_path)

    # Night 1's actual shape, isolated: the arm that GATHERS truncates, the arm
    # that reads a fixed snapshot does not — and never five in a row, so the
    # barren money-guard stays silent and only the integrity guard can catch it.
    # This is the dangerous case: a night where everything downstream looks
    # healthy and the cell set is perfectly paired.
    seen = {"B_tools": 0}

    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            if "COMPANY_X" not in user and "no investigation tools" not in user:
                seen["B_tools"] += 1
                if seen["B_tools"] % 2:
                    return _Reply(text="", finish_reason="length",
                                  tokens_out=1600)
            return _Reply(text=_forecast_body())
        return _Reply(text=json.dumps({"ok": True}))

    feats = {f"T{i}": {"price": 100.0, "dollar_volume_20d": 1e9,
                       "abs_resid_return_z_1d": 3.0, "volume_z_20d": 3.0,
                       "earnings_within_5d": False, "filing_within_2d": False}
             for i in range(6)}

    res = N.run_night(feats, k=6, arms=("A_snapshot", "B_tools"),
                      llm_call=llm, tool_runner=lambda *a, **k: None,
                      sandbox=True, night="2026-01-01")

    assert res.status == "void"
    assert "truncation guard" in res.void_reason
    assert res.records_written == 0
    assert res.truncation["n_cells_truncated"] > 0


def test_a_clean_night_still_carries_a_truncation_block(monkeypatch, tmp_path):
    monkeypatch.setattr(N, "SANDBOX_RECEIPTS_DIR", tmp_path)

    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            return _Reply(text=_forecast_body())
        return _Reply(text=json.dumps({"ok": True}))

    feats = {f"T{i}": {"price": 100.0, "dollar_volume_20d": 1e9,
                       "abs_resid_return_z_1d": 3.0, "volume_z_20d": 3.0,
                       "earnings_within_5d": False, "filing_within_2d": False}
             for i in range(4)}

    res = N.run_night(feats, k=4, arms=("A_snapshot", "B_tools"),
                      llm_call=llm, tool_runner=lambda *a, **k: None,
                      sandbox=True, night="2026-01-02")

    # Reported on GOOD nights too. A field that only appears when it is bad
    # teaches the reader that its absence means fine, and absence is also what
    # a broken instrument produces.
    assert res.truncation["n_cells_truncated"] == 0
    assert res.truncation["worst_arm_rate"] == 0.0
    assert res.status != "void"


# ── the ceiling is registered, so drift is a refusal ────────────────────────

def test_max_tokens_is_on_the_registered_surface():
    from backend.services import iif1_prereg as P
    assert "MAX_TOKENS" in P.runtime_surface()
    assert A.MAX_TOKENS >= 8000, (
        "sized off a measured 7,186-token worst case on a tool-bearing cell; "
        "dropping below that reintroduces the defect that voided Night 1")


# ── the snapshot must not go stale under a paying night ─────────────────────

def test_a_stale_snapshot_refuses_a_paying_night():
    import datetime as dt
    import pytest
    ts = dt.datetime(2026, 8, 14, 11, 50, tzinfo=dt.timezone.utc)
    now = ts + dt.timedelta(hours=3)

    with pytest.raises(N.DecisionTimeStale, match="hindsight"):
        N.assert_decision_time_fresh(ts.isoformat(), now=now)


def test_a_fresh_snapshot_passes_and_reports_its_lag():
    import datetime as dt
    ts = dt.datetime(2026, 8, 14, 11, 50, tzinfo=dt.timezone.utc)

    # Night 1 ran 16 minutes after its snapshot. The protocol held by habit;
    # nothing enforced it, which is the defect this closes.
    lag = N.assert_decision_time_fresh(ts.isoformat(),
                                       now=ts + dt.timedelta(minutes=16))
    assert round(lag) == 16


def test_the_arms_of_one_cell_run_together_not_arm_by_arm(monkeypatch,
                                                          tmp_path):
    """The confound the cell-major loop removes.

    Arm-major order ran every cell of A, then every cell of B. Because the
    tools read the live internet, that made arm order a proxy for information
    age: on a 200-cell night the last arm saw hours more of the world than the
    first, and the trial would have scored that as the effect of tools.
    """
    monkeypatch.setattr(N, "SANDBOX_RECEIPTS_DIR", tmp_path)
    order = []

    def llm(*, system, user, model="m", temperature=0.0, max_tokens=0):
        if "MAGNITUDE" in system:
            return _Reply(text=_forecast_body())
        return _Reply(text=json.dumps({"ok": True}))

    class _Spy(A.Investigator):
        def investigate(self, ticker, snapshot=None):
            order.append((ticker, self.arm))
            return super().investigate(ticker, snapshot)

    monkeypatch.setattr(N, "Investigator", _Spy)
    feats = {f"T{i}": {"price": 100.0, "dollar_volume_20d": 1e9,
                       "abs_resid_return_z_1d": 3.0, "volume_z_20d": 3.0,
                       "earnings_within_5d": False, "filing_within_2d": False}
             for i in range(3)}

    N.run_night(feats, k=3, arms=("A_snapshot", "B_tools"), llm_call=llm,
                tool_runner=lambda *a, **k: None, sandbox=True,
                night="2026-01-03")

    tickers_in_order = [t for t, _ in order]
    # Cell-major: each ticker's arms are adjacent. Arm-major would give
    # [T0,T1,T2,T0,T1,T2]; this asserts [T0,T0,T1,T1,T2,T2].
    assert tickers_in_order == sorted(tickers_in_order,
                                      key=tickers_in_order.index)
    for i in range(0, len(order), 2):
        assert order[i][0] == order[i + 1][0], order
        assert order[i][1] != order[i + 1][1], order
