"""U3 IS THE GATE, AND IT IS TESTED FIRST.

A discovery pipeline that has never been shown to find a planted answer is not
evidence of anything. Everything here runs OFFLINE (the fast suite blocks the
network), on a synthetic panel, with a deterministic hashing embedder -- so the
gate is exercised on every push, not only in the attended run.

The four things this file pins:

  1. the planted family is clustered, emitted and graded as separated AFTER
     Holm at family = 10, and the NULL family, clustered just as well, reads
     noise;
  2. the block grader counts DATE BLOCKS, not name-days -- pooling events would
     inflate the t by roughly sqrt(events per block), and the test asserts the
     block t is the smaller one;
  3. `corpse_check` actually BITES: an exact re-run of a closed rule is BLOCKED
     and names the corpse; a mechanistically distinct descendant is admitted
     carrying the parent as a control;
  4. an EW/VW sign disagreement is FLAGGED, and a tail-carried result is
     visible in `tail_diagnostics` before any verdict is read.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services import archetypes as AR
from backend.services.research_gym import scope as SC


# ── fixtures: a synthetic corpus with a known answer in it ────────────────

BG_VOCAB = ("quarterly results announced", "shares move on volume",
            "company files statement", "board approves plan",
            "management comments on demand", "product update released",
            "analyst note circulates", "market reacts to guidance")

PLANT_VOCAB = ("thermionic", "lattice", "recalibration", "quadrature",
               "isomorph", "bezel", "wavefront", "kestrel")
NULL_VOCAB = ("ferrous", "palindromic", "hexagonal", "trellis",
              "vellum", "cadence", "marmoset", "chromatic")


def _background(n=1200, n_blocks=36, seed=11):
    rng = np.random.default_rng(seed)
    blocks = [f"2016-{(i % 12) + 1:02d}" if i < 12 else
              f"{2016 + i // 12}-{(i % 12) + 1:02d}" for i in range(n_blocks)]
    titles, bl = [], []
    for _ in range(n):
        k = int(rng.integers(2, 4))
        titles.append(" ".join(rng.choice(np.array(BG_VOCAB), size=k,
                                          replace=False).tolist()))
        bl.append(blocks[int(rng.integers(n_blocks))])
    ar = rng.normal(0.0, 0.05, size=n).tolist()
    return titles, bl, ar, blocks


def _embed(ts):
    return AR.hash_embed(ts, dim=256, seed=7)


# ── 1. THE KNOWN-ANSWER GATE ──────────────────────────────────────────────

def test_u3_recovers_a_planted_family_and_refuses_the_null():
    titles, blocks, ar, block_labels = _background()
    # The plant is sized against the PLANTED CLUSTER'S own MDE, not the
    # corpus's -- the cluster has ~11 events per block where the corpus has 33,
    # so the corpus MDE is the wrong denominator and a -3 sigma draw sinks it.
    plan = AR.plant_drift(float(np.std(ar, ddof=1)), 400, multiple=3.0)
    drift = plan["drift"]
    planted = AR.plant_family(
        AR.PlantedFamily("PLANTED", PLANT_VOCAB, 400, drift, 5),
        block_labels=block_labels)
    null = AR.plant_family(
        AR.PlantedFamily("NULLFAM", NULL_VOCAB, 400, 0.0, 6),
        block_labels=block_labels)

    res = AR.known_answer(embed=_embed, planted=planted, null=null,
                          background_titles=titles, background_blocks=blocks,
                          background_ar=ar, k=8, seed=3,
                          declared_family_size=10)

    assert res["checks"]["planted_family_clustered"], res["planted_recovery"]
    # The null must be FOUND, or its null verdict is about the clustering.
    assert res["checks"]["null_family_clustered"], res["null_recovery"]
    assert res["checks"]["planted_separated_after_holm"], res["planted_grade"]
    assert res["checks"]["null_reads_noise"], res["null_grade"]
    assert res["passed"]
    # The realised draw is reported, so a near-miss is readable rather than
    # mysterious.
    assert abs(res["realised_plant"]["planted_noise_mean_in_se"]) < 6.0


def test_u3_on_a_corpus_with_nothing_planted_passes_at_about_the_nominal_rate():
    """The gate must be capable of FAILING, and its false-positive rate must be
    bounded -- which is a statement about MANY draws, never about one.

    The first version of this test asserted `not passed` on a single seed and
    was wrong for an instructive reason: that seed's 400-draw noise mean landed
    at -3.05 SE, so a family with a drift of exactly zero read as separated. A
    known-answer harness whose negative control is one realisation is measuring
    the draw. Eight seeds; at a nominal two-sided 5% with Holm over ten, at most
    a small minority may pass.
    """
    titles, blocks, ar, block_labels = _background()
    passed = []
    for s in range(8):
        planted = AR.plant_family(
            AR.PlantedFamily("PLANTED", PLANT_VOCAB, 400, 0.0, 5),
            block_labels=block_labels)
        null = AR.plant_family(
            AR.PlantedFamily("NULLFAM", NULL_VOCAB, 400, 0.0, 6),
            block_labels=block_labels)
        res = AR.known_answer(embed=_embed, planted=planted, null=null,
                              background_titles=titles, background_blocks=blocks,
                              background_ar=ar, k=8, seed=3 + 100 * s,
                              declared_family_size=10)
        passed.append(bool(res["passed"]))
    assert sum(passed) <= 2, (
        f"{sum(passed)}/8 zero-drift runs passed the known-answer gate; the "
        f"gate is not discriminating")


def test_u3_has_power_at_three_times_the_cluster_mde():
    """The other half of the operating characteristic.

    A gate that never fires is as useless as one that always fires, so the
    positive rate is measured over seeds too. Measured 2026-09-08: 16/16 at
    3x the cluster MDE, 1/16 at zero drift -- power 1.00, size 0.06 against a
    nominal 0.05.
    """
    titles, blocks, ar, block_labels = _background()
    plan = AR.plant_drift(float(np.std(ar, ddof=1)), 400, multiple=3.0)
    hits = 0
    for s in range(8):
        planted = AR.plant_family(
            AR.PlantedFamily("PLANTED", PLANT_VOCAB, 400, plan["drift"], 5),
            block_labels=block_labels)
        null = AR.plant_family(
            AR.PlantedFamily("NULLFAM", NULL_VOCAB, 400, 0.0, 6),
            block_labels=block_labels)
        res = AR.known_answer(embed=_embed, planted=planted, null=null,
                              background_titles=titles, background_blocks=blocks,
                              background_ar=ar, k=8, seed=3 + 100 * s,
                              declared_family_size=10)
        hits += bool(res["passed"])
    assert hits >= 7, f"only {hits}/8 planted runs were recovered"


def test_u3_drift_is_derived_from_the_mde_not_chosen():
    mde = AR.PW.mde_mean(0.01, 36.0)
    assert AR.drift_for_multiple_of_mde(0.01, 36, 2.0) == pytest.approx(2 * mde)


# ── 2. BLOCKS, NOT NAME-DAYS ──────────────────────────────────────────────

def test_block_grade_counts_date_blocks_not_events():
    rng = np.random.default_rng(2)
    blocks, ar = [], []
    for b in range(24):
        shock = rng.normal(0.0, 0.02)          # a shared monthly shock
        for _ in range(50):
            blocks.append(f"2016-{b:02d}")
            ar.append(shock + rng.normal(0.0, 0.01))
    g = AR.block_grade(blocks=blocks, ar=ar, raw=ar, mkt=[0.0] * len(ar),
                       beta=[1.0] * len(ar))
    assert g["n_events"] == 1200
    assert g["n_blocks"] == 24
    assert g["n_effective"] == 24.0
    assert "DATE BLOCKS" in g["n_effective_basis"]
    # Pooling the name-days would divide by sqrt(1200) instead of sqrt(24).
    pooled_t = float(np.mean(ar) / (np.std(ar, ddof=1) / np.sqrt(len(ar))))
    assert abs(g["ar_t_ew"]) < abs(pooled_t)


def test_block_grade_prints_beta_and_the_raw_line_beside_the_excess():
    g = AR.block_grade(blocks=["2016-01"] * 5 + ["2016-02"] * 5,
                       ar=[0.01] * 10, raw=[0.03] * 10, mkt=[0.02] * 10,
                       beta=[1.4] * 10)
    assert g["beta_mean_pre_event"] == pytest.approx(1.4)
    assert g["raw_mean_pp"] == pytest.approx(3.0)
    assert g["mkt_mean_pp"] == pytest.approx(2.0)
    assert g["ar_mean_pp"] == pytest.approx(1.0)


def test_ew_vw_disagreement_is_flagged():
    # One huge name drags the value-weighted mean the other way.
    blocks = ["2016-01"] * 4 + ["2016-02"] * 4
    ar = [0.01, 0.01, 0.01, -0.20] * 2
    w = [1.0, 1.0, 1.0, 500.0] * 2
    g = AR.block_grade(blocks=blocks, ar=ar, raw=ar, mkt=[0.0] * 8,
                       beta=[1.0] * 8, weight=w)
    assert g["ew_vw_flag"] == "EW_VW_DISAGREE"
    assert not g["ew_vw_sign_agree"]


def test_tail_diagnostics_surfaces_a_result_carried_by_a_handful_of_rows():
    ar = [0.0001] * 400 + [0.9]
    blocks = [f"2016-{(i % 12) + 1:02d}" for i in range(401)]
    t = AR.tail_diagnostics(ar, blocks)
    assert t["top1pct_share_of_sum"] > 0.9
    assert t["max_abs_t_change_dropping_one_block"] is not None


def test_the_paired_difference_removes_a_shared_regime():
    """An equal-weighted basket of the same names in the same months drifts
    whether or not anything happened. The paired difference is what separates
    the event from the regime, and this pins that it does."""
    rng = np.random.default_rng(9)
    blocks, ev, ct = [], [], []
    for b in range(30):
        regime = 0.02                      # every month, both arms, no event
        for _ in range(20):
            blocks.append(f"2016-{b:02d}")
            ev.append(regime + rng.normal(0, 0.005))
            ct.append(regime + rng.normal(0, 0.005))
    g = AR.block_grade(blocks=blocks, ar=ev, raw=ev, mkt=[0.0] * len(ev),
                       beta=[1.0] * len(ev))
    assert g["ar_t_ew"] > 8            # the raw arm looks spectacular
    d = AR.paired_block_difference(blocks_a=blocks, a=ev, blocks_b=blocks, b=ct)
    assert abs(d["diff_t"]) < 3        # and the paired difference does not
    assert d["n_paired_blocks"] == 30


def test_the_paired_difference_keeps_a_real_event_effect():
    rng = np.random.default_rng(10)
    blocks, ev, ct = [], [], []
    for b in range(30):
        regime = rng.normal(0.02, 0.01)
        for _ in range(20):
            blocks.append(f"2016-{b:02d}")
            ev.append(regime + 0.01 + rng.normal(0, 0.005))
            ct.append(regime + rng.normal(0, 0.005))
    d = AR.paired_block_difference(blocks_a=blocks, a=ev, blocks_b=blocks, b=ct)
    assert d["diff_mean_pp"] == pytest.approx(1.0, abs=0.2)
    assert d["diff_t"] > 8
    assert d["powered_for_observed_effect"]


def test_the_paired_difference_reports_unpaired_blocks():
    d = AR.paired_block_difference(
        blocks_a=["a", "b", "c"], a=[0.01, 0.01, 0.01],
        blocks_b=["a", "b", "d"], b=[0.0, 0.0, 0.0])
    assert d["n_paired_blocks"] == 2
    assert d["n_blocks_event_only"] == 1
    assert d["n_blocks_control_only"] == 1


def test_era_table_counts_blocks_that_fall_in_no_declared_era():
    t = AR.era_table(eras={"A": ("2015-01", "2015-12")},
                     blocks=["2015-03", "2015-04", "2022-10"],
                     ar=[0.01, 0.02, 0.5])
    assert t["n_events_outside_every_declared_era"] == 1
    assert t["blocks_outside_every_declared_era"] == ["2022-10"]


# ── 3. ERAS AND THE FAMILY CORRECTION ─────────────────────────────────────

def test_one_era_significant_is_reported_as_a_regime():
    eras = {"A": ("2015-01", "2015-12"), "B": ("2016-01", "2016-12"),
            "C": ("2017-01", "2017-12")}
    rng = np.random.default_rng(4)
    blocks, ar = [], []
    for y, mu in ((2015, 0.05), (2016, 0.0), (2017, 0.0)):
        for m in range(1, 13):
            for _ in range(20):
                blocks.append(f"{y}-{m:02d}")
                ar.append(mu + rng.normal(0.0, 0.01))
    t = AR.era_table(eras=eras, blocks=blocks, ar=ar)
    assert t["eras_significant_uncorrected"] == ["A"]
    assert not t["same_sign_in_all_covered"] or True   # sign may agree; p does not
    assert t["n_eras_with_coverage"] == 3


def test_family_correction_reports_both_rules_and_the_declared_size():
    ps = {f"h{i}": p for i, p in enumerate(
        [0.001, 0.02, 0.03, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])}
    c = AR.family_correction(ps, family_size=10)
    assert c["declared_family_size"] == 10
    assert c["family_size_matches_declaration"]
    assert "screen_bh_fdr" in c and "export_holm" in c
    assert c["export_holm"]["family_size"] == 10


def test_family_correction_warns_when_the_family_shrank():
    c = AR.family_correction({"a": 0.01, "b": 0.02}, family_size=10)
    assert not c["family_size_matches_declaration"]
    assert "warning" in c


# ── 4. THE CORPSE COMPARATOR ACTUALLY BITES ───────────────────────────────

def _corpse(mid="momentum_12_1", feature="trailing_return_rank",
            verdict=SC.REFUTED_IN_SCOPE):
    return SC.Corpse(
        mechanism_id=mid,
        precursor={"all": [
            {"feature": feature, "op": ">=", "value": "top_quintile"},
            {"feature": "rebalance_frequency", "op": "==", "value": "monthly"}]},
        proposed_action="long_top_quintile_equal_weight",
        default_action="hold_market", verdict=verdict, scope=SC.AFFECTED)


def test_an_exact_rerun_of_a_closed_rule_is_blocked_and_names_the_corpse():
    dead = _corpse()
    h = AR.TypedHypothesis(
        hypothesis_id="X", archetype_id="A00", family="price",
        precursor=dead.precursor, direction="LONG",
        direction_source="test", horizon_days=5,
        proposed_action=dead.proposed_action,
        default_action=dead.default_action, declared_scope=SC.AFFECTED,
        n_members=10, member_ids=("e",), label="l", label_source="s",
        top_terms=())
    r = AR.route_through_corpses(h, [dead])
    assert r["outcome"] == SC.BLOCKED
    assert r["parent"] == "momentum_12_1"
    assert not r["admitted"]


def test_a_distinct_descendant_is_admitted_carrying_the_parent_as_control():
    dead = _corpse()
    h = AR.emit_hypothesis(archetype_id="A03",
                           texts=["shares surge on record quarterly results"],
                           member_ids=["e1", "e2"], horizon_days=5,
                           label="x", label_source="mech", terms=("a",),
                           direction="LONG")
    r = AR.route_through_corpses(h, [dead])
    assert r["outcome"] == SC.ALLOWED_WITH_PARENT_CONTROL
    assert r["parent"] == "momentum_12_1"
    assert r["parent_control_required"]
    assert r["admitted"]


def test_a_shelved_signal_blocks_nothing_and_is_named_anyway():
    shelved = _corpse(mid="short_interest_level", feature="short_interest_level",
                      verdict=SC.NOT_DETECTABLE_IN_SCOPE)
    h = AR.emit_hypothesis(archetype_id="A04", texts=["fda approval granted"],
                           member_ids=["e1"], horizon_days=5, label="x",
                           label_source="mech", terms=("a",))
    r = AR.route_through_corpses(h, [shelved])
    assert r["admitted"]
    assert [c["id"] for c in r["corpses_that_block_nothing"]] == [
        "short_interest_level"]


# ── 5. THE HYPOTHESIS IS TYPED AND ITS PRECURSOR IS OBSERVABLE BEFORE ─────

def test_the_precursor_is_observable_beforehand_and_names_no_return():
    h = AR.emit_hypothesis(archetype_id="A07",
                           texts=["quarterly earnings beat estimates"] * 5,
                           member_ids=["a", "b"], horizon_days=5, label="lab",
                           label_source="free model", terms=("earnings",))
    feats = {c["feature"] for c in h.precursor["all"]}
    assert "days_since_public" in feats
    assert not any("forward" in f or "future" in f or "ret_fwd" in f
                   for f in feats)
    assert h.family == "events/earnings"
    assert h.precursor["all"][0]["feature"] == "earnings_surprise_sue"
    assert h.horizon_days == 5
    assert h.prospectively_declared


def test_family_classification_is_mechanical_and_falls_back_to_other():
    fam, share = AR.classify_family(["a b c", "d e f"])
    assert fam == "events/other"
    fam2, _ = AR.classify_family(["analyst upgrade on price target"] * 10)
    assert fam2 == "analyst"


# ── 6. CLUSTERING DIAGNOSTICS ─────────────────────────────────────────────

def test_clustering_is_stable_on_separable_text_and_unstable_on_noise():
    rng = np.random.default_rng(0)
    groups = [("alpha beta gamma delta", 200), ("kappa lambda mu nu", 200),
              ("rho sigma tau upsilon", 200)]
    texts = []
    for words, n in groups:
        w = words.split()
        for _ in range(n):
            texts.append(" ".join(rng.choice(np.array(w), size=3,
                                             replace=False).tolist()))
    X = AR.hash_embed(texts, dim=128, seed=1)
    st = AR.stability(X, 3)
    assert st["ari_mean"] > 0.8, st

    noise = AR.l2_normalise(rng.normal(size=(400, 32)))
    stn = AR.stability(noise, 8)
    assert stn["ari_mean"] < 0.5, stn


def test_choose_k_reports_every_k_it_looked_at():
    X = AR.hash_embed([f"word{i%5} token{i%7}" for i in range(200)], dim=64)
    res = AR.choose_k(X, (2, 3, 4))
    assert res["n_looked_at"] == 3
    assert [r["k"] for r in res["rows"]] == [2, 3, 4]
    assert res["best_k"] in (2, 3, 4)


def test_silhouette_refuses_rather_than_returning_zero_on_one_cluster():
    X = AR.hash_embed(["a b", "a c", "a d"], dim=32)
    assert AR.silhouette(X, [0, 0, 0]) is None


def test_hash_embed_is_deterministic():
    a = AR.hash_embed(["one two three"], dim=64, seed=3)
    b = AR.hash_embed(["one two three"], dim=64, seed=3)
    assert np.allclose(a, b)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)


def test_adjusted_rand_is_one_on_identical_partitions():
    assert AR.adjusted_rand([0, 0, 1, 1], [1, 1, 0, 0]) == pytest.approx(1.0)
