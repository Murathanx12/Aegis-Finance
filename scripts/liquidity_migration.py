"""DOES A STOCK CLIMBING THE LIQUIDITY LADDER PREDICT ANYTHING? (Murat's hypothesis)

THE INTUITION, IN HIS WORDS
===========================
    "seeing how these bands are changing per stock might be a great showcase of
     growth and potential too. seeing how bid and ask change is also"

A name that traded $500k/day last year and trades $5m/day now is being
DISCOVERED: more people are looking, more capital can enter, and the spread it
must pay is collapsing. The claim is that this migration is visible before the
re-rating finishes.

Intuition GENERATES, data ADJUDICATES. So this asks the one question that
separates it from ordinary momentum:

    Does climbing a liquidity band predict forward return AFTER controlling
    for the 12-month return that usually comes with it?

If a migrating name is just a name that went up, this is momentum wearing a new
label and it should be said so. The control is the whole test.

WHAT IS MEASURED
================
Per name-month over 2013-2024 (CRSP daily, monthly aggregated):

  * `mdv`        median dollar volume over the month
  * `band`       0..4 on the ladder used by the TAQ spread study, so the cost
                 of each rung is already known:
                 100k-1m (149 bps) / 1m-5m (39) / 5m-10m (21) /
                 10m-50m (20) / 50m+ (7)
  * `climb_12m`  bands climbed since 12 months ago
  * forward 3 / 6 / 12-month returns, delist-inclusive

Then the cross-section is cut by `climb_12m` AND by trailing 12-month return
quintile, so a climber is compared against a non-climber THAT WENT UP JUST AS
MUCH. A raw climber-vs-everything table would confirm the hypothesis by
construction.

WHY IT MATTERS BEYOND THE SIGNAL
================================
Migration is also a COST forecast. The TAQ study priced each rung; a name
climbing from band 0 to band 2 sees its round-trip cost fall from ~149 bps to
~21. A strategy that cannot afford a name today may afford it in a year, and
that is a different statement from "the edge is not buyable".

NOT a claim of alpha. This is a PRODUCT_EXPERIMENT-grade cross-sectional look
with an explicit control; costs are stated per band and not netted, because the
holding period is exactly what the follow-up has to decide.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "data" / "optimus" / "wrds"
HOST, PORT, DB, USER = "wrds-pgdata.wharton.upenn.edu", 9737, "wrds", "murathan12"

START, END = "2013-01-01", "2024-12-31"

#: Same ladder as the TAQ spread study, so each rung's cost is already measured.
BAND_EDGES = (1e5, 1e6, 5e6, 1e7, 5e7)
BAND_NAMES = ("<100k", "100k-1m", "1m-5m", "5m-10m", "10m-50m", "50m+")
#: Measured round-trip cost per band, bps (taq_spread_by_liquidity_band.json).
BAND_COST_BPS = {"100k-1m": 148.9, "1m-5m": 38.7, "5m-10m": 21.0,
                 "10m-50m": 20.2, "50m+": 6.7}

MONTHLY_SQL = f"""
SELECT d.permno,
       DATE_TRUNC('month', d.date)::date                                   AS ym,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.prc) * d.vol)     AS mdv,
       EXP(SUM(LN(1 + COALESCE(d.ret, 0)))) - 1                            AS mret,
       COUNT(*)                                                            AS ndays
FROM crsp.dsf d
JOIN crsp.dsenames n
  ON n.permno = d.permno AND d.date BETWEEN n.namedt AND n.nameendt
WHERE d.date BETWEEN '{START}' AND '{END}'
  AND n.shrcd IN (10, 11) AND n.exchcd IN (1, 2, 3)
  AND d.prc IS NOT NULL AND d.vol IS NOT NULL AND ABS(d.prc) >= 1.0
  AND d.ret IS NOT NULL AND d.ret > -1
GROUP BY d.permno, DATE_TRUNC('month', d.date)
HAVING COUNT(*) >= 15
"""


def band_of(mdv: float) -> int:
    b = 0
    for e in BAND_EDGES:
        if mdv >= e:
            b += 1
    return min(b, len(BAND_NAMES) - 1)


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

    # CACHE THE PANEL. The pull is 520k name-months and several minutes, and it
    # is the same panel every downstream study needs (CompanyState, the `fell`
    # cut, revision velocity). Re-querying WRDS to re-slice numbers we already
    # have is paying twice for a value that does not change.
    cache = OUT / f"crsp_monthly_panel_{START[:4]}_{END[:4]}.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        print(f"  panel from cache: {len(raw):,} name-months ({cache.name})", flush=True)
    else:
        conn = psycopg2.connect(host=HOST, port=PORT, dbname=DB, user=USER,
                                sslmode="require", connect_timeout=25)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 1800000")
        print(f"pulling crsp.dsf monthly {START}..{END} ...", flush=True)
        cur.execute(MONTHLY_SQL)
        raw = [[int(r[0]), str(r[1]), float(r[2]), float(r[3]), int(r[4])]
               for r in cur.fetchall()]
        conn.close()
        OUT.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw), encoding="utf-8")
        print(f"  {len(raw):,} name-months -> cached {cache.name}", flush=True)

    # permno -> ordered list of (ym, mdv, mret)
    by: dict[int, list] = defaultdict(list)
    for permno, ym, mdv, mret, _n in raw:
        by[int(permno)].append((str(ym), float(mdv), float(mret)))
    for v in by.values():
        v.sort(key=lambda r: r[0])

    rows = []
    for permno, series in by.items():
        if len(series) < 25:
            continue
        bands = [band_of(m[1]) for m in series]
        rets = [m[2] for m in series]
        for i in range(12, len(series) - 12):
            climb = bands[i] - bands[i - 12]
            # trailing 12m return: the control. A climber is usually a name that
            # went up, and without this the table confirms itself.
            tr12 = 1.0
            for r in rets[i - 12:i]:
                tr12 *= (1 + r)
            fwd = {}
            for h in (3, 6, 12):
                f = 1.0
                for r in rets[i:i + h]:
                    f *= (1 + r)
                fwd[h] = f - 1.0
            rows.append({"permno": permno, "ym": series[i][0], "band": bands[i],
                         "climb_12m": climb, "trail_12m": tr12 - 1.0,
                         "mdv": series[i][1], **{f"fwd_{h}m": fwd[h] for h in (3, 6, 12)}})

    print(f"  {len(rows):,} usable observations", flush=True)

    # Trailing-return quintiles, computed WITHIN each month so the control is a
    # cross-sectional peer, not a name from a different market.
    per_month: dict[str, list] = defaultdict(list)
    for r in rows:
        per_month[r["ym"]].append(r)
    for ym, group in per_month.items():
        group.sort(key=lambda r: r["trail_12m"])
        n = len(group)
        for j, r in enumerate(group):
            r["trail_q"] = min(4, int(5 * j / max(1, n)))

    def agg(sel, key):
        v = [r[key] for r in sel]
        if len(v) < 30:
            return None
        n = len(v)
        # THE TAIL, not just the centre. The first run found climbers at a
        # +12.62% MEAN against a +1.16% MEDIAN while flat names ran +13.03% /
        # +5.45%: most climbers go nowhere and a few go a long way. "Growth and
        # potential" is a claim about that tail, and a mean cannot express it.
        return {"n": n, "mean": round(100 * st.mean(v), 2),
                "median": round(100 * st.median(v), 2),
                "p_up_50pct": round(100 * sum(1 for x in v if x > 0.50) / n, 2),
                "p_up_100pct": round(100 * sum(1 for x in v if x > 1.00) / n, 2),
                "p_dn_50pct": round(100 * sum(1 for x in v if x < -0.50) / n, 2),
                "p90": round(100 * sorted(v)[int(0.90 * n)], 2)}

    climbed2 = [r for r in rows if r["climb_12m"] >= 2]
    climbed = [r for r in rows if r["climb_12m"] >= 1]
    flat = [r for r in rows if r["climb_12m"] == 0]
    fell = [r for r in rows if r["climb_12m"] <= -1]

    headline = {"climbed>=2_bands": agg(climbed2, "fwd_12m"),
                "climbed>=1_band": agg(climbed, "fwd_12m"),
                "flat": agg(flat, "fwd_12m"),
                "fell>=1_band": agg(fell, "fwd_12m")}

    # THE TEST THAT MATTERS: inside each trailing-return quintile.
    controlled = {}
    for q in range(5):
        c = [r for r in climbed if r["trail_q"] == q]
        f = [r for r in flat if r["trail_q"] == q]
        # FELL gets the same control. The uncontrolled table showed fallers with
        # the HIGHEST mean of the four groups and tails as fat as the climbers',
        # which is the observation that turned this from a direction signal into
        # a dispersion one. Leaving it uncontrolled would leave the claim
        # resting on the one cut that was not tested.
        d = [r for r in fell if r["trail_q"] == q]
        ac, af, ad = agg(c, "fwd_12m"), agg(f, "fwd_12m"), agg(d, "fwd_12m")
        controlled[f"trail_q{q}"] = {
            "climbed": ac, "flat": af, "fell": ad,
            "spread_pp": (round(ac["mean"] - af["mean"], 2) if ac and af else None),
            "fell_spread_pp": (round(ad["mean"] - af["mean"], 2) if ad and af else None)}

    payload = {
        "receipt": "LIQUIDITY-MIGRATION-1",
        "at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": ("a name climbing the dollar-volume ladder is being "
                       "discovered, and that is visible before the re-rating ends"),
        "control": ("trailing 12-month return quintile, computed WITHIN each "
                    "month. Without it a climber is just a name that went up and "
                    "the table confirms itself."),
        "window": [START, END], "band_names": list(BAND_NAMES),
        "band_round_trip_cost_bps": BAND_COST_BPS,
        "n_name_months": len(rows),
        "headline_uncontrolled": headline,
        "controlled_by_trailing_return_quintile": controlled,
        "caveat": ("returns are GROSS. Each band's measured round-trip cost is "
                   "carried above so a migration strategy is costed at the rung "
                   "it actually trades, not at a flat assumption."),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "liquidity_migration.json"
    dst.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\n" + "=" * 74)
    print("FORWARD 12-MONTH RETURN BY LIQUIDITY-BAND MIGRATION (gross, 2013-2024)")
    print("=" * 74)
    print(f"  {'group':<18} {'n':>8} {'mean':>8} {'median':>8} {'>+50%':>7} {'>+100%':>7} {'<-50%':>7} {'p90':>8}")
    for k, v in headline.items():
        if v:
            print(f"  {k:<18} {v['n']:>8,} {v['mean']:+7.2f}% {v['median']:+7.2f}% "
                  f"{v['p_up_50pct']:>6.1f}% {v['p_up_100pct']:>6.1f}% "
                  f"{v['p_dn_50pct']:>6.1f}% {v['p90']:+7.1f}%")
    print("\n  CONTROLLED for trailing 12m return (the whole test):")
    print(f"  {'quintile':<10} {'climbed':>13} {'flat':>13} {'fell':>13} "
          f"{'climb-flat':>11} {'fell-flat':>10}   {'>+100%: cl/fl/fe':>18}")
    for q in range(5):
        c = controlled[f"trail_q{q}"]
        cc, ff, dd = c["climbed"], c["flat"], c["fell"]
        f_ = lambda x: f"{x['mean']:+6.2f}%" if x else "   --"
        sp = lambda v: f"{v:+6.2f}pp" if v is not None else "    --"
        tails = (f"{cc['p_up_100pct']:.1f}/{ff['p_up_100pct']:.1f}/{dd['p_up_100pct']:.1f}%"
                 if cc and ff and dd else "--")
        print(f"  q{q} {'(worst)' if q == 0 else '(best)' if q == 4 else '':<7} "
              f"{f_(cc):>13} {f_(ff):>13} {f_(dd):>13} "
              f"{sp(c['spread_pp']):>11} {sp(c['fell_spread_pp']):>10}   {tails:>18}")
    print(f"\nreceipt -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
