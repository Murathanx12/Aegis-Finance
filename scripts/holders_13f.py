"""WHAT ARE THE BIG HOLDERS DOING -- and is it worth anything after the corpse?

THE HYPOTHESIS, IN MURAT'S WORDS
===============================
    "maybe the biggest holder sell or want more might be good indicator.
     estimating what firms and hedge funds will do will show that too"

Two things have to be separated for this to be a question at all:

  * the LEVEL of institutional ownership -- how many funds hold it, how much of
    the float they hold. This is the **13F-popularity corpse**: a known
    non-signal, and the mandatory control (TIER 0). Without it, "institutions
    own a lot of it" gets credited for being a large, liquid, well-covered
    company.
  * the CHANGE -- who is adding, who is leaving, and what the LARGEST holder
    did. That is what the hypothesis is actually about, and it is a different
    variable.

THE POINT-IN-TIME TRAP THAT COMES FIRST
=======================================
`tr_13f.s34` has both `rdate` (quarter end) and `fdate`, and `fdate` looks like
the file date. It is not. MEASURED over 24 quarters:

    fdate - rdate:  median 0 days, min 0, max 0

`fdate` EQUALS `rdate` in this table. Using it as the knowability bound would
assume a quarter's holdings were public on the last day of the quarter -- **45
days before they actually were** -- which is look-ahead of the most ordinary
kind and would manufacture an edge out of nothing.

So the bound here is `rdate + 45 calendar days`, the SEC deadline. That is still
OPTIMISTIC: a manager may file on the deadline, and many do, so the true
knowability date is at or after this. Being optimistic in a stated direction is
acceptable; being optimistic by 45 days without noticing is not.

WHAT THIS IS NOT
================
13F is quarterly, longs-only, and 45 days stale by construction. It cannot be a
catalyst. It can only be STRUCTURE: who owns this, how crowded is it, who is
leaving. Any result here is a slow conditioning variable, never a trigger.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "data" / "optimus" / "wrds"
HOST, PORT, DB, USER = "wrds-pgdata.wharton.upenn.edu", 9737, "wrds", "murathan12"

START = "2013-01-01"
#: The SEC deadline. `fdate` is unusable (see the docstring), so this is the
#: knowability bound, and it is optimistic rather than conservative.
FILING_LAG_DAYS = 45

#: Aggregated server-side: s34 is 72.7m rows since 2013 and the per-name
#: quarterly summary is ~200k.
HOLDINGS_SQL = f"""
SELECT rdate,
       SUBSTRING(cusip FROM 1 FOR 8)              AS cusip8,
       SUM(shares)                                AS inst_shares,
       COUNT(DISTINCT mgrno)                      AS n_managers,
       MAX(shares)                                AS top_shares
FROM tr_13f.s34
WHERE rdate >= '{START}' AND shares > 0
GROUP BY rdate, SUBSTRING(cusip FROM 1 FOR 8)
HAVING COUNT(DISTINCT mgrno) >= 3
"""

#: permno <-> ncusip, so the holdings join the cached CRSP monthly panel.
LINK_SQL = f"""
SELECT DISTINCT permno, ncusip
FROM crsp.dsenames
WHERE ncusip IS NOT NULL AND namedt <= '2025-12-31' AND nameendt >= '{START}'
"""


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                           # noqa: BLE001
            pass
    os.environ.setdefault("PGPASSFILE",
                          os.path.expandvars(r"%APPDATA%\postgresql\pgpass.conf"))
    import statistics as st
    from collections import defaultdict

    import psycopg2

    panel_path = OUT / "crsp_monthly_panel_2013_2024.json"
    if not panel_path.exists():
        print("REFUSED: the CRSP monthly panel cache is missing. Run "
              "`python -m scripts.liquidity_migration` first.")
        return 1
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    by_permno: dict[int, list] = defaultdict(list)
    for permno, ym, _mdv, mret, _n in panel:
        by_permno[int(permno)].append((str(ym)[:7], float(mret)))
    for v in by_permno.values():
        v.sort()
    print(f"panel: {len(panel):,} name-months, {len(by_permno):,} names", flush=True)

    cache = OUT / "tr13f_quarterly.json"
    if cache.exists():
        rows = json.loads(cache.read_text(encoding="utf-8"))
        print(f"holdings from cache: {len(rows):,} rows", flush=True)
        link = json.loads((OUT / "tr13f_permno_link.json").read_text(encoding="utf-8"))
    else:
        conn = psycopg2.connect(host=HOST, port=PORT, dbname=DB, user=USER,
                                sslmode="require", connect_timeout=25)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 1800000")
        print("aggregating tr_13f.s34 (72.7m rows -> per name-quarter) ...", flush=True)
        cur.execute(HOLDINGS_SQL)
        rows = [[str(r[0]), str(r[1]), float(r[2]), int(r[3]), float(r[4])]
                for r in cur.fetchall()]
        print(f"  {len(rows):,} name-quarters", flush=True)
        cur.execute(LINK_SQL)
        link = {str(c).strip(): int(p) for p, c in cur.fetchall() if c}
        conn.close()
        OUT.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows), encoding="utf-8")
        (OUT / "tr13f_permno_link.json").write_text(json.dumps(link), encoding="utf-8")
        print(f"  link map: {len(link):,} cusip8 -> permno", flush=True)

    # cusip8 -> quarterly series
    series: dict[str, list] = defaultdict(list)
    for rdate, cusip8, inst, nmgr, top in rows:
        series[cusip8].append((rdate, inst, nmgr, top))
    for v in series.values():
        v.sort()

    def fwd(permno: int, start_ym: str, months: int) -> float | None:
        ms = by_permno.get(permno)
        if not ms:
            return None
        idx = [i for i, (ym, _r) in enumerate(ms) if ym >= start_ym]
        if not idx:
            return None
        i = idx[0]
        if i + months > len(ms):
            return None
        f = 1.0
        for _ym, r in ms[i:i + months]:
            f *= (1 + r)
        return f - 1.0

    obs = []
    for cusip8, ser in series.items():
        permno = link.get(cusip8)
        if permno is None:
            continue
        for k in range(1, len(ser)):
            rdate, inst, nmgr, top = ser[k]
            p_rdate, p_inst, p_nmgr, p_top = ser[k - 1]
            # consecutive quarters only; a gap is a different comparison
            d0 = datetime.fromisoformat(rdate).date()
            if (d0 - datetime.fromisoformat(p_rdate).date()).days > 100:
                continue
            if p_inst <= 0 or p_top <= 0:
                continue
            # THE PIT BOUND. rdate + 45 days, then the first month at or after
            # it -- never the quarter-end month, which is 45 days of hindsight.
            entry = (d0 + timedelta(days=FILING_LAG_DAYS)).isoformat()[:7]
            f12 = fwd(permno, entry, 12)
            if f12 is None:
                continue
            obs.append({
                "cusip8": cusip8, "permno": permno, "rdate": rdate, "entry_ym": entry,
                "n_managers": nmgr, "d_managers": nmgr - p_nmgr,
                "inst_shares": inst,
                "d_inst_pct": (inst - p_inst) / p_inst,
                "top_share_of_inst": top / inst if inst > 0 else None,
                "d_top_pct": (top - p_top) / p_top,
                "fwd_12m": f12,
            })

    print(f"  {len(obs):,} PIT-clean name-quarters with a 12m forward return", flush=True)

    # Quintiles of the CONTROL (ownership level) computed within each quarter,
    # so a name is compared against peers of the same popularity in the same
    # market -- the 13F-popularity corpse is held fixed, not assumed away.
    per_q: dict[str, list] = defaultdict(list)
    for o in obs:
        per_q[o["rdate"]].append(o)
    for _q, g in per_q.items():
        g.sort(key=lambda r: r["n_managers"])
        n = len(g)
        for j, r in enumerate(g):
            r["pop_q"] = min(4, int(5 * j / max(1, n)))

    def agg(sel):
        v = [r["fwd_12m"] for r in sel]
        if len(v) < 50:
            return None
        n = len(v)
        return {"n": n, "mean": round(100 * st.mean(v), 2),
                "median": round(100 * st.median(v), 2),
                "p_up_100pct": round(100 * sum(1 for x in v if x > 1.0) / n, 2)}

    def cut(key, lo, hi):
        return [o for o in obs if lo <= o[key] < hi]

    tables = {}
    for key, edges in (("d_top_pct", (-1e9, -0.20, -0.05, 0.05, 0.20, 1e9)),
                       ("d_inst_pct", (-1e9, -0.10, -0.02, 0.02, 0.10, 1e9)),
                       ("d_managers", (-1e9, -5, -1, 2, 6, 1e9))):
        tables[key] = {}
        for i in range(len(edges) - 1):
            lab = f"[{edges[i]:g},{edges[i+1]:g})"
            tables[key][lab] = agg(cut(key, edges[i], edges[i + 1]))

    # THE TEST: the largest holder's move, INSIDE each popularity quintile.
    controlled = {}
    for q in range(5):
        inq = [o for o in obs if o["pop_q"] == q]
        sell = [o for o in inq if o["d_top_pct"] < -0.20]
        hold = [o for o in inq if -0.05 <= o["d_top_pct"] < 0.05]
        buy = [o for o in inq if o["d_top_pct"] >= 0.20]
        a_s, a_h, a_b = agg(sell), agg(hold), agg(buy)
        controlled[f"pop_q{q}"] = {
            "top_holder_sold_20pct": a_s, "top_holder_flat": a_h,
            "top_holder_added_20pct": a_b,
            "buy_minus_sell_pp": (round(a_b["mean"] - a_s["mean"], 2)
                                  if a_b and a_s else None)}

    payload = {
        "receipt": "HOLDERS-13F-1",
        "at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "the largest holder adding or selling predicts forward return",
        "control": ("institutional POPULARITY quintile (manager count) within each "
                    "quarter -- the 13F-popularity corpse, held fixed rather than "
                    "assumed away"),
        "pit": {
            "trap": ("tr_13f.s34 `fdate` EQUALS `rdate`: measured median/min/max "
                     "lag of 0 days over 24 quarters. It is NOT the SEC filing "
                     "date and using it would grant 45 days of hindsight."),
            "bound_used": f"rdate + {FILING_LAG_DAYS} calendar days (the SEC deadline)",
            "still_optimistic": ("managers may file ON the deadline, so true "
                                 "knowability is at or after this date"),
        },
        "n_observations": len(obs),
        "univariate": tables,
        "controlled_by_popularity_quintile": controlled,
        "caveat": "quarterly, longs-only, 45 days stale: STRUCTURE, never a catalyst",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "holders_13f.json"
    dst.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\n" + "=" * 78)
    print("FORWARD 12-MONTH RETURN BY 13F CHANGE (PIT: rdate + 45d), 2013-2024")
    print("=" * 78)
    for key, tab in tables.items():
        print(f"\n  {key}:")
        for lab, v in tab.items():
            if v:
                print(f"    {lab:<16} n={v['n']:>7,}  mean {v['mean']:+7.2f}%  "
                      f"median {v['median']:+7.2f}%  >+100% {v['p_up_100pct']:>5.1f}%")
    print("\n  CONTROLLED for institutional popularity (the corpse held fixed):")
    print(f"  {'quintile':<12} {'top sold >20%':>15} {'top flat':>15} "
          f"{'top added >20%':>15} {'buy-sell':>10}")
    for q in range(5):
        c = controlled[f"pop_q{q}"]
        f_ = lambda x: f"{x['mean']:+6.2f}% ({x['n']:,})" if x else "--"
        d = c["buy_minus_sell_pp"]
        print(f"  q{q} {'(least)' if q == 0 else '(most)' if q == 4 else '':<8} "
              f"{f_(c['top_holder_sold_20pct']):>15} {f_(c['top_holder_flat']):>15} "
              f"{f_(c['top_holder_added_20pct']):>15} "
              f"{(f'{d:+6.2f}pp' if d is not None else '--'):>10}")
    print(f"\nreceipt -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
