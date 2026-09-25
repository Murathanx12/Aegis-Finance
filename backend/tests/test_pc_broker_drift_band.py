"""The drift band: a one-share rounding flip on a held name is not an order.

2026-09-25, PC-PAPER's first live PROBE day: GOOGL sold 1 share at 13:37 and
bought 1 at 13:47 because a 2% target on a $345 stock flips between 58 and 59
shares as the price moves. Entries and exits are never gated by the band.
"""
from backend.services import pc_broker as B


def _t(sym, w):
    return B.Target(symbol=sym, weight=w, reason="probe", median_dollar_vol=5e8) \
        if "median_dollar_vol" in B.Target.__dataclass_fields__ else B.Target(symbol=sym, weight=w, reason="probe")


def test_a_one_share_flip_on_a_held_name_is_refused_as_churn():
    plans = B.plan_orders([_t("GOOGL", 0.02)], equity=1_000_000.0, held={"GOOGL": 59.0},
                          prices={"GOOGL": 344.0}, min_order_usd=250.0)
    assert len(plans) == 1
    p = plans[0]
    assert p.qty == 0 and p.refused and "rounding churn" in p.refused


def test_a_real_drift_on_a_held_name_is_sent():
    # target 2% of $1M at $344 = 58 sh; held 40 -> delta 18 sh = $6,192 > 10% of $20,000
    plans = B.plan_orders([_t("GOOGL", 0.02)], equity=1_000_000.0, held={"GOOGL": 40.0},
                          prices={"GOOGL": 344.0}, min_order_usd=250.0)
    assert plans[0].side == "buy" and plans[0].qty == 18 and not plans[0].refused


def test_entries_and_exits_are_never_gated_by_the_band():
    entry = B.plan_orders([_t("GOOGL", 0.02)], equity=1_000_000.0, held={},
                          prices={"GOOGL": 344.0}, min_order_usd=250.0)[0]
    assert entry.side == "buy" and entry.qty == 58 and not entry.refused
    exit_ = B.plan_orders([], equity=1_000_000.0, held={"GOOGL": 1.0},
                          prices={"GOOGL": 344.0}, min_order_usd=250.0)[0]
    assert exit_.side == "sell" and exit_.qty == 1 and not exit_.refused
