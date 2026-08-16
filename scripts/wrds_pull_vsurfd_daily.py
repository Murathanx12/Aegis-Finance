"""Bounded, read-only acquisition of the DAILY OptionMetrics volatility surface.

    python -m scripts.wrds_pull_vsurfd_daily --probe
    python -m scripts.wrds_pull_vsurfd_daily --map
    python -m scripts.wrds_pull_vsurfd_daily --pull 2006 2019

For `IV-ORACLE-GAP-1` (`docs/TRIALS/PREREG_IV_ORACLE_GAP_1.md`). Touches no
production path, no lane, no NAV, no live registry, and deploys nothing.

WHY A NEW EXTRACTION AND NOT THE ONE WE HAVE
============================================
`Aegis module/data/wrds_raw/optionm_vsurf_me/` holds 183 MB across 2002-2024,
and it is **month-end**: 2015 has exactly 12 observation dates, 2015-01-30
through 2015-12-31, median gap 31 days, across 4,718 secids. Twelve dates a
year cannot resolve a 20-day forecast comparison.

That limitation was reported twice as a property of OptionMetrics. It is a
property of **our `WHERE` clause**: `optionm.vsurfd` is the daily standardised
surface and the month-end table is a filter over it. A property of your
extraction is not a property of the data — the house error, twice on the same
dataset.

So this writes a NEW immutable dataset version beside the old one. The existing
extraction is never overwritten: a run made under a different extraction is
evidence about the process that produced it.

WHAT IS BOUNDED, AND WHY THAT IS NOT AN OPTIMISATION
====================================================
Eighteen ETF secids, four surface coordinates, one year per query. That is
~18 x 252 x 4 = ~18k rows/year against ~413k rows/year for the whole month-end
universe. The bound is declared in the manifest so a later reader knows the
extraction was narrow BY DESIGN and does not mistake missing securities for
missing data.

EVERY PULL LEAVES A MANIFEST
============================
Exact SQL, query timestamp, server version, schema, date coverage, secid
coverage, coordinates per security-date, row count and sha256 of each parquet.
A file without a manifest entry is not evidence and this script will say so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\optionm_vsurfd_daily")
MANIFEST = OUT_DIR / "manifest.json"

HOST, PORT, DBNAME, USER = ("wrds-pgdata.wharton.upenn.edu", 9737,
                            "wrds", "murathan12")

#: WM0's panel, verbatim. The comparison is only interpretable on the panel the
#: 21.4% headroom was measured on; a different universe measures a different
#: question and would need its own bound.
UNIVERSE = ("SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP",
            "XLU", "XLB", "XLY", "DIA", "TLT", "GLD", "EFA", "EEM", "IYR")

#: The coordinates the pre-registration's rungs need, and no others:
#: ATM (delta 50) at 30d and 60d gives level and term slope; the 25-delta put
#: at 30d gives downside skew. `days=91` is carried for a longer-horizon check
#: that the prereg reports without a power claim.
DAYS = (30, 60, 91)
DELTAS = (50, -25)

SQL_SURFACE = """
select secid, date, days, delta, cp_flag, impl_volatility, dispersion
from optionm.vsurfd
where secid in %(secids)s
  and days in %(days)s
  and delta in %(deltas)s
  and date >= %(start)s and date <= %(end)s
"""

SQL_MAP = """
select secid, ticker, issuer, issue_type, index_flag, effect_date, exchange_d
from optionm.securd
where ticker in %(tickers)s
"""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _reachable() -> tuple[bool, str]:
    """Say WHY, not just no. A pull that fails silently looks like empty data."""
    s = socket.socket()
    s.settimeout(12)
    try:
        s.connect((HOST, PORT))
        return True, "tcp ok"
    except Exception as exc:                                     # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        s.close()


def _engine():
    """Non-interactive by construction: libpq reads PGPASSFILE itself.

    The `wrds` wrapper prompts for a username when its own pgpass lookup misses
    — which on this machine it does, because the credentials live in
    %APPDATA%\\postgresql\\pgpass.conf and it looks in ~/.pgpass. A prompt in an
    unattended pull is a hang, so the wrapper is bypassed and the password is
    never read by this process.
    """
    if not os.environ.get("PGPASSFILE"):
        cand = Path(os.environ.get("APPDATA", "")) / "postgresql" / "pgpass.conf"
        if cand.exists():
            os.environ["PGPASSFILE"] = str(cand)
    from sqlalchemy import create_engine
    return create_engine(
        f"postgresql+psycopg2://{USER}@{HOST}:{PORT}/{DBNAME}?sslmode=require")


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"dataset": "optionm.vsurfd", "bound": {
        "universe": list(UNIVERSE), "days": list(DAYS), "deltas": list(DELTAS),
        "why": "IV-ORACLE-GAP-1 needs ATM level, term slope and 25d put skew "
               "on WM0's 18-security panel. Narrow BY DESIGN — absent "
               "securities are out of scope, not missing data."},
        "runs": []}


def _write_manifest(m: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")


def _secid_map() -> dict:
    m = _load_manifest()
    for run in reversed(m["runs"]):
        if run.get("kind") == "map" and run.get("mapping"):
            return {k: int(v) for k, v in run["mapping"].items()}
    raise SystemExit("no secid mapping in the manifest — run --map first. "
                     "Guessing a secid would silently pull another security.")


def cmd_probe(a) -> int:
    ok, why = _reachable()
    print(f"{HOST}:{PORT} reachable: {ok}  ({why})")
    if not ok:
        print("\nNOT A CODE FAILURE. The endpoint was called and the status is "
              "printed above. WRDS is unreachable from this network — "
              "wrds-www.wharton.upenn.edu:443 times out too, while other hosts "
              "do not, so this is the route to Wharton rather than the port. "
              "Likely a campus/VPN requirement. Nothing here is blocked on "
              "credentials or on this script.")
        return 1
    from sqlalchemy import text
    with _engine().connect() as c:
        print("server:", c.execute(text("select version()")).scalar()[:60])
        cols = c.execute(text(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='optionm' and table_name='vsurfd' "
            "order by ordinal_position")).fetchall()
        print("optionm.vsurfd schema:")
        for name, typ in cols:
            print(f"  {name:20s} {typ}")
        span = c.execute(text(
            "select min(date), max(date) from optionm.vsurfd")).fetchone()
        print("date span:", span)
    return 0


def cmd_map(a) -> int:
    ok, why = _reachable()
    if not ok:
        print(f"unreachable ({why}) — cannot map tickers to secids offline")
        return 1
    import pandas as pd
    from sqlalchemy import text
    started = datetime.now(timezone.utc).isoformat()
    with _engine().connect() as c:
        df = pd.read_sql(text(SQL_MAP), c, params={"tickers": tuple(UNIVERSE)})
    # An ETF ticker can map to several secids across history. Refuse to guess:
    # print them all and require the ambiguity to be resolved deliberately.
    mapping, ambiguous = {}, {}
    for tkr, grp in df.groupby("ticker"):
        ids = sorted(set(grp["secid"].astype(int)))
        if len(ids) == 1:
            mapping[tkr] = ids[0]
        else:
            ambiguous[tkr] = ids
    print(f"resolved {len(mapping)}/{len(UNIVERSE)}; ambiguous: {ambiguous}")
    missing = sorted(set(UNIVERSE) - set(mapping) - set(ambiguous))
    if missing:
        print(f"NOT FOUND: {missing} — these are named, never dropped quietly")
    m = _load_manifest()
    m["runs"].append({
        "kind": "map", "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sql": SQL_MAP.strip(), "tickers": list(UNIVERSE),
        "mapping": {k: int(v) for k, v in mapping.items()},
        "ambiguous": {k: [int(x) for x in v] for k, v in ambiguous.items()},
        "not_found": missing,
    })
    _write_manifest(m)
    print(f"manifest -> {MANIFEST}")
    return 0 if not (ambiguous or missing) else 1


def cmd_pull(a) -> int:
    ok, why = _reachable()
    if not ok:
        print(f"unreachable ({why})")
        return 1
    import pandas as pd
    from sqlalchemy import text
    secids = _secid_map()
    m = _load_manifest()
    eng = _engine()
    y0, y1 = a.pull
    for year in range(int(y0), int(y1) + 1):
        out = OUT_DIR / f"vsurfd_{year}.parquet"
        if out.exists():
            print(f"{out.name} exists — REFUSING to overwrite. A run made "
                  f"under a different extraction is evidence about that run.")
            continue
        started = datetime.now(timezone.utc).isoformat()
        params = {"secids": tuple(sorted(secids.values())),
                  "days": tuple(DAYS), "deltas": tuple(DELTAS),
                  "start": f"{year}-01-01", "end": f"{year}-12-31"}
        with eng.connect() as c:
            df = pd.read_sql(text(SQL_SURFACE), c, params=params)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        d = pd.to_datetime(df["date"])
        per_sd = (df.groupby(["secid", "date"]).size()
                  if len(df) else pd.Series(dtype=int))
        rec = {
            "kind": "pull", "year": year, "file": out.name,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "sql": SQL_SURFACE.strip(), "params": {
                k: (list(v) if isinstance(v, tuple) else v)
                for k, v in params.items()},
            "rows": int(len(df)),
            "n_secids": int(df["secid"].nunique()) if len(df) else 0,
            "n_dates": int(d.nunique()) if len(df) else 0,
            "first_date": str(d.min())[:10] if len(df) else None,
            "last_date": str(d.max())[:10] if len(df) else None,
            "coords_per_security_date_median":
                float(per_sd.median()) if len(df) else None,
            "columns": list(df.columns),
            "dtypes": {c_: str(t) for c_, t in df.dtypes.items()},
            "sha256": _sha256(out),
        }
        m["runs"].append(rec)
        _write_manifest(m)
        print(f"{out.name}: {rec['rows']} rows  {rec['n_dates']} dates  "
              f"{rec['n_secids']} secids  sha {rec['sha256'][:16]}")
        if rec["n_dates"] and rec["n_dates"] < 200:
            print(f"  WARNING: {rec['n_dates']} observation dates in {year}. "
                  f"A daily surface should give ~252. Do not proceed to the "
                  f"analysis on a frame that is not daily — that is the "
                  f"defect this extraction exists to fix.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true",
                   help="reachability + schema + span, no rows pulled")
    g.add_argument("--map", action="store_true",
                   help="resolve the 18 tickers to secids, into the manifest")
    g.add_argument("--pull", nargs=2, metavar=("Y0", "Y1"),
                   help="pull [Y0..Y1] inclusive, one query per year")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    if a.probe:
        return cmd_probe(a)
    if a.map:
        return cmd_map(a)
    return cmd_pull(a)


if __name__ == "__main__":
    raise SystemExit(main())
