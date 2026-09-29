"""Offline tests for the analyst/insider-on-CRSP board logic (2026-09-29)."""
from __future__ import annotations

import pandas as pd

from scripts import analyst_insider_on_crsp as A


def _w(mean, t=None):
    return {"mean_monthly": mean, "t_blocks": t}


def _split(d, v, dv_t):
    return {"design": _w(d), "validate": _w(v), "design_validate": _w((d + v) / 2, dv_t),
            "holdout": _w(None), "full": _w(None)}


def test_survives_needs_every_leg():
    ok, why = A.survives(_split(0.004, 0.003, 2.5), _split(0.002, 0.001, 1.0), 0.97)
    assert ok and not why
    ok, why = A.survives(_split(0.004, 0.003, 2.5), _split(0.002, -0.001, 1.0), 0.97)
    assert not ok and "rule-market <= 0 in validate" in why
    ok, why = A.survives(_split(0.004, 0.003, 2.5), _split(0.002, 0.001, 1.0), 0.80)
    assert not ok and any("DSR" in w for w in why)
    ok, why = A.survives(_split(0.004, 0.003, 1.5), _split(0.002, 0.001, 1.0), 0.99)
    assert not ok and any("t < 2" in w for w in why)


def test_split_boundaries_declared_and_ordered():
    assert A.SPLITS["design"] == ("1991-01-01", "2008-12-31")
    assert A.SPLITS["validate"] == ("2009-01-01", "2016-12-31")
    assert A.SPLITS["holdout"] == ("2017-01-01", "2024-12-31")
    for v in A.SOURCE_START.values():
        assert pd.Timestamp(v) < pd.Timestamp(A.SPLITS["validate"][0])


def test_split_stats_keys_on_hold_month():
    idx = pd.to_datetime(["2008-12-31", "2009-01-30"])
    s = pd.Series([0.01, 0.02], index=idx)
    st = A.split_stats(s)
    assert st["design"]["n_months"] == 0        # 2008-12-31 decision holds in January 2009
    assert st["validate"]["n_months"] == 2
