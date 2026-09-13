"""T3 — the surviving G3 lineage, frozen, and the probe that stopped its deploy.

What is pinned here is not the arithmetic (there is none) but the discipline:

  1. the rule is READ from the receipts, never re-derived. The evolutionary
     search does not run again — a re-run is a NEW search with a new
     multiplicity budget and the deflated Sharpe that licensed this lineage
     would no longer apply to its result;
  2. the export REFUSES when the receipts stop saying what it was written
     against: no ACTIVE lineage, several ACTIVE lineages, a representative the
     evaluation log does not carry, or a genome whose feature list the probe
     does not classify. A probe over a feature list nobody checked is a probe
     of the wrong rule;
  3. the probe's verdict is NOT EXECUTABLE and it NAMES the missing inputs.
     A "cannot" with no named cause is the shape of an excuse.

Every fixture here is synthetic; the real receipts are read only by the one
test that reads the real ones, and it asserts the row rather than a number
computed from it.
"""

from __future__ import annotations

import json

import pytest

from scripts import night_g3_lineage_export as GX


def _verdict_row(**over):
    row = {"lineage": GX.LINEAGE, "representative_key": GX.REPRESENTATIVE,
           "verdict": "ACTIVE", "reason": "DSR 1.000 > 0.95 bar",
           "observed_sharpe": 6.273508, "expected_maximum_sharpe": 3.152785,
           "dsr": 1.0, "dsr_bar": 0.95, "n_observations": 342,
           "banks_met": 342, "n_windows_measured": 8208,
           "n_trials_raw": 595, "n_trials_effective_proxy": 251,
           "n_trials_effective_onc": None, "n_trials_effective_onc_gap": "…",
           "pbo": None, "pbo_status": "insufficient_windows"}
    row.update(over)
    return row


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the refusals


def test_no_active_lineage_refuses(tmp_path):
    p = _write_jsonl(tmp_path / "v.jsonl", [_verdict_row(verdict="CANNOT_DETERMINE")])
    with pytest.raises(GX.LineageUnavailable, match="0 lineage"):
        GX.active_lineage(path=p)


def test_two_active_lineages_refuse_rather_than_taking_the_first(tmp_path):
    p = _write_jsonl(tmp_path / "v.jsonl",
                     [_verdict_row(), _verdict_row(lineage="deadbeef")])
    with pytest.raises(GX.LineageUnavailable, match=r"not 1"):
        GX.active_lineage(path=p)


def test_a_missing_receipt_names_the_file_and_says_the_search_never_reruns(tmp_path):
    with pytest.raises(GX.LineageUnavailable, match="does not re-run the search"):
        GX.active_lineage(path=tmp_path / "absent.jsonl")


def test_a_representative_the_evaluation_log_lacks_refuses(tmp_path):
    p = _write_jsonl(tmp_path / "e.jsonl", [{"key": "other", "genome": {}}])
    with pytest.raises(GX.LineageUnavailable, match="different runs"):
        GX.genome_for(GX.REPRESENTATIVE, path=p)


# --------------------------------------------------------------------------
# the probe


def test_the_probe_names_what_is_missing_and_refuses_to_call_partial_usable():
    p = GX.probe()
    assert p["executable_in_the_terminal_repo"] is False
    assert p["n_features"] == 14
    assert set(p["missing"]) == {
        "log_market_cap__xs", "disagreement__xs", "dispersion__xs",
        "net_rev_4w__xs", "target_rev_1m__xs", "consensus_rev_1m__xs"}
    # a near-substitute from another vendor is NOT a yes
    assert set(p["partial_and_therefore_not_usable"]) == {"ratio__xs", "coverage__xs"}
    assert p["verdict"].startswith("NOT EXECUTABLE")
    for f in p["missing"]:
        assert f in p["verdict"], "a 'cannot' with no named cause is an excuse"
    assert "CROSS-SECTIONAL z-score" in p["cross_section_objection"]
    assert "engine-file pattern" in p["what_would_change_it"]


def test_the_probe_says_EXECUTABLE_only_when_every_feature_is_a_yes():
    ok = {"a__xs": {"terminal": "yes", "builder": "x", "why": "y"},
          "b__xs": {"terminal": "yes", "builder": "x", "why": "y"}}
    assert GX.probe(ok)["executable_in_the_terminal_repo"] is True
    assert GX.probe(ok)["verdict"] == "EXECUTABLE"
    half = {**ok, "c__xs": {"terminal": "partial", "builder": "x", "why": "y"}}
    assert GX.probe(half)["executable_in_the_terminal_repo"] is False


def test_every_classified_feature_carries_a_reason_and_a_builder():
    for f, meta in GX.FEATURE_SOURCES.items():
        assert meta["terminal"] in ("yes", "partial", "no"), f
        assert meta["builder"] and meta["why"], f
        assert f.endswith("__xs"), f


# --------------------------------------------------------------------------
# the real receipts, read as rows


def test_the_real_receipts_still_name_the_lineage_this_job_was_written_against():
    v = GX.active_lineage()
    assert v["lineage"] == GX.LINEAGE
    assert v["representative_key"] == GX.REPRESENTATIVE
    assert v["dsr"] > v["dsr_bar"]
    assert v["observed_sharpe"] > v["expected_maximum_sharpe"]
    assert v["n_trials_raw"] == 595 and v["n_trials_effective_proxy"] == 251
    # PBO could not run, and that is reported rather than scored as a pass
    assert v["pbo"] is None and v["pbo_status"] == "insufficient_windows"



#: 2026-09-13: `export()` reads the night search's own evaluation log, which is
#: gitignored DATA -- absent on every fresh checkout (CI went red on it). The
#: receipt-reading tests skip by name there; the synthetic ones above still run.
_REAL_LOG_PRESENT = (GX.run_dir() / GX.EVALUATIONS).exists()
_needs_real_log = pytest.mark.skipif(not _REAL_LOG_PRESENT, reason="the night search's evaluation log is gitignored data and is absent here")

@_needs_real_log
def test_the_exported_rule_is_the_genome_the_receipt_names(tmp_path):
    r = GX.export(out_dir=tmp_path)
    p = json.loads((tmp_path / f"G3_lineage_{GX.LINEAGE}.json").read_text(encoding="utf-8"))
    assert p == r["payload"]
    rule = p["rule"]
    assert set(rule["weights"]) == set(GX.FEATURE_SOURCES)
    assert rule["k"] == 20 and rule["weighting"] == "ew" and rule["hold_mult"] == 8
    assert rule["hold_k"] == 160
    assert "new multiplicity budget" in rule["search_never_re_runs"]
    assert p["dsr_receipt"]["verdict"] == "ACTIVE"
    assert p["trials"]["n_trials_raw"] == 595
    # the DEV-only status and the search's two standing defects travel with it
    assert p["dev_only"]["corrected_verdict_of_the_search"] == "CONDITIONAL"
    assert len(p["dev_only"]["two_standing_defects"]) == 2
    assert "NOT READ" in p["dev_only"]["holdout"]
    assert p["terminal_repo_probe"]["executable_in_the_terminal_repo"] is False


@_needs_real_log
def test_the_job_receipt_states_the_consequence_for_hack4(tmp_path, monkeypatch):
    monkeypatch.setattr(GX, "engines_dir", lambda: tmp_path)
    out = GX.G3_lineage_export()
    assert out["executable_in_the_terminal_repo"] is False
    assert out["stage"] == "weights"
    assert "hack4 keeps its current mandate" in out["verdict"]
    assert "drawdown cut" in out["verdict"]
    assert out["llm_spend_usd"] == 0.0
