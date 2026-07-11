"""Offline tests for the brain digest: degraded sections are explicit (never
fabricated), cached readings flow into the markdown with the REAL cache keys
(action/composite_score — not invented ones), and the fragility section reads
the persisted composite (no live recompute)."""

from unittest.mock import patch

from backend.services import market_digest

_FRAG_PATH = ("backend.services.portfolio_intelligence.fragility"
              ".latest_persisted_composite")


class TestMarketDigest:
    def test_empty_cache_yields_explicit_not_available(self):
        with patch.object(market_digest, "_peek", return_value=(None, None)), \
             patch(_FRAG_PATH, return_value={"status": "no_reading"}):
            d = market_digest.build_market_digest()
        assert d["sections"]["news"]["status"] == "not_available"
        assert d["sections"]["market"]["status"] == "not_available"
        assert d["sections"]["fragility"]["status"] == "no_reading"
        assert "Not available" in d["markdown"]
        assert d["markdown"].startswith("# Market context digest")

    def test_cached_readings_flow_into_markdown(self):
        readings = {
            "news_market": {
                "llm_summary": {"summary": "Markets steady.", "sentiment": "neutral"},
                "event_score": {"score": 0.1, "label": "calm"},
                "news": [{"title": "Headline A"}],
            },
            "market_status": {"regime": "Bull", "risk_score": 0.5,
                              "vix": 15.0, "sp500": 6000.0},
            # the REAL market_signal keys (get_market_signal's shape)
            "market_signal": {"action": "HOLD", "composite_score": 0.1},
        }
        with patch.object(market_digest, "_peek",
                          side_effect=lambda k: (readings.get(k), 5)), \
             patch(_FRAG_PATH, return_value={
                 "composite": 0.23, "level": "low structural fragility",
                 "evaluated_at": "2026-07-10T20:30:00"}):
            d = market_digest.build_market_digest()
        md = d["markdown"]
        assert "Markets steady." in md
        assert "Headline A" in md
        assert "Regime: Bull" in md
        assert "HOLD" in md
        assert "0.23" in md and "low structural fragility" in md
        assert d["sections"]["signal"]["action"] == "HOLD"

    def test_stale_reading_is_disclosed(self):
        readings = {"market_status": {"regime": "Bull", "risk_score": 0.5,
                                      "vix": 15.0, "sp500": 6000.0}}
        with patch.object(market_digest, "_peek",
                          side_effect=lambda k: (readings.get(k),
                                                 300 if k in readings else None)), \
             patch(_FRAG_PATH, return_value={"status": "no_reading"}):
            md = market_digest.build_market_digest()["markdown"]
        assert "reading is 300 min old" in md

    def test_fragility_never_recomputes_live(self):
        # the digest must call latest_persisted_composite, NEVER
        # compute_fragility_index (which does live network fetches)
        with patch.object(market_digest, "_peek", return_value=(None, None)), \
             patch(_FRAG_PATH, return_value={"status": "no_reading"}) as frag, \
             patch("backend.services.portfolio_intelligence.fragility"
                   ".compute_fragility_index",
                   side_effect=AssertionError("live recompute!")):
            market_digest.build_market_digest()
        frag.assert_called_once()

    def test_no_advice_language(self):
        with patch.object(market_digest, "_peek", return_value=(None, None)), \
             patch(_FRAG_PATH, return_value={"status": "no_reading"}):
            md = market_digest.build_market_digest()["markdown"].lower()
        for banned in ("buy ", "sell ", "should invest"):
            assert banned not in md
