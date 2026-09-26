"""Chunk A: fast-mover forensics on a synthetic ledger (offline, no LLM)."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from backend.services import fast_mover_forensics as F


def _panel(jumps: dict[str, float], *, n: int = 90, seed: int = 7):
    """Business-day closes with small noise; `jumps[sym]` applied at S+1."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=10),
                         periods=n)
    syms = ["POS"] + [f"T{i}" for i in range(6)] + [f"F{i}" for i in range(6)] + ["SPY"]
    S = n - 8
    data = {}
    for s in syms:
        r = rng.normal(0, 0.004, n)
        r[S + 1] += jumps.get(s, 0.0)
        data[s] = 50 * np.cumprod(1 + r)
    closes = pd.DataFrame(data, index=idx)
    sector = {s: ("tech" if s.startswith("T") or s == "POS" else "fin")
              for s in syms if s != "SPY"}
    return closes, sector, idx[S]


def _position(S: pd.Timestamp, closes: pd.DataFrame) -> F.Position:
    close_utc = F._close_utc(S)
    return F.Position(book="book:test", family="night_books", ticker="POS",
                      direction=1, entry_ts=(close_utc + timedelta(hours=2)).isoformat(),
                      entry_px=float(closes["POS"].loc[S]),
                      why_selected={"signal": "mom_12_1"},
                      held_by_book=("POS",), entry_session=str(S.date()))


def _one_case(ctx, pos):
    cases = F.find_fast_movers(positions=[pos], ctx=ctx)
    assert len(cases) == 1, cases
    return cases[0]


def test_post_entry_news_is_unforeseeable_and_absent_from_state():
    closes, sector, S = _panel({"POS": 0.08})
    pos = _position(S, closes)
    cutoff = F._utc(pos.entry_ts)
    news = [
        {"source": "yfinance_ticker_news", "_tickers": ["POS"],
         "first_seen_utc": (cutoff - timedelta(days=1)).isoformat(),
         "published_utc": (cutoff - timedelta(days=1)).isoformat(),
         "title": "PosCo shareholders meet"},
        {"source": "yfinance_ticker_news", "_tickers": ["POS"],
         "first_seen_utc": (cutoff + timedelta(hours=14)).isoformat(),
         "published_utc": (cutoff + timedelta(hours=13)).isoformat(),
         "title": "PosCo announces surprise strategic update"},
    ]
    ctx = F.Context(closes=closes, sector=sector, news=news)
    case = _one_case(ctx, pos)
    assert case.move > 0.07 and case.horizon in (1, 5)

    st = F.state_at_entry(case, ctx)
    assert st["news_pre_entry"]["count"] == 1
    for row in st["news_pre_entry"]["top5"]:
        assert F._utc(row["first_seen_utc"]) <= cutoff
    assert "surprise" not in str(st)          # no post-entry row leaked in

    ex = F.ex_post_catalyst(case, ctx)
    assert ex["news_count"] == 1
    cl = F.classify(case, ctx=ctx)
    assert cl["label"] == "UNFORESEEABLE_NEWS", cl
    assert cl["rule"]


def test_sector_wide_move_is_sector_beta():
    jumps = {f"T{i}": 0.08 for i in range(6)}
    jumps["POS"] = 0.082
    closes, sector, S = _panel(jumps)
    pos = _position(S, closes)
    ctx = F.Context(closes=closes, sector=sector)
    case = _one_case(ctx, pos)
    cl = F.classify(case, ctx=ctx)
    assert cl["label"] == "SECTOR_BETA", cl
    assert "R1" in cl["rule"]


def test_hit_below_control_median_is_not_credited():
    jumps = {s: 0.09 for s in [f"T{i}" for i in range(6)] + [f"F{i}" for i in range(6)]}
    jumps["POS"] = 0.06
    closes, sector, S = _panel(jumps)
    pos = _position(S, closes)
    ctx = F.Context(closes=closes, sector=sector)
    case = _one_case(ctx, pos)
    ctl = F.matched_controls(case, ctx)
    assert len(ctl["names"]) == 3 and "POS" not in ctl["names"]
    assert ctl["median"] > case.move_cc
    cl = F.classify(case, controls=ctl, ctx=ctx)
    cr = F.credit(case, cl["label"], True, True, ctl)   # even if "predicted"
    assert cr["credit"] == "none", cr
    assert "did not beat" in cr["why"]


def test_state_at_entry_drops_post_entry_revisions_and_forecasts():
    closes, sector, S = _panel({"POS": 0.08})
    pos = _position(S, closes)
    cutoff = F._utc(pos.entry_ts)
    rev = pd.DataFrame([
        {"ticker": "POS", "event_date": (cutoff - timedelta(days=5)).replace(tzinfo=None),
         "firm": "EarlyCo", "action": "main", "target_action": "Raises",
         "target_change": 0.1},
        {"ticker": "POS", "event_date": (cutoff + timedelta(hours=12)).replace(tzinfo=None),
         "firm": "LateCo", "action": "up", "target_action": "Raises",
         "target_change": 0.2},
    ])
    preds = [{"ticker": "POS", "made_at": (cutoff + timedelta(hours=1)).isoformat(),
              "observable": "return_sign", "probability": 0.9, "thesis": "late"}]
    ctx = F.Context(closes=closes, sector=sector, revisions=rev, predictions=preds)
    case = _one_case(ctx, pos)
    st = F.state_at_entry(case, ctx)
    assert st["revision_flow_90d"]["firms"] == ["EarlyCo"]
    assert st["forecasts"]["n"] == 0
    ex = F.ex_post_catalyst(case, ctx)
    assert "LateCo" in ex["revisions_in_window"]["firms"]
