"""E1's pipeline has to find an effect it was GIVEN before its failure to find
one in the real panel means anything.

That is the whole design of this file. A walk-forward that returns "no signal"
is indistinguishable from a walk-forward that is broken, and E1's honest
outcome is expected to be the first -- so the second has to be excluded by
construction:

* **planted-effect recovery** -- one event type, at direction +1, deterministically
  adds +2% to the label and nothing else carries anything. Both LightGBM and
  `StockMixer_T1` must find it, and the EVENT arm must beat the SHUFFLE arm by a
  wide margin on the same synthetic panel.
* **shuffled recovers nothing** -- on the SAME panel, with the event block
  permuted, the margin must collapse. A permutation that preserved the
  association (permuting within a group that still aligns with the planted
  cells) would pass the first test and fail this one.
* **nothing reaches past its own date** -- the feature builder's windows are
  `[D - w + 1, D]` in sessions, and an event landing AFTER a cell must not move
  that cell's features by a single bit.

Plus the proxy's own honesty: 39 ids exactly, the ids frozen against the
vocabulary spec, `no_event` never emitted as a row, and the entity-tag path
live and separately attributable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import event_head as eh                           # noqa: E402
from scripts import night_e1_event_head as e1                  # noqa: E402

VOCAB_SPEC = (REPO / "docs" / "research_notes" / "2026-09-11"
              / "spec_events_and_calibration.md")


# ---------------------------------------------------------------------------
# the vocabulary is the contract with L2
# ---------------------------------------------------------------------------
def test_the_vocabulary_is_the_specs_39_ids_in_its_order():
    if not VOCAB_SPEC.is_file():
        pytest.skip("the vocabulary spec is not on this checkout")
    body = VOCAB_SPEC.read_text(encoding="utf-8").split("### 1.2")[1].split("### 1.3")[0]
    ids = [ln.strip("|").split("|")[0].strip().strip("`")
           for ln in body.splitlines() if ln.startswith("| `")]
    ids = [i for i in ids if i != eh.NO_EVENT]
    assert len(ids) == 39, f"the spec no longer lists 39 types, it lists {len(ids)}"
    assert list(eh.TYPE_IDS) == ids, (
        "E1's vocabulary has drifted from the spec's frozen ids. The ids are the contract "
        "with L2's extraction; the PATTERNS are E1's to change, the ids are not.")


def test_no_event_is_never_emitted_as_a_row():
    assert eh.type_text("5 things to know about Acme Corp before the market opens") == []
    assert eh.NO_EVENT not in eh.TYPE_IDS


@pytest.mark.parametrize("text,expect", [
    ("Acme Corp reports Q3 EPS of $1.20, beating estimates of $1.05", "earnings_report"),
    ("Acme raises full-year revenue guidance to $4.1-4.3B", "guidance_change"),
    ("Acme Corp files for Chapter 11 bankruptcy protection", "bankruptcy_or_going_concern"),
    ("Acme recalls 2.1M vehicles over brake defect", "product_recall_or_defect"),
    ("FDA approves Acme's lead drug candidate for commercial sale", "regulatory_approval"),
    ("Acme board authorizes $1B share buyback program", "stock_buyback"),
    ("US announces 25% tariff on imported steel and aluminum", "tariff_or_trade_policy"),
])
def test_the_proxy_types_the_specs_own_example_headlines(text, expect):
    got = {e["event_type"] for e in eh.type_text(text)}
    assert expect in got, f"{expect!r} not among {sorted(got)}"


def test_direction_is_a_cue_vote_and_falls_back_to_the_type_prior():
    up = [e for e in eh.type_text("Acme reports Q3 earnings, beats estimates")
          if e["event_type"] == "earnings_report"][0]
    dn = [e for e in eh.type_text("Acme reports Q3 earnings, misses estimates")
          if e["event_type"] == "earnings_report"][0]
    assert up["direction"] == 1 and dn["direction"] == -1
    bk = eh.type_text("Acme Corp files for Chapter 11 bankruptcy protection")[0]
    assert bk["direction"] == -1, "a type with a negative prior must not come out neutral"


def test_the_entity_tag_path_is_live_and_separately_attributable():
    ev = eh.type_text("Acme puts out a press release", entity_tags=["8-K:2.02", "domain:x.com"])
    assert [e["event_type"] for e in ev] == ["earnings_report"]
    assert ev[0]["basis"] == "entity_tag"


# ---------------------------------------------------------------------------
# the feature builder
# ---------------------------------------------------------------------------
def _panel(n_symbols=6, n_sessions=30, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-02", periods=n_sessions)
    rows = []
    for s in range(n_symbols):
        for d in dates:
            rows.append({"symbol": f"S{s:02d}", "entry_date": d, "text": "routine market note",
                         "y": float(rng.normal(0, 0.01)), "pit_dv_21": 1e8,
                         "mom_21": float(rng.normal()), "mom_5": float(rng.normal())})
    return pd.DataFrame(rows)


def test_no_feature_reaches_past_its_own_date():
    """An event on session +1 must not move session 0's features by one bit."""
    cells = _panel()
    ev = pd.DataFrame([{"symbol": "S00", "entry_date": cells["entry_date"].iloc[10],
                        "event_type": "earnings_report", "direction": 1,
                        "magnitude_bucket": "MODERATE", "confidence": 0.8,
                        "basis": "keyword_proxy", "magnitude": 2.0}] * 40)
    X_before, _ = eh.build_features(cells, ev, min_occurrences=1)
    later = ev.copy()
    later["entry_date"] = cells["entry_date"].iloc[11]
    X_after, _ = eh.build_features(cells, later, min_occurrences=1)
    d0 = cells.index[(cells["symbol"] == "S00")
                     & (cells["entry_date"] == cells["entry_date"].iloc[10])][0]
    # the cell ON the event date sees it in one case and not the other
    assert X_before.loc[d0, "cnt_earnings_report_w1"] > 0
    assert X_after.loc[d0, "cnt_earnings_report_w1"] == 0
    # ... and no cell strictly BEFORE the later event date may move at all
    earlier = cells.index[cells["entry_date"] < cells["entry_date"].iloc[10]]
    assert X_before.loc[earlier].equals(X_after.loc[earlier]), (
        "moving an event forward in time changed a feature of a cell that precedes it")


def test_recency_is_censored_not_zeroed():
    cells = _panel()
    ev = pd.DataFrame([{"symbol": "S00", "entry_date": cells["entry_date"].iloc[5],
                        "event_type": "stock_buyback", "direction": 1,
                        "magnitude_bucket": "SMALL", "confidence": 0.6,
                        "basis": "keyword_proxy", "magnitude": 1.0}] * 40)
    X, _ = eh.build_features(cells, ev, min_occurrences=1)
    i0 = cells.index[(cells["symbol"] == "S00") & (cells["entry_date"] == cells["entry_date"].iloc[0])][0]
    i7 = cells.index[(cells["symbol"] == "S00") & (cells["entry_date"] == cells["entry_date"].iloc[7])][0]
    assert X.loc[i0, "rec_stock_buyback"] == eh.RECENCY_CENSOR
    assert X.loc[i0, "rec_stock_buyback_censored"] == 1.0, (
        "a name with no history was given a recency that reads as 'never', with no flag -- a "
        "0 there would claim an event happened today")
    assert X.loc[i7, "rec_stock_buyback"] == 2.0
    assert X.loc[i7, "rec_stock_buyback_censored"] == 0.0


def test_sparse_types_are_dropped_and_named():
    cells = _panel()
    ev = pd.DataFrame([{"symbol": "S00", "entry_date": cells["entry_date"].iloc[3],
                        "event_type": "spinoff", "direction": 0,
                        "magnitude_bucket": "LARGE", "confidence": 0.6,
                        "basis": "keyword_proxy", "magnitude": 3.0}])
    X, meta = eh.build_features(cells, ev, min_occurrences=30)
    assert meta["kept_types"] == []
    assert "spinoff" in meta["dropped_sparse_types"]
    assert X.shape[1] == 0


# ---------------------------------------------------------------------------
# the known-answer tests: a planted effect, and a shuffle that must not find it
# ---------------------------------------------------------------------------
def _planted(n_symbols=40, n_sessions=120, effect=0.02, rate=0.12, seed=11):
    """One type, at direction +1, adds `effect` to the label. Nothing else does."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-02", periods=n_sessions)
    rows, evs = [], []
    for s in range(n_symbols):
        sym = f"S{s:02d}"
        for d in dates:
            planted = bool(rng.random() < rate)
            noise_evt = bool(rng.random() < rate)
            y = float(rng.normal(0, 0.01)) + (effect if planted else 0.0)
            rows.append({"symbol": sym, "entry_date": d, "text": "x", "y": y,
                         "pit_dv_21": 1e8, "mom_21": float(rng.normal()),
                         "mom_5": float(rng.normal())})
            if planted:
                evs.append({"symbol": sym, "entry_date": d, "event_type": "regulatory_approval",
                            "direction": 1, "magnitude_bucket": "LARGE", "confidence": 0.9,
                            "basis": "planted", "magnitude": 3.0})
            if noise_evt:
                evs.append({"symbol": sym, "entry_date": d, "event_type": "product_launch_or_innovation",
                            "direction": 0, "magnitude_bucket": "SMALL", "confidence": 0.6,
                            "basis": "planted_noise", "magnitude": 1.0})
    return pd.DataFrame(rows), pd.DataFrame(evs)


def _split(cells):
    cut = cells["entry_date"].quantile(0.7)
    return (cells["entry_date"] <= cut).to_numpy(), (cells["entry_date"] > cut).to_numpy()


def test_gbm_recovers_a_planted_event_effect_and_the_shuffle_does_not():
    cells, ev = _planted()
    mats, meta = e1._feature_matrices(cells, ev, seed=3)
    tr, te = _split(cells)
    y = cells["y"].to_numpy()
    ics = {}
    for arm in ("EVENT", "SHUFFLE", "NOTEXT"):
        X = mats[arm]
        p, _ = eh.fit_predict_gbm(X.loc[tr].reset_index(drop=True), y[tr],
                                  X.loc[te].reset_index(drop=True))
        ics[arm] = np.corrcoef(p, y[te])[0, 1]
    assert ics["EVENT"] > 0.30, (
        f"LightGBM did not recover a +2% deterministic effect it was handed (r={ics['EVENT']:.3f}); "
        "a pipeline that cannot find a planted effect cannot be trusted to report its absence")
    assert ics["EVENT"] > ics["SHUFFLE"] + 0.20
    assert abs(ics["SHUFFLE"]) < 0.15, (
        f"the SHUFFLE arm recovered the planted effect (r={ics['SHUFFLE']:.3f}) -- the permutation "
        "is not cutting the event-to-cell link")
    assert meta["shuffle_control"]["fixed_points"] < 0.05 * len(cells)


def test_stockmixer_t1_recovers_the_same_planted_effect():
    pytest.importorskip("torch")
    cells, ev = _planted()
    mats, _ = e1._feature_matrices(cells, ev, seed=3)
    tr, te = _split(cells)
    y = cells["y"].to_numpy()
    d = cells["entry_date"].to_numpy()
    out = {}
    for arm in ("EVENT", "SHUFFLE"):
        X = mats[arm]
        p, info = eh.fit_predict_stockmixer(X.loc[tr].reset_index(drop=True), y[tr], d[tr],
                                            X.loc[te].reset_index(drop=True), d[te], epochs=8)
        out[arm] = np.corrcoef(p, y[te])[0, 1]
    assert out["EVENT"] > 0.25, f"StockMixer_T1 missed a planted effect (r={out['EVENT']:.3f})"
    assert out["EVENT"] > out["SHUFFLE"] + 0.15
    assert info["degeneracy"].startswith("T=1"), "the T=1 degeneracy must be stated, not implied"


def test_the_gbm_control_is_named_a_control_not_a_competitor():
    src = Path(e1.__file__).read_text(encoding="utf-8")
    assert "gbm_is_a_control" in src
    assert "Gu-Kelly-Xiu" in src


# ---------------------------------------------------------------------------
# grading: the two bars stay two bars
# ---------------------------------------------------------------------------
def test_beats_gbm_and_beats_shuffle_are_reported_separately():
    rng = np.random.default_rng(5)
    n = 120
    dd = pd.DataFrame({"date": pd.bdate_range("2025-01-02", periods=n),
                       "n": 50, "n_tradable": 40})
    for model in e1.MODELS:
        for arm in e1.ARMS:
            k = f"{model}_{arm}"
            dd[f"ic_{k}"] = rng.normal(0, 0.05, n)
            dd[f"gross_{k}"] = rng.normal(0, 0.002, n)
            dd[f"net_{k}"] = rng.normal(0, 0.002, n)
            dd[f"turnover_{k}"] = 0.5
    g = e1.grade(dd)
    head, lines = e1.verdict(g)
    assert "beats_gbm" in lines
    assert any(k.startswith("beats_shuffle_") for k in lines)
    assert lines["verdict"].startswith("FAILED_VARIANT")
    assert "beats_gbm" in lines and "beats_shuffle_GBM" in lines
    assert g["holm_family_size"] == 6, (
        "the Holm family must be the six EVENT-vs-control comparisons, not the "
        "architecture comparison as well -- that is a different question")
    assert "StockMixer_T1_minus_GBM_on_EVENT" in g["eras"]["ALL"]["vs_controls"]


def test_holm_is_monotone_and_never_below_the_raw_p():
    rng = np.random.default_rng(9)
    n = 200
    dd = pd.DataFrame({"date": pd.bdate_range("2025-01-02", periods=n), "n": 50, "n_tradable": 40})
    for model in e1.MODELS:
        for arm in e1.ARMS:
            k = f"{model}_{arm}"
            base = rng.normal(0, 0.05, n)
            dd[f"ic_{k}"] = base + (0.03 if arm == "EVENT" else 0.0)
            dd[f"gross_{k}"] = rng.normal(0, 0.002, n)
            dd[f"net_{k}"] = rng.normal(0, 0.002, n)
            dd[f"turnover_{k}"] = 0.5
    g = e1.grade(dd)
    holm = g["holm_adjusted_p_all_era_ic"]
    raw = {k: v["ic"]["p"] for k, v in g["eras"]["ALL"]["vs_controls"].items() if k in holm}
    for k, adj in holm.items():
        assert adj >= raw[k] - 1e-9, f"{k}: Holm-adjusted p {adj} is below the raw p {raw[k]}"
    assert g["family_max_p"] == max(holm.values())


# ---------------------------------------------------------------------------
# the receipt, when a run is on the checkout
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("horizon", [5, 21])
def test_the_e1_receipt_says_it_is_a_proxy(horizon):
    night = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-13"
    hits = list(night.glob(f"E1_event_head_h{horizon}_run*.json"))
    if not hits:
        pytest.skip(f"E1 h={horizon} has not run on this checkout")
    r = json.loads(hits[0].read_text(encoding="utf-8"))
    if r.get("status") != "done":
        pytest.skip(f"receipt is {r.get('status')!r}")
    assert r["licence"] == "PRODUCT_EXPERIMENT"
    assert r["stage"] == "signal"
    assert "PROXY" in r["design"]["typing"]
    assert r["design"]["horizon_sessions"] == horizon
    assert r["design"]["embargo_sessions"] == max(5, horizon)
    assert r["features"]["typing_coverage"]["event_rows_from_entity_tags"] >= 0
    assert r["beats_gbm"] and r["beats_shuffle"]
    assert r["next_test"]
    assert float(r["design"]["cost_bps_per_side"]) > 0.0
