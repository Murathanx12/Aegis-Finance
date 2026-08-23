"""G4 V1 — build real expectation records for the highest-sample event family.

    python -m scripts.g4_collect_earnings --probe
    python -m scripts.g4_collect_earnings --years 2015 2015
    python -m scripts.g4_collect_earnings --years 2006 2019

Quarterly EPS announcements: what was expected, what happened, when each became
knowable. Read-only, bounded, manifested. Touches no production path, no lane,
no NAV, no live registry, and deploys nothing.

WHY EARNINGS FIRST
==================
Ordered by "produce real records on the easiest high-sample family first". EPS
announcements win on every axis that matters here: thousands per year, a
consensus that is published BEFORE the event rather than reconstructed after it,
an actual that is unambiguous, and a timestamp to the minute on both.

THE PIT RULES, EACH ONE PAID FOR BY A KNOWN TRAP
================================================
1.  **Unadjusted files** (`statsumu_epsus`, `actu_epsus`), never the adjusted
    ones. IBES applies split adjustments RETROACTIVELY, so a consensus read
    from the adjusted file today is not the number that existed then. A 2-for-1
    split turns a $2.14 consensus into $1.07 across the whole history, and
    every surprise computed against a mixture of the two is wrong in a way that
    correlates with which companies split — that is, with past performance.

2.  **The consensus is the last snapshot STRICTLY BEFORE the announcement.**
    `statpers < anndats`, not `<=`. IBES stamps a snapshot with its cutoff date
    and a same-day snapshot can post-date a morning announcement.

3.  **Fiscal period matched explicitly** (`fpedats = pends`) rather than by
    `fpi` code. The fpi for a given quarter CHANGES as the calendar moves — the
    same fiscal period is '8' a year out and '6' a month out, visible in the
    data. Matching on the code would silently pick a different quarter.

4.  **`tradable_at` derives from the exchange calendar**, not from arithmetic on
    the announcement date. Most companies report outside market hours; 16:30 ET
    is not tradable until the next session. The calendar comes from `crsp.dsi`,
    which is the set of dates the market actually traded, rather than from a
    weekday rule that a holiday breaks.

5.  **The price reaction starts at `tradable_at`, and the run-up ends strictly
    before `first_public_ts`.** They must not share a day. If they do, the
    "run-up" contains the reaction and every model built on it looks prescient.

WHAT THIS DOES NOT DO
=====================
No semantic fields. `semantic_expected_state` and friends stay None with a
stated reason, because an LLM pass is a separate, sourced, PIT-blinded step and
mixing it into the collector would make the numeric layer's provenance
unauditable. The schema carries the columns so the later pass has somewhere to
land.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.services.g4_expectation import (ExpectationRecord, summarise,
                                             validate)
from scripts.wrds_pull_vsurfd_daily import _engine, _reachable, _sha256

OUT_DIR = Path(r"C:\Users\mrthn\Aegis module\data\g4\earnings_v1")
MANIFEST = OUT_DIR / "manifest.json"

#: Below this, `stdev` is a statistic about three opinions and the scaled
#: surprise is mostly noise about coverage. Declared here, recorded in the
#: manifest, and NOT tuned — it is a data-quality floor, not a parameter.
MIN_ESTIMATES = 10

#: Announcements at or after this local exchange time are not tradable until
#: the next session. IBES `anntims` is exchange time.
AFTER_HOURS_FROM = "16:00:00"

#: Regular-session open, exchange time.
SESSION_OPEN = "09:30:00"

#: Run-up window, trading days before the announcement. Fixed a priori; this is
#: a descriptive context field, not a signal, and it must not be chosen by
#: looking at which length separates winners.
RUNUP_DAYS = 20

SQL_EVENTS = """
select a.ticker, a.oftic, a.cname, a.cusip, a.pends, a.anndats, a.anntims,
       a.actdats, a.acttims, a.value as actual,
       s.statpers, s.fpedats, s.numest, s.numup, s.numdown,
       s.meanest, s.medest, s.stdev
from ibes.actu_epsus a
left join lateral (
    select statpers, fpedats, numest, numup, numdown, meanest, medest, stdev
    from ibes.statsumu_epsus s
    where s.ticker = a.ticker
      and s.measure = 'EPS' and s.fiscalp = 'QTR'
      and s.fpedats = a.pends
      and s.statpers < a.anndats        -- STRICTLY before. rule 2.
    order by s.statpers desc
    limit 1
) s on true
where a.measure = 'EPS' and a.pdicity = 'QTR' and a.usfirm = 1
  and a.anndats >= :start and a.anndats <= :end
  and a.value is not null
"""

#: ISSUER GUIDANCE IS NOT AVAILABLE TO US, and the way that was discovered is
#: worth recording. `ibes.det_guidance` appears in `information_schema.tables`
#: with a full column list — ticker, anndats, action, val_1, mean_at_date, all
#: exactly what `guidance_state` wants. Selecting from it returns
#:
#:     InsufficientPrivilege: permission denied for schema tr_ibes_guidance
#:
#: It is a view over a source our subscription does not include. **Appearing in
#: the catalogue is not the same as being entitled to it**, and a collector that
#: had assumed availability from the schema listing would have shipped a
#: guidance column that silently never populated.
#:
#: So `guidance_state` stays UNKNOWN with this as its stated reason, which is
#: the whole point of `unknown_reasons`: the next person reads why rather than
#: rediscovering it. If the subscription changes, this is the one place to look.
GUIDANCE_UNAVAILABLE = ("ibes.det_guidance is visible in the catalogue but "
                        "permission is denied on its source schema "
                        "tr_ibes_guidance — not entitled under this WRDS "
                        "subscription (checked 2026-08-16)")

#: The exchange calendar, derived rather than assumed (rule 4).
SQL_CALENDAR = "select distinct date from crsp.dsi where date >= :start and date <= :end order by 1"

#: IBES 8-char cusip -> CRSP permno, resolved PER EVENT DATE.
#:
#: The first version of this bound the link to one `asof` for the whole run,
#: which is wrong twice: it drops every company delisted before year-end, and
#: for the survivors it resolves the identifier at a date the event did not
#: happen on. Cusips are REUSED — that is the entire reason `stocknames` carries
#: validity intervals — so a link resolved at the wrong date silently attaches
#: another company's prices to an event, and the result looks like data.
#:
#: So the intervals come back whole and the resolution happens per announcement.
SQL_LINK = """
select ncusip, permno, namedt, nameenddt
from crsp.stocknames
where ncusip in :cusips
"""

#: `openprc` is what makes the reaction decomposable. CRSP's `ret` is
#: close-to-close, so for an after-hours announcement it CONTAINS the overnight
#: gap — a move nobody could trade on. Pulling the open lets the record carry
#: both halves and lets a later reader ask the implementable question.
SQL_PRICES = """
select permno, date, abs(prc) as prc, abs(openprc) as openprc, ret,
       vol, abs(bidlo) as bidlo, abs(askhi) as askhi
from crsp.dsf
where permno in :permnos and date >= :start and date <= :end
"""


def _iso(d, t=None) -> str | None:
    """Combine an IBES date and time into one UTC-naive-but-stamped instant.

    The times are EXCHANGE time. They are stamped UTC here without conversion,
    which is a deliberate, recorded simplification: every comparison this
    module makes is between two timestamps carrying the SAME convention, so the
    ordering guards are exact. It would become wrong the moment a non-US
    venue enters, which is why it is written down rather than assumed away.
    """
    if d is None:
        return None
    ds = str(d)[:10]
    ts = str(t)[:8] if t is not None else "00:00:00"
    return f"{ds}T{ts}+00:00"


def _revision_state(up, down) -> str:
    if up is None or down is None:
        return "UNKNOWN"
    up, down = float(up), float(down)
    if up == 0 and down == 0:
        return "FLAT"
    if up > 0 and down > 0:
        # Genuinely mixed. Collapsing this into UP because up>down would hide
        # disagreement, which is the thing the factory is looking for.
        return "MIXED" if abs(up - down) <= max(up, down) * 0.25 else (
            "UP" if up > down else "DOWN")
    return "UP" if up > down else "DOWN"


_REFUSAL_KINDS = (
    "is not strictly before", "precedes first_public_ts",
    "with no entry in `unknown_reasons`", "is required",
    "no disagreement to measure", "is not one of", "no `source_ids`",
)


def _refusal_kind(msg: str) -> str:
    """Group refusals by KIND, not by the values in them.

    The first version keyed on the message prefix, which contains a timestamp,
    so 57 instances of one bug reported as 57 distinct reasons each with count
    1 — a refusal report that hides the pattern is barely better than silence.
    """
    for k in _REFUSAL_KINDS:
        if k in msg:
            head = msg.split(" ")[0]
            return f"{head} ... {k}"
    return msg[:70]


def _link_key(cusip, anndats) -> str:
    return f"{cusip}|{str(anndats)[:10]}"


def _resolve_links(df, spans: dict) -> dict:
    """Resolve cusip -> permno separately for EVERY announcement.

    Keyed by (cusip, announcement date) rather than by cusip, because the same
    eight characters can belong to two companies inside one run. An ambiguous
    date — two spans covering it — resolves to nothing rather than to the first
    match: the whole purpose of the interval is to be unambiguous, so an
    overlap means the assumption failed and picking would hide it.
    """
    out: dict[str, int] = {}
    for row in df.itertuples(index=False):
        cu, day = str(row.cusip), str(row.anndats)[:10]
        hits = [p for (a, b, p) in spans.get(cu, []) if a <= day <= b]
        if len(set(hits)) == 1:
            out[_link_key(cu, day)] = hits[0]
    return out


def build_records(df, calendar: list[str], prices: dict) -> tuple[list, dict]:
    """Rows -> validated records. Refusals are counted and named, never dropped."""
    import pandas as pd

    cal = sorted(calendar)
    recs, refused, reasons = [], 0, {}

    def next_session(day: str) -> str | None:
        i = 0
        for i, d in enumerate(cal):                              # noqa: B007
            if d > day:
                return d
        return None

    n_unknown_time = 0
    for row in df.itertuples(index=False):
        ann_d = str(row.anndats)[:10]
        raw_t = row.anntims
        ann_t = str(raw_t)[:8] if raw_t is not None else ""
        # AN UNKNOWN TIME IS NOT MIDNIGHT. `str(x or "00:00:00")` turned a
        # missing stamp into 00:00, which reads as PRE-MARKET and made the
        # announcement tradable at that same session's open — a price that may
        # precede the information. 807 rows from 2006 carry exactly 00:00:00,
        # which is not a time anyone announces earnings at; it is the field's
        # placeholder. Unknown takes the NEXT session, at a cost of 0.13% of
        # rows losing one session of precision.
        time_unknown = (not ann_t) or ann_t in ("None", "NaT", "nan", "<NA>") \
            or ann_t == "00:00:00"
        if time_unknown:
            n_unknown_time += 1
        pub = _iso(row.anndats, row.anntims)
        obs = _iso(row.actdats, row.acttims)

        # rule 4 — tradable_at from the exchange calendar.
        #
        # THREE CASES, and the middle one was wrong in the first version: it
        # gave every intraday announcement a 09:30 tradable time, which is
        # BEFORE the announcement. `validate` refused 57 of them rather than
        # letting a negative reaction window through, which is the guard doing
        # the job — a same-session announcement is exactly the case where an
        # off-by-one buys you the move you are trying to predict.
        if time_unknown or ann_t >= AFTER_HOURS_FROM or ann_d not in cal:
            trd_day, trd_t = next_session(ann_d), SESSION_OPEN     # after hours
        elif ann_t <= SESSION_OPEN:
            trd_day, trd_t = ann_d, SESSION_OPEN                   # pre-market
        else:
            trd_day, trd_t = ann_d, ann_t                          # intraday
        trd = _iso(trd_day, trd_t) if trd_day else None

        unknown: dict[str, str] = {}
        exp = disp = nest = None
        if row.statpers is None:
            unknown["numeric_expectation"] = (
                "no IBES summary snapshot for this fiscal period dated "
                "strictly before the announcement")
            unknown["expectation_dispersion"] = unknown["numeric_expectation"]
            unknown["n_estimates"] = unknown["numeric_expectation"]
        else:
            exp = None if pd.isna(row.meanest) else float(row.meanest)
            disp = None if pd.isna(row.stdev) else float(row.stdev)
            nest = None if pd.isna(row.numest) else int(row.numest)
            if exp is None:
                unknown["numeric_expectation"] = "snapshot carries no meanest"
            if disp is None:
                unknown["expectation_dispersion"] = "snapshot carries no stdev"
            if nest is None:
                unknown["n_estimates"] = "snapshot carries no numest"

        # rule 5 — the two price windows may not share a day
        runup = react = tradable = gap = None
        pre: list = []
        permno = prices.get("link", {}).get(_link_key(row.cusip, ann_d))
        px = prices.get("by_permno", {}).get(permno) if permno else None
        if px is None:
            m = ("no CRSP permno for this cusip valid at the announcement date"
                 if permno is None else "no CRSP prices in the window")
            unknown["pre_event_price_runup"] = m
            unknown["market_reaction"] = m
            unknown["market_reaction_tradable"] = m
            unknown["overnight_gap"] = m
        else:
            pre = [b for b in px if b[0] < ann_d][-RUNUP_DAYS:]
            before = [b[1] for b in pre]
            after = [b for b in px if trd_day and b[0] >= trd_day][:1]
            if len(before) == RUNUP_DAYS:
                cum = 1.0
                for r in before:
                    cum *= (1.0 + r)
                runup = cum - 1.0
            else:
                unknown["pre_event_price_runup"] = (
                    f"only {len(before)} of {RUNUP_DAYS} pre-event trading days")
            if after:
                _d, _ret, _prc, _open = after[0][:4]
                react = float(_ret)
                # THE DECOMPOSITION.
                #   tradable = open -> close, same session, so no adjustment
                #              factor enters and a split cannot corrupt it.
                #   gap      = backed out of CRSP's OWN adjusted return rather
                #              than from raw prices, so distributions and
                #              splits are handled by the vendor that knows
                #              about them:  (1+ret) = (1+gap)(1+tradable).
                if _prc is not None and _open and _open > 0:
                    tradable = float(_prc) / float(_open) - 1.0
                    gap = (1.0 + react) / (1.0 + tradable) - 1.0
                else:
                    tradable = gap = None
                    unknown["market_reaction_tradable"] = (
                        "no CRSP open price on the first tradable session")
                    unknown["overnight_gap"] = unknown["market_reaction_tradable"]
            else:
                react = tradable = gap = None
                unknown["market_reaction"] = (
                    "no CRSP return on or after tradable_at")
                unknown["market_reaction_tradable"] = unknown["market_reaction"]
                unknown["overnight_gap"] = unknown["market_reaction"]

        # ── liquidity at the decision, from the SAME pre-event window ─────
        # A gross edge is not an edge. These are the inputs to a break-even
        # cost, and they are computed strictly before `ann_d` like every other
        # covariate — a liquidity measure that includes the announcement day
        # would be measuring the event's own volume spike.
        dv = hlr = amh = None
        _pre = pre
        _dv = [float(b[2]) * float(b[4]) for b in _pre
               if b[2] is not None and b[4] is not None and b[4] > 0]
        if len(_dv) >= 10:
            dv = float(sorted(_dv)[len(_dv) // 2])
            _im = [abs(float(b[1])) / (float(b[2]) * float(b[4])) * 1e6
                   for b in _pre
                   if b[2] and b[4] and b[4] > 0 and b[1] is not None]
            amh = float(sum(_im) / len(_im)) if _im else None
            _hl = [(float(b[6]) - float(b[5])) / ((float(b[6]) + float(b[5])) / 2)
                   for b in _pre
                   if b[5] and b[6] and b[6] > 0 and b[5] > 0 and b[6] >= b[5]]
            hlr = float(sum(_hl) / len(_hl)) if _hl else None
        for _f, _v in (("dollar_volume_20d", dv), ("hl_range_20d", hlr),
                       ("amihud_20d", amh)):
            if _v is None:
                unknown[_f] = (f"fewer than 10 usable pre-event sessions with "
                               f"price and volume, or the inputs were absent")
        unknown["guidance_state"] = GUIDANCE_UNAVAILABLE
        unknown["options_implied_move"] = (
            "single-name option surface not extracted; the daily vsurfd pull "
            "is bounded to WM0's 18 ETFs for IV-ORACLE-GAP-1")

        rec = ExpectationRecord(
            entity=str(row.cname or row.ticker), entity_id_kind="ibes_ticker",
            entity_id=str(row.ticker), event_type="EPS_ANNOUNCEMENT",
            event_id=f"IBES:{row.ticker}:{str(row.pends)[:10]}",
            first_public_ts=pub,
            expectation_asof=_iso(row.statpers) if row.statpers is not None else None,
            observed_at=obs, tradable_at=trd,
            numeric_expectation=exp, expectation_dispersion=disp,
            n_estimates=nest,
            actual=None if pd.isna(row.actual) else float(row.actual),
            analyst_revision_state=_revision_state(
                None if row.numup is None or pd.isna(row.numup) else row.numup,
                None if row.numdown is None or pd.isna(row.numdown) else row.numdown),
            guidance_state="UNKNOWN",
            pre_event_price_runup=runup, market_reaction=react,
            overnight_gap=gap, market_reaction_tradable=tradable,
            options_implied_move=None,
            dollar_volume_20d=dv, hl_range_20d=hlr, amihud_20d=amh,
            source_ids=[f"ibes.actu_epsus:{row.ticker}:{str(row.pends)[:10]}"]
            + ([f"ibes.statsumu_epsus:{row.ticker}:{str(row.statpers)[:10]}"]
               if row.statpers is not None else []),
            unknown_reasons=unknown,
        )
        bad = validate(rec, strict=False)
        if bad:
            refused += 1
            for b in bad:
                key = _refusal_kind(b)
                reasons[key] = reasons.get(key, 0) + 1
            continue
        recs.append(rec)
    return recs, {"n_refused": refused, "refusal_reasons": reasons,
                  "n_unknown_announcement_time": n_unknown_time,
                  "unknown_time_rule": (
                      "`anntims` missing or exactly 00:00:00 -> the NEXT "
                      "session's open. Read as a time, midnight means "
                      "pre-market and would make the announcement tradable at "
                      "a price that may precede it.")}


def cmd_collect(y0: int, y1: int, *, overwrite: bool = False) -> int:
    import pandas as pd
    from sqlalchemy import bindparam, text

    ok, why = _reachable()
    if not ok:
        print(f"WRDS unreachable ({why}) — nothing collected, nothing faked.")
        return 1

    eng = _engine()
    out = OUT_DIR / f"g4_earnings_{y0}_{y1}.jsonl"
    if out.exists() and not overwrite:
        print(f"{out.name} exists — REFUSING to overwrite. Pass --overwrite "
              f"only if that extraction is known to be superseded.")
        return 1

    start, end = f"{y0}-01-01", f"{y1}-12-31"
    started = datetime.now(timezone.utc).isoformat()
    print(f"events {start} .. {end}")

    with eng.connect() as c:
        df = pd.read_sql(text(SQL_EVENTS), c, params={"start": start, "end": end})
        print(f"  IBES announcements: {len(df):,}")
        # The coverage floor, applied AFTER the count above so the denominator
        # is visible rather than implied.
        keep = df["numest"].fillna(0) >= MIN_ESTIMATES
        print(f"  with >= {MIN_ESTIMATES} estimates: {int(keep.sum()):,} "
              f"({len(df) - int(keep.sum()):,} dropped as thin coverage)")
        df = df[keep].copy()
        if df.empty:
            print("  nothing to build.")
            return 1

        cal = [str(d)[:10] for (d,) in c.execute(
            text(SQL_CALENDAR), {"start": f"{y0 - 1}-01-01",
                                 "end": f"{y1 + 1}-12-31"})]
        print(f"  exchange sessions in window: {len(cal):,}")

        cusips = sorted({str(x) for x in df["cusip"].dropna().unique()})
        link_stmt = text(SQL_LINK).bindparams(bindparam("cusips", expanding=True))
        spans: dict[str, list] = {}
        for r in c.execute(link_stmt, {"cusips": cusips}):
            spans.setdefault(str(r.ncusip), []).append(
                (str(r.namedt)[:10], str(r.nameenddt)[:10], int(r.permno)))
        link = _resolve_links(df, spans)
        print(f"  cusip -> permno at the ANNOUNCEMENT date: "
              f"{len(link):,} / {len(cusips):,} cusips")

        permnos = sorted(set(link.values()))
        px_stmt = text(SQL_PRICES).bindparams(bindparam("permnos", expanding=True))
        pxdf = pd.read_sql(px_stmt, c, params={
            "permnos": permnos, "start": f"{y0 - 1}-10-01", "end": f"{y1 + 1}-02-01"})
        print(f"  CRSP daily rows: {len(pxdf):,}")

    by_permno: dict[int, list] = {}
    for p, g in pxdf.dropna(subset=["ret"]).groupby("permno"):
        g = g.sort_values("date")
        by_permno[int(p)] = list(zip(g["date"].astype(str).str[:10],
                                     g["ret"].astype(float),
                                     g["prc"], g["openprc"],
                                     g["vol"], g["bidlo"], g["askhi"]))

    recs, refusals = build_records(
        df, cal, {"link": link, "by_permno": by_permno})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    summ = summarise(recs)
    print(f"\nwrote {len(recs):,} records -> {out}")
    print(f"  refused at validation: {refusals['n_refused']:,}")
    for k, v in sorted(refusals["refusal_reasons"].items(),
                       key=lambda kv: -kv[1]):
        print(f"     {v:>6,}  {k}")
    print("\n  " + "\n  ".join(f"{k:<32} {v}" for k, v in summ.items()))

    m = (json.loads(MANIFEST.read_text(encoding="utf-8"))
         if MANIFEST.exists() else {"dataset": "g4/earnings_v1", "runs": []})
    m["runs"].append({
        "kind": "collect", "years": [y0, y1], "file": out.name,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sql": {"events": SQL_EVENTS.strip(), "calendar": SQL_CALENDAR.strip(),
                "link": SQL_LINK.strip(), "prices": SQL_PRICES.strip()},
        "rules": {"min_estimates": MIN_ESTIMATES,
                  "after_hours_from": AFTER_HOURS_FROM,
                  "runup_trading_days": RUNUP_DAYS,
                  "unadjusted_files": True,
                  "consensus_strictly_before_announcement": True,
                  "fiscal_period_matched_on_fpedats_not_fpi": True},
        "summary": summ, **refusals, "sha256": _sha256(out),
    })
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"\nmanifest -> {MANIFEST}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--years", nargs=2, type=int, metavar=("Y0", "Y1"),
                    required=True)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass
    return cmd_collect(a.years[0], a.years[1], overwrite=a.overwrite)


if __name__ == "__main__":
    raise SystemExit(main())
