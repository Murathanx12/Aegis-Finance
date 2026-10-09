"""The plan reads what the night learned -- preferences only (2026-09-27).

Review 2026-09-26 item 7 / roadmap Lane R: `policy_state.json` was refreshed
every night and nothing on the paper-decision path read it. These tests pin:

* the PROBE ORDER follows reputation-weighted E[r] when the state is fresh, and
  is the old shortlist order when it is stale / missing / unparseable;
* the PROBE WEIGHTING stays `equal` while the three twins are immature and
  flips only past the declared margin;
* PROBE_MAX_WEIGHT and PROBE_GROSS_CAP never move, whatever the state says;
* the plan receipt names the learning it used (or why it ignored it);
* the `policy_state` health probe is STALE while the learning is write-only.

Offline. Every date derives from TODAY (session protocol item 5).
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from backend import config
from backend.services import expected_return as ER
from backend.services import policy_state as PS
from backend.services import system_health as SH
from backend.tests.test_u_plan_probe import (ASOF, EQUITY, FakeBroker, _funnel,
                                             _ranking)
from scripts import sim_run as S

TODAY = date.fromisoformat(ASOF)


def _weekdays_back(n: int) -> str:
    d = TODAY
    while n > 0:
        d -= timedelta(days=1)
        n -= d.weekday() < 5
    return d.isoformat()


def _state(tmp: Path, *, rep_date: str | None = ASOF, weighting: str = "equal",
           rep_w: dict | None = None, extra_values: dict | None = None) -> Path:
    values = {**PS.defaults(),
              "reputation_weights": rep_w if rep_w is not None else
              {"investigator:D_all": 0.42, "macro_rates": 0.0},
              "probe_weighting": weighting, **(extra_values or {})}
    p = tmp / "policy_state.json"
    p.write_text(json.dumps({
        "receipt": "policy_state", "values": values,
        "refreshed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {"reputation_date": rep_date, "reputation_receipt": "rep.json"},
        "probe_weighting": {"value": weighting, "reason": "test", "evidence": {}}}),
        encoding="utf-8")
    return p


def _lb(sessions: int, nets: dict[str, float] | None = None) -> dict:
    nets = nets or {"equal": 0.0, "inverse_vol": 0.0, "bigmove_tilt": 0.0}
    return {"schema": "llm_portfolio/1", "kind": "leaderboard",
            "graded_utc": f"{ASOF}T04:53:14+00:00", "bars_through": ASOF,
            "grades": [
                {"name": PS.PROBE_TWIN_BOOKS[k], "status": "OK", "benchmark": "SPY",
                 "benchmark_missing": False, "weight_priced": 1.0,
                 "weight_waiting_in_cash": 0.0,
                 "entry_session": _weekdays_back(sessions - 1),
                 "to_date": {"status": "OK", "sessions": sessions, "net": nets[k],
                             "benchmark_return": 0.0, "vs_benchmark": nets[k],
                             "weight_priced": 1.0, "as_of": ASOF}}
                for k in PS.PROBE_TWIN_BOOKS]}


# ─────────────────────────────── the weighting preference ───────────────────

def test_weighting_stays_equal_while_twins_are_immature():
    r = PS.probe_weighting_from_twins(
        _lb(20, {"equal": 0.0, "inverse_vol": 0.0, "bigmove_tilt": 0.50}))
    assert r["value"] == "equal"
    assert r["reason"].startswith("twins immature (20 sessions")


def test_weighting_reads_nested_producer_grade_at_nine_sessions():
    r = PS.probe_weighting_from_twins(
        _lb(9, {"equal": 0.0, "inverse_vol": 0.0, "bigmove_tilt": 0.50}))
    assert r["value"] == "equal"
    assert "twins immature (9 sessions" in r["reason"]
    assert {row["sessions"] for row in r["evidence"]["by_scheme"].values()} == {9}
    assert {row["weight_priced"] for row in r["evidence"]["by_scheme"].values()} == {1.0}


@pytest.mark.parametrize("mutation,reason", [
    (lambda lb: lb["grades"].append(copy.deepcopy(lb["grades"][0])), "expected one grade"),
    (lambda lb: lb["grades"][0]["to_date"].update(net=float("nan")), "invalid net"),
    (lambda lb: lb["grades"][0]["to_date"].update(net=float("inf")), "invalid net"),
    (lambda lb: lb["grades"][0]["to_date"].update(sessions=True), "invalid sessions"),
    (lambda lb: lb["grades"][0]["to_date"].update(vs_benchmark=None),
     "invalid vs_benchmark"),
    (lambda lb: lb["grades"][0]["to_date"].update(status="PENDING"), "not graded OK"),
    (lambda lb: lb["grades"][0].update(status="PENDING"), "not graded OK"),
    (lambda lb: lb["grades"][0]["to_date"].update(
        as_of=(TODAY - timedelta(days=1)).isoformat()),
     "unequal evaluation window"),
    (lambda lb: lb["grades"][0].update(entry_session=_weekdays_back(25)),
     "unequal evaluation window"),
    (lambda lb: lb["grades"][0]["to_date"].update(sessions=22),
     "unequal evaluation window"),
    (lambda lb: lb["grades"][0].update(benchmark="USMV"),
     "unequal evaluation window"),
    (lambda lb: lb["grades"][1].update(weight_priced=0.8,
                                           weight_waiting_in_cash=0.2),
     "incomplete price coverage"),
    (lambda lb: lb["grades"][1].pop("weight_priced"), "incomplete price coverage"),
    (lambda lb: lb["grades"][1]["to_date"].pop("weight_priced"),
     "incomplete price coverage"),
    (lambda lb: lb["grades"][1].update(benchmark_missing=True),
     "benchmark missing"),
    (lambda lb: lb["grades"][1].pop("benchmark_missing"),
     "benchmark missing"),
    (lambda lb: lb["grades"][1]["to_date"].pop("benchmark_return"),
     "invalid benchmark_return"),
    (lambda lb: lb["grades"][1]["to_date"].update(benchmark_return=0.30),
     "net/benchmark excess inconsistent"),
    (lambda lb: lb["grades"][1]["to_date"].update(vs_benchmark=0.99),
     "net/benchmark excess inconsistent"),
    (lambda lb: lb["grades"][1].update(sessions=9),
     "conflicting top-level sessions"),
    (lambda lb: lb["grades"][1].update(net_to_date=-0.2),
     "conflicting top-level net_to_date"),
    (lambda lb: lb["grades"].pop(), "expected one grade"),
    (lambda lb: lb.update(schema="unknown"), "unsupported leaderboard schema"),
])
def test_weighting_defaults_explicitly_on_invalid_producer_grade(mutation, reason):
    lb = _lb(21, {"equal": 0.0, "inverse_vol": 0.05, "bigmove_tilt": 0.0})
    mutation(lb)
    r = PS.probe_weighting_from_twins(lb)
    assert r["value"] == "equal"
    assert reason in r["reason"]
    assert "leader" not in r["evidence"]


def test_weighting_refuses_unequal_benchmark_returns_even_when_excess_is_coherent():
    lb = _lb(21, {"equal": 0.0, "inverse_vol": 0.05, "bigmove_tilt": 0.0})
    td = lb["grades"][1]["to_date"]
    td["benchmark_return"] = 0.01
    td["vs_benchmark"] = td["net"] - td["benchmark_return"]
    r = PS.probe_weighting_from_twins(lb)
    assert r["value"] == "equal"
    assert "unequal benchmark return" in r["reason"]


def test_weighting_stays_equal_when_a_twin_is_missing_or_unreadable(tmp_path):
    lb = _lb(30, {"equal": 0.0, "inverse_vol": 0.2, "bigmove_tilt": 0.0})
    lb["grades"] = lb["grades"][1:]
    assert PS.probe_weighting_from_twins(lb)["value"] == "equal"
    r = PS.probe_weighting_from_twins(tmp_path / "nope.json")
    assert r["value"] == "equal" and r["reason"].startswith("twins unreadable")


def test_weighting_flips_only_past_the_declared_margin():
    m = PS.PROBE_TWIN_MARGIN
    below = PS.probe_weighting_from_twins(
        _lb(21, {"equal": 0.0, "inverse_vol": m * 0.9, "bigmove_tilt": -0.01}))
    assert below["value"] == "equal" and "declared margin" in below["reason"]
    above = PS.probe_weighting_from_twins(
        _lb(21, {"equal": 0.0, "inverse_vol": m * 1.1, "bigmove_tilt": -0.01}))
    assert above["value"] == "inverse_vol"
    assert above["evidence"]["leader_gap"] == pytest.approx(m * 1.1)


@pytest.fixture()
def ps_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "LEARNED_RULES", tmp_path / "no_rules.jsonl")
    monkeypatch.setattr(PS, "STATE_PATH", tmp_path / "policy_state.json")
    monkeypatch.setattr(PS, "JOURNAL_PATH", tmp_path / "policy_journal.jsonl")
    monkeypatch.setattr(PS, "LEADERBOARD_DIR", tmp_path / "no_leaderboards")
    return tmp_path


GATE = {"verdict": "UNMEASURED_TRADE_SMALL"}
REC = {"status": "OK", "date": ASOF, "arms": [
    {"arm": "investigator:D_all", "weight": 0.42, "skill": 0.06, "n": 468}]}


def test_refresh_writes_the_weighting_and_journals_a_flip(ps_paths):
    s = PS.refresh(REC, receipt_path="r.json", persona_receipt="s", probe_gate=GATE)
    assert s["values"]["probe_weighting"] == "equal"
    assert s["probe_weighting"]["reason"].startswith("twins unreadable")
    assert "probe_weighting" not in s["changed_since_last"]
    s = PS.refresh(REC, receipt_path="r.json", persona_receipt="s", probe_gate=GATE,
                   twin_leaderboard=_lb(25, {"equal": 0.0, "inverse_vol": 0.0,
                                             "bigmove_tilt": 0.05}))
    assert s["values"]["probe_weighting"] == "bigmove_tilt"
    assert s["changed_since_last"] == ["probe_weighting"]
    j = [json.loads(x) for x in PS.JOURNAL_PATH.read_text(encoding="utf-8").splitlines()]
    assert j[-1]["key"] == "probe_weighting" and j[-1]["old"] == "equal"
    assert j[-1]["evidence"]["by_scheme"]["bigmove_tilt"]["sessions"] == 25
    with pytest.raises(PS.PolicyRefused):
        PS._check("probe_weighting", "leverage_2x")


def test_a_refresh_without_a_receipt_keeps_the_weights_dated_by_their_receipt(ps_paths):
    PS.refresh(REC, receipt_path="r.json", persona_receipt="s", probe_gate=GATE)
    s = PS.refresh(None, probe_gate=GATE)
    assert s["observed"]["status"] == "NO_RECEIPT"
    assert s["sources"]["reputation_date"] == ASOF
    assert s["sources"]["reputation_carried_from_previous"] is True
    assert s["values"]["reputation_weights"] == {"investigator:D_all": 0.42}


# ─────────────────────────────── freshness: stale is UNKNOWN ────────────────

def test_plan_view_uses_a_fresh_state_and_ignores_every_other_kind(tmp_path):
    v = PS.plan_view(ASOF, path=_state(tmp_path))
    assert v["use"] and v["used"]["reputation_arms_with_weight"] == ["investigator:D_all"]
    assert v["used"]["age_sessions"] == 0

    v = PS.plan_view(ASOF, path=_state(tmp_path, rep_date=_weekdays_back(5)))
    assert not v["use"] and v["ignored"]["reason"].startswith("stale:")
    v = PS.plan_view(ASOF, path=_state(tmp_path, rep_date=None))
    assert not v["use"] and "undateable" in v["ignored"]["reason"]
    v = PS.plan_view(ASOF, path=tmp_path / "absent.json")
    assert not v["use"] and v["ignored"]["reason"].startswith("missing")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    v = PS.plan_view(ASOF, path=bad)
    assert not v["use"] and v["ignored"]["reason"].startswith("unparseable")
    v = PS.plan_view(ASOF, path=_state(tmp_path, rep_w={"macro_rates": 0.0}))
    assert not v["use"] and "weight > 0" in v["ignored"]["reason"]


# ─────────────────────────────── the order ──────────────────────────────────

def _cell(x: dict, w: dict) -> dict:
    return {"x": x, "weights_reputation": w}


def test_only_components_whose_arm_has_weight_contribute():
    rep = {"investigator:D_all": 0.4, "thesis_card:v1": 0.0}
    er, used = PS.reputation_er(_cell({"investigator_dir": 0.02, "thesis_card": 0.5},
                                      {"investigator_dir": 0.5, "thesis_card": 0.5}), rep)
    assert used == ["investigator_dir"] and er == pytest.approx(0.01)
    er, used = PS.reputation_er(_cell({"thesis_card": 0.5}, {"thesis_card": 1.0}), rep)
    assert er is None and used == []
    er, used = PS.reputation_er(_cell({"ranker": 0.01}, {"ranker": 0.0}), rep)
    assert er is None


def test_unpriced_names_keep_shortlist_order_after_priced_ones_and_ties_go_to_the_vol_prior():
    rows = [{"ticker": t} for t in ("A", "B", "C", "D")]
    view = {"names": {"C": {"h5": _cell({"investigator_dir": 0.01}, {"investigator_dir": 1.0})},
                      "D": {"h5": _cell({"investigator_dir": 0.01}, {"investigator_dir": 1.0})}}}
    out, meta = PS.probe_order(rows, view, {"investigator:D_all": 1.0},
                               sigma={"A": .01, "B": .01, "C": .01, "D": .03})
    assert [r["ticker"] for r in out] == ["D", "C", "A", "B"]
    assert meta["changed"] and meta["n_priced"] == 2


# ─────────────────────────────── caps never move ────────────────────────────

@pytest.mark.parametrize("scheme", ["equal", "inverse_vol", "bigmove_tilt"])
def test_probe_weights_never_exceed_either_cap(scheme):
    rng = np.random.default_rng(7)
    for _ in range(200):
        n = int(rng.integers(1, 16))
        cap, gross = float(rng.uniform(0.005, 0.05)), float(rng.uniform(0.02, 0.3))
        tick = [f"T{i}" for i in range(n)]
        sig = {t: float(rng.uniform(0.002, 0.2)) for t in tick}
        w, meta = PS.probe_weights(tick, sig, scheme, max_weight=cap, gross_cap=gross)
        assert max(w.values()) <= cap + 1e-12
        assert sum(w.values()) <= gross + 1e-9
        assert sum(w.values()) <= min(cap, gross / n) * n + 1e-9, "a shape may only shrink gross"
    w, meta = PS.probe_weights(["A", "B"], {"A": 0.0, "B": 0.1}, "inverse_vol",
                               max_weight=0.02, gross_cap=0.2)
    assert meta["applied"] == "equal" and meta["fallback_why"] == "a name has no sigma"


def _run(tmp: Path, state: Path | None) -> dict:
    return S.u_plan(tmp / "out", "paper_profit", asof=ASOF,
                    funnel_path=tmp / "funnel.json", ledger_path=tmp / "ledger.jsonl",
                    contracts_dir=tmp / "decisions" / "pc_plan", policy_state_path=state)


def _receipt(tmp: Path) -> dict:
    return json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8"))


@pytest.fixture()
def reputation_says_sl07(monkeypatch):
    """The real sandbox E[r] view, with SL07 carrying a positive investigator
    direction read at h=5 -- the only name any component prices."""
    orig = ER.build

    def build(*a, **k):
        v = orig(*a, **k)
        cell = v["names"]["SL07"]["h5"]
        cell["x"] = {"investigator_dir": 0.03}
        cell["weights_reputation"] = {"investigator_dir": 1.0}
        return v
    monkeypatch.setattr(ER, "build", build)


def test_the_order_follows_reputation_when_the_state_is_fresh(tmp_path, monkeypatch,
                                                             reputation_says_sl07):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path, _state(tmp_path))
    assert res["policy_state_used"] is True
    assert fb.submitted[0].symbol == "SL07"
    rec = _receipt(tmp_path)
    used = rec["policy_state_used"]
    assert used["age_sessions"] == 0 and used["probe_weighting"] == "equal"
    assert used["reputation_arms_with_weight"] == ["investigator:D_all"]
    assert used["order_source"].startswith("reputation-weighted E[r_5]")
    assert used["generated_at"]
    assert "policy_state_ignored" not in rec
    assert list(rec["probe_order"])[0] == "SL07"


def test_the_order_is_unchanged_when_the_state_is_stale(tmp_path, monkeypatch,
                                                        reputation_says_sl07):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path, _state(tmp_path, rep_date=_weekdays_back(6)))
    assert res["policy_state_used"] is False
    assert res["policy_state_ignored"].startswith("stale:")
    assert [p.symbol for p in fb.submitted] == [f"SL{i:02d}" for i in range(10)]
    rec = _receipt(tmp_path)
    assert "policy_state_used" not in rec
    assert rec["policy_state_ignored"]["order_source"].startswith("shortlist order (policy_state ignored")


def test_a_sandbox_caller_never_reads_this_machines_state(tmp_path, monkeypatch):
    FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path, None)
    assert res["policy_state_ignored"] == "sandbox caller named no policy_state_path"


def test_no_policy_value_moves_a_cap(tmp_path, monkeypatch):
    """A matured tilt plus every cap-shaped key a night might smuggle in."""
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    st = _state(tmp_path, weighting="bigmove_tilt", extra_values={
        "PROBE_MAX_WEIGHT": 0.5, "PROBE_GROSS_CAP": 1.0, "probe_gross_cap": 1.0,
        "MAX_NAME_FRAC": 1.0, "book_size": 40})
    res = _run(tmp_path, st)
    assert res["probe_weighting"] == "bigmove_tilt"
    cap = config.PROBE_MAX_WEIGHT * EQUITY
    assert len(fb.submitted) <= config.PROBE_MAX_NAMES
    assert all(p.notional <= cap + 1e-6 for p in fb.submitted)
    assert sum(p.notional for p in fb.submitted) <= config.PROBE_GROSS_CAP * EQUITY + 1e-6
    rec = _receipt(tmp_path)
    w = rec["probe_weights"]
    assert len(set(round(v, 10) for v in w.values())) > 1, "the tilt was applied"
    assert max(w.values()) <= config.PROBE_MAX_WEIGHT + 1e-12
    assert rec["probe_gross"] <= config.PROBE_GROSS_CAP + 1e-9
    assert config.PROBE_MAX_WEIGHT == 0.02 and config.PROBE_GROSS_CAP == 0.20


# ─────────────────────────────── the health probe ───────────────────────────

def _ctx(tmp: Path) -> SH.ProbeCtx:
    od = tmp / "optimus"
    od.mkdir(exist_ok=True)
    return SH.ProbeCtx(optimus_dir=od, now=datetime.now(timezone.utc), repo=tmp,
                       allow_proc=False)


def _plan_row(tmp: Path, asof: str, **fields) -> None:
    day = tmp / "optimus" / "pc_book" / asof
    day.mkdir(parents=True, exist_ok=True)
    row = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "asof": asof, "verdict": "MEASURED_NEGATIVE", **fields}
    with (day / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def test_probe_alive_only_when_a_recent_plan_read_the_state(tmp_path):
    ctx = _ctx(tmp_path)
    last = SH.last_closed_session(ctx.now).isoformat()
    assert SH.p_policy_state(ctx).verdict == "UNKNOWN"          # no evidence at all
    (tmp_path / "optimus" / "pc_book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "optimus" / "pc_book" / "policy_state.json").write_text(json.dumps(
        {"refreshed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
        encoding="utf-8")
    r = SH.p_policy_state(ctx)
    assert r.verdict == "STALE" and r.detail.startswith("WRITE-ONLY")   # written, never read
    _plan_row(tmp_path, last, policy_state_ignored={"reason": "stale: 5 sessions old"})
    r = SH.p_policy_state(ctx)
    assert r.verdict == "STALE" and "stale: 5 sessions old" in r.detail
    _plan_row(tmp_path, last, policy_state_used={"age_sessions": 1, "order_source": "x",
                                                 "probe_weighting": "equal"})
    assert SH.p_policy_state(ctx).verdict == "ALIVE"


def test_probe_stale_when_the_only_reading_plan_is_old(tmp_path):
    ctx = _ctx(tmp_path)
    last = SH.last_closed_session(ctx.now)
    old = last - timedelta(days=10)
    _plan_row(tmp_path, old.isoformat(), policy_state_used={"age_sessions": 0})
    (tmp_path / "optimus" / "pc_book" / "policy_state.json").write_text(json.dumps(
        {"refreshed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
        encoding="utf-8")
    r = SH.p_policy_state(ctx)
    assert r.verdict == "STALE" and "WRITE-ONLY" in r.detail


# ─────────────────────── adversarial / broken state files (2026-09-27) ─────

@pytest.mark.parametrize("bad_w", [5.0, -0.3, float("nan"), float("inf")])
def test_an_out_of_range_reputation_weight_is_ignored_by_name(tmp_path, bad_w):
    """5.0, a negative, NaN or inf in the state is REFUSED by the schema, and
    the plan says so -- it never becomes a bigger vote or a bigger weight."""
    st = _state(tmp_path, rep_w={"investigator:D_all": bad_w, "macro_rates": 0.0})
    v = PS.plan_view(ASOF, path=st)
    assert not v["use"]
    assert v["ignored"]["reason"].startswith("unparseable: REFUSED")


def test_a_zero_byte_state_is_ignored_by_name(tmp_path):
    p = tmp_path / "policy_state.json"
    p.write_bytes(b"")
    v = PS.plan_view(ASOF, path=p)
    assert not v["use"] and v["ignored"]["reason"].startswith("unparseable")


@pytest.mark.parametrize("pw", [5.0, "leverage_2x", None, -1])
def test_a_weighting_that_is_not_a_declared_shape_falls_back_to_equal(tmp_path, pw):
    st = _state(tmp_path)
    raw = json.loads(st.read_text(encoding="utf-8"))
    raw["probe_weighting"]["value"] = pw
    st.write_text(json.dumps(raw), encoding="utf-8")
    v = PS.plan_view(ASOF, path=st)
    assert v["use"] and v["used"]["probe_weighting"] == "equal"


@pytest.mark.parametrize("sig", [float("nan"), float("inf"), -0.01, None])
def test_a_broken_sigma_falls_back_to_equal_weights(sig):
    for scheme in ("inverse_vol", "bigmove_tilt"):
        w, meta = PS.probe_weights(["A", "B", "C"], {"A": 0.02, "B": sig, "C": 0.03},
                                   scheme, max_weight=0.02, gross_cap=0.20)
        assert meta["applied"] == "equal"
        assert set(w.values()) == {0.02}


def test_the_admissible_worst_case_bounds_every_shape():
    """Protocol item 4: `n_max x w_max x k*max(sigma)` (what the receipt prints
    as the largest admissible PROBE book) bounds sum_i w_i * k*sigma_i under
    every weighting -- a shape can move loss between names, never past it."""
    rng = np.random.default_rng(11)
    cap, gross, n_max = config.PROBE_MAX_WEIGHT, config.PROBE_GROSS_CAP, config.PROBE_MAX_NAMES
    w_max = min(cap, gross / n_max)
    for _ in range(300):
        n = int(rng.integers(1, n_max + 1))
        tick = [f"T{i}" for i in range(n)]
        sig = {t: float(rng.uniform(0.005, 0.12)) for t in tick}
        bound = n_max * w_max * max(sig.values())
        for scheme in ("equal", "inverse_vol", "bigmove_tilt"):
            w, _ = PS.probe_weights(tick, sig, scheme, max_weight=cap, gross_cap=gross)
            assert sum(w[t] * sig[t] for t in tick) <= bound + 1e-12
            assert sum(w.values()) <= gross + 1e-9


def test_adversarial_state_gives_the_old_book(tmp_path, monkeypatch, reputation_says_sl07):
    """Weights of 5.0 / negative / NaN plus smuggled cap keys: the plan ignores
    the state by name and the book is the pre-2026-09-27 book exactly."""
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    st = _state(tmp_path, weighting="bigmove_tilt",
                rep_w={"investigator:D_all": 5.0, "macro_rates": -1.0,
                       "skeptic": float("nan")},
                extra_values={"PROBE_GROSS_CAP": 1.0, "PROBE_MAX_WEIGHT": 0.5})
    res = _run(tmp_path, st)
    assert res["policy_state_used"] is False
    assert res["policy_state_ignored"].startswith("unparseable: REFUSED")
    assert res["probe_weighting"] == "equal"
    assert [p.symbol for p in fb.submitted] == [f"SL{i:02d}" for i in range(10)]
    rec = _receipt(tmp_path)
    assert set(rec["probe_weights"].values()) == {config.PROBE_MAX_WEIGHT}
    assert rec["probe_gross"] == pytest.approx(config.PROBE_GROSS_CAP)


@pytest.mark.parametrize("kind", ["missing", "zero_byte", "unparseable"])
def test_a_broken_state_gives_the_old_book(tmp_path, monkeypatch, reputation_says_sl07, kind):
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    p = tmp_path / "policy_state.json"
    if kind == "zero_byte":
        p.write_bytes(b"")
    elif kind == "unparseable":
        p.write_text("{not json", encoding="utf-8")
    res = _run(tmp_path, p)
    assert res["policy_state_used"] is False
    assert res["policy_state_ignored"].startswith(
        "missing" if kind == "missing" else "unparseable")
    assert [p.symbol for p in fb.submitted] == [f"SL{i:02d}" for i in range(10)]
    assert set(_receipt(tmp_path)["probe_weights"].values()) == {config.PROBE_MAX_WEIGHT}


def test_a_sandbox_caller_never_opens_the_production_file(tmp_path, monkeypatch,
                                                           reputation_says_sl07):
    """A FRESH, valid state sits at STATE_PATH; a sandbox caller naming no path
    must not even call the reader."""
    monkeypatch.setattr(PS, "STATE_PATH", _state(tmp_path))
    called = []
    monkeypatch.setattr(PS, "plan_view", lambda *a, **k: called.append(1) or {})
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    res = _run(tmp_path, None)
    assert called == []
    assert res["policy_state_ignored"] == "sandbox caller named no policy_state_path"
    assert [p.symbol for p in fb.submitted] == [f"SL{i:02d}" for i in range(10)]


@pytest.mark.parametrize("stamp", ["not-a-date", "", "2026-13-45", 20260927])
def test_an_undateable_reputation_stamp_is_unknown_never_fresh(tmp_path, stamp):
    v = PS.plan_view(ASOF, path=_state(tmp_path, rep_date=stamp))
    assert not v["use"]
    assert v["ignored"]["reason"].startswith("stale:")


def test_a_reputation_stamp_from_the_future_is_unknown(tmp_path):
    ahead = (TODAY + timedelta(days=3)).isoformat()
    v = PS.plan_view(ASOF, path=_state(tmp_path, rep_date=ahead))
    assert not v["use"] and "undateable" in v["ignored"]["reason"]
    # one calendar day of slack (UTC+8 machine, ET plan date) is still fresh
    v = PS.plan_view(ASOF, path=_state(tmp_path, rep_date=(TODAY + timedelta(days=1)).isoformat()))
    assert v["use"] and v["used"]["age_sessions"] == 0
