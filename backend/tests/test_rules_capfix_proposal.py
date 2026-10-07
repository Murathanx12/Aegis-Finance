"""C20 / D13: the mirror cap hole, as a PROPOSAL that no lane path imports."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.services import rules_capfix_proposal as CF
from backend.services.portfolio_intelligence.rules import enforce_position_limits

REPO = Path(__file__).resolve().parents[2]


def test_the_hole_exists_in_the_shipped_function():
    """Pinned as documented on 2026-10-06: two names under a 25% cap come back
    over the cap, because the shipped waterfill keeps the sum at 1."""
    out = enforce_position_limits({"DKNG": 0.5, "SLDP": 0.5}, 0.25, 0.60, {})
    assert max(out.values()) > 0.25 + 1e-9


def test_two_names_are_held_at_the_cap_and_the_rest_is_cash():
    out = CF.enforce_position_limits_with_cash({"DKNG": 0.5, "SLDP": 0.5}, 0.25, 0.60, {})
    assert out["DKNG"] == pytest.approx(0.25) and out["SLDP"] == pytest.approx(0.25)
    assert out[CF.CASH_KEY] == pytest.approx(0.50)
    assert sum(out.values()) == pytest.approx(1.0)


def test_uneven_names_waterfill_into_cash():
    out = CF.enforce_position_limits_with_cash({"A": 0.9, "B": 0.1}, 0.25, 1.0, {})
    assert out["A"] == pytest.approx(0.25) and out["B"] == pytest.approx(0.25)
    assert out[CF.CASH_KEY] == pytest.approx(0.50)
    small = CF.enforce_position_limits_with_cash({"A": 0.15, "B": 0.05}, 0.25, 1.0, {})
    assert small["A"] == pytest.approx(0.15) and small[CF.CASH_KEY] == pytest.approx(0.0)


def test_sector_cap_trims_into_cash_never_into_another_name():
    out = CF.enforce_position_limits_with_cash(
        {"A": 0.4, "B": 0.3, "C": 0.3}, 0.25, 0.60, {"A": "tech", "B": "tech", "C": "tech"})
    assert all(out[t] <= 0.25 + 1e-12 for t in "ABC")
    assert sum(out[t] for t in "ABC") == pytest.approx(0.60)
    assert out[CF.CASH_KEY] == pytest.approx(0.40)


def test_outside_the_hole_it_defers_unchanged():
    w = {f"N{i}": 1 / 12 + (0.02 if i == 0 else -0.02 / 11) for i in range(12)}
    assert CF.enforce_position_limits_with_cash(dict(w), 0.25, 0.60, {}) == \
        enforce_position_limits(dict(w), 0.25, 0.60, {})
    assert CF.CASH_KEY not in CF.enforce_position_limits_with_cash(dict(w), 0.25, 0.60, {})
    assert CF.cap_hole(w, 0.25)["in_hole"] is False
    assert CF.cap_hole({"A": 0.5, "B": 0.5}, 0.25)["cash_if_fixed"] == pytest.approx(0.5)


def test_worst_case_rows_halve_the_single_name_loss():
    rows = CF.worst_case_rows(nav=75_525.03, weights_unfixed={"DKNG": 0.5, "SLDP": 0.5},
                              weights_fixed={"DKNG": 0.25, "SLDP": 0.25, "CASH": 0.5},
                              sigmas={"DKNG": 0.03, "SLDP": 0.033})
    before, after = rows
    assert before["one_name_to_zero_usd"] == pytest.approx(-0.5 * 75_525.03)
    assert after["one_name_to_zero_usd"] == pytest.approx(-0.25 * 75_525.03)
    assert after["k_sigma_day_usd"] == pytest.approx(before["k_sigma_day_usd"] / 2)
    assert after["gross_over_equity"] == pytest.approx(0.5)


def test_the_proposal_is_not_wired_into_any_lane_path():
    """Lane-integrity work is attended (D13): only its tests and the C20
    preparer may import it."""
    allowed = {"scripts/fleet_v3_prepare.py"}
    offenders = []
    for root in ("backend", "scripts"):
        for f in (REPO / root).rglob("*.py"):
            rel = f.relative_to(REPO).as_posix()
            if rel in allowed or "/tests/" in rel or "__pycache__" in rel \
                    or rel.endswith("rules_capfix_proposal.py"):
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8-sig"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                mods = ([a.name for a in n.names] if isinstance(n, ast.Import) else
                        [n.module or ""] + [a.name for a in n.names]
                        if isinstance(n, ast.ImportFrom) else [])
                if any("rules_capfix_proposal" in m for m in mods):
                    offenders.append(rel)
    assert not offenders, offenders
