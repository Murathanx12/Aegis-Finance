"""The zero-yield governor versus a microtask-chain campaign.

THE BLOCKER THESE TESTS PIN
===========================
`research_budget`'s zero-yield rule halts a campaign whose calls stop producing
gradeable output. A row is gradeable when it is schema-valid AND carries a
prediction or hypothesis id.

INTERNET-INVESTIGATOR-FWD-1 spends five calls per (arm, ticker) cell and mints
nothing until the LAST arm finishes, because the records it writes are the
cross-arm intersection and that set does not exist before then. Read per call,
every row of a night is ungradeable while the night is running — so the rule
fired at 100% zero yield after 50 calls and stopped the run. Every arm after
that point would have returned nothing, the cross-arm intersection would have
been empty, and the night would have gone VOID having spent real money.

Found by simulation during Night 1's pre-spend checks, before the first dollar.

The fix is not an exemption. A chain declares its accounting unit, its rows are
PENDING rather than dead while it runs, and every call is amended when the chain
finishes — with what it minted, or with nothing. A cell that produced nothing
still lands in the dead bucket. What is removed is only the ability to read "the
night has not finished" as "this campaign is buying tokens".
"""

from __future__ import annotations

import json

import pytest

from backend.services import investigator_night as N
from backend.services import llm_telemetry as T
from backend.services import research_budget as RB


def _row(i: int, *, chain: str | None = None, pids: list[str] | None = None,
         resolved: bool = False) -> dict:
    meta: dict = {"trial": N.TRIAL}
    if chain:
        meta.update({"yield_unit": T.YIELD_UNIT_CHAIN, "chain_id": chain})
    if resolved:
        meta["yield_resolved"] = True
    return {"call_id": f"cid-{i:04d}", "ts": "2026-08-14T12:00:00+00:00",
            "row_type": "call", "provider": "deepseek",
            "model": "deepseek-v4-flash", "purpose": N.TRIAL, "agent": N.TRIAL,
            "model_version": "deepseek-v4-flash", "tokens_in": 900,
            "tokens_out": 300, "cached_tokens": 0, "cost_usd": 0.0004,
            "schema_valid": True, "prediction_ids": list(pids or []),
            "hypothesis_ids": [], "meta": meta}


def _ledger(tmp_path, rows: list[dict]):
    p = tmp_path / "calls.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    T._PARSE_CACHE.pop(str(p.resolve()), None)
    return p


# ── the regression that would have voided Night 1 ────────────────────────────
def test_an_unfinished_chain_night_does_not_trip_the_zero_yield_gate(tmp_path):
    """60 in-flight chain calls: pending, not dead. This is the exact shape."""
    p = _ledger(tmp_path, [_row(i, chain=f"n:A:T{i // 5}") for i in range(60)])
    st = RB.check("brain_v3", path=p)
    assert st.ok, st.reason
    assert st.n_yield_pending == 60
    assert st.n_yield_resolvable == 0


def test_a_chain_that_minted_nothing_is_still_zero_yield(tmp_path):
    """The strictness is kept: resolved-and-empty is dead, and the gate fires."""
    p = _ledger(tmp_path, [_row(i, chain=f"n:A:T{i // 5}", resolved=True)
                           for i in range(60)])
    st = RB.check("brain_v3", path=p)
    assert not st.ok
    assert "zero-yield" in (st.reason or "")
    assert st.zero_yield_rate == 1.0
    assert st.n_yield_resolvable == 60


def test_a_chain_that_minted_records_is_not_zero_yield(tmp_path):
    p = _ledger(tmp_path, [_row(i, chain=f"n:A:T{i // 5}", pids=["p1"],
                                resolved=True) for i in range(60)])
    st = RB.check("brain_v3", path=p)
    assert st.ok, st.reason
    assert st.zero_yield_rate == 0.0


def test_plain_per_call_rows_are_governed_exactly_as_before(tmp_path):
    """No chain declaration, no change. The old reading is the default."""
    p = _ledger(tmp_path, [_row(i) for i in range(60)])
    st = RB.check("brain_v3", path=p)
    assert not st.ok
    assert st.zero_yield_rate == 1.0
    assert st.n_yield_pending == 0


def test_a_mixed_window_divides_by_the_resolvable_calls_only(tmp_path):
    """60 dead + 20 in flight is 100% of what is knowable, not 75%."""
    rows = [_row(i) for i in range(60)]
    rows += [_row(100 + i, chain="n:A:LATE") for i in range(20)]
    p = _ledger(tmp_path, rows)
    st = RB.check("brain_v3", path=p)
    assert st.n_yield_pending == 20
    assert st.n_yield_resolvable == 60
    assert st.zero_yield_rate == 1.0
    assert not st.ok
    assert "80 total, 20 pending" in (st.reason or "")


def test_the_minimum_sample_applies_to_the_resolvable_calls(tmp_path):
    """40 knowable calls is not yet a rate, whatever the other 40 are doing.

    The min-n exists so a handful of calls cannot condemn a campaign; counting
    pending rows toward it would restore exactly the bug this change removes,
    one line lower down.
    """
    rows = [_row(i) for i in range(40)]
    rows += [_row(100 + i, chain="n:A:LATE") for i in range(40)]
    p = _ledger(tmp_path, rows)
    st = RB.check("brain_v3", path=p)
    assert st.n_yield_resolvable == 40 < RB.RESEARCH_LLM_ZERO_YIELD_MIN_N
    assert st.ok, st.reason


# ── the amendment that resolves a chain ──────────────────────────────────────
def test_attach_outputs_resolves_a_pending_row_through_read_calls(tmp_path):
    p = _ledger(tmp_path, [_row(0, chain="n:A:AAPL")])
    assert T._yield_pending(T.read_calls(p)[0])

    T.attach_outputs("cid-0000", prediction_ids=["pred-1"], yield_resolved=True,
                     path=p)
    T._PARSE_CACHE.pop(str(p.resolve()), None)
    row = T.read_calls(p)[0]
    assert not T._yield_pending(row)
    assert row["prediction_ids"] == ["pred-1"]


def test_an_empty_resolution_still_ends_the_pending_state(tmp_path):
    """Otherwise a barren chain would sit outside the denominator forever."""
    p = _ledger(tmp_path, [_row(0, chain="n:A:AAPL")])
    T.attach_outputs("cid-0000", yield_resolved=True, path=p)
    T._PARSE_CACHE.pop(str(p.resolve()), None)
    row = T.read_calls(p)[0]
    assert not T._yield_pending(row)
    assert not T._gradeable(row)          # resolved AND barren: the dead bucket


def test_one_resolution_does_not_mark_its_neighbours(tmp_path):
    """`read_calls` hands out cached dicts; a shared meta object would leak."""
    p = _ledger(tmp_path, [_row(0, chain="n:A:AAPL"), _row(1, chain="n:A:MSFT")])
    T.attach_outputs("cid-0000", yield_resolved=True, path=p)
    T._PARSE_CACHE.pop(str(p.resolve()), None)
    rows = {r["call_id"]: r for r in T.read_calls(p)}
    assert not T._yield_pending(rows["cid-0000"])
    assert T._yield_pending(rows["cid-0001"])


# ── the runner's side ────────────────────────────────────────────────────────
def test_the_night_tags_its_rows_with_the_cell_they_belong_to(monkeypatch):
    written: list = []
    monkeypatch.setattr(T, "append", lambda rows, path=None: written.extend(rows))

    class _Reply:
        model_version, tokens_in, tokens_out = "deepseek-v4-flash", 10, 5
        cached_tokens, latency_ms, retries = 0, 1.0, 0

    chain = {"id": N.chain_id("2026-08-14", "A_snapshot", "AAPL"), "calls": {}}
    N._record_telemetry(_Reply(), model="deepseek-v4-flash", system="s",
                        user="u", chain=chain)

    assert len(written) == 1
    assert written[0].meta["yield_unit"] == T.YIELD_UNIT_CHAIN
    assert written[0].meta["chain_id"] == "2026-08-14:A_snapshot:AAPL"
    # The id is kept, because a chain that cannot name its rows cannot resolve
    # them — which is how they would stay pending forever.
    assert chain["calls"]["2026-08-14:A_snapshot:AAPL"] == [written[0].call_id]


def test_a_night_with_no_chain_context_still_records(monkeypatch):
    written: list = []
    monkeypatch.setattr(T, "append", lambda rows, path=None: written.extend(rows))

    class _Reply:
        model_version, tokens_in, tokens_out = "deepseek-v4-flash", 10, 5
        cached_tokens, latency_ms, retries = 0, 1.0, 0

    N._record_telemetry(_Reply(), model="deepseek-v4-flash", system="s",
                        user="u", chain=None)
    assert len(written) == 1
    assert "yield_unit" not in written[0].meta


def test_resolve_chain_yield_amends_every_call_of_every_cell(monkeypatch):
    seen: list[tuple] = []
    monkeypatch.setattr(T, "attach_outputs",
                        lambda cid, **kw: seen.append((cid, kw)))

    class _Rec:
        def __init__(self, arm, ticker, pid):
            self.arm, self.ticker, self.prediction_id = arm, ticker, pid

    chain = {"calls": {"2026-08-14:A:AAPL": ["c1", "c2", "c3"],
                       "2026-08-14:A:MSFT": ["c4", "c5"]}}
    out = N.resolve_chain_yield(chain, [_Rec("A", "AAPL", "p1"),
                                        _Rec("A", "AAPL", "p2")],
                                night="2026-08-14")

    assert out == {"n_chains": 2, "n_chains_minted_nothing": 1,
                   "n_calls_resolved": 5, "n_calls_in_barren_chains": 2}
    by_cid = {cid: kw for cid, kw in seen}
    assert by_cid["c1"]["prediction_ids"] == ["p1", "p2"]
    assert by_cid["c4"]["prediction_ids"] == []      # barren, and resolved
    assert all(kw["yield_resolved"] for kw in by_cid.values())


def test_a_telemetry_failure_during_resolution_does_not_lose_the_night(
        monkeypatch, caplog):
    def _boom(cid, **kw):
        raise RuntimeError("ledger is read-only")
    monkeypatch.setattr(T, "attach_outputs", _boom)

    out = N.resolve_chain_yield({"calls": {"n:A:X": ["c1"]}}, [], night="n")
    assert out["n_chains"] == 1                      # returned, not raised


# ── the ceiling has to be able to READ spend ────────────────────────────────
def test_the_nightly_ceiling_reads_the_key_the_ledger_actually_returns(tmp_path):
    """Night 1 spent $0.0665 and reported $0.00.

    `_spend_since` read `s["cost_usd"]`; `spend()` returns `total_cost_usd`.
    Nothing errored — `.get(...) or 0.0` turned the missing key into a number —
    so every ceiling check compared 0.00 + 0.05 against $12.00 and the nightly
    USD ceiling was decorative from the day it was written.
    """
    p = _ledger(tmp_path, [_row(i, pids=["p"]) for i in range(10)])
    s = T.spend(path=p)
    assert N.SPEND_KEY in s, "the constant must name a key spend() returns"
    assert s[N.SPEND_KEY] > 0


def test_a_summary_without_the_spend_key_stops_the_night(monkeypatch):
    """A default of 0.0 is what turned a typo into an unarmed ceiling."""
    monkeypatch.setattr(T, "spend", lambda **kw: {"n_calls": 5})
    with pytest.raises(N.NightlyBudgetExhausted, match="UNKNOWN, not zero"):
        N._spend_since("2026-08-14T00:00:00+00:00")


def test_spend_is_read_not_assumed(monkeypatch):
    monkeypatch.setattr(T, "spend",
                        lambda **kw: {"total_cost_usd": 3.25, "n_calls": 7})
    assert N._spend_since("2026-08-14T00:00:00+00:00") == (3.25, 7)


# ── the information guard, at the unit that can actually be barren ───────────
def _snapshot_features(n: int) -> dict:
    return {f"T{i}": {"abs_resid_return_z_1d": 4.0 + i, "volume_z_20d": 3.0,
                      "price": 50.0, "dollar_volume_20d": 5e7,
                      "earnings_within_5d": False, "filing_within_2d": False}
            for i in range(n)}


def test_consecutive_barren_cells_stop_the_night_and_void_it(monkeypatch):
    """A model that answers with nothing must not be paid for forty cells."""
    calls = {"n": 0}

    def _empty_llm(*, system, user, model="stub", temperature=0.0,
                   max_tokens=1600):
        calls["n"] += 1

        class _R:
            text = json.dumps({"forecasts": []})
            model_version, tokens_in, tokens_out = "stub", 0, 0
            cached_tokens, latency_ms, retries = 0, 0.0, 0
        return _R()

    def _tools(name, args, budget=None):
        from backend.services import investigator_tools as IT
        return IT.ToolResult(name, IT.STATUS_EMPTY)

    res = N.run_night(_snapshot_features(40), llm_call=_empty_llm,
                      tool_runner=_tools, sandbox=True, dry_run=True,
                      night="2026-08-14")

    assert res.status == "void"
    assert "information guard" in res.void_reason
    # It stopped inside the FIRST arm rather than paying for all five.
    assert len(res.per_arm) == 1
    assert res.per_arm["A_snapshot"]["n_cells"] == N.MAX_BARREN_CELLS


def test_the_guard_resets_when_a_cell_produces_forecasts(monkeypatch):
    """A run that keeps yielding is never stopped by the guard."""
    state = {"i": 0}

    def _alternating_llm(*, system, user, model="stub", temperature=0.0,
                         max_tokens=1600):
        from backend.services.investigator_agent import FORECAST_CELLS
        if "MAGNITUDE" in system:
            state["i"] += 1
            body = {"forecasts": [
                {"observable": o, "horizon_days": h, "threshold": t,
                 "prior": 0.2, "posterior": 0.2, "rationale": "r"}
                for o, h, t in FORECAST_CELLS]}
        elif "Extract what changed" in system:
            body = {"what_changed": "x", "when": "n/a", "who_is_affected": [],
                    "novelty": "low", "expectedness": "fully_expected",
                    "unknowns": []}
        elif "prior_market_belief" in system:
            body = {"prior_market_belief": "n/a",
                    "what_moved_in_expectations": "n/a", "already_priced": "n/a"}
        elif "strongest_objection" in system:
            body = {"strongest_objection": "n/a", "contradicting_evidence": "n/a",
                    "falsifying_check": "n/a", "confidence_in_chain": "low"}
        else:
            body = {"calls": [], "done": True}

        class _R:
            text = json.dumps(body)
            model_version, tokens_in, tokens_out = "stub", 0, 0
            cached_tokens, latency_ms, retries = 0, 0.0, 0
        return _R()

    def _tools(name, args, budget=None):
        from backend.services import investigator_tools as IT
        return IT.ToolResult(name, IT.STATUS_EMPTY)

    res = N.run_night(_snapshot_features(8), llm_call=_alternating_llm,
                      tool_runner=_tools, sandbox=True, dry_run=True, k=6,
                      night="2026-08-14")
    assert "information guard" not in (res.void_reason or "")
