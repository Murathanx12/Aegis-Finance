"""X5 — the verdict vocabulary has a word between NOVEL and NOISE.

WHAT HAPPENED. The B1 known-answer battery (`--fast`) planted a linear
cross-sectional edge, and the machine MEASURED it correctly:

    linear::lgbm   t 3.0147   p_raw 0.00257   Holm 0.01543   BH-FDR 0.00625
                   observed 15.6%/yr   own MDE 10.4%/yr
                   DSR 0.9313   SPA 0.002   PBO 0.0857

and `weekend_lab_jobs.verdict_from` returned **NOISE**, because a self-resolved
arm had exactly two outcomes: NOVEL — which needs DSR >= 0.95 AND SPA <= 0.10
AND PBO < 0.5 AND a sign in two of three eras — or NOISE. On 36 months the
deflated Sharpe cannot reach 0.95, so the entire vocabulary collapsed onto the
word for *there was nothing there*, on tape where something demonstrably was.
The battery filed it as a defect in the INSTRUMENT, which is what it is.

`SEPARATED_NOT_SURVIVING` is the missing word:

    resolved itself on this tape  AND  family-corrected p <= 0.05
                                  AND  short of the export bar

It authorises nothing. It caps in `evidence_memory.export_verdict` exactly as
NOISE does, so nothing is promoted through it; what changes is that a reader is
no longer told a real, family-significant planted effect was noise.

A NOTE ON THE ROADMAP'S WORDING, because the receipt outranks it. The X5 row
glosses the condition as "the t clears the MDE but Holm does not". Holm p
**0.01543 clears** 0.05 — what fails is the DEFLATION bar (DSR 0.9277-0.9459 on
36 months). The implemented condition is therefore *separated after Holm, short
of the export bar*, which is also exactly what the battery's own finding text
asked for: "no word for 'significant, did not clear the deflation bar'".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from learner import evidence_memory as EM
from scripts import weekend_lab_jobs as WLJ

REPO = Path(__file__).resolve().parents[2]
FAST_RECEIPT = (REPO / "backend" / "data" / "optimus" /
                "labor_day_lab_2026-09-07" / "B1_known_answer_battery_fast.json")


def _inf(dsr=0.93, spa=0.004, pbo=0.086, powered=False, resolved=True):
    return {
        "deflated_sharpe": {"dsr": dsr},
        "spa": {"p_spa_consistent": spa},
        "pbo": {"pbo": pbo},
        "power": {"powered": powered,
                  "powered_for_observed_effect": resolved,
                  "mde_annual_excess_at_t_target": 0.1033},
    }


def _eras(holds=False):
    return {"holds_in_2_of_3": holds,
            "2016-2018": {"t": 1.1}, "2019-2021": {"t": 1.2},
            "2022-2024": {"t": 1.3}}


# ------------------------------------------------------- the case that broke

def test_the_planted_edge_at_holm_0_0154_no_longer_reads_noise():
    v = WLJ.verdict_from(_inf(), _eras(), holm_p=0.01543458)
    assert v.startswith("SEPARATED_NOT_SURVIVING"), v
    assert "0.01543458" in v
    assert "DSR 0.93" in v, "the verdict must name WHICH leg of the bar failed"


def test_without_the_family_p_the_old_answer_stands():
    """A caller with no family has no correction to report, and the honest
    word for an arm nobody corrected is still NOISE."""
    assert WLJ.verdict_from(_inf(), _eras()) == "NOISE"


def test_a_family_p_above_the_alpha_is_still_noise():
    assert WLJ.verdict_from(_inf(), _eras(), holm_p=0.20) == "NOISE"


def test_an_underpowered_arm_that_did_not_resolve_itself_stays_cannot_determine():
    inf = _inf(powered=False, resolved=False)
    v = WLJ.verdict_from(inf, _eras(), holm_p=0.001)
    assert v.startswith("CANNOT DETERMINE"), v


def test_the_full_bar_still_reaches_novel_and_is_not_downgraded():
    inf = _inf(dsr=0.99, spa=0.01, pbo=0.1, powered=True, resolved=True)
    assert WLJ.verdict_from(inf, _eras(holds=True), holm_p=0.0001) == "NOVEL"


def test_a_null_arm_is_never_separated():
    """The one direction of error that matters: a true null must not acquire a
    word that sounds like a finding."""
    inf = _inf(dsr=0.13, spa=0.38, pbo=0.086, powered=True, resolved=False)
    v = WLJ.verdict_from(inf, _eras(), holm_p=1.0)
    assert not v.startswith("SEPARATED_NOT_SURVIVING"), v


def test_the_alpha_is_declared_not_inline():
    assert WLJ.SEPARATION_ALPHA == 0.05


# ------------------------------------------------------------- the vocabulary

def test_the_word_is_in_the_shared_vocabulary():
    assert "SEPARATED_NOT_SURVIVING" in EM.VERDICT_VOCABULARY
    v = WLJ.verdict_from(_inf(), _eras(), holm_p=0.01543458)
    assert EM._leading_vocabulary_word(v) == "SEPARATED_NOT_SURVIVING"


def test_it_caps_the_export_exactly_as_noise_does():
    """A recorded SEPARATED_NOT_SURVIVING may not be promoted by arithmetic."""
    assert "SEPARATED_NOT_SURVIVING" in EM._CAPPING_WORDS
    row = {
        "dsr": 0.999, "spa_p": 0.0001, "pbo": 0.0,
        "eras": {"holds_in_2_of_3": True},
        "powered": True,
        "verdict": "SEPARATED_NOT_SURVIVING (family-corrected Holm p 0.0154; "
                   "short of the export bar on DSR 0.9277)",
    }
    word, why = EM.export_verdict(row)
    assert word == "SEPARATED_NOT_SURVIVING"
    assert why and "capped by the job" in why


def test_the_derived_path_never_invents_it():
    """A stored observation carries no family, so the arithmetic cannot reach
    the word -- it only ever arrives from a job that computed a correction."""
    row = {"dsr": 0.93, "spa_p": 0.004, "pbo": 0.086, "powered": True,
           "holm_p": 0.0154, "eras": {"holds_in_2_of_3": False}}
    assert EM._derive_verdict(row) == "NOISE"


# --------------------------------------------------- the battery, re-adjudicated

def test_the_b1_fast_receipt_shows_the_flip():
    """The battery re-run under X5. Every family-significant planted cell must
    now carry the new word, and the null world must NOT."""
    if not FAST_RECEIPT.is_file():
        pytest.skip(f"B1 fast receipt absent: {FAST_RECEIPT}")
    r = json.loads(FAST_RECEIPT.read_text(encoding="utf-8"))
    cells = r["results"]

    planted = {k: v for k, v in cells.items() if k.startswith("linear::")}
    assert planted, "the fast battery must carry the linear world"
    for k, v in planted.items():
        assert v["p_holm"] is not None and v["p_holm"] < 0.05, k
        assert str(v["verdict"]).startswith("SEPARATED_NOT_SURVIVING"), (k, v["verdict"])

    for k, v in cells.items():
        if not k.startswith("null::"):
            continue
        assert not str(v["verdict"]).startswith("SEPARATED_NOT_SURVIVING"), (k, v["verdict"])

    assert r["adjudication"]["ALL_PASS"] is True
    assert any(str(f).startswith("RESOLVED [linear]")
               for f in r["adjudication"]["findings"]), \
        r["adjudication"]["findings"]
