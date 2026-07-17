"""
Tests for the bull/bear two-sided card (V4 chunk 5).

The hard constraints under test: the LLM argues both sides of the COMPUTED
signal (prose only, numeric signal untouched), recommendation language is
rejected fail-closed, and every failure path is disclosed-unavailable
instead of fabricated. All offline — the LLM call is stubbed.
"""

import json
from unittest.mock import patch

from backend.services.llm_analyzer import (
    _contains_advice_language,
    argue_signal_two_sided,
)


def _sig_json(**overrides) -> str:
    sig = {
        "action": "Buy",
        "composite_score": 0.42,
        "confidence": 55,
        "components": {"momentum": 0.3, "valuation": -0.15, "crash_risk": -0.05},
        "price": 182.5,
        "crash_prob_3m": 9.1,
    }
    sig.update(overrides)
    return json.dumps(sig, sort_keys=True)


_GOOD_RESPONSE = (
    "BULL: Momentum dominates the composite and the crash probability is low. "
    "The positive reading rests on broad participation.\n"
    "BEAR: The valuation component is negative and the confidence is modest. "
    "A momentum reversal would flip the composite quickly.\n"
    "WATCH: A change in the momentum component's sign."
)


class TestArgueSignalTwoSided:
    @patch("backend.services.llm_analyzer._call_llm", return_value=_GOOD_RESPONSE)
    def test_parses_bull_bear_watch(self, _mock):
        out = argue_signal_two_sided("AAPL", _sig_json())
        assert out is not None
        assert out["bull_case"].startswith("Momentum dominates")
        assert out["bear_case"].startswith("The valuation component")
        assert out["watch_for"].startswith("A change")
        # the numeric signal is echoed from the INPUT, never LLM-generated
        assert out["signal_action"] == "Buy"
        assert out["composite_score"] == 0.42

    @patch("backend.services.llm_analyzer._call_llm",
           return_value="BULL: Strong setup, so investors should buy the stock "
                        "now.\nBEAR: Weak.\nWATCH: x")
    def test_advice_language_rejected_fail_closed(self, _mock):
        assert argue_signal_two_sided("MSFT", _sig_json()) is None

    @patch("backend.services.llm_analyzer._call_llm",
           return_value="Some unstructured rambling without the format")
    def test_malformed_response_rejected(self, _mock):
        assert argue_signal_two_sided("NVDA", _sig_json()) is None

    @patch("backend.services.llm_analyzer._call_llm", return_value=None)
    def test_llm_unavailable_returns_none(self, _mock):
        assert argue_signal_two_sided("AMD", _sig_json()) is None

    def test_bad_signal_json_returns_none(self):
        assert argue_signal_two_sided("TSLA", "not json") is None


class TestAdviceFilter:
    def test_flags_recommendations(self):
        assert _contains_advice_language("You should buy this dip.")
        assert _contains_advice_language("We recommend adding exposure.")
        assert _contains_advice_language("Investors should sell into strength.")
        assert _contains_advice_language("Sell the shares before earnings.")

    def test_allows_analytical_nouns(self):
        # "buy" as a noun/rating and factual signal descriptions are fine
        assert not _contains_advice_language(
            "The street's buy ratings rose while the model's reading is "
            "cautious; selling pressure showed in the momentum component."
        )
        assert not _contains_advice_language(
            "The model signal is Buy with modest confidence."
        )
