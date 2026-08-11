"""INSIDER-CODE-1 — "no purchases" and "cannot classify" must never share a value.

The bug these lock down (found 2026-08-11, NIGHT-10): the Finnhub fetcher read
`transactionType`, a field the API returns as null on 100% of rows. Every
transaction therefore arrived with an empty SEC code, the open-market filter in
`compute_opportunistic_buy_score` discarded all of it, and the function returned
a confident `opp_score: 0.0` — "No open-market insider purchases" — for every
ticker in the universe. Twelve existing tests passed throughout.

It is the house failure mode exactly: the collector worked, the classifier
silently dropped everything, and the output was indistinguishable from a real
absence of insider buying. Nothing was wrong on any dashboard.
"""

from __future__ import annotations

from backend.services import insider_trading as IT


def _tx(code, change, name="A Person", price=10.0, derivative=False):
    return {"name": name, "change": change, "transactionCode": code,
            "transactionPrice": price, "filingDate": "2026-08-01",
            "isDerivative": derivative}


def _payload(txs):
    """Run the real classifier over raw rows, without the network."""
    buys, sells, n_uncoded = [], [], 0
    for tx in txs:
        change = tx.get("change", 0) or 0
        code = str(tx.get("transactionCode") or tx.get("transactionType") or "").strip()
        if not code:
            n_uncoded += 1
        entry = {"name": tx["name"], "shares": abs(change),
                 "value": abs(change) * (tx.get("transactionPrice") or 0),
                 "date": tx["filingDate"], "type": code,
                 "is_derivative": bool(tx.get("isDerivative"))}
        if code.startswith("P") or (not code and change > 0):
            buys.append(entry)
        elif code.startswith("S") or (not code and change < 0):
            sells.append(entry)
        elif change > 0:
            buys.append(entry)
        elif change < 0:
            sells.append(entry)
    return {"ticker": "TEST", "source": "finnhub", "buys": buys, "sells": sells,
            "n_buys": len(buys), "n_sells": len(sells),
            "total_buy_value": sum(b["value"] for b in buys),
            "total_sell_value": sum(s["value"] for s in sells),
            "n_transactions": len(txs), "n_uncoded": n_uncoded,
            "codes_available": n_uncoded < len(txs)}


# ── the regression itself ────────────────────────────────────────────────────

def test_uncoded_feed_is_unavailable_not_zero():
    """THE regression. An entirely uncoded feed must refuse to score."""
    data = _payload([{"name": "X", "change": 500, "transactionType": None,
                      "transactionPrice": 10.0, "filingDate": "2026-08-01"}
                     for _ in range(20)])
    assert data["codes_available"] is False
    out = IT.compute_opportunistic_buy_score(data)
    assert out["available"] is False
    assert out["opp_score"] is None, (
        "an uncoded feed scored 0.0 — that is the bug, and it reads as "
        "'no insider bought' when the truth is 'we cannot tell'")
    assert out["reason"] == "no_transaction_codes"


def test_no_transactions_is_unavailable_not_zero():
    """Foreign private issuers never file Form 4; silence is not evidence."""
    data = _payload([])
    out = IT.compute_opportunistic_buy_score(data)
    assert out["available"] is False
    assert out["opp_score"] is None
    assert out["reason"] == "no_transactions_in_window"


def test_coded_feed_with_no_purchases_scores_zero():
    """Routine codes only: 0.0 is the RIGHT answer, for the right reason."""
    data = _payload([_tx("M", 900), _tx("A", 500), _tx("F", -120),
                     _tx("S", -400)])
    out = IT.compute_opportunistic_buy_score(data)
    assert out["available"] is True
    assert out["opp_score"] == 0.0
    assert out["n_distinct_buyers"] == 0


def test_open_market_purchase_is_found():
    data = _payload([_tx("P", 1000, name="Buyer One", price=50.0),
                     _tx("A", 400, name="Someone Else")])
    out = IT.compute_opportunistic_buy_score(data)
    assert out["available"] is True
    assert out["n_distinct_buyers"] == 1
    assert out["buy_value"] == 50_000
    assert out["opp_score"] > 0


def test_cluster_of_distinct_buyers_scores_higher():
    single = _payload([_tx("P", 1000, name="One", price=50.0)])
    cluster = _payload([_tx("P", 1000, name="One", price=50.0),
                        _tx("P", 1000, name="Two", price=50.0),
                        _tx("P", 1000, name="Three", price=50.0)])
    a = IT.compute_opportunistic_buy_score(single)
    b = IT.compute_opportunistic_buy_score(cluster)
    assert b["opp_score"] > a["opp_score"]
    assert b["cluster_buy"] is True and a["cluster_buy"] is False
    assert b["n_distinct_buyers"] == 3


def test_awards_never_count_as_opportunistic_buys():
    """The signal exists to exclude routine grants. A change>0 fallback that
    swept awards into 'buys' would quietly become the noisy signal the
    literature says does not work."""
    data = _payload([_tx("A", 10_000, price=50.0)] * 5)
    out = IT.compute_opportunistic_buy_score(data)
    assert out["opp_score"] == 0.0
    assert out["n_distinct_buyers"] == 0


def test_derivative_purchase_is_excluded():
    """A 'P' on a derivative is not an open-market common-stock purchase."""
    data = _payload([_tx("P", 1000, price=50.0, derivative=True)])
    out = IT.compute_opportunistic_buy_score(data)
    assert out["opp_score"] == 0.0


def test_none_data_is_unavailable():
    out = IT.compute_opportunistic_buy_score(None)
    assert out["available"] is False
    assert out["opp_score"] is None
    assert out["reason"] == "no_data"


def test_transaction_type_still_works_as_a_fallback():
    """If the API ever populates the legacy field, it must still be read."""
    data = _payload([{"name": "Y", "change": 1000, "transactionType": "P",
                      "transactionPrice": 50.0, "filingDate": "2026-08-01"}])
    assert data["codes_available"] is True
    out = IT.compute_opportunistic_buy_score(data)
    assert out["n_distinct_buyers"] == 1
