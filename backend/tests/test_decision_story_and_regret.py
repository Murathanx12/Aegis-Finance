"""C11 (2026-10-06): Decision Story ids, frozen alternatives, the regret ledger,
and the fixes from `docs/reviews/REVIEW_2026-10-06_C11_DECISION_STORY_REGRET.md`.

Every decision -- an abstention included -- freezes its alternatives at decision
time, keyed on the XNYS session it could first trade at, and
`regret_ledger.grade_due` prices them on real bars when a horizon matures.
Dates derive from TODAY (session protocol item 5); no broker, no network, no LLM.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.services import decision_story as DS
from backend.services import pc_broker as PB
from backend.services import policy_state as PS
from backend.services import regret_ledger as RL
from scripts import sim_run as S
from scripts import task_keeper as TK

TODAY = datetime.now(timezone.utc).date()
EQUITY = 1_000_000.0
NO_SHADOW = Path(__file__).parent / "_c11_no_shadow_news.jsonl"   # never exists


def _session_back(n: int) -> str:
    """The XNYS session n sessions before today (derived, never a literal)."""
    from backend.services.counterfactual_prices import sessions_after
    d = TODAY - timedelta(days=int(n * 1.6) + 10)
    while True:
        s = sessions_after(d - timedelta(days=1), 1)[0]
        if s >= d:
            return s.isoformat()
        d += timedelta(days=1)


ASOF_OLD = _session_back(100)               # 63 sessions have matured since
IN_SESSION = f"{ASOF_OLD}T15:00:00+00:00"   # 10:00-11:00 ET: entry at this close


def _inp(asof: str = ASOF_OLD, *, basis: dict | None = None, **over) -> dict:
    """AAA, BBB on the shortlist (one PROBE slot -> AAA taken, BBB next-ranked);
    CCC held from an earlier PROBE and exited."""
    inp = {
        "asof": asof, "mode": "paper_profit", "session_id": "test",
        "policy_id": "sim_run.u_plan.probe", "policy_version": "vtest",
        "equity": EQUITY, "pool": [], "book_size": 18,
        "shortlist": [{"ticker": "AAA", "score": 1.0, "source": "funnel:test@x",
                       "reasons": [], "median_dollar_vol": 5e9, "vol_annual": 0.3},
                      {"ticker": "BBB", "score": 0.9, "source": "funnel:test@x",
                       "reasons": [], "median_dollar_vol": 5e9, "vol_annual": 0.3}],
        "rep_weights": None, "probe_weighting": "equal",
        "sig_by": {"AAA": 0.02, "BBB": 0.02},
        "probe_max_names": 1, "probe_max_weight": 0.02, "probe_gross_cap": 0.02,
        "exploit_max_weight": 0.10,
        "gates": {"mode": "paper_profit", "ranker_may_trade": False, "blend_may_trade": False},
        "actual_weights": {"AAA": 0.02},
        "probe_syms": ["AAA"], "ex_syms": [],
        "probe_acting": True, "exploit_acting": False,
        "positions": [{"symbol": "CCC", "qty": 100, "market_value": 20_000.0}],
        "prices": {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0},
        "plans": {"AAA": {"side": "buy", "qty": 200, "reason": "PROBE", "refused": None},
                  "CCC": {"side": "sell", "qty": 100, "reason": "PROBE_EXIT", "refused": None}},
        "sent": [], "prior_probe": ["CCC"],
        "funnel_evidence_basis": basis if basis is not None else {"ranked_by": ["profitability_small"]},
        "funnel_generated_at": f"{asof}T12:00:00+00:00",
        "ranking_model_version": None, "ranking_asof": None,
        "contract_path": None, "contract_status": "absent",
        "shadow_news_path": NO_SHADOW,
    }
    inp.update(over)
    return inp


def _bars(asof: str, *, drift: dict[str, float], after: int = 80, before: int = 70,
          noise: float = 0.0, seed: int = 0) -> pd.DataFrame:
    days = pd.bdate_range(pd.Timestamp(asof) - pd.offsets.BDay(before),
                          pd.Timestamp(asof) + pd.offsets.BDay(after))
    rng = np.random.default_rng(seed)
    rows = []
    for sym, mu in drift.items():
        eps = 1.0 + mu + (rng.normal(0.0, noise, len(days)) if noise else np.zeros(len(days)))
        px = 100.0 * np.cumprod(eps)
        for d, c in zip(days, px):
            rows.append({"symbol": sym, "date": d, "open": c, "high": c, "low": c,
                         "close": c, "volume": 5e7})       # $5bn/day: the mega band
    return pd.DataFrame(rows)


DRIFT = {"AAA": 0.001, "BBB": 0.003, "CCC": 0.003, "SPY": 0.0005}


def _freeze(tmp: Path, **kw) -> dict:
    kw.setdefault("now", IN_SESSION)
    kw.setdefault("shadow_news", None)
    inp = kw.pop("inp", None) or _inp()
    return DS.freeze_plan(inp, er_view=None, story_dir=tmp, **kw)


# ───────────────────────────────── stories ───────────────────────────────────

def test_story_chains_ids_and_reuses_what_exists(tmp_path):
    preds = [{"prediction_id": "pred-inv-1", "ticker": "AAA", "specialist": "investigator:x",
              "made_at": f"{ASOF_OLD}T10:00:00+00:00", "inputs_used": {"price_at_write": 99.5}},
             {"prediction_id": "pred-news-1", "ticker": "AAA", "specialist": "news_digest:policy",
              "made_at": f"{ASOF_OLD}T09:00:00+00:00",
              "inputs_used": {"published_at": f"{ASOF_OLD}T08:30:00+00:00"}},
             {"prediction_id": "pred-future", "ticker": "AAA", "specialist": "investigator:x",
              "made_at": "2999-01-01T00:00:00+00:00"}]
    res = _freeze(tmp_path, predictions=preds)
    assert res["replay_matches_actual"] is True
    by = {s["ticker"]: s for s in res["stories"]}
    a, b, c = by["AAA"], by["BBB"], by["CCC"]
    assert (a["action"], b["action"], c["action"]) == ("BUY", "REFUSE", "EXIT")
    assert (a["cohort"], b["cohort"], c["cohort"]) == ("acted", "shortlist_not_taken", "acted")
    assert a["session"] == ASOF_OLD and a["entry_basis"] == "close"
    ch = a["chain"]
    assert ch["decision_id"] == a["decision_id"] and a["decision_id"].startswith("dec_")
    assert ch["forecast_ids"] == ["pred-inv-1"], "reuse the forecast row's id; nothing future"
    assert ch["event_ids"] == ["pred-news-1"] and ch["event_ids_read_by_plan"] is False
    assert ch["order_or_abstention_id"].startswith("pending_order:")
    assert b["chain"]["order_or_abstention_id"] == DS.abstention_id(b["decision_id"])
    assert ch["outcome_ids"]["h21"] == DS.outcome_id(a["decision_id"], 21)
    assert a["latency"]["published_at"].startswith(ASOF_OLD)
    assert a["latency"]["prices"]["forecast_at"] == 99.5
    assert set(a["latency"]) >= {"published_at", "aegis_detected_at", "forecast_at",
                                 "decision_at", "order_at", "fill_at"}
    for s in res["stories"]:
        assert s["sha256"] == DS.seal(s)
        assert s["n_alternatives"] == sum(1 for x in res["alternatives"]
                                          if x["decision_id"] == s["decision_id"])


def test_stories_never_mutate_and_order_links_append(tmp_path):
    _freeze(tmp_path)
    sp, ap = DS.stories_path(tmp_path, ASOF_OLD), DS.alternatives_path(tmp_path, ASOF_OLD)
    s0, a0 = sp.read_bytes(), ap.read_bytes()
    inp2 = _inp(sent=[{"status": "submitted", "symbol": "AAA", "order_id": "brk-123",
                       "submitted_at": f"{ASOF_OLD}T15:05:00+00:00"}])
    res = _freeze(tmp_path, inp=inp2, now=f"{ASOF_OLD}T15:05:00+00:00")
    assert res["n_new_stories"] == 0 and res["n_order_links"] == 1
    assert sp.read_bytes().startswith(s0), "earlier story rows are byte-identical"
    assert ap.read_bytes() == a0, "no alternative is rewritten"
    link = DS.read_jsonl(sp)[-1]
    assert link["kind"] == "order_link" and link["order_id"] == "brk-123"
    res3 = _freeze(tmp_path, inp=_inp(probe_acting=False), now=f"{ASOF_OLD}T15:10:00+00:00")
    assert res3["n_new_stories"] >= 1 and sp.read_bytes().startswith(s0)


def test_alternatives_are_frozen_point_in_time(tmp_path):
    """Mutate every bar AFTER asof: the frozen rows are byte-identical."""
    bars = _bars(ASOF_OLD, drift=DRIFT)
    bars2 = bars.copy()
    later = bars2["date"] > pd.Timestamp(ASOF_OLD)
    bars2.loc[later, "close"] = bars2.loc[later, "close"] * 7.0
    no_mv = _inp(positions=[{"symbol": "CCC", "qty": 100}], prices={"AAA": 100.0, "BBB": 100.0})
    r1 = _freeze(tmp_path / "a", inp=no_mv, bars=bars, write=False)
    r2 = _freeze(tmp_path / "b", inp=no_mv, bars=bars2, write=False)
    dump = lambda r: [json.dumps(x, sort_keys=True) for x in r["alternatives"]]  # noqa: E731
    assert dump(r1) == dump(r2)
    assert [s["sha256"] for s in r1["stories"]] == [s["sha256"] for s in r2["stories"]]
    c = next(s for s in r1["stories"] if s["ticker"] == "CCC")
    assert c["held_weight"] > 0, "held weight from the bar ON asof, not after it"


def test_every_decision_carries_its_alternatives_and_no_earlier_entry(tmp_path):
    res = _freeze(tmp_path)
    alts: dict = {}
    for x in res["alternatives"]:
        alts.setdefault(x["decision_id"], {})[x["alt"]] = x
    for s in res["stories"]:
        names = set(alts[s["decision_id"]])
        assert {"actual", "plan_full", "buy_default", "buy_half", "buy_double_capped",
                "enter_next_open", "plan_plus_shadow_news",
                *(f"loo_{x}" for x in DS.LOO_SOURCES)} <= names
        assert "enter_prev_session" not in names, "an entry before the decision is infeasible"
        if s["held_weight"] > 0:
            assert {"exit_now", "hold"} <= names
        for a in alts[s["decision_id"]].values():
            assert a["places_orders"] is False and a["horizons"] == [5, 21, 63]
            if a["target_weight"] is not None:
                assert a["target_weight"] <= PB.MAX_NAME_FRAC + 1e-12
    a = next(s for s in res["stories"] if s["ticker"] == "AAA")
    assert alts[a["decision_id"]]["selection_next_ranked"]["ticker"] == "BBB"
    assert alts[a["decision_id"]]["loo_news"]["status"] == "IDENTICAL_NOT_READ"
    assert alts[a["decision_id"]]["plan_plus_shadow_news"]["status"] == "NOT_AVAILABLE"


# ─────────────────────────── F3: one session, one story ───────────────────────

def test_weekend_and_after_close_decisions_are_one_session(tmp_path):
    """Friday after the close, Saturday, Sunday: ONE story about Monday's open."""
    from backend.services.counterfactual_prices import sessions_after
    fri = date.fromisoformat(_session_back(100))
    while fri.weekday() != 4 or sessions_after(fri, 1)[0].weekday() != 0:
        fri -= timedelta(days=1)
    mon = sessions_after(fri, 1)[0].isoformat()
    stamps = [f"{fri.isoformat()}T21:30:00+00:00",                    # after 16:00 ET
              f"{(fri + timedelta(days=1)).isoformat()}T15:00:00+00:00",
              f"{(fri + timedelta(days=2)).isoformat()}T15:00:00+00:00"]
    res = [_freeze(tmp_path, inp=_inp(fri.isoformat()), now=t) for t in stamps]
    assert res[0]["n_new_stories"] == 3 and res[0]["session"] == mon
    assert res[0]["entry_basis"] == "open"
    assert res[1]["n_new_stories"] == 0 and res[2]["n_new_stories"] == 0
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path,
                       bars=_bars(fri.isoformat(), drift=DRIFT), write=False)
    h5 = [r for r in rec["rows"] if r["horizon"] == 5]
    assert {r["session"] for r in h5} == {mon}
    assert all(r["entry"] == mon and r["entry_basis"] == "open" for r in h5)
    assert rec["summary"]["by_horizon"]["h5"]["n_sessions"] == 1


def test_reference_session_rule():
    s = _session_back(30)
    assert DS.reference_session(f"{s}T12:00:00+00:00")["entry_basis"] == "open"     # pre-open
    mid = DS.reference_session(f"{s}T17:00:00+00:00")                               # 12-13 ET
    assert mid["session"] == s and mid["entry_basis"] == "close"
    late = DS.reference_session(f"{s}T22:00:00+00:00")
    assert late["session"] > s and late["entry_basis"] == "open"


# ───────────────────────────── NOT_SEPARABLE ─────────────────────────────────

def test_not_separable_is_recorded_not_fabricated(tmp_path):
    res = _freeze(tmp_path, inp=_inp(basis={"ranked_by": ["momentum_12_1"],
                                            "filtered_by": ["low_volatility"]}), write=False)
    pm = [x for x in res["alternatives"] if x["alt"] == "loo_price_momentum"
          and x["ticker"] in ("AAA", "BBB")]
    assert pm and all(x["status"] == "NOT_SEPARABLE" and x["target_weight"] is None
                      and "funnel" in x["why"] for x in pm)
    res2 = _freeze(tmp_path, inp=_inp(basis={}), write=False)
    assert set(res2["not_separable_sources"]) == set(DS.LOO_SOURCES)
    res3 = _freeze(tmp_path, inp=_inp(actual_weights={"AAA": 0.02, "ZZZ": 0.05}), write=False)
    assert res3["replay_matches_actual"] is False and "MISMATCH" in res3["line"]
    assert all(x["status"] == "NOT_SEPARABLE" for x in res3["alternatives"]
               if x["alt"].startswith("loo_"))


def test_er_minus_a_source_renormalises_and_drops_regime():
    names = {"AAA": {"h21": {"er": 0.5 * (0.02 + 0.04) * 0.8, "x": {"ranker": 0.02, "revision_flow": 0.04},
                             "weights": {"ranker": 0.5, "revision_flow": 0.5},
                             "weights_reputation": {"ranker": 0.5, "revision_flow": 0.5},
                             "weights_source": "equal"},
                     "size_scale_mag": 0.9, "size_scale": 0.72}}
    nm, meta = DS.er_names_minus(names, "analyst", regime_scale=0.8)
    assert nm["AAA"]["h21"]["er"] == pytest.approx(0.8 * 0.02) and meta["approximation"] is None
    nm, _ = DS.er_names_minus(names, "regime", regime_scale=0.8)
    assert nm["AAA"]["h21"]["er"] == pytest.approx(0.03) and nm["AAA"]["size_scale"] == pytest.approx(0.9)


# ───────────────────────────────── grading ───────────────────────────────────

def test_grading_signs_on_a_trending_synthetic_session(tmp_path):
    _freeze(tmp_path)
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path,
                       bars=_bars(ASOF_OLD, drift=DRIFT), out_dir=tmp_path / "regret")
    assert rec["status"] == "OK" and Path(rec["path"]).is_file()
    row = {(r["ticker"], r["horizon"]): r for r in rec["rows"]}
    a, b, c = row[("AAA", 21)], row[("BBB", 21)], row[("CCC", 21)]
    assert a["direction_regret_bps"] < 0, "AAA rose: buying was right"
    # signed sizing: the default (2%) equals the actual size here -> exactly 0
    assert a["sizing_regret_bps"] == pytest.approx(0.0)
    assert b["action"] == "REFUSE" and b["abstention_regret_bps"] > 0
    assert c["action"] == "EXIT" and c["exit_regret_bps"] > 0
    sel = [r for r in rec["selection_rows"] if r["horizon"] == 21]
    assert len(sel) == 1 and sel[0]["alt"] == "BBB" and sel[0]["selection_regret_bps"] > 0


def test_every_regret_type_is_mean_zero_under_the_null():
    """Review F1: under a zero-drift (martingale) random walk every regret is
    mean zero before costs -- no best-of-N picked after the outcome."""
    rng = np.random.default_rng(20261006)
    sess = ASOF_OLD
    days = pd.bdate_range(pd.Timestamp(sess) - pd.offsets.BDay(70),
                          pd.Timestamp(sess) + pd.offsets.BDay(10))
    dstr = [d.strftime("%Y-%m-%d") for d in days]
    sigma, n_draws, h = 0.0216, 1000, 5
    acc: dict[str, list[float]] = {}

    def walk() -> dict:
        c = 100.0 * np.cumprod(1.0 + rng.normal(0.0, sigma, len(days)))
        o = np.r_[100.0, c[:-1]] * (1.0 + rng.normal(0.0, sigma / 2, len(days)))
        return {"dates": dstr, "open": list(o), "close": list(c), "volume": [5e7] * len(days)}

    def alts(**w) -> dict:
        return {k: {"target_weight": v, "ticker": "X"} for k, v in w.items()}
    for _ in range(n_draws):
        s, alt, spy = walk(), walk(), walk()
        win = RL.hold_window(s, sess, "close", h, asof_cut="2999-01-01")
        if win["status"] != "OK":
            continue
        wb = RL.hold_window(spy, sess, "close", h, asof_cut="2999-01-01")
        cases = [
            ({"action": "BUY", "held_weight": 0.0, "effective_weight": 0.03, "cohort": "acted"},
             alts(no_trade=0.0, buy_default=0.02)),
            ({"action": "REFUSE", "held_weight": 0.0, "effective_weight": 0.0,
              "cohort": "shortlist_not_taken"}, alts(buy_default=0.02)),
            ({"action": "REFUSE", "held_weight": 0.0, "effective_weight": 0.0,
              "cohort": "picked_blocked"}, alts(plan_full=0.02)),
            ({"action": "EXIT", "held_weight": 0.02, "effective_weight": 0.0, "cohort": "acted"},
             alts(hold=0.02)),
            ({"action": "HOLD", "held_weight": 0.02, "effective_weight": 0.02,
              "cohort": "held_resize"}, alts(exit_now=0.0)),
        ]
        for ci, (d, a_by) in enumerate(cases):
            # per CASE: two cases sharing one draw must not cancel each other
            reg = RL.row_regrets(d, a_by, win, rt_bps=35.0, bench_ret=wb["ret"])
            for k in RL.REGRET_TYPES:
                if reg.get(f"{k}_gross") is not None:
                    acc.setdefault(f"{k}#{ci}", []).append(reg[f"{k}_gross"])
        # selection, once per session, at equal cost bands -> net is the null
        cells = {(sess, "PROBE", h): {"alt": "ALT", "alt_mdv": 5e9, "basis": "close",
                                      "eq": EQUITY,
                                      "taken": [{"w": 0.02, "r": win["ret"], "rt": 6.0}]}}
        rows = RL._selection_rows(cells, lambda _s: alt, "2999-01-01")
        if rows:
            acc.setdefault("selection_regret", []).append(rows[0]["selection_regret_bps"] / 1e4)
    assert {k.split("#")[0] for k in acc} == {*RL.REGRET_TYPES, "selection_regret"}
    for k, v in acc.items():
        v = np.asarray(v)
        t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
        assert len(v) >= 900, k
        assert abs(t) < 2.0, f"{k}: mean {v.mean()*1e4:+.3f} bps, t {t:+.2f} under the null"


def test_abstention_cohorts_are_scaled_to_the_cap_and_net_of_spy(tmp_path):
    """Review F2: 30 refused names at 2% = 60% gross. The cohort book is scaled to
    PROBE_GROSS_CAP, and when every name IS the market the excess over SPY is
    minus the cost -- never a raw dollar sum of market beta."""
    tick = [f"N{i:02d}" for i in range(30)]
    inp = _inp(shortlist=[{"ticker": t, "score": 1.0 - i / 100, "source": "funnel:test@x",
                           "reasons": [], "median_dollar_vol": 5e9, "vol_annual": 0.3}
                          for i, t in enumerate(tick)],
               probe_max_names=10, probe_gross_cap=0.20, actual_weights={t: 0.02 for t in tick[:10]},
               probe_syms=tick[:10], probe_acting=False, positions=[], plans={},
               prior_probe=[], sig_by={t: 0.02 for t in tick})
    _freeze(tmp_path, inp=inp)
    bars = _bars(ASOF_OLD, drift={**{t: 0.002 for t in tick}, "SPY": 0.002})
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path, bars=bars, write=False)
    cr = {(c["cohort"], c["horizon"]): c for c in rec["cohort_rows"]}
    pb, sl = cr[("picked_blocked", 5)], cr[("shortlist_not_taken", 5)]
    assert pb["n_names"] == 10 and pb["book_gross_raw"] == pytest.approx(0.20)
    assert sl["n_names"] == 20 and sl["book_gross_raw"] == pytest.approx(0.40)
    assert sl["scale_to_cap"] == pytest.approx(0.5) and sl["book_gross_scaled"] == pytest.approx(0.20)
    cost = -0.20 * 6.0                                  # bps of equity, the mega band
    assert sl["net_excess_vs_spy_bps"] == pytest.approx(cost, abs=1e-6)
    assert pb["excess_vs_band_control_bps"] == pytest.approx(0.0, abs=1e-6)
    assert "would have made $" not in rec["line"]
    assert "picked-but-blocked book (scaled to the gross cap)" in rec["line"]
    tbl = RL.h_table(rec, 5)
    assert {r["cohort"] for r in tbl} == {"picked_blocked", "shortlist_not_taken"}
    assert all(set(r) >= {"mean_net_excess_vs_spy_bps", "vs_band_control_bps",
                          "n_date_blocks", "mde_bps"} for r in tbl)


def test_selection_counts_once_per_session_at_its_own_cost(tmp_path):
    """Review F8: two PROBE names share one next-ranked name -> one row; the
    alternative pays its own band (mega 6 bps), not the taken name's."""
    sl = [{"ticker": "AAA", "score": 1.0, "source": "f", "reasons": [], "median_dollar_vol": 1e6},
          {"ticker": "DDD", "score": 0.95, "source": "f", "reasons": [], "median_dollar_vol": 1e6},
          {"ticker": "BBB", "score": 0.9, "source": "f", "reasons": [], "median_dollar_vol": 5e9}]
    inp = _inp(shortlist=sl, probe_max_names=2, probe_gross_cap=0.04,
               actual_weights={"AAA": 0.02, "DDD": 0.02}, probe_syms=["AAA", "DDD"],
               sig_by={"AAA": 0.02, "DDD": 0.02, "BBB": 0.02}, positions=[], prior_probe=[],
               plans={"AAA": {"side": "buy", "qty": 200}, "DDD": {"side": "buy", "qty": 200}})
    _freeze(tmp_path, inp=inp)
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path,
                       bars=_bars(ASOF_OLD, drift={**DRIFT, "DDD": 0.001}), write=False)
    rows = [r for r in rec["selection_rows"] if r["horizon"] == 5]
    assert len(rows) == 1 and rows[0]["n_taken"] == 2
    assert rows[0]["alt"] == "BBB" and rows[0]["alt_cost_bps"] == 6.0


def test_a_held_name_without_a_frozen_volume_is_costed_from_the_panel(tmp_path):
    _freeze(tmp_path)
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path,
                       bars=_bars(ASOF_OLD, drift=DRIFT), write=False)
    c = next(r for r in rec["rows"] if r["ticker"] == "CCC")
    assert c["cost_source"] == "panel" and c["cost_round_trip_bps"] == 6.0


# ───────────────────────── F6: one adjustment basis ──────────────────────────

def _one(tmp: Path, bars: pd.DataFrame) -> dict:
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp, bars=bars, write=False)
    return rec


def test_a_raw_split_inside_the_window_is_refused_not_graded(tmp_path):
    _freeze(tmp_path)
    bars = _bars(ASOF_OLD, drift=DRIFT)
    split_day = pd.Timestamp(ASOF_OLD) + pd.offsets.BDay(3)
    m = (bars["symbol"] == "BBB") & (bars["date"] >= split_day)
    bars.loc[m, ["open", "close"]] = bars.loc[m, ["open", "close"]] * 0.5     # raw 2:1
    rec = _one(tmp_path, bars)
    bad = [r for r in rec["refused_rows"] if r["ticker"] == "BBB"]
    assert bad and all(r["status"] == "REFUSED" and "split" in r["why"] for r in bad)
    assert not [r for r in rec["rows"] if r["ticker"] == "BBB"]


def test_a_two_basis_splice_is_refused(tmp_path):
    _freeze(tmp_path)
    bars = _bars(ASOF_OLD, drift=DRIFT)
    m = (bars["symbol"] == "BBB") & (bars["date"] <= pd.Timestamp(ASOF_OLD) + pd.offsets.BDay(2))
    bars.loc[m, ["open", "close"]] = bars.loc[m, ["open", "close"]] * 2.0     # old basis
    assert any(r["ticker"] == "BBB" for r in _one(tmp_path, bars)["refused_rows"])


def test_rewritten_past_bars_grade_on_one_basis(tmp_path):
    """A LATER back-adjustment rewrites PAST bars (the nn_lab leak shape). The
    window is on one basis, so the return is unchanged; the gap to the frozen
    decision-time quote is printed, not hidden."""
    _freeze(tmp_path)
    clean = _bars(ASOF_OLD, drift=DRIFT)
    rows0 = _one(tmp_path, clean)["rows"]
    r0 = {(r["ticker"], r["horizon"]): r["realised_return"] for r in rows0}
    f0 = {(r["ticker"], r["horizon"]): r["basis_factor"] for r in rows0}
    adj = clean.copy()
    later = pd.Timestamp(ASOF_OLD) + pd.offsets.BDay(75)
    m = (adj["symbol"] == "BBB") & (adj["date"] < later)
    adj.loc[m, ["open", "close"]] = adj.loc[m, ["open", "close"]] * 0.5      # split AFTER h63
    rec = _one(tmp_path, adj)
    for r in rec["rows"]:
        if r["ticker"] == "BBB":
            assert r["realised_return"] == pytest.approx(r0[("BBB", r["horizon"])])
            assert r["basis_factor"] == pytest.approx(0.5 * f0[("BBB", r["horizon"])])
            assert r["basis_note"] and r["status"] == "OK"


# ─────────────────────────── F7: news, measured ──────────────────────────────

def test_shadow_news_tilt_is_frozen_and_gives_a_real_mdc(tmp_path):
    sn = {"t": f"{ASOF_OLD}T12:00:00+00:00", "contract_hash": "testhash",
          "signal": {"AAA": {"d": -0.5, "s": 1.0, "n": 1}, "BBB": {"d": 0.6, "s": 1.0, "n": 1}},
          "trust_dir": 1.0, "trust_size": 0.0}
    res = _freeze(tmp_path, shadow_news=sn)
    tilt = {x["ticker"]: x for x in res["alternatives"] if x["alt"] == "plan_plus_shadow_news"}
    assert tilt["BBB"]["target_weight"] > 0, "a d>0 candidate enters the tilted book"
    assert tilt["AAA"]["target_weight"] < 0.02
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path,
                       bars=_bars(ASOF_OLD, drift=DRIFT), write=False)
    m = rec["summary"]["mdc"]["mdc_news_tilt"]["h21"]
    assert m["mean_bps"] is not None and m["mean_bps"] > 0, "BBB outran AAA: the tilt helped"
    assert m["label"].startswith("TRUST_AT_63")
    assert rec["summary"]["mdc"]["mdc_news"]["h21"]["note"].startswith("zero by construction")


def test_shadow_news_view_is_point_in_time(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in (
        {"t": "2026-01-01T10:00:00+00:00", "signal": {"A": {"d": 1, "s": 1, "n": 1}}, "trust_dir": 0.1},
        {"t": "2026-01-02T10:00:00+00:00", "signal": {"B": {"d": 1, "s": 1, "n": 1}}, "trust_dir": 0.2},
    )), encoding="utf-8")
    v = DS.shadow_news_view("2026-01-01T12:00:00+00:00", p)
    assert set(v["signal"]) == {"A"} and v["trust_dir"] == 0.1
    assert DS.shadow_news_view("2025-12-31T00:00:00+00:00", p) is None


def test_nothing_is_graded_before_its_horizon(tmp_path):
    s = _session_back(3)
    _freeze(tmp_path, inp=_inp(s), now=f"{s}T15:00:00+00:00")
    rec = RL.grade_due(TODAY.isoformat(), story_dir=tmp_path,
                       bars=_bars(s, drift=DRIFT, after=0), write=False)
    assert rec["rows"] == [] and rec["pending_not_matured"] > 0
    assert rec["status"] == "NOTHING_MATURED"


def test_costs_are_never_zero(tmp_path):
    with pytest.raises(RL.CostRefused):
        RL.pnl(0.02, 0.05, w_held=0.0, rt_bps=0.0)
    res = _freeze(tmp_path, write=False)
    assert all(s["cost_round_trip_bps"] > 0 for s in res["stories"])
    c = next(s for s in res["stories"] if s["ticker"] == "CCC")
    assert c["median_dollar_vol"] is None and c["cost_round_trip_bps"] == 35.0


# ─────────────────────────────── callers ─────────────────────────────────────

def test_u_plan_writes_stories_in_a_sandbox_and_appends_the_line(tmp_path, monkeypatch):
    from backend.tests import test_u_plan_probe as T
    T.FakeBroker(is_open=False).install(monkeypatch)
    T._funnel(tmp_path, n=25)
    T._ranking(tmp_path / "out", net=-0.2)
    res = T._run(tmp_path, mode="observe")
    assert res["n_sent"] == 0
    assert res["decision_story_new"] == 25 + 18
    line = res["decision_story_line"]
    assert "abstentions frozen with BUY counterfactuals" in line and "replay MATCHES" in line
    assert "live stories on disk: 43" in line
    rec = json.loads((tmp_path / "out" / "intended_book.json").read_text(encoding="utf-8"))
    assert rec["decision_story"]["replay_matches_actual"] is True
    assert rec["decision_story_line"] == line
    assert (tmp_path / "out" / "decision_story").is_dir(), "a sandbox never writes the live folder"
    # the zero-order explanation carries the line whenever there is one
    res0 = T._run(tmp_path, mode="observe")
    if res0["why_zero_orders"] is not None:
        assert "abstentions frozen" in res0["why_zero_orders"]
    else:
        assert res0["n_orders"] > 0


def test_why_zero_orders_carries_the_story_line_when_nothing_is_planned(tmp_path, monkeypatch):
    from backend.tests import test_u_plan_probe as T
    T.FakeBroker(is_open=False).install(monkeypatch)
    T._funnel(tmp_path, n=25)
    T._ranking(tmp_path / "out", net=-0.2)
    monkeypatch.setattr(PB, "plan_orders", lambda *a, **k: [])
    res = T._run(tmp_path, mode="observe")
    assert res["n_orders"] == 0
    assert res["why_zero_orders"] is not None and "abstentions frozen" in res["why_zero_orders"]


def _exploit_acting(tmp_path, monkeypatch, *, gate_scale: float):
    from backend.tests import test_u_plan_probe as T
    T.FakeBroker(is_open=False).install(monkeypatch)
    T._funnel(tmp_path, n=25)
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps({
        "asof": T.ASOF, "top20_net_rel_21d": 0.01, "model_version": "test",
        "top": [{"rank": i + 1, "symbol": f"RK{i:02d}", "decile": 9,
                 "expected_relative_return_21d_net": 0.01 - i / 1000}
                for i in range(18)]}), encoding="utf-8")
    monkeypatch.setattr(S, "_blend_grade", lambda *a, **k: {
        "verdict": "MEASURED_POSITIVE", "may_trade": True, "why": "test"})

    def gate(targets, **kw):
        for t in targets:
            if t.symbol in kw["ex_syms"]:
                t.weight = float(t.weight) * gate_scale
        return {"block": None, "scale_exploit": gate_scale, "line": "test gate"}
    monkeypatch.setattr(S, "_order_path_gate", gate)
    return T._run(tmp_path)


def test_replay_matches_pre_gate_and_names_the_bound_order_gate(tmp_path, monkeypatch):
    """Review F5: the order-path gate scales EXPLOIT before the freeze. The
    replay reproduces the PRE-gate book; leave-one-out rows for EXPLOIT names
    say the gate bound instead of pretending to know its scale."""
    res = _exploit_acting(tmp_path, monkeypatch, gate_scale=0.5)
    assert res["exploit_acting"] is True
    rec = json.loads((tmp_path / "out" / "intended_book.json").read_text(encoding="utf-8"))
    ds = rec["decision_story"]
    assert ds["replay_matches_actual"] is True and ds["order_gate_scale_exploit"] == 0.5
    assert "order gate scaled EXPLOIT x0.500" in ds["line"]
    alts = DS.read_jsonl(Path(ds["alternatives_path"]))
    st = {s["ticker"]: s for s in DS.read_jsonl(Path(ds["stories_path"])) if s["kind"] == "decision"}
    exploit = {t for t, s in st.items() if s["state"] == "EXPLOIT"}
    ex = [a for a in alts if a["ticker"] in exploit and a["alt"] == "loo_analyst"]
    assert ex and all(a["status"] == "NOT_SEPARABLE" and "order gate bound" in a["why"] for a in ex)
    # a pool name EXPLOIT in neither book carries weight 0 whatever the gate did
    other = [a for a in alts if a["ticker"].startswith("RK") and a["ticker"] not in exploit
             and a["alt"] == "loo_analyst"]
    assert all(a["status"] == "NOT_SEPARABLE" or a["target_weight"] == 0.0 for a in other)
    rk = next(s for s in st.values() if s["state"] == "EXPLOIT")
    assert rk["target_weight"] == pytest.approx(rk["plan_full_weight"] * 0.5)


def test_a_drifted_replay_is_a_red_line_not_a_silent_mismatch(tmp_path, monkeypatch):
    """If u_plan's sizing changes and `replan` does not, the receipt says
    MISMATCH and no leave-one-out is trusted."""
    real = DS.replan

    def drifted(inp, names, **kw):
        out = real(inp, names, **kw)
        out["weights"] = {k: v * 1.01 for k, v in out["weights"].items()}
        return out
    monkeypatch.setattr(DS, "replan", drifted)
    _exploit_acting(tmp_path, monkeypatch, gate_scale=1.0)
    rec = json.loads((tmp_path / "out" / "intended_book.json").read_text(encoding="utf-8"))
    assert rec["decision_story"]["replay_matches_actual"] is False
    assert "replay MISMATCH" in rec["decision_story_line"]


@pytest.mark.parametrize("n_pool", [5, 18])
@pytest.mark.parametrize("forecast_present", [False, True])
@pytest.mark.parametrize("probe_present", [False, True])
def test_no_er_inventory_replay_obeys_exploit_cap(n_pool, forecast_present, probe_present):
    symbols = [f"RK{i:02d}" for i in range(n_pool)]
    probe_weight = 0.02 if probe_present else 0.0
    expected = min((1.0 - probe_weight) / n_pool, 0.10)
    actual = {s: expected for s in symbols}
    if probe_present:
        actual["AAA"] = probe_weight
    inp = _inp(pool=[{"symbol": s} for s in symbols],
               shortlist=_inp()["shortlist"] if probe_present else [],
               actual_weights=actual)
    names = ({s: {"h21": {"er": None, "x": {}, "weights": {}},
                  "size_scale": 0.5} for s in symbols} if forecast_present else None)
    chk = DS.replay_check(inp, names)
    assert chk["matches"] is True, chk["diff"]
    assert all(w <= inp["exploit_max_weight"] for s, w in chk["replay"]["weights"].items()
               if s in symbols)


def test_u_plan_null_analyst_forecast_replays_five_name_inventory(tmp_path, monkeypatch):
    from backend.tests import test_u_plan_probe as T
    from backend.services import expected_return as ER
    broker = T.FakeBroker(is_open=False).install(monkeypatch)
    T._funnel(tmp_path, n=0)
    symbols = [f"RK{i:02d}" for i in range(5)]
    T._ranking(tmp_path / "out", net=None, symbols=symbols)
    src = ER.Sources(label="without_analyst_regression", predictions=[], decision_rows=[],
                     unavailable={"revisions": "analyst ablated", "ranking": "unmeasured"})
    res = S.u_plan(tmp_path / "out", "research", asof=T.ASOF,
                   funnel_path=tmp_path / "funnel.json", ledger_path=tmp_path / "ledger.jsonl",
                   contracts_dir=tmp_path / "contracts", er_sources=src,
                   er_dir=tmp_path / "forecast")
    rec = T._receipt(tmp_path)
    ds = rec["decision_story"]
    assert res["n_sent"] == 0 and not broker.submitted
    assert ds["replay_matches_actual"] is True, ds["replay_diff"]
    assert "replay MATCHES" in res["decision_story_line"]
    stories = DS.read_jsonl(Path(ds["stories_path"]))
    inventory = [s for s in stories if s["ticker"] in symbols]
    assert len(inventory) == 5
    assert all(s["target_weight"] == pytest.approx(config.ER_EXPLOIT_MAX_WEIGHT)
               and s["plan_full_weight"] == pytest.approx(s["target_weight"]) for s in inventory)
    assert ds["loo_status"]["news"]["status"] == "IDENTICAL_NOT_READ"


def test_task_keeper_regret_daily_pass_step_and_policy_state_read(tmp_path, monkeypatch):
    out = TK.run_regret(grade=lambda: {"status": "OK", "run_id": "r1", "line": "x"},
                        log_path=tmp_path / "k.jsonl")
    assert out["action"] == "ok" and out["regret"]["run_id"] == "r1"

    def boom() -> dict:
        raise RuntimeError("bars gone")
    out = TK.run_regret(grade=boom, log_path=tmp_path / "k.jsonl")
    assert out["action"] == "refused" and "bars gone" in out["regret"]["why"]

    from scripts import daily_pass as DP
    assert "regret" in {s for s, _ in DP.STEPS} and "regret" in config.DAILY_PASS_STEP_BOX_S
    order = [s for s, _ in DP.STEPS]
    assert order.index("regret") > order.index("grade_forecasts") > order.index("bars_refresh")
    monkeypatch.setattr(DP, "run_regret", lambda timeout_s: {
        "status": "nothing_to_do", "n_rows": 0, "line": "nothing matured yet", "rc": 0})
    row = DP.step_regret({})
    assert row["status"] == "nothing_to_do"

    assert PS.regret_view(tmp_path / "none")["use"] is False
    _freeze(tmp_path / "s")
    RL.grade_due(TODAY.isoformat(), story_dir=tmp_path / "s",
                 bars=_bars(ASOF_OLD, drift=DRIFT), out_dir=tmp_path / "rg")
    before = sorted(p.name for p in (tmp_path / "rg").iterdir())
    v = PS.regret_view(tmp_path / "rg")
    assert v["use"] is True and v["trusted"] is False and "never a risk limit" in v["may_change"]
    assert sorted(p.name for p in (tmp_path / "rg").iterdir()) == before, "READ, never write"
    from scripts import night_morning_report as MR
    monkeypatch.setattr(PS, "regret_view", lambda *a, **k: v)
    assert MR.block_regret()[0].startswith("- regret ledger (")
