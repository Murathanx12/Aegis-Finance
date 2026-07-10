"""
Explain-the-move — offline tests.

Invariants: the move gets quantified vs the ticker's OWN history; every
evidence block degrades to an explicit `unavailable` (never vanishes, never
raises); narration works with NO LLM key and carries the context-not-causation
framing with no buy/sell language.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services import explain_move as em


def _series(returns, start_px=10.0, start="2024-01-02"):
    idx = pd.bdate_range(start, periods=len(returns) + 1)
    px = start_px * np.cumprod([1.0] + [1 + r for r in returns])
    return pd.Series(px, index=idx)


def _spike_series():
    """~2y of quiet drift, then a violent 21d melt-up (the SOC/300% case)."""
    rng = np.random.default_rng(7)
    quiet = list(rng.normal(0.0003, 0.005, 480))
    spike = [0.07] * 21  # ~4x in a month
    return _series(quiet + spike)


class TestMoveProfile:
    def test_spike_is_flagged_extreme(self):
        out = em.compute_move_profile(_spike_series())
        assert out["status"] == "ok"
        assert out["return_21d"] > 2.0  # a multi-hundred-percent month
        assert out["move_zscore_21d"] > 3
        assert out["move_unusualness"] == "extreme"

    def test_quiet_series_is_ordinary(self):
        rng = np.random.default_rng(1)
        out = em.compute_move_profile(_series(list(rng.normal(0.0003, 0.005, 500))))
        assert out["move_unusualness"] in ("ordinary", "notable")

    def test_short_history_is_honest(self):
        out = em.compute_move_profile(_series([0.01] * 30))
        assert out["status"] == "ok"
        assert "move_zscore_21d" not in out  # no fake z on 30 days
        assert out["return_63d"] is None

    def test_empty_series(self):
        assert em.compute_move_profile(pd.Series(dtype=float))["status"] == \
            "insufficient_history"


def _happy_sources():
    return {
        "history": lambda t: _spike_series(),
        "earnings": lambda t: {"next_earnings_date": "2026-07-20",
                               "days_until_earnings": 11, "earnings_imminent": False,
                               "surprise_trend": "improving", "beat_rate": "75%",
                               "earnings_surprises": [{"q": "2026Q1"}]},
        "filings": lambda t: [{"form": "8-K", "filed": "2026-07-01T00:00:00",
                               "event_types": ["results"]}],
        "news_sentiment": lambda t: {"sentiment": "positive", "score": 0.6,
                                     "headline_count": 12, "method": "finbert"},
        "insider": lambda t: {"opp_score": 2.1, "n_distinct_buyers": 2,
                              "cluster_buy": True, "n_buys": 3},
        "options": lambda t: {"available": True, "sentiment": "bullish",
                              "put_call_ratio": 0.6},
    }


class TestAssembly:
    def test_all_blocks_present_and_ok(self):
        d = em.assemble_move_evidence("SOC", sources=_happy_sources())
        assert d["ticker"] == "SOC"
        assert d["move"]["move_unusualness"] == "extreme"
        assert set(d["evidence"]) == {"earnings", "filings", "news_sentiment",
                                      "insider", "options"}
        assert all(b["status"] == "ok" for b in d["evidence"].values())
        assert "not advice" in d["label"] or "not " in d["label"]

    def test_one_dead_source_degrades_only_itself(self):
        src = _happy_sources()
        def _boom(t):
            raise RuntimeError("SEC down")
        src["filings"] = _boom
        d = em.assemble_move_evidence("SOC", sources=src)
        assert d["evidence"]["filings"]["status"] == "unavailable"
        assert d["evidence"]["earnings"]["status"] == "ok"

    def test_error_dict_from_source_is_unavailable(self):
        src = _happy_sources()
        src["earnings"] = lambda t: {"error": "yfinance rate limit"}
        d = em.assemble_move_evidence("SOC", sources=src)
        assert d["evidence"]["earnings"]["status"] == "unavailable"

    def test_dead_history_never_raises(self):
        src = _happy_sources()
        def _boom(t):
            raise RuntimeError("no data")
        src["history"] = _boom
        d = em.assemble_move_evidence("GONE", sources=src)
        assert d["move"]["status"] == "unavailable"


class TestNarration:
    def test_template_fallback_without_llm_key(self, monkeypatch):
        monkeypatch.setattr("backend.services.llm_analyzer.is_available",
                            lambda: False)
        out = em.explain_move("SOC", sources=_happy_sources())
        assert out["method"] == "template"
        n = out["narration"].lower()
        assert "soc" in n
        assert "not advice" in n
        # no ADVICE phrasing ("buyers" describing insider activity is fine)
        for phrase in ("should buy", "should sell", "buy now", "sell now",
                       "recommend", "time to buy", "time to sell"):
            assert phrase not in n

    def test_narration_names_unavailable_sources(self, monkeypatch):
        monkeypatch.setattr("backend.services.llm_analyzer.is_available",
                            lambda: False)
        src = _happy_sources()
        src["options"] = lambda t: {"error": "no chain"}
        out = em.explain_move("SOC", sources=src)
        assert "options" in out["narration"].lower()  # absence is shown

    def test_llm_failure_falls_back_to_template(self, monkeypatch):
        monkeypatch.setattr("backend.services.llm_analyzer.is_available",
                            lambda: True)
        def _boom(system, user, **kw):
            raise RuntimeError("provider 500")
        monkeypatch.setattr("backend.services.llm_analyzer._call_llm", _boom)
        out = em.explain_move("SOC", sources=_happy_sources())
        assert out["method"] == "template"
        assert out["narration"]
