"""BOOKS E, F and G — the historical read of three characteristics already on disk.

WHY THIS JOB EXISTS
===================
CLAUDE.md's bottleneck diagnosis is that all ten arena books select on ONE
signal and differ in portfolio treatment, not in alpha source. The 2026-09-13
research note found that the fastest way to add a genuinely different error type
is not a new data pull: `backend/data/optimus/wrds/jkp_full/jkp_usa_*.parquet`
(1926-2012) and `jkp_global_factor_usa.parquet` (2013-2024) carry
Jensen-Kelly-Pedersen's own quality (`qmj`) and calendar-seasonality
(`seas_11_15an`, `seas_16_20an`) composites, and
`ibes_consensus_monthly[_early].parquet` carries `stdev`/`numest`/`meanest`.
Every one of those columns has been sitting unread since the 19-22 August pulls.

  E  qmj_quality_tilt_v0      TRIAL-DRAFT-E   top `qmj` tercile, long only
  F  seasonality_11_20_v0     TRIAL-DRAFT-F   same-calendar-month, 11-20y lags
  G  forecast_dispersion_v0   TRIAL-DRAFT-G   LOW analyst disagreement, held

THE SAME ENGINE, ON PURPOSE
===========================
Every leg runs through `night_first_books_replay.run_monthly` — the same monthly
engine, the same turnover-matched twin, the same flat 25 bps ruler, the same
Newey-West lag-2 t, the same `by_era` split — that Books A and C were read
under. A new book that brought its own engine would be a comparison of two
engines wearing the names of two books.

WHAT IS NEW IS `pool_filter`, AND IT IS THE POINT
=================================================
Each of these three books requires something of a name that the market does not
require of every name: a JKP `qmj` score, twenty years of tape, three analysts.
A book measured against a twin drawn from names that require NONE of those is
measuring coverage and calling it selection. `run_monthly(pool_filter=...)`
narrows the eligible band BEFORE either leg sees it, so the book and its twin
are drawn from the identical covered pool at every floor.

BOTH FLOORS IN ONE PASS, TWIN RE-DRAWN AT EACH
==============================================
TRIAL-H5's lesson and `A_corner`'s: a corner-dependent control must be
RE-MEASURED at every corner. `floor_usd` moves the book, the twin and the
regressions' universe together, and every book here is read at the $3M primary
and the $10M secondary floor in one job so that neither can be quoted alone.

THE RECEIPT PRINTS THE CONSTRUCTION
===================================
Book C's 2026-09-13 lesson, paid for once already: run 1 warmed a 60-month
overhang at 24 months and the receipt said `confirm_slice 1995-2024` anyway.
Every cell here carries `registered_construction` with the frozen parameters it
actually used and a boolean `honours_the_registration`, so a smoke window or a
relaxed minimum cannot be mistaken for the registered read.

    python -m scripts.night_factory_jobs B_books_efg_replay --smoke
    NIGHT_QUEUE="B_books_efg_replay:90" python -m scripts.night_factory

TIME: the four-book replay measured 829 s over 1990-2024. This one skips Book
B's 35-year wide daily frame and adds three column-projected parquet reads;
projection 15-30 minutes. Queue it with an explicit box -- a job killed at its
time limit writes no receipt at all (2026-09-10, G3 at generation 340).
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

from scripts.night_c_falsifiers import january_split
from scripts.night_first_books_replay import (
    COST_BPS_PER_SIDE,
    COST_CURVE,
    ERAS,
    FLOOR_USD as REPLAY_FLOOR_USD,
    FULL_END,
    FULL_START,
    by_era,
    eligible,
    holm,
    load_monthly_panel,
    newey_west_t,
    run_monthly,
    two_sided_p,
    wrds_dir,
)

logger = logging.getLogger("books_efg_replay")

JOB = "B_books_efg_replay"

#: THE SECOND FAMILY, DECLARED AT SIZE FOUR BEFORE THE READ. It does not extend
#: `NIGHT_JOB_BOOKS_2026_09` (A, B, C, D), whose four primaries are read and
#: whose budget is spent. `disposition_overhang_conditioner_v1` is the fourth
#: member and is computed by `scripts/night_c_falsifiers.C_v1`, not here -- so
#: the Holm block below NAMES it as a leg without a p-value rather than
#: correcting over three and calling it four.
FAMILY = "NIGHT_JOB_BOOKS_2026_09_13"
DECLARED_FAMILY = ("qmj_quality_tilt_v0", "seasonality_11_20_v0",
                   "forecast_dispersion_v0",
                   "disposition_overhang_conditioner_v1")

#: Frozen by all three registrations: k, the tercile, the floors, the price
#: minimum (the last lives in the replay's `eligible`).
K = 30
TERCILE = 2.0 / 3.0
PRIMARY_FLOOR_USD = None                      # the replay's own $3M
SECONDARY_FLOOR_USD = 10_000_000.0

#: Per-book seeds. Inert wherever a twin is a named selector and carried anyway,
#: because a receipt that omits an unused seed is indistinguishable from one
#: that used a different seed.
SEEDS = {"E": 0x0E11, "F": 0x0F22, "G": 0x0733}

#: Each draft's own declared effect size (section 4), and the two MDE figures
#: every one of them prints: the nominal-360-block number and the same number
#: deflated by the lag-1 rho measured for k=30 on this panel. Written once here
#: rather than three times below.
DECLARED_EFFECT = {"E": 0.0070, "F": 0.0065, "G": 0.0065}
DECLARED_MDE_NOMINAL = 0.00637
DECLARED_MDE_DEFLATED = 0.00724
MDE_Z_SUM = 2.8                               # 1.96 + 0.84, two-sided, 80% power

#: |t| at or above which a payoff is called alive. The same line all three
#: drafts state for the primary metric and read their falsifiers against.
T_ALIVE = 2.0

#: A cross-sectional regression over fewer names than this is a regression on
#: the survivors. Same number `night_c_falsifiers` uses, for the same reason.
MIN_REGRESSION_NAMES = 20

#: The contamination clauses, verbatim from the three registrations. E excludes
#: a year whose coverage inside the eligible band falls below 0.25; F and G
#: exclude a year below 0.10 OR one whose MEDIAN month carries fewer than 3k
#: covered names.
MIN_COVERAGE_SHARE = {"E": 0.25, "F": 0.10, "G": 0.10}
MIN_COVERED_NAMES_MEDIAN = {"E": None, "F": 3 * K, "G": 3 * K}

#: The JKP columns this job reads. Named here so a reader can check them against
#: the parquet schema without running anything -- all nine were read directly
#: off the files on 2026-09-13 and none is assumed.
JKP_COLUMNS = ("permno", "eom", "qmj", "qmj_prof", "seas_2_5an",
               "seas_11_15an", "seas_16_20an", "market_equity", "beta_60m")

#: The IBES consensus columns Book G reads, with its frozen filters.
IBES_COLUMNS = ("permno", "statpers", "measure", "fpi", "numest", "meanest",
                "stdev")
IBES_FPI = "1"
IBES_MEASURE = "EPS"

#: The smoke window. Ten recent years and the 500 largest names by median dollar
#: volume: the three characteristics need no warm-up (they are precomputed
#: columns), but a tercile of a thin covered band is not the registered cut, and
#: a smoke that refuses every leg proves nothing about the job.
SMOKE_START, SMOKE_END, SMOKE_NAMES = 2015, 2024, 500


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "first_books" / "replay"


def find_run_receipt(*, smoke: bool = False) -> Path | None:
    """The newest `B_books_efg_replay` run receipt, or `None`.

    One finder, so `C_v1` and any later reader quote the same run. Smoke
    receipts are EXCLUDED unless asked for by name.
    """
    from backend.config import OPTIMUS_LEDGER_DIR

    cands = [p for p in OPTIMUS_LEDGER_DIR.glob(
        f"night_factory_*/{JOB}_run*.json")
        if ("_smoke" in p.name) == bool(smoke)]
    if not cands:
        return None
    return sorted(cands, key=lambda p: (p.stat().st_mtime, p.name))[-1]


# --------------------------------------------------------------------------
# the panels


class CharacteristicPanelUnavailable(RuntimeError):
    """A characteristic panel this job was asked to replay is not on disk.

    Raised rather than returned, so a book turns it into its own named refusal
    and a reader sees WHICH panel was missing. A shared `None` would leave every
    leg guessing.
    """


def jkp_files(start: int, end: int) -> list[Path]:
    """The JKP USA files covering `start`..`end`, oldest chunk first.

    The panel is stored as 2-to-5-year chunks to 2012 (`jkp_full/jkp_usa_a_b`)
    plus one continuation file for 2013-2024. The chunk boundaries are parsed
    from the filenames rather than hard-coded, because a later pull that adds a
    chunk should be picked up by existing code and not by an edit to a list.
    """
    d = wrds_dir()
    out = []
    for p in sorted((d / "jkp_full").glob("jkp_usa_*.parquet")):
        parts = p.stem.split("_")
        try:
            lo, hi = int(parts[-2]), int(parts[-1])
        except (ValueError, IndexError):
            continue
        if hi >= int(start) and lo <= int(end):
            out.append(p)
    cont = d / "jkp_global_factor_usa.parquet"
    if cont.is_file() and int(end) >= 2013:
        out.append(cont)
    return out


def load_jkp_monthly(start: int, end: int, *, columns=JKP_COLUMNS):
    """Per (permno, month) JKP characteristics over `start`..`end`.

    `eom` is the panel's own FORMATION stamp and the PIT argument rests on it:
    the panel's meta.json states each characteristic derives from data public by
    its `eom`. It is converted to a monthly period and nothing is shifted -- the
    engine selects at the close of `ym` and earns `ym+1`, which is exactly the
    month the seasonality columns refer to (TRIAL-DRAFT-F section 2, measured).

    Rows without a permno are dropped: the JKP `id` is not a CRSP identifier and
    guessing a join would be a leak dressed as coverage.
    """
    import pandas as pd

    files = jkp_files(start, end)
    if not files:
        raise CharacteristicPanelUnavailable(
            f"no JKP USA panel under {wrds_dir() / 'jkp_full'} or at "
            f"{wrds_dir() / 'jkp_global_factor_usa.parquet'}. This job does not "
            f"build data it was asked to replay.")
    frames = []
    for f in files:
        df = pd.read_parquet(f, columns=list(columns))
        df = df.dropna(subset=["permno"])
        df["permno"] = df["permno"].astype("int64")
        df["ym"] = pd.PeriodIndex(pd.to_datetime(df["eom"]), freq="M")
        df = df[(df["ym"].dt.year >= int(start)) & (df["ym"].dt.year <= int(end))]
        frames.append(df.drop(columns=["eom"]))
    panel = pd.concat(frames, ignore_index=True)
    # One row per (permno, month). The chunk files and the continuation file do
    # not overlap on this pull, but a duplicate would silently double a name's
    # weight in a cross-sectional z, so it is dropped rather than trusted away.
    panel = panel.drop_duplicates(subset=["permno", "ym"], keep="last")
    return panel.sort_values(["ym", "permno"], kind="mergesort").reset_index(drop=True)


def load_ibes_dispersion(start: int, end: int):
    """Per (permno, month) the one-year-ahead EPS consensus Book G reads.

    Filtered to `measure == 'EPS'` and `fpi == '1'` (TRIAL-DRAFT-G section 6,
    frozen) and stamped on `statpers`, the consensus snapshot date. A permno
    with two snapshots in one month keeps the LATER one: the selection happens
    at the month's close and the close knows both.
    """
    import pandas as pd

    con = wrds_dir() / "ibes_consensus_monthly.parquet"
    early = wrds_dir() / "ibes_consensus_monthly_early.parquet"
    frames = [pd.read_parquet(p, columns=list(IBES_COLUMNS))
              for p in (early, con) if p.is_file()]
    if not frames:
        raise CharacteristicPanelUnavailable(
            f"no IBES consensus panel at {con} or {early}; forecast dispersion "
            f"is `stdev / meanest` on that table and this job does not "
            f"substitute another measure of disagreement")
    ib = pd.concat(frames, ignore_index=True)
    ib = ib[(ib["measure"].astype(str) == IBES_MEASURE)
            & (ib["fpi"].astype(str) == IBES_FPI)]
    ib = ib.dropna(subset=["permno"])
    ib["permno"] = ib["permno"].astype("int64")
    ib["statpers"] = pd.to_datetime(ib["statpers"])
    ib["ym"] = ib["statpers"].dt.to_period("M")
    ib = ib[(ib["ym"].dt.year >= int(start)) & (ib["ym"].dt.year <= int(end))]
    ib = ib.sort_values(["permno", "ym", "statpers"], kind="mergesort")
    ib = ib.drop_duplicates(subset=["permno", "ym"], keep="last")
    return ib[["permno", "ym", "numest", "meanest", "stdev"]].reset_index(drop=True)


def by_month(frame) -> dict:
    """{ym: that month's rows}. Built once; every leg of a book reads it."""
    return {ym: g for ym, g in frame.groupby("ym", sort=False)}


# --------------------------------------------------------------------------
# coverage, and the contamination clauses


def covered_permnos(frames: dict, *, book: str) -> dict:
    """{ym: set(permno)} — the names that CARRY the book's characteristic.

    This is the set the twin is drawn from as well as the book, which is the
    single most important line in this file: a book that requires a `qmj` score,
    or twenty years of tape, or three analysts, measured against a twin that
    requires none of them, is measuring coverage and calling it selection.
    """
    import numpy as np

    out = {}
    for ym, g in frames.items():
        if book == "E":
            ok = np.isfinite(g["qmj"].to_numpy(dtype=float))
        elif book == "F":
            ok = (np.isfinite(g["seas_11_15an"].to_numpy(dtype=float))
                  & np.isfinite(g["seas_16_20an"].to_numpy(dtype=float)))
        elif book == "G":
            n = g["numest"].to_numpy(dtype=float)
            m = g["meanest"].to_numpy(dtype=float)
            s = g["stdev"].to_numpy(dtype=float)
            ok = (np.isfinite(n) & np.isfinite(m) & np.isfinite(s)
                  & (n >= 3) & (m != 0.0))
        else:
            raise ValueError(f"unknown book {book!r}")
        out[ym] = {int(p) for p, keep in zip(g["permno"], ok) if keep}
    return out


def coverage_and_contamination(panel, covered: dict, *, book: str,
                               floor_usd: float | None) -> dict:
    """Per-year coverage inside the eligible band, and the years it excludes.

    The clause is each registration's own and is applied BEFORE the number is
    read, not after it: E excludes a year whose covered share falls below 0.25,
    F and G a year below 0.10 or one whose MEDIAN month carries fewer than 3k
    covered names. The excluded years are reported with their numbers, because
    "we dropped 1991" and "we dropped 1991, coverage 0.06" are different facts.
    """
    import numpy as np

    per_year: dict = {}
    for ym, g in panel.groupby("ym", sort=True):
        pool = eligible(g, floor_usd=floor_usd)
        n_elig = int(len(pool))
        if n_elig == 0:
            continue
        have = covered.get(ym) or set()
        n_cov = int(sum(1 for p in pool["permno"] if int(p) in have))
        per_year.setdefault(int(ym.year), []).append((n_elig, n_cov))

    share_floor = MIN_COVERAGE_SHARE[book]
    names_floor = MIN_COVERED_NAMES_MEDIAN[book]
    years, excluded = {}, []
    for y, rows in sorted(per_year.items()):
        elig = [a for a, _ in rows]
        cov = [b for _, b in rows]
        share = float(np.sum(cov)) / float(np.sum(elig)) if np.sum(elig) else 0.0
        med = float(np.median(cov)) if cov else 0.0
        why = []
        if share < share_floor:
            why.append(f"covered share {share:.3f} < {share_floor}")
        if names_floor is not None and med < names_floor:
            why.append(f"median covered names {med:.0f} < {names_floor}")
        years[str(y)] = {"months": len(rows),
                         "median_eligible_names": float(np.median(elig)),
                         "median_covered_names": med,
                         "covered_share": round(share, 4),
                         "excluded": bool(why),
                         "why": "; ".join(why) or None}
        if why:
            excluded.append(y)
    return {"clause": (f"TRIAL-DRAFT-{book}'s contamination clause: exclude a "
                       f"year whose covered share inside the eligible band "
                       f"falls below {share_floor}"
                       + (f", or whose MEDIAN month carries fewer than "
                          f"{names_floor} covered names" if names_floor else "")),
            "floor_usd": (float(REPLAY_FLOOR_USD) if floor_usd is None
                          else float(floor_usd)),
            "per_year": years, "excluded_years": sorted(excluded),
            "n_excluded_years": len(excluded)}


# --------------------------------------------------------------------------
# the selectors
#
# Each is built from a characteristic frame and a covered-set, and each returns
# a (pool_filter, select) pair so that the book and its twin are drawn from the
# same band by construction rather than by a caller remembering to do it.


def _pool_filter(covered: dict, skip_years: set):
    def keep(pool, ym):
        if int(ym.year) in skip_years:
            return pool.iloc[0:0]
        have = covered.get(ym) or set()
        if not have:
            return pool.iloc[0:0]
        return pool[pool["permno"].astype("int64").isin(have)]
    return keep


def book_e_selector(frames: dict, *, column: str = "qmj", side: str = "top",
                    ascending: bool = False):
    """Book E: the `qmj` tercile, ranked so the BOOK's own end comes first.

    `side="bottom"` with `ascending=True` is the junk leg -- TRIAL-DRAFT-E
    section 5 clause 2 -- and it is the same call with the cut read from the
    other end, not a second selector.
    """
    from backend.services import book_signals as BS

    def select(pool, ym):
        g = frames.get(ym)
        if g is None or g.empty:
            return []
        sub = g[g["permno"].isin(set(pool["permno"].astype("int64")))]
        if sub.empty:
            return []
        try:
            scores = BS.qmj_rank(sub, column=column, side=side, tercile=TERCILE)
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(scores.items(),
                                     key=lambda kv: (kv[1] if ascending
                                                     else -kv[1]))]
    return select


def book_f_selector(frames: dict, *, columns=None, shift_months: int = 0):
    """Book F: the seasonality composite's top tercile.

    `shift_months=1` is the REGISTERED PLACEBO (TRIAL-DRAFT-F section 5 clause
    2): the same columns read from the name's row one month EARLIER, which by
    the measured alignment is the NEIGHBOURING calendar month's seasonality and
    is strictly older information -- so the placebo is PIT-safe by construction
    and cannot be the leak that makes it pay.
    """
    from backend.services import book_signals as BS

    cols = columns or BS.SEASONALITY_COLUMNS

    def select(pool, ym):
        src = ym - int(shift_months)
        g = frames.get(src)
        if g is None or g.empty:
            return []
        sub = g[g["permno"].isin(set(pool["permno"].astype("int64")))]
        if sub.empty:
            return []
        try:
            scores = BS.seasonality_score(sub, columns=cols, side="top",
                                          tercile=TERCILE)
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(scores.items(), key=lambda kv: -kv[1])]
    return select


def book_g_selector(frames: dict, *, side: str = "bottom"):
    """Book G: the LOW-disagreement tercile, ranked ASCENDING.

    A smaller `|stdev / meanest|` is a stronger hold, so the sort is ascending
    for the held leg and descending for the avoided one. The avoided leg is
    REPORTED and never traded: section 8 forbids shorting it, because the borrow
    cost that took 162 anomalies to -0.01%/month is not in this cost ruler.
    """
    from backend.services import book_signals as BS

    ascending = (side == "bottom")

    def select(pool, ym):
        g = frames.get(ym)
        if g is None or g.empty:
            return []
        sub = g[g["permno"].isin(set(pool["permno"].astype("int64")))]
        if sub.empty:
            return []
        try:
            scores = BS.forecast_dispersion(sub, side=side, tercile=TERCILE)
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(scores.items(),
                                     key=lambda kv: (kv[1] if ascending
                                                     else -kv[1]))]
    return select


# --------------------------------------------------------------------------
# the shared statistics


def recompute_mde(result: dict) -> dict:
    """The MDE from the book's OWN realised difference series.

    Every one of the three registrations promises this in section 4 -- "the MDE
    is recomputed from this book's own realised difference series, its own block
    count and its own measured lag-1 rho, before the decision is taken, and the
    recomputation is reported". It is computed here rather than left as a
    sentence, because a promise kept only in prose is not kept.
    """
    import numpy as np

    e = np.asarray(result.get("excess") or [], dtype=float)
    e = e[np.isfinite(e)]
    n = int(e.size)
    if n < 8:
        return {"status": "CANNOT DETERMINE",
                "why": f"{n} readable block(s); an autocorrelation over fewer "
                       f"than 8 is not a measurement"}
    sd = float(np.std(e, ddof=1))
    a, b = e[:-1] - e.mean(), e[1:] - e.mean()
    denom = float((a * a).sum() * (b * b).sum()) ** 0.5
    rho = float((a * b).sum() / denom) if denom > 0 else 0.0
    rho = max(-0.99, min(0.99, rho))
    n_eff = n * (1.0 - rho) / (1.0 + rho)
    mde = MDE_Z_SUM * sd / math.sqrt(n_eff) if n_eff > 0 else None
    return {"status": "MEASURED", "n_blocks": n,
            "realised_difference_sd": round(sd, 6),
            "measured_lag1_rho": round(rho, 4),
            "n_effective": round(n_eff, 2),
            "mde_monthly": (round(mde, 6) if mde is not None else None),
            "declared_mde_nominal": DECLARED_MDE_NOMINAL,
            "declared_mde_deflated": DECLARED_MDE_DEFLATED,
            "why": ("the registration's 0.637%/0.724% pair was computed from a "
                    "MODELLED book-minus-twin sd of 0.043167 at k=30. This is "
                    "the same arithmetic on the sd the book actually realised, "
                    "and it is the number the verdict should be read against "
                    "where the two disagree.")}


def era_stability(cell: dict) -> dict:
    """How many eras carry a POSITIVE mean, and which ones do not.

    Four eras are split, not three, so the count is reported with its
    denominator rather than squeezed into a rule written for a different split.
    """
    eras = cell.get("by_era") or {}
    rows = {k: (v or {}).get("mean_excess_net_monthly") for k, v in eras.items()}
    readable = {k: v for k, v in rows.items() if v is not None}
    positive = sorted(k for k, v in readable.items() if v > 0)
    negative = sorted(k for k, v in readable.items() if v <= 0)
    return {"n_eras_read": len(readable), "n_positive": len(positive),
            "positive_eras": positive, "negative_eras": negative,
            "mean_by_era": readable,
            "all_positive": bool(readable and not negative)}


def _z(a):
    import numpy as np

    x = np.asarray(a, dtype=float)
    sd = float(np.nanstd(x))
    if not np.isfinite(sd) or sd <= 0:
        return np.zeros_like(x)
    return (x - float(np.nanmean(x))) / sd


def fama_macbeth(rows, *, regressors, target: str = "ret_next",
                 min_names: int = MIN_REGRESSION_NAMES) -> dict:
    """Month-by-month cross-sectional OLS, then a Newey-West t on the slopes.

    Every regressor is standardised WITHIN each month before the fit, so the
    coefficients are comparable across months and across regressors. Both the
    MULTIVARIATE slope and the UNIVARIATE ("raw") slope of every regressor are
    returned, because a subsumption test is only readable if the thing being
    subsumed was alive to begin with -- 2026-09-13, when Book C's momentum
    falsifier "passed" with raw momentum at t 0.15 and nothing alive to subsume.
    """
    import numpy as np

    reg = list(regressors)
    by_ym: dict = {}
    for r in rows:
        by_ym.setdefault(r["ym"], []).append(r)
    multi: dict = {k: [] for k in reg}
    uni: dict = {k: [] for k in reg}
    months = []
    for ym in sorted(by_ym):
        block = by_ym[ym]
        if len(block) < int(min_names):
            continue
        y = np.asarray([b[target] for b in block], dtype=float)
        cols = [_z([b[k] for b in block]) for k in reg]
        if not np.all(np.isfinite(y)) or any(not np.all(np.isfinite(c))
                                             for c in cols):
            continue
        X = np.column_stack([np.ones_like(y)] + cols)
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        for i, k in enumerate(reg):
            multi[k].append(float(beta[i + 1]))
            Xu = np.column_stack([np.ones_like(y), cols[i]])
            try:
                bu = np.linalg.lstsq(Xu, y, rcond=None)[0]
            except np.linalg.LinAlgError:
                uni[k].append(float("nan"))
                continue
            uni[k].append(float(bu[1]))
        months.append(str(ym))

    def _leg(series):
        vals = [v for v in series if np.isfinite(v)]
        if len(vals) < 3:
            return {"n_months": len(vals), "mean": None, "nw_lag2_t": None}
        t = newey_west_t(vals)
        return {"n_months": len(vals), "mean": round(float(np.mean(vals)), 6),
                "nw_lag2_t": (round(t, 4) if t is not None else None)}

    return {"n_months": len(months), "regressors": reg, "target": target,
            "multivariate": {k: _leg(v) for k, v in multi.items()},
            "univariate": {k: _leg(v) for k, v in uni.items()},
            "construction": ("each regressor standardised within the month's own "
                             "cross-section, OLS with an intercept, the slope "
                             "series priced with a Newey-West lag-2 t. The "
                             "univariate block is the LIVENESS check: a control "
                             "that was never alive cannot subsume anything.")}


def survives(fm: dict, key: str) -> dict:
    """Did `key` survive the multivariate fit, and was it alive to begin with?"""
    m = (fm.get("multivariate") or {}).get(key) or {}
    u = (fm.get("univariate") or {}).get(key) or {}
    t_m, t_u = m.get("nw_lag2_t"), u.get("nw_lag2_t")
    testable = bool(t_u is not None and abs(t_u) >= T_ALIVE)
    return {
        "regressor": key,
        "t_multivariate": t_m, "t_univariate_raw": t_u,
        "alive_raw": testable,
        "survives": (None if t_m is None else bool(abs(t_m) >= T_ALIVE)),
        "testable": testable,
        "why": (f"raw |t| {t_u} against the |t| >= {T_ALIVE} line, and "
                f"{t_m} with the controls on the right-hand side."
                + ("" if testable else
                   " The raw payoff was NOT alive, so this is a check that "
                   "could not run and not a check that passed.")),
    }


# --------------------------------------------------------------------------
# one book, one floor


def run_cell(panel, *, book: str, label: str, select, pool_filter,
             floor_usd, seed: int) -> dict:
    """One book at one floor, with its twin re-drawn at that floor."""
    res = run_monthly(panel, select, k=K, seed=seed, label=label,
                      twin="random_universe_turnover_matched",
                      floor_usd=floor_usd, pool_filter=pool_filter)
    return {"label": label, "book": book,
            "floor_usd": (float(REPLAY_FLOOR_USD) if floor_usd is None
                          else float(floor_usd)),
            "floor_is_registered_primary": floor_usd is None,
            "result": {k: v for k, v in res.items()
                       if k not in ("blocks", "excess")},
            "by_era": by_era(res),
            "mde_recomputed": recompute_mde(res),
            "_series": res}


def decide_cell(book: str, cell: dict, falsifiers: list, secondary: dict | None) -> dict:
    """Each draft's section 5, applied to the PRIMARY floor's cell.

    The ladder can only be read off the primary floor: section 8 of every draft
    says both floors are printed or neither is, and section 5 makes the second
    floor a way for a CLEARED primary to be held back -- never a way for a
    failed one to be promoted.
    """
    res = cell.get("result") or {}
    mean, t = res.get("mean_excess_net_monthly"), res.get("nw_lag2_t")
    declared = DECLARED_EFFECT[book]
    eras = era_stability(cell)
    sec_mean = ((secondary or {}).get("result") or {}).get("mean_excess_net_monthly")

    if mean is None:
        return {"verdict": "CANNOT_DETERMINE", "clauses_fired": [],
                "reading": ("the primary cell produced no block mean, so no "
                            "verdict may be read. A check that did not run is "
                            "not a check that passed.")}

    fired = []
    if mean <= 0:
        fired.append(
            f"the primary metric is on the WRONG SIDE OF ZERO: {mean:+.6f}/month "
            f"at NW lag-2 t {t} (section 5 clause 1, carried in this draft from "
            f"the start rather than added by amendment afterwards)")
    for f in falsifiers:
        if f.get("fires"):
            fired.append(f["clause"])
    if fired:
        return {"verdict": "FAILED_VARIANT", "clauses_fired": fired,
                "era_stability": eras,
                "reading": ("any one clause alone closes the book, whatever the "
                            "others did. " + "; ".join(fired))}

    undetermined = [f["falsifier"] for f in falsifiers if f.get("fires") is None]
    if undetermined:
        return {"verdict": "CANNOT_DETERMINE", "clauses_fired": [],
                "era_stability": eras,
                "undetermined_falsifiers": undetermined,
                "reading": (f"the primary metric is {mean:+.6f}/month at t {t} "
                            f"and no clause fired, but {undetermined} could not "
                            f"be computed. A falsifier that could not run is not "
                            f"a falsifier that passed.")}

    clears = bool(mean >= declared and t is not None and t >= T_ALIVE)
    promising = bool(clears and eras["n_positive"] >= 3
                     and sec_mean is not None and sec_mean > 0)
    if promising:
        return {"verdict": "PRODUCT_PROMISING", "clauses_fired": [],
                "era_stability": eras,
                "reading": (f"{mean:+.6f}/month at t {t} clears the declared "
                            f"{declared:.4f}/month, both falsifiers passed, the "
                            f"sign is positive in {eras['n_positive']}/"
                            f"{eras['n_eras_read']} eras and the $10M cell is "
                            f"{sec_mean:+.6f}/month.")}
    holds = []
    if not clears:
        holds.append(f"the block mean {mean:+.6f}/month at t {t} is below the "
                     f"declared {declared:.4f}/month or below the |t| >= "
                     f"{T_ALIVE} line")
    if eras["n_positive"] < 3:
        holds.append(f"the sign is positive in only {eras['n_positive']}/"
                     f"{eras['n_eras_read']} eras "
                     f"(negative: {', '.join(eras['negative_eras']) or 'none'})")
    if sec_mean is None or sec_mean <= 0:
        holds.append(f"the $10M secondary cell is {sec_mean}")
    return {"verdict": "CONDITIONAL", "clauses_fired": [],
            "era_stability": eras,
            "reading": ("both falsifiers passed, so neither FAILED_VARIANT "
                        "clause fires, and the standing verdict is the one the "
                        "primary metric earned and no better: " + "; ".join(holds)
                        + ". A falsifier that passes is not evidence FOR the "
                          "book.")}


def _p(cell: dict):
    return ((cell or {}).get("result") or {}).get("p_two_sided")


# --------------------------------------------------------------------------
# BOOK E


def replay_book_e(panel, jkp_frames: dict, *, smoke: bool) -> dict:
    covered = covered_permnos(jkp_frames, book="E")
    cells, falsifier_blocks = {}, {}
    contamination = {}
    for name, floor in (("primary_floor", PRIMARY_FLOOR_USD),
                        ("secondary_floor", SECONDARY_FLOOR_USD)):
        cont = coverage_and_contamination(panel, covered, book="E",
                                          floor_usd=floor)
        contamination[name] = cont
        skip = set(cont["excluded_years"])
        pf = _pool_filter(covered, skip)
        cells[name] = run_cell(panel, book="E", label="qmj_quality_tilt_v0",
                               select=book_e_selector(jkp_frames),
                               pool_filter=pf, floor_usd=floor,
                               seed=SEEDS["E"])
        # Falsifier 1: the junk leg must LOSE.
        junk = run_cell(panel, book="E", label="qmj_junk_leg_falsifier",
                        select=book_e_selector(jkp_frames, side="bottom",
                                               ascending=True),
                        pool_filter=pf, floor_usd=floor, seed=SEEDS["E"])
        legs = {"junk_leg": junk}
        if floor is PRIMARY_FLOOR_USD:
            # TRIAL-DRAFT-E section 3's `qmj_prof`-only leg: REPORTED, never
            # deciding, and section 8 forbids it becoming the primary. It is run
            # so that "QMJ is really profitability" is a number on the receipt
            # rather than an objection nobody measured.
            legs["qmj_prof_only_diagnostic"] = run_cell(
                panel, book="E", label="qmj_prof_only_diagnostic",
                select=book_e_selector(jkp_frames, column="qmj_prof"),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["E"])
        falsifier_blocks[name] = legs

    primary_skip = set(contamination["primary_floor"]["excluded_years"])
    rows = characteristic_rows(panel, jkp_frames, covered, primary_skip,
                               floor_usd=PRIMARY_FLOOR_USD,
                               fields={"qmj": "qmj",
                                       "size": "market_equity",
                                       "beta": "beta_60m"},
                               log_fields=("size",))
    fm = fama_macbeth(rows, regressors=("qmj", "size", "beta"))
    qmj_check = survives(fm, "qmj")

    junk_mean = ((falsifier_blocks["primary_floor"]["junk_leg"].get("result")
                  or {}).get("mean_excess_net_monthly"))
    falsifiers = [
        {"falsifier": "junk_leg_must_lose",
         "registered_as": ("TRIAL-DRAFT-E section 5 clause 2: the bottom-`qmj` "
                           "tercile, same engine, same twin, same floor, must "
                           "have a NEGATIVE net excess. If quality and junk BOTH "
                           "beat the twin, the sort is not ordering anything."),
         "junk_mean_excess_net_monthly": junk_mean,
         "junk_nw_lag2_t": ((falsifier_blocks["primary_floor"]["junk_leg"]
                             .get("result") or {}).get("nw_lag2_t")),
         "fires": (None if junk_mean is None else bool(junk_mean > 0)),
         "clause": ("the JUNK leg also beats the twin "
                    f"({junk_mean}/month), so the `qmj` sort is not ordering "
                    "anything (section 5 clause 2)")},
        {"falsifier": "size_and_beta_control",
         "registered_as": ("TRIAL-DRAFT-E section 5 clause 3: in a Fama-MacBeth "
                           "of next month's return on z(qmj), z(log market "
                           "equity) and z(beta_60m), `qmj`'s own payoff must "
                           "survive at |t| >= 2.0."),
         "fama_macbeth": fm, "qmj": qmj_check,
         "fires": (None if not qmj_check["testable"]
                   else (None if qmj_check["survives"] is None
                         else not qmj_check["survives"])),
         "undetermined_because": (None if qmj_check["testable"] else
                                  "the raw `qmj` payoff was not alive, so the "
                                  "control cannot subsume it and the clause "
                                  "cannot fire either way"),
         "clause": ("`qmj` DIES with size and beta on the right-hand side "
                    f"(multivariate t {qmj_check['t_multivariate']} vs raw "
                    f"{qmj_check['t_univariate_raw']}), so the tilt is size and "
                    "beta in quality's clothing (section 5 clause 3)")},
    ]
    # A clause that could not be computed is CANNOT_DETERMINE at the verdict and
    # never a quiet pass: `fires=None` carries that up to `decide_cell`, and
    # `undetermined_because` says WHICH way it failed to run -- a control that
    # was never alive and a regression that never converged are different facts.
    verdict = decide_cell("E", cells["primary_floor"], falsifiers,
                          cells["secondary_floor"])
    return _book_payload("E", "qmj_quality_tilt_v0",
                         "TRIAL-DRAFT-E-quality-minus-junk-v0 (UNSIGNED)",
                         cells, falsifiers, falsifier_blocks, contamination,
                         verdict, smoke=smoke,
                         construction={
                             "column": "qmj",
                             "cut": "top tercile",
                             "tercile": TERCILE, "k": K,
                             "hold": "one month, monthly rebalance",
                             "twin": "turnover-matched random draw from the "
                                     "SAME qmj-covered band",
                             "declared_effect_size": DECLARED_EFFECT["E"]})


# --------------------------------------------------------------------------
# BOOK F


def replay_book_f(panel, jkp_frames: dict, *, smoke: bool) -> dict:
    covered = covered_permnos(jkp_frames, book="F")
    # The placebo reads the name's row one month EARLIER, so its covered set is
    # the earlier month's. Shifting the SET as well as the read is what makes
    # the placebo's universe the placebo's universe.
    shifted = {ym: (covered.get(ym - 1) or set()) for ym in covered}
    cells, falsifier_blocks, contamination = {}, {}, {}
    for name, floor in (("primary_floor", PRIMARY_FLOOR_USD),
                        ("secondary_floor", SECONDARY_FLOOR_USD)):
        cont = coverage_and_contamination(panel, covered, book="F",
                                          floor_usd=floor)
        contamination[name] = cont
        skip = set(cont["excluded_years"])
        cells[name] = run_cell(panel, book="F", label="seasonality_11_20_v0",
                               select=book_f_selector(jkp_frames),
                               pool_filter=_pool_filter(covered, skip),
                               floor_usd=floor, seed=SEEDS["F"])
        placebo = run_cell(panel, book="F",
                           label="seasonality_one_month_shift_placebo",
                           select=book_f_selector(jkp_frames, shift_months=1),
                           pool_filter=_pool_filter(shifted, skip),
                           floor_usd=floor, seed=SEEDS["F"])
        legs = {"one_month_shift_placebo": placebo}
        if floor is PRIMARY_FLOOR_USD:
            # TRIAL-DRAFT-F section 3's years-2-5 leg: REPORTED, never deciding,
            # and section 8 forbids it becoming the primary. Its covered band is
            # its own, so it gets its own filter rather than borrowing the
            # 11-20 band and silently reading a different universe.
            near_cov = {ym: {int(x) for x, v in zip(g["permno"],
                                                    g["seas_2_5an"])
                             if v == v}
                        for ym, g in jkp_frames.items()}
            legs["seas_2_5_diagnostic"] = run_cell(
                panel, book="F", label="seasonality_years_2_5_diagnostic",
                select=book_f_selector(jkp_frames,
                                       columns=_seasonality_columns_near()),
                pool_filter=_pool_filter(near_cov, skip), floor_usd=floor,
                seed=SEEDS["F"])
        falsifier_blocks[name] = legs

    jan = january_split(cells["primary_floor"]["_series"])
    rest = (jan.get("february_to_december") or {})
    rest_t, rest_n = rest.get("nw_lag2_t"), rest.get("n_blocks") or 0
    jan_n = (jan.get("january") or {}).get("n_blocks") or 0

    pl = falsifier_blocks["primary_floor"]["one_month_shift_placebo"]
    pl_mean = (pl.get("result") or {}).get("mean_excess_net_monthly")
    pl_t = (pl.get("result") or {}).get("nw_lag2_t")
    falsifiers = [
        {"falsifier": "one_month_shifted_placebo",
         "registered_as": ("TRIAL-DRAFT-F section 5 clause 2: the same book "
                           "built from the SAME columns read one month EARLIER "
                           "-- the neighbouring calendar month's seasonality, "
                           "strictly older information and therefore PIT-safe "
                           "-- must be indistinguishable from zero. If picking "
                           "names on the wrong calendar month pays as well, the "
                           "effect is a persistent name-level premium and not a "
                           "calendar one."),
         "placebo_mean_excess_net_monthly": pl_mean, "placebo_nw_lag2_t": pl_t,
         "fires": (None if pl_mean is None or pl_t is None
                   else bool(pl_mean > 0 and abs(pl_t) >= T_ALIVE)),
         "clause": (f"the one-month-shifted placebo ALSO pays ({pl_mean}/month, "
                    f"t {pl_t}), so what was measured is not a calendar effect "
                    f"(section 5 clause 2)")},
        {"falsifier": "the_whole_effect_is_january",
         "registered_as": ("TRIAL-DRAFT-F section 5 clause 3: the ex-January "
                           "block mean must still carry NW lag-2 t >= 1.5. A "
                           "book whose payoff lives in one month of the year is "
                           "a January book and must be called one."),
         "january_split": jan,
         "fires": (None if rest_t is None or jan_n < 24 or rest_n < 24
                   else bool(rest_t < 1.5)),
         "undetermined_because": (None if (rest_t is not None and jan_n >= 24
                                           and rest_n >= 24)
                                  else f"{jan_n} January block(s) and {rest_n} "
                                       f"non-January block(s); section 5 makes "
                                       f"fewer than 24 Januaries UNTESTABLE"),
         "clause": (f"the ex-January residual carries NW lag-2 t {rest_t}, below "
                    f"the 1.5 line, so the payoff is January and not "
                    f"seasonality (section 5 clause 3)")},
    ]
    verdict = decide_cell("F", cells["primary_floor"], falsifiers,
                          cells["secondary_floor"])
    return _book_payload("F", "seasonality_11_20_v0",
                         "TRIAL-DRAFT-F-calendar-seasonality-v0 (UNSIGNED)",
                         cells, falsifiers, falsifier_blocks, contamination,
                         verdict, smoke=smoke,
                         construction={
                             "columns": list(_seasonality_columns()),
                             "both_columns_required": True,
                             "cut": "top tercile of the equal-weight mean of "
                                    "the within-month z-scores",
                             "tercile": TERCILE, "k": K,
                             "hold": "one month, monthly rebalance",
                             "twin": "turnover-matched random draw from the "
                                     "SAME band covered by BOTH columns",
                             "alignment_measured": (
                                 "seas_2_5an at eom=t correlates 0.99999 with "
                                 "the name's own mean excess return at months "
                                 "t+1-12k, k=2..5 (TRIAL-DRAFT-F section 2). The "
                                 "column refers to the month the book EARNS."),
                             "declared_effect_size": DECLARED_EFFECT["F"]})


def _seasonality_columns():
    from backend.services import book_signals as BS
    return BS.SEASONALITY_COLUMNS


def _seasonality_columns_near():
    from backend.services import book_signals as BS
    return BS.SEASONALITY_COLUMNS_NEAR


# --------------------------------------------------------------------------
# BOOK G


def replay_book_g(panel, ibes_frames: dict, *, smoke: bool) -> dict:
    covered = covered_permnos(ibes_frames, book="G")
    cells, falsifier_blocks, contamination = {}, {}, {}
    for name, floor in (("primary_floor", PRIMARY_FLOOR_USD),
                        ("secondary_floor", SECONDARY_FLOOR_USD)):
        cont = coverage_and_contamination(panel, covered, book="G",
                                          floor_usd=floor)
        contamination[name] = cont
        skip = set(cont["excluded_years"])
        cells[name] = run_cell(panel, book="G", label="forecast_dispersion_v0",
                               select=book_g_selector(ibes_frames),
                               pool_filter=_pool_filter(covered, skip),
                               floor_usd=floor, seed=SEEDS["G"])
        avoided = run_cell(panel, book="G",
                           label="forecast_dispersion_high_leg_reported_only",
                           select=book_g_selector(ibes_frames, side="top"),
                           pool_filter=_pool_filter(covered, skip),
                           floor_usd=floor, seed=SEEDS["G"])
        falsifiers_here = {"high_dispersion_leg_reported_only": avoided}
        # Falsifier 1: the same book inside the TOP HALF of the band by dollar
        # volume, twin re-drawn there. DMS report the effect concentrated in
        # small stocks, so a payoff that lives only in the smallest names of a
        # $3M-floor universe is small-cap beta.
        falsifiers_here["big_half_only"] = run_cell(
            panel, book="G", label="forecast_dispersion_big_half_only",
            select=book_g_selector(ibes_frames),
            pool_filter=_big_half_filter(covered, skip), floor_usd=floor,
            seed=SEEDS["G"])
        falsifier_blocks[name] = falsifiers_here

    big = falsifier_blocks["primary_floor"]["big_half_only"]
    big_mean = (big.get("result") or {}).get("mean_excess_net_monthly")
    big_t = (big.get("result") or {}).get("nw_lag2_t")

    primary_skip = set(contamination["primary_floor"]["excluded_years"])
    rows, si_status = dispersion_si_rows(panel, ibes_frames, covered,
                                         primary_skip,
                                         floor_usd=PRIMARY_FLOOR_USD)
    fm = fama_macbeth(rows, regressors=("low_dispersion", "si_ratio")) if rows else {}
    disp_check = survives(fm, "low_dispersion") if fm else {
        "regressor": "low_dispersion", "t_multivariate": None,
        "t_univariate_raw": None, "alive_raw": False, "survives": None,
        "testable": False, "why": si_status}

    falsifiers = [
        {"falsifier": "survives_outside_the_smallest_names",
         "registered_as": ("TRIAL-DRAFT-G section 5 clause 2: re-run inside the "
                           "TOP HALF of the eligible band by dollar volume, twin "
                           "re-drawn there, and require the net excess to stay "
                           "positive. DMS report the effect concentrated in "
                           "small stocks."),
         "big_half_mean_excess_net_monthly": big_mean,
         "big_half_nw_lag2_t": big_t,
         "fires": (None if big_mean is None else bool(big_mean <= 0)),
         "clause": (f"the effect does not survive outside the smallest names "
                    f"({big_mean}/month, t {big_t} in the top half of the band), "
                    f"so it is small-cap beta and not a disagreement premium "
                    f"(section 5 clause 2)")},
        {"falsifier": "survives_short_interest_conditioning",
         "registered_as": ("TRIAL-DRAFT-G section 5 clause 3: with `si_ratio` on "
                           "the right-hand side, dispersion's own payoff must "
                           "survive at |t| >= 2.0. Miller (1977) is the mechanism "
                           "BOTH this book and Book A claim, and Book A's cell is "
                           "closed FAILED_VARIANT at -0.9368%/month."),
         "fama_macbeth": fm, "low_dispersion": disp_check,
         "short_interest_panel": si_status,
         "fires": (None if not disp_check["testable"]
                   else (None if disp_check["survives"] is None
                         else not disp_check["survives"])),
         "undetermined_because": (None if disp_check["testable"] else
                                  "the raw low-dispersion payoff was not alive "
                                  "(or the short-interest panel did not cover "
                                  "the window), so the control cannot subsume "
                                  "it and the clause cannot fire either way"),
         "clause": ("low dispersion DIES with short interest on the right-hand "
                    f"side (multivariate t {disp_check['t_multivariate']} vs raw "
                    f"{disp_check['t_univariate_raw']}), so this book is Book A's "
                    "closed cell in costume (section 5 clause 3)")},
    ]
    verdict = decide_cell("G", cells["primary_floor"], falsifiers,
                          cells["secondary_floor"])
    return _book_payload("G", "forecast_dispersion_v0",
                         "TRIAL-DRAFT-G-forecast-dispersion-v0 (UNSIGNED)",
                         cells, falsifiers, falsifier_blocks, contamination,
                         verdict, smoke=smoke,
                         construction={
                             "ratio": "|stdev / meanest|",
                             "filters": {"measure": IBES_MEASURE,
                                         "fpi": IBES_FPI, "numest_min": 3},
                             "cut": "BOTTOM tercile (low disagreement) is HELD; "
                                    "the top tercile is AVOIDED and never shorted",
                             "tercile": TERCILE, "k": K,
                             "hold": "one month, monthly rebalance",
                             "twin": "turnover-matched random draw from the "
                                     "SAME numest>=3 covered band",
                             "declared_effect_size": DECLARED_EFFECT["G"]})


def _big_half_filter(covered: dict, skip_years: set):
    """The covered band, further restricted to the TOP HALF by dollar volume.

    The median is taken INSIDE the covered eligible band for that month, so the
    twin drawn from this filtered pool is matched on the same restriction. A
    "big half" cut against a control drawn from the whole band would compare two
    universes and call it a size check.
    """
    base = _pool_filter(covered, skip_years)

    def keep(pool, ym):
        sub = base(pool, ym)
        if sub is None or sub.empty:
            return sub
        med = float(sub["dv"].median())
        return sub[sub["dv"] >= med]
    return keep


# --------------------------------------------------------------------------
# the regression row builders


def characteristic_rows(panel, frames: dict, covered: dict, skip_years: set, *,
                        floor_usd, fields: dict, log_fields=()):
    """(ym, permno, ret_next, <named fields>) over the covered eligible band.

    `ret_next` is the NEXT month's return, taken from the panel exactly as
    `run_monthly` takes it, so the regression prices the same thing the book
    earns. `log_fields` are log-transformed before standardising, which is what
    "size" means in a cross-sectional regression.
    """
    import numpy as np

    months = sorted(panel["ym"].unique())
    bm = {ym: g for ym, g in panel.groupby("ym", sort=False)}
    rows = []
    for i in range(len(months) - 1):
        ym, nxt = months[i], months[i + 1]
        if int(ym.year) in skip_years:
            continue
        pool = eligible(bm[ym], floor_usd=floor_usd)
        have = covered.get(ym) or set()
        if pool.empty or not have:
            continue
        g = frames.get(ym)
        if g is None or g.empty:
            continue
        keep = set(int(p) for p in pool["permno"]) & have
        sub = g[g["permno"].isin(keep)]
        if len(sub) < MIN_REGRESSION_NAMES:
            continue
        nf = bm.get(nxt)
        if nf is None:
            continue
        rmap = dict(zip(nf["permno"], nf["ret_m"]))
        for r in sub.itertuples(index=False):
            pn = int(getattr(r, "permno"))
            nxt_r = rmap.get(pn)
            if nxt_r is None or not np.isfinite(float(nxt_r)):
                continue
            row = {"ym": ym, "permno": pn, "ret_next": float(nxt_r)}
            ok = True
            for key, col in fields.items():
                v = float(getattr(r, col, float("nan")))
                if key in log_fields:
                    v = math.log(v) if v > 0 else float("nan")
                if not np.isfinite(v):
                    ok = False
                    break
                row[key] = v
            if ok:
                rows.append(row)
    return rows


def dispersion_si_rows(panel, ibes_frames: dict, covered: dict,
                       skip_years: set, *, floor_usd):
    """Book G's falsifier rows: low-dispersion and short interest, same names.

    The short-interest panel is Book A's own, read on `observed_at` (settlement
    + the measured publication lag) and never on `datadate`. If it is not on
    disk the rows come back empty and the falsifier reports CANNOT DETERMINE --
    a check that could not run is not a check that passed.
    """
    import numpy as np
    import pandas as pd

    from backend.services import book_signals as BS

    years = sorted({int(p.year) for p in panel["ym"].unique()})
    d = BS.short_interest_panel_dir()
    frames = []
    for y in years:
        f = d / f"{y}.parquet"
        if f.is_file():
            frames.append(pd.read_parquet(f, columns=["permno", "observed_at",
                                                      "si_ratio"]))
    if not frames:
        return [], (f"no short-interest panel under {d}; TRIAL-DRAFT-G section 5 "
                    f"clause 3 is UNTESTABLE on this checkout and is reported as "
                    f"CANNOT DETERMINE rather than as a pass")
    si = pd.concat(frames, ignore_index=True)
    si["observed_at"] = pd.to_datetime(si["observed_at"])
    si["permno"] = si["permno"].astype("int64")

    months = sorted(panel["ym"].unique())
    bm = {ym: g for ym, g in panel.groupby("ym", sort=False)}
    rows = []
    for i in range(len(months) - 1):
        ym, nxt = months[i], months[i + 1]
        if int(ym.year) in skip_years:
            continue
        pool = eligible(bm[ym], floor_usd=floor_usd)
        have = covered.get(ym) or set()
        g = ibes_frames.get(ym)
        if pool.empty or not have or g is None or g.empty:
            continue
        asof = ym.to_timestamp(how="end")
        seen = si[si["observed_at"] <= asof]
        if seen.empty:
            continue
        latest = (seen.sort_values(["permno", "observed_at"], kind="mergesort")
                  .drop_duplicates(subset=["permno"], keep="last"))
        simap = dict(zip(latest["permno"], latest["si_ratio"]))
        nf = bm.get(nxt)
        if nf is None:
            continue
        rmap = dict(zip(nf["permno"], nf["ret_m"]))
        keep = set(int(p) for p in pool["permno"]) & have
        sub = g[g["permno"].isin(keep)]
        for pn, sd, mean in zip(sub["permno"], sub["stdev"], sub["meanest"]):
            pn = int(pn)
            nxt_r, s = rmap.get(pn), simap.get(pn)
            if nxt_r is None or s is None:
                continue
            try:
                disp = abs(float(sd) / float(mean))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if not (np.isfinite(disp) and np.isfinite(float(s))
                    and np.isfinite(float(nxt_r))):
                continue
            rows.append({"ym": ym, "permno": pn, "ret_next": float(nxt_r),
                         # NEGATED so the regressor points the way the book
                         # trades: more of it is more hold, exactly as `qmj` is.
                         "low_dispersion": -disp, "si_ratio": float(s)})
    return rows, "read"


# --------------------------------------------------------------------------
# the per-book payload


def _book_payload(key: str, label: str, prereg: str, cells: dict,
                  falsifiers: list, falsifier_blocks: dict, contamination: dict,
                  verdict: dict, *, smoke: bool, construction: dict) -> dict:
    def _strip(cell):
        return {k: v for k, v in cell.items() if k != "_series"}

    def _strip_all(d):
        return {k: _strip(v) for k, v in d.items()}

    p = cells["primary_floor"]["result"]
    s = cells["secondary_floor"]["result"]
    return {
        "book": label, "book_key": key, "prereg": prereg,
        "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "ran": bool(p.get("mean_excess_net_monthly") is not None),
        "primary_metric": "net_monthly_excess_vs_random_twin",
        "registered_construction": {
            **construction,
            "floors_usd": {"primary": float(REPLAY_FLOOR_USD),
                           "secondary": float(SECONDARY_FLOOR_USD)},
            "min_price_usd": 5.0,
            "cost_curve": COST_CURVE,
            "cost_bps_per_side": COST_BPS_PER_SIDE,
            "honours_the_registration": bool(not smoke),
            "why": ("printed in full because Book C's run 1 said "
                    "`confirm_slice 1995-2024` while warming a 60-month overhang "
                    "at 24 months. A receipt that does not print its own "
                    "construction cannot be checked against the registration "
                    "that licensed it. A SMOKE run cannot honour the registered "
                    "window and says so here rather than being mistaken for it."),
        },
        "cells": {"primary_floor": _strip(cells["primary_floor"]),
                  "secondary_floor": _strip(cells["secondary_floor"])},
        "falsifiers": falsifiers,
        "falsifier_cells": {k: _strip_all(v) for k, v in falsifier_blocks.items()},
        "contamination": contamination,
        "era_stability": {"primary_floor": era_stability(cells["primary_floor"]),
                          "secondary_floor": era_stability(cells["secondary_floor"])},
        "verdict_block": verdict,
        "verdict": verdict["verdict"] + " — " + verdict["reading"],
        "both_floors_or_neither": (
            "TRIAL-DRAFT-A section 8's rule, applied here for the same reason: a "
            "book quoted at the floor that flatters it is a book quoted at a "
            "chosen corner. Both cells are above; neither may travel alone."),
        "headline": (
            f"{label}: $3M {p.get('mean_excess_net_monthly')}/month t "
            f"{p.get('nw_lag2_t')} over {p.get('n_blocks')} blocks (median "
            f"{p.get('median_names_selected')} names) | $10M "
            f"{s.get('mean_excess_net_monthly')}/month t {s.get('nw_lag2_t')} "
            f"over {s.get('n_blocks')} blocks -> {verdict['verdict']}"),
        "smoke": bool(smoke),
    }


# --------------------------------------------------------------------------
# the job


def B_books_efg_replay(*, smoke: bool = False) -> dict:           # noqa: N802
    """The night-factory entry point. One receipt, three books, two floors each."""
    t0 = datetime.now(timezone.utc)
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    panel = load_monthly_panel(start, end,
                               max_names=SMOKE_NAMES if smoke else None)

    base = {
        "job": JOB, "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "window": [start, end], "smoke": bool(smoke),
        "max_names": SMOKE_NAMES if smoke else None,
        "months_in_panel": int(panel["ym"].nunique()),
        "permnos_in_panel": int(panel["permno"].nunique()),
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "cost_caveat": ("the interim flat ruler, pending chunk 5c's TAQ curve. "
                        "Every leg of every comparison pays it, so DIFFERENCES "
                        "may be read and no LEVEL may -- and the two floors do "
                        "NOT pay the same real spread, which is exactly what a "
                        "flat ruler cannot see."),
        "question": ("Do three characteristics this repository has held unread "
                     "since August -- JKP quality, JKP calendar seasonality and "
                     "IBES forecast dispersion -- beat a twin drawn from their "
                     "own covered band, at both floors, 1990-2024?"),
        "eras_reported": [f"{a}-{b}" for a, b in ERAS],
    }

    books = []
    try:
        jkp = load_jkp_monthly(start, end)
        jkp_frames = by_month(jkp)
        base["jkp_rows"] = int(len(jkp))
        base["jkp_months"] = int(jkp["ym"].nunique())
    except CharacteristicPanelUnavailable as exc:
        jkp_frames = None
        base["jkp_refused"] = str(exc)
    try:
        ibes = load_ibes_dispersion(start, end)
        ibes_frames = by_month(ibes)
        base["ibes_rows"] = int(len(ibes))
        base["ibes_months"] = int(ibes["ym"].nunique())
    except CharacteristicPanelUnavailable as exc:
        ibes_frames = None
        base["ibes_refused"] = str(exc)

    if jkp_frames is not None:
        books.append(replay_book_e(panel, jkp_frames, smoke=smoke))
        books.append(replay_book_f(panel, jkp_frames, smoke=smoke))
    else:
        for lbl, key, pre in (("qmj_quality_tilt_v0", "E", "TRIAL-DRAFT-E"),
                              ("seasonality_11_20_v0", "F", "TRIAL-DRAFT-F")):
            books.append({"book": lbl, "book_key": key, "prereg": pre,
                          "ran": False, "refused": base["jkp_refused"]})
    if ibes_frames is not None:
        books.append(replay_book_g(panel, ibes_frames, smoke=smoke))
    else:
        books.append({"book": "forecast_dispersion_v0", "book_key": "G",
                      "prereg": "TRIAL-DRAFT-G", "ran": False,
                      "refused": base["ibes_refused"]})

    pvals = {name: None for name in DECLARED_FAMILY}
    for b in books:
        if b.get("ran"):
            pvals[b["book"]] = _p((b.get("cells") or {}).get("primary_floor"))
    family_holm = holm(pvals, family=FAMILY)
    family_holm["c_v1_is_computed_elsewhere"] = (
        "`disposition_overhang_conditioner_v1` is this family's fourth declared "
        "primary and is read by `scripts/night_c_falsifiers.C_v1`. It is NAMED "
        "here without a p-value rather than dropped, because Holm over three "
        "p-values in a family that declared four is a different correction and "
        "a reader has to see which happened. `C_v1`'s own receipt reads this "
        "one and prints the complete four-leg block.")

    d = out_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = t0.strftime("%Y-%m-%dT%H%M%SZ")
    written = []
    for b in books:
        name = f"{b['book']}_{stamp}{'_smoke' if smoke else ''}.json"
        (d / name).write_text(json.dumps(b, indent=2, default=str),
                              encoding="utf-8")
        written.append(str(d / name))

    ran = [b for b in books if b.get("ran")]
    return {
        **base, "books": books, "receipts": written, "holm": family_holm,
        "n_ran": len(ran), "n_refused": len(books) - len(ran),
        "headline": ("; ".join(b["headline"] for b in ran) if ran
                     else "no leg ran"),
        "next_test": ("`C_v1` -- the fourth declared primary of this family -- "
                      "and then, for whichever book carries a POSITIVE $10M cell "
                      "at |t| >= 2, the allocator question chunk 13b asks."),
        "verdict": ("SMOKE — proves the job runs end to end; no verdict is read "
                    "from a shortened window on the largest names"
                    if smoke else
                    "read each book against its own pre-registration's decision "
                    "rule, under the family Holm block above; both floors are "
                    "printed for every book or neither is"),
    }


__all__ = ["B_books_efg_replay", "CharacteristicPanelUnavailable",
           "DECLARED_EFFECT", "DECLARED_FAMILY", "FAMILY", "K",
           "SECONDARY_FLOOR_USD", "T_ALIVE", "book_e_selector",
           "book_f_selector", "book_g_selector", "characteristic_rows",
           "coverage_and_contamination", "covered_permnos", "decide_cell",
           "dispersion_si_rows", "era_stability", "fama_macbeth",
           "find_run_receipt", "jkp_files", "load_ibes_dispersion",
           "load_jkp_monthly", "by_month", "recompute_mde", "run_cell",
           "survives", "two_sided_p"]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    print(json.dumps(B_books_efg_replay(smoke=a.smoke), indent=1, default=str))
