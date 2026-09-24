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
    # CHUNK 15b: the family grew with the SCALAR treatment, and the per-model
    # line is now per (model, treatment). Both facts are asserted against the
    # DECLARED family rather than a hand-counted literal, so the next arm cannot
    # silently shrink the correction.
    assert "beats_gbm" in lines and "beats_shuffle_GBM_EVENT" in lines
    assert "beats_shuffle_GBM_SCALAR" in lines
    assert g["holm_family_size"] == g["holm_family_declared_size"] == 14, (
        "two treatments x two models x (three shared controls + each "
        "treatment's own matched shuffle) = 14. The architecture comparison and "
        "SCALAR_minus_EVENT are head-to-heads and stay OUT of the family -- "
        "sweeping them in would inflate the correction on the controls and hide "
        "the M5 bar inside a multiplicity adjustment it was never part of")
    assert g["holm_family_declared"] == e1.family_keys()
    assert g["holm_family_legs_without_a_p"] == []
    assert "StockMixer_T1_minus_GBM_on_EVENT" in g["eras"]["ALL"]["vs_controls"]
    assert "GBM:SCALAR_minus_EVENT" in g["eras"]["ALL"]["vs_controls"]
    assert "GBM:SCALAR_minus_EVENT" not in g["holm_adjusted_p_all_era_ic"]


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
    # SORTED, and the NEWEST run -- not `glob()[0]`.
    #
    # This test was a coin flip. Six h=5 receipts exist and they disagree:
    # run01 says "PROXY -- L2 has typed no row this panel holds", while
    # run02/03/04 say "L2's typed rows (LLM extraction, frozen 40-id
    # vocabulary)" because by then L2 typing WAS built. `glob()[0]` returns
    # whatever the filesystem lists first, so the test passed on NTFS (run01)
    # and failed on CI's Linux (a later run) on byte-identical data. It had
    # been latent since run02 was committed.
    hits = sorted(night.glob(f"E1_event_head_h{horizon}_run*.json"))
    hits = [h for h in hits if "_smoke" not in h.name] or hits
    if not hits:
        pytest.skip(f"E1 h={horizon} has not run on this checkout")
    r = json.loads(hits[-1].read_text(encoding="utf-8"))
    if r.get("status") != "done":
        pytest.skip(f"receipt is {r.get('status')!r}")
    assert r["licence"] == "PRODUCT_EXPERIMENT"
    assert r["stage"] == "signal"
    # The invariant is that the receipt NAMES WHICH TYPING IT READ -- not that
    # the typing is a proxy. Demanding "PROXY" asserted a fact the programme
    # outgrew the moment L2 typing shipped, and would have to be edited every
    # time the input improved. Its sibling
    # `test_the_failed_variant_sentence_names_which_typing_was_read` already
    # encodes the correct rule; this brings the receipt test into line with it.
    typing = r["design"]["typing"]
    assert ("PROXY" in typing) or ("typed rows" in typing), (
        f"the receipt does not say which typing it read: {typing[:120]!r}")
    assert r["design"]["horizon_sessions"] == horizon
    assert r["design"]["embargo_sessions"] == max(5, horizon)
    assert r["features"]["typing_coverage"]["event_rows_from_entity_tags"] >= 0
    assert r["beats_gbm"] and r["beats_shuffle"]
    assert r["next_test"]
    assert float(r["design"]["cost_bps_per_side"]) > 0.0


def test_the_failed_variant_sentence_names_which_typing_was_read():
    """2026-09-13: run 2 was the first E1 read on LLM-typed rows (630 of 129,983
    cells) and the receipt still closed 'the KEYWORD PROXY'. The sentence now
    names the source and the coverage, and says what the next test is."""
    from scripts import night_e1_event_head as E
    ic = {"mean": 0.001, "t": 0.5, "p": 0.6, "n_date_blocks": 30}
    vs = {"StockMixer_T1_minus_GBM_on_EVENT": {"ic": ic}}
    holm = {}
    for model in E.MODELS:
        for t in E.TREATMENTS:
            k = f"{model}:{t}_minus_{E.MATCHED_SHUFFLE[t]}"
            vs[k] = {"ic": ic}
            holm[k] = 1.0
    g = {"eras": {"ALL": {"vs_controls": vs}}, "holm_adjusted_p_all_era_ic": holm}
    _, lines = E.verdict(g, event_source="typed_l2",
                         typing_coverage={"cells": 129983, "cells_with_at_least_one_event": 630})
    assert "LLM-typed" in lines["verdict"] and "0.5% coverage" in lines["verdict"]
    assert "KEYWORD PROXY" not in lines["verdict"]
    _, lines = E.verdict(g, event_source="keyword_proxy", typing_coverage={})
    assert "KEYWORD PROXY" in lines["verdict"]


# ---------------------------------------------------------------------------
# chunk 15b — horizon 1 and the SCALAR arm
#
# `research_notes/2026-09-13/research_event_returns_last_read.md`: the
# construction the published event-return literature supports is a SCALAR
# direction x confidence score at a ONE-SESSION horizon. E1 had never run
# either — `HORIZONS` excluded 1 and no arm dropped the one-hots — so its null
# closed a hypothesis the literature never proposed.
# ---------------------------------------------------------------------------


def test_horizon_1_is_now_a_choice_and_n3_always_had_the_label():
    """Only THIS file's tuple excluded it. The label has always existed."""
    from scripts import night_n3_frozen_embedding_head as n3

    assert 1 in e1.HORIZONS
    assert 1 in n3.HORIZONS, "n3 has always built the h=1 label"
    assert n3.embargo_for(1) == 5
    assert "open-to-close" in n3.design_block(1)["target"]


def test_at_h1_the_overlap_caveat_is_NONE_and_says_so():
    """Every h>1 receipt carries 'divide the t by sqrt(h)'. At h=1 the label is
    one session, so date blocks do not overlap -- and the absence of the caveat
    must be STATED, not left to be noticed."""
    from scripts import night_n3_frozen_embedding_head as n3

    c1 = n3.horizon_caveats(1, 250)
    assert c1["n_effective_independent_blocks"] == 250
    assert "non-overlapping" in c1["overlap_note"]
    c5 = n3.horizon_caveats(5, 250)
    assert c5["n_effective_independent_blocks"] == 50
    assert "sqrt(5)" in c5["overlap_note"]


def test_the_scalar_arm_has_no_one_hot_column_of_any_kind():
    """The arm's whole content is that the TYPE IDENTITY is not used."""
    cells, ev = _planted()
    X, meta = eh.build_scalar_features(cells, ev)
    assert list(X.columns) == list(eh.SCALAR_COLUMNS)
    assert X.shape[1] == 5
    for c in X.columns:
        assert not c.startswith(("evt_", "cnt_", "mag_", "conf_", "rec_")), c
    for t in eh.TYPE_IDS:
        assert not any(t in c for c in X.columns), f"{t} leaked into a scalar column"
    assert "no one-hot" in meta["no_one_hot"] or "DELIBERATELY absent" in meta["no_one_hot"]


def test_the_scalar_score_is_signed_direction_times_confidence():
    cells = _panel()
    d = cells["entry_date"].iloc[10]
    ev = pd.DataFrame([
        {"symbol": "S00", "entry_date": d, "event_type": "earnings_report",
         "direction": 1, "magnitude_bucket": "LARGE", "confidence": 0.8,
         "basis": "t", "magnitude": 3.0},
        {"symbol": "S01", "entry_date": d, "event_type": "earnings_report",
         "direction": -1, "magnitude_bucket": "LARGE", "confidence": 0.8,
         "basis": "t", "magnitude": 3.0},
        {"symbol": "S02", "entry_date": d, "event_type": "earnings_report",
         "direction": 1, "magnitude_bucket": "SMALL", "confidence": 0.1,
         "basis": "t", "magnitude": 1.0},
    ])
    X, _ = eh.build_scalar_features(cells, ev)
    def at(sym):
        i = cells.index[(cells["symbol"] == sym) & (cells["entry_date"] == d)][0]
        return X.loc[i]
    assert at("S00")["sc_dirconf"] == pytest.approx(0.8)
    assert at("S01")["sc_dirconf"] == pytest.approx(-0.8), "a confident NEGATIVE is negative"
    assert at("S02")["sc_dirconf"] == pytest.approx(0.1), "an unconfident one is near zero"
    assert at("S00")["sc_mag"] == pytest.approx(3.0)


def test_a_cell_with_no_event_is_NaN_on_the_signed_column_and_zero_on_the_counts():
    """`fillna(0)` on a feature matrix is banned here, and a zero in a SIGNED
    column would read as 'confidently neutral' rather than 'nothing happened'.
    Counts are genuinely zero."""
    cells = _panel()
    ev = pd.DataFrame([{"symbol": "S00", "entry_date": cells["entry_date"].iloc[10],
                        "event_type": "earnings_report", "direction": 1,
                        "magnitude_bucket": "LARGE", "confidence": 0.9,
                        "basis": "t", "magnitude": 3.0}])
    X, _ = eh.build_scalar_features(cells, ev)
    i = cells.index[(cells["symbol"] == "S05")][0]
    assert np.isnan(X.loc[i, "sc_dirconf"])
    assert np.isnan(X.loc[i, "sc_mag"])
    assert X.loc[i, "sc_cnt_w1"] == 0.0
    assert X.loc[i, "sc_cnt_w21"] == 0.0


def test_no_scalar_feature_reaches_past_its_own_date():
    """The same PIT guarantee `build_features` carries, on the same arithmetic."""
    cells = _panel()
    ev = pd.DataFrame([{"symbol": "S00", "entry_date": cells["entry_date"].iloc[10],
                        "event_type": "earnings_report", "direction": 1,
                        "magnitude_bucket": "LARGE", "confidence": 0.8,
                        "basis": "t", "magnitude": 2.0}] * 5)
    X_before, _ = eh.build_scalar_features(cells, ev)
    later = ev.copy()
    later["entry_date"] = cells["entry_date"].iloc[11]
    X_after, _ = eh.build_scalar_features(cells, later)
    d0 = cells.index[(cells["symbol"] == "S00")
                     & (cells["entry_date"] == cells["entry_date"].iloc[10])][0]
    assert X_before.loc[d0, "sc_cnt_w1"] > 0
    assert X_after.loc[d0, "sc_cnt_w1"] == 0
    earlier = cells.index[cells["entry_date"] < cells["entry_date"].iloc[10]]
    assert X_before.loc[earlier].equals(X_after.loc[earlier])


def test_the_counts_are_the_declared_windows_and_type_agnostic():
    cells = _panel()
    d = cells["entry_date"]
    ev = pd.DataFrame([
        {"symbol": "S00", "entry_date": d.iloc[10], "event_type": "earnings_report",
         "direction": 1, "magnitude_bucket": "L", "confidence": 0.5, "basis": "t",
         "magnitude": 1.0},
        {"symbol": "S00", "entry_date": d.iloc[8], "event_type": "stock_buyback",
         "direction": 1, "magnitude_bucket": "L", "confidence": 0.5, "basis": "t",
         "magnitude": 1.0},
    ])
    X, meta = eh.build_scalar_features(cells, ev)
    i = cells.index[(cells["symbol"] == "S00") & (cells["entry_date"] == d.iloc[10])][0]
    assert meta["windows_sessions"] == [1, 5, 21]
    assert X.loc[i, "sc_cnt_w1"] == 1.0
    assert X.loc[i, "sc_cnt_w5"] == 2.0, "two DIFFERENT types, counted together"
    assert X.loc[i, "sc_cnt_w21"] == 2.0


def test_both_shuffles_use_ONE_permutation_so_the_two_reads_are_comparable():
    cells, ev = _planted()
    mats, meta = e1._feature_matrices(cells, ev, seed=3)
    assert set(mats) == set(e1.ARMS)
    assert mats["TFIDF"] is None
    # the scalar block appears in SCALAR and SCALAR_SHUFFLE, and nowhere else
    for c in eh.SCALAR_COLUMNS:
        assert c in mats["SCALAR"].columns and c in mats["SCALAR_SHUFFLE"].columns
        assert c not in mats["EVENT"].columns and c not in mats["SHUFFLE"].columns
    # price is held fixed in every arm that has it
    assert mats["SCALAR"]["mom_21"].equals(mats["EVENT"]["mom_21"])
    assert mats["SCALAR_SHUFFLE"]["mom_21"].equals(mats["EVENT"]["mom_21"])
    assert "why_two_shuffles" in meta["shuffle_control"]
    assert "WEAKER opponent" in meta["shuffle_control"]["why_two_shuffles"]


def test_the_matched_shuffle_is_a_permutation_of_the_scalar_block_itself():
    cells, ev = _planted()
    mats, _ = e1._feature_matrices(cells, ev, seed=3)
    a = mats["SCALAR"][list(eh.SCALAR_COLUMNS)].to_numpy()
    b = mats["SCALAR_SHUFFLE"][list(eh.SCALAR_COLUMNS)].to_numpy()
    assert a.shape == b.shape
    assert np.nansum(a) == pytest.approx(np.nansum(b)), (
        "a permutation moves rows, it does not change the multiset of values")
    assert not np.array_equal(np.nan_to_num(a), np.nan_to_num(b))


def test_gbm_recovers_a_planted_effect_through_the_SCALAR_arm_too():
    """A known-answer test for the new arm: the planted type is direction +1 at
    confidence 0.9 and the noise type is direction 0, so the scalar score
    separates them even with the type identity gone."""
    cells, ev = _planted()
    mats, _ = e1._feature_matrices(cells, ev, seed=3)
    tr, te = _split(cells)
    y = cells["y"].to_numpy(dtype=float)
    from scripts import night_n3_frozen_embedding_head as n3

    ics = {}
    for arm in ("SCALAR", "SCALAR_SHUFFLE"):
        Xtr = mats[arm].loc[tr].reset_index(drop=True)
        Xte = mats[arm].loc[te].reset_index(drop=True)
        pred, _ = eh.fit_predict_gbm(Xtr, y[tr], Xte, seed=3)
        ics[arm] = n3._spearman(pred, y[te])
    assert ics["SCALAR"] > ics["SCALAR_SHUFFLE"], ics
    assert ics["SCALAR"] > 0.05, ics


def test_the_family_is_declared_from_the_arms_not_hand_counted():
    keys = e1.family_keys()
    assert len(keys) == len(set(keys)) == 14
    assert "GBM:EVENT_minus_SHUFFLE" in keys, (
        "an earlier dedup dropped the single most load-bearing leg in this file")
    assert "GBM:SCALAR_minus_SCALAR_SHUFFLE" in keys
    assert "GBM:SCALAR_minus_EVENT" not in keys, "a head-to-head, not a control"
    assert "StockMixer_T1_minus_GBM_on_EVENT" not in keys
    assert len(e1.family_keys(("GBM",))) == 7


def test_a_scalar_win_is_reported_separately_from_an_event_win():
    """Two treatments, two verdict lines. Collapsing them would let one arm's
    result be quoted as the other's -- which is exactly the conflation the
    literature note found in E1's own null."""
    rng = np.random.default_rng(17)
    n = 200
    dd = pd.DataFrame({"date": pd.bdate_range("2025-01-02", periods=n),
                       "n": 50, "n_tradable": 40})
    for model in e1.MODELS:
        for arm in e1.ARMS:
            k = f"{model}_{arm}"
            dd[f"ic_{k}"] = rng.normal(0, 0.02, n) + (0.08 if arm == "SCALAR" else 0.0)
            dd[f"gross_{k}"] = rng.normal(0, 0.002, n)
            dd[f"net_{k}"] = rng.normal(0, 0.002, n)
            dd[f"turnover_{k}"] = 0.5
    g = e1.grade(dd, horizon=1)
    _, lines = e1.verdict(g)
    assert "-> YES" in lines["beats_shuffle_GBM_SCALAR"]
    assert "-> NO" in lines["beats_shuffle_GBM_EVENT"]
    assert not lines["verdict"].startswith("FAILED_VARIANT: NEITHER")
    assert g["horizon_caveats"]["n_effective_independent_blocks"] == n
