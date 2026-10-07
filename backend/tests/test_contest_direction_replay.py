"""The ROT5_DIR event-level replay as a receipt (scripts/contest_direction_replay.py, 2026-10-07).

Pins: the declaration refuses when mutated after its stamp; the momentum-tercile split sums to
the total; the direction verdict is the frozen `contest_direction.analyst_direction`, applied with
rows dated before each buy day only; the ranking is per buy day by trail_abs. Synthetic data;
dates derive from today; the frozen contest modules are imported, never edited.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts import contest_direction as CD
from scripts import contest_direction_replay as R

TODAY = pd.Timestamp.today().normalize()


def test_the_shipped_declaration_verifies_and_pins_the_code():
    d = R.load_declaration()
    assert d["code"]["source_sha256"] == R.code_sha()
    assert d["primary"]["costs_bps_a_side"] == [10.0, 25.0]


def test_a_mutated_declaration_refuses(tmp_path):
    d = json.loads(R.DECLARATION.read_text(encoding="utf-8"))
    p = tmp_path / "decl.json"
    p.write_text(json.dumps(d, sort_keys=True, indent=1), encoding="utf-8")
    assert R.load_declaration(p)["sha256_of_body_without_this_field"] == d["sha256_of_body_without_this_field"]
    d["tops"] = [5, 10]                                              # a book size changed after the stamp
    p.write_text(json.dumps(d, sort_keys=True, indent=1), encoding="utf-8")
    with pytest.raises(R.ReplayRefused, match="edited"):
        R.load_declaration(p)
    p.unlink()
    with pytest.raises(R.ReplayRefused, match="absent"):
        R.load_declaration(p)


def _subset(n_days: int = 60, per_day: int = 6, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_days):
        d = TODAY - pd.Timedelta(days=900 - 12 * i)
        for k in range(per_day):
            mom = rng.normal(0, 0.3) if (i + k) % 11 else np.nan       # a few without momentum
            drop = bool(rng.random() < 0.3)
            rows.append({"pre_date": d, "symbol": f"N{k}", "mom63": mom,
                         "verdict": "DROP_NET_LOWERING" if drop else ("ADMIT" if k % 2 else "UNRATED"),
                         "r_o2o": rng.normal(-0.01 if drop else 0.0, 0.08)})
    return pd.DataFrame(rows)


def test_the_momentum_tercile_split_sums_to_the_total():
    s = _subset()
    s["is_drop"] = s.verdict.str.startswith("DROP")
    mc = R.momentum_control(s)
    assert mc["split_sums_to_total"]
    assert sum(v["n"] for v in mc["terciles"].values()) == mc["n_with_mom63"]
    assert mc["n_with_mom63"] + mc["n_without_mom63"] == len(s)
    assert sum(v["n_drop"] + v["n_kept"] for v in mc["terciles"].values()) == mc["n_with_mom63"]
    assert sum(v["n_drop"] for v in mc["terciles"].values()) == int(s[np.isfinite(s.mom63)].is_drop.sum())


def test_the_primary_difference_is_dropped_minus_kept_means():
    s = _subset()
    rep = R.subset_report(s)
    drop = s.verdict.str.startswith("DROP")
    want = s[drop].r_o2o.mean() - s[~drop].r_o2o.mean()
    assert rep["primary_diff_drop_minus_kept"]["diff"] == pytest.approx(want)
    assert rep["n_events"] == len(s) and rep["drop_share"] == pytest.approx(drop.mean())
    g = rep["dropped"]
    assert g["mean_net_10bps_a_side"] == pytest.approx(g["mean_gross"] - 0.002)
    assert g["mean_net_25bps_a_side"] == pytest.approx(g["mean_gross"] - 0.005)
    assert rep["by_year_and_loo"]["years"] >= 2


def test_event_table_ranks_per_buy_day_by_trail_abs_and_applies_eligibility():
    d0, d1 = TODAY - pd.Timedelta(days=30), TODAY - pd.Timedelta(days=29)
    ev = pd.DataFrame({
        "symbol": ["A", "B", "C", "D", "E"], "ci": [0, 1, 2, 3, 4],
        "pre_i": [10, 10, 10, 11, 11], "react_i": [11, 11, 11, 12, 12],
        "pre_date": [d0, d0, d0, d1, d1], "on_cadence": [True, True, True, True, False],
        "trail_abs": [0.05, 0.09, 0.07, 0.04, 0.20], "r_o2o": [0.01, -0.02, 0.03, 0.0, 0.1]})
    liq = np.ones((20, 5), dtype=bool)
    liq[10, 2] = False                                               # C illiquid at its buy open
    e = R.event_table(ev, liq, start=str((TODAY - pd.Timedelta(days=60)).date()), tops=(1, 2))
    assert e.symbol.tolist() == ["B", "A", "D"]                      # C illiquid, E off cadence
    assert e["rank"].tolist() == [1, 2, 1]
    assert e.top1.tolist() == [True, False, True]


def _rev(rows: list[dict]) -> pd.DataFrame:
    pulled = str(TODAY - pd.Timedelta(days=1))
    out = pd.DataFrame(rows)
    out["pulled_at"] = pulled
    out["first_seen_utc"] = pulled
    for c in ("action", "target_action", "to_grade", "firm"):
        if c not in out:
            out[c] = ""
    return out


def test_verdicts_use_the_frozen_rule_with_rows_dated_before_the_buy_day_only():
    buy = TODAY - pd.Timedelta(days=200)
    e = pd.DataFrame({"pre_date": [buy, buy, buy], "symbol": ["DN", "UP", "NONE"], "rank": [1, 2, 3]})
    rev = _rev([
        # DN: two lowerings in the 90 days before the buy day -> DROP_NET_LOWERING
        {"ticker": "DN", "event_date": str(buy - pd.Timedelta(days=20)), "firm": "f1", "to_grade": "Buy",
         "target_action": "Lowers"},
        {"ticker": "DN", "event_date": str(buy - pd.Timedelta(days=10)), "firm": "f2", "to_grade": "Buy",
         "target_action": "Lowers"},
        # UP: a raise before; a downgrade to Sell AFTER the buy day must not be read
        {"ticker": "UP", "event_date": str(buy - pd.Timedelta(days=5)), "firm": "f1", "to_grade": "Buy",
         "target_action": "Raises"},
        {"ticker": "UP", "event_date": str(buy + pd.Timedelta(days=3)), "firm": "f2", "to_grade": "Sell",
         "action": "down", "target_action": "Lowers"},
        {"ticker": "UP", "event_date": str(buy + pd.Timedelta(days=4)), "firm": "f3", "to_grade": "Sell",
         "action": "down", "target_action": "Lowers"},
    ])
    v = R.verdicts_by_day(e, rev, CD.analyst_direction, max_rank=3).set_index("symbol")
    assert v.loc["DN", "verdict"] == "DROP_NET_LOWERING"
    assert v.loc["UP", "verdict"] == "ADMIT"
    assert v.loc["NONE", "verdict"] == "UNRATED"
    # a day whose names have no rows at all is UNRATED for all, without calling the source
    e2 = pd.DataFrame({"pre_date": [buy], "symbol": ["ZZZ"], "rank": [1]})
    assert R.verdicts_by_day(e2, rev, CD.analyst_direction, max_rank=3).verdict.tolist() == ["UNRATED"]


def test_mom63_is_known_before_the_buy_open():
    C = np.arange(1, 201, dtype=float).reshape(-1, 1)                # close rises 1 a day
    m = R.mom63_of(C, np.array([100, 50]), np.array([0, 0]))
    assert m[0] == pytest.approx(C[99, 0] / C[36, 0] - 1)            # close(t-1) / close(t-64)
    assert np.isnan(m[1])                                            # not enough history


def test_cluster_diff_without_controls_is_the_difference_of_means():
    rng = np.random.default_rng(0)
    y = rng.normal(size=300)
    x = rng.random(300) < 0.3
    g = np.repeat(np.arange(60), 5)
    c = R.cluster_diff(y, x, g)
    assert c["b"] == pytest.approx(y[x].mean() - y[~x].mean())
    assert c["clusters"] == 60 and c["t"] is not None
