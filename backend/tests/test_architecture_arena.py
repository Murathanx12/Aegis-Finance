"""Offline pins for LLM-ARCHITECTURE-ARENA-1.

Everything here runs with an INJECTED caller and never touches the network, so
the whole refusal surface — which is the part that decides whether the money
bought information — is testable before a dollar is spent.

The two pins that exist because something was paid for:
  * `served_model` is read off the RESPONSE BODY and priced from it. Trusting
    the requested name voided an arm of a running trial on 2026-08-12.
  * A2 does NOT inherit the `p = 0.50` refusal. That ban is what taught the
    model to say 0.51; replacing it is the point of the arm, and a test that let
    it leak back in would silently reinstate the failure.
"""
from __future__ import annotations

import json

import pytest

from backend.services import architecture_arena as aa
from backend.services.belief_state import HORIZONS

SNAP = {
    "ticker": "TEST", "as_of": "2026-08-11", "last_close": 10.0,
    "sector": "Healthcare", "vendor_sector": "Healthcare",
    "company_name": "Test Co", "industry": "Biotechnology",
    "n_bars_available": 400,
    "trailing_return_pct": {"1d": 1.0, "5d": 2.0, "21d": -3.0},
    "realised_vol_annualised_pct": {"21d": 40.0, "63d": 38.0},
    "max_drawdown_1y_pct": -25.0, "beta_vs_benchmark": 1.1,
    "benchmark": "SPY", "benchmark_trailing_return_pct": {"21d": 1.0},
}

GOOD_FORECASTS = [
    {"observable": "return_sign", "horizon_days": 5, "probability": 0.62,
     "threshold": None, "thesis": "t", "counter_thesis": "c",
     "next_observable": "n"},
    {"observable": "abs_move_exceeds", "horizon_days": 20, "probability": 0.4,
     "threshold": 0.15, "thesis": "t", "counter_thesis": "c",
     "next_observable": "n"},
]


class FakeReply(aa.ArmReply):
    pass


def fake_caller(payloads, *, served="deepseek-v4-flash", cost=0.001):
    """A caller that returns a scripted reply per STEP, recording what it saw."""
    seen: list[dict] = []

    def call(messages, *, model="deepseek-v4-flash", arm="", item="", step="",
             max_tokens=0, **kw):
        seen.append({"arm": arm, "item": item, "step": step, "model": model,
                     "messages": messages})
        body = payloads[step] if isinstance(payloads, dict) else payloads
        if callable(body):
            body = body(len(seen) - 1)
        return aa.ArmReply(text=json.dumps(body), served_model=served,
                           requested_model=model, tokens_in=100, tokens_out=50,
                           cost_usd=cost)
    call.seen = seen                                       # type: ignore[attr-defined]
    return call


# ── the metric ──────────────────────────────────────────────────────────────

def test_effective_distinct_ideas_is_the_swarm1_implementation():
    """The number's only value is comparability to 0.2996."""
    from backend.services import llm_swarm as sw
    preds = [{"ticker": "A", "observable": "return_sign", "probability": 0.6,
              "horizon_days": 5}]
    assert aa.effective_distinct_ideas(preds) == sw.effective_distinct_ideas(preds)


def test_idea_buckets_never_cross_tickers_so_the_count_is_additive():
    """Additivity is the licence for a per-item bootstrap and a paired MDE.

    If two different securities could share a bucket, summing per-item idea
    counts would over-count and every downstream interval would be wrong in the
    reassuring direction.
    """
    f = [{"observable": "return_sign", "probability": 0.6}]
    assert not (aa._idea_keys(f, "AAA") & aa._idea_keys(f, "BBB"))


def test_arm_metrics_uses_a_ratio_of_sums_not_a_mean_of_ratios():
    rows = [
        {"arm": "X", "item": "A", "status": "ok", "n_calls": 1,
         "cost_usd": 0.001, "forecasts": [
             {"observable": "return_sign", "probability": 0.6}]},
        {"arm": "X", "item": "B", "status": "ok", "n_calls": 1,
         "cost_usd": 0.009, "forecasts": [
             {"observable": "return_sign", "probability": 0.6}]},
    ]
    m = aa.arm_metrics(rows)
    assert m["effective_distinct_ideas"] == 2
    assert m["ideas_per_usd"] == pytest.approx(2 / 0.010, rel=1e-6)
    # a mean of per-item ratios would be (1000 + 111)/2 = 555.5, which would let
    # one cheap item dominate a dollar-denominated metric
    assert m["ideas_per_usd"] != pytest.approx(555.5, rel=1e-3)


def test_bootstrap_supplies_a_threshold_and_a_dispersion():
    rows = [{"arm": "A0", "item": f"T{i}", "status": "ok", "n_calls": 1,
             "cost_usd": 0.001,
             "forecasts": [{"observable": "return_sign",
                            "probability": 0.5 + i * 0.01}]}
            for i in range(30)]
    b = aa.bootstrap_a0_dispersion(rows, n_boot=500)
    assert b["n_items"] == 30
    assert b["boot_sd"] >= 0
    assert b["threshold_point_plus_1sd"] >= b["a0_ideas_per_usd"]


def test_paired_difference_prints_its_own_mde():
    a0 = [{"arm": "A0", "item": f"T{i}", "status": "ok", "n_calls": 1,
           "cost_usd": 0.002,
           "forecasts": [{"observable": "return_sign", "probability": 0.6}]}
          for i in range(20)]
    a1 = [{"arm": "A1", "item": f"T{i}", "status": "ok", "n_calls": 7,
           "cost_usd": 0.004,
           "forecasts": [{"observable": "return_sign", "probability": 0.6}]}
          for i in range(20)]
    d = aa.paired_difference(a1, a0)
    assert d["n_paired_items"] == 20
    assert "mde_80pct_power" in d
    # A1 bought the SAME one idea for twice the money, so the difference is
    # NEGATIVE. That direction is the whole shape of the trial's risk: a
    # decomposition that costs seven calls must produce more than one extra
    # bucket per item to break even on a dollar-denominated metric.
    assert d["mean_per_item_difference"] == pytest.approx(-250.0, rel=1e-6)


# ── the refusals ────────────────────────────────────────────────────────────

def test_percent_masquerading_as_a_fraction_is_refused():
    out = aa.ArmResult(arm="X", item="T")
    bad = dict(GOOD_FORECASTS[1], threshold=15.0)
    assert aa.validate_forecast(bad, out) is None
    assert out.rejections[0]["reason"] == "threshold_not_a_fraction"


def test_a_horizon_outside_the_frozen_tuple_is_refused():
    out = aa.ArmResult(arm="X", item="T")
    bad = dict(GOOD_FORECASTS[0], horizon_days=7)
    assert 7 not in HORIZONS
    assert aa.validate_forecast(bad, out) is None
    assert out.rejections[0]["reason"] == "horizon_not_frozen"


def test_recommendation_language_is_refused():
    out = aa.ArmResult(arm="X", item="T")
    bad = dict(GOOD_FORECASTS[0], thesis="we recommend a large position")
    assert aa.validate_forecast(bad, out) is None
    assert out.rejections[0]["reason"] == "recommendation_language"


def test_coin_flip_is_refused_by_default_and_ALLOWED_in_the_a2_channel():
    """Constraint 4, executable.

    `posterior == prior` at 0.50 is A2's abstain channel and the whole reason
    the arm exists. Everywhere else the ban stands.
    """
    flip = dict(GOOD_FORECASTS[0], probability=0.50)
    banned = aa.ArmResult(arm="A1", item="T")
    assert aa.validate_forecast(flip, banned) is None
    assert banned.rejections[0]["reason"] == "coin_flip_filler"
    allowed = aa.ArmResult(arm="A2", item="T")
    assert aa.validate_forecast(flip, allowed, allow_coin_flip=True) is not None
    assert not allowed.rejections


def test_a_monoculture_batch_is_refused_whole():
    out = aa.ArmResult(arm="X", item="T")
    same = [dict(GOOD_FORECASTS[0]), dict(GOOD_FORECASTS[0], probability=0.7)]
    aa.finish(out, same)
    assert out.status == "zero_yield"
    assert any(r["reason"] == "monoculture_batch" for r in out.rejections)


# ── the arms ────────────────────────────────────────────────────────────────

def test_a1_runs_seven_separate_calls_with_seven_distinct_schemas():
    payloads = {
        "extract": {"facts": [{"fact": "f", "field": "x", "value": "1"}]},
        "novelty": {"novelty": [{"fact": "f", "novel": True, "why": "w"}]},
        "expectedness": {"expectedness": [{"fact": "f", "expected": False,
                                           "why": "w"}]},
        "propagate": {"propagation": [{"from": "f", "to": "price",
                                       "mechanism": "m", "sign": "+",
                                       "lag": "days"}]},
        "market_expectation": {"market_expects": "e", "visible_in": "v",
                               "confidence_in_reading": "medium"},
        "discrepancy": {"discrepancy": "d", "magnitude": "small",
                        "direction": "up"},
        "forecast": {"forecasts": GOOD_FORECASTS},
    }
    call = fake_caller(payloads)
    res = aa.run_a1(SNAP, caller=call)
    assert res.status == "ok"
    assert len(res.replies) == 7
    assert [s["step"] for s in call.seen] == list(aa._A1_STEPS)
    assert len({s["messages"][0]["content"] for s in call.seen}) == 7


def test_every_non_control_arm_shares_the_cached_prefix():
    """Constraint 5. Cached input is 50x cheaper than a miss, so the shared
    prefix is simultaneously the cheapest design and the correctly paired one.
    A0 is EXCLUDED because A0 must be the SWARM-1 prompt byte-for-byte."""
    systems = (list(aa._A1_SYS.values())
               + [aa._A2_PRIOR_SYS, aa._A2_POST_SYS, aa._A3_PROPOSE_SYS,
                  aa._A3_REFUTE_SYS, aa._A3_MERGE_SYS, aa._A4_SYS])
    assert all(s.startswith(aa.ARENA_PREFIX) for s in systems)


def test_a2_freezes_a_prior_that_never_sees_a_price():
    """The prior call is shown identity only. If a price leaked into it, the
    posterior would not be an update — it would be a second forecast."""
    payloads = {
        "prior": {"prior": [
            {"observable": "return_sign", "horizon_days": 5,
             "threshold": None, "probability": 0.50, "basis": "base rate"},
            {"observable": "abs_move_exceeds", "horizon_days": 20,
             "threshold": 0.15, "probability": 0.3, "basis": "vol"}]},
        "posterior": {"posterior": [
            dict(GOOD_FORECASTS[0], probability=0.50, unchanged=True,
                 moved_by="nothing", evidence_quality="none"),
            dict(GOOD_FORECASTS[1], probability=0.45, unchanged=False,
                 moved_by="21d vol", evidence_quality="weak")]},
    }
    call = fake_caller(payloads)
    res = aa.run_a2(SNAP, caller=call)
    assert res.status == "ok"
    prior_user = call.seen[0]["messages"][1]["content"]
    assert "last_close" not in prior_user
    assert "trailing_return_pct" not in prior_user
    assert "Test Co" in prior_user
    # posterior == prior survives, at exactly 0.50
    assert any(abs(f["probability"] - 0.50) < 1e-9 for f in res.forecasts)
    assert res.extra["n_posterior_equals_prior"] == 1
    assert res.extra["mean_abs_belief_update"] == pytest.approx(0.075, abs=1e-6)


def test_a3_records_an_honest_empty_when_every_claim_is_killed():
    payloads = {
        "propose": {"claim": "c", "forecasts": GOOD_FORECASTS},
        "refute": {"attacks": [{"target_index": 0, "attack": "a",
                                "severity": "fatal", "your_probability": 0.5}]},
        "merge": {"surviving": [], "killed": [
            {"observable": "return_sign", "horizon_days": 5,
             "killed_by": "base rate"}]},
    }
    res = aa.run_a3(SNAP, caller=fake_caller(payloads))
    assert res.status == "zero_yield"
    assert any(r["reason"] == "all_claims_killed" for r in res.rejections)


def test_a4_serves_tools_from_the_frozen_snapshot_and_records_the_trace():
    """Constraint 3: no tool holds a network handle, so no tool CAN answer with
    information from after the observation timestamp."""
    seq = [
        {"tool_calls": [{"tool": "prices", "args": {}},
                        {"tool": "news_search", "args": {"q": "x"}}]},
        {"forecasts": GOOD_FORECASTS, "used": ["prices"]},
    ]
    call = fake_caller(lambda i: seq[min(i, len(seq) - 1)])
    res = aa.run_a4(SNAP, caller=call, ctx=aa.ToolContext(snapshot=SNAP))
    assert res.status == "ok"
    assert [t["tool"] for t in res.trace] == ["prices", "news_search"]
    assert res.trace[0]["available"] is True
    assert res.trace[1]["available"] is False        # there is no search tool
    assert res.extra["n_tools_unavailable"] == 1


def test_no_tool_can_reach_the_network_or_a_date_after_as_of():
    """Every served field is a slice of the frozen snapshot or a static file."""
    ctx = aa.ToolContext(snapshot=SNAP, peers=[], registry=[])
    assert aa.serve_tool("prices", {}, ctx)["as_of"] == SNAP["as_of"]
    assert aa.serve_tool("peers", {}, ctx)["available"] is False
    assert aa.serve_tool("prior_experiments", {"query": "x"}, ctx)[
        "available"] is False
    assert aa.serve_tool("web_search", {}, ctx)["available"] is False


def test_a4_out_of_rounds_is_its_own_counted_reason():
    call = fake_caller(lambda i: {"tool_calls": [{"tool": "prices", "args": {}}]})
    res = aa.run_a4(SNAP, caller=call, ctx=aa.ToolContext(snapshot=SNAP),
                    max_rounds=2)
    assert res.status == "zero_yield"
    assert any(r["reason"] == "tool_budget_exhausted" for r in res.rejections)


# ── constraint 1 ────────────────────────────────────────────────────────────

def test_served_model_is_carried_and_an_alias_mismatch_is_flagged():
    r = aa.ArmReply(text="{}", served_model="deepseek-v4-flash",
                    requested_model="deepseek-reasoner")
    assert r.alias_mismatch is True
    r2 = aa.ArmReply(text="{}", served_model="deepseek-v4-pro",
                     requested_model="deepseek-v4-pro")
    assert r2.alias_mismatch is False


def test_a_cell_row_carries_served_model_and_reasoning_tokens():
    res = aa.ArmResult(arm="A1", item="TEST")
    res.replies.append(aa.ArmReply(text="{}", served_model="deepseek-v4-pro",
                                   requested_model="deepseek-v4-pro",
                                   reasoning_tokens=42, cost_usd=0.01))
    row = res.as_row()
    assert row["served_models"] == ["deepseek-v4-pro"]
    assert row["reasoning_tokens"] == 42
    assert row["cost_usd"] == 0.01


def test_minted_records_are_arm_attributed_so_forward_brier_can_slice():
    res = aa.ArmResult(arm="A2", item="TEST")
    res.forecasts = [dict(GOOD_FORECASTS[0]),
                     dict(GOOD_FORECASTS[0], horizon_days=1)]
    res.replies.append(aa.ArmReply(text="{}", served_model="deepseek-v4-flash",
                                   requested_model="deepseek-v4-flash"))
    recs = aa.mint(res, snapshot=SNAP, made_at="2026-08-12T00:00:00+00:00")
    assert len(recs) == 2
    assert recs[0].specialist == "arena_A2"
    assert recs[0].model_version == "deepseek-v4-flash"
    # P3's first grade falls on 2026-08-16 ONLY for the 1-day horizon. A run
    # whose arms never choose horizon 1 does not resolve on the 16th, and the
    # report must state the earliest date the ledger actually holds rather than
    # the earliest the horizon tuple permits.
    assert recs[1].horizon_days == 1
    assert recs[1].resolves_after == "2026-08-16"
    assert recs[0].resolves_after == "2026-08-22"       # the 5-day horizon


def test_ledger_refusals_are_surfaced_not_swallowed():
    res = aa.ArmResult(arm="A1", item="TEST")
    # threshold >= 1 is refused by make_prediction; validate_forecast would have
    # caught it first, so this pins that the LEDGER's refusal also reaches the
    # rejection pile rather than dropping a record silently.
    res.forecasts = [dict(GOOD_FORECASTS[1], threshold=9.0)]
    res.replies.append(aa.ArmReply(text="{}", served_model="x",
                                   requested_model="x"))
    recs = aa.mint(res, snapshot=SNAP)
    assert recs == []
    assert res.rejections[0]["reason"] == "ledger_refused"
