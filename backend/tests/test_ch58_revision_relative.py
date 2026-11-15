"""CH-58: known-answer tests on a synthetic WRDS-shaped folder under tmp_path.

No live data, no network. The synthetic years are fixed labels of a simulated
history, not a calendar moment: nothing here depends on today's date.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import ch58_revision_relative as M

Y0, Y1 = 2002, 2003          # labels of the simulated history
N_NAMES, N_GOOD, N_BAD, K = 90, 15, 15, 10


def _write_wrds(root: Path, *, planted_daily: float, good_beta: float, bad_beta: float, mkt_mean: float,
                idio_sd: float, seed: int, delist: bool = True) -> Path:
    """A WRDS-shaped folder: `good` names get monthly target raises, `bad` names cuts.

    `planted_daily` is the daily drift of good (+) and bad (-) names; betas let a
    test make the 'edge' pure market exposure instead."""
    rng = np.random.default_rng(seed)
    (root / "bulk").mkdir(parents=True)
    days = pd.bdate_range(f"{Y0 - 1}-01-01", f"{Y1 + 1}-12-31")
    mkt = rng.normal(mkt_mean, 0.005, len(days))
    permnos = np.arange(10001, 10001 + N_NAMES)
    good, bad = permnos[:N_GOOD], permnos[N_GOOD:N_GOOD + N_BAD]
    beta = np.where(np.isin(permnos, good), good_beta, np.where(np.isin(permnos, bad), bad_beta, 1.0))
    drift = np.where(np.isin(permnos, good), planted_daily, np.where(np.isin(permnos, bad), -planted_daily, 0.0))
    ret = mkt[:, None] * beta[None, :] + drift[None, :] + rng.normal(0, idio_sd, (len(days), N_NAMES))
    dead = int(bad[-1])
    dead_last = int(np.searchsorted(days, pd.Timestamp(f"{Y1}-06-16")))
    frames = []
    for j, p in enumerate(permnos):
        f = pd.DataFrame({"permno": int(p), "date": days, "prc": 50.0, "ret": ret[:, j], "vol": 1_000_000.0,
                          "openprc": 50.0})
        if delist and int(p) == dead:
            f = f.iloc[:dead_last + 1]
        frames.append(f)
    dsf = pd.concat(frames, ignore_index=True)
    for y in range(Y0 - 1, Y1 + 2):
        dsf[dsf["date"].dt.year == y].to_parquet(root / f"crsp_dsf_{y}.parquet", index=False)
    pd.DataFrame({"date": days, "mktrf": mkt, "rf": 0.0}).to_parquet(root / "ff_factors_daily.parquet", index=False)
    pd.DataFrame({"permno": [dead], "dlstdt": [days[dead_last]], "dlstcd": [552], "dlret": [-0.9]}
                 ).to_parquet(root / "bulk" / "crsp__dsedelist.parquet", index=False)
    pd.DataFrame({"ticker": [f"T{p}" for p in permnos], "permno": permnos.astype(float), "ncusip": "x",
                  "sdate": days[0], "edate": days[-1], "score": 1}
                 ).to_parquet(root / "bulk" / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet", index=False)
    rows = []
    months = pd.date_range(days[0], days[-1], freq="MS")
    for p in permnos:
        step = 1.05 if p in good else (0.95 if p in bad else 1.0)
        for firm in range(5 if int(p) == dead else 3):
            v = 100.0
            for m in months:
                rows.append({"ticker": f"T{p}", "amaskcd": float(firm), "estimid": f"B{firm}", "value": v,
                             "anndats": m + pd.Timedelta(days=9 + firm), "horizon": "12", "curr": "USD", "usfirm": 1})
                v *= step
    pd.DataFrame(rows).to_parquet(root / "bulk" / "ibes__ptgdet.parquet", index=False)
    return root


def _run(wrds: Path, out: Path) -> dict:
    return M.run(wrds, out, y0=Y0, y1=Y1, k=K, n_random=10, twin_draws=3, run_id="t")


@pytest.fixture(scope="module")
def planted(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("planted")
    w = _write_wrds(d / "wrds", planted_daily=0.001, good_beta=1.0, bad_beta=1.0, mkt_mean=0.0003,
                    idio_sd=0.005, seed=1)
    return {"rc": _run(w, d / "out"), "out": d / "out", "wrds": w}


@pytest.fixture(scope="module")
def pure_beta(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("beta")
    w = _write_wrds(d / "wrds", planted_daily=0.0, good_beta=1.8, bad_beta=0.4, mkt_mean=0.001,
                    idio_sd=0.004, seed=2)
    return {"rc": _run(w, d / "out"), "out": d / "out"}


def test_planted_relative_edge_is_recovered_with_the_right_sign(planted):
    res = planted["rc"]["results"]["R2"]
    for con in M.CONSTRUCTIONS:
        s = res[con]["with_delisting"]
        assert s["mean"] > 0, con
        assert s["t"] > 2, con
    tb = res["TOP_BOTTOM"]["gross_with_delisting"]["mean"]
    # +0.1% a day long and -0.1% a day short over 21 sessions is about +4.3% gross
    assert 0.03 < tb < 0.06
    # the hedged series carry (almost) no market exposure
    assert abs(res["BETA"]["with_delisting"]["realised_beta"]) < 0.25
    assert abs(res["TWIN"]["with_delisting"]["realised_beta"]) < 0.25


def test_costs_and_borrow_are_charged_on_both_legs(planted):
    b = planted["rc"]["results"]["R2"]["TOP_BOTTOM"]
    # every synthetic name trades $50M a day: the mid band, 18 bps a leg and 1% a year of borrow
    assert b["cost_per_hold_mean"] == pytest.approx(2 * 18e-4, rel=1e-6)
    assert b["borrow_per_hold_mean"] == pytest.approx(0.01 * 21 / 252, rel=1e-6)
    net, gross = b["with_delisting"]["mean"], b["gross_with_delisting"]["mean"]
    assert net == pytest.approx(gross - b["cost_per_hold_mean"] - b["borrow_per_hold_mean"], abs=1e-9)
    stress = b["borrow_x3"]["mean"]
    assert stress == pytest.approx(net - 2 * b["borrow_per_hold_mean"], abs=1e-9)


def test_a_pure_beta_edge_is_near_zero_after_the_hedge(pure_beta):
    res = pure_beta["rc"]["results"]["R2"]
    long_only = res["_control_long_only_minus_market"]["with_delisting"]
    hedged = res["BETA"]["gross_with_delisting"]
    assert long_only["mean"] > 0.008            # the unhedged book looks like an edge
    assert long_only["realised_beta"] > 0.5     # ... and it is market exposure
    assert abs(hedged["mean"]) < 0.004          # the beta hedge removes it
    assert abs(hedged["mean"]) < long_only["mean"] / 3
    assert abs(res["BETA"]["with_delisting"]["realised_beta"]) < 0.25
    assert res["BETA"]["hedge_ratio_mean"] == pytest.approx(1.8, abs=0.15)
    assert pure_beta["rc"]["verdict"] != "PASS"


def test_delisting_return_is_folded_in_and_reported_beside_the_number_without_it(planted):
    rc = planted["rc"]
    assert rc["delisting"]["names_with_a_delisting_record_in_span"] == 1
    assert rc["universe"]["delistings_inside_a_hold_on_the_eligible_set"] >= 1
    b = rc["results"]["R2"]["TOP_BOTTOM"]
    # the dead name is a SHORT: its -90% delisting return helps the hedged book
    assert b["with_delisting"]["mean"] > b["without_delisting"]["mean"]
    assert rc["panel"]["names_that_stop_trading"] == 1
    assert rc["panel"]["survivor_selected"] is False


def test_receipt_shape_and_no_per_security_rows(planted):
    out = planted["out"]
    rc = json.loads((out / "revision_relative_t.json").read_text(encoding="utf-8"))
    assert (out / "revision_relative_t.md").exists()
    assert rc["verdict"] in {"PASS", "FAILED_VARIANT", "CANNOT_DISTINGUISH"}
    assert rc["live_folder_files"]["unchanged"] is True
    assert rc["cells_computed"] == {"primary": 3, "all": 9, "note": rc["cells_computed"]["note"]}
    for con in M.CONSTRUCTIONS:
        s = rc["results"]["R2"][con]["with_delisting"]
        for key in ("mean", "t", "mde", "holm_one_sided", "holm_two_sided", "by_year", "leave_one_year_out",
                    "loo_worst_mean", "split", "realised_beta", "top_months_share_of_sum", "t_newey_west_lag1"):
            assert key in s, (con, key)
        assert s["mde"] == pytest.approx(2.8 * s["se"])
        assert rc["results"]["R2"][con]["random_control"]["n_draws"] == 10
        assert "gross_percentile_of_rule" in rc["results"]["R2"][con]["random_control"]
    text = json.dumps(rc)
    assert "long_names" not in text
    monthly = pd.read_csv(out / "revision_relative_t_monthly.csv")
    assert not any("permno" in c for c in monthly.columns)
    md = (out / "revision_relative_t.md").read_text(encoding="utf-8")
    assert "VERDICT (computed)" in md and "SURVIVORSHIP" in md and "MDE" in md


def test_survivorship_line_says_survivor_selected_when_nothing_dies():
    cal = pd.bdate_range("2001-01-01", periods=300)
    alive = pd.Series({1: cal[-1], 2: cal[-1], 3: cal[-3]})
    s = M.survivorship_line(alive, cal, 21)
    assert s["names_that_stop_trading"] == 0 and s["survivor_selected"] is True
    assert "SURVIVOR-SELECTED" in s["line"]
    s2 = M.survivorship_line(pd.Series({1: cal[-1], 2: cal[100]}), cal, 21)
    assert s2["names_that_stop_trading"] == 1 and s2["survivor_selected"] is False
    assert "CANNOT DETERMINE" in M.survivorship_line(pd.Series(dtype="datetime64[ns]"), cal, 21)["line"]


def test_holm_is_step_down_and_monotone():
    assert M.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    out = M.holm([0.5, float("nan"), 0.01])
    assert out[0] == pytest.approx(0.5) and np.isnan(out[1]) and out[2] == pytest.approx(0.02)


def _stat(t: float, mde: float, late: float, loo: float, holm_p: float) -> dict:
    return {"t": t, "mde": mde, "late_mean": late, "loo_worst_mean": loo, "loo_worst_year_dropped": 2010,
            "holm_one_sided": holm_p}


def test_verdict_is_computed_from_the_declared_conditions():
    ok = _stat(2.6, 0.004, 0.003, 0.002, 0.014)
    weak = _stat(0.4, 0.004, 0.001, 0.0005, 0.6)
    assert M.verdict({"TWIN": ok, "BETA": weak, "TOP_BOTTOM": weak})["verdict"] == "PASS"
    assert M.verdict_predeclared({"TWIN": ok, "BETA": weak, "TOP_BOTTOM": weak})["verdict"] == "PASS"
    # the regime check binds: a negative late window or a year that carries it is not a pass
    for bad in (_stat(2.6, 0.004, -0.001, 0.002, 0.014), _stat(2.6, 0.004, 0.003, -0.0001, 0.014),
                _stat(2.6, 0.004, 0.003, 0.002, 0.2), _stat(1.4, 0.004, 0.003, 0.002, 0.014)):
        for fn in (M.verdict, M.verdict_predeclared):
            v = fn({"TWIN": bad, "BETA": weak, "TOP_BOTTOM": weak})
            assert v["verdict"] == "FAILED_VARIANT" and v["failing_conditions"]["TWIN"]
    wide = _stat(0.4, 0.02, 0.001, 0.0005, 0.6)
    for fn in (M.verdict, M.verdict_predeclared):
        assert fn({"TWIN": wide, "BETA": wide, "TOP_BOTTOM": wide})["verdict"] == "CANNOT_DISTINGUISH"
        # one powered cell is enough to make the family a failure rather than "cannot distinguish"
        assert fn({"TWIN": wide, "BETA": weak, "TOP_BOTTOM": wide})["verdict"] == "FAILED_VARIANT"


def test_the_label_rests_on_the_median_prior_not_the_largest():
    med, top = float(np.median(M.CFG.CH58_PRIOR_EFFECTS)), M.CFG.CH58_PLAUSIBLE_MAX_EFFECT
    assert med < top == max(M.CFG.CH58_PRIOR_EFFECTS)
    # every MDE between the median and the largest prior: unpowered for the typical prior effect
    between = _stat(1.39, (med + top) / 2, 0.005, 0.002, 0.25)
    fam = {"TWIN": between, "BETA": between, "TOP_BOTTOM": between}
    assert M.verdict(fam)["verdict"] == "CANNOT_DISTINGUISH"
    assert M.verdict_predeclared(fam)["verdict"] == "FAILED_VARIANT"
    tight = _stat(0.4, med / 2, 0.001, 0.0005, 0.6)
    assert M.verdict({"TWIN": tight, "BETA": between, "TOP_BOTTOM": between})["verdict"] == "FAILED_VARIANT"


def test_pass_bar_power_and_forward_sample_are_computed():
    bar = M.pass_bar(3, 250)
    # 't >= 1.5 after Holm over three cells' asks the best cell for about t 2.02
    assert bar["t_implied_by_holm"] == pytest.approx(2.02, abs=0.02)
    assert M.pass_bar(1, 100_000)["t_implied_by_holm"] == pytest.approx(1.5, abs=0.01)
    # true effect = 1.39 se against a bar of 2.02: about one chance in four
    assert M.power_at(0.00299, 0.00299 / 1.39, bar["t_implied_by_holm"]) == pytest.approx(0.26, abs=0.02)
    assert M.power_at(0.0, 0.002, 1.645) == pytest.approx(0.05, abs=0.002)
    fs = M.forward_sample(0.003, 0.034)
    assert fs["months_for_power"] == pytest.approx(((1.959964 + 0.841621) * 0.034 / 0.003) ** 2, rel=1e-4)
    assert fs["months_for_expected_t"] == pytest.approx((1.5 * 0.034 / 0.003) ** 2, rel=1e-9)
    assert M.forward_sample(-0.001, 0.03)["months_for_power"] is None


def test_an_announcement_dated_on_the_decision_day_is_excluded():
    d = pd.Timestamp("2003-03-31")
    link = pd.DataFrame({"ticker": ["A", "B"], "permno": [1.0, 2.0], "sdate": pd.Timestamp("1990-01-01"),
                         "edate": pd.Timestamp("2030-01-01"), "score": 1})
    acts = pd.DataFrame({"ticker": ["A", "A", "B", "B", "B"], "estimid": ["X", "Y", "X", "X", "Y"],
                         "anndats": [d - pd.Timedelta(days=1), d, d, d + pd.Timedelta(days=1),
                                     d - pd.Timedelta(days=M.CFG.CH58_SIGNAL_WINDOW_DAYS + 5)],
                         "act": [1, 1, 1, 1, 1]}).sort_values("anndats").reset_index(drop=True)
    sig = M.signal(acts, link, d)
    # A: only the raise of the day before counts; B: same-day, next-day and stale raises all excluded
    assert sig.loc[1, "net"] == 1 and sig.loc[1, "n_firms"] == 1
    assert 2 not in sig.index
    # one day later the decision-day announcements have become usable
    sig2 = M.signal(acts, link, d + pd.Timedelta(days=1))
    assert sig2.loc[1, "net"] == 2 and sig2.loc[2, "net"] == 1


def test_a_twin_is_never_a_name_held_in_the_long_leg():
    # one cell of 12 names of which 9 are held: every draw must land on the 3 that are not
    n = 12
    panel_d = pd.DataFrame({"symbol": list(range(1, n + 1)), "eligible": True, "median_dollar_vol": 5e7,
                            "vol_63": 0.02, "mom_252_21": 0.1})
    cells = M.MT.cell_table(panel_d)
    ctx = {"cells": cells, "panel_d": panel_d, "cell_index": M.MT.CellIndex(cells)}
    held = list(range(1, 10))
    for seed in range(50):
        pairs, counts = M.draw_twin_pairs(held, ctx, np.random.default_rng(seed))
        twins = [t for _s, t, _lv in pairs if t is not None]
        assert not set(twins) & set(held)
        assert len(set(twins)) == len(twins) == 3          # only three free names exist; the rest go to cash
        assert counts["none"] == 6


def test_twin_guard_refuses_a_held_twin(monkeypatch):
    monkeypatch.setattr(M.MT, "draw_twins", lambda held, *a, **k: ([(held[0], held[1], "cell")], {"cell": 1}))
    with pytest.raises(RuntimeError, match="held name"):
        M.draw_twin_pairs([1, 2], {"cells": None, "panel_d": None, "cell_index": None}, np.random.default_rng(0))


def test_post_hoc_turnover_cost_is_marked_and_never_above_the_full_charge(planted):
    rc = planted["rc"]
    assert rc["verdict_as_predeclared"] in {"PASS", "FAILED_VARIANT", "CANNOT_DISTINGUISH"}
    assert "review" in rc["verdict_change_note"]
    assert rc["priors"]["median"] == pytest.approx(float(np.median(M.CFG.CH58_PRIOR_EFFECTS)))
    for con in M.CONSTRUCTIONS:
        b = rc["results"]["R2"][con]
        ph = b["post_hoc_cost_on_turnover"]
        assert ph["marked"].startswith("POST HOC")
        full = b["with_delisting"]["mean"]
        assert full <= ph["long_leg_only"]["mean"] + 1e-12 <= ph["both_legs"]["mean"] + 2e-12
        assert ph["cost_per_hold_mean_both_legs"] <= ph["cost_per_hold_mean_long_leg_only"] <= b["cost_per_hold_mean"] + 1e-12
        for key in ("split", "leave_one_year_out", "loo_worst_mean"):
            assert key in ph["long_leg_only"] and key in ph["both_legs"]
        assert b["power_at_observed_effect"]["at_holm_implied_t"] is not None
        assert "months_for_power" in b["forward_sample"]
    tw = rc["results"]["R2"]["TWIN"]
    d = tw["single_twin_basket_across_draws"]
    assert d["draws"] == 3 and d["mean_min"] <= d["mean_median"] <= d["mean_max"]
    # the mean of the per-draw means is the reported 3-draw figure
    assert "single_draw0_net_with_delisting" not in tw
    md = "\n".join(M.headline(rc))
    for needle in ("verdict_as_predeclared", "SELECTION (gross)", "AFTER COSTS", "POST HOC", "FORWARD SAMPLE",
                   "Real pass bar", "Priors"):
        assert needle in md, needle


def test_missing_input_exits_non_zero(tmp_path, planted):
    env = dict(os.environ, AEGIS_IGNORE_DOTENV="1", AEGIS_PERSONAL_MODE="0")
    repo = Path(M.__file__).resolve().parents[1]
    empty = tmp_path / "empty"
    empty.mkdir()
    for wrds in (tmp_path / "nowhere", empty):
        r = subprocess.run([sys.executable, "-m", "scripts.ch58_revision_relative", "--out", str(tmp_path / "o"),
                            "--wrds", str(wrds)], cwd=repo, env=env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 2, r.stderr[-500:]
        assert "REFUSED" in r.stderr
        assert not (tmp_path / "o").exists()
    # one yearly price file missing is a refusal too, never a silently shorter panel
    with pytest.raises(M.InputMissing):
        M.check_inputs(planted["wrds"], Y0 - 3, Y1)
    # writing into the input folder is refused
    assert M.main(["--out", str(planted["wrds"] / "sub"), "--wrds", str(planted["wrds"])]) == 2
