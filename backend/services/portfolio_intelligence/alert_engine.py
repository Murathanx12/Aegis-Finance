"""
V4 Alert Engine — the thing that taps you on the shoulder (rules core)
======================================================================

Evaluates alert rules against readings the engine already produces, with
dedupe/cooldown, an append-only ``alerts`` log (schema v8), and pluggable
delivery (always logs; Telegram if env-configured). Framing contract: every
alert is **risk-awareness, never an order** — no buy/sell language unless the
underlying signal has passed its Brier gate (none has; see V2 Goal 5).

v1 rules (cheap, state-driven, no extra network):
- ``regime_change``       — market regime moved (Bull/Neutral/Bear/Volatile).
- ``fragility_level_change`` — the descriptive composite's band moved
  (low/moderate/elevated/high).
- ``fragility_jump``      — composite rose ≥ JUMP_THRESHOLD between
  consecutive evals (direction matters: rising only).

State memory: the previous readings live in the engine's own
``alert_state`` audit row — so change detection survives restarts and never
re-fires on every tick. Cooldown: a (rule, subject, state) triple never
re-emits within COOLDOWN_HOURS.

The event-driven paper lane that *acts* on these alerts is a separate,
attended, pre-registered seed — this module only observes and notifies.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend.db import get_connection, init_db, insert_audit_log

logger = logging.getLogger(__name__)

COOLDOWN_HOURS = 48
JUMP_THRESHOLD = 0.15  # composite points between consecutive evals
MARKET = "market"

DISCLAIMER = "Risk-awareness context, not advice or an order."


@dataclass
class Alert:
    rule: str
    subject: str
    state: str
    message: str
    payload: dict = field(default_factory=dict)


# ── Pure rule evaluation ──────────────────────────────────────────────────────


def evaluate_rules(current: dict, previous: dict) -> list[Alert]:
    """Compare current readings against the previous run's. Pure — no I/O.

    ``current`` / ``previous`` keys (all optional): ``regime`` (str),
    ``fragility_composite`` (float), ``fragility_level`` (str).
    """
    alerts: list[Alert] = []

    cur_regime, prev_regime = current.get("regime"), previous.get("regime")
    if cur_regime and prev_regime and cur_regime != prev_regime:
        alerts.append(Alert(
            rule="regime_change", subject=MARKET, state=cur_regime,
            message=(f"Market regime shifted {prev_regime} → {cur_regime}. "
                     f"Regime shifts change the risk backdrop, not the forecast. "
                     f"{DISCLAIMER}"),
            payload={"from": prev_regime, "to": cur_regime},
        ))

    cur_lvl, prev_lvl = current.get("fragility_level"), previous.get("fragility_level")
    if cur_lvl and prev_lvl and cur_lvl != prev_lvl:
        alerts.append(Alert(
            rule="fragility_level_change", subject=MARKET, state=cur_lvl,
            message=(f"Structural fragility moved {prev_lvl} → {cur_lvl} "
                     f"(descriptive composite; measures fragility, not crash "
                     f"timing). {DISCLAIMER}"),
            payload={"from": prev_lvl, "to": cur_lvl,
                     "composite": current.get("fragility_composite")},
        ))

    cur_c, prev_c = current.get("fragility_composite"), previous.get("fragility_composite")
    if (cur_c is not None and prev_c is not None
            and (cur_c - prev_c) >= JUMP_THRESHOLD):
        alerts.append(Alert(
            rule="fragility_jump", subject=MARKET, state=f"{cur_c:.2f}",
            message=(f"Fragility composite rose {prev_c:.2f} → {cur_c:.2f} "
                     f"between evals — systemic stress inputs are moving "
                     f"together. {DISCLAIMER}"),
            payload={"from": prev_c, "to": cur_c},
        ))

    return alerts


# ── State memory ──────────────────────────────────────────────────────────────


def _load_previous_state(conn) -> dict:
    row = conn.execute(
        "SELECT payload FROM audit_log WHERE event_type = 'alert_state' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {}
    try:
        return json.loads(row["payload"]) or {}
    except Exception:
        return {}


def _latest_fragility_reading(conn) -> dict:
    row = conn.execute(
        "SELECT payload FROM audit_log WHERE event_type = 'fragility_eval' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {}
    try:
        p = json.loads(row["payload"]) or {}
        return {"fragility_composite": p.get("composite"),
                "fragility_level": p.get("level")}
    except Exception:
        return {}


# ── Cooldown + persistence ────────────────────────────────────────────────────


def _under_cooldown(conn, alert: Alert, now: datetime) -> bool:
    cutoff = (now - timedelta(hours=COOLDOWN_HOURS)).isoformat()
    row = conn.execute(
        "SELECT id FROM alerts WHERE rule = ? AND subject = ? AND state = ? "
        "AND created_at >= ? LIMIT 1",
        (alert.rule, alert.subject, alert.state, cutoff),
    ).fetchone()
    return row is not None


def _persist_alert(conn, alert: Alert, delivered: list[str], now: datetime) -> int:
    from backend.db import _write_lock
    with _write_lock:
        cur = conn.execute(
            "INSERT INTO alerts (created_at, rule, subject, state, message, "
            "payload, delivered) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now.isoformat(), alert.rule, alert.subject, alert.state,
             alert.message, json.dumps(alert.payload), json.dumps(delivered)),
        )
        conn.commit()
        return int(cur.lastrowid)


# ── Delivery (always log; Telegram when env-configured) ──────────────────────


def _deliver(alert: Alert) -> list[str]:
    channels = ["log"]
    logger.warning("ALERT [%s/%s→%s]: %s", alert.rule, alert.subject,
                   alert.state, alert.message)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            import requests
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"⚠️ Aegis: {alert.message}"},
                timeout=10,
            )
            r.raise_for_status()
            channels.append("telegram")
        except Exception as e:  # delivery failure is loud but never fatal
            logger.error("Telegram delivery failed for %s: %s", alert.rule, e)
    return channels


# ── Runner (scheduler hook) ───────────────────────────────────────────────────


def run_alert_check(current_regime: str | None = None, db_path=None,
                    now: datetime | None = None) -> dict:
    """Evaluate rules against the latest persisted readings, emit + persist
    alerts past cooldown, and store this run's state for the next comparison.

    ``current_regime`` is passed by the caller when it already computed it;
    None simply disables the regime rule for this run (no extra fetch here).
    """
    init_db(db_path)
    now = now or datetime.now()
    conn = get_connection(db_path)
    try:
        previous = _load_previous_state(conn)
        current = _latest_fragility_reading(conn)
        if current_regime:
            current["regime"] = current_regime

        fired = evaluate_rules(current, previous)
        emitted, suppressed = [], 0
        for a in fired:
            if _under_cooldown(conn, a, now):
                suppressed += 1
                continue
            delivered = _deliver(a)
            _persist_alert(conn, a, delivered, now)
            emitted.append({"rule": a.rule, "state": a.state})

        # Persist the observed state — merged over previous so a reading that
        # is missing THIS run (e.g. regime fetch failed) doesn't erase memory
        # and fire a spurious "change" when it comes back.
        insert_audit_log(conn, now.isoformat(), None, "alert_state",
                         {**previous, **current})
        return {"status": "ok", "evaluated": len(fired) + 0,
                "emitted": emitted, "suppressed_by_cooldown": suppressed,
                "readings": current}
    finally:
        conn.close()


def recent_alerts(limit: int = 50, db_path=None) -> list[dict]:
    """Read the alert log (newest first) for the API surface."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, created_at, rule, subject, state, message, payload, "
            "delivered FROM alerts ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("payload", "delivered"):
            try:
                d[k] = json.loads(d[k]) if d[k] else None
            except Exception:
                pass
        out.append(d)
    return out
