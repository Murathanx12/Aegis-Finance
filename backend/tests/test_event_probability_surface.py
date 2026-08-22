"""EVENT_PROBABILITY_SURFACE v0 — basket coherence on the FED_DECISION family.

Pins: a complete basket is judged against sum=1, a partial basket is refused
a coherence verdict (its missing class is simply not quoted), a one-sided
book refuses a mid, and sanity violations (crossed books) are named. One
meeting = one statistical unit — the surface never grades five correlated
binaries as five results.
"""

from __future__ import annotations

import json

import pytest

from backend import config
from backend.services import event_probability_surface as eps


@pytest.fixture
def pm_dir(tmp_path, monkeypatch):
    d = tmp_path / "pmkt"
    monkeypatch.setattr(config, "PREDICTION_MARKET_DIR", d)
    return d


def _write_day(pm_dir, day, source, rows):
    p = pm_dir / "snapshots" / f"{day}.{source}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                 encoding="utf-8")


def _kalshi_basket(meeting_code, mids, bids_asks=None):
    """Rows for one Kalshi meeting. mids: {class_code: mid}."""
    rows = []
    for code, mid in mids.items():
        row = {"source": "kalshi",
               "ticker": f"KXFEDDECISION-{meeting_code}-{code}",
               "title": "t", "mid": mid}
        if bids_asks and code in bids_asks:
            row["yes_bid"], row["yes_ask"] = bids_asks[code]
        rows.append(row)
    return rows


FULL = {"H0": 0.62, "H25": 0.10, "H26": 0.02, "C25": 0.22, "C26": 0.04}


class TestBasketCoherence:
    def test_complete_coherent_basket(self, pm_dir):
        _write_day(pm_dir, "2026-08-22", "kalshi",
                   _kalshi_basket("26SEP", FULL))  # sums to 1.00
        out = eps.surface_day("2026-08-22")
        k = out["venues"]["kalshi"]
        assert k["n_meetings"] == 1
        rep = k["meetings"][0]
        assert rep["verdict"] == "COHERENT"
        assert rep["mid_sum"] == pytest.approx(1.00)
        assert rep["deviation_from_one"] <= eps.BASKET_TOLERANCE
        assert set(rep["implied_distribution"]) == eps.FULL_CLASS_SET

    def test_incoherent_basket_is_flagged_with_deviation(self, pm_dir):
        mids = dict(FULL, H0=0.70)  # sums to 1.08
        _write_day(pm_dir, "2026-08-22", "kalshi",
                   _kalshi_basket("26SEP", mids))
        out = eps.surface_day("2026-08-22")
        rep = out["venues"]["kalshi"]["meetings"][0]
        assert rep["verdict"] == "BASKET_INCOHERENT"
        assert rep["deviation_from_one"] == pytest.approx(0.08)

    def test_partial_basket_gets_no_coherence_verdict(self, pm_dir):
        mids = {"H0": 0.70, "C25": 0.25}  # 3 classes unquoted
        _write_day(pm_dir, "2026-08-22", "kalshi",
                   _kalshi_basket("26SEP", mids))
        out = eps.surface_day("2026-08-22")
        rep = out["venues"]["kalshi"]["meetings"][0]
        assert rep["verdict"] == "PARTIAL_BASKET"
        assert "deviation_from_one" not in rep, (
            "an incomplete basket must not be judged against sum=1")
        assert set(rep["missing_classes"]) == {"hike_25", "hike_50plus",
                                               "cut_50plus"}

    def test_one_sided_book_refuses_the_meeting(self, pm_dir):
        rows = _kalshi_basket("26SEP", dict(FULL, H26=None))
        _write_day(pm_dir, "2026-08-22", "kalshi", rows)
        out = eps.surface_day("2026-08-22")
        rep = out["venues"]["kalshi"]["meetings"][0]
        assert rep["verdict"] == "REFUSED_NO_MID"

    def test_crossed_book_is_named_in_sanity(self, pm_dir):
        rows = _kalshi_basket("26SEP", FULL,
                              bids_asks={"H0": (0.65, 0.60)})  # crossed
        _write_day(pm_dir, "2026-08-22", "kalshi", rows)
        out = eps.surface_day("2026-08-22")
        rep = out["venues"]["kalshi"]["meetings"][0]
        assert any("crossed book" in v for v in rep["sanity_violations"])

    def test_missing_snapshot_reports_not_raises(self, pm_dir):
        _write_day(pm_dir, "2026-08-22", "kalshi",
                   _kalshi_basket("26SEP", FULL))
        out = eps.surface_day("2026-08-22")
        assert out["venues"]["polymarket"] == {"status": "NO_SNAPSHOT"}

    def test_banner_and_unit_declaration_on_every_payload(self, pm_dir):
        _write_day(pm_dir, "2026-08-22", "kalshi",
                   _kalshi_basket("26SEP", FULL))
        out = eps.surface_day("2026-08-22")
        assert "never a signal" in out["banner"]
        assert "one FOMC meeting" in out["statistical_unit"]
