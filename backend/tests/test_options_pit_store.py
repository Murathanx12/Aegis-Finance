"""The options PIT store — a perishable input, so its refusals matter more.

An implied move that was not captured before its event is gone permanently:
yfinance option chains are a snapshot with no history. So the failures worth
testing are the ones that would let a WRONG row into the store and be
indistinguishable later, and the ones that would let the store stop collecting
quietly.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services import options_pit_store as ops


# ── fixtures that look like yfinance ────────────────────────────────────────


def _chain(strikes, ivs, spot=100.0, is_call=True, r=0.04, q=0.0):
    """A chain carrying BOTH the vendor's IV column and consistent QUOTES.

    The quotes are the Black-Scholes prices of the very IVs in the column, so
    the fixture is internally consistent: our own inversion recovers exactly
    what the vendor claims. That makes the fixture silent about the convention
    gap -- which is right, because the gap is an empirical fact about Yahoo
    (`OPTIONS-CONVENTION-1`), not something a unit test should assert into
    existence.
    """
    from backend.services.option_implier import bsm_price, to_continuous

    px = [bsm_price(spot, k, 30 / 365, to_continuous(r), to_continuous(q),
                    iv, is_call) for k, iv in zip(strikes, ivs)]
    return pd.DataFrame({"strike": strikes, "impliedVolatility": ivs,
                         "bid": [max(v - 0.01, 0.01) for v in px],
                         "ask": [v + 0.01 for v in px],
                         "lastPrice": px})


class FakeTicker:
    """Minimal stand-in: expiries at given day offsets with flat ATM IVs."""

    def __init__(self, spot=100.0, by_days=None, expiries=None):
        self.spot = spot
        self.by_days = by_days or {}
        self._expiries = expiries
        self.today = pd.Timestamp("2026-08-24")

    def history(self, period="1d", auto_adjust=True, actions=False):
        # Signature widened 2026-08-24: `build_state` now asks for 1y WITH
        # actions, because the same single request must yield the spot and the
        # trailing dividends that our own inversion needs for q.
        df = pd.DataFrame({"Close": [self.spot]})
        if actions:
            df["Dividends"] = [0.0]
        return df

    @property
    def options(self):
        if self._expiries is not None:
            return self._expiries
        return [str((self.today + pd.Timedelta(days=d)).date())
                for d in sorted(self.by_days)]

    def option_chain(self, e):
        days = (pd.Timestamp(e).normalize() - self.today).days
        ivc, ivp = self.by_days[days]
        ks = [self.spot * 0.99, self.spot, self.spot * 1.01]
        return SimpleNamespace(
            calls=_chain(ks, [ivc] * 3, self.spot, True),
            puts=_chain(ks, [ivp] * 3, self.spot, False))


def _build(tk, as_of="2026-08-24"):
    # r is passed explicitly so the unit suite never reaches FRED. The
    # collector resolves it from FRED and LOGS the fallback; a test that
    # silently used the fallback would be testing the fallback.
    return ops.build_state("X", as_of, ticker_obj=tk, r_simple=0.04)


# ── the definition the screen validated ─────────────────────────────────────


def test_implied_move_matches_the_screens_formula():
    """`implied_move_1d = atm_iv_30 * sqrt(1/252)` — transcribed, not chosen."""
    tk = FakeTicker(by_days={30: (0.40, 0.40), 60: (0.30, 0.30)})
    st = _build(tk)
    assert st.atm_iv_30 == pytest.approx(0.40, abs=1e-6)
    assert st.implied_move_1d == pytest.approx(0.40 * math.sqrt(1 / 252),
                                               abs=1e-6)


def test_term_slope_and_put_call_residual_match_stdopd():
    tk = FakeTicker(by_days={30: (0.40, 0.44), 60: (0.30, 0.30)})
    st = _build(tk)
    assert st.iv_term_slope == pytest.approx(st.atm_iv_30 - st.atm_iv_60)
    assert st.iv_put_minus_call_30d == pytest.approx(0.04, abs=1e-6)


def test_constant_maturity_is_interpolated_not_nearest_expiry():
    """THE POINT OF THE MODULE.

    `stdopd` is a STANDARDIZED 30-day surface. Reading whichever expiry happens
    to be nearest would make the feature drift with the expiry cycle — rich
    just before a monthly, cheap just after — and that drift is a seasonal
    pattern the screen never validated, wearing its name.

    With flat total variance between 20d and 45d, the 30-day point must land
    strictly between the two inputs, not on either.
    """
    tk = FakeTicker(by_days={20: (0.50, 0.50), 45: (0.30, 0.30)})
    st = _build(tk)
    assert 0.30 < st.atm_iv_30 < 0.50
    assert st.atm_iv_30 not in (0.30, 0.50)
    # linear in total variance: w = iv^2 * T
    w20, w45 = 0.50 ** 2 * 20, 0.30 ** 2 * 45
    w30 = w20 + (w45 - w20) * (30 - 20) / (45 - 20)
    assert st.atm_iv_30 == pytest.approx(math.sqrt(w30 / 30), abs=1e-6)


def test_interpolation_is_in_variance_not_in_vol():
    """Interpolating IV directly can admit calendar arbitrage; the two differ
    measurably, so the choice is asserted rather than described."""
    tk = FakeTicker(by_days={20: (0.50, 0.50), 45: (0.30, 0.30)})
    st = _build(tk)
    naive_vol_interp = 0.50 + (0.30 - 0.50) * (30 - 20) / (45 - 20)
    assert abs(st.atm_iv_30 - naive_vol_interp) > 1e-3


# ── refusals, because a plausible wrong row is worse than none ──────────────


def test_a_single_expiry_is_REFUSED():
    tk = FakeTicker(by_days={30: (0.40, 0.40)})
    with pytest.raises(ops.OptionStateUnavailable) as e:
        _build(tk)
    assert "cannot be interpolated from one point" in str(e.value)


def test_an_expiry_far_from_the_tenor_cannot_be_called_30_day():
    """Two expiries, both far from 30 days on the same side. Calling a 70-day
    IV 'the 30-day IV' is a different feature, not a noisy one."""
    tk = FakeTicker(by_days={70: (0.40, 0.40), 85: (0.38, 0.38)})
    with pytest.raises(ops.OptionStateUnavailable) as e:
        _build(tk)
    assert "30-day ATM IV" in str(e.value)


def test_no_expiries_is_REFUSED_not_silently_empty():
    tk = FakeTicker(by_days={}, expiries=[])
    with pytest.raises(ops.OptionStateUnavailable):
        _build(tk)


def test_a_missing_60d_leg_still_stores_the_30d_feature():
    """The 30-day leg carries the licensed feature; the 60-day one only feeds
    the term slope. Losing the second must not discard the first."""
    tk = FakeTicker(by_days={20: (0.40, 0.40), 30: (0.40, 0.40)})
    st = _build(tk)
    assert st.atm_iv_30 is not None and st.implied_move_1d is not None
    assert st.atm_iv_60 is None and st.iv_term_slope is None


# ── the store ───────────────────────────────────────────────────────────────


def test_the_store_is_WRITE_ONCE_per_ticker_and_date(tmp_path):
    tk = FakeTicker(by_days={30: (0.40, 0.40), 60: (0.30, 0.30)})
    st = _build(tk)
    assert ops.record(st, root=tmp_path) is True
    assert ops.record(st, root=tmp_path) is False, (
        "a second capture would replace an observation taken at a different "
        "moment, and the store's whole value is WHEN its rows were taken")
    rows = [json.loads(x) for x in
            (tmp_path / "option_state_2026-08.jsonl").read_text().splitlines()]
    assert len(rows) == 1


def test_capture_time_is_ours_never_the_payloads(tmp_path):
    tk = FakeTicker(by_days={30: (0.40, 0.40), 60: (0.30, 0.30)})
    st = _build(tk)
    assert st.captured_at != st.as_of
    assert st.captured_at.endswith("+00:00") or "T" in st.captured_at


def test_capture_over_an_empty_universe_is_REFUSED(tmp_path):
    with pytest.raises(ops.OptionStateUnavailable) as e:
        ops.capture([], root=tmp_path)
    assert "stored nothing and reported success" in str(e.value)


def test_one_bad_name_does_not_abort_the_pass(tmp_path):
    def builder(t, as_of):
        if t == "BAD":
            raise ops.OptionStateUnavailable("no chain")
        return ops.OptionState(
            ticker=t, as_of=as_of, captured_at="2026-08-24T00:00:00+00:00",
            spot=100.0, atm_iv_30=0.4, atm_iv_60=0.3, iv30_call=0.4,
            iv30_put=0.4, iv_term_slope=0.1, iv_put_minus_call_30d=0.0,
            implied_move_1d=0.025, parity_basis="matched_strike",
            method="test", n_expiries_used=2)

    out = ops.capture(["A", "BAD", "C"], "2026-08-24", root=tmp_path,
                      builder=builder)
    assert out["stored"] == 2 and out["unavailable"] == 1
    assert "BAD" in out["reasons"]
    assert out["coverage"] == pytest.approx(2 / 3, abs=1e-4)


# ── health, because a store that stopped looks like one nobody queried ──────


def test_health_is_ABSENT_before_anything_is_captured(tmp_path):
    assert ops.health(root=tmp_path)["status"] == "ABSENT"


def test_health_DEGRADES_when_collection_stops(tmp_path):
    st = ops.OptionState(
        ticker="A", as_of="2026-08-01", captured_at="2026-08-01T00:00:00+00:00",
        spot=100.0, atm_iv_30=0.4, atm_iv_60=0.3, iv30_call=0.4, iv30_put=0.4,
        iv_term_slope=0.1, iv_put_minus_call_30d=0.0, implied_move_1d=0.025,
        parity_basis="matched_strike", method="test", n_expiries_used=2)
    ops.record(st, root=tmp_path)
    h = ops.health(root=tmp_path)
    assert h["status"] == "DEGRADED"
    assert "PERISHABLE" in h["reason"]
    assert h["days_held"] == 1 and h["rows"] == 1


# ── our own inversion, recorded from the first row (schema 1.1.0) ───────────


def test_our_own_residual_is_recorded_BESIDE_the_vendors_not_instead_of_it():
    """`OPTIONS-CONVENTION-1`: the vendor's implied-vol column discounts
    nothing, which is the whole 0.026 train/serve gap. Both quantities are
    kept -- the vendor's because every standing receipt is written against it,
    ours because it is the one that means what the feature says it means."""
    tk = FakeTicker(by_days={25: (0.30, 0.32), 45: (0.28, 0.29)})
    st = _build(tk)
    assert st.iv_put_minus_call_30d is not None
    assert st.iv_put_minus_call_30d_own is not None
    assert st.schema_version == "options-pit-1.1.0"


def test_the_convention_travels_with_the_row():
    """A residual without the r and q it was computed under is not
    re-derivable, and it moves ~0.0070 per percentage point of rate."""
    tk = FakeTicker(by_days={25: (0.30, 0.32), 45: (0.28, 0.29)})
    st = _build(tk)
    assert st.r_used == pytest.approx(0.04)
    assert st.q_used == pytest.approx(0.0)
    assert st.price_basis == "mid"


def test_our_residual_is_NOT_silently_filled_from_the_vendor():
    """A chain with no two-sided quotes must leave our column None. Copying the
    vendor's number in would make the two indistinguishable in the store, which
    is the one thing this schema change exists to prevent."""
    tk = FakeTicker(by_days={25: (0.30, 0.32), 45: (0.28, 0.29)})
    real = tk.option_chain

    def stripped(e):
        ch = real(e)
        for df in (ch.calls, ch.puts):
            df["bid"] = 0.0
            df["ask"] = 0.0
            df["lastPrice"] = 0.0
        return ch

    tk.option_chain = stripped
    st = _build(tk)
    assert st.iv_put_minus_call_30d is not None, "the vendor column survives"
    assert st.iv_put_minus_call_30d_own is None
    assert st.price_basis is None


def test_capture_resolves_the_rate_ONCE_for_the_whole_pass(tmp_path):
    """Per-name resolution would price two names in one snapshot off different
    curves, and a cross-section computed under two conventions is not one."""
    calls = []

    def builder(ticker, as_of, r_simple=None):
        calls.append(r_simple)
        return ops.OptionState(
            ticker=ticker, as_of=as_of, captured_at="2026-08-24T00:00:00+00:00",
            spot=100.0, atm_iv_30=0.3, atm_iv_60=0.3, iv30_call=0.3,
            iv30_put=0.3, iv_term_slope=0.0, iv_put_minus_call_30d=0.0,
            implied_move_1d=0.02, parity_basis="matched_strike", method="t",
            n_expiries_used=2)

    rep = ops.capture(["A", "B", "C"], as_of="2026-08-24", root=tmp_path,
                      builder=builder)
    assert rep["stored"] == 3
    assert len(set(calls)) == 1, f"rate resolved more than once: {calls}"
    assert rep["r_simple"] == calls[0]
    assert rep["r_source"]
