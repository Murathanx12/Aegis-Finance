"""The matched twin's cost convention (CHUNK C1, 2026-10-06).

Until 2026-10-06 the bridges board charged the twin a full Corwin-Schultz round trip every
month while the rule paid only its own turnover; 106 of 161 "beats its twin" results were 18
on gross selection. These tests pin the one convention every board now imports
(`matched_twins.TWIN_COST_CONVENTION`), the four columns every board row prints, and that no
board path still nets the full-round-trip twin outside the labelled upper bound.

Synthetic data only; no calendar literal (dates derive from today); no panel parquet is read.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import matched_twins as MT

REPO = Path(__file__).resolve().parents[2]
BASE = pd.Timestamp.today().normalize() - pd.DateOffset(years=8)


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range(BASE, periods=n, freq="BME")


# ── (a) the convention ───────────────────────────────────────────────────────

def test_a_zero_turnover_twin_pays_zero_cost():
    assert MT.turnover_cost(0.0, 0.04) == 0.0
    w = {"a": 0.5, "b": 0.5}
    cost, to = MT.trade_cost(w, dict(w), {"a": 0.05, "b": 0.08}, 0.0035)
    assert cost == 0.0 and to == 0.0
    flat = pd.Series([0.01, 0.02, -0.01], index=_idx(3))
    full = flat - 0.03                                   # a full round trip charged every month
    pd.testing.assert_series_equal(MT.turnover_scaled_net(flat, full, 0.0), flat)


def test_a_twin_with_the_rules_turnover_pays_the_rules_cost():
    spread = {"a": 0.02, "b": 0.02, "c": 0.02, "d": 0.02}
    rule_cost, rule_to = MT.trade_cost({"a": 0.5, "b": 0.5}, {"a": 0.5, "c": 0.5}, spread, 0.0035)
    twin_cost, twin_to = MT.trade_cost({"b": 0.5, "d": 0.5}, {"b": 0.5, "a": 0.5}, spread, 0.0035)
    assert rule_to == twin_to == pytest.approx(0.5)
    assert twin_cost == pytest.approx(rule_cost) == pytest.approx(MT.turnover_cost(0.5, 0.02))
    flat = pd.Series([0.01, 0.0, 0.02], index=_idx(3))
    full = flat - 0.02
    r = MT.turnover_scaled_net(flat, full, 0.3)
    t = MT.turnover_scaled_net(flat.copy(), full.copy(), 0.3)
    pd.testing.assert_series_equal(r, t)                 # same function, same turnover, same charge
    assert float((flat - r).iloc[0]) == pytest.approx(0.3 * 0.02)


def test_a_missing_turnover_refuses_instead_of_defaulting_to_a_full_round_trip():
    with pytest.raises(MT.TwinInputMissing):
        MT.turnover_cost(None, 0.02)
    with pytest.raises(MT.TwinInputMissing):
        MT.turnover_cost(-0.1, 0.02)
    with pytest.raises(MT.TwinInputMissing):
        MT.turnover_cost(float("nan"), 0.02)


def test_a_the_convention_is_one_constant_and_one_docstring():
    assert MT.twin_cost_convention() == MT.TWIN_COST_CONVENTION
    doc = MT.twin_cost_convention.__doc__ or ""
    assert "OWN" in doc and "never a flat full round trip" in doc
    assert MT.UPPER_BOUND_COLUMN == MT.FOUR_COLUMNS[-1] and "UPPER_BOUND" in MT.UPPER_BOUND_COLUMN


def test_a_the_per_trade_model_is_imported_not_retyped():
    from backend.services import hyp_investable as HI
    from scripts import conditionals_on_crsp as C
    assert HI.trade_cost is MT.trade_cost and C.trade_cost is MT.trade_cost


def test_a_upper_bound_charges_a_full_round_trip_on_every_name():
    assert MT.twin_full_round_trip_upper_bound({"a": 0.25, "b": 0.75}, {"a": 0.04, "b": 0.02}, 0.0035) == \
        pytest.approx(0.25 * 0.04 + 0.75 * 0.02)


# ── (b) every board row carries all four columns ─────────────────────────────

def _book(n: int = 36, twin_turnover: float = 0.0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(7)
    idx = _idx(n)
    gross = pd.Series(rng.normal(0.01, 0.04, n), index=idx)
    twin_gross = gross - 0.002 + pd.Series(rng.normal(0, 0.01, n), index=idx)
    B = pd.DataFrame({"gross": gross, "cost": 0.0008, "turnover": 0.2, "twin_gross": twin_gross,
                      "twin_cost": twin_turnover * 0.02, "twin_turnover": twin_turnover,
                      "twin_full_rt": 0.02}, index=idx)
    return B, pd.Series(rng.normal(0.008, 0.04, n), index=idx)


def test_b_four_columns_values():
    B, mkt = _book(twin_turnover=0.0)
    F = MT.four_columns(B["gross"], B["cost"], B["twin_gross"], B["twin_cost"], B["twin_full_rt"], mkt)
    assert tuple(F.columns) == MT.FOUR_COLUMNS
    np.testing.assert_allclose(F["pure_selection"], B["gross"] - B["twin_gross"])
    # a zero-turnover twin pays nothing: fair = selection - the rule's own cost
    np.testing.assert_allclose(F["fair_twin_net"], F["pure_selection"] - B["cost"])
    np.testing.assert_allclose(F["twin_full_round_trip_UPPER_BOUND"], F["fair_twin_net"] + 0.02)
    np.testing.assert_allclose(F["net_minus_market"], B["gross"] - B["cost"] - mkt)


def test_b_fair_twin_board_row_has_all_four_columns_and_year_reads():
    from scripts import hyp_twin_board as TB
    B, mkt = _book(twin_turnover=0.15)
    S = TB.fair_series(B, mkt)
    row = TB.fair_row(S, (B["gross"] - B["twin_gross"]))
    for c in MT.FOUR_COLUMNS:
        assert c in row and {"full", "design", "validate", "late", "design_validate"} <= set(row[c])
    for c in ("fair_twin_net", "net_minus_market"):
        assert "by_hold_year" in row[c] and "loo_worst" in row[c]
    assert row["cost_convention"] == MT.TWIN_COST_CONVENTION
    assert row["twin_cost_bps"] == pytest.approx(0.15 * 0.02 * 1e4)


def test_b_fair_series_holds_cash_after_entry_and_refuses_incomplete_frames():
    from scripts import hyp_twin_board as TB
    B, mkt = _book(12)
    B.iloc[:3, B.columns.get_loc("gross")] = np.nan       # before the first position: dropped
    B.iloc[6, B.columns.get_loc("gross")] = np.nan        # gated off later: cash, read vs the market
    S = TB.fair_series(B, mkt)
    assert S.index[0] == B.index[3]
    d = B.index[6]
    assert np.isnan(S.loc[d, "fair_twin_net"]) and np.isnan(S.loc[d, "pure_selection"])
    assert S.loc[d, "net_minus_market"] == pytest.approx(-B.loc[d, "cost"] - mkt.loc[d])
    with pytest.raises(MT.TwinInputMissing):
        TB.fair_series(B.drop(columns=["twin_full_rt"]), mkt)


def test_b_bridges_board_columns_are_read_from_the_fair_series_not_interpolated():
    """Review F1/F2 of C1: the bridges board scaled twin21 by the BASKET's turnover and the rule
    by names-replaced-per-rebalance. It now reads the four columns from the fair board's series,
    where rule and twin are one engine, one turnover function, one cost composition."""
    from scripts import bridges_on_crsp_run as BR
    from scripts import hyp_twin_board as TB
    B, mkt = _book(24, twin_turnover=0.15)
    S = TB.fair_series(B, mkt)
    C = BR.board_columns(S)
    assert tuple(C.columns) == MT.FOUR_COLUMNS
    pd.testing.assert_frame_equal(C, S[list(MT.FOUR_COLUMNS)])
    with pytest.raises(MT.TwinInputMissing):
        BR.board_columns(S.drop(columns=["twin_turnover"]))
    src = (REPO / "scripts/bridges_on_crsp_run.py").read_text(encoding="utf-8")
    assert "turnover_scaled_net(" not in src                         # no two-run interpolation left


def test_b_library_fair_row_carries_old_and_new_headline_and_four_columns():
    from scripts import hyp_twin_board as TB
    from scripts import library_on_crsp as L
    B, mkt = _book(60, twin_turnover=0.1)
    fair = {"status": "OK", **TB.fair_row(TB.fair_series(B, mkt))}
    old = {"rule": "x", "headline": "ALPHA_DETECTED", "full": {"t_blocks": 6.0},
           "calendar": {"verdict": "n/a"}, "ff3_umd_net": {"verdict": "CANNOT_DISTINGUISH"}}
    r = L.fair_headline_row(old, fair)
    assert set(r["four_columns"]) == set(MT.FOUR_COLUMNS)
    assert r["headline_old"] == "ALPHA_DETECTED" and r["headline_fair"] in {
        "FAILED_VARIANT", "ALPHA_DETECTED", "CANNOT_DISTINGUISH", "BETA_EXPLAINS", "CALENDAR_ARTEFACT",
        "NOT_COMPUTED", "NET_EDGE_FROM_TURNOVER"}
    assert "by_hold_year" in r["four_columns"]["fair_twin_net"]


def test_b_bridges_board_refuses_without_a_fair_run(capsys):
    from scripts import bridges_on_crsp_run as BR
    assert BR.part_board("unused", "a", "b", "c", None) == 2
    assert "REFUSED" in capsys.readouterr().out


# ── (c) no board path still nets the full-round-trip twin ────────────────────

BOARD_MODULES = ("scripts/bridges_on_crsp_run.py", "scripts/hyp_twin_board.py", "scripts/library_on_crsp.py",
                 "scripts/hyp_investable.py", "scripts/conditionals_on_crsp.py",
                 "backend/services/hyp_investable.py")


def _tree(rel: str) -> ast.Module:
    return ast.parse((REPO / rel).read_text(encoding="utf-8"))


def _functions_with(tree: ast.Module, pred) -> list:
    """Names of the functions (innermost) containing a node matching `pred`. Docstrings are
    string constants and never match a Subscript / Call / def predicate."""
    hits = []

    def walk(node, fn):
        for ch in ast.iter_child_nodes(node):
            name = ch.name if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if pred(ch):
                hits.append(name)
            walk(ch, name)
    walk(tree, "<module>")
    return hits


def _is_cs_twin(node) -> bool:
    """`<full-CS run frame>["twin21_net"]`: the twin charged a round trip every month."""
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id in {"cs", "cs_", "C_CS", "full", "full_cs"}
            and isinstance(node.slice, ast.Constant) and node.slice.value == "twin21_net")


def _scaled_args(tree: ast.Module) -> set:
    """ids of the argument nodes of every `turnover_scaled_net(...)` call: there the full-CS
    series is an INPUT that the twin's own turnover scales, not a charge."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name == "turnover_scaled_net":
                out |= {id(a) for a in n.args}
    return out


@pytest.mark.parametrize("rel", BOARD_MODULES)
def test_c_full_round_trip_twin_only_inside_an_upper_bound_function(rel):
    tree = _tree(rel)
    ok = _scaled_args(tree)
    bad = [f for f in _functions_with(tree, lambda n: _is_cs_twin(n) and id(n) not in ok)
           if "upper_bound" not in f.lower()]
    assert not bad, f"{rel}: the full-CS twin is netted outside an upper-bound function in {bad}"


@pytest.mark.parametrize("rel", BOARD_MODULES)
def test_c_no_board_module_retypes_the_per_trade_model(rel):
    defs = _functions_with(_tree(rel), lambda n: isinstance(n, ast.FunctionDef) and n.name == "trade_cost")
    assert not defs, f"{rel} defines its own trade_cost; import matched_twins.trade_cost"


def test_c_no_turnover_defaults_to_a_full_round_trip():
    """The 09-29 board read `float(tov) if tov is not None else 1.0`: a missing turnover became
    a full round trip. Any `<x> if <...> is not None else 1.0` on a turnover name is refused."""
    def bad(n) -> bool:
        if not (isinstance(n, ast.IfExp) and isinstance(n.orelse, ast.Constant) and n.orelse.value == 1.0):
            return False
        names = {x.id for x in ast.walk(n.test) if isinstance(x, ast.Name)}
        return any("tov" in s or "turnover" in s for s in names)
    for rel in BOARD_MODULES:
        assert not _functions_with(_tree(rel), bad), rel


@pytest.mark.parametrize("rel", ("scripts/bridges_on_crsp_run.py", "scripts/hyp_twin_board.py",
                                 "scripts/library_on_crsp.py"))
def test_c_every_board_reads_the_shared_convention(rel):
    attrs = {n.attr for n in ast.walk(_tree(rel)) if isinstance(n, ast.Attribute)}
    assert {"TWIN_COST_CONVENTION", "FOUR_COLUMNS"} <= attrs, rel


# ── (d) review of C1 (2026-10-07): one turnover function, weights, the alpha word ─

def _assigned_from_trade_cost(fn: ast.FunctionDef) -> set:
    """Names bound by a tuple-unpack of a `trade_cost(...)` call inside `fn`."""
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            f = n.value.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name == "trade_cost":
                for t in n.targets:
                    out |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
    return out


def _fn(rel: str, name: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(_tree(rel)) if isinstance(n, ast.FunctionDef) and n.name == name)


@pytest.mark.parametrize("rel,name,rule_to,twin_to", [
    ("scripts/hyp_investable.py", "run_book", "to", "tto"),
    ("backend/services/matched_twins.py", "twin_series_sticky", "to", "toj")])
def test_d_rule_and_twin_turnover_come_from_the_same_function_on_the_same_book(rel, name, rule_to, twin_to):
    bound = _assigned_from_trade_cost(_fn(rel, name))
    assert {rule_to, twin_to} <= bound, f"{rel}:{name} binds {bound}"


def test_d_rule_and_twin_turnover_same_units_on_a_real_book():
    """The same book measured as the rule and as the twin gives the same turnover and cost."""
    from scripts import hyp_investable as HIS
    dates = pd.date_range(BASE, periods=4, freq="BME")
    rows = []
    for d in dates:
        for i in range(30):
            rows.append({"date": d, "symbol": f"S{i:02d}", "eligible": True, "fwd_ret": 0.01 * (i % 3),
                         "median_dollar_vol": 3e8, "vol_63": 0.1 + i / 100, "mom_252_21": i / 50,
                         "_sp": 0.01, "mcap": 1e9})
    P = pd.DataFrame(rows)
    picks = {d: [f"S{i:02d}" for i in range(k, k + 5)] for k, d in enumerate(dates)}
    B = HIS.run_book(P, picks, start=str(dates[0].date()))
    w_prev = {}
    from backend.services import hyp_investable as HI
    for d in dates:
        g = P[P["date"] == d].set_index("symbol")
        w = {s: 0.2 for s in picks[d]}
        c, to = MT.trade_cost(w_prev, w, g["_sp"].to_dict(), MT.DEFAULT_ROUND_TRIP)
        assert B.loc[d, "turnover"] == pytest.approx(to) and B.loc[d, "cost"] == pytest.approx(c)
        w_prev = HI.drift(w, g["fwd_ret"])


def test_d_weighted_rules_keep_their_weights():
    """Review F4 of C1: ivw / liqw rules were scored as their EW parent."""
    from scripts import hyp_investable as HIS
    from scripts import hyp_twin_board as TB
    dates = pd.date_range(BASE, periods=3, freq="BME")
    rows = [{"date": d, "symbol": s, "eligible": True, "fwd_ret": r, "median_dollar_vol": 3e8, "vol_63": 0.3,
             "mom_252_21": 0.1, "_sp": 0.01, "mcap": 1e9}
            for d in dates for s, r in (("A", 0.10), ("B", 0.0), ("C", 0.0))]
    P = pd.DataFrame(rows)

    class R:
        hold_months, rebalance_months = 1, None
    hold = [{"date": str(d.date()), "symbols": ["A", "B"], "weights": [0.8, 0.2]} for d in dates]
    pk = TB.carried_picks(hold, dates, R, None)
    assert pk[dates[0]] == {"A": 0.8, "B": 0.2}
    B = HIS.run_book(P, pk, start=str(dates[0].date()))
    assert B["gross"].iloc[0] == pytest.approx(0.08)                 # EW would read 0.05
    Bew = HIS.run_book(P, {d: ["A", "B"] for d in dates}, start=str(dates[0].date()))
    assert Bew["gross"].iloc[0] == pytest.approx(0.05)


def test_d_a_missing_weight_refuses_and_is_never_defaulted():
    from backend.services import hyp_investable as HI
    with pytest.raises(ValueError):
        HI.book_weights({"A": float("nan")})
    assert HI.book_weights(["A", "B", "A"]) == {"A": 0.5, "B": 0.5}


def test_d_alpha_needs_pure_selection_too():
    """Review F3 of C1: fair t >= 2 with selection < 2 is NET_EDGE_FROM_TURNOVER, never alpha."""
    from scripts import library_on_crsp as L
    fair = {"mean_monthly": 0.004, "t_blocks": 2.4}
    hold = {"mean_monthly": 0.003}
    assert L.fair_headline(fair, {"t_blocks": 0.65}, None, hold, None) == L.NET_EDGE_LABEL
    assert L.fair_headline(fair, {"t_blocks": 2.1}, None, hold, None) == "ALPHA_DETECTED"
    assert L.fair_headline(fair, {}, None, hold, None) == L.NET_EDGE_LABEL
    assert L.fair_headline({"mean_monthly": -0.001, "t_blocks": 2.4}, {"t_blocks": 3}, None, hold, None) \
        == "FAILED_VARIANT"
    assert "pure selection" in L.FAIR_HEADLINE_RULE and "twin21" not in L.FAIR_HEADLINE_RULE


def test_d_one_cost_composition():
    cs = np.array([0.05, np.nan, 0.50, 0.001])
    flat = np.array([0.0035, 0.0035, 0.0035, 0.0035])
    np.testing.assert_allclose(MT.round_trip_spread(cs, flat), [0.05, 0.0035, MT.CS_CAP, 0.0035])
    for rel in ("scripts/hyp_investable.py", "scripts/conditionals_on_crsp.py"):
        assert "round_trip_spread(" in (REPO / rel).read_text(encoding="utf-8"), rel


def _is_one_default_on_turnover(n) -> bool:
    """`x or 1.0`, `.get(k, 1.0)`, `.fillna(1.0)` on a turnover-named expression."""
    def tov(node) -> bool:
        names = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)}
        names |= {x.attr for x in ast.walk(node) if isinstance(x, ast.Attribute)}
        names |= {x.value for x in ast.walk(node) if isinstance(x, ast.Constant) and isinstance(x.value, str)}
        return any("tov" in str(s) or "turnover" in str(s) for s in names)
    one = lambda x: isinstance(x, ast.Constant) and x.value == 1.0 and not isinstance(x.value, bool)  # noqa: E731
    if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) and one(n.values[-1]):
        return any(tov(v) for v in n.values[:-1])
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
        if n.func.attr == "get" and len(n.args) == 2 and one(n.args[1]):
            return tov(n.args[0]) or tov(n.func.value)
        if n.func.attr == "fillna" and n.args and one(n.args[0]):
            return tov(n.func.value)
    return False


def test_d_the_default_guard_catches_or_get_and_fillna():
    bad = ["x = tov or 1.0", "x = row.get('turnover', 1.0)", "x = df['twin_turnover'].fillna(1.0)"]
    for src in bad:
        assert any(_is_one_default_on_turnover(n) for n in ast.walk(ast.parse(src))), src
    assert not any(_is_one_default_on_turnover(n) for n in ast.walk(ast.parse("x = w or 1.0")))


@pytest.mark.parametrize("rel", BOARD_MODULES + ("backend/services/matched_twins.py",))
def test_d_no_board_module_defaults_a_turnover_to_one(rel):
    assert not _functions_with(_tree(rel), _is_one_default_on_turnover), rel


def test_d_every_weight_rule_has_its_column_on_the_board():
    """`mom_12_1_liqw` / `qc623_mom63_liquidity_weighted` were scored EW: their weight column
    (`amihud`) is not in `rule.requires`, so the board never selected it."""
    from backend.services import strategy_library as SL
    from scripts import hyp_twin_board as TB
    assert set(SL.WEIGHT_RULES) - {"equal"} <= set(TB.WEIGHT_COLUMNS)
    src = (REPO / "scripts/hyp_twin_board.py").read_text(encoding="utf-8")
    assert "WEIGHT_COLUMNS.get(rule.weight_rule)" in src
