"""Every dataset on this machine, in one receipt: what it is, where, how big, who reads it.

    python -m backend.services.data_catalog                 # walk, write the receipt + docs/DATA_CATALOG.md
    python -m backend.services.data_catalog --query bars    # "do we have X?" from the newest receipt
    python -m backend.services.data_catalog --no-doc        # receipt only

WHY (owner, 2026-10-06)
=======================
"We have lost media in folders, data we downloaded and forgot, we pull the same
data again." `docs/DATA_MANIFEST.md` is hand-written and covers what someone
remembered to add; 77 GB / ~40,000 files sit under `backend/data/` and most of
them are in no manifest. A session that cannot find a panel pulls it again, and
absence of a RECORD is how that happens (CLAUDE.md: absence of a local object is
not evidence of absence -- and absence of a catalogue row is not either, which is
why this one is derived by walking the disk, not written by hand).

ONE ROW PER DATASET
-------------------
* A file of a dataset kind (parquet, jsonl, sqlite, gguf, csv, npy, joblib, ...)
  or any file >= `DATA_CATALOG_OWN_ROW_MIN_BYTES` is its own row.
* Everything else (small JSON receipts, logs, text) is rolled up into ONE row for
  its directory (kind `dir`): file count, bytes, extension mix, a LISTING hash
  (names + sizes, labelled as such -- not a content hash).

Per row: id (path-derived), path, kind, bytes, rows where cheap (parquet footer;
jsonl/csv line count only under the full-hash ceiling), a date range DERIVED
FROM THE DATA (parquet column statistics; first/last rows of a jsonl; a JSON
receipt's own stamp) with the method named, a schema hash, a content sha256
(full under 200 MB, else size + first/last 1 MB, labelled), provenance (from
DATA_MANIFEST.md, a committed ledger manifest, or a `.meta.json` sidecar; else
`UNKNOWN_PROVENANCE`), git status, and downstream CONSUMERS found by searching
the repo's code for the file's name, family or directory (heuristic; the match
level is on the row). A row with no code consumer is an ORPHAN.

DATED BY THE RUN, NEVER BY mtime
--------------------------------
The receipt's stamp and `run_id` come from the run clock. No row carries an
mtime, and no date range is ever read from the filesystem (protocol item 7: a
fresh checkout writes every file "today"). mtime is used for exactly one thing:
as half of the CACHE KEY (size + mtime_ns) that lets a nightly rerun skip
re-hashing 70 GB. A touched file is re-inspected and produces the same row.

PATHS
-----
Repo paths are repo-relative. A root outside the repo (the GGUF directory) is
written as `<llama models>/...` -- no home directory in a receipt or a doc.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import re
import sqlite3
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

OPT = Path(_config.OPTIMUS_LEDGER_DIR)
CATALOG_DIR = OPT / "data_catalog"
CACHE_PATH = CATALOG_DIR / "file_cache.json"
DOC_PATH = REPO / "docs" / "DATA_CATALOG.md"
MANIFEST_DOC = REPO / "docs" / "DATA_MANIFEST.md"

FULL_HASH_MAX = int(getattr(_config, "DATA_CATALOG_FULL_HASH_MAX_BYTES", 200 * 1024 * 1024))
OWN_ROW_MIN = int(getattr(_config, "DATA_CATALOG_OWN_ROW_MIN_BYTES", 5 * 1024 * 1024))
LLAMA_ENV = str(getattr(_config, "DATA_CATALOG_LLAMA_MODELS_ENV", "AEGIS_LLAMA_MODELS_DIR"))
HEAD_TAIL = 1024 * 1024
SAMPLE_ROWS = 200
#: Bump when the inspection logic changes, so cached results are recomputed.
CACHE_VERSION = 3
UNKNOWN = "UNKNOWN_PROVENANCE"

KIND_BY_EXT = {
    ".parquet": "parquet", ".jsonl": "jsonl", ".json": "json", ".sqlite": "sqlite",
    ".sqlite3": "sqlite", ".db": "sqlite", ".gguf": "gguf", ".csv": "csv", ".npy": "npy",
    ".npz": "npz", ".joblib": "joblib", ".pt": "pt", ".pkl": "pkl", ".zip": "zip",
    ".feather": "feather", ".arrow": "arrow", ".h5": "h5",
}
#: Kinds that are a dataset at any size.
DATASET_KINDS = {"parquet", "jsonl", "sqlite", "gguf", "csv", "npy", "npz", "joblib", "pt",
                 "pkl", "zip", "feather", "arrow", "h5"}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}
DATE_NAMES = ("date", "datadate", "ts", "utc", "timestamp", "datetime", "asof", "as_of",
              "trade_date", "observed_at_utc", "time", "day", "dt", "caldt", "anndats",
              "statpers", "fdate", "rdate", "generated_at", "created_at")
STAMP_KEYS = ("generated_at", "generated_at_utc", "utc", "asof", "as_of", "created_at",
              "run_utc", "written_at", "ts")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".cmd", ".ps1", ".bat", ".sh",
            ".vbs", ".yaml", ".yml", ".toml"}
#: Directory names too generic to identify a consumer.
GENERIC_DIRS = {"data", "optimus", "backend", "receipts", "raw", "parsed", "cache", "tmp",
                "logs", "log", "out", "state", "table", "models", "predictions", "bulk",
                "archive", "history", "runs", "results", "output", "inputs", "work"}
TOKEN = re.compile(r"[A-Za-z0-9_.\-]+")

#: Paths that code BUILDS at run time from a variable, so no static token names
#: them (review F7). Each entry is a glob over the catalog path plus the code
#: that builds it, as `file:line` and the exact snippet; a test checks the
#: snippet is still in that file, so an entry cannot outlive the code. A match
#: reads `RUNTIME_BUILT`, never "no static reference".
RUNTIME_PATTERNS: tuple[dict, ...] = (
    {"glob": "backend/data/optimus/contest/bars/bars_*.parquet",
     "built_by": "scripts/contest_calendar.py:453",
     "snippet": 'BARS_DIR / f"bars_{market}.parquet"'},
    {"glob": "backend/data/optimus/wrds/bulk/*__*.parquet",
     "built_by": "scripts/wrds_pull_catchup.py:620 (also wrds_pull_everything.py:288)",
     "snippet": "BULK / f\"{p['schema']}__{p['table']}.parquet\""},
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================ roots + walk

@dataclass(frozen=True)
class Root:
    label: str
    path: Path
    #: None = display repo-relative; else this prefix replaces the root path.
    display_prefix: Optional[str] = None


def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT` (frozen-path defect family).

    Inside the packaged app `__file__` lives under `_internal/`, which carries
    no `backend/data`, so a catalogue rooted there would walk an empty tree and
    report nothing without failing. `test_frozen_path_family.py` is the gate.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return REPO


def default_roots() -> list[Root]:
    llama = os.getenv(LLAMA_ENV)
    repo = _repo_root()
    return [
        Root("data", repo / "backend" / "data"),
        Root("ft_lab", repo / "ft_lab" / "data"),
        Root("llama_models", Path(llama) if llama else Path.home() / "llama" / "models",
             "<llama models>"),
    ]


def _display(root: Root, p: Path) -> str:
    rel = p.relative_to(root.path).as_posix()
    if root.display_prefix is not None:
        return f"{root.display_prefix}/{rel}" if rel != "." else root.display_prefix
    try:
        return p.resolve().relative_to(_repo_root()).as_posix()
    except ValueError:
        return f"<{root.label}>/{rel}"


@dataclass
class FileEntry:
    abs: Path
    display: str
    root: str
    size: int
    mtime_ns: int
    ext: str
    in_repo: bool


def walk(roots: Iterable[Root], *, skip: Iterable[Path] = ()) -> list[FileEntry]:
    skip_set = {Path(s).resolve() for s in skip}
    out: list[FileEntry] = []
    for root in roots:
        if not root.path.exists():
            continue
        in_repo = root.display_prefix is None
        stack = [root.path]
        while stack:
            d = stack.pop()
            if d.resolve() in skip_set:
                continue
            try:
                it = list(os.scandir(d))
            except OSError:
                continue
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name not in SKIP_DIRS:
                            stack.append(Path(e.path))
                        continue
                    if not e.is_file(follow_symlinks=False):
                        continue
                    st = e.stat()
                except OSError:
                    continue
                p = Path(e.path)
                name = e.name.lower()
                ext = ".meta.json" if name.endswith(".meta.json") else Path(name).suffix
                out.append(FileEntry(p, _display(root, p), root.label, st.st_size,
                                     st.st_mtime_ns, ext, in_repo))
    return out


def kind_of(ext: str) -> str:
    if ext == ".meta.json":
        return "json"
    return KIND_BY_EXT.get(ext, ext.lstrip(".") or "none")


def is_own_row(fe: FileEntry, own_row_min: int = OWN_ROW_MIN) -> bool:
    return kind_of(fe.ext) in DATASET_KINDS or fe.size >= own_row_min


# ============================================================ inspection

def content_hash(path: Path, size: int, full_max: int = FULL_HASH_MAX) -> dict:
    """Full sha256 under `full_max`; else size + first/last 1 MB, labelled."""
    h = hashlib.sha256()
    if size <= full_max:
        nl = 0
        last = b""
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8 << 20), b""):
                h.update(chunk)
                nl += chunk.count(b"\n")
                last = chunk[-1:]
        return {"sha256": h.hexdigest(), "mode": "full", "_newlines": nl,
                "_ends_nl": last == b"\n"}
    h.update(f"size={size}".encode())
    with path.open("rb") as fh:
        h.update(fh.read(HEAD_TAIL))
        fh.seek(max(0, size - HEAD_TAIL))
        h.update(fh.read(HEAD_TAIL))
    return {"sha256": h.hexdigest(), "mode": "size+head1MB+tail1MB"}


def _schema_hash(items: list) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:16]


def _iso(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bytes):
        try:
            v = v.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(v, str) and _ISO.match(v):
        return v[:10]
    return None


def _sentinel(rng: dict) -> bool:
    try:
        return not (1900 < int(rng["min"][:4]) and int(rng["max"][:4]) <= 2030)
    except (TypeError, ValueError, KeyError):
        return False


def inspect_parquet(path: Path) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    md = pf.metadata
    schema = pf.schema_arrow
    cols = [[f.name, str(f.type)] for f in schema]
    out: dict = {"rows": md.num_rows, "rows_method": "parquet footer",
                 "schema": cols[:80], "n_columns": len(cols), "schema_hash": _schema_hash(cols)}
    temporal = [f.name for f in schema
                if pa.types.is_temporal(f.type) and not pa.types.is_time(f.type)]
    named = [f.name for f in schema if f.name.lower() in DATE_NAMES
             and (pa.types.is_string(f.type) or pa.types.is_large_string(f.type)
                  or pa.types.is_temporal(f.type))]
    order = sorted(set(temporal) | set(named),
                   key=lambda n: (n not in temporal,
                                  DATE_NAMES.index(n.lower()) if n.lower() in DATE_NAMES else 99))
    paths = {md.schema.column(j).path: j for j in range(md.num_columns)}
    for col in order:
        j = paths.get(col)
        if j is None:
            continue
        lo = hi = None
        for i in range(md.num_row_groups):
            st = md.row_group(i).column(j).statistics
            if st is None or not st.has_min_max:
                continue
            a, b = _iso(st.min), _iso(st.max)
            if a and (lo is None or a < lo):
                lo = a
            if b and (hi is None or b > hi):
                hi = b
        if lo and hi:
            rng = {"min": lo, "max": hi, "column": col, "method": "parquet column statistics"}
            rng["sentinel"] = _sentinel(rng)
            out["date_range"] = rng
            break
    return out


def _sample_lines(path: Path, size: int, n: int = SAMPLE_ROWS) -> tuple[list[bytes], list[bytes]]:
    with path.open("rb") as fh:
        head = fh.read(min(size, HEAD_TAIL))
        fh.seek(max(0, size - HEAD_TAIL))
        tail = fh.read(HEAD_TAIL)
    h = head.split(b"\n")
    if len(head) < size:
        h = h[:-1]                       # last piece may be cut mid-line
    t = tail.split(b"\n")
    if size > HEAD_TAIL:
        t = t[1:]                        # first piece may be cut mid-line
    return [x for x in h if x.strip()][:n], [x for x in t if x.strip()][-n:]


def _jtype(v: Any) -> str:
    return {dict: "object", list: "array", str: "string", bool: "bool", int: "int",
            float: "float", type(None): "null"}.get(type(v), "other")


def _stamp(row: Any) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(row, dict):
        return None, None
    for k in ("ts", "utc", "timestamp", "date", "created_at", "observed_at_utc",
              "generated_at", "asof", "as_of", "day"):
        s = _iso(row.get(k))
        if s:
            return s, k
    return None, None


def inspect_jsonl(path: Path, size: int, hashed: dict) -> dict:
    head, tail = _sample_lines(path, size)
    keys: dict[str, set] = defaultdict(set)
    stamps: list[str] = []
    fields: Counter = Counter()
    for ln in head + tail:
        try:
            row = json.loads(ln)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(row, dict):
            for k, v in row.items():
                keys[k].add(_jtype(v))
        s, f = _stamp(row)
        if s:
            stamps.append(s)
            fields[f] += 1
    cols = sorted([k, "|".join(sorted(t))] for k, t in keys.items())
    out: dict = {"schema": cols[:80], "n_columns": len(cols), "schema_hash": _schema_hash(cols),
                 "schema_method": f"union of keys over first/last {SAMPLE_ROWS} rows"}
    if hashed.get("mode") == "full":
        out["rows"] = hashed["_newlines"] + (0 if hashed["_ends_nl"] or size == 0 else 1)
        out["rows_method"] = "line count"
    else:
        out["rows"] = None
        out["rows_method"] = f"skipped: over {FULL_HASH_MAX // (1024 * 1024)} MB"
    if stamps:
        f = fields.most_common(1)[0][0]
        out["date_range"] = {"min": min(stamps), "max": max(stamps), "column": f,
                             "method": f"row field '{f}' over first/last {SAMPLE_ROWS} rows"}
    return out


def inspect_json(path: Path, size: int) -> dict:
    if size > 50 * 1024 * 1024:
        return {"schema_method": "skipped: JSON over 50 MB is not parsed"}
    try:
        obj = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return {"error": f"unparseable JSON ({type(exc).__name__})"}
    out: dict = {}
    if isinstance(obj, dict):
        cols = sorted([k, _jtype(v)] for k, v in obj.items())
        out.update(schema=cols[:80], n_columns=len(cols), schema_hash=_schema_hash(cols),
                   schema_method="top-level keys")
        for k in ("rows", "data", "records", "items"):
            if isinstance(obj.get(k), list):
                out.update(rows=len(obj[k]), rows_method=f"len(top-level '{k}')")
                break
        for k in STAMP_KEYS:
            s = _iso(obj.get(k))
            if s:
                out["date_range"] = {"min": s, "max": s, "column": k,
                                     "method": f"the receipt's own top-level '{k}'"}
                break
    elif isinstance(obj, list):
        out.update(rows=len(obj), rows_method="len(top-level list)",
                   schema=[["<list>", "array"]], schema_hash=_schema_hash(["<list>"]))
    return out


def inspect_csv(path: Path, size: int, hashed: dict) -> dict:
    head, tail = _sample_lines(path, size, n=2)
    if not head:
        return {}
    header = head[0].decode("utf-8", "replace").strip().split(",")
    cols = [[c.strip().strip('"'), "csv"] for c in header]
    out: dict = {"schema": cols[:80], "n_columns": len(cols), "schema_hash": _schema_hash(cols),
                 "schema_method": "header row"}
    if hashed.get("mode") == "full":
        n = hashed["_newlines"] + (0 if hashed["_ends_nl"] else 1)
        out.update(rows=max(0, n - 1), rows_method="line count minus header")
    low = [c[0].lower() for c in cols]
    j = next((i for i, c in enumerate(low) if c in DATE_NAMES), None)
    if j is not None and len(head) > 1 and tail:
        vals = []
        for ln in (head[1], tail[-1]):
            parts = ln.decode("utf-8", "replace").split(",")
            if j < len(parts):
                s = _iso(parts[j].strip().strip('"'))
                if s:
                    vals.append(s)
        if vals:
            out["date_range"] = {"min": min(vals), "max": max(vals), "column": cols[j][0],
                                 "method": "first and last data row"}
    return out


def inspect_sqlite(path: Path, size: int) -> dict:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
    try:
        tables = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' order by name")]
        cols, rows = [], 0
        for t in tables[:200]:
            for c in con.execute(f'pragma table_info("{t}")'):
                cols.append([f"{t}.{c[1]}", str(c[2])])
            if size <= FULL_HASH_MAX:
                rows += con.execute(f'select count(*) from "{t}"').fetchone()[0]
        out = {"schema": cols[:80], "n_columns": len(cols), "schema_hash": _schema_hash(cols),
               "schema_method": f"{len(tables)} table(s)"}
        if size <= FULL_HASH_MAX:
            out.update(rows=rows, rows_method="sum of count(*) over tables")
        return out
    finally:
        con.close()


def inspect_npy(path: Path) -> dict:
    import numpy as np

    with path.open("rb") as fh:
        ver = np.lib.format.read_magic(fh)
        shape, _, dtype = (np.lib.format.read_array_header_1_0(fh) if ver == (1, 0)
                           else np.lib.format.read_array_header_2_0(fh))
    cols = [["shape", str(list(shape))], ["dtype", str(dtype)]]
    return {"rows": int(shape[0]) if shape else None, "rows_method": "npy header",
            "schema": cols, "schema_hash": _schema_hash(cols)}


def inspect_gguf(path: Path) -> dict:
    with path.open("rb") as fh:
        head = fh.read(24)
    if head[:4] != b"GGUF":
        return {"error": "no GGUF magic"}
    ver, n_t, n_kv = struct.unpack("<IQQ", head[4:24])
    cols = [["gguf_version", str(ver)], ["tensors", str(n_t)], ["metadata_kv", str(n_kv)]]
    return {"schema": cols, "schema_hash": _schema_hash(cols), "schema_method": "GGUF header"}


def inspect_file(fe: FileEntry, *, full_max: int = FULL_HASH_MAX) -> dict:
    """The expensive, cacheable part of a file row. Never reads mtime."""
    kind = kind_of(fe.ext)
    res: dict = {}
    try:
        hashed = content_hash(fe.abs, fe.size, full_max)
        res["content"] = {"sha256": hashed["sha256"], "mode": hashed["mode"]}
        if kind == "parquet":
            res.update(inspect_parquet(fe.abs))
        elif kind == "jsonl":
            res.update(inspect_jsonl(fe.abs, fe.size, hashed))
        elif kind == "json":
            res.update(inspect_json(fe.abs, fe.size))
        elif kind == "csv":
            res.update(inspect_csv(fe.abs, fe.size, hashed))
        elif kind == "sqlite":
            res.update(inspect_sqlite(fe.abs, fe.size))
        elif kind == "npy":
            res.update(inspect_npy(fe.abs))
        elif kind == "gguf":
            res.update(inspect_gguf(fe.abs))
    except Exception as exc:                                       # noqa: BLE001
        res["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return res


# ============================================================ cache

def load_cache(path: Path) -> dict:
    try:
        c = json.loads(Path(path).read_text(encoding="utf-8"))
        return c if c.get("v") == CACHE_VERSION else {"v": CACHE_VERSION, "files": {}}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {"v": CACHE_VERSION, "files": {}}


def save_cache(path: Path, cache: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


# ============================================================ provenance

@dataclass
class ProvRule:
    regex: re.Pattern
    pattern: str
    produced_by: Optional[str]
    source: str
    prefix: bool


def _glob_regex(pat: str) -> tuple[re.Pattern, bool]:
    prefix = pat.endswith("/")
    pat2 = re.sub(r"<[^>]+>", "\x00", pat)
    rx = re.escape(pat2).replace(r"\*", "[^/]*").replace("\x00", "[^/]*")
    return re.compile("^" + rx + (".*" if prefix else "$")), prefix


def load_manifest_rules(text: str) -> list[ProvRule]:
    """Rules from DATA_MANIFEST.md: table rows (path glob + 'Produced by') and,
    weaker, backticked repo paths in prose."""
    rules: list[ProvRule] = []
    produced_col: Optional[int] = None
    in_table_paths: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            # prose ends a table; a blank line does not (DATA_MANIFEST.md has
            # rows of one table separated by a blank line)
            produced_col = produced_col if not s else None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        hdr = [c.lower() for c in cells]
        if any(h.startswith("produced by") for h in hdr):
            produced_col = next(i for i, h in enumerate(hdr) if h.startswith("produced by"))
            continue
        if set(s.replace("|", "").strip()) <= set("-: "):
            continue
        toks = re.findall(r"`([^`]+)`", cells[0]) if cells else []
        path = next((t for t in toks if "/" in t), None)
        if not path:
            continue
        produced = None
        if produced_col is not None and produced_col < len(cells):
            produced = cells[produced_col].replace("`", "").strip() or None
        rx, pre = _glob_regex(path)
        rules.append(ProvRule(rx, path, produced, "DATA_MANIFEST.md table", pre))
        in_table_paths.add(path)
    for tok in set(re.findall(r"`(backend/data/[^`\s]+)`", text)) - in_table_paths:
        # A prose mention counts only for an exact file (or a file glob): a
        # passing "`backend/data/optimus/`" in a sentence would otherwise claim
        # provenance for 70 GB. Directory prefixes count only in TABLE rows,
        # where a producer is named.
        if tok.endswith("/"):
            continue
        rx, pre = _glob_regex(tok)
        rules.append(ProvRule(rx, tok, None, "DATA_MANIFEST.md prose", pre))
    # table rules first: they carry a producer
    return sorted(rules, key=lambda r: r.source != "DATA_MANIFEST.md table")


def provenance_for(display: str, *, rules: list[ProvRule], is_dir: bool = False,
                   sidecar: Optional[dict] = None, ledger_manifest: Optional[dict] = None) -> dict:
    for r in rules:
        if r.source != "DATA_MANIFEST.md table":
            continue
        if r.regex.match(display) or (is_dir and r.prefix and (display + "/").startswith(
                r.pattern)):
            return {"source": r.source, "pattern": r.pattern, "produced_by": r.produced_by}
    if ledger_manifest:
        return {"source": "ledger_manifest", "manifest": ledger_manifest["path"],
                "produced_by": ledger_manifest.get("command")}
    if sidecar:
        return {"source": "sidecar .meta.json", "pulled_at": sidecar.get("pulled_at"),
                "produced_by": sidecar.get("script") or sidecar.get("produced_by")}
    for r in rules:
        if r.source == "DATA_MANIFEST.md table":
            continue
        if r.regex.match(display) or (is_dir and r.prefix and (display + "/").startswith(
                r.pattern)):
            return {"source": r.source, "pattern": r.pattern, "produced_by": None}
    return {"source": UNKNOWN}


# ============================================================ git

def _git(args: list[str], stdin: Optional[str] = None) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(_repo_root()), input=stdin, capture_output=True,
                           text=True, encoding="utf-8", timeout=300)
    except Exception:                                              # noqa: BLE001
        return None
    if r.returncode not in (0, 1):
        return None
    return r.stdout


def git_status_map(paths: list[str]) -> dict[str, str]:
    """tracked / ignored / untracked per repo-relative path; `unknown` if git
    cannot be asked (CANNOT DETERMINE is not 'untracked')."""
    out = _git(["ls-files", "-z", "--", "backend/data", "ft_lab"])
    if out is None:
        return {p: "unknown" for p in paths}
    tracked = set(out.split("\0"))
    rest = [p for p in paths if p not in tracked]
    ign = _git(["check-ignore", "--stdin", "-z"], stdin="\0".join(rest) + "\0") if rest else ""
    if ign is None:
        return {p: ("tracked" if p in tracked else "unknown") for p in paths}
    ignored = set(ign.split("\0"))
    return {p: "tracked" if p in tracked else "ignored" if p in ignored else "untracked"
            for p in paths}


# ============================================================ consumers

@dataclass
class TokenIndex:
    """token -> set of file ids, plus a sorted token list for prefix search."""
    files: list[str] = field(default_factory=list)
    index: dict[str, set] = field(default_factory=dict)
    sorted_tokens: list[str] = field(default_factory=list)

    @classmethod
    def from_texts(cls, texts: dict[str, str]) -> "TokenIndex":
        ix = cls()
        for i, (name, text) in enumerate(sorted(texts.items())):
            ix.files.append(name)
            for tok in set(TOKEN.findall(text)):
                ix.index.setdefault(tok, set()).add(i)
        ix.sorted_tokens = sorted(ix.index)
        return ix

    def exact(self, tok: str) -> set:
        return self.index.get(tok, set())

    def family(self, fam: str) -> set:
        hit: set = set()
        i = bisect.bisect_left(self.sorted_tokens, fam)
        while i < len(self.sorted_tokens) and self.sorted_tokens[i].startswith(fam):
            t = self.sorted_tokens[i]
            if t == fam or t[len(fam)] in "_.-":
                hit |= self.index[t]
            i += 1
        return hit


def _repo_files(exts: set[str], *, include: tuple[str, ...] = (),
                exclude: tuple[str, ...] = ()) -> list[str]:
    tracked = _git(["ls-files", "-z"]) or ""
    others = _git(["ls-files", "-z", "--others", "--exclude-standard"]) or ""
    out = []
    for p in set(tracked.split("\0")) | set(others.split("\0")):
        if not p or Path(p).suffix.lower() not in exts:
            continue
        if include and not p.startswith(include):
            continue
        if exclude and p.startswith(exclude):
            continue
        out.append(p)
    return sorted(out)


def build_code_index() -> TokenIndex:
    files = _repo_files(CODE_EXT, exclude=("backend/data/", "docs/", "frontend/.next/",
                                           "build/", "dist/", ".venv/"))
    texts = {}
    for p in files:
        try:
            texts[p] = (_repo_root() / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return TokenIndex.from_texts(texts)


def build_doc_index() -> TokenIndex:
    files = _repo_files({".md"}, include=("docs/",), exclude=("docs/DATA_CATALOG.md",))
    texts = {}
    for p in files:
        try:
            texts[p] = (_repo_root() / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return TokenIndex.from_texts(texts)


def family_of(stem: str) -> str:
    """`llm_calls_2026-09` -> `llm_calls`; `crsp_dsf_1990` -> `crsp_dsf`."""
    f = re.sub(r"[_\-.]?\d{4}[-_]?\d{2}(?:[-_]?\d{2})?(?:[T_.]?\d{4,6}Z?)?.*$", "", stem)
    prev = None
    while prev != f:
        prev = f
        f = re.sub(r"[_\-.]+\d+$", "", f).rstrip("_-.")
    return f


def consumers_for(display: str, ix: TokenIndex, *, is_dir: bool = False,
                  max_df: int = 25) -> dict:
    """Code files naming this dataset: by basename, stem, family, then directory."""
    p = Path(display)
    name = p.name
    levels: list[tuple[str, str, set]] = []
    if is_dir:
        if name.lower() not in GENERIC_DIRS and len(name) >= 4:
            levels.append(("dir_name", name, ix.exact(name)))
    else:
        stem = name.split(".")[0] if not name.startswith(".") else name
        levels.append(("basename", name, ix.exact(name)))
        if len(stem) >= 6 and stem != name:
            levels.append(("stem", stem, ix.exact(stem)))
        fam = family_of(stem)
        if fam != stem and len(fam) >= 5:
            levels.append(("family", fam, ix.family(fam)))
    for anc in (p.parent.name, p.parent.parent.name):
        if anc and anc.lower() not in GENERIC_DIRS and len(anc) >= 4:
            hits = ix.exact(anc)
            if 0 < len(hits) <= max_df:
                levels.append(("dir:" + anc, anc, hits))
    tests_only: Optional[dict] = None
    for level, tok, hits in levels:
        if hits:
            names = sorted(ix.files[i] for i in hits)
            code = [n for n in names if "/tests/" not in n and not n.startswith("tests/")
                    and not Path(n).name.startswith("test_")]
            res = {"match": level, "token": tok, "n": len(code),
                   "n_tests": len(names) - len(code), "files": (code or names)[:5]}
            if code:
                return res
            # named only by tests at this level: a weaker level may still find
            # the code that reads it (`llm_calls_2026-08.jsonl` -> family)
            tests_only = tests_only or res
    return tests_only or {"match": None, "n": 0, "n_tests": 0, "files": []}


def runtime_built(display: str, patterns: Iterable[dict] = RUNTIME_PATTERNS) -> Optional[dict]:
    """The declared runtime pattern this path matches, or None. `*` stays
    inside one path segment."""
    for pat in patterns:
        rx = "^" + re.escape(pat["glob"]).replace(r"\*", "[^/]*") + "$"
        if re.match(rx, display):
            return pat
    return None


def doc_mentions(display: str, ix: TokenIndex) -> int:
    name = Path(display).name
    stem = name.split(".")[0]
    hits = ix.exact(name) | (ix.exact(stem) if len(stem) >= 6 else set())
    fam = family_of(stem)
    if fam != stem and len(fam) >= 5:
        hits |= ix.family(fam)
    return len(hits)


# ============================================================ build

def _consumers_or_runtime(display: str, ix: TokenIndex) -> dict:
    c = consumers_for(display, ix)
    if c["n"] == 0:
        rt = runtime_built(display)
        if rt is not None:
            return {"match": "RUNTIME_BUILT", "token": rt["glob"], "n": 0,
                    "n_tests": c.get("n_tests", 0), "files": [rt["built_by"]]}
    return c


def _row_id(display: str, is_dir: bool = False) -> str:
    return ("dir:" if is_dir else "") + display


def _ledger_manifests() -> dict[str, dict]:
    out = {}
    try:
        from backend.services import ledger_archive as LA          # noqa: PLC0415
        for mp in sorted(LA.MANIFEST_DIR.glob("*.json")):
            try:
                m = json.loads(mp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            root = _repo_root()
            rel = mp.relative_to(root).as_posix() if mp.is_relative_to(root) else mp.name
            for key in ("jsonl", "parquet"):
                if (m.get(key) or {}).get("path"):
                    out[m[key]["path"]] = {"path": rel, "command": m.get("command"),
                                           "month": m.get("month"), "ledger": m.get("ledger")}
    except Exception:                                              # noqa: BLE001
        pass
    return out


def build_catalog(*, roots: Optional[list[Root]] = None, cache_path: Optional[Path] = CACHE_PATH,
                  manifest_text: Optional[str] = None, code_index: Optional[TokenIndex] = None,
                  doc_index: Optional[TokenIndex] = None, use_git: bool = True,
                  now: Optional[datetime] = None, workers: int = 4,
                  full_max: int = FULL_HASH_MAX, own_row_min: int = OWN_ROW_MIN) -> dict:
    run = now or _now()
    roots = roots if roots is not None else default_roots()
    entries = walk(roots, skip=[CATALOG_DIR])
    if manifest_text is None:
        mdoc = _repo_root() / "docs" / "DATA_MANIFEST.md"
        manifest_text = mdoc.read_text(encoding="utf-8") if mdoc.exists() else ""
    rules = load_manifest_rules(manifest_text)
    code_ix = code_index if code_index is not None else build_code_index()
    doc_ix = doc_index if doc_index is not None else build_doc_index()
    ledgers = _ledger_manifests()

    own = [fe for fe in entries if is_own_row(fe, own_row_min)]
    rest = [fe for fe in entries if not is_own_row(fe, own_row_min)]

    cache = load_cache(cache_path) if cache_path else {"v": CACHE_VERSION, "files": {}}
    cfiles = cache["files"]
    todo = [fe for fe in own
            if not ((c := cfiles.get(fe.display)) and c.get("size") == fe.size
                    and c.get("mtime_ns") == fe.mtime_ns)]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for fe, res in zip(todo, pool.map(lambda f: inspect_file(f, full_max=full_max), todo)):
            cfiles[fe.display] = {"size": fe.size, "mtime_ns": fe.mtime_ns, "res": res}
    if cache_path:
        live = {fe.display for fe in own}
        cache["files"] = {k: v for k, v in cfiles.items() if k in live}
        save_cache(cache_path, cache)

    sidecars = {fe.display[:-len(".meta.json")]: fe for fe in entries if fe.ext == ".meta.json"}
    repo_paths = sorted({fe.display for fe in entries if fe.in_repo})
    gmap = git_status_map(repo_paths) if use_git else {p: "unknown" for p in repo_paths}

    rows: list[dict] = []
    for fe in own:
        res = cfiles[fe.display]["res"]
        stem_key = fe.display.rsplit(".", 1)[0]
        sc = None
        if stem_key in sidecars:
            try:
                sc = json.loads(sidecars[stem_key].abs.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                sc = {}
        row = {
            "id": _row_id(fe.display), "path": fe.display, "root": fe.root,
            "kind": kind_of(fe.ext), "bytes": fe.size,
            "rows": res.get("rows"), "rows_method": res.get("rows_method"),
            "date_range": res.get("date_range"),
            "schema_hash": res.get("schema_hash"), "n_columns": res.get("n_columns"),
            "schema": res.get("schema"), "schema_method": res.get("schema_method"),
            "content": res.get("content"),
            "provenance": provenance_for(fe.display, rules=rules, sidecar=sc,
                                         ledger_manifest=ledgers.get(fe.display)),
            "git": gmap.get(fe.display, "outside_repo") if fe.in_repo else "outside_repo",
            "consumers": _consumers_or_runtime(fe.display, code_ix),
            "doc_mentions": doc_mentions(fe.display, doc_ix),
        }
        if res.get("error"):
            row["error"] = res["error"]
        rows.append(row)

    by_dir: dict[str, list[FileEntry]] = defaultdict(list)
    for fe in rest:
        by_dir[fe.display.rsplit("/", 1)[0] if "/" in fe.display else "."].append(fe)
    for d, fes in sorted(by_dir.items()):
        listing = "\n".join(f"{f.display.rsplit('/', 1)[-1]}\t{f.size}"
                            for f in sorted(fes, key=lambda f: f.display))
        gs = Counter(gmap.get(f.display, "outside_repo") if f.in_repo else "outside_repo"
                     for f in fes)
        rows.append({
            "id": _row_id(d, True), "path": d, "root": fes[0].root, "kind": "dir",
            "bytes": sum(f.size for f in fes), "n_files": len(fes),
            "ext_mix": dict(Counter(f.ext or "none" for f in fes).most_common(8)),
            "rows": None, "rows_method": "n/a (directory of small files)",
            "date_range": None, "schema_hash": None,
            "content": {"sha256": hashlib.sha256(listing.encode()).hexdigest(),
                        "mode": "listing (names+sizes), not content"},
            "provenance": provenance_for(d, rules=rules, is_dir=True),
            "git": next(iter(gs)) if len(gs) == 1 else "mixed",
            "git_counts": dict(gs),
            "consumers": consumers_for(d, code_ix, is_dir=True),
            "doc_mentions": 0,
        })

    dups = find_duplicates(rows)
    summary = summarise(rows, dups, entries)
    return {
        "job": "data_catalog", "schema_version": "data_catalog/1",
        "run_id": run.strftime("%Y%m%dT%H%M%SZ"), "utc": run.isoformat(timespec="seconds"),
        "dated_by": "the run clock; no row carries an mtime and no date range is read "
                    "from the filesystem (mtime is only a cache key)",
        "roots": [{"label": r.label, "path": r.display_prefix or _safe_rel(r.path),
                   "exists": r.path.exists()} for r in roots],
        "thresholds": {"full_hash_max_bytes": full_max, "own_row_min_bytes": own_row_min,
                       "head_tail_bytes": HEAD_TAIL, "sample_rows": SAMPLE_ROWS},
        "cache": {"hits": len(own) - len(todo), "inspected": len(todo)},
        "consumer_method": ("tokens of tracked + untracked code files (py/ts/js/cmd/ps1/yaml...), "
                            "matched by basename, then stem, then name family, then a specific "
                            "parent directory; then the declared RUNTIME_PATTERNS (paths built "
                            "from a variable). 'no static reference' is a question, never a "
                            "deletion list"),
        "summary": summary,
        "findings": {
            "replays": [g for g in dups if g["class"] == "REPLAY"],
            "variant_identical": [g for g in dups if g["class"] == "VARIANT_IDENTICAL"],
            "data_checks": [g for g in dups if g["class"] == "DATA_CHECK"],
        },
        "duplicates": dups, "rows": rows,
    }


def _safe_rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(_repo_root()).as_posix()
    except ValueError:
        return "<outside repo>"


_RUN_TOKEN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{6}Z|\d{8}T\d{6}Z|\d{4}-\d{2}-\d{2}|\d{8}|run\d+")
_WRDS_BULK = re.compile(r"/wrds/bulk/(?:_quarantine_truncated/)?(?P<schema>[^/]+?)__(?P<table>[^/]+)\.parquet$")


def classify_duplicate(paths: list[str]) -> tuple[str, str]:
    """`(class, why)` for a group of byte-identical files (review F1).

    ALIAS     -- one WRDS table pulled under two library names: disk to reclaim.
    DATA_CHECK-- two DIFFERENTLY NAMED source tables with the same bytes: either
                 the pull returned one table twice or upstream serves one under
                 two names. A data question, not a disk question.
    SNAPSHOT  -- a dated copy beside its undated live file: keep, it is history.
    REPLAY    -- the same run family under different run ids / dates / runNN
                 with identical bytes: two runs that should have differed did
                 not (CLAUDE.md protocol 9). A FINDING for the morning report.
    VARIANT_IDENTICAL -- a declared variant (`x_ivw`, `x_liqw`, ...) identical to
                 its parent in the same directory: the variant path did nothing.
    OTHER     -- none of the above."""
    m = [_WRDS_BULK.search(p) for p in paths]
    if all(m):
        tables = {x.group("table") for x in m}
        if len(tables) == 1:
            return "ALIAS", "one WRDS table under several library names"
        return "DATA_CHECK", ("differently named WRDS tables are byte-identical: "
                              + " = ".join(sorted(tables)))
    norm = {_RUN_TOKEN.sub("<RUN>", p) for p in paths}
    stripped = {re.sub(r"[_\-.]?<RUN>", "", _RUN_TOKEN.sub("<RUN>", p)) for p in paths}
    if len(norm) == 1:
        return "REPLAY", "same run family, different run ids, identical bytes"
    if len(stripped) == 1:
        if any(not _RUN_TOKEN.search(Path(p).name) and not _RUN_TOKEN.search(str(Path(p).parent))
               for p in paths):
            return "SNAPSHOT", "a dated copy of an undated live file"
        return "REPLAY", "same run family, different run ids, identical bytes"
    dirs = {str(Path(p).parent) for p in paths}
    stems = sorted((Path(p).name.split(".")[0] for p in paths), key=len)
    if len(dirs) == 1 and all(s.startswith(stems[0] + "_") for s in stems[1:]):
        return "VARIANT_IDENTICAL", (f"variants {', '.join(stems[1:])} are byte-identical to "
                                     f"their parent {stems[0]}")
    return "OTHER", ""


def find_duplicates(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        c = r.get("content") or {}
        if r["kind"] == "dir" or not c.get("sha256") or r["bytes"] == 0:
            continue
        groups[(c["mode"], c["sha256"])].append(r)
    out = []
    for (mode, sha), rs in groups.items():
        if len(rs) < 2:
            continue
        paths = sorted(r["path"] for r in rs)
        cls, why = classify_duplicate(paths)
        out.append({"sha256": sha, "mode": mode, "class": cls, "why": why,
                    "certainty": "exact" if mode == "full" else "probable (size + head/tail)",
                    "bytes_each": rs[0]["bytes"], "n": len(rs),
                    "redundant_bytes": rs[0]["bytes"] * (len(rs) - 1),
                    "paths": paths})
    return sorted(out, key=lambda g: -g["redundant_bytes"])


def summarise(rows: list[dict], dups: list[dict], entries: list[FileEntry]) -> dict:
    total = sum(r["bytes"] for r in rows)
    rt = [r for r in rows if r["consumers"].get("match") == "RUNTIME_BUILT"]
    orphans = [r for r in rows if r["consumers"]["n"] == 0
               and r["consumers"].get("match") != "RUNTIME_BUILT"]
    by_class: dict[str, dict] = defaultdict(lambda: {"groups": 0, "redundant_bytes": 0})
    for g in dups:
        by_class[g["class"]]["groups"] += 1
        by_class[g["class"]]["redundant_bytes"] += g["redundant_bytes"]
    unknown = [r for r in rows if r["provenance"]["source"] == UNKNOWN]
    by_kind: dict[str, dict] = defaultdict(lambda: {"n": 0, "bytes": 0})
    by_root: dict[str, dict] = defaultdict(lambda: {"n": 0, "bytes": 0})
    by_git: dict[str, dict] = defaultdict(lambda: {"n": 0, "bytes": 0})
    for r in rows:
        for d, k in ((by_kind, r["kind"]), (by_root, r["root"]), (by_git, r["git"])):
            d[k]["n"] += 1
            d[k]["bytes"] += r["bytes"]
    files = [r for r in rows if r["kind"] != "dir"]
    return {
        "n_datasets": len(rows), "n_file_rows": len(files),
        "n_dir_rows": len(rows) - len(files), "n_files_walked": len(entries),
        "total_bytes": total, "total_gb": round(total / 1e9, 2),
        "duplicate_groups": len(dups),
        "duplicate_exact_groups": sum(1 for g in dups if g["mode"] == "full"),
        "duplicate_redundant_bytes": sum(g["redundant_bytes"] for g in dups),
        "duplicate_redundant_bytes_exact": sum(g["redundant_bytes"] for g in dups
                                               if g["mode"] == "full"),
        "duplicate_redundant_bytes_probable": sum(g["redundant_bytes"] for g in dups
                                                  if g["mode"] != "full"),
        "duplicates_by_class": dict(by_class),
        "replay_groups": sum(1 for g in dups if g["class"] == "REPLAY"),
        "no_static_reference": len(orphans),
        "no_static_reference_bytes": sum(r["bytes"] for r in orphans),
        "no_static_reference_files": sum(1 for r in orphans if r["kind"] != "dir"),
        "runtime_built": len(rt), "runtime_built_bytes": sum(r["bytes"] for r in rt),
        "unknown_provenance": len(unknown),
        "unknown_provenance_bytes": sum(r["bytes"] for r in unknown),
        "errors": sum(1 for r in rows if r.get("error")),
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1]["bytes"])),
        "by_root": dict(by_root), "by_git": dict(by_git),
        "biggest": [{"path": r["path"], "bytes": r["bytes"], "kind": r["kind"]}
                    for r in sorted(files, key=lambda r: -r["bytes"])[:5]],
    }


# ============================================================ outputs

def write_receipt(cat: dict, out_dir: Path = CATALOG_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"catalog_{cat['run_id']}.json"
    if p.exists():
        raise FileExistsError(f"{p.name} exists; a receipt is never overwritten")
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cat, separators=(",", ":"), default=str), encoding="utf-8")
    os.replace(tmp, p)
    return p


def _mb(b: int) -> str:
    return f"{b / 1e9:.2f} GB" if b >= 1e9 else f"{b / 1e6:.1f} MB"


def _dr(r: dict) -> str:
    d = r.get("date_range")
    if not d:
        return ""
    s = f"{d['min']} .. {d['max']}"
    return s + (" [sentinel]" if d.get("sentinel") else "")


def render_markdown(cat: dict, receipt_rel: str) -> str:
    s = cat["summary"]
    rows = cat["rows"]
    L = [
        "# DATA_CATALOG — every dataset on disk (GENERATED, do not edit)",
        "",
        f"**Generated by `python -m backend.services.data_catalog` at {cat['utc']} "
        f"(run `{cat['run_id']}`).** Edits here are overwritten on the next run. The full "
        f"row list is the receipt `{receipt_rel}`; this page is its summary. The hand-written "
        "companion is `docs/DATA_MANIFEST.md` (how to rebuild); this page is what IS on disk.",
        "",
        "Ask it: `python -m backend.services.data_catalog --query <substring>` answers "
        "\"do we have X?\" from the newest receipt in one command.",
        "",
        "Dated by the run clock. No row carries a file mtime; date ranges come from the data "
        "(parquet column statistics, first/last rows of a jsonl, a receipt's own stamp) and "
        "name their method.",
        "",
        "## Totals",
        "",
        "| | |", "|---|---:|",
        f"| datasets (rows) | {s['n_datasets']:,} ({s['n_file_rows']:,} files + "
        f"{s['n_dir_rows']:,} directories of small files) |",
        f"| files walked | {s['n_files_walked']:,} |",
        f"| bytes | {_mb(s['total_bytes'])} |",
        f"| duplicate groups (same content at 2+ paths) | {s['duplicate_groups']:,}: "
        f"{s['duplicate_exact_groups']:,} exact ({_mb(s['duplicate_redundant_bytes_exact'])} "
        f"redundant) + {s['duplicate_groups'] - s['duplicate_exact_groups']:,} probable by "
        f"size+head/tail ({_mb(s['duplicate_redundant_bytes_probable'])}) |",
        f"| REPLAY groups (two runs that should have differed did not) | "
        f"{s['replay_groups']:,} |",
        f"| no static reference (no code file names them) | {s['no_static_reference']:,} "
        f"({_mb(s['no_static_reference_bytes'])}) |",
        f"| runtime-built (declared `RUNTIME_PATTERNS`) | {s['runtime_built']:,} "
        f"({_mb(s['runtime_built_bytes'])}) |",
        f"| `UNKNOWN_PROVENANCE` | {s['unknown_provenance']:,} "
        f"({_mb(s['unknown_provenance_bytes'])}) |",
        f"| rows with an inspection error | {s['errors']:,} |",
        "",
        "### By kind", "", "| kind | rows | bytes |", "|---|---:|---:|",
    ]
    L += [f"| {k} | {v['n']:,} | {_mb(v['bytes'])} |" for k, v in s["by_kind"].items()]
    L += ["", "### By git status", "", "| status | rows | bytes |", "|---|---:|---:|"]
    L += [f"| {k} | {v['n']:,} | {_mb(v['bytes'])} |" for k, v in s["by_git"].items()]

    files = sorted((r for r in rows if r["kind"] != "dir"), key=lambda r: -r["bytes"])
    L += ["", "## The 40 biggest files", "",
          "| path | kind | size | rows | date range (from data) | git | consumers | provenance |",
          "|---|---|---:|---:|---|---|---|---|"]
    for r in files[:40]:
        c = r["consumers"]
        cons = f"{c['n']} ({c['match']})" if c["match"] else "**none**"
        prov = r["provenance"]["source"]
        L.append(f"| `{r['path']}` | {r['kind']} | {_mb(r['bytes'])} | "
                 f"{'' if r['rows'] is None else format(r['rows'], ',')} | {_dr(r)} | {r['git']} | "
                 f"{cons} | {prov} |")

    def _paths(g: dict) -> str:
        return "<br>".join(f"`{p}`" for p in g["paths"][:4]) + (
            f"<br>(+{len(g['paths']) - 4} more)" if len(g["paths"]) > 4 else "")

    fnd = cat.get("findings") or {}
    L += ["", "## Findings in the duplicates: REPLAY / VARIANT_IDENTICAL / DATA_CHECK", "",
          "A REPLAY is the same run family under different run ids with identical bytes "
          "(CLAUDE.md protocol 9): two runs that should have differed did not. "
          "VARIANT_IDENTICAL is a declared variant identical to its parent. DATA_CHECK is two "
          "differently named source tables with the same bytes. These are findings, not disk.",
          "", "| class | copies | each | paths |", "|---|---:|---:|---|"]
    for cls in ("replays", "variant_identical", "data_checks"):
        for g in fnd.get(cls, [])[:40]:
            L.append(f"| {g['class']} | {g['n']} | {_mb(g['bytes_each'])} | {_paths(g)} |")
    byc = s.get("duplicates_by_class") or {}
    L += ["", "## Duplicates by class", "", "| class | groups | redundant |", "|---|---:|---:|"]
    L += [f"| {k} | {v['groups']:,} | {_mb(v['redundant_bytes'])} |"
          for k, v in sorted(byc.items(), key=lambda kv: -kv[1]["redundant_bytes"])]
    L += ["", "## Duplicates (top 30 by redundant bytes)", "",
          "Nothing is deleted. Only ALIAS is disk to reclaim, and that is the owner's call.",
          "", "| class | copies | each | redundant | certainty | paths |",
          "|---|---:|---:|---:|---|---|"]
    for g in cat["duplicates"][:30]:
        L.append(f"| {g['class']} | {g['n']} | {_mb(g['bytes_each'])} | "
                 f"{_mb(g['redundant_bytes'])} | {g['certainty']} | {_paths(g)} |")

    orph = sorted((r for r in rows if r["consumers"]["n"] == 0
                   and r["consumers"].get("match") != "RUNTIME_BUILT"), key=lambda r: -r["bytes"])
    L += ["", "## No static reference (top 40 by size)", "",
          "No code file names these by basename, stem, family or directory, and no declared "
          "`RUNTIME_PATTERNS` entry builds them. A path assembled from variables can still be "
          "missed, and a dataset read only by tests is listed. **This is a question, never a "
          "deletion list.**", "",
          "| path | kind | size | git | provenance | doc mentions |", "|---|---|---:|---|---|---:|"]
    for r in orph[:40]:
        L.append(f"| `{r['path']}` | {r['kind']} | {_mb(r['bytes'])} | {r['git']} | "
                 f"{r['provenance']['source']} | {r.get('doc_mentions', 0)} |")

    unk = Counter()
    unk_b: Counter = Counter()
    for r in rows:
        if r["provenance"]["source"] == UNKNOWN:
            top = "/".join(r["path"].split("/")[:4])
            unk[top] += 1
            unk_b[top] += r["bytes"]
    L += ["", "## `UNKNOWN_PROVENANCE` by area (top 30 by bytes)", "",
          "Not in `docs/DATA_MANIFEST.md`, no committed ledger manifest, no `.meta.json` "
          "sidecar. Adding a manifest row is how a dataset leaves this list.", "",
          "| area | rows | bytes |", "|---|---:|---:|"]
    for top, b in unk_b.most_common(30):
        L.append(f"| `{top}` | {unk[top]:,} | {_mb(b)} |")

    led = [r for r in rows if r["provenance"]["source"] == "ledger_manifest"]
    L += ["", "## Archived ledger months", ""]
    if led:
        L += ["| path | size | manifest |", "|---|---:|---|"]
        L += [f"| `{r['path']}` | {_mb(r['bytes'])} | `{r['provenance']['manifest']}` |"
              for r in led]
    else:
        L.append("None yet.")
    L.append("")
    return "\n".join(L)


def write_doc(cat: dict, receipt: Path, path: Optional[Path] = None) -> Path:
    path = Path(path) if path is not None else _repo_root() / "docs" / "DATA_CATALOG.md"
    try:
        rel = receipt.resolve().relative_to(_repo_root()).as_posix()
    except ValueError:
        rel = receipt.name
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(render_markdown(cat, rel), encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


#: Full receipts kept locally (gitignored): the newest N plus the first of each month.
KEEP_NEWEST = 7


def prune_receipts(out_dir: Path = CATALOG_DIR, keep: int = KEEP_NEWEST) -> list[str]:
    """Remove this job's OWN old full receipts (review F9). Ordered by the run id
    in the name, never by mtime. Keeps the newest `keep` and the first receipt
    of every month. Touches nothing but `catalog_<run_id>.json` here."""
    pat = re.compile(r"^catalog_(\d{8}T\d{6}Z)\.json$")
    rs = sorted((q for q in Path(out_dir).glob("catalog_*.json") if pat.match(q.name)),
                key=lambda q: q.name)
    keepers = set(q.name for q in rs[-keep:]) if keep > 0 else set()
    first_of_month: dict[str, str] = {}
    for q in rs:
        first_of_month.setdefault(pat.match(q.name).group(1)[:6], q.name)
    keepers |= set(first_of_month.values())
    removed = []
    for q in rs:
        if q.name not in keepers:
            q.unlink()
            removed.append(q.name)
    return removed


def latest_receipt(out_dir: Path = CATALOG_DIR) -> Optional[Path]:
    """Newest by the run id IN THE NAME (a UTC stamp), never by mtime."""
    c = sorted(out_dir.glob("catalog_*.json"), key=lambda p: p.name)
    return c[-1] if c else None


def query(cat: dict, needle: str, limit: int = 50) -> list[dict]:
    n = needle.lower()
    hits = []
    for r in cat["rows"]:
        hay = " ".join([r["id"], r["path"], json.dumps(r.get("schema") or []),
                        str((r.get("provenance") or {}).get("produced_by") or "")]).lower()
        if n in hay:
            hits.append(r)
    return sorted(hits, key=lambda r: (n not in Path(r["path"]).name.lower(), -r["bytes"]))[:limit]


def run(*, write_doc_too: bool = True, **kw: Any) -> dict:
    cat = build_catalog(**kw)
    p = write_receipt(cat)
    if write_doc_too:
        write_doc(cat, p)
    pruned = prune_receipts(p.parent)
    s = cat["summary"]
    return {"job": "data_catalog", "run_id": cat["run_id"], "receipt": _safe_rel(p),
            "datasets": s["n_datasets"], "gb": s["total_gb"],
            "duplicate_groups": s["duplicate_groups"], "replay_groups": s["replay_groups"],
            "no_static_reference": s["no_static_reference"],
            "runtime_built": s["runtime_built"], "receipts_pruned": len(pruned),
            "unknown_provenance": s["unknown_provenance"], "errors": s["errors"],
            "cache": cat["cache"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="data_catalog",
                                 description="Catalogue every dataset; or answer 'do we have X?'")
    ap.add_argument("--query", default=None, help="substring of a path, column or producer")
    ap.add_argument("--no-doc", action="store_true", help="write the receipt only")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.query is not None:
        rp = latest_receipt()
        if rp is None:
            print("REFUSED: no catalog receipt yet; run `python -m backend.services.data_catalog`")
            return 2
        cat = json.loads(rp.read_text(encoding="utf-8"))
        hits = query(cat, a.query)
        print(f"catalog {cat['run_id']} ({cat['utc']}): {len(hits)} match(es) for {a.query!r}")
        for r in hits:
            c = r["consumers"]
            print(f"  {r['path']}  [{r['kind']}, {_mb(r['bytes'])}"
                  + (f", {r['rows']:,} rows" if r.get("rows") is not None else "")
                  + (f", {_dr(r)}" if r.get("date_range") else "")
                  + f", git={r['git']}, consumers={c['n']}"
                  + (f" via {c['match']}" if c["match"] else "")
                  + f", provenance={r['provenance']['source']}]")
        return 0 if hits else 1
    out = run(write_doc_too=not a.no_doc, workers=a.workers)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
