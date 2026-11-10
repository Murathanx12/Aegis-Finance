"""apply_wls against a MEMB export written with EXCHANGE codes (synthetic rows only)."""

from __future__ import annotations

import pandas as pd

from scripts import contest_calendar as cc


def _export(path, with_symbols: bool) -> None:
    rows = pd.DataFrame({
        "Ticker": ["AAA UQ Equity", "005930 KP Equity", "BRK/B UN Equity", "RR/ LN Equity",
                   "VOLVB SS Equity", "NESN SE Equity", "ITX SQ Equity", "HDFCB IS Equity"],
        "yahoo_symbol": ["AAA", "005930.KS", "BRK-B", "RR.L", "VOLV-B.ST", "NESN.SW", "ITX.MC", "HDFCBANK.NS"],
    })
    if not with_symbols:
        rows = rows.drop(columns=["yahoo_symbol"])
    rows.to_csv(path / "wls_members.csv", index=False)


def _univ() -> pd.DataFrame:
    syms = ["AAA", "005930.KS", "BRK-B", "RR.L", "VOLV-B.ST", "NESN.SW", "ITX.MC", "HDFCBANK.NS", "ZZZZ"]
    return pd.DataFrame({"symbol": syms, "bbg_ticker": [cc.bloomberg_ticker(s) for s in syms]})


def test_exchange_codes_and_share_classes_match_the_composite_keys(tmp_path):
    _export(tmp_path, with_symbols=False)
    m = dict(zip(*cc.apply_wls(_univ(), tmp_path)[["symbol", "membership"]].T.values))
    for s in ["AAA", "005930.KS", "BRK-B", "RR.L", "VOLV-B.ST", "NESN.SW", "ITX.MC"]:
        assert m[s] == "CONFIRMED_WLS", s
    # India: Bloomberg's ticker (HDFCB) is not the NSE symbol, so only the symbol column can match it
    assert m["HDFCBANK.NS"] == "NOT_IN_WLS_EXPORT"
    assert m["ZZZZ"] == "NOT_IN_WLS_EXPORT"


def test_the_converted_symbol_column_confirms_india(tmp_path):
    _export(tmp_path, with_symbols=True)
    out = cc.apply_wls(_univ(), tmp_path)
    m = dict(zip(out.symbol, out.membership))
    assert m["HDFCBANK.NS"] == "CONFIRMED_WLS" and m["ZZZZ"] == "NOT_IN_WLS_EXPORT"
    assert "yahoo_symbol" in cc.load_wls_export(tmp_path).columns
