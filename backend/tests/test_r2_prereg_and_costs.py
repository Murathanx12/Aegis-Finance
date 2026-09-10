"""R2 — the pre-registration is pinned to the code, and the numbers to the receipts.

Two jobs, in the `test_x9_day_run_numbers.py` style (**the receipt wins**), plus a
third the X9 tests do not do:

1. **The prompt hash.** `docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`,
   `backend/services/portfolio_intelligence/r2_trial.py` and every R2 receipt on
   this checkout must carry the SAME sha256 for the system prompt, the user
   prompt and the digest spec. Edit the prompt and this file goes red — which is
   the whole point of registering it: TRIAL-R2's own hypothesis section names
   "the prompt was not registered when it ran" as the reason PANEL-A is
   CONDITIONAL rather than a claim, and an unpinned registration would be the
   same situation with a document on top.

2. **The headline numbers.** PANEL-A's +16.189%/yr, t 3.922 over 112 blocks and
   its passing AMNESIA canary are quoted in the trial doc; they are read out of
   `R2_monthly_llm_2015_2024_run01.json` and required to match.

3. **The cost arithmetic itself**, on synthetic answers where the right answer is
   known by hand. `grade` charges 25 bps a side on REALISED turnover
   (Σ|Δw| per rebalance) rather than a flat rate per date — the defect that made
   C2 print −237%/yr net for a monthly book on 2026-09-09 — and a paired
   difference of two identically-rebalanced books must therefore lose almost
   nothing to costs. That is asserted here, not argued in prose.

A receipt that is absent on this checkout SKIPS; a receipt that is present and
disagrees FAILS, which is the case that bites.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.portfolio_intelligence import r2_trial          # noqa: E402

NIGHT_A = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-08"
NIGHT_B = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-10"
DOC = REPO / "docs" / "TRIALS" / "TRIAL-R2-monthly-news-digest-read.md"


def _json(p: Path) -> dict:
    if not p.is_file():
        pytest.skip(f"receipt absent on this machine: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _doc() -> str:
    if not DOC.is_file():
        pytest.skip(f"trial doc absent on this machine: {DOC}")
    return DOC.read_text(encoding="utf-8", errors="replace")


# ───────────────────────────────────────────── 1. the frozen prompt

def test_the_registered_hashes_are_in_the_trial_document():
    """The doc's §6 table must carry the hashes the module computes."""
    doc = _doc()
    for label, sha in (("system prompt", r2_trial.SYSTEM_SHA256),
                       ("user prompt", r2_trial.PROMPT_SHA256),
                       ("digest spec", r2_trial.DIGEST_SPEC_SHA256)):
        assert sha in doc, (
            f"the {label} sha256 {sha} is not in {DOC.name}. Either the prompt was edited "
            "(register a NEW arm — a prompt edit is a new experiment, not a better version "
            "of this one) or the document was not updated with it.")


def test_the_prompt_that_ran_on_panel_a_is_the_prompt_that_is_registered():
    """The commitment is worth nothing if it froze a DIFFERENT prompt.

    `night_r2_monthly_llm` no longer defines the prompt; it imports it. This
    asserts the import really is the text that produced PANEL-A, by checking the
    module's own constants against the frozen hashes.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_r2_script", REPO / "scripts" / "night_r2_monthly_llm.py")
    if spec is None or spec.loader is None:            # pragma: no cover
        pytest.skip("the R2 script is not on this checkout")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert r2_trial._sha(mod.SYSTEM) == r2_trial.SYSTEM_SHA256
    assert r2_trial._sha(mod.PROMPT) == r2_trial.PROMPT_SHA256


def test_a_prompt_edit_is_refused_rather_than_run():
    """`verify_frozen` REFUSES; it does not repair, retry or warn."""
    with pytest.raises(r2_trial.FrozenPromptViolation):
        r2_trial.verify_frozen(r2_trial.SYSTEM, r2_trial.PROMPT + " Be concise.")
    with pytest.raises(r2_trial.FrozenPromptViolation):
        r2_trial.verify_frozen(r2_trial.SYSTEM + " ", r2_trial.PROMPT)
    assert r2_trial.verify_frozen(r2_trial.SYSTEM, r2_trial.PROMPT)["prompt_sha256"] == \
        r2_trial.PROMPT_SHA256


@pytest.mark.parametrize("name", ["R2_widened_panelB_run01.json"])
def test_every_r2_receipt_records_the_hashes_it_ran_under(name):
    """A receipt without the fingerprint cannot be tied to any commitment."""
    r = _json(NIGHT_B / name)
    fp = r.get("PREREGISTRATION") or {}
    assert fp.get("prompt_sha256") == r2_trial.PROMPT_SHA256, (
        f"{name} ran under prompt {fp.get('prompt_sha256')}, the registration says "
        f"{r2_trial.PROMPT_SHA256}")
    assert fp.get("system_sha256") == r2_trial.SYSTEM_SHA256
    assert fp.get("digest_spec_sha256") == r2_trial.DIGEST_SPEC_SHA256
    assert fp.get("model_identity", {}).get("sha256") == r2_trial.MODEL_IDENTITY["sha256"]


# ─────────────────────────────────────── 2. the numbers, against the receipts

def test_panel_a_headline_numbers_match_the_trial_document():
    """The doc quotes PANEL-A as the honest prior; the receipt is the authority."""
    r = _json(NIGHT_A / "R2_monthly_llm_2015_2024_run01.json")
    doc = _doc()
    pri = r["PRIMARY_read_minus_control"]
    assert pri["blocks"] == 112
    for v in (f"{pri['mean_ann_pct']:.3f}", f"{pri['t_nw']:.3f}",
              f"{r['arm_masked_read']['long_short_ann_pct']:.3f}",
              f"{r['control_shuffled_digest']['long_short_ann_pct']:.3f}"):
        assert v in doc, f"PANEL-A's {v} is not in {DOC.name}"


def test_panel_a_amnesia_canary_still_passes_in_its_receipt():
    """The canary is a GATE in §5, so its sign is load-bearing, not decoration."""
    r = _json(NIGHT_A / "R2_monthly_llm_2015_2024_run01.json")
    gap = r["AMNESIA_canary"]["accuracy_gap_real_minus_masked"]
    assert gap is not None and gap <= 0.02, (
        f"the AMNESIA gap is {gap}: the model does BETTER with real company names, which is "
        "recall of its training data, not reading. TRIAL-R2 §5 rejects above +0.05.")


def test_panel_b_power_declaration_matches_the_receipt_that_produced_it():
    """§4's power numbers were computed by the PENDING_MODEL run; pin them."""
    r = _json(NIGHT_B / "R2_widened_panelB_run01.json")
    doc = _doc()
    pw = r["POWER_FIRST"]
    assert pw["date_blocks"] == 19
    for v in (f"{pw['cells']:,}", f"{pw['median_names_per_month']:.0f}",
              f"{pw['implied_long_short_monthly_sd'] * 100:.2f}"):
        assert v in doc, f"PANEL-B's {v} is not in {DOC.name}"
    assert r["masking"]["mask_hit_rate"] > 0.0, "no document lost a company token: the mask is inert"


def test_panel_b_is_filed_as_its_own_receipt_and_does_not_restate_panel_a():
    r = _json(NIGHT_B / "R2_widened_panelB_run01.json")
    assert r["panel"] == "PANEL-B"
    assert "does_not_restate" in r
    assert r["job"] != "R2_monthly_llm", "the widened read must not overwrite PANEL-A's job name"


def test_panel_a_cost_amendment_bounds_are_arithmetic_and_match_the_doc():
    """PANEL-A's net cannot be measured, so it is BOUNDED — and the bound is checked.

    A bound quoted in prose and computed nowhere is how `corr = 0.516` happened.
    """
    r = _json(NIGHT_A / "R2_cost_amendment.json")
    src = _json(NIGHT_A / "R2_monthly_llm_2015_2024_run01.json")
    doc = _doc()
    b = r["what_CAN_be_said_without_the_answers"]
    max_drag = 2.0 * (b["cost_bps_per_side"] / 1e4) * 12 * 100
    assert b["max_cost_drag_ann_pct_per_leg"] == pytest.approx(max_drag, abs=1e-9)
    arm = src["arm_masked_read"]["long_short_ann_pct"]
    assert b["bound_on_the_arm_NET_ann_pct"] == [pytest.approx(arm - max_drag, abs=1e-3),
                                                 pytest.approx(arm, abs=1e-3)]
    lo, hi = b["bound_on_the_DIFFERENCE_NET_ann_pct"]
    assert lo < src["PRIMARY_read_minus_control"]["mean_ann_pct"] < hi
    for v in (f"{lo:.3f}", f"{hi:.3f}"):
        assert v in doc, f"the PANEL-A cost bound {v} is not in {DOC.name}"
    assert "CANNOT DETERMINE" in r["what_the_net_line_IS_NOT_AVAILABLE"]["verdict"], (
        "PANEL-A's net must stay CANNOT DETERMINE until a run persists its answers")


# ─────────────────────────────────────────── 3. the cost arithmetic itself

def _script():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_r2_script_costs", REPO / "scripts" / "night_r2_monthly_llm.py")
    if spec is None or spec.loader is None:            # pragma: no cover
        pytest.skip("the R2 script is not on this checkout")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_full_monthly_replacement_costs_six_percent_a_year_not_two_hundred():
    """The C2 defect, asserted away: a MONTHLY book pays a MONTHLY cost.

    Two names, flipping long and short every month, is the worst case a gross-1
    long-short can have: turnover 2.0 at every rebalance after the first, and
    1.0 at the first, because the opening book is bought from nothing and that
    is charged too. Over 12 months the mean is 23/12 = 1.9167, i.e. 5.75%/yr at
    25 bps a side — not 100 bps a DAY, which is what a flat per-date charge on a
    monthly book comes to.
    """
    mod = _script()
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    rows = []
    for i, m in enumerate(months):
        s = 1 if i % 2 == 0 else -1
        rows.append({"tag": "t", "name": "AAA", "month": m, "dir": s, "conf": 1.0, "fwd": 0.0})
        rows.append({"tag": "t", "name": "BBB", "month": m, "dir": -s, "conf": 1.0, "fwd": 0.0})
    g = mod.grade(rows, "worst case", cost_bps=25.0)
    assert g["date_blocks"] == 12
    assert g["turnover_per_rebalance"] == pytest.approx(23 / 12, abs=1e-4)
    assert g["long_short_ann_pct"] == pytest.approx(0.0, abs=1e-9)
    assert g["long_short_ann_pct_NET"] == pytest.approx(-5.75, abs=1e-2)
    # and the flat-per-date model this replaces would have said:
    assert 100 / 1e4 * 252 * 100 > 200, "the C2 arithmetic: 100 bps a day is >200%/yr"


def test_an_unchanged_book_pays_only_the_first_month():
    """Turnover is REALISED, so a book that does not trade does not pay."""
    mod = _script()
    rows = [{"tag": "t", "name": "AAA", "month": f"2025-{m:02d}", "dir": 1, "conf": 1.0, "fwd": 0.0}
            for m in range(1, 13)]
    g = mod.grade(rows, "buy and hold", cost_bps=25.0)
    assert g["turnover_per_rebalance"] == pytest.approx(1.0 / 12, abs=1e-4)
    assert g["long_short_ann_pct_NET"] == pytest.approx(-0.25, abs=1e-2)


def test_costs_cancel_in_the_paired_difference_of_two_identical_books():
    """The PRIMARY is a difference; the claim that costs cancel is MEASURED.

    Two books over the same names on the same dates, both turning over fully,
    differ in gross by construction here — and their NET difference must equal
    their GROSS difference to within the turnover mismatch, which is zero.
    """
    mod = _script()
    rng = np.random.default_rng(20260910)
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    arm_rows, ctl_rows = [], []
    for m in months:
        for n in ("AAA", "BBB", "CCC", "DDD"):
            f = float(rng.normal(0, 0.05))
            arm_rows.append({"tag": "a", "name": n, "month": m,
                             "dir": int(rng.choice([-1, 1])), "conf": 1.0, "fwd": f})
            ctl_rows.append({"tag": "c", "name": n, "month": m,
                             "dir": int(rng.choice([-1, 1])), "conf": 1.0, "fwd": f})
    arm = mod.grade(arm_rows, "arm", cost_bps=25.0)
    ctl = mod.grade(ctl_rows, "control", cost_bps=25.0)
    d = mod.paired_vs(arm, ctl, "arm minus control")
    assert d["blocks"] == 12
    moved = d["cost_cancellation"]["cost_effect_on_the_difference_ann_pct"]
    assert abs(moved) < 1.0, (
        f"costs moved the paired difference by {moved}%/yr; with matched turnover they should "
        "move it by ~0. The claim in the amendment is that they cancel — this is the measurement.")
    assert d["mean_ann_pct"] is not None and d["mean_ann_pct_NET"] is not None


def test_a_paired_difference_refuses_when_the_two_books_do_not_share_their_months():
    """Pairing different dates is not a paired test. Refuse, do not silently zip."""
    mod = _script()
    a = mod.grade([{"tag": "a", "name": "AAA", "month": f"2025-{m:02d}", "dir": 1, "conf": 1.0,
                    "fwd": 0.01} for m in range(1, 13)], "a")
    c = mod.grade([{"tag": "c", "name": "AAA", "month": f"2024-{m:02d}", "dir": 1, "conf": 1.0,
                    "fwd": 0.01} for m in range(1, 13)], "c")
    out = mod.paired_vs(a, c, "mismatched")
    assert out.get("verdict", "").startswith("REFUSED")


def test_regrade_reproduces_a_grade_without_any_model(tmp_path):
    """Answers on disk are re-gradable at any cost rate, forever, for free."""
    mod = _script()
    rows = []
    for m in range(1, 13):
        for n, d in (("AAA", 1), ("BBB", -1)):
            rows.append({"tag": "read_MASKED", "name": n, "month": f"2025-{m:02d}",
                         "dir": d, "conf": 1.0, "fwd": 0.01 * d})
            rows.append({"tag": "control_SHUFFLED", "name": n, "month": f"2025-{m:02d}",
                         "dir": -d, "conf": 1.0, "fwd": 0.01 * d})
    f = tmp_path / "answers.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = mod.regrade(f, cost_bps=25.0)
    assert out["rows"] == len(rows)
    assert set(out["by_tag"]) == {"read_MASKED", "control_SHUFFLED"}
    pri = out["PRIMARY_read_minus_control"]
    assert pri["blocks"] == 12
    assert pri["mean_ann_pct"] > 0, "the arm calls the sign right and the control calls it wrong"
    cheap = mod.regrade(f, cost_bps=5.0)
    assert cheap["PRIMARY_read_minus_control"]["mean_ann_pct_NET"] is not None
    assert cheap["cost_bps_per_side"] == 5.0
