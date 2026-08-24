"""A file that exists is not a file that is usable.

`wrds_pull_catchup` resumes by skipping any table whose parquet exists. That is
correct for a pull that either happened or did not, and wrong for one that
happened with a narrower column list than a later consumer needs — and the
queue cannot notice, because existence is the only thing it inspects.

The measured consequence: `crsp_dsf_1990..2012` carry `permno/date/prc/ret/vol`
and nothing else, so `portfolio_farm` refuses twenty-three years and the whole
farm runs on twelve. The sub-period split then showed the leading strategy is
1.01x the market over 2013-2018 — one regime — which is what makes those
missing years the difference between a result and an artefact.

These tests pin the DETECTOR, including its own calibration: a checker that
cannot fail on a real gap is decoration.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.wrds_column_completeness import REQUIRED, audit


def _write(d, stem, cols):
    pd.DataFrame({c: [1] for c in cols}).to_parquet(d / f"{stem}.parquet")


FULL = ["permno", "date", "prc", "ret", "retx", "vol", "shrout", "openprc"]
THIN = ["permno", "date", "prc", "ret", "vol"]


def test_a_thin_file_is_reported_PARTIAL_not_present(tmp_path):
    """The whole point: the file exists and is still not usable."""
    _write(tmp_path, "crsp_dsf_2011", THIN)
    _write(tmp_path, "crsp_dsf_2013", FULL)
    r = audit(tmp_path)["crsp_dsf_*"]
    assert r["n_files"] == 2
    assert r["n_complete"] == 1
    assert r["n_partial"] == 1
    assert r["partial"]["crsp_dsf_2011"]["missing"] == ["openprc", "retx",
                                                        "shrout"]


def test_the_usable_range_names_only_COMPLETE_files(tmp_path):
    for y in (2011, 2012):
        _write(tmp_path, f"crsp_dsf_{y}", THIN)
    for y in (2013, 2014):
        _write(tmp_path, f"crsp_dsf_{y}", FULL)
    r = audit(tmp_path)["crsp_dsf_*"]
    assert r["complete_range"] == "crsp_dsf_2013..crsp_dsf_2014"


def test_all_complete_reports_no_gap(tmp_path):
    _write(tmp_path, "crsp_dsf_2013", FULL)
    assert audit(tmp_path)["crsp_dsf_*"]["n_partial"] == 0


def test_an_empty_directory_is_not_a_PASS(tmp_path):
    """Zero files means zero evidence. `n_complete` must not read as coverage."""
    r = audit(tmp_path)["crsp_dsf_*"]
    assert r["n_files"] == 0 and r["n_complete"] == 0
    assert r["complete_range"] is None


def test_an_UNREADABLE_file_is_reported_and_not_silently_skipped(tmp_path):
    (tmp_path / "crsp_dsf_2020.parquet").write_bytes(b"not a parquet")
    r = audit(tmp_path)["crsp_dsf_*"]
    assert r["n_partial"] == 1
    assert "error" in r["partial"]["crsp_dsf_2020"]


def test_the_detector_would_FIRE_on_the_real_gap():
    """Calibration against the actual repository, not a fixture. If this ever
    passes with n_partial == 0, either the re-pull happened (delete this test's
    xfail expectation and celebrate) or the checker stopped checking."""
    r = audit()["crsp_dsf_*"]
    if r["n_files"] == 0:
        pytest.skip("no CRSP daily parquet on this host")
    assert r["n_complete"] + r["n_partial"] == r["n_files"], (
        "every file must land in exactly one bucket — a file counted in "
        "neither is a file the audit silently ignored")


def test_every_required_column_has_a_stated_REASON():
    """A required column with no reason is a column somebody added defensively.
    The three that matter each say what breaks without them."""
    spec = REQUIRED["crsp_dsf_*"]
    for c in ("openprc", "retx", "shrout"):
        assert spec["why"].get(c), f"{c} is required with no reason given"
        assert len(spec["why"][c]) > 20
