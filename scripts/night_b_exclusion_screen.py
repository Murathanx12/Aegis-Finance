"""B -- the exclusion screen the ledger asked for three times and never ran.

RE-TEST 1 OF THE 2026-09-19 FAILURE THESIS
==========================================
`NEGATIVE_RESULTS.md` says the same thing in three independent sections and
never acts on it:

  * §26 (TRIAL-ABIO-KIRK): `io_level` in the small segment carries a mean rank
    IC of +4.91% at **t 11.29** -- one of the largest IC t-statistics in the
    whole 179-candidate programme -- against a long-only top-decile book whose
    GROSS excess t is **+0.02**.
  * §27 (TRIAL-OPT-COHORT): `skew_25d` 8.34 / +1.01 and `skew_resid` 7.90 /
    +1.02. Same shape, different data.
  * §28 (INSTR-RANK-DEAD) explains it: **150.6 of 150.8 bps (99.9%)** of
    `io_level`'s decile spread and **93.4 of 105.8 (88%)** of `skew_25d`'s sit
    in the SHORT leg. "High institutional ownership does not predict
    outperformance, LOW institutional ownership predicts underperformance."

§28 closes with the sentence this job exists for: *"These signals are usable
long-only only defensively, as exclusion screens, never as a return source.
Whether an exclusion screen clears our bars is a separate question needing its
own registration."* It was written 2026-08-02 and nobody ran it.

WHAT IS TESTED, EXACTLY
=======================
Not a new book. The EXISTING long-only book the night factory already replays
-- Book F, `seasonality_11_20_v0`, the one positive $10M cell in the programme
(`B_books_efg_replay_run01`, 2026-09-13) -- with the screen variable's WORST
decile removed from the eligible pool BEFORE selection, at the same cost model,
the same floor and the same universe.

Three arms per screen, replayed in ONE pass over the identical month set so the
differences are exactly paired:

  unscreened      Book F on the covered pool                 (the incumbent)
  screened        Book F on the pool minus the worst decile  (the candidate)
  random_twin     Book F on the pool minus the SAME NUMBER
                  of names drawn at random that month        (the control)

The random twin is the whole point. Removing any decile changes the pool's
size, its liquidity mix and the book's turnover; a screened book that beat the
unscreened one without beating a random exclusion of the same count would have
measured the removal, not the RANK. The twin is re-drawn at every floor for
TRIAL-H5's reason (a corner-dependent control moves with the corner).

THE DIRECTION IS THE LEDGER'S, NOT A CHOICE MADE HERE
=====================================================
Which end is "worst" is frozen per screen in `SCREENS` from the measured
§26/§27/§28 receipts, before this file computed anything:

  io_level, io_abn   LOW is the bad end   (low institutional ownership)
  skew_25d, skew_resid HIGH is the bad end (dear crash insurance)

A screen whose worst end were chosen after seeing its number would be a
one-sided test wearing a two-sided coat.

WHAT IT REFUSES
===============
Every screen names the files its rank is built from. A screen whose sources are
not on this checkout is REFUSED BY NAME, with the exact paths that were looked
for, and is carried into the Holm block as a leg WITHOUT a p-value -- never
dropped, because Holm over two p-values in a family that declared four is a
different correction and a reader has to see which happened. Nothing is
fabricated, interpolated or back-filled.

    python -m scripts.night_factory_jobs B_exclusion_screen --smoke
    python -m scripts.night_factory_jobs B_exclusion_screen --floor-usd 3000000

LICENCE: PRODUCT_EXPERIMENT. Nothing here orders, seeds or promotes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.night_books_efg_replay import (
    K,
    SECONDARY_FLOOR_USD,
    SMOKE_END,
    SMOKE_NAMES,
    SMOKE_START,
    book_f_selector,
    by_month,
    covered_permnos,
    coverage_and_contamination,
    load_jkp_monthly,
    CharacteristicPanelUnavailable,
    _pool_filter,
    _seasonality_columns,
)
from scripts.night_first_books_replay import (
    COST_BPS_PER_SIDE,
    COST_CURVE,
    ERAS,
    FULL_END,
    FULL_START,
    _cost,
    _turnover_matched_draw,
    eligible,
    holm,
    load_monthly_panel,
    newey_west_t,
    two_sided_p,
    wrds_dir,
)

logger = logging.getLogger("b_exclusion_screen")

JOB = "B_exclusion_screen"
LICENCE = "PRODUCT_EXPERIMENT"

#: A night job dates its outputs by the DAY it runs. Never a literal: three
#: idle-queue jobs carried `RUN_DATE = "2026-09-12"` and overwrote a committed
#: receipt three nights running (2026-09-18). Unset means TODAY; the factory
#: sets `NIGHT_RUN_DATE` for its children so a past night is reproducible.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

#: The family, DECLARED AT ITS SIZE BEFORE THE READ: one primary per screen.
FAMILY = "EXCLUSION_SCREEN_2026_09_19"

#: The book the screen is applied to. Named, not parameterised: this is a test
#: of a defensive overlay on the ONE long-only construction in this repository
#: with a positive $10M cell, and a screen measured on a different book would
#: be a different question.
HOST_BOOK = "seasonality_11_20_v0"
HOST_PREREG = "TRIAL-DRAFT-F-calendar-seasonality-v0 (UNSIGNED)"

#: The decile removed. Frozen; a screen that swept this would be sweeping a
#: parameter against the outcome.
EXCLUDE_SHARE = 0.10

#: Book F's live floor. `--floor-usd` moves the book, the screen and BOTH
#: controls together -- the only way the difference stays a difference in
#: selection (TRIAL-H5's lesson).
DEFAULT_FLOOR_USD = SECONDARY_FLOOR_USD

#: The 60-CALENDAR-DAY availability lag on 13F holdings, frozen at
#: TRIAL-ABIO-KIRK's registration: a quarter's `fdate` may only inform a
#: formation month `m` when `fdate + 60 days <= m`'s close. Anything faster
#: acts on a filing before it was public.
IO_LAG_DAYS = 60

#: The Kirk-STYLE characteristic set the abnormal leg residualises on, frozen
#: at TRIAL-ABIO-KIRK and re-declared here because this file computes it from
#: THIS checkout's own columns rather than the module's.
IO_ABN_CHARS = ("log_mktcap", "mom_12_1", "log_dvol", "inv_price", "log_age")

#: The option-implied residual's controls (§27's `skew_resid` arm): the level
#: of implied volatility first, because a skew that predicts exactly as well as
#: ATM implied vol is volatility wearing a name (`learner/features_options.py`).
SKEW_RESID_CHARS = ("atm_iv_30d", "log_mktcap", "log_dvol")

#: |t| at which a difference is called alive. The same line every book in this
#: repository is read at.
T_ALIVE = 2.0


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / f"night_factory_{RUN_DATE}"


def learner_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "learner"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(x, n: int = 6):
    return None if x is None else round(float(x), n)


class RankSourceMissing(RuntimeError):
    """A rank's source files are not on this checkout. Named, never faked."""

    def __init__(self, screen: str, paths: list[Path]):
        self.screen = screen
        self.paths = [str(p) for p in paths]
        super().__init__(
            f"REFUSED: {screen} cannot be built on this checkout -- "
            f"{len(self.paths)} source file(s) are absent. Looked for: "
            + "; ".join(self.paths[:6])
            + ("; ..." if len(self.paths) > 6 else ""))


# --------------------------------------------------------------------------
# the rank sources
#
# Each screen declares the files it reads and builds a per-month percentile
# rank in [0, 1] over whatever names it covers. A name with no rank in a month
# is NOT excluded and NOT counted as covered: an exclusion screen that removed
# everything it could not see would be a coverage filter wearing a screen's
# name.


def _pct_rank(values: dict) -> dict:
    """Percentile rank in (0, 1] within one month's cross-section."""
    if not values:
        return {}
    items = sorted(values.items(), key=lambda kv: kv[1])
    n = len(items)
    return {int(p): (i + 1) / n for i, (p, _v) in enumerate(items)}


def _resid_rank(frame, target: str, regressors) -> dict:
    """Within-month OLS residual of `target` on `regressors`, ranked.

    An intercept is always fitted. A month with fewer rows than regressors + 3
    returns `{}` rather than a fit nobody could defend, and the count of such
    months is printed on the receipt.
    """
    import numpy as np

    cols = [c for c in regressors if c in frame.columns]
    sub = frame.dropna(subset=[target, *cols])
    if len(sub) < len(cols) + 3:
        return {}
    y = sub[target].to_numpy(dtype="float64")
    X = np.column_stack([np.ones(len(sub))]
                        + [sub[c].to_numpy(dtype="float64") for c in cols])
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:                                # noqa: PERF203
        return {}
    resid = y - X @ beta
    return _pct_rank(dict(zip(sub["permno"].astype("int64"), resid)))


def crsp_shrout_monthly(start: int, end: int):
    """Month-end shares outstanding per permno, from the same CRSP files the
    replay panel is built from. Three columns; nothing else is read."""
    import pandas as pd

    missing, frames = [], []
    for y in range(int(start), int(end) + 1):
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if not p.is_file():
            missing.append(p)
            continue
        d = pd.read_parquet(p, columns=["permno", "date", "shrout"])
        d["date"] = pd.to_datetime(d["date"])
        d["ym"] = d["date"].dt.to_period("M")
        g = (d.sort_values("date").groupby(["permno", "ym"], sort=False)
             .agg(shrout=("shrout", "last")).reset_index())
        frames.append(g)
    if not frames:
        raise RankSourceMissing("crsp_shrout", missing)
    return pd.concat(frames, ignore_index=True)


def _panel_characteristics(panel):
    """The five Kirk-style characteristics, from the replay panel's own columns.

    Every one is computed from the month that has ALREADY CLOSED, which is the
    month the rank is used in, so nothing here is contemporaneous with the
    return it will help earn.
    """
    import numpy as np

    df = panel.sort_values(["permno", "ym"], kind="mergesort").copy()
    df["log_dvol"] = np.log(df["dv"].clip(lower=1.0))
    df["inv_price"] = 1.0 / df["price"].clip(lower=0.01)
    g = df.groupby("permno", sort=False)
    # 12-1 momentum: the product of months t-12..t-2, so the formation month's
    # own return never enters it.
    lg = np.log1p(df["ret_m"].clip(lower=-0.999))
    df["_lg"] = lg
    roll = g["_lg"].apply(lambda s: s.shift(1).rolling(11, min_periods=8).sum())
    df["mom_12_1"] = np.expm1(roll.reset_index(level=0, drop=True))
    first = g["ym"].transform("min")
    df["log_age"] = np.log1p([max(0, (a - b).n) for a, b in
                              zip(df["ym"], first)])
    return df[["permno", "ym", "log_dvol", "inv_price", "mom_12_1", "log_age",
               "price"]].copy()


def build_io_ranks(panel, *, start: int, end: int, abnormal: bool) -> dict:
    """`io_level` (or `io_abn`) as a per-month percentile rank.

    io = institutional shares held / shares outstanding, from the WRDS s34
    holdings this checkout carries, aggregated per (fdate, cusip8), linked to
    permno through `tr13f_permno_link.json`, and made available only 60
    calendar days after the filing date. `abnormal=True` residualises it on the
    five frozen characteristics within each month (TRIAL-ABIO-KIRK's io_abn).
    """
    import numpy as np
    import pandas as pd

    link_path = wrds_dir() / "tr13f_permno_link.json"
    holdings = [wrds_dir() / f"tr13f_s34_{y}.parquet"
                for y in range(int(start) - 1, int(end) + 1)]
    have = [p for p in holdings if p.is_file()]
    if not link_path.is_file() or not have:
        raise RankSourceMissing("io_level" if not abnormal else "io_abn",
                                ([link_path] if not link_path.is_file() else [])
                                + [p for p in holdings if not p.is_file()])
    link = {str(k).upper()[:8]: int(v) for k, v in
            json.loads(link_path.read_text(encoding="utf-8")).items()}

    parts = []
    for p in have:
        d = pd.read_parquet(p, columns=["fdate", "cusip", "shares"])
        d = d.dropna(subset=["shares"])
        d["cusip"] = d["cusip"].astype(str).str.upper().str[:8]
        d["permno"] = d["cusip"].map(link)
        d = d.dropna(subset=["permno"])
        d["fdate"] = pd.to_datetime(d["fdate"])
        g = (d.groupby(["fdate", "permno"], sort=False)["shares"].sum()
             .reset_index())
        parts.append(g)
    own = pd.concat(parts, ignore_index=True)
    own["permno"] = own["permno"].astype("int64")
    # The availability rule, applied to the FILING date: the earliest formation
    # month whose close is at least 60 days after fdate.
    own["avail"] = (own["fdate"] + pd.Timedelta(days=IO_LAG_DAYS)
                    ).dt.to_period("M")

    shr = crsp_shrout_monthly(start, end)
    chars = _panel_characteristics(panel)
    months = sorted(panel["ym"].unique())
    shr_by = {ym: dict(zip(g["permno"].astype("int64"),
                           g["shrout"].astype("float64")))
              for ym, g in shr.groupby("ym", sort=False)}
    chars_by = {ym: g for ym, g in chars.groupby("ym", sort=False)}

    # Forward-fill the latest AVAILABLE quarter into every formation month.
    own = own.sort_values("avail", kind="mergesort")
    latest: dict[int, float] = {}
    by_avail: dict = {}
    for avail, g in own.groupby("avail", sort=True):
        by_avail[avail] = dict(zip(g["permno"].astype("int64"),
                                   g["shares"].astype("float64")))

    ranks: dict = {}
    degenerate = 0
    for ym in months:
        for avail in sorted(k for k in by_avail if k <= ym):
            if avail in by_avail:
                latest.update(by_avail.pop(avail))
        shrout = shr_by.get(ym) or {}
        io = {}
        for permno, held in latest.items():
            so = shrout.get(int(permno))
            if not so or so <= 0:
                continue
            frac = float(held) / (float(so) * 1000.0)
            if 0.0 < frac <= 1.5:        # >150% of shares out is a link error
                io[int(permno)] = frac
        if not io:
            continue
        if not abnormal:
            ranks[ym] = _pct_rank(io)
            continue
        cg = chars_by.get(ym)
        if cg is None or cg.empty:
            degenerate += 1
            continue
        frame = cg.copy()
        frame["io"] = [io.get(int(p)) for p in frame["permno"]]
        shr_here = [shrout.get(int(p)) for p in frame["permno"]]
        frame["log_mktcap"] = [
            math.log(max(px * (so or 0.0) * 1000.0, 1.0))
            if (so and px and px > 0) else np.nan
            for px, so in zip(frame["price"], shr_here)]
        r = _resid_rank(frame, "io", IO_ABN_CHARS)
        if r:
            ranks[ym] = r
        else:
            degenerate += 1
    ranks["_degenerate_months"] = degenerate            # read by the receipt
    return ranks


def build_skew_ranks(panel, *, residual: bool) -> dict:
    """`skew_25d` (or `skew_resid`) as a per-month percentile rank.

    `learner/features_options.parquet` carries `skew_25d_30d` -- 25-delta put
    IV minus 25-delta call IV, the price of crash insurance relative to upside
    -- daily per permno, 1998-2024. The month's LAST observation is the one a
    formation at that close could have seen.
    """
    import numpy as np
    import pandas as pd

    path = learner_dir() / "features_options.parquet"
    if not path.is_file():
        raise RankSourceMissing("skew_25d" if not residual else "skew_resid",
                                [path])
    cols = ["permno", "date", "skew_25d_30d"]
    if residual:
        cols.append("atm_iv_30d")
    opt = pd.read_parquet(path, columns=cols)
    opt["date"] = pd.to_datetime(opt["date"])
    opt["ym"] = opt["date"].dt.to_period("M")
    keep = set(panel["ym"].unique())
    opt = opt[opt["ym"].isin(keep)]
    opt = (opt.sort_values("date").groupby(["permno", "ym"], sort=False)
           .tail(1))
    opt = opt.dropna(subset=["skew_25d_30d"])
    if not residual:
        return {ym: _pct_rank(dict(zip(g["permno"].astype("int64"),
                                       g["skew_25d_30d"].astype("float64"))))
                for ym, g in opt.groupby("ym", sort=False)}

    chars = _panel_characteristics(panel)
    shr = crsp_shrout_monthly(int(str(min(keep))[:4]), int(str(max(keep))[:4]))
    shr_by = {ym: dict(zip(g["permno"].astype("int64"),
                           g["shrout"].astype("float64")))
              for ym, g in shr.groupby("ym", sort=False)}
    chars_by = {ym: g for ym, g in chars.groupby("ym", sort=False)}
    ranks: dict = {}
    degenerate = 0
    for ym, g in opt.groupby("ym", sort=False):
        cg = chars_by.get(ym)
        if cg is None or cg.empty:
            degenerate += 1
            continue
        shrout = shr_by.get(ym) or {}
        frame = cg.merge(g[["permno", "skew_25d_30d", "atm_iv_30d"]],
                         on="permno", how="inner")
        if frame.empty:
            degenerate += 1
            continue
        frame["log_mktcap"] = [
            math.log(max(px * (shrout.get(int(p)) or 0.0) * 1000.0, 1.0))
            if (shrout.get(int(p)) and px and px > 0) else np.nan
            for p, px in zip(frame["permno"], frame["price"])]
        r = _resid_rank(frame, "skew_25d_30d", SKEW_RESID_CHARS)
        if r:
            ranks[ym] = r
        else:
            degenerate += 1
    ranks["_degenerate_months"] = degenerate
    return ranks


#: THE FAMILY, DECLARED AT SIZE FOUR BEFORE THE FIRST NUMBER.
#:
#: `worst_end` is the ledger's MEASURED direction (§26/§27/§28), frozen here so
#: no read may choose it: "low" means the BOTTOM decile is removed, "high" the
#: TOP decile.
SCREENS: dict[str, dict] = {
    "io_level": {
        "worst_end": "low",
        "receipt": ("NEGATIVE_RESULTS §26/§28: 150.6 of 150.8 bps (99.9%) of "
                    "the decile spread sits in the SHORT leg -- LOW "
                    "institutional ownership predicts UNDERperformance; high "
                    "IO predicts nothing (banked book gross t +0.02 at IC "
                    "t 11.29)"),
        "source": ("wrds/tr13f_s34_<year>.parquet holdings summed per "
                   "(fdate, cusip8), linked by wrds/tr13f_permno_link.json, "
                   "divided by CRSP month-end shrout, lagged "
                   f"{IO_LAG_DAYS} calendar days from the filing date"),
        "builder": lambda panel, s, e: build_io_ranks(panel, start=s, end=e,
                                                      abnormal=False),
    },
    "io_abn": {
        "worst_end": "low",
        "receipt": ("NEGATIVE_RESULTS §26: io_abn small IC t 10.64, gross t "
                    "+1.16; the pre-declared comparison fired -- residualising "
                    "REMOVED information (pooled io_level 7.77 vs io_abn 6.89)"),
        "source": ("io_level residualised within each month on "
                   + ", ".join(IO_ABN_CHARS)
                   + " (Kirk-STYLE; this checkout's own columns)"),
        "builder": lambda panel, s, e: build_io_ranks(panel, start=s, end=e,
                                                      abnormal=True),
    },
    "skew_25d": {
        "worst_end": "high",
        "receipt": ("NEGATIVE_RESULTS §27/§28: 93.4 of 105.8 bps (88%) in the "
                    "short leg -- HIGH put-call skew predicts UNDERperformance "
                    "(IC t 8.34, banked book gross t +1.01)"),
        "source": ("learner/features_options.parquet `skew_25d_30d` (25-delta "
                   "put IV minus 25-delta call IV), the month's LAST daily "
                   "observation"),
        "builder": lambda panel, s, e: build_skew_ranks(panel, residual=False),
    },
    "skew_resid": {
        "worst_end": "high",
        "receipt": ("NEGATIVE_RESULTS §27: skew_resid IC t 7.90, gross t "
                    "+1.02 -- the third residualisation receipt, same shape"),
        "source": ("skew_25d_30d residualised within each month on "
                   + ", ".join(SKEW_RESID_CHARS)),
        "builder": lambda panel, s, e: build_skew_ranks(panel, residual=True),
    },
}


def _seed_for(screen: str) -> int:
    """A per-screen seed that is the same on every machine and every run.

    `hash()` is salted per process (PYTHONHASHSEED), so a seed derived from it
    would draw a different control every night while the receipt printed one
    number for it.
    """
    return 0x5CEE0000 + int(hashlib.sha256(screen.encode()).hexdigest()[:6], 16)


def excluded_names(pool, ranks_for_month: dict, *, worst_end: str,
                   share: float = EXCLUDE_SHARE) -> list[int]:
    """The worst `share` of the names in `pool` that CARRY a rank this month.

    A name with no rank is never excluded. The cut is taken inside the pool,
    not in the rank file's own universe: excluding a decile of a wider
    cross-section would remove a different number of tradable names at every
    floor and make the two floors incomparable.
    """
    scored = [(int(p), ranks_for_month.get(int(p)))
              for p in pool["permno"].astype("int64")]
    scored = [(p, v) for p, v in scored if v is not None]
    if not scored:
        return []
    scored.sort(key=lambda kv: kv[1], reverse=(worst_end == "high"))
    n = int(len(scored) * float(share))
    return [p for p, _ in scored[:n]]


# --------------------------------------------------------------------------
# the three arms, in ONE pass


def run_screen_arms(panel, select, *, ranks: dict, worst_end: str,
                    pool_filter, floor_usd, k: int, seed: int) -> dict:
    """Unscreened / screened / random-exclusion twin, month by month, paired.

    ONE pass, so the three arms see the identical month set, the identical
    pool and the identical selector. Running them as three separate replays
    would let one arm skip a month the others kept and turn a difference of
    selections into a difference of samples.

    Each arm carries its OWN previous holdings, so each pays its own turnover
    at the same 25 bps. The random twin removes exactly as many names as the
    screen did, drawn without replacement from the same pool -- so pool SIZE,
    and the mechanical part of the turnover change, are matched by
    construction and what survives is the RANK.
    """
    import numpy as np

    months = sorted(panel["ym"].unique())
    frames = {ym: g for ym, g in panel.groupby("ym", sort=False)}
    arms = {"unscreened": [], "screened": [], "random_twin": []}
    prev = {a: set() for a in arms}
    prev_book_twin: set = set()
    twin_r: list[float] = []
    blocks: list[str] = []
    n_excluded: list[int] = []
    pool_sizes: list[int] = []
    months_with_no_rank = 0

    for i in range(len(months) - 1):
        ym, nxt = months[i], months[i + 1]
        pool = eligible(frames[ym], floor_usd=floor_usd)
        if pool_filter is not None:
            pool = pool_filter(pool, ym)
        if pool is None or pool.empty:
            continue
        nf = frames.get(nxt)
        if nf is None:
            continue
        month_ranks = ranks.get(ym) or {}
        drop = excluded_names(pool, month_ranks, worst_end=worst_end)
        if not drop:
            months_with_no_rank += 1
        # The floor is part of the draw: TRIAL-H5's control moves with the
        # corner, so a $3M pass and a $10M pass draw different twins.
        rng = np.random.default_rng(int(seed) + int(ym.year) * 100
                                    + int(ym.month)
                                    + int(floor_usd or 0) // 1000)
        cand = [int(x) for x in pool["permno"].astype("int64")]
        rand_drop = ([int(cand[int(j)]) for j in
                      rng.choice(len(cand), size=min(len(drop), len(cand)),
                                 replace=False)] if drop else [])
        pools = {
            "unscreened": pool,
            "screened": pool[~pool["permno"].astype("int64").isin(set(drop))],
            "random_twin": pool[~pool["permno"].astype("int64")
                                .isin(set(rand_drop))],
        }
        picks = {a: list(select(p, ym) or [])[: int(k)] for a, p in pools.items()}
        if not all(picks.values()):
            continue
        rmap = dict(zip(nf["permno"], nf["ret_m"]))
        rets = {}
        ok = True
        for a, names in picks.items():
            r = [rmap[p] for p in names if p in rmap]
            if not r:
                ok = False
                break
            rets[a] = float(np.mean(r)) - _cost(prev[a], set(names))
        if not ok:
            continue
        # The host book's OWN random-universe twin, unchanged from the replay,
        # so the screened book can also be read against the control Book F was
        # registered against rather than only against its unscreened self.
        tw = _turnover_matched_draw(pool, picks["unscreened"],
                                    prev["unscreened"], prev_book_twin, rng)
        tr = [rmap[p] for p in tw if p in rmap]
        if not tr:
            continue
        twin_r.append(float(np.mean(tr)) - _cost(prev_book_twin, set(tw)))
        prev_book_twin = set(tw)
        for a in arms:
            arms[a].append(rets[a])
            prev[a] = set(picks[a])
        blocks.append(str(nxt))
        n_excluded.append(len(drop))
        pool_sizes.append(int(len(pool)))

    return {
        "blocks": blocks,
        "arms": arms,
        "host_random_universe_twin": twin_r,
        "n_blocks": len(blocks),
        "median_excluded_per_month": (int(np.median(n_excluded))
                                      if n_excluded else 0),
        "median_pool_size": int(np.median(pool_sizes)) if pool_sizes else 0,
        "months_with_no_rank_in_pool": months_with_no_rank,
    }


def _difference(a: list, b: list, blocks: list, *, label: str) -> dict:
    """Paired block difference with a Newey-West lag-2 t, and its eras."""
    import numpy as np
    import pandas as pd

    d = [float(x) - float(y) for x, y in zip(a, b)]
    t = newey_west_t(d)
    eras = {}
    if blocks:
        years = [pd.Period(x).year for x in blocks]
        for lo, hi in ERAS:
            idx = [i for i, y in enumerate(years) if lo <= y <= hi]
            if len(idx) >= 12:
                sub = [d[i] for i in idx]
                eras[f"{lo}-{hi}"] = {
                    "n_blocks": len(sub),
                    "mean_monthly": _r(float(np.mean(sub))),
                    "nw_lag2_t": _r(newey_west_t(sub), 4)}
    return {
        "label": label,
        "n_blocks": len(d),
        "mean_excess_net_monthly": _r(float(np.mean(d))) if d else None,
        "nw_lag2_t": _r(t, 4),
        "p_two_sided": _r(two_sided_p(t), 6),
        "by_era": eras,
        "n_positive_eras": sum(1 for v in eras.values()
                               if (v["mean_monthly"] or 0) > 0),
        "n_eras_read": len(eras),
    }


def _verdict(vs_unscreened: dict, vs_twin: dict) -> dict:
    """Both differences must be alive and positive, or the screen is not one.

    Beating the unscreened book alone is not enough: any exclusion changes the
    pool, and the random twin is what separates "the RANK helped" from "the
    removal helped". Beating the twin alone is not enough either -- a screen
    that beats a random exclusion while losing to holding the whole pool has
    made the book worse and found a less-bad way of making it worse.
    """
    mu, tu = (vs_unscreened.get("mean_excess_net_monthly"),
              vs_unscreened.get("nw_lag2_t"))
    mt, tt = (vs_twin.get("mean_excess_net_monthly"),
              vs_twin.get("nw_lag2_t"))
    if mu is None or mt is None:
        return {"verdict": "CANNOT_DETERMINE",
                "reading": ("one of the two differences produced no block "
                            "mean; a check that did not run is not a check "
                            "that passed")}
    if mu <= 0 or mt <= 0:
        return {"verdict": "FAILED_VARIANT",
                "reading": (f"the screen is {mu:+.6f}/month against the "
                            f"unscreened book (t {tu}) and {mt:+.6f}/month "
                            f"against a random exclusion of the same count "
                            f"(t {tt}); a point estimate at or below zero is "
                            f"not rescued by under-power")}
    if (tu or 0) >= T_ALIVE and (tt or 0) >= T_ALIVE:
        return {"verdict": "PRODUCT_PROMISING",
                "reading": (f"+{mu:.6f}/month vs the unscreened book (t {tu}) "
                            f"and +{mt:.6f}/month vs a random exclusion of the "
                            f"same count (t {tt}); both clear |t| >= "
                            f"{T_ALIVE}. Read it under the family Holm block, "
                            f"not alone.")}
    return {"verdict": "CONDITIONAL",
            "reading": (f"both differences are positive (+{mu:.6f} t {tu} vs "
                        f"unscreened, +{mt:.6f} t {tt} vs the random "
                        f"exclusion) and at least one is below |t| >= "
                        f"{T_ALIVE}. Positive and under-powered is not a "
                        f"result; it is a reason to keep the lane open.")}


# --------------------------------------------------------------------------
# the job


def B_exclusion_screen(*, smoke: bool = False,                   # noqa: N802
                        floor_usd: float | None = None) -> dict:
    """One receipt: every declared screen, on the host book, at one floor."""
    t0 = datetime.now(timezone.utc)
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    floor = float(DEFAULT_FLOOR_USD if floor_usd is None else floor_usd)

    base = {
        "job": JOB, "family": FAMILY, "licence": LICENCE,
        "llm_spend_usd": 0.0,
        "run_date": RUN_DATE,
        "window": [start, end], "smoke": bool(smoke),
        "floor_usd": floor,
        "host_book": HOST_BOOK, "host_prereg": HOST_PREREG,
        "exclude_share": EXCLUDE_SHARE,
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "question": (
            "NEGATIVE_RESULTS §26/§27/§28 measure enormous rank information "
            "(IC t up to 11.3) living in a SHORT leg a long-only book cannot "
            "hold, and say three separate times that using these signals as "
            "EXCLUSION SCREENS is untested. Does removing the worst decile of "
            "io_level / io_abn / skew_25d / skew_resid from an existing "
            "long-only book's pool beat (a) the unscreened book and (b) a "
            "random exclusion of the same count, at the same cost model?"),
        "registered_construction": {
            "host_book": HOST_BOOK,
            "host_construction": {
                "columns": list(_seasonality_columns()),
                "cut": "top tercile of the equal-weight mean of the "
                       "within-month z-scores",
                "k": K, "hold": "one month, monthly rebalance"},
            "screen": f"remove the worst {EXCLUDE_SHARE:.0%} of the POOL by "
                      f"the screen's own rank, before selection",
            "worst_end_is_the_ledgers": (
                "frozen per screen in SCREENS from the measured §26/§27/§28 "
                "receipts, before this file computed anything"),
            "controls": ["the unscreened book on the identical months",
                         "a random exclusion of the SAME COUNT, re-drawn per "
                         "floor", "the host book's own random-universe twin"],
            "floor_usd": floor,
            "cost_curve": COST_CURVE,
            "cost_bps_per_side": COST_BPS_PER_SIDE,
            "blocks": "one return per MONTH (CANON §58); Newey-West lag 2",
            "honours_the_registration": bool(not smoke),
            "why": ("Book C's 2026-09-13 lesson: run 1 warmed a 60-month "
                    "overhang at 24 months and the receipt said "
                    "`confirm_slice 1995-2024` anyway. A receipt that does "
                    "not print its own construction cannot be checked against "
                    "the registration that licensed it. A SMOKE run cannot "
                    "honour the registered window and says so here."),
        },
    }

    panel = load_monthly_panel(start, end,
                              max_names=SMOKE_NAMES if smoke else None)
    base["months_in_panel"] = int(panel["ym"].nunique())
    base["permnos_in_panel"] = int(panel["permno"].nunique())

    try:
        jkp = load_jkp_monthly(start, end)
        jkp_frames = by_month(jkp)
    except CharacteristicPanelUnavailable as exc:
        return {**base, "screens": {}, "n_ran": 0,
                "n_refused": len(SCREENS),
                "holm": holm({s: None for s in SCREENS}, family=FAMILY),
                "headline": f"no leg ran: {exc}",
                "verdict": ("REFUSED: the host book's own characteristic "
                            f"panel is absent -- {exc}"),
                "family_max_p": None}

    covered = covered_permnos(jkp_frames, book="F")
    cont = coverage_and_contamination(panel, covered, book="F", floor_usd=floor)
    skip = set(cont["excluded_years"])
    host_filter = _pool_filter(covered, skip)
    select = book_f_selector(jkp_frames)
    base["host_coverage"] = cont

    screens: dict = {}
    pvals: dict = {s: None for s in SCREENS}
    for name, decl in SCREENS.items():
        block = {"screen": name, "worst_end": decl["worst_end"],
                 "ledger_receipt": decl["receipt"], "source": decl["source"]}
        try:
            ranks = decl["builder"](panel, start, end)
        except RankSourceMissing as exc:
            block.update({"ran": False, "refused": str(exc),
                          "paths_looked_for": exc.paths})
            screens[name] = block
            logger.warning("%s refused: %s", name, exc)
            continue
        except FileNotFoundError as exc:                         # noqa: PERF203
            block.update({"ran": False,
                          "refused": f"REFUSED: {exc}",
                          "paths_looked_for": [str(exc)]})
            screens[name] = block
            continue
        degenerate = ranks.pop("_degenerate_months", 0)
        res = run_screen_arms(panel, select, ranks=ranks,
                              worst_end=decl["worst_end"],
                              pool_filter=host_filter, floor_usd=floor,
                              k=K, seed=_seed_for(name))
        vs_un = _difference(res["arms"]["screened"], res["arms"]["unscreened"],
                            res["blocks"],
                            label="screened_minus_unscreened")
        vs_tw = _difference(res["arms"]["screened"], res["arms"]["random_twin"],
                            res["blocks"],
                            label="screened_minus_random_exclusion_twin")
        vs_host = _difference(res["arms"]["screened"],
                              res["host_random_universe_twin"], res["blocks"],
                              label="screened_minus_host_random_universe_twin")
        unscreened_vs_host = _difference(
            res["arms"]["unscreened"], res["host_random_universe_twin"],
            res["blocks"], label="unscreened_minus_host_random_universe_twin")
        verdict = _verdict(vs_un, vs_tw)
        block.update({
            "ran": bool(res["n_blocks"]),
            "n_blocks": res["n_blocks"],
            "rank_months": len(ranks),
            "degenerate_rank_months": int(degenerate),
            "median_excluded_per_month": res["median_excluded_per_month"],
            "median_pool_size": res["median_pool_size"],
            "months_with_no_rank_in_pool": res["months_with_no_rank_in_pool"],
            "PRIMARY_vs_unscreened": vs_un,
            "PRIMARY_vs_random_exclusion_twin": vs_tw,
            "SECONDARY_vs_host_random_universe_twin": vs_host,
            "REFERENCE_unscreened_vs_host_twin": unscreened_vs_host,
            "verdict_block": verdict,
            "verdict": verdict["verdict"] + " — " + verdict["reading"],
            "headline": (
                f"{name} (exclude worst {EXCLUDE_SHARE:.0%}, {decl['worst_end']} "
                f"end): {vs_un.get('mean_excess_net_monthly')}/month t "
                f"{vs_un.get('nw_lag2_t')} vs unscreened | "
                f"{vs_tw.get('mean_excess_net_monthly')}/month t "
                f"{vs_tw.get('nw_lag2_t')} vs the random exclusion, over "
                f"{res['n_blocks']} blocks at ${floor:,.0f} "
                f"-> {verdict['verdict']}"),
        })
        # The FAMILY's primary is the difference against the random exclusion:
        # it is the only one of the two that separates the rank from the
        # removal, and a family corrected on the easier comparison would be a
        # family corrected on the wrong test.
        if block["ran"]:
            pvals[name] = vs_tw.get("p_two_sided")
        screens[name] = block

    ran = [b for b in screens.values() if b.get("ran")]
    family = holm(pvals, family=FAMILY)
    family["primary_is_the_random_exclusion_difference"] = (
        "Holm runs over `screened_minus_random_exclusion_twin`, because that "
        "is the comparison that separates the RANK from the REMOVAL. The "
        "difference against the unscreened book is reported for every screen "
        "and corrects nothing.")

    d = out_dir()
    d.mkdir(parents=True, exist_ok=True)

    return {
        **base,
        "screens": screens,
        "n_ran": len(ran), "n_refused": len(SCREENS) - len(ran),
        "holm": family,
        "family_max_p": (max(v["p_raw"] for v in family["per_leg"].values())
                         if family["per_leg"] else None),
        "headline": ("; ".join(b["headline"] for b in ran) if ran
                     else "no screen ran -- every rank source was refused "
                          "by name"),
        "next_test": (
            "a screen whose difference against the RANDOM exclusion clears "
            "Holm at this family's declared size earns one thing: the same "
            "read at the OTHER floor, with the twin re-drawn there. It does "
            "not earn a book -- §26/§27 close the long-only return source and "
            "this job never reopened it."),
        "verdict": ("SMOKE — proves the job runs end to end; no verdict is "
                    "read from a shortened window on the largest names"
                    if smoke else
                    "read each screen against BOTH of its controls under the "
                    "family Holm block; a screen that beats only one of them "
                    "has not been shown to be a screen"),
        "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "written_utc": _now(),
    }
