"""scripts.railway_cost_check against a fake Railway API -- offline, dates derived from today."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts import railway_cost_check as rcc


class FakeClient:
    """Answers the four queries the script makes; usage rows are in API units (GB-min etc.)."""

    def __init__(self, now: datetime, *, plan: str = "PRO", so_far: float | None = 3.0,
                 usage: list[dict[str, Any]] | None = None, fail: bool = False):
        self.now, self.plan, self.so_far, self.fail = now, plan, so_far, fail
        self.usage = usage if usage is not None else []
        self.calls: list[tuple[str, dict]] = []

    def query(self, query: str, variables: dict | None = None) -> dict:
        self.calls.append((query, variables or {}))
        if self.fail:
            raise rcc.ApiError("HTTP 401")
        if "me {" in query:
            return {"me": {"workspaces": [{"id": "ws1", "name": "W", "plan": self.plan}]}}
        if "workspace(" in query:
            start = self.now - timedelta(days=2)
            return {"workspace": {"name": "W", "plan": self.plan, "customer": {
                "billingPeriod": {"start": start.isoformat(), "end": (start + timedelta(days=30)).isoformat()},
                "currentUsage": self.so_far}}}
        if "projects(" in query:
            return {"projects": {"edges": [{"node": {"id": "p1", "name": "proj", "services": {"edges": [
                {"node": {"id": "s-web", "name": "web"}}, {"node": {"id": "s-loop", "name": "loop"}}]}}}]}}
        if "usage(" in query:
            return {"usage": self.usage}
        raise AssertionError(query)


def _row(m: str, v: float, sid: str) -> dict:
    return {"measurement": m, "value": v, "tags": {"serviceId": sid, "projectId": "p1"}}


def _gb_minutes(gb: float, days: float) -> float:
    return gb * days * 1440


def test_prices_a_week_and_projects_the_month():
    now = datetime.now(timezone.utc)
    usage = [
        _row("MEMORY_USAGE_GB", _gb_minutes(1.0, 7), "s-loop"),   # 1 GB all week -> $10/mo
        _row("CPU_USAGE", _gb_minutes(0.1, 7), "s-web"),          # 0.1 vCPU all week -> $2/mo
        _row("DISK_USAGE_GB", _gb_minutes(2.0, 7), "s-loop"),     # 2 GB volume -> $0.30/mo
        _row("NETWORK_TX_GB", 0.2, "s-web"),                      # $0.01
    ]
    r = rcc.check(FakeClient(now, usage=usage), now=now, days=7)
    assert r.plan == "PRO"
    assert list(r.per_service_usd_window)[0] == "proj/loop"  # biggest first
    assert r.run_rate_usd_month == pytest.approx(10 + 2 + 0.3 + 0.01 * 30 / 7, abs=0.02)
    # 3.00 so far + 28 remaining days at the run-rate
    assert r.projected_period_usage_usd == pytest.approx(3.0 + r.run_rate_usd_month * 28 / 30, abs=0.05)
    # Pro: $20 includes $20 usage, so a projected ~$14.5 is billed at the floor
    assert r.expected_bill_usd == pytest.approx(20.0)


def test_bill_above_the_floor_is_fee_plus_overage():
    now = datetime.now(timezone.utc)
    usage = [_row("MEMORY_USAGE_GB", _gb_minutes(5.0, 7), "s-loop")]  # $50/mo
    r = rcc.check(FakeClient(now, so_far=0.0, usage=usage), now=now, days=7)
    assert r.expected_bill_usd == pytest.approx(20 + (50 * 28 / 30 - 20), abs=0.1)


def test_window_is_derived_from_now_not_a_literal_date():
    now = datetime.now(timezone.utc)
    fc = FakeClient(now)
    rcc.check(fc, now=now, days=7)
    (_, v), = [c for c in fc.calls if "usage(" in c[0]]
    assert v["e"] == rcc._iso(now)
    assert v["s"] == rcc._iso(now - timedelta(days=7))


def test_a_deleted_service_is_named_not_dropped():
    now = datetime.now(timezone.utc)
    usage = [_row("DISK_USAGE_GB", _gb_minutes(1.0, 7), "gone1234-xxxx")]
    r = rcc.check(FakeClient(now, usage=usage), now=now, days=7)
    assert any(k.startswith("(deleted service gone1234") for k in r.per_service_usd_window)


def test_line_and_receipt(tmp_path: Path):
    now = datetime.now(timezone.utc)
    usage = [_row("MEMORY_USAGE_GB", _gb_minutes(1.0, 7), "s-loop")]
    r = rcc.check(FakeClient(now, usage=usage), now=now, days=7, run_id="t1")
    line = rcc.one_line(r)
    assert line.startswith("railway: bill ~$20 this period")
    assert "loop $10" in line and "\n" not in line
    p = rcc.write_receipt(r, tmp_path)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert p.name == "railway_cost_t1.json" and d["line"] == line
    assert d["prices"]["MEMORY_USAGE_GB"] == pytest.approx(10 / 43200)


def test_unreadable_api_is_unknown_not_zero(tmp_path: Path, capsys):
    now = datetime.now(timezone.utc)
    rc = rcc.main([], client_factory=lambda: FakeClient(now, fail=True), out_dir=tmp_path)
    assert rc == 2
    assert "UNKNOWN" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_no_token_is_unknown(tmp_path: Path, capsys):
    rc = rcc.main([], client_factory=lambda: None, out_dir=tmp_path)
    assert rc == 2 and "UNKNOWN" in capsys.readouterr().out


def test_main_writes_a_receipt_with_a_run_id(tmp_path: Path, capsys):
    now = datetime.now(timezone.utc)
    rc = rcc.main(["--line-only"], client_factory=lambda: FakeClient(now), out_dir=tmp_path)
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("railway: ") and len(out.splitlines()) == 1
    files = list(tmp_path.glob("railway_cost_*.json"))
    assert len(files) == 1
