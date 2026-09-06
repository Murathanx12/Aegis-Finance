"""The growth lab's latches, levers and overlays — on planted worlds.

Every test here is ALGEBRAIC where it can be: the expected number is written
out from the construction rather than asserted inside a tolerance band, so a
sign error or a double-charged spread goes red instead of drifting.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from learner import growth_lab as GL


# --------------------------------------------------------------- the latch

def _months(a: str, b: str) -> list[str]:
    return [f"{y}-{m:02d}" for y in range(int(a[:4]), int(b[:4]) + 1)
            for m in range(1, 13) if a <= f"{y}-{m:02d}" <= b]


def _series(a: str, b: str, value: float = 0.01) -> pd.Series:
    idx = _months(a, b)
    return pd.Series([value] * len(idx), index=pd.Index(idx, name="month"))


def test_dev_slice_stops_at_2015_and_starts_at_the_common_window():
    s = _series("1999-01", "2024-12")
    d = GL.dev(s)
    assert d.index[0] == GL.COMMON_DEV_START
    assert d.index[-1] == GL.DEV_END
    assert len(d) == 12 * 12                      # 2004-01 .. 2015-12


def test_dev_slice_can_be_asked_for_the_full_development_era():
    d = GL.dev(_series("1999-01", "2024-12"), start=GL.DEV_START)
    assert d.index[0] == "1999-01" and d.index[-1] == GL.DEV_END


def test_assert_development_only_raises_on_a_series_that_reaches_the_sealed_era():
    with pytest.raises(GL.SealedEraViolation) as e:
        GL.assert_development_only(_series("2014-01", "2016-03"), "planted book")
    msg = str(e.value)
    assert "planted book" in msg and "2016-01" in msg


def test_assert_development_only_passes_on_a_development_series():
    GL.assert_development_only(_series("1999-01", "2015-12"))


def test_sealed_writes_one_append_only_line_per_opening(tmp_path):
    led = tmp_path / "openings.jsonl"
    s = _series("2004-01", "2024-12")
    out = GL.sealed(s, champion_id="planted_v1", champion_sha256="deadbeef",
                    reason="unit test", ledger=led)
    assert out.index[0] == GL.SEALED_START and out.index[-1] == GL.SEALED_END
    assert GL.openings_for("planted_v1", ledger=led) == 1
    GL.sealed(s, champion_id="planted_v1", champion_sha256="deadbeef",
              reason="a second, accidental opening", ledger=led)
    # the ledger is APPEND-ONLY: the second call cannot un-write the first,
    # which is the whole point -- the count is evidence, not a setting.
    assert GL.openings_for("planted_v1", ledger=led) == 2
    assert GL.openings_for("some_other_champion", ledger=led) == 0
    lines = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert [l["months_returned"] for l in lines] == [len(out), len(out)]


def test_openings_for_reads_a_missing_ledger_as_zero_not_as_an_error(tmp_path):
    assert GL.openings_for("nobody", ledger=tmp_path / "absent.jsonl") == 0


# ------------------------------------------------------------- the levers

def test_exposure_one_is_the_risky_leg_minus_exactly_one_entry_cost():
    r = _series("2004-01", "2004-06", 0.02)
    rf = _series("2004-01", "2004-06", 0.001)
    w = pd.Series(1.0, index=r.index)
    net, meta = GL._exposure_return(r, rf, w, cost_bps=10.0)
    assert net.iloc[0] == pytest.approx(0.02 - 10.0 / 10_000.0)
    assert list(net.iloc[1:]) == pytest.approx([0.02] * 5)
    assert meta["mean_exposure"] == 1.0


def test_exposure_zero_earns_the_risk_free_leg_and_is_not_free_cash():
    r = _series("2004-01", "2004-03", 0.05)
    rf = _series("2004-01", "2004-03", 0.004)
    w = pd.Series(0.0, index=r.index)
    net, _ = GL._exposure_return(r, rf, w, cost_bps=25.0)
    # nothing is bought, so nothing is traded and nothing is paid; the parked
    # dollar earns RF. A book that reported 0.0 here would be the cash-drag
    # error the amendment names.
    assert list(net) == pytest.approx([0.004, 0.004, 0.004])


def test_exposure_two_borrows_at_rf_plus_the_financing_spread():
    r = _series("2004-01", "2004-02", 0.03)
    rf = _series("2004-01", "2004-02", 0.002)
    w = pd.Series(2.0, index=r.index)
    net, _ = GL._exposure_return(r, rf, w, cost_bps=0.0,
                                 financing_bps=GL.FINANCING_BPS)
    spread = GL.FINANCING_BPS / 10_000.0 / 12
    assert list(net) == pytest.approx([2 * 0.03 - (0.002 + spread)] * 2)


def test_a_change_of_exposure_pays_the_spread_on_the_risky_leg_only():
    r = _series("2004-01", "2004-03", 0.0)
    rf = _series("2004-01", "2004-03", 0.0)
    w = pd.Series([1.0, 0.0, 1.0], index=r.index)
    net, meta = GL._exposure_return(r, rf, w, cost_bps=10.0)
    bps = 10.0 / 10_000.0
    # |dw| is 1, 1, 1 -- one side each time, not two: moving to T-bills is not
    # a round trip in the book.
    assert list(net) == pytest.approx([-bps, -bps, -bps])
    assert meta["mean_abs_exposure_change"] == pytest.approx(1.0)


# ------------------------------------------------------------- the overlays

def _ctx_for(idx, *, trend_on=True, rf=0.0) -> pd.DataFrame:
    return pd.DataFrame({
        "rf": pd.Series(rf, index=idx),
        "trend_on": pd.Series(bool(trend_on), index=idx),
    })


def test_the_drawdown_overlay_cannot_see_the_month_it_is_sizing():
    """A book whose ONLY loss is in its last month must be UNSCALED there.

    The overlay reads a trailing drawdown lagged one month. If the lag were
    dropped, the last month's exposure would fall and the overlay would be
    reading the outcome it is supposed to precede -- which is the single most
    profitable bug available in this file.
    """
    idx = _months("2004-01", "2004-12")
    net = pd.Series([0.01] * 11 + [-0.30], index=pd.Index(idx))
    out, meta = GL.apply_overlays(net, _ctx_for(idx), ("dd",), cost_bps=0.0)
    assert meta["per_overlay"]["dd"]["min"] == pytest.approx(1.0)
    assert out.iloc[-1] == pytest.approx(-0.30)


def test_the_drawdown_overlay_does_scale_the_month_after_the_loss():
    idx = _months("2004-01", "2005-02")
    net = pd.Series([0.01] * 11 + [-0.30] + [0.01] * (len(idx) - 12),
                    index=pd.Index(idx))
    out, meta = GL.apply_overlays(net, _ctx_for(idx), ("dd",), cost_bps=0.0)
    assert meta["per_overlay"]["dd"]["min"] < 1.0
    expected_w = max(GL.DD_FLOOR, min(1.0, 1.0 - 0.30 / GL.DD_SCALE))
    assert out.iloc[12] == pytest.approx(expected_w * 0.01)


def test_the_trend_gate_moves_the_whole_book_to_the_risk_free_leg():
    idx = _months("2004-01", "2004-04")
    net = pd.Series(0.05, index=pd.Index(idx))
    ctx = _ctx_for(idx, rf=0.003)
    ctx["trend_on"] = [True, False, False, True]
    out, meta = GL.apply_overlays(net, ctx, ("tg",), cost_bps=0.0)
    assert list(out) == pytest.approx([0.05, 0.003, 0.003, 0.05])
    assert meta["per_overlay"]["tg"]["min"] == 0.0


def test_two_overlays_compose_on_exposure_and_charge_the_spread_once():
    """Composing on RETURNS would pay the spread twice on one trade."""
    idx = _months("2004-01", "2005-06")
    rng = np.random.default_rng(20260907)
    net = pd.Series(rng.normal(0.005, 0.04, len(idx)), index=pd.Index(idx))
    ctx = _ctx_for(idx, rf=0.002)
    ctx["trend_on"] = [True] * 10 + [False] * 4 + [True] * (len(idx) - 14)
    both, mb = GL.apply_overlays(net, ctx, ("dd", "tg"), cost_bps=25.0)
    once, m1 = GL.apply_overlays(net, ctx, ("tg",), cost_bps=25.0)
    twice, _ = GL.apply_overlays(once, ctx, ("dd",), cost_bps=25.0)
    assert mb["per_overlay"].keys() == {"dd", "tg"}
    assert not np.allclose(both.to_numpy(), twice.to_numpy())
    assert mb["overlay_cost_annual_pct"] < (
        m1["overlay_cost_annual_pct"] * 2 + 1e-9)


def test_an_unknown_overlay_refuses_rather_than_passing_through():
    idx = _months("2004-01", "2004-06")
    with pytest.raises(SystemExit) as e:
        GL.apply_overlays(pd.Series(0.01, index=pd.Index(idx)),
                          _ctx_for(idx), ("no_such_overlay",), cost_bps=10.0)
    assert "REFUSED" in str(e.value)


# ------------------------------------------------------------- the blend

def test_a_fifty_fifty_blend_of_a_series_with_itself_is_that_series():
    s = _series("2004-01", "2005-12", 0.013)
    out = GL.build_blend([(s, 0.5), (s, 0.5)])
    assert out.to_numpy() == pytest.approx(s.to_numpy())


def test_a_blend_is_taken_on_the_common_months_only():
    a = _series("2004-01", "2010-12", 0.02)
    b = _series("2006-01", "2015-12", 0.00)
    out = GL.build_blend([(a, 0.5), (b, 0.5)])
    assert out.index[0] == "2006-01" and out.index[-1] == "2010-12"
    assert out.to_numpy() == pytest.approx(0.01)


# --------------------------------------------------------- market context

def test_market_context_compounds_over_the_books_own_window(tmp_path, monkeypatch):
    """The market leg is the product over (entry[m], entry[m+1]], exactly.

    Not the calendar month. The book labelled 2020-02 is the book ENTERED on
    2020-02-21, and grading it against calendar February is two different
    months wearing one label.
    """
    days = pd.bdate_range("2004-01-05", "2004-05-31")
    spy = pd.Series(0.001, index=days)
    csv = tmp_path / "spy.csv"
    pd.DataFrame({"Date": days, "spy_tr": spy.to_numpy()}).to_csv(csv, index=False)
    monkeypatch.setattr(GL, "SPY_CSV", csv)
    monkeypatch.setattr(GL, "SPY_META", tmp_path / "absent.json")
    monkeypatch.setattr(GL, "_rf_daily", lambda tracker=None: pd.Series(0.0, index=days))

    entries = [pd.Timestamp("2004-01-15"), pd.Timestamp("2004-02-17"),
               pd.Timestamp("2004-03-16")]
    panel = pd.DataFrame({"month": ["2004-01", "2004-02", "2004-03"],
                          "entry_date": entries})
    ctx = GL.market_context(panel)
    assert list(ctx.index) == ["2004-01", "2004-02"]        # the last is dropped
    n = int(((days > entries[0]) & (days <= entries[1])).sum())
    assert ctx.loc["2004-01", "spy"] == pytest.approx(1.001 ** n - 1.0)
    assert ctx.loc["2004-01", "next_entry"] == entries[1]


def test_market_context_refuses_when_the_pinned_tape_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(GL, "SPY_CSV", tmp_path / "nope.csv")
    with pytest.raises(SystemExit) as e:
        GL.market_context(pd.DataFrame({"month": ["2004-01"],
                                        "entry_date": [pd.Timestamp("2004-01-15")]}))
    assert "REFUSED" in str(e.value) and "PINNED" in str(e.value)


# ------------------------------------------------- genomes and declaration

def test_generation_zero_ids_are_unique_and_every_overlay_key_is_known():
    G = GL.generation_zero()
    ids = [g.genome_id for g in G]
    assert len(ids) == len(set(ids))
    for g in G:
        for k in g.overlay:
            assert k in GL.OVERLAYS
        if g.parent_ids:
            assert all(p in ids for p in g.parent_ids)


def test_generation_zero_carries_every_family_the_amendment_names():
    fams = {g.family for g in GL.generation_zero()}
    assert {"index", "momentum", "quality", "learner", "blend"} <= fams


def test_a_genome_hash_is_the_recipe_and_not_its_name():
    a = GL.Genome("a", "f", "panel", {"pred_col": "x"})
    b = GL.Genome("b_renamed", "f", "panel", {"pred_col": "x"})
    c = GL.Genome("c", "f", "panel", {"pred_col": "y"})
    assert a.sha256() == b.sha256()
    assert a.sha256() != c.sha256()
    assert GL.Genome("a", "f", "panel", {"pred_col": "x"}, ("dd",)).sha256() != a.sha256()


def test_the_declaration_hash_ignores_its_own_timestamp():
    G = GL.generation_zero()
    d1 = GL.declaration(G)
    d2 = dict(d1, declared_utc="1999-01-01T00:00:00+00:00")
    assert GL.declaration_sha256(d1) == GL.declaration_sha256(d2)
    d3 = GL.declaration(G[:-1])
    assert GL.declaration_sha256(d3) != GL.declaration_sha256(d1)


def test_the_declaration_states_the_split_and_the_ranking_metric():
    d = GL.declaration(GL.generation_zero())
    assert d["eras"]["sealed_test"] == [GL.SEALED_START, GL.SEALED_END]
    assert d["eras"]["development_common_grading_window"] == [GL.COMMON_DEV_START, GL.DEV_END]
    assert "leverage-neutral" in d["ranking_metric"]
    assert d["licence"] == "PRODUCT_EXPERIMENT"
    assert len(d["generation_0_genomes"]) == d["generation_0_size"]


def test_the_shipped_declaration_on_disk_still_hashes_to_its_recorded_value():
    """The receipt's `declaration_sha256` must be reproducible from the file.

    A declaration whose hash cannot be recomputed is a declaration, not a
    commitment.
    """
    if not GL.DECLARATION.exists():
        pytest.skip("G2 has not been run in this checkout")
    d = json.loads(GL.DECLARATION.read_text(encoding="utf-8"))
    assert GL.declaration_sha256(d) == d["sha256"]
