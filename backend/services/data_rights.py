"""Loader and validator for the data-rights register (`backend/data/data_rights.yaml`).

The register says which data sources may legally reach a public page. This
module only loads and validates it; `scripts/data_rights_audit.py` maps public
routes onto it. Nothing in the running system calls either (report-only).

Rules enforced here (a refusal raises `DataRightsError`, never returns quietly):
  * every flag is `yes`, `no` or `UNVERIFIED` (YAML 1.1 turns bare yes/no into
    booleans; they are normalised, so both spellings load);
  * a `yes` for public_display or commercial requires terms_url, date_read and
    a basis -- no `yes` without a cited primary page;
  * ids are unique; required fields present.

Deliberately NOT enforced: that sources are verified. A register full of
UNVERIFIED is honest; a test that went red on it would not be.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend import config as _config

FLAGS = ("personal", "academic", "public_display", "commercial")
ALLOWED = ("yes", "no", "UNVERIFIED")
TERMS_READ = ("ok", "failed", "not_attempted")
REQUIRED = ("id", "what", "obtained", "stored", *FLAGS, "terms_url", "terms_read",
            "date_read", "basis", "owner_confirm")
#: flags whose `yes` must carry a cited, dated primary terms page
CITED_FLAGS = ("public_display", "commercial")


class DataRightsError(ValueError):
    """The register is malformed or claims a `yes` it cannot cite."""


def register_path() -> Path:
    """The committed register, from the IMAGE (`config.BACKEND_DIR`, read at call
    time), same convention as `news_registry.registry_path`: tracked config that
    ships with the code, never under the mutable `AEGIS_DATA_DIR`."""
    return Path(_config.BACKEND_DIR) / "data" / "data_rights.yaml"


def _norm(v: Any) -> Any:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return v


def validate(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise DataRightsError("register must be a mapping with a `sources` list")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in payload["sources"]:
        if not isinstance(row, dict):
            raise DataRightsError(f"source row is not a mapping: {row!r}")
        row = dict(row)
        for f in FLAGS:
            if f in row:
                row[f] = _norm(row[f])
        sid = row.get("id")
        for k in REQUIRED:
            if k not in row:
                raise DataRightsError(f"source {sid!r} missing field {k!r}")
        if sid in seen:
            raise DataRightsError(f"duplicate source id {sid!r}")
        seen.add(sid)
        for f in FLAGS:
            if row[f] not in ALLOWED:
                raise DataRightsError(f"{sid}.{f}={row[f]!r} not in {ALLOWED}")
        if row["terms_read"] not in TERMS_READ:
            raise DataRightsError(f"{sid}.terms_read={row['terms_read']!r}")
        if not isinstance(row["owner_confirm"], bool):
            raise DataRightsError(f"{sid}.owner_confirm must be a bool")
        for f in CITED_FLAGS:
            if row[f] == "yes":
                if not (row["terms_url"] and row["date_read"] and row["basis"]
                        and row["terms_read"] == "ok"):
                    raise DataRightsError(
                        f"{sid}.{f}=yes needs terms_url, date_read, basis and terms_read=ok")
        row.setdefault("hosts", [])
        row.setdefault("detect", {})
        out.append(row)
    return out


def load(path: Path | str | None = None) -> list[dict[str, Any]]:
    p = Path(path) if path else register_path()
    with open(p, "r", encoding="utf-8") as fh:
        return validate(yaml.safe_load(fh))


def by_id(rows: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in (rows if rows is not None else load())}


def flag_counts(rows: list[dict[str, Any]] | None = None) -> dict[str, dict[str, int]]:
    rows = rows if rows is not None else load()
    return {f: {a: sum(1 for r in rows if r[f] == a) for a in ALLOWED} for f in FLAGS}
