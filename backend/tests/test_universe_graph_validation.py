"""Second review of PR #93 (2026-11-11): "validated" is derived, never read.

B1  `validated` was a plain column in the weights parquet; any file with
    validated=True lifted its cells to MEDIUM/HIGH. It is now DERIVED at load
    time from the validation receipt `<event_response>/<run_id>.json`, which
    must carry the weights file's sha256, a COMPLETE run of the registered
    grid, and the same grid id; survivors are re-screened from the receipt's
    cell statistics against the full registered grid. A column in a file is
    ignored, and so is one on an in-memory frame.
B2  `propagate` returned a direction and a size for typed but UNVALIDATED
    cells. Those cells are now context only: the connected name, direction 0,
    no size, no weight; w and n stay in the WHY.
B3  The BH denominator was the number of cells that run chose to look at
    (`--families`, `--years`), so re-running one family made "validated"
    easier. The grid registry is persisted; the denominator is every cell ever
    registered; and a partial run never validates.

Offline and synthetic (the CH-30 tiny panel from test_universe_graph).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend import config
from backend.services import universe_graph as UG
from backend.tests.test_universe_graph import _graph, _panel

EV = {"node_id": "company:LEAD", "event_type": "8k_results", "direction": "down"}


def _weights(w: float = -0.2, d: int = -1, family: str = "8k_results") -> pd.DataFrame:
    return pd.DataFrame([{"family": family, "subset": "all", "edge": "sector", "d": d, "h": h,
                          "mean": w * 1.2, "n": 400, "sd": 1.0, "w": w, "t": 4.0,
                          "as_of": "2021-06-01"} for h in (1, 5, 21)])


def _cell(*, family: str = "8k_results", edge: str = "sector", h: int = 1, p: float = 1e-9,
          subset: str = "all") -> dict:
    return {"family": family, "subset": subset, "edge": edge, "h": h, "n": 400,
            "tradable": True, "p_vs_liquid": p, "p_vs_sector": p, "p_vs_placebo": p,
            "p_vs_ordinary_day": p, "diff_vs_liquid_bps": 20.0, "diff_vs_sector_bps": 15.0,
            "diff_vs_placebo_bps": 12.0, "diff_vs_ordinary_day_bps": 10.0,
            "years_positive": "9/9", "loyo_worst_bps": 5.0,
            "tail_top1pct_share_of_signed_ret": 0.1}


def _full_grid() -> dict:
    return dict(families=list(UG.EVENT_FAMILIES),
                years=[int(y) for y in config.UNIVERSE_GRAPH_EVENT_CHECK_YEARS],
                horizons=[int(h) for h in config.UNIVERSE_GRAPH_EVENT_HORIZONS],
                top_n=int(config.UNIVERSE_GRAPH_EVENT_TOP_N))


def _write_check(out: Path, *, run_id: str = "event_check_20210601T000000Z", p: float = 1e-9,
                 weights: pd.DataFrame | None = None, grid: dict | None = None) -> dict:
    """What `event-check` writes: the registry line, the weights, the hash-linked receipt."""
    ev = out / "event_response"
    UG.register_grid(ev)
    cells = [_cell(h=h, p=p) for h in (1, 5, 21)]
    res = {"cells": UG.screen_cells(cells, 0.10, m_total=UG.registered_cell_counts(ev)["tradable"]),
           "weights": _weights() if weights is None else weights}
    return UG.write_event_check_outputs(ev, run_id=run_id, res=res, receipt={},
                                        grid=UG.grid_of_run(ev, **(grid or _full_grid())))


def _f5(g) -> list:
    return [i for i in UG.propagate(g, EV) if i.target == "company:FOLLOW" and i.horizon == 5]


# ─────────────────────────── B1 ─────────────────────────────────────────────

def test_a_complete_receipt_with_matching_hash_validates_its_survivors(tmp_path: Path):
    _write_check(tmp_path)
    g = _graph(_panel())
    row = UG.attach_event_weights(g, None, tmp_path)
    assert row["validated_cells"] == 3, row
    f5 = _f5(g)
    assert f5 and f5[0].expected_direction == -1 and f5[0].confidence_label == "HIGH"
    assert "SURVIVED" in f5[0].why


def test_a_validated_column_without_a_receipt_loads_unvalidated(tmp_path: Path):
    ev = tmp_path / "event_response"
    ev.mkdir(parents=True)
    w = _weights()
    w["validated"] = True
    w["validated_by"] = "event_check_forged"
    w.to_parquet(ev / "event_check_20210601T000000Z_weights.parquet", index=False)
    g = _graph(_panel())
    row = UG.attach_event_weights(g, None, tmp_path)
    assert row["validated_cells"] == 0
    imps = UG.propagate(g, EV)
    assert imps and all(i.confidence_label == "LOW" for i in imps)
    assert not any("SURVIVED" in i.why for i in imps)


def test_a_validated_column_is_ignored_even_when_a_receipt_exists(tmp_path: Path):
    # the receipt says nothing survived; the file says everything did
    _write_check(tmp_path, p=0.5)
    wp = next((tmp_path / "event_response").glob("*_weights.parquet"))
    w = pd.read_parquet(wp)
    w["validated"] = True
    w.to_parquet(wp, index=False)                       # also breaks the hash
    g = _graph(_panel())
    assert UG.attach_event_weights(g, None, tmp_path)["validated_cells"] == 0
    assert all(i.confidence_label == "LOW" for i in UG.propagate(g, EV))


def test_weights_edited_after_the_receipt_do_not_validate(tmp_path: Path):
    _write_check(tmp_path)
    wp = next((tmp_path / "event_response").glob("*_weights.parquet"))
    w = pd.read_parquet(wp)
    w["w"] = -0.9                                       # a bigger number, same cells
    w.to_parquet(wp, index=False)
    g = _graph(_panel())
    row = UG.attach_event_weights(g, None, tmp_path)
    assert row["validated_cells"] == 0
    assert "sha256" in json.dumps(row["validation"])


def test_an_in_memory_validated_column_is_not_a_validation():
    g = _graph(_panel())
    w = _weights()
    w["validated"] = True
    g.event_weights = w
    assert all(i.confidence_label == "LOW" and i.expected_size is None
               for i in UG.propagate(g, EV))


def test_a_receipt_from_a_different_grid_does_not_validate(tmp_path: Path, monkeypatch):
    _write_check(tmp_path)
    monkeypatch.setattr(config, "UNIVERSE_GRAPH_EVENT_HORIZONS", (1, 5, 21, 63))
    g = _graph(_panel())
    row = UG.attach_event_weights(g, None, tmp_path)
    assert row["validated_cells"] == 0 and "grid" in json.dumps(row["validation"])


def test_the_graph_round_trip_re_derives_validation_and_ignores_the_copy(tmp_path: Path):
    _write_check(tmp_path)
    g = _graph(_panel())
    UG.attach_event_weights(g, None, tmp_path)
    rec = {"build_id": "ug_v", "as_of": g.as_of, "built_utc": "2021-06-01T00:00:00+00:00",
           "params": __import__("dataclasses").asdict(g.params), "counts": g.counts()}
    UG.write_graph(g, tmp_path, rec)
    g2 = UG.load_graph(tmp_path)
    assert [i.to_dict() for i in UG.propagate(g2, EV)] == [i.to_dict() for i in UG.propagate(g, EV)]
    assert _f5(g2)[0].confidence_label == "HIGH"
    # the graph's own copy of the weights is not a validation: edit it and it is LOW
    cp = tmp_path / "ug_v" / "event_weights.parquet"
    w = pd.read_parquet(cp)
    assert "validated" not in w.columns, "the persisted copy carries no flag"
    w["w"] = -0.9
    w["validated"] = True
    w.to_parquet(cp, index=False)
    g3 = UG.load_graph(tmp_path)
    assert all(i.confidence_label == "LOW" and i.expected_size is None
               for i in UG.propagate(g3, EV))


# ─────────────────────────── B2 ─────────────────────────────────────────────

def test_unvalidated_cells_are_context_only_no_direction_no_size(tmp_path: Path):
    _write_check(tmp_path, p=0.5)                       # measured, did NOT survive
    g = _graph(_panel())
    UG.attach_event_weights(g, None, tmp_path)
    imps = UG.propagate(g, EV)
    assert {"company:FOLLOW", "company:OTH1"} <= {i.target for i in imps}
    for i in imps:
        assert i.expected_direction == 0 and i.expected_size is None and i.weight is None, i
        assert i.confidence_label == "LOW"
        assert "w=" in i.why and "n=400" in i.why and "NOT validated" in i.why
    held = UG.holdings_exposure(g, ["FOLLOW"], [EV])
    assert held and all(r["expected_direction"] == 0 and r["expected_size"] is None for r in held)
    assert UG.funnel_candidates(g, [EV], horizon=5, min_label="LOW") == []
    assert UG.owner_warnings(g, ["FOLLOW"], [EV], min_label="LOW") == []


# ─────────────────────────── B3 ─────────────────────────────────────────────

def test_the_bh_denominator_is_the_full_registered_grid():
    # one family's 30 cells: p = 0.003 passes BH over 30 (q 0.09) but not over the grid
    cells = [_cell(edge="sector", h=1, p=0.003)] + [
        _cell(edge="theme", h=5, p=0.9) for _ in range(29)]
    small = UG.screen_cells([dict(c) for c in cells], 0.10)
    assert small[0]["survives"], "the mechanism: a 30-cell family is easy"
    full = UG.screen_cells([dict(c) for c in cells], 0.10,
                           m_total=len(UG.registered_grid()["tradable_cells"]))
    assert not full[0]["survives"] and full[0]["q_bh"] > 0.10


def test_the_registry_is_persisted_and_the_denominator_never_shrinks(tmp_path: Path, monkeypatch):
    ev = tmp_path / "event_response"
    n_full = len(UG.registered_grid()["tradable_cells"])
    assert n_full == len(UG.EVENT_FAMILIES) * 2 * len(UG.EVENT_EDGE_TYPES) * len(
        config.UNIVERSE_GRAPH_EVENT_HORIZONS)
    UG.register_grid(ev)
    assert (ev / UG.GRID_REGISTRY_FILE).exists()
    assert UG.registered_cell_counts(ev)["tradable"] == n_full
    # a later config that registers a SMALLER grid cannot shrink the count
    monkeypatch.setattr(UG, "EVENT_FAMILIES", UG.EVENT_FAMILIES[:2])
    UG.register_grid(ev)
    assert UG.registered_cell_counts(ev)["tradable"] == n_full
    assert len((ev / UG.GRID_REGISTRY_FILE).read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.parametrize("partial", [
    {"families": ["8k_results"]},
    {"years": [2024, 2025]},
    {"horizons": [1]},
    {"top_n": 300},
])
def test_a_partial_run_never_validates_a_cell(tmp_path: Path, partial):
    _write_check(tmp_path, grid={**_full_grid(), **partial})
    rc = json.loads(next((tmp_path / "event_response").glob("event_check_*Z.json"))
                    .read_text(encoding="utf-8"))
    assert rc["grid"]["complete"] is False
    assert rc["grid"]["bh_denominator_tradable"] == len(UG.registered_grid()["tradable_cells"])
    g = _graph(_panel())
    assert UG.attach_event_weights(g, None, tmp_path)["validated_cells"] == 0
    assert all(i.expected_size is None for i in UG.propagate(g, EV))


def test_load_time_rescreen_uses_the_current_registry_not_the_receipts_survives(tmp_path):
    # a receipt whose cells say survives=True but whose p cannot survive the grid
    _write_check(tmp_path, p=0.004)
    rp = next((tmp_path / "event_response").glob("event_check_*Z.json"))
    rc = json.loads(rp.read_text(encoding="utf-8"))
    for c in rc["cells"]:
        c["survives"] = True                            # a hand edit of the flag
    rp.write_text(json.dumps(rc), encoding="utf-8")
    g = _graph(_panel())
    assert UG.attach_event_weights(g, None, tmp_path)["validated_cells"] == 0


# ─────────────────────────── the CLI path ───────────────────────────────────

def _fake_check(monkeypatch, seen: dict):
    monkeypatch.setattr(UG, "prepare_event_inputs", lambda *a, **k: {"receipt": {
        "panel": {}, "events_in_panel_dedup": 0, "event_inputs": []}})

    def _run(inp, **k):
        seen.update(k)
        cells = UG.screen_cells([_cell(h=h) for h in (1, 5, 21)], 0.10, m_total=k["m_total"])
        for c in cells:
            c.update({"hit_graph": 0.6, "hit_ctrl_liquid": 0.5, "mean_signed_ret_bps": 20.0,
                      "t_vs_liquid": 9.0})
        return {"cells": cells, "weights": _weights(), "families": {}, "n_cells": 3,
                "n_cells_same_session": 0, "n_survivors": sum(c["survives"] for c in cells),
                "n_same_session_transfer": 0}
    monkeypatch.setattr(UG, "run_event_check", _run)


@pytest.mark.parametrize("families,complete", [(None, True), (["8k_results"], False)])
def test_event_check_cli_corrects_against_the_registry_and_marks_partial_runs(
        tmp_path: Path, monkeypatch, families, complete):
    seen: dict = {}
    _fake_check(monkeypatch, seen)
    ev = tmp_path / "event_response"
    argv = ["event-check", "--out", str(ev)] + (["--families", *families] if families else [])
    assert UG.main(argv) == 0
    assert seen["m_total"] == len(UG.registered_grid()["tradable_cells"])
    assert (ev / UG.GRID_REGISTRY_FILE).exists()
    rc = json.loads(next(ev.glob("event_check_*Z.json")).read_text(encoding="utf-8"))
    assert rc["grid"]["complete"] is complete
    w = pd.read_parquet(next(ev.glob("*_weights.parquet")))
    assert "validated" not in w.columns
    g = _graph(_panel(), as_of="2099-01-01")        # the CLI dates its weights today
    assert UG.attach_event_weights(g, None, tmp_path)["validated_cells"] == (3 if complete else 0)
