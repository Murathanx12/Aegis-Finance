"""Offline unit tests for ft_lab's time split and leakage guards. Synthetic data only: no GPU,
no network, no files read.

  ft_lab/.venv/Scripts/python.exe -m pytest ft_lab/tests -q -p no:cacheprovider
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ft_lab import dataset as D
from ft_lab import evaluate as E
from ft_lab import prompts as P

SPLITS = {"train": ("2025-01-02", "2025-06-30"), "val": ("2025-07-16", "2025-09-30"),
          "test": ("2025-10-15", "2025-12-31")}


def _frame(dates):
    return pd.DataFrame({"entry_date": [str(pd.Timestamp(d).date()) for d in dates]})


def test_assign_split_is_by_time_and_gaps_are_embargo():
    days = pd.bdate_range("2025-01-02", "2025-12-31")
    df = _frame(days)
    df["split"] = D.assign_split(df["entry_date"], SPLITS)
    d = pd.to_datetime(df["entry_date"])
    assert d[df["split"] == "train"].max() < d[df["split"] == "val"].min()
    assert d[df["split"] == "val"].max() < d[df["split"] == "test"].min()
    # the days between blocks are embargo and belong to no block
    gap = df[(d > pd.Timestamp("2025-06-30")) & (d < pd.Timestamp("2025-07-16"))]
    assert set(gap["split"]) == {"embargo"}


def test_assert_time_split_passes_with_embargo():
    days = pd.bdate_range("2025-01-02", "2025-12-31")
    df = _frame(days)
    df["split"] = D.assign_split(df["entry_date"], SPLITS)
    out = D.assert_time_split(df[df["split"] != "embargo"], embargo=10)
    assert out["sessions_between"]["train->val"] >= 10


def test_assert_time_split_refuses_overlap():
    df = _frame(["2025-01-02", "2025-03-03", "2025-02-03", "2025-04-01", "2025-05-01"])
    df["split"] = ["train", "train", "val", "val", "test"]     # val starts before train ends
    with pytest.raises(ValueError, match="LEAK"):
        D.assert_time_split(df, embargo=0)


def test_assert_time_split_refuses_short_embargo():
    df = _frame(["2025-01-02", "2025-01-10", "2025-01-13", "2025-01-20", "2025-03-01"])
    df["split"] = ["train", "train", "val", "val", "test"]     # 0 sessions between train and val
    with pytest.raises(ValueError, match="embargo"):
        D.assert_time_split(df, embargo=10)


def test_random_split_is_refused():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2025-01-02", "2025-12-31")
    df = _frame(days)
    df["split"] = rng.choice(["train", "val", "test"], size=len(df))
    with pytest.raises(ValueError, match="LEAK"):
        D.assert_time_split(df, embargo=10)


def test_forbidden_feature_columns_are_refused():
    df = _frame(["2025-01-02"])
    for bad in ("x_oc", "dollar_vol", "r_oo", "y"):
        with pytest.raises(ValueError, match="forbidden"):
            D.assert_features_pit(df, ["l_vol21_absx", bad])


def test_trailing_feature_dated_on_entry_day_is_refused():
    df = pd.DataFrame({"entry_date": ["2025-03-03", "2025-03-04"],
                       "asof_date": [pd.Timestamp("2025-02-28"), pd.Timestamp("2025-03-04")]})
    with pytest.raises(ValueError, match="as of >= entry_date"):
        D.assert_features_pit(df, ["l_vol21_absx"])
    D.assert_features_pit(df.iloc[:1], ["l_vol21_absx"])  # the clean row passes


def test_block_stats_uses_weeks_not_rows():
    # 20 weeks x 5 dates; every date in a week shares the same value -> n_blocks = 20
    dates = pd.bdate_range("2025-01-06", periods=100)
    vals = pd.Series(np.repeat(np.linspace(-0.1, 0.1, 20), 5), index=[str(d.date()) for d in dates])
    r = E.block_stats(vals)
    assert r["n_blocks"] == 20 and r["n_dates"] == 100
    assert r["mde"] == pytest.approx(2.8 * r["se"], rel=1e-2)


def test_student_parsers_reject_off_schema_replies():
    assert P.valid_events(P.parse_json('{"event_type":"earnings_report","direction":1,'
                                       '"magnitude":"SMALL","confidence":0.8}'))
    assert P.valid_events(P.parse_json('{"event_type":"made_up_event","direction":1,'
                                       '"magnitude":"SMALL","confidence":0.8}')) is None
    assert P.valid_psych(P.parse_json('{"tone":0.2,"emotion":"joy","uncertainty":0.1,"surprise":0.1,'
                                      '"mgmt_confidence":null,"novelty":0.1,"attention":0.1,'
                                      '"expected_move":"SMALL"}')) is None


def test_ft_lab_is_not_imported_by_the_live_path():
    """Read the AST (not the text), so a docstring that mentions ft_lab is not an import."""
    import ast
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    offenders = []
    for top in ("backend", "scripts", "engine"):
        for f in (repo / top).rglob("*.py"):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(n == "ft_lab" or n.startswith("ft_lab.") for n in names):
                    offenders.append(str(f.relative_to(repo)))
    assert offenders == []
