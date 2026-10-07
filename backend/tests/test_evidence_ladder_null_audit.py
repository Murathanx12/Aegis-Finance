"""The evidence ladder's rate under NO edge is a property of the rule, pinned here.

`scripts/evidence_ladder_null_audit.py` measures how often `book_dna.evidence_label`
awards EARLY_EVIDENCE / REPLICATED to a book with no edge, and
`docs/research_notes/2026-10-07/evidence_ladder_null_rate_cloud_2026-10-07.md`
quotes the numbers. These tests tie the note to the code: if the rule changes,
the pinned band fails and the audit is re-run, rather than the note going stale.
Synthetic, seeded, offline; a few seconds.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services import book_dna as BD
from scripts import evidence_ladder_null_audit as A


@pytest.fixture(scope="module")
def p() -> dict:
    return BD.params()


def test_the_vectorised_copy_agrees_with_book_dna_label_for_label(p):
    out = A.check_vectorised_against_module(p, n_check=120, seed=11)
    assert out["mismatches"] == 0 and out["checked_pairs"] >= 120 * 6


def test_the_copy_refuses_when_it_and_the_module_disagree(p, monkeypatch):
    monkeypatch.setattr(A.BD, "evidence_label",
                        lambda **kw: {"label": "OBSERVED(0)", "why": "forced"})
    with pytest.raises(A.AuditRefused):
        A.check_vectorised_against_module(p, n_check=60, seed=3)


def test_a_book_with_no_edge_earns_early_evidence_about_four_times_in_ten(p):
    """THE pinned number. Sign rule => scale-free but for drag (next test); the band is
    wide enough for 3,000 paths and narrow enough to fail on a real rule change."""
    sim = A.simulate(3000, 63, alpha_year=0.0, seed=20261007)
    for n in (21, 63):
        rate = float((A.vector_labels(sim["book"], sim["spy"], None, n, p) >= 1).mean())
        assert 0.33 <= rate <= 0.47, (n, rate)


def test_the_rate_is_scale_free_but_for_compounding_drag(p, monkeypatch):
    """Same draws, rescaled noise. At realistic tracking error the scale is
    invisible; at an extreme one, compounding drag (~sigma^2/2 a session) makes a
    no-edge book LESS likely to be labelled -- never more."""
    base_te = A.TE_SIGMA
    rates = {}
    for k in (0.5, 1.0, 4.0):
        monkeypatch.setattr(A, "TE_SIGMA", base_te * k)
        sim = A.simulate(3000, 63, alpha_year=0.0, seed=5)
        rates[k] = float((A.vector_labels(sim["book"], sim["spy"], None, 63, p) >= 1).mean())
    assert abs(rates[0.5] - rates[1.0]) < 0.02, rates
    assert rates[4.0] < rates[1.0], rates


def test_daily_relooks_label_most_no_edge_books_while_the_boundary_holds_alpha(p):
    sim = A.simulate(3000, 126, alpha_year=0.0, seed=17)
    ever = np.zeros(3000, dtype=bool)
    for n in range(p["early_min_sessions"], 127):
        ever |= A.vector_labels(sim["book"], sim["spy"], None, n, p) >= 1
    crossed = A.robbins_crossed(sim["book"], sim["spy"], start=p["early_min_sessions"],
                                alpha=0.05, rho=A.RHO_SESSIONS)
    assert ever.mean() > 0.6
    assert crossed.mean() <= 0.05


def test_replicated_through_the_twin_clause_is_reached_by_a_quarter_of_no_edge_books(p):
    sim = A.simulate(3000, 63, alpha_year=0.0, seed=23, twin_corr=0.5)
    rep = float((A.vector_labels(sim["book"], sim["spy"], sim["twin"], 63, p) == 2).mean())
    assert 0.18 <= rep <= 0.36, rep
