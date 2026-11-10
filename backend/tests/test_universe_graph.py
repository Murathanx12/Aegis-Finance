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
    a = UG.propagate(g, ev)
    b = UG.propagate(g, ev)
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
    down = UG.propagate(g, {**ev, "direction": "down"})
    f1d = [i for i in down if i.target == "company:FOLLOW" and i.horizon == 1]
    assert f1d[0].expected_direction == -1
    # a round trip through disk returns the same implications
    rec = {"build_id": "ug_test", "as_of": g.as_of, "built_utc": "2021-06-01T00:00:00+00:00",
           "params": __import__("dataclasses").asdict(g.params), "counts": g.counts()}
    UG.write_graph(g, tmp_path, rec)
    g2 = UG.load_graph(tmp_path)
    assert [i.to_dict() for i in UG.propagate(g2, ev)] == [i.to_dict() for i in a]


def test_shock_z_is_capped_so_a_huge_event_cannot_extrapolate():
    g = _graph(_panel())
    big = UG.propagate(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": 5.0})
    cap = g.params.max_shock_z * g.nodes["company:LEAD"].attrs["sigma"]
    capped = UG.propagate(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": cap})
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
    imps = UG.propagate(g, {"node_id": "company:LEAD", "direction": "up", "magnitude": 0.07})
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
        UG.propagate(g, {"node_id": "company:LEAD", "direction": "up", "as_of": "2021-01-04"})
    with pytest.raises(UG.UnknownNode):
        UG.propagate(g, {"node_id": "company:NOPE", "direction": "up"})
    with pytest.raises(UG.GraphRefused):
        UG.propagate(g, {"node_id": "company:LEAD", "direction": "sideways"})


def test_consumers_return_graph_sourced_rows():
    g = _graph(_panel())
    ev = [{"node_id": "company:LEAD", "direction": "down", "magnitude": 0.07}]
    rows = UG.funnel_candidates(g, ev, horizon=1, min_label="LOW")
    assert rows and all(r["source"] == "graph" for r in rows)
    assert "FOLLOW" in [r["ticker"] for r in rows]
    held = UG.holdings_exposure(g, ["FOLLOW"], ev)
    assert held and {r["ticker"] for r in held} == {"FOLLOW"}
    warn = UG.owner_warnings(g, ["FOLLOW"], ev, min_label="LOW")
    assert warn and all(w["expected_direction"] < 0 for w in warn)


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
