"""N-E — the daily analyst snapshot. Mocked fetch; no network, no key."""

from __future__ import annotations

import json

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

    def dying_fetch(symbol):
        seen.append(symbol)
        if len(seen) > 3:
            raise KeyboardInterrupt("pretend the process was killed")
        return dict(FAKE.get(symbol, {"status": "empty", "company_name": ""}))

    with pytest.raises(KeyboardInterrupt):
        snap.snapshot(max_symbols=4, pace_s=0, fetch=dying_fetch, update_names=False)

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


def test_no_universe_file_is_zero_rows_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(snap._config, "DATA_DIR", tmp_path, raising=False)
    rec = snap.snapshot(max_symbols=5, pace_s=0, fetch=fake_fetch, update_names=False)
    assert rec["rows"] == 0
    assert rec["coverage_rate"] is None
