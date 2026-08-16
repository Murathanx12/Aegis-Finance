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

#: THE ROUTE. Measured 2026-08-16, and it corrects an earlier reading of mine.
#:
#: `wrds-pgdata:9737`, `wrds-pgdata:5432` and `wrds-www:443` all time out from
#: this network, which I first read as "the route to Wharton is closed, needs a
#: campus VPN". It is not. DNS resolves all three names to 165.123.60.0/24, and
#: `wrds-cloud.wharton.upenn.edu:22` **connects and offers keyboard-interactive
#: auth**. Same /24, same instant. So the block is PORT FILTERING on this
#: network, not a route, and one open port is enough:
#:
#:   ssh -N -L 9737:wrds-pgdata.wharton.upenn.edu:9737 \
#:       murathan12@wrds-cloud.wharton.upenn.edu
#:
#: Three hosts timing out looked like one cause and was one guess. The cheap
#: check that distinguished them was a fourth port, and it took ten seconds.
TUNNEL_ADDR = "127.0.0.1"

#: `host` stays the real WRDS name even when tunnelled, and only `hostaddr` is
#: redirected. libpq uses `host` for the pgpass lookup and `hostaddr` for the
#: socket, so the existing `%APPDATA%\\postgresql\\pgpass.conf` entry keyed on
#: `wrds-pgdata.wharton.upenn.edu:9737:wrds:murathan12` keeps matching. The
#: alternative — adding a `localhost` line to the credential file — would edit
#: Murat's credentials to work around a networking detail, which is the wrong
#: file to touch for this reason.

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

#: PER-YEAR TABLES, discovered rather than assumed. There is no unified
#: `optionm.vsurfd`: the daily surface is `optionm.vsurfd2000` .. `vsurfd2025`
#: (and `vsurfbrYYYY` for the Brazilian panel, which is not this universe).
#: The prereg named the family `optionm.vsurfd`; that stays true as a family
#: name and the manifest records the exact per-year relation actually queried.
#:
#: Scale, measured on one year: `optionm.vsurfd2015` holds **404,564,776 rows
#: across 252 distinct observation dates**, 2015-01-02 .. 2015-12-31. Our
#: month-end extraction of the same year holds 12 dates. That is the vendor
#: confirming, from its own table, that the month-end limitation reported twice
#: in this programme was OUR `WHERE` clause. At 404M rows/year the bound below
#: is not an optimisation, it is what makes the pull possible at all.
SQL_SURFACE = """
select secid, date, days, delta, cp_flag, impl_volatility, dispersion
from optionm.vsurfd{year}
where secid in :secids
  and days in :days
  and delta in :deltas
  and date >= :start and date <= :end
"""

SQL_MAP = """
select secid, cusip, ticker, class, issue_type, index_flag, exchange_d
from optionm.securd
where ticker in :tickers
"""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tcp(host: str, port: int, timeout: float = 12.0) -> tuple[bool, str]:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True, "tcp ok"
    except Exception as exc:                                     # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        s.close()


def tunnel_open() -> bool:
    """Is a local forward listening on 9737? Checked, never assumed.

    Assuming the tunnel is up produces a connection error that reads exactly
    like bad credentials, and the next hour goes into the wrong file.
    """
    return _tcp(TUNNEL_ADDR, PORT, timeout=3.0)[0]


def _reachable() -> tuple[bool, str]:
    """Say WHY, not just no. A pull that fails silently looks like empty data."""
    if tunnel_open():
        return True, f"tcp ok via local forward {TUNNEL_ADDR}:{PORT}"
    return _tcp(HOST, PORT)


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
    url = f"postgresql+psycopg2://{USER}@{HOST}:{PORT}/{DBNAME}?sslmode=require"
    if tunnel_open():
        # `host` is left alone so pgpass still matches; only the socket moves.
        url += f"&hostaddr={TUNNEL_ADDR}"
    return create_engine(url)


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
        ssh_ok, ssh_why = _tcp("wrds-cloud.wharton.upenn.edu", 22, timeout=8)
        print("\nNOT A CODE FAILURE. The endpoint was called and the status is "
              "printed above. Nothing here is blocked on credentials or on "
              "this script.")
        print(f"  wrds-cloud.wharton.upenn.edu:22 -> "
              f"{'OPEN' if ssh_ok else 'BLOCKED'} ({ssh_why})")
        if ssh_ok:
            print("\n  So the ROUTE is fine and the direct database PORT is "
                  "filtered. Open a forward in your own shell — it needs a "
                  "password and a Duo push, so it cannot be done unattended:\n")
            print(f"    ssh -N -L {PORT}:{HOST}:{PORT} "
                  f"{USER}@wrds-cloud.wharton.upenn.edu\n")
            print("  Leave it running, then re-run --probe. This script "
                  "detects the forward and routes through it without touching "
                  "the credential file.")
        else:
            print("\n  Route and port both closed — this one really is the "
                  "network (campus VPN).")
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
    from sqlalchemy import bindparam, text
    started = datetime.now(timezone.utc).isoformat()
    stmt = text(SQL_MAP).bindparams(bindparam("tickers", expanding=True))
    with _engine().connect() as c:
        df = pd.read_sql(stmt, c, params={"tickers": list(UNIVERSE)})
    # An ETF ticker maps to several secids, and 16 of our 18 do. The raw
    # ambiguity is recorded before any rule is applied, so the manifest shows
    # what was chosen FROM rather than only what was chosen.
    raw = {t: sorted(set(g["secid"].astype(int)))
           for t, g in df.groupby("ticker")}
    #
    # THE RULE, declared and derived from the vendor's OWN classification
    # columns rather than from a ticker I recognise:
    #
    #   index_flag = '0'  and  issue_type = '%'
    #
    # Every ticker here resolves to exactly three kinds of row. `index_flag='1'`
    # with `class` in {I, N}, `issue_type='A'` and `exchange_d=32768` are
    # DERIVED INDEX series on the ETF, not the fund. `issue_type='%'` with
    # `index_flag='0'` is the fund. A third kind appears for SPY (secid 7571,
    # cusip 81750M10) and GLD (8274, 80217610): `issue_type` NULL and
    # `exchange_d=0` — dead 1990s tickers that happen to reuse the symbol, and
    # the reason "pick the lowest secid" would have been wrong for two names.
    #
    # Cross-checked against an EXTERNAL identifier the vendor did not choose:
    # the surviving cusips are 78462F10 (SPY), 78467X10 (DIA), 46090E10 (QQQ),
    # 4642876x/4642872x (the iShares family) and 81369Y** (every Select Sector
    # SPDR). Two independent classifications agreeing is what makes this a
    # derivation; either one alone would be a guess with a citation.
    sel = df[(df["index_flag"].astype(str) == "0")
             & (df["issue_type"].astype(str) == "%")]
    mapping, ambiguous = {}, {}
    for tkr in sorted(raw):
        ids = sorted(set(sel.loc[sel["ticker"] == tkr, "secid"].astype(int)))
        if len(ids) == 1:
            mapping[tkr] = ids[0]
        else:
            # Still ambiguous AFTER the rule, or eliminated by it. Either way
            # the rule did not decide, so this script does not either.
            ambiguous[tkr] = raw[tkr]
    print(f"resolved {len(mapping)}/{len(UNIVERSE)} by "
          f"index_flag='0' & issue_type='%'; ambiguous: {ambiguous}")
    for t in sorted(mapping):
        cu = sel.loc[sel["secid"].astype(int) == mapping[t], "cusip"]
        print(f"   {t:<4} secid {mapping[t]:>7}  cusip {cu.iloc[0]}  "
              f"(from {len(raw[t])} candidate(s))")
    missing = sorted(set(UNIVERSE) - set(mapping) - set(ambiguous))
    if missing:
        print(f"NOT FOUND: {missing} — these are named, never dropped quietly")
    m = _load_manifest()
    m["runs"].append({
        "kind": "map", "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sql": SQL_MAP.strip(), "tickers": list(UNIVERSE),
        "disambiguation_rule": "index_flag == '0' and issue_type == '%'",
        "candidates_before_rule": {k: [int(x) for x in v]
                                   for k, v in raw.items()},
        "mapping": {k: int(v) for k, v in mapping.items()},
        "cusips": {k: str(sel.loc[sel["secid"].astype(int) == v,
                                  "cusip"].iloc[0]) for k, v in mapping.items()},
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
    from sqlalchemy import bindparam, text
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
        params = {"secids": sorted(secids.values()),
                  "days": list(DAYS), "deltas": list(DELTAS),
                  "start": f"{year}-01-01", "end": f"{year}-12-31"}
        sql = SQL_SURFACE.format(year=year)
        stmt = text(sql).bindparams(
            *(bindparam(n, expanding=True) for n in ("secids", "days", "deltas")))
        with eng.connect() as c:
            df = pd.read_sql(stmt, c, params=params)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        d = pd.to_datetime(df["date"])
        per_sd = (df.groupby(["secid", "date"]).size()
                  if len(df) else pd.Series(dtype=int))
        rec = {
            "kind": "pull", "year": year, "file": out.name,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "sql": sql.strip(), "relation": f"optionm.vsurfd{year}", "params": {
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
