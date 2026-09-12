"""BOOK A's DATA — the short-interest x turnover panel, PIT from PUBLICATION.

WHY THIS FILE EXISTS
====================
`docs/research_notes/2026-09-12/spec_first_books.md` §A.2 says no historical
short-interest panel exists in this repository and that FINRA's files must be
newly ingested. That is **wrong**, and the correction is
`docs/research_notes/2026-09-12/probe_short_interest.md`: the WRDS bulk pull
already put `comp__sec_shortint.parquet` (5,279,203 rows, 2006-07-14 ..
2026-08-14) and `comp__sec_shortint_legacy.parquet` (4,770,658 rows,
1973-01-15 .. 2024-12-31) on disk. `backend/services/short_interest.py` is a
live yfinance SNAPSHOT with no history; the bulk panel is the history.

So this script builds no new pull. It joins what is already here.

THE PIT TRAP, WHICH IS THE WHOLE POINT
======================================
`datadate` in `comp.sec_shortint` is the **settlement date** of the short
position — NOT the date the figure was published. A panel keyed on `datadate`
and used on `datadate` is a panel that trades on a number nobody could see, and
it is the same trap FINRA's own files carry. The probe measured the publication
lag at 10-26 calendar days (median 14; the exchanges' nominal commitment is 8
business days), so this panel stamps

    observed_at = datadate + PUBLICATION_LAG_DAYS (14 calendar days)

and every consumer is expected to use `observed_at`, never `datadate`. Fourteen
is the measured MEDIAN, which means roughly half the prints were public earlier
and roughly half later; the honest reading is that a book keyed on `observed_at`
is approximately right and occasionally a few days optimistic. A book that
needs better than that must wait for the FINRA forward leg, whose own
`settlementDate` field carries the same distinction.

WHY THE VOLUME UNIT IS VERIFIED AND NOT ASSUMED
===============================================
Turnover is `vol / (shrout * 1000)` and is wrong by a factor of 100 if CRSP's
`vol` is in round lots rather than shares. Measured here, across eras, before
the panel is built (`verify_volume_unit`): median daily turnover 0.122% (1990),
0.198% (1995), 0.307% (2000), 0.382% (2005), 0.476% (2010), 0.662% (2020),
0.597% (2024) — a smooth secular rise with no 100x break anywhere, so `vol` is
RAW SHARES and `shrout` is THOUSANDS of shares over the whole 1990-2024 file
set. The check runs on every build and lands in the receipt: a unit that was
verified once in a session and never again is a unit that changes silently when
the vendor re-pulls.

WHAT IS UNRESOLVED, AND SAYS SO
===============================
**Nasdaq double-counting (Anderson-Dyl 2005).** Dealer-intermediated volume on
Nasdaq is reported roughly twice, so Nasdaq turnover is inflated relative to
NYSE turnover, most severely before decimalisation/2001. The probe did not
verify the adjustment against CRSP's own volume notes and neither does this
script. The panel therefore carries `turnover_unadjusted_for_venue = True` and
the receipt names the caveat as UNRESOLVED. A cross-venue turnover SORT is the
construction this bites; Book A's own double sort is one, which is exactly why
the flag travels on the row instead of living in a comment.

    python -m scripts.short_interest_panel --start 1990 --end 2024
    python -m scripts.short_interest_panel --start 2020 --end 2021 --out <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("short_interest_panel")

#: The measured MEDIAN publication lag, in calendar days, from
#: `docs/research_notes/2026-09-12/probe_short_interest.md` (range 10-26; the
#: exchanges' nominal commitment is 8 business days). A number here that is not
#: the measured one would be a PIT rule chosen for convenience.
PUBLICATION_LAG_DAYS = 14

#: Trailing sessions the monthly turnover is summed over. Twenty-one is one
#: trading month and matches `log_dollar_vol_20d`'s own window convention in
#: `learner/dataset.py`.
TURNOVER_WINDOW = 21

#: Winsorisation of turnover, per output year. The probe found a low-float
#: outlier at 4,073%/month in a twenty-name sample; a double sort on turnover
#: that lets one such name into the top cell is sorting on a share count, not
#: on trading interest.
WINSOR_LO, WINSOR_HI = 0.01, 0.99

#: The link rows that are a real identity link. Applied EXPLICITLY even though
#: `link_ccm.parquet` happens to contain only these today: a filter that is a
#: no-op on this vintage is not a no-op on the next one.
LINKTYPES = ("LC", "LU")
LINKPRIMS = ("P", "C")

#: CRSP daily files on disk, from `backend/data/optimus/wrds/crsp_dsf_<year>`.
CRSP_FIRST_YEAR, CRSP_LAST_YEAR = 1990, 2024


# --------------------------------------------------------------------------
# paths


def wrds_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "wrds"


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "short_interest" / "comp_sec_shortint"


def receipt_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return (OPTIMUS_LEDGER_DIR / "short_interest"
            / "comp_sec_shortint_receipt.json")


def crsp_path(year: int) -> Path:
    return wrds_dir() / f"crsp_dsf_{year}.parquet"


# --------------------------------------------------------------------------
# the short-interest panel


def _as_ts(series):
    import pandas as pd
    return pd.to_datetime(series, errors="coerce")


def dedupe_shortint(current, legacy) -> tuple:
    """(one panel, stats). The 2006-2024 overlap resolves to the CURRENT file.

    Both files carry the same (gvkey, iid, datadate) key over their overlap and
    the current table is the live one; preferring the legacy archive on an
    overlap would freeze whatever restatement the archive was taken before.
    Which side won is COUNTED, not assumed — an overlap that turns out to
    disagree on the value is a fact a reader needs.
    """
    import pandas as pd

    cur = current.copy()
    leg = legacy.copy()
    for df, src in ((cur, "current"), (leg, "legacy")):
        df["datadate"] = _as_ts(df["datadate"])
        df["source_file"] = src
    both = pd.concat([cur, leg], ignore_index=True)
    key = ["gvkey", "iid", "datadate"]
    before = len(both)
    # `current` first, so `drop_duplicates(keep="first")` keeps it.
    both["_rank"] = (both["source_file"] == "legacy").astype(int)
    both = both.sort_values(key + ["_rank"], kind="mergesort")
    dedup = both.drop_duplicates(subset=key, keep="first").drop(columns=["_rank"])
    stats = {
        "rows_current": int(len(cur)),
        "rows_legacy": int(len(leg)),
        "rows_concatenated": int(before),
        "rows_after_dedupe": int(len(dedup)),
        "overlap_rows_dropped": int(before - len(dedup)),
        "kept_from_current": int((dedup["source_file"] == "current").sum()),
        "kept_from_legacy": int((dedup["source_file"] == "legacy").sum()),
        "rule": ("the key is (gvkey, iid, datadate); on a collision the CURRENT "
                 "file wins because it is the live table and the legacy archive "
                 "predates any restatement"),
    }
    return dedup.reset_index(drop=True), stats


def pick_primary_issue(df) -> tuple:
    """Keep ONE issue per (gvkey, datadate): the lowest numeric `iid`.

    `link_ccm.parquet` carries no `iid`, so the gvkey -> permno link cannot tell
    two issues of the same company apart. Compustat numbers the primary issue
    `01` and reserves 90/91 for ADR-and-similar forms, so the lowest numeric iid
    is the primary issue by the vendor's own convention. It is an IDENTITY rule,
    not a return-affecting choice, and the number of (gvkey, datadate) cells
    that actually had more than one issue is recorded so the rule's reach is
    visible rather than assumed small.
    """
    import pandas as pd

    d = df.copy()
    d["iid_num"] = pd.to_numeric(d["iid"], errors="coerce")
    multi = d.groupby(["gvkey", "datadate"])["iid"].transform("nunique")
    n_multi_cells = int((multi > 1).groupby([d["gvkey"], d["datadate"]]).first().sum())
    d = d.sort_values(["gvkey", "datadate", "iid_num", "iid"], kind="mergesort")
    kept = d.drop_duplicates(subset=["gvkey", "datadate"], keep="first")
    stats = {
        "rows_in": int(len(df)),
        "rows_out": int(len(kept)),
        "dropped_non_primary_issues": int(len(df) - len(kept)),
        "gvkey_date_cells_with_multiple_issues": n_multi_cells,
        "rule": ("lowest numeric iid per (gvkey, datadate) — Compustat numbers "
                 "the primary issue 01 and 90/91 are ADR-and-similar forms; "
                 "link_ccm carries no iid so the link cannot disambiguate"),
    }
    return kept.drop(columns=["iid_num"]).reset_index(drop=True), stats


def link_permno(si, link) -> tuple:
    """Interval join gvkey -> permno on `linkdt <= datadate <= linkenddt`.

    An open link (`linkenddt` null) runs to the present. A `datadate` outside
    every link interval for its gvkey gets NO permno and is DROPPED with a
    count, never carried with a null permno: a row that cannot be priced is a
    row that would silently become a hole in a portfolio.
    """
    import pandas as pd

    lk = link.copy()
    lk = lk[lk["linktype"].isin(LINKTYPES) & lk["linkprim"].isin(LINKPRIMS)]
    lk["linkdt"] = _as_ts(lk["linkdt"])
    lk["linkenddt"] = _as_ts(lk["linkenddt"]).fillna(pd.Timestamp("2262-01-01"))
    lk = lk.dropna(subset=["permno", "linkdt"])
    # Primary links first, so a gvkey-date inside two intervals resolves to the
    # primary one deterministically rather than by row order in the file.
    lk["_prim"] = (lk["linkprim"] != "P").astype(int)
    lk = lk.sort_values(["gvkey", "_prim", "linkdt"], kind="mergesort")

    merged = si.merge(lk[["gvkey", "permno", "linktype", "linkprim",
                          "linkdt", "linkenddt", "_prim"]],
                      on="gvkey", how="left")
    inside = (merged["linkdt"] <= merged["datadate"]) & \
             (merged["datadate"] <= merged["linkenddt"])
    hit = merged[inside].sort_values(["gvkey", "datadate", "_prim", "linkdt"],
                                     kind="mergesort")
    hit = hit.drop_duplicates(subset=["gvkey", "iid", "datadate"], keep="first")
    hit = hit.drop(columns=["_prim", "linkdt", "linkenddt"])
    hit["permno"] = hit["permno"].astype("int64")
    stats = {
        "rows_in": int(len(si)),
        "rows_linked": int(len(hit)),
        "rows_unlinked_dropped": int(len(si) - len(hit)),
        "match_rate": (round(len(hit) / len(si), 4) if len(si) else None),
        "linktypes": list(LINKTYPES), "linkprims": list(LINKPRIMS),
        "rule": ("linkdt <= datadate <= linkenddt; a null linkenddt is an OPEN "
                 "link; primary (linkprim P) wins a tie"),
    }
    return hit.reset_index(drop=True), stats


# --------------------------------------------------------------------------
# CRSP: shares outstanding, volume, and the unit check


def verify_volume_unit(dsf) -> dict:
    """Is `vol` raw shares or round lots? Measured, never assumed.

    Returns the median and 99th percentile of `vol / (shrout * 1000)`. A daily
    turnover median in the 0.1%-1% band says raw shares; a median near 10%-100%
    says the figure is in hundreds and every turnover in this panel would be
    100x too large.
    """
    import numpy as np

    d = dsf[(dsf["vol"] > 0) & (dsf["shrout"] > 0)]
    if d.empty:
        return {"verdict": "CANNOT DETERMINE — no positive vol/shrout rows",
                "n": 0}
    t = (d["vol"] / (d["shrout"] * 1000.0)).to_numpy(dtype=float)
    med = float(np.nanmedian(t))
    out = {"n": int(len(t)), "median_daily_turnover": round(med, 6),
           "p99_daily_turnover": round(float(np.nanpercentile(t, 99)), 6)}
    if 0.0001 <= med <= 0.05:
        out["unit"] = "raw shares"
        out["verdict"] = (f"vol is RAW SHARES and shrout is THOUSANDS: median "
                          f"daily turnover {med:.4%} is in the plausible band")
    else:
        out["unit"] = "UNKNOWN"
        out["verdict"] = (f"REFUSED: median daily turnover {med:.4%} is outside "
                          f"the plausible 0.01%-5% band, so vol/(shrout*1000) "
                          f"is not turnover on this file and the unit must be "
                          f"re-established before any panel is built")
    return out


def load_crsp(years, path_for=None):
    """Concatenated CRSP daily rows for `years`, sorted by (permno, date)."""
    import pandas as pd

    path_for = path_for or crsp_path
    frames = []
    for y in years:
        p = path_for(int(y))
        if not Path(p).is_file():
            continue
        df = pd.read_parquet(p, columns=["permno", "date", "prc", "vol", "shrout"])
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["permno", "date", "prc", "vol", "shrout"])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = _as_ts(out["date"])
    out["permno"] = out["permno"].astype("int64")
    return out.sort_values(["permno", "date"], kind="mergesort").reset_index(drop=True)


def crsp_features(dsf):
    """Per (permno, date): trailing 21-session volume sum, shrout, |prc|.

    The window ENDS ON the row's own date, so every value is known at that
    close. `min_periods` is the full window: a partial sum over 6 sessions
    presented as a monthly turnover is a smaller number for a mechanical reason
    and would sort the name into the LOW-turnover leg it does not belong in.
    """
    import pandas as pd

    d = dsf.copy()
    d["vol"] = pd.to_numeric(d["vol"], errors="coerce")
    grp = d.groupby("permno", sort=False)["vol"]
    d["vol_21d"] = grp.transform(
        lambda s: s.rolling(TURNOVER_WINDOW, min_periods=TURNOVER_WINDOW).sum())
    d["price"] = d["prc"].abs()
    return d[["permno", "date", "price", "shrout", "vol_21d"]]


def attach_crsp(si, feats, *, tolerance_days: int = 10):
    """As-of join: each (permno, datadate) takes the NEAREST PRIOR CRSP session.

    Backward, with a tolerance, because a settlement date can fall on a weekend
    or a holiday — but a settlement date whose nearest prior session is two
    weeks back belongs to a name that had stopped trading, and joining it would
    divide a short interest by a stale share count.
    """
    import pandas as pd

    left = si.sort_values("datadate", kind="mergesort").copy()
    right = feats.sort_values("date", kind="mergesort").copy()
    if left.empty or right.empty:
        out = left.copy()
        for c in ("price", "shrout", "vol_21d"):
            out[c] = pd.NA
        return out
    merged = pd.merge_asof(
        left, right, left_on="datadate", right_on="date", by="permno",
        direction="backward", tolerance=pd.Timedelta(days=int(tolerance_days)))
    return merged


def winsorise(series, lo: float = WINSOR_LO, hi: float = WINSOR_HI):
    """Clip to the [lo, hi] quantiles of the series' own finite values."""
    import numpy as np
    import pandas as pd

    s = pd.to_numeric(series, errors="coerce")
    finite = s[np.isfinite(s)]
    if finite.empty:
        return s
    a, b = float(finite.quantile(lo)), float(finite.quantile(hi))
    return s.clip(lower=a, upper=b)


def observed_at(datadate_series):
    """`datadate + PUBLICATION_LAG_DAYS`. The one PIT rule this panel has."""
    import pandas as pd
    return _as_ts(datadate_series) + pd.Timedelta(days=PUBLICATION_LAG_DAYS)


def build_frame(si_year, feats):
    """The output frame for one year: ratios, turnover, PIT stamp, flags."""
    import numpy as np

    merged = attach_crsp(si_year, feats)
    merged = merged.dropna(subset=["shrout", "vol_21d"])
    if merged.empty:
        return merged
    shares = merged["shrout"].astype(float) * 1000.0
    merged = merged.assign(
        shares_outstanding=shares,
        si_ratio=merged["shortint"].astype(float) / shares.replace(0.0, np.nan),
        turnover_21d=merged["vol_21d"].astype(float) / shares.replace(0.0, np.nan),
        observed_at=observed_at(merged["datadate"]),
    )
    merged = merged[np.isfinite(merged["si_ratio"])
                    & np.isfinite(merged["turnover_21d"])]
    if merged.empty:
        return merged
    merged["turnover_21d_w"] = winsorise(merged["turnover_21d"])
    merged["turnover_unadjusted_for_venue"] = True
    merged["publication_lag_days"] = PUBLICATION_LAG_DAYS
    cols = ["permno", "gvkey", "iid", "datadate", "observed_at", "shortint",
            "shortintadj", "shares_outstanding", "price", "si_ratio",
            "turnover_21d", "turnover_21d_w", "source_file", "linktype",
            "linkprim", "publication_lag_days", "turnover_unadjusted_for_venue"]
    have = [c for c in cols if c in merged.columns]
    return merged[have].sort_values(["datadate", "permno"],
                                    kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------
# the build


def build(*, start: int = CRSP_FIRST_YEAR, end: int = CRSP_LAST_YEAR,
          out: Path | None = None, write: bool = True) -> dict:
    """Build `<out>/<year>.parquet` for every year in [start, end], + a receipt."""
    import pandas as pd

    t0 = datetime.now(timezone.utc)
    wd = wrds_dir()
    cur_p = wd / "bulk" / "comp__sec_shortint.parquet"
    leg_p = wd / "bulk" / "comp__sec_shortint_legacy.parquet"
    link_p = wd / "link_ccm.parquet"
    missing = [str(p) for p in (cur_p, leg_p, link_p) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"the WRDS bulk short-interest panel is not on this machine: "
            f"{missing}. `docs/research_notes/2026-09-12/probe_short_interest.md` "
            f"says it is produced by `scripts/wrds_pull_everything.py`; nothing "
            f"here re-pulls it, because a build that silently downloads 10M rows "
            f"is not a build.")

    si, dd_stats = dedupe_shortint(pd.read_parquet(cur_p), pd.read_parquet(leg_p))
    si, iid_stats = pick_primary_issue(si)
    si, link_stats = link_permno(si, pd.read_parquet(link_p))

    outd = Path(out) if out is not None else out_dir()
    if write:
        outd.mkdir(parents=True, exist_ok=True)

    years: dict[str, dict] = {}
    unit_check: dict = {}
    si["_y"] = si["datadate"].dt.year
    for year in range(int(start), int(end) + 1):
        chunk = si[si["_y"] == year].drop(columns=["_y"])
        if chunk.empty:
            years[str(year)] = {"rows": 0, "reason": "no short-interest rows"}
            continue
        dsf = load_crsp([year - 1, year])
        if dsf.empty:
            years[str(year)] = {"rows": 0,
                                "reason": f"no crsp_dsf_{year}.parquet on disk"}
            continue
        if not unit_check:
            unit_check = verify_volume_unit(dsf)
            if unit_check.get("unit") != "raw shares":
                raise ValueError(unit_check["verdict"])
        frame = build_frame(chunk, crsp_features(dsf))
        row = {"rows_shortint": int(len(chunk)), "rows": int(len(frame)),
               "match_rate_vs_shortint": (round(len(frame) / len(chunk), 4)
                                          if len(chunk) else None),
               "permnos": int(frame["permno"].nunique()) if len(frame) else 0,
               "median_si_ratio": (round(float(frame["si_ratio"].median()), 6)
                                   if len(frame) else None),
               "median_turnover_21d": (round(float(frame["turnover_21d_w"].median()), 6)
                                       if len(frame) else None)}
        if write and len(frame):
            p = outd / f"{year}.parquet"
            frame.to_parquet(p, index=False)
            row["path"] = str(p)
        years[str(year)] = row
        logger.info("%s: %d rows (%s)", year, row["rows"],
                    row["match_rate_vs_shortint"])

    total = sum(int(v.get("rows", 0)) for v in years.values())
    receipt = {
        "job": "short_interest_panel",
        "built_utc": t0.isoformat(timespec="seconds"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "for": "Book A — low short interest x high turnover (spec_first_books.md A)",
        "licence": "PRODUCT_EXPERIMENT",
        "sources": {"current": str(cur_p), "legacy": str(leg_p),
                    "link": str(link_p),
                    "crsp": str(wd / "crsp_dsf_<year>.parquet")},
        "dedupe": dd_stats,
        "primary_issue": iid_stats,
        "link": link_stats,
        "volume_unit_check": unit_check,
        "pit_rule": {
            "observed_at": f"datadate + {PUBLICATION_LAG_DAYS} calendar days",
            "why": ("`datadate` is the SETTLEMENT date, not the publication "
                    "date. The probe measured the publication lag at 10-26 "
                    "calendar days (median 14; nominal 8 business days), so a "
                    "panel used on `datadate` trades on a figure nobody could "
                    "see. Fourteen is the MEDIAN: about half the prints were "
                    "public earlier and about half later, so a book keyed on "
                    "`observed_at` is approximately right and occasionally a "
                    "few days optimistic."),
            "source": "docs/research_notes/2026-09-12/probe_short_interest.md",
        },
        "turnover": {
            "definition": f"sum(vol) over {TURNOVER_WINDOW} sessions / (shrout * 1000)",
            "window_ends_on": "the row's own CRSP session, so it is known at that close",
            "winsorised_at": [WINSOR_LO, WINSOR_HI],
            "winsorised_within": "each output year",
        },
        "unresolved": [
            "NASDAQ DOUBLE-COUNTING (Anderson-Dyl 2005) is UNRESOLVED. Nasdaq "
            "dealer volume is reported roughly twice, inflating Nasdaq turnover "
            "against NYSE turnover, worst before 2001. Neither the probe nor "
            "this build verified an adjustment against CRSP's own volume notes, "
            "so every row carries `turnover_unadjusted_for_venue = True`. A "
            "CROSS-VENUE turnover sort is the construction this bites, and Book "
            "A's double sort is one.",
            "`observed_at` uses one fixed median lag rather than the per-print "
            "release date, which this vendor table does not carry. The FINRA "
            "forward leg carries `settlementDate` and the same distinction.",
        ],
        "years": years,
        "total_rows": total,
        "out_dir": str(outd),
    }
    if write:
        rp = receipt_path()
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
        receipt["receipt_path"] = str(rp)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=CRSP_FIRST_YEAR)
    ap.add_argument("--end", type=int, default=CRSP_LAST_YEAR)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="build the frames and print the receipt; write nothing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rec = build(start=a.start, end=a.end,
                out=Path(a.out) if a.out else None, write=not a.dry_run)
    print(json.dumps({k: v for k, v in rec.items() if k != "years"},
                     indent=2, default=str))
    print(json.dumps({"years": rec["years"]}, indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
