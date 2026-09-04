"""Do the tracker's status rules survive OUT OF SAMPLE, on the whole US market?

    python -m scripts.tracker_ibes_backtest --run
    python -m scripts.tracker_ibes_backtest --run --start 2013 --end 2024 --cost-bps 10

THE QUESTION, AND WHY IT IS NOT ANSWERABLE IN THE OTHER REPO
===========================================================
`aegis-alpha-terminal` grades `murat_rule_v1` against a base rate measured on a
152-name news panel over ELEVEN DATE BLOCKS, in sample. The tracker it now
selects from holds several thousand names and is one day old, so it cannot
produce a base rate of its own: a forward rate needs forward returns and there
are none yet.

IBES can. `ibes__ptgsumu` carries consensus PRICE TARGETS **in the share terms
that existed at `statpers`** and `ibes__recdsum` carries recommendation counts,
both monthly, both point-in-time, for the whole US market from 2013. Joined to
CRSP daily prices that is eleven years of the same screen on names nobody
curated -- which is the only instrument that can answer Murat's two hypotheses:

    "thin coverage has more upside"     -> split every result by coverage bucket
    "do not buy last year's winner"     -> split every result by past_winner

THE SHARE-BASIS TRAP, WHICH THIS FILE FELL INTO FOR A YEAR
==========================================================
IBES ships the price-target summary twice: `ibes__ptgsum` is SPLIT-ADJUSTED
(every historical target restated in END-OF-SAMPLE share terms) and
`ibes__ptgsumu` is UNADJUSTED (the target as it was quoted). Until 2026-09-04
this file read the ADJUSTED file and divided by the RAW CRSP close, which is not
a ratio at all: `ratio_used = true_ratio / cfacpr(t)`, and `cfacpr(t)` is a
FUTURE quantity. AAPL 2013-06-20: adjusted 19.323, unadjusted 541.04, raw close
413.50, `cfacpr` 28.0 -- the tape said 0.047, the truth was 1.308. A name that
LATER reverse-split had its ratio inflated into the "toxic" band, so that label
was a future-collapse detector (74.35% of toxic rows carry a future reverse
split, against 0.09% of the below-1.5 band).
See `docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` §2. Pinned by
`backend/tests/test_ibes_target_share_basis.py`.

THE SCALE TRAP, NAMED BECAUSE IT WOULD NOT LOOK LIKE AN ERROR
=============================================================
IBES `meanrec` runs 1 = STRONG BUY to 5 = STRONG SELL. The tracker's consensus
runs 5 = STRONG BUY, matching Murat's ">= 4.1 / 5". They are the same numbers
in opposite order, so applying a `>= 4.1` bar to raw `meanrec` would select the
most HATED decile of the market and would produce a perfectly clean-looking
backtest of the opposite strategy. The conversion is `6 - meanrec` and it is
asserted by a test below before anything else runs.

THE RULES ARE IMPORTED, NEVER RETYPED
=====================================
`alpha/tracker.py` lives in the other repository and is loaded here BY PATH.
Re-implementing the thresholds in this file would guarantee that the two drift,
and a test of thresholds nobody runs live is not an out-of-sample test of
anything. The module's sha256 goes in the receipt so the result names the exact
version of the rules it tested.

WHAT THIS TEST CANNOT DO, STATED UP FRONT
=========================================
* **Clause (d), the dated catalyst, is not readable here.** IBES carries no
  event calendar, so `days_to_catalyst` is None for every row and STRONG_BUY --
  which asserts a catalyst -- can never fire. What is tested is the BUY bar,
  which has no catalyst clause. This is a real limit on scope, not a silent
  approximation: the receipt says `strong_buy_testable: false`.
* **Monthly, not daily.** IBES summary is a monthly cut, so the basket
  rebalances monthly and holds one month. A rule that only works intra-month is
  invisible here.
* Costs are charged on measured TURNOVER, both sides, and are never zero.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The Shumway (1997) delisting fills are IMPORTED, never retyped: the panel and
# the benchmark must count a dead name's last return the same way. `learner
# .benchmark` imports `learner.dataset` only inside a function, so this cannot
# close a cycle with `learner.dataset`'s top-level import of this module.
from learner.benchmark import SHUMWAY_FILL                       # noqa: E402

WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
BULK = WRDS / "bulk"
OUT = REPO / "backend" / "data" / "optimus" / "tracker_backtest"

#: The other repository. The rules live there and are imported, not copied.
TERMINAL = Path(r"C:\Users\mrthn\aegis-alpha-terminal")
TRACKER_PY = TERMINAL / "alpha" / "tracker.py"

#: The SPLIT-ADJUSTED IBES summary. Held behind a name, never written as a
#: `BULK / <adjusted-file-name>` literal, so that
#: `backend/tests/test_ibes_target_share_basis.py` -- which parses the loader
#: source for the file it opens -- can only ever match the PIT file.
_ADJUSTED_PTG_FILE = "ibes__ptgsum.parquet"

#: DELISTING CODES. CRSP `dlstcd`:
#:   100      still trading (not a delisting at all)
#:   200-399  merger / exchange -- the holder receives something
#:   400-489  liquidation (450, n=216 in 2013-24, mean dlret -0.74%)
#:   {500} u [520, 584]  PERFORMANCE-CODED: dropped by the exchange, moved to
#:            OTC, price/market-cap/assets deficient. 866 events 2013-24, mean
#:            `dlret` -24.63%. Shumway (1997) fills a MISSING dlret here.
#: The wider 400-591 range is NOT the performance set: it dilutes the mean to
#: -19.57% by counting liquidations, and 585/587/591 are administrative.
DELIST_PERF_CODES = (500,)
DELIST_PERF_RANGE = (520, 584)
DELIST_LIQUIDATION_RANGE = (400, 489)
DELIST_MERGER_RANGE = (200, 399)

#: CRSP share codes 10 and 11 are US COMMON STOCK. Everything else -- ADRs,
#: closed-end funds, REITs with other codes, units -- is a different instrument
#: and the tracker's live universe (Alpaca US equities, non-ETF) does not hold
#: them either.
SHRCD_COMMON = (10, 11)
#: NYSE / AMEX / NASDAQ.
EXCHCD_MAIN = (1, 2, 3)

#: One side, in basis points. Charged on measured turnover, both sides. The
#: farm's `Policy` REFUSES a zero-cost run unless it is declared a diagnostic,
#: and the same rule applies here.
DEFAULT_COST_BPS = 10.0

#: The honest label for CRSP's NONCLASSIFIABLE block. SIC 9900-9999 is the
#: standard's own "Nonclassifiable Establishments" range -- 9999 is the code
#: CRSP stamps on a name it could not classify, and this panel is dominated by
#: it: 3,580 of the 3,625 filtered name-rows in 9000-9999 are exactly 9999
#: (98.8%, measured on `crsp__stocknames.parquet` 2026-09-03; 9990 adds 12
#: more rows and the 9995 placeholder some vendors use does NOT appear here).
#: Until 2026-09-03 the whole 9000-9999 range was labelled "Public
#: Administration", which put an industry's name on 22.5% of the training
#: panel's rows when the truth was "we do not know". A sector label that means
#: absence of information must SAY so -- anything sector-neutral built on the
#: old label was quietly neutralising against a bucket of unknowns.
#: Downstream readers key on this constant, not on the string.
SIC_UNCLASSIFIED = "Unclassified"

#: SIC division -> the sector label `past_winner` groups on. Coarse on purpose:
#: the live tracker groups on Finnhub's industry string, which is coarser than
#: a 4-digit SIC and finer than a 1-digit division. What matters for the test is
#: that names are compared against LIKE names and that thin groups fall back to
#: the market, which the imported rule already handles.
#:
#: Genuine Public Administration (Division J, 9100-9729 in the standard;
#: everything observed here sits at 9199-9711, 33 name-rows) keeps its label.
#: The Nonclassifiable range 9900-9999 gets `SIC_UNCLASSIFIED` -- see above.
SIC_DIVISIONS = (
    (1, 999, "Agriculture"), (1000, 1499, "Mining"), (1500, 1799, "Construction"),
    (2000, 3999, "Manufacturing"), (4000, 4999, "Transport & Utilities"),
    (5000, 5199, "Wholesale"), (5200, 5999, "Retail"),
    (6000, 6799, "Finance & Real Estate"), (7000, 8999, "Services"),
    (9000, 9899, "Public Administration"), (9900, 9999, SIC_UNCLASSIFIED),
)


def sic_division(siccd) -> str:
    """4-digit SIC -> division label. 9900-9999 is `SIC_UNCLASSIFIED`, never
    "Public Administration" -- CRSP's 9999 means it did NOT classify the name,
    and a label must not claim otherwise. Unparseable/absent codes (CRSP uses
    0 for missing) stay "_UNKNOWN": distinct from `SIC_UNCLASSIFIED` because
    "CRSP said nonclassifiable" and "no code at all" have different provenance
    even though both mean the sector is not known."""
    try:
        s = int(siccd)
    except (TypeError, ValueError):
        return "_UNKNOWN"
    for lo, hi, name in SIC_DIVISIONS:
        if lo <= s <= hi:
            return name
    return "_UNKNOWN"


# --------------------------------------------------------------- the rules

def load_tracker_rules():
    """Import `alpha/tracker.py` from the terminal repo. (module, sha256).

    REFUSES rather than falling back to a local copy. A backtest that silently
    tested a stale duplicate of the rules would be worse than no backtest: it
    would carry the authority of an out-of-sample result while measuring
    something that is not running anywhere.
    """
    if not TRACKER_PY.exists():
        raise SystemExit(
            f"REFUSED: {TRACKER_PY} not found. The status rules live in the terminal repo "
            "and are imported, never retyped -- a second copy would drift and this test "
            "would stop testing what actually runs.")
    sha = hashlib.sha256(TRACKER_PY.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("_aat_tracker", TRACKER_PY)
    mod = importlib.util.module_from_spec(spec)
    # `alpha.tracker.consensus_score` delegates to `alpha.analyst_targets`; make
    # the terminal repo importable so that delegation resolves.
    if str(TERMINAL) not in sys.path:
        sys.path.insert(0, str(TERMINAL))
    # `@dataclass` resolves its own module's namespace through `sys.modules`, so
    # a module loaded by path must be registered there BEFORE it is executed --
    # otherwise the decorator dereferences None on the first dataclass it meets.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, sha


def assert_scale_conversion(T) -> None:
    """IBES 1=best -> tracker 5=best. Checked BEFORE anything is measured.

    If this is wrong every number downstream is a clean backtest of the
    opposite strategy, which is the failure that does not announce itself.
    """
    strong_buy_ibes, strong_sell_ibes = 1.0, 5.0
    assert 6.0 - strong_buy_ibes == 5.0, "IBES 1 (strong buy) must map to 5"
    assert 6.0 - strong_sell_ibes == 1.0, "IBES 5 (strong sell) must map to 1"
    # and the bar must select the bullish end on the converted scale
    assert (6.0 - strong_buy_ibes) >= T.BUY_CONSENSUS
    assert (6.0 - strong_sell_ibes) < T.SELL_CONSENSUS


# ----------------------------------------------------------------- the data

def load_names() -> pd.DataFrame:
    """permno <-> ncusip with validity dates, share code, exchange, SIC."""
    df = pd.read_parquet(BULK / "crsp__stocknames.parquet",
                         columns=["permno", "namedt", "nameenddt", "shrcd", "exchcd",
                                  "siccd", "ncusip"])
    df = df[df["ncusip"].notna() & (df["ncusip"] != "")]
    df = df[df["shrcd"].isin(SHRCD_COMMON) & df["exchcd"].isin(EXCHCD_MAIN)]
    for c in ("namedt", "nameenddt"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["sector"] = df["siccd"].map(sic_division)
    return df.dropna(subset=["namedt", "nameenddt"])


# ------------------------------------------------------- delisting returns

def delist_category(dlstcd) -> str:
    """`dlstcd` -> one of active / merger / liquidation / performance / other.

    Named categories rather than one range, because the categories have
    different means and pooling them is how -24.63% became -19.57%.
    """
    try:
        c = int(dlstcd)
    except (TypeError, ValueError):
        return "unknown"
    if c < 200:
        return "active"
    if DELIST_MERGER_RANGE[0] <= c <= DELIST_MERGER_RANGE[1]:
        return "merger_or_exchange"
    if DELIST_LIQUIDATION_RANGE[0] <= c <= DELIST_LIQUIDATION_RANGE[1]:
        return "liquidation"
    if c in DELIST_PERF_CODES or DELIST_PERF_RANGE[0] <= c <= DELIST_PERF_RANGE[1]:
        return "performance"
    return "other"


def resolve_delisting_return(d: pd.DataFrame) -> pd.DataFrame:
    """Add `dlret_used` / `dlret_source` / `dl_factor` to a delisting frame.

    Input columns: `category` (from `delist_category`), `dlret`, `hexcd`.
    Separated from `load_delistings` so the FILL RULE can be tested on a
    synthetic frame offline -- a fill that only runs against a 19k-row parquet
    is a fill nobody checks.

    The Shumway (1997) fill applies to PERFORMANCE codes only, and only where
    CRSP has no `dlret`: -30% on NYSE/AMEX (`hexcd` 1-2), -55% on NASDAQ
    (`hexcd` 3). A merger or a liquidation with no `dlret` gets NO fill -- a
    made-up number for a wind-up whose proceeds are unknown is a fabrication,
    and `dlret_source == "none"` says so in the census.
    """
    d = d.copy()
    d["dlret"] = pd.to_numeric(d["dlret"], errors="coerce")
    perf = d["category"] == "performance"
    missing = perf & d["dlret"].isna()
    # `hexcd` is CRSP's header exchange code on the delisting record itself and
    # uses the same 1=NYSE / 2=AMEX / 3=NASDAQ vocabulary as `exchcd`. Anything
    # else gets no fill rather than the wrong one.
    nasdaq = d["hexcd"] == 3
    nyse_amex = d["hexcd"].isin((1, 2))
    d["dlret_used"] = d["dlret"]
    d["dlret_source"] = np.where(d["dlret"].notna(), "crsp", "none")
    fill_na = missing & nyse_amex
    fill_nd = missing & nasdaq
    d.loc[fill_na, "dlret_used"] = SHUMWAY_FILL["NYSE_AMEX"]
    d.loc[fill_na, "dlret_source"] = "shumway_nyse_amex"
    d.loc[fill_nd, "dlret_used"] = SHUMWAY_FILL["NASDAQ"]
    d.loc[fill_nd, "dlret_source"] = "shumway_nasdaq"
    # A delisting return below -100% is not a return. CRSP does not emit one,
    # but a clip is cheaper than discovering a negative wealth factor later.
    d["dl_factor"] = (1.0 + d["dlret_used"].clip(lower=-1.0)).fillna(1.0)
    return d


def load_delistings() -> pd.DataFrame:
    """`crsp__dsedelist` with the delisting return resolved per permno.

    Columns: permno, dlstdt, dlstcd, category, dlret, dlret_used, dlret_source,
    dl_factor. `dlret_source` is one of `crsp` / `shumway_nyse_amex` /
    `shumway_nasdaq` / `none` -- so a receipt can say how many dead names were
    counted on a FILL rather than on a measurement.

    WHY THIS IS NEEDED AT ALL: `crsp.dsf.ret` is not delisting-inclusive.
    Measured 2026-09-04, 1,103 of the 1,114 events coded 400-591 in 2013-24 have
    a `dsf` bar on `dlstdt` and only FOUR carry `ret == dlret`.
    """
    d = pd.read_parquet(BULK / "crsp__dsedelist.parquet",
                        columns=["permno", "dlstdt", "dlstcd", "dlret", "hexcd"])
    d["dlstdt"] = pd.to_datetime(d["dlstdt"], errors="coerce")
    d = d[d["dlstdt"].notna()].copy()
    d["category"] = d["dlstcd"].map(delist_category)
    # `dlstcd` under 200 means the name was still trading; it is not a delisting
    # and must not be counted as one.
    d = d[d["category"] != "active"]
    d = resolve_delisting_return(d)
    # One row per permno: the LAST delisting event (CRSP normally has exactly
    # one; a permno with two is a reissue and the final one is what killed it).
    d = d.sort_values(["permno", "dlstdt"]).drop_duplicates("permno", keep="last")
    return d.reset_index(drop=True)


def delisting_factors(start: int | None = None,
                      end: int | None = None) -> tuple[pd.DataFrame, dict]:
    """(`load_delistings()` restricted to the window, census dict).

    The census is what goes in the receipt: events and mean `dlret` per
    category, plus how many performance events had to be Shumway-filled.
    """
    d = load_delistings()
    if start is not None:
        d = d[d["dlstdt"] >= pd.Timestamp(f"{start}-01-01")]
    if end is not None:
        d = d[d["dlstdt"] <= pd.Timestamp(f"{end}-12-31")]
    d = d.reset_index(drop=True)
    census: dict = {"window": [start, end], "events": int(len(d)), "by_category": {}}
    for cat, chunk in d.groupby("category"):
        census["by_category"][str(cat)] = {
            "events": int(len(chunk)),
            "with_crsp_dlret": int(chunk["dlret"].notna().sum()),
            "mean_dlret": (round(float(chunk["dlret"].mean()), 6)
                           if chunk["dlret"].notna().any() else None),
            "mean_dlret_used": round(float(chunk["dlret_used"].mean()), 6)
                               if chunk["dlret_used"].notna().any() else None,
        }
    census["shumway_filled"] = (
        d.loc[d["dlret_source"].str.startswith("shumway"), "dlret_source"]
        .value_counts().to_dict())
    census["performance_codes"] = {
        "definition": "dlstcd in {500} u [520, 584]",
        "why_not_400_591": ("400-591 counts liquidations (450) and administrative "
                            "codes and dilutes the mean from -24.63% to -19.57%"),
    }
    return d, census


def _filter_ptg(ptg: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """The universe filters both IBES summary files share. ONE definition."""
    ptg = ptg[(ptg["usfirm"] == 1) & (ptg["measure"] == "PTG")]
    ptg = ptg[ptg["curr"].isin(["USD"]) | ptg["curr"].isna()]
    ptg = ptg.copy()
    ptg["statpers"] = pd.to_datetime(ptg["statpers"])
    return ptg[(ptg["statpers"].dt.year >= start) & (ptg["statpers"].dt.year <= end)]


def load_ptg_adjusted(start: int, end: int) -> pd.DataFrame:
    """The SPLIT-ADJUSTED consensus, for the cross-check column ONLY.

    `meanptg_adj * cfacpr(t) / prc` should reproduce the PIT ratio and mostly
    does; it disagrees on ~7% of rows because `cfacpr(t)` is itself a future
    quantity. That is why the rescale is a DIAGNOSTIC and the unadjusted file is
    the source. Named `_ADJUSTED_PTG_FILE` rather than written as a literal so
    `test_ibes_target_share_basis` finds exactly one `BULK / "ibes__ptgsum*"`
    literal in each loader and cannot match the wrong one.
    """
    d = pd.read_parquet(BULK / _ADJUSTED_PTG_FILE,
                        columns=["cusip", "statpers", "meanptg", "usfirm",
                                 "measure", "curr"])
    d = _filter_ptg(d, start, end)
    return (d[["cusip", "statpers", "meanptg"]]
            .rename(columns={"meanptg": "meanptg_adj"})
            .drop_duplicates(["cusip", "statpers"]))


def load_ibes(start: int, end: int) -> pd.DataFrame:
    """Consensus targets joined to recommendation counts, monthly, US firms.

    `meanptg` is the UNADJUSTED consensus (`ibes__ptgsumu`) -- the target in the
    share terms that existed at `statpers`, which is the only basis on which
    `meanptg / prc` against a raw CRSP close is a ratio. `meanptg_adj` carries
    the split-adjusted number under a name that says what it is.
    """
    ptg = pd.read_parquet(BULK / "ibes__ptgsumu.parquet",
                          columns=["cusip", "statpers", "meanptg", "numest", "usfirm",
                                   "measure", "curr"])
    ptg = _filter_ptg(ptg, start, end)
    ptg = ptg.merge(load_ptg_adjusted(start, end), on=["cusip", "statpers"], how="left")

    rec = pd.read_parquet(BULK / "ibes__recdsum.parquet",
                          columns=["cusip", "statpers", "meanrec", "numrec", "usfirm"])
    rec = rec[rec["usfirm"] == 1]
    rec["statpers"] = pd.to_datetime(rec["statpers"])
    rec = rec[(rec["statpers"].dt.year >= start) & (rec["statpers"].dt.year <= end)]

    df = ptg.merge(rec, on=["cusip", "statpers"], how="inner", suffixes=("", "_r"))
    df = df[df["meanptg"].notna() & (df["meanptg"] > 0) & df["meanrec"].notna()]
    # THE CONVERSION. IBES 1 = strong buy; the tracker's scale is 5 = strong buy.
    df["consensus"] = 6.0 - df["meanrec"]
    df["coverage"] = df["numrec"].fillna(0).astype(int)
    return df[["cusip", "statpers", "meanptg", "meanptg_adj", "numest",
               "consensus", "coverage"]]


_VOLUME_UNITS: dict = {"read_as": "not checked"}


def load_prices(start: int, end: int) -> pd.DataFrame:
    """Daily CRSP closes, one year per file. `prc` is negated for bid/ask means."""
    frames = []
    for year in range(start - 1, end + 1):        # one extra year for ret_12m
        f = WRDS / f"crsp_dsf_{year}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["permno", "date", "prc", "ret", "cfacpr", "vol"])
        frames.append(d)
    if not frames:
        raise SystemExit("REFUSED: no CRSP daily files found for that range.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    # A NEGATIVE `prc` is CRSP's flag for "no trade; this is the bid/ask
    # average". It is a real price estimate and dropping it would delete
    # exactly the illiquid names Murat wants in the universe, so take abs()
    # and keep the row -- and never let the sign reach a return calculation.
    px["prc"] = px["prc"].abs()
    px = px[px["prc"].notna() & (px["prc"] > 0)]
    px["ret"] = pd.to_numeric(px["ret"], errors="coerce")
    # SPLIT ADJUSTMENT, and why the first version of this file was wrong.
    #
    # Every price-derived quantity must be adjusted. Run on RAW `prc`, a 1-for-10
    # REVERSE split reads as +900% and a 2-for-1 forward split reads as -50%:
    # the upside is unbounded and the downside floors at -100%, so the asymmetry
    # biases every cross-sectional mean upward. It is not a small effect in this
    # universe -- reverse splits are common in exactly the thin, beaten-down
    # names the screen selects. The first run of this script reported a 42% CAGR
    # "equal weighted market" and an 831x basket, both of which were that
    # artefact and neither of which is a return anyone could have earned.
    #
    # `cfacpr` is CRSP's cumulative price adjustment factor: `prc / cfacpr` is a
    # split-consistent series. `ret` is CRSP's own total return, already net of
    # splits and inclusive of dividends, so REALISED performance is compounded
    # from `ret` and never from a price ratio.
    #
    # `ret` does NOT carry the DELISTING return. This comment used to say "and
    # of the delisting return where one exists", which is a hedge that reads as
    # a reassurance: measured 2026-09-04, 1,103 of the 1,114 events coded
    # 400-591 in 2013-24 have a bar on `dlstdt` and exactly FOUR of them carry
    # `ret == dlret` (mean `dsf.ret` -9.2% vs mean `dlret` -19.6%). The wind-up
    # comes from `crsp__dsedelist` and is applied by `delisting_factors()`.
    cf = px["cfacpr"].where(px["cfacpr"].notna() & (px["cfacpr"] != 0), 1.0)
    px["adj_prc"] = px["prc"] / cf
    return px.sort_values(["permno", "date"])


def price_panel(px: pd.DataFrame) -> pd.DataFrame:
    """Per (permno, date): raw close, adjusted 60-session high, 12m total return.

    `prc` stays RAW because `load_ibes` now reads the UNADJUSTED IBES summary
    (`ibes__ptgsumu`), whose `meanptg` is quoted in the share terms that existed
    at `statpers` -- so `meanptg / prc` is the ratio a desk would actually have
    seen that morning, both legs on ONE basis.

    The premise this docstring used to state -- "the analyst target is quoted in
    today's dollars" -- was FALSE for the file it was reading: `ibes__ptgsum` is
    split-ADJUSTED, restated in end-of-sample share terms, so the old ratio was
    `true_ratio / cfacpr(t)` and a future reverse split inflated it. That is the
    defect in `docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` §2, and it is why the
    file name matters more than the comment.

    Everything that compares a price to its own past -- the 60-day high, the
    twelve-month return -- uses the ADJUSTED series, and realised performance
    uses the total-return index.
    """
    px = px.copy()
    g = px.groupby("permno", sort=False)
    px["high_60d"] = g["adj_prc"].transform(lambda s: s.rolling(60, min_periods=20).max())
    px["adj_252"] = g["adj_prc"].transform(lambda s: s.shift(252))
    px["ret_12m"] = px["adj_prc"] / px["adj_252"] - 1.0
    # Total-return index: dividends in, splits out. THE DELISTING RETURN IS NOT
    # IN HERE -- `dsf.ret` does not carry it (see `load_prices`). This script's
    # monthly `fwd_1m` needs a NEXT monthly row for the same permno, so a name's
    # final, dying month is DROPPED rather than mis-measured; that is a known
    # limitation of this script and the reason `learner/dataset.py` -- which owns
    # the panel every claim is now measured on -- compounds
    # `delisting_factors()` into the final index value instead.
    px["tri"] = g["ret"].transform(lambda s: (1.0 + s.fillna(0.0)).cumprod())
    # Did the share basis change in the prior year? `cfacpr` moves only on a
    # split or similar adjustment. A stale IBES target across such a change
    # makes `meanptg / prc` meaningless, so the share of affected rows is
    # reported beside every upside band rather than cleaned out of it.
    cf252 = g["cfacpr"].transform(lambda s: s.shift(252))
    px["split_prior_year"] = (px["cfacpr"] != cf252) & cf252.notna()
    # CAPACITY. A cost assumption in basis points answers "what does the spread
    # take?"; it does not answer "could this position have been opened at all?".
    # Those are different questions and a thin-coverage result needs both,
    # because the names with one analyst are also the names with no volume.
    #
    # CRSP `vol` on the daily file is SHARES for the modern era (it was round
    # lots on the very old tapes, before this window). `assert_volume_units`
    # checks the magnitude against a mega-cap rather than trusting the doc.
    px["dollar_vol"] = px["vol"] * px["prc"]
    px["dollar_vol_20d"] = g["dollar_vol"].transform(
        lambda s: s.rolling(20, min_periods=5).median())
    return px


# ------------------------------------------------------------------ the run

def assert_volume_units(px: "pd.DataFrame") -> dict:
    """CRSP `vol` is shares or round lots depending on the era, and the whole
    capacity split is off by 100x if that is assumed rather than checked.

    The check is a magnitude one: over 2013-2024 the busiest name-days in the
    universe are mega-caps trading tens of millions of shares. If the median of
    the top 100 daily volumes lands near 1e6 instead, the file is in round lots
    and every dollar-volume number below is 100x too small.
    """
    top = px["vol"].dropna().nlargest(100)
    med = float(top.median()) if len(top) else 0.0
    unit = "shares" if med > 5e6 else "ROUND LOTS OR UNKNOWN"
    out = {"median_of_top_100_daily_vol": round(med, 1), "read_as": unit}
    print(f"  volume units: median of the 100 busiest name-days = {med:,.0f} -> {unit}")
    if unit != "shares":
        print("  WARNING: dollar-volume buckets below are NOT trustworthy at this scale.")
    return out


def build_monthly(start: int, end: int, lag_days: int) -> pd.DataFrame:
    """One row per (name, month) with every column the status rules read."""
    names = load_names()
    ibes = load_ibes(start, end)
    print(f"  IBES rows with BOTH a target and a rating: {len(ibes):,}")

    # cusip -> permno, valid AT statpers (a cusip is reassigned over time)
    ibes = ibes.merge(names[["permno", "ncusip", "namedt", "nameenddt", "sector"]],
                      left_on="cusip", right_on="ncusip", how="inner")
    ibes = ibes[(ibes["statpers"] >= ibes["namedt"]) & (ibes["statpers"] <= ibes["nameenddt"])]
    print(f"  linked to a CRSP common-stock permno valid that month: {len(ibes):,}")

    px = price_panel(load_prices(start, end))
    print(f"  CRSP daily rows: {len(px):,}")
    global _VOLUME_UNITS
    _VOLUME_UNITS = assert_volume_units(px)

    # PIT: trade at the first close STRICTLY AFTER statpers + lag. The IBES cut
    # is dated statpers but is not on a desk that morning; using statpers itself
    # would buy at a price set before the number existed.
    ibes = ibes.sort_values("statpers")
    ibes["tradable_from"] = ibes["statpers"] + pd.Timedelta(days=lag_days)
    px = px.sort_values("date")
    merged = pd.merge_asof(
        ibes, px[["permno", "date", "prc", "adj_prc", "high_60d", "ret_12m", "tri",
                  "split_prior_year", "dollar_vol_20d"]],
        left_on="tradable_from", right_on="date", by="permno",
        direction="forward", tolerance=pd.Timedelta(days=7))
    merged = merged[merged["prc"].notna()]
    print(f"  with a tradable close within 7 days of the cut: {len(merged):,}")

    # forward one-month return: the next month's entry price for the same name
    merged = merged.sort_values(["permno", "statpers"])
    merged["tri_next"] = merged.groupby("permno", sort=False)["tri"].shift(-1)
    merged["statpers_next"] = merged.groupby("permno", sort=False)["statpers"].shift(-1)
    gap = (merged["statpers_next"] - merged["statpers"]).dt.days
    # A gap far from one month is a name that left the panel and came back; its
    # "one-month" return would silently be a one-year return.
    merged = merged[(gap >= 20) & (gap <= 45)]
    # From the TOTAL RETURN INDEX, never from a price ratio: splits out,
    # dividends in. The DELISTING return is not in `dsf.ret` and a dying name
    # has no next monthly row, so its final month is absent here rather than
    # flattered -- `learner/dataset.py` is where the wind-up is compounded in.
    merged["fwd_1m"] = merged["tri_next"] / merged["tri"] - 1.0
    merged = merged[merged["fwd_1m"].notna()]
    merged["month"] = merged["statpers"].dt.to_period("M").astype(str)
    print(f"  with a forward one-month return: {len(merged):,}")
    return merged


def label(df: pd.DataFrame, T) -> pd.DataFrame:
    """Apply the IMPORTED status rules, month by month, cross-sectionally."""
    out = []
    for month, chunk in df.groupby("month", sort=True):
        rows = [{
            "symbol": int(r.permno), "close": float(r.prc),
            "adj_close": float(r.adj_prc),
            "high_60d": float(r.high_60d) if pd.notna(r.high_60d) else None,
            "ret_12m": float(r.ret_12m) if pd.notna(r.ret_12m) else None,
            "sector": r.sector,
            "mean_target": float(r.meanptg),
            "consensus": float(r.consensus),
            "coverage": int(r.coverage),
            # IBES carries no event calendar: clause (d) is UNREADABLE, not
            # failed. STRONG_BUY asserts a catalyst so it cannot fire here.
            "days_to_catalyst": None,
            "tradable": True,
            "fwd_1m": float(r.fwd_1m), "month": month,
            "split_prior_year": bool(r.split_prior_year),
            "dollar_vol_20d": (float(r.dollar_vol_20d)
                               if pd.notna(r.dollar_vol_20d) else None),
        } for r in chunk.itertuples()]
        for row in rows:
            row["upside"] = T.upside(row["mean_target"], row["close"])
            # drawdown compares a price to its OWN past: both legs adjusted.
            row["drawdown_60d"] = T.drawdown_60d(row["adj_close"], row["high_60d"])
            row["coverage_bucket"] = T.coverage_bucket(row["coverage"])
        T.mark_past_winners(rows)             # per-month cross-section, never pooled
        T.apply_status(rows)                  # no `prev`: HOLD needs history, BUY does not
        out.extend(rows)
    return pd.DataFrame(out)


def wealth(monthly_returns: pd.Series) -> dict:
    r = monthly_returns.dropna()
    if r.empty:
        return {"months": 0}
    terminal = float((1.0 + r).prod())
    yrs = len(r) / 12.0
    return {
        "months": int(len(r)),
        "terminal_wealth": round(terminal, 4),
        "cagr": round(terminal ** (1 / yrs) - 1.0, 4) if yrs > 0 and terminal > 0 else None,
        "mean_monthly": round(float(r.mean()), 5),
        "vol_monthly": round(float(r.std()), 5),
        "hit_rate": round(float((r > 0).mean()), 4),
        "worst_month": round(float(r.min()), 4),
        "t_stat": (round(float(r.mean() / (r.std() / np.sqrt(len(r)))), 3)
                   if r.std() > 0 else None),
    }


def basket(df: pd.DataFrame, mask: pd.Series, cost_bps: float) -> dict:
    """Equal-weighted monthly basket over the masked names, net of turnover cost."""
    sel = df[mask]
    if sel.empty:
        return {"months": 0, "note": "no names ever selected"}
    per_month = sel.groupby("month")["fwd_1m"].mean()
    holdings = sel.groupby("month")["symbol"].apply(set)

    # TURNOVER, MEASURED. A monthly basket that keeps most of its names does not
    # pay a full round trip; asserting 100% turnover would overstate the cost as
    # badly as asserting zero would understate it.
    turnovers, prev = [], None
    for m in holdings.index:
        cur = holdings.loc[m]
        turnovers.append(1.0 if prev is None
                         else len(cur - prev) / max(1, len(cur)))
        prev = cur
    turnover = pd.Series(turnovers, index=holdings.index)
    cost = turnover * (cost_bps / 10_000.0) * 2.0        # both sides
    net = per_month - cost.reindex(per_month.index).fillna(0.0)

    out = wealth(net)
    out["gross"] = wealth(per_month)
    out["mean_names_per_month"] = round(float(sel.groupby("month").size().mean()), 1)
    out["mean_turnover"] = round(float(turnover.mean()), 3)
    out["cost_bps_per_side"] = cost_bps
    return out


def paired_vs_market(df: pd.DataFrame, mask: pd.Series, market: pd.Series,
                     cost_bps: float) -> dict:
    """The DECISIVE test: the monthly spread (basket - market), paired by month.

    Comparing two terminal wealths is not a test -- both are one draw of a
    correlated pair, and the market's own t over this window is only 1.7. The
    paired difference removes the shared market factor and asks the question
    that actually matters: better than WHAT, month by month.
    """
    sel = df[mask]
    if sel.empty:
        return {"months": 0}
    per_month = sel.groupby("month")["fwd_1m"].mean()
    holdings = sel.groupby("month")["symbol"].apply(set)
    turnovers, prev = [], None
    for m in holdings.index:
        cur = holdings.loc[m]
        turnovers.append(1.0 if prev is None else len(cur - prev) / max(1, len(cur)))
        prev = cur
    cost = pd.Series(turnovers, index=holdings.index) * (cost_bps / 10_000.0) * 2.0
    net = per_month - cost.reindex(per_month.index).fillna(0.0)
    spread = (net - market.reindex(net.index)).dropna()
    if spread.empty:
        return {"months": 0}
    t = float(spread.mean() / (spread.std() / np.sqrt(len(spread)))) if spread.std() > 0 else None
    return {
        "months": int(len(spread)),
        "mean_monthly_excess": round(float(spread.mean()), 5),
        "annualised_excess": round(float(spread.mean()) * 12, 4),
        "t_stat_paired": round(t, 3) if t is not None else None,
        "months_beating_market": round(float((spread > 0).mean()), 4),
    }


def quintile_shape(df: pd.DataFrame, column: str, market: pd.Series,
                   cost_bps: float, n_bins: int = 5) -> dict:
    """Sort the WHOLE universe by one column each month and grade every bin.

    ASK THE CROSS SECTION FIRST. A rule that takes the top of a column is only
    sensible if that column is monotone in the right direction. If the bottom
    bin beats the top, the screen is inverted and no threshold on it can help;
    if the shape is flat, the column carries nothing and the threshold is
    ceremony. Bins are cut PER MONTH -- a full-sample quantile would be
    lookahead.
    """
    d = df[df[column].notna()].copy()
    if d.empty:
        return {}
    d["_bin"] = d.groupby("month")[column].transform(
        lambda s: pd.qcut(s.rank(method="first"), n_bins, labels=False, duplicates="drop"))
    out = {}
    for b in sorted(x for x in d["_bin"].dropna().unique()):
        m = d["_bin"] == b
        sub = d[m]
        per_month = sub.groupby("month")["fwd_1m"].mean()
        spread = (per_month - market.reindex(per_month.index)).dropna()
        t = (float(spread.mean() / (spread.std() / np.sqrt(len(spread))))
             if len(spread) > 1 and spread.std() > 0 else None)
        out[f"Q{int(b)+1}"] = {
            "mean_value": round(float(sub[column].mean()), 4),
            "name_months": int(m.sum()),
            "gross_wealth": wealth(per_month).get("terminal_wealth"),
            "annualised_excess_vs_market": round(float(spread.mean()) * 12, 4),
            "t_stat_paired": round(t, 3) if t is not None else None,
        }
    return out


#: Absolute upside bands. Quintiles say WHERE the top of the column is; these
#: say what the LIVE BAR actually buys. `BUY_UPSIDE` is 0.30 and
#: `STRONG_BUY_UPSIDE` is 0.50, so the rule lives entirely inside the last four
#: bands and the question is which of them carry the damage.
UPSIDE_BANDS = ((-9.9, 0.0), (0.0, 0.15), (0.15, 0.30), (0.30, 0.50),
                (0.50, 1.00), (1.00, 2.00), (2.00, 4.00), (4.00, 1e9))


def upside_bands(df: pd.DataFrame, market: pd.Series) -> dict:
    """Grade every absolute upside band against the market, paired by month.

    WHY THIS AND NOT ONLY QUINTILES. A quintile is relative -- "the top 20% of
    whatever was on offer that month" -- and it moves as the market's optimism
    moves. The rule is written in ABSOLUTE terms (`upside >= 0.30`), so the
    only cut that tells us what the rule buys is an absolute one.

    THE SPLIT CAVEAT, WHICH THIS CANNOT FULLY REMOVE. `meanptg` is a consensus
    target in the dollars of whenever it was set; `prc` is today's raw price.
    If a split falls between the two, the ratio is meaningless -- a 1-for-10
    reverse split leaves a stale target a tenth of the new price, and a forward
    split leaves it a multiple. Those land in the extreme bands. So a band is
    reported with the SHARE of its rows that saw a split in the prior year,
    which is what separates "the rule buys bad names" from "the rule buys a
    measurement error". Flagged and counted, never dropped.
    """
    out = {}
    for lo, hi in UPSIDE_BANDS:
        m = (df["upside"] >= lo) & (df["upside"] < hi)
        sub = df[m]
        if len(sub) < 500:
            continue
        per_month = sub.groupby("month")["fwd_1m"].mean()
        spread = (per_month - market.reindex(per_month.index)).dropna()
        if len(spread) < 12:
            continue
        t = (float(spread.mean() / (spread.std() / np.sqrt(len(spread))))
             if spread.std() > 0 else None)
        label_ = f"{lo:+.0%} to {hi:+.0%}" if hi < 1e8 else f"{lo:+.0%}+"
        out[label_] = {
            "name_months": int(m.sum()),
            "median_upside": round(float(sub["upside"].median()), 4),
            "annualised_excess_vs_market": round(float(spread.mean()) * 12, 4),
            "t_stat_paired": round(t, 3) if t is not None else None,
            "months_beating_market": round(float((spread > 0).mean()), 4),
            "split_in_prior_year_share": (round(float(sub["split_prior_year"].mean()), 4)
                                          if "split_prior_year" in sub else None),
        }
    return out


def run(start: int, end: int, cost_bps: float, lag_days: int) -> int:
    T, sha = load_tracker_rules()
    assert_scale_conversion(T)
    print(f"rules: {TRACKER_PY} sha256 {sha[:16]}")
    print(f"  BUY bar: upside >= {T.BUY_UPSIDE:.0%}, consensus >= {T.BUY_CONSENSUS} "
          f"(IBES meanrec <= {6 - T.BUY_CONSENSUS:.1f}), upside < "
          f"{T.UPSIDE_IMPLAUSIBLE_AT:.0f}x")
    print("  clause (f) is NOT in the status any more -- it is a per-book preference, "
          "so both arms are graded below. By book: "
          + ", ".join(f"{x.book}={x.exclude_past_winners}" for x in T.PERSONALITIES))

    print(f"\nbuilding the monthly panel {start}-{end} ...")
    panel = build_monthly(start, end, lag_days)
    print("\nlabelling with the imported rules ...")
    lab = label(panel, T)
    print(f"  {len(lab):,} name-months labelled")

    hist = lab["status"].value_counts().to_dict()
    print(f"  statuses: {hist}")

    market = lab.groupby("month")["fwd_1m"].mean()
    # THE TWO ARMS, named for the books that run them. Since 2026-08-30 (e) the
    # tracker STATUS no longer applies clause (f) -- it is a per-book preference
    # -- so `is_cand` is the hack4/hack6 universe and `is_cand_f` is hack3's.
    # Everything below that says "BUY basket" means the status, i.e. the arm two
    # of the three books actually trade.
    is_cand = lab["status"].isin(T.CANDIDATE_STATUSES)
    is_cand_f = is_cand & (lab["past_winner"] == False)          # noqa: E712

    report = {
        "generated": date.today().isoformat(),
        "window": f"{start}-{end}", "cost_bps_per_side": cost_bps,
        "ibes_lag_days": lag_days,
        "tracker_py_sha256": sha,
        "thresholds": {"BUY_UPSIDE": T.BUY_UPSIDE, "BUY_CONSENSUS": T.BUY_CONSENSUS,
                       "PAST_WINNER_ABSOLUTE_RETURN": T.PAST_WINNER_ABSOLUTE_RETURN,
                       "PAST_WINNER_SECTOR_DECILE": T.PAST_WINNER_SECTOR_DECILE},
        "strong_buy_testable": False,
        "strong_buy_note": ("IBES carries no event calendar, so clause (d) is UNREADABLE and "
                            "STRONG_BUY -- which asserts a dated catalyst -- cannot fire. What "
                            "is tested below is the BUY bar, which has no catalyst clause."),
        "name_months": int(len(lab)),
        "status_histogram": {k: int(v) for k, v in hist.items()},
        "market_equal_weighted": wealth(market),
        "buy_basket": basket(lab, is_cand, cost_bps),
    }

    # -- Murat's hypothesis 1: does thin coverage behave differently? ------
    by_cov = {}
    for b in [x[0] for x in T.COVERAGE_BUCKETS]:
        m = is_cand & (lab["coverage_bucket"] == b)
        if m.sum() == 0:
            continue
        by_cov[b] = basket(lab, m, cost_bps)
        by_cov[b]["name_months"] = int(m.sum())
    report["buy_basket_by_coverage_bucket"] = by_cov

    # -- Murat's hypothesis 2: is excluding past winners the right call? ---
    # ONE CHANGE AT A TIME. Both arms carry the same upside cap and the same
    # status; the ONLY difference between them is `past_winner`, so the
    # comparison cannot hand the cap's benefit to the exclusion.
    #
    # The naming is the BOOKS' naming, because the code and the receipt have to
    # agree about which arm is live: `buy_with_clause_f` is hack3, `buy_basket`
    # (the status itself) is what hack4 and hack6 trade.
    report["arm_definitions"] = {
        "buy_basket": "tracker status in (BUY, STRONG_BUY). Clause (f) NOT applied. "
                      "This is the hack4 / hack6 universe, and it is what the previous "
                      "receipt called `buy_without_clause_f`.",
        "buy_with_clause_f": "the same, minus every name flagged `past_winner`. "
                             "This is hack3's universe, and it is what the previous "
                             "receipt called `buy_basket`.",
        "past_winners_only": "the names clause (f) throws away, on their own.",
    }
    report["buy_with_clause_f"] = basket(lab, is_cand_f, cost_bps)
    report["past_winners_only"] = basket(
        lab, is_cand & (lab["past_winner"] == True), cost_bps)          # noqa: E712
    # kept under the old key so a reader of the previous receipt can line the
    # two up rather than silently comparing different things.
    report["buy_without_clause_f"] = report["buy_basket"]
    # THE DECISIVE TESTS -- paired, and the cross-sectional shape.
    report["paired_vs_market"] = {
        "buy_basket": paired_vs_market(lab, is_cand, market, cost_bps),
        "buy_with_clause_f": paired_vs_market(lab, is_cand_f, market, cost_bps),
        "past_winners_only": paired_vs_market(
            lab, is_cand & (lab["past_winner"] == True), market, cost_bps),  # noqa: E712
        "note": ("terminal wealth alone compares two correlated single draws; the market's own "
                 "t over this window is 1.72. The paired monthly spread removes the shared "
                 "market factor and is the number that decides."),
    }
    report["cross_section_shape"] = {
        "upside": quintile_shape(lab, "upside", market, cost_bps),
        "consensus": quintile_shape(lab, "consensus", market, cost_bps),
        "ret_12m": quintile_shape(lab, "ret_12m", market, cost_bps),
        "note": ("every name sorted into per-month quintiles by one column, each bin graded "
                 "against the market. A threshold on a column is only sensible if the column "
                 "is monotone in the direction the rule assumes."),
    }
    # THE VARIANT THE BANDS POINT AT. `UPSIDE_IMPLAUSIBLE_AT` already exists in
    # the tracker as a FLAG; the bands say whether it should also be a BAR.
    lab["year_tmp"] = lab["month"].str[:4].astype(int)
    capped = is_cand & (lab["upside"] < T.UPSIDE_IMPLAUSIBLE_AT)
    report["buy_basket_with_upside_cap"] = basket(lab, capped, cost_bps)
    report["paired_buy_with_upside_cap"] = paired_vs_market(lab, capped, market, cost_bps)
    report["upside_cap_used"] = T.UPSIDE_IMPLAUSIBLE_AT
    report["excluded_by_cap_name_months"] = int((is_cand & ~capped).sum())
    # IS THE CAP A PLATEAU OR A KNIFE EDGE? A threshold that only works at one
    # value is a fitted parameter wearing a rule's clothes. `UPSIDE_IMPLAUSIBLE_AT`
    # was in the code BEFORE this data was looked at, which is the honest defence
    # of the level -- but the sensitivity is what shows whether the level matters.
    report["upside_cap_sensitivity"] = {}
    for cap in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 10.0, 100.0):
        m = is_cand & (lab["upside"] < cap)
        if m.sum() < 1000:
            continue
        report["upside_cap_sensitivity"][f"<{cap:g}x"] = {
            "name_months": int(m.sum()),
            **paired_vs_market(lab, m, market, cost_bps)}
    # and the capped rule, era by era, never pooled
    report["capped_by_era"] = {}
    for lo, hi in ((2013, 2016), (2017, 2020), (2021, 2024)):
        m = capped & lab["year_tmp"].between(lo, hi) if "year_tmp" in lab else None
        if m is None:
            continue
        if m.sum() == 0:
            continue
        report["capped_by_era"][f"{lo}-{hi}"] = paired_vs_market(lab, m, market, cost_bps)
    # ---------------------------------------------------------------------
    # THE COST QUESTION. 10 bps a side is a fair number for a liquid name and
    # an optimistic one for a stock four analysts follow -- and the whole
    # thin-coverage result lives in exactly those names. A finding that only
    # survives at a cost we would not actually pay is not a finding, so the
    # rule is re-graded on a grid and every bucket reports where it dies.
    #
    # The market leg stays GROSS in the paired spread. That is deliberate and
    # conservative in the honest direction: it charges the basket for its
    # turnover and gives the benchmark its turnover free, so the spread below
    # UNDERSTATES the strategy rather than flattering it.
    report["cost_sensitivity"] = {}
    for bps in (10.0, 25.0, 50.0, 100.0):
        entry = {"all_candidates": {
            "wealth": basket(lab, is_cand, bps).get("terminal_wealth"),
            "cagr": basket(lab, is_cand, bps).get("cagr"),
            **paired_vs_market(lab, is_cand, market, bps)},
            "with_clause_f": {
                "wealth": basket(lab, is_cand_f, bps).get("terminal_wealth"),
                "cagr": basket(lab, is_cand_f, bps).get("cagr"),
                **paired_vs_market(lab, is_cand_f, market, bps)}}
        by_b = {}
        for b in [x[0] for x in T.COVERAGE_BUCKETS]:
            m = is_cand & (lab["coverage_bucket"] == b)
            if m.sum() == 0:
                continue
            bk = basket(lab, m, bps)
            by_b[b] = {"name_months": int(m.sum()),
                       "wealth": bk.get("terminal_wealth"), "cagr": bk.get("cagr"),
                       "mean_turnover": bk.get("mean_turnover"),
                       **paired_vs_market(lab, m, market, bps)}
        entry["by_coverage_bucket"] = by_b
        report["cost_sensitivity"][f"{bps:g}bps_per_side"] = entry
    report["cost_sensitivity_note"] = (
        "the SAME capped BUY rule, re-graded at four cost levels. 10bps is the headline "
        "number and is optimistic for the thin buckets; 25-50bps is a fairer read on a "
        "name four analysts follow. A bucket whose paired t crosses zero between two "
        "columns is a bucket whose edge is the spread, not the screen.")

    # CAPACITY, which basis points do not answer. A 1-3-analyst edge that lives
    # entirely in names trading $200k a day is not an edge this book can take.
    report["volume_units"] = _VOLUME_UNITS
    dv = lab["dollar_vol_20d"]
    report["capacity"] = {"n_with_dollar_volume": int(dv.notna().sum()),
                          "n_without": int(dv.isna().sum()),
                          "note": ("20-session median dollar volume at entry, in the dollars of "
                                   "the day -- NOT inflation-adjusted, so the early years look "
                                   "thinner than they traded. Bands are absolute on purpose: a "
                                   "per-month quantile would call the thinnest decile of 2013 "
                                   "'liquid' merely because everything around it was thinner.")}
    BANDS = ((0, 1e5, "<$100k/day"), (1e5, 1e6, "$100k-1m"), (1e6, 1e7, "$1m-10m"),
             (1e7, 1e8, "$10m-100m"), (1e8, float("inf"), ">$100m"))
    report["capacity"]["bands"] = {}
    for lo, hi, lbl in BANDS:
        m = is_cand & dv.notna() & (dv >= lo) & (dv < hi)
        if m.sum() < 200:
            report["capacity"]["bands"][lbl] = {"name_months": int(m.sum()),
                                                "note": "too few to grade"}
            continue
        report["capacity"]["bands"][lbl] = {
            "name_months": int(m.sum()),
            "wealth": basket(lab, m, 25.0).get("terminal_wealth"),
            **paired_vs_market(lab, m, market, 25.0)}
    # and the cross of the two questions: is the thin-coverage edge only in the
    # names nobody can buy? This is the one table that answers Murat directly.
    report["capacity"]["thin_coverage_by_liquidity_at_25bps"] = {}
    for b in ("1-3", "4-10"):
        row = {}
        for lo, hi, lbl in BANDS:
            m = (is_cand & (lab["coverage_bucket"] == b) & dv.notna()
                 & (dv >= lo) & (dv < hi))
            if m.sum() < 200:
                row[lbl] = {"name_months": int(m.sum()), "note": "too few to grade"}
                continue
            row[lbl] = {"name_months": int(m.sum()),
                        "wealth": basket(lab, m, 25.0).get("terminal_wealth"),
                        **paired_vs_market(lab, m, market, 25.0)}
        report["capacity"]["thin_coverage_by_liquidity_at_25bps"][b] = row

    # DOES CONCENTRATION HELP? The basket above holds every candidate -- ~416
    # names. The live books hold 5 to 15. That is a different portfolio and it
    # has to be tested as one: the farm's standing result is that breadth raised
    # terminal wealth in EVERY row and that concentration is a return decision,
    # not a risk preference. Top-k is taken by upside, the only ranking that
    # exists in both this panel and the live book.
    report["top_k_by_upside"] = {}
    ranked = lab[capped].copy()
    ranked["rk"] = ranked.groupby("month")["upside"].rank(ascending=False, method="first")
    for k in (5, 10, 15, 25, 50, 100, 250):
        idx = ranked[ranked["rk"] <= k].index
        m = pd.Series(False, index=lab.index)
        m.loc[idx] = True
        if m.sum() < 200:
            continue
        report["top_k_by_upside"][f"top{k}"] = {
            "name_months": int(m.sum()),
            "wealth": basket(lab, m, cost_bps).get("terminal_wealth"),
            **paired_vs_market(lab, m, market, cost_bps)}
    report["upside_bands"] = upside_bands(lab, market)
    report["upside_bands_note"] = (
        "the quintiles say where the top of the column is; these say what the LIVE BAR buys. "
        f"BUY_UPSIDE is {T.BUY_UPSIDE:.0%} and STRONG_BUY_UPSIDE is {T.STRONG_BUY_UPSIDE:.0%}, "
        "so the rule lives entirely in the upper bands. `split_in_prior_year_share` separates "
        "'the rule buys bad names' from 'the rule buys a stale target across a split'.")
    report["buy_basket_note"] = (
        "`buy_basket` is the tracker status and does NOT apply clause (f) (hack4/hack6); "
        "`buy_with_clause_f` is the same screen minus past winners (hack3). "
        "The DIFFERENCE between them is what clause (f) bought "
        "or cost -- which is the only way to answer 'do not buy last year's winner' rather "
        "than assume it.")

    # -- by decade / era, never pooled ------------------------------------
    lab["year"] = lab["month"].str[:4].astype(int)
    eras = {}
    for lo, hi in ((2013, 2016), (2017, 2020), (2021, 2024)):
        m = is_cand & lab["year"].between(lo, hi)
        em = lab["year"].between(lo, hi)
        if m.sum() == 0:
            continue
        eras[f"{lo}-{hi}"] = {"buy": basket(lab, m, cost_bps),
                              "market": wealth(lab[em].groupby("month")["fwd_1m"].mean())}
    report["by_era"] = eras

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ibes_status_rules_{start}_{end}.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    _print(report)
    print(f"\nreceipt -> {path}")
    return 0


def _print(rep: dict) -> None:
    def line(name, d):
        if not d or not d.get("months"):
            print(f"  {name:28s} -- no months --")
            return
        print(f"  {name:28s} wealth {d['terminal_wealth']:>8.3f}  CAGR "
              f"{(d['cagr'] or 0):>7.2%}  hit {d['hit_rate']:>5.1%}  t {str(d['t_stat']):>7s}  "
              f"n/mo {d.get('mean_names_per_month','--')}")

    print("\n" + "=" * 78)
    print(f"TRACKER STATUS RULES ON IBES + CRSP, {rep['window']}, "
          f"costs {rep['cost_bps_per_side']}bps/side")
    print("=" * 78)
    print(f"{rep['name_months']:,} name-months. STRONG_BUY not testable here "
          f"(no event calendar).")
    print("\nHEADLINE")
    line("market (equal weighted)", rep["market_equal_weighted"])
    line("BUY basket (net)", rep["buy_basket"])
    if "cost_sensitivity" in rep:
        print("\nCOST -- the same capped rule at four cost levels (paired excess/yr, t)")
        cols = list(rep["cost_sensitivity"].keys())
        buckets = sorted({b for c in cols
                          for b in rep["cost_sensitivity"][c]["by_coverage_bucket"]})
        head = "  " + "coverage".ljust(10) + "".join(c.replace("_per_side", "").rjust(18)
                                                     for c in cols)
        print(head)
        for b in ["ALL", "ALL+f"] + buckets:
            cells = []
            for c in cols:
                cs = rep["cost_sensitivity"][c]
                d = (cs["all_candidates"] if b == "ALL"
                     else cs.get("with_clause_f", {}) if b == "ALL+f"
                     else cs["by_coverage_bucket"].get(b, {}))
                if not d or d.get("annualised_excess") is None:
                    cells.append("--".rjust(18))
                else:
                    cells.append(f"{d['annualised_excess']:+7.2%} t{d['t_stat_paired']:+5.2f}"
                                 .rjust(18))
            print("  " + b.ljust(10) + "".join(cells))
    if "capacity" in rep:
        print("\nCAPACITY -- can the thin names actually be bought? (25bps/side)")
        for lbl, d in rep["capacity"].get("bands", {}).items():
            if d.get("note"):
                print(f"  {lbl:14} {d['name_months']:>7,} name-months  {d['note']}")
            else:
                print(f"  {lbl:14} {d['name_months']:>7,} name-months  "
                      f"{d['annualised_excess']:+7.2%}/yr  t {d['t_stat_paired']:+5.2f}")

    print("\nHYPOTHESIS 1 -- does thin coverage behave differently?")
    for b, d in rep["buy_basket_by_coverage_bucket"].items():
        line(f"  coverage {b}", d)
    print("\nHYPOTHESIS 2 -- is 'do not buy the past winner' right?")
    line("BUY without clause (f)  [hack4/hack6]", rep["buy_basket"])
    line("BUY with clause (f)     [hack3]", rep["buy_with_clause_f"])
    line("past winners only", rep["past_winners_only"])
    print("\nBY ERA (never pooled)")
    for era, d in rep["by_era"].items():
        line(f"  {era} BUY", d["buy"])
        line(f"  {era} market", d["market"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS,
                    help="one side, in basis points, charged on measured turnover")
    ap.add_argument("--lag-days", type=int, default=1,
                    help="calendar days after the IBES cut before the basket may trade")
    a = ap.parse_args(argv)
    if a.cost_bps <= 0:
        raise SystemExit("REFUSED: a zero-cost run is a diagnostic, not a result. "
                         "The farm's Policy refuses one and so does this.")
    if not a.run:
        ap.print_help()
        return 0
    return run(a.start, a.end, a.cost_bps, a.lag_days)


if __name__ == "__main__":
    sys.exit(main())
