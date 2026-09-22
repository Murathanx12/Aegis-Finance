"""Declared mutable policy state — what the night may change about itself.

MURAT, 2026-09-22
=================
    "It should not be able to update its code, but update its preferences.
     Maybe every night we can adjust what it did."

That sentence draws the only line that makes an unattended self-improving loop
safe to leave running: **code is immutable overnight, preferences are not.** A
system that may rewrite its own source can change the meaning of its own
guardrails while nobody is watching. A system that may only move declared
numbers inside declared bounds can adapt every night and still be the same
system in the morning.

THE CONTRACT
============
Exactly the keys in `SCHEMA` may change. Each carries a type, a range and a
sentence saying what it does. An update to anything else REFUSES — not because
the value would be wrong, but because an undeclared key is a code change wearing
a config's clothes.

Every write records **old value, new value, reason, evidence, timestamp** and
appends to an immutable journal. A change with no evidence is refused. That is
not ceremony: the 2026-09-22 morning report could name three new measurements
and not one line of *"this number was X, is now Y, because Z"*, which is the
difference between a night that learned and a night that ran.

WHAT IS DELIBERATELY NOT HERE
=============================
* **Risk limits.** `MAX_INVESTED_FRAC`, `MAX_NAME_FRAC`, `MAX_ADV_PARTICIPATION`
  live in `pc_broker` as module constants and are asserted at import. A loop
  that can widen its own stop overnight is the 2026-08-28 failure — twelve names
  x 25% = 300% gross, and the "fix" that widened the stop took the worst case
  from -9% to -24%. Sizing bounds are a human decision.
* **The model's weights.** A fitted checkpoint is an artefact with a version,
  promoted by the bake-off's economic objective, not a preference.
* **Anything the ledger has already sealed.** Policy versions are frozen once a
  decision has been made under them.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# See `xs_ranker` for why these are not rooted on `Path(__file__)`.
from backend import config as _cfg

_BOOK = _cfg.OPTIMUS_LEDGER_DIR / "pc_book"
STATE_PATH = _BOOK / "policy_state.json"
JOURNAL_PATH = _BOOK / "policy_journal.jsonl"


class PolicyRefused(RuntimeError):
    """The night asked to change something it is not allowed to change."""


#: key -> (default, low, high, what it does)
SCHEMA: dict[str, tuple[Any, float, float, str]] = {
    "book_size": (18, 8, 40,
                  "how many names the ranked book holds"),
    "replan_drift_frac": (0.05, 0.01, 0.25,
                          "minimum drift between held and desired book before a "
                          "rebalance is worth its round trip"),
    "heartbeat_minutes": (30, 5, 120,
                          "how often the live loop re-examines the book in session"),
    "exploration_temperature": (0.10, 0.0, 1.0,
                                "share of the book allocated to names the ranking "
                                "is uncertain about, so uncertainty is reduced by "
                                "spending rather than by waiting"),
    "min_decile_confidence": (0.0, 0.0, 1.0,
                              "minimum OOS hit rate a decile must show before its "
                              "names may be sized above the exploration budget"),
    "reader_reliability_local": (0.5, 0.0, 1.0,
                                 "weight on the local model when it disagrees with "
                                 "DeepSeek; moved by the paired-read outcomes"),
    "reader_reliability_deepseek": (0.5, 0.0, 1.0,
                                    "weight on DeepSeek in the same comparison"),
    "source_trust": ({}, 0.0, 1.0,
                     "per-source reliability for web/news evidence, keyed by "
                     "domain; moved by whether that source's events graded well"),
    "horizon_weights": ({"21": 1.0}, 0.0, 1.0,
                        "relative weight on each forecast horizon when a name "
                        "carries several"),
    "watchlist_attention": ({}, 0.0, 1.0,
                            "extra attention per symbol, so a name that surprised "
                            "us is examined sooner next session"),
}


def defaults() -> dict:
    return {k: (v[0].copy() if isinstance(v[0], dict) else v[0])
            for k, v in SCHEMA.items()}


def load() -> dict:
    if not STATE_PATH.exists():
        return defaults()
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("policy_state: unreadable (%s); serving defaults", exc)
        return defaults()
    out = defaults()
    out.update({k: v for k, v in (d.get("values") or {}).items() if k in SCHEMA})
    return out


def _check(key: str, value: Any) -> None:
    if key not in SCHEMA:
        raise PolicyRefused(
            f"REFUSED: {key!r} is not declared mutable. The night may change "
            f"{sorted(SCHEMA)} and nothing else; an undeclared key is a code "
            f"change wearing a config's clothes.")
    default, low, high, _ = SCHEMA[key]
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise PolicyRefused(f"REFUSED: {key} must be a mapping, got {type(value).__name__}")
        for k, v in value.items():
            if not isinstance(v, (int, float)) or not (low <= float(v) <= high):
                raise PolicyRefused(
                    f"REFUSED: {key}[{k!r}] = {v!r} is outside [{low}, {high}]")
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PolicyRefused(f"REFUSED: {key} must be numeric, got {type(value).__name__}")
    if not (low <= float(value) <= high):
        raise PolicyRefused(
            f"REFUSED: {key} = {value} is outside its declared range "
            f"[{low}, {high}]. Widening a bound is a human decision.")


def update(key: str, value: Any, *, reason: str, evidence: Any,
           actor: str = "night") -> dict:
    """Move one declared preference. Refuses without a reason AND evidence.

    `evidence` must be something a later reader can check — a receipt path, a
    measured before/after, a count. A free-text reason alone is how a night
    talks itself into a change, which is exactly the failure the five questions
    were written to catch.
    """
    if not reason or not str(reason).strip():
        raise PolicyRefused(f"REFUSED: a change to {key} needs a reason")
    if evidence in (None, "", [], {}):
        raise PolicyRefused(
            f"REFUSED: a change to {key} needs EVIDENCE — a receipt path, a "
            f"measured before/after, or a count. A reason without evidence is "
            f"a night talking itself into a change.")
    _check(key, value)

    state = load()
    old = state.get(key)
    state[key] = value
    row = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor, "key": key, "old": old, "new": value,
        "reason": str(reason), "evidence": evidence,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(
        {"receipt": "policy_state", "values": state,
         "updated": row["t"], "schema_keys": sorted(SCHEMA)},
        indent=1, default=str), encoding="utf-8")
    with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    logger.info("policy_state: %s %r -> %r (%s)", key, old, value, reason)
    return row


def journal(limit: int = 50) -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    rows = [json.loads(l) for l in JOURNAL_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-limit:]


def changed_since(iso: str) -> list[dict]:
    """What beliefs moved, for the morning report's BELIEF_CHANGED line."""
    return [r for r in journal(limit=10_000) if r.get("t", "") >= iso]


def declaration() -> dict:
    """What is mutable, what it means, and what it is right now."""
    cur = load()
    return {
        "receipt": "policy_state_declaration",
        "mutable": {k: {"value": cur.get(k), "default": v[0],
                        "range": [v[1], v[2]], "what": v[3]}
                    for k, v in SCHEMA.items()},
        "immutable_by_design": [
            "pc_broker.MAX_INVESTED_FRAC / MAX_NAME_FRAC / MAX_ADV_PARTICIPATION "
            "-- sizing bounds are a human decision (2026-08-28: widening a stop on "
            "uncapped gross took the worst case from -9% to -24%)",
            "production source code",
            "any policy version a decision has already been sealed under",
        ],
        "n_changes_recorded": len(journal(limit=10_000)),
    }
