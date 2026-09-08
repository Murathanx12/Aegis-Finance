"""R7 -- the contracts of the news-representation lane.

Every test here is OFFLINE. The module imports no torch at import time (the
encoder is behind `_torch()`), so this suite runs on a machine with no GPU and
on CI, which is the only way the contracts below stay enforced.

What is pinned, and why each one is here rather than in a docstring:

* COVERAGE NORMALISATION IS A SWITCH, NOT A HABIT. `_pool(normalise=True)` is
  the mean and `False` is the sum; the difference is the whole of Murat's
  standing "a name with more news is not a name with more signal", so it is a
  test and not a comment.
* THE PIT TICKER JOIN. A ticker reused by a different company must not inherit
  the earlier permno. That is the interval bound, and without a test it is one
  merge away from disappearing.
* THE WALK-FORWARD BOUNDARY. No training month may reach into or past the test
  year, and the embargo month must actually be dropped.
* NO RETURN IS READ BY THE PRE-TRAINING PATH. Asserted on the source, because
  the whole claim of the lane is that the representation never saw a label.
* A MISSING INPUT IS A REFUSAL. Not a silent skip, not an empty frame.
"""

from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import r7_news_representation as R7


# ───────────────────────────────────────────────────────────── text handling

def test_normalise_text_strips_tags_and_entities():
    out = R7.normalise_text("A &amp; B <b>rise</b>", "the market&#39;s day <i>x</i>")
    assert "<" not in out and "&" not in out and "#39" not in out
    assert "rise" in out and "market" in out


def test_normalise_text_survives_a_missing_body():
    assert R7.normalise_text("Headline only", None) == "Headline only"
    assert R7.normalise_text("Headline only", "   ") == "Headline only"


def test_normalise_text_bounds_the_body():
    out = R7.normalise_text("T", "x" * 5000, body_chars=50)
    assert len(out) < 120


def test_tokenise_keeps_dollar_and_percent():
    assert R7.tokenise("Beat by $1.20, up 4%") == ["beat", "by", "$1.20", "up", "4%"]


# ─────────────────────────────────────────────── company-identity masking

def test_mask_company_masks_the_ticker_and_the_issuer_name():
    toks = R7.tokenise("apple inc beats on aapl guidance")
    out = R7.mask_company(toks, "AAPL", {"apple"})
    assert R7.CO_TOKEN in out
    assert "aapl" not in out and "apple" not in out
    assert "beats" in out and "guidance" in out


def test_mask_company_leaves_generic_corporate_words_alone():
    # "inc" is generic: masking it would delete ordinary English from every
    # headline and make the masked corpus unlike the unmasked one for no gain.
    assert "inc" in R7._GENERIC_NAME_TOKENS
    toks = R7.tokenise("holdings inc group reports")
    assert R7.mask_company(toks, "ZZZZ", set()) == toks


def test_company_name_map_drops_generic_tokens(monkeypatch, tmp_path):
    df = pd.DataFrame({"ticker": ["AAPL", "AAPL"],
                       "issuernm": ["APPLE INC", "APPLE COMPUTER INC"]})
    p = tmp_path / "sn.parquet"
    df.to_parquet(p)
    monkeypatch.setattr(R7, "STOCKNAMES", p)
    m = R7.company_name_map()
    assert m["AAPL"] == {"apple", "computer"}


def test_company_name_map_refuses_when_the_source_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(R7, "STOCKNAMES", tmp_path / "nope.parquet")
    with pytest.raises(R7.R7Refusal):
        R7.company_name_map()


# ────────────────────────────────────────────────── vocabulary and encoding

def test_build_vocab_puts_the_specials_first_and_honours_min_count():
    docs = [["a", "b", "c"]] * 6 + [["rare"]]
    v = R7.build_vocab(docs, min_count=5)
    assert [t for t, i in sorted(v.items(), key=lambda kv: kv[1])][:4] == R7.SPECIALS
    assert "a" in v and "rare" not in v


def test_build_vocab_respects_max_vocab():
    docs = [[f"t{i}" for i in range(500)] for _ in range(6)]
    v = R7.build_vocab(docs, max_vocab=20, min_count=1)
    assert len(v) == 20


def test_encode_ids_starts_with_cls_pads_and_truncates():
    v = R7.build_vocab([["x"] * 6], min_count=1)
    ids = R7.encode_ids(["x", "x"], v, seq_len=6)
    assert ids[0] == R7.CLS and len(ids) == 6 and ids[-1] == R7.PAD
    long = R7.encode_ids(["x"] * 50, v, seq_len=6)
    assert len(long) == 6 and R7.PAD not in long


def test_encode_ids_maps_an_unseen_token_to_unk():
    v = R7.build_vocab([["x"] * 6], min_count=1)
    assert R7.UNK in R7.encode_ids(["zzz"], v, seq_len=4)


# ───────────────────────────────────────────────────────── the PIT ticker join

def _crosswalk_frame():
    return pd.DataFrame({
        "permno": [1.0, 2.0],
        "ticker": ["ABC", "ABC"],
        "namedt": pd.to_datetime(["2010-01-01", "2020-01-01"]),
        "nameenddt": pd.to_datetime(["2015-01-01", "2030-01-01"]),
    })


def test_resolve_permnos_uses_the_interval_and_not_the_first_row():
    docs = pd.DataFrame({
        "uid": ["u1", "u2"],
        "symbols": ["ABC", "ABC"],
        "observed_at": pd.to_datetime(["2012-06-01", "2022-06-01"], utc=True),
    })
    out = R7.resolve_permnos(docs, _crosswalk_frame()).set_index("uid")
    assert out.loc["u1", "permno"] == 1.0
    assert out.loc["u2", "permno"] == 2.0


def test_resolve_permnos_leaves_an_unmatched_ticker_unresolved_rather_than_dropping_it():
    docs = pd.DataFrame({
        "uid": ["u3"],
        "symbols": ["ZZZZ"],
        "observed_at": pd.to_datetime(["2012-06-01"], utc=True),
    })
    out = R7.resolve_permnos(docs, _crosswalk_frame())
    assert len(out) == 1 and pd.isna(out.iloc[0]["permno"])


def test_resolve_permnos_never_returns_two_rows_for_one_document():
    cw = _crosswalk_frame()
    cw = pd.concat([cw, cw], ignore_index=True)      # duplicated name intervals
    docs = pd.DataFrame({"uid": ["u1"], "symbols": ["ABC"],
                         "observed_at": pd.to_datetime(["2012-06-01"], utc=True)})
    assert len(R7.resolve_permnos(docs, cw)) == 1


# ───────────────────────────────────────────── coverage normalisation is a switch

def test_pool_mean_is_coverage_normalised_and_sum_is_not():
    emb = np.array([[1.0, 0.0], [3.0, 0.0], [10.0, 0.0]])
    keys = np.array(["a", "a", "b"])
    uk, mean, cnt = R7._pool(emb, keys, normalise=True)
    uk2, tot, _ = R7._pool(emb, keys, normalise=False)
    assert list(uk) == ["a", "b"]
    assert mean[0, 0] == pytest.approx(2.0)      # (1+3)/2 -- count divided out
    assert tot[0, 0] == pytest.approx(4.0)       # 1+3     -- count still in
    assert list(cnt) == [2.0, 1.0]


def test_pool_sum_scales_with_document_count_and_mean_does_not():
    one = np.ones((1, 3))
    ten = np.ones((10, 3))
    _, m1, _ = R7._pool(one, np.array(["x"]), True)
    _, m10, _ = R7._pool(ten, np.array(["x"] * 10), True)
    _, s1, _ = R7._pool(one, np.array(["x"]), False)
    _, s10, _ = R7._pool(ten, np.array(["x"] * 10), False)
    assert np.allclose(m1, m10)
    assert np.allclose(s10, 10 * s1)


# ─────────────────────────────────────────────────── monthly metrics and costs

def _pred_frame(n_months=3, n_names=40, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_months):
        for i in range(n_names):
            rows.append({"permno": float(i), "month": f"2020-{m+1:02d}",
                         R7.TARGET: rng.normal(), "ret_1m": rng.normal(),
                         "mkt_vw_1m": 0.01 * m, "pred": rng.normal()})
    return pd.DataFrame(rows)


def test_monthly_metrics_emits_one_row_per_month_not_per_name_month():
    mm = R7._monthly_metrics(_pred_frame(n_months=4))
    assert len(mm) == 4
    assert set(mm["month"]) == {"2020-01", "2020-02", "2020-03", "2020-04"}


def test_monthly_metrics_drops_a_month_thinner_than_the_floor():
    p = _pred_frame(n_months=2, n_names=40)
    p = pd.concat([p[p["month"] == "2020-01"],
                   p[p["month"] == "2020-02"].head(R7.MIN_NAMES_PER_MONTH - 1)])
    mm = R7._monthly_metrics(p)
    assert list(mm["month"]) == ["2020-01"]


def test_a_perfect_ranker_scores_ic_one():
    p = _pred_frame(n_months=1, n_names=40)
    p["pred"] = p[R7.TARGET]
    assert R7._monthly_metrics(p)["ic"].iloc[0] == pytest.approx(1.0)


def test_turnover_cost_is_zero_for_a_book_that_never_changes():
    p = _pred_frame(n_months=3, n_names=40)
    p["pred"] = p["permno"]                       # the same ranking every month
    c = R7._turnover_cost(p, R7.ONE_WAY_BPS_HOUSE)
    assert c.iloc[0] > 0                          # month 1 pays to get in
    assert list(c.iloc[1:]) == [0.0, 0.0]


def test_turnover_cost_rises_with_the_rate():
    p = _pred_frame(n_months=3, n_names=40, seed=7)
    lo = R7._turnover_cost(p, R7.ONE_WAY_BPS_HOUSE).sum()
    hi = R7._turnover_cost(p, R7.ONE_WAY_BPS_STRESS).sum()
    assert hi > lo > 0
    assert hi / lo == pytest.approx(R7.ONE_WAY_BPS_STRESS / R7.ONE_WAY_BPS_HOUSE)


def test_costs_are_never_omitted_from_the_net_column():
    # the net column is the gross column minus a cost that is >= 0, always
    p = _pred_frame(n_months=4, n_names=40, seed=3)
    mm = R7._monthly_metrics(p)
    c = R7._turnover_cost(p, R7.ONE_WAY_BPS_HOUSE)
    net = mm["ls_gross"] - mm["month"].map(c).fillna(0.0)
    assert (net <= mm["ls_gross"] + 1e-12).all()


# ────────────────────────────────────────────────────────── statistics

def test_tstat_refuses_a_sample_too_small_to_have_one():
    t, p, n = R7._tstat([0.1, 0.2])
    assert math.isnan(t) and n == 2


def test_tstat_matches_the_definition():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    t, p, n = R7._tstat(x)
    assert n == 4
    assert t == pytest.approx(x.mean() / (x.std(ddof=1) / 2.0))


def test_beta_recovers_a_planted_loading():
    rng = np.random.default_rng(0)
    mkt = rng.normal(size=200)
    book = 0.7 * mkt + 0.001
    b, a = R7._beta(book, mkt)
    assert b == pytest.approx(0.7, abs=1e-6)


def test_beta_refuses_a_sample_that_cannot_support_one():
    b, a = R7._beta(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
    assert math.isnan(b)


def test_mde_falls_as_the_sample_grows():
    a = R7.mde_for_mean(0.2, 20)
    b = R7.mde_for_mean(0.2, 200)
    assert a > b > 0
    assert b == pytest.approx(R7.Z80_TWO_SIDED * 0.2 / math.sqrt(200))


def test_mde_refuses_a_degenerate_input():
    assert math.isnan(R7.mde_for_mean(0.0, 100))
    assert math.isnan(R7.mde_for_mean(0.2, 1))


# ──────────────────────────────────────────────── the walk-forward boundary

def test_the_fold_boundary_leaves_an_embargo_month():
    for Y in R7.TEST_YEARS:
        last_train = f"{Y-1}-11"
        first_test = f"{Y}-01"
        embargoed = f"{Y-1}-12"
        assert last_train < embargoed < first_test


def test_every_test_year_belongs_to_exactly_one_era():
    assert sorted(R7.ERA_OF_YEAR) == sorted(R7.TEST_YEARS)
    assert set(R7.ERA_OF_YEAR.values()) == {"E1", "E2", "E3"}
    assert set(R7.PIT_FOR_ERA) == {"E1", "E2", "E3"}


def test_each_eras_pit_encoder_is_cut_off_before_that_eras_first_test_month():
    for era, sl in R7.PIT_FOR_ERA.items():
        first_test = min(y for y, e in R7.ERA_OF_YEAR.items() if e == era)
        assert R7.PIT_CUTOFF[sl] <= f"{first_test}-01"


def test_the_full_slice_is_declared_leaky_by_its_cutoff():
    # `full` has no cutoff at all -- that is the point of it, and the sentinel
    # must sort ABOVE every real month so `slice_docs` keeps everything.
    assert R7.PIT_CUTOFF["full"] > "2026-12"


def test_ridge_inner_validation_uses_the_tail_and_not_a_random_split():
    src = inspect.getsource(R7._ridge_fit_predict)
    assert "cut = max(1, int(n * (1 - inner_frac)))" in src
    assert "shuffle" not in src and "permutation" not in src


def test_ridge_picks_the_alpha_that_predicts_the_held_out_tail():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 5))
    y = X[:, 0] * 2.0 + rng.normal(scale=0.1, size=400)
    p, a = R7._ridge_fit_predict(X, y, X[:10])
    assert np.corrcoef(p, y[:10])[0, 1] > 0.9
    assert a in (1.0, 10.0, 100.0, 1000.0)


# ─────────────────────────────────────── the pre-training path reads no returns

def _module_source() -> str:
    return Path(R7.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize("fn", ["build_docs", "pretrain", "run_pretrain",
                                "prepare_masked", "mask_company", "build_vocab"])
def test_no_pretraining_function_mentions_the_return_target(fn):
    src = inspect.getsource(getattr(R7, fn))
    for banned in ("TRAIN_TABLE", "excess_vw", "TARGET", "ret_1m", "mkt_vw"):
        assert banned not in src, f"{fn} touches {banned}: the pre-train would see a label"


def test_the_pretrain_receipt_declares_that_no_return_was_read():
    src = inspect.getsource(R7.run_pretrain)
    assert '"returns_read": False' in src


def test_the_label_ceiling_is_declared_and_matches_the_panel_note():
    assert R7.LABEL_LAST_MONTH == "2024-12"
    assert R7.TARGET == "excess_vw_1m"


# ───────────────────────────────────────────────── refusals, not silent skips

def test_build_docs_refuses_when_the_corpus_directory_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(R7, "CORPUS_OBS_DIR", tmp_path / "nowhere")
    with pytest.raises(R7.R7Refusal) as e:
        R7.build_docs()
    assert "news corpus absent" in str(e.value)


def test_build_docs_refuses_an_empty_corpus_directory(monkeypatch, tmp_path):
    d = tmp_path / "obs"
    d.mkdir()
    monkeypatch.setattr(R7, "CORPUS_OBS_DIR", d)
    with pytest.raises(R7.R7Refusal):
        R7.build_docs()


def test_build_panel_refuses_without_the_documents(monkeypatch, tmp_path):
    monkeypatch.setattr(R7, "DOCS_PARQUET", tmp_path / "missing.parquet")
    with pytest.raises(R7.R7Refusal) as e:
        R7.build_panel()
    assert "--build-docs" in str(e.value)


def test_embed_all_refuses_a_missing_checkpoint(monkeypatch, tmp_path):
    pytest.importorskip("torch")
    monkeypatch.setattr(R7, "OUT_DIR", tmp_path)
    with pytest.raises(R7.R7Refusal) as e:
        R7.embed_all("pit2018", np.zeros((2, R7.SEQ_LEN), dtype=np.int64), 16,
                     device="cpu")
    assert "checkpoint absent" in str(e.value)


def test_run_pretrain_refuses_a_slice_too_thin_for_a_vocabulary(monkeypatch):
    monkeypatch.setattr(R7, "prepare_masked",
                        lambda *a, **k: pd.DataFrame({"masked": ["a b"] * 10,
                                                      "month": ["2015-01"] * 10,
                                                      "company_id": [0] * 10,
                                                      "day": [0] * 10}))
    with pytest.raises(R7.R7Refusal) as e:
        R7.run_pretrain("pit2018", epochs=1, seed=0, device="cpu")
    assert "refusing to pretrain" in str(e.value)


# ──────────────────────────────────────────────────── the leak gate's grading

def test_the_year_and_ticker_extractors_are_strict():
    assert R7._TICKER_RE.findall("AAPL is the answer")[0] == "AAPL"
    assert R7._YEAR_RE.search("published in 2019.").group(0) == "2019"
    assert R7._YEAR_RE.search("no year here") is None


def test_the_declared_qwen_cutoff_sits_inside_the_labelled_window():
    assert "2015-02" < R7.QWEN_CUTOFF_MONTH < R7.LABEL_LAST_MONTH


def test_the_leak_gate_verdict_has_a_cannot_determine_branch():
    src = inspect.getsource(R7.leak_gate)
    assert "CANNOT_DETERMINE" in src
    assert "MEMORY SUSPECTED" in src
    # a provider failure must not be graded as a wrong answer
    assert "failures += 1" in src


def test_the_leak_gate_prints_the_share_answered_beat_beside_accuracy():
    src = inspect.getsource(R7.leak_gate)
    assert "share_answered_BEAT" in src and "base_rate_actually_positive" in src


# ─────────────────────────────────────────────────────────── retrieval probe

def test_retrieval_probe_returns_cannot_determine_rather_than_a_number(monkeypatch):
    monkeypatch.setattr(R7, "prepare_masked",
                        lambda *a, **k: pd.DataFrame({"masked": ["a b"] * 5,
                                                      "month": ["2019-01"] * 5,
                                                      "company_id": [0] * 5,
                                                      "day": [0] * 5}))
    out = R7.retrieval_probe("pit2018")
    assert out["status"] == "CANNOT_DETERMINE"
    assert "documents" in out["reason"]


def test_the_arm_list_carries_every_comparison_the_brief_demands():
    # (a) no-pretraining, (b) TF-IDF, (c) coverage alone -- plus the leaky FULL
    # encoder, which is how the leak gets a price rather than an assurance.
    assert "rand_mean" in R7.ARMS
    assert "tfidf_svd" in R7.ARMS and "tfidf_raw" in R7.ARMS
    assert "coverage" in R7.ARMS
    assert "full_mean" in R7.ARMS and "pit_mean" in R7.ARMS and "pit_sum" in R7.ARMS


def test_the_module_never_calls_a_random_kfold():
    src = _module_source()
    for banned in ("KFold", "train_test_split", "ShuffleSplit"):
        assert banned not in src, f"{banned} is a random split on a time series"


def test_the_diagnostic_arms_are_excluded_from_the_multiplicity_family():
    src = inspect.getsource(R7.adjudicate)
    assert 'r["arm"] not in DIAGNOSTIC_ARMS' in src
    assert set(R7.DIAGNOSTIC_ARMS) == {"planted_signal", "pure_noise"}
    assert not set(R7.DIAGNOSTIC_ARMS) & set(R7.ARMS)


def test_the_receipt_separates_the_known_answer_battery_from_the_arms():
    src = inspect.getsource(R7.run_evaluate)
    assert "harness_known_answer_battery" in src


def test_the_leak_gate_reports_an_mde_beside_every_null():
    src = inspect.getsource(R7.leak_gate)
    # "no drop detected" is only readable next to the drop that COULD have been
    assert "mde_accuracy_drop_80pct_pp" in src
    assert "company_mde_80pct_above_chance_pp" in src
    assert "company_exact_binomial_p_greater" in src
    assert "year_exact_binomial_p_greater" in src


def test_the_retrieval_probe_samples_pairs_rather_than_embedding_the_whole_corpus():
    src = inspect.getsource(R7.retrieval_probe)
    assert "n_pairs_total" in src and "pairs_sampled" in src
    # the sample must be uniform, not the first N (which would be one era)
    assert "rng.choice(len(pair_a), size=30000, replace=False)" in src


def test_the_retrieval_probe_never_grades_a_same_company_distractor_as_a_miss():
    src = inspect.getsource(R7.retrieval_probe)
    assert "sim[same] = -np.inf" in src
