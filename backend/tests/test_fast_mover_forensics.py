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


def test_case_held_by_two_rules_is_selectable_by_rule_with_both_ids():
    closes, sector, S = _panel({"POS": 0.08})
    pos = _position(S, closes)
    R = str(S.date())
    before = str((S - pd.Timedelta(days=20)).date())
    after = str((S + pd.Timedelta(days=3)).date())       # post-R: must not count
    ctx = F.Context(closes=closes, sector=sector, rule_holdings={
        "rule_a": {before: ["POS", "T1"]},
        "rule_b": {"2020-01-31": ["T2"], before: ["POS"]},
        "rule_c": {before: ["T3"], after: ["POS"]},       # bought POS only after R
        "rule_d": {"2020-01-31": ["POS"], before: ["T4"]},  # sold POS before R
    }, rule_meta={"rule_a": {"sealed_rank": 7}, "rule_b": {"sealed_rank": 2}})
    case = _one_case(ctx, pos)
    assert case.R == R
    sel = F.selectable_by_rules("POS", case.R, ctx)
    assert sel["selectable_by_rules"] == ["rule_b", "rule_a"]     # sealed-rank order
    assert sel["n_rules_selecting"] == 2
    r = F.analyse([case], ctx)[0]
    assert r["class"] == "SELECTABLE_BY_RULE", r["class_rule"]
    assert set(r["selectable_by_rules"]) == {"rule_a", "rule_b"}
    assert r["n_rules_selecting"] == 2
    assert r["class_before_rule_join"] in F.CLASSES
    assert r["class_before_rule_join"] != "SELECTABLE_BY_RULE"
    assert r["credit"] != "credited"                  # it credits no book


def test_adverse_move_on_a_held_name_is_not_selectable():
    closes, sector, S = _panel({"POS": -0.08})
    pos = _position(S, closes)
    before = str((S - pd.Timedelta(days=20)).date())
    ctx = F.Context(closes=closes, sector=sector, rule_holdings={"rule_a": {before: ["POS"]}})
    r = F.analyse([_one_case(ctx, pos)], ctx)[0]
    assert r["class"] != "SELECTABLE_BY_RULE" and r["n_rules_selecting"] == 1


def test_book_sigma_from_a_synthetic_correlation_matrix():
    sig = [0.02, 0.04, 0.03]
    C = np.array([[1.0, 0.5, 0.2], [0.5, 1.0, 0.0], [0.2, 0.0, 1.0]])
    w = [2.0, 1.0, 1.0]                                  # normalised to 0.5/0.25/0.25
    wn = np.array([0.5, 0.25, 0.25])
    cov = np.outer(sig, sig) * C
    expect = float(np.sqrt(wn @ cov @ wn))
    assert abs(F.book_sigma(sig, C, w) - expect) < 1e-12
    # rho = 1 collapses to the weighted mean sigma; rho = 0 to the root sum of squares
    assert abs(F.book_sigma(sig, np.ones((3, 3)), [1, 1, 1]) - np.mean(sig)) < 1e-12
    assert abs(F.book_sigma(sig, np.eye(3), [1, 1, 1])
               - np.sqrt(sum((s / 3) ** 2 for s in sig))) < 1e-12


def test_book_move_is_printed_in_book_sigma_from_realised_correlation():
    closes, sector, S = _panel({"POS": 0.08, "T0": 0.08})
    ps = []
    for tk in ("POS", "T0"):
        p = _position(S, closes)
        p.ticker, p.book = tk, "book:bk"
        ps.append(p)
    ctx = F.Context(closes=closes, sector=sector)
    bm = F.book_moves(ps, ctx, horizons=(1, 5))
    assert len(bm) == 1
    b = bm[0]
    i = ctx.sessions.get_loc(S)
    ret = closes[["POS", "T0"]].iloc[i - 63: i + 1].pct_change().iloc[1:]
    expect = F.book_sigma(ret.std(ddof=1).to_numpy(), ret.corr().to_numpy(), [1, 1])
    assert abs(b["sigma_1_book"] - round(expect, 6)) < 1e-6
    m5 = b["moves"]["5"]
    assert abs(m5["z_book"] - m5["move"] / (expect * np.sqrt(5))) < 1e-3
    assert "book-sigma" in F.book_sigma_line(b)
