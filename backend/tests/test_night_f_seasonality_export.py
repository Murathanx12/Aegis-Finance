"""T1 — Book F's frozen engine export, on a synthetic panel.

The file this job writes is an ORDER-PATH INPUT in another repository: the
execution loop hash-verifies it and then buys what it says. So the things
pinned here are the ways it could ship a plausible file that is wrong:

  1. the RANKING is the registered selector's, not a re-implementation. The
     job calls `book_signals.seasonality_score` twice (once at `tercile=0.0`
     for the whole cross-section, once at the registered 2/3 for the cut) and
     never computes a quantile of its own;
  2. a name that cannot fill BOTH year windows in full is ABSENT, not imputed
     at zero — a partial average is a different characteristic, and the age of
     a listing is what a twenty-year lag selects on;
  3. a thin cross-section is a REFUSAL, not an empty book. An engine file with
     no rows and a missing universe look identical to a consumer;
  4. `content_sha256` is byte-identical to `scripts.prediction_book._sha` in
     the execution repo, because that hash is the only guarantee the consumer
     has, and it changes when any row changes;
  5. the ticker→permno map takes the LAST-KNOWN name row, so a live symbol
     cannot be mapped onto the 1994 company that used to carry it.

Nothing here reads WRDS, CRSP or the venue. Every month is derived from a
`today` passed in — a literal month in a fixture is correct until it passes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pandas as pd
import pytest

from scripts import night_f_seasonality_export as FX


# --------------------------------------------------------------------------
# fixtures: a monthly panel with a PLANTED same-calendar-month effect


def _panel(permnos, *, month: int, first_year: int, last_year: int,
           effect: dict | None = None, holes: dict | None = None):
    """One row per (permno, ym) for every month of `first_year..last_year`.

    Every name earns a flat 1% outside `month`; inside `month` it earns
    1% + its own planted effect, so the seasonality composite ORDERS the names
    by the planted value and by nothing else.
    """
    effect = effect or {}
    holes = holes or {}
    rows = []
    for pn in permnos:
        for y in range(first_year, last_year + 1):
            for m in range(1, 13):
                if m == month and y in holes.get(pn, ()):
                    continue
                r = 0.01 + (effect.get(pn, 0.0) if m == month else 0.0)
                rows.append({"permno": pn, "ym": pd.Period(f"{y}-{m:02d}", freq="M"),
                             "ret_m": r, "price": 50.0, "dv": 5e7, "turnover_m": 0.1})
    return pd.DataFrame(rows)


def _universe(symbols, **over):
    members = []
    for i, s in enumerate(symbols):
        members.append({"symbol": s, "name": s, "exchange": "NASDAQ",
                        "price": 50.0, "median_dollar_volume": 5e7,
                        "sessions": 60, "etf_like": False, **over.get(s, {})})
    return {"name": "HIGH_DISPERSION_US_v1", "asof": "2026-09-01",
            "n": len(members), "screen": {"min_price": 2.0}, "members": members}


def _write_universe(tmp_path, payload) -> str:
    p = tmp_path / "HIGH_DISPERSION_US_v1_2026-09-01.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


# --------------------------------------------------------------------------
# the calendar arithmetic


def test_lag_years_spans_eleven_to_twenty_years_back():
    assert FX.lag_years("2026-10") == (2006, 2015)
    assert FX.lag_years("2031-01") == (2011, 2020)


def test_default_months_are_derived_from_today_never_written_down():
    assert FX.default_months(date(2026, 9, 13)) == ["2026-09", "2026-10"]
    # the December roll is the case a literal always gets wrong
    assert FX.default_months(date(2026, 12, 2)) == ["2026-12", "2027-01"]


def test_default_months_honours_the_env_override(monkeypatch):
    monkeypatch.setenv("F_EXPORT_MONTHS", "2027-03, 2027-04")
    assert FX.default_months(date(2026, 9, 13)) == ["2027-03", "2027-04"]


# --------------------------------------------------------------------------
# the two columns


def test_a_name_missing_one_lag_year_carries_no_column_at_all():
    pns = [1, 2, 3]
    panel = _panel(pns, month=10, first_year=2006, last_year=2015,
                   effect={1: 0.05, 2: 0.02, 3: 0.0}, holes={2: (2009,)})
    frame, counts = FX.seasonality_frame(panel, "2026-10")
    assert set(frame["permno"]) == {1, 3}, "permno 2 is short one year and must be absent"
    assert set(frame.columns) >= {"permno", "seas_11_15an", "seas_16_20an"}
    # 2009 is SEVENTEEN years back from 2026, so the hole lands in the 16-20
    # window only -- and a name that carries one window and not the other is
    # still absent, because both are required.
    assert counts["seas_11_15an"] == 3
    assert counts["seas_16_20an"] == 2
    # the planted effect IS the column, less the flat 1% every month earns
    got = frame.set_index("permno")["seas_11_15an"].to_dict()
    assert got[1] == pytest.approx(0.06)
    assert got[3] == pytest.approx(0.01)


def test_the_two_windows_read_different_years():
    # 11-15y back from 2026-10 is 2011-10..2015-10; 16-20y is 2006-10..2010-10.
    panel = _panel([1, 2], month=10, first_year=2006, last_year=2015,
                   effect={1: 0.05, 2: 0.0})
    late = panel[(panel["ym"].dt.year >= 2011) & (panel["ym"].dt.month == 10)]
    early = panel[(panel["ym"].dt.year <= 2010) & (panel["ym"].dt.month == 10)]
    assert len(late) == 10 and len(early) == 10
    frame, _ = FX.seasonality_frame(panel, "2026-10")
    row = frame.set_index("permno").loc[1]
    assert row["seas_11_15an"] == pytest.approx(row["seas_16_20an"])


# --------------------------------------------------------------------------
# the universe screen


def test_the_floor_the_price_and_the_etf_flag_all_bind(tmp_path):
    payload = _universe(
        ["AAA", "BBB", "CCC", "DDD"],
        BBB={"median_dollar_volume": 5e6},      # below the $10M floor
        CCC={"price": 3.0},                     # below the $5 minimum
        DDD={"etf_like": True})
    u = FX.load_universe(_write_universe(tmp_path, payload))
    assert sorted(u["symbols"]) == ["AAA"]
    assert u["dropped"] == {"etf_like": 1, "below_floor": 1, "below_price": 1}
    assert u["n_members"] == 4 and u["n_kept"] == 1


def test_an_empty_band_refuses_rather_than_returning_nothing(tmp_path):
    payload = _universe(["AAA"], AAA={"median_dollar_volume": 1.0})
    with pytest.raises(FX.ExportRefused, match="none survived the floor"):
        FX.load_universe(_write_universe(tmp_path, payload))


def test_a_missing_universe_file_is_a_refusal_not_a_default(tmp_path):
    with pytest.raises(FX.ExportRefused):
        FX.load_universe(tmp_path / "nope.json")


# --------------------------------------------------------------------------
# the ticker map


def _names_parquet(tmp_path, rows) -> str:
    p = tmp_path / "crsp__dsenames.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def test_the_last_known_name_row_wins_the_ticker(tmp_path):
    rows = [
        {"permno": 111, "ticker": "ZZZ", "nameendt": "1994-06-30", "shrcd": 11},
        {"permno": 222, "ticker": "ZZZ", "nameendt": "2024-12-31", "shrcd": 11},
        {"permno": 333, "ticker": "TRU", "nameendt": "2024-12-31", "shrcd": 73},
    ]
    m = FX.ticker_to_permno(path=_names_parquet(tmp_path, rows))
    assert m == {"ZZZ": 222}, "the recent common stock wins; the ETF share code is out"


def test_a_missing_name_table_refuses(tmp_path):
    with pytest.raises(FX.ExportRefused, match="does not guess the join"):
        FX.ticker_to_permno(path=tmp_path / "absent.parquet")


# --------------------------------------------------------------------------
# the payload


def _built(tmp_path, n=30, k=FX.K):
    syms = [f"S{i:03d}" for i in range(n)]
    pns = list(range(1, n + 1))
    tickers = dict(zip(syms, pns))
    # a monotone planted effect: S000 best, S029 worst
    effect = {pn: 0.05 - 0.001 * (pn - 1) for pn in pns}
    panel = _panel(pns, month=10, first_year=2006, last_year=2015, effect=effect)
    universe = FX.load_universe(_write_universe(tmp_path, _universe(syms)))
    return FX.build_month(panel, universe, tickers, "2026-10",
                          panel_last_month="2015-12", k=k)


def test_the_ranking_follows_the_planted_effect(tmp_path):
    p = _built(tmp_path)
    ranks = [r["symbol"] for r in p["rows"]]
    assert ranks[0] == "S000" and ranks[-1] == "S029"
    assert [r["rank"] for r in p["rows"]] == list(range(1, 31))


def test_the_cut_is_the_registered_tercile_and_selected_is_its_prefix(tmp_path):
    p = _built(tmp_path, n=30, k=4)
    top = [r["symbol"] for r in p["rows"] if r["tercile"] == "top"]
    assert len(top) == 10, "a 2/3 quantile over 30 evenly spaced scores keeps 10"
    assert p["selected"] == top[:4]
    assert p["construction"]["k"] == 4
    assert p["construction"]["tercile"] == pytest.approx(2.0 / 3.0)


def test_the_construction_and_its_deviations_are_printed(tmp_path):
    p = _built(tmp_path)
    c = p["construction"]
    assert c["both_columns_required"] is True
    assert c["floor_usd"] == 10_000_000.0
    assert c["required_years_per_window"] == 5
    assert c["selector"] == "backend.services.book_signals.seasonality_score"
    # Book C's lesson: the receipt has to say where it departs from the replay.
    assert len(c["deviations_from_the_replay"]) == 3
    assert any("k=10" in d for d in c["deviations_from_the_replay"])
    assert p["panel_last_month"] == "2015-12"
    assert p["registration"].startswith("TRIAL-DRAFT-F")
    assert p["licence"] == "PRODUCT_EXPERIMENT"


def test_coverage_is_reported_against_the_band_not_against_the_survivors(tmp_path):
    syms = [f"S{i:03d}" for i in range(40)]
    pns = list(range(1, 41))
    tickers = dict(zip(syms[:35], pns[:35]))            # five symbols unmapped
    effect = {pn: 0.05 - 0.001 * pn for pn in pns}
    # the last five mapped names are one year short and drop out
    panel = _panel(pns[:35], month=10, first_year=2006, last_year=2015,
                   effect=effect, holes={pn: (2008,) for pn in pns[30:35]})
    universe = FX.load_universe(_write_universe(tmp_path, _universe(syms)))
    p = FX.build_month(panel, universe, tickers, "2026-10", panel_last_month="2015-12")
    cov = p["coverage"]
    assert cov["universe_after_floor"] == 40
    assert cov["mapped_to_permno"] == 35
    assert cov["unmapped_count"] == 5
    assert cov["carrying_both_windows"] == 30
    assert cov["mapped_share_of_universe"] == pytest.approx(35 / 40)
    assert cov["carrying_both_windows_share_of_mapped"] == pytest.approx(30 / 35, abs=1e-4)


def test_a_thin_cross_section_refuses_rather_than_shipping_a_short_book(tmp_path):
    syms = [f"S{i:03d}" for i in range(19)]
    pns = list(range(1, 20))
    panel = _panel(pns, month=10, first_year=2006, last_year=2015,
                   effect={pn: 0.001 * pn for pn in pns})
    universe = FX.load_universe(_write_universe(tmp_path, _universe(syms)))
    with pytest.raises(FX.ExportRefused, match="REFUSAL, not an empty book"):
        FX.build_month(panel, universe, dict(zip(syms, pns)), "2026-10",
                       panel_last_month="2015-12")


# --------------------------------------------------------------------------
# the hash the consumer checks


def test_the_hash_is_the_execution_repos_own_formula(tmp_path):
    p = _built(tmp_path)
    body = dict(p)
    claimed = body.pop("content_sha256")
    # scripts/prediction_book._sha, aegis-alpha-terminal, written out in full
    # rather than imported: the two repositories share no code, and this line is
    # what stops the two copies from drifting in silence.
    expected = hashlib.sha256(json.dumps(
        body, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    assert claimed == expected


def test_editing_one_row_breaks_the_hash(tmp_path):
    p = _built(tmp_path)
    assert FX.content_sha256(p) == p["content_sha256"]
    p["rows"][0]["symbol"] = "EVIL"
    assert FX.content_sha256(p) != p["content_sha256"]
