"""SEC ownership forms 3/4/5 — the whole filing, not just the flattering half.

WHY THIS EXISTS BESIDE `insider_form4.py`
=========================================
`parse_form4_open_market_buys` does exactly what its name says: transaction code
`P`, acquisitions only. That is the right input for a buy-signal feature and the
wrong input for a Teacher Library, because a corpus that can only see purchases
cannot answer the question the library is FOR.

The handoff's R6 puts it directly: *losers are studied with the same machinery as
winners — otherwise this is reverse-engineered hagiography*. A buys-only parser
does not merely make that hard, it makes the favourable answer structural. Ask
"do insider purchases predict returns" of a corpus containing nothing but
purchases and the sample cannot disagree.

So this parser keeps everything and labels it:

* every transaction code, acquisition AND disposition;
* derivative and non-derivative tables (an option exercise followed by a same-day
  sale is two rows that mean one thing, and they are only visible together);
* Form 3 holdings, which are not transactions at all — they are the opening
  balance an actor's later history is measured against;
* the flags R6 names as the things to test: officer / director / 10% owner, the
  role title, and whether the trade was made under a pre-arranged Rule 10b5-1
  plan or at the filer's discretion.

WHAT IT DOES NOT DO
===================
No scoring, no signal, no interpretation. It returns what the filing says. The
distinction between what a filing STATES and what we INFER from it is R6's other
half, and it is enforced by keeping inference out of this file entirely.

THE TIMESTAMP THAT MATTERS
==========================
`transaction_date` is when the insider traded. `period_of_report` is the same
thing from the form header. Neither is when anyone else could act. Only the
FILING date is public, and Section 16 allows two business days between them. This
parser returns all of them separately and never collapses them.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)

PARSER_VERSION = "ownership_forms/1.0.0"

#: SEC transaction codes (Form 4/5, Table I & II footnote key). Kept as data
#: rather than as branches so an unknown code is recorded as unknown instead of
#: silently landing in whichever branch happened to be last.
TRANSACTION_CODES: dict[str, str] = {
    "P": "open_market_purchase",
    "S": "open_market_sale",
    "A": "grant_award_or_other_acquisition",
    "D": "disposition_to_issuer",
    "F": "tax_withholding",
    "M": "option_exercise_or_conversion",
    "C": "conversion_of_derivative",
    "E": "expiration_short_derivative",
    "H": "expiration_long_derivative",
    "O": "out_of_money_option_exercise",
    "X": "in_the_money_option_exercise",
    "G": "gift",
    "L": "small_acquisition",
    "W": "will_or_inheritance",
    "Z": "voting_trust_deposit_or_withdrawal",
    "J": "other_see_footnote",
    "K": "equity_swap",
    "U": "tender_of_shares",
    "I": "discretionary_transaction",
}

#: The only codes where a market participant CHOSE to buy or sell at a market
#: price. Grants, tax withholding and option mechanics are compensation events;
#: counting them as sentiment is the classic insider-signal error, because an
#: executive whose shares are withheld for taxes has expressed nothing.
DISCRETIONARY_MARKET_CODES = frozenset({"P", "S"})


def _txt(node, path: str) -> str:
    """Ownership XML wraps most leaves in <value>; some filers omit it."""
    if node is None:
        return ""
    v = node.findtext(f"{path}/value")
    if v is None:
        v = node.findtext(path)
    return (v or "").strip()


def _num(node, path: str) -> float | None:
    raw = _txt(node, path)
    if not raw:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _flag(root, path: str) -> bool | None:
    """Tri-state on purpose. A filing that does not say is not a filing that
    says no, and `False` here would become "not an officer" downstream."""
    raw = (root.findtext(path) or "").strip().lower()
    if raw in ("1", "true"):
        return True
    if raw in ("0", "false"):
        return False
    return None


def _is_10b5_1(tx, root) -> bool | None:
    """Was this trade made under a pre-arranged plan?

    R6 names 10b5-1 vs discretionary as a mechanism to test, and it is the one
    field most likely to be misread. Since the 2023 amendments there is an
    explicit element; before that the only evidence is a footnote, and a filing
    with neither is genuinely UNKNOWN. Returning False for "no element" would
    quietly relabel every pre-2023 planned sale as discretionary — which is the
    exact direction that would manufacture a finding.
    """
    explicit = tx.find(".//transactionCoding/rule10b5-1Checked")
    if explicit is None:
        explicit = root.find(".//rule10b5-1Checked")
    if explicit is not None and (explicit.text or "").strip():
        return (explicit.text or "").strip().lower() in ("1", "true")
    blob = " ".join(f.text or "" for f in root.findall(".//footnote")).lower()
    if "10b5-1" in blob:
        return True
    return None


def _owner_role(root) -> str:
    """The officer title as filed, e.g. "Chief Financial Officer"."""
    return (root.findtext(".//reportingOwnerRelationship/officerTitle")
            or root.findtext(".//reportingOwnerRelationship/otherText")
            or "").strip()


def parse_ownership_form(xml_text: str | bytes) -> dict:
    """One Form 3/4/5 document → header, owner, and every reported line.

    Never raises on malformed input: returns `{"status": "PARSE_ERROR"}` with a
    reason, because one bad filing in a day's index must not take the day down.
    """
    try:
        root = ET.fromstring(xml_text.encode("utf-8")
                             if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as exc:
        return {"status": "PARSE_ERROR", "reason": f"xml:{exc}",
                "transactions": [], "holdings": []}

    doc_type = (root.findtext(".//documentType") or "").strip()
    period = (root.findtext(".//periodOfReport") or "").strip()
    issuer_cik = (root.findtext(".//issuer/issuerCik") or "").strip().lstrip("0")
    issuer_name = (root.findtext(".//issuer/issuerName") or "").strip()
    ticker = (root.findtext(".//issuer/issuerTradingSymbol") or "").strip().upper()

    owner_name = (root.findtext(
        ".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    owner_cik = (root.findtext(
        ".//reportingOwner/reportingOwnerId/rptOwnerCik") or "").strip()
    owner_cik = owner_cik.lstrip("0") or owner_cik

    header = {
        "status": "OK_DATA",
        "reason": "",
        "form_type": doc_type,
        "period_of_report": period,
        "issuer_cik": issuer_cik,
        "issuer_name": issuer_name,
        "ticker": ticker,
        "owner_name": owner_name or "Unknown",
        "owner_cik": owner_cik,
        "is_director": _flag(root, ".//reportingOwnerRelationship/isDirector"),
        "is_officer": _flag(root, ".//reportingOwnerRelationship/isOfficer"),
        "is_ten_pct_owner": _flag(
            root, ".//reportingOwnerRelationship/isTenPercentOwner"),
        "is_other": _flag(root, ".//reportingOwnerRelationship/isOther"),
        "officer_title": _owner_role(root),
        "parser_version": PARSER_VERSION,
    }

    transactions: list[dict] = []
    for derivative in (False, True):
        tag = ("derivativeTransaction" if derivative
               else "nonDerivativeTransaction")
        for tx in root.findall(f".//{tag}"):
            code = _txt(tx, ".//transactionCoding/transactionCode") or ""
            ad = _txt(tx, ".//transactionAcquiredDisposedCode") or ""
            shares = (_num(tx, ".//transactionShares")
                      or _num(tx, ".//underlyingSecurityShares"))
            price = _num(tx, ".//transactionPricePerShare")
            transactions.append({
                "is_derivative": derivative,
                "security_title": _txt(tx, ".//securityTitle"),
                "transaction_date": _txt(tx, ".//transactionDate"),
                "code": code,
                # An unknown code stays unknown. Mapping it to "other" would
                # make a future SEC addition silently indistinguishable from a
                # gift.
                "code_meaning": TRANSACTION_CODES.get(code, f"unknown:{code}"),
                "acquired_disposed": ad,
                "shares": shares,
                "price_per_share": price,
                "value": (shares * price
                          if shares is not None and price is not None else None),
                "shares_owned_after": _num(
                    tx, ".//postTransactionAmounts/sharesOwnedFollowingTransaction"),
                "ownership_type": _txt(
                    tx, ".//ownershipNature/directOrIndirectOwnership"),
                "rule_10b5_1": _is_10b5_1(tx, root),
                # The judgement a signal layer needs and must not re-derive from
                # the code by hand every time.
                "is_discretionary_market_trade": code in DISCRETIONARY_MARKET_CODES,
            })

    holdings: list[dict] = []
    for derivative in (False, True):
        tag = "derivativeHolding" if derivative else "nonDerivativeHolding"
        for h in root.findall(f".//{tag}"):
            holdings.append({
                "is_derivative": derivative,
                "security_title": _txt(h, ".//securityTitle"),
                "shares_owned": _num(
                    h, ".//postTransactionAmounts/sharesOwnedFollowingTransaction"),
                "ownership_type": _txt(
                    h, ".//ownershipNature/directOrIndirectOwnership"),
            })

    header["transactions"] = transactions
    header["holdings"] = holdings
    if not transactions and not holdings:
        # A Form 3 with no holdings is a real filing that says "I hold nothing",
        # and it is not the same as a document we failed to read.
        header["status"] = "OK_EMPTY"
        header["reason"] = "no_transactions_or_holdings_reported"
    return header


def summarise(parsed: dict) -> dict:
    """Counts a reviewer actually wants, with buys and sells side by side.

    Deliberately reports BOTH directions and the discretionary subset. A summary
    that led with "n_buys" would reintroduce the bias this module exists to
    remove, one layer up.
    """
    tx = parsed.get("transactions") or []
    disc = [t for t in tx if t["is_discretionary_market_trade"]]
    return {
        "form_type": parsed.get("form_type", ""),
        "n_transactions": len(tx),
        "n_holdings": len(parsed.get("holdings") or []),
        "n_discretionary": len(disc),
        "n_buys": sum(1 for t in disc if t["code"] == "P"),
        "n_sells": sum(1 for t in disc if t["code"] == "S"),
        "n_non_discretionary": len(tx) - len(disc),
        "codes": sorted({t["code"] for t in tx if t["code"]}),
        "n_10b5_1": sum(1 for t in tx if t["rule_10b5_1"] is True),
        "n_10b5_1_unknown": sum(1 for t in tx if t["rule_10b5_1"] is None),
    }
