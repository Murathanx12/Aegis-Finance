"""CH-38 dip study: the pure parts on synthetic panels (no licensed data, no network)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import ch38_dip_study as S


def _W(C: np.ndarray, M: np.ndarray, V: float = 1e6, rf: float = 0.0, start: str = "2001-01-01") -> dict:
    T, N = C.shape
    dates = pd.bdate_range(start, periods=T)
    return S._study_arrays(dates, np.array([f"{k:06d}" for k in range(1, N + 1)], dtype=object), C,
                           np.full((T, N), V), C, np.zeros((T, N), dtype=bool), M, np.full(T, rf))


def _p(**kw) -> dict:
    p = S.params()
    p.update(kw)
    return p


def test_config_block_present_and_fixed():
    p = S.params()
    assert p["dip_drawdown"] == 0.30 and p["market_drawdown"] == 0.10
    assert p["horizons"] == [21, 63, 126] and p["stop_sigma"] == 3.0
    assert p["liquid_top_n"] > 0 and p["min_price"] == 5.0


def test_block_months_scale_with_horizon():
    assert [S.block_months(h) for h in (21, 63, 126)] == [1, 3, 6]


def test_nonoverlap_t_uses_every_origin_and_counts_blocks():
    idx = pd.date_range("2001-01-31", periods=24, freq="ME")
    x = pd.Series(np.arange(24, dtype=float) % 5 - 1.0, index=idx)
    pos = pd.Series(np.arange(24), index=idx)
    org = S.nonoverlap_t(x, pos, 3, 0.05, 0.80)
    assert [o["origin"] for o in org] == [0, 1, 2]
    assert all(o["n_blocks"] == 8 for o in org)
    v = x.to_numpy()[0::3]
    assert org[0]["mean"] == pytest.approx(v.mean())
    assert org[0]["t"] == pytest.approx(v.mean() / (v.std(ddof=1) / math.sqrt(8)))
    assert org[0]["mde"] > org[0]["se"] * 2.0
    x2 = x.copy()
    x2.iloc[::2] = np.nan                                 # an empty cell on half the dates
    assert sum(o["n_blocks"] for o in S.nonoverlap_t(x2, pos, 3, 0.05, 0.80)) == 12


def test_beta_matches_book_dna_formula():
    from backend.services import book_dna as BD
    rng = np.random.default_rng(0)
    m = rng.normal(0, 0.01, 252)
    r = 1.5 * m + rng.normal(0, 0.01, 252)
    b = S.beta_cols(r[:, None], m, 100)[0]
    ref = BD.beta_of([(None, float(y), float(x)) for x, y in zip(m, r)], 100)
    assert b == pytest.approx(ref.get("value", ref.get("beta_same_day")), abs=1e-3)
    r2 = r.copy()
    r2[:200] = np.nan
    assert np.isnan(S.beta_cols(r2[:, None], m, 100)[0])


def test_by_year_and_leave_one_year_out():
    idx = pd.to_datetime(["2001-01-31", "2001-02-28", "2002-01-31", "2003-01-31"])
    x = pd.Series([0.1, 0.3, -0.4, 0.0], index=idx)
    by = S.by_year(x)
    assert by["2001"]["mean"] == pytest.approx(0.2) and by["2001"]["n"] == 2
    loo = S.leave_one_year_out(x)
    assert loo["worst_dropped"] == "2001" and loo["worst"] == pytest.approx(-0.2)
    assert loo["best_dropped"] == "2002" and loo["best"] == pytest.approx(0.4 / 3)


def _panel(T: int = 420, N: int = 30, crash_cols=(0, 1, 2), seed: int = 1, sd: float = 0.005):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, sd, (T, N))
    C = 50.0 * np.cumprod(1 + r, axis=0)
    C[300:, list(crash_cols)] *= 0.5                     # a 50% gap in three names at row 300
    M = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.008, T))
    return C, M


def test_date_features_dip_liquidity_and_market_drawdown():
    C, M = _panel()
    M[300:] *= 0.85                                      # the market falls 15% at row 300
    V = np.ones_like(C) * 1e6
    V[:, 29] = 1.0                                       # one illiquid name
    W = S._study_arrays(pd.bdate_range("2001-01-01", periods=C.shape[0]),
                        np.array([f"{k:06d}" for k in range(1, 31)], dtype=object), C, V, C,
                        np.zeros(C.shape, dtype=bool), M, np.zeros(C.shape[0]))
    f = S.date_features(W, 310, _p(liquid_top_n=29))
    assert f["liquid"].sum() == 29 and not f["liquid"][29]
    assert all(f["off"][k] <= -0.30 for k in (0, 1, 2))
    assert f["mkt_dd"] <= -0.10
    assert f["off"][C[:311].argmax(axis=0) == 310].max() == pytest.approx(0.0)


def test_forward_and_stop_returns():
    T = 40
    C = np.full((T, 2), 100.0)
    C[5:, 0] = 95.0                                      # name 0 falls 5% at row 5 then flat
    C[3:, 1] = 110.0                                     # name 1 rises
    C[25:, 1] = np.nan                                   # and dies (held at its last value)
    W = _W(C, np.full(T, 100.0), rf=0.001)
    W["Cf"] = S.ffill_cols(C)
    fwd = S.forward_returns(W, 1, np.array([0, 1]), [21])
    assert fwd[0, 0] == pytest.approx(-0.05) and fwd[1, 0] == pytest.approx(0.10)
    sr, hit = S.stop_returns(W, 1, np.array([0, 1]), np.array([0.01, 0.01]), 3.0, [21])
    assert hit[0, 0] and not hit[1, 0]
    # exit at the close AFTER the first close below 97: 95, then cash at rf from row 6 to row 22
    assert sr[0, 0] == pytest.approx(0.95 * (1.001 ** 16) - 1.0)
    assert sr[1, 0] == pytest.approx(0.10)
    far = S.forward_returns(W, 30, np.array([0]), [21])
    assert np.isnan(far[0, 0])                           # past the calendar: never filled


def test_date_events_twins_come_from_the_non_dip_pool():
    C, M = _panel(T=420, N=40, crash_cols=(0, 1, 2, 3))
    C[312:, :4] *= 1.20                                  # dip names rebound 20% after the entry close
    W = _W(C, M)
    rng = np.random.default_rng(3)
    rec, frames = S.date_events(W, 310, _p(liquid_top_n=40, twin_draws=8, twin_draws_sweep=2), rng)
    prim = [f for f in frames if f["thr"].iloc[0] == 0.30][0]
    assert set(prim["symbol"]) == {"000001", "000002", "000003", "000004"}
    assert rec["n_dip_0.30"] == 4
    assert (prim["net_21"] > 0.15).all()
    assert (prim["twin_21"].abs() < 0.15).all()          # twins are ordinary names, not the dips
    assert prim["_draws"].iloc[0].shape == (8, 3)
    assert {"stop_21", "twin3_21", "beta", "rt"} <= set(prim.columns)


def test_verdict_rule():
    def stats(mean, t, n=10, loo_w=0.01, loo_b=0.02, ypos=8, yrs=10):
        return {"mean": mean, "origins": [{"t": t, "t_crit": 2.0, "n_blocks": n}] * 3, "t_min": t, "t_max": t,
                "mde_max": 0.02, "min_blocks": n, "loo": {"worst": loo_w, "best": loo_b, "worst_dropped": "2009"},
                "years": yrs, "years_positive": ypos}
    assert S.verdict(stats(0.02, 3.0), {"mean": 0.01}, 0.01, 0.05)[0] == "ADMIT"
    assert S.verdict(stats(0.02, 3.0), {"mean": 0.01}, -0.01, 0.05)[0] == "CANNOT_DISTINGUISH"   # sweep
    assert S.verdict(stats(0.02, 3.0, n=5), {"mean": 0.01}, 0.01, 0.05)[0] == "CANNOT_DISTINGUISH"
    assert S.verdict(stats(0.02, 1.0), {"mean": 0.01}, 0.01, 0.05)[0] == "CANNOT_DISTINGUISH"
    assert S.verdict(stats(-0.02, -3.0), {"mean": 0.01}, 0.01, 0.05)[0] == "REJECT"
    assert S.verdict(stats(-0.01, -1.0, loo_w=-0.02, loo_b=-0.001), {"mean": -0.01}, 0.0, 0.05)[0] == "REJECT"
    assert S.verdict(stats(-0.01, -1.0, loo_w=-0.02, loo_b=0.001), {"mean": -0.01}, 0.0, 0.05)[0] \
        == "CANNOT_DISTINGUISH"


def test_profitability_is_point_in_time():
    ev = pd.DataFrame({"date": pd.to_datetime(["2005-03-31", "2005-06-30"]), "symbol": ["000007", "000007"]})
    prof = pd.DataFrame({"permno": [7, 7], "public_date": pd.to_datetime(["2005-02-28", "2005-05-31"]),
                         "npm": [0.05, -0.10]})
    flag = S.attach_profitability(ev, prof)
    assert flag.tolist() == [0.0, 1.0]
    late = prof.assign(public_date=pd.to_datetime(["2005-04-30", "2005-07-31"]))
    assert np.isnan(S.attach_profitability(ev, late).iloc[0])


def test_month_end_rows():
    d = pd.bdate_range("2003-01-01", "2003-04-30")
    rows = S.month_end_rows(d, 2003)
    assert [d[r].month for r in rows] == [1, 2, 3, 4]
    assert all(d[r + 1].month != d[r].month for r in rows[:-1])


def test_refuses_out_inside_the_data_root(tmp_path: Path, capsys):
    root = tmp_path / "data" / "optimus"
    root.mkdir(parents=True)
    rc = S.main(["--data-root", str(root), "--out", str(tmp_path / "data" / "out"), "--run-id", "t"])
    assert rc == 2 and "REFUSED" in capsys.readouterr().out
    assert not (tmp_path / "data" / "out" / "ch38_dip_study_t_DECLARATION.json").exists()


def test_missing_input_refuses_red(tmp_path: Path, capsys):
    root = tmp_path / "data" / "optimus"
    (root / "wrds").mkdir(parents=True)
    rc = S.main(["--data-root", str(root), "--out", str(tmp_path / "elsewhere"), "--run-id", "t", "--no-oop"])
    assert rc == 2 and "REFUSED" in capsys.readouterr().out


def _stats(mean: float, t: float = 1.0) -> dict:
    return {"mean": mean, "t_min": t, "t_max": t, "mde_max": 0.02, "min_blocks": 10,
            "loo": {"worst": mean - 0.001, "best": mean + 0.001, "worst_dropped": "2009", "best_dropped": "2002"},
            "years": 10, "years_positive": 6, "by_year": {}, "share_by_date": {"top_5pct_of_months": 0.4}}


def _receipt() -> dict:
    p = S.params()
    p["horizons"] = list(p["horizons"])
    prim, spec = {}, {}
    for arm in S.ARMS:
        for cell in ("v1", "all"):
            for h in p["horizons"]:
                k = f"{arm}|{cell}|{h}"
                good = arm == S.ARMS[0] and cell == "v1" and h == 21
                prim[k] = {"n_dates": 12, "mean_names_per_date": 5.0, "raw_net_mean": 0.01 if good else -0.01,
                           "basket_beta_mean": 1.2, "beta_share_of_raw_excess_over_cash": 0.5 if good else None,
                           "excess_vs_twin": _stats(0.01 if good else -0.01, 2.5 if good else -2.5),
                           "excess_vs_beta_line": _stats(0.003 if good else -0.01),
                           "stop_vs_hold": {"mean": -0.002}, "share_stopped": 0.4, "stop_label": "STOP_BELOW_HOLD",
                           "verdict": "ADMIT" if good else "REJECT"}
                spec[k] = {"excess_vs_twin": {"mean": 0.005}, "excess_vs_beta_line": {"mean": -0.001 if good else -0.02}}
    return {"run_id": "t", "declaration_sha16": "x", "params": p, "primary": prim,
            "sweep_dip_drawdown": {"0.20": spec, "0.40": spec}, "sweep_market_drawdown": {"0.05": spec, "0.15": spec},
            "sensitivity_nominal_20m": spec}


def test_final_reading_keeps_declared_verdicts_and_prints_fragility():
    rec = _receipt()
    fr = S.final_reading(rec, None)
    assert fr["admitted"] == [f"{S.ARMS[0]}|v1|21"]
    row = [x for x in fr["cells"] if x["cell"] == f"{S.ARMS[0]}|v1|21"][0]
    assert row["verdict"] == "ADMIT"                           # the declared rule's, never re-decided
    assert row["sens_beta_nonpositive"] == 5 and row["sens_n"] == 5
    assert fr["variants"]["crsp_specifications"] == 6
    assert fr["variants"]["crsp_cell_readings"] == 6 * len(fr["cells"])
    assert fr["arms"][S.ARMS[0]]["stop"]["below_hold"] == fr["arms"][S.ARMS[0]]["stop"]["cells"]
    md = "\n".join(S.render_final(fr, rec))
    assert md.startswith(S.FINAL_MARK) and "Variants tried" in md and "Stop versus hold" in md


def test_episode_snapshot_counts_dips_and_names_the_arm():
    C, M = _panel(T=420, N=30)
    M[300:] *= 0.85
    W = _W(C, M)
    s = S.episode_snapshot(W, 310, _p(liquid_top_n=30))
    assert s["n_dip_0.30"] == 3 and s["arm"] == S.ARMS[0]
    assert sum(s["by_vol_tercile"].values()) == 3
    assert {n["symbol"] for n in s["_names"]} == {"000001", "000002", "000003"}
    calm = S.episode_snapshot(_W(C, np.linspace(100.0, 140.0, C.shape[0])), 310, _p(liquid_top_n=30))
    assert calm["arm"] == S.ARMS[1]


def test_addendum_refuses_without_a_receipt_and_never_overwrites(tmp_path: Path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    rc = S.main(["--data-root", str(tmp_path / "root"), "--out", str(out), "--run-id", "t", "--addendum"])
    assert rc == 2 and "REFUSED" in capsys.readouterr().out
    import json
    (out / "ch38_dip_study_t.json").write_text(json.dumps(_receipt()), encoding="utf-8")
    (out / "ch38_dip_study_t.md").write_text("# receipt\n", encoding="utf-8")
    rc = S.main(["--data-root", str(tmp_path / "root"), "--out", str(out), "--run-id", "t", "--addendum",
                 "--no-episode"])
    assert rc == 0
    assert S.FINAL_MARK in (out / "ch38_dip_study_t.md").read_text(encoding="utf-8")
    assert (out / "ch38_dip_study_t_ADDENDUM.json").exists()
    rc = S.main(["--data-root", str(tmp_path / "root"), "--out", str(out), "--run-id", "t", "--addendum",
                 "--no-episode"])
    assert rc == 2                                             # second run refuses, nothing appended twice
    assert (out / "ch38_dip_study_t.md").read_text(encoding="utf-8").count(S.FINAL_MARK) == 1
