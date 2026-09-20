"""CHUNK 22 — the decile map, its reader, and what it is allowed to size.

`scripts/calibrate_signal_return.py` (the night job `C7_signal_calibration`),
`backend/services/signal_calibration.py` (the reader) and the two lines of
`roi_rank` / `decision_authority` that now take a per-name `mu_i` instead of a
signal family's average.

The load-bearing tests here are the two nulls' mirror images:

* a PLANTED linear signal must come back as a monotone decile map — if the
  machinery cannot recover a map that is there, every negative it reports is
  uninterpretable;
* a SHUFFLED panel must not — if it can manufacture a map that is not there,
  every positive it reports is uninterpretable.

Everything is synthetic and offline. Nothing here reads `backend/data`: every
calibration file is planted under `tmp_path` and `signal_calibration._repo_root`
is pointed at it, so the suite's verdicts never depend on which night last ran.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.services import decision_authority as DA
from backend.services import roi_rank
from backend.services import signal_calibration as SC
from backend.services.recommendation import Recommendation, SignalContribution
from scripts import calibrate_signal_return as C7

ASOF = date(2026, 9, 21)


# ===========================================================================
# helpers — a synthetic panel, and a planted calibration file
# ===========================================================================


def _panel(*, alpha: float, n_months: int = 144, n_names: int = 200,
           seed: int = 7, noise: float = 0.05) -> pd.DataFrame:
    """A panel whose forward return is `alpha x score` plus noise.

    `alpha = 0` is the pure null. Sessions advance 21 per month, so the
    horizon arithmetic in the statistics is the same one the real job runs.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_months):
        stamp = pd.Timestamp("2006-01-31") + pd.DateOffset(months=m)
        score = rng.uniform(0.0, 1.0, n_names)
        fwd = alpha * (score - 0.5) + rng.normal(0.0, noise, n_names)
        rows.append(pd.DataFrame({
            "permno": np.arange(n_names) + 10_000,
            "sess": np.full(n_names, m * 21),
            "month": np.full(n_names, stamp.strftime("%Y-%m"), dtype=object),
            "year": np.full(n_names, stamp.year),
            "score": score,
            "fwd_21": fwd,
        }))
    return pd.concat(rows, ignore_index=True)


def _deciles(means, p20s=None, n=500, blocks=120, net=None):
    out = []
    for i, mu in enumerate(means, start=1):
        p20 = (p20s[i - 1] if p20s is not None else -8.0)
        out.append({"decile": i, "n_names": n, "n_date_blocks": blocks,
                    "turnover_one_way_monthly": 0.1,
                    "cost_pct": 0.05,
                    "mean_abn_pct": mu + 0.05,
                    "mean_abn_net_pct": (net[i - 1] if net is not None else mu),
                    "p20_abn_pct": p20, "sd_abn_pct": 10.0,
                    "ci_lo_pct": mu - 0.2, "ci_hi_pct": mu + 0.2})
    return out


def plant(tmp_path, signal, *, verdict, means, cuts, spread_t=3.0,
          holm_p=0.001, asof="2026-09-21", p20s=None, schema=SC.SCHEMA,
          name=None):
    """Write one calibration file under `tmp_path`, and return its path."""
    d = tmp_path / config.CALIB_OUTPUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    blob = {
        "schema": schema, "signal": signal, "asof": asof,
        "verdict": verdict, "verdict_basis": "planted by a test",
        "deciding_horizon_sessions": 21,
        "cut_points": cuts,
        "holm": {"adjusted_p": holm_p},
        "horizons": {"21": {
            "deciles": _deciles(means, p20s=p20s),
            "spread": {"label": "D10 - D1", "net_t": spread_t,
                       "net_spread_pct": means[-1] - means[0],
                       "gross_spread_pct": means[-1] - means[0],
                       "n_date_blocks": 120},
            "monotonicity": {"monotone": True},
        }},
    }
    p = d / (name or f"{signal}_{asof}.json")
    p.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    return p


@pytest.fixture()
def rooted(tmp_path, monkeypatch):
    """Point the reader at tmp_path. Nothing in this file reads backend/data."""
    monkeypatch.setattr(SC, "_repo_root", lambda: tmp_path)
    return tmp_path


def _table(**over):
    def row(pct, t):
        return {"monthly_net_pct": pct, "t": t,
                "t_basis": "a t on the net return", "n_blocks": 419,
                "net_basis": "synthetic fixture", "receipt": "README.md",
                "measured_on": "2026-09-13"}
    base = {"planted": row(0.50, 3.10), "unproven": row(0.17, 1.40)}
    base.update(over)
    return base


def _rec(ticker, signal, *, rank=1, score=1.0, verdict="BUY"):
    r = Recommendation(ticker=ticker, rank=rank, ranking_score=score,
                       confidence="MEDIUM", evidence_grade="SUPPORTED",
                       price=20.0)
    r.recommendation = verdict
    r.signal_contributions = [SignalContribution(
        signal_id=signal, role="PICKER", grade="SUPPORTED", raw_value=1.0,
        weight=0.7, contribution=0.5, rank_bearing=True, basis="test")]
    return r


@pytest.fixture()
def measured(monkeypatch):
    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN", _table(),
                        raising=False)
    monkeypatch.setattr(config, "IC_ROI_RANKING", True, raising=False)
    monkeypatch.setattr(config, "IC_LEGACY_HEURISTIC_SIZING", False,
                        raising=False)
    monkeypatch.setattr(config, "ROI_USE_CALIBRATION", True, raising=False)
    return _table()


# ===========================================================================
# THE TWO MIRROR TESTS — it finds a map that is there, and only that
# ===========================================================================


def test_a_planted_linear_signal_comes_back_as_a_monotone_decile_map():
    panel = _panel(alpha=0.20)
    oos, wf = C7.assign_deciles(panel, first_test_year=2009)
    rng = np.random.default_rng(config.CALIB_BOOTSTRAP_SEED)
    table = C7.decile_table(oos, 21, rng=rng)
    mono = C7.monotonicity(table)
    spread = C7.spread_block(oos, 21, table)

    assert wf["n_nonempty_deciles"] == config.CALIB_N_DECILES
    assert mono["monotone"] is True
    assert mono["spearman_decile_vs_mean"] > 0.95
    means = [r["mean_abn_pct"] for r in table["rows"]]
    assert means[-1] > means[0]
    assert spread["gross_spread_pct"] > 0
    assert spread["gross_t"] is not None and spread["gross_t"] > 2.0
    # every cell is a count of MONTHS, never of rows (CANON §58)
    assert all(r["n_date_blocks"] <= r["n_names"] for r in table["rows"])


def _read(panel):
    oos, wf = C7.assign_deciles(panel, first_test_year=2009)
    rng = np.random.default_rng(config.CALIB_BOOTSTRAP_SEED)
    table = C7.decile_table(oos, 21, rng=rng)
    return wf, table, C7.spread_block(oos, 21, table), C7.monotonicity(table)


def test_a_shuffled_panel_yields_no_monotone_spread_and_never_calibrates():
    """The null's own test. Scores carry nothing; the map must say so.

    Stated as a RATIO against the planted panel of the test above rather than
    as an absolute t: one shuffled draw at one seed can produce any t, and a
    hard threshold on it would be a test of that seed. What must hold is that
    the machinery separates the two by orders of magnitude, and that the
    monotonicity gate refuses the null whatever its spread did.
    """
    _, _, planted, _ = _read(_panel(alpha=0.20))
    _, _, spread, mono = _read(_panel(alpha=0.0))

    assert abs(spread["gross_spread_pct"]) < 0.05 * planted["gross_spread_pct"]
    assert mono["monotone"] is False
    assert (mono["spearman_decile_vs_mean"]
            < config.CALIB_MONOTONE_MIN_SPEARMAN)

    # and the verdict the family adjustment reaches can never be CALIBRATED,
    # even if the spread's own p were handed to it as significant
    entry = {"signal": "planted", "verdict": None,
             "horizons": {"21": {"spread": spread, "monotonicity": mono}}}
    out = C7.family_verdict(entry, {"planted@21": 0.0001})
    assert out["verdict"] != C7.CALIBRATED


def test_the_two_nulls_are_both_run_and_both_reported():
    panel = _panel(alpha=0.20, n_months=72, n_names=120)
    rng = np.random.default_rng(config.CALIB_BOOTSTRAP_SEED)
    nulls = C7.run_nulls(panel, first_test_year=2009, h=21, rng=rng, draws=25)
    one = nulls["null_1_end_to_end_shuffle"]
    two = nulls["null_2_shuffled_distribution"]
    _, _, planted, _ = _read(panel)
    assert one["gross_spread_pct"] is not None
    # the shuffled replication must not reproduce the panel's own spread
    assert abs(one["gross_spread_pct"]) < 0.2 * planted["gross_spread_pct"]
    assert two["draws"] == 25 and two["n_spread_draws"] > 0
    assert "GROSS" in one["read_the_gross"]
    assert "GROSS against GROSS" in two["compared_on"]


# ===========================================================================
# THE REFUSALS — every one by name
# ===========================================================================


def test_a_leadable_signal_with_no_panel_builder_is_NO_PANEL_by_name():
    out = C7.calibrate_signal("rating_drift_3m", None, None, uni_block={},
                              start_year=2006)
    assert out["verdict"] == C7.NO_PANEL
    assert "PANEL_BUILDERS" in out["verdict_basis"]


def test_a_missing_table_is_NO_PANEL_naming_the_path(monkeypatch, tmp_path):
    def nothing(uni, *, start_year, smoke=False):
        return None, {"verdict": C7.NO_PANEL,
                      "why": "no such parquet on this checkout",
                      "looked_for": ["backend/data/optimus/nowhere.parquet"]}

    monkeypatch.setitem(C7.PANEL_BUILDERS, "profitability_small", nothing)
    out = C7.calibrate_signal("profitability_small", None, None, uni_block={},
                              start_year=2006)
    assert out["verdict"] == C7.NO_PANEL
    assert out["looked_for"] == ["backend/data/optimus/nowhere.parquet"]


def test_the_family_is_derived_from_the_adapters_and_the_registry():
    lead, excluded = C7.leadable_signals()
    assert set(lead) == {"profitability_small", "insider_opportunistic",
                         "fusion_insider_profitability"}
    assert "momentum_12_1" in excluded and "CLOSED" in excluded["momentum_12_1"]
    assert "low_volatility" in excluded and "FILTER" in excluded["low_volatility"]


def test_the_reader_skips_smoke_partial_stale_and_mislabelled_files(rooted):
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.1] * 10,
          cuts=list(np.linspace(0.1, 0.9, 9)), name="planted_2026-09-21_smoke.json")
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.1] * 10,
          cuts=list(np.linspace(0.1, 0.9, 9)),
          name="planted_2026-09-21.partial.json")
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.1] * 10,
          cuts=list(np.linspace(0.1, 0.9, 9)), asof="2020-01-01")
    blob, why = SC.latest_for("planted", asof=ASOF)
    assert blob is None
    assert "SMOKE" in why and "PARTIAL" in why and "CALIB_MAX_AGE_DAYS" in why


def test_the_reader_refuses_a_file_whose_body_disagrees_with_its_name(rooted):
    p = plant(rooted, "planted", verdict="CALIBRATED", means=[0.1] * 10,
              cuts=list(np.linspace(0.1, 0.9, 9)))
    blob = json.loads(p.read_text("utf-8"))
    blob["asof"] = "2026-01-01"
    p.write_text(json.dumps(blob), encoding="utf-8")
    out, why = SC.latest_for("planted", asof=ASOF)
    assert out is None and "disagrees with its own name" in why


def test_the_reader_refuses_a_wrong_schema(rooted):
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.1] * 10,
          cuts=list(np.linspace(0.1, 0.9, 9)), schema="something.else")
    out, why = SC.latest_for("planted", asof=ASOF)
    assert out is None and "schema" in why


def test_the_decile_tie_rule_matches_the_job(rooted):
    cuts = [0.0] * 9
    assert SC.decile_for(0.0, cuts) == 1        # a tied block falls to ONE bucket
    assert SC.decile_for(0.5, cuts) == 10
    assert SC.decile_for(None, cuts) is None
    assert SC.decile_for(0.5, []) is None
    n = 40 * config.CALIB_N_DECILES * config.CALIB_MIN_NAMES_PER_DECILE
    scores = [0.0] * (n // 2) + [1.0] * (n - n // 2)
    full = pd.concat([pd.DataFrame({"year": [2006] * n, "score": scores}),
                      pd.DataFrame({"year": [2009] * n, "score": scores})],
                     ignore_index=True)
    oos, wf = C7.assign_deciles(full, first_test_year=2009)
    # every zero falls into ONE bucket and every one into ONE other — two
    # levels, not ten, and the receipt says so rather than implying ten
    seen = set(oos["decile"])
    assert len(seen) == 2, seen
    lo = oos.loc[oos["score"] == 0.0, "decile"].unique().tolist()
    hi = oos.loc[oos["score"] == 1.0, "decile"].unique().tolist()
    assert lo == [min(seen)] and hi == [max(seen)]
    assert wf["n_nonempty_deciles"] == 2
    assert wf["largest_decile_share"] == pytest.approx(0.5)


# ===========================================================================
# THE WIRING — a per-name mu, and which source produced it
# ===========================================================================


def test_a_candidate_in_decile_3_gets_decile_3s_mu_not_the_family_mean(
        rooted, measured):
    means = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.90]
    cuts = list(np.linspace(0.1, 0.9, 9))
    p = plant(rooted, "planted", verdict="CALIBRATED", means=means, cuts=cuts)
    rec = _rec("AAA", "planted")
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.25}}
    out = roi_rank.rank([rec], candidates=cands, asof=ASOF,
                        calibration_root=rooted)
    body = out.rows["AAA"]
    assert body["mu_source"] == roi_rank.MU_CALIBRATION
    assert body["calibration_decile"] == 3
    # decile 3's own number, and NOT the family row's +0.50%/month x 24 months
    assert body["expected_return_net_pct"] == pytest.approx(means[2])
    assert body["expected_return_net_pct"] != pytest.approx(0.50 * 24)
    assert body["mu_basis"].endswith(p.name)
    assert body["roi_horizon_months"] == pytest.approx(1.0)


@pytest.fixture(autouse=True)
def _planted_adapter(monkeypatch):
    """`planted` and `unproven` are synthetic signal ids with no adapter.

    They borrow `profitability_small`'s field (`quality`) so that
    `roi_rank.raw_score_of` has a column to read the candidate's raw score off.
    What is under test is the decile lookup and the precedence, not which
    column carries the number.
    """
    real = roi_rank.adapter_field

    def fake(signal_id):
        if signal_id in ("planted", "unproven"):
            return "quality"
        return real(signal_id)

    monkeypatch.setattr(roi_rank, "adapter_field", fake)


def test_two_names_on_one_signal_get_different_mu(rooted, measured):
    means = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.90]
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "planted", verdict="CALIBRATED", means=means, cuts=cuts)
    recs = [_rec("AAA", "planted", rank=1), _rec("BBB", "planted", rank=2)]
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45, "median_dollar_vol": 5e7,
                     "quality": 0.95},
             "BBB": {"price": 20.0, "vol_annual": 0.20, "median_dollar_vol": 5e7,
                     "quality": 0.25}}
    out = roi_rank.rank(recs, candidates=cands, asof=ASOF,
                        calibration_root=rooted)
    assert out.rows["AAA"]["expected_return_net_pct"] != (
        out.rows["BBB"]["expected_return_net_pct"])
    # and the LOWER-VOL name no longer wins by default: the review's complaint
    assert out.rows["AAA"]["roi_score"] > out.rows["BBB"]["roi_score"]


def test_the_downside_is_the_decile_p20_and_says_so(rooted, measured):
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.3] * 10, cuts=cuts,
          p20s=[-12.5] * 10)
    rec = _rec("AAA", "planted")
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.5}}
    out = roi_rank.rank([rec], candidates=cands, asof=ASOF,
                        calibration_root=rooted)
    body = out.rows["AAA"]
    assert body["downside_source"] == roi_rank.DN_DECILE_P20
    assert body["downside_pct"] == pytest.approx(12.5)
    assert "MEASURED 20th percentile" in body["downside_basis"]


def test_the_vol_fallback_prints_its_own_name(rooted, measured):
    """A decile whose p20 is not negative has no measured downside."""
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.3] * 10, cuts=cuts,
          p20s=[+1.0] * 10)
    rec = _rec("AAA", "planted")
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.5}}
    out = roi_rank.rank([rec], candidates=cands, asof=ASOF,
                        calibration_root=rooted)
    # the name is not scored on a positive "downside": it falls back, and says so
    body = out.rows.get("AAA") or {}
    assert body, out.not_calibrated
    assert body["downside_source"] == roi_rank.DN_VOL
    assert "VOL FALLBACK" in body["downside_basis"]
    assert "not a downside" in body["downside_basis"]


# ===========================================================================
# PRECEDENCE, AND THE EXPLOIT GATE
# ===========================================================================


def test_a_calibrated_file_beats_the_family_row_and_licenses_EXPLOIT(
        rooted, measured):
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.3] * 10, cuts=cuts)
    rec = _rec("AAA", "planted")
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.5}}
    split = DA.assign([rec], candidates=cands, asof=ASOF,
                      calibration_root=rooted)
    assert split.authority_for("AAA") == DA.EXPLOIT
    assert split.roi.rows["AAA"]["mu_source"] == roi_rank.MU_CALIBRATION


def test_a_family_row_that_clears_the_t_floor_is_no_longer_enough_for_EXPLOIT(
        rooted, measured):
    """Chunk 22's tightening, stated as a test.

    `planted` has a family row at +0.50%/month with t 3.10 — it cleared
    ROI_MIN_T all through chunk 21 and would have been EXPLOIT. With no
    CALIBRATED map on disk it is refused from EXPLOIT by name, and the name is
    not frozen: it is EXPLORE's or it is nothing.
    """
    rec = _rec("AAA", "planted")
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.5}}
    split = DA.assign([rec], candidates=cands, asof=ASOF,
                      calibration_root=rooted)
    assert split.authority_for("AAA") != DA.EXPLOIT
    assert "CALIBRATED decile map" in split.refused["AAA"]


@pytest.mark.parametrize("verdict", ["INVERTED", "NO_PANEL", "REFUSED"])
def test_inverted_and_no_panel_leave_the_candidate_where_chunk_21_put_it(
        rooted, measured, verdict):
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "unproven", verdict=verdict, means=[0.3] * 10, cuts=cuts)
    rec = _rec("BBB", "unproven")
    cands = {"BBB": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.5}}
    split = DA.assign([rec], candidates=cands, asof=ASOF,
                      calibration_root=rooted)
    # chunk 21 made `unproven` (t 1.40, +0.17%/mo) an EXPLORE name; it still is
    assert split.authority_for("BBB") == DA.EXPLORE
    block = split.blocks["BBB"]["explore"]
    assert block["posterior_source"] == DA.POSTERIOR_FAMILY
    assert block["posterior_mean_pct_per_month"] == pytest.approx(0.17)


def test_a_WEAK_calibration_feeds_EXPLOREs_posterior_from_its_own_decile(
        rooted, measured):
    means = [-0.6, -0.4, -0.2, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.9]
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "unproven", verdict="WEAK", means=means, cuts=cuts,
          spread_t=1.2, holm_p=0.4)
    rec = _rec("BBB", "unproven")
    cands = {"BBB": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.95}}
    split = DA.assign([rec], candidates=cands, asof=ASOF,
                      calibration_root=rooted)
    assert split.authority_for("BBB") == DA.EXPLORE
    block = split.blocks["BBB"]["explore"]
    assert block["posterior_source"] == DA.POSTERIOR_DECILE
    assert block["calibration_decile"] == 10
    # decile 10's own mean, not the family's +0.17%/month
    assert block["posterior_mean_pct_per_month"] == pytest.approx(0.9)
    assert block["posterior_se_pct_per_month"] > 0
    assert "OWN decile" in block["posterior_basis"]


def test_a_WEAK_calibration_with_a_negative_decile_is_refused_not_explored(
        rooted, measured):
    means = [-0.6, -0.4, -0.2, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.9]
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "unproven", verdict="WEAK", means=means, cuts=cuts,
          spread_t=1.2, holm_p=0.4)
    rec = _rec("BBB", "unproven")
    cands = {"BBB": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.05}}
    split = DA.assign([rec], candidates=cands, asof=ASOF,
                      calibration_root=rooted)
    assert split.authority_for("BBB") == DA.REFUSED
    assert "EXPLORE_MIN_NET_PCT" in split.refused["BBB"]


def test_the_flag_is_a_true_revert(rooted, measured, monkeypatch):
    monkeypatch.setattr(config, "ROI_USE_CALIBRATION", False, raising=False)
    cuts = list(np.linspace(0.1, 0.9, 9))
    plant(rooted, "planted", verdict="CALIBRATED", means=[0.3] * 10, cuts=cuts)
    rec = _rec("AAA", "planted")
    cands = {"AAA": {"price": 20.0, "vol_annual": 0.45,
                     "median_dollar_vol": 5e7, "quality": 0.5}}
    out = roi_rank.rank([rec], candidates=cands, asof=ASOF,
                        calibration_root=rooted)
    body = out.rows["AAA"]
    assert body["mu_source"] == roi_rank.MU_FAMILY_MEAN
    assert body["expected_return_net_pct"] == pytest.approx(0.50 * 24)
    assert body["downside_source"] == roi_rank.DN_VOL


# ===========================================================================
# THE JOB'S CONTRACT WITH THE NIGHT FACTORY
# ===========================================================================


def test_the_job_is_registered_resumable_and_at_the_features_stage():
    from scripts.night_factory_jobs import JOB_STAGES, JOBS, RESUMABLE, STAGE_ORDER

    assert "C7_signal_calibration" in JOBS
    assert JOB_STAGES["C7_signal_calibration"] == "features"
    assert JOB_STAGES["C7_signal_calibration"] in STAGE_ORDER
    assert "C7_signal_calibration" in RESUMABLE


def test_the_output_path_separates_a_smoke_run_from_the_real_map():
    real = C7.output_path("planted", run_date="2026-09-21")
    smoke = C7.output_path("planted", run_date="2026-09-21", smoke=True)
    assert real != smoke
    assert "_smoke" in smoke.name and "_smoke" not in real.name


def test_the_run_date_is_never_a_literal():
    import re
    src = (C7.__file__.replace(".pyc", ".py"))
    text = open(src, encoding="utf-8").read()
    body = text.split('"""', 2)[-1]
    assert 'RUN_DATE = os.getenv("NIGHT_RUN_DATE")' in body
    assert not re.search(r'RUN_DATE\s*=\s*"20\d\d-\d\d-\d\d"', body)


def test_the_verdict_needs_monotonicity_as_well_as_a_significant_spread():
    spread = {"label": "D10 - D1", "net_spread_pct": 1.0, "net_t": 4.0,
              "gross_spread_pct": 1.1, "cost_pct": 0.1, "n_date_blocks": 120}
    entry = {"signal": "x", "horizons": {"21": {
        "spread": spread, "monotonicity": {"monotone": False,
                                           "verdict": "not monotone"}}}}
    out = C7.family_verdict(dict(entry), {"x@21": 0.001})
    assert out["verdict"] == C7.WEAK

    entry["horizons"]["21"]["monotonicity"] = {"monotone": True,
                                               "verdict": "monotone"}
    out = C7.family_verdict(dict(entry), {"x@21": 0.001})
    assert out["verdict"] == C7.CALIBRATED

    entry["horizons"]["21"]["spread"] = dict(spread, net_spread_pct=-1.0,
                                             net_t=-4.0)
    out = C7.family_verdict(dict(entry), {"x@21": 0.001})
    assert out["verdict"] == C7.INVERTED


def test_a_collapsed_decile_map_cannot_reach_CALIBRATED():
    """The insider score is 0.0 for most names; two buckets is not ten."""
    table = {"rows": [{"decile": 1, "n_names": 5000, "mean_abn_pct": -0.1,
                       "n_date_blocks": 120},
                      {"decile": 10, "n_names": 500, "mean_abn_pct": 0.5,
                       "n_date_blocks": 120}]}
    mono = C7.monotonicity(table)
    assert mono["monotone"] is None
    assert "CANNOT DETERMINE" in mono["verdict"]
    assert str(config.CALIB_MIN_NONEMPTY_DECILES) in mono["verdict"]
