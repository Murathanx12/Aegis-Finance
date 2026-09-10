"""X9 for the 2026-09-09 day run — §11's numbers are pinned to their own receipts.

Same rule as `test_x9_doc_numbers.py`, applied to the section written today:
**the receipt wins.** Each test reads a number out of the receipt JSON and then
requires roadmap §11 to carry it, so the prose cannot drift from the run and a
re-run with different numbers goes red here rather than quietly disagreeing with
the paragraph beside it.

The receipts are large and are not all committed on every checkout, so a missing
receipt SKIPS rather than fails — but a receipt that is present and disagrees
with the doc is a failure, which is the case that actually bites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NIGHT = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-08"
DOC = REPO / "docs" / "ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md"


def _json(p: Path) -> dict:
    if not p.is_file():
        pytest.skip(f"receipt absent on this machine: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _section_11() -> str:
    if not DOC.is_file():
        pytest.skip(f"doc absent on this machine: {DOC}")
    text = DOC.read_text(encoding="utf-8", errors="replace")
    head = text.find("## 11. THE 2026-09-09 DAY RUN")
    if head < 0:
        pytest.skip("roadmap section 11 is not on this checkout")
    return text[head:]


def test_rw2_tradable_corner_era_table_matches_its_receipt():
    """§11.2's two era tables are the receipt's $10m / 200 bps cells."""
    s = _json(NIGHT / "RW2_event_windows_run01.json")["summary"]
    doc = _section_11()
    for sig in ("reaction_LS", "N1_H5_all_LS"):
        eras = s[f"{sig}|floor_10m|borrow200"]["by_start_era"]
        for era, cell in eras.items():
            diff = cell["median_vs_control_ann_pct"]
            assert f"{diff:+.2f}".lstrip("+") in doc or f"{abs(diff):.2f}" in doc, (
                f"{sig} {era} diff {diff} is not in section 11")
            assert f"{round(cell['win_vs_control'] * 100):d}%" in doc, (
                f"{sig} {era} win-vs-control {cell['win_vs_control']} is not in section 11")


def test_rw2_control_coverage_is_effectively_complete():
    """The win rates only mean what §11.2 says if the control was gradable.

    `beats_control` is False when the control could not be graded, which would
    bias every win rate DOWN. This asserts the bias is negligible rather than
    assuming it."""
    s = _json(NIGHT / "RW2_event_windows_run01.json")["summary"]
    for key in ("reaction_LS|floor_10m|borrow200", "N1_H5_all_LS|floor_10m|borrow200"):
        assert (s[key]["overall"]["share_control_ungraded"] or 0.0) <= 0.05, key


def test_n2_paired_numbers_and_the_sign_of_the_incremental():
    """§11.6's whole claim is that the DATELESS control adds MORE than the print."""
    r = _json(NIGHT / "N2_learner_v3_run01.json")
    doc = _section_11()
    treat = r["paired"]["v3_minus_v2"]["mean_diff_ann_pct"]
    ctl = r["paired"]["v3control_minus_v2"]["mean_diff_ann_pct"]
    incr = r["incremental_over_control_ann_pct"]
    assert ctl > treat, "the receipt no longer says the dateless control adds more"
    assert incr < 0, "the receipt no longer says the event print is negative over its control"
    for v in (f"{treat:.3f}", f"{ctl:.2f}", f"{abs(incr):.3f}"):
        assert v in doc, f"{v} is not in section 11"
    assert r["verdict"].startswith("FAILED_VARIANT")


def test_p6_bar_counts_match_the_panel_receipt():
    r = _json(NIGHT / "P6_bars_and_regret_run01.json")["P6a"]
    doc = _section_11()
    # prose may carry a thousands separator or not; both are the same number,
    # and a guard that insists on one spelling is a guard about typography
    for v in (r["bars"], r["symbols_with_bars"], r["sessions"]):
        assert str(v) in doc or f"{v:,}" in doc, f"{v} is not in section 11"
    assert r["symbols_with_no_bars"] == [], "some symbol returned no bars; section 11 claims zero"


def test_p6_survivorship_rows_carry_a_warning_and_stay_out_of_the_headline():
    """A survivor-screen book must never be the headline number."""
    b = _json(NIGHT / "P6_bars_and_regret_run03.json")["P6b"]
    books = b["mechanical_benchmarks_2025_to_today"]
    for name in ("EW_universe", "MOM_12_1", "REV_1M"):
        assert "BIAS_WARNING" in books[name], f"{name} lost its survivorship warning"
    for name in ("EW_universe", "REV_1M"):
        assert name not in b["headline"], f"{name} is survivorship-biased and is in the headline"


def test_p6_regret_uses_the_sessions_the_books_actually_existed():
    """The paired fix: 6-7 sessions, not the 62 the unpaired read compared against."""
    b = _json(NIGHT / "P6_bars_and_regret_run03.json")["P6b"]
    rows = b["regret_vs_spy_over_the_same_sessions"]
    assert rows, "no account returned a readable equity history"
    assert all(1 <= v["sessions"] <= 30 for v in rows.values()), (
        "an account is being graded over a window longer than it has existed; "
        "check that timestamps and equity are paired BEFORE filtering")
