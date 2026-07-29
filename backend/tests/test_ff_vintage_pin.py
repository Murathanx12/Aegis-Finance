"""
Pinned Fama-French vintage tests (offline)
==========================================

The product's factor attribution is anchored to a committed daily vintage
(backend/data/ff_daily_pinned.csv.gz + sha256 sidecar). These tests exercise
the hash gate, the pinned-only fallback (live fetch dead), the disclosed
live-append, and the refuse-on-tamper path — all against the real committed
file, no network.

Run with:
    python -m pytest backend/tests/test_ff_vintage_pin.py -v
"""

import gzip
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import factor_model as fm


@pytest.fixture(autouse=True)
def _fresh_factor_cache():
    fm._FACTOR_CACHE.clear()
    fm._FACTOR_CACHE_TS.clear()
    yield
    fm._FACTOR_CACHE.clear()
    fm._FACTOR_CACHE_TS.clear()


# ── The committed pin itself ──────────────────────────────────────


def test_pinned_file_is_committed_and_passes_hash_gate():
    # The crash-model .pkl was gitignored and silently absent in prod; the pin
    # must never repeat that shape.
    assert fm._PINNED_CSV.exists(), "pinned vintage missing from the repo"
    assert fm._PINNED_VINTAGE.exists(), "vintage sidecar missing from the repo"

    df, meta = fm._load_pinned()
    assert meta["status"] == "ok"
    assert df is not None
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF", "Mom"]
    assert df.index.is_monotonic_increasing


def test_pinned_span_and_units():
    df, _ = fm._load_pinned()
    ff5 = df[fm._FF5_COLS].dropna()
    mom = df[["Mom"]].dropna()
    # FF5 daily starts 1963-07; momentum daily starts 1926-11
    assert ff5.index[0].year == 1963
    assert mom.index[0].year == 1926
    # decimal daily returns, not percent
    assert ff5["Mkt-RF"].abs().max() < 0.25
    assert mom["Mom"].abs().max() < 0.25
    # RF is non-negative and small
    assert (ff5["RF"] >= 0).all()
    assert ff5["RF"].max() < 0.001


def test_sidecar_records_what_the_loader_serves():
    recorded = json.loads(fm._PINNED_VINTAGE.read_text(encoding="utf-8"))
    df, meta = fm._load_pinned()
    assert meta["sha256"] == recorded["sha256"]
    ff5 = df[fm._FF5_COLS].dropna()
    assert str(ff5.index[-1].date()) == recorded["ff5_end"]
    assert str(df[["Mom"]].dropna().index[-1].date()) == recorded["mom_end"]


# ── Hash gate: tamper -> refuse ───────────────────────────────────


def test_tampered_pin_is_refused(tmp_path, monkeypatch):
    tampered = tmp_path / "ff_daily_pinned.csv.gz"
    tampered.write_bytes(gzip.compress(b"Date,Mkt-RF\n20200101,0.010000\n"))
    sidecar = tmp_path / "ff_daily_pinned_VINTAGE.json"
    sidecar.write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")

    monkeypatch.setattr(fm, "_PINNED_CSV", tampered)
    monkeypatch.setattr(fm, "_PINNED_VINTAGE", sidecar)

    df, meta = fm._load_pinned()
    assert df is None
    assert meta["status"] == "hash_mismatch"


def test_absent_pin_is_disclosed(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, "_PINNED_CSV", tmp_path / "nope.csv.gz")
    monkeypatch.setattr(fm, "_PINNED_VINTAGE", tmp_path / "nope.json")
    df, meta = fm._load_pinned()
    assert df is None
    assert meta["status"] == "absent"


# ── Serving paths ─────────────────────────────────────────────────


def test_pinned_only_when_live_fetch_dead(monkeypatch):
    monkeypatch.setattr(fm, "_fetch_ff5_live", lambda: None)
    df = fm.get_factor_data()
    assert df is not None
    assert list(df.columns) == fm._FF5_COLS
    prov = fm.factor_provenance()["ff5"]
    assert prov["mode"] == "pinned_only"
    assert prov["extended_through"] == prov["pinned_through"]


def test_live_append_extends_but_never_rewrites_pinned_span(monkeypatch):
    pinned_df, _ = fm._load_pinned()
    base = pinned_df[fm._FF5_COLS].dropna()
    pin_end = base.index[-1]
    known_val = float(base["Mkt-RF"].iloc[-1])

    # Fake live vintage: rewrites history (different value at pin_end) AND
    # extends past it — only the extension may be served.
    tail_dates = pd.bdate_range(start=pin_end, periods=6)  # includes pin_end
    fake_live = pd.DataFrame(
        {c: 0.005 for c in fm._FF5_COLS}, index=tail_dates
    )
    monkeypatch.setattr(fm, "_fetch_ff5_live", lambda: fake_live)

    df = fm.get_factor_data()
    prov = fm.factor_provenance()["ff5"]
    assert prov["mode"] == "pinned+live_append"
    # pinned span untouched by the fake vintage's rewrite
    assert float(df.loc[pin_end, "Mkt-RF"]) == pytest.approx(known_val)
    # tail rows after pin_end appended
    assert df.index[-1] == tail_dates[-1]
    assert float(df.iloc[-1]["Mkt-RF"]) == pytest.approx(0.005)


def test_momentum_pinned_only(monkeypatch):
    monkeypatch.setattr(fm, "_fetch_mom_live", lambda: None)
    df = fm.get_momentum_factor()
    assert df is not None
    assert list(df.columns) == ["Mom"]
    assert fm.factor_provenance()["mom"]["mode"] == "pinned_only"


def test_unavailable_only_when_pin_refused_and_live_dead(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, "_PINNED_CSV", tmp_path / "nope.csv.gz")
    monkeypatch.setattr(fm, "_PINNED_VINTAGE", tmp_path / "nope.json")
    monkeypatch.setattr(fm, "_fetch_ff5_live", lambda: None)
    assert fm.get_factor_data() is None
    assert fm.factor_provenance()["ff5"]["mode"] == "unavailable"


def test_lookback_slicing_still_works(monkeypatch):
    monkeypatch.setattr(fm, "_fetch_ff5_live", lambda: None)
    df = fm.get_factor_data(lookback_days=100)
    assert len(df) == 100
