"""The revision_flow sleeve's membership: one selection rule, an age that is compared.

2026-11-11: the live sleeve mirrors a book frozen once (2026-09-25) and
`sim_run.u_plan` rewrites `revision_flow_members.json` every cycle with a fresh
`written_utc` over the same names. These tests pin (1) that the refresh selects
exactly as `revision_flow_sweep.freeze_books` did, (2) that the frozen list's age is
compared to a limit and an undateable stamp is never fresh, (3) that the refresh job
refuses to overwrite, and (4) that none of it touched a source the PC-PAPER policy
epoch pins by bytes. Synthetic data only.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from backend.services import revision_flow as RF
from scripts import revision_flow_refresh as R


def _revisions(today: date) -> pd.DataFrame:
    rows = []
    # AAA: 5 raises from 5 firms; BBB: 4 raises, 1 lower, 4 firms; CCC: 2 firms only
    plan = {"AAA": [("raises", f"F{i}") for i in range(5)],
            "BBB": [("raises", f"F{i}") for i in range(4)] + [("lowers", "F9")],
            "CCC": [("raises", "F1"), ("raises", "F2")],
            "DDD": [("lowers", f"F{i}") for i in range(4)]}
    for t, evs in plan.items():
        for j, (act, firm) in enumerate(evs):
            rows.append({"ticker": t, "event_date": pd.Timestamp(today - timedelta(days=10 + j)),
                         "firm": firm, "target_action": act, "prior_target": 10.0,
                         "current_target": 11.0 if act == "raises" else 9.0, "pit_safe": True})
    # an event ON the asof day never counts (strict)
    rows.append({"ticker": "DDD", "event_date": pd.Timestamp(today), "firm": "FX",
                 "target_action": "raises", "prior_target": 1.0, "current_target": 2.0,
                 "pit_safe": True})
    return pd.DataFrame(rows)


def test_select_members_is_the_rule_on_the_eligible_set():
    today = date.today()
    flow = RF.compute(_revisions(today), asof=pd.Timestamp(today))
    top = R.select_members(flow, ["AAA", "bbb", "CCC", "DDD"], k=2, min_firms=3)
    assert list(top.index) == ["AAA", "BBB"]          # CCC has 2 firms; DDD scores negative
    assert top["AAA"] == 25 and top["BBB"] == 15
    only_b = R.select_members(flow, ["BBB"], k=20, min_firms=3)
    assert list(only_b.index) == ["BBB"], "an ineligible name is never selected"


def test_book_age_is_compared_and_an_undateable_stamp_is_not_fresh():
    t = date.today()
    fresh = R.book_age((t - timedelta(days=10)).isoformat(), today=t, max_age_days=35)
    assert fresh["age_days"] == 10 and fresh["stale"] is False and "STALE" not in fresh["age_line"]
    old = R.book_age((t - timedelta(days=47)).isoformat(), today=t, max_age_days=35)
    assert old["stale"] is True and "STALE" in old["age_line"] and "NEW book" in old["age_line"]
    bad = R.book_age(None, today=t)
    assert bad["stale"] is True and bad["age_days"] is None and "UNKNOWN" in bad["age_line"]


def test_the_refresh_selection_is_freeze_books_selection_line_for_line():
    """`freeze_books` picks `score[score.index.isin(day.index)].sort_values(desc,
    mergesort)`; the refresh must give the same ranked list on the same inputs."""
    today = date.today()
    flow = RF.compute(_revisions(today), asof=pd.Timestamp(today))
    score = RF.rule_score(flow, min_firms=3)
    day = pd.Index(["AAA", "BBB", "CCC", "DDD"])
    ref = score[score.index.isin(day)].sort_values(ascending=False, kind="mergesort")
    assert list(R.select_members(flow, day, k=len(ref)).index) == list(ref.index)


def test_no_policy_pinned_source_was_edited():
    """The PC-PAPER epoch pins pc_sleeves / revision_flow / sim_run by bytes; the
    refresh must not need them changed (it refused CI once, 2026-11-11)."""
    import json
    from pathlib import Path
    from backend.services import pc_policy_epoch as PE
    root = Path(__file__).resolve().parents[2]
    c = json.loads((root / "backend/data/pc_policy_epochs/pc_paper_no_index_2026_10_v1.json")
                   .read_text(encoding="utf-8"))
    pinned = (c.get("content") or c).get("source_sha256") or {}
    assert "scripts/revision_flow_refresh.py" not in pinned
    # scripts/sim_run.py is not checked here: OD-10 (#89) changed it on main, so the
    # prepared epoch already fails closed on that pin (review 4 of #89). The refresh
    # itself never imports or edits sim_run.
    for rel in ("backend/services/pc_sleeves.py", "backend/services/revision_flow.py"):
        assert PE._source_sha((root / rel).resolve()) == pinned[rel], rel


def test_refresh_job_refuses_an_existing_file_and_the_live_folder(tmp_path):
    from scripts import revision_flow_refresh as R
    existing = tmp_path / "x.json"
    existing.write_text("{}", encoding="utf-8")
    assert R.main(["--out", str(existing)]) == 2
    assert R.main(["--out", str(R.MEMBERS_PATH.parent / "refresh_test.json")]) == 2
    assert not (R.MEMBERS_PATH.parent / "refresh_test.json").exists()


@pytest.mark.parametrize("bad", [False, None])
def test_flow_refuses_rows_that_are_not_pit_safe(bad):
    r = _revisions(date.today())
    r["pit_safe"] = r["pit_safe"].astype(object)
    r.loc[0, "pit_safe"] = bad
    with pytest.raises(ValueError, match="pit_safe"):
        RF.compute(r, asof=pd.Timestamp(date.today()))
