"""CH-12: grade the news already acted on -- offline tests on synthetic inputs.

Every date is derived from today (no calendar-moment literal); every input is
written under `tmp_path`; no network; no dependence on live data.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import ch12_news_grade as G

N_SYM = 160
N_SESS = 120
H = 5


def _sessions() -> list[date]:
    end = pd.Timestamp(date.today() - timedelta(days=21))
    return [d.date() for d in pd.bdate_range(end=end, periods=N_SESS)]


def _bars(path: Path, sessions: list[date], *, boost: dict[tuple[str, int], float] | None = None) -> Path:
    """Random-walk closes for S000..S159 and SPY. `boost[(sym, i)]` adds a
    one-session return at session index i (to plant an effect)."""
    rng = np.random.default_rng(7)
    rows = []
    syms = [f"S{i:03d}" for i in range(N_SYM)] + ["SPY"]
    for j, s in enumerate(syms):
        r = rng.normal(0.0, 0.02 if s != "SPY" else 0.01, size=len(sessions))
        for (bs, i), v in (boost or {}).items():
            if bs == s:
                r[i] += v
        px = 20.0 * np.exp(np.cumsum(r))
        vol = 1e5 * (1 + j % 7)
        for d, c in zip(sessions, px):
            rows.append({"symbol": s, "date": pd.Timestamp(d), "close": float(c), "volume": float(vol),
                         "vwap": float(c)})
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def _stamp(t: datetime) -> str:
    return t.strftime("%Y%m%dT%H%M%SZ")


def _buys_inputs(tmp_path: Path, *, plant: float = 0.0) -> dict:
    """fleet_manager dir (decisions + runs), digest dir and bars for 5 buy
    sessions x 4 news names; `plant` adds a return to each bought name on the
    session after entry."""
    ss = _sessions()
    buy_idx = [70, 76, 82, 88, 94]
    news = {i: [f"S{(k * 4 + n):03d}" for n in range(4)] for k, i in enumerate(buy_idx)}
    boost = {(s, i + 1): plant for i, names in news.items() for s in names} if plant else None
    bars = _bars(tmp_path / "live" / "bars.parquet", ss, boost=boost)
    fm = tmp_path / "live" / "fm"
    (fm / "runs").mkdir(parents=True)
    dg = tmp_path / "live" / "digest"
    dg.mkdir(parents=True)
    dec = []
    for i, names in news.items():
        d = ss[i]
        t_dec = datetime.combine(d, time(15, 0), tzinfo=timezone.utc)
        t_dig = t_dec - timedelta(hours=1)
        dname = f"world_digest_{_stamp(t_dig)}.json"
        (dg / dname).write_text(json.dumps({"themes": [{"title": "synthetic", "implications": [
            {"subject_type": "ticker", "subject": s, "direction": "up", "confidence": 0.6,
             "horizon_sessions": 5, "size_bucket": "normal"} for s in names]}]}), encoding="utf-8")
        rid = _stamp(t_dec) + "-abc"
        acts = []
        for s in names:
            coid = f"aegisfm-hack6-{d}-buy-{s}"
            dec.append({"role": "hack6", "row": "decision", "kind": "buy", "mode": "LIVE", "refused": None,
                        "session": str(d), "t": t_dec.isoformat(), "symbol": s, "coid": coid, "run_id": rid,
                        "inputs": {"held_plus_pending": 0}})
            acts.append({"coid": coid, "entry_status": "filled", "filled_avg_price": 20.0})
        dec.append({"role": "hack1", "row": "decision", "kind": "buy", "mode": "LIVE", "session": str(d),
                    "t": t_dec.isoformat(), "symbol": "S150", "coid": f"x-{d}", "run_id": rid})
        dec.append({"role": "hack6", "row": "decision", "kind": "sell", "mode": "LIVE", "session": str(d),
                    "t": t_dec.isoformat(), "symbol": "S151", "coid": f"y-{d}", "run_id": rid})
        (fm / "runs" / f"run_{rid}.json").write_text(json.dumps({"started_utc": t_dec.isoformat(), "accounts": [
            {"role": "hack6", "digest": {"file": dname}, "actions": acts}]}), encoding="utf-8")
    (fm / "decisions.jsonl").write_text("\n".join(json.dumps(r) for r in dec) + "\n", encoding="utf-8")
    uni = tmp_path / "live" / "universe.jsonl"
    # every name has a sector except S003 (a bought name, standing in for an ETF)
    uni.write_text("\n".join(json.dumps({"symbol": f"S{i:03d}", "identity": {"sector": f"sec{i % 3}"}})
                             for i in range(N_SYM) if i != 3) + "\n", encoding="utf-8")
    return {"fm": fm, "digest": dg, "bars": bars, "sessions": ss, "news": news, "universe": uni}


def _run_buys(inp: dict, out: Path, *extra: str) -> int:
    return G.main(["buys", "--fm-dir", str(inp["fm"]), "--digest-dir", str(inp["digest"]),
                   "--bars", str(inp["bars"]), "--out", str(out), "--before", str(date.today()),
                   "--universe", str(inp["universe"]), "--k", "20", "--k-sector", "10", "--run-id", "t1", *extra])


# ───────────────────────────── verdict and MDE ─────────────────────────────

def test_verdict_words_and_mde_with_few_blocks():
    v = G.scoped_verdict(0.05, 0.01, n_blocks=10, covers="c", does_not_cover="d", units="u", scope="s")
    assert v["verdict"] == "SUPPORTED_IN_SCOPE" and v["mde_80pct_power"] is not None and v["t"] == 5.0
    v = G.scoped_verdict(-0.05, 0.01, n_blocks=10, covers="c", does_not_cover="d", units="u", scope="s")
    assert v["verdict"] == "NOT_SUPPORTED_IN_SCOPE"
    v = G.scoped_verdict(0.01, 0.01, n_blocks=10, covers="c", does_not_cover="d", units="u", scope="s")
    assert v["verdict"] == "CANNOT_DISTINGUISH"
    v = G.scoped_verdict(0.5, None, n_blocks=1, covers="c", does_not_cover="d", units="u", scope="s")
    assert v["verdict"] == "CANNOT_DISTINGUISH" and v["mde_80pct_power"] is None
    # t = 2.5 clears 1.96 but not the 3-df critical value (3.18): few blocks widen the bar
    assert G.scoped_verdict(0.025, 0.01, n_blocks=4, covers="", does_not_cover="", units="",
                            scope="")["verdict"] == "CANNOT_DISTINGUISH"
    assert G.mde_of(0.01, 4) > G.mde_of(0.01, 400) > 0.027
    for v in G.VERDICTS:
        assert v in ("SUPPORTED_IN_SCOPE", "CANNOT_DISTINGUISH", "NOT_SUPPORTED_IN_SCOPE")


def test_block_se_counts_blocks_not_rows():
    vals = [1.0] * 50 + [3.0] * 50
    b = G.block_se(vals, ["a"] * 50 + ["b"] * 50)
    assert b["n_blocks"] == 2 and b["mean"] == 2.0
    c = G.coarser({"se": 0.1, "n_blocks": 30}, {"se": 0.2, "n_blocks": 4})
    assert c["n_blocks"] == 4
    # two blocks at a smaller SE still carry the larger MDE (df 1): they set the bar
    c = G.coarser({"se": 0.007, "n_blocks": 9}, {"se": 0.006, "n_blocks": 2})
    assert c["n_blocks"] == 2


def test_hit_rate_t_is_against_one_half():
    rows = [{"made_at": f"d{i % 4}", "_sidx": i % 4, "ticker": f"T{i % 8}"} for i in range(40)]
    x = G._two_block_se([1.0 if i % 2 else 0.0 for i in range(40)], rows, null=0.5)
    assert x["t_null"] == 0.5 and (x["t"] is None or abs(x["t"]) < 1e-6)


def test_leave_one_out_and_tail():
    lo = G.leave_one_out([1.0, 1.0, -5.0], ["a", "b", "c"])
    assert lo["by_left_out"]["c"] == 1.0 and lo["n_sign_flips"] == 1
    t = G.tail_check([10.0, 0.1, 0.1, 0.1, 0.1, 0.1, -0.5], [str(i) for i in range(7)])
    assert t["top5_share_of_total"] > 1.0 and t["direction_of_total"] == "positive"


def test_out_guard_refuses_live_folders(tmp_path):
    live = tmp_path / "live"
    (live / "x").mkdir(parents=True)
    f = live / "a.jsonl"
    f.write_text("", encoding="utf-8")
    assert G.out_guard(live / "out", [f]) is not None
    assert G.out_guard(tmp_path / "backend" / "data" / "o", []) is not None
    assert G.out_guard(tmp_path / "reports", [f]) is None


def test_draw_controls_never_returns_an_excluded_name():
    rng = np.random.default_rng(1)
    idx = [f"S{i:03d}" for i in range(100)]
    feat = pd.DataFrame({"dv20": np.linspace(1, 100, 100), "sigma63": np.tile([0.01, 0.02, 0.03, 0.04], 25),
                         "move5_sigma": 0.0, "n_hist": 63}, index=idx)
    excl = set(idx[::2])
    ctrls, band, pool = G.draw_controls(feat, sym="S001", sector_of={}, excluded=excl, k=5, rng=rng, no_chase=2.0)
    assert ctrls and not (set(ctrls) & excl) and "S001" not in ctrls


# ───────────────────────────── buys CLI ────────────────────────────────────

def test_buys_cli_writes_a_complete_receipt(tmp_path):
    inp = _buys_inputs(tmp_path)
    out = tmp_path / "reports"
    live_before = sorted(p.name for p in (tmp_path / "live").rglob("*"))
    assert _run_buys(inp, out) == 0
    assert sorted(p.name for p in (tmp_path / "live").rglob("*")) == live_before   # nothing written to inputs
    r = json.loads((out / "ch12_news_buys_t1.json").read_text(encoding="utf-8"))
    h = r["headline"]
    assert h["verdict"] in G.VERDICTS and h["mde_80pct_power"] is not None and h["t"] is not None
    assert h["n"] == 20 and r["sample"]["n"] == 20
    assert r["sample"]["row_ledger"]["rows_in_file"] == 30 and r["sample"]["row_ledger"]["after role"] == 25
    assert r["sample"]["dropped_after_sample"]["graded"] == 20
    for k in ("raw_news_mean", "raw_controls_mean", "raw_spy_mean", "excess_news_vs_spy_net_mean",
              "excess_controls_vs_spy_net_mean"):
        assert h[k] is not None
    s = r["results"]["V1_primary_all_buys_close_entry"]["summary"]
    assert s["n_entry_dates"] == 5 and s["n_effective_blocks_used"] <= 5
    assert s["by_month"] and s["leave_one_month_out_mean_d"]["by_left_out"]
    assert s["leave_one_5_session_block_out_mean_d"]["by_left_out"] and "top5_share_of_total" in s["tail"]
    assert r["results"]["V1_primary_all_buys_close_entry"]["controls_sharing_event_name"] == 0
    assert "bps per side" in h["cost"]
    for row in r["inputs"]:
        assert row["bytes"] > 0 and row["newest_date"]
    assert r["live_folder_file_counts"]["before"] == r["live_folder_file_counts"]["after"]
    # every control is a non-news name: the news names of each date are absent from its band draws
    assert all(u["n_controls"] >= 10 for u in r["units_primary"])   # --k-sector 10


def test_buys_planted_effect_is_seen(tmp_path):
    inp = _buys_inputs(tmp_path, plant=0.25)
    out = tmp_path / "reports"
    assert _run_buys(inp, out) == 0
    r = json.loads((out / "ch12_news_buys_t1.json").read_text(encoding="utf-8"))
    assert r["headline"]["d_news_minus_controls_mean"] > 0.15
    assert r["headline"]["raw_news_mean"] > r["headline"]["raw_controls_mean"]


def test_buys_missing_input_is_red(tmp_path):
    inp = _buys_inputs(tmp_path)
    inp["bars"] = tmp_path / "nope.parquet"
    out = tmp_path / "reports"
    assert _run_buys(inp, out) == 2
    assert not out.exists()


def test_buys_out_inside_input_is_refused(tmp_path):
    inp = _buys_inputs(tmp_path)
    out = inp["fm"] / "receipts"
    assert _run_buys(inp, out) == 2
    assert not out.exists()


# ───────────────────────────── forecasts CLI ───────────────────────────────

def _forecast_inputs(tmp_path: Path) -> dict:
    ss = _sessions()
    bars = _bars(tmp_path / "live" / "bars.parquet", ss)
    rng = np.random.default_rng(3)
    rows, n_late, n_pending, n_void = [], 0, 0, 0
    fams = {"news_digest:insider_v0": ("beats_benchmark", 0.5175),
            "news_digest:positioning_v0": ("abs_move_exceeds", 0.5),
            "news_digest:congress_v0": ("beats_benchmark", 0.515)}
    k = 0
    for i in range(66, 100, 2):
        d = ss[i]
        for f, (obs, p) in fams.items():
            for j in range(3):
                k += 1
                y = int(rng.random() < 0.5)
                late = j == 2 and f == "news_digest:insider_v0"
                made = datetime.combine(d, time(23 if late else 14, 0), tzinfo=timezone.utc)
                n_late += late
                vs = float(rng.normal(0, 0.03))
                rows.append({"prediction_id": f"p{k}", "ticker": f"S{(k % 150):03d}", "specialist": f,
                             "observable": obs, "horizon_days": 5, "probability": p,
                             "raw_probability": p + (0.07 if p != 0.5 else 0.0),
                             "threshold": 0.04 if obs == "abs_move_exceeds" else None,
                             "benchmark": "SPY" if obs == "beats_benchmark" else None,
                             "made_at": made.isoformat(), "resolves_after": str(ss[i + 7]),
                             "mechanism_id": "news_digest_v0",
                             "inputs_used": {"rule": "r1", "vol_prior_p": 0.45} if obs == "abs_move_exceeds"
                             else {"rule": "r2"},
                             "outcome": y, "brier": (p - y) ** 2, "resolved_at": str(ss[i + 7]),
                             "void_reason": None, "vs_benchmark": vs,
                             "resolution_detail": {"realised_return": vs + 0.001}})
    rows.append({**rows[0], "prediction_id": "pend", "outcome": None, "brier": None, "resolved_at": None})
    rows.append({**rows[1], "prediction_id": "void", "void_reason": "bar defect"})
    n_pending, n_void = 1, 1
    rows.append({"prediction_id": "other", "specialist": "llm:x", "made_at": rows[0]["made_at"]})
    pred = tmp_path / "live" / "predictions.jsonl"
    text = "\n".join(json.dumps(r) for r in rows) + '\n{"specialist": "news_digest:insider_v0", "torn\n'
    pred.write_text(text, encoding="utf-8")
    return {"pred": pred, "bars": bars, "n_graded": k, "n_late": n_late, "n_pending": n_pending, "n_void": n_void}


def _run_fc(inp: dict, out: Path) -> int:
    return G.main(["forecasts", "--predictions", str(inp["pred"]), "--bars", str(inp["bars"]), "--out", str(out),
                   "--graded-by", str(date.today()), "--n-boot", "100", "--k", "20", "--run-id", "t2"])


def test_forecasts_cli_writes_a_complete_receipt(tmp_path):
    inp = _forecast_inputs(tmp_path)
    out = tmp_path / "reports"
    live_before = sorted(p.name for p in (tmp_path / "live").rglob("*"))
    assert _run_fc(inp, out) == 0
    assert sorted(p.name for p in (tmp_path / "live").rglob("*")) == live_before
    r = json.loads((out / "ch12_news_forecasts_t2.json").read_text(encoding="utf-8"))
    led = r["sample"]["row_ledger"]
    assert led["check"] is True and led["unparseable_family_lines"] == 1
    assert led["graded_now"] == inp["n_graded"] and led["voided"] == 1 and led["pending_ungraded"] == 1
    assert led["excluded_made_at_or_after_window_start"] == inp["n_late"]
    assert led["scored_clean"] == inp["n_graded"] - inp["n_late"]
    assert r["sample"]["brier_recomputed_mismatches"] == 0
    for f in G.FAMILIES + ("pooled",):
        v = r["verdicts"][f]
        assert v["verdict"] in G.VERDICTS and v["mde_80pct_power"] is not None and v["scope_sentence"]
    for f in G.FAMILIES:
        c = r["results_clean"][f]["all"]
        assert c["brier_const_0_5"] == 0.25 and c["brier_climatology"] is not None
        rr = c["reliability_resolution_by_stated_p"]
        assert abs(rr["brier_identity"] - rr["brier_actual"]) < 1e-6
        assert c["leave_one_month_out_brier_minus_control"]["by_left_out"]
        assert "top5_share_of_total" in c["tail_brier_minus_control"]
        assert r["results_clean"][f]["by_month"]
    d = r["results_clean"]["news_digest:insider_v0"]["all"]["direction"]
    assert d["raw_signed_return_gross"]["mean"] is not None and d["signed_excess_vs_spy_gross"]["mde_80pct_power"]
    for row in r["inputs"]:
        assert row["bytes"] > 0 and row["newest_date"]


def test_forecasts_missing_input_is_red(tmp_path):
    out = tmp_path / "reports"
    rc = G.main(["forecasts", "--predictions", str(tmp_path / "none.jsonl"), "--bars",
                 str(tmp_path / "none.parquet"), "--out", str(out)])
    assert rc == 2 and not out.exists()


# ───────────────────────────── review round 1 ──────────────────────────────

def test_cluster_se_is_the_row_mean_estimator():
    vals = [1.0] * 90 + [3.0] * 10
    b = G.block_se(vals, ["a"] * 90 + ["b"] * 10)
    assert b["mean"] == 1.2 and b["estimator"].startswith("row mean")


def test_ticker_scheme_decides_when_few_names_carry_the_rows():
    rng = np.random.default_rng(5)
    vals = [float(v) for v in rng.normal(0.0, 0.2, size=200)]
    vals = [v + (1.0 if i % 2 else -0.2) for i, v in enumerate(vals)]   # the two names differ a lot
    tab = G.scheme_table(vals, dates=[i % 40 for i in range(200)], sess_idx=[i % 40 for i in range(200)],
                         tickers=["A" if i % 2 else "B" for i in range(200)])
    assert tab["schemes"]["ticker"]["n_blocks"] == 2 and tab["used_scheme"] == "ticker"
    assert tab["word"] == "CANNOT_DISTINGUISH"            # df 1: nothing short of a huge t clears 12.7


def test_a_word_stands_only_if_every_calendar_origin_agrees():
    rng = np.random.default_rng(11)
    for trial in range(40):
        n = 120
        sidx = list(rng.integers(0, 30, size=n))
        vals = list(rng.normal(rng.uniform(-0.6, 0.6), 1.0, size=n) + np.array(sidx) * rng.uniform(-0.05, 0.05))
        tab = G.scheme_table(vals, dates=sidx, sess_idx=sidx, tickers=[f"T{i % 60}" for i in range(n)])
        words = set(tab["origin_sweep"]["words"])
        if len(words) > 1:
            assert tab["word"] == "CANNOT_DISTINGUISH" and tab["word_override"]
        assert len(tab["origin_sweep"]["by_origin"]) == G.CAL_BLOCK_SESSIONS
        assert tab["origin_sweep"]["t_min"] is None or tab["origin_sweep"]["t_min"] <= tab["origin_sweep"]["t_max"]


def test_sector_tier_uses_the_smaller_k_and_can_require_a_sector():
    idx = [f"S{i:03d}" for i in range(120)]
    feat = pd.DataFrame({"dv20": np.linspace(1, 120, 120), "sigma63": 0.02, "move5_sigma": 0.0, "n_hist": 63},
                        index=idx)
    sector_of = {s: ("A" if i < 30 else "B") for i, s in enumerate(idx) if i != 7}
    rng = np.random.default_rng(2)
    ctrls, band, pool = G.draw_controls(feat, sym="S001", sector_of=sector_of, excluded=set(), k=50, rng=rng,
                                        no_chase=None, k_sector=5)
    assert band.startswith("sector") and 5 <= len(ctrls) <= 50 and all(sector_of.get(c) == "A" for c in ctrls)
    ctrls, band, _ = G.draw_controls(feat, sym="S001", sector_of=sector_of, excluded=set(), k=20, rng=rng,
                                     no_chase=None, k_sector=500, require_sector=True)
    assert not band.startswith("sector") and "S007" not in ctrls


def test_buys_receipt_carries_ex_etf_line_schemes_and_distribution(tmp_path):
    inp = _buys_inputs(tmp_path)
    out = tmp_path / "reports"
    assert _run_buys(inp, out) == 0
    r = json.loads((out / "ch12_news_buys_t1.json").read_text(encoding="utf-8"))
    a, x = r["headline_all_rows"], r["headline_ex_etf_sector_controls"]
    assert a["n"] == 20 and x["n"] == 19 and x["verdict"] in G.VERDICTS
    assert set(a["t_by_scheme"]) >= {"date", "ticker", f"calendar_{H}"} and a["origin_sweep_t"][0] is not None
    assert r["sector_matching"]["without_sector"] == ["S003"] and r["sector_matching"]["n_sector_matched_all_rows"] >= 1
    assert "V2_new_entries_only" not in r["results"] and "student_t" in r["critical_values_from"]
    assert "LIFT the controls" in r["survivorship"]
    assert r["verdict"]["origin_sweep"]["share_of_origins_agreeing_with_coarsest"] is not None


def test_forecast_receipt_has_ticker_scheme_sweep_and_panel_base_rate(tmp_path):
    inp = _forecast_inputs(tmp_path)
    out = tmp_path / "reports"
    assert _run_fc(inp, out) == 0
    r = json.loads((out / "ch12_news_forecasts_t2.json").read_text(encoding="utf-8"))
    h = r["headline"]["by_family"]["news_digest:insider_v0"]
    assert "ticker" in h["t_by_scheme"] and h["n_tickers"] and h["n_calendar_blocks"]
    assert h["origin_sweep"]["t_min"] is not None
    lb = r["results_clean"]["news_digest:insider_v0"]["all"]["direction"]["long_beat_spy_minus_panel_share"]
    assert 0.0 <= lb["panel_share_beating_spy_same_windows"] <= 1.0
    assert "tickers" in r["verdicts"]["news_digest:insider_v0"]["scope_sentence"]
