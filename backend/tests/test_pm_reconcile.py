"""The reconciler must recover the book without inventing any part of it.

Every test here pins a way the recovery could go quietly wrong: a source read
as zero instead of unreadable, a logging price promoted to a cost basis, the
$100k paper lane mistaken for the $45k account, a conflict resolved in silence.
"""
from __future__ import annotations

import json

import pytest
import yaml

from backend.services import pm_engine, pm_reconcile as R


# ─────────────────────────────── fixtures ──────────────────────────────────

@pytest.fixture
def lanes_file(tmp_path):
    p = tmp_path / "book_lanes.yaml"
    p.write_text(yaml.safe_dump({
        "holdings": {"AAA": 100, "BBB": 200, "CCC": 300},
        "inception": {"notional_usd": 100000.0, "benchmark": "SPY"},
    }), encoding="utf-8")
    return p


@pytest.fixture
def conv_file(tmp_path):
    p = tmp_path / "conv.json"
    p.write_text(json.dumps({
        "source": "https://example.invalid/api",
        "fetched_at": "2026-08-10T00:00:00+00:00",
        "payload_sha256": "deadbeef",
        "decisions": [
            {"id": 1, "timestamp": "2026-07-11T05:00:00", "ticker": "AAA",
             "action": "enter", "shares_delta": 100.0, "price": 10.0,
             "rationale": "bought months ago", "late_entry": False,
             "conviction": 3},
            {"id": 2, "timestamp": "2026-07-11T05:01:00", "ticker": "BBB",
             "action": "enter", "shares_delta": 250.0, "price": 4.0,
             "rationale": "", "late_entry": False, "conviction": 3},
            {"id": 3, "timestamp": "2026-07-11T05:02:00", "ticker": "CCC",
             "action": "enter", "shares_delta": 300.0, "price": 7.0,
             "rationale": "", "late_entry": False, "conviction": 3},
        ],
    }), encoding="utf-8")
    return p


@pytest.fixture
def book_file(tmp_path):
    p = tmp_path / "murat_book.yaml"
    p.write_text(yaml.safe_dump({
        "account": "t", "confirmed": False, "cash": 0,
        "sizing_mode": "high_growth",
        "wealth_targets": {"horizon_months": 12, "target_value": 100000},
        "positions": [
            {"ticker": "AAA", "dollars": 1000, "cost_basis": 8.0,
             "entry_date": "2025-11-07", "thesis": "t", "kill_condition": "k"},
            {"ticker": "ZZZ", "dollars": 500, "cost_basis": 3.0},
        ],
        "watchlist": ["QQQ"],
    }), encoding="utf-8")
    return p


def _run(lanes_file, conv_file, book_file):
    return R.reconcile(book_lanes_path=lanes_file,
                       conviction_path=conv_file,
                       murat_book_path=book_file)


# ────────────────────────────── the recovery ────────────────────────────────

def test_recovers_every_share_count_without_asking(lanes_file, conv_file, book_file):
    rep = _run(lanes_file, conv_file, book_file)
    assert rep["summary"]["n_positions_recovered"] == 3
    assert rep["summary"]["n_share_counts_known"] == 3
    by = {p["ticker"]: p for p in rep["positions"]}
    assert by["AAA"]["shares"] == 100
    assert by["CCC"]["shares"] == 300


def test_a_conflict_is_reported_never_silently_resolved(lanes_file, conv_file, book_file):
    """BBB: the log says 250, the lane config says 200."""
    rep = _run(lanes_file, conv_file, book_file)
    by = {p["ticker"]: p for p in rep["positions"]}
    assert by["BBB"]["shares_contested"] is True
    assert by["BBB"]["shares"] == 250, "the dated log wins"
    dis = [d for d in rep["disagreements"] if d.get("ticker") == "BBB"]
    assert dis, "the disagreement must appear in the report, not only inline"
    assert dis[0]["claims"] == {"conviction_log": 250.0, "book_lanes": 200.0}
    assert dis[0]["needs_murat"] is True
    # and the agreeing names must NOT be flagged
    assert by["AAA"]["shares_contested"] is False


def test_the_logging_price_never_becomes_a_cost_basis(lanes_file, conv_file, book_file):
    """The log's `price` is a mark on the day it was typed, not a fill."""
    rep = _run(lanes_file, conv_file, book_file)
    by = {p["ticker"]: p for p in rep["positions"]}
    # BBB and CCC have a logged price but no reconstruction cost basis.
    for t in ("BBB", "CCC"):
        assert by[t]["cost_basis"] is None
        assert by[t]["cost_basis_status"] == "MISSING"
        assert by[t]["last_logged_price"] is not None, (
            "the mark is still recorded — it is evidence, just not a basis")
    # AAA has one, from the reconstruction only.
    assert by["AAA"]["cost_basis"] == 8.0
    assert by["AAA"]["cost_basis_source"] == "murat_book"
    assert by["AAA"]["cost_basis_status"] == "RECONSTRUCTED"


def test_cash_is_always_reported_unrecoverable(lanes_file, conv_file, book_file):
    rep = _run(lanes_file, conv_file, book_file)
    assert rep["summary"]["cash"] == "UNRECOVERABLE"
    cash = [u for u in rep["unrecoverable"] if u["field"] == "cash"]
    assert cash and cash[0]["needs_murat"] is True


def test_a_stale_reconstruction_name_is_excluded_exactly_once(
        lanes_file, conv_file, book_file):
    rep = _run(lanes_file, conv_file, book_file)
    tickers = [p["ticker"] for p in rep["positions"]]
    assert "ZZZ" not in tickers, "not in the dated log => not held"
    excluded = [e["ticker"] for e in rep["excluded"]]
    assert excluded.count("ZZZ") == 1, "a duplicated exclusion double-counts"
    zzz = [e for e in rep["excluded"] if e["ticker"] == "ZZZ"][0]
    assert zzz["inference"] is True, "this is reasoning, and must say so"


def test_an_unreadable_source_is_a_finding_not_a_zero(tmp_path, conv_file, book_file):
    """The house failure mode: a source that fails and reads as 'nothing here'."""
    missing = tmp_path / "nope.yaml"
    rep = R.reconcile(book_lanes_path=missing, conviction_path=conv_file,
                      murat_book_path=book_file)
    assert rep["sources"]["book_lanes"]["status"] == "UNREADABLE"
    assert "error" in rep["sources"]["book_lanes"]
    # and the recovery still proceeds on the sources that DID read
    assert rep["summary"]["n_positions_recovered"] == 3
    # with nothing contested, because there is no second opinion to contest
    assert rep["summary"]["n_contested"] == 0


def test_an_uninterpretable_decision_row_does_not_move_shares(tmp_path, lanes_file,
                                                              book_file):
    p = tmp_path / "conv2.json"
    p.write_text(json.dumps({"decisions": [
        {"id": 1, "timestamp": "2026-07-11T05:00:00", "ticker": "AAA",
         "action": "enter", "shares_delta": 100.0, "price": 10.0},
        {"id": 2, "timestamp": "2026-07-11T05:01:00", "ticker": "AAA",
         "action": "teleport", "shares_delta": 999.0, "price": 10.0},
        {"id": 3, "timestamp": "2026-07-11T05:02:00", "ticker": "AAA",
         "action": "enter", "shares_delta": "not a number", "price": 10.0},
    ]}), encoding="utf-8")
    rep = R.reconcile(book_lanes_path=lanes_file, conviction_path=p,
                      murat_book_path=book_file)
    by = {x["ticker"]: x for x in rep["positions"]}
    assert by["AAA"]["shares"] == 100, "the garbage rows moved nothing"
    kinds = [d["kind"] for d in rep["disagreements"]]
    assert "uninterpretable_decision_rows" in kinds, "and they were reported"


def test_an_exit_closes_the_position(tmp_path, lanes_file, book_file):
    p = tmp_path / "conv3.json"
    p.write_text(json.dumps({"decisions": [
        {"id": 1, "timestamp": "2026-07-11T05:00:00", "ticker": "AAA",
         "action": "enter", "shares_delta": 100.0, "price": 10.0},
        {"id": 2, "timestamp": "2026-07-12T05:00:00", "ticker": "AAA",
         "action": "exit", "shares_delta": 100.0, "price": 12.0},
    ]}), encoding="utf-8")
    rep = R.reconcile(book_lanes_path=lanes_file, conviction_path=p,
                      murat_book_path=book_file)
    by = {x["ticker"]: x for x in rep["positions"]}
    # book_lanes still lists AAA at 100. The exit must WIN and must be flagged:
    # a sold name reappearing at a config's share count is the silent-wrong
    # failure this whole module exists to prevent.
    assert by["AAA"]["shares"] == 0.0, "the dated exit beats the stale config"
    assert by["AAA"]["shares_contested"] is True
    assert any("exited" in n for n in by["AAA"]["notes"])
    dis = [d for d in rep["disagreements"] if d.get("ticker") == "AAA"]
    assert dis and dis[0]["needs_murat"] is True


# ──────────────────────── the rendered book must be safe ────────────────────

def test_the_rendered_book_never_confirms_itself(lanes_file, conv_file, book_file):
    rep = _run(lanes_file, conv_file, book_file)
    text = R.to_book_yaml(rep)
    assert "confirmed: false" in text
    assert "confirmed: true" not in text
    parsed = yaml.safe_load(text)
    assert parsed["confirmed"] is False


def test_the_rendered_book_loads_and_marks_to_market(lanes_file, conv_file,
                                                     book_file, tmp_path):
    rep = _run(lanes_file, conv_file, book_file)
    out = tmp_path / "recovered.yaml"
    out.write_text(R.to_book_yaml(rep), encoding="utf-8")
    book = pm_engine.load_book(out, strict=False)
    assert len(book.positions) == 3
    assert all(p.shares is not None for p in book.positions), (
        "a recovered position without a share count cannot mark to market")
    marked = pm_engine.mark_book(book, {"AAA": 11.0, "BBB": 5.0, "CCC": 8.0})
    assert marked["invested"] == pytest.approx(100 * 11 + 250 * 5 + 300 * 8)


def test_every_share_count_carries_its_provenance(lanes_file, conv_file, book_file):
    rep = _run(lanes_file, conv_file, book_file)
    text = R.to_book_yaml(rep)
    for tic in ("AAA", "BBB", "CCC"):
        assert f"ticker: {tic}" in text
    assert text.count("# shares from") == 3
    assert "claims:" in text
    assert "CONTESTED" in text, "the contested line must be visible in the file"


def test_unrecoverable_cash_is_stated_in_the_file(lanes_file, conv_file, book_file):
    rep = _run(lanes_file, conv_file, book_file)
    text = R.to_book_yaml(rep)
    assert "UNRECOVERABLE" in text
    assert "cash:" in text


def test_the_mirror_lane_notional_is_never_used_as_shares(lanes_file, conv_file,
                                                          book_file):
    """The $100k paper lane rescales the book; its shares are not holdings.

    book_lanes.yaml carries `inception.notional_usd: 100000`. If a future
    refactor ever reads the SEEDED lane share counts instead of `holdings:`,
    the recovered book would be ~2.5x the real account. Pin the read.
    """
    rep = _run(lanes_file, conv_file, book_file)
    by = {p["ticker"]: p for p in rep["positions"]}
    claims = {c["source"]: c["value"] for c in by["AAA"]["shares_claims"]}
    assert claims["book_lanes"] == 100, "must come from holdings:, not the seed"
    text = json.dumps(rep)
    assert "100000" not in text or "notional" not in text
