"""The COPY-LAB lane configuration, and the hash that identifies a segment.

WHY THE HASH IS OVER THE RAW BYTES
==================================
A segment's identity is the exact configuration it ran under. Hashing a parsed
dict would make a comment change invisible and a key-order change significant —
exactly backwards for a file whose comments carry the frozen policy. So the hash
is SHA-256 of the file's bytes, and any edit to the file is a NEW configuration
that needs a new file and a new inception rather than a quiet continuation.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend import config as _config

logger = logging.getLogger(__name__)

CONFIG_PATH = (_config.BACKEND_DIR / "data" / "copy_lab"
               / "copy_lab_lanes_v1.yaml")

#: The lanes the directive authorised to run. Named here as well as in the YAML
#: so a YAML edit alone cannot activate a lane.
AUTHORISED_ACTIVE = ("CORPORATE_INSIDER_CLUSTER", "ACTIVIST_13D")


class LaneConfigError(RuntimeError):
    """The lane configuration cannot be trusted. Never a warning."""


@dataclass(frozen=True)
class LaneSpec:
    """One lane, with everything a fill needs and nothing it does not."""

    lane_id: str
    active: bool
    source: str
    actor_type: str | None
    action_types: tuple[str, ...]
    thesis: str
    entry_rule: str
    exit_rule: str
    holding_days: int
    benchmark: str
    validation_status: str
    label: str
    config_version: str
    config_hash: str
    blocked_by: str = ""
    cluster_window_days: int | None = None
    min_distinct_actors: int | None = None
    params: dict = field(default_factory=dict)

    @property
    def seedable(self) -> bool:
        return self.active and not self.blocked_by

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["action_types"] = list(self.action_types)
        return d


def config_bytes(path: Path | None = None) -> bytes:
    p = path or CONFIG_PATH
    if not p.exists():
        raise LaneConfigError(f"COPY-LAB configuration missing at {p}")
    return p.read_bytes()


def config_hash(path: Path | None = None) -> str:
    return hashlib.sha256(config_bytes(path)).hexdigest()


def load_lanes(path: Path | None = None) -> dict[str, LaneSpec]:
    """Every declared lane, active or not.

    Inactive lanes are RETURNED rather than filtered out: a lane that exists and
    cannot run is a different thing from a lane nobody has designed, and the
    status page has to be able to say which.
    """
    p = path or CONFIG_PATH
    raw: dict[str, Any] = yaml.safe_load(config_bytes(p).decode("utf-8")) or {}
    h = config_hash(p)
    defaults = raw.get("defaults") or {}
    lanes: dict[str, LaneSpec] = {}

    for lane_id, spec in (raw.get("lanes") or {}).items():
        spec = spec or {}
        active = bool(spec.get("active", False))
        blocked = str(spec.get("blocked_by", "") or "")
        if active and blocked:
            raise LaneConfigError(
                f"{lane_id} is marked active AND blocked_by={blocked!r}. A lane "
                f"whose source is not live would accrue an inception date "
                f"against an empty feed — a track record of a strategy that "
                f"never ran.")
        if active and lane_id not in AUTHORISED_ACTIVE:
            raise LaneConfigError(
                f"{lane_id} is active in the YAML but is not in the authorised "
                f"set {AUTHORISED_ACTIVE}. Activating a lane is an attended "
                f"decision, not a config edit.")
        lanes[lane_id] = LaneSpec(
            lane_id=lane_id,
            active=active,
            source=str(spec.get("source", "")),
            actor_type=spec.get("actor_type"),
            action_types=tuple(spec.get("action_types") or ()),
            thesis=str(spec.get("thesis", "")).strip(),
            entry_rule=str(spec.get("entry_rule", "")).strip(),
            exit_rule=str(spec.get("exit_rule", "")).strip(),
            holding_days=int(spec.get("holding_days", 0) or 0),
            benchmark=str(spec.get("benchmark")
                          or (defaults.get("benchmarks") or ["SPY"])[0]),
            validation_status=str(raw.get("validation_status",
                                          "PRODUCT_EXPERIMENT")),
            label=str(raw.get("label", "PRODUCT_LANE")),
            config_version=str(raw.get("config_version", "")),
            config_hash=h,
            blocked_by=blocked,
            cluster_window_days=spec.get("cluster_window_days"),
            min_distinct_actors=spec.get("min_distinct_actors"),
            params=dict(defaults),
        )

    missing = [n for n in AUTHORISED_ACTIVE if n not in lanes]
    if missing:
        raise LaneConfigError(
            f"authorised lanes absent from the configuration: {missing}")
    return lanes


def active_lanes(path: Path | None = None) -> dict[str, LaneSpec]:
    return {k: v for k, v in load_lanes(path).items() if v.active}


def summary(path: Path | None = None) -> dict:
    lanes = load_lanes(path)
    return {
        "config_path": str(path or CONFIG_PATH),
        "config_hash": config_hash(path),
        "n_lanes": len(lanes),
        "active": sorted(k for k, v in lanes.items() if v.active),
        "inactive": sorted(k for k, v in lanes.items() if not v.active),
        "blocked_reasons": {k: v.blocked_by for k, v in sorted(lanes.items())
                            if v.blocked_by},
        "validation_status": next(iter(lanes.values())).validation_status
                             if lanes else None,
    }
