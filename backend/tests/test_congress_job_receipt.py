"""The congress collector's failures reach its receipt, and its writes are on it.

2026-09-20. Fifteen production receipts for `pi_congress_collect` (2026-09-01
to 09-18) read `status: ran, exception: null, writes: null`, 0.3 s each, while
the local and (by every available sign) the production PIT store held zero
`congress_score:*` rows: the job body caught every exception itself, one hop
below `@receipted()`, so a source failure and a clean success produced the
same record. The slot also ran at 07:30 ET -- eleven hours into FMP's UTC
quota day, after other callers had already marked it exhausted.

Three things are pinned here: a raise reaches the receipt; a success puts what
it wrote on the receipt; the slot is the top of the UTC day.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.services import job_receipts as JR


@pytest.fixture(autouse=True)
def _tmp_ledger(monkeypatch, tmp_path):
    from backend import config as _config
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    return tmp_path


def _receipts(job: str) -> list[dict]:
    return JR.read(job, limit=50)["receipts"]


def test_a_source_failure_is_a_raised_receipt(monkeypatch):
    from backend.services.portfolio_intelligence import congress_collector as CC
    from backend.services.portfolio_intelligence import scheduler as S

    def _boom(*a, **k):
        raise RuntimeError("FMP quota exhausted for today (HTTP 402)")

    monkeypatch.setattr(CC, "collect_congress_scores", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(S._congress_morning_collect())
    rec = _receipts("congress_morning_collect")[0]
    assert rec["status"] == "raised"
    assert "402" in rec["exception"]


def test_a_success_puts_its_writes_on_the_receipt(monkeypatch):
    from backend.services.portfolio_intelligence import congress_collector as CC
    from backend.services.portfolio_intelligence import scheduler as S

    monkeypatch.setattr(CC, "collect_congress_scores",
                        lambda *a, **k: {"status": "ok", "n": 12, "nonzero": 3,
                                         "written": 12, "throttled": 0})
    out = asyncio.run(S._congress_morning_collect())
    assert out["n"] == 12
    rec = _receipts("congress_morning_collect")[0]
    assert rec["status"] == "ran" and rec["exception"] is None
    assert rec["writes"]["n"] == 12 and rec["writes"]["nonzero"] == 3


def test_the_slot_is_the_top_of_the_utc_quota_day():
    """`fmp_budget` rolls its day at 00:00 UTC; the collector must draw its
    priority slice before anything else has spent. The cron is read from the
    scheduler source rather than a live scheduler so the test needs no
    jobstore."""
    import ast
    import inspect
    from backend.services.portfolio_intelligence import scheduler as S

    src = inspect.getsource(S)
    tree = ast.parse(src)
    found = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_job"
                and node.args and getattr(node.args[0], "id", "") == "_congress_morning_collect"):
            trig = node.args[1]
            kw = {k.arg: getattr(k.value, "value", None) for k in trig.keywords}
            found = kw
    assert found is not None, "the congress job is not scheduled"
    assert found["timezone"] == "UTC"
    assert (found["hour"], found["minute"]) == (0, 40)


def test_member_identity_survives_the_aggregate():
    from backend.services.congress_trades import compute_congress_scores
    def _t(member, ttype="Purchase"):
        return {"chamber": "senate", "member_id": member, "symbol": "AAA",
                "asset_type": "Stock", "type": ttype,
                "amount": "$1,001 - $15,000", "transaction_date": "2026-06-01",
                "disclosure_date": "2026-07-01"}

    trades = [_t("m1"), _t("m2"), _t("m3", "Sale (Full)")]
    score, payload = compute_congress_scores(trades, as_of="2026-07-11")["AAA"]
    assert score == 1.0
    assert payload["buyer_ids"] == ["m1", "m2"]
    assert payload["seller_ids"] == ["m3"]
