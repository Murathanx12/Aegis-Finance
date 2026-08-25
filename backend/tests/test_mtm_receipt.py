"""Every mark-to-market attempt leaves a dated receipt, including the ones
that decided to do nothing.

WHY. `paper_nav` was missing 2026-08-05, 08-06 and 08-19 on all three reference
lanes that carry NAV data (conservative, balanced, aggressive — identical
dates on each, so the cause is the JOB, not any lane), and 2026-08-24 makes a
fourth. About one gap a fortnight in an otherwise complete 53-day series. Diagnosing it was impossible: `_hourly_mtm` has two early
returns that logged at DEBUG (below production level) and wrote nothing, so a
job that skipped and a job that ran and failed left identical evidence, which
is to say none.

`pi_ledger_resolve` had already established the principle in its own docstring
— *a result, written down, not an inference from silence*. This applies it to
the job that actually persists NAV.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config as _config  # noqa: E402
from backend.services.portfolio_intelligence import scheduler as S  # noqa: E402


def _receipts(d: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((d / "mtm_receipts").glob("*.json"))]


def test_marked_run_writes_a_receipt_naming_the_lanes(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    S._write_mtm_receipt("marked", results={"balanced": 10_000.0,
                                            "aggressive": None})
    (r,) = _receipts(tmp_path)
    assert r["job"] == "pi_hourly_mtm"
    assert r["status"] == "marked"
    assert r["marked"] == ["balanced"]
    assert r["failed"] == ["aggressive"]
    assert r["n_marked"] == 1 and r["n_failed"] == 1
    assert r["did_not_mark"] is False


@pytest.mark.parametrize("status,reason", [
    ("skipped", "within 50 minutes of the last mark"),
    ("skipped", "cached market_data_timestamp stale"),
    ("all_lanes_failed", "no lane returned a NAV"),
    ("raised", "RuntimeError: boom"),
])
def test_every_non_marking_outcome_is_written_down(tmp_path, monkeypatch,
                                                   status, reason):
    """A skip is a RESULT. This is the whole point of the receipt."""
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    S._write_mtm_receipt(status, reason)
    (r,) = _receipts(tmp_path)
    assert r["status"] == status
    assert r["reason"] == reason
    assert r["did_not_mark"] is True
    assert r["expected_nav_date"]          # so the gap is attributable to a day


def test_receipt_failure_never_breaks_the_mark(tmp_path, monkeypatch):
    """A receipt that cannot be written must not take down the marking it
    describes — the same rule `_write_resolver_receipt` follows."""
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR",
                        tmp_path / "nope" / "\0bad")
    S._write_mtm_receipt("marked", results={"balanced": 1.0})   # must not raise


def test_both_silent_early_returns_now_write_one():
    """Pins the two paths that made the gaps undiagnosable. A future edit that
    adds a third early return should fail here until it writes a receipt."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    i = src.index("async def _hourly_mtm")
    body = src[i:src.index("async def _options_pit_capture")]
    returns = body.count("        return")
    receipts = body.count("_write_mtm_receipt(")
    assert returns <= receipts, (
        f"{returns} early return(s) in _hourly_mtm but only {receipts} "
        f"receipt call(s) — a path that returns without writing one is a gap "
        f"nobody will be able to diagnose")
    assert "logger.debug" not in body, (
        "an MTM decision logged at DEBUG is invisible in production")


def test_endpoint_exposes_the_new_receipt_kind():
    """A receipt nobody can read is barely better than the log line it
    replaced — the endpoint's own words."""
    src = (Path(__file__).resolve().parents[1] / "routers"
           / "optimus_ledger.py").read_text(encoding="utf-8")
    assert "pi_hourly_mtm" in src and "mtm_receipts" in src
