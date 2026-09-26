"""pit_features: strictly point-in-time, NaN below support, first_seen not published.

Every test is synthetic and offline. The central property is the first one:
appending rows dated ON or AFTER the decision date to EVERY input must leave
every column at that date unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import pit_features as pf
from backend.services import strategy_library as sl
from backend.services import strategy_library_ext as ext

D = pd.Timestamp("2024-06-03")          # a Monday decision date


def _sessions(end: pd.Timestamp, n: int = 400) -> pd.DatetimeIndex:
    return pd.bdate_range(end=end + pd.Timedelta(days=30), periods=n + 25)


def _bars(tickers=("AAA", "BBB"), end=D, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=end - pd.Timedelta(days=1), periods=260)
    rows = []
    for t in tickers:
        px = 50 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
        rows += [(t, d, p) for d, p in zip(days, px)]
    return pd.DataFrame(rows, columns=["symbol", "date", "close"])


def _revisions(end=D) -> pd.DataFrame:
    rows = []
    firms = ["Lead Co", "Follow A", "Follow B", "Follow C", "Lag Co"]
    # history: Lead Co moves first on many names, followers pile in within 7 days
    start = end - pd.Timedelta(days=700)
    for k in range(30):
        base = start + pd.Timedelta(days=20 * k)
        tk = "AAA" if k % 2 else "BBB"
        rows.append((tk, base, "Lead Co", "Raises", 10.0, 11.0))
        for j, f in enumerate(firms[1:4]):
            rows.append((tk, base + pd.Timedelta(days=j + 1), f, "Raises", 10.0, 11.0))
        rows.append((tk, base + pd.Timedelta(days=12), "Lag Co", "Raises", 10.0, 11.0))
    # recent: Lead Co raises AAA 10 days before D, Lag Co lowers BBB 5 days before
    rows.append(("AAA", end - pd.Timedelta(days=10), "Lead Co", "Raises", 10.0, 12.0))
    rows.append(("AAA", end - pd.Timedelta(days=9), "Follow A", "Raises", 10.0, 12.0))
    rows.append(("BBB", end - pd.Timedelta(days=5), "Lag Co", "Lowers", 12.0, 10.0))
    rows.append(("BBB", end - pd.Timedelta(days=4), "Follow B", "Lowers", 12.0, 10.0))
    df = pd.DataFrame(rows, columns=["ticker", "event_date", "firm", "target_action",
                                     "prior_target", "current_target"])
    df["pit_safe"] = True
    return df


def _actor(end=D) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for firm, p in (("LEADCO", 0.75), ("LAGCO", 0.35), ("FOLLA", 0.55)):
        for k in range(200):
            day = end - pd.Timedelta(days=900) + pd.Timedelta(days=3 * k)
            rows.append((firm, 1, int(rng.random() < p), day.isoformat() + "+00:00"))
    return pd.DataFrame(rows, columns=["estimid", "direction", "outcome", "public_at"])


FIRM_MAP = {"Lead Co": "LEADCO", "Lag Co": "LAGCO", "Follow A": "FOLLA"}


def _news(end=D, sessions=None) -> list[dict]:
    sessions = sessions if sessions is not None else _sessions(end)
    past = sessions[sessions < end][-140:]
    rows = []
    for s in past:
        rows.append({"first_seen_utc": f"{s.date()}T14:00:00+00:00", "tickers": "['BBB']",
                     "published_utc": f"{s.date()}T13:00:00+00:00"})
        rows.append({"first_seen_utc": f"{s.date()}T15:00:00+00:00", "tickers": "[]"})
    for s in past[-5:]:                  # AAA spikes in the last five sessions
        for _ in range(6):
            rows.append({"first_seen_utc": f"{s.date()}T16:00:00+00:00",
                         "tickers": "['AAA']", "published_utc": "2015-01-02T00:00:00+00:00"})
    return rows


def _facts(end=D) -> pd.DataFrame:
    """COGS grows 2%/yr through 2020, then 5%, 8%, 12%: cost pressure turns ON."""
    growth = {2017: .02, 2018: .02, 2019: .02, 2020: .02, 2021: .05, 2022: .08, 2023: .12}
    rows = []
    for i in range(160):                  # a broad market so the cost proxy has filers
        tk = "AAA" if i == 0 else ("BBB" if i == 1 else f"F{i:03d}")
        cogs = 60.0
        for y in range(2016, 2024):
            e = pd.Timestamp(f"{y}-12-31")
            filed = e + pd.Timedelta(days=45 + (i % 30))
            rev = 100.0 * (1.03 ** (y - 2016))
            cogs = cogs * (1 + growth.get(y, 0.0))
            c = rev * (0.60 - 0.01 * (y - 2016)) if tk == "AAA" else cogs  # AAA expands margin
            rows.append((tk, "revenue", filed, str(e.date()), 365.0, rev))
            rows.append((tk, "cogs", filed, str(e.date()), 365.0, c))
    return pd.DataFrame(rows, columns=["ticker", "fact", "filed", "end", "period_days", "val"])


def _compute(**over):
    sess = _sessions(D)
    kw = dict(bars=_bars(), revisions=_revisions(), news_rows=_news(sessions=sess),
              actor_corpus=_actor(), fundamentals=_facts(), firm_map=FIRM_MAP,
              tickers=["AAA", "BBB"], sessions=sess)
    kw.update(over)
    return pf.compute([D], **kw)


def test_shape_and_columns():
    out = _compute()
    assert list(out.index.names) == ["ticker", "date"]
    for c in pf.FEATURE_COLUMNS:
        assert c in out.columns and f"{c}_n" in out.columns
    a = out.loc[("AAA", D)]
    assert np.isfinite(a["max_21"]) and a["max_21_n"] >= 15
    assert np.isfinite(a["attention_z"]) and a["attention_z"] > 2
    assert np.isfinite(a["analyst_skill_weight"])
    assert np.isfinite(a["pricing_power_cost_pressure"])


def test_post_date_rows_change_nothing():
    """Rows dated on/after D in EVERY input must not move ANY column at D."""
    base = _compute()
    sess = _sessions(D)
    bars = _bars()
    fut_days = pd.bdate_range(D, periods=10)
    bars2 = pd.concat([bars, pd.DataFrame(
        [(t, d, 999.0) for t in ("AAA", "BBB") for d in fut_days],
        columns=["symbol", "date", "close"])], ignore_index=True)
    rev = _revisions()
    fut_rev = pd.DataFrame(
        [("AAA", D, "Lag Co", "Lowers", 12.0, 1.0), ("BBB", D + pd.Timedelta(hours=15), "Lead Co",
                                                     "Raises", 1.0, 99.0),
         ("BBB", D + pd.Timedelta(days=3), "Follow A", "Raises", 1.0, 99.0)],
        columns=["ticker", "event_date", "firm", "target_action", "prior_target", "current_target"])
    fut_rev["pit_safe"] = True
    rev2 = pd.concat([rev, fut_rev], ignore_index=True)
    news2 = _news(sessions=sess) + [
        {"first_seen_utc": f"{D.date()}T00:00:01+00:00", "tickers": "['BBB']"}] * 50 + [
        {"first_seen_utc": f"{(D + pd.Timedelta(days=2)).date()}T12:00:00+00:00",
         "tickers": "['AAA']"}] * 50
    actor2 = pd.concat([_actor(), pd.DataFrame(
        [("LAGCO", 1, 1, (D - pd.Timedelta(days=RES)).isoformat() + "+00:00")
         for RES in (0, 10, 50, 91)] * 200,
        columns=["estimid", "direction", "outcome", "public_at"])], ignore_index=True)
    facts2 = pd.concat([_facts(), pd.DataFrame(
        [("AAA", "revenue", D - pd.Timedelta(days=1), "2024-03-31", 365.0, 500.0),
         ("AAA", "cogs", D - pd.Timedelta(days=1), "2024-03-31", 365.0, 1.0),
         ("BBB", "revenue", D + pd.Timedelta(days=5), "2024-03-31", 365.0, 500.0),
         ("BBB", "cogs", D + pd.Timedelta(days=5), "2024-03-31", 365.0, 1.0)],
        columns=["ticker", "fact", "filed", "end", "period_days", "val"])], ignore_index=True)
    after = _compute(bars=bars2, revisions=rev2, news_rows=news2, actor_corpus=actor2,
                     fundamentals=facts2)
    pd.testing.assert_frame_equal(base, after)


def test_actor_claim_unresolved_before_date_is_ignored():
    """A claim public 10 days before D has not resolved (63 sessions): no effect."""
    base = _compute()
    extra = pd.DataFrame([("LAGCO", 1, 1, (D - pd.Timedelta(days=10)).isoformat() + "+00:00")] * 500,
                         columns=["estimid", "direction", "outcome", "public_at"])
    after = _compute(actor_corpus=pd.concat([_actor(), extra], ignore_index=True))
    pd.testing.assert_frame_equal(base, after)


def test_skill_weight_uses_reliability_and_prior():
    rel = pf.firm_reliability(_actor(), D)
    assert rel.loc["LEADCO", "weight"] > 1.0 > rel.loc["LAGCO", "weight"]
    out = _compute()
    # BBB's recent lowers: Lag Co (weight < 1) and Follow B (unmapped -> prior 1.0)
    w_lag = rel.loc["LAGCO", "weight"]
    assert out.loc[("BBB", D), "analyst_skill_weight"] == pytest.approx(-(w_lag + 1.0))
    # no actor corpus at all -> every firm at the prior -> plain net raises
    plain = _compute(actor_corpus=None)
    assert plain.loc[("BBB", D), "analyst_skill_weight"] == pytest.approx(-2.0)


def test_nan_below_support_never_zero():
    # a name with 5 bars: max_21 support 4 < 15
    short = _bars(tickers=("AAA",)).tail(5)
    out = _compute(bars=short)
    assert np.isnan(out.loc[("AAA", D), "max_21"]) and out.loc[("AAA", D), "max_21_n"] == 4
    # a single revision in the window: support 1 < 2
    rev = _revisions()
    one = rev[(rev["ticker"] == "AAA") & (rev["event_date"] == D - pd.Timedelta(days=10))]
    out = _compute(revisions=one)
    assert out.loc[("AAA", D), "analyst_skill_weight_n"] == 1
    assert np.isnan(out.loc[("AAA", D), "analyst_skill_weight"])
    # a news corpus only 20 sessions deep: baseline support 15 < 60 -> NaN, not 0
    sess = _sessions(D)
    thin = [r for r in _news(sessions=sess) if r["first_seen_utc"][:10] >= str(sess[sess < D][-20].date())]
    out = _compute(news_rows=thin)
    assert np.isnan(out.loc[("AAA", D), "attention_z"])
    assert np.isnan(out.loc[("AAA", D), "fomo_reversal"])
    # one annual filing: no margin change is possible
    f = _facts()
    f1 = f[(f["ticker"] != "AAA") | (f["end"] == "2016-12-31")]
    out = _compute(fundamentals=f1)
    assert np.isnan(out.loc[("AAA", D), "pricing_power_cost_pressure"])
    # missing inputs -> NaN with support 0
    out = _compute(bars=None, revisions=None, news_rows=None, fundamentals=None)
    for c in pf.FEATURE_COLUMNS:
        assert out[c].isna().all() and (out[f"{c}_n"] == 0).all()


def test_attention_uses_first_seen_not_published():
    sess = _sessions(D)
    rows = _news(sessions=sess)
    # published long ago, first seen AFTER D: must not count
    late = [{"first_seen_utc": f"{(D + pd.Timedelta(days=1)).date()}T10:00:00+00:00",
             "published_utc": "2024-05-20T10:00:00+00:00", "tickers": "['BBB']"}] * 100
    base = _compute(news_rows=rows)
    after = _compute(news_rows=rows + late)
    assert base.loc[("BBB", D), "attention_z"] == after.loc[("BBB", D), "attention_z"]
    # published AFTER D but first seen BEFORE it: must count (the stamp we own is first_seen)
    early = [{"first_seen_utc": f"{sess[sess < D][-1].date()}T10:00:00+00:00",
              "published_utc": "2030-01-01T00:00:00+00:00", "tickers": "['BBB']"}] * 30
    moved = _compute(news_rows=rows + early)
    assert moved.loc[("BBB", D), "attention_z"] > base.loc[("BBB", D), "attention_z"] + 2
    # and a frame with ONLY published_utc stamps contributes nothing
    nf = pf.news_frame([{"published_utc": "2024-05-30T00:00:00+00:00", "tickers": "['AAA']"}])
    assert nf.empty


def test_fomo_is_rev5_times_spike():
    out = _compute()
    a, b = out.loc[("AAA", D)], out.loc[("BBB", D)]
    assert a["attention_z"] > pf.ATT_SPIKE_Z and b["attention_z"] <= pf.ATT_SPIKE_Z
    assert b["fomo_reversal"] == 0.0
    bars = _bars()
    aa = bars[bars["symbol"] == "AAA"].sort_values("date")["close"].to_numpy()
    assert a["fomo_reversal"] == pytest.approx(aa[-1] / aa[-6] - 1.0)


def test_first_mover_rank_sign_and_leadership():
    out = _compute()
    # AAA's latest cluster was started by Lead Co (followed by 3 firms historically)
    assert out.loc[("AAA", D), "first_mover_rank"] > 0.5
    # BBB's latest cluster: a LOWER started by Lag Co (followed by nobody)
    v = out.loc[("BBB", D), "first_mover_rank"]
    assert v < 0 and abs(v) < abs(out.loc[("AAA", D), "first_mover_rank"])


def test_pricing_power_nan_when_pressure_off():
    # before 2021 cost growth is flat: no pressure -> NaN (unobservable), not 0
    d0 = pd.Timestamp("2020-06-01")
    out = pf.compute([d0], fundamentals=_facts(), tickers=["AAA"])
    assert np.isnan(out.loc[("AAA", d0), "pricing_power_cost_pressure"])
    # a caller-supplied pressure series is read strictly before the date
    cp = pd.Series([0.05, -1.0], index=[D - pd.Timedelta(days=30), D])
    out = pf.compute([D], fundamentals=_facts(), tickers=["AAA"], cost_pressure=cp)
    assert out.loc[("AAA", D), "pricing_power_cost_pressure"] > 0


def test_firm_mapping_by_cooccurrence():
    rev = pd.DataFrame({"ticker": ["AAA"] * 30 + ["BBB"] * 30,
                        "event_date": list(pd.bdate_range("2020-01-01", periods=30)) * 2,
                        "firm": ["Goldman Sachs"] * 30 + ["Tiny Shop"] * 30,
                        "current_target": [100.0 + i for i in range(30)] * 2})
    ib = pd.DataFrame({"oftic": ["AAA"] * 30, "anndats": pd.bdate_range("2020-01-01", periods=30),
                       "estimid": ["GOLDMAN"] * 30, "value": [100.0 + i for i in range(30)]})
    m, table = pf.map_firms_to_estimid(rev, ib)
    assert m == {"Goldman Sachs": "GOLDMAN"}


# ── the rule list ────────────────────────────────────────────────────────────

def test_extra_strategies_shape():
    assert len(ext.CHUNK_C_STRATEGIES) == 8
    ours = {r.id for r in ext.CHUNK_C_STRATEGIES}
    base = [r for r in sl.RULES if r.id not in ours]      # the library may already merge ours
    base_fams = set(sl.FAMILY_REASON) | {r.family for r in base}
    base_sigs = {r.signature() for r in base}
    for r in ext.CHUNK_C_STRATEGIES:
        m = r.meta()
        for k in ext.REQUIRED_KEYS:
            assert k in m, (r.id, k)
        assert m["economic_reason"] and m["source"].startswith("literature:")
        assert m["first_registered_utc"] == ext.REGISTERED_CHUNK_C
        assert r.family not in base_fams, f"{r.id}: family {r.family} is a base family"
        assert r.signature() not in base_sigs
    fwd = {r.id for r in ext.CHUNK_C_STRATEGIES if r.forward_only}
    assert fwd == {"attention_shock_fade", "fomo_reversal_5d", "fomo_reversal_21d"}
    lib = list(base)
    for r in ext.CHUNK_C_STRATEGIES:
        sl.register(lib, r)                   # no id clash, no signature twin
    assert not (set(getattr(sl, "EXTRA_REFUSED", {})) & ours), sl.EXTRA_REFUSED


def test_every_pit_column_has_a_rule():
    used = {c for r in ext.EXTRA_STRATEGIES for c in r.requires}
    assert set(pf.FEATURE_COLUMNS) <= used


def test_attach_maps_features_back_to_the_month_end_row(monkeypatch, tmp_path):
    """attach() computes at t+1d from rows dated <= t and lands on the row dated t."""
    bars = _bars()
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    syms = np.array(["AAA", "BBB"])
    close = bars.pivot(index="date", columns="symbol", values="close").reindex(
        index=dates, columns=syms).to_numpy()
    W = {"dates": dates.values, "symbols": syms, "close": close}
    monkeypatch.setattr(pf, "_optimus", lambda: tmp_path)   # no disk inputs: bars only
    t = dates[-1]
    panel = pd.DataFrame({"symbol": ["AAA", "BBB", "AAA"], "date": [t, t, dates[-2]],
                          "is_month_end": [True, True, False]})
    out, info = ext.attach(panel, W)
    assert list(out.index) == list(panel.index)
    aa = bars[bars["symbol"] == "AAA"].sort_values("date")["close"].to_numpy()
    r = aa[1:] / aa[:-1] - 1.0
    assert out.loc[0, "max_21"] == pytest.approx(r[-21:].max())      # includes t's close
    assert np.isnan(out.loc[2, "max_21"])                              # not a month-end row
    assert out["analyst_skill_weight"].isna().all()                    # no revisions on disk
