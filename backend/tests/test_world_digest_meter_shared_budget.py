"""Real-meter accounting for shared PC reservations and legacy cloud responses."""

import pytest

from backend.services.world_digest import BudgetExceeded, Meter


def call_with(result):
    meter = Meter(0.1, llm=lambda *args, **kwargs: result)
    text = meter.call("system", "user", purpose="test", max_tokens=10, stage="extract")
    return meter, text


@pytest.mark.parametrize("status", ["BILLING_UNKNOWN", "SETTLEMENT_FAILED_RESERVATION_RETAINED"])
def test_unknown_billable_attempt_keeps_host_charge(status):
    meter, text = call_with({"ok": False, "text": None, "status": "ERROR",
                             "cost_usd": None, "budget_charge_usd": 0.025,
                             "billing_status": status, "tokens_in": 0, "tokens_out": 0})
    assert text is None
    assert meter.summary()["spent_usd"] == 0.025
    assert meter.summary()["unpriced_calls"] == 1
    assert meter.summary()["failed"] == 1


def test_settled_call_uses_host_charge_without_unpriced_flag():
    meter, text = call_with({"ok": True, "text": "typed", "status": "OK",
                             "cost_usd": 0.012, "budget_charge_usd": 0.012,
                             "billing_status": "SETTLED_PEAK_ESTIMATE"})
    assert text == "typed"
    assert meter.summary()["spent_usd"] == 0.012
    assert meter.summary()["unpriced_calls"] == 0


def test_no_wire_refusal_is_zero_without_unpriced_attempt():
    meter, text = call_with({"ok": False, "text": None, "status": "BUDGET_REFUSED",
                             "cost_usd": None, "budget_charge_usd": 0.0})
    assert text is None
    assert meter.summary()["spent_usd"] == 0
    assert meter.summary()["unpriced_calls"] == 0


def test_legacy_cloud_token_fallback_unchanged():
    meter, text = call_with({"ok": False, "text": None, "status": "ERROR",
                             "cost_usd": None, "tokens_in": 1000, "tokens_out": 100})
    assert text is None
    assert meter.summary()["spent_usd"] == pytest.approx(round((1000 * .53 + 100 * 1.29) / 1e6, 5))
    assert meter.summary()["unpriced_calls"] == 1


def test_invalid_shared_charge_fails_closed():
    for charge in (None, -1, float("nan"), True):
        with pytest.raises(BudgetExceeded, match="invalid shared budget charge"):
            call_with({"ok": False, "text": None, "status": "ERROR",
                       "cost_usd": None, "budget_charge_usd": charge})
