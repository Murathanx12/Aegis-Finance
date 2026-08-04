"""Gate D3 — known-answer replication (AEGIS_EXECUTION_ROADMAP.md).

The anti-restart test: before any NOVEL signal touches this stack, the stack
must reproduce three results that are already known to be true. If any fails,
the pipeline is broken TODAY at a cost of days — not after three months of
signal work.

Pre-registered expectations (tolerances fixed before running):

D3a  Gross profitability (Novy-Marx 2013 / OSAP "GP"):
     GP = (revt - cogs) / at, fiscal year ending in calendar year t-1,
     portfolios formed end-June year t, held July t .. June t+1,
     value-weighted deciles, NYSE/AMEX/NASDAQ common stock (shrcd 10/11).
     PASS if over 1963-07..2024-12: (i) D10-D1 spread POSITIVE,
     (ii) mean monthly VW spread in [0.15%, 0.66%] (published ~0.31%/mo +-50%
     with margin for sample), (iii) decile means broadly monotone
     (Spearman rho of decile rank vs mean return >= 0.6).

D3b  Delisting bias (Shumway 1997):
     Bottom-NYSE-size-decile equal-weighted portfolio computed WITH vs
     WITHOUT delisting returns merged from dsedelist.
     PASS if ignoring delistings OVERSTATES the small-cap EW annualized
     return by >= 0.3%/yr over 1963-2024 (documented direction; magnitude
     varies by period and universe — the gate is the sign plus materiality).

D3c  BoardEx descriptive fact:
     Mean board size (directors with unexpired supervisory-board roles per
     linked company per year) for CRSP-linked US companies, 2010-2020.
     Published US figures cluster at 8-11 (Spencer Stuart ~10.8 for S&P 500;
     all-public means lower). PASS if mean in [6, 13] and median in [5, 13]
     — a truncated or mis-linked graph produces means far outside this.

Any FAIL -> stop, fix the pipeline, re-run. Nothing downstream may run first.

Inputs: fresh phase-2 pulls (comp_funda_full, crsp_msf_full, crsp_msenames_full,
crsp_ccmxpf_lnkhist_full, crsp_dsedelist_full) + link_boardid_permno.parquet
(Gate D2 output) + boardex_na_wrds_org_composition.

Usage: .venv/Scripts/python.exe scripts/gate_d3_replication.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

DATA = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\full")
REPORT = DATA / "GATE_D3_REPORT.txt"

lines: list[str] = []


def say(msg: str) -> None:
    print(msg)
    lines.append(msg)


def p(name: str) -> str:
    return str(DATA / name).replace("'", "''")


def build_monthly_universe(con: duckdb.DuckDBPyConnection) -> None:
    """Monthly CRSP common-stock rows with PIT share/exchange codes + mcap."""
    # mcap_lag (prior month-end cap) is the ONLY valid ranking/weighting
    # variable: month-t cap already contains month-t's return, and using it
    # contemporaneously is a look-ahead that this gate itself caught on its
    # first run (decile-1 GP at 2.24%/mo VW, small-cap EW at -22%/yr).
    con.execute(f"""
        create temp table crsp_m as
        select *, lag(mcap) over (partition by permno order by month) as mcap_lag
        from (
            select m.permno, cast(m.date as date) as date,
                   date_trunc('month', cast(m.date as date)) as month,
                   m.ret, abs(m.prc) * m.shrout as mcap, n.exchcd
            from read_parquet('{p("crsp_msf_full.parquet")}') m
            join read_parquet('{p("crsp_msenames_full.parquet")}') n
              on m.permno = n.permno
             and cast(m.date as date)
                 between cast(n.namedt as date)
                     and coalesce(cast(n.nameendt as date), date '2262-01-01')
            where n.shrcd in (10, 11) and n.exchcd in (1, 2, 3)
        )
    """)


def d3a_gross_profitability(con: duckdb.DuckDBPyConnection) -> int:
    say("")
    say("D3a — Novy-Marx gross profitability decile replication")
    con.execute(f"""
        create temp table gp as
        select f.gvkey, cast(f.datadate as date) as datadate,
               (f.revt - f.cogs) / nullif(f.at, 0) as gp,
               year(cast(f.datadate as date)) as fy_cal
        from read_parquet('{p("comp_funda_full.parquet")}') f
        where f.at > 0 and f.revt is not null and f.cogs is not null
    """)
    # fiscal year ending in cal year t-1 -> formation June t, held Jul t..Jun t+1
    con.execute(f"""
        create temp table gp_permno as
        select g.*, l.lpermno as permno
        from gp g
        join read_parquet('{p("crsp_ccmxpf_lnkhist_full.parquet")}') l
          on g.gvkey = l.gvkey
         and l.linktype in ('LU', 'LC') and l.linkprim in ('P', 'C')
         and g.datadate between cast(l.linkdt as date)
                            and coalesce(cast(l.linkenddt as date), date '2262-01-01')
    """)
    rets = con.execute("""
        with formation as (
            select permno, fy_cal + 1 as form_year, gp,
                   row_number() over (partition by permno, fy_cal order by datadate desc) rn
            from gp_permno
        ),
        deciles as (
            select permno, form_year, ntile(10) over (partition by form_year order by gp) as d
            from formation where rn = 1 and gp is not null
        ),
        held as (
            select c.month, c.ret, c.mcap_lag, d.d
            from crsp_m c
            join deciles d
              on c.permno = d.permno
             and c.month between make_date(d.form_year, 7, 1)
                             and make_date(d.form_year + 1, 6, 1)
            where c.ret is not null and c.mcap_lag is not null
              and c.month >= date '1963-07-01'
        )
        select month, d, sum(ret * mcap_lag) / sum(mcap_lag) as vw_ret
        from held group by month, d order by month, d
    """).fetchdf()
    piv = rets.pivot(index="month", columns="d", values="vw_ret").dropna()
    means = piv.mean() * 100
    spread = (piv[10] - piv[1]).mean() * 100
    rho = spearmanr(np.arange(1, 11), means.reindex(range(1, 11)).values).statistic
    say(f"  months: {len(piv)}, decile mean VW ret %/mo: "
        + " ".join(f"{means[d]:.2f}" for d in range(1, 11)))
    say(f"  D10-D1 spread: {spread:.3f}%/mo, monotonicity rho: {rho:.2f}")
    ok = (spread > 0) and (0.15 <= spread <= 0.66) and (rho >= 0.6)
    say(f"  D3a: {'PASS' if ok else 'FAIL'} "
        f"(need spread in [0.15, 0.66]%/mo, positive, rho>=0.6)")
    return 0 if ok else 1


def d3b_delisting_bias(con: duckdb.DuckDBPyConnection) -> int:
    say("")
    say("D3b — Shumway delisting-bias replication (bottom size decile, EW)")
    # The bias lives in stocks whose FINAL month has no msf return — the
    # delisting return is their only month-t observation. So: form the holding
    # set at t-1, LEFT-join month-t returns and delist events, and let dlret
    # stand in when ret is missing. Missing dlret on performance delistings
    # (codes 500, 520-584) gets Shumway's standard -35% imputation.
    con.execute(f"""
        create temp table dl as
        select permno, date_trunc('month', cast(dlstdt as date)) as month,
               coalesce(dlret,
                        case when dlstcd = 500 or dlstcd between 520 and 584
                             then -0.35 end) as dlret
        from read_parquet('{p("crsp_dsedelist_full.parquet")}')
        where dlstcd >= 200
    """)
    df = con.execute("""
        with hold as (
            select month + interval 1 month as hmonth, permno
            from (
                select month, permno,
                       ntile(10) over (partition by month order by mcap) as size_d
                from crsp_m
                where mcap is not null and month >= date '1962-12-01'
            )
            where size_d = 1
        ),
        small as (
            select h.hmonth, h.permno, r.ret,
                   case
                     when r.ret is not null and d.dlret is not null
                       then (1 + r.ret) * (1 + d.dlret) - 1
                     when r.ret is not null then r.ret
                     else d.dlret
                   end as ret_dl
            from hold h
            left join crsp_m r on r.permno = h.permno and r.month = h.hmonth
            left join dl d on d.permno = h.permno and d.month = h.hmonth
        )
        select hmonth as month,
               avg(ret) as ew_no_dl,
               avg(ret_dl) as ew_with_dl
        from small
        group by hmonth order by hmonth
    """).fetchdf()
    ann_no = (1 + df["ew_no_dl"].mean()) ** 12 - 1
    ann_with = (1 + df["ew_with_dl"].mean()) ** 12 - 1
    gap = (ann_no - ann_with) * 100
    say(f"  months: {len(df)}; EW bottom-decile annualized: "
        f"{ann_no:.2%} without dlret vs {ann_with:.2%} with dlret")
    say(f"  overstatement from ignoring delistings: {gap:.2f}%/yr")
    ok = gap >= 0.3
    say(f"  D3b: {'PASS' if ok else 'FAIL'} (need >= 0.30%/yr overstatement)")
    return 0 if ok else 1


def d3c_board_size(con: duckdb.DuckDBPyConnection) -> int:
    say("")
    say("D3c — BoardEx descriptive: mean board size, CRSP-linked firms 2010-2020")
    df = con.execute(f"""
        with seats as (
            select o.companyid, o.directorid,
                   cast(o.datestartrole as date) as datestartrole,
                   cast(o.dateendrole as date) as dateendrole
            from read_parquet('{p("boardex_na_wrds_org_composition.parquet")}') o
            where lower(o.rolename) like '%director%'
              and o.datestartrole is not null
              and cast(o.datestartrole as date) > date '1900-01-01'
        ),
        linked as (
            select distinct s.companyid, s.directorid, s.datestartrole, s.dateendrole
            from seats s
            join read_parquet('{p("link_boardid_permno.parquet")}') l
              on s.companyid = l.boardid
        ),
        yearly as (
            select y.yr, companyid, count(distinct directorid) as bsize
            from linked, (select unnest(range(2010, 2021)) as yr) y
            where datestartrole <= make_date(y.yr, 12, 31)
              and coalesce(dateendrole, date '9999-12-31') >= make_date(y.yr, 12, 31)
            group by y.yr, companyid
        )
        select avg(bsize) as mean_size,
               median(bsize) as med_size,
               count(*) as firm_years
        from yearly where bsize between 1 and 60
    """).fetchdf()
    mean_s, med_s, n = df.iloc[0]
    say(f"  firm-years: {int(n):,}; mean board size {mean_s:.1f}, median {med_s:.0f}")
    ok = (6 <= mean_s <= 13) and (5 <= med_s <= 13)
    say(f"  D3c: {'PASS' if ok else 'FAIL'} (need mean in [6,13], median in [5,13])")
    return 0 if ok else 1


def main() -> int:
    say("GATE D3 — known-answer replication")
    say("=" * 70)
    con = duckdb.connect()
    build_monthly_universe(con)
    failures = d3a_gross_profitability(con)
    failures += d3b_delisting_bias(con)
    failures += d3c_board_size(con)
    say("=" * 70)
    say("GATE D3: PASS" if failures == 0 else f"GATE D3: FAIL ({failures})")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    say(f"report written to {REPORT}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
