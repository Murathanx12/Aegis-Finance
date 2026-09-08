"""X6 — no caller of `grade_by_era` refuses on a long panel.

WHAT HAPPENED. `learner/evaluate.ERAS` is hard-coded 2016-2018 / 2019-2021 /
2022-2024 — written for the 12-year panel and never revisited. Graded against
the 1999-2024 long panel it described the last nine years and said nothing
about the other seventeen; the B1 known-answer battery found it and filed it as
a finding rather than a miss (`labor_b1_known_answer_battery.py`, and the same
line is in the G7 build note).

The first repair made `grade_by_era` DERIVE its coverage or REFUSE. That was
right and it was not finished: **both remaining bare callers then refused**.
`scripts/learner_run.py` and `scripts/learner_v2_run.py` called
`E.grade_by_era(sub, col, horizon)` with no grid, so on the long panel they
wrote `{"_coverage": "REFUSED: ..."}` into a receipt and no era table at all. A
guard that converts a silently WRONG answer into a silently ABSENT one has
moved the problem one step.

So `evaluate.eras_covering(df)` picks the narrowest of the two grids this repo
owns — `ERAS`, else `long_eras()` — and refuses if neither covers the frame,
rather than inventing a third grid at a call site. This file pins:

  1. the helper returns `ERAS` on a short panel (sealed receipts reproduce);
  2. it returns `long_eras()` on the long panel and the table is FULL;
  3. every `grade_by_era` call outside `learner/evaluate.py` passes `eras=`;
  4. the known answer: bare, on the long panel, it really does refuse.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from learner import evaluate as E

REPO = Path(__file__).resolve().parents[2]


def _panel(lo: int, hi: int, names: int = 40, seed: int = 20260907) -> pd.DataFrame:
    """A minimal frame with the columns `grade_by_era` reads.

    Years are given explicitly, never derived from `today`: a fixture that
    encodes a calendar moment fails the day after that moment passes.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for year in range(lo, hi + 1):
        for month in range(1, 13):
            mkt = float(rng.normal(0.006, 0.04))
            for i in range(names):
                pred = float(rng.normal())
                rows.append({
                    "entry_date": pd.Timestamp(year=year, month=month, day=1),
                    "month": f"{year}-{month:02d}",
                    "permno": 10000 + i,
                    "pred": pred,
                    "fwd_1m": mkt + 0.02 * pred + float(rng.normal(0.0, 0.05)),
                    "mkt_vw_1m": mkt,
                    "market_cap": float(rng.lognormal(mean=7.0, sigma=1.2)) * 1e6,
                })
    df = pd.DataFrame(rows)
    df["excess_vw_1m"] = df["fwd_1m"] - df["mkt_vw_1m"]
    return df


# ------------------------------------------------------------- the helper

def test_short_panel_keeps_the_module_grid_so_sealed_receipts_reproduce():
    df = _panel(2016, 2024)
    assert E.eras_covering(df) == dict(E.ERAS)


def test_long_panel_gets_the_long_grid():
    df = _panel(1999, 2024)
    assert E.eras_covering(df) == E.long_eras()


def test_the_helper_is_exported():
    assert "eras_covering" in E.__all__


def test_neither_grid_covering_is_a_refusal_not_a_third_grid():
    df = _panel(1980, 1985)
    with pytest.raises(SystemExit) as exc:
        E.eras_covering(df)
    assert "no canonical era grid covers this frame" in str(exc.value)


# --------------------------------------------- the tables the callers get

def test_the_derived_grid_produces_a_full_table_on_the_long_panel():
    df = _panel(1999, 2024, names=25)
    out = E.grade_by_era(df, "pred", 1, eras=E.eras_covering(df))
    assert not out["_coverage"]["verdict"].startswith("REFUSED")
    assert out["_coverage"]["rows_outside_every_era"] == 0
    assert set(out) == {"_coverage"} | set(E.long_eras())


def test_the_known_answer_bare_really_does_refuse_on_the_long_panel():
    """The defect, reproduced. Without a grid the long panel gets no table."""
    df = _panel(1999, 2024, names=25)
    bare = E.grade_by_era(df, "pred", 1)
    assert bare["_coverage"]["verdict"].startswith("REFUSED")
    assert set(bare) == {"_coverage"}, (
        "bare, the long panel gets a refusal and NO era buckets -- which is "
        "exactly why every caller must derive its grid")


# ------------------------------------------------------------- the callers

_OWNER = "learner/evaluate.py"
_SCAN = ("scripts", "learner", "backend", "lab", "engine")
_SKIP = {"tests", "__pycache__", ".venv", "venv", "node_modules", "site-packages"}


def _grade_by_era_calls() -> dict[str, bool]:
    """`"<relpath>:<line>" -> passes an explicit `eras=`."""
    out: dict[str, bool] = {}
    for d in _SCAN:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.py")):
            if _SKIP & set(p.parts):
                continue
            rel = p.relative_to(REPO).as_posix()
            if rel == _OWNER:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:                                # noqa: PERF203
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = (f.attr if isinstance(f, ast.Attribute)
                        else f.id if isinstance(f, ast.Name) else "")
                if name != "grade_by_era":
                    continue
                explicit = any(k.arg == "eras" for k in node.keywords)
                out[f"{rel}:{node.lineno}"] = explicit
    return out


def test_every_caller_passes_an_explicit_era_grid():
    calls = _grade_by_era_calls()
    assert calls, "no grade_by_era call site found -- the scanner is broken"
    bare = sorted(k for k, ok in calls.items() if not ok)
    assert not bare, (
        "these callers take the module default and therefore REFUSE on a long "
        f"panel; pass eras=E.eras_covering(df) or eras=E.long_eras(): {bare}")


def test_the_two_named_call_sites_are_among_them():
    """The roadmap names two; if either file is renamed this says so."""
    calls = _grade_by_era_calls()
    files = {k.split(":")[0] for k in calls}
    for named in ("scripts/learner_run.py", "scripts/learner_v2_run.py"):
        assert named in files, (
            f"{named} no longer calls grade_by_era -- X6's premise moved")
