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


def test_b_bridges_board_columns_scale_the_twin_on_its_own_turnover():
    from scripts import bridges_on_crsp_run as BR
    idx = _idx(24)
    rng = np.random.default_rng(3)
    rg, tg = pd.Series(rng.normal(0.01, 0.03, 24), index=idx), pd.Series(rng.normal(0.008, 0.03, 24), index=idx)
    flat_cost = 0.001
    fl = pd.DataFrame({"rule_net": rg - flat_cost, "twin21_net": tg - flat_cost, "market": 0.007}, index=idx)
    cs = pd.DataFrame({"rule_net": fl["rule_net"] - 0.03, "twin21_net": fl["twin21_net"] - 0.03,
                       "market": 0.007}, index=idx)
    C = BR.board_columns(fl, cs, rule_tov=0.2, twin_tov=0.2)
    assert tuple(C.columns) == MT.FOUR_COLUMNS
    np.testing.assert_allclose(C["pure_selection"], rg - tg)
    np.testing.assert_allclose(C["fair_twin_net"], rg - tg)          # same turnover, same spread: cancels
    np.testing.assert_allclose(C["twin_full_round_trip_UPPER_BOUND"] - C["fair_twin_net"], 0.03 * (1 - 0.2))
    C0 = BR.board_columns(fl, cs, rule_tov=0.2, twin_tov=0.0)        # a still twin pays no spread
    np.testing.assert_allclose(C0["fair_twin_net"], rg - tg - 0.2 * 0.03)


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
        "NOT_COMPUTED"}
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
