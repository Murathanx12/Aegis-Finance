"""The published-anomaly cadence: the refusals, the control, the decision rule.

The replay itself is the farm's, tested elsewhere. What is tested here is the
part a weekly cadence gets wrong: grading a primary before its plan is signed,
deciding on the eras that happened to load, and quoting one cost rate.
"""

from __future__ import annotations

import pytest

from scripts import night_anomaly_adjudicate as A


# ------------------------------------------------------------- the table

def test_the_eight_anomalies_are_declared_in_cadence_order_with_citations():
    assert [a["week"] for a in A.ANOMALIES] == list(range(1, 9))
    for row in A.ANOMALIES:
        assert row["citation"] and "(" in row["citation"], row["name"]
        assert row["published_direction"], row["name"]
        assert row["data_need"], row["name"]
    names = [a["name"] for a in A.ANOMALIES]
    assert len(set(names)) == 8
    # week 1 needs no data build -- that is why it is week 1
    assert A.anomaly_of(1)["name"] == "short_term_reversal"
    assert A.anomaly_of(1)["signal"] == "reversal_1m"


def test_a_week_with_no_factor_yet_says_so_by_name(tmp_path):
    """`NOT_RUNNABLE_YET` is a row in the cadence table, not a silent gap: a
    week that produced nothing and said nothing is a week nobody notices is
    missing."""
    out = A.A_published_anomaly(week=4, out_dir=tmp_path)
    assert out["available"] is False
    assert out["verdict"].startswith("NOT_RUNNABLE_YET")
    assert "fundamentals panel" in out["data_need"]


def test_the_engine_signal_named_by_a_week_actually_exists():
    """A cadence that names a signal the engine does not have fails on the
    night, three hours in, not here."""
    from backend.services.portfolio_farm.signals import SIGNALS
    for row in A.ANOMALIES:
        if row["signal"] is not None:
            assert row["signal"] in SIGNALS, row["name"]
    assert A.DRIFT_ONLY_CONTROL in SIGNALS


# ------------------------------------------------------------ the prereg

def test_the_primary_is_REFUSED_while_the_prereg_is_unsigned(tmp_path):
    state = A.prereg_state(A.anomaly_of(1))
    assert state["present"] is True
    out = A.A_published_anomaly(week=1, smoke=False, out_dir=tmp_path)
    if state["signed"]:                                   # pragma: no cover
        pytest.skip("the week-1 prereg has been signed; the refusal path is "
                    "no longer reachable from this fixture")
    assert out["available"] is False
    assert out["verdict"].startswith("REFUSED_PREREG_UNSIGNED")


def test_prereg_state_reads_the_FILE_and_not_a_flag(tmp_path, monkeypatch):
    """The pre-registration IS the commitment; a second place recording its
    status is a second place that can disagree with it."""
    monkeypatch.setattr(A, "TRIALS", tmp_path)
    (tmp_path / "P.md").write_text("# draft\nStatus: UNSIGNED\n", encoding="utf-8")
    assert A.prereg_state({"week": 1, "prereg": "P.md"})["signed"] is False
    (tmp_path / "P.md").write_text("# draft\nSIGNED-BY: Murat\n", encoding="utf-8")
    assert A.prereg_state({"week": 1, "prereg": "P.md"})["signed"] is True
    missing = A.prereg_state({"week": 1, "prereg": "NOPE.md"})
    assert missing["present"] is False and "not on this checkout" in missing["why"]
    none_at_all = A.prereg_state({"week": 2, "prereg": None})
    assert none_at_all["present"] is False


def test_the_week_1_prereg_declares_what_the_linter_requires():
    """The corpse check runs in the `Aegis module` repo and cannot run from
    the fast suite, so the FIELDS it needs are pinned here: a prereg that
    silently lost `slice_purpose` would only be caught by a human re-running
    the linter."""
    from pathlib import Path
    text = Path(A.prereg_state(A.anomaly_of(1))["path"]).read_text(
        encoding="utf-8")
    for field in ("event_frequency_per_year:", "declared_effect_size:",
                  "outcome_dispersion:", "slice_purpose:", "slice_period:",
                  "hypothesis_source:", "hypothesis_source_period:",
                  "information_cutoff:", "corpus_years:"):
        assert field in text, field
    assert "NEGATIVE_RESULTS.md" in text
    assert "UNSIGNED" in text


# ------------------------------------------------------- the decision rule

def _row(era, cost, adv):
    return {"era": era, "cost_cell": cost, "sharpe_advantage": adv}


def test_two_of_three_eras_is_the_bar_and_one_era_can_never_decide():
    """A rule that decided on one era would be deciding on whichever era
    loaded."""
    one = A.adjudicate([_row("a", A.PRIMARY_COST, 1.0)])
    assert one["verdict"] == "CANNOT_DETERMINE"
    assert "needs 2 of 3" in one["reason"]

    two = A.adjudicate([_row("a", A.PRIMARY_COST, 1.0),
                        _row("b", A.PRIMARY_COST, 0.5),
                        _row("c", A.PRIMARY_COST, -0.2)])
    assert two["verdict"] == "REPLICATES"
    assert two["n_eras_positive"] == 2

    none = A.adjudicate([_row("a", A.PRIMARY_COST, -1.0),
                         _row("b", A.PRIMARY_COST, 0.5),
                         _row("c", A.PRIMARY_COST, -0.2)])
    assert none["verdict"] == "DOES_NOT_REPLICATE"


def test_a_gross_only_replication_is_its_own_verdict_with_the_cost_named():
    """`REPLICATES_GROSS_ONLY` exists so a cost-killed anomaly is not reported
    as if the effect were absent."""
    rows = [_row("a", A.PRIMARY_COST, -0.1), _row("b", A.PRIMARY_COST, -0.2),
            _row("c", A.PRIMARY_COST, -0.3),
            _row("a", "flat_5+1bps", 0.4), _row("b", "flat_5+1bps", 0.3)]
    out = A.adjudicate(rows)
    assert out["verdict"] == "REPLICATES_GROSS_ONLY"
    assert "cost is what killed it" in out["reason"]


def test_the_verdict_is_decided_at_the_PRIMARY_cost_ruler_only():
    """Three cost cells are reported and one decides; a verdict that took the
    best of three rates would be a verdict about the rate."""
    rows = [_row("a", "flat_5+1bps", 2.0), _row("b", "flat_5+1bps", 2.0),
            _row("c", "flat_5+1bps", 2.0)]
    out = A.adjudicate(rows)
    assert out["verdict"] == "CANNOT_DETERMINE"      # nothing at the primary
    assert A.PRIMARY_COST == "taq_empirical"


# -------------------------------------------------------------- the control

def test_every_book_is_paired_with_a_drift_only_control_at_the_same_cost():
    cells = A.era_cells(A.anomaly_of(1))
    assert len(cells) == len(A.ERAS) * len(A.COST_CELLS)
    for c in cells:
        assert c["control"].signal == A.DRIFT_ONLY_CONTROL
        assert c["book"].signal == "reversal_1m"
        # same calendar, same size, same cost -- only the sort differs
        assert c["book"].holding_days == c["control"].holding_days
        assert c["book"].top_k == c["control"].top_k
        assert c["book"].curve == c["control"].curve
        assert (c["book"].transaction_cost_bps
                == c["control"].transaction_cost_bps)
        assert c["book"].policy_id != c["control"].policy_id


def test_the_control_is_declared_ONCE_and_not_per_anomaly():
    """A control chosen per anomaly is a control chosen after seeing the
    anomaly."""
    assert A.DRIFT_ONLY_CONTROL == "oldest_listing"
    assert all("control" not in a for a in A.ANOMALIES)
