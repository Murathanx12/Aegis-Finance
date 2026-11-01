"""Read deployment provenance without importing the application or its config."""

import json
import os
from pathlib import Path
import re

_SHA = re.compile(r"[0-9a-fA-F]{40}")
_MAX_BYTES = 4096


def _valid(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def source_commit(environ=None, metadata_path=None):
    """Prefer valid Railway identity; absent/invalid metadata is explicitly unknown."""
    env = os.environ if environ is None else environ
    value = env.get("RAILWAY_GIT_COMMIT_SHA")
    if _valid(value):
        return value.lower()
    path = Path(metadata_path) if metadata_path is not None else Path(__file__).with_name("_build_source.json")
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return "unknown"
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return "unknown"
    value = data.get("source_commit") if isinstance(data, dict) else None
    return value.lower() if _valid(value) else "unknown"
