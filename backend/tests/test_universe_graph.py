"""universe_graph v1 (CH-30): PIT, shrinkage, propagation, refusal, staleness.

Offline and synthetic: a tiny panel where FOLLOW reacts one session after LEAD's
shocks, so the right answer is known before the graph is asked.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import universe_graph as UG


def _panel(n_days: int = 420, seed: int = 7) -> pd.DataFrame:
    """Market-adjusted returns: LEAD shocks every ~15 sessions; FOLLOW = 0.5 x LEAD(t-1)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    lead = rng.normal(0, 0.01, n_days)
    shock_days = np.arange(70, n_days, 15)
    lead[shock_days] = rng.choice([-0.07, 0.07], size=len(shock_days))
    follow = rng.normal(0, 0.004, n_days)
    follow[1:] += 0.5 * lead[:-1]
    other = rng.normal(0, 0.01, (n_days, 3))
    df = pd.DataFrame({"LEAD": lead, "FOLLOW": follow, "OTH1": other[:, 0],
                       "OTH2": other[:, 1], "OTH3": other[:, 2]}, index=dates)
    return df


SECTORS = {"LEAD": "Semis", "FOLLOW": "Semis", "OTH1": "Semis", "OTH2": "Banks",
           "OTH3": "Banks"}


def _graph(df: pd.DataFrame, as_of: str = "2021-06-01") -> UG.UniverseGraph:
    return UG.build_graph(df, as_of=as_of, sectors=SECTORS,
                          themes={"theme:ai_demand": {"LEAD", "FOLLOW", "OTH1"}})


def _rr(g: UG.UniverseGraph, src: str, dst: str) -> UG.Edge:
    hits = [e for e in g.edges if e.type == "return_response" and e.src == src and e.dst == dst]
    assert len(hits) == 1, (src, dst, len(hits))
    return hits[0]


def test_forward_sums_excludes_day_t_and_needs_full_window():
    X = np.array([[1.0], [2.0], [4.0], [np.nan], [8.0]])
    f1 = UG.forward_sums(X, 1)
    assert f1[0, 0] == 2.0 and f1[1, 0] == 4.0
    assert np.isnan(f1[2, 0])                     # window holds the NaN
    assert np.isnan(f1[4, 0])                     # beyond the panel
    f2 = UG.forward_sums(X, 2)
    assert f2[0, 0] == 6.0 and np.isnan(f2[1, 0])


def test_fit_response_is_shrunk_by_n_over_n_plus_k():
    s = np.array([0.05, -0.05, 0.06, -0.04, 0.05, 0.07])
    Y = (2.0 * s)[:, None]
    f = UG.fit_response(s, Y, k=20.0)
    assert f["n"][0] == 6
    assert f["raw"][0] == pytest.approx(2.0)
    assert f["w"][0] == pytest.approx(2.0 * 6 / 26)


def test_known_answer_lead_follow_edge_is_found():
    g = _graph(_panel())
    e = _rr(g, "company:LEAD", "company:FOLLOW")
    assert e.horizons[1]["ret_slope"] == pytest.approx(0.5, abs=0.1)   # return units
    assert e.horizons[1]["raw"] > 0.5                                   # sigma units
    assert 0 < e.horizons[1]["w"] < e.horizons[1]["raw"]                # shrunk
    assert "sector_member" in e.via
    # the reverse direction carries no lagged response
    back = [x for x in g.edges if x.type == "return_response"
            and x.src == "company:FOLLOW" and x.dst == "company:LEAD"]
    assert not back or abs(back[0].horizons[1]["ret_slope"]) < 0.2
    # banks are not candidates of a semis name (no structural edge => no pair)
    assert not [x for x in g.edges if x.type == "return_response"
                and x.src == "company:LEAD" and x.dst == "company:OTH2"]
    counts = g.counts()
    assert counts["nodes"]["company"] == 5 and counts["nodes"]["sector"] == 2


def test_weights_are_point_in_time():
    df = _panel()
    as_of = "2021-03-01"
    g1 = _graph(df, as_of)
    poisoned = df.copy()
    poisoned.loc[poisoned.index >= pd.Timestamp(as_of)] = 0.5   # absurd future bars
    g2 = _graph(poisoned, as_of)
    n1, e1 = g1.to_frames()
    n2, e2 = g2.to_frames()
    pd.testing.assert_frame_equal(e1, e2)
    pd.testing.assert_frame_equal(n1, n2)
    # and the future does change a graph built after it (the test can fail)
    g3 = _graph(poisoned, "2021-09-01")
    assert not g3.to_frames()[1].equals(g1.to_frames()[1])


def test_propagate_known_answer_and_determinism(tmp_path: Path):
    g = _graph(_panel())
    ev = {"node_id": "company:LEAD", "direction": "up", "magnitude": 0.07,
          "as_of": "2021-06-02"}
    a = UG.propagate_price_shock(g, ev)
    b = UG.propagate_price_shock(g, ev)
    assert [i.to_dict() for i in a] == [i.to_dict() for i in b]
    f1 = [i for i in a if i.target == "company:FOLLOW" and i.horizon == 1]
    assert f1 and f1[0].expected_direction == 1
    # ~ 0.5 x 0.07, shrunk by n/(n+k) with n ~ 20, k = 20
    assert 0.005 < f1[0].expected_size < 0.04
    lead_sig = g.nodes["company:LEAD"].attrs["sigma"]
    fol_sig = g.nodes["company:FOLLOW"].attrs["sigma"]
    assert f1[0].expected_size == pytest.approx(
        f1[0].weight * (0.07 / lead_sig) * fol_sig, rel=1e-3)
    assert f1[0].path == ["company:LEAD", "company:FOLLOW"]
    down = UG.propagate_price_shock(g, {**ev, "direction": "down"})
    f1d = [i for i in down if i.target == "company:FOLLOW" and i.horizon == 1]
    assert f1d[0].expected_direction == -1
    # a round trip through disk returns the same implications
    rec = {"build_id": "ug_test", "as_of": g.as_of, "built_utc": "2021-06-01T00:00:00+00:00",
           "params": __import__("dataclasses").asdict(g.params), "counts": g.counts()}
    UG.write_graph(g, tmp_path, rec)
    g2 = UG.load_graph(tmp_path)
    assert [i.to_dict() for i in UG.propagate_price_shock(g2, ev)] == [i.to_dict() for i in a]


def test_shock_z_is_capped_so_a_huge_event_cannot_extrapolate():
    g = _graph(_panel())
    big = UG.propagate_price_shock(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": 5.0})
    cap = g.params.max_shock_z * g.nodes["company:LEAD"].attrs["sigma"]
    capped = UG.propagate_price_shock(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": cap})
    assert [i.expected_size for i in big] == [i.expected_size for i in capped]


def test_two_hop_paths_and_low_confidence_when_n_small():
    df = _panel()
    rng = np.random.default_rng(3)
    df["DOWN"] = rng.normal(0, 0.004, len(df))
    df.iloc[1:, df.columns.get_loc("DOWN")] += 0.5 * df["FOLLOW"].to_numpy()[:-1]
    # DOWN is linked to FOLLOW only (a theme LEAD is not in): LEAD -> FOLLOW -> DOWN
    g = UG.build_graph(df, as_of="2021-06-01", sectors=SECTORS,
                       themes={"theme:ai_demand": {"LEAD", "FOLLOW", "OTH1"},
                               "theme:downstream": {"FOLLOW", "DOWN"}})
    imps = UG.propagate_price_shock(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": 0.07})
    two = [i for i in imps if i.target == "company:DOWN" and i.hops == 2]
    assert two and two[0].path[0] == "company:LEAD" and len(two[0].path) == 3
    assert all(i.target != "company:DOWN" for i in imps if i.hops == 1)
    p = UG.GraphParams()
    assert UG.confidence_of(p.min_n_confident - 1, 10.0, p)[1] == "LOW"
    assert UG.confidence_of(200, 10.0, p)[1] == "HIGH"
    assert UG.confidence_of(200, 1.9, p)[1] == "LOW"
    assert UG.confidence_of(200, 2.5, p)[1] == "MEDIUM"


def test_propagate_refuses_lookahead_and_unknown_nodes():
    g = _graph(_panel())
    with pytest.raises(UG.GraphRefused):
        UG.propagate_price_shock(g, {"node_id": "company:LEAD", "direction": "up", "as_of": "2021-01-04"})
    with pytest.raises(UG.UnknownNode):
        UG.propagate_price_shock(g, {"node_id": "company:NOPE", "direction": "up"})
    with pytest.raises(UG.GraphRefused):
        UG.propagate_price_shock(g, {"node_id": "company:LEAD", "direction": "sideways"})


def _weights(w: float = -0.2, d: int = -1) -> pd.DataFrame:
    rows = []
    for h in (1, 5, 21):
        rows.append({"family": "8k_results", "edge": "sector", "d": d, "h": h, "mean": w * 1.2,
                     "n": 400, "sd": 1.0, "w": w, "t": 4.0, "as_of": "2021-06-01"})
    return pd.DataFrame(rows)


def _attach_checked(g: UG.UniverseGraph, tmp: Path, *, p: float = 1e-9,
                    w: float = -0.2) -> dict:
    """What `event-check` writes for the 8k_results x sector cells (weights + the
    hash-linked receipt over the full registered grid), attached to `g`. p tiny =
    the cells survive; p = 0.5 = measured and NOT validated (review2 #93)."""
    from backend import config
    ev = tmp / "event_response"
    m = UG.register_grid(ev)["tradable"]
    cells = [{"family": "8k_results", "subset": "all", "edge": "sector", "h": h, "n": 400,
              "tradable": True, "p_vs_liquid": p, "p_vs_sector": p, "p_vs_placebo": p,
              "p_vs_ordinary_day": p, "diff_vs_liquid_bps": 20.0, "diff_vs_sector_bps": 15.0,
              "diff_vs_placebo_bps": 12.0, "diff_vs_ordinary_day_bps": 10.0,
              "years_positive": "9/9", "loyo_worst_bps": 5.0,
              "tail_top1pct_share_of_signed_ret": 0.1} for h in (1, 5, 21)]
    W = _weights(w=w)
    W["subset"] = "all"
    UG.write_event_check_outputs(
        ev, run_id="event_check_20210601T000000Z",
        res={"cells": UG.screen_cells(cells, 0.10, m_total=m), "weights": W}, receipt={},
        grid=UG.grid_of_run(ev, families=UG.EVENT_FAMILIES,
                            years=config.UNIVERSE_GRAPH_EVENT_CHECK_YEARS,
                            horizons=config.UNIVERSE_GRAPH_EVENT_HORIZONS,
                            top_n=config.UNIVERSE_GRAPH_EVENT_TOP_N))
    return UG.attach_event_weights(g, None, tmp)


def test_consumers_return_graph_sourced_rows_only_for_typed_events(tmp_path: Path):
    g = _graph(_panel())
    _attach_checked(g, tmp_path)
    ev = [{"node_id": "company:LEAD", "event_type": "8k_results", "direction": "down"}]
    rows = UG.funnel_candidates(g, ev, horizon=1, min_label="MEDIUM")
    assert rows and all(r["source"] == "graph" for r in rows)
    assert {"FOLLOW", "OTH1"} <= {r["ticker"] for r in rows}
    held = UG.holdings_exposure(g, ["FOLLOW"], ev)
    assert held and {r["ticker"] for r in held} == {"FOLLOW"}
    warn = UG.owner_warnings(g, ["FOLLOW"], ev, min_label="MEDIUM")
    assert warn and all(w["expected_direction"] < 0 for w in warn)
    # an UNTYPED event never reaches the funnel or a warning, whatever the price weights say
    untyped = [{"node_id": "company:LEAD", "direction": "down", "magnitude": 0.07}]
    assert UG.funnel_candidates(g, untyped, horizon=1, min_label="LOW") == []
    assert UG.owner_warnings(g, ["FOLLOW"], untyped, min_label="LOW") == []


def test_untyped_event_is_context_only_never_price_shock_weights():
    g = _graph(_panel())
    g.event_weights = _weights()
    imps = UG.propagate(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": 0.07})
    assert imps, "context rows list who is connected"
    assert all(i.expected_direction == 0 and i.expected_size is None and i.weight is None
               for i in imps)
    assert all("return_response" not in i.edge_types for i in imps)
    assert all(i.why.startswith("context only") for i in imps)
    assert {"company:FOLLOW", "company:OTH1"} <= {i.target for i in imps}
    # unknown type, missing direction, no weights: all context only
    for ev in ({"node_id": "company:LEAD", "event_type": "rumour", "direction": "up"},
               {"node_id": "company:LEAD", "event_type": "8k_results"}):
        assert all(i.expected_size is None for i in UG.propagate(g, ev))
    g.event_weights = None
    assert all(i.expected_size is None for i in UG.propagate(
        g, {"node_id": "company:LEAD", "event_type": "8k_results", "direction": "down"}))


def test_typed_event_reads_event_weights_and_unvalidated_is_context_only(tmp_path: Path):
    g = _graph(_panel())
    _attach_checked(g, tmp_path / "ok")
    ev = {"node_id": "company:LEAD", "event_type": "8k_results", "direction": "down"}
    a = UG.propagate(g, ev)
    assert [i.to_dict() for i in a] == [i.to_dict() for i in UG.propagate(g, ev)]
    f5 = [i for i in a if i.target == "company:FOLLOW" and i.horizon == 5]
    assert f5 and f5[0].expected_direction == -1
    sig = g.nodes["company:FOLLOW"].attrs["sigma"]
    assert f5[0].expected_size == pytest.approx(-0.2 * sig * 5 ** 0.5, rel=1e-4)
    assert f5[0].edge_types == ["event_response:sector"] and f5[0].confidence_label == "HIGH"
    assert "SURVIVED" in f5[0].why
    # banks are not connected to a semis name
    assert not [i for i in a if i.target == "company:OTH2"]
    # the "up" cell was never measured -> nothing directional for an up move
    up = UG.propagate(g, {**ev, "direction": "up"})
    assert all(i.expected_size is None for i in up)
    # measured but NOT validated: context only (review2 #93 B2)
    _attach_checked(g, tmp_path / "no", p=0.5)
    low = UG.propagate(g, ev)
    assert low and all(i.confidence_label == "LOW" for i in low)
    assert all(i.expected_direction == 0 and i.expected_size is None for i in low)
    assert all("NOT validated" in i.why for i in low)


def test_event_weights_round_trip_and_lookahead_refusal(tmp_path: Path):
    g = _graph(_panel())
    _attach_checked(g, tmp_path)
    rec = {"build_id": "ug_ev", "as_of": g.as_of, "built_utc": "2021-06-01T00:00:00+00:00",
           "params": __import__("dataclasses").asdict(g.params), "counts": g.counts()}
    UG.write_graph(g, tmp_path, rec)
    g2 = UG.load_graph(tmp_path)
    ev = {"node_id": "company:LEAD", "event_type": "8k_results", "direction": "down"}
    assert [i.to_dict() for i in UG.propagate(g2, ev)] == [i.to_dict() for i in UG.propagate(g, ev)]
    wp = tmp_path / "w.parquet"
    late = _weights()
    late["as_of"] = "2021-07-01"                       # fitted after the graph's as_of
    late.to_parquet(wp, index=False)
    with pytest.raises(UG.GraphRefused):
        UG.attach_event_weights(g, wp, tmp_path)
    assert UG.attach_event_weights(g, None, tmp_path / "none")["status"] == "MISSING"
    # runs over different families merge; the newest run wins per family
    er = tmp_path / "multi" / "event_response"
    er.mkdir(parents=True)
    a = _weights()
    a.to_parquet(er / "event_check_20210101T000000Z_weights.parquet", index=False)
    b = _weights(w=0.3)
    b["family"] = "rev_up"
    b.to_parquet(er / "event_check_20210102T000000Z_weights.parquet", index=False)
    c = _weights(w=-0.5)
    c.to_parquet(er / "event_check_20210103T000000Z_weights.parquet", index=False)
    row = UG.attach_event_weights(g, None, tmp_path / "multi")
    assert row["families"] == {"8k_results": "event_check_20210103T000000Z_weights.parquet",
                               "rev_up": "event_check_20210102T000000Z_weights.parquet"}
    assert set(g.event_weights["family"]) == {"8k_results", "rev_up"}
    assert (g.event_weights.loc[g.event_weights["family"] == "8k_results", "w"] == -0.5).all()


# ── event-typed edges: timing, families, PIT structure, the held-out screen ──

def test_eightk_family_priority():
    assert UG.eightk_family(["2.02", "7.01", "9.01"]) == "8k_results"
    assert UG.eightk_family("7.01,9.01") == "8k_regfd"
    assert UG.eightk_family(["5.02", "1.01"]) == "8k_agreement"
    assert UG.eightk_family(["2.06", "2.02"]) == "8k_results"
    assert UG.eightk_family(["4.02"]) == "8k_distress"
    assert UG.eightk_family(["9.01"]) is None and UG.eightk_family(None) is None


def test_effective_session_rules():
    sess = pd.bdate_range("2024-03-04", periods=10)        # Mon 4 .. Fri 15 March 2024
    ts = pd.Series(pd.to_datetime([
        "2024-03-05 13:00:00+00:00",    # 09:00 ET Tue  -> Tue (before the close)
        "2024-03-05 21:30:00+00:00",    # 16:30 EST Tue -> Wed (no DST until 10 March)
        "2024-03-09 15:00:00+00:00",    # Saturday      -> Mon 11
        "2024-03-05 00:00:00+00:00",    # date only Tue -> Wed, window starts Tue
        "2024-03-15 21:00:00+00:00",    # after the last session -> beyond the panel
    ]))
    prec = ["timestamp", "timestamp", "timestamp", "date", "timestamp"]
    start, eff = UG.effective_sessions(sess, ts, prec)
    d = [str(sess[i].date()) if i >= 0 else None for i in eff]
    assert d == ["2024-03-05", "2024-03-06", "2024-03-11", "2024-03-06", None]
    assert str(sess[start[3]].date()) == "2024-03-05" and start[1] == eff[1]


def test_cocoverage_and_seglinks_are_point_in_time():
    rev = pd.DataFrame({"ticker": ["A", "A", "B", "B", "C", "A"],
                        "firm": ["f1", "f2", "f1", "f2", "f9", "f3"],
                        "day": pd.to_datetime(["2020-03-01", "2020-04-01", "2020-03-02",
                                               "2020-05-01", "2020-05-01", "2021-03-01"])})
    cov = UG.coverage_sets_as_of(rev, "2021-01-01", 730)
    assert cov["A"] == frozenset({"f1", "f2"})          # the 2021 row is the future
    peers = UG.cocoverage_peers(cov, ["A", "B", "C"], top_k=5, min_jaccard=0.3)
    assert peers["A"] == ["B"] and "C" not in peers
    seg = pd.DataFrame({"stic": ["SUP"], "ctic": ["CUS"],
                        "srcdate": pd.to_datetime(["2020-12-31"])})
    c0, _ = UG.seglinks_as_of(seg, "2021-03-01", lag_days=120, valid_days=450)
    assert not c0                                       # 10-K not yet filed
    c1, s1 = UG.seglinks_as_of(seg, "2021-06-01", lag_days=120, valid_days=450)
    assert c1 == {"SUP": {"CUS"}} and s1 == {"CUS": {"SUP"}}
    c2, _ = UG.seglinks_as_of(seg, "2022-12-01", lag_days=120, valid_days=450)
    assert not c2                                       # expired


def test_bh_fdr_matches_hand_computation():
    q = UG.bh_fdr([0.01, 0.04, 0.03, float("nan"), 0.20])
    assert np.isnan(q[3])
    # m = 4: sorted p 0.01, 0.03, 0.04, 0.20 -> 0.04, 0.0533, 0.0533, 0.20
    assert q[0] == pytest.approx(0.04)
    assert q[2] == pytest.approx(0.04 * 4 / 3) and q[1] == pytest.approx(0.04 * 4 / 3)
    assert q[4] == pytest.approx(0.20)


def _event_world(planted: float, seed: int = 5, same_day: float = 0.0, factor: float = 0.0):
    """40 names in 4 sectors over 2016-2020; eight LEADs announce every 7 sessions;
    the sector peers of the announcer drift `planted` sigma over the next 5 sessions
    in the sign of its move."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2016-01-04", "2020-12-31")
    names = [f"S{i:02d}" for i in range(40)]
    X = rng.normal(0, 0.01, (len(dates), 40))
    sectors = {n: f"sec{i % 4}" for i, n in enumerate(names)}
    if factor:
        # a sector factor EVERY day: peers co-move with the announcer on ordinary days too
        F = rng.normal(0, 0.01, (len(dates), 4))
        X += factor * F[:, [i % 4 for i in range(40)]]
    ev = []
    for t in range(80, len(dates) - 30, 7):
        a = int(rng.integers(8))
        mv = float(rng.choice([-0.05, 0.05]))
        if factor:
            mv = float(X[t, a])         # no event content: A's sign is its ordinary move
        else:
            X[t, a] = mv
        for j, n in enumerate(names):
            if j != a and sectors[n] == sectors[names[a]]:
                X[t + 1:t + 6, j] += np.sign(mv) * planted * 0.01 / 5 ** 0.5
                X[t, j] += np.sign(mv) * same_day * 0.01
        ev.append({"symbol": names[a], "family": "8k_results",
                   "ts_utc": pd.Timestamp(dates[t]).tz_localize("UTC") + pd.Timedelta(hours=13),
                   "precision": "timestamp", "source": "test"})
    adj = pd.DataFrame(X, index=dates, columns=names)
    panel = UG.EventPanel.from_returns(adj, horizons=(1, 5), sigma_window=63, clip_z=4.0,
                                       max_abs_daily=0.75)
    empty_seg = pd.DataFrame({"stic": pd.Series(dtype=str), "ctic": pd.Series(dtype=str),
                              "srcdate": pd.Series(dtype="datetime64[ns]")})
    structures = {Y: UG.event_structure_as_of(f"{Y}-01-01", names, sectors=sectors, themes={},
                                              coverage={}, seglink=empty_seg, top_k=10,
                                              min_jaccard=0.3, lag_days=120, valid_days=450,
                                              panel_symbols=names)
                  for Y in range(2016, 2021)}
    evs = pd.DataFrame(ev)
    st, ef = UG.effective_sessions(panel.dates, evs["ts_utc"], evs["precision"])
    return panel, structures, evs.assign(start=st, eff=ef)


def test_planted_sector_spillover_is_found_held_out_and_null_is_not():
    for planted, expect in ((1.5, True), (0.0, False)):
        panel, structures, evs = _event_world(planted)
        tab = UG.event_implications(panel, evs, structures, horizons=(1, 5), peer_cap=15, seed=1)
        assert set(tab["edge"].unique()) >= {0, 1}       # self + sector
        cells, _ = UG.event_walk_forward(tab, panel.dates, years=[2018, 2019, 2020],
                                         horizons=(1, 5), k=20.0, min_rows=30)
        cells = UG.screen_cells(cells, 0.10)
        sec5 = [c for c in cells if c["edge"] == "sector" and c["h"] == 5][0]
        assert sec5["n"] > 500
        assert sec5["survives"] is expect, sec5["fails_because"]
        if expect:
            assert sec5["hit_graph"] > sec5["hit_ctrl_liquid"] + 0.1
            assert sec5["diff_vs_liquid_bps"] > 0 and sec5["years_positive"] == "3/3"


def test_same_session_transfer_is_measured_but_never_a_survivor():
    panel, structures, evs = _event_world(0.0, same_day=1.0)
    tab = UG.event_implications(panel, evs, structures, horizons=(0, 1, 5), peer_cap=15, seed=1)
    sec = tab[tab["edge"] == 1]
    # day-e window of the peers moves with the announcer; nothing after it
    assert np.nanmean(np.sign(sec["r0"]) == sec["d"]) > 0.75
    cells, _ = UG.event_walk_forward(tab, panel.dates, years=[2018, 2019, 2020],
                                     horizons=(0, 1, 5), k=20.0, min_rows=30)
    h0 = UG.screen_cells([c for c in cells if c["h"] == 0], 0.10)
    tr = UG.screen_cells([c for c in cells if c["h"] > 0], 0.10)
    assert [c for c in h0 if c["edge"] == "sector"][0]["survives"]
    assert not [c for c in tr if c["edge"] == "sector" and c["survives"]]


def test_sector_factor_comovement_is_not_credited_to_the_event():
    # no event effect at all, only a daily sector factor: the event-day co-move beats a
    # random name but NOT the same pair on an ordinary day, so nothing may pass
    panel, structures, evs = _event_world(0.0, factor=1.0)
    tab = UG.event_implications(panel, evs, structures, horizons=(0, 1), peer_cap=15, seed=1)
    cells, _ = UG.event_walk_forward(tab, panel.dates, years=[2018, 2019, 2020],
                                     horizons=(0, 1), k=20.0, min_rows=30)
    h0 = UG.screen_cells([c for c in cells if c["h"] == 0], 0.10)
    sec0 = [c for c in h0 if c["edge"] == "sector"][0]
    assert sec0["t_vs_liquid"] > 3                      # looks like transfer against a random name
    assert not sec0["survives"]                         # but an ordinary day explains it
    assert any("ordinary day" in r for r in sec0["fails_because"]) or sec0["q_bh"] > 0.1


def test_event_content_sign_overrides_the_move_sign():
    panel, structures, evs = _event_world(0.0)
    evs = evs.assign(event_sign=-1.0)            # every surprise negative, whatever A did
    tab = UG.event_implications(panel, evs, structures, horizons=(1,), peer_cap=15, seed=1)
    assert set(tab["d"].unique()) == {-1}
    tab2 = UG.event_implications(panel, evs.drop(columns="event_sign"), structures,
                                 horizons=(1,), peer_cap=15, seed=1)
    assert set(tab2["d"].unique()) == {-1, 1}


def test_event_weights_are_point_in_time():
    panel, structures, evs = _event_world(1.5)
    tab = UG.event_implications(panel, evs, structures, horizons=(1, 5), peer_cap=15, seed=1)
    kw = dict(family="8k_results", horizons=(1, 5), k=20.0, min_rows=30)
    w1 = UG.event_weight_table(tab, panel.dates, "2019-01-01", **kw)
    poisoned = tab.copy()
    # poison exactly the rows whose outcome window reaches 2019-01-01 or later
    cut = int(np.searchsorted(panel.dates.values, np.datetime64("2019-01-01")))
    e = poisoned["e"].to_numpy()
    poisoned.loc[e >= cut - 1, "y1"] = 9.0
    poisoned.loc[e >= cut - 5, "y5"] = 9.0
    w2 = UG.event_weight_table(poisoned, panel.dates, "2019-01-01", **kw)
    pd.testing.assert_frame_equal(w1, w2)
    w3 = UG.event_weight_table(poisoned, panel.dates, "2020-01-01", **kw)
    assert not w3.equals(w1)


def test_build_graph_refuses_empty_or_short_panel():
    with pytest.raises(UG.GraphRefused):
        UG.build_graph(pd.DataFrame(), as_of="2021-01-01")
    with pytest.raises(UG.GraphRefused):
        UG.build_graph(_panel(), as_of="2020-02-01")      # too few sessions before as_of


# ── CLI: refusal exit codes and staleness ───────────────────────────────────

def _write_root(root: Path, n_names: int = 24) -> None:
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2020-01-01", periods=420)
    rows = []
    mkt = rng.normal(0, 0.01, len(dates))
    for k in range(n_names + 1):
        sym = "SPY" if k == 0 else f"N{k:02d}"
        r = mkt + (0 if k == 0 else rng.normal(0, 0.015, len(dates)))
        close = 50 * np.cumprod(1 + r)
        for d, c in zip(dates, close):
            rows.append({"symbol": sym, "date": d, "open": c, "high": c, "low": c, "close": c,
                         "volume": int(1e6 * (k + 1)), "vwap": c, "trades": 1})
    (root / "prices_deep").mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(root / "prices_deep" / "bars.parquet", index=False)
    (root / "potential_universe").mkdir()
    with (root / "potential_universe" / "2021-07-01.jsonl").open("w", encoding="utf-8") as f:
        for k in range(1, n_names + 1):
            f.write(json.dumps({"symbol": f"N{k:02d}",
                                "identity": {"sector": "Alpha" if k % 2 else "Beta"}}) + "\n")


def test_cli_build_refuses_on_empty_inputs(tmp_path: Path):
    rc = UG.main(["build", "--data-root", str(tmp_path), "--out", str(tmp_path / "out")])
    assert rc == 2
    assert not (tmp_path / "out" / "latest.json").exists()


def test_cli_build_refuses_without_sector_map(tmp_path: Path):
    _write_root(tmp_path)
    for f in (tmp_path / "potential_universe").glob("*"):
        f.unlink()
    rc = UG.main(["build", "--data-root", str(tmp_path), "--out", str(tmp_path / "out"),
                  "--as-of", "2021-08-02"])
    assert rc == 2


def test_cli_build_writes_receipt_and_status_goes_red_when_stale(tmp_path: Path):
    _write_root(tmp_path)
    out = tmp_path / "out"
    rc = UG.main(["build", "--data-root", str(tmp_path), "--out", str(out),
                  "--as-of", "2021-08-02"])
    assert rc in (0, 3)                 # 3 = written but DEGRADED (no coverage / co-mention here)
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    rec = json.loads((out / latest["build_id"] / "receipt.json").read_text(encoding="utf-8"))
    assert rec["as_of"] == "2021-08-02"
    assert rec["counts"]["edges"].get("return_response", 0) > 0
    assert "survivorship" in rec and "verdict" in rec["survivorship"]
    assert rec["liquid_subset"]["chosen"] == 24
    ok = UG.status(out, now="2021-08-05")
    assert ok["status"] == "OK" and not ok["red"]
    stale = UG.status(out, now="2021-08-30")
    assert stale["status"] == "STALE" and stale["red"]
    assert UG.status(tmp_path / "nowhere")["red"]
    assert UG.main(["status", "--out", str(tmp_path / "nowhere")]) == 1


# ── staleness is the DATA's age, not the build's (review #87 R1) ────────────

def _fake_build(out: Path, *, as_of: str, last_session) -> None:
    """A minimal written build whose receipt carries a chosen panel_last_session."""
    bid = f"ug_{as_of.replace('-', '')}_fake"
    (out / bid).mkdir(parents=True)
    rec = {"build_id": bid, "as_of": as_of, "built_utc": f"{as_of}T00:00:00+00:00",
           "counts": {"n_edges": 1}}
    if last_session is not None:
        rec["panel_last_session"] = last_session
    (out / bid / "receipt.json").write_text(json.dumps(rec), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps({"build_id": bid, "as_of": as_of}),
                                     encoding="utf-8")


def test_status_ages_the_newest_input_bar_not_the_build_date(tmp_path: Path):
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    stale_bar = str((today - pd.Timedelta(days=60)).date())
    _fake_build(tmp_path, as_of=str(today.date()), last_session=stale_bar)
    s = UG.status(tmp_path, now=today)
    assert s["red"] and s["status"] == "STALE", s
    assert s["age_days"] == 60 and s["panel_last_session"] == stale_bar


def test_status_is_unknown_and_red_when_the_input_bar_date_is_absent(tmp_path: Path):
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    _fake_build(tmp_path, as_of=str(today.date()), last_session=None)
    s = UG.status(tmp_path, now=today)
    assert s["red"] and s["status"] == "UNKNOWN", s
    _fake_build(tmp_path / "b", as_of=str(today.date()), last_session="not-a-date")
    s = UG.status(tmp_path / "b", now=today)
    assert s["red"] and s["status"] == "UNKNOWN", s


def test_cli_build_refuses_when_the_bars_are_stale_relative_to_as_of(tmp_path: Path):
    _write_root(tmp_path)                       # bars end 2021-08-11
    out = tmp_path / "out"
    rc = UG.main(["build", "--data-root", str(tmp_path), "--out", str(out),
                  "--as-of", "2021-11-01"])     # 82 days after the last bar
    assert rc == 2
    assert not (out / "latest.json").exists()


def test_check_returns_red_when_no_fold_is_ok():
    assert UG._check_rc({"by_year": {"2021": {"status": "SKIPPED"},
                                     "2022": {"status": "REFUSED"}}}) == 2
    assert UG._check_rc({"by_year": {}}) == 2
    assert UG._check_rc({"by_year": {"2021": {"status": "OK"},
                                     "2022": {"status": "SKIPPED"}}}) == 0


def test_trailing_sigma_at_t_excludes_day_t():
    rng = np.random.default_rng(3)
    X = rng.normal(0, 0.01, (80, 1))
    base = UG.trailing_sigma(X, 20)
    X2 = X.copy()
    X2[60, 0] = 0.50                            # a huge same-day move
    s2 = UG.trailing_sigma(X2, 20)
    assert s2[60, 0] == pytest.approx(base[60, 0])     # sigma at t did not see day t
    assert s2[61, 0] > base[61, 0]                     # ...and the next day does
