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
    # 2026-09-26 (adjudication row 9): the two keys a GRADE moves every night.
    "reputation_weights": ({}, 0.0, 1.0,
                           "per-arm pooling weight from the newest "
                           "forecast_reputation refit; moved only by a refit "
                           "receipt, never by hand"),
    "persona_weights": ({}, 0.0, 1.0,
                        "weight on each thematic persona's forecast; its "
                        "reputation weight, 0.0 while held-out skill <= 0 (§64)"),
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


# ─────────────────────────── the nightly refresh ────────────────────────────
#
# ADJUDICATION 2026-09-26 ROW 9: `policy_state.json` had NEVER been written.
# Every nightly measurement since 09-22 had been computed and none of them moved
# a declared preference, because `update()` needed a caller and had none. The
# refresh below is that caller, and it has one rule: **it moves only the keys a
# GRADE decides** (per-arm pooling weights from the reputation refit, persona
# weights) and writes the file every night, `changed_since_last: []` included,
# so "nothing changed" and "nothing ran" are different files.
#
# It never touches a risk limit or code: it goes through `_check`, which
# refuses any key outside `SCHEMA`, and the sizing bounds are not in `SCHEMA`.

#: Families that are a tool-using PROCESS rather than a thematic persona.
PROCESS_FAMILIES = ("investigator",)
#: Families that are neither (too few rows to be a bench, or not a forecaster).
NON_PERSONA_FAMILIES = ("investigator", "why_moved", "review", "thesis_card")

#: Rounding before comparison, so a refit that moves a weight in the 7th decimal
#: is not a journal line.
WEIGHT_DP = 4


def _family(arm: str) -> str:
    arm = str(arm or "")
    return "investigator" if arm.startswith("investigator:") else arm.split(":")[0]


def _latest(dir_: Path, pattern: str) -> Path | None:
    files = sorted(Path(dir_).glob(pattern)) if Path(dir_).is_dir() else []
    return files[-1] if files else None


def _probe_gate() -> dict:
    """The PROBE gate's state, read from the gate's own function.

    `sim_run._probe_grade` owns the verdict; this reads it and never
    re-implements it (two implementations of a gate drift). If it cannot be
    read the state is CANNOT DETERMINE, never a default verdict.
    """
    try:
        from scripts import sim_run as SR
        g = SR._probe_grade()
        return {"verdict": g.get("verdict"),
                "sessions_graded": g.get("n_days_scored"),
                "sessions_needed": g.get("min_days"),
                "horizon_sessions": g.get("horizon_sessions"),
                "mean_excess_per_day": g.get("mean_excess_per_day"),
                "why": g.get("why"), "source": "scripts.sim_run._probe_grade"}
    except Exception as exc:                                    # noqa: BLE001
        return {"verdict": "CANNOT DETERMINE",
                "why": f"{type(exc).__name__}: {exc}"[:200],
                "source": "scripts.sim_run._probe_grade"}


#: The distillation's rule store: the fallback source of per-cell skill when a
#: reputation receipt predates `arms_by_observable` (the 2026-09-25 one does).
LEARNED_RULES = _cfg.OPTIMUS_LEDGER_DIR / "brain" / "learned_rules.jsonl"


def _cells_from_learned_rules(path: Path | None = None) -> list[dict]:
    """Held-out (group, observable, horizon) cells from MEASURED ledger rules,
    newest row per fact, shaped like `arms_by_observable`."""
    p = Path(path or LEARNED_RULES)
    if not p.is_file():
        return []
    latest: dict[str, dict] = {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("state") == "MEASURED" and r.get("fact_key", "").startswith("class:"):
            latest[r["fact_key"]] = r
    return [{"arm": ("investigator:*" if r.get("group") == "investigator"
                     else str(r.get("group"))),
             "observable": r.get("observable"), "horizon_days": r.get("horizon_days"),
             "n": r.get("n_heldout") or 0, "skill": r.get("skill"),
             "kind": r.get("kind")} for r in latest.values()]


def _direction_vs_magnitude(rec: dict, *, rules_path: Path | None = None) -> dict:
    """Per family: n-weighted held-out skill on DIRECTION vs MAGNITUDE cells.

    From the reputation receipt's `arms_by_observable`; when the receipt has
    none, from the distillation's MEASURED rules, and the source says which.
    """
    acc: dict[str, dict[str, list[float]]] = {}
    cells = rec.get("arms_by_observable") or []
    source = "reputation receipt arms_by_observable"
    if not cells:
        cells = _cells_from_learned_rules(rules_path)
        source = "learned_rules.jsonl (MEASURED class cells)" if cells else "none"
    for c in cells:
        kind = c.get("kind")
        if c.get("observable") == "return_sign":
            kind = "direction"
        if kind not in ("direction", "magnitude") or c.get("skill") is None:
            continue
        fam = _family(c.get("arm"))
        a = acc.setdefault(fam, {"direction": [0.0, 0.0], "magnitude": [0.0, 0.0]})
        a[kind][0] += float(c["skill"]) * int(c.get("n") or 0)
        a[kind][1] += int(c.get("n") or 0)
    out = {}
    for fam, a in sorted(acc.items()):
        row = {}
        for kind in ("direction", "magnitude"):
            s, n = a[kind]
            row[f"{kind}_skill_heldout"] = round(s / n, 4) if n else None
            row[f"{kind}_n_heldout"] = int(n)
        out[fam] = row
    inv = out.get("investigator") or {}
    note = ("investigator: magnitude held-out skill %s (n %s) vs direction %s "
            "(n %s) -- size on the magnitude read, never the direction read"
            % (inv.get("magnitude_skill_heldout"), inv.get("magnitude_n_heldout"),
               inv.get("direction_skill_heldout"), inv.get("direction_n_heldout"))
            if inv else "no investigator cells in the receipt or the rule store")
    return {"note": note, "by_family": out, "source": source}


def _diff(old: dict, new: dict) -> list[str]:
    keys = sorted(set(old) | set(new))
    return [k for k in keys if old.get(k) != new.get(k)]


def refresh(reputation_receipt: dict | str | Path | None, *,
            receipt_path: str | None = None, persona_receipt: str | None = None,
            probe_gate: dict | None = None, write: bool = True,
            now: str | None = None, rules_path: Path | None = None) -> dict:
    """Rewrite `policy_state.json` from the newest GRADES. Every night.

    Moves `reputation_weights` and `persona_weights` only, each change one
    journal line carrying the receipt that caused it. An identical receipt
    changes nothing and journals nothing; the file is still written, with
    `changed_since_last: []`. A missing or REFUSED receipt keeps every previous
    value and says why in `observed.status`.
    """
    t = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec: dict | None
    if isinstance(reputation_receipt, (str, Path)):
        receipt_path = receipt_path or str(reputation_receipt)
        try:
            rec = json.loads(Path(reputation_receipt).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rec = None
    else:
        rec = reputation_receipt
    if persona_receipt is None:
        p = _latest(_cfg.OPTIMUS_LEDGER_DIR / "specialists", "scoreboard_*.json")
        persona_receipt = str(p) if p else None

    prev_values = load()
    values = {k: (v.copy() if isinstance(v, dict) else v)
              for k, v in prev_values.items()}
    ok = isinstance(rec, dict) and rec.get("status") == "OK" and rec.get("arms")
    status = "OK" if ok else (
        "NO_RECEIPT" if not isinstance(rec, dict) else
        f"RECEIPT_{rec.get('status') or 'EMPTY'}: {rec.get('reason') or 'no arms'}")
    changes: list[dict] = []
    if ok:
        rep_w = {str(a["arm"]): round(float(a.get("weight") or 0.0), WEIGHT_DP)
                 for a in rec["arms"]}
        persona_w = {arm: w for arm, w in rep_w.items()
                     if _family(arm) not in NON_PERSONA_FAMILIES}
        for key, new, why, ev in (
            ("reputation_weights", rep_w,
             "per-arm pooling weight from the newest forecast_reputation refit "
             "(held-out skill, shrunk, normalised)", receipt_path),
            ("persona_weights", persona_w,
             "thematic personas are weighted by their own held-out grade; §64: "
             "optimal weight ZERO (negative discrimination)",
             {"reputation": receipt_path, "section_64": persona_receipt}),
        ):
            _check(key, new)
            old = prev_values.get(key) or {}
            moved = _diff(old, new)
            if not moved:
                continue
            values[key] = new
            changes.append({
                "t": t, "actor": "night:policy_state.refresh", "key": key,
                "old": {k: old.get(k) for k in moved},
                "new": {k: new.get(k) for k in moved},
                "reason": why, "evidence": ev})

    dvm = _direction_vs_magnitude(rec if isinstance(rec, dict) else {},
                                  rules_path=rules_path)
    state = {
        "receipt": "policy_state", "values": values, "updated": t,
        "schema_keys": sorted(SCHEMA),
        "refreshed_utc": t,
        "changed_since_last": [c["key"] for c in changes],
        "changes": [{k: c[k] for k in ("key", "old", "new")} for c in changes],
        "sources": {"reputation_receipt": receipt_path,
                    "reputation_date": (rec or {}).get("date") if isinstance(rec, dict) else None,
                    "persona_receipt_section_64": persona_receipt},
        # OBSERVED, not preferences: read-only facts the night reports beside
        # the values it may move. Nothing here is a knob.
        "observed": {
            "status": status,
            "persona_weights_note": (
                "personas pooled at their reputation weight, which is 0.0 while "
                "their held-out skill is <= 0 (§64: optimal weight ZERO)"),
            "probe_gate": probe_gate if probe_gate is not None else _probe_gate(),
            "direction_vs_magnitude": dvm,
        },
        "contract": ("the night changes preferences, never code or risk limits: "
                     "only SCHEMA keys move, each with a receipt"),
    }
    if write:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
        tmp.replace(STATE_PATH)
        if changes:
            with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
                for c in changes:
                    fh.write(json.dumps(c, default=str) + "\n")
    return state
