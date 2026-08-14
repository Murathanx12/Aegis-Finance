"""Forms 3/4/5: the whole filing, including the parts that look bad.

Offline and deterministic — these are XML fixtures shaped like real ownership
documents. Nothing here touches EDGAR.

THE PROPERTY UNDER TEST
=======================
R6 of the handoff: *losers are studied with the same machinery as winners —
otherwise this is reverse-engineered hagiography.* The existing Form 4 path
parses transaction code `P`, acquisitions only. A corpus built from it cannot
disagree with "insider buying is bullish", because it contains nothing else.
So the first test is that a sale survives parsing, and most of the rest are
about not quietly turning compensation mechanics into sentiment.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.services import ownership_forms as OF
from backend.services import sec_daily_index as IDX


def _doc(body: str, form: str = "4", owner_extra: str = "") -> str:
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <documentType>{form}</documentType>
  <periodOfReport>2026-08-10</periodOfReport>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>APPLE INC</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001214156</rptOwnerCik>
      <rptOwnerName>COOK TIMOTHY D</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  {owner_extra}
  {body}
</ownershipDocument>"""


def _tx(code: str, ad: str, shares: str = "1000", price: str = "50.00",
        plan: str | None = None) -> str:
    rule = (f"<rule10b5-1Checked>{plan}</rule10b5-1Checked>"
            if plan is not None else "")
    return f"""
  <nonDerivativeTransaction>
    <securityTitle><value>Common Stock</value></securityTitle>
    <transactionDate><value>2026-08-10</value></transactionDate>
    <transactionCoding>
      <transactionCode>{code}</transactionCode>
      {rule}
    </transactionCoding>
    <transactionAmounts>
      <transactionShares><value>{shares}</value></transactionShares>
      <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
    <postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>500000</value></sharesOwnedFollowingTransaction>
    </postTransactionAmounts>
    <ownershipNature>
      <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
    </ownershipNature>
  </nonDerivativeTransaction>"""


# ── the hagiography test ────────────────────────────────────────────────────

def test_a_sale_survives_parsing():
    p = OF.parse_ownership_form(_doc(_tx("S", "D")))

    assert p["status"] == "OK_DATA"
    assert len(p["transactions"]) == 1
    t = p["transactions"][0]
    assert t["code"] == "S"
    assert t["code_meaning"] == "open_market_sale"
    assert t["acquired_disposed"] == "D"
    assert t["is_discretionary_market_trade"] is True
    # The old parser returned [] for this document. A library that cannot see a
    # sale cannot be asked whether insiders are right.
    assert OF.summarise(p)["n_sells"] == 1


def test_buys_and_sells_are_both_counted_in_the_summary():
    p = OF.parse_ownership_form(_doc(_tx("P", "A") + _tx("S", "D")))
    s = OF.summarise(p)

    assert (s["n_buys"], s["n_sells"]) == (1, 1)
    assert s["n_discretionary"] == 2


# ── compensation mechanics are not sentiment ────────────────────────────────

@pytest.mark.parametrize("code,meaning", [
    ("A", "grant_award_or_other_acquisition"),
    ("F", "tax_withholding"),
    ("M", "option_exercise_or_conversion"),
    ("G", "gift"),
])
def test_non_market_codes_are_kept_but_marked_non_discretionary(code, meaning):
    p = OF.parse_ownership_form(_doc(_tx(code, "A")))
    t = p["transactions"][0]

    # Kept — a study may want them. NOT discretionary: an executive whose shares
    # are withheld for taxes has expressed no opinion, and counting that as a
    # purchase is how "insiders are buying" charts get built out of payroll.
    assert t["code_meaning"] == meaning
    assert t["is_discretionary_market_trade"] is False
    assert OF.summarise(p)["n_buys"] == 0
    assert OF.summarise(p)["n_non_discretionary"] == 1


def test_an_unknown_transaction_code_stays_unknown():
    p = OF.parse_ownership_form(_doc(_tx("Q", "A")))
    # Not silently folded into "other": a future SEC addition must be visibly
    # unhandled rather than indistinguishable from a gift.
    assert p["transactions"][0]["code_meaning"] == "unknown:Q"


# ── 10b5-1: the tri-state that must not collapse ────────────────────────────

def test_an_explicit_10b5_1_flag_is_read():
    p = OF.parse_ownership_form(_doc(_tx("S", "D", plan="1")))
    assert p["transactions"][0]["rule_10b5_1"] is True


def test_an_explicit_absence_is_false_not_unknown():
    p = OF.parse_ownership_form(_doc(_tx("S", "D", plan="0")))
    assert p["transactions"][0]["rule_10b5_1"] is False


def test_a_filing_that_does_not_say_returns_unknown_not_false():
    p = OF.parse_ownership_form(_doc(_tx("S", "D")))
    # Pre-2023 filings carry no element at all. Returning False would relabel
    # every planned sale before 2023 as discretionary — which would manufacture
    # exactly the finding a 10b5-1 study is trying to test.
    assert p["transactions"][0]["rule_10b5_1"] is None
    assert OF.summarise(p)["n_10b5_1_unknown"] == 1


def test_a_footnote_mentioning_the_plan_counts_as_evidence():
    fn = "<footnote id='F1'>Sale under a Rule 10b5-1 trading plan.</footnote>"
    p = OF.parse_ownership_form(_doc(_tx("S", "D"), owner_extra=fn))
    assert p["transactions"][0]["rule_10b5_1"] is True


# ── the fields R6 names as mechanisms to test ───────────────────────────────

def test_role_and_relationship_flags_are_captured():
    p = OF.parse_ownership_form(_doc(_tx("P", "A")))

    # "CEO vs CFO vs director" is a question R6 asks directly; it is
    # unanswerable unless these travel on the row.
    assert p["officer_title"] == "Chief Executive Officer"
    assert p["is_officer"] is True
    assert p["is_director"] is True
    assert p["is_ten_pct_owner"] is False
    assert p["owner_cik"] == "1214156"          # leading zeros stripped


def test_a_missing_relationship_flag_is_none_not_false():
    doc = _doc(_tx("P", "A")).replace(
        "<isTenPercentOwner>0</isTenPercentOwner>", "")
    p = OF.parse_ownership_form(doc)
    # A filing that does not say is not a filing that says no.
    assert p["is_ten_pct_owner"] is None


# ── Form 3 is an opening balance, not a trade ───────────────────────────────

def test_form_3_holdings_are_parsed_rather_than_dropped():
    holding = """
  <nonDerivativeHolding>
    <securityTitle><value>Common Stock</value></securityTitle>
    <postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>12345</value></sharesOwnedFollowingTransaction>
    </postTransactionAmounts>
    <ownershipNature>
      <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
    </ownershipNature>
  </nonDerivativeHolding>"""
    p = OF.parse_ownership_form(_doc(holding, form="3"))

    assert p["form_type"] == "3"
    assert p["transactions"] == []
    assert p["holdings"][0]["shares_owned"] == 12345
    # Without it, an actor's first appearance in the corpus looks like their
    # first trade, and every later delta is measured from a wrong baseline.
    assert p["status"] == "OK_DATA"


def test_an_empty_form_3_is_ok_empty_not_a_parse_error():
    p = OF.parse_ownership_form(_doc("", form="3"))
    assert p["status"] == "OK_EMPTY"
    assert "no_transactions_or_holdings" in p["reason"]


def test_malformed_xml_is_a_parse_error_not_an_exception():
    p = OF.parse_ownership_form("<ownershipDocument><unclosed>")
    assert p["status"] == "PARSE_ERROR"
    assert p["transactions"] == []


def test_derivative_transactions_are_kept_and_labelled():
    body = """
  <derivativeTransaction>
    <securityTitle><value>Employee Stock Option</value></securityTitle>
    <transactionDate><value>2026-08-10</value></transactionDate>
    <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>2000</value></transactionShares>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </derivativeTransaction>"""
    p = OF.parse_ownership_form(_doc(body + _tx("S", "D")))

    # An option exercise followed by a same-day sale is two rows that mean one
    # thing, and they are only visible together.
    assert [t["is_derivative"] for t in p["transactions"]] == [False, True]
    assert {t["code"] for t in p["transactions"]} == {"S", "M"}


# ── the daily index ─────────────────────────────────────────────────────────

#: The LIVE format, copied from `form.20260813.idx` (1.39 MB, fetched
#: 2026-08-14): the date is YYYYMMDD with no separators, and rows carry
#: trailing whitespace. The first version of this fixture invented
#: `YYYY-MM-DD`, the parser was written to match the invention, and the whole
#: path then reported a Thursday of insider filings as "index published but
#: held no ownership forms". A fixture that agrees with the parser and not with
#: the source proves only that they agree.
_IDX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Aug 13, 2026
Comments:              webmaster@sec.gov

Form Type   Company Name                                                  CIK
      Date Filed  File Name
------------------------------------------------------------------------------------------
4                Apple Inc Officer Person                                      1214156     20260813    edgar/data/1214156/0001214156-26-000123.txt
3                New Director Person                                            999888     20260813    edgar/data/999888/0000999888-26-000001.txt
8-K              Some Company Inc                                               111222     20260813    edgar/data/111222/0000111222-26-000009.txt
4/A              Amended Filer With Spaces LLC                                  333444     20260813    edgar/data/333444/0000333444-26-000002.txt
"""

#: The dashed spelling, kept so the tolerance is deliberate rather than luck.
_IDX_DASHED = _IDX.replace("20260813    edgar", "2026-08-13  edgar")


@pytest.mark.parametrize("blob", [_IDX, _IDX_DASHED])
def test_the_index_keeps_only_ownership_forms(blob):
    rows = IDX.parse_index(blob)

    assert [r["form_type"] for r in rows] == ["4", "3", "4/A"]
    # Normalised to ISO whichever way the source spelled it.
    assert all(r["filed_date"] == "2026-08-13" for r in rows)


def test_company_names_containing_spaces_survive():
    rows = IDX.parse_index(_IDX)
    # Splitting on whitespace breaks on almost every real company name, which
    # is why the form type and trailing path are anchored instead.
    assert rows[2]["company"] == "Amended Filer With Spaces LLC"
    assert rows[2]["accession"] == "0000333444-26-000002"
    assert rows[2]["cik"] == "333444"


def test_a_weekend_is_reported_empty_with_its_reason_not_as_a_failure():
    # 2026-08-15 is a Saturday.
    out = IDX.fetch_index(date(2026, 8, 15))
    assert out["status"] == "OK_EMPTY"
    assert "weekend" in out["reason"]
    assert out["filings"] == []


def test_a_historical_day_is_refused_unless_asked_for_explicitly():
    today = date(2026, 8, 14)
    old = today - timedelta(days=30)

    out = IDX.collect_day(old, today=today)

    # Same discipline COPY-LAB already enforces at the lane, applied at the
    # source. A corpus that quietly absorbed history would make every forward
    # claim built on it unfalsifiable.
    assert out["status"] == "REFUSED"
    assert "historical" in out["reason"]
    assert out["parsed"] == []
