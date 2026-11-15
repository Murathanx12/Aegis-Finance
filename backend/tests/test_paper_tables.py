"""scripts/paper_tables.py: the four properties a referee attacks first.

1. the persona/process classification is fixed BEFORE grading and cannot read outcomes;
2. a forecast frozen at or after its entry close is dropped (pre-window filter);
3. date-block clustering matches `forecast_reputation.date_blocks`;
4. the label simulation calls the REAL `book_dna.evidence_label`.

Fix round (review 2026-11-15): the volatility formula beside the arm MEAN and the
block rule on its verdict; `twin_of` and `book_path` pinned to `llm_portfolio.twins`
and `llm_portfolio.grade`; refusals; time-block intervals; the headline sentences.

Synthetic fixtures only; no network; dates derived from a fixed synthetic calendar.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from backend.services import book_dna as BD
from backend.services import forecast_reputation as FR
from backend.services import llm_portfolio as LP
from backend.services import xs_ranker as XR
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


# ══ fix round after the adversarial review (2026-11-15) ══════════════════════
ARMS = ("A_snapshot", "B_tools", "C_tools_only", "D_all", "B_anon")
ARM_P = (0.1, 0.2, 0.3, 0.4, 0.5)                      # mean 0.3, by construction


def _vol_fixture(n_days: int = 12, n_p1: int = 8):
    """Five arms x six tickers x `n_days` made days of h=1 magnitude rows.
    Five tickers have a quiet price history (sigma ~1%/day, so the formula says a
    3% move is very unlikely) and never move; `NOSIG` has no bars and always
    moves, which gives the stratum a base rate above zero."""
    rng = np.random.default_rng(11)
    made = pd.bdate_range("2030-03-20", periods=n_days)
    hist = pd.bdate_range(end=made[0] - pd.Timedelta(days=1), periods=100)
    tick = [f"VT{i}" for i in range(5)]
    bars = pd.DataFrame([{"symbol": t, "date": d, "close": c}
                         for t in tick
                         for d, c in zip(hist, 50 * np.cumprod(1 + rng.normal(0, 0.01, len(hist))))])
    rows = []
    for i, d in enumerate(made):
        for t in tick + ["NOSIG"]:
            for arm, p in zip(ARMS, ARM_P):
                rows.append({"kind": PT.PROCESS, "specialist": f"investigator:{arm}",
                             "observable": "abs_move_exceeds", "ticker": t, "threshold": "0.03",
                             "h": 1, "p": p, "y": 1.0 if t == "NOSIG" else 0.0,
                             "made_ts": pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=10),
                             "made_day": str(d.date()), "made_month": d.strftime("%Y-%m"),
                             "period": "P1" if i < n_p1 else "P2"})
    x = PT.add_reference(pd.DataFrame(rows))
    x["block"] = PT.assign_date_blocks(x)
    return x, bars, made


def _cell(rows, **want):
    hit = [r for r in rows if all(r.get(k) == v for k, v in want.items())]
    assert len(hit) == 1, (want, len(hit))
    return hit[0]


# ── 5. the volatility formula beside the LLM arms ────────────────────────────
def test_vol_prior_has_an_arm_mean_row_scored_as_one_forecast_per_ticker_day():
    x, bars, made = _vol_fixture()
    out = PT.vol_prior_rows(x, bars, 200, np.random.default_rng(5))
    rows_ = _cell(out, split="period", period="ALL", h=1, unit="arm_rows")
    mean_ = _cell(out, split="period", period="ALL", h=1, unit="arm_mean")
    assert rows_["n"] == 5 * 5 * len(made)             # arms x tickers with sigma x days
    assert mean_["n"] == 5 * len(made)                 # ONE forecast per ticker-day
    assert mean_["arms_per_ticker_day_min"] == mean_["arms_per_ticker_day_max"] == 5
    base = 1 / 6                                       # NOSIG's rows are in the stratum reference
    assert mean_["bss_llm"] == pytest.approx(1 - 0.3 ** 2 / base ** 2)
    assert rows_["bss_llm"] == pytest.approx(1 - np.mean(np.square(ARM_P)) / base ** 2)
    assert mean_["bss_vol_prior"] == pytest.approx(rows_["bss_vol_prior"]) and mean_["bss_vol_prior"] > 0.9
    meta = _cell(out, split="meta")
    assert meta["unit_arm_mean"]["arms"] == sorted(f"investigator:{a}" for a in ARMS)


def test_vol_prior_verdict_applies_the_block_rule_and_never_says_beats():
    x, bars, made = _vol_fixture(n_days=12, n_p1=8)
    out = PT.vol_prior_rows(x, bars, 200, np.random.default_rng(5))
    for unit in ("arm_rows", "arm_mean"):
        p1 = _cell(out, split="period", period="P1", h=1, unit=unit)
        # the formula wins every one of the 8 days and the interval excludes zero ...
        assert p1["n_date_blocks"] == 8 < PT.MIN_CLUSTERS_FOR_VERDICT
        assert p1["days_vol_prior_wins"] == 8 and p1["interval_excludes_zero"] is True
        # ... and it is still not a verdict: 8 blocks is below the rule
        assert p1["interval_read"] is False
        assert p1["verdict"].startswith("CANNOT_DISTINGUISH (too few blocks")
        allp = _cell(out, split="period", period="ALL", h=1, unit=unit)
        assert allp["n_date_blocks"] == 12 and allp["interval_read"] is True
        assert allp["verdict"] == "OBSERVED (vol prior above the LLM)"
    assert not any("beat" in str(r.get("verdict", "")).lower() for r in out)


def test_vol_prior_counts_rows_without_sigma_per_cell_and_breaks_out_months():
    x, bars, made = _vol_fixture(n_days=12, n_p1=8)
    out = PT.vol_prior_rows(x, bars, 100, np.random.default_rng(5))
    assert _cell(out, split="period", period="P1", h=1, unit="arm_rows")["n_rows_without_sigma"] == 8 * 5
    assert _cell(out, split="period", period="P2", h=1, unit="arm_rows")["n_rows_without_sigma"] == 4 * 5
    assert _cell(out, split="period", period="ALL", h=1, unit="arm_rows")["n_rows_without_sigma"] == 12 * 5
    assert _cell(out, split="period", period="P1", h=1, unit="arm_mean")["n_rows_without_sigma"] == 8
    months = {r["made_month"] for r in out if r.get("split") == "month"}
    assert months == {d.strftime("%Y-%m") for d in made} and len(months) == 2
    for mo in months:
        n_days = sum(1 for d in made if d.strftime("%Y-%m") == mo)
        c = _cell(out, split="month", made_month=mo, h=1, unit="arm_mean")
        assert c["n_days"] == n_days and c["n_rows_without_sigma"] == n_days


def test_vol_verdict_rule():
    assert PT.vol_verdict(8, -0.127, -0.037).startswith("CANNOT_DISTINGUISH (too few blocks")
    assert PT.vol_verdict(10, -0.127, -0.037) == "OBSERVED (vol prior above the LLM)"
    assert PT.vol_verdict(18, -0.033, 0.049) == "CANNOT_DISTINGUISH (interval spans 0)"
    assert PT.vol_verdict(18, 0.01, 0.05) == "OBSERVED (LLM above the vol prior)"


# ── 6. the twin draw and the cost convention, pinned to production ──────────
def _lp_bars(n: int = 90, seed: int = 21):
    """SPY + 3 mega (M), 6 large (L), 6 mid (D) and 6 small (S) names on a fixed
    synthetic calendar. The band letter is the LAST character and the bands are
    interleaved, so alphabetical order is not band order (the fallback pool in
    `llm_portfolio.twins` is alphabetical)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2030-01-07", periods=n)
    vol = {"SPY": 1e9}
    share_vol = {"M": 4e7, "L": 4e6, "D": 8e5, "S": 1e4}       # x ~$50 -> the four bands
    for i, band in enumerate("SLDMSLDMSLDMSLDSLDSLD"):
        vol[f"ZQ{i:02d}{band}"] = share_vol[band]
    rows = []
    for s, v in vol.items():
        c = 50 * np.cumprod(1 + rng.normal(0, 0.01, n))
        o = np.concatenate([[50.0], c[:-1]]) * (1 + rng.normal(0, 0.004, n))   # open != prior close
        rows += [{"symbol": s, "date": d, "open": float(a), "close": float(b), "volume": float(v)}
                 for d, a, b in zip(dates, o, c)]
    return pd.DataFrame(rows), dates


def _frozen_book(tickers, asof):
    w = 1.0 / len(tickers)
    return LP.freeze({"name": "pin", "objective": "beat SPY", "kind": "personal",
                      "positions": [{"ticker": t, "weight": w, "thesis": "x",
                                     "falsifier": "y"} for t in tickers]
                      + [{"ticker": "CASH", "weight": 0.0, "thesis": "none"}]}, today=asof)


@pytest.mark.parametrize("seed", [0, 1, 7, 20261115])
def test_twin_of_draws_what_llm_portfolio_twins_draws(seed):
    bars, dates = _lp_bars()
    asof = dates[69]
    # two of the three megas (the second finds its band empty and falls back to the
    # whole pool), two larges, one mid, and a name with no bars (no band: the pool)
    names = ["ZQ03M", "ZQ07M", "ZQ01L", "ZQ13L", "ZQ06D", "ZZNOBARS"]
    book = _frozen_book(names, str(asof.date()))
    prod = LP.twins(book, asof=asof, seed=seed, bars=bars)["random_same_band"]["positions"]
    prod = [p["ticker"] for p in prod if p["ticker"] != "CASH"]
    panel = PT.Panel(bars)
    bands, by_band = PT.bands_and_pool(panel, np.datetime64(asof))
    assert {b for b in bands.values()} == {"mega", "large", "mid", "small"}
    mine = PT.twin_of(names, bands, by_band, np.random.default_rng(seed))
    assert mine == prod
    assert not set(mine) & set(names) and len(set(mine)) == len(names)


def test_book_path_matches_llm_portfolio_grade_entry_and_cost():
    """Entry at the open of the session after `asof`, net of HALF the band round
    trip: the same NAV `llm_portfolio.grade` reports, to the cent."""
    bars, dates = _lp_bars()
    i0, L = 70, 20
    asof = dates[i0 - 1]
    names = ["ZQ03M", "ZQ04S", "ZQ10D"]                       # mega 6, small 35, mid 18 bps
    rec = _frozen_book(names, str(asof.date()))
    g = LP.grade(rec, bars)
    assert g["status"] == "OK" and g["to_date"]["sessions"] == L
    panel = PT.Panel(bars)
    bands, _ = PT.bands_and_pool(panel, np.datetime64(asof))
    half_bps = np.mean([XR.COST_BPS_BY_BAND[b] for b in ("mega", "small", "mid")]) / 2.0
    assert PT.entry_cost_fraction(names, bands) * 1e4 == pytest.approx(half_bps)
    assert g["entry_cost_bps"] == pytest.approx(half_bps, abs=0.05)   # production rounds to 0.1
    r = PT.book_path(panel, names, i0, L, bands)
    assert len(r) == L
    assert float(np.prod(1 + r)) - 1 == pytest.approx(g["to_date"]["net"], abs=1e-5)
    # the first period is open -> close of the entry session, less the entry cost
    j = [panel.col[s] for s in names]
    gross0 = float(np.mean(panel.C[i0, j] / panel.O[i0, j]))
    assert r[0] == pytest.approx(gross0 - half_bps / 1e4 - 1, abs=1e-6)
    assert abs(r[0] - (gross0 * (1 - 2 * half_bps / 1e4) - 1)) > 5e-4     # not the full round trip
    s = PT.spy_path(panel, i0, L)
    assert float(np.prod(1 + s)) - 1 == pytest.approx(g["to_date"]["benchmark_return"], abs=1e-5)


# ── 7. refusals and the receipt ──────────────────────────────────────────────
def test_load_deep_bars_refuses_instead_of_an_unstitched_concat(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("stitcher failed")
    monkeypatch.setattr(XR, "load_bars", boom)
    with pytest.raises(PT.Refusal, match="split-stitched"):
        PT.load_deep_bars([tmp_path / "bars.parquet"])


def test_a_panel_without_spy_is_a_named_refusal(monkeypatch, tmp_path):
    bars, _ = _lp_bars(n=30)
    no_spy = bars[bars["symbol"] != "SPY"]
    monkeypatch.setattr(XR, "load_bars", lambda *a, **k: no_spy)
    with pytest.raises(PT.Refusal, match="SPY"):
        PT.load_deep_bars([tmp_path / "bars.parquet"])
    with pytest.raises(PT.Refusal, match="SPY"):
        PT.spy_path(PT.Panel(no_spy), 5, 10)


def test_load_deep_bars_asof_drops_later_bars(monkeypatch, tmp_path):
    bars, dates = _lp_bars(n=30)
    monkeypatch.setattr(XR, "load_bars", lambda *a, **k: bars)
    b, how = PT.load_deep_bars([tmp_path / "x.parquet"],
                               asof=pd.Timestamp(dates[19], tz="UTC") + pd.Timedelta(hours=5))
    assert b["date"].max() == dates[19] and "--asof" in how


def test_main_exits_non_zero_when_there_is_no_panel(tmp_path, capsys):
    root = tmp_path / "optimus"
    root.mkdir()
    rc = PT.main(["--out", str(tmp_path / "out"), "--data-root", str(root), "--table", "2"])
    assert rc == PT.RC_REFUSED_INPUT != 0
    assert "REFUSED" in capsys.readouterr().out
    assert not list((tmp_path / "out").glob("table2_*.json"))


def test_stream_ledger_hashes_the_bytes_it_read_and_asof_ignores_later_rows(tmp_path):
    recs = [{"prediction_id": "a", "specialist": "s", "model": "m",
             "made_at": "2030-03-04T10:00:00+00:00", "outcome": 1,
             "resolved_at": "2030-03-05T21:00:00+00:00"},
            {"prediction_id": "b", "specialist": "s", "model": "m",
             "made_at": "2030-03-06T10:00:00+00:00", "outcome": 0,
             "resolved_at": "2030-03-12T21:00:00+00:00"},
            {"prediction_id": "c", "specialist": "s", "model": "m",
             "made_at": "2030-03-11T10:00:00+00:00", "outcome": None, "resolved_at": None}]
    p = tmp_path / "predictions.jsonl"
    p.write_bytes(("\n".join(json.dumps(r) for r in recs) + "\n").encode())
    D, O, stats = PT.stream_ledger(p)
    assert stats["sha256_of_bytes_read"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert stats["bytes_read"] == p.stat().st_size and stats["lines"] == 3
    D2, O2, info = PT.apply_asof(D, O, "2030-03-08T00:00:00Z")
    assert sorted(D2["prediction_id"]) == ["a", "b"]           # c was made after the cap
    o = O2.set_index("prediction_id")["outcome"]
    assert o["a"] == 1 and pd.isna(o["b"])                    # b resolved after the cap
    assert info["rows_made_after_asof_ignored"] == 1
    assert info["outcomes_resolved_after_asof_treated_as_ungraded"] == 1


# ── 8. Table 2 intervals come from time blocks, windows are (length, start) ──
def _sim_frame():
    rows = []
    starts = pd.bdate_range("2030-01-07", periods=12 * 63, freq="B")[::63]     # 12 quarters apart
    for q, d in enumerate(starts):
        for L in (21, 35):                                    # two lengths share each start date
            for j in range(100):
                rows.append({"L": L, "start": str(d.date()), "year": str(d.year),
                             "time_block": str(d.to_period("Q")),
                             "early": q % 2 == 0, "replicated_twin_route": False,
                             "replicated_any_route": q % 4 == 0,
                             "excess_pp": 1.0 if j < 40 else -1.0})
    return pd.DataFrame(rows)


def test_label_rates_interval_is_time_clustered_and_windows_are_length_start_pairs():
    sim = _sim_frame()
    r = PT.label_rates(sim.assign(_all="all"), ["_all"], 400, np.random.default_rng(9))[0]
    n_blocks = sim["time_block"].nunique()
    assert r["n_time_blocks"] == n_blocks >= PT.MIN_CLUSTERS_FOR_VERDICT
    assert r["time_block_interval_read"] is True
    assert r["n_windows"] == 2 * sim["start"].nunique()        # (L, start), not start dates
    lo, hi = r["early_or_higher_time_block_ci95"]
    wl, wh = r["early_or_higher_wilson95_books_as_independent"]
    assert lo < 0.5 < hi and (hi - lo) > 5 * (wh - wl)          # books in a block are one draw
    assert r["early_or_higher_by_window"] == {"min": 0.0, "p10": 0.0, "median": 0.5,
                                              "p90": 1.0, "max": 1.0}
    assert r["share_positive_excess_vs_spy"] == pytest.approx(0.4)
    assert r["median_excess_pp"] == -1.0
    assert "replicated_twin_or_sibling_upper_bound" in r and "upper bound" in PT.SIBLING_ROUTE_NOTE.lower()
    few = PT.label_rates(sim[sim["year"] == sim["year"].min()], ["year"], 100,
                         np.random.default_rng(9))[0]
    assert few["n_time_blocks"] < PT.MIN_CLUSTERS_FOR_VERDICT and few["time_block_interval_read"] is False


def test_zero_edge_symmetric_book_gets_the_label_about_two_times_in_five():
    z = PT.zero_edge_rate((30,), 3000, seed=13)
    assert z["n_books"] == 3000 and 0.37 < z["early_or_higher"] < 0.47


# ── 9. the three headline sentences ──────────────────────────────────────────
def test_headlines_rebuild_the_reviewed_sentences_from_a_receipt():
    r2 = {"sim_start_first": "2016-04-05", "panel_end": "2026-11-13",
          "zero_edge_symmetric": {"early_or_higher": 0.419},
          "all": [{"early_or_higher": 0.350, "early_or_higher_time_block_ci95": [0.301, 0.407],
                   "early_or_higher_by_window": {"min": 0.009, "max": 0.97},
                   "median_excess_pp": -0.9, "replicated_twin": 0.251,
                   "replicated_twin_or_sibling_upper_bound": 0.313}]}
    assert PT.headline_a(r2) == PT.REVIEW_HEADLINES["a"]
    census = {PT.PERSONA: {"n_rows": 20048, "n_made_days": 2, "first_day": "2026-08-11",
                           "last_day": "2026-08-12", "share_in_busiest_utc_hour": 0.9957}}
    assert PT.headline_b({"persona_made_census": census}) == PT.REVIEW_HEADLINES["b"]

    def cell(split, key, val, unit, nb, days, diff, lo, hi, h=1):
        return {"split": split, key: val, "h": h, "unit": unit, "n_date_blocks": nb,
                "n_days": days, "llm_minus_vol": diff, "interval_excludes_zero": lo > 0 or hi < 0,
                "interval_read": nb >= PT.MIN_CLUSTERS_FOR_VERDICT,
                "llm_minus_vol_ci_date_blocks": [lo, hi], "verdict": PT.vol_verdict(nb, lo, hi)}
    vol = [cell("period", "period", "ALL", "arm_mean", 18, 18, 0.005, -0.033, 0.049),
           cell("period", "period", "ALL", "arm_rows", 18, 18, -0.03, -0.07, 0.01),
           cell("period", "period", "P1", "arm_rows", 8, 8, -0.077, -0.127, -0.037),
           cell("month", "made_month", "2026-08", "arm_rows", 8, 8, -0.077, -0.127, -0.037),
           cell("month", "made_month", "2026-10", "arm_rows", 6, 6, -0.009, -0.05, 0.03),
           {"split": "meta", "sigma_window_sessions": 63,
            "unit_arm_mean": {"arms": [f"investigator:{a}" for a in ARMS]}}]
    assert PT.headline_c({"vol_prior": vol}) == PT.REVIEW_HEADLINES["c"]
    # a 3-block interval at the 5-day horizon is not a month's verdict: the month clause
    # reads the 1-day horizon, and the cell is listed under the headline instead of hidden
    vol.insert(5, cell("month", "made_month", "2026-10", "arm_rows", 3, 6, -0.027, -0.036, -0.021, h=5))
    assert PT.headline_c({"vol_prior": vol}) == PT.REVIEW_HEADLINES["c"]
    listed = PT.unread_exclusions({"vol_prior": vol})
    assert len(listed) == 3 and any(x.startswith("2026-10 h=5") for x in listed)
    # a month that clears the block rule is an OBSERVED cell, and the sentence stops saying "level"
    vol[3] = cell("month", "made_month", "2026-08", "arm_rows", 12, 12, -0.077, -0.127, -0.037)
    assert "do not read as level" in PT.headline_c({"vol_prior": vol})
