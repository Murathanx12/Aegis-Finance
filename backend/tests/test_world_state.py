"""C17 -- world state, regime rows, scenarios, the dormant news wire (v2 after
the 2026-10-07 adversarial review, docs/reviews/REVIEW_2026-10-07_C17_WORLD_STATE_REGIME.md).

Offline: every model call is a fake that CAPTURES the system prompt it was sent
(memory: "a prompt that refers to a schema it never sends").
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend import config as cfg
from backend.services import belief_state as B
from backend.services import world_digest as WD
from backend.services import world_state as WS

FIXTURE = Path(__file__).parent / "fixtures" / "world_state_digest_sample.json"
NOW = datetime(2026, 10, 7, 4, 30, tzinfo=timezone.utc)


def _fx() -> tuple[list[dict], list[dict]]:
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = fx["rows"]
    themes = [dict(t, rows_idx=list(range(k * 20, k * 20 + 20))) for k, t in enumerate(fx["themes"])]
    return rows, themes


def _px(n: int = 330, end: str = "2026-10-06", seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=end, periods=n)
    cols = ["SPY", "TLT", "IEF", "HYG", "IWM", "USO", "GLD", "UUP"] + list(WS.SECTOR_ETFS)
    data = {c: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))) for c in cols}
    return pd.DataFrame(data, index=idx)


class FakeLLM:
    def __init__(self, reply: dict | str | None):
        self.reply = reply
        self.systems: list[str] = []
        self.users: list[str] = []
        self.calls = 0

    def __call__(self, system, user, *, purpose, max_tokens):
        self.calls += 1
        self.systems.append(system)
        self.users.append(user)
        text = self.reply if isinstance(self.reply, str) or self.reply is None else json.dumps(self.reply)
        return {"ok": text is not None, "text": text, "cost_usd": 0.0021, "served_model": "deepseek-flash",
                "status": "OK", "tokens_in": 900, "tokens_out": 200}


GOOD_REPLY = {"p": {v: {"h1": 0.55, "h5": 0.52} for v in WS.REGIME_VARS},
              "sectors": {e: {"h1": 0.4 + 0.02 * i, "h5": 0.45} for i, e in enumerate(WS.SECTOR_ETFS)},
              "why": "fixture"}
N_ROWS = (len(WS.REGIME_VARS) + len(WS.SECTOR_ETFS)) * len(cfg.WORLD_STATE_REGIME_HORIZONS)


# ── B1: provenance (review F9) ───────────────────────────────────────────────

def test_provenance_enum_covers_every_real_digest_row():
    rows, _ = _fx()
    seen = set()
    for r in rows:
        p = WD.row_provenance(r)
        assert p["provenance"] in WD.PROVENANCE
        assert p["provenance_author"] in WD.PROVENANCE_AUTHORS
        assert p["provenance_basis"]
        seen.add(p["provenance"])
    assert seen == set(WD.PROVENANCE)          # all five kinds occur in real rows
    tally = WS.stamp_rows(rows)
    assert sum(tally.values()) == len(rows) and all(r["provenance"] in WD.PROVENANCE for r in rows)
    assert WD.row_provenance(None)["provenance"] == "UNCLASSIFIED"


def test_fact_is_a_positive_rule_and_claims_carry_their_own_kind():
    bare = {"kind": "headline", "event_type": "other", "novelty": "new_fact", "source_kind": "news"}
    assert WD.row_provenance(bare)["provenance"] == "UNCLASSIFIED"
    actuals = {"kind": "article", "event_type": "earnings", "novelty": "new_fact", "source_kind": "news",
               "forward_claims": [{"who": "management", "direction": "up"}]}
    p = WD.row_provenance(actuals)
    assert (p["provenance"], p["provenance_basis"]) == ("FACT", "REPORTED_ACTUALS_WITH_COMPANY_OUTLOOK")
    assert WD.claim_provenance({"who": "management"}) == "COMPANY_CLAIM"
    assert WD.claim_provenance({"who": "analyst"}) == "FORECAST"
    analyst = {"kind": "headline", "event_type": "analyst_action", "novelty": "new_fact"}
    assert WD.row_provenance(analyst)["provenance"] == "INTERPRETATION"
    filing = {"kind": "article", "event_type": "other", "novelty": "new_fact",
              "url": "https://www.sec.gov/Archives/edgar/data/1/x.htm"}
    assert WD.row_provenance(filing)["provenance_basis"] == "OFFICIAL_RELEASE"
    lookalike = dict(filing, url="https://news.google.com/rss/articles/CBMsecbeaXYZ")
    assert WD.row_provenance(lookalike)["provenance"] == "UNCLASSIFIED"


def test_type_row_and_implication_stamp_provenance_in_code():
    item = WD.Item(item_id="i1", kind="article", source="wsj", url="u", title="MU guides up",
                   text="Micron MU raised guidance", first_seen_utc="2026-10-06T00:00:00Z",
                   published_utc=None, tickers_named=["MU"])
    raw = {"topic": "t", "summary": "s", "event_type": "guidance", "tickers": ["MU"],
           "novelty": "new_fact", "forward_claims": [{"subject": "demand", "direction": "up", "who": "ceo"}]}
    r = WD.type_row(raw, item)
    assert (r["provenance"], r["provenance_author"]) == ("COMPANY_CLAIM", "COMPANY")
    assert r["forward_claims"][0]["provenance"] == "COMPANY_CLAIM"
    imp = WD.type_implication({"subject": "MU", "subject_type": "ticker", "direction": "up",
                               "size_bucket": "normal", "horizon_sessions": 5, "confidence": 0.6,
                               "order": 1, "chain": "c", "contradiction": "x"}, theme_tickers={"MU"})
    assert (imp["provenance"], imp["provenance_author"]) == ("INTERPRETATION", "AEGIS")


# ── B1: beliefs (review F3) ──────────────────────────────────────────────────

def _rates_rows(day: str, n_outlets: int, tag: str = "a") -> list[dict]:
    return [{"item_id": f"{tag}{i}", "source": f"outlet{i}", "source_kind": "news", "macro": ["rates"],
             "event_type": "central_bank", "first_seen_utc": f"{day}T01:00:00+00:00"}
            for i in range(n_outlets)]


def _rates_theme(n: int, d: str, conf: float = 0.8) -> dict:
    return {"title": f"rates {d}", "rows_idx": list(range(n)),
            "implications": [{"subject": "rates", "subject_type": "macro", "direction": d,
                              "confidence": conf, "horizon_sessions": 5}]}


def test_belief_update_is_idempotent_per_digest():
    rows, themes = _fx()
    t1, rc1, lines = WS.update_beliefs(None, rows, themes, digest_id="D1", now=NOW)
    assert rc1["state"] == "UPDATED" and rc1["touched"] and lines
    assert all(ln["provenance"] == "INTERPRETATION" for ln in lines)
    t2, rc2, lines2 = WS.update_beliefs(t1, rows, themes, digest_id="D1", now=NOW + timedelta(hours=6))
    assert rc2["state"] == "ALREADY_APPLIED" and lines2 == [] and t2 == t1


def test_a_syndicated_story_is_one_vote_not_five():
    one, _, _ = WS.update_beliefs(None, _rates_rows("2026-10-06", 1), [_rates_theme(1, "up")],
                                  digest_id="A", now=NOW)
    five, _, _ = WS.update_beliefs(None, _rates_rows("2026-10-06", 5), [_rates_theme(5, "up")],
                                   digest_id="A", now=NOW)
    assert one["beliefs"]["rates"]["confidence"] == five["beliefs"]["rates"]["confidence"]
    assert five["beliefs"]["rates"]["n_root_events_this_cycle"] == 1


def test_already_applied_evidence_never_moves_a_belief_again():
    rows, themes = _fx()
    t1, _, _ = WS.update_beliefs(None, rows, themes, digest_id="D1", now=NOW)
    # the next digest 45 minutes later re-reads the SAME window (overlapping rows)
    t2, rc2, _ = WS.update_beliefs(t1, rows, themes, digest_id="D2", now=NOW + timedelta(minutes=45))
    st = rc2["stability"]
    assert st["belief_stability"] == 0.0 and st["status"] == "OK"
    for k, b in t1["beliefs"].items():
        assert t2["beliefs"][k]["direction"] == b["direction"]
        assert t2["beliefs"][k]["confidence"] <= b["confidence"] + 1e-9   # decay only


def test_beliefs_decay_by_elapsed_time_and_expire():
    t1, _, _ = WS.update_beliefs(None, _rates_rows("2026-10-06", 3), [_rates_theme(3, "up")],
                                 digest_id="A", now=NOW)
    m0 = t1["beliefs"]["rates"]["mass_up"]
    hl = cfg.WORLD_STATE_HALF_LIFE_DAYS["rates"]
    t2, rc, _ = WS.update_beliefs(t1, [], [], digest_id="B", now=NOW + timedelta(days=hl))
    assert t2["beliefs"]["rates"]["mass_up"] == pytest.approx(m0 / 2, rel=1e-3)
    assert "rates" in rc["decayed"] and "rates" in t2["unresolved_beliefs"]
    t3, rc3, _ = WS.update_beliefs(t2, [], [], digest_id="C", now=NOW + timedelta(days=40 * hl))
    assert "rates" not in t3["beliefs"] and "rates" in rc3["expired"]


def test_a_topic_with_no_evidence_is_unresolved_not_fabricated():
    rows, _ = _fx()
    t, _, _ = WS.update_beliefs(None, rows[:3], [], digest_id="D1", now=NOW)
    assert set(t["beliefs"]) | set(t["unresolved_beliefs"]) == set(WS.TOPICS)


def test_new_opposite_evidence_is_a_contradiction():
    t1, _, _ = WS.update_beliefs(None, _rates_rows("2026-10-05", 3, "a"), [_rates_theme(3, "up", 0.9)],
                                 digest_id="A", now=NOW)
    assert t1["beliefs"]["rates"]["direction"] == "up"
    t2, rc, _ = WS.update_beliefs(t1, _rates_rows("2026-10-06", 3, "b"), [_rates_theme(3, "down", 0.9)],
                                  digest_id="B", now=NOW + timedelta(hours=6))
    assert "rates" in rc["contradicted"]


def test_belief_stability_goes_degraded_above_the_max():
    prev = {"beliefs": {t: {"direction": "up"} for t in ("a", "b", "c", "d")}}
    new = {"beliefs": {t: {"direction": "down"} for t in ("a", "b", "c", "d")}}
    st = WS.belief_stability(prev, new)
    assert st["belief_stability"] == 1.0 and st["status"] == "DEGRADED"


def test_refuses_an_update_with_no_digest_id():
    with pytest.raises(WS.WorldStateRefused):
        WS.update_beliefs(None, [], [], digest_id="", now=NOW)


# ── B2: regime rows (review F1, F2, F5, F7) ──────────────────────────────────

def _table():
    return WS.update_beliefs(None, *_fx(), digest_id="D1", now=NOW)[0]


def test_regime_v1_events_and_baselines_are_in_the_captured_prompt():
    llm = FakeLLM(GOOD_REPLY)
    out = WS.run_regime(_table(), WD.Meter(0.5, llm=llm), px=_px(),
                        made_at="2026-10-06T22:30:00+00:00", digest_id="D1", preds=[])
    assert llm.calls == 1
    sent = llm.systems[0]
    for var in WS.REGIME_VARS:
        assert f'"{var}"' in sent
    for etf in WS.SECTOR_ETFS:
        assert f'"{etf}"' in sent
    assert "base_rate" in sent and "persistence" in sent
    assert '"base_rate"' in llm.users[0] and '"persistence"' in llm.users[0]
    assert out["state"] == "OK" and out["model"] == "deepseek:deepseek-flash"
    assert out["prompt_version"] == "regime_v1" == cfg.WORLD_STATE_REGIME_PROMPT_VERSION
    assert {r.model for r in out["records"]} == {"deepseek:deepseek-flash"}
    assert {r.model_version for r in out["records"]} == {"regime_v1"}


def test_regime_row_schema_and_grader_round_trip():
    px = _px()
    out = WS.run_regime(_table(), WD.Meter(0.5, llm=FakeLLM(GOOD_REPLY)), px=px,
                        made_at="2026-10-06T22:30:00+00:00", digest_id="D1", preds=[])
    recs = [asdict(r) for r in out["records"]]
    assert len(recs) == N_ROWS
    for r in recs:
        iu = r["inputs_used"]
        assert r["specialist"] == WD.REGIME_SPECIALIST and iu["provenance"] == "FORECAST"
        assert iu["entry_session"] == "2026-10-06" and iu["panel_lag_sessions"] == 0
        assert 0 < iu["baseline_base_rate_p"] < 1 and 0 < iu["baseline_persistence_p"] < 1
    stress = [r for r in recs if r["inputs_used"]["regime_variable"] == "realised_stress"]
    assert all(r["inputs_used"]["baseline_ewma_vol_p"] is not None for r in stress)
    # the graded event is fixed: P(TLT up) is the model's number, no label flip
    rd = [r for r in recs if r["inputs_used"]["regime_variable"] == "rates_down" and r["horizon_days"] == 1][0]
    assert rd["ticker"] == "TLT" and rd["raw_probability"] == pytest.approx(0.55)
    # sectors: normalised so their mean equals the mean of their base rates
    sec1 = [r for r in recs if r["inputs_used"]["regime_variable"].startswith("sector:") and r["horizon_days"] == 1]
    assert len(sec1) == 13
    assert np.mean([r["raw_probability"] for r in sec1]) == pytest.approx(
        np.mean([r["inputs_used"]["baseline_base_rate_p"] for r in sec1]), abs=2e-3)
    fut = pd.bdate_range(start="2026-10-07", periods=10)
    ext = pd.concat([px, pd.DataFrame({c: px[c].iloc[-1] * (1 + 0.01 * np.arange(1, 11))
                                       for c in px.columns}, index=fut)])
    graded = [B.resolve_one(r, ext, today=date(2026, 10, 30)) for r in recs]
    assert all(g is not None and g["outcome"] in (0, 1) for g in graded)
    g = WD.grade(graded)
    assert g["regime"]["vs_persistence"]["n_dates"] == 1 and g["regime"]["trust"] == 0.0
    assert g["regime"]["vs_ewma_vol"]["n_rows"] == 2
    assert g["direction"]["n_rows"] == 0 and g["size"]["n_rows"] == 0
    rg = WS.regime_grade(graded)
    f = rg["fields"]["growth:h1"]
    assert f["trust"] == 0.0 and f["brier_model_raw"] is not None
    assert f["nulls"]["base_rate"]["n_needed"] and "brier_ledger_shrunk_NOT_THE_GRADE" in f
    assert "N_needed" in rg["mde_line"]


def test_weekend_and_monday_writes_share_one_entry_session():
    px = _px(end="2026-10-09")                       # Friday
    llm = FakeLLM(GOOD_REPLY)
    sat = WS.run_regime(_table(), WD.Meter(0.5, llm=llm), px=px, made_at="2026-10-10T04:30:00+00:00",
                        digest_id="S", preds=[])
    assert sat["state"] == "OK" and sat["entry_session"] == "2026-10-12"
    preds = [asdict(r) for r in sat["records"]]
    for when in ("2026-10-11T10:30:00+00:00", "2026-10-12T04:30:00+00:00"):
        again = WS.run_regime(_table(), WD.Meter(0.5, llm=llm), px=px, made_at=when,
                              digest_id="X", preds=preds)
        assert again["state"] == "ALREADY_WRITTEN_FOR_ENTRY_SESSION" and not again["records"]
    assert llm.calls == 1


def test_a_stale_panel_is_refused_before_any_spend():
    llm = FakeLLM(GOOD_REPLY)
    out = WS.run_regime(_table(), WD.Meter(0.5, llm=llm), px=_px(end="2026-10-05"),
                        made_at="2026-10-06T22:30:00+00:00", digest_id="D", preds=[])
    assert out["state"].startswith("REFUSED: PANEL_STALE") and llm.calls == 0
    assert out["panel_lag_sessions"] == 1


def test_v0_rows_are_excluded_from_every_grade_by_rule():
    v0 = {"specialist": WD.REGIME_SPECIALIST, "model_version": "regime_v0", "outcome": 1,
          "probability": 0.5, "raw_probability": 0.3, "horizon_days": 1, "decision_date": "2026-10-06",
          "inputs_used": {"regime_variable": "sector_leadership", "baseline_base_rate_p": 0.59,
                          "baseline_persistence_p": 0.6}}
    g = WD.grade([v0])
    assert g["regime"]["excluded_by_rule"] == 1 and g["regime"]["vs_base_rate"]["n_rows"] == 0
    rg = WS.regime_grade([v0])
    assert rg["excluded_by_rule"] == {"v0_incoherent": 1} and rg["fields"] == {}
    assert WS.regime_existing_keys([v0]) == set()     # an excluded row never blocks a v1 row


def test_regime_baselines_are_null_with_a_reason_on_short_history():
    bl = WS.regime_baselines(_px(n=40), WS.REGIME_VARS["growth"], "SPY", 5)
    assert bl["baseline_base_rate_p"] is None and "insufficient history" in bl["baseline_note"]


def test_non_numeric_or_unknown_keys_are_dropped_not_coerced():
    assert WS.type_regime({"p": {"growth": {"h1": "high"}, "vibes": {"h1": 0.6}},
                           "sectors": {"NVDA": {"h1": 0.6}}}) == {}
    assert WS.type_regime("nonsense") == {}


def test_a_failed_regime_reply_is_a_refusal_not_a_row():
    out = WS.run_regime(_table(), WD.Meter(0.5, llm=FakeLLM(None)), px=_px(),
                        made_at="2026-10-06T22:30:00+00:00", digest_id="D1", preds=[])
    assert out["state"].startswith("REFUSED") and out["records"] == []


# ── B3: scenarios (review F8) ────────────────────────────────────────────────

def test_scenarios_seeded_sealed_and_never_for_sizing(tmp_path):
    t = _table()
    sc = WS.update_scenarios(t, now=NOW, snapshots_dir=tmp_path)
    assert 5 <= len(sc["scenarios"]) <= 10
    for s in sc["scenarios"]:
        assert "current_probability" not in s and "probability_sealed" in s
        assert s["prior_record"]["declared_by"] and s["prior_record"]["declared_at"]
        assert s["prior_record"]["prior_hash"] and s["update_log"][-1]["kind"] == "INITIAL"
        with pytest.raises(WS.ScenarioNotForSizing):
            WS.scenario_probability(s, "sizing")
        assert 0 < WS.scenario_probability(s, "display") < 1
    tags = WS.scenario_tags_for({"sector": "Semiconductors"}, sc)
    assert tags and all(t_["use"] == "LABEL_ONLY" and "%" in t_["label"] for t_ in tags)
    assert all(not isinstance(v, (int, float)) for t_ in tags for v in t_.values())


def test_scenarios_move_slowly(tmp_path):
    t = _table()
    sc0 = WS.update_scenarios(t, now=NOW, snapshots_dir=tmp_path)
    sc1 = WS.update_scenarios(t, now=NOW + timedelta(minutes=45), prev=sc0, snapshots_dir=tmp_path)
    for a, b in zip(sc0["scenarios"], sc1["scenarios"]):
        assert abs(WS.scenario_probability(a, "display") - WS.scenario_probability(b, "display")) < 0.001
    sc2 = WS.update_scenarios(t, now=NOW + timedelta(days=2), prev=sc1, snapshots_dir=tmp_path)
    for a, b in zip(sc1["scenarios"], sc2["scenarios"]):
        assert abs(WS.scenario_probability(a, "display") - WS.scenario_probability(b, "display")) \
            <= cfg.WORLD_STATE_SCENARIO_MAX_DAILY_MOVE * 2.0 + 1e-6


def test_an_owner_restatement_is_logged_as_restated(tmp_path, monkeypatch):
    t = _table()
    sc0 = WS.update_scenarios(t, now=NOW, snapshots_dir=tmp_path)
    pri = {k: dict(v) for k, v in cfg.WORLD_STATE_SCENARIO_PRIORS.items()}
    pri["us_recession_2027"].update({"prior": 0.35, "version": 2, "declared_by": "owner",
                                     "declared_at": "2026-10-08"})
    monkeypatch.setattr(cfg, "WORLD_STATE_SCENARIO_PRIORS", pri)
    sc1 = WS.update_scenarios(t, now=NOW + timedelta(hours=6), prev=sc0, snapshots_dir=tmp_path)
    rec = [s for s in sc1["scenarios"] if s["scenario_id"] == "us_recession_2027"][0]
    assert rec["update_log"][-1]["kind"] == "PRIOR_RESTATED"
    assert WS.scenario_probability(rec, "display") == pytest.approx(0.35)
    other = [s for s in sc1["scenarios"] if s["scenario_id"] == "ai_capex_supercycle_2027"][0]
    assert other["update_log"][-1]["kind"] != "PRIOR_RESTATED"


def test_a_stale_market_match_is_reported_and_not_used(tmp_path):
    (tmp_path / "2026-08-21.polymarket.jsonl").write_text(json.dumps(
        {"title": "Will China invade Taiwan by June 30, 2027?", "mid": 0.12, "liquidity": 1e5}) + "\n",
        encoding="utf-8")
    mk = WS.market_prior([["china", "taiwan", "2027"]], now=NOW, snapshots_dir=tmp_path)
    assert mk["matched"] and not mk["used"] and mk["age_days"] > 7


def test_opportunities_rows_carry_scenario_tags(monkeypatch):
    from backend.services import opportunities as OPP
    sc = WS.update_scenarios(_table(), now=NOW, snapshots_dir=Path("does-not-exist"))
    monkeypatch.setattr(WS, "load_scenarios", lambda root=None: sc)
    out = OPP.with_ages({"rows": [{"ticker": "NVDA", "sector": "Semiconductors"},
                                  {"ticker": "XYZ", "sector": None}]})
    assert out["rows"][0]["scenario_tags"] and out["rows"][1]["scenario_tags"] == []


# ── B3: the dormant news wire (review F4, F10) ───────────────────────────────

REAL_DIR_GRADE = {"n_rows": 3, "n_dates": 3, "mean_improvement": 0.01203, "se": 0.09263,
                  "posterior_mean": 0.000139, "trust": 0.0069}


def _root(tmp_path: Path, grade_dir: dict, trust_dir: float) -> Path:
    d = tmp_path / "digest"
    d.mkdir()
    (d / "world_digest_20261007T043000Z.json").write_text(json.dumps(
        {"shadow": {"trust_dir": trust_dir, "trust_size": 0.0,
                    "grade": {"direction": grade_dir, "size": {"n_dates": 0}}}}), encoding="utf-8")
    s = tmp_path / "news_digest" / "shadow"
    s.mkdir(parents=True)
    (s / "decisions.jsonl").write_text(json.dumps(
        {"signal": {"AAA": {"d": 0.8, "s": 1.0, "n": 2}, "NEW": {"d": 0.9, "s": 1.0, "n": 1}}}) + "\n",
        encoding="utf-8")
    return tmp_path


def test_key1_is_not_met_on_three_dates_and_says_how_far():
    k = WS.key1_arm(REAL_DIR_GRADE, "direction")
    assert not k["met"] and 450 <= k["n_mde"] <= 560
    assert k["line"].startswith("direction NOT MET (n 3 of ~")


def test_flag_off_changes_no_target_weight_byte_identical(tmp_path, monkeypatch):
    big = {"n_dates": 900, "se": 0.0001, "posterior_mean": 0.004, "trust": 0.2}
    root = _root(tmp_path, big, 0.2)      # a digest that WOULD tilt if the flag were on
    w = {"AAA": 0.05, "BBB": 0.05, "CCC": 0.02}
    before = json.dumps(w, sort_keys=True)
    off = WS.plan_news_tilt(w, enabled=False, root=root)
    assert off["weights"] is w and json.dumps(off["weights"], sort_keys=True) == before
    assert off["applied"] is False and "applied=False" in off["line"]
    assert cfg.NEWS_TILT_IN_PLAN is False
    monkeypatch.setattr(WD, "optimus", lambda: root)
    targets = [SimpleNamespace(symbol=k, weight=v) for k, v in w.items()]
    import scripts.sim_run as SR
    res = SR._plan_news_tilt(targets, sandbox=False)
    assert res["applied"] is False and {t.symbol: t.weight for t in targets} == w


def test_flag_on_with_key1_failing_is_still_identity(tmp_path):
    root = _root(tmp_path, REAL_DIR_GRADE, 0.0069)
    w = {"AAA": 0.05, "BBB": 0.05}
    on = WS.plan_news_tilt(w, enabled=True, root=root)
    assert on["weights"] is w and on["applied"] is False and on["trust_dir_usable"] == 0.0
    assert "key 1: NOT MET (direction NOT MET (n 3 of ~" in on["line"]


def test_flag_on_with_key1_met_tilts_without_new_names_or_more_gross(tmp_path):
    big = {"n_dates": 900, "se": 0.0001, "posterior_mean": 0.004, "trust": 0.2}
    root = _root(tmp_path, big, 0.2)
    w = {"AAA": 0.05, "BBB": 0.05, "CCC": 0.02}
    on = WS.plan_news_tilt(w, enabled=True, root=root)
    assert on["applied"] and set(on["weights"]) == set(w)
    assert sum(on["weights"].values()) <= sum(w.values()) + 1e-12
    assert max(on["weights"].values()) <= max(w.values()) + 1e-12


def test_the_flag_needs_two_keys_and_names_the_missing_one():
    st = WS.two_key_state({"grade": {"direction": REAL_DIR_GRADE}}, {"n_sessions": 0})
    assert not st["ready_for_owner"] and len(st["missing"]) == 2
    assert "0/20 PC-plan regret sessions" in st["line2"]
    big = {"n_dates": 900, "se": 0.0001, "posterior_mean": 0.004, "trust": 0.2}
    st = WS.two_key_state({"grade": {"direction": big}},
                          {"n_sessions": 30, "mean_bps": 5.0, "sd_bps": 2.0})
    assert st["ready_for_owner"] and st["missing"] == []


def test_run_cycle_writes_receipts_and_survives_a_dead_model(tmp_path):
    rows, themes = _fx()
    calls: list = []
    rc = WS.run_cycle(rows, themes, digest_id="20261007T043000Z", now=NOW,
                      meter=WD.Meter(0.5, llm=FakeLLM(None)), px=_px(), preds=[],
                      write=True, append_records=calls.append, root=tmp_path)
    assert rc["beliefs"]["state"] == "UPDATED" and "belief_stability" in rc
    assert rc["regime"]["state"].startswith("REFUSED") and calls == []
    assert (tmp_path / "world_state" / "beliefs.json").exists()
    assert (tmp_path / "world_state" / "scenarios.json").exists()
    assert (tmp_path / "digest" / "world_state_20261007T043000Z.json").exists()
    assert rc["cost_line"].startswith("world state $0.0000")
