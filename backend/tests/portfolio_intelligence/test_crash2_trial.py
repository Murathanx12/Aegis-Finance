"""TRIAL-CRASH-2 pre-registration invariants."""

import pytest

from backend.services.portfolio_intelligence import fragility as frag


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_pi.db"


def test_ensure_crash2_trial_idempotent(tmp_db):
    rid1 = frag.ensure_crash2_trial(db_path=tmp_db)
    rid2 = frag.ensure_crash2_trial(db_path=tmp_db)
    assert rid1 == rid2


def test_crash2_counts_toward_cumulative_trials(tmp_db):
    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(tmp_db)
    conn = get_connection(tmp_db)
    before = count_cumulative_trials(conn)
    conn.close()

    frag.ensure_crash2_trial(db_path=tmp_db)

    conn = get_connection(tmp_db)
    after = count_cumulative_trials(conn)
    conn.close()
    assert after == before + 1


def test_crash2_decision_rule_is_frozen_and_descriptive():
    rule = frag.CRASH2_DECISION_RULE
    # The gate-critical fields must exist and carry the hard constraints.
    assert rule["trial"] == "TRIAL-CRASH-2"
    assert "STLFSI4" in rule["adopt_threshold"] or "STLFSI4" in rule["hypothesis"]
    assert "climatology" in rule["hypothesis"] or "climatology" in rule["adopt_threshold"]
    assert "NEVER arms a lane" in rule["hard_constraint"]
    assert rule["canonical_doc"] == "docs/TRIALS/TRIAL-CRASH-2-severity-model.md"
    # No buy/sell language anywhere in the rule text.
    text = " ".join(str(v) for v in rule.values()).lower()
    assert "buy " not in text.replace("buy-sell", "") and "sell " not in text.replace("buy-sell", "")
