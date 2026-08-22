"""INSTR-PREDMARKET-MATCHING V1 — parsers, refusals, and the divergence math.

The matcher's job is to be NARROW: mechanical pairs only, refusals recorded,
nothing approximated. These tests pin the parsers to the live formats both
venues actually used on 2026-08-21 and every refusal path to its reason.
"""

from __future__ import annotations

import json

import pytest

from backend import config
from backend.services import prediction_market_matching as mm


def _k(ticker, mid=0.5, title="t"):
    return {"source": "kalshi", "ticker": ticker, "title": title, "mid": mid}


def _p(title, mid=0.5, ticker="slug-1"):
    return {"source": "polymarket", "ticker": ticker, "title": title,
            "mid": mid}


class TestParsers:
    def test_kalshi_fed_ticker_grammar(self):
        assert mm.parse_kalshi(_k("KXFEDDECISION-26SEP-H0")) == \
            ("FED_DECISION", "2026-09", "maintain")
        assert mm.parse_kalshi(_k("KXFEDDECISION-27JAN-H26")) == \
            ("FED_DECISION", "2027-01", "hike_50plus")
        assert mm.parse_kalshi(_k("KXFEDDECISION-26DEC-C25")) == \
            ("FED_DECISION", "2026-12", "cut_25")
        # not the family, or a strike V1 does not know -> None, never a guess
        assert mm.parse_kalshi(_k("KXCPI-26SEP-T3.0")) is None
        assert mm.parse_kalshi(_k("KXFEDDECISION-26SEP-C50")) is None

    def test_polymarket_title_grammar(self):
        assert mm.parse_polymarket(_p(
            "Will the Fed increase interest rates by 25 bps after the "
            "September 2026 meeting?")) == \
            ("FED_DECISION", "2026-09", "hike_25")
        assert mm.parse_polymarket(_p(
            "Will the Fed decrease interest rates by 50+ bps after the "
            "December 2026 meeting?")) == \
            ("FED_DECISION", "2026-12", "cut_50plus")
        assert mm.parse_polymarket(_p(
            "Will there be no change in Fed interest rates after the "
            "October 2026 meeting?")) == \
            ("FED_DECISION", "2026-10", "maintain")
        # "50 bps" exact (no plus) has no Kalshi twin in V1 -> unparsed
        assert mm.parse_polymarket(_p(
            "Will the Fed increase interest rates by 50 bps after the "
            "September 2026 meeting?")) is None
        assert mm.parse_polymarket(_p("Will 4 Fed rate cuts happen in "
                                      "2026?")) is None


@pytest.fixture
def pm_dir(tmp_path, monkeypatch):
    d = tmp_path / "pmkt"
    monkeypatch.setattr(config, "PREDICTION_MARKET_DIR", d)
    return d


def _write_day(pm_dir, day, source, rows):
    p = pm_dir / "snapshots" / f"{day}.{source}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                 encoding="utf-8")


class TestExecutableEdge:
    """ADJUDICATION 2026-08-22: |mid−mid| is price disagreement, not
    arbitrage. These pin the locked-profit arithmetic — reported beside the
    frozen trial metric, never deciding it."""

    def test_real_cross_computes_net_and_roic(self):
        kr = {"yes_bid": 0.38, "yes_ask": 0.40, "mid": 0.39,
              "close_time": "2026-09-17T18:00:00Z"}
        pr = {"yes_bid": 0.50, "yes_ask": 0.52, "mid": 0.51,
              "fee_rate": 0.04, "close_time": "2026-09-17T12:00:00Z"}
        out = mm.executable_edge(kr, pr, "2026-08-22")
        assert out["verdict"] == "MEASURED"
        assert out["direction"] == "yes_kalshi/no_polymarket"
        assert out["gross_locked"] == pytest.approx(0.10)
        # kalshi taker at p=0.40: 0.07*0.40*0.60 = 0.0168
        # polymarket taker at p=0.50, rate 0.04: 0.04*0.50 = 0.02
        assert out["fees"] == pytest.approx(0.0368)
        assert out["net_locked"] == pytest.approx(0.0632)
        assert out["capital_per_dollar_payout"] == pytest.approx(0.90)
        assert out["days_locked"] == 26
        assert out["annualized_roic"] == pytest.approx(
            (0.0632 / 0.90) * (365 / 26), abs=1e-3)

    def test_no_cross_is_net_negative_not_hidden(self):
        # bids strictly inside the other venue's ask: no locked profit exists
        kr = {"yes_bid": 0.48, "yes_ask": 0.52, "mid": 0.50,
              "close_time": None}
        pr = {"yes_bid": 0.49, "yes_ask": 0.53, "mid": 0.51,
              "fee_rate": 0.04, "close_time": None}
        out = mm.executable_edge(kr, pr, "2026-08-22")
        assert out["verdict"] == "MEASURED"
        assert out["net_locked"] < 0
        assert "annualized_roic" not in out
        assert "days_locked" not in out

    def test_one_sided_book_is_refused(self):
        kr = {"yes_bid": None, "yes_ask": 0.40, "mid": None}
        pr = {"yes_bid": 0.50, "yes_ask": 0.52, "mid": 0.51}
        out = mm.executable_edge(kr, pr, "2026-08-22")
        assert out["verdict"] == "REFUSED_NO_BOOK"

    def test_missing_fee_rate_falls_back_conservatively(self):
        kr = {"yes_bid": 0.38, "yes_ask": 0.40, "mid": 0.39,
              "close_time": None}
        pr = {"yes_bid": 0.50, "yes_ask": 0.52, "mid": 0.51,
              "fee_rate": None, "close_time": None}
        out = mm.executable_edge(kr, pr, "2026-08-22")
        # fallback 0.05 > measured 0.04 — missing data must cost MORE
        assert out["fees"] == pytest.approx(0.0168 + 0.05 * 0.50)


class TestMatchDay:
    def test_pairs_measure_divergence_against_the_cost_bar(self, pm_dir):
        _write_day(pm_dir, "2026-08-21", "kalshi", [
            _k("KXFEDDECISION-26SEP-H0", mid=0.70),
            _k("KXFEDDECISION-26SEP-H25", mid=0.29),
        ])
        _write_day(pm_dir, "2026-08-21", "polymarket", [
            _p("Will there be no change in Fed interest rates after the "
               "September 2026 meeting?", mid=0.62),   # d=0.08 > bar
            _p("Will the Fed increase interest rates by 25 bps after the "
               "September 2026 meeting?", mid=0.32),   # d=0.03 < bar
        ])
        out = mm.match_day("2026-08-21")
        assert out["status"] == "ok"
        assert out["n_measured"] == 2
        assert out["n_above_cost_bar"] == 1
        by_class = {p["action_class"]: p for p in out["pairs"]}
        assert by_class["maintain"]["above_cost_bar"] is True
        assert by_class["hike_25"]["above_cost_bar"] is False
        assert by_class["maintain"]["abs_divergence"] == pytest.approx(0.08)
        assert "persistence" in out["note"]

    def test_ambiguous_key_is_refused_not_chosen(self, pm_dir):
        _write_day(pm_dir, "2026-08-21", "kalshi", [
            _k("KXFEDDECISION-26SEP-H0", mid=0.70)])
        _write_day(pm_dir, "2026-08-21", "polymarket", [
            _p("Will there be no change in Fed interest rates after the "
               "September 2026 meeting?", mid=0.62, ticker="a"),
            _p("Will there be no change in Fed interest rates after the "
               "September 2026 meeting?", mid=0.99, ticker="b"),
        ])
        out = mm.match_day("2026-08-21")
        assert out["n_pairs"] == 0
        assert len(out["refused"]) == 1
        assert out["refused"][0]["tickers"] == ["a", "b"]
        assert "ambiguous" in out["refused"][0]["reason"]

    def test_one_sided_book_is_a_named_refusal(self, pm_dir):
        _write_day(pm_dir, "2026-08-21", "kalshi", [
            _k("KXFEDDECISION-26SEP-H0", mid=None)])
        _write_day(pm_dir, "2026-08-21", "polymarket", [
            _p("Will there be no change in Fed interest rates after the "
               "September 2026 meeting?", mid=0.62)])
        out = mm.match_day("2026-08-21")
        assert out["pairs"][0]["verdict"] == "REFUSED_NO_MID"
        assert out["n_measured"] == 0

    def test_a_day_with_one_venue_is_ok_empty(self, pm_dir):
        _write_day(pm_dir, "2026-08-21", "kalshi", [
            _k("KXFEDDECISION-26SEP-H0", mid=0.7)])
        out = mm.match_day("2026-08-21")
        assert out["status"] == "OK_EMPTY"
        assert "both" in out["reason"]

    def test_latest_divergence_picks_the_newest_complete_day(self, pm_dir):
        for day in ("2026-08-20", "2026-08-21"):
            _write_day(pm_dir, day, "kalshi",
                       [_k("KXFEDDECISION-26SEP-H0", mid=0.7)])
            _write_day(pm_dir, day, "polymarket", [
                _p("Will there be no change in Fed interest rates after "
                   "the September 2026 meeting?", mid=0.68)])
        # 08-22 exists on ONE venue only -> the complete day still wins
        _write_day(pm_dir, "2026-08-22", "kalshi",
                   [_k("KXFEDDECISION-26SEP-H0", mid=0.7)])
        out = mm.latest_divergence()
        assert out["status"] == "ok"
        assert out["day"] == "2026-08-21"

    def test_route_is_registered(self):
        from backend.routers.prediction_markets import router
        assert any(r.path == "/api/prediction-markets/divergence"
                   for r in router.routes)
