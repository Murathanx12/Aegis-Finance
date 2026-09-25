"""llm_portfolio: `kind` constraints at freeze, twins, and the daily leaderboard.

Offline and date-relative: every fixture derives its calendar from `today`.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import llm_portfolio as LP


# ───────────────────────────── fixtures ─────────────────────────────────────

def _pos(t, w, theme=None, falsifier="it did not happen"):
    p = {"ticker": t, "weight": w, "thesis": f"{t} because reasons",
         "falsifier": falsifier}
    if theme:
        p["theme"] = theme
    return p


def _competition_book(n=10, cash=0.0, w=None):
    w = w if w is not None else round((1.0 - cash) / n, 6)
    pos = [_pos(f"N{i:02d}", w, theme="semis" if i % 2 else "biotech")
           for i in range(n)]
    if cash:
        pos.append({"ticker": "CASH", "weight": cash, "thesis": "declared"})
    return {"name": "comp_v0", "kind": "competition",
            "objective": C.BOOK_COMPETITION_OBJECTIVE,
            "strategy": "test", "positions": pos}


def _personal_book():
    return {"name": "pers_v0", "kind": "personal",
            "objective": "maximise 126-session return vs SPY",
            "positions": [_pos("AAA", 0.30, "semis"), _pos("BBB", 0.30, "lithium"),
                          _pos("CCC", 0.30, "semis"),
                          {"ticker": "CASH", "weight": 0.10, "thesis": "declared"}]}


def _bars(symbols, *, n=80, seed=0, dollar_vol=None):
    """A synthetic US panel ending yesterday, one random walk per symbol."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(date.today() - timedelta(days=1))
    days = pd.bdate_range(end=end, periods=n)
    rows = []
    for s in symbols:
        px = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        vol = (dollar_vol or {}).get(s, 5e7) / px
        rows.append(pd.DataFrame({"symbol": s, "date": days, "open": px,
                                  "high": px, "low": px, "close": px,
                                  "volume": vol}))
    return pd.concat(rows, ignore_index=True)


# ───────────────────────────── freeze: kinds ────────────────────────────────

def test_legacy_book_without_kind_still_freezes():
    rec = LP.freeze({"name": "x", "objective": "y",
                     "positions": [{"ticker": "AAA", "weight": 1.0}]})
    assert rec["kind"] == "personal" and rec["kind_declared"] is False


def test_competition_valid_book_passes():
    rec = LP.freeze(_competition_book(n=10, cash=0.0))
    assert rec["kind"] == "competition"
    assert rec["constraints"]["max_weight"] == C.BOOK_COMPETITION_MAX_WEIGHT
    assert rec["benchmark"] == C.BOOK_WLS_PROXY


def test_competition_refuses_overweight_name():
    b = _competition_book(n=10)
    b["positions"][0]["weight"] = 0.15
    b["positions"][1]["weight"] = 0.05
    with pytest.raises(LP.Refusal, match="max_weight"):
        LP.freeze(b)


def test_competition_refuses_too_few_names():
    with pytest.raises(LP.Refusal, match="at least"):
        LP.freeze(_competition_book(n=7, w=0.10, cash=0.30))


def test_competition_refuses_cash_above_two_percent():
    b = _competition_book(n=10, cash=0.05, w=0.095)
    with pytest.raises(LP.Refusal, match="cash"):
        LP.freeze(b)


def test_competition_refuses_etf():
    b = _competition_book(n=10)
    b["positions"][0]["ticker"] = "SMH"
    with pytest.raises(LP.Refusal, match="ETF"):
        LP.freeze(b)


def test_competition_refuses_wrong_objective():
    b = _competition_book(n=10)
    b["objective"] = "beat SPY"
    with pytest.raises(LP.Refusal, match="Relative P&L vs WLS"):
        LP.freeze(b)


def test_competition_refuses_position_without_falsifier():
    b = _competition_book(n=10)
    b["positions"][3]["falsifier"] = ""
    with pytest.raises(LP.Refusal, match="falsifier"):
        LP.freeze(b)


def test_personal_requires_declared_cash():
    b = _personal_book()
    b["positions"] = [p for p in b["positions"] if p["ticker"] != "CASH"]
    for p in b["positions"]:
        p["weight"] = 1 / 3
    with pytest.raises(LP.Refusal, match="CASH"):
        LP.freeze(b)


def test_personal_has_no_weight_cap():
    b = _personal_book()
    b["positions"][0]["weight"] = 0.60
    b["positions"][1]["weight"] = 0.15
    b["positions"][2]["weight"] = 0.15
    assert LP.freeze(b)["max_weight"] == pytest.approx(0.60)


def test_falsifier_is_lifted_from_the_thesis():
    b = _personal_book()
    for p in b["positions"]:
        p.pop("falsifier", None)
        p["thesis"] = "AI power demand. Falsifier: backlog stalls at Q3."
    rec = LP.freeze(b)
    assert rec["positions"][0]["falsifier"] == "backlog stalls at Q3."


def test_draft_state_is_refused():
    b = _personal_book()
    b["state"] = "DRAFT_NOT_FROZEN"
    with pytest.raises(LP.Refusal, match="DRAFT"):
        LP.freeze(b)


def test_unknown_kind_is_refused():
    b = _personal_book()
    b["kind"] = "yolo"
    with pytest.raises(LP.Refusal, match="kind"):
        LP.freeze(b)


# ─────────────────────── freeze: priceability ───────────────────────────────

def test_unpriceable_ticker_refused_without_resolution():
    with pytest.raises(LP.Refusal, match="CCC"):
        LP.freeze(_personal_book(), universe={"AAA", "BBB"})


def test_unpriceable_ticker_resolves_through_global_prices():
    calls = []

    def resolve(ts):
        calls.append(list(ts))
        return {"CCC"}

    rec = LP.freeze(_personal_book(), universe={"AAA", "BBB"}, resolve=resolve)
    assert calls == [["CCC"]]
    assert rec["priced_by"]["global_prices"] == ["CCC"]


def test_resolution_that_fails_still_refuses():
    with pytest.raises(LP.Refusal, match="CCC"):
        LP.freeze(_personal_book(), universe={"AAA", "BBB"},
                  resolve=lambda ts: set())


# ──────────────────────────────── twins ─────────────────────────────────────

def _panel_for_twins():
    names = ["AAA", "BBB", "CCC"] + [f"R{i:02d}" for i in range(30)]
    dv = {n: (5e8 if i % 2 else 5e7) for i, n in enumerate(names)}
    return _bars(names, dollar_vol=dv)


def test_twins_shapes_and_parent_hash():
    parent = LP.freeze(_personal_book())
    tw = LP.twins(parent, asof=date.today(), seed=7, bars=_panel_for_twins())
    assert set(tw) == {"ew", "sector_etf", "spy", "random_same_band"}
    for k, t in tw.items():
        assert t["parent_book_id"] == parent["book_id"], k
        assert t["kind"] == "twin" and t["twin"] == k
        assert sum(p["weight"] for p in t["positions"]) == pytest.approx(1.0)
    ew = {p["ticker"]: p["weight"] for p in tw["ew"]["positions"]}
    assert ew == pytest.approx({"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3})
    etf = {p["ticker"]: p["weight"] for p in tw["sector_etf"]["positions"]}
    assert etf == pytest.approx({"SMH": 2 / 3, "LIT": 1 / 3})
    assert [p["ticker"] for p in tw["spy"]["positions"]] == ["SPY"]


def test_random_twin_same_count_same_band_and_seeded():
    bars = _panel_for_twins()
    parent = LP.freeze(_personal_book())
    a = LP.twins(parent, asof=date.today(), seed=7, bars=bars)["random_same_band"]
    b = LP.twins(parent, asof=date.today(), seed=7, bars=bars)["random_same_band"]
    c = LP.twins(parent, asof=date.today(), seed=8, bars=bars)["random_same_band"]
    assert a["positions"] == b["positions"]
    assert a["positions"] != c["positions"]
    names = [p["ticker"] for p in a["positions"] if p["ticker"] != "CASH"]
    assert len(names) == 3 and not set(names) & {"AAA", "BBB", "CCC"}
    bands = LP.liquidity_bands(bars, asof=date.today())
    parent_bands = sorted(bands[t] for t in ("AAA", "BBB", "CCC"))
    assert sorted(bands[t] for t in names) == parent_bands
    cash = [p for p in a["positions"] if p["ticker"] == "CASH"]
    assert cash and cash[0]["weight"] == pytest.approx(0.10)


def test_competition_twins_use_urth():
    parent = LP.freeze(_competition_book(n=10))
    names = [f"N{i:02d}" for i in range(10)] + [f"R{i:02d}" for i in range(30)]
    tw = LP.twins(parent, asof=date.today(), seed=1, bars=_bars(names))
    assert "urth" in tw and "spy" not in tw
    assert tw["urth"]["positions"][0]["ticker"] == "URTH"


def test_ai_only_twin_equals_the_draft():
    parent = LP.freeze(_personal_book())
    draft = {"positions": [_pos("AAA", 0.5), _pos("BBB", 0.5)]}
    tw = LP.twins(parent, asof=date.today(), seed=1, bars=_panel_for_twins(),
                  ai_draft=draft)
    got = [(p["ticker"], p["weight"]) for p in tw["ai_only"]["positions"]]
    assert got == [("AAA", 0.5), ("BBB", 0.5)]


def test_twins_refuse_an_unfrozen_book():
    with pytest.raises(LP.Refusal, match="FROZEN"):
        LP.twins(_personal_book(), asof=date.today(), seed=1,
                 bars=_panel_for_twins())


# ──────────────────────────── grade / leaderboard ───────────────────────────

def _asof_n_sessions_ago(bars, n):
    d = np.sort(bars["date"].unique())
    return str(pd.Timestamp(d[-n - 1]).date())


def test_grade_reports_to_date_and_benchmark():
    bars = _bars(["AAA", "BBB", "CCC", "SPY", "URTH"])
    asof = _asof_n_sessions_ago(bars, 10)
    rec = LP.freeze(_personal_book(), today=asof)
    g = LP.grade(rec, bars)
    assert g["status"] == "OK" and g["benchmark"] == "SPY"
    td = g["to_date"]
    assert td["sessions"] == 10 and td["vs_benchmark"] is not None
    # entry cost now comes from the name's own dollar volume (mid band, 18bps)
    assert g["entry_cost_bps"] == pytest.approx(0.9 * 18 / 2, rel=1e-6)


def test_competition_grade_is_marked_as_proxy():
    names = [f"N{i:02d}" for i in range(10)]
    bars = _bars(names + ["URTH", "SPY"])
    rec = LP.freeze(_competition_book(n=10), today=_asof_n_sessions_ago(bars, 5))
    g = LP.grade(rec, bars)
    assert g["benchmark"] == "URTH" and g["benchmark_is_proxy"] is True
    assert "PROXY" in g["caveat"]


def test_leaderboard_compares_book_to_its_twins():
    names = ["AAA", "BBB", "CCC"] + [f"R{i:02d}" for i in range(30)]
    bars = pd.concat([_bars(names), _bars(["SPY", "SMH", "LIT"], seed=3)],
                     ignore_index=True)
    asof = _asof_n_sessions_ago(bars, 5)
    parent = LP.freeze(_personal_book(), today=asof)
    tw = LP.twins(parent, asof=asof, seed=3, bars=bars)
    lb = LP.leaderboard([parent, *tw.values()], bars)
    row = [r for r in lb["books"] if r["book_id"] == parent["book_id"]][0]
    for k in ("vs_ew", "vs_sector_etf", "vs_random_same_band", "vs_benchmark"):
        assert row[k] is not None, k
    assert lb["by_kind"]["personal"]["n_books"] == 1
    assert lb["n_twins"] == 4


def test_union_bars_takes_the_fresher_source_per_symbol():
    us = _bars(["AAA", "BBB"], n=20)
    us = us[~((us["symbol"] == "BBB") & (us["date"] == us["date"].max()))]
    glob = _bars(["BBB", "2330.TW"], n=20, seed=5)
    u = LP.union_bars(us, glob)
    src = u.groupby("symbol")["date"].max()
    assert src["BBB"] == glob["date"].max()
    assert set(u["symbol"]) == {"AAA", "BBB", "2330.TW"}
    # one source per symbol, never interleaved
    assert u.groupby(["symbol", "date"]).size().max() == 1


# ───────────────────── the v1 draft's keys (2026-09-25 PM) ──────────────────

def _v1_shaped():
    """The keys `docs/research_notes/2026-09-25/book_human_ai_thematic_v1.draft.json`
    carries, on a synthetic book."""
    b = _personal_book()
    b.update({"state": "DRAFT_NOT_FROZEN", "drafted_at": "2026-09-25",
              "supersedes": "book_v0.draft.json", "max_weight": 0.12,
              "dropped_from_v0": {"SRAD": "no separating fact"},
              "human_edits": [], "twins_requested": ["ew", "spy"],
              "model": "fable draft + Murat"})
    return b


def test_v1_draft_refused_unless_accepted_and_the_override_is_recorded():
    b = _v1_shaped()
    with pytest.raises(LP.Refusal):
        LP.freeze(b)
    rec = LP.freeze(b, accept_draft=True)
    assert rec["state"] == "DRAFT_NOT_FROZEN"
    assert rec["draft_accepted_by_override"] is True
    assert rec["human_edits"] == []


def test_v1_provenance_keys_and_falsifiers_are_carried():
    b = _v1_shaped()
    b["state"] = "READY"
    rec = LP.freeze(b)
    for k in ("supersedes", "dropped_from_v0", "human_edits",
              "twins_requested", "drafted_at"):
        assert rec[k] == b[k], k
    assert rec["declared_max_weight"] == 0.12
    assert all(p.get("falsifier") for p in rec["positions"] if p["ticker"] != "CASH")
    # provenance does not change the identity of the book
    b2 = dict(b, supersedes="something else")
    assert LP.freeze(b2)["book_id"] == rec["book_id"]


def test_ticker_theme_map_fills_what_keywords_miss():
    b = {"name": "t", "kind": "personal", "objective": "o", "state": "READY",
         "positions": [
             {"ticker": "TSM", "weight": 0.3, "thesis": "Q3 earnings Oct 15",
              "falsifier": "capex cut"},
             {"ticker": "IONQ", "weight": 0.3, "thesis": "decoder news",
              "falsifier": "no replication"},
             {"ticker": "WST", "weight": 0.3, "thesis": "GLP-1 supply chain",
              "falsifier": "destocking"},
             {"ticker": "CASH", "weight": 0.1, "thesis": "declared"}]}
    th = {p["ticker"]: (p.get("theme"), p.get("theme_source"))
          for p in LP.freeze(b)["positions"]}
    assert th["TSM"] == ("semis", "ticker_map")
    assert th["IONQ"] == ("quantum", "ticker_map")
    assert th["WST"] == ("biotech", "inferred")


def test_freeze_with_twins_honours_twins_requested(monkeypatch, tmp_path):
    from scripts import llm_portfolio as CLI
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    b = _v1_shaped()
    b["state"] = "READY"
    bars = _bars(["AAA", "BBB", "CCC"] + [f"R{i}" for i in range(20)])
    rc, frozen = CLI.freeze_with_twins([b], us_bars=bars, twins=True,
                                       check_prices=False, out=lambda *_: None)
    assert rc == 0
    assert sorted(f["twin"] for f in frozen if f.get("twin")) == ["ew", "spy"]
