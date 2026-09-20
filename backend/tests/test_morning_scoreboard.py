"""THE MORNING SCOREBOARD — what it derives, and what it refuses to invent.

`backend/services/morning_scoreboard.py` (chunk 21, Murat's item 12). Every
input here is a SYNTHETIC receipt written into `tmp_path`: no test in this file
reads `backend/data`, opens a socket or calls a model, and every path the
module reads is a parameter.

The load-bearing test is `test_every_absent_field_says_why_and_never_zero`. A
scoreboard that prints `0.0%` where it means "nothing has been scored" is the
failure this module exists to avoid — the reader acts on the zero.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend import config
from backend.services import morning_scoreboard as MS

ASOF = date(2026, 9, 20)


# ── synthetic receipts ──────────────────────────────────────────────────────

def _contract(day: str, *, exploit=(), explore=(), refused=("ZZZ",),
              capital=40_000.0):
    rows = []
    for i, (ticker, weight) in enumerate(list(exploit) + list(explore)):
        authority = "EXPLOIT" if (ticker, weight) in list(exploit) else "EXPLORE"
        rows.append({
            "decision_id": f"{day}-{ticker}",
            "ticker": ticker, "asof": day, "direction": "BUY",
            "authority": authority,
            "authority_basis": f"{authority} because the fixture says so",
            "position_budget": {"weight": weight, "dollars": weight * capital,
                                "capital_usd": capital},
        })
    for ticker in refused:
        rows.append({
            "decision_id": f"{day}-{ticker}", "ticker": ticker, "asof": day,
            "direction": "REFUSED", "authority": "REFUSED",
            "authority_basis": "no measured read exists",
            "position_budget": {"weight": 0.0, "capital_usd": capital},
        })
    exploit_pct = sum(w for _, w in exploit)
    explore_pct = sum(w for _, w in explore)
    return {
        "receipt": "decision_contract", "date": day, "capital_usd": capital,
        "count_by_direction": {"BUY": len(exploit) + len(explore), "WATCH": 0,
                               "SELL": 0, "REFUSED": len(refused)},
        "authority": {"count_by_authority_over_rows": {
            "EXPLOIT": len(exploit), "EXPLORE": len(explore),
            "REFUSED": len(refused)}},
        "capital_resolution": {
            "benchmark_pct": 1.0 - exploit_pct - explore_pct,
            "active_exploit_pct": exploit_pct,
            "active_explore_pct": explore_pct, "cash_pct": 0.0,
            "sums_to": 1.0,
            "nothing_happened_is_not_allowed": "every dollar resolved today",
        },
        "rows": rows,
    }


@pytest.fixture()
def world(tmp_path):
    """A whole day of receipts on disk, all synthetic, all under tmp_path."""
    decisions = tmp_path / "decisions"
    night = tmp_path / "night_factory_2026-09-20"
    replay = tmp_path / "replay"
    for d in (decisions, night, replay):
        d.mkdir(parents=True)
    (decisions / "2026-09-19.json").write_text(
        json.dumps(_contract("2026-09-19")), encoding="utf-8")
    (decisions / "2026-09-20.json").write_text(
        json.dumps(_contract("2026-09-20",
                             explore=(("AAA", 0.0025), ("BBB", 0.0025)))),
        encoding="utf-8")
    (night / "grade_forecasts_2026-09-20.json").write_text(json.dumps({
        "newly_resolved": 14_703, "graded_after_this_run": 14_703,
        "n_records": 24_839,
        "totals": {"not_yet_due": 7_219, "NO_BAR_FOR_RESOLUTION_DATE": 2_911},
        "headline": "14,703 newly resolved"}), encoding="utf-8")
    (night / "decision_vs_reality_2026-09-20.json").write_text(json.dumps({
        "window": "trailing_24h", "overall": {"n": 0, "brier": None},
        "by_mechanism": [], "headline": "nothing resolved"}), encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    return {"decisions": decisions, "night": night, "replay": replay,
            "ledger": ledger, "root": tmp_path}


def _replay(folder, name, stamp, *, excess, t, verdict, smoke=False):
    body = {"book": name, "smoke": smoke, "verdict": verdict,
            "cells": {"primary_floor": {"result": {
                "mean_excess_net_monthly": excess, "nw_lag2_t": t,
                "n_blocks": 419, "floor_usd": 3_000_000.0}}}}
    suffix = "_smoke" if smoke else ""
    (folder / f"{name}_{stamp}Z{suffix}.json").write_text(
        json.dumps(body), encoding="utf-8")


def _board(world, **kw):
    kw.setdefault("asof", ASOF)
    kw.setdefault("out_dir", world["decisions"])
    kw.setdefault("ledger_path", world["ledger"])
    kw.setdefault("night_folder", world["night"])
    kw.setdefault("replay_folder", world["replay"])
    kw.setdefault("navs", {})
    return MS.compose(**kw)


# ===========================================================================
# THE RULE
# ===========================================================================


def test_every_absent_field_says_why_and_never_zero(world):
    board = _board(world)
    for field in ("nav_vs_spy", "exploit_pnl", "explore_pnl", "calibration",
                  "strongest_new_positive", "strongest_killed"):
        value = board[field]
        assert isinstance(value, str), field
        assert value.startswith("CANNOT DETERMINE: "), field
        assert len(value) > 40, f"{field} names no reason"
    # ... and the ones that CAN be derived are derived, not refused
    assert board["forecasts"]["newly_resolved"] == 14_703
    assert board["capital_resolution"]["active_explore_pct"] == 0.005
    assert board["decisions"]["count_by_authority"]["EXPLORE"] == 2


def test_the_nine_fields_murat_asked_for_are_all_present(world):
    board = _board(world)
    for field in ("nav_vs_spy", "exploit_pnl", "explore_pnl", "decisions",
                  "forecasts", "calibration", "strongest_new_positive",
                  "strongest_killed", "learning_changed_capital",
                  "capital_resolution"):
        assert field in board, field
    assert board["licence"] == "PRODUCT_EXPERIMENT"
    assert board["llm_spend_usd"] == 0.0
    text = MS.render(board)
    assert text.startswith("### the morning scoreboard")
    for label in ("NAV vs", "EXPLOIT P&L", "EXPLORE P&L", "every dollar today",
                  "decisions", "forecasts matured and graded", "calibration",
                  "strongest new positive", "strongest killed",
                  "learning changed capital"):
        assert label in text, label


# ===========================================================================
# THE P&L — attributed to the authority that took the decision
# ===========================================================================


def test_realised_pnl_is_attributed_per_authority(world):
    """EXPLOIT P&L and EXPLORE P&L are different questions and never summed."""
    rows = [
        {"decision_id": "2026-09-20-AAA", "state": "SCORED",
         "detail": {"realised_return": 0.10}},
        {"decision_id": "2026-09-20-BBB", "state": "SCORED",
         "detail": {"realised_return": -0.04}},
        {"decision_id": "2026-09-20-ZZZ", "state": "SCORED",
         "detail": {"realised_return": 9.99}},   # REFUSED: never counted
        {"decision_id": "2026-09-20-AAA", "state": "DECIDED", "detail": {}},
    ]
    world["ledger"].write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    board = _board(world)
    explore = board["explore_pnl"]
    assert explore["n_scored"] == 2
    # 0.25% x +10% + 0.25% x -4% = +0.015% of the book
    assert explore["weighted_return_pct"] == pytest.approx(0.015, abs=1e-6)
    assert explore["dollars"] == pytest.approx(0.0025 * 0.06 * 40_000, abs=1e-6)
    assert isinstance(board["exploit_pnl"], str)      # nothing scored: refused
    assert "no EXPLOIT decision has been SCORED" in board["exploit_pnl"]


def test_a_scored_row_with_no_realised_return_is_counted_not_zeroed(world):
    world["ledger"].write_text(json.dumps(
        {"decision_id": "2026-09-20-AAA", "state": "SCORED",
         "detail": {"realised_return": None}}), encoding="utf-8")
    board = _board(world)
    assert isinstance(board["explore_pnl"], str)
    assert "1 scored row(s) carried no usable realised return" in \
        board["explore_pnl"]


# ===========================================================================
# STRONGEST NEW POSITIVE / KILLED — dated by the receipt's own stamp
# ===========================================================================


def test_the_strongest_rows_are_ranked_and_smoke_runs_are_excluded(world):
    _replay(world["replay"], "weak_book", "2026-09-18T090000",
            excess=0.001, t=1.1, verdict="CONDITIONAL")
    _replay(world["replay"], "strong_book", "2026-09-19T090000",
            excess=0.010, t=5.65, verdict="PRODUCT_PROMISING")
    _replay(world["replay"], "fake_book", "2026-09-19T100000",
            excess=0.900, t=99.0, verdict="PRODUCT_PROMISING", smoke=True)
    _replay(world["replay"], "dead_book", "2026-09-19T110000",
            excess=-0.002, t=-0.29, verdict="FAILED_VARIANT — wrong side")
    board = _board(world)
    assert board["strongest_new_positive"]["book"] == "strong_book"
    assert board["strongest_killed"]["book"] == "dead_book"
    assert "strong_book" in MS.render(board)


def test_a_receipt_outside_the_window_is_not_new(world):
    _replay(world["replay"], "old_book", "2026-08-01T090000",
            excess=0.02, t=9.0, verdict="PRODUCT_PROMISING")
    board = _board(world, window_days=7)
    assert isinstance(board["strongest_new_positive"], str)
    assert "last 7 day(s)" in board["strongest_new_positive"]
    # the same file IS new in a wider window — the window is the only filter
    wide = _board(world, window_days=90)
    assert wide["strongest_new_positive"]["book"] == "old_book"


def test_the_window_is_dated_by_the_receipts_own_stamp_not_the_filesystem(
        world):
    """Session protocol 7: a gate on `st_mtime` is a gate on checkout time.

    The file is written NOW (so its mtime is today) and stamped in August. It
    must read as August, or a fresh CI checkout would call every receipt new.
    """
    _replay(world["replay"], "old_book", "2026-08-01T090000",
            excess=0.02, t=9.0, verdict="PRODUCT_PROMISING")
    rows = MS._replay_rows(world["replay"], asof=ASOF, window_days=365)
    assert rows and rows[0]["stamped"] == "2026-08-01"


# ===========================================================================
# NAV vs SPY, and the one sentence
# ===========================================================================


def test_nav_vs_spy_differences_the_same_window(world, monkeypatch):
    monkeypatch.setattr(MS, "spy_closes",
                        lambda start, end: [("2026-09-01", 100.0),
                                            ("2026-09-19", 110.0)])
    navs = {"book:alpha": [("2026-09-01", 100.0), ("2026-09-19", 120.0)]}
    board = _board(world, navs=navs)
    nav = board["nav_vs_spy"]
    assert nav["mean_since_inception_pct"] == pytest.approx(20.0)
    assert nav["benchmark_pct"] == pytest.approx(10.0)
    assert nav["excess_pct"] == pytest.approx(10.0)


def test_a_nav_reader_that_raises_is_a_different_finding_from_no_nav(
        world, monkeypatch):
    """Silent fragility, refused: a caught exception must not read as a fact.

    `nav_map` returns its problems instead of logging them away, so "nobody
    marked" and "the reader raised" cannot print the same sentence.
    """
    monkeypatch.setattr(MS, "nav_map",
                        lambda: ({}, ["book NAV unreadable (OSError: disk)"]))
    board = _board(world, navs=None)
    assert "the NAV readers REFUSED" in board["nav_vs_spy"]
    assert "OSError: disk" in board["nav_vs_spy"]


def test_a_missing_benchmark_refuses_the_excess_rather_than_zeroing_it(
        world, monkeypatch):
    monkeypatch.setattr(MS, "spy_closes", lambda start, end: [])
    navs = {"book:alpha": [("2026-09-01", 100.0), ("2026-09-19", 120.0)]}
    nav = _board(world, navs=navs)["nav_vs_spy"]
    assert nav["mean_since_inception_pct"] == pytest.approx(20.0)
    assert str(nav["excess_pct"]).startswith("CANNOT DETERMINE")


def test_the_one_sentence_can_say_no(world):
    """A scoreboard that cannot say 'no' cannot say 'yes' (§15.1)."""
    same = _contract("2026-09-19", explore=(("AAA", 0.0025), ("BBB", 0.0025)))
    (world["decisions"] / "2026-09-19.json").write_text(json.dumps(same),
                                                        encoding="utf-8")
    sentence = _board(world)["learning_changed_capital"]
    assert sentence.startswith("no: the split is identical to 2026-09-19")


def test_the_one_sentence_names_what_moved(world):
    sentence = _board(world)["learning_changed_capital"]
    assert sentence.startswith("yes: since 2026-09-19")
    assert "EXPLORE 0.00% -> 0.50%" in sentence
    assert "added AAA, BBB" in sentence


def test_a_contract_without_the_split_cannot_claim_capital_moved(world):
    old = _contract("2026-09-20", explore=(("AAA", 0.0025),))
    old.pop("capital_resolution")
    (world["decisions"] / "2026-09-20.json").write_text(json.dumps(old),
                                                        encoding="utf-8")
    sentence = _board(world)["learning_changed_capital"]
    assert sentence.startswith("CANNOT DETERMINE")
    assert "'the file cannot say'" in sentence


def test_compose_writes_nothing(world):
    before = sorted(p.name for p in world["root"].rglob("*"))
    _board(world)
    assert sorted(p.name for p in world["root"].rglob("*")) == before


def test_the_desktop_ask_puts_the_scoreboard_first(monkeypatch):
    from backend.services import ask_tools

    monkeypatch.setattr(ask_tools, "scoreboard_paragraph",
                        lambda: "### the morning scoreboard\n- fixture")
    body, _ = ask_tools.tool_decisions()
    assert body.startswith("### the morning scoreboard")


def test_the_scoreboard_paragraph_never_costs_the_reader_the_decisions(
        monkeypatch):
    from backend.services import ask_tools

    def boom(**kw):
        raise RuntimeError("receipts unreadable (test)")

    monkeypatch.setattr(MS, "compose", boom)
    text = ask_tools.scoreboard_paragraph()
    assert text.startswith("### the morning scoreboard")
    assert "CANNOT DETERMINE" in text
    assert "decisions below are unaffected" in text


def test_the_kill_verdicts_are_configured_not_spelled_in_the_module():
    assert "FAILED_VARIANT" in config.SCOREBOARD_KILL_VERDICTS
    assert "STOP" not in config.SCOREBOARD_KILL_VERDICTS
