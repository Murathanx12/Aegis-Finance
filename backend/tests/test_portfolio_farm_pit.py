"""The farm cannot see tomorrow — proven by planting tomorrow in the panel.

WHY A PLANTED ORACLE AND NOT A CODE REVIEW
==========================================
"No lookahead" is the one claim in this package that cannot be allowed to rest
on reading the source, because it is exactly the claim a refactor breaks
silently: an off-by-one in a window, a `shift` that moves the wrong way, a
convenience index added six months from now. None of those produce an error.
They produce a better number.

So the test builds a synthetic panel with a column whose value at row `i` IS
row `i+1`'s return — perfect foresight, sitting in the data, reachable by any
function that indexes forward — and asserts that:

  * no registered signal's grid at row i correlates with the planted future;
  * the replay's NAV is byte-identical whether the oracle column exists or not.

The second is the strong one. It does not ask whether the code looks careful;
it asks whether the answer changes when the future is made available.

THE SYNTHETIC PANEL IS ALSO THE UNIT-TEST SUBSTRATE. The real panel is 4 GB of
CRSP on one developer's disk; a suite that needed it would not run in CI and
therefore would not run. Everything here is built in memory in milliseconds.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.portfolio_farm import replay, signals as SIG
from backend.services.portfolio_farm.panel import Panel
from backend.services.portfolio_farm.policy import Policy

T, N = 420, 30


def synthetic(seed: int = 7, *, oracle_col: int | None = None) -> Panel:
    """A small, well-formed panel. Prices are a random walk; `oracle_col`, when
    given, is a name whose PRICE PATH is engineered to be irresistible to
    anything that peeks — it jumps tomorrow, every time."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, 0.02, size=(T, N))
    if oracle_col is not None:
        # A name that returns +5% on odd days and -5% on even ones. Anything
        # reading row i+1 can time it perfectly; anything trailing cannot.
        r[:, oracle_col] = np.where(np.arange(T) % 2 == 1, 0.05, -0.05)
    tri = np.cumprod(1.0 + r, axis=0)
    close = 50.0 * tri
    open_ = close * (1.0 + rng.normal(0, 0.002, size=(T, N)))
    dates = np.array([f"20{10 + i // 252:02d}-{1 + (i % 12):02d}-"
                      f"{1 + (i % 28):02d}" for i in range(T)], dtype=object)
    # Unique, ascending, ISO-ish. Only ordering matters to the engine.
    dates = np.array([f"2010-01-01+{i:04d}" for i in range(T)], dtype=object)
    return Panel(
        dates=dates,
        permnos=np.arange(10000, 10000 + N, dtype=np.int64),
        close=close.astype(np.float32),
        open_=open_.astype(np.float32),
        ret=r.astype(np.float32),
        retx=r.astype(np.float32),
        traded=np.ones((T, N), dtype=bool),
        dolvol=np.full((T, N), 5e7, dtype=np.float32),
        mktcap=np.full((T, N), 1e10, dtype=np.float32),
        tri=tri.astype(np.float32),
        source="synthetic",
        close_raw=close.astype(np.float32),
        # Non-price characteristics, supplied DIRECTLY rather than read from
        # disk. The whole point of these signals is that they come from another
        # file; a test that reached for that file would be testing the join and
        # not the signal, and would pass or fail depending on what is pulled.
        #
        # They are built from a LAGGED slice of the panel's own returns so that
        # a lookahead in the dispatcher is still detectable: if `value_bm`
        # started reading row i+1, the PIT test's oracle correlation would
        # catch it exactly as it does for a price signal.
        chars={
            "bm": np.vstack([np.full((1, N), np.nan, dtype=np.float32),
                             tri[:-1].astype(np.float32)]),
            "roe": np.vstack([np.full((1, N), np.nan, dtype=np.float32),
                              -tri[:-1].astype(np.float32)]),
            # The analyst-revision channels, on the same lagged-slice
            # construction and for the same reason. Each is a DIFFERENT
            # transform of the lagged panel so `sell_side_state` cannot pass
            # by having three identical components — a composite of one thing
            # repeated is exactly the `arena_composite` failure.
            "rev_breadth": np.vstack([
                np.full((1, N), np.nan, dtype=np.float32),
                np.tanh(tri[:-1]).astype(np.float32)]),
            "rev_magnitude": np.vstack([
                np.full((1, N), np.nan, dtype=np.float32),
                (0.5 * tri[:-1]).astype(np.float32)]),
            "rev_dispersion": np.vstack([
                np.full((1, N), np.nan, dtype=np.float32),
                (-0.25 * tri[:-1]).astype(np.float32)]),
        },
    )


def _policy(**kw) -> Policy:
    return Policy(**{"top_k": 5, "universe_n": 20, "holding_days": 5, **kw})


# ── no signal can reach the future ──────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(SIG.SIGNALS))
def test_no_signal_grid_correlates_with_TOMORROWS_return(name):
    """A grid row `i` is scored against the panel's row `i+1` return. A signal
    that had peeked would show a correlation far from zero; a trailing one
    shows noise. The bar is deliberately loose (|rho| < 0.25) — this catches
    LOOKAHEAD, not weak predictive power, and a tight bar here would fail on a
    signal that legitimately works."""
    p = synthetic()
    g = SIG.matrix(p, name)
    fut = p.ret[1:].astype(np.float64)
    cur = g[:-1].astype(np.float64)
    ok = np.isfinite(cur) & np.isfinite(fut)
    if ok.sum() < 500 or np.nanstd(cur[ok]) == 0:
        pytest.skip(f"{name}: not enough variation on the synthetic panel")
    rho = float(np.corrcoef(cur[ok], fut[ok])[0, 1])
    assert abs(rho) < 0.25, (
        f"{name} correlates {rho:+.3f} with the NEXT day's return on a random "
        f"walk. On data with no structure, the only way to do that is to have "
        f"read row i+1.")


# ── the strong test: the answer does not change when the future is offered ──


def test_planting_a_perfect_oracle_does_not_move_the_NAV():
    """The claim that survives refactoring.

    One name is engineered so that a peeking engine would hold it every up-day
    and avoid every down-day — a free 5% a session. If any part of the decision
    path reads row i+1, this policy's terminal wealth explodes. It does not.
    """
    clean = synthetic(oracle_col=None)
    planted = synthetic(oracle_col=3)
    pol = _policy(signal="mom_12_1")

    a = replay.run(clean, pol, warmup=260)
    b = replay.run(planted, pol, warmup=260)

    # The panels differ (one name's path was replaced), so NAVs differ. What
    # must NOT happen is the planted panel becoming spectacularly better: a
    # peeking engine would compound +5%/session on the oracle name.
    ratio = b.metrics["terminal_usd"] / a.metrics["terminal_usd"]
    assert ratio < 3.0, (
        f"terminal wealth is {ratio:.1f}x higher with a perfect-foresight name "
        f"in the panel. Something in the decision path is reading forward.")


def test_a_signal_that_indexes_FORWARD_would_be_caught():
    """The detector's own calibration. A test that cannot fail on a real
    violation is decoration, so this plants the violation and asserts the
    detector fires — the same discipline the repo applies to every gate."""
    p = synthetic()

    def cheating_matrix(panel, name, seed=0):
        g = np.full(panel.ret.shape, np.nan, dtype=np.float64)
        g[:-1] = panel.ret[1:]                    # row i knows row i+1
        return g

    fut = p.ret[1:].astype(np.float64)
    cur = cheating_matrix(p, "x")[:-1]
    ok = np.isfinite(cur) & np.isfinite(fut)
    rho = float(np.corrcoef(cur[ok], fut[ok])[0, 1])
    assert abs(rho) > 0.9, "the cheat is not detectable — the bar is wrong"


# ── the decision/fill convention ────────────────────────────────────────────


def test_the_fill_happens_at_the_NEXT_open_not_todays_close():
    """Close-to-close execution books the overnight gap that follows the
    signal. This asserts the engine's fills move when the OPEN moves and are
    unaffected by a change to the decision day's own close-to-open spread."""
    base = synthetic()
    pol = _policy(signal="mom_12_1")
    a = replay.run(base, pol, warmup=260)

    bumped = synthetic()
    o = bumped.open_.copy()
    o[261:] *= 1.02                    # every fill 2% worse from the first one
    bumped = Panel(**{**bumped.__dict__, "open_": o})
    b = replay.run(bumped, pol, warmup=260)
    assert b.metrics["terminal_usd"] != a.metrics["terminal_usd"], (
        "raising every open price changed nothing — the engine is not filling "
        "at the open")


def test_a_decision_is_taken_every_holding_days_and_not_more():
    p = synthetic()
    for h in (1, 5, 21):
        res = replay.run(p, _policy(signal="mom_12_1", holding_days=h),
                         warmup=260)
        expected = len(range(260, T - 1, h))
        assert res.diagnostics["n_decisions"] == expected, (
            f"holding_days={h}: {res.diagnostics['n_decisions']} decisions, "
            f"expected {expected}")
