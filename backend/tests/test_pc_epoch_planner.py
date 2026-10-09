"""The frozen no-index allocation consumes contract values in offline replay."""

from backend.services import pc_epoch_planner as PL
from backend.services import pc_policy_epoch as PE


def _contract():
    content = {"allocation": {"revision_flow_gross_cap": 0.30,
                              "probe_gross_cap": 0.20, "gross_cap": 1.0,
                              "non_core_name_cap": 0.12,
                              "minimum_cash_buffer": 0.01,
                              "cash_when_unqualified": "RESERVE_NO_ELIGIBLE_RISK_CAPACITY"},
               "binding_limits": dict(PE.EXPECTED_LIMITS),
               "revision_flow": {"members": [f"T{i:02d}" for i in range(20)]}}
    return {"content": content, "content_sha256": "offline-frozen-hash"}


def _evidence():
    return {"account": {"equity": "100000", "cash": "100000"},
            "positions": [], "open_orders": []}


def _selectors():
    return {"bars_fresh": True, "revision_source_verified": True,
            "adv_by_symbol": {f"T{i:02d}": 1_000_000.0 for i in range(20)},
            "ranking": {"top20_net_rel_21d": -0.01, "top": [{"symbol": "SPY"}]},
            "blend_grade_may_trade": False, "probe_grade_may_trade": False,
            "probe_rows": [], "prior_probe_holdings": []}


def _prices():
    return {f"T{i:02d}": 100.0 for i in range(20)}


def _sigmas():
    return {f"T{i:02d}": 0.02 for i in range(20)}


def test_negative_exploit_still_plans_frozen_stock_sleeve_and_cash():
    result = PL.plan_active(contract=_contract(), evidence=_evidence(),
                            selectors=_selectors(), prices=_prices(),
                            sigmas=_sigmas())
    assert result["exploit_acting"] is False
    assert result["revision_acting"] is True
    assert len(result["sendable"]) == 20
    assert {x["state"] for x in result["sendable"]} == {"REVISION_FLOW"}
    assert all(x["side"] == "buy" and x["qty"] == 15 for x in result["sendable"])
    assert result["reserve_weight"] == 0.70
    assert result["reserve_reason"] == "RESERVE_NO_ELIGIBLE_RISK_CAPACITY"
    assert result["view_40000"]["reporting_only"] is True
    assert "SPY" not in {x["symbol"] for x in result["targets"]}


def test_active_values_ignore_mutated_legacy_flags(monkeypatch):
    from backend import config
    baseline = PL.plan_active(contract=_contract(), evidence=_evidence(),
                              selectors=_selectors(), prices=_prices(),
                              sigmas=_sigmas())
    monkeypatch.setattr(config, "PC_BENCHMARK_CORE", True)
    monkeypatch.setattr(config, "PC_SLEEVE_REVISION_FLOW_GROSS", 0.90)
    monkeypatch.setattr(config, "PROBE_GROSS_CAP", 0.95)
    again = PL.plan_active(contract=_contract(), evidence=_evidence(),
                           selectors=_selectors(), prices=_prices(),
                           sigmas=_sigmas())
    assert again == baseline


def test_pending_or_unknown_sigma_blocks_incremental_risk():
    evidence = _evidence()
    evidence["open_orders"] = [{"symbol": "T00", "side": "buy", "qty": "15"}]
    pending = PL.plan_active(contract=_contract(), evidence=evidence,
                             selectors=_selectors(), prices=_prices(), sigmas=_sigmas())
    assert pending["sendable"] == []
    assert "pending orders unresolved" in pending["risk_blocks"]
    sigmas = _sigmas()
    sigmas.pop("T00")
    unknown = PL.plan_active(contract=_contract(), evidence=_evidence(),
                             selectors=_selectors(), prices=_prices(), sigmas=sigmas)
    assert unknown["sendable"] == []
    assert any("unknown price/sigma" in x for x in unknown["risk_blocks"])


def test_refused_revision_source_holds_existing_member_risk():
    evidence = _evidence()
    evidence["positions"] = [{"symbol": "T00", "qty": "15", "market_value": "1500"}]
    evidence["account"]["cash"] = "98500"
    selectors = _selectors()
    selectors["revision_source_verified"] = False
    result = PL.plan_active(contract=_contract(), evidence=evidence,
                            selectors=selectors, prices=_prices(), sigmas=_sigmas())
    assert result["rf_hold"] == ["T00"]
    assert result["held_residual_gross"] == 0.015
    assert result["sendable"] == []


def test_probe_precedence_and_cap_leave_overlap_slice_as_cash():
    selectors = _selectors()
    selectors["probe_grade_may_trade"] = True
    selectors["probe_rows"] = [{"ticker": "T00", "median_dollar_vol": 1000000}]
    result = PL.plan_active(contract=_contract(), evidence=_evidence(),
                            selectors=selectors, prices=_prices(), sigmas=_sigmas())
    weights = {x["symbol"]: x["weight"] for x in result["targets"]}
    assert weights["T00"] == 0.02
    assert len(weights) == 20
    assert sum(weights.values()) < 0.32  # skipped RF slice is held as cash


def test_missing_rf_adv_blocks_incremental_risk():
    selectors = _selectors()
    selectors.pop("adv_by_symbol")
    plan = PL.plan_active(contract=_contract(), evidence=_evidence(),
                          selectors=selectors, prices=_prices(), sigmas=_sigmas())
    assert not [o for o in plan["sendable"] if o["side"] == "buy"]
    assert any("missing or invalid ADV" in x for x in plan["risk_blocks"])


def test_exploit_uses_its_supplied_adv_and_refuses_oversized_order():
    selectors = _selectors()
    selectors["revision_source_verified"] = False
    selectors["blend_grade_may_trade"] = True
    selectors["ranking"] = {"top20_net_rel_21d": 0.01,
                            "top": [{"symbol": "OTHER", "median_dollar_vol": 1000}]}
    selectors["er_view"] = {"names": {"OTHER": {"h21": {
        "er": 0.01, "er_equal": 0.01, "x": {}, "weights": {},
        "phi": {}, "components_awake": [], "weights_source": "offline"}}}}
    plan = PL.plan_active(contract=_contract(), evidence=_evidence(),
                          selectors=selectors, prices={"OTHER": 100},
                          sigmas={"OTHER": 0.02})
    assert not [o for o in plan["sendable"] if o["side"] == "buy"]
    assert plan["targets"][0]["median_dollar_vol"] == 1000


def test_rotating_probe_does_not_double_held_sleeve():
    evidence = _evidence()
    evidence["positions"] = [{"symbol": f"P{i:02d}", "qty": "20",
                              "market_value": "2000"} for i in range(10)]
    evidence["account"]["cash"] = "80000"
    selectors = _selectors()
    selectors["probe_grade_may_trade"] = True
    selectors["probe_rows"] = [{"ticker": f"P{i:02d}",
                                "median_dollar_vol": 1_000_000}
                               for i in range(10, 20)]
    selectors["prior_probe_holdings"] = [f"P{i:02d}" for i in range(10)]
    selectors["adv_by_symbol"].update({f"P{i:02d}": 1_000_000 for i in range(20)})
    prices = {**_prices(), **{f"P{i:02d}": 100 for i in range(20)}}
    sigmas = {**_sigmas(), **{f"P{i:02d}": 0.02 for i in range(20)}}
    plan = PL.plan_active(contract=_contract(), evidence=evidence,
                          selectors=selectors, prices=prices, sigmas=sigmas)
    assert len([o for o in plan["sendable"] if o["side"] == "sell"
                and o["state"] == "PROBE_EXIT"]) == 10
    assert plan["post_fill_gross"] <= 0.5000001
    # Without proven old-name liquidity the exits cannot authorize buys.
    selectors["adv_by_symbol"] = {f"P{i:02d}": 1_000_000 for i in range(10, 20)}
    plan = PL.plan_active(contract=_contract(), evidence=evidence,
                          selectors=selectors, prices=prices, sigmas=sigmas)
    assert not [o for o in plan["sendable"] if o["side"] == "buy"]
    assert any("PROBE/unattributed" in x for x in plan["risk_blocks"])
