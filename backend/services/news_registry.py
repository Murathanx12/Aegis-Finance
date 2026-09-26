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
from typing import Any, Optional

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

#: WHICH NETWORK DOOR a source's pages come through. OPTIONAL on a row, and
#: `plain` when absent — which is what every row written before 2026-09-19
#: means and what `scripts/news_pull.py` has always done.
#:
#: `scrapling` is the stealthy browser fetcher attached in chunk 20
#: (`backend/services/fetch_scrapling.py`). It is a PER-SOURCE, deliberate
#: registry edit and never a blanket swap: the stealthy path is slower and
#: heavier, and the reason it exists is the collector class that 403s on a
#: plain `urllib` request, not "pages in general".
#:
#: Changing this field changes nothing about PIT. A page fetched by a browser
#: is the same page; `pit_grade` and `label_source` are declared by the row and
#: invariant 20 still binds (`index_state` may never label).
VALID_FETCHERS = ("plain", "scrapling")
DEFAULT_FETCHER = "plain"


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
    #: Which network door this source's pages come through. Optional in the
    #: file, `plain` when absent — see `VALID_FETCHERS`.
    fetcher: str = DEFAULT_FETCHER
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
    """`backend/data/news_sources.yaml` — from the IMAGE, not from `DATA_DIR`.

    Deliberately NOT under `AEGIS_DATA_DIR`, for the same reason
    `paper_portfolios.yaml` is not (`config.py:105-115`): the registry is
    immutable, version-controlled data that ships with the code, and a
    persistence volume mounted over `DATA_DIR` must never be able to shadow it.
    A pull run with `AEGIS_DATA_DIR` pointed at another checkout writes its
    CORPUS there and still reads THIS registry — which is what we want, because
    the registry belongs to the commit that defined the parsers.

    `_config.BACKEND_DIR` is read at CALL time so a test can repoint it.
    """
    return Path(_config.BACKEND_DIR) / "data" / "news_sources.yaml"


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

    # OPTIONAL, because every row written before chunk 20 omits it and they all
    # mean `plain`. An unrecognised value is refused for the same reason an
    # unrecognised `pit_grade` is: it is not a new kind of door, it is a typo,
    # and a typo that fell through to the default would silently keep using the
    # fetcher the editor was trying to change.
    fetcher = str(row.get("fetcher", DEFAULT_FETCHER) or DEFAULT_FETCHER).strip()
    if fetcher not in VALID_FETCHERS:
        raise RegistryError(
            f"REFUSED: source {sid!r} fetcher {fetcher!r} not in {VALID_FETCHERS}. "
            f"Omit the field for the plain HTTP door."
        )

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
        fetcher=fetcher,
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


# --------------------------------------------------------------------------
# ROW-LEVEL PIT GRADE AT READ TIME: the archive quarantine (2026-09-26, wave-1
# adjudication row 12)
#
# `pit_grade` above is a SOURCE's declaration. A source can be honest and a
# ROW can still be an archive: `alpaca_benzinga_news` served 36,720 headlines
# published on or before 2015-02-20, and each was stamped `first_seen_utc` =
# its 2026 ingest time. Filtered on `first_seen_utc` alone, a 2015 headline is
# "pre-entry evidence" for a 2026 decision (fast-mover forensics read
# "Facebook acquiring QuickFire Networks" as state at entry). The corpus files
# are NOT rewritten -- the grade is applied here, at read time, so every
# reader that goes through `grade_row` sees the same answer and the raw row
# keeps its declared grade in `declared_pit_grade`.

#: A row grade, never a source grade (so it is deliberately NOT in PIT_GRADES,
#: which validates the registry file).
ARCHIVE_GRADE = "archive"
#: `published_utc` earlier than `first_seen_utc` by more than this is an
#: archive row: we first saw it long after the world did, so it is not news at
#: first_seen and must never enter a state-at-entry.
ARCHIVE_LAG_DAYS = 30


def _row_ts(v: Any):
    from datetime import datetime, timezone
    if v is None or v == "":
        return None
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def effective_pit_grade(row: dict, *, lag_days: int = ARCHIVE_LAG_DAYS) -> str:
    """The grade a reader must act on: `archive` when the row was published
    more than `lag_days` before we first saw it, else the row's declared grade
    (empty string when it declares none). A row missing either stamp keeps its
    declared grade -- it cannot be proven an archive, and every PIT reader
    already refuses a row with no `first_seen_utc`."""
    pub, seen = _row_ts(row.get("published_utc")), _row_ts(row.get("first_seen_utc"))
    if pub is not None and seen is not None and (seen - pub).total_seconds() > lag_days * 86400:
        return ARCHIVE_GRADE
    return str(row.get("pit_grade") or "")


def grade_row(row: dict, *, lag_days: int = ARCHIVE_LAG_DAYS) -> dict:
    """A copy of `row` with `pit_grade` set to the effective grade and the
    source's own grade kept in `declared_pit_grade`. Never mutates the input."""
    out = dict(row)
    out.setdefault("declared_pit_grade", row.get("pit_grade"))
    out["pit_grade"] = effective_pit_grade(row, lag_days=lag_days)
    return out


def is_archive(row: dict, *, lag_days: int = ARCHIVE_LAG_DAYS) -> bool:
    return effective_pit_grade(row, lag_days=lag_days) == ARCHIVE_GRADE


def has_stamp_pair(row: dict) -> bool:
    """Both `published_utc` and `first_seen_utc` parse: only such a row CAN be
    proven an archive. A reader prints the rest as `rows_without_stamp_pair`,
    because 'excluded 0' over rows that could never be graded is not 'clean'."""
    return _row_ts(row.get("published_utc")) is not None and         _row_ts(row.get("first_seen_utc")) is not None


def exclude_archive(rows, *, lag_days: int = ARCHIVE_LAG_DAYS) -> tuple[list[dict], dict]:
    """(kept rows, each `grade_row`-graded; census for the receipt).

    The one call every corpus reader makes (wave-2 handoff §3 owed): a row
    published more than `lag_days` before we first saw it is dropped and
    COUNTED, per source, so the receipt says how much archive it refused."""
    kept: list[dict] = []
    by_source: dict[str, int] = {}
    n = unstamped = 0
    for r in rows:
        n += 1
        if not has_stamp_pair(r):
            unstamped += 1
        g = grade_row(r, lag_days=lag_days)
        if g["pit_grade"] == ARCHIVE_GRADE:
            src = str(r.get("source") or "?")
            by_source[src] = by_source.get(src, 0) + 1
            continue
        kept.append(g)
    return kept, archive_receipt(n, sum(by_source.values()), unstamped, by_source,
                                 lag_days=lag_days)


def archive_receipt(rows_read: int, excluded: int, unstamped: int,
                    by_source: Optional[dict] = None, *,
                    lag_days: int = ARCHIVE_LAG_DAYS) -> dict:
    """The receipt block every corpus reader prints beside its own funnel."""
    return {"rows_read": int(rows_read), "archive_rows_excluded": int(excluded),
            "archive_rows_excluded_by_source": dict(sorted((by_source or {}).items())),
            "rows_without_stamp_pair": int(unstamped),
            "rule": (f"news_registry.grade_row: pit_grade '{ARCHIVE_GRADE}' when first_seen_utc - "
                     f"published_utc > {lag_days} days; a row without both stamps cannot be "
                     "proven an archive and is kept, counted in rows_without_stamp_pair")}


def archive_census(corpus_dir: Path | str | None = None, *,
                   lag_days: int = ARCHIVE_LAG_DAYS) -> dict:
    """Per-source counts of rows the read-time grade quarantines. Reads every
    `news_corpus/<source>/*.jsonl`; writes nothing."""
    import json as _json
    base = Path(corpus_dir) if corpus_dir is not None else (
        Path(_config.OPTIMUS_LEDGER_DIR) / "news_corpus")
    by_source: dict[str, dict] = {}
    for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("_")):
        n = n_arch = n_unstamped = 0
        oldest_pub = newest_arch_pub = None
        for f in sorted(d.glob("*.jsonl")):
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = _json.loads(line)
                    except ValueError:
                        continue
                    n += 1
                    if _row_ts(r.get("published_utc")) is None or _row_ts(r.get("first_seen_utc")) is None:
                        n_unstamped += 1
                    if is_archive(r, lag_days=lag_days):
                        n_arch += 1
                        p = str(r.get("published_utc"))
                        oldest_pub = p if oldest_pub is None or p < oldest_pub else oldest_pub
                        newest_arch_pub = (p if newest_arch_pub is None or p > newest_arch_pub
                                           else newest_arch_pub)
        by_source[d.name] = {"rows": n, "archive": n_arch,
                             "archive_share": round(n_arch / n, 4) if n else None,
                             "missing_a_stamp": n_unstamped,
                             "archive_published_min": oldest_pub,
                             "archive_published_max": newest_arch_pub}
    return {"rule": (f"pit_grade = '{ARCHIVE_GRADE}' when first_seen_utc - published_utc > "
                     f"{lag_days} days; graded at read time "
                     "(backend.services.news_registry.grade_row), corpus files untouched"),
            "lag_days": lag_days,
            "total_rows": sum(v["rows"] for v in by_source.values()),
            "total_archive": sum(v["archive"] for v in by_source.values()),
            "by_source": by_source}
