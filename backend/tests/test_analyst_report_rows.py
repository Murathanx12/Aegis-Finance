"""analyst_report_rows: the contract an extracted analyst report must meet.

Synthetic fixture only (a fictional company and broker); licensed report
content never enters the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import analyst_report_rows as ARR
from scripts import analyst_report_rows as CLI

FIX = Path(__file__).parent / "fixtures" / "analyst_report" / "synthetic_report.json"


def _rep() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_the_synthetic_report_validates_and_code_computes_the_changes():
    rep, errs = ARR.validate_report(_rep())
    assert errs == []
    assert rep["ticker"] == "EXMP" and rep["rating"] == "buy" and rep["rating_raw"] == "Outperform"
    assert rep["target_change_pct"] == pytest.approx(20.0)
    assert rep["implied_upside_pct"] == pytest.approx(25.0)
    q2 = rep["eps_revisions"][0]
    assert q2["pct_change"] == pytest.approx(10.0) and q2["vs_consensus_pct"] == pytest.approx(7.8431, abs=1e-3)
    assert rep["warnings"] == []


def test_knowable_at_is_the_later_of_published_and_first_held():
    rep, _ = ARR.validate_report(_rep())
    assert rep["published_at"] == "2026-03-02" and rep["knowable_at"] == "2026-03-05"
    rows = ARR.to_rows(rep)
    assert all(r["knowable_at"] == "2026-03-05" for r in rows)
    assert ARR.visible_at(rows, "2026-03-05") == []           # strictly before
    assert len(ARR.visible_at(rows, "2026-03-06")) == len(rows)


def test_an_unknown_first_held_date_is_not_pit_safe_and_never_visible():
    r = _rep()
    r["first_held_at"] = None
    rep, errs = ARR.validate_report(r)
    assert errs == [] and rep["pit_safe"] is False
    assert ARR.visible_at(ARR.to_rows(rep), "2027-01-01") == []


def test_every_error_is_listed_and_nothing_is_repaired():
    r = _rep()
    r["ticker"] = ""
    r["published_at"] = "March 2"
    r["price_target"] = -5
    r["scenarios"][0]["name"] = "bull"
    r["falsifiers"] = [{"statement": "it fails", "observable": "", "by_date": None}]
    rep, errs = ARR.validate_report(r)
    assert rep is None
    joined = " | ".join(errs)
    for needle in ("missing ticker", "published_at", "price_target", "scenario 0",
                   "observable", "by_date"):
        assert needle in joined, needle


def test_a_report_without_a_falsifier_is_refused():
    r = _rep()
    r["falsifiers"] = []
    rep, errs = ARR.validate_report(r)
    assert rep is None and any("falsifier" in e for e in errs)


def test_unstated_probabilities_stay_none_and_inconsistency_is_a_warning():
    r = _rep()
    for s in r["scenarios"]:
        s["probability"] = None
    rep, errs = ARR.validate_report(r)
    assert errs == [] and all(s["probability"] is None for s in rep["scenarios"])
    r2 = _rep()
    r2["scenarios"][0]["probability"] = 0.5
    r2["eps_revisions"][0]["pct_change_stated"] = 25.0
    rep2, errs2 = ARR.validate_report(r2)
    assert errs2 == []
    assert any("sum to" in w for w in rep2["warnings"])
    assert any("stated 25.0%" in w for w in rep2["warnings"])


def test_ratings_map_or_stay_unknown():
    assert ARR.normalise_rating("Overweight") == "buy"
    assert ARR.normalise_rating("Neutral") == "hold"
    assert ARR.normalise_rating("Underperform") == "sell"
    assert ARR.normalise_rating("Top Pick (Asia)") == "unknown"


def test_rows_carry_kinds_ids_and_the_change_not_the_level():
    rep, _ = ARR.validate_report(_rep())
    rows = ARR.to_rows(rep)
    kinds = {r["kind"] for r in rows}
    assert kinds == set(ARR.ROW_KINDS)
    pt = next(r for r in rows if r["kind"] == "price_target")
    assert pt["rank_on"] == "change_pct" and pt["change_pct"] == pytest.approx(20.0)
    assert len({r["row_id"] for r in rows}) == len(rows)
    with pytest.raises(ARR.ReportInvalid):
        ARR.to_rows(_rep())                                     # unvalidated


def test_text_is_capped_so_a_row_is_a_pointer_not_a_copy():
    r = _rep()
    r["key_debates"] = [{"text": "x" * 5000, "page": 3}]
    rep, _ = ARR.validate_report(r)
    assert len(rep["key_debates"][0]["text"]) == ARR.MAX_TEXT


def test_append_is_idempotent(tmp_path):
    rep, _ = ARR.validate_report(_rep())
    rows = ARR.to_rows(rep)
    p = tmp_path / "rows.jsonl"
    assert ARR.append_rows(rows, p) == len(rows)
    assert ARR.append_rows(rows, p) == 0
    assert len(p.read_text(encoding="utf-8").splitlines()) == len(rows)


def test_cli_refuses_an_in_repo_path_outside_the_private_dir(tmp_path, capsys):
    import shutil
    import subprocess
    assert CLI.out_path_allowed(tmp_path / "rows.jsonl")
    assert not CLI.out_path_allowed(CLI.REPO / "docs" / "rows.jsonl")
    # CH-05 "U": backend/data/optimus is default-deny now, so an arbitrary file there IS
    # ignored (allowed); a keep-list path there is still addable, so it is still refused
    assert not CLI.out_path_allowed(CLI.REPO / "backend" / "data" / "optimus" / "ledger_manifests"
                                    / "rows.jsonl")
    if shutil.which("git") and (CLI.REPO / ".git").exists():
        assert CLI.out_path_allowed(CLI.PRIVATE_DIR / "x" / "rows.jsonl")
    # ANOTHER checkout (the runtime, a sibling worktree) is just as tracked
    if shutil.which("git"):
        other = tmp_path / "other_checkout"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        assert not CLI.out_path_allowed(other / "backend" / "x.jsonl")
        (other / ".gitignore").write_text("private/\n", encoding="utf-8")
        assert CLI.out_path_allowed(other / "private" / "x.jsonl")
    assert CLI.main(["validate", str(FIX), "--out", str(CLI.REPO / "docs" / "x.jsonl")]) == 2
    assert CLI.main(["validate", str(FIX), "--out", str(tmp_path / "ok.jsonl")]) == 0
    bad = tmp_path / "bad.json"
    r = _rep()
    r["falsifiers"] = []
    bad.write_text(json.dumps(r), encoding="utf-8")
    assert CLI.main(["validate", str(bad)]) == 2
    assert "INVALID" in capsys.readouterr().out


def test_the_private_dir_is_gitignored():
    gi = (CLI.REPO / ".gitignore").read_text(encoding="utf-8")
    assert "backend/data/optimus/analyst_reports/" in gi


def test_a_different_extraction_of_the_same_source_is_refused(tmp_path):
    rep, _ = ARR.validate_report(_rep())
    p = tmp_path / "rows.jsonl"
    ARR.append_rows(ARR.to_rows(rep), p)
    r2 = _rep()
    r2["first_held_at"] = "2026-03-09"           # a corrected, LATER knowable date
    rep2, _ = ARR.validate_report(r2)
    rows2 = ARR.to_rows(rep2)
    assert {r["row_id"] for r in rows2} == {r["row_id"] for r in ARR.to_rows(rep)}
    with pytest.raises(ARR.ReportInvalid):
        ARR.append_rows(rows2, p)


def test_garbage_is_an_error_not_a_nan():
    r = _rep()
    r["scenarios"][0]["assumptions"]["y3_op_margin_pct"] = "high"
    r["eps_revisions"][0]["pct_change_stated"] = "10%"
    r["rating"] = "x" * 2000
    r["key_debates"] = [{"text": "a debate", "page": "p" * 5000}]
    r["scenarios"].append(dict(r["scenarios"][1]))           # duplicate "base"
    r["published_at"] = "2026-03-02xyz"
    rep, errs = ARR.validate_report(r)
    joined = " | ".join(errs)
    assert rep is None
    for needle in ("is not a number", "pct_change_stated", "rating longer", "page must be",
                   "duplicate scenario", "published_at"):
        assert needle in joined, needle
