"""THE FLEET'S END-OF-DAY AUDIT: one row per account, read-only (C26, 2026-10-07).

    python -m scripts.fleet_eod_audit                 # every fleet role, trigger=manual
    (and the Preclose pass runs it as its LAST step: trigger=preclose_pass)

WHY
===
Two of our own hackathon failures had the same shape: an account nobody was
watching. hack3's key started answering 401 on 2026-09-22 and its nine
positions have been unreadable since; the Railway loops drifted for days
before anyone read their logs. The winners (Autobelay) ran an automated
end-of-day critique per account. This is the deterministic half of that: a
row per account, every day, that says what is held, whether every held name
has its stop, whether the broker agrees with our own record, what the worst
case is in dollars -- and NAMES a dead credential instead of skipping it.

WHAT IT NEVER DOES
==================
It places nothing and cancels nothing. The venue it builds is wrapped in a
transport that REFUSES every method but GET, so the guarantee is structural,
not a promise in a docstring.

THE ROW (schema `fleet_eod_audit/1`, `fleet_manager/eod_audit/audit.jsonl`)
=========================================================================
status  OK | DEGRADED | CREDENTIAL_INVALID | NO_CREDENTIAL | UNREADABLE | ERROR
        DEGRADED when: a held long equity name lacks a stop for its full
        quantity, the broker disagrees with `state/<role>.json` + fills since,
        the grades ledger disagrees with the broker's previous-close equity,
        cash is negative, or shares are short.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from backend import config as _cfg
from backend.services import fleet_manager as FM

SCHEMA = "fleet_eod_audit/1"
EXAMPLES = 5


class EodAuditRefusal(FM.FleetRefusal):
    """The audit will not write a row it cannot support (no roles, a write verb)."""


def audit_path(base: Optional[Path] = None) -> Path:
    return FM.root(base) / "eod_audit" / "audit.jsonl"


def readonly_transport(inner: Callable) -> Callable:
    """Every non-GET is refused before it reaches the network."""
    def t(method: str, url: str, headers: dict, body: Optional[bytes]):
        if str(method).upper() != "GET":
            raise EodAuditRefusal(f"REFUSED: the end-of-day audit is read-only ({method} {url.split('?')[0]})")
        return inner(method, url, headers, body)
    return t


# ─────────────────────────────── pure pieces ────────────────────────────────

def stops_check(positions: list[dict], open_orders: list[dict]) -> dict:
    """Every long share position must have resting sell stops for its full quantity."""
    held, missing, partial = 0, [], []
    for p in positions:
        if p.get("asset_class") == "us_option":
            continue
        qty = float(p.get("qty") or 0)
        if qty <= 0:
            continue
        held += 1
        cov = sum(float(o.get("qty") or 0) for o in FM.stops_for(p["symbol"], open_orders))
        if cov <= 0:
            missing.append(p["symbol"])
        elif cov + 1e-9 < qty:
            partial.append({"symbol": p["symbol"], "qty": qty, "covered": cov})
    return {"n_held_long": held, "n_protected": held - len(missing) - len(partial),
            "missing": missing, "partial": partial}


def worst_case_block(positions: list[dict], open_orders: list[dict], equity: float) -> dict:
    """CLAUDE.md protocol 4 at the account's own stops: the exact sum over names
    (`fleet_manager.worst_case`: (price - stop) x qty, a name without a full stop
    counts WHOLE), and the n x notional% x stop% form at the largest notional and
    the widest stop held, plus sum|notional| / equity."""
    exact = FM.worst_case(positions, open_orders, [], equity, {})
    fracs, stops = [], []
    for p in positions:
        if p.get("asset_class") == "us_option":
            continue
        qty, px = float(p.get("qty") or 0), float(p.get("current_price") or 0)
        if qty <= 0 or px <= 0 or equity <= 0:
            continue
        fracs.append(qty * px / equity)
        st = FM.stops_for(p["symbol"], open_orders)
        cov = sum(float(o.get("qty") or 0) for o in st)
        if st and cov + 1e-9 >= qty:
            stops.append(max(0.0, (px - min(float(o.get("stop_price") or 0) for o in st)) / px))
        else:
            stops.append(1.0)                     # no full stop: the whole position is at risk
    n = len(fracs)
    bound = FM.formula_worst_case(n, max(fracs) if fracs else 0.0, max(stops) if stops else 0.0, equity)
    return {"usd_at_stops": exact["worst_usd"], "pct_equity": exact["worst_pct_equity"],
            "gross_usd": exact["gross_usd"], "gross_over_equity": exact["gross_over_equity"],
            "formula_bound": bound,
            "formula_note": "n x largest notional% x widest stop% (an upper bound on the exact sum)"}


def reconcile_state(state: Optional[dict], broker: dict[str, float], fills: list[dict],
                    orders_since: list[dict]) -> dict:
    """Our own record (`state/<role>.json`) + fills since == broker truth."""
    if not state:
        return {"status": "NO_STATE", "n_mismatch": 1,
                "examples": [{"why": "no state/<role>.json: the manager has no record for this account"}]}
    rec = FM.reconcile({k: float(q) for k, q in (state.get("positions") or {}).items()},
                       fills, broker, orders_since)
    ex = [dict(m, why="position") for m in rec["mismatches"]] + \
         [dict(f, why="order without our prefix since the record") for f in rec["foreign_orders"]]
    return {"status": rec["status"], "since": state.get("t"), "n_fills_since": len(fills),
            "n_mismatch": len(ex), "examples": ex[:EXAMPLES]}


def reconcile_grades(role: str, grades: Iterable[dict], last_equity: Optional[float],
                     prev_session: Optional[str], tol: Optional[float] = None) -> dict:
    """The newest grade row for the account vs the broker's previous-close equity."""
    tol = float(_cfg.FLEET_EOD_AUDIT_GRADE_TOL_FRAC) if tol is None else tol
    mine = [g for g in grades if g.get("role") == role and g.get("session")]
    if not mine:
        return {"status": "NO_GRADE", "n_mismatch": 1, "examples": [{"why": "no grade row for this account"}]}
    g = sorted(mine, key=lambda r: str(r["session"]))[-1]      # stable: the last row of the newest session
    out = {"newest_session": g["session"], "grade_equity": g.get("equity"), "broker_last_equity": last_equity}
    ex = []
    if prev_session and str(g["session"]) < prev_session:
        ex.append({"why": f"newest grade {g['session']} is older than the previous session {prev_session}"})
    elif last_equity and g.get("equity") and str(g["session"]) == prev_session:
        d = abs(float(g["equity"]) / float(last_equity) - 1.0)
        out["rel_diff"] = round(d, 6)
        if d > tol:
            ex.append({"why": f"grade equity {g['equity']} vs broker last_equity {last_equity}: "
                              f"{d:.2%} > {tol:.2%}"})
    out.update(status="OK" if not ex else "MISMATCH", n_mismatch=len(ex), examples=ex)
    return out


def prev_weekday(d: date) -> date:
    """The previous NYSE session: weekends AND `config.US_MARKET_HOLIDAYS` are
    skipped (review F7: 2026-11-27 would otherwise expect a 11-26 grade)."""
    hol = set(getattr(_cfg, "US_MARKET_HOLIDAYS", ()) or ())
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in hol:
        d -= timedelta(days=1)
    return d


# ─────────────────────────────── one account ────────────────────────────────

def audit_account(role: str, venue: Optional[FM.Venue], *, state: Optional[dict], grades: list[dict],
                  run_id: str, trigger: str, credential_present: bool = True) -> dict:
    row: dict[str, Any] = {"schema": SCHEMA, "run_id": run_id, "trigger": trigger, "t": FM._now_iso(),
                           "role": role, "places_orders": False}
    if not credential_present or venue is None:
        row.update(status="NO_CREDENTIAL", credential="MISSING",
                   why=f"no AAT_{role.upper()}_KEY_ID / _SECRET_KEY pair in the execution repo's .env")
        return row
    st, acct = venue.call("GET", "/v2/account")
    if st in (401, 403):
        row.update(status="CREDENTIAL_INVALID", credential=f"INVALID_HTTP_{st}",
                   why=f"the account's key answers HTTP {st}: positions cannot be read or managed; "
                       "the credential is the owner's to rotate")
        return row
    if st != 200 or not isinstance(acct, dict):
        row.update(status="UNREADABLE", credential="UNKNOWN", why=f"GET /v2/account -> HTTP {st}")
        return row
    row["credential"] = "OK"
    clock = venue.clock()
    day = str(clock.get("timestamp", ""))[:10] or date.today().isoformat()
    today = date.fromisoformat(day)
    equity, cash = float(acct.get("equity") or 0), float(acct.get("cash") or 0)
    last_eq = float(acct.get("last_equity") or 0) or None
    positions = venue.positions()
    open_orders = venue.open_orders()
    broker = FM.signed_positions(positions)
    day_start = f"{day}T00:00:00Z"
    orders_today = venue.orders_since(day_start)
    ours = sum(1 for o in orders_today if str(o.get("client_order_id") or "").startswith(FM.COID_PREFIX))
    since = (state or {}).get("t")
    fills = venue.fills(after=since) if since else []
    orders_since = venue.orders_since(since) if since else []
    stops = stops_check(positions, open_orders)
    rs = reconcile_state(state, broker, fills, orders_since)
    rg = reconcile_grades(role, grades, last_eq, prev_weekday(today).isoformat())
    flags = []
    if stops["missing"] or stops["partial"]:
        flags.append(f"MISSING_STOP {stops['missing'] + [p['symbol'] for p in stops['partial']]}")
    if rs["n_mismatch"]:
        flags.append(f"STATE_{rs['status']} ({rs['n_mismatch']})")
    if rg["n_mismatch"]:
        flags.append(f"GRADES_{rg['status']} ({rg['n_mismatch']})")
    if cash < 0:
        flags.append(f"NEGATIVE_CASH {cash:,.2f}")
    shorts = [p["symbol"] for p in positions if float(p.get("qty") or 0) < 0 and p.get("asset_class") != "us_option"]
    if shorts:
        flags.append(f"SHORT_SHARES {shorts}")
    row.update(session_day_et=day, equity=equity, cash=cash, last_equity=last_eq,
               n_positions=len(positions), n_open_orders=len(open_orders),
               orders_today={"n": len(orders_today), "ours": ours, "foreign": len(orders_today) - ours},
               stops=stops,
               reconciliation={"state": rs, "grades": rg},
               n_mismatches=rs["n_mismatch"] + rg["n_mismatch"],
               mismatch_examples=(rs["examples"] + rg["examples"])[:EXAMPLES],
               worst_case=worst_case_block(positions, open_orders, equity),
               flags=flags, status="DEGRADED" if flags else "OK",
               why="; ".join(flags))
    return row


# ─────────────────────────────── the fleet ──────────────────────────────────

def run_audit(roles: list[str], env: dict, *, run_id: str, trigger: str, base: Optional[Path] = None,
              transport: Optional[Callable] = None, write: bool = True) -> list[dict]:
    """Audit every role, append one row each, return the rows. One account's
    exception becomes that account's ERROR row; it never stops the others."""
    if not roles:
        raise EodAuditRefusal("REFUSED: no fleet roles to audit (an audit of nothing would read green)")
    grades = FM.read_jsonl(FM.grades_path(base))
    inner = transport or FM._urllib_transport
    rows = []
    for role in roles:
        kid, sec = env.get(f"AAT_{role.upper()}_KEY_ID"), env.get(f"AAT_{role.upper()}_SECRET_KEY")
        sp = FM.state_path(role, base)
        try:
            state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
            v = FM.Venue(kid, sec, transport=readonly_transport(inner)) if (kid and sec) else None
            row = audit_account(role, v, state=state, grades=grades, run_id=run_id, trigger=trigger,
                                credential_present=bool(kid and sec))
        except Exception as exc:                                # noqa: BLE001 -- one account never stops the rest
            row = {"schema": SCHEMA, "run_id": run_id, "trigger": trigger, "t": FM._now_iso(), "role": role,
                   "places_orders": False, "status": "ERROR", "why": f"{type(exc).__name__}: {exc}"[:300]}
        rows.append(row)
        if write:
            FM.append_jsonl(audit_path(base), row)
    return rows
