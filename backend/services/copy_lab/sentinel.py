"""SILENT_CASH_SENTINEL_v1 -- a refusing lane and a dead lane must never look alike.

THE FOURTEEN DAYS
=================
Both copy-lab lanes refused every run from 2026-08-14 to 2026-08-28 because
`autocrlf` rewrote 247 line endings and the config hash stopped matching the
seed (`FINDING_2026-08-28_A_LINE_ENDING_IS_NOT_A_CONFIGURATION.md`). Nobody
noticed, and the reason is the whole point of this module:

    a lane that REFUSED to run writes    cash 100000, positions {}, last_nav null
    a lane that RAN and found nothing writes cash 100000, positions {}, last_nav null

Identical bytes, opposite meanings. One is a broken engine and the other is a
working engine correctly declining to trade. When the hash bug was fixed a
SECOND stoppage appeared behind it -- the Form 4 source had been stale since
12 August and the 13D source returns zero events -- which had been invisible for
the same reason.

The failure generalises well past copy-lab. `docs/FINDING_2026-08-28_THE_ENGINE_
NEVER_TRADED.md` found no `nav.jsonl` anywhere in the estate: ten arena books,
no NAV rows, and "demonstrated edge is 0%" turned out to mean NO EVIDENCE rather
than evidence of no edge.

WHAT MAKES A STATE READABLE
===========================
A lane must emit enough to distinguish those two worlds without a human reading
code. Six quantities do it:

    ran_at            did the engine execute at all, and when
    refusals          why it declined, by reason and count
    candidates        how many names it CONSIDERED
    forecasts         how many it formed a view on
    source_age_days   the freshest input's age -- a stale source is a stopped one
    nav_rows          whether the book has ever been marked

The classification rule is the inversion of the bug: **absence of activity is
only benign when something positive says the engine ran and chose not to act.**
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.services.copy_lab import lanes as lanes_mod
from backend.services.copy_lab import store

OK, ELEVATED, FAIL = "OK", "ELEVATED", "FAIL"

DORMANT = "DORMANT"
"""Configured but `active: false`, so it is not supposed to have run.

The first version of this sweep classified all 14 lanes and reported the 12
dormant ones as FAIL ("NOT SEEDED"), which is true and useless: seeding is
attended and env-gated by canon, so those lanes are correctly unseeded and
always will be until a human seeds them. Twelve permanent red lines standing
beside two real ones is the `monday_gate_check` failure again -- a guard that
CANNOT go green teaches the reader to skim red. Dormant is its own status and
is not an alarm."""

STALE_SOURCE_DAYS = 5.0
"""A source older than this is treated as stopped. The Form 4 feed sat at 16
days and read as 'no insider buying'."""

QUIET_CYCLES_BEFORE_ELEVATED = 3
"""Consecutive marked sessions with zero candidates before the lane is called
out. One quiet day is a market; three is a pipeline."""


@dataclass
class LaneHealth:
    lane_id: str
    status: str = OK
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def flag(self, status: str, why: str) -> None:
        order = {DORMANT: -1, OK: 0, ELEVATED: 1, FAIL: 2}
        if order[status] > order[self.status]:
            self.status = status
        self.reasons.append(why)


def _age_days(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 86400.0


def _last_receipt(lane_id: str, root: Path | None = None) -> dict | None:
    d = store.lane_dir(lane_id, root) / "receipts"
    if not d.exists():
        return None
    files = sorted(d.glob("*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def inspect_lane(lane_id: str, *, root: Path | None = None,
                 spec=None) -> LaneHealth:
    """One lane's health, derived from what is on disk -- never assumed."""
    h = LaneHealth(lane_id)

    active = True if spec is None else bool(getattr(spec, "active", True))
    h.metrics["active"] = active
    if not active:
        h.status = DORMANT
        h.reasons.append("configured with active: false -- not expected to run. "
                         "Seeding is attended and env-gated, so an unseeded "
                         "dormant lane is the correct state, not a fault.")
        return h

    seeded = store.is_seeded(lane_id, root)
    h.metrics["seeded"] = seeded
    if not seeded:
        h.flag(FAIL, "NOT SEEDED: the lane has no inception record, so nothing "
                     "it later reports can be dated. This is not a quiet lane, "
                     "it is an absent one.")
        return h

    # CONFIG DRIFT -- the exact 14-day failure. Reported as FAIL rather than
    # allowed to surface as a silent refusal inside the runner.
    if spec is not None:
        try:
            store.assert_config_current(spec, root=root)
            h.metrics["config_current"] = True
        except store.ConfigDrift as exc:
            h.metrics["config_current"] = False
            h.flag(FAIL, f"CONFIG DRIFT: {exc}. A lane in this state refuses "
                         "every run and writes a state file identical to a lane "
                         "that simply found nothing.")

    nav = store.read_nav(lane_id, root)
    positions = store.read_positions(lane_id, root)
    signals = store.read_signals(lane_id, root)
    receipt = _last_receipt(lane_id, root)

    h.metrics["nav_rows"] = len(nav)
    h.metrics["n_positions"] = len(positions.get("positions", {}) or {})
    h.metrics["n_signals"] = len(signals)

    nav_age = _age_days(nav[-1].get("date") or nav[-1].get("ts")) if nav else None
    h.metrics["nav_age_days"] = nav_age

    ran_at = (receipt or {}).get("ran_at") or (receipt or {}).get("at")
    ran_age = _age_days(ran_at)
    h.metrics["last_run_age_days"] = ran_age
    h.metrics["candidates"] = (receipt or {}).get("n_candidates")
    h.metrics["forecasts"] = (receipt or {}).get("n_forecasts")
    h.metrics["refusals"] = (receipt or {}).get("refusals") or {}

    # THE CORE RULE. Zero positions is only benign with positive evidence that
    # the engine ran and declined.
    if h.metrics["n_positions"] == 0:
        if receipt is None:
            h.flag(FAIL, "ZERO POSITIONS AND NO RECEIPT: nothing on disk says "
                         "the engine ever ran. An empty book is being read as a "
                         "decision when it may be a dead process.")
        elif ran_age is not None and ran_age > STALE_SOURCE_DAYS:
            h.flag(FAIL, f"ZERO POSITIONS and the last run was {ran_age:.1f} days "
                         f"ago. A stopped engine and a flat book are the same "
                         f"file; this one is stopped.")
        else:
            h.flag(ELEVATED, "zero positions, but a recent receipt exists -- "
                             "this is a REFUSAL, which is a finding, not a fault")

    if not nav:
        h.flag(FAIL, "NO NAV ROWS EVER: the book has never been marked, so it "
                     "has no track record. 'Edge is 0%' across this estate meant "
                     "exactly this and was read as a measured zero.")
    elif nav_age is not None and nav_age > STALE_SOURCE_DAYS:
        h.flag(ELEVATED, f"NAV last marked {nav_age:.1f} days ago")

    for name, ts in ((receipt or {}).get("sources") or {}).items():
        age = _age_days(ts)
        if age is None:
            h.flag(ELEVATED, f"source {name} has no usable timestamp")
        elif age > STALE_SOURCE_DAYS:
            h.flag(FAIL, f"SOURCE STALE: {name} is {age:.1f} days old. A stale "
                         f"source does not read as an error, it reads as 'no "
                         f"events' -- which is how the Form 4 feed hid for 16 days.")

    return h


def sweep(*, root: Path | None = None, config_path: Path | None = None
          ) -> list[LaneHealth]:
    """Every configured lane, healthiest last so the tail of the log is the problem."""
    try:
        specs = lanes_mod.load_lanes(config_path)
    except Exception as exc:                                    # noqa: BLE001
        h = LaneHealth("<config>")
        h.flag(FAIL, f"lane configuration unreadable: {type(exc).__name__}: {exc}")
        return [h]
    out = [inspect_lane(lid, root=root, spec=spec) for lid, spec in specs.items()]
    if not out:
        h = LaneHealth("<none>")
        h.flag(FAIL, "NO LANES CONFIGURED: a sweep that inspects nothing returns "
                     "all-clear, which is the failure this module is named for.")
        return [h]
    rank = {FAIL: 0, ELEVATED: 1, OK: 2, DORMANT: 3}
    return sorted(out, key=lambda x: rank[x.status], reverse=True)


def report(healths: list[LaneHealth]) -> str:
    lines = []
    for h in healths:
        lines.append(f"  [{h.status:<8}] {h.lane_id}")
        for k in ("nav_rows", "n_positions", "candidates", "forecasts",
                  "last_run_age_days", "nav_age_days"):
            if k in h.metrics and h.metrics[k] is not None:
                v = h.metrics[k]
                lines.append(f"      {k:<20} "
                             f"{v:.1f}" if isinstance(v, float) else
                             f"      {k:<20} {v}")
        for r in h.reasons:
            lines.append(f"      -> {r}")
    live = [h for h in healths if h.status != DORMANT]
    worst = max((h.status for h in live),
                key=lambda s: {OK: 0, ELEVATED: 1, FAIL: 2}[s]) if live else OK
    lines.append(f"  WORST (of {len(live)} active, "
                 f"{len(healths) - len(live)} dormant): {worst}")
    return "\n".join(lines)
