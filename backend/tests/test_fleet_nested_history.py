"""Nested broker child identity is evidence for historical cooldown classification."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from backend.services import fleet_manager as FM

FILL_TIME = "2026-09-29T13:36:00.978665Z"
SINCE = "2026-09-04T00:00:00Z"


def _fill(**change):
    return {"id": "fill-child", "activity_type": "FILL", "order_id": "child",
            "symbol": "BE261016C00290000", "side": "sell", "qty": "7",
            "transaction_time": FILL_TIME, **change}


def _parent(kind="limit", **leg_change):
    leg = {"id": "child", "type": kind, "side": "sell", "symbol": "BE261016C00290000",
           "qty": "7", "filled_qty": "7", "status": "filled", "filled_at": FILL_TIME,
           "legs": None}
    leg.update(leg_change)
    return {"id": "parent", "order_class": "mleg", "type": "limit", "legs": [leg]}


def _venue(*, fills=None, closed=None, child_status=404, child_row=None):
    seen = []
    fills = [_fill()] if fills is None else fills
    closed = [_parent()] if closed is None else closed

    def transport(method, url, _headers, _body):
        assert method == "GET"
        parsed = urlparse(url)
        seen.append(parsed)
        if parsed.path.endswith("/activities/FILL"):
            return 200, json.dumps(fills).encode()
        if parsed.path.endswith("/v2/orders"):
            params = parse_qs(parsed.query)
            assert params["status"] == ["closed"] and params["nested"] == ["true"]
            assert params["after"] == [SINCE] and params["limit"] == ["500"]
            return 200, json.dumps(closed).encode()
        if parsed.path.endswith("/v2/orders/child"):
            return child_status, json.dumps(child_row or {}).encode()
        raise AssertionError(parsed.path)

    return FM.Venue("offline", "offline", transport=transport), seen


def test_mleg_limit_child_classifies_despite_direct_child_404():
    venue, seen = _venue()
    assert venue.stop_fills_since(SINCE) == []
    assert any(p.path.endswith("/v2/orders/child") for p in seen)


def test_mleg_stop_child_is_a_stop_fill():
    venue, seen = _venue(closed=[_parent("stop")])
    result = venue.stop_fills_since(SINCE)
    assert [(r["symbol"], r["type"]) for r in result] == [("BE261016C00290000", "stop")]
    assert any(p.path.endswith("/v2/orders/child") for p in seen)


def test_readable_direct_child_must_agree_with_nested_type_and_identity():
    direct = _parent()["legs"][0]
    venue, _ = _venue(child_status=200, child_row=dict(direct, type="stop"))
    with pytest.raises(FM.FleetRefusal, match="direct and nested"):
        venue.stop_fills_since(SINCE)
    venue, _ = _venue(child_status=200, child_row=direct)
    assert venue.stop_fills_since(SINCE) == []


@pytest.mark.parametrize("change", [
    {"qty": "5", "filled_qty": "5"}, {"status": "partially_filled"},
    {"filled_at": "2026-09-28T00:00:00Z"}, {"qty": True},
])
def test_direct_child_quantity_status_and_time_must_corroborate(change):
    direct = dict(_parent()["legs"][0], **change)
    venue, _ = _venue(child_status=200, child_row=direct)
    with pytest.raises(FM.FleetRefusal):
        venue.stop_fills_since(SINCE)


def test_partial_window_fill_uses_aware_chronology_without_requiring_lifetime_sum():
    partial = _fill(qty="1", transaction_time="2026-09-29T13:35:00Z")
    leg = _parent(filled_at=FILL_TIME, submitted_at="2026-09-20T13:00:00Z")
    venue, _ = _venue(fills=[partial], closed=[leg])
    assert venue.stop_fills_since(SINCE) == []
    for bad in ("not-a-date", "2026-09-29T13:37:00Z",
                "2026-09-19T13:00:00Z", "2026-09-29T13:35:00"):
        venue, _ = _venue(fills=[dict(partial, transaction_time=bad)], closed=[leg])
        with pytest.raises(FM.FleetRefusal):
            venue.stop_fills_since(SINCE)


@pytest.mark.parametrize("bad_fills,bad_closed", [
    ([_fill(qty=True)], None),
    (None, [_parent(qty=True, filled_qty=True)]),
    ([_fill(activity_type="DIV")], None),
    ([_fill(id=[])], None),
    ([_fill(order_id={})], None),
    (None, [_parent(id=[])]),
    (None, [_parent(status=[])]),
])
def test_malformed_quantities_types_and_ids_refuse_typed(bad_fills, bad_closed):
    venue, _ = _venue(fills=bad_fills, closed=bad_closed)
    with pytest.raises(FM.FleetRefusal):
        venue.stop_fills_since(SINCE)


def test_activity_identity_duplicate_across_distinct_children_refuses():
    first, second = _parent(), _parent()
    second["id"] = "parent-two"
    second["legs"][0]["id"] = "child-two"
    fills = [_fill(), _fill(order_id="child-two")]
    venue, _ = _venue(fills=fills, closed=[first, second])
    with pytest.raises(FM.FleetRefusal, match="duplicated"):
        venue.stop_fills_since(SINCE)


@pytest.mark.parametrize("closed", [
    [_parent(id="parent")],  # replaced below: duplicate parent/leg identity
    [_parent(), _parent()],
    [_parent(), {"id": "child", "type": "stop"}],
])
def test_duplicate_or_conflicting_order_identity_refuses(closed):
    if len(closed) == 1:
        closed[0]["legs"][0]["id"] = "parent"
    venue, _ = _venue(closed=closed)
    with pytest.raises(FM.FleetRefusal, match="duplicate historical broker order identity"):
        venue.stop_fills_since(SINCE)


@pytest.mark.parametrize("change", [
    {"symbol": "OTHER"}, {"side": "buy"}, {"qty": "5"},
    {"filled_qty": "5"}, {"filled_qty": "NaN"}, {"status": "new"},
    {"filled_at": "2026-09-29T13:35:00Z"}, {"type": "unknown"},
    {"legs": [{"id": "grandchild"}]}, {"id": None},
])
def test_malformed_or_nonmatching_nested_leg_cannot_supply_type(change):
    venue, _ = _venue(closed=[_parent(**change)])
    with pytest.raises(FM.FleetRefusal):
        venue.stop_fills_since(SINCE)


def test_duplicate_fill_identity_and_simple_parent_refuse_nested_authority():
    two = [dict(_fill(), qty="3.5"), dict(_fill(), qty="3.5")]
    venue, _ = _venue(fills=two)
    with pytest.raises(FM.FleetRefusal, match="FILL identity duplicated"):
        venue.stop_fills_since(SINCE)
    parent = _parent()
    parent["order_class"] = "simple"
    venue, _ = _venue(closed=[parent])
    with pytest.raises(FM.FleetRefusal, match="nested historical order structure malformed"):
        venue.stop_fills_since(SINCE)


def test_missing_nested_child_still_uses_only_exact_accepted_local_fallback():
    venue, seen = _venue(closed=[])
    with pytest.raises(FM.FleetRefusal, match="type unknown"):
        venue.stop_fills_since(SINCE, owned_types={"other": "stop"})
    assert any(p.path.endswith("/v2/orders/child") for p in seen)
    assert venue.stop_fills_since(SINCE, owned_types={"child": "limit"}) == []


def test_truncated_closed_and_fill_pages_refuse():
    closed = [{"id": f"other-{i}", "type": "limit"} for i in range(500)]
    venue, _ = _venue(closed=closed)
    with pytest.raises(FM.FleetRefusal, match="closed order page incomplete"):
        venue.stop_fills_since(SINCE)
    fills = [dict(_fill(), id=f"fill-{i}") for i in range(100)]
    venue, _ = _venue(fills=fills)
    with pytest.raises(FM.FleetRefusal, match="FILL pages incomplete"):
        venue.stop_fills_since(SINCE)
