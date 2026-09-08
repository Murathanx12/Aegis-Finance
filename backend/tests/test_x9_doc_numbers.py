"""X9 — the headline numbers in `docs/` are pinned to their own receipts.

WHAT HAPPENED. `docs/VALIDATION_2026-09-07_GPT_SUMMARY_VS_RECEIPTS.md` checked
twenty claims a reader had made about this repo and found **eight places where
OUR OWN DOCUMENTS disagreed with the receipts they cite**. Not one of them was
an arithmetic error: each was a number written once, copied forward, and never
re-read against the file it came from. The worst of them changed the reading of
a result:

  * the night lab's construction-tax table put a **25 bps** control row
    (TW 3.66) beside a **10 bps** broad row (TW 29.27) and called it "one
    column, two constructions". That is 8.0x, of which the construction bought
    about 5.0x and the COST RATE bought the rest. Same-cost pairs are
    **3.66 -> 18.14 at 25 bps** and **8.96 -> 29.27 at 10 bps**;
  * "993,005 rows, 2015-2024" put a 2015-**2026** count under a 2015-2024
    label; 2015-2024 holds **789,277**;
  * event compression was quoted at a stale **127,157 -> 97,949 / 1.298**
    snapshot when the receipt at HEAD says **137,190 -> 105,494 / 1.3005**;
  * the NVIDIA embedder was called ABSENT in a roadmap row whose own cited
    receipt records `status OK, 3 embeddings, dim 2048`;
  * `conviction`'s lead/lag loadings were rounded to "0.66 / 1.50", which
    matches no field of `G7_forward_lanes.json` (0.6072 / 1.3990 joint);
  * the index-hedged long-short was said to hedge "correctly (realised beta
    0.00-0.05)" when four of twenty cells sit at 0.205-0.425;
  * the round-2 fantasy canary was quoted as a single "0/8" when that is the
    END arm alone; FRONT moved one of eight.

THE RULE THIS FILE ENFORCES IS **THE RECEIPT WINS**. Every assertion below
reads the number out of the receipt JSON first and then requires the prose to
carry it, so a doc cannot drift without a red test, and a receipt that is
re-run with different numbers fails here rather than quietly disagreeing with
the paragraph beside it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
NIGHT = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
GROWTH = REPO / "backend" / "data" / "optimus" / "growth_book"

NIGHT_LAB_DOC = DOCS / "BUILD_NIGHT_LAB_2026-09-07.md"
GROWTH_DOC = DOCS / "BUILD_GROWTH_BOOK_2026-09-07.md"
ROADMAP_DOC = DOCS / "ROADMAP_2026-09-04_PROFIT_ENGINE.md"


def _json(p: Path) -> dict:
    if not p.is_file():
        pytest.skip(f"receipt absent on this machine: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _text(p: Path) -> str:
    if not p.is_file():
        pytest.skip(f"doc absent on this machine: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


#: Opening quote marks. A retired number QUOTED in order to be corrected is not
#: the same act as a retired number ASSERTED, and a guard that cannot tell them
#: apart makes every correction unwritable -- which is how a wrong number
#: survives: nobody can afford to name it.
_QUOTE_OPEN = "\"'`“‘"


def _unquoted(text: str, pattern: str) -> list[str]:
    """Matches of `pattern` that are NOT immediately preceded by a quote mark."""
    out = []
    for m in re.finditer(pattern, text):
        before = text[m.start() - 1] if m.start() else ""
        if before not in _QUOTE_OPEN:
            out.append(m.group(0))
    return out


# ------------------------------------------------- 1. the event table's span

def test_event_table_span_and_the_2015_2024_subtotal():
    """993,005 rows span 2015-2026; 789,277 of them are in 2015-2024."""
    cov = _json(NIGHT / "N4_coverage_by_year.json")["by_year"]
    years = sorted(int(y) for y in cov)
    assert (years[0], years[-1]) == (2015, 2026)

    total = sum(int(v["rows"]) for v in cov.values())
    sub = sum(int(v["rows"]) for y, v in cov.items() if 2015 <= int(y) <= 2024)
    assert total == 993_005, total
    assert sub == 789_277, sub

    build = _json(NIGHT / "N4_event_table_build_run01.json")
    assert int(build["rows_written"]) == total

    doc = _text(NIGHT_LAB_DOC)
    assert "993,005 rows" in doc
    assert "789,277" in doc, "the 2015-2024 subtotal must be printed beside the total"
    assert "2015-2026" in doc, "the table's real span must be named"
    # the defect: the whole-table count under a 2015-2024 label. A doc may
    # QUOTE the wrong label in order to correct it; it may not assert it.
    assert not _unquoted(doc, r"993,005 rows,\s*\n?2015-2024"), (
        "993,005 is the 2015-2026 count; it may not be labelled 2015-2024")


# ------------------------------------------------------- 2. event compression

def test_event_compression_counts_come_from_the_receipt():
    c = _json(NIGHT / "N5_event_compression.json")["compression"]
    assert int(c["raw_news_rows"]) == 137_190
    assert int(c["n_canonical_events"]) == 105_494
    assert round(float(c["compression_ratio"]), 4) == 1.3005

    doc = _text(NIGHT_LAB_DOC)
    assert "137,190" in doc and "105,494" in doc and "1.3005" in doc
    # the stale pair may still be NAMED as stale, but never asserted as current.
    assert "127,157 news rows → **97,949" not in doc


# --------------------------------------------------------- 3. the embedder

def test_the_nemotron_embedder_is_reachable_and_no_doc_says_otherwise():
    probe = _json(NIGHT / "N5_event_compression.json")["nemotron_probe"]
    assert probe["status"] == "OK"
    assert int(probe["dim"]) == 2048
    assert int(probe["n_embeddings"]) == 3

    # A doc may DESCRIBE the stale "ABSENT" line as an error (the review and
    # validation files do exactly that); it may not ASSERT it.
    offenders = []
    for p in sorted(DOCS.rglob("*.md")):
        for i, line in enumerate(_text(p).splitlines(), 1):
            if _unquoted(line, r"NVIDIA embedder ABSENT"):
                offenders.append(f"{p.relative_to(REPO)}:{i}")
    assert not offenders, offenders


# ----------------------------------------------- 4. conviction's lead and lag

def test_conviction_lead_lag_loadings_match_the_g7_receipt():
    rows = _json(GROWTH / "G7_forward_lanes.json")["rows"]
    conv = next(r for r in rows if r.get("lane") == "conviction")
    diag = conv["stale_mark_diagnostic"]
    assert round(float(diag["beta_contemporaneous_joint"]), 4) == 0.6072
    assert round(float(diag["beta_on_lagged_market_joint"]), 4) == 1.3990
    assert diag["stale_marks_suspected"] is True

    for doc in (GROWTH_DOC, ROADMAP_DOC):
        t = _text(doc)
        assert "0.6072" in t, doc.name
        assert "1.3990" in t, doc.name
        assert "loads 0.66 on today's market and **1.50" not in t
        assert "loads 0.66 on today's market and 1.50" not in t


# ------------------------------------------- 5. the long-short hedge's beta

def test_long_short_realised_beta_range_is_stated_honestly():
    ls = _json(NIGHT / "N1_construction_books.json")["index_hedged_long_short"]
    betas = [float(v["realised_beta_of_the_hedged_book"]) for v in ls.values()]
    assert len(betas) == 20
    assert round(min(betas), 4) == -0.0605
    assert round(max(betas), 4) == 0.4254
    outside = [b for b in betas if abs(b) > 0.05]
    assert len(outside) == 6, outside
    assert len(betas) - len(outside) == 14

    for doc in (NIGHT_LAB_DOC, ROADMAP_DOC):
        t = _text(doc)
        assert "0.4254" in t or "0.425" in t, doc.name
        assert "14 of 20" in t, doc.name
        assert "hedges correctly (realised β\n0.00–0.05)" not in t
        assert "hedge works (β 0.00-0.05)" not in t


# ----------------------------------------------------- 6. the round-2 canary

def test_round_two_canary_is_reported_per_clause_position():
    r = _json(NIGHT / "N6b_fantasy_exams_round2.json")
    end, front = r["summary_end_position"], r["summary_front_position"]
    assert int(end["canaries_graded"]) == 8 and float(end["canary_rate"]) == 0.0
    assert int(front["canaries_graded"]) == 8 and float(front["canary_rate"]) == 0.125

    doc = _text(NIGHT_LAB_DOC)
    flat = " ".join(doc.split())
    assert "END 0/8, FRONT 1/8" in flat, (
        "both arms of the canary must be printed; a lone 0/8 is the END arm only")
    assert "canary **0/8**;" not in doc


# ------------------------------------------- 7. the construction tax AT COST

#: cell label -> terminal wealth net. Read from the receipt, printed in the doc.
_TAX_CELLS = {
    "revisions|k=50|vw|hold=none|25bps": 3.6586,
    "revisions|k=300|ew|hold=600|25bps": 18.1376,
    "revisions|k=50|vw|hold=none|10bps": 8.96,
    "revisions|k=300|ew|hold=600|10bps": 29.266,
}


def test_the_construction_tax_cells_are_what_the_receipt_says():
    cells = _json(NIGHT / "N1_construction_books.json")["cells"]
    for label, tw in _TAX_CELLS.items():
        assert round(float(cells[label]["terminal_wealth_net"]), 4) == tw, label

    doc = _text(NIGHT_LAB_DOC)
    for s in ("**3.66**", "**18.14**", "**8.96**", "**29.27**"):
        assert s in doc, s
    flat = " ".join(doc.split())
    assert "3.66 → 18.14 at 25 bps" in flat
    assert "8.96 → 29.27 at 10 bps" in flat


def _mixed_cost_tables(text: str) -> list[int]:
    """1-based line numbers of markdown table blocks that put 3.66 on one row
    and 29.27 on ANOTHER row of the same table.

    That shape -- and only that shape -- is the defect: a single table whose
    rows are at different cost rates, read as one column. Prose that NAMES the
    pair in order to disavow it (the review and validation files do) keeps both
    numbers on one line and is not flagged.
    """
    hits: list[int] = []
    block: list[str] = []
    start = 0
    lines = text.splitlines()

    def judge(blk: list[str], first: int) -> None:
        a = {i for i, l in enumerate(blk) if "3.66" in l}
        b = {i for i, l in enumerate(blk) if "29.27" in l}
        if a and b and (a - b) and (b - a):
            hits.append(first + 1)

    for i, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            if not block:
                start = i
            block.append(line)
        else:
            if block:
                judge(block, start)
                block = []
    if block:
        judge(block, start)
    return hits


def test_the_detector_fires_on_the_table_as_it_actually_stood():
    """KNOWN ANSWER. A guard is only worth its line count if it is shown to
    fire on the real case, so the pre-fix table is reproduced verbatim."""
    before = (
        "| book on `revisions` | b | TC | eff. names | TW net | market |\n"
        "|---|---|---|---|---|---|\n"
        "| top-50 VW, 25 bps (the incumbent) | 0.882 | 0.132 | 12.2 | **3.66** | 13.18 |\n"
        "| top-300 EW hold-600, 10 bps | 1.086 | 0.587 | 299.4 | **29.27** | 13.18 |\n"
    )
    assert _mixed_cost_tables(before) == [1]


def test_no_doc_puts_3_66_and_29_27_in_one_table():
    offenders = []
    for p in sorted(DOCS.rglob("*.md")):
        for ln in _mixed_cost_tables(_text(p)):
            offenders.append(f"{p.relative_to(REPO)}:{ln}")
    assert not offenders, (
        "a table mixing the 25 bps control (3.66) with the 10 bps broad book "
        f"(29.27) reads a cost effect as a construction effect: {offenders}")
