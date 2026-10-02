"""Offline tests for scripts/hyp_llm_theories.py (JOB3: LLM theories measured fairly).

No network, no model call, no literal calendar dates (dates derive from today)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import hyp_llm_theories as T


def _dates(n: int) -> list[str]:
    base = pd.Timestamp.today().normalize() - pd.Timedelta(days=400)
    return [str((base + pd.offsets.BDay(i)).date()) for i in range(n)]


def test_blind_removes_ticker_and_name_and_reports_no_leak():
    txt = "Acmecorp Widgets Inc (NASDAQ: ACMW) beat estimates; ACMW shares rose. Acmecorp said more."
    out, leaks = T.blind(txt, "ACMW", "Acmecorp Widgets Inc")
    assert "ACMW" not in out and "Acmecorp" not in out
    assert T.CODE in out
    assert leaks == []


def test_identified_matches_ticker_or_alias_and_not_unknown():
    assert T.identified({"company": "UNKNOWN", "ticker": "UNKNOWN"}, "ACMW", "Acmecorp Widgets Inc") is False
    assert T.identified({"company": "x", "ticker": "acmw"}, "ACMW", "Acmecorp Widgets Inc") is True
    assert T.identified({"company": "Acmecorp Widgets", "ticker": ""}, "ACMW", "Acmecorp Widgets Inc") is True
    assert T.identified({"company": "Other Corp", "ticker": "OTH"}, "ACMW", "Acmecorp Widgets Inc") is False
    assert T.identified(None, "ACMW", "Acmecorp Widgets Inc") is False


def test_parse_prob_refuses_out_of_range_and_missing():
    assert T.parse_prob('{"p": 0.37}', "p") == pytest.approx(0.37)
    assert T.parse_prob('```json\n{"p": 0.5}\n```', "p") == pytest.approx(0.5)
    assert T.parse_prob('{"p": 1.7}', "p") is None
    assert T.parse_prob('{"q": 0.3}', "p") is None
    assert T.parse_prob("no json here", "p") is None


def test_parse_scores_requires_every_item():
    full = "{" + ", ".join(f'"{k}": {10 * k}' for k in range(1, T.GROUP + 1)) + "}"
    s = T.parse_scores(full)
    assert s is not None and s[3] == 30.0
    assert T.parse_scores('{"1": 10, "2": 20}') is None


def test_block_stats_uses_weekly_blocks_not_rows():
    d = _dates(40)
    per_row = pd.Series(np.r_[np.ones(200), -np.ones(200)])
    dates = pd.Series(np.repeat(d, 10))
    st = T.block_stats(per_row, dates)
    assert st["n"] == 400
    assert st["n_blocks"] <= 9          # 40 business days = 8-9 weeks, not 400 rows
    assert st["mde"] == pytest.approx(2.8 * st["se"], rel=1e-3)


def test_score_binary_perfect_forecast_beats_base_rate():
    d = _dates(30)
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, size=300)
    df = pd.DataFrame({"entry_date": np.repeat(d, 10), "month": [x[:7] for x in np.repeat(d, 10)],
                       "event": y, "p_good": np.where(y == 1, 0.9, 0.1), "p_base": 0.5})
    sc = T.score_binary(df, "p_good", "event", ["p_base"])
    assert sc["brier"] == pytest.approx(0.01)
    assert sc["vs_p_base"]["mean"] > 0 and sc["vs_p_base"]["bss"] > 0.9
    assert sc["auc"] == 1.0


def test_make_pairs_same_date_distinct_symbols():
    d = _dates(5)
    rows = []
    for i, day in enumerate(d):
        for j in range(6):
            rows.append({"key": f"S{j}|{day}", "symbol": f"S{j}", "entry_date": day, "week": "w", "month": day[:7],
                         "y": float(j), "vol21_absx": 0.01 * (6 - j), "T2_trailing_meta_tfidf": float(j)})
    s = pd.DataFrame(rows)
    p = T.make_pairs(s, 100, 1)
    assert len(p) == 15
    for r in p.itertuples():
        assert r.a.split("|")[1] == r.b.split("|")[1] == r.entry_date
        assert r.a.split("|")[0] != r.b.split("|")[0]


def test_ece_zero_for_calibrated_bins():
    p = np.r_[np.full(100, 0.25), np.full(100, 0.75)]
    y = np.r_[np.r_[np.ones(25), np.zeros(75)], np.r_[np.ones(75), np.zeros(25)]]
    assert T.ece(p, y) == pytest.approx(0.0, abs=1e-9)


def test_group_ic_detects_perfect_ranking():
    d = _dates(3)
    rows = [{"gid": g, "entry_date": d[g], "month": d[g][:7], "score": k, "rel": k * 2.0}
            for g in range(3) for k in range(8)]
    gi = T.group_ic(pd.DataFrame(rows), "score", "rel")
    assert len(gi) == 3 and np.allclose(gi["ic"], 1.0)


def test_verdict_rule_three_way():
    assert T.verdict(0.01, 2.5, 0.01, 0.005) == "PASS"
    assert T.verdict(-0.001, -1.0, 0.004, 0.005) == "FAILED_VARIANT"
    assert T.verdict(-0.001, -1.0, 0.02, 0.005) == "CANNOT_DISTINGUISH"
    assert T.verdict(0.002, 1.2, 0.004, 0.005) == "CANNOT_DISTINGUISH"
    assert T.verdict(None, None, None, 0.005) == "NOT_RUN"
