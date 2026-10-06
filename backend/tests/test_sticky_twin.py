"""The STICKY matched twin (CHUNK C1b, 2026-10-07).

The fair-twin board's twin was rebuilt every month (terciles re-cut, draws redrawn), so it
turned over ~0.4 a month against a quality rule's 0.11-0.17 and a holding rule beat it on
costs alone. `matched_twins.twin_series_sticky` draws one partner per rule holding when the
rule ENTERS the name and holds it until the rule exits, so the twin's turnover equals the
rule's by construction. These tests pin that, the dying-partner replacement, the receipt's
refusal outside the declared tolerance, and that the REGISTERED `twin_series` (the forward
trials LIB-FWD-TWIN-1 and CRSP_BLEND_v0 are frozen on it) is byte-for-byte unchanged.

Synthetic data only; dates derive from today; no panel parquet is read.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import matched_twins as MT

BASE = pd.Timestamp.today().normalize() - pd.DateOffset(years=3)
LEVELS = np.array([3e9, 3e8, 5e7, 5e6])


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range(BASE, periods=n, freq="BME")


def _panel(n_months: int, n_names: int, *, seed: int = 1, flat_ret: float | None = 0.01,
           ineligible: set | None = None) -> pd.DataFrame:
    """n_names over four size bands. `flat_ret` set: every name earns the same return, so an
    EW book never drifts off EW (turnover is name changes only). `ineligible` names are on
    the panel (the rule may hold them) but never a twin candidate (no collision possible)."""
    rng = np.random.default_rng(seed)
    ineligible = ineligible or set()
    rows = []
    for d in _dates(n_months):
        for i in range(n_names):
            s = f"S{i:03d}"
            rows.append({"date": d, "symbol": s, "eligible": s not in ineligible,
                         "median_dollar_vol": LEVELS[i % 4] * (1 + 0.1 * rng.random()),
                         "vol_63": rng.uniform(0.1, 0.8), "mom_252_21": rng.normal(0, 0.3),
                         "fwd_ret": flat_ret if flat_ret is not None else rng.normal(0.005, 0.05),
                         "_sp": 0.01})
    return pd.DataFrame(rows)


# ── turnover equals the rule's by construction ─────────────────────────────

def test_a_rule_that_never_trades_has_a_twin_that_never_trades():
    k, n = 8, 120
    rule_names = [f"S{i:03d}" for i in range(k)]
    P = _panel(10, n, ineligible=set(rule_names))
    book = {d: list(rule_names) for d in _dates(10)}
    K = MT.twin_series_sticky({"id": "holder", "held_symbols_by_date": book}, P, n_draws=5)
    assert K["turnover"].iloc[0] == pytest.approx(0.5)              # the entry from cash
    assert K["twin_turnover"].iloc[0] == pytest.approx(0.5)
    assert (K["turnover"].iloc[1:] == 0).all()
    assert (K["twin_turnover"].iloc[1:] == 0).all()                # 0 = 0
    assert (K["twin_cost"].iloc[1:] == 0).all()
    assert int(K["twin_entry"].sum()) == k * 5                     # drawn once per holding per draw
    assert int(K[["twin_died", "twin_collision", "twin_exit"]].to_numpy().sum()) == 0
    chk = MT.sticky_turnover_check(K)
    assert chk["ok"] and chk["median_abs_gap"] == 0.0


def test_a_rule_that_replaces_one_name_a_month_has_a_twin_that_replaces_one_partner():
    k, n, months = 5, 160, 12
    pool = [f"S{i:03d}" for i in range(40)]                         # the rule's names: never candidates
    P = _panel(months, n, ineligible=set(pool))
    book, cur = {}, pool[:k]
    for i, d in enumerate(_dates(months)):
        if i:
            cur = cur[1:] + [pool[k + i - 1]]                       # one out, one in
        book[d] = list(cur)
    K = MT.twin_series_sticky({"id": "one_a_month", "held_symbols_by_date": book}, P, n_draws=7)
    assert np.allclose(K["turnover"].iloc[1:], 1.0 / k)
    assert np.allclose(K["twin_turnover"].to_numpy(), K["turnover"].to_numpy())
    assert np.allclose(K["twin_cost"].to_numpy(), K["cost"].to_numpy())   # same spreads, same traded weight
    assert (K["twin_exit"].iloc[1:] == 7).all() and (K["twin_entry"].iloc[1:] == 7).all()
    assert MT.sticky_turnover_check(K)["median_abs_gap"] == pytest.approx(0.0)


def test_the_partner_is_held_until_the_rule_exits_the_matched_name():
    k, n = 4, 120
    names = [f"S{i:03d}" for i in range(k)]
    P = _panel(6, n, ineligible=set(names))
    book = {d: list(names) for d in _dates(6)}
    # the monthly-redrawn registered twin re-draws every month; the sticky one never does
    K = MT.twin_series_sticky({"id": "hold", "held_symbols_by_date": book}, P, n_draws=1)
    assert K["twin_entry"].tolist() == [k, 0, 0, 0, 0, 0]


def test_a_dying_partner_is_replaced_and_counted_as_twin_turnover():
    """Two eligible names in the twin's universe: X on month 0-1, then X delists and Y lists.
    The rule holds one ineligible name throughout; its turnover after entry is 0, the
    twin's is 1.0 the month X is replaced, and the replacement is counted and charged."""
    d = _dates(4)
    rows = []
    for i, dt in enumerate(d):
        rows.append({"date": dt, "symbol": "R00", "eligible": False, "median_dollar_vol": 3e8,
                     "vol_63": 0.3, "mom_252_21": 0.1, "fwd_ret": 0.0, "_sp": 0.01})
        live = "X01" if i < 2 else "Y02"
        rows.append({"date": dt, "symbol": live, "eligible": True, "median_dollar_vol": 3e8,
                     "vol_63": 0.3, "mom_252_21": 0.1, "fwd_ret": 0.0, "_sp": 0.02})
    P = pd.DataFrame(rows)
    book = {dt: ["R00"] for dt in d}
    K = MT.twin_series_sticky({"id": "dies", "held_symbols_by_date": book}, P, n_draws=3)
    assert K["turnover"].tolist() == pytest.approx([0.5, 0.0, 0.0, 0.0])
    assert K["twin_turnover"].tolist() == pytest.approx([0.5, 0.0, 1.0, 0.0])
    assert K["twin_died"].tolist() == [0, 0, 3, 0]                  # once per draw
    assert K["twin_cost"].iloc[2] > 0                               # the replacement is charged
    # sell X at the default spread (X is off the panel) + buy Y at its own
    assert K["twin_cost"].iloc[2] == pytest.approx(0.0035 / 2 + 0.02 / 2)


def test_a_partner_the_rule_later_buys_is_replaced_as_a_collision():
    d = _dates(3)
    rows = []
    for dt in d:
        for s, el in (("R00", False), ("X01", True), ("Y02", True)):
            rows.append({"date": dt, "symbol": s, "eligible": el, "median_dollar_vol": 3e8, "vol_63": 0.3,
                         "mom_252_21": 0.1, "fwd_ret": 0.0, "_sp": 0.01})
    P = pd.DataFrame(rows)
    K0 = MT.twin_series_sticky({"id": "c", "held_symbols_by_date": {d[0]: ["R00"]}}, P, n_draws=1, dates=d[:1])
    assert K0["twin_entry"].iloc[0] == 1
    # whichever of X / Y the draw took, the rule buys THAT one next month
    first = None
    for cand in ("X01", "Y02"):
        K = MT.twin_series_sticky({"id": "c", "held_symbols_by_date": {d[0]: ["R00"], d[1]: ["R00", cand]}},
                                  P, n_draws=1, dates=d[:2])
        if K["twin_collision"].iloc[1] == 1:
            first = cand
    assert first is not None


# ── the receipt refuses a row outside the tolerance ─────────────────────────

def test_the_receipt_refuses_a_row_outside_the_declared_tolerance():
    idx = _dates(6)
    F = pd.DataFrame({"n": [5] * 6, "turnover": [0.1] * 6, "twin_turnover": [0.4] * 6}, index=idx)
    chk = MT.sticky_turnover_check(F)
    assert chk["tolerance"] == C.STICKY_TWIN_TURNOVER_TOLERANCE
    assert not chk["ok"] and chk["reason"].startswith("REFUSED")
    assert "0.3000" in chk["reason"]
    F2 = F.assign(twin_turnover=0.1 + C.STICKY_TWIN_TURNOVER_TOLERANCE / 2)
    assert MT.sticky_turnover_check(F2)["ok"]
    assert not MT.sticky_turnover_check(F.assign(n=0))["ok"]       # nothing invested: no check, refused


def test_the_board_refuses_a_sticky_row_whose_turnover_gap_is_over_tolerance(monkeypatch):
    from scripts import hyp_twin_board as TB
    k, n = 4, 80
    names = [f"S{i:03d}" for i in range(k)]
    P = _panel(5, n, ineligible=set(names))
    pk = {dt: list(names) for dt in _dates(5)}
    by_date = {pd.Timestamp(dt): g for dt, g in P.groupby("date")}
    K = MT.twin_series_sticky({"id": "b", "held_symbols_by_date": pk}, by_date=by_date, n_draws=2)
    B = K[["gross", "cost", "turnover"]].copy()
    for c in ("twin_gross", "twin_cost", "twin_turnover", "twin_full_rt"):
        B[c] = 0.0
    out, extra = TB.sticky_book(B, "b", pk, by_date, {})
    assert extra["twin_kind"] == "sticky" and extra["sticky_turnover_check"]["ok"]
    assert (out["twin_turnover"].to_numpy() == K["twin_turnover"].to_numpy()).all()
    monkeypatch.setattr(C, "STICKY_TWIN_TURNOVER_TOLERANCE", -1.0)
    with pytest.raises(MT.TwinInputMissing, match="REFUSED"):
        TB.sticky_book(B, "b", pk, by_date, {})
    B2 = B.copy()
    B2.iloc[1, B2.columns.get_loc("turnover")] += 0.1               # run_book and sticky disagree
    monkeypatch.setattr(C, "STICKY_TWIN_TURNOVER_TOLERANCE", 0.03)
    with pytest.raises(MT.TwinInputMissing, match="differently"):
        TB.sticky_book(B2, "b", pk, by_date, {})


# ── the registered construction is untouched ────────────────────────────────

#: sha256 of the registered `twin_series` output on the fixture below, computed BEFORE
#: `twin_series_sticky` was added (2026-10-07). A change here is a change to the twin the
#: forward trials LIB-FWD-TWIN-1 and CRSP_BLEND_v0 were registered on.
REGISTERED_TWIN_SERIES_SHA = "3ad169104cfa5e6a261d95a48675b4bb72e637e2391c0b27b4395fa5dca5c2d9"


def _registered_fixture():
    rng = np.random.default_rng(11)
    dates = pd.date_range(BASE, periods=8, freq="BME")
    rows = []
    for d in dates:
        for i in range(60):
            rows.append({"date": d, "symbol": f"S{i:03d}", "eligible": True,
                         "median_dollar_vol": LEVELS[i % 4] * (1 + 0.1 * rng.random()),
                         "vol_63": rng.uniform(0.1, 0.8), "mom_252_21": rng.normal(0, 0.3),
                         "fwd_ret": rng.normal(0.005, 0.05)})
    P = pd.DataFrame(rows)
    held, wts, months = {}, {}, []
    for i, (d, _g) in enumerate(P.groupby("date")):
        ds = str(d.date())
        if i % 2 == 0:
            held[ds] = [f"S{(3 * i + j) % 60:03d}" for j in range(6)]
            wts[ds] = [1 / 6] * 6
        months.append({"date": ds, "gross": 0.0, "cost": 0.0, "net": 0.0, "rebalanced": i % 2 == 0})
    return P, {"id": "pin_rule", "held_symbols_by_date": held, "weights_by_date": wts,
               "monthly_return_series": months}


def test_the_registered_twin_series_is_byte_identical():
    P, rule = _registered_fixture()
    ts = MT.twin_series(rule, P, seed=MT.seed_for("pin_rule"))
    vals = json.dumps({"r": [round(x, 15) for x in ts["rule_gross_recon"]],
                       "t": [round(x, 15) for x in ts["twin_gross"]],
                       "f": list(ts["fallbacks"])}, sort_keys=True, default=str)
    assert hashlib.sha256(vals.encode()).hexdigest() == REGISTERED_TWIN_SERIES_SHA


def test_sticky_reports_its_kind_and_draw_count():
    names = ["S000", "S001"]
    P = _panel(3, 40, ineligible=set(names))
    K = MT.twin_series_sticky({"id": "k", "held_symbols_by_date": {d: names for d in _dates(3)}}, P)
    assert K.attrs["twin_kind"] == MT.STICKY_TWIN_KIND == "sticky"
    assert K.attrs["n_draws"] == C.STICKY_TWIN_N_DRAWS == 21
    assert K.attrs["cost_convention"] == MT.TWIN_COST_CONVENTION


def test_each_partner_carries_its_matched_names_weight():
    """Review F4/F5 of C1: an ivw / liqw rule's twin is weighted like the rule."""
    d = _dates(2)
    rows = []
    for dt in d:
        for s, el, mdv, r in (("R1", False, 3e9, 0.0), ("R2", False, 5e6, 0.0),
                              ("M1", True, 3e9, 0.10), ("S1", True, 5e6, 0.0)):
            rows.append({"date": dt, "symbol": s, "eligible": el, "median_dollar_vol": mdv, "vol_63": 0.3,
                         "mom_252_21": 0.1, "fwd_ret": r, "_sp": 0.01})
    P = pd.DataFrame(rows)
    book = {dt: {"R1": 0.9, "R2": 0.1} for dt in d}             # the mega name carries 90%
    K = MT.twin_series_sticky({"id": "w", "held_symbols_by_date": book}, P, n_draws=2)
    # M1 is the only mega candidate: it partners R1 at R1's 0.9 weight -> twin gross 0.09
    assert K["twin_gross"].iloc[0] == pytest.approx(0.09)
    assert K["turnover"].iloc[0] == pytest.approx(0.5) and K["twin_turnover"].iloc[0] == pytest.approx(0.5)


def test_a_partner_without_a_forward_return_is_replaced_as_died():
    d = _dates(3)
    rows = []
    for i, dt in enumerate(d):
        rows.append({"date": dt, "symbol": "R00", "eligible": False, "median_dollar_vol": 3e8, "vol_63": 0.3,
                     "mom_252_21": 0.1, "fwd_ret": 0.0, "_sp": 0.01})
        rows.append({"date": dt, "symbol": "X01", "eligible": True, "median_dollar_vol": 3e8, "vol_63": 0.3,
                     "mom_252_21": 0.1, "fwd_ret": 0.0 if i == 0 else np.nan, "_sp": 0.01})
        rows.append({"date": dt, "symbol": "Y02", "eligible": i > 0, "median_dollar_vol": 3e8, "vol_63": 0.3,
                     "mom_252_21": 0.1, "fwd_ret": 0.0, "_sp": 0.01})
    P = pd.DataFrame(rows)
    K = MT.twin_series_sticky({"id": "nr", "held_symbols_by_date": {dt: ["R00"] for dt in d}}, P, n_draws=1)
    assert K["twin_died"].tolist() == [0, 1, 0]
    chk = MT.sticky_turnover_check(K)
    assert chk["n_months_excluded_death_or_collision"] == 1 and chk["ok"]


def test_the_sticky_construction_is_declared_and_the_code_matches_the_declaration():
    from scripts import hyp_twin_board as TB
    d = TB.sticky_declaration()
    assert d["path"].endswith("DECLARATION_TWIN_STICKY_v1.json") and len(d["sha256"]) == 64
    doc = json.loads(TB.STICKY_DECLARATION.read_text(encoding="utf-8"))
    body = {k: v for k, v in doc.items() if k != "sha256_of_body_without_this_field"}
    assert hashlib.sha256(json.dumps(body, sort_keys=True, indent=1).encode()).hexdigest() == d["sha256"]
    assert doc["receipt_check"]["tolerance"] == C.STICKY_TWIN_TURNOVER_TOLERANCE
