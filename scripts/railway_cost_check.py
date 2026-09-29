"""railway_cost_check -- what the Railway workspace is costing, from Railway's own usage API.

One call answers "what is Railway going to charge this month, and who is it?"
without opening the dashboard. It reads:

  * the workspace plan and billing period (`workspace.customer`),
  * usage so far in the period (`customer.currentUsage`, dollars),
  * the last N days of usage per service (`usage(groupBy: SERVICE_ID)`),

prices the per-service numbers at Railway's published rates (printed on the
receipt, because a rate is an INPUT and a rate change must not silently change
the conclusion), projects a monthly run-rate, and applies the plan floor
(Pro: $20 fee that INCLUDES $20 of usage, so the bill is max($20, usage)).

Why this exists (2026-09-28): the owner saw a ~$60 bill for Aug 26 -> Sep 26
and asked for it to come down. The measurement that answered it
(`docs/NOTE_2026-09-28_RAILWAY_COST.md`) took an hour of CLI and GraphQL by
hand; this makes the same reading one line, monthly.

Privacy: the receipt carries service ids and dollar figures, so it is written
under `backend/data/optimus/local_pc/railway/` (gitignored). The printed line
names services only by name.

Auth: `RAILWAY_API_TOKEN` if set, else the Railway CLI's own stored login
(`~/.railway/config.json`). The token is never printed or written.

Usage:
    python -m scripts.railway_cost_check              # 7-day run-rate
    python -m scripts.railway_cost_check --days 14
    python -m scripts.railway_cost_check --line-only  # just the Telegram line

Exit code: 0 on a reading, 2 when the API could not be read (no token, HTTP
error, GraphQL error). An unreadable API is reported as UNKNOWN, never as $0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

ROOT = Path(__file__).resolve().parent.parent
RECEIPT_DIR = ROOT / "backend" / "data" / "optimus" / "local_pc" / "railway" / "cost_checks"
API_URL = "https://backboard.railway.com/graphql/v2"

#: Railway published rates (docs.railway.com/reference/pricing/plans, read
#: 2026-09-26/28). The usage API returns GB-minutes / vCPU-minutes for
#: memory, CPU and disk, and GB for egress.
MINUTES_PER_MONTH = 43_200  # Railway prices a month as 30 days
PRICE_PER_UNIT: dict[str, float] = {
    "MEMORY_USAGE_GB": 10.0 / MINUTES_PER_MONTH,   # $10 / GB-month
    "CPU_USAGE": 20.0 / MINUTES_PER_MONTH,         # $20 / vCPU-month
    "DISK_USAGE_GB": 0.15 / MINUTES_PER_MONTH,     # $0.15 / GB-month (volumes)
    "NETWORK_TX_GB": 0.05,                         # $0.05 / GB egress
}
#: plan -> (monthly fee, usage included in that fee)
PLAN_FLOOR: dict[str, tuple[float, float]] = {"PRO": (20.0, 20.0), "HOBBY": (5.0, 5.0)}


class Client(Protocol):
    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]: ...


class ApiError(RuntimeError):
    pass


def _token() -> str | None:
    tok = os.getenv("RAILWAY_API_TOKEN")
    if tok:
        return tok
    cfg = Path.home() / ".railway" / "config.json"
    try:
        user = json.loads(cfg.read_text(encoding="utf-8")).get("user") or {}
    except (OSError, ValueError):
        return None
    return user.get("accessToken") or user.get("token")


@dataclass
class HttpClient:
    token: str
    url: str = API_URL

    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(self.url, data=body, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "aegis-railway-cost-check/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                out = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ApiError(f"HTTP {e.code}") from None
        except Exception as e:  # noqa: BLE001
            raise ApiError(f"unreachable: {type(e).__name__}") from None
        if out.get("errors"):
            raise ApiError("graphql: " + "; ".join(str(x.get("message")) for x in out["errors"])[:300])
        return out.get("data") or {}


Q_ME = "query { me { workspaces { id name plan } } }"
Q_WORKSPACE = """query($ws: String!) { workspace(workspaceId: $ws) { name plan
  customer { billingPeriod { start end } currentUsage } } }"""
Q_PROJECTS = """query($ws: String!) { projects(workspaceId: $ws) { edges { node { id name
  services { edges { node { id name } } } } } } }"""
Q_USAGE = """query($ws: String!, $s: DateTime!, $e: DateTime!) {
  usage(workspaceId: $ws, measurements: [MEMORY_USAGE_GB, CPU_USAGE, DISK_USAGE_GB, NETWORK_TX_GB],
        startDate: $s, endDate: $e, groupBy: [SERVICE_ID, PROJECT_ID]) {
    measurement value tags { serviceId projectId } } }"""


@dataclass
class Reading:
    run_id: str
    now_utc: str
    workspace: str
    plan: str
    period_start: str | None
    period_end: str | None
    usage_so_far_usd: float | None
    window_days: float
    per_service_usd_window: dict[str, float] = field(default_factory=dict)
    per_service_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    run_rate_usd_month: float = 0.0
    projected_period_usage_usd: float | None = None
    expected_bill_usd: float | None = None
    prices: dict[str, float] = field(default_factory=lambda: dict(PRICE_PER_UNIT))
    plan_floor: tuple[float, float] | None = None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def check(client: Client, *, now: datetime | None = None, days: float = 7.0,
          run_id: str | None = None) -> Reading:
    """Read the workspace and price the last `days` of usage per service."""
    now = now or datetime.now(timezone.utc)
    me = client.query(Q_ME)
    workspaces = ((me.get("me") or {}).get("workspaces")) or []
    if not workspaces:
        raise ApiError("no workspace visible to this token")
    ws = workspaces[0]
    wsd = (client.query(Q_WORKSPACE, {"ws": ws["id"]}).get("workspace")) or {}
    cust = wsd.get("customer") or {}
    period = cust.get("billingPeriod") or {}
    plan = str(wsd.get("plan") or ws.get("plan") or "UNKNOWN").upper()

    names: dict[str, str] = {}
    for pe in ((client.query(Q_PROJECTS, {"ws": ws["id"]}).get("projects") or {}).get("edges") or []):
        p = pe["node"]
        for se in (p.get("services") or {}).get("edges") or []:
            names[se["node"]["id"]] = f"{p['name']}/{se['node']['name']}"

    start = now - timedelta(days=days)
    rows = client.query(Q_USAGE, {"ws": ws["id"], "s": _iso(start), "e": _iso(now)}).get("usage") or []
    breakdown: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        m = r.get("measurement")
        if m not in PRICE_PER_UNIT:
            continue
        sid = (r.get("tags") or {}).get("serviceId")
        label = names.get(sid) or f"(deleted service {str(sid)[:8]})"
        breakdown[label][m] += float(r.get("value") or 0.0) * PRICE_PER_UNIT[m]
    per_service = {k: round(sum(v.values()), 4) for k, v in breakdown.items()}
    window_total = sum(per_service.values())
    run_rate = window_total * 30.0 / days if days > 0 else 0.0

    so_far = cust.get("currentUsage")
    so_far = float(so_far) if so_far is not None else None
    ps, pe_ = _parse(period.get("start")), _parse(period.get("end"))
    projected = None
    if so_far is not None and ps and pe_:
        remaining_days = max(0.0, (pe_ - now).total_seconds() / 86400.0)
        projected = so_far + run_rate * remaining_days / 30.0
    floor = PLAN_FLOOR.get(plan)
    basis = projected if projected is not None else run_rate
    bill = None
    if floor:
        fee, included = floor
        bill = fee + max(0.0, basis - included)

    return Reading(
        run_id=run_id or f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}",
        now_utc=_iso(now), workspace=str(wsd.get("name") or ws.get("name")), plan=plan,
        period_start=period.get("start"), period_end=period.get("end"),
        usage_so_far_usd=None if so_far is None else round(so_far, 2),
        window_days=days,
        per_service_usd_window=dict(sorted(per_service.items(), key=lambda kv: -kv[1])),
        per_service_breakdown={k: {m: round(x, 4) for m, x in v.items()} for k, v in breakdown.items()},
        run_rate_usd_month=round(run_rate, 2),
        projected_period_usage_usd=None if projected is None else round(projected, 2),
        expected_bill_usd=None if bill is None else round(bill, 2),
        plan_floor=floor,
    )


def one_line(r: Reading, top: int = 3) -> str:
    """The Telegram `report` line: bill, run-rate, the biggest services."""
    scale = 30.0 / r.window_days if r.window_days else 0.0
    tops = ", ".join(f"{k.split('/')[-1]} ${v * scale:.0f}" for k, v in list(r.per_service_usd_window.items())[:top])
    bill = "unknown" if r.expected_bill_usd is None else f"${r.expected_bill_usd:.0f}"
    so_far = "?" if r.usage_so_far_usd is None else f"${r.usage_so_far_usd:.2f}"
    end = (r.period_end or "?")[:10]
    return (f"railway: bill ~{bill} this period (to {end}; {r.plan}); usage so far {so_far}, "
            f"run-rate ${r.run_rate_usd_month:.0f}/mo over {r.window_days:g}d; top {tops}")


def write_receipt(r: Reading, out_dir: Path = RECEIPT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"railway_cost_{r.run_id}.json"
    tmp = path.with_suffix(".json.tmp")
    payload = dict(r.__dict__)
    payload["line"] = one_line(r)
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))  # verify before replace
    os.replace(tmp, path)
    return path


def main(argv: list[str] | None = None, *, client_factory: Callable[[], Client | None] | None = None,
         out_dir: Path = RECEIPT_DIR) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=7.0, help="run-rate window (default 7)")
    ap.add_argument("--line-only", action="store_true")
    a = ap.parse_args(argv)
    if client_factory is None:
        tok = _token()
        client: Client | None = HttpClient(tok) if tok else None
    else:
        client = client_factory()
    if client is None:
        print("railway: UNKNOWN -- no Railway token (set RAILWAY_API_TOKEN or `railway login`)")
        return 2
    try:
        r = check(client, days=a.days)
    except ApiError as e:
        print(f"railway: UNKNOWN -- API not read ({e}); that is not $0")
        return 2
    path = write_receipt(r, out_dir)
    if a.line_only:
        print(one_line(r))
        return 0
    print(one_line(r))
    for k, v in r.per_service_usd_window.items():
        print(f"  {k:40s} ${v:7.2f} in {a.days:g}d  -> ${v * 30 / a.days:7.2f}/mo")
    print(f"receipt: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
