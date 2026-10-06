"""Offline tests for hyp_lab (the hypothesis ledger), hyp_cells (its test designs) and hyp_llm (the
budgeted call path). Synthetic data only; no network; no literal calendar moment (dates are built
relative to a fixed synthetic calendar, never to "today")."""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from backend.services import hyp_cells as HC
from backend.services import hyp_lab as L
from backend.services import hyp_llm as HL


def _h(**kw):
    base = dict(title="Oil shock airlines lag", mechanism="jet fuel is a large cost share and repricing is slow",
                precursor="oil futures daily change beyond two sd at close t",
                separation_from_beta="same-day response printed apart; lag residual after beta",
                refutation="confirm-fold mean signed residual at or below zero", target="return",
                family="macro_readthrough_commodity", source="test", cell_type="macro_lead_lag",
                params={"driver": "CL=F", "targets": ["AAA"], "expected_sign": -1, "h": 1})
    base.update(kw)
    return L.make_hypothesis(**base)


# ---------------------------------------------------------------- ledger rows
def test_row_without_refutation_is_discarded_not_dropped():
    r = _h(refutation="")
    assert r["status"] == "DISCARDED_NO_REFUTATION"
    r2 = _h(precursor="n/a")
    assert r2["status"] == "DISCARDED_NO_REFUTATION"


def test_row_without_cell_needs_cell_and_id_is_stable_per_params():
    assert _h(cell_type=None)["status"] == "NEEDS_CELL"
    a, b = _h(), _h()
    assert a["hyp_id"] == b["hyp_id"]
    c = _h(params={"driver": "CL=F", "targets": ["AAA"], "expected_sign": -1, "h": 5})
    assert c["hyp_id"] != a["hyp_id"], "a new parameter set is a new hypothesis (its own look)"


def test_unknown_target_refused():
    with pytest.raises(ValueError):
        _h(target="alpha")


def test_ledger_is_append_only_and_folds(tmp_path):
    led = tmp_path / "ledger.jsonl"
    r = _h()
    L.append([r], led)
    L.update(r["hyp_id"], status="DECLARED", receipt="x.json", path=led)
    L.update(r["hyp_id"], status="RUN", verdict="FAILED_VARIANT", summary={"confirm": {"mean": -0.1, "t": -1.0}},
             path=led)
    lines = led.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    st = L.load_state(led)
    s = st[r["hyp_id"]]
    assert s["status"] == "RUN" and s["verdict"] == "FAILED_VARIANT"
    assert s["receipts"] == ["x.json"] and len(s["history"]) == 2
    with pytest.raises(ValueError):
        L.update(r["hyp_id"], verdict="GREAT", path=led)


# ---------------------------------------------------------------- dedupe + ranking
def test_dedupe_flags_closed_duplicate_and_same_params():
    corpus = [{"ref": "TRIAL-PT", "text": "price target change next session fade reversal analyst price target"}]
    dup = _h(title="Price target change next session fade", mechanism="analyst price target change reverses next session",
             precursor="analyst price target change", params={"k": 1})
    new = _h(title="Oil shock airlines lag")
    out = L.dedupe([dup, new], {}, corpus=corpus)
    assert out[0]["status"] == "DUPLICATE_OF_CLOSED"
    assert out[1]["status"] == "PROPOSED"
    # a differently worded row with the SAME cell params as a ledger row is the same test
    state = {new["hyp_id"]: {**new, "history": []}}
    same = _h(title="Crude spike hurts carriers next day", mechanism="fuel hedges are partial",
              precursor="crude oil jumps two sigma")
    out2 = L.dedupe([same], state, corpus=corpus)
    assert out2[0]["status"] == "DUPLICATE_IN_LEDGER"


def test_family_record_learns_and_moves_ranking(monkeypatch):
    # review 2026-10-06: families come from a fixed taxonomy and only POWERED failures count
    from backend import config as C
    monkeypatch.setattr(C, "HYP_LAB_FAMILIES", tuple(C.HYP_LAB_FAMILIES) + ("fam_a", "fam_b"))
    a = {**_h(family="fam_a"), "history": []}
    b = {**_h(family="fam_b", params={"x": 2}), "history": []}
    state = {a["hyp_id"]: a, b["hyp_id"]: b}
    fails = []
    for i in range(4):
        f = {**_h(family="fam_a", params={"x": 10 + i}), "history": [], "verdict": "FAILED_VARIANT", "status": "RUN",
             "last_summary": {"powered": True}}
        fails.append(f)
    for f in fails:
        state[f["hyp_id"]] = f
    fam = L.family_record(state)
    assert fam["fam_a"]["p_positive"] < fam["fam_b"]["p_positive"]
    q = L.rank(state, runnable_only=True)
    assert q[0]["family"] == "fam_b", "a family that keeps failing drops in the queue"


def test_value_comes_from_the_cell_not_the_claimed_target():
    fam = {}
    size_cell = _h(target="return", cell_type="size_feature_increment",
                   params={"feature_set": "abn_attention", "design_fold": "F2025", "confirm_fold": "F2026"})
    macro = _h(target="return")
    assert L.score(size_cell, fam)["value"] < L.score(macro, fam)["value"]


def test_parse_generated_discards_and_validates():
    items = [
        {"title": "A", "mechanism": "m" * 20, "precursor": "a public filing before the open",
         "separation_from_beta": "matched controls", "refutation": "the confirm fold mean is below zero",
         "target": "return", "family": "x", "cell_type": "macro_lead_lag",
         "params": {"driver": "CL=F", "targets": ["DAL"], "expected_sign": -1, "h": 1}},
        {"title": "B", "mechanism": "m" * 20, "precursor": "p" * 20, "refutation": "",
         "target": "size", "family": "y", "cell_type": None, "params": {}},
        {"title": "C", "mechanism": "m" * 20, "precursor": "an earnings release before the open",
         "separation_from_beta": "vol matched", "refutation": "the next-session size ratio is not above one",
         "target": "size", "family": "z", "cell_type": "macro_lead_lag",
         "params": {"driver": "GOLD", "targets": ["DAL"], "expected_sign": -1}},
    ]
    rows = L.parse_generated(items, "test_gen", "ref")
    st = {r["title"]: r for r in rows}
    assert st["A"]["status"] == "PROPOSED" and st["A"]["cell_type"] == "macro_lead_lag"
    assert st["B"]["status"] == "DISCARDED_NO_REFUTATION"
    assert st["C"]["status"] == "NEEDS_CELL" and st["C"]["cell_type"] is None


def test_declare_writes_hashed_receipt_before_run(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "RECEIPTS", tmp_path / "rc")
    monkeypatch.setattr(L, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(L, "STOP", tmp_path / "STOP")
    r = _h()
    L.append([r])
    order = []

    def runner(ct, params):
        order.append(("run", sorted((tmp_path / "rc").glob("declare_*.json"))))
        return {"verdict": "CANNOT_DISTINGUISH", "design": {"primary_x": {"mean": 0.1, "t": 1.0, "mde": 0.3}},
                "confirm": {"primary_x": {"mean": 0.05, "t": 0.5, "mde": 0.3}}}

    rec = L.declare([r], "night-x", notes=["disclosure"])
    assert rec["sha256"] and rec["disclosures"] == ["disclosure"]
    res = L.run_declared([L.load_state()[r["hyp_id"]]], "night-x", runner=runner)
    assert order and order[0][1], "the declaration receipt exists before the runner is called"
    st = L.load_state()[r["hyp_id"]]
    assert st["verdict"] == "CANNOT_DISTINGUISH" and st["status"] == "RUN"
    assert res[0]["confirm"]["mean"] == 0.05


def test_stop_file_blocks_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "RECEIPTS", tmp_path / "rc")
    monkeypatch.setattr(L, "LEDGER", tmp_path / "ledger.jsonl")
    (tmp_path / "STOP").write_text("x")
    r = _h()
    L.append([r])
    called = []
    out = L.run_declared([r], "n", runner=lambda *a: called.append(1) or {}, stop_file=tmp_path / "STOP")
    assert out == [] and called == []


def test_crashed_cell_is_a_refused_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "RECEIPTS", tmp_path / "rc")
    monkeypatch.setattr(L, "LEDGER", tmp_path / "ledger.jsonl")
    r = _h()
    L.append([r])

    def boom(*a):
        raise KeyError("missing column")

    L.run_declared([r], "n", runner=boom, stop_file=tmp_path / "STOP")
    assert L.load_state()[r["hyp_id"]]["verdict"] == "REFUSED"


# ---------------------------------------------------------------- the budgeted call path
def test_night_id_groups_evening_and_next_morning():
    ev = datetime(2031, 3, 4, 21, 30).astimezone()
    mo = datetime(2031, 3, 5, 6, 30).astimezone()
    assert HL.night_id(ev) == HL.night_id(mo)
    assert HL.night_id(datetime(2031, 3, 5, 9, 30).astimezone()) != HL.night_id(ev)


def test_cap_refuses_before_calling(tmp_path):
    sp = tmp_path / "spend.jsonl"
    calls = []

    def fake(provider, system, user, **kw):
        calls.append(1)
        return {"ok": True, "status": "OK", "text": "{}", "tokens_in": 1_000_000, "tokens_out": 1_000_000,
                "cost_usd": 0.0, "served_model": "fake"}

    r1 = HL.call("s", "u", purpose="t", arm="a", cap_usd=1.0, night="n1", spend_path=sp, _call_named=fake)
    assert r1["ok"] and len(calls) == 1
    # the ledger priced it at $0, but the peak-price estimate is 1.50: the cap binds anyway
    assert HL.spent("n1", sp)["binding_usd"] == pytest.approx(1.5)
    r2 = HL.call("s", "u", purpose="t", arm="a", cap_usd=1.0, night="n1", spend_path=sp, _call_named=fake)
    assert r2["status"] == "HYP_CAP_REFUSED" and len(calls) == 1
    # another night has its own budget; local calls never count
    assert HL.spent("n2", sp)["binding_usd"] == 0.0


def test_parse_recovers_truncated_array():
    t = '[{"a": 1, "b": "x}"}, {"a": 2}, {"a": 3, "b": "cut'
    assert HL.parse_json(t) == [{"a": 1, "b": "x}"}, {"a": 2}]
    assert HL.parse_json("```json\n{\"k\": 1}\n```") == {"k": 1}
    assert HL.parse_json("no json") is None


# ---------------------------------------------------------------- cells on synthetic data
def _synthetic_wide(n_days=900, n_names=40, seed=7, lag_beta=0.0, same_beta=0.0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2001-01-01", periods=n_days)
    driver = rng.normal(0, 0.02, n_days)
    names = [f"S{i}" for i in range(n_names)] + ["SPY"]
    rcc = pd.DataFrame(rng.normal(0, 0.01, (n_days, len(names))), index=dates, columns=names)
    tgt = ["S0", "S1", "S2"]
    for s in tgt:
        rcc[s] += same_beta * driver
        rcc.loc[rcc.index[1:], s] += lag_beta * driver[:-1]
    close = 100 * (1 + rcc).cumprod()
    op = close.shift(1).fillna(100.0)          # open = previous close: the whole day is open -> close
    W = {"open": op, "close": close, "rcc": close.pct_change(fill_method=None),
         "roc": close / op - 1.0}
    W["xoc"] = W["roc"].sub(W["roc"]["SPY"], axis=0)
    W["vol21"] = W["xoc"].abs().shift(1).rolling(21, min_periods=10).mean()
    macro = pd.DataFrame({"DRV": 50 * (1 + pd.Series(driver, index=dates)).cumprod()})
    return W, macro, tgt


def test_macro_lead_lag_finds_a_planted_lag_and_not_a_same_day_link():
    W, macro, tgt = _synthetic_wide(lag_beta=-0.6)
    p = {"driver": "DRV", "targets": tgt, "expected_sign": -1, "h": 1, "shock_z": 1.5,
         "design_end": str(W["close"].index[450].date()), "confirm_start": str(W["close"].index[480].date())}
    r = HC.macro_lead_lag(p, W=W, macro=macro)
    assert r["verdict"] == "CONDITIONAL_POSITIVE", r["reason"]
    W2, macro2, _ = _synthetic_wide(same_beta=-0.6)
    r2 = HC.macro_lead_lag(p, W=W2, macro=macro2)
    assert r2["verdict"] != "CONDITIONAL_POSITIVE"
    same = r2["confirm"]["same_day_signed_resid (ordinary beta, not tradable)"]
    assert same["t"] > 2, "the same-day beta is visible and printed apart"


def test_verdict_rule():
    assert HC.verdict({"mean": 0.1}, {"mean": 0.1, "t": 2.5, "mde": 0.1}, 0.01)["verdict"] == "CONDITIONAL_POSITIVE"
    assert HC.verdict({"mean": 0.1}, {"mean": -0.01, "t": -0.5, "mde": 0.1}, 0.01)["verdict"] == "FAILED_VARIANT"
    assert HC.verdict({"mean": 0.1}, {"mean": 0.02, "t": 1.0, "mde": 0.05}, 0.01)["verdict"] == "FAILED_VARIANT"
    assert HC.verdict({"mean": 0.1}, {"mean": 0.02, "t": 1.0, "mde": 0.3}, 0.01)["verdict"] == "CANNOT_DISTINGUISH"
    assert HC.verdict({"mean": -0.1}, {"mean": 0.2, "t": 3.0, "mde": 0.1}, 0.01)["verdict"] != "CONDITIONAL_POSITIVE"
    assert HC.verdict({}, {"mean": None, "t": None, "mde": None}, 0.01)["verdict"] == "REFUSED"


def test_comention_links_use_only_documents_known_before_t():
    t = pd.Timestamp("2001-06-10")
    docs = pd.DataFrame({
        "uid": ["u1", "u1", "u2", "u2", "u3", "u3"],
        "symbol": ["SRC", "OLD", "SRC", "FUT", "SRC", "SAME"],
        "known_date": [t - pd.Timedelta(days=20)] * 2 + [t + pd.Timedelta(days=1)] * 2 + [t] * 2})
    links = HC.comention_links("SRC", t, docs, lookback_days=90, k=5)
    assert links == ["OLD"], "a document known on or after t never defines a link"


def test_corr_links_exclude_source_and_index():
    W, _, tgt = _synthetic_wide(same_beta=0.0)
    rcc = W["rcc"].copy()
    rcc["TWIN"] = rcc["S5"] + np.random.default_rng(1).normal(0, 0.001, len(rcc))
    t = rcc.index[400]
    links = HC.corr_links("S5", t, rcc, k=3)
    assert links[0] == "TWIN" and "S5" not in links and "SPY" not in links


def test_lexicon_tone_signs():
    assert HC.lexicon_tone("Shares surge after record profit beat") > 0
    assert HC.lexicon_tone("Stock plunges on lawsuit and weak guidance cut") < 0
    assert HC.lexicon_tone("") == 0.0


def test_event_prior_is_fit_on_the_fit_block_only():
    cells = pd.DataFrame({"symbol": ["A", "B", "C", "D"] * 20, "entry_date": [f"d{i:03d}" for i in range(80)],
                          "rel": [5.0 if i < 40 else -5.0 for i in range(80)]})
    labels = pd.DataFrame({"symbol": cells["symbol"], "entry_date": cells["entry_date"],
                           "event_type": ["earnings_report"] * 80})
    fit = pd.Series([i < 40 for i in range(80)])
    f = HC.event_prior_features(cells, fit, labels=labels.drop_duplicates(["symbol", "entry_date"]))
    # the encoding is centred on the fit block: a type seen only there carries no test-block outcome
    assert f["earnings_flag"].eq(1.0).all()
    assert np.allclose(f["event_prior"].fillna(0), 0.0)
