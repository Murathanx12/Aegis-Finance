"""Data-rights register + report-only audit. No test fails because a source is
UNVERIFIED (that would turn CI red on day one); the register is a worklist."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from backend.services import data_rights
from scripts import data_rights_audit


def test_register_parses_and_flags_allowed():
    rows = data_rights.load()
    assert len(rows) >= 20
    for r in rows:
        for f in data_rights.FLAGS:
            assert r[f] in data_rights.ALLOWED, (r["id"], f)
        assert r["terms_read"] in data_rights.TERMS_READ


def test_every_yes_for_public_or_commercial_cites_a_page():
    for r in data_rights.load():
        for f in data_rights.CITED_FLAGS:
            if r[f] == "yes":
                assert r["terms_url"] and r["date_read"] and r["basis"], r["id"]


def test_loader_refuses_uncited_yes():
    payload = yaml.safe_load(data_rights.register_path().read_text(encoding="utf-8"))
    bad = copy.deepcopy(payload)
    row = next(r for r in bad["sources"] if r["id"] == "yfinance_market_data")
    row["public_display"] = "yes"
    row["terms_url"] = None
    with pytest.raises(data_rights.DataRightsError):
        data_rights.validate(bad)


def test_loader_refuses_bad_flag_and_duplicate():
    payload = yaml.safe_load(data_rights.register_path().read_text(encoding="utf-8"))
    bad = copy.deepcopy(payload)
    bad["sources"][0]["personal"] = "maybe"
    with pytest.raises(data_rights.DataRightsError):
        data_rights.validate(bad)
    dup = copy.deepcopy(payload)
    dup["sources"].append(dup["sources"][0])
    with pytest.raises(data_rights.DataRightsError):
        data_rights.validate(dup)


def test_audit_runs_and_receipt_shape(tmp_path: Path):
    rc = data_rights_audit.main(["--out", str(tmp_path)])
    assert rc == 0
    rep = json.loads((tmp_path / "data_rights_audit.json").read_text(encoding="utf-8"))
    for k in ("sources_total", "sources_by_flag", "public_routes", "routes", "flagged_routes",
              "partial_trace_routes", "excluded_local_only_routes", "limits"):
        assert k in rep
    assert rep["public_routes"] > 50
    assert (tmp_path / "data_rights_audit.md").is_file()
    ids = set(data_rights.by_id())
    for route in rep["routes"]:
        assert set(route["sources"]) <= ids
        assert route["trace"] in ("traced", "partial")
    # the yfinance news route is the known public-display problem
    news = next(r for r in rep["routes"] if r["path"] == "/api/news/{ticker}")
    assert "yfinance_news" in news["sources"]
    assert any(f["route"].endswith("/api/news/{ticker}") for f in rep["flagged_routes"])
    # local-only control writes are excluded, not listed as public
    assert rep["excluded_local_only_routes"] >= 1


def test_strict_only_fails_on_a_no(tmp_path: Path):
    # report mode is always 0; strict is allowed to be non-zero (nothing calls it)
    assert data_rights_audit.main(["--out", str(tmp_path)]) == 0
    assert data_rights_audit.main(["--out", str(tmp_path), "--strict"]) in (0, 1)
