"""Read the converted Bloomberg / broker-research tables that live OUTSIDE the repo.

CH-00 / CH-32. The owner holds licensed documents (a Bloomberg MEMB export of the
WLS index, a Bloomberg FA workbook, broker research PDFs). They are converted to
tidy CSV/parquet under ``config.LICENSED_DATA_DIR`` (default
``~/AEGIS_DOCUMENTS/bloomberg/converted``) together with a ``MANIFEST.json`` that
records, per dataset: its kind, its ``as_of`` date, and for every output table the
file name, sha256 and row count. Nothing licensed is ever committed; this module
and its synthetic test fixture are the only repo-side pieces.

WHAT THIS MODULE REFUSES TO DO
==============================
* Return an empty frame for a missing file. In CI, and on any machine without
  the documents, every dataset is ``UNAVAILABLE`` with a reason and ``frame is
  None``. An empty frame would read as "the index has no members".
* Call a table fresh because its file is new. Age is counted from the
  manifest's ``as_of`` (the data's own date), never from the file mtime -- a
  fresh copy of an October export is still an October export. A dataset with
  no parseable ``as_of`` is ``UNDATED``, never fresh.
* Load a table whose bytes or row count disagree with the manifest. A
  truncated rewrite or a hand edit is ``INVALID`` -- the conversion's whole
  job was to not drop rows silently, and a reader that skipped this check
  would reintroduce exactly that.

``python -m backend.services.licensed_data`` prints the inventory and exits
non-zero unless every dataset is OK (2 = unavailable/invalid, 1 = stale/undated).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend import config

OK = "OK"
STALE = "STALE"
UNDATED = "UNDATED"
UNAVAILABLE = "UNAVAILABLE"
INVALID = "INVALID"
#: Inventory-only: the manifest lists a source with no table (e.g. a screenshot). Not a refusal.
NOT_CONVERTED = "NOT_CONVERTED"

#: Statuses under which a frame is returned (the caller decides what STALE means for it).
_USABLE = (OK, STALE, UNDATED)

#: Column contracts for the tables the converter writes. A table whose kind/name is
#: not listed here still loads, untyped, with every other check applied.
#: Each entry: column -> dtype ("str", "float", "int", "bool", "date").
SCHEMAS: dict[tuple[str, str], dict[str, str]] = {
    ("index_membership", "members"): {
        "row_label": "int", "page": "int", "Ticker": "str", "bbg_key": "str", "symbol": "str",
        "exch_code": "str", "name": "str", "weight_pct": "float", "shares_mn": "float",
        "price_local": "float", "country": "str", "aegis_market": "str", "yahoo_symbol": "str",
        "match_method": "str", "in_contest_universe": "bool", "has_aegis_bars": "bool",
    },
    ("fundamentals", "fa"): {
        "ticker": "str", "excel_row": "int", "line_item": "str", "bbg_field": "str",
        "period_label": "str", "period_end": "date", "is_estimate": "bool", "is_ltm": "bool",
        "value": "float", "cached_value_missing": "bool",
    },
    ("broker_note", "financials"): {
        "page": "int", "section": "str", "line_item": "str", "col_index": "int", "period": "str",
        "is_estimate": "bool", "is_pct_change": "bool", "value_raw": "str", "value": "float",
    },
}


@dataclass(frozen=True)
class LicensedStatus:
    dataset: str
    table: str
    status: str
    reason: str = ""
    kind: Optional[str] = None
    path: Optional[str] = None
    rows: Optional[int] = None
    as_of: Optional[str] = None
    age_days: Optional[int] = None
    max_age_days: Optional[int] = None

    @property
    def usable(self) -> bool:
        return self.status in _USABLE

    def line(self) -> str:
        age = "age ?" if self.age_days is None else f"age {self.age_days}d/{self.max_age_days}d"
        rows = "" if self.rows is None else f" rows={self.rows:,}"
        why = f" -- {self.reason}" if self.reason else ""
        return f"[{self.status}] {self.dataset}/{self.table} as_of={self.as_of} {age}{rows}{why}"


@dataclass
class LicensedFrame:
    status: LicensedStatus
    frame: Optional[pd.DataFrame] = field(default=None, repr=False)


def _root(root: Optional[Path]) -> Path:
    return Path(root) if root is not None else Path(config.LICENSED_DATA_DIR)


def read_manifest(root: Optional[Path] = None) -> Optional[dict]:
    """The manifest dict, or None when the folder or the manifest is absent."""
    p = _root(root) / config.LICENSED_DATA_MANIFEST
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_day(v: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pick_output(outputs: list[dict], table: Optional[str]) -> tuple[Optional[dict], str]:
    """Parquet first, CSV second, among the outputs of one table."""
    tables = sorted({o.get("table") for o in outputs if o.get("table")})
    if table is None:
        if len(tables) != 1:
            return None, f"dataset has tables {tables}; name one"
        table = tables[0]
    cands = [o for o in outputs if o.get("table") == table]
    if not cands:
        return None, f"no table {table!r} (has {tables})"
    for suffix in (".parquet", ".csv", ".jsonl"):
        for o in cands:
            if str(o.get("file", "")).lower().endswith(suffix):
                return o, table
    return None, f"table {table!r} has no .parquet, .csv or .jsonl output"


def _coerce(df: pd.DataFrame, schema: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    missing = [c for c in schema if c not in df.columns]
    if missing:
        return df, missing
    out = df.copy()
    for c, t in schema.items():
        if t == "str":
            out[c] = out[c].astype("string")
        elif t == "float":
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
        elif t == "int":
            out[c] = pd.to_numeric(out[c], errors="raise").astype("int64")
        elif t == "bool":
            if out[c].dtype != bool:
                out[c] = out[c].astype(str).str.strip().str.lower().map({"true": True, "false": False})
                if out[c].isna().any():
                    raise ValueError(f"column {c!r} holds values that are not true/false")
                out[c] = out[c].astype(bool)
        elif t == "date":
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.date
    return out, []


def load(dataset: str, table: Optional[str] = None, *, root: Optional[Path] = None,
         today: Optional[date] = None) -> LicensedFrame:
    """One converted table, typed, with a status that says whether it can be used.

    ``frame`` is None unless the status is OK, STALE or UNDATED.
    """
    base = _root(root)
    tname = table or "?"
    man = read_manifest(base)
    if man is None:
        return LicensedFrame(LicensedStatus(dataset, tname, UNAVAILABLE,
                                            f"no {config.LICENSED_DATA_MANIFEST} under {base}"))
    ds = (man.get("datasets") or {}).get(dataset)
    if ds is None:
        return LicensedFrame(LicensedStatus(dataset, tname, UNAVAILABLE,
                                            f"dataset not in manifest (has {sorted(man.get('datasets', {}))})"))
    kind = ds.get("kind")
    out, tname_or_why = _pick_output(ds.get("outputs") or [], table)
    if out is None:
        return LicensedFrame(LicensedStatus(dataset, tname, UNAVAILABLE, tname_or_why, kind=kind))
    tname = tname_or_why
    path = base / out["file"]
    max_age = int(config.LICENSED_DATA_MAX_AGE_DAYS.get(kind, config.LICENSED_DATA_DEFAULT_MAX_AGE_DAYS))
    as_of_raw = ds.get("as_of")
    as_of = _parse_day(as_of_raw)
    common = dict(kind=kind, path=str(path), as_of=None if as_of is None else as_of.isoformat(),
                  max_age_days=max_age)
    if not path.is_file():
        return LicensedFrame(LicensedStatus(dataset, tname, UNAVAILABLE, f"{out['file']} is missing", **common))
    want_sha = out.get("sha256")
    if want_sha and _sha256(path) != want_sha:
        return LicensedFrame(LicensedStatus(dataset, tname, INVALID,
                                            f"{out['file']} sha256 differs from the manifest", **common))
    try:
        suf = path.suffix.lower()
        if suf == ".parquet":
            df = pd.read_parquet(path)
        elif suf == ".jsonl":
            df = pd.read_json(path, lines=True)
        else:
            df = pd.read_csv(path, low_memory=False)
    except Exception as exc:                                    # noqa: BLE001 -- reported, not swallowed
        return LicensedFrame(LicensedStatus(dataset, tname, INVALID,
                                            f"unreadable: {type(exc).__name__}: {exc}", **common))
    want_rows = out.get("rows")
    if want_rows is None or int(want_rows) != len(df):
        return LicensedFrame(LicensedStatus(dataset, tname, INVALID,
                                            f"{len(df)} rows read, manifest says {want_rows}", rows=len(df), **common))
    schema = SCHEMAS.get((kind, tname))
    if schema:
        try:
            df, missing = _coerce(df, schema)
        except Exception as exc:                                # noqa: BLE001
            return LicensedFrame(LicensedStatus(dataset, tname, INVALID,
                                                f"type check failed: {exc}", rows=len(df), **common))
        if missing:
            return LicensedFrame(LicensedStatus(dataset, tname, INVALID,
                                                f"missing columns {missing}", rows=len(df), **common))
    if as_of is None:
        st = LicensedStatus(dataset, tname, UNDATED, f"manifest as_of {as_of_raw!r} is not a date",
                            rows=len(df), **common)
        return LicensedFrame(st, df)
    age = ((today or date.today()) - as_of).days
    if age > max_age:
        st = LicensedStatus(dataset, tname, STALE, f"as_of is {age} days old (> {max_age})",
                            rows=len(df), age_days=age, **common)
    else:
        st = LicensedStatus(dataset, tname, OK, rows=len(df), age_days=age, **common)
    return LicensedFrame(st, df)


def inventory(root: Optional[Path] = None, *, today: Optional[date] = None) -> list[LicensedStatus]:
    """One status per (dataset, table) the manifest lists; one UNAVAILABLE row when there is no manifest."""
    base = _root(root)
    man = read_manifest(base)
    if man is None:
        return [LicensedStatus("*", "*", UNAVAILABLE, f"no {config.LICENSED_DATA_MANIFEST} under {base}")]
    rows: list[LicensedStatus] = []
    for name, ds in sorted((man.get("datasets") or {}).items()):
        tables = sorted({o.get("table") for o in ds.get("outputs") or [] if o.get("table")})
        if not tables:
            rows.append(LicensedStatus(name, "-", NOT_CONVERTED, "manifest lists the source but no table "
                                       "(see its pages_failed)", kind=ds.get("kind"), as_of=ds.get("as_of")))
            continue
        for t in tables:
            rows.append(load(name, t, root=base, today=today).status)
    return rows


def datasets_of_kind(kind: str, root: Optional[Path] = None) -> list[str]:
    man = read_manifest(root) or {}
    return sorted(k for k, v in (man.get("datasets") or {}).items() if v.get("kind") == kind)


# ---- typed conveniences --------------------------------------------------------------

def wls_members(root: Optional[Path] = None, *, today: Optional[date] = None) -> LicensedFrame:
    """The Bloomberg WLS index membership (one row per member, `yahoo_symbol` = Aegis join key)."""
    names = datasets_of_kind("index_membership", root)
    if not names:
        return LicensedFrame(LicensedStatus("wls_members", "members", UNAVAILABLE,
                                            "no index_membership dataset in the manifest"))
    return load(names[-1], "members", root=root, today=today)


def bloomberg_fundamentals(root: Optional[Path] = None, *, today: Optional[date] = None) -> list[LicensedFrame]:
    return [load(n, "fa", root=root, today=today) for n in datasets_of_kind("fundamentals", root)]


def broker_note_financials(root: Optional[Path] = None, *, today: Optional[date] = None) -> list[LicensedFrame]:
    return [load(n, "financials", root=root, today=today) for n in datasets_of_kind("broker_note", root)]


def main(argv: Optional[list[str]] = None) -> int:
    rows = inventory()
    for r in rows:
        print(r.line())
    if any(r.status in (UNAVAILABLE, INVALID) for r in rows):
        return 2
    if any(r.status in (STALE, UNDATED) for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
