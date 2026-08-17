"""Every receipt says which version of the arms produced it, and how they failed.

WHY (Fable's sharpest catch on Order 14)
========================================
IIF-1 buys 40 nights and pools them into ONE contrast. That pooling assumes the
nights are homogeneous — same treatment, same control. Hardening
`investigator_agent`'s tool-call parsing on 2026-08-17 changed the behaviour of
the tool-USING arms mid-campaign: before it a malformed tool call killed the cell
(and cost three paired cells from every other arm), after it the call is skipped
and counted. That is a better arm and a DIFFERENT arm.

So a contrast pooled across the boundary silently mixes two versions of B, and
the only way the analysis can report within-version as well as pooled is if the
receipts say which version they came from. The fix was ordered without the stamp;
this is the stamp.

AND per-arm failure counts, on every receipt including clean nights: a failure
that can only strike tool-using arms is a bias with a DIRECTION (toward the null,
which is the direction that looks like a clean negative), not noise.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from backend.services import investigator_night as N
from backend.services import investigator_tools as IT
from backend.services.investigator_agent import FORECAST_CELLS


def _feats(z=1.0):
    return {"abs_resid_return_z_1d": z, "volume_z_20d": 0.5,
            "earnings_within_5d": False, "filing_within_2d": False,
            "price": 100.0, "dollar_volume_20d": 1e9}


class FakeReply:
    def __init__(self, text, model="deepseek-v4-flash"):
        self.text = text
        self.model_version = model
        self.tokens_in = 10
        self.tokens_out = 20
        self.latency_ms = 1.0
        self.retries = 0


def _body(system, gather):
    if "Extract what changed" in system:
        return {"what_changed": "earnings", "when": "soon",
                "who_is_affected": [], "novelty": "low",
                "expectedness": "fully_expected", "unknowns": []}
    if "prior_market_belief" in system:
        return {"prior_market_belief": "b", "what_moved_in_expectations": "m",
                "already_priced": "partly"}
    if "MAGNITUDE" in system:
        return {"forecasts": [
            {"observable": o, "horizon_days": h, "threshold": t,
             "prior": 0.20, "posterior": 0.35, "rationale": "r"}
            for o, h, t in FORECAST_CELLS]}
    if "strongest_objection" in system:
        return {"strongest_objection": "o", "contradicting_evidence": "c",
                "falsifying_check": "f", "confidence_in_chain": "low"}
    return gather


def good_llm(*, system, user, model="deepseek-v4-flash", **kw):
    return FakeReply(json.dumps(_body(system, {"calls": [], "done": True})),
                     model)


def malformed_tool_llm(*, system, user, model="deepseek-v4-flash", **kw):
    """Emits the Night 1 ICE payload on every gather call."""
    gather = {"calls": [{"tool": "search_news", "args": [[1, 2, 3]]}],
              "done": True}
    return FakeReply(json.dumps(_body(system, gather)), model)


def ok_tools(name, args, budget=None):
    if budget is not None:
        budget.take()
        r = IT.ToolResult(name, IT.STATUS_OK, payload={"h": "x"})
        budget.log.append(r.as_row())
        return r
    return IT.ToolResult(name, IT.STATUS_OK, payload={"h": "x"})


def _run(llm, tools, k=3, n=4):
    # sandbox=True is REQUIRED and is the point: injecting the LLM client and
    # overriding k are exactly what `SandboxRequired` refuses for a night that
    # could accrue. A sandbox night can never write the evidence ledger, which
    # is what makes it safe to assert receipt fields from a test.
    return N.run_night({f"T{i}": _feats(float(i)) for i in range(n)},
                       k=k, llm_call=llm, tool_runner=tools, dry_run=True,
                       sandbox=True)


# ── the implementation boundary ─────────────────────────────────────────────
def test_every_receipt_carries_the_implementation_version():
    res = _run(good_llm, ok_tools)
    assert res.implementation_version == N.IMPLEMENTATION_VERSION
    assert res.implementation_version >= 2, (
        "Night 1 ran at version 1; anything produced after the tool-call "
        "hardening must not be poolable with it unmarked")


def test_the_fingerprint_is_derived_from_the_code_not_declared():
    """A hand-maintained version integer is on the honour system.

    The person changing arm behaviour is the person who has to remember to bump
    it, so the receipt carries a DERIVED fingerprint beside the declared number.
    Two nights with the same version and different fingerprints are a forgotten
    bump — detectable after the fact instead of assumed away.
    """
    res = _run(good_llm, ok_tools)
    fp = res.arm_implementation_fingerprint
    assert fp and fp != "UNAVAILABLE"
    assert fp == N.arm_implementation_fingerprint(), "not reproducible"

    from backend.services import investigator_agent as IA
    import hashlib
    expected = hashlib.sha256(
        pathlib.Path(IA.__file__).read_bytes()).hexdigest()[:16]
    assert fp == expected, (
        "the fingerprint must be a hash of the module that DEFINES arm "
        "behaviour — otherwise it cannot differ when that behaviour differs")


def test_an_unreadable_source_refuses_rather_than_faking_a_stable_hash(
        monkeypatch):
    """A missing input must not become a value that compares equal by accident.

    A fingerprint that silently degrades to a constant would make two genuinely
    different implementations look identical, which is worse than having none.
    """
    monkeypatch.setattr(N.Path, "read_bytes",
                        lambda self: (_ for _ in ()).throw(OSError("gone")))
    assert N.arm_implementation_fingerprint() == "UNAVAILABLE"


# ── per-arm failure counts ─────────────────────────────────────────────────
def test_arm_failures_is_on_a_clean_receipt_with_zeros():
    """A field that only appears when it is bad teaches readers absence is fine.

    This count's whole value is being read on clean nights, so the drift toward
    tool-arm-only failures is caught while it is still small.
    """
    res = _run(good_llm, ok_tools)
    assert res.arm_failures, "a clean night must still report the shape"
    for arm, blk in res.arm_failures.items():
        assert blk["n_cells_failed"] == 0, arm
        assert blk["n_tool_call_drops"] == 0, arm
        assert blk["tool_call_drop_reasons"] == {}, arm
        assert "n_cells" in blk


def test_malformed_tool_calls_are_attributed_to_the_tool_arms_only():
    """The asymmetry that biases H1, made visible on the receipt.

    Every arm gets the same malformed gather reply, but only arms that MAY use
    tools ever reach the parser — so the drops land one-sided by construction.
    That is exactly why the count is per-arm rather than a night total.
    """
    res = _run(malformed_tool_llm, ok_tools)

    tool_arms = {a for a, b in res.arm_failures.items()
                 if b["n_tool_call_drops"] > 0}
    assert tool_arms, "the malformed payload produced no drops at all"
    assert "A_snapshot" not in tool_arms, (
        "the control arm recorded a tool-call drop — it cannot reach that code, "
        "so this would mean the arms are not isolated")

    for arm in tool_arms:
        assert res.arm_failures[arm]["tool_call_drop_reasons"].get(
            "args_not_a_mapping"), arm

    # And the night still completed: a malformed reply costs a lookup, not a cell.
    assert res.status == "ok", f"{res.status}: {res.void_reason}"
    for arm, blk in res.arm_failures.items():
        assert blk["n_cells_failed"] == 0, (
            f"{arm} lost a cell to a malformed tool call — that is the Night 1 "
            f"defect, and one dead cell costs three paired cells per arm")


def test_the_counts_also_live_in_per_arm_so_the_rollup_cannot_drift():
    res = _run(malformed_tool_llm, ok_tools)
    for arm, blk in res.arm_failures.items():
        assert blk["n_tool_call_drops"] == res.per_arm[arm]["n_tool_call_drops"]
        assert blk["n_cells_failed"] == res.per_arm[arm]["n_cells_failed"]
