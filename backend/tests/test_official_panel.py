"""The joinable daily panel over the official tables (2026-09-30).

Keyed by (ticker, public_date): insider net buying (distinct insiders, dollars,
officer flag, the 10b5-1 flag's source), House trades by disclosure date, FINRA
short interest level and change, and CFTC positioning extremes mapped onto the
digest's proxies. Offline; dates derived from today, never literal.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pandas as pd

from backend.services import official_sources as OS

TODAY = datetime.now(timezone.utc).date()
# a weekday at least a week back, so every "next business day" stays a weekday
D0 = next(TODAY - timedelta(days=k) for k in range(7, 14) if (TODAY - timedelta(days=k)).weekday() < 3)


def _et(d, hh, mm=0):
    return datetime.combine(d, time(hh, mm), tzinfo=OS.ET_TZ).astimezone(timezone.utc).isoformat()


def _ins(i, tk, code, value, *, owner, officer=True, role="officer", plan=False,
         basis="aff10b5One_filing_box", pub=None, deriv=False):
    return {"row_id": f"acc{i}:0", "ticker": tk, "code": code, "value_usd": value,
            "owner_cik": owner, "is_officer": officer, "role": role, "rule_10b5_1": plan,
            "rule_10b5_1_basis": basis, "public_utc": pub or _et(D0, 11), "is_derivative": deriv}


def test_insider_block_counts_distinct_insiders_and_keeps_10pct_and_plans_apart():
    rows = [_ins(1, "ACME", "P", 100_000, owner="A"),
            _ins(2, "ACME", "P", 50_000, owner="A"),                      # same insider twice
            _ins(3, "ACME", "P", 25_000, owner="B", officer=False, role="director"),
            _ins(4, "ACME", "S", 40_000, owner="C", plan=True),           # planned sale
            _ins(5, "ACME", "P", 9_000_000, owner="F", officer=False, role="10pct"),
            _ins(6, "ACME", "M", 1_000_000, owner="A"),                   # option exercise: ignored
            _ins(7, "ACME", "P", 5_000, owner="D", deriv=True),           # derivative: ignored
            _ins(8, "ACME", "S", 10_000, owner="E", plan=None, basis="unknown",
                 pub=_et(D0, 17))]                                         # after the close
    c = OS.panel_insiders(rows)[("ACME", D0)]
    assert (c["ins_n_insiders_buy"], c["ins_n_insiders_sell"]) == (2, 2)
    assert c["ins_buy_usd"] == 175_000 and c["ins_sell_usd"] == 50_000
    assert c["ins_net_usd"] == 125_000
    assert c["ins_net_usd_ex_plan"] == 165_000                 # the planned sale is left out
    assert c["ins_ten_pct_net_usd"] == 9_000_000
    assert c["ins_officer_buy"] is True and c["ins_officer_sell"] is True
    assert (c["ins_n_plan_lines"], c["ins_n_plan_unknown"]) == (1, 1)
    assert c["ins_10b5_1_basis"] == "aff10b5One_filing_box|unknown"
    assert c["tradable_date"] == OS.next_business_day(D0)      # one line came after 16:00 ET


def test_the_public_date_is_new_york_not_utc():
    late = _et(D0, 21)                                           # 01:00 UTC the next day
    c = OS.panel_insiders([_ins(1, "ACME", "P", 1, owner="A", pub=late)])
    assert list(c) == [("ACME", D0)]


def test_politician_block_is_keyed_by_disclosure_and_uses_range_midpoints():
    pub = _et(D0, 23, 59)
    rows = [{"ticker": "MSFT", "tx_type": "P", "member": "Rep A", "amount_lo": 1001,
             "amount_hi": 15000, "lag_days": 20, "public_utc": pub,
             "tradable_from_utc": _et(OS.next_business_day(D0), 9, 30)},
            {"ticker": "MSFT", "tx_type": "S (partial)", "member": "Rep B", "amount_lo": 15001,
             "amount_hi": 50000, "lag_days": 40, "public_utc": pub},
            {"ticker": "MSFT", "tx_type": "E", "member": "Rep C", "public_utc": pub}]
    c = OS.panel_politicians(rows)[("MSFT", D0)]
    assert (c["pol_n_members_buy"], c["pol_n_members_sell"], c["pol_n_trades"]) == (1, 1, 2)
    assert c["pol_buy_mid_usd"] == 8000.5 and c["pol_sell_mid_usd"] == 32500.5
    assert c["pol_median_lag_days"] == 30
    assert c["tradable_date"] == OS.next_business_day(D0)


def test_short_interest_block_keeps_the_latest_settlement_per_public_date():
    pub = _et(D0, 19)
    rows = [{"symbol": "XYZ", "settlement_date": str(D0 - timedelta(days=30)), "short_qty": 1,
             "public_utc": pub},
            {"symbol": "XYZ", "settlement_date": str(D0 - timedelta(days=15)), "short_qty": 200,
             "prev_short_qty": 100, "change_pct": 100.0, "days_to_cover": 4.5, "public_utc": pub}]
    c = OS.panel_short_interest(rows)[("XYZ", D0)]
    assert c["si_short_qty"] == 200 and c["si_change_pct"] == 100.0 and c["si_days_to_cover"] == 4.5


def test_cot_extremes_map_to_the_digest_proxies_in_the_proxy_direction():
    pub = _et(D0, 15, 30)
    rows = [{"code": "099741", "market": "EURO FX", "headline_pctile_3y": 0.98,
             "headline_net_pct_oi": 20.0, "headline_chg_z": 1.0, "public_utc": pub},
            {"code": "088691", "market": "GOLD", "headline_pctile_3y": 0.5, "public_utc": pub},
            {"code": "999999", "market": "UNMAPPED", "headline_pctile_3y": 0.99, "public_utc": pub}]
    out = OS.panel_positioning(rows)
    uup = out[("UUP", D0)]                  # euro crowded long = the DOLLAR crowded short
    assert uup["cot_subject"] == "macro:dollar" and uup["cot_extreme"] == "proxy_crowded_short"
    assert uup["cot_pctile_3y"] == 0.02 and uup["cot_net_pct_oi"] == -20.0
    assert out[("GLD", D0)]["cot_extreme"] == ""
    assert not [k for k in out if k[0] not in ("UUP", "GLD")]
    assert OS.cot_proxy("13874A")[0] == "SPY" and OS.cot_proxy("13874A")[3] == "code_map"


def test_build_daily_panel_writes_one_parquet_with_the_declared_schema(tmp_path):
    OS.append_rows("insider_tx", [_ins(1, "ACME", "P", 100_000, owner="A")], tmp_path)
    OS.append_rows("short_interest", [{"row_id": "si:ACME:x", "symbol": "ACME",
                                       "settlement_date": str(D0 - timedelta(days=10)),
                                       "short_qty": 5, "public_utc": _et(D0, 19)}], tmp_path)
    rec = OS.build_daily_panel(tmp_path)
    df = pd.read_parquet(rec["path"])
    assert list(df.columns) == list(OS.PANEL_SCHEMA)
    assert len(df) == 1 and df.loc[0, "ticker"] == "ACME"
    assert df.loc[0, "ins_buy_usd"] == 100_000 and df.loc[0, "si_short_qty"] == 5
    assert pd.Timestamp(D0) == df.loc[0, "public_date"]
    assert rec["rows_by_block"] == {"insiders": 1, "politicians": 0, "short_interest": 1,
                                    "positioning": 0}
    assert OS.panel_age_s(tmp_path) is not None and OS.panel_age_s(tmp_path) < 60
