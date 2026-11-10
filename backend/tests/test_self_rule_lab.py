"""learner.self_rule_lab: self-written rules adjudicated by held-out data.

Offline and synthetic: no ledger file, no bars file, no model call (the model
is a stub that returns a planted reply).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from learner import rule_distillation as RD
from learner import self_rule_lab as L


def _ledger(seed: int = 1) -> list[dict]:
    """Investigator: informative. `macro_rates`: anti-informative on the SAME
    questions, so down-weighting it is the right rule and the data can show it."""
    rng = np.random.default_rng(seed)
    rows = []
    start = date(2026, 8, 3)
    for d in range(0, 100, 1):
        day = start + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        for t in range(12):
            y = int(rng.random() < 0.4)
            q = {"ticker": f"T{t}", "observable": "beats_benchmark", "horizon_days": 5,
                 "threshold": None, "benchmark": "SPY",
                 "made_at": f"{day}T13:00:00+00:00",
                 "resolved_at": str(day + timedelta(days=7)), "outcome": y,
                 "void_reason": None}
            good = float(np.clip((0.65 if y else 0.25) + rng.normal(0, 0.1), 0.02, 0.98))
            bad = float(np.clip((0.3 if y else 0.7) + rng.normal(0, 0.1), 0.02, 0.98))
            rows.append({**q, "prediction_id": f"g{d}-{t}", "specialist": "investigator:D_all",
                         "probability": good, "belief_change": 0.1, "model": "m"})
            rows.append({**q, "prediction_id": f"b{d}-{t}", "specialist": "macro_rates",
                         "probability": bad, "model": "m"})
    return rows


T1, T2 = "2026-09-07", "2026-10-05"


# ---------------------------------------------------------------- schema
def test_a_condition_on_an_outcome_field_is_refused_by_name():
    for f in ("outcome", "y", "resolved_at", "realised_return", "brier"):
        rule, why = L.validate_rule({"when": [{"field": f, "op": "eq", "value": 1}],
                                     "action": {"type": "abstain"}})
        assert rule is None and why.startswith("REJECTED_LEAKED_OUTCOME_FIELD"), f


def test_schema_refusals_and_a_valid_rule():
    bad = [
        {"when": [], "action": {"type": "abstain"}},
        {"when": [{"field": "nope", "op": "eq", "value": 1}], "action": {"type": "abstain"}},
        {"when": [{"field": "family", "op": "gte", "value": 1}], "action": {"type": "abstain"}},
        {"when": [{"field": "family", "op": "eq", "value": "x"}], "action": {"type": "buy"}},
        {"when": [{"field": "family", "op": "eq", "value": "x"}],
         "action": {"type": "shrink", "lambda": 1.5}},
        {"when": [{"field": "family", "op": "eq", "value": "x"}],
         "action": {"type": "reweight", "factor": 0}},
    ]
    for b in bad:
        assert L.validate_rule(b)[0] is None, b
    ok, why = L.validate_rule({"when": [{"field": "family", "op": "eq", "value": "macro_rates"}],
                               "action": {"type": "reweight", "factor": 0.5},
                               "rule_text": "down-weight"})
    assert why is None and ok["action"] == {"type": "reweight", "factor": 0.5}
    assert len(L.rule_hash(ok)) == 16


def test_the_vectorised_mask_agrees_with_condition_holds():
    """Same semantics as the distillation's evaluator, including MISSING -> False."""
    g = pd.DataFrame({"observable": ["a", "b", None, "a"],
                      "horizon_days": [1.0, 5.0, 20.0, np.nan],
                      "family": ["x", "y", "x", "z"]})
    conds = [{"field": "observable", "op": "eq", "value": "a"},
             {"field": "observable", "op": "in", "value": ["a", "b"]},
             {"field": "horizon_days", "op": "gte", "value": 5},
             {"field": "horizon_days", "op": "between", "value": [1, 5]}]
    for c in conds:
        rows = [{k: (None if (isinstance(v, float) and np.isnan(v)) else v)
                 for k, v in r.items()} for r in g.to_dict("records")]
        expected = [RD.condition_holds(c, r) for r in rows]
        assert list(L.cond_mask(c, g)) == expected, c


# ---------------------------------------------------------------- the split
def test_the_split_embargoes_rows_that_resolve_across_a_boundary():
    g = L.frame_from_rows(_ledger())
    sp = L.split_frame(g, T1, T2)
    assert (sp.train["resolved_on"] < T1).all() and (sp.train["made_day"] < T1).all()
    assert (sp.validation["made_day"] >= T1).all() and (sp.validation["resolved_on"] < T2).all()
    assert (sp.held_out["made_day"] >= T2).all()
    assert sp.meta["n_embargoed"] > 0      # the week before each boundary is in no split
    assert (sp.meta["n_train"] + sp.meta["n_validation"] + sp.meta["n_held_out"]
            + sp.meta["n_embargoed"]) == len(g)


def test_bar_features_never_use_the_forecast_days_own_bar():
    g = L.frame_from_rows(_ledger())
    days = pd.bdate_range("2026-05-01", "2026-11-30")
    bars = pd.DataFrame([{"symbol": "T0", "date": d, "close": 100.0 + i, "volume": 1000}
                         for i, d in enumerate(days)])
    # a huge jump ON a forecast day must not be visible to that day's forecast
    jump_day = pd.Timestamp("2026-08-04")
    bars.loc[bars["date"] == jump_day, "close"] = 10_000.0
    out = L.attach_bar_features(g, bars)
    row = out[(out["ticker"] == "T0") & (out["made_day"] == "2026-08-04")].iloc[0]
    assert abs(row["mom20"]) < 0.5          # computed from bars up to 08-03 only


def test_tables_refuse_rows_from_after_t1():
    g = L.frame_from_rows(_ledger())
    sp = L.split_frame(g, T1, T2)
    t = L.train_tables(sp.train)
    L.assert_train_only(t, T1)
    leaky = L.train_tables(pd.concat([sp.train, sp.validation]))
    with pytest.raises(L.LabRefused):
        L.assert_train_only(leaky, T1)


# ---------------------------------------------------------------- actions
def test_abstain_shrink_and_reweight_do_what_they_say():
    g = L.frame_from_rows(_ledger())
    br = L.base_rates(g)
    b = L.base_rate_for(g, br)
    Q = L.questions_of(g, b)
    ab = {"when": [{"field": "family", "op": "in", "value": ["investigator", "macro_rates"]}],
          "action": {"type": "abstain"}}
    assert np.allclose(L.score_rules(g, Q, b, [ab]), Q.b)
    sh = {"when": [{"field": "family", "op": "eq", "value": "macro_rates"}],
          "action": {"type": "shrink", "lambda": 0.5}}
    w, p = L.apply_rules(g, [sh], b)
    m = (g["family"] == "macro_rates").to_numpy()
    assert np.allclose(p[m], b[m] + 0.5 * (g["p"].to_numpy()[m] - b[m]))
    assert np.allclose(p[~m], g["p"].to_numpy()[~m])
    down = {"when": [{"field": "family", "op": "eq", "value": "macro_rates"}],
            "action": {"type": "reweight", "factor": 0.25}}
    assert L.brier(L.score_rules(g, Q, b, [down]), Q.y) < L.brier(L.score_rules(g, Q, b, []), Q.y)


# ---------------------------------------------------------------- end to end
def test_the_loop_freezes_selects_and_reports_once(tmp_path):
    seen = {}

    def fake_llm(system: str, user: str) -> dict:
        seen["prompt"] = user
        reply = {"rules": [
            {"rule_text": "the anti-signal persona gets no vote",
             "when": [{"field": "family", "op": "eq", "value": "macro_rates"}],
             "action": {"type": "abstain"}},
            {"rule_text": "leaky", "when": [{"field": "outcome", "op": "eq", "value": 1}],
             "action": {"type": "abstain"}}]}
        return {"text": json.dumps(reply), "status": "OK", "cost_usd": 0.0}

    rec = L.run(_ledger(), bars=None, out_dir=tmp_path, complete_fn=fake_llm,
                n_rules=3, t1=T1, t2=T2)
    # no held-out or validation day may appear in what the model was shown
    held_days = set(L.split_frame(L.frame_from_rows(_ledger()), T1, T2).held_out["made_day"])
    assert not any(d in seen["prompt"] for d in held_days)
    assert rec["llm"]["n_valid"] == 1 and rec["llm"]["refused"][0].startswith("REJECTED_LEAKED")
    frozen = json.loads((tmp_path / "frozen_rules.json").read_text())
    assert set(frozen) == {"llm", "greedy", "random"}
    assert all(r["rule_hash"] and r["frozen_utc"] for v in frozen.values() for r in v)
    llm = rec["held_out"]["llm"]["validation_selected"]
    assert llm["n_rules"] == 1 and llm["d_brier"] < 0        # the planted true rule helps
    assert set(llm) >= {"by_month", "by_week", "leave_one_month_out_d_brier",
                        "d_brier_ci95_day_block", "non_review"}
    assert "random_control_distribution" in rec["held_out"]
    assert rec["weights"]["held_out"]["investigator_only"]["d_brier_vs_equal"] < 0
    assert rec["verdict"]["claim"].startswith("none")
    assert (tmp_path / "self_rule_lab_receipt.json").is_file()


def test_no_model_means_no_llm_source_and_says_so(tmp_path):
    rec = L.run(_ledger(), bars=None, out_dir=tmp_path, complete_fn=None, n_rules=2,
                t1=T1, t2=T2)
    assert rec["llm"] == {"called": False}
    assert "llm" not in rec["held_out"]


def test_frozen_rules_are_rescored_and_an_altered_one_is_refused(tmp_path):
    rule = {"when": [{"field": "family", "op": "eq", "value": "macro_rates"}],
            "action": {"type": "abstain"}, "rule_text": "no vote"}
    frozen = L.freeze([rule], "llm")
    rec = L.run(_ledger(), bars=None, out_dir=tmp_path, n_rules=2, t1=T1, t2=T2,
                frozen_llm=frozen)
    assert rec["llm"]["rescored_frozen"] and rec["llm"]["frozen_hashes"] == [frozen[0]["rule_hash"]]
    assert rec["held_out"]["llm"]["all_frozen"]["d_brier"] < 0
    tampered = [{**frozen[0], "action": {"type": "shrink", "lambda": 0.5}}]
    with pytest.raises(L.LabRefused):
        L.run(_ledger(), bars=None, out_dir=tmp_path / "t", n_rules=2, t1=T1, t2=T2,
              frozen_llm=tampered)


def test_the_premature_resolution_rows_are_held_out_like_the_refit_holds_them(monkeypatch):
    import hashlib as _h
    from backend.services import forecast_reputation as FR
    rows = _ledger()
    victim = rows[0]["prediction_id"]
    monkeypatch.setattr(FR, "_PREMATURE_ID_HASHES",
                        frozenset({_h.blake2b(victim.encode(), digest_size=16).digest()}))
    g = L.frame_from_rows(rows)
    assert victim not in set(g["row_id"]) and len(g) == len(rows) - 1
