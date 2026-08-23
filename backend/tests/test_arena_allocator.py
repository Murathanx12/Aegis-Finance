"""The ce_kelly capital-engine book and its refusals.

PROFIT_ALLOCATOR_v1 was RETIRED 2026-08-23 (`spec.RETIRED`): it was seeded with
the trust router's cluster adjustment OFF, that setting is part of its policy
identity, and the setting was corrected to ON. It therefore no longer appears in
`active_specs()` — but its SPEC is still in the YAML and still the definition of
the ce_kelly mechanism a successor will use, so these tests read it through
`load_specs()`. They test the allocator, not the roster.

The claim under test is narrow and honest: at FIXED alpha (the same composite
every book sees), does a declared Kelly/CE capital layer behave correctly —
more capital to more edge per unit variance, zero to non-positive edge, cash
as the residual, and aggression throttled while the trust router cannot vouch
for the models. Nothing here is a return claim.
"""

from __future__ import annotations

import pytest

from backend.services.arena import engine, policies
from backend.services.arena import spec as spec_mod

ALLOC = {"ic_prior": 0.05, "kelly_fraction": 0.5,
         "abstain_kelly_factor": 0.5, "max_gross": 1.0}


def _state(names: dict) -> dict:
    return {"date": "2026-08-21", "names": names,
            "priced_fraction": 1.0, "priced_n": len(names),
            "universe_n": len(names)}


def _chosen(*rows):
    return [{"ticker": t, "rank": i + 1, "score": z}
            for i, (t, z) in enumerate(rows)]


# ── the sizing math ─────────────────────────────────────────────────────────
class TestSizeCeKelly:
    def test_more_edge_per_variance_earns_more_capital(self):
        state = _state({
            "CALM": {"status": "ok", "close": 10.0, "vol63": 0.20},
            "WILD": {"status": "ok", "close": 10.0, "vol63": 0.80},
        })
        w, receipt = policies.size_ce_kelly(
            _chosen(("CALM", 1.0), ("WILD", 1.0)), state,
            ic_prior=0.05, kelly_fraction=0.5, max_single_name=0.15)
        # same score, 4x the vol -> 4x less capital
        assert w["CALM"] == pytest.approx(4 * w["WILD"], rel=1e-6)
        assert receipt["sizing"] == "ce_kelly"

    def test_non_positive_edge_earns_nothing(self):
        state = _state({
            "GOOD": {"status": "ok", "close": 10.0, "vol63": 0.3},
            "BAD": {"status": "ok", "close": 10.0, "vol63": 0.3},
        })
        w, receipt = policies.size_ce_kelly(
            _chosen(("GOOD", 1.5), ("BAD", -0.2)), state,
            ic_prior=0.05, kelly_fraction=0.5, max_single_name=0.15)
        assert "BAD" not in w
        reasons = {r["ticker"]: r.get("reason") for r in receipt["names"]}
        assert reasons["BAD"] == "non_positive_edge"

    def test_missing_vol_is_ineligible_not_average(self):
        state = _state({
            "OK": {"status": "ok", "close": 10.0, "vol63": 0.3},
            "NOV": {"status": "ok", "close": 10.0, "vol63": None},
        })
        w, receipt = policies.size_ce_kelly(
            _chosen(("OK", 1.0), ("NOV", 2.0)), state,
            ic_prior=0.05, kelly_fraction=0.5, max_single_name=0.15)
        assert "NOV" not in w
        reasons = {r["ticker"]: r.get("reason") for r in receipt["names"]}
        assert reasons["NOV"] == "no_vol63_under_ce_kelly"

    def test_cash_is_the_residual_never_renormalised_away(self):
        state = _state({"A": {"status": "ok", "close": 10.0, "vol63": 0.4}})
        w, receipt = policies.size_ce_kelly(
            _chosen(("A", 0.5)), state,
            ic_prior=0.05, kelly_fraction=0.5, max_single_name=0.15)
        # 0.5*0.05*0.5/0.4 = 0.03125 -> ~97% cash, and it STAYS cash
        assert sum(w.values()) < 0.05
        assert receipt["cash_weight"] == pytest.approx(
            1.0 - sum(w.values()), abs=1e-3)

    def test_per_name_cap_truncates_without_redistribution(self):
        state = _state({
            "HOT": {"status": "ok", "close": 10.0, "vol63": 0.05},
            "MEH": {"status": "ok", "close": 10.0, "vol63": 0.30},
        })
        w, receipt = policies.size_ce_kelly(
            _chosen(("HOT", 3.0), ("MEH", 0.5)), state,
            ic_prior=0.05, kelly_fraction=0.5, max_single_name=0.15)
        assert w["HOT"] == pytest.approx(0.15)
        # MEH keeps ITS kelly weight — HOT's truncated conviction became
        # cash, not a forced bet on the next name
        assert w["MEH"] == pytest.approx(0.5 * 0.05 * 0.5 / 0.30, rel=1e-6)

    def test_max_gross_scales_down_proportionally(self):
        names = {f"T{i}": {"status": "ok", "close": 10.0, "vol63": 0.05}
                 for i in range(12)}
        w, receipt = policies.size_ce_kelly(
            _chosen(*((f"T{i}", 2.0) for i in range(12))), _state(names),
            ic_prior=0.05, kelly_fraction=0.5, max_single_name=0.15)
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-6)
        assert receipt["gross"] == pytest.approx(1.0, abs=1e-3)


# ── spec refusals ───────────────────────────────────────────────────────────
class TestSpecRefusals:
    def test_ten_books_load_and_allocator_is_declared(self):
        assert len(spec_mod.active_specs()) == 9, (
            "nine ACTIVE books since PROFIT_ALLOCATOR_v1 was retired; its "
            "ledger and seed are untouched on disk")
        specs = spec_mod.load_specs()
        assert "PROFIT_ALLOCATOR_v1" in spec_mod.RETIRED
        pa = spec_mod.load_specs()["PROFIT_ALLOCATOR_v1"]
        assert pa.sizing == "ce_kelly"
        assert pa.allocator["ic_prior"] == 0.05
        assert pa.allocator["kelly_fraction"] == 0.5

    def test_ce_kelly_without_allocator_refuses(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
            "    sizing: ce_kelly\n", encoding="utf-8")
        with pytest.raises(spec_mod.SpecError):
            spec_mod.load_specs(bad)

    def test_allocator_without_ce_kelly_refuses(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
            "    sizing: equal_weight\n"
            "    allocator: {ic_prior: 0.05}\n", encoding="utf-8")
        with pytest.raises(spec_mod.SpecError):
            spec_mod.load_specs(bad)

    def test_unknown_allocator_key_refuses(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
            "    sizing: ce_kelly\n"
            "    allocator: {ic_prior: 0.05, leverage: 3.0}\n",
            encoding="utf-8")
        with pytest.raises(spec_mod.SpecError):
            spec_mod.load_specs(bad)

    def test_ce_kelly_with_winner_exemption_refuses(self, tmp_path):
        """Winner exemption renormalises to full investment — it would
        silently destroy the cash position. Refuse, don't reshape."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
            "    sizing: ce_kelly\n"
            "    allocator: {ic_prior: 0.05}\n"
            "    winner_exemption: {gain_threshold_pct: 40}\n",
            encoding="utf-8")
        with pytest.raises(spec_mod.SpecError):
            spec_mod.load_specs(bad)

    def test_allocator_shares_the_common_world(self):
        specs = spec_mod.load_specs()
        base = specs["ENGINE_BASELINE_v1"]
        pa = specs["PROFIT_ALLOCATOR_v1"]
        assert pa.cost_bps == base.cost_bps
        assert pa.slippage_bps == base.slippage_bps
        assert pa.benchmark == base.benchmark
        assert pa.min_priced_fraction == base.min_priced_fraction


# ── engine wiring: the router is CONSUMED ───────────────────────────────────
class TestDecideWiring:
    def _book(self):
        return {"positions": {}, "cash": 100000.0, "pending": [],
                "session_index": 0, "last_rebalance_month": None}

    def _rich_state(self, n=8):
        names = {f"T{i}": {"status": "ok", "close": 50.0, "vol63": 0.25,
                           "scores": {"arena_composite": float(n - i) / 2}}
                 for i in range(n)}
        return _state(names)

    def test_decision_records_router_verdict_and_throttled_kelly(self, tmp_path):
        spec = spec_mod.load_specs()["PROFIT_ALLOCATOR_v1"]
        dec = engine._decide(spec, self._book(), self._rich_state(),
                             "hash123", root=tmp_path)
        assert dec["status"] == "decided"
        rec = dec["allocator"]
        # empty arena root -> router ABSTAINs -> quarter-Kelly effective
        assert rec["router_verdict"] == "ABSTAIN"
        assert rec["kelly_declared"] == 0.5
        assert rec["kelly_used"] == pytest.approx(0.25)
        assert sum(dec["weights"].values()) <= 1.0 + 1e-9
        assert rec["cash_weight"] >= 0.0

    def test_orders_leave_the_cash_uninvested(self, tmp_path):
        spec = spec_mod.load_specs()["PROFIT_ALLOCATOR_v1"]
        book = self._book()
        dec = engine._decide(spec, book, self._rich_state(), "hash123",
                             root=tmp_path)
        buys = sum(o["usd"] for o in book["pending"] if o["side"] == "buy")
        invested = sum(dec["weights"].values())
        assert buys <= book["cash"] * invested * 1.01

    def test_non_allocator_books_carry_no_allocator_receipt(self, tmp_path):
        spec = spec_mod.active_specs()["ENGINE_BASELINE_v1"]
        dec = engine._decide(spec, self._book(), self._rich_state(),
                             "hash123", root=tmp_path)
        assert dec["status"] == "decided"
        assert "allocator" not in dec
