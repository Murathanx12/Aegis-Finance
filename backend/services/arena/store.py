"""Arena ledger namespace. Never the research book, never `paper_nav`.

WHERE THINGS LIVE
=================
    <OPTIMUS_LEDGER_DIR>/arena/snapshots/<date>.json      frozen daily state
                              /predictions.jsonl          arena-local LLM ledger
                              /experiences.jsonl          decision records
                              /experience_outcomes.jsonl  matured outcomes
                              /<book_id>/seed.json        inception + config hash
                                        /decisions.jsonl  every decision, incl. rejected
                                        /orders.jsonl     queued + filled orders
                                        /positions.json   current book
                                        /nav.jsonl        one row per marked session
                                        /receipts/        one per engine run

Seeds are files, not flags (copy_lab pattern): written once, refuse to move.
Snapshots are write-once: re-freezing the same date with different content is
an error, because the snapshot is the information state decisions are graded
against.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)

ROOT = _config.OPTIMUS_LEDGER_DIR / "arena"

_LOCK = threading.Lock()


class SeedRefused(RuntimeError):
    """Seeding would overwrite or contradict an existing inception."""


class ConfigDrift(RuntimeError):
    """The book is running under a configuration it was not seeded with."""


class SnapshotConflict(RuntimeError):
    """A date's frozen information state already exists with other content."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def book_dir(book_id: str, root: Path | None = None) -> Path:
    return (root or ROOT) / book_id


def seed_path(book_id: str, root: Path | None = None) -> Path:
    return book_dir(book_id, root) / "seed.json"


def is_seeded(book_id: str, root: Path | None = None) -> bool:
    return seed_path(book_id, root).exists()


def read_seed(book_id: str, root: Path | None = None) -> dict | None:
    p = seed_path(book_id, root)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def seed_book(spec, *, root: Path | None = None,
              seeded_at: str | None = None) -> dict:
    """Write the inception record. Idempotent; refuses to move an inception."""
    p = seed_path(spec.book_id, root)
    with _LOCK:
        if p.exists():
            existing = json.loads(p.read_text(encoding="utf-8"))
            if existing.get("config_hash") != spec.config_hash:
                raise SeedRefused(
                    f"{spec.book_id} was seeded at {existing.get('seeded_at')} "
                    f"under config {str(existing.get('config_hash'))[:12]} and "
                    f"the current config is {spec.config_hash[:12]}. A changed "
                    f"configuration is a NEW book with its own id, never a new "
                    f"start date for this one.")
            if (existing.get("policy_fingerprint")
                    and existing.get("policy_fingerprint")
                    != spec.policy_fingerprint):
                raise SeedRefused(
                    f"{spec.book_id}'s YAML is unchanged but its selection "
                    f"ESTIMATOR is not: seeded under policy "
                    f"{str(existing.get('policy_fingerprint'))[:12]}, code now "
                    f"fingerprints {spec.policy_fingerprint[:12]}. Same rules, "
                    f"different meaning — that is a new book, not a new day.")
            return existing
        rec = {
            "book_id": spec.book_id,
            "seeded_at": seeded_at or _now(),
            "config_version": spec.config_version,
            "config_hash": spec.config_hash,
            "policy_fingerprint": spec.policy_fingerprint,
            "policy_version": spec.policy_version,
            "purpose": spec.purpose,
            "notional_usd": spec.notional_usd,
            "benchmark": spec.benchmark,
            "transaction_cost_bps": spec.cost_bps,
            "slippage_bps": spec.slippage_bps,
            "label": spec.label,
            "validation_status": spec.validation_status,
            "simulation": True,
            "paper_only": True,
            "real_capital": False,
            "note": ("PRODUCT_EXPERIMENT / SIMULATION / NOT VALIDATED ALPHA. "
                     "Never cited as evidence of skill. History starts at "
                     "seeded_at; nothing is ever backdated."),
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        logger.info("ARENA: seeded %s at %s under config %s",
                    spec.book_id, rec["seeded_at"], spec.config_hash[:12])
        return rec


def assert_config_current(spec, *, root: Path | None = None) -> dict:
    rec = read_seed(spec.book_id, root)
    if rec is None:
        raise ConfigDrift(f"{spec.book_id} is not seeded")
    if rec.get("config_hash") != spec.config_hash:
        raise ConfigDrift(
            f"{spec.book_id} was seeded under config "
            f"{str(rec.get('config_hash'))[:12]} but the file on disk hashes "
            f"to {spec.config_hash[:12]} — refusing to run. Segment identity "
            f"IS the configuration.")
    # A seed written before policy fingerprints existed has no claim to check;
    # once it has one, it binds. Absent is absent, never "matches".
    seeded_fp = rec.get("policy_fingerprint")
    if seeded_fp and seeded_fp != spec.policy_fingerprint:
        raise ConfigDrift(
            f"{spec.book_id} was seeded under policy {str(seeded_fp)[:12]} but "
            f"the running code fingerprints {spec.policy_fingerprint[:12]} — "
            f"the YAML is unchanged and the SELECTION ESTIMATOR is not. "
            f"Refusing to run: a book whose scores changed meaning mid-segment "
            f"has one NAV series describing two policies.")
    return rec


# ── generic JSONL ───────────────────────────────────────────────────────────
def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            logger.error("ARENA: %s line %d unreadable — counts from this "
                         "file are LOWER BOUNDS", path, i)
    return out


# ── per-book files ──────────────────────────────────────────────────────────
def append_decisions(book_id: str, rows: list[dict],
                     root: Path | None = None) -> None:
    _append_jsonl(book_dir(book_id, root) / "decisions.jsonl", rows)


def read_decisions(book_id: str, root: Path | None = None) -> list[dict]:
    return _read_jsonl(book_dir(book_id, root) / "decisions.jsonl")


def append_orders(book_id: str, rows: list[dict],
                  root: Path | None = None) -> None:
    _append_jsonl(book_dir(book_id, root) / "orders.jsonl", rows)


def read_orders(book_id: str, root: Path | None = None) -> list[dict]:
    return _read_jsonl(book_dir(book_id, root) / "orders.jsonl")


def append_nav(book_id: str, rows: list[dict],
               root: Path | None = None) -> None:
    _append_jsonl(book_dir(book_id, root) / "nav.jsonl", rows)


def read_nav(book_id: str, root: Path | None = None) -> list[dict]:
    return _read_jsonl(book_dir(book_id, root) / "nav.jsonl")


def write_positions(book_id: str, book: dict, root: Path | None = None) -> None:
    p = book_dir(book_id, root) / "positions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(book, indent=2, default=str), encoding="utf-8")


def read_positions(book_id: str, root: Path | None = None) -> dict:
    p = book_dir(book_id, root) / "positions.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_receipt(book_id: str, receipt: dict,
                  root: Path | None = None) -> Path:
    d = book_dir(book_id, root) / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    stamp = (receipt.get("run_at") or _now()).replace(":", "").replace("-", "")
    p = d / f"run_{stamp}.json"
    p.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return p


# ── shared (namespace-level) files ──────────────────────────────────────────
def snapshot_path(day: str, root: Path | None = None) -> Path:
    return (root or ROOT) / "snapshots" / f"{day}.json"


def content_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def freeze_snapshot(day: str, payload: dict,
                    root: Path | None = None) -> dict:
    """Write the day's information state exactly once.

    Same content → no-op returning the existing record. Different content →
    SnapshotConflict: the frozen state is what every decision that day is
    graded against, and two versions of it is two versions of the truth.
    """
    p = snapshot_path(day, root)
    h = content_hash(payload)
    with _LOCK:
        if p.exists():
            existing = json.loads(p.read_text(encoding="utf-8"))
            if existing.get("information_state_hash") != h:
                raise SnapshotConflict(
                    f"snapshot for {day} already frozen with hash "
                    f"{existing.get('information_state_hash')} != {h}")
            return existing
        rec = {"date": day, "frozen_at": _now(),
               "information_state_hash": h, "state": payload}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        return rec


def read_snapshot(day: str, root: Path | None = None) -> dict | None:
    p = snapshot_path(day, root)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def predictions_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "predictions.jsonl"


def experiences_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "experiences.jsonl"


def outcomes_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "experience_outcomes.jsonl"


def append_experiences(rows: list[dict], root: Path | None = None) -> None:
    _append_jsonl(experiences_path(root), rows)


def read_experiences(root: Path | None = None) -> list[dict]:
    return _read_jsonl(experiences_path(root))


def append_outcomes(rows: list[dict], root: Path | None = None) -> None:
    _append_jsonl(outcomes_path(root), rows)


def read_outcomes(root: Path | None = None) -> list[dict]:
    return _read_jsonl(outcomes_path(root))


def reliability_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "reliability.jsonl"


def append_reliability(rows: list[dict], root: Path | None = None) -> None:
    _append_jsonl(reliability_path(root), rows)


def read_reliability(root: Path | None = None) -> list[dict]:
    return _read_jsonl(reliability_path(root))


def snapshot_dates(root: Path | None = None) -> list[str]:
    d = (root or ROOT) / "snapshots"
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def beliefs_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "beliefs.jsonl"


def append_beliefs(rows: list[dict], root: Path | None = None) -> None:
    _append_jsonl(beliefs_path(root), rows)


def read_beliefs(root: Path | None = None) -> list[dict]:
    return _read_jsonl(beliefs_path(root))
