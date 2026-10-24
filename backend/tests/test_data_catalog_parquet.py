"""Parquet footer date selection is reproducible, not a PIT availability claim."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.services import data_catalog as DC


def test_date_column_ties_are_stable_across_hash_seeds_and_schema_order(tmp_path):
    now = datetime.now(timezone.utc)
    columns = {
        "first_bar": pa.array([now - timedelta(days=9), now - timedelta(days=8)]),
        "asof_session": pa.array([now - timedelta(days=3), now - timedelta(days=2)]),
    }
    paths = [tmp_path / "forward.parquet", tmp_path / "reversed.parquet"]
    pq.write_table(pa.table(columns), paths[0])
    pq.write_table(pa.table(dict(reversed(list(columns.items())))), paths[1])
    expected = {
        "column": "asof_session", "min": (now - timedelta(days=3)).date().isoformat(),
        "max": (now - timedelta(days=2)).date().isoformat(),
        "method": "parquet column statistics",
    }
    code = (
        "import json, sys; from pathlib import Path; "
        "from backend.services.data_catalog import inspect_parquet; "
        "print(json.dumps([inspect_parquet(Path(p))['date_range'] for p in sys.argv[1:]]))"
    )
    for seed in (0, 1, 2, 3, 7, 17, 42, 123):
        result = subprocess.run(
            [sys.executable, "-B", "-c", code, *(str(p) for p in paths)],
            cwd=DC.REPO,
            env={**os.environ, "PYTHONHASHSEED": str(seed), "AEGIS_IGNORE_DOTENV": "1"},
            capture_output=True, text=True, check=True, timeout=30,
        )
        ranges = json.loads(result.stdout)
        assert ranges[0] == ranges[1], f"PYTHONHASHSEED={seed}"
        assert {k: ranges[0][k] for k in expected} == expected, f"PYTHONHASHSEED={seed}"


@pytest.mark.parametrize("columns,expected", [
    # Temporal fields keep priority over even a recognised string date name.
    ([("date", "string"), ("first_bar", "temporal")], "first_bar"),
    # DATE_NAMES priority still beats alphabetical order among temporal fields.
    ([("asof", "temporal"), ("date", "temporal")], "date"),
    # Case variants with identical priority also have a total name ordering.
    ([("date", "temporal"), ("DATE", "temporal")], "DATE"),
])
def test_date_column_existing_priority_precedes_name_tie_break(tmp_path, columns, expected):
    now = datetime.now(timezone.utc)
    values = [now - timedelta(days=3), now - timedelta(days=2)]
    table = pa.table({name: pa.array([v.date().isoformat() for v in values]
                                   if kind == "string" else values)
                      for name, kind in columns})
    path = tmp_path / "priority.parquet"
    pq.write_table(table, path)
    assert DC.inspect_parquet(path)["date_range"]["column"] == expected
