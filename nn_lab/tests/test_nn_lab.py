"""nn_lab tests: synthetic data only, dates derived from today, no network, no GPU."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from nn_lab import config as C
from nn_lab import nightly as N
from nn_lab import seeds as S
from nn_lab import table as T
from nn_lab.splits import Fold, check_fold, walk_forward_folds


def _sessions(n: int) -> pd.DatetimeIndex:
    end = pd.Timestamp(date.today()) - pd.offsets.BDay(1)
    return pd.bdate_range(end=end, periods=n)


def _bars(n_sessions=320, n_sym=40, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cal = _sessions(n_sessions)
    rows = []
    for s in [C.MARKET] + [f"S{i:02d}" for i in range(n_sym)]:
        r = rng.normal(0.0005, 0.02, n_sessions)
        close = 50 * np.exp(np.cumsum(r))
        op = close * (1 + rng.normal(0, 0.003, n_sessions))
        rows.append(pd.DataFrame({"symbol": s, "date": cal, "open": op, "high": close * 1.01,
                                  "low": close * 0.99, "close": close,
                                  "volume": np.full(n_sessions, 2e5, dtype="float32"),
                                  "vwap": close, "trades": np.full(n_sessions, 1000.0)}))
    return pd.concat(rows, ignore_index=True)


# ── 1. the table never uses a value dated after (or on) the decision date ────

def test_fundamentals_refuse_a_filing_dated_on_or_after_t():
    t = pd.Timestamp(date.today()) - pd.offsets.BDay(5)
    rows = pd.DataFrame({"symbol": ["AAA"], "date": [t], "close": [10.0], "close_raw": [10.0]})
    facts = pd.DataFrame({
        "ticker": ["AAA"] * 4, "fact": ["net_income", "net_income", "shares", "shares"],
        "filed": [t - pd.Timedelta(days=40), t + pd.Timedelta(days=1),   # the second is FUTURE
                  t - pd.Timedelta(days=40), t],                          # filed ON t: not usable at t
        "end": [t - pd.Timedelta(days=60), t - pd.Timedelta(days=5), t - pd.Timedelta(days=60), t],
        "period_days": [90.0, 90.0, np.nan, np.nan],
        "val": [1e6, 9e9, 1e7, 5e9]})
    f = T.fundamentals(rows, facts)
    # earnings yield uses the OLD filing (1e6 * 4), the OLD share count (1e7) and the
    # UNADJUSTED close (review F1): 4e6 / 1e8
    assert f["f_ey"].iloc[0] == pytest.approx(4e6 / (10.0 * 1e7), rel=1e-4)
    assert pd.Timestamp(f["fund_filed_max"].iloc[0]) < t


def test_analyst_and_news_ignore_events_on_or_after_t():
    t = pd.Timestamp(date.today()) - pd.offsets.BDay(3)
    rows = pd.DataFrame({"symbol": ["AAA"], "date": [t], "close": [10.0]})
    rev = pd.DataFrame({"ticker": ["AAA"] * 3,
                        "event_date": [t - pd.Timedelta(days=10), t + pd.Timedelta(hours=2),
                                       t + pd.Timedelta(days=3)],
                        "action": ["up", "up", "up"], "target_change": [0.1, 0.5, 0.9]})
    a = T.analyst(rows, rev, pit_from=t - pd.Timedelta(days=30))   # PIT inside the snapshot
    assert a["an_up_63"].iloc[0] == 1.0
    assert a["an_tgt_chg_63"].iloc[0] == pytest.approx(0.1, rel=1e-5)
    panel = pd.DataFrame({"symbol": ["AAA"] * 3,          # coverage starts 60 days before t
                          "published_utc": [str((t - pd.Timedelta(days=60)).date()) + "T12:00:00Z",
                                            str((t - pd.Timedelta(days=2)).date()) + "T12:00:00Z",
                                            str(t.date()) + "T15:00:00Z"]})
    n = T.news(rows, panel)
    assert n["news_n_5"].iloc[0] == pytest.approx(np.log1p(1.0))


def test_assert_pit_raises_on_a_planted_future_stamp():
    t = pd.Timestamp(date.today())
    df = pd.DataFrame({"symbol": ["A", "B"], "date": [t, t],
                       "fund_filed_max": [t - pd.Timedelta(days=3), t + pd.Timedelta(days=1)]})
    with pytest.raises(T.PITViolation):
        T.assert_pit(df)
    df.loc[1, "fund_filed_max"] = t - pd.Timedelta(days=1)
    assert T.assert_pit(df)["fund"] == 0


def test_price_features_do_not_change_when_the_future_changes():
    b = _bars()
    cal = T.session_calendar(b)
    t = cal[-40]
    r1 = T.price_rows(b, cal, keep_dates=pd.DatetimeIndex([t]))
    b2 = b.copy()
    fut = b2["date"] > t
    b2.loc[fut, ["open", "high", "low", "close", "vwap"]] *= 3.0     # rewrite the future
    r2 = T.price_rows(b2, cal, keep_dates=pd.DatetimeIndex([t]))
    for c in T.PRICE_FEATURES:
        np.testing.assert_allclose(r1[c].values, r2[c].values, rtol=1e-5, equal_nan=True)


# ── 2. entry is the NEXT session's open ──────────────────────────────────────

def test_forward_return_enters_at_next_session_open():
    b = _bars(n_sessions=300, n_sym=3)
    cal = T.session_calendar(b)
    t = cal[200]
    r = T.price_rows(b, cal, keep_dates=pd.DatetimeIndex([t]))
    s = b[b["symbol"] == "S00"].set_index("date")["open"]
    row = r[r["symbol"] == "S00"].iloc[0]
    for h in C.HORIZONS:
        exp = s.iloc[201 + h] / s.iloc[201] - 1.0
        assert row[f"fwd_{h}"] == pytest.approx(exp, rel=1e-9)
    # the close of t itself plays no part: changing it leaves the label intact
    b.loc[(b["symbol"] == "S00") & (b["date"] == t), "open"] *= 5
    r2 = T.price_rows(b, cal, keep_dates=pd.DatetimeIndex([t]))
    assert r2[r2["symbol"] == "S00"]["fwd_21"].iloc[0] == pytest.approx(row["fwd_21"])


def test_label_beyond_known_calendar_is_nan_for_a_living_name():
    b = _bars(n_sessions=300, n_sym=3)
    cal = T.session_calendar(b)
    t = cal[-10]
    r = T.price_rows(b, cal, keep_dates=pd.DatetimeIndex([t]))
    assert r["fwd_5"].notna().all() and r["fwd_21"].isna().all()


# ── 3. the walk-forward splitter ─────────────────────────────────────────────

def test_walk_forward_blocks_never_overlap_and_respect_the_embargo():
    cal = pd.bdate_range(end=pd.Timestamp(date.today()), periods=252 * 6)
    grid = cal[::5]
    years = tuple(sorted(set(grid.year)))[2:]
    folds = walk_forward_folds(grid, cal, test_years=years)
    assert len(folds) >= 2
    for f in folds:
        check_fold(f, cal)
        assert f.train.max() < f.val.min() < f.val.max() < f.test.min()
        g1 = cal.get_loc(f.val.min()) - cal.get_loc(f.train.max())
        g2 = cal.get_loc(f.test.min()) - cal.get_loc(f.val.max())
        assert g1 > C.EMBARGO_SESSIONS and g2 > C.EMBARGO_SESSIONS


def test_check_fold_raises_when_embargo_is_violated():
    cal = pd.bdate_range(end=pd.Timestamp(date.today()), periods=400)
    bad = Fold("bad", cal[:100], cal[110:130], cal[300:320])
    with pytest.raises(AssertionError):
        check_fold(bad, cal)


# ── 4. seeds: tonight's seed is not any earlier night's ──────────────────────

def test_seed_draw_excludes_every_recorded_seed(tmp_path):
    led = tmp_path / "seeds.jsonl"
    S.record([11, 22, 33], source="night_1", path=led)
    S.record([44], source="night_2", path=led)
    seq = iter([11, 22, 44, 33, 11, 55, 55, 66])
    got = S.draw(2, path=led, _source=lambda n: next(seq))
    assert got == [55, 66]
    assert not set(got) & S.used(led) - set(got)


# ── 5. promotion on a validation block is GONE (review F5): see test_after_review.py ──

# ── 6. an un-elapsed horizon is never graded ─────────────────────────────────

def test_unelapsed_horizon_is_never_graded():
    from nn_lab import loop as L
    b = _bars(n_sessions=60, n_sym=5)
    cal = T.session_calendar(b)
    dd = cal[-10]
    written = (dd + pd.Timedelta(hours=22)).isoformat()      # after the close of dd
    syms = [f"S{i:02d}" for i in range(5)]
    assert L.realised(dd, written, 5, syms, b, cal) is not None
    assert L.realised(dd, written, 21, syms, b, cal) is None     # 21 and 63 have not elapsed
    assert L.realised(dd, written, 63, syms, b, cal) is None
    ent = L.entry_session(dd, written, cal)
    assert ent == cal[-9]                            # the next session, not dd
    # a prediction written AFTER the next open enters one session later
    late = (cal[-9] + pd.Timedelta(hours=14)).isoformat()
    assert L.entry_session(dd, late, cal) == cal[-8]


# ── 7. a night with no new rows reports DEGRADED ─────────────────────────────

def test_no_new_rows_is_degraded():
    assert N.night_status(0) == "DEGRADED"
    assert N.night_status(12) == "OK"
    assert N.night_status(5, refused="STOP_FILE") == "REFUSED"
    assert N.night_status(5, stale=True) == "STALE_BARS"


def test_stop_file_refuses_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "STOP_FILE", tmp_path / "STOP")
    (tmp_path / "STOP").write_text("stop")
    assert "STOP_FILE" in (N.refuse_reason() or "")


def test_nn_lab_is_not_imported_by_the_live_path():
    import pathlib
    repo = pathlib.Path(C.REPO)
    for sub in ("backend", "scripts", "engine"):
        for p in (repo / sub).rglob("*.py"):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            assert "import nn_lab" not in txt and "from nn_lab" not in txt, p


# ── 8. a reused ticker is never spliced onto another company's history ───────

def test_reused_ticker_is_not_spliced(tmp_path):
    b = _bars(n_sessions=300, n_sym=2)
    cal = T.session_calendar(b)
    live = b[(b["symbol"] == "S00") & (b["date"] >= cal[200])]          # a 2nd company, recent IPO
    dead = b[(b["symbol"] == "S01") & (b["date"] < cal[150])].assign(symbol="S00")  # old company, same ticker
    rest = b[b["symbol"] == C.MARKET]
    p1, p2 = tmp_path / "live.parquet", tmp_path / "dead.parquet"
    pd.concat([live, rest]).to_parquet(p1)
    dead.to_parquet(p2)
    out = T.load_bars([p1, p2])
    s = out[out["symbol"] == "S00"]
    assert s["date"].min() == cal[200] and len(s) == 100
    # an extend_only file adds only newer dates for the same symbol
    newer = b[(b["symbol"] == "S00") & (b["date"] >= cal[250])]
    p3 = tmp_path / "recent.parquet"
    newer.assign(close=newer["close"] * 7).to_parquet(p3)
    out2 = T.load_bars([p1, p3], extend_only=[p3])
    assert len(out2[out2["symbol"] == "S00"]) == 100


def test_a_symbol_with_a_long_gap_becomes_two_companies():
    b = _bars(n_sessions=300, n_sym=1)
    cal = T.session_calendar(b)
    s = b[(b["symbol"] == "S00") & ((b["date"] < cal[100]) | (b["date"] >= cal[200]))]
    out = T.split_reused_symbols(pd.concat([b[b["symbol"] == C.MARKET], s]).sort_values(["symbol", "date"]))
    assert set(out["symbol"]) == {C.MARKET, "S00", "S00#1"}
    assert out.loc[out["symbol"] == "S00", "date"].min() == cal[200]
    assert out.loc[out["symbol"] == "S00#1", "date"].max() == cal[99]
