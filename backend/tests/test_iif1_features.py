"""INTERNET-INVESTIGATOR-FWD-1 — the point-in-time feature layer.

Offline: every fetch is monkeypatched. The network guard would block a real one
anyway, but these tests are about *semantics*, and the semantics that matter are
all about what happens when data is missing rather than when it is present.

THE ONE PROPERTY WORTH MOST OF THIS FILE
========================================
An unmeasured security is not a calm security. Every path here either produces
`OK_DATA`, or says `OK_EMPTY` (there is genuinely nothing), or says
`UNAVAILABLE` (we could not find out) — and the last two must never collapse
into each other, because "no filing in two days" and "SEC lookup failed" score
identically the moment they do.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.services import iif1_features as F
from backend.services import investigator_triggers as TR


def _hist(n=400, seed=0, start="2025-01-02", vol_mult=1.0, last_jump=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    r = rng.normal(0.0004, 0.012, n)
    if last_jump:
        r[-1] = last_jump
    close = 100 * np.exp(np.cumsum(r))
    vol = rng.integers(1_000_000, 2_000_000, n).astype(float) * vol_mult
    return pd.DataFrame({"Close": close, "Volume": vol}, index=idx)


# ── decision time is New York time ──────────────────────────────────────────

def test_a_naive_timestamp_is_read_as_new_york_not_utc():
    """Guessing UTC for a string a human typed while thinking about the US
    close shifts every boundary by five hours, in the direction that leaks."""
    ts = F.resolve_decision_ts("2026-08-14 16:05")
    assert ts.hour == 16 and "New_York" in str(ts.tzinfo)


def test_an_aware_timestamp_is_converted_rather_than_relabelled():
    from datetime import timezone
    ts = F.resolve_decision_ts(datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc))
    assert ts.utcoffset() != timedelta(0)
    assert ts.hour in (15, 16)          # 20:00Z is 16:00 EDT / 15:00 EST


# ── the tri-state, which is the point ───────────────────────────────────────

def test_an_unavailable_history_marks_every_price_feature_unavailable(monkeypatch):
    monkeypatch.setattr(F, "_history_upto", lambda t, ts: None)
    vals = F.assemble_ticker("XYZ", F.resolve_decision_ts("2026-08-14 21:00"))
    for name in ("price", "dollar_volume_20d", "volume_z_20d",
                 "abs_resid_return_z_1d"):
        assert vals[name].status == F.UNAVAILABLE
        assert vals[name].value is None
        assert vals[name].note


def test_a_failed_fetch_is_unavailable_not_a_quiet_zero(monkeypatch):
    def boom(t, ts):
        raise RuntimeError("throttled")
    monkeypatch.setattr(F, "_history_upto", boom)
    vals = F.assemble_ticker("XYZ", F.resolve_decision_ts("2026-08-14 21:00"))
    assert vals["price"].status == F.UNAVAILABLE
    assert "throttled" in vals["price"].note


def test_no_filing_is_OK_EMPTY_while_a_broken_lookup_is_UNAVAILABLE(monkeypatch):
    """The distinction the whole file exists for. A throttled EDGAR and a
    genuinely quiet fortnight must not arrive as the same value."""
    from backend.services import edgar_events as EE
    ts = F.resolve_decision_ts("2026-08-14 21:00")

    monkeypatch.setattr(EE, "lookup_cik", lambda t: 320193)
    monkeypatch.setattr(EE, "_fetch_submissions",
                        lambda cik: {"filings": {"recent": {"form": []}}})
    empty = F._filing_within("AAPL", ts, "now")
    assert empty.status == F.OK_EMPTY and empty.value is False

    monkeypatch.setattr(EE, "_fetch_submissions", lambda cik: None)
    broken = F._filing_within("AAPL", ts, "now")
    assert broken.status == F.UNAVAILABLE and broken.value is None

    def boom(cik):
        raise RuntimeError("SEC 403")
    monkeypatch.setattr(EE, "_fetch_submissions", boom)
    threw = F._filing_within("AAPL", ts, "now")
    assert threw.status == F.UNAVAILABLE and "RuntimeError" in threw.note


def test_unavailable_features_are_omitted_so_the_scorer_discloses_them(monkeypatch):
    """`score_candidate` already treats an absent component as missing and says
    so in its reason. Passing None or 0.0 instead would rank an unmeasured
    security as an ordinary one, forever, invisibly."""
    monkeypatch.setattr(F, "_history_upto", lambda t, ts: None)
    monkeypatch.setattr(F, "_earnings_within",
                        lambda t, ts, f: F.FeatureValue(True, F.OK_DATA, "s",
                                                        "o", f))
    monkeypatch.setattr(F, "_filing_within",
                        lambda t, ts, f: F.FeatureValue(False, F.OK_EMPTY, "s",
                                                        "o", f))
    snap = F.assemble("2026-08-14 21:00", universe=["XYZ"])
    feats = snap["features"]["XYZ"]
    assert "price" not in feats and "abs_resid_return_z_1d" not in feats
    assert feats["earnings_within_5d"] is True
    assert feats["filing_within_2d"] is False       # OK_EMPTY IS a measurement
    assert "price" in snap["unavailable"]["XYZ"]

    # The scorer never sees a fabricated number for anything it could not
    # measure. Here that also means the liquidity floor is unverifiable, so the
    # name is excluded rather than admitted on the strength of two booleans.
    c = TR.score_candidate("XYZ", feats)
    assert "abs_resid_return_z_1d" not in c.components
    assert not c.eligible
    assert "liquidity unverifiable" in c.reason


# ── the filing clock is acceptance, not date ────────────────────────────────

def test_a_filing_accepted_after_the_decision_time_is_not_yet_public(monkeypatch):
    """A filing accepted at 18:05 was available to nobody during that session.
    Counting it as same-day information hands the model up to a day of future.
    """
    from backend.services import edgar_events as EE
    monkeypatch.setattr(EE, "lookup_cik", lambda t: 1)
    monkeypatch.setattr(EE, "_fetch_submissions", lambda cik: {"filings": {
        "recent": {"form": ["8-K"],
                   "acceptanceDateTime": ["2026-08-14T18:05:00-04:00"],
                   "filingDate": ["2026-08-14"]}}})
    out = F._filing_within("X", F.resolve_decision_ts("2026-08-14 16:00"), "n")
    assert out.status == F.OK_EMPTY and out.value is False


def test_a_filing_accepted_before_the_decision_time_counts(monkeypatch):
    from backend.services import edgar_events as EE
    monkeypatch.setattr(EE, "lookup_cik", lambda t: 1)
    monkeypatch.setattr(EE, "_fetch_submissions", lambda cik: {"filings": {
        "recent": {"form": ["8-K"],
                   "acceptanceDateTime": ["2026-08-14T09:05:00-04:00"],
                   "filingDate": ["2026-08-14"]}}})
    out = F._filing_within("X", F.resolve_decision_ts("2026-08-14 16:00"), "n")
    assert out.status == F.OK_DATA and out.value is True


def test_an_old_filing_is_measured_as_false_not_missing(monkeypatch):
    from backend.services import edgar_events as EE
    monkeypatch.setattr(EE, "lookup_cik", lambda t: 1)
    monkeypatch.setattr(EE, "_fetch_submissions", lambda cik: {"filings": {
        "recent": {"form": ["10-Q"],
                   "acceptanceDateTime": ["2026-07-01T09:05:00-04:00"],
                   "filingDate": ["2026-07-01"]}}})
    out = F._filing_within("X", F.resolve_decision_ts("2026-08-14 16:00"), "n")
    assert out.status == F.OK_DATA and out.value is False


def test_a_missing_acceptance_time_falls_back_and_says_so(monkeypatch):
    """Assuming a time the source did not give us would be inventing
    precision, so the fallback is end-of-day and it is named in the note."""
    from backend.services import edgar_events as EE
    monkeypatch.setattr(EE, "lookup_cik", lambda t: 1)
    monkeypatch.setattr(EE, "_fetch_submissions", lambda cik: {"filings": {
        "recent": {"form": ["8-K"], "acceptanceDateTime": [""],
                   "filingDate": ["2026-08-13"]}}})
    out = F._filing_within("X", F.resolve_decision_ts("2026-08-14 16:00"), "n")
    assert out.status == F.OK_DATA
    assert "acceptance missing" in out.note


# ── history never reaches past the decision time ────────────────────────────

def test_history_is_truncated_at_the_decision_timestamp(monkeypatch):
    from backend.services import data_fetcher
    monkeypatch.setattr(data_fetcher, "fetch_ticker_history",
                        lambda t, period="1y": _hist(n=300, start="2026-01-01"))
    ts = F.resolve_decision_ts("2026-06-01 16:00")
    h = F._history_upto("X", ts)
    assert h is not None and not h.empty
    assert h.index.max() <= ts, "a bar from after the decision time survived"


def _paired_frames(stock_last: float, market_last: float, n: int = 300,
                   seed: int = 7):
    """A stock with beta 1 and its own idiosyncratic noise, plus its market.

    Deliberately NOT perfectly collinear: a stock whose returns equal the
    market's exactly has a residual of floating-point dust, and dividing a
    rounding error by another rounding error produces a z-score of whatever it
    likes. That degenerate fixture is what a first draft of this test used, and
    it "failed" against correct code.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-02", periods=n)
    m = rng.normal(0.0, 0.010, n)
    idio = rng.normal(0.0, 0.005, n)
    m[-1], idio[-1] = market_last, stock_last - market_last
    r = m + idio

    def frame(rets):
        close = 100 * np.exp(np.cumsum(rets))
        vol = rng.integers(1_000_000, 2_000_000, n).astype(float)
        return pd.DataFrame({"Close": close, "Volume": vol}, index=idx)
    return frame(r), frame(m)


@pytest.mark.parametrize("stock_last,market_last,unusual", [
    (0.060, 0.060, False),      # moved 6% because the whole market did
    (0.060, 0.000, True),       # moved 6% while the market did nothing
])
def test_the_residual_is_market_adjusted_not_raw(monkeypatch, stock_last,
                                                 market_last, unusual):
    """On a day the index falls 3% every security prints an unusual move, and a
    raw-return trigger list becomes a list of large caps. What is wanted is a
    security doing something its market did not.
    """
    from backend.services import data_fetcher
    F._MARKET_CACHE.clear()
    stock, market = _paired_frames(stock_last, market_last)
    monkeypatch.setattr(data_fetcher, "fetch_ticker_history",
                        lambda t, period="1y": (market if t == F.MARKET
                                                else stock))
    ts = F.resolve_decision_ts("2027-01-01 16:00")
    z = F.assemble_ticker("X", ts)["abs_resid_return_z_1d"]
    assert z.status == F.OK_DATA
    assert "beta" in z.note
    if unusual:
        assert z.value > 3.0, "an idiosyncratic 6% move did not register"
    else:
        assert z.value < 2.0, "a move the whole market made scored as unusual"


def test_a_missing_market_series_does_not_silently_become_a_raw_return(
        monkeypatch):
    from backend.services import data_fetcher
    F._MARKET_CACHE.clear()
    monkeypatch.setattr(data_fetcher, "fetch_ticker_history",
                        lambda t, period="1y": (None if t == F.MARKET
                                                else _hist(n=300)))
    ts = F.resolve_decision_ts("2027-01-01 16:00")
    vals = F.assemble_ticker("X", ts)
    z = vals["abs_resid_return_z_1d"]
    assert z.status == F.UNAVAILABLE
    assert "silently change what the feature measures" in z.note


# ── the snapshot is immutable ───────────────────────────────────────────────

def test_a_snapshot_refuses_to_overwrite_itself(monkeypatch, tmp_path):
    """Rebuilding a night's inputs would substitute today's corrected calendar,
    filing index and adjusted prices for what the model actually saw."""
    monkeypatch.setattr(F, "SNAPSHOT_DIR", tmp_path)
    snap = {"decision_ts": "2026-08-14T21:00:00-04:00"}
    p = F.write_snapshot(snap)
    assert p.exists()
    with pytest.raises(FileExistsError, match="point-in-time record"):
        F.write_snapshot(snap)
    F.write_snapshot(snap, overwrite=True)          # explicit, and only that


def test_load_snapshot_refuses_rather_than_returning_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "SNAPSHOT_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="frozen before any money"):
        F.load_snapshot(F.resolve_decision_ts("2026-08-14 21:00"))


def test_the_snapshot_carries_provenance_for_every_feature(monkeypatch):
    monkeypatch.setattr(F, "_history_upto", lambda t, ts: None)
    monkeypatch.setattr(F, "_earnings_within",
                        lambda t, ts, f: F.FeatureValue(False, F.OK_EMPTY, "s",
                                                        "o", f))
    monkeypatch.setattr(F, "_filing_within",
                        lambda t, ts, f: F.FeatureValue(False, F.OK_EMPTY, "s",
                                                        "o", f))
    snap = F.assemble("2026-08-14 21:00", universe=["A", "B"])
    for t in ("A", "B"):
        prov = snap["provenance"][t]
        assert set(prov) >= set(TR.TRIGGER_WEIGHTS) | {"price",
                                                       "dollar_volume_20d"}
        for v in prov.values():
            assert v["status"] in (F.OK_DATA, F.OK_EMPTY, F.UNAVAILABLE)
            assert v["source"] and v["observed_at"] and v["fetched_at"]
    assert json.dumps(snap, default=str)            # round-trips to the file


def test_the_universe_order_is_deterministic():
    """Ties in the trigger score break by ticker, so a universe arriving in a
    different order must still produce the same forty names."""
    a, b = F.default_universe(), F.default_universe()
    assert a == b == sorted(set(a))
    assert len(a) > 50
