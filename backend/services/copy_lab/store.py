"""COPY-LAB's own ledger namespace. It never touches the research book.

WHERE THINGS LIVE
=================
    <OPTIMUS_LEDGER_DIR>/copy_lab/<lane_id>/seed.json      inception + config hash
                                           /signals.jsonl  every signal, filled or not
                                           /positions.json current book
                                           /nav.jsonl      one row per marked session
                                           /receipts/      one per engine run

Separate directory, separate files, separate hash. The ten research lanes
accruing since 2026-06-08 live in the portfolio-intelligence tables and in
`paper_portfolios.yaml`, and nothing in this package reads or writes either.

WHY SEEDING IS A FILE AND NOT A FLAG IN MEMORY
==============================================
`seed.json` is written once and refuses to be rewritten. It carries the
inception timestamp and the configuration hash that was in force, so a later
config edit cannot retroactively claim to have been the one that ran. A lane
whose seed file says one hash and whose config says another is a lane that must
stop, not a lane that quietly continues.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)

ROOT = _config.OPTIMUS_LEDGER_DIR / "copy_lab"

_LOCK = threading.Lock()


class SeedRefused(RuntimeError):
    """Seeding would overwrite or contradict an existing inception."""


class ConfigDrift(RuntimeError):
    """The lane is running under a configuration it was not seeded with."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lane_dir(lane_id: str, root: Path | None = None) -> Path:
    return (root or ROOT) / lane_id


def seed_path(lane_id: str, root: Path | None = None) -> Path:
    return lane_dir(lane_id, root) / "seed.json"


def is_seeded(lane_id: str, root: Path | None = None) -> bool:
    return seed_path(lane_id, root).exists()


def read_seed(lane_id: str, root: Path | None = None) -> dict | None:
    p = seed_path(lane_id, root)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def seed_lane(spec, *, root: Path | None = None,
              seeded_at: str | None = None) -> dict:
    """Write the inception record. Idempotent; refuses to move an inception.

    Re-seeding with the SAME configuration is a no-op that returns the existing
    record — seeds are idempotent by design, because the alternative is a
    procedure people are afraid to re-run. Re-seeding with a DIFFERENT hash
    raises: that is a new strategy and needs a new lane, not a new start date
    for an old one.
    """
    p = seed_path(spec.lane_id, root)
    with _LOCK:
        if p.exists():
            existing = json.loads(p.read_text(encoding="utf-8"))
            if existing.get("config_hash") != spec.config_hash:
                raise SeedRefused(
                    f"{spec.lane_id} was seeded at {existing.get('seeded_at')} "
                    f"under config {existing.get('config_hash')[:12]} and the "
                    f"current config is {spec.config_hash[:12]}. A changed "
                    f"configuration is a NEW lane with its own inception, never "
                    f"a new start date for this one.")
            return existing
        rec = {
            "lane_id": spec.lane_id,
            "seeded_at": seeded_at or _now(),
            "config_version": spec.config_version,
            "config_hash": spec.config_hash,
            "source": spec.source,
            "actor_type": spec.actor_type,
            "entry_rule": spec.entry_rule,
            "exit_rule": spec.exit_rule,
            "holding_days": spec.holding_days,
            "benchmark": spec.benchmark,
            "sizing_rule": spec.params.get("sizing"),
            "target_weight": spec.params.get("target_weight"),
            "notional_usd": spec.params.get("notional_usd"),
            "transaction_cost_bps": spec.params.get("transaction_cost_bps"),
            "slippage_bps": spec.params.get("slippage_bps"),
            "min_price": spec.params.get("min_price"),
            "min_dollar_volume_20d": spec.params.get("min_dollar_volume_20d"),
            "max_single_name": spec.params.get("max_single_name"),
            "max_positions": spec.params.get("max_positions"),
            "label": spec.label,
            "validation_status": spec.validation_status,
            "paper_only": True,
            "real_capital": False,
            "note": ("PRODUCT_EXPERIMENT / NOT VALIDATED ALPHA. The entry clock "
                     "starts at seeded_at; no event public before it is ever "
                     "eligible, and no historical fill is ever written."),
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        logger.info("COPY-LAB: seeded %s at %s under config %s",
                    spec.lane_id, rec["seeded_at"], spec.config_hash[:12])
        return rec


def assert_config_current(spec, *, root: Path | None = None) -> dict:
    """The lane may only run under the configuration it was seeded with."""
    rec = read_seed(spec.lane_id, root)
    if rec is None:
        raise ConfigDrift(f"{spec.lane_id} is not seeded")
    if rec.get("config_hash") != spec.config_hash:
        raise ConfigDrift(
            f"{spec.lane_id} was seeded under config "
            f"{str(rec.get('config_hash'))[:12]} but the file on disk hashes to "
            f"{spec.config_hash[:12]} — refusing to run. Segment identity IS "
            f"the configuration; continuing would attribute one strategy's "
            f"record to another's rules.")
    return rec


# ── the per-lane books ──────────────────────────────────────────────────────
def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
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
            logger.error("COPY-LAB: %s line %d unreadable — counts from this "
                         "file are LOWER BOUNDS", path, i)
    return out


def append_signals(lane_id: str, rows: list[dict],
                   root: Path | None = None) -> None:
    _append_jsonl(lane_dir(lane_id, root) / "signals.jsonl", rows)


def read_signals(lane_id: str, root: Path | None = None) -> list[dict]:
    return _read_jsonl(lane_dir(lane_id, root) / "signals.jsonl")


def append_nav(lane_id: str, rows: list[dict],
               root: Path | None = None) -> None:
    _append_jsonl(lane_dir(lane_id, root) / "nav.jsonl", rows)


def read_nav(lane_id: str, root: Path | None = None) -> list[dict]:
    return _read_jsonl(lane_dir(lane_id, root) / "nav.jsonl")


def write_positions(lane_id: str, book: dict, root: Path | None = None) -> None:
    p = lane_dir(lane_id, root) / "positions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(book, indent=2, default=str), encoding="utf-8")


def read_positions(lane_id: str, root: Path | None = None) -> dict:
    p = lane_dir(lane_id, root) / "positions.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_receipt(lane_id: str, receipt: dict,
                  root: Path | None = None) -> Path:
    d = lane_dir(lane_id, root) / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    stamp = (receipt.get("run_at") or _now()).replace(":", "").replace("-", "")
    p = d / f"run_{stamp}.json"
    p.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return p
