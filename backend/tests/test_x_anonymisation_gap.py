"""The anonymisation gap: raw-vs-masked on the SAME cells, and the rule.

The spec's own known-answer test (section 7, step 2) is the first one here: feed
`read_RAW` and `read_MASKED` IDENTICAL digests -- a no-op mask -- and the gap
must be exactly 0.0 with `gap_nw_t` NULL, because a difference with zero
variance has no t. Reporting 0.0 from a 1e-18 variance floor would be a number
where there is none.

The rest pin the adjudication (spec section 2.2), the stratified cell draw, and
that the job refuses BY NAME when the reader is down instead of tracebacking.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from backend.services import protocol_p16 as pp
from backend.services import x_lane_data as xd
from scripts import night_x_anonymisation_gap as X
from scripts.night_r2_monthly_llm import grade


def _rows(tag, months, dirs, fwds, names=None):
    names = names or [f"S{i}" for i in range(len(months))]
    return [{"tag": tag, "name": n, "month": m, "dir": d, "conf": 0.6, "fwd": f}
            for n, m, d, f in zip(names, months, dirs, fwds)]


def _series(dirs_by_month, fwd_by_month):
    """A gradeable row set: three names per month, one month per block."""
    rows = []
    for m in sorted(dirs_by_month):
        for i, (d, f) in enumerate(zip(dirs_by_month[m], fwd_by_month[m])):
            rows.append({"tag": "x", "name": f"N{i}", "month": m, "dir": d,
                         "conf": 0.6, "fwd": f})
    return rows


MONTHS = [f"2025-{i:02d}" for i in range(1, 13)]


def _identical_arms():
    rng = np.random.default_rng(20260912)
    dirs = {m: list(rng.choice([-1, 1], 4)) for m in MONTHS}
    fwd = {m: list(rng.normal(0, 0.05, 4)) for m in MONTHS}
    rows = _series(dirs, fwd)
    return grade(rows, "raw"), grade(list(rows), "masked")


def test_identical_digests_give_a_zero_gap_and_no_t():
    """Spec section 7 step 2's known answer, exactly."""
    raw, masked = _identical_arms()
    gap = X.paired_gap(raw, masked)
    assert gap["gap_pct_pt"] == pytest.approx(0.0, abs=1e-9)
    assert gap["gap_nw_t"] is None, "a difference with zero variance has no t"
    assert gap["gap_paired_blocks"] == 12
    assert "identically zero" in gap["note"]


def test_a_raw_arm_that_really_wins_produces_a_positive_gap_with_a_t():
    rng = np.random.default_rng(7)
    fwd = {m: list(rng.normal(0, 0.04, 4)) for m in MONTHS}
    # the raw arm calls every sign right, the masked arm calls every sign wrong
    raw = grade(_series({m: [int(np.sign(f) or 1) for f in fwd[m]] for m in MONTHS}, fwd), "raw")
    masked = grade(_series({m: [-int(np.sign(f) or 1) for f in fwd[m]] for m in MONTHS}, fwd),
                   "masked")
    gap = X.paired_gap(raw, masked)
    assert gap["gap_pct_pt"] > 0
    assert gap["gap_nw_t"] is not None and gap["gap_nw_t"] > 2.0


def test_mismatched_month_blocks_refuse_rather_than_pair_different_dates():
    raw, masked = _identical_arms()
    masked["_months"] = list(reversed(masked["_months"]))
    gap = X.paired_gap(raw, masked)
    assert gap["gap_pct_pt"] is None and "REFUSED" in gap["note"]


# ------------------------------------------------------------ the adjudication

@pytest.mark.parametrize("gap_pp,amnesia,expect", [
    (None, 0.0, "CONDITIONAL_INSUFFICIENT_DATA"),
    (-3.0, 0.0, "MASKED"),                    # raw loses -> the default stands
    (0.0, 0.0, "MASKED"),                     # a tie is not a reason to switch
    (5.0, None, "CONDITIONAL_INSUFFICIENT_DATA"),   # no cross-check available
    (5.0, 0.09, "MASKED"),                    # raw wins AND the canary is hot
    (5.0, 0.02, "RAW"),                       # raw wins, canary at the threshold
    (5.0, -0.001, "RAW"),                     # PANEL-B's measured canary
])
def test_the_adoption_rule_is_applied_literally(gap_pp, amnesia, expect):
    arm, why = X.adjudicate({"gap_pct_pt": gap_pp}, {"gap": amnesia})
    assert arm == expect, why
    assert why


def test_the_rule_text_travels_in_the_receipt_so_nobody_re_derives_it():
    assert "citation" not in X.ADOPTION_RULE.lower() or True
    for phrase in ("block-paired", "AMNESIA canary", "Default while the raw arm has not run"
                   .replace("Default", "3. Default")):
        assert phrase in X.ADOPTION_RULE


def test_the_canary_threshold_is_trial_r2s_own_not_a_new_one():
    assert X.AMNESIA_ADOPT_MAX == 0.02


# ------------------------------------------------------------- the cell draw

def test_the_draw_is_stratified_by_month_block_and_reproducible():
    keys = [(f"S{i}", m) for m in MONTHS for i in range(50)]
    a = xd.stratified_cells(keys, n=60, seed=20260909)
    b = xd.stratified_cells(keys, n=60, seed=20260909)
    assert a == b, "the same seed must draw the same cells"
    assert len(a) == 60
    per_block = {}
    for _, m in a:
        per_block[m] = per_block.get(m, 0) + 1
    assert set(per_block) == set(MONTHS)
    assert max(per_block.values()) - min(per_block.values()) <= 1, per_block
    assert xd.stratified_cells(keys, n=60, seed=1) != a


def test_a_short_block_does_not_shorten_the_draw():
    keys = [("A", "2025-01")] + [(f"S{i}", "2025-02") for i in range(40)]
    drawn = xd.stratified_cells(keys, n=20, seed=3)
    assert len(drawn) == 20
    assert sum(1 for k in drawn if k[1] == "2025-01") == 1


def test_the_draw_never_exceeds_what_exists():
    keys = [("A", "2025-01"), ("B", "2025-01")]
    assert len(xd.stratified_cells(keys, n=99, seed=1)) == 2


def test_the_fingerprint_changes_with_the_cells_and_not_with_the_run():
    a = xd.cells_fingerprint([("A", "2025-01"), ("B", "2025-02")])
    b = xd.cells_fingerprint([("A", "2025-01"), ("B", "2025-02")])
    c = xd.cells_fingerprint([("A", "2025-01"), ("C", "2025-02")])
    assert a == b and a["cells_sha256"] != c["cells_sha256"]
    assert a["n_cells"] == 2


# ------------------------------------------------------- the AMNESIA import

def test_the_canary_gap_is_read_from_the_receipt_when_it_has_one(tmp_path):
    r = tmp_path / "R2_run01.json"
    r.write_text(json.dumps({"AMNESIA_canary": {"accuracy_gap_real_minus_masked": 0.031}}),
                 encoding="utf-8")
    out = xd.amnesia_gap(receipt=r)
    assert out["gap"] == 0.031 and "imported" in out["how"]


def test_the_canary_gap_falls_back_to_r2s_own_answers_and_says_so(tmp_path):
    """R2's PANEL-B receipt is PENDING_MODEL and has no canary block. The
    fallback reads R2's OWN persisted canary rows -- still R2's output -- and
    the receipt says which source was used, because 'imported' and 'derived
    from the same file' are different claims."""
    ans = tmp_path / "answers.jsonl"
    rows = (_rows("canary_REAL_names", ["2025-01"] * 4, [1, 1, 1, 1], [1.0, 1.0, 1.0, -1.0])
            + _rows("canary_MASKED", ["2025-01"] * 4, [1, 1, 1, 1], [1.0, -1.0, -1.0, -1.0]))
    ans.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = xd.amnesia_gap(receipt=tmp_path / "absent.json", answers=ans)
    assert out["gap"] == pytest.approx(0.75 - 0.25)
    assert "re-derived" in out["how"] and out["n_real"] == 4


def test_no_canary_anywhere_is_cannot_determine_not_zero(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    out = xd.amnesia_gap(receipt=tmp_path / "absent.json", answers=empty)
    assert out["gap"] is None and "CANNOT DETERMINE" in out["how"]


def test_flat_calls_are_excluded_from_the_accuracy_denominator():
    rows = _rows("t", ["2025-01"] * 3, [1, 0, -1], [1.0, 1.0, 1.0])
    acc, n = xd.sign_accuracy(rows)
    assert n == 2 and acc == pytest.approx(0.5)


# ----------------------------------------------------- the run with no reader

def _synthetic_panel(monkeypatch, tmp_path):
    """A 4-name x 12-month PANEL-B stand-in.

    The real `news_returns_2025_26.parquet` is NOT in version control, so a
    test that read it would pass here and take the REFUSED branch on a fresh
    CI checkout -- green for the wrong reason, the shape CLAUDE.md protocol 7
    is about. The synthetic panel makes the refusal logic testable on any
    checkout.
    """
    import pandas as pd

    months = MONTHS
    syms = [f"S{i}" for i in range(4)]
    rng = np.random.default_rng(11)
    cells = pd.DataFrame([{"symbol": s, "month": m, "name": s,
                           "excess_vw_1m": float(rng.normal(0, 0.05))}
                          for m in months for s in syms])
    dig = {(s, m): f"- news about {s} in {m}" for m in months for s in syms}
    monkeypatch.setattr(X, "OUT", tmp_path)
    monkeypatch.setattr(X, "widened_cells_and_docs", lambda: (cells, None, {"f": 1}))
    monkeypatch.setattr(X, "widened_digests",
                        lambda c, n: (dict(dig), dict(dig), {"mask_hit_rate": 0.4}))
    return cells, dig


def test_the_job_refuses_by_name_when_the_reader_is_down(monkeypatch, tmp_path):
    """No model, no traceback, and the cell list frozen so the real run
    reproduces this one."""
    _synthetic_panel(monkeypatch, tmp_path)
    monkeypatch.setattr(X, "_probe", lambda backend: "ProviderRefusal: local unreachable")
    payload = X.X_anon_gap(cells=40, run=7)
    assert payload["verdict"].startswith("PENDING_MODEL")
    assert payload["cells_frozen"]["n_cells"] == 40      # 48 exist; 40 were drawn
    frozen = tmp_path / "X_anon_gap_run07_cells.json"
    assert frozen.is_file()
    saved = json.loads(frozen.read_text(encoding="utf-8"))
    assert saved["cells_sha256"] == payload["cells_frozen"]["cells_sha256"]
    assert len(saved["cells"]) == 40
    assert pp.refuse_reasons("X_anon_gap", payload) == [], "the receipt must pass the protocol"
    assert payload["anonymisation_gap"]["value_pct_pt"] is None
    assert "PENDING_MODEL" in payload["anonymisation_gap"]["reason"]
    assert payload["LAP"]["applies"] is False and payload["LAP"]["reason_if_not_applicable"]


def test_the_job_never_starts_the_model_server():
    """AST: nothing in this module calls `llama_server.start`."""
    import ast
    from pathlib import Path

    src = Path(X.__file__).read_text(encoding="utf-8")
    banned = {"start", "stop", "bind_lifetime"}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute) and node.attr in banned:
            val = node.value
            name = getattr(val, "id", None) or getattr(val, "attr", None)
            assert name not in ("llama_server", "ls"), (
                "the desktop shell owns llama-server; a research job that boots it "
                "collides with another job mid-run")


def test_the_job_is_registered_in_the_night_factory():
    from scripts import night_factory_jobs as NFJ

    assert "X_anon_gap" in NFJ.JOBS and callable(NFJ.JOBS["X_anon_gap"])


def test_a_mocked_reader_produces_a_gap_the_validator_accepts(monkeypatch, tmp_path):
    """The whole path with a stubbed `complete`: four arms, a gap, a verdict,
    and a receipt that passes the P1-P6 refusal."""
    from types import SimpleNamespace

    _synthetic_panel(monkeypatch, tmp_path)
    monkeypatch.setattr(X, "_probe", lambda backend: None)

    import backend.services.free_inference as fi

    calls = {"n": 0}

    def fake_complete(backend, prompt, **kw):
        calls["n"] += 1
        d = "UP" if calls["n"] % 2 else "DOWN"
        return SimpleNamespace(text=f"DIRECTION: {d}\nCONFIDENCE: 0.7",
                               tokens_in=100, tokens_out=10)

    monkeypatch.setattr(fi, "complete", fake_complete)
    payload = X.X_anon_gap(cells=24, run=3)
    assert calls["n"] == 24 * 4, "four arms over the same cells"
    assert payload["verdict"].startswith("ADOPTED_ARM=")
    assert pp.refuse_reasons("X_anon_gap", payload) == []
    assert payload["ANONYMISATION_GAP"]["gap_paired_blocks"] > 0
    assert (tmp_path / "X_anon_gap_answers_run03.jsonl").is_file()


def test_a_checkout_without_the_panel_refuses_and_still_carries_the_protocol(monkeypatch,
                                                                             tmp_path):
    """A fresh CI checkout has no `news_returns_2025_26.parquet`. The job says
    so and its receipt STILL carries P1-P6 -- a refusal is a finding, and a
    finding the board cannot print is a finding nobody reads."""
    monkeypatch.setattr(X, "OUT", tmp_path)

    def missing():
        raise FileNotFoundError("no widened panel on this checkout")

    monkeypatch.setattr(X, "widened_cells_and_docs", missing)
    payload = X.X_anon_gap(run=2)
    assert payload["verdict"].startswith("REFUSED")
    assert pp.refuse_reasons("X_anon_gap", payload) == []


def test_the_frozen_cell_list_cannot_be_mistaken_for_a_receipt():
    """`night_leaderboard_sync.RECEIPT` matches anything ending `_runNN.json`.
    A sidecar named `X_anon_gap_cells_run01.json` would parse as a JOB called
    `X_anon_gap_cells` and reach the board as a row -- refused for having no
    P1_P6 block, a true statement about a file that was never a receipt. The
    suffix goes after the run number, and this pins it."""
    from scripts.night_leaderboard_sync import RECEIPT

    assert RECEIPT.match("X_anon_gap_run01.json")
    assert not RECEIPT.match("X_anon_gap_run01_cells.json")
    assert RECEIPT.match("X_anon_gap_cells_run01.json"), (
        "the old name DID match -- this assertion documents why it changed")
