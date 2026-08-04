"""Gate D2 — PIT linkage certification (AEGIS_EXECUTION_ROADMAP.md).

Builds the canonical BoardEx boardid -> CRSP permno link with point-in-time
validity windows, then measures what fraction of CRSP market cap the linked
universe covers.

Link paths, in priority order (a boardid-permno pair keeps its best path):
  A. cikcode -> comp.company.cik -> gvkey -> CCM link history -> permno
     (linktype LU/LC, linkprim P/C, linkdt..linkenddt windows)
  B. boardid -> gvkey via wrdsapps exec_boardex (WRDS-maintained match),
     then the same CCM window logic
  C. US ISIN -> 8-char CUSIP -> crsp.stocknames ncusip -> permno
     (namedt..nameenddt windows)

Pre-registered kill criterion (roadmap D2): linked coverage < ~70% of CRSP
common-stock market cap (shrcd 10/11, exchcd 1/2/3) -> STOP, fix linkage.
BoardEx NA ramps up in the early 2000s, so the gate binds on sample dates
2005-12 onward; 2000-12 is reported as informational.

Also reports the PIT hygiene facts D2 requires downstream:
  - datestartroleflag/dateendroleflag distributions in org_composition
    (imputed dates must be screened or lag-padded by consumers)
  - sentinel-date exposure (9999-12-31 / 9000-01-01 = current, 1900-01-01 =
    imputed floor) — no literal "Curr" string survives ingestion (asserted)

Outputs:
  full/link_boardid_permno.parquet   (boardid, permno, gvkey, method, linkdt, linkenddt)
  full/GATE_D2_REPORT.txt

Usage: .venv/Scripts/python.exe scripts/gate_d2_linkage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DATA = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\full")
REPORT = DATA / "GATE_D2_REPORT.txt"
LINK_OUT = DATA / "link_boardid_permno.parquet"

SAMPLE_DATES = ["2000-12-31", "2005-12-31", "2010-12-31", "2015-12-31",
                "2020-12-31", "2024-12-31"]
GATE_BINDS_FROM = "2005-12-31"  # earlier dates informational (BoardEx NA ramp-up)
KILL_THRESHOLD = 0.70

lines: list[str] = []


def say(msg: str) -> None:
    print(msg)
    lines.append(msg)


def norm_cik(s: pd.Series) -> pd.Series:
    """Digits only, no leading zeros, then zero-pad to 10 for exact joins."""
    d = s.astype("string").str.extract(r"(\d+)", expand=False)
    return d.str.lstrip("0").str.zfill(10)


def main() -> int:
    say("GATE D2 — BoardEx -> CRSP PIT linkage certification")
    say("=" * 70)

    prof = pd.read_parquet(DATA / "boardex_na_wrds_company_profile.parquet",
                           columns=["boardid", "cikcode", "ticker", "isin"])
    prof = prof.dropna(subset=["boardid"]).drop_duplicates("boardid")
    prof["boardid"] = prof["boardid"].astype("int64")
    say(f"BoardEx company profiles: {len(prof):,} unique boardids "
        f"(cik present {prof['cikcode'].notna().mean():.1%}, "
        f"isin {prof['isin'].notna().mean():.1%}, "
        f"ticker {prof['ticker'].notna().mean():.1%})")

    comp = pd.read_parquet(DATA / "comp_company_full.parquet")
    comp = comp[["gvkey", "cik"]].dropna()
    comp["cik_n"] = norm_cik(comp["cik"])

    ccm = pd.read_parquet(DATA / "crsp_ccmxpf_lnkhist_full.parquet")
    ccm = ccm[ccm["linktype"].isin(["LU", "LC"]) & ccm["linkprim"].isin(["P", "C"])]
    ccm = ccm.rename(columns={"lpermno": "permno"}).dropna(subset=["permno"])
    ccm["permno"] = ccm["permno"].astype("int64")
    ccm["linkdt"] = pd.to_datetime(ccm["linkdt"])
    ccm["linkenddt"] = pd.to_datetime(ccm["linkenddt"]).fillna(pd.Timestamp("2262-01-01"))
    ccm = ccm[["gvkey", "permno", "linkdt", "linkenddt"]]
    say(f"CCM usable link rows (LU/LC, P/C): {len(ccm):,}")

    # --- path A: cikcode -> comp cik -> gvkey -> ccm ----------------------
    a = prof.dropna(subset=["cikcode"]).copy()
    a["cik_n"] = norm_cik(a["cikcode"])
    a = a.merge(comp, on="cik_n")[["boardid", "gvkey"]].drop_duplicates()
    path_a = a.merge(ccm, on="gvkey")
    path_a["method"] = "A_cik_ccm"
    say(f"Path A (cik->gvkey->permno): {a['boardid'].nunique():,} boardids w/ gvkey, "
        f"{path_a['boardid'].nunique():,} w/ permno")

    # --- path B: exec_boardex boardid -> gvkey -> ccm ---------------------
    ex = pd.read_parquet(DATA / "link_boardex_exec_boardex.parquet",
                         columns=["boardid", "gvkey", "score"])
    ex = ex.dropna(subset=["boardid", "gvkey"])
    ex["boardid"] = ex["boardid"].astype("int64")
    ex["gvkey"] = ex["gvkey"].astype("int64").astype(str).str.zfill(6)
    ex = ex[["boardid", "gvkey"]].drop_duplicates()
    path_b = ex.merge(ccm, on="gvkey")
    path_b["method"] = "B_execlink_ccm"
    say(f"Path B (exec_boardex->gvkey->permno): {ex['boardid'].nunique():,} boardids "
        f"w/ gvkey, {path_b['boardid'].nunique():,} w/ permno")

    # --- path C: US ISIN -> cusip8 -> stocknames --------------------------
    sn = pd.read_parquet(DATA / "crsp_stocknames_full.parquet")
    sn["namedt"] = pd.to_datetime(sn["namedt"])
    sn["nameenddt"] = pd.to_datetime(sn["nameenddt"]).fillna(pd.Timestamp("2262-01-01"))
    c = prof.dropna(subset=["isin"]).copy()
    c = c[c["isin"].astype(str).str.upper().str.startswith("US")]
    c["cusip8"] = c["isin"].astype(str).str.upper().str[2:10]
    path_c = c.merge(
        sn[["permno", "ncusip", "namedt", "nameenddt"]].dropna(subset=["ncusip"]),
        left_on="cusip8", right_on="ncusip",
    )
    path_c = path_c.rename(columns={"namedt": "linkdt", "nameenddt": "linkenddt"})
    path_c["gvkey"] = pd.NA
    path_c["method"] = "C_isin_cusip"
    path_c["permno"] = path_c["permno"].astype("int64")
    say(f"Path C (isin->cusip->permno): {c['boardid'].nunique():,} US-isin boardids, "
        f"{path_c['boardid'].nunique():,} matched")

    # --- combine, priority A > B > C on duplicate (boardid, permno) -------
    cols = ["boardid", "permno", "gvkey", "linkdt", "linkenddt", "method"]
    link = pd.concat([path_a[cols], path_b[cols], path_c[cols]], ignore_index=True)
    link["prio"] = link["method"].map({"A_cik_ccm": 1, "B_execlink_ccm": 2,
                                       "C_isin_cusip": 3})
    link = (link.sort_values("prio")
                .drop_duplicates(["boardid", "permno", "linkdt"])
                .drop(columns="prio"))
    say(f"Combined link: {len(link):,} rows, {link['boardid'].nunique():,} boardids, "
        f"{link['permno'].nunique():,} permnos")
    say("  by method: " + ", ".join(
        f"{m} {n:,}" for m, n in link.groupby('method')['boardid'].nunique().items()))
    link.to_parquet(LINK_OUT, index=False)
    say(f"wrote {LINK_OUT.name}")

    # --- market-cap coverage via duckdb over fresh msf --------------------
    say("")
    say("CRSP market-cap coverage (common stock shrcd 10/11, exchcd 1/2/3):")
    con = duckdb.connect()
    msf = str(DATA / "crsp_msf_full.parquet").replace("'", "''")
    nm = str(DATA / "crsp_msenames_full.parquet").replace("'", "''")
    con.execute(f"""
        create temp table lk as select distinct permno, linkdt, linkenddt
        from link where permno is not null
    """)
    failures = 0
    for d in SAMPLE_DATES:
        row = con.execute(f"""
            with univ as (
                select m.permno, abs(m.prc) * m.shrout as mcap
                from read_parquet('{msf}') m
                join read_parquet('{nm}') n
                  on m.permno = n.permno
                 and cast(m.date as date)
                     between cast(n.namedt as date)
                         and coalesce(cast(n.nameendt as date), date '2262-01-01')
                where date_trunc('month', cast(m.date as date))
                      = date_trunc('month', date '{d}')
                  and n.shrcd in (10, 11) and n.exchcd in (1, 2, 3)
                  and m.prc is not null and m.shrout is not null
            )
            select
                count(*) as n_stocks,
                sum(mcap) as total_mcap,
                sum(case when l.permno is not null then mcap else 0 end) as linked_mcap,
                count(distinct l.permno) as n_linked
            from univ u
            left join lk l
              on u.permno = l.permno
             and date '{d}' between l.linkdt and l.linkenddt
        """).fetchone()
        n_stocks, total, linked, n_linked = row
        cov = (linked or 0) / total if total else 0.0
        binds = d >= GATE_BINDS_FROM
        verdict = ("FAIL" if cov < KILL_THRESHOLD else "ok") if binds else "info"
        if binds and cov < KILL_THRESHOLD:
            failures += 1
        say(f"  {d}: {cov:6.1%} of mcap linked "
            f"({n_linked:,}/{n_stocks:,} names) [{verdict}]")

    # --- PIT hygiene facts -------------------------------------------------
    say("")
    say("PIT hygiene (org_composition role dates):")
    oc = str(DATA / "boardex_na_wrds_org_composition.parquet").replace("'", "''")
    for col in ("datestartroleflag", "dateendroleflag"):
        dist = con.execute(
            f"select {col}, count(*) n from read_parquet('{oc}') group by 1 order by 2 desc"
        ).fetchdf()
        say(f"  {col}: " + ", ".join(
            f"{r[col]}={r['n']:,}" for _, r in dist.head(6).iterrows()))
    (n_curr,) = con.execute(f"""
        select count(*) from read_parquet('{oc}')
        where cast(datestartrole as varchar) = 'Curr'
           or cast(dateendrole as varchar) = 'Curr'
    """).fetchone()
    say(f"  literal 'Curr' strings in role dates: {n_curr} "
        f"{'OK (must stay 0)' if n_curr == 0 else 'FAIL'}")
    if n_curr:
        failures += 1
    sent = con.execute(f"""
        select
          sum(case when cast(dateendrole as date) >= date '9000-01-01'
                   then 1 else 0 end) as cur_sentinel,
          sum(case when cast(datestartrole as date) <= date '1900-01-01'
                   then 1 else 0 end) as floor_sentinel,
          count(*) as n
        from read_parquet('{oc}')
    """).fetchone()
    say(f"  sentinel dates: {sent[0]:,} end>=9000-01-01 (current roles), "
        f"{sent[1]:,} start<=1900-01-01 (imputed floor), of {sent[2]:,} rows — "
        f"consumers MUST treat these via the flag columns, never as real dates")

    say("=" * 70)
    verdict = "GATE D2: PASS" if failures == 0 else f"GATE D2: FAIL ({failures})"
    say(verdict)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    say(f"report written to {REPORT}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
