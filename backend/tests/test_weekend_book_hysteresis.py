"""VALIDATION of `learner.evaluate.book(..., hold_k=...)` -- turnover hysteresis.

THE TWO CLAIMS THE CHANGE MAKES, AND WHY EACH NEEDS ITS OWN TEST
================================================================
1. **`hold_k=None` is the v1 rule, untouched.** `evaluate.py`'s own docstring
   promises v1's receipt reproduces byte for byte. A parameter that quietly
   perturbs the default path would re-date every published learner number, and
   nothing in the receipt would say so. So the default path is checked against
   an INDEPENDENT reimplementation of the documented rule -- top-k by
   prediction, cap-weighted, half-L1 weight turnover, both sides costed --
   rather than against a golden file this repo could have written wrong twice.

2. **`hold_k > k` reduces turnover and nothing else structural.** The band is
   supposed to cost less, not to select differently in kind: the book must stay
   exactly `k` names, and on a panel whose ranking never churns the band must be
   a strict no-op. A "hysteresis" that shrinks the book would cut costs by
   holding fewer names, which is a different strategy wearing the same label.

A SILENT NO-OP IS THE HOUSE FAILURE MODE, so `test_hysteresis_is_not_inert`
asserts the band actually changes the holdings on a churning panel. A test that
only checks "turnover did not go up" would pass on a parameter that does
nothing at all.

Offline, seeded, no calendar moment: months are derived from `today`.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from learner import evaluate as E


N_MONTHS = 24
N_NAMES = 40
K = 5
HOLD_K = 12


def _months(n: int = N_MONTHS) -> list[str]:
    """`n` consecutive YYYY-MM labels ending at the month before today.

    Derived from `today`, never written down: a literal month in a fixture is a
    calendar moment, and CLAUDE.md's session protocol #5 exists because one of
    those rotted the day after it passed.
    """
    end = dt.date.today().replace(day=1)
    out = []
    for back in range(n, 0, -1):
        y, m = divmod((end.year * 12 + end.month - 1) - back, 12)
        out.append(f"{y:04d}-{m + 1:02d}")
    return out


def _panel(churn: bool, seed: int = 7) -> pd.DataFrame:
    """One row per (month, name). `churn=False` freezes the ranking forever.

    Predictions are drawn from a continuous distribution and then made strictly
    distinct within each month, so the ranking has NO ties and the expected
    selection is unambiguous without reimplementing the tie-break.
    """
    rng = np.random.default_rng(seed)
    months = _months()
    rows = []
    static_score = rng.normal(size=N_NAMES)
    caps = rng.uniform(1e8, 5e10, size=N_NAMES)
    for i, m in enumerate(months):
        score = static_score if not churn else rng.normal(size=N_NAMES)
        mkt = float(rng.normal(0.008, 0.03))
        for j in range(N_NAMES):
            rows.append({
                "month": m,
                "permno": 10_000 + j,
                # a tiny distinct offset per name kills exact ties without
                # reordering anything drawn from a continuous distribution
                "pred": float(score[j]) + j * 1e-12,
                "fwd_1m": float(rng.normal(0.01, 0.06)),
                "mkt_vw_1m": mkt,
                "market_cap": float(caps[j]),
            })
    df = pd.DataFrame(rows)
    assert df.groupby("month")["pred"].apply(lambda s: s.duplicated().any()).sum() == 0
    return df


def _expected_v1(df: pd.DataFrame, k: int, cost_bps: float = E.COST_BPS_PER_SIDE) -> dict:
    """The v1 rule, written out independently: top-k by prediction each month,
    cap-weighted, half-L1 weight turnover with a full first month, both sides
    costed. This is the oracle the default path is checked against."""
    gross, mkt, weights = {}, {}, {}
    for m, chunk in df.groupby("month", sort=True):
        sel = chunk.sort_values("pred", ascending=False).head(k)
        w = sel["market_cap"] / sel["market_cap"].sum()
        gross[m] = float((w.to_numpy() * sel["fwd_1m"].to_numpy()).sum())
        mkt[m] = float(sel["mkt_vw_1m"].iloc[0])
        weights[m] = dict(zip(sel["permno"].astype(int), w.to_numpy()))
    g = pd.Series(gross).sort_index()
    mk = pd.Series(mkt).sort_index()
    turn, prev = [], None
    for m in g.index:
        cur = weights[m]
        if prev is None:
            turn.append(1.0)
        else:
            keys = set(cur) | set(prev)
            turn.append(0.5 * sum(abs(cur.get(x, 0.0) - prev.get(x, 0.0)) for x in keys))
        prev = cur
    t = pd.Series(turn, index=g.index)
    net = g - t * (cost_bps / 10_000.0) * 2.0
    spread = net - mk
    return {
        "months": int(len(net)),
        "mean_turnover": round(float(t.mean()), 3),
        "terminal_wealth_net": round(float((1.0 + net).prod()), 4),
        "terminal_wealth_gross": round(float((1.0 + g).prod()), 4),
        "terminal_wealth_market_same_months": round(float((1.0 + mk).prod()), 4),
        "mean_monthly_excess": round(float(spread.mean()), 5),
        "worst_month_net": round(float(net.min()), 4),
        "hit_rate": round(float((net > 0).mean()), 4),
        "holdings": {m: set(w) for m, w in weights.items()},
    }


# ----------------------------------------- 1. the default path did not move


def test_hold_k_none_reproduces_the_v1_rule_number_for_number():
    """Every v1 number, against an independent reimplementation."""
    df = _panel(churn=True)
    got = E.book(df, "pred", k=K, weight="vw")
    want = _expected_v1(df, K)

    for key in ("months", "mean_turnover", "terminal_wealth_net",
                "terminal_wealth_gross", "terminal_wealth_market_same_months",
                "mean_monthly_excess", "worst_month_net", "hit_rate"):
        assert got[key] == want[key], f"{key}: book gave {got[key]}, the v1 rule gives {want[key]}"
    assert got["hold_k"] is None
    assert got["selection_rule"] == f"top-{K} rebuilt every month"
    assert got["mean_names_per_month"] == float(K)


def test_hold_k_none_selects_exactly_the_top_k_every_month():
    """The selection itself, not just the aggregate it rolls up to. Two
    different books can share a terminal wealth by accident; they cannot share
    every month's holdings by accident."""
    df = _panel(churn=True)
    want = _expected_v1(df, K)["holdings"]
    got = E.book(df, "pred", k=K, weight="vw", return_series=True)
    # reconstruct the realised holdings from the per-month gross return: with
    # distinct predictions there is exactly one top-k, so matching the monthly
    # gross series for every month pins the selection.
    series = got["_series"]["gross"]
    for m, chunk in df.groupby("month", sort=True):
        sel = chunk[chunk["permno"].isin(want[m])]
        w = sel["market_cap"] / sel["market_cap"].sum()
        assert float((w.to_numpy() * sel["fwd_1m"].to_numpy()).sum()) == pytest.approx(
            float(series[m]), abs=1e-12), f"month {m} did not hold the top {K}"
        assert len(want[m]) == K


def test_the_v2_flags_still_do_not_move_the_v1_numbers():
    """`with_risk` / `return_series` / an explicit `hold_k=None` must all leave
    every shared key identical -- the guarantee the v1 receipt rests on."""
    df = _panel(churn=True)
    base = E.book(df, "pred", k=K, weight="vw")
    for kwargs in ({"with_risk": True}, {"return_series": True}, {"hold_k": None}):
        other = E.book(df, "pred", k=K, weight="vw", **kwargs)
        for key in base:
            assert base[key] == other[key], f"{key} moved under {kwargs}"


# ------------------------------------------------ 2. the band, and its refusal


@pytest.mark.parametrize("hold_k", [1, 4, 5])
def test_hold_k_at_or_below_k_refuses(hold_k):
    """A band no wider than the buy rank is the no-hysteresis rule written a
    longer way, and the receipt would report a band where there is none."""
    df = _panel(churn=True)
    with pytest.raises(SystemExit, match="REFUSED"):
        E.book(df, "pred", k=K, weight="vw", hold_k=hold_k)


def test_hold_k_just_above_k_is_accepted():
    """The refusal must be strict-inequality, not an off-by-one that also bans
    the narrowest legal band."""
    df = _panel(churn=True)
    res = E.book(df, "pred", k=K, weight="vw", hold_k=K + 1)
    assert res["hold_k"] == K + 1
    assert res["months"] > 0


def test_hysteresis_strictly_reduces_turnover_on_a_churning_panel():
    df = _panel(churn=True)
    plain = E.book(df, "pred", k=K, weight="vw")
    band = E.book(df, "pred", k=K, weight="vw", hold_k=HOLD_K)
    assert band["mean_turnover"] < plain["mean_turnover"], (
        f"hold_k={HOLD_K} turnover {band['mean_turnover']} did not fall below the "
        f"rebuild-every-month {plain['mean_turnover']}")


@pytest.mark.parametrize("hold_k", [8, 12, 20, 30])
def test_turnover_falls_monotonically_as_the_band_widens(hold_k):
    """Not just "lower than none": a wider band must hold longer. A band that
    reduced turnover by a constant regardless of its width would not be
    hysteresis."""
    df = _panel(churn=True)
    narrow = E.book(df, "pred", k=K, weight="vw", hold_k=K + 1)["mean_turnover"]
    wide = E.book(df, "pred", k=K, weight="vw", hold_k=hold_k)["mean_turnover"]
    assert wide <= narrow, f"hold_k={hold_k} turned over more than hold_k={K + 1}"


def test_the_book_stays_exactly_k_names_under_hysteresis():
    """The band changes how often the book pays the spread. It must not change
    how many names the book holds -- a smaller book is a different strategy."""
    df = _panel(churn=True)
    for hk in (K + 1, HOLD_K, 30):
        res = E.book(df, "pred", k=K, weight="vw", hold_k=hk, return_series=True)
        assert res["mean_names_per_month"] == float(K), (
            f"hold_k={hk} produced {res['mean_names_per_month']} names/month, not {K}")
        # weights must still be a full allocation every month
        for m, w in res["_series"]["net"].items():
            assert np.isfinite(w)


def _expected_hysteresis(df: pd.DataFrame, k: int, hold_k: int) -> dict:
    """The banded rule written out from its PROSE, independently of the module.

    "BUY at rank <= k, HOLD until rank > hold_k. Incumbents inside the band keep
    their slots, best-ranked first; the remainder is filled from the top of the
    ranking." One month at a time, returning the holdings so the comparison is
    on the selection itself and not on an aggregate that could agree by luck.
    """
    holdings, gross, held = {}, {}, set()
    for m, chunk in df.groupby("month", sort=True):
        ranked = chunk.sort_values("pred", ascending=False)
        band = ranked.head(hold_k)
        keep = band[band["permno"].isin(held)].head(k)
        keep_ids = set(keep["permno"])
        fill = ranked[~ranked["permno"].isin(keep_ids)].head(max(0, k - len(keep)))
        sel = pd.concat([keep, fill]) if len(fill) else keep
        held = set(sel["permno"])
        holdings[m] = set(held)
        w = sel["market_cap"] / sel["market_cap"].sum()
        gross[m] = float((w.to_numpy() * sel["fwd_1m"].to_numpy()).sum())
    return {"holdings": holdings, "gross": pd.Series(gross).sort_index()}


@pytest.mark.parametrize("hold_k", [K + 1, HOLD_K, 30])
def test_hysteresis_selects_exactly_what_the_documented_rule_selects(hold_k):
    """The banded selection, month by month, against the prose rule."""
    df = _panel(churn=True)
    want = _expected_hysteresis(df, K, hold_k)
    got = E.book(df, "pred", k=K, weight="vw", hold_k=hold_k, return_series=True)
    series = got["_series"]["gross"]
    assert list(series.index) == list(want["gross"].index)
    for m in series.index:
        assert float(series[m]) == pytest.approx(float(want["gross"][m]), abs=1e-12), (
            f"month {m}: the band selected something other than the documented rule")


def test_every_held_name_sits_inside_the_band():
    """No name outside the top `hold_k` of its own month's ranking may survive.

    Checked on the holdings themselves (via the prose reimplementation the test
    above pins to the module), not on a range the gross return happens to fall
    in -- that check passes vacuously whenever the band is wide."""
    df = _panel(churn=True)
    want = _expected_hysteresis(df, K, HOLD_K)
    for m, chunk in df.groupby("month", sort=True):
        band = set(chunk.sort_values("pred", ascending=False).head(HOLD_K)["permno"])
        held = want["holdings"][m]
        assert len(held) == K
        assert held <= band, f"month {m} held {held - band} from outside the top {HOLD_K}"


def test_incumbents_are_actually_carried_across_months():
    """The mechanism, not its side effect: on a churning panel the banded book
    must retain names the rebuild-every-month book would have sold."""
    df = _panel(churn=True)
    banded = _expected_hysteresis(df, K, HOLD_K)["holdings"]
    plain = _expected_v1(df, K)["holdings"]
    months = sorted(banded)
    carried_band = sum(len(banded[a] & banded[b]) for a, b in zip(months, months[1:]))
    carried_plain = sum(len(plain[a] & plain[b]) for a, b in zip(months, months[1:]))
    assert carried_band > carried_plain, (
        f"the band carried {carried_band} name-months across rebalances vs the plain "
        f"book's {carried_plain} -- nothing was actually held")


def test_hysteresis_is_a_strict_no_op_when_the_ranking_never_churns():
    """A frozen ranking means the top-k never leaves the band, so the band can
    change nothing. Every v1 number must be identical."""
    df = _panel(churn=False)
    plain = E.book(df, "pred", k=K, weight="vw")
    band = E.book(df, "pred", k=K, weight="vw", hold_k=HOLD_K)
    for key in plain:
        if key in ("hold_k", "selection_rule"):
            continue
        assert plain[key] == band[key], f"{key} moved on a panel with no churn"


def test_hysteresis_is_not_inert():
    """THE SILENT NO-OP GUARD. Every other test here would pass on a `hold_k`
    that was accepted, echoed into the receipt, and then ignored. This one
    fails unless the band actually changes the book."""
    df = _panel(churn=True)
    plain = E.book(df, "pred", k=K, weight="vw", return_series=True)
    band = E.book(df, "pred", k=K, weight="vw", hold_k=HOLD_K, return_series=True)
    differing = int((plain["_series"]["gross"] != band["_series"]["gross"]).sum())
    assert differing > 0, (
        "hold_k produced a byte-identical monthly gross series on a churning panel -- "
        "the band was accepted and then ignored")
    assert plain["terminal_wealth_gross"] != band["terminal_wealth_gross"]


def test_the_receipt_names_the_rule_it_ran():
    """The selection rule is in the receipt in words, so a later reader cannot
    mistake a banded book for a rebuilt one."""
    df = _panel(churn=True)
    res = E.book(df, "pred", k=K, weight="vw", hold_k=HOLD_K)
    assert res["selection_rule"] == f"buy at rank <= {K}, hold until rank > {HOLD_K}"
    assert res["hold_k"] == HOLD_K


def test_costs_are_never_omitted_under_hysteresis():
    """Costs are one of the four things that never relax. A band that reduces
    turnover must still pay for the turnover it has: net < gross whenever any
    trading happened at a positive cost rate."""
    df = _panel(churn=True)
    res = E.book(df, "pred", k=K, weight="vw", hold_k=HOLD_K, cost_bps=25.0)
    assert res["mean_turnover"] > 0
    assert res["terminal_wealth_net"] < res["terminal_wealth_gross"]
    assert res["cost_bps_per_side"] == 25.0
