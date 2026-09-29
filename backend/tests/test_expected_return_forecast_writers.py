"""E[r] names every forecast writer in the ledger, READ or NOT READ BY DESIGN
(2026-09-29). `source:` claims (the news reader) have no code path into the
plan, on purpose until the owner decides; the receipt now says so every night."""
from __future__ import annotations

from datetime import date

from backend.services import expected_return as ER

ASOF = date.today().isoformat()      # derived, never a literal calendar moment


def _rows():
    return ([{"specialist": "investigator:evidence_v3", "made_at": "2026-08-30T01:00:00+00:00",
              "probability": 0.55, "ticker": "AAA"}]
            + [{"specialist": "source:dowjones/claims_v1", "made_at": f"2026-08-3{i}T01:00:00+00:00",
                "probability": 0.6, "ticker": "BBB"} for i in range(2)]
            + [{"specialist": "mystery:x", "made_at": "2026-08-29T00:00:00+00:00"}])


def test_every_writer_in_the_ledger_is_listed_with_a_status_and_reason():
    w = {x["prefix"]: x for x in ER.forecast_writers(_rows())}
    assert w["investigator:"]["status"] == "READ"
    assert w["source:"]["status"] == "NOT READ BY DESIGN"
    assert w["source:"]["n_rows"] == 2 and "owner" in w["source:"]["why"]
    assert w["source:"]["writer"] == "source_claims"
    assert w["mystery:"]["status"].startswith("NOT READ") and w["mystery:"]["why"]
    assert "thesis_card:" not in w                       # only writers present


def test_the_receipt_and_its_print_carry_the_omission(tmp_path):
    src = ER.Sources(label="test", predictions=_rows())
    view = ER.build(ASOF, ["AAA", "BBB"], src, out_dir=tmp_path)
    import json
    rec = json.loads(open(view["path"], encoding="utf-8").read())
    st = {x["prefix"]: x["status"] for x in rec["forecast_writers"]}
    assert st["source:"] == "NOT READ BY DESIGN" and st["investigator:"] == "READ"
    txt = ER.format_top(view)
    assert "forecast writer source: (2 rows): NOT READ BY DESIGN" in txt


def test_the_read_set_is_exactly_what_build_consumes():
    """If a new prefix is wired into E[r], FORECAST_GRADED must name it, or the
    receipt would call a read writer unread."""
    assert set(ER.FORECAST_GRADED.values()) == {"investigator:", "thesis_card:"}
    assert not set(ER.NOT_READ_BY_DESIGN) & set(ER.FORECAST_GRADED.values())
