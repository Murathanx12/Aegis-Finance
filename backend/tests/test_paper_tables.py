"""scripts/paper_tables.py: the four properties a referee attacks first.

1. the persona/process classification is fixed BEFORE grading and cannot read outcomes;
2. a forecast frozen at or after its entry close is dropped (pre-window filter);
3. date-block clustering matches `forecast_reputation.date_blocks`;
4. the label simulation calls the REAL `book_dna.evidence_label`.

Synthetic fixtures only; no network; dates derived from a fixed synthetic calendar.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend.services import book_dna as BD
from backend.services import forecast_reputation as FR
from scripts import paper_tables as PT


REG = {"geopolitical": "You are a geopolitical risk analyst. You reason about conflict.",
       "skeptic": "You are a professional skeptic whose job is to find the loss.",
       "odd_arm": "Summarise the filing."}


def _sessions(n: int = 30) -> np.ndarray:
    return pd.bdate_range("2030-03-04", periods=n).values.astype("datetime64[D]")


# ── 1. classification before grading ─────────────────────────────────────────
def test_classifier_refuses_any_outcome_column():
    declared = pd.DataFrame({"specialist": ["geopolitical"], "model": ["deepseek-chat"],
                             "outcome": [1]})
    with pytest.raises(ValueError, match="REFUSED"):
        PT.classify_forecasters(declared, registry=REG)


def test_classification_reads_only_declared_fields():
    rows = [("investigator:B_tools", "deepseek-v4-flash"), ("geopolitical", "deepseek-chat"),
            ("skeptic", "deepseek-chat"), ("review:v0", "deterministic"),
            ("news_digest:insider_v0", "rule:cluster_buy_2"), ("source:wsj_other", "openclaw:x"),
            ("odd_arm", "deepseek-chat"), ("thesis_card:v1", "deepseek-chat")]
    d = pd.DataFrame(rows, columns=["specialist", "model"])
    cm = PT.classify_forecasters(d, registry=REG).set_index("specialist")["kind"]
    assert cm["investigator:B_tools"] == PT.PROCESS
    assert cm["geopolitical"] == PT.PERSONA and cm["skeptic"] == PT.PERSONA
    assert cm["review:v0"] == PT.EX_NOT_LLM and cm["news_digest:insider_v0"] == PT.EX_NOT_LLM
    assert cm["source:wsj_other"] == PT.EX_THIRD_PARTY
    assert cm["odd_arm"] == PT.EX_AMBIGUOUS          # registered, but no role identity
    assert cm["thesis_card:v1"] == PT.EX_AMBIGUOUS


def test_class_map_is_invariant_to_outcomes():
    """Same declared rows, outcomes flipped: the frozen map and its hash do not move."""
    d = pd.DataFrame({"specialist": ["geopolitical", "investigator:A_snapshot"] * 4,
                      "model": ["deepseek-chat", "deepseek-v4-flash"] * 4})
    rng = np.random.default_rng(0)
    h = []
    for _ in range(3):
        _ = rng.integers(0, 2, len(d))               # outcomes exist, the classifier never sees them
        h.append(PT.class_map_hash(PT.classify_forecasters(d, registry=REG)))
    assert len(set(h)) == 1


def test_build_graded_joins_outcomes_after_the_map(monkeypatch):
    """build_graded receives the class map already built from the declared frame."""
    ses = _sessions()
    day = str(ses[3])
    D = pd.DataFrame([{"prediction_id": f"p{i}", "specialist": s, "model": m, "ticker": "AAA",
                       "observable": "return_sign", "horizon_days": 5, "probability": 0.6,
                       "raw_probability": None, "shrink_basis": None, "threshold": None,
                       "benchmark": None, "made_at": f"{day}T10:00:00+00:00",
                       "resolves_after": day, "mechanism_id": None, "void_reason": None,
                       "entry_after_utc": None}
                      for i, (s, m) in enumerate([("geopolitical", "deepseek-chat"),
                                                  ("investigator:B_tools", "x"),
                                                  ("review:v0", "deterministic")])])
    O = pd.DataFrame({"prediction_id": ["p0", "p1", "p2"], "outcome": [1, 0, 1],
                      "resolved_at": [day] * 3})
    cm = PT.classify_forecasters(D[["specialist", "model"]], registry=REG)
    monkeypatch.setattr(PT, "premature_hold_mask", lambda ids: pd.Series(False, index=ids.index))
    x, flow = PT.build_graded(D, O, cm, ses)
    assert sorted(x["kind"]) == [PT.PERSONA, PT.PROCESS]
    assert flow["by_kind_all_rows"][PT.EX_NOT_LLM] == 1


# ── 2. the pre-window filter ─────────────────────────────────────────────────
def test_prewindow_drops_a_forecast_frozen_after_the_entry_close():
    ses = _sessions()
    d = str(ses[5])                                   # a weekday in the calendar
    made = pd.Series([f"{d}T14:00:00+00:00",         # 09:00/10:00 New York: before the close
                      f"{d}T22:30:00+00:00",         # after the 16:00 New York close
                      f"{d}T20:00:00+00:00"])        # 15:00/16:00 depending on DST
    start = pd.Series([d, d, d])
    pre, close = PT.prewindow_mask(made, start, ses)
    assert bool(pre.iloc[0]) is True
    assert bool(pre.iloc[1]) is False
    exp = pd.Timestamp(f"{d} 16:00").tz_localize("America/New_York").tz_convert("UTC")
    assert close.iloc[0] == exp
    assert bool(pre.iloc[2]) is (pd.Timestamp(made.iloc[2]) < exp)


def test_prewindow_weekend_forecast_enters_next_session():
    ses = _sessions()
    sat = (pd.Timestamp(str(ses[4])) + pd.Timedelta(days=1))
    while sat.weekday() != 5:
        sat += pd.Timedelta(days=1)
    made = pd.Series([f"{sat.date()}T23:00:00+00:00"])
    pre, close = PT.prewindow_mask(made, pd.Series([str(sat.date())]), ses)
    assert bool(pre.iloc[0]) is True
    assert close.iloc[0].tz_convert("America/New_York").weekday() == 0


def test_prewindow_unknown_entry_is_not_admitted():
    ses = _sessions(5)
    after = str(pd.Timestamp(str(ses[-1])) + pd.Timedelta(days=20))[:10]
    pre, _ = PT.prewindow_mask(pd.Series([f"{after}T01:00:00+00:00"]), pd.Series([after]), ses)
    assert bool(pre.iloc[0]) is False


# ── 3. date-block clustering ─────────────────────────────────────────────────
@pytest.mark.parametrize("h", [1, 2, 5, 20])
def test_date_blocks_match_forecast_reputation(h):
    rng = np.random.default_rng(h)
    days = [str(d.date()) for d in pd.bdate_range("2030-01-07", periods=80)]
    pick = sorted(rng.choice(days, size=35, replace=False))
    ids = PT.date_block_ids(pick, h)
    assert len(set(ids.values())) == FR.date_blocks(pick, h)
    # blocks are contiguous in time and never span more than h business days from their start
    for b in set(ids.values()):
        ds = sorted(d for d, v in ids.items() if v == b)
        assert int(np.busday_count(ds[0], ds[-1])) < max(h, 1)


def test_cluster_bootstrap_counts_date_blocks_not_rows():
    days = [str(d.date()) for d in pd.bdate_range("2030-01-07", periods=12)]
    rows = []
    for i, d in enumerate(days):
        for j in range(50):                            # 50 rows per day, 600 rows in all
            rows.append({"made_day": d, "h": 5, "ticker": f"T{j}", "kind": PT.PROCESS,
                         "bs": 0.2 + 0.01 * (i % 3), "bs_ref": 0.25})
    df = pd.DataFrame(rows)
    df["block"] = PT.assign_date_blocks(df)
    out = PT.cluster_bootstrap(df, "block", 200, np.random.default_rng(1))
    assert out["n_clusters"] == FR.date_blocks(days, 5) < len(df)


def test_one_date_block_kind_gives_no_date_verdict():
    rows = []
    for d in [str(x.date()) for x in pd.bdate_range("2030-01-07", periods=30)]:
        rows.append({"made_day": d, "h": 1, "ticker": "A", "kind": PT.PROCESS, "p": 0.6,
                     "y": 1.0, "observable": "abs_move_exceeds", "threshold": "0.03"})
    for t in range(40):
        rows.append({"made_day": "2030-01-07", "h": 1, "ticker": f"P{t}", "kind": PT.PERSONA,
                     "p": 0.7, "y": float(t % 2), "observable": "abs_move_exceeds",
                     "threshold": "0.03"})
    df = PT.add_reference(pd.DataFrame(rows))
    df["block"] = PT.assign_date_blocks(df)
    c = PT.contrast(df, 100, np.random.default_rng(2))
    assert c["date_blocks_per_kind"][PT.PERSONA] == 1
    assert c["verdict_date_blocks"].startswith("CANNOT_DETERMINE")


# ── 4. the label simulation calls the real evidence_label ────────────────────
def test_label_book_calls_the_real_evidence_label(monkeypatch):
    calls = []
    real = BD.evidence_label

    def spy(**kw):
        calls.append(kw)
        return real(**kw)

    monkeypatch.setattr(BD, "evidence_label", spy)
    L = 30
    dates = [str(d.date()) for d in pd.bdate_range("2030-01-07", periods=L)]
    b = np.full(L, 0.002)
    s = np.full(L, 0.001)
    out = PT.label_book(dates, b, s, twin_total=1.0, L=L, p=BD.params())
    assert len(calls) == 1 and calls[0]["sessions"] == L
    assert out["label"] == "REPLICATED"              # beats SPY, 3/3 thirds, beats its twin
    out2 = PT.label_book(dates, s, b, twin_total=None, L=L, p=BD.params())
    assert out2["label"] == "OBSERVED"


def test_simulate_on_a_synthetic_panel_uses_the_real_label(monkeypatch):
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2030-01-07", periods=140)
    syms = ["SPY"] + [f"S{i:03d}" for i in range(60)]
    rows = []
    for s in syms:
        px = 50 * np.cumprod(1 + rng.normal(0, 0.01, len(dates)))
        vol = 1e6 if s != "SPY" else 1e8
        for d, c in zip(dates, px):
            rows.append({"symbol": s, "date": d, "open": c, "close": c, "volume": vol})
    panel = PT.Panel(pd.DataFrame(rows))
    seen = []
    real = BD.evidence_label
    monkeypatch.setattr(BD, "evidence_label", lambda **kw: (seen.append(1), real(**kw))[1])
    sim = PT.simulate(panel, (21,), (5,), ("mixed",), 6, seed=4, n_starts=3)
    assert len(sim) > 0 and len(seen) == 4 * len(sim)
    assert set(sim["label_twin_route"]) <= {"OBSERVED", "EARLY_EVIDENCE", "REPLICATED"}
    rates = PT.label_rates(sim, ["L"])
    assert rates[0]["n_books"] == len(sim) and 0 <= rates[0]["early_or_higher"] <= 1


def test_wilson_interval_brackets_the_rate():
    lo, hi = PT.wilson(30, 100)
    assert lo < 0.30 < hi and 0 <= lo and hi <= 1


def test_main_refuses_an_out_dir_inside_the_data_root(tmp_path):
    root = tmp_path / "optimus"
    root.mkdir()
    assert PT.main(["--out", str(root / "x"), "--data-root", str(root), "--table", "1"]) == 2
    assert not (root / "x").exists()


def test_live_twins_reads_stored_labels(tmp_path):
    rec = {"generated_utc": "x", "params": BD.params(), "books": [
        {"category": "twin", "twin_kind": "random_same_band", "sessions_graded": 35,
         "inception": "a", "excess_pp": 2.0, "evidence": {"label": "EARLY_EVIDENCE"},
         "subwindows": {"status": "OK", "n_positive": 2}, "fair_twin": None},
        {"category": "twin", "twin_kind": "random_same_band", "sessions_graded": 35,
         "inception": "a", "excess_pp": -1.0, "evidence": {"label": "OBSERVED(35)"},
         "subwindows": {"status": "OK", "n_positive": 1}, "fair_twin": None},
        {"category": "strategy", "twin_kind": None, "evidence": {"label": "REPLICATED"}}]}
    p = tmp_path / "book_dna_x.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    out = PT.live_twins(p)
    assert out["n_random_twins"] == 2 and out["recompute_agrees"] == 2
    assert out["all"]["early_or_higher"] == 0.5
