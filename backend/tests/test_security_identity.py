"""SECURITY-IDENTITY-LAYER-1 — the four proven cases as regression fixtures.

MMC→MRSH, SQ↔XYZ, EA's death (and its 8 quote-ghost days), dead PXD. If any
of these ever "goes missing" again, a test names it before a session spends
hours rediscovering a rename.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backend.services import security_identity as SI


# ── the MMC→MRSH boundary, dated ───────────────────────────────────────────
def test_mmc_resolves_to_mmc_before_rename():
    r = SI.resolve("MMC", "2025-12-31")
    assert r.aegis_id == "AEGIS-MARSH"
    assert r.ticker_on_date == "MMC"
    assert r.alive and r.provenance == "CURATED"


def test_mmc_asked_after_rename_maps_to_mrsh():
    r = SI.resolve("MMC", "2026-08-14")
    assert r.aegis_id == "AEGIS-MARSH"
    assert r.ticker_on_date == "MRSH", (
        "sym_root='MMC' after 2026-01-14 was the right company at the "
        "wrong symbol — the exact defect this layer exists to catch")


def test_rename_day_itself_belongs_to_the_new_symbol():
    assert SI.resolve("MRSH", "2026-01-14").ticker_on_date == "MRSH"


# ── SQ↔XYZ: same identity, honestly undated ────────────────────────────────
def test_sq_and_xyz_share_an_identity():
    assert (SI.resolve("SQ", "2026-08-01").aegis_id
            == SI.resolve("XYZ", "2026-08-01").aegis_id == "AEGIS-BLOCK")


def test_block_rename_date_is_declared_unrecorded_not_invented():
    rec = next(r for r in SI._MASTER if r.aegis_id == "AEGIS-BLOCK")
    assert all(f is None and t is None for _, f, t in rec.aliases)
    assert any("UNRECORDED" in n for n in rec.notes)


# ── EA: death, and the ghost signature ─────────────────────────────────────
def test_ea_alive_before_buyout_dead_after():
    assert SI.resolve("EA", "2026-08-01").alive
    assert not SI.resolve("EA", "2026-08-05").alive


def test_assert_alive_refuses_dead_ea():
    with pytest.raises(SI.SecurityDead):
        SI.assert_alive("EA", "2026-08-14")


def test_pxd_is_dead_and_says_why():
    r = SI.resolve("PXD", date(2026, 8, 19))
    assert not r.alive and "Exxon" in r.terminal_reason


def test_quote_ghost_scan_catches_the_ea_signature():
    days = pd.date_range("2026-07-28", periods=14, freq="B")
    rows = []
    for d in days:
        dead = d > pd.Timestamp("2026-08-04")
        rows.append({"ticker": "EA", "date": d,
                     "n_trades": 0 if dead else 50_000,
                     "n_quotes": 40_000})
        rows.append({"ticker": "AAPL", "date": d,
                     "n_trades": 400_000, "n_quotes": 900_000})
    flags = SI.quote_ghost_scan(pd.DataFrame(rows))
    assert len(flags) == 1 and flags[0]["ticker"] == "EA"
    assert flags[0]["ghost_days_at_end"] >= 3
    assert "2026-08-04" in flags[0]["last_trade_date"]


def test_ghost_scan_does_not_flag_a_merely_illiquid_name():
    days = pd.date_range("2026-08-03", periods=8, freq="B")
    rows = [{"ticker": "THIN", "date": d,
             "n_trades": 3 if i % 2 else 0, "n_quotes": 500}
            for i, d in enumerate(days)]
    assert SI.quote_ghost_scan(pd.DataFrame(rows)) == []


# ── refusals (guard contract: missing input → refusal, never a default) ────
def test_resolve_refuses_missing_ticker():
    with pytest.raises(SI.IdentityUnknown):
        SI.resolve("", "2026-08-19")


def test_resolve_refuses_missing_date():
    with pytest.raises(SI.IdentityUnknown):
        SI.resolve("AAPL", None)


def test_ghost_scan_refuses_empty_panel():
    with pytest.raises(SI.IdentityUnknown):
        SI.quote_ghost_scan(pd.DataFrame(
            columns=["ticker", "date", "n_trades", "n_quotes"]))


def test_ghost_scan_refuses_missing_columns():
    with pytest.raises(SI.IdentityUnknown):
        SI.quote_ghost_scan(pd.DataFrame({"ticker": ["A"], "date": ["x"]}))


# ── unknown names pass through VISIBLY, never silently ─────────────────────
def test_unknown_ticker_is_assumed_stable_with_visible_provenance():
    r = SI.resolve("NVDA", "2026-08-19")
    assert r.alive and r.ticker_on_date == "NVDA"
    assert r.provenance == "ASSUMED_STABLE", (
        "a curated 4-row table must not impersonate market coverage")
