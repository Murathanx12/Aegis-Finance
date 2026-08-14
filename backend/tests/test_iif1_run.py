"""INTERNET-INVESTIGATOR-FWD-1 — the entrypoint.

`run_night()` had twenty-four tests and no caller. These pin the thing that
turned it into something that can actually be run, and in particular pin the
three modes apart: only one of them can spend, and the other two must not be
able to reach the evidence ledger by forgetting a keyword.

Offline: the feature layer is monkeypatched, the model is the shipped stub.
"""

from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from backend.services import iif1_features as F
from backend.services import iif1_run as R
from backend.services import investigator_night as N


@pytest.fixture(autouse=True)
def _isolated_snapshots(monkeypatch):
    d = pathlib.Path(tempfile.mkdtemp())
    monkeypatch.setattr(F, "SNAPSHOT_DIR", d)
    monkeypatch.setattr(N, "SANDBOX_RECEIPTS_DIR", d / "receipts")
    monkeypatch.setattr(N, "_spend_since", lambda s: (0.0, 0))
    return d


@pytest.fixture(autouse=True)
def _fake_features(monkeypatch):
    """Six measured features per name, no network."""
    def vals(t, ts):
        f = lambda v, s=F.OK_DATA: F.FeatureValue(v, s, "test", ts.isoformat(),
                                                  "now")
        return {"price": f(100.0), "dollar_volume_20d": f(1e9),
                "volume_z_20d": f(1.5), "abs_resid_return_z_1d": f(2.5),
                "earnings_within_5d": f(False, F.OK_EMPTY),
                "filing_within_2d": f(False, F.OK_EMPTY)}
    monkeypatch.setattr(F, "assemble_ticker", vals)


# ── the stub model is deterministic and never leaves the process ────────────

def test_the_stub_answers_every_microtask_with_a_valid_shape():
    from backend.services.investigator_agent import FORECAST_CELLS
    fc = json.loads(R.stub_llm(system="... MAGNITUDE ...", user="u").text)
    assert len(fc["forecasts"]) == len(FORECAST_CELLS)
    for f in fc["forecasts"]:
        assert set(f) >= {"observable", "horizon_days", "threshold",
                          "prior", "posterior"}
    assert "what_changed" in json.loads(
        R.stub_llm(system="Extract what changed", user="u").text)
    assert "strongest_objection" in json.loads(
        R.stub_llm(system="strongest_objection", user="u").text)


def test_the_stub_leaves_belief_unchanged_so_a_rehearsal_claims_nothing():
    """A rehearsal that invented belief changes would put fake signal into any
    receipt someone later mistook for a real night."""
    fc = json.loads(R.stub_llm(system="MAGNITUDE", user="u").text)
    assert all(f["prior"] == f["posterior"] for f in fc["forecasts"])


# ── the three modes ────────────────────────────────────────────────────────

def test_assemble_only_freezes_the_inputs_and_spends_nothing(capsys):
    rc = R.main(["--assemble-only", "--as-of", "2026-08-14 21:00",
                 "--universe", "AAA,BBB,CCC"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "inputs frozen" in out
    assert "nothing was spent" in out
    assert F.snapshot_path(F.resolve_decision_ts("2026-08-14 21:00")).exists()


def test_a_rehearsal_runs_end_to_end_and_writes_no_evidence(capsys, monkeypatch):
    wrote = []
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: wrote.extend(recs))
    rc = R.main(["--rehearse", "--as-of", "2026-08-14 21:00",
                 "--universe", "AAA,BBB,CCC"])
    out = capsys.readouterr().out
    assert rc == 0
    assert wrote == [], "a rehearsal reached the evidence ledger"
    assert "sandbox: nothing reached the evidence ledger" in out
    assert "status        ok" in out
    assert "pairing" in out


def test_the_rehearsal_prints_the_four_required_funding_numbers(capsys):
    R.main(["--rehearse", "--as-of", "2026-08-14 21:00", "--universe", "AAA,BBB"])
    out = capsys.readouterr().out
    for k in ("measured_cost_night_1", "projected_40_night_cost",
              "current_balance", "funding_gap_or_surplus"):
        assert k in out
    assert "the planning number" in out
    assert "a stop, not a plan" in out


def test_a_rehearsal_reports_cost_unknown_rather_than_free(capsys):
    """It made no vendor call, so its cost is not $0.00/night — it is unmeasured.
    Printing zero here would project a free 40-night trial."""
    R.main(["--rehearse", "--as-of", "2026-08-14 21:00", "--universe", "AAA,BBB"])
    out = capsys.readouterr().out
    assert "measured_cost_night_1     None (unknown)" in out
    assert "projected_40_night_cost   None" in out


def test_the_snapshot_is_frozen_before_any_reasoning_happens(capsys):
    """Assembling inside the run would make the inputs a side effect of it, so a
    crash halfway would leave a night whose inputs no longer exist."""
    R.main(["--rehearse", "--as-of", "2026-08-14 21:00", "--universe", "AAA"])
    out = capsys.readouterr().out
    assert out.index("snapshot ") < out.index("REHEARSAL")


def test_rerunning_a_night_refuses_to_rebuild_its_snapshot():
    args = ["--assemble-only", "--as-of", "2026-08-14 21:00",
            "--universe", "AAA,BBB"]
    assert R.main(args) == 0
    with pytest.raises(FileExistsError, match="point-in-time record"):
        R.main(args)
    assert R.main(args + ["--overwrite-snapshot"]) == 0


def test_reuse_snapshot_reads_the_frozen_inputs_rather_than_refetching(capsys):
    R.main(["--assemble-only", "--as-of", "2026-08-14 21:00",
            "--universe", "AAA,BBB"])
    capsys.readouterr()
    rc = R.main(["--rehearse", "--reuse-snapshot", "--as-of", "2026-08-14 21:00"])
    out = capsys.readouterr().out
    assert rc == 0 and "reusing frozen snapshot" in out


def test_being_short_of_k_is_announced_not_padded(capsys):
    R.main(["--assemble-only", "--as-of", "2026-08-14 21:00",
            "--universe", "AAA,BBB"])
    out = capsys.readouterr().out
    assert "SHORT OF K" in out


def test_the_report_survives_a_console_that_cannot_encode_box_characters(
        capsys, monkeypatch):
    """Found in the very first rehearsal: the Windows console is cp1252 and the
    crash landed AFTER the night ran — so a production night would have spent
    the money, written the receipt, and then died printing it."""
    rc = R.main(["--rehearse", "--as-of", "2026-08-14 21:00", "--universe", "AAA"])
    assert rc == 0
    assert "funding" in capsys.readouterr().out
