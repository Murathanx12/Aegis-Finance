"""N-B — the whole-market news SOURCE REGISTRY, loaded and validated.

Roadmap 2026-09-11 §3 N-B states the contract in one line:

    a source not in the registry cannot be pulled (refusal at parse)

so this module is the only door to `backend/data/news_sources.yaml`, and it
refuses rather than repairs. Three refusals, each of which has a real failure
behind it:

1. **An unknown id is a refusal, not an empty pull.** `scripts/news_pull.py`
   resolves `--source X` through `get()`; an id that is not in the file raises
   `UnknownSource` before a single byte leaves the machine. A collector that
   quietly writes nothing for a name nobody registered is the silent-fragility
   bug class this repo keeps paying for.

2. **A missing field is a refusal for the WHOLE file.** Not for that row — for
   the file. A half-added source that loads fine and then explodes at 3 a.m.
   inside the pull is worse than a file that refuses to load at all.

3. **`pit_grade: index_state` forbids `label_source: true`.** This is invariant
   20 written as code. An index_state feed (Google News, Reddit, Nikkei's RDF,
   Yahoo's consensus snapshot) can be reordered, edited or backfilled by its
   provider after the fact, so a return labelled from one of its timestamps is
   a look-ahead with no way to detect it later. The registry is where that rule
   is cheap to enforce; by the time a row is in a parquet it is not.

The loader is deliberately dumb about everything else. It does not fetch, it
does not know what a parser does, and it holds no state beyond an mtime-keyed
cache so the coverage endpoint can call it per request without re-parsing a
30 KB YAML each time.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend import config as _config

#: The three PIT grades, and the only ones. `native_stamp` and
#: `first_seen_only` may label a return (the second because WE write the
#: anchor); `index_state` never may.
PIT_GRADES = ("native_stamp", "first_seen_only", "index_state")

#: Every field a source row must carry. A row missing any one of them fails the
#: whole file — see the module docstring for why that is deliberate.
REQUIRED_FIELDS = (
    "id",
    "provider",
    "region",
    "language",
    "tier",
    "licence",
    "method",
    "parser",
    "endpoint_or_feed",
    "auth",
    "rate_limit",
    "min_interval_s",
    "pit_grade",
    "stamp_field",
    "stamp_tz",
    "ticker_tags",
    "body_available",
    "label_source",
    "implemented",
    "implemented_note",
    "notes",
)

VALID_TIERS = ("1", "2", "3", "social_hypothesis")
VALID_METHODS = ("api", "rss", "lib")


class RegistryError(ValueError):
    """The registry file itself is wrong. Nothing is pullable until it is fixed."""


class UnknownSource(KeyError):
    """An id that is not in the registry. The refusal roadmap N-B asks for."""

    def __init__(self, source_id: str, known: list[str]):
        self.source_id = source_id
        self.known = known
        super().__init__(
            f"REFUSED: {source_id!r} is not in the news source registry. "
            f"A source not in the registry cannot be pulled (roadmap N-B). "
            f"Known ids: {', '.join(known)}"
        )

    def __str__(self) -> str:  # KeyError repr-quotes its arg; this reads better
        return self.args[0]


@dataclass(frozen=True)
class NewsSource:
    """One validated registry row."""

    id: str
    provider: str
    region: str
    language: str
    tier: str
    licence: str
    method: str
    parser: str
    endpoint_or_feed: str
    auth: str
    rate_limit: str
    min_interval_s: float
    pit_grade: str
    stamp_field: str
    stamp_tz: str
    ticker_tags: bool
    body_available: bool
    label_source: bool
    implemented: bool
    implemented_note: str
    notes: str
    #: GDELT's per-region/per-theme query list; empty for everyone else.
    queries: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def needs_key(self) -> bool:
        """True when `auth` names an environment variable rather than 'none'."""
        return self.auth.strip().lower() != "none"

    def key_names(self) -> list[str]:
        """The ENV VARIABLE NAMES this source's auth string mentions.

        Names only. A receipt prints which name resolved, never a value.
        """
        out: list[str] = []
        for tok in self.auth.replace("(", " ").replace(")", " ").split():
            if tok.startswith("key:"):
                name = tok[4:].strip(" ,;")
                if name:
                    out.append(name)
        return out


def registry_path() -> Path:
    """`backend/data/news_sources.yaml`, following `AEGIS_DATA_DIR`.

    The registry is CODE-SHAPED data (it changes with the pull scripts, not with
    the market), so it lives beside the repo's other shipped data files and is
    read through `config.DATA_DIR` like everything else — a frozen build and a
    source checkout must resolve it the same way
    ([[feedback-a-path-that-resolves-differently-when-frozen-is-a-defect-family]]).
    """
    # Read the attribute at CALL time, never bind it at import time: a test
    # that points `config.DATA_DIR` at a tmp_path must be able to.
    return Path(_config.DATA_DIR) / "news_sources.yaml"


_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def _as_bool(row: dict, key: str, source_id: str) -> bool:
    v = row.get(key)
    if isinstance(v, bool):
        return v
    raise RegistryError(
        f"REFUSED: source {source_id!r} field {key!r} must be a YAML boolean "
        f"(true/false), got {v!r}. A string 'false' is truthy in Python and "
        f"would silently flip a PIT rule."
    )


def _validate_row(row: Any, seen: set[str]) -> NewsSource:
    if not isinstance(row, dict):
        raise RegistryError(f"REFUSED: every entry under `sources:` must be a mapping, got {type(row).__name__}")
    sid = row.get("id")
    if not isinstance(sid, str) or not sid.strip():
        raise RegistryError("REFUSED: a source row has no usable `id`")
    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if missing:
        raise RegistryError(
            f"REFUSED: source {sid!r} is missing required field(s): {', '.join(missing)}. "
            f"The whole registry is refused, not just this row — a half-added source "
            f"that loads and then fails inside the pull is worse than a file that will not load."
        )
    if sid in seen:
        raise RegistryError(f"REFUSED: duplicate source id {sid!r}")

    tier = str(row["tier"])
    if tier not in VALID_TIERS:
        raise RegistryError(f"REFUSED: source {sid!r} tier {tier!r} not in {VALID_TIERS}")
    if row["method"] not in VALID_METHODS:
        raise RegistryError(f"REFUSED: source {sid!r} method {row['method']!r} not in {VALID_METHODS}")
    grade = row["pit_grade"]
    if grade not in PIT_GRADES:
        raise RegistryError(
            f"REFUSED: source {sid!r} pit_grade {grade!r} not in {PIT_GRADES}. "
            f"An unrecognised grade is not a new kind of evidence, it is a typo."
        )

    ticker_tags = _as_bool(row, "ticker_tags", sid)
    body_available = _as_bool(row, "body_available", sid)
    label_source = _as_bool(row, "label_source", sid)
    implemented = _as_bool(row, "implemented", sid)

    # INVARIANT 20, as code.
    if grade == "index_state" and label_source:
        raise RegistryError(
            f"REFUSED: source {sid!r} is pit_grade `index_state` and also "
            f"`label_source: true`. An index_state feed can be reordered, "
            f"edited or backfilled by its provider after the fact, so a return "
            f"labelled from it is a look-ahead that cannot be detected later. "
            f"Set label_source: false, or justify a different pit_grade."
        )
    if not implemented and not str(row["implemented_note"]).strip():
        raise RegistryError(
            f"REFUSED: source {sid!r} is `implemented: false` with an empty "
            f"`implemented_note`. A source that cannot be pulled must say why, "
            f"or its zero rows look like a dead feed."
        )
    try:
        interval = float(row["min_interval_s"])
    except (TypeError, ValueError) as exc:
        raise RegistryError(f"REFUSED: source {sid!r} min_interval_s is not a number: {row['min_interval_s']!r}") from exc
    if interval < 0:
        raise RegistryError(f"REFUSED: source {sid!r} min_interval_s is negative")

    queries = row.get("queries") or []
    if not isinstance(queries, list) or any(not isinstance(q, str) for q in queries):
        raise RegistryError(f"REFUSED: source {sid!r} `queries` must be a list of strings")

    return NewsSource(
        id=sid,
        provider=str(row["provider"]),
        region=str(row["region"]),
        language=str(row["language"]),
        tier=tier,
        licence=str(row["licence"]),
        method=str(row["method"]),
        parser=str(row["parser"]),
        endpoint_or_feed=str(row["endpoint_or_feed"]).strip(),
        auth=str(row["auth"]).strip(),
        rate_limit=str(row["rate_limit"]).strip(),
        min_interval_s=interval,
        pit_grade=grade,
        stamp_field=str(row["stamp_field"]),
        stamp_tz=str(row["stamp_tz"]),
        ticker_tags=ticker_tags,
        body_available=body_available,
        label_source=label_source,
        implemented=implemented,
        implemented_note=str(row["implemented_note"]).strip(),
        notes=str(row["notes"]).strip(),
        queries=tuple(queries),
        raw=dict(row),
    )


def validate(payload: Any) -> list[NewsSource]:
    """Validate an already-parsed registry mapping. Raises `RegistryError`."""
    if not isinstance(payload, dict):
        raise RegistryError("REFUSED: the registry must be a YAML mapping")
    rows = payload.get("sources")
    if not isinstance(rows, list) or not rows:
        raise RegistryError("REFUSED: the registry has no `sources:` list")
    out: list[NewsSource] = []
    seen: set[str] = set()
    for row in rows:
        src = _validate_row(row, seen)
        seen.add(src.id)
        out.append(src)
    return out


def load(path: Path | str | None = None, *, refresh: bool = False) -> list[NewsSource]:
    """Every validated source, in file order. Cached on (path, mtime)."""
    p = Path(path) if path is not None else registry_path()
    if not p.exists():
        raise RegistryError(
            f"REFUSED: no news source registry at {p}. Lane N cannot pull "
            f"anything without it (roadmap N-B)."
        )
    stamp = (str(p), p.stat().st_mtime_ns, p.stat().st_size)
    with _LOCK:
        if not refresh and _CACHE.get("stamp") == stamp:
            return list(_CACHE["sources"])
    payload = yaml.safe_load(p.read_text(encoding="utf-8"))
    sources = validate(payload)
    with _LOCK:
        _CACHE["stamp"] = stamp
        _CACHE["sources"] = sources
        _CACHE["meta"] = {
            "version": str(payload.get("version", "")),
            "licence": str(payload.get("licence", "")),
            "path": str(p),
        }
    return list(sources)


def meta(path: Path | str | None = None) -> dict:
    """`version`, `licence`, `path` — for a receipt or the coverage payload."""
    load(path)
    return dict(_CACHE.get("meta") or {})


def ids(path: Path | str | None = None) -> list[str]:
    return [s.id for s in load(path)]


def get(source_id: str, path: Path | str | None = None) -> NewsSource:
    """One source, or `UnknownSource`. THE refusal gate of roadmap N-B."""
    rows = load(path)
    for s in rows:
        if s.id == source_id:
            return s
    raise UnknownSource(source_id, [s.id for s in rows])


def pullable(path: Path | str | None = None) -> list[NewsSource]:
    """Sources `scripts/news_pull.py` can actually fetch today."""
    return [s for s in load(path) if s.implemented and s.parser != "none"]


def label_sources(path: Path | str | None = None) -> list[str]:
    """Ids whose rows may label a return (N-C reads only these)."""
    return [s.id for s in load(path) if s.label_source]
