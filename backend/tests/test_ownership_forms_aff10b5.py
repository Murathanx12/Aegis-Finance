"""The Rule 10b5-1 flag on CURRENT Form 4 filings (schema X0609).

MEASURED 2026-09-30 on four live EDGAR filings: the checkbox is the
filing-level element `<aff10b5One>` directly under `ownershipDocument`, spelled
`1`, `0` or `false`. None carried the per-line `rule10b5-1Checked` the parser
looked for, so every current filing read as "unknown" unless a footnote
happened to name the plan. The fixture below keeps the real document's shape
(whitespace, address block, footnoteId references, footnotes, signature),
with a made-up issuer and owner. Offline.
"""
from __future__ import annotations

from datetime import date, timedelta

from backend.services import ownership_forms as OF

_D = (date.today() - timedelta(days=1)).isoformat()


def _current_filing(box: str | None, footnotes: str = "", code: str = "P",
                    ad: str = "A") -> str:
    box_el = f"\n    <aff10b5One>{box}</aff10b5One>\n" if box is not None else "\n"
    fn = f"""
    <footnotes>
{footnotes}
    </footnotes>""" if footnotes else ""
    return f"""<?xml version="1.0"?>
<ownershipDocument>

    <schemaVersion>X0609</schemaVersion>

    <documentType>4</documentType>

    <periodOfReport>{_D}</periodOfReport>

    <issuer>
        <issuerCik>0009999999</issuerCik>
        <issuerName>Example Bancorp</issuerName>
        <issuerTradingSymbol>EXBK</issuerTradingSymbol>
        <issuerForeignTradingSymbol></issuerForeignTradingSymbol>
    </issuer>

    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0008888888</rptOwnerCik>
            <rptOwnerName>Doe Jane</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerAddress>
            <rptOwnerNonUSAddressFlag>false</rptOwnerNonUSAddressFlag>
            <rptOwnerStreet1>1 MAIN STREET</rptOwnerStreet1>
            <rptOwnerStreet2></rptOwnerStreet2>
            <rptOwnerCity>SPRINGFIELD</rptOwnerCity>
            <rptOwnerState>CA</rptOwnerState>
            <rptOwnerZipCode>90000</rptOwnerZipCode>
            <rptOwnerStateDescription></rptOwnerStateDescription>
        </reportingOwnerAddress>
        <reportingOwnerRelationship>
            <isDirector>1</isDirector>
        </reportingOwnerRelationship>
    </reportingOwner>
{box_el}
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <securityTitle>
                <value>Common Stock</value>
            </securityTitle>
            <transactionDate>
                <value>{_D}</value>
                <footnoteId id="F2"/>
            </transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>{code}</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares>
                    <value>125</value>
                    <footnoteId id="F1"/>
                </transactionShares>
                <transactionPricePerShare>
                    <value>34.03</value>
                </transactionPricePerShare>
                <transactionAcquiredDisposedCode>
                    <value>{ad}</value>
                </transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction>
                    <value>62787</value>
                </sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership>
                    <value>D</value>
                </directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
    </nonDerivativeTable>{fn}
    <ownerSignature>
        <signatureName>/s/ Jane Doe</signatureName>
        <signatureDate>{_D}</signatureDate>
    </ownerSignature>
</ownershipDocument>
"""


def _line(xml: str) -> dict:
    p = OF.parse_ownership_form(xml)
    assert p["status"] == "OK_DATA"
    return p["transactions"][0]


def test_a_checked_filing_box_is_read_as_a_plan_trade():
    t = _line(_current_filing("1"))
    assert t["rule_10b5_1"] is True
    assert t["rule_10b5_1_basis"] == "filing_box"


def test_an_unchecked_box_is_false_whichever_spelling_the_filer_used():
    for spelling in ("0", "false"):
        t = _line(_current_filing(spelling, code="S", ad="D"))
        assert t["rule_10b5_1"] is False, spelling
        assert t["rule_10b5_1_basis"] == "filing_box"
    assert OF.summarise(OF.parse_ownership_form(_current_filing("0")))["n_10b5_1_unknown"] == 0


def test_the_real_filing_with_box_and_plan_footnotes_reads_true_from_the_box():
    fns = ('        <footnote id="F1">Transactions executed in accordance with 10b5-1 '
           'purchase plan</footnote>\n'
           '        <footnote id="F2">Adoption date of referenced 10b5-1(c) plan is: '
           '04-28-2026</footnote>')
    t = _line(_current_filing("1", footnotes=fns))
    assert (t["rule_10b5_1"], t["rule_10b5_1_basis"]) == (True, "filing_box")


def test_an_older_filing_without_the_box_keeps_the_old_readings():
    # no box, no footnote -> unknown (never False)
    t = _line(_current_filing(None))
    assert (t["rule_10b5_1"], t["rule_10b5_1_basis"]) == (None, "none")
    # no box, a footnote naming the plan -> True from the footnote
    t = _line(_current_filing(None, footnotes='        <footnote id="F1">Sale under a Rule '
                                              '10b5-1 trading plan.</footnote>'))
    assert (t["rule_10b5_1"], t["rule_10b5_1_basis"]) == (True, "footnote")


def test_a_per_line_element_still_wins_over_the_filing_box():
    xml = _current_filing("1").replace(
        "<equitySwapInvolved>0</equitySwapInvolved>",
        "<equitySwapInvolved>0</equitySwapInvolved><rule10b5-1Checked>0</rule10b5-1Checked>")
    t = _line(xml)
    assert (t["rule_10b5_1"], t["rule_10b5_1_basis"]) == (False, "line_element")


def test_official_rows_carry_the_box_basis_under_its_existing_name():
    from datetime import datetime, timezone
    from backend.services import official_sources as OS
    xml = _current_filing("1")
    rows = OS.insider_rows(OF.parse_ownership_form(xml), accession="a", basis="EDGAR_ACCEPTANCE",
                           public_utc=datetime.now(timezone.utc), plan_flag=OS.aff10b5_flag(xml))
    assert rows[0]["rule_10b5_1"] is True
    assert rows[0]["rule_10b5_1_basis"] == "aff10b5One_filing_box"
