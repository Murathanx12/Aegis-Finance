"""
Offline tests for the SEC Form 4 open-market-buy data source + the opportunistic
buy score. No network: the pure parser runs on a fixture XML, and the score runs
on normalised dicts. (Live `fetch_open_market_buys` is exercised only in slow
network tests, omitted here.)
"""

from backend.services.insider_form4 import parse_form4_open_market_buys
from backend.services.insider_trading import compute_opportunistic_buy_score


def _form4_xml(transactions: str, owner: str = "DOE JANE") -> str:
    """Minimal valid Form 4 ownershipDocument wrapping the given transaction XML."""
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>TEST</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable>{transactions}</nonDerivativeTable>
</ownershipDocument>"""


def _txn(code: str, shares: str, price: str, ad: str = "A", dt: str = "2026-05-01") -> str:
    return f"""
    <nonDerivativeTransaction>
      <transactionDate><value>{dt}</value></transactionDate>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>"""


class TestParseForm4:
    def test_extracts_open_market_purchase(self):
        xml = _form4_xml(_txn("P", "1000", "12.50"))
        buys = parse_form4_open_market_buys(xml)
        assert len(buys) == 1
        b = buys[0]
        assert b["name"] == "DOE JANE"
        assert b["shares"] == 1000.0
        assert b["value"] == 12500.0  # shares * price
        assert b["type"] == "P"

    def test_ignores_awards_and_options_and_sales(self):
        # A=award, M=option exercise, S=sale, F=tax — none are open-market buys
        xml = _form4_xml(_txn("A", "5000", "0") + _txn("M", "200", "1")
                         + _txn("S", "300", "20", ad="D") + _txn("F", "50", "10", ad="D"))
        assert parse_form4_open_market_buys(xml) == []

    def test_mixed_filing_keeps_only_the_purchase(self):
        xml = _form4_xml(_txn("A", "5000", "0") + _txn("P", "800", "10"))
        buys = parse_form4_open_market_buys(xml)
        assert len(buys) == 1 and buys[0]["shares"] == 800.0

    def test_zero_share_purchase_dropped(self):
        assert parse_form4_open_market_buys(_form4_xml(_txn("P", "0", "12"))) == []

    def test_garbage_xml_returns_empty_not_raises(self):
        assert parse_form4_open_market_buys("<not-valid") == []
        assert parse_form4_open_market_buys("") == []


class TestOpportunisticScore:
    def test_no_data_is_zero(self):
        assert compute_opportunistic_buy_score(None)["opp_score"] == 0.0
        assert compute_opportunistic_buy_score({"buys": []})["opp_score"] == 0.0

    def test_non_open_market_buys_score_zero(self):
        # buys present but tagged as awards (type 'A') → not the informative signal
        data = {"buys": [{"name": "X", "shares": 100, "value": 0, "type": "A"}]}
        s = compute_opportunistic_buy_score(data)
        assert s["opp_score"] == 0.0 and s["n_distinct_buyers"] == 0

    def test_single_buyer_below_cluster(self):
        data = {"buys": [{"name": "Jane", "shares": 1000, "value": 500_000, "type": "P"}]}
        s = compute_opportunistic_buy_score(data)
        assert s["n_distinct_buyers"] == 1
        assert s["cluster_buy"] is False
        # score = 1 buyer + tanh(0.5) ≈ 1.46
        assert 1.4 < s["opp_score"] < 1.5

    def test_three_distinct_buyers_is_cluster(self):
        data = {"buys": [
            {"name": "Jane", "shares": 1, "value": 10, "type": "P"},
            {"name": "John", "shares": 1, "value": 10, "type": "P"},
            {"name": "Amir", "shares": 1, "value": 10, "type": "P"},
        ]}
        s = compute_opportunistic_buy_score(data)
        assert s["n_distinct_buyers"] == 3
        assert s["cluster_buy"] is True

    def test_same_insider_twice_counts_once(self):
        data = {"buys": [
            {"name": "Jane", "shares": 1, "value": 10, "type": "P"},
            {"name": "jane", "shares": 1, "value": 10, "type": "P"},  # case-folded dup
        ]}
        assert compute_opportunistic_buy_score(data)["n_distinct_buyers"] == 1

    def test_value_bonus_saturates_not_explodes(self):
        # a $100M buy must not blow the score past n_buyers + 1
        data = {"buys": [{"name": "Jane", "shares": 1, "value": 100_000_000, "type": "P"}]}
        s = compute_opportunistic_buy_score(data)
        assert 1.99 < s["opp_score"] <= 2.0

    def test_more_buyers_outranks_fewer(self):
        one = compute_opportunistic_buy_score(
            {"buys": [{"name": "A", "shares": 1, "value": 999_999_999, "type": "P"}]})
        three = compute_opportunistic_buy_score({"buys": [
            {"name": "A", "shares": 1, "value": 10, "type": "P"},
            {"name": "B", "shares": 1, "value": 10, "type": "P"},
            {"name": "C", "shares": 1, "value": 10, "type": "P"}]})
        # cross-sectional rank must favour the cluster even with tiny dollars
        assert three["opp_score"] > one["opp_score"]
