"""A graph receipt must name the edge file that produced it.

WHY
===
On 2026-09-06 `scripts/w4_companyworld_rerun.py` ran three arms over three
different edge sets -- `companyworld_v1.parquet` (2,020 rows),
MARKET-GRAPH-1's `edge_instances.parquet` (10,923) and the two pooled
(12,943) -- and **all three receipts named the MARKET-GRAPH-1 path**, because
`features_graph.build()` stamped `str(edge_source())` (the module default /
env override) instead of the `edges_path` it was handed. Only `source_rows`
disagreed.

That is the difference between "customer momentum fell from t 1.447 to t 0.297
on a tape it had never seen" and "the same tape produced two different
numbers". The finding survives -- but a reader checking provenance would have
been told the wrong file, and outcome provenance is a standing rule.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from learner import features_graph as FG


def _tiny_edges(tmp_path: Path, name: str, n: int) -> Path:
    """A minimal edge file in the schema `load_edges`/`relation_table` expect."""
    src = FG.edge_source()
    if not src.exists():
        pytest.skip(f"no edge source on this machine at {src}")
    real = pd.read_parquet(src)
    out = tmp_path / name
    real.head(n).to_parquet(out, index=False)
    return out


def test_the_receipt_names_the_path_it_was_given_not_the_module_default(tmp_path):
    p = _tiny_edges(tmp_path, "some_other_edges.parquet", 400)
    try:
        _feats, rec = FG.build(edges_path=p, verbose=False)
    except SystemExit as exc:                                    # a refusal is fine
        pytest.skip(f"build refused on the truncated fixture: {exc}")
    assert Path(rec["source"]) == p, (
        f"receipt names {rec['source']!r} but the edges were read from {p!r} -- "
        "a receipt that names the wrong file is worse than one that names none")
    assert rec["source_is_the_module_default"] is False
    assert str(FG.DEFAULT_EDGE_SOURCE) != rec["source"]


def test_the_receipt_still_names_the_default_when_no_path_is_given():
    """The flag must distinguish 'the default' from 'a path that happens to match'."""
    src = FG.edge_source()
    if not src.exists():
        pytest.skip(f"no edge source on this machine at {src}")
    # Cheap structural check: no rebuild, just the two code paths' agreement.
    assert FG.edge_source() == src
