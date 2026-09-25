"""Chunk 2 (2026-09-25): the expected-return layer.

Spec: `docs/research_notes/2026-09-25/spec_chunk2_expected_return_layer.md`,
section "Tests (write first)". Six tests, one per numbered line, plus the
receipt/ledger fields the spec binds. Offline, no broker, no LLM; dates derive
from TODAY (session protocol item 5).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.services import decision_ledger as DL
from backend.services import expected_return as ER
from backend.services import forecast_reputation as fr

TODAY = datetime.now(timezone.utc).date()
ASOF = TODAY.isoformat()


def _planted(n_dates: int, *, signal: str = "revision_flow", h: int = 21,
             n_names: int = 20, seed: int = 7) -> pd.DataFrame:
    """A graded long frame where only `signal` predicts the relative return."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_dates):
        day = (TODAY - timedelta(days=400 - d * 3)).isoformat()
        xs = {c: rng.normal(0, 0.02, n_names) for c in ER.COMPONENTS}
        rel = 0.8 * xs[signal] + rng.normal(0, 0.01, n_names)
        for c in ER.COMPONENTS:
            for i in range(n_names):
                rows.append({"component": c, "horizon": h, "date": day,
                             "ticker": f"N{i:02d}", "x": float(xs[c][i]),
                             "rel": float(rel[i])})
    return pd.DataFrame(rows)


# ── 1. a planted world: the component with signal earns the weight ──────────

def test_planted_revision_flow_dominates_after_60_dates_and_everything_is_prior_below_30():
    t = ER.component_weights(_planted(60), horizon=21)
    assert bool(t.loc["revision_flow", "graded"]) is True
    assert t.loc["revision_flow", "n_dates"] == 60
    all_awake = {c: 0.01 for c in ER.COMPONENTS}
    b = ER.blend(all_awake, t)
    w = b["weights_reputation"]
    assert w["revision_flow"] > 0.8, w
    assert w["revision_flow"] == max(w.values())
    # the equal-weight blend is ALWAYS printed beside it
    assert b["weights_equal"] == {c: pytest.approx(1 / len(ER.COMPONENTS)) for c in ER.COMPONENTS}
    assert b["er_equal"] == pytest.approx(0.01)

    # n < 30 graded DATE blocks: every component sits at the prior, not zero
    t2 = ER.component_weights(_planted(config.ER_MIN_GRADED - 1), horizon=21)
    assert not t2["graded"].any()
    b2 = ER.blend(all_awake, t2)
    assert b2["weights_reputation"] == b2["weights_equal"]
    assert all(v > 0 for v in b2["weights_reputation"].values())


# ── 2. magnitude skill never enters the direction term ──────────────────────

def _pred(ticker, arm, obs, h, p, y, made, *, rel=None, ret=None, thr=None):
    return {"ticker": ticker, "specialist": arm, "observable": obs,
            "horizon_days": h, "probability": p, "outcome": y, "made_at": made,
            "threshold": thr, "benchmark": "SPY" if obs == "beats_benchmark" else None,
            "resolution_detail": {"realised_return": ret, "vs_benchmark": rel}}


def _magnitude_world(with_direction: bool) -> list[dict]:
    rows = []
    for d in range(80):
        made = (TODAY - timedelta(days=200 - d)).isoformat() + "T12:00:00+00:00"
        for i in range(6):
            t = f"M{i}"
            big = (d + i) % 2 == 0
            move = 0.12 if big else 0.01
            # PERFECT magnitude skill
            rows.append(_pred(t, "investigator:mag", "abs_move_exceeds", 5,
                              0.9 if big else 0.1, 1 if big else 0, made,
                              ret=move if i % 3 else -move, thr=0.05))
            if with_direction:
                # NO direction skill: p is unrelated to the outcome, tilted a
                # hair the wrong way so a float-noise +1e-17 IC cannot earn weight
                p = 0.6 if i % 2 == 0 else 0.4
                rel = (0.02 if (d % 2 == 0) else -0.02) - (0.001 if p > 0.5 else -0.001)
                rows.append(_pred(t, "investigator:mag", "beats_benchmark", 5, p,
                                  1 if rel > 0 else 0, made, rel=rel))
    # today's forecasts for a name to size
    now = ASOF + "T01:00:00+00:00"
    rows.append(_pred("HOT", "investigator:mag", "abs_move_exceeds", 5, 0.9, None, now, thr=0.05))
    rows.append(_pred("COLD", "investigator:mag", "abs_move_exceeds", 5, 0.1, None, now, thr=0.05))
    if with_direction:
        rows.append(_pred("HOT", "investigator:mag", "beats_benchmark", 5, 0.6, None, now))
    return rows


@pytest.mark.parametrize("with_direction", [True, False])
def test_a_magnitude_only_arm_gets_zero_in_er_and_nonzero_in_sizing(with_direction):
    src = ER.Sources(label="test", predictions=_magnitude_world(with_direction))
    fitted = ER.fit(src, asof=ASOF)
    t5 = fitted["tables"][5]
    if with_direction:
        assert bool(t5.loc["investigator_dir", "graded"]) is True
        assert t5.loc["investigator_dir", "rep_weight"] == 0.0
    else:
        # abs_move rows NEVER become direction rows
        assert t5.loc["investigator_dir", "n_dates"] == 0
    view = ER.build(ASOF, ["HOT", "COLD"], src, fitted=fitted, write=False)
    hot = view["names"]["HOT"]["h5"]
    assert "investigator_mag" not in hot["weights_reputation"]
    assert "investigator_mag" not in hot["weights_equal"]
    assert "investigator_mag" not in hot["phi"]
    assert hot["weights_reputation"].get("investigator_dir", 0.0) == 0.0
    # ...and it DOES move sizing: the big-move name is sized down, the quiet one is not
    assert fitted["magnitude"]["lambda"] > 0
    assert view["names"]["HOT"]["size_scale_mag"] < 1.0
    assert view["names"]["COLD"]["size_scale_mag"] == pytest.approx(1.0)
    # the reputation key that made this possible
    ks = fr.magnitude_skill(fr.graded_frame_from_rows(src.predictions))
    assert list(ks.index.names) == list(fr.KEY_ARM_OBSERVABLE_HORIZON)
    assert float(ks["skill"].iloc[0]) > 0.9


# ── 3. a sleeping component is excluded, the awake weights renormalise ──────

def test_a_sleeping_component_is_excluded_and_named():
    t = ER.component_weights(_planted(60), horizon=21)
    x = {c: 0.01 for c in ER.COMPONENTS}
    x["catalyst"] = None
    x["thesis_card"] = None
    b = ER.blend(x, t, asleep_reasons={"catalyst": "no dated PDUFA inside 21 sessions"})
    assert set(b["asleep"]) == {"catalyst", "thesis_card"}
    assert b["asleep"]["catalyst"] == "no dated PDUFA inside 21 sessions"
    assert "catalyst" not in b["awake"] and "catalyst" not in b["weights_reputation"]
    assert sum(b["weights_reputation"].values()) == pytest.approx(1.0)
    assert sum(b["weights_equal"].values()) == pytest.approx(1.0)
    assert len(b["weights_equal"]) == len(ER.COMPONENTS) - 2


# ── 4. Shapley on a linear blend is exact ───────────────────────────────────

def test_shapley_sums_exactly_to_er_minus_baseline():
    t = ER.component_weights(_planted(60), horizon=21)
    x = {"ranker": 0.004, "revision_flow": 0.012, "investigator_dir": -0.003,
         "thesis_card": None, "catalyst": -0.02, "source_reliability": 0.001}
    base = {"ranker": 0.001, "revision_flow": 0.002, "investigator_dir": 0.0,
            "catalyst": -0.005, "source_reliability": 0.0}
    for scale in (1.0, 0.5):
        b = ER.blend(x, t, regime_scale=scale, baseline=base)
        for kind in ("reputation", "equal"):
            er, phi, bl = b[f"er_{kind}"], b[f"phi_{kind}"], b[f"baseline_{kind}"]
            assert sum(phi.values()) + bl == pytest.approx(er, abs=1e-15)
            assert set(phi) == set(b["awake"])


# ── 5. the PDUFA term flips sign at the break-even ──────────────────────────

def test_pdufa_term_is_negative_below_087_and_positive_above():
    be = config.ER_PDUFA_BREAKEVEN_P
    assert be == pytest.approx(0.87)
    assert ER.pdufa_term(0.86) < 0
    assert ER.pdufa_term(0.70) < 0
    assert ER.pdufa_term(0.88) > 0
    assert ER.pdufa_term(be) == pytest.approx(0.0, abs=1e-12)
    ev = [{"date": (TODAY + timedelta(days=10)).isoformat(), "ticker": "BIO",
           "kind": "pdufa", "what": "x"}]
    x, det = ER.catalyst_x("BIO", ASOF, 21, ev)
    assert x is not None and x < 0 and det["p_approval_source"] == "prior"
    x2, _ = ER.catalyst_x("BIO", ASOF, 21, ev, p_approval=0.95)
    assert x2 > 0
    # outside the horizon the component sleeps; an earnings date carries no sign
    x3, d3 = ER.catalyst_x("BIO", ASOF, 5, ev)
    assert x3 is None and "no dated PDUFA" in d3["asleep_reason"]
    x4, d4 = ER.catalyst_x("BIO", ASOF, 21, [{**ev[0], "kind": "earnings"}])
    assert x4 is None and d4["unsigned_events"]


# ── 6. u_plan: EXPLOIT waits for the blend's own grade, PROBE still places ──

def _er_sources(tmp: Path, positive: bool) -> "ER.Sources":
    rk = [{"rank": i + 1, "symbol": f"RK{i:02d}", "decile": 9,
           "expected_relative_return_21d_net": (0.01 if positive else -0.004) - i * 1e-4,
           "calibration_measured": True} for i in range(18)]
    return ER.Sources(label="test", ranking={"asof": ASOF, "top": rk},
                      decision_rows=DL.read(tmp / "ledger.jsonl"))


def _plant_blend_grade(ledger: Path, n_days: int, excess: float) -> None:
    with ledger.open("a", encoding="utf-8") as fh:
        for i in range(n_days):
            fh.write(json.dumps({
                "decision_id": f"bg{i}", "state": "SCORED",
                "asof": (TODAY - timedelta(days=90 - i)).isoformat(),
                "detail": {"horizon_sessions": config.ER_BLEND_GRADE_HORIZON,
                           "er_total": 0.01, "excess_return": excess}}) + "\n")


def test_u_plan_refuses_exploit_until_the_blend_is_graded_and_still_probes(tmp_path, monkeypatch):
    from backend.tests.test_u_plan_probe import FakeBroker, _funnel, _ranking, EQUITY
    from scripts import sim_run as S
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=+0.01)             # the ranker's own gate is OPEN

    res = S.u_plan(tmp_path / "out", "paper_profit", asof=ASOF,
                   funnel_path=tmp_path / "funnel.json",
                   ledger_path=tmp_path / "ledger.jsonl",
                   contracts_dir=tmp_path / "decisions" / "pc_plan",
                   er_sources=_er_sources(tmp_path, positive=True))
    rec = json.loads((tmp_path / "out" / "intended_book.json").read_text(encoding="utf-8"))
    assert rec["er"]["present"] is True
    assert rec["er"]["weights_source"]["h21"] == "equal"
    assert res["blend_verdict"] == "UNMEASURED"
    assert res["exploit_acting"] is False and res["n_exploit_orders"] == 0
    assert res["probe_acting"] is True and fb.submitted
    assert all(p.symbol.startswith("SL") for p in fb.submitted)
    assert rec["er_top"] and len(rec["er_top"]) <= 12
    assert rec["worst_case"]["largest_admissible_exploit"]["line"]

    # every decision row carries the decomposition the autopsy reads
    rows = json.loads((tmp_path / "decisions" / "pc_plan" / f"{ASOF}.json")
                      .read_text(encoding="utf-8"))["rows"]
    for r in rows:
        for k in DL.ER_ROW_FIELDS:
            assert k in r, k
    decided = [r for r in DL.read(tmp_path / "ledger.jsonl") if r["state"] == "DECIDED"]
    for k in DL.ER_ROW_FIELDS:
        assert k in decided[0]["detail"], k

    # the blend's own grade exists and is positive -> EXPLOIT acts, on E[r]
    _plant_blend_grade(tmp_path / "ledger.jsonl", config.ER_BLEND_GRADE_MIN_SESSIONS, +0.01)
    fb2 = FakeBroker().install(monkeypatch)
    res2 = S.u_plan(tmp_path / "out", "paper_profit", asof=ASOF,
                    funnel_path=tmp_path / "funnel.json",
                    ledger_path=tmp_path / "ledger.jsonl",
                    contracts_dir=tmp_path / "decisions" / "pc_plan",
                    er_sources=_er_sources(tmp_path, positive=True))
    assert res2["blend_verdict"] == "MEASURED_POSITIVE"
    assert res2["exploit_acting"] is True and res2["n_exploit_orders"] > 0
    ex = [p for p in fb2.submitted if p.symbol.startswith("RK")]
    assert ex and all(p.notional <= config.ER_EXPLOIT_MAX_WEIGHT * EQUITY + 1e-6 for p in ex)
    assert sum(p.notional for p in fb2.submitted) <= EQUITY + 1e-6


def test_negative_er_names_are_not_exploited_even_when_the_blend_is_graded(tmp_path, monkeypatch):
    from backend.tests.test_u_plan_probe import FakeBroker, _funnel, _ranking
    from scripts import sim_run as S
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=+0.01)
    _plant_blend_grade(tmp_path / "ledger.jsonl", config.ER_BLEND_GRADE_MIN_SESSIONS, +0.01)
    res = S.u_plan(tmp_path / "out", "paper_profit", asof=ASOF,
                   funnel_path=tmp_path / "funnel.json",
                   ledger_path=tmp_path / "ledger.jsonl",
                   contracts_dir=tmp_path / "decisions" / "pc_plan",
                   er_sources=_er_sources(tmp_path, positive=False))
    assert res["n_exploit_orders"] == 0
    assert not [p for p in fb.submitted if p.symbol.startswith("RK")]


# ── the receipt ─────────────────────────────────────────────────────────────

def test_build_writes_the_receipt_with_the_bound_fields(tmp_path):
    src = ER.Sources(label="test", ranking={"asof": ASOF, "top": [
        {"rank": 1, "symbol": "AAA", "decile": 9,
         "expected_relative_return_21d_net": 0.006, "calibration_measured": True}]})
    view = ER.build(ASOF, ["AAA", "BBB"], src, out_dir=tmp_path)
    blob = json.loads((tmp_path / f"er_{ASOF}.json").read_text(encoding="utf-8"))
    a = blob["names"]["AAA"]["h21"]
    assert a["er"] == pytest.approx(0.006) and a["components_awake"] == ["ranker"]
    assert a["weights_source"] == "equal"
    assert "oos_advantage_reputation_vs_equal" in blob["fit"]["oos"]["h21"]
    assert blob["names"]["BBB"]["h21"]["er"] is None
    assert "ranker" in blob["names"]["BBB"]["h21"]["asleep"]
    assert view["regime"]["regime"] == "unknown"
    assert ER.format_top(view, n=10).count("\n") <= 12
