"""WRDS training-data substrate puller — manifest-driven, resumable.

    python -m scripts.wrds_training_pull links finratio ibes fundq bondret
    python -m scripts.wrds_training_pull global_factor
    python -m scripts.wrds_training_pull dsf          # per-year, resumable
    python -m scripts.wrds_training_pull --list

Scope: every PERMNO in the CRSP PIT screen (6,894 — the SUPERSET of the
4,796 ever-eligible; eligibility is a formation-time filter downstream),
2013-01-01 .. 2024-12-31 (the entitled CRSP vintage ends 2024-12-31). Every dataset
writes `<name>.parquet` + `<name>.meta.json` under
backend/data/optimus/wrds/ and is SKIPPED if the parquet already exists
(delete to re-pull). Parquets are gitignored; metas are committed.

PIT discipline: each meta records the as-of/knowledge-date column that
downstream feature builders MUST use (public_date, statpers, rdq, ...).
This module builds SUBSTRATE — no verdicts, no backtests; those need
their own preregistrations.

Authority for entitlement claims: entitlement_map_2026-08-19.json
(catalogue is not entitlement).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "wrds"
UNIVERSE = (_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
            "crsp_pit_monthly_v1.parquet")
START, END = "2013-01-01", "2024-12-31"


def _conn():
    os.environ.setdefault("PGPASSFILE", os.path.expandvars(
        r"%APPDATA%\postgresql\pgpass.conf"))
    import psycopg2
    c = psycopg2.connect(host="wrds-pgdata.wharton.upenn.edu", port=9737,
                         dbname="wrds", user="murathan12",
                         sslmode="require", connect_timeout=15)
    c.set_session(readonly=True, autocommit=True)
    return c


def _permnos() -> list[int]:
    u = pd.read_parquet(UNIVERSE, columns=["permno"])
    return sorted(int(p) for p in u["permno"].unique())


def _write(name: str, df: pd.DataFrame, *, sql_note: str, pit: str,
           extra: dict | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.parquet"
    df.to_parquet(p, index=False)
    meta = {"dataset": name,
            "pulled_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "rows": int(len(df)), "cols": list(df.columns),
            "window": [START, END],
            "universe": "crsp_pit_monthly_v1 ALL screened PERMNOs (6,894 "
                        "superset; the 4,796 ever-ELIGIBLE subset is a "
                        "downstream formation-time filter, never a pull "
                        "filter)",
            "pit_knowledge_column": pit,
            "sql_note": sql_note, **(extra or {})}
    (OUT / f"{name}.meta.json").write_text(json.dumps(meta, indent=2),
                                           encoding="utf-8")
    print(f"  {name}: {len(df):,} rows -> {p.name}")


def _done(name: str) -> bool:
    if (OUT / f"{name}.parquet").exists():
        print(f"  {name}: exists, skipped (delete parquet to re-pull)")
        return True
    return False


# ── datasets ───────────────────────────────────────────────────────────────
def pull_links(conn, permnos):
    for name, sql, pit in [
        ("link_ibes_crsp",
         "SELECT ticker, permno, ncusip, sdate, edate, score "
         "FROM wrdsapps_link_crsp_ibes.ibcrsphist", "sdate..edate validity"),
        ("link_optionm_crsp",
         "SELECT secid, permno, sdate, edate, score "
         "FROM wrdsapps_link_crsp_optionm.opcrsphist",
         "sdate..edate validity"),
        ("link_bond_crsp",
         "SELECT * FROM wrdsapps_link_crsp_bond.bondcrsp_link",
         "link validity range"),
        ("link_ccm",
         "SELECT gvkey, lpermno AS permno, linktype, linkprim, linkdt, "
         "linkenddt FROM crsp.ccmxpf_lnkhist "
         "WHERE linktype IN ('LU','LC') AND linkprim IN ('P','C')",
         "linkdt..linkenddt validity"),
    ]:
        if _done(name):
            continue
        _write(name, pd.read_sql(sql, conn), sql_note=sql, pit=pit)


def pull_finratio(conn, permnos):
    if _done("finratio_monthly"):
        return
    sql = ("SELECT * FROM wrdsapps_finratio.firm_ratio "
           "WHERE permno = ANY(%(p)s) "
           "AND public_date BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn,
                     params={"p": permnos, "s": START, "e": END})
    _write("finratio_monthly", df, sql_note=sql,
           pit="public_date (WRDS's own availability stamp)")


def pull_ibes(conn, permnos):
    if _done("ibes_consensus_monthly"):
        return
    sql = ("SELECT s.ticker, l.permno, s.statpers, s.measure, s.fpi, "
           "s.numest, s.numup, s.numdown, s.medest, s.meanest, s.stdev, "
           "s.highest, s.lowest, s.fpedats, s.actual, s.anndats_act "
           "FROM ibes.statsum_epsus s "
           "JOIN wrdsapps_link_crsp_ibes.ibcrsphist l "
           "ON s.ticker = l.ticker "
           "AND s.statpers BETWEEN l.sdate AND COALESCE(l.edate, %(e)s) "
           "WHERE l.permno = ANY(%(p)s) AND l.score <= 2 "
           "AND s.measure = 'EPS' AND s.fpi IN ('0','1','2','6') "
           "AND s.statpers BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn,
                     params={"p": permnos, "s": START, "e": END})
    _write("ibes_consensus_monthly", df, sql_note=sql,
           pit="statpers (consensus computed as of this date); "
               "anndats_act is when the actual became known — never use "
               "actual before anndats_act")


def pull_fundq(conn, permnos):
    if _done("compustat_fundq"):
        return
    cols = ("gvkey, datadate, rdq, fyearq, fqtr, saleq, revtq, cogsq, "
            "xsgaq, oibdpq, ibq, niq, epspxq, epsfxq, atq, actq, cheq, "
            "rectq, invtq, lctq, ltq, dlttq, dlcq, ceqq, seqq, txditcq, "
            "oancfy, capxy, dvy, cshoq, prccq")
    sql = (f"SELECT {cols} FROM comp.fundq "
           "WHERE gvkey IN (SELECT gvkey FROM crsp.ccmxpf_lnkhist "
           "  WHERE lpermno = ANY(%(p)s) AND linktype IN ('LU','LC')) "
           "AND indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' "
           "AND consol = 'C' AND datadate BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn,
                     params={"p": permnos, "s": START, "e": END})
    _write("compustat_fundq", df, sql_note=sql,
           pit="rdq (report date = first public availability; rows with "
               "NULL rdq have no honest knowledge date — exclude from "
               "features)")


def pull_bondret(conn, permnos):
    if _done("bondret_monthly"):
        return
    sql = ("SELECT b.date, b.cusip, b.company_symbol, l.permno, "
           "b.maturity, b.coupon, b.ret_eom, b.ret_ldm, b.price_eom, "
           "b.t_spread, b.yield, b.rating_num, b.amount_outstanding "
           "FROM wrdsapps_bondret.bondret b "
           "JOIN wrdsapps_link_crsp_bond.bondcrsp_link l "
           "ON b.cusip = l.cusip "
           "WHERE l.permno = ANY(%(p)s) "
           "AND b.date BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn,
                     params={"p": permnos, "s": START, "e": END})
    _write("bondret_monthly", df, sql_note=sql,
           pit="date (month-end trade-based return; TRACE-derived, "
               "public at month end)")


def pull_global_factor(conn, permnos):
    if _done("jkp_global_factor_usa"):
        return
    # column set varies by vintage — introspect, keep permno+eom+chars
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='contrib_global_factor' "
                "AND table_name='global_factor'")
    cols = [r[0] for r in cur.fetchall()]
    if "permno" not in cols:
        print("  jkp_global_factor_usa: no permno column, REFUSED "
              f"(cols sample {cols[:10]})")
        return
    datecol = "eom" if "eom" in cols else "date"
    sql = ("SELECT * FROM contrib_global_factor.global_factor "
           "WHERE excntry = 'USA' AND permno = ANY(%(p)s) "
           f"AND {datecol} BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn,
                     params={"p": permnos, "s": START, "e": END})
    _write("jkp_global_factor_usa", df, sql_note=sql,
           pit=f"{datecol} (JKP characteristics are formation-date "
               "stamped; each char derives from data public by then per "
               "JKP construction — spot-audit before first trial use)",
           extra={"source": "Jensen-Kelly-Pedersen via "
                            "contrib_global_factor (WRDS contributed)"})


def pull_dsf(conn, permnos):
    for yr in range(2013, 2025):
        name = f"crsp_dsf_{yr}"
        if _done(name):
            continue
        sql = ("SELECT permno, date, prc, ret, retx, vol, shrout, "
               "askhi, bidlo, openprc, cfacpr, cfacshr "
               "FROM crsp.dsf WHERE permno = ANY(%(p)s) "
               "AND date BETWEEN %(s)s AND %(e)s")
        df = pd.read_sql(sql, conn, params={"p": permnos,
                                            "s": f"{yr}-01-01",
                                            "e": f"{yr}-12-31"})
        _write(name, df, sql_note=sql,
               pit="date (daily bar, public at close); |prc| convention: "
                   "negative = bid/ask midpoint on no-trade days; vol in "
                   "SHARES on dsf (not hundreds — that is msf)")


def pull_optionm_surface(conn, permnos):
    """30-day surface IVs at |delta| 25/50, calls+puts, per year."""
    link = pd.read_parquet(OUT / "link_optionm_crsp.parquet")
    secids = sorted(int(s) for s in
                    link[link["permno"].isin(permnos)]["secid"].unique())
    for yr in range(2013, 2025):
        name = f"optionm_surface30d_{yr}"
        if _done(name):
            continue
        sql = (f"SELECT secid, date, days, delta, impl_volatility, "
               f"cp_flag, dispersion FROM optionm.vsurfd{yr} "
               "WHERE secid = ANY(%(sec)s) AND days = 30 "
               "AND abs(delta) IN (25, 50)")
        df = pd.read_sql(sql, conn, params={"sec": secids})
        _write(name, df, sql_note=sql,
               pit="date (end-of-day surface, public next morning; treat "
                   "as known at t+1 open to be conservative)",
               extra={"n_secids": len(secids),
                      "join": "opcrsphist sdate..edate validity applies "
                              "downstream"})


def pull_iid(conn, permnos):
    """WRDS Intraday Indicators (taqmsec), daily per symbol, per year."""
    link = pd.read_sql(
        "SELECT permno, symbol, date, score FROM "
        "wrdsapps_link_crsp_taq.tclink WHERE permno = ANY(%(p)s)",
        conn, params={"p": permnos})
    syms = sorted(link["symbol"].dropna().unique().tolist())
    for yr in range(2013, 2025):
        name = f"taq_iid_{yr}"
        if _done(name):
            continue
        sql = (f"SELECT * FROM taqmsec.wrds_iid_{yr} "
               "WHERE sym_root = ANY(%(sy)s) AND sym_suffix IS NULL")
        df = pd.read_sql(sql, conn, params={"sy": syms})
        _write(name, df, sql_note=sql,
               pit="date (intraday aggregates final after close); join to "
                   "permno via tclink DATED validity — symbols are reused "
                   "across time (canon: sym_suffix IS NULL, never = '')")
    if not (OUT / "link_taq_crsp.parquet").exists():
        _write("link_taq_crsp", link,
               sql_note="tclink for universe permnos", pit="date validity")


def pull_13f(conn, permnos):
    """Thomson 13F holdings restricted to universe CUSIPs, quarterly."""
    if _done("tr13f_s34_universe"):
        return
    cus = pd.read_sql(
        "SELECT DISTINCT permno, ncusip FROM crsp.stocknames "
        "WHERE permno = ANY(%(p)s) AND ncusip IS NOT NULL",
        conn, params={"p": permnos})
    cusips = sorted(cus["ncusip"].unique().tolist())
    sql = ("SELECT fdate, rdate, mgrno, mgrname, typecode, cusip, shares, "
           "change, prc, shrout1 FROM tr_13f.s34 "
           "WHERE cusip = ANY(%(c)s) AND fdate BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn,
                     params={"c": cusips, "s": START, "e": END})
    _write("tr13f_s34_universe", df, sql_note=sql,
           pit="fdate (vintage/file date = when holdings became public); "
               "rdate is the quarter-end the holdings DESCRIBE — features "
               "may never use rdate as the knowledge date",
           extra={"n_cusips": len(cusips)})
    if not (OUT / "link_cusip_permno.parquet").exists():
        _write("link_cusip_permno", cus,
               sql_note="crsp.stocknames ncusip map", pit="dated names")


DATASETS = {"links": pull_links, "finratio": pull_finratio,
            "ibes": pull_ibes, "fundq": pull_fundq,
            "bondret": pull_bondret, "global_factor": pull_global_factor,
            "dsf": pull_dsf, "optionm": pull_optionm_surface,
            "iid": pull_iid, "s13f": pull_13f}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wrds_training_pull")
    ap.add_argument("datasets", nargs="*", choices=[*DATASETS, []])
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    if a.list or not a.datasets:
        print("datasets:", ", ".join(DATASETS))
        return 0
    permnos = _permnos()
    print(f"universe: {len(permnos)} PERMNOs, window {START}..{END}")
    conn = _conn()
    try:
        for name in a.datasets:
            print(f"[{name}]")
            DATASETS[name](conn, permnos)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
