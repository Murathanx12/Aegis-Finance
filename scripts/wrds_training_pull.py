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
EARLY_START, EARLY_END = "1990-01-01", "2012-12-31"
EARLY_UNIVERSE = ("crsp_pit_monthly_early ALL screened PERMNOs (6,988 "
                  "eligible, 1,463 delistings); the HELD-OUT early-era "
                  "confirmation slice — a different universe file from "
                  "the modern pulls, which is exactly why the window and "
                  "universe fields must derive from the data")


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


def _date_ranges(df: pd.DataFrame) -> dict:
    """Observed min/max for every date-like column, from the DATA.

    Never trust a module constant to describe a pull: the early-era
    functions override the window inline, so a hardcoded [START, END]
    silently mislabels them (found 2026-08-20 — every meta.json on disk
    claimed 2013-2024, including the 1990-2012 slices).
    """
    out = {}
    for c in df.columns:
        lc = c.lower()
        if not any(k in lc for k in ("date", "dat", "eom", "public",
                                     "statpers", "rdq")):
            continue
        try:
            s = pd.to_datetime(df[c], errors="coerce").dropna()
        except Exception:
            continue
        if len(s):
            out[c] = [str(s.min())[:10], str(s.max())[:10]]
    return out


def _write(name: str, df: pd.DataFrame, *, sql_note: str, pit: str,
           universe: str | None = None,
           extra: dict | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.parquet"
    df.to_parquet(p, index=False)
    ranges = _date_ranges(df)
    # the window is whatever the PIT knowledge column actually spans;
    # fall back to the union of all date columns, never to a constant.
    pit_col = pit.split(";")[0].split()[0].strip().lower()
    if pit_col in ranges:
        window, wsrc = ranges[pit_col], pit_col
    elif ranges:
        window = [min(v[0] for v in ranges.values()),
                  max(v[1] for v in ranges.values())]
        wsrc = "union:" + ",".join(sorted(ranges))
    else:
        window, wsrc = None, "no date column"
    meta = {"dataset": name,
            "pulled_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "rows": int(len(df)), "cols": list(df.columns),
            "window": window,
            "window_source": wsrc,
            "date_ranges_observed": ranges,
            "universe": universe or (
                "crsp_pit_monthly_v1 ALL screened PERMNOs (6,894 "
                "superset; the 4,796 ever-ELIGIBLE subset is a "
                "downstream formation-time filter, never a pull "
                "filter)"),
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


def pull_finratio_early(conn, permnos):
    """finratio for the HELD-OUT early era; universe = early PIT screen."""
    if _done("finratio_monthly_early"):
        return
    early = pd.read_parquet(_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
                            "crsp_pit_monthly_early.parquet",
                            columns=["permno"])
    pn = sorted(int(p) for p in early["permno"].unique())
    sql = ("SELECT gvkey, permno, public_date, bm, roe "
           "FROM wrdsapps_finratio.firm_ratio "
           "WHERE permno = ANY(%(p)s) "
           "AND public_date BETWEEN '1990-01-01' AND '2012-12-31'")
    df = pd.read_sql(sql, conn, params={"p": pn})
    _write("finratio_monthly_early", df, sql_note=sql,
           universe=EARLY_UNIVERSE,
           pit="public_date; early-era confirmation slice, columns "
               "limited to the two signals the frozen grammar uses")


def pull_dsf_early(conn, permnos):
    """Daily prices for the HELD-OUT early era; own universe file."""
    early = pd.read_parquet(_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
                            "crsp_pit_monthly_early.parquet",
                            columns=["permno"])
    pn = sorted(int(p) for p in early["permno"].unique())
    for yr in range(1990, 2013):
        name = f"crsp_dsf_{yr}"
        if _done(name):
            continue
        sql = ("SELECT permno, date, prc, ret, vol "
               "FROM crsp.dsf WHERE permno = ANY(%(p)s) "
               "AND date BETWEEN %(s)s AND %(e)s")
        df = pd.read_sql(sql, conn, params={"p": pn,
                                            "s": f"{yr}-01-01",
                                            "e": f"{yr}-12-31"})
        _write(name, df, sql_note=sql,
               pit="date (daily bar); early-era confirmation slice",
               universe=EARLY_UNIVERSE,)


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
        sql = (f"SELECT date, sym_root, total_trade, total_vol, "
               f"total_dv_lr, buyvol_lr, sellvol_lr, buynumtrades_lr, "
               f"sellnumtrades_lr, cprc, oprc "
               f"FROM taqmsec.wrds_iid_{yr} "
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
    """Thomson 13F holdings restricted to universe CUSIPs, PER YEAR —
    the single-query version was killed three times at ~50M rows."""
    cus = pd.read_sql(
        "SELECT DISTINCT permno, ncusip FROM crsp.stocknames "
        "WHERE permno = ANY(%(p)s) AND ncusip IS NOT NULL",
        conn, params={"p": permnos})
    if not (OUT / "link_cusip_permno.parquet").exists():
        _write("link_cusip_permno", cus,
               sql_note="crsp.stocknames ncusip map", pit="dated names")
    cusips = sorted(cus["ncusip"].unique().tolist())
    for yr in range(2013, 2025):
        name = f"tr13f_s34_{yr}"
        if _done(name):
            continue
        sql = ("SELECT fdate, rdate, mgrno, typecode, cusip, shares, "
               "change FROM tr_13f.s34 "
               "WHERE cusip = ANY(%(c)s) AND fdate BETWEEN %(s)s AND %(e)s")
        df = pd.read_sql(sql, conn, params={"c": cusips,
                                            "s": f"{yr}-01-01",
                                            "e": f"{yr}-12-31"})
        _write(name, df, sql_note=sql,
               pit="fdate (vintage = when holdings became public); rdate "
                   "is the described quarter-end — never the knowledge "
                   "date", extra={"n_cusips": len(cusips)})


DATASETS = {"links": pull_links, "finratio": pull_finratio,
            "ibes": pull_ibes, "fundq": pull_fundq,
            "bondret": pull_bondret, "global_factor": pull_global_factor,
            "dsf": pull_dsf, "optionm": pull_optionm_surface,
            "iid": pull_iid, "s13f": pull_13f,
            "dsf_early": pull_dsf_early,
            "finratio_early": pull_finratio_early}


def pull_optionm_early(conn, permnos):
    """1996–2012 surfaces for the early universe — the OPTIONS-RUNG
    confirmation slice (prereg frozen before this function first ran)."""
    early = pd.read_parquet(_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
                            "crsp_pit_monthly_early.parquet",
                            columns=["permno"])
    pn = sorted(int(p) for p in early["permno"].unique())
    link = pd.read_parquet(OUT / "link_optionm_crsp.parquet")
    secids = sorted(int(s) for s in
                    link[link["permno"].isin(pn)]["secid"].unique())
    for yr in range(1996, 2013):
        name = f"optionm_surface30d_{yr}"
        if _done(name):
            continue
        sql = (f"SELECT secid, date, days, delta, impl_volatility, "
               f"cp_flag, dispersion FROM optionm.vsurfd{yr} "
               "WHERE secid = ANY(%(sec)s) AND days = 30 "
               "AND abs(delta) IN (25, 50)")
        df = pd.read_sql(sql, conn, params={"sec": secids})
        _write(name, df, sql_note=sql,
               pit="date (EOD surface); early-era confirmation slice",
               universe=EARLY_UNIVERSE,
               extra={"n_secids": len(secids)})


def pull_ibes_early(conn, permnos):
    if _done("ibes_consensus_monthly_early"):
        return
    early = pd.read_parquet(_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
                            "crsp_pit_monthly_early.parquet",
                            columns=["permno"])
    pn = sorted(int(p) for p in early["permno"].unique())
    sql = ("SELECT s.ticker, l.permno, s.statpers, s.measure, s.fpi, "
           "s.numest, s.numup, s.numdown, s.medest, s.meanest, s.stdev, "
           "s.fpedats, s.actual, s.anndats_act "
           "FROM ibes.statsum_epsus s "
           "JOIN wrdsapps_link_crsp_ibes.ibcrsphist l "
           "ON s.ticker = l.ticker "
           "AND s.statpers BETWEEN l.sdate AND COALESCE(l.edate, %(e)s) "
           "WHERE l.permno = ANY(%(p)s) AND l.score <= 2 "
           "AND s.measure = 'EPS' AND s.fpi IN ('0','1','2','6') "
           "AND s.statpers BETWEEN %(s)s AND %(e)s")
    df = pd.read_sql(sql, conn, params={"p": pn, "s": "1990-01-01",
                                        "e": "2012-12-31"})
    _write("ibes_consensus_monthly_early", df, sql_note=sql,
           universe=EARLY_UNIVERSE,
           pit="statpers; anndats_act gates actuals")


def pull_13f_early(conn, permnos):
    early = pd.read_parquet(_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
                            "crsp_pit_monthly_early.parquet",
                            columns=["permno"])
    pn = sorted(int(p) for p in early["permno"].unique())
    cus = pd.read_sql(
        "SELECT DISTINCT permno, ncusip FROM crsp.stocknames "
        "WHERE permno = ANY(%(p)s) AND ncusip IS NOT NULL",
        conn, params={"p": pn})
    cusips = sorted(cus["ncusip"].unique().tolist())
    if not (OUT / "link_cusip_permno_early.parquet").exists():
        _write("link_cusip_permno_early", cus,
               sql_note="crsp.stocknames early ncusip map",
           universe=EARLY_UNIVERSE,
               pit="dated names")
    for yr in range(1996, 2013):
        name = f"tr13f_s34_{yr}"
        if _done(name):
            continue
        sql = ("SELECT fdate, rdate, mgrno, typecode, cusip, shares, "
               "change FROM tr_13f.s34 "
               "WHERE cusip = ANY(%(c)s) AND fdate BETWEEN %(s)s AND %(e)s")
        df = pd.read_sql(sql, conn, params={"c": cusips,
                                            "s": f"{yr}-01-01",
                                            "e": f"{yr}-12-31"})
        _write(name, df, sql_note=sql,
               pit="fdate (vintage); early-era manager-behavior slice",
               universe=EARLY_UNIVERSE,
               extra={"n_cusips": len(cusips)})


DATASETS.update({"optionm_early": pull_optionm_early,
                 "ibes_early": pull_ibes_early,
                 "s13f_early": pull_13f_early})


# ── round 2: entitled schemas the first pass never touched ─────────────────
# The entitlement probe found 46 SELECT-OK schemas; the first pass drew on
# nine. These are the remainder that bear on questions Order 24 left open,
# not a sweep for its own sake:
#   ff       the REAL Fama-French factors — Order 24 demanded an FF5+MOM
#            residual-alpha gate and it has been running on JKP proxies
#   frb      83 rate/term-structure series — candidate observables for the
#            LEVEL ceiling REGIME-RISK-CONDITIONING-1 could not reach
#   boardex  governance: a genuinely new information class, and
#            INFORMATION-DIMENSION-1 found none of the ones we own separate
#   compseg  business segments — another untried information class
#   patents  innovation — another untried information class
#   finratio_ibes  ratio set keyed on permno + public_date, PIT-stamped

def _all_permnos() -> list[int]:
    """Both eras' universes. Round-2 sources are era-agnostic."""
    out = set()
    for f in ("crsp_pit_monthly_v1.parquet", "crsp_pit_monthly_early.parquet"):
        p = _config.OPTIMUS_LEDGER_DIR / "crsp_pit" / f
        if p.exists():
            out |= {int(x) for x in
                    pd.read_parquet(p, columns=["permno"])["permno"].unique()}
    return sorted(out)


def pull_ff(conn, permnos):
    """Fama-French factors + Pastor-Stambaugh liquidity. Small, and the
    thing every residual-alpha gate in the programme should have used."""
    for name, sql, pit in [
        ("ff_fivefactors_daily",
         "SELECT * FROM ff.fivefactors_daily", "date"),
        ("ff_fivefactors_monthly",
         "SELECT * FROM ff.fivefactors_monthly", "date"),
        ("ff_factors_daily", "SELECT * FROM ff.factors_daily", "date"),
        ("ff_factors_monthly", "SELECT * FROM ff.factors_monthly", "date"),
        ("ff_liq_ps", "SELECT * FROM ff.liq_ps", "date"),
    ]:
        if _done(name):
            continue
        _write(name, pd.read_sql(sql, conn), sql_note=sql, pit=pit,
               universe="market-wide factor series; no security universe",
               extra={"source": "Kenneth French / WRDS ff schema",
                      "use": "FF5+MOM residual-alpha gate (Order 24 "
                             "standing rule) — replaces the JKP proxy set"})


def pull_frb(conn, permnos):
    """Fed rates and FX. Term structure and credit spreads are the
    classic market-wide LEVEL observables, which is precisely what
    REGIME-RISK-CONDITIONING-1 found missing."""
    for name, sql, pit in [
        ("frb_rates_daily", "SELECT * FROM frb.rates_daily", "date"),
        ("frb_rates_monthly", "SELECT * FROM frb.rates_monthly", "date"),
    ]:
        if _done(name):
            continue
        _write(name, pd.read_sql(sql, conn), sql_note=sql, pit=pit,
               universe="market-wide rate series; no security universe",
               extra={"use": "candidate observables for the level ceiling "
                             "REGIME-RISK-CONDITIONING-1 could not reach"})


def pull_finratio_ibes(conn, permnos):
    if _done("finratio_ibes_monthly"):
        return
    pn = _all_permnos()
    sql = ("SELECT * FROM wrdsapps_finratio_ibes.firm_ratio_ibes "
           "WHERE permno = ANY(%(p)s)")
    df = pd.read_sql(sql, conn, params={"p": pn})
    _write("finratio_ibes_monthly", df, sql_note=sql,
           pit="public_date (WRDS availability stamp)",
           universe="both eras' PIT universes, union",
           extra={"n_permnos_requested": len(pn)})


def pull_boardex(conn, permnos):
    """Governance. A NEW information class — the ones already owned
    (options, expectations, liquidity) did not separate."""
    for name, sql, pit in [
        ("boardex_na_board_characteristics",
         "SELECT * FROM boardex.na_board_characteristics", "annualreportdate"),
        ("boardex_na_company_profile_stocks",
         "SELECT * FROM boardex.na_company_profile_stocks", "isin/ticker map"),
    ]:
        if _done(name):
            continue
        try:
            df = pd.read_sql(sql, conn)
        except Exception as e:                                 # noqa: BLE001
            print(f"  {name}: REFUSED/failed -> {type(e).__name__}: {e}")
            conn.rollback() if hasattr(conn, "rollback") else None
            continue
        _write(name, df, sql_note=sql, pit=pit,
               universe="BoardEx North America; links to CRSP via ticker/"
                        "ISIN and is NOT yet linked — linkage is a "
                        "downstream job, not a pull filter",
               extra={"caveat": "no permno on these rows; any trial using "
                                "them must build and audit the link first"})


def pull_compseg(conn, permnos):
    if _done("compseg_segmerged"):
        return
    sql = ("SELECT * FROM compseg.wrds_segmerged WHERE gvkey IN "
           "(SELECT gvkey FROM crsp.ccmxpf_lnkhist WHERE lpermno = ANY(%(p)s)"
           " AND linktype IN ('LU','LC'))")
    df = pd.read_sql(sql, conn, params={"p": _all_permnos()})
    _write("compseg_segmerged", df, sql_note=sql,
           pit="datadate/srcdate — segment data is as-reported; gate on "
               "the parent filing's rdq before any feature use",
           universe="gvkeys linked to both eras' PIT permnos")


def pull_patents(conn, permnos):
    """Innovation, as a gvkey-year aggregate rather than raw patents —
    the aggregate is the feature; the 10M-row raw table is not."""
    if _done("patents_gvkey_year"):
        return
    sql = ("SELECT l.gvkey, EXTRACT(YEAR FROM m.grantdate)::int AS year, "
           "COUNT(*) AS n_patents, "
           "SUM(m.forward_cites) AS forward_cites, "
           "SUM(m.backward_cites) AS backward_cites "
           "FROM wrdsapps_patents.uspatents_meta m "
           "JOIN wrdsapps_patents.uspatents_gvkey_linking l "
           "ON m.patnum = l.patnum "
           "WHERE m.grantdate IS NOT NULL "
           "GROUP BY l.gvkey, EXTRACT(YEAR FROM m.grantdate)")
    df = pd.read_sql(sql, conn)
    _write("patents_gvkey_year", df, sql_note=sql,
           pit="grantdate year — a patent is public at GRANT, never at "
               "application; forward_cites accumulate AFTER the grant and "
               "are NOT point-in-time (using them at t is lookahead)",
           universe="all linked gvkeys (filter downstream)",
           extra={"warning": "forward_cites is a FUTURE quantity by "
                             "construction — the single most common "
                             "lookahead in the patent literature"})


DATASETS.update({"ff": pull_ff, "frb": pull_frb,
                 "finratio_ibes": pull_finratio_ibes,
                 "boardex": pull_boardex, "compseg": pull_compseg,
                 "patents": pull_patents})


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
