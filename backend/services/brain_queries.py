"""THE READ-ONLY QUERY SURFACE the Optimus MCP wraps (roadmap section 11b).

The `optimus` repo runs the MCP server; this module is the five functions that
server calls. The split is deliberate and is in CLAUDE.md's four-repo table:
the DATA lives here, in `aegis-finance`, and the query LAYER lives here too,
so the tools cannot drift from what the allocator itself reads; only the
transport -- the MCP tool registration -- lives over there. Building the
server here would duplicate the one Optimus already runs.

READ-ONLY IS STRUCTURAL, NOT A FLAG
===================================
Qanat's MCP has 27 tools, 20 read and 7 write, and a `--read-only` mode that
restricts the agent to the 20. A flag can be off. This surface has NO write
tool at all -- not a disabled one, an absent one. Nothing here imports
`append`, `observe`, `supersede`, a broker, a subprocess or a network client,
and `test_brain_queries.py` walks this module's AST and fails if it ever does.
The same "read the AST, don't grep" discipline CLAUDE.md item 10 demands
elsewhere, applied to the surface an agent talks to.

THREE REFUSALS, EACH FOR A FAILURE THAT HAS HAPPENED
====================================================
1. **No query string, ever.** Filters are a typed DSL
   (`{"field": {"op": ..., "value": ...}}`). There is no code path that
   accepts SQL or an expression to evaluate, so there is nothing to inject
   and nothing to write through.
2. **Every read is BOUNDED.** `limit` is capped at `MAX_LIMIT` and the reply
   says `truncated: true` rather than quietly returning a page. An unbounded
   scan on a 340,465-row panel is how an agent turns a question into a
   timeout.
3. **Paths are SANDBOXED to the checkout.** A `job`/`run` that resolves
   outside `backend/data/optimus` is refused by name. An MCP tool that reads
   an arbitrary path is a file-read primitive wearing a research tool's name.

And the standing one: a missing receipt returns `CANNOT DETERMINE, no receipt
at <path>` rather than raising or returning an empty success -- a guard
derives its inputs or refuses, and a caller cannot tell an empty answer from
an absent one.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: Hard cap on rows returned by any function here.
MAX_LIMIT = 1000
DEFAULT_LIMIT = 500

#: The filter vocabulary. No `like`, no `regex`, no expression: each of those
#: is a small language, and a small language is the thing that grows.
OPS = ("eq", "ne", "in", "not_in", "gte", "lte", "gt", "lt", "between",
       "contains")


class QueryRefused(ValueError):
    """The query asks for something this surface will not do, and says which."""


def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT`.

    Not `Path(__file__)`-rooted alone: inside the packaged app `__file__` is
    under `_internal/`, so a path built that way reads a directory that does
    not exist and returns nothing WITHOUT failing (defect family #14).
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


def DATA() -> Path:                                            # noqa: N802
    return _repo_root() / "backend" / "data" / "optimus"


NEWS_PANEL = ("text_return_panel", "news_returns_2025_26.parquet")
REGISTRY = ("..", "signal_registry.yaml")


def _sandboxed(path: Path) -> Path:
    """`path`, or a refusal naming it. Nothing outside the data root is read."""
    root = DATA().resolve()
    try:
        resolved = Path(path).resolve()
        resolved.relative_to(root)
    except (ValueError, OSError) as exc:
        raise QueryRefused(
            f"REFUSED: {path} resolves outside {root}. This surface reads the "
            f"research data root and nothing else; a tool that reads an "
            f"arbitrary path is a file-read primitive wearing a research "
            f"tool's name.") from exc
    return resolved


def _check_limit(limit: int) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError) as exc:
        raise QueryRefused(f"limit must be an integer, got {limit!r}") from exc
    if n < 1:
        raise QueryRefused(f"limit must be >= 1, got {n}")
    if n > MAX_LIMIT:
        raise QueryRefused(
            f"REFUSED: limit {n} is above the {MAX_LIMIT}-row cap. An "
            f"unbounded scan turns a question into a timeout; narrow the "
            f"filters or page.")
    return n


def _as_text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _matches(row: dict, filters: dict | None) -> bool:
    """One row against the typed filter DSL. A MISSING field never matches.

    Missing is missing, never "average" and never "true": a filter that
    silently passed rows lacking the field it filters on would return a
    superset the caller cannot see.
    """
    if not filters:
        return True
    for field, spec in filters.items():
        if not isinstance(spec, dict) or "op" not in spec:
            raise QueryRefused(
                f"filter on {field!r} must be {{'op': ..., 'value': ...}}; a "
                f"query STRING is not accepted anywhere on this surface")
        op, target = spec.get("op"), spec.get("value")
        if op not in OPS:
            raise QueryRefused(f"unknown op {op!r}; declared: {list(OPS)}")
        if field not in row or row[field] is None:
            return False
        value = row[field]
        try:
            if op == "eq" and _as_text(value) != _as_text(target):
                return False
            if op == "ne" and _as_text(value) == _as_text(target):
                return False
            if op == "in" and _as_text(value) not in {_as_text(t) for t in target}:
                return False
            if op == "not_in" and _as_text(value) in {_as_text(t) for t in target}:
                return False
            if op == "contains" and _as_text(target).lower() not in _as_text(value).lower():
                return False
            if op in ("gte", "lte", "gt", "lt"):
                a, b = float(value), float(target)
                if op == "gte" and not a >= b:
                    return False
                if op == "lte" and not a <= b:
                    return False
                if op == "gt" and not a > b:
                    return False
                if op == "lt" and not a < b:
                    return False
            if op == "between":
                lo, hi = target
                if not float(lo) <= float(value) <= float(hi):
                    return False
        except (TypeError, ValueError):
            return False
    return True


def _jsonable(obj: Any) -> Any:
    """Whatever came out of the repo, as something an MCP reply can carry.

    A `PaperBook` holds a whole `Strategy` dataclass, and a tool that returned
    it raw would serialise to a REPR on the far side -- readable to nobody and
    parseable by nothing, which is the same class of failure as returning a
    number with no units. Nested dataclasses are walked into rather than
    stringified; anything left over falls back to `str` so an unexpected type
    degrades to something legible instead of raising inside an MCP reply.
    """
    import dataclasses

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _jsonable(getattr(obj, f.name, None))
                for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _project(row: dict, fields: Iterable[str] | None) -> dict:
    if not fields:
        return dict(row)
    return {k: row.get(k) for k in fields}


# ------------------------------------------------------------------ panel

def panel_query(fields: list[str] | None = None, filters: dict | None = None,
                limit: int = DEFAULT_LIMIT, as_of: str | None = None) -> dict:
    """The joined news-return panel, field-filtered and bounded.

    `as_of` is a PIT cut-off applied to the row's OWN `first_seen_utc` -- the
    stamp WE wrote when the item reached us, never the publisher's
    `published_utc`, which a vendor can backdate. A row whose anchor cannot be
    read is EXCLUDED by an `as_of` query rather than admitted: a stamp the
    code cannot parse must never be treated as early enough.
    """
    n = _check_limit(limit)
    path = _sandboxed(DATA().joinpath(*NEWS_PANEL))
    if not path.is_file():
        return {"rows": [], "n": 0, "truncated": False, "as_of_applied": as_of,
                "available": False,
                "why": f"CANNOT DETERMINE, no panel at {path}"}
    import pandas as pd

    df = pd.read_parquet(path)
    anchor = n_no_anchor = None
    if as_of:
        anchor = ("first_seen_utc" if "first_seen_utc" in df.columns
                  else "published_utc")
        stamps = pd.to_datetime(df[anchor], errors="coerce", utc=True)
        cut = pd.to_datetime(as_of, utc=True, errors="coerce")
        if cut is None or pd.isna(cut):
            raise QueryRefused(
                f"as_of={as_of!r} is not a date this surface can parse; a "
                f"cut-off nobody can read is a query with no cut-off")
        # ROWS WITH NO READABLE ANCHOR ARE EXCLUDED AND COUNTED. On this
        # checkout only 808 of 340,465 panel rows carry a `first_seen_utc` --
        # the rest predate the stamp -- so an `as_of` query returns almost
        # nothing, and a caller who saw only the empty result would read it as
        # "no news before that date" rather than "the anchor is thin". A stamp
        # the code cannot read must never be treated as early enough, and the
        # count of what that cost is in the reply.
        keep = stamps.notna() & (stamps <= cut)
        n_no_anchor = int(stamps.isna().sum())
        df = df[keep]
    out, total = [], 0
    for rec in df.to_dict("records"):
        if not _matches(rec, filters):
            continue
        total += 1
        if len(out) < n:
            out.append(_project(rec, fields))
    return {"rows": out, "n": len(out), "n_matched": total,
            "truncated": total > len(out), "as_of_applied": as_of,
            "as_of_anchor": anchor,
            "n_dropped_no_readable_anchor": n_no_anchor,
            "available": True, "source": str(path),
            "pit_note": ("`as_of` cuts on `first_seen_utc`, the stamp this "
                         "repository wrote, not on the publisher's date, and "
                         "a row whose anchor cannot be read is EXCLUDED and "
                         "counted in `n_dropped_no_readable_anchor`")}


# ------------------------------------------------------------------- farm

def farm_query(preset: str | None = None, family_id: str | None = None,
               state: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """`evidence_memory`'s registry rows -- the SAME function the export calls.

    Reading through `registry_rows()` rather than re-deriving means this tool
    cannot diverge from what the allocator itself sees. Two views of one
    evidence base is how a leaderboard and a registry start disagreeing.
    """
    n = _check_limit(limit)
    from learner import evidence_memory as EM

    rows, meta = EM.registry_rows()
    out = []
    for r in rows:
        if family_id and str(r.get("family")) != family_id:
            continue
        if state and str(r.get("state")) != state:
            continue
        if preset and preset not in str(r.get("representative_cell") or ""):
            continue
        out.append(r)
    return {"rows": out[:n], "n": min(len(out), n), "n_matched": len(out),
            "truncated": len(out) > n, "meta": meta, "available": True,
            "source": "learner.evidence_memory.registry_rows"}


# ---------------------------------------------------------------- receipts

def receipt(job: str, run: str | None = None) -> dict:
    """One job's receipt by name, newest night first, or CANNOT DETERMINE.

    Night directories are searched in NAME order, never mtime: on a fresh CI
    checkout every file is written today, so an mtime order is an order on
    checkout time (CLAUDE.md session protocol item 7).
    """
    if not job or not str(job).strip():
        raise QueryRefused("receipt() needs a job name; an empty job would "
                           "match whichever file sorted first")
    if any(sep in str(job) for sep in ("/", "\\", "..")):
        raise QueryRefused(
            f"REFUSED: job {job!r} contains a path separator. A job name is a "
            f"name; a path here is a file-read primitive.")
    root = DATA()
    if not root.is_dir():
        return {"available": False,
                "why": f"CANNOT DETERMINE, no data root at {root}"}
    pattern = (f"{job}_run{int(run):02d}*.json" if run is not None
               and str(run).isdigit() else f"{job}_run*.json")
    hits: list[Path] = []
    for night in sorted((p for p in root.iterdir()
                         if p.is_dir() and p.name.startswith("night_factory_")),
                        key=lambda p: p.name, reverse=True):
        hits.extend(sorted(night.glob(pattern), key=lambda p: p.name))
    if not hits:
        return {"available": False, "job": job, "run": run,
                "why": (f"CANNOT DETERMINE, no receipt at "
                        f"{root}/night_factory_*/{pattern}")}
    path = _sandboxed(hits[0])
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError as exc:
        return {"available": False, "job": job, "run": run,
                "why": f"receipt at {path} is not readable JSON ({exc})"}
    return {"available": True, "job": job, "run": run, "path": str(path),
            "n_nights_searched": len(hits), "receipt": payload}


# -------------------------------------------------------------- leaderboard

def leaderboard(limit: int = DEFAULT_LIMIT) -> dict:
    """The registry export's `conditional_evidence` block, exactly as written.

    Read from `backend/data/signal_registry.yaml` -- what `to_registry()`
    wrote -- rather than recomputed, so this answers "what does the registry
    say" and not "what would it say if recomputed now", which are different
    questions and only the first one is what the allocator reads.
    """
    n = _check_limit(limit)
    path = (_repo_root() / "backend" / "data" / "signal_registry.yaml")
    if not path.is_file():
        return {"available": False, "rows": [], "n": 0,
                "why": f"CANNOT DETERMINE, no registry at {path}"}
    try:
        import yaml
        blob = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:                                   # noqa: BLE001
        return {"available": False, "rows": [], "n": 0,
                "why": f"registry at {path} did not parse ({exc})"}
    block = blob.get("conditional_evidence") or {}
    # `rules` is what `to_registry()` actually writes; `families` was the
    # earlier name. Both are read and the key that answered is REPORTED, so a
    # rename shows up as a changed field rather than as an empty leaderboard
    # that looks like an empty registry.
    rows, key = None, None
    if isinstance(block, dict):
        for candidate in ("rules", "families", "rows"):
            if isinstance(block.get(candidate), list):
                rows, key = block[candidate], candidate
                break
    elif isinstance(block, list):
        rows, key = block, "conditional_evidence"
    if rows is None:
        return {"available": False, "rows": [], "n": 0, "source": str(path),
                "why": ("CANNOT DETERMINE: the registry's "
                        "`conditional_evidence` block carries no row list "
                        f"under rules/families/rows; it has {sorted(block)}"
                        if isinstance(block, dict) else
                        "CANNOT DETERMINE: no `conditional_evidence` block")}
    full = list(rows)
    return {"available": True, "rows": full[:n], "n": min(len(full), n),
            "n_matched": len(full), "truncated": len(full) > n,
            "rows_key": key, "source": str(path),
            "generated_by": (block.get("generated_by")
                             if isinstance(block, dict) else None),
            "read_only_until": (block.get("read_only_until")
                                if isinstance(block, dict) else None)}


# -------------------------------------------------------------------- books

def books(limit: int = DEFAULT_LIMIT, include_shadow: bool = False) -> dict:
    """The declared paper books, read through `paper_books` and never a path.

    `include_shadow` is off by default: a shadow book is a diagnostic and
    listing it beside the live ones is how a diagnostic gets quoted as a
    track record.
    """
    n = _check_limit(limit)
    try:
        from backend.services import paper_books as PB
    except Exception as exc:                                   # noqa: BLE001
        return {"available": False, "rows": [], "n": 0,
                "why": f"paper_books did not import ({exc})"}
    lister = (getattr(PB, "all_books", None) or getattr(PB, "list_books", None)
              or getattr(PB, "load_all", None))
    if lister is None:
        return {"available": False, "rows": [], "n": 0,
                "why": ("CANNOT DETERMINE: `paper_books` exposes no listing "
                        "function this surface knows about. Named rather than "
                        "guessed -- a reader that fell back to globbing the "
                        "book directory would report files, not books.")}
    try:
        found = list(lister())
    except Exception as exc:                                   # noqa: BLE001
        return {"available": False, "rows": [], "n": 0,
                "why": f"listing books raised {type(exc).__name__}: {exc}"}
    import dataclasses

    rows = []
    for b in found:
        if isinstance(b, dict):
            row = dict(b)
        elif dataclasses.is_dataclass(b):
            # THE BOOK'S OWN FIELDS, not a hand-written list. A fixed list of
            # names silently returns None for every field the dataclass
            # renamed, which reads as "this book has no licence" rather than
            # as "this reader is out of date".
            row = {f.name: getattr(b, f.name, None)
                   for f in dataclasses.fields(b)}
        else:
            row = {"book": str(b)}
        if not include_shadow and bool(row.get("shadow")):
            continue
        rows.append(row)
    return {"available": True, "rows": _jsonable(rows[:n]),
            "n": min(len(rows), n),
            "n_matched": len(rows), "truncated": len(rows) > n,
            "include_shadow": bool(include_shadow),
            "source": "backend.services.paper_books"}


#: The five signatures the `optimus` MCP wraps. Declared as DATA so the
#: doc, the MCP registration and this module cannot fall out of step -- the
#: test asserts this list against what the module actually defines.
SURFACE = ("panel_query", "farm_query", "receipt", "leaderboard", "books")
