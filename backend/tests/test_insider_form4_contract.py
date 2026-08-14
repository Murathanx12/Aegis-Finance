"""Form 4 source contract — the Track E prerequisite.

`OK_DATA` / `OK_EMPTY` / `UNAVAILABLE`, end to end from the fetcher through the
scorer. This is the pre-registered prerequisite for the Teacher Library, and it
exists because the collector's history is a list of times this exact conflation
reported confident zeros:

  - Finnhub returned uncoded transactions, the filter discarded 100% of real
    buying, and the score read `0.0 — "No open-market insider purchases"` for
    every ticker on earth;
  - the SEC Form 4 fetcher then returned the same empty shape for a missing
    CIK, a failed submissions fetch, and a genuinely quiet six months;
  - and `_ticker_cik_map` cached `{}` on failure for the life of the process,
    so one transient 403 silenced the entire universe until redeploy.

None of those raised anything. All of them ran green.

Offline: every SEC call is monkeypatched.
"""

from __future__ import annotations

import pytest

from backend.services import insider_form4 as F4
from backend.services.insider_trading import compute_opportunistic_buy_score


@pytest.fixture(autouse=True)
def _clear_cik_cache():
    F4._CIK_MAP_CACHE.clear()
    yield
    F4._CIK_MAP_CACHE.clear()


class _Resp:
    def __init__(self, payload=None, text=""):
        self._payload, self.text = payload, text

    def json(self):
        return self._payload


_ONE_BUY_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId>
    <rptOwnerName>DOE JANE</rptOwnerName><rptOwnerCik>0000012345</rptOwnerCik>
  </reportingOwnerId></reportingOwner>
  <nonDerivativeTransaction>
    <transactionDate><value>2026-08-01</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>1000</value></transactionShares>
      <transactionPricePerShare><value>50</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction>
</ownershipDocument>"""


def _subs(n_form4: int = 1, fdate: str = "2026-08-10"):
    return {"filings": {"recent": {
        "form": ["4"] * n_form4,
        "accessionNumber": [f"0001-{i}" for i in range(n_form4)],
        "primaryDocument": ["doc.xml"] * n_form4,
        "filingDate": [fdate] * n_form4}}}


# ── the cache that could silence the universe ──────────────────────────────

def test_a_failed_cik_map_is_not_cached(monkeypatch):
    """`@lru_cache` + `return {}` on failure meant ONE transient 403 reported
    "no insider buying" for every ticker for the life of the process."""
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("SEC 403")
        return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})

    monkeypatch.setattr(F4, "_sec_get", flaky)
    assert F4._ticker_cik_map() == {}          # failure
    assert not F4.cik_map_is_loaded()
    assert F4._ticker_cik_map() == {"AAPL": "0000320193"}   # retried, not cached
    assert F4.cik_map_is_loaded()


def test_a_successful_map_is_cached(monkeypatch):
    calls = {"n": 0}

    def once(url):
        calls["n"] += 1
        return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})

    monkeypatch.setattr(F4, "_sec_get", once)
    F4._ticker_cik_map()
    F4._ticker_cik_map()
    assert calls["n"] == 1


def test_an_empty_map_is_not_cached_either(monkeypatch):
    monkeypatch.setattr(F4, "_sec_get", lambda url: _Resp({}))
    assert F4._ticker_cik_map() == {}
    assert not F4.cik_map_is_loaded()


# ── the three failures that used to look identical ─────────────────────────

def test_a_dead_cik_map_is_unavailable_not_zero_buys(monkeypatch):
    monkeypatch.setattr(F4, "_sec_get",
                        lambda url: (_ for _ in ()).throw(RuntimeError("403")))
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_UNAVAILABLE
    assert out["reason"] == "cik_map_unavailable"


def test_an_unknown_ticker_is_distinguishable_from_a_dead_map(monkeypatch):
    monkeypatch.setattr(F4, "_sec_get",
                        lambda url: _Resp({"0": {"ticker": "AAPL",
                                                 "cik_str": 320193}}))
    out = F4.fetch_open_market_buys("NOTATICKER")
    assert out["status"] == F4.STATUS_UNAVAILABLE
    assert out["reason"] == "ticker_not_in_cik_map"


def test_a_failed_submissions_fetch_is_unavailable(monkeypatch):
    def get(url):
        if "company_tickers" in url:
            return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})
        raise RuntimeError("gateway")
    monkeypatch.setattr(F4, "_sec_get", get)
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_UNAVAILABLE
    assert out["reason"] == "submissions_fetch_failed"


def test_a_genuinely_quiet_window_is_OK_EMPTY(monkeypatch):
    def get(url):
        if "company_tickers" in url:
            return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})
        return _Resp(_subs(n_form4=0))
    monkeypatch.setattr(F4, "_sec_get", get)
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_OK_EMPTY
    assert out["reason"] == "no_form4_filings_in_window"
    assert out["n_buys"] == 0


def test_filings_present_but_no_purchases_is_also_OK_EMPTY(monkeypatch):
    def get(url):
        if "company_tickers" in url:
            return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})
        return _Resp(_subs(n_form4=2))
    monkeypatch.setattr(F4, "_sec_get", get)
    monkeypatch.setattr(F4, "_filing_xml", lambda *a: "<ownershipDocument/>")
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_OK_EMPTY
    assert out["reason"] == "no_open_market_purchases"
    assert out["n_filings_examined"] == 2


def test_real_purchases_are_OK_DATA(monkeypatch):
    def get(url):
        if "company_tickers" in url:
            return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})
        return _Resp(_subs(n_form4=1))
    monkeypatch.setattr(F4, "_sec_get", get)
    monkeypatch.setattr(F4, "_filing_xml", lambda *a: _ONE_BUY_XML)
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_OK_DATA
    assert out["n_buys"] == 1
    assert out["buys"][0]["filing_date"] == "2026-08-10"
    assert out["total_buy_value"] == pytest.approx(50_000.0)


# ── the partial case, which is the subtle one ──────────────────────────────

def test_an_empty_result_with_unreadable_filings_is_UNAVAILABLE(monkeypatch):
    """An absence we did not fully look for is not an absence. Three Form 4s in
    the window, none of them readable, zero purchases found — reporting that as
    "no insider buying" is a claim the fetch did not earn."""
    def get(url):
        if "company_tickers" in url:
            return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})
        return _Resp(_subs(n_form4=3))
    monkeypatch.setattr(F4, "_sec_get", get)
    monkeypatch.setattr(F4, "_filing_xml", lambda *a: None)
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_UNAVAILABLE
    assert out["reason"] == "empty_but_unverified"
    assert out["n_filings_unfetchable"] == 3


def test_purchases_found_with_some_filings_unreadable_is_a_lower_bound(monkeypatch):
    """Real buying was seen, so the answer is data — but the COUNT is a floor,
    and saying so is the difference between a measurement and a number."""
    def get(url):
        if "company_tickers" in url:
            return _Resp({"0": {"ticker": "AAPL", "cik_str": 320193}})
        return _Resp(_subs(n_form4=2))
    seq = [_ONE_BUY_XML, None]
    monkeypatch.setattr(F4, "_sec_get", get)
    monkeypatch.setattr(F4, "_filing_xml", lambda *a: seq.pop(0))
    out = F4.fetch_open_market_buys("AAPL")
    assert out["status"] == F4.STATUS_OK_DATA
    assert out["partial"] is True
    assert out["n_filings_unfetchable"] == 1


# ── the contract survives into the score ───────────────────────────────────

@pytest.mark.parametrize("reason", ["cik_map_unavailable",
                                    "submissions_fetch_failed",
                                    "empty_but_unverified"])
def test_the_scorer_refuses_to_score_an_unavailable_source(reason):
    """The layer that writes the PIT store must not turn any of these into 0.0."""
    s = compute_opportunistic_buy_score(
        {"status": "UNAVAILABLE", "reason": reason, "buys": [], "n_buys": 0})
    assert s["available"] is False
    assert s["opp_score"] is None
    assert s["reason"] == reason
    assert "NOT evidence of no insider buying" in s["interpretation"]


def test_the_scorer_still_scores_a_genuine_zero():
    """OK_EMPTY is a measurement and must keep scoring 0.0 — the fix must not
    turn every quiet ticker into an unscoreable one."""
    s = compute_opportunistic_buy_score(
        {"status": "OK_EMPTY", "reason": "no_open_market_purchases",
         "buys": [], "n_buys": 0, "codes_available": True})
    assert s["available"] is True
    assert s["opp_score"] == 0.0


def test_an_unavailable_source_writes_nothing_to_the_pit_store(tmp_path):
    """End to end: the collector must record UNSCOREABLE, not a fabricated 0.0
    observation that later research reads as fact."""
    from backend.db import init_db
    from backend.services.portfolio_intelligence import insider_collector as IC
    p = tmp_path / "pit.db"
    init_db(p)
    out = IC.collect_insider_opp_scores(
        db_path=p, tickers=["AAPL"], throttle_days=0,
        fetch=lambda t: {"status": "UNAVAILABLE",
                         "reason": "cik_map_unavailable",
                         "buys": [], "n_buys": 0})
    assert out["written"] == 0
    assert out["unscoreable"] == {"AAPL": "cik_map_unavailable"}


def test_a_genuine_zero_still_reaches_the_pit_store(tmp_path):
    """The counterweight. If the fix turned every quiet ticker unscoreable the
    signal would stop accruing and the trial would quietly starve."""
    from backend.db import init_db
    from backend.services.portfolio_intelligence import insider_collector as IC
    p = tmp_path / "pit.db"
    init_db(p)
    out = IC.collect_insider_opp_scores(
        db_path=p, tickers=["AAPL"], throttle_days=0,
        fetch=lambda t: {"status": "OK_EMPTY",
                         "reason": "no_open_market_purchases",
                         "codes_available": True, "buys": [], "n_buys": 0})
    assert out["written"] == 1
    assert out["unscoreable"] == {}
    assert out["scores"]["AAPL"] == 0.0
