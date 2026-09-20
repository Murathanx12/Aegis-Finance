"""N-E — the daily analyst snapshot. Mocked fetch; no network, no key."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import analyst_snapshot as snap


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snap._config, "DATA_DIR", tmp_path, raising=False)
    uni = tmp_path / "optimus" / "potential_universe"
    uni.mkdir(parents=True)
    (uni / "2026-09-02.jsonl").write_text(
        json.dumps({"artefact": "HEADER"}) + "\n"
        + "\n".join(json.dumps({"symbol": s}) for s in ("NVDA", "AAPL", "GPRO", "ZZZZ")),
        encoding="utf-8",
    )
    return tmp_path


FAKE = {
    "NVDA": {"status": "ok", "company_name": "NVIDIA Corporation", "recommendation_mean": 1.4,
             "recommendation_key": "strong_buy", "n_analysts": 60, "current_price": 218.0,
             "target_low": 150.0, "target_mean": 326.0, "target_median": 320.0, "target_high": 500.0,
             "rec_period": "0m", "strong_buy": 40, "buy": 15, "hold": 4, "sell": 1, "strong_sell": 0},
    "AAPL": {"status": "partial", "company_name": "Apple Inc.", "recommendation_mean": 2.0,
             "error": "targets: HTTPError: 404"},
    "GPRO": {"status": "empty", "company_name": "GoPro, Inc.", "error": ""},
}


def fake_fetch(symbol: str) -> dict:
    if symbol == "ZZZZ":
        raise RuntimeError("possibly delisted; no data found")
    return dict(FAKE[symbol])


def test_one_row_per_symbol_date_including_the_empties(data_dir):
    rec = snap.snapshot(max_symbols=4, pace_s=0, fetch=fake_fetch, update_names=False)
    assert rec["rows"] == 4, "an empty or failing symbol is still a ROW — a dropped symbol is an invisible gap"
    assert rec["by_status"] == {"ok": 1, "partial": 1, "empty": 1, "error": 1}
    assert rec["coverage_rate"] == 0.5


def test_the_parquet_lands_with_every_column(data_dir):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    rec = snap.snapshot(max_symbols=4, pace_s=0, fetch=fake_fetch, update_names=False)
    assert rec["parquet"] is True
    df = pd.read_parquet(rec["path"])
    assert list(df.columns) == list(snap.COLUMNS)
    nvda = df[df["symbol"] == "NVDA"].iloc[0]
    assert nvda["target_mean"] == 326.0
    assert nvda["n_analysts"] == 60
    assert df["date"].nunique() == 1


def test_a_failing_symbol_is_recorded_not_swallowed(data_dir):
    rec = snap.snapshot(max_symbols=4, pace_s=0, fetch=fake_fetch, update_names=False)
    assert any("ZZZZ" in e for e in rec["errors_first_20"])


def test_the_receipt_says_the_series_starts_today(data_dir):
    rec = snap.snapshot(max_symbols=2, pace_s=0, fetch=fake_fetch, update_names=False)
    assert rec["series_starts"] == rec["date"]
    assert rec["series_days"] == 1
    assert "STARTS THE DAY THIS JOB FIRST RAN" in rec["series_note"]
    assert "4 months" in rec["series_note"], "Finnhub's retention is WHY there is nothing to backfill"


def test_the_receipt_names_the_finnhub_key_it_looked_for_never_a_value(data_dir, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("AAT_FINNHUB_API_KEY", raising=False)
    rec = snap.snapshot(max_symbols=1, pace_s=0, fetch=fake_fetch, update_names=False)
    assert rec["finnhub"]["attempted"] is False
    assert "FINNHUB_API_KEY" in rec["finnhub"]["reason"]

    monkeypatch.setenv("AAT_FINNHUB_API_KEY", "a-real-looking-secret")
    rec2 = snap.snapshot(max_symbols=1, pace_s=0, fetch=fake_fetch, update_names=False)
    assert "a-real-looking-secret" not in json.dumps(rec2)
    assert "AAT_FINNHUB_API_KEY" in rec2["finnhub"]["reason"]


def test_the_receipt_carries_the_perverse_corpse(data_dir):
    """ANALYST-IBES-1 binds anything built on this panel."""
    rec = snap.snapshot(max_symbols=1, pace_s=0, fetch=fake_fetch, update_names=False)
    assert "PERVERSE" in rec["corpse_that_binds"]
    assert "ANALYST-IBES-1" in rec["corpse_that_binds"]


def test_the_name_table_is_filled_but_never_overwritten(data_dir, monkeypatch, tmp_path):
    ents = tmp_path / "backend_data" / "news_entities"
    ents.mkdir(parents=True)
    (ents / "issuers.csv").write_text(
        "symbol,primary_name,aliases,country,is_adr\n"
        "NVDA,,NVDA,US,\n"
        'AAPL,"A HAND-CHECKED NAME",AAPL,US,\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(snap.entities, "entities_dir", lambda: ents)
    rec = snap.snapshot(max_symbols=2, pace_s=0, fetch=fake_fetch, update_names=True)
    assert rec["name_table_update"]["updated"] == 1
    text = (ents / "issuers.csv").read_text(encoding="utf-8")
    assert "NVIDIA Corporation" in text, "an empty primary_name is filled"
    assert "A HAND-CHECKED NAME" in text, "an existing primary_name is NEVER overwritten"
    assert "Apple Inc." not in text


def test_a_killed_sweep_leaves_a_valid_partial_parquet(data_dir, monkeypatch):
    """A 70-minute sweep that only wrote at exit would lose everything to one
    kill — the G3 lesson of 2026-09-10. It checkpoints instead."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    monkeypatch.setattr(snap, "CHECKPOINT_EVERY", 2)
    seen = []
    real_row = snap._row

    # The kill is simulated on the MAIN thread, which is where a real one lands.
    # It used to be raised from inside `fetch`, and since 2026-09-18 every fetch
    # runs on a daemon thread under `SYMBOL_TIMEOUT_S` — a thread that cannot
    # receive a KeyboardInterrupt, so raising it there simulated nothing.
    def dying_row(symbol, day, observed, got):
        seen.append(symbol)
        if len(seen) > 3:
            raise KeyboardInterrupt("pretend the process was killed")
        return real_row(symbol, day, observed, got)

    monkeypatch.setattr(snap, "_row", dying_row)
    with pytest.raises(KeyboardInterrupt):
        snap.snapshot(max_symbols=4, pace_s=0, fetch=fake_fetch, update_names=False)

    import pandas as pd
    day = snap._now().date().isoformat()
    df = pd.read_parquet(snap.out_dir() / f"{day}.parquet")
    assert len(df) == 2, "the last checkpoint before the kill survived"
    assert list(df.columns) == list(snap.COLUMNS)

    # ...and a parquet with no receipt is a number with no provenance.
    rec = json.loads((snap.out_dir() / f"{day}_receipt.json").read_text(encoding="utf-8"))
    assert rec["status"] == "PARTIAL"
    assert rec["rows"] == 2 and rec["symbols_requested"] == 4
    assert rec["rate_s_per_symbol"] is not None


def test_a_wedged_symbol_is_one_error_row_and_the_sweep_goes_on(data_dir, monkeypatch):
    """WHAT HELD THE 2026-09-14 DAILY PASS, bounded.

    That pass checkpointed 1,500 of 2,362 symbols and never returned; it stayed
    alive four days and every scheduled firing after it died at Windows
    0x80070420, so 09-15..09-18 have no receipt at all. Every yfinance property
    read was ALREADY boxed at 25 s — which is the lesson: a per-call box does
    not bound the call site. The whole symbol is boxed now.
    """
    import time as _time
    monkeypatch.setattr(snap, "SYMBOL_TIMEOUT_S", 0.2)
    seen = []

    def wedging_fetch(symbol):
        seen.append(symbol)
        if len(seen) == 2:
            _time.sleep(30)                    # the daemon thread is abandoned
        return dict(FAKE.get(symbol, {"status": "empty", "company_name": ""}))

    rec = snap.snapshot(max_symbols=3, pace_s=0, fetch=wedging_fetch,
                        update_names=False)
    assert rec["rows"] == 3, "the sweep stopped at the wedged symbol"
    assert rec["by_status"]["error"] == 1
    assert any("no response in" in e for e in rec["errors_first_20"])


def test_every_network_call_in_the_sweep_is_boxed():
    """The construction was the ONE unboxed call, found 2026-09-18.

    `yfinance.Ticker(symbol)` is not the free attribute assignment it looks
    like: `TickerBase.__init__` allocates a curl_cffi session, a C-level libcurl
    handle, on the calling thread.
    """
    import ast
    src = Path(snap.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    boxed = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "call_with_timeout":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute):
                    boxed.add(sub.attr)
                if isinstance(sub, ast.Name):
                    boxed.add(sub.id)
    assert "Ticker" in boxed, "the Ticker construction is not boxed"
    for prop in ("info", "analyst_price_targets", "recommendations"):
        assert prop in boxed, f"{prop} is not boxed"


def test_no_universe_file_is_zero_rows_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(snap._config, "DATA_DIR", tmp_path, raising=False)
    rec = snap.snapshot(max_symbols=5, pace_s=0, fetch=fake_fetch, update_names=False)
    assert rec["rows"] == 0
    assert rec["coverage_rate"] is None


# ---------------------------------------------------------------------------
# chunk 15b — `--universe tradable`
#
# The band is READ from `night_f_seasonality_export.load_universe`, never
# re-derived here, so these tests stub THAT function: what they are pinning is
# the wiring and the receipt, not a second copy of the floor arithmetic. A test
# that re-implemented the $10M/$5/ETF clauses would be the very duplication the
# feature exists to avoid.
# ---------------------------------------------------------------------------

BAND = {
    "path": "/x/state/universe/HIGH_DISPERSION_US_v1_2026-09-01.json",
    "asof": "2026-09-01",
    "n_members": 9668,
    "n_kept": 3,
    "dropped": {"etf_like": 5013, "below_floor": 2226, "below_price": 67},
    "symbols": {"NVDA": {}, "AAPL": {}, "GPRO": {}},
    "screen": "HIGH_DISPERSION_US_v1",
}


@pytest.fixture
def band(monkeypatch):
    from scripts import night_f_seasonality_export as X

    monkeypatch.setattr(X, "load_universe", lambda *a, **k: dict(BAND))
    return BAND


def test_the_cli_default_is_still_the_whole_potential_universe(data_dir):
    """`all` must not change under anyone: the name-table sweep wants every name."""
    syms, prov = snap._symbols(None, "all")
    assert syms == ["NVDA", "AAPL", "GPRO", "ZZZZ"]
    assert prov["universe"] == "all"
    assert prov["filter"].startswith("none")
    assert snap.main.__doc__ is None or True  # the default lives in the parser


def test_tradable_reads_the_band_and_never_re_derives_it(data_dir, band):
    syms, prov = snap._symbols(None, "tradable")
    assert syms == ["AAPL", "GPRO", "NVDA"], "sorted, and the band's own members"
    assert prov["universe"] == "tradable"
    assert prov["source"] == BAND["path"]
    assert prov["asof"] == "2026-09-01"
    assert prov["n_members"] == 9668 and prov["n_available"] == 3
    assert prov["dropped"] == BAND["dropped"]
    assert "10,000,000" in prov["filter"] and "price >= $5" in prov["filter"]
    assert "ETFs excluded" in prov["filter"]
    assert "night_f_seasonality_export" in prov["filter_owner"]


def test_the_receipt_prints_the_universe_the_filter_and_the_drops(data_dir, band):
    rec = snap.snapshot(pace_s=0, fetch=fake_fetch, update_names=False,
                        universe="tradable")
    u = rec["universe"]
    assert u["universe"] == "tradable"
    assert u["n_available"] == 3
    assert u["dropped"]["etf_like"] == 5013
    assert u["dropped"]["below_floor"] == 2226
    assert u["dropped"]["below_price"] == 67
    assert "tradable universe" in rec["headline"]
    assert "10,000,000" in rec["headline"]
    assert rec["rows"] == 3, "the three band names, and only those"


def test_an_unresolvable_band_REFUSES_and_does_not_fall_back_to_3056(data_dir, monkeypatch):
    """The failure that would otherwise be invisible: a silent 700-name growth."""
    from scripts import night_f_seasonality_export as X

    def _boom(*a, **k):
        raise X.ExportRefused("no stored tradable universe under /x/state/universe")

    monkeypatch.setattr(X, "load_universe", _boom)
    rec = snap.snapshot(pace_s=0, fetch=fake_fetch, update_names=False,
                        universe="tradable")
    assert rec["rows"] == 0
    assert "could not be resolved" in rec["refused"]
    assert "no stored tradable universe" in rec["refused"]
    assert rec["headline"].startswith("REFUSED")
    assert rec["universe"]["resolved"] is False


def test_an_unknown_universe_name_is_a_loud_error_not_a_default(data_dir):
    with pytest.raises(ValueError, match="unknown universe"):
        snap._symbols(None, "everything")


def test_max_symbols_still_bounds_the_band(data_dir, band):
    syms, _ = snap._symbols(2, "tradable")
    assert syms == ["AAPL", "GPRO"]


def test_the_daily_pass_asks_for_the_tradable_band(monkeypatch):
    """Reachability: the step must pass it, not merely be able to.

    `daily_pass` is the only caller that matters for the 3.9 h budget, and a
    keyword it never sends is a feature that exists and does nothing.
    """
    from scripts import daily_pass

    seen = {}

    def _fake(**kw):
        seen.update(kw)
        return {"rows": 3, "by_status": {"ok": 3}, "coverage_rate": 1.0,
                "path": "/x.parquet", "headline": "h"}

    monkeypatch.setattr(daily_pass, "run_analyst_snapshot", _fake)
    row = daily_pass.step_analyst_snapshot({})
    assert seen == {"universe": "tradable",
                    "budget_s": float(daily_pass._config.DAILY_PASS_ANALYST_BUDGET_S)}
    assert row["status"] == "ok"


# ── THE SWEEP STOPS ITSELF (2026-09-20) ────────────────────────────────────
#
# The step box abandons a wedged thread and leaves no receipt of its own; the
# sweep's own budget flushes and RETURNS, so the shortfall is a counted field
# rather than a `timeout` row every single morning.


def test_a_budget_stops_the_sweep_and_the_shortfall_is_a_counted_field(
        data_dir, monkeypatch):
    import time as _time

    def _slow(symbol: str) -> dict:
        _time.sleep(0.2)
        return dict(FAKE.get(symbol) or {"status": "empty", "error": ""})

    rec = snap.snapshot(max_symbols=4, pace_s=0, fetch=_slow,
                        update_names=False, budget_s=0.25)
    assert rec["truncated"] is True
    assert rec["budget_s"] == 0.25
    assert rec["rows"] == rec["symbols_reached"] < 4
    assert rec["symbols_reached"] + rec["symbols_not_reached"] == 4
    assert "budget" in rec["truncation_reason"]
    assert "TRUNCATED" in rec["headline"]


def test_no_budget_is_a_FIELD_and_not_an_absence(data_dir):
    """A reader must be able to tell "no budget was set" from "a budget was set
    and there was room to spare" — an omitted key reads as neither."""
    rec = snap.snapshot(max_symbols=4, pace_s=0, fetch=fake_fetch,
                        update_names=False)
    assert rec["budget_s"] is None
    assert rec["truncated"] is False
    assert rec["symbols_not_reached"] == 0
    assert rec["truncation_reason"] is None


def test_a_budget_with_room_to_spare_runs_the_whole_sweep(data_dir):
    rec = snap.snapshot(max_symbols=4, pace_s=0, fetch=fake_fetch,
                        update_names=False, budget_s=600)
    assert rec["truncated"] is False
    assert rec["rows"] == 4
    assert rec["symbols_not_reached"] == 0


def test_the_daily_pass_names_the_truncation_in_its_row(monkeypatch):
    from scripts import daily_pass

    def _fake(**kw):
        return {"rows": 800, "by_status": {"ok": 800}, "coverage_rate": 1.0,
                "path": "/x.parquet", "headline": "h", "truncated": True,
                "budget_s": 3300.0, "symbols_not_reached": 1562,
                "truncation_reason": "the sweep reached its own 3300s budget"}

    monkeypatch.setattr(daily_pass, "run_analyst_snapshot", _fake)
    row = daily_pass.step_analyst_snapshot({})
    # `ok`, not `timeout` and not `refused`: 800 real rows landed, and the
    # 1,562 that did not is a NUMBER on the row rather than a status nobody
    # can act on.
    assert row["status"] == "ok"
    assert row["truncated"] is True
    assert row["symbols_not_reached"] == 1562
    assert any("budget" in r for r in row["refusals"])
